"""
task_queue.py — Hàng chờ lệnh per-AGV
---------------------------------------
Mỗi AGV có 1 hàng chờ (deque). Khi AGV đang bận, lệnh mới được xếp vào hàng
chờ. Khi AGV hoàn thành lệnh hiện tại, lệnh tiếp theo tự động được dispatch.

Persistence: ghi vào bảng agv_task_executions trong PostgreSQL.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Optional, Callable

# ── Kiểu lệnh ─────────────────────────────────────────────────────────────────
CMD_GO_TO     = "go_to"
CMD_GO_CHARGE = "go_charge"
CMD_GO_WAIT   = "go_wait"
CMD_STOP      = "stop"
CMD_RESUME    = "resume"
# Lệnh thang máy (xem floor_nav.py / elevator_coordinator.py): dest_node mang tham số dạng chuỗi
from floor_nav import CMD_ELEV_BOOK, CMD_ELEV_CALL, CMD_ELEV_RIDE, CMD_ELEV_RELEASE

CMD_LABELS = {
    CMD_GO_TO:     "Đi đến điểm",
    CMD_GO_CHARGE: "Đi sạc pin",
    CMD_GO_WAIT:   "Về khu chờ",
    CMD_STOP:      "Dừng khẩn cấp",
    CMD_RESUME:    "Tiếp tục",
    CMD_ELEV_BOOK:    "Đặt thang máy",
    CMD_ELEV_CALL:    "Gọi thang máy",
    CMD_ELEV_RIDE:    "Đi thang máy",
    CMD_ELEV_RELEASE: "Ra khỏi thang",
}

STATUS_QUEUED    = "queued"
STATUS_RUNNING   = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED    = "failed"
STATUS_CANCELLED = "cancelled"
# Dispatch lỗi TỰ ĐỘNG (mất kết nối MQTT, không lập được lộ trình...) — KHÔNG
# dùng STATUS_FAILED nữa. Theo yêu cầu: "Thất bại"/"Hủy" trong thống kê chỉ được
# tính khi có người CHỦ ĐỘNG bấm Hủy — dispatch lỗi tự động vẫn giải phóng xe
# ngay (không kẹt xe) nhưng không được tính vào thống kê Thất bại/Hủy.
STATUS_ERROR     = "error"


@dataclass
class QueuedCommand:
    cmd_id:        str
    agv_id:        str
    command:       str
    dest_node:     Optional[str]
    start_node:    Optional[str] = None   # vị trí xuất phát thủ công (Line AGV)
    queued_at:     float = field(default_factory=time.time)
    started_at:    Optional[float] = None
    completed_at:  Optional[float] = None
    status:        str = STATUS_QUEUED
    notes:         str = ""
    session_id:    Optional[str] = None   # nhóm các bước của cùng 1 lượt workflow
    session_label: Optional[str] = None   # tên workflow / nhãn hiển thị
    chain_leg:     bool = False           # go_to TRUNG GIAN của chuỗi đi thang (không phải đích thật của lượt)
    seq:           float = 0.0            # thứ tự trong hàng đợi (nhỏ = chạy trước) — lưu DB để khôi phục đúng thứ tự khi server khởi động lại

    def to_dict(self) -> dict:
        return {
            "cmd_id":        self.cmd_id,
            "agv_id":        self.agv_id,
            "command":       self.command,
            "command_label": CMD_LABELS.get(self.command, self.command),
            "dest_node":     self.dest_node,
            "queued_at":     self.queued_at,
            "started_at":    self.started_at,
            "completed_at":  self.completed_at,
            "status":        self.status,
            "notes":         self.notes,
            "session_id":    self.session_id,
            "session_label": self.session_label,
            "chain_leg":     self.chain_leg,
        }


class AGVTaskQueue:
    """
    Hàng chờ lệnh per-AGV với DB persistence.

    Flow khi AGV bận:
      dispatch_or_queue() → enqueue → popup "Đã xếp hàng chờ"
    Flow khi AGV hoàn thành:
      on_agv_completed()  → complete_current → start_next → dispatch
    """

    def __init__(self):
        self._queues:  dict[str, deque[QueuedCommand]] = {}
        self._running: dict[str, Optional[QueuedCommand]] = {}
        self._pool = None
        self._loop = None   # event loop reference — set khi set_pool gọi từ lifespan
        # Callback dispatch thực tế: dispatch_fn(QueuedCommand) -> bool
        self.dispatch_fn: Optional[Callable] = None
        # Pickup tracking per session (lượt cấp hàng): {session_key: {supply_node,...}}
        # Một supply node chỉ lấy hàng MỘT lần mỗi lượt; các lệnh giao hàng sau trong
        # cùng session sẽ không dừng lại tại supply node đã lấy (đi một mạch qua).
        self._session_pickups: dict[str, set[str]] = {}
        # AGV có hàng đợi vừa KHÔI PHỤC từ DB sau khi server khởi động lại, chờ xe sẵn sàng (online, đứng yên, biết vị trí)
        # rồi mới chạy lệnh đầu (xem restore_from_rows / pop_restored).
        self._restore_pending: set[str] = set()
        # Chuẩn bị lệnh đầu của hàng đợi vừa khôi phục TRƯỚC khi chạy (nạp bản đồ, nhận lại chuyến thang, gọi lại thang...). Gắn bởi
        # main.py. Mọi đường kích hàng đợi — người vận hành xác nhận trên web, bấm xác nhận/tiếp tục trực tiếp trên xe (HMI),
        # hay tự động khi xe sẵn sàng — đều đi qua on_agv_completed nên cùng chạy hàm này: kết quả y hệt nhau.
        # fn(agv_id) -> False = giữ hàng đợi, chưa chạy.
        self.restore_prepare_fn: Optional[Callable] = None

    def set_pool(self, pool) -> None:
        self._pool = pool
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None

    def _schedule_db(self, coro) -> None:
        """Schedule DB coroutine từ bất kỳ context nào (event loop hoặc thread pool)."""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(coro)
        except RuntimeError:
            if self._loop and self._loop.is_running():
                asyncio.run_coroutine_threadsafe(coro, self._loop)

    # ── Thứ tự hàng đợi (lưu DB) ───────────────────────────────────────────────

    def _tail_seq(self, agv_id: str) -> float:
        q = self._queues.get(agv_id)
        now = time.time()
        return max(now, q[-1].seq + 1e-3) if q else now

    def _head_seq(self, agv_id: str) -> float:
        q = self._queues.get(agv_id)
        return (q[0].seq - 1.0) if q else time.time()

    def mark_chain_leg(self, cmd: "QueuedCommand", flag: bool) -> None:
        """Đặt cờ chain_leg SAU khi tạo lệnh và lưu DB (bản ghi đã được chèn trước đó)."""
        if cmd.chain_leg != bool(flag):
            cmd.chain_leg = bool(flag)
            self._db_set_chain_leg(cmd)

    # ── Public API ─────────────────────────────────────────────────────────────

    def is_busy(self, agv_id: str) -> bool:
        return bool(self._running.get(agv_id))

    # ── Session pickup tracking ──────────────────────────────────────────────
    @staticmethod
    def _session_key(session_id: Optional[str]) -> str:
        return session_id or "__none__"

    def mark_session_pickup(self, session_id: Optional[str], node) -> None:
        """Đánh dấu supply node đã (hoặc sẽ) lấy hàng trong session này."""
        if node is None:
            return
        key = self._session_key(session_id)
        bucket = self._session_pickups.setdefault(key, set())
        if str(node) not in bucket:
            bucket.add(str(node))
            from persistent_flags import flag_store
            flag_store.add("session_pickup", key, str(node))      # sống sót qua server khởi động lại

    def restore_session_pickups(self, rows) -> None:
        """Nạp lại từ DB: rows = [(session_key, node)]."""
        for key, node in rows:
            self._session_pickups.setdefault(str(key), set()).add(str(node))

    def session_has_pickup(self, session_id: Optional[str], node) -> bool:
        """True nếu supply node đã được lấy hàng trong session này → không dừng lại nữa."""
        if node is None:
            return False
        return str(node) in self._session_pickups.get(self._session_key(session_id), ())

    def current_session(self, agv_id: str) -> Optional[str]:
        """session_id của lệnh đang chạy trên AGV (None nếu không có)."""
        running = self._running.get(agv_id)
        return running.session_id if running else None

    def session_queued_dests(self, agv_id: str, session_id: Optional[str],
                             command: str) -> list[str]:
        """dest_node của các lệnh `command` đang CHỜ trong queue thuộc cùng session.

        Dùng để gom pickup cả lượt: khi giao 1 tổ, biết các tổ còn lại đang chờ
        để đi lấy hàng tại tất cả điểm cấp TRƯỚC khi giao.
        """
        out: list[str] = []
        for c in self._queues.get(agv_id, deque()):
            if c.command == command and c.dest_node and c.session_id == session_id:
                out.append(str(c.dest_node))
        return out

    def _clear_session_pickups(self, session_id: Optional[str]) -> None:
        key = self._session_key(session_id)
        if self._session_pickups.pop(key, None) is not None:
            from persistent_flags import flag_store
            flag_store.remove_group("session_pickup", key)

    def dispatch_or_queue(
        self,
        agv_id:        str,
        command:       str,
        dest_node:     Optional[str] = None,
        start_node:    Optional[str] = None,
        session_id:    Optional[str] = None,
        session_label: Optional[str] = None,
    ) -> tuple[QueuedCommand, bool]:
        """
        AGV rảnh → dispatch ngay, trả về (cmd, True)
        AGV bận  → enqueue,       trả về (cmd, False)
        """
        if not self.is_busy(agv_id):
            cmd = QueuedCommand(
                cmd_id=str(uuid.uuid4())[:8],
                agv_id=agv_id,
                command=command,
                dest_node=dest_node,
                start_node=start_node,
                status=STATUS_RUNNING,
                started_at=time.time(),
                session_id=session_id,
                session_label=session_label,
                seq=time.time(),
            )
            self._running[agv_id] = cmd
            self._db_insert(cmd)
            ok = self._do_dispatch(cmd)
            if not ok:
                cmd.status       = STATUS_ERROR
                cmd.completed_at = time.time()
                if not cmd.notes:
                    cmd.notes = "dispatch failed"
                self._running[agv_id] = None
                self._db_update(cmd)
            return cmd, ok
        else:
            cmd = QueuedCommand(
                cmd_id=str(uuid.uuid4())[:8],
                agv_id=agv_id,
                command=command,
                dest_node=dest_node,
                start_node=start_node,
                status=STATUS_QUEUED,
                session_id=session_id,
                session_label=session_label,
                seq=self._tail_seq(agv_id),
            )
            self._queues.setdefault(agv_id, deque()).append(cmd)
            self._db_insert(cmd)
            print(f"[QUEUE] {agv_id}: enqueued '{command}' dest={dest_node} id={cmd.cmd_id}")
            return cmd, False

    def on_agv_completed(self, agv_id: str, notes: str = "",
                         auto_dispatch: bool = True) -> None:
        """Gọi khi AGV hoàn thành lệnh. Tự dispatch lệnh tiếp theo nếu có.

        auto_dispatch=False: chỉ HOÀN THÀNH lệnh hiện tại + GIẢI PHÓNG xe, KHÔNG pop
        lệnh kế. Dùng cho 'đứng yên chờ retry' (dest bị chiếm) — để xe rảnh cho
        pending_retry dispatch LẠI go_to khi đích trống, mà KHÔNG chạy nhầm go_charge
        đứng sau trong hàng đợi (gây bỏ giao hàng đi sạc).
        """
        if agv_id in self._restore_pending and not self._running.get(agv_id):
            self._restore_pending.discard(agv_id)
            if auto_dispatch and self.restore_prepare_fn is not None:
                try:
                    if self.restore_prepare_fn(agv_id) is False:
                        return           # chưa chạy được (vd xe trong cabin mà thang chưa nhận lại) — giữ nguyên hàng đợi
                except Exception as e:
                    print(f"[QUEUE] {agv_id}: chuẩn bị lệnh đầu hàng đợi khôi phục lỗi: {type(e).__name__}: {e}")

        running = self._running.get(agv_id)
        if running:
            running.status        = STATUS_COMPLETED
            running.completed_at  = time.time()
            running.notes         = notes
            self._running[agv_id] = None   # ← Giải phóng AGV NGAY
            self._db_update(running)
            print(f"[QUEUE] {agv_id}: completed cmd={running.cmd_id}"
                  f"{' (giữ hàng đợi, chờ retry)' if not auto_dispatch else ''}")

        if not auto_dispatch:
            return   # giải phóng xe nhưng KHÔNG chạy lệnh kế (go_charge vẫn chờ)

        q = self._queues.get(agv_id)
        if not q:
            # Hàng đợi rỗng → lượt cấp hàng (session) kết thúc → dọn pickup tracking
            if running:
                self._clear_session_pickups(running.session_id)
            return

        next_cmd            = q.popleft()
        next_cmd.status     = STATUS_RUNNING
        next_cmd.started_at = time.time()
        self._running[agv_id] = next_cmd
        self._db_update(next_cmd)
        print(f"[QUEUE] {agv_id}: auto-dispatch next cmd={next_cmd.cmd_id}")

        # Dispatch bất đồng bộ để không block MQTT callback thread
        # và để frontend thấy trạng thái "rảnh" trước khi lệnh mới bắt đầu
        if self._loop and self._loop.is_running():
            async def _run_next():
                ok = await asyncio.to_thread(self._do_dispatch, next_cmd)
                if not ok:
                    next_cmd.status       = STATUS_ERROR
                    next_cmd.completed_at = time.time()
                    if not next_cmd.notes:
                        next_cmd.notes = "auto-dispatch failed"
                    self._running[agv_id] = None
                    self._db_update(next_cmd)
                    print(f"[QUEUE] {agv_id}: auto-dispatch cmd={next_cmd.cmd_id} FAILED")
                else:
                    print(f"[QUEUE] {agv_id}: auto-dispatch cmd={next_cmd.cmd_id} OK")
            asyncio.run_coroutine_threadsafe(_run_next(), self._loop)
        else:
            # Fallback: đồng bộ (tránh mất lệnh nếu loop chưa sẵn sàng)
            ok = self._do_dispatch(next_cmd)
            if not ok:
                next_cmd.status       = STATUS_ERROR
                next_cmd.completed_at = time.time()
                next_cmd.notes        = "auto-dispatch failed"
                self._running[agv_id] = None
                self._db_update(next_cmd)

    def insert_next(
        self,
        agv_id:    str,
        command:   str,
        dest_node: Optional[str] = None,
    ) -> QueuedCommand:
        """
        Chèn lệnh vào ĐẦU hàng chờ — sẽ chạy ngay sau lệnh hiện tại.
        Dùng khi split route tại intermediate arrival_action node.
        Kế thừa session_id từ lệnh đang chạy để không bị tách nhóm.
        """
        running = self._running.get(agv_id)
        cmd = QueuedCommand(
            cmd_id=str(uuid.uuid4())[:8],
            agv_id=agv_id,
            command=command,
            dest_node=dest_node,
            status=STATUS_QUEUED,
            session_id=running.session_id if running else None,
            session_label=running.session_label if running else None,
            chain_leg=bool(running and running.chain_leg and command == "go_to"),
            seq=self._head_seq(agv_id),
        )
        self._queues.setdefault(agv_id, deque()).appendleft(cmd)
        self._db_insert(cmd)
        print(f"[QUEUE] {agv_id}: insert_next '{command}' dest={dest_node} id={cmd.cmd_id}")
        return cmd

    def cancel_running(self, agv_id: str) -> Optional[dict]:
        """Force-cancel lệnh đang chạy (bị stuck), giải phóng AGV để dispatch lệnh tiếp."""
        cmd = self._running.get(agv_id)
        if not cmd:
            return None
        cmd.status       = STATUS_CANCELLED
        cmd.completed_at = time.time()
        cmd.notes        = "force-cancelled by user"
        self._running[agv_id] = None
        self._db_update(cmd)
        print(f"[QUEUE] {agv_id}: force-cancelled running cmd={cmd.cmd_id}")
        if cmd.command in ("go_charge", "go_wait"):
            try:
                from mqtt_client import release_station
                release_station(agv_id, reason="cancel_running")
            except Exception:
                pass
        return cmd.to_dict()

    def cancel_cmd(self, cmd_id: str) -> bool:
        """Hủy 1 lệnh cụ thể trong queue (chưa chạy)."""
        for agv_id, q in self._queues.items():
            for i, cmd in enumerate(list(q)):
                if cmd.cmd_id == cmd_id:
                    q.remove(cmd)
                    cmd.status       = STATUS_CANCELLED
                    cmd.completed_at = time.time()
                    cmd.notes        = "cancelled by user"
                    self._db_update(cmd)
                    print(f"[QUEUE] {agv_id}: cancelled queued cmd={cmd_id}")
                    return True
        return False

    def cancel_queue(self, agv_id: str) -> int:
        """Hủy toàn bộ lệnh đang chờ (chưa chạy) của 1 AGV."""
        q     = self._queues.pop(agv_id, deque())
        count = len(q)
        now   = time.time()
        for cmd in q:
            cmd.status       = STATUS_CANCELLED
            cmd.completed_at = now
            cmd.notes        = "cancelled by user"
            self._db_update(cmd)
        if count:
            print(f"[QUEUE] {agv_id}: cancelled {count} queued command(s)")
        return count

    def cancel_all(self, agv_id: str) -> dict:
        """Hủy lệnh đang chạy + toàn bộ hàng chờ. Dùng khi AGV bị stuck."""
        running  = self.cancel_running(agv_id)
        queued_n = self.cancel_queue(agv_id)
        # Dấu "staging transit" còn sót của xe này (đặt lúc off_route/split nhưng lệnh re-queue
        # đã bị huỷ) PHẢI xoá — nếu không lệnh go_to KẾ TIẾP tới đúng node đó bị coi là transit:
        # tới điểm lấy hàng không chờ xác nhận mà tự đi tiếp (log 2026-11-11 13:39, AGV02 node 98).
        try:
            from main import _pending_staging_transits as _pst_ca
            for _k in [k for k in _pst_ca if k[0] == agv_id]:
                _pst_ca.discard(_k)
        except Exception:
            pass
        return {"cancelled_running": running, "cancelled_queued": queued_n}

    # ── Khôi phục hàng đợi sau khi server khởi động lại ─────────────────────────

    def restore_from_rows(self, rows: list) -> dict:
        """Dựng lại hàng đợi từ các dòng DB còn 'running'/'queued' của lần chạy trước (rows đã sắp: lệnh đang chạy dở trước,
        rồi theo seq). Mọi lệnh khôi phục về trạng thái 'queued' — lệnh đang chạy dở sẽ được dispatch LẠI từ vị trí thật của xe
        khi xe sẵn sàng. Trả {agv_id: số lệnh}."""
        per: dict = {}
        was_running: set = set()
        for r in rows:
            cmd = QueuedCommand(
                cmd_id=str(r["cmd_id"]), agv_id=str(r["agv_id"]), command=str(r["command"]),
                dest_node=(str(r["dest_node"]) if r.get("dest_node") not in (None, "") else None),
                start_node=(str(r["start_node"]) if r.get("start_node") else None),
                queued_at=float(r.get("queued_at") or time.time()),
                status=STATUS_QUEUED,
                notes="restored",
                session_id=r.get("session_id"), session_label=r.get("session_label"),
                chain_leg=bool(r.get("chain_leg")),
                seq=float(r["seq"]) if r.get("seq") is not None else float(r.get("queued_at") or time.time()),
            )
            per.setdefault(cmd.agv_id, []).append(cmd)
            if str(r.get("status")) == STATUS_RUNNING:
                was_running.add(cmd.cmd_id)
        out: dict = {}
        for agv_id, cmds in per.items():
            if self._running.get(agv_id) or self._queues.get(agv_id):
                continue        # xe đã có lệnh mới trong RAM (restore chạy trễ) — không đè
            self._queues[agv_id] = deque(cmds)
            self._restore_pending.add(agv_id)
            out[agv_id] = len(cmds)
            for c in cmds:
                if c.cmd_id in was_running:
                    self._db_update(c)      # DB: lệnh đang chạy dở quay về 'queued' (sẽ dispatch lại)
        return out

    def restore_pending(self) -> list:
        return sorted(self._restore_pending)

    def pop_restored(self, agv_id: str) -> bool:
        """Bỏ AGV khỏi danh sách chờ khôi phục. True nếu trước đó đang chờ."""
        had = agv_id in self._restore_pending
        self._restore_pending.discard(agv_id)
        return had

    def heading_to_special(self, agv_id: str) -> bool:
        """True nếu lệnh đang chạy là go_charge/go_wait, hoặc là chặng go_to TRUNG GIAN của một chuỗi (đi thang...) mà đích cuối
        là go_charge/go_wait. Với các lượt này xe CHỈ ĐI QUA các node lấy/thả hàng, không dừng lấy hàng (xem _dispatch_go_to)."""
        run = self._running.get(agv_id)
        if run is None:
            return False
        if run.command in (CMD_GO_CHARGE, CMD_GO_WAIT):
            return True
        if run.command != CMD_GO_TO or not run.chain_leg:
            return False
        for c in self._queues.get(agv_id, ()):
            if c.command in (CMD_GO_CHARGE, CMD_GO_WAIT):
                return True
            if c.command == CMD_GO_TO and not c.chain_leg:
                return False
        return False

    def peek_head(self, agv_id: str):
        q = self._queues.get(agv_id)
        return q[0] if q else None

    def get_queue(self, agv_id: str) -> list[dict]:
        return [c.to_dict() for c in self._queues.get(agv_id, [])]

    def get_running(self, agv_id: str) -> Optional[dict]:
        c = self._running.get(agv_id)
        return c.to_dict() if c else None

    def queue_size(self, agv_id: str) -> int:
        return len(self._queues.get(agv_id, []))

    def status_summary(self, agv_id: str) -> dict:
        return {
            "running":    self.get_running(agv_id),
            "queue":      self.get_queue(agv_id),
            "queue_size": self.queue_size(agv_id),
        }

    def get_history(self, agv_id: Optional[str] = None, limit: int = 50) -> list[dict]:
        """Lấy lịch sử từ DB (sync, dùng psycopg2)."""
        try:
            import psycopg2, os
            conn = psycopg2.connect(os.getenv(
                "DATABASE_URL",
                "postgresql://postgres:ducmanh1801@localhost:5432/TOT_AGV",
            ))
            cur = conn.cursor()
            if agv_id:
                cur.execute(
                    "SELECT cmd_id,agv_id,command,dest_node,status,"
                    "EXTRACT(EPOCH FROM queued_at),"
                    "EXTRACT(EPOCH FROM started_at),"
                    "EXTRACT(EPOCH FROM completed_at),notes "
                    "FROM agv_task_executions WHERE agv_id=%s "
                    "ORDER BY queued_at DESC LIMIT %s",
                    (agv_id, limit),
                )
            else:
                cur.execute(
                    "SELECT cmd_id,agv_id,command,dest_node,status,"
                    "EXTRACT(EPOCH FROM queued_at),"
                    "EXTRACT(EPOCH FROM started_at),"
                    "EXTRACT(EPOCH FROM completed_at),notes "
                    "FROM agv_task_executions "
                    "ORDER BY queued_at DESC LIMIT %s",
                    (limit,),
                )
            rows = cur.fetchall()
            conn.close()
            return [
                {
                    "cmd_id":        r[0], "agv_id": r[1],
                    "command":       r[2],
                    "command_label": CMD_LABELS.get(r[2], r[2]),
                    "dest_node":     r[3], "status": r[4],
                    "queued_at":     r[5], "started_at": r[6],
                    "completed_at":  r[7], "notes": r[8] or "",
                }
                for r in rows
            ]
        except Exception as e:
            print(f"[QUEUE] get_history error: {e}")
            return []

    def get_mission_history(self, agv_id: Optional[str] = None, limit: int = 200) -> list[dict]:
        """
        Lịch sử theo mission:
        - Có session_id  → GROUP BY session_id (chính xác, dữ liệu mới)
        - Không session_id → gom theo thời gian (gap > 30s = session mới, dữ liệu cũ)
        """
        import psycopg2, os
        DB_URL = os.getenv("DATABASE_URL", "postgresql://postgres:ducmanh1801@localhost:5432/TOT_AGV")
        conn = None
        try:
            conn = psycopg2.connect(DB_URL)
            cur  = conn.cursor()

            # Kiểm tra cột session_id
            cur.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='agv_task_executions' AND column_name='session_id'
                )
            """)
            has_session_col = cur.fetchone()[0]

            agv_cond   = "AND agv_id = %s" if agv_id else ""
            agv_params = (agv_id,) if agv_id else ()
            results    = []

            # ── 1. Dữ liệu MỚI có session_id → GROUP BY ───────────────────────
            if has_session_col:
                cur.execute(f"""
                    SELECT session_id, session_label, agv_id,
                        EXTRACT(EPOCH FROM MIN(queued_at)),
                        EXTRACT(EPOCH FROM MAX(completed_at)),
                        ARRAY_REMOVE(ARRAY_AGG(dest_node ORDER BY queued_at), NULL),
                        ARRAY_AGG(command ORDER BY queued_at),
                        CASE
                            WHEN SUM(CASE WHEN status IN ('running','queued') THEN 1 ELSE 0 END) > 0 THEN 'running'
                            WHEN SUM(CASE WHEN status='failed'    THEN 1 ELSE 0 END) > 0 THEN 'failed'
                            WHEN SUM(CASE WHEN status='cancelled' THEN 1 ELSE 0 END) > 0 THEN 'cancelled'
                            WHEN SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) = COUNT(*) THEN 'completed'
                            ELSE 'running'
                        END,
                        COUNT(*)
                    FROM agv_task_executions
                    WHERE session_id IS NOT NULL {agv_cond}
                    GROUP BY session_id, session_label, agv_id
                    ORDER BY MIN(queued_at) DESC
                    LIMIT %s
                """, agv_params + (limit,))
                for r in cur.fetchall():
                    results.append({
                        "session_id":    r[0],
                        "session_label": r[1] or "Lệnh thủ công",
                        "agv_id":        r[2],
                        "queued_at":     float(r[3]) if r[3] else None,
                        "completed_at":  float(r[4]) if r[4] else None,
                        "dest_nodes":    list(dict.fromkeys(d for d in (r[5] or []) if d)),
                        "commands":      r[6] or [],
                        "status":        r[7],
                        "step_count":    r[8],
                        "notes":         "",
                    })

            # ── 2. Dữ liệu CŨ không có session_id → gom theo thời gian ────────
            null_filter = "AND session_id IS NULL" if has_session_col else ""
            cur.execute(f"""
                SELECT cmd_id, agv_id, command, dest_node, status,
                    EXTRACT(EPOCH FROM queued_at),
                    EXTRACT(EPOCH FROM completed_at), notes
                FROM agv_task_executions
                WHERE 1=1 {null_filter} {agv_cond}
                ORDER BY agv_id, queued_at ASC
                LIMIT %s
            """, agv_params + (limit * 10,))   # fetch nhiều hơn để group
            raw = cur.fetchall()
            conn.close()

            results.extend(self._group_raw_by_time(raw))
            results.sort(key=lambda x: x["queued_at"] or 0, reverse=True)
            return results[:limit]

        except Exception as e:
            print(f"[QUEUE] get_mission_history error: {e}")
            if conn:
                try: conn.close()
                except Exception: pass
            return []

    @staticmethod
    def _group_raw_by_time(rows, gap_sec: float = 30.0) -> list[dict]:
        """
        Gom các lệnh thô thành missions dựa trên khoảng cách thời gian.
        Lệnh cùng AGV, cách nhau < gap_sec → cùng 1 mission.
        """
        # Nhóm theo AGV
        by_agv: dict[str, list] = {}
        for r in rows:
            by_agv.setdefault(r[1], []).append(r)  # r[1] = agv_id

        missions = []
        for agv_id, cmds in by_agv.items():
            if not cmds:
                continue
            # Chia thành các group theo gap thời gian
            groups: list[list] = []
            current = [cmds[0]]
            for i in range(1, len(cmds)):
                prev_t = float(cmds[i-1][5]) if cmds[i-1][5] else 0
                curr_t = float(cmds[i][5])   if cmds[i][5]   else 0
                if curr_t - prev_t > gap_sec:
                    groups.append(current)
                    current = [cmds[i]]
                else:
                    current.append(cmds[i])
            groups.append(current)

            for grp in groups:
                dest_nodes = list(dict.fromkeys(r[3] for r in grp if r[3]))
                cmd_list   = [r[2] for r in grp]
                statuses   = [r[4] for r in grp]
                notes      = next((r[7] for r in grp if r[7]), "") or ""

                if any(s in ('running', 'queued') for s in statuses):
                    status = 'running'
                elif any(s == 'failed' for s in statuses):
                    status = 'failed'
                elif any(s == 'cancelled' for s in statuses):
                    status = 'cancelled'
                elif all(s == 'completed' for s in statuses):
                    status = 'completed'
                else:
                    status = 'running'

                # Label: tên workflow từ tập lệnh duy nhất
                unique = list(dict.fromkeys(cmd_list))
                parts  = [CMD_LABELS.get(c, c) for c in unique]
                label  = " → ".join(parts) if len(parts) > 1 else (parts[0] if parts else "Lệnh")

                missions.append({
                    "session_id":    grp[0][0],    # cmd_id của lệnh đầu tiên
                    "session_label": label,
                    "agv_id":        agv_id,
                    "queued_at":     float(grp[0][5])  if grp[0][5]  else None,
                    "completed_at":  float(grp[-1][6]) if grp[-1][6] else None,
                    "dest_nodes":    dest_nodes,
                    "commands":      cmd_list,
                    "status":        status,
                    "step_count":    len(grp),
                    "notes":         notes,
                })
        return missions

    # ── Internal ───────────────────────────────────────────────────────────────

    def _do_dispatch(self, cmd: QueuedCommand) -> bool:
        if self.dispatch_fn is None:
            print("[QUEUE] dispatch_fn chưa inject!")
            return False
        try:
            return bool(self.dispatch_fn(cmd))
        except Exception as e:
            print(f"[QUEUE] _do_dispatch error: {e}")
            return False

    def _db_insert(self, cmd: QueuedCommand) -> None:
        if not self._pool:
            return
        async def _do():
            try:
                async with self._pool.acquire() as conn:
                    await conn.execute(
                        "INSERT INTO agv_task_executions"
                        "(cmd_id,agv_id,command,dest_node,status,queued_at,session_id,session_label,"
                        "seq,chain_leg,start_node)"
                        " VALUES($1,$2,$3,$4,$5,to_timestamp($6),$7,$8,$9,$10,$11)",
                        cmd.cmd_id, cmd.agv_id, cmd.command,
                        cmd.dest_node, cmd.status, cmd.queued_at,
                        cmd.session_id, cmd.session_label,
                        float(cmd.seq), bool(cmd.chain_leg), cmd.start_node,
                    )
            except Exception as e:
                print(f"[QUEUE] DB insert error: {e}")
        self._schedule_db(_do())

    def _db_set_chain_leg(self, cmd: QueuedCommand) -> None:
        if not self._pool:
            return
        async def _do():
            try:
                async with self._pool.acquire() as conn:
                    await conn.execute("UPDATE agv_task_executions SET chain_leg=$2 WHERE cmd_id=$1",
                                       cmd.cmd_id, bool(cmd.chain_leg))
            except Exception as e:
                print(f"[QUEUE] DB chain_leg error: {e}")
        self._schedule_db(_do())

    def _db_update(self, cmd: QueuedCommand) -> None:
        if not self._pool:
            return
        async def _do():
            try:
                async with self._pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE agv_task_executions SET "
                        "status=$2,started_at=to_timestamp($3),"
                        "completed_at=to_timestamp($4),notes=$5 "
                        "WHERE cmd_id=$1",
                        cmd.cmd_id, cmd.status,
                        cmd.started_at, cmd.completed_at, cmd.notes or "",
                    )
            except Exception as e:
                print(f"[QUEUE] DB update error: {e}")
        self._schedule_db(_do())


# ── Singleton ──────────────────────────────────────────────────────────────────
agv_task_queue = AGVTaskQueue()
