"""Kiểm thử đi thang máy: floor_nav (lập chuỗi lệnh) + elevator_coordinator (máy trạng thái thang).
Chạy: python test_elevator.py   (không cần DB / MQTT — dùng bản đồ giả + thiết bị giả)."""
import sys
import types

import networkx as nx

import floor_nav
import elevator_coordinator as ec_mod

PASS = FAIL = 0


def check(name, cond, extra=None):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} :: {extra}")


class FakeMM:
    """Bản đồ 3 tầng: mỗi tầng 1 đường thẳng a-b-c-W-E (E = cabin cụt); thang E1 dừng cả 3 tầng,
    thang E2 chỉ nối F2<->F3."""
    def __init__(self):
        self.floors = [{"id": "F1", "name": "T1", "level": 1}, {"id": "F2", "name": "T2", "level": 2},
                       {"id": "F3", "name": "T3", "level": 3}]
        g = nx.DiGraph()
        self.node_floor = {}
        # F1: 1-2-3-4(W)-5(E1)   F2: 11-12-13-14(W)-15(E1)  16-17(E2, nhánh từ 13)   F3: 21-22-23-24(W)-25(E1) 26-27(E2)
        chains = {"F1": ["1", "2", "3", "4", "5"], "F2": ["11", "12", "13", "14", "15"], "F3": ["21", "22", "23", "24", "25"]}
        for f, ch in chains.items():
            for a, b in zip(ch, ch[1:]):
                g.add_edge(a, b); g.add_edge(b, a)
            for n in ch:
                self.node_floor[n] = f
        for f, (a, b, c) in {"F2": ("13", "16", "17"), "F3": ("23", "26", "27")}.items():
            g.add_edge(a, b); g.add_edge(b, a); g.add_edge(b, c); g.add_edge(c, b)
            for n in (b, c):
                self.node_floor[n] = f
        self.graph = self.line_graph = g
        self.elevators = [{"id": "E1", "name": "Thang 1"}, {"id": "E2", "name": "Thang 2"}]
        self.elev_nodes = {("E1", "F1"): "5", ("E1", "F2"): "15", ("E1", "F3"): "25",
                           ("E2", "F2"): "17", ("E2", "F3"): "27"}

    def line_shortest_path(self, a, b):
        try:
            return nx.shortest_path(self.line_graph, a, b)
        except Exception:
            return None


mm = FakeMM()

print("floor_nav")
check("multi_floor", floor_nav.multi_floor(mm))
check("floor_of", floor_nav.floor_of("12", mm) == "F2" and floor_nav.floor_of("27", mm) == "F3")
check("level", floor_nav.floor_level("F3", mm) == 3 and floor_nav.floor_id_of_level(2, mm) == "F2")
check("cùng tầng → không cần thang", floor_nav.plan_rides("F2", "F2", mm) == [])
check("plan 1 chuyến F1→F3 (E1)", floor_nav.plan_rides("F1", "F3", mm) == [("E1", "F1", "F3")], floor_nav.plan_rides("F1", "F3", mm))
check("elevator_floors E2", floor_nav.elevator_floors("E2", mm) == ["F2", "F3"])
steps = floor_nav.decompose("A", "1", "22", mm)
check("đường thẳng không ngã ba → đặt thang ngay (8 bước)", len(steps) == 8, steps)
check("bước 0 = ĐẶT thang (elev_book)", steps[0] == ("elev_book", "E1@F1"), steps[0])
check("bước 1 = go_to node chờ (4)", steps[1] == ("go_to", "4"), steps[1])
check("elev_call E1@F1", steps[2] == ("elev_call", "E1@F1"), steps[2])
check("vào cabin 5", steps[3] == ("go_to", "5"), steps[3])
check("elev_ride có node ra W_B=24", steps[4] == ("elev_ride", "E1@F1>F3#24"), steps[4])
check("ra tới 24", steps[5] == ("go_to", "24"), steps[5])
check("nhả thang", steps[6] == ("elev_release", "E1"), steps[6])
check("cuối cùng go_to đích", steps[7] == ("go_to", "22"), steps[7])
# tầng 2 có ngã ba ở 13 (nhánh 16-17) → điểm xếp hàng = 12 (nhánh NGAY TRƯỚC ngã ba, ngoài hành lang 13-14-15)
q = floor_nav.decompose("A", "11", "22", mm)
check("có ngã ba → đi tới điểm xếp hàng 12 trước, rồi mới đặt thang", q[0] == ("go_to", "12") and q[1] == ("elev_book", "E1@F2"), q[:3])
check("xe đứng ngay ngã ba → đặt thang luôn", floor_nav.decompose("A", "13", "22", mm)[0] == ("elev_book", "E1@F2"))
q2 = floor_nav.decompose("B", "11", "22", mm)
check("xe thứ 2 cùng đường: điểm xếp hàng đã có xe → đặt thang tại chỗ, không tranh", q2[0] == ("elev_book", "E1@F2"), q2[:2])
# xe tới sau khi điểm xếp hàng đã có xe: xe ở XA phải đi tới chỗ chờ SAU điểm xếp hàng rồi mới đặt thang (không đặt từ xa)
check("chỗ chờ sau điểm xếp hàng 23 = 22 (xe ở xa đi tới đó rồi mới đặt thang)", floor_nav._hold_behind(["21", "22", "23", "24", "25"], "23", mm) == "22")
check("xe đã sát sau điểm xếp hàng → không cần chỗ chờ thêm (đặt thang tại chỗ)", floor_nav._hold_behind(["21", "22", "23", "24", "25"], "22", mm) is None)
# 2 điểm xếp hàng khai báo thủ công ở 2 NHÁNH SONG SONG cùng dẫn vào node chờ (như node 6 và 28): xe sau phải sang điểm còn trống
import networkx as _nx_p
_gp = _nx_p.DiGraph()
for _a, _b in [("S", "Q1"), ("Q1", "J"), ("S", "Q2"), ("Q2", "R"), ("R", "J"), ("J", "W"), ("W", "C")]:
    _gp.add_edge(_a, _b); _gp.add_edge(_b, _a)
