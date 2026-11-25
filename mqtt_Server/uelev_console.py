"""Bảng điều khiển thang máy giao thức uelev/v2 — ĐỘC LẬP với bản đồ, với chuỗi đi thang của xe và với ELEVATOR_BACKEND.

  • Hub nghe `uelev/v2/+/+/+/state|connection` (luôn bật) → biết thang nào / thiết bị nào (master, call1..N) đang kết nối,
    factory nào, tầng, cửa, giữ cửa, lỗi, trạng thái các lệnh đã gửi.
  • Gửi lệnh tay qua `uelev/v2/{factory}/{thang}/{thiết bị}/instantActions` (VDA5050 instantActions, mỗi lệnh 1 actionId).
    Mỗi thiết bị được gửi theo ĐÚNG factory nó đang báo trên topic (mỗi thang cấu hình 1 factory).
  • Giữ cửa: master tự nhả sau ttlS → gửi lại holdDoor (actionId mới) mỗi HOLD_REFRESH_SEC trong luồng riêng, không
    phụ thuộc xe nào. Dùng để thử thang / xe mất mạng giữa chừng.

Giao thức (elevator_coord/protocol.py): master nhận callFloor{floor,pulseMs} · holdDoor{ttlS} · releaseDoor ·
fastClose{durationMs} · depart{toFloor,holdTtlS,pulseMs,fastCloseMs} · reset; caller nhận hallCall{direction,ttlS} ·
releaseHall · reset.
"""
import os
import sys
import threading
import time

try:
    from elevator_coord import protocol as P
except ImportError:
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _root not in sys.path:
        sys.path.insert(0, _root)
    from elevator_coord import protocol as P

STATE_FRESH_SEC = 10.0      # state sống trong ngần này giây mới tính "đang gửi tin" (thiết bị gửi ~1 s/lần)
HOLD_TTL_SEC = 30           # ttlS của holdDoor — master tự nhả nếu không được làm mới
HOLD_REFRESH_SEC = 10.0     # làm mới trước khi hết TTL (khớp elevator_coord: ttl_refresh_s)
HOLD_MAX_SEC = 3600
PULSE_MS, FAST_CLOSE_MS = 1000, 3000     # mặc định của elevator_coord (timing)
ACTION_KEEP = 8
RETRY_SEC = 1.0              # chưa thấy actionId trong actionStates sau chừng này → gửi LẠI CÙNG actionId (11 §3.3)
RETRY_MAX = 10               # tối đa 10 lần gửi lại → EXPIRED
QUEUE_MAX_AGE_SEC = 0.0      # 0 = GIỮ lệnh tới khi thiết bị online lại (cabin đóng cửa có thể mất mạng hàng giờ); >0: bỏ lệnh chờ quá lâu (tránh thang tự chạy sau khi nối lại muộn)


class _Dev:
    def __init__(self, factory, elev, device):
        self.factory, self.elev, self.device = factory, elev, device
        self.kind = P.KIND_MASTER if device == "master" else P.KIND_CALLER
        self.conn = None            # chuỗi connectionState gần nhất (ONLINE / CONNECTIONBROKEN / OFFLINE)
        self.conn_at = None         # monotonic
        self.live_at = None         # monotonic: tin state SỐNG (không retained) gần nhất
        self.any_at = None          # wall: tin state bất kỳ
        self.state = None           # P.MasterState | P.CallerState
        self.bad = ""               # lỗi phân tích state gần nhất
        self.diag = {}              # state.diag: rssi, uptimeS…
        self.logged_link = None     # link đã in log gần nhất (chỉ log khi ĐỔI)
        self.logged_dep = None      # (pha depart, tầng đích) đã in log gần nhất


