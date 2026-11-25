"""Test _head_on_should_wait: HEAD-ON ưu tiên CHỜ xe kia đi qua, chỉ đi vòng khi có xe thứ 3 cần đoạn đó
hoặc xe kia đứng yên. Chạy: PYTHONIOENCODING=utf-8 python test_headon_wait.py"""
import mqtt_client as mc
from line_agv_handler import line_agv_handler as H, traffic_coordinator as TC

_pass = _fail = 0


def check(cond, msg):
    global _pass, _fail
    if cond:
        _pass += 1; print("  PASS:", msg)
    else:
        _fail += 1; print("  FAIL:", msg)


def reset():
    TC._registered.clear(); TC._intent_route.clear()


def put(agv, tag, path, driving=True):
    st = H.state_store.get_or_create(agv)
    st.current_tag = tag; st.driving = driving
    TC._registered[agv] = {"path": path, "current_idx": path.index(str(tag)), "priority": 2}


mine = ["33", "34", "5"]
print("[test] chỉ 2 xe, xe kia đang chạy, đoạn chung ngắn → CHỜ")
reset(); put("A01", "5", ["5", "34", "33"])
check(mc._head_on_should_wait("A02", "A01", mine) is True, "chờ A01 đi qua, không vòng")

print("[test] có xe thứ 3 cũng cần node đoạn đó → đi vòng")
put("A03", "21", ["21", "34", "5"])
check(mc._head_on_should_wait("A02", "A01", mine) is False, "A03 cũng đi qua 34 → không chờ")

print("[test] xe kia ĐỨNG YÊN → đi vòng")
reset(); put("A01", "5", ["5", "34", "33"], driving=False)
check(mc._head_on_should_wait("A02", "A01", mine) is False, "A01 đứng yên → không chờ")

print("[test] đoạn chung quá dài → đi vòng")
reset(); long_mine = [str(i) for i in range(1, 9)]
put("A01", "8", [str(i) for i in range(8, 0, -1)])
check(mc._head_on_should_wait("A02", "A01", long_mine) is False, "đoạn chung 7 cạnh > ngưỡng → không chờ")

print("[test] xe thứ 3 đi chỗ khác → vẫn chờ")
reset(); put("A01", "5", ["5", "34", "33"]); put("A03", "90", ["90", "91"])
check(mc._head_on_should_wait("A02", "A01", mine) is True, "A03 ở xa → chờ")


print("[test] ÉP NHƯỜNG: chỗ đỗ ở ngã ba đông xe (chế độ thường không tìm được, relaxed tìm được)")
import networkx as nx
g = nx.DiGraph()
for a, b in [("19","20"),("20","21"),("21","22"),("22","23"),("21","34"),("34","35"),("22","33")]:
    g.add_edge(a, b, weight=1.0); g.add_edge(b, a, weight=1.0)
mc.map_manager.graph = g; mc.map_manager.line_graph = g; mc.map_manager.node_actions = {}
reset()
put("SIM03", "19", ["19", "20", "21", "22", "23"])
put("SIM02", "35", ["35", "34", "21", "20"])
put("SIM05", "21", ["21", "34", "35"])
strict = TC.find_flexible_parking("SIM05", "21", ["21", "34", "35"])
relaxed = TC.find_flexible_parking("SIM05", "21", ["21", "34", "35"], relaxed=True)
check(strict is None, f"thường: mọi hướng thoát nằm trên đường xe khác -> None (được {strict})")
check(relaxed == "33", f"relaxed: đỗ vào {relaxed} (22 trống vật lý; 33 không nằm trên đường xe nào nên ưu tiên hơn 23)")
H.state_store.get_or_create("SIM04").current_tag = "22"
r2 = TC.find_flexible_parking("SIM05", "21", ["21", "34", "35"], relaxed=True)
check(r2 not in ("22", "23", "33"), f"relaxed không đi xuyên/đỗ ở node có xe đứng (22 có SIM04) -> {r2}")

