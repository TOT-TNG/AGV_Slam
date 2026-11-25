"""Kiểm thử cabin thang DÙNG CHUNG (1 thẻ RFID cho mọi tầng): map_manager nhận diện + đường đi trong 1 tầng + floor_nav.
Chạy: python test_shared_cabin.py   (không cần DB / MQTT)."""
import networkx as nx

import floor_nav
from map_manager import MapManager

PASS = FAIL = 0


def check(name, cond, extra=None):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} :: {extra}")


def build(shared=True):
    """F1: 1-2-3(W)-100(cabin)   F2: 11-12-13(W)-100   F3: 21-22-23(W)-100 ; thang E1 = node 100."""
    mm = MapManager()
    g = nx.DiGraph()
    mm.node_floor = {}
    chains = {"F1": ["1", "2", "3"], "F2": ["11", "12", "13"], "F3": ["21", "22", "23"]}
    for f, ch in chains.items():
        for a, b in zip(ch, ch[1:]):
            g.add_edge(a, b, weight=1.0); g.add_edge(b, a, weight=1.0)
        for n in ch:
            mm.node_floor[n] = f
        w = ch[-1]
        g.add_edge(w, "100", weight=1.0); g.add_edge("100", w, weight=1.0)
    mm.node_floor["100"] = "F1"            # DB lưu 1 floor_id cho node cabin (tầng nào cũng được)
    mm.floors = [{"id": "F1", "name": "T1", "level": 1}, {"id": "F2", "name": "T2", "level": 2},
                 {"id": "F3", "name": "T3", "level": 3}]
    mm.elevators = [{"id": "E1", "name": "Thang 1"}]
    mm.graph = mm.line_graph = g
    mm.points = mm.line_points = {n: (float(i), 0.0) for i, n in enumerate(g.nodes)}
    mm.node_actions = {"100": {"elevator_id": "E1"}}
    mm.elev_nodes, mm.elev_wait, mm.shared_cabins = MapManager.derive_elevator_nodes(
        g, mm.node_actions, mm.node_floor, "F1")
    return mm


mm = build()
print("nhận diện cabin dùng chung")
check("shared_cabins", mm.shared_cabins == {"100"}, mm.shared_cabins)
check("elev_nodes trỏ cùng 1 node cho mọi tầng",
      mm.elev_nodes == {("E1", "F1"): "100", ("E1", "F2"): "100", ("E1", "F3"): "100"}, mm.elev_nodes)
check("elev_wait theo tầng", mm.elev_wait == {("E1", "F1"): "3", ("E1", "F2"): "13", ("E1", "F3"): "23"}, mm.elev_wait)
check("elevator_floors", floor_nav.elevator_floors("E1", mm) == ["F1", "F2", "F3"])
check("cabin cũ (mỗi tầng 1 node) vẫn được hiểu",
      MapManager.derive_elevator_nodes(
          nx.DiGraph([("1", "5"), ("5", "1"), ("11", "15"), ("15", "11")]),
          {"5": {"elevator_id": "E1"}, "15": {"elevator_id": "E1"}},
          {"1": "F1", "5": "F1", "11": "F2", "15": "F2"}, "F1")[0] == {("E1", "F1"): "5", ("E1", "F2"): "15"})

print("đường đi trong 1 tầng")
check("không đi xuyên tầng qua cabin", mm.line_shortest_path("1", "21") is None, mm.line_shortest_path("1", "21"))
check("cùng tầng bình thường", mm.line_shortest_path("1", "3") == ["1", "2", "3"])
check("tới cabin", mm.line_shortest_path("1", "100") == ["1", "2", "3", "100"])
check("từ cabin ra tầng 2 (ép theo node đích)", mm.line_shortest_path("100", "11") == ["100", "13", "12", "11"],
      mm.line_shortest_path("100", "11"))
check("cabin→cabin cần ép tầng", mm.line_shortest_path("100", "100", floor="F2") == ["100"])
check("directional: cabin → tầng 3 không rẽ sang tầng khác",
      mm.line_directional_path("100", "21", "23") == ["100", "23", "22", "21"], mm.line_directional_path("100", "21", "23"))
check("floor_of cabin = tầng hiện tại", floor_nav.floor_of("100", mm) == "F1")
floor_nav.set_cabin_floor("100", "F3", mm)
check("set_cabin_floor", floor_nav.floor_of("100", mm) == "F3")
floor_nav.set_cabin_floor("3", "F3", mm)       # node thường: bỏ qua
check("set_cabin_floor bỏ qua node thường", floor_nav.floor_of("3", mm) == "F1")
floor_nav.set_cabin_floor("100", "F1", mm)

