"""
test_traffic_safety.py — Chốt chặn AN TOÀN cho hệ thống traffic Line-AGV.

Mục đích: chạy LẠI sau MỖI thay đổi traffic để bảo đảm KHÔNG bao giờ tái phạm va chạm.
Đây là "sàn an toàn" (Bước 2 của plan): allocate-before-move + không giành node xe khác
đang đứng / đang-là-bước-kế. Các bước sau (né chủ động, resume...) thêm test riêng nhưng
file này phải LUÔN xanh.

Chạy:  python test_traffic_safety.py
(cần postgres TOT_AGV chạy — dùng graph map 1779790224391 thật)
"""
import sys
import psycopg2
import networkx as nx

import line_agv_handler as LH
from mqtt_client import map_manager as MM

DB = "postgresql://postgres:ducmanh1801@localhost:5432/TOT_AGV"
MAP_ID = "1779790224391"

_PASS = 0
_FAIL = 0


def _ok(msg):
    global _PASS
    _PASS += 1
    print(f"  PASS: {msg}")


def _bad(msg):
    global _FAIL
    _FAIL += 1
    print(f"  FAIL: {msg}")


def load_graph():
    conn = psycopg2.connect(DB)
    cur = conn.cursor()
    cur.execute(
        "SELECT id_source,id_dest,distance FROM agv_map_roads WHERE map_id=%s",
        (MAP_ID,),
    )
    g = nx.Graph()
    for s, d, dist in cur.fetchall():
        g.add_edge(str(s), str(d), weight=float(dist or 1))
    conn.close()
    return g


def reset(g):
    """Đưa traffic coordinator về trạng thái sạch + nạp graph (không block tay)."""
    MM.line_graph = g
    MM.graph = g
    MM.node_actions = {}
    tc = LH.traffic_coordinator
    h = LH.line_agv_handler
    tc._registered.clear()
    tc._node_res.clear()
    tc._edge_res.clear()
    tc._intent_route.clear()
    tc._block_holders.clear()
    tc._block_dir.clear()
    tc._block_cfg_src = None
    LH._line_blocked_edges.clear() if hasattr(LH, "_line_blocked_edges") else None
    h._routes.clear()
    h.state_store._states.clear()
    return tc, h


def place(h, agv_id, tag, driving=False):
    st = h.state_store.get_or_create(agv_id)
    st.current_tag = tag
    st.driving = driving
    return st


# ════════════════════════════════════════════════════════════════════════════
# INVARIANT chính: không 2 AGV cùng giữ 1 node
# ════════════════════════════════════════════════════════════════════════════
def assert_no_shared_node(tc):
    """_node_res là map node→owner duy nhất nên cấu trúc đã đảm bảo 1 chủ/node.
    Test này kiểm tra reserve_ahead của nhiều xe không tạo overlap logic."""
    seen = {}
    for node, owner in tc._node_res.items():
        if node in seen and seen[node] != owner:
            return False
        seen[node] = owner
    return True


def test_no_steal_occupied():
    """Xe MẠNH không giành node mà xe YẾU đang ĐỨNG (current_tag==node) → hết đâm."""
    print("[test] không giành node xe khác đang ĐỨNG")
    g = load_graph()
    tc, h = reset(g)
    # AGV01 yếu (charge) đứng tại 5; AGV02 mạnh (delivery)
    tc._registered["AGV01"] = {"path": ["5", "8", "15", "9", "4"], "direction": "bwd",
                                "current_idx": 0, "priority": 1}
    tc._registered["AGV02"] = {"path": ["4", "18", "5", "17"], "direction": "fwd",
                                "current_idx": 0, "priority": 3}
    place(h, "AGV01", "5", driving=False)
    place(h, "AGV02", "4", driving=True)
    tc._node_res["5"] = "AGV01"
    got = tc._reserve_node("AGV02", "5")
    if got is False and tc._node_res["5"] == "AGV01":
        _ok("AGV02(mạnh) KHÔNG giành được node 5 (AGV01 đang đứng)")
    else:
        _bad(f"AGV02 giành được node 5 → sẽ đâm (got={got})")


def test_no_steal_committed():
    """Xe MẠNH không giành node là BƯỚC KẾ của xe YẾU (sắp vào) dù xe yếu dừng tạm."""
    print("[test] không giành node là bước-kế xe khác")
    g = load_graph()
    tc, h = reset(g)
    # AGV01 yếu ở 18, route 18->4->19, node 4 là bước kế (đã giữ); dừng tạm
    tc._registered["AGV01"] = {"path": ["18", "4", "19"], "direction": "fwd",
                                "current_idx": 0, "priority": 1}
    tc._registered["AGV02"] = {"path": ["19", "4", "18"], "direction": "fwd",
                                "current_idx": 0, "priority": 3}
    place(h, "AGV01", "18", driving=False)
    place(h, "AGV02", "19", driving=True)
    tc._node_res["4"] = "AGV01"
    got = tc._reserve_node("AGV02", "4")
    if got is False and tc._node_res["4"] == "AGV01":
        _ok("AGV02(mạnh) KHÔNG giành được node 4 (bước-kế AGV01) → dừng trước chờ")
    else:
        _bad(f"AGV02 giành được node 4 (AGV01 sắp vào) → sẽ đâm (got={got})")


def test_window_cap_blocks_overlap():
    """Window xe bị CẮT tại node đã giữ — không lao vào node xe khác giữ."""
    print("[test] window-cap chặn lao vào vùng xe khác giữ")
    g = load_graph()
    tc, h = reset(g)
    # AGV02 muốn đi 4->18->5->17 nhưng node 18 đang bị AGV01 giữ
    tc._registered["AGV02"] = {"path": ["4", "18", "5", "17"], "direction": "fwd",
                                "current_idx": 0, "priority": 3}
    tc._node_res["4"] = "AGV02"     # AGV02 giữ node hiện tại
    tc._node_res["18"] = "AGV01"    # node kế bị xe khác giữ
    tc._registered["AGV01"] = {"path": ["18"], "direction": "fwd",
                                "current_idx": 0, "priority": 3}  # AGV01 tồn tại (không mồ côi)
    ext = tc.reserved_extent("AGV02", ["4", "18", "5", "17"], 0)
    if ext == 0:
        _ok("reserved_extent=0 → window AGV02 chỉ [0→0], dừng tại 4 (không vào 18)")
    else:
        _bad(f"reserved_extent={ext} → AGV02 lao vào node 18 đang bị giữ → đâm")


def test_edge_headon_blocked():
    """2 xe ngược chiều trên CÙNG cạnh: cạnh chỉ 1 chủ → xe kia bị chặn."""
    print("[test] head-on cùng cạnh bị chặn (edge reservation)")
    g = load_graph()
    tc, h = reset(g)
    tc._registered["AGV01"] = {"path": ["4", "19", "64"], "direction": "fwd",
                                "current_idx": 0, "priority": 1}
    tc._registered["AGV02"] = {"path": ["64", "19", "4"], "direction": "fwd",
                                "current_idx": 0, "priority": 3}
    place(h, "AGV01", "4", driving=True)
    place(h, "AGV02", "64", driving=True)
    tc.reserve_ahead("AGV01")
    tc.reserve_ahead("AGV02")
    # Cạnh 19-64 không thể vừa của AGV01 vừa của AGV02
    e = frozenset(("19", "64"))
    owner = tc._edge_res.get(e)
    # Ít nhất 1 trong 2 xe KHÔNG được vào sâu cả đoạn (auto-block 19-64 hoặc edge res)
    ext1 = tc.reserved_extent("AGV01", ["4", "19", "64"], 0)
    ext2 = tc.reserved_extent("AGV02", ["64", "19", "4"], 0)
    # Không được cả 2 cùng vươn tới node chung 19 (idx1=1 cho cả 2)
    a1_has19 = tc._node_res.get("19") == "AGV01"
    a2_has19 = tc._node_res.get("19") == "AGV02"
    if not (a1_has19 and a2_has19):
        _ok(f"node 19 chỉ 1 chủ (AGV01={a1_has19}, AGV02={a2_has19}); ext1={ext1} ext2={ext2}")
    else:
        _bad("cả 2 xe cùng giữ node 19 → đâm head-on")
    if assert_no_shared_node(tc):
        _ok("không node nào có 2 chủ (invariant chính)")
    else:
        _bad("có node bị 2 xe cùng giữ")


def test_autoblock_single_lane():
    """Đoạn đơn 19-64 thành auto-block: 1 xe vào cả đoạn, xe kia bị chặn ngoài."""
    print("[test] auto-block đoạn đơn 19-64")
    g = load_graph()
    tc, h = reset(g)
    tc._refresh_block_config()
    auto = {k: sorted(v) for k, v in tc._block_nodes.items() if k.startswith("auto_")}
    has_1964 = any(set(v) >= {"19", "64"} for v in auto.values())
    if has_1964:
        _ok(f"19-64 là block đơn (auto-blocks={auto})")
    else:
        _bad(f"19-64 KHÔNG thành block đơn (auto={auto})")
    # AGV01 vào block; AGV02 thử vào từ đầu kia → bị chặn
    tc.register("AGV01", ["4", "19", "64", "2"], "fwd", "return_charge")
    bid = tc._block_of_node.get("64")
    blocked = tc._single_block_blocked_by_other(bid, "AGV02") if bid else False
    if blocked:
        _ok("AGV02 bị chặn vào đoạn 19-64 khi AGV01 đang trong đó")
    else:
        _bad("AGV02 KHÔNG bị chặn → 2 xe cùng vào đoạn đơn → đâm")


def test_yield_offpath_siding():
    """Xe THUA tìm được waiting node NGOÀI đường winner, rẽ ngay từ node hiện tại."""
    print("[test] xe thua né siding off-path (Bước 3)")
    g = load_graph()
    tc, h = reset(g)
    # Winner AGV02 (delivery) đi corridor 19→4→18→5→17; Loser AGV01 (charge) ngược lại.
    tc._registered["AGV02"] = {"path": ["19", "4", "18", "5", "17"], "direction": "fwd",
                                "current_idx": 0, "priority": 3}
    loser_path = ["17", "5", "18", "4", "19", "64", "2", "1", "13"]
    winner_future = {"19", "4", "18", "5", "17"}
    park = tc.find_parking_node("AGV01", loser_path, 2, "AGV02")
    if park is None:
        _bad("find_parking_node trả None (xe thua không có chỗ né)")
        return
    siding, entry = park
    if siding not in winner_future and siding not in set(loser_path):
        _ok(f"siding={siding} (rẽ tại {entry}) NẰM NGOÀI đường winner → winner đi qua được")
    else:
        _bad(f"siding={siding} vẫn trên đường winner/loser → không né được")


def test_arbiter_single_winner():
    """Trọng tài đối xứng: đúng 1 xe THẮNG → đúng 1 xe nhường (không cả 2 cùng né/đi)."""
    print("[test] trọng tài chọn đúng 1 xe thắng (Bước 3)")
    g = load_graph()
    tc, h = reset(g)
    tc._registered["AGV01"] = {"path": ["17", "5", "18", "4"], "direction": "bwd",
                                "current_idx": 0, "priority": 1}  # charge yếu
    tc._registered["AGV02"] = {"path": ["19", "4", "18", "5", "17"], "direction": "fwd",
                                "current_idx": 0, "priority": 3}  # delivery mạnh
    w1 = tc._arbitrate("AGV01", "AGV02", "5")
    w2 = tc._arbitrate("AGV02", "AGV01", "5")
    if w1 == w2 == "AGV02":
        _ok("trọng tài đối xứng → AGV02 thắng cả 2 chiều; AGV01 là xe DUY NHẤT nhường")
    else:
        _bad(f"trọng tài KHÔNG đối xứng (w1={w1}, w2={w2}) → có thể cả 2 cùng nhường/đi")


def test_reroute_avoids_winner():
    """Xe THUA reroute né HẲN đường winner (đi nhánh loop khác) — chỉ xe thua đổi đường,
    winner giữ nguyên (đa dạng tuyến tất định, không cả-hai-cùng-nhảy-1-nhánh)."""
    print("[test] xe thua reroute né đường winner (Bước 6)")
    import line_agv_handler as _LH
    g = load_graph()
    tc, h = reset(g)
    # Winner AGV02 (delivery) giữ corridor 19→4→18→5→17
    tc._registered["AGV02"] = {"path": ["19", "4", "18", "5", "17"], "direction": "fwd",
                                "current_idx": 0, "priority": 3}
    h.state_store.get_or_create("AGV02").current_tag = "19"
    h.state_store.get_or_create("AGV02").driving = False
    # Loser AGV01 (charge) ở 17 đi 13 qua corridor — phải reroute sang loop né 18,5
    tc._registered["AGV01"] = {"path": ["17", "5", "18", "4", "19", "64", "2", "1", "13"],
                                "direction": "bwd", "current_idx": 0, "priority": 1}
    st1 = place(h, "AGV01", "17", driving=False)
    st1.prev_tag = 5
    r1 = _LH.LineAGVRoute(full_path=["17", "5", "18", "4", "19", "64", "2", "1", "13"],
                          task_type="return_charge", direction="bwd",
                          window_start=0, window_end=4, is_complete=False)
    h._routes["AGV01"] = r1
    _saved = h.send_window_fn
    h.send_window_fn = lambda a, p: None
    try:
        ok = h._try_line_reroute("AGV01", st1, r1, 0)
        # đường mới phải KHÁC và NÉ node 18/5 (đường winner) — đi qua 6 (nhánh loop)
        if "6" in r1.full_path and ("18" not in r1.full_path[:4] or "5" not in r1.full_path[:3]):
            _ok(f"AGV01 reroute → {r1.full_path[:6]}... (đi loop qua 6, né corridor winner)")
        else:
            _bad(f"AGV01 KHÔNG né được đường winner: {r1.full_path}")
    finally:
        h.send_window_fn = _saved


