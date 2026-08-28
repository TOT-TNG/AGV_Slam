"""
line_agv_handler.py — Handler cho Line AGV (RFID-based)
---------------------------------------------------------
Nhận MQTT state từ Line AGV (format v2), parse, cập nhật state store,
và thông báo cho VDA5050 traffic engine về edge đang bị chiếm.

State format Line AGV nhận được:
  {
    "lastNodeId": "101",        ← tag RFID hiện tại (string hoặc int)
    "tag": 101,                 ← backward compat
    "prev_tag": 100,            ← tag trước đó (tính hướng đi)
    "ack": "cmd_id",            ← xác nhận lệnh
    "driving": false,
    "paused": false,
    "batteryState": {"batteryCharge": 85},
    "battery": 85,              ← backward compat
    "battery_low": false,
    "battery_blocking": false,
    "event": "confirm" | "return" | "battery_need_charge",
    "operatingMode": "AUTOMATIC",
    "errors": [],
  }

Cross-type integration:
  - Khi LINE AGV chiếm edge (prev→cur), edge ID tương ứng được đưa vào
    _line_blocked_edges. VDA5050 route planner có thể query để tránh cạnh này.
  - Naming convention edge: "{from_tag}_to_{to_tag}" (khớp với VDA5050 map nếu
    cùng dùng integer node ID).
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from typing import Optional, Callable, Union

from agv_registry import agv_registry
from line_agv_plan_builder import (
    build_plan_window,
    first_window_end,
    LOOKAHEAD,
    RETRY_TIMEOUT,
    ACTION_HOOK_RAISE,
)

# Ngưỡng thời gian không nhận state → coi là OFFLINE
OFFLINE_TIMEOUT_SEC = 30.0  # Line AGV chỉ pub state khi di chuyển — cần timeout dài hơn VDA5050

# Thời gian vật cản duy trì trước khi tự reroute
OBSTACLE_REROUTE_TIMEOUT = 5.0   # giây

# Xe phải đứng yên GIỮA route đủ lâu (đường phía trước thông) mới gửi-lại cửa sổ cứu
# kẹt — đủ dài để KHÔNG ghi đè plan vừa dispatch (xe mới tới node chưa kịp chạy).
STUCK_RESEND_GRACE = 8.0   # giây — tăng từ 4.0 để giảm tần suất gửi lại khi kẹt
STUCK_RESEND_COOLDOWN = 7.0   # giây giữa các lần gửi lại liên tiếp — tăng từ 3.0

# Lệnh NÂNG MÓC ('action' rời rạc, KHÔNG nằm trong cơ chế resend plan/rolling-window
# ở trên) — nếu gói MQTT bị rớt giữa đường, xe không hề nhận được lệnh, không có
# hook_raised/hook_raise_failed nào quay về → đứng chờ vô thời hạn. Gửi lại tối đa
# HOOK_RAISE_MAX_RETRIES lần nếu không thấy phản hồi sau HOOK_RAISE_TIMEOUT giây.
HOOK_RAISE_TIMEOUT     = 6.0
HOOK_RAISE_MAX_RETRIES = 2

# Số node nhìn trước để phát hiện conflict chủ động (tách khỏi LOOKAHEAD window)
# Yêu cầu an toàn: xe phải PHÁT HIỆN và XỬ LÝ né tránh khi còn cách nhau 5-6 node
# (cộng với reservation 5 node của xe kia → quyết định được đưa ra từ rất xa).
TRAFFIC_LOOKAHEAD = 6

# Số node ĐỆM giữ lại trước điểm conflict khi buộc phải DỪNG CHỜ head-on:
# dừng tại (conflict_at - HEADON_STANDOFF), KHÔNG dừng sát node tranh chấp
# → 2 xe không bao giờ đứng kề nhau trong tầm LIDAR rồi rơi vào obstacle reactive.
HEADON_STANDOFF = 2

# Cooldown giữa 2 lần LÙI nhường đường của cùng 1 xe (chống ping-pong lùi↔tiến).
BACKUP_COOLDOWN = 30.0

# Cooldown giữa 2 lần REROUTE-do-obstacle (avoid_all) của cùng 1 xe. Chống DAO ĐỘNG
# (flip-flop): 2 xe ở gần nhau, mỗi obstacle-timeout (5s) lại reroute lật sang nhánh kia
# của vòng (16-8-15 ⇄ 16-7-6-17) → plan-race (firmware chạy plan cũ, server gửi plan mới)
# → kẹt. Sau 1 lần reroute, xe COMMIT nhánh đó tối thiểu REROUTE_COOLDOWN giây (gặp lại
# obstacle thì CHỜ tại chỗ thay vì lật lại). KHÔNG chặn reroute đầu tiên; KHÔNG áp cho
# né head-on chủ động (avoid_all=False).
REROUTE_COOLDOWN = 18.0


def _charger_exit_direction(start_node: str, proposed_dir: str) -> str:
    """
    Tổng quát: bất kỳ node nào là CHARGER (locationType=CHARGER hoặc
    arrival_action=wait_charge) thì chỉ có thể THOÁT bằng tiến (fwd).
    Đằng sau trạm sạc không có đường — không bao giờ lùi thêm từ trạm.
    Dùng ở mọi chỗ xây dựng transit plan bắt đầu từ một node bất kỳ.
    """
    try:
        from mqtt_client import map_manager as _mm
        na = getattr(_mm, 'node_actions', {}) or {}
        cfg = na.get(str(start_node), {}) or {}
        if (str(cfg.get('locationType', '')).upper() == 'CHARGER'
                or str(cfg.get('arrival_action', '')).lower() == 'wait_charge'):
            return 'fwd'
    except Exception:
        pass
    return proposed_dir


def requester_closer_than_claimer(graph, requester_node, claimer_node, dest_node) -> bool:
    """True nếu xe YÊU CẦU gần ĐÍCH hơn xe đang 'claim' đích (cùng đích, claimer chưa ở
    vật lý tại đích — chỉ đang trên đường tới). Dùng ở dispatch để KHÔNG bắt xe gần phải
    chờ xe xa khi cùng tới 1 điểm lấy/giao (tránh "node chưa có xe mà báo occupied" + tránh
    deadlock khi xe gần đang đứng TRÊN đường xe xa tới đích). So bằng số cạnh shortest path
    trên đồ thị line. Lỗi/không có đường → False (giữ hành vi chờ cũ, an toàn)."""
    if graph is None or requester_node is None or claimer_node is None or dest_node is None:
        return False
    try:
        import networkx as _nx
        return (_nx.shortest_path_length(graph, str(requester_node), str(dest_node))
                < _nx.shortest_path_length(graph, str(claimer_node), str(dest_node)))
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# LineAGVState — snapshot trạng thái 1 Line AGV
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class LineAGVState:
    agv_id:           str            = ""
    current_tag:      Optional[int]  = None  # None cho đến khi nhận RFID đầu tiên
    prev_tag:         int            = 0     # tag trước đó
    next_tag:         int            = 0     # tag tiếp theo (từ route đang chạy)
    battery:          int   = 0
    battery_low:      bool  = False
    battery_blocking: bool  = False
    driving:          bool  = False
    paused:           bool  = False
    operating_mode:   str   = "MANUAL"
    connection_state: str   = "OFFLINE"
    error_code:       int   = 0
    last_update:      float = 0.0   # 0 cho đến khi nhận state message đầu tiên
    last_ack:         str   = ""    # cmd_id vừa được AGV ACK

    # Edge đang chiếm: (from_tag, to_tag) — None nếu đứng yên tại node
    current_edge_pair: Optional[tuple[int, int]] = None

    # Task lifecycle: "picking" (đến điểm lấy hàng, WAIT_SYS) | "delivering" (đến điểm giao, WAIT_USER) | None
    task_lifecycle: Optional[str] = None

    # Hướng di chuyển của transit vừa hoàn thành ("fwd"/"bwd"/"") — dùng để xác định hướng plan tiếp theo
    last_transit_direction: str = ""

    # Hướng vật lý của plan gần nhất đã thực thi (fwd/bwd) — dùng làm baseline khi tính hướng plan mới
    last_plan_direction: str = "fwd"

    # Obstacle tracking: ghi nhận khi firmware báo 'obstacle', clear khi 'obstacle_cleared'
    obstacle_since:     Optional[float] = None   # monotonic timestamp lúc obstacle bắt đầu
    obstacle_direction: str             = ""     # hướng xe khi gặp vật cản ("fwd"/"bwd")

    # Tích lũy các node bị chặn vật lý qua nhiều lần reroute liên tiếp.
    # Clear khi AGV thực sự đi sang tag mới (tránh dao động giữa 2 đường).
    accumulated_blocked: "set[str]" = field(default_factory=set)

    # Bounce-detected dispatch retry: khi go_charge/go_wait phát hiện bounce và không dispatch
    # được, lưu tên lệnh để _check_waiting_agvs trigger lại khi xe cản đã rời đi.
    pending_retry_cmd: Optional[str] = None   # 'go_charge' | 'go_wait' | 'go_to' | None
    pending_retry_dest: Optional[str] = None  # destination cho pending_retry_cmd='go_to'
    pending_retry_session: Optional[str] = None  # session_id GIỮ để retry go_to bỏ-qua-supply đúng

    # ── Trạng thái ĐÃ NHƯỜNG (yield) — xe THUA đỗ né siding/đi vòng, GIỮ lệnh gốc, CHỜ
    # winner đi qua rồi mới resume (qua _check_waiting_agvs). Tách RIÊNG pending_retry để
    # KHÔNG bị xoá khi xe đang LÁI tới siding (pending_retry bị xoá lúc driving=True).
    yield_cmd:     Optional[str]  = None   # lệnh gốc giữ lại: go_charge|go_wait|go_to
    yield_dest:    Optional[str]  = None
    yield_session: Optional[str]  = None
    yield_winner:  Optional[str]  = None   # xe THẮNG cần chờ đi qua
    yield_path:    "Optional[list]" = None # path gốc (đang conflict) — resume khi winner rời hẳn

    # ── Móc hàng (xe rơ-moóc/đầu kéo) — MỚI ──────────────────────────────────
    hook_state:   Optional[str] = None   # "raised" | "lowered" | None (chưa rõ)
    hook_pending: Optional[str] = None   # "pickup" | "dropoff" | None — đang chờ kết quả nâng/hạ ở đâu
    hook_raise_sent_at:  float = 0.0   # time.monotonic() lúc gửi lệnh NÂNG móc gần nhất (0 = chưa gửi/đã xong)
    hook_raise_retries:  int   = 0     # số lần đã gửi lại do không thấy phản hồi
    hook_report_seq_seen: int  = 0     # hook_report_seq mới nhất đã xử lý (dedupe — firmware lặp lại report mỗi
                                        # gói state cho tới khi ACK, tránh xử lý trùng)
    hook_fallback_notified: bool = False  # đã báo lỗi móc qua kênh "hook" (up_fail/dn_fail) cho đợt hiện tại
                                           # chưa — tránh gọi lại _notify_hook_error mỗi 1.5s khi còn kẹt

    # ── Chạy thử thủ công đến 1 tag (không cần map) — MỚI ────────────────────
    test_drive_target: Optional[str] = None   # tag cần dừng khi tới, None = không có chạy thử đang chờ
    test_drive_seq:    int = 0   # tăng mỗi lần bắt đầu chạy thử mới — vòng lặp gửi lại "deba" cũ tự thoát khi lệch seq

    # ── Dò vị trí bằng deba trước khi Về trạm (xe mất vị trí do bị đẩy tay/mới bật) ──
    locate_then_charge_seq: int = 0   # tăng mỗi lần bắt đầu dò vị trí mới — vòng lặp cũ tự thoát khi lệch seq

    # ── Lidar khi lái thủ công (D-pad / Chạy thử đến node) — MỚI ─────────────
    manual_lidar_off: Optional[bool] = None   # trạng thái Lidar đã gửi lần gần nhất khi lái thủ công (None = chưa rõ)


# ═══════════════════════════════════════════════════════════════════════════════
# LineAGVRoute — rolling plan state cho 1 Line AGV
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class LineAGVRoute:
    full_path:    list         # list[str] — toàn bộ đường đi
    task_type:    str  = "delivery"
    direction:    str  = "fwd" # "fwd" | "bwd" — hướng vật lý của plan này
    window_start: int  = 0    # index đầu cửa sổ hiện tại trong full_path
    window_end:   int  = 0    # index cuối cửa sổ hiện tại (inclusive)
    sent_cmd_id:  str  = ""   # cmd_id của plan vừa gửi
    sent_at:      float = 0.0 # thời điểm gửi plan cuối
    acked:        bool = False # đã nhận ACK cho plan này chưa
    is_complete:  bool = False # True khi cửa sổ cuối đã được gửi

    # Conflict-aware stop: node cuối cùng được gửi trước vùng tranh chấp
    # Khi != None → AGV đang chờ tại node này, chưa được phép tiến vào path tiếp theo
    waiting_before_conflict: Optional[str] = None

    # True khi dispatch ban đầu (main.py:_dispatch_go_to) có prepend các bước
    # 1-LẦN-DUY-NHẤT tại full_path[0] (vd _trailer_exit_steps: tắt Lidar + lùi mù +
    # quay đầu cho xe rơ-moóc rời trạm sạc) KHÔNG nằm trong build_plan_window —
    # resend window trong lúc AGV còn ở full_path[0] sẽ làm MẤT các bước đó (xe hiểu
    # nhầm thành tiến thẳng). Dùng để watchdog cứu-kẹt biết KHÔNG được resend khi
    # current_idx == 0 cho route này (xem _on_state, khối "CỨU KẸT: DỪNG GIỮA route").
    has_exit_steps: bool = False


# ═══════════════════════════════════════════════════════════════════════════════
# LineAGVStateStore
# ═══════════════════════════════════════════════════════════════════════════════

class LineAGVStateStore:
    def __init__(self):
        self._states: dict[str, LineAGVState] = {}

    def get(self, agv_id: str) -> Optional[LineAGVState]:
        return self._states.get(str(agv_id))

    def get_or_create(self, agv_id: str) -> LineAGVState:
        if agv_id not in self._states:
            self._states[agv_id] = LineAGVState(agv_id=agv_id)
        return self._states[agv_id]

    def all(self) -> dict[str, LineAGVState]:
        return dict(self._states)

    def snapshot(self) -> list[dict]:
        result = []
        for s in self._states.values():
            result.append({
                "agv_id":          s.agv_id,
                "current_tag":     s.current_tag,   # Optional[int]
                "prev_tag":        s.prev_tag,
                "next_tag":        s.next_tag,
                "battery":         s.battery,
                "battery_low":     s.battery_low,
                "battery_blocking": s.battery_blocking,
                "driving":         s.driving,
                "paused":          s.paused,
                "operating_mode":  s.operating_mode,
                "connection":      s.connection_state,
                "last_update":     s.last_update,
                "task_lifecycle":  s.task_lifecycle,
                "current_edge":    (f"{s.current_edge_pair[0]}→{s.current_edge_pair[1]}"
                                    if s.current_edge_pair else None),
            })
        return result


# ═══════════════════════════════════════════════════════════════════════════════
# Cross-type edge blocking
# ═══════════════════════════════════════════════════════════════════════════════

_line_blocked_edges: dict[str, str] = {}  # {edge_id: agv_id}


def get_line_agv_blocked_edges() -> list[str]:
    """VDA5050 route planner gọi hàm này để tránh các cạnh Line AGV đang chiếm."""
    return list(_line_blocked_edges.keys())


def _reserve_line_edge(agv_id: str, from_tag: int, to_tag: int) -> None:
    edge_id = f"{from_tag}_to_{to_tag}"
    _line_blocked_edges[edge_id] = agv_id
    print(f"[LINE_AGV] {agv_id}: reserve edge {edge_id}")


def _release_line_edge(agv_id: str, from_tag: int, to_tag: int) -> None:
    edge_id = f"{from_tag}_to_{to_tag}"
    if _line_blocked_edges.get(edge_id) == agv_id:
        del _line_blocked_edges[edge_id]
        print(f"[LINE_AGV] {agv_id}: release edge {edge_id}")


def _release_all_line_edges(agv_id: str) -> None:
    keys = [k for k, v in _line_blocked_edges.items() if v == agv_id]
    for k in keys:
        del _line_blocked_edges[k]
    if keys:
        print(f"[LINE_AGV] {agv_id}: released all edges {keys}")


# ── Chặng "lấy hàng rỗng cố định gần trạm" (đầu quy trình, trước khi ra Tổ) ──
# Đánh dấu tại DISPATCH TIME (agv_id, node_id) đang chờ ĐÚNG chặng đặc biệt
# này — vì node đó có thể ĐỒNG THỜI được đánh dấu 'trailer_staging=yes' (thả
# đầy — dùng ở chặng CUỐI, đường về) khi 1 node dùng chung cho cả 2 chức năng;
# nếu chỉ dựa vào cấu hình tĩnh của node sẽ không phân biệt được đang ở chặng
# nào. Discard ngay khi tới nơi (dùng 1 lần).
_pending_empty_pickup_legs: set[tuple[str, str]] = set()

# ── Chặng "lấy hàng đầy nhiều Tổ trong 1 chuyến" (milk run) — điểm KHÔNG phải
# Tổ gần nhất (không móc cơ khí, chỉ dừng chờ xác nhận thủ công vì hàng được
# công nhân chuyển tay từ xe của Tổ đó sang xe đang kéo theo AGV). Đánh dấu
# tại DISPATCH TIME (agv_id, node_id) để arrival handler BỎ QUA hoàn toàn logic
# móc (mặc định mọi node trailer_role='pickup' đều tự vào luồng móc) — rơi
# xuống nhánh "chờ xác nhận" giống hệt AGV carry. Dùng 1 lần rồi bỏ đánh dấu.
_pending_confirm_only_legs: set[tuple[str, str]] = set()


# ═══════════════════════════════════════════════════════════════════════════════
# HMI onboard — nút bấm vật lý trên AGV gửi event 'line_X' (đi tới Tổ X) hoặc
# 'station' (về trạm sạc). Chạy trong MQTT thread (sync) nên không dùng asyncpg
# (async) như main.py — viết lại bản sync (psycopg2) tương đương
# _resolve_team_node()/_find_trailer_staging_node() trong main.py.
# ═══════════════════════════════════════════════════════════════════════════════

def _hmi_resolve_team_node_sync(map_id: str, team: int, agv_type: str, want_pickup: bool) -> Optional[str]:
    import psycopg2, os, json as _j
    _DB = os.getenv("DATABASE_URL", "postgresql://postgres:ducmanh1801@localhost:5432/TOT_AGV")
    role = "pickup" if want_pickup else "drop"
    conn = psycopg2.connect(_DB)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT name_id, action FROM agv_map_points
                   WHERE CAST(map_id AS TEXT) = %s
                     AND action->>'trailer_role' = %s
                     AND (action->>'team')::int = %s""",
                (str(map_id), role, team),
            )
            rows = cur.fetchall()
            if not rows:
                # Node thả rỗng/lấy đầy dùng chung nhiều Tổ — khai tường minh qua
                # 'trailer_pickup_teams'/'trailer_drop_teams' (mảng), không suy
                # luận qua supply_group.
                _shared_field = "trailer_pickup_teams" if want_pickup else "trailer_drop_teams"
                cur.execute(
                    f"""SELECT name_id, action FROM agv_map_points
                       WHERE CAST(map_id AS TEXT) = %s
                         AND action->>'trailer_role' = %s
                         AND action->'{_shared_field}' ? %s""",
                    (str(map_id), role, str(team)),
                )
                rows = cur.fetchall()
            if not rows:
                if want_pickup:
                    cur.execute(
                        """SELECT name_id, action FROM agv_map_points
                           WHERE CAST(map_id AS TEXT) = %s
                             AND action->>'arrival_action' = 'wait_sys'
                             AND action->'supply_group' ? %s""",
                        (str(map_id), str(team)),
                    )
                else:
                    cur.execute(
                        """SELECT name_id, action FROM agv_map_points
                           WHERE CAST(map_id AS TEXT) = %s
                             AND (action->>'locationType' = 'DROPOFF'
                                  OR action->>'arrival_action' = 'wait_user')
                             AND (action->>'team')::int = %s""",
                        (str(map_id), team),
                    )
                rows = cur.fetchall()
    finally:
        conn.close()

    exact, generic = [], []
    for name_id, action in rows:
        act = action or {}
        if isinstance(act, str):
            act = _j.loads(act)
        tat = str(act.get("team_agv_type") or "").strip().lower()
        if tat == agv_type:
            exact.append(str(name_id))
        elif not tat:
            generic.append(str(name_id))
    if exact:
        return exact[0]
    if generic:
        return generic[0]
    return None


def _hmi_find_trailer_staging_node_sync(map_id: str) -> Optional[str]:
    import psycopg2, os
    _DB = os.getenv("DATABASE_URL", "postgresql://postgres:ducmanh1801@localhost:5432/TOT_AGV")
    conn = psycopg2.connect(_DB)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT name_id FROM agv_map_points
                   WHERE CAST(map_id AS TEXT) = %s
                     AND action->>'trailer_staging' = 'yes'
                   LIMIT 1""",
                (str(map_id),),
            )
            row = cur.fetchone()
            return str(row[0]) if row else None
    finally:
        conn.close()


def _hmi_find_trailer_empty_staging_node_sync(map_id: str) -> Optional[str]:
    """Node đánh dấu 'trailer_empty_staging=yes' — điểm lấy hàng rỗng cố định
    gần trạm (đầu quy trình, trước khi ra Tổ). Có thể trùng với node
    trailer_staging (1 node dùng chung cả 2 chức năng) — không xung đột vì
    2 field độc lập nhau."""
    import psycopg2, os
    _DB = os.getenv("DATABASE_URL", "postgresql://postgres:ducmanh1801@localhost:5432/TOT_AGV")
    conn = psycopg2.connect(_DB)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT name_id FROM agv_map_points
                   WHERE CAST(map_id AS TEXT) = %s
                     AND action->>'trailer_empty_staging' = 'yes'
                   LIMIT 1""",
                (str(map_id),),
            )
            row = cur.fetchone()
            return str(row[0]) if row else None
    finally:
        conn.close()


def _handle_hmi_line_event(agv_id: str, team: int) -> None:
    """HMI bấm nút 'Tổ X' — trailer: chạy đủ chu trình 4 chặng (giống
    /api/execute/trailer-roundtrip); carry: đi thẳng tới node của Tổ đó."""
    from agv_registry import agv_registry
    from mqtt_client import get_agv_runtime_info
    from task_queue import agv_task_queue, CMD_GO_TO, CMD_GO_CHARGE

    agv_type = str(agv_registry.get_config(agv_id).get('agv_type') or '').strip().lower()
    info = get_agv_runtime_info(agv_id)
    map_id = info.get('map_id')
    if not map_id:
        print(f"[HMI] {agv_id}: chưa có map hiện tại — bỏ qua sự kiện line_{team}")
        return

    if agv_type == 'trailer':
        drop_node = _hmi_resolve_team_node_sync(map_id, team, agv_type, want_pickup=False)
        if not drop_node:
            print(f"[HMI] {agv_id}: không tìm thấy node thả rỗng cho Tổ {team}")
            return
        pickup_node = _hmi_resolve_team_node_sync(map_id, team, agv_type, want_pickup=True)
        if not pickup_node:
            print(f"[HMI] {agv_id}: không tìm thấy node lấy đầy cho Tổ {team}")
            return
        staging_node = _hmi_find_trailer_staging_node_sync(map_id)
        if not staging_node:
            print(f"[HMI] {agv_id}: chưa đánh dấu node Staging (thả hàng đầy cố định) trên map")
            return
        # Điểm lấy hàng rỗng cố định gần trạm — TUỲ CHỌN, bỏ qua chặng này nếu
        # map chưa cấu hình (giữ đúng hành vi 4 chặng cũ, không bắt buộc).
        empty_staging_node = _hmi_find_trailer_empty_staging_node_sync(map_id)
        # Chèn theo thứ tự NGƯỢC — insert_next luôn chèn vào ĐẦU hàng đợi.
        agv_task_queue.insert_next(agv_id, CMD_GO_CHARGE, dest_node=None)
        agv_task_queue.insert_next(agv_id, CMD_GO_TO, dest_node=staging_node)
        agv_task_queue.insert_next(agv_id, CMD_GO_TO, dest_node=pickup_node)
        agv_task_queue.insert_next(agv_id, CMD_GO_TO, dest_node=drop_node)
        if empty_staging_node:
            _pending_empty_pickup_legs.add((agv_id, str(empty_staging_node)))
            agv_task_queue.insert_next(agv_id, CMD_GO_TO, dest_node=empty_staging_node)
        if not agv_task_queue.is_busy(agv_id):
            agv_task_queue.on_agv_completed(agv_id, notes="hmi_line_trigger", auto_dispatch=True)
        print(f"[HMI] {agv_id}: kích hoạt chu trình rơ-moóc Tổ {team} "
              f"(lấy rỗng={empty_staging_node or '(không cấu hình)'}, thả={drop_node}, "
              f"lấy={pickup_node}, staging={staging_node})")
    else:
        dest_node = _hmi_resolve_team_node_sync(map_id, team, agv_type, want_pickup=False)
        if not dest_node:
            print(f"[HMI] {agv_id}: không tìm thấy node cho Tổ {team}")
            return
        agv_task_queue.dispatch_or_queue(agv_id, CMD_GO_TO, dest_node=dest_node,
                                          session_label="hmi_line_trigger")
        print(f"[HMI] {agv_id}: đi tới Tổ {team} (node {dest_node})")


def _handle_hmi_station_event(agv_id: str) -> None:
    """HMI bấm nút 'Về trạm' — về trạm sạc đã cấu hình trên map."""
    from task_queue import agv_task_queue, CMD_GO_CHARGE
    agv_task_queue.dispatch_or_queue(agv_id, CMD_GO_CHARGE, session_label="hmi_station_trigger")
    print(f"[HMI] {agv_id}: về trạm sạc (yêu cầu từ HMI)")


# ═══════════════════════════════════════════════════════════════════════════════
# TrafficCoordinator — điều phối giao thông proactive, direction-aware
# ═══════════════════════════════════════════════════════════════════════════════

