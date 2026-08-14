"""
line_agv_plan_builder.py
Xây dựng plan {"c":"plan","id":"...","d":[...]} cho Line AGV (ESP32+Arduino RFID-based).

Quy tắc (theo PROTOCOL_GUIDE.md):
  - Plan bắt đầu từ thẻ HIỆN TẠI của xe (overlap)
  - Pattern chuẩn trước TURN: tại N-1 → SPEED_SLOW, LIDAR_OFF, RUN
  - Pattern chuẩn tại TURN node N → TURN_R/L, LIDAR_ON, SPEED_FAST, RUN
  - Plan gửi theo cửa sổ LOOKAHEAD node; cuối cửa sổ trung gian dùng WAIT_SYS
"""
from __future__ import annotations

import math
import uuid

# ── Action codes (khớp với Arduino mission.h) ─────────────────────────────────
ACTION_WAIT_SYS    = 1    # Dừng, chờ hệ thống
ACTION_WAIT_USER   = 2    # Dừng, chờ người bấm nút HMI
ACTION_RUN         = 3    # Chạy thẳng đến thẻ tiếp theo
ACTION_SPEED       = 4    # Đặt tốc độ (v = 0-255)
ACTION_TURN_R      = 5    # Rẽ phải 90°
ACTION_TURN_L      = 6    # Rẽ trái 90°
ACTION_DIR_FWD     = 7    # Đặt chiều tiến
ACTION_DIR_BWD     = 8    # Đặt chiều lùi
ACTION_LIDAR_OFF   = 20   # Tắt cảm biến vật cản (bắt buộc trước TURN)
ACTION_LIDAR_ON    = 21   # Bật cảm biến vật cản (sau TURN xong)
ACTION_WAIT_CHARGE = 35   # Đến trạm sạc: đèn vàng + cảm biến, chờ
ACTION_HOOK_RAISE  = 30   # Nâng móc (xe rơ-moóc/đầu kéo) — gửi qua instantActions, không phải trong plan
ACTION_HOOK_LOWER  = 31   # Hạ móc (xe rơ-moóc/đầu kéo) — bình thường do cảm biến xe tự làm, không server gửi
ACTION_REVERSE_BLIND = 36 # Lùi mù theo thời gian (v = ms) — chỉ dùng khi xe rơ-moóc rời trạm sạc để quay đầu

SPEED_FAST     = 120   # byte mặc định khi edge không cấu hình speed
SPEED_SLOW     = 60    # byte tốc độ tiếp cận nút rẽ (N-1 pattern)
LOOKAHEAD      = 4    # số node/cửa sổ rolling (≤5 node) — tránh tràn UART buffer Arduino (128B)
RETRY_TIMEOUT  = 4.0   # giây, thời gian chờ ACK trước khi retry

# Hệ số chuyển đổi m/s → Arduino byte: 0.5 m/s = SPEED_FAST = 120 → factor = 240
_SPEED_FACTOR  = 240


def ms_to_speed_byte(speed_ms: float) -> int:
    """Chuyển tốc độ m/s (từ map editor) sang Arduino byte (0-255)."""
    if speed_ms <= 0:
        return SPEED_FAST
    return max(10, min(255, int(speed_ms * _SPEED_FACTOR)))


def _act_name(a: int | None) -> str:
    _MAP = {ACTION_TURN_R: "TURN_R", ACTION_TURN_L: "TURN_L",
            ACTION_DIR_FWD: "DIR_FWD", ACTION_DIR_BWD: "DIR_BWD",
            ACTION_WAIT_SYS: "WAIT_SYS", ACTION_WAIT_USER: "WAIT_USER",
            ACTION_WAIT_CHARGE: "WAIT_CHARGE"}
    return _MAP.get(a, "STRAIGHT") if a is not None else "STRAIGHT"


# ── Turn direction ─────────────────────────────────────────────────────────────

