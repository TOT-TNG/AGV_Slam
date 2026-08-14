import asyncio
import calendar
import html
import json
import logging
import os
import re
from datetime import datetime, date, timedelta, timezone
from typing import Optional

import asyncpg
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

def e(text) -> str:
    """Escape HTML đặc biệt cho nội dung động."""
    return html.escape(str(text) if text is not None else "")

PM = ParseMode.HTML
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters,
)

logger = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────────
_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "telegram_config.json")

def _load_config() -> dict:
    try:
        with open(_CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        logger.error(f"[TELEGRAM] Lỗi đọc config: {e}")
        return {}

def get_token() -> str:
    return os.getenv("TELEGRAM_BOT_TOKEN") or _load_config().get("bot_token", "")

def get_allowed_chats() -> set:
    raw = os.getenv("TELEGRAM_ALLOWED_CHATS") or ""
    if raw:
        return {int(x.strip()) for x in raw.split(",") if x.strip().lstrip("-").isdigit()}
    ids = _load_config().get("allowed_chat_ids", [])
    return set(ids) if ids else set()

# ── Globals ────────────────────────────────────────────────────────────────────
_db_pool: Optional[asyncpg.Pool] = None
_application: Optional[Application] = None
_loop: Optional[asyncio.AbstractEventLoop] = None   # MỚI — event loop lúc bot khởi động, dùng để gửi cảnh báo an toàn từ thread khác (MQTT callback)
_factories_cache: list = []   # danh sách tên nhà máy, load khi bot khởi động

def set_pool(pool: asyncpg.Pool):
    global _db_pool
    _db_pool = pool

async def _load_factories():
    """Load danh sách nhà máy từ DB vào cache."""
    global _factories_cache
    if not _db_pool:
        return
    try:
        async with _db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT DISTINCT factory FROM agv_devices WHERE factory IS NOT NULL AND factory != '' ORDER BY factory"
            )
        _factories_cache = [r["factory"] for r in rows]
        print(f"[TELEGRAM] Loaded {len(_factories_cache)} factories: {_factories_cache}")
    except Exception as ex:
        logger.warning(f"[TELEGRAM] load_factories error: {ex}")

def _detect_factory(text: str) -> Optional[str]:
    """Tìm tên nhà máy trong câu hỏi, trả về tên chính xác từ cache."""
    t = text.lower()
    best = None
    best_len = 0
    for f in _factories_cache:
        if f.lower() in t and len(f) > best_len:
            best, best_len = f, len(f)
    return best

def _factory_cond(factory: Optional[str], params: list) -> tuple:
    """Trả về (sql_snippet, updated_params) để lọc theo nhà máy."""
    if not factory:
        return "", params
    idx = len(params) + 1
    return (
        f" AND agv_id IN (SELECT name FROM agv_devices WHERE factory = ${idx})",
        params + [factory],
    )

# ── Auth ───────────────────────────────────────────────────────────────────────
def _is_allowed(update: Update) -> bool:
    allowed = get_allowed_chats()
    if not allowed:
        return True
    chat_id = update.effective_chat.id if update.effective_chat else None
    return chat_id in allowed

def _parse_date(text: str) -> Optional[date]:
    """Nhận dạng ngày từ text tiếng Việt hoặc định dạng số."""
    t = text.lower().strip()
    today = date.today()

    if any(k in t for k in ["hôm nay", "today", "ngày hôm nay"]):
        return today
    if any(k in t for k in ["hôm qua", "yesterday", "ngày qua"]):
        return today - timedelta(days=1)
    if any(k in t for k in ["ngày kia", "hôm kia"]):
        return today - timedelta(days=2)

    # dd/mm/yyyy hoặc dd-mm-yyyy
    m = re.search(r'(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{4})', t)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass

    # dd/mm (năm hiện tại)
    m = re.search(r'(\d{1,2})[/\-\.](\d{1,2})(?!\d)', t)
    if m:
        try:
            d = date(today.year, int(m.group(2)), int(m.group(1)))
            # Nếu ngày đó trong tương lai → lùi về năm trước
            if d > today:
                d = date(today.year - 1, int(m.group(2)), int(m.group(1)))
            return d
        except ValueError:
            pass

    # "ngày 25 tháng 6" hoặc "25 tháng 6"
    m = re.search(r'(?:ngày\s+)?(\d{1,2})\s+tháng\s+(\d{1,2})(?:\s+(?:năm\s+)?(\d{4}))?', t)
    if m:
        try:
            year = int(m.group(3)) if m.group(3) else today.year
            d = date(year, int(m.group(2)), int(m.group(1)))
            if d > today and not m.group(3):
                d = date(today.year - 1, int(m.group(2)), int(m.group(1)))
            return d
        except ValueError:
            pass

    return None

