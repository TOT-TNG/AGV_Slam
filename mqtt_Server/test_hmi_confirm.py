"""Test: nút XÁC NHẬN / TIẾP TỤC bấm trực tiếp trên xe (HMI/firmware) làm xe chạy tiếp GIỐNG HỆT xác nhận trên web.
So sánh từng cặp (đường web ↔ đường HMI) trên cùng trạng thái ban đầu.
Chạy: PYTHONIOENCODING=utf-8 python test_hmi_confirm.py   (không cần broker/DB)."""
import asyncio
import time

import main as M
import mqtt_client as mc
import agv_registry as AR
import task_queue as TQ
from line_agv_handler import line_agv_handler as H, LineAGVRoute

_pass = _fail = 0


def check(cond, msg):
    global _pass, _fail
    if cond:
        _pass += 1
        print("  PASS:", msg)
    else:
        _fail += 1
        print("  FAIL:", msg)


AGV = "AGVH"
AR.agv_registry._type[AGV] = AR.AGV_TYPE_LINE
AR.agv_registry._config[AGV] = {"agv_id": AGV, "agv_type": "tow", "reg_type": AR.AGV_TYPE_LINE}
H.on_event = lambda *a, **k: None                 # bỏ qua gửi ack_event qua MQTT trong test
mc._HELD_PLANS.clear()
mc.map_manager.node_actions = dict(getattr(mc.map_manager, "node_actions", {}) or {})
mc.map_manager.node_actions["17"] = {"arrival_action": "wait_user"}
mc.map_manager.node_actions["21"] = {}

dispatched = []
hook_calls = []
H._send_hook_action_delayed = lambda agv, code, delay=0.0: hook_calls.append((agv, code))


def new_queue():
    q = TQ.AGVTaskQueue()
    q.dispatch_fn = lambda cmd: (dispatched.append((cmd.command, cmd.dest_node)) or True)
    TQ.agv_task_queue = q
    return q


st = H.state_store.get_or_create(AGV)


def reset_state(tag=17):
    st.current_tag = tag
    st.connection_state = "ONLINE"
    st.last_update = time.time()
    st.real_state_seen = True
    st.driving = False
    st.task_lifecycle = None
    st.hook_pending = None
    st.pending_retry_cmd = None
    H._routes.pop(AGV, None)
    dispatched.clear()
    hook_calls.clear()


def web_ack():
    return asyncio.run(M.lifecycle_ack(AGV))


def hmi(event):
    H._handle_event(AGV, event, {}, st)


print("[test] xe chờ 'Đã lấy/giao hàng' (lifecycle=picking): nút TIẾP TỤC trên xe ≡ nút xác nhận trên web")
results = {}
for how in ("web", "hmi_continue", "hmi_confirm"):
    q = new_queue()
    q.dispatch_or_queue(AGV, "go_to", "17")           # lệnh đang chạy (đã tới 17, chờ xác nhận)
    q.dispatch_or_queue(AGV, "go_to", "21")           # lệnh kế
    reset_state(17)
    dispatched.clear()
    st.task_lifecycle = "picking"
    H._routes[AGV] = LineAGVRoute(full_path=["16", "17"], window_end=1, is_complete=True)
    if how == "web":
        web_ack()
    else:
        hmi("continue" if how == "hmi_continue" else "confirm")
    results[how] = (st.task_lifecycle, AGV in H._routes, tuple(dispatched), (q.get_running(AGV) or {}).get("dest_node"))
check(results["web"] == (None, False, (("go_to", "21"),), "21"), f"web: xoá chờ xác nhận, xoá route, chạy lệnh kế → {results['web']}")
check(results["hmi_continue"] == results["web"], f"nút TIẾP TỤC trên xe cho kết quả y hệt web → {results['hmi_continue']}")
check(results["hmi_confirm"] == results["web"], f"nút XÁC NHẬN trên xe cho kết quả y hệt web → {results['hmi_confirm']}")

print("[test] xe chờ XÁC NHẬN MÓC (hook_pending=pickup): nút XÁC NHẬN trên xe ≡ nút 'Xác nhận móc' trên web")
q = new_queue()
q.dispatch_or_queue(AGV, "go_to", "17")
q.dispatch_or_queue(AGV, "go_to", "21")
reset_state(17); dispatched.clear()
st.hook_pending = "pickup"
H._routes[AGV] = LineAGVRoute(full_path=["16", "17"], window_end=1, is_complete=True)
asyncio.run(M.hook_confirm(type("R", (), {"json": staticmethod(lambda: asyncio.sleep(0, {"agv_id": AGV}))})()))
web_hook = list(hook_calls)
hook_calls.clear()
hmi("confirm")
check(web_hook and hook_calls == web_hook, f"nút XÁC NHẬN trên xe gửi đúng lệnh móc như web: {hook_calls} (web: {web_hook})")
check(not dispatched and (q.get_running(AGV) or {}).get("dest_node") == "17" and AGV in H._routes,
      "KHÔNG hoàn tất lệnh/không đi tiếp khi chưa móc (chờ móc xong rồi mới 'Đã lấy hàng')")
