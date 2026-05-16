"""
protocol/heartbeat.py  — Heartbeat & Latency Monitor
------------------------------------------------------
Kiểm soát độ trễ và phản hồi giữa AGV và Server.
Cảnh báo nếu AGV mất kết nối hoặc latency quá cao.

Module này hoàn toàn MỚI — chưa có trong codebase cũ.
"""
from __future__ import annotations
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.context import AppContext

# Ngưỡng cảnh báo
HEARTBEAT_TIMEOUT_S = 10.0   # AGV không gửi state trong 10s → cảnh báo offline
LATENCY_WARN_MS     = 500    # Round-trip > 500ms → cảnh báo độ trễ


class HeartbeatMonitor:
    """
    Theo dõi thời gian phản hồi của từng AGV.
    Chạy trong background thread (tần suất 1s).
    """

    def __init__(self, ctx: AppContext):
        self.ctx = ctx
        self._last_seen: dict[str, float] = {}   # agv_id → timestamp
        self._latency:   dict[str, float] = {}   # agv_id → ms

    def record_heartbeat(self, agv_id: str):
        """Gọi mỗi khi nhận được state message từ AGV."""
        self._last_seen[agv_id] = time.time()

    def record_latency(self, agv_id: str, latency_ms: float):
        """Gọi sau khi đo được round-trip time (gửi lệnh → nhận ACK)."""
        self._latency[agv_id] = latency_ms

    def get_status(self, agv_id: str) -> dict:
        """
        Trả về {online: bool, last_seen_s: float, latency_ms: float}
        """
        now      = time.time()
        last     = self._last_seen.get(agv_id, 0)
        latency  = self._latency.get(agv_id, -1)
        elapsed  = now - last if last > 0 else float('inf')
        return {
            "online":      elapsed < HEARTBEAT_TIMEOUT_S,
            "last_seen_s": round(elapsed, 1),
            "latency_ms":  round(latency, 1),
        }

    def run_loop(self):
        """
        Vòng lặp 1s: kiểm tra tất cả AGV, phát cảnh báo nếu timeout/latency cao.
        TODO: implement — tích hợp vào thread riêng hoặc tk.after()
        """
        raise NotImplementedError