_mp = FakeMM(); _mp.line_graph = _mp.graph = _gp
_mp.line_shortest_path = lambda a, b, floor=None: _nx_p.shortest_path(_gp, a, b)
_mp.elev_queue = {("E1", "F1"): ["Q1", "Q2"]}
check("nhánh song song: điểm ngoài đường ngắn nhất cũng được xét",
      floor_nav._with_parallel_points(["Q1"], "S", "W", "E1", "F1", _mp) == ["Q1", "Q2"],
      floor_nav._with_parallel_points(["Q1"], "S", "W", "E1", "F1", _mp))
check("không nhận điểm xe đang đứng", floor_nav._with_parallel_points([], "Q2", "W", "E1", "F1", _mp) == ["Q1"])
check("parse_call", floor_nav.parse_call("E1@F1") == ("E1", "F1"))
check("parse_ride", floor_nav.parse_ride("E1@F1>F3#24") == ("E1", "F1", "F3", "24"))
# xe đã đứng ngay node chờ → bước đầu vẫn là go_to node chờ (tự hoàn tất vì đã ở đó)
check("xe ở sẵn node chờ", floor_nav.decompose("A", "4", "22", mm)[1] == ("go_to", "4"))
# xe đang trong cabin → từ chối
try:
    floor_nav.decompose("A", "5", "22", mm); check("xe trong cabin bị từ chối", False)
except ValueError:
    check("xe trong cabin bị từ chối", True)
# đổi thang: F1 → nhánh chỉ E2 phục vụ (node 17 ở F2 / 27 ở F3) — E1 không tới được node đó nhưng cùng tầng → đường
steps2 = floor_nav.decompose("A", "12", "26", mm)     # F2 → F3 : E1 hoặc E2 đều được (ít chuyến nhất, 1 chuyến)
check("F2→F3 1 chuyến", sum(1 for c, _ in steps2 if c == "elev_ride") == 1, steps2)
# không có thang
mm2 = FakeMM(); mm2.elev_nodes = {("E1", "F1"): "5"}
try:
    floor_nav.decompose("A", "1", "22", mm2); check("thiếu thang → ValueError", False)
except ValueError as e:
    check("thiếu thang → ValueError", "Không có thang" in str(e), str(e))
