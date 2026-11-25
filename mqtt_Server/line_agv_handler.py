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
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Optional, Callable, Union

from agv_registry import agv_registry


import functools as _functools


def _agv_scoped(fn):
    """Chạy phương thức (self, agv_id, ...) trong VÙNG HOẠT ĐỘNG của xe agv_id: đồ thị
    map_manager.graph/line_graph tự loại các node loại xe này không được vào (đường vòng,
    chỗ đỗ né, lùi... không bao giờ đưa xe vào vùng cấm). Xem MapManager.agv_scope."""
    @_functools.wraps(fn)
    def _wrapper(self, agv_id, *args, **kwargs):
        try:
            from mqtt_client import map_manager as _mm_scope
        except Exception:
            return fn(self, agv_id, *args, **kwargs)
        with _mm_scope.agv_scope(agv_id):
            return fn(self, agv_id, *args, **kwargs)
    return _wrapper


def _charger_siding_ok(agv_id: str, node, busy=None) -> bool:
    """Trạm sạc `node` có dùng được làm ĐIỂM NÉ cho xe agv_id không — CHỈ gọi khi xe kẹt hết
    đường (phương án cuối). Điều kiện: đúng là trạm sạc; loại xe này được phép vào (vùng cấm);
    trạm dành riêng (station_agv_type) khớp loại xe hoặc dùng chung; không có xe khác đang đứng /
    sắp tới (busy) và không bị xe khác giữ chỗ (reserve_station)."""
    try:
        from mqtt_client import map_manager as _mm, _station_reservations, _station_reservations_lock
    except Exception:
        return False
    node = str(node)
    cfg = (getattr(_mm, "node_actions", {}) or {}).get(node) or {}
    if not (str(cfg.get("locationType", "")).upper() == "CHARGER"
            or str(cfg.get("arrival_action", "")).lower() == "wait_charge"):
        return False
    if not _mm.is_node_allowed(agv_id, node):
        return False
    st_type = str(cfg.get("station_agv_type") or "").strip().lower()
    my_type = str(agv_registry.get_config(agv_id).get("agv_type") or "").strip().lower()
    if st_type and st_type != my_type:
        return False
    if busy and node in busy:
        return False
    with _station_reservations_lock:
        holder = _station_reservations.get(node)
    return not (holder and holder != agv_id)


def _nodes_busy_for(agv_id: str, handler) -> set:
    """Node đang có xe KHÁC đứng hoặc nằm trên đường đã đăng ký / dự định của xe khác."""
    busy: set = set()
    try:
        for oid, st in handler.state_store._states.items():
            if oid != agv_id and st is not None and st.current_tag is not None:
                busy.add(str(st.current_tag))
    except Exception:
        pass
    for oid, r in traffic_coordinator._registered.items():
        if oid != agv_id:
            busy.update(str(n) for n in r['path'][r.get('current_idx', 0):])
    for oid, ir in traffic_coordinator._intent_route.items():
        if oid != agv_id and ir:
            busy.update(str(n) for n in ir)
    return busy

from line_agv_plan_builder import (
    build_plan_window,
    first_window_end,
    LOOKAHEAD,
    RETRY_TIMEOUT,
    ACTION_HOOK_RAISE,
    ACTION_HOOK_LOWER,
    ACTION_DIR_BWD,
    ACTION_RUN,
    ACTION_WAIT_CHARGE,
    ACTION_TURN_R,
    ACTION_TURN_L,
)

# Ngưỡng thời gian không nhận state → coi là OFFLINE
OFFLINE_TIMEOUT_SEC = 30.0  # Line AGV chỉ pub state khi di chuyển — cần timeout dài hơn VDA5050

# Thời gian vật cản duy trì trước khi tự reroute
OBSTACLE_REROUTE_TIMEOUT = 5.0   # giây

# Xe phải đứng yên GIỮA route đủ lâu (đường phía trước thông) mới gửi-lại cửa sổ cứu
# kẹt — đủ dài để KHÔNG ghi đè plan vừa dispatch (xe mới tới node chưa kịp chạy).
STUCK_RESEND_GRACE = 8.0   # giây — tăng từ 4.0 để giảm tần suất gửi lại khi kẹt
STUCK_RESEND_COOLDOWN = 7.0   # giây giữa các lần gửi lại liên tiếp — tăng từ 3.0

# Nudge (gửi lại cửa sổ) có thể lặp vô hạn nếu xe không hề phản hồi (kẹt vật lý/
# firmware — không phải do traffic engine chặn). Sau ngưỡng này vẫn chưa nhúc
# nhích dù đã nudge nhiều lần → CẢNH BÁO một lần cho dễ phát hiện, cùng mẫu với
# cảnh báo "sau ~20s" của LOCATE_THEN_CHARGE (mqtt_client.py) — KHÔNG tự ý đổi
# hành vi (vẫn tiếp tục nudge định kỳ như cũ), chỉ tăng khả năng phát hiện sớm.
STUCK_ALERT_THRESHOLD = 60.0   # giây đứng yên liên tục trước khi cảnh báo

# Vòng lặp off_route (xe cứ bị đẩy lại đúng 1 node rồi off_route lại) — xem giải
# thích đầy đủ tại self._off_route_history trong __init__.
OFF_ROUTE_LOOP_THRESHOLD  = 3      # số lần off_route liên tiếp TẠI ĐÚNG 1 TAG → coi là vòng lặp
OFF_ROUTE_LOOP_WINDOW_SEC = 90.0   # cửa sổ thời gian tính các lần off_route gần đây
# PHÁT HIỆN THỰC TẾ (2026-09-30, AGV04 "lùi trôi dần" 13→99→10→11→12): biến thể
# KHÁC của vòng lặp — mỗi lần off_route lại rẽ SAI sang 1 node KHÁC (không lặp
# lại đúng 1 tag như OFF_ROUTE_LOOP_THRESHOLD ở trên bắt được), nên xe cứ trôi
# dần qua hàng loạt node khác nhau mà KHÔNG bao giờ có 1 tag lặp lại ≥3 lần liên
# tiếp — né được bộ đếm "cùng 1 tag" phía trên. Bắt bằng cách khác: đếm TỔNG SỐ
# lần off_route trong cùng cửa sổ, KHÔNG cần cùng tag — off_route lặp lại dồn dập
# (dù mỗi lần ở node khác) trong thời gian ngắn vẫn là dấu hiệu thrashing thật.
OFF_ROUTE_DRIFT_THRESHOLD = 5      # tổng số lần off_route (bất kỳ tag) trong cửa sổ → coi là trôi/thrash

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

# Ngưỡng "đường vòng có đáng đi không" cho _try_line_reroute(require_worthwhile=True) —
# dùng ở nhánh "còn đường khác → đi luôn" (following, tự chọn chứ không bắt buộc). Chấp
# nhận đường thay thế nếu thoả ÍT NHẤT MỘT trong 2 điều kiện (không dài hơn đường cũ quá
# X node HOẶC không dài hơn quá Y lần) — không thoả CẢ HAI mới coi là "quá xa, thà chờ".
REROUTE_WORTHWHILE_MAX_EXTRA = 4     # số node dôi ra tối đa được chấp nhận
REROUTE_WORTHWHILE_MAX_RATIO = 2.0   # tỉ lệ dài hơn tối đa được chấp nhận

# Xe cùng chiều chắn phía trước (following): KHÔNG còn ngưỡng đếm node. Quyết định theo THỜI GIAN — đổi đường chỉ khi
# thời gian vòng dôi thêm nhỏ hơn thời gian ước tính chờ xe chắn thoát (estimate_clear_wait_sec / detour_allowance_sec).
# Mô phỏng 2026-11-03: SIM04/06 đổi sang đường dôi 11 node dù xe trước đang chạy và còn cách 4-5 node (ngưỡng cũ
# "tỉ lệ ≤ 2" tính trên cả quãng đường còn lại nên đường dài nào cũng lọt).
FOLLOW_REROUTE_MIN_STALL_SEC = 4.0   # phải đứng chờ ≥ chừng này giây mới xét đổi đường (tránh lật nhánh vì chắn thoáng qua)

# Cooldown giữa 2 lần ĐỖ-NÉ (parking) head-on tại DISPATCH (main.py, khác
# REROUTE_COOLDOWN ở trên vốn dành cho _try_line_reroute lúc đang chạy giữa route).
# Chống dao động: mỗi lần xe "đến" node đỗ-né xong, dispatch lại đích cũ → nếu HEAD-ON
# với ĐÚNG xe đó vẫn còn (chưa kịp rời) mà đỗ-né tiếp có thể chọn ngược lại đúng node
# vừa rời → đi tới lui liên tục giữa 2 node đỗ-né sát nhau. Trong cooldown này, rơi
# xuống "dừng chờ tại chỗ" (không di chuyển) thay vì đỗ-né lần nữa.
PARKING_COOLDOWN = 15.0

# PHÁT HIỆN THỰC TẾ (2026-10-02): REROUTE_COOLDOWN (18s) tự nó có thể trở thành cái
# bẫy khi cả hệ thống đang THỰC SỰ bế tắc (vd 2 xe khoá chéo nhau qua reservation —
# xe A chờ node bị xe B "giữ chỗ trước" trong khi B lại đang đứng chờ chính A) — mỗi
# lần watchdog đánh thức lại rơi vào "vừa reroute < 18s → chờ tại chỗ", xe KHÔNG BAO
# GIỜ thực sự thử đường khác dù đã đứng im rất lâu (log thực tế: 3 xe cùng đứng im
# >2 phút, liên tục in "BỎ reroute... chống dao động"). Thêm lối thoát có điều kiện
# CHẶT: chỉ bỏ qua cooldown khi xe đã đứng im (không tiến được 1 node nào) LÂU HƠN
# chính cooldown một khoảng an toàn — để không vô hiệu hoá chống dao động trong các
# tình huống chờ ngắn bình thường, chỉ kích hoạt khi cooldown thật sự là rào cản cuối.
STALL_BYPASS_SEC = 25.0

# Ngưỡng coi là "CẢ HỆ THỐNG bí hoàn toàn" (global stall, N xe, không chỉ 2 xe khoá
# chéo nhau) — dùng để kích hoạt tính năng "node chờ" (xem check_global_stall()).
# Lớn hơn STALL_BYPASS_SEC để nhánh A (bypass cooldown, tự giải được nếu còn đường
# khác) có đủ thời gian thử trước; node chờ chỉ là biện pháp CUỐI khi ngay cả bypass
# cũng không giải quyết được (vd không còn đường nào khác ngoài đứng chờ thật).
GLOBAL_STALL_SEC = 45.0

# Bước CƯỠNG BỨC cuối: xe đứng im liên tục quá ngưỡng này (kể cả khi đã thử đổi đường/
# lùi mà vẫn bí) → ép đi vào node đỗ trống gần nhất để nhả node đang giữ, rồi tự đi
# tiếp lệnh cũ. Cooldown tránh ép lặp liên tục cùng 1 xe.
STALL_FORCE_YIELD_SEC = 90.0
STALL_FORCE_YIELD_COOLDOWN = 120.0
IDLE_BLOCKER_EVICT_SEC = 60.0
COLLISION_HOLD_SEC = 120.0   # sau PHYSICAL_COLLISION_ACTIVE: không re-dispatch tự động trong khoảng này   # xe đứng yên chắn đường xe khác quá ngần này giây → ép đi sang node trống

# ── Thống kê điều phối (sản xuất + mô phỏng dùng chung code này, mỗi process
# tự có bộ đếm riêng của mình) — dùng cho màn "Mô phỏng Fleet" hiển thị số lần
# gặp ngã tư/xử lý và số lần lỗi/kẹt (xem GET /api/execute/traffic-stats trong
# main.py). Chỉ CỘNG DỒN tại các điểm quyết định đã có sẵn, KHÔNG đổi hành vi
# gì. Dict thường (không defaultdict) để không thêm import mới vào file này.
_traffic_stats_lock = threading.Lock()
_traffic_stats: dict = {"junction": {}, "alerts": {}}


def _bump_traffic_stat(category: str, key: str) -> None:
    with _traffic_stats_lock:
        bucket = _traffic_stats.setdefault(category, {})
        bucket[key] = bucket.get(key, 0) + 1


def get_traffic_stats() -> dict:
    """Snapshot thống kê điều phối hiện tại (bản copy, an toàn đọc ngoài lock)."""
    with _traffic_stats_lock:
        return {k: dict(v) for k, v in _traffic_stats.items()}


def reset_traffic_stats() -> None:
    """Xoá sạch thống kê — dùng khi bắt đầu 1 lượt mô phỏng mới để số liệu
    không lẫn từ lượt chạy trước (process mô phỏng có thể sống qua nhiều lượt
    Start/Stop trên UI)."""
    with _traffic_stats_lock:
        _traffic_stats["junction"] = {}
        _traffic_stats["alerts"] = {}


# ── Dự đoán head-on THEO THỜI GIAN THẬT (khoảng cách + tốc độ), KHÔNG đếm node ──
# Trước đây bước "Head-on DỰ ĐOÁN" (_find_upcoming_conflict #4) chặn NGAY nếu route
# TƯƠNG LAI (toàn bộ, không giới hạn) của xe kia có 1 cạnh đi ngược chiều — kể cả khi
# xe kia đang bận việc khác CÁCH RẤT XA, có thể mất nhiều phút mới tới điểm giao nhau.
# Hậu quả thực tế: 1 xe đã xong việc, sẵn sàng đi tiếp, bị chặn oan chỉ vì tuyến ĐÍCH
# CUỐI của xe khác (chưa hề tới gần) tình cờ trùng 1 đoạn. Giờ so sánh THỜI GIAN THẬT
# (quãng đường 'distance' + tốc độ 'speed' cấu hình trên map, không phải số node —
# 2 xe cách nhau "5 node" có thể là 5 cạnh dài+nhanh (thật ra rất xa về thời gian) hoặc
# 5 cạnh ngắn+chậm (rất gần)) ước lượng xe kia tới điểm giao nhau so với chính mình:
# chỉ coi là mối đe doạ THỰC SỰ nếu xe kia có thể tới nơi trong khoảng thời gian tương
# đương (hoặc sớm hơn) — xa hơn nhiều thì bỏ qua, để dành đánh giá lại ở lần state-tick
# sau khi xe kia đã tới gần hơn (luôn re-check mỗi khi có state mới).
#
# Tiêu chí AN TOÀN đúng về mặt vật lý KHÔNG phải "xe kia xa hơn X lần" (tỉ lệ) — trên
# các đoạn đường dài/chậm, quãng đường CÒN LẠI của 2 xe tới cùng 1 điểm giao thường
# cùng bậc độ lớn (không lệch nhau nhiều LẦN) dù một bên thực sự đủ xa để mình đi qua
# AN TOÀN TRƯỚC. Tiêu chí đúng: xe kia phải tới điểm giao nhau MUỘN HƠN thời điểm mình
# ĐÃ ĐI QUA KHỎI điểm đó (không chỉ mới tới nơi) — dùng THỜI GIAN TRUNG BÌNH MỖI CẠNH
# của chính hành trình mình vừa tính (cùng đơn vị, không cần biết đơn vị thật) làm ước
# lượng "cần thêm bao lâu để đi qua khỏi điểm giao" (HEADON_CLEARANCE_EDGES cạnh nữa).
HEADON_CLEARANCE_EDGES = 1.5      # số "cạnh trung bình" cần thêm để coi là ĐÃ ĐI QUA KHỎI
HEADON_PREDICT_BUFFER_SEC = 15.0  # buffer nhỏ cộng thêm chống nhiễu số/làm tròn
# NGÃ RẼ/CÙNG CHIỀU (khác head-on thật): 2 xe không hề đi đối đầu nhau trên cùng cạnh —
# chỉ CHẠM nhau tại 1 node chung (giao nhau hoặc cùng hướng). Không cần yêu cầu "đã đi
# qua khỏi + dư vài cạnh" như head-on thật (mức an toàn đó chỉ cần khi 2 xe lao vào nhau
# trên cùng 1 đường) — CHỈ cần chủ khoá KHÔNG CÒN Ở PHẠM VI node đó đúng lúc mình định
# qua (đúng yêu cầu: "xe đi trước chỉ cần không nằm trong phạm vi di chuyển của xe sau
# là xe sau đi được luôn"). PHÁT HIỆN THỰC TẾ (2026-09-23): dùng chung ngưỡng head-on
# (my_eta + 1.5 cạnh + 15s) cho cả trường hợp này khiến xe sau phải chờ RẤT LÂU dù xe
# trước chỉ còn cách vài giây/vài cạnh và không hề cản đường thật — ví dụ xe trước đang
# đi lòng vòng gần đó (lùi/rẽ nhánh khác) vẫn giữ node trong cửa sổ RESERVE_AHEAD suốt
# nhiều chục giây dù không còn thực sự chắn lối. Buffer nhỏ hơn nhiều, chỉ đủ chống
# nhiễu số/làm tròn ETA — không cộng thêm "thời gian đi qua khỏi".
JUNCTION_PREDICT_BUFFER_SEC = 5.0
# Ngưỡng ĐẾM NODE trực tiếp cho ngã rẽ/cùng chiều (2026-09-23, theo yêu cầu người
# dùng): chủ khoá còn cách >= ngưỡng này (số node, trên CHÍNH route của nó) tới
# node tranh chấp → CHƯA cần chờ, cứ đi tiếp; chỉ khi khoảng cách thu hẹp còn
# đúng "2-node gap" (dưới ngưỡng) mới thực sự dừng chờ. Không phụ thuộc ước
# lượng tốc độ/thời gian (map có thể thiếu cấu hình 'speed' khiến ETA sai lệch).
JUNCTION_SAFE_NODE_GAP = 3
DEFAULT_EDGE_SPEED_MS = 0.4       # tốc độ dự phòng khi map thiếu 'speed' trên cạnh


def _headon_safe_threshold(my_eta: float, num_edges: int) -> float:
    """Ngưỡng ETA (giây) tối thiểu mà xe kia cần vượt qua để coi là AN TOÀN cho mình đi
    qua điểm giao nhau trước — mình phải ĐÃ ĐI QUA KHỎI (không chỉ vừa tới) trước khi xe
    kia tới nơi. num_edges = số cạnh mình đã tính trong my_eta (để suy ra thời gian
    trung bình mỗi cạnh, dùng làm ước lượng "clearance")."""
    avg_edge_t = (my_eta / num_edges) if num_edges > 0 else my_eta
    return my_eta + (avg_edge_t * HEADON_CLEARANCE_EDGES) + HEADON_PREDICT_BUFFER_SEC


def _estimate_travel_seconds(path: list, from_idx: int, to_idx: int) -> Optional[float]:
    """Ước lượng thời gian (giây) đi từ path[from_idx] đến path[to_idx] dựa trên
    khoảng cách thật ('weight'/distance, do người dùng nhập ở Map Editor) và tốc độ
    cấu hình ('speed', m/s) của TỪNG cạnh trên map — KHÔNG đếm số node. Trả về None
    nếu không tính được (thiếu graph/cạnh) để caller giữ hành vi AN TOÀN cũ (coi như
    chưa biết → không nới lỏng blocking) thay vì đoán liều.
    """
    if from_idx is None or to_idx is None or from_idx >= to_idx or from_idx < 0:
        return 0.0
    if to_idx >= len(path):
        return None
    try:
        from mqtt_client import map_manager as _mm_eta
        g = (_mm_eta.line_graph
             if _mm_eta.line_graph and _mm_eta.line_graph.number_of_nodes() > 0
             else _mm_eta.graph)
        if g is None:
            return None
    except Exception:
        return None
    total = 0.0
    for i in range(from_idx, to_idx):
        u, v = str(path[i]), str(path[i + 1])
        try:
            ed = g[u][v]
        except Exception:
            try:
                ed = g[v][u]   # dự phòng: đồ thị/hướng lệch, dùng thông số cạnh đảo
            except Exception:
                return None
        dist  = float(ed.get('weight', 1.0) or 1.0)
        speed = float(ed.get('speed', DEFAULT_EDGE_SPEED_MS) or DEFAULT_EDGE_SPEED_MS)
        if speed <= 0:
            speed = DEFAULT_EDGE_SPEED_MS
        total += dist / speed
    return total


# ── Cửa sổ dispatch co giãn theo THỜI GIAN THẬT (không còn cố định LOOKAHEAD node) ──
# Mỗi lần gửi 1 "cửa sổ" plan xuống AGV (nhiều node/lần, do giới hạn buffer UART
# Arduino — xem LOOKAHEAD ở line_agv_plan_builder.py), TOÀN BỘ các node trong cửa sổ
# đó bị TrafficCoordinator coi là "ĐÃ CAM KẾT" (_owner_committed_to) — không AGV nào
# khác được giành, DÙ AGV này còn cách rất xa về mặt VẬT LÝ, cho tới khi nó tự đi hết
# cửa sổ. Đây là cơ chế AN TOÀN CỐ Ý (từng sửa 1 vụ đâm nhau thật — xem
# _owner_committed_to) nên KHÔNG được nới lỏng phía "chấp nhận xung đột" — nhưng gốc
# rễ thật sự là: LOOKAHEAD cố định theo SỐ NODE, trong khi trên đoạn đường dài/tốc độ
# thấp, "LOOKAHEAD node" có thể là NHIỀU PHÚT thực tế → khoá cam kết cả 1 đoạn dài
# thời gian dù AGV vừa mới xuất phát. Sửa tại NGUỒN: co ngắn cửa sổ dispatch lại theo
# thời gian thực trên các đoạn dài/chậm (LOOKAHEAD chỉ còn là TRẦN tối đa, không phải
# giá trị cố định luôn dùng) — đoạn ngắn/nhanh vẫn dùng đủ LOOKAHEAD như cũ (không đổi
# hành vi/hiệu năng giao tiếp MQTT trên các map bình thường).
# Đặt DISPATCH_WINDOW_TIME_HORIZON (biến môi trường) lớn hơn để xe đi liền nhiều node mỗi cửa sổ — cần khi khoảng cách cạnh trong
# map không phải mét thật (vd lấy theo toạ độ vẽ/pixel): thời gian ước tính phóng đại nhiều lần nên MỖI cạnh thành 1 cửa sổ
# riêng và xe dừng (WAIT_SYS) ở từng node. Đặt 0 = không co cửa sổ theo thời gian (chỉ còn trần LOOKAHEAD node).
try:
    DISPATCH_WINDOW_TIME_HORIZON = float(os.getenv("DISPATCH_WINDOW_TIME_HORIZON", "60") or 60)
except ValueError:
    DISPATCH_WINDOW_TIME_HORIZON = 60.0   # giây — trần thời gian "cam kết" cho 1 cửa sổ dispatch


_warned_long_edges: set = set()


def _time_capped_window_end(path: list, start_idx: int, node_cap_idx: int) -> int:
    """Co ngắn `node_cap_idx` (trần cứng theo LOOKAHEAD/buffer phần cứng — KHÔNG BAO
    GIỜ vượt qua giá trị này) xuống theo THỜI GIAN THỰC tích luỹ từ start_idx, nếu tổng
    thời gian ước tính (xem _estimate_travel_seconds) vượt DISPATCH_WINDOW_TIME_HORIZON.
    LUÔN đi ít nhất 1 cạnh (start_idx+1) — cửa sổ không bao giờ rỗng, kể cả khi CHỈ 1
    cạnh đó thôi đã vượt ngưỡng (không có lựa chọn nào ngắn hơn để chọn).
    Nếu không tính được thời gian (thiếu graph/cạnh) → trả nguyên node_cap_idx, giữ
    ĐÚNG hành vi cũ (không co, không mở rộng) — an toàn khi thiếu dữ liệu map."""
    if node_cap_idx <= start_idx:
        return node_cap_idx
    floor_idx = min(start_idx + 1, node_cap_idx)
    end = floor_idx
    if DISPATCH_WINDOW_TIME_HORIZON > 0:
        _t1 = _estimate_travel_seconds(path, start_idx, floor_idx)
        _k1 = (str(path[start_idx]), str(path[floor_idx]))
        if _t1 is not None and _t1 > DISPATCH_WINDOW_TIME_HORIZON and _k1 not in _warned_long_edges:
            _warned_long_edges.add(_k1)       # chỉ cảnh báo 1 lần/cạnh
            print(f"[LINE_AGV] CẢNH BÁO cạnh {_k1[0]}→{_k1[1]}: ước tính {_t1:.0f}s > {DISPATCH_WINDOW_TIME_HORIZON:.0f}s "
                  f"(độ dài cạnh/tốc độ) — xe sẽ DỪNG ở từng node. Khoảng cách cạnh có thể không phải mét thật: "
                  f"nhập 'Khoảng cách thật (m)' trong Map Editor")
    for k in range(start_idx + 1, node_cap_idx + 1):
        t = _estimate_travel_seconds(path, start_idx, k)
        if t is None:
            return node_cap_idx   # không tính được → không đổi hành vi cũ
        if k <= floor_idx or DISPATCH_WINDOW_TIME_HORIZON <= 0 or t <= DISPATCH_WINDOW_TIME_HORIZON:
            end = k
        else:
            break
    return end


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


def resolve_departure_direction(agv_id: str, start_node: str) -> str:
    """
    Quyết định hướng (fwd/bwd) khi xe RỜI KHỎI start_node để bắt đầu 1 CHUYẾN MỚI
    sau khi đã hoàn tất hẳn chặng trước (vd trước khi "Về trạm" sau khi giao/lấy
    hàng xong) — KHÔNG dùng cho việc tiếp tục 1 route đang dở dang (off_route,
    wait_sys giữa route...), những chỗ đó phải giữ nguyên chiều route đang chạy.

    Nguyên lý chung, tổng quát theo layout thật, không hard-code theo loại
    node/AGV cụ thể: xe luôn rời 1 điểm dừng theo chiều NGƯỢC với chiều nó vừa
    dùng để TỚI đó — vừa LÙI vào (rear-first, đầu xe hướng ra ngoài) → rời đi
    bằng TIẾN; vừa TIẾN vào (front-first, đuôi xe hướng ra lối cũ) → rời đi
    bằng LÙI để rút lui đúng theo lối đã vào (áp dụng cho MỌI node dạng
    điểm cụt/điểm chờ, không riêng trạm sạc). Đây chính là quy tắc đã dùng cho
    `_charger_exit_direction` (lùi vào trạm sạc → luôn tiến ra) — hàm này tổng
    quát hoá y hệt quy tắc đó, không cần biết trước node có phải trạm sạc hay
    không, chỉ cần biết chiều chặng VỪA hoàn tất (`last_transit_direction`).

    Ngoại lệ: xe không lùi được (can_reverse=False, trailer/tow) → luôn 'fwd'.
    """
    try:
        from agv_registry import agv_registry as _areg_rdd
        if not _areg_rdd.can_reverse(agv_id):
            return 'fwd'
    except Exception:
        pass
    # Trạm sạc: không có đường lùi thêm sau trạm — luôn thoát bằng tiến (trường
    # hợp riêng của quy tắc chung bên dưới, viết tường minh cho chắc/dễ đọc).
    try:
        from mqtt_client import map_manager as _mm_rdd
        _cfg_rdd = (getattr(_mm_rdd, 'node_actions', {}) or {}).get(str(start_node), {}) or {}
        if (str(_cfg_rdd.get('locationType', '')).upper() == 'CHARGER'
                or str(_cfg_rdd.get('arrival_action', '')).lower() == 'wait_charge'):
            return 'fwd'
    except Exception:
        pass
    # PHÁT HIỆN THỰC TẾ (2026-09-18): quy tắc "lùi ra đúng chiều đã vào" bên dưới
    # chỉ ĐÚNG cho node CỤT (đúng 1 hàng xóm vật lý, vd 105/104 — không còn lối
    # nào khác để đi tiếp ngoài quay lại đúng đường cũ). Với node CÓ ≥2 hàng xóm
    # (vd 98 nối cả 6 và 15 — điểm trả hàng nằm GIỮA hành lang, không phải điểm
    # cụt), xe vừa TIẾN vào hoàn toàn có thể TIẾN TIẾP qua hàng xóm còn lại mà
    # KHÔNG cần lùi lại đúng lối cũ.
    #
    # PHÁT HIỆN THỰC TẾ (2026-10-02): "mặc định TIẾN" (bản sửa trước) lại gây lỗi
    # NGƯỢC khi xe vừa LÙI vào node trung chuyển (vd AGV04 lùi vào 98 từ phía 15 —
    # mũi xe đang hướng VỀ 15, vì lùi vào thì mũi luôn hướng ra lối cũ). Ép "tiến"
    # lúc này chạy THẲNG VỀ LẠI 15 (lối cũ), dù đường về trạm thật cần đi tiếp qua
    # hàng xóm còn lại (6) — xe phải vòng lại qua 98 lần 2 mới ra đúng hướng, đúng
    # lỗi thực tế "cứ phải tiến ra chỗ khác để quay đầu". Người dùng chủ động
    # không gắn approach_dir cho các node này (muốn linh động: vào tiến hay lùi
    # đều được, tuỳ plan tối ưu) — nên quy tắc KHÔNG được giả định trước mũi xe
    # hướng nào, mà phải suy ra từ CHIỀU CHẶNG VỪA XONG: tiến vào (mũi hướng ra
    # hàng xóm còn lại) → tiếp tục tiến đúng hướng mũi; lùi vào (mũi hướng về lối
    # cũ) → tiếp tục lùi (đuôi dẫn, đi đúng sang hàng xóm còn lại, KHÔNG quay lại
    # lối cũ). Tức là GIỮ NGUYÊN last_transit_direction cho mọi node trung chuyển
    # (degree≥2) — mũi xe không tự xoay chỉ vì node có nhiều hàng xóm, nó chỉ xoay
    # khi thực sự rẽ (đã xử lý ở nhánh TURN trong plan builder, không phải ở đây).
    # Chỉ node CỤT/trạm sạc (degree<2, xử lý ở trên + nhánh fallback dưới) mới
    # BẮT BUỘC lật chiều, vì đó là nơi duy nhất không còn lối nào khác ngoài lùi lại.
    try:
        from mqtt_client import map_manager as _mm_deg
        _g_deg = _mm_deg.graph
        if _g_deg.has_node(str(start_node)):
            # QUAN TRỌNG (phát hiện thực tế 2026-10-02): map_manager.graph LUÔN là
            # DiGraph (pathfinding cần tôn trọng chiều đi) — 1 cạnh 2 chiều được add
            # CẢ 2 hướng, nên .degree() cộng gấp đôi: node cụt thật (1 hàng xóm) báo
            # degree=2, trùng với ngưỡng ">=2" lẽ ra chỉ dành cho node trung chuyển
            # thật (≥2 hàng xóm) — khiến node cụt bị NHẬN NHẦM thành trung chuyển,
            # vô hiệu hoàn toàn nhánh "node cụt phải lật chiều" phía dưới. Đếm số
            # hàng xóm KHÁC NHAU thật (không phân biệt chiều cạnh) thay vì degree.
            if _g_deg.is_directed():
                _n_neighbors_deg = len(set(_g_deg.successors(str(start_node)))
                                        | set(_g_deg.predecessors(str(start_node))))
            else:
                _n_neighbors_deg = len(set(_g_deg.neighbors(str(start_node))))
            if _n_neighbors_deg >= 2:
                _state_deg = line_agv_handler.state_store.get(agv_id)
                _last_dir_deg = getattr(_state_deg, 'last_transit_direction', '') if _state_deg else ''
                return _last_dir_deg if _last_dir_deg in ('fwd', 'bwd') else 'fwd'
    except Exception:
        pass
    state = line_agv_handler.state_store.get(agv_id)
    last_dir = getattr(state, 'last_transit_direction', '') if state else ''
    if last_dir == 'bwd':
        return 'fwd'
    if last_dir == 'fwd':
        return 'bwd'
    return 'fwd'   # không có tín hiệu đáng tin (vd chuyến đầu sau restart) → mặc định cũ


# ── ƯỚC TÍNH THỜI GIAN: chờ xe chắn thoát HAY đổi đường vòng? ────────────────────────────
# Quyết định "chờ / đổi đường" phải so THỜI GIAN, không đếm node: đổi đường chỉ đáng khi thời gian đi vòng
# DÔI THÊM nhỏ hơn thời gian phải chờ xe chắn thoát. Xe chắn đang CHẠY và sắp rời đường mình → chờ ngắn → nên
# chờ; xe chắn ĐỖ / đứng chờ xác nhận → chờ lâu → đáng đi vòng nếu vòng không quá xa.
AGV_NOMINAL_SPEED_MPS = float(os.getenv("AGV_NOMINAL_SPEED_MPS", "0.5"))   # tốc độ danh định để đổi m → giây
STATIONARY_WAIT_SEC   = 40.0   # xe chắn đứng yên / sắp đỗ lại: giả định chờ chừng này giây
MOVING_MIN_WAIT_SEC   = 6.0    # xe chắn đang chạy: tối thiểu chờ chừng này giây (1 cạnh)
MOVING_CLEAR_MARGIN_SEC = 4.0  # cộng thêm khi xe chắn đang chạy (khoảng đệm an toàn)
DETOUR_BENEFIT_FACTOR = 0.8    # đi vòng chỉ khi thời gian dôi ≤ 80% thời gian chờ ước tính (có lời rõ ràng)
DETOUR_ALWAYS_OK_SEC  = 6.0    # vòng dôi ≤ chừng này giây (≈ 1 cạnh) thì luôn chấp nhận


def path_length_m(path) -> float:
    """Tổng độ dài (m, theo 'weight' của đồ thị line) của một đường node; lỗi/không có → 0."""
    try:
        from mqtt_client import map_manager as _mm
        g = _mm.line_graph if _mm.line_graph else _mm.graph
        p = [str(n) for n in path]
        return float(sum(g[p[i]][p[i + 1]].get('weight', 1.0) for i in range(len(p) - 1)
                         if g.has_edge(p[i], p[i + 1])))
    except Exception:
        return 0.0