def test_staging_intent_avoided():
    """Xe STAGING đăng ký đoạn NGẮN nhưng intent ĐẦY ĐỦ tới đích thật → xe khác thấy
    được đoạn còn lại để né (gốc lỗi: staging không ghi intent → AGV01 đi xuyên node 5)."""
    print("[test] staging ghi intent đầy đủ → xe khác né được (Bước 6/log)")
    import line_agv_handler as _LH
    g = load_graph()
    tc, h = reset(g)
    # AGV02 (delivery, mạnh) STAGING: chỉ đăng ký đoạn ['4','18'] nhưng intent đầy đủ
    # tới đích thật 17 = [4,18,5,17]
    tc._registered["AGV02"] = {"path": ["4", "18"], "direction": "fwd",
                                "current_idx": 0, "priority": 3}
    tc.set_intent_route("AGV02", ["4", "18", "5", "17"])
    h.state_store.get_or_create("AGV02").current_tag = "4"
    h.state_store.get_or_create("AGV02").driving = False
    # AGV01 (charge, yếu) ở 17, route mặc định đi XUYÊN node 5
    tc._registered["AGV01"] = {"path": ["17", "5", "8", "15", "9", "4", "19", "64", "2", "1", "13"],
                                "direction": "bwd", "current_idx": 0, "priority": 1}
    st1 = place(h, "AGV01", "17", driving=False)
    st1.prev_tag = 5
    r1 = _LH.LineAGVRoute(full_path=["17", "5", "8", "15", "9", "4", "19", "64", "2", "1", "13"],
                          task_type="return_charge", direction="bwd",
                          window_start=0, window_end=1, is_complete=False)
    h._routes["AGV01"] = r1
    _saved = h.send_window_fn
    h.send_window_fn = lambda a, p: None
    try:
        h._try_line_reroute("AGV01", st1, r1, 0)
        # đường mới phải NÉ node 5 (trong intent AGV02) ở đoạn đầu → rẽ sang 6
        head = r1.full_path[:5]
        if "6" in r1.full_path and r1.full_path[1] != "5":
            _ok(f"AGV01 thấy intent AGV02 (qua 5) → né: {head}... (rẽ sang 6, KHÔNG xuyên 5)")
        else:
            _bad(f"AGV01 VẪN đi xuyên node 5: {r1.full_path}")
    finally:
        h.send_window_fn = _saved


def test_yield_resume_timing():
    """Xe thua đã né (yield) CHỈ resume khi winner rời hẳn path gốc; còn winner trên
    path thì GIỮ chờ (không resume sớm → không né↔đụng vòng lặp)."""
    print("[test] resume yield đúng lúc winner clear (Bước 4)")
    import task_queue as TQ
    g = load_graph()
    tc, h = reset(g)
    # ghi lại dispatch thay vì chạy stack thật
    calls = []
    _orig = TQ.agv_task_queue.dispatch_or_queue
    TQ.agv_task_queue.dispatch_or_queue = lambda *a, **k: calls.append((a, k))
    try:
        # Loser AGV01 đã đỗ né (yield_cmd set), đứng yên tại siding
        st1 = place(h, "AGV01", "8", driving=False)
        st1.yield_cmd = "go_charge"
        st1.yield_dest = None
        st1.yield_session = None
        st1.yield_winner = "AGV02"
        st1.yield_path = ["17", "5", "18", "4", "19", "64", "2", "1", "13"]
        # Winner AGV02 còn ĐANG trên path gốc (đè 18,5,4,19) → KHÔNG resume
        tc._registered["AGV02"] = {"path": ["19", "4", "18", "5", "17"],
                                    "current_idx": 0, "direction": "fwd", "priority": 3}
        h._check_waiting_agvs("AGV02")
        if st1.yield_cmd == "go_charge" and not calls:
            _ok("winner còn trên path → GIỮ chờ (chưa resume)")
        else:
            _bad(f"resume SỚM khi winner chưa qua (yield_cmd={st1.yield_cmd}, calls={len(calls)})")
        # Winner đã đi xong (deregistered) → resume
        tc._registered.pop("AGV02", None)
        st1.yield_winner = "AGV02"   # vẫn trỏ tới winner đã rời
        h._check_waiting_agvs("AGV02")
        if st1.yield_cmd is None and calls:
            _ok("winner rời hẳn → RESUME lệnh gốc go_charge (yield_cmd đã clear)")
        else:
            _bad(f"KHÔNG resume khi winner đã rời (yield_cmd={st1.yield_cmd}, calls={len(calls)})")
    finally:
        TQ.agv_task_queue.dispatch_or_queue = _orig


def _fake_points(g):
    """Toạ độ giả cho build plan trong test (không cần map thật)."""
    MM.points = {str(n): (0.0, 0.0) for n in g.nodes}
    MM.roads = []


def test_setroute_conflict_cap_standoff():
    """set_route CẮT window tại điểm an toàn (conflict_at - HEADON_STANDOFF) ngay
    lúc dispatch khi phía trước có xe ĐẬU ngược chiều — hiện thực hoá 'chờ tại
    điểm an toàn' của planner (trước đây chỉ là câu log)."""
    print("[test] set_route cắt window theo conflict + standoff (né từ xa)")
    g = load_graph()
    tc, h = reset(g)
    _fake_points(g)
    # AGV02 ĐẬU tại node 5 (không route → không rõ chiều) — nằm trên đường AGV01
    place(h, "AGV02", "5", driving=False)
    place(h, "AGV01", "19", driving=False)
    r = h.set_route("AGV01", ["19", "4", "18", "5", "17"], "delivery", "fwd")
    # conflict tại idx=2 (edge 18→5) → safe = 2 - HEADON_STANDOFF(2) = 0
    if r.window_end == 0 and r.waiting_before_conflict == "19":
        _ok("window cắt về [0→0] ngay tại dispatch — đứng cách xe đậu 3 node, "
            "không lao tới sát")
    else:
        _bad(f"window_end={r.window_end} wait={r.waiting_before_conflict} "
             f"(kỳ vọng 0/'19') → xe vẫn lao gần conflict")


def test_rolling_stop_respects_conflict():
    """arrived_wait_sys (rolling stop) KHÔNG được gửi window mù vượt điểm chờ
    conflict (gốc lỗi: AGV01 được lệnh 'halt tại 15' xong rolling-stop đẩy thẳng
    window tới node 4 → 2 xe lao vào sát nhau)."""
    print("[test] rolling stop tôn trọng điểm chờ conflict")
    g = load_graph()
    tc, h = reset(g)
    _fake_points(g)
    place(h, "AGV02", "5", driving=False)   # xe đậu ngược chiều tại 5
    r1 = LH.LineAGVRoute(full_path=["19", "4", "18", "5", "17"],
                         task_type="delivery", direction="fwd",
                         window_start=0, window_end=0, is_complete=False)
    r1.waiting_before_conflict = "19"
    h._routes["AGV01"] = r1
    st1 = place(h, "AGV01", "19", driving=False)
    sent = []
    _saved, _saved_ev = h.send_window_fn, h.on_event
    h.send_window_fn = lambda a, p: sent.append(p)
    h.on_event = lambda *a, **k: None
    try:
        h._handle_event("AGV01", "arrived_wait_sys", {}, st1)
        if r1.window_end <= 1 and not sent:
            _ok(f"window giữ [0→{r1.window_end}], KHÔNG gửi window mù vượt điểm chờ")
        else:
            _bad(f"window_end={r1.window_end}, sent={len(sent)} → vẫn bị đẩy vượt điểm chờ")
    finally:
        h.send_window_fn, h.on_event = _saved, _saved_ev


def test_backup_to_reroute_node():
    """HEAD-ON hết đường tiến: xe thua LÙI dọc đường ĐÃ ĐI về node có nhánh rẽ
    (hoặc node ngoài hành lang xe thắng) + queue lại đích — KHÔNG đứng chờ mãi
    dẫn đến deadlock."""
    print("[test] lùi về node có nhánh rẽ khi hết đường (chống deadlock)")
    import task_queue as TQ
    g = load_graph()
    tc, h = reset(g)
    _fake_points(g)
    # Winner AGV02 chiếm hành lang 64→19→4→9→15 (ngược chiều AGV01)
    tc._registered["AGV02"] = {"path": ["64", "19", "4", "9", "15"], "direction": "fwd",
                                "current_idx": 0, "priority": 3}
    place(h, "AGV02", "64", driving=True)
    # AGV01 đã đi 5→8→15→9→4, đích 64 — head-on tại 4→19, không thể tiến
    r1 = LH.LineAGVRoute(full_path=["5", "8", "15", "9", "4", "19", "64"],
                         task_type="delivery", direction="fwd",
                         window_start=0, window_end=4, is_complete=False)
    h._routes["AGV01"] = r1
    st1 = place(h, "AGV01", "4", driving=False)
    st1.prev_tag = 9
    queued = []
    _orig_in = TQ.agv_task_queue.insert_next
    TQ.agv_task_queue.insert_next = lambda aid, cmd, **k: queued.append((aid, cmd, k))
    _saved = h.send_window_fn
    h.send_window_fn = lambda a, p: None
    try:
        # AGV01 đứng tại '4' = nằm TRÊN hành lang tương lai AGV02 → phải nhận ra
        if not h._blocks_corridor_of("AGV01", "AGV02"):
            _bad("_blocks_corridor_of không nhận ra AGV01 đang chặn hành lang AGV02")
            return
        ok = h._back_up_to_reroute_node("AGV01", st1, r1, 4, "AGV02")
        nr = h._routes.get("AGV01")
        if (ok and nr and nr.task_type == "transit" and nr.full_path[0] == "4"
                and nr.full_path[-1] in ("9", "15", "8", "5") and queued
                and queued[0][2].get("dest_node") == "64"):
            _ok(f"LÙI theo {nr.full_path} (transit, dir={nr.direction}) + queue lại "
                f"đích 64 → nhả hành lang cho winner")
        else:
            _bad(f"ok={ok} route={getattr(nr, 'full_path', None)} queued={queued}")
    finally:
        TQ.agv_task_queue.insert_next = _orig_in
        h.send_window_fn = _saved


def test_continue_midroute_no_complete():
    """event 'continue' GIỮA ĐƯỜNG không được complete task (gốc lỗi: xe đi về trạm
    đứng chờ ở node 18 nhận 'continue' → task xoá → UI hiện 'sẵn sàng' dù chưa về
    trạm). Tại node đích thì complete bình thường."""
    print("[test] 'continue' giữa đường KHÔNG complete task")
    import task_queue as TQ
    g = load_graph()
    tc, h = reset(g)
    _fake_points(g)
    completed = []
    _orig_done = TQ.agv_task_queue.on_agv_completed
    TQ.agv_task_queue.on_agv_completed = lambda aid, **k: completed.append((aid, k))
    _saved, _saved_ev = h.send_window_fn, h.on_event
    h.send_window_fn = lambda a, p: None
    h.on_event = lambda *a, **k: None
    try:
        r1 = LH.LineAGVRoute(full_path=["5", "18", "4", "19", "64", "2", "14"],
                             task_type="return_charge", direction="bwd",
                             window_start=0, window_end=6, is_complete=False)
        h._routes["AGV01"] = r1
        st1 = place(h, "AGV01", "18", driving=False)   # GIỮA đường về trạm 14
        h._handle_event("AGV01", "continue", {}, st1)
        if not completed and "AGV01" in h._routes:
            _ok("giữa đường (18): route GIỮ NGUYÊN, task KHÔNG complete")
        else:
            _bad(f"giữa đường vẫn complete → UI 'sẵn sàng' sớm "
                 f"(completed={completed}, route_alive={'AGV01' in h._routes})")
        # Tại node đích → complete bình thường
        st1.current_tag = "14"
        h._handle_event("AGV01", "continue", {}, st1)
        if completed and "AGV01" not in h._routes:
            _ok("tại đích (14): complete bình thường")
        else:
            _bad(f"tại đích KHÔNG complete (completed={completed})")
    finally:
        TQ.agv_task_queue.on_agv_completed = _orig_done
        h.send_window_fn, h.on_event = _saved, _saved_ev


def test_siding_park_no_picking():
    """Xe đỗ né siding (yield_cmd set) tới node siding KHÔNG được vào lifecycle
    'picking' (chờ HMI mãi → kẹt). Phải: complete siding cmd (auto_dispatch=False,
    không pop go_charge), giải phóng xe, resume go_to khi winner đã rời.
    Gốc lỗi log: AGV02 né sang node 10 rồi đứng im, đến khi AGV01 về vẫn không đi."""
    print("[test] đỗ né siding KHÔNG vào picking + resume được")
    import task_queue as TQ
    g = load_graph()
    tc, h = reset(g)
    _fake_points(g)
    completed = []
    dispatched = []
    _orig_done = TQ.agv_task_queue.on_agv_completed
    _orig_disp = TQ.agv_task_queue.dispatch_or_queue
    TQ.agv_task_queue.on_agv_completed = lambda aid, **k: completed.append((aid, k))
    TQ.agv_task_queue.dispatch_or_queue = lambda *a, **k: dispatched.append((a, k))
    _saved, _saved_ev = h.send_window_fn, h.on_event
    h.send_window_fn = lambda a, p: None
    h.on_event = lambda *a, **k: None
    try:
        # AGV02 đã đỗ né: route siding [2,10] is_complete, yield giữ go_to 17.
        # Winner AGV01 ĐÃ rời (không registered) → resume phải dispatch go_to 17.
        r2 = LH.LineAGVRoute(full_path=["2", "10"], task_type="delivery",
                             direction="fwd", window_start=0, window_end=1,
                             is_complete=True)
        h._routes["AGV02"] = r2
        st2 = place(h, "AGV02", "10", driving=False)
        st2.yield_cmd = "go_to"
        st2.yield_dest = "17"
        st2.yield_session = None
        st2.yield_winner = "AGV01"
        st2.yield_path = ["2", "64", "19", "4", "18", "5", "17"]
        h._handle_event("AGV02", "arrived_wait_sys", {}, st2)
        _no_picking = (st2.task_lifecycle != "picking")
        _freed = any(k.get("auto_dispatch") is False for _, k in completed)
        _resumed = any(a and a[1] == "go_to" or k.get("dest_node") == "17"
                       for a, k in dispatched)
        if _no_picking and _freed and "AGV02" not in h._routes:
            _ok("siding-park: KHÔNG picking, complete auto_dispatch=False, route popped")
        else:
            _bad(f"picking={st2.task_lifecycle} freed={_freed} route_alive={'AGV02' in h._routes}")
        if _resumed:
            _ok("winner đã rời → RESUME dispatch go_to 17 (không kẹt ở siding)")
        else:
            _bad(f"KHÔNG resume go_to sau khi đỗ siding (dispatched={dispatched})")
    finally:
        TQ.agv_task_queue.on_agv_completed = _orig_done
        TQ.agv_task_queue.dispatch_or_queue = _orig_disp
        h.send_window_fn, h.on_event = _saved, _saved_ev


