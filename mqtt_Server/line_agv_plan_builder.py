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

SPEED_FAST     = 120   # byte mặc định khi edge không cấu hình speed
SPEED_SLOW     = 60    # byte tốc độ tiếp cận nút rẽ (N-1 pattern)
LOOKAHEAD      = 6
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
) -> tuple[int | None, str]:
    """
    Trả về (action, source) với action = ACTION_TURN_R | ACTION_TURN_L | None.

    Ưu tiên:
    1a. turn_map["{from}_{to}_{direction}"] — explicit có chiều
    1b. turn_map["{from}_{to}"] — explicit không chiều (fallback)
    2.  Coordinate geometry (get_turn_direction)
    3.  Legacy fwd_turn / bwd_turn config — backward compat
    """
    act = node_actions.get(str(tag_str), {}) if node_actions else {}

    # ── Priority 1: turn_map lookup ──────────────────────────────────────────
    if from_tag and to_tag:
        turn_map = act.get("turn_map") or {}
        key_dir  = f"{from_tag}_{to_tag}_{direction}"
        key_any  = f"{from_tag}_{to_tag}"
        if key_dir in turn_map:
            val = str(turn_map[key_dir]).lower()
            src = f"turn_map:{key_dir}={val}"
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
    if from_tag and to_tag:
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
    fwd_geo = get_turn_direction(from_tag, tag_str, to_tag, points)
    if fwd_geo is not None:
        inv = _invert_turn(fwd_geo)
        return inv, "geometry [bwd_arrival,inverted]"

    # 4. Legacy bwd_turn (đã xử lý đảo chiều trong _resolve_turn với direction='bwd')
    return _resolve_turn(tag_str, from_tag, to_tag, points, node_actions, "bwd")


# ── Step builder ───────────────────────────────────────────────────────────────

def _edge_speed(path: list[str], gi: int, edge_speeds: dict) -> int:
    """Tốc độ byte cho edge path[gi]→path[gi+1]. Fallback SPEED_FAST nếu không có."""
    if not edge_speeds or gi + 1 >= len(path):
        return SPEED_FAST
    return edge_speeds.get(f"{path[gi]}_{path[gi + 1]}", SPEED_FAST)