def _parse_month(text: str) -> Optional[tuple]:
    """Trả về (year, month) từ text như 'tháng 6', 'tháng 6/2026', 'tháng trước'."""
    t = text.lower().strip()
    today = date.today()

    if any(k in t for k in ["tháng trước", "tháng vừa rồi", "tháng qua"]):
        if today.month == 1:
            return (today.year - 1, 12)
        return (today.year, today.month - 1)

    if "tháng này" in t:
        return (today.year, today.month)

    # "tháng 6/2026" hoặc "tháng 6 năm 2026"
    m = re.search(r'tháng\s+(\d{1,2})[/\s]+(?:năm\s+)?(\d{4})', t)
    if m:
        try:
            month, year = int(m.group(1)), int(m.group(2))
            if 1 <= month <= 12:
                return (year, month)
        except ValueError:
            pass

    # "tháng 6" đứng một mình (không có ngày đứng trước)
    m = re.search(r'(?<!ngày\s{0,10}\d{1,2}\s)tháng\s+(\d{1,2})(?!\d)', t)
    if m:
        try:
            month = int(m.group(1))
            if 1 <= month <= 12:
                year = today.year
                if month > today.month:
                    year -= 1
                return (year, month)
        except ValueError:
            pass

    return None

def _fmt_duration(seconds: float) -> str:
    """Chuyển giây sang chuỗi dễ đọc: 2 giờ 30 phút 15 giây."""
    if seconds is None or seconds < 0:
        return "0 giây"
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    parts = []
    if h:
        parts.append(f"{h} giờ")
    if m:
        parts.append(f"{m} phút")
    if sec or not parts:
        parts.append(f"{sec} giây")
    return " ".join(parts)

def _online_label(last_seen) -> str:
    if not last_seen:
        return "⚫ Chưa kết nối"
    if last_seen.tzinfo:
        diff = (datetime.now(timezone.utc) - last_seen).total_seconds()
    else:
        diff = (datetime.utcnow() - last_seen).total_seconds()
    if diff < 60:
        return "🟢 Online"
    if diff < 300:
        return f"🟡 {int(diff)}s trước"
    return f"🔴 Offline ({int(diff // 60)}m trước)"

# ── Menu keyboard ──────────────────────────────────────────────────────────────
def _main_menu(factory: Optional[str] = None) -> InlineKeyboardMarkup:
    factory_label = f"📍 {factory}" if factory else "📍 Chọn nhà máy"
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(factory_label,            callback_data="factory_menu"),
        ],
        [
            InlineKeyboardButton("📊 Thống kê hôm nay",  callback_data="stats_today"),
            InlineKeyboardButton("📅 Tuần này",          callback_data="stats_week"),
        ],
        [
            InlineKeyboardButton("📆 Tháng này",         callback_data="stats_month"),
            InlineKeyboardButton("🏆 Xếp hạng AGV",      callback_data="top"),
        ],
        [
            InlineKeyboardButton("🗓 Ngày cụ thể",        callback_data="ask_date"),
            InlineKeyboardButton("🤖 Trạng thái AGV",    callback_data="status"),
        ],
        [
            InlineKeyboardButton("⏱ Thời gian hoạt động", callback_data="uptime_menu"),
        ],
    ])

def _factory_menu() -> InlineKeyboardMarkup:
    buttons = []
    for f in _factories_cache:
        buttons.append([InlineKeyboardButton(f"🏭 {f}", callback_data=f"set_factory:{f}")])
    buttons.append([
        InlineKeyboardButton("🌐 Tất cả nhà máy", callback_data="set_factory:"),
        InlineKeyboardButton("« Quay lại",         callback_data="back_menu"),
    ])
    return InlineKeyboardMarkup(buttons)

def _uptime_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Hôm nay",    callback_data="uptime_today"),
            InlineKeyboardButton("📅 Tuần này",   callback_data="uptime_week"),
        ],
        [
            InlineKeyboardButton("📆 Tháng này",  callback_data="uptime_month"),
            InlineKeyboardButton("📅 Năm nay",    callback_data="uptime_year"),
        ],
        [
            InlineKeyboardButton("🗓 Ngày cụ thể", callback_data="ask_date_uptime"),
            InlineKeyboardButton("« Quay lại",     callback_data="back_menu"),
        ],
    ])

# ── Query helpers (dùng chung cho lệnh, nút bấm, và chat tự nhiên) ─────────────
def _factory_header(factory: Optional[str]) -> str:
    return f"  <i>📍 {e(factory)}</i>" if factory else ""

async def _query_status(factory: Optional[str] = None) -> str:
    if not _db_pool:
        return "❌ Chưa kết nối database."
    async with _db_pool.acquire() as conn:
        if factory:
            rows = await conn.fetch(
                "SELECT name, agv_type, last_seen FROM agv_devices WHERE factory = $1 ORDER BY name",
                factory,
            )
        else:
            rows = await conn.fetch(
                "SELECT name, agv_type, last_seen FROM agv_devices ORDER BY name"
            )
    if not rows:
        return f"Chưa có AGV nào{' tại ' + e(factory) if factory else ''}."
    lines = [f"<b>🤖 Trạng thái AGV hiện tại</b>{_factory_header(factory)}\n"]
    for r in rows:
        lines.append(f"• <b>{e(r['name'])}</b> ({e(r['agv_type'] or 'unknown')}): {_online_label(r['last_seen'])}")
    return "\n".join(lines)