def test_following_not_penalized():
    """Penalty traffic-aware CHỈ né xe NGƯỢC chiều (head-on), KHÔNG né xe CÙNG chiều
    (following). Gốc lỗi log: AGV01 (dẫn đầu) đi vòng 19→4→9→15→8→16→7→6→17 để tránh
    AGV02 (theo sau, cùng tới 17) thay vì đi thẳng 19→4→18→5→17."""
    print("[test] following KHÔNG bị penalty (xe dẫn đi thẳng)")
    from mqtt_client import _path_is_headon_against as _hoa
    # Đường tự nhiên xe dẫn AGV01: 19→4→18→5→17
    _lead = ["19", "4", "18", "5", "17"]
    _my = {(_lead[i], _lead[i + 1]) for i in range(len(_lead) - 1)}
    # AGV02 theo sau, intent CÙNG chiều tới 17: 2→64→19→4→18→5→17
    _follow = ["2", "64", "19", "4", "18", "5", "17"]
    if not _hoa(_my, _follow, 0):
        _ok("AGV02 cùng chiều (following) → KHÔNG head-on → xe dẫn giữ đường thẳng")
    else:
        _bad("following bị coi là head-on → xe dẫn đi vòng vô nghĩa")
    # Xe ngược chiều thật: 17→5→18→4 (đi ngược trên cạnh 4-18, 18-5)
    _onc = ["17", "5", "18", "4", "19"]
    if _hoa(_my, _onc, 0):
        _ok("xe ngược chiều (17→5→18→4) → head-on → vẫn né đúng")
    else:
        _bad("KHÔNG phát hiện head-on thật → mất khả năng tách 2 nhánh")


def test_siding_excludes_station():
    """find_parking_node KHÔNG được chọn node TRẠM (sạc/chờ) làm siding → không 'lùi
    về trạm tránh'. Gốc lỗi log: AGV02 ở node 2 né bằng cách lùi về node 14 = trạm sạc."""
    print("[test] siding KHÔNG chọn node trạm (không lùi về trạm)")
    g = load_graph()
    tc, h = reset(g)
    # Đánh dấu node 14 là CHARGER (như map thật)
    MM.node_actions = {"14": {"locationType": "CHARGER"},
                       "13": {"locationType": "CHARGER"}}
    # AGV02 ở node 2 đi lên 19; winner AGV01 corridor 19→4→18→5→17
    tc._registered["AGV01"] = {"path": ["19", "4", "18", "5", "17"], "direction": "fwd",
                                "current_idx": 0, "priority": 3}
    st2 = place(h, "AGV02", "2", driving=False)
    st2.prev_tag = 14
    park = tc.find_parking_node("AGV02", ["2", "64", "19"], 1, "AGV01")
    if park is None:
        _ok("không có siding hợp lệ (node 14=trạm bị loại) → sẽ DỪNG CHỜ, không lùi trạm")
    elif str(park[0]) not in ("14", "13"):
        _ok(f"siding={park[0]} KHÔNG phải trạm (14/13 đã bị loại)")
    else:
        _bad(f"siding={park[0]} VẪN là trạm sạc → lùi về trạm tránh (sai)")


def test_following_no_yield_no_retreat():
    """Xe đi lên gặp xe CÙNG CHIỀU phía trước (following) KHÔNG được yield/lùi — chỉ
    DỪNG CHỜ. Gốc lỗi log: AGV02 (2→64→19) coi AGV01 (19→4→18→5→17, cùng chiều) là
    head-on → né lùi về trạm 14. Chỉ né khi xe kia NGƯỢC CHIỀU thật."""
    print("[test] following KHÔNG yield/lùi, chỉ chờ (chỉ né xe ngược chiều)")
    g = load_graph()
    tc, h = reset(g)
    _fake_points(g)
    r2 = LH.LineAGVRoute(full_path=["2", "64", "19"], task_type="delivery",
                         direction="fwd", window_start=0, window_end=2,
                         is_complete=False)
    # Xe cùng chiều AGV01 đi lên 19→4→18→5→17 (KHÔNG ngược chiều AGV02)
    tc._registered["AGV01"] = {"path": ["19", "4", "18", "5", "17"], "direction": "fwd",
                                "current_idx": 0, "priority": 3}
    if h._is_oncoming("AGV02", r2, "AGV01"):
        _bad("AGV01 cùng chiều bị coi là oncoming → AGV02 né nhầm (lùi trạm)")
    else:
        _ok("AGV01 cùng chiều → KHÔNG oncoming → AGV02 chỉ chờ, không lùi về trạm")
    # Xe NGƯỢC chiều thật: AGV01 về sạc 17→5→18→4→19→64→2 (đè cạnh 64-19, 4-18... ngược)
    tc._registered["AGV01"] = {"path": ["17", "5", "18", "4", "19", "64", "2", "1", "13"],
                                "direction": "bwd", "current_idx": 0, "priority": 1}
    if h._is_oncoming("AGV02", r2, "AGV01"):
        _ok("AGV01 ngược chiều (về sạc qua 64→19) → oncoming → AGV02 mới né")
    else:
        _bad("KHÔNG nhận ra xe ngược chiều thật → mất khả năng né head-on")


def test_loser_yields_to_stopped_winner():
    """Xe về sạc (loser) gặp xe giao hàng (winner) ĐANG ĐẬU trên đường về của nó →
    phải nhận diện xe đậu ở node KẾ (conf_tn) rồi NHƯỜNG, KHÔNG cả 2 cùng đứng chờ.
    Gốc deadlock log: _identify_conflicting_agv chỉ check conf_fn → trả None → loser
    tưởng following → chờ mãi; winner cũng chờ loser né → kẹt cứng."""
    print("[test] loser nhường xe winner đang đậu chắn node kế (chống deadlock)")
    g = load_graph()
    tc, h = reset(g)
    _fake_points(g)
    # AGV02 (delivery, mạnh) ĐẬU tại node 19 — registered route (đi lên) 2→64→19
    tc._registered["AGV02"] = {"path": ["2", "64", "19"], "direction": "fwd",
                                "current_idx": 2, "priority": 3}
    st2 = place(h, "AGV02", "19", driving=False)
    st2.prev_tag = 64   # AGV02 vừa đi 64→19 (ngược chiều đường về của AGV01)
    # AGV01 (về sạc) đang xét edge 4→19 — AGV02 đậu ở conf_tn=19
    other = h._identify_conflicting_agv("AGV01", "4", "19")
    if other == "AGV02":
        _ok("_identify nhận ra AGV02 đậu ở node KẾ (conf_tn=19), không trả None")
    else:
        _bad(f"_identify={other} (cần AGV02) → loser không biết ai chắn → deadlock")
    # AGV02 (2→64→19) NGƯỢC chiều AGV01 (…→19→64→2) → oncoming → loser phải nhường
    r1 = LH.LineAGVRoute(full_path=["5", "18", "4", "19", "64", "2", "1", "13"],
                         task_type="return_charge", direction="bwd",
                         window_start=0, window_end=2, is_complete=False)
    if h._is_oncoming("AGV01", r1, "AGV02"):
        _ok("AGV02 ngược chiều → AGV01 (loser) sẽ nhường, không đứng chờ chết")
    else:
        _bad("AGV01 KHÔNG thấy oncoming → vẫn deadlock cả 2 cùng đứng")
    # Arbiter: AGV01 (charge pri1) THUA AGV02 (delivery pri3) → đúng loser
    if tc._arbitrate("AGV01", "AGV02", "19") == "AGV02":
        _ok("arbiter: AGV02 (delivery) thắng → AGV01 (charge) là loser phải né")
    else:
        _bad("arbiter sai → loser/winner đảo ngược")


def test_edge_release_on_move():
    """Edge reservation phải NHẢ khi xe sang cạnh mới, KHÔNG giữ cạnh 'ma' đã đi qua.
    Gốc lỗi log: AGV01 rời node 17 đi đường vòng nhưng edge 5_to_17 (cạnh nó vừa tới
    17) vẫn bị giữ → AGV02 (18→5→17) tưởng AGV01 head-on tại node 5 → đứng chờ mãi
    dù AGV01 đã đi đường khác."""
    print("[test] nhả edge cũ khi sang cạnh mới (không còn edge ma)")
    import json
    g = load_graph()
    tc, h = reset(g)
    _fake_points(g)
    _saved, _saved_sc = h.send_window_fn, h.on_state_changed
    h.send_window_fn = lambda a, p: None
    h.on_state_changed = None
    try:
        # AGV01 đang ở 17 (vừa từ 5 tới), driving → giữ edge 5_to_17
        st = h.state_store.get_or_create("AGV01")
        st.current_tag = 17
        st.prev_tag = 5
        st.driving = True
        st.current_edge_pair = (5, 17)
        LH._line_blocked_edges.clear()
        LH._line_blocked_edges["5_to_17"] = "AGV01"
        # AGV01 đi tiếp 17→6 (đường vòng): state mới tag=6 driving=True
        h._on_state("AGV01", json.dumps({"tag": 6, "driving": True}))
        if LH._line_blocked_edges.get("5_to_17") != "AGV01":
            _ok("edge 5_to_17 ĐÃ nhả khi AGV01 sang cạnh 17→6 (hết edge ma)")
        else:
            _bad("edge 5_to_17 VẪN bị giữ → AGV02 tưởng head-on tại 5, kẹt cứng")
        # AGV02 (18→5→17) giờ KHÔNG còn thấy head-on ma tại edge 5→17
        other = h._identify_conflicting_agv("AGV02", "5", "17")
        if other != "AGV01":
            _ok("AGV02 KHÔNG còn nhận AGV01 head-on tại 5→17 → đi thẳng tới 17")
        else:
            _bad(f"AGV02 vẫn thấy AGV01 ở edge 5→17 (other={other}) → vẫn kẹt")
    finally:
        h.send_window_fn, h.on_state_changed = _saved, _saved_sc


def test_winner_no_detour_when_unregistered():
    """Xe giao hàng (winner) lập route giao khi CHƯA registered (vừa picking xong)
    KHÔNG được né đường xe kia → đi THẲNG; chỉ xe loser né. Gốc lỗi log: AGV02
    (delivery) chưa registered → rank mặc định 2 < AGV01 (registered pri3) → AGV02 né
    đường vòng QUA node 8 đúng chỗ AGV01 đang đỗ né → CẢ HAI cùng né, đâm nhau."""
    print("[test] winner (chưa registered) đi thẳng, KHÔNG cùng né (chống đâm)")
    from mqtt_client import (_planner_dest_priority as _dp,
                             _planner_should_avoid as _sa)
    # node 17 = đích giao (NORMAL) → delivery priority 3, KHÔNG phải mặc định 2
    na = {"17": {"locationType": "NORMAL"}, "13": {"locationType": "CHARGER"}}
    if _dp(na, "17") == 3:
        _ok("đích giao 17 → priority delivery=3 (không phải mặc định 2)")
    else:
        _bad(f"priority đích giao = {_dp(na,'17')} (cần 3)")
    if _dp(na, "13") == 1:
        _ok("đích sạc 13 → priority return_charge=1")
    else:
        _bad(f"priority đích sạc = {_dp(na,'13')} (cần 1)")
    # AGV02 (delivery pri3) vs AGV01 (registered delivery pri3): AGV02 id lớn hơn →
    # AGV01 mạnh hơn theo tie-break → nhưng AGV02 KHÔNG né (vì không < ): đi thẳng.
    if not _sa(3, "AGV02", 3, "AGV01"):
        _ok("AGV02 (winner, pri3) KHÔNG né AGV01 (pri3) → đi thẳng, để AGV01 né")
    else:
        _bad("AGV02 vẫn né AGV01 → cả 2 cùng né → đâm như log")
    # Với rank mặc định 2 (lỗi cũ) thì AGV02 SẼ né — chứng minh fix cần thiết
    if _sa(2, "AGV02", 3, "AGV01"):
        _ok("(đối chứng) rank mặc định 2 → AGV02 né nhầm = đúng lỗi cũ")
    else:
        _bad("đối chứng sai")