# 2 chuyến: thang A chỉ F1<->F2, thang B chỉ F2<->F3
mm3 = FakeMM(); mm3.elev_nodes = {("E1", "F1"): "5", ("E1", "F2"): "15", ("E2", "F2"): "17", ("E2", "F3"): "27"}
check("đổi thang: 2 chuyến", floor_nav.plan_rides("F1", "F3", mm3) == [("E1", "F1", "F2"), ("E2", "F2", "F3")],
      floor_nav.plan_rides("F1", "F3", mm3))
s3 = floor_nav.decompose("A", "1", "21", mm3)
check("chuỗi 2 chuyến có 2 elev_ride", [c for c, _ in s3].count("elev_ride") == 2, s3)

mmd = FakeMM(); mmd.floors[2]["level"] = 2     # F2 và F3 cùng số tầng
try:
    floor_nav.decompose("A", "1", "22", mmd); check("trùng số tầng → ValueError rõ ràng", False)
except ValueError as e:
    check("trùng số tầng → ValueError rõ ràng", "trùng" in str(e), str(e))
check("level_conflict", floor_nav.level_conflict("F3", mmd) == "T2" and floor_nav.level_conflict("F1", mmd) is None)

print("elevator_coordinator")
# Gắn bản đồ giả + thiết bị giả
fake_mc = types.SimpleNamespace(map_manager=mm, sent=[], located=[])
def _send_elev(eid, cmd, floor=None):
    fake_mc.sent.append((eid, cmd, floor)); return True
def _send_line(agv, cmd, **kw):
    fake_mc.located.append((agv, cmd, kw)); return True
fake_mc.send_elevator_command = _send_elev
fake_mc.send_line_command = _send_line
sys.modules["mqtt_client"] = fake_mc
# line_agv_handler giả (state_store)
class _St: pass
class _Store:
    def __init__(self): self.d = {}
    def get_or_create(self, a): return self.d.setdefault(a, _St())
    def get(self, a): return self.d.get(a)
fake_lah = types.SimpleNamespace(line_agv_handler=types.SimpleNamespace(state_store=_Store(), _set_alert=lambda *a, **k: None))
sys.modules["line_agv_handler"] = fake_lah
completed = []
class _Q:
    def on_agv_completed(self, agv, notes=""): completed.append((agv, notes))
    def cancel_all(self, agv): completed.append((agv, "CANCEL_ALL"))
sys.modules["task_queue"] = types.SimpleNamespace(agv_task_queue=_Q())

co = ec_mod.ElevatorCoordinator()
check("AGV1 đặt thang → được cấp ngay", co.book("E1", "F1", "AGV1") and completed[-1] == ("AGV1", "elevator_booked"), completed)
check("đặt thang chưa gửi lệnh gì tới thiết bị", not fake_mc.sent, fake_mc.sent)
check("xin thang tầng 1", co.request_open("E1", "F1", "AGV1"))
check("gửi open floor=1", fake_mc.sent[-1] == ("E1", "open", 1), fake_mc.sent[-1])
_n_c = len(completed)
co.on_state("E1", "opening", 1)
check("chưa mở thì chưa hoàn tất", len(completed) == _n_c)
co.on_state("E1", "open", 2)      # mở nhầm tầng → bỏ qua
check("open sai tầng bị bỏ qua", len(completed) == _n_c)
co.on_state("E1", "open", 1)
check("open đúng tầng → hoàn tất elev_call", completed[-1] == ("AGV1", "elevator_open"), completed)
# xe thứ 2 xin cùng lúc → xếp hàng
n_before = len(completed)
check("xe 2 đặt thang → xếp hàng (đứng yên chỗ cũ)", co.book("E1", "F1", "AGV2") and co._el["E1"].queue and co._el["E1"].owner == "AGV1")
check("AGV2 chưa được cấp", len(completed) == n_before)
# AGV1 đã vào cabin → đi tầng 3
check("start_ride", co.start_ride("E1", "F1", "F3", "24", "AGV1"))
check("gửi close trước", fake_mc.sent[-1] == ("E1", "close", None), fake_mc.sent[-1])
co.on_state("E1", "closing", 1)
co.on_state("E1", "closed", 1)
check("closed → gửi open floor=3", fake_mc.sent[-1] == ("E1", "open", 3), fake_mc.sent[-1])
co.on_state("E1", "moving", 2)
co.on_state("E1", "open", 3)
check("tới tầng 3 → hoàn tất elev_ride", completed[-1] == ("AGV1", "elevator_arrived"), completed[-1])
check("xe được đặt lại vị trí cabin tầng 3 (25), prev=24",
      fake_mc.located and fake_mc.located[-1][2] == {"tag": 25, "prev": 24}, fake_mc.located)
