"""
sim_caller.py — Firmware Bộ gọi tầng giả: relay Up/Dn chạy chu kỳ 5 s ON / 1 s OFF có TTL
(docs/04 §3.2). Loại trừ lẫn nhau Up/Dn như bộ gọi T2 của hệ cũ.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

from .. import protocol as P
from ..clock import Clock
from .fake_broker import FakeBroker
from .sim_car import SimCar
from .sim_device import SimDevice

HALL_ON_S = 5.0
HALL_OFF_S = 1.0


class SimCaller(SimDevice):
    kind = P.KIND_CALLER

    def __init__(self, broker: FakeBroker, clock: Clock, car: SimCar, factory: str, elevator_id: str,
                 device_id: str, floor: int, directions: Sequence[str], **kw: Any) -> None:
        self.car = car
        self.floor = floor
        self.directions = tuple(directions)
        self._boot()
        super().__init__(broker, clock, factory, elevator_id, device_id, **kw)

    def _boot(self) -> None:
        self.direction: Optional[str] = None
        self.hall_until = 0.0
        self.relay = False
        self._phase_t = 0.0
        self._apply_relay()

    def on_manager_lost(self) -> None:
        self._deactivate()

    def _deactivate(self) -> None:
        self.direction = None
        self.relay = False
        self._apply_relay()

    def _apply_relay(self) -> None:
        for d in ("UP", "DN"):
            self.car.set_hall_relay(self.floor, d, bool(self.relay and self.direction == d))

    def _exec(self, st: P.ActionState, typ: str, params: Dict[str, Any], now: float) -> None:
        if typ == P.ACT_HALL_CALL:
            d, ttl = params.get("direction"), params.get("ttlS")
            if d not in self.directions:
                st.status, st.result = P.ST_FAILED, "direction_unsupported"
                return
            if not isinstance(ttl, int) or not (1 <= ttl <= 600):
                st.status, st.result = P.ST_FAILED, "ttl_out_of_range"
                return
            if self.direction is not None and self.direction != d:
                st.status, st.result = P.ST_FAILED, "opposite_direction_active"
                return
            if self.direction is None:
                self.direction, self.relay, self._phase_t = d, True, now
            self.hall_until = now + ttl
            st.status = P.ST_FINISHED
        elif typ in (P.ACT_RELEASE_HALL, P.ACT_RESET):
            self._deactivate()
            st.status = P.ST_FINISHED
        else:
            st.status, st.result = P.ST_FAILED, "unknown_action"

    def _logic(self, now: float) -> None:
        if self.direction is not None:
            if now >= self.hall_until:
                self._deactivate()
            else:
                span = HALL_ON_S if self.relay else HALL_OFF_S
                if now - self._phase_t >= span:
                    self.relay = not self.relay
                    self._phase_t = now
        self._apply_relay()

    def _build_state(self) -> str:
        now = self.clock.monotonic()
        st = P.CallerState(
            floor=self.floor,
            directions=self.directions,
            hall_active=self.direction is not None,
            hall_direction=self.direction,
            hall_ttl_s=self.ceil_s(self.hall_until - now) if self.direction else 0,
            hall_relay=self.relay,
            action_states=list(self.history),
        )
        return P.build_caller_state(self._header(self.t_state), st, {"fw": "sim", "rssi": -50, "uptimeS": int(now)})
