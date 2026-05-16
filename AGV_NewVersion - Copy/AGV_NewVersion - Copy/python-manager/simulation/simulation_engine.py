"""
SimulationEngine — Mô phỏng lệnh điều hướng AGV (Dry Run)
Tái tạo logic set_path() + _send_segment() của AGV nhưng không gửi MQTT.
"""
import json, os, math, re, copy
from agv.agv_instance import auto_nav_action, calc_turn_angle

ACT_WAIT_SYS  = 1
ACT_WAIT_USER = 2
ACT_RUN       = 3
ACT_SPEED     = 4
ACT_TURN_R    = 5
ACT_TURN_L    = 6
ACT_DIR_FWD   = 7
ACT_DIR_BWD   = 8
ACT_LIDAR_OFF = 20
ACT_LIDAR_ON  = 21
ACT_NHAC_START    = 22
ACT_NHAC_STOP     = 23
ACT_NHAC_XIN_LIEU = 24
ACT_NHAC_MO_CUA   = 25
ACT_NHAC_XIN_RE   = 26
ACT_NHAC_TAT      = 27
ACT_BRAKE_ON      = 28
ACT_BRAKE_OFF     = 29
ACT_HOOK_RAISE    = 30
ACT_HOOK_LOWER    = 31
ACT_DEN_VANG      = 32
ACT_DEN_XANH      = 33
ACT_DEN_TAT       = 34

ACTION_CODE_TO_NAME = {
    0: "NOP", 1: "WAIT_SYS", 2: "WAIT_USER", 3: "RUN",
    4: "SPEED", 5: "TURN_R", 6: "TURN_L",
    7: "DIR_TIẾN", 8: "DIR_LÙI", 9: "ROTATE_180",
    11: "CHARGE", 20: "LIDAR_OFF", 21: "LIDAR_ON",
    22: "NHAC_START", 23: "NHAC_STOP", 24: "NHAC_XIN_LIEU",
    25: "NHAC_MO_CUA", 26: "NHAC_XIN_RE", 27: "NHAC_TAT",
    28: "BRAKE_ON", 29: "BRAKE_OFF",
    30: "HOOK_RAISE", 31: "HOOK_LOWER",
    32: "DEN_VANG", 33: "DEN_XANH", 34: "DEN_TAT",
}

ACTION_NAME_TO_CODE = {v: k for k, v in ACTION_CODE_TO_NAME.items()}
ACTION_NAME_TO_CODE.update({
    "SPEED_SLOW": 4, "SPEED_FAST": 4, "SPEED_NONE": -1,
    "TURN_LEFT": 6, "TURN_RIGHT": 5, "WAIT": 1, "STOP": 1,
})

TASK_TYPES = [
    ("pickup",                  "Đi lấy hàng (Pickup)"),
    ("delivery",                "Đi giao hàng (Delivery)"),
    ("return",                  "Về trạm chờ (Return Home)"),
    ("return_charge",           "Về trạm sạc (Return Charge)"),
    ("return_reversing_charge", "Lùi vào trạm sạc (Reverse Charge)"),
    ("homing_search",           "Dò tìm vị trí (Homing)"),
    ("maintenance",             "Vào bảo trì (Maintenance)"),
]

def _action_label(code, value=0, speed_slow=60, speed_fast=120):
    """Tạo tên ngắn gọn cho 1 action."""
    if code == ACT_SPEED:
        tag = " (CHẬM)" if value == speed_slow else (" (NHANH)" if value == speed_fast else "")
        return f"SPEED({value}){tag}"
    if code == ACT_DIR_FWD: return "TIẾN→"
    if code == ACT_DIR_BWD: return "LÙI←"
    if code == ACT_TURN_L:  return "TURN_L"
    if code == ACT_TURN_R:  return "TURN_R"
    base = ACTION_CODE_TO_NAME.get(code, f"ACT_{code}")
    return f"{base}({value})" if value else base


_DEFAULT_OVERRIDE_TEMPLATE = """# === QUY TẮC CAN THIỆP HÀNH VI AGV ===
# Dòng bắt đầu # là chú thích, bỏ qua.
#
# Cú pháp:  Thẻ <id> [<loại_task>]: <hành_động_cũ> -> <hành_động_mới>
#
# <loại_task>  : any (mặc định), pickup, delivery, return, return_charge
# <hành_động>  : RUN, TURN_L, TURN_R, WAIT_USER, WAIT_SYS
#                SPEED_SLOW, SPEED_FAST, SPEED_NONE (xóa lệnh tốc độ)
#                LIDAR_OFF -> REMOVE   (xóa lệnh tắt lidar)
#
# Ví dụ:
#   Thẻ 8: SPEED_SLOW -> SPEED_NONE         # Không giảm tốc tại thẻ 8
#   Thẻ 9 [any]: TURN_L -> TURN_R           # Đổi sang rẽ PHẢI tại thẻ 9
#   Thẻ 12 [delivery]: RUN -> WAIT_USER     # Dừng chờ xác nhận khi delivery
#   Thẻ 7: LIDAR_OFF -> REMOVE              # Xóa lệnh tắt lidar tại thẻ 7
#
# Ghi chú:
#   - Ký hiệu ✏ trong log báo dòng có override đang áp dụng
#   - Lưu file để hệ thống ghi nhớ quy tắc cho lần sau
#

"""


