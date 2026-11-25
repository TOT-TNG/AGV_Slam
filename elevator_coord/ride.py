"""
ride.py — Dữ liệu một chuyến đi + sự kiện phát ra cho FMS (docs/05).
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


class RideState(str, enum.Enum):
    QUEUED = "QUEUED"
    CALLING_HALL = "CALLING_HALL"
    WAIT_ELEVATOR = "WAIT_ELEVATOR"
    HOLDING = "HOLDING"
    BOARDING = "BOARDING"
    RECOVER_BOARD = "RECOVER_BOARD"
    DEPARTING = "DEPARTING"
    TRANSIT = "TRANSIT"
    ARRIVED = "ARRIVED"
    EXITING = "EXITING"
    RELEASING = "RELEASING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


TERMINAL = (RideState.COMPLETED, RideState.FAILED, RideState.CANCELLED)


class EventType(str, enum.Enum):
    QUEUED = "QUEUED"
    STARTED = "STARTED"
    BOARD_ALLOWED = "BOARD_ALLOWED"
    BOARD_REVOKED = "BOARD_REVOKED"
    EXIT_ALLOWED = "EXIT_ALLOWED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    WARNING = "WARNING"
    ZONE_RELEASED = "ZONE_RELEASED"


@dataclass
class RideEvent:
    type: EventType
    ride_id: Optional[str]
    agv_id: Optional[str]
    elevator_id: str
    ts: float
    data: Dict[str, Any] = field(default_factory=dict)


class RideRejected(Exception):
    """request_ride bị từ chối. `.reason` là mã ngắn (unknown_elevator, floor_invalid, same_floor,
    route_not_allowed, direction_unsupported, agv_busy)."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason


@dataclass
class Ride:
    ride_id: str
    elevator_id: str
    agv_id: str
    from_floor: int
    to_floor: int
    direction: str
    priority: int
    seq: int
    created_at: float

    state: RideState = RideState.QUEUED
    state_since: float = 0.0
    started_at: Optional[float] = None
    finished_at: Optional[float] = None

    board_announced: bool = False     # đã phát BOARD_ALLOWED ít nhất 1 lần
    agv_ready: bool = True            # xe đã tới node chờ (chỉ xét khi unit.defer_until_ready)
    boarded: bool = False             # FMS đã gọi agv_boarded()
    exited: bool = False              # FMS đã gọi agv_exited()
    recoveries: int = 0

    outcome: Optional[RideState] = None   # COMPLETED / FAILED / CANCELLED (đang trong RELEASING)
    reason: str = ""
    zone_floor: Optional[int] = None      # tầng khóa mà ride này đã cấp/đang giữ
    zone_new: bool = False                # khóa do CHÍNH ride này cấp mới

    # --- nội bộ state machine (không phải API) ---
    cmds: Dict[str, Any] = field(default_factory=dict)    # lệnh của pha hiện tại (xóa khi đổi pha)
    cond: Dict[str, float] = field(default_factory=dict)  # mốc "điều kiện đúng liên tục từ" (xóa khi đổi pha)
    phase: Dict[str, Any] = field(default_factory=dict)   # biến cục bộ pha hiện tại (xóa khi đổi pha)
    data: Dict[str, Any] = field(default_factory=dict)    # biến bền vững suốt ride

    @property
    def agv_inside(self) -> bool:
        return self.boarded and not self.exited

    def public(self) -> Dict[str, Any]:
        return {
            "ride_id": self.ride_id, "elevator_id": self.elevator_id, "agv_id": self.agv_id,
            "from": self.from_floor, "to": self.to_floor, "state": self.state.value,
            "priority": self.priority, "boarded": self.boarded, "exited": self.exited,
            "recoveries": self.recoveries, "reason": self.reason,
        }