def get_turn_direction(
    from_tag: str,
    at_tag:   str,
    to_tag:   str,
    points:   dict,
) -> int | None:
    """
    Tính hướng rẽ tại at_tag khi đến từ from_tag và đi tiếp đến to_tag.

    points: {node_id_str: (x, y)} — từ map_manager.points
    Returns: ACTION_TURN_R | ACTION_TURN_L | None (đi thẳng / thiếu tọa độ)

    Cross product 2D:  in_vec × out_vec
      > 0  → CCW (rẽ trái,  tọa độ toán học Y-up)
      < 0  → CW  (rẽ phải, tọa độ toán học Y-up)
    Map editor dùng SVG (Y tăng xuống) → MAP_Y_DOWN = True.
    """
    MAP_Y_DOWN = True    # SVG/màn hình: Y tăng xuống → đảo chiều cross product

    p_from = points.get(str(from_tag))
    p_at   = points.get(str(at_tag))
    p_to   = points.get(str(to_tag))
    if not (p_from and p_at and p_to):
        return None

    in_vec  = (p_at[0] - p_from[0], p_at[1] - p_from[1])
    out_vec = (p_to[0]  - p_at[0],  p_to[1]  - p_at[1])

    cross   = in_vec[0] * out_vec[1] - in_vec[1] * out_vec[0]
    mag_in  = math.hypot(*in_vec)
    mag_out = math.hypot(*out_vec)

    if mag_in < 1e-6 or mag_out < 1e-6:
        return None

    sin_a = cross / (mag_in * mag_out)
    if abs(sin_a) < 0.3:          # < ~17° → coi là đi thẳng
        return None

    if MAP_Y_DOWN:
        cross = -cross             # đảo chiều cho tọa độ màn hình

    return ACTION_TURN_R if cross < 0 else ACTION_TURN_L


# ── Turn resolver ─────────────────────────────────────────────────────────────

def _resolve_turn(
    tag_str:      str,
    from_tag:     str | None,
    to_tag:       str | None,
    points:       dict,
    node_actions: dict,
    direction:    str,   # "fwd"|"bwd"
    skip_geometry: bool = False,   # True cho xe không lùi được — chỉ rẽ tại junction đã cấu hình tường minh
) -> tuple[int | None, str]:
    """
    Trả về (action, source) với action = ACTION_TURN_R | ACTION_TURN_L | None.

    Ưu tiên:
    1a. turn_map["{from}_{to}_{direction}"] — explicit có chiều
    1b. turn_map["{from}_{to}"] — explicit không chiều (fallback)
    2.  Coordinate geometry (get_turn_direction) — BỎ QUA nếu skip_geometry=True
    3.  Legacy fwd_turn / bwd_turn config — backward compat

    skip_geometry=True: xe đầu kéo/rơ-moóc (không lùi được) chỉ được rẽ tại
    node đã cấu hình tường minh là junction (turn_map hoặc legacy fwd/bwd_turn)
    — không suy đoán theo toạ độ, vì toạ độ import (vd từ draw.io) có thể lệch
    nhẹ và geometry sẽ coi mọi khúc cong nhẹ là 1 cú rẽ, xe rơ-moóc không xử lý
    được rẽ ngoài ý muốn (dễ gập xe kéo).
    """
    act = node_actions.get(str(tag_str), {}) if node_actions else {}

    # ── Priority 0: turn_allowed='no' — ép đi thẳng, bỏ qua turn_map/geometry.
    # Node được đánh dấu KHÔNG cho rẽ/quay trên map (vd điểm giữa đường 1 chiều)
    # — trước đây field này bị bỏ qua hoàn toàn, khiến geometry đôi khi tính ra
    # góc quay sai (gần 180°) tại các node import từ draw.io toạ độ chưa chuẩn.
    if str(act.get("turn_allowed") or "yes").lower() == "no":
        return None, "turn_allowed=no"

    # ── Priority 1: turn_map lookup ──────────────────────────────────────────
    if from_tag and to_tag:
        turn_map = act.get("turn_map") or {}
        key_dir     = f"{from_tag}_{to_tag}_{direction}"
        # (from_tag, to_tag) đã TỰ xác định rõ chiều đi qua node (thứ tự 2 tag)
        # — hậu tố "_fwd"/"_bwd" chỉ đánh dấu THEO NGỮ CẢNH lúc người dùng cấu
        # hình trên Map Editor (thường luôn để "_fwd" mặc định), KHÔNG phải chiều
        # vật lý khác nhau cho CÙNG 1 cặp (from,to). Nếu chỉ tra đúng hậu tố
        # 'direction' hiện tại (vd route trả-về-sạc gắn nhãn 'bwd') mà cấu hình
        # lại lưu dưới "_fwd" → tra trật, rơi thẳng xuống "none" dù đã cấu hình
        # rẽ rõ ràng cho ĐÚNG cặp (from,to) này. Thử luôn hậu tố còn lại trước khi
        # bỏ cuộc — an toàn vì (from,to) đã đủ xác định turn, không cần suy luận gì thêm.
        _opp_dir    = "bwd" if direction == "fwd" else "fwd"
        key_dir_opp = f"{from_tag}_{to_tag}_{_opp_dir}"
        key_any     = f"{from_tag}_{to_tag}"
        if key_dir in turn_map:
            val = str(turn_map[key_dir]).lower()
            src = f"turn_map:{key_dir}={val}"
        elif key_dir_opp in turn_map:
            val = str(turn_map[key_dir_opp]).lower()
            src = f"turn_map:{key_dir_opp}={val}"
        elif key_any in turn_map:
            val = str(turn_map[key_any]).lower()
            src = f"turn_map:{key_any}={val}"
        else:
            val = "none"
            src = ""
        if val == "right":    return ACTION_TURN_R, src
        if val == "left":     return ACTION_TURN_L, src
        if val == "straight": return None, src

    # ── Priority 2: coordinate geometry ─────────────────────────────────────
    if not skip_geometry and from_tag and to_tag:
        coord_turn = get_turn_direction(from_tag, tag_str, to_tag, points)
        if coord_turn is not None:
            return coord_turn, "geometry"

    # ── Priority 3: legacy fwd_turn / bwd_turn ───────────────────────────────
    if direction == "bwd":
        explicit = str(act.get("bwd_turn") or "none").lower()
        if explicit == "none":
            fwd = str(act.get("fwd_turn") or "none").lower()
            if fwd == "right":
                explicit = "left"
            elif fwd == "left":
                explicit = "right"
        src = f"legacy_bwd_turn={explicit}"
    else:
        explicit = str(act.get("fwd_turn") or "none").lower()
        src = f"legacy_fwd_turn={explicit}"

    if explicit == "right": return ACTION_TURN_R, src
    if explicit == "left":  return ACTION_TURN_L, src
    return None, "straight"