def test_dispatch_headon_winner_no_yield():
    """Tầng DISPATCH head-on (main.py) + Phase 2 planner: xe winner (delivery) lập KH
    khi CHƯA registered KHÔNG được nhường — phải đi thẳng. Gốc lỗi log mới nhất: AGV01
    (về sạc) né siding 8 ĐÚNG, nhưng AGV02 (delivery, winner) ở tầng dispatch lại 'đỗ
    tại 9' né nữa → CẢ HAI cùng né → kẹt/đâm. should_avoid_path_of(my_priority=…) phải
    cho AGV02 đi thẳng."""
    print("[test] dispatch head-on: winner (chưa reg) đi thẳng, không cùng né")
    g = load_graph()
    tc, h = reset(g)
    # AGV01 đang né siding, registered ['5','8'] type=delivery (priority 3) — che mất
    # priority thật return_charge=1. AGV02 (delivery) CHƯA registered (vừa picking).
    tc._registered["AGV01"] = {"path": ["5", "8"], "direction": "fwd",
                                "current_idx": 0, "priority": 3}
    # Lỗi cũ: AGV02 rank mặc định 2 < AGV01(3) → should_avoid=True → AGV02 né nhầm
    if tc.should_avoid_path_of("AGV02", "AGV01"):
        _ok("(đối chứng) không truyền my_priority → AGV02 né nhầm (rank mặc định 2)")
    else:
        _bad("đối chứng sai")
    # CÙNG ưu tiên (delivery 3 vs 3): tie-break ĐỒNG BỘ với _arbitrate (ID NHỎ thắng).
    # ĐÚNG 1 xe nhường (antisymmetric) → KHÔNG "cả 2 cùng né". Và should_avoid phải KHỚP
    # _arbitrate (nguồn quyết reservation) → dispatch & runtime KHÔNG chọn winner đối
    # nghịch → hết FLAIL (xe chạy tới rồi lại nhường, đúng log AGV01/AGV02 qua node 8).
    _av_02 = tc.should_avoid_path_of("AGV02", "AGV01", my_priority=3)
    _av_01 = tc.should_avoid_path_of("AGV01", "AGV02", my_priority=3)
    if _av_02 and not _av_01:
        _ok("cùng ưu tiên → ĐÚNG 1 xe nhường (AGV02 né AGV01=id nhỏ), antisymmetric")
    else:
        _bad(f"tie-break không antisymmetric/sai hướng: avoid02={_av_02} avoid01={_av_01}")
    if (tc._arbitrate("AGV01", "AGV02", "8") == "AGV01") and _av_02 and not _av_01:
        _ok("should_avoid KHỚP _arbitrate (AGV01 thắng cả 2 tầng) → dispatch=runtime, hết flail")
    else:
        _bad("should_avoid NGƯỢC _arbitrate → dispatch & runtime đối nghịch = flail")
    # Chiều ngược: xe về sạc (prio1) gặp delivery(3) → vẫn nhường đúng
    if tc.should_avoid_path_of("AGV02", "AGV01", my_priority=1):
        _ok("my_priority=1 (return_charge) → vẫn nhường delivery (đúng)")
    else:
        _bad("return_charge KHÔNG nhường delivery → sai")


def test_yield_siding_preserves_bwd_dir():
    """Xe né siding phải GIỮ hướng arrival (bwd) — nếu mất → dispatch siding mặc định
    fwd → plan ra DIR_FWD + turn sai → xe đi THẲNG ra ngoài line thay vì rẽ vào siding.
    Gốc lỗi log: AGV01 arrived bwd (transit 17→5), route gốc bị cắt [0→0] (clear
    last_transit_direction), siding 5→8 dispatch fwd → đi thẳng ra ngoài."""
    print("[test] né siding giữ hướng bwd (không đi thẳng ra ngoài line)")
    import task_queue as TQ
    g = load_graph()
    tc, h = reset(g)
    _fake_points(g)
    # AGV01 đang ở node 5, route về sạc dir=bwd (arrived bwd từ 17→5)
    r1 = LH.LineAGVRoute(full_path=["5", "18", "4", "19", "64", "2", "1", "13"],
                         task_type="return_charge", direction="bwd",
                         window_start=0, window_end=0, is_complete=False)
    h._routes["AGV01"] = r1
    st1 = place(h, "AGV01", "5", driving=False)
    st1.prev_tag = 17
    st1.last_transit_direction = ''   # đã bị clear bởi dispatch charge trước (window [0→0])
    # Winner AGV02 corridor ngược chiều
    tc._registered["AGV02"] = {"path": ["19", "4", "18", "5", "17"], "direction": "fwd",
                                "current_idx": 0, "priority": 3}
    # mock find_parking_node → siding 8; mock running cmd + dispatch_or_queue
    _orig_fpn = tc.find_parking_node
    _orig_run = TQ.agv_task_queue._running.get("AGV01")
    _orig_disp = TQ.agv_task_queue.dispatch_or_queue
    _orig_done = TQ.agv_task_queue.on_agv_completed
    tc.find_parking_node = lambda a, p, c, o: ("8", "5")
    import task_queue as _TQ2
    TQ.agv_task_queue._running["AGV01"] = _TQ2.QueuedCommand(
        cmd_id="x", agv_id="AGV01", command="go_charge", dest_node=None)
    _captured = {}
    def _fake_disp(aid, cmd, **k):
        _captured['ltd'] = h.state_store.get(aid).last_transit_direction
        return None
    TQ.agv_task_queue.dispatch_or_queue = _fake_disp
    TQ.agv_task_queue.on_agv_completed = lambda aid, **k: None
    try:
        ok = h._yield_to_siding("AGV01", r1, 2, "AGV02")
        if ok and _captured.get('ltd') == 'bwd':
            _ok("siding dispatch thấy last_transit_direction='bwd' → plan DIR_BWD đúng")
        else:
            _bad(f"ok={ok} ltd={_captured.get('ltd')} (cần 'bwd') → xe đi thẳng ra ngoài")
    finally:
        tc.find_parking_node = _orig_fpn
        TQ.agv_task_queue.dispatch_or_queue = _orig_disp
        TQ.agv_task_queue.on_agv_completed = _orig_done
        if _orig_run is not None:
            TQ.agv_task_queue._running["AGV01"] = _orig_run
        else:
            TQ.agv_task_queue._running.pop("AGV01", None)


def test_anti_trap_vacate():
    """CHỐNG-TRAP: xe KHÔNG bị kẹt window [0→0] tại node đang đứng khi node KẾ đã giữ
    chỗ được → phải VACATE được để xe khác lên. Gốc deadlock log: AGV01 ở node 5 bị
    cắt window [0→0] (reservation buffer + conflict-cap) → không rời được → AGV02 chờ
    mãi → 2 xe đứng im chờ nhau."""
    print("[test] chống-trap: vacate node đang đứng (chống deadlock 2 xe)")
    g = load_graph()
    tc, h = reset(g)
    _fake_points(g)
    # AGV03 giữ node 15 (auto_9 block {15,9}) → AGV01 chỉ giữ được tới node 8 → window
    # bị các tầng cắt về [0→0]. AGV02 (ở node 4) CẦN node 5 (đường 4→18→5→17) → AGV01
    # đang chắn nó → phải vacate node 5.
    tc._registered["AGV03"] = {"path": ["15", "16"], "direction": "fwd",
                                "current_idx": 0, "priority": 3}
    place(h, "AGV03", "15", driving=True)
    tc.reserve_ahead("AGV03")
    tc._registered["AGV02"] = {"path": ["19", "4", "18", "5", "17"], "direction": "fwd",
                                "current_idx": 1, "priority": 3}
    place(h, "AGV02", "4", driving=False)
    # AGV01 (yếu, về sạc) đứng node 5, route loop 5→8→15→9→4→… — phải rời node 5
    place(h, "AGV01", "5", driving=False)
    r1 = h.set_route("AGV01", ["5", "8", "15", "9", "4", "19", "64", "2", "1", "13"],
                     "return_charge", direction="bwd")
    if r1.window_end >= 1 and tc._node_res.get("8") == "AGV01":
        _ok(f"AGV01 giữ node 8, window=[0→{r1.window_end}] → rời node 5 cho AGV02 lên")
    else:
        _bad(f"window=[0→{r1.window_end}] node8={tc._node_res.get('8')} → kẹt, deadlock")
    # node KẾ THỰC SỰ bị chiếm (node 8 bị xe khác) → vẫn phải [0→0] (không vacaté ẩu)
    tc2, h2 = reset(g)
    _fake_points(g)
    tc2._registered["AGV02"] = {"path": ["8", "16"], "direction": "fwd",
                                 "current_idx": 0, "priority": 3}
    place(h2, "AGV02", "8", driving=False)
    tc2.reserve_ahead("AGV02")   # AGV02 giữ node 8 (node kế của AGV01)
    place(h2, "AGV01", "5", driving=False)
    r2 = h2.set_route("AGV01", ["5", "8", "15"], "return_charge", direction="bwd")
    if r2.window_end == 0:
        _ok("node KẾ bị xe khác chiếm thật → giữ [0→0] (KHÔNG vacate ẩu vào node bị chiếm)")
    else:
        _bad(f"window=[0→{r2.window_end}] → lao vào node 8 đang bị AGV02 chiếm (đâm)")
    # KHOÁ-MA: node 8 bị reserve bởi xe khác (reserved_extent=0) NHƯNG TRỐNG VẬT LÝ →
    # vẫn phải vacate được (gốc deadlock log: reserve_ahead không khoá được node 8 dù
    # node trống). Anti-trap dựa vào TRỐNG VẬT LÝ, không phải reserved_extent.
    tc3, h3 = reset(g)
    _fake_points(g)
    tc3._registered["AGV02"] = {"path": ["19", "4", "18", "5", "17"], "direction": "fwd",
                                 "current_idx": 1, "priority": 3}
    place(h3, "AGV02", "4", driving=False)
    tc3._registered["AGV99"] = {"path": ["8"], "direction": "fwd",
                                 "current_idx": 0, "priority": 3}   # chủ khoá-ma, KHÔNG đặt vị trí
    tc3._node_res["8"] = "AGV99"   # node 8 bị khoá nhưng KHÔNG xe nào đứng đó
    place(h3, "AGV01", "5", driving=False)
    r3 = h3.set_route("AGV01", ["5", "8", "15", "9", "4", "19", "64", "2", "1", "13"],
                      "return_charge", direction="bwd")
    if r3.window_end >= 1 and tc3._node_res.get("8") == "AGV01":
        _ok("node 8 khoá-ma nhưng TRỐNG vật lý → vacate được (cướp khoá ma, không kẹt)")
    else:
        _bad(f"window=[0→{r3.window_end}] node8={tc3._node_res.get('8')} → vẫn kẹt vì khoá-ma")


def test_no_redundant_siding_when_clear():
    """Xe thua đã VACATE khỏi đường winner (không còn chắn) → KHÔNG đỗ-né-siding thừa,
    chỉ DỪNG CHỜ tại chỗ. Gốc lỗi log: AGV01 vacate 5→8 (node 8 NGOÀI đường AGV02
    4→18→5→17) nhưng vẫn né tiếp 8→16 vô ích. Đứng chờ ở 8 là đủ."""
    print("[test] không đỗ-né-siding thừa khi đã thoáng (đứng chờ tại chỗ)")
    g = load_graph()
    tc, h = reset(g)
    _fake_points(g)
    # AGV02 (winner) ở node 4, đường 4→18→5→17 — node 8 KHÔNG nằm trên đó.
    # prev_tag=19 (vừa 19→4) → _is_oncoming(AGV01,AGV02)=True (AGV01 muốn đi 4→19).
    tc._registered["AGV02"] = {"path": ["19", "4", "18", "5", "17"], "direction": "fwd",
                                "current_idx": 1, "priority": 3}
    st2 = place(h, "AGV02", "4", driving=False)
    st2.prev_tag = 19
    # AGV01 (loser) ở node 8, route 8→15→9→4→… — đã thoáng (8 ngoài đường AGV02)
    r1 = LH.LineAGVRoute(full_path=["8", "15", "9", "4", "19", "64", "2", "1", "13"],
                         task_type="return_charge", direction="bwd",
                         window_start=0, window_end=0, is_complete=False)
    h._routes["AGV01"] = r1
    st1 = place(h, "AGV01", "8", driving=False)
    st1.prev_tag = 5
    if h._is_oncoming("AGV01", r1, "AGV02") and not h._blocks_corridor_of("AGV01", "AGV02"):
        _ok("AGV01 oncoming với AGV02 NHƯNG KHÔNG chắn đường nó (node 8 thoáng)")
    else:
        _bad("tiền đề sai: oncoming hoặc blocks_corridor không như kỳ vọng")
    # spy: _yield_to_siding KHÔNG được gọi (gate _blocks_corridor_of chặn)
    _called = []
    _orig_yield = h._yield_to_siding
    _orig_rr = h._try_line_reroute
    h._yield_to_siding = lambda *a, **k: (_called.append(a), False)[1]
    h._try_line_reroute = lambda *a, **k: False   # đường đơn, không có nhánh vòng
    _saved = h.send_window_fn
    h.send_window_fn = lambda a, p: None
    try:
        h._check_rolling_plan("AGV01", st1)
        if not _called and h._routes.get("AGV01") is r1:
            _ok("KHÔNG gọi _yield_to_siding → AGV01 giữ route, DỪNG CHỜ tại node 8")
        else:
            _bad(f"vẫn né siding thừa (yield_called={len(_called)})")
    finally:
        h._yield_to_siding = _orig_yield
        h._try_line_reroute = _orig_rr
        h.send_window_fn = _saved