async def _query_stats(period: str = "today", specific_date: Optional[date] = None,
                       specific_month: Optional[tuple] = None,
                       factory: Optional[str] = None) -> str:
    if not _db_pool:
        return "❌ Chưa kết nối database."

    params = []
    if specific_month:
        year, month = specific_month
        last_day = calendar.monthrange(year, month)[1]
        label = f"tháng {month}/{year}"
        where = "queued_at >= $1 AND queued_at < $2"
        params = [
            datetime(year, month, 1),
            datetime(year, month, last_day, 23, 59, 59) + timedelta(seconds=1),
        ]
    elif specific_date:
        label = specific_date.strftime("ngày %d/%m/%Y")
        where = "queued_at >= $1 AND queued_at < $2"
        params = [
            datetime(specific_date.year, specific_date.month, specific_date.day),
            datetime(specific_date.year, specific_date.month, specific_date.day) + timedelta(days=1),
        ]
    elif period == "week":
        label = "7 ngày qua"
        where = "queued_at >= NOW() - INTERVAL '7 days'"
    elif period == "month":
        label = "30 ngày qua"
        where = "queued_at >= NOW() - INTERVAL '30 days'"
    else:
        label = "hôm nay"
        where = "queued_at >= CURRENT_DATE"

    # status='error' = dispatch lỗi TỰ ĐỘNG (không phải người dùng bấm Hủy) —
    # loại hẳn khỏi thống kê (kể cả tổng), chỉ "Thất bại"/"Hủy" do người dùng
    # chủ động bấm Hủy mới được tính.
    where += " AND status != 'error'"

    fc_sql, params = _factory_cond(factory, params)
    async with _db_pool.acquire() as conn:
        summary = await conn.fetchrow(f"""
            SELECT
                COUNT(*) FILTER (WHERE status = 'completed')  AS completed,
                COUNT(*) FILTER (WHERE status = 'failed')     AS failed,
                COUNT(*) FILTER (WHERE status = 'cancelled')  AS cancelled,
                COUNT(*) FILTER (WHERE status = 'queued')     AS queued,
                COUNT(*) FILTER (WHERE status = 'running')    AS running,
                COUNT(*)                                       AS total,
                AVG(EXTRACT(EPOCH FROM (completed_at - started_at)))
                    FILTER (WHERE status = 'completed'
                            AND started_at IS NOT NULL
                            AND completed_at IS NOT NULL)      AS avg_duration
            FROM agv_task_executions
            WHERE {where}{fc_sql}
        """, *params)
        by_agv = await conn.fetch(f"""
            SELECT agv_id,
                COUNT(*) FILTER (WHERE status = 'completed') AS completed,
                COUNT(*) FILTER (WHERE status = 'failed')    AS failed,
                COUNT(*)                                      AS total
            FROM agv_task_executions
            WHERE {where} AND agv_id IS NOT NULL{fc_sql}
            GROUP BY agv_id ORDER BY total DESC
        """, *params)

    total     = summary["total"] or 0
    completed = summary["completed"] or 0
    failed    = summary["failed"] or 0
    cancelled = summary["cancelled"] or 0
    running   = summary["running"] or 0
    queued    = summary["queued"] or 0
    avg_dur   = summary["avg_duration"]

    lines = [f"<b>📊 Thống kê task – {label}</b>{_factory_header(factory)}\n"]
    lines.append(f"Tổng: <b>{total}</b> task")
    lines.append(f"✅ Hoàn thành: <b>{completed}</b>")
    lines.append(f"❌ Thất bại: <b>{failed}</b>")
    lines.append(f"🚫 Đã hủy: <b>{cancelled}</b>")
    lines.append(f"⏳ Đang chạy: {running}")
    lines.append(f"⌛ Chờ: {queued}")
    if avg_dur is not None:
        lines.append(f"⏱ Thời gian TB: {avg_dur:.1f}s")
    if by_agv:
        lines.append("\n<b>Theo AGV:</b>")
        for r in by_agv:
            lines.append(f"• {e(r['agv_id'])}: {r['completed']} ✅  {r['failed']} ❌  (tổng {r['total']})")
    return "\n".join(lines)

async def _query_top(factory: Optional[str] = None) -> str:
    if not _db_pool:
        return "❌ Chưa kết nối database."
    fc_sql, params = _factory_cond(factory, [])
    async with _db_pool.acquire() as conn:
        rows = await conn.fetch(f"""
            SELECT agv_id,
                COUNT(*) FILTER (WHERE status = 'completed') AS completed,
                COUNT(*) FILTER (WHERE status = 'failed')    AS failed,
                COUNT(*) FILTER (WHERE queued_at >= CURRENT_DATE) AS today
            FROM agv_task_executions
            WHERE agv_id IS NOT NULL{fc_sql}
            GROUP BY agv_id ORDER BY completed DESC LIMIT 10
        """, *params)
    if not rows:
        return "Chưa có dữ liệu task."
    medals = ["🥇", "🥈", "🥉"]
    lines = [f"<b>🏆 Top AGV hoạt động nhiều nhất</b>{_factory_header(factory)}\n"]
    for i, r in enumerate(rows):
        prefix = medals[i] if i < 3 else f"{i+1}."
        lines.append(
            f"{prefix} <b>{e(r['agv_id'])}</b> – {r['completed']} hoàn thành"
            f" / {r['failed']} thất bại  (hôm nay: {r['today']})"
        )
    return "\n".join(lines)

