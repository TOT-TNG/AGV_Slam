"""
traffic/dynamic_rerouting.py  — 2.5 Dynamic Rerouting
-------------------------------------------------------
Logic _rerout_after_off_route, _run_dry_run_for_path, _run_dry_run_for_exact_path
đã được migrate vào dispatch/request_handler.py (RequestHandler).

Class DynamicRerouter ở đây đóng vai trò thin adapter — delegate sang RequestHandler.
"""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.context import AppContext


class DynamicRerouter:
    """
    Thin adapter — delegates to RequestHandler for actual rerouting logic.
    Xem dispatch/request_handler.py: _rerout_after_off_route(),
    _run_dry_run_for_path(), _run_dry_run_for_exact_path().
    """

    def __init__(self, ctx: "AppContext"):
        self.ctx = ctx

    def _get_handler(self):
        return getattr(self.ctx, 'request_handler', None)

    def reroute_after_off_route(self, agv, station_cfg_list: list):
        """Delegate to RequestHandler._rerout_after_off_route()."""
        h = self._get_handler()
        if h:
            h._rerout_after_off_route(agv, station_cfg_list)

    def run_dry_run(self, path: list, prev_tag, task_type: str,
                    end_tag_override=None, facing_tag=None):
        """Delegate to RequestHandler._run_dry_run_for_path()."""
        h = self._get_handler()
        if h:
            return h._run_dry_run_for_path(path, prev_tag, task_type,
                                            end_tag_override, facing_tag)
        return None, None

    def run_dry_run_exact(self, path: list, prev_tag, task_type: str):
        """Delegate to RequestHandler._run_dry_run_for_exact_path()."""
        h = self._get_handler()
        if h:
            return h._run_dry_run_for_exact_path(path, prev_tag, task_type)
        return None

    def block_node(self, node: int, reason: str = ""):
        """Đánh dấu node bị chặn trong planner graph."""
        ctx = self.ctx
        if ctx.planner.graph.has_node(node):
            for u, v in list(ctx.planner.graph.edges(node)):
                ctx.planner.graph[u][v]['allowed'] = False
            for u, v in list(ctx.planner.graph.in_edges(node)):
                ctx.planner.graph[u][v]['allowed'] = False
            print(f"[REROUTER] Node {node} blocked: {reason}")

    def unblock_node(self, node: int):
        """Gỡ block node."""
        ctx = self.ctx
        if ctx.planner.graph.has_node(node):
            for u, v in list(ctx.planner.graph.edges(node)):
                ctx.planner.graph[u][v]['allowed'] = True
            for u, v in list(ctx.planner.graph.in_edges(node)):
                ctx.planner.graph[u][v]['allowed'] = True
            print(f"[REROUTER] Node {node} unblocked.")
