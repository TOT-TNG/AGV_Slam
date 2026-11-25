"""
Điều phối THANG MÁY cho Line AGV — thiết kế GIỐNG cửa tự động (door_coordinator.py).

Thang là 1 "cánh cửa di động": thiết bị thang giao tiếp qua MQTT cùng kiểu với cửa tự động
(xin mở → chờ đúng trạng thái "open" → xe đi tiếp → xong thì đóng), chỉ khác là lệnh mở kèm TẦNG:

    elevator/v1/{factory}/{elevator_id}/cmd     Server → thang   {"c":"open","floor":2} | {"c":"close"}
    elevator/v1/{factory}/{elevator_id}/state   Thang → server   {"state":"open","floor":2}   (RETAINED)

    "open" + floor=L : đi tới tầng L (số tầng = "Số tầng" của tầng trong Map Editor) rồi mở cửa. Đã ở tầng
                       L + cửa mở sẵn → chỉ cần publish lại state "open". Cửa đang mở ở tầng khác → thang tự
                       đóng cửa trước khi chạy (server vẫn gửi "close" tường minh trước chuyến đi).
    "close"          : đóng cửa.
    state            : closed | opening | open | closing | moving | error  (+ "floor" = tầng hiện tại/vừa tới).
                       Server chỉ coi là mở xong khi nhận đúng state="open" VÀ floor đúng tầng cần.
    Lệnh lặp lại phải an toàn (idempotent) — server gửi lại nếu quá ELEV_OPEN_TIMEOUT giây không thấy "open".

Mỗi thang là TÀI NGUYÊN ĐỘC QUYỀN: 1 xe 1 lúc (cabin 1 cửa, vào hướng nào ra hướng đó). Xe xin sau xếp hàng.
QUAN TRỌNG: xe phải ĐẶT TRƯỚC thang (elev_book) NGAY ĐẦU chuỗi, trước khi đi tới node chờ — xe xếp hàng đứng
yên ở chỗ cũ, KHÔNG tới node chờ cạnh cabin. Nếu cho xe xếp hàng đứng ở node chờ thì khi xe đang dùng thang ra ở
đúng tầng đó, lối ra duy nhất (qua node chờ) bị chính xe xếp hàng chắn → kẹt cả hai (đã gặp trong mô phỏng).
Toàn bộ chuyến đi là chuỗi lệnh hàng đợi do floor_nav.decompose() sinh ra; module này xử lý 4 lệnh thang:

  elev_book    E@A        book        : đặt trước; được cấp (hoàn tất lệnh) khi thang rảnh, nếu không thì xếp hàng.
  elev_call    E@A        request_open: gọi thang tới tầng A + mở cửa; hoàn tất khi state=open@A.
  elev_ride    E@A>B#W_B  start_ride : xe đã đứng trong cabin → close → "open floor=B" → khi open@B: đặt lại vị
                          trí xe (current_tag = cabin ở tầng B, prev_tag = W_B → logic điểm cụt có sẵn tự cho xe
                          ra theo hướng ngược lúc vào), gửi lệnh 'locate' cho xe, hoàn tất.
  elev_release E          release   : xe đã ra khỏi cabin → nhả thang (cấp cho xe xếp hàng kế, hoặc đóng cửa).
"""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field

ELEV_OPEN_TIMEOUT     = 45.0   # giây chờ state="open" đúng tầng (thang chạy tầng xa lâu hơn cửa thường)
ELEV_OPEN_MAX_RETRIES = 2
ELEV_CLOSE_TIMEOUT    = 20.0
HOLD_RESEND_SEC       = 10.0   # giữ cửa: gửi lại "open" mỗi N giây (idempotent theo giao thức → chỉ publish lại state)
HOLD_MAX_SEC          = 3600.0


def _tagval(x):
    s = str(x)
    return int(s) if s.lstrip("-").isdigit() else s


