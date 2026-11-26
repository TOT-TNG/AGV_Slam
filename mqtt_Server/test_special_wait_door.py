"""Test: lệnh khu chờ/về trạm tách route tại node CỬA TỰ ĐỘNG (xe dừng xin mở), xếp lệnh tiếp vào hàng đợi.
Chạy: PYTHONIOENCODING=utf-8 python test_special_wait_door.py"""
import time
import mqtt_client as mc
import floor_nav
import agv_registry as AR
from line_agv_handler import line_agv_handler as H
from door_coordinator import door_coordinator as DC
from task_queue import agv_task_queue as Q

_p = _f = 0
def check(c, m):
    global _p, _f
    if c: _p += 1; print("  PASS:", m)
    else: _f += 1; print("  FAIL:", m)

sent = []
PATH = ["5", "6", "7", "8", "9"]
mc.send_generated_order = lambda agv, order: sent.append(order)
floor_nav.multi_floor = lambda mm: False
mc.resolve_special_target_node = lambda agv, t: {"node_id": "9", "name": "WAIT", "map_id": "m", "all_occupied": False}
mc.plan_path_for_order = lambda agv, a, b: ([{"nodeId": n} for n in PATH], [])
mc.get_agv_runtime_info = lambda agv: {"current_node": "5", "raw_map": "m", "resolved_map_id": "m", "agv_state": {}}
mc.map_manager.points = {n: (i * 100, 0) for i, n in enumerate(PATH)}
mc.map_manager.node_actions = {n: {} for n in PATH}
mc.map_manager.node_actions["7"] = {"door_id": "gate1"}
mc.map_manager.node_actions["8"] = {"door_id": "gate1"}     # node phía bên kia của cùng cửa
mc.map_manager.node_actions["9"] = {"locationType": "WAIT"}
mc.map_manager.roads = []
AR.agv_registry.get_config = lambda a: {"agv_type": "tow"}
AR.agv_registry.is_line = lambda a: True

def run(agv="K1", target="wait"):
    sent.clear()
    Q._queues.pop(agv, None); Q._running.pop(agv, None)
    st = H.state_store.get_or_create(agv)
    st.current_tag = 5; st.prev_tag = 4; st.connection_state = "ONLINE"; st.last_update = time.time()
    st.task_lifecycle = None; st.last_transit_direction = ""
    r = mc.send_agv_to_special_target(agv, target, False)
    queued = [c.command for c in Q._queues.get(agv, [])]
    return r, sent[0]["d"] if sent else [], queued

print("[test] xe TIẾN VÀO cửa (7) → plan dừng ở 7, lệnh khu chờ xếp lại hàng đợi")
DC._doors.clear()
r, d, q = run()
tags = [s["t"] for s in d]
check(d and d[-1]["t"] == 7 and d[-1]["a"] == 1, f"plan kết thúc WAIT_SYS tại node cửa 7 (tags={sorted(set(tags))})")
check(max(tags) == 7, "plan KHÔNG đi qua node 8 và 9")
check(q == ["go_wait"], f"hàng đợi có go_wait để đi tiếp sau khi cửa mở: {q}")

print("[test] về trạm cũng tách tại cửa")
DC._doors.clear()
r, d, q = run(target="charge")
check(d and d[-1]["t"] == 7 and q == ["go_charge"], f"plan dừng ở 7, hàng đợi {q}")

print("[test] xe ĐÃ vào cửa từ node 7 (đang ở giữa cửa) → node 8 là lượt THOÁT, đi thẳng không dừng")
DC._doors.clear()
DC.request_open("gate1", "K1", "7")
PATH[:] = ["7", "8", "9"]
mc.map_manager.points = {n: (i * 100, 0) for i, n in enumerate(PATH)}
mc.get_agv_runtime_info = lambda agv: {"current_node": "7", "raw_map": "m", "resolved_map_id": "m", "agv_state": {}}
sent.clear(); Q._queues.pop("K1", None)
st = H.state_store.get_or_create("K1"); st.current_tag = 7; st.prev_tag = 6
mc.send_agv_to_special_target("K1", "wait")
tags = {s["t"] for s in sent[0]["d"]}
check(9 in tags and not Q._queues.get("K1"), f"đi thẳng tới 9 (tags={sorted(tags)}), không tách thêm")

print("[test] đường không có cửa → không đổi hành vi")
DC._doors.clear()
PATH[:] = ["5", "6", "8", "9"]
mc.map_manager.node_actions["7"] = {}; mc.map_manager.node_actions["8"] = {}
mc.map_manager.points = {n: (i * 100, 0) for i, n in enumerate(PATH)}
mc.get_agv_runtime_info = lambda agv: {"current_node": "5", "raw_map": "m", "resolved_map_id": "m", "agv_state": {}}
r, d, q = run()
check(d and d[-1]["t"] == 9 and q == [], f"đi thẳng tới 9, hàng đợi trống: {q}")
print(f"KẾT QUẢ: {_p} pass, {_f} fail")
raise SystemExit(1 if _f else 0)