def _invert_turn(action: int | None) -> int | None:
    if action == ACTION_TURN_R: return ACTION_TURN_L
    if action == ACTION_TURN_L: return ACTION_TURN_R
    return action


def _resolve_turn_bwd_arrival(
    tag_str:      str,
    from_tag:     str,
    to_tag:       str,
    points:       dict,
    node_actions: dict,
    skip_geometry: bool = False,
) -> tuple[int | None, str]:
    """Turn tại start node khi AGV vừa đến BACKWARD (front hướng về from_tag).

    Logic:
    1. Key '_bwd' trong turn_map → user cấu hình riêng cho backward arrival → dùng trực tiếp.
    2. Key '_fwd' / undirected → cấu hình cho forward arrival → đảo chiều (L↔R).
    3. Geometry forward → đảo chiều (do in_vec bị ngược so với hướng front thực tế).
    4. Legacy bwd_turn (đã tự đảo trong _resolve_turn với direction='bwd').
    """
    act      = node_actions.get(str(tag_str), {}) if node_actions else {}
    turn_map = act.get("turn_map") or {}
    key_bwd  = f"{from_tag}_{to_tag}_bwd"
    key_fwd  = f"{from_tag}_{to_tag}_fwd"
    key_any  = f"{from_tag}_{to_tag}"

    # 0. turn_allowed='no' — ép đi thẳng, bỏ qua mọi tính toán khác (xem lý do
    # tương tự ở _resolve_turn).
    if str(act.get("turn_allowed") or "yes").lower() == "no":
        return None, "turn_allowed=no [bwd_arrival]"

    # 1. Explicit bwd key → user đã cấu hình cho backward arrival
    if key_bwd in turn_map:
        val = str(turn_map[key_bwd]).lower()
        src = f"turn_map:{key_bwd}={val} [bwd_arrival]"
        if val == "right":    return ACTION_TURN_R, src
        if val == "left":     return ACTION_TURN_L, src
        if val == "straight": return None, src

    # 2. Fwd / undirected key → cấu hình cho forward arrival → đảo chiều
    for key in (key_fwd, key_any):
        if key in turn_map:
            val = str(turn_map[key]).lower()
            src = f"turn_map:{key}={val} [bwd_arrival,inverted]"
            if val == "right":    return ACTION_TURN_L, src   # inverted
            if val == "left":     return ACTION_TURN_R, src   # inverted
            if val == "straight": return None, src

    # 3. Geometry (forward direction) → đảo chiều vì front thực tế ngược in_vec
    if not skip_geometry:
        fwd_geo = get_turn_direction(from_tag, tag_str, to_tag, points)
        if fwd_geo is not None:
            inv = _invert_turn(fwd_geo)
            return inv, "geometry [bwd_arrival,inverted]"

    # 4. Legacy bwd_turn (đã xử lý đảo chiều trong _resolve_turn với direction='bwd')
    return _resolve_turn(tag_str, from_tag, to_tag, points, node_actions, "bwd", skip_geometry=skip_geometry)


# ── Step builder ───────────────────────────────────────────────────────────────

def _edge_speed(path: list[str], gi: int, edge_speeds: dict) -> int:
    """Tốc độ byte cho edge path[gi]→path[gi+1]. Fallback SPEED_FAST nếu không có."""
    if not edge_speeds or gi + 1 >= len(path):
        return SPEED_FAST
    return edge_speeds.get(f"{path[gi]}_{path[gi + 1]}", SPEED_FAST)


