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

SPEED_FAST     = 120
SPEED_SLOW     = 60
LOOKAHEAD      = 6
RETRY_TIMEOUT  = 4.0   # giây, thời gian chờ ACK trước khi retry


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
    Nếu bản đồ dùng tọa độ màn hình (Y tăng xuống) thì kết quả ngược lại — điều chỉnh
    hằng số MAP_Y_DOWN nếu cần.
    """
    MAP_Y_DOWN = False   # True nếu Y tăng xuống (tọa độ màn hình)

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
    direction:    str,          # "fwd" | "bwd"
) -> int | None:
    """
    Trả về ACTION_TURN_R, ACTION_TURN_L, hoặc None (đi thẳng).
    Ưu tiên: explicit config trong node_actions > tính từ tọa độ.
    Với chiều lùi (bwd): dùng bwd_turn; nếu không có thì đảo chiều fwd_turn.
    """
    act = node_actions.get(str(tag_str), {})

    if direction == "bwd":
        explicit = str(act.get("bwd_turn") or "none").lower()
        # Nếu bwd_turn không cấu hình, thử đảo fwd_turn
        if explicit == "none":
            fwd = str(act.get("fwd_turn") or "none").lower()
            if fwd == "right":
                explicit = "left"
            elif fwd == "left":
                explicit = "right"
    else:
        explicit = str(act.get("fwd_turn") or "none").lower()

    if explicit == "right":
        return ACTION_TURN_R
    if explicit == "left":
        return ACTION_TURN_L

    # Fallback: tính từ tọa độ nếu có đủ thông tin
    if from_tag and to_tag:
        return get_turn_direction(from_tag, tag_str, to_tag, points)
    return None


# ── Step builder ───────────────────────────────────────────────────────────────

def _build_steps(
    full_path:    list[str],
    w_start:      int,
    w_end:        int,
    points:       dict,
    is_final:     bool,
    task_type:    str,
    node_actions: dict = {},    # {nid: {fwd_turn, bwd_turn, ...}}
    direction:    str  = "fwd", # "fwd" | "bwd"
) -> list[dict]:
    """
    Tạo action steps cho cửa sổ full_path[w_start..w_end].
    Dùng full_path làm context để tính turn chính xác ở biên cửa sổ.
    """
    steps   = []
    n_full  = len(full_path)
    w_len   = w_end - w_start + 1

    # Đặt chiều đi ở bước đầu tiên của cửa sổ đầu tiên
    if w_start == 0:
        dir_action = ACTION_DIR_BWD if direction == "bwd" else ACTION_DIR_FWD
        first_tag  = int(full_path[0]) if full_path else 0
        steps.append({"t": first_tag, "a": dir_action, "v": 0})

    for local_i in range(w_len):
        global_i = w_start + local_i
        tag      = int(full_path[global_i])
        is_last  = (local_i == w_len - 1)

        # ── Thẻ cuối cửa sổ ───────────────────────────────────────────────────
        if is_last:
            if is_final:
                if task_type in ("delivery", "pickup"):
                    steps.append({"t": tag, "a": ACTION_WAIT_USER,   "v": 0})
                elif task_type == "return_charge":
                    steps.append({"t": tag, "a": ACTION_WAIT_CHARGE, "v": 0})
                else:
                    steps.append({"t": tag, "a": ACTION_WAIT_SYS,    "v": 0})
            else:
                # Cuối cửa sổ trung gian → WAIT_SYS, Python sẽ gửi cửa sổ tiếp
                steps.append({"t": tag, "a": ACTION_WAIT_SYS, "v": 0})
            break

        # ── Rẽ TẠI NÚT HIỆN TẠI (đến từ global_i-1, đi tiếp global_i+1) ──────
        turn_at_current = None
        if global_i > 0 and global_i + 1 < n_full:
            turn_at_current = _resolve_turn(
                full_path[global_i],
                full_path[global_i - 1],
                full_path[global_i + 1],
                points, node_actions, direction,
            )

        # ── Rẽ TẠI NÚT TIẾP THEO (từ global_i → global_i+1 → global_i+2) ─────
        turn_at_next = None
        if global_i + 2 < n_full:
            turn_at_next = _resolve_turn(
                full_path[global_i + 1],
                full_path[global_i],
                full_path[global_i + 2],
                points, node_actions, direction,
            )

        # ── Sinh steps ────────────────────────────────────────────────────────
        if turn_at_current is not None:
            # Thực hiện rẽ (LIDAR_OFF đã được set từ thẻ N-1 trước đó)
            steps.append({"t": tag, "a": turn_at_current, "v": 0})
            steps.append({"t": tag, "a": ACTION_LIDAR_ON, "v": 0})
            if turn_at_next is not None:
                # Thẻ tiếp theo cũng rẽ → cần giảm tốc + tắt LIDAR ngay
                steps.append({"t": tag, "a": ACTION_SPEED,    "v": SPEED_SLOW})
                steps.append({"t": tag, "a": ACTION_LIDAR_OFF, "v": 0})
                steps.append({"t": tag, "a": ACTION_RUN,       "v": 0})
            else:
                steps.append({"t": tag, "a": ACTION_SPEED, "v": SPEED_FAST})
                steps.append({"t": tag, "a": ACTION_RUN,   "v": 0})
        else:
            if turn_at_next is not None:
                # Thẻ tiếp theo rẽ → giảm tốc + tắt LIDAR NGAY TẠI ĐÂY (pattern N-1)
                steps.append({"t": tag, "a": ACTION_SPEED,    "v": SPEED_SLOW})
                steps.append({"t": tag, "a": ACTION_LIDAR_OFF, "v": 0})
                steps.append({"t": tag, "a": ACTION_RUN,       "v": 0})
            else:
                # Đi thẳng
                steps.append({"t": tag, "a": ACTION_SPEED, "v": SPEED_FAST})
                steps.append({"t": tag, "a": ACTION_RUN,   "v": 0})

    return steps


# ── Public API ─────────────────────────────────────────────────────────────────

def build_plan_window(
    full_path:    list[str | int],
    w_start:      int,
    w_end:        int,
    points:       dict,
    is_final:     bool,
    task_type:    str  = "delivery",
    cmd_id:       str | None = None,
    node_actions: dict = {},
    direction:    str  = "fwd",   # "fwd" | "bwd"
) -> dict:
    """
    Build plan cho cửa sổ [w_start, w_end] trong full_path.

    Args:
        full_path:    Toàn bộ đường đi (list node ID str/int)
        points:       {node_id_str: (x, y)} từ map_manager.points
        node_actions: {node_id_str: {fwd_turn, bwd_turn, ...}} từ map_manager.node_actions
        direction:    "fwd" (tiến) | "bwd" (lùi) — ảnh hưởng DIR_FWD/BWD và chiều rẽ
    """
    if cmd_id is None:
        cmd_id = str(uuid.uuid4())[:8]

    str_path = [str(p) for p in full_path]
    steps    = _build_steps(str_path, w_start, w_end, points, is_final,
                            task_type, node_actions, direction)

    return {"c": "plan", "id": cmd_id, "d": steps}


def build_line_plan(
    path:         list[str | int],
    points:       dict,
    task_type:    str  = "delivery",
    cmd_id:       str | None = None,
    node_actions: dict = {},
    direction:    str  = "fwd",
) -> dict:
    """
    Build plan đầy đủ (không rolling) cho path.

    Args:
        node_actions: {nid: {fwd_turn, bwd_turn}} từ map_manager.node_actions
        direction:    "fwd" (tiến) | "bwd" (lùi)
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
    )


def first_window_end(full_path: list) -> int:
    """Tính index kết thúc cửa sổ đầu tiên."""
    return min(LOOKAHEAD, len(full_path) - 1)