async def _query_uptime(period: str = "today", specific_date: Optional[date] = None,
                        specific_month: Optional[tuple] = None,
                        factory: Optional[str] = None) -> str:
    if not _db_pool:
        return "❌ Chưa kết nối database."

    params = []
    if specific_month:
        year, month = specific_month
        last_day = calendar.monthrange(year, month)[1]
        label = f"tháng {month}/{year}"
        where = "queued_at >= $1 AND queued_at < $2"
        params = [
            datetime(year, month, 1),
            datetime(year, month, last_day, 23, 59, 59) + timedelta(seconds=1),
        ]
    elif specific_date:
        label = specific_date.strftime("ngày %d/%m/%Y")
        where = "queued_at >= $1 AND queued_at < $2"
        params = [
            datetime(specific_date.year, specific_date.month, specific_date.day),
            datetime(specific_date.year, specific_date.month, specific_date.day) + timedelta(days=1),
        ]
    elif period == "week":
        label = "tuần này (7 ngày qua)"
        where = "queued_at >= NOW() - INTERVAL '7 days'"
    elif period == "month":
        label = "tháng này (30 ngày qua)"
        where = "queued_at >= NOW() - INTERVAL '30 days'"
    elif period == "year":
        label = f"năm {date.today().year}"
        where = f"EXTRACT(YEAR FROM queued_at) = {date.today().year}"
    else:
        label = "hôm nay"
        where = "queued_at >= CURRENT_DATE"

    fc_sql, params = _factory_cond(factory, params)
    async with _db_pool.acquire() as conn:
        rows = await conn.fetch(f"""
            SELECT
                agv_id,
                COUNT(*) FILTER (WHERE status = 'completed')  AS completed,
                SUM(EXTRACT(EPOCH FROM (completed_at - started_at)))
                    FILTER (WHERE status = 'completed'
                            AND started_at IS NOT NULL
                            AND completed_at IS NOT NULL)      AS active_seconds
            FROM agv_task_executions
            WHERE {where} AND agv_id IS NOT NULL{fc_sql}
            GROUP BY agv_id
            ORDER BY active_seconds DESC NULLS LAST
        """, *params)

    if not rows:
        return f"<b>⏱ Thời gian hoạt động – {label}</b>{_factory_header(factory)}\n\nChưa có dữ liệu."

    lines = [f"<b>⏱ Thời gian hoạt động – {label}</b>{_factory_header(factory)}\n"]
    total_all = 0.0
    for r in rows:
        secs = float(r["active_seconds"] or 0)
        total_all += secs
        lines.append(
            f"• <b>{e(r['agv_id'])}</b>: {_fmt_duration(secs)}"
            f"  ({r['completed']} lệnh)"
        )
    lines.append(f"\n<b>Tổng toàn đội: {_fmt_duration(total_all)}</b>")
    return "\n".join(lines)

async def _query_single_metric(metric: str, label_period: str,
                               where: str, params: list,
                               factory: Optional[str] = None) -> str:
    """Trả lời ngắn gọn cho 1 chỉ số cụ thể (hoàn thành / hủy / thất bại / uptime)."""
    if not _db_pool:
        return "❌ Chưa kết nối database."

    metric_map = {
        "completed": ("✅ Hoàn thành", "status = 'completed'"),
        "cancelled":  ("🚫 Đã hủy",     "status = 'cancelled'"),
        "failed":     ("❌ Thất bại",    "status = 'failed'"),
        "running":    ("⏳ Đang chạy",   "status = 'running'"),
        "queued":     ("⌛ Đang chờ",    "status = 'queued'"),
    }

    fc_sql, params = _factory_cond(factory, params)
    if metric == "uptime":
        async with _db_pool.acquire() as conn:
            rows = await conn.fetch(f"""
                SELECT agv_id,
                    SUM(EXTRACT(EPOCH FROM (completed_at - started_at)))
                        FILTER (WHERE status = 'completed'
                                AND started_at IS NOT NULL
                                AND completed_at IS NOT NULL) AS secs
                FROM agv_task_executions
                WHERE {where} AND agv_id IS NOT NULL{fc_sql}
                GROUP BY agv_id ORDER BY secs DESC NULLS LAST
            """, *params)
        if not rows:
            return f"<b>⏱ Thời gian hoạt động – {label_period}</b>{_factory_header(factory)}\n\nChưa có dữ liệu."
        lines = [f"<b>⏱ Thời gian hoạt động – {label_period}</b>{_factory_header(factory)}\n"]
        total = 0.0
        for r in rows:
            s = float(r["secs"] or 0)
            total += s
            lines.append(f"• <b>{e(r['agv_id'])}</b>: {_fmt_duration(s)}")
        lines.append(f"\n<b>Tổng: {_fmt_duration(total)}</b>")
        return "\n".join(lines)

    icon, status_cond = metric_map.get(metric, ("📊", f"status = '{metric}'"))
    async with _db_pool.acquire() as conn:
        rows = await conn.fetch(f"""
            SELECT agv_id, COUNT(*) AS cnt
            FROM agv_task_executions
            WHERE {where} AND agv_id IS NOT NULL AND {status_cond}{fc_sql}
            GROUP BY agv_id ORDER BY cnt DESC
        """, *params)
        total = await conn.fetchval(f"""
            SELECT COUNT(*) FROM agv_task_executions
            WHERE {where} AND {status_cond}{fc_sql}
        """, *params)

    label_metric = metric_map.get(metric, ("📊 " + metric,))[0]
    lines = [f"{icon} <b>{label_metric} – {label_period}</b>{_factory_header(factory)}\n"]
    lines.append(f"Tổng: <b>{total}</b> lệnh")
    if rows:
        lines.append("\nTheo AGV:")
        for r in rows:
            lines.append(f"• {e(r['agv_id'])}: {r['cnt']} lệnh")
    return "\n".join(lines)

