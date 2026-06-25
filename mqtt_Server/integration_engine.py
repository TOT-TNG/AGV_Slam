"""
integration_engine.py
Quản lý kết nối AGV ↔ hệ thống ngoài (WMS / ERP / MES).
- Inbound : nhận lệnh qua webhook POST /api/webhook/{conn_id}
- Outbound: gửi callback khi task hoàn thành/thất bại
"""
import asyncio
import asyncpg
import httpx
import uuid
import json
import time
from typing import Optional

# ── pool được inject từ main.py khi startup ──────────────────────────────────
_pool: Optional[asyncpg.Pool] = None

def set_pool(p: asyncpg.Pool):
    global _pool
    _pool = p

# ══════════════════════════════════════════════════════════════════════════════
# MIGRATION — tạo bảng nếu chưa có
# ══════════════════════════════════════════════════════════════════════════════

async def ensure_tables():
    if not _pool:
        return
    async with _pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS agv_integrations (
                id               SERIAL PRIMARY KEY,
                conn_id          VARCHAR(36) UNIQUE NOT NULL DEFAULT gen_random_uuid()::text,
                name             VARCHAR(200) NOT NULL,
                system_type      VARCHAR(50)  DEFAULT 'generic',
                direction        VARCHAR(20)  DEFAULT 'both',
                enabled          BOOLEAN      DEFAULT TRUE,

                -- Inbound webhook
                api_key          VARCHAR(128),
                map_id           TEXT,
                default_agv      VARCHAR(50),

                -- Outbound callback
                callback_url     TEXT,
                callback_auth_type  VARCHAR(20)  DEFAULT 'bearer',
                callback_auth_value TEXT,
                callback_events  TEXT         DEFAULT 'completed,failed,cancelled',

                -- Polling (phase 4)
                poll_enabled     BOOLEAN      DEFAULT FALSE,
                poll_url         TEXT,
                poll_interval    INT          DEFAULT 60,
                poll_auth_type   VARCHAR(20)  DEFAULT 'bearer',
                poll_auth_value  TEXT,
                poll_field_map   JSONB        DEFAULT '{}',

                field_map        JSONB        DEFAULT '{}',
                created_at       TIMESTAMPTZ  DEFAULT NOW(),
                updated_at       TIMESTAMPTZ  DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS agv_integration_logs (
                id            SERIAL PRIMARY KEY,
                conn_id       VARCHAR(36),
                direction     VARCHAR(10),
                event         VARCHAR(50),
                status_code   INT,
                request_body  TEXT,
                response_body TEXT,
                error_msg     TEXT,
                created_at    TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        # Index để tìm nhanh theo conn_id + thời gian
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_int_logs_conn_time
            ON agv_integration_logs (conn_id, created_at DESC)
        """)
    print("[INTEGRATION] Tables ready")

# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

async def _log(conn_id: str, direction: str, event: str,
               status_code: int = 0, request_body: str = "",
               response_body: str = "", error_msg: str = ""):
    if not _pool:
        return
    try:
        async with _pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO agv_integration_logs
                   (conn_id, direction, event, status_code, request_body, response_body, error_msg)
                   VALUES ($1,$2,$3,$4,$5,$6,$7)""",
                conn_id, direction, event, status_code,
                request_body[:4000] if request_body else "",
                response_body[:4000] if response_body else "",
                error_msg[:1000] if error_msg else "",
            )
    except Exception as e:
        print(f"[INTEGRATION] log error: {e}")

def _build_auth_headers(auth_type: str, auth_value: str) -> dict:
    if not auth_value:
        return {}
    t = (auth_type or "bearer").lower()
    if t == "bearer":
        return {"Authorization": f"Bearer {auth_value}"}
    if t == "basic":
        import base64 as _b64
        return {"Authorization": "Basic " + _b64.b64encode(auth_value.encode()).decode()}
    if t == "apikey":
        return {"X-API-Key": auth_value}
    return {}

def _apply_field_map(raw: dict, field_map: dict) -> dict:
    """Ánh xạ tên field từ WMS sang field nội bộ AGV."""
    result = dict(raw)
    for agv_field, ext_field in field_map.items():
        if ext_field in raw and agv_field not in raw:
            result[agv_field] = raw[ext_field]
    return result

# ══════════════════════════════════════════════════════════════════════════════
# INBOUND — xử lý webhook từ WMS
# ══════════════════════════════════════════════════════════════════════════════

async def handle_webhook(conn_id: str, api_key: str, body: dict) -> dict:
    """Được gọi từ endpoint POST /api/webhook/{conn_id}."""
    if not _pool:
        raise ValueError("Database chưa sẵn sàng")

    # Lấy config kết nối
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM agv_integrations WHERE conn_id=$1 AND enabled=TRUE", conn_id
        )
    if not row:
        await _log(conn_id, "in", "webhook_rejected", 404,
                   json.dumps(body), "", "conn_id không tồn tại hoặc đã tắt")
        raise ValueError(f"Kết nối '{conn_id}' không tồn tại hoặc đã bị tắt")

    # Kiểm tra API key
    if row["api_key"] and row["api_key"] != api_key:
        await _log(conn_id, "in", "webhook_rejected", 401,
                   json.dumps(body), "", "API key không hợp lệ")
        raise PermissionError("API key không hợp lệ")

    direction = row["direction"] or "both"
    if direction == "outbound":
        raise ValueError("Kết nối này chỉ hỗ trợ outbound")

    # Ánh xạ field
    field_map = dict(row["field_map"] or {})
    data = _apply_field_map(body, field_map)

    agv_id      = str(data.get("agv_id")      or row["default_agv"] or "").strip()
    destination = str(data.get("destination") or "").strip()
    map_id      = str(data.get("map_id")      or row["map_id"] or "").strip() or None
    notes       = str(data.get("notes")       or "").strip()
    ext_order   = str(data.get("external_order_id") or "").strip()
    op_name     = str(data.get("operator_name") or "").strip() or None
    op_id       = str(data.get("operator_id")   or "").strip() or None

    # Thông tin đơn hàng: ưu tiên key "order_info" (nested dict),
    # nếu không có thì gom tất cả field không thuộc chuẩn AGV vào order_info.
    _STANDARD = {"agv_id", "destination", "map_id", "notes",
                 "external_order_id", "operator_name", "operator_id", "order_info"}
    raw_oi = data.get("order_info")
    if not isinstance(raw_oi, dict) or not raw_oi:
        raw_oi = {k: v for k, v in data.items() if k not in _STANDARD}
    order_info = json.dumps(raw_oi, ensure_ascii=False) if raw_oi else None

    if not destination:
        await _log(conn_id, "in", "webhook_error", 400,
                   json.dumps(body), "", "Thiếu destination")
        raise ValueError("Thiếu trường 'destination'")

    # Tạo task trong DB
    task_id = str(uuid.uuid4())
    full_notes = f"[{row['name']}]{' ext:'+ext_order if ext_order else ''} {notes}".strip()

    async with _pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO agv_tasks
               (task_id, agv_id, destination, map_id, status, notes, operator_name, operator_id, order_info)
               VALUES ($1,$2,$3,$4,'pending',$5,$6,$7,$8::jsonb)""",
            task_id, agv_id or None, destination, map_id, full_notes, op_name, op_id, order_info,
        )

    await _log(conn_id, "in", "webhook_received", 200,
               json.dumps(body),
               json.dumps({"task_id": task_id, "agv_id": agv_id, "destination": destination}))

    print(f"[INTEGRATION] Webhook '{row['name']}' → task={task_id} agv={agv_id} dest={destination}")
    return {
        "task_id": task_id,
        "agv_id":  agv_id or None,
        "destination": destination,
        "status":  "pending",
        "external_order_id": ext_order or None,
    }

# ══════════════════════════════════════════════════════════════════════════════
# OUTBOUND — gửi callback khi task thay đổi trạng thái
# ══════════════════════════════════════════════════════════════════════════════

async def fire_callbacks(task_id: str, event: str, task_row: dict):
    """
    Gọi tất cả callback outbound phù hợp với event (completed/failed/cancelled).
    task_row: dict từ agv_tasks (agv_id, destination, map_id, operator_name, …)
    """
    if not _pool:
        return
    try:
        async with _pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT * FROM agv_integrations
                   WHERE enabled=TRUE AND direction IN ('outbound','both')
                   AND map_id IS NOT DISTINCT FROM $1""",
                task_row.get("map_id"),
            )
        # Nếu không có row theo map_id, lấy tất cả (wildcard)
        if not rows:
            async with _pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT * FROM agv_integrations WHERE enabled=TRUE AND direction IN ('outbound','both')"
                )
    except Exception as e:
        print(f"[INTEGRATION] fire_callbacks DB error: {e}")
        return

    for row in rows:
        events_cfg = (row["callback_events"] or "completed,failed").split(",")
        events_cfg = [e.strip() for e in events_cfg]
        if event not in events_cfg:
            continue
        if not row["callback_url"]:
            continue
        asyncio.create_task(
            _send_callback_with_retry(row, task_id, event, task_row)
        )