print(f"\nKẾT QUẢ: {_pass} pass, {_fail} fail")
# ── Lật qua lại A→B→A không được tính là "tiến" (SIM01 lật 22↔33 che mắt ép nhường, 2026-10-29) ──
import time as _t
reset()
TC.register("SIM01", ["22", "33", "34"], "fwd", "delivery")
TC._progress.pop("SIM01", None)
TC._registered["SIM01"]["last_progress_ts"] = _t.monotonic() - 100
TC.update_position("SIM01", "33")
check(_t.monotonic() - TC._registered["SIM01"]["last_progress_ts"] < 1, "tới node MỚI 33 -> tính là tiến")
TC._registered["SIM01"]["last_progress_ts"] = _t.monotonic() - 100
TC._registered["SIM01"]["path"] = ["22", "33", "22", "21"]   # replan lật về 22
TC._registered["SIM01"]["current_idx"] = 1
TC.update_position("SIM01", "22")
check(_t.monotonic() - TC._registered["SIM01"]["last_progress_ts"] > 90, "quay lại node vừa qua (33→22) -> KHÔNG reset mốc đứng im")
TC._progress["SIM01"]["real_ts"] = _t.monotonic() - 100   # (giả lập: lần tiến thật cuối cách đây 100s)
TC.register("SIM01", ["22", "33", "34"], "fwd", "delivery")   # replan lại làm register lại
check(_t.monotonic() - TC._registered["SIM01"]["last_progress_ts"] > 90, "register lại khi đang lật -> giữ mốc đứng im cũ")
TC.update_position("SIM01", "33")
TC.update_position("SIM01", "34")
check(_t.monotonic() - TC._registered["SIM01"]["last_progress_ts"] < 1, "đi tới node mới sau đó -> tiến lại bình thường")

# ── find_stall_cycles: xe chặn ĐẦU TIÊN không bí thì vẫn phải thấy vòng với xe chặn thứ hai ──
reset()
for a, pth in (("A", ["1", "2", "3", "4"]), ("B", ["5", "3", "9"]), ("C", ["7", "2", "8"])):
    TC.register(a, pth, "fwd", "delivery")
TC._node_res.clear()
TC._node_res.update({"2": "C", "3": "B", "9": "A"})        # A chờ C (node 2) rồi B (node 3); B chờ A (node 9)
_old = _t.monotonic() - 100
for a in ("A", "B"):
    TC._registered[a]["last_progress_ts"] = _old
cyc = TC.find_stall_cycles(25.0)
check(any(set(c) == {"A", "B"} for c in cyc), f"vòng A↔B được nhận ra dù xe chặn đầu của A là C (không bí): {cyc}")

# ── Block đơn: xe đứng chung block không được khoá cả block cướp node của nhau (SIM01@20 ↔ SIM03@19, 2026-11-02) ──
reset(); TC._node_res.clear(); TC._edge_res.clear()
TC._block_cfg_src = id(getattr(mc.map_manager, "node_actions", None))   # chặn nạp lại cấu hình block
TC._block_of_node = {n: "auto_18" for n in ("18", "19", "20")}
TC._block_nodes = {"auto_18": {"18", "19", "20"}}
TC._block_type = {"auto_18": "single"}
put("SIM01", "20", ["20", "21", "34"]); put("SIM03", "19", ["19", "20", "21", "22"])
TC.reserve_ahead("SIM03")
check(TC._node_res.get("20") != "SIM03" and TC._node_res.get("21") != "SIM03",
      f"SIM03 (đứng sau) không cướp 20/21 của SIM01 đang đứng ở 20: {dict(TC._node_res)}")
TC.reserve_ahead("SIM01")
check(TC._node_res.get("20") == "SIM01" and TC._node_res.get("21") == "SIM01",
      f"SIM01 (đứng trong block) vẫn giữ được 20 và 21: {dict(TC._node_res)}")
TC.reserve_ahead("SIM03")
check(TC._node_res.get("21") == "SIM01", "SIM03 reserve lại vẫn không cướp 21")