def estimate_clear_wait_sec(blocker_id: str, my_nodes) -> float:
    """Ước tính (giây) xe `blocker_id` mất bao lâu để thoát khỏi vùng `my_nodes` (các node sắp đi của xe mình).
      • đứng yên / không có route / sắp đỗ lại ngay trong vùng của mình → STATIONARY_WAIT_SEC
      • đang chạy rồi rời vùng của mình → thời gian đi hết đoạn còn lại trong vùng + đệm (tối thiểu 1 cạnh)."""
    try:
        st = line_agv_handler.state_store.get(blocker_id)
        reg = traffic_coordinator._registered.get(blocker_id)
        if st is None or reg is None or not getattr(st, 'driving', False):
            return STATIONARY_WAIT_SEC
        path = [str(n) for n in reg.get('path', [])]
        i = reg.get('current_idx', 0)
        mine = {str(n) for n in my_nodes}
        last = -1
        for k in range(i, len(path)):
            if path[k] in mine:
                last = k
        if last < 0:
            return MOVING_MIN_WAIT_SEC
        if last >= len(path) - 1:           # đích của nó nằm trong vùng của mình → nó sẽ ĐỖ lại ở đó
            return STATIONARY_WAIT_SEC
        meters = path_length_m(path[i:last + 2])
        return max(MOVING_MIN_WAIT_SEC, meters / max(AGV_NOMINAL_SPEED_MPS, 0.05) + MOVING_CLEAR_MARGIN_SEC)
    except Exception:
        return STATIONARY_WAIT_SEC


def detour_allowance_sec(wait_sec: float) -> float:
    """Thời gian đi vòng dôi thêm tối đa được chấp nhận khi ước tính phải chờ `wait_sec` giây."""
    return max(DETOUR_ALWAYS_OK_SEC, DETOUR_BENEFIT_FACTOR * wait_sec)


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
        if (_nx.shortest_path_length(graph, str(requester_node), str(dest_node))
                < _nx.shortest_path_length(graph, str(claimer_node), str(dest_node))):
            return True
    except Exception:
        return False
    # Hoà khoảng cách nhưng xe yêu cầu đang đứng NGAY TRÊN đường đã lên kế hoạch của claimer →
    # claimer không thể tới đích nếu requester chờ nó (SIM06@28 ↔ SIM03@26, cùng đích 30, 2026-11-03:
    # SIM03 thắng head-on đợi SIM06 né, SIM06 đợi SIM03 "nhả" đích → kẹt 17 phút).
    try:
        c, r, d = str(claimer_node), str(requester_node), str(dest_node)
        for aid, rt in line_agv_handler._routes.items():
            fp = [str(n) for n in (getattr(rt, 'full_path', None) or [])]
            st = line_agv_handler.state_store.get(aid)
            if (st is not None and st.current_tag is not None and str(st.current_tag) == c
                    and c in fp and d in fp):
                ci = fp.index(c)
                if r in fp[ci + 1:fp.index(d, ci)]:
                    return True
    except Exception:
        pass
    return False


# ═══════════════════════════════════════════════════════════════════════════════
# LineAGVState — snapshot trạng thái 1 Line AGV
# ═══════════════════════════════════════════════════════════════════════════════

def _canon_edge_node(fn, tn):
    """Node TRỌNG TÀI chuẩn của cạnh head-on {fn,tn}: id nhỏ hơn. Cả 2 xe đối đầu
    (mỗi xe thấy cạnh theo chiều ngược nhau) và mọi call-site phải dùng CÙNG node,
    nếu không khoảng-cách-tới-node cho winner khác nhau → cả hai cùng nhường/cùng
    tưởng mình thắng → deadlock."""
    try:
        return fn if int(fn) <= int(tn) else tn
    except (TypeError, ValueError):
        return min(str(fn), str(tn))


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

    # Báo lỗi THẬT từ firmware, đúng giao thức PROTOCOL_GUIDE.md §3 (xác nhận
    # với bên firmware là ĐANG được gửi lên, không phải suy đoán):
    firmware_errors: "list" = field(default_factory=list)   # data["errors"], mỗi
                                        # phần tử {"errorType","errorLevel","errorDescription"}
    estop_state:      str   = "NONE"   # data["safetyState"]["eStop"]: "NONE" | "MANUAL"
    field_violation:  bool  = False    # data["safetyState"]["fieldViolation"]

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

    # TẤT CẢ trạm sạc đang có xe/đã giữ chỗ lúc "Về trạm" được gọi → đã chuyển
    # sang "wait" (xem mqtt_client.send_agv_to_special_target) — CHƯA dùng
    # pending_retry_cmd vì đó bị XOÁ ngay khi driving=True (đúng lúc xe đang
    # lái TỚI điểm chờ) → mất luôn ý định "Về trạm" phải thử lại. Cờ riêng
    # này KHÔNG bị ai xoá trong lúc lái — chỉ main.monitor_charge_station_wait
    # xoá, khi xe đã TỚI điểm chờ VÀ rảnh hẳn (dispatch_or_queue go_charge lại).
    charge_station_wait: bool = False

    # ── Trạng thái ĐÃ NHƯỜNG (yield) — xe THUA đỗ né siding/đi vòng, GIỮ lệnh gốc, CHỜ
    # winner đi qua rồi mới resume (qua _check_waiting_agvs). Tách RIÊNG pending_retry để
    # KHÔNG bị xoá khi xe đang LÁI tới siding (pending_retry bị xoá lúc driving=True).
    yield_cmd:     Optional[str]  = None   # lệnh gốc giữ lại: go_charge|go_wait|go_to
    yield_dest:    Optional[str]  = None
    yield_session: Optional[str]  = None
    yield_winner:  Optional[str]  = None   # xe THẮNG cần chờ đi qua
    yield_park:    Optional[str]  = None   # node siding đích của lượt đỗ né
    yield_path:    "Optional[list]" = None # path gốc (đang conflict) — resume khi winner rời hẳn

    # ── Móc hàng (xe rơ-moóc/đầu kéo) — MỚI ──────────────────────────────────
    hook_state:   Optional[str] = None   # "raised" | "lowered" | None (chưa rõ)
    hook_pending: Optional[str] = None   # "pickup" | "dropoff" | None — đang chờ kết quả nâng/hạ ở đâu
    hook_raise_sent_at:  float = 0.0   # time.monotonic() lúc gửi lệnh móc (nâng/hạ) gần nhất (0 = chưa gửi/đã xong)
    hook_pending_action: Optional[int] = None  # action code (30=NÂNG/31=HẠ) vừa gửi lúc tới node móc —
                                        # dùng để: (1) gửi lại ĐÚNG lệnh khi watchdog retry timeout, (2) biết
                                        # hook_state ĐÍCH cần đạt (30→"raised", 31→"lowered") — cho AGV kéo
                                        # (agv_type='tow') lệnh gửi lúc tới là HẠ (31) thay vì NÂNG (30) như
                                        # rơ-moóc, nên không thể hardcode "raised" như trước nữa.
    hook_lowered_at: float = 0.0  # time.monotonic() lúc hook_lowered (nhả hàng) gần nhất, 0 = chưa có —
                                    # dùng để trì hoãn bước "deba" xác nhận vị trí (mqtt_client._start_
                                    # locate_then_charge) 1 nhịp ngắn khi Về trạm được dispatch ngay sau khi
                                    # vừa nhả hàng, phòng xe hàng vừa nhả còn chắn ngay trước đầu AGV.
    locate_then_charge_auto_retries: int = 0  # số lần mqtt_client._locate_then_charge_loop_coro đã TỰ
                                    # huỷ+gọi lại "Về trạm" do "deba" đứng im hẳn (driving chưa từng
                                    # =True) — reset về 0 ngay khi 1 lượt dò vị trí thành công.
    hook_raise_retries:  int   = 0     # số lần đã gửi lại do không thấy phản hồi
    hook_report_seq_seen: int  = 0     # hook_report_seq mới nhất đã xử lý (dedupe — firmware lặp lại report mỗi
                                        # gói state cho tới khi ACK, tránh xử lý trùng)
    hook_fallback_notified: bool = False  # đã báo lỗi móc qua kênh "hook" (up_fail/dn_fail) cho đợt hiện tại
                                           # chưa — tránh gọi lại _notify_hook_error mỗi 1.5s khi còn kẹt
    hook_prearmed_for: Optional[str] = None  # AGV kéo (tow): tag đích lấy hàng đã được NÂNG MÓC TRƯỚC 1 node
                                        # (xem _maybe_preraise_tow_hook) — khi xe THẬT SỰ tới đúng tag này,
                                        # _handle_trailer_hook_arrival biết móc đã nâng sẵn, bỏ qua bước
                                        # nâng/hạ lại, đi thẳng vào chờ xác nhận thủ công duy nhất

    # ── Chạy thử thủ công đến 1 tag (không cần map) — MỚI ────────────────────
    test_drive_target: Optional[str] = None   # tag cần dừng khi tới, None = không có chạy thử đang chờ
    test_drive_seq:    int = 0   # tăng mỗi lần bắt đầu chạy thử mới — vòng lặp gửi lại "deba" cũ tự thoát khi lệch seq

    # ── Dò vị trí bằng deba trước khi Về trạm (xe mất vị trí do bị đẩy tay/mới bật) ──
    locate_then_charge_seq: int = 0   # tăng mỗi lần bắt đầu dò vị trí mới — vòng lặp cũ tự thoát khi lệch seq
    # Thẻ xe VỪA TỚI theo event arrived_wait_* (firmware tự đọc thẻ → vị trí chắc chắn). None khi xe đã được gửi plan/stop/deba mới
    # (đang/đã di chuyển) → lệnh Về trạm chỉ bỏ qua bước dò vị trí (deba) khi thẻ hiện tại còn trùng thẻ này.
    position_confirmed_tag: Optional[str] = None

    # ── Lidar khi lái thủ công (D-pad / Chạy thử đến node) — MỚI ─────────────
    manual_lidar_off: Optional[bool] = None   # trạng thái Lidar đã gửi lần gần nhất khi lái thủ công (None = chưa rõ)

    # ── Cảnh báo hệ thống đang hiển thị (map/UI) — MỚI ───────────────────────
    # {"kind": str, "message": str, "since": float} | None — set tại ĐÚNG các
    # điểm đã có sẵn cảnh báo Telegram (xem _set_alert/_clear_alert), KHÔNG
    # thêm ngưỡng phát hiện mới. Tự clear khi hệ thống thấy đã ổn (xe di
    # chuyển lại được, hoặc đợt lỗi mới bắt đầu thay đợt cũ).
    active_alert: Optional[dict] = None

    # ── Xe MA: mất tín hiệu (wifi) lúc đang có lệnh/đang chạy → vẫn nằm trên đường ──
    # ghost=True: vẫn chiếm node last-known + tới cuối cửa sổ đã gửi (ghost_nodes) và vẫn
    # hiện trên map (mờ). Chỉ hết khi xe online lại ổn định hoặc người vận hành gỡ.
    ghost:        bool       = False
    ghost_since:  float      = 0.0
    ghost_nodes:  "list"     = field(default_factory=list)
    offline_decided: bool    = False   # monitor_line_offline đã quyết ma/ẩn cho đợt offline này
    online_streak: int       = 0       # số lượt kiểm tra online liên tiếp (chống wifi chập chờn)
    # id lệnh hàng đợi đang chạy lúc xe mất tín hiệu → khi xe online lại mà lệnh đó còn dang dở (không còn route để
    # tiếp tục) thì dựng lại từ vị trí thật (resume_after_offline). Rỗng = không có lệnh nào cần khôi phục.
    resume_cmd_id: "Optional[str]" = None
    # True khi đã nhận ít nhất 1 gói state THẬT từ xe kể từ lúc server khởi động. override_position() (khôi phục last_tag từ DB,
    # đặt vị trí tay) KHÔNG đặt cờ này — vị trí đó có thể đã cũ (vd xe im lặng trong cabin) nên không được dùng để chạy tiếp lệnh.
    real_state_seen: bool = False
    # Plan vừa gửi BẮT ĐẦU bằng cú RẼ tại ĐÚNG thẻ xe đang đứng (rẽ tại chỗ, vd node 30 → 7 vào thang): theo dõi để phát hiện xe
    # LĂN THẲNG trước khi rẽ (xem arm_standing_turn / _check_standing_turn). None = không theo dõi.
    standing_turn: "Optional[dict]" = None


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

STANDING_TURN_GUARD = os.getenv("STANDING_TURN_GUARD", "1").strip().lower() not in ("0", "false", "no", "off")
STANDING_TURN_ROLL_S = 1.5          # xe lăn (driving) liên tục chừng này mà chưa có turn_busy → coi là lăn thẳng
STANDING_TURN_WATCH_S = 25.0        # chỉ theo dõi chừng này giây sau khi gửi plan
STANDING_TURN_RESEND_S = 2.5        # chờ xe dừng hẳn rồi gửi lại plan
STANDING_TURN_MAX_RETRIES = 2
LINE_STATE_STALE_SEC = 20.0   # cùng ngưỡng main.LINE_OFFLINE_THRESHOLD_SEC


def line_state_online(st) -> bool:
    """Xe còn online thật: connection ONLINE và state message mới trong LINE_STATE_STALE_SEC."""
    if st is None or st.last_update <= 0:
        return False
    if st.connection_state != "ONLINE":
        return False
    return (time.time() - st.last_update) <= LINE_STATE_STALE_SEC


def line_state_present(st) -> bool:
    """Xe CÓ MẶT trên đường: online, hoặc là xe ma (mất tín hiệu khi đang chạy)."""
    return st is not None and (st.ghost or line_state_online(st))


class _OnlineStatesDict(dict):
    """dict {agv_id: LineAGVState} mà items()/values() CHỈ trả xe có mặt trên đường
    (online hoặc xe ma).

    Xe offline thường coi như không tồn tại trên bản đồ: không chiếm node/cạnh, không
    tham gia nhường đường/kiểm tra va chạm. get()/[]/in vẫn trả đủ để ghi state
    và xử lý kết nối lại; muốn duyệt cả xe offline dùng raw_items()."""

    def items(self):
        return [(k, v) for k, v in dict.items(self) if line_state_present(v)]

    def values(self):
        return [v for v in dict.values(self) if line_state_present(v)]

    def raw_items(self):
        return list(dict.items(self))


class LineAGVStateStore:
    def __init__(self):
        self._states: dict[str, LineAGVState] = _OnlineStatesDict()

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
        for _, s in self._states.raw_items():
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
# Ghi xuyên DB (persistent_flags): khôi phục được sau khi server khởi động lại giữa chừng.
from persistent_flags import PersistentPairSet as _PPS
_pending_empty_pickup_legs = _PPS("empty_pickup")   # set[(agv_id, node)]