async def _query_agv(agv_id: str) -> str:
    if not _db_pool:
        return "❌ Chưa kết nối database."
    async with _db_pool.acquire() as conn:
        device = await conn.fetchrow(
            "SELECT name, agv_type, last_seen, last_tag, map_id FROM agv_devices WHERE name = $1",
            agv_id,
        )
        if not device:
            return f"Không tìm thấy AGV: *{agv_id}*"
        stats = await conn.fetchrow("""
            SELECT
                COUNT(*) FILTER (WHERE status = 'completed')                   AS total_completed,
                COUNT(*) FILTER (WHERE status = 'failed')                      AS total_failed,
                COUNT(*) FILTER (WHERE queued_at >= CURRENT_DATE)              AS today,
                COUNT(*) FILTER (WHERE queued_at >= NOW() - INTERVAL '7 days') AS week,
                AVG(EXTRACT(EPOCH FROM (completed_at - started_at)))
                    FILTER (WHERE status = 'completed'
                            AND started_at IS NOT NULL
                            AND completed_at IS NOT NULL)                      AS avg_duration,
                SUM(EXTRACT(EPOCH FROM (completed_at - started_at)))
                    FILTER (WHERE status = 'completed'
                            AND started_at IS NOT NULL
                            AND completed_at IS NOT NULL
                            AND queued_at >= CURRENT_DATE)                     AS active_today,
                SUM(EXTRACT(EPOCH FROM (completed_at - started_at)))
                    FILTER (WHERE status = 'completed'
                            AND started_at IS NOT NULL
                            AND completed_at IS NOT NULL
                            AND queued_at >= NOW() - INTERVAL '7 days')        AS active_week
            FROM agv_task_executions WHERE agv_id = $1
        """, agv_id)
        recent = await conn.fetch("""
            SELECT command, dest_node, status
            FROM agv_task_executions WHERE agv_id = $1
            ORDER BY queued_at DESC LIMIT 5
        """, agv_id)

    si = {"completed": "✅", "failed": "❌", "running": "⏳", "queued": "⌛"}
    lines = [f"<b>🤖 AGV: {e(agv_id)}</b>\n"]
    lines.append(f"Loại: {e(device['agv_type'] or 'N/A')}")
    lines.append(f"Trạng thái: {_online_label(device['last_seen'])}")
    if device["map_id"]:
        lines.append(f"Map: {e(device['map_id'])}")
    if device["last_tag"]:
        lines.append(f"Tag hiện tại: {e(device['last_tag'])}")
    lines.append("\n<b>Thống kê task:</b>")
    lines.append(f"Hôm nay: {stats['today']}  |  7 ngày: {stats['week']}")
    lines.append(f"Tổng hoàn thành: {stats['total_completed']}  |  Thất bại: {stats['total_failed']}")
    if stats["avg_duration"] is not None:
        lines.append(f"Thời gian TB mỗi lệnh: {_fmt_duration(stats['avg_duration'])}")
    lines.append("\n<b>Thời gian hoạt động:</b>")
    lines.append(f"Hôm nay: {_fmt_duration(stats['active_today'] or 0)}")
    lines.append(f"7 ngày: {_fmt_duration(stats['active_week'] or 0)}")
    if recent:
        lines.append("\n<b>5 task gần nhất:</b>")
        for r in recent:
            lines.append(f"{si.get(r['status'], '•')} {e(r['command'])} → {e(r['dest_node'] or '?')}")
    return "\n".join(lines)

# ── /start & /menu ─────────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text(
        f"<b>🤖 AGVmqtt Telegram Bot</b>\n\nChat ID của bạn: <code>{chat_id}</code>\n\nChọn thao tác hoặc nhắn tin bình thường:",
        parse_mode=PM,
        reply_markup=_main_menu(),
    )

async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed(update):
        return
    await update.message.reply_text(
        "Chọn thao tác:",
        reply_markup=_main_menu(),
    )

# ── Lệnh slash (giữ lại cho người quen dùng lệnh) ─────────────────────────────
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed(update):
        return
    await update.message.reply_text(await _query_status(), parse_mode=PM, reply_markup=_main_menu())

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed(update):
        return
    arg = context.args[0] if context.args else "today"
    specific = _parse_date(" ".join(context.args)) if context.args else None
    if specific:
        reply = await _query_stats(specific_date=specific)
    else:
        reply = await _query_stats(arg.lower())
    await update.message.reply_text(reply, parse_mode=PM, reply_markup=_main_menu())

