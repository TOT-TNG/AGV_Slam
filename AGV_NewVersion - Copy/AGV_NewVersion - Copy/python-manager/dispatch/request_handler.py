"""
dispatch/request_handler.py  — 1.1 Request Handler
----------------------------------------------------
Migrate từ main.py:
  - order_queue (list)
  - remove_from_queue()
  - _dispatch_next_team()
  - run_hmi_handler()  (toàn bộ business logic vòng lặp 1s)
  - _get_dynamic_target()
"""
from __future__ import annotations
import networkx as nx
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.context import AppContext


class RequestHandler:
    """
    Quản lý vòng đời mission: nhận → hàng đợi → assign → dispatch.
    """

    def __init__(self, ctx: AppContext):
        self.ctx = ctx
        self.order_queue: list[int] = []

    # ── Public API ──────────────────────────────────────────────────────

    def add_to_queue(self, team_id: int):
        """Thêm tổ vào hàng đợi nếu chưa có."""
        if team_id not in self.order_queue:
            self.order_queue.append(team_id)
            print(f"Added Team {team_id} to Queue. Current Queue: {self.order_queue}")
        else:
            print(f"Team {team_id} already in queue.")

    def remove_from_queue(self, team_id: int):
        """Xóa tất cả instance của team_id khỏi hàng đợi."""
        if team_id in self.order_queue:
            self.order_queue = [t for t in self.order_queue if t != team_id]
            print(f"Removed Team {team_id} from Queue.")

    # ── Dispatch helpers ────────────────────────────────────────────────

    def _dispatch_next_team(self, agv, station_cfg_list: list) -> bool:
        """Tìm tổ gần nhất trong danh sách còn lại, gửi lệnh đến đó.
        Trả về True nếu thành công, False nếu hết tổ hoặc không tìm được đường."""
        ctx = self.ctx
        remaining = getattr(agv, '_remaining_delivery_teams', [])
        if not remaining:
            return False
        # Tìm tổ có đường đi ngắn nhất từ vị trí hiện tại
        best_id, best_len = None, float('inf')
        for tid in remaining:
            cfg = next((t for t in station_cfg_list if t['id'] == tid), None)
            if not cfg:
                continue
            path = ctx.planner.find_path(agv.current_tag, cfg['delivery'])
            plen = len(path) if path else float('inf')
            if plen < best_len:
                best_len, best_id = plen, tid
        if best_id is None:
            return False
        remaining.remove(best_id)
        self.remove_from_queue(best_id)
        agv._current_delivery_team = best_id
        team_cfg = next((t for t in station_cfg_list if t['id'] == best_id))
        _prev = agv.prev_tag if agv.prev_tag > 0 else None
        print(f"[DELIVERY] {agv.id}: dispatch Tổ {best_id} từ tag={agv.current_tag} prev={_prev} "
              f"→ delivery tag={team_cfg['delivery']}")
        path = ctx.planner.find_path_directed(agv.current_tag, team_cfg['delivery'], prev_node=_prev)
        if path:
            precomp_steps, sim_path = self._run_dry_run_for_path(path, _prev, "delivery")
            if sim_path and sim_path != list(path):
                path = sim_path
            print(f"[DELIVERY] {agv.id} plan path: {path}")
            if precomp_steps:
                for _i, (_tag, _step) in enumerate(zip(path, precomp_steps)):
                    _pre = [a.get('code') for a in _step.get('actions', [])]
                    _nav = _step.get('nav_action', {}).get('code', '?')
                    _dest = _step.get('is_destination', False)
                    print(f"[DELIVERY]   step[{_i}] tag={_tag} pre={_pre} nav={_nav} dest={_dest}")
            agv.set_path(path, ctx.planner.graph, task_type="delivery",
                         precomp_steps=precomp_steps)
            agv._mission_dest_node = team_cfg['delivery']
            print(f"[DELIVERY] {agv.id} → Tổ {best_id} (thẻ {team_cfg['delivery']}), "
                  f"còn lại: {remaining}")
            return True
        print(f"[DELIVERY] {agv.id}: không tìm được đường đến Tổ {best_id}, bỏ qua.")
        agv._current_delivery_team = None
        return self._dispatch_next_team(agv, station_cfg_list)

    # ── Dry-run helpers (delegates to sim_engine) ───────────────────────

    def _run_dry_run_for_path(self, path, prev_tag, task_type,
                               end_tag_override=None, facing_tag=None):
        """Chạy SimulationEngine.dry_run để lấy path + lệnh giống simulation panel.
        Trả về (steps, sim_path) hoặc (None, None) nếu lỗi."""
        sim = getattr(self.ctx, 'sim_engine', None)
        if not sim or not path:
            return None, None
        _end = end_tag_override if end_tag_override is not None else path[-1]
        try:
            steps, err = sim.dry_run(
                start_tag  = path[0],
                prev_tag   = prev_tag,
                end_tag    = _end,
                task_type  = task_type,
                facing_tag = facing_tag,
            )
            if err:
                print(f"[PRECOMP] dry_run lỗi: {err} → dùng tính toán thông thường")
                return None, None
            sim_path = [s['tag'] for s in steps]
            if sim_path != list(path):
                print(f"[PRECOMP] ⚠ dry_run path KHÁC dispatch path!")
                print(f"[PRECOMP]   dispatch: {list(path)}")
                print(f"[PRECOMP]   sim:      {sim_path}")
                print(f"[PRECOMP]   → Dùng path simulation (chính xác hơn)")
            return steps, sim_path
        except Exception as e:
            import traceback
            print(f"[PRECOMP] dry_run exception: {e} → dùng tính toán thông thường")
            traceback.print_exc()
            return None, None

    def _run_dry_run_for_exact_path(self, path, prev_tag, task_type):
        """Chạy SimulationEngine.dry_run_for_path cho path đã xác định.
        Trả về steps hoặc None nếu lỗi."""
        sim = getattr(self.ctx, 'sim_engine', None)
        if not sim or not path:
            return None
        try:
            steps, err = sim.dry_run_for_path(
                path      = list(path),
                prev_tag  = prev_tag,
                task_type = task_type,
            )
            if err:
                print(f"[PRECOMP] dry_run_for_path lỗi: {err}")
                return None
            return steps
        except Exception as e:
            import traceback
            print(f"[PRECOMP] dry_run_for_path exception: {e}")
            traceback.print_exc()
            return None

    # ── Re-route after off-route ────────────────────────────────────────

    def _rerout_after_off_route(self, agv, station_cfg_list: list):
        """Định tuyến lại sau khi phát hiện xe đi sai đường (off_route)."""
        ctx = self.ctx
        agv.is_navigating = False
        agv.full_path = []

        dest = None
        if agv.task_lifecycle == "picking":
            dest = getattr(agv, '_pickup_target_node', None)
        elif agv.task_lifecycle == "delivering":
            if getattr(agv, '_remaining_delivery_teams', []):
                if self._dispatch_next_team(agv, station_cfg_list):
                    print(f"[OFF-ROUTE] {agv.id}: đã re-route → tổ tiếp theo")
                    return
            dest = getattr(agv, '_mission_dest_node', None)

        if dest and ctx.planner.graph.has_node(dest):
            _prev = agv.prev_tag if agv.prev_tag > 0 else None
            from_node = agv.current_tag
            if not ctx.planner.graph.has_node(from_node):
                print(f"[OFF-ROUTE] {agv.id}: current_tag {from_node} không có trên map → thử từ prev_tag {_prev}")
                from_node = _prev
                _prev = None
            if from_node and ctx.planner.graph.has_node(from_node):
                path = ctx.planner.find_path_directed(from_node, dest, prev_node=_prev)
                if path:
                    task_t = "pickup" if agv.task_lifecycle == "picking" else "delivery"
                    precomp_steps, sim_path = self._run_dry_run_for_path(path, _prev, task_t)
                    if sim_path and sim_path != list(path):
                        path = sim_path
                    agv.set_path(path, ctx.planner.graph, task_type=task_t,
                                 precomp_steps=precomp_steps)
                    print(f"[OFF-ROUTE] {agv.id}: re-route {from_node}→{dest} OK: {path}")
                    return
                print(f"[OFF-ROUTE] {agv.id}: không tìm được đường từ {from_node}→{dest}")

        print(f"[OFF-ROUTE] {agv.id}: không xác định được đích → về sạc (lifecycle={agv.task_lifecycle})")
        agv.pending_request = "return"

    # ── Main event loop ─────────────────────────────────────────────────

    def run_hmi_handler(self):
        """
        Xử lý các yêu cầu từ AGV gửi lên (Nút bấm, Xác nhận hoàn thành)
        và logic hàng đợi (Queue). Gọi lặp mỗi 1s từ GUI.
        """
        ctx = self.ctx
        config          = ctx.config
        agv_list        = ctx.agv_list
        planner         = ctx.planner
        zone_mgr        = getattr(ctx, 'zone_mgr', None)
        workflow_engine = getattr(ctx, 'workflow_engine', None)
        mqtt_client     = ctx.mqtt
        mqtt_connected  = getattr(ctx, 'mqtt_connected', False)

        home_node        = config.get('home_node_id', 10)
        station_cfg_list = config.get('station_config', [])

        # ── Workflow Engine: kích hoạt rule khi AGV đến tag mới ──────────
        if workflow_engine:
            for agv in agv_list:
                if agv.current_tag > 0:
                    last_wf = getattr(agv, '_last_wf_tag', -1)
                    if agv.current_tag != last_wf:
                        agv._last_wf_tag = agv.current_tag
                        workflow_engine.trigger(agv, agv.current_tag, mqtt_client)

        # 1. Xử lý yêu cầu từ AGV
        for agv in agv_list:
            # --- Post-Homing ---
            if agv.post_homing_action and agv.current_tag > 0:
                in_plan      = bool(agv.full_path) and agv.current_tag in agv.full_path
                prev_in_plan = bool(agv.full_path) and agv.prev_tag > 0 and agv.prev_tag in agv.full_path
                if in_plan:
                    print(f"[HOMING] {agv.id}: gặp thẻ homing {agv.current_tag} → kích hoạt '{agv.post_homing_action}'")
                    agv.send_command("run")
                    agv.pending_request    = agv.post_homing_action
                    agv.post_homing_action = None
                elif agv.prev_tag > 0 and not prev_in_plan:
                    print(f"[HOMING DISCOVER] {agv.id}: tìm thấy tại {agv.prev_tag}→{agv.current_tag}")
                    agv.send_command("stop")
                    agv.is_navigating      = False
                    agv.full_path          = []
                    agv.pending_request    = agv.post_homing_action
                    agv.post_homing_action = None

            if not agv.pending_request:
                continue

            req = agv.pending_request

            # Workflow blocking check
            MOVEMENT_EVENTS = {"confirm", "return", "supply", "continue", "station"}
            if workflow_engine and req in MOVEMENT_EVENTS and workflow_engine.is_blocking(agv.id):
                print(f"[WF] {agv.id}: workflow blocking → defer '{req}'")
                continue

            targets = agv.selected_targets
            agv.pending_request  = None
            agv.selected_targets = []
            print(f"EVENT from {agv.id}: {req} | Targets: {targets}")
            agv.send_server_ack(req)

            # --- line_X: nút bấm tổ ---
            if req.startswith("line_"):
                try:
                    team_num = int(req.split("_")[1])
                    if agv.task_lifecycle == "picking":
                        if team_num not in agv.selected_targets:
                            agv.selected_targets.append(team_num)
                        else:
                            agv.selected_targets.remove(team_num)
                    else:
                        if team_num not in self.order_queue:
                            self.order_queue.append(team_num)
                            print(f"[HMI] Team {team_num} added to order_queue by {agv.id}.")
                        else:
                            print(f"[HMI] Team {team_num} already in order_queue.")
                except (ValueError, IndexError):
                    print(f"WARNING: Unrecognised line event: {req}")
                continue

            # --- arrived_wait_sys ---
            if req == "arrived_wait_sys":
                if agv.current_tag <= 0 and agv.post_homing_action:
                    chargers = config.get('chargers', [])
                    assigned_charger = next((c for c in chargers if c.get('assigned_agv') == agv.id), None)
                    retry_path = [n for n in (assigned_charger or {}).get('homing_path', [])
                                  if planner.graph.has_node(n)]
                    if retry_path:
                        print(f"WARNING: {agv.id} finished homing but still lost. Resending homing path...")
                        agv.set_path(retry_path, planner.graph, task_type="homing_search")
                    else:
                        print(f"WARNING: {agv.id} still lost. Không có homing path hợp lệ để retry.")
                        agv.post_homing_action = None
                    continue

                if agv._pre_return_charger:
                    charger_cfg = agv._pre_return_charger
                    agv._pre_return_charger = None
                    cn = charger_cfg['node_id']
                    short_rev = planner.find_path(cn, agv.current_tag)
                    if short_rev:
                        rev = list(reversed(short_rev))
                        print(f"[RETURN] {agv.id}: đến approach node {agv.current_tag} → lùi vào trạm {cn}: {rev}")
                        slow_sp = int(charger_cfg.get('slow_speed', 40))
                        _pc_rev = self._run_dry_run_for_exact_path(rev, None, "return_reversing_charge")
                        agv.set_path(rev, planner.graph, task_type="return_reversing_charge",
                                     precomp_steps=_pc_rev)
                        if len(rev) >= 2:
                            agv.speed_overrides[rev[-2]] = slow_sp
                    else:
                        print(f"ERROR: {agv.id}: không tìm được đường lùi từ {agv.current_tag} vào {cn}")
                    continue

                bypass_zone = (zone_mgr.get_zone_for_bypass_slot(agv.current_tag)
                               if zone_mgr and zone_mgr.is_enabled() else None)
                if bypass_zone and agv.bypass_dest:
                    agv.bypass_holding = True
                    agv.bypass_zone_id  = bypass_zone.id
                    agv.is_navigating   = False
                    print(f"[BYPASS] {agv.id} đã vào slot {agv.current_tag} trong '{bypass_zone.name}', chờ lane clear.")
                    continue

                chargers = config.get('chargers', [])
                is_at_charger = any(agv.current_tag == c.get('node_id') for c in chargers)
                if is_at_charger:
                    agv.task_lifecycle = "free"
                    agv.is_navigating  = False
                    agv.send_reset_team_btns()
                    print(f"{agv.id} arrived at CHARGER (node {agv.current_tag}). Lifecycle: free.")
                elif agv.task_lifecycle == "returning":
                    print(f"{agv.id} mid-return WAIT_SYS @ tag {agv.current_tag} — giữ lifecycle=returning.")
                else:
                    agv.task_lifecycle = "picking"
                    pending = getattr(agv, '_pending_delivery_team', None)
                    if pending is not None and pending not in agv.selected_targets:
                        agv.selected_targets.append(pending)
                        print(f"[SUPPLY] {agv.id} pre-select Tổ {pending} (auto-dispatch)")
                    print(f"{agv.id} arrived at WAIT POINT (node {agv.current_tag}). Lifecycle: picking.")
                continue

            # --- arrived_wait_user ---
            if req == "arrived_wait_user":
                print(f"{agv.id} arrived at DELIVERY POINT (node {agv.current_tag}). Waiting for user.")
                agv.task_lifecycle = "delivering"
                continue

            # --- off_route ---
            if req == "off_route":
                print(f"[OFF-ROUTE] {agv.id}: tag={agv.current_tag} prev={agv.prev_tag} "
                      f"lifecycle={agv.task_lifecycle} dest={getattr(agv,'_mission_dest_node',None)}")
                agv.send_server_ack("off_route")
                self._rerout_after_off_route(agv, station_cfg_list)
                continue

            # --- door_blocked ---
            if req == "door_blocked":
                from config_mgmt.settings_io import find_door_cfg
                door = find_door_cfg(config, agv.current_tag, agv.prev_tag)
                if door:
                    topic   = door.get('relay_topic', '')
                    payload = str(door.get('relay_on_payload', '1'))
                    if topic and mqtt_connected:
                        mqtt_client.publish(topic, payload)
                        print(f"[DOOR] {agv.id} @ tag {agv.current_tag}: blocked → relay ON ({topic}={payload})")
                    elif not topic:
                        print(f"[DOOR] {agv.id} @ tag {agv.current_tag}: relay_topic chưa cấu hình")
                else:
                    print(f"[DOOR] {agv.id} @ tag {agv.current_tag}: door_blocked — không tìm thấy config")
                continue

            # --- door_clear ---
            if req == "door_clear":
                from config_mgmt.settings_io import find_door_cfg
                door = find_door_cfg(config, agv.current_tag, agv.prev_tag)
                if door:
                    topic   = door.get('relay_topic', '')
                    payload = str(door.get('relay_off_payload', '0'))
                    if topic and mqtt_connected:
                        mqtt_client.publish(topic, payload)
                        print(f"[DOOR] {agv.id} @ tag {agv.current_tag}: clear → relay OFF ({topic}={payload})")
                else:
                    print(f"[DOOR] {agv.id} @ tag {agv.current_tag}: door_clear — không tìm thấy config")
                agv.resume_from_door_hold()
                continue

            # --- Normalize ---
            if req == "supply":
                req = "confirm"
            if req == "station":
                req = "return"
            if req == "continue":
                print(f"[CONTINUE] {agv.id}: tag={agv.current_tag} lifecycle={agv.task_lifecycle} "
                      f"remaining={getattr(agv,'_remaining_delivery_teams',[])} "
                      f"cur_team={getattr(agv,'_current_delivery_team',None)}")
                if agv.task_lifecycle == "picking":
                    req = "start_delivery"
                elif agv.task_lifecycle == "delivering":
                    req = "next_delivery"
                else:
                    req = "confirm"
                    if not targets:
                        pending = getattr(agv, '_pending_delivery_team', None)
                        if pending is not None:
                            targets = [pending]
                            agv._pending_delivery_team = None

            # --- return ---
            if req == "return":
                print(f"[RETURN] {agv.id} tag={agv.current_tag} lifecycle={agv.task_lifecycle}")
                if agv.current_tag <= 0:
                    agv.post_homing_action = "return"
                    chargers = config.get('chargers', [])
                    assigned_charger = next((c for c in chargers if c.get('assigned_agv') == agv.id), None)
                    homing_beacon_path = []
                    if assigned_charger:
                        homing_beacon_path = assigned_charger.get('homing_path', [])
                        if homing_beacon_path:
                            valid_nodes = [n for n in homing_beacon_path if planner.graph.has_node(n)]
                            if len(valid_nodes) < len(homing_beacon_path):
                                invalid = [n for n in homing_beacon_path if not planner.graph.has_node(n)]
                                print(f"WARNING: Homing path có nodes không tồn tại: {invalid}. Bỏ qua.")
                            homing_beacon_path = valid_nodes
                            if homing_beacon_path:
                                print(f"INFO: {agv.id} is lost. Homing → Trạm '{assigned_charger.get('name', assigned_charger['id'])}', path={homing_beacon_path}")
                        else:
                            print(f"WARNING: {agv.id} is lost. Trạm '{assigned_charger.get('name', '')}' chưa cấu hình 'Homing Path'.")
                    else:
                        print(f"WARNING: {agv.id} is lost. Chưa có trạm nào được phân công.")
                    if homing_beacon_path:
                        agv.set_path(homing_beacon_path, planner.graph, task_type="homing_search")
                    else:
                        agv.post_homing_action = None
                    continue

                chargers = config.get('chargers', [])
                if not chargers:
                    print(f"WARNING: No chargers configured. Cannot execute return command for {agv.id}.")
                    continue

                target_charger  = None
                is_reversing    = False

                # Bước 1: Reversing zone tường minh
                for charger in chargers:
                    if agv.current_tag in charger.get('reversing_zone', []):
                        target_charger = charger
                        is_reversing   = True
                        break

                # Bước 2: Assigned charger với short path ≤ 4
                if not target_charger:
                    assigned = next((c for c in chargers if c.get('assigned_agv') == agv.id), None)
                    if assigned:
                        path_test = planner.find_path(assigned['node_id'], agv.current_tag)
                        if path_test and len(path_test) <= 4:
                            target_charger = assigned
                            is_reversing   = True

                # Bước 3: Tất cả charger short path ≤ 4
                if not target_charger:
                    for charger in chargers:
                        path_test = planner.find_path(charger['node_id'], agv.current_tag)
                        if path_test and len(path_test) <= 4:
                            target_charger = charger
                            is_reversing   = True
                            break

                # Bước 4: Fallback — gần nhất forward
                if not target_charger:
                    from dispatch.robot_filter import RobotFilter
                    target_charger = RobotFilter(ctx).find_nearest_charger(agv)

                if not target_charger:
                    print(f"ERROR: Cannot find any reachable charger for {agv.id} from tag {agv.current_tag}")
                    continue

                charger_node = target_charger['node_id']
                if is_reversing and not agv.can_reverse:
                    print(f"[RETURN] {agv.id}: can_reverse=False → bỏ qua reverse mode.")
                    is_reversing = False

                if is_reversing:
                    print(f"INFO: {agv.id} reversing to Charger {target_charger.get('id')}.")
                    path_from_charger = planner.find_path(charger_node, agv.current_tag)
                    if path_from_charger:
                        _prev = agv.prev_tag if agv.prev_tag > 0 else None
                        reverse_path_full = list(reversed(path_from_charger))
                        approach_node = (reverse_path_full[1] if len(reverse_path_full) >= 2 else None)
                        first_step_bwd = False
                        if _prev and approach_node and len(reverse_path_full) >= 2:
                            first_step_bwd = planner._backward_cost(_prev, agv.current_tag, approach_node, 1) > 0
                        if first_step_bwd and approach_node and approach_node != agv.current_tag:
                            fwd_to_approach = planner.find_path_directed(
                                agv.current_tag, approach_node, prev_node=_prev)
                            if fwd_to_approach and len(fwd_to_approach) > 1:
                                print(f"[RETURN] {agv.id}: tiến đến approach node {approach_node}: {fwd_to_approach}")
                                agv._pre_return_charger = target_charger
                                _pc_s, _sim_p = self._run_dry_run_for_path(fwd_to_approach, _prev, "return_charge")
                                if _sim_p and _sim_p != list(fwd_to_approach):
                                    fwd_to_approach = _sim_p
                                agv.set_path(fwd_to_approach, planner.graph,
                                             task_type="return_charge", precomp_steps=_pc_s)
                                agv.task_lifecycle = "returning"
                                continue
                        fwd_successors = [s for s in planner.graph.successors(agv.current_tag)
                                          if s not in path_from_charger]
                        if fwd_successors:
                            path_from_charger = path_from_charger + [fwd_successors[0]]
                        reverse_path = list(reversed(path_from_charger))
                        print(f"-> Reverse path for {agv.id}: {reverse_path}")
                        _pc_rev = self._run_dry_run_for_exact_path(reverse_path, _prev, "return_reversing_charge")
                        agv.set_path(reverse_path, planner.graph,
                                     task_type="return_reversing_charge", precomp_steps=_pc_rev)
                        agv.task_lifecycle = "returning"
                        slow_sp = int(target_charger.get('slow_speed', 40))
                        if len(reverse_path) >= 2:
                            agv.speed_overrides[reverse_path[-2]] = slow_sp
                    else:
                        print(f"ERROR: {agv.id}: không tính được reverse path từ {charger_node} → {agv.current_tag}")
                else:
                    print(f"INFO: {agv.id} returning to Charger {target_charger.get('id')} (Node {charger_node}).")
                    _prev = agv.prev_tag if agv.prev_tag > 0 else None
                    path  = planner.find_path_directed(agv.current_tag, charger_node, prev_node=_prev)
                    if path:
                        print(f"-> Path to charger for {agv.id}: {path}")
                        _pc_s, _sim_p = self._run_dry_run_for_path(
                            path, _prev, "return_charge", end_tag_override=charger_node)
                        if _sim_p and _sim_p != list(path):
                            path = _sim_p
                        agv.set_path(path, planner.graph, task_type="return_charge", precomp_steps=_pc_s)
                        agv.task_lifecycle = "returning"
                        slow_sp = int(target_charger.get('slow_speed', 40))
                        if len(path) >= 2:
                            agv.speed_overrides[path[-2]] = slow_sp
                    else:
                        print(f"ERROR: Cannot find path from {agv.current_tag} to charger {charger_node}.")
                continue

            # --- start_delivery ---
            elif req == "start_delivery":
                print(f"[START_DELIVERY] {agv.id}: tag={agv.current_tag} selected={targets} "
                      f"lifecycle={agv.task_lifecycle}")
                supply_targets = list(targets)
                if not supply_targets:
                    pending = getattr(agv, '_pending_delivery_team', None)
                    if pending is not None:
                        supply_targets = [pending]
                        print(f"[DELIVERY] {agv.id}: dùng tổ pre-assign = {pending}")
                agv._pending_delivery_team = None
                if not supply_targets:
                    print(f"[DELIVERY] {agv.id}: không có tổ nào → về sạc")
                    agv.pending_request = "return"
                    continue
                for tid in supply_targets:
                    self.remove_from_queue(tid)
                agv._remaining_delivery_teams = supply_targets[:]
                agv.task_lifecycle = "delivering"
                print(f"[DELIVERY] {agv.id}: bắt đầu giao hàng cho tổ {supply_targets}")
                if not self._dispatch_next_team(agv, station_cfg_list):
                    print(f"[DELIVERY] {agv.id}: không tìm được đường đến tổ nào → về sạc")
                    agv.pending_request = "return"

            # --- next_delivery ---
            elif req == "next_delivery":
                delivered_team = getattr(agv, '_current_delivery_team', None)
                remaining      = getattr(agv, '_remaining_delivery_teams', [])
                print(f"[NEXT_DELIVERY] {agv.id}: tag={agv.current_tag} delivered={delivered_team} "
                      f"remaining={remaining} lifecycle={agv.task_lifecycle}")
                if delivered_team is not None:
                    agv.send_btn_pic(delivered_team, 27)
                    agv._current_delivery_team = None
                    print(f"[NEXT_DELIVERY] {agv.id}: xong Tổ {delivered_team} → btn pic=27")
                if remaining:
                    print(f"[NEXT_DELIVERY] {agv.id}: còn lại {remaining} → dispatch tổ tiếp")
                    if not self._dispatch_next_team(agv, station_cfg_list):
                        print(f"[NEXT_DELIVERY] {agv.id}: không tìm được đường → set pending=return")
                        agv.pending_request = "return"
                else:
                    print(f"[NEXT_DELIVERY] {agv.id}: đã giao hết tất cả tổ → set pending=return")
                    agv.pending_request = "return"
                print(f"[NEXT_DELIVERY] {agv.id}: pending_request={agv.pending_request}")

            # --- confirm (manual route building) ---
            elif req == "confirm":
                full_route   = []
                current_node = agv.current_tag
                agv.task_lifecycle = "delivering"
                if not targets:
                    targets = []
                valid_route  = True
                temp_start   = current_node
                prev_for_dir = agv.prev_tag if agv.prev_tag > 0 else None
                for team_id in targets:
                    team_cfg = next((t for t in station_cfg_list if t['id'] == team_id), None)
                    if team_cfg:
                        segment = planner.find_path_directed(
                            temp_start, team_cfg['delivery'], prev_node=prev_for_dir)
                        if segment:
                            if full_route:
                                full_route.extend(segment[1:])
                            else:
                                full_route.extend(segment)
                            temp_start   = team_cfg['delivery']
                            prev_for_dir = segment[-2] if len(segment) >= 2 else None
                            self.remove_from_queue(team_id)
                        else:
                            print(f"Error: No path to Team {team_id}")
                            valid_route = False
                            break
                bat_threshold = config.get('battery', {}).get('resume_threshold', 80)
                next_role = "wait"
                if agv.battery < bat_threshold and config.get('battery', {}).get('enabled', False):
                    next_role = "charger"
                    print(f"AGV {agv.id} Low Battery ({agv.battery}%), returning to Charger after delivery.")
                target_next   = self._get_dynamic_target(next_role, agv)
                path_to_home  = planner.find_path_directed(temp_start, target_next, prev_node=prev_for_dir)
                if path_to_home:
                    if full_route:
                        full_route.extend(path_to_home[1:])
                    else:
                        full_route.extend(path_to_home)
                if valid_route and full_route:
                    print(f"Dynamic Route for {agv.id}: {full_route}")
                    _prev_dr = agv.prev_tag if agv.prev_tag > 0 else None
                    precomp_steps, sim_path = self._run_dry_run_for_path(full_route, _prev_dr, "delivery")
                    if sim_path and sim_path != list(full_route):
                        full_route = sim_path
                    agv.set_path(full_route, planner.graph, task_type="delivery",
                                 precomp_steps=precomp_steps)

        # 2. Dispatcher: điều xe rảnh từ hàng đợi
        if self.order_queue:
            next_order_team = self.order_queue[0]
            charger_nodes   = [c.get('node_id') for c in config.get('chargers', []) if c.get('node_id')]
            valid_idle_nodes = list(set([home_node] + charger_nodes))
            candidate_agv = None
            for agv in agv_list:
                if agv.is_available(valid_idle_nodes):
                    candidate_agv = agv
                    break
            if candidate_agv:
                team_cfg = next((t for t in station_cfg_list if t['id'] == next_order_team), None)
                if team_cfg:
                    wait_node = team_cfg['wait']
                    _prev = candidate_agv.prev_tag if candidate_agv.prev_tag > 0 else None
                    if candidate_agv.current_task_type in ("return_reversing_charge", "return_charge"):
                        _prev = None
                    path = planner.find_path_directed(candidate_agv.current_tag, wait_node, prev_node=_prev)
                    if path:
                        print(f"DISPATCH: Sending {candidate_agv.id} to Wait Point of Team {next_order_team} (Node {wait_node}).")
                        precomp_steps, sim_path = self._run_dry_run_for_path(path, _prev, "pickup")
                        if sim_path and sim_path != list(path):
                            path = sim_path
                        candidate_agv.set_path(path, planner.graph, task_type="pickup",
                                               precomp_steps=precomp_steps)
                        candidate_agv._pickup_target_node    = wait_node
                        candidate_agv._mission_dest_node     = wait_node
                        candidate_agv._pending_delivery_team = next_order_team
                        candidate_agv.task_lifecycle         = "assigned"
                        self.order_queue.pop(0)
                else:
                    print(f"Config missing for Team {next_order_team}, removing from queue.")
                    self.order_queue.pop(0)

    # ── Dynamic target helper ───────────────────────────────────────────

    def _get_dynamic_target(self, role: str, requesting_agv) -> int:
        """Tìm node đích phù hợp nhất cho role (wait/charger)."""
        ctx  = self.ctx
        config   = ctx.config
        agv_list = ctx.agv_list
        planner  = ctx.planner
        candidates = planner.get_nodes_by_role(role)
        if not candidates:
            return config.get('home_node_id', 10)
        available = []
        for node in candidates:
            is_occupied = False
            for agv in agv_list:
                if agv.id == requesting_agv.id:
                    continue
                if agv.current_tag == node or (agv.full_path and agv.full_path[-1] == node):
                    is_occupied = True
                    break
            if not is_occupied:
                available.append(node)
        if not available:
            available = candidates
        best_node = available[0]
        min_dist  = 999999
        try:
            for node in available:
                dist = nx.shortest_path_length(planner.graph, requesting_agv.current_tag, node, weight='weight')
                if dist < min_dist:
                    min_dist  = dist
                    best_node = node
        except Exception:
            pass
        return best_node
