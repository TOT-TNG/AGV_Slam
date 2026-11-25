"""
sim_car.py — "PLC thang máy" giả: cabin di chuyển, cửa tự đóng, giữ cửa, nút gọi tầng, người bấm xen ngang.

Chỉ cần đủ thực tế để kiểm thử logic điều phối (không mô phỏng vật lý chính xác):
  * cabin chạy giữa các tầng với `travel_s` giây/tầng; cảm biến tầng chỉ báo khi gần tầng (cửa sổ ±0.15)
  * tới tầng -> mở cửa (door_open_delay) -> giữ mở door_open_hold giây -> đóng (door_close_s)
  * giữ cửa (Y2) hoặc relay gọi tầng (Bộ gọi) ở đúng tầng cabin đang đỗ -> cửa giữ mở / mở lại
  * đóng cửa nhanh (Y3) chỉ có tác dụng khi KHÔNG đang giữ
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

CLOSED, OPENING, OPEN, CLOSING = "CLOSED", "OPENING", "OPEN", "CLOSING"
_SENSOR_WINDOW = 0.15


class SimCar:
    def __init__(self, floors: Sequence[int] = (1, 2, 3), start_floor: int = 1,
                 travel_s: float = 3.0, door_open_delay: float = 1.0,
                 door_open_hold: float = 6.0, door_close_s: float = 1.5) -> None:
        self.floors = tuple(floors)
        self.pos = float(start_floor)
        self.travel_s = travel_s
        self.door_open_delay = door_open_delay
        self.door_open_hold = door_open_hold
        self.door_close_s = door_close_s
        self.targets: List[int] = []
        self.door = CLOSED
        self._timer = 0.0
        self.moving = False
        # đầu vào từ thiết bị
        self.hold = False
        self.fast_close = False
        self._hall: Dict[Tuple[int, str], bool] = {}
        # nhiễu
        self.human_hold_until = 0.0
        self.drop_cabin_presses = 0       # PLC "bỏ lỡ" N lần bấm tầng cabin đầu
        self.cabin_presses: List[int] = []   # log để test kiểm đếm
        self.hall_presses: List[int] = []

    # ---------------- đầu vào ----------------
    def press_cabin(self, floor: int) -> None:
        self.cabin_presses.append(floor)
        if self.drop_cabin_presses > 0:
            self.drop_cabin_presses -= 1
            return
        self._add_target(floor)

    def set_hold(self, on: bool) -> None:
        self.hold = on

    def set_fast_close(self, on: bool) -> None:
        self.fast_close = on

    def set_hall_relay(self, floor: int, direction: str, on: bool) -> None:
        prev = self._hall.get((floor, direction), False)
        self._hall[(floor, direction)] = on
        if on and not prev:
            self.hall_presses.append(floor)
            self._add_target(floor)

    def human_call(self, floor: int) -> None:
        self._add_target(floor)

    def human_hold(self, now: float, seconds: float) -> None:
        self.human_hold_until = now + seconds

    def teleport(self, floor: int, door_open: bool = True) -> None:
        """Test: PLC bất ngờ đưa cabin tới `floor` (mô phỏng người dùng/PLC override)."""
        self.pos = float(floor)
        self.moving = False
        self.targets = [t for t in self.targets if t != floor]
        self.door, self._timer = (OPEN if door_open else CLOSED), 0.0

    def _add_target(self, floor: int) -> None:
        if floor in self.floors and floor not in self.targets:
            self.targets.append(floor)

    # ---------------- đầu ra (cảm biến) ----------------
    @property
    def floor_sensor(self) -> Optional[int]:
        nearest = int(round(self.pos))
        if abs(self.pos - nearest) <= _SENSOR_WINDOW and nearest in self.floors:
            return nearest
        return None

    @property
    def door_open_sensor(self) -> bool:
        return self.door == OPEN

    @property
    def current_floor(self) -> int:
        return int(round(self.pos))

    # ---------------- mô phỏng ----------------
    def _held_at(self, floor: int, now: float) -> bool:
        if self.hold or now < self.human_hold_until:
            return True
        return any(on for (fl, _d), on in self._hall.items() if fl == floor)

    def step(self, dt: float, now: float) -> None:
        if self.moving:
            tgt = self.targets[0]
            step = dt / self.travel_s
            if abs(tgt - self.pos) <= step:
                self.pos = float(tgt)
                self.moving = False
                self.targets.remove(tgt)
                self.door, self._timer = OPENING, 0.0
            else:
                self.pos += step if tgt > self.pos else -step
            return

        f = self.current_floor
        held = self._held_at(f, now)
        if self.door == CLOSED:
            if f in self.targets:
                self.targets.remove(f)
                self.door, self._timer = OPENING, 0.0
            elif held:
                self.door, self._timer = OPENING, 0.0
            elif self.targets:
                self.moving = True
        elif self.door == OPENING:
            self._timer += dt
            if self._timer >= self.door_open_delay:
                self.door, self._timer = OPEN, 0.0
        elif self.door == OPEN:
            if held:
                self._timer = 0.0
            else:
                self._timer += dt
                if self.fast_close:
                    self._timer = self.door_open_hold
                if self._timer >= self.door_open_hold:
                    self.door, self._timer = CLOSING, 0.0
        elif self.door == CLOSING:
            if held:
                self.door, self._timer = OPENING, 0.0
            else:
                self._timer += dt
                if self._timer >= self.door_close_s:
                    self.door = CLOSED