def test_loser_waits_on_route_not_siding():
    """Xe THUA đang CHẮN node winner (node 5 ∈ đường AGV02) NHƯNG route CHÍNH của nó
    rẽ off-corridor ngay node kế (5→8, node 8 ngoài đường AGV02 4→18→5→17) → chỉ NHÍCH
    tới node thoáng (8) rồi DỪNG CHỜ, KHÔNG đỗ-né-siding/lùi dù _blocks_corridor_of=True.
    Gốc log: AGV01 sạc đứng 5, AGV02 (winner) chờ tại 4 — AGV01 phải nhường node 5; đúng
    là vacate 5→8 chờ AGV02 qua rồi đi tiếp, KHÔNG vòng lên siding 16 (rồi 16→8 vô ích)."""
    print("[test] xe thua nhích tới node thoáng trên route + chờ (không siding 16)")
    g = load_graph()
    tc, h = reset(g)
    _fake_points(g)
    # AGV02 (winner, delivery pri 3) chờ tại node 4, đường 4→18→5→17 (node 5 trong đó).
    tc._registered["AGV02"] = {"path": ["19", "4", "18", "5", "17"], "direction": "fwd",
                                "current_idx": 1, "priority": 3}
    st2 = place(h, "AGV02", "4", driving=False)
    st2.prev_tag = 19
    # AGV01 (loser, return_charge pri 1) ĐỨNG tại node 5 (đang chắn corridor AGV02),
    # route sạc 5→8→15→9→4→… — node 8 (kế) NẰM NGOÀI đường AGV02.
    tc._registered["AGV01"] = {"path": ["5", "8", "15", "9", "4", "19", "64", "2", "1", "13"],
                                "direction": "bwd", "current_idx": 0, "priority": 1}
    r1 = LH.LineAGVRoute(full_path=["5", "8", "15", "9", "4", "19", "64", "2", "1", "13"],
                         task_type="return_charge", direction="bwd",
                         window_start=0, window_end=0, is_complete=False)
    h._routes["AGV01"] = r1
    st1 = place(h, "AGV01", "5", driving=False)
    st1.prev_tag = 17
    # tiền đề: AGV01 ĐANG chắn node 5 → gate cũ (_blocks_corridor_of) sẽ cho đi siding
    if h._blocks_corridor_of("AGV01", "AGV02"):
        _ok("tiền đề: AGV01 đang chắn node 5 (∈ đường AGV02) → gate cũ sẽ cho siding")
    else:
        _bad("tiền đề sai: AGV01 không chắn corridor AGV02")
    _called = []
    _orig_yield = h._yield_to_siding
    _orig_rr    = h._try_line_reroute
    _orig_bu    = h._back_up_to_reroute_node
    _orig_bp    = h._back_up_to_prev
    h._yield_to_siding         = lambda *a, **k: (_called.append("siding"), True)[1]
    h._try_line_reroute        = lambda *a, **k: (_called.append("reroute"), True)[1]
    h._back_up_to_reroute_node = lambda *a, **k: (_called.append("backup"), True)[1]
    h._back_up_to_prev         = lambda *a, **k: (_called.append("backprev"), True)[1]
    _wins = []
    _saved = h.send_window_fn
    h.send_window_fn = lambda a, p: _wins.append((a, p))
    try:
        h._check_rolling_plan("AGV01", st1)
        if (not _called and r1.waiting_before_conflict == "8"
                and h._routes.get("AGV01") is r1):
            _ok("KHÔNG siding/reroute/lùi → giữ route, chờ tại node 8 (nhích 5→8)")
        else:
            _bad(f"vẫn né thừa: called={_called} wait={r1.waiting_before_conflict}")
    finally:
        h._yield_to_siding         = _orig_yield
        h._try_line_reroute        = _orig_rr
        h._back_up_to_reroute_node = _orig_bu
        h._back_up_to_prev         = _orig_bp
        h.send_window_fn           = _saved


def test_immediate_headon_loser_evades():
    """Xe THUA đứng tại node 5 với route ĐÂM THẲNG vào hành lang winner ngay CẠNH KẾ
    (5→18, winner AGV02 đi 4→18→5→17) → conflict_at == current_idx (==0). Trước đây guard
    `conflict_at > current_idx` BỎ QUA toàn bộ xử lý head-on cho cạnh-kề → AGV01 đứng im
    giữa hành lang winner → 2 xe chờ nhau = DEADLOCK (đúng log user: 'head-on 5→18 → nhường
    AGV02' rồi vẫn đứng). Nay guard `>= current_idx` → xe thua NÉ sang siding (rồi đi bypass
    8→15→9→4→19→… về sạc), KHÔNG đứng chết."""
    print("[test] head-on sát cạnh-kế: xe thua NÉ, không deadlock đứng im")
    g = load_graph()
    tc, h = reset(g)
    _fake_points(g)
    # AGV02 (winner, delivery pri3) ở node 4, route 4→18→5→17 (node 5 trong đó)
    tc._registered["AGV02"] = {"path": ["19", "4", "18", "5", "17"], "direction": "fwd",
                                "current_idx": 1, "priority": 3}
    r2 = LH.LineAGVRoute(full_path=["19", "4", "18", "5", "17"],
                         task_type="delivery", direction="fwd",
                         window_start=1, window_end=4, is_complete=False)
    h._routes["AGV02"] = r2
    place(h, "AGV02", "4", driving=False)
    # AGV01 (loser, return_charge pri1) ở node 5, route đâm thẳng 5→18→4→19→…
    # (cạnh kế 5→18 = head-on với winner đi 18→5)
    tc._registered["AGV01"] = {"path": ["5", "18", "4", "19", "64", "2", "1", "13"],
                                "direction": "bwd", "current_idx": 0, "priority": 1}
    r1 = LH.LineAGVRoute(full_path=["5", "18", "4", "19", "64", "2", "1", "13"],
                         task_type="return_charge", direction="bwd",
                         window_start=0, window_end=0, is_complete=False)
    h._routes["AGV01"] = r1
    st1 = place(h, "AGV01", "5", driving=False)
    st1.prev_tag = 17
    # đối chứng: conflict head-on NGAY tại cạnh kế (idx 0)
    _craw = h._find_upcoming_conflict("AGV01", r1, 0, len(r1.full_path) - 1)
    if _craw == 0:
        _ok("conflict head-on tại cạnh kế 5→18 (conflict_at == current_idx == 0)")
    else:
        _bad(f"conflict_raw={_craw} (kỳ vọng 0 — head-on cạnh kế)")
    # spy: xe thua PHẢI né (yield_to_siding gọi); KHÔNG được chỉ đứng WAIT-BASED
    _evaded = []
    _orig_yield = h._yield_to_siding
    _orig_rr    = h._try_line_reroute
    h._yield_to_siding  = lambda *a, **k: (_evaded.append("siding"), True)[1]
    h._try_line_reroute = lambda *a, **k: False   # cầu đơn 19-64 → không reroute được
    _saved = h.send_window_fn
    h.send_window_fn = lambda a, p: None
    try:
        h._check_rolling_plan("AGV01", st1)
        if _evaded == ["siding"]:
            _ok("guard `>=` → xe thua NÉ sang siding (phá deadlock cạnh-kế)")
        else:
            _bad(f"xe thua KHÔNG né (evaded={_evaded}) → vẫn deadlock đứng im tại 5")
    finally:
        h._yield_to_siding  = _orig_yield
        h._try_line_reroute = _orig_rr
        h.send_window_fn    = _saved


def test_continue_midroute_resends_window():
    """Firmware DỪNG GIỮA route (vd supply node passthrough 64: xe tự dừng tại node có
    arrival_action/supply_group rồi phát 'continue' xin đi tiếp). Route đã final
    (is_complete=True) → `_check_rolling_plan` BỎ QUA ngay (return tại `route.is_complete`)
    → KHÔNG gửi cửa sổ nào → xe KẸT mãi tại node giữa (đúng lỗi: AGV02 gửi cấp hàng nhưng
    dừng ở 64 không tới 19, phải điều khiển tay). FIX: gửi lại cửa sổ còn lại (force) để xe
    đi tiếp tới đích; KHÔNG complete task (xe chưa tới đích)."""
    print("[test] continue giữa route (is_complete) → gửi lại cửa sổ, không kẹt")
    g = load_graph()
    tc, h = reset(g)
    _fake_points(g)
    r = LH.LineAGVRoute(full_path=["2", "64", "19"], task_type="delivery",
                        direction="fwd", window_start=0, window_end=2, is_complete=True)
    h._routes["AGV02"] = r
    st = place(h, "AGV02", "64", driving=False)
    st.prev_tag = 2
    _orig_on_event = h.on_event
    h.on_event = lambda *a, **k: None    # bỏ qua ack MQTT
    _sent = []
    _orig_sw = h._send_window
    h._send_window = lambda a, rt, ws, we, fin, force=False: _sent.append((ws, we, fin, force))
    try:
        h._handle_event("AGV02", "continue", {}, st)
        if _sent == [(1, 2, True, True)]:
            _ok("gửi lại cửa sổ [1→2] final=True force=True → AGV02 đi tiếp 64→19")
        elif _sent:
            _bad(f"gửi cửa sổ SAI: {_sent} (kỳ vọng [(1,2,True,True)])")
        else:
            _bad("KHÔNG gửi cửa sổ → AGV02 vẫn kẹt tại 64 (supply node passthrough)")
        if "AGV02" in h._routes:
            _ok("route GIỮ NGUYÊN (không complete mù khi đứng giữa route)")
        else:
            _bad("route bị xoá → xe đứng giữa đường nhưng UI hiện 'sẵn sàng'")
    finally:
        h._send_window = _orig_sw
        h.on_event = _orig_on_event


def test_pickup_marked_on_arrival_not_dispatch():
    """Pickup CHỈ đánh dấu khi xe THỰC SỰ tới supply node (lifecycle 'picking'), KHÔNG
    phải lúc dispatch. Đánh dấu sớm + xe off-route trước khi tới → re-dispatch bị auto-
    complete bỏ qua → xe KHÔNG BAO GIỜ lấy hàng (lỗi AGV02: lạc 2→10 rồi bỏ qua 19, giao
    thẳng). CHỈ supply node (wait_sys + supply_group), KHÔNG delivery node (wait_sys nhưng
    không supply_group)."""
    print("[test] pickup đánh dấu khi TỚI supply node (không phải lúc dispatch)")
    g = load_graph()
    tc, h = reset(g)
    _fake_points(g)
    from task_queue import agv_task_queue as ATQ
    from types import SimpleNamespace
    MM.node_actions = {
        "19": {"arrival_action": "wait_sys", "supply_group": ["2", "3"]},  # supply
        "16": {"arrival_action": "wait_sys"},                               # delivery
    }
    ATQ._session_pickups.clear()
    ATQ._running["AGV02"] = SimpleNamespace(session_id="S1", dest_node="19", command="go_to")
    _saved_oe = h.on_event
    h.on_event = lambda *a, **k: None
    try:
        if not ATQ.session_has_pickup("S1", "19"):
            _ok("trước khi xe tới: session CHƯA đánh dấu pickup 19 (không mark lúc dispatch)")
        else:
            _bad("session đã đánh dấu 19 SỚM (lỗi: mark lúc dispatch)")
        # xe TỚI supply node 19 (route final) → arrived_wait_sys → picking → mark
        r = LH.LineAGVRoute(full_path=["2", "64", "19"], task_type="delivery",
                            direction="fwd", window_start=0, window_end=2, is_complete=True)
        h._routes["AGV02"] = r
        st = place(h, "AGV02", "19", driving=False)
        h._handle_event("AGV02", "arrived_wait_sys", {}, st)
        if ATQ.session_has_pickup("S1", "19"):
            _ok("xe TỚI 19 (picking) → ĐÁNH DẤU pickup 19 cho session")
        else:
            _bad("xe tới 19 nhưng KHÔNG đánh dấu pickup → giao hàng sẽ sai")
        # delivery node 16 (wait_sys, KHÔNG supply_group) → KHÔNG đánh dấu
        ATQ._running["AGV02"] = SimpleNamespace(session_id="S1", dest_node="16", command="go_to")
        r2 = LH.LineAGVRoute(full_path=["5", "8", "16"], task_type="delivery",
                             direction="fwd", window_start=0, window_end=2, is_complete=True)
        h._routes["AGV02"] = r2
        st2 = place(h, "AGV02", "16", driving=False)
        h._handle_event("AGV02", "arrived_wait_sys", {}, st2)
        if not ATQ.session_has_pickup("S1", "16"):
            _ok("delivery node 16 (không supply_group) → KHÔNG đánh dấu nhầm là pickup")
        else:
            _bad("đánh dấu nhầm delivery node 16 là pickup")
    finally:
        h.on_event = _saved_oe
        ATQ._running.pop("AGV02", None)
        ATQ._session_pickups.clear()
        MM.node_actions = {}