# ── Cùng đích, hoà khoảng cách, requester đứng trên đường claimer → requester đi trước (SIM06@28 ↔ SIM03@26, 2026-11-03) ──
import networkx as _nx
from types import SimpleNamespace as _NS
_g = _nx.Graph([("26", "28"), ("26", "29"), ("28", "29"), ("29", "30")])
H._routes["SIM03"] = _NS(full_path=["26", "28", "29", "30"])
H.state_store.get_or_create("SIM03").current_tag = "26"
check(mc.__dict__ is not None and H.__class__ is not None, "setup")
import line_agv_handler as _LH
check(_LH.requester_closer_than_claimer(_g, "28", "26", "30"),
      "hoà 2-2 nhưng SIM06@28 nằm trên đường 26→28→29→30 của SIM03 -> SIM06 đi trước")
check(not _LH.requester_closer_than_claimer(_g, "27", "26", "30"),
      "requester không nằm trên đường claimer và không gần hơn -> vẫn chờ")
H._routes.pop("SIM03", None)

# ── Chống A→B→A: vòng 2 nhánh, mỗi nhánh bị 1 xe khác giữ → xe không được lật về nhánh vừa bỏ (SIM02 39↔38/40, 2026-11-03) ──
import networkx as _nx2
import line_agv_handler as _LH2
_ring = _nx2.Graph()
for _a, _b in (("39", "38"), ("38", "37"), ("37", "18"), ("39", "40"), ("40", "15"), ("15", "16"), ("16", "17"), ("17", "18")):
    _ring.add_edge(_a, _b, weight=1.0)
_saved_lg = mc.map_manager.line_graph
mc.map_manager.line_graph = _ring
_sv = H.send_window_fn; H.send_window_fn = lambda a, p: None
try:
    reset(); TC._intent_route.clear(); H._reroute_ts.clear(); H._reroute_hist.clear(); H._reroute_left.clear()
    st = H.state_store.get_or_create("R1"); st.current_tag = "39"; st.driving = False
    TC._registered["R1"] = {"path": ["39", "38", "37", "18"], "current_idx": 0, "priority": 2, "last_progress_ts": __import__("time").monotonic() - 60}
    rt = _LH2.LineAGVRoute(full_path=["39", "38", "37", "18"], task_type="delivery", direction="fwd",
                           window_start=0, window_end=1, is_complete=False)
    H._routes["R1"] = rt
    TC._registered["X1"] = {"path": ["37", "38"], "current_idx": 0, "priority": 3}   # chặn nhánh 38-37
    ok1 = H._try_line_reroute("R1", st, rt, 0, require_worthwhile=True)
    check(ok1 and rt.full_path[1] == "40", f"lần 1: né X1, sang nhánh 40: {rt.full_path}")
    TC._registered.pop("X1", None); TC._registered["X2"] = {"path": ["15", "40"], "current_idx": 0, "priority": 3}  # giờ nhánh 40 bị chặn
    H._reroute_ts.clear()
    TC._registered["R1"]["path"] = list(rt.full_path)
    ok2 = H._try_line_reroute("R1", st, rt, 0, require_worthwhile=True)
    check(not ok2 and rt.full_path[1] == "40", f"lần 2: KHÔNG lật về nhánh 38 vừa bỏ, đứng chờ: {rt.full_path}")
    ok3 = H._try_line_reroute("R1", st, rt, 0, avoid_all=True)
    check(ok3 is True or ok3 is False, "reroute bắt buộc (avoid_all) không bị cổng này chặn bằng exception")
finally:
    mc.map_manager.line_graph = _saved_lg; H.send_window_fn = _sv
    for _d in (H._routes,):
        _d.pop("R1", None)