class SimulationEngine:
    OVERRIDE_FILE = "config/sim_overrides.txt"

    def __init__(self, traffic_manager, app_config):
        self.tm     = traffic_manager
        self.config = app_config

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _calc_angle(self, g, n1, n2, n3):
        """Delegate sang hàm dùng chung (calc_turn_angle từ agv_instance)."""
        return calc_turn_angle(g, n1, n2, n3)

    def _auto_nav(self, g, prev_n, curr_n, next_n):
        """Delegate sang hàm dùng chung (auto_nav_action từ agv_instance).
        Bật _debug=True để in tọa độ thực tế và cross product ra console."""
        return auto_nav_action(g, prev_n, curr_n, next_n, _debug=True)

    def _calc_speed_maps(self, path, task_type):
        """Trả về (speed_overrides dict, lidar_off_nodes set). Giống AGV.set_path logic."""
        g  = self.tm.graph
        tc = self.config.get('traffic', {})
        SPEED_SLOW = int(tc.get('speed_slow', 60))
        SPEED_FAST = int(tc.get('speed_fast', 120))
        speed_ov, lidar_off = {}, set()
        is_return = task_type in ("return_reversing_charge", "return_charge")

        if len(path) >= 3:
            turn_idx = [i for i in range(1, len(path) - 1)
                        if self._calc_angle(g, path[i-1], path[i], path[i+1]) < 150]
            for i, node in enumerate(path):
                if (i + 1) in turn_idx:
                    speed_ov[node] = SPEED_SLOW
                    lidar_off.add(node)
                elif (i - 1) in turn_idx and not is_return:
                    if node not in speed_ov:
                        speed_ov[node] = SPEED_FAST

        if not is_return and path and path[0] not in speed_ov:
            speed_ov[path[0]] = SPEED_FAST

        # Edge speed priority: nếu cạnh ra từ node có p > 0, dùng p thay cho tốc độ tự động.
        # Ngoại lệ: không override SPEED_SLOW (giảm tốc trước điểm cua — ưu tiên an toàn).
        for i, node in enumerate(path):
            if i + 1 < len(path):
                out_e = g.get_edge_data(node, path[i + 1]) or {}
                ep = int(out_e.get('p', 0))
                if ep > 0 and speed_ov.get(node) != SPEED_SLOW:
                    speed_ov[node] = ep

        return speed_ov, lidar_off

    # ── Core dry_run ──────────────────────────────────────────────────────────

    def dry_run(self, start_tag, prev_tag, end_tag, task_type="delivery", facing_tag=None):
        """
        Mô phỏng chuyến đi. Không gửi MQTT.
        Returns: (steps: list[dict], error: str | None)

        Each step dict:
          tag, tag_name, node_type, node_role,
          actions: list[{code, value, label, source}],
          nav_action: {code, label, source},
          next_tag, is_destination, turn_angle,
          applied_overrides: list[str]
        """
        g  = self.tm.graph
        tc = self.config.get('traffic', {})
        SPEED_SLOW = int(tc.get('speed_slow', 60))
        SPEED_FAST = int(tc.get('speed_fast', 120))

        # Validate
        if not g.has_node(start_tag):
            return [], f"Thẻ {start_tag} không tồn tại trên bản đồ."
        if not g.has_node(end_tag):
            return [], f"Thẻ {end_tag} không tồn tại trên bản đồ."
        if start_tag == end_tag:
            return [], "Thẻ bắt đầu và thẻ đích giống nhau."

        # ── Kiểm tra trạm sạc đặc biệt: AGV lùi vào (không có cạnh VÀO) ──────
        # Charger node thường chỉ có cạnh RA (AGV tiến ra). Để vào: dẫn đến
        # exit_node (điểm trước trạm) rồi lùi.
        is_charger_approach = (
            g.nodes[end_tag].get('role') == 'charger' and
            g.in_degree(end_tag) == 0
        )

        if is_charger_approach:
            exit_nodes = list(g.successors(end_tag))
            if not exit_nodes:
                return [], f"Trạm sạc Thẻ {end_tag} không có cạnh kết nối nào trong bản đồ."
            approach_node = exit_nodes[0]   # Ví dụ: Thẻ 210
            if prev_tag is not None and g.has_node(prev_tag):
                path = self.tm.find_path_directed(start_tag, approach_node, prev_tag)
            else:
                path = self.tm.find_path(start_tag, approach_node)
            if not path:
                return [], (
                    f"Không tìm được đường đến điểm trước trạm sạc "
                    f"(Thẻ {approach_node}) từ Thẻ {start_tag}."
                )
            path.append(end_tag)   # Bước lùi cuối: approach_node → charger
        else:
            # Tìm đường thường (dùng find_path_directed nếu có prev_tag)
            if prev_tag is not None and g.has_node(prev_tag):
                path = self.tm.find_path_directed(start_tag, end_tag, prev_tag)
            else:
                path = self.tm.find_path(start_tag, end_tag)
            if not path:
                return [], f"Không tìm được đường từ Thẻ {start_tag} → Thẻ {end_tag}."

        speed_ov, lidar_off = self._calc_speed_maps(path, task_type)
        steps = []
        # Theo dõi chiều hiện tại để inject direction khi thay đổi (Issue 2)
        # Dùng list 1 phần tử để mutate trong closure/inner scope
        _cur_dir = [ACT_DIR_BWD if task_type == "return_reversing_charge" else ACT_DIR_FWD]

        for i, node in enumerate(path):
            nd = g.nodes[node] if g.has_node(node) else {}
            step = {
                "tag":            node,
                "tag_name":       nd.get("name", ""),
                "node_type":      nd.get("type", "normal"),
                "node_role":      nd.get("role", "none"),
                "actions":        [],
                "nav_action":     {"code": ACT_RUN, "label": "RUN", "source": "auto"},
                "next_tag":       path[i + 1] if i < len(path) - 1 else None,
                "is_destination": (i == len(path) - 1),
                "turn_angle":     None,
                "applied_overrides": [],
            }

            # 0. Direction inject / Quay đầu xe ở node đầu tiên
            if i == 0:
                # Tính toán quay chính xác tại node xuất phát.
                #
                # Nguồn hướng xe (ưu tiên):
                #   1. facing_tag  — thẻ mà đầu xe đang hướng tới
                #      vin = vector(start → facing_tag)   ← hướng đầu xe trực tiếp
                #   2. prev_tag    — thẻ xe đến từ đó (fallback)
                #      vin = vector(prev_tag → start)
                #
                # Phân loại góc cần quay (dot giữa vin và vout):
                #   dot >  0.5  (< 60°)  → không cần quay
                #   dot 0.5→-0.5 (60°-120°) → quay 90° (1× TURN_R hoặc TURN_L)
                #   dot < -0.5  (>120°)  → quay 180° (TURN_L×2 hoặc ROTATE_180)
                #
                # Chiều quay: cross_product (screen Y-down): cross>0=CW=TURN_R; cross<0=CCW=TURN_L
                init_turn_cmds = []  # danh sách (code, label) cần inject

                # --- Xác định vector hướng xe (vin) ---
                vin_x = vin_y = 0.0
                has_vin = False
                p_curr = g.nodes.get(node, {})

                if facing_tag is not None and g.has_node(facing_tag) and facing_tag != node:
                    # Ưu tiên: facing_tag — đầu xe đang nhìn về phía đó
                    p_facing = g.nodes.get(facing_tag, {})
                    vin_x = p_facing.get('x', 0) - p_curr.get('x', 0)
                    vin_y = p_facing.get('y', 0) - p_curr.get('y', 0)
                    has_vin = math.sqrt(vin_x**2 + vin_y**2) > 1e-6

                elif prev_tag is not None and g.has_node(prev_tag) and prev_tag != node:
                    # Fallback: prev_tag — xe đến từ đó
                    p_prev = g.nodes.get(prev_tag, {})
                    vin_x = p_curr.get('x', 0) - p_prev.get('x', 0)
                    vin_y = p_curr.get('y', 0) - p_prev.get('y', 0)
                    has_vin = math.sqrt(vin_x**2 + vin_y**2) > 1e-6

                if has_vin and len(path) > 1:
                    next_n = path[1]
                    first_edge = g.get_edge_data(path[0], next_n) or {}
                    if first_edge.get('direction', 'forward') == 'forward':
                        p_next = g.nodes.get(next_n, {})
                        vout_x = p_next.get('x', 0) - p_curr.get('x', 0)
                        vout_y = p_next.get('y', 0) - p_curr.get('y', 0)
                        mag_in  = math.sqrt(vin_x**2  + vin_y**2)
                        mag_out = math.sqrt(vout_x**2 + vout_y**2)
                        if mag_in > 1e-6 and mag_out > 1e-6:
                            dot_n   = (vin_x*vout_x + vin_y*vout_y) / (mag_in * mag_out)
                            cross_v = vin_x * vout_y - vin_y * vout_x  # screen CW→TURN_R
                            all_nb  = set(g.predecessors(node)) | set(g.successors(node))
                            n_conn  = len(all_nb)
                            if dot_n < 0.5:  # cần quay (lệch > 60°)
                                if dot_n < -0.5:  # >120° → quay 180°
                                    # Luôn dùng 2×TURN_L: hoạt động với mọi layout (+/ngã tư)
                                    # ROTATE_180 chỉ hoạt động trên đường thẳng, không đáng tin
                                    init_turn_cmds = [
                                        (ACT_TURN_L, "TURN_L (180° — quay 1/2)"),
                                        (ACT_TURN_L, "TURN_L (180° — quay 2/2)"),
                                    ]
                                else:  # 60°-120° → quay 90° (1 lần)
                                    # Không dùng n_conn để phân biệt: nút góc (2 kết nối
                                    # nhưng ở góc 90°, như 108→102/105) cần TURN, không ROTATE_180.
                                    # n_conn<=2 chỉ đúng cho đường thẳng (dot≈1), nhưng ở đây
                                    # dot ≈ 0 nghĩa là góc thực sự → luôn dùng TURN.
                                    turn_act = ACT_TURN_R if cross_v > 0 else ACT_TURN_L
                                    turn_lbl = "TURN_R (góc 90°)" if turn_act == ACT_TURN_R else "TURN_L (góc 90°)"
                                    init_turn_cmds = [(turn_act, turn_lbl)]

                if init_turn_cmds:
                    step["actions"].append({
                        "code": ACT_LIDAR_OFF, "value": 0,
                        "label": "LIDAR_OFF", "source": "auto"
                    })
                    for tc_code, tc_lbl in init_turn_cmds:
                        step["actions"].append({
                            "code": tc_code, "value": 0,
                            "label": tc_lbl, "source": "auto"
                        })
                    step["actions"].append({
                        "code": ACT_LIDAR_ON, "value": 0,
                        "label": "LIDAR_ON", "source": "auto"
                    })
                    step["actions"].append({
                        "code": ACT_DIR_FWD, "value": 0,
                        "label": _action_label(ACT_DIR_FWD), "source": "auto"
                    })
                else:
                    dc = ACT_DIR_BWD if task_type == "return_reversing_charge" else ACT_DIR_FWD
                    step["actions"].append({
                        "code": dc, "value": 0,
                        "label": _action_label(dc), "source": "auto"
                    })
            # Lùi vào trạm sạc: inject ACT_DIR_BWD tại node ngay trước trạm
            elif is_charger_approach and i == len(path) - 2:
                step["actions"].append({
                    "code": ACT_DIR_BWD, "value": 0,
                    "label": "LÙI← (chuẩn bị vào trạm sạc)", "source": "auto"
                })

            # 1. Edge end_actions từ cạnh TRƯỚC
            if i > 0:
                prev_e = g.get_edge_data(path[i - 1], node) or {}
                for act in prev_e.get("end_actions", []):
                    if isinstance(act, dict):
                        c, v = int(act.get('a', 0)), int(act.get('v', 0))
                    else:
                        c, v = int(act), 0
                    step["actions"].append({
                        "code": c, "value": v,
                        "label": _action_label(c, v, SPEED_SLOW, SPEED_FAST),
                        "source": "edge_end"
                    })

            # 2. LIDAR_OFF trước cua
            if node in lidar_off:
                step["actions"].append({
                    "code": ACT_LIDAR_OFF, "value": 0,
                    "label": "LIDAR_OFF", "source": "auto"
                })

            # 3. Speed override
            if node in speed_ov:
                spd = speed_ov[node]
                step["actions"].append({
                    "code": ACT_SPEED, "value": spd,
                    "label": _action_label(ACT_SPEED, spd, SPEED_SLOW, SPEED_FAST),
                    "source": "auto"
                })

            # 4. Node actions (nâng, hạ, còi...)
            for act_raw in nd.get("actions", []):
                if isinstance(act_raw, dict):
                    c, v = int(act_raw.get('a', 0)), int(act_raw.get('v', 0))
                else:
                    c, v = int(act_raw), 0
                step["actions"].append({
                    "code": c, "value": v,
                    "label": _action_label(c, v, SPEED_SLOW, SPEED_FAST),
                    "source": "node"
                })

            # 5. Navigation action
            if not step["is_destination"]:
                next_n = path[i + 1]
                edge   = g.get_edge_data(node, next_n) or {}

                # Edge start actions
                for act in edge.get("actions", []):
                    if isinstance(act, dict):
                        c, v = int(act.get('a', 0)), int(act.get('v', 0))
                    else:
                        c, v = int(act), 0
                    step["actions"].append({
                        "code": c, "value": v,
                        "label": _action_label(c, v, SPEED_SLOW, SPEED_FAST),
                        "source": "edge_start"
                    })

                # Issue 2: Inject direction nếu edge cấu hình direction thay đổi
                edge_dir    = edge.get('direction', 'forward')
                target_dir  = ACT_DIR_BWD if edge_dir == 'backward' else ACT_DIR_FWD
                if target_dir != _cur_dir[0]:
                    # Nếu đang tiến mà phải lùi: kiểm tra vector để biết có cần quay không
                    if target_dir == ACT_DIR_BWD and _cur_dir[0] == ACT_DIR_FWD and i > 0:
                        pp = g.nodes.get(path[i - 1], {})
                        pc = g.nodes.get(node, {})
                        pn = g.nodes.get(next_n, {})
                        vin_x  = pc.get('x', 0) - pp.get('x', 0)
                        vin_y  = pc.get('y', 0) - pp.get('y', 0)
                        vout_x = pn.get('x', 0) - pc.get('x', 0)
                        vout_y = pn.get('y', 0) - pc.get('y', 0)
                        mag_in  = math.sqrt(vin_x**2 + vin_y**2)
                        mag_out = math.sqrt(vout_x**2 + vout_y**2)
                        if mag_in > 1e-6 and mag_out > 1e-6:
                            dot = (vin_x*vout_x + vin_y*vout_y) / (mag_in * mag_out)
                            if dot > 0.3:   # cùng chiều → đuôi chưa hướng về next → quay 180°
                                all_nb = set(g.predecessors(node)) | set(g.successors(node))
                                n_conn = len(all_nb)
                                step["actions"].append({"code": ACT_LIDAR_OFF, "value": 0,
                                    "label": "LIDAR_OFF", "source": "bwd_rot"})
                                # Luôn 2×TURN_L: hoạt động với mọi layout (+/ngã tư)
                                step["actions"].append({"code": ACT_TURN_L, "value": 0,
                                    "label": "TURN_L (quay 1/2)", "source": "bwd_rot"})
                                step["actions"].append({"code": ACT_TURN_L, "value": 0,
                                    "label": "TURN_L (quay 2/2)", "source": "bwd_rot"})
                                step["actions"].append({"code": ACT_LIDAR_ON, "value": 0,
                                    "label": "LIDAR_ON", "source": "bwd_rot"})
                    step["actions"].append({
                        "code": target_dir, "value": 0,
                        "label": _action_label(target_dir), "source": "edge_dir"
                    })
                    _cur_dir[0] = target_dir

                # Nav action
                manual_a = edge.get('a', 0)
                if manual_a not in (0, ACT_RUN):
                    nav, nav_src = manual_a, "edge_manual"
                elif i > 0:
                    nav, nav_src = self._auto_nav(g, path[i - 1], node, next_n), "auto"
                else:
                    nav, nav_src = ACT_RUN, "auto"

                # Flip hướng rẽ khi edge là backward:
                # auto_nav tính theo chiều tiến; khi lùi đuôi-trước hướng rẽ vật lý ngược lại
                if nav in (ACT_TURN_L, ACT_TURN_R) and edge_dir == 'backward':
                    nav = ACT_TURN_R if nav == ACT_TURN_L else ACT_TURN_L
                    nav_src = nav_src + "+bwd_flip"

                # Tính góc cua để hiển thị
                if nav in (ACT_TURN_L, ACT_TURN_R) and i > 0:
                    step["turn_angle"] = self._calc_angle(g, path[i - 1], node, next_n)

                # Issue 4: Look-ahead — nếu nav là TURN và edge sau TURN (i+1→i+2) là backward
                # → inject LÙI trước TURN tại node hiện tại, flip hướng rẽ
                if (nav in (ACT_TURN_L, ACT_TURN_R)
                        and _cur_dir[0] == ACT_DIR_FWD
                        and i + 2 < len(path)):
                    look_edge = g.get_edge_data(next_n, path[i + 2]) or {}
                    if look_edge.get('direction', 'forward') == 'backward':
                        step["actions"].append({
                            "code": ACT_DIR_BWD, "value": 0,
                            "label": "LÙI←", "source": "bwd_turn_pre"
                        })
                        _cur_dir[0] = ACT_DIR_BWD
                        nav = ACT_TURN_R if nav == ACT_TURN_L else ACT_TURN_L

                step["nav_action"] = {
                    "code": nav,
                    "label": _action_label(nav),
                    "source": nav_src
                }
            else:
                step["nav_action"] = {
                    "code": ACT_WAIT_SYS,
                    "label": "WAIT_SYS",
                    "source": "auto"
                }
                # Trạm sạc: tự động thêm CHARGE
                if is_charger_approach and step["node_role"] == "charger":
                    step["actions"].append({
                        "code": 11, "value": 0,
                        "label": "CHARGE", "source": "auto"
                    })

            steps.append(step)

        return steps, None

    def dry_run_for_path(self, path, prev_tag, task_type="delivery"):
        """Tính lệnh điều hướng cho path đã được tính sẵn (không tìm đường lại).
        Dùng bởi _run_dry_run_for_path trong main.py để đảm bảo path khớp hoàn toàn.

        Returns: (steps: list[dict], error: str | None)
        """
        if not path or len(path) < 1:
            return [], "Path rỗng."
        g = self.tm.graph
        for n in path:
            if not g.has_node(n):
                return [], f"Node {n} không tồn tại trên bản đồ."

        tc = self.config.get('traffic', {})
        SPEED_SLOW = int(tc.get('speed_slow', 60))
        SPEED_FAST = int(tc.get('speed_fast', 120))

        # Kiểm tra xem đích cuối có phải charger approach không
        is_charger_approach = (
            len(path) >= 2 and
            g.nodes[path[-1]].get('role') == 'charger' and
            g.in_degree(path[-1]) == 0
        )

        speed_ov, lidar_off = self._calc_speed_maps(path, task_type)
        steps = []
        _cur_dir = [ACT_DIR_BWD if task_type == "return_reversing_charge" else ACT_DIR_FWD]

        for i, node in enumerate(path):
            nd = g.nodes[node] if g.has_node(node) else {}
            step = {
                "tag":               node,
                "tag_name":          nd.get("name", ""),
                "node_type":         nd.get("type", "normal"),
                "node_role":         nd.get("role", "none"),
                "actions":           [],
                "nav_action":        {"code": ACT_RUN, "label": "RUN", "source": "auto"},
                "next_tag":          path[i + 1] if i < len(path) - 1 else None,
                "is_destination":    (i == len(path) - 1),
                "turn_angle":        None,
                "applied_overrides": [],
            }

            # 0. Direction inject / Quay đầu tại node đầu tiên
            if i == 0:
                init_turn_cmds = []
                vin_x = vin_y = 0.0
                has_vin = False
                p_curr = g.nodes.get(node, {})
                if prev_tag is not None and g.has_node(prev_tag) and prev_tag != node:
                    p_prev = g.nodes.get(prev_tag, {})
                    vin_x = p_curr.get('x', 0) - p_prev.get('x', 0)
                    vin_y = p_curr.get('y', 0) - p_prev.get('y', 0)
                    has_vin = math.sqrt(vin_x**2 + vin_y**2) > 1e-6
                if has_vin and len(path) > 1:
                    next_n = path[1]
                    first_edge = g.get_edge_data(path[0], next_n) or {}
                    if first_edge.get('direction', 'forward') == 'forward':
                        p_next = g.nodes.get(next_n, {})
                        vout_x = p_next.get('x', 0) - p_curr.get('x', 0)
                        vout_y = p_next.get('y', 0) - p_curr.get('y', 0)
                        mag_in  = math.sqrt(vin_x**2  + vin_y**2)
                        mag_out = math.sqrt(vout_x**2 + vout_y**2)
                        if mag_in > 1e-6 and mag_out > 1e-6:
                            dot_n   = (vin_x*vout_x + vin_y*vout_y) / (mag_in * mag_out)
                            cross_v = vin_x * vout_y - vin_y * vout_x
                            all_nb  = set(g.predecessors(node)) | set(g.successors(node))
                            n_conn  = len(all_nb)
                            if dot_n < 0.5:
                                if dot_n < -0.5:
                                    # Luôn 2×TURN_L: hoạt động với mọi layout (+/ngã tư)
                                    init_turn_cmds = [
                                        (ACT_TURN_L, "TURN_L (180° 1/2)"),
                                        (ACT_TURN_L, "TURN_L (180° 2/2)"),
                                    ]
                                else:
                                    turn_act = ACT_TURN_R if cross_v > 0 else ACT_TURN_L
                                    init_turn_cmds = [(turn_act, "TURN_R (90°)" if turn_act == ACT_TURN_R else "TURN_L (90°)")]
                if init_turn_cmds:
                    step["actions"].append({"code": ACT_LIDAR_OFF, "value": 0, "label": "LIDAR_OFF", "source": "auto"})
                    for tc_code, tc_lbl in init_turn_cmds:
                        step["actions"].append({"code": tc_code, "value": 0, "label": tc_lbl, "source": "auto"})
                    step["actions"].append({"code": ACT_LIDAR_ON, "value": 0, "label": "LIDAR_ON", "source": "auto"})
                    step["actions"].append({"code": ACT_DIR_FWD, "value": 0, "label": _action_label(ACT_DIR_FWD), "source": "auto"})
                else:
                    dc = ACT_DIR_BWD if task_type == "return_reversing_charge" else ACT_DIR_FWD
                    step["actions"].append({"code": dc, "value": 0, "label": _action_label(dc), "source": "auto"})
            elif is_charger_approach and i == len(path) - 2:
                step["actions"].append({"code": ACT_DIR_BWD, "value": 0, "label": "LÙI← (chuẩn bị vào trạm sạc)", "source": "auto"})

            # 1. Edge end_actions từ cạnh trước
            if i > 0:
                prev_e = g.get_edge_data(path[i - 1], node) or {}
                for act in prev_e.get("end_actions", []):
                    if isinstance(act, dict):
                        c, v = int(act.get('a', 0)), int(act.get('v', 0))
                    else:
                        c, v = int(act), 0
                    step["actions"].append({"code": c, "value": v, "label": _action_label(c, v, SPEED_SLOW, SPEED_FAST), "source": "edge_end"})

            # 2. LIDAR_OFF trước cua
            if node in lidar_off:
                step["actions"].append({"code": ACT_LIDAR_OFF, "value": 0, "label": "LIDAR_OFF", "source": "auto"})

            # 3. Speed override
            if node in speed_ov:
                spd = speed_ov[node]
                step["actions"].append({"code": ACT_SPEED, "value": spd, "label": _action_label(ACT_SPEED, spd, SPEED_SLOW, SPEED_FAST), "source": "auto"})

            # 4. Node actions
            for act_raw in nd.get("actions", []):
                if isinstance(act_raw, dict):
                    c, v = int(act_raw.get('a', 0)), int(act_raw.get('v', 0))
                else:
                    c, v = int(act_raw), 0
                step["actions"].append({"code": c, "value": v, "label": _action_label(c, v, SPEED_SLOW, SPEED_FAST), "source": "node"})

            # 5. Navigation action
            if not step["is_destination"]:
                next_n = path[i + 1]
                edge   = g.get_edge_data(node, next_n) or {}
                for act in edge.get("actions", []):
                    if isinstance(act, dict):
                        c, v = int(act.get('a', 0)), int(act.get('v', 0))
                    else:
                        c, v = int(act), 0
                    step["actions"].append({"code": c, "value": v, "label": _action_label(c, v, SPEED_SLOW, SPEED_FAST), "source": "edge_start"})

                edge_dir   = edge.get('direction', 'forward')
                target_dir = ACT_DIR_BWD if edge_dir == 'backward' else ACT_DIR_FWD
                if target_dir != _cur_dir[0]:
                    if target_dir == ACT_DIR_BWD and _cur_dir[0] == ACT_DIR_FWD and i > 0:
                        pp = g.nodes.get(path[i - 1], {})
                        pc = g.nodes.get(node, {})
                        pn = g.nodes.get(next_n, {})
                        vin_x  = pc.get('x', 0) - pp.get('x', 0)
                        vin_y  = pc.get('y', 0) - pp.get('y', 0)
                        vout_x = pn.get('x', 0) - pc.get('x', 0)
                        vout_y = pn.get('y', 0) - pc.get('y', 0)
                        mag_in  = math.sqrt(vin_x**2 + vin_y**2)
                        mag_out = math.sqrt(vout_x**2 + vout_y**2)
                        if mag_in > 1e-6 and mag_out > 1e-6:
                            dot = (vin_x*vout_x + vin_y*vout_y) / (mag_in * mag_out)
                            if dot > 0.3:
                                all_nb = set(g.predecessors(node)) | set(g.successors(node))
                                n_conn = len(all_nb)
                                step["actions"].append({"code": ACT_LIDAR_OFF, "value": 0, "label": "LIDAR_OFF", "source": "bwd_rot"})
                                if n_conn <= 2:
                                    step["actions"].append({"code": 9, "value": 0, "label": "ROTATE_180", "source": "bwd_rot"})
                                else:
                                    step["actions"].append({"code": ACT_TURN_L, "value": 0, "label": "TURN_L (quay 1/2)", "source": "bwd_rot"})
                                    step["actions"].append({"code": ACT_TURN_L, "value": 0, "label": "TURN_L (quay 2/2)", "source": "bwd_rot"})
                                step["actions"].append({"code": ACT_LIDAR_ON, "value": 0, "label": "LIDAR_ON", "source": "bwd_rot"})
                    step["actions"].append({"code": target_dir, "value": 0, "label": _action_label(target_dir), "source": "edge_dir"})
                    _cur_dir[0] = target_dir

                manual_a = edge.get('a', 0)
                if manual_a not in (0, ACT_RUN):
                    nav, nav_src = manual_a, "edge_manual"
                elif i > 0:
                    nav, nav_src = self._auto_nav(g, path[i - 1], node, next_n), "auto"
                else:
                    nav, nav_src = ACT_RUN, "auto"

                if nav in (ACT_TURN_L, ACT_TURN_R) and edge_dir == 'backward':
                    nav = ACT_TURN_R if nav == ACT_TURN_L else ACT_TURN_L
                    nav_src += "+bwd_flip"

                if nav in (ACT_TURN_L, ACT_TURN_R) and i > 0:
                    step["turn_angle"] = self._calc_angle(g, path[i - 1], node, next_n)

                if (nav in (ACT_TURN_L, ACT_TURN_R)
                        and _cur_dir[0] == ACT_DIR_FWD
                        and i + 2 < len(path)):
                    look_edge = g.get_edge_data(next_n, path[i + 2]) or {}
                    if look_edge.get('direction', 'forward') == 'backward':
                        step["actions"].append({"code": ACT_DIR_BWD, "value": 0, "label": "LÙI←", "source": "bwd_turn_pre"})
                        _cur_dir[0] = ACT_DIR_BWD
                        nav = ACT_TURN_R if nav == ACT_TURN_L else ACT_TURN_L

                step["nav_action"] = {"code": nav, "label": _action_label(nav), "source": nav_src}
            else:
                step["nav_action"] = {"code": ACT_WAIT_SYS, "label": "WAIT_SYS", "source": "auto"}
                if is_charger_approach and step["node_role"] == "charger":
                    step["actions"].append({"code": 11, "value": 0, "label": "CHARGE", "source": "auto"})

            steps.append(step)

        return steps, None

    # ── Override system ───────────────────────────────────────────────────────

    def load_overrides_text(self):
        """Đọc file override rules về dạng text thuần."""
        if not os.path.exists(self.OVERRIDE_FILE):
            return _DEFAULT_OVERRIDE_TEMPLATE
        try:
            with open(self.OVERRIDE_FILE, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception:
            return _DEFAULT_OVERRIDE_TEMPLATE

    def save_overrides_text(self, text):
        """Lưu text override rules vào file."""
        os.makedirs(os.path.dirname(self.OVERRIDE_FILE), exist_ok=True)
        with open(self.OVERRIDE_FILE, 'w', encoding='utf-8') as f:
            f.write(text)

    def parse_overrides(self, text):
        """
        Parse text override rules.
        Trả về (rules: list[dict], warnings: list[str]).
        Cú pháp: Thẻ <id> [<task_type>]: <hành_động_cũ> -> <hành_động_mới>
        """
        rules, warnings = [], []
        pattern = re.compile(
            r"Thẻ\s+(\d+)"
            r"(?:\s*\[([^\]]+)\])?"
            r"\s*:\s*"
            r"([^#\->]+?)"
            r"\s*->\s*"
            r"([^#\n]+)",
            re.IGNORECASE
        )
        for lineno, raw in enumerate(text.splitlines(), 1):
            line = raw.split('#')[0].strip()
            if not line:
                continue
            m = pattern.match(line)
            if not m:
                if not line.startswith('#'):
                    warnings.append(f"Dòng {lineno}: Không đọc được → '{raw.strip()}'")
                continue
            rules.append({
                "tag":       int(m.group(1)),
                "task_type": (m.group(2) or "any").strip().lower(),
                "old":       m.group(3).strip().upper(),
                "new":       m.group(4).strip().upper(),
                "raw":       raw.strip(),
            })
        return rules, warnings

    def apply_overrides_from_text(self, text, steps, task_type):
        """
        Áp dụng override rules vào danh sách steps.
        Trả về (modified_steps, applied_count, warnings).
        """
        rules, warn = self.parse_overrides(text)
        steps       = copy.deepcopy(steps)
        applied     = 0
        tc = self.config.get('traffic', {})
        SPEED_SLOW = int(tc.get('speed_slow', 60))
        SPEED_FAST = int(tc.get('speed_fast', 120))

        for rule in rules:
            if rule["task_type"] not in ("any", task_type):
                continue
            tag, old_n, new_n = rule["tag"], rule["old"], rule["new"]

            for step in steps:
                if step["tag"] != tag:
                    continue
                changed = False

                # Case 1: Override tốc độ
                if old_n in ("SPEED_SLOW", "SPEED_FAST", "SPEED"):
                    for idx, a in enumerate(step["actions"]):
                        if a["code"] != ACT_SPEED:
                            continue
                        match = (
                            (old_n == "SPEED_SLOW" and a["value"] == SPEED_SLOW) or
                            (old_n == "SPEED_FAST" and a["value"] == SPEED_FAST) or
                            (old_n == "SPEED")
                        )
                        if not match:
                            continue
                        if new_n == "SPEED_NONE":
                            step["actions"].pop(idx)
                        elif new_n == "SPEED_SLOW":
                            a["value"] = SPEED_SLOW
                            a["label"] = _action_label(ACT_SPEED, SPEED_SLOW, SPEED_SLOW, SPEED_FAST)
                            a["source"] = "override"
                        elif new_n == "SPEED_FAST":
                            a["value"] = SPEED_FAST
                            a["label"] = _action_label(ACT_SPEED, SPEED_FAST, SPEED_SLOW, SPEED_FAST)
                            a["source"] = "override"
                        else:
                            warn.append(f"Thẻ {tag}: giá trị tốc độ không hợp lệ '{new_n}'")
                            continue
                        changed = True
                        break

                # Case 2: Override nav action
                elif old_n in ("RUN", "TURN_L", "TURN_R", "WAIT_USER", "WAIT_SYS", "AUTO"):
                    nav = step["nav_action"]
                    cur_name = ACTION_CODE_TO_NAME.get(nav["code"], "").upper()
                    if cur_name == old_n or old_n == "AUTO":
                        new_code = ACTION_NAME_TO_CODE.get(new_n)
                        if new_code is not None and new_code >= 0:
                            nav["code"]   = new_code
                            nav["label"]  = _action_label(new_code)
                            nav["source"] = "override"
                            changed = True
                        else:
                            warn.append(f"Thẻ {tag}: Không hiểu hành động '{new_n}'")

                # Case 3: Xóa LIDAR_OFF
                elif old_n == "LIDAR_OFF" and new_n == "REMOVE":
                    before = len(step["actions"])
                    step["actions"] = [a for a in step["actions"] if a["code"] != ACT_LIDAR_OFF]
                    changed = len(step["actions"]) < before

                # Case 4: ADD action
                elif old_n == "ADD":
                    new_code = ACTION_NAME_TO_CODE.get(new_n)
                    if new_code and new_code > 0:
                        step["actions"].append({
                            "code": new_code, "value": 0,
                            "label": _action_label(new_code), "source": "override"
                        })
                        changed = True

                if changed:
                    applied += 1
                    step["applied_overrides"].append(rule["raw"])

        return steps, applied, warn

    # ── Log formatter ─────────────────────────────────────────────────────────

    def format_log(self, steps, start_tag, end_tag, task_type):
        """Tạo log text từ list steps để hiển thị trong UI."""
        task_label = dict(TASK_TYPES).get(task_type, task_type.upper())
        SEP = "═" * 70
        sep2 = "─" * 70
        lines = [
            SEP,
            f"  MÔ PHỎNG: {task_label.upper()}",
            f"  Thẻ {start_tag} → Thẻ {end_tag}  |  Tổng: {len(steps)} thẻ",
            SEP,
            f"  {'TAG':<12}  {'CÁC LỆNH TRƯỚC DI CHUYỂN':<32}  LỆNH DI CHUYỂN",
            sep2,
        ]

        turn_count  = 0
        speed_count = 0
        for step in steps:
            tag_str  = f"Thẻ {step['tag']}"
            role     = step["node_role"]
            name     = step["tag_name"]
            role_str = f"[{role}]" if role not in ("none", "", None) else ""
            name_str = f"({name})" if name else ""
            header   = f"{tag_str} {role_str}{name_str}".strip()

            # Pre-actions
            pre_parts = []
            for a in step["actions"]:
                a_src = a.get("source", "auto")
                a_mark = "✏ " if a_src == "override" else ("[M] " if a_src == "edge_manual" else "")
                pre_parts.append(f"{a_mark}{a['label']}")
            pre_str = "  ".join(pre_parts) if pre_parts else "—"

            # Nav action
            nav  = step["nav_action"]
            src  = nav.get("source", "auto")
            if src == "override":
                mark = "✏ "       # Override rule do người dùng nhập
            elif src == "edge_manual":
                mark = "[M] "     # Cấu hình thủ công trên cạnh (field 'a' trong map)
            else:
                mark = ""
            if step["is_destination"]:
                if step["node_role"] == "charger":
                    nav_str = f"⚡ {mark}ĐÍCH SẠC — CHARGE + WAIT_SYS"
                else:
                    nav_str = f"■ {mark}ĐÍCH — WAIT_SYS"
            else:
                arrow   = "↻" if nav["code"] in (ACT_TURN_L, ACT_TURN_R) else "➜"
                ang_str = f" (góc {step['turn_angle']:.0f}°)" if step.get("turn_angle") else ""
                nav_str = f"{arrow} {mark}{nav['label']}{ang_str} → Thẻ {step['next_tag']}"

            if nav["code"] in (ACT_TURN_L, ACT_TURN_R):
                turn_count += 1
            if any(a["code"] == ACT_SPEED for a in step["actions"]):
                speed_count += 1

            lines.append(f"  {header:<18}  {pre_str:<32}  {nav_str}")

            for ov in step.get("applied_overrides", []):
                lines.append(f"  {'':>18}  ✏ Override: {ov}")

        lines += [
            sep2,
            f"  TỔNG KẾT: {len(steps)} thẻ  |  {turn_count} lần rẽ  |  {speed_count} lần đổi tốc độ",
            SEP,
        ]
        return "\n".join(lines)
