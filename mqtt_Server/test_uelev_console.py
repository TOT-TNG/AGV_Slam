"""Test bảng điều khiển thang uelev/v2 (uelev_console) với MQTT giả — KHÔNG gửi gì ra broker thật.
Chạy: python test_uelev_console.py"""
import json
import sys
import time
import types

# mqtt_client giả: ghi lại mọi publish
published = []


class _Res:
    rc = 0


class _FakeClient:
    def publish(self, topic, payload, qos=0, retain=False):
        published.append((topic, json.loads(payload)))
        return _Res()


sys.modules["mqtt_client"] = types.SimpleNamespace(client=_FakeClient())

import uelev_console as U  # noqa: E402
from elevator_coord import protocol as P  # noqa: E402

fails = []


def check(name, cond):
    print(("OK   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


def master_state(floor=1, door_open=False, hold=False, errors=None, actions=None):
    h = P.build_header(1, time.time(), "tngfh", "ELV01", "master")
    st = P.MasterState(floor=floor, door_open=door_open, door_hold=hold, errors=errors or [],
                       action_states=[P.ActionState(*a) for a in (actions or [])])
    return P.build_master_state(h, st).encode()


def caller_state(floor, dirs):
    h = P.build_header(1, time.time(), "tngfh", "ELV01", "call%d" % floor)
    return P.build_caller_state(h, P.CallerState(floor=floor, directions=tuple(dirs))).encode()


def conn(state):
    return json.dumps({"connectionState": state}).encode()


hub = U.UelevHub()
U.RETRY_SEC = 999.0          # các test cũ đếm số lần gửi: tắt gửi lại; ca "gửi lại" bên dưới bật riêng

# ── nhận diện ──
hub.on_message("uelev/v2/tngfh/ELV01/master/connection", conn("ONLINE"), True)
hub.on_message("uelev/v2/tngfh/ELV01/master/state", master_state(2), True)
e = hub.elevators()["ELV01"]
check("chỉ có tin retained → master chưa online", not e["online"] and e["devices"][0]["link"] == "stale" or e["devices"][0]["link"] == "stale")

hub.on_message("uelev/v2/tngfh/ELV01/master/state", master_state(2, door_open=True), False)
e = hub.elevators()["ELV01"]
check("tin state sống → online, đọc tầng + cửa", e["online"] and e["floor"] == 2 and e["door_open"] is True)

hub.on_message("uelev/v2/tngfh/ELV01/call3/connection", conn("CONNECTIONBROKEN"), True)
hub.on_message("uelev/v2/tngfh/ELV01/call2/state", caller_state(2, ["UP", "DN"]), False)
devs = {d["device"]: d for d in hub.elevators()["ELV01"]["devices"]}
check("caller LWT CONNECTIONBROKEN → offline", devs["call3"]["link"] == "offline")
check("caller sống đọc được tầng + hướng", devs["call2"]["floor"] == 2 and devs["call2"]["directions"] == ["UP", "DN"])
check("master đứng đầu danh sách thiết bị", hub.elevators()["ELV01"]["devices"][0]["device"] == "master")

hub.on_message("uelev/v2/Vietduc/ELV01/call1/state", caller_state(1, ["UP"]), False)
check("nhiều factory trong 1 thang → factory_mixed", hub.elevators()["ELV01"]["factory_mixed"])

hub.on_message("uelev/v2/tngfh/ELV01/master/state", b"{khong phai json", False)
check("state rác không làm hỏng thiết bị", hub.elevators()["ELV01"]["online"])
hub.on_message("uelev/v2/tngfh/ELV01/master/state", master_state(2, errors=[{"errorType": "x", "errorDescription": "cam bien cua bi bypass"}]), False)
check("lỗi master được đọc", "cam bien cua bi bypass" in hub.elevators()["ELV01"]["devices"][0]["errors"])

# ── gửi lệnh ──
published.clear()
r = hub.send("ELV01", "master", P.ACT_CALL_FLOOR, {"floor": 3, "pulseMs": 1000})
t, body = published[-1]
check("topic instantActions đúng factory của master", t == "uelev/v2/tngfh/ELV01/master/instantActions")
acts = P.parse_actions(json.dumps(body))
check("payload parse được bằng thư viện: callFloor floor=3", acts[0][0] == "callFloor" and acts[0][2]["floor"] == 3 and acts[0][1] == r["action_id"])
check("header manufacturer = factory", body["manufacturer"] == "tngfh" and body["serialNumber"] == "ELV01-master")

published.clear()
hub.send("ELV01", "call1", P.ACT_HALL_CALL, {"direction": "UP", "ttlS": 30})
check("caller gửi theo factory riêng của nó (Vietduc)", published[-1][0] == "uelev/v2/Vietduc/ELV01/call1/instantActions")
check("thiết bị chưa từng thấy → báo lỗi, không gửi", not hub.send("ELV99", "master", P.ACT_RESET)["ok"])

# actionStates phản hồi
aid = r["action_id"]
hub.on_message("uelev/v2/tngfh/ELV01/master/state", master_state(3, actions=[(aid, "callFloor", "FINISHED", "")]), False)
acts_ui = hub.elevators()["ELV01"]["devices"][0]["actions"]
check("actionStates của thiết bị hiện cho UI", acts_ui and acts_ui[0]["id"] == aid and acts_ui[0]["status"] == "FINISHED")

# ── giữ cửa ──
U.HOLD_REFRESH_SEC = 0.5
published.clear()
h = hub.hold("ELV01", 5.0, close_on_end=True)
check("hold gửi holdDoor ttlS=30 ngay", h["ok"] and published[0][1]["actions"][0]["actionType"] == "holdDoor"
      and published[0][1]["actions"][0]["actionParameters"] == [{"key": "ttlS", "value": 30}])
check("trạng thái hold hiện trong elevators()", hub.elevators()["ELV01"]["hold"] is not None)
time.sleep(2.3)
holds = [p for p in published if p[1]["actions"][0]["actionType"] == "holdDoor"]
ids = {p[1]["actions"][0]["actionId"] for p in holds}
check("làm mới holdDoor định kỳ với actionId MỚI", len(holds) >= 3 and len(ids) == len(holds))

published.clear()
rel = hub.release("ELV01")
types_sent = [p[1]["actions"][0]["actionType"] for p in published]
check("release: releaseDoor + fastClose, bỏ hold", types_sent == ["releaseDoor", "fastClose"] and rel["was_holding"]
      and hub.elevators()["ELV01"]["hold"] is None)
time.sleep(1.2)
check("sau release không còn gửi holdDoor", not any(p[1]["actions"][0]["actionType"] == "holdDoor" for p in published))

# hết giờ tự nhả
U.HOLD_REFRESH_SEC = 10.0
published.clear()
hub.hold("ELV01", 5.0, close_on_end=True)
hub._holds["ELV01"]["until"] = time.monotonic() + 1.0     # rút ngắn để test
time.sleep(3.0)
tp = [p[1]["actions"][0]["actionType"] for p in published]
check("hết giờ → releaseDoor + fastClose", tp[-2:] == ["releaseDoor", "fastClose"] and hub.elevators()["ELV01"]["hold"] is None)

# ── master tự báo "đã tới" (09 §6.3): depart=null + doorHoldAuto + floor ──
import contextlib
import io


def master_dep(phase, to, floor, auto=False, ttl=0):
    h = P.build_header(1, time.time(), "tngfh", "ELV02", "master")
    st = P.MasterState(floor=floor, door_open=None, door_hold=auto, door_hold_auto=auto, hold_ttl_s=ttl,
                       depart_phase=phase, depart_to=to)
    return P.build_master_state(h, st).encode()


buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    hub.on_message("uelev/v2/tngfh/ELV02/master/state", master_dep("transit", 2, None), False)
    hub.on_message("uelev/v2/tngfh/ELV02/master/state", master_dep("transit", 2, None), False)
    hub.on_message("uelev/v2/tngfh/ELV02/master/state", master_dep(None, None, 2, auto=True, ttl=290), False)
    hub.on_message("uelev/v2/tngfh/ELV02/master/state", master_dep(None, None, 2, auto=True, ttl=289), False)
out = buf.getvalue()
check("log pha depart chỉ 1 lần khi không đổi", out.count("pha transit") == 1)
check("log 'ĐÃ TỚI tầng 2' đúng 1 lần", out.count("ĐÃ TỚI tầng 2") == 1 and "doorHoldAuto" in out)
m2 = hub.elevators()["ELV02"]["devices"][0]
check("dữ liệu cho UI: depart null + doorHoldAuto + floor", m2["depart_phase"] is None and m2["door_hold_auto"] and m2["floor"] == 2)
check("_arrived nhận dấu hiệu firmware (cả khi cảm biến cửa không có)", U.UelevHub._arrived(m2, 2) and not U.UelevHub._arrived(m2, 3))
check("_arrived từ chối khi còn đang depart", not U.UelevHub._arrived({"floor": 2, "depart_phase": "transit", "door_hold_auto": True}, 2))

buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    hub.on_message("uelev/v2/tngfh/ELV03/master/state", master_dep("transit", 2, None), False)
    hub.on_message("uelev/v2/tngfh/ELV03/master/state", master_dep(None, None, None, auto=False), False)
check("depart kết thúc mà không tới → cảnh báo kiểm tra cảm biến", "CHƯA xác nhận tới nơi" in buf.getvalue())
# ── gửi tin cậy (11-tai-lieu-dev §3.3): gửi lại CÙNG actionId; offline thì giữ lệnh ──
def conn_state(h, factory, dev, st):
    h.on_message(f"uelev/v2/{factory}/ELV09/{dev}/connection", json.dumps({"connectionState": st}).encode(), False)


def live_master(h, actions=(), floor=1):
    hh = P.build_header(1, time.time(), "tngfh", "ELV09", "master")
    st = P.MasterState(floor=floor, action_states=[P.ActionState(*a) for a in actions])
    h.on_message("uelev/v2/tngfh/ELV09/master/state", P.build_master_state(hh, st).encode(), False)


h2 = U.UelevHub()
conn_state(h2, "tngfh", "master", "ONLINE")
live_master(h2)
U.RETRY_SEC = 0.3
U.RETRY_MAX = 3
published.clear()
r = h2.send("ELV09", "master", P.ACT_CALL_FLOOR, {"floor": 2, "pulseMs": 1000})
aid = r["action_id"]
time.sleep(3.2)
same = [p for p in published if p[1]["actions"][0]["actionId"] == aid]
check("chưa có phản hồi → gửi lại CÙNG actionId nhiều lần", len(same) >= 3)
check("hết RETRY_MAX lần gửi lại → EXPIRED (không gửi mãi)", len(same) <= 1 + 3 + 1 and aid in h2._expired and aid not in h2._pending)
check("UI thấy lệnh 'expired'", any(x["state"] == "expired" for x in h2.elevators()["ELV09"]["devices"][0]["sent"]))

U.RETRY_MAX = 10
published.clear()
r = h2.send("ELV09", "master", P.ACT_CALL_FLOOR, {"floor": 3, "pulseMs": 1000})
aid = r["action_id"]
time.sleep(0.7)
n_before = len([p for p in published if p[1]["actions"][0]["actionId"] == aid])
live_master(h2, actions=[(aid, "callFloor", "RUNNING", "")])           # thiết bị đã nhận
time.sleep(1.0)
n_after = len([p for p in published if p[1]["actions"][0]["actionId"] == aid])
check("thấy actionId trong actionStates → dừng gửi lại", n_before >= 2 and n_after == n_before and aid not in h2._pending)

# thiết bị offline (cabin đóng cửa mất Wi-Fi): giữ lệnh, KHÔNG đếm lần gửi lặp, gửi khi online lại
conn_state(h2, "tngfh", "master", "CONNECTIONBROKEN")
published.clear()
r = h2.send("ELV09", "master", P.ACT_HOLD_DOOR, {"ttlS": 30})
aid = r["action_id"]
check("offline: lệnh được giữ trong hàng chờ, chưa publish", r["ok"] and r.get("queued") and not published)
time.sleep(1.0)
check("offline: vẫn chưa publish và chưa đếm lần gửi lại", not published and h2._pending[aid]["n"] == 0)
check("UI thấy lệnh 'queued'", any(x["state"] == "queued" for x in h2.elevators()["ELV09"]["devices"][0]["sent"]))
live_master(h2)                                                       # state sống mới hơn LWT → online lại
time.sleep(1.2)
check("online lại → lệnh được gửi (1 lần, đúng actionId)",
      len([p for p in published if p[1]["actions"][0]["actionId"] == aid]) >= 1)
live_master(h2, actions=[(aid, "holdDoor", "FINISHED", "")])
time.sleep(0.8)
U.RETRY_SEC = 999.0

# lệnh chờ quá lâu → bỏ (tránh thang tự chạy khi nối lại muộn)
U.QUEUE_MAX_AGE_SEC = 0.5
conn_state(h2, "tngfh", "master", "CONNECTIONBROKEN")
h2._dev[("tngfh", "ELV09", "master")].live_at = None
published.clear()
r = h2.send("ELV09", "master", P.ACT_DEPART, {"toFloor": 2})
time.sleep(1.5)
check("(giới hạn bật thủ công) offline quá lâu → bỏ lệnh chưa gửi", r["action_id"] in h2._expired and not published)
U.QUEUE_MAX_AGE_SEC = 0.0      # mặc định: GIỮ lệnh tới khi thiết bị online lại

# mặc định không giới hạn: lệnh chờ lâu vẫn được GIỮ và gửi khi cabin online lại (cabin đóng cửa mất mạng hàng giờ)
conn_state(h2, "tngfh", "master", "CONNECTIONBROKEN")
h2._dev[("tngfh", "ELV09", "master")].live_at = None
published.clear()
r_keep = h2.send("ELV09", "master", P.ACT_DEPART, {"toFloor": 3})
time.sleep(1.5)
check("mặc định: offline lâu vẫn GIỮ lệnh (không bị bỏ)", r_keep["action_id"] not in h2._expired and not published)
live_master(h2)
time.sleep(1.5)
check("online lại → lệnh giữ được gửi", any(p[1]["actions"][0]["actionId"] == r_keep["action_id"] for p in published))
live_master(h2, actions=[(r_keep["action_id"], "depart", "RUNNING", "")])
time.sleep(0.5)

# master mất Wi-Fi khi cabin đóng cửa chạy depart = bình thường
h3 = U.UelevHub()
conn_state(h3, "tngfh", "master", "ONLINE")
hh = P.build_header(1, time.time(), "tngfh", "ELV09", "master")
h3.on_message("uelev/v2/tngfh/ELV09/master/state",
              P.build_master_state(hh, P.MasterState(floor=1, depart_phase="transit", depart_to=2)).encode(), False)
conn_state(h3, "tngfh", "master", "CONNECTIONBROKEN")
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    conn_state(h3, "tngfh", "master", "CONNECTIONBROKEN")
mj = h3.elevators()["ELV09"]["devices"][0]
check("đang depart mà master mất mạng → cabin_closed_offline (bình thường)", mj["link"] == "offline" and mj["cabin_closed_offline"])
h4 = U.UelevHub()
conn_state(h4, "tngfh", "master", "CONNECTIONBROKEN")
check("offline khi KHÔNG depart → không gắn cờ bình thường", not h4.elevators()["ELV09"]["devices"][0]["cabin_closed_offline"])
# ── không publish đúp: luồng gửi lại KHÔNG được publish lại lệnh vừa được send() chiếm lượt gửi đầu (race đã sửa) ──
import threading
_fc = sys.modules["mqtt_client"].client
_orig_pub = _fc.publish


def _slow_pub(topic, payload, qos=0, retain=False):
    time.sleep(0.8)                                  # lâu hơn nhịp quét 0,5s của luồng gửi lại → cửa sổ race rộng
    return _orig_pub(topic, payload, qos, retain)


U.RETRY_SEC = 999.0
h5 = U.UelevHub()
conn_state(h5, "tngfh", "master", "ONLINE")
live_master(h5)
published.clear()
_fc.publish = _slow_pub
th = [threading.Thread(target=lambda: h5.send("ELV09", "master", P.ACT_CALL_FLOOR, {"floor": 1, "pulseMs": 1000})) for _ in range(4)]
for t_ in th:
    t_.start()
for t_ in th:
    t_.join()
time.sleep(1.5)
_fc.publish = _orig_pub
ids_ = [p_[1]["actions"][0]["actionId"] for p_ in published]
check("mỗi actionId chỉ publish đúng 1 lần dù luồng gửi lại đang chạy (không race)", len(ids_) == 4 and len(set(ids_)) == 4)
print("\nTỔNG:", "TẤT CẢ ĐẠT" if not fails else f"{len(fails)} LỖI: {fails}")
raise SystemExit(1 if fails else 0)
