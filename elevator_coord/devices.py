"""
devices.py — Bản sao phía FMS của một thiết bị (master / bộ gọi): state mới nhất + presence.
"""
from __future__ import annotations

from typing import Optional

from . import protocol as P


class DeviceProxy:
    def __init__(self, device_id: str, kind: str) -> None:
        self.device_id = device_id
        self.kind = kind
        self.state: Optional[P.DeviceState] = None
        self.connection: str = "UNKNOWN"
        self.last_state_at: Optional[float] = None
        self._unavail_since: Optional[float] = None
        # tự chữa rò rỉ
        self.leak_since: Optional[float] = None
        self.last_reset_at: float = -1e9

    # ---- cập nhật từ message ----
    def update_state(self, state: P.DeviceState, now: float) -> None:
        self.state = state
        self.last_state_at = now

    def update_connection(self, conn: str) -> None:
        self.connection = conn

    # ---- truy vấn ----
    def fresh(self, now: float, stale_s: float) -> bool:
        return self.last_state_at is not None and (now - self.last_state_at) <= stale_s

    def available(self, now: float, stale_s: float) -> bool:
        """state còn mới và LWT không báo chết."""
        return self.fresh(now, stale_s) and self.connection in ("ONLINE", "UNKNOWN")

    def refresh_availability(self, now: float, stale_s: float, link_up: bool = True) -> None:
        """Gọi mỗi tick để biết thiết bị đã mất liên lạc bao lâu.
        link_up=False: chính FMS mất broker -> không tính thời gian "thiết bị offline" (không phải lỗi thiết bị);
        khi FMS có mạng lại, đồng hồ bắt đầu đếm từ đầu."""
        if not link_up:
            self._unavail_since = None
        elif self.available(now, stale_s):
            self._unavail_since = None
        elif self._unavail_since is None:
            self._unavail_since = now

    def unavailable_for(self, now: float) -> float:
        return 0.0 if self._unavail_since is None else now - self._unavail_since

    def usable_state(self, now: float, stale_s: float) -> Optional[P.DeviceState]:
        """State chỉ khi còn mới & thiết bị không bị báo chết; ngược lại None."""
        return self.state if self.available(now, stale_s) else None