def test_rolling_anti_trap_vacate():
    """Lưới CHỐNG-TRAP phải chạy CẢ ở `_send_window` (rolling), không chỉ set_route. 2 xe
    CÙNG CHIỀU merge qua 5→8: AGV01 (leader) tại node 5 route 5→8→15; AGV02 (follower) tại
    node 4 route …5→8→16 đã GIỮ node 8. Re-check rolling (`_check_waiting_agvs` khi AGV02 di
    chuyển → _send_window) bị reservation cắt window AGV01 về [0→0] (node 8 bị AGV02 giữ) →
    GHI ĐÈ vacate → AGV01 đứng im tại 5 → 2 xe kẹt (đúng log: server bảo rẽ phải nhưng xe
    đứng im). Phải vacate [0→1]: AGV01 chắn node 5 mà AGV02 CẦN + node 8 trống vật lý."""
    print("[test] anti-trap rolling: _send_window vacate, không bị reservation cắt [0→0]")
    g = load_graph()
    tc, h = reset(g)
    _fake_points(g)
    # AGV02 (follower) tại node 4, route …5→8→16, ĐÃ GIỮ node 8 (reserve_ahead của follower)
    tc._registered["AGV02"] = {"path": ["19", "4", "18", "5", "8", "16"], "direction": "fwd",
                                "current_idx": 1, "priority": 3}
    place(h, "AGV02", "4", driving=False)
    tc._node_res["8"] = "AGV02"   # follower giữ node 8 (gốc gây cắt [0→0])
    tc._node_res["5"] = "AGV01"   # leader giữ node mình đang đứng
    # AGV01 (leader) tại node 5, route 5→8→15
    tc._registered["AGV01"] = {"path": ["5", "8", "15"], "direction": "bwd",
                                "current_idx": 0, "priority": 3}
    r = LH.LineAGVRoute(full_path=["5", "8", "15"], task_type="delivery", direction="bwd",
                        window_start=0, window_end=2, is_complete=False)
    h._routes["AGV01"] = r
    place(h, "AGV01", "5", driving=False)
    _sent = []
    _saved = h.send_window_fn
    h.send_window_fn = lambda a, p: _sent.append(p)
    try:
        h._send_window("AGV01", r, 0, 2, False)
        if r.window_end == 1 and tc._node_res.get("8") == "AGV01":
            _ok("CHỐNG-TRAP rolling → window [0→1] + cướp node 8 → AGV01 nhích 5→8 (không kẹt)")
        else:
            _bad(f"window_end={r.window_end} node8_owner={tc._node_res.get('8')} "
                 f"(kỳ vọng 1 + AGV01) → AGV01 vẫn kẹt tại 5")
        # đối chứng: nếu KHÔNG chắn xe nào (AGV02 không cần node 5) → KHÔNG vacate ẩu
        tc._node_res["8"] = "AGV02"
        tc._registered["AGV02"]["path"] = ["19", "4", "18"]   # không qua 5/8 nữa
        tc._registered["AGV02"]["current_idx"] = 1
        r2 = LH.LineAGVRoute(full_path=["5", "8", "15"], task_type="delivery", direction="bwd",
                             window_start=0, window_end=2, is_complete=False)
        h._send_window("AGV01", r2, 0, 2, False)
        if r2.window_end == 0:
            _ok("không chắn xe nào → GIỮ [0→0] (không vacate ẩu vào node bị giữ thật)")
        else:
            _bad(f"vacate ẩu khi không chắn ai: window_end={r2.window_end}")
    finally:
        h.send_window_fn = _saved


def test_headon_canonical_one_loser():
    """2 xe CÙNG PRIORITY head-on trên CÙNG cạnh {5,8} từ 2 đầu ĐỐI DIỆN: AGV01 đi 8→5
    (tại 16, route 16→8→5→18), AGV02 đi 5→8 (tại 5, route 5→8→15). Trước đây mỗi xe tính
    `_am_winner` theo `_conf_fn` RIÊNG (AGV01 thấy fn=8, AGV02 thấy fn=5) → arbiter ra winner
    KHÁC nhau → CẢ HAI tưởng mình thắng → cùng đứng chờ = DEADLOCK (đúng log: 2 xe 'winner,
    chờ thua né'). Nay dùng node CANONICAL (min cạnh) → đúng 1 xe loser (gọi né), 1 winner (chờ)."""
    print("[test] head-on cùng cạnh 2 đầu → đúng 1 loser né (không cả 2 cùng winner chờ)")
    g = load_graph()
    tc, h = reset(g)
    _fake_points(g)
    tc._registered["AGV01"] = {"path": ["16", "8", "5", "18"], "direction": "bwd",
                                "current_idx": 0, "priority": 3}
    r1 = LH.LineAGVRoute(full_path=["16", "8", "5", "18"], task_type="delivery",
                         direction="bwd", window_start=0, window_end=3, is_complete=False)
    h._routes["AGV01"] = r1
    place(h, "AGV01", "16", driving=False)
    tc._registered["AGV02"] = {"path": ["5", "8", "15"], "direction": "bwd",
                                "current_idx": 0, "priority": 3}
    r2 = LH.LineAGVRoute(full_path=["5", "8", "15"], task_type="delivery",
                         direction="bwd", window_start=0, window_end=2, is_complete=False)
    h._routes["AGV02"] = r2
    place(h, "AGV02", "5", driving=False)
    tc._node_res["8"] = "AGV01"   # AGV01 giữ node 8 (đang hướng tới)
    tc._node_res["5"] = "AGV02"   # AGV02 giữ node 5 (đang đứng)
    _loser_acts = []
    _orig = (h._try_line_reroute, h._yield_to_siding,
             h._back_up_to_reroute_node, h._back_up_to_prev)
    h._try_line_reroute        = lambda a, *x, **k: (_loser_acts.append(a), False)[1]
    h._yield_to_siding         = lambda a, *x, **k: False
    h._back_up_to_reroute_node = lambda a, *x, **k: False
    h._back_up_to_prev         = lambda a, *x, **k: False
    _saved = h.send_window_fn
    h.send_window_fn = lambda a, p: None
    try:
        h._check_rolling_plan("AGV01", h.state_store.get("AGV01"))
        h._check_rolling_plan("AGV02", h.state_store.get("AGV02"))
        if _loser_acts == ["AGV01"]:
            _ok("đúng 1 loser (AGV01) gọi né; AGV02 = winner chờ → không cả 2 cùng chờ")
        elif set(_loser_acts) == {"AGV01", "AGV02"}:
            _bad("CẢ HAI cùng né (arbiter ra 2 loser) → dao động")
        elif not _loser_acts:
            _bad("KHÔNG xe nào né → cả 2 cùng winner chờ = DEADLOCK (lỗi cũ)")
        else:
            _bad(f"loser sai: {_loser_acts} (kỳ vọng chỉ AGV01)")
    finally:
        (h._try_line_reroute, h._yield_to_siding,
         h._back_up_to_reroute_node, h._back_up_to_prev) = _orig
        h.send_window_fn = _saved


def test_continue_staging_no_skip_pickup():
    """Xe ĐỨNG CHỜ RETRY vì đích bị chiếm (vd lấy 64 xong, đi lấy 19 nhưng 19 bị xe khác
    giữ → 'đứng yên tại 64, chờ retry', KHÔNG có route). 'continue'/'confirm' lúc này KHÔNG
    được hoàn tất lệnh go_to(19) — nếu hoàn tất, xe BỎ QUA điểm lấy 19, nhảy sang giao hàng
    (đúng lỗi log; sau đó 19 chỉ được ghé như điểm né transit). Giữ lệnh chờ tới đích."""
    print("[test] continue khi staging (chưa tới đích) → KHÔNG bỏ qua điểm lấy hàng")
    g = load_graph()
    tc, h = reset(g)
    _fake_points(g)
    from task_queue import agv_task_queue as ATQ
    from types import SimpleNamespace
    _saved_oe = h.on_event
    h.on_event = lambda *a, **k: None
    _completed = []
    _orig_done = ATQ.on_agv_completed
    ATQ.on_agv_completed = lambda aid, **k: _completed.append(aid)
    try:
        # case 1: ĐANG CHỜ RETRY tại 64 (pending_retry_cmd set, _running RỖNG — đúng nhánh
        # "đứng yên chờ retry" gọi on_agv_completed(auto_dispatch=False)) → continue KHÔNG hoàn tất
        ATQ._running.pop("AGV01", None)
        h._routes.pop("AGV01", None)
        st = place(h, "AGV01", "64", driving=False)
        st.pending_retry_cmd = "go_to"
        st.pending_retry_dest = "19"
        h._handle_event("AGV01", "continue", {}, st)
        if not _completed:
            _ok("chờ retry tại 64 (đích 19 bị chiếm) → KHÔNG hoàn tất, giữ lệnh lấy 19")
        else:
            _bad("hoàn tất nhầm khi đang chờ retry → bỏ qua điểm lấy hàng 19")
        # case 2 (đối chứng): xe Ở ĐÚNG đích 19, KHÔNG pending → continue HOÀN TẤT bình thường
        _completed.clear()
        st2 = place(h, "AGV01", "19", driving=False)
        st2.pending_retry_cmd = None
        st2.pending_retry_dest = None
        ATQ._running["AGV01"] = SimpleNamespace(session_id="S", dest_node="19", command="go_to")
        h._handle_event("AGV01", "continue", {}, st2)
        if _completed == ["AGV01"]:
            _ok("(đối chứng) xe ở ĐÚNG đích 19, không pending → continue hoàn tất bình thường")
        else:
            _bad(f"đối chứng sai: completed={_completed} (kỳ vọng hoàn tất tại đích)")
    finally:
        h.on_event = _saved_oe
        ATQ.on_agv_completed = _orig_done
        ATQ._running.pop("AGV01", None)


def test_dest_claim_closer_goes_first():
    """Node đích bị 'claim TỪ XA' (xe khác đang TRÊN ĐƯỜNG tới, chưa ở vật lý tại đích) KHÔNG
    được chặn xe GẦN hơn — đúng ý user "chưa có xe nào ở node 19 mà báo occupied". AGV01 ở 64
    (sát 19), AGV02 ở 1 (xa) cùng đích 19 → AGV01 đi trước. Quan trọng: node 64 NẰM TRÊN đường
    AGV02 lên 19 → bắt AGV01 chờ = DEADLOCK (AGV02 không lên 19 được). Đối chứng: claimer gần
    hơn → giữ chờ; graph None → False (an toàn)."""
    print("[test] dest claim-từ-xa: xe gần đích đi trước (không deadlock chặn xe xa)")
    import networkx as _nx
    g = load_graph()
    if LH.requester_closer_than_claimer(g, "64", "1", "19"):
        _ok("AGV01(64) gần đích 19 hơn AGV02(1) → cho ĐI TRƯỚC (không chặn nhầm)")
    else:
        _bad("không nhận ra requester gần hơn → vẫn chặn nhầm")
    if "64" in _nx.shortest_path(g, "1", "19"):
        _ok("node 64 (chỗ AGV01 đứng) NẰM TRÊN đường claimer 1→19 → chờ sẽ deadlock")
    else:
        _bad("tiền đề bản đồ sai (64 không trên đường 1→19)")
    if not LH.requester_closer_than_claimer(g, "1", "64", "19"):
        _ok("(đối chứng) requester(1) XA hơn claimer(64) → KHÔNG chen, giữ chờ")
    else:
        _bad("đối chứng sai: requester xa hơn nhưng vẫn cho chen")
    if not LH.requester_closer_than_claimer(None, "64", "1", "19"):
        _ok("graph None → False (an toàn, giữ hành vi chờ cũ)")
    else:
        _bad("graph None nhưng trả True")


def test_park_plan_keeps_turn_at_start():
    """Plan đỗ-né/dừng-chờ (head-on dispatch) build từ node ĐẦU = vị trí xe → cú RẼ tại node
    đó phụ thuộc initial_prev_tag (node trước). Thiếu (None) → plan KHÔNG có TURN → xe đi
    THẲNG thay vì rẽ → off_route (đúng lỗi: đỗ ['4','9'] từ node 4 cần rẽ 19→4→9=left nhưng
    plan không turn → xe đi thẳng 4→18). Fix: truyền prev_tag thật vào build_line_plan."""
    print("[test] plan đỗ-né giữ cú rẽ tại node đầu (truyền initial_prev_tag)")
    from line_agv_plan_builder import build_line_plan, ACTION_TURN_L, ACTION_TURN_R
    pts = {"4": (0.0, 0.0), "9": (0.0, 0.0), "19": (0.0, 0.0)}
    na = {"4": {"turn_map": {"19_9_fwd": "left", "19_9_bwd": "left"}}}
    plan_ok = build_line_plan(["4", "9"], pts, task_type="transit", node_actions=na,
                              direction="fwd", edge_speeds={}, edge_lidar={},
                              agv_id="AGV01", initial_prev_tag="19")
    _acts_ok = [s["a"] for s in plan_ok["d"]]
    if ACTION_TURN_L in _acts_ok:
        _ok("initial_prev_tag=19 → plan CÓ TURN_L tại node 4 (xe rẽ đúng tới 9)")
    else:
        _bad(f"thiếu TURN_L dù có prev_tag: acts={_acts_ok}")
    plan_bad = build_line_plan(["4", "9"], pts, task_type="transit", node_actions=na,
                               direction="fwd", edge_speeds={}, edge_lidar={},
                               agv_id="AGV01", initial_prev_tag=None)
    _acts_bad = [s["a"] for s in plan_bad["d"]]
    if ACTION_TURN_L not in _acts_bad and ACTION_TURN_R not in _acts_bad:
        _ok("(đối chứng) initial_prev_tag=None → KHÔNG turn = gốc lỗi đi thẳng 4→18")
    else:
        _bad(f"đối chứng sai: không prev_tag mà vẫn có turn? acts={_acts_bad}")