async def cmd_top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed(update):
        return
    await update.message.reply_text(await _query_top(), parse_mode=PM, reply_markup=_main_menu())

async def cmd_agv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed(update):
        return
    if not context.args:
        await update.message.reply_text("Dùng: /agv <tên_AGV>\nVí dụ: /agv AGV001")
        return
    await update.message.reply_text(await _query_agv(context.args[0]), parse_mode=PM, reply_markup=_main_menu())

# ── Xử lý nút bấm ─────────────────────────────────────────────────────────────
async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not _is_allowed(update):
        await query.edit_message_text("⛔ Bạn chưa được cấp quyền.")
        return

    factory = context.user_data.get("factory")
    data = query.data

    if data == "factory_menu":
        await _load_factories()
        if not _factories_cache:
            await query.edit_message_text("Chưa có nhà máy nào trong hệ thống.")
            return
        text = "🏭 Chọn nhà máy cần xem thống kê:"
        await query.edit_message_text(text, reply_markup=_factory_menu())
        return
    elif data.startswith("set_factory:"):
        chosen = data.split(":", 1)[1]
        context.user_data["factory"] = chosen or None
        factory = chosen or None
        label = f"<b>📍 Nhà máy: {e(chosen)}</b>" if chosen else "<b>🌐 Tất cả nhà máy</b>"
        await query.edit_message_text(
            f"{label}\n\nChọn thao tác:",
            parse_mode=PM,
            reply_markup=_main_menu(factory),
        )
        return
    elif data == "status":
        text = await _query_status(factory)
        markup = _main_menu(factory)
    elif data == "stats_today":
        text = await _query_stats("today", factory=factory)
        markup = _main_menu(factory)
    elif data == "stats_week":
        text = await _query_stats("week", factory=factory)
        markup = _main_menu(factory)
    elif data == "stats_month":
        text = await _query_stats("month", factory=factory)
        markup = _main_menu(factory)
    elif data == "top":
        text = await _query_top(factory)
        markup = _main_menu(factory)
    elif data == "uptime_menu":
        text = "⏱ Chọn kỳ xem thời gian hoạt động:"
        markup = _uptime_menu()
    elif data == "uptime_today":
        text = await _query_uptime("today", factory=factory)
        markup = _uptime_menu()
    elif data == "uptime_week":
        text = await _query_uptime("week", factory=factory)
        markup = _uptime_menu()
    elif data == "uptime_month":
        text = await _query_uptime("month", factory=factory)
        markup = _uptime_menu()
    elif data == "uptime_year":
        text = await _query_uptime("year", factory=factory)
        markup = _uptime_menu()
    elif data == "back_menu":
        text = "Chọn thao tác:"
        markup = _main_menu(factory)
    elif data == "ask_date":
        context.user_data["waiting_for_date"] = "stats"
        await query.edit_message_text(
            "📅 Nhập ngày cần xem thống kê:\n\n"
            "Ví dụ:\n• `25/6`\n• `20/06/2026`\n• `hôm qua`\n• `25 tháng 6`",
            parse_mode=PM,
        )
        return
    elif data == "ask_date_uptime":
        context.user_data["waiting_for_date"] = "uptime"
        await query.edit_message_text(
            "📅 Nhập ngày cần xem thời gian hoạt động:\n\n"
            "Ví dụ:\n• `22/6`\n• `18/06/2026`\n• `hôm qua`\n• `22 tháng 6`",
            parse_mode=PM,
        )
        return
    else:
        text = "Không nhận ra thao tác này."
        markup = _main_menu()

    await query.edit_message_text(text, parse_mode=PM, reply_markup=markup)

