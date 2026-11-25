"""Test: hàng đợi lệnh được LƯU DB kèm thứ tự và KHÔI PHỤC sau khi server khởi động lại; xe làm nốt lệnh dang dở.
Chạy: PYTHONIOENCODING=utf-8 python test_queue_restore.py   (không cần broker/DB: dòng DB giả, dispatch giả)."""
import time

import main as M
import mqtt_client as mc
import floor_nav
from line_agv_handler import line_agv_handler as H
import task_queue as TQ

_pass = _fail = 0


def check(cond, msg):
    global _pass, _fail
    if cond:
        _pass += 1
        print("  PASS:", msg)
    else:
        _fail += 1
        print("  FAIL:", msg)


Q = TQ.AGVTaskQueue()
dispatched = []
Q.dispatch_fn = lambda cmd: (dispatched.append((cmd.command, cmd.dest_node)) or True)
TQ.agv_task_queue = Q                      # main._kick_restored_queue import lại từ task_queue
import task_queue as _tq_mod
_tq_mod.agv_task_queue = Q

print("[test] thứ tự seq: append tăng dần, insert_next đứng trước")
c1, _ = Q.dispatch_or_queue("A1", "go_to", "10")             # xe rảnh → chạy ngay
c2, _ = Q.dispatch_or_queue("A1", "go_to", "20")             # xếp hàng
c3, _ = Q.dispatch_or_queue("A1", "go_to", "30")
n1 = Q.insert_next("A1", "go_charge")
n2 = Q.insert_next("A1", "go_wait")
order = [c.cmd_id for c in Q._queues["A1"]]
check(order == [n2.cmd_id, n1.cmd_id, c2.cmd_id, c3.cmd_id], "thứ tự trong deque đúng")
check(sorted(Q._queues["A1"], key=lambda c: c.seq) == list(Q._queues["A1"]), "sắp theo seq tái tạo đúng thứ tự hàng đợi")
check(n2.seq < n1.seq < c2.seq < c3.seq, "seq: lệnh chèn đầu nhỏ hơn, lệnh nối đuôi lớn hơn")

print("[test] khôi phục từ dòng DB (lệnh đang chạy dở nằm đầu)")
Q2 = TQ.AGVTaskQueue()
rows = [
    {"cmd_id": "r0", "agv_id": "AGVR", "command": "go_to", "dest_node": "17", "status": "running", "queued_at": 100.0,
     "session_id": "s1", "session_label": "L", "chain_leg": True, "start_node": None, "seq": 5.0},
    {"cmd_id": "r1", "agv_id": "AGVR", "command": "elev_ride", "dest_node": "ELV01@F1>F3#17", "status": "queued",
     "queued_at": 101.0, "session_id": "s1", "session_label": "L", "chain_leg": False, "start_node": None, "seq": 6.0},
    {"cmd_id": "r2", "agv_id": "AGVR", "command": "go_to", "dest_node": "21", "status": "queued", "queued_at": 102.0,
     "session_id": "s1", "session_label": "L", "chain_leg": False, "start_node": None, "seq": 7.0},
]
res = Q2.restore_from_rows(rows)
check(res == {"AGVR": 3}, "khôi phục 3 lệnh cho AGVR")
check([c.cmd_id for c in Q2._queues["AGVR"]] == ["r0", "r1", "r2"], "đúng thứ tự")
check(all(c.status == TQ.STATUS_QUEUED for c in Q2._queues["AGVR"]) and Q2._queues["AGVR"][0].chain_leg, "trạng thái queued, giữ cờ chain_leg")
check("AGVR" in Q2.restore_pending() and not Q2.is_busy("AGVR"), "chờ xe sẵn sàng (chưa chạy)")
check(Q2.restore_from_rows(rows) == {}, "không khôi phục đè lên hàng đợi đã có trong RAM")

print("[test] xe CHƯA sẵn sàng → chưa chạy")
mc.map_manager.elev_nodes = {("ELV01", "F1"): "7", ("ELV01", "F3"): "7"}
mc.map_manager.node_actions = dict(getattr(mc.map_manager, "node_actions", {}) or {})
mc.map_manager.node_actions["17"] = {"arrival_action": "wait_sys"}
mc.map_manager.node_actions["30"] = {}
st = H.state_store.get_or_create("AGVR")
mc._HELD_PLANS.clear()


def ready(tag, **kw):
    st.current_tag = tag
    st.connection_state = "ONLINE"
    st.last_update = time.time()
    st.online_streak = M.GHOST_ONLINE_STREAK
    st.driving = kw.get("driving", False)
    st.ghost = False
    st.real_state_seen = True
    st.task_lifecycle = kw.get("lifecycle")
    st.hook_pending = None
    H._routes.pop("AGVR", None)


