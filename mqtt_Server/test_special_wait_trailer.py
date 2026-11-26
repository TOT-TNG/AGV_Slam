"""Test chạy ĐÚNG hàm lệnh khu chờ (send_agv_to_special_target) cho xe RƠ-MOÓC đứng ở trạm sạc 10, vừa tới từ node 11.
Lỗi thực tế 26/11: plan gửi xuống là DIR_BWD 10→11 (lùi thẳng) thay vì lùi mù + quay đầu.
Chạy: PYTHONIOENCODING=utf-8 python test_special_wait_trailer.py"""
import time
import mqtt_client as mc
import floor_nav
from line_agv_handler import line_agv_handler as H
from line_agv_plan_builder import ACTION_REVERSE_BLIND, ACTION_DIR_BWD, ACTION_TURN_L, ACTION_DIR_FWD

_p = _f = 0
def check(c, m):
    global _p, _f
    if c: _p += 1; print("  PASS:", m)
    else: _f += 1; print("  FAIL:", m)

sent = []
mc.send_generated_order = lambda agv, order: sent.append(order)
floor_nav.multi_floor = lambda mm: False
mc.resolve_special_target_node = lambda agv, t: {"node_id": "12", "name": "WAIT", "map_id": "m", "all_occupied": False}
mc.plan_path_for_order = lambda agv, a, b: ([{"nodeId": "10"}, {"nodeId": "11"}, {"nodeId": "12"}], [])
mc.get_agv_runtime_info = lambda agv: {"current_node": "10", "raw_map": "m", "resolved_map_id": "m", "agv_state": {}}
mc.map_manager.points = {"10": (0, 0), "11": (100, 0), "12": (200, 0)}
mc.map_manager.node_actions = {"10": {"locationType": "CHARGER", "exit_reverse_ms": 3000, "exit_turn": "left"},
                               "11": {}, "12": {"locationType": "WAIT"}}
mc.map_manager.roads = []
import agv_registry as AR
types = {"T1": "trailer", "K1": "tow"}
AR.agv_registry.get_config = lambda a: {"agv_type": types.get(a, "")}
AR.agv_registry.is_line = lambda a: True

def run(agv):
    sent.clear()
    st = H.state_store.get_or_create(agv)
    st.current_tag = 10; st.prev_tag = 11; st.connection_state = "ONLINE"; st.last_update = time.time()
    st.task_lifecycle = None; st.last_transit_direction = ""
    r = mc.send_agv_to_special_target(agv, "wait")
    return r, [s["a"] for s in (sent[0]["d"] if sent else [])]

try:
    r, acts = run("T1")
    check(bool(sent), f"đã gửi plan (acts={acts})")
    check(ACTION_REVERSE_BLIND in acts and ACTION_TURN_L in acts, "rơ-moóc: có LÙI MÙ + QUAY TRÁI")
    check(acts and acts[0] != ACTION_DIR_BWD, "rơ-moóc: KHÔNG mở đầu bằng DIR_BWD (lùi thẳng dọc đường cũ)")
    r, acts = run("K1")
    check(ACTION_REVERSE_BLIND not in acts, "xe kéo: không có lùi mù")
except Exception as e:
    import traceback; traceback.print_exc()
    check(False, f"lỗi khi chạy: {type(e).__name__}: {e}")
print(f"KẾT QUẢ: {_p} pass, {_f} fail")
raise SystemExit(1 if _f else 0)
