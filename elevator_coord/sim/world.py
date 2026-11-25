"""
world.py — Khung mô phỏng: nối broker giả + PLC thang + Master + Bộ gọi + coordinator + stub AGV,
bước thời gian ảo. Chạy hàng giờ thang máy trong mili-giây, không cần mạng/phần cứng.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from .. import protocol as P
from ..clock import FakeClock
from ..config import CoordinatorConfig, default_config
from ..coordinator import ElevatorCoordinator
from ..ride import EventType, RideEvent
from .agv_stub import AgvStub
from .fake_broker import FakeBroker
from .sim_caller import SimCaller
from .sim_car import SimCar
from .sim_master import SimMaster


class World:
    def __init__(self, config: Optional[CoordinatorConfig] = None, *, start_floor: int = 1,
                 car_kwargs: Optional[Dict[str, Any]] = None,
                 door_sensor_valid: bool = True, seed: int = 0,
                 board_after: float = 3.0, exit_after: float = 3.0) -> None:
        self.config = config or default_config()
        ecfg = self.config.elevators[0]
        self.factory = self.config.factory
        self.elevator_id = ecfg.elevator_id
        self.clock = FakeClock()
        self.broker = FakeBroker(self.clock, seed)
        self.car = SimCar(floors=tuple(ecfg.floors), start_floor=start_floor, **(car_kwargs or {}))
        self.master = SimMaster(self.broker, self.clock, self.car, self.factory, self.elevator_id,
                                ecfg.master_device, ecfg.floors, door_sensor_valid=door_sensor_valid)
        self.callers: Dict[int, SimCaller] = {
            fl: SimCaller(self.broker, self.clock, self.car, self.factory, self.elevator_id,
                          c.device_id, fl, c.directions)
            for fl, c in ecfg.callers.items()}
        self.events: List[RideEvent] = []
        self.fms_client = self.broker.client("fms")
        self.coord = ElevatorCoordinator(self.config, self.fms_client, self.clock, on_event=self._on_event)
        self.agv = AgvStub(self.coord, self.clock, board_after, exit_after)
        self.extra_ticks: List[Callable[[], None]] = []
        self.listeners: List[Callable[[RideEvent], None]] = []   # thêm callback nhận sự kiện (tùy chọn)
        self.run_coord = True        # False = mô phỏng FMS treo (coordinator ngừng tick)

    def _on_event(self, ev: RideEvent) -> None:
        self.events.append(ev)
        self.agv.on_event(ev)
        for fn in self.listeners:
            fn(ev)

    # ---------------- chạy ----------------
    def start(self, settle_s: float = 3.0) -> "World":
        self.coord.start()
        self.run(settle_s)
        return self

    def step(self, dt: float = 0.1) -> None:
        self.clock.advance(dt)
        now = self.clock.monotonic()
        self.car.step(dt, now)
        self.master.tick()
        for c in self.callers.values():
            c.tick()
        self.broker.pump()
        self.agv.tick()
        for fn in self.extra_ticks:
            fn()
        if self.run_coord:
            self.coord.tick()
        self.broker.pump()

    def run(self, seconds: float, dt: float = 0.1) -> None:
        for _ in range(int(round(seconds / dt))):
            self.step(dt)

    def run_until(self, predicate: Callable[[], bool], timeout: float, dt: float = 0.1) -> bool:
        for _ in range(int(round(timeout / dt))):
            if predicate():
                return True
            self.step(dt)
        return predicate()

    # ---------------- tiện ích truy vấn ----------------
    def types(self, ride_id: Optional[str] = None) -> List[str]:
        return [e.type.value for e in self.events if ride_id is None or e.ride_id == ride_id]

    def has(self, typ: EventType, ride_id: Optional[str] = None) -> bool:
        return any(e.type == typ and (ride_id is None or e.ride_id == ride_id) for e in self.events)

    def find(self, typ: EventType, ride_id: Optional[str] = None) -> List[RideEvent]:
        return [e for e in self.events if e.type == typ and (ride_id is None or e.ride_id == ride_id)]

    def ride_done(self, ride_id: str) -> bool:
        r = self.coord.get_ride(ride_id)
        return r is not None and r.state.value in ("COMPLETED", "FAILED", "CANCELLED")

    def actions(self, device_id: str) -> List[Tuple[str, Dict[str, Any]]]:
        """Các action FMS đã gửi tới thiết bị, KHỬ TRÙNG theo actionId, đúng thứ tự: [(actionType, params)]."""
        topic = P.topic_actions(self.factory, self.elevator_id, device_id)
        seen, out = set(), []
        for _t, tp, payload in self.broker.log:
            if tp != topic:
                continue
            for typ, aid, params in P.parse_actions(payload):
                if aid not in seen:
                    seen.add(aid)
                    out.append((typ, params))
        return out

    def action_types(self, device_id: str, collapse: bool = True, skip: Tuple[str, ...] = ()) -> List[str]:
        types = [t for t, _ in self.actions(device_id) if t not in skip]
        if not collapse:
            return types
        out: List[str] = []
        for t in types:
            if not out or out[-1] != t:
                out.append(t)
        return out

    def outputs_idle(self) -> bool:
        """Mọi relay giữ cửa/gọi tầng đã nhả?"""
        return (not self.master.hold and not self.car.hold
                and all(c.direction is None for c in self.callers.values()))