def _build_steps(
    full_path:           list[str],
    w_start:             int,
    w_end:               int,
    points:              dict,
    is_final:            bool,
    task_type:           str,
    node_actions:        dict = {},    # {nid: {fwd_turn, bwd_turn, ...}}
    direction:           str  = "fwd", # "fwd" | "bwd"
    edge_speeds:         dict = {},    # {"src_dst": speed_byte} từ map_manager.roads
    edge_lidar:          dict = {},    # {"src_dst": True} edge có lidar_off từ map editor
    _agv:                str  = "?",
    initial_prev_tag:    str | None = None,  # hướng xe trước node đầu tiên (dùng khi w_start==0)
    initial_arrived_bwd: bool = False,       # True khi xe đến start node theo chiều lùi (charger exit)
) -> list[dict]:
    """
    Tạo action steps cho cửa sổ full_path[w_start..w_end].

    edge_lidar: {"{src}_{dst}": True} — đoạn đường cần tắt LIDAR (từ map editor).
    Logic LIDAR:
      - Nếu node_actions[node].lidar_off == "yes" HOẶC edge out có lidar_off:
        chèn LIDAR_OFF trước RUN. Tại node tiếp theo, chèn LIDAR_ON đầu tiên.
      - Turn pattern vẫn tự động thêm LIDAR_OFF/ON quanh rẽ (ưu tiên an toàn).
    """
    steps   = []
    n_full  = len(full_path)
    w_len   = w_end - w_start + 1

    # Lùi vào đích (DIR_BWD ở node trước đích) CHỈ áp dụng khi:
    #   (a) đích là TRẠM SẠC (locationType=CHARGER / wait_charge) — nơi THỰC SỰ cần lùi vào.
    #       → KHÔNG honor approach_dir=bwd sót lại trên node thường (NORMAL/junction). Nhiều
    #         node thường trong map để approach_dir=bwd mặc định → nếu lùi vào sẽ chèn DIR_BWD
    #         bậy, kết hợp với TURN làm xe đi NHẦM node (vd 1→96 thay vì 1→2) → off_route loạn.
    #   (b) node TRƯỚC đích KHÔNG phải trạm sạc — vì sau trạm sạc không có đường để lùi.
    dest_node_act      = node_actions.get(str(full_path[w_end]), {}) if full_path else {}
    _dest_is_charger = (
        str(dest_node_act.get("locationType", "")).upper() == "CHARGER"
        or str(dest_node_act.get("arrival_action", "")).lower() == "wait_charge"
    )
    _pre_final_node = full_path[w_end - 1] if (full_path and w_end >= 1) else None
    _pre_final_cfg  = node_actions.get(str(_pre_final_node), {}) if _pre_final_node is not None else {}
    _pre_final_is_charger = (
        str(_pre_final_cfg.get("locationType", "")).upper() == "CHARGER"
        or str(_pre_final_cfg.get("arrival_action", "")).lower() == "wait_charge"
    )
    _dest_wants_bwd = str(dest_node_act.get("approach_dir") or "").lower() == "bwd"
    # MỚI: xe không lùi được (đầu kéo/rơ-moóc) — KHÔNG BAO GIỜ chèn lùi vào trạm
    # sạc dù node đích cấu hình approach_dir=bwd (cấu hình đó dành cho carry).
    # Map cần trạm sạc riêng (approach_dir để trống/tiến) cho xe loại này.
    _can_reverse_agv = True
    try:
        from agv_registry import agv_registry as _areg_bwd
        _can_reverse_agv = _areg_bwd.can_reverse(_agv)
    except Exception:
        pass
    final_approach_bwd = (
        is_final and _dest_wants_bwd and _dest_is_charger and not _pre_final_is_charger
        and _can_reverse_agv
    )
    if is_final and _dest_wants_bwd and _dest_is_charger and not _can_reverse_agv:
        print(f"[PLAN] {_agv} | xe không lùi được — BỎ backward-approach vào trạm sạc "
              f"{full_path[w_end]}, đi TIẾN vào (cần trạm sạc riêng nếu vật lý không tiếp cận được bằng tiến)")
    if is_final and _dest_wants_bwd and not _dest_is_charger:
        print(f"[PLAN] {_agv} | BỎ qua approach_dir=bwd tại {full_path[w_end]} "
              f"(không phải trạm sạc) → đi TIẾN vào, tránh DIR_BWD bậy gây đi nhầm node")
    elif is_final and _dest_wants_bwd and _pre_final_is_charger:
        print(f"[PLAN] {_agv} | BỎ backward-approach vào {full_path[w_end]} "
              f"vì node trước ({_pre_final_node}) là trạm sạc (sau trạm không có đường lùi) → đi tiến")

    # Đặt chiều đi ở bước đầu tiên của cửa sổ đầu tiên
    if w_start == 0:
        dir_action = ACTION_DIR_BWD if direction == "bwd" else ACTION_DIR_FWD
        first_tag  = int(full_path[0]) if full_path else 0
        steps.append({"t": first_tag, "a": dir_action, "v": 0})
        print(f"[PLAN] {_agv} | node {first_tag}: {_act_name(dir_action)} (direction={direction}, dest={full_path[-1]}, task={task_type})")

    # Trạng thái LIDAR: True khi LIDAR đang bị tắt bởi user config (không phải turn)
    incoming_lidar_off = False

    for local_i in range(w_len):
        global_i  = w_start + local_i
        tag       = int(full_path[global_i])
        tag_str   = full_path[global_i]
        is_last   = (local_i == w_len - 1)

        # Lưu lại state từ vòng trước và reset
        need_restore_lidar = incoming_lidar_off
        incoming_lidar_off = False

        # ── Thẻ cuối cửa sổ ───────────────────────────────────────────────────
        if is_last:
            # KHÔNG bật lại LIDAR nếu chính node CUỐI này cũng được cấu hình tắt
            # (vd trạm sạc node 10 — hay bị báo vật cản giả do LIDAR bật đúng lúc
            # xe dừng sát vách/trụ sạc). Trước đây bật ON vô điều kiện ngay khi tới
            # bất kỳ node nào theo sau 1 edge lidar_off=yes, dù chính node đó CŨNG
            # được đánh dấu tắt — bật rồi lại phải tắt ngay, tạo khoảng hở ngắn dễ
            # trúng vật cản giả đúng lúc dừng.
            _last_node_lidar_off = str(node_actions.get(str(tag), {}).get("lidar_off", "no")).lower() == "yes"
            if need_restore_lidar and not _last_node_lidar_off:
                steps.append({"t": tag, "a": ACTION_LIDAR_ON, "v": 0})
            if is_final:
                node_cfg     = node_actions.get(str(tag), {})
                arrival_cfg  = str(node_cfg.get("arrival_action") or "").lower()
                # Node đã đánh dấu vai trò lấy/thả hàng rơ-moóc (Tổ dọc chuyền hay
                # điểm đích lấy/thả) — luôn cần người thao tác cơ khí NGAY TẠI XE,
                # hiếm khi có ai trực Web để bấm xác nhận từ xa. Nhận diện theo
                # đúng các field mà _handle_trailer_hook_arrival() dùng.
                _trailer_role_pb = str(node_cfg.get("trailer_role") or "").strip().lower()
                _is_trailer_hook_node = (
                    _trailer_role_pb in ("drop", "pickup")
                    or str(node_cfg.get("trailer_staging") or "").strip().lower() == "yes"
                    or str(node_cfg.get("trailer_empty_staging") or "").strip().lower() == "yes"
                    or bool(node_cfg.get("supply_group"))
                )
                if task_type == "transit":
                    # Đoạn lùi tạm — không áp dụng arrival_action, luôn WAIT_SYS
                    _arr = ACTION_WAIT_SYS
                elif arrival_cfg == "wait_sys":
                    _arr = ACTION_WAIT_SYS
                elif arrival_cfg == "wait_user":
                    _arr = ACTION_WAIT_USER
                elif arrival_cfg == "wait_charge":
                    _arr = ACTION_WAIT_CHARGE
                elif task_type in ("delivery", "pickup") and _is_trailer_hook_node:
                    # Chưa cấu hình arrival_action tường minh nhưng là điểm móc hàng
                    # → mặc định WAIT_USER (xe tự chờ người bấm xác nhận tại chỗ)
                    # thay vì WAIT_SYS (chờ lệnh hệ thống/Web — dễ treo vô thời hạn
                    # vì các điểm này thường không có ai trực Web).
                    _arr = ACTION_WAIT_USER
                elif task_type in ("delivery", "pickup"):
                    _arr = ACTION_WAIT_SYS
                elif task_type == "return_charge":
                    _arr = ACTION_WAIT_CHARGE
                else:
                    _arr = ACTION_WAIT_SYS
                steps.append({"t": tag, "a": _arr, "v": 0})
                print(f"[PLAN] {_agv} | node {tag}: {_act_name(_arr)} (arrival, task={task_type}, arrival_cfg={arrival_cfg!r})")
            else:
                steps.append({"t": tag, "a": ACTION_WAIT_SYS, "v": 0})
            break

        # ── Rẽ TẠI NÚT HIỆN TẠI ─────────────────────────────────────────────
        # Nếu global_i==0 và biết hướng xe trước đó (initial_prev_tag), tính turn ngay tại node đầu
        _using_initial_prev = (global_i == 0 and w_start == 0 and initial_prev_tag is not None)
        _from_for_turn = (full_path[global_i - 1] if global_i > 0
                          else (initial_prev_tag if w_start == 0 else None))
        turn_at_current = None
        _turn_src_cur   = ""
        if _from_for_turn and global_i + 1 < n_full:
            if _using_initial_prev and direction == "fwd" and initial_arrived_bwd:
                # Xe đến start node theo chiều lùi (ví dụ: lùi vào trạm sạc), kế hoạch mới đi tiến.
                # Front của xe đang hướng về phía prev_tag → cần đảo chiều geometry.
                turn_at_current, _turn_src_cur = _resolve_turn_bwd_arrival(
                    tag_str,
                    _from_for_turn,
                    full_path[global_i + 1],
                    points, node_actions,
                    skip_geometry=not _can_reverse_agv,
                )
            else:
                # Xe đến start node theo chiều tiến (bình thường, bao gồm cả staging node),
                # HOẶC xe tiếp tục theo chiều lùi → dùng _resolve_turn với direction thực tế.
                turn_at_current, _turn_src_cur = _resolve_turn(
                    tag_str,
                    _from_for_turn,
                    full_path[global_i + 1],
                    points, node_actions, direction,
                    skip_geometry=not _can_reverse_agv,
                )
            _from_l = _from_for_turn
            _to_l   = full_path[global_i + 1]
            print(f"[PLAN] {_agv} | node {tag} ({direction}, from={_from_l}→{tag}→{_to_l}): "
                  f"{_act_name(turn_at_current)}"
                  + (f"  [{_turn_src_cur}]" if _turn_src_cur and _turn_src_cur not in ("straight","") else ""))

        # ── Rẽ TẠI NÚT TIẾP THEO ─────────────────────────────────────────────
        turn_at_next = None
        if global_i + 2 < n_full:
            turn_at_next, _ = _resolve_turn(
                full_path[global_i + 1],
                tag_str,
                full_path[global_i + 2],
                points, node_actions, direction,
                skip_geometry=not _can_reverse_agv,
            )

        # ── Kiểm tra LIDAR config cho edge ra / node hiện tại ────────────────
        out_edge_key   = f"{tag_str}_{full_path[global_i + 1]}"
        node_lidar_off = str(node_actions.get(tag_str, {}).get("lidar_off", "no")).lower() == "yes"
        # edge_lidar value: "fwd"|"bwd"|"both" hoặc None
        _eld = edge_lidar.get(out_edge_key)
        edge_lidar_off = _eld is not None and (_eld == "both" or _eld == direction)
        force_lidar_off = node_lidar_off or edge_lidar_off

        # ── LIDAR restore: chỉ khi không có turn (turn tự xử lý LIDAR_ON) VÀ
        # node hiện tại không TIẾP TỤC cần tắt (force_lidar_off) — tránh bật rồi
        # tắt ngay lập tức khi 2 node liền kề CÙNG được đánh dấu lidar_off=yes
        # (map đánh dấu cả 1 đoạn dài cần tắt liên tục, không phải từng node rời
        # rạc) — trước đây bật ON vô điều kiện ngay khi tới node kế sau 1 edge
        # lidar_off, tạo khoảng hở ngắn dễ trúng vật cản giả giữa 2 node lidar_off
        # liên tiếp.
        if need_restore_lidar and turn_at_current is None and not force_lidar_off:
            steps.append({"t": tag, "a": ACTION_LIDAR_ON, "v": 0})

        # Tốc độ edge từ nút hiện tại → nút tiếp theo — luôn theo đúng tốc độ đã
        # cấu hình trên map (không tự ép chậm lại ở điểm dừng cuối nữa — người
        # dùng tự cài chậm ở edge nào cần chậm).
        spd          = _edge_speed(full_path, global_i, edge_speeds)
        spd_approach = min(spd, SPEED_SLOW)   # tốc độ tiếp cận nút rẽ

        # Tại node N-1 (ngay trước đích cuối): chèn DIR_BWD NẾU plan đang đi fwd nhưng
        # charger cần approach bwd (lùi vào). Nếu plan đã là bwd từ đầu → KHÔNG chèn thêm
        # vì DIR_BWD thứ 2 sau TURN sẽ override/cancel lệnh rẽ, làm AGV đi nhầm hướng.
        is_pre_final     = final_approach_bwd and (global_i == w_end - 1) and direction == 'fwd'

        if is_pre_final:
            print(f"[PLAN] {_agv} | node {tag}: DIR_BWD inserted (final_approach_bwd → dest={full_path[w_end]})")

        # ── Sinh steps ────────────────────────────────────────────────────────
        if turn_at_current is not None:
            # Nếu là node đầu tiên (global_i==0), không có N-1 prep → tự chèn LIDAR_OFF
            if global_i == 0:
                steps.append({"t": tag, "a": ACTION_LIDAR_OFF, "v": 0})
            steps.append({"t": tag, "a": turn_at_current, "v": 0})
            steps.append({"t": tag, "a": ACTION_LIDAR_ON, "v": 0})  # luôn ON sau rẽ

            if turn_at_next is not None:
                # Nút tiếp theo cũng rẽ → giảm tốc + tắt LIDAR ngay (cho rẽ tiếp)
                steps.append({"t": tag, "a": ACTION_SPEED,     "v": spd_approach})
                steps.append({"t": tag, "a": ACTION_LIDAR_OFF, "v": 0})
                if is_pre_final:
                    steps.append({"t": tag, "a": ACTION_DIR_BWD, "v": 0})
                steps.append({"t": tag, "a": ACTION_RUN, "v": 0})
                incoming_lidar_off = True   # LIDAR đã OFF cho rẽ tiếp
            else:
                spd_val = spd_approach if is_pre_final else spd
                steps.append({"t": tag, "a": ACTION_SPEED, "v": spd_val})
                if force_lidar_off:
                    steps.append({"t": tag, "a": ACTION_LIDAR_OFF, "v": 0})
                    incoming_lidar_off = True
                if is_pre_final:
                    steps.append({"t": tag, "a": ACTION_DIR_BWD, "v": 0})
                steps.append({"t": tag, "a": ACTION_RUN, "v": 0})

        else:
            if turn_at_next is not None:
                # Pattern N-1 trước rẽ: giảm tốc + tắt LIDAR
                steps.append({"t": tag, "a": ACTION_SPEED,     "v": spd_approach})
                steps.append({"t": tag, "a": ACTION_LIDAR_OFF, "v": 0})
                if is_pre_final:
                    steps.append({"t": tag, "a": ACTION_DIR_BWD, "v": 0})
                steps.append({"t": tag, "a": ACTION_RUN, "v": 0})
                incoming_lidar_off = True   # LIDAR đã OFF cho rẽ
            else:
                # Đi thẳng
                if is_pre_final:
                    steps.append({"t": tag, "a": ACTION_SPEED,   "v": SPEED_SLOW})
                    steps.append({"t": tag, "a": ACTION_DIR_BWD, "v": 0})
                    steps.append({"t": tag, "a": ACTION_RUN,     "v": 0})
                else:
                    steps.append({"t": tag, "a": ACTION_SPEED, "v": spd})
                    if force_lidar_off:
                        steps.append({"t": tag, "a": ACTION_LIDAR_OFF, "v": 0})
                        incoming_lidar_off = True
                    steps.append({"t": tag, "a": ACTION_RUN, "v": 0})

    return steps


