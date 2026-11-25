"""Test giữ plan khi xe offline (09-ack-lenh-fms.md §1/§2.1) + cảnh báo CMD_NOT_ACKED.
Chạy: PYTHONIOENCODING=utf-8 python test_plan_hold.py   (không cần broker: client MQTT giả)."""
import time

import mqtt_client as mc
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


class _Res:
    rc = 0


class FakeClient:
    def __init__(self):
        self.pub, self.up = [], True

    def publish(self, topic, payload, qos=0, retain=False):
        self.pub.append((topic, payload))
        return _Res()

    def is_connected(self):
        return self.up

    def plans(self):
        return [t for t, _ in self.pub if t.endswith("/order")]


fc = FakeClient()
mc.client = fc
mc._line_agv_topic = lambda agv, leaf: f"uagv/v2/T/{agv}/{leaf}"
_real_slc = mc.send_line_command
mc.send_line_command = lambda *a, **k: True          # _send_line_order gọi 'run' khôi phục MANUAL: bỏ qua trong test

AGV = "AGVT"
st = H.state_store.get_or_create(AGV)
st.current_tag = 5
st.connection_state = "ONLINE"
st.last_update = time.time()
H._routes[AGV] = LineAGVRoute(full_path=["5", "6", "7"], window_end=2)


def plan(pid):
    return {"c": "plan", "id": pid, "d": [{"t": 5, "a": 7, "v": 0}, {"t": 7, "a": 1, "v": 0}]}


print("[test] xe online: publish ngay")
mc._send_line_order(AGV, plan("p1"))
check(len(fc.plans()) == 1 and AGV not in mc._HELD_PLANS, "gửi 1 plan, không giữ")

print("[test] xe CONNECTIONBROKEN: giữ plan, không publish")
st.connection_state = "CONNECTIONBROKEN"
H._routes[AGV] = LineAGVRoute(full_path=["5", "6", "7"], window_end=2)
mc._send_line_order(AGV, plan("p2"))
check(len(fc.plans()) == 1 and AGV in mc._HELD_PLANS, "không publish thêm, plan nằm trong hàng giữ")
check(H._routes[AGV].sent_cmd_id == "p2", "route ghi nhận id plan giữ (để đối chiếu)")
mc._send_line_order(AGV, plan("p3"))
H._routes[AGV].sent_cmd_id = "p3"
check(mc._HELD_PLANS[AGV]["order"]["id"] == "p3", "plan mới đè plan đang giữ")

print("[test] chưa online lại: flush không gửi")
check(mc.flush_held_plan(AGV) is False and len(fc.plans()) == 1, "vẫn offline → giữ")

print("[test] có state mới (online lại) → gửi bù với id MỚI")
st.connection_state = "ONLINE"
st.last_update = time.time()
check(mc.flush_held_plan(AGV) is True and len(fc.plans()) == 2, "gửi bù 1 plan")
import json
sent_plan = json.loads(fc.pub[-1][1])
check(sent_plan["id"] not in ("p1", "p2", "p3") and len(sent_plan["id"]) == 8, "id mới (§2.1)")
check(sent_plan["d"] == plan("p3")["d"], "nội dung plan giữ nguyên")
check(H._routes[AGV].sent_cmd_id == sent_plan["id"] and AGV not in mc._HELD_PLANS, "route trỏ id mới, hết giữ")

print("[test] server mất broker cũng giữ plan")
fc.up = False
mc._send_line_order(AGV, plan("p4"))
check(AGV in mc._HELD_PLANS and len(fc.plans()) == 2, "broker down → giữ")
fc.up = True
H._routes[AGV].sent_cmd_id = "p4"
check(mc.flush_held_plan(AGV) is True, "broker lại → gửi bù")

print("[test] xe đổi thẻ khi offline → bỏ plan giữ")
st.connection_state = "CONNECTIONBROKEN"
mc._send_line_order(AGV, plan("p5"))
st.connection_state = "ONLINE"; st.last_update = time.time(); st.current_tag = 9
n = len(fc.plans())
check(mc.flush_held_plan(AGV) is False and len(fc.plans()) == n and AGV not in mc._HELD_PLANS, "không gửi plan cũ")
st.current_tag = 5

print("[test] route bị thay/huỷ trong lúc giữ → bỏ plan giữ")
st.connection_state = "CONNECTIONBROKEN"
mc._send_line_order(AGV, plan("p6"))
H._routes.pop(AGV, None)
st.connection_state = "ONLINE"; st.last_update = time.time()
n = len(fc.plans())
check(mc.flush_held_plan(AGV) is False and len(fc.plans()) == n, "route không còn → bỏ")

print("[test] stop xoá plan đang giữ")
H._routes[AGV] = LineAGVRoute(full_path=["5", "6", "7"], window_end=2)
st.connection_state = "CONNECTIONBROKEN"
mc._send_line_order(AGV, plan("p7"))
check(AGV in mc._HELD_PLANS, "đang giữ plan p7")
_real_slc("AGVT", "stop")
check(AGV not in mc._HELD_PLANS, "gửi stop → plan giữ bị xoá")
mc._agv_cmd_channel.cancel(AGV)

print("[test] cảnh báo CMD_NOT_ACKED khi lệnh hết lượt và xoá khi xe xác nhận lại")
st.active_alert = None
mc._on_line_cmd_expired(AGV, "run")
check(st.active_alert and st.active_alert["kind"] == "CMD_NOT_ACKED", "expired → active_alert CMD_NOT_ACKED")
mc._on_line_cmd_acked(AGV, "run")
check(st.active_alert is None, "xe xác nhận lại → hết cảnh báo")
st.active_alert = {"kind": "OBSTACLE", "message": "x", "since": 0}
mc._on_line_cmd_acked(AGV, "run")
check(st.active_alert and st.active_alert["kind"] == "OBSTACLE", "không xoá nhầm cảnh báo khác")

print(f"\nKẾT QUẢ: {_pass} pass, {_fail} fail")
raise SystemExit(1 if _fail else 0)