ready(30, driving=True)
check(M._restored_queue_ready(H, "AGVR") is False, "đang chạy → chưa")
ready(30, lifecycle="picking")
check(M._restored_queue_ready(H, "AGVR") is False, "đang chờ xác nhận → chưa")
ready(30); st.online_streak = 0
check(M._restored_queue_ready(H, "AGVR") is False, "mới online 1 lượt → chưa (chống chập chờn)")
st.current_tag = None; st.online_streak = M.GHOST_ONLINE_STREAK
check(M._restored_queue_ready(H, "AGVR") is False, "chưa biết vị trí → chưa")
ready(30); st.real_state_seen = False
check(M._restored_queue_ready(H, "AGVR") is False, "vị trí chỉ là last_tag khôi phục từ DB (chưa có state thật) → chưa")
ready(30)
check(M._restored_queue_ready(H, "AGVR") is True, "online ổn định, đứng yên, biết vị trí → sẵn sàng")

print("[test] kick: chạy tiếp lệnh đang dang dở từ vị trí thật")
TQ.agv_task_queue = Q2; _tq_mod.agv_task_queue = Q2
Q2.dispatch_fn = lambda cmd: (dispatched.append((cmd.command, cmd.dest_node)) or True)
dispatched.clear()
ready(30)
M._kick_restored_queue(H, "AGVR")
check(dispatched and dispatched[0] == ("go_to", "17"), "dispatch lại lệnh đang dang dở (go_to 17)")
check(Q2.is_busy("AGVR") and "AGVR" not in Q2.restore_pending(), "hết trạng thái chờ khôi phục")
check([c.cmd_id for c in Q2._queues["AGVR"]] == ["r1", "r2"], "các lệnh còn lại giữ nguyên")

print("[test] lệnh đầu là elev_ride (ride cũ đã mất): xe ngoài cabin → gọi lại thang trước")
Q3 = TQ.AGVTaskQueue(); Q3.dispatch_fn = Q2.dispatch_fn
TQ.agv_task_queue = Q3; _tq_mod.agv_task_queue = Q3
Q3.restore_from_rows([dict(rows[1], status="running", seq=1.0), dict(rows[2], seq=2.0)])
dispatched.clear(); ready(30)
M._kick_restored_queue(H, "AGVR")
check(dispatched and dispatched[0] == ("elev_call", "ELV01@F1"), "chèn elev_call (đặt chuyến mới) chạy trước")
check([c.command for c in Q3._queues["AGVR"]] == ["elev_ride", "go_to"], "elev_ride và các lệnh sau vẫn còn")

print("[test] lệnh đầu là elev_ride mà xe đang TRONG cabin: không tự đoán, giữ nguyên hàng đợi + cảnh báo")
Q4 = TQ.AGVTaskQueue(); Q4.dispatch_fn = Q2.dispatch_fn
TQ.agv_task_queue = Q4; _tq_mod.agv_task_queue = Q4
Q4.restore_from_rows([dict(rows[1], status="running", seq=1.0), dict(rows[2], seq=2.0)])
dispatched.clear(); ready(7)
M._kick_restored_queue(H, "AGVR")
check(not dispatched and Q4.queue_size("AGVR") == 2 and "AGVR" not in Q4.restore_pending(), "không dispatch, hàng đợi còn 2 lệnh")
check((st.active_alert or {}).get("kind") == "ELEVATOR_ERROR", "đã đặt cảnh báo ELEVATOR_ERROR cho người vận hành")
st.active_alert = None

print("[test] xe đã đứng ở đích cần xác nhận người (wait_sys) → đặt lại lifecycle, chờ xác nhận, KHÔNG tự đi tiếp")
Q5 = TQ.AGVTaskQueue(); Q5.dispatch_fn = Q2.dispatch_fn
TQ.agv_task_queue = Q5; _tq_mod.agv_task_queue = Q5
Q5.restore_from_rows([dict(rows[0], seq=1.0), dict(rows[2], seq=2.0)])
dispatched.clear(); ready(17)
M._kick_restored_queue(H, "AGVR")
check(not dispatched and st.task_lifecycle == "picking" and Q5.queue_size("AGVR") == 2, "chờ xác nhận, hàng đợi còn nguyên")
st.task_lifecycle = None

print("[test] người vận hành đã làm xe chạy lệnh khác trước khi kick → bỏ qua, không dispatch đè")
Q6 = TQ.AGVTaskQueue(); Q6.dispatch_fn = Q2.dispatch_fn
TQ.agv_task_queue = Q6; _tq_mod.agv_task_queue = Q6
Q6.restore_from_rows([dict(rows[2], seq=1.0)])
Q6._running["AGVR"] = TQ.QueuedCommand("x", "AGVR", "go_to", "99", status=TQ.STATUS_RUNNING)
dispatched.clear(); ready(30)
M._kick_restored_queue(H, "AGVR")
check(not dispatched and "AGVR" not in Q6.restore_pending(), "xe đang bận → không dispatch thêm")

print()
print(f"KẾT QUẢ: {_pass} pass, {_fail} fail")
raise SystemExit(1 if _fail else 0)