# ── Public API ─────────────────────────────────────────────────────────────────

def build_plan_window(
    full_path:           list[str | int],
    w_start:             int,
    w_end:               int,
    points:              dict,
    is_final:            bool,
    task_type:           str  = "delivery",
    cmd_id:              str | None = None,
    node_actions:        dict = {},
    direction:           str  = "fwd",   # "fwd" | "bwd"
    edge_speeds:         dict = {},      # {"{src}_{dst}": speed_byte}
    edge_lidar:          dict = {},      # {"{src}_{dst}": True} edge có lidar_off
    agv_id:              str  = "?",
    initial_prev_tag:    str | None = None,  # hướng xe trước node đầu tiên
    initial_arrived_bwd: bool = False,       # True khi xe đến start node theo chiều lùi
) -> dict:
    """
    Build plan cho cửa sổ [w_start, w_end] trong full_path.

    Args:
        points:       {node_id_str: (x, y)} từ map_manager.points
        node_actions: {node_id_str: action_dict} từ map_manager.node_actions
        direction:    "fwd" | "bwd"
        edge_speeds:  {"{src}_{dst}": speed_byte} — tốc độ per-edge, build bằng build_edge_speeds()
        edge_lidar:   {"{src}_{dst}": True} — đoạn đường tắt LIDAR, build bằng build_edge_lidar()
    """
    if cmd_id is None:
        cmd_id = str(uuid.uuid4())[:8]

    str_path = [str(p) for p in full_path]
    steps    = _build_steps(str_path, w_start, w_end, points, is_final,
                            task_type, node_actions, direction, edge_speeds, edge_lidar,
                            agv_id, initial_prev_tag, initial_arrived_bwd)

    return {"c": "plan", "id": cmd_id, "d": steps}