# ── Following: đường mới dôi quá FOLLOW_REROUTE_MAX_EXTRA node thì thà đứng chờ (SIM04/06 vòng +11 node, 2026-11-03) ──
_ring2 = _nx2.Graph()
_chain = ["a1", "a2", "a3", "a4", "a5", "a6", "a7", "a8"]          # đường ngắn tới đích, a4 bị xe khác giữ
for _u, _v in zip(_chain, _chain[1:]):
    _ring2.add_edge(_u, _v, weight=1.0)
for _u, _v in zip(["a2", "b1", "b2", "b3", "b4", "b5", "b6", "b7", "b8", "a6"][:-1], ["b1", "b2", "b3", "b4", "b5", "b6", "b7", "b8", "a6"]):
    _ring2.add_edge(_u, _v, weight=1.0)                           # đường vòng dôi ~6 node
mc.map_manager.line_graph = _ring2
H.send_window_fn = lambda a, p: None
try:
    def _mk():
        reset(); H._reroute_ts.clear(); H._reroute_hist.clear(); H._reroute_left.clear()
        st = H.state_store.get_or_create("F1"); st.current_tag = "a2"; st.driving = False
        TC._registered["F1"] = {"path": list(_chain), "current_idx": 1, "priority": 2}
        TC._registered["F2"] = {"path": ["a4", "a5"], "current_idx": 0, "priority": 3}
        H.state_store.get_or_create("F2").current_tag = "a4"; H.state_store.get_or_create("F2").driving = False
        rt = _LH2.LineAGVRoute(full_path=list(_chain), task_type="delivery", direction="fwd", window_start=1, window_end=2, is_complete=False)
        H._routes["F1"] = rt
        return st, rt
    st, rt = _mk()
    ok = H._try_line_reroute("F1", st, rt, 1, require_worthwhile=True, max_extra=3)
    check(not ok and rt.full_path == _chain, f"đường vòng dôi >3 node: KHÔNG đổi, đứng chờ ({rt.full_path[:6]})")
    st, rt = _mk()
    ok2 = H._try_line_reroute("F1", st, rt, 1, require_worthwhile=True, max_extra=12)
    check(ok2 and "b1" in rt.full_path, "cho phép dôi nhiều hơn (max_extra=12) thì vẫn đổi được (cơ chế vẫn hoạt động)")
finally:
    mc.map_manager.line_graph = _saved_lg; H.send_window_fn = _sv
    H._routes.pop("F1", None)

# ── Quyết định chờ / đổi đường theo THỜI GIAN (estimate_clear_wait_sec + max_extra_sec) ──
_LH3 = _LH2
mc.map_manager.line_graph = _ring2
try:
    reset()
    for _a in ("M1", "S1"):
        H.state_store.get_or_create(_a)
    H.state_store.get("M1").driving = True; H.state_store.get("S1").driving = False
    TC._registered["M1"] = {"path": ["a1", "a2", "a3", "a4", "a5", "a6", "a7", "a8"], "current_idx": 2, "priority": 2}
    TC._registered["S1"] = {"path": ["a3", "a4"], "current_idx": 0, "priority": 2}
    my = ["a4", "a5", "a6"]
    w_move = _LH3.estimate_clear_wait_sec("M1", my)
    w_park = _LH3.estimate_clear_wait_sec("S1", my)
    check(w_park == _LH3.STATIONARY_WAIT_SEC, f"xe chắn đứng yên → chờ lâu ({w_park}s)")
    check(w_move < w_park, f"xe chắn đang chạy rồi rời vùng → chờ ngắn hơn đỗ ({w_move:.0f}s < {w_park:.0f}s)")
    TC._registered["M1"]["path"] = ["a1", "a2", "a3", "a4", "a5"]       # đích của nó nằm trong vùng của mình → sẽ đỗ
    check(_LH3.estimate_clear_wait_sec("M1", my) == _LH3.STATIONARY_WAIT_SEC, "xe chắn chạy tới ĐỖ trong vùng của mình → coi như chờ lâu")
    check(_LH3.detour_allowance_sec(0.0) == _LH3.DETOUR_ALWAYS_OK_SEC and _LH3.detour_allowance_sec(40.0) > _LH3.detour_allowance_sec(10.0),
          "ngân sách đi vòng tăng theo thời gian chờ ước tính")
    _sv3 = H.send_window_fn; H.send_window_fn = lambda a, p: None
    def _mk3():
        reset(); H._reroute_ts.clear(); H._reroute_hist.clear(); H._reroute_left.clear()
        st = H.state_store.get_or_create("F1"); st.current_tag = "a2"; st.driving = False
        TC._registered["F1"] = {"path": list(_chain), "current_idx": 1, "priority": 2}
        TC._registered["F2"] = {"path": ["a4", "a5"], "current_idx": 0, "priority": 3}
        H.state_store.get_or_create("F2").current_tag = "a4"; H.state_store.get_or_create("F2").driving = False
        rt = _LH2.LineAGVRoute(full_path=list(_chain), task_type="delivery", direction="fwd", window_start=1, window_end=2, is_complete=False)
        H._routes["F1"] = rt
        return st, rt
    st, rt = _mk3()
    ok = H._try_line_reroute("F1", st, rt, 1, require_worthwhile=True, max_extra_sec=6.0)
    check(not ok and rt.full_path == _chain, "chờ ngắn (ngân sách 6s) mà vòng tốn thêm ~12s → ĐỨNG CHỜ")
    st, rt = _mk3()
    ok2 = H._try_line_reroute("F1", st, rt, 1, require_worthwhile=True, max_extra_sec=40.0)
    check(ok2 and "b1" in rt.full_path, "xe chắn đỗ lâu (ngân sách 40s) → ĐI VÒNG vì nhanh hơn chờ")
