"""
traffic/conflict_manager.py  — 2.4 Conflict Management
--------------------------------------------------------
Migrate từ:
  whca_planner.py    — WHCAPlanner, AGVPlan, ConflictInfo (toàn bộ)
  rolling_replanner.py — RollingRePlanner (toàn bộ)
"""
from __future__ import annotations
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.context import AppContext

# ─── Priority Mapping ─────────────────────────────────────────────────────────
MISSION_PRIORITY = {
    "delivery":                1,
    "pickup":                  2,
    "return_reversing_charge": 3,
    "return_charge":           3,
    "homing_search":           4,
    "idle":                   99,
}

STEP_TOLERANCE = 2

# Soft-avoid penalty dùng trong RollingRePlanner
SOFT_PENALTY_CURRENT = 80
SOFT_PENALTY_NEXT    = 50
REPLAN_COOLDOWN      = 2.0


# ═══════════════════════════════════════════════════════════════════════
# Data classes (migrate từ whca_planner.py)
# ═══════════════════════════════════════════════════════════════════════

class AGVPlan:
    """Kế hoạch di chuyển của 1 AGV trong cửa sổ nhìn trước."""

    def __init__(self, agv_id, path, priority, task_type):
        self.agv_id     = agv_id
        self.path       = list(path)
        self.priority   = priority
        self.task_type  = task_type
        self.updated_at = time.time()

    def step_of(self, node_id):
        try:
            return self.path.index(node_id)
        except ValueError:
            return None

    def node_set(self):
        return set(self.path)


class ConflictInfo:
    """Mô tả 1 xung đột giữa 2 AGV."""

    def __init__(self, node_id, my_step, other_id, other_step):
        self.node_id    = node_id
        self.my_step    = my_step
        self.other_id   = other_id
        self.other_step = other_step
        self.step_diff  = abs(my_step - other_step)
        self.is_headon   = False
        self.headon_edge = None

    def __repr__(self):
        kind = "HeadOn" if self.is_headon else "Conflict"
        return (f"{kind}(node={self.node_id}, me@{self.my_step}, "
                f"{self.other_id}@{self.other_step}, diff={self.step_diff})")


# ═══════════════════════════════════════════════════════════════════════
# WHCAPlanner (migrate từ whca_planner.py)
# ═══════════════════════════════════════════════════════════════════════

