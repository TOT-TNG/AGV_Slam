"""
agv_stub.py — Giả lập phần FMS/AGV phản ứng với sự kiện thang (docs/07): BOARD_ALLOWED -> sau
`board_after` giây xe vào cabin -> agv_boarded(); EXIT_ALLOWED -> sau `exit_after` giây -> agv_exited().
Dùng cho test và để dev FMS xem mẫu cách nối sự kiện.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from ..clock import Clock
from ..coordinator import ElevatorCoordinator
from ..ride import EventType, RideEvent


class AgvStub:
    def __init__(self, coord: ElevatorCoordinator, clock: Clock,
                 board_after: float = 3.0, exit_after: float = 3.0) -> None:
        self.coord = coord
        self.clock = clock
        self.board_after = board_after
        self.exit_after = exit_after
        self.never_board = set()            # ride_id không bao giờ vào cabin (test timeout)
        self.never_exit = set()
        self.stopped: List[str] = []        # ride_id đã nhận BOARD_REVOKED (FMS phải dừng xe)
        self._due: Dict[Tuple[str, str], float] = {}

    def on_event(self, ev: RideEvent) -> None:
        now = self.clock.monotonic()
        rid = ev.ride_id
        if ev.type == EventType.BOARD_ALLOWED and rid not in self.never_board:
            self._due[(rid, "board")] = now + self.board_after
        elif ev.type == EventType.BOARD_REVOKED:
            self._due.pop((rid, "board"), None)
            self.stopped.append(rid)
        elif ev.type == EventType.EXIT_ALLOWED and rid not in self.never_exit:
            self._due[(rid, "exit")] = now + self.exit_after
        elif ev.type in (EventType.FAILED, EventType.CANCELLED, EventType.COMPLETED):
            self._due.pop((rid, "board"), None)
            self._due.pop((rid, "exit"), None)

    def tick(self) -> None:
        now = self.clock.monotonic()
        for (rid, what), due in list(self._due.items()):
            if now >= due:
                del self._due[(rid, what)]
                if what == "board":
                    self.coord.agv_boarded(rid)
                else:
                    self.coord.agv_exited(rid)