async def _send_callback_with_retry(row, task_id: str, event: str, task_row: dict,
                                     max_retries: int = 3):
    conn_id = row["conn_id"]
    # Giải mã order_info nếu là chuỗi JSON
    _oi_raw = task_row.get("order_info")
    try:
        order_info_obj = json.loads(_oi_raw) if isinstance(_oi_raw, str) else _oi_raw
    except Exception:
        order_info_obj = None

    payload = {
        "event":          event,
        "task_id":        task_id,
        "agv_id":         task_row.get("agv_id"),
        "destination":    task_row.get("destination"),
        "map_id":         task_row.get("map_id"),
        "status":         task_row.get("status"),
        "operator_name":  task_row.get("operator_name"),
        "operator_id":    task_row.get("operator_id"),
        "notes":          task_row.get("notes"),
        "order_info":     order_info_obj,
        "timestamp":      time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    headers = {
        "Content-Type": "application/json",
        **_build_auth_headers(row["callback_auth_type"] or "bearer",
                              row["callback_auth_value"] or ""),
    }
    body_str = json.dumps(payload)

    for attempt in range(1, max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(row["callback_url"], content=body_str, headers=headers)
            await _log(conn_id, "out", event, resp.status_code,
                       body_str, resp.text[:2000])
            if resp.status_code < 300:
                print(f"[INTEGRATION] Callback '{row['name']}' event={event} → {resp.status_code}")
                return
            print(f"[INTEGRATION] Callback '{row['name']}' attempt {attempt} → HTTP {resp.status_code}")
        except Exception as e:
            await _log(conn_id, "out", event, 0, body_str, "", str(e))
            print(f"[INTEGRATION] Callback '{row['name']}' attempt {attempt} error: {e}")

        if attempt < max_retries:
            await asyncio.sleep(5 * attempt)  # backoff: 5s, 10s

    print(f"[INTEGRATION] Callback '{row['name']}' event={event} — thất bại sau {max_retries} lần")

# ══════════════════════════════════════════════════════════════════════════════
# CRUD helpers — dùng từ API endpoints trong main.py
# ══════════════════════════════════════════════════════════════════════════════

async def list_integrations() -> list:
    if not _pool:
        return []
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM agv_integrations ORDER BY created_at DESC"
        )
    result = []
    for r in rows:
        d = dict(r)
        # Ẩn giá trị nhạy cảm — chỉ trả về dấu hiệu có hay không
        d["api_key"]             = "***" if d.get("api_key")             else ""
        d["callback_auth_value"] = "***" if d.get("callback_auth_value") else ""
        d["poll_auth_value"]     = "***" if d.get("poll_auth_value")     else ""
        d["created_at"] = d["created_at"].isoformat() if d.get("created_at") else None
        d["updated_at"] = d["updated_at"].isoformat() if d.get("updated_at") else None
        result.append(d)
    return result

async def get_integration(conn_id: str) -> Optional[dict]:
    if not _pool:
        return None
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM agv_integrations WHERE conn_id=$1", conn_id
        )
    if not row:
        return None
    d = dict(row)
    d["created_at"] = d["created_at"].isoformat() if d.get("created_at") else None
    d["updated_at"] = d["updated_at"].isoformat() if d.get("updated_at") else None
    return d