print("floor_nav.decompose với cabin dùng chung")
steps = floor_nav.decompose("A", "1", "22", mm)
check("chuỗi lệnh", steps == [("elev_book", "E1@F1"), ("go_to", "3"), ("elev_call", "E1@F1"), ("go_to", "100"),
                              ("elev_ride", "E1@F1>F3#23"), ("go_to", "23"), ("elev_release", "E1"), ("go_to", "22")],
      steps)
check("cabin_a == cabin_b", floor_nav.cabin_node("E1", "F1", mm) == floor_nav.cabin_node("E1", "F3", mm) == "100")
check("wait_node", floor_nav.wait_node("E1", "F2", mm) == "13")
s2 = floor_nav.decompose("A", "12", "2", mm)
check("tầng 2 → tầng 1", ("elev_ride", "E1@F2>F1#3") in s2 and s2[-1] == ("go_to", "2"), s2)
try:
    floor_nav.decompose("A", "100", "22", mm); check("xe trong cabin bị từ chối", False)
except ValueError:
    check("xe trong cabin bị từ chối", True)

print("cạnh cửa cabin: cách ra (plan_cabin_exit)")
px = floor_nav.plan_cabin_exit
r = px("N", "N", "fwd")
check("cùng cạnh, vào tiến → lùi ra", r["exit_dir"] == "bwd" and r["turns"] == [] and r["kind"] == "reverse", r)
r = px("N", "N", "bwd")
check("cùng cạnh, vào lùi → tiến ra", r["exit_dir"] == "fwd" and r["turns"] == [], r)
r = px("N", "S", "fwd")
check("đối diện, vào tiến → tiến thẳng", r["exit_dir"] == "fwd" and r["turns"] == [] and r["kind"] == "straight", r)
r = px("N", "S", "bwd")
check("đối diện, vào lùi → lùi thẳng", r["exit_dir"] == "bwd" and r["turns"] == [] and r["kind"] == "straight", r)
# Vào tiến từ cửa Bắc: mũi hướng Nam. Cửa Đông ở bên TRÁI xe (xe quay mặt về Nam, đông nằm bên trái) → TURN_L
r = px("N", "E", "fwd")
check("cửa ra bên trái (vào tiến) → quay trái, tiến ra", r["exit_dir"] == "fwd" and r["turns"] == ["L"], r)
r = px("N", "W", "fwd")
check("cửa ra bên phải (vào tiến) → quay phải, tiến ra", r["exit_dir"] == "fwd" and r["turns"] == ["R"], r)
r = px("N", "E", "bwd")
check("vào lùi, cửa vuông góc → quay, giữ chiều lùi", r["exit_dir"] == "bwd" and len(r["turns"]) == 1, r)
check("rơ-moóc: đối diện OK", px("N", "S", "fwd", can_reverse=False, can_rotate_=False)["turns"] == [])
check("rơ-moóc: cùng cạnh → không ra được", px("N", "N", "fwd", can_reverse=False, can_rotate_=False) is None)
check("rơ-moóc: vuông góc → không ra được", px("N", "E", "fwd", can_reverse=False, can_rotate_=False) is None)
check("xe lùi được nhưng không quay: vuông góc không ra được", px("N", "E", "fwd", True, False) is None)
check("xe lùi được nhưng không quay: cùng cạnh vẫn lùi ra", px("N", "N", "fwd", True, False)["exit_dir"] == "bwd")

# Hướng quay xác nhận bằng mô phỏng hình học: quay q×90° CW từ heading rồi đi theo heading mới phải trúng cạnh cửa ra
ok = True
for di in "NESW":
    for do in "NESW":
        for d_in in ("fwd", "bwd"):
            r = px(di, do, d_in)
            if r is None:
                ok = False
                continue
            h = (floor_nav.DOORS.index(di) + (2 if d_in == "fwd" else 0)) % 4
            h = (h + {"R": 1, "L": 3}.get(r["turns"][0], 0) * 1 + (2 if len(r["turns"]) == 2 else 0)) % 4 if r["turns"] else h
            nose_to_door = h if r["exit_dir"] == "fwd" else (h + 2) % 4
            ok = ok and nose_to_door == floor_nav.DOORS.index(do)
check("mọi cặp cửa × hướng vào: xe quay xong đi đúng về cạnh cửa ra", ok)

print("cạnh cửa trong map + decompose theo loại xe")
mm.node_actions["100"] = {"elevator_id": "E1", "cabin_doors": {"F1": "N", "F2": "S", "F3": "E"}}
check("cabin_door", floor_nav.cabin_door("100", "F2", mm) == "S" and floor_nav.cabin_door("100", "F9", mm) == "")
e12 = floor_nav.cabin_exit_for("E1", "F1", "F2", "fwd", "A", mm)
check("F1→F2 (N→S) đi thẳng", e12["kind"] == "straight", e12)
e13 = floor_nav.cabin_exit_for("E1", "F1", "F3", "fwd", "A", mm)
check("F1→F3 (N→E) quay trái", e13["turns"] == ["L"], e13)
mm.node_actions["100"] = {"elevator_id": "E1"}
check("chưa khai báo cạnh → lùi ra như cũ", floor_nav.cabin_exit_for("E1", "F1", "F2", "fwd", "A", mm)["kind"] == "reverse")