hook_calls.clear()
hmi("continue")                                   # 'continue' có thể do firmware tự phát khi tới đích → không được tự móc
check(not hook_calls, "event 'continue' KHÔNG kích móc (firmware có thể tự phát khi xe tới đích)")

print("[test] sau khi móc xong, xe vào 'Đã lấy hàng' → TIẾP TỤC trên xe chạy tiếp như web (cả chuỗi 2 bước bấm trên xe)")
q = new_queue()
q.dispatch_or_queue(AGV, "go_to", "17"); q.dispatch_or_queue(AGV, "go_to", "21")
reset_state(17); dispatched.clear()
st.hook_pending = "pickup"
H._routes[AGV] = LineAGVRoute(full_path=["16", "17"], window_end=1, is_complete=True)
hmi("confirm")                                    # bước 1: xác nhận móc
st.hook_pending = None; st.task_lifecycle = "picking"     # (firmware báo hook xong → server chờ 'Đã lấy hàng')
hmi("continue")                                   # bước 2: tiếp tục
check(st.task_lifecycle is None and dispatched == [("go_to", "21")] and (q.get_running(AGV) or {}).get("dest_node") == "21",
      f"xe chạy tiếp tới 21: {dispatched}")

print("[test] hàng đợi KHÔI PHỤC sau khi server khởi động lại, xe chờ xác nhận: web ≡ nút trên xe")
rows = [
    {"cmd_id": "r0", "agv_id": AGV, "command": "go_to", "dest_node": "17", "status": "running", "queued_at": 1.0,
     "session_id": None, "session_label": None, "chain_leg": False, "start_node": None, "seq": 1.0},
    {"cmd_id": "r1", "agv_id": AGV, "command": "go_to", "dest_node": "21", "status": "queued", "queued_at": 2.0,
     "session_id": None, "session_label": None, "chain_leg": False, "start_node": None, "seq": 2.0},
]
res2 = {}
for how in ("web", "hmi_continue", "hmi_confirm"):
    q = new_queue()
    q.restore_prepare_fn = lambda agv: M._prepare_restored_head(H, agv, user_initiated=True)
    q.restore_from_rows([dict(r) for r in rows])
    reset_state(17)
    M._kick_restored_queue(H, AGV)                    # xe sẵn sàng → server đặt "chờ xác nhận"
    waited = (st.task_lifecycle, dispatched == [], q.queue_size(AGV))
    if how == "web":
        web_ack()
    else:
        hmi("continue" if how == "hmi_continue" else "confirm")
    res2[how] = (waited, st.task_lifecycle, tuple(dispatched), AGV in q._restore_pending)
check(res2["web"][0] == ("picking", True, 2), f"sau khởi động lại xe CHỜ xác nhận, hàng đợi còn 2 lệnh: {res2['web'][0]}")
check(res2["web"][1] is None and res2["web"][2] and res2["web"][3] is False, f"web xác nhận → hàng đợi chạy tiếp: {res2['web'][1:]}")
check(res2["hmi_continue"] == res2["web"] and res2["hmi_confirm"] == res2["web"], "nút TIẾP TỤC/XÁC NHẬN trên xe cho kết quả y hệt web")

print("[test] người vận hành bấm xác nhận NGAY sau khởi động lại (trước khi server kịp chạy tiếp), lệnh đầu là elev_ride")
mc.map_manager.elev_nodes = {("ELV01", "F1"): "7", ("ELV01", "F3"): "7"}
rows3 = [dict(r0, command="elev_ride", dest_node="ELV01@F1>F3#17", status="running") for r0 in [rows[0]]] + [rows[1]]
res3 = {}
for how in ("web", "hmi_continue"):
    q = new_queue()
    q.restore_prepare_fn = lambda agv: M._prepare_restored_head(H, agv, user_initiated=True)
    q.restore_from_rows([dict(r) for r in rows3])
    reset_state(30)
    st.task_lifecycle = "picking"                 # có người vừa thấy "chờ xác nhận" rồi bấm
    if how == "web":
        web_ack()
    else:
        hmi("continue")
    res3[how] = tuple(dispatched)
check(res3["web"] and res3["web"][0] == ("elev_call", "ELV01@F1"), f"xe ngoài cabin: gọi lại thang trước (không dispatch thẳng elev_ride không có chuyến): {res3['web']}")
check(res3["hmi_continue"] == res3["web"], "nút trên xe cho kết quả y hệt web")

print()
print(f"KẾT QUẢ: {_pass} pass, {_fail} fail")
raise SystemExit(1 if _fail else 0)