def build_line_plan(
    path:                list[str | int],
    points:              dict,
    task_type:           str  = "delivery",
    cmd_id:              str | None = None,
    node_actions:        dict = {},
    direction:           str  = "fwd",
    edge_speeds:         dict = {},      # {"{src}_{dst}": speed_byte}
    edge_lidar:          dict = {},      # {"{src}_{dst}": True} build bằng build_edge_lidar()
    agv_id:              str  = "?",
    initial_prev_tag:    str | None = None,
    initial_arrived_bwd: bool = False,   # True khi xe đến start node theo chiều lùi (charger exit)
) -> dict:
    """
    Build plan đầy đủ (không rolling) cho path.

    Args:
        node_actions:        {nid: action_dict} từ map_manager.node_actions
        direction:           "fwd" | "bwd"
        edge_speeds:         build bằng build_edge_speeds(map_manager.roads)
        edge_lidar:          build bằng build_edge_lidar(map_manager.roads)
        initial_arrived_bwd: True nếu xe vừa đến start node theo chiều lùi (charger exit).
                             False (default) cho tất cả trường hợp còn lại (fwd arrival, staging...).
    """
    return build_plan_window(
        full_path=path,
        w_start=0,
        w_end=len(path) - 1,
        points=points,
        is_final=True,
        task_type=task_type,
        cmd_id=cmd_id,
        node_actions=node_actions,
        direction=direction,
        edge_speeds=edge_speeds,
        edge_lidar=edge_lidar,
        agv_id=agv_id,
        initial_prev_tag=initial_prev_tag,
        initial_arrived_bwd=initial_arrived_bwd,
    )