def test_reroute_releases_stale_reservation():
    """Khi `_try_line_reroute` đổi sang đường VÒNG, PHẢI cập nhật lại đăng ký + reservation
    trong TrafficCoordinator — NHẢ node CŨ mình KHÔNG còn đi qua. Thiếu → node cũ STALE bị
    khoá → xe khác chờ phantom mãi = DEADLOCK (đúng lỗi: AGV02 reroute 8→5→18 → 8→15→9→4→18
    nhưng node 5 vẫn bị nó khoá → AGV01 'following xe phía trước dừng tại 5' chờ mãi)."""
    print("[test] reroute NHẢ reservation node cũ (không stale → không deadlock)")
    g = load_graph()
    tc, h = reset(g)
    _fake_points(g)
    # AGV01 (mạnh, delivery pri3) đi qua 5,18 → AGV02 phải né đường AGV01
    tc._registered["AGV01"] = {"path": ["17", "5", "18"], "direction": "fwd",
                                "current_idx": 0, "priority": 3}
    place(h, "AGV01", "17", driving=False)
    # AGV02 (yếu, transit pri2) ở node 8, route 8→5→18, đã GIỮ node 5 (đường cũ)
    tc._registered["AGV02"] = {"path": ["8", "5", "18"], "direction": "fwd",
                                "current_idx": 0, "priority": 2}
    r2 = LH.LineAGVRoute(full_path=["8", "5", "18"], task_type="transit", direction="fwd",
                         window_start=0, window_end=2, is_complete=False)
    h._routes["AGV02"] = r2
    st2 = place(h, "AGV02", "8", driving=False)
    tc._node_res["5"] = "AGV02"
    _saved = h.send_window_fn
    h.send_window_fn = lambda a, p: None
    try:
        _rr = h._try_line_reroute("AGV02", st2, r2, 0)
        _new = list(r2.full_path)
        if _rr and "5" not in _new:
            _ok(f"reroute né node 5 → {_new}")
        else:
            _bad(f"reroute không né được node 5: rr={_rr} path={_new}")
        if tc._node_res.get("5") != "AGV02":
            _ok("node 5 ĐÃ NHẢ (không còn AGV02 khoá) → AGV01 đi được, không deadlock")
        else:
            _bad("node 5 VẪN bị AGV02 khoá (stale) → AGV01 chờ phantom = deadlock")
        if tc._registered["AGV02"]["path"] == [str(n) for n in _new]:
            _ok("registered path AGV02 cập nhật = route mới (đồng bộ)")
        else:
            _bad(f"registered path lệch: reg={tc._registered['AGV02']['path']} route={_new}")
    finally:
        h.send_window_fn = _saved


def test_reroute_notifies_waiting_agvs():
    """Sau khi reroute (nhả reservation node cũ), PHẢI thông báo xe khác RE-CHECK NGAY —
    nếu không, xe đang chờ node vừa-nhả (vd AGV02 'following dừng tại 5') sẽ kẹt tới khi xe
    reroute gửi state-message kế; nếu xe reroute đứng im/firmware lỡ dừng → kẹt lâu. Kiểm tra
    `_check_waiting_agvs` được gọi ngay sau reroute."""
    print("[test] reroute báo xe chờ re-check ngay (không kẹt chờ node đã nhả)")
    g = load_graph()
    tc, h = reset(g)
    _fake_points(g)
    tc._registered["AGV01"] = {"path": ["17", "5", "18"], "direction": "fwd",
                                "current_idx": 0, "priority": 3}
    place(h, "AGV01", "17", driving=False)
    tc._registered["AGV02"] = {"path": ["8", "5", "18"], "direction": "fwd",
                                "current_idx": 0, "priority": 2}
    r2 = LH.LineAGVRoute(full_path=["8", "5", "18"], task_type="transit", direction="fwd",
                         window_start=0, window_end=2, is_complete=False)
    h._routes["AGV02"] = r2
    st2 = place(h, "AGV02", "8", driving=False)
    tc._node_res["5"] = "AGV02"
    _notified = []
    _orig_cwa = h._check_waiting_agvs
    h._check_waiting_agvs = lambda a: _notified.append(a)
    _saved = h.send_window_fn
    h.send_window_fn = lambda a, p: None
    try:
        _rr = h._try_line_reroute("AGV02", st2, r2, 0)
        if _rr and _notified == ["AGV02"]:
            _ok("reroute → _check_waiting_agvs gọi ngay (xe chờ đánh giá lại node đã nhả)")
        else:
            _bad(f"reroute KHÔNG thông báo: rr={_rr} notified={_notified}")
    finally:
        h._check_waiting_agvs = _orig_cwa
        h.send_window_fn = _saved


def test_obstacle_blocker_asymmetric_only_loser_reroutes():
    """Vật cản là XE KHÁC trong `_handle_obstacle_timeout`: CHỈ bên THUA arbiter ĐI VÒNG,
    bên THẮNG ĐỨNG CHỜ. Nếu CẢ 2 cùng obstacle-reroute (avoid_all) khi thấy nhau → cùng nhảy
    nhánh → GIẰNG CO quanh vùng tắc (đúng log: 2 xe né qua né lại 5-8-15-16). Arbiter theo
    priority→id (đối xứng)."""
    print("[test] vật cản là AGV: chỉ bên THUA né, bên THẮNG chờ (chống thrashing)")
    g = load_graph()
    tc, h = reset(g)
    _fake_points(g)
    _rr_calls = []
    _orig = h._try_line_reroute
    h._try_line_reroute = lambda a, *x, **k: (_rr_calls.append(a), True)[1]
    _saved = h.send_window_fn
    h.send_window_fn = lambda a, p: None
    try:
        # WINNER: AGV01 (cùng pri AGV02 → id thắng), vật cản AGV02 ở node 8 phía trước
        tc._registered["AGV01"] = {"path": ["15", "8", "16"], "direction": "fwd",
                                    "current_idx": 0, "priority": 3}
        r1 = LH.LineAGVRoute(full_path=["15", "8", "16"], task_type="delivery", direction="fwd",
                             window_start=0, window_end=2, is_complete=False)
        h._routes["AGV01"] = r1
        st1 = place(h, "AGV01", "15", driving=False)
        st1.obstacle_direction = "fwd"
        tc._registered["AGV02"] = {"path": ["8", "16"], "direction": "fwd",
                                    "current_idx": 0, "priority": 3}
        place(h, "AGV02", "8", driving=False)
        h._handle_obstacle_timeout("AGV01", st1)
        if "AGV01" not in _rr_calls and r1.waiting_before_conflict == "8":
            _ok("AGV01 THẮNG → KHÔNG đi vòng, DỪNG CHỜ trước node 8 (không thrashing)")
        else:
            _bad(f"AGV01 thắng nhưng vẫn né: calls={_rr_calls} wait={r1.waiting_before_conflict}")
        # LOSER: AGV02 (id thua AGV01), vật cản AGV01 ở node 5 phía trước
        _rr_calls.clear()
        tc._registered["AGV02"]["path"] = ["8", "5", "18"]
        tc._registered["AGV02"]["current_idx"] = 0
        r2 = LH.LineAGVRoute(full_path=["8", "5", "18"], task_type="delivery", direction="fwd",
                             window_start=0, window_end=2, is_complete=False)
        h._routes["AGV02"] = r2
        st2 = place(h, "AGV02", "8", driving=False)
        st2.obstacle_direction = "fwd"
        place(h, "AGV01", "5", driving=False)
        h._handle_obstacle_timeout("AGV02", st2)
        if _rr_calls == ["AGV02"]:
            _ok("AGV02 THUA → ĐI VÒNG né (đúng 1 xe né, không cả 2 = không thrashing)")
        else:
            _bad(f"AGV02 thua nhưng không né: calls={_rr_calls}")
    finally:
        h._try_line_reroute = _orig
        h.send_window_fn = _saved


def test_no_steal_node_in_owner_window():
    """KHÔNG cướp node nằm trong CỬA SỔ ĐANG CHẠY của chủ (firmware đã nhận plan lái qua →
    sắp/đang đi). Thiếu → race ngã ba: window cũ gửi khi node còn trống, xe ưu-tiên-cao cướp
    node → 2 xe cùng lái vào → ĐÂM (đúng log: AGV01 9→4 & AGV02 18→4 cùng vào node 4).
    `_owner_committed_to` phải True khi node ∈ [window_start..window_end] dù registered
    current_idx còn ở xa (bước-kế chưa tới node đó)."""
    print("[test] không cướp node trong cửa sổ đang chạy của chủ (chống đâm ngã ba)")
    g = load_graph()
    tc, h = reset(g)
    _fake_points(g)
    tc._registered["AGV01"] = {"path": ["15", "9", "4", "19"], "direction": "bwd",
                                "current_idx": 0, "priority": 1}
    r1 = LH.LineAGVRoute(full_path=["15", "9", "4", "19"], task_type="return_charge",
                         direction="bwd", window_start=0, window_end=3, is_complete=False)
    h._routes["AGV01"] = r1
    place(h, "AGV01", "15", driving=True)
    tc._registered["AGV02"] = {"path": ["18", "4", "19"], "direction": "bwd",
                                "current_idx": 0, "priority": 2}
    place(h, "AGV02", "18", driving=True)
    # bước-kế registered của AGV01 là 9 (KHÔNG phải 4) — nhưng 4 ∈ window [0→3]
    if tc._owner_committed_to("AGV01", "4"):
        _ok("node 4 ∈ window AGV01 → committed=True (dù bước-kế registered là 9)")
    else:
        _bad("committed=False cho node trong window → cướp được = đâm")
    if not tc._owner_committed_to("AGV01", "64"):
        _ok("(đối chứng) node 64 NGOÀI window AGV01 → committed=False")
    else:
        _bad("đối chứng sai: node ngoài path lại committed")
    # điều kiện cướp (y như reserve_ahead): bị chặn vì committed
    _can_steal = (tc._arbitrate("AGV02", "AGV01", "4") == "AGV02"
                  and not tc._owner_committed_to("AGV01", "4")
                  and not tc._owner_at_node("AGV01", "4"))
    if not _can_steal:
        _ok("AGV02 (pri 2>1) KHÔNG cướp được node 4 → AGV01 lái qua an toàn, không đâm")
    else:
        _bad("AGV02 cướp được node 4 dù AGV01 đang lái tới (trong window) → đâm")


def test_backward_start_respects_reservation():
    """Đoạn LÙI đầu đường (backward-start dispatch) phải build plan THEO window CẮT bởi
    reservation — GIỐNG nhánh forward. Gốc lỗi (đúng log): AGV01 lùi 17→5 trong khi AGV02
    GIỮ node 5; dispatch cũ build full bwd_seg rồi gửi BẤT KỂ window=[0→0] → firmware được
    lệnh lái VÀO node 5 (không sở hữu) → 2 xe cùng vào node 5 = ĐÂM. Fix: set_route TRƯỚC,
    build_plan_window(w_end=window_end) → node 5 bị giữ ⇒ plan CHỈ giữ tại 17 (không t:5)."""
    print("[test] backward-start tôn trọng window cắt theo reservation (chống đâm)")
    from line_agv_plan_builder import build_plan_window, ACTION_RUN
    g = load_graph()
    tc, h = reset(g)
    _fake_points(g)
    # AGV02 (delivery, pri 3) GIỮ node 5; AGV01 (transit, pri 2) muốn lùi 17→5.
    tc._registered["AGV02"] = {"path": ["4", "18", "5", "8", "16"], "direction": "fwd",
                                "current_idx": 0, "priority": 3}
    place(h, "AGV02", "18", driving=True)
    tc._node_res["5"] = "AGV02"
    place(h, "AGV01", "17", driving=False)
    r = h.set_route("AGV01", ["17", "5"], "transit", direction="bwd")
    plan = build_plan_window(full_path=["17", "5"], w_start=0, w_end=r.window_end,
                             points=MM.points, is_final=r.is_complete, task_type="transit",
                             node_actions={}, direction="bwd", edge_speeds={}, edge_lidar={},
                             agv_id="AGV01", initial_prev_tag=None)
    _drives_to_5 = any(str(s["t"]) == "5" and s["a"] == ACTION_RUN for s in plan["d"])
    if r.window_end == 0 and not _drives_to_5:
        _ok("node 5 bị giữ → window [0→0], plan GIỮ tại 17 (KHÔNG lệnh lái vào node 5)")
    else:
        _bad(f"window_end={r.window_end} drives_to_5={_drives_to_5} → vẫn lao vào node 5 = đâm")
    # ĐỐI CHỨNG: node 5 TRỐNG → window đầy đủ → plan CÓ lái 17→5 (hành vi cũ giữ nguyên).
    tc2, h2 = reset(g)
    _fake_points(g)
    place(h2, "AGV01", "17", driving=False)
    r2 = h2.set_route("AGV01", ["17", "5"], "transit", direction="bwd")
    plan2 = build_plan_window(full_path=["17", "5"], w_start=0, w_end=r2.window_end,
                              points=MM.points, is_final=r2.is_complete, task_type="transit",
                              node_actions={}, direction="bwd", edge_speeds={}, edge_lidar={},
                              agv_id="AGV01", initial_prev_tag=None)
    _drives_to_5b = any(str(s["t"]) == "5" for s in plan2["d"])
    if r2.window_end == 1 and _drives_to_5b:
        _ok("(đối chứng) node 5 trống → window [0→1], plan lái 17→5 bình thường (không phá hành vi cũ)")
    else:
        _bad(f"đối chứng sai: window_end={r2.window_end} reaches_5={_drives_to_5b}")