@dataclass
class _Elev:
    state:   str = "unknown"
    level:   int | None = None            # tầng (số) thiết bị báo
    owner:   str | None = None
    phase:   str = ""                      # booked | call | board | close | move | exit
    call_floor: str = ""                  # id tầng đang gọi tới
    ride:    dict = field(default_factory=dict)   # {from,to,w_b,cab_a,cab_b,to_level}
    queue:   deque = field(default_factory=deque)  # (agv_id, floor_id, kind: 'book'|'call') đang xếp hàng
    stale_since: float = 0.0               # mốc chủ thang không còn lệnh thang nào (dọn booking mồ côi)
    sent_at: float = 0.0
    retries: int = 0
    last_cmd: tuple = ()                   # (cmd, level) gửi gần nhất — để gửi lại


class ElevatorCoordinator:
    def __init__(self):
        self._el: dict[str, _Elev] = {}
        self._lock = threading.RLock()
        self._qclaims: dict[tuple, tuple] = {}     # (eid, tầng) -> (agv_id, mốc thời gian): xe đang đi tới/đứng ở điểm xếp hàng
        self._holds: dict[str, dict] = {}          # eid -> {level, until, close_on_end, last_sent}: giữ cửa thủ công
        self._hold_thread: threading.Thread | None = None

    # ── Điểm xếp hàng: mỗi (thang, tầng) chỉ 1 xe được tới đứng chờ ───────────────
    QCLAIM_TTL = 300.0

    def claim_queue_point(self, eid: str, floor_id: str, agv_id: str, node: str = "") -> bool:
        """True nếu xe được đi tới điểm xếp hàng. Đã có xe KHÁC đang tới/đứng ở đó → False: xe này đặt thang ngay tại
        chỗ và đứng chờ (không tranh cùng 1 node với xe kia — tranh node làm bộ tránh đối đầu đẩy xe vòng vào khu vực thang).
        Claim nhả khi xe được cấp thang (_take) hoặc sau QCLAIM_TTL."""
        with self._lock:
            k = (eid, floor_id, node) if node else (eid, floor_id)
            cur = self._qclaims.get(k)
            if cur and cur[0] != agv_id and time.monotonic() - cur[1] < self.QCLAIM_TTL:
                print(f"[ELEVATOR] {eid}: điểm xếp hàng {node or ('tầng ' + str(floor_id))} đã có {cur[0]} — {agv_id} không tranh")
                return False
            self._qclaims[k] = (agv_id, time.monotonic())
            return True

    def _get(self, eid: str) -> _Elev:
        if eid not in self._el:
            self._el[eid] = _Elev()
        return self._el[eid]

    # ── Gửi lệnh tới thiết bị ────────────────────────────────────────────────
    def _send(self, eid: str, cmd: str, level: int | None = None) -> None:
        e = self._get(eid)
        e.last_cmd = (cmd, level)
        e.sent_at = time.monotonic()
        try:
            from mqtt_client import send_elevator_command
            send_elevator_command(eid, cmd, level)
        except Exception as ex:
            print(f"[ELEVATOR] {eid}: gửi lệnh {cmd} lỗi: {ex}")

    def _complete(self, agv_id: str, notes: str) -> None:
        """Hoàn tất lệnh thang đang chạy của xe → hàng đợi tự dispatch lệnh kế (giống resume_after_door)."""
        try:
            from task_queue import agv_task_queue
            agv_task_queue.on_agv_completed(agv_id, notes=notes)
        except Exception as ex:
            print(f"[ELEVATOR] hoàn tất lệnh {agv_id} lỗi: {ex}")

    # ── Giữ cửa thủ công (Quản lý AGV → Điều khiển thủ công) ──────────────────────
    # Dùng khi xe đã gọi thang / đang thử mà xe mất mạng hoặc chưa có xe thật: thang đi tới tầng, mở cửa và giữ MỞ tới khi
    # hết giờ hoặc người vận hành thả. Giữ bằng cách gửi lại "open <tầng>" định kỳ (lệnh idempotent: thang đã mở ở tầng đó
    # chỉ publish lại state) — phòng thiết bị có timer tự đóng. Chạy bằng LUỒNG RIÊNG vì check_retries() chỉ được tick khi có
    # tin state của một AGV nào đó (không xe nào online thì không chạy). Tự thả khi xe bắt đầu chuyến (đóng cửa/chạy) hoặc
    # thiết bị báo lỗi — không tranh lệnh với chuỗi đi thang của xe.
    def hold_door(self, eid: str, level: int, duration_sec: float, close_on_end: bool = True) -> dict:
        duration_sec = max(5.0, min(float(duration_sec), HOLD_MAX_SEC))
        with self._lock:
            e = self._get(eid)
            if e.owner and e.phase in ("close", "move", "exit"):
                return {"ok": False, "error": f"Thang {eid} đang chạy chuyến của xe {e.owner} — không giữ cửa lúc này"}
            self._holds[eid] = {"level": int(level), "until": time.monotonic() + duration_sec,
                                "close_on_end": bool(close_on_end), "last_sent": time.monotonic()}
            self._ensure_hold_thread()
        print(f"[ELEVATOR] {eid}: GIỮ CỬA MỞ ở tầng {level} trong {duration_sec:.0f}s"
              f"{' (đóng cửa khi hết giờ)' if close_on_end else ''}")
        self._send_hold_open(eid, int(level), quiet=False)
        return {"ok": True, "level": int(level), "duration_sec": duration_sec}

    def release_hold(self, eid: str, close: bool | None = None, why: str = "") -> bool:
        """Thả giữ cửa. close=None → theo cờ close_on_end lúc bắt đầu giữ. False nếu không đang giữ."""
        with self._lock:
            h = self._holds.pop(eid, None)
            if not h:
                return False
            e = self._get(eid)
            do_close = h["close_on_end"] if close is None else close
            if e.owner:
                do_close = False        # xe đang dùng thang: để chuỗi đi thang của xe tự đóng
        print(f"[ELEVATOR] {eid}: thả giữ cửa{' — ' + why if why else ''}{' → đóng cửa' if do_close else ''}")
        if do_close:
            self._send(eid, "close")
        return True

    def _send_hold_open(self, eid: str, level: int, quiet: bool) -> None:
        try:
            from mqtt_client import send_elevator_command
            send_elevator_command(eid, "open", level, quiet=quiet)
        except Exception as ex:
            print(f"[ELEVATOR] {eid}: gửi lệnh giữ cửa lỗi: {ex}")

    def _ensure_hold_thread(self) -> None:
        if self._hold_thread is None or not self._hold_thread.is_alive():
            self._hold_thread = threading.Thread(target=self._hold_loop, name="elevator-hold", daemon=True)
            self._hold_thread.start()

    def _hold_loop(self) -> None:
        while True:
            time.sleep(1.0)
            now = time.monotonic()
            todo = []                      # (hành động, eid, level/lý do)
            with self._lock:
                if not self._holds:
                    self._hold_thread = None
                    return
                for eid, h in list(self._holds.items()):
                    e = self._get(eid)
                    if e.state == "error":
                        todo.append(("release", eid, "thiết bị thang báo lỗi"))
                    elif e.owner and e.phase in ("close", "move", "exit"):
                        todo.append(("release", eid, f"xe {e.owner} bắt đầu chuyến đi thang"))
                    elif now >= h["until"]:
                        todo.append(("release", eid, "hết giờ giữ cửa"))
                    elif now - h["last_sent"] >= HOLD_RESEND_SEC:
                        h["last_sent"] = now
                        todo.append(("resend", eid, h["level"]))
            for act, eid, arg in todo:
                if act == "release":
                    self.release_hold(eid, why=arg)
                else:
                    self._send_hold_open(eid, arg, quiet=True)

    # ── elev_book: đặt trước thang (đầu chuỗi, xe chưa đi đâu) ───────────────
    def book(self, eid: str, floor_id: str, agv_id: str) -> bool:
        with self._lock:
            e = self._get(eid)
            if e.owner in (None, agv_id):
                self._take(eid, agv_id, floor_id)
                print(f"[ELEVATOR] {eid}: {agv_id} đặt thang (tầng {floor_id}) — được cấp ngay")
                self._complete(agv_id, "elevator_booked")
            else:
                if all(a != agv_id for a, _f, _k in e.queue):
                    e.queue.append((agv_id, floor_id, "book"))
                print(f"[ELEVATOR] {eid}: đang phục vụ {e.owner} — {agv_id} xếp hàng chờ (đứng yên tại chỗ; "
                      f"hàng đợi: {[a for a, _f, _k in e.queue]})")
        return True

    def release_claims(self, agv_id: str) -> None:
        """Nhả mọi claim điểm xếp hàng của xe (xe đã được cấp thang / chuỗi bị huỷ)."""
        with self._lock:
            for k in [k for k, v in self._qclaims.items() if v[0] == agv_id]:
                self._qclaims.pop(k, None)

    def on_agv_state(self, agv_id: str, tag, driving: bool = False) -> None:
        """Hook mỗi state của xe — backend legacy không cần (backend uelev_v2 dùng để phát hiện vào/ra cabin)."""

    def plan_tail(self, agv_id: str, order: dict):
        """Hook sửa plan trước khi gửi — backend legacy không đổi gì."""
        return order

    def _take(self, eid: str, agv_id: str, floor_id: str) -> None:
        self.release_claims(agv_id)
        e = self._get(eid)
        e.owner, e.phase, e.call_floor, e.retries, e.ride, e.stale_since = agv_id, "booked", floor_id, 0, {}, 0.0
        e.sent_at = 0.0

    # ── elev_call: xe đã tới node chờ — gọi thang tới tầng, mở cửa ───────────
    def request_open(self, eid: str, floor_id: str, agv_id: str) -> bool:
        import floor_nav
        level = floor_nav.floor_level(floor_id)
        if level is None:
            print(f"[ELEVATOR] {eid}: tầng '{floor_id}' không có số tầng — không gọi được")
            return False
        with self._lock:
            e = self._get(eid)
            if e.owner is None:
                self._take(eid, agv_id, floor_id)       # chưa đặt trước (vd server vừa khởi động lại) → lấy luôn
            elif e.owner != agv_id:
                # Không đặt trước mà tới được đây (hiếm): xếp hàng ở chỗ đang đứng, được cấp thì gọi luôn
                if all(a != agv_id for a, _f, _k in e.queue):
                    e.queue.append((agv_id, floor_id, "call"))
                print(f"[ELEVATOR] {eid}: đang phục vụ {e.owner} — {agv_id} xếp hàng chờ gọi "
                      f"(hàng đợi: {[a for a, _f, _k in e.queue]})")
                return True
            e.call_floor = floor_id
            self._call(eid)
        return True

    def _call(self, eid: str) -> None:
        import floor_nav
        e = self._get(eid)
        agv_id, floor_id = e.owner, e.call_floor
        level = floor_nav.floor_level(floor_id)
        e.phase, e.retries, e.ride = "call", 0, {}
        if e.state == "open" and e.level == level:
            print(f"[ELEVATOR] {eid}: đã mở sẵn ở tầng {level} — {agv_id} vào ngay")
            self._opened_for_call(eid)
            return
        print(f"[ELEVATOR] {eid}: {agv_id} gọi thang tới tầng {level} ({floor_id}) → gửi lệnh MỞ")
        e.state = "calling"
        self._send(eid, "open", level)

    def _opened_for_call(self, eid: str) -> None:
        e = self._get(eid)
        e.phase = "board"
        e.sent_at = 0.0
        try:   # cabin dùng chung: thang mở cửa đón xe ở tầng gọi → xe vào cabin thì đang ở tầng đó (màn theo dõi)
            import floor_nav
            floor_nav.set_cabin_floor(floor_nav.cabin_node(eid, e.call_floor), e.call_floor)
        except Exception:
            pass
        self._complete(e.owner, "elevator_open")

    # ── elev_ride: xe đã trong cabin → đi tới tầng đích ──────────────────────
    def start_ride(self, eid: str, from_floor: str, to_floor: str, w_b: str, agv_id: str) -> bool:
        import floor_nav
        to_level = floor_nav.floor_level(to_floor)
        with self._lock:
            e = self._get(eid)
            if e.owner != agv_id or e.phase != "board":
                print(f"[ELEVATOR] {eid}: {agv_id} xin đi thang nhưng không giữ thang "
                      f"(chủ={e.owner}, pha={e.phase!r}) — bỏ")
                return False
            if to_level is None:
                print(f"[ELEVATOR] {eid}: tầng đích '{to_floor}' không có số tầng")
                return False
            if self._holds.pop(eid, None):    # xe bắt đầu chuyến (sắp đóng cửa) → không để lệnh giữ cửa gửi lặp tranh lệnh
                print(f"[ELEVATOR] {eid}: {agv_id} bắt đầu chuyến đi thang — thả giữ cửa")
            e.ride = {"from": from_floor, "to": to_floor, "w_b": w_b, "to_level": to_level,
                      "cab_a": floor_nav.cabin_node(eid, from_floor), "cab_b": floor_nav.cabin_node(eid, to_floor)}
            e.phase, e.retries = "close", 0
            print(f"[ELEVATOR] {eid}: {agv_id} đã vào cabin ({from_floor}→{to_floor}) → ĐÓNG cửa")
            if e.state == "closed":
                self._start_move(eid)
            else:
                self._send(eid, "close")
        return True

    def _start_move(self, eid: str) -> None:
        e = self._get(eid)
        e.phase, e.retries = "move", 0
        print(f"[ELEVATOR] {eid}: cửa đã đóng → chạy tới tầng {e.ride['to_level']} và mở cửa")
        e.state = "calling"
        self._send(eid, "open", e.ride["to_level"])

    # ── elev_release: xe đã ra khỏi cabin ────────────────────────────────────
    def release(self, eid: str, agv_id: str) -> bool:
        with self._lock:
            e = self._get(eid)
            if e.owner != agv_id:
                print(f"[ELEVATOR] {eid}: {agv_id} nhả thang nhưng không giữ — bỏ qua")
                return True
            e.owner, e.phase, e.ride = None, "", {}
            if e.queue:
                nxt, nfloor, kind = e.queue.popleft()
                print(f"[ELEVATOR] {eid}: {agv_id} đã ra — cấp thang cho {nxt} (tầng {nfloor}, {kind})")
                self._take(eid, nxt, nfloor)
                if kind == "book":
                    self._complete(nxt, "elevator_booked")     # xe đó sẽ đi tới node chờ rồi mới gọi
                else:
                    self._call(eid)
            else:
                print(f"[ELEVATOR] {eid}: {agv_id} đã ra, không còn xe chờ — gửi lệnh ĐÓNG")
                e.state = "closing"
                self._send(eid, "close")
        return True

    # ── Trạng thái từ thiết bị ───────────────────────────────────────────────
    def on_state(self, eid: str, state: str, level) -> None:
        with self._lock:
            e = self._get(eid)
            e.state = state
            try:
                if level is not None:
                    e.level = int(level)
            except (TypeError, ValueError):
                pass
            if state == "error":
                print(f"[ELEVATOR] {eid}: thiết bị báo LỖI — dừng tự động, cần kiểm tra thủ công")
                if e.owner:
                    self._fail(eid, "thiết bị thang báo lỗi")
                return
            if e.owner is None:
                return
            if e.phase == "call" and state == "open":
                import floor_nav
                want = floor_nav.floor_level(e.call_floor)
                if e.level == want:
                    print(f"[ELEVATOR] {eid}: xác nhận MỞ ở tầng {want} — {e.owner} vào cabin")
                    self._opened_for_call(eid)
            elif e.phase == "close" and state == "closed":
                self._start_move(eid)
            elif e.phase == "move" and state == "open" and e.level == e.ride.get("to_level"):
                self._arrived(eid)

    def _arrived(self, eid: str) -> None:
        e = self._get(eid)
        agv_id, r = e.owner, e.ride
        print(f"[ELEVATOR] {eid}: tới tầng {r['to_level']} và đã mở cửa — {agv_id} ra khỏi cabin")
        try:
            import floor_nav
            floor_nav.set_cabin_floor(r.get("cab_b"), r.get("to"))   # cabin dùng chung: tầng của thẻ = tầng thang đứng
        except Exception:
            pass
        self._relocate(agv_id, r.get("cab_b"), r.get("w_b"))
        e.phase, e.sent_at = "exit", 0.0
        self._complete(agv_id, "elevator_arrived")

    def _relocate(self, agv_id: str, cab_node, prev_node) -> None:
        """Xe vừa được thang chở sang tầng khác (xe không di chuyển → firmware không đọc thẻ mới) → đặt lại
        vị trí phía server + gửi 'locate' cho xe. prev_tag = node chờ ngoài cabin → xe vào TIẾN thì ra LÙI,
        vào LÙI thì ra TIẾN (nhánh "node cụt" của _dispatch_go_to dùng last_transit_direction đã giữ nguyên)."""
        if cab_node is None:
            return
        try:
            from line_agv_handler import line_agv_handler
            st = line_agv_handler.state_store.get_or_create(agv_id)
            st.current_tag = _tagval(cab_node)
            if prev_node:
                st.prev_tag = _tagval(prev_node)
            st.driving = False
            from mqtt_client import send_line_command
            kw = {"tag": _tagval(cab_node)}
            if prev_node:
                kw["prev"] = _tagval(prev_node)
            send_line_command(agv_id, "locate", **kw)
            print(f"[ELEVATOR] {agv_id}: đặt lại vị trí → tag {cab_node} (prev {prev_node})")
        except Exception as ex:
            print(f"[ELEVATOR] đặt lại vị trí {agv_id} lỗi: {ex}")

    # ── Timeout / thử lại (gọi định kỳ — mỗi state message của bất kỳ AGV nào) ─
    def _owner_has_elevator_cmd(self, agv_id: str) -> bool:
        try:
            from task_queue import agv_task_queue
            from floor_nav import ELEVATOR_COMMANDS
            run = agv_task_queue.get_running(agv_id)
            cmds = ([run["command"]] if run else []) + [c["command"] for c in agv_task_queue.get_queue(agv_id)]
            return any(c in ELEVATOR_COMMANDS for c in cmds)
        except Exception:
            return True      # không kiểm tra được → coi như còn sống (không nhả nhầm)

    def check_retries(self) -> None:
        now = time.monotonic()
        with self._lock:
            # Booking mồ côi: chủ thang không còn lệnh thang nào trong hàng đợi (bị huỷ giữa chừng, lỗi...) →
            # nhả sau 8s để không giữ thang vĩnh viễn.
            for eid, e in list(self._el.items()):
                if not e.owner:
                    continue
                if self._owner_has_elevator_cmd(e.owner):
                    e.stale_since = 0.0
                elif e.stale_since <= 0:
                    e.stale_since = now
                elif now - e.stale_since > 8.0:
                    print(f"[ELEVATOR] {eid}: {e.owner} không còn lệnh thang nào (bị huỷ?) — tự nhả thang")
                    self.release(eid, e.owner)
            for eid, e in list(self._el.items()):
                if not e.owner or e.sent_at <= 0 or e.phase not in ("call", "close", "move"):
                    continue
                limit = ELEV_CLOSE_TIMEOUT if e.phase == "close" else ELEV_OPEN_TIMEOUT
                if now - e.sent_at < limit:
                    continue
                if e.retries < ELEV_OPEN_MAX_RETRIES and e.last_cmd:
                    e.retries += 1
                    print(f"[ELEVATOR] {eid}: không thấy xác nhận sau {now - e.sent_at:.0f}s (pha {e.phase}) "
                          f"→ GỬI LẠI {e.last_cmd} lần {e.retries}/{ELEV_OPEN_MAX_RETRIES}")
                    self._send(eid, e.last_cmd[0], e.last_cmd[1])
                else:
                    self._fail(eid, f"thang không phản hồi (pha {e.phase})")

    def _fail(self, eid: str, why: str) -> None:
        """Lỗi thang: dừng chuỗi lệnh đi thang của xe (xe đứng yên tại chỗ — không vào cabin khi cửa chưa mở),
        nhả thang, báo cảnh báo cho người vận hành."""
        e = self._get(eid)
        agv_id = e.owner
        print(f"[ELEVATOR] {eid}: LỖI — {why}; huỷ lệnh của {agv_id}, cần kiểm tra thủ công")
        e.owner, e.phase, e.ride, e.sent_at = None, "", {}, 0.0
        if not agv_id:
            return
        try:
            from line_agv_handler import line_agv_handler
            st = line_agv_handler.state_store.get(agv_id)
            if st is not None:
                line_agv_handler._set_alert(agv_id, st, "ELEVATOR_ERROR", f"Thang {eid}: {why}")
        except Exception as ex:
            print(f"[ELEVATOR] đặt cảnh báo lỗi: {ex}")
        try:
            from task_queue import agv_task_queue
            agv_task_queue.cancel_all(agv_id)
        except Exception as ex:
            print(f"[ELEVATOR] huỷ hàng đợi {agv_id} lỗi: {ex}")

    # ── Cho UI ───────────────────────────────────────────────────────────────
    def status(self) -> list[dict]:
        import floor_nav
        out = []
        try:
            from mqtt_client import map_manager
            metas = {str(m.get("id")): m for m in (getattr(map_manager, "elevators", None) or [])}
        except Exception:
            metas = {}
        with self._lock:
            ids = list(metas.keys()) + [k for k in self._el if k not in metas]
            for eid in ids:
                e = self._el.get(eid) or _Elev()
                floors = []
                try:
                    for fid in floor_nav.elevator_floors(eid):
                        lv = floor_nav.floor_level(fid)
                        if lv is not None:
                            floors.append({"id": fid, "name": floor_nav.floor_name(fid), "level": lv})
                    floors.sort(key=lambda f: f["level"])
                except Exception:
                    floors = []
                h = self._holds.get(eid)
                out.append({
                    "id": eid, "name": (metas.get(eid) or {}).get("name") or eid,
                    "state": e.state, "level": e.level,
                    "floor": floor_nav.floor_id_of_level(e.level) if e.level is not None else None,
                    "owner": e.owner, "phase": e.phase, "queue": [a for a, _f, _k in e.queue],
                    "floors": floors,
                    "hold": ({"level": h["level"], "remaining_sec": max(0, int(h["until"] - time.monotonic())),
                              "close_on_end": h["close_on_end"]} if h else None),
                })
        return out