import agv_registry as _ar
reg = _ar.agv_registry
reg._can_reverse["TOW1"] = False
try:
    floor_nav.decompose("TOW1", "1", "22", mm); check("xe không lùi + chưa khai báo cạnh → từ chối", False)
except ValueError as e:
    check("xe không lùi + chưa khai báo cạnh → từ chối", "không ra được cabin" in str(e), str(e))
mm.node_actions["100"] = {"elevator_id": "E1", "cabin_doors": {"F1": "N", "F2": "S", "F3": "N"}}
check("xe không lùi + cửa đối diện F1→F2 → đi được", len(floor_nav.decompose("TOW1", "1", "12", mm)) == 8)
try:
    floor_nav.decompose("TOW1", "1", "22", mm); check("xe không lùi + F1→F3 cùng cạnh → từ chối", False)
except ValueError:
    check("xe không lùi + F1→F3 cùng cạnh → từ chối", True)
reg._can_reverse.pop("TOW1", None)

print("toạ độ cabin theo tầng")
mm.node_actions["100"] = {"elevator_id": "E1", "cabin_facets": {"F2": {"x": 50.0, "y": 60.0}}}
mm.node_floor["100"] = "F1"
cx = MapManager.derive_cabin_xy({"100"}, mm.node_actions, mm.node_floor, {"100": (1.0, 2.0)})
check("derive_cabin_xy", cx == {"100": {"F1": (1.0, 2.0), "F2": (50.0, 60.0)}}, cx)
mm.cabin_xy = cx
floor_nav.set_cabin_floor("100", "F2", mm)
check("points[cabin] theo mặt tầng 2", mm.points["100"] == (50.0, 60.0) and mm.line_points["100"] == (50.0, 60.0), mm.points["100"])
floor_nav.set_cabin_floor("100", "F1", mm)
check("trở lại tầng 1", mm.points["100"] == (1.0, 2.0))

print("bridge.plan_tail theo cạnh cửa")
from elevator_bridge import ElevatorBridge, _Ctx
import elevator_bridge as eb


class _IO:
    def __init__(self, d): self.d = d
    def route_direction(self, agv): return self.d


def tail_for(doors, d_in, fa="F1", fb="F3"):
    mm.node_actions["100"] = {"elevator_id": "E1", "cabin_doors": doors} if doors else {"elevator_id": "E1"}
    floor_nav._mm = lambda: mm
    b = ElevatorBridge(transport=object(), io=_IO(d_in), autostart_thread=False)
    ctx = _Ctx(agv="A", eid="E1", fa=fa, fb=fb, ride_id="r", created=0.0, cab_a="100", cab_b="100", w_b="23", tail=True)
    b._ctx["A"] = ctx
    plan = {"c": "plan", "id": "p", "d": [{"t": 3, "a": 7, "v": 0}, {"t": 100, "a": 1, "v": 0}]}
    out = b.plan_tail("A", plan)
    return [(s["t"], s["a"]) for s in out["d"][2:]], ctx


t, c = tail_for(None, "fwd")
check("không khai báo: LIDAR_ON, DIR_BWD, RUN, thẻ thoát", t == [(100, 21), (100, 8), (100, 3), (23, 1)] and c.exit_dir == "bwd", t)
t, c = tail_for({"F1": "N", "F3": "S"}, "fwd")
check("đối diện: tiến thẳng", t == [(100, 21), (100, 7), (100, 3), (23, 1)] and c.exit_dir == "fwd", t)
t, c = tail_for({"F1": "N", "F3": "E"}, "fwd")
check("vuông góc trái: bước rẽ do plan builder dựng (DIR, LIDAR_OFF, TURN_L, LIDAR_ON, SPEED, RUN, thẻ thoát)",
      t == [(100, 7), (100, 20), (100, 6), (100, 21), (100, 4), (100, 3), (23, 1)] and c.exit_dir == "fwd", t)
t, c = tail_for({"F1": "N", "F3": "W"}, "fwd")
check("vuông góc phải: TURN_R", t[:3] == [(100, 7), (100, 20), (100, 5)], t)
t, c = tail_for({"F1": "N", "F3": "E"}, "bwd")
check("vào lùi + vuông góc: giữ chiều lùi (DIR_BWD), exit_dir=bwd, vẫn có TURN",
      c.exit_dir == "bwd" and t[0] == (100, 8) and (100, 6) in t and (100, 7) not in t, (t, c.exit_dir))
floor_nav._mm = lambda: mm

print(f"KẾT QUẢ: {PASS} pass, {FAIL} fail")
raise SystemExit(1 if FAIL else 0)