async def create_integration(data: dict) -> dict:
    if not _pool:
        raise RuntimeError("DB chưa sẵn sàng")
    # Tạo API key tự động nếu là inbound và chưa có
    direction = data.get("direction", "both")
    api_key = data.get("api_key") or (
        str(uuid.uuid4()).replace("-", "") if direction in ("inbound", "both") else None
    )
    # Dùng conn_id client gửi lên nếu có (để webhook URL biết trước khi lưu)
    conn_id = str(data.get("conn_id") or uuid.uuid4())
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO agv_integrations
               (conn_id, name, system_type, direction, enabled,
                api_key, map_id, default_agv,
                callback_url, callback_auth_type, callback_auth_value, callback_events,
                field_map)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
               RETURNING *""",
            conn_id,
            data.get("name", "Kết nối mới"),
            data.get("system_type", "generic"),
            direction,
            bool(data.get("enabled", True)),
            api_key,
            data.get("map_id") or None,
            data.get("default_agv") or None,
            data.get("callback_url") or None,
            data.get("callback_auth_type", "bearer"),
            data.get("callback_auth_value") or None,
            data.get("callback_events", "completed,failed,cancelled"),
            json.dumps(data.get("field_map") or {}),
        )
    d = dict(row)
    d["created_at"] = d["created_at"].isoformat() if d.get("created_at") else None
    d["updated_at"] = d["updated_at"].isoformat() if d.get("updated_at") else None
    print(f"[INTEGRATION] Created: '{d['name']}' conn_id={conn_id}")
    return d

async def update_integration(conn_id: str, data: dict) -> Optional[dict]:
    if not _pool:
        return None
    # Nếu giá trị nhạy cảm là "***" → không cập nhật
    fields, vals = [], []
    idx = 1
    for col in ("name", "system_type", "direction", "enabled",
                "map_id", "default_agv",
                "callback_url", "callback_auth_type", "callback_events",
                "field_map"):
        if col in data:
            fields.append(f"{col}=${idx}"); vals.append(data[col]); idx += 1
    for col in ("api_key", "callback_auth_value"):
        if col in data and data[col] and data[col] != "***":
            fields.append(f"{col}=${idx}"); vals.append(data[col]); idx += 1
    if not fields:
        return await get_integration(conn_id)
    fields.append(f"updated_at=NOW()")
    vals.append(conn_id)
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            f"UPDATE agv_integrations SET {', '.join(fields)} WHERE conn_id=${idx} RETURNING *",
            *vals,
        )
    if not row:
        return None
    d = dict(row)
    d["created_at"] = d["created_at"].isoformat() if d.get("created_at") else None
    d["updated_at"] = d["updated_at"].isoformat() if d.get("updated_at") else None
    return d

async def delete_integration(conn_id: str) -> bool:
    if not _pool:
        return False
    async with _pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM agv_integrations WHERE conn_id=$1", conn_id
        )
    return result == "DELETE 1"

async def get_logs(conn_id: str, limit: int = 100) -> list:
    if not _pool:
        return []
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT * FROM agv_integration_logs
               WHERE conn_id=$1 ORDER BY created_at DESC LIMIT $2""",
            conn_id, limit,
        )
    result = []
    for r in rows:
        d = dict(r)
        d["created_at"] = d["created_at"].isoformat() if d.get("created_at") else None
        result.append(d)
    return result

