"""Test: chọn xe nhường đường khi cả hệ thống bí (_pick_stall_victim) + hướng riêng theo loại xe trong agv_scope.
Chạy: PYTHONIOENCODING=utf-8 python test_stall_typedir.py   (không cần DB/broker)."""
import networkx as nx

import main
from line_agv_handler import line_agv_handler as H, traffic_coordinator as TC
from mqtt_client import map_manager as MM

_pass = _fail = 0


def check(cond, msg):
    global _pass, _fail
    if cond:
        _pass += 1
        print("  PASS:", msg)
    else:
        _fail += 1
        print("  FAIL:", msg)


# ── Đồ thị: hành lang 1-2-3-4-5, nhánh chờ W nối 3 ──
g = nx.DiGraph()
for a, b in [("1", "2"), ("2", "3"), ("3", "4"), ("4", "5"), ("3", "W")]:
    g.add_edge(a, b, weight=1.0)
    g.add_edge(b, a, weight=1.0)
MM.graph = g
MM.line_graph = g
MM.node_actions = {"W": {"waiting_node": "yes"}}

print("[test] _pick_stall_victim: ưu tiên xe đang CHẶN nhiều xe nhất, không chỉ ưu tiên thấp nhất")
for a, tag in (("A", 2), ("B", 4), ("C", 5)):
    H.state_store.get_or_create(a).current_tag = tag
H.state_store.get_or_create("Z").current_tag = 1      # xe đứng ngoài vòng khoá
TC._registered["A"] = {"path": ["2", "3", "4"], "current_idx": 0, "priority": 2}
TC._registered["B"] = {"path": ["4", "3", "2"], "current_idx": 0, "priority": 2}
TC._registered["C"] = {"path": ["5", "4", "3"], "current_idx": 0, "priority": 2}   # đi qua 4 (B) và 3
TC._registered["Z"] = {"path": ["1"], "current_idx": 0, "priority": 1}              # ưu tiên THẤP nhất, không chặn ai
main._find_waiting_nodes = lambda: ["W"]
_orig_scope = MM.agv_scope
picked = main._pick_stall_victim(["A", "B", "C", "Z"], ["W"])
check(picked is not None and picked[0] == "B", f"chọn B (chặn A và C) thay vì Z (ưu tiên thấp nhưng không chặn ai): {picked}")

TC._registered["Z"] = {"path": ["1", "2"], "current_idx": 0, "priority": 1}
picked = main._pick_stall_victim(["Z", "B"], ["W"])
check(picked is not None, "vẫn chọn được khi nhóm bí nhỏ")

print("[test] hướng riêng theo loại xe: đường đi/neighbors trong agv_scope")
MM.edge_type_dirs = {("1", "2"): {"trailer": "forward"}, ("2", "3"): {"trailer": "forward"}}
MM._agv_type_of = staticmethod(lambda a: "trailer" if a == "TR" else "tow")
H.state_store.get_or_create("TR").current_tag = 3
with MM.agv_scope("TR"):
    gs = MM.line_graph
    check(not gs.has_edge("3", "2") and gs.has_edge("2", "3"), "rơ-moóc: cấm 3→2, cho phép 2→3")
    try:
        nx.shortest_path(gs, "3", "1")
        ok = False
    except nx.NetworkXNoPath:
        ok = True
    check(ok, "rơ-moóc không có đường ngược 3→1")
with MM.agv_scope("TOW"):
    check(MM.line_graph.has_edge("3", "2"), "xe thường vẫn đi 3→2")

print("[test] _nearest_of tính khoảng cách theo đường đi của loại xe")
MM.edge_type_dirs = {("3", "4"): {"trailer": "forward"}, ("4", "5"): {"trailer": "forward"}}
H.state_store.get_or_create("TR").current_tag = 5
# từ 5: rơ-moóc không đi ngược 5→4; tow đi được → candidate 4 gần với tow, rơ-moóc không tới được 4/1 (giữ candidate đầu)
check(main._nearest_of(["1", "4"], "5", "TOW") == "4", "xe thường: node gần nhất = 4")

print(f"\nKẾT QUẢ: {_pass} pass, {_fail} fail")
raise SystemExit(1 if _fail else 0)