# ── Nhận dạng ngôn ngữ tự nhiên ───────────────────────────────────────────────
def _detect_intent(text: str):
    """Trả về (intent, arg) từ tin nhắn tiếng Việt tự nhiên.
    arg có thể là: str period | date object | str agv_id
    """
    t = text.lower().strip()

    # Hỏi về AGV cụ thể — ưu tiên kiểm tra trước
    agv_match = re.search(r'\b([a-zA-Z]{1,5}\d{2,6})\b', text)

    if any(k in t for k in ["trạng thái", "online", "offline", "đang chạy", "kết nối", "hoạt động không", "có chạy không"]):
        if agv_match:
            return ("agv", agv_match.group(1))
        return ("status", None)

    if any(k in t for k in ["chi tiết", "thông tin", "lịch sử"]):
        if agv_match:
            return ("agv", agv_match.group(1))

    if agv_match and any(k in t for k in ["agv", "xe", "robot"]):
        return ("agv", agv_match.group(1))

    if any(k in t for k in ["top", "xếp hạng", "nhiều nhất", "ranking", "tốt nhất", "giỏi nhất"]):
        return ("top", None)

    if any(k in t for k in ["thời gian hoạt động", "hoạt động bao lâu", "chạy bao lâu",
                             "tổng thời gian", "uptime", "active time", "làm việc bao lâu"]):
        specific = _parse_date(text)
        if specific:
            return ("single_metric", {"metric": "uptime", "date": specific})
        specific_month = _parse_month(text)
        if specific_month:
            return ("uptime_month", specific_month)
        if any(k in t for k in ["năm", "year"]):
            return ("uptime", "year")
        if any(k in t for k in ["tháng", "month"]):
            return ("uptime", "month")
        if any(k in t for k in ["tuần", "week", "7 ngày"]):
            return ("uptime", "week")
        return ("uptime", "today")

    # Câu hỏi chỉ số đơn lẻ kèm ngày/kỳ
    _metric = None
    if any(k in t for k in ["hủy", "huỷ", "cancel"]):
        _metric = "cancelled"
    elif any(k in t for k in ["hoàn thành", "thành công", "completed", "xong", "done"]):
        _metric = "completed"
    elif any(k in t for k in ["thất bại", "lỗi", "fail", "failed"]):
        _metric = "failed"

    if _metric:
        specific = _parse_date(text)
        if specific:
            return ("single_metric", {"metric": _metric, "date": specific})
        specific_month = _parse_month(text)
        if specific_month:
            return ("single_metric", {"metric": _metric, "month": specific_month})
        if any(k in t for k in ["năm", "year"]):
            return ("single_metric", {"metric": _metric, "period": "year"})
        if any(k in t for k in ["tháng", "month"]):
            return ("single_metric", {"metric": _metric, "period": "month"})
        if any(k in t for k in ["tuần", "week", "7 ngày"]):
            return ("single_metric", {"metric": _metric, "period": "week"})
        return ("single_metric", {"metric": _metric, "period": "today"})

    if any(k in t for k in ["tháng", "month", "30 ngày"]):
        # Kiểm tra NGÀY CỤ THỂ trước — câu kiểu "ngày 6 tháng 8 năm 2026" cũng chứa
        # từ "tháng" nhưng là 1 NGÀY, không phải hỏi cả tháng. Nếu check _parse_month
        # trước (như code cũ), nó khớp nhầm "tháng 8 năm 2026" và ÂM THẦM BỎ MẤT
        # phần "ngày 6", trả về thống kê nguyên cả tháng thay vì đúng 1 ngày.
        specific = _parse_date(text)
        if specific:
            return ("stats_date", specific)
        specific_month = _parse_month(text)
        if specific_month:
            return ("stats_month", specific_month)
        return ("stats", "month")

    if any(k in t for k in ["tuần", "week", "7 ngày", "tuần này", "tuần qua"]):
        return ("stats", "week")

    # Thử parse ngày cụ thể
    specific = _parse_date(text)
    if specific:
        return ("stats_date", specific)

    if any(k in t for k in ["hôm nay", "today", "ngày hôm nay", "task", "chuyến", "lần", "bao nhiêu"]):
        return ("stats", "today")

    if any(k in t for k in ["trạng thái", "status", "tất cả"]):
        return ("status", None)

    if any(k in t for k in ["menu", "giúp", "help", "hướng dẫn", "lệnh"]):
        return ("menu", None)

    return (None, None)

async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed(update):
        await update.message.reply_text(
            f"⛔ Chat ID <code>{update.effective_chat.id}</code> chưa được cấp quyền.",
            parse_mode=PM,
        )
        return

    text = update.message.text or ""
    factory = context.user_data.get("factory")

    # Nhận dạng nhà máy trong câu hỏi — cập nhật context nếu có
    detected_factory = _detect_factory(text)
    if detected_factory:
        context.user_data["factory"] = detected_factory
        factory = detected_factory

    # Đang chờ nhập ngày cụ thể (từ nút bấm)
    waiting = context.user_data.get("waiting_for_date")
    if waiting:
        context.user_data["waiting_for_date"] = None
        parsed = _parse_date(text)
        if parsed:
            if waiting == "uptime":
                reply = await _query_uptime(specific_date=parsed, factory=factory)
                markup = _uptime_menu()
            else:
                reply = await _query_stats(specific_date=parsed, factory=factory)
                markup = _main_menu(factory)
            await update.message.reply_text(reply, parse_mode=PM, reply_markup=markup)
        else:
            await update.message.reply_text(
                "❌ Không nhận ra ngày này.\n\nVui lòng nhập lại, ví dụ:\n"
                "• <code>25/6</code>\n• <code>20/06/2026</code>\n• <code>hôm qua</code>",
                parse_mode=PM,
                reply_markup=_main_menu(factory),
            )
        return

    intent, arg = _detect_intent(text)

    if intent == "status":
        reply = await _query_status(factory)
    elif intent == "stats":
        reply = await _query_stats(arg or "today", factory=factory)
    elif intent == "stats_date":
        reply = await _query_stats(specific_date=arg, factory=factory)
    elif intent == "stats_month":
        reply = await _query_stats(specific_month=arg, factory=factory)
    elif intent == "uptime":
        reply = await _query_uptime(arg or "today", factory=factory)
    elif intent == "uptime_month":
        reply = await _query_uptime(specific_month=arg, factory=factory)
    elif intent == "single_metric":
        metric   = arg.get("metric", "completed")
        sp_date  = arg.get("date")
        sp_month = arg.get("month")
        period   = arg.get("period", "today")
        if sp_date:
            lbl   = sp_date.strftime("ngày %d/%m/%Y")
            where = "queued_at >= $1 AND queued_at < $2"
            params = [
                datetime(sp_date.year, sp_date.month, sp_date.day),
                datetime(sp_date.year, sp_date.month, sp_date.day) + timedelta(days=1),
            ]
        elif sp_month:
            yr, mo = sp_month
            last_day = calendar.monthrange(yr, mo)[1]
            lbl   = f"tháng {mo}/{yr}"
            where = "queued_at >= $1 AND queued_at < $2"
            params = [
                datetime(yr, mo, 1),
                datetime(yr, mo, last_day, 23, 59, 59) + timedelta(seconds=1),
            ]
        elif period == "week":
            lbl, where, params = "7 ngày qua", "queued_at >= NOW() - INTERVAL '7 days'", []
        elif period == "month":
            lbl, where, params = "30 ngày qua", "queued_at >= NOW() - INTERVAL '30 days'", []
        elif period == "year":
            lbl, where, params = f"năm {date.today().year}", f"EXTRACT(YEAR FROM queued_at) = {date.today().year}", []
        else:
            lbl, where, params = "hôm nay", "queued_at >= CURRENT_DATE", []
        reply = await _query_single_metric(metric, lbl, where, params)
    elif intent == "top":
        reply = await _query_top(factory)
    elif intent == "agv":
        reply = await _query_agv(arg)
    elif intent == "menu":
        await update.message.reply_text("Chọn thao tác:", reply_markup=_main_menu(factory))
        return
    else:
        fac_hint = f"\nĐang xem: <b>{e(factory)}</b>" if factory else ""
        await update.message.reply_text(
            "Tôi chưa hiểu câu hỏi này 🤔\n\nBạn có thể hỏi kiểu:\n"
            "• <i>\"nhà máy TNG Việt Đức hôm nay chạy bao nhiêu?\"</i>\n"
            "• <i>\"thống kê tháng 6 nhà máy ABC\"</i>\n"
            "• <i>\"AGV001 đang thế nào?\"</i>\n"
            "• <i>\"tuần này cái nào chạy nhiều nhất?\"</i>"
            f"{fac_hint}\n\nHoặc chọn từ menu bên dưới:",
            parse_mode=PM,
            reply_markup=_main_menu(factory),
        )
        return

    await update.message.reply_text(reply, parse_mode=PM, reply_markup=_main_menu(factory))

