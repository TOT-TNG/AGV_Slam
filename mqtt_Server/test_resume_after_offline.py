"""Test: xe offline (vd vào thang, cabin đóng cửa mất Wi-Fi) rồi online lại — lệnh hàng đợi đang dang dở KHÔNG được mất.
Chạy: PYTHONIOENCODING=utf-8 python test_resume_after_offline.py   (không cần broker/DB: hàng đợi giả)."""
import time

import main as M
from line_agv_handler import line_agv_handler as H, LineAGVRoute, line_state_online
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


# ── hàng đợi giả: ghi lại insert_next / on_agv_completed, giữ "lệnh đang chạy" ──
class FakeQ:
    def __init__(self):
        self.running = {}
        self.calls = []

    def get_running(self, agv):
        return self.running.get(agv)

    def insert_next(self, agv, command, dest_node=None):
        self.calls.append(("insert_next", agv, command, dest_node))

    def on_agv_completed(self, agv, notes="", **kw):
        self.calls.append(("completed", agv, notes))
        self.running.pop(agv, None)


fq = FakeQ()
TQ.agv_task_queue = fq

import mqtt_client as mc
mc._HELD_PLANS.clear()

AGV = "AGVR"
st = H.state_store.get_or_create(AGV)


def online(tag):
    st.current_tag = tag
    st.connection_state = "ONLINE"
    st.last_update = time.time()
    st.driving = False
    st.online_streak = M.GHOST_ONLINE_STREAK


def offline():
    st.connection_state = "CONNECTIONBROKEN"
    st.last_update = time.time() - 60
    st.online_streak = 0
    st.offline_decided = False


def running(cmd="go_to", dest="21", cid="c1"):
    fq.running[AGV] = {"cmd_id": cid, "command": cmd, "dest_node": dest}


print("[test] mất tín hiệu khi đang chạy lệnh go_to → ghi nhớ lệnh")
online(7)
st.resume_cmd_id = None
running()
H._routes[AGV] = LineAGVRoute(full_path=["7", "17", "18"], window_end=2)
offline()
M._line_offline_tick(H, AGV, st)
check(st.resume_cmd_id == "c1", "ghi nhớ id lệnh đang chạy lúc offline")

print("[test] online lại, route bị huỷ (xe ma online lại ngoài vùng) → dựng lại lệnh từ vị trí thật")
online(30)                                   # xe ra khỏi thang ở tầng khác, thẻ nằm NGOÀI vùng ma [7,17,18]
M._line_offline_tick(H, AGV, st)             # xe ma online lại → huỷ route (vị trí lệch vùng ma)
check(AGV not in H._routes and not st.ghost, "xe ma được gỡ, route bị huỷ vì vị trí lệch")
check(H.resume_after_offline(AGV, st) is True, "xử lý xong")
check(("insert_next", AGV, "go_to", "21") in fq.calls, "chèn lại đúng lệnh go_to → 21")
check(("completed", AGV, "resume_after_offline") in fq.calls, "giải phóng lệnh cũ để dispatch lại")
check(st.resume_cmd_id is None, "xoá cờ khôi phục (chỉ làm 1 lần)")

print("[test] xe còn đang chạy / còn là xe ma → chưa khôi phục, kiểm tra lại sau")
fq.calls.clear(); running(); st.resume_cmd_id = "c1"; H._routes.pop(AGV, None)
online(17); st.driving = True
check(H.resume_after_offline(AGV, st) is False and not fq.calls, "driving → chờ")
st.driving = False; st.ghost = True
check(H.resume_after_offline(AGV, st) is False and not fq.calls, "ghost → chờ")
st.ghost = False

print("[test] route còn khớp vị trí → không đụng (cơ chế gửi bù plan/cửa sổ lo tiếp)")
fq.calls.clear(); st.resume_cmd_id = "c1"
H._routes[AGV] = LineAGVRoute(full_path=["7", "17", "18"], window_end=2)
online(17)
check(H.resume_after_offline(AGV, st) is True and not fq.calls and AGV in H._routes, "giữ nguyên route + lệnh")

print("[test] route cũ KHÔNG chứa vị trí thật (xe đứng yên ở nơi khác) → bỏ route cũ, dựng lại lệnh")
fq.calls.clear(); running(); st.resume_cmd_id = "c1"
H._routes[AGV] = LineAGVRoute(full_path=["7", "8", "9"], window_end=2)
online(17)
check(H.resume_after_offline(AGV, st) is True, "xử lý xong")
check(AGV not in H._routes and ("insert_next", AGV, "go_to", "21") in fq.calls, "bỏ route lệch và chèn lại lệnh")

print("[test] plan đang giữ chờ gửi bù → để flush_held_plan làm trước")
fq.calls.clear(); running(); st.resume_cmd_id = "c1"; H._routes.pop(AGV, None)
mc._HELD_PLANS[AGV] = {"order": {"id": "x"}, "tag": "17", "held_at": time.time()}
online(17)
check(H.resume_after_offline(AGV, st) is False and not fq.calls, "chờ plan giữ")
mc._HELD_PLANS.pop(AGV, None)

print("[test] lệnh đã đổi/xong trong lúc offline → bỏ cờ, không chèn lệnh thừa")
fq.calls.clear(); st.resume_cmd_id = "c1"; running(cid="c2")
online(17)
check(H.resume_after_offline(AGV, st) is True and not fq.calls and st.resume_cmd_id is None, "không đụng lệnh mới")

print("[test] lệnh thang elev_* do cầu nối thang điều khiển → không dựng lại")
fq.calls.clear(); running(cmd="elev_ride", dest="ELV01@F2>F1#30", cid="c3"); st.resume_cmd_id = "c3"
H._routes.pop(AGV, None); online(7)
check(H.resume_after_offline(AGV, st) is True and not fq.calls, "bỏ qua elev_*")

print("[test] đang chờ xác nhận lấy/giao hàng → lifecycle lo, không dựng lại")
fq.calls.clear(); running(); st.resume_cmd_id = "c1"; st.task_lifecycle = "picking"
online(17)
check(H.resume_after_offline(AGV, st) is True and not fq.calls, "không chen vào lifecycle")
st.task_lifecycle = None

print("[test] go_charge (không có dest) cũng được dựng lại")
fq.calls.clear(); running(cmd="go_charge", dest=None, cid="c4"); st.resume_cmd_id = "c4"
H._routes.pop(AGV, None); online(30)
check(H.resume_after_offline(AGV, st) is True and ("insert_next", AGV, "go_charge", None) in fq.calls, "go_charge dựng lại")

print("[test] GHOST: xe ma online lại ở vị trí lệch vùng ma → huỷ route nhưng lệnh vẫn được khôi phục sau")
fq.calls.clear(); running(); st.resume_cmd_id = "c1"
H._routes[AGV] = LineAGVRoute(full_path=["7", "17", "18"], window_end=2)
st.ghost = True; st.ghost_nodes = ["7"]
online(30)
M._ghost_release(H, AGV, st, recovered=True)
check(AGV not in H._routes and st.resume_cmd_id == "c1", "route huỷ nhưng cờ khôi phục còn")
check(H.resume_after_offline(AGV, st) is True and ("insert_next", AGV, "go_to", "21") in fq.calls, "lệnh dang dở được dựng lại")

print()
print(f"KẾT QUẢ: {_pass} pass, {_fail} fail")
raise SystemExit(1 if _fail else 0)