class WHCAPlanner:
    """
    Planner phát hiện xung đột proactive theo cửa sổ thời gian.

    Interface:
        update_plan(agv)
        should_hold(agv_id) → (bool, reason_str)
        clear_plan(agv_id)
        get_all_conflicts() → dict
    """

    def __init__(self, ctx: "AppContext | None" = None, lookahead: int = 6,
                 step_tolerance: int = STEP_TOLERANCE):
        self.ctx            = ctx
        self.window         = lookahead
        self.step_tolerance = step_tolerance
        self._plans: dict   = {}   # agv_id → AGVPlan

    # ── Cập nhật plan ─────────────────────────────────────────────────────────
    def update_plan(self, agv):
        if not agv.is_navigating or not agv.full_path or not agv.current_tag:
            self._plans.pop(agv.id, None)
            return
        if agv.current_tag not in agv.full_path:
            return
        try:
            idx = agv.full_path.index(agv.current_tag)
        except ValueError:
            return
        remaining = agv.full_path[idx: idx + self.window + 1]
        priority  = MISSION_PRIORITY.get(agv.current_task_type, 99)
        self._plans[agv.id] = AGVPlan(
            agv_id    = agv.id,
            path      = remaining,
            priority  = priority,
            task_type = agv.current_task_type,
        )

    def clear_plan(self, agv_id: str):
        self._plans.pop(agv_id, None)

    # ── Phát hiện xung đột ────────────────────────────────────────────────────
    def get_conflicts(self, agv_id: str) -> list:
        my_plan = self._plans.get(agv_id)
        if not my_plan:
            return []

        conflicts   = []
        seen_headon = set()

        for other_id, other_plan in self._plans.items():
            if other_id == agv_id:
                continue

            # 1. Node conflicts
            common_nodes = my_plan.node_set() & other_plan.node_set()
            for node in common_nodes:
                my_step    = my_plan.step_of(node)
                other_step = other_plan.step_of(node)
                if my_step is None or other_step is None:
                    continue
                if abs(my_step - other_step) <= self.step_tolerance:
                    conflicts.append(ConflictInfo(node, my_step, other_id, other_step))

            # 2. Head-on edge conflicts
            for k1 in range(len(my_plan.path) - 1):
                u1, v1 = my_plan.path[k1], my_plan.path[k1 + 1]
                for k2 in range(len(other_plan.path) - 1):
                    u2, v2 = other_plan.path[k2], other_plan.path[k2 + 1]
                    if u1 == v2 and v1 == u2:
                        my_s    = k1 + 1
                        other_s = k2
                        key = (min(agv_id, other_id), max(agv_id, other_id), u1, v1)
                        if key not in seen_headon and abs(my_s - other_s) <= self.step_tolerance + 1:
                            seen_headon.add(key)
                            c = ConflictInfo(v1, my_s, other_id, other_s)
                            c.is_headon   = True
                            c.headon_edge = (u1, v1)
                            conflicts.append(c)

        return sorted(conflicts, key=lambda c: c.my_step)

    def should_hold(self, agv_id: str) -> tuple:
        my_plan = self._plans.get(agv_id)
        if not my_plan:
            return False, ""

        conflicts = self.get_conflicts(agv_id)
        if not conflicts:
            return False, ""

        hold_threshold   = self.window // 2 + 1
        headon_threshold = hold_threshold + 1

        for c in conflicts:
            other_plan = self._plans.get(c.other_id)
            if not other_plan:
                continue
            threshold    = headon_threshold if getattr(c, 'is_headon', False) else hold_threshold
            close_enough = (c.my_step <= threshold)
            if not close_enough:
                continue
            kind = "HEAD-ON" if getattr(c, 'is_headon', False) else "node"
            if my_plan.priority > other_plan.priority:
                reason = (f"{kind} {c.node_id} xung đột với {c.other_id} "
                          f"[tôi=bước {c.my_step}/{my_plan.task_type}, "
                          f"họ=bước {c.other_step}/{other_plan.task_type}]")
                return True, reason
            if (my_plan.priority == other_plan.priority
                    and my_plan.updated_at > other_plan.updated_at):
                reason = (f"{kind} {c.node_id} xung đột với {c.other_id} "
                          f"[cùng priority, tôi={my_plan.task_type} nhường]")
                return True, reason

        return False, ""

    def get_conflict_nodes(self, agv_id: str) -> list:
        my_plan = self._plans.get(agv_id)
        if not my_plan:
            return []
        result, seen = [], set()
        for c in self.get_conflicts(agv_id):
            other = self._plans.get(c.other_id)
            if not other:
                continue
            must_yield = (
                my_plan.priority > other.priority or
                (my_plan.priority == other.priority and
                 my_plan.updated_at > other.updated_at)
            )
            if must_yield and c.node_id not in seen:
                seen.add(c.node_id)
                result.append(c.node_id)
        return result

    # ── Debug ─────────────────────────────────────────────────────────────────
    def get_all_conflicts(self) -> dict:
        result = {}
        seen   = set()
        for agv_id in list(self._plans.keys()):
            for c in self.get_conflicts(agv_id):
                pair = tuple(sorted([agv_id, c.other_id]))
                if pair not in seen:
                    seen.add(pair)
                    result.setdefault(agv_id, []).append(
                        (c.node_id, c.other_id, c.step_diff))
        return result

    def get_status_for_ui(self) -> list:
        result = []
        seen   = set()
        for agv_id in list(self._plans.keys()):
            for c in self.get_conflicts(agv_id):
                pair = tuple(sorted([agv_id, c.other_id]))
                if pair not in seen:
                    seen.add(pair)
                    result.append({
                        "agv1":      agv_id,
                        "agv2":      c.other_id,
                        "node":      c.node_id,
                        "step_diff": c.step_diff,
                    })
        return result

    def print_status(self):
        print("─" * 60)
        print(f"[WHCA*] Plans ({len(self._plans)} AGVs, window={self.window}):")
        for agv_id, plan in self._plans.items():
            hold, _ = self.should_hold(agv_id)
            flag = " ⏸HOLD" if hold else ""
            print(f"  {agv_id} [{plan.task_type}/p{plan.priority}]{flag}: {plan.path}")
        all_c = self.get_all_conflicts()
        if all_c:
            print("[WHCA*] ⚠ CONFLICTS:")
            for agv_id, cs in all_c.items():
                for node, other, diff in cs:
                    print(f"  {agv_id} ↔ {other} tại node {node} (diff={diff} bước)")
        else:
            print("[WHCA*] ✓ Không có xung đột.")
        print("─" * 60)