def _build_steps(
    full_path:         list[str],
    w_start:           int,
    w_end:             int,
    points:            dict,
    is_final:          bool,
    task_type:         str,
    node_actions:      dict = {},    # {nid: {fwd_turn, bwd_turn, ...}}
    direction:         str  = "fwd", # "fwd" | "bwd"
    edge_speeds:       dict = {},    # {"src_dst": speed_byte} từ map_manager.roads
    edge_lidar:        dict = {},    # {"src_dst": True} edge có lidar_off từ map editor
    _agv:              str  = "?",
    initial_prev_tag:  str | None = None,  # hướng xe trước node đầu tiên (dùng khi w_start==0)
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

    # Kiểm tra node đích có cấu hình approach_dir=bwd không (lùi vào trạm sạc)
    dest_node_act      = node_actions.get(str(full_path[w_end]), {}) if full_path else {}
    final_approach_bwd = (
        is_final
        and str(dest_node_act.get("approach_dir") or "").lower() == "bwd"
    )

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
            if need_restore_lidar:
                steps.append({"t": tag, "a": ACTION_LIDAR_ON, "v": 0})
            if is_final:
                node_cfg     = node_actions.get(str(tag), {})
                arrival_cfg  = str(node_cfg.get("arrival_action") or "").lower()
                if task_type == "transit":
                    # Đoạn lùi tạm — không áp dụng arrival_action, luôn WAIT_SYS
                    _arr = ACTION_WAIT_SYS
                elif arrival_cfg == "wait_sys":
                    _arr = ACTION_WAIT_SYS
                elif arrival_cfg == "wait_user":
                    _arr = ACTION_WAIT_USER
                elif arrival_cfg == "wait_charge":
                    _arr = ACTION_WAIT_CHARGE
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
            if _using_initial_prev:
                if direction == "fwd":
                    # Hiếm gặp: arrived bwd, new plan fwd → bù đảo chiều
                    turn_at_current, _turn_src_cur = _resolve_turn_bwd_arrival(
                        tag_str,
                        _from_for_turn,
                        full_path[global_i + 1],
                        points, node_actions,
                    )
                else:
                    # AGV vừa đến bwd, tiếp tục bwd → turn bình thường theo direction=bwd
                    turn_at_current, _turn_src_cur = _resolve_turn(
                        tag_str,
                        _from_for_turn,
                        full_path[global_i + 1],
                        points, node_actions,
                        direction,
                    )
            else:
                turn_at_current, _turn_src_cur = _resolve_turn(
                    tag_str,
                    _from_for_turn,
                    full_path[global_i + 1],
                    points, node_actions, direction,
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
            )

        # ── LIDAR restore: chỉ khi không có turn (turn tự xử lý LIDAR_ON) ────
        if need_restore_lidar and turn_at_current is None:
            steps.append({"t": tag, "a": ACTION_LIDAR_ON, "v": 0})

        # ── Kiểm tra LIDAR config cho edge ra / node hiện tại ────────────────
        out_edge_key   = f"{tag_str}_{full_path[global_i + 1]}"
        node_lidar_off = str(node_actions.get(tag_str, {}).get("lidar_off", "no")).lower() == "yes"
        # edge_lidar value: "fwd"|"bwd"|"both" hoặc None
        _eld = edge_lidar.get(out_edge_key)
        edge_lidar_off = _eld is not None and (_eld == "both" or _eld == direction)
        force_lidar_off = node_lidar_off or edge_lidar_off

        # Tốc độ edge từ nút hiện tại → nút tiếp theo
        spd          = _edge_speed(full_path, global_i, edge_speeds)
        spd_approach = min(spd, SPEED_SLOW)

        # Tại node N-1 (ngay trước đích cuối): chèn DIR_BWD nếu approach_dir=bwd
        is_pre_final = final_approach_bwd and (global_i == w_end - 1)
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
    full_path:         list[str | int],
    w_start:           int,
    w_end:             int,
    points:            dict,
    is_final:          bool,
    task_type:         str  = "delivery",
    cmd_id:            str | None = None,
    node_actions:      dict = {},
    direction:         str  = "fwd",   # "fwd" | "bwd"
    edge_speeds:       dict = {},      # {"{src}_{dst}": speed_byte}
    edge_lidar:        dict = {},      # {"{src}_{dst}": True} edge có lidar_off
    agv_id:            str  = "?",
    initial_prev_tag:  str | None = None,  # hướng xe trước node đầu tiên
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
                            agv_id, initial_prev_tag)

    return {"c": "plan", "id": cmd_id, "d": steps}


def build_line_plan(
    path:              list[str | int],
    points:            dict,
    task_type:         str  = "delivery",
    cmd_id:            str | None = None,
    node_actions:      dict = {},
    direction:         str  = "fwd",
    edge_speeds:       dict = {},      # {"{src}_{dst}": speed_byte}
    edge_lidar:        dict = {},      # {"{src}_{dst}": True} build bằng build_edge_lidar()
    agv_id:            str  = "?",
    initial_prev_tag:  str | None = None,
) -> dict:
    """
    Build plan đầy đủ (không rolling) cho path.

    Args:
        node_actions: {nid: action_dict} từ map_manager.node_actions
        direction:    "fwd" | "bwd"
        edge_speeds:  build bằng build_edge_speeds(map_manager.roads)
        edge_lidar:   build bằng build_edge_lidar(map_manager.roads)
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

    roads: [{id_source, id_dest, speed (m/s), ...}]
    Trả về: {"{src}_{dst}": speed_byte, "{dst}_{src}": speed_byte}

    Công thức: speed_byte = int(speed_m_s * 240)
      → 0.5 m/s = 120 = SPEED_FAST  (tốc độ mặc định map editor)
      → 0.25 m/s = 60 = SPEED_SLOW
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
        result[f"{dst}_{src}"] = byte_val   # cả 2 chiều dùng cùng giới hạn tốc độ
    return result


def first_window_end(full_path: list) -> int:
    """Tính index kết thúc cửa sổ đầu tiên."""
    return min(LOOKAHEAD, len(full_path) - 1)