# ── Lifecycle ──────────────────────────────────────────────────────────────────
async def start_bot():
    global _application, _loop
    _loop = asyncio.get_running_loop()
    token = get_token()
    if not token:
        print("[TELEGRAM] BOT_TOKEN chưa cấu hình — bỏ qua khởi động bot")
        return

    proxy_url = _load_config().get("proxy_url") or os.getenv("HTTPS_PROXY") or os.getenv("https_proxy")
    builder = (
        Application.builder()
        .token(token)
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .pool_timeout(30)
    )
    if proxy_url:
        builder = builder.proxy(proxy_url)
        print(f"[TELEGRAM] Dùng proxy: {proxy_url}")
    _application = builder.build()

    _application.add_handler(CommandHandler("start",  cmd_start))
    _application.add_handler(CommandHandler("menu",   cmd_menu))
    _application.add_handler(CommandHandler("status", cmd_status))
    _application.add_handler(CommandHandler("stats",  cmd_stats))
    _application.add_handler(CommandHandler("top",    cmd_top))
    _application.add_handler(CommandHandler("agv",    cmd_agv))
    _application.add_handler(CallbackQueryHandler(on_button))
    _application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

    await _application.initialize()
    await _application.start()
    await _application.updater.start_polling(drop_pending_updates=True)
    await _load_factories()
    print("[TELEGRAM] Bot đã khởi động thành công ✓")

async def stop_bot():
    global _application
    if _application:
        try:
            await _application.updater.stop()
            await _application.stop()
            await _application.shutdown()
            print("[TELEGRAM] Bot đã dừng")
        except Exception as e:
            logger.warning(f"[TELEGRAM] stop error: {e}")
        _application = None


# ── Gửi cảnh báo chủ động (MỚI) — dùng cho lỗi móc hàng, v.v. ────────────────
async def send_alert(text: str) -> None:
    """Gửi tin nhắn cảnh báo tới tất cả chat được phép, không cần chờ lệnh /... """
    if _application is None:
        print(f"[TELEGRAM] Bot chưa sẵn sàng — bỏ qua cảnh báo: {text}")
        return
    for chat_id in get_allowed_chats():
        try:
            await _application.bot.send_message(chat_id=chat_id, text=text)
        except Exception as ex:
            print(f"[TELEGRAM] Gửi cảnh báo tới {chat_id} lỗi: {ex}")


def notify_error(text: str) -> None:
    """Gọi được từ code ĐỒNG BỘ (vd MQTT callback thread) — lên lịch gửi an
    toàn qua event loop của bot bằng run_coroutine_threadsafe."""
    if _application is None or _loop is None:
        print(f"[TELEGRAM] Bot chưa sẵn sàng — bỏ qua cảnh báo: {text}")
        return
    try:
        asyncio.run_coroutine_threadsafe(send_alert(text), _loop)
    except Exception as ex:
        print(f"[TELEGRAM] notify_error lỗi: {ex}")