async def test_callback(conn_id: str) -> dict:
    """Gửi payload test đến callback URL."""
    row = await get_integration(conn_id)
    if not row:
        return {"ok": False, "error": "Không tìm thấy kết nối"}
    if not row.get("callback_url"):
        return {"ok": False, "error": "Chưa có callback URL"}
    payload = {
        "event":       "test",
        "task_id":     "test-" + str(uuid.uuid4())[:8],
        "agv_id":      "AGV01",
        "destination": "99",
        "status":      "completed",
        "timestamp":   time.strftime("%Y-%m-%dT%H:%M:%S"),
        "message":     f"Test từ AGV server — kết nối '{row['name']}'",
    }
    # Lấy auth value thực từ DB (không phải ***)
    async with _pool.acquire() as conn:
        real = await conn.fetchrow(
            "SELECT callback_auth_type, callback_auth_value FROM agv_integrations WHERE conn_id=$1",
            conn_id,
        )
    headers = {
        "Content-Type": "application/json",
        **_build_auth_headers(real["callback_auth_type"] or "bearer",
                              real["callback_auth_value"] or ""),
    }
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.post(
                row["callback_url"],
                content=json.dumps(payload),
                headers=headers,
            )
        await _log(conn_id, "out", "test", resp.status_code,
                   json.dumps(payload), resp.text[:500])
        return {"ok": resp.status_code < 300, "status_code": resp.status_code,
                "response": resp.text[:300]}
    except Exception as e:
        await _log(conn_id, "out", "test", 0, json.dumps(payload), "", str(e))
        return {"ok": False, "error": str(e)}
