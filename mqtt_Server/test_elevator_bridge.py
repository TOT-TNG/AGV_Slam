"""Kiểm thử ElevatorBridge (backend uelev_v2) với thư viện elevator_coord + thiết bị thang giả (sim) và hàng đợi/xe giả.
Chạy: PYTHONIOENCODING=utf-8 python test_elevator_bridge.py   (không cần DB / broker)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import networkx as nx

import floor_nav
from elevator_bridge import AgvIO, ElevatorBridge
from elevator_coord import CoordinatorConfig
from elevator_coord.sim.world import World

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
    """3 tầng, mỗi tầng chuỗi a-b-c-W-cabin (cabin cụt), thang ELV01 dừng cả 3 tầng, số tầng 1/2/3."""
    def __init__(self):
        self.floors = [{"id": "F1", "name": "T1", "level": 1}, {"id": "F2", "name": "T2", "level": 2},
                       {"id": "F3", "name": "T3", "level": 3}]
        g = nx.DiGraph()
        self.node_floor = {}
        chains = {"F1": ["1", "2", "3", "4", "5"], "F2": ["11", "12", "13", "14", "15"],
                  "F3": ["21", "22", "23", "24", "25"]}
        for f, ch in chains.items():
            for a, b in zip(ch, ch[1:]):
                g.add_edge(a, b)
                g.add_edge(b, a)
            for n in ch:
                self.node_floor[n] = f
        self.graph = self.line_graph = g
        self.elevators = [{"id": "ELV01", "name": "Thang 1"}]
        self.elev_nodes = {("ELV01", "F1"): "5", ("ELV01", "F2"): "15", ("ELV01", "F3"): "25"}
        self.node_actions = {}

    def line_shortest_path(self, a, b):
        try:
            return nx.shortest_path(self.line_graph, a, b)
        except Exception:
            return None


mm = FakeMM()
floor_nav._mm = lambda: mm


class FakeIO(AgvIO):
    """Hàng đợi + xe giả. Điều khiển bởi Rig.drive()."""
    def __init__(self, rig):
        self.rig = rig
        self.q = {}
        self.run_cmd = {}
        self.log = []
        self.alerts = []
        self.sent_runs = []
        self.sent_stops = []
        self.sent_plans = []
        self.exit_state = []

    def complete(self, agv, notes):
        self.log.append((agv, "done", (self.run_cmd.get(agv) or ("?",))[0], notes))
        self.run_cmd[agv] = None
        if self.q.get(agv):
            nxt = self.q[agv].pop(0)
            self.run_cmd[agv] = nxt
            self.rig.dispatch(agv, nxt)

    def running(self, agv):
        c = self.run_cmd.get(agv)
        return {"command": c[0], "dest_node": c[1]} if c else None

    def queued(self, agv):
        return [{"command": c, "dest_node": a} for c, a in self.q.get(agv, [])]

    def cancel_queue(self, agv):
        self.q[agv] = []
        self.run_cmd[agv] = None
        self.log.append((agv, "cancel_all"))

    def insert_next(self, agv, command, dest_node):
        self.q.setdefault(agv, []).insert(0, (command, dest_node))

    def send_run(self, agv):
        self.sent_runs.append((agv, round(self.rig.world.clock.monotonic(), 1)))
        self.rig.on_run(agv)

    def send_stop(self, agv):
        self.sent_stops.append(agv)

    def send_plan(self, agv, steps):
        self.sent_plans.append((agv, list(steps)))

    def route_direction(self, agv):
        return "fwd"

    def finish_cabin_leg(self, agv, cab):
        run = self.running(agv)
        if run and run["command"] == "go_to" and run["dest_node"] == str(cab):
            self.complete(agv, "elev_cabin_reached")
            return True
        return False

    def sync_exit_state(self, agv, prev_node, direction):
        self.exit_state.append((agv, str(prev_node), direction))

    def alert(self, agv, code, msg):
        self.alerts.append((agv, code, msg))

    def agv_tag(self, agv):
        return self.rig.agvs[agv]["tag"]

    def agv_available(self, agv):
        return self.rig.agvs[agv]["online"]

    def pending_cmd(self, agv):
        return None


class Rig:
    def __init__(self, **world_kw):
        self.world = World(**world_kw)                     # cấu hình mặc định: ELV01, tầng 1/2/3
        self.world.run_coord = False                       # coordinator của World không chạy — dùng bridge
        self.cfg = CoordinatorConfig.from_dict({
            "factory": self.world.factory,
            "elevators": [{"id": "ELV01", "floors": [1, 2, 3], "master": "master",
                           "callers": {"1": {"device": "call1", "directions": ["UP"]},
                                       "2": {"device": "call2", "directions": ["UP", "DN"]},
                                       "3": {"device": "call3", "directions": ["DN"]}},
                           "zones": [], "allowed_routes": "all"}]})
        self.io = FakeIO(self)
        self.bridge = ElevatorBridge(transport=self.world.broker.client("fms-bridge"), clock=self.world.clock,
                                     io=self.io, config=self.cfg, autostart_thread=False)
        self.world.extra_ticks.append(self.bridge.tick)
        self.agvs = {}
        self.moves = []          # (due, agv, tag, kind)
        self.bridge._ensure()
        self.world.run(3.0)
        self.plans = {}

    def add_agv(self, agv, tag):
        self.agvs[agv] = {"tag": tag, "online": True}

    def start_chain(self, agv, dest):
        steps = floor_nav.decompose(agv, self.agvs[agv]["tag"], dest, mm)
        self.io.q[agv] = list(steps[1:])
        self.io.run_cmd[agv] = steps[0]
        self.dispatch(agv, steps[0])
        return steps

    def now(self):
        return self.world.clock.monotonic()

    def dispatch(self, agv, cmd):
        c, a = cmd
        b = self.bridge
        if c == "elev_book":
            e, f = floor_nav.parse_call(a)
            if not b.book(e, f, agv):
                self.io.cancel_queue(agv)
        elif c == "elev_call":
            e, f = floor_nav.parse_call(a)
            b.request_open(e, f, agv)
        elif c == "elev_ride":
            e, fa, fb, wb = floor_nav.parse_ride(a)
            b.start_ride(e, fa, fb, wb, agv)
        elif c == "elev_release":
            b.release(a, agv)
            self.io.complete(agv, "released")
        elif c == "go_to":
            if self.agvs[agv]["tag"] == a:
                self.io.complete(agv, "already")
            else:
                self.moves.append((self.now() + 2.0, agv, a, "goto"))

    def on_run(self, agv):
        """`run` tới xe: nếu xe đang chờ ở thẻ cabin → lùi ra thẻ thoát theo đuôi plan (mất 2 s)."""
        ctx = self.bridge._ctx.get(agv)
        if ctx and self.agvs[agv]["tag"] == ctx.cab_a and ctx.exit_allowed:
            self.moves.append((self.now() + 2.0, agv, ctx.w_b, "exit"))

    def drive(self):
        now = self.now()
        for m in list(self.moves):
            due, agv, tag, kind = m
            if now < due:
                continue
            self.moves.remove(m)
            ctx = self.bridge._ctx.get(agv)
            if kind == "goto":
                if ctx and ctx.tail and tag == ctx.cab_a:
                    plan = {"c": "plan", "id": "p1", "d": [{"t": int(ctx.cab_a) - 1, "a": 7, "v": 0},
                                                           {"t": int(ctx.cab_a), "a": 1, "v": 0}]}
                    self.plans[agv] = self.bridge.plan_tail(agv, plan)
                self.agvs[agv]["tag"] = tag
                self.bridge.on_agv_state(agv, tag, False)
                run = self.io.running(agv)
                if run and run["command"] == "go_to" and run["dest_node"] == tag:
                    self.io.complete(agv, "arrived")
            else:                                           # exit
                self.agvs[agv]["tag"] = tag
                self.bridge.on_agv_state(agv, tag, False)

    def step(self, dt=0.1):
        self.world.step(dt)
        self.drive()

    def run_until(self, pred, timeout=400.0):
        for _ in range(int(timeout / 0.1)):
            if pred():
                return True
            self.step()
        return pred()


# ══════════════════════════════════════════════════════════════════════════════
print("1 xe F1 → F3")
rig = Rig()
rig.add_agv("A", "1")
steps = rig.start_chain("A", "22")
check("chuỗi bắt đầu bằng elev_book", steps[0][0] == "elev_book", steps)
ok = rig.run_until(lambda: rig.agvs["A"]["tag"] == "22" and rig.io.run_cmd.get("A") is None)
check("xe tới được đích 22 ở tầng 3", ok, (rig.agvs, rig.io.log[-6:]))
done = [x[2] for x in rig.io.log if x[1] == "done"]
check("thứ tự lệnh hoàn tất đúng chuỗi", done[:5] == ["elev_book", "go_to", "elev_call", "go_to", "elev_ride"], done)
tail = [(s["t"], s["a"]) for s in rig.plans.get("A", {}).get("d", [])]
check("plan tới cabin được NỐI ĐUÔI (chờ → đổi chiều → chạy → thẻ thoát 24)",
      tail[-4:] == [(5, 21), (5, 8), (5, 3), (24, 1)], tail)
check("sau khi ra: prev_tag = cabin tầng đích (25), hướng ra = lùi", rig.io.exit_state == [("A", "25", "bwd")],
      rig.io.exit_state)
check("không có cảnh báo lỗi thang", rig.io.alerts == [], rig.io.alerts)
check("run gửi đúng 1 lần cho EXIT_ALLOWED", len(rig.io.sent_runs) == 1, rig.io.sent_runs)
rig.world.run(20)
check("thiết bị thang nhả hết relay sau chuyến", rig.world.outputs_idle())
check("ctx đã dọn", "A" not in rig.bridge._ctx, list(rig.bridge._ctx))

print("2 xe cùng lúc: xe tới trước đi trước, xe sau chờ")
rig = Rig()
rig.add_agv("A", "1")
rig.add_agv("B", "2")
rig.start_chain("A", "22")
rig.world.run(0.5)
rig.start_chain("B", "23")
ok = rig.run_until(lambda: all(rig.agvs[a]["tag"] == t and rig.io.run_cmd.get(a) is None
                               for a, t in (("A", "22"), ("B", "23"))))
check("cả hai xe tới đích", ok, (rig.agvs, rig.io.alerts, rig.io.log[-6:]))
order = [x[0] for x in rig.io.log if x[1] == "done" and x[2] == "elev_ride"]
check("A (đặt trước) được chở trước B", order == ["A", "B"], order)
check("không lỗi", rig.io.alerts == [], rig.io.alerts)

print("Cabin mất mạng khi đóng cửa (Master + xe offline suốt chuyến)")
rig = Rig()
rig.add_agv("A", "1")
rig.start_chain("A", "22")
state = {"down": False}


def cabin_net():
    ctx = rig.bridge._ctx.get("A")
    if ctx and ctx.boarded and not ctx.exited and not state["down"] and rig.world.car.door in ("CLOSING", "CLOSED"):
        state["down"] = True
        rig.world.master.net_down()
        rig.agvs["A"]["online"] = False
    if state["down"] and rig.world.car.door == "OPEN" and not rig.world.car.moving:
        state["down"] = False
        rig.world.master.net_up()
        rig.agvs["A"]["online"] = True


rig.world.extra_ticks.append(cabin_net)
ok = rig.run_until(lambda: rig.agvs["A"]["tag"] == "22" and rig.io.run_cmd.get("A") is None)
check("vẫn hoàn tất khi cabin mất mạng giữa chuyến", ok, (rig.agvs, rig.io.alerts, rig.io.log[-6:]))
check("không báo lỗi", rig.io.alerts == [], rig.io.alerts)

print("Yêu cầu không hợp lệ")
rig = Rig()
rig.add_agv("A", "1")
check("book tầng đích lạ → False", rig.bridge.book("ELV01", "F1>F9", "A") is False)

# ══════════════════════════════════════════════════════════════════════════════
# KHÓA VÙNG THANG: xe sau chỉ được gọi khi xe trước đã đi QUA mốc thoát; FIFO giữa các tầng
# ══════════════════════════════════════════════════════════════════════════════
import elevator_bridge as EB


def spy(rig):
    """Ghi lại sự kiện thư viện + mọi state xe (thời gian mô phỏng)."""
    evs, states = [], []
    orig_ev, orig_st = rig.bridge._on_event, rig.bridge.on_agv_state

    def on_ev(ev):
        evs.append((rig.now(), ev.type.value, ev.agv_id))
        orig_ev(ev)

    def on_st(agv, tag, driving=False):
        states.append((rig.now(), agv, str(tag)))
        orig_st(agv, tag, driving)
    rig.bridge._on_event, rig.bridge.on_agv_state = on_ev, on_st
    return evs, states


def when(evs, typ, agv):
    return next((t for t, k, a in evs if k == typ and a == agv), None)


print("Khóa vùng: xe B chỉ được gọi SAU khi xe A đi qua mốc thoát (không phải ngay khi A chạm node thoát)")
rig = Rig()
evs, states = spy(rig)
rig.add_agv("A", "1")
rig.add_agv("B", "11")
rig.start_chain("A", "22")
rig.world.run(0.5)
rig.start_chain("B", "23")
ok = rig.run_until(lambda: all(rig.agvs[a]["tag"] == t and rig.io.run_cmd.get(a) is None
                               for a, t in (("A", "22"), ("B", "23"))), timeout=600)
check("cả hai xe tới đích", ok, (rig.agvs, rig.io.alerts))
t_exit = next((t for t, a, tag in states if a == "A" and tag == "24"), None)          # A chạm node thoát
t_pass = next((t for t, a, tag in states if a == "A" and tag not in ("24", "25") and t_exit and t > t_exit), None)
t_b = when(evs, "STARTED", "B")
check("A có chạm node thoát rồi đi qua mốc", t_exit is not None and t_pass is not None, (t_exit, t_pass))
check("B chỉ được cấp lượt (gọi thang) SAU khi A đi qua mốc thoát", t_b is not None and t_pass is not None and t_b >= t_pass,
      (t_exit, t_pass, t_b))
check("khoảng chờ có thật: B cấp lượt muộn hơn lúc A hoàn tất chuyến", t_b - when(evs, "COMPLETED", "A") >= 1.0,
      (t_b, when(evs, "COMPLETED", "A")))
check("khóa đã nhả sau khi xong", rig.bridge._coord.snapshot()["elevators"][0]["area_hold"] is None
      and not rig.bridge._areas, rig.bridge._areas)
check("không lỗi", rig.io.alerts == [], rig.io.alerts)

print("FIFO giữa nhiều tầng: C(T3) → D(T2) → E(T1) gọi lần lượt, thang phục vụ đúng thứ tự đặt")
rig = Rig()
rig.add_agv("C", "21")
rig.add_agv("D", "11")
rig.add_agv("E", "1")
rig.start_chain("C", "2")
rig.world.run(0.5)
rig.start_chain("D", "3")
rig.world.run(0.5)
rig.start_chain("E", "22")
ok = rig.run_until(lambda: all(rig.agvs[a]["tag"] == t and rig.io.run_cmd.get(a) is None
                               for a, t in (("C", "2"), ("D", "3"), ("E", "22"))), timeout=900)
order = [x[0] for x in rig.io.log if x[1] == "done" and x[2] == "elev_ride"]
check("cả 3 xe tới đích", ok, (rig.agvs, rig.io.alerts, rig.io.log[-5:]))
check("thứ tự chở = thứ tự đặt thang (FIFO): C, D, E", order == ["C", "D", "E"], order)
check("không lỗi", rig.io.alerts == [], rig.io.alerts)

print("Huỷ ride của xe đầu khi chưa vào cabin → khóa nhả ngay, xe sau không bị kẹt")
rig = Rig()
evs, states = spy(rig)
rig.add_agv("A", "1")
rig.add_agv("B", "11")
rig.start_chain("A", "22")
rig.world.run(0.3)
rig.start_chain("B", "23")
rig.run_until(lambda: rig.bridge._ctx.get("A") is not None and rig.bridge._ctx["A"].started)
rig.bridge.release("ELV01", "A")                       # chuỗi của A bị huỷ giữa chừng (chưa vào cabin)
rig.io.cancel_queue("A")
ok = rig.run_until(lambda: rig.agvs["B"]["tag"] == "23" and rig.io.run_cmd.get("B") is None, timeout=600)
check("B vẫn tới đích sau khi A huỷ", ok, (rig.agvs, rig.io.alerts, rig.io.log[-5:]))
check("khóa không còn giữ", rig.bridge._coord.snapshot()["elevators"][0]["area_hold"] is None)

print("Xe đứng im ở node thoát (không đi tiếp): quá timeout → tự nhả + cảnh báo; xe sau được gọi")
EB.AREA_CLEAR_TIMEOUT_S = 6.0
rig = Rig()
evs, states = spy(rig)
rig.world.extra_ticks.append(rig.bridge.check_retries)
rig.add_agv("A", "1")
rig.add_agv("B", "11")
rig.start_chain("A", "24")                             # đích = node thoát → A dừng hẳn ở đó
rig.world.run(0.5)
rig.start_chain("B", "23")
ok = rig.run_until(lambda: rig.agvs["B"]["tag"] == "23" and rig.io.run_cmd.get("B") is None, timeout=900)
t_exit = next((t for t, a, tag in states if a == "A" and tag == "24"), None)
t_b = when(evs, "STARTED", "B")
check("B cuối cùng vẫn tới đích", ok, (rig.agvs, rig.io.alerts, rig.io.log[-5:]))
check("B bị giữ ≥ timeout (6s) kể từ lúc A chạm node thoát", t_exit is not None and t_b is not None and t_b - t_exit >= 5.5,
      (t_exit, t_b))
check("có cảnh báo ELEVATOR_AREA_TIMEOUT cho A", any(c == "ELEVATOR_AREA_TIMEOUT" for _a, c, _m in rig.io.alerts), rig.io.alerts)

print("Nhả khóa thủ công khi xe kẹt ở hành lang")
EB.AREA_CLEAR_TIMEOUT_S = 900.0
rig = Rig()
evs, states = spy(rig)
rig.add_agv("A", "1")
rig.add_agv("B", "11")
rig.start_chain("A", "24")
rig.world.run(0.5)
rig.start_chain("B", "23")
rig.run_until(lambda: rig.agvs["A"]["tag"] == "24" and rig.io.run_cmd.get("A") is None, timeout=600)
rig.world.run(15)
check("A kẹt ở node thoát → B chưa được gọi", when(evs, "STARTED", "B") is None, evs[-4:])
t_rel = rig.now()
check("nhả tay trả True", rig.bridge.release_area_manual("ELV01") is True)
ok = rig.run_until(lambda: when(evs, "STARTED", "B") is not None, timeout=60)
check("sau khi nhả tay B được cấp lượt ngay", ok and when(evs, "STARTED", "B") - t_rel < 3.0, (t_rel, when(evs, "STARTED", "B")))
EB.AREA_CLEAR_TIMEOUT_S = 90.0

print("floor_nav.exit_corridor")
import networkx as nx2
g = nx2.Graph()
g.add_edges_from([("C", "W"), ("W", "X"), ("X", "J"), ("J", "P"), ("J", "Q")])     # cabin C → W → X → ngã ba J
mm_j = types_ns = type("M", (), {})()
mm_j.line_graph = g
check("hành lang tới ngã ba đầu tiên (gồm cả ngã ba)", floor_nav.exit_corridor("C", "W", mm_j) == ["C", "W", "X", "J"],
      floor_nav.exit_corridor("C", "W", mm_j))
g2 = nx2.Graph()
g2.add_edges_from([("C", "W"), ("W", "X"), ("X", "Y")])
mm_j.line_graph = g2
check("không có ngã ba → chỉ {cabin, node thoát}", floor_nav.exit_corridor("C", "W", mm_j) == ["C", "W"],
      floor_nav.exit_corridor("C", "W", mm_j))
g3 = nx2.Graph()
g3.add_edges_from([("C", "W"), ("W", "P"), ("W", "Q")])                              # node thoát chính là ngã ba
mm_j.line_graph = g3
check("node thoát là ngã ba → {cabin, node thoát}", floor_nav.exit_corridor("C", "W", mm_j) == ["C", "W"],
      floor_nav.exit_corridor("C", "W", mm_j))

print("Chỉ gọi Bộ gọi tầng khi xe TỚI node chờ (không gọi từ xa)")
rig = Rig()
rig.add_agv("A", "1")
rig.start_chain("A", "22")
unit = rig.bridge._coord.units["ELV01"]
ok = rig.run_until(lambda: unit.active is not None, timeout=30)
rig.world.run(1.0)
ctx = rig.bridge._ctx.get("A")
check("tới lượt nhưng xe chưa tới node chờ → chưa gọi Bộ gọi tầng", ok and unit.active is not None and unit.active.state.value == "CALLING_HALL"
      and "hall" not in unit.active.cmds and not unit.active.agv_ready, (unit.active and unit.active.state, unit.active and unit.active.cmds))
ok = rig.run_until(lambda: unit.active is not None and "hall" in unit.active.cmds, timeout=120)
check("xe tới node chờ (elev_call) → mới gọi Bộ gọi tầng", ok and bool(ctx and ctx.waiting_call), (ctx and ctx.waiting_call,))

print("Xe đứng ở cabin khi `run` không có tác dụng → gửi PLAN mới ra thẻ thoát")
rig = Rig()
rig.add_agv("A", "1")
rig.on_run = lambda agv: None                           # firmware không thoát WAIT_SYS bằng run
rig.start_chain("A", "22")
ctx_a = None
ok = rig.run_until(lambda: (lambda c: bool(c and c.exit_allowed and rig.agvs["A"]["tag"] == c.cab_a))(rig.bridge._ctx.get("A")), timeout=300)
rig.bridge._ctx["A"].last_run_at -= 100                # bridge dùng đồng hồ thật (time.monotonic), không phải đồng hồ mô phỏng
for _ in range(4):                                     # xe vẫn báo thẻ cabin (state mỗi vài giây)
    rig.world.run(4)
    rig.bridge.on_agv_state("A", rig.bridge._ctx["A"].cab_a, False)
ctx_a = rig.bridge._ctx.get("A")
check("xe tới cabin, tầng đích mở cửa", ok and ctx_a is not None and ctx_a.exit_allowed)
check("đã gửi lại run rồi gửi PLAN độc lập cabin → thẻ thoát", len(rig.io.sent_plans) >= 1 and rig.io.sent_plans[0][0] == "A", rig.io.sent_plans[:1])
if rig.io.sent_plans:
    stp = rig.io.sent_plans[0][1]
    check("plan ra bắt đầu bằng DIR và kết thúc WAIT_SYS ở thẻ thoát",
          stp[0]["a"] in (7, 8) and stp[-1]["a"] == 1 and str(stp[-1]["t"]) == str(ctx_a.w_b), stp)

print("Chuỗi thang khởi động từ lệnh go_charge: đặt thang xong phải hoàn tất lệnh go_charge để hàng đợi chạy tiếp")
rig = Rig()
rig.add_agv("A", "1")
steps = floor_nav.decompose("A", "1", "22", mm)
rig.io.q["A"] = list(steps[1:])
rig.io.run_cmd["A"] = ("go_charge", None)               # bước đầu (elev_book) chạy BÊN TRONG lệnh go_charge đang chạy
rig.dispatch("A", steps[0])
ok = rig.run_until(lambda: any(l[0] == "A" and l[1] == "done" and l[2] == "go_charge" for l in rig.io.log), timeout=60)
check("elevator_booked hoàn tất lệnh go_charge (không bị bỏ qua) → chuỗi chạy tiếp", ok, rig.io.log[-3:])

print("floor_nav: mốc thoát / điểm chờ khai báo thủ công")
mm_j.line_graph = g                                                   # C-W-X-J, J rẽ P/Q
mm_j.elev_exit = {("E1", "F2"): ["X"]}
mm_j.line_shortest_path = lambda a, b, floor=None: nx2.shortest_path(g, a, b)
check("mốc thoát thủ công: hành lang = cabin → trước mốc (mốc đã là ngoài hành lang)",
      floor_nav.exit_corridor("C", "W", mm_j, eid="E1", fid="F2") == ["C", "W"], floor_nav.exit_corridor("C", "W", mm_j, eid="E1", fid="F2"))
mm_j.elev_exit = {("E1", "F2"): ["P"]}
check("mốc xa hơn → hành lang dài hơn", floor_nav.exit_corridor("C", "W", mm_j, eid="E1", fid="F2") == ["C", "W", "X", "J"])
mm_j.elev_exit = {}
check("không khai báo → vẫn tự suy theo ngã ba", floor_nav.exit_corridor("C", "W", mm_j, eid="E1", fid="F2") == ["C", "W", "X", "J"])
mm_j.elev_queue = {}
check("chưa khai báo điểm chờ → None (dùng cách tự suy)", floor_nav._manual_queue_points(["S", "Q1", "Q2", "J", "W", "C"], "E1", "F1", mm_j) is None)
mm_j.elev_queue = {("E1", "F1"): ["Q1", "Q2", "ZZ"]}
check("điểm chờ thủ công trên đường: gần cabin nhất trước, bỏ node không nằm trên đường",
      floor_nav._manual_queue_points(["S", "Q1", "Q2", "J", "W", "C"], "E1", "F1", mm_j) == ["Q2", "Q1"])
check("xe đang đứng ở điểm chờ đó → không đi lại",
      floor_nav._manual_queue_points(["Q1", "Q2", "J", "W", "C"], "E1", "F1", mm_j) == ["Q2"])
check("đã khai báo nhưng đường không qua điểm nào → []",
      floor_nav._manual_queue_points(["S", "J", "W", "C"], "E1", "F1", mm_j) == [])
from elevator_coordinator import elevator_coordinator as _ecq
check("nhiều điểm chờ: xe 1 chiếm Q2, xe 2 phải đứng Q1",
      _ecq.claim_queue_point("EQ", "F1", "A", node="Q2") and not _ecq.claim_queue_point("EQ", "F1", "B", node="Q2")
      and _ecq.claim_queue_point("EQ", "F1", "B", node="Q1"))

print("11-tai-lieu-dev §6: ride FAILED (exit_timeout) khi xe CÒN TRONG CABIN → KHÔNG cho xe kế tiếp vào thang")
rig = Rig()
evs, states = spy(rig)
rig.add_agv("A", "1")
rig.add_agv("B", "11")
rig.on_run = lambda agv: None                         # xe A kẹt: không bao giờ ra khỏi cabin (thẻ thoát hỏng)
object.__setattr__(rig.bridge._coord.units["ELV01"].t, "exit_timeout_s", 20.0)
rig.start_chain("A", "22")
rig.world.run(0.5)
rig.start_chain("B", "23")
ok = rig.run_until(lambda: any(k == "FAILED" and a == "A" for _t, k, a in evs), timeout=600)
check("ride của A kết thúc FAILED (exit_timeout)", ok, evs[-6:])
rig.world.run(120)
snap = rig.bridge._coord.snapshot()["elevators"][0]
check("A còn trong cabin → khóa vùng thang vẫn giữ cho A", snap["area_hold"] and snap["area_hold"]["agv_id"] == "A", snap["area_hold"])
check("B KHÔNG được cấp lượt trong 120s sau khi ride của A lỗi", when(evs, "STARTED", "B") is None, evs[-4:])
check("có cảnh báo ELEVATOR_ERROR 'XE ĐANG TRONG CABIN' cho A",
      any(c == "ELEVATOR_ERROR" and "TRONG CABIN" in m for a, c, m in rig.io.alerts if a == "A"), rig.io.alerts)
check("ride lỗi khi xe còn TRONG CABIN → hàng đợi lệnh của xe KHÔNG bị xoá (xe online lại còn lệnh làm nốt)",
      (("A", "cancel_all")) not in rig.io.log, [x for x in rig.io.log if x[1] == "cancel_all"])
check("trang thái UI: áp dụng ghi chú 'xe còn trong cabin'", rig.bridge.status()[0].get("area_note") == "xe còn trong cabin",
      rig.bridge.status()[0].get("area_note"))
rig.bridge.on_agv_state("A", "24", False)               # xe A cuối cùng ra tới thẻ ngoài cabin (hoặc người vận hành đẩy ra)
ok = rig.run_until(lambda: when(evs, "STARTED", "B") is not None, timeout=120)
check("xe A đọc được thẻ ngoài cabin → khóa tự mở, B được cấp lượt", ok, evs[-4:])

print("Ride lỗi khi xe CHƯA vào cabin (vẫn online) → KHÔNG xoá hàng đợi, tự đặt lại thang rồi chạy tiếp tới đích")
rig = Rig()
rig.world.extra_ticks.append(rig.bridge.check_retries)
evs, states = spy(rig)
rig.add_agv("A", "1")
rig.start_chain("A", "22")
ok = rig.run_until(lambda: rig.bridge._ctx.get("A") is not None and rig.bridge._ctx["A"].waiting_call, timeout=120)
check("A tới node chờ, đang đợi cabin mở cửa (elev_call treo)", ok, rig.io.running("A"))
old_ride = rig.bridge._ctx["A"].ride_id
q_before = [c for c, _a in rig.io.q["A"]]
rig.bridge._coord.cancel_ride(old_ride, "test_fail", force=True)       # ride hỏng khi xe còn ở node chờ
rig.world.run(1.0)
check("hàng đợi của A KHÔNG bị xoá (không cancel_all)", ("A", "cancel_all") not in rig.io.log, rig.io.log[-3:])
check("các lệnh còn lại vẫn nằm trong hàng đợi", [c for c, _a in rig.io.q["A"]] == q_before, rig.io.q["A"])
check("đã đặt lịch thử lại", "A" in rig.bridge._retry, rig.bridge._retry)
check("xe KHÔNG bị dừng (không phải đang tiến vào cabin)", "A" not in rig.io.sent_stops, rig.io.sent_stops)
ok = rig.run_until(lambda: rig.agvs["A"]["tag"] == "22" and rig.io.run_cmd.get("A") is None, timeout=600)
check("sau khi đặt lại thang, A đi hết chuỗi tới đích 22", ok, (rig.agvs["A"], rig.io.run_cmd.get("A"), rig.io.q.get("A")))
check("chuyến thang cũ đã bị thay bằng chuyến mới", old_ride not in rig.bridge._by_ride)
check("không có lần cancel_all nào trong cả quá trình", ("A", "cancel_all") not in rig.io.log)

print("Ride lỗi khi xe đang OFFLINE ngoài cabin → chờ xe online lại mới đặt lại thang (không mất lệnh)")
rig = Rig()
rig.world.extra_ticks.append(rig.bridge.check_retries)
evs, states = spy(rig)
rig.add_agv("A", "1")
rig.start_chain("A", "22")
ok = rig.run_until(lambda: rig.bridge._ctx.get("A") is not None and rig.bridge._ctx["A"].waiting_call, timeout=120)
rig.agvs["A"]["online"] = False
rig.bridge._coord.cancel_ride(rig.bridge._ctx["A"].ride_id, "test_fail", force=True)
rig.world.run(30.0)
check("xe offline: hàng đợi còn nguyên, chưa đặt lại thang",
      ("A", "cancel_all") not in rig.io.log and "A" in rig.bridge._retry and (rig.io.running("A") or {}).get("command") == "elev_call",
      (rig.bridge._retry, rig.io.running("A")))
rig.agvs["A"]["online"] = True
ok = rig.run_until(lambda: rig.agvs["A"]["tag"] == "22" and rig.io.run_cmd.get("A") is None, timeout=600)
check("xe online lại → đặt lại thang và đi nốt tới đích", ok, (rig.agvs["A"], rig.io.run_cmd.get("A")))

print("Dispatch lệnh thang lỗi (vd đặt thang bị từ chối) → giữ hàng đợi, chèn lại đúng lệnh sau RIDE_RETRY_S")
rig = Rig()
rig.world.extra_ticks.append(rig.bridge.check_retries)
rig.add_agv("A", "1")
rig.io.run_cmd["A"] = None
rig.io.q["A"] = [("go_to", "6"), ("elev_ride", "ELV01@F1>F3#24"), ("elev_release", "ELV01")]
rig.bridge.retry_failed_command("A", "elev_book", "ELV01@F1")
rig.world.run(5.0)
check("chưa tới hạn: chưa chạy lại", rig.io.run_cmd.get("A") is None)
rig.world.run(8.0)
check("tới hạn: elev_book được chạy lại (đặt chuyến mới thành công) rồi chuỗi đi tiếp tới lệnh kế", rig.bridge._ctx.get("A") is not None and (rig.io.run_cmd.get("A") or ("",))[0] == "go_to", (rig.io.run_cmd.get("A"), rig.bridge._ctx.get("A")))
check("các lệnh phía sau vẫn còn nguyên trong hàng đợi", [c for c, _a in rig.io.q["A"]] == ["elev_ride", "elev_release"], rig.io.q["A"])


print("Thang CHƯA khởi tạo được (map chưa nạp sau khi server khởi động lại) → vẫn xử lý được lịch thử lại, không kẹt")
import time as _time
import elevator_bridge as _eb


class _StubIO(AgvIO):
    def __init__(self):
        self.calls = []

    def running(self, agv):
        return None

    def queued(self, agv):
        return []

    def insert_next(self, agv, command, dest_node):
        self.calls.append(("insert_next", agv, command, dest_node))

    def complete(self, agv, notes):
        self.calls.append(("complete", agv, notes))

    def agv_available(self, agv):
        return True


_old_retry_s = _eb.RIDE_RETRY_S
_eb.RIDE_RETRY_S = 0.1
_sio = _StubIO()
_b = ElevatorBridge(transport=Rig().world.broker.client("fms-x"), io=_sio, config=None, autostart_thread=False)
_b._build_config = lambda: None                            # map chưa nạp → không dựng được cấu hình thang
check("book thất bại vì chưa có cấu hình", _b._ensure() is False)
_b.retry_failed_command("A", "elev_book", "ELV01@F1")
_time.sleep(0.25)
_b.check_retries()
check("dù thang chưa khởi tạo, lệnh lỗi vẫn được chèn lại và chạy lại",
      ("insert_next", "A", "elev_book", "ELV01@F1") in _sio.calls and ("complete", "A", "elevator_cmd_retry") in _sio.calls, _sio.calls)
_eb.RIDE_RETRY_S = _old_retry_s


print("Server KHỞI ĐỘNG LẠI khi xe đang ĐI THANG (trong cabin) → nhận lại chuyến, thang đưa xe tới tầng đích, xe ra và đi nốt chuỗi")
rig = Rig()
rig.world.extra_ticks.append(rig.bridge.check_retries)
rig.add_agv("A", "1")
rig.start_chain("A", "22")


def _in_transit(rg):
    c = rg.bridge._ctx.get("A")
    return c is not None and c.boarded and rg.bridge._coord.get_ride(c.ride_id).state.value == "TRANSIT"


ok = rig.run_until(lambda: _in_transit(rig), timeout=300)
check("xe đã vào cabin, thang đang chạy (TRANSIT)", ok, rig.io.running("A"))
run = rig.io.running("A")
_eid, _fa, _fb, _wb = floor_nav.parse_ride(run["dest_node"])
old = rig.bridge
rig.world.extra_ticks[:] = [t for t in rig.world.extra_ticks if getattr(t, "__self__", None) is not old]
new = ElevatorBridge(transport=rig.world.broker.client("fms-bridge2"), clock=rig.world.clock, io=rig.io, config=rig.cfg,
                     autostart_thread=False)                       # "server mới": RAM trống, không còn ctx
rig.bridge = new
rig.world.extra_ticks += [new.tick, new.check_retries]
new._ensure()
check("server mới không còn biết chuyến cũ", not new.has_ctx("A"))
check("nhận lại chuyến của xe trong cabin", new.adopt_inside("A", _eid, _fa, _fb, _wb) is True, new._ctx.get("A"))
ok = rig.run_until(lambda: rig.agvs["A"]["tag"] == "22" and rig.io.run_cmd.get("A") is None, timeout=900)
check("thang đưa xe tới tầng đích, xe ra và đi nốt chuỗi tới đích 22", ok, (rig.agvs["A"], rig.io.run_cmd.get("A"), rig.io.q.get("A")))
check("hàng đợi không bị xoá", ("A", "cancel_all") not in rig.io.log)

print("Ride lỗi/huỷ khi xe còn TRONG CABIN → tự NHẬN LẠI chuyến sau RIDE_RETRY_S, xe ra khỏi cabin và đi nốt tới đích")
rig = Rig()
rig.world.extra_ticks.append(rig.bridge.check_retries)
rig.add_agv("A", "1")
rig.start_chain("A", "22")
ok = rig.run_until(lambda: _in_transit(rig), timeout=300)
rig.bridge._coord.cancel_ride(rig.bridge._ctx["A"].ride_id, "test_fail", force=True)
rig.world.run(1.0)
check("hàng đợi giữ nguyên, đã đặt lịch nhận lại chuyến", ("A", "cancel_all") not in rig.io.log
      and (rig.bridge._retry.get("A") or {}).get("kind") == "adopt", rig.bridge._retry)
ok = rig.run_until(lambda: rig.agvs["A"]["tag"] == "22" and rig.io.run_cmd.get("A") is None, timeout=900)
check("sau khi nhận lại chuyến, xe tới đích 22", ok, (rig.agvs["A"], rig.io.run_cmd.get("A"), rig.io.q.get("A"), rig.bridge._retry))
check("không có lần cancel_all nào", ("A", "cancel_all") not in rig.io.log)


print("Người vận hành HUỶ hàng đợi lúc xe đang đi thang rồi đưa xe ra TAY → chuyến mồ côi bị dọn, thang không bị giữ mãi")
rig = Rig()
rig.world.extra_ticks.append(rig.bridge.check_retries)
rig.add_agv("A", "1")
rig.start_chain("A", "22")


def _boarded_transit(rg):
    c = rg.bridge._ctx.get("A")
    return c is not None and c.boarded and rg.bridge._coord.get_ride(c.ride_id).state.value in ("TRANSIT", "ARRIVED", "EXITING")


ok = rig.run_until(lambda: _boarded_transit(rig), timeout=300)
check("xe đã lên cabin, chuyến đang chạy", ok)
old_ride = rig.bridge._ctx["A"].ride_id
rig.io.cancel_queue("A")                                   # người vận hành bấm huỷ hàng đợi
rig.agvs["A"]["tag"] = "1"                                 # rồi đưa xe ra tay (thẻ ngoài cabin)
rig.bridge.on_agv_state("A", "1", False)
rig.world.run(3.0)                                         # check_retries ghi mốc "không còn lệnh thang"
rig.bridge._ctx["A"].stale_since -= 100                    # bridge dùng đồng hồ thật (time.monotonic), không phải đồng hồ mô phỏng
rig.world.run(5.0)
snap = rig.bridge._coord.snapshot()["elevators"][0]
check("chuyến mồ côi bị huỷ, bridge không còn ctx", rig.bridge._ctx.get("A") is None, rig.bridge._ctx.get("A"))
check("thang rảnh, không còn khóa vùng cho A", not snap.get("area_hold") and not snap.get("active"), snap)

print("Chuyến cũ còn sót + người vận hành giao lệnh MỚI (elev_book cùng tầng) → đặt chuyến MỚI, không dùng lại chuyến cũ")
rig = Rig()
rig.world.extra_ticks.append(rig.bridge.check_retries)
rig.add_agv("A", "1")
rig.start_chain("A", "22")
ok = rig.run_until(lambda: _boarded_transit(rig), timeout=300)
old_ride = rig.bridge._ctx["A"].ride_id
rig.io.cancel_queue("A")
rig.agvs["A"]["tag"] = "1"
rig.bridge.on_agv_state("A", "1", False)                   # ra tay, nhưng NGAY sau đó giao lệnh mới (chưa kịp dọn mồ côi)
rig.start_chain("A", "23")                                 # chuỗi mới cũng bắt đầu bằng elev_book cùng tầng nguồn
rig.world.run(1.0)
c = rig.bridge._ctx.get("A")
check("đã đặt chuyến MỚI (ride id khác chuyến cũ)", c is not None and c.ride_id != old_ride, (c.ride_id if c else None, old_ride))
ok = rig.run_until(lambda: rig.agvs["A"]["tag"] == "23" and rig.io.run_cmd.get("A") is None, timeout=900)
check("xe đi hết chuỗi mới tới đích 23 (không treo ở elev_book)", ok, (rig.agvs["A"], rig.io.run_cmd.get("A"), rig.io.q.get("A")))

print(f"\nKẾT QUẢ: {PASS} pass, {FAIL} fail")
raise SystemExit(1 if FAIL else 0)