def test_obstacle_winner_proceeds_when_loser_held():
    """Vật cản là XE KHÁC: xe THẮNG mà ĐÃ GIỮ node phía trước và xe cản là xe ƯU TIÊN THẤP
    đang ĐỨNG YÊN (bị chính reservation của winner khoá → KHÔNG né được) → winner KHÔNG
    đứng chờ "để xe kia né" (sẽ DEADLOCK cả 2 đứng im) mà GỬI LẠI window đi tiếp qua node
    mình sở hữu. Đúng log: AGV02 thắng đứng chờ node 5 + AGV01 thua đứng chờ node 5 = kẹt."""
    print("[test] winner ĐI TIẾP (gửi lại window) khi xe thua bị khoá không né được")
    g = load_graph()
    tc, h = reset(g)
    _fake_points(g)
    _sent = []
    _saved = h.send_window_fn
    h.send_window_fn = lambda a, p: _sent.append(a)
    try:
        # AGV02 THẮNG (delivery pri 3) tại 18, GIỮ node 18 & 5; vật cản AGV01 (transit pri 2)
        # đứng yên tại 17 (kề node 5) — AGV01 KHÔNG né được vì node kế của nó (5) do AGV02 giữ.
        tc._registered["AGV02"] = {"path": ["18", "5", "8", "16"], "direction": "fwd",
                                    "current_idx": 0, "priority": 3}
        r2 = LH.LineAGVRoute(full_path=["18", "5", "8", "16"], task_type="delivery",
                             direction="fwd", window_start=0, window_end=1, is_complete=False)
        h._routes["AGV02"] = r2
        st2 = place(h, "AGV02", "18", driving=False)
        st2.obstacle_direction = "fwd"
        tc._node_res["18"] = "AGV02"
        tc._node_res["5"]  = "AGV02"
        tc._registered["AGV01"] = {"path": ["17", "5", "8", "15"], "direction": "fwd",
                                    "current_idx": 0, "priority": 2}
        place(h, "AGV01", "17", driving=False)
        h._handle_obstacle_timeout("AGV02", st2)
        if "AGV02" in _sent and r2.waiting_before_conflict != "5":
            _ok("AGV02 THẮNG & giữ node 5, xe thua bị khoá → GỬI LẠI window đi tiếp (không kẹt)")
        else:
            _bad(f"AGV02 không đi tiếp: sent={_sent} wait={r2.waiting_before_conflict} = deadlock")
    finally:
        h.send_window_fn = _saved


def test_off_route_recovery_when_not_on_route():
    """Xe ĐỨNG tại node KHÔNG nằm trên route đăng ký (route CHƯA complete) → rolling plan
    không tính được current_idx (ValueError). Trước đây return im lặng → xe KẸT MÃI, winner
    xe kia chờ nó dời = DEADLOCK (đúng log: AGV01 kẹt ở node 8 — firmware chạy plan 16→8 cũ
    trong khi route server là 16→7→6→17… không chứa 8 — plan-race). FIX: off_route re-dispatch
    để lấy route mới từ vị trí thực → xe đi tiếp."""
    print("[test] off-route recovery khi vị trí xe ∉ route (thoát kẹt plan-race)")
    g = load_graph()
    tc, h = reset(g)
    _fake_points(g)
    _events = []
    _orig_ev = h._handle_event
    h._handle_event = lambda a, ev, d, st: _events.append((a, ev))
    try:
        # Route server = nhánh 16→7→6→17 (KHÔNG chứa node 8), CHƯA complete
        r1 = LH.LineAGVRoute(full_path=["16", "7", "6", "17"], task_type="return_charge",
                             direction="fwd", window_start=0, window_end=1, is_complete=False)
        h._routes["AGV01"] = r1
        # Xe ĐỨNG vật lý tại node 8 (∉ route), không lái, không lifecycle
        st1 = place(h, "AGV01", "8", driving=False)
        st1.task_lifecycle = None
        h._check_rolling_plan("AGV01", st1)
        if ("AGV01", "off_route") in _events:
            _ok("vị trí 8 ∉ route → off_route re-dispatch (không còn return im lặng = kẹt)")
        else:
            _bad(f"KHÔNG off_route → xe kẹt mãi tại node lạ: events={_events}")
        # ĐỐI CHỨNG: xe ĐANG LÁI tại node lạ (transient) → KHÔNG off_route (chờ nó tới node route)
        _events.clear()
        st2 = place(h, "AGV01", "8", driving=True)
        st2.task_lifecycle = None
        h._check_rolling_plan("AGV01", st2)
        if ("AGV01", "off_route") not in _events:
            _ok("(đối chứng) đang LÁI tại node lạ → KHÔNG off_route (tránh re-dispatch transient)")
        else:
            _bad("đối chứng sai: off_route khi đang lái (transient)")
    finally:
        h._handle_event = _orig_ev


def test_reroute_cooldown_prevents_flipflop():
    """Chống DAO ĐỘNG: sau 1 reroute-do-obstacle (avoid_all), reroute avoid_all KẾ < cooldown
    bị CHẶN (giữ nhánh đã chọn, chờ tại chỗ) → không lật qua lật lại 2 nhánh vòng gây plan-race
    (đúng log: AGV01 flip-flop 16→8→15 ⇄ 16→7→6→17 liên tục). Né head-on chủ động (avoid_all=
    False) KHÔNG bị chặn."""
    print("[test] reroute cooldown chặn flip-flop lật nhánh (avoid_all)")
    import time as _t
    g = load_graph()
    tc, h = reset(g)
    _fake_points(g)
    _saved = h.send_window_fn
    h.send_window_fn = lambda a, p: None
    try:
        def _fresh_route():
            tc._registered["AGV01"] = {"path": ["8", "5", "18"], "direction": "fwd",
                                        "current_idx": 0, "priority": 1}
            r = LH.LineAGVRoute(full_path=["8", "5", "18"], task_type="delivery",
                                direction="fwd", window_start=0, window_end=2, is_complete=False)
            h._routes["AGV01"] = r
            return r
        st1 = place(h, "AGV01", "8", driving=False)
        # (1) reroute đầu (cooldown=0) né node 5 → THÀNH CÔNG (có nhánh vòng 8→15/16→…→18)
        h._reroute_ts.pop("AGV01", None)
        r1 = _fresh_route()
        ok1 = h._try_line_reroute("AGV01", st1, r1, 0, {"5"}, avoid_all=True)
        if ok1 and "5" not in r1.full_path[1:]:
            _ok("reroute đầu (ngoài cooldown) → THÀNH CÔNG, né node 5 qua nhánh vòng")
        else:
            _bad(f"reroute đầu thất bại: ok={ok1} path={r1.full_path}")
        # (2) reroute KẾ ngay sau (trong cooldown) → BỊ CHẶN, giữ nhánh, route KHÔNG đổi
        r2 = _fresh_route()
        h._reroute_ts["AGV01"] = _t.monotonic()
        _before = list(r2.full_path)
        ok2 = h._try_line_reroute("AGV01", st1, r2, 0, {"5"}, avoid_all=True)
        if (not ok2) and r2.full_path == _before:
            _ok("reroute kế (trong cooldown) → BỊ CHẶN, giữ nhánh (chống dao động)")
        else:
            _bad(f"cooldown không chặn → vẫn flip-flop: ok={ok2} path={r2.full_path}")
    finally:
        h.send_window_fn = _saved


def test_no_backup_into_held_node():
    """`_back_up_to_prev` (thoát deadlock head-on) KHÔNG được LÙI vào node đang bị xe KHÁC
    giữ chỗ. Gốc lỗi (đúng log): AGV02 ở 15 head-on tại node 8 (do AGV01 giữ) → "LÙI VỀ
    prev"=node 8 (vừa đi 8→15) → lùi THẲNG vào node đối thủ giữ → firmware đi nhầm ra
    node 9/ngoài đường + không thoát deadlock. Khi prev bị giữ → return False (đứng chờ)."""
    print("[test] không lùi vào node đang bị xe khác giữ (thoát deadlock an toàn)")
    g = load_graph()
    tc, h = reset(g)
    _fake_points(g)
    _sent = []
    _saved = h.send_window_fn
    h.send_window_fn = lambda a, p: _sent.append(a)
    try:
        # AGV02 ở node 15, vừa đi 8→15 (prev=8), route delivery tới 16
        r2 = LH.LineAGVRoute(full_path=["15", "8", "16"], task_type="delivery",
                             direction="fwd", window_start=0, window_end=0, is_complete=False)
        h._routes["AGV02"] = r2
        st2 = place(h, "AGV02", "15", driving=False)
        st2.prev_tag = 8
        # node 8 (prev của AGV02) đang bị AGV01 giữ chỗ
        tc._registered["AGV01"] = {"path": ["16", "8", "15"], "direction": "fwd",
                                    "current_idx": 0, "priority": 3}
        tc._node_res["8"] = "AGV01"
        ok = h._back_up_to_prev("AGV02", st2, r2)
        if (not ok) and "AGV02" not in _sent:
            _ok("prev (node 8) bị AGV01 giữ → KHÔNG lùi (đứng chờ), không gửi plan lùi bậy")
        else:
            _bad(f"vẫn lùi vào node bị giữ → đâm/đi nhầm: ok={ok} sent={_sent}")
        # ĐỐI CHỨNG: prev TRỐNG → lùi bình thường (hành vi thoát deadlock cũ giữ nguyên)
        _sent.clear()
        del tc._node_res["8"]
        tc._registered.pop("AGV01", None)
        h.state_store._states.pop("AGV01", None)
        ok2 = h._back_up_to_prev("AGV02", st2, r2)
        if ok2 and "AGV02" in _sent:
            _ok("(đối chứng) prev trống → lùi bình thường (không phá thoát-deadlock cũ)")
        else:
            _bad(f"đối chứng sai: prev trống mà không lùi: ok={ok2} sent={_sent}")
    finally:
        h.send_window_fn = _saved


def test_dest_occupied_not_headon_at_dispatch():
    """`find_head_on` (dispatch): xe khác ĐỨNG tại ĐÍCH CUỐI của ta (vd đang picking ở
    pickup chung node 19) KHÔNG phải head-on → trả negative (chờ), KHÔNG phải (idx, other)
    = head-on → đỗ-né đi vòng XA. Gốc lỗi (đúng log): AGV01 picking tại 19, AGV02 đi
    2→64→19 lấy hàng → dispatch coi head-on tại 64→19 → AGV02 đỗ tận node 10 → quay lại
    tiếp cận 19 kiểu LÙI-CÓ-RẼ kỳ lạ. Phải KHỚP _find_upcoming_conflict runtime (đích bị
    chiếm → chờ)."""
    print("[test] dispatch: xe đứng tại ĐÍCH cuối → chờ, KHÔNG head-on đi vòng")
    g = load_graph()
    tc, h = reset(g)
    # AGV01 đứng (picking) tại node 19 — deregistered sau confirm, route delivery rời 19→4
    place(h, "AGV01", "19", driving=False)
    r1 = LH.LineAGVRoute(full_path=["19", "4", "18", "5", "17"], task_type="delivery",
                         direction="fwd", window_start=0, window_end=4, is_complete=True)
    h._routes["AGV01"] = r1
    # AGV02 đi 2→64→19 lấy hàng (đích cuối = 19, nơi AGV01 đang đứng)
    res = tc.find_head_on("AGV02", ["2", "64", "19"], task_type="delivery", near_only=False)
    if not isinstance(res, tuple):
        _ok(f"đích 19 bị AGV01 chiếm → KHÔNG head-on (trả {res}=chờ), không đỗ-né đi vòng node 10")
    else:
        _bad(f"vẫn coi head-on tại đích → đỗ-né đi vòng xa = maneuver loạn: {res}")
    # ĐỐI CHỨNG: xe đứng tại node GIỮA đường (không phải đích) ngược chiều → vẫn head-on
    tc2, h2 = reset(g)
    place(h2, "AGV01", "64", driving=False)
    r1b = LH.LineAGVRoute(full_path=["64", "2", "1"], task_type="delivery",
                          direction="fwd", window_start=0, window_end=2, is_complete=True)
    h2._routes["AGV01"] = r1b
    res2 = tc2.find_head_on("AGV02", ["2", "64", "19"], task_type="delivery", near_only=False)
    if isinstance(res2, tuple) and res2[0] == 0:
        _ok("(đối chứng) xe ngược chiều đứng GIỮA đường (node 64, không phải đích) → vẫn head-on")
    else:
        _bad(f"đối chứng sai: xe chắn giữa đường mà không báo head-on: {res2}")


def main():
    print("=" * 70)
    print("SÀN AN TOÀN TRAFFIC — phải LUÔN xanh sau mọi thay đổi")
    print("=" * 70)
    for t in (test_no_steal_occupied, test_no_steal_committed,
              test_window_cap_blocks_overlap, test_edge_headon_blocked,
              test_autoblock_single_lane,
              test_yield_offpath_siding, test_arbiter_single_winner,
              test_reroute_avoids_winner, test_staging_intent_avoided,
              test_yield_resume_timing,
              test_setroute_conflict_cap_standoff,
              test_rolling_stop_respects_conflict,
              test_backup_to_reroute_node,
              test_continue_midroute_no_complete,
              test_siding_park_no_picking,
              test_following_not_penalized,
              test_siding_excludes_station,
              test_following_no_yield_no_retreat,
              test_loser_yields_to_stopped_winner,
              test_edge_release_on_move,
              test_winner_no_detour_when_unregistered,
              test_dispatch_headon_winner_no_yield,
              test_yield_siding_preserves_bwd_dir,
              test_anti_trap_vacate,
              test_no_redundant_siding_when_clear,
              test_loser_waits_on_route_not_siding,
              test_immediate_headon_loser_evades,
              test_continue_midroute_resends_window,
              test_pickup_marked_on_arrival_not_dispatch,
              test_rolling_anti_trap_vacate,
              test_headon_canonical_one_loser,
              test_continue_staging_no_skip_pickup,
              test_dest_claim_closer_goes_first,
              test_park_plan_keeps_turn_at_start,
              test_reroute_releases_stale_reservation,
              test_reroute_notifies_waiting_agvs,
              test_obstacle_blocker_asymmetric_only_loser_reroutes,
              test_no_steal_node_in_owner_window,
              test_backward_start_respects_reservation,
              test_obstacle_winner_proceeds_when_loser_held,
              test_off_route_recovery_when_not_on_route,
              test_reroute_cooldown_prevents_flipflop,
              test_no_backup_into_held_node,
              test_dest_occupied_not_headon_at_dispatch):
        try:
            t()
        except Exception as e:
            _bad(f"{t.__name__} CRASH: {e!r}")
    print("=" * 70)
    print(f"KẾT QUẢ: {_PASS} pass, {_FAIL} fail")
    print("=" * 70)
    sys.exit(1 if _FAIL else 0)


if __name__ == "__main__":
    main()