finally:
    mc.map_manager.line_graph = _saved_lg; H.send_window_fn = _sv3
    H._routes.pop("F1", None); reset()

# ── Block 1 làn: xe khác ĐỨNG VẬT LÝ trong block (đỗ, không có khoá) vẫn phải chặn xe vào sau (SIM04@73 / SIM03, 2026-11-04) ──
reset(); TC._node_res.clear(); TC._edge_res.clear()
TC._block_cfg_src = id(getattr(mc.map_manager, "node_actions", None))
TC._block_of_node = {n: "auto_27" for n in ("73", "27", "28")}
TC._block_nodes = {"auto_27": {"73", "27", "28"}}
TC._block_type = {"auto_27": "single"}
H.state_store.get_or_create("PK").current_tag = "73"; H.state_store.get_or_create("PK").driving = False   # xe đỗ, KHÔNG đăng ký route
check(TC._single_block_blocked_by_other("auto_27", "TR"), "xe đỗ ở 73 (trong block) → xe khác KHÔNG được vào block")
check(not TC._single_block_blocked_by_other("auto_27", "PK"), "chính xe đỗ đó thì không bị chặn bởi bản thân")
H.state_store.get_or_create("PK").current_tag = "29"
check(not TC._single_block_blocked_by_other("auto_27", "TR"), "xe đỗ rời khỏi block → xe khác vào được")
# Đỗ né: node nằm trong block 1 làn (xe chưa ở trong) xếp SAU node thường
_gp = _nx2.Graph()
for _u, _v in (("c0", "j1"), ("j1", "t1"), ("t1", "t2"), ("c0", "j2")):
    _gp.add_edge(_u, _v, weight=1.0)
mc.map_manager.line_graph = _gp
TC._block_of_node = {"t1": "auto_t", "t2": "auto_t"}; TC._block_nodes = {"auto_t": {"t1", "t2"}}; TC._block_type = {"auto_t": "single"}
reset(); H.state_store.get_or_create("YV").current_tag = "c0"
pk = TC.find_flexible_parking("YV", "c0", ["zz"], max_hops=3)
mc.map_manager.line_graph = _saved_lg
check(pk in ("j1", "j2"), f"đỗ né chọn node thường, không chui vào ngách cụt 1 làn t1/t2 (được {pk})")

raise SystemExit(1 if _fail else 0)
