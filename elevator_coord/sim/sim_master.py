"""
sim_master.py — Firmware Master (cabin) giả: đọc SimCar qua cảm biến X4..X7 (có debounce),
điều khiển nút giữ cửa Y2 / đóng nhanh Y3 / gọi tầng Y4..Y6 theo hợp đồng docs/04 §3.1.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from .. import protocol as P
from ..clock import Clock
from .fake_broker import FakeBroker
from .sim_car import SimCar
from .sim_device import SimDevice


class SimMaster(SimDevice):
    kind = P.KIND_MASTER

    def __init__(self, broker: FakeBroker, clock: Clock, car: SimCar, factory: str, elevator_id: str,
                 device_id: str = "master", floors: Sequence[int] = (1, 2, 3),
                 door_sensor_valid: bool = True, debounce_s: float = 0.1, **kw: Any) -> None:
        self.car = car
        self.floors = tuple(floors)
        self.door_sensor_valid = door_sensor_valid
        self.debounce_s = debounce_s
        self._boot()
        super().__init__(broker, clock, factory, elevator_id, device_id, **kw)

    def _boot(self) -> None:
        self.hold = False
        self.hold_auto = False
        self.dep: Optional[Dict[str, Any]] = None   # depart đang canh (xem firmware master/main.cpp)
        self.hold_until = 0.0
        self.pulses: List[Dict[str, Any]] = []      # {"st": ActionState, "floor": int, "end": float}
        self.fast: Optional[Dict[str, Any]] = None  # {"st": ActionState, "end": float}
        self._floor_deb: Optional[int] = None
        self._door_deb = False
        self._cand_floor: Optional[int] = None
        self._cand_floor_t = 0.0
        self._cand_door = False
        self._cand_door_t = 0.0

    # ---- an toàn ----
    def on_manager_lost(self) -> None:
        self.hold = False       # FMS chết -> nhả giữ cửa ngay (xung đang chạy cho chạy hết)

    # ---- action ----
    def _exec(self, st: P.ActionState, typ: str, params: Dict[str, Any], now: float) -> None:
        if typ == P.ACT_CALL_FLOOR:
            floor, ms = params.get("floor"), int(params.get("pulseMs", 1000) or 1000)
            if not isinstance(floor, int) or floor not in self.floors:
                st.status, st.result = P.ST_FAILED, "floor_out_of_range"
                return
            st.status = P.ST_RUNNING
            self.pulses.append({"st": st, "floor": floor, "end": now + ms / 1000.0})
            self.car.press_cabin(floor)
        elif typ == P.ACT_HOLD_DOOR:
            ttl = params.get("ttlS")
            if not isinstance(ttl, int) or not (1 <= ttl <= 600):
                st.status, st.result = P.ST_FAILED, "ttl_out_of_range"
                return
            if self.fast:                                # giữ cửa thắng đóng nhanh: không bao giờ bật cả hai
                self.fast["st"].status, self.fast["st"].result = P.ST_FAILED, "preempted_by_hold"
                if self.fast.get("depart"):
                    self.dep = None
                self.fast = None
            if self.dep:                                 # FMS nhận quản lý cửa -> giải phóng depart (không tự giữ cửa lại)
                self.dep["st"].status, self.dep["st"].result = P.ST_FINISHED, "handed_to_fms"
                self.dep = None
            self.hold_auto = False                       # FMS tự quản giữ cửa từ đây
            self.hold, self.hold_until = True, now + ttl
            st.status = P.ST_FINISHED
        elif typ == P.ACT_RELEASE_DOOR:
            if self.dep:                                 # depart còn treo mà FMS đã nhả cửa -> giải phóng
                self.dep["st"].status, self.dep["st"].result = P.ST_FAILED, "superseded"
                self.dep = None
            self.hold = False
            self.hold_auto = False
            st.status = P.ST_FINISHED
        elif typ == P.ACT_FAST_CLOSE:
            if self.hold:                                # đang giữ cửa: từ chối đóng nhanh
                st.status, st.result = P.ST_FAILED, "door_hold_active"
                return
            ms = int(params.get("durationMs", 3000) or 3000)
            st.status = P.ST_RUNNING
            self.fast = {"st": st, "end": now + ms / 1000.0}
        elif typ == P.ACT_DEPART:
            to = params.get("toFloor")
            ttl = params.get("holdTtlS", 300)
            pms = int(params.get("pulseMs", 1000) or 1000)
            fms = int(params.get("fastCloseMs", 3000) or 3000)
            if not isinstance(to, int) or to not in self.floors:
                st.status, st.result = P.ST_FAILED, "floor_out_of_range"
                return
            if not isinstance(ttl, int) or not (1 <= ttl <= 600):
                st.status, st.result = P.ST_FAILED, "ttl_out_of_range"
                return
            frm = self._floor_deb
            if frm == to:
                st.status, st.result = P.ST_FAILED, "already_at_floor"
                return
            if self.dep:                                  # depart mới thay depart cũ
                self.dep["st"].status, self.dep["st"].result = P.ST_FAILED, "superseded"
                self.dep = None
            if self.fast:
                self.fast = None
            self.hold, self.hold_auto = False, False       # tắt giữ cửa trong
            st.status = P.ST_RUNNING
            self.fast = {"st": st, "end": now + fms / 1000.0, "depart": True}
            self.dep = {"st": st, "to": to, "from": frm, "phase": 0, "ttl": ttl, "pulse_ms": pms,
                        "left": frm is None, "resends": 0, "last_call": now, "arrived_since": None,
                        "started": now}
        elif typ == P.ACT_RESET:
            self.hold = False
            self.hold_auto = False
            for p in self.pulses:
                p["st"].status = P.ST_FINISHED
            self.pulses.clear()
            if self.fast:
                self.fast["st"].status = P.ST_FINISHED
            self.fast = None
            if self.dep:
                self.dep["st"].status, self.dep["st"].result = P.ST_FAILED, "cancelled"
                self.dep = None
            st.status = P.ST_FINISHED
        else:
            st.status, st.result = P.ST_FAILED, "unknown_action"

    # ---- logic theo thời gian ----
    def _logic(self, now: float) -> None:
        # debounce cảm biến
        raw_floor, raw_door = self.car.floor_sensor, self.car.door_open_sensor
        if raw_floor != self._cand_floor:
            self._cand_floor, self._cand_floor_t = raw_floor, now
        elif now - self._cand_floor_t >= self.debounce_s:
            self._floor_deb = raw_floor
        if raw_door != self._cand_door:
            self._cand_door, self._cand_door_t = raw_door, now
        elif now - self._cand_door_t >= self.debounce_s:
            self._door_deb = raw_door
        # TTL giữ cửa
        if self.hold and now >= self.hold_until:
            self.hold = False
        # xung gọi tầng / đóng nhanh
        for p in list(self.pulses):
            if now >= p["end"]:
                p["st"].status = P.ST_FINISHED
                self.pulses.remove(p)
        if self.fast and now >= self.fast["end"]:
            if self.fast.get("depart") and self.dep:
                d = self.dep                           # hết đóng cửa -> bấm gọi tầng đích
                self.pulses.append({"st": d["st"], "floor": d["to"], "end": now + d["pulse_ms"] / 1000.0})
                self.car.press_cabin(d["to"])
                d["phase"], d["last_call"] = 1, now
            else:
                self.fast["st"].status = P.ST_FINISHED
            self.fast = None
        self._service_depart(now)
        # xuất ra "PLC"
        self.car.set_hold(self.hold)
        self.car.set_fast_close(self.fast is not None)

    def _service_depart(self, now: float) -> None:
        """Giống serviceDepart() của firmware: tới tầng đích ổn định -> TỰ giữ cửa (không cần mạng)."""
        d = self.dep
        if d is None or d["phase"] == 0:
            return
        if d["phase"] == 1 and not any(p["floor"] == d["to"] for p in self.pulses):
            d["phase"] = 2
        fl = self._floor_deb
        if fl != d["from"]:
            d["left"] = True
        if fl == d["to"]:
            if d["arrived_since"] is None:
                d["arrived_since"] = now
            if now - d["arrived_since"] >= 2.0:     # = DEPART_ARRIVE_STABLE_MS (2000 ms)
                self.hold, self.hold_auto, self.hold_until = True, True, now + d["ttl"]
                self.dep = None
            return
        d["arrived_since"] = None
        if not d["left"] and d["resends"] < 3 and now - d["last_call"] >= 20.0:
            self.pulses.append({"st": d["st"], "floor": d["to"], "end": now + d["pulse_ms"] / 1000.0})
            self.car.press_cabin(d["to"])
            d["resends"] += 1
            d["last_call"], d["phase"] = now, 1
        if now - d["started"] >= 600.0:
            self.dep = None

    def _build_state(self) -> str:
        now = self.clock.monotonic()
        sensors = {"x4": int(self._door_deb)}
        for i, fl in enumerate(sorted(self.floors)):
            sensors[f"x{5 + i}"] = int(self._floor_deb == fl)
        st = P.MasterState(
            floor=self._floor_deb,
            door_open=self._door_deb if self.door_sensor_valid else None,
            door_sensor_valid=self.door_sensor_valid,
            door_hold=self.hold,
            door_hold_auto=self.hold_auto,
            depart_phase=(("closing", "calling", "transit")[self.dep["phase"]] if self.dep else None),
            depart_to=(self.dep["to"] if self.dep else None),
            hold_ttl_s=self.ceil_s(self.hold_until - now) if self.hold else 0,
            fast_close=self.fast is not None,
            call_pulse=self.pulses[-1]["floor"] if self.pulses else None,
            sensors=sensors,
            errors=[] if self.door_sensor_valid else [
                {"errorType": "DOOR_SENSOR_BYPASS", "errorLevel": "WARNING",
                 "errorDescription": "cảm biến cửa bị bypass"}],
            action_states=list(self.history),
        )
        return P.build_master_state(self._header(self.t_state), st,
                                    {"fw": "sim", "rssi": -50, "uptimeS": int(now)})