st = sys.modules["line_agv_handler"].line_agv_handler.state_store.get("AGV1")
check("state server cập nhật", st.current_tag == 25 and st.prev_tag == 24, (st.current_tag, st.prev_tag))
# AGV1 ra khỏi cabin → nhả → cấp cho AGV2
sent_n = len(fake_mc.sent)
co.release("E1", "AGV1")
check("nhả → cấp đặt trước cho AGV2 (chưa gọi cửa)", completed[-1] == ("AGV2", "elevator_booked") and co._el["E1"].owner == "AGV2" and len(fake_mc.sent) == sent_n, completed[-1])
co.request_open("E1", "F1", "AGV2")
check("AGV2 tới node chờ → gửi open floor=1", fake_mc.sent[-1] == ("E1", "open", 1), fake_mc.sent[-1])
co.on_state("E1", "open", 1)
check("AGV2 được mở", completed[-1] == ("AGV2", "elevator_open"), completed[-1])
# AGV2 ride rồi nhả khi không còn ai → đóng
co.start_ride("E1", "F1", "F2", "14", "AGV2")
co.on_state("E1", "closed", 1); co.on_state("E1", "open", 2)
co.release("E1", "AGV2")
check("hết xe → gửi close", fake_mc.sent[-1] == ("E1", "close", None) and co._el["E1"].owner is None, fake_mc.sent[-1])
# start_ride khi không giữ thang → từ chối
check("start_ride không giữ thang bị từ chối", not co.start_ride("E1", "F1", "F2", "14", "AGV9"))
# timeout / retry / lỗi
co2 = ec_mod.ElevatorCoordinator()
co2.book("E1", "F2", "AGV3")
co2.request_open("E1", "F2", "AGV3")
ec_mod.ELEV_OPEN_TIMEOUT = 0.0
n = len(fake_mc.sent)
co2.check_retries(); co2.check_retries()
check("gửi lại 2 lần", len(fake_mc.sent) - n == 2, fake_mc.sent[n:])
completed.clear()
co2.check_retries()
check("quá số lần → huỷ lệnh + nhả thang", completed and completed[-1] == ("AGV3", "CANCEL_ALL") and co2._el["E1"].owner is None, completed)
co3 = ec_mod.ElevatorCoordinator()
co3.book("E1", "F1", "AGV4"); co3.request_open("E1", "F1", "AGV4"); completed.clear()
co3.on_state("E1", "error", 1)
check("thiết bị báo lỗi → huỷ lệnh", completed and completed[-1][1] == "CANCEL_ALL", completed)
# đã mở sẵn đúng tầng → vào ngay
co4 = ec_mod.ElevatorCoordinator(); co4.on_state("E1", "open", 1); completed.clear()
co4.request_open("E1", "F1", "AGV5")
check("mở sẵn → vào ngay", completed and completed[-1] == ("AGV5", "elevator_open"), completed)
# booking mồ côi: chủ thang không còn lệnh thang nào → tự nhả sau 8s
class _Q2:
    def get_running(self, a): return None
    def get_queue(self, a): return []
    def on_agv_completed(self, agv, notes=""): completed.append((agv, notes))
    def cancel_all(self, agv): completed.append((agv, "CANCEL_ALL"))
sys.modules["task_queue"] = types.SimpleNamespace(agv_task_queue=_Q2())
co5 = ec_mod.ElevatorCoordinator(); co5.book("E1", "F1", "AGV6")
co5.check_retries()
check("lần đầu thấy mồ côi chỉ đánh dấu", co5._el["E1"].owner == "AGV6")
co5._el["E1"].stale_since -= 9
co5.check_retries()
check("mồ côi > 8s → tự nhả thang", co5._el["E1"].owner is None)
st_list = co4.status()
check("status", any(s["id"] == "E1" and s["owner"] == "AGV5" for s in st_list), st_list)

print("=" * 50)
print(f"KẾT QUẢ: {PASS} pass, {FAIL} fail")
sys.exit(1 if FAIL else 0)
