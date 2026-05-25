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

CMD_LABELS = {
    CMD_GO_TO:     "Đi đến điểm",
    CMD_GO_CHARGE: "Đi sạc pin",
    CMD_GO_WAIT:   "Về khu chờ",
    CMD_STOP:      "Dừng khẩn cấp",
    CMD_RESUME:    "Tiếp tục",
}

STATUS_QUEUED    = "queued"
STATUS_RUNNING   = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED    = "failed"
STATUS_CANCELLED = "cancelled"


@dataclass
class QueuedCommand:
    cmd_id:       str
    agv_id:       str
    command:      str
    dest_node:    Optional[str]
    start_node:   Optional[str] = None   # vị trí xuất phát thủ công (Line AGV)
    queued_at:    float = field(default_factory=time.time)
    started_at:   Optional[float] = None
    completed_at: Optional[float] = None
    status:       str = STATUS_QUEUED
    notes:        str = ""

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

    # ── Public API ─────────────────────────────────────────────────────────────

    def is_busy(self, agv_id: str) -> bool:
        return bool(self._running.get(agv_id))

    def dispatch_or_queue(
        self,
        agv_id:     str,
        command:    str,
        dest_node:  Optional[str] = None,
        start_node: Optional[str] = None,
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
            )
            self._running[agv_id] = cmd
            self._db_insert(cmd)
            ok = self._do_dispatch(cmd)
            if not ok:
                cmd.status       = STATUS_FAILED
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
            )
            self._queues.setdefault(agv_id, deque()).append(cmd)
            self._db_insert(cmd)
            print(f"[QUEUE] {agv_id}: enqueued '{command}' dest={dest_node} id={cmd.cmd_id}")
            return cmd, False

    def on_agv_completed(self, agv_id: str, notes: str = "") -> None:
        """Gọi khi AGV hoàn thành lệnh. Tự dispatch lệnh tiếp theo nếu có."""
        running = self._running.get(agv_id)
        if running:
            running.status        = STATUS_COMPLETED
            running.completed_at  = time.time()
            running.notes         = notes
            self._running[agv_id] = None   # ← Giải phóng AGV NGAY
            self._db_update(running)
            print(f"[QUEUE] {agv_id}: completed cmd={running.cmd_id}")

        q = self._queues.get(agv_id)
        if not q:
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
                    next_cmd.status       = STATUS_FAILED
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
                next_cmd.status       = STATUS_FAILED
                next_cmd.completed_at = time.time()
                next_cmd.notes        = "auto-dispatch failed"
                self._running[agv_id] = None
                self._db_update(next_cmd)

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
        return {"cancelled_running": running, "cancelled_queued": queued_n}

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
                        "(cmd_id,agv_id,command,dest_node,status,queued_at)"
                        " VALUES($1,$2,$3,$4,$5,to_timestamp($6))",
                        cmd.cmd_id, cmd.agv_id, cmd.command,
                        cmd.dest_node, cmd.status, cmd.queued_at,
                    )
            except Exception as e:
                print(f"[QUEUE] DB insert error: {e}")
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
