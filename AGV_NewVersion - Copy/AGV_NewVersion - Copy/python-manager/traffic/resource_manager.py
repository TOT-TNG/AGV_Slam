"""
traffic/resource_manager.py  — 2.3 Resource Management
---------------------------------------------------------
Quản lý thiết bị phục vụ di chuyển: Thang máy, Cửa tự động, Trạm sạc.

- find_nearest_charger → đã migrate vào dispatch/robot_filter.py: RobotFilter.find_nearest_charger()
- find_door_cfg, rebuild_door_maps → đã migrate vào config_mgmt/settings_io.py
- ElevatorManager / DoorManager / ChargerManager: skeleton; elevator/door sẽ mở rộng khi có hardware
"""
from __future__ import annotations
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.context import AppContext


class ResourceState(Enum):
    IDLE    = "idle"
    BUSY    = "busy"
    ERROR   = "error"
    OFFLINE = "offline"


# ── ElevatorManager ──────────────────────────────────────────────────────────

class ElevatorManager:
    """
    Quản lý thang máy: gọi tầng, chờ mở cửa, dispatch AGV.
    Hiện tại placeholder — elevator logic chưa có hardware tương ứng.
    """

    def __init__(self, ctx: "AppContext"):
        self.ctx = ctx
        self._elevators: dict[str, dict] = {}

    def register(self, elev_cfg: dict):
        self._elevators[elev_cfg['id']] = {
            'cfg':   elev_cfg,
            'state': ResourceState.IDLE,
            'holder': None,
            'queue':  [],
        }

    def request(self, agv_id: str, elev_id: str,
                from_floor: int, to_floor: int) -> bool:
        """AGV yêu cầu sử dụng thang. Trả True nếu được assign ngay."""
        elev = self._elevators.get(elev_id)
        if not elev:
            return False
        if elev['state'] == ResourceState.IDLE:
            elev['state']  = ResourceState.BUSY
            elev['holder'] = agv_id
            print(f"[ELEVATOR] {agv_id} → elevator '{elev_id}' assigned "
                  f"floor {from_floor}→{to_floor}")
            return True
        if agv_id not in elev['queue']:
            elev['queue'].append(agv_id)
        return False

    def release(self, agv_id: str, elev_id: str):
        elev = self._elevators.get(elev_id)
        if elev and elev['holder'] == agv_id:
            elev['holder'] = None
            elev['state']  = ResourceState.IDLE
            print(f"[ELEVATOR] {agv_id} nhả elevator '{elev_id}'")
            # Cấp cho AGV tiếp trong hàng chờ
            if elev['queue']:
                next_agv = elev['queue'].pop(0)
                elev['holder'] = next_agv
                elev['state']  = ResourceState.BUSY
                print(f"[ELEVATOR] elevator '{elev_id}' → {next_agv} (từ queue)")

    def on_arrived(self, elev_id: str, floor: int):
        print(f"[ELEVATOR] elevator '{elev_id}' arrived at floor {floor}")


# ── DoorManager ───────────────────────────────────────────────────────────────

class DoorManager:
    """
    Quản lý cửa tự động.
    Delegates find_door / rebuild_maps sang config_mgmt.settings_io.
    """

    def __init__(self, ctx: "AppContext"):
        self.ctx = ctx

    def rebuild_maps(self) -> dict:
        """Build door_check_map từ config. Delegates to settings_io."""
        from config_mgmt.settings_io import rebuild_door_maps
        return rebuild_door_maps(self.ctx.config)

    def find_door(self, tag_id: int, prev_tag: int) -> dict | None:
        """Tìm door_cfg phù hợp. Delegates to settings_io."""
        from config_mgmt.settings_io import find_door_cfg
        return find_door_cfg(self.ctx.config, tag_id, prev_tag)

    def request_open(self, agv_id: str, door_id: str) -> bool:
        print(f"[DOOR] {agv_id} request open door '{door_id}'")
        return True

    def on_door_opened(self, door_id: str):
        print(f"[DOOR] door '{door_id}' opened")


# ── ChargerManager ────────────────────────────────────────────────────────────

class ChargerManager:
    """
    Quản lý trạm sạc.
    find_nearest delegates sang RobotFilter.find_nearest_charger().
    """

    def __init__(self, ctx: "AppContext"):
        self.ctx = ctx
        self._assignments: dict[str, str] = {}   # agv_id → charger_id

    def find_nearest(self, agv) -> dict | None:
        """Delegates to RobotFilter.find_nearest_charger()."""
        from dispatch.robot_filter import RobotFilter
        return RobotFilter(self.ctx).find_nearest_charger(agv)

    def assign(self, agv_id: str, charger_id: str):
        self._assignments[agv_id] = charger_id
        print(f"[CHARGER] {agv_id} assigned to charger '{charger_id}'")

    def release(self, agv_id: str):
        charger_id = self._assignments.pop(agv_id, None)
        if charger_id:
            print(f"[CHARGER] {agv_id} released charger '{charger_id}'")