def _make_coordinator():
    """Backend thang: 'uelev_v2' (thư viện elevator_coord, giao thức uelev/v2 của phần cứng — xem elevator_bridge.py)
    hoặc 'legacy' (elevator/v1 open/close — emulator mô phỏng cũ). Mặc định: uelev_v2 cho server thật (thang thật nói
    uelev/v2; legacy publish elevator/v1 nên master không bao giờ nhận được lệnh); server mô phỏng (MQTT_MODE_OVERRIDE)
    giữ legacy trừ khi ELEVATOR_BACKEND đặt rõ. Đặt ELEVATOR_BACKEND=legacy để ép dùng bản cũ."""
    import os
    _default = "legacy" if os.getenv("MQTT_MODE_OVERRIDE", "").strip() else "uelev_v2"
    if os.getenv("ELEVATOR_BACKEND", _default).strip().lower() in ("uelev_v2", "uelev", "v2"):
        try:
            from elevator_bridge import ElevatorBridge
            print("[ELEVATOR] backend = uelev_v2 (elevator_coord)")
            return ElevatorBridge()
        except Exception as ex:
            print(f"[ELEVATOR] KHÔNG nạp được backend uelev_v2 ({type(ex).__name__}: {ex}) — dùng legacy")
    return ElevatorCoordinator()


elevator_coordinator = _make_coordinator()
