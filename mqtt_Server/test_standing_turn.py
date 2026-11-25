"""Test: plan bắt đầu bằng RẼ tại thẻ xe đang đứng (vd node 30 → 7 vào thang) — xe lăn thẳng trước khi quay thì server dừng xe và gửi lại plan.
Chạy: PYTHONIOENCODING=utf-8 python test_standing_turn.py   (không cần broker: client MQTT giả, đồng hồ giả)."""
import time

import mqtt_client as mc
import line_agv_handler as LH
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
        self.pub = []

    def publish(self, topic, payload, qos=0, retain=False):
        self.pub.append((topic, payload))
        return _Res()

    def is_connected(self):
        return True


fc = FakeClient()
mc.client = fc
mc._line_agv_topic = lambda agv, leaf: f"uagv/v2/T/{agv}/{leaf}"
mc._HELD_PLANS.clear()
H.on_event = lambda *a, **k: None
LH.STANDING_TURN_RESEND_S = 0.05                       # gửi lại gần như ngay trong test

AGV = "AGVT"
st = H.state_store.get_or_create(AGV)

TURN_PLAN = {"c": "plan", "id": "p0", "d": [{"t": 30, "a": 7, "v": 0}, {"t": 30, "a": 5, "v": 0}, {"t": 30, "a": 4, "v": 120},
                                            {"t": 30, "a": 3, "v": 0}, {"t": 7, "a": 1, "v": 0}]}
STRAIGHT_PLAN = {"c": "plan", "id": "p1", "d": [{"t": 6, "a": 7, "v": 0}, {"t": 6, "a": 3, "v": 0}, {"t": 30, "a": 1, "v": 0}]}


def sent(kind):
    out = []
    for topic, payload in fc.pub:
        if topic.endswith("/" + kind):
            out.append(payload)
    return out


def reset(tag=30, driving=False):
    fc.pub.clear()
    st.current_tag = tag
    st.connection_state = "ONLINE"
    st.last_update = time.time()
    st.driving = driving
    st.standing_turn = None
    st.active_alert = None
    H._routes[AGV] = LineAGVRoute(full_path=["30", "7"], window_end=1, is_complete=True)


def plans():
    import json
    return [json.loads(p) for p in sent("order")]


print("[test] arm: chỉ theo dõi plan BẮT ĐẦU bằng rẽ tại thẻ xe đang đứng")
reset()
H.arm_standing_turn(AGV, TURN_PLAN)
check(st.standing_turn is not None and st.standing_turn["tag"] == "30", "plan rẽ tại thẻ 30, xe đứng ở 30 → theo dõi")
reset()
H.arm_standing_turn(AGV, STRAIGHT_PLAN)
check(st.standing_turn is None, "plan đi thẳng → không theo dõi")
reset(tag=6)
H.arm_standing_turn(AGV, TURN_PLAN)
check(st.standing_turn is None, "xe KHÔNG đứng ở thẻ đầu plan → không theo dõi")
reset(driving=True)
H.arm_standing_turn(AGV, TURN_PLAN)
check(st.standing_turn is None, "xe đang chạy → không theo dõi")

print("[test] bình thường: driving + turn_busy CÙNG gói → không can thiệp")
reset()
H.arm_standing_turn(AGV, TURN_PLAN)
st.driving = True
H._check_standing_turn(AGV, st, "turn_busy")
time.sleep(0.05)
check(st.standing_turn is None and not sent("instantActions") and not plans(), "không dừng, không gửi lại")

print("[test] xe LĂN THẲNG (driving, không turn_busy) quá ngưỡng → dừng xe + gửi lại plan")
LH.STANDING_TURN_ROLL_S = 0.2
reset()
H.arm_standing_turn(AGV, TURN_PLAN)
st.driving = True
H._check_standing_turn(AGV, st, "")                    # gói đầu: bắt đầu tính
check(st.standing_turn is not None and not sent("instantActions"), "mới lăn → chưa làm gì")
time.sleep(0.25)
H._check_standing_turn(AGV, st, "")                    # đủ ngưỡng
st.driving = False                                     # xe đã dừng sau lệnh stop
time.sleep(0.9)                                        # chờ Timer gửi lại
import json
stops = [json.loads(p) for p in sent("instantActions") if json.loads(p).get("c") == "stop"]
check(len(stops) == 1, f"đã gửi lệnh stop: {len(stops)}")
rp = plans()
check(len(rp) == 1 and rp[0]["id"] != "p0" and rp[0]["d"] == TURN_PLAN["d"], "gửi lại ĐÚNG plan (id mới, cùng các bước)")
check(st.standing_turn is not None and st.standing_turn["retries"] == 1, "theo dõi lại với số lần thử = 1")

print("[test] lặp lại tới giới hạn rồi cảnh báo, không dừng xe vô hạn")
for n in (2, 3):
    st.driving = True
    H._check_standing_turn(AGV, st, "")
    time.sleep(0.25)
    H._check_standing_turn(AGV, st, "")
    st.driving = False
    time.sleep(0.9)
stops = [json.loads(p) for p in sent("instantActions") if json.loads(p).get("c") == "stop"]
check(len(stops) == LH.STANDING_TURN_MAX_RETRIES, f"tối đa {LH.STANDING_TURN_MAX_RETRIES} lần dừng/gửi lại: {len(stops)}")
check((st.active_alert or {}).get("kind") == "TURN_NOT_STARTED", "lần thứ 3: đặt cảnh báo TURN_NOT_STARTED thay vì dừng tiếp")

print("[test] thẻ đổi (xe đã đi tới thẻ khác) hoặc lệnh bị huỷ → huỷ theo dõi/không gửi lại")
reset()
H.arm_standing_turn(AGV, TURN_PLAN)
st.current_tag = 7
st.driving = True
H._check_standing_turn(AGV, st, "")
check(st.standing_turn is None, "thẻ đổi → ngừng theo dõi")
reset()
H.arm_standing_turn(AGV, TURN_PLAN)
st.driving = True
H._check_standing_turn(AGV, st, "")
time.sleep(0.25)
H._routes.pop(AGV, None)                               # lệnh bị huỷ ngay lúc dừng
H._check_standing_turn(AGV, st, "")
time.sleep(0.9)
check(not plans(), "lệnh đã huỷ → KHÔNG gửi lại plan")

print("[test] tắt bằng STANDING_TURN_GUARD")
LH.STANDING_TURN_GUARD = False
reset()
H.arm_standing_turn(AGV, TURN_PLAN)
check(st.standing_turn is None, "guard tắt → không theo dõi")
LH.STANDING_TURN_GUARD = True

print("[test] _publish_line_order gắn theo dõi tự động")
reset()
mc._publish_line_order(AGV, dict(TURN_PLAN, id="px"))
check(st.standing_turn is not None, "publish plan rẽ tại chỗ → tự theo dõi")

print()
print(f"KẾT QUẢ: {_pass} pass, {_fail} fail")
raise SystemExit(1 if _fail else 0)