# ═══════════════════════════════════════════════════════════════════════
# RollingRePlanner (migrate từ rolling_replanner.py)
# ═══════════════════════════════════════════════════════════════════════

class RollingRePlanner:
    """
    Re-plan thời gian thực khi phát hiện xung đột đầu-đuôi hoặc đổi chỗ.
    Chạy TRƯỚC WHCA* trong traffic loop để xử lý xung đột tức thì.
    """

    def __init__(self, ctx: "AppContext | None" = None):
        self.ctx            = ctx
        self._last_replan: dict = {}   # agv_id → timestamp

    # ── Phát hiện xung đột ────────────────────────────────────────────────────
    def detect_conflicts(self, state: dict) -> list:
        """
        Phát hiện xung đột từ fleet state snapshot.
        Trả về list (agv_id_A, agv_id_B, kind) với kind = "headon" | "swap".
        """
        conflicts = []
        seen      = set()
        ids       = list(state.keys())

        for i, aid in enumerate(ids):
            a = state[aid]
            if not a["is_navigating"]:
                continue
            a_cur  = a["current_tag"]
            a_next = a["next_tag"]

            for j in range(i + 1, len(ids)):
                bid = ids[j]
                b   = state[bid]
                if not b["is_navigating"]:
                    continue
                b_cur  = b["current_tag"]
                b_next = b["next_tag"]

                pair = (min(aid, bid), max(aid, bid))
                if pair in seen:
                    continue

                # HEAD-ON
                if (a_cur is not None and a_next is not None
                        and b_cur is not None and b_next is not None
                        and a_cur == b_next and a_next == b_cur):
                    seen.add(pair)
                    conflicts.append((aid, bid, "headon"))
                    continue

                # SWAP
                if (a_next is not None and b_cur is not None
                        and a_next == b_cur
                        and b_next is not None and b_next == a_cur):
                    seen.add(pair)
                    conflicts.append((aid, bid, "swap"))

        return conflicts

    # ── Quyết định ai nhường ──────────────────────────────────────────────────
    def try_replan(self, agv_a, agv_b, traffic_mgr, agv_list) -> bool:
        prio_a = MISSION_PRIORITY.get(agv_a.current_task_type, 99)
        prio_b = MISSION_PRIORITY.get(agv_b.current_task_type, 99)

        if prio_a < prio_b:
            yield_agv, other_agv = agv_b, agv_a
        elif prio_b < prio_a:
            yield_agv, other_agv = agv_a, agv_b
        else:
            ta = agv_a.stats.get("start_time", 0)
            tb = agv_b.stats.get("start_time", 0)
            yield_agv, other_agv = (agv_b, agv_a) if tb > ta else (agv_a, agv_b)

        return self._do_replan(yield_agv, other_agv, traffic_mgr, agv_list)

    def _do_replan(self, yield_agv, priority_agv, traffic_mgr, agv_list) -> bool:
        agv_id = yield_agv.id
        now    = time.time()
        if now - self._last_replan.get(agv_id, 0) < REPLAN_COOLDOWN:
            return False
        if not yield_agv.full_path or not yield_agv.current_tag:
            return False
        target = yield_agv.full_path[-1]
        if yield_agv.current_tag == target:
            return False

        soft_avoid = {}
        for agv in agv_list:
            if agv.id == agv_id:
                continue
            if agv.current_tag:
                soft_avoid[agv.current_tag] = SOFT_PENALTY_CURRENT
            nt = agv.next_tag
            if nt and nt not in soft_avoid:
                soft_avoid[nt] = SOFT_PENALTY_NEXT

        new_path = traffic_mgr.find_path_smart(
            yield_agv.current_tag, target,
            prev_node  = yield_agv.prev_tag,
            soft_avoid = soft_avoid,
        )

        if new_path and new_path != yield_agv.full_path:
            print(f"[ROLLING] ↩ {agv_id}: re-plan "
                  f"{yield_agv.current_tag}→{target} "
                  f"(avoid {priority_agv.id}@{priority_agv.current_tag}) "
                  f"→ {new_path}")
            yield_agv.set_path(new_path, traffic_mgr.graph, yield_agv.current_task_type)
            self._last_replan[agv_id] = now
            return True

        print(f"[ROLLING] ⚠ {agv_id}: không tìm được đường thay thế (giữ WHCA* xử lý)")
        return False

    # ── Re-plan tại tag mới ───────────────────────────────────────────────────
    def replan_at_tag(self, agv, agv_list, traffic_mgr):
        if not agv.is_navigating or not agv.full_path or not agv.current_tag:
            return
        try:
            idx = agv.full_path.index(agv.current_tag)
        except ValueError:
            return
        if idx >= len(agv.full_path) - 2:
            return
        target = agv.full_path[-1]
        now    = time.time()
        if now - self._last_replan.get(agv.id, 0) < REPLAN_COOLDOWN:
            return

        soft_avoid = {}
        for other in agv_list:
            if other.id == agv.id:
                continue
            if other.current_tag:
                soft_avoid[other.current_tag] = SOFT_PENALTY_CURRENT
            nt = other.next_tag
            if nt and nt not in soft_avoid:
                soft_avoid[nt] = SOFT_PENALTY_NEXT

        new_path = traffic_mgr.find_path_smart(
            agv.current_tag, target,
            prev_node  = agv.prev_tag,
            soft_avoid = soft_avoid,
        )

        if new_path and new_path != agv.full_path[idx:]:
            print(f"[ROLLING@TAG] ↩ {agv.id} tại {agv.current_tag}: path cập nhật → {new_path}")
            agv.full_path = new_path
            self._last_replan[agv.id] = now

    # ── Edge conflict check ───────────────────────────────────────────────────
    @staticmethod
    def check_edge_conflict(agv, agv_list) -> tuple:
        my_cur  = agv.current_tag
        my_next = agv.next_tag
        if not my_cur or not my_next:
            return False, None
        for other in agv_list:
            if other.id == agv.id or not other.is_navigating:
                continue
            if other.current_tag == my_next and other.next_tag == my_cur:
                return True, other
        return False, None

    # ── Reverse-and-reroute (head-on mid-edge) ───────────────────────────────
    def try_reverse_replan(self, agv_a, agv_b, traffic_mgr, agv_list) -> bool:
        """
        Khi phát hiện HEAD-ON mid-edge: lệnh AGV priority thấp hơn lùi về prev_tag,
        sau đó tính path mới tránh cạnh bị conflict.

        Điều kiện kích hoạt:
          - Cả 2 AGV đang navigating
          - yield_agv có prev_tag (biết cạnh đang đi)
          - Tìm được đường mới tránh cạnh head-on
        """
        prio_a = MISSION_PRIORITY.get(agv_a.current_task_type, 99)
        prio_b = MISSION_PRIORITY.get(agv_b.current_task_type, 99)

        if prio_a < prio_b:
            yield_agv, priority_agv = agv_b, agv_a
        elif prio_b < prio_a:
            yield_agv, priority_agv = agv_a, agv_b
        else:
            # Cùng priority: AGV nào được dispatch sau thì nhường
            ta = agv_a.stats.get("start_time", 0)
            tb = agv_b.stats.get("start_time", 0)
            yield_agv, priority_agv = (agv_b, agv_a) if tb > ta else (agv_a, agv_b)

        agv_id  = yield_agv.id
        cur_tag = yield_agv.current_tag
        prev_tag = yield_agv.prev_tag

        # Cần biết cạnh để lùi về
        if not prev_tag or not cur_tag or prev_tag == cur_tag:
            return False

        # Kiểm tra cooldown
        now = time.time()
        if now - self._last_replan.get(agv_id, 0) < REPLAN_COOLDOWN:
            return False

        if not yield_agv.full_path:
            return False

        target = yield_agv.full_path[-1]
        if not target or target == prev_tag:
            return False

        # Tính path mới từ prev_tag, hard-block cạnh prev_tag→cur_tag (cạnh head-on)
        soft_avoid = {}
        for agv in agv_list:
            if agv.id == agv_id:
                continue
            if agv.current_tag:
                soft_avoid[agv.current_tag] = SOFT_PENALTY_CURRENT
            nt = getattr(agv, 'next_tag', None)
            if nt and nt not in soft_avoid:
                soft_avoid[nt] = SOFT_PENALTY_NEXT

        new_path = traffic_mgr.find_path_avoiding_edges(
            start_node  = prev_tag,
            end_node    = target,
            avoid_edges = [(prev_tag, cur_tag)],   # hard-block cạnh head-on
            prev_node   = None,
            soft_avoid  = soft_avoid,
        )

        if not new_path:
            print(f"[REVERSE] ⚠ {agv_id}: không tìm được path thay thế từ {prev_tag}→{target}")
            return False

        # Cập nhật path và gửi lệnh lùi
        yield_agv.full_path = new_path
        if hasattr(yield_agv, 'send_reverse_to_node'):
            yield_agv.send_reverse_to_node(prev_tag)
            self._last_replan[agv_id] = now
            print(f"[REVERSE+REROUTE] ↩ {agv_id}: lùi {cur_tag}→{prev_tag}, "
                  f"path mới tránh cạnh ({prev_tag}→{cur_tag}): {new_path}")
            return True

        return False

    # ── Tick (gọi từ traffic loop mỗi 500ms) ─────────────────────────────────
    def tick(self, agv_list, traffic_mgr) -> int:
        if len(agv_list) < 2:
            return 0
        from traffic.fleet_state import get_fleet_state
        state     = get_fleet_state(agv_list)
        conflicts = self.detect_conflicts(state)
        replanned = 0
        agv_map   = {agv.id: agv for agv in agv_list}
        for aid, bid, kind in conflicts:
            agv_a = agv_map.get(aid)
            agv_b = agv_map.get(bid)
            if not agv_a or not agv_b:
                continue
            print(f"[ROLLING] ⚡ {kind.upper()} conflict: {aid}({agv_a.current_tag}→{agv_a.next_tag}) "
                  f"↔ {bid}({agv_b.current_tag}→{agv_b.next_tag})")

            if kind == "headon":
                # HEAD-ON: ưu tiên lùi edge + reroute thay vì chỉ replan tại node
                if self.try_reverse_replan(agv_a, agv_b, traffic_mgr, agv_list):
                    replanned += 1
                    continue
                # Fallback: replan thông thường từ current_tag (WHCA* sẽ hold)
                if self.try_replan(agv_a, agv_b, traffic_mgr, agv_list):
                    replanned += 1
            else:
                # SWAP: replan thông thường
                if self.try_replan(agv_a, agv_b, traffic_mgr, agv_list):
                    replanned += 1
        return replanned