def build_edge_lidar(roads: list) -> dict:
    """
    Xây dict edge_lidar từ map_manager.roads.

    Trả về: {"{src}_{dst}": "fwd"|"bwd"|"both"} cho mỗi edge cần tắt LIDAR.
    - lidar_off_dir = "fwd"  → chỉ tắt khi xe đi chiều tiến (src→dst)
    - lidar_off_dir = "bwd"  → chỉ tắt khi xe đi chiều lùi  (src→dst với direction=bwd)
    - lidar_off_dir = "both" → tắt cả 2 chiều
    - Nếu chỉ có boolean lidar_off=True (dữ liệu cũ): coi là "both"
    """
    result: dict = {}
    for r in roads:
        src = str(r.get("id_source", "")).strip()
        dst = str(r.get("id_dest",   "")).strip()
        if not src or not dst:
            continue
        # Ưu tiên lidar_off_dir (mới) nếu có
        ldir = str(r.get("lidar_off_dir") or "none").strip().lower()
        if ldir in ("fwd", "bwd", "both"):
            result[f"{src}_{dst}"] = ldir
        elif r.get("lidar_off"):
            # Fallback dữ liệu cũ (boolean): coi là cả 2 chiều
            result[f"{src}_{dst}"] = "both"
    return result


def build_edge_speeds(roads: list) -> dict:
    """
    Xây dict edge_speeds từ map_manager.roads.

    roads: [{id_source, id_dest, speed (m/s), speed_bwd (m/s, tuỳ chọn), ...}]
    Trả về: {"{src}_{dst}": speed_byte, "{dst}_{src}": speed_byte}

    Công thức: speed_byte = int(speed_m_s * 240)
      → 0.5 m/s = 120 = SPEED_FAST  (tốc độ mặc định map editor)
      → 0.25 m/s = 60 = SPEED_SLOW

    speed_bwd (chiều về, dst→src) là TUỲ CHỌN — nếu không cấu hình (None/0),
    dùng chung giá trị speed (chiều đi) cho cả 2 chiều như trước đây. _edge_speed()
    tra theo đúng thứ tự node THẬT SỰ đi qua trong path nên không cần biết "fwd/bwd"
    theo nghĩa lượt chạy — chỉ cần 2 key riêng biệt ở đây là đủ áp dụng đúng hướng.
    """
    result: dict = {}
    for r in roads:
        src = str(r.get("id_source", "")).strip()
        dst = str(r.get("id_dest",   "")).strip()
        speed_ms = float(r.get("speed", 0) or 0)
        if not src or not dst or speed_ms <= 0:
            continue
        byte_val = ms_to_speed_byte(speed_ms)
        result[f"{src}_{dst}"] = byte_val

        speed_bwd_ms = r.get("speed_bwd")
        if speed_bwd_ms is not None and float(speed_bwd_ms) > 0:
            result[f"{dst}_{src}"] = ms_to_speed_byte(float(speed_bwd_ms))
        else:
            result[f"{dst}_{src}"] = byte_val   # chưa cấu hình riêng → dùng chung chiều đi
    return result


def first_window_end(full_path: list) -> int:
    """Tính index kết thúc cửa sổ đầu tiên."""
    return min(LOOKAHEAD, len(full_path) - 1)
