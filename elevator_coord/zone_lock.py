"""
zone_lock.py — Khóa độc quyền theo tầng (tổng quát hóa LOCK3 của hệ cũ, docs/05 §4.4).
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple, Union


class ZoneLock:
    def __init__(self, floor: int, timeout_s: float, release_floor: int = 1) -> None:
        self.floor = floor
        self.release_floor = release_floor
        self.timeout_s = timeout_s
        self.owner: Optional[str] = None
        self.acquired_at: float = 0.0

    def can_acquire(self, agv_id: str) -> bool:
        return self.owner is None or self.owner == agv_id

    def acquire(self, agv_id: str, now: float) -> bool:
        """Trả True nếu khóa MỚI được cấp (False nếu chủ cũ xin lại hoặc bị từ chối)."""
        if self.owner is None:
            self.owner = agv_id
            self.acquired_at = now      # KHÔNG làm mới khi xin lại: watchdog tính từ lần cấp đầu (như LOCK3)
            return True
        return False

    def release(self, agv_id: Optional[str] = None) -> bool:
        if self.owner is None:
            return False
        if agv_id is not None and self.owner != agv_id:
            return False
        self.owner = None
        return True

    def expired(self, now: float) -> bool:
        return self.owner is not None and (now - self.acquired_at) >= self.timeout_s


class ZoneLocks:
    def __init__(self, zones: Dict[int, Union[float, Tuple[float, int]]]) -> None:
        """zones: {tầng khóa: timeout_s} hoặc {tầng khóa: (timeout_s, release_floor)}"""
        self._locks = {}
        for fl, v in zones.items():
            t, rf = v if isinstance(v, tuple) else (v, 1)
            self._locks[fl] = ZoneLock(fl, t, rf)

    def owned_by(self, agv_id: str) -> List[ZoneLock]:
        return [z for z in self._locks.values() if z.owner == agv_id]

    def get(self, floor: int) -> Optional[ZoneLock]:
        return self._locks.get(floor)

    def expired(self, now: float) -> List[ZoneLock]:
        return [z for z in self._locks.values() if z.expired(now)]

    def snapshot(self) -> Dict[int, Optional[str]]:
        return {fl: z.owner for fl, z in self._locks.items()}