# ── Chặng "lấy hàng đầy nhiều Tổ trong 1 chuyến" (milk run) — điểm KHÔNG phải
# Tổ gần nhất (không móc cơ khí, chỉ dừng chờ xác nhận thủ công vì hàng được
# công nhân chuyển tay từ xe của Tổ đó sang xe đang kéo theo AGV). Đánh dấu
# tại DISPATCH TIME (agv_id, node_id) để arrival handler BỎ QUA hoàn toàn logic
# móc (mặc định mọi node trailer_role='pickup' đều tự vào luồng móc) — rơi
# xuống nhánh "chờ xác nhận" giống hệt AGV carry. Dùng 1 lần rồi bỏ đánh dấu.
_pending_confirm_only_legs = _PPS("confirm_only")   # set[(agv_id, node)]


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

    if agv_type in ('trailer', 'tow') and agv_registry.op_mode(agv_id) == 'roundtrip':
        # (carry_hook / carry_fixed: đi thẳng tới node Tổ như xe chở — nhánh else)
        # AGV kéo ('tow') chạy CHUNG chu trình 4 chặng với rơ-moóc — cùng quy
        # trình lấy rỗng → thả ở Tổ → lấy đầy → staging, chỉ khác hướng lệnh
        # nâng/hạ móc (xử lý riêng trong line_agv_handler._handle_trailer_hook_arrival).
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

    OSC_CARRY_SEC = 240.0   # cửa sổ nhớ node đã qua để nhận ra xe lật qua lại

    def __init__(self):
        # {agv_id: {'path': list[str], 'direction': str, 'task_type': str,
        #           'current_idx': int, 'priority': int, 'registered_at': float}}
        self._registered: dict[str, dict] = {}
        self._offline_saved: dict[str, dict] = {}   # _registered của xe đang offline (xem suspend_offline)
        # Lịch sử đến node + mốc "tiến thật" (node MỚI) của từng xe — sống qua register/deregister để
        # phát hiện xe lật qua lại 2 node (xem update_position). {agv: {'hist': [(tag, ts)], 'real_ts', 'osc'}}
        self._progress: dict[str, dict] = {}
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
        # ── CHỐNG DAO ĐỘNG đỗ-né HEAD-ON tại dispatch (main.py) ──────────────
        # PHÁT HIỆN THỰC TẾ (2026-09-23): mỗi lần AGV "đến" node đỗ-né (parking)
        # xong, main.py dispatch lại y hệt đích cũ → nếu HEAD-ON vẫn còn (xe kia
        # chưa kịp rời), find_parking_node() được gọi LẠI và có thể chọn NGƯỢC
        # LẠI đúng node vừa rời (do "came_from" đảo chiều theo hướng vừa tới) →
        # xe bị bắt đi tới lui liên tục giữa 2 node đỗ-né sát nhau (vd 31↔106),
        # 3 lần dispatch chỉ trong ~4 giây, rồi đứng im hẳn (có thể làm firmware
        # rối loạn không phản hồi). FIX: nếu vừa đỗ-né head-on với ĐÚNG xe đó
        # trong PARKING_COOLDOWN giây → không đỗ-né tiếp, để dispatch rơi xuống
        # nhánh "dừng chờ tại chỗ" (không di chuyển) cho tới khi xe kia rời hẳn.
        self._parking_ts: dict[str, tuple[float, str]] = {}  # agv_id -> (ts, other_agv_id)
        # Chống gửi 2 xe cùng lúc vào node chờ / gọi lại liên tục mỗi vài giây khi
        # watchdog tick cho từng xe (xem check_global_stall() + main._dispatch_to_waiting_node).
        self._last_stall_dispatch_ts: float = 0.0

    def set_intent_route(self, agv_id: str, full_path: list) -> None:
        """Ghi tuyến ĐẦY ĐỦ tới đích cuối (cho penalty routing của xe khác)."""
        if full_path and len(full_path) >= 2:
            self._intent_route[agv_id] = [str(n) for n in full_path]

    def check_global_stall(self) -> Optional[list[str]]:
        """Phát hiện TOÀN HỆ THỐNG bí (N xe, không chỉ 2 xe khoá chéo nhau như
        _is_deadlocked_with) — dùng để kích hoạt tính năng "node chờ" (xem
        main._dispatch_to_waiting_node). Chỉ xét các xe đang `_registered` (đang
        di chuyển dở trong traffic) — xe đang đứng chờ xác nhận HMI/sạc đã
        `deregister()` từ trước nên không bị tính nhầm là "bí".

        Trả về danh sách agv_id đang bí (TẤT CẢ xe active đều không nhích được
        quá GLOBAL_STALL_SEC giây) nếu có ≥2 xe active; None nếu hệ thống vẫn còn
        ít nhất 1 xe tiến được (không phải bí do giao thông) hoặc chưa đủ 2 xe để
        gọi là "kẹt lẫn nhau".
        """
        if len(self._registered) < 2:
            return None
        now = time.monotonic()
        stalled = [aid for aid, r in self._registered.items()
                   if now - r.get('last_progress_ts', now) > GLOBAL_STALL_SEC]
        if len(stalled) < len(self._registered):
            return None
        # Chống gọi lại liên tục mỗi vài giây trong khi 1 lượt "đi vào node chờ"
        # đã được kích hoạt và còn đang xử lý (chưa kịp giải toả bế tắc).
        if now - self._last_stall_dispatch_ts < GLOBAL_STALL_SEC:
            return None
        self._last_stall_dispatch_ts = now
        return stalled

    def find_stall_cycles(self, stall_threshold_sec: float) -> list[list[str]]:
        """Dò CHU TRÌNH chờ-nhau giữa NHIỀU xe (≥2, không chỉ 2 xe khoá chéo
        TRỰC TIẾP như _is_deadlocked_with) — vd A chờ node do B giữ, B chờ node
        do C giữ, C chờ lại node do A giữ: không xe nào thấy mình khoá chéo
        TRỰC TIẾP với ai nên các nhánh né/lùi tại-điểm (chỉ biết "ai đang chặn
        TÔI") không tự phá được cả vòng. KHÁC check_global_stall() (yêu cầu
        TẤT CẢ xe active đều bí mới coi là bí) — ở đây chỉ cần ĐÚNG các xe
        trong chu trình bí, các xe khác vẫn chạy bình thường (đúng ca mô
        phỏng 15 xe: 1 vòng 3-4 xe kẹt dây chuyền >300s dù 11 xe khác vẫn
        chạy tốt). Chỉ xét xe đã đứng im (last_progress_ts) quá
        stall_threshold_sec VÀ đang có route đăng ký.

        Trả về list các chu trình tìm được, mỗi chu trình là list agv_id theo
        thứ tự chờ nhau (vd [A, B, C] nghĩa là A chờ B, B chờ C, C chờ lại A).
        """
        now = time.monotonic()
        stalled = {aid for aid, r in self._registered.items()
                   if now - r.get('last_progress_ts', now) > stall_threshold_sec}
        if len(stalled) < 2:
            return []

        def _blocked_by(aid: str) -> Optional[str]:
            # PHÁT HIỆN THỰC TẾ (mô phỏng 15 xe, 2026-10-10, lần 2): chỉ xét
            # ĐÚNG node kế tiếp (ci+1) bỏ lọt hầu hết ca thật — xung đột
            # thường nằm xa hơn 1 node trong TRAFFIC_LOOKAHEAD (giống cách
            # _find_upcoming_conflict quét), nên "ai chặn tôi" bị tính SAI
            # thành None (coi như không ai chặn) → chu trình thật không được
            # nhận ra. Quét CẢ cửa sổ lookahead, lấy xe đầu tiên đang giữ 1
            # node trong đó — khớp đúng phạm vi mà hệ thống dùng để báo
            # "khoá (ngã rẽ/cùng chiều)"/"head-on" ở nơi khác.
            r = self._registered.get(aid)
            if not r:
                return None
            path, ci = r['path'], r.get('current_idx', 0)
            for j in range(ci + 1, min(ci + 1 + TRAFFIC_LOOKAHEAD, len(path))):
                owner = self.node_reserved_by_other(aid, path[j])
                if owner:
                    return owner
            return None

        # TẤT CẢ xe chặn trong cửa sổ lookahead (không chỉ xe đầu tiên): nếu xe chặn đầu tiên là xe
        # chưa "bí" thì chuỗi cũ đứt, dù xe chặn thứ hai mới là bên khoá chéo thật (mô phỏng 2026-10-29:
        # SIM01@48 ↔ SIM06@16 kẹt ~270s mà không được nhận là chu trình).
        def _blockers(aid: str) -> list[str]:
            r = self._registered.get(aid)
            if not r:
                return []
            path, ci = r['path'], r.get('current_idx', 0)
            out: list[str] = []
            for j in range(ci + 1, min(ci + 1 + TRAFFIC_LOOKAHEAD, len(path))):
                owner = self.node_reserved_by_other(aid, path[j])
                if owner and owner in stalled and owner not in out:
                    out.append(owner)
            return out

        cycles: list[list[str]] = []
        resolved: set[str] = set()
        for start in sorted(stalled):
            if start in resolved:
                continue
            # DFS tìm vòng quay về start (chỉ đi qua xe đang bí)
            stack = [(start, [start])]
            seen: set[str] = set()
            while stack:
                cur, chain = stack.pop()
                for nxt in _blockers(cur):
                    if nxt == start and len(chain) >= 2:
                        cycles.append(chain)
                        resolved.update(chain)
                        stack = []
                        break
                    if nxt not in seen and nxt not in chain and len(chain) < 8:
                        seen.add(nxt)
                        stack.append((nxt, chain + [nxt]))
        return cycles

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
            'path':            [str(n) for n in path],
            'direction':       direction,
            'task_type':       task_type,
            'current_idx':     0,
            'priority':        self.PRIORITY.get(task_type, 2),
            'registered_at':   time.time(),
            # Mốc thời gian lần cuối xe THỰC SỰ nhích (current_idx đổi) — dùng để
            # phát hiện "đứng im quá lâu" cho cả STALL_BYPASS_SEC (vá cooldown tự
            # bẫy) và GLOBAL_STALL_SEC (node chờ). Khởi tạo = lúc đăng ký (coi như
            # "mới nhích" để không bị bypass/trigger oan ngay khi vừa dispatch).
            'last_progress_ts': time.monotonic(),
        }
        # Xe đang LẬT qua lại (replan liên tục làm register lại) → KHÔNG reset mốc đứng im, nếu không
        # _force_yield_long_stalls/stall-cycle không bao giờ thấy xe này "đứng im".
        _pg = self._progress.get(agv_id)
        if _pg and _pg.get('osc') and time.monotonic() - _pg.get('real_ts', 0.0) < self.OSC_CARRY_SEC:
            self._registered[agv_id]['last_progress_ts'] = _pg['real_ts']
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
                _old_tag = r['path'][r['current_idx']] if r['current_idx'] < len(r['path']) else None
                r['current_idx'] = new_idx
                # "Tiến" chỉ tính khi tới node MỚI. Quay lại node vừa qua (A→B→A, replan lật nhánh)
                # không phải tiến: mô phỏng 2026-10-29 SIM01 lật 22↔33 mỗi 6s suốt 8 phút, mỗi lần
                # đều "tiến" nên không bị ép nhường, trong khi chặn SIM05/SIM03/SIM02 đứng im >5 phút.
                now = time.monotonic()
                pg = self._progress.setdefault(agv_id, {'hist': [], 'real_ts': now, 'osc': False})
                pg['hist'] = [(t, ts) for t, ts in pg['hist'] if now - ts < self.OSC_CARRY_SEC][-3:]
                if _old_tag is not None and not any(t == _old_tag for t, _ in pg['hist']):
                    pg['hist'].append((_old_tag, now))   # node vừa rời cũng là "đã qua" (seed cho A→B→A)
                if str(tag) in {t for t, _ in pg['hist']}:
                    pg['osc'] = True
                else:
                    pg['osc'] = False
                    pg['real_ts'] = now
                    r['last_progress_ts'] = now
                pg['hist'].append((str(tag), now))
        except ValueError:
            pass
        # Cập nhật giữ chỗ: nhả node đã qua, khoá node phía trước.
        self.reserve_ahead(agv_id)

    def suspend_offline(self, agv_id: str) -> None:
        """Xe offline = không tồn tại: nhả mọi giữ chỗ node/cạnh/block và bỏ khỏi
        _registered (cất lại để khôi phục khi xe online trở lại)."""
        r = self._registered.pop(agv_id, None)
        if r is not None:
            self._offline_saved[agv_id] = r
        self._release_reservations(agv_id)
        self._release_edges(agv_id)
        self._release_blocks(agv_id)

    def hold_ghost(self, agv_id: str, nodes: list) -> None:
        """Xe MA: giữ chỗ đúng `nodes` (vị trí cuối + tới cuối cửa sổ đã gửi), cắt path đã
        đăng ký ở đó để không giữ chỗ phần route xe chưa được phép đi. Cất path đầy đủ."""
        r = self._registered.get(agv_id)
        if r is not None:
            self._offline_saved.setdefault(agv_id, dict(r, path=list(r['path'])))
            cut = [n for n in r['path'] if n in set(nodes)]
            if cut:
                last = max(r['path'].index(n) for n in cut)
                r['path'] = r['path'][:last + 1]
        for n in nodes:
            self._reserve_node(agv_id, str(n))

    def resume_online(self, agv_id: str) -> None:
        r = self._offline_saved.pop(agv_id, None)
        if r is not None:
            self._registered[agv_id] = r
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
                # ── NGÁCH CỤT (pocket): node cụt + hành lang hẹp dẫn vào nó, tính trên đồ thị VÔ HƯỚNG ──────────────
                # Xe đỗ trong ngõ cụt chỉ ra được qua hành lang này; xe khác vào hành lang khi trong ngõ cụt còn xe sẽ
                # khoá cứng nhau (mô phỏng 2026-11-04: SIM06 ở 10, rơ-moóc SIM03 vào 73 → kẹt 38+ phút). Đồ thị đường là
                # có hướng (degree = vào+ra) nên chuỗi 2 chiều như 73-10 không lọt vào auto-block bậc-2 ở trên.
                try:
                    _ug = g.to_undirected() if hasattr(g, 'to_undirected') else g
                    for _dead in [str(n) for n in _ug.nodes() if _ug.degree(n) == 1]:
                        if _dead in bon or _dead in {x for v in bn.values() for x in v}:
                            continue
                        _pocket, _prev, _cur = [_dead], None, _dead
                        while True:
                            _nxt = [str(x) for x in _ug.neighbors(_cur) if str(x) != _prev]
                            if len(_nxt) != 1:
                                break
                            _nx = _nxt[0]
                            if _ug.degree(_nx) != 2 or _nx in bon or _nx in _pocket:
                                break
                            _pocket.append(_nx); _prev, _cur = _cur, _nx
                        if len(_pocket) >= 2:
                            _bid = 'auto_pocket_' + _dead
                            bt[_bid] = 'single'
                            for _pn in _pocket:
                                bon[_pn] = _bid
                                bn.setdefault(_bid, set()).add(_pn)
                except Exception as _e_pk:
                    print(f"[TRAFFIC] auto-block ngách cụt lỗi: {_e_pk}")
                if any(k.startswith('auto_') for k in bn):
                    print(f"[TRAFFIC] auto-block đường đơn: "
                          f"{ {k: sorted(v) for k, v in bn.items() if k.startswith('auto_')} }")
        except Exception as _e_ab:
            print(f"[TRAFFIC] auto-block lỗi: {_e_ab}")

        self._block_of_node, self._block_nodes, self._block_type = bon, bn, bt

    def _single_block_blocked_by_other(self, block_id: str, agv_id: str) -> bool:
        """SINGLE block: có node nào của block đang bị xe KHÁC khoá, HOẶC có xe khác đang ĐỨNG VẬT LÝ trong block?
        Xe đỗ/đứng chờ (chưa đăng ký route nên không có khoá) vẫn chặn hành lang 1 làn: xe vào sau sẽ đụng đầu nhau
        trong đó (mô phỏng 2026-11-04: SIM04 đỗ ở 73 (ngách 73-27-28), rơ-moóc SIM03 vẫn đi vào tới 28 → kẹt 10+ phút)."""
        nodes = {str(b) for b in self._block_nodes.get(block_id, ())}
        for bn in nodes:  # noqa
            owner = self._node_res.get(bn)
            if owner and owner != agv_id and owner in self._registered:
                return True
        for oid, st in line_agv_handler.state_store._states.items():
            if (oid != agv_id and st is not None and st.current_tag is not None
                    and str(st.current_tag) in nodes):
                return True
        return False

    def _reserve_node(self, agv_id: str, n: str) -> bool:
        """Thử khoá 1 node cho agv_id. True nếu được (trống/của mình/thắng arbiter &
        chủ chưa cam kết & chủ KHÔNG đang đứng tại node), False nếu phải dừng trước."""
        if self._in_elev_zone(n):
            return True          # vùng thang (cabin + điểm chờ/thoát): thang tự khóa vùng, không khóa node theo giao thông
        owner = self._node_res.get(n)
        if owner == agv_id:
            return True
        if owner is None:
            # Node trống nhưng xe KHÁC (đang chạy lệnh) đang đứng vật lý ở đó → không giữ chỗ được.
            for oid in self._registered:
                if oid != agv_id and self._owner_at_node(oid, n):
                    return False
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

    def _agv_inside_block(self, agv_id: str, block_id: str) -> bool:
        """agv_id đang đứng vật lý tại 1 node của block?"""
        try:
            st = line_agv_handler.state_store.get(agv_id)
            return bool(st and st.current_tag is not None
                        and str(st.current_tag) in {str(b) for b in self._block_nodes.get(block_id, ())})
        except Exception:
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
        # Xe KHÔNG lùi được (rơ-moóc/đầu kéo, đã móc hàng không quay đầu được) KHÔNG có cách né
        # (không lùi, không đổi nhánh trên đường một chiều) → phải LUÔN là bên THẮNG (ưu tiên số 1, trên cả điểm lấy/giao hàng và ưu tiên lệnh); xe lùi/đổi nhánh
        # được sẽ nhường. Nếu xếp xe này thua thì cả hai cùng đứng chờ nhau (thắng chờ thua né) =
        # kẹt vĩnh viễn. Hàm vẫn THUẦN & ĐỐI XỨNG (chỉ phụ thuộc thuộc tính xe).
        try:
            _ca = agv_registry.can_reverse(a)
            _cb = agv_registry.can_reverse(b)
            if _ca != _cb:
                return b if _ca else a
        except Exception:
            pass
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
                if btype == 'single' and self._agv_inside_block(agv_id, block_id):
                    # Xe ĐÃ ĐỨNG TRONG block: không khoá cả block (sẽ cướp node của xe khác đang đứng chung
                    # block, vd rơ-moóc ở 19 khoá luôn 20/21 của đầu kéo đứng ở 20 → cả hai chờ nhau mãi,
                    # mô phỏng 2026-11-02) mà giữ chỗ từng node như node thường.
                    if not self._reserve_node(agv_id, n):
                        break
                elif btype == 'single':
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

    def reserved_extent_lenient(self, agv_id: str, path: list, from_idx: int,
                                 hard_end: int) -> int:
        """Giống reserved_extent() nhưng thêm khoan nhượng theo KHOẢNG CÁCH THẬT,
        dùng CHUNG hằng số/nguyên tắc đã có ở _find_upcoming_conflict
        (JUNCTION_SAFE_NODE_GAP) thay vì bịa ngưỡng mới.

        PHÁT HIỆN THỰC TẾ (2026-09-24): reserved_extent() gốc cắt cứng ngay khi
        node kế bị AGV KHÁC giữ chỗ (reserve_ahead), HOÀN TOÀN không biết chủ khoá
        đang cách bao xa — trong khi _find_upcoming_conflict() (quyết định có nên
        coi là "conflict" hay không) ĐÃ có khoan nhượng theo khoảng cách thật y hệt
        yêu cầu người dùng: "xe kia còn cách xa (>= JUNCTION_SAFE_NODE_GAP node)
        thì cứ đi tiếp, chỉ dừng khi thật sự gần nhau". Vì reserved_extent() chạy
        ĐỘC LẬP (ở set_route/_send_window) và cắt SAU/không hay biết quyết định
        "an toàn, đi tiếp" mà _find_upcoming_conflict vừa đưa ra, nó ÂM THẦM GHI
        ĐÈ về window=[x→x] (đứng yên) — xe kẹt cứng dù xe giữ chỗ còn cách rất xa
        (đúng log thực tế: AGV03 đứng hình >2 phút tại node 16, dù chính log in ra
        "còn cách 3 node ... CHƯA cần chờ, đi tiếp" ngay trước khi vẫn bị cắt về
        [3→3]).

        An toàn: KHÔNG đụng gì tới _node_res thật (không tự cấp/cướp khoá) — chỉ
        nới lỏng quyết định "cắt window ở đâu". Khi chủ khoá KHÔNG đủ xa (hoặc
        không xác định được khoảng cách) → cắt cứng y hệt reserved_extent() gốc,
        giữ nguyên toàn bộ an toàn hiện có.
        """
        end = from_idx
        _cap = min(hard_end, len(path) - 1)
        for k in range(from_idx, _cap + 1):
            node  = str(path[k])
            owner = self._node_res.get(node)
            if owner is None or owner == agv_id:
                end = k
                continue
            if owner not in self._registered:
                end = k   # khoá mồ côi (chủ đã offline/xong) → coi như trống
                continue
            _owner_reg  = self._registered.get(owner, {})
            _owner_path = [str(n) for n in _owner_reg.get('path', [])]
            _owner_idx  = _owner_reg.get('current_idx', 0)
            _safe_far = False
            if _owner_path and not self._is_junction(node):
                try:
                    _tn_idx_owner = _owner_path.index(node, _owner_idx)
                    _safe_far = (_tn_idx_owner - _owner_idx) >= JUNCTION_SAFE_NODE_GAP
                except ValueError:
                    pass
            if _safe_far:
                end = k   # chủ khoá còn xa (>= ngưỡng an toàn) → coi như trống
                continue
            break   # chủ khoá đang ở gần / không rõ khoảng cách → dừng an toàn tại đây
        return end

    @staticmethod
    def _in_elev_zone(node) -> bool:
        """Node thuộc vùng thang (cabin / điểm chờ / mốc thoát khai báo trong Map Editor)?"""
        try:
            from mqtt_client import map_manager as _mm_z
            z = getattr(_mm_z, "elev_zone", None)
            return isinstance(z, (set, frozenset)) and str(node) in z
        except Exception:
            return False

    def _is_junction(self, node: str) -> bool:
        """
        Node có phải NÚT GIAO cần khoá độc quyền không — tự suy TỪ CẤU TRÚC ĐỒ THỊ
        (bậc/degree ≥3, tức ≥3 cạnh nối — nơi ≥2 luồng xe khác nhau có thể thật sự
        cắt nhau), KHÔNG cấu hình tay theo từng map (map nào cũng tự áp dụng y hệt,
        không cần biết trước layout).

        PHÁT HIỆN THỰC TẾ (2026-09-24, va chạm vật lý AGV03/AGV04 tại node 15): các
        khoan nhượng "chủ khoá còn xa (ước lượng qua ETA/số node) → cứ đi tiếp" (xem
        reserved_extent_lenient(), _find_upcoming_conflict()) AN TOÀN cho hành lang
        thẳng (rủi ro cắt nhau thấp) nhưng KHÔNG đủ an toàn tại nút giao nhiều nhánh —
        định vị chỉ qua RFID rời rạc nên ước lượng ETA có thể sai lệch đúng lúc 2 xe
        cùng hội tụ vào 1 điểm. Node nào có degree≥3 → BỎ QUA mọi khoan nhượng
        ETA/số-node, luôn coi reservation là chặn cứng (y hệt reserved_extent() gốc,
        không lenient) — cơ chế chung, không phải "vùng cấm" khai báo tay cho map cụ
        thể, nên áp dụng như nhau dù map có 3 hay 30 node giao nhau, dù đội có 3 hay
        30 xe.
        """
        try:
            from mqtt_client import map_manager as _mm_j
            if self._in_elev_zone(node):
                return False                      # vùng thang không phải nút giao của giao thông
            g = _mm_j.line_graph if _mm_j.line_graph else _mm_j.graph
            return bool(g is not None and g.has_node(str(node)) and g.degree(str(node)) >= 3)
        except Exception:
            return False

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

    def _eta_to_node(self, other_id: str, node: str) -> Optional[float]:
        """Ước lượng thời gian (giây) xe other_id cần để ĐẾN node, dựa trên khoảng
        cách thật + tốc độ từng cạnh trên đường ĐÃ ĐĂNG KÝ của nó (xem
        _estimate_travel_seconds) — dùng để phân biệt "xe kia sắp tới" (mối đe doạ
        thật, nên chặn/né) với "xe kia còn rất xa, đang bận việc khác" (chưa cần
        chặn ngay, sẽ re-check khi nó tới gần hơn). None nếu không tính được (node
        không nằm phía trước trong route đã đăng ký, hoặc thiếu graph)."""
        r = self._registered.get(other_id)
        if not r:
            return None
        path = r.get('path') or []
        cur_idx = r.get('current_idx', 0)
        try:
            node_idx = path.index(str(node), cur_idx)
        except ValueError:
            return None
        base_t = _estimate_travel_seconds(path, cur_idx, node_idx)
        if base_t is None:
            return None
        # register() luôn khởi tạo current_idx=0 (coi xe ĐÃ Ở path[0]) — nhưng route
        # mới có thể được đăng ký ngay khi xe VẪN ĐANG CHẠY trên cạnh cuối của đoạn
        # TRƯỚC dẫn tới path[0] (vd vừa xác nhận xong tại 1 node rồi dispatch tiếp
        # trong khi "current_tag" phần mềm cập nhật SỚM HƠN lúc xe vật lý thực sự tới
        # nơi — phát hiện thực tế 2026-09-18: AGV đăng ký path=['98',...] trong khi
        # vẫn còn giữ edge-lock VẬT LÝ '6_to_98' nhiều chục giây sau đó). update_position()
        # chưa kịp sửa current_idx vì '6' không nằm trong path mới → ETA bị tính THIẾU
        # hẳn đoạn 6→98, khiến xe kia trông như "sắp tới" dù còn rất xa. Grounded lại
        # bằng edge-lock VẬT LÝ THẬT (_line_blocked_edges, cập nhật theo sự kiện tag
        # thật của xe) — chỉ áp dụng khi cur_idx==0 (chưa có xác nhận vị trí nào trong
        # path này) và xe đang thực giữ 1 cạnh dẫn TỚI đúng path[0].
        if cur_idx == 0 and path:
            anchor = str(path[0])
            for eid, holder in _line_blocked_edges.items():
                if holder != other_id:
                    continue
                _f, _sep, _t = eid.partition('_to_')
                if _sep and _t == anchor and _f != anchor:
                    _extra = _estimate_travel_seconds([_f, _t], 0, 1)
                    if _extra is not None:
                        base_t += _extra
                    break
        return base_t

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
                # Ghi nhận xe đứng yên đang CHẶN đường xe khác (cho _evict_idle_blockers).
                try:
                    _ib = self.__dict__.setdefault('_idle_blocked', {})
                    _e = _ib.get(s_agv)
                    _nowb = time.monotonic()
                    _tg = str(line_agv_handler.state_store.get(s_agv).current_tag)
                    # Xe bị chặn chỉ đánh giá lại mỗi vài chục giây–2 phút → cửa sổ 300s.
                    if (not _e) or _nowb - _e['last'] > 300.0 or _e['blocked'] != agv_id                             or _e.get('tag') != _tg:
                        _e = {'blocked': agv_id, 'first': _nowb, 'last': _nowb, 'tag': _tg}
                    _e['last'] = _nowb
                    _e['path'] = list(path)
                    _ib[s_agv] = _e
                except Exception:
                    pass
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

    @_agv_scoped
    def find_flexible_parking(
        self, agv_id: str, current_node: str,
        conflict_path: list[str], max_hops: int = 3,
        extra_blocked: Optional[set] = None,
        relaxed: bool = False,
    ) -> Optional[str]:
        """
        BFS từ current_node tìm node đỗ xe linh hoạt:
        - Không nằm trên conflict_path (vùng tranh chấp)
        - Không bị xe khác chiếm
        - Ưu tiên: locationType=WAITING > ít kết nối (side branch)
        Không phân biệt hướng tiến/lùi — AGV sẽ tự tính hướng khi được dispatch.

        relaxed=True (dùng cho ÉP NHƯỜNG sau khi đã kẹt lâu): chỉ coi là "bị chiếm" các node đang CÓ XE ĐỨNG,
        KHÔNG loại cả đường tương lai của mọi xe khác. Chế độ thường loại hết đường tương lai của xe khác nên ở
        ngã ba đông xe mọi hướng thoát đều "nằm trên đường ai đó" → BFS không đi qua được → không có chỗ đỗ → kẹt
        hàng chục phút (mô phỏng 2026-10-29: SIM05 tại 21 kẹt 30 phút dù 22/33 vật lý trống).
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
        others_future: set[str] = set()     # chỉ dùng ở relaxed: ưu tiên chỗ đỗ KHÔNG nằm trên đường xe khác
        if relaxed:
            for oid, ost in line_agv_handler.state_store._states.items():
                if oid != agv_id and ost is not None and ost.current_tag is not None:
                    occupied.add(str(ost.current_tag))
            for oid, r in self._registered.items():
                if oid != agv_id:
                    others_future.update(str(n) for n in r['path'][r.get('current_idx', 0):])
        else:
            for oid, r in self._registered.items():
                if oid == agv_id:
                    continue
                cur = r.get('current_idx', 0)
                occupied.update(r['path'][cur:])

        from collections import deque
        visited   = {str(current_node)}
        queue     = deque([(str(current_node), 0)])
        candidates: list[tuple] = []
        charger_cands: list[tuple] = []     # DỰ PHÒNG: trạm sạc làm điểm né khi hết chỗ khác
        # Đi sâu hơn max_hops CHỈ để tìm trạm sạc dự phòng; chỗ đỗ thường vẫn giới hạn max_hops.
        depth_limit = max(max_hops, 6)
        _busy_ch = None

        while queue:
            node, hops = queue.popleft()
            if hops > depth_limit:
                continue

            is_start = (node == str(current_node))
            is_blocked = (node in conflict_set or node in occupied)

            if not is_start and not is_blocked:
                cfg      = na.get(node, {}) or {}
                loc_type = str(cfg.get('locationType', '')).upper()
                arrival  = str(cfg.get('arrival_action', '')).lower()
                # Loại trừ khỏi chỗ đỗ THƯỜNG: CHARGER, DROPOFF, node có arrival_action đặc biệt
                if loc_type in ('CHARGER', 'DROPOFF') or arrival in ('wait_charge',):
                    # Trạm sạc: chỉ ghi nhận làm phương án DỰ PHÒNG (dùng khi không còn chỗ nào khác)
                    if loc_type == 'CHARGER' or arrival == 'wait_charge':
                        if _busy_ch is None:
                            _busy_ch = _nodes_busy_for(agv_id, line_agv_handler)
                        if _charger_siding_ok(agv_id, node, _busy_ch):
                            charger_cands.append((hops, g.degree(str(node)) if str(node) in g else 99, node))
                elif hops <= max_hops:
                    degree = g.degree(str(node)) if str(node) in g else 99
                    is_waiting = 1 if loc_type == 'WAITING' else 0
                    # Hành lang 1 làn / ngách cụt (SINGLE block) mà xe CHƯA ở trong: đỗ vào đó tự nhốt mình và chắn
                    # xe sau (đỗ ở 73 — ngách cụt, đích của rơ-moóc) → để cuối danh sách, chỉ dùng khi hết chỗ khác.
                    _blk = self._block_of_node.get(str(node))
                    _foreign_single = int(bool(_blk) and self._block_type.get(_blk) == 'single'
                                          and _blk != self._block_of_node.get(str(current_node)))
                    candidates.append((_foreign_single, -is_waiting, 1 if node in others_future else 0, degree, hops, node))

            # Chỉ traverse tiếp từ node KHÔNG bị blocked (trừ node xuất phát).
            # Không đi qua blocked node để tìm candidate phía sau nó —
            # vì đường đi thực tế vẫn phải qua node đó.
            if hops < depth_limit and (is_start or not is_blocked):
                for nb in g.neighbors(str(node)):
                    nb_str = str(nb)
                    if nb_str not in visited:
                        visited.add(nb_str)
                        queue.append((nb_str, hops + 1))

        if not candidates:
            if charger_cands:
                # Hết chỗ đỗ thường → dùng TRẠM SẠC làm điểm né (điểm CUỐI bản đồ: đường tới đây
                # kết thúc tại trạm, xe dừng hẳn — không đi tiếp).
                charger_cands.sort()
                best = charger_cands[0][2]
                print(f"[TRAFFIC] {agv_id}: KẸT hết đường → dùng TRẠM SẠC {best} làm điểm né "
                      f"(cách {charger_cands[0][0]} bước, từ {current_node}) — điểm cuối bản đồ")
                return best
            return None
        candidates.sort()
        best = candidates[0][5]
        print(f"[TRAFFIC] {agv_id}: flexible parking → {best} "
              f"(score={candidates[0][:5]}, from={current_node})")
        return best

    @_agv_scoped
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

        # Cabin thang máy là ngõ cụt dùng chung → cũng không được làm siding
        # (xe đỗ trong cabin giam thang và đi cùng hành lang với winner).
        _cabin_nodes = set()
        try:
            _cabin_nodes = {str(v) for v in dict(getattr(_mm, "elev_nodes", None) or {}).values()}
        except Exception:
            pass

        def _is_station(_n: str) -> bool:
            if str(_n) in _cabin_nodes or TrafficCoordinator._in_elev_zone(_n):
                return True
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

        # Node đang có xe KHÁC đứng (vị trí vật lý) hoặc nằm trong path đã đăng ký/giữ chỗ
        # của xe khác → KHÔNG được chọn làm chỗ đỗ né (nếu không 2 xe sẽ chồng lên nhau
        # cùng 1 node = va chạm vật lý, vd SIM15 đỗ né vào 202 khi SIM13 đang đứng đó).
        occupied: set[str] = set()
        try:
            for _oid_o, _st_o in line_agv_handler.state_store._states.items():
                if _oid_o != agv_id and _st_o is not None and _st_o.current_tag is not None:
                    occupied.add(str(_st_o.current_tag))
        except Exception:
            pass
        for _oid_r, _r_o in self._registered.items():
            if _oid_r == agv_id:
                continue
            occupied.update(str(n) for n in _r_o['path'][_r_o.get('current_idx', 0):])
        for _oid_i, _ir in self._intent_route.items():
            if _oid_i != agv_id and _ir:
                occupied.update(str(n) for n in _ir)

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
                and str(n) not in occupied       # KHÔNG đỗ né vào node có xe khác
            ]
            if not candidates:
                continue
            # ưu tiên nhánh cụt / ít kết nối (đỗ né không cản xe khác)
            candidates.sort(key=lambda n: g.degree(str(n)))
            parking = candidates[0]
            print(f"[TRAFFIC] {agv_id}: waiting/parking node={parking} "
                  f"(rẽ tại entry={entry_node}, conflict_idx={conflict_idx})")
            return (parking, entry_node)

        # DỰ PHÒNG CUỐI: không còn chỗ né thường → thử TRẠM SẠC kề điểm rẽ (chỉ trạm xe này được
        # phép vào, đang trống, đúng loại xe). Trạm sạc là điểm cuối bản đồ — xe vào rồi dừng hẳn.
        for si in range(0, end_search):
            entry_node = path[si]
            if entry_node not in g:
                continue
            came_from = path[si - 1] if si > 0 else None
            for n in g.neighbors(str(entry_node)):
                n = str(n)
                if (n not in path_set and n not in other_future and n != str(came_from)
                        and n != str(_prev_phys) and n not in occupied
                        and _charger_siding_ok(agv_id, n, occupied)):
                    print(f"[TRAFFIC] {agv_id}: KẸT hết chỗ né → dùng TRẠM SẠC {n} làm điểm né "
                          f"(rẽ tại entry={entry_node}) — điểm cuối bản đồ")
                    return (n, entry_node)

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
        self._stuck_warned: dict[str, bool] = {}
        # Cảnh báo lỗi firmware THẬT theo đúng giao thức đã xác nhận với bên
        # firmware (PROTOCOL_GUIDE.md §3: "errors"[]/"safetyState") — edge-trigger
        # (chỉ báo 1 lần khi CHUYỂN từ hết→có, không báo lại mỗi state message
        # trong lúc lỗi vẫn đang tiếp diễn), tự xoá khi hết.
        self._fw_error_active: dict[str, bool] = {}
        self._estop_active: dict[str, bool] = {}
        self._field_violation_active: dict[str, bool] = {}
        # Riêng cho CẢNH BÁO kẹt-không-rõ-lý-do: KHÁC _stopped_since (mốc đó cố
        # tình không reset trong lúc waiting_before_conflict/reservation hợp lệ,
        # để chu kỳ re-check 8s vẫn chạy đều) — mốc này CHỈ tính thời gian đứng
        # yên MÀ KHÔNG CÒN lý do hợp lệ nào (re-check xong vẫn không thấy
        # waiting_before_conflict), tránh báo nhầm khi 1 chờ-hợp-lệ (vd kẹt ngã
        # tư nhiều xe) kéo dài tự nhiên >60s rồi mới được giải phóng.
        self._unexplained_stuck_since: dict[str, float] = {}
        # Thời điểm xe BẮT ĐẦU đứng yên tại tag hiện tại (để chờ đủ lâu mới cứu kẹt).
        self._stopped_since: dict[str, float] = {}
        # PHÁT HIỆN THỰC TẾ (2026-09-29, AGV03 kẹt vòng lặp tiến-lùi tại 28↔30):
        # off_route re-dispatch bình thường là cơ chế TỐT (tự sửa khi xe lệch route),
        # nhưng nếu NGUYÊN NHÂN off_route lặp lại (vd rẽ sai hướng tại đúng 1 ngã tư
        # sau khi vừa lùi tới) thì cơ chế này tự lặp VÔ HẠN: dispatch lại → lại rẽ sai
        # → lại off_route tại ĐÚNG node cũ → dispatch lại... không có gì tự nhận ra
        # đây là vòng lặp thay vì off_route rời rạc bình thường. Theo dõi lịch sử
        # (tag, thời điểm) mỗi lần off_route; nếu ĐÚNG 1 tag lặp lại liên tiếp quá
        # OFF_ROUTE_LOOP_THRESHOLD lần trong OFF_ROUTE_LOOP_WINDOW_SEC giây → coi là
        # vòng lặp thật, KHÔNG re-dispatch tiếp tục (tự lặp mãi), dừng xe + báo operator.
        self._off_route_history: dict[str, list[tuple[str, float]]] = {}
        # True khi xe từng báo error_code != 0 và CHƯA được "tiêu thụ" bởi 1 lần
        # cứu-kẹt — watchdog "DỪNG GIỮA route" chỉ được phép resend khi cờ này đang
        # True (tức xe THỰC SỰ từng lỗi rồi mới hết lỗi), KHÔNG resend cho mọi ca
        # đứng yên bình thường (tránh polling/spam liên tục không cần thiết).
        self._had_error: dict[str, bool] = {}
        # Lần cuối xe LÙI nhường đường (chống ping-pong lùi↔tiến liên tục).
        self._backup_ts: dict[str, float] = {}
        # Lần cuối xe REROUTE-do-obstacle (avoid_all) — chống flip-flop lật nhánh vòng.
        self._reroute_ts: dict[str, float] = {}
        self._reroute_hist: dict[str, list] = {}   # lịch sử mốc reroute (chống lật nhánh dài hạn)
        self._reroute_left: dict[str, list] = {}   # [(ts, 4 node đầu nhánh vừa BỎ)] — chống quay lại nhánh cũ
        # Đếm số lần gửi lại plan liên tiếp tại CÙNG 1 node trung gian mà tag không
        # đổi (nghi firmware "nuốt" plan/MANUAL) — dùng để cảnh báo rõ thay vì lặng
        # lẽ resend vô hạn. {agv_id: (tag, count)}
        self._intermediate_resend: dict[str, tuple] = {}

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
            # Xe kia vừa ĐỔI ĐƯỜNG: path đăng ký có thể chưa cập nhật nhưng route/cửa sổ đã gửi cho firmware
            # → nó sắp lái vào node kế của mình (đúng va chạm SIM01/SIM04 tại 33: SIM01 vừa REROUTED
            # [34,33,32] thì SIM04 vacate sang 33). Nhìn cả cửa sổ đang chạy và ý định đi của nó.
            _rtb = self._routes.get(_oid_b)
            if _rtb and _rtb.full_path and _stb.current_tag is not None:
                _fpb = [str(n) for n in _rtb.full_path]
                _cb = str(_stb.current_tag)
                if _cb in _fpb:
                    _ci = _fpb.index(_cb)
                    _we = min(max(getattr(_rtb, 'window_end', 0), _ci + 1), len(_fpb) - 1)
                    if _nxt_node in _fpb[_ci + 1:_we + 1]:
                        return False
            _intb = traffic_coordinator._intent_route.get(_oid_b)
            if _intb and _stb.current_tag is not None:
                _ib2 = [str(n) for n in _intb]
                _cb2 = str(_stb.current_tag)
                if _cb2 in _ib2 and _nxt_node in _ib2[_ib2.index(_cb2) + 1:_ib2.index(_cb2) + 3]:
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
        w_end    = _time_capped_window_end(str_path, 0, first_window_end(str_path))
        route    = LineAGVRoute(
            full_path=str_path,
            task_type=task_type,
            direction=direction,
            window_start=0,
            window_end=w_end,
            is_complete=(w_end == len(str_path) - 1),
        )
        self._routes[agv_id] = route
        # Lớp chặn cuối: đường nào (kể cả đường né/thay thế tự tính) đi NGƯỢC hướng riêng theo loại xe
        # (type_directions) thì báo to — chỉ log, không huỷ (huỷ giữa chừng có thể làm xe kẹt tại chỗ).
        try:
            from mqtt_client import map_manager as _mm_td
            _fe_td = _mm_td.forbidden_edges(agv_id)
            if _fe_td:
                _bad_td = [(a, b) for a, b in zip(str_path, str_path[1:]) if (a, b) in _fe_td]
                if _bad_td and getattr(route, "_td_warned", None) != tuple(str_path):
                    print(f"[TYPE_DIR] {agv_id}: route đi NGƯỢC hướng riêng theo loại xe trên cạnh {_bad_td} "
                          f"(path={str_path}) — lỗi điều phối, kiểm tra nơi tính đường này")
        except Exception:
            pass
        # Cập nhật hướng plan hiện tại vào state để dispatch sau này tham chiếu
        _st = self.state_store.get(agv_id)
        if _st:
            _st.last_plan_direction = direction
        # Đăng ký vào TrafficCoordinator (register → reserve_ahead giữ chỗ phía trước)
        traffic_coordinator.register(agv_id, str_path, direction, task_type)
        # CẮT window theo RESERVATION (openTCS "allocate trước, move sau"): xe CHỈ được
        # gửi RUN tới node đã giữ chỗ. Nếu node kế bị xe khác giữ → window dừng tại node
        # đã reserve → xe KHÔNG lao vào vùng tranh chấp (tránh đâm do đua reactive).
        _res_end = traffic_coordinator.reserved_extent_lenient(
            agv_id, str_path, 0, route.window_end)
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

    # ── Rẽ tại chỗ: xe lăn thẳng trước khi quay ─────────────────────────────────────────────────────────────
    # PHÁT HIỆN THỰC TẾ (23/11, AGV01 tại node 30 trước khi vào thang; cũng 20/11, 21/11): plan đúng (TURN_R ở thẻ 30) nhưng ~1 trong 5
    # lần xe chỉ lăn THẲNG ~1,2 s sau plan (sớm hơn lúc xe quay bình thường ~1,9 s), chạy hết đoạn rồi mới dừng và quay sau 5–18 s.
    # Bình thường `driving=True` và event `turn_busy` tới CÙNG gói state. Nếu xe `driving` liên tục ≥ STANDING_TURN_ROLL_S mà chưa có
    # `turn_busy` và thẻ chưa đổi → xe đang lăn thẳng: dừng xe rồi gửi lại plan (tối đa STANDING_TURN_MAX_RETRIES lần), thay vì để
    # nó chạy hết đường. Tắt bằng env STANDING_TURN_GUARD=0.
    def arm_standing_turn(self, agv_id: str, order: dict, prev_retries: int = 0) -> None:
        """Gọi ngay sau khi PUBLISH 1 plan: nếu plan bắt đầu bằng rẽ tại thẻ xe đang đứng thì bắt đầu theo dõi."""
        st = self.state_store.get(agv_id)
        if st is None:
            return
        st.standing_turn = None
        if not STANDING_TURN_GUARD or not isinstance(order, dict) or order.get("c") != "plan":
            return
        steps = order.get("d") or []
        if not steps or st.current_tag in (None, 0) or st.driving:
            return
        t0 = str(steps[0].get("t"))
        if t0 != str(st.current_tag):
            return
        if not any(str(s.get("t")) == t0 and s.get("a") in (ACTION_TURN_R, ACTION_TURN_L) for s in steps):
            return
        st.standing_turn = {"order": order, "at": time.time(), "tag": t0, "busy": False, "drive_since": 0.0,
                            "retries": prev_retries, "fired": False}

    def _check_standing_turn(self, agv_id: str, state: "LineAGVState", event_name: str) -> None:
        stt = state.standing_turn
        if not stt:
            return
        now = time.time()
        if (event_name == "turn_busy" or str(state.current_tag) != stt["tag"] or stt["fired"]
                or now - stt["at"] > STANDING_TURN_WATCH_S):
            if event_name == "turn_busy":
                stt["busy"] = True
            state.standing_turn = None
            return
        if not state.driving:
            stt["drive_since"] = 0.0
            return
        if not stt["drive_since"]:
            stt["drive_since"] = now
            return
        if now - stt["drive_since"] < STANDING_TURN_ROLL_S:
            return
        # xe đã lăn thẳng ≥ ngưỡng mà chưa quay
        stt["fired"] = True
        state.standing_turn = None
        if stt["retries"] >= STANDING_TURN_MAX_RETRIES:
            msg = (f"Xe {agv_id} lăn thẳng khỏi thẻ {stt['tag']} mà không quay (đã thử lại {stt['retries']} lần) — cần kiểm tra xe/vị trí dừng so với thẻ")
            print(f"[LINE_AGV] {agv_id}: {msg}")
            self._set_alert(agv_id, state, "TURN_NOT_STARTED", msg)
            return
        print(f"[LINE_AGV] {agv_id}: plan bắt đầu bằng RẼ tại thẻ {stt['tag']} nhưng xe LĂN THẲNG {now - stt['drive_since']:.1f}s "
              f"không có turn_busy → DỪNG xe và gửi lại plan (lần {stt['retries'] + 1}/{STANDING_TURN_MAX_RETRIES})")
        try:
            from mqtt_client import send_line_command as _slc_st
            _slc_st(agv_id, "stop")
        except Exception as e:
            print(f"[LINE_AGV] {agv_id}: dừng xe lăn thẳng lỗi: {e}")
            return
        import threading as _th_st
        _tm = _th_st.Timer(STANDING_TURN_RESEND_S, self._resend_standing_turn,
                           args=(agv_id, stt["order"], stt["tag"], stt["retries"] + 1))
        _tm.daemon = True
        _tm.start()

    def _resend_standing_turn(self, agv_id: str, order: dict, tag0: str, retries: int) -> None:
        """Sau khi dừng: gửi lại ĐÚNG plan (id mới) — chỉ khi lệnh còn hiệu lực và xe vẫn ở thẻ cũ."""
        try:
            st = self.state_store.get(agv_id)
            route = self._routes.get(agv_id)
            if st is None or route is None or str(st.current_tag) != str(tag0):
                print(f"[LINE_AGV] {agv_id}: bỏ gửi lại plan rẽ tại {tag0} (lệnh đã đổi/huỷ hoặc xe đã sang thẻ khác)")
                return
            import uuid as _uuid_st
            new = dict(order)
            new["id"] = _uuid_st.uuid4().hex[:8]
            import mqtt_client as _mc_st
            _mc_st._send_line_order(agv_id, new)
            cur = self.state_store.get(agv_id)
            if cur is not None and cur.standing_turn:
                cur.standing_turn["retries"] = retries
        except Exception as e:
            print(f"[LINE_AGV] {agv_id}: gửi lại plan rẽ tại chỗ lỗi: {type(e).__name__}: {e}")

    def resume_after_offline(self, agv_id: str, state: "LineAGVState") -> bool:
        """Xe vừa ONLINE LẠI sau khi mất tín hiệu (vd vào thang, cabin đóng cửa mất Wi-Fi): lệnh hàng đợi đang chạy
        lúc đó KHÔNG được mất. Nếu lệnh còn dang dở mà server không còn route để tiếp tục (route bị huỷ khi xe ma
        online lại ở vị trí khác, hoặc route cũ không còn khớp vị trí thật) → dựng lại lệnh từ VỊ TRÍ THẬT, y như off_route.

        Gọi từ luồng riêng (dispatch chờ vòng lặp sự kiện — KHÔNG gọi thẳng trong event loop). True = xong/không cần nữa;
        False = chưa đủ điều kiện (xe còn chạy/xe ma/đang giữ plan) → kiểm tra lại lượt sau."""
        want = state.resume_cmd_id
        if not want:
            return True
        try:
            from task_queue import agv_task_queue as _atq
            run = _atq.get_running(agv_id)
        except Exception as e:
            print(f"[RESUME] {agv_id}: đọc lệnh đang chạy lỗi: {e}")
            return False
        if not run or run.get("cmd_id") != want:
            state.resume_cmd_id = None          # lệnh đã xong/đổi/huỷ trong lúc offline — đã có cơ chế khác lo
            return True
        cmd = str(run.get("command") or "")
        if cmd not in ("go_to", "go_charge", "go_wait") or state.pending_retry_cmd:
            state.resume_cmd_id = None          # lệnh thang (elev_*) do cầu nối thang điều khiển; pending_retry tự thử lại
            return True
        if state.task_lifecycle or state.hook_pending:
            state.resume_cmd_id = None          # đang chờ xác nhận người/móc — cơ chế lifecycle/móc lo tiếp
            return True
        if state.ghost or state.driving or state.current_tag in (None, 0):
            return False
        try:
            from mqtt_client import _HELD_PLANS
            if agv_id in _HELD_PLANS:
                return False                    # plan đang giữ chờ gửi bù — để flush_held_plan làm trước
        except Exception:
            pass
        route = self._routes.get(agv_id)
        if route is not None:
            fp = [str(n) for n in (route.full_path or [])]
            if str(state.current_tag) in fp:
                state.resume_cmd_id = None      # route còn khớp vị trí: gửi bù plan / cửa sổ kế tiếp như thường
                return True
            # route cũ không còn chứa vị trí thật của xe đang đứng yên → bỏ route cũ rồi dựng lại bên dưới
            self._routes.pop(agv_id, None)
            traffic_coordinator.deregister(agv_id)
            _release_all_line_edges(agv_id)
            state.current_edge_pair = None
        dest = run.get("dest_node")
        if cmd == "go_to" and not dest:
            state.resume_cmd_id = None
            return True
        try:
            _atq.insert_next(agv_id, cmd, dest_node=(str(dest) if dest else None))
            state.resume_cmd_id = None
            print(f"[RESUME] {agv_id}: online lại tại {state.current_tag}, lệnh {cmd}"
                  f"{' → ' + str(dest) if dest else ''} còn dang dở và không còn route — dựng lại từ vị trí thật")
            _atq.on_agv_completed(agv_id, notes="resume_after_offline")
            return True
        except Exception as e:
            print(f"[RESUME] {agv_id}: dựng lại lệnh dang dở lỗi: {e}")
            return False

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
        _driving_now = bool(data.get("driving", False))
        if new_tag != old_tag and old_tag is not None:
            # Xe ĐANG ĐỨNG YÊN (driving=False cả gói cũ lẫn gói mới) mà tag lại đổi
            # → CHẮC CHẮN là gói tin trễ/lặp báo tag CŨ (vật lý xe không hề nhúc nhích),
            # KHÔNG phải di chuyển thật. Nếu tin nó → current_tag/prev_tag vừa được
            # đồng bộ đúng bởi logic "transit hoàn tất" (line_agv_handler.py) sẽ bị
            # phá ngược lại, dẫn tới turn-direction tính SAI ở lệnh dispatch kế tiếp
            # (from=X→X→Y, prev==current) → xe đi thẳng thay vì rẽ, lùi vòng vô tận.
            if not _driving_now and not state.driving:
                new_tag = old_tag
            else:
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
        state.real_state_seen = True        # đã nhận state THẬT từ xe (khác override_position: vị trí khôi phục từ DB/đặt tay)

        # Thang máy (backend uelev_v2): xe tới thẻ cabin / thẻ thoát → báo thư viện (agv_boarded / agv_exited)
        try:
            from elevator_coordinator import elevator_coordinator as _ec_st
            _ec_st.on_agv_state(agv_id, state.current_tag, state.driving)
        except Exception as _ee:
            print(f"[ELEVATOR] on_agv_state {agv_id} lỗi: {type(_ee).__name__}: {_ee}")

        # ── Lỗi THẬT từ firmware (PROTOCOL_GUIDE.md §3, xác nhận đang được gửi
        # lên) — "errors"[] (mảng lỗi chung kiểu VDA5050: errorType/errorLevel/
        # errorDescription) + "safetyState" (eStop, fieldViolation). Trước đây
        # KHÔNG hề đọc — firmware có báo nhưng rơi mất hoàn toàn, không log,
        # không dashboard, không Telegram. Edge-trigger (chỉ báo lúc CHUYỂN từ
        # hết→có, không spam mỗi state message) + tự xoá khi hết, cùng mẫu với
        # mọi cảnh báo khác trong file này (_set_alert + Telegram).
        self._handle_firmware_errors(agv_id, state, data)

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

        # ── ACK lệnh tức thời run/stop theo ID (09-ack-lenh-fms.md §2.2) ──────
        # Có lệnh chờ → kiểm state.cmd_ack; chưa khớp thì gửi lặp/gửi bù (xe vừa online lại).
        try:
            from agv_cmd_channel import agv_cmd_channel as _acc
            _acc.on_state(agv_id, data, state.paused, state.driving)
        except Exception as _ce:
            print(f"[CMD_ACK] {agv_id}: on_state lỗi: {_ce}")
        # Plan đang GIỮ vì xe offline: có state mới = xe online lại → gửi bù (id mới) trước khi xử lý các event bên dưới
        try:
            from mqtt_client import flush_held_plan as _fhp
            _fhp(agv_id)
        except Exception as _fe:
            print(f"[PLAN_HOLD] {agv_id}: flush lỗi: {_fe}")

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
                # PHÁT HIỆN THỰC TẾ (2026-10-08, 2 lần trong 1 ngày: AGV01/AGV03
                # tại node 7, AGV03/AGV04 tại node 28): cả 2 lần xe CHIẾM node
                # chỉ vừa vật lý tới đó (đúng dòng tag đổi này) SAU KHI xe kia
                # đã được cấp quyền đi vào node đó từ trước (hợp lệ lúc cấp —
                # không phải lỗi reservation). Chờ tới tick kế tiếp của watchdog
                # 1 giây (main.monitor_physical_collision_risk) để phát hiện là
                # CHẬM — gọi NGAY lượt quét đồng bộ ở đây, đúng lúc tag vừa đổi
                # (sự kiện duy nhất tạo ra rủi ro mới), để STOP được gửi sớm hơn
                # tới cả giây so với chờ tick định kỳ.
                try:
                    from main import physical_collision_scan_once as _pcso
                    _pcso()
                except Exception as _e_pcso:
                    print(f"[LINE_AGV] {agv_id}: physical_collision_scan_once lỗi: {_e_pcso}")
                # Lớp 2 (xem main.physical_overlap_scan_once): tag vừa đổi có thể
                # đổi THẲNG tới đúng node 1 xe khác đang đứng — gọi ngay tại đây
                # cùng lý do với lớp 1 ở trên, không chờ tick 1s.
                try:
                    from main import physical_overlap_scan_once as _posc
                    _posc()
                except Exception as _e_posc:
                    print(f"[LINE_AGV] {agv_id}: physical_overlap_scan_once lỗi: {_e_posc}")
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
            # ── AGV kéo (tow): tới điểm LẤY HÀNG (Tổ hoặc lấy rỗng gần trạm)
            # cần nâng móc TRƯỚC 1 node — tới đúng node LIỀN TRƯỚC đích lấy
            # hàng là tự động NÂNG MÓC LUÔN (không chờ tới nơi mới nâng), để
            # móc kịp nâng xong TRƯỚC khi xe áp sát xe hàng cần lấy. Tại node
            # đích, _handle_trailer_hook_arrival sẽ thấy móc đã nâng sẵn (xem
            # state.hook_prearmed_for) và bỏ qua bước nâng/hạ lại — chỉ còn
            # chờ xác nhận thủ công DUY NHẤT "đã lấy hàng xong, đi tiếp".
            if new_tag is not None:
                try:
                    self._maybe_preraise_tow_hook(agv_id, str(new_tag), state)
                except Exception as _e_prh:
                    print(f"[LINE_AGV] {agv_id}: pre-raise móc (tow) lỗi: {_e_prh}")
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
            elif (_hook_field == "up_fail" and state.hook_raise_sent_at > 0
                    and state.hook_pending_action != ACTION_HOOK_LOWER
                    and not state.hook_fallback_notified):
                # hook_pending_action != LOWER (mặc định None cũng qua được) — chỉ báo
                # lỗi NÂNG khi thực sự đang chờ NÂNG. Trước đây không phân biệt được vì
                # chỉ có 1 loại AGV (rơ-moóc) luôn gửi NÂNG lúc tới node — AGV kéo
                # (agv_type='tow') gửi HẠ lúc tới nên phải tách rõ theo action đã gửi.
                state.hook_fallback_notified = True
                self._handle_event(agv_id, "hook_raise_failed", data, state)
                _hook_handled_as = "hook_raise_failed"
            elif (_hook_field == "dn_fail" and state.hook_pending is not None
                    and state.hook_pending_action != ACTION_HOOK_RAISE
                    and not state.hook_fallback_notified):
                # Trước đây gate cứng theo hook_pending=="pickup" (đúng cho rơ-moóc: HẠ
                # chỉ xảy ra lúc lấy hàng, qua nút thủ công). AGV kéo lại gửi HẠ tự động
                # lúc THẢ hàng (hook_pending=="dropoff") — gate theo hook_pending_action
                # để đúng cho cả 2 loại, không bỏ sót lỗi hạ móc của AGV kéo lúc thả hàng.
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
        try:
            self._check_standing_turn(agv_id, state, event_name)
        except Exception as _e_stt:
            print(f"[LINE_AGV] {agv_id}: kiểm tra rẽ tại chỗ lỗi: {_e_stt}")

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
        # PHÁT HIỆN THỰC TẾ (2026-09-26, AGV04 "biến mất" khỏi log >4 phút sau khi
        # tag nhảy tới 1 node ngoài route): khối này trước đây KHÔNG có try/except
        # (khác hầu hết chỗ khác trong file) — nếu _handle_event("off_route", ...)
        # ném exception, cả state message coi như mất trắng, KHÔNG có dấu vết gì
        # (không print, không Telegram) → xe đứng im vĩnh viễn mà "không báo lỗi
        # gì cả" đúng như người dùng phản ánh. Bọc lại để LUÔN thấy được nếu lần
        # sau tái diễn, dùng đúng cơ chế Telegram đã có cho các cảnh báo khác.
        try:
            if (new_tag != old_tag and new_tag is not None
                    and not state.driving and not state.task_lifecycle):
                _route_now = self._routes.get(agv_id)
                if _route_now and _route_now.is_complete and _route_now.full_path:
                    _exp_end = _route_now.full_path[-1]
                    if str(new_tag) != str(_exp_end) and str(new_tag) not in _route_now.full_path:
                        print(f"[LINE_AGV] {agv_id}: dừng bất ngờ tại {new_tag} "
                              f"(route chờ đích {_exp_end}) → coi như off_route, re-dispatch")
                        self._handle_event(agv_id, "off_route", {}, state)
        except Exception as _e_offr:
            _msg_offr = (f"⚠️ AGV {agv_id}: phát hiện off_route tại {new_tag} nhưng "
                         f"xử lý re-dispatch bị lỗi ({_e_offr}) — xe có thể đang đứng "
                         f"im vĩnh viễn tại node ngoài route, cần kiểm tra/gửi lệnh "
                         f"lại thủ công.")
            print(f"[LINE_AGV] {agv_id}: {_msg_offr}")
            self._set_alert(agv_id, state, "OFF_ROUTE_ERROR", _msg_offr)
            try:
                from telegram_bot import notify_error as _tg_notify_offr
                _tg_notify_offr(_msg_offr)
            except Exception as _e_tg_offr:
                print(f"[LINE_AGV] {agv_id}: gửi Telegram cảnh báo off_route lỗi: {_e_tg_offr}")

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
        # Thang máy: cùng kiểu — kiểm tra timeout chờ xác nhận mở/đóng, tự gửi lại (elevator_coordinator.py)
        try:
            from elevator_coordinator import elevator_coordinator as _elev_co_tick
            _elev_co_tick.check_retries()
        except Exception as _e_elev_tick:
            print(f"[LINE_AGV] elevator check_retries lỗi: {_e_elev_tick}")
        # Lệnh run/stop chờ cmd_ack: quét gửi lặp/gửi bù (xe khác báo state cũng kích được)
        try:
            from agv_cmd_channel import agv_cmd_channel as _acc_tick
            _acc_tick.tick()
        except Exception as _e_acc_tick:
            print(f"[CMD_ACK] tick lỗi: {_e_acc_tick}")

        # ── CỨU KẸT MÓC: gửi lại lệnh móc (nâng/hạ) nếu không thấy phản hồi ──
        # Lệnh 'action' móc là 1 lệnh RỜI RẠC, KHÔNG nằm trong cơ chế resend
        # plan/rolling-window ở dưới — nếu gói MQTT bị rớt (đã xảy ra thực tế: publish
        # rc=0 nhưng không có hook_raised/hook_raise_failed nào quay về), xe đứng chờ
        # MÃI MÃI vì không có gì tự phát hiện. Theo dõi qua hook_raise_sent_at (set khi
        # gửi, xoá khi có phản hồi/lỗi rõ ràng) — quá HOOK_RAISE_TIMEOUT giây mà vẫn
        # treo (hook_pending còn set, hook_state chưa đạt đích) → gửi lại ĐÚNG lệnh đã
        # gửi (hook_pending_action — 30=NÂNG cho rơ-moóc, hoặc 31=HẠ cho AGV kéo lúc
        # tới node), tối đa HOOK_RAISE_MAX_RETRIES lần rồi thôi (tránh spam vô hạn nếu
        # móc thật sự hỏng cơ khí — cần người can thiệp).
        # ACTION_HOOK_LOWER=31 gửi lúc tới (AGV kéo) → đích "lowered"; mặc định/
        # ACTION_HOOK_RAISE=30 (rơ-moóc) → đích "raised".
        _hook_target_state = "lowered" if state.hook_pending_action == ACTION_HOOK_LOWER else "raised"
        if (state.hook_pending is not None and state.hook_state != _hook_target_state
                and state.hook_raise_sent_at > 0):
            _hook_elapsed = time.monotonic() - state.hook_raise_sent_at
            _hook_verb = "HẠ" if state.hook_pending_action == ACTION_HOOK_LOWER else "NÂNG"
            if _hook_elapsed >= HOOK_RAISE_TIMEOUT:
                if state.hook_raise_retries < HOOK_RAISE_MAX_RETRIES:
                    state.hook_raise_retries += 1
                    print(f"[LINE_AGV] {agv_id}: không thấy phản hồi {_hook_verb} móc sau "
                          f"{_hook_elapsed:.1f}s → GỬI LẠI lần "
                          f"{state.hook_raise_retries}/{HOOK_RAISE_MAX_RETRIES}")
                    self._send_hook_action_delayed(
                        agv_id, state.hook_pending_action or ACTION_HOOK_RAISE, delay=0.0)
                else:
                    _msg_hk_retry = (f"⚠️ AGV {agv_id}: gửi lại {HOOK_RAISE_MAX_RETRIES} lần "
                          f"vẫn không có phản hồi {_hook_verb} móc tại node {state.current_tag} — "
                          f"dừng thử tự động, cần kiểm tra thủ công (hook_state hiện tại "
                          f"có thể KHÔNG đúng thực tế).")
                    print(f"[LINE_AGV] {agv_id}: {_msg_hk_retry}")
                    state.hook_raise_sent_at = 0.0   # tránh lặp lại log này mỗi tick
                    self._set_alert(agv_id, state, "HOOK_RETRY_EXHAUSTED", _msg_hk_retry)
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
            self._stuck_warned.pop(agv_id, None)
            self._unexplained_stuck_since.pop(agv_id, None)
            self._clear_alert(state)   # xe lại di chuyển/chạy được → hệ thống thấy đã ổn
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
        # arrived_wait_* (firmware tới nơi mà không báo / mất gói) → đoạn KHÔNG bao giờ
        # hoàn tất → kẹt HẲN, dispatch lệnh kế không chạy (chính lỗi AGV02 kẹt ở node 2,
        # lỗi AGV04 kẹt ở node 98 chờ móc, và lỗi AGV03 kẹt ở trạm sạc node 1 — không
        # thấy arrived_wait_charge nào dù xe đã lùi vào hẳn). MỞ RỘNG sang
        # 'delivery'/'pickup'/'return_charge' (trước đây chỉ 'transit', né lifecycle
        # giao/lấy/móc hàng/sạc) — dùng CHUNG điều kiện an toàn đã có (xe thật sự đứng
        # yên, đúng node biên, không lỗi, không vật cản, sau grace period) nên rủi ro
        # kích nhầm khi xe CHƯA thật sự tới là như nhau.
        # Sau grace → tự sinh ĐÚNG event mà node/plan đó cần (đọc từ action code cuối
        # cùng của plan ĐÃ GỬI cho node hiện tại — KHÔNG hardcode 'arrived_wait_sys',
        # vì node giao/lấy hàng thường dùng WAIT_USER, trạm sạc dùng WAIT_CHARGE) để
        # hoàn tất đoạn + dispatch kế/kích hook/xác nhận sạc đúng luồng.
        # KHÔNG kích khi error_code != 0 (xem giải thích ở watchdog phía trên).
        # KHÔNG kích khi state.hook_pending đã set (2026-09-18 — PHÁT HIỆN THỰC TẾ):
        # hook_pending!=None nghĩa là sự kiện tới-nơi ĐÃ xử lý xong (lệnh nâng/hạ
        # móc đã gửi), xe giờ đang chờ ĐÚNG phản hồi móc — thuộc trách nhiệm của
        # watchdog "CỨU KẸT MÓC" riêng ở trên (HOOK_RAISE_TIMEOUT/MAX_RETRIES, có
        # báo Telegram + dừng hẳn khi hết lần thử). Trước đây watchdog này không
        # loại trừ hook_pending → cứ mỗi STUCK_RESEND_GRACE/COOLDOWN lại tưởng nhầm
        # "chưa từng nhận sự kiện tới nơi", tự sinh lại arrived_wait_user →
        # _handle_trailer_hook_arrival() LUÔN reset hook_raise_retries=0 rồi gửi
        # lại móc — khiến bộ đếm của "CỨU KẸT MÓC" không bao giờ chạm
        # HOOK_RAISE_MAX_RETRIES để báo lỗi/dừng lại → lặp gửi-lại-hạ-móc vô hạn,
        # im lặng, xe không bao giờ tiến tiếp (đúng log: AGV01 kẹt ở 104, móc đã hạ
        # thật nhưng cứ 8s lại "TỰ SINH" gửi lại HẠ móc mãi không dứt).
        try:
            _route_b = self._routes.get(agv_id)
            # PHÁT HIỆN THỰC TẾ (2026-09-24): loại trừ `hook_pending is not None`
            # ở trên vốn để KHÔNG đụng vào ca đang chờ ACK móc (thuộc watchdog
            # "CỨU KẸT MÓC" riêng, dòng ~1750). Nhưng `hook_pending` cũng ĐƯỢC
            # GIỮ NGUYÊN lâu dài (cố ý, xem _maybe_preraise_tow_hook/comment
            # dòng ~4975) trong suốt quãng đường xe TIẾP TỤC DI CHUYỂN tới đích
            # thật sau khi đã nâng móc TRƯỚC 1 node — đây là trạng thái BÌNH
            # THƯỜNG, không phải "đang chờ ACK móc". Loại trừ theo `hook_pending`
            # một cách mù quáng khiến ca xe bị vật cản/obstacle chặn NGAY SAU khi
            # nâng móc trước (móc đã ACK xong, hook_raise_sent_at đã reset về 0)
            # KHÔNG BAO GIỜ được watchdog này cứu nữa — đúng lỗi thực tế: AGV01
            # nâng móc trước tại 30 (đích thật 105), bị vật cản ngay khi rời 30,
            # dừng hẳn tại 30 mãi mãi, không ai đánh thức lại (hook_pending vẫn
            # ="pickup" từ lúc nâng trước, chặn watchdog dù móc đã ACK xong từ
            # lâu) → 1 xe khác cũng cần tới 105 kẹt theo vô thời hạn. Sửa: chỉ
            # loại trừ khi hook_raise_sent_at > 0 (lệnh móc THẬT SỰ còn đang chờ
            # ACK, chưa xong) — mechanical action đã ACK xong (=0) thì watchdog
            # này vẫn cần chạy bình thường như mọi ca di chuyển khác.
            if (_route_b and _route_b.full_path and state.current_tag is not None
                    and not state.driving and not state.task_lifecycle
                    and (state.hook_pending is None or state.hook_raise_sent_at == 0)
                    and state.obstacle_since is None and not event_name
                    and state.error_code == 0
                    and getattr(_route_b, 'task_type', '') in
                        ('transit', 'delivery', 'pickup', 'return_charge')):
                _ct_b = str(state.current_tag)
                _ci_b = (_route_b.full_path.index(_ct_b)
                         if _ct_b in _route_b.full_path else -1)
                # ĐANG CHỜ reservation (node kế bị xe khác giữ) ≠ KẸT mất gói →
                # KHÔNG tự sinh; _check_waiting_agvs sẽ resume khi node được nhả.
                _nxt_b = (_route_b.full_path[_ci_b + 1]
                          if 0 <= _ci_b < len(_route_b.full_path) - 1 else None)
                # PHÁT HIỆN THỰC TẾ (2026-10-08, AGV01↔AGV04 tại cạnh 32↔30): khi 2 xe
                # HEAD-ON kiểu "tráo chỗ" (A đứng tại node B muốn tới, B đứng tại node
                # A muốn tới) thì node kế của xe THUA luôn bị node_reserved_by_other=True
                # (vì xe THẮNG đang current_tag CHÍNH ngay đó) → _res_wait_b=True khiến
                # xe THUA bị loại khỏi watchdog re-check này mãi mãi, TƯỞNG rằng
                # _check_waiting_agvs() sẽ tự đánh thức lại khi node được nhả — nhưng
                # _check_waiting_agvs() CHỈ chạy khi CÓ xe khác đổi tag; xe THẮNG (đang
                # winner-wait) cũng không đổi tag → KHÔNG AI đánh thức xe THUA →
                # _check_rolling_plan() (nơi DUY NHẤT thử _yield_to_siding/
                # _try_line_reroute/_back_up_to_reroute_node) không bao giờ được gọi lại
                # → xe THUA đứng im vĩnh viễn ngay cả khi còn siding/nhánh rẽ (vd node
                # 110) ngay gần đó chưa từng được thử. Chỉ coi "node kế bị giữ" là lý do
                # hợp lệ để BỎ QUA watchdog này khi CHƯA từng được đánh dấu head-on
                # standoff (waiting_before_conflict trống) — đã có waiting_before_conflict
                # rồi thì đây CHÍNH LÀ ca cần watchdog đánh thức lại để thử né tiếp.
                _res_wait_b = bool(
                    _nxt_b and traffic_coordinator.node_reserved_by_other(agv_id, _nxt_b)
                    and not _route_b.waiting_before_conflict)
                if _res_wait_b:
                    # Đang chờ node kế được xe khác giữ — lý do hợp lệ (có thể kéo
                    # dài tự nhiên khi nhiều xe cùng qua 1 nút giao đông đúc) →
                    # KHÔNG tính vào thời gian "kẹt không rõ lý do".
                    self._unexplained_stuck_since.pop(agv_id, None)
                # PHÁT HIỆN THỰC TẾ (2026-09-24): trước đây CHỈ bắt đúng lúc xe đứng
                # yên NGAY TẠI window_end (_ci_b == window_end). Nhưng có ca xe đứng
                # yên tại 1 node PHÍA SAU window_end (_ci_b < window_end — vd do
                # "REROUTED"/plan-race khiến current_tag lùi lại về đúng 1 node đã đi
                # qua trong full_path) mà KHÔNG có waiting_before_conflict/error/
                # reservation nào giữ — rơi hẳn ra ngoài MỌI safety-net hiện có (mid-
                # route resend ở trên chỉ chạy khi _had_error=True; nhánh này trước
                # đây chỉ chạy khi == window_end) → đứng im MÃI MÃI dù xe kia (winner
                # head-on) chỉ đang CHỜ mình né/đi tiếp (đúng lỗi thực tế: AGV03 đứng
                # yên tại 21 — 1 node đã đi qua, window_end lớn hơn nhiều — trong khi
                # AGV01 cứ "chờ AGV03 sẽ né" mãi không ai kích lại cho AGV03 cả).
                # Mở rộng sang MỌI _ci_b <= window_end (không chỉ đúng bằng) để bắt
                # được ca này; phần sinh event "tới nơi" bên dưới vẫn CHỈ áp dụng khi
                # thật sự == window_end (tránh sinh nhầm event tới-nơi khi chưa tới).
                if _ci_b >= 0 and _ci_b <= _route_b.window_end and not _res_wait_b:
                    _now_b = time.monotonic()
                    self._stopped_since.setdefault(agv_id, _now_b)
                    if (_now_b - self._stopped_since[agv_id] >= STUCK_RESEND_GRACE
                            and _now_b - self._mid_resend_ts.get(agv_id, 0.0) >= STUCK_RESEND_COOLDOWN):
                        self._mid_resend_ts[agv_id] = _now_b
                        if _route_b.waiting_before_conflict:
                            # Lý do hợp lệ tại thời điểm kiểm tra này — không tính
                            # vào "kẹt không rõ lý do" (có thể tự nhiên >60s khi
                            # nhiều xe cùng qua 1 nút giao đông đúc).
                            self._unexplained_stuck_since.pop(agv_id, None)
                        if _route_b.waiting_before_conflict or _ci_b < _route_b.window_end:
                            # PHÁT HIỆN THỰC TẾ 2026-09-18: route đang chờ 1 conflict đã
                            # phát hiện lúc set_route()/_check_rolling_plan() trước đó
                            # (waiting_before_conflict được gán). Bình thường tự resume
                            # qua _check_waiting_agvs() — nhưng hàm đó CHỈ được gọi khi
                            # CÓ xe KHÁC đổi tag (xem "new_tag != old_tag" phía trên).
                            # Nếu điều-kiện-chặn biến mất theo cách KHÔNG kèm đổi tag
                            # (vd xe kia đã vào lifecycle charging từ trước, hoặc
                            # reservation mồ côi tự hết hạn) → KHÔNG BAO GIỜ có ai kích
                            # lại cho agv_id này → đứng im MÃI MÃI dù đường đã thông
                            # (đúng lỗi thực tế: AGV01 đứng ở 7 chờ node 1, node 1 đã
                            # trống từ lâu nhưng không ai báo lại). Định kỳ RE-CHECK
                            # (KHÔNG ép đi — _check_rolling_plan tự quyết định lại từ
                            # đầu, an toàn y hệt lần kiểm tra đầu tiên, chỉ khác là được
                            # gọi lại theo chu kỳ thay vì chỉ chờ sự kiện từ xe khác).
                            _stuck_why = ("đang chờ conflict" if _route_b.waiting_before_conflict
                                          else f"đứng yên phía sau window_end (idx {_ci_b}<{_route_b.window_end})")
                            print(f"[LINE_AGV] {agv_id}: {_stuck_why} tại {_ct_b} "
                                  f"quá lâu → re-check định kỳ (đề phòng không ai kích lại)")
                            self._check_rolling_plan(agv_id, state)
                            # Tận dụng đúng nhịp watchdog này (chạy định kỳ cho MỌI xe
                            # đang bị nghi "kẹt") để kiểm tra luôn CẢ HỆ THỐNG có đang bí
                            # hoàn toàn không (3+ xe khoá chéo nhau, _is_deadlocked_with
                            # chỉ bắt được 2 xe) — nếu có, cử 1 xe vào node chờ đã cấu
                            # hình (Map Editor) để nhường đường, KHÔNG động vào arbitration/
                            # reservation hiện có.
                            _stalled_agvs = traffic_coordinator.check_global_stall()
                            if _stalled_agvs:
                                try:
                                    from main import _dispatch_to_waiting_node as _dtwn
                                    _dtwn(_stalled_agvs)
                                except Exception as _e_stall:
                                    print(f"[LINE_AGV] global-stall dispatch error: {_e_stall}")
                            # PHÁT HIỆN THỰC TẾ (2026-10-03): nhánh re-check này trước đây
                            # CHỈ gửi lại ĐÚNG cửa sổ cũ (nudge) hoặc chờ check_global_stall()
                            # (chỉ kích khi ≥2 xe CÙNG LÚC bí quá GLOBAL_STALL_SEC) — không
                            # nhánh nào thử ĐƯỜNG KHÁC cho đúng CA xe này. Log thực tế: AGV03
                            # đứng yên 1 mình tại 103 (node kế 24 bị AGV01 đang ĐỨNG — không
                            # tính là "node_reserved_by_other" nên không bị skip ở _res_wait_b,
                            # nhưng _find_upcoming_conflict cũng không coi đó là conflict để
                            # tự reroute) gần 4 phút liền, không ai thử đường khác, vì
                            # check_global_stall() đòi ≥2 xe (AGV01/AGV04 vẫn nhích tag đều,
                            # chỉ AGV03 đứng im → không đạt ngưỡng ≥2). Vá: xe đứng im quá
                            # STALL_BYPASS_SEC → tự thử đường khác CÓ GIỚI HẠN (require_
                            # worthwhile=True, giống nhánh "following" ở _check_rolling_plan);
                            # nếu vẫn bí tới GLOBAL_STALL_SEC (xe này không được check_global_
                            # stall() cứu vì không đủ ≥2 xe) → mới chấp nhận cả đường dài hơn
                            # nhiều (unbounded) — giống nhánh head-on/deadlock đã làm, còn hơn
                            # đứng im vô thời hạn không ai kích lại.
                            _stalled_sec_b = (_now_b - traffic_coordinator._registered
                                              .get(agv_id, {}).get('last_progress_ts', _now_b))
                            if _stalled_sec_b > STALL_BYPASS_SEC:
                                if self._try_line_reroute(agv_id, state, _route_b, _ci_b,
                                                           require_worthwhile=True):
                                    return
                                if (_stalled_sec_b > GLOBAL_STALL_SEC
                                        and self._try_line_reroute(agv_id, state, _route_b,
                                                                    _ci_b)):
                                    return
                            # PHÁT HIỆN THỰC TẾ (2026-09-24, tiếp): _check_rolling_plan()
                            # ở trên, khi KHÔNG thấy conflict nào (_find_upcoming_conflict
                            # trả None), chỉ gửi lại cửa sổ (B — ROLLING WINDOW REFRESH)
                            # NẾU `remaining <= LOOKAHEAD//2` — tức window đã gần hết. Ca
                            # thực tế: xe kẹt giữa 1 window CÒN NHIỀU node phía trước
                            # (remaining lớn, vd window=[0→4] nhưng xe đứng yên tại idx=1)
                            # do plan không tới được firmware / firmware "rớt" giữa
                            # chừng mà KHÔNG có conflict gì cả → _check_rolling_plan
                            # coi "window vẫn còn đủ, không cần gửi" → KHÔNG làm gì, xe
                            # đứng im MÃI MÃI (đúng log thực tế: AGV01 kẹt tại node 8
                            # nhiều phút, "đứng yên phía sau window_end" cứ lặp lại mà
                            # không ai gửi lại plan). Nếu sau re-check vẫn đứng yên tại
                            # ĐÚNG tag cũ và KHÔNG có waiting_before_conflict mới (nghĩa
                            # là re-check không tìm thấy lý do chính đáng để chờ) → coi
                            # như "rớt gói/kẹt firmware thật", CHỦ ĐỘNG gửi lại nguyên cửa
                            # sổ hiện tại (force=True) để nudge — an toàn vì force chỉ
                            # gửi lại ĐÚNG plan xe lẽ ra đã có, không đổi route/hướng.
                            _route_b2 = self._routes.get(agv_id)
                            if (_route_b2 is not None and not state.driving
                                    and str(state.current_tag) == _ct_b
                                    and not _route_b2.waiting_before_conflict):
                                print(f"[LINE_AGV] {agv_id}: re-check không đổi gì, vẫn "
                                      f"đứng yên tại {_ct_b} → CHỦ ĐỘNG gửi lại cửa sổ "
                                      f"hiện tại (nudge, đề phòng firmware rớt plan)")
                                self._send_window(agv_id, _route_b2, _ci_b,
                                                  _route_b2.window_end,
                                                  _route_b2.is_complete, force=True)
                                # Vào đây nghĩa là re-check KHÔNG tìm thấy lý do hợp lệ
                                # nào (not waiting_before_conflict) — bắt đầu/tiếp tục
                                # tính "kẹt không rõ lý do" từ đây, TÁCH RIÊNG khỏi
                                # _stopped_since (mốc đó cố tình không reset trong lúc
                                # chờ hợp lệ để chu kỳ re-check 8s vẫn chạy đều — dùng
                                # nó cho CẢNH BÁO sẽ báo nhầm khi 1 đợt chờ-hợp-lệ tự
                                # nhiên kéo dài >60s rồi mới được giải phóng, đúng ca
                                # thực tế AGV03 chờ nút giao 28 bị AGV01 giữ >60s).
                                self._unexplained_stuck_since.setdefault(agv_id, _now_b)
                            else:
                                self._unexplained_stuck_since.pop(agv_id, None)
                            # Nudge có thể lặp vô hạn nếu xe không phản hồi vì lý do
                            # KHÔNG liên quan traffic (kẹt vật lý, MANUAL không thoát
                            # được, lỗi firmware) — traffic engine không có cách nào
                            # phân biệt việc này với "đang chờ hợp lệ". CẢNH BÁO một
                            # lần sau STUCK_ALERT_THRESHOLD để operator để ý, không tự
                            # ý thay đổi hành vi (vẫn tiếp tục nudge như cũ).
                            _unexp_since = self._unexplained_stuck_since.get(agv_id)
                            if (_unexp_since is not None
                                    and not self._stuck_warned.get(agv_id)
                                    and _now_b - _unexp_since >= STUCK_ALERT_THRESHOLD):
                                self._stuck_warned[agv_id] = True
                                _msg_stuck_b = (
                                    f"⚠️ AGV {agv_id}: đứng yên tại {_ct_b} quá "
                                    f"{STUCK_ALERT_THRESHOLD:.0f}s dù đã nudge nhiều lần và "
                                    f"đường phía trước không còn bị xe khác chặn — có thể "
                                    f"đang kẹt vật lý/firmware, KHÔNG phải do điều phối. "
                                    f"Cần kiểm tra xe trực tiếp.")
                                print(f"[LINE_AGV] {agv_id}: {_msg_stuck_b}")
                                self._set_alert(agv_id, state, "STUCK_UNEXPLAINED", _msg_stuck_b)
                                # PHÁT HIỆN THỰC TẾ (2026-09-25): cảnh báo này trước đây
                                # chỉ in ra console server — người vận hành không theo dõi
                                # console nên không hề biết xe đang kẹt thật (tưởng hệ
                                # thống "không báo lỗi gì cả"). Đẩy qua Telegram, cùng cơ
                                # chế đã dùng cho cảnh báo lỗi móc hàng (notify_error).
                                try:
                                    from telegram_bot import notify_error as _tg_notify_stuck_b
                                    _tg_notify_stuck_b(_msg_stuck_b)
                                except Exception as _e_tg_stuck_b:
                                    print(f"[LINE_AGV] {agv_id}: gửi Telegram cảnh báo kẹt lỗi: {_e_tg_stuck_b}")
                        else:
                            # Xác định ĐÚNG event cần sinh: đọc action code CUỐI CÙNG nhắm
                            # tới node hiện tại trong plan vừa gửi — luôn là hành động
                            # "arrival" cho node biên (build_plan_window luôn kết thúc 1
                            # cửa sổ bằng action đó).
                            _ev_gen = 'arrived_wait_sys'
                            try:
                                _pending_b = self._pending_cmds.get(agv_id) or {}
                                _steps_b = (_pending_b.get('payload') or {}).get('d') or []
                                _last_b = next((s for s in reversed(_steps_b)
                                                if str(s.get('t')) == _ct_b), None)
                                if _last_b is not None:
                                    _act_map_b = {1: 'arrived_wait_sys', 2: 'arrived_wait_user',
                                                  35: 'arrived_wait_charge'}
                                    _ev_gen = _act_map_b.get(_last_b.get('a'), _ev_gen)
                            except Exception:
                                pass
                            print(f"[LINE_AGV] {agv_id}: KẸT tại node biên {_ct_b} (đích đoạn "
                                  f"{_route_b.task_type}) — KHÔNG nhận {_ev_gen} → TỰ SINH để hoàn tất")
                            self._handle_event(agv_id, _ev_gen, {}, state)
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

        PHÁT HIỆN THỰC TẾ (2026-09-29, deadlock AGV03↔AGV04 tại 28↔104): trước đây,
        khi other_id KHÔNG còn đăng ký (đã deregister — vd thua head-on không có
        nhánh né, rơi vào pending_retry_cmd đứng yên), hàm này rơi xuống dùng
        self._routes[other_id] — route CACHE CŨ, có thể đã LỖI THỜI so với ý định
        di chuyển thật (route cũ không hề chứa node hiện tại của xe kia nữa) —
        khiến kết quả sai lệch so với đúng docstring đã ghi ("không đăng ký = coi
        khác chiều để an toàn"). Hậu quả thực tế: AGV04 thua head-on, đứng yên tại
        104 không đăng ký gì cả, nhưng AGV03 lại bị phân loại "following" (cùng
        chiều) → chỉ đứng chờ AGV04 tự dời đi — mà AGV04 cũng chỉ ngồi chờ AGV03
        dời trước → CẢ HAI đứng chờ nhau vô thời hạn (không ai được coi là head-on
        thật để kích hoạt né/lùi). Sửa: bỏ hẳn fallback self._routes — không đăng
        ký thì LUÔN trả False (khác chiều), đúng như docstring, để xe đối diện một
        AGV đã dừng-không-đăng-ký được xử lý như head-on (có thể né/lùi) thay vì
        "following" (chỉ biết đứng chờ).
        """
        other_reg = traffic_coordinator._registered.get(other_id)
        if not other_reg:
            return False
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
                # QUAN TRỌNG (phát hiện thực tế 2026-09-18): reservation ở đây được
                # cấp bởi reserve_ahead() — vốn giữ chỗ theo SỐ NODE cố định phía
                # trước chủ khoá, KHÔNG theo thời gian thực. Trên các đoạn đường dài/
                # tốc độ thấp, "vài node phía trước" của chủ khoá có thể là RẤT XA về
                # thời gian thực (hàng chục/hàng trăm giây) — xe MÌNH bị chặn đứng
                # ngay tại chỗ dù chủ khoá còn cách rất lâu mới tới, dù còn đường khác
                # đi được (đúng phản ánh thực tế: xe đã xong việc phải đứng chờ vì xe
                # kia "còn xa mới đến"). So sánh THỜI GIAN THẬT (khoảng cách+tốc độ,
                # xem _estimate_travel_seconds) — nếu chủ khoá còn quá xa so với chính
                # mình, CHƯA cần chờ ngay, cứ đi tiếp: reservation THẬT của chủ khoá
                # (qua _owner_committed_to/_owner_at_node trong _reserve_node) vẫn bảo
                # vệ an toàn đúng lúc khi mình THỰC SỰ tới gần node đó sau này.
                _is_headon_res    = (_headon == _res_owner)
                # PHÁT HIỆN THỰC TẾ (2026-09-23): ngã rẽ/cùng chiều — đếm TRỰC TIẾP số
                # node chủ khoá còn phải đi (trên CHÍNH route đã đăng ký của nó) để tới
                # `tn`, KHÔNG suy qua ước lượng thời gian/tốc độ (phụ thuộc cấu hình tốc
                # độ từng cạnh, có thể sai lệch nếu map thiếu 'speed'). Đúng yêu cầu
                # người dùng: "xe kia còn cách 3-4 node thì cứ đi tiếp, cách 2 node mới
                # dừng chờ" — khớp thuật ngữ "2-node gap" hệ thống đã dùng sẵn ở chỗ
                # khác (an toàn: reservation thật của chủ khoá vẫn bảo vệ khi mình tới
                # gần node đó sau này, xem comment gốc phía trên).
                # PHÁT HIỆN THỰC TẾ (2026-09-24, va chạm vật lý): mọi khoan nhượng
                # "chủ khoá còn xa → cứ đi tiếp" dưới đây CHỈ áp dụng khi tn KHÔNG
                # phải nút giao (degree<3) — tại nút giao, ước lượng ETA/số-node có
                # thể sai lệch đúng lúc 2 xe cùng hội tụ → luôn coi là chặn cứng,
                # rơi thẳng xuống xử lý head-on/chờ bên dưới. Cơ chế chung (tự suy
                # từ đồ thị qua _is_junction), không khai báo tay theo map.
                _tn_is_junction = traffic_coordinator._is_junction(tn)
                if not _is_headon_res and not _tn_is_junction:
                    _owner_reg_j  = traffic_coordinator._registered.get(_res_owner, {})
                    _owner_path_j = _owner_reg_j.get('path', [])
                    _owner_idx_j  = _owner_reg_j.get('current_idx', 0)
                    if _owner_path_j:
                        try:
                            _tn_idx_owner_j    = _owner_path_j.index(str(tn), _owner_idx_j)
                            _owner_nodes_away  = _tn_idx_owner_j - _owner_idx_j
                            if _owner_nodes_away >= JUNCTION_SAFE_NODE_GAP:
                                print(f"[TRAFFIC] {agv_id}: {tn} bị {_res_owner} giữ chỗ "
                                      f"nhưng xe đó còn cách {_owner_nodes_away} node (ngã "
                                      f"rẽ/cùng chiều, ngưỡng {JUNCTION_SAFE_NODE_GAP}) → "
                                      f"CHƯA cần chờ, đi tiếp")
                                continue
                        except ValueError:
                            pass
                if not _tn_is_junction:
                    _my_eta_res       = _estimate_travel_seconds(path, from_idx, i + 1)
                    _other_eta_res    = traffic_coordinator._eta_to_node(_res_owner, tn)
                    if _my_eta_res is not None and _other_eta_res is not None:
                        if _is_headon_res:
                            _threshold_res = _headon_safe_threshold(_my_eta_res, i + 1 - from_idx)
                        else:
                            # Ngã rẽ/cùng chiều — xem giải thích đầy đủ ở JUNCTION_PREDICT_BUFFER_SEC.
                            _threshold_res = _my_eta_res + JUNCTION_PREDICT_BUFFER_SEC
                        if _other_eta_res > _threshold_res:
                            print(f"[TRAFFIC] {agv_id}: {tn} bị {_res_owner} giữ chỗ nhưng xe đó "
                                  f"còn cách ~{_other_eta_res:.0f}s (mình ~{_my_eta_res:.0f}s, "
                                  f"ngưỡng an toàn {_threshold_res:.0f}s) → CHƯA cần chờ, đi tiếp "
                                  f"(reservation thật vẫn bảo vệ khi tới gần)")
                            continue
                else:
                    print(f"[TRAFFIC] {agv_id}: {tn} là NÚT GIAO (degree≥3), bị {_res_owner} "
                          f"giữ chỗ → BỎ QUA khoan nhượng ETA, xử lý như chặn cứng")
                if _is_headon_res:
                    # Head-on thật. CHỈ bên THUA arbiter mới reroute/né; bên THẮNG CHỜ
                    # (xe thua sẽ né → node trống → ta đi). KHÔNG để CẢ HAI cùng reroute
                    # → cùng nhảy nhánh khác → vẫn đâm (dao động).
                    if traffic_coordinator._arbitrate(agv_id, _res_owner, _canon_edge_node(fn, tn)) == agv_id:
                        print(f"[TRAFFIC] {agv_id}: {tn} bị {_res_owner} (head-on) nhưng TÔI "
                              f"thắng arbiter → CHỜ ({_res_owner} sẽ né)")
                        _bump_traffic_stat("junction", "HEADON_WIN_WAIT")
                        # Trả i (head-on) chứ KHÔNG -(i+1) (following): winner cứ để
                        # nhánh head-on xử lý (đứng chờ, loser né); nhánh following sẽ
                        # cho winner tự đi vòng → hai xe cùng di chuyển, dao động.
                        return i
                    print(f"[TRAFFIC] {agv_id}: {tn} bị {_res_owner} khoá (head-on) → tôi nhường+reroute")
                    _bump_traffic_stat("junction", "HEADON_LOSE_REROUTE")
                    return i
                # Ngã rẽ / cùng chiều → chờ trước node cho xe kia đi qua (không reroute).
                # PHÁT HIỆN THỰC TẾ (2026-10-09, mô phỏng SIM02/SIM05): "xe kia" (_res_owner)
                # giữ tn chỉ vì ĐANG kẹt head-on với CHÍNH agv_id này ở 1 cạnh khác xa hơn
                # trên route (vd agv_id tới tn qua nhánh A, nhưng tn cũng là bước đệm trước
                # 1 cạnh mà agv_id và _res_owner đối đầu thật) → "chờ xe kia đi qua" không
                # bao giờ xảy ra (xe kia cũng đang chờ NGƯỢC LẠI agv_id né ở cạnh đó) → cả 2
                # đứng im vĩnh viễn, vòng chờ nhau không ai được phép né (nhánh "ngã rẽ/cùng
                # chiều" vốn CHỦ Ý không reroute). Dùng lại ĐÚNG ngưỡng/đại lượng đã có sẵn
                # cho ca tương tự (STALL_BYPASS_SEC + last_progress_ts, xem nhánh A ở trên) —
                # agv_id đứng im quá lâu không rõ lý do hợp lệ nào khác → coi như head-on
                # (return i, không phải -(i+1)) để cơ chế reroute/thoát-deadlock SẴN CÓ của
                # caller tự xử lý, KHÔNG tự viết thêm logic né mới ở đây.
                _stalled_sec_jr = (time.monotonic() - traffic_coordinator._registered
                                   .get(agv_id, {}).get('last_progress_ts', time.monotonic()))
                if _stalled_sec_jr > STALL_BYPASS_SEC:
                    print(f"[TRAFFIC] {agv_id}: {tn} bị {_res_owner} khoá (ngã rẽ/cùng chiều) "
                          f"nhưng đã đứng im {_stalled_sec_jr:.0f}s (>{STALL_BYPASS_SEC:.0f}s) → "
                          f"có thể {_res_owner} đang kẹt head-on ngược lại chính mình, thử "
                          f"đường khác thay vì chờ mãi")
                    _bump_traffic_stat("junction", "STALL_BYPASS_REROUTE")
                    return i
                print(f"[TRAFFIC] {agv_id}: {tn} bị {_res_owner} khoá (ngã rẽ/cùng chiều) → chờ")
                _bump_traffic_stat("junction", "JUNCTION_WAIT")
                return -(i + 1)

            # 4. Head-on DỰ ĐOÁN (xe kia CHƯA khoá tn — không có reservation thật, chỉ
            #    suy từ TOÀN BỘ route còn lại của nó, có thể còn rất xa): TRƯỚC KHI xử
            #    lý như mối đe doạ thật, so sánh THỜI GIAN THẬT (khoảng cách+tốc độ, xem
            #    _estimate_travel_seconds) xe kia cần để tới `tn` với chính mình — xe kia
            #    còn quá xa về THỜI GIAN (đang bận việc khác ở xa) thì CHƯA phải mối đe
            #    doạ hiện tại, bỏ qua lần này (không tính vào node/edge count như trước —
            #    "5 node" có thể là rất xa hoặc rất gần tuỳ cạnh dài/ngắn, nhanh/chậm).
            if _headon:
                # Nút giao (degree≥3): KHÔNG khoan nhượng theo ETA dự đoán — buộc phân
                # xử arbiter NGAY (xem _is_junction()), tránh đúng ca va chạm thực tế
                # (2 xe cùng "tưởng còn xa" rồi hội tụ đúng lúc tại 1 nút giao).
                if not traffic_coordinator._is_junction(tn):
                    _my_eta_tn    = _estimate_travel_seconds(path, from_idx, i + 1)
                    _other_eta_tn = traffic_coordinator._eta_to_node(_headon, tn)
                    if _my_eta_tn is not None and _other_eta_tn is not None:
                        _threshold = _headon_safe_threshold(_my_eta_tn, i + 1 - from_idx)
                        if _other_eta_tn > _threshold:
                            print(f"[TRAFFIC] {agv_id}: head-on TƯƠNG LAI {fn}→{tn} với {_headon} "
                                  f"nhưng xe đó còn cách ~{_other_eta_tn:.0f}s (mình ~{_my_eta_tn:.0f}s, "
                                  f"ngưỡng {_threshold:.0f}s) → CHƯA phải mối đe doạ, đi tiếp")
                            continue
                if traffic_coordinator._arbitrate(agv_id, _headon, _canon_edge_node(fn, tn)) == agv_id:
                    print(f"[TRAFFIC] {agv_id}: head-on {fn}→{tn} với {_headon} "
                          f"→ TÔI ưu tiên (arbiter), đi tiếp")
                    continue
                print(f"[TRAFFIC] {agv_id}: head-on {fn}→{tn} → nhường {_headon} (arbiter)")
                return i

        return None

    @_agv_scoped
    def _try_line_reroute(
        self, agv_id: str, state: LineAGVState,
        route: LineAGVRoute, current_idx: int,
        extra_blocked_nodes: Optional[set] = None,
        avoid_all: bool = False,
        require_worthwhile: bool = False,
        max_extra: Optional[int] = None,
        max_extra_sec: Optional[float] = None,
    ) -> bool:
        """
        Tìm đường thay thế tránh edges/nodes đang bị chiếm.
        max_extra: (cùng require_worthwhile) đường mới không được dôi quá chừng này node so với đường cũ
        (tuyệt đối, thay cho điều kiện tỉ lệ).
        max_extra_sec: đường mới không được tốn thêm quá chừng này GIÂY đi (tính theo độ dài thật / tốc độ danh
        định) — dùng khi đã ước tính được thời gian chờ xe chắn (xem estimate_clear_wait_sec). Áp dụng cả khi
        require_worthwhile=False (vd xe thua head-on).
        extra_blocked_nodes: set các node cần tránh thêm (vd: vật cản vật lý phía trước).
        avoid_all=True: né đường của MỌI xe đăng ký (không chỉ xe mạnh hơn) — dùng khi
        BUỘC phải rời đường hiện tại vì vật cản (quy tắc bất đối xứng không áp dụng:
        mình đã không thể giữ đường ngắn nữa, reroute mù vào hành lang xe khác = đâm).
        require_worthwhile=True: CHỈ nhận đường thay thế nếu KHÔNG dài hơn đáng kể so
        với đường cũ (xem REROUTE_WORTHWHILE_* dưới) — dùng cho nhánh "còn đường khác
        thì đi luôn" (following, tự chọn, không bắt buộc phải rời đường như vật cản/
        deadlock). PHÁT HIỆN THỰC TẾ (2026-09-28): không giới hạn gì → 1 xe chặn có
        1-2 node cũng có thể khiến xe kia vòng qua 8-10 node khác để né, 2 xe cùng làm
        vậy với nhau tạo vòng lặp đuổi nhau qua lại rất lâu (nhìn giống "đi lung tung")
        dù chỉ cần đứng chờ vài giây là xong. avoid_all=True (buộc rời đường vì vật
        cản) và các ca deadlock/head-on khác KHÔNG dùng cờ này — ở đó không có lựa
        chọn "đứng chờ" an toàn, nên đường dài cỡ nào cũng phải chấp nhận.
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

            # ── CHỐNG FLIP-FLOP: reroute vừa làm < REROUTE_COOLDOWN giây trước → KHÔNG
            #    reroute lại (sẽ lật về nhánh kia của vòng → dao động + plan-race). Để
            #    caller rơi xuống WAIT-BASED (đứng chờ tại chỗ) — đã COMMIT nhánh vừa chọn.
            #    PHÁT HIỆN THỰC TẾ (2026-09-23): trước đây chỉ áp cooldown khi avoid_all=True
            #    (obstacle-reroute) — nhánh "còn đường khác → đi đường khác" (avoid_all=False,
            #    gọi mỗi khi rolling-plan re-check phát hiện xe khác chắn đường) KHÔNG có
            #    cooldown, nên khi 2-3 xe cùng đổi đường liên tục (mỗi xe đổi lại kích xe
            #    kia đổi theo), 1 xe có thể tính lại đường 6-7 LẦN chỉ trong ~50 giây, không
            #    bao giờ thực sự di chuyển — và tệ hơn, có thể tự đổi NGƯỢC LẠI đúng đường
            #    vừa bị obstacle-reroute né ra (2 cơ chế né khác nhau không biết về nhau).
            #    Áp cooldown CHUNG cho MỌI lần gọi (bỏ điều kiện avoid_all) — nếu bị chặn,
            #    caller vẫn có fallback an toàn (đứng chờ/đỗ-né) như thiết kế sẵn có.
            _now_rr = time.monotonic()
            # PHÁT HIỆN THỰC TẾ (2026-10-02): cooldown trên tự nó có thể trở thành cái
            # bẫy khi cả hệ thống đang THỰC SỰ bế tắc (vd 2+ xe khoá chéo reservation
            # của nhau) — mỗi lần watchdog đánh thức lại rơi vào nhánh "vừa reroute <
            # 18s", xe KHÔNG BAO GIỜ thực sự thử đường khác dù đã đứng im rất lâu (log
            # thực tế: 3 xe cùng đứng im >2 phút, liên tục in dòng "chống dao động" này).
            # Lối thoát CHẶT: chỉ bỏ qua cooldown khi xe đã đứng im (current_idx không
            # đổi) LÂU HƠN cooldown một khoảng an toàn (STALL_BYPASS_SEC > REROUTE_COOLDOWN)
            # — không ảnh hưởng các ca chờ ngắn bình thường, chỉ kích hoạt khi cooldown
            # thật sự là rào cản cuối cùng còn lại.
            _last_progress = (traffic_coordinator._registered.get(agv_id, {})
                               .get('last_progress_ts', _now_rr))
            _stalled_sec = _now_rr - _last_progress
            if _now_rr - self._reroute_ts.get(agv_id, 0.0) < REROUTE_COOLDOWN:
                if _stalled_sec > STALL_BYPASS_SEC:
                    print(f"[LINE_AGV] {agv_id}: cooldown reroute bị bỏ qua — xe đứng im "
                          f"{_stalled_sec:.0f}s không tiến được, thử đường khác")
                else:
                    print(f"[LINE_AGV] {agv_id}: BỎ reroute (vừa reroute < {REROUTE_COOLDOWN:.0f}s "
                          f"→ giữ nhánh đã chọn, chờ tại chỗ — chống dao động lật nhánh)")
                    return False

            # ── CHỐNG LẬT NHÁNH DÀI HẠN: nhánh "còn đường khác thì đi" (require_worthwhile, tự
            #    chọn, không bắt buộc) mà đã reroute >= FLIP_MAX lần trong FLIP_WINDOW_SEC → vòng
            #    lặp 2 nhánh bị xe khác luân phiên giữ chỗ (mô phỏng 2026-10-14: SIM02 lật 22↔21↔33
            #    ~4 phút). Dừng đổi, đứng chờ nhánh hiện tại. Reroute bắt buộc (avoid_all/deadlock)
            #    KHÔNG bị ảnh hưởng.
            if require_worthwhile and not avoid_all:
                _hist = [t for t in self._reroute_hist.get(agv_id, []) if _now_rr - t < 150.0]
                self._reroute_hist[agv_id] = _hist
                if len(_hist) >= 3 and _stalled_sec <= STALL_BYPASS_SEC * 2:
                    print(f"[LINE_AGV] {agv_id}: đã đổi đường {len(_hist)} lần trong 150s → "
                          f"KHÔNG đổi nữa, đứng chờ (chống lật nhánh vòng)")
                    return False

            _left_sigs = [(t, sg) for t, sg in self._reroute_left.get(agv_id, []) if _now_rr - t < 150.0]
            self._reroute_left[agv_id] = _left_sigs

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
                # YÊU CẦU THỰC TẾ (2026-09-18): TRƯỚC ĐÂY chỉ né đường xe MẠNH hơn (bất
                # đối xứng, chống dao động khi cả 2 cùng né nhau nhảy sang 1 nhánh mới rồi
                # vẫn đâm). Nhưng gốc rủi ro dao động đó CHỈ áp dụng cho đối đầu trực diện
                # THẬT (head-on) — nơi CẢ HAI xe cùng lúc đánh giá tình huống và có thể
                # cùng quyết định né. Hàm này còn được gọi cho ca "following/reservation
                # tạm thời" (1 xe bị 1 xe khác giữ chỗ ngắn hạn, xe kia không hề phản ứng
                # lại quyết định của mình) — ở đây CHỈ 1 phía tự quyết, không có rủi ro
                # dao động, nhưng luật bất đối xứng cũ lại cấm luôn cả xe "mạnh" (ưu tiên
                # cao/ID nhỏ) thử đường vòng dù có sẵn (vd AGV03 mạnh hơn AGV04 nhưng vẫn
                # đứng chờ AGV04 đi qua node 28 dù còn đường vòng qua 29/27/26 chỉ dài hơn
                # ~35%). User yêu cầu: MỌI xe đều được né nhau, chỉ đứng chờ khi THẬT SỰ
                # hết đường — an toàn vì việc CÓ đối đầu trực diện thật hay không (và ai
                # thắng khi đó) vẫn do arbiter/should_avoid_path_of ở TẦNG GỌI quyết định
                # riêng (chỉ đúng 1 bên — bên thua — được gọi hàm này trong nhánh head-on
                # thật; xem _am_winner ở _check_rolling_plan) — bỏ gate ở đây không làm
                # winner head-on tự nhiên né theo.
                pass
                # Ưu tiên TUYẾN ĐẦY ĐỦ (intent) — biết cả phần sẽ đi sau khi dispatch
                # chia đoạn / đang đứng chờ (vd 18→5→17 của xe chờ tới 17).
                _intent = traffic_coordinator._intent_route.get(_oid)
                if _intent and len(_intent) >= 2:
                    _op = _intent
                    # Suy vị trí THẬT trong intent theo current_tag — tránh phạt nhầm các
                    # cạnh xe đó ĐÃ ĐI QUA XONG và đang đứng chờ xác nhận ở cuối đường (xem
                    # giải thích đầy đủ ở bản vá tương tự trong mqtt_client.py, 2026-09-21).
                    _oc = 0
                    try:
                        _ost_intent2 = self.state_store.get(_oid)
                        if _ost_intent2 and _ost_intent2.current_tag is not None:
                            _oc = _intent.index(str(_ost_intent2.current_tag))
                    except ValueError:
                        pass
                else:
                    _oreg = traffic_coordinator._registered.get(_oid, {})
                    _op = _oreg.get('path', []); _oc = _oreg.get('current_idx', 0)
                for _j in range(_oc, len(_op) - 1):
                    _a, _b = str(_op[_j]), str(_op[_j + 1])
                    _bump(_a, _b, _PEN_PATH); _bump(_b, _a, _PEN_PATH)
            # Né VỊ TRÍ xe đang DỪNG (driving=False). TRƯỚC ĐÂY bất đối xứng (chỉ né xe
            # mạnh hơn) cùng lý do/cùng gỡ bỏ như khối phạt TRAJECTORY phía trên — mọi xe
            # đều được né vị trí xe khác đang đứng, chỉ đứng chờ khi thật sự hết đường.
            for _oid2, st in self.state_store._states.items():
                if (_oid2 == agv_id or st is None or st.current_tag is None
                        or getattr(st, 'driving', False)):
                    continue
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

            # ── CHỐNG QUAY LẠI NHÁNH VỪA BỎ (A→B→A): vòng có 2 nhánh mà mỗi nhánh bị 1 xe khác
            #    giữ chỗ thì đổi sang nhánh kia chỉ để bị xe còn lại chặn, rồi lại đổi về
            #    (mô phỏng 2026-11-03: SIM02 lật 39→40→15 ↔ 39→38→37 ~6 phút, 8 lần reroute). Mốc
            #    "đứng im" không còn miễn được ở đây vì lật qua lại không tính là tiến; chỉ cho
            #    quay lại nhánh cũ khi đã đứng im rất lâu (> 4×STALL_BYPASS_SEC). Reroute bắt buộc
            #    (avoid_all) không bị ảnh hưởng.
            if (require_worthwhile and not avoid_all and _left_sigs
                    and tuple(new_path[:4]) in {sg for _, sg in _left_sigs}
                    and _stalled_sec <= STALL_BYPASS_SEC * 4):
                print(f"[LINE_AGV] {agv_id}: BỎ đổi đường (nhánh {list(new_path[:4])} vừa bỏ "
                      f"<150s trước — quay lại chỉ để bị xe kia chặn) → đứng chờ")
                return False

            # ── Chặn đường vòng QUÁ DÀI so với việc đứng chờ (chỉ khi tự chọn) ──────
            # require_worthwhile=True: đường thay thế chỉ được chấp nhận nếu KHÔNG dài
            # hơn đường cũ quá nhiều — nếu không, đứng chờ vài giây rẻ hơn nhiều so với
            # vòng qua hàng chục node xa lạ (và 2 xe cùng làm vậy sẽ đuổi nhau qua lại
            # rất lâu, xem comment ở chữ ký hàm).
            if max_extra_sec is not None:
                _extra_m = (path_length_m(new_path) - path_length_m(route.full_path[current_idx:]))
                _extra_s = _extra_m / max(AGV_NOMINAL_SPEED_MPS, 0.05)
                if _extra_s > max_extra_sec:
                    print(f"[LINE_AGV] {agv_id}: BỎ đi-đường-khác (đường vòng tốn thêm ~{_extra_s:.0f}s "
                          f"> ngưỡng {max_extra_sec:.0f}s ≈ thời gian chờ xe chắn thoát) → đứng chờ")
                    return False
            if require_worthwhile:
                _old_len_rr = len(route.full_path) - current_idx
                _new_len_rr = len(new_path)
                if ((max_extra is not None and _new_len_rr > _old_len_rr + max_extra)
                        or (max_extra is None
                            and _new_len_rr > _old_len_rr + REROUTE_WORTHWHILE_MAX_EXTRA
                            and _new_len_rr > _old_len_rr * REROUTE_WORTHWHILE_MAX_RATIO)):
                    print(f"[LINE_AGV] {agv_id}: BỎ đi-đường-khác (đường vòng {_new_len_rr} "
                          f"node dài hơn nhiều so với {_old_len_rr} node còn lại của đường "
                          f"cũ) → đứng chờ thay vì vòng xa")
                    return False

            # ── KHÔNG tự ép đổi hướng bwd→fwd khi nhánh thay thế rẽ khỏi nhánh cũ ──
            # TRƯỚC ĐÂY (2026-09-28) có đoạn ép route.direction='fwd' tại đây nếu nhánh
            # thay thế đi sang node kế khác hẳn và node hiện tại không đánh dấu riêng
            # approach_dir=bwd/wait_charge — cùng tiền đề SAI đã rút lại ở main.py
            # _dispatch_go_to (xem comment _cur_needs_bwd_exit): mũi xe KHÔNG tự đổi
            # hướng chỉ vì node hiện tại thiếu đánh dấu, nó chỉ đổi khi THỰC SỰ có 1 cú
            # rẽ vật lý xảy ra. Reroute ở đây chỉ đổi NHÁNH kế tiếp (vẫn cùng 1 lần tới
            # node hiện tại, chưa có rẽ nào xảy ra) — ép sang fwd+rẽ tại đây khiến lệnh
            # rẽ không khớp hướng mũi xe thật, xe lái sai nhánh THẬT ngoài đời. PHÁT
            # HIỆN THỰC TẾ (2026-10-01): AGV04 lùi ra 98→6 (đúng), reroute đổi nhánh
            # kế tiếp tại 6 từ 10 sang 98 → bản vá cũ ép sang fwd+TURN_R (vì 6 không có
            # approach_dir=bwd) → xe rẽ sai, vật lý trôi tới node 3 (TRẠM SẠC) thay vì
            # 98, kẹt cứng rồi off_route. Giữ nguyên route.direction như cũ (bwd vẫn bwd)
            # — để turn_map tự tính đúng theo cặp (from, to, bwd) THẬT của nhánh mới,
            # không áp logic đổi gear ở đây.

            # Cập nhật route
            self._reroute_left.setdefault(agv_id, []).append(
                (time.monotonic(), tuple(route.full_path[current_idx:current_idx + 4])))
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

            new_end  = _time_capped_window_end(
                route.full_path, current_idx,
                min(current_idx + LOOKAHEAD, len(route.full_path) - 1))
            is_final = (new_end == len(route.full_path) - 1)
            # PHẢI force=True: đường ĐÃ ĐỔI nên cửa sổ cũ (chạy tới node của đường cũ) không còn
            # hợp lệ. Nếu chỉ số cửa sổ trùng lần gửi trước, dedup trong _send_window sẽ BỎ QUA
            # im lặng → xe vật lý vẫn chạy nốt plan CŨ trong khi server tưởng nó đã đi đường mới.
            # PHÁT HIỆN THỰC TẾ (mô phỏng 2026-10-13): SIM02 "REROUTED" ra xa node 40 nhưng không
            # có plan mới nào được gửi, xe cứ tiến vào 40 (đang có SIM01 đứng) → va chạm; watchdog
            # va chạm vật lý cũng mù vì tag của xe không còn nằm trong route đã đổi.
            self._send_window(agv_id, route, current_idx, new_end, is_final, force=True)
            self._reroute_ts[agv_id] = time.monotonic()   # mốc chống flip-flop (mọi loại reroute)
            self._reroute_hist.setdefault(agv_id, []).append(self._reroute_ts[agv_id])
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

    @_agv_scoped
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
                    _bn_end = _time_capped_window_end(
                        route.full_path, current_idx,
                        min(current_idx + LOOKAHEAD, len(route.full_path) - 1))
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
                        # Đích nằm trong VÙNG CẤM của loại xe này → lệnh không bao giờ thực hiện
                        # được: BỎ lệnh (không đặt lại pending_retry), tránh thử lại vô tận.
                        try:
                            from mqtt_client import map_manager as _mm_zr
                            if not _mm_zr.is_node_allowed(oid, _dest_r):
                                print(f"[LINE_AGV] {oid}: bỏ lệnh chờ go_to {_dest_r} — node thuộc VÙNG CẤM "
                                      f"của loại xe này")
                                continue
                        except Exception:
                            pass
                        # Đánh giá lại ngay lúc retry: nếu _dest_r là supply node
                        # (vd 98) và có node tương đương cùng supply_group (vd 99)
                        # đã trống hơn — đổi sang đó thay vì bám cứng node cũ (xem
                        # comment ở main._reevaluate_supply_node).
                        try:
                            from main import _reevaluate_supply_node as _resn
                            _cur_r = str(st.current_tag) if st.current_tag is not None else None
                            _alt_r = _resn(_dest_r, oid, _cur_r)
                            if _alt_r and _alt_r != _dest_r:
                                print(f"[LINE_AGV] {oid}: node cấp hàng {_dest_r} vẫn bận "
                                      f"lúc retry → đổi sang node tương đương {_alt_r}")
                                _dest_r = _alt_r
                        except Exception:
                            pass
                        # Xe đang BẬN lệnh khác và hàng đợi đã có đúng go_to này → không xếp thêm bản trùng
                        # (trước đây mỗi lần xe khác di chuyển lại xếp thêm 1 bản: SIM06 dồn 22 lệnh go_to trùng).
                        if _atq_r.is_busy(oid) and any(
                                str(q.get("dest_node")) == str(_dest_r) and q.get("command") == _CGT_r
                                for q in _atq_r.get_queue(oid)):
                            continue
                        print(f"[LINE_AGV] {oid}: dest-wait retry triggered by {moved_agv_id} → go_to {_dest_r} (session={_sess_r})")
                        _rcmd_r, _rok_r = _atq_r.dispatch_or_queue(
                            oid, _CGT_r, dest_node=_dest_r, start_node=None,
                            session_id=_sess_r, session_label='dest_retry')
                        # dispatch_or_queue trả ok=False cả khi xe bận và lệnh chỉ được XẾP HÀNG (status queued) —
                        # đó không phải thất bại: lệnh sẽ chạy khi lệnh hiện tại xong.
                        if not _rok_r and getattr(_rcmd_r, "status", None) == "queued":
                            _rok_r = True
                        # PHÁT HIỆN THỰC TẾ (2026-10-01, AGV04 kẹt vĩnh viễn sau khi
                        # dispatch_fn ném exception): nếu dispatch THẤT BẠI (ok=False —
                        # vd lỗi tạm thời trong _dispatch_go_to bị main.py._queue_dispatch
                        # bắt và nuốt thành "dispatch failed"), trước đây KHÔNG ai đặt lại
                        # pending_retry_cmd/dest (đã xoá ở dòng trên trước khi gọi) → AGV
                        # rơi vào trạng thái "rảnh nhưng không còn ai theo dõi để kích lại"
                        # VĨNH VIỄN, trong khi các lệnh go_to kế tiếp vẫn còn nguyên trong
                        # hàng đợi (insert_next trước đó) chờ đích NÀY xong mới tới lượt.
                        # Đúng log thực tế: AGV04 '[QUEUE_DISPATCH] error:' (thông báo rỗng)
                        # rồi im lặng hoàn toàn, không timeout/cảnh báo nào cứu được vì mọi
                        # watchdog "kẹt" đều dựa vào pending_retry_cmd/route đang có — cả 2
                        # đều đã bị xoá. Đặt lại để watchdog monitor_pending_retry_stuck
                        # (main.py) tự thử lại sau — AN TOÀN vì chỉ redo đúng go_to đã thất
                        # bại, không đổi gì khác; nếu lỗi gốc là tạm thời (vd race dữ liệu),
                        # lần thử sau nhiều khả năng qua được.
                        if not _rok_r:
                            st.pending_retry_cmd     = 'go_to'
                            st.pending_retry_dest    = _dest_r
                            st.pending_retry_session = _sess_r
                            print(f"[LINE_AGV] {oid}: dest-wait retry THẤT BẠI (dispatch lỗi) "
                                  f"→ đặt lại pending_retry để thử lại sau, không bỏ rơi lệnh")
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

    @_agv_scoped
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
            # PHÁT HIỆN THỰC TẾ (2026-09-28): route.task_type=='transit' nghĩa là
            # dest_final CHỈ là điểm đỗ tạm (staging), không phải đích giao/lấy hàng
            # thật — y hệt lý do đã xử lý cho off_route (xem đó). Nếu không đánh dấu
            # lại _pending_staging_transits ở đây, lần dispatch lại tới dest_final
            # (do _dispatch_go_to gọi sau khi queue) sẽ mặc định coi nó là đích thật
            # ('delivery') → hạ móc nhầm tại node tạm (đúng lỗi thực tế: AGV01 hạ móc
            # tại node 31 — chỉ là điểm đỗ tạm khi đích 106 đang bị chiếm — sau khi
            # bị lùi né đối đầu rồi queue lại đúng node 31 này lần 2).
            if route.task_type == "transit":
                try:
                    from main import _pending_staging_transits as _pst_bu
                    _pst_bu.add((agv_id, str(dest_final)))
                except Exception:
                    pass
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

    @_agv_scoped
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
            # PHÁT HIỆN THỰC TẾ (2026-09-28): _task_type=='transit' nghĩa là `dest`
            # chỉ là điểm đỗ tạm (staging), không phải đích giao/lấy hàng thật — y hệt
            # lý do đã xử lý cho off_route và _back_up_to_prev (xem đó). Thiếu đánh dấu
            # lại _pending_staging_transits ở đây khiến lần dispatch lại tới `dest` bị
            # coi là đích thật ('delivery') → hạ móc nhầm tại node tạm (đúng lỗi thực
            # tế: AGV01 bị head-on với AGV03, lùi né rồi queue lại đúng node 31 — vốn
            # chỉ là điểm đỗ tạm vì đích thật 106 đang bị AGV04 chiếm — và hạ móc nhầm
            # ngay tại 31).
            if _task_type == "transit":
                try:
                    from main import _pending_staging_transits as _pst_ho
                    _pst_ho.add((agv_id, str(dest)))
                except Exception:
                    pass
            _atq.insert_next(agv_id, _cmd, dest_node=dest)
            print(f"[TRAFFIC] {agv_id}: HEAD-ON hết đường tiến — LÙI {current_idx - back_idx} "
                  f"node về {_seg[-1]} ({reason}), nhường {other_agv}, queue lại đích {dest}")
            return True
        except Exception as _e:
            print(f"[TRAFFIC] {agv_id}: _back_up_to_reroute_node lỗi: {_e}")
            return False

    @_agv_scoped
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
                _st.yield_park    = _park
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
            # PHÁT HIỆN THỰC TẾ (2026-09-24): window_start là SỔ SÁCH NỘI BỘ, có
            # thể LỆCH phía sau vị trí thật sau nhiều lần REROUTED/off_route/
            # CHỐNG-TRAP liên tiếp (full_path được thay nhưng window_start không
            # phải lúc nào cũng đồng bộ lại đúng theo current_idx mới). Trước đây
            # return CÂM ở đây — hàm này (kể cả khi được gọi lại định kỳ bởi
            # watchdog "đang chờ conflict... quá lâu") KHÔNG BAO GIỜ đánh giá lại
            # được nữa, không in gì, không hành động gì → xe đứng im vĩnh viễn dù
            # được "đánh thức" liên tục (đúng lỗi thực tế: AGV04 đứng hình tại 13
            # hàng phút, watchdog gọi lại đều đặn nhưng rơi thẳng vào return câm
            # này mỗi lần → AGV01 thắng arbiter chờ AGV04 thua dời đi mãi mãi =
            # deadlock kép không bên nào thoát được). current_idx tính từ
            # current_tag THẬT (RFID vừa quẹt) — đáng tin hơn window_start (chỉ
            # là bookkeeping) → đồng bộ lại window_start theo vị trí thật rồi
            # TIẾP TỤC đánh giá bình thường, thay vì bỏ qua.
            route.window_start = current_idx

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
                # FOLLOWING: trước khi CHỈ DỪNG CHỜ, thử xem còn đường nào khác đi
                # HẲN được không (yêu cầu người dùng: "còn đường khác thì cho đi
                # luôn, hết đường mới đứng chờ"). QUAN TRỌNG (phát hiện thực tế
                # 2026-09-17): dùng avoid_all=True (né đường CỦA MỌI xe, kể cả xe
                # yếu hơn) ở đây khiến reroute nhảy sang nhánh VÒNG RẤT XA để né cả
                # hành lang những xe sắp rời đi/không thật sự cản lâu, gây đi vòng
                # vô ích thấy rõ trong log dù "đi 1 mình 1 đường". Đây chỉ là một
                # xe cùng chiều tạm chắn phía trước (không phải vật cản buộc rời
                # đường) → dùng avoid_all=False (mặc định) giống hệt nhánh head-on
                # — chỉ né đường xe MẠNH hơn (bất đối xứng, đã có sẵn), cho ra
                # nhánh vòng hợp lý hoặc trả False (đường đơn) để rơi xuống chờ.
                # Quyết định theo THỜI GIAN: chỉ đổi đường khi vòng dôi (giây) < thời gian chờ xe chắn thoát.
                # Xe trước đang chạy & sắp rời → chờ ngắn → cứ chờ (kể cả khi nó còn cách 4-5 node);
                # xe trước ĐỖ / đứng chờ xác nhận → chờ lâu → đi vòng nếu vòng không quá xa.
                _fol_stalled = time.monotonic() - traffic_coordinator._registered.get(
                    agv_id, {}).get('last_progress_ts', time.monotonic())
                _fol_blocker = (traffic_coordinator.node_reserved_by_other(
                    agv_id, route.full_path[min(conflict_at + 1, len(route.full_path) - 1)])
                    or self._identify_conflicting_agv(
                        agv_id, route.full_path[conflict_at],
                        route.full_path[conflict_at + 1] if conflict_at + 1 < len(route.full_path) else None))
                _fol_wait = (estimate_clear_wait_sec(_fol_blocker, route.full_path[current_idx:current_idx + 8])
                             if _fol_blocker else STATIONARY_WAIT_SEC)
                if (_fol_stalled >= FOLLOW_REROUTE_MIN_STALL_SEC
                        and self._try_line_reroute(agv_id, state, route, current_idx,
                                                   require_worthwhile=True,
                                                   max_extra_sec=detour_allowance_sec(_fol_wait))):
                    print(f"[LINE_AGV] {agv_id}: following nhưng còn đường khác "
                          f"→ ĐI ĐƯỜNG KHÁC thay vì đứng chờ xe phía trước")
                    return
                # FOLLOWING: xe cùng chiều đứng trước, KHÔNG có đường nào khác (đường
                # đơn thật) → chỉ dừng lại chờ. Dừng cách xe trước ≥2 node: safe_end = conflict_at - 1
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
                _ho_wait = (estimate_clear_wait_sec(_other_agv, route.full_path[current_idx:current_idx + 8])
                            if _other_agv else STATIONARY_WAIT_SEC)
                if self._try_line_reroute(agv_id, state, route, current_idx,
                                          max_extra_sec=detour_allowance_sec(_ho_wait)):
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
                # PHÁT HIỆN THỰC TẾ (2026-09-24): _yield_to_siding gửi hẳn 1 plan MỚI
                # (deregister + on_agv_completed + dispatch_or_queue) nhưng KHÔNG hề
                # qua cổng chống-dao-động REROUTE_COOLDOWN như _try_line_reroute ở nhánh
                # (1) — nên khi _try_line_reroute VỪA reroute xong (đặt _reroute_ts) rồi
                # NGAY SAU ĐÓ phát hiện thêm 1 head-on khác trên đường mới, rơi thẳng
                # xuống đây gửi TIẾP 1 plan khác chỉ trong <1s. Firmware nhận liên tiếp
                # nhiều plan quá nhanh không kịp ACK/thực thi hết plan trước → xe âm
                # thầm chạy theo plan CŨ trong lúc server tưởng đã chuyển plan mới, dẫn
                # tới lệch route (off_route) hàng chục giây sau (đúng log thực tế: AGV04
                # bị "REROUTED" rồi "ĐI VÒNG"/đỗ-né-siding chỉ trong <1s, sau đó ~34s mới
                # phát hiện "tại 17 KHÔNG thuộc route" phải off_route re-dispatch). Áp
                # CHUNG cổng cooldown này cho siding (coi như 1 dạng đổi-đường) — nếu vừa
                # đổi đường/plan gần đây, rơi xuống WAIT-BASED (an toàn, không gửi plan
                # mới) thay vì chồng thêm 1 plan nữa ngay lập tức.
                _now_sd = time.monotonic()
                if _now_sd - self._reroute_ts.get(agv_id, 0.0) < REROUTE_COOLDOWN:
                    print(f"[LINE_AGV] {agv_id}: BỎ đỗ-né-siding (vừa đổi đường/plan < "
                          f"{REROUTE_COOLDOWN:.0f}s → chờ tại chỗ, tránh chồng plan liên "
                          f"tiếp làm firmware lệch route)")
                elif (self._blocks_corridor_of(agv_id, _other_agv)
                        and self._yield_to_siding(agv_id, route, conflict_at, _other_agv)):
                    self._reroute_ts[agv_id] = _now_sd
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

            # PHÁT HIỆN THỰC TẾ (2026-09-18): khi _other_agv được nhận diện qua nhánh
            # "đang ĐỨNG tại conf_tn/conf_fn" (vd xe khác đậu tạm ngay trên đường mình,
            # không hề có route đối đầu thật) → _oncoming trả False (đúng, không phải
            # head-on) nhưng conflict_raw vẫn DƯƠNG (nhánh head-on) → rơi thẳng xuống
            # WAIT-BASED bên dưới mà KHÔNG bao giờ thử _try_line_reroute trước, khác
            # hẳn nhánh "following" (conflict_raw âm) đã có sẵn thử reroute trước khi
            # chờ. Hệ quả: xe đứng chờ VĨNH VIỄN nếu xe kia đậu lâu (vd đang chờ xác
            # nhận HMI/nâng móc) dù còn đường khác đi được — đúng lỗi thực tế "đang chờ
            # conflict ... quá lâu → re-check định kỳ" lặp lại mãi không dứt. Áp dụng
            # đúng quy tắc user đã yêu cầu (còn đường khác thì đi, hết đường mới chờ)
            # cho CẢ trường hợp này, giống hệt nhánh following.
            #
            # PHÁT HIỆN THỰC TẾ (2026-09-23): trước khi tính hẳn 1 đường VÒNG tới
            # ĐÍCH CUỐI (_try_line_reroute), ưu tiên NHÍCH TỐI THIỂU tới node an toàn
            # gần conflict nhất (_safe_end_pre, đã tính sẵn ở trên cho nhánh oncoming)
            # NẾU node đó đã NẰM NGOÀI hành lang tương lai của xe kia (_can_wait_on_route
            # — tái dùng nguyên vẹn phép tính của nhánh head-on, không tính lại). Tránh
            # đúng lỗi log thực tế: AGV01 bị AGV04 chắn tạm ở node 28 (không đối đầu
            # thật), đi vòng hẳn qua 29→27→26 để né — nhưng đường vòng đó lại CHÍNH LÀ
            # đoạn AGV04 sẽ dùng ngay sau (28→27→26→22→...) → vòng xong vẫn đụng lại
            # đúng xe vừa né, chờ thêm 1 lần nữa, đường lại dài hơn hẳn so với chỉ nhích
            # lên gần rồi chờ ngay tại chỗ.
            if _other_agv and not _oncoming:
                # PHÁT HIỆN THỰC TẾ (mô phỏng 15 xe, 2026-10-10): nhánh "NHÍCH rồi
                # CHỜ" (_can_wait_on_route) ngay dưới đây có thể tự lặp lại VÔ HẠN —
                # nếu agv_id và _other_agv khoá chéo nhau (mỗi xe đều "không đối đầu
                # thật" với xe kia nhưng đều đang ở trên hành lang tương lai của
                # nhau), mỗi lần re-check lại rơi đúng vào đây, chỉ re-đăng-ký CHỜ,
                # KHÔNG BAO GIỜ thử _try_line_reroute/lùi — log thực tế: 1 cặp xe
                # đứng im CÙNG NHAU >10 PHÚT (idle >500s), in lại dòng "NHÍCH tới...
                # rồi CHỜ" hàng trăm lần liên tiếp. Dùng lại ĐÚNG ngưỡng/đại lượng đã
                # có (STALL_BYPASS_SEC + last_progress_ts, xem nhánh "ngã rẽ/cùng
                # chiều" trong _find_upcoming_conflict) — đứng im quá lâu → BỎ QUA
                # bước "nhích rồi chờ", thử reroute THẬT (bỏ luôn giới hạn độ dài
                # require_worthwhile — đứng cả chục phút rồi thì đường nào cũng đáng),
                # rồi mới tới lùi nếu vẫn bế tắc — KHÔNG đứng chờ mãi vô điều kiện.
                _stalled_sec_noc = (time.monotonic() - traffic_coordinator._registered
                                    .get(agv_id, {}).get('last_progress_ts', time.monotonic()))
                _stall_escaped_noc = _stalled_sec_noc > STALL_BYPASS_SEC
                if _can_wait_on_route and not _stall_escaped_noc:
                    route.waiting_before_conflict = route.full_path[_safe_end_pre]
                    if _safe_end_pre > current_idx:
                        self._send_window(agv_id, route, current_idx, _safe_end_pre, False)
                    print(f"[LINE_AGV] {agv_id}: bị {_other_agv} chắn (không đối đầu "
                          f"thật) → NHÍCH tới {route.full_path[_safe_end_pre]} (ngoài "
                          f"đường {_other_agv}) rồi CHỜ, thay vì đi vòng hẳn tới đích")
                    return
                if self._try_line_reroute(agv_id, state, route, current_idx,
                                           require_worthwhile=not _stall_escaped_noc):
                    print(f"[LINE_AGV] {agv_id}: bị {_other_agv} chắn (không đối đầu "
                          f"thật, không cùng route) nhưng còn đường khác → ĐI ĐƯỜNG "
                          f"KHÁC thay vì đứng chờ")
                    return
                if (_stall_escaped_noc
                        and self._is_deadlocked_with(agv_id, _other_agv)
                        and self._back_up_to_prev(agv_id, state, route)):
                    print(f"[LINE_AGV] {agv_id}: bị {_other_agv} khoá chéo, đứng im "
                          f"{_stalled_sec_noc:.0f}s không còn đường vòng → LÙI VỀ "
                          f"prev_tag nhả node tranh chấp")
                    return

            # ── WAIT-BASED: xe THẮNG, hoặc xe THUA chưa có chỗ né → DỪNG CHỜ tại
            # điểm an toàn CÁCH conflict HEADON_STANDOFF node (không đứng sát node
            # tranh chấp). Reservation/arbiter đã quyết ai đi trước; winner qua →
            # conflict clear → đi tiếp (A1 + _check_waiting_agvs).
            safe_end = max(current_idx, conflict_at - HEADON_STANDOFF)
            route.waiting_before_conflict = route.full_path[safe_end]
            if safe_end > current_idx:
                self._send_window(agv_id, route, current_idx, safe_end, False)
            elif route.window_end > current_idx:
                # Đã đứng ngay điểm an toàn NHƯNG cửa sổ đã gửi trước đó (vd sau REROUTED) còn
                # kéo dài qua node tranh chấp → xe vẫn chạy nốt plan cũ vào node có xe khác đứng
                # (va chạm SIM06/SIM03 tại 18, mô phỏng 2026-10-14). Gửi cửa sổ cắt ngay tại chỗ.
                self._send_window(agv_id, route, current_idx, current_idx, False, force=True)
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
        # LUÔN chuẩn bị sẵn LOOKAHEAD node phía trước: mỗi lần xe qua 1 node (tag đổi) mà phía trước còn ít hơn LOOKAHEAD node
        # trong plan đã gửi thì CẬP NHẬT plan ngay (cửa sổ trượt theo xe), thay vì đợi còn ≤ LOOKAHEAD//2 → cuối cửa sổ
        # (WAIT_SYS) không bao giờ tới trước plan kế → xe không phải dừng để chờ server.
        remaining = route.window_end - current_idx
        if remaining >= LOOKAHEAD:
            return  # Window còn đủ LOOKAHEAD node, chưa cần gửi tiếp

        new_end  = _time_capped_window_end(
            route.full_path, current_idx,
            min(current_idx + LOOKAHEAD, len(route.full_path) - 1))
        if new_end <= route.window_end and not (new_end == len(route.full_path) - 1 and not route.is_complete):
            return  # không kéo dài thêm được (tới trần thời gian/đã sát đích): không gửi lại cùng cửa sổ
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
            # Suy vị trí THẬT trong intent theo current_tag — xe kia có thể đã đi hết
            # intent này và đang đứng chờ xác nhận ở cuối đường (intent chỉ bị xoá lúc
            # deregister); dùng 0 sẽ coi các cạnh nó ĐÃ ĐI QUA XONG là còn "sắp đối đầu",
            # kích nhầm né/lùi dù xe kia không còn di chuyển trên các cạnh đó nữa.
            _oc_intent = 0
            _ost2 = self.state_store.get(other_id)
            if _ost2 and _ost2.current_tag is not None:
                try:
                    _oc_intent = _intent.index(str(_ost2.current_tag))
                except ValueError:
                    pass
            _checks.append(([str(n) for n in _intent], _oc_intent))
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

    def _break_stall_cycles(self) -> None:
        """Lớp bảo hiểm CUỐI cho bế tắc DÂY CHUYỀN nhiều xe (≥2) — gọi định kỳ
        từ watchdog (xem main.monitor_stall_cycles), KHÔNG phải mỗi tick của 1
        xe cụ thể. Các nhánh né/lùi tại-điểm trong _check_rolling_plan (nhánh
        "ngã rẽ/cùng chiều" và "không đối đầu thật") chỉ biết "ai đang chặn TÔI
        trực tiếp" — nếu bế tắc là 1 VÒNG DÀI (A chờ B, B chờ C, C chờ lại A),
        không xe nào thấy mình khoá chéo trực tiếp với ai nên không bên nào tự
        né. PHÁT HIỆN THỰC TẾ (mô phỏng 15 xe, 2026-10-10): sau khi vá ca 2-xe,
        1 vòng kẹt dây chuyền 3-4 xe vẫn đứng ~360s không tự thoát vì đúng lý
        do này. Dùng traffic_coordinator.find_stall_cycles() để tìm các vòng
        này, rồi chọn ĐÚNG 1 xe mỗi vòng (xe đứng im LÂU NHẤT — hợp lý nhất để
        được "ưu tiên" hành động trước) thử né (avoid_all=True — né TẤT CẢ xe
        khác, không chỉ xe mạnh hơn, vì đây là chu trình ĐÃ XÁC NHẬN thật, không
        phải suy đoán bất đối xứng thường) rồi lùi nếu vẫn hết đường. _try_line_
        reroute() khi thành công TỰ nhả reservation cũ + báo các xe đang chờ
        re-check ngay (xem cuối hàm đó) → phá 1 điểm trong vòng thường đủ giải
        thoát CẢ VÒNG, không cần xử lý riêng từng xe còn lại."""
        try:
            cycles = traffic_coordinator.find_stall_cycles(STALL_BYPASS_SEC)
        except Exception as e:
            print(f"[TRAFFIC] find_stall_cycles lỗi: {e}")
            return
        now = time.monotonic()
        for cyc in cycles:
            _stalled_of = lambda a: now - traffic_coordinator._registered.get(a, {}).get('last_progress_ts', now)
            # Thử lần lượt từng xe trong vòng, xe đứng im LÂU NHẤT trước. TRƯỚC ĐÂY chỉ thử đúng 1 xe:
            # nếu xe đó vừa không đổi được đường vừa không lùi được (vd SIM04 ở node 60 đối đầu SIM01
            # trong đoạn đường đơn 58-59-60, bị SIM05 chắn lối vòng) thì cả vòng kẹt vĩnh viễn dù xe
            # KIA còn nhánh trống để nhường.
            members = sorted(cyc, key=_stalled_of, reverse=True)
            _cycle_str = '→'.join(cyc + [cyc[0]])
            ctx: dict = {}
            for m in members:
                state = self.state_store.get(m)
                route = self._routes.get(m)
                if not state or not route or state.current_tag is None:
                    continue
                try:
                    ci = route.full_path.index(str(state.current_tag))
                except ValueError:
                    continue
                ctx[m] = (state, route, ci)

            # Bước 1: đổi đường rồi lùi (nhẹ nhất) — xe nào gỡ được thì dừng.
            resolved = False
            for m, (state, route, ci) in ctx.items():
                if self._try_line_reroute(m, state, route, ci,
                                           avoid_all=True, require_worthwhile=False):
                    print(f"[TRAFFIC] PHÁ CHU TRÌNH CHỜ NHAU ({_cycle_str}), {m} đứng im "
                          f"{_stalled_of(m):.0f}s → ĐI ĐƯỜNG KHÁC (né mọi xe)")
                    resolved = True
                    break
                if self._back_up_to_prev(m, state, route):
                    print(f"[TRAFFIC] PHÁ CHU TRÌNH CHỜ NHAU ({_cycle_str}), {m} đứng im "
                          f"{_stalled_of(m):.0f}s, hết đường vòng → LÙI VỀ prev_tag")
                    resolved = True
                    break
            if resolved:
                continue

            # Bước 2: không xe nào đổi đường / lùi được → cho 1 xe NHƯỜNG vào chỗ né (siding), KỂ CẢ
            # xe "thắng" arbiter — vì xe "thua" không có chỗ né thì xe thắng đứng chờ nó thoát là
            # chờ mãi (chờ nhau vô hạn). Xe nhường quay lại lệnh gốc sau khi xe kia đi qua.
            for m, (state, route, ci) in ctx.items():
                owner, conflict_at = None, None
                for j in range(ci + 1, min(ci + 1 + TRAFFIC_LOOKAHEAD, len(route.full_path))):
                    o = traffic_coordinator.node_reserved_by_other(m, route.full_path[j])
                    if o:
                        owner, conflict_at = o, j
                        break
                if owner is None:
                    continue
                if self._yield_to_siding(m, route, conflict_at, owner):
                    print(f"[TRAFFIC] PHÁ CHU TRÌNH CHỜ NHAU ({_cycle_str}), {m} đứng im "
                          f"{_stalled_of(m):.0f}s, không ai đổi đường/lùi được → {m} NHƯỜNG vào "
                          f"chỗ né cho {owner}")
                    break
        self._force_yield_long_stalls()
        self._evict_idle_blockers()

    def _evict_idle_blockers(self) -> None:
        """Xe ĐỨNG YÊN (đã deregister, không route — vd chờ thang/chờ đích) chắn đường xe khác
        quá IDLE_BLOCKER_EVICT_SEC: các lớp trên chỉ xử lý xe có route nên không gỡ được
        (log 2026-11-17: SIM01 đứng node 9 chờ thang của SIM02, SIM02 cần đi qua 9 → chờ nhau mãi).
        Ép xe chắn đi sang node trống gần nhất; chuỗi lệnh trong hàng đợi tự đưa nó quay lại sau."""
        ib = traffic_coordinator.__dict__.get('_idle_blocked')
        if not ib:
            return
        now = time.monotonic()
        cd = self.__dict__.setdefault('_idle_evict_ts', {})
        for blocker, e in list(ib.items()):
            if now - e['last'] > 300.0:
                ib.pop(blocker, None)
                continue
            if now - e['first'] < IDLE_BLOCKER_EVICT_SEC:
                continue
            if now - cd.get(blocker, 0.0) < STALL_FORCE_YIELD_COOLDOWN:
                continue
            state = self.state_store.get(blocker)
            if (not state or state.driving or state.current_tag is None
                    or self._routes.get(blocker)
                    or str(state.current_tag) != e.get('tag')):
                continue
            if not agv_registry.can_reverse(blocker):
                continue
            cd[blocker] = now
            cur = str(state.current_tag)
            try:
                park = traffic_coordinator.find_flexible_parking(
                    blocker, cur, e.get('path') or [cur],
                    extra_blocked=(state.accumulated_blocked or set()).copy(), relaxed=True)
                if not park:
                    print(f"[TRAFFIC] ÉP NHƯỜNG: {blocker} chắn {e['blocked']} tại {cur} "
                          f"{now - e['first']:.0f}s nhưng KHÔNG có node đỗ trống")
                    continue
                import networkx as _nx_eb
                from mqtt_client import map_manager as _mm_eb
                from line_agv_plan_builder import build_line_plan, build_edge_speeds, build_edge_lidar
                g = _mm_eb.line_graph if _mm_eb.line_graph else _mm_eb.graph
                transit = [str(n) for n in _nx_eb.shortest_path(g, cur, str(park), weight='weight')]
                if len(transit) < 2:
                    continue
                if state.prev_tag is not None and transit[1] == str(state.prev_tag)                         and not agv_registry.can_reverse(blocker):
                    continue
                pdir = _charger_exit_direction(transit[0], 'fwd')
                plan = build_line_plan(
                    transit, getattr(_mm_eb, "points", {}) or {}, task_type="transit",
                    node_actions=getattr(_mm_eb, "node_actions", {}) or {}, direction=pdir,
                    edge_speeds=build_edge_speeds(getattr(_mm_eb, "roads", []) or []),
                    edge_lidar=build_edge_lidar(getattr(_mm_eb, "roads", []) or []),
                    agv_id=blocker,
                    initial_prev_tag=str(state.prev_tag) if state.prev_tag else None)
                self.set_route(blocker, transit, "transit", direction=pdir)
                rt = self._routes[blocker]
                rt.window_end = len(transit) - 1
                rt.is_complete = True
                if self.send_window_fn:
                    self.send_window_fn(blocker, plan)
                else:
                    from mqtt_client import send_order as _so_eb
                    _so_eb(blocker, plan)
                print(f"[TRAFFIC] ÉP NHƯỜNG: {blocker} đứng yên chắn {e['blocked']} tại {cur} "
                      f"{now - e['first']:.0f}s → đi sang node trống {park}")
                ib.pop(blocker, None)
                break
            except Exception as ex:
                print(f"[TRAFFIC] {blocker}: ép nhường xe đứng yên lỗi: {ex}")

    def _force_yield_long_stalls(self) -> None:
        """Bước cưỡng bức cuối: xe đứng im > STALL_FORCE_YIELD_SEC (5 phút) mà các lớp
        đổi đường/lùi ở trên không gỡ được → ép đi vào node đỗ trống gần nhất
        (_reverse_to_side_node, BFS, tránh node đang bị xe khác giữ) để nhả chỗ."""
        now = time.monotonic()
        last = self.__dict__.setdefault('_force_yield_ts', {})
        # Xe lùi được nhường TRƯỚC (rơ-moóc không lùi nên khó nhường), rồi xe đứng im lâu hơn.
        _order = sorted(traffic_coordinator._registered.items(),
                        key=lambda kv: (not agv_registry.can_reverse(kv[0]),
                                        -(now - kv[1].get('last_progress_ts', now))))
        for agv_id, r in _order:
            stalled = now - r.get('last_progress_ts', now)
            if stalled <= STALL_FORCE_YIELD_SEC:
                continue
            if now - last.get(agv_id, 0.0) < STALL_FORCE_YIELD_COOLDOWN:
                continue
            state = self.state_store.get(agv_id)
            route = self._routes.get(agv_id)
            if not state or not route or state.current_tag is None:
                continue
            try:
                current_idx = route.full_path.index(str(state.current_tag))
            except ValueError:
                continue
            # CHỈ ép nhường khi xe đang bị XE KHÁC chặn đường phía trước. Xe đứng im vì lý do khác (firmware ở MANUAL/eStop,
            # chờ xác nhận, lỗi vật lý…) mà không ai chắn thì ép lùi/đỗ chẳng giải quyết gì — chỉ khiến xe chạy lung tung
            # (PHÁT HIỆN THỰC TẾ 2026-11-20: AGV02 không vướng ai vẫn bị ép đi đỗ 23 rồi quay lại 4, lùi qua lại hết đường).
            try:
                _ahead_fy = [str(n) for n in route.full_path[current_idx + 1: current_idx + 1 + LOOKAHEAD]]
                if not _ahead_fy or path_claimed_by_other(agv_id, _ahead_fy) is None:
                    continue
            except Exception:
                pass
            last[agv_id] = now
            try:
                ok = self._reverse_to_side_node(agv_id, state, route, current_idx, relaxed=True)
            except Exception as e:
                print(f"[TRAFFIC] {agv_id}: ép nhường lỗi: {e}")
                continue
            print(f"[TRAFFIC] ÉP NHƯỜNG: {agv_id} đứng im {stalled:.0f}s "
                  f"(>{STALL_FORCE_YIELD_SEC:.0f}s) tại {state.current_tag} → "
                  f"{'đi vào node đỗ gần nhất' if ok else 'KHÔNG tìm được node đỗ trống'}")
            if ok:
                break   # 1 xe nhường là đủ phá vòng; xe còn lại để lượt quét sau xét tiếp

    @_agv_scoped
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

    @_agv_scoped
    def _reverse_to_side_node(
        self, agv_id: str, state: LineAGVState,
        route: LineAGVRoute, current_idx: int,
        relaxed: bool = False,
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
            extra_blocked=_acc_blocked, relaxed=relaxed
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
            # AN TOÀN: đường tới chỗ đỗ KHÔNG được xuyên qua node đang bị xe KHÁC giữ chỗ / đứng thật.
            # PHÁT HIỆN THỰC TẾ (2026-11-19): ÉP NHƯỜNG gửi AGV02 (đứng im ở 6) đi đỗ ở 17 qua 6→30→7→17
            # trong khi AGV01 đang vào node 30 → cả hai CÙNG sắp vào 30, chỉ nhờ watchdog
            # PHYSICAL_COLLISION_RISK dừng khẩn cấp mới không va. Có chặn → bỏ phương án này (xe tiếp tục chờ).
            try:
                for _n_ck in _transit[1:]:
                    _own_ck = traffic_coordinator.node_reserved_by_other(agv_id, str(_n_ck))
                    if not _own_ck:
                        for _oid_ck, _st_ck in self.state_store._states.items():
                            if (_oid_ck != agv_id and _st_ck is not None
                                    and str(_st_ck.current_tag) == str(_n_ck)):
                                _own_ck = _oid_ck
                                break
                    if _own_ck:
                        print(f"[TRAFFIC] {agv_id}: đường tới chỗ đỗ {side_node} {_transit} xuyên qua "
                              f"node {_n_ck} đang bị {_own_ck} giữ → KHÔNG đi (chờ tiếp)")
                        return False
            except Exception:
                pass
            # Xe không lùi được (rơ-moóc/đầu kéo) không thể đi ngược về node vừa tới để vào chỗ đỗ
            if (relaxed and not agv_registry.can_reverse(agv_id) and len(_transit) > 1
                    and state.prev_tag is not None and str(_transit[1]) == str(state.prev_tag)):
                return False
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

    def _send_reverse_into_charger(
        self, agv_id: str, route: "LineAGVRoute", node_tag: str, final_node: str,
    ) -> None:
        """Gửi tiếp đoạn LÙI CÒN LẠI vào trạm sạc sau khi firmware báo arrived_wait_sys
        TẠI NODE TRUNG GIAN (đã rẽ + dừng hẳn theo PROTOCOL_GUIDE.md "Đổi chiều lùi",
        xem nhánh return_charge ở _handle_event). KHÔNG dùng build_plan_window() ở đây
        — nó sẽ tính lại TỪ ĐẦU node_tag (rẽ lại lần nữa dù xe đã rẽ xong, xoay lố
        thêm 90°) — chỉ cần phần CÒN LẠI: đổi chiều lùi rồi chạy thẳng vào đích."""
        import uuid as _uuid_rc
        plan = {
            "c": "plan",
            "id": str(_uuid_rc.uuid4())[:8],
            "d": [
                {"t": int(node_tag),   "a": ACTION_DIR_BWD,     "v": 0},
                {"t": int(node_tag),   "a": ACTION_RUN,         "v": 0},
                {"t": int(final_node), "a": ACTION_WAIT_CHARGE, "v": 0},
            ],
        }
        route.sent_cmd_id = plan["id"]
        route.sent_at      = time.time()
        route.acked        = False
        if self.send_window_fn is not None:
            self.send_window_fn(agv_id, plan)
        else:
            from mqtt_client import send_order as _so_rc
            _so_rc(agv_id, plan)
        print(f"[LINE_AGV] {agv_id}: gửi tiếp lùi vào trạm sạc | id={plan['id']} "
              f"| {node_tag}→{final_node}")

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
            _res_end = traffic_coordinator.reserved_extent_lenient(
                agv_id, route.full_path, w_start, w_end)
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
        # ── AN TOÀN VẬT LÝ (lưới chặn cuối, KHÔNG phụ thuộc sổ sách đăng ký):
        # PHÁT HIỆN THỰC TẾ (2026-10-03, va chạm thật tại node 24): AGV03 được
        # dispatch đi 28→24→103 đúng lúc node 24 còn "trống" theo reservation —
        # nhưng 0.4s sau, AGV04 cập thẻ TỚI ĐÚNG node 24 (off_route, đang xử lý
        # deregister/redispatch) → có 1 khoảng ngắn node 24 bị CHIẾM VẬT LÝ THẬT
        # nhưng CHƯA kịp phản ánh vào reservation (xe kia đang deregistered giữa
        # lúc xử lý off_route). Lúc xe rẽ vào node, LIDAR luôn bị tắt ngay trước
        # rẽ (xem build_plan_window — tắt/mở quanh mỗi TURN, tránh báo giả lúc
        # xe/rơ-moóc tự quét qua khúc cong) → nếu node đích đang có xe khác đứng
        # vật lý mà reservation chưa biết, KHÔNG CÒN LỚP NÀO bảo vệ cả. Vá: ngay
        # trước khi gửi 1 window CÓ bước di chuyển thật (w_end>w_start), so khớp
        # TRỰC TIẾP current_tag của MỌI xe khác (không qua sổ sách đăng ký) với
        # node ngay sau vị trí hiện tại — nếu trùng, GIỮ TẠI CHỖ (w_end=w_start)
        # bất kể reservation nói gì. Chỉ thêm 1 lớp chặn, không thay đổi cách
        # tính route/reservation hiện có.
        # Tự clear MỖI lần gọi trước khi đánh giá lại — cảnh báo này tự sửa
        # đúng/sai theo từng cửa sổ gửi, không cần chờ xe di chuyển mới hết.
        # ── TRẠM SẠC LÀ ĐIỂM CUỐI BẢN ĐỒ: tuyệt đối không gửi cửa sổ đi QUÁ trạm sạc (xe sẽ chạy ra
        # ngoài bản đồ). Gặp trạm sạc nằm GIỮA cửa sổ (không phải node cuối của cửa sổ, và không
        # phải node xe đang đứng) → cắt cửa sổ dừng đúng tại trạm sạc.
        try:
            from mqtt_client import map_manager as _mm_ch
            _chs = _mm_ch.charger_nodes()
            for _k in range(w_start + 1, min(w_end, len(route.full_path) - 1)):
                if str(route.full_path[_k]) in _chs:
                    print(f"[SAFETY] {agv_id}: route đi QUÁ trạm sạc {route.full_path[_k]} "
                          f"(ngoài bản đồ) → cắt cửa sổ dừng tại trạm sạc")
                    w_end    = _k
                    is_final = False
                    break
        except Exception:
            pass
        self._clear_alert(self.state_store.get(agv_id), "PHYSICAL_BLOCK")
        if w_end > w_start:
            _nxt_phys = route.full_path[w_start + 1]
            for _oid_phys, _st_phys in self.state_store._states.items():
                if _oid_phys == agv_id or _st_phys is None:
                    continue
                if (_st_phys.current_tag is not None
                        and str(_st_phys.current_tag) == _nxt_phys):
                    _msg_phys = (f"AN TOÀN — node {_nxt_phys} đang bị {_oid_phys} "
                                 f"CHIẾM VẬT LÝ (current_tag, không qua đăng ký) → GIỮ "
                                 f"TẠI CHỖ, không gửi bước rẽ/tiến vào đó")
                    print(f"[LINE_AGV] {agv_id}: {_msg_phys}")
                    self._set_alert(agv_id, None, "PHYSICAL_BLOCK", _msg_phys)
                    w_end    = w_start
                    is_final = False
                    break
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
        # PHÁT HIỆN THỰC TẾ (2026-09-23): dedup này giả định "window giống lần
        # trước" luôn có nghĩa "xe đang chạy dở window cũ, khỏi gửi lại" — SAI khi
        # xe hiện KHÔNG đang chạy (driving=False) và đang đứng ĐÚNG tại node
        # w_start (vừa báo arrived_wait_sys ngay tại đây, đang CHỜ LỆNH TIẾP để
        # vượt qua checkpoint WAIT_SYS). Firmware ở WAIT_SYS KHÔNG tự resume và
        # KHÔNG tự báo plan_wait_timeout (đó là trạng thái CHỜ CHỦ ĐỘNG, không
        # phải lỗi) — nếu recompute (vd CHỐNG-TRAP rolling) ra đúng window đã gửi
        # trước đó, dedup im lặng bỏ qua → xe đứng im VÔ THỜI HẠN tại checkpoint.
        # Log thực tế: AGV04 kẹt >100s tại node 98 (window [0→1] lặp lại y hệt mỗi
        # lần re-check), chỉ thoát được nhờ người vận hành gửi tay lệnh "deba".
        # Dedup chỉ nên chặn khi xe ĐANG CHẠY giữa window cũ (driving=True) —
        # không chặn khi xe đang đứng yên chờ đúng tại đầu window.
        # PHÁT HIỆN THỰC TẾ (2026-09-24): fix trên (2026-09-23) thiếu điều kiện
        # `w_end > w_start` → khi window sau mọi cắt vẫn là ĐỘ DÀI 0 (không có
        # bước di chuyển nào, chỉ 1 action WAIT_SYS tại chính node hiện tại — vd
        # bị reservation cắt về [3→3]), force-resend liên tục KHÔNG giúp gì (gửi
        # lại y hệt 1 lệnh "đứng yên" thì xe vẫn đứng yên) mà còn khiến xe echo lại
        # arrived_wait_sys ngay lập tức mỗi lần nhận → server lại resend → LẶP VÔ
        # HẠN mỗi ~1-2 giây (đúng log thực tế: AGV03 kẹt ở node 16 hơn 2 phút, log
        # "sent window (fallback) [3→3]" lặp hàng chục lần liên tục, không bao giờ
        # tiến). Chỉ force-resend khi window THẬT SỰ có bước di chuyển (w_end >
        # w_start) — đúng ca gốc cần sửa (AGV kẹt tại WAIT_SYS giữa 1 window nhiều
        # bước, vd 98→6).
        _st_dedup = self.state_store.get(agv_id)
        _stuck_at_start = (
            w_end > w_start
            and _st_dedup is not None and not _st_dedup.driving
            and _st_dedup.current_tag is not None
            and w_start < len(route.full_path)
            and str(_st_dedup.current_tag) == route.full_path[w_start]
        )
        if (not force and not _stuck_at_start and route.sent_cmd_id and route.window_start == w_start
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
        # QUAN TRỌNG (phát hiện thực tế 2026-09-17): nếu xe đã VẬT LÝ tiến XA HƠN
        # node đầu cửa sổ (vd đã rẽ xong tại node giữa route) mà chỉ THIẾU gói ACK
        # (rớt gói/race, không phải chưa nhận plan) — gửi lại build_plan_window với
        # window_start CŨ (lùi về đầu) sẽ tạo 1 plan MỚI đè lên plan xe đang thực
        # thi dở, xoá mất các bước rẽ đã lên kế hoạch giữa chừng → xe đi THẲNG qua
        # ngã rẽ thay vì rẽ đúng (đúng lỗi thực tế: kế hoạch rẽ nhưng xe đi thẳng).
        # Tiến bộ vật lý rõ ràng (tag đã ở 1 node XA HƠN window_start trên
        # full_path) là bằng chứng đủ tin cậy plan ĐÃ được nhận và đang thực thi —
        # coi như đã ACK (reset timer), KHÔNG gửi đè.
        if route.full_path:
            try:
                _cur_idx_rt = route.full_path.index(tag_str)
            except ValueError:
                _cur_idx_rt = -1
            if _cur_idx_rt > route.window_start:
                print(f"[LINE_AGV] {agv_id}: bỏ retry plan id={route.sent_cmd_id} — xe đã "
                      f"tiến tới {tag_str} (xa hơn đầu cửa sổ "
                      f"{route.full_path[route.window_start]}) → coi như đã nhận plan "
                      f"(chỉ rớt gói ACK), KHÔNG gửi đè")
                route.acked = True
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

    def _handle_elevator_leg_arrival(self, agv_id: str, state) -> bool:
        """True nếu lệnh go_to đang chạy là 1 chặng TRUNG GIAN của chuỗi đi thang (lệnh kế tiếp trong hàng đợi là elev_*) và
        xe đã tới đúng đích chặng đó: hoàn tất chặng, hàng đợi tự chạy bước thang kế (đặt/gọi/vào/nhả) — không chờ xác nhận."""
        try:
            from task_queue import agv_task_queue as _atq_el
            run = _atq_el.get_running(agv_id)
            if run and str(run.get("command") or "").startswith("elev_"):
                # Đang trong bước thang (đặt/gọi/đi thang/nhả): các tin WAIT_SYS tại thẻ cabin/thẻ thoát do cầu thang
                # (elevator_bridge) quản lý theo tín hiệu cửa — KHÔNG vào "picking" chờ xác nhận.
                return True
            # go_charge/go_wait cũng có thể chứa chặng ĐẦU của chuỗi đi thang (trạm ở tầng khác → decompose() chạy
            # "go_to node chờ" ngay trong lệnh gốc). PHÁT HIỆN THỰC TẾ (2026-11-21): AGV01 về sạc từ node 15 tới điểm
            # xếp hàng 10 bị coi là "picking" chờ xác nhận, không đặt thang. Các lệnh này không có dest_node tại
            # node chờ nên chỉ khớp qua đích route (_leg_dest_el) + lệnh kế tiếp là elev_* (kiểm tra bên dưới).
            if not run or run.get("command") not in ("go_to", "go_charge", "go_wait"):
                return False
            _tag_el = str(state.current_tag)
            # Chặng đầu của chuỗi đi thang có thể chạy NGAY TRONG lệnh go_to gốc (đích cuối, vd 14) — khi đó
            # run.dest_node KHÁC node chờ (6) dù xe đã tới đúng đích CỦA CHẶNG (full_path[-1]). So với route.
            # PHÁT HIỆN THỰC TẾ (2026-11-19): AGV02 tới node 6 bị coi là "picking" chờ xác nhận, không đặt thang.
            _rt_el = self._routes.get(agv_id)
            _leg_dest_el = str(_rt_el.full_path[-1]) if (_rt_el and _rt_el.full_path) else None
            _run_dest_el = str(run.get("dest_node") or "")
            if _run_dest_el != _tag_el and _leg_dest_el != _tag_el:
                return False
            # Đích THẬT của lượt (vd giao hàng tại 15) thì KHÔNG phải chặng đi thang dù lệnh kế tiếp là elev_*
            # (chuỗi chiều VỀ được nối ngay sau) — xe phải dừng chờ xác nhận. Chặng trung gian = go_to đã đánh dấu
            # chain_leg, hoặc chặng ĐẦU chạy trong lệnh gốc (route kết thúc ở node chờ khác đích lệnh).
            if _run_dest_el == _tag_el and not run.get("chain_leg"):
                # Lệnh go_to bị TÁCH giữa đường (split tại node lấy hàng…) sinh ra go_to mới KHÔNG mang cờ chain_leg
                # → nhận ra chặng thang qua chính node: node thuộc vùng thang (cabin/điểm xếp hàng/mốc thoát/node chờ).
                # PHÁT HIỆN THỰC TẾ (2026-11-20): AGV tới node 6/28 bị hỏi xác nhận vì go_to 28 sinh ra sau split.
                try:
                    from mqtt_client import map_manager as _mm_el
                    _zone_el = set(getattr(_mm_el, 'elev_zone', ()) or ()) | {
                        str(v) for v in (getattr(_mm_el, 'elev_wait', {}) or {}).values()}
                except Exception:
                    _zone_el = set()
                if _tag_el not in _zone_el:
                    return False
            q = _atq_el.get_queue(agv_id)
            if not q or not str(q[0].get("command") or "").startswith("elev_"):
                return False
            # Ghi lại CHIỀU chạy của chặng vừa xong (như mọi nhánh hoàn tất route khác) — mũi xe giữ nguyên khi đứng chờ thang,
            # nên chặng kế tiếp phải biết xe vừa LÙI hay TIẾN tới đây. Thiếu bước này last_tdir='' → dispatch mặc định 'fwd' và
            # xe vừa lùi tới node chờ bị gửi lệnh tiến NGƯỢC chiều (PHÁT HIỆN THỰC TẾ 2026-11-20: AGV02 32→33 thay vì 32→31).
            try:
                if _rt_el is not None and getattr(_rt_el, 'direction', None) in ('fwd', 'bwd'):
                    state.last_transit_direction = _rt_el.direction
            except Exception:
                pass
            self._routes.pop(agv_id, None)
            traffic_coordinator.deregister(agv_id)
            print(f"[LINE_AGV] {agv_id}: tới node {state.current_tag} (chặng đi thang) — tự động đi tiếp: {q[0].get('command')}")
            _atq_el.on_agv_completed(agv_id, notes="elev_leg")
            return True
        except Exception as e:
            print(f"[LINE_AGV] {agv_id}: kiểm tra chặng thang lỗi: {type(e).__name__}: {e}")
            return False

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

    def _is_tow_agv(self, agv_id: str) -> bool:
        """True nếu AGV này là 'AGV kéo' (agv_devices.agv_type='tow') — quy trình
        móc NGƯỢC với xe rơ-moóc/đầu kéo mặc định ('trailer'):
          - Rơ-moóc: tới node LẤY hàng → gửi NÂNG (30), chờ hạ thủ công (31) mới
            xong lấy hàng; tới node THẢ hàng → gửi NÂNG (30), tự xong khi nâng.
          - AGV kéo: tới node LẤY hàng → gửi HẠ (31), chờ nâng thủ công (30) mới
            xong lấy hàng; tới node THẢ hàng → gửi HẠ (31), tự xong khi hạ.
        Ngoài ra AGV kéo đi được cả 2 chiều (can_reverse=True, cấu hình riêng ở
        agv_devices.can_reverse — không liên quan hàm này), khác rơ-moóc chỉ tiến."""
        try:
            return agv_registry.get_config(agv_id).get('agv_type') == 'tow'
        except Exception:
            return False

    def _carry_skip_hook(self, agv_id: str, tag: str) -> bool:
        """True nếu xe kéo/rơ-moóc đang ở chế độ carry (agv_registry.op_mode) và
        node `tag` KHÔNG cần thao tác móc → xử lý như xe chở: dừng, chờ người xác
        nhận thủ công rồi mới đi tiếp.
          - carry_fixed: thùng gắn cố định → KHÔNG BAO GIỜ móc.
          - carry_hook : chỉ móc ở node LẤY hàng (trailer_role=pickup /
            trailer_empty_staging / supply_group); node đích giao hàng chờ xác nhận,
            không thả xe hàng. Node 'trailer_staging' (điểm thả cố định, dùng cho
            return_mode=drop_cart) vẫn tự thả như cũ.
          - roundtrip  : luôn False (hành vi cũ)."""
        try:
            mode = agv_registry.op_mode(agv_id)
            if mode == "roundtrip":
                return False
            from mqtt_client import map_manager as _mm_cs
            act = (getattr(_mm_cs, 'node_actions', {}) or {}).get(str(tag)) or {}
            if str(act.get('trailer_staging') or '').strip().lower() == 'yes':
                return False
            if mode == "carry_fixed":
                return True
            if self._is_tow_pickup_target(agv_id, str(tag)) or act.get('supply_group'):
                return False
            return True
        except Exception:
            return False

    def _is_tow_pickup_target(self, agv_id: str, tag: str) -> bool:
        """True nếu `tag` là 1 điểm LẤY HÀNG của AGV kéo (tow) — dùng CHUNG logic
        ưu tiên với _handle_trailer_hook_arrival (ưu tiên 0: đang trong chặng lấy
        rỗng gần trạm đã đánh dấu lúc dispatch; ưu tiên 2: trailer_role='pickup';
        ưu tiên 3: trailer_empty_staging='yes'). KHÔNG tiêu thụ (discard) dấu
        _pending_empty_pickup_legs ở đây — chỉ dùng để KIỂM TRA, việc dùng-1-lần-
        rồi-xoá vẫn do _handle_trailer_hook_arrival đảm nhiệm khi xe THẬT SỰ tới."""
        if (agv_id, tag) in _pending_empty_pickup_legs:
            return True
        try:
            from mqtt_client import map_manager as _mm_pk2
            act = (getattr(_mm_pk2, 'node_actions', {}) or {}).get(tag) or {}
        except Exception:
            act = {}
        role = str(act.get('trailer_role') or '').strip().lower()
        if role == 'pickup':
            return True
        if str(act.get('trailer_empty_staging') or '').strip().lower() == 'yes':
            return True
        return False

    def _maybe_preraise_tow_hook(self, agv_id: str, new_tag: str, state: "LineAGVState") -> None:
        """AGV kéo (tow): tới điểm lấy hàng cần NÂNG móc TRƯỚC 1 node — nâng
        ngay khi xe tới node LIỀN TRƯỚC đích lấy hàng trong route hiện tại (không
        chờ tới hẳn nơi mới nâng), để móc kịp nâng xong TRƯỚC khi xe áp sát xe
        hàng cần lấy. Gọi mỗi lần tag đổi (xem _handle_state) — tự thoát ngay nếu
        không khớp điều kiện, không ảnh hưởng các loại xe/chặng khác."""
        if not self._is_tow_agv(agv_id):
            return
        if agv_registry.op_mode(agv_id) == "carry_fixed":
            return   # thùng cố định — không có móc để nâng trước
        route = self._routes.get(agv_id)
        if not route or not route.full_path or len(route.full_path) < 2:
            return
        if str(route.full_path[-2]) != new_tag:
            return   # không phải node liền trước đích — bỏ qua
        final_tag = str(route.full_path[-1])
        if not self._is_tow_pickup_target(agv_id, final_tag):
            return
        # Nếu marker còn set nhưng hook_state CHƯA "raised" (vd sau khi bị huỷ
        # lệnh/re-dispatch giữa chừng, marker cũ còn sót) — vẫn gửi lại cho chắc,
        # an toàn hơn bỏ qua rồi lỡ mất bước nâng thật.
        if state.hook_prearmed_for == final_tag and state.hook_state == "raised":
            return   # đã nâng trước cho đúng đích này VÀ đã xác nhận xong — tránh gửi lặp
        print(f"[LINE_AGV] {agv_id}: sắp tới điểm lấy hàng {final_tag} — "
              f"tự động NÂNG móc TRƯỚC 1 node (tại {new_tag})")
        state.hook_prearmed_for      = final_tag
        state.hook_pending           = "pickup"
        state.hook_raise_retries     = 0
        state.hook_fallback_notified = False
        self._send_hook_action_delayed(agv_id, ACTION_HOOK_RAISE, delay=0.0)

    def _send_hook_action_delayed(self, agv_id: str, action_code: int, delay: float = 0.3) -> None:
        """Gửi lệnh móc (NÂNG=ACTION_HOOK_RAISE hoặc HẠ=ACTION_HOOK_LOWER) sau 1
        khoảng trễ ngắn, KHÔNG block thread MQTT (dùng threading.Timer). Gửi ngay
        sát lúc arrived_wait_sys/arrived_wait_user vừa ACK xong (2 message liên
        tiếp gần như tức thời) khiến firmware không kịp xử lý — publish rc=0
        (broker nhận) nhưng móc không di chuyển thực tế. Trễ nhẹ để firmware xử
        lý xong ACK/arrival trước khi nhận action tiếp theo."""
        _verb = "HẠ" if action_code == ACTION_HOOK_LOWER else "NÂNG"
        def _fire():
            try:
                from mqtt_client import send_line_command
                send_line_command(agv_id, "action", a=action_code, v=0)
                print(f"[LINE_AGV] {agv_id}: (trễ {delay}s) đã gửi {_verb} móc")
                _st_hk = self.state_store.get(agv_id)
                if _st_hk:
                    _st_hk.hook_raise_sent_at = time.monotonic()
                    _st_hk.hook_pending_action = action_code
            except Exception as e:
                print(f"[LINE_AGV] {agv_id}: gửi {_verb} móc (trễ) lỗi: {e}")
        threading.Timer(delay, _fire).start()

    def confirm_hook_manual(self, agv_id: str) -> dict:
        """Xử lý nút xác nhận móc THỦ CÔNG trên Web UI (trước đây gọi thẳng
        /api/execute/line-action với action_code=31 'Hạ móc' cứng cho MỌI AGV) —
        giờ chọn ĐÚNG lệnh theo loại xe: rơ-moóc ('trailer') → HẠ (31) để khoá
        vào chốt xe hàng; AGV kéo ('tow') → NÂNG (30) để khoá (quy trình ngược).
        Dùng CHUNG _send_hook_action_delayed (thay vì gọi send_line_command trực
        tiếp) để hook_pending_action/hook_raise_sent_at được cập nhật đồng bộ —
        nếu không, watchdog cứu-kẹt (dòng ~1750) và phát hiện lỗi up_fail/dn_fail
        (kênh A, dòng ~1690) vẫn tưởng đang chờ lệnh TỚI NODE trước đó, không
        theo dõi đúng bước thủ công này."""
        state = self.state_store.get(agv_id)
        if not state or state.hook_pending != "pickup":
            return {"ok": False, "error": "AGV không ở trạng thái chờ xác nhận móc"}
        # PHÁT HIỆN THỰC TẾ (2026-09-21): xoá hook_prearmed_for TRƯỚC khi gửi lệnh
        # xác nhận thủ công — nếu field này còn sót giá trị CŨ (vd từ 1 lần nâng-
        # trước cho 1 đích KHÁC mà xe rốt cuộc không tới đúng đích đó do bị reroute/
        # off-route/huỷ lệnh giữa chừng, nên không bao giờ được dọn ở nhánh thành
        # công thông thường trong _handle_trailer_hook_arrival), event 'hook_raised'
        # trả về sau lệnh XÁC NHẬN THẬT này sẽ bị nhánh "móc đã nâng TRƯỚC (đích
        # ...) — xe tiếp tục chạy tới nơi" ở trên NUỐT MẤT (chỉ log rồi return, không
        # set task_lifecycle='picking') — AGV đứng im vĩnh viễn, không báo lỗi, dù
        # người dùng đã bấm xác nhận (đúng lỗi thực tế: gọi 3 xe cùng lúc, xe thứ 3
        # dừng hẳn không đi tiếp sau khi xác nhận móc). Xác nhận THỦ CÔNG luôn là
        # hoàn tất THẬT — không bao giờ là bước "nâng trước" — nên phải đi đúng
        # nhánh hoàn tất, không được để marker cũ chặn nhầm.
        state.hook_prearmed_for = None
        is_tow = self._is_tow_agv(agv_id)
        action_code = ACTION_HOOK_RAISE if is_tow else ACTION_HOOK_LOWER
        self._send_hook_action_delayed(agv_id, action_code, delay=0.0)
        return {"ok": True, "action_code": action_code, "is_tow": is_tow}

    def _complete_hook_leg(self, agv_id: str, notes: str) -> None:
        """Hoàn tất chặng hiện tại NGAY (tự động, không chờ xác nhận web) sau khi
        nâng móc xong (thả hàng) — pop route + deregister + để task_queue tự
        dispatch chặng kế tiếp đã được xếp sẵn (insert_next)."""
        self._routes.pop(agv_id, None)
        traffic_coordinator.deregister(agv_id)
        state_hk = self.state_store.get(agv_id)
        # PHÁT HIỆN THỰC TẾ (2026-10-01): hàm này TRƯỚC ĐÂY không reset
        # task_lifecycle (cùng họ lỗi bất đối xứng đã sửa ở last_transit_direction
        # nhiều lần trong code này) — giá trị CŨ (vd 'delivering'/'picking' từ 1
        # chặng móc TRƯỚC đó, set bởi _handle_trailer_hook_arrival) bị bỏ sót lại
        # dù chặng đó đã hoàn tất THẬT qua đường tự động (tow). Hệ quả nghiêm
        # trọng: watchdog "kẹt-không-rõ-lý-do" (boundary-stuck self-generate, xem
        # _check_rolling_plan/TỰ SINH arrived_wait_*) có điều kiện gate bắt buộc
        # `not state.task_lifecycle` — còn sót giá trị cũ khiến TOÀN BỘ watchdog
        # đó bị tắt câm lặng cho chặng kế tiếp, dù xe đã tới đích và event tới-nơi
        # không bao giờ được xử lý (im lặng hoàn toàn, không log, không cảnh báo,
        # đúng ca thực tế: AGV01 tới 98 lần 2 rồi đứng im ~11 phút không ai phát
        # hiện, phải force-stop thủ công). Reset tường minh để chặng MỚI không kế
        # thừa lifecycle của chặng CŨ đã xong.
        if state_hk:
            state_hk.task_lifecycle = None
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
        # PHÁT HIỆN THỰC TẾ (2026-09-18): firmware đôi khi PHÁT LẠI đúng event
        # arrived_wait_user/arrived_wait_sys CŨ (không phải TỰ SINH từ server)
        # ngay sau khi chặng móc hàng đã HOÀN TẤT XONG (hook_lowered/raised đã
        # nhận, _complete_hook_leg đã pop route + dispatch lệnh KẾ TIẾP trong
        # queue) — quan sát thực tế: gửi lệnh 'run' phục hồi AUTOMATIC trước
        # 'deba' (Về trạm) khiến firmware báo lại y hệt event WAIT_USER cũ của
        # node vừa xong. Nếu không chặn, hàm này chạy LẠI TỪ ĐẦU: set
        # hook_pending='dropoff'/'pickup' và gửi lại lệnh móc — trong khi AGV
        # đã chuyển sang việc HOÀN TOÀN KHÁC (vd đang "deba" dò vị trí Về trạm,
        # không đi qua traffic engine) → móc bị điều khiển lại giữa chừng,
        # khiến AGV đứng im tại node cũ mãi dù "không có vật cản" thật (đúng
        # log: AGV03 tại 98, 'deba toi' gửi xong lại nhận thêm 1 arrived_wait_user
        # + gửi lại HẠ móc, sau đó deba không bao giờ thấy tag đổi). Phát hiện
        # bằng cách so lệnh đang chạy thật trong task_queue: nếu lệnh running
        # hiện tại KHÔNG PHẢI 'go_to' tới ĐÚNG node này nữa (đã chuyển sang lệnh
        # khác, vd go_charge) → đây chắc chắn là echo cũ, bỏ qua hoàn toàn
        # (không set hook_pending, không gửi lại lệnh móc).
        try:
            from task_queue import agv_task_queue as _atq_stale, CMD_GO_TO as _CGT_stale
            _run_stale = _atq_stale._running.get(agv_id)
            # PHÁT HIỆN THỰC TẾ (2026-09-25, AGV04 kẹt vĩnh viễn tại 99 vô hình
            # chung khoá luôn AGV03): so `state.current_tag` với `dest_node` của
            # LỆNH QUEUE (đích CUỐI CÙNG của cả lệnh go_to) sai khi route bị TÁCH
            # ĐOẠN giữa chừng (staging vì đích thật đang bị chiếm, hoặc chèn 1
            # chặng "lấy hàng rỗng gần trạm" trước khi đi tiếp — xem
            # route split/'_pending_empty_pickup_legs' ở dispatch): lệnh queue vẫn
            # ghi dest_node=đích CUỐI (vd 98), nhưng route NỘI BỘ đang chạy lại
            # kết thúc ở node lấy hàng TRUNG GIAN thật (vd 99) — 2 giá trị này
            # KHÁC NHAU một cách HOÀN TOÀN HỢP LỆ, không phải echo cũ. Trước đây
            # chỉ so theo dest_node của lệnh queue → mọi lần tới đúng node lấy
            # hàng trung gian đều bị coi nhầm là "echo cũ" và ÂM THẦM BỎ QUA
            # (không vào lifecycle picking, không chờ xác nhận, không báo ai) —
            # xe đứng yên vĩnh viễn giữ nguyên reservation, kéo theo xe khác cần
            # node đó cũng kẹt theo. Thêm lối thoát: nếu route NỘI BỘ đang chạy
            # (chưa bị pop) có full_path kết thúc ĐÚNG tại current_tag, đây chắc
            # chắn là arrival THẬT của CHÍNH chặng đang chạy — không phải echo.
            _route_leg_ok = bool(route and route.full_path
                                  and str(route.full_path[-1]) == str(state.current_tag))
            if (not _route_leg_ok
                    and (not _run_stale or _run_stale.command != _CGT_stale
                         or str(_run_stale.dest_node) != str(state.current_tag))):
                print(f"[LINE_AGV] {agv_id}: bỏ qua arrival móc CŨ/LẶP LẠI tại "
                      f"{state.current_tag} (lệnh đang chạy thật đã khác — "
                      f"chặng móc này đã hoàn tất trước đó)")
                return
        except Exception:
            pass
        # PHÁT HIỆN THỰC TẾ (2026-09-18): TRƯỚC ĐÂY chỉ gán 'bwd', KHÔNG có nhánh
        # else gán 'fwd' — cùng lỗi bất đối xứng đã sửa ở các điểm khác (dispatch
        # rời trạm, hoàn tất transit) nhưng bị SÓT tại điểm hook lấy/thả này. Hệ
        # quả: xe tiến vào (route.direction='fwd') để thả hàng tại 1 node bình
        # thường (vd node 98) — last_transit_direction KHÔNG được cập nhật, vẫn
        # giữ giá trị CŨ từ 1 chặng trước đó (có thể là 'bwd' từ rất lâu) →
        # resolve_departure_direction() đọc nhầm 'bwd' → ra lệnh "Về trạm" tiếp
        # theo chạy TIẾN (đúng ra phải LÙI vì vừa tiến vào) → deba dò-vị-trí chạy
        # sai hướng, không bao giờ quẹt được thẻ mới, đứng im vĩnh viễn tại node
        # thả hàng (đúng log: tag mãi không đổi khỏi 98 dù gửi lại deba nhiều lần).
        if route:
            state.last_transit_direction = route.direction
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
        _is_tow = self._is_tow_agv(agv_id)

        # ── AGV kéo (tow) đã được NÂNG MÓC TRƯỚC 1 node cho ĐÚNG điểm lấy hàng
        # này (xem _maybe_preraise_tow_hook, kích khi xe vừa rời node liền
        # trước) — bỏ qua hẳn bước nâng/hạ lại ở đây, đi thẳng vào chờ xác nhận
        # thủ công DUY NHẤT "đã lấy hàng xong, đi tiếp" (đúng yêu cầu: chỉ còn
        # 1 thao tác thủ công tại điểm lấy hàng, không còn bấm Nâng móc riêng).
        # Bắt buộc hook_state=='raised' (đã CÓ xác nhận thật từ xe, không chỉ dựa
        # marker) — marker có thể còn sót lại từ 1 lượt bị huỷ/re-dispatch giữa
        # chừng mà móc chưa thật sự nâng xong; lúc đó rơi xuống luồng cũ bên dưới
        # (gửi lại HẠ/chờ như bình thường) an toàn hơn là tin nhầm đã xong.
        if (_is_tow and _is_pickup_node and state.hook_state == "raised"
                and state.hook_prearmed_for == str(state.current_tag)):
            state.hook_prearmed_for = None
            state.hook_pending      = None
            state.task_lifecycle    = "picking"
            print(f"[LINE_AGV] {agv_id}: tới điểm lấy hàng {state.current_tag} "
                  f"— móc đã nâng sẵn từ trước, chờ xác nhận trên web để đi tiếp")
            if self.on_state_changed:
                try:
                    self.on_state_changed(state)
                except Exception as e:
                    print(f"[LINE_AGV] on_state_changed error: {e}")
            try:
                from task_queue import agv_task_queue as _atq_hkpk2
                _run_hkpk2 = _atq_hkpk2._running.get(agv_id)
                if _run_hkpk2 and getattr(_run_hkpk2, 'session_id', None):
                    _atq_hkpk2.mark_session_pickup(_run_hkpk2.session_id, state.current_tag)
            except Exception as _e_hkpk2:
                print(f"[LINE_AGV] {agv_id}: mark pickup (hook, pre-armed) error: {_e_hkpk2}")
            return

        state.hook_pending = "pickup" if _is_pickup_node else "dropoff"
        # LUÔN gửi lệnh móc khi tới node cần xử lý — KHÔNG tin vào hook_state đã
        # ghi nhận trước đó: đường xóc/cảm biến lệch trong lúc di chuyển có thể
        # khiến móc thực tế không còn đúng vị trí dù state cũ báo đã xong. Chỉ
        # coi là xong khi nhận được event THẬT từ xe (xử lý ở nhánh event_name ==
        # "hook_raised"/"hook_lowered" phía dưới) — không tự suy luận rồi bỏ qua
        # hành động như trước (đã gây lỗi xe không nhả hàng thật ở node thả dù
        # trạng thái nội bộ báo "đã xong sẵn").
        #
        # Rơ-moóc ('trailer', mặc định): LUÔN gửi NÂNG (30) khi tới node — dùng
        # chung cho cả lấy (canh vị trí, chờ hạ thủ công) lẫn thả (nâng = nhả).
        # AGV kéo ('tow'): quy trình NGƯỢC — LUÔN gửi HẠ (31) khi tới node.
        _arrival_action = ACTION_HOOK_LOWER if _is_tow else ACTION_HOOK_RAISE
        _arrival_verb   = "HẠ" if _is_tow else "NÂNG"
        state.hook_raise_retries = 0   # đợt móc MỚI — reset đếm gửi-lại
        state.hook_fallback_notified = False   # đợt MỚI — cho phép kênh "hook" báo lỗi lại nếu cần
        self._clear_alert(state, "HOOK_RETRY_EXHAUSTED")
        self._clear_alert(state, "HOOK_ERROR")
        self._send_hook_action_delayed(agv_id, _arrival_action)
        if _is_pickup_node:
            print(f"[LINE_AGV] {agv_id}: tới điểm lấy hàng {state.current_tag} "
                  f"— gửi {_arrival_verb} móc, chờ xe hàng")
        else:
            print(f"[LINE_AGV] {agv_id}: tới điểm thả hàng {state.current_tag} "
                  f"— gửi {_arrival_verb} móc để nhả xe hàng, chờ xác nhận từ xe")
        if _is_pickup_node:
            # Đánh dấu pickup giống nhánh carry (tránh lấy hàng 2 lần khi re-dispatch)
            try:
                from task_queue import agv_task_queue as _atq_hkpk
                _run_hkpk = _atq_hkpk._running.get(agv_id)
                if _run_hkpk and getattr(_run_hkpk, 'session_id', None):
                    _atq_hkpk.mark_session_pickup(_run_hkpk.session_id, state.current_tag)
            except Exception as _e_hkpk:
                print(f"[LINE_AGV] {agv_id}: mark pickup (hook) error: {_e_hkpk}")

    def _handle_firmware_errors(self, agv_id: str, state: "LineAGVState", data: dict) -> None:
        """Đọc 3 field báo lỗi THẬT firmware gửi lên theo đúng PROTOCOL_GUIDE.md §3
        (đã xác nhận với bên firmware — không phải suy đoán):
          - "errors": [{"errorType","errorLevel","errorDescription"}, ...]
          - "safetyState": {"eStop": "NONE"|"MANUAL", "fieldViolation": bool}
        Edge-trigger: chỉ in log/đặt cảnh báo/gửi Telegram lúc CHUYỂN từ hết→có
        (tránh spam mỗi state message trong lúc lỗi vẫn còn), tự xoá khi hết."""
        _errors_raw = data.get("errors")
        state.firmware_errors = _errors_raw if isinstance(_errors_raw, list) else []
        _safety = data.get("safetyState") or {}
        state.estop_state     = str(_safety.get("eStop") or "NONE").strip().upper() or "NONE"
        state.field_violation = bool(_safety.get("fieldViolation", False))

        # ── "errors"[] — lỗi chung firmware báo (kiểu/mức độ/mô tả) ─────────────
        _fw_now = bool(state.firmware_errors)
        if _fw_now and not self._fw_error_active.get(agv_id):
            self._fw_error_active[agv_id] = True
            _desc = "; ".join(
                f"{e.get('errorType', '?')}/{e.get('errorLevel', '?')}: {e.get('errorDescription', '')}"
                for e in state.firmware_errors if isinstance(e, dict)
            ) or str(state.firmware_errors)
            _msg = f"⚠️ AGV {agv_id}: firmware báo lỗi — {_desc}"
            print(f"[LINE_AGV] {agv_id}: {_msg}")
            self._set_alert(agv_id, state, "FIRMWARE_ERROR", _msg)
            try:
                from telegram_bot import notify_error as _tg_fw
                _tg_fw(_msg)
            except Exception as _e_tg_fw:
                print(f"[LINE_AGV] {agv_id}: Telegram báo lỗi firmware lỗi: {_e_tg_fw}")
        elif not _fw_now and self._fw_error_active.get(agv_id):
            self._fw_error_active[agv_id] = False
            print(f"[LINE_AGV] {agv_id}: firmware hết báo lỗi (errors[] rỗng lại)")
            self._clear_alert(state, "FIRMWARE_ERROR")

        # ── safetyState.eStop — "MANUAL" = xe đang ở trạng thái dừng/idle thủ công ──
        _estop_now = state.estop_state != "NONE"
        if _estop_now and not self._estop_active.get(agv_id):
            self._estop_active[agv_id] = True
            _msg = (f"⚠️ AGV {agv_id}: safetyState.eStop='{state.estop_state}' "
                    f"(xe đang ở trạng thái dừng/idle thủ công theo firmware)")
            print(f"[LINE_AGV] {agv_id}: {_msg}")
            self._set_alert(agv_id, state, "ESTOP", _msg)
            try:
                from telegram_bot import notify_error as _tg_estop
                _tg_estop(_msg)
            except Exception as _e_tg_estop:
                print(f"[LINE_AGV] {agv_id}: Telegram báo lỗi eStop lỗi: {_e_tg_estop}")
        elif not _estop_now and self._estop_active.get(agv_id):
            self._estop_active[agv_id] = False
            print(f"[LINE_AGV] {agv_id}: safetyState.eStop đã về 'NONE'")
            self._clear_alert(state, "ESTOP")

        # ── safetyState.fieldViolation — cảm biến vật cản kích hoạt (raw, song song
        # với event="obstacle" đã xử lý riêng ở nơi khác — ở đây chỉ để KHÔNG BAO
        # GIỜ rơi mất tín hiệu này khỏi log/dashboard/Telegram dù event có bị mất) ──
        _fv_now = state.field_violation
        if _fv_now and not self._field_violation_active.get(agv_id):
            self._field_violation_active[agv_id] = True
            _msg = f"⚠️ AGV {agv_id}: safetyState.fieldViolation=true — cảm biến vật cản đang kích hoạt"
            print(f"[LINE_AGV] {agv_id}: {_msg}")
            self._set_alert(agv_id, state, "FIELD_VIOLATION", _msg)
            try:
                from telegram_bot import notify_error as _tg_fv
                _tg_fv(_msg)
            except Exception as _e_tg_fv:
                print(f"[LINE_AGV] {agv_id}: Telegram báo lỗi fieldViolation lỗi: {_e_tg_fv}")
        elif not _fv_now and self._field_violation_active.get(agv_id):
            self._field_violation_active[agv_id] = False
            print(f"[LINE_AGV] {agv_id}: fieldViolation đã hết (vật cản đã rời)")
            self._clear_alert(state, "FIELD_VIOLATION")

    def _set_alert(self, agv_id: str, state: Optional["LineAGVState"], kind: str, message: str) -> None:
        """Ghi cảnh báo có cấu trúc lên state (đọc qua API agv-positions/agv-list
        → hiển thị trên map/UI thật). KHÔNG tự quyết định khi nào đáng báo —
        chỉ gọi tại ĐÚNG các điểm đã có sẵn cảnh báo Telegram, dùng lại message
        đã viết sẵn ở đó. Xem _clear_alert để biết khi nào tự hết."""
        if state is None:
            state = self.state_store.get(agv_id)
        if state is None:
            return
        _prev_kind = state.active_alert.get("kind") if state.active_alert else None
        if _prev_kind != kind:
            # Chỉ đếm khi THỰC SỰ là cảnh báo mới xuất hiện (đổi kind), không
            # đếm lại mỗi lần message lặp lại cùng 1 cảnh báo đang treo.
            _bump_traffic_stat("alerts", kind)
        state.active_alert = {"kind": kind, "message": message, "since": time.time()}

    def _clear_alert(self, state: Optional["LineAGVState"], kind: Optional[str] = None) -> None:
        """Xoá cảnh báo đang hiển thị khi hệ thống thấy đã ổn. `kind=None` xoá
        bất kỳ cảnh báo nào đang có (dùng ở các điểm 'xe đã nhúc nhích lại' —
        không cần biết trước đó là cảnh báo gì); truyền `kind` cụ thể để chỉ
        xoá ĐÚNG loại đó, tránh xoá nhầm 1 cảnh báo KHÁC vừa mới set."""
        if state is None or state.active_alert is None:
            return
        if kind is None or state.active_alert.get("kind") == kind:
            state.active_alert = None

    def set_external_alert(self, agv_id: str, kind: str, message: str, ttl_sec: float = 8.0) -> None:
        """Cảnh báo đến từ TIẾN TRÌNH NGOÀI (vd sim_monitor.py — theo dõi MQTT
        độc lập, KHÔNG chung process/memory với server) — dùng cho mô phỏng
        fleet để hiện va chạm/đối đầu phát hiện được NGAY trên map, không chỉ
        nằm trong bảng text. Khác _set_alert (nội bộ, có _clear_alert tương
        ứng khi server TỰ biết lúc nào hết): ở đây server KHÔNG có cách nào
        biết chính xác lúc vi phạm kết thúc (tiến trình ngoài, không chung
        state) — nên dùng TTL: nếu không được gọi lại (refresh) trong
        `ttl_sec` giây, cảnh báo TỰ hết (xem _line_agv_alert trong main.py,
        nơi đọc field `expires_at` này). Bên gọi (sim_monitor) chỉ cần gọi lại
        mỗi lần vẫn thấy vi phạm còn tiếp diễn — không cần tự theo dõi/gọi
        "clear" riêng."""
        state = self.state_store.get(agv_id)
        if state is None:
            return
        now = time.time()
        state.active_alert = {"kind": kind, "message": message, "since": now,
                               "expires_at": now + ttl_sec}

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
        self._set_alert(agv_id, None, "HOOK_ERROR", _msg)
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
        if event_name.startswith("arrived_wait") and state.current_tag is not None:
            state.position_confirmed_tag = str(state.current_tag)

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
                    new_end   = _time_capped_window_end(
                        route.full_path, current_idx,
                        min(current_idx + LOOKAHEAD, len(route.full_path) - 1))
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
            # Đoạn LÙI tạm (transit) kết thúc giữa đường tới siding KHÔNG phải đã đỗ:
            # nếu coi là đỗ, xe nằm lại giữa corridor và chặn đúng winner (deadlock).
            if (route and route.is_complete and state.yield_cmd
                    and (not state.yield_park
                         or str(state.current_tag) == str(state.yield_park))):
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
                # QUAN TRỌNG: đồng bộ current_tag về ĐÚNG node cuối route TRƯỚC khi
                # dispatch chặng kế — event arrived_wait_sys xác nhận đã hoàn tất
                # WAIT_SYS tại node cuối (route.full_path[-1]) theo đúng plan đã gửi,
                # nhưng nếu gói tin báo event này KHÔNG kèm theo tag mới (hoặc tag bị
                # trễ 1 nhịp) thì current_tag vẫn còn giữ giá trị CŨ (node xuất phát
                # của transit) → dispatch chặng kế tính đường từ SAI vị trí, y hệt bug
                # thực tế: lùi ra khỏi node thả hàng xong, chặng "đi tiếp" lại tính từ
                # đúng node thả hàng đó (chưa lùi) → lệnh mới bảo TIẾN thẳng vào lại
                # ngõ cụt thay vì lùi ra. Event WAIT_SYS đã xác nhận vị trí thật —
                # luôn tin route.full_path[-1] hơn current_tag có thể trễ.
                _final_tag_transit = route.full_path[-1] if route.full_path else None
                if _final_tag_transit and str(state.current_tag) != str(_final_tag_transit):
                    print(f"[LINE_AGV] {agv_id}: transit hoàn tất tại {_final_tag_transit} "
                          f"nhưng current_tag đang báo {state.current_tag} (trễ/thiếu cập "
                          f"nhật) — đồng bộ lại về {_final_tag_transit} trước khi dispatch tiếp")
                    # QUAN TRỌNG: đồng bộ CẢ prev_tag = node liền trước trong chính route
                    # transit này (full_path[-2]) — nếu chỉ sửa current_tag mà bỏ quên
                    # prev_tag, dispatch kế tính rẽ tại node hiện tại sẽ dùng SAI "from"
                    # (vd from=32→32→30 thay vì from=106→32→30 thật), tra turn_map trật
                    # → đi THẲNG thay vì rẽ đúng hướng, lùi thẳng vào lại đúng ngõ cụt vừa
                    # rời đi → lặp vô hạn (đã xảy ra thực tế: xe cứ 106↔32 mãi không thoát).
                    _prev_tag_transit = (route.full_path[-2]
                                          if len(route.full_path) >= 2 else None)
                    try:
                        state.current_tag = int(_final_tag_transit)
                    except (TypeError, ValueError):
                        state.current_tag = _final_tag_transit
                    if _prev_tag_transit is not None:
                        try:
                            state.prev_tag = int(_prev_tag_transit)
                        except (TypeError, ValueError):
                            pass
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
                # QUAN TRỌNG: is_complete chỉ có nghĩa "cửa sổ cuối đã gửi" (toàn bộ
                # full_path nằm trong 1 lần gửi), KHÔNG có nghĩa "xe đã tới node đích
                # thật". Với trạm sạc lùi vào (approach_dir=bwd), plan_builder chèn
                # WAIT_SYS (dừng hẳn bắt buộc, xem PROTOCOL_GUIDE "Đổi chiều lùi")
                # TẠI NODE TRUNG GIAN trước DIR_BWD — firmware báo arrived_wait_sys
                # ngay tại đó dù chưa hề lùi vào trạm. ACTION_WAIT_SYS luôn là điểm
                # DỪNG HẲN CHỜ SERVER (giống mọi chỗ khác trong hệ thống — rolling
                # window, giao/lấy hàng...) — KHÔNG tự chạy tiếp dù cùng 1 plan đã gửi
                # trước đó (đã kiểm chứng thực tế: xe đứng im tại đây, không tự lùi).
                # Server phải tự gửi tiếp lệnh DIR_BWD+RUN+WAIT_CHARGE để hoàn tất nốt
                # đoạn lùi còn lại; SERVER CHỈ được coi là "đã sạc" khi current_tag
                # THẬT SỰ là node cuối route (nhánh dưới).
                _final_node_chg = route.full_path[-1] if route.full_path else None
                _tag_str_chg = str(state.current_tag) if state.current_tag is not None else None
                if _final_node_chg and _tag_str_chg != str(_final_node_chg):
                    print(f"[LINE_AGV] {agv_id}: wait_sys giữa route return_charge tại "
                          f"{_tag_str_chg} (đích thật {_final_node_chg}) — CHƯA tới trạm sạc, "
                          f"gửi tiếp lệnh lùi vào trạm")
                    self._send_reverse_into_charger(agv_id, route, _tag_str_chg, _final_node_chg)
                    return
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
                    try:
                        current_idx = route.full_path.index(tag_str)
                    except ValueError:
                        current_idx = 0
                    _next_node_ws = (route.full_path[current_idx + 1]
                                      if current_idx + 1 < len(route.full_path) else None)
                    # Vật cản THẬT đã biết (accumulated_blocked) ngay tại node kế tiếp
                    # → không gửi lại mù vào đó; cơ chế obstacle-timeout tự xử lý tiếp.
                    _blocked_by_obstacle_ws = (
                        _next_node_ws is not None
                        and str(_next_node_ws) in state.accumulated_blocked)
                    # Xung đột AGV-vs-AGV: kiểm tra LẠI TƯƠI (không tin giá trị cũ của
                    # waiting_before_conflict, có thể đã hết từ trước mà chưa ai clear)
                    # bằng đúng hàm proactive-check dùng ở rolling-plan-tick.
                    _traffic_end_ws = min(current_idx + TRAFFIC_LOOKAHEAD, len(route.full_path) - 1)
                    _conflict_raw_ws = self._find_upcoming_conflict(
                        agv_id, route, current_idx, _traffic_end_ws)
                    if _blocked_by_obstacle_ws or _conflict_raw_ws is not None:
                        # PHÁT HIỆN THỰC TẾ (2026-09-25, AGV03/AGV04 kẹt >2 phút tại
                        # node 28/15): khi _find_upcoming_conflict trả về giá trị
                        # KHÔNG ÂM (head-on, xe MÌNH thua arbiter → cần né/reroute,
                        # xem _find_upcoming_conflict), nhánh này trước đây chỉ đứng
                        # im "chờ cơ chế theo dõi tự xử lý" mà KHÔNG hề tự thử reroute
                        # — trong khi watchdog nudge định kỳ (đứng yên phía sau
                        # window_end) cũng chỉ gửi lại y hệt cửa sổ cũ chứ không gọi
                        # lại logic né/reroute này. Kết quả: xe thua arbiter đứng im
                        # VĨNH VIỄN chờ xe thắng đi qua, trong khi xe thắng lại đang
                        # tự thấy node kế "bị xe thua giữ chỗ (reserve_ahead)" (do xe
                        # thua đã reserve trước theo route riêng của nó, không liên
                        # quan quyết định arbiter) nên CŨNG đứng chờ → deadlock 2
                        # chiều, chỉ thoát được nhờ can thiệp thủ công. Nếu là
                        # head-on (không phải chỉ "following" chờ xe cùng chiều —
                        # phân biệt qua _conflict_raw_ws >= 0, xem quy ước dấu ở
                        # _find_upcoming_conflict), thử né/reroute ngay tại đây,
                        # giống hệt nhánh A2 của _check_rolling_plan.
                        if not _blocked_by_obstacle_ws and _conflict_raw_ws is not None \
                                and _conflict_raw_ws >= 0 \
                                and self._try_line_reroute(agv_id, state, route, current_idx):
                            print(f"[LINE_AGV] {agv_id}: wait_sys tại node trung gian "
                                  f"{tag_str} — thua head-on nhưng còn đường khác → "
                                  f"ĐI ĐƯỜNG KHÁC thay vì đứng chờ mãi")
                            return
                        print(f"[LINE_AGV] {agv_id}: wait_sys tại node trung gian {tag_str} "
                              f"(đích thực là {final_node}) nhưng phía trước vẫn còn chặn "
                              f"(obstacle={_blocked_by_obstacle_ws}, conflict={_conflict_raw_ws}) "
                              f"— KHÔNG gửi lại mù, chờ cơ chế theo dõi tự xử lý")
                        return
                    # QUAN TRỌNG (phát hiện thực tế 2026-09-17): nếu KHÔNG có gì
                    # chặn (obstacle/conflict) mà vẫn cứ resend liên tục CÙNG 1
                    # node không tiến — nghi plan bị firmware "nuốt" (MANUAL/race,
                    # cùng họ lỗi đã gặp ở _send_line_order/_start_locate_then_
                    # charge). Đếm để CẢNH BÁO RÕ thay vì lặng lẽ resend vô hạn
                    # trông như hệ thống treo mà không ai biết vì sao.
                    _prev_tag_ws, _prev_cnt_ws = self._intermediate_resend.get(agv_id, (None, 0))
                    _cnt_ws = (_prev_cnt_ws + 1) if _prev_tag_ws == tag_str else 1
                    self._intermediate_resend[agv_id] = (tag_str, _cnt_ws)
                    if _cnt_ws in (5, 15, 30):
                        _msg_resend_ws = (
                            f"⚠️ AGV {agv_id}: đã gửi lại plan {_cnt_ws} lần liên tiếp tại "
                            f"node {tag_str} (đích {final_node}) mà KHÔNG tiến được — không "
                            f"phải do vật cản/xung đột giao thông, nghi firmware không thực "
                            f"thi plan (MANUAL/mất gói). Cần kiểm tra xe {agv_id} trực tiếp "
                            f"nếu tiếp tục kẹt.")
                        print(f"[LINE_AGV] {agv_id}: {_msg_resend_ws}")
                        self._set_alert(agv_id, state, "RESEND_LOOP", _msg_resend_ws)
                        # Cùng lý do với cảnh báo "đứng yên quá 60s" ở trên: chỉ in
                        # console thì người vận hành không thấy — đẩy qua Telegram.
                        try:
                            from telegram_bot import notify_error as _tg_notify_resend_ws
                            _tg_notify_resend_ws(_msg_resend_ws)
                        except Exception as _e_tg_resend_ws:
                            print(f"[LINE_AGV] {agv_id}: gửi Telegram cảnh báo resend lỗi: {_e_tg_resend_ws}")
                    print(f"[LINE_AGV] {agv_id}: wait_sys tại node trung gian {tag_str} "
                          f"(đích thực là {final_node}) — gửi lại plan tiếp")
                    # Gửi cửa sổ ≤LOOKAHEAD node (không gửi full remaining) — tránh tràn buffer
                    new_end  = _time_capped_window_end(
                        route.full_path, current_idx,
                        min(current_idx + LOOKAHEAD, len(route.full_path) - 1))
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
            # ── THANG MÁY: xe tới node trung gian của chuỗi đi thang (điểm chờ / node chờ / cabin / node thoát) → TỰ ĐỘNG
            # đi tiếp theo tín hiệu thang (bước elev_* kế tiếp), KHÔNG vào "picking" chờ xác nhận web/HMI.
            if self._handle_elevator_leg_arrival(agv_id, state):
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
            _is_confirm_only_ws = ((_confirm_only_key_ws in _pending_confirm_only_legs
                                    or self._carry_skip_hook(agv_id, str(state.current_tag)))
                                   and not _is_trailer_staging_ws)
            if _confirm_only_key_ws in _pending_confirm_only_legs:
                _pending_confirm_only_legs.discard(_confirm_only_key_ws)   # dọn dấu, kể cả khi bị staging ghi đè
            if (agv_registry.get_config(agv_id).get('agv_type') in ('trailer', 'tow')
                    and not _is_confirm_only_ws):
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
            _is_confirm_only_wu = ((_confirm_only_key_wu in _pending_confirm_only_legs
                                    or self._carry_skip_hook(agv_id, str(state.current_tag)))
                                   and not _is_trailer_staging_wu)
            if _confirm_only_key_wu in _pending_confirm_only_legs:
                _pending_confirm_only_legs.discard(_confirm_only_key_wu)
            if (agv_registry.get_config(agv_id).get('agv_type') in ('trailer', 'tow')
                    and not _is_confirm_only_wu):
                self._handle_trailer_hook_arrival(agv_id, state, _route_wu)
                return
            if _route_wu:
                # Đối xứng: ghi lại ĐÚNG chiều chặng vừa hoàn tất (không chỉ 'bwd')
                # để các quyết định hướng khởi hành kế tiếp (resolve_departure_direction)
                # luôn có tín hiệu đáng tin cậy, không phụ thuộc giá trị cũ còn sót lại.
                state.last_transit_direction = _route_wu.direction
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
            # Vừa bị STOP vì va chạm vật lý (main.physical_collision_active): KHÔNG tự re-dispatch — cần người kiểm tra xe.
            _ch_hold = self.__dict__.get('_collision_hold', {}).get(agv_id)
            if _ch_hold is not None and time.monotonic() - _ch_hold < COLLISION_HOLD_SEC:
                print(f"[LINE_AGV] {agv_id}: off_route trong {COLLISION_HOLD_SEC:.0f}s sau va chạm vật lý — "
                      f"KHÔNG tự điều xe lại, chờ người kiểm tra")
                return
            route = self._routes.pop(agv_id, None)
            traffic_coordinator.deregister(agv_id)
            _release_all_line_edges(agv_id)
            state.current_edge_pair = None
            dest_node  = route.full_path[-1] if (route and route.full_path) else None
            task_type  = route.task_type     if route else "delivery"
            cur_tag    = state.current_tag
            print(f"[LINE_AGV] {agv_id}: off_route tại tag={cur_tag} "
                  f"dest={dest_node} task={task_type}")

            # ── Phát hiện vòng lặp off_route (xe cứ bị đẩy về ĐÚNG 1 tag rồi
            # off_route lại, vd rẽ sai hướng tại 1 ngã tư sau khi vừa lùi tới) —
            # xem giải thích tại self._off_route_history trong __init__.
            _now_orl = time.monotonic()
            _hist_orl = self._off_route_history.setdefault(agv_id, [])
            _hist_orl.append((str(cur_tag), _now_orl))
            del _hist_orl[:-(max(OFF_ROUTE_LOOP_THRESHOLD, OFF_ROUTE_DRIFT_THRESHOLD) + 2)]
            _recent_orl = [t for t, ts in _hist_orl
                           if _now_orl - ts <= OFF_ROUTE_LOOP_WINDOW_SEC]
            _is_bounce_loop = (
                len(_recent_orl) >= OFF_ROUTE_LOOP_THRESHOLD
                and len(set(_recent_orl[-OFF_ROUTE_LOOP_THRESHOLD:])) == 1
            )
            _is_drift_thrash = len(_recent_orl) >= OFF_ROUTE_DRIFT_THRESHOLD
            if _is_bounce_loop or _is_drift_thrash:
                self._off_route_history.pop(agv_id, None)
                if _is_bounce_loop:
                    _msg_bl = (f"⚠️ AGV {agv_id}: off_route lặp lại {OFF_ROUTE_LOOP_THRESHOLD}+ "
                               f"lần LIÊN TIẾP tại ĐÚNG node {cur_tag} trong "
                               f"{OFF_ROUTE_LOOP_WINDOW_SEC:.0f}s (vòng lặp tiến-lùi, không tự "
                               f"thoát được) — DỪNG tự động re-dispatch, cần kiểm tra cấu hình "
                               f"rẽ (turn_map) tại node {cur_tag} trên Map Editor. Xe đang đứng "
                               f"yên chờ thao tác thủ công.")
                else:
                    _path_orl = " → ".join(t for t, _ in _hist_orl[-OFF_ROUTE_DRIFT_THRESHOLD:])
                    _msg_bl = (f"⚠️ AGV {agv_id}: off_route {OFF_ROUTE_DRIFT_THRESHOLD}+ lần trong "
                               f"{OFF_ROUTE_LOOP_WINDOW_SEC:.0f}s dù KHÔNG lặp lại đúng 1 node — có "
                               f"vẻ xe đang TRÔI DẦN qua nhiều node do rẽ sai hướng liên tiếp "
                               f"(đường đi gần đây: {_path_orl}) — DỪNG tự động re-dispatch, cần "
                               f"kiểm tra cấu hình rẽ trên các node đó. Xe đang đứng yên chờ thao "
                               f"tác thủ công.")
                print(f"[LINE_AGV] {agv_id}: {_msg_bl}")
                self._set_alert(agv_id, state,
                                 "OFF_ROUTE_LOOP" if _is_bounce_loop else "OFF_ROUTE_DRIFT",
                                 _msg_bl)
                try:
                    from telegram_bot import notify_error as _tg_notify_bl
                    _tg_notify_bl(_msg_bl)
                except Exception as _e_tg_bl:
                    print(f"[LINE_AGV] {agv_id}: gửi Telegram cảnh báo vòng lặp off_route lỗi: {_e_tg_bl}")
                try:
                    from task_queue import agv_task_queue as _atq_bl
                    _atq_bl.on_agv_completed(agv_id, notes='off_route_bounce_loop', auto_dispatch=False)
                except Exception as _e_atq_bl:
                    print(f"[LINE_AGV] {agv_id}: dừng queue sau vòng lặp off_route lỗi: {_e_atq_bl}")
                return

            if dest_node and cur_tag is not None:
                try:
                    from task_queue import agv_task_queue as _atq
                    from task_queue import CMD_GO_TO as _CGT, CMD_GO_CHARGE as _CGC
                    cmd = _CGC if task_type in ("return_charge",) else _CGT
                    # Route bị ngắt (off_route) vốn là transit (staging node, không
                    # phải đích giao/lấy hàng thật) → phải giữ nguyên task_type=transit
                    # cho lần dispatch lại, nếu không _dispatch_go_to sẽ coi staging
                    # node là đích thật (mặc định 'delivery') → hạ móc nhầm chỗ trước
                    # khi tới đích thật. Dùng chung cơ chế _pending_staging_transits
                    # (đã có sẵn cho trường hợp split-route) để đánh dấu.
                    if task_type == "transit":
                        try:
                            from main import _pending_staging_transits as _pst_or
                            _pst_or.add((agv_id, str(dest_node)))
                        except Exception:
                            pass
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
            if self._is_tow_agv(agv_id):
                if state.hook_prearmed_for:
                    # Đây là xác nhận NÂNG MÓC TRƯỚC 1 node (xem
                    # _maybe_preraise_tow_hook) — xe CHƯA tới hẳn điểm lấy hàng,
                    # chỉ vừa nâng xong móc trong lúc còn đang chạy tới đó. KHÔNG
                    # vào lifecycle "picking" ở đây (xe còn di chuyển bình
                    # thường) — để _handle_trailer_hook_arrival tự chuyển
                    # "picking" khi xe THẬT SỰ tới đích (so khớp hook_prearmed_for
                    # với current_tag lúc đó).
                    print(f"[LINE_AGV] {agv_id}: móc đã nâng TRƯỚC (đích "
                          f"{state.hook_prearmed_for}) — xe tiếp tục chạy tới nơi")
                    return
                # AGV kéo: NÂNG là hành động THỦ CÔNG (nút Web UI, xem
                # confirm_hook_manual) hoàn tất LẤY hàng — vai trò y hệt event
                # "hook_lowered" của rơ-moóc bên dưới, chỉ đảo hướng lệnh. Áp
                # dụng CHUNG không xét pending vì nút chỉ hiện khi pending=='pickup'.
                state.hook_pending = None
                state.task_lifecycle = "picking"
                print(f"[LINE_AGV] {agv_id}: móc đã nâng (xe hàng đã gắn) "
                      f"— chờ xác nhận trên web để đi tiếp")
                if self.on_state_changed:
                    try:
                        self.on_state_changed(state)
                    except Exception as e:
                        print(f"[LINE_AGV] on_state_changed error: {e}")
            elif state.hook_pending == "dropoff":
                state.hook_pending = None
                print(f"[LINE_AGV] {agv_id}: móc đã nâng (xe hàng đã nhả) — tự động đi tiếp")
                self._complete_hook_leg(agv_id, "hook_raised")
            elif state.hook_pending == "pickup":
                # GIỮ NGUYÊN hook_pending='pickup' — KHÔNG tự động hạ móc nữa (theo
                # yêu cầu: chỉ nâng tự động, hạ phải qua thao tác thủ công của người
                # dùng trên Web UI). Web UI dựa vào hook_pending=='pickup' để hiện nút
                # xác nhận — chỉ event 'hook_lowered' (sau khi người dùng bấm nút, xem
                # confirm_hook_manual/POST /api/execute/hook-confirm) mới clear field này.
                print(f"[LINE_AGV] {agv_id}: móc đã nâng — chờ người dùng móc hàng vào "
                      f"rồi bấm Hạ móc trên Web UI")
            else:
                state.hook_pending = None
                print(f"[LINE_AGV] {agv_id}: móc đã nâng — chờ xe hàng được đưa vào")
            return

        if event_name == "hook_lowered":
            state.hook_state = "lowered"
            state.hook_raise_sent_at = 0.0   # có phản hồi → dừng theo dõi retry
            state.hook_lowered_at = time.monotonic()
            if self._is_tow_agv(agv_id):
                # AGV kéo: HẠ là hành động gửi TỰ ĐỘNG lúc TỚI node (vai trò y hệt
                # event "hook_raised" của rơ-moóc phía trên, chỉ đảo hướng lệnh) —
                # dropoff tự hoàn tất, pickup chỉ là bước canh chờ xác nhận thủ công.
                if state.hook_pending == "dropoff":
                    state.hook_pending = None
                    print(f"[LINE_AGV] {agv_id}: móc đã hạ (xe hàng đã nhả) — tự động đi tiếp")
                    self._complete_hook_leg(agv_id, "hook_lowered")
                elif state.hook_pending == "pickup":
                    print(f"[LINE_AGV] {agv_id}: móc đã hạ — chờ người dùng móc hàng vào "
                          f"rồi bấm Nâng móc trên Web UI")
                else:
                    state.hook_pending = None
                    print(f"[LINE_AGV] {agv_id}: móc đã hạ — chờ xe hàng được đưa vào")
            else:
                # Rơ-moóc: HẠ là hành động THỦ CÔNG hoàn tất LẤY hàng — áp dụng
                # CHUNG cho mọi điểm lấy hàng (Tổ lẫn điểm lấy hàng rỗng gần trạm),
                # luôn chờ xác nhận web trước khi đi tiếp, không tự động.
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
        # Nút XÁC NHẬN bấm trực tiếp trên xe (HMI) khi xe đang CHỜ XÁC NHẬN MÓC (hook_pending='pickup', web hiện nút "Xác nhận
        # móc") → làm ĐÚNG việc nút web làm (confirm_hook_manual: gửi lệnh móc phù hợp loại xe). Trước đây event này rơi xuống
        # nhánh hoàn tất bên dưới → hàng đợi đi tiếp mà xe CHƯA móc xe hàng. Sau khi móc xong xe vào lifecycle 'picking' (chờ
        # "Đã lấy hàng"); nút TIẾP TỤC/XÁC NHẬN trên xe lần kế sẽ hoàn tất như nút web (nhánh bên dưới).
        # Chỉ 'confirm' (người bấm); KHÔNG 'continue' — firmware cũng phát 'continue' tự động khi xe tới đích chờ hệ thống.
        if event_name == "confirm" and state.hook_pending == "pickup":
            _hk = self.confirm_hook_manual(agv_id)
            if _hk.get("ok"):
                print(f"[LINE_AGV] {agv_id}: nút XÁC NHẬN trên xe lúc chờ móc hàng → xác nhận móc (như nút web), "
                      f"lệnh {_hk.get('action_code')}")
                return
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
                            _we_res = _time_capped_window_end(
                                _completed_route.full_path, _ci_res,
                                min(_ci_res + LOOKAHEAD,
                                    len(_completed_route.full_path) - 1))
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
            # Lưu hướng vừa hoàn thành để dispatch tiếp theo dùng — đối xứng cả 2
            # chiều (không chỉ 'bwd') để resolve_departure_direction() tin cậy được.
            if _completed_route:
                state.last_transit_direction = _completed_route.direction
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


def path_claimed_by_other(agv_id: str, nodes) -> Optional[str]:
    """Trả về id xe KHÁC đang CHIẾM bất kỳ node nào trong `nodes` (thường là đoạn đường xe này sẽ đi tới 1 node đích), hoặc None.
    'Chiếm' gồm: xe khác đang đứng đó, đang giữ chỗ (reservation), hoặc node nằm trong phần ĐƯỜNG CÒN LẠI của route xe khác
    (xe đó sắp đi qua/tới đó dù CHƯA tới nơi). Dùng để chọn giữa các node có chức năng tương đương (điểm xếp hàng thang,
    điểm lấy hàng rỗng …): ưu tiên node mà đường tới đó đang thông thoáng. Xe offline coi như không tồn tại."""
    want = {str(n) for n in nodes if n is not None and str(n) != ""}
    if not want:
        return None
    try:
        for oid, st in list(line_agv_handler.state_store._states.items()):
            if oid == agv_id or st is None or not line_state_online(st):
                continue
            cur = str(st.current_tag) if st.current_tag is not None else None
            if cur and cur in want:
                return oid
            rt = line_agv_handler._routes.get(oid)
            if rt and rt.full_path:
                fp = [str(x) for x in rt.full_path]
                try:
                    i0 = fp.index(cur) if cur in fp else 0
                except ValueError:
                    i0 = 0
                if want & set(fp[i0:]):
                    return oid
        for n in want:
            o = traffic_coordinator.node_reserved_by_other(agv_id, n)
            if o:
                return o
    except Exception:
        return None
    return None
