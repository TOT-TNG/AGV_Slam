"""
dispatch/robot_filter.py  — 1.2 Robot Filter
---------------------------------------------
Migrate từ main.py:
  - App.find_best_agv()         (lines ~3498–3562)
  - find_nearest_charger()      (lines ~619–639)
"""
from __future__ import annotations
import time
import networkx as nx
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.context import AppContext


class RobotFilter:
    """
    Lọc và xếp hạng AGV theo từng mission.
    """

    def __init__(self, ctx: AppContext):
        self.ctx = ctx

    def find_nearest_charger(self, agv) -> dict | None:
        """Tìm trạm sạc gần nhất (theo graph distance) cho AGV."""
        ctx      = self.ctx
        chargers = ctx.config.get('chargers', [])
        if not chargers:
            return None
        best_charger = None
        min_dist     = float('inf')
        for charger in chargers:
            try:
                dist = nx.shortest_path_length(
                    ctx.planner.graph, agv.current_tag,
                    charger['node_id'], weight='weight')
                if dist < min_dist:
                    min_dist     = dist
                    best_charger = charger
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                pass
        return best_charger

    def find_best_agv(self, target_node: int, mission: dict | None = None):
        """
        Thuật toán tìm AGV tốt nhất dựa trên trọng số (Weighted Scoring).
        Trả về (agv, reason_str).
        """
        ctx     = self.ctx
        config  = ctx.config
        weights = config.get('dispatch_weights', {"distance": 80, "idle": 20, "battery": 0})

        # 1. Lọc AGV khả dụng
        candidates = []
        for agv in ctx.agv_list:
            if (time.time() - agv.last_update) > 3.0:
                continue
            if agv.action_info != 'idle':
                continue
            if agv.error_code != 0:
                continue
            candidates.append(agv)

        if not candidates:
            return None, "No AGV available (All busy or offline)"

        # 2. Tính điểm
        scored = []
        for agv in candidates:
            score = 0

            # Khoảng cách (càng gần càng tốt)
            dist = 9999
            try:
                if agv.current_tag in ctx.planner.graph:
                    dist = nx.shortest_path_length(
                        ctx.planner.graph, source=agv.current_tag,
                        target=target_node)
            except Exception:
                pass
            norm_dist = max(0, 1 - (dist / 100.0))
            score    += norm_dist * weights.get('distance', 80)

            # Idle time / trips (ít trip → điểm cao → cân bằng tải)
            trips     = agv.stats['trips']
            norm_idle = max(0, 1 - (trips / 50.0))
            score    += norm_idle * weights.get('idle', 20)

            # Pin (cao hơn = tốt hơn)
            bat      = getattr(agv, 'battery', 100)
            norm_bat = bat / 100.0
            score   += norm_bat * weights.get('battery', 0)

            scored.append((score, agv))
            print(f"Candidate {agv.id}: Dist={dist}, Trips={trips}, Bat={bat} -> Score={score:.2f}")

        # 3. Chọn xe điểm cao nhất
        scored.sort(key=lambda x: x[0], reverse=True)
        best_agv = scored[0][1] if scored else None
        if best_agv:
            return best_agv, "OK"
        return None, "No path found for any candidate"
