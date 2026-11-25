"""
config.py — Cấu hình coordinator (khớp phần cứng 3 tầng hiện hữu, xem docs/06).

Mọi hằng số thời gian là mặc định lấy từ hệ UDP cũ (docs/02 §5) — chỉnh qua `timing`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, fields
from typing import Dict, List, Optional, Tuple

UP = "UP"
DN = "DN"
DIRECTIONS = (UP, DN)


class ConfigError(ValueError):
    pass


@dataclass
class Timing:
    # --- thiết bị / kênh lệnh ---
    state_stale_s: float = 5.0          # state cũ hơn mức này = chưa có thông tin
    device_offline_s: float = 30.0      # thiết bị cần dùng mà offline quá mức này -> FAILED
    boarding_offline_s: float = 90.0    # pha BOARDING: cabin (Master) offline quá mức này mới FAILED (cửa đóng/vào vùng chết Wi-Fi)
    hall_recall_grace_s: float = 3.0    # hallCall FINISHED mà relay không active quá mức này -> gọi lại (TTL hết)
    cmd_retry_s: float = 1.0            # gửi lại cùng actionId nếu chưa thấy phản hồi
    cmd_max_retries: int = 10           # quá số lần này -> EXPIRED
    # --- TTL relay (dead-man switch) ---
    hall_ttl_s: int = 30
    hold_ttl_s: int = 30
    ttl_refresh_s: float = 10.0         # làm mới TTL (gửi actionId mới) khi còn đang cần
    # --- điều kiện chuyển pha ---
    arrival_stable_s: float = 0.5       # (đúng tầng + cửa mở) phải liên tục đủ lâu (cũ: delay 200 ms)
    wrong_floor_s: float = 1.0          # cabin ở tầng thật khác tầng mong đợi liên tục đủ lâu -> sai tầng
    hold_verify_s: float = 5.0          # giữ cửa rồi kiểm lại (cũ: delay(5000))
    hold_timeout_s: float = 0.0         # chờ thiết bị xác nhận doorHold; 0 = chờ tới khi được xác nhận
    # --- timeout theo pha ---
    queue_timeout_s: float = 0.0        # 0 = chờ vô hạn
    elevator_wait_timeout_s: float = 0.0     # 0 = chờ vô hạn (cũ: keep_time 200 s)
    board_timeout_s: float = 0.0             # 0 = chờ vô hạn (cũ: keep_time 200 s)
    transit_timeout_s: float = 0.0           # 0 = chờ tới khi thang tới nơi (cũ: watchdog 360 s)
    exit_timeout_s: float = 0.0              # 0 = chờ vô hạn tới khi xe ra (cũ: Exit_time 300 s)
    cleanup_timeout_s: float = 10.0
    # --- Transit Guard / gọi lại ---
    transit_guard_s: float = 15.0            # cũ: TRANSIT_WF_TIMEOUT
    transit_guard_nodoor_s: float = 45.0     # khi không có cảm biến cửa
    call_retry_s: float = 20.0
    call_retries: int = 0                    # 0 = gọi lại tầng mãi tới khi thang chạy (>0: quá số lần -> elevator_not_moving)
    max_recoveries: int = 0                  # 0 = vô hạn (cũ: transit guard thử vô hạn)
    # --- xung ---
    fast_close_ms: int = 3000                # cũ: dongcua_nhanh delay(3000)
    call_pulse_ms: int = 1000                # cũ: Call_thang_may delay(1000)
    # --- tự chữa rò rỉ ---
    leak_grace_s: float = 2.0
    leak_reset_interval_s: float = 10.0

    def validate(self) -> None:
        for f in fields(self):
            v = getattr(self, f.name)
            if not isinstance(v, (int, float)) or isinstance(v, bool) or v < 0:
                raise ConfigError(f"timing.{f.name} phải là số >= 0 (nhận {v!r})")
        if self.ttl_refresh_s >= self.hold_ttl_s or self.ttl_refresh_s >= self.hall_ttl_s:
            raise ConfigError("timing.ttl_refresh_s phải nhỏ hơn hold_ttl_s và hall_ttl_s")
        if self.cmd_retry_s <= 0 or self.cmd_max_retries < 1:
            raise ConfigError("timing.cmd_retry_s > 0 và cmd_max_retries >= 1")


@dataclass
class CallerConfig:
    floor: int
    device_id: str
    directions: Tuple[str, ...]


@dataclass
class ZoneConfig:
    floor: int                       # tầng bị khóa: mỗi lúc chỉ 1 xe được đi tới tầng này
    timeout_s: float = 1800.0        # watchdog: cũ LOCK3_TIMEOUT 30 phút
    release_floor: Optional[int] = None   # xe chủ khóa phải về tầng này khóa mới nhả (None = tầng thấp nhất)
    enabled: bool = True             # False = tắt khóa mà vẫn giữ cấu hình


@dataclass
class ElevatorConfig:
    elevator_id: str
    floors: List[int]
    master_device: str = "master"
    callers: Dict[int, CallerConfig] = field(default_factory=dict)
    allowed_routes: List[Tuple[int, int]] = field(default_factory=list)
    zones: List[ZoneConfig] = field(default_factory=list)
    timing: Timing = field(default_factory=Timing)

    def hall_direction(self, from_floor: int, to_floor: int) -> str:
        return UP if to_floor > from_floor else DN

    def check_route(self, from_floor: int, to_floor: int) -> Optional[str]:
        """None nếu hợp lệ, ngược lại trả mã lý do."""
        if from_floor not in self.floors or to_floor not in self.floors:
            return "floor_invalid"
        if from_floor == to_floor:
            return "same_floor"
        if (from_floor, to_floor) not in self.allowed_routes:
            return "route_not_allowed"
        caller = self.callers.get(from_floor)
        if caller is None or self.hall_direction(from_floor, to_floor) not in caller.directions:
            return "direction_unsupported"
        return None

    def device_ids(self) -> List[str]:
        return [self.master_device] + [c.device_id for c in self.callers.values()]

    def validate(self) -> None:
        if not self.elevator_id:
            raise ConfigError("elevator.id rỗng")
        if len(self.floors) < 2 or len(set(self.floors)) != len(self.floors):
            raise ConfigError("elevator.floors cần >= 2 tầng, không trùng")
        ids = self.device_ids()
        if len(set(ids)) != len(ids):
            raise ConfigError("device id (master/callers) bị trùng")
        for fl, c in self.callers.items():
            if fl not in self.floors:
                raise ConfigError(f"caller tầng {fl} không nằm trong floors")
            if not c.directions or any(d not in DIRECTIONS for d in c.directions):
                raise ConfigError(f"caller tầng {fl}: directions phải thuộc {DIRECTIONS}")
        for a, b in self.allowed_routes:
            if a not in self.floors or b not in self.floors or a == b:
                raise ConfigError(f"allowed_routes có tuyến không hợp lệ: {(a, b)}")
        for z in self.zones:
            if z.floor not in self.floors:
                raise ConfigError(f"zone tầng {z.floor} không nằm trong floors")
            if z.release_floor is None or z.release_floor not in self.floors:
                raise ConfigError(f"zone tầng {z.floor}: release_floor không nằm trong floors")
            if z.release_floor == z.floor:
                raise ConfigError(f"zone tầng {z.floor}: release_floor không được trùng tầng khóa")
            if z.timeout_s <= 0:
                raise ConfigError("zone.timeout_s phải > 0")
        self.timing.validate()


@dataclass
class CoordinatorConfig:
    factory: str
    elevators: List[ElevatorConfig]

    def get(self, elevator_id: Optional[str]) -> Optional[ElevatorConfig]:
        if elevator_id is None:
            return self.elevators[0] if self.elevators else None
        for e in self.elevators:
            if e.elevator_id == elevator_id:
                return e
        return None

    def validate(self) -> None:
        if not self.factory:
            raise ConfigError("factory rỗng")
        if not self.elevators:
            raise ConfigError("cần ít nhất 1 elevator")
        ids = [e.elevator_id for e in self.elevators]
        if len(set(ids)) != len(ids):
            raise ConfigError("elevator.id bị trùng")
        for e in self.elevators:
            e.validate()

    # ---- nạp từ dict/JSON ----
    @classmethod
    def from_dict(cls, d: dict) -> "CoordinatorConfig":
        if not isinstance(d, dict):
            raise ConfigError("config phải là object JSON")
        elevators = []
        for e in d.get("elevators", []):
            floors = [int(x) for x in e.get("floors", [])]
            callers: Dict[int, CallerConfig] = {}
            for fl, c in (e.get("callers") or {}).items():
                fl_i = int(fl)
                callers[fl_i] = CallerConfig(
                    floor=fl_i,
                    device_id=str(c.get("device", f"call{fl_i}")),
                    directions=tuple(str(x).upper() for x in c.get("directions", [])),
                )
            raw_routes = e.get("allowed_routes", "all")
            if raw_routes == "all":                      # mặc định: coordinator điều phối mọi tuyến giữa các tầng
                routes = [(a, b) for a in floors for b in floors if a != b]
            else:
                routes = [(int(a), int(b)) for a, b in raw_routes]
            zones = [ZoneConfig(floor=int(z["floor"]), timeout_s=float(z.get("timeout_s", 1800)),
                                release_floor=int(z["release_floor"]) if z.get("release_floor") is not None
                                else (min(floors) if floors else None),
                                enabled=bool(z.get("enabled", True)))
                     for z in e.get("zones", [])]
            timing = Timing()
            for k, v in (e.get("timing") or {}).items():
                if not hasattr(timing, k):
                    raise ConfigError(f"timing.{k} không tồn tại")
                setattr(timing, k, v)
            elevators.append(ElevatorConfig(
                elevator_id=str(e.get("id", "")),
                floors=floors,
                master_device=str(e.get("master", "master")),
                callers=callers,
                allowed_routes=routes,
                zones=zones,
                timing=timing,
            ))
        cfg = cls(factory=str(d.get("factory", "")), elevators=elevators)
        cfg.validate()
        return cfg

    @classmethod
    def from_file(cls, path: str) -> "CoordinatorConfig":
        with open(path, "r", encoding="utf-8") as fh:
            return cls.from_dict(json.load(fh))


def default_config(factory: str = "Vietduc", **timing_overrides) -> CoordinatorConfig:
    """Cấu hình khớp phần cứng 3 tầng hiện hữu (mọi tuyến giữa các tầng + khóa tầng 3).
    `timing_overrides` ghi đè `Timing` (vd default_config(board_timeout_s=30))."""
    return CoordinatorConfig.from_dict({
        "factory": factory,
        "elevators": [{
            "id": "ELV01",
            "floors": [1, 2, 3],
            "master": "master",
            "callers": {
                "1": {"device": "call1", "directions": ["UP"]},
                "2": {"device": "call2", "directions": ["UP", "DN"]},
                "3": {"device": "call3", "directions": ["DN"]},
            },
            "allowed_routes": "all",
            "zones": [{"floor": 3, "release_floor": 1, "timeout_s": 1800, "enabled": True}],
            "timing": timing_overrides,
        }],
    })
