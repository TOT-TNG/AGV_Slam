"""
clock.py — Đồng hồ tiêm vào được (thời gian thật / thời gian ảo cho test).

Coordinator KHÔNG gọi time.time()/time.sleep() trực tiếp: mọi mốc thời gian lấy từ Clock
để test chạy "hàng giờ" trong mili-giây và xác định (deterministic).
"""
from __future__ import annotations

import time
from typing import Protocol


class Clock(Protocol):
    def monotonic(self) -> float:
        """Giây, đơn điệu tăng — dùng cho timeout/TTL."""

    def wall(self) -> float:
        """Epoch giây — chỉ dùng cho timestamp ISO trong payload."""


class SystemClock:
    def monotonic(self) -> float:
        return time.monotonic()

    def wall(self) -> float:
        return time.time()


class FakeClock:
    """Thời gian ảo: chỉ trôi khi gọi advance()."""

    def __init__(self, start: float = 1000.0, wall_epoch: float = 1_760_000_000.0):
        self._t = float(start)
        self._wall0 = float(wall_epoch)
        self._t0 = float(start)

    def monotonic(self) -> float:
        return self._t

    def wall(self) -> float:
        return self._wall0 + (self._t - self._t0)

    def advance(self, dt: float) -> None:
        if dt < 0:
            raise ValueError("dt phải >= 0")
        self._t += dt