class TrafficCoordinator:
    """
    Quản lý đường đi của mọi AGV: phát hiện xung đột đối đầu (head-on) theo
    hướng di chuyển NGAY TẠI THỜI ĐIỂM DISPATCH, không chờ LIDAR kích hoạt.

    Nguyên tắc:
      - Mọi path được đăng ký ngay khi dispatch (register).
      - Khi tính đường mới, check xem path đề xuất có edge nào ngược chiều
        với edge tương lai của xe khác không (head-on).
      - Nếu có: thử tìm đường thay thế; nếu không được, trả về điểm chờ an toàn.
      - Xe ưu tiên cao hơn (delivery > transit > return_charge) không nhường.
      - Vị trí hiện tại được cập nhật liên tục khi xe di chuyển.
    """

    PRIORITY = {'delivery': 3, 'transit': 2, 'return_charge': 1}

    # Số node phía trước mỗi AGV giữ chỗ (reservation). Khoá node = ngăn xe khác
    # vào → xử lý cả head-on lẫn giao nhau tại ngã rẽ một thể.
    # PHẢI ≥ LOOKAHEAD (kích thước window) để khi KHÔNG conflict, window không bị cắt
    # ngắn; khi CÓ conflict, reservation dừng sớm → window cũng bị cắt theo (xe chỉ đi
    # tới node đã giữ chỗ — mô hình openTCS "allocate trước, move sau").
    RESERVE_AHEAD = 5

    def __init__(self):
        # {agv_id: {'path': list[str], 'direction': str, 'task_type': str,
        #           'current_idx': int, 'priority': int, 'registered_at': float}}
        self._registered: dict[str, dict] = {}
        # Bảng khoá node tiến trước: {node_id: agv_id} — mỗi node tối đa 1 chủ.
        self._node_res: dict[str, str] = {}
        # Khoá cạnh (edge) vô hướng phía trước: {frozenset({a,b}): agv_id} — chống đối
        # đầu trên CÙNG một cạnh (mỗi xe giữ node đích khác nhau nhưng chung cạnh).
        self._edge_res: dict = {}
        # ── BLOCKS (openTCS-style critical zones) ────────────────────────────
        # Cấu hình block đọc từ node_actions: action.block (tên) + action.block_type.
        self._block_of_node: dict[str, str] = {}     # node_id -> block_id
        self._block_nodes:   dict[str, set] = {}      # block_id -> {node_id,...}
        self._block_type:    dict[str, str] = {}      # block_id -> 'single' | 'same_dir'
        # SAME_DIRECTION_ONLY: theo dõi xe đang trong block + chiều chung
        self._block_holders: dict[str, set] = {}      # block_id -> {agv_id,...}
        self._block_dir:     dict[str, str] = {}      # block_id -> direction chung
        self._block_cfg_src = None                    # id(node_actions) đã load (cache)
        # ── INTENT ROUTE (tuyến ĐẦY ĐỦ tới đích cuối) ────────────────────────
        # Khi dispatch chia tuyến thành đoạn (vd lùi 17→5 trước, phần 5→…→13 queue
        # sau), `_registered.path` chỉ là ĐOẠN hiện tại. `_intent_route` lưu TUYẾN
        # ĐẦY ĐỦ để xe KHÁC né-đường (penalty) đúng — biết trước cả 5→18→4→19→… chứ
        # không chỉ đoạn lùi ngắn. CHỈ dùng cho penalty routing, KHÔNG cho reservation
        # (tránh giữ chỗ thừa node chưa tới).
        self._intent_route: dict[str, list] = {}

    def set_intent_route(self, agv_id: str, full_path: list) -> None:
        """Ghi tuyến ĐẦY ĐỦ tới đích cuối (cho penalty routing của xe khác)."""
        if full_path and len(full_path) >= 2:
            self._intent_route[agv_id] = [str(n) for n in full_path]

    def _rank(self, agv_id: str) -> tuple:
        """Hạng xe (cao = MẠNH hơn): (priority theo task, agv_id). Dùng để né BẤT
        ĐỐI XỨNG — chỉ xe YẾU né đường xe MẠNH, chống dao động (2 xe cùng nhảy nhánh)."""
        r = self._registered.get(agv_id, {})
        return (r.get('priority', 2), str(agv_id))

    def should_avoid_path_of(self, my_id: str, other_id: str,
                             my_priority: Optional[int] = None) -> bool:
        """me có nên NÉ đường other không? CHỈ khi other MẠNH hơn.
        Antisymmetric → đúng 1 trong 2 xe né → xe mạnh đi đường ngắn (cố định), xe
        yếu né sang nhánh khác → tách 2 nhánh, không dao động.
        my_priority: ưu tiên THẬT của xe đang lập KH (KHÔNG để rank mặc định 2 khi
        chưa registered → tránh winner né nhầm). None = dùng priority đã registered.

        ĐỒNG BỘ tie-break với `_arbitrate` (nguồn quyết reservation runtime): ưu tiên
        cao hơn thắng; CÙNG ưu tiên → ID NHỎ hơn thắng. TRƯỚC ĐÂY dùng `_rank=(priority,
        id)` so sánh `>` → ID LỚN thắng = NGƯỢC arbiter → 2 xe cùng ưu tiên: dispatch
        chọn winner này, runtime chọn winner kia → xe chạy tới rồi lại nhường = FLAIL
        (đúng log AGV01/AGV02 hoán đổi 15↔16 qua node 8: dispatch 'AGV02 ưu tiên' nhưng
        runtime 'AGV02 nhường')."""
        _my_p = (my_priority if my_priority is not None
                 else self._registered.get(my_id, {}).get('priority', 2))
        _ot_p = self._registered.get(other_id, {}).get('priority', 2)
        if _ot_p != _my_p:
            return _ot_p > _my_p
        # Cùng ưu tiên: other THẮNG (tôi né) nếu ID other NHỎ hơn — KHỚP _arbitrate.
        return str(other_id) < str(my_id)

    # ── Registration ──────────────────────────────────────────────────────────

    def register(self, agv_id: str, path: list[str], direction: str,
                 task_type: str = 'delivery') -> None:
        self._registered[agv_id] = {
            'path':          [str(n) for n in path],
            'direction':     direction,
            'task_type':     task_type,
            'current_idx':   0,
            'priority':      self.PRIORITY.get(task_type, 2),
            'registered_at': time.time(),
        }
        print(f"[TRAFFIC] {agv_id}: registered path={path} dir={direction} type={task_type}")
        self.reserve_ahead(agv_id)

    def deregister(self, agv_id: str) -> None:
        self._release_reservations(agv_id)
        self._release_edges(agv_id)
        self._release_blocks(agv_id)
        self._intent_route.pop(agv_id, None)
        if self._registered.pop(agv_id, None) is not None:
            print(f"[TRAFFIC] {agv_id}: deregistered")

    def update_position(self, agv_id: str, tag: str) -> None:
        """Cập nhật vị trí hiện tại của AGV trên path đã đăng ký."""
        r = self._registered.get(agv_id)
        if not r:
            return
        try:
            new_idx = r['path'].index(str(tag))
            if new_idx != r['current_idx']:
                r['current_idx'] = new_idx
        except ValueError:
            pass
        # Cập nhật giữ chỗ: nhả node đã qua, khoá node phía trước.
        self.reserve_ahead(agv_id)

    # ── Node / edge / block reservation ─────────────────────────────────────────
    def _release_reservations(self, agv_id: str) -> None:
        for n in [n for n, o in self._node_res.items() if o == agv_id]:
            del self._node_res[n]

    def _release_edges(self, agv_id: str) -> None:
        for e in [e for e, o in self._edge_res.items() if o == agv_id]:
            del self._edge_res[e]

    def _release_blocks(self, agv_id: str) -> None:
        """Gỡ agv_id khỏi holders của các SAME_DIR block; cập nhật chiều chung."""
        for b, holders in list(self._block_holders.items()):
            if agv_id in holders:
                holders.discard(agv_id)
                if not holders:
                    self._block_holders.pop(b, None)
                    self._block_dir.pop(b, None)

    def _refresh_block_config(self) -> None:
        """Load định nghĩa block từ node_actions (action.block + action.block_type).
        Cache theo id(node_actions) để khỏi tính lại mỗi lần. Không có block → rỗng
        → toàn bộ hành vi giữ nguyên (additive)."""
        try:
            from mqtt_client import map_manager as _mm
            na = getattr(_mm, 'node_actions', {}) or {}
        except Exception:
            return
        if id(na) == self._block_cfg_src:
            return   # chưa đổi → khỏi load lại
        self._block_cfg_src = id(na)
        bon, bn, bt = {}, {}, {}
        for nid, cfg in na.items():
            if not isinstance(cfg, dict):
                continue
            b = str(cfg.get('block', '') or '').strip()
            if not b or b.lower() == 'none':
                continue
            bon[str(nid)] = b
            bn.setdefault(b, set()).add(str(nid))
            _t = str(cfg.get('block_type', '') or 'single').strip().lower()
            bt[b] = 'same_dir' if _t in ('same_dir', 'same_direction', 'same_direction_only') else 'single'

        # ── AUTO-BLOCK đoạn đường ĐƠN (chuỗi node degree-2) ─────────────────────
        # Chuỗi liên tiếp các node bậc-2 = hành lang 1 làn (vd 19-64): 2 xe ngược chiều
        # KHÔNG thể tránh trong đó → coi mỗi chuỗi (≥2 node) là 1 SINGLE block: 1 xe vào
        # cả đoạn thì xe kia phải chờ NGOÀI (ở junction). Loại trừ head-on/kẹt giữa hành
        # lang mà không cần cấu hình tay. Bỏ qua node đã có block tay.
        try:
            from mqtt_client import map_manager as _mm2
            g = _mm2.line_graph if getattr(_mm2, 'line_graph', None) else getattr(_mm2, 'graph', None)
            if g is not None:
                _deg2 = {str(n) for n in g.nodes()
                         if g.degree(n) == 2 and str(n) not in bon}
                _seen: set = set()
                for _n in _deg2:
                    if _n in _seen:
                        continue
                    # gom chuỗi liên thông các node bậc-2 (BFS qua láng giềng bậc-2)
                    _chain, _stack = set(), [_n]
                    while _stack:
                        _c = _stack.pop()
                        if _c in _chain:
                            continue
                        _chain.add(_c); _seen.add(_c)
                        for _nb in g.neighbors(_c):
                            if str(_nb) in _deg2 and str(_nb) not in _chain:
                                _stack.append(str(_nb))
                    if len(_chain) >= 2:
                        _bid = 'auto_' + min(_chain, key=lambda x: (len(x), x))
                        bt[_bid] = 'single'
                        for _cn in _chain:
                            bon[_cn] = _bid
                            bn.setdefault(_bid, set()).add(_cn)
                if any(k.startswith('auto_') for k in bn):
                    print(f"[TRAFFIC] auto-block đường đơn: "
                          f"{ {k: sorted(v) for k, v in bn.items() if k.startswith('auto_')} }")
        except Exception as _e_ab:
            print(f"[TRAFFIC] auto-block lỗi: {_e_ab}")

        self._block_of_node, self._block_nodes, self._block_type = bon, bn, bt

    def _single_block_blocked_by_other(self, block_id: str, agv_id: str) -> bool:
        """SINGLE block: có node nào của block đang bị xe KHÁC khoá không?"""
        for bn in self._block_nodes.get(block_id, ()):  # noqa
            owner = self._node_res.get(str(bn))
            if owner and owner != agv_id and owner in self._registered:
                return True
        return False

    def _reserve_node(self, agv_id: str, n: str) -> bool:
        """Thử khoá 1 node cho agv_id. True nếu được (trống/của mình/thắng arbiter &
        chủ chưa cam kết & chủ KHÔNG đang đứng tại node), False nếu phải dừng trước."""
        owner = self._node_res.get(n)
        if owner is None or owner == agv_id:
            self._node_res[n] = agv_id
            return True
        # Xe MẠNH có thể GIÀNH node từ xe yếu — NHƯNG tuyệt đối KHÔNG giành node mà chủ
        # đang ĐỨNG VẬT LÝ tại đó (current_tag==n) hoặc đang lái tới: giành = đâm vào nó.
        # → xe mạnh phải DỪNG trước node, chờ xe yếu DỜI ĐI rồi mới vào.
        if (self._arbitrate(agv_id, owner, n) == agv_id
                and not self._owner_committed_to(owner, n)
                and not self._owner_at_node(owner, n)):
            self._node_res[n] = agv_id
            return True
        return False

    def _owner_at_node(self, owner: str, node: str) -> bool:
        """Chủ khoá có đang ĐỨNG VẬT LÝ tại `node` không (current_tag==node)?"""
        try:
            st = line_agv_handler.state_store.get(owner)
            return bool(st and st.current_tag is not None
                        and str(st.current_tag) == str(node))
        except Exception:
            return False

    def _dist_to(self, r: dict, node: str) -> int:
        """Số node từ vị trí hiện tại của r đến `node` trên path (999 nếu không có)."""
        try:
            return r['path'].index(str(node)) - r.get('current_idx', 0)
        except ValueError:
            return 999

    def _arbitrate(self, a: str, b: str, contested_node: Optional[str] = None) -> str:
        """Trả về agv_id ĐƯỢC QUYỀN đi qua (winner). Hàm THUẦN & ĐỐI XỨNG →
        cả 2 xe tính ra cùng kết quả → đúng 1 xe nhường (không kẹt do cùng nhường).

        Thứ tự quyết định:
          1. Đã qua điểm lấy/giao hàng (committed critical) → ưu tiên (không bị đẩy lùi)
          2. Task priority: delivery > transit > return_charge
          3. Gần node tranh chấp hơn → đi trước (giải phóng nhanh)
          4. agv_id (tất định cuối cùng)
        """
        ra = self._registered.get(a)
        rb = self._registered.get(b)
        if not ra:
            return b
        if not rb:
            return a
        critical = self._get_critical_nodes()
        if critical:
            a_comm = self._committed_past_critical(ra['path'], ra.get('current_idx', 0), critical)
            b_comm = self._committed_past_critical(rb['path'], rb.get('current_idx', 0), critical)
            if a_comm != b_comm:
                return a if a_comm else b
        pa = ra.get('priority', 2)
        pb = rb.get('priority', 2)
        if pa != pb:
            return a if pa > pb else b
        if contested_node is not None:
            da = self._dist_to(ra, contested_node)
            db = self._dist_to(rb, contested_node)
            if da != db:
                return a if da < db else b
        return a if str(a) <= str(b) else b

    def _owner_committed_to(self, owner: str, node: str) -> bool:
        """Chủ khoá có đang VẬT LÝ cam kết vào `node` không (chủ sắp/đang lái vào đó)? Nếu
        có → KHÔNG cướp khoá dù mình ưu tiên cao hơn: cướp = chủ lái vào node mình vừa
        chiếm → ĐÂM. Gồm: (1) node là BƯỚC KẾ TIẾP của chủ (registered path); (2) node nằm
        TRONG CỬA SỔ ĐANG CHẠY của chủ (`_routes[owner].window_start..window_end`) — firmware
        ĐÃ nhận plan lái qua đó nên sắp đi, dù registered current_idx còn ở xa. Thiếu (2) →
        RACE ngã ba: window cũ gửi khi node còn trống, sau đó xe ưu-tiên-cao cướp node →
        cả 2 cùng lái vào → ĐÂM (đúng log: AGV01 9→4 & AGV02 18→4 cùng vào node 4)."""
        try:
            r = self._registered.get(owner)
            if not r:
                return False
            idx = r.get('current_idx', 0)
            nxt = r['path'][idx + 1] if idx + 1 < len(r['path']) else None
            if nxt is not None and str(nxt) == str(node):
                return True
            _rt = line_agv_handler._routes.get(owner)
            if _rt and _rt.full_path:
                _ws = max(0, getattr(_rt, 'window_start', 0))
                _we = min(getattr(_rt, 'window_end', 0), len(_rt.full_path) - 1)
                for _k in range(_ws, _we + 1):
                    if str(_rt.full_path[_k]) == str(node):
                        return True
            return False
        except Exception:
            return False

    def reserve_ahead(self, agv_id: str) -> None:
        """Khoá RESERVE_AHEAD node (và cạnh + block) phía trước cho agv_id.
        Dừng khoá tại điểm bị xe khác giữ → xe sẽ chờ trước đó. Bao gồm:
          - Node lock (arbiter, có thể cướp của xe ưu tiên thấp chưa cam kết).
          - Edge lock vô hướng (chống đối đầu trên cùng cạnh).
          - BLOCK (vùng tới hạn): SINGLE = khoá CẢ block; SAME_DIR = chỉ chặn ngược chiều.
        """
        r = self._registered.get(agv_id)
        if not r:
            self._release_reservations(agv_id)
            self._release_edges(agv_id)
            self._release_blocks(agv_id)
            return
        self._refresh_block_config()
        self._release_reservations(agv_id)
        self._release_edges(agv_id)
        self._release_blocks(agv_id)
        path   = r['path']
        idx    = r.get('current_idx', 0)
        my_dir = r.get('direction', 'fwd')
        end    = min(idx + self.RESERVE_AHEAD, len(path) - 1)
        for k in range(idx, end + 1):
            n = str(path[k])
            block_id = self._block_of_node.get(n)

            # ── BLOCK handling ───────────────────────────────────────────────
            if block_id is not None:
                btype = self._block_type.get(block_id, 'single')
                if btype == 'single':
                    # CẢ block phải trống (hoặc của mình) → mới vào, và khoá TOÀN BỘ block.
                    if self._single_block_blocked_by_other(block_id, agv_id):
                        break   # block bị xe khác chiếm → dừng trước block, chờ
                    for bn in self._block_nodes.get(block_id, ()):
                        self._node_res[str(bn)] = agv_id   # khoá độc quyền cả vùng
                else:  # same_dir
                    holders = self._block_holders.get(block_id, set())
                    others  = holders - {agv_id}
                    bdir    = self._block_dir.get(block_id)
                    if others and bdir is not None and bdir != my_dir:
                        break   # đang có xe ngược chiều trong block → chờ
                    self._block_holders.setdefault(block_id, set()).add(agv_id)
                    self._block_dir[block_id] = my_dir
                    if not self._reserve_node(agv_id, n):
                        break
            # ── Node thường ─────────────────────────────────────────────────
            else:
                if not self._reserve_node(agv_id, n):
                    break

            # ── Edge lock vô hướng (cạnh từ node trước reserved tới n) ────────
            if k > idx:
                e = frozenset((str(path[k - 1]), n))
                eo = self._edge_res.get(e)
                if eo is not None and eo != agv_id and eo in self._registered:
                    break   # cạnh đang bị xe khác giữ (đối đầu cùng cạnh) → dừng
                self._edge_res[e] = agv_id

    def reserved_extent(self, agv_id: str, path: list, from_idx: int) -> int:
        """Index node XA NHẤT (từ from_idx) mà agv_id đã giữ chỗ LIÊN TỤC.
        Window gửi cho xe sẽ bị cắt tại đây → xe CHỈ đi tới node đã reserve
        (không lao vào node bị xe khác giữ → tránh đâm do đua reactive)."""
        end = from_idx
        for k in range(from_idx, len(path)):
            if self._node_res.get(str(path[k])) == agv_id:
                end = k
            else:
                break
        return end

    def node_reserved_by_other(self, agv_id: str, node: str) -> Optional[str]:
        """Trả về agv_id chủ khoá node nếu KHÁC agv_id, ngược lại None.
        Tự nhả khoá mồ côi: chủ không còn route đăng ký (offline/đã xong)."""
        owner = self._node_res.get(str(node))
        if not owner or owner == agv_id:
            return None
        if owner not in self._registered:
            del self._node_res[str(node)]   # khoá mồ côi → nhả
            return None
        return owner

    # ── Conflict detection ────────────────────────────────────────────────────

    def _future_edges(self, r: dict) -> set[tuple[str, str]]:
        """Tập edges mà AGV sẽ đi qua (từ vị trí hiện tại trở đi)."""
        path = r['path']
        idx  = r.get('current_idx', 0)
        return {(path[i], path[i + 1]) for i in range(idx, len(path) - 1)}

    def _is_same_direction(
        self, my_path: list[str], edge_fn: str, edge_tn: str, other_id: str
    ) -> bool:
        """
        Kiểm tra xe kia (other_id) đi CÙNG CHIỀU với chúng ta trên edge fn→tn.
        Dùng registered path của TrafficCoordinator.
        """
        r = self._registered.get(other_id)
        if not r:
            return False
        op = r['path']
        try:
            idx_fn = op.index(str(edge_fn))
            idx_tn = op.index(str(edge_tn))
            return idx_fn < idx_tn
        except ValueError:
            # fn không có trong route xe kia (xe kia bắt đầu từ tn hoặc đi từ nhánh khác).
            # So sánh node tiếp theo sau tn trong cả 2 path để xác định hướng.
            try:
                idx_tn_op = op.index(str(edge_tn))
                if idx_tn_op < len(op) - 1:
                    op_next = op[idx_tn_op + 1]
                    my_idx_tn = my_path.index(str(edge_tn))
                    if my_idx_tn < len(my_path) - 1:
                        return my_path[my_idx_tn + 1] == op_next
            except ValueError:
                pass
            return False

    def _get_critical_nodes(self) -> set[str]:
        """
        Nodes có arrival_action='wait_sys' hoặc 'wait_user' = điểm chờ cấp hàng.
        Đây là các điểm "cam kết": AGV nào đã qua điểm này có quyền ưu tiên tiếp tục.
        """
        try:
            from mqtt_client import map_manager as _mm
            na = getattr(_mm, 'node_actions', {}) or {}
            return {
                nid for nid, cfg in na.items()
                if isinstance(cfg, dict)
                and str(cfg.get('arrival_action', '')).lower() in ('wait_sys', 'wait_user')
            }
        except Exception:
            return set()

    def _committed_past_critical(
        self, path: list[str], up_to_idx: int, critical: set[str]
    ) -> bool:
        """
        AGV đã đi qua (hoặc đang đứng tại) critical node không?
        Kiểm tra các node trong path[0..up_to_idx].
        True = đã cam kết → có quyền ưu tiên tiếp tục.
        """
        for i, node in enumerate(path):
            if node in critical and i <= up_to_idx:
                return True
        return False

    def _approaching_critical(
        self, path: list[str], cur_idx: int, critical: set[str], near: int = 2
    ) -> bool:
        """
        AGV đang tiến đến critical node trong vòng `near` bước không?
        True = sắp đến điểm chờ → cũng được ưu tiên (để không bị chặn lại giữa đường).
        """
        for i, node in enumerate(path):
            if node in critical and cur_idx < i <= cur_idx + near:
                return True
        return False

    # Số edge tối đa check ở dispatch time.
    # Conflict xa hơn thế này để rolling plan xử lý động khi 2 xe tiếp cận nhau.
    DISPATCH_HORIZON = 4

    def find_head_on(
        self, agv_id: str, proposed_path: list[str], task_type: str = 'delivery',
        near_only: bool = False,
    ) -> Optional[tuple[int, str]]:
        """
        Kiểm tra xung đột đối đầu (head-on) có tính đến ưu tiên theo vị trí điểm chờ.

        Quy tắc ưu tiên (theo thứ tự):
          1. AGV đã qua điểm chờ cấp hàng (wait_sys) → ưu tiên cao, xe kia nhường.
          2. AGV về đang gần (≤2 bước) hoặc đã qua điểm chờ → ưu tiên, xe đi nhường.
          3. Không có critical point liên quan → dùng task_priority thông thường.

        near_only=True  → chỉ check DISPATCH_HORIZON edges đầu (dispatch time).
        near_only=False → check toàn path (rolling plan).

        Returns: (conflict_edge_idx, other_agv_id) nếu agv_id cần nhường, None nếu không.
        """
        critical    = self._get_critical_nodes()
        path        = [str(n) for n in proposed_path]
        limit       = self.DISPATCH_HORIZON if near_only else len(path)
        my_priority = self.PRIORITY.get(task_type, 2)

        # Tập AGV đang DỪNG tại node nào đó (kể cả đã deregister — lifecycle confirm,
        # vừa nhận lệnh mới, v.v.). Đây là lớp an toàn cuối cùng trước khi phát lệnh.
        stopped_map: dict[str, str] = {}   # {node_str: agv_id}
        try:
            _ss = line_agv_handler.state_store._states
            for oid, st in _ss.items():
                if oid == agv_id or st is None:
                    continue
                if st.current_tag is not None and not st.driving:
                    stopped_map[str(st.current_tag)] = oid
        except Exception:
            pass

        # ── Pass 1: kiểm tra AGV đang DỪNG (kể cả deregistered) ─────────────
        # Race-condition fix: sau khi confirm lifecycle, AGV deregister nhưng
        # vẫn đứng yên tại node. find_head_on phải bắt được trường hợp này.
        for i in range(min(limit, len(path) - 1)):
            fn, tn = path[i], path[i + 1]
            if tn not in stopped_map:
                continue
            s_agv = stopped_map[tn]
            if s_agv == agv_id:
                continue
            # Xe đang dừng tại ĐÍCH CUỐI của ta (vd nó đang picking tại pickup/đích CHUNG
            # node 19) → KHÔNG phải head-on: ta đi TỚI node đó, nó sẽ rời đi (hoặc ta chờ
            # nó rời). KHỚP `_find_upcoming_conflict` runtime (tn==path[-1] → -(i+1)=chờ).
            # Thiếu guard này → dispatch coi là head-on → đỗ-né đi VÒNG XA (đúng log: AGV02
            # đỗ tại node 10) → quay lại tiếp cận đích kiểu LÙI-CÓ-RẼ kỳ lạ (turn ngược/đi
            # thẳng). Dispatch ≠ runtime = mâu thuẫn → maneuver loạn. → chờ tại chỗ, runtime
            # tự cắt window trước đích cho tới khi node trống.
            if tn == path[-1]:
                return -(i + 1)
            # Xe đang dừng tại node phía trước
            same_dir = self._is_same_direction(path, fn, tn, s_agv)
            if same_dir:
                # Cùng chiều + dừng = following → trả về negative (halt+chờ)
                return -(i + 1)
            else:
                # Ngược chiều + dừng = conflict thật
                print(f"[TRAFFIC] {agv_id}: stopped-AGV conflict "
                      f"at {fn}→{tn} (other={s_agv})")
                return (i, s_agv)

        # ── Pass 2: kiểm tra HEAD-ON với AGV đang di chuyển (registered) ─────
        for other_id, r in self._registered.items():
            if other_id == agv_id:
                continue
            future = self._future_edges(r)
            if not future:
                continue
            other_cur_idx = r.get('current_idx', 0)

            for i in range(min(limit, len(path) - 1)):
                fn, tn = path[i], path[i + 1]
                if (tn, fn) not in future:
                    continue

                # HEAD-ON PHÁT HIỆN → áp dụng ưu tiên critical point
                if critical:
                    my_committed    = self._committed_past_critical(path, i, critical)
                    other_committed = self._committed_past_critical(
                        r['path'], other_cur_idx, critical)
                    other_near      = self._approaching_critical(
                        r['path'], other_cur_idx, critical, near=2)

                    if my_committed and not other_committed and not other_near:
                        # Trước khi skip: kiểm tra xe kia có đang ĐANG DI CHUYỂN
                        # trên đoạn đường trong vùng conflict không.
                        # Nếu có → xe kia chưa nhường xong (chưa đến safe_wait) →
                        # KHÔNG bỏ qua conflict, xử lý như head-on bình thường.
                        _other_still_moving = False
                        try:
                            _ost = line_agv_handler.state_store._states.get(other_id)
                            if _ost and _ost.driving:
                                _cur_t = str(_ost.current_tag or '')
                                # Xe kia đang ở trong vùng path[:i+2] (trước conflict)
                                if _cur_t in [str(p) for p in path[:i + 2]]:
                                    _other_still_moving = True
                        except Exception:
                            pass
                        if _other_still_moving:
                            # Xe kia đang di chuyển vào vùng conflict → chưa nhường xong
                            # Báo head-on để dispatcher xử lý (chờ hoặc tránh)
                            print(f"[TRAFFIC] {agv_id}: đã qua critical nhưng {other_id} "
                                  f"đang di chuyển trong vùng conflict → xử lý head-on")
                        else:
                            print(f"[TRAFFIC] {agv_id}: đã qua critical → ưu tiên, "
                                  f"{other_id} nhường")
                            continue

                    if (other_committed or other_near) and not my_committed:
                        print(f"[TRAFFIC] {agv_id} nhường {other_id} "
                              f"(committed={other_committed}, near={other_near})")
                        return (i, other_id)

                other_priority = r.get('priority', 2)
                print(f"[TRAFFIC] {agv_id} HEAD-ON với {other_id} "
                      f"edge {fn}→{tn} idx={i} "
                      f"(pri {my_priority} vs {other_priority})")
                return (i, other_id)
        return None

    def find_same_dir_following(
        self, agv_id: str, proposed_path: list[str]
    ) -> Optional[tuple[int, str]]:
        """
        Phát hiện xe phía trước cùng chiều đang dừng tại node đề xuất đi qua.
        Trả về (index node bị chặn, agv_id xe chặn) hoặc None.
        """
        path = [str(n) for n in proposed_path]
        for other_id, r in self._registered.items():
            if other_id == agv_id:
                continue
            other_cur = r['path'][r['current_idx']] if r['path'] else None
            if not other_cur:
                continue
            for i in range(1, len(path)):
                if path[i] == other_cur:
                    return (i, other_id)
        return None

    def find_safe_wait_node(
        self, proposed_path: list[str], conflict_idx: int
    ) -> Optional[str]:
        """
        Tìm node an toàn GẦN NHẤT với AGV để đứng chờ tránh conflict.
        Scan từ path[1] (gần nhất với AGV) lên gần conflict → trả về node đầu tiên hợp lệ.
        Điều này đảm bảo AGV chỉ lùi TỐI THIỂU cần thiết, không lùi quá xa.
        Khoảng cách an toàn ≥2 node từ xe kia vẫn được đảm bảo vì path[1] cách
        path[conflict_idx+1] (vị trí xe kia) ít nhất 2 node.
        """
        path = [str(n) for n in proposed_path]
        # Scan từ gần nhất (path[1]) ra xa hơn
        # Bỏ qua path[0] (vị trí hiện tại), trả về node đầu tiên hợp lệ
        for i in range(1, conflict_idx):
            if path[i] != path[0]:
                return path[i]
        return None

    def find_flexible_parking(
        self, agv_id: str, current_node: str,
        conflict_path: list[str], max_hops: int = 3,
        extra_blocked: Optional[set] = None,
    ) -> Optional[str]:
        """
        BFS từ current_node tìm node đỗ xe linh hoạt:
        - Không nằm trên conflict_path (vùng tranh chấp)
        - Không bị xe khác chiếm
        - Ưu tiên: locationType=WAITING > ít kết nối (side branch)
        Không phân biệt hướng tiến/lùi — AGV sẽ tự tính hướng khi được dispatch.
        """
        try:
            from mqtt_client import map_manager as _mm
            g  = _mm.line_graph if _mm.line_graph else _mm.graph
            na = getattr(_mm, 'node_actions', {}) or {}
            if g is None:
                return None
        except Exception:
            return None

        conflict_set = {str(n) for n in conflict_path}
        # Thêm extra_blocked (accumulated_blocked từ obstacle handler)
        if extra_blocked:
            conflict_set.update(str(n) for n in extra_blocked)

        # Tập nodes đang bị xe khác chiếm (future path từ vị trí hiện tại)
        occupied: set[str] = set()
        for oid, r in self._registered.items():
            if oid == agv_id:
                continue
            cur = r.get('current_idx', 0)
            occupied.update(r['path'][cur:])

        from collections import deque
        visited   = {str(current_node)}
        queue     = deque([(str(current_node), 0)])
        candidates: list[tuple] = []

        while queue:
            node, hops = queue.popleft()
            if hops > max_hops:
                continue

            is_start = (node == str(current_node))
            is_blocked = (node in conflict_set or node in occupied)

            if not is_start and not is_blocked:
                cfg      = na.get(node, {}) or {}
                loc_type = str(cfg.get('locationType', '')).upper()
                arrival  = str(cfg.get('arrival_action', '')).lower()
                # Loại trừ hoàn toàn: CHARGER, DROPOFF, node có arrival_action đặc biệt
                if loc_type in ('CHARGER', 'DROPOFF') or arrival in ('wait_charge',):
                    pass  # không thêm vào candidates, nhưng vẫn có thể traverse qua
                else:
                    degree = g.degree(str(node)) if str(node) in g else 99
                    is_waiting = 1 if loc_type == 'WAITING' else 0
                    candidates.append((-is_waiting, degree, hops, node))

            # Chỉ traverse tiếp từ node KHÔNG bị blocked (trừ node xuất phát).
            # Không đi qua blocked node để tìm candidate phía sau nó —
            # vì đường đi thực tế vẫn phải qua node đó.
            if hops < max_hops and (is_start or not is_blocked):
                for nb in g.neighbors(str(node)):
                    nb_str = str(nb)
                    if nb_str not in visited:
                        visited.add(nb_str)
                        queue.append((nb_str, hops + 1))

        if not candidates:
            return None
        candidates.sort()
        best = candidates[0][3]
        print(f"[TRAFFIC] {agv_id}: flexible parking → {best} "
              f"(score={candidates[0][:3]}, from={current_node})")
        return best

    def find_parking_node(
        self, agv_id: str, proposed_path: list[str], conflict_idx: int,
        other_agv_id: str,
    ) -> Optional[tuple[str, str]]:
        """
        Tìm node "bãi đỗ" (parking) trên nhánh phụ để AGV tránh ra chờ,
        không chiếm đường chính và không cản xe đang đi qua bottleneck.

        Thuật toán:
          1. Xét node cuối an toàn trước conflict (entry_node = path[conflict_idx-1]).
          2. Lấy tất cả láng giềng của entry_node từ graph.
          3. Lọc: không nằm trên proposed_path, không nằm trong future path của xe kia.
          4. Ưu tiên node ít kết nối hơn (dead-end / side track) để tránh cản xe khác.

        Returns: (parking_node, entry_node) hoặc None nếu không tìm được.
        """
        try:
            from mqtt_client import map_manager as _mm
            g = (_mm.line_graph if _mm.line_graph else _mm.graph)
            if g is None:
                return None
        except Exception:
            return None

        path = [str(n) for n in proposed_path]

        # Tập future nodes của xe THẮNG (winner) — siding phải NẰM NGOÀI đây để winner
        # đi qua được. Gồm path đăng ký + intent_route (cả khi winner đang chờ/deregistered).
        other_future: set[str] = set()
        if other_agv_id in self._registered:
            r_other = self._registered[other_agv_id]
            cur = r_other.get('current_idx', 0)
            other_future.update(str(n) for n in r_other['path'][cur:])
        _oi = self._intent_route.get(other_agv_id)
        if _oi:
            other_future.update(str(n) for n in _oi)
        # MỞ RỘNG theo BLOCK: nếu winner chạm 1 node trong block (vd 17 ∈ auto_6) thì CẢ
        # block là "winner cần" → siding KHÔNG được nằm trong đó (đỗ ở 6∈auto_6 sẽ chặn
        # winner vào 17). Tránh chọn chỗ né mà lại giam winner.
        self._refresh_block_config()
        for _n in list(other_future):
            _bid = self._block_of_node.get(str(_n))
            if _bid:
                other_future.update(str(b) for b in self._block_nodes.get(_bid, ()))

        path_set = set(path)

        # TRẠM (sạc/chờ) KHÔNG được dùng làm siding: đỗ né vào trạm = "lùi về trạm
        # tránh" (lỗi user thấy). Cũng loại node xe VỪA TỪ ĐÓ TỚI (prev_tag vật lý) →
        # không rẽ ngược về chỗ vừa rời.
        _na_park = getattr(_mm, 'node_actions', {}) or {}

        def _is_station(_n: str) -> bool:
            _cfg = _na_park.get(str(_n), {}) or {}
            return (str(_cfg.get('locationType', '')).upper() == 'CHARGER'
                    or str(_cfg.get('arrival_action', '')).lower()
                    in ('wait_charge', 'wait_user'))
        # prev_tag lấy từ handler (TrafficCoordinator KHÔNG có state_store).
        _prev_phys = None
        try:
            _st_park = line_agv_handler.state_store.get(agv_id)
            if _st_park and _st_park.prev_tag is not None:
                _prev_phys = str(_st_park.prev_tag)
        except Exception:
            pass

        # Tìm điểm RẼ NHÁNH SỚM NHẤT (gần vị trí hiện tại path[0] nhất) có 1 node bên
        # cạnh nằm NGOÀI đường winner → xe thua rẽ khỏi corridor CÀNG SỚM CÀNG TỐT, ít
        # lấn vào vùng tranh chấp. entry_node NẰM TRÊN path xe thua là đúng (nó là điểm
        # rẽ); KHÔNG loại entry theo winner-path (head-on cùng corridor thì entry tất
        # nhiên nằm trên path winner — quan trọng là SIDING nằm ngoài, và xe thua rời
        # node chung trước khi winner tới, do reservation/arbiter bảo đảm an toàn).
        end_search = max(1, min(conflict_idx + 1, len(path)))
        for si in range(0, end_search):
            entry_node = path[si]
            if entry_node not in g:
                continue
            # node xe thua VỪA RỜI (không rẽ ngược lại đúng chỗ vừa tới)
            came_from = path[si - 1] if si > 0 else None
            candidates = [
                str(n) for n in g.neighbors(str(entry_node))
                if str(n) not in path_set
                and str(n) not in other_future
                and str(n) != str(came_from)
                and str(n) != str(_prev_phys)   # không lùi về node vừa từ đó tới
                and not _is_station(str(n))      # KHÔNG đỗ né vào trạm
            ]
            if not candidates:
                continue
            # ưu tiên nhánh cụt / ít kết nối (đỗ né không cản xe khác)
            candidates.sort(key=lambda n: g.degree(str(n)))
            parking = candidates[0]
            print(f"[TRAFFIC] {agv_id}: waiting/parking node={parking} "
                  f"(rẽ tại entry={entry_node}, conflict_idx={conflict_idx})")
            return (parking, entry_node)

        return None

    def get_status(self) -> list[dict]:
        return [
            {
                'agv_id':  agv_id,
                'current': r['path'][r['current_idx']] if r['path'] else None,
                'dest':    r['path'][-1] if r['path'] else None,
                'type':    r['task_type'],
                'dir':     r['direction'],
            }
            for agv_id, r in self._registered.items()
        ]


