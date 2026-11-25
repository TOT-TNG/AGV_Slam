"""Test bài test "1 chuyến xe đi thang" (uelev_console.start_ride_test) với master + bộ gọi GIẢ — không gửi gì ra broker thật.
Chuỗi chuẩn (giống elevator_coord): hallCall tại bộ gọi tầng A → thang tới, mở cửa → holdDoor → releaseHall
→ (xe vào) → depart(B) → thang tới B → (xe ra) → releaseDoor + fastClose.
Chạy: python test_uelev_ridetest.py"""
import json
import sys
import threading
import time
import types

published = []          # (thiết bị, loại lệnh)
master = {"floor": 3, "door_open": False, "hold": False, "phase": None, "actions": [], "errors": []}
callers = {}            # "call1" -> {"active": bool, "dir": str|None, "actions": []}
mode = {"stuck": False, "caller_fail": None, "travel": 0.4}   # travel: thời gian cabin chạy giữa 2 tầng (floor=null)
hub_ref = {}


def push_master():
    from elevator_coord import protocol as P
    h = P.build_header(1, time.time(), "tngfh", "ELV01", "master")
    st = P.MasterState(floor=master["floor"], door_open=master["door_open"], door_hold=master["hold"],
                       depart_phase=master["phase"], depart_to=None, errors=list(master["errors"]),
                       action_states=[P.ActionState(*a) for a in master["actions"][-8:]])
    hub_ref["hub"].on_message("uelev/v2/tngfh/ELV01/master/state", P.build_master_state(h, st).encode(), False)


def push_caller(name):
    from elevator_coord import protocol as P
    c = callers[name]
    fl = int(name[4:])
    h = P.build_header(1, time.time(), "tngfh", "ELV01", name)
    dirs = [d for d in ("UP", "DN") if (d == "UP" and fl < 3) or (d == "DN" and fl > 1)]
    st = P.CallerState(floor=fl, directions=tuple(dirs), hall_active=c["active"], hall_direction=c["dir"],
                       hall_ttl_s=30 if c["active"] else 0, hall_relay=c["active"],
                       action_states=[P.ActionState(*a) for a in c["actions"][-8:]])
    hub_ref["hub"].on_message(f"uelev/v2/tngfh/ELV01/{name}/state", P.build_caller_state(h, st).encode(), False)


def caller_react(name, action):
    typ, aid = action["actionType"], action["actionId"]
    params = {p["key"]: p["value"] for p in action["actionParameters"]}
    c = callers[name]
    if typ == "hallCall":
        if mode["caller_fail"]:
            c["actions"].append((aid, typ, "FAILED", mode["caller_fail"]))
            return push_caller(name)
        c["actions"].append((aid, typ, "FINISHED", ""))
        was_active = c["active"]
        c.update(active=True, dir=params["direction"], last_dir=params["direction"])
        push_caller(name)
        if not was_active and not mode["stuck"]:         # thang tới tầng của bộ gọi và mở cửa
            def arrive():
                time.sleep(0.4)
                master.update(floor=int(name[4:]), door_open=True, phase=None)
                push_master()
            threading.Thread(target=arrive, daemon=True).start()
    elif typ == "releaseHall":
        c["actions"].append((aid, typ, "FINISHED", ""))
        c.update(active=False, dir=None)
        push_caller(name)


def master_react(action):
    typ, aid = action["actionType"], action["actionId"]
    params = {p["key"]: p["value"] for p in action["actionParameters"]}
    master["actions"].append((aid, typ, "RUNNING", ""))
    push_master()
    if typ == "depart":
        if mode["stuck"]:
            return
        master.update(phase="transit", door_open=False, hold=False, floor=None)      # giữa 2 tầng: không cảm biến nào active
        push_master()
        time.sleep(mode["travel"])
        master.update(floor=params["toFloor"], phase=None, door_open=True, hold=True)
        master["actions"][-1] = (aid, typ, "FINISHED", "")
    elif typ == "holdDoor":
        master.update(door_open=True, hold=True)
        master["actions"][-1] = (aid, typ, "FINISHED", "")
    elif typ == "releaseDoor":
        master.update(hold=False)
        master["actions"][-1] = (aid, typ, "FINISHED", "")
    elif typ == "fastClose":
        time.sleep(0.3)
        master.update(door_open=False)
        master["actions"][-1] = (aid, typ, "FINISHED", "")
    push_master()


