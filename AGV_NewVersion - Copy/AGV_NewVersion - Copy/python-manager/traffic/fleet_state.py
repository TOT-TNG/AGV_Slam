"""
traffic/fleet_state.py  — 2.6 State Management
------------------------------------------------
Migrate từ traffic_manager.py: get_fleet_state() (module-level function).
FleetStateManager là wrapper thin — snapshot() gọi get_fleet_state().
"""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.context import AppContext


def get_fleet_state(agv_list: list) -> dict:
    """Snapshot trạng thái tức thời của toàn bộ fleet."""
    snapshot = {}
    for agv in agv_list:
        remaining = []
        if agv.is_navigating and agv.full_path and agv.current_tag in agv.full_path:
            idx       = agv.full_path.index(agv.current_tag)
            remaining = agv.full_path[idx:]
        snapshot[agv.id] = {
            "current_tag"    : agv.current_tag,
            "next_tag"       : getattr(agv, 'next_tag', None),
            "prev_tag"       : agv.prev_tag,
            "remaining_path" : remaining,
            "task_type"      : agv.current_task_type,
            "is_navigating"  : agv.is_navigating,
        }
    return snapshot


class FleetStateManager:
    """
    Quản lý và phân tích trạng thái toàn bộ fleet.
    """

    def __init__(self, ctx: "AppContext"):
        self.ctx = ctx

    def snapshot(self) -> dict:
        """Tạo snapshot trạng thái tất cả AGV tại thời điểm hiện tại."""
        return get_fleet_state(self.ctx.agv_list)