class UelevHub:
    def __init__(self):
        self._lock = threading.RLock()
        self._dev = {}              # (factory, elev, device) -> _Dev
        self._hdr = P.HeaderCounter()
        self._sent = {}             # (elev, device) -> [{"id","type","params","at"}] lệnh gần đây (cho UI đối chiếu actionStates)
        self._acked = {}            # actionId -> trạng thái đã in log (chỉ log khi ĐỔI: RUNNING → FINISHED/FAILED)
        self._pending = {}          # actionId -> lệnh đã gửi nhưng CHƯA thấy phản hồi (gửi lại cùng actionId) / đang chờ thiết bị online
        self._expired = {}          # actionId -> (elev, device, type, thời điểm) lệnh hết số lần gửi lại
        self._retry_thread = None
        self._holds = {}            # elev -> {"device","factory","until","last","close_on_end"}
        self._thread = None
        self._rt = {}               # elev -> trạng thái bài test "1 chuyến xe đi thang" (xem start_ride_test)
        self._rt_cancel = {}        # elev -> threading.Event
        self._rt_confirm = {}       # elev -> threading.Event: người vận hành bấm "Thang đã tới" (chế độ manual)

    # ── nhận tin ─────────────────────────────────────────────────────────────
    def on_message(self, topic: str, payload: bytes, retained: bool = False) -> None:
        parsed = P.parse_topic(topic)
        if parsed is None:
            return
        factory, elev, device, kind = parsed
        if kind not in ("state", "connection"):
            return
        with self._lock:
            d = self._dev.get((factory, elev, device))
            if d is None:
                d = self._dev[(factory, elev, device)] = _Dev(factory, elev, device)
                print(f"[UELEV] thấy thiết bị mới: factory={factory} thang={elev} thiết bị={device} "
                      f"(topic {topic}{', retained' if retained else ''})")
            if kind == "connection":
                try:
                    d.conn = P.parse_connection(payload).upper()
                    d.conn_at = time.monotonic()
                except P.ProtocolError:
                    pass
                self._log_link(d)
                return
            try:
                import json
                obj = json.loads(payload)
                if isinstance(obj, dict):
                    d.kind = P.KIND_MASTER if "elevator" in obj else (P.KIND_CALLER if "caller" in obj else d.kind)
                d.state = P.parse_state(d.kind, payload)
                d.diag = dict(obj.get("diag") or {}) if isinstance(obj, dict) else {}
                d.bad = ""
            except (P.ProtocolError, ValueError) as ex:
                d.bad = str(ex)
                return
            d.any_at = time.time()
            if not retained:
                d.live_at = time.monotonic()
            self._log_link(d)
            self._log_acks(d)
            self._log_depart(d)

    def _log_depart(self, d: _Dev) -> None:
        """Master tự canh depart: log khi đổi pha (closing → calling → transit) và khi master báo ĐÃ TỚI
        (depart=null + doorHoldAuto + floor). Chỉ in khi đổi."""
        st = d.state
        if not isinstance(st, P.MasterState):
            return
        cur = (st.depart_phase, st.depart_to)
        if cur == d.logged_dep:
            return
        prev, d.logged_dep = d.logged_dep, cur
        if st.depart_phase:
            print(f"[UELEV] {d.elev}/master: depart tới tầng {st.depart_to} — pha {st.depart_phase}")
        elif prev and prev[0]:
            if st.door_hold_auto and st.floor is not None:
                print(f"[UELEV] {d.elev}/master: ĐÃ TỚI tầng {st.floor} — master tự giữ cửa (doorHoldAuto, còn {st.hold_ttl_s}s)")
            else:
                print(f"[UELEV] {d.elev}/master: depart kết thúc nhưng CHƯA xác nhận tới nơi (floor={st.floor}, "
                      f"doorHoldAuto={st.door_hold_auto}) — kiểm tra cảm biến tầng/cửa")

    def _log_acks(self, d: _Dev) -> None:
        """In phản hồi của thiết bị cho lệnh TA đã gửi (đổi trạng thái WAITING/RUNNING/FINISHED/FAILED) — để biết lệnh có tới nơi."""
        st = d.state
        if st is None:
            return
        mine = {x["id"] for x in self._sent.get((d.elev, d.device), [])}
        for a in st.action_states:
            if a.action_id in mine and self._acked.get(a.action_id) != a.status:
                self._acked[a.action_id] = a.status
                print(f"[UELEV] ← {d.elev}/{d.device} (factory={d.factory}) phản hồi: {a.action_type} id={a.action_id} "
                      f"{a.status}{' (' + a.result + ')' if a.result else ''}")
        if len(self._acked) > 200:
            self._acked = dict(list(self._acked.items())[-100:])

    def _log_link(self, d: _Dev) -> None:
        """Chỉ in khi trạng thái kết nối của thiết bị ĐỔI (không in mỗi tin state ~1 s/lần)."""
        link = self._link(d)
        if link != d.logged_link:
            d.logged_link = link
            hint = ""
            if link == "offline" and isinstance(d.state, P.MasterState) and d.state.depart_phase:
                hint = " — bình thường nếu cabin đang đóng cửa chạy depart (master mất Wi-Fi, sẽ nối lại khi cửa mở ở tầng đến)"
            print(f"[UELEV] {d.elev}/{d.device} (factory={d.factory}): {link.upper()} (connectionState={d.conn}){hint}")

    # ── trạng thái thiết bị / thang ──────────────────────────────────────────
    @staticmethod
    def _link(d: _Dev):
        now = time.monotonic()
        if d.conn in ("OFFLINE", "CONNECTIONBROKEN"):
            # LWT báo chết; chỉ coi sống lại khi có state SỐNG mới hơn tin LWT
            if not (d.live_at is not None and d.conn_at is not None and d.live_at > d.conn_at):
                return "offline"
        if d.live_at is not None and now - d.live_at <= STATE_FRESH_SEC:
            return "online"
        if d.live_at is not None:
            return "offline"          # từng gửi sống nhưng đã im
        return "stale" if d.any_at is not None else "never"

    def _dev_json(self, d: _Dev) -> dict:
        now = time.monotonic()
        out = {"device": d.device, "kind": d.kind, "factory": d.factory, "link": self._link(d), "conn": d.conn,
               "last_seen_sec": None if d.live_at is None else round(now - d.live_at, 1),
               "bad": d.bad, "errors": [], "actions": [], "diag": dict(d.diag)}
        with self._lock:
            sent = [{"id": p["aid"], "type": p["type"], "state": p["state"], "n": max(0, p["n"] - 1)}
                    for p in self._pending.values() if (p["elev"], p["device"]) == (d.elev, d.device)]
            sent += [{"id": aid, "type": v[2], "state": "expired", "n": RETRY_MAX}
                     for aid, v in self._expired.items() if (v[0], v[1]) == (d.elev, d.device)]
        out["sent"] = sent
        st = d.state
        out["cabin_closed_offline"] = bool(st is not None and isinstance(st, P.MasterState) and st.depart_phase
                                           and out["link"] == "offline")
        if st is not None:
            out["errors"] = [e.get("errorDescription") or e.get("errorType") or str(e) if isinstance(e, dict) else str(e)
                             for e in (st.errors or [])][:5]
            out["actions"] = [{"id": a.action_id, "type": a.action_type, "status": a.status, "result": a.result}
                              for a in st.action_states]
            if isinstance(st, P.MasterState):
                out.update(floor=st.floor, door_open=st.door_open, door_sensor_valid=st.door_sensor_valid,
                           door_hold=st.door_hold, hold_ttl_s=st.hold_ttl_s, fast_close=st.fast_close,
                           door_hold_auto=st.door_hold_auto, depart_phase=st.depart_phase, depart_to=st.depart_to,
                           sensors=dict(st.sensors or {}), call_pulse=st.call_pulse)
            else:
                out.update(floor=st.floor, directions=list(st.directions), hall_active=st.hall_active,
                           hall_direction=st.hall_direction, hall_ttl_s=st.hall_ttl_s, hall_relay=st.hall_relay)
        return out

    def elevators(self) -> dict:
        """{elev_id: {"devices":[...], "factories":[...], "online": bool (master online), "floor", "door_open"...}}"""
        res = {}
        with self._lock:
            for (_f, elev, _dv), d in self._dev.items():
                res.setdefault(elev, []).append(self._dev_json(d))
            holds = {e: {"device": h["device"], "remaining_sec": max(0, int(h["until"] - time.monotonic())),
                         "close_on_end": h["close_on_end"]} for e, h in self._holds.items()}
        out = {}
        for elev, devs in res.items():
            devs.sort(key=lambda x: (x["kind"] != P.KIND_MASTER, x["device"]))
            masters = [x for x in devs if x["kind"] == P.KIND_MASTER]
            m = next((x for x in masters if x["link"] == "online"), masters[0] if masters else None)
            # tin retained cũ của factory cũ (thiết bị đã đổi factory) không tính là "đang gửi dưới 2 factory"
            facs = sorted({x["factory"] for x in devs if x["link"] not in ("stale", "never")}
                          or {x["factory"] for x in devs})
            out[elev] = {"devices": devs, "factories": facs, "factory_mixed": len(facs) > 1,
                         "online": bool(m and m["link"] == "online"), "master": m["device"] if m else None,
                         "floor": m.get("floor") if m else None, "door_open": m.get("door_open") if m else None,
                         "door_hold": m.get("door_hold") if m else None, "hold": holds.get(elev),
                         "ride_test": self.ride_test_status(elev)}
        return out

    def device_factory(self, elev: str, device: str, prefer: str = ""):
        """Factory của thiết bị (ưu tiên bản đang sống, rồi bản khai báo `prefer`)."""
        with self._lock:
            cands = [d for (f, e, dv), d in self._dev.items() if e == elev and dv == device]
            if not cands:
                return None
            cands.sort(key=lambda d: (self._link(d) != "online", d.factory != prefer))
            return cands[0].factory

    # ── gửi lệnh ─────────────────────────────────────────────────────────────
    def send(self, elev: str, device: str, action_type: str, params=None, prefer_factory: str = "") -> dict:
        factory = self.device_factory(elev, device, prefer_factory)
        if factory is None:
            return {"ok": False, "error": f"Chưa thấy thiết bị {elev}/{device} trên broker (không biết factory để gửi)"}
        aid = P.new_action_id()
        key = f"{factory}/{elev}/{device}/instantActions"
        hdr = P.build_header(self._hdr.next(key), time.time(), factory, elev, device)
        payload = P.build_instant_actions(hdr, [P.action_dict(action_type, aid, params)])
        quiet = action_type == P.ACT_HOLD_DOOR and bool(self._holds.get(elev))        # holdDoor làm mới mỗi 10 s: không log lặp
        pend = {"aid": aid, "elev": elev, "device": device, "factory": factory, "type": action_type, "params": params or {},
                "topic": P.topic_actions(factory, elev, device), "payload": payload, "n": 0, "sent_at": 0.0,
                "queued_at": time.monotonic(), "state": "queued", "quiet": quiet}
        with self._lock:
            lst = self._sent.setdefault((elev, device), [])
            lst.append({"id": aid, "type": action_type, "params": params or {}, "at": time.time()})
            del lst[:-ACTION_KEEP]
            self._pending[aid] = pend
            dev = self._dev.get((factory, elev, device))
            online = dev is not None and self._link(dev) == "online"
            if online:
                self._claim(pend)         # chiếm lượt gửi đầu trong khoá: luồng gửi lại thấy n>=1, không publish đúp
            if self._retry_thread is None or not self._retry_thread.is_alive():
                self._retry_thread = threading.Thread(target=self._retry_loop, name="uelev-retry", daemon=True)
                self._retry_thread.start()
        if not online:
            # 11 §3.2/4: thiết bị offline → GIỮ lệnh trong hàng chờ, gửi khi ONLINE lại (không tính là lần gửi lặp)
            print(f"[UELEV] ⏳ {elev}/{device} (factory={factory}) đang offline — giữ lệnh {action_type} id={aid}, "
                  f"gửi khi thiết bị online" + (f" (tối đa {QUEUE_MAX_AGE_SEC:.0f}s)" if QUEUE_MAX_AGE_SEC > 0 else ""))
            return {"ok": True, "queued": True, "action_id": aid, "factory": factory, "device": device, "type": action_type}
        rc = self._publish_raw(pend)
        return {"ok": rc == 0, "action_id": aid, "factory": factory, "device": device, "type": action_type}

    def _claim(self, pend: dict) -> None:
        """Ghi nhận 1 lần gửi (gọi TRONG khoá, TRƯỚC khi publish): đếm lần gửi + mốc thời gian."""
        pend["n"] += 1
        pend["sent_at"] = time.monotonic()
        pend["state"] = "sent" if pend["n"] == 1 else "retry"

    def _publish_raw(self, pend: dict) -> int:
        import mqtt_client
        res = mqtt_client.client.publish(pend["topic"], pend["payload"], qos=1)
        if pend["n"] == 1 and not pend["quiet"]:
            print(f"[UELEV] → {pend['elev']}/{pend['device']} (factory={pend['factory']}) gửi: {pend['type']} "
                  f"id={pend['aid']} {pend['params'] or ''} rc={res.rc}")
        return res.rc

    def _retry_loop(self) -> None:
        """Gửi lại CÙNG actionId mỗi RETRY_SEC khi chưa thấy nó trong actionStates (tối đa RETRY_MAX lần → EXPIRED).
        Thiết bị offline thì giữ lệnh, KHÔNG đếm lần gửi lặp (cabin đóng cửa mất Wi-Fi là bình thường). Thiết bị khử trùng theo
        actionId nên gửi lại không chạy lệnh hai lần."""
        while True:
            time.sleep(0.5)
            with self._lock:
                items = list(self._pending.values())
            if not items:
                with self._lock:
                    if not self._pending:
                        self._retry_thread = None
                        return
                continue
            now = time.monotonic()
            for p in items:
                try:
                    with self._lock:
                        d = self._dev.get((p["factory"], p["elev"], p["device"]))
                        acked = bool(d and d.state and any(a.action_id == p["aid"] for a in d.state.action_states))
                        link = self._link(d) if d else "never"
                    if acked:
                        with self._lock:
                            self._pending.pop(p["aid"], None)
                        continue
                    if link != "online":
                        if QUEUE_MAX_AGE_SEC > 0 and p["n"] == 0 and now - p["queued_at"] > QUEUE_MAX_AGE_SEC:
                            self._expire(p, f"thiết bị offline quá {QUEUE_MAX_AGE_SEC:.0f}s — bỏ lệnh chưa gửi")
                        continue
                    with self._lock:
                        if p["aid"] not in self._pending:
                            continue
                        if p["n"] == 0:
                            self._claim(p)
                            action = "first"
                        elif now - p["sent_at"] >= RETRY_SEC:
                            if p["n"] > RETRY_MAX:
                                action = "expire"
                            else:
                                self._claim(p)
                                action = "retry"
                        else:
                            action = None
                    if action == "first":
                        self._publish_raw(p)
                    elif action == "expire":
                        self._expire(p, f"đã gửi lại {RETRY_MAX} lần mà thiết bị không phản hồi")
                    elif action == "retry":
                        self._publish_raw(p)
                        print(f"[UELEV] ↻ {p['elev']}/{p['device']} chưa thấy phản hồi cho {p['type']} id={p['aid']} sau "
                              f"{RETRY_SEC:g}s → gửi lại lần {p['n'] - 1}/{RETRY_MAX} (cùng actionId)")
                except Exception as ex:
                    print(f"[UELEV] gửi lại lỗi: {type(ex).__name__}: {ex}")

    def _expire(self, p: dict, why: str) -> None:
        with self._lock:
            self._pending.pop(p["aid"], None)
            self._expired[p["aid"]] = (p["elev"], p["device"], p["type"], time.monotonic())
            for k in [k for k, v in self._expired.items() if time.monotonic() - v[3] > 120][:50]:
                self._expired.pop(k, None)
        print(f"[UELEV] ✗ EXPIRED {p['elev']}/{p['device']} {p['type']} id={p['aid']}: {why}")

    # ── giữ cửa (làm mới holdDoor định kỳ) ───────────────────────────────────
    def hold(self, elev: str, duration_sec: float, close_on_end: bool = True, prefer_factory: str = "") -> dict:
        duration_sec = max(5.0, min(float(duration_sec), HOLD_MAX_SEC))
        r = self.send(elev, "master", P.ACT_HOLD_DOOR, {"ttlS": HOLD_TTL_SEC}, prefer_factory)
        if not r["ok"]:
            return r
        with self._lock:
            self._holds[elev] = {"device": "master", "factory": r["factory"], "until": time.monotonic() + duration_sec,
                                 "last": time.monotonic(), "close_on_end": close_on_end, "prefer": prefer_factory}
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._hold_loop, name="uelev-hold", daemon=True)
                self._thread.start()
        return {**r, "duration_sec": duration_sec}

    def release(self, elev: str, prefer_factory: str = "", fast_close: bool = True) -> dict:
        with self._lock:
            had = self._holds.pop(elev, None) is not None
        r = self.send(elev, "master", P.ACT_RELEASE_DOOR, None, prefer_factory)
        if r["ok"] and fast_close:
            self.send(elev, "master", P.ACT_FAST_CLOSE, {"durationMs": FAST_CLOSE_MS}, prefer_factory)
        return {**r, "was_holding": had}

    def drop_hold(self, elev: str) -> bool:
        """Bỏ giữ cửa tay (không gửi gì) — dùng khi chuỗi đi thang của xe tiếp quản thang."""
        with self._lock:
            return self._holds.pop(elev, None) is not None

    def go_to(self, elev: str, floor: int, hold_s: float, prefer_factory: str = "") -> dict:
        """Đưa thang tới `floor` và giữ cửa mở. Thang ĐÃ ở tầng đó thì `depart` bị thiết bị từ chối (already_at_floor, không
        đụng relay nào) → thay bằng holdDoor để cửa mở/giữ mở tại chỗ. Trả {"ok", "mode": "depart"|"hold_here", "action_id"...}."""
        self.drop_hold(elev)            # holdDoor tay đang làm mới sẽ phá chuỗi `closing` của depart
        m = self._master_json(elev, prefer_factory)
        if m is not None and m.get("floor") == floor and m.get("link") == "online":
            r = self.hold(elev, hold_s, True, prefer_factory)
            return {**r, "mode": "hold_here"}
        r = self.send(elev, "master", P.ACT_DEPART, {"toFloor": floor, "holdTtlS": int(min(max(hold_s, 5), 600)),
                                                      "pulseMs": PULSE_MS, "fastCloseMs": FAST_CLOSE_MS}, prefer_factory)
        return {**r, "mode": "depart"}

    # ── Bài test "1 chuyến": giả lập AGV gọi thang đi từ tầng A tới tầng B ───────────────────────────────
    # Chuỗi như xe thật (elevator_coord): gọi thang tới A → thang mở cửa, báo về → (xe vào cabin: trễ board_s)
    # → đóng cửa, chạy tới B → thang mở cửa, báo về → (xe ra: trễ exit_s) → đóng cửa, báo đã đóng. Chạy ở server.
    RT_ARRIVE_TIMEOUT = 150.0
    RT_CLOSE_TIMEOUT = 25.0

    def _master_json(self, elev: str, prefer: str = ""):
        with self._lock:
            cands = [d for (_f, e, dv), d in self._dev.items() if e == elev and d.kind == P.KIND_MASTER]
            if not cands:
                return None
            cands.sort(key=lambda d: (self._link(d) != "online", d.factory != prefer))
            return self._dev_json(cands[0])

    def _device_json(self, elev: str, device: str, prefer: str = ""):
        with self._lock:
            cands = [d for (_f, e, dv), d in self._dev.items() if e == elev and dv == device]
            if not cands:
                return None
            cands.sort(key=lambda d: (self._link(d) != "online", d.factory != prefer))
            return self._dev_json(cands[0])

    @staticmethod
    def _arrived(m: dict, floor: int) -> bool:
        """Thang đã tới `floor`, hết chạy lệnh depart và cửa đã mở/đang được giữ."""
        # Dấu hiệu firmware (09 §6.3): depart=null + doorHoldAuto=true + floor = tầng đích (master tự phát hiện, KHÔNG có
        # thông báo "đã tới" riêng). Nhận thêm cửa mở / đang giữ cửa để dùng được cả khi cảm biến cửa bypass.
        if not m or m.get("floor") != floor or m.get("depart_phase"):
            return False
        return bool(m.get("door_hold_auto")) or m.get("door_open") is True or (m.get("door_open") is None and bool(m.get("door_hold")))

    def ride_test_status(self, elev: str):
        with self._lock:
            t = self._rt.get(elev)
            return None if t is None else {**t, "steps": [dict(x) for x in t["steps"]]}

    ARRIVE_MODES = ("sensor", "timer", "manual")

    def start_ride_test(self, elev: str, from_floor: int, to_floor: int, board_s: float = 3.5,
                        exit_s: float = 3.5, prefer_factory: str = "", arrive_mode: str = "sensor",
                        travel_s: float = 10.0) -> dict:
        """arrive_mode — cách biết "thang đã tới tầng":
            sensor: master tự báo qua cảm biến tầng (mặc định, như xe thật);
            timer : KHÔNG có cảm biến → coi như tới sau `travel_s` giây (chỉ để thử chuỗi lệnh + relay, không xác nhận gì);
            manual: KHÔNG có cảm biến → người vận hành nhìn thang thật rồi bấm "Thang đã tới" (confirm_arrival)."""
        if arrive_mode not in self.ARRIVE_MODES:
            return {"ok": False, "error": f"arrive_mode phải là một trong {self.ARRIVE_MODES}"}
        with self._lock:
            cur = self._rt.get(elev)
            if cur and cur["state"] == "running":
                return {"ok": False, "error": f"Thang {elev} đang chạy bài test — chờ xong hoặc hủy"}
            m = self._master_json(elev, prefer_factory)
            if m is None or m["link"] != "online":
                return {"ok": False, "error": f"Master của thang {elev} chưa kết nối — không chạy được bài test"}
            ev = threading.Event()
            self._rt_cancel[elev] = ev
            self._rt_confirm[elev] = threading.Event()
            self._rt[elev] = {"state": "running", "from": from_floor, "to": to_floor, "started": time.time(),
                              "board_s": board_s, "exit_s": exit_s, "steps": [], "arrive_mode": arrive_mode,
                              "travel_s": travel_s, "awaiting": None}
        self._holds.pop(elev, None)          # bỏ giữ cửa tay đang chạy (nếu có)
        threading.Thread(target=self._ride_test_run, name=f"uelev-ridetest-{elev}", daemon=True,
                         args=(elev, from_floor, to_floor, board_s, exit_s, prefer_factory, ev, arrive_mode, travel_s)).start()
        return {"ok": True}

    def confirm_arrival(self, elev: str) -> bool:
        """Chế độ manual: người vận hành xác nhận thang đã tới tầng đang chờ. False nếu không có gì đang chờ xác nhận."""
        with self._lock:
            t = self._rt.get(elev)
            if not t or t["state"] != "running" or not t.get("awaiting"):
                return False
            self._rt_confirm[elev].set()
            return True

    def cancel_ride_test(self, elev: str, prefer_factory: str = "") -> bool:
        ev = self._rt_cancel.get(elev)
        t = self.ride_test_status(elev)
        if ev is None or t is None or t["state"] != "running":
            return False
        ev.set()
        return True

    def _rt_step(self, elev: str, text: str, status: str = "run") -> int:
        """Thêm bước; trả chỉ số để đổi trạng thái sau (run → ok/fail). Mỗi bước đủ để in log và hiện lên UI."""
        with self._lock:
            t = self._rt[elev]
            t["steps"].append({"text": text, "status": status, "at": round(time.time() - t["started"], 1)})
            print(f"[UELEV-TEST] {elev} +{t['steps'][-1]['at']}s {status.upper()}: {text}")
            return len(t["steps"]) - 1

    def _rt_set(self, elev: str, idx: int, status: str, text: str = "") -> None:
        with self._lock:
            st = self._rt[elev]["steps"][idx]
            st["status"] = status
            if text:
                st["text"] = text
            st["at"] = round(time.time() - self._rt[elev]["started"], 1)
            print(f"[UELEV-TEST] {elev} +{st['at']}s {status.upper()}: {st['text']}")

    RT_NOFLOOR_SEC = 12.0       # master KHÔNG đọc được tầng VÀ báo lỗi cảm biến tầng sau chừng này giây → dừng sớm (chờ vô ích)

    @staticmethod
    def _floor_fault(m: dict) -> bool:
        """Master báo lỗi cảm biến tầng (vd ">=2 cam bien tang active", FLOOR_SENSOR_INCONSISTENT). floor=null thuần túy KHÔNG
        phải lỗi: giữa 2 tầng cabin không chạm cảm biến nào (tài liệu firmware: 0/null nếu chưa xác định)."""
        txt = " ".join(str(x) for x in (m.get("errors") or [])).lower()
        return "tang" in txt and ("cam bien" in txt or "sensor" in txt) or "floor_sensor" in txt

    def _rt_wait(self, elev, prefer, cond, timeout, ev, watch_action=None, device="master", keepalive=None,
                 need_floor=False):
        """Chờ cond(json thiết bị) đúng. Trả (ok, lý do). Dừng sớm nếu hủy / thiết bị báo FAILED cho lệnh `watch_action`
        / (need_floor) master không đọc được tầng. `keepalive()` được gọi mỗi HOLD_REFRESH_SEC (làm mới hallCall/holdDoor)."""
        t0 = last_ka = time.monotonic()
        end = t0 + timeout
        while time.monotonic() < end:
            if ev.is_set():
                return False, "đã hủy"
            d = self._device_json(elev, device, prefer)
            if d is not None:
                if watch_action:
                    a = next((x for x in d.get("actions", []) if x["id"] == watch_action), None)
                    if a and a["status"] == P.ST_FAILED:
                        return False, f"thiết bị từ chối lệnh: {a.get('result') or 'FAILED'}"
                if cond(d):
                    return True, ""
            if need_floor:
                mj = d if device == "master" else self._master_json(elev, prefer)
                if (mj is not None and mj.get("floor") is None and self._floor_fault(mj)
                        and time.monotonic() - t0 >= self.RT_NOFLOOR_SEC):
                    return False, "master không xác định được tầng"
            if keepalive and time.monotonic() - last_ka >= HOLD_REFRESH_SEC:
                last_ka = time.monotonic()
                keepalive()
            time.sleep(0.3)
        return False, "quá thời gian chờ"

    def _rt_sleep(self, secs: float, ev) -> bool:
        end = time.monotonic() + secs
        while time.monotonic() < end:
            if ev.is_set():
                return False
            time.sleep(0.2)
        return True

    def _ride_test_run(self, elev, a, b, board_s, exit_s, prefer, ev, arrive_mode="sensor", travel_s=10.0) -> None:
        def finish(state, text):
            with self._lock:
                self._rt[elev]["state"] = state
            self._rt_step(elev, text, "ok" if state == "done" else ("fail" if state == "failed" else "info"))

        hall_dev = [None]          # bộ gọi đang bấm nút gọi (cần nhả nếu bài test dừng giữa chừng)

        def hint(m):
            if m is None:
                return "master không còn báo tin"
            if m.get("floor") is None:
                sn = m.get("sensors") or {}
                raw = ", ".join(f"{k}={v}" for k, v in sorted(sn.items()))
                return ("master chưa đọc được tầng hiện tại — cảm biến tầng " + (raw or "không rõ")
                        + (" (≥2 cảm biến cùng active nên không xác định được tầng; sửa cảm biến rồi chạy lại)" if raw else "")
                        + " (kiểm tra cảm biến tầng)")
            return f"master đang ở tầng {m.get('floor')}, cửa {'mở' if m.get('door_open') else 'chưa mở/chưa rõ'}"

        confirm_ev = self._rt_confirm[elev]

        def await_arrival(floor, sensor_cond, watch_action, keepalive):
            """Chờ thang tới `floor` theo arrive_mode. Trả (ok, lý do)."""
            if arrive_mode == "timer":
                i = self._rt_step(elev, f"Thang đang chạy tới tầng {floor}… (không dùng cảm biến: chờ {travel_s:g}s rồi coi như đã tới)")
                t_end = time.monotonic() + travel_s
                ok, why = self._rt_wait(elev, prefer, lambda m: time.monotonic() >= t_end, travel_s + 5, ev, watch_action,
                                        keepalive=keepalive)
                if ok:
                    self._rt_set(elev, i, "ok", f"GIẢ ĐỊNH thang đã tới tầng {floor} sau {travel_s:g}s — KHÔNG có xác nhận từ cảm biến")
                else:
                    self._rt_set(elev, i, "fail", f"Thang không chạy tiếp được: {why}")
                return ok, why
            if arrive_mode == "manual":
                i = self._rt_step(elev, f"Chờ bạn xác nhận: thang đã tới tầng {floor}? (nhìn thang thật rồi bấm “Thang đã tới”)")
                confirm_ev.clear()
                with self._lock:
                    self._rt[elev]["awaiting"] = {"floor": floor}
                try:
                    ok, why = self._rt_wait(elev, prefer, lambda m: confirm_ev.is_set(), 600.0, ev, watch_action,
                                            keepalive=keepalive)
                finally:
                    with self._lock:
                        self._rt[elev]["awaiting"] = None
                if ok:
                    self._rt_set(elev, i, "ok", f"Bạn đã xác nhận thang tới tầng {floor}")
                else:
                    self._rt_set(elev, i, "fail", f"Chưa xác nhận được thang tới tầng {floor}: {why}")
                return ok, why
            i = self._rt_step(elev, f"Thang đang chạy tới tầng {floor}…")
            ok, why = self._rt_wait(elev, prefer, sensor_cond, self.RT_ARRIVE_TIMEOUT, ev, watch_action, device="master",
                                    need_floor=True, keepalive=keepalive)
            if ok:
                self._rt_set(elev, i, "ok", f"Thang đã tới tầng {floor}, cửa mở — đã báo về server")
            else:
                self._rt_set(elev, i, "fail", f"Thang chưa tới tầng {floor}: {why} — {hint(self._master_json(elev, prefer))}")
            return ok, why

        def fail_arrive(floor, why):
            return finish("cancelled" if why == "đã hủy" else "failed", "Dừng bài test")

        try:
            # 1) AGV bấm nút gọi thang ở bộ gọi tầng A (hallCall) → thang tới, mở cửa → giữ cửa → nhả nút gọi
            direction = "UP" if b > a else "DN"
            caller = f"call{a}"
            dirvi = "lên" if direction == "UP" else "xuống"
            cj = self._device_json(elev, caller, prefer)
            hp = {"direction": direction, "ttlS": 30}
            if cj is None or cj["link"] != "online":
                i = self._rt_step(elev, f"Bộ gọi {caller} (tầng {a}) chưa online — gọi thẳng cabin bằng master")
                r = self.go_to(elev, a, 120, prefer)
                if not r["ok"]:
                    self._rt_set(elev, i, "fail", f"Không gửi được lệnh gọi thang: {r.get('error') or 'lỗi MQTT'}")
                    return finish("failed", "Dừng bài test")
                self._rt_set(elev, i, "ok", f"Gọi thẳng cabin tới tầng {a} bằng master (bộ gọi {caller} offline nên không có đèn gọi)"
                             + (" — thang đang sẵn ở tầng này" if r["mode"] == "hold_here" else ""))
                if r["mode"] != "hold_here":
                    ok, why = await_arrival(a, lambda m: self._arrived(m, a), r["action_id"], None)
                    if not ok:
                        return fail_arrive(a, why)
            else:
                hall_dev[0] = caller
                i = self._rt_step(elev, f"Xe bấm nút gọi thang đi {dirvi} tại tầng {a} (bộ gọi {caller})")
                r = self.send(elev, caller, P.ACT_HALL_CALL, hp, prefer)
                if not r["ok"]:
                    self._rt_set(elev, i, "fail", f"Không gửi được lệnh bấm nút gọi: {r.get('error') or 'lỗi MQTT'}")
                    return finish("failed", "Dừng bài test")
                ok, why = self._rt_wait(elev, prefer, lambda d: bool(d.get("hall_active")), 10.0, ev, r["action_id"], device=caller)
                if not ok:
                    self._rt_set(elev, i, "fail", f"Bộ gọi {caller} không bật nút gọi: {why}")
                    return finish("cancelled" if why == "đã hủy" else "failed", "Dừng bài test")
                self._rt_set(elev, i, "ok", f"Bộ gọi {caller} đã nhận: relay đang bấm nút gọi {dirvi} (đèn gọi sáng) — đã báo về server")
                ok, why = await_arrival(
                    a, lambda m: m.get("floor") == a and m.get("door_open") is not False and not m.get("depart_phase"),
                    None, lambda: self.send(elev, caller, P.ACT_HALL_CALL, hp, prefer))
                if not ok:
                    return fail_arrive(a, why)
            i = self._rt_step(elev, "Giữ cửa mở để xe vào")
            hr = self.hold(elev, board_s + 90, True, prefer)
            if not hr["ok"]:
                self._rt_set(elev, i, "fail", f"Không gửi được lệnh giữ cửa: {hr.get('error') or 'lỗi MQTT'}")
                return finish("failed", "Dừng bài test")
            ok, why = self._rt_wait(elev, prefer, lambda m: bool(m.get("door_hold")), 10.0, ev, hr["action_id"])
            if not ok:
                self._rt_set(elev, i, "fail", f"Thang chưa xác nhận giữ cửa: {why}")
                return finish("cancelled" if why == "đã hủy" else "failed", "Dừng bài test")
            if hall_dev[0]:
                self.send(elev, hall_dev[0], P.ACT_RELEASE_HALL, None, prefer)        # đã tới nơi: nhả nút gọi
                hall_dev[0] = None
            self._rt_set(elev, i, "ok", "Đang giữ cửa mở" + (", đã nhả nút gọi ở bộ gọi" if cj and cj["link"] == "online" else ""))

            # 2) AGV đi vào cabin
            i = self._rt_step(elev, f"Xe đi vào cabin (mô phỏng {board_s:g}s)…")
            if not self._rt_sleep(board_s, ev):
                self._rt_set(elev, i, "fail", "Đã hủy")
                return finish("cancelled", "Đã hủy — thả giữ cửa")
            self._rt_set(elev, i, "ok", f"Xe đã vào cabin ({board_s:g}s)")

            # 3) đóng cửa, đi tới tầng B
            i = self._rt_step(elev, f"Đóng cửa và đi tới tầng {b}")
            r = self.go_to(elev, b, 120, prefer)
            if not r["ok"]:
                self._rt_set(elev, i, "fail", f"Không gửi được lệnh đi tầng {b}: {r.get('error') or 'lỗi MQTT'}")
                return finish("failed", "Dừng bài test")
            self._rt_set(elev, i, "ok", f"Đã gửi lệnh: đóng cửa và đi tới tầng {b}")
            if r["mode"] != "hold_here":
                ok, why = await_arrival(b, lambda m: self._arrived(m, b), r["action_id"], None)
                if not ok:
                    return fail_arrive(b, why)

            # ARRIVED (như elevator_coord): FMS gửi holdDoor, khi lệnh xong và doorHold=true mới cho xe ra (EXIT_ALLOWED);
            # trong lúc xe ra, holdDoor được làm mới định kỳ (hub.hold)
            i = self._rt_step(elev, "Giữ cửa mở để xe ra (holdDoor)")
            hr = self.hold(elev, exit_s + 90, True, prefer)
            if not hr["ok"]:
                self._rt_set(elev, i, "fail", f"Không gửi được lệnh giữ cửa: {hr.get('error') or 'lỗi MQTT'}")
                return finish("failed", "Dừng bài test")
            ok, why = self._rt_wait(elev, prefer, lambda m: bool(m.get("door_hold")), 10.0, ev, hr["action_id"])
            if not ok:
                self._rt_set(elev, i, "fail", f"Thang chưa xác nhận giữ cửa ở tầng {b}: {why}")
                return finish("cancelled" if why == "đã hủy" else "failed", "Dừng bài test")
            self._rt_set(elev, i, "ok", f"Đã giữ cửa ở tầng {b} — cho phép xe ra (EXIT_ALLOWED)")

            # 4) AGV đi ra
            i = self._rt_step(elev, f"Xe đi ra khỏi cabin (mô phỏng {exit_s:g}s)…")
            if not self._rt_sleep(exit_s, ev):
                self._rt_set(elev, i, "fail", "Đã hủy")
                return finish("cancelled", "Đã hủy — thả giữ cửa")
            self._rt_set(elev, i, "ok", f"Xe đã ra khỏi cabin ({exit_s:g}s)")

            # 5) đóng cửa, báo đã đóng
            i = self._rt_step(elev, "Đóng cửa thang")
            self.drop_hold(elev)
            self.send(elev, "master", P.ACT_RELEASE_DOOR, None, prefer)
            fc = self.send(elev, "master", P.ACT_FAST_CLOSE, {"durationMs": FAST_CLOSE_MS}, prefer)

            def closed(m):
                if m.get("door_open") is False and m.get("door_sensor_valid", True):
                    return True
                a_ = next((x for x in m.get("actions", []) if x["id"] == fc.get("action_id")), None)
                return bool(a_ and a_["status"] == P.ST_FINISHED and not m.get("door_hold"))

            ok, why = self._rt_wait(elev, prefer, closed, self.RT_CLOSE_TIMEOUT, ev, fc.get("action_id"))
            if not ok:
                self._rt_set(elev, i, "fail", f"Chưa xác nhận được cửa đã đóng: {why} — {hint(self._master_json(elev, prefer))}")
                return finish("cancelled" if why == "đã hủy" else "failed", "Dừng bài test")
            self._rt_set(elev, i, "ok", f"Thang đã đóng cửa ở tầng {b} — đã báo về server")
            finish("done", f"HOÀN TẤT 1 chuyến: tầng {a} → tầng {b}")
        except Exception as ex:
            import traceback
            traceback.print_exc()
            finish("failed", f"Lỗi nội bộ: {type(ex).__name__}: {ex}")
        finally:
            with self._lock:
                running = self._rt.get(elev, {}).get("state") == "running"
            if hall_dev[0]:
                try:
                    self.send(elev, hall_dev[0], P.ACT_RELEASE_HALL, None, prefer)
                except Exception:
                    pass
            if self._rt.get(elev, {}).get("state") in ("cancelled", "failed"):
                self.drop_hold(elev)
                try:                                    # luôn nhả giữ cửa khi dừng giữa chừng
                    self.send(elev, "master", P.ACT_RELEASE_DOOR, None, prefer)
                except Exception:
                    pass

    def _hold_loop(self) -> None:
        while True:
            time.sleep(1.0)
            now = time.monotonic()
            with self._lock:
                items = list(self._holds.items())
            if not items:
                return
            for elev, h in items:
                try:
                    if now >= h["until"]:
                        with self._lock:
                            self._holds.pop(elev, None)
                        print(f"[UELEV] {elev}: hết giờ giữ cửa — nhả" + (" + đóng nhanh" if h["close_on_end"] else ""))
                        self.send(elev, "master", P.ACT_RELEASE_DOOR, None, h.get("prefer", ""))
                        if h["close_on_end"]:
                            self.send(elev, "master", P.ACT_FAST_CLOSE, {"durationMs": FAST_CLOSE_MS}, h.get("prefer", ""))
                    elif now - h["last"] >= HOLD_REFRESH_SEC:
                        h["last"] = now
                        self.send(elev, "master", P.ACT_HOLD_DOOR, {"ttlS": HOLD_TTL_SEC}, h.get("prefer", ""))
                except Exception as ex:
                    print(f"[UELEV] giữ cửa {elev} lỗi: {type(ex).__name__}: {ex}")


uelev_hub = UelevHub()