class _Res:
    rc = 0


class _FakeClient:
    def publish(self, topic, payload, qos=0, retain=False):
        body = json.loads(payload)
        dev = topic.split("/")[4]
        published.append((dev, body["actions"][0]["actionType"]))
        fn = master_react if dev == "master" else (lambda a, d=dev: caller_react(d, a))
        threading.Thread(target=fn, args=(body["actions"][0],), daemon=True).start()
        return _Res()


sys.modules["mqtt_client"] = types.SimpleNamespace(client=_FakeClient())
import uelev_console as U  # noqa: E402
U.RETRY_SEC = 999.0       # bộ test này đếm CHÍNH XÁC số lệnh publish — gửi lại cùng actionId có test riêng (test_uelev_console.py)

fails = []


def check(name, cond):
    print(("OK   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


def wait_done(hub, secs=25):
    end = time.time() + secs
    while time.time() < end:
        t = hub.ride_test_status("ELV01")
        if t and t["state"] != "running":
            return t
        time.sleep(0.2)
    return hub.ride_test_status("ELV01")


def reset_world(floor=3, door=False, hold=False):
    published.clear()
    master.update(floor=floor, door_open=door, hold=hold, phase=None, actions=[], errors=[])
    for n in ("call1", "call2", "call3"):
        callers[n] = {"active": False, "dir": None, "actions": []}
    push_master()
    for n in callers:
        push_caller(n)


hub = U.UelevHub()
hub_ref["hub"] = hub
import traceback
rel_stacks = []
_orig_send = hub.send


def _traced_send(elev, device, typ, params=None, prefer_factory=""):
    if typ == "releaseDoor":
        rel_stacks.append((round(time.time(), 2), [f.name for f in traceback.extract_stack()][-6:-1]))
    return _orig_send(elev, device, typ, params, prefer_factory)


hub.send = _traced_send
for n in ("master", "call1", "call2", "call3"):
    hub.on_message(f"uelev/v2/tngfh/ELV01/{n}/connection", json.dumps({"connectionState": "ONLINE"}).encode(), False)
reset_world()

# ── 1) chuyến thành công: tầng 1 → tầng 2, thang đang ở tầng 3 ──
r = hub.start_ride_test("ELV01", 1, 2, board_s=0.5, exit_s=0.5)
check("bắt đầu được", r["ok"])
check("không cho chạy 2 bài cùng lúc", not hub.start_ride_test("ELV01", 1, 2)["ok"])
t = wait_done(hub)
texts = [s["text"] for s in t["steps"]]
check("kết thúc 'done'", t["state"] == "done")
check("chuỗi lệnh đúng: hallCall(call1) → holdDoor → releaseHall(call1) → depart → holdDoor(tầng đến) → releaseDoor → fastClose",
      published[:3] == [("call1", "hallCall"), ("master", "holdDoor"), ("call1", "releaseHall")]
      and published[3:] == [("master", "depart"), ("master", "holdDoor"), ("master", "releaseDoor"), ("master", "fastClose")])
check("bộ gọi call1 được bấm (hallCall đầu tiên)", callers["call1"]["actions"][0][1] == "hallCall")
check("nút gọi đã được nhả cuối bài", callers["call1"]["active"] is False)
check("có báo bộ gọi đã nhận (đèn gọi sáng)", any("đèn gọi sáng" in x for x in texts))
check("có báo thang tới tầng 1 rồi tầng 2", any("đã tới tầng 1" in x for x in texts) and any("đã tới tầng 2" in x for x in texts))
check("có bước giữ cửa + EXIT_ALLOWED ở tầng đến", any("EXIT_ALLOWED" in x for x in texts))
check("EXIT_ALLOWED đến TRƯỚC khi xe ra", [i for i, x in enumerate(texts) if "EXIT_ALLOWED" in x][0]
      < [i for i, x in enumerate(texts) if "ra khỏi cabin" in x][0])
check("có bước xe vào / xe ra", any("vào cabin" in x for x in texts) and any("ra khỏi cabin" in x for x in texts))
check("có báo đã đóng cửa + hoàn tất", any("đã đóng cửa ở tầng 2" in x for x in texts) and "HOÀN TẤT" in texts[-1])
check("thứ tự bước đúng", [i for i, x in enumerate(texts) if "đã tới tầng 1" in x][0]
      < [i for i, x in enumerate(texts) if "vào cabin" in x][0]
      < [i for i, x in enumerate(texts) if "đã tới tầng 2" in x][0]
      < [i for i, x in enumerate(texts) if "ra khỏi cabin" in x][0])
check("mọi bước ok", all(s["status"] in ("ok", "info") for s in t["steps"]))
check("trễ vào/ra được tôn trọng (>= 1.0s)", t["steps"][-1]["at"] >= 1.0)

# ── 2) chiều xuống: tầng 3 → tầng 1 gọi bằng bộ gọi call3 ──
reset_world(floor=1)
hub.start_ride_test("ELV01", 3, 1, board_s=0.2, exit_s=0.2)
t = wait_done(hub)
check("tầng 3 → 1: gọi ở call3, kết thúc done", t["state"] == "done" and published[0] == ("call3", "hallCall"))
check("hướng gọi là XUỐNG (DN)", callers["call3"].get("last_dir") == "DN")

# ── 3) bộ gọi từ chối (hướng không hỗ trợ) → thất bại có lý do, không chạy tiếp ──
reset_world(floor=3)
mode["caller_fail"] = "direction_unsupported"
hub.start_ride_test("ELV01", 1, 2, board_s=0.2, exit_s=0.2)
t = wait_done(hub)
check("hallCall bị từ chối → 'failed' kèm mã lý do", t["state"] == "failed" and any("direction_unsupported" in s["text"] for s in t["steps"]))
check("không gửi depart khi hallCall đã thất bại", ("master", "depart") not in published)
mode["caller_fail"] = None

# ── 4) cảm biến tầng hỏng: floor=None → dừng sớm, nêu cảm biến, nhả nút gọi + cửa ──
reset_world(floor=None)
master["errors"] = [{"errorType": "FLOOR_SENSOR_INCONSISTENT", "errorDescription": ">=2 cam bien tang active"}]
push_master()
mode["stuck"] = True
U.UelevHub.RT_NOFLOOR_SEC = 1.5
hub.start_ride_test("ELV01", 1, 3, board_s=0.2, exit_s=0.2)
t = wait_done(hub)
check("floor=None → 'failed' sớm", t["state"] == "failed" and t["steps"][-1]["at"] < 10)
check("nêu rõ không xác định được tầng", any("chưa đọc được tầng" in s["text"] for s in t["steps"]))
time.sleep(0.6)
check("thất bại → nhả nút gọi ở bộ gọi", ("call1", "releaseHall") in published and callers["call1"]["active"] is False)
mode["stuck"] = False

# ── 4b) floor=null trong lúc cabin chạy giữa 2 tầng (KHÔNG có lỗi cảm biến) → phải chờ tiếp, không dừng sớm ──
reset_world(floor=3)
U.UelevHub.RT_NOFLOOR_SEC = 0.5
mode["travel"] = 2.5                    # cabin chạy 2,5s với floor=null — dài hơn RT_NOFLOOR_SEC
hub.start_ride_test("ELV01", 1, 2, board_s=0.2, exit_s=0.2)
t = wait_done(hub)
check("floor=null hợp lệ khi đang chạy: bài test KHÔNG bị dừng sớm", t["state"] == "done")
mode["travel"] = 0.4
U.UelevHub.RT_NOFLOOR_SEC = 12.0
check("_floor_fault: chỉ true khi master báo lỗi cảm biến tầng",
      U.UelevHub._floor_fault({"errors": [">=2 cam bien tang active"]}) and U.UelevHub._floor_fault({"errors": ["FLOOR_SENSOR_INCONSISTENT"]})
      and not U.UelevHub._floor_fault({"errors": []}) and not U.UelevHub._floor_fault({"errors": ["cam bien cua bi bypass"]}))

# ── 5) hủy giữa chừng ──
reset_world(floor=3)
U.UelevHub.RT_NOFLOOR_SEC = 12.0
hub.start_ride_test("ELV01", 2, 3, board_s=5.0, exit_s=5.0)
time.sleep(1.8)                       # đã tới tầng 2, đang giữ cửa / xe vào cabin
check("hủy được khi đang chạy", hub.cancel_ride_test("ELV01"))
t = wait_done(hub)
check("trạng thái 'cancelled'", t["state"] == "cancelled")
time.sleep(0.6)
check("hủy → nhả giữ cửa", ("master", "releaseDoor") in published)
check("hủy → không còn nút gọi nào đang bấm", not any(c["active"] for c in callers.values()))
check("hủy → không còn giữ cửa tay", hub.elevators()["ELV01"]["hold"] is None)

# ── 6) bộ gọi offline → fallback gọi thẳng cabin bằng master ──
reset_world(floor=3)
hub.on_message("uelev/v2/tngfh/ELV01/call1/connection", json.dumps({"connectionState": "CONNECTIONBROKEN"}).encode(), False)
hub._dev[("tngfh", "ELV01", "call1")].live_at = None
hub.start_ride_test("ELV01", 1, 2, board_s=0.2, exit_s=0.2)
t = wait_done(hub)
check("call1 offline: dùng master gọi thẳng cabin (depart tới 1 trước)", published[0] == ("master", "depart"))
check("call1 offline: ghi chú rõ không có đèn gọi", any("không có đèn gọi" in s["text"] for s in t["steps"]))

# ── 7) go_to: cùng tầng → hold_here, khác tầng → depart ──
reset_world(floor=2, door=True)
check("go_to cùng tầng → hold_here", hub.go_to("ELV01", 2, 60)["mode"] == "hold_here")
check("go_to khác tầng → depart", hub.go_to("ELV01", 3, 60)["mode"] == "depart")
hub.drop_hold("ELV01")

time.sleep(1.0)        # master giả của ca 7 còn luồng depart chạy dở (ngủ 0,4s) — chờ nó xong, kẻo ghi đè trạng thái ca sau
# ── 6b) nhánh bộ gọi offline phải CHỜ thang tới (lỗi cũ: bỏ qua bước chờ rồi chạy tiếp ngay) ──
reset_world(floor=3)
hub.on_message("uelev/v2/tngfh/ELV01/call1/connection", json.dumps({"connectionState": "CONNECTIONBROKEN"}).encode(), False)
hub._dev[("tngfh", "ELV01", "call1")].live_at = None
hub.start_ride_test("ELV01", 1, 2, board_s=0.2, exit_s=0.2)
t = wait_done(hub)
tx = [x["text"] for x in t["steps"]]
check("call1 offline: có bước chờ + báo thang đã tới tầng 1 TRƯỚC khi xe vào cabin",
      any("đã tới tầng 1" in x for x in tx) and
      [i for i, x in enumerate(tx) if "đã tới tầng 1" in x][0] < [i for i, x in enumerate(tx) if "vào cabin" in x][0])
check("call1 offline: có giữ cửa trước khi xe vào", any("Đang giữ cửa mở" in x for x in tx) and ("master", "holdDoor") in published)
hub.on_message("uelev/v2/tngfh/ELV01/call1/connection", json.dumps({"connectionState": "ONLINE"}).encode(), False)
push_caller("call1")

# ── 6c) KHÔNG có cảm biến: chế độ timer — master không bao giờ báo tới, bài test vẫn chạy hết chuỗi lệnh/relay ──
reset_world(floor=None)
mode["stuck"] = True
t0 = time.time()
hub.start_ride_test("ELV01", 1, 2, board_s=0.2, exit_s=0.2, arrive_mode="timer", travel_s=1.0)
t = wait_done(hub)
tx = [x["text"] for x in t["steps"]]
check("timer: hoàn tất dù master không có cảm biến tầng", t["state"] == "done")
print("DBG_PUBLISHED:", published)
print("DBG_REL_STACKS:", rel_stacks[-3:])
check("timer: chuỗi lệnh đủ (hallCall, holdDoor, releaseHall, depart, holdDoor, releaseDoor, fastClose)",
      [x[1] for x in published] == ["hallCall", "holdDoor", "releaseHall", "depart", "holdDoor", "releaseDoor", "fastClose"])
check("timer: ghi rõ là GIẢ ĐỊNH, không có xác nhận cảm biến", sum("GIẢ ĐỊNH" in x for x in tx) == 2)
check("timer: có chờ ~1s mỗi chặng (tổng ≥ 2s)", time.time() - t0 >= 2.0)
mode["stuck"] = False

# ── 6d) chế độ manual: chờ người vận hành bấm "Thang đã tới" ở từng chặng ──
reset_world(floor=None)
mode["stuck"] = True
check("manual: chưa chạy thì confirm → False", hub.confirm_arrival("ELV01") is False)
hub.start_ride_test("ELV01", 1, 2, board_s=0.2, exit_s=0.2, arrive_mode="manual")


def wait_awaiting(floor, secs=10):
    end = time.time() + secs
    while time.time() < end:
        st = hub.ride_test_status("ELV01")
        if st["awaiting"] and st["awaiting"]["floor"] == floor:
            return True
        time.sleep(0.1)
    return False


check("manual: dừng chờ xác nhận tầng 1", wait_awaiting(1))
time.sleep(0.6)
check("manual: chưa bấm thì chưa chạy tiếp (đang chờ, chưa done)", hub.ride_test_status("ELV01")["state"] == "running")
check("manual: confirm tầng 1 nhận", hub.confirm_arrival("ELV01") is True)
check("manual: tiếp tục, chờ xác nhận tầng 2", wait_awaiting(2))
check("manual: confirm tầng 2 nhận", hub.confirm_arrival("ELV01") is True)
t = wait_done(hub)
check("manual: hoàn tất sau 2 lần xác nhận", t["state"] == "done")
check("manual: awaiting được xoá khi xong", t["awaiting"] is None)
mode["stuck"] = False

# manual: hủy khi đang chờ xác nhận
reset_world(floor=None)
mode["stuck"] = True
hub.start_ride_test("ELV01", 1, 2, board_s=0.2, exit_s=0.2, arrive_mode="manual")
wait_awaiting(1)
hub.cancel_ride_test("ELV01")
t = wait_done(hub)
time.sleep(0.6)
check("manual: hủy khi đang chờ → cancelled, nhả nút gọi", t["state"] == "cancelled" and callers["call1"]["active"] is False)
mode["stuck"] = False
check("arrive_mode lạ bị từ chối", not hub.start_ride_test("ELV01", 1, 2, arrive_mode="xyz")["ok"])
# ── 8) master offline → từ chối ngay ──
hub2 = U.UelevHub()
check("master chưa kết nối → từ chối", not hub2.start_ride_test("ELV01", 1, 2)["ok"])

print("\nTỔNG:", "TẤT CẢ ĐẠT" if not fails else f"{len(fails)} LỖI: {fails}")
raise SystemExit(1 if fails else 0)