traffic_coordinator = TrafficCoordinator()


# ═══════════════════════════════════════════════════════════════════════════════
# LineAGVHandler
# ═══════════════════════════════════════════════════════════════════════════════

class LineAGVHandler:
    """
    Nhận và xử lý MQTT messages từ Line AGV.
    Được gọi từ unified on_message khi topic thuộc v2.
    """

    def __init__(self):
        self.state_store = LineAGVStateStore()

        # ── Rolling plan state: {agv_id: LineAGVRoute} ────────────────────────
        self._routes: dict[str, LineAGVRoute] = {}
        # Lần cuối gửi-lại cửa sổ khi xe DỪNG GIỮA route (cứu kẹt), chống spam.
        self._mid_resend_ts: dict[str, float] = {}
        # Thời điểm xe BẮT ĐẦU đứng yên tại tag hiện tại (để chờ đủ lâu mới cứu kẹt).
        self._stopped_since: dict[str, float] = {}
        # True khi xe từng báo error_code != 0 và CHƯA được "tiêu thụ" bởi 1 lần
        # cứu-kẹt — watchdog "DỪNG GIỮA route" chỉ được phép resend khi cờ này đang
        # True (tức xe THỰC SỰ từng lỗi rồi mới hết lỗi), KHÔNG resend cho mọi ca
        # đứng yên bình thường (tránh polling/spam liên tục không cần thiết).
        self._had_error: dict[str, bool] = {}
        # Lần cuối xe LÙI nhường đường (chống ping-pong lùi↔tiến liên tục).
        self._backup_ts: dict[str, float] = {}
        # Lần cuối xe REROUTE-do-obstacle (avoid_all) — chống flip-flop lật nhánh vòng.
        self._reroute_ts: dict[str, float] = {}

        # ── Callbacks (inject từ mqtt_client sau khi MQTT sẵn sàng) ──────────
        # send_window_fn(agv_id, plan_dict) — gửi plan đến AGV
        self.send_window_fn: Optional[Callable] = None
        # on_state_changed(LineAGVState) — notify GUI
        self.on_state_changed: Optional[Callable] = None
        # on_battery_event(agv_id, event_name, data) — xử lý pin yếu
        self.on_battery_event: Optional[Callable] = None
        # on_event(agv_id, event_name, data) — xử lý tất cả events
        self.on_event: Optional[Callable] = None

        # Pending commands: {agv_id: {cmd_id, sent_at, payload}}
        self._pending_cmds: dict[str, dict] = {}

    # ── Route management ──────────────────────────────────────────────────────

    def _should_anti_trap_vacate(self, agv_id: str, full_path: list, cur_idx: int) -> bool:
        """CHỐNG-TRAP: xe bị kẹt window [cur→cur] (không nhích được) tại node mình ĐANG
        đứng — kiểm tra có phải mình ĐANG CHẮN xe khác không và node KẾ có trống vật lý:
          (a) có XE KHÁC THỰC SỰ CẦN node mình đang đứng (node hiện tại ∈ đường tương lai
              xe đó) → mình chắn nó (đứng im → 2 xe kẹt nhau), VÀ
          (b) node KẾ TRỐNG VẬT LÝ (không xe nào đang đứng đó, không xe nào sắp vào nó).
        Nếu cả hai đúng → FORCE giữ node kế cho mình (`_node_res[next]=agv_id`, cướp khoá
        ma/khoá xe follower) và trả True (caller đẩy window +1 để VACATE). Dùng CHUNG cho
        `set_route` (lúc dispatch) và `_send_window` (rolling) — tránh re-check rolling ghi
        đè vacate thành đứng-im (vd 2 xe cùng chiều: leader bị reservation của follower
        khoá node kế → đứng mãi). KHÔNG fire cho standoff thường (xe kia đậu chỗ khác,
        không cần node mình)."""
        if cur_idx + 1 >= len(full_path):
            return False
        _my_cur   = str(full_path[cur_idx])
        _nxt_node = str(full_path[cur_idx + 1])
        # (a) Có xe khác CẦN node mình đang đứng?
        _blocks_other = False
        for _oid_a, _oreg_a in traffic_coordinator._registered.items():
            if _oid_a == agv_id:
                continue
            _opa = [str(n) for n in _oreg_a.get('path', [])]
            _oca = _oreg_a.get('current_idx', 0)
            if _my_cur in _opa[_oca:]:
                _blocks_other = True
                break
        if not _blocks_other:
            return False
        # (b) Node KẾ trống vật lý (không ai đứng + không ai sắp vào)?
        for _oid_b, _stb in self.state_store._states.items():
            if _oid_b == agv_id or _stb is None or _stb.current_tag is None:
                continue
            if str(_stb.current_tag) == _nxt_node:
                return False
            _rb = traffic_coordinator._registered.get(_oid_b)
            if _rb:
                _pb = [str(n) for n in _rb.get('path', [])]
                _ib = _rb.get('current_idx', 0)
                if _ib + 1 < len(_pb) and _pb[_ib + 1] == _nxt_node:
                    return False
        # FORCE giữ node kế (đã xác nhận trống + không ai sắp vào → an toàn)
        traffic_coordinator._node_res[_nxt_node] = agv_id
        return True

    def set_route(
        self,
        agv_id:    str,
        full_path: list,
        task_type: str = "delivery",
        direction: str = "fwd",
    ) -> LineAGVRoute:
        """
        Lưu route mới cho AGV và tính cửa sổ đầu tiên.
        Gọi từ build_order_for_traffic_route trước khi gửi plan.
        """
        str_path = [str(p) for p in full_path]
        w_end    = first_window_end(str_path)
        route    = LineAGVRoute(
            full_path=str_path,
            task_type=task_type,
            direction=direction,
            window_start=0,
            window_end=w_end,
            is_complete=(w_end == len(str_path) - 1),
        )
        self._routes[agv_id] = route
        # Cập nhật hướng plan hiện tại vào state để dispatch sau này tham chiếu
        _st = self.state_store.get(agv_id)
        if _st:
            _st.last_plan_direction = direction
        # Đăng ký vào TrafficCoordinator (register → reserve_ahead giữ chỗ phía trước)
        traffic_coordinator.register(agv_id, str_path, direction, task_type)
        # CẮT window theo RESERVATION (openTCS "allocate trước, move sau"): xe CHỈ được
        # gửi RUN tới node đã giữ chỗ. Nếu node kế bị xe khác giữ → window dừng tại node
        # đã reserve → xe KHÔNG lao vào vùng tranh chấp (tránh đâm do đua reactive).
        _res_end = traffic_coordinator.reserved_extent(agv_id, str_path, 0)
        if _res_end < route.window_end:
            # Node ngay sau vùng đã giữ bị XE KHÁC giữ → lùi thêm 1 node ĐỆM
            # (không đứng sát biên reservation của xe kia — ngoài tầm LIDAR).
            _nxt = str_path[_res_end + 1] if _res_end + 1 < len(str_path) else None
            if _nxt and traffic_coordinator.node_reserved_by_other(agv_id, _nxt):
                _res_end = max(0, _res_end - 1)
            route.window_end  = max(0, _res_end)
            route.is_complete = (route.window_end == len(str_path) - 1)
            print(f"[LINE_AGV] {agv_id}: window CẮT theo reservation → [0→{route.window_end}] "
                  f"(node kế bị xe khác giữ — chỉ đi tới node đã giữ chỗ, chừa 1 node đệm)")
        # ── CẮT window theo CONFLICT phía trước (hiện thực hoá "chờ tại điểm an
        # toàn" của planner): nếu trong TRAFFIC_LOOKAHEAD node đầu có head-on /
        # ngã rẽ bị chiếm → window chỉ tới điểm an toàn (trừ HEADON_STANDOFF node),
        # KHÔNG phó mặc cho per-tag check (có thể bị sự kiện khác ghi đè).
        try:
            _conf0 = self._find_upcoming_conflict(
                agv_id, route, 0, min(TRAFFIC_LOOKAHEAD, len(str_path) - 1))
            if _conf0 is not None:
                _fol0  = (_conf0 < 0)
                _cat0  = (-_conf0 - 1) if _fol0 else _conf0
                _safe0 = max(0, (_cat0 - 1) if _fol0 else (_cat0 - HEADON_STANDOFF))
                if _safe0 < route.window_end:
                    route.window_end  = _safe0
                    route.is_complete = (_safe0 == len(str_path) - 1)
                    route.waiting_before_conflict = str_path[_safe0]
                    print(f"[LINE_AGV] {agv_id}: window CẮT theo conflict phía trước "
                          f"→ [0→{_safe0}] (chờ tại điểm an toàn {str_path[_safe0]}, "
                          f"conflict tại idx={_cat0})")
        except Exception as _e_c0:
            print(f"[LINE_AGV] {agv_id}: set_route conflict-cap error: {_e_c0}")
        # ── CHỐNG-TRAP DEADLOCK: KHÔNG kẹt xe tại node hiện tại (window=[0→0]) khi
        # (a) node KẾ đã GIỮ CHỖ ĐƯỢC (reserved_extent ≥ 1 → xe SỞ HỮU node kế → vào an
        # toàn, KHÔNG phải head-on) VÀ (b) có XE KHÁC THỰC SỰ CẦN node mình đang đứng
        # (node hiện tại nằm trên đường tương lai xe đó) → mình chắn nó. Khi đó phải
        # VACATE để xe kia lên (nếu không → 2 xe đứng im chờ nhau). KHÔNG vacate cho
        # standoff thường (xe kia đậu chỗ khác, không cần node mình → giữ khoảng cách an toàn).
        if route.window_end == 0 and len(str_path) > 1:
            if self._should_anti_trap_vacate(agv_id, str_path, 0):
                route.window_end = 1
                route.is_complete = (1 == len(str_path) - 1)
                route.waiting_before_conflict = str_path[1]
                print(f"[LINE_AGV] {agv_id}: CHỐNG-TRAP → window [0→1] (xe khác cần node "
                      f"{str_path[0]} mình đang đứng; node kế {str_path[1]} trống → VACATE cho nó lên)")
        print(f"[LINE_AGV] {agv_id}: set_route len={len(str_path)} dir={direction} "
              f"window=[0→{route.window_end}] final={route.is_complete}")
        return route

    def get_route(self, agv_id: str) -> Optional[LineAGVRoute]:
        return self._routes.get(agv_id)

    def clear_route(self, agv_id: str) -> None:
        self._routes.pop(agv_id, None)
        traffic_coordinator.deregister(agv_id)

    # ── Dispatch ──────────────────────────────────────────────────────────────

    def dispatch(self, agv_id: str, kind: str, payload_str: str) -> None:
        if kind == "state":
            self._on_state(agv_id, payload_str)
        elif kind == "connection":
            self._on_connection(agv_id, payload_str)

    # ── State handler ─────────────────────────────────────────────────────────

    def _on_state(self, agv_id: str, payload_str: str) -> None:
        try:
            data = json.loads(payload_str)
        except json.JSONDecodeError as e:
            print(f"[LINE_AGV] {agv_id}: JSON error: {e}")
            return

        state   = self.state_store.get_or_create(agv_id)
        old_tag = state.current_tag  # Optional[int]

        # ── Parse tag ─────────────────────────────────────────────────────────
        # Ưu tiên lastNodeId, fallback tag; bỏ qua nếu cả hai đều absent/rỗng
        raw_lid = data.get("lastNodeId")
        raw_tag = data.get("tag")
        last_node_raw = raw_lid if (raw_lid is not None and raw_lid != "") \
                        else (raw_tag if (raw_tag is not None and raw_tag != "") else None)

        if last_node_raw is not None:
            try:
                s = str(last_node_raw).strip()
                new_tag: Optional[int] = int(s) if s.lstrip("-").isdigit() else int(float(s))
            except (ValueError, TypeError):
                new_tag = old_tag   # giữ nguyên nếu parse lỗi
                print(f"[LINE_AGV] {agv_id}: parse tag failed raw={last_node_raw!r}")
        else:
            new_tag = old_tag   # không có tag trong payload — giữ nguyên vị trí

        # Tag=0 nghĩa là AGV không đứng tại RFID nào — giữ nguyên vị trí đã biết
        # (tránh ghi đè vị trí gán thủ công hoặc RFID quét được trước đó)
        if new_tag == 0:
            new_tag = old_tag

        # ── Parse prev_tag ────────────────────────────────────────────────────
        fw_prev = int(data.get("prev_tag", 0) or 0)
        if new_tag != old_tag and old_tag is not None:
            state.prev_tag = old_tag if old_tag else fw_prev
        elif state.prev_tag == 0 and fw_prev:
            state.prev_tag = fw_prev

        prev_tag = state.prev_tag

        # ── Cập nhật edge reservation ─────────────────────────────────────────
        if new_tag != old_tag and old_tag is not None and old_tag != 0 \
                and new_tag is not None and new_tag != 0:
            _release_line_edge(agv_id, prev_tag, old_tag)

        state.current_tag     = new_tag
        # AGV đã đến tag mới → quên các node từng bị chặn vật lý trước đó
        if new_tag != old_tag and new_tag is not None:
            state.accumulated_blocked.clear()
        state.driving         = bool(data.get("driving", False))
        state.paused          = bool(data.get("paused",  False))
        state.operating_mode  = str(data.get("operatingMode", "MANUAL"))
        state.error_code      = int(data.get("error_code", 0) or 0)
        if state.error_code != 0:
            self._had_error[agv_id] = True   # đánh dấu — cứu-kẹt watchdog sẽ dùng khi lỗi hết
        state.battery_low     = bool(data.get("battery_low", False))
        state.battery_blocking = bool(data.get("battery_blocking", False))
        state.last_update     = time.time()

        # Nhận được state message → AGV chắc chắn đang online
        if state.connection_state != "ONLINE":
            print(f"[LINE_AGV] {agv_id}: auto ONLINE (state message received)")
        state.connection_state = "ONLINE"

        # Battery (2 format)
        batt_obj = data.get("batteryState") or {}
        if batt_obj:
            state.battery = int(batt_obj.get("batteryCharge", state.battery) or state.battery)
        elif "battery" in data:
            state.battery = int(data["battery"] or 0)

        # ── ACK ───────────────────────────────────────────────────────────────
        ack_id = str(data.get("ack", "") or "").strip()
        if ack_id:
            state.last_ack = ack_id
            self._pending_cmds.pop(agv_id, None)
            # Đánh dấu acked cho rolling plan
            route = self._routes.get(agv_id)
            if route and route.sent_cmd_id == ack_id:
                route.acked = True

        # ── Cập nhật current_edge_pair ────────────────────────────────────────
        # GIỮ ĐÚNG 1 edge = cạnh ĐANG đi (prev→current). Khi sang cạnh mới phải NHẢ
        # cạnh cũ NGAY (trước đây chỉ nhả khi dừng hẳn → cạnh "ma" như 5_to_17 của xe
        # vừa rời node 17 đi đường khác vẫn bị giữ → xe khác tưởng head-on, đứng chờ
        # mãi). Dòng 1187 nhả theo (prev,old) là no-op vì prev đã bị gán = old.
        if state.driving and state.prev_tag and state.current_tag:
            _new_pair = (state.prev_tag, state.current_tag)
            if state.current_edge_pair and state.current_edge_pair != _new_pair:
                _of, _ot = state.current_edge_pair
                _release_line_edge(agv_id, _of, _ot)
            state.current_edge_pair = _new_pair
            _reserve_line_edge(agv_id, state.prev_tag, state.current_tag)
        else:
            if state.current_edge_pair:
                _release_all_line_edges(agv_id)
                state.current_edge_pair = None

        # ── Log thay đổi tag ──────────────────────────────────────────────────
        if new_tag != old_tag:
            print(f"[LINE_AGV] {agv_id}: tag {old_tag}→{new_tag}  "
                  f"bat={state.battery}%  bat_low={state.battery_low}  "
                  f"driving={state.driving}")
            # Cập nhật vị trí trong TrafficCoordinator
            if new_tag is not None:
                traffic_coordinator.update_position(agv_id, str(new_tag))
            # ── Chạy thử thủ công: tới đúng tag mục tiêu → dừng ngay, không cần map ──
            if state.test_drive_target and str(new_tag) == state.test_drive_target:
                from mqtt_client import send_line_command as _sdlc_stop
                _sdlc_stop(agv_id, "stop")
                state.test_drive_target = None
                try:
                    from main import _sync_manual_lidar as _sml_stop
                    _sml_stop(agv_id, force_on=True)
                except Exception:
                    pass
                print(f"[LINE_AGV] {agv_id}: chạy thử — đã tới tag {new_tag}, dừng xe")
            # ── Cửa tự động: xe tới node cửa MÀ đã được ghi nhận "đang ở giữa
            # cửa" (đã vào từ phía kia trước đó, xem door_coordinator.py) →
            # ĐÃ THOÁT cửa, báo có thể đóng (nếu không còn xe khác đang qua).
            # KHÔNG cần xe dừng — chạy nền, dựa thuần vào tag report. LƯU Ý: 2
            # node của 1 cửa KHÔNG bắt buộc liền kề (có thể cách nhiều node
            # trung gian) nên KHÔNG so old_tag với node cặp — is_exit_arrival tự
            # theo dõi đúng theo từng xe, không phụ thuộc khoảng cách giữa 2 node.
            if new_tag is not None:
                try:
                    from mqtt_client import map_manager as _mm_door_exit
                    _na_exit = (getattr(_mm_door_exit, 'node_actions', {}) or {}).get(str(new_tag)) or {}
                    _door_id_exit = str(_na_exit.get('door_id') or '').strip()
                    if _door_id_exit:
                        from door_coordinator import door_coordinator as _door_co_exit
                        if _door_co_exit.is_exit_arrival(_door_id_exit, agv_id, str(new_tag)):
                            _door_co_exit.notify_exit(_door_id_exit, agv_id)
                except Exception as _e_door_exit:
                    print(f"[LINE_AGV] {agv_id}: door exit-check lỗi: {_e_door_exit}")
        elif old_tag is None and new_tag is None:
            print(f"[LINE_AGV] {agv_id}: state received (no tag in payload)")

        # ── Móc hàng — theo đúng giao thức firmware gửi (tài liệu "AGV KÉO ↔
        # FMS" v1.1, 28/08/2026) — 4 kênh trong MỌI gói state, ưu tiên kênh
        # nào xác định được trước thì dùng luôn, không cần xét kênh còn lại:
        #   Kênh C — hook_report + hook_report_seq: kết quả thao tác gần
        #     nhất, LẶP LẠI mỗi gói (burst 300ms rồi theo heartbeat) cho tới
        #     khi FMS ACK đúng — đáng tin nhất, dedupe theo seq. QUAN TRỌNG
        #     (đúng yêu cầu tài liệu §4.4): xử lý logic CHỈ 1 LẦN/seq, nhưng
        #     phải ACK LẠI cho MỌI lần nhận kể cả seq trùng — phòng khi ACK
        #     lần trước bị rớt gói thì bản lặp sau vẫn dừng được firmware.
        #   Kênh A — "hook" (moving/up/dn/up_fail/dn_fail): trạng thái tức
        #     thời, LUÔN có, không cần ACK, không bao giờ biến mất khỏi gói
        #     — dùng khi kênh C không cho tin gì mới lượt này (report đã xử
        #     lý rồi/không có report — vd sau 20s GIVE UP firmware ngừng gửi
        #     report nhưng "hook" vẫn còn) — lưới an toàn cuối cùng.
        #   Kênh B — hook_uplim/hook_dnlim (cữ giới hạn thô, digitalRead()
        #     trực tiếp): chỉ dùng khi cả C lẫn A đều không có gì (hiếm).
        # Kênh D (event="hook_raised"...) đã xử lý ở nhánh event chung bên
        # dưới — chỉ là bản sao 1-lần của kênh C từ bản vá 28/08, guard
        # _hook_handled_as tránh xử lý trùng khi cả 2 kênh cùng có trong 1 gói.
        _hook_report     = str(data.get("hook_report") or "").strip()
        _hook_report_seq = int(data.get("hook_report_seq") or 0)
        _hook_handled_as: Optional[str] = None
        if _hook_report and _hook_report_seq:
            _hook_handled_as = _hook_report
            # ACK ngay, kể cả seq đã xử lý trước đó (§4.3/§4.4 tài liệu) —
            # gửi kèm cả "d" lẫn "seq" theo đúng dạng khuyến nghị.
            try:
                from mqtt_client import send_line_command as _slc_hkrep
                _slc_hkrep(agv_id, "ack_event", d=_hook_report, seq=_hook_report_seq)
            except Exception as _e_hkrep_ack:
                print(f"[LINE_AGV] {agv_id}: ack hook_report lỗi: {_e_hkrep_ack}")
            if _hook_report_seq != state.hook_report_seq_seen:
                state.hook_report_seq_seen = _hook_report_seq
                self._handle_event(agv_id, _hook_report, data, state)
        else:
            _hook_field = str(data.get("hook") or "").strip()
            if not _hook_field:
                if data.get("hook_uplim") is not None or data.get("hook_dnlim") is not None:
                    _hook_field = "up" if bool(data.get("hook_uplim")) else (
                        "dn" if bool(data.get("hook_dnlim")) else "")
            if _hook_field == "up" and state.hook_state != "raised":
                self._handle_event(agv_id, "hook_raised", data, state)
                _hook_handled_as = "hook_raised"
            elif _hook_field == "dn" and state.hook_state != "lowered":
                self._handle_event(agv_id, "hook_lowered", data, state)
                _hook_handled_as = "hook_lowered"
            elif _hook_field == "up_fail" and state.hook_raise_sent_at > 0 and not state.hook_fallback_notified:
                state.hook_fallback_notified = True
                self._handle_event(agv_id, "hook_raise_failed", data, state)
                _hook_handled_as = "hook_raise_failed"
            elif _hook_field == "dn_fail" and state.hook_pending == "pickup" and not state.hook_fallback_notified:
                state.hook_fallback_notified = True
                self._handle_event(agv_id, "hook_lower_failed", data, state)
                _hook_handled_as = "hook_lower_failed"

        # Đối chiếu độc lập (tài liệu §8, dòng cuối): cữ trên/dưới cùng false
        # trong khi "hook" báo đã xong (không phải "moving") → bất thường
        # (tuột cữ/lỗi cơ khí) — chỉ cảnh báo, không tự suy luận trạng thái.
        _hook_now = str(data.get("hook") or "").strip()
        if (_hook_now and _hook_now != "moving"
                and data.get("hook_uplim") is not None and data.get("hook_dnlim") is not None
                and not bool(data.get("hook_uplim")) and not bool(data.get("hook_dnlim"))):
            print(f"[LINE_AGV] {agv_id}: ⚠️ móc BẤT THƯỜNG — hook='{_hook_now}' nhưng "
                  f"cả 2 cữ giới hạn đều false (có thể tuột cữ/lỗi cơ khí)")

        # ── Xử lý event từ xe ────────────────────────────────────────────────
        event_name = str(data.get("event", "") or "").strip()
        if event_name and event_name != _hook_handled_as:
            self._handle_event(agv_id, event_name, data, state)

        # ── Rolling plan: kiểm tra có cần gửi cửa sổ tiếp không ─────────────
        if new_tag != old_tag:
            self._check_rolling_plan(agv_id, state)
            # Khi xe này di chuyển, kiểm tra lại các xe khác đang chờ conflict
            self._check_waiting_agvs(agv_id)

        # ── Detect: AGV dừng ở node ngoài route (do plan cũ còn đang chạy) ──
        # Xảy ra khi flex-park plans được gửi NHƯNG firmware vẫn chạy plan cũ
        # (ví dụ: đã quay trái tại ngã tư trước khi nhận plan mới → tới node 9
        # trong khi server route đang là [4,18,5]).
        # Không có arrived_wait_sys event vì firmware plan không khớp route server.
        if (new_tag != old_tag and new_tag is not None
                and not state.driving and not state.task_lifecycle):
            _route_now = self._routes.get(agv_id)
            if _route_now and _route_now.is_complete and _route_now.full_path:
                _exp_end = _route_now.full_path[-1]
                if str(new_tag) != str(_exp_end) and str(new_tag) not in _route_now.full_path:
                    print(f"[LINE_AGV] {agv_id}: dừng bất ngờ tại {new_tag} "
                          f"(route chờ đích {_exp_end}) → coi như off_route, re-dispatch")
                    self._handle_event(agv_id, "off_route", {}, state)

        # ── Obstacle timeout: sau OBSTACLE_REROUTE_TIMEOUT → tự reroute ──────
        if state.obstacle_since is not None:
            elapsed = time.monotonic() - state.obstacle_since
            if elapsed >= OBSTACLE_REROUTE_TIMEOUT:
                self._handle_obstacle_timeout(agv_id, state)

        # ── Cửa tự động: kiểm tra định kỳ có cửa nào xin mở mà chưa thấy xác
        # nhận sau timeout không (tự gửi lại) — chạy mỗi state message của BẤT
        # KỲ AGV nào (cửa không thuộc riêng 1 xe). Xem door_coordinator.py.
        try:
            from door_coordinator import door_coordinator as _door_co_tick
            _door_co_tick.check_retries()
        except Exception as _e_door_tick:
            print(f"[LINE_AGV] door check_retries lỗi: {_e_door_tick}")

        # ── CỨU KẸT MÓC: gửi lại lệnh NÂNG móc nếu không thấy phản hồi ───────
        # Lệnh 'action' nâng móc là 1 lệnh RỜI RẠC, KHÔNG nằm trong cơ chế resend
        # plan/rolling-window ở dưới — nếu gói MQTT bị rớt (đã xảy ra thực tế: publish
        # rc=0 nhưng không có hook_raised/hook_raise_failed nào quay về), xe đứng chờ
        # MÃI MÃI vì không có gì tự phát hiện. Theo dõi qua hook_raise_sent_at (set khi
        # gửi, xoá khi có phản hồi hook_raised/lỗi rõ ràng) — quá HOOK_RAISE_TIMEOUT
        # giây mà vẫn treo (hook_pending còn set, hook_state chưa 'raised') → gửi lại,
        # tối đa HOOK_RAISE_MAX_RETRIES lần rồi thôi (tránh spam vô hạn nếu móc thật
        # sự hỏng cơ khí — cần người can thiệp).
        if (state.hook_pending is not None and state.hook_state != "raised"
                and state.hook_raise_sent_at > 0):
            _hook_elapsed = time.monotonic() - state.hook_raise_sent_at
            if _hook_elapsed >= HOOK_RAISE_TIMEOUT:
                if state.hook_raise_retries < HOOK_RAISE_MAX_RETRIES:
                    state.hook_raise_retries += 1
                    print(f"[LINE_AGV] {agv_id}: không thấy phản hồi NÂNG móc sau "
                          f"{_hook_elapsed:.1f}s → GỬI LẠI lần "
                          f"{state.hook_raise_retries}/{HOOK_RAISE_MAX_RETRIES}")
                    self._send_hook_raise_delayed(agv_id, delay=0.0)
                else:
                    _msg_hk_retry = (f"⚠️ AGV {agv_id}: gửi lại {HOOK_RAISE_MAX_RETRIES} lần "
                          f"vẫn không có phản hồi NÂNG móc tại node {state.current_tag} — "
                          f"dừng thử tự động, cần kiểm tra thủ công (hook_state hiện tại "
                          f"có thể KHÔNG đúng thực tế).")
                    print(f"[LINE_AGV] {agv_id}: {_msg_hk_retry}")
                    state.hook_raise_sent_at = 0.0   # tránh lặp lại log này mỗi tick
                    try:
                        from telegram_bot import notify_error as _tg_notify_hk
                        _tg_notify_hk(_msg_hk_retry)
                    except Exception as _e_tg_hk:
                        print(f"[LINE_AGV] {agv_id}: gửi Telegram cảnh báo NÂNG móc lỗi: {_e_tg_hk}")

        # ── CỨU KẸT: AGV DỪNG GIỮA route (nghi ngờ firmware lỡ dừng/mất gói) ─────
        # Từng bị TẮT HẲN (comment) vì có thể ghi đè mất _trailer_exit_steps (tắt
        # Lidar + lùi mù + quay đầu, chèn 1 LẦN DUY NHẤT lúc dispatch ban đầu, KHÔNG
        # nằm trong build_plan_window) nếu resend rơi đúng lúc xe còn ở full_path[0]
        # đang dở thao tác đó — xe hiểu nhầm resend thành "tiến thẳng từ tag hiện
        # tại", bỏ mất hẳn lùi/quay (lỗi thực tế đã xảy ra ở tag 10).
        #
        # BẬT LẠI vì phát sinh vấn đề khác nghiêm trọng hơn: khi xe lỗi giữa route
        # (vd lệch line) rồi được can thiệp THỦ CÔNG đưa về đúng line nhưng KHÔNG
        # băng qua tag RFID mới (vẫn đứng yên tại tag cũ) → _check_rolling_plan()
        # không tự kích (chỉ chạy khi new_tag != old_tag) → xe đứng yên MÃI dù lỗi
        # đã hết, không có cách nào tự phục hồi. Đây là cơ chế DUY NHẤT xử lý ca đó.
        #
        # AN TOÀN: chỉ chặn ĐÚNG trường hợp rủi ro gốc — resend khi xe còn ở node
        # ĐẦU route (current_idx==0) VÀ route đó có has_exit_steps=True (xem
        # LineAGVRoute, được main.py:_dispatch_go_to gán ngay sau set_route).
        #
        # CHỈ KÍCH HOẠT SAU KHI XE TỪNG BÁO LỖI (self._had_error, set khi error_code
        # != 0) — KHÔNG chạy cho mọi ca đứng yên bình thường (đứng chờ hợp lệ vì lý
        # do khác không phải lỗi thì KHÔNG cần "cứu", tự có cơ chế riêng xử lý —
        # tránh polling/resend tràn lan không cần thiết). Chỉ resend ĐÚNG 1 LẦN cho
        # mỗi đợt lỗi (xoá cờ _had_error ngay sau khi gửi) — nếu vẫn kẹt sau lần đó,
        # KHÔNG tự lặp lại nữa (không "spam" 7s/lần), cần người can thiệp tiếp.
        if new_tag != old_tag or state.driving or state.operating_mode == "SEMIAUTOMATIC":
            self._stopped_since.pop(agv_id, None)   # nhúc nhích/đi tiếp → reset
            self._mid_resend_ts.pop(agv_id, None)
        try:
            _route_s = self._routes.get(agv_id)
            if (_route_s and _route_s.full_path and state.current_tag is not None
                    and not state.driving and not state.task_lifecycle
                    and state.operating_mode != "SEMIAUTOMATIC"
                    and state.obstacle_since is None and not event_name
                    and not _route_s.waiting_before_conflict
                    and state.error_code == 0
                    and self._had_error.get(agv_id, False)):
                _ct_s = str(state.current_tag)
                _ci_s = _route_s.full_path.index(_ct_s) if _ct_s in _route_s.full_path else -1
                _unsafe_exit_s = (_ci_s == 0 and _route_s.has_exit_steps)
                _next_s = (_route_s.full_path[_ci_s + 1]
                           if 0 <= _ci_s < len(_route_s.full_path) - 1 else None)
                _blocked_s = (traffic_coordinator.node_reserved_by_other(agv_id, _next_s)
                              if _next_s else None)
                if 0 <= _ci_s < _route_s.window_end and not _blocked_s and not _unsafe_exit_s:
                    _now_s = time.monotonic()
                    self._stopped_since.setdefault(agv_id, _now_s)
                    if (_now_s - self._stopped_since[agv_id] >= STUCK_RESEND_GRACE
                            and _now_s - self._mid_resend_ts.get(agv_id, 0.0) >= STUCK_RESEND_COOLDOWN):
                        self._mid_resend_ts[agv_id] = _now_s
                        self._had_error[agv_id] = False   # tiêu thụ — chỉ resend 1 lần/đợt lỗi
                        print(f"[LINE_AGV] {agv_id}: vừa hết lỗi, đứng yên tại {_ct_s} "
                              f"(đường thông tới {_route_s.full_path[_route_s.window_end]}) "
                              f"— GỬI LẠI cửa sổ để đi tiếp (1 lần)")
                        self._send_window(agv_id, _route_s, _ci_s,
                                          _route_s.window_end, _route_s.is_complete,
                                          force=True)
        except Exception as _e_mr:
            print(f"[LINE_AGV] {agv_id}: mid-route resend error: {_e_mr}")

        # ── CỨU KẸT NODE BIÊN: AGV tới ĐÍCH ĐOẠN (window_end) nhưng KHÔNG nhận
        # arrived_wait_sys (firmware tới nơi mà không báo / mất gói) → đoạn KHÔNG bao giờ
        # hoàn tất → kẹt HẲN, dispatch lệnh kế không chạy (chính lỗi AGV02 kẹt ở node 2).
        # GIỚI HẠN ở segment 'transit' (staging/đi giữa) để KHÔNG đụng lifecycle giao/sạc.
        # Sau grace → tự sinh arrived_wait_sys để hoàn tất đoạn + dispatch kế.
        # KHÔNG kích khi error_code != 0 (xem giải thích ở watchdog phía trên).
        try:
            _route_b = self._routes.get(agv_id)
            if (_route_b and _route_b.full_path and state.current_tag is not None
                    and not state.driving and not state.task_lifecycle
                    and state.obstacle_since is None and not event_name
                    and not _route_b.waiting_before_conflict
                    and state.error_code == 0
                    and getattr(_route_b, 'task_type', '') == 'transit'):
                _ct_b = str(state.current_tag)
                _ci_b = (_route_b.full_path.index(_ct_b)
                         if _ct_b in _route_b.full_path else -1)
                # ĐANG CHỜ reservation (node kế bị xe khác giữ) ≠ KẸT mất gói →
                # KHÔNG tự sinh; _check_waiting_agvs sẽ resume khi node được nhả.
                _nxt_b = (_route_b.full_path[_ci_b + 1]
                          if 0 <= _ci_b < len(_route_b.full_path) - 1 else None)
                _res_wait_b = bool(
                    _nxt_b and traffic_coordinator.node_reserved_by_other(agv_id, _nxt_b))
                if _ci_b >= 0 and _ci_b == _route_b.window_end and not _res_wait_b:
                    _now_b = time.monotonic()
                    self._stopped_since.setdefault(agv_id, _now_b)
                    if (_now_b - self._stopped_since[agv_id] >= STUCK_RESEND_GRACE
                            and _now_b - self._mid_resend_ts.get(agv_id, 0.0) >= STUCK_RESEND_COOLDOWN):
                        self._mid_resend_ts[agv_id] = _now_b
                        print(f"[LINE_AGV] {agv_id}: KẸT tại node biên {_ct_b} (đích đoạn "
                              f"transit) — KHÔNG nhận arrived_wait_sys → TỰ SINH để hoàn tất")
                        self._handle_event(agv_id, 'arrived_wait_sys', {}, state)
        except Exception as _e_be:
            print(f"[LINE_AGV] {agv_id}: boundary-stuck recovery error: {_e_be}")

        # ── Retry: gửi lại nếu không nhận ACK sau RETRY_TIMEOUT ──────────────
        self._check_retry(agv_id, state)

        # ── Callback thay đổi state ───────────────────────────────────────────
        if self.on_state_changed:
            try:
                self.on_state_changed(state)
            except Exception as e:
                print(f"[LINE_AGV] on_state_changed error: {e}")

    # ── Rolling plan ──────────────────────────────────────────────────────────

    # ══════════════════════════════════════════════════════════════════════════
    # Conflict-aware helpers
    # ══════════════════════════════════════════════════════════════════════════

    def _is_same_direction(
        self, my_path: list[str], edge_fn: str, edge_tn: str, other_id: str
    ) -> bool:
        """
        Kiểm tra xe kia (other_id) đi CÙNG CHIỀU với chúng ta trên edge fn→tn.
        Cùng chiều = trong route của xe kia, fn xuất hiện TRƯỚC tn (cùng thứ tự).
        Ngược chiều (head-on) = tn xuất hiện trước fn.
        Không rõ (xe kia không đăng ký) = coi là khác chiều để an toàn.
        """
        other_reg = traffic_coordinator._registered.get(other_id)
        if not other_reg:
            other_route = self._routes.get(other_id)
            if not other_route:
                return False
            op = other_route.full_path
        else:
            op = other_reg['path']
        try:
            idx_fn = op.index(str(edge_fn))
            idx_tn = op.index(str(edge_tn))
            return idx_fn < idx_tn
        except ValueError:
            # fn không có trong route xe kia (xe kia bắt đầu từ tn hoặc nhánh khác).
            # So sánh node tiếp theo sau tn trong cả 2 path để xác định hướng.
            try:
                idx_tn_op = op.index(str(edge_tn))
                if idx_tn_op < len(op) - 1:
                    op_next = op[idx_tn_op + 1]
                    my_idx_tn = my_path.index(str(edge_tn))
                    if my_idx_tn < len(my_path) - 1:
                        return my_path[my_idx_tn + 1] == op_next
            except ValueError:
                pass
            return False

    def _find_upcoming_conflict(
        self, agv_id: str, route: LineAGVRoute,
        from_idx: int, to_idx: int,
    ) -> Optional[int]:
        """
        Quét path[from_idx..to_idx] tìm xung đột THỰC SỰ:
          1. Physical edge bị xe khác ĐANG GIỮ (edge reservation).
          2. Node tiếp theo có xe ĐỨNG YÊN và đi NGƯỢC CHIỀU (hoặc không rõ chiều).
             → Cùng chiều + đứng yên = đơn giản là xe phía trước, KHÔNG coi là conflict.
          3. HEAD-ON: xe khác sẽ đi tn→fn (ngược chiều chúng ta).

        Nguyên tắc: chỉ conflict khi 2 xe đi NGƯỢC CHIỀU nhau trên cùng đoạn đường.
        Cùng chiều = following = không block, chờ tự nhiên.
        """
        path = route.full_path

        # Tập nodes xe khác đang dừng + chiều đi của chúng
        # {node: other_id}
        stopped_opposite: dict[str, str] = {}
        for oid, st in self.state_store._states.items():
            if oid == agv_id or st is None:
                continue
            if st.current_tag is not None and not st.driving:
                stopped_opposite[str(st.current_tag)] = oid

        # Tập future edges của xe khác (chỉ edges chưa qua)
        future_edges: dict[tuple[str, str], str] = {}
        for oid, other_route in self._routes.items():
            if oid == agv_id or not other_route or not other_route.full_path:
                continue
            op  = other_route.full_path
            ost = self.state_store.get(oid)
            cur_idx = 0
            if ost and ost.current_tag:
                try:
                    cur_idx = op.index(str(ost.current_tag))
                except ValueError:
                    pass
            for j in range(cur_idx, len(op) - 1):
                future_edges[(op[j], op[j + 1])] = oid

        for i in range(from_idx, min(to_idx, len(path) - 1)):
            fn = path[i]
            tn = path[i + 1]

            # 0. BLOCK same_dir: node tn thuộc block "cùng chiều" đang có xe NGƯỢC
            #    chiều bên trong → phải chờ trước block (SINGLE block đã được bắt qua
            #    node_reserved_by_other vì cả vùng bị khoá). Edge head-on đã có ở #3.
            _bid = traffic_coordinator._block_of_node.get(str(tn))
            if _bid and traffic_coordinator._block_type.get(_bid) == 'same_dir':
                _holders = traffic_coordinator._block_holders.get(_bid, set()) - {agv_id}
                _bdir    = traffic_coordinator._block_dir.get(_bid)
                if _holders and _bdir is not None and _bdir != route.direction:
                    print(f"[TRAFFIC] {agv_id}: block {_bid} (same_dir) đang có xe ngược "
                          f"chiều {_holders} → chờ trước {tn}")
                    return -(i + 1)

            # 1. Physical edge reservation
            for eid in (f"{fn}_to_{tn}", f"{tn}_to_{fn}"):
                owner = _line_blocked_edges.get(eid)
                if owner and owner != agv_id:
                    # Chỉ conflict nếu xe kia đi ngược chiều trên edge này
                    if not self._is_same_direction(path, fn, tn, owner):
                        return i

            # 2. Xe đứng yên tại tn
            if tn in stopped_opposite:
                other_id_stopped = stopped_opposite[tn]
                # Nếu tn là ĐIỂM ĐẾN CUỐI của route ta → không reroute (không có nơi khác để đi),
                # chỉ halt+chờ cho đến khi node đó trống. Destination conflict được xử lý
                # ở dispatch level; rolling plan chỉ cần giữ xe chờ ở node trước.
                if tn == path[-1]:
                    return -(i + 1)
                # Phân biệt bằng giá trị âm/dương để _check_rolling_plan biết cách xử lý:
                #   return i    → head-on: reroute + park
                #   return -i-1 → following: chỉ halt+chờ, KHÔNG reroute
                if not self._is_same_direction(path, fn, tn, other_id_stopped):
                    return i
                else:
                    return -(i + 1)

            _headon = future_edges.get((tn, fn))   # xe kia sẽ đi tn→fn (ngược chiều) = head-on

            # 3. Node tn ĐANG BỊ XE KHÁC KHOÁ (reservation) → tôi nhường.
            #    Khoá được gán bởi arbiter (reserve_ahead) → tất định, đúng 1 xe nhường.
            #    Bao quát cả GIAO NHAU TẠI NGÃ RẼ (2 xe tới cùng node từ 2 cạnh khác).
            _res_owner = traffic_coordinator.node_reserved_by_other(agv_id, tn)
            if _res_owner:
                if tn == path[-1]:
                    return -(i + 1)
                if _headon == _res_owner:
                    # Head-on thật. CHỈ bên THUA arbiter mới reroute/né; bên THẮNG CHỜ
                    # (xe thua sẽ né → node trống → ta đi). KHÔNG để CẢ HAI cùng reroute
                    # → cùng nhảy nhánh khác → vẫn đâm (dao động).
                    if traffic_coordinator._arbitrate(agv_id, _res_owner, tn) == agv_id:
                        print(f"[TRAFFIC] {agv_id}: {tn} bị {_res_owner} (head-on) nhưng TÔI "
                              f"thắng arbiter → CHỜ ({_res_owner} sẽ né)")
                        return -(i + 1)
                    print(f"[TRAFFIC] {agv_id}: {tn} bị {_res_owner} khoá (head-on) → tôi nhường+reroute")
                    return i
                # Ngã rẽ / cùng chiều → chờ trước node cho xe kia đi qua (không reroute)
                print(f"[TRAFFIC] {agv_id}: {tn} bị {_res_owner} khoá (ngã rẽ/cùng chiều) → chờ")
                return -(i + 1)

            # 4. Head-on DỰ ĐOÁN (xe kia chưa khoá tn nhưng sẽ đi ngược chiều):
            #    trọng tài TẤT ĐỊNH quyết định đúng 1 xe nhường (tránh cùng nhường → kẹt).
            if _headon:
                if traffic_coordinator._arbitrate(agv_id, _headon, tn) == agv_id:
                    print(f"[TRAFFIC] {agv_id}: head-on {fn}→{tn} với {_headon} "
                          f"→ TÔI ưu tiên (arbiter), đi tiếp")
                    continue
                print(f"[TRAFFIC] {agv_id}: head-on {fn}→{tn} → nhường {_headon} (arbiter)")
                return i

        return None

    def _try_line_reroute(
        self, agv_id: str, state: LineAGVState,
        route: LineAGVRoute, current_idx: int,
        extra_blocked_nodes: Optional[set] = None,
        avoid_all: bool = False,
    ) -> bool:
        """
        Tìm đường thay thế tránh edges/nodes đang bị chiếm.
        extra_blocked_nodes: set các node cần tránh thêm (vd: vật cản vật lý phía trước).
        avoid_all=True: né đường của MỌI xe đăng ký (không chỉ xe mạnh hơn) — dùng khi
        BUỘC phải rời đường hiện tại vì vật cản (quy tắc bất đối xứng không áp dụng:
        mình đã không thể giữ đường ngắn nữa, reroute mù vào hành lang xe khác = đâm).
        Cập nhật route.full_path và gửi window mới nếu tìm được.
        Trả về True nếu reroute thành công.
        """
        try:
            import networkx as nx
            from mqtt_client import map_manager as _mm

            current_node = route.full_path[current_idx]
            dest_node    = route.full_path[-1]
            if current_node == dest_node:
                return False

            # ── CHỐNG FLIP-FLOP: reroute-do-obstacle (avoid_all) vừa làm < REROUTE_COOLDOWN
            #    giây trước → KHÔNG reroute lại (sẽ lật về nhánh kia của vòng → dao động +
            #    plan-race). Để caller rơi xuống WAIT-BASED (đứng chờ tại chỗ) — đã COMMIT
            #    nhánh vừa chọn. Né head-on chủ động (avoid_all=False) KHÔNG bị chặn.
            if avoid_all:
                _now_rr = time.monotonic()
                if _now_rr - self._reroute_ts.get(agv_id, 0.0) < REROUTE_COOLDOWN:
                    print(f"[LINE_AGV] {agv_id}: BỎ reroute (vừa reroute < {REROUTE_COOLDOWN:.0f}s "
                          f"→ giữ nhánh đã chọn, chờ tại chỗ — chống dao động lật nhánh)")
                    return False

            g = (_mm.line_graph if _mm.line_graph else _mm.graph).copy()

            # ── TRAFFIC-AWARE: PHẠT MỀM đường xe khác (như planner) ──────────────
            # Phạt (cộng weight) cạnh trên path đăng ký + nặng quanh vị trí xe khác
            # → reroute ưu tiên NHÁNH VÒNG né hẳn xe kia; nhưng nếu đường ĐƠN (không
            # có vòng) thì shortest_path trả về ĐÚNG đường cũ → không reroute → chờ.
            _PEN_PATH = 1000.0
            _PEN_POS  = 10000.0

            def _bump(_u, _v, _amt):
                if g.has_edge(_u, _v):
                    g[_u][_v]['weight'] = g[_u][_v].get('weight', 1.0) + _amt

            # Xe CÓ route → phạt cả TRAJECTORY (path đăng ký). Path[current_idx:] đã
            # bắt đầu từ vị trí xe → tự bao gồm hướng nó đang đi; KHÔNG phạt riêng vị
            # trí (sẽ over-phạt các cạnh xe KHÔNG đi, đẩy mình vào đúng đường nó — đâm).
            _routed = set()
            # Duyệt CẢ xe đăng ký LẪN xe đang chờ có intent_route (deregistered nhưng
            # vẫn có ý định đi) → thấy được đường của xe đang đứng chờ để né.
            for _oid in (set(traffic_coordinator._registered)
                         | set(traffic_coordinator._intent_route)):
                if _oid == agv_id:
                    continue
                _routed.add(_oid)
                # BẤT ĐỐI XỨNG: chỉ né đường xe MẠNH hơn (chống dao động — nếu cả 2 cùng
                # né nhau sẽ cùng nhảy sang 1 nhánh → vẫn đâm). Xe mạnh đi đường ngắn.
                # avoid_all=True (vật cản ép rời đường): né đường của MỌI xe.
                if not avoid_all and not traffic_coordinator.should_avoid_path_of(agv_id, _oid):
                    continue
                # Ưu tiên TUYẾN ĐẦY ĐỦ (intent) — biết cả phần sẽ đi sau khi dispatch
                # chia đoạn / đang đứng chờ (vd 18→5→17 của xe chờ tới 17).
                _intent = traffic_coordinator._intent_route.get(_oid)
                if _intent and len(_intent) >= 2:
                    _op = _intent; _oc = 0
                else:
                    _oreg = traffic_coordinator._registered.get(_oid, {})
                    _op = _oreg.get('path', []); _oc = _oreg.get('current_idx', 0)
                for _j in range(_oc, len(_op) - 1):
                    _a, _b = str(_op[_j]), str(_op[_j + 1])
                    _bump(_a, _b, _PEN_PATH); _bump(_b, _a, _PEN_PATH)
            # Né VỊ TRÍ xe đang DỪNG (driving=False) — BẤT ĐỐI XỨNG: chỉ né vị trí xe
            # MẠNH hơn (mình yếu → tránh đường nó), HOẶC xe đậu yên KHÔNG route (vật cản
            # tĩnh). KHÔNG né vị trí xe YẾU hơn có route: mình mạnh → đi đường ngắn, dừng
            # trước nó CHỜ nó dời (reserve không giành node nó đang đứng). Né vị trí xe
            # yếu = xe mạnh nhảy nhánh khác → trùng nhánh xe yếu → dao động/kẹt.
            for _oid2, st in self.state_store._states.items():
                if (_oid2 == agv_id or st is None or st.current_tag is None
                        or getattr(st, 'driving', False)):
                    continue
                _registered = _oid2 in traffic_coordinator._registered
                if (not avoid_all and _registered
                        and not traffic_coordinator.should_avoid_path_of(agv_id, _oid2)):
                    continue   # xe YẾU hơn có route → KHÔNG né vị trí (chờ nó dời)
                _cn = str(st.current_tag)
                if _cn != current_node and _cn != dest_node and _cn in g:
                    for _nb in list(g.neighbors(_cn)):
                        _bump(_cn, _nb, _PEN_POS); _bump(_nb, _cn, _PEN_POS)

            # Vật cản VẬT LÝ (LIDAR) → XOÁ cứng (không đi qua được thật)
            for eid, owner in list(_line_blocked_edges.items()):
                if owner == agv_id:
                    continue
                parts = eid.split("_to_")
                if len(parts) == 2:
                    n1, n2 = parts[0], parts[1]
                    if g.has_edge(n1, n2): g.remove_edge(n1, n2)
                    if g.has_edge(n2, n1): g.remove_edge(n2, n1)
            if extra_blocked_nodes:
                for nt in extra_blocked_nodes:
                    if nt and nt != current_node and nt != dest_node and nt in g:
                        g.remove_node(nt)

            try:
                new_path = nx.shortest_path(g, source=current_node,
                                            target=dest_node, weight="weight")
            except Exception:
                return False

            if list(new_path) == route.full_path[current_idx:]:
                # shortest_path (dù đã phạt) vẫn trả ĐÚNG đường cũ = KHÔNG có nhánh vòng
                # né được (đường ĐƠN thật, vd 4-19-64-2) → không reroute, để gọi chờ.
                return False

            # Cập nhật route
            route.full_path               = route.full_path[:current_idx] + list(new_path)
            route.waiting_before_conflict = None
            route.is_complete             = False

            # RE-ĐĂNG KÝ path mới với TrafficCoordinator → NHẢ reservation/edge/block CŨ
            # (vd node trên đường CŨ mà giờ KHÔNG đi qua nữa) rồi giữ chỗ theo đường MỚI.
            # THIẾU bước này → reservation CŨ STALE → xe khác chờ node mình ĐÃ RỜI mãi =
            # DEADLOCK (đúng lỗi: AGV02 reroute 8→5→18 → 8→15→9→4→18 nhưng node 5 vẫn bị nó
            # khoá → AGV01 "following xe phía trước dừng tại 5" chờ phantom mãi). reserve_ahead
            # tự release-trước-acquire theo `_registered[agv]['path']` nên PHẢI sửa path đó
            # trước. current_idx GIỮ NGUYÊN: prefix [:current_idx] không đổi → vị trí xe vẫn
            # đúng index.
            _reg_rr = traffic_coordinator._registered.get(agv_id)
            if _reg_rr is not None:
                _reg_rr['path'] = [str(n) for n in route.full_path]
                traffic_coordinator.reserve_ahead(agv_id)
            else:
                traffic_coordinator.register(agv_id, route.full_path,
                                             route.direction, route.task_type)
                traffic_coordinator._registered[agv_id]['current_idx'] = current_idx
                traffic_coordinator.reserve_ahead(agv_id)

            new_end  = min(current_idx + LOOKAHEAD, len(route.full_path) - 1)
            is_final = (new_end == len(route.full_path) - 1)
            self._send_window(agv_id, route, current_idx, new_end, is_final)
            if avoid_all:
                self._reroute_ts[agv_id] = time.monotonic()   # mốc chống flip-flop
            print(f"[LINE_AGV] {agv_id}: REROUTED → {new_path}")
            # THÔNG BÁO các xe khác RE-CHECK NGAY: reroute vừa NHẢ reservation (vd node 5)
            # → xe đang chờ node đó (vd AGV02 'following — dừng tại 5') phải đánh giá lại NGAY,
            # KHÔNG chờ tới state-message kế (nếu xe reroute đứng im/firmware lỡ dừng thì xe
            # chờ sẽ kẹt lâu vì không được trigger). Guard `_reroute_notifying` chống đệ quy
            # vô hạn (A reroute→báo B→B reroute→báo A…): chỉ báo 1 cấp.
            if not getattr(self, '_reroute_notifying', False):
                self._reroute_notifying = True
                try:
                    self._check_waiting_agvs(agv_id)
                finally:
                    self._reroute_notifying = False
            return True
        except Exception as e:
            print(f"[LINE_AGV] {agv_id}: _try_line_reroute error: {e}")
            return False

    def _handle_obstacle_timeout(self, agv_id: str, state: LineAGVState) -> None:
        """
        Gọi khi AGV bị obstacle > OBSTACLE_REROUTE_TIMEOUT.
        Chiến lược (theo thứ tự):
          1. Reroute cùng hướng (tránh node phía trước có vật cản)
          2. Reroute hướng ngược (đường dài hơn nhưng vẫn đến đích)
          3. Flexible parking: đỗ vào node BFS gần nhất không tranh chấp
          4. Full re-dispatch: xóa route, queue lại đích để _dispatch_go_to tính lại
        """
        route = self._routes.get(agv_id)
        state.obstacle_since = None

        if not route or state.current_tag is None:
            return
        try:
            current_idx = route.full_path.index(str(state.current_tag))
        except ValueError:
            return

        orig_dir      = state.obstacle_direction or route.direction
        dest_final    = route.full_path[-1]

        # Kiểm tra obstacle tại node phía trước
        if current_idx + 1 < len(route.full_path):
            blocked_node = route.full_path[current_idx + 1]
            # Vật cản là XE KHÁC? Bắt cả xe ĐẬU YÊN ở NODE KỀ node bị chặn (thân xe
            # chắn ngã rẽ — tag không trùng blocked_node nhưng LIDAR vẫn thấy nó).
            _blocker = None
            try:
                _nbrs_o: set = set()
                try:
                    from mqtt_client import map_manager as _mm_o
                    _g_o = _mm_o.line_graph if _mm_o.line_graph else _mm_o.graph
                    if _g_o is not None and str(blocked_node) in _g_o:
                        _nbrs_o = set(map(str, _g_o.neighbors(str(blocked_node))))
                except Exception:
                    pass
                for oid, st in self.state_store._states.items():
                    if oid == agv_id or st is None or st.current_tag is None:
                        continue
                    _ot = str(st.current_tag)
                    if _ot == str(blocked_node):
                        _blocker = oid
                        break
                    if _ot in _nbrs_o and not getattr(st, 'driving', False):
                        _blocker = oid    # xe đậu yên sát node bị chặn → chính nó chắn
                        break
            except Exception:
                pass
            if _blocker:
                # BẤT ĐỐI XỨNG (chống THRASHING): vật cản là XE KHÁC → CHỈ bên THUA arbiter
                # mới ĐI VÒNG né; bên THẮNG ĐỨNG CHỜ (xe thua sẽ né/rời → mình đi tiếp).
                # Nếu CẢ HAI cùng obstacle-reroute (avoid_all) khi thấy nhau → cùng nhảy
                # nhánh → gặp lại → GIẰNG CO liên tục (đúng log: 2 xe né qua né lại quanh
                # 5-8-15-16). Arbiter THEO PRIORITY→ID (không truyền node) → ĐỐI XỨNG, cả 2
                # tính ra cùng winner (mỗi xe thấy blocked_node KHÁC nhau nên KHÔNG dùng node).
                _i_win_obs = (traffic_coordinator._arbitrate(agv_id, _blocker) == agv_id)
                if not _i_win_obs and self._try_line_reroute(
                        agv_id, state, route, current_idx, {str(blocked_node)},
                        avoid_all=True):
                    print(f"[LINE_AGV] {agv_id}: vật cản là AGV {_blocker} (tôi THUA) "
                          f"tại/gần {blocked_node} → ĐI VÒNG nhánh khác")
                    state.obstacle_since = None
                    return
                # ── CHỐNG DEADLOCK "winner chờ vô vọng" ──────────────────────────
                # Xe THẮNG mà đã GIỮ CHỖ node phía trước (blocked_node) VÀ xe cản là xe
                # ƯU TIÊN THẤP đang ĐỨNG YÊN (driving=False): nhiều khả năng nó bị CHÍNH
                # reservation của TA chặn (node kế của nó = node ta đang giữ) → nó KHÔNG
                # thể "né" → nếu ta cũng ĐỨNG CHỜ "để xe kia né" thì CẢ HAI đứng im =
                # DEADLOCK (đúng log: AGV02 thắng đứng chờ, AGV01 thua đứng chờ ở node 5).
                # → GỬI LẠI cửa sổ của MÌNH (force) để firmware THỬ đi tiếp qua node ta SỞ
                # HỮU (xe thua bị khoá sau ta, sẽ theo sau khi ta nhả). KHÔNG reroute (không
                # dao động) — chỉ resume route SẴN CÓ trên node đã reserve nên KHÔNG đâm.
                _own_ahead = (traffic_coordinator._node_res.get(str(blocked_node)) == agv_id)
                _blk_st    = self.state_store.get(_blocker)
                _blk_idle  = bool(_blk_st and not getattr(_blk_st, 'driving', False))
                if _i_win_obs and _own_ahead and _blk_idle:
                    _bn_end = min(current_idx + LOOKAHEAD, len(route.full_path) - 1)
                    _bn_fin = (_bn_end == len(route.full_path) - 1)
                    print(f"[LINE_AGV] {agv_id}: vật cản là AGV {_blocker} (tôi THẮNG & đã giữ "
                          f"{blocked_node}; xe kia đứng yên — không né được) → ĐI TIẾP "
                          f"(gửi lại window, không reroute)")
                    self._send_window(agv_id, route, current_idx, _bn_end, _bn_fin, force=True)
                    state.obstacle_since = None
                    return
                print(f"[LINE_AGV] {agv_id}: vật cản là AGV {_blocker} tại/gần {blocked_node} "
                      f"→ DỪNG CHỜ ({'thắng arbiter, để xe kia né' if _i_win_obs else 'không nhánh vòng'})")
                route.waiting_before_conflict = blocked_node
                state.obstacle_since = None
                return
            # Không có xe nào ở đó → vật cản THẬT (hộp/người) → mới tính reroute.
            state.accumulated_blocked.add(blocked_node)

        blocked_ahead = state.accumulated_blocked.copy() if state.accumulated_blocked else None

        print(f"[LINE_AGV] {agv_id}: obstacle timeout ({OBSTACLE_REROUTE_TIMEOUT}s) "
              f"dir={orig_dir} blocked={blocked_ahead}")

        # Thử 1: reroute cùng hướng (vật cản ép rời đường → né đường MỌI xe)
        if self._try_line_reroute(agv_id, state, route, current_idx, blocked_ahead,
                                  avoid_all=True):
            print(f"[LINE_AGV] {agv_id}: rerouted (same dir)")
            return

        # Thử 2: reroute hướng ngược (đường dài hơn nhưng hợp lý — bwd→fwd hay fwd→bwd)
        # CHỈ áp dụng nếu opposite == "fwd" (đảo bwd→fwd luôn an toàn), hoặc xe
        # thực sự lùi được — xe rơ-moóc/đầu kéo (can_reverse=False) TUYỆT ĐỐI
        # không được thử chuyển sang bwd, kể cả khi né vật cản.
        opposite = "fwd" if orig_dir == "bwd" else "bwd"
        _can_reverse_obs = True
        if opposite == "bwd":
            try:
                _can_reverse_obs = agv_registry.can_reverse(agv_id)
            except Exception:
                pass
        if opposite == "bwd" and not _can_reverse_obs:
            print(f"[LINE_AGV] {agv_id}: xe không lùi được — BỎ QUA thử reroute "
                  f"{orig_dir}→bwd, đi thẳng tới wait-based")
        else:
            print(f"[LINE_AGV] {agv_id}: switching {orig_dir}→{opposite}, trying reroute")
            route.direction          = opposite
            state.obstacle_direction = opposite
            if self._try_line_reroute(agv_id, state, route, current_idx, blocked_ahead,
                                      avoid_all=True):
                print(f"[LINE_AGV] {agv_id}: rerouted (opposite dir={opposite})")
                return
            # Restore direction nếu thử 2 thất bại
            route.direction          = orig_dir
            state.obstacle_direction = orig_dir

        # WAIT-BASED: KHÔNG flex-park sang node tùy ý (gây ra khỏi line). Reroute
        # (đường line khác) đã thử ở trên — nếu không có thì ĐỨNG YÊN CHỜ vật cản
        # tự hết (người/hộp di chuyển). An toàn hơn là tự lùi/né lung tung.
        print(f"[LINE_AGV] {agv_id}: không có đường line thay thế → ĐỨNG YÊN CHỜ "
              f"vật cản tại {state.accumulated_blocked} tự hết (wait-based)")
        route.waiting_before_conflict = (route.full_path[current_idx + 1]
                                         if current_idx + 1 < len(route.full_path)
                                         else str(dest_final))
        state.obstacle_since = None

    def _check_waiting_agvs(self, moved_agv_id: str) -> None:
        """
        Khi 1 xe di chuyển, proactive check lại tất cả xe khác đang active.
        Không chỉ check xe đang chờ — xe đang di chuyển cũng cần re-evaluate
        vì xe vừa di chuyển có thể đã giải phóng đoạn đường trước đó.
        """
        for oid, route in list(self._routes.items()):
            if oid == moved_agv_id or not route:
                continue
            st = self.state_store.get(oid)
            if st and st.current_tag is not None:
                # Xe vừa di chuyển có thể đã NHẢ node → cho xe đang chờ giữ chỗ LẠI
                # (mở rộng reservation) rồi mới đánh giá → window sẽ nới ra đi tiếp.
                traffic_coordinator.reserve_ahead(oid)
                self._check_rolling_plan(oid, st)

        # Trigger retry cho các AGV đang chờ ở cấp dispatch (bounce-detected)
        for oid, st in list(self.state_store._states.items()):
            if oid == moved_agv_id or st is None or not st.pending_retry_cmd:
                continue
            if st.driving:
                st.pending_retry_cmd = None
                continue
            # Xe đó đang đứng yên và chờ retry.
            # Dùng delay 5s để xe cản kịp thoát khỏi vùng xung đột trước khi re-dispatch.
            _cmd_name = st.pending_retry_cmd
            st.pending_retry_cmd = None   # xóa trước để tránh re-entry
            _oid = oid  # capture for closure
            try:
                import asyncio as _asyncio
                from task_queue import agv_task_queue as _atq_r
                from task_queue import CMD_GO_CHARGE as _CGC_r, CMD_GO_WAIT as _CGW_r, CMD_GO_TO as _CGT_r

                if _cmd_name == 'go_to':
                    # go_to retry: dispatch ngay (không cần delay — xe cản đã di chuyển)
                    _dest_r = getattr(st, 'pending_retry_dest', None)
                    # GIỮ session_id của lệnh gốc → để logic bỏ-qua-supply-node (đi
                    # thẳng tới đích, không dừng đòi xác nhận ở supply node trung gian
                    # như 64) hoạt động đúng. Mất session → tách nhầm ở mọi supply node.
                    _sess_r = getattr(st, 'pending_retry_session', None)
                    st.pending_retry_dest = None
                    st.pending_retry_session = None
                    if _dest_r:
                        print(f"[LINE_AGV] {oid}: dest-wait retry triggered by {moved_agv_id} → go_to {_dest_r} (session={_sess_r})")
                        _atq_r.dispatch_or_queue(oid, _CGT_r, dest_node=_dest_r, start_node=None,
                                                 session_id=_sess_r, session_label='dest_retry')
                else:
                    # go_charge/go_wait retry: delay 5s để xe cản kịp thoát khỏi conflict path
                    _cmd_id_r = _CGC_r if _cmd_name == 'go_charge' else _CGW_r

                    async def _delayed_retry(_o=_oid, _c=_cmd_id_r, _n=_cmd_name):
                        await _asyncio.sleep(5.0)
                        print(f"[LINE_AGV] {_o}: bounce-retry dispatch (delayed 5s) → {_n}")
                        _atq_r.dispatch_or_queue(_o, _c, None, None, None, 'bounce_retry')

                    try:
                        _loop = _asyncio.get_running_loop()
                        _loop.create_task(_delayed_retry())
                        print(f"[LINE_AGV] {oid}: bounce-retry triggered by {moved_agv_id} moving → {_cmd_name} in 5s")
                    except RuntimeError:
                        _atq_r.dispatch_or_queue(oid, _cmd_id_r, None, None, None, 'bounce_retry')
            except Exception as _e:
                print(f"[LINE_AGV] {oid}: bounce-retry dispatch error: {_e}")

        # ── RESUME xe ĐÃ NHƯỜNG (yield) khi winner đã RỜI HẲN path gốc ──────────
        # Xe thua đỗ né siding (yield_cmd set), đứng chờ. Khi winner di chuyển và đường
        # CÒN LẠI của winner KHÔNG còn cắt path gốc xe thua → an toàn → re-dispatch lệnh
        # gốc (đúng loại + session). KHÔNG xoá yield khi đang lái (khác pending_retry).
        for oid, st in list(self.state_store._states.items()):
            # KHÔNG skip moved_agv_id: xe thua vừa TỚI siding (chính nó move) cũng phải
            # được kiểm tra resume ngay (phòng khi winner đã clear sẵn trước khi tới nơi).
            if st is None or not st.yield_cmd:
                continue
            if st.driving:
                continue   # đang lái tới siding → chưa tới nơi, chờ
            _w = st.yield_winner
            _wreg = traffic_coordinator._registered.get(_w) if _w else None
            if _wreg is not None:
                _wfut = {str(n) for n in _wreg['path'][_wreg.get('current_idx', 0):]}
                if _wfut & set(str(n) for n in (st.yield_path or [])):
                    continue   # winner CHƯA rời hẳn path gốc → tiếp tục chờ
            # winner đã rời hẳn (hoặc deregistered) → RESUME lệnh gốc
            _yc, _yd, _ys = st.yield_cmd, st.yield_dest, st.yield_session
            st.yield_cmd = st.yield_dest = st.yield_session = None
            st.yield_winner = st.yield_path = None
            try:
                from task_queue import (agv_task_queue as _atq_y, CMD_GO_TO as _CGT_y,
                                        CMD_GO_CHARGE as _CGC_y, CMD_GO_WAIT as _CGW_y)
                _cid = {'go_charge': _CGC_y, 'go_wait': _CGW_y}.get(_yc, _CGT_y)
                print(f"[LINE_AGV] {oid}: winner {_w} đã qua → RESUME '{_yc}' (sau khi né siding)")
                _atq_y.dispatch_or_queue(oid, _cid, dest_node=_yd, start_node=None,
                                         session_id=_ys, session_label='yield_resume')
            except Exception as _e:
                print(f"[LINE_AGV] {oid}: yield-resume dispatch error: {_e}")

    def _is_deadlocked_with(self, agv_id: str, other_id: str) -> bool:
        """Kẹt 2 chiều: other_id đang CHỜ (waiting_before_conflict) và node KẾ TIẾP
        của nó bị agv_id khoá → mỗi xe giữ node mà xe kia cần → deadlock."""
        o_route = self._routes.get(other_id)
        o_reg   = traffic_coordinator._registered.get(other_id)
        if not o_route or not o_reg:
            return False
        if not o_route.waiting_before_conflict:
            return False
        idx   = o_reg.get('current_idx', 0)
        opath = o_reg['path']
        o_next = opath[idx + 1] if idx + 1 < len(opath) else None
        if o_next is None:
            return False
        return traffic_coordinator._node_res.get(str(o_next)) == agv_id

    def _back_up_to_prev(self, agv_id: str, state: LineAGVState,
                         route: LineAGVRoute) -> bool:
        """Thoát deadlock bằng cách LÙI 1 NODE về prev_tag — luôn HỢP LỆ VẬT LÝ
        (xe đến node hiện tại TỪ prev_tag nên lùi lại được). KHÔNG đỗ sang node tùy
        ý (gây ra khỏi line). Sau khi lùi, re-queue đích gốc để đi lại khi thông.
        """
        # MỚI: xe không lùi được (đầu kéo/rơ-moóc) → bỏ qua, để caller rơi xuống
        # fallback khác (đứng chờ). Mọi AGV khác (mặc định can_reverse=True) không
        # bị ảnh hưởng — chạy tiếp y như cũ.
        if not agv_registry.can_reverse(agv_id):
            return False
        cur  = str(state.current_tag) if state.current_tag is not None else None
        prev = str(state.prev_tag)    if state.prev_tag    else None
        dest_final = route.full_path[-1] if route.full_path else None
        if not cur or not prev or cur == prev or not dest_final:
            print(f"[TRAFFIC] {agv_id}: không thể lùi về prev (cur={cur} prev={prev}) → đứng chờ")
            return False
        # prev phải là láng giềng thật của cur (an toàn)
        try:
            from mqtt_client import map_manager as _mm_b
            _g = _mm_b.line_graph if _mm_b.line_graph else _mm_b.graph
            if _g is not None and cur in _g and prev not in set(map(str, _g.neighbors(cur))):
                print(f"[TRAFFIC] {agv_id}: prev {prev} không kề cur {cur} → đứng chờ")
                return False
        except Exception:
            pass
        # KHÔNG lùi vào node đang bị XE KHÁC giữ chỗ / ĐỨNG tại đó. Gốc lỗi (đúng log):
        # AGV02 ở node 15 head-on tại node 8 (do AGV01 giữ) → "LÙI VỀ prev" mà prev CHÍNH
        # là node 8 (nó vừa đi 8→15) → lùi THẲNG vào node đối thủ đang giữ = ĐÂM + không
        # thoát deadlock (cả 2 cùng cần node đó). Khi prev bị giữ → KHÔNG lùi, đứng chờ.
        _owner_prev = traffic_coordinator.node_reserved_by_other(agv_id, prev)
        if _owner_prev:
            print(f"[TRAFFIC] {agv_id}: KHÔNG lùi về {prev} (đang bị {_owner_prev} giữ chỗ) → đứng chờ")
            return False
        for _oid_p, _stp in self.state_store._states.items():
            if (_oid_p != agv_id and _stp is not None and _stp.current_tag is not None
                    and str(_stp.current_tag) == prev):
                print(f"[TRAFFIC] {agv_id}: KHÔNG lùi về {prev} ({_oid_p} đang đứng đó) → đứng chờ")
                return False
        try:
            from mqtt_client import map_manager as _mm2
            from line_agv_plan_builder import build_line_plan, build_edge_speeds, build_edge_lidar
            _pts = getattr(_mm2, "points", {}) or {}
            _na  = getattr(_mm2, "node_actions", {}) or {}
            _rds = getattr(_mm2, "roads", []) or []
            _seg = [cur, prev]
            _plan = build_line_plan(
                _seg, _pts, task_type="transit", node_actions=_na, direction="bwd",
                edge_speeds=build_edge_speeds(_rds), edge_lidar=build_edge_lidar(_rds),
                agv_id=agv_id, initial_prev_tag=None,
            )
            self.set_route(agv_id, _seg, "transit", direction="bwd")
            _rt = self._routes[agv_id]
            _rt.window_end  = len(_seg) - 1
            _rt.is_complete = True
            if self.send_window_fn:
                self.send_window_fn(agv_id, _plan)
            else:
                from mqtt_client import send_order as _so
                _so(agv_id, _plan)
            from task_queue import agv_task_queue as _atq, CMD_GO_TO as _CGT
            _atq.insert_next(agv_id, _CGT, dest_node=str(dest_final))
            print(f"[TRAFFIC] {agv_id}: LÙI VỀ {prev} (thoát deadlock), queue lại đích {dest_final}")
            return True
        except Exception as _e:
            print(f"[TRAFFIC] {agv_id}: _back_up_to_prev lỗi: {_e}")
            return False

    def _blocks_corridor_of(self, agv_id: str, other_id: str) -> bool:
        """Vị trí hiện tại của agv_id có nằm trên path TƯƠNG LAI của other_id không
        (tôi đang đứng chặn hành lang xe kia — đứng chờ mãi sẽ thành deadlock)."""
        st = self.state_store.get(agv_id)
        if not st or st.current_tag is None:
            return False
        _reg = traffic_coordinator._registered.get(other_id)
        if not _reg:
            return False
        _op = [str(n) for n in _reg.get('path', [])]
        _oc = _reg.get('current_idx', 0)
        return str(st.current_tag) in _op[_oc:]

    def _back_up_to_reroute_node(self, agv_id: str, state: LineAGVState,
                                 route: LineAGVRoute, current_idx: int,
                                 other_agv: str) -> bool:
        """HEAD-ON hết đường tiến + không siding: LÙI dọc đoạn ĐÃ ĐI (vật lý hợp lệ
        — xe vừa đi qua nên chắc chắn lùi lại được) về node gần nhất có NHÁNH RẼ
        thay thế tới đích (né hành lang xe thắng), rồi queue lại đích để planner
        reroute từ đó. Không node nào có nhánh rẽ → lùi về node NGOÀI hành lang xe
        thắng để đứng chờ (nhả đường). Trả True nếu đã gửi plan lùi."""
        # MỚI: xe không lùi được (đầu kéo/rơ-moóc) → bỏ qua, để caller rơi xuống
        # fallback khác (đứng chờ). Không ảnh hưởng AGV khác (mặc định True).
        if not agv_registry.can_reverse(agv_id):
            return False
        if current_idx <= 0 or not route.full_path:
            return False
        try:
            import networkx as nx
            from mqtt_client import map_manager as _mm
            g_base = _mm.line_graph if _mm.line_graph else _mm.graph
            if g_base is None:
                return False
            dest = str(route.full_path[-1])
            # Hành lang TƯƠNG LAI của xe thắng (node + edge) — đường thay thế phải né
            _reg = traffic_coordinator._registered.get(other_agv, {})
            _op  = [str(n) for n in _reg.get('path', [])]
            _oc  = _reg.get('current_idx', 0)
            _corr_nodes = set(_op[_oc:])
            _corr_edges = {(_op[j], _op[j + 1]) for j in range(_oc, len(_op) - 1)}

            def _alt_path_from(_cand: str):
                g = g_base.copy()
                for _a, _b in _corr_edges:
                    if g.has_edge(_a, _b):
                        g.remove_edge(_a, _b)
                    if g.has_edge(_b, _a):
                        g.remove_edge(_b, _a)
                for _n in _corr_nodes:
                    if _n in g and _n != _cand and _n != dest:
                        g.remove_node(_n)
                try:
                    return nx.shortest_path(g, source=_cand, target=dest, weight='weight')
                except Exception:
                    return None

            # Giới hạn lùi: KHÔNG lùi xuyên qua node có xe khác đứng / bị xe khác
            # giữ (xe bám đuôi phía sau) — chỉ được lùi tới trước node đó.
            _occupied = {str(st.current_tag)
                         for oid, st in self.state_store._states.items()
                         if oid != agv_id and st is not None
                         and st.current_tag is not None}
            _min_bi = 0
            for _bi in range(current_idx - 1, -1, -1):
                _n_bi = str(route.full_path[_bi])
                if (_n_bi in _occupied
                        or traffic_coordinator.node_reserved_by_other(agv_id, _n_bi)):
                    _min_bi = _bi + 1
                    break

            # Pass 1: node lùi gần nhất CÓ đường thay thế tới đích (nhánh rẽ thật)
            back_idx = None
            reason   = ""
            for _bi in range(current_idx - 1, _min_bi - 1, -1):
                if _alt_path_from(str(route.full_path[_bi])):
                    back_idx = _bi
                    reason   = "có nhánh rẽ thay thế tới đích"
                    break
            # Pass 2: không nhánh rẽ → node lùi gần nhất NGOÀI hành lang xe thắng
            if back_idx is None:
                for _bi in range(current_idx - 1, _min_bi - 1, -1):
                    if str(route.full_path[_bi]) not in _corr_nodes:
                        back_idx = _bi
                        reason   = "ngoài hành lang xe thắng (đứng chờ nhường)"
                        break
            if back_idx is None:
                return False

            _seg      = [str(n) for n in route.full_path[back_idx:current_idx + 1]][::-1]
            _back_dir = 'fwd' if route.direction == 'bwd' else 'bwd'
            from line_agv_plan_builder import build_line_plan, build_edge_speeds, build_edge_lidar
            _pts = getattr(_mm, "points", {}) or {}
            _na  = getattr(_mm, "node_actions", {}) or {}
            _rds = getattr(_mm, "roads", []) or []
            _plan = build_line_plan(
                _seg, _pts, task_type="transit", node_actions=_na, direction=_back_dir,
                edge_speeds=build_edge_speeds(_rds), edge_lidar=build_edge_lidar(_rds),
                agv_id=agv_id, initial_prev_tag=None,
            )
            _task_type = route.task_type
            self.set_route(agv_id, _seg, "transit", direction=_back_dir)
            _rt = self._routes[agv_id]
            _rt.window_end  = len(_seg) - 1   # hành lang sau lưng trống (vừa đi qua) → lùi 1 mạch
            _rt.is_complete = True
            _rt.waiting_before_conflict = None
            if self.send_window_fn:
                self.send_window_fn(agv_id, _plan)
            else:
                from mqtt_client import send_order as _so
                _so(agv_id, _plan)
            from task_queue import agv_task_queue as _atq
            from task_queue import CMD_GO_TO as _CGT, CMD_GO_CHARGE as _CGC
            _cmd = _CGC if _task_type == "return_charge" else _CGT
            _atq.insert_next(agv_id, _cmd, dest_node=dest)
            print(f"[TRAFFIC] {agv_id}: HEAD-ON hết đường tiến — LÙI {current_idx - back_idx} "
                  f"node về {_seg[-1]} ({reason}), nhường {other_agv}, queue lại đích {dest}")
            return True
        except Exception as _e:
            print(f"[TRAFFIC] {agv_id}: _back_up_to_reroute_node lỗi: {_e}")
            return False

    def _yield_to_siding(self, agv_id: str, route: LineAGVRoute,
                         conflict_at: int, other_agv: str) -> bool:
        """Xe THUA CHỦ ĐỘNG đỗ sang nhánh phụ (siding) cho xe THẮNG đi qua, rồi đi
        tiếp lệnh cũ. Định tuyến tới siding QUA HÀNG ĐỢI (go_to → planner đã validated
        — đúng rẽ/hướng/window-cap), KHÔNG build plan thủ công (tránh off-track).
        Trả True nếu đã đỗ né; False nếu không có siding → để gọi wait-based."""
        # MỚI: xe không lùi được (đầu kéo/rơ-moóc) → bỏ qua đỗ né siding (việc
        # rời siding sau này có thể cần lùi), để caller rơi xuống wait-based.
        # Không ảnh hưởng AGV khác (mặc định can_reverse=True).
        if not agv_registry.can_reverse(agv_id):
            return False
        try:
            parking = traffic_coordinator.find_parking_node(
                agv_id, route.full_path, conflict_at, other_agv)
            if not parking:
                return False
            _park = str(parking[0])
            _st = self.state_store.get(agv_id)
            _cur = str(_st.current_tag) if (_st and _st.current_tag is not None) else None
            if not _park or _park == _cur:
                return False
            from task_queue import agv_task_queue as _atq, CMD_GO_TO as _CGT
            running = _atq._running.get(agv_id)
            if not running:
                return False
            # LƯU lệnh GỐC vào trạng thái YIELD (riêng pending_retry — không bị xoá khi xe
            # đang LÁI tới siding). Resume qua _check_waiting_agvs CHỈ khi winner đã rời hẳn
            # path gốc (tất định, không né↔đụng vòng lặp). Giữ đúng loại lệnh + session.
            if _st:
                _st.yield_cmd     = running.command   # go_charge|go_wait|go_to
                _st.yield_dest    = running.dest_node
                _st.yield_session = running.session_id
                _st.yield_winner  = other_agv
                _st.yield_path    = list(route.full_path)
            # Đi tới siding NGAY: nhả route/đăng ký, hoàn tất lệnh gốc (free, KHÔNG auto
            # chạy lệnh kế), rồi dispatch go_to(siding) qua planner (validated).
            self._routes.pop(agv_id, None)
            traffic_coordinator.deregister(agv_id)
            _atq.on_agv_completed(agv_id, notes='yield_siding', auto_dispatch=False)
            # GIỮ ĐÚNG HƯỚNG ARRIVAL cho nước né siding: xe đang đứng tại node conflict
            # với heading theo route.direction (vd arrived bwd từ transit 17→5). Nhưng
            # last_transit_direction ĐÃ bị clear bởi dispatch trước (route gốc bị cắt
            # window [0→0] — xe KHÔNG di chuyển) → siding mặc định 'fwd' → plan ra
            # DIR_FWD + turn sai hướng → xe đi THẲNG ra ngoài line thay vì rẽ vào siding.
            # Khôi phục để dispatch siding tính turn/dir đúng theo chiều xe đang quay.
            if _st and route.direction == 'bwd':
                _st.last_transit_direction = 'bwd'
            _atq.dispatch_or_queue(agv_id, _CGT, dest_node=_park, start_node=None,
                                   session_id=running.session_id, session_label='yield_siding')
            print(f"[TRAFFIC] {agv_id}: CHỦ ĐỘNG đỗ né sang siding {_park} cho "
                  f"{other_agv} (winner) đi qua; giữ '{running.command}' chờ winner rời hẳn")
            return True
        except Exception as _e:
            print(f"[TRAFFIC] {agv_id}: _yield_to_siding lỗi: {_e}")
            return False

    def _check_rolling_plan(self, agv_id: str, state: LineAGVState) -> None:
        """
        Chạy mỗi khi AGV di chuyển đến tag mới.

        Hai nhiệm vụ độc lập:
          A) PROACTIVE TRAFFIC CHECK (TRAFFIC_LOOKAHEAD=5 nodes):
             Luôn nhìn trước 5 node, phát hiện conflict sớm và xử lý ngay.
             Độc lập với kích thước rolling window — chạy mọi lúc.
          B) ROLLING WINDOW REFRESH:
             Gửi plan window tiếp theo khi cần (khi sắp hết window).
             Chỉ gửi nếu không có conflict.

        Phân tách rõ 2 nhiệm vụ để:
          - Không bỏ lỡ conflict chỉ vì window chưa cần refresh
          - Không gửi window mới khi đang có conflict phía trước
        """
        route = self._routes.get(agv_id)
        if route is None or route.is_complete:
            return
        if state.current_tag is None:
            return

        tag_str = str(state.current_tag)
        try:
            current_idx = route.full_path.index(tag_str)
        except ValueError:
            # Vị trí THỰC của xe KHÔNG nằm trên route đăng ký → rolling plan bế tắc
            # (không tính được current_idx). Gốc: PLAN-RACE — firmware chạy plan CŨ
            # (nhánh khác) trong khi server đã reroute sang nhánh kia → xe tới node ∉
            # route server (vd firmware đi 16→8 trong khi route server là 16→7→6→17…).
            # Trước đây return im lặng → xe ĐỨNG MÃI tại node lạ, không bao giờ được lệnh
            # tiếp → winner xe kia chờ nó dời = DEADLOCK (đúng log: AGV01 kẹt ở 8, AGV02
            # chờ tại 5). FIX: nếu xe ĐANG ĐỨNG (không lái, không lifecycle) → off_route
            # re-dispatch để có route MỚI từ vị trí thực → xe đi tiếp, giải kẹt.
            if not state.driving and not getattr(state, 'task_lifecycle', None):
                print(f"[LINE_AGV] {agv_id}: tại {tag_str} KHÔNG thuộc route "
                      f"(đích {route.full_path[-1]}) → off_route re-dispatch (thoát kẹt plan-race)")
                self._handle_event(agv_id, "off_route", {}, state)
            return

        if current_idx < route.window_start:
            return

        # ══════════════════════════════════════════════════════════════════════
        # A) PROACTIVE TRAFFIC CHECK — luôn nhìn trước TRAFFIC_LOOKAHEAD nodes
        # ══════════════════════════════════════════════════════════════════════
        traffic_end = min(current_idx + TRAFFIC_LOOKAHEAD, len(route.full_path) - 1)

        # A1. Đang chờ vì conflict trước: kiểm tra đã thông / nhích tiếp được chưa.
        # HEAD-ON còn tồn tại KHÔNG return sớm nữa — phải rơi xuống A2 để xe thua
        # tiếp tục thử reroute/siding/LÙI (không "dừng chờ mãi" → deadlock).
        if route.waiting_before_conflict:
            still_raw = self._find_upcoming_conflict(
                agv_id, route, current_idx, traffic_end,
            )
            if still_raw is None:
                route.waiting_before_conflict = None
                print(f"[LINE_AGV] {agv_id}: conflict cleared → resuming")
            else:
                _fol_w  = (still_raw < 0)
                _cat_w  = (-still_raw - 1) if _fol_w else still_raw
                _safe_w = max(current_idx,
                              (_cat_w - 1) if _fol_w else (_cat_w - HEADON_STANDOFF))
                if _fol_w:
                    if _safe_w > current_idx:
                        # Xe trước đã tiến xa hơn → được nhích theo (A2 gửi window mới)
                        route.waiting_before_conflict = None
                    else:
                        return  # following vẫn blocked sát trước → tiếp tục chờ
                # head-on: rơi xuống A2 — xe thua thử né tiếp, xe thắng chờ (idempotent)

        # A2. Check proactive trong TRAFFIC_LOOKAHEAD nodes phía trước
        conflict_raw = self._find_upcoming_conflict(
            agv_id, route, current_idx, traffic_end
        )

        # Phân biệt following (âm) vs head-on (dương)
        # following: chỉ halt+chờ  |  head-on: reroute/park/halt
        _is_following = (conflict_raw is not None and conflict_raw < 0)
        conflict_at   = (-conflict_raw - 1) if _is_following else conflict_raw

        # `>= current_idx` (KHÔNG phải `>`): xung đột có thể nằm ngay tại CẠNH KẾ
        # (conflict_at == current_idx) — vd xe THUA đang đứng tại node 5, route
        # `5→18→…` đâm thẳng vào hành lang winner ở cạnh đầu tiên 5→18. Nếu chỉ xét
        # `> current_idx` thì bỏ qua HẲN xử lý head-on cho cạnh-kế → xe thua đứng im
        # giữa hành lang winner → 2 xe chờ nhau = DEADLOCK. Phải vào nhánh xử lý để xe
        # thua NÉ (siding/reroute/lùi) ngay cả khi đầu-đâm-đầu sát ngay cạnh kế. (Xe
        # THẮNG/following ở cạnh-kế chỉ rơi xuống WAIT-BASED — đứng chờ tại chỗ, an toàn.)
        if conflict_at is not None and conflict_at >= current_idx:
            if _is_following:
                # ── Phát hiện DEADLOCK do khoá node lẫn nhau ────────────────────
                # Node chặn ta bị xe O khoá, mà O cũng đang chờ một node do TA khoá
                # → kẹt 2 chiều (obstacle-timeout KHÔNG cứu vì không có vật cản LIDAR).
                # Bên thua arbiter lùi/đỗ sang side node để giải phóng.
                _block_node  = route.full_path[min(conflict_at + 1, len(route.full_path) - 1)]
                _block_owner = traffic_coordinator.node_reserved_by_other(agv_id, _block_node)
                if _block_owner and self._is_deadlocked_with(agv_id, _block_owner):
                    if traffic_coordinator._arbitrate(agv_id, _block_owner, _block_node) != agv_id:
                        print(f"[TRAFFIC] {agv_id}: DEADLOCK với {_block_owner} "
                              f"→ tôi nhường, LÙI VỀ prev_tag")
                        if self._back_up_to_prev(agv_id, state, route):
                            return
                    else:
                        print(f"[TRAFFIC] {agv_id}: DEADLOCK với {_block_owner} "
                              f"→ tôi ưu tiên, chờ {_block_owner} né")
                # FOLLOWING: xe cùng chiều đứng trước → chỉ dừng lại chờ, không reroute.
                # Dừng cách xe trước ≥2 node: safe_end = conflict_at - 1
                # (xe trước tại path[conflict_at+1], ta dừng tại path[conflict_at-1] = 2 node gap)
                safe_end = max(current_idx, conflict_at - 1)
                print(f"[TRAFFIC] {agv_id}: following — xe phía trước dừng tại "
                      f"{route.full_path[min(conflict_at+1, len(route.full_path)-1)]}, "
                      f"halt tại {route.full_path[safe_end]} (2-node gap)")
                if safe_end > current_idx:
                    route.waiting_before_conflict = route.full_path[safe_end]
                    self._send_window(agv_id, route, current_idx, safe_end, False)
                return

            print(f"[TRAFFIC] {agv_id}: head-on conflict ahead "
                  f"at node {route.full_path[conflict_at]} (idx={conflict_at})")

            # Xác định xe kia đang gây conflict
            _conf_fn = route.full_path[conflict_at]
            _conf_tn = route.full_path[conflict_at + 1] \
                       if conflict_at + 1 < len(route.full_path) else None
            _other_agv = self._identify_conflicting_agv(agv_id, _conf_fn, _conf_tn)

            # ── QUYẾT ĐỊNH TẤT ĐỊNH: đúng 1 xe nhường ────────────────────────
            # Trọng tài (priority→khoảng cách→id, đối xứng) chọn winner. CHỈ xe THUA
            # hành động; xe THẮNG đi tiếp/chờ tại chỗ. KHÔNG reroute giữa-route nữa
            # (nguồn dao động): đa dạng tuyến đã làm ở lúc lập-kế-hoạch. Đa dạng tuyến
            # reactive khiến CẢ HAI cùng nhảy nhánh → vẫn đâm.
            # NODE TRỌNG TÀI phải GIỐNG NHAU cho cả 2 xe head-on → arbiter ĐỐI XỨNG (cùng
            # winner). 2 xe đối đầu trên CÙNG cạnh {fn,tn} nhưng MỖI xe vào từ đầu ĐỐI DIỆN
            # → `_conf_fn` của chúng KHÁC nhau (vd AGV01 đi 8→5 thấy fn=8; AGV02 đi 5→8 thấy
            # fn=5) → nếu arbiter theo `_conf_fn` thì khoảng-cách-tới-node ra winner KHÁC
            # nhau → CẢ HAI tưởng mình thắng → cùng đứng chờ = DEADLOCK (đúng log). Dùng node
            # CANONICAL (id nhỏ hơn của cạnh head-on) → cả 2 tính ra cùng node → cùng winner.
            _arb_node = _conf_fn
            if _conf_tn is not None:
                try:
                    _arb_node = _conf_fn if int(_conf_fn) <= int(_conf_tn) else _conf_tn
                except (TypeError, ValueError):
                    _arb_node = min(str(_conf_fn), str(_conf_tn))
            _am_winner = bool(_other_agv) and (
                traffic_coordinator._arbitrate(agv_id, _other_agv, _arb_node) == agv_id)

            # CHỈ né (reroute/siding/lùi) khi xe kia THỰC SỰ NGƯỢC CHIỀU (oncoming).
            # Cùng chiều (following — vd 2 xe cùng đi lên, xe sau gặp xe trước tại node
            # chung/đích) → KHÔNG né, KHÔNG lùi về trạm; chỉ DỪNG CHỜ xe trước đi qua.
            _oncoming = bool(_other_agv) and self._is_oncoming(agv_id, route, _other_agv)

            # ── NÉ TỐI THIỂU: xe THUA chỉ cần NHÍCH tới node kế trên CHÍNH route mình
            # (điểm dừng an toàn trước conflict = safe_end) mà node đó ĐÃ NẰM NGOÀI hành
            # lang tương lai của winner → chỉ DỪNG CHỜ tại đó cho winner qua rồi đi tiếp.
            # KHÔNG đỗ-né-siding (dead-end, phải lùi lại) / reroute / lùi. Đây đúng ý user:
            # "né lên node 8, chờ AGV02 qua rồi đi tiếp" — KHÔNG vòng lên 16 vô ích.
            # Chỉ khi route mình VẪN bám hành lang winner tới sát conflict (safe_end vẫn
            # nằm trong đường winner) hoặc không nhích được (safe_end==current) mới cần
            # siding/lùi.
            _win_future_wait: set[str] = set()
            if _other_agv:
                _wreg = traffic_coordinator._registered.get(_other_agv, {})
                if _wreg:
                    _wc = _wreg.get('current_idx', 0)
                    _win_future_wait.update(str(n) for n in _wreg.get('path', [])[_wc:])
                _wint = traffic_coordinator._intent_route.get(_other_agv)
                if _wint:
                    _win_future_wait.update(str(n) for n in _wint)
            _safe_end_pre = max(current_idx, conflict_at - HEADON_STANDOFF)
            _can_wait_on_route = (
                _safe_end_pre > current_idx
                and str(route.full_path[_safe_end_pre]) not in _win_future_wait
            )

            # ── CHỈ XE THUA hành động (tất định → không cả-hai-cùng-né = dao động) ─
            if _other_agv and not _am_winner and _oncoming and not _can_wait_on_route:
                # 1) RE-ROUTE qua nhánh KHÁC né winner (đi vòng, vẫn tiến tới đích —
                #    không phải dừng). CHỈ xe thua reroute → KHÔNG dao động (trước đây
                #    cả 2 cùng reroute vào 1 nhánh mới đâm). traffic-aware giữ prefix nên
                #    không off-track; đường đơn thật → trả False → xuống siding/chờ.
                if self._try_line_reroute(agv_id, state, route, current_idx):
                    print(f"[LINE_AGV] {agv_id}: HEAD-ON (thua) với {_other_agv} → ĐI VÒNG "
                          f"né hẳn qua nhánh khác")
                    return
                # 2) Không có nhánh vòng → ĐỖ NÉ sang siding off-path + giữ lệnh gốc chờ
                #    winner clear (resume qua _check_waiting_agvs). "Di chuyển tới node
                #    ngoài đường đi của nhau để chờ".
                #    CHỈ đỗ-né-siding khi mình ĐANG CHẮN hành lang winner (vị trí hiện
                #    tại nằm trên đường tương lai của nó). Nếu mình ĐÃ THOÁNG (vd vừa
                #    vacate sang node 8 không nằm trên đường winner) → KHÔNG đi siding
                #    vô ích (lãng phí 8→16 rồi 16→8); chỉ DỪNG CHỜ tại chỗ cho winner
                #    qua rồi đi tiếp. Tránh "né thừa" như user thấy (đứng 8 là đủ, lên 16).
                if (self._blocks_corridor_of(agv_id, _other_agv)
                        and self._yield_to_siding(agv_id, route, conflict_at, _other_agv)):
                    return
                # 3) Hết đường tiến + không siding: nếu TÔI đang CHẶN hành lang xe
                #    thắng (vị trí nằm trên path tương lai của nó) hoặc deadlock
                #    khoá-node 2 chiều → LÙI dọc đường ĐÃ ĐI về node có NHÁNH RẼ
                #    thay thế rồi reroute từ đó. KHÔNG đứng chờ mãi → deadlock.
                _now_bu = time.monotonic()
                if (_now_bu - self._backup_ts.get(agv_id, 0.0) >= BACKUP_COOLDOWN
                        and (self._blocks_corridor_of(agv_id, _other_agv)
                             or self._is_deadlocked_with(agv_id, _other_agv))):
                    if self._back_up_to_reroute_node(agv_id, state, route,
                                                     current_idx, _other_agv):
                        self._backup_ts[agv_id] = _now_bu
                        return
                    # Không tìm được node nhánh rẽ phía sau → lùi tối thiểu 1 node
                    # (prev_tag) để nhả node tranh chấp.
                    if self._back_up_to_prev(agv_id, state, route):
                        self._backup_ts[agv_id] = _now_bu
                        return

            # ── WAIT-BASED: xe THẮNG, hoặc xe THUA chưa có chỗ né → DỪNG CHỜ tại
            # điểm an toàn CÁCH conflict HEADON_STANDOFF node (không đứng sát node
            # tranh chấp). Reservation/arbiter đã quyết ai đi trước; winner qua →
            # conflict clear → đi tiếp (A1 + _check_waiting_agvs).
            safe_end = max(current_idx, conflict_at - HEADON_STANDOFF)
            route.waiting_before_conflict = route.full_path[safe_end]
            if safe_end > current_idx:
                self._send_window(agv_id, route, current_idx, safe_end, False)
            if _am_winner:
                _why = 'winner, chờ thua né'
            elif not _oncoming:
                _why = 'cùng chiều (following) → chỉ chờ, không né'
            elif _can_wait_on_route:
                _why = 'thua → nhích tới node thoáng trên route, chờ winner qua (không siding)'
            else:
                _why = 'thua, chưa có chỗ né'
            print(f"[LINE_AGV] {agv_id}: HEAD-ON → DỪNG CHỜ tại {route.full_path[safe_end]} "
                  f"(cách conflict {conflict_at - safe_end} node; {_why})")
            return

        # ══════════════════════════════════════════════════════════════════════
        # B) ROLLING WINDOW REFRESH — chỉ chạy khi không có conflict
        # ══════════════════════════════════════════════════════════════════════
        remaining = route.window_end - current_idx
        if remaining > LOOKAHEAD // 2:
            return  # Window còn đủ, chưa cần gửi tiếp

        new_end  = min(current_idx + LOOKAHEAD, len(route.full_path) - 1)
        is_final = (new_end == len(route.full_path) - 1)
        self._send_window(agv_id, route, current_idx, new_end, is_final)

    # ── Traffic helper methods ─────────────────────────────────────────────────

    def _identify_conflicting_agv(
        self, agv_id: str, conf_fn: Optional[str], conf_tn: Optional[str]
    ) -> Optional[str]:
        """Tìm AGV nào đang gây conflict tại edge conf_fn→conf_tn."""
        if conf_tn:
            # Kiểm tra edge reservation (cả 2 chiều)
            for eid in (f"{conf_tn}_to_{conf_fn}", f"{conf_fn}_to_{conf_tn}"):
                owner = _line_blocked_edges.get(eid)
                if owner and owner != agv_id:
                    return owner
            # Kiểm tra future edges trong traffic registry
            for oid, r in traffic_coordinator._registered.items():
                if oid == agv_id:
                    continue
                if (conf_tn, conf_fn) in traffic_coordinator._future_edges(r):
                    return oid
        # Kiểm tra AGV đang ĐỨNG tại conf_tn (node KẾ — nơi ta sắp vào) HOẶC conf_fn.
        # BẮT conf_tn trước: gốc deadlock là xe đậu CHẮN ở node kế (vd xe đang picking
        # tại pickup/đích nằm trên đường ta) — trước đây chỉ check conf_fn → trả None →
        # KHÔNG nhận ra xe chắn → cả 2 cùng đứng chờ. Hướng (oncoming/following) do
        # _is_oncoming quyết sau, nên bắt thêm conf_tn KHÔNG phá case following.
        for _cn in (conf_tn, conf_fn):
            if not _cn:
                continue
            for oid, st in self.state_store._states.items():
                if oid == agv_id:
                    continue
                if st and st.current_tag is not None \
                        and str(st.current_tag) == str(_cn) and not st.driving:
                    return oid
        return None

    def _is_oncoming(self, agv_id: str, route: LineAGVRoute,
                     other_id: str) -> bool:
        """Xe other có THỰC SỰ ĐI NGƯỢC CHIỀU ta (oncoming) trên ≥1 cạnh vật lý CHUNG
        không? = xe kia đi a→b mà ta đi b→a trên cùng cạnh (head-on thật). Dùng để CHỈ
        né (siding/lùi) xe đi chiều ngược lại vướng đường; xe CÙNG CHIỀU (following — vd
        xe sau đi lên gặp xe trước cũng đi lên) → KHÔNG né, chỉ DỪNG CHỜ."""
        st = self.state_store.get(agv_id)
        cur = str(st.current_tag) if (st and st.current_tag is not None) else None
        try:
            ci = route.full_path.index(cur) if (cur and cur in route.full_path) else 0
        except ValueError:
            ci = 0
        my_edges = {(str(route.full_path[i]), str(route.full_path[i + 1]))
                    for i in range(ci, len(route.full_path) - 1)}
        if not my_edges:
            return False
        # Tuyến TƯƠNG LAI của xe kia: registered path + intent (cả khi đang chờ).
        _checks = []
        _oreg = traffic_coordinator._registered.get(other_id, {})
        _op = [str(n) for n in _oreg.get('path', [])]
        if _op:
            _checks.append((_op, _oreg.get('current_idx', 0)))
        _intent = traffic_coordinator._intent_route.get(other_id)
        if _intent and len(_intent) >= 2:
            _checks.append(([str(n) for n in _intent], 0))
        for _op2, _oc2 in _checks:
            for _j in range(_oc2, len(_op2) - 1):
                if (_op2[_j + 1], _op2[_j]) in my_edges:   # nó a→b, ta b→a = head-on
                    return True
        # FALLBACK — xe kia ĐẬU cuối route / đang picking (KHÔNG còn future-edge để so,
        # vd vừa lên tới pickup 19, sắp đổi task): xét hướng nó VỪA ĐI TỚI (prev→cur).
        # Nó đi prev→cur; nếu TA đi cur→prev trên cùng cạnh (cur,prev)∈my_edges → nó đến
        # từ phía TA định đi = NGƯỢC CHIỀU (oncoming). Following (nó đến từ phía sau ta)
        # → (cur,prev)∉my_edges → False. → loser nhận ra phải né, không kẹt cứng.
        ost = self.state_store.get(other_id)
        if ost and ost.current_tag is not None and ost.prev_tag is not None:
            if (str(ost.current_tag), str(ost.prev_tag)) in my_edges:
                return True
        return False

    def _dispatch_to_parking(
        self, agv_id: str, state: LineAGVState, route: LineAGVRoute,
        current_idx: int, park_info: tuple[str, str],
    ) -> bool:
        """
        Gửi transit plan đến parking node (nhánh phụ).
        Returns True nếu thành công.
        """
        _park_node, _entry_node = park_info
        _cur_tag = str(state.current_tag or "")
        if _park_node == _cur_tag:
            return False  # Đã ở parking node rồi

        _dest_final = route.full_path[-1]
        try:
            _entry_idx = route.full_path.index(_entry_node) \
                         if _entry_node in route.full_path else current_idx
            _transit_path = route.full_path[current_idx:_entry_idx + 1] + [_park_node]
            if len(_transit_path) < 2:
                return False

            from mqtt_client import map_manager as _mm
            from line_agv_plan_builder import build_line_plan, build_edge_speeds, build_edge_lidar
            _pts = getattr(_mm, "points", {}) or {}
            _na  = getattr(_mm, "node_actions", {}) or {}
            _rds = getattr(_mm, "roads", []) or []
            _park_dir = _charger_exit_direction(
                _transit_path[0] if _transit_path else '', route.direction)
            _plan = build_line_plan(
                _transit_path, _pts, task_type="transit",
                node_actions=_na, direction=_park_dir,
                edge_speeds=build_edge_speeds(_rds),
                edge_lidar=build_edge_lidar(_rds),
                agv_id=agv_id, initial_prev_tag=None,
            )
            self.set_route(agv_id, _transit_path, "transit", direction=_park_dir)
            _rt = self._routes[agv_id]
            _rt.window_end  = len(_transit_path) - 1
            _rt.is_complete = True
            if self.send_window_fn:
                self.send_window_fn(agv_id, _plan)
            else:
                from mqtt_client import send_order as _so
                _so(agv_id, _plan)
            from task_queue import agv_task_queue as _atq, CMD_GO_TO as _CGT
            _atq.insert_next(agv_id, _CGT, dest_node=str(_dest_final))
            print(f"[TRAFFIC] {agv_id}: → PARK tại {_park_node} "
                  f"(qua {_entry_node}), queue tiếp→{_dest_final}")
            return True
        except Exception as _e:
            print(f"[TRAFFIC] {agv_id}: parking dispatch error: {_e}")
            return False

    def _reverse_to_side_node(
        self, agv_id: str, state: LineAGVState,
        route: LineAGVRoute, current_idx: int,
    ) -> bool:
        """
        Tìm node đỗ tạm linh hoạt (BFS) không nằm trên vùng tranh chấp.
        AGV sẽ đi đến đó bằng hướng phù hợp (tiến hoặc lùi, không cố định).
        Sau khi đỗ, tự re-dispatch đến đích gốc.
        """
        cur_node   = str(state.current_tag or "")
        dest_final = route.full_path[-1]

        # Dùng BFS để tìm node đỗ tốt nhất (ưu tiên WAITING, side branch)
        # Loại trừ cả accumulated_blocked (các node đã thử và thất bại trước đó)
        _acc_blocked = (state.accumulated_blocked or set()).copy()
        side_node = traffic_coordinator.find_flexible_parking(
            agv_id, cur_node, route.full_path,
            extra_blocked=_acc_blocked
        )
        # Nếu node được chọn vẫn nằm trong accumulated_blocked → đã bị obstacle
        # trước đó → không thử lại, coi như không có parking node.
        if side_node and str(side_node) in _acc_blocked:
            side_node = None
        if not side_node:
            # Không tìm được parking node → kiểm tra xem có phải dead-end không
            # Nếu dead-end (chỉ 1 neighbor, nằm trên conflict path) → đứng yên chờ
            try:
                from mqtt_client import map_manager as _mm_de
                _g_de = _mm_de.line_graph if _mm_de.line_graph else _mm_de.graph
                if _g_de and cur_node in _g_de:
                    _deg = _g_de.degree(str(cur_node))
                    if _deg <= 1:
                        print(f"[TRAFFIC] {agv_id}: dead-end tại {cur_node} "
                              f"— đứng yên chờ conflict clear")
                        # Đặt flag chờ, _check_waiting_agvs sẽ retry khi xe kia đi
                        _r = self._routes.get(agv_id)
                        if _r:
                            _r.waiting_before_conflict = str(dest_final)
                        return True   # Coi như đã xử lý (đứng yên)
            except Exception:
                pass
            return False

        try:
            from mqtt_client import map_manager as _mm2
            from line_agv_plan_builder import build_line_plan, build_edge_speeds, build_edge_lidar
            _pts = getattr(_mm2, "points", {}) or {}
            _na  = getattr(_mm2, "node_actions", {}) or {}
            _rds = getattr(_mm2, "roads", []) or []
            # Tính đường thực tế từ cur_node đến side_node (tránh invalid 2-node plan
            # khi 2 node không kết nối trực tiếp, gây AGV đi sai hướng)
            _g_rts = _mm2.line_graph if _mm2.line_graph else _mm2.graph
            try:
                import networkx as _nx_rts
                _transit = list(_nx_rts.shortest_path(
                    _g_rts, source=str(cur_node), target=str(side_node), weight='weight'
                ))
            except Exception:
                _transit = [str(cur_node), str(side_node)]  # fallback
            # Dùng hướng của route hiện tại để giữ nguyên chiều vật lý của xe
            _park_dir = route.direction
            _park_dir = _charger_exit_direction(_transit[0] if _transit else cur_node, _park_dir)
            _plan = build_line_plan(
                _transit, _pts, task_type="transit",
                node_actions=_na, direction=_park_dir,
                edge_speeds=build_edge_speeds(_rds),
                edge_lidar=build_edge_lidar(_rds),
                agv_id=agv_id,
                initial_prev_tag=str(state.prev_tag) if state.prev_tag else None,
            )
            self.set_route(agv_id, _transit, "transit", direction=_park_dir)
            _rt = self._routes[agv_id]
            _rt.window_end  = len(_transit) - 1
            _rt.is_complete = True
            if self.send_window_fn:
                self.send_window_fn(agv_id, _plan)
            else:
                from mqtt_client import send_order as _so
                _so(agv_id, _plan)
            from task_queue import agv_task_queue as _atq, CMD_GO_TO as _CGT
            _atq.insert_next(agv_id, _CGT, dest_node=str(dest_final))
            print(f"[TRAFFIC] {agv_id}: → FLEX PARK tại {side_node}, "
                  f"queue tiếp→{dest_final}")
            return True
        except Exception as _e:
            print(f"[TRAFFIC] {agv_id}: flex_park error: {_e}")
            return False

    def _send_window(
        self,
        agv_id:    str,
        route:     LineAGVRoute,
        w_start:   int,
        w_end:     int,
        is_final:  bool,
        force:     bool = False,
    ) -> None:
        """Build và gửi 1 cửa sổ plan. force=True: bỏ qua chặn-trùng (cứu kẹt)."""
        # CẮT window theo RESERVATION (openTCS allocate-before-move): chỉ RUN tới node
        # đã giữ chỗ. Boundary node nhận WAIT → firmware dừng đúng đó, KHÔNG lao vào node
        # bị xe khác giữ.
        try:
            _res_end = traffic_coordinator.reserved_extent(agv_id, route.full_path, w_start)
            if _res_end < w_end:
                # Node ngay sau vùng đã giữ bị XE KHÁC giữ → chừa thêm 1 node ĐỆM:
                # không bao giờ dừng sát biên reservation của xe kia (ngoài tầm LIDAR).
                _nxt_r = (route.full_path[_res_end + 1]
                          if _res_end + 1 < len(route.full_path) else None)
                if _nxt_r and traffic_coordinator.node_reserved_by_other(agv_id, _nxt_r):
                    _res_end = max(w_start, _res_end - 1)
                w_end    = max(w_start, _res_end)
                is_final = (w_end == len(route.full_path) - 1)
        except Exception:
            pass
        # ── CHỐNG-TRAP (rolling): reservation cắt window về [w_start→w_start] (kẹt tại
        # chỗ) NHƯNG mình ĐANG CHẮN xe khác (node hiện tại ∈ đường tương lai nó) + node
        # KẾ trống vật lý → VACATE 1 node. CÙNG lưới chống-trap như set_route (helper
        # chung). Nếu thiếu net này, re-check rolling (vd `_check_waiting_agvs` khi xe kia
        # di chuyển) sẽ GHI ĐÈ window [w→w+1] (vacate) bằng [w→w] (đứng im) khi node kế
        # bị reservation của follower khoá → 2 xe cùng chiều kẹt nhau (leader không nhường
        # được node mình đang giữ). KHÔNG fire cho standoff thường (xe kia không cần node mình).
        if w_end == w_start and w_start + 1 < len(route.full_path):
            if self._should_anti_trap_vacate(agv_id, route.full_path, w_start):
                w_end    = w_start + 1
                is_final = (w_end == len(route.full_path) - 1)
                print(f"[LINE_AGV] {agv_id}: CHỐNG-TRAP rolling → window [{w_start}→{w_end}] "
                      f"(chắn xe khác; node kế {route.full_path[w_end]} trống → VACATE)")
        # Window y hệt lần trước (cùng dải, không phải đích) → khỏi gửi lại, tránh spam
        # (trừ khi force=True — cứu kẹt khi firmware lỡ dừng giữa route).
        if (not force and route.sent_cmd_id and route.window_start == w_start
                and route.window_end == w_end and not is_final):
            return
        try:
            # Lấy points, node_actions, edge_speeds, edge_lidar từ map_manager singleton
            try:
                from mqtt_client import map_manager as _mm
                from line_agv_plan_builder import build_edge_speeds, build_edge_lidar
                points       = getattr(_mm, "points",       {}) or {}
                node_actions = getattr(_mm, "node_actions", {}) or {}
                roads        = getattr(_mm, "roads",        []) or []
                edge_speeds  = build_edge_speeds(roads)
                edge_lidar   = build_edge_lidar(roads)
            except Exception:
                points       = {}
                node_actions = {}
                edge_speeds  = {}
                edge_lidar   = {}

            # Khi w_start==0 (node đầu cửa sổ = vị trí xe), TRUYỀN prev_tag thật để
            # tính ĐÚNG lệnh rẽ tại node đó (rẽ phụ thuộc node TRƯỚC = prev_tag). Thiếu
            # cái này → mất TURN → xe đi THẲNG thay vì rẽ (vd 4→18 thay vì rẽ 4→9 → đâm).
            # w_start>0: build_plan_window tự dùng full_path[w_start-1] nên không cần.
            _st_w = self.state_store.get(agv_id)
            _init_prev_w = (str(_st_w.prev_tag)
                            if (w_start == 0 and _st_w and _st_w.prev_tag) else None)
            plan = build_plan_window(
                full_path=route.full_path,
                w_start=w_start,
                w_end=w_end,
                points=points,
                is_final=is_final,
                task_type=route.task_type,
                node_actions=node_actions,
                direction=route.direction,
                edge_speeds=edge_speeds,
                edge_lidar=edge_lidar,
                agv_id=agv_id,
                initial_prev_tag=_init_prev_w,
            )

            route.window_start = w_start
            route.window_end   = w_end
            route.sent_cmd_id  = plan["id"]
            route.sent_at      = time.time()
            route.acked        = False
            route.is_complete  = is_final

            if self.send_window_fn is not None:
                self.send_window_fn(agv_id, plan)
            else:
                # Fallback: gửi trực tiếp qua mqtt_client khi callback chưa inject
                from mqtt_client import send_order as _so_fb
                _so_fb(agv_id, plan)
                print(f"[LINE_AGV] {agv_id}: sent window (fallback) [{w_start}→{w_end}] "
                      f"id={plan['id']} final={is_final}")
                return
            print(f"[LINE_AGV] {agv_id}: sent window [{w_start}→{w_end}] "
                  f"id={plan['id']} final={is_final} steps={len(plan['d'])}")

        except Exception as e:
            print(f"[LINE_AGV] {agv_id}: _send_window error: {e}")

    # ── Retry ─────────────────────────────────────────────────────────────────

    def _check_retry(self, agv_id: str, state: LineAGVState) -> None:
        """Gửi lại plan nếu không nhận ACK sau RETRY_TIMEOUT."""
        route = self._routes.get(agv_id)
        if route is None or route.acked or not route.sent_cmd_id:
            return
        if time.time() - route.sent_at < RETRY_TIMEOUT:
            return
        # Không retry nếu xe đang đứng ở đầu cửa sổ (plan đã nhận, chưa di chuyển)
        tag_str = str(state.current_tag)
        if route.full_path and route.window_start < len(route.full_path):
            if tag_str == route.full_path[route.window_start]:
                return
        print(f"[LINE_AGV] {agv_id}: retry plan id={route.sent_cmd_id} "
              f"(no ACK after {RETRY_TIMEOUT}s)")
        self._send_window(
            agv_id, route,
            route.window_start, route.window_end,
            route.is_complete,
        )

    # ── Cửa tự động (gate) — helper dùng chung, MỚI ────────────────────────────
    # Xem door_coordinator.py (thiết kế đầy đủ) + PROTOCOL_GUIDE.md mục
    # "Cửa tự động (Gate Controller)" (giao thức MQTT với bộ điều khiển cửa).

    def _handle_door_arrival(self, agv_id: str, state: "LineAGVState") -> bool:
        """Xe tới node có door_id (cửa tự động) — xin mở cửa, xe đứng chờ (đã
        dừng sẵn nhờ WAIT_SYS/WAIT_USER trong plan) tới khi cửa xác nhận mở
        xong (door_coordinator.resume_after_door sẽ gọi ngược lại để đi tiếp).
        Trả về True nếu node này LÀ cửa (caller phải return ngay), False nếu
        không phải cửa (rơi xuống xử lý cũ — móc hàng/lifecycle picking...).

        BÌNH THƯỜNG chỉ được gọi khi xe ĐANG TIẾN VÀO cửa — main.py:_dispatch_go_to
        đã lo việc TÁCH route (split) để node này luôn là đích thật của 1 chặng
        nhỏ khi đó là hướng tiến vào (xem vòng lặp split_idx, dùng
        door_coordinator.is_exit_arrival để quyết định). Hướng THOÁT cửa
        (đã băng qua) thường không cần dừng nên không tới đây — nhưng NẾU lỡ
        rơi vào đây (vd trùng ranh giới rolling-window ngẫu nhiên), vẫn PHẢI tự
        kiểm tra lại chiều bằng is_exit_arrival để không xin mở NHẦM lúc xe đang
        thực ra đã thoát cửa rồi."""
        _na_door = {}
        try:
            from mqtt_client import map_manager as _mm_door
            _na_door = (getattr(_mm_door, 'node_actions', {}) or {}).get(str(state.current_tag)) or {}
        except Exception:
            pass
        _door_id = str(_na_door.get('door_id') or '').strip()
        if not _door_id:
            return False
        from door_coordinator import door_coordinator
        _node_str = str(state.current_tag)
        if door_coordinator.is_exit_arrival(_door_id, agv_id, _node_str):
            print(f"[LINE_AGV] {agv_id}: tới node cửa tự động '{_door_id}' "
                  f"({_node_str}) — đã thoát cửa, đi tiếp ngay")
            door_coordinator.notify_exit(_door_id, agv_id)
            self.resume_after_door(agv_id)
            return True
        print(f"[LINE_AGV] {agv_id}: tới node cửa tự động '{_door_id}' "
              f"({_node_str}) — xin mở, chờ xác nhận")
        door_coordinator.request_open(_door_id, agv_id, _node_str)
        return True

    def resume_after_door(self, agv_id: str) -> None:
        """Cửa đã xác nhận MỞ (hoặc đã mở sẵn) — cho xe đi tiếp. Route hiện tại
        (chặng nhỏ TỚI node cửa, do split_idx tạo ra) coi như hoàn tất, hàng
        đợi tự dispatch chặng kế (đã insert_next sẵn ở main.py lúc split) —
        giống hệt pattern _complete_hook_leg()."""
        self._routes.pop(agv_id, None)
        traffic_coordinator.deregister(agv_id)
        try:
            from task_queue import agv_task_queue as _atq_door
            _atq_door.on_agv_completed(agv_id, notes="door_opened")
            print(f"[LINE_AGV] {agv_id}: cửa đã mở → tự động đi tiếp")
        except Exception as e:
            print(f"[LINE_AGV] {agv_id}: resume sau cửa lỗi: {e}")

    # ── Móc hàng (xe rơ-moóc/đầu kéo) — helper dùng chung, MỚI ─────────────────

    def _send_hook_raise_delayed(self, agv_id: str, delay: float = 0.3) -> None:
        """Gửi lệnh NÂNG móc sau 1 khoảng trễ ngắn, KHÔNG block thread MQTT (dùng
        threading.Timer). Gửi ngay sát lúc arrived_wait_sys/arrived_wait_user vừa
        ACK xong (2 message liên tiếp gần như tức thời) khiến firmware không kịp
        xử lý — publish rc=0 (broker nhận) nhưng móc không nhô lên thực tế. Trễ
        nhẹ để firmware xử lý xong ACK/arrival trước khi nhận action tiếp theo."""
        def _fire():
            try:
                from mqtt_client import send_line_command
                send_line_command(agv_id, "action", a=ACTION_HOOK_RAISE, v=0)
                print(f"[LINE_AGV] {agv_id}: (trễ {delay}s) đã gửi NÂNG móc")
                _st_hk = self.state_store.get(agv_id)
                if _st_hk:
                    _st_hk.hook_raise_sent_at = time.monotonic()
            except Exception as e:
                print(f"[LINE_AGV] {agv_id}: gửi NÂNG móc (trễ) lỗi: {e}")
        threading.Timer(delay, _fire).start()

    def _complete_hook_leg(self, agv_id: str, notes: str) -> None:
        """Hoàn tất chặng hiện tại NGAY (tự động, không chờ xác nhận web) sau khi
        nâng móc xong (thả hàng) — pop route + deregister + để task_queue tự
        dispatch chặng kế tiếp đã được xếp sẵn (insert_next)."""
        self._routes.pop(agv_id, None)
        traffic_coordinator.deregister(agv_id)
        try:
            from task_queue import agv_task_queue as _atq_hk
            _atq_hk.on_agv_completed(agv_id, notes=notes)
            print(f"[LINE_AGV] {agv_id}: hoàn tất chặng qua {notes} → tự động đi tiếp")
        except Exception as _e_hk:
            print(f"[LINE_AGV] {agv_id}: hook complete queue error: {_e_hk}")

    def _handle_trailer_hook_arrival(self, agv_id: str, state: "LineAGVState", route) -> None:
        """Xử lý xe rơ-moóc/đầu kéo tới 1 node có vai trò móc hàng (lấy/thả) —
        DÙNG CHUNG cho cả arrived_wait_sys VÀ arrived_wait_user, vì map có thể
        cấu hình node lấy/thả bằng arrival_action nào cũng được (wait_sys hay
        wait_user tuỳ người tạo map). Trước đây logic phân biệt lấy/thả CHỈ
        được viết ở nhánh wait_sys — node cấu hình wait_user (vd điểm lấy hàng
        rỗng gần trạm) rơi vào 1 đoạn code RIÊNG, cũ, luôn mặc định là "thả
        hàng" — khiến xe tới điểm LẤY hàng lại tự nhả (không chờ) rồi đi thẳng,
        gây lệch route/vật cản ở đoạn tiếp theo.
        """
        if route and route.direction == 'bwd':
            state.last_transit_direction = 'bwd'
        _na_hook = {}
        try:
            from mqtt_client import map_manager as _mm_hk
            _na_hook = (getattr(_mm_hk, 'node_actions', {}) or {}).get(str(state.current_tag)) or {}
        except Exception:
            pass
        # Ưu tiên 0: đang trong CHẶNG "lấy hàng rỗng gần trạm" đã đánh dấu lúc
        # dispatch (_pending_empty_pickup_legs) — cao hơn CẢ trailer_staging,
        # vì 1 node có thể dùng chung cho cả 2 chức năng (lấy rỗng lúc đi,
        # thả đầy lúc về) — chỉ dispatch-context mới biết đang ở chặng nào,
        # cấu hình tĩnh của node không đủ phân biệt. Dùng 1 lần rồi bỏ đánh dấu.
        _empty_pickup_key = (agv_id, str(state.current_tag))
        _is_empty_pickup_leg = _empty_pickup_key in _pending_empty_pickup_legs
        if _is_empty_pickup_leg:
            _pending_empty_pickup_legs.discard(_empty_pickup_key)
        # Ưu tiên 1: 'trailer_staging' — điểm thả hàng đầy CỐ ĐINH LUÔN là vai
        # trò "thả". Ưu tiên 2: field 'trailer_role' TƯỜNG MINH (drop/pickup).
        # Ưu tiên 3: 'trailer_empty_staging' — dự phòng khi cờ tạm bị mất (off
        # route re-dispatch, force-cancel...). Cuối cùng suy luận theo
        # supply_group (map cũ, AGV carry).
        _trailer_role = str(_na_hook.get('trailer_role') or '').strip().lower()
        if _is_empty_pickup_leg:
            _is_pickup_node = True
        elif str(_na_hook.get('trailer_staging') or '').strip().lower() == 'yes':
            _is_pickup_node = False
        elif _trailer_role == 'pickup':
            _is_pickup_node = True
        elif _trailer_role == 'drop':
            _is_pickup_node = False
        elif str(_na_hook.get('trailer_empty_staging') or '').strip().lower() == 'yes':
            _is_pickup_node = True
        else:
            _is_pickup_node = bool(_na_hook.get('supply_group'))
        state.hook_pending = "pickup" if _is_pickup_node else "dropoff"
        # LUÔN gửi lệnh NÂNG móc khi tới node cần nâng — KHÔNG tin vào hook_state
        # đã ghi nhận trước đó dù đang là "raised": đường xóc/cảm biến lệch trong
        # lúc di chuyển có thể khiến móc thực tế không còn đúng vị trí dù state cũ
        # báo đã nâng. Chỉ coi là xong khi nhận được event 'hook_raised' THẬT từ xe
        # (xử lý ở nhánh event_name == "hook_raised" phía dưới) — không tự suy luận
        # rồi bỏ qua hành động như trước (đã gây lỗi xe không nhả hàng thật ở node
        # thả dù trạng thái nội bộ báo "đã nâng sẵn").
        state.hook_raise_retries = 0   # đợt nâng móc MỚI — reset đếm gửi-lại
        state.hook_fallback_notified = False   # đợt MỚI — cho phép kênh "hook" báo lỗi lại nếu cần
        self._send_hook_raise_delayed(agv_id)
        if _is_pickup_node:
            print(f"[LINE_AGV] {agv_id}: tới điểm lấy hàng {state.current_tag} "
                  f"— gửi NÂNG móc, chờ xe hàng")
        else:
            print(f"[LINE_AGV] {agv_id}: tới điểm thả hàng {state.current_tag} "
                  f"— gửi NÂNG móc để nhả xe hàng, chờ xác nhận từ xe")
        if _is_pickup_node:
            # Đánh dấu pickup giống nhánh carry (tránh lấy hàng 2 lần khi re-dispatch)
            try:
                from task_queue import agv_task_queue as _atq_hkpk
                _run_hkpk = _atq_hkpk._running.get(agv_id)
                if _run_hkpk and getattr(_run_hkpk, 'session_id', None):
                    _atq_hkpk.mark_session_pickup(_run_hkpk.session_id, state.current_tag)
            except Exception as _e_hkpk:
                print(f"[LINE_AGV] {agv_id}: mark pickup (hook) error: {_e_hkpk}")

    def _notify_hook_error(self, agv_id: str, event_name: str) -> None:
        """Lỗi cơ khí móc hàng (nâng/hạ timeout, hoặc hạ bị từ chối vì không có
        xe hàng) — TRƯỚC ĐÂY chỉ in log + báo Telegram, KHÔNG hề gửi lệnh dừng
        xe hay chặn hàng đợi. Nếu firmware không tự đứng yên khi báo lỗi này
        (hoặc đã có sẵn 1 cửa sổ plan buffer từ trước), xe vẫn tiếp tục chạy
        theo plan cũ — tức đi thẳng qua node lỗi luôn, bỏ qua bước móc hàng mà
        KHÔNG hề dừng thật như thông báo "chờ can thiệp thủ công" đã ghi.
        Giờ chủ động: (1) gửi lệnh dừng khẩn cấp thật sự, (2) xoá route +
        reservation hiện tại để hệ thống KHÔNG coi như đang tiến triển bình
        thường nữa (tránh watchdog "DỪNG GIỮA route" hiểu nhầm rồi tự gửi lại
        lệnh chạy tiếp). Hàng đợi (task_queue._running) CỐ TÌNH không đóng —
        để nó treo lại, chờ người dùng tự sửa phần cơ khí rồi Hủy lệnh + gửi
        lại thủ công qua giao diện có sẵn."""
        _msg = f"⚠️ AGV {agv_id}: LỖI móc hàng ({event_name}) — đã gửi lệnh DỪNG xe, cần kiểm tra thủ công."
        print(f"[LINE_AGV] {agv_id}: {_msg}")
        # Firmware đã báo lỗi RÕ RÀNG (không phải im lặng mất gói) → dừng hẳn watchdog
        # retry nâng móc, tránh cứ gửi lại vô ích trong khi đang chờ người sửa cơ khí.
        _st_err = self.state_store.get(agv_id)
        if _st_err:
            _st_err.hook_raise_sent_at = 0.0
        try:
            from mqtt_client import send_line_command
            send_line_command(agv_id, "stop")
        except Exception as _e_stop:
            print(f"[LINE_AGV] {agv_id}: gửi lệnh dừng (do lỗi móc) thất bại: {_e_stop}")
        self._routes.pop(agv_id, None)
        traffic_coordinator.deregister(agv_id)
        _release_all_line_edges(agv_id)
        try:
            from telegram_bot import notify_error as _tg_notify
            _tg_notify(_msg)
        except Exception as _e_tg:
            print(f"[LINE_AGV] {agv_id}: gửi Telegram cảnh báo lỗi: {_e_tg}")

    # ── Event handler ─────────────────────────────────────────────────────────

    def _handle_event(
        self,
        agv_id: str,
        event_name: str,
        data: dict,
        state: LineAGVState,
    ) -> None:
        print(f"[LINE_AGV] {agv_id}: event='{event_name}'")

        # Bước 1: gửi ACK ngay để AGV xóa pendingEvent
        # "continue", "confirm", "return" đều cần ack_event trước khi xử lý
        if self.on_event:
            try:
                self.on_event(agv_id, event_name, data)
            except Exception as e:
                print(f"[LINE_AGV] on_event callback error: {e}")
        else:
            # Fallback nếu callback chưa inject: tự gửi ack trực tiếp qua MQTT
            try:
                from mqtt_client import send_line_command as _slc
                _slc(agv_id, "ack_event", d=event_name)
                print(f"[LINE_AGV] {agv_id}: ACK (fallback) event='{event_name}'")
            except Exception as e:
                print(f"[LINE_AGV] {agv_id}: ACK fallback failed: {e}")

        # Bước 1b: HMI vật lý trên AGV — nút "Tổ X" (event='line_X') hoặc
        # "Về trạm" (event='station') — kênh lệnh thứ 3 ngoài Web UI/App di động.
        if event_name.startswith("line_") and event_name[5:].isdigit():
            try:
                _handle_hmi_line_event(agv_id, int(event_name[5:]))
            except Exception as e:
                print(f"[HMI] {agv_id}: lỗi xử lý sự kiện '{event_name}': {e}")
            return
        if event_name == "station":
            try:
                _handle_hmi_station_event(agv_id)
            except Exception as e:
                print(f"[HMI] {agv_id}: lỗi xử lý sự kiện 'station': {e}")
            return

        # Bước 2: xử lý battery event
        if event_name == "battery_need_charge":
            state.battery_blocking = True
            if self.on_battery_event:
                try:
                    self.on_battery_event(agv_id, event_name, data)
                except Exception as e:
                    print(f"[LINE_AGV] on_battery_event callback error: {e}")

        # Bước 3: xử lý lifecycle events (đến điểm LẤY/GIAO hàng — chờ người xác nhận)
        if event_name == "arrived_wait_sys":
            # Phân biệt rolling-window stop (cửa sổ trung gian, is_complete=False)
            # vs transit completion (đoạn lùi tạm → trigger queue ngay)
            # vs genuine delivery/pickup wait (cửa sổ cuối, is_complete=True)
            route = self._routes.get(agv_id)
            if route and not route.is_complete and state.current_tag is not None:
                # Rolling-window stop: KHÔNG gửi window mù nữa — chạy lại proactive
                # traffic check (tôn trọng waiting_before_conflict + conflict phía
                # trước trong TRAFFIC_LOOKAHEAD). Trước đây gửi thẳng [idx→+LOOKAHEAD]
                # đè lên quyết định chờ → 2 xe lao vào sát nhau.
                tag_str = str(state.current_tag)
                if tag_str in route.full_path:
                    print(f"[LINE_AGV] {agv_id}: rolling stop tại {tag_str} "
                          f"→ re-check traffic rồi mới gửi cửa sổ tiếp")
                    self._check_rolling_plan(agv_id, state)
                else:
                    # Tag lệch route (hiếm): fallback gửi từ window_end như cũ
                    current_idx = route.window_end
                    new_end   = min(current_idx + LOOKAHEAD, len(route.full_path) - 1)
                    is_final  = (new_end == len(route.full_path) - 1)
                    print(f"[LINE_AGV] {agv_id}: rolling stop tại {tag_str} (off-path) "
                          f"→ gửi cửa sổ [{current_idx}→{new_end}] final={is_final}")
                    self._send_window(agv_id, route, current_idx, new_end, is_final)
                return
            # ĐỖ NÉ SIDING: xe đang YIELD (yield_cmd set) tới node siding (route
            # is_complete) → đây KHÔNG phải điểm giao/lấy hàng → TUYỆT ĐỐI không vào
            # 'picking' (chờ HMI mãi → kẹt như log AGV02 ở node 10). Hoàn tất lệnh
            # siding (auto_dispatch=False → KHÔNG pop go_charge phía sau), giải phóng
            # xe, rồi thử RESUME ngay (winner có thể đã rời trước khi tới nơi).
            if route and route.is_complete and state.yield_cmd:
                print(f"[LINE_AGV] {agv_id}: đỗ né tại siding {state.current_tag} — "
                      f"chờ winner {state.yield_winner} rời (giữ '{state.yield_cmd}')")
                self._routes.pop(agv_id, None)
                traffic_coordinator.deregister(agv_id)
                try:
                    from task_queue import agv_task_queue as _atq
                    _atq.on_agv_completed(agv_id, notes='parked_siding',
                                          auto_dispatch=False)
                except Exception as _qe:
                    print(f"[LINE_AGV] {agv_id}: siding-park queue error: {_qe}")
                # Winner đã rời sẵn → resume NGAY; chưa rời → chờ _check_waiting_agvs.
                self._check_waiting_agvs(agv_id)
                return
            # Transit completion: đoạn lùi tạm kết thúc → trigger queue ngay
            if route and route.is_complete and route.task_type == "transit":
                transit_dir = route.direction  # lưu hướng để plan tiếp theo dùng
                state.last_transit_direction = transit_dir
                self._routes.pop(agv_id, None)
                traffic_coordinator.deregister(agv_id)
                print(f"[LINE_AGV] {agv_id}: transit segment done dir={transit_dir} → dispatch next from queue")
                try:
                    from task_queue import agv_task_queue as _atq
                    _atq.on_agv_completed(agv_id)
                except Exception as _qe:
                    print(f"[LINE_AGV] {agv_id}: queue trigger error: {_qe}")
                return
            # Charge arrival: route return_charge → server tự xác nhận, không cần người bấm
            if route and route.is_complete and route.task_type == "return_charge":
                # Trạm sạc luôn dùng approach_dir=bwd → AGV luôn lùi vào trạm
                # Buộc last_transit_direction="bwd" để dispatch tiếp theo dùng direction="fwd"
                # MỚI: xe không lùi được → vừa tiến vào (không lùi), KHÔNG ép "bwd"
                # (nếu ép sai sẽ làm dispatch RỜI trạm tiếp theo tính sai hướng).
                _can_rev_chg = agv_registry.can_reverse(agv_id)
                if _can_rev_chg:
                    state.last_transit_direction = "bwd"
                state.task_lifecycle = "charging"
                print(f"[LINE_AGV] {agv_id}: lifecycle → charging (auto-confirm, "
                      + ("force last_dir=bwd)" if _can_rev_chg else "xe tiến vào, giữ last_dir)"))
                self._routes.pop(agv_id, None)
                traffic_coordinator.deregister(agv_id)
                try:
                    from mqtt_client import release_station
                    release_station(agv_id, reason="arrived_charge_via_route")
                except Exception:
                    pass
                if self.on_state_changed:
                    try:
                        self.on_state_changed(state)
                    except Exception as e:
                        print(f"[LINE_AGV] on_state_changed error: {e}")
                try:
                    from task_queue import agv_task_queue as _atq
                    _atq.on_agv_completed(agv_id, notes="charge_arrived")
                except Exception as _qe:
                    print(f"[LINE_AGV] {agv_id}: queue error: {_qe}")
                return
            # Guard: AGV báo wait_sys tại node TRUNG GIAN (không phải đích cuối).
            # Xảy ra khi firmware dừng giữa đường do vật cản, bat thấp, v.v.
            # Trong trường hợp này KHÔNG vào picking — gửi lại plan từ node hiện tại.
            if route and route.is_complete and state.current_tag is not None:
                final_node = route.full_path[-1] if route.full_path else None
                tag_str = str(state.current_tag)
                if final_node and tag_str != str(final_node):
                    print(f"[LINE_AGV] {agv_id}: wait_sys tại node trung gian {tag_str} "
                          f"(đích thực là {final_node}) — gửi lại plan tiếp")
                    try:
                        current_idx = route.full_path.index(tag_str)
                    except ValueError:
                        current_idx = 0
                    # Gửi cửa sổ ≤LOOKAHEAD node (không gửi full remaining) — tránh tràn buffer
                    new_end  = min(current_idx + LOOKAHEAD, len(route.full_path) - 1)
                    is_final = (new_end == len(route.full_path) - 1)
                    self._send_window(agv_id, route, current_idx, new_end, is_final)
                    return
            # ── CỬA TỰ ĐỘNG: node có door_id → xin mở cửa, chờ xác nhận rồi mới
            # đi tiếp (KHÔNG vào lifecycle "picking", hoàn toàn tự động, không
            # cần xác nhận web/HMI). Kiểm tra TRƯỚC móc hàng — 1 node không nên
            # vừa là cửa vừa là điểm móc, ưu tiên cửa nếu trùng cấu hình.
            # Xem door_coordinator.py + PROTOCOL_GUIDE.md mục "Cửa tự động".
            if self._handle_door_arrival(agv_id, state):
                return
            # ── MÓC HÀNG (xe rơ-moóc/đầu kéo) — node wait_sys → tự động nâng
            # móc, KHÔNG vào lifecycle "picking" (không cần HMI). Logic phân
            # biệt lấy/thả DÙNG CHUNG với arrived_wait_user (xem
            # _handle_trailer_hook_arrival) — map có thể cấu hình node lấy/thả
            # bằng arrival_action nào cũng được. AGV carry/loại khác hoàn toàn
            # không đụng — rơi xuống nhánh cũ bên dưới.
            # NGOẠI LỆ: node được đánh dấu "chỉ xác nhận" (milk-run nhiều Tổ,
            # xem _pending_confirm_only_legs) → BỎ QUA hoàn toàn logic móc, rơi
            # xuống nhánh "chờ xác nhận" như AGV carry (không móc lại — hàng
            # được chuyển tay từ xe Tổ đó sang xe đang kéo).
            # Node 'trailer_staging' (điểm thả hàng đầy CỐ ĐỊNH) LUÔN phải tự động,
            # KHÔNG được phép rơi vào "chờ xác nhận" dù có dấu _pending_confirm_only_legs
            # sót lại từ 1 lượt điều phối khác hay không (dấu đó chỉ nhằm cho các điểm
            # giao/lấy hàng theo Tổ trong milk-run, không áp dụng cho node staging).
            # QUAN TRỌNG: chỉ coi là "tới node staging thật" nếu node đó ĐÚNG LÀ đích
            # được giao ban đầu (agv_task_queue._running.dest_node) — không phải điểm
            # dừng TẠM do bị chiếm đích thật (staging redirect chống kẹt đường,
            # main.py ~3030-3167, không liên quan gì tới trailer_staging) — nếu không
            # check, xe đi NGANG QUA node 81 lúc đường đi (không phải đích) vì kẹt
            # đường cũng bị hiểu nhầm là "đã tới đích thả hàng".
            _na_ws_stg = {}
            try:
                from mqtt_client import map_manager as _mm_ws_stg
                _na_ws_stg = (getattr(_mm_ws_stg, 'node_actions', {}) or {}).get(str(state.current_tag)) or {}
            except Exception:
                pass
            _queued_dest_is_here_ws = False
            try:
                from task_queue import agv_task_queue as _atq_stg_ws
                _run_stg_ws = _atq_stg_ws._running.get(agv_id)
                _queued_dest_is_here_ws = bool(_run_stg_ws and str(getattr(_run_stg_ws, 'dest_node', '') or '').strip() == str(state.current_tag).strip())
            except Exception:
                pass
            _is_trailer_staging_ws = (str(_na_ws_stg.get('trailer_staging', '')).lower() == 'yes'
                                       and _queued_dest_is_here_ws)
            _confirm_only_key_ws = (agv_id, str(state.current_tag))
            _is_confirm_only_ws = (_confirm_only_key_ws in _pending_confirm_only_legs) and not _is_trailer_staging_ws
            if _confirm_only_key_ws in _pending_confirm_only_legs:
                _pending_confirm_only_legs.discard(_confirm_only_key_ws)   # dọn dấu, kể cả khi bị staging ghi đè
            if agv_registry.get_config(agv_id).get('agv_type') == 'trailer' and not _is_confirm_only_ws:
                self._handle_trailer_hook_arrival(agv_id, state, route)
                return
            # Genuine wait: đến điểm dừng thực sự → chờ xác nhận.
            # Có 2 cách xác nhận:
            #   (1) HMI: người bấm nút → AGV gửi event 'confirm'
            #   (2) System API: POST /api/execute/lifecycle-ack/{agv_id}
            # Nếu plan lùi (direction='bwd'), lưu lại để dispatch tiếp theo biết mũi xe ngược
            if route and route.direction == 'bwd':
                state.last_transit_direction = 'bwd'
            state.task_lifecycle = "picking"
            print(f"[LINE_AGV] {agv_id}: lifecycle → picking "
                  f"(node={state.current_tag} — chờ xác nhận HMI hoặc system API)")
            # ĐÁNH DẤU PICKUP KHI XE THỰC SỰ TỚI supply node (không phải lúc dispatch).
            # Đánh dấu sớm lúc dispatch → nếu xe off-route TRƯỚC khi tới supply node thì
            # re-dispatch bị auto-complete bỏ qua → xe KHÔNG BAO GIỜ lấy hàng (lỗi AGV02:
            # đi lạc 2→10, re-dispatch 19 bị "đã lấy hàng → bỏ qua", giao thẳng). CHỈ đánh
            # dấu node SUPPLY thật (wait_sys + supply_group), KHÔNG delivery node (cũng
            # WAIT_SYS nhưng không có supply_group).
            try:
                from task_queue import agv_task_queue as _atq_pk
                _run_pk = _atq_pk._running.get(agv_id)
                if _run_pk and getattr(_run_pk, 'session_id', None):
                    from mqtt_client import map_manager as _mm_pk
                    _na_pk = (getattr(_mm_pk, 'node_actions', {}) or {}).get(
                        str(state.current_tag)) or {}
                    if (str(_na_pk.get('arrival_action', '')).lower() == 'wait_sys'
                            and _na_pk.get('supply_group')):
                        _atq_pk.mark_session_pickup(_run_pk.session_id, state.current_tag)
                        print(f"[LINE_AGV] {agv_id}: đánh dấu ĐÃ LẤY HÀNG tại supply "
                              f"{state.current_tag} (session={_run_pk.session_id})")
            except Exception as _e_pk:
                print(f"[LINE_AGV] {agv_id}: mark pickup error: {_e_pk}")
            if self.on_state_changed:
                try:
                    self.on_state_changed(state)
                except Exception as e:
                    print(f"[LINE_AGV] on_state_changed error: {e}")
            return
        if event_name == "arrived_wait_charge":
            # Firmware gửi event riêng khi đến WAIT_CHARGE → server tự xác nhận
            # Trạm sạc luôn approach_dir=bwd → buộc last_transit_direction="bwd"
            # MỚI: xe không lùi được → vừa tiến vào, KHÔNG ép "bwd" (tránh dispatch
            # rời trạm kế tiếp tính sai hướng).
            if agv_registry.can_reverse(agv_id):
                state.last_transit_direction = "bwd"
            state.task_lifecycle = "charging"
            print(f"[LINE_AGV] {agv_id}: lifecycle → charging (auto-confirm, force last_dir=bwd)")
            self._routes.pop(agv_id, None)
            try:
                from mqtt_client import release_station
                release_station(agv_id, reason="arrived_wait_charge_event")
            except Exception:
                pass
            if self.on_state_changed:
                try:
                    self.on_state_changed(state)
                except Exception as e:
                    print(f"[LINE_AGV] on_state_changed error: {e}")
            try:
                from task_queue import agv_task_queue as _atq
                _atq.on_agv_completed(agv_id, notes="charge_arrived")
            except Exception as _qe:
                print(f"[LINE_AGV] {agv_id}: queue error: {_qe}")
            return
        if event_name == "arrived_wait_user":
            _route_wu = self._routes.get(agv_id)
            # ── CỬA TỰ ĐỘNG: xem giải thích đầy đủ ở nhánh arrived_wait_sys.
            if self._handle_door_arrival(agv_id, state):
                return
            # ── MÓC HÀNG (xe rơ-moóc/đầu kéo) — node wait_user → tự động nâng
            # móc, KHÔNG vào lifecycle "delivering" (không cần HMI). Logic phân
            # biệt lấy/thả DÙNG CHUNG với arrived_wait_sys (xem
            # _handle_trailer_hook_arrival) — trước đây nhánh này LUÔN mặc định
            # là "thả hàng" bất kể trailer_empty_staging/trailer_role thật, nên
            # node lấy hàng cấu hình wait_user (thay vì wait_sys) bị tự nhả và
            # đi thẳng luôn, không chờ. AGV carry/loại khác hoàn toàn không đụng.
            # NGOẠI LỆ: node "chỉ xác nhận" (milk-run nhiều Tổ) — xem giải thích
            # đầy đủ ở nhánh arrived_wait_sys.
            # Node 'trailer_staging' LUÔN tự động — xem giải thích đầy đủ ở nhánh
            # arrived_wait_sys, áp dụng y hệt cho arrived_wait_user.
            _na_wu_stg = {}
            try:
                from mqtt_client import map_manager as _mm_wu_stg
                _na_wu_stg = (getattr(_mm_wu_stg, 'node_actions', {}) or {}).get(str(state.current_tag)) or {}
            except Exception:
                pass
            # Chỉ tính là "tới staging thật" nếu node đúng là đích được giao ban đầu —
            # xem giải thích đầy đủ ở nhánh arrived_wait_sys.
            _queued_dest_is_here_wu = False
            try:
                from task_queue import agv_task_queue as _atq_stg_wu
                _run_stg_wu = _atq_stg_wu._running.get(agv_id)
                _queued_dest_is_here_wu = bool(_run_stg_wu and str(getattr(_run_stg_wu, 'dest_node', '') or '').strip() == str(state.current_tag).strip())
            except Exception:
                pass
            _is_trailer_staging_wu = (str(_na_wu_stg.get('trailer_staging', '')).lower() == 'yes'
                                       and _queued_dest_is_here_wu)
            _confirm_only_key_wu = (agv_id, str(state.current_tag))
            _is_confirm_only_wu = (_confirm_only_key_wu in _pending_confirm_only_legs) and not _is_trailer_staging_wu
            if _confirm_only_key_wu in _pending_confirm_only_legs:
                _pending_confirm_only_legs.discard(_confirm_only_key_wu)
            if agv_registry.get_config(agv_id).get('agv_type') == 'trailer' and not _is_confirm_only_wu:
                self._handle_trailer_hook_arrival(agv_id, state, _route_wu)
                return
            if _route_wu and _route_wu.direction == 'bwd':
                state.last_transit_direction = 'bwd'
            state.task_lifecycle = "delivering"
            print(f"[LINE_AGV] {agv_id}: lifecycle → delivering (chờ xác nhận giao hàng)")
            if self.on_state_changed:
                try:
                    self.on_state_changed(state)
                except Exception as e:
                    print(f"[LINE_AGV] on_state_changed error: {e}")
            return

        # ── Obstacle: ghi nhận thời điểm, trigger timeout reroute nếu chưa clear ─
        if event_name == "obstacle":
            if state.obstacle_since is None:
                state.obstacle_since     = time.monotonic()
                route_now                = self._routes.get(agv_id)
                state.obstacle_direction = (route_now.direction if route_now else "fwd")
                print(f"[LINE_AGV] {agv_id}: obstacle detected "
                      f"dir={state.obstacle_direction} — will reroute in {OBSTACLE_REROUTE_TIMEOUT}s")
            return

        if event_name == "obstacle_cleared":
            state.obstacle_since      = None
            state.obstacle_direction  = ""
            state.accumulated_blocked.clear()
            print(f"[LINE_AGV] {agv_id}: obstacle cleared")
            return

        # Bước 3b: off_route — xe đến sai node, cần re-plan
        if event_name == "off_route":
            route = self._routes.pop(agv_id, None)
            traffic_coordinator.deregister(agv_id)
            _release_all_line_edges(agv_id)
            state.current_edge_pair = None
            dest_node  = route.full_path[-1] if (route and route.full_path) else None
            task_type  = route.task_type     if route else "delivery"
            cur_tag    = state.current_tag
            print(f"[LINE_AGV] {agv_id}: off_route tại tag={cur_tag} "
                  f"dest={dest_node} task={task_type}")
            if dest_node and cur_tag is not None:
                try:
                    from task_queue import agv_task_queue as _atq
                    from task_queue import CMD_GO_TO as _CGT, CMD_GO_CHARGE as _CGC
                    cmd = _CGC if task_type in ("return_charge",) else _CGT
                    # 1. Thêm lệnh re-dispatch vào đầu queue
                    _atq.insert_next(agv_id, cmd, dest_node=str(dest_node))
                    # 2. Hoàn thành task hiện tại để giải phóng _running và auto-dispatch
                    #    Nếu không gọi on_agv_completed, task cũ vẫn "running" → queue kẹt.
                    _atq.on_agv_completed(agv_id, notes='off_route')
                    print(f"[LINE_AGV] {agv_id}: off_route → re-dispatch cmd={cmd} dest={dest_node}")
                except Exception as e:
                    print(f"[LINE_AGV] {agv_id}: off_route re-dispatch error: {e}")
            return

        # Bước 3c: plan_wait_timeout — firmware nhận plan xong nhưng không thấy
        # chạy, tự báo timeout nội bộ. KHÁC off_route: xe VẪN ở đúng node của
        # route hiện tại (không lệch vị trí) — chỉ là gói lệnh trước đó có thể
        # đã bị rớt/race lúc server gửi quá sát ngay sau khi vừa hoàn tất chặng
        # trước (xem comment "plan-race" ở watchdog CỨU KẸT phía trên). Vì vị
        # trí vẫn đúng, KHÔNG cần re-plan lại từ đầu như off_route — chỉ cần gửi
        # LẠI đúng cửa sổ hiện tại (force=True) để firmware nhận lại lệnh.
        if event_name == "plan_wait_timeout":
            route = self._routes.get(agv_id)
            ct = str(state.current_tag) if state.current_tag is not None else None
            ci = (route.full_path.index(ct)
                  if (route and route.full_path and ct in route.full_path) else -1)
            if route and ci >= 0:
                print(f"[LINE_AGV] {agv_id}: plan_wait_timeout tại {ct} — route vẫn đúng, "
                      f"GỬI LẠI cửa sổ hiện tại")
                self._send_window(agv_id, route, ci, route.window_end,
                                  route.is_complete, force=True)
            else:
                # Không có route hợp lệ để resend (hiếm gặp) → fallback re-dispatch
                # từ vị trí hiện tại, cùng cơ chế với off_route.
                print(f"[LINE_AGV] {agv_id}: plan_wait_timeout nhưng không có route hợp lệ "
                      f"để gửi lại — fallback re-dispatch")
                route = self._routes.pop(agv_id, None)
                traffic_coordinator.deregister(agv_id)
                _release_all_line_edges(agv_id)
                state.current_edge_pair = None
                dest_node = route.full_path[-1] if (route and route.full_path) else None
                task_type = route.task_type if route else "delivery"
                if dest_node and ct is not None:
                    try:
                        from task_queue import agv_task_queue as _atq
                        from task_queue import CMD_GO_TO as _CGT, CMD_GO_CHARGE as _CGC
                        cmd = _CGC if task_type in ("return_charge",) else _CGT
                        _atq.insert_next(agv_id, cmd, dest_node=str(dest_node))
                        _atq.on_agv_completed(agv_id, notes='plan_wait_timeout')
                        print(f"[LINE_AGV] {agv_id}: plan_wait_timeout fallback → "
                              f"re-dispatch cmd={cmd} dest={dest_node}")
                    except Exception as e:
                        print(f"[LINE_AGV] {agv_id}: plan_wait_timeout fallback "
                              f"re-dispatch error: {e}")
            return

        # ── HMI VẬT LÝ TRÊN XE (kênh lệnh thứ 3, ngoài Web UI/Mobile App) ────
        # Nút bấm cấu hình CỨNG trên màn hình xe → firmware gửi event này kèm
        # 'dest' cố định trong chính message state. HMI 1 CHIỀU (không có màn
        # hình phản hồi) nên: validate chặt dest trước khi dispatch, và nếu bị
        # từ chối/lỗi thì chỉ log lại (không có gì để trả về HMI).
        # Đi qua ĐÚNG agv_task_queue.dispatch_or_queue() mà Web UI/App đang dùng
        # → được TrafficEngine điều phối/xếp hàng y hệt, KHÔNG thêm logic riêng.
        # Đây là bổ sung THUẦN TÚY: mọi event khác ở trên/dưới giữ nguyên hành vi.
        if event_name == "hmi_request":
            _dest_hmi = str(data.get("dest", "") or "").strip()
            if not _dest_hmi:
                print(f"[LINE_AGV] {agv_id}: hmi_request thiếu 'dest' — bỏ qua")
                return
            try:
                from mqtt_client import map_manager as _mm_hmi
                _g_hmi = _mm_hmi.line_graph if _mm_hmi.line_graph else _mm_hmi.graph
                if not _g_hmi or _dest_hmi not in _g_hmi:
                    print(f"[LINE_AGV] {agv_id}: hmi_request dest='{_dest_hmi}' "
                          f"không tồn tại trên map hiện tại — từ chối")
                    return
            except Exception as _e_hmi:
                print(f"[LINE_AGV] {agv_id}: hmi_request validate map error: {_e_hmi} — từ chối")
                return
            try:
                from task_queue import agv_task_queue as _atq_hmi, CMD_GO_TO as _CGT_hmi
                _cmd_hmi, _dispatched_now = _atq_hmi.dispatch_or_queue(
                    agv_id, _CGT_hmi, dest_node=_dest_hmi)
                print(f"[LINE_AGV] {agv_id}: hmi_request dest={_dest_hmi} → "
                      f"{'dispatch ngay' if _dispatched_now else 'đã xếp hàng (xe đang bận)'}")
            except Exception as _e_hmi2:
                print(f"[LINE_AGV] {agv_id}: hmi_request dispatch error: {_e_hmi2}")
            return

        # ── MÓC HÀNG (xe rơ-moóc/đầu kéo) — kết quả nâng/hạ móc từ firmware ──
        # Hoàn toàn MỚI, không đụng các event khác. hook_state luôn được cập
        # nhật (nguồn sự thật) bất kể context; hook_pending quyết định có cần
        # dispatch tiếp hay chỉ tiếp tục chờ (đang chờ xe hàng ở điểm lấy hàng).
        if event_name == "hook_raised":
            state.hook_state = "raised"
            state.hook_raise_sent_at = 0.0   # có phản hồi → dừng theo dõi retry
            if state.hook_pending == "dropoff":
                state.hook_pending = None
                print(f"[LINE_AGV] {agv_id}: móc đã nâng (xe hàng đã nhả) — tự động đi tiếp")
                self._complete_hook_leg(agv_id, "hook_raised")
            elif state.hook_pending == "pickup":
                # GIỮ NGUYÊN hook_pending='pickup' — KHÔNG tự động hạ móc nữa (theo
                # yêu cầu: chỉ nâng tự động, hạ phải qua thao tác thủ công của người
                # dùng trên Web UI). Web UI dựa vào hook_pending=='pickup' để hiện nút
                # "Hạ móc" — chỉ event 'hook_lowered' (sau khi người dùng bấm nút, xem
                # /api/execute/line-action action_code=31) mới clear field này.
                print(f"[LINE_AGV] {agv_id}: móc đã nâng — chờ người dùng móc hàng vào "
                      f"rồi bấm Hạ móc trên Web UI")
            else:
                state.hook_pending = None
                print(f"[LINE_AGV] {agv_id}: móc đã nâng — chờ xe hàng được đưa vào")
            return

        if event_name == "hook_lowered":
            state.hook_state = "lowered"
            # Áp dụng CHUNG cho mọi điểm lấy hàng (Tổ lẫn điểm lấy hàng rỗng gần
            # trạm) — luôn chờ xác nhận web trước khi đi tiếp, không tự động.
            state.hook_pending = None
            state.task_lifecycle = "picking"
            print(f"[LINE_AGV] {agv_id}: móc đã hạ (xe hàng đã gắn) "
                  f"— chờ xác nhận trên web để đi tiếp")
            if self.on_state_changed:
                try:
                    self.on_state_changed(state)
                except Exception as e:
                    print(f"[LINE_AGV] on_state_changed error: {e}")
            return

        if event_name == "hook_raise_failed":
            print(f"[LINE_AGV] {agv_id}: LỖI nâng móc (timeout, chưa chạm PIN_HOOK_UPLIM) "
                  f"— dừng, chờ can thiệp thủ công")
            self._notify_hook_error(agv_id, "hook_raise_failed")
            return

        if event_name == "hook_lower_failed":
            print(f"[LINE_AGV] {agv_id}: LỖI hạ móc (timeout, chưa chạm PIN_HOOK_DNLIM) "
                  f"— dừng, chờ can thiệp thủ công")
            self._notify_hook_error(agv_id, "hook_lower_failed")
            return

        if event_name == "hook_lower_rejected_no_cargo":
            print(f"[LINE_AGV] {agv_id}: LỖI hạ móc bị TỪ CHỐI (không phát hiện xe hàng) "
                  f"— kiểm tra lại vị trí xe hàng trước khi hạ móc")
            self._notify_hook_error(agv_id, "hook_lower_rejected_no_cargo")
            return

        # Bước 4: thông báo task_queue hoàn thành
        # "continue" = AGV đến đích, chờ hệ thống (tương đương "confirm")
        # "confirm"  = người dùng bấm nút HMI xác nhận
        # "return"   = xe đã về vị trí ban đầu
        _COMPLETE_EVENTS = ("confirm", "continue", "return", "battery_need_charge")
        if event_name in _COMPLETE_EVENTS:
            _completed_route = self._routes.get(agv_id)   # lấy trước khi pop
            # GUARD VỊ TRÍ: confirm/continue/return chỉ hợp lệ khi xe Ở NODE ĐÍCH
            # của route. Firmware/HMI có thể phát 'continue' GIỮA ĐƯỜNG (resume sau
            # chờ/vật cản) — nếu complete mù: route về trạm bị xoá, xe đứng giữa
            # đường mãi mãi nhưng UI hiện "sẵn sàng". battery_need_charge giữ nguyên
            # (cố ý ngắt giữa đường để đi sạc).
            if (event_name in ("confirm", "continue", "return")
                    and _completed_route and _completed_route.full_path
                    and state.current_tag is not None
                    and str(state.current_tag) != str(_completed_route.full_path[-1])):
                print(f"[LINE_AGV] {agv_id}: event='{event_name}' tại node "
                      f"{state.current_tag} GIỮA route (đích={_completed_route.full_path[-1]}) "
                      f"→ KHÔNG complete task, coi như tín hiệu resume")
                # Firmware DỪNG GIỮA route (vd tại supply node passthrough như 64: xe tự
                # dừng ở node có arrival_action/supply_group rồi phát 'continue' xin đi
                # tiếp) → phải GỬI LẠI cửa sổ để xe chạy tiếp tới đích. `_check_rolling_plan`
                # BỎ QUA ngay khi `route.is_complete` (cửa sổ final đã phủ tới đích) → nếu
                # chỉ gọi nó thì KHÔNG gửi gì → xe KẸT mãi tại node giữa (đúng lỗi: AGV02
                # dừng ở 64 không tới 19). Khi route đã complete mà xe đứng GIỮA route →
                # gửi lại cửa sổ còn lại (force=True, bỏ qua chặn-trùng). _send_window tự
                # cắt theo reservation (allocate-before-move) nên vẫn an toàn traffic.
                _resumed = False
                try:
                    _ci_res = _completed_route.full_path.index(str(state.current_tag))
                    # KHÔNG resend nếu xe còn ở node ĐẦU route của 1 dispatch có
                    # has_exit_steps=True — có thể đang dở lùi mù + quay đầu (xem
                    # giải thích đầy đủ ở watchdog "DỪNG GIỮA route" phía trên).
                    _unsafe_exit_res = (_ci_res == 0 and _completed_route.has_exit_steps)
                    # TRƯỚC ĐÂY chỉ resend khi route.is_complete=True — nhưng firmware
                    # cũng có thể đứng "chờ lệnh hệ thống" mãi sau 'continue' giữa 1
                    # cửa sổ ROLLING chưa complete (vd sau khi obstacle vừa hết): window
                    # cũ vẫn còn hợp lệ về mặt server (chưa cần refresh) nên
                    # _check_rolling_plan không gửi gì, nhưng firmware vẫn cần 1 lệnh
                    # MỚI để thực sự chạy tiếp. Nên giờ LUÔN resend (is_complete hay
                    # không) — chỉ khác biên window: route xong thì gửi hết phần còn
                    # lại (LOOKAHEAD), route rolling thì gửi lại đúng tới window_end
                    # hiện có (không tự ý mở rộng thêm — việc mở rộng do
                    # _check_rolling_plan quyết định ở lần tag-change riêng).
                    if _ci_res < len(_completed_route.full_path) - 1 and not _unsafe_exit_res:
                        if _completed_route.is_complete:
                            _we_res = min(_ci_res + LOOKAHEAD,
                                          len(_completed_route.full_path) - 1)
                        else:
                            _we_res = max(_ci_res, _completed_route.window_end)
                        _completed_route.window_start = _ci_res
                        self._send_window(agv_id, _completed_route, _ci_res, _we_res,
                                          _we_res == len(_completed_route.full_path) - 1,
                                          force=True)
                        _resumed = True
                except ValueError:
                    pass
                if not _resumed:
                    self._check_rolling_plan(agv_id, state)
                return
            # GUARD STAGING/RETRY (KHÔNG có route): xe đang ĐỨNG CHỜ RETRY vì đích bị chiếm.
            # Nhánh "đứng yên chờ retry" (main.py) đã gọi on_agv_completed(auto_dispatch=False)
            # → _running RỖNG + đặt state.pending_retry_cmd (đích chờ trong pending_retry_dest).
            # 'continue'/'confirm' lúc này tới (HMI/firmware) → nếu để rơi xuống on_agv_completed
            # bên dưới sẽ dispatch LỆNH KẾ (giao hàng), BỎ QUA điểm lấy/giao đang chờ (đúng lỗi:
            # AGV01 lấy 64 xong chờ 19 bị chiếm → 'continue' nhảy sang go_to(96), 19 chỉ ghé như
            # điểm né transit). FIX: nếu pending_retry_cmd đang set → KHÔNG hoàn tất, giữ lệnh để
            # _check_waiting_agvs retry khi đích trống. (Cũng chặn staging chưa-tới-đích theo
            # _running.dest_node phòng trường hợp khác.) mid-route guard ở trên lo case CÓ route.
            if event_name in ("confirm", "continue", "return") and not _completed_route:
                _pend = getattr(state, 'pending_retry_cmd', None)
                _dest_stg = getattr(state, 'pending_retry_dest', None) if _pend else None
                if _dest_stg is None:
                    try:
                        from task_queue import agv_task_queue as _atq_stg
                        _run_stg = _atq_stg._running.get(agv_id)
                        if _run_stg and getattr(_run_stg, 'dest_node', None) is not None:
                            _dest_stg = str(_run_stg.dest_node)
                    except Exception:
                        pass
                _not_at_dest = (_dest_stg is not None and state.current_tag is not None
                                and str(state.current_tag) != str(_dest_stg))
                if _pend or _not_at_dest:
                    print(f"[LINE_AGV] {agv_id}: event='{event_name}' tại node "
                          f"{state.current_tag} đang CHỜ RETRY/staging (đích={_dest_stg}, "
                          f"pending={_pend}) → KHÔNG hoàn tất, giữ lệnh chờ đích trống")
                    return
            # Nếu đang chờ lifecycle (arrived_wait_sys/user), HMI xác nhận → tự sync
            if state.task_lifecycle:
                print(f"[LINE_AGV] {agv_id}: lifecycle '{state.task_lifecycle}' "
                      f"auto-cleared by HMI event='{event_name}'")
                state.task_lifecycle = None
                if self.on_state_changed:
                    try:
                        self.on_state_changed(state)
                    except Exception as e:
                        print(f"[LINE_AGV] on_state_changed error: {e}")
            # Xóa route + traffic registration
            self._routes.pop(agv_id, None)
            traffic_coordinator.deregister(agv_id)
            # Lưu hướng vừa hoàn thành để dispatch tiếp theo dùng
            if _completed_route and _completed_route.direction == 'bwd':
                state.last_transit_direction = 'bwd'
            try:
                from task_queue import agv_task_queue
                agv_task_queue.on_agv_completed(agv_id, notes=f"event:{event_name}")
                print(f"[LINE_AGV] {agv_id}: task completed via event='{event_name}'")
            except Exception as e:
                print(f"[LINE_AGV] queue on_agv_completed error: {e}")

    # ── Connection handler ────────────────────────────────────────────────────

    def _on_connection(self, agv_id: str, payload_str: str) -> None:
        try:
            data       = json.loads(payload_str)
            conn_state = str(data.get("connectionState", "OFFLINE")).upper()
            if conn_state not in ("ONLINE", "OFFLINE", "CONNECTIONBROKEN"):
                conn_state = "OFFLINE"
        except Exception:
            conn_state = "OFFLINE"

        state = self.state_store.get_or_create(agv_id)
        old   = state.connection_state

        # Bỏ qua LWT/retained cũ: nếu AGV vừa gửi state gần đây thì nó đang ONLINE thật
        if conn_state in ("OFFLINE", "CONNECTIONBROKEN") and state.last_update > 0:
            elapsed = time.time() - state.last_update
            if elapsed < OFFLINE_TIMEOUT_SEC:
                print(f"[LINE_AGV] {agv_id}: ignored stale '{conn_state}' "
                      f"(state nhận {elapsed:.1f}s trước < {OFFLINE_TIMEOUT_SEC}s)")
                return

        state.connection_state = conn_state

        if conn_state != old:
            print(f"[LINE_AGV] {agv_id}: connection {old}→{conn_state}")

        if conn_state in ("OFFLINE", "CONNECTIONBROKEN"):
            _release_all_line_edges(agv_id)
            traffic_coordinator.deregister(agv_id)
            state.current_edge_pair = None

    # ── Manual position override ─────────────────────────────────────────────

    def override_position(self, agv_id: str, tag: int) -> None:
        """Đặt thủ công vị trí AGV (dùng khi server mới khởi động chưa nhận state)."""
        state = self.state_store.get_or_create(agv_id)
        old   = state.current_tag
        state.current_tag = tag
        if state.last_update == 0.0:
            state.last_update = time.time()
        if state.connection_state != "ONLINE":
            state.connection_state = "ONLINE"
        print(f"[LINE_AGV] {agv_id}: position overridden {old}→{tag} (manual set)")

    # ── Pending command tracking ───────────────────────────────────────────────

    def record_sent_cmd(self, agv_id: str, cmd_id: str, payload) -> None:
        self._pending_cmds[agv_id] = {
            "cmd_id":  cmd_id,
            "sent_at": time.time(),
            "payload": payload,
        }
        # Cũng cập nhật route nếu có
        route = self._routes.get(agv_id)
        if route and cmd_id:
            route.sent_cmd_id = cmd_id
            route.sent_at     = time.time()
            route.acked       = False

    def get_pending_cmd(self, agv_id: str) -> Optional[dict]:
        return self._pending_cmds.get(agv_id)


# ── Module-level singleton ────────────────────────────────────────────────────
line_agv_handler = LineAGVHandler()
