"""
elevator_bridge.py — Backend thang máy `uelev_v2`: nối chuỗi lệnh đi thang của server (floor_nav /
task_queue) với thư viện điều phối `elevator_coord` của đội phần cứng (giao thức uelev/v2, VDA5050-aligned,
xem 04-giao-thuc-mqtt.md / 07-tich-hop-fms.md).

Bật bằng biến môi trường  ELEVATOR_BACKEND=uelev_v2  (mặc định `legacy` = elevator_coordinator.py cũ).
Cùng giao diện với ElevatorCoordinator cũ (book / request_open / start_ride / release / status /
claim_queue_point / check_retries) nên main.py, task_queue, floor_nav, UI KHÔNG phải đổi.

Ánh xạ chuỗi lệnh hàng đợi ⇄ vòng đời ride của thư viện:

  elev_book  E@A       request_ride(xe, tầng A→B)        hoàn tất khi STARTED (tới lượt dùng thang)
  go_to W_A            (bình thường)                     xe tới node chờ
  elev_call  E@A       —                                 hoàn tất khi BOARD_ALLOWED (cabin mở + giữ cửa ở A)
  go_to cabin_A        (bình thường + ĐUÔI plan)         plan gửi lúc xe còn online được NỐI THÊM đoạn
                                                         "chờ EXIT_ALLOWED → lùi ra → thẻ thoát W_B" (xe mất
                                                         mạng trong cabin, không nhận thêm plan — 07 §3.1)
  elev_ride  E@A>B#W   agv_boarded() → (đợi) EXIT_ALLOWED → `run` → xe báo thẻ W_B → agv_exited()
                                                         hoàn tất khi xe đã ra tới W_B
  go_to W_B            (xe đã ở W_B → tự hoàn tất)
  elev_release E       dọn ctx; hoàn tất ngay (thư viện tự nhả thiết bị)

Toàn bộ tương tác ngoài (hàng đợi, lệnh xe, cảnh báo) đi qua `AgvIO` để test thay thế được.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from persistent_flags import flag_store
from typing import Callable, Dict, List, Optional

from elevator_coordinator import ElevatorCoordinator as _LegacyCoordinator

# ── Nạp thư viện elevator_coord (nằm cạnh thư mục mqtt_Server) ────────────────
try:
    import elevator_coord as _ec_lib
except ImportError:
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _root not in sys.path:
        sys.path.insert(0, _root)
    import elevator_coord as _ec_lib

from elevator_coord import (CoordinatorConfig, ElevatorCoordinator as LibCoordinator, EventType, RideRejected)

# Mã action plan (khớp line_agv_plan_builder.py)
ACT_WAIT_SYS, ACT_RUN, ACT_DIR_FWD, ACT_DIR_BWD, ACT_LIDAR_ON = 1, 3, 7, 8, 21
ACT_TURN_R, ACT_TURN_L, ACT_LIDAR_OFF = 5, 6, 20

# Bước "LIDAR_GATE" (07 §3.1: kiểm lidar dài SAU cabin trống rồi mới lùi ra) — mã 36 trong 07 nhưng server đang dùng 36 là
# REVERSE_BLIND: để TRỐNG tới khi đội firmware xác nhận. Đặt ELEVATOR_LIDAR_GATE_ACTION=<mã> để chèn.
LIDAR_GATE_ACTION = int(os.getenv("ELEVATOR_LIDAR_GATE_ACTION", "0") or 0)

RUN_RESEND_S = 3.0          # 07 §3: gửi lặp `run` mỗi 3 s tới khi thẻ RFID của xe đổi

# Khóa VÙNG thang: từ lúc xe được cấp lượt tới khi xe đi QUA mốc thoát (ra khỏi hành lang cabin → ngã ba) không xe nào khác
# được gọi thang; xe sau xếp hàng FIFO (thứ tự đặt thang). Tắt bằng ELEVATOR_AREA_GATING=0.
DEFER_CALL = os.getenv("ELEVATOR_DEFER_CALL", "1").strip().lower() not in ("0", "false", "no", "off")   # chỉ gọi Bộ gọi tầng khi xe tới node chờ
AREA_GATING = os.getenv("ELEVATOR_AREA_GATING", "1").strip().lower() not in ("0", "false", "no", "off")
AREA_CLEAR_TIMEOUT_S = float(os.getenv("ELEVATOR_AREA_CLEAR_TIMEOUT_S", "90") or 90)   # xe đứng yên ở hành lang quá lâu → nhả + cảnh báo
AREA_ORPHAN_S = 30.0        # khóa còn mà không có chuyến nào chạy / không ai nhận → nhả (dự phòng)
REVOKED_WARN_S = 30.0       # bị thu hồi quyền vào cabin quá lâu mà xe chưa vào → cảnh báo (không tự huỷ ride)
ORPHAN_S = 8.0              # chủ ride không còn lệnh thang nào trong hàng đợi quá lâu → huỷ ride
RIDE_RETRY_S = 10.0         # ride lỗi khi xe CHƯA vào cabin: chờ chừng này rồi đặt lại thang (KHÔNG xoá hàng đợi của xe)


# ══════════════════════════════════════════════════════════════════════════════
# Cầu nối tới phần còn lại của server (thay được khi test)
# ══════════════════════════════════════════════════════════════════════════════
class AgvIO:
    """Mọi tác động lên xe / hàng đợi / cảnh báo. Mặc định dùng module thật của server."""

    def complete(self, agv_id: str, notes: str) -> None:
        from task_queue import agv_task_queue
        agv_task_queue.on_agv_completed(agv_id, notes=notes)

    def running(self, agv_id: str) -> Optional[dict]:
        from task_queue import agv_task_queue
        return agv_task_queue.get_running(agv_id)

    def queued(self, agv_id: str) -> List[dict]:
        from task_queue import agv_task_queue
        return agv_task_queue.get_queue(agv_id)

    def cancel_queue(self, agv_id: str) -> None:
        from task_queue import agv_task_queue
        agv_task_queue.cancel_all(agv_id)

    def insert_next(self, agv_id: str, command: str, dest_node) -> None:
        from task_queue import agv_task_queue
        agv_task_queue.insert_next(agv_id, command, dest_node=dest_node)

    def send_run(self, agv_id: str) -> None:
        from mqtt_client import send_line_command
        send_line_command(agv_id, "run")

    def send_stop(self, agv_id: str) -> None:
        from mqtt_client import send_line_command
        send_line_command(agv_id, "stop")

    def send_plan(self, agv_id: str, steps: list) -> None:
        """Gửi plan mới (id mới) — dùng khi `run` không nhả được xe khỏi WAIT_SYS ở thẻ cabin."""
        import uuid
        from mqtt_client import send_order
        send_order(agv_id, {"c": "plan", "id": uuid.uuid4().hex[:8], "d": list(steps)})

    def agv_tag(self, agv_id: str):
        from line_agv_handler import line_agv_handler
        st = line_agv_handler.state_store.get(agv_id)
        return None if st is None else st.current_tag

    def route_direction(self, agv_id: str) -> str:
        from line_agv_handler import line_agv_handler
        r = line_agv_handler._routes.get(agv_id)
        return str(getattr(r, "direction", "") or "")

    def finish_cabin_leg(self, agv_id: str, cab_node: str) -> bool:
        """Xe tới thẻ cabin (plan có ĐUÔI nên firmware KHÔNG dừng báo 'tới đích' như bình thường, và xe sắp mất mạng):
        hoàn tất lệnh `go_to cabin` TỪ PHÍA SERVER — bỏ route/đăng ký giao thông của chặng này để watchdog 'kẹt node biên',
        'wait_sys tại node trung gian' không tự sinh event/gửi lại plan cũ khi xe đã lùi ra tầng khác."""
        run = self.running(agv_id)
        if not run or run.get("command") != "go_to" or str(run.get("dest_node")) != str(cab_node):
            return False
        try:
            from line_agv_handler import line_agv_handler, traffic_coordinator
            line_agv_handler._routes.pop(agv_id, None)
            traffic_coordinator.deregister(agv_id)
            st = line_agv_handler.state_store.get(agv_id)
            if st is not None:
                st.task_lifecycle = None
        except Exception as ex:
            print(f"[ELEVATOR] dọn route {agv_id} lỗi: {ex}")
        self.complete(agv_id, "elev_cabin_reached")
        return True

    def sync_exit_state(self, agv_id: str, prev_node, direction: str) -> None:
        """Xe vừa ra khỏi cabin tới thẻ thoát: đặt prev_tag = cabin ở tầng đích (kề node thoát trong đồ thị) và hướng
        di chuyển vừa rồi → lệnh đi tiếp tính DIR/rẽ đúng như khi xe rời cabin theo chuỗi cũ."""
        from line_agv_handler import line_agv_handler
        st = line_agv_handler.state_store.get(agv_id)
        if st is None:
            return
        try:
            st.prev_tag = int(prev_node)
        except (TypeError, ValueError):
            st.prev_tag = prev_node
        if direction:
            st.last_transit_direction = direction

    def alert(self, agv_id: str, code: str, msg: str) -> None:
        from line_agv_handler import line_agv_handler
        st = line_agv_handler.state_store.get(agv_id)
        if st is not None:
            line_agv_handler._set_alert(agv_id, st, code, msg)

    def agv_available(self, agv_id: str) -> bool:
        from mqtt_client import _line_agv_available
        return _line_agv_available(agv_id)

    def clear_alert(self, agv_id: str, code: str) -> None:
        from line_agv_handler import line_agv_handler
        st = line_agv_handler.state_store.get(agv_id)
        if st is not None:
            line_agv_handler._clear_alert(st, code)

    def pending_cmd(self, agv_id: str) -> Optional[str]:
        from agv_cmd_channel import agv_cmd_channel
        return agv_cmd_channel.pending(agv_id)


class ServerTransport:
    """Transport (elevator_coord) dùng CHÍNH client MQTT của server (mqtt_client.client). Tra `client` mỗi lần gọi vì
    server có thể thay client khi đổi chế độ MQTT. Tin `uelev/...` được mqtt_client.on_message chuyển vào `handle()`."""

    def __init__(self) -> None:
        self._handler: Optional[Callable[[str, bytes], None]] = None
        self._link: Optional[Callable[[bool], None]] = None
        self._filters: List[tuple] = []

    @staticmethod
    def _client():
        import mqtt_client
        return mqtt_client.client

    def publish(self, topic: str, payload: str, qos: int = 1, retain: bool = False) -> None:
        self._client().publish(topic, payload, qos=qos, retain=retain)

    def subscribe(self, topic_filter: str, qos: int = 1) -> None:
        self._filters.append((topic_filter, qos))
        try:
            self._client().subscribe(topic_filter, qos=qos)
        except Exception as ex:
            print(f"[ELEVATOR] subscribe {topic_filter} lỗi (sẽ đăng ký lại khi kết nối): {ex}")

    def set_message_handler(self, handler) -> None:
        self._handler = handler

    def set_link_handler(self, handler) -> None:
        self._link = handler

    def resubscribe(self) -> None:
        for flt, qos in self._filters:
            try:
                self._client().subscribe(flt, qos=qos)
            except Exception:
                pass

    def notify_link(self, up: bool) -> None:
        if self._link is not None:
            self._link(up)

    def handle(self, topic: str, payload: bytes) -> None:
        if self._handler is not None:
            self._handler(topic, payload)


# ══════════════════════════════════════════════════════════════════════════════
@dataclass
class _Ctx:
    agv: str
    eid: str
    fa: str                       # id tầng nguồn / đích (floor id của map)
    fb: str
    ride_id: str
    created: float
    started: bool = False
    board_allowed: bool = False
    revoked: bool = False
    exit_allowed: bool = False
    boarded: bool = False
    exited: bool = False
    finished: bool = False        # thư viện báo COMPLETED
    waiting_call: bool = False    # lệnh elev_call đang chờ BOARD_ALLOWED
    waiting_ride: bool = False    # lệnh elev_ride đang chờ xe ra
    w_b: str = ""
    cab_a: str = ""
    cab_b: str = ""
    tail: bool = False            # đã đăng ký NỐI ĐUÔI plan cho xe này
    entry_dir: str = ""
    exit_dir: str = ""            # chiều xe ra khỏi cabin ('fwd'|'bwd') — theo cạnh cửa vào/ra (plan_tail)
    last_run_at: float = 0.0
    exit_steps: list = field(default_factory=list)   # plan ĐỘC LẬP cabin → thẻ thoát (dự phòng khi `run` không nhả được xe)
    exit_plan_at: float = 0.0
    stale_since: float = 0.0
    revoked_at: float = 0.0       # lúc BOARD_REVOKED (0 = không bị thu hồi)
    revoked_warned: bool = False  # đã cảnh báo "bị thu hồi quá lâu mà xe chưa vào cabin" (log 1 lần)
    warned: bool = False          # đã log việc agv_boarded/agv_exited chưa được nhận (chỉ log 1 lần)


class ElevatorBridge(_LegacyCoordinator):
    def __init__(self, transport=None, clock=None, io: Optional[AgvIO] = None,
                 config: Optional[CoordinatorConfig] = None, autostart_thread: bool = True) -> None:
        super().__init__()
        self._transport = transport or ServerTransport()
        self._clock = clock
        self._io = io or AgvIO()
        self._cfg = config
        self._coord: Optional[LibCoordinator] = None
        self._ctx: Dict[str, _Ctx] = {}
        self._by_ride: Dict[str, _Ctx] = {}
        # eid -> {agv, nodes(set thẻ hành lang), since, timeout|None, why}: xe đã ra/đang kẹt trong vùng thang, chờ đi qua mốc
        self._areas: Dict[str, dict] = {}
        self._retry: Dict[str, dict] = {}        # agv_id -> lần thử lại sau lỗi thang (không xoá hàng đợi)
        self._retry_n: Dict[str, int] = {}
        self._persisted: Dict[str, dict] = {}   # agv_id -> ngữ cảnh chuyến thang đã lưu DB (chiều vào/ra, plan thoát...) để NHẬN LẠI sau khi khởi động lại
        self._thread: Optional[threading.Thread] = None
        self._autostart = autostart_thread
        self._sig = ""

    # ── Khởi tạo lười: cần map đã nạp (danh sách thang + tầng) ────────────────
    def _build_config(self) -> Optional[CoordinatorConfig]:
        import floor_nav
        mm = floor_nav._mm()
        elevs = getattr(mm, "elevators", None) or []
        if not elevs:
            return None
        factory = ""
        try:
            from agv_registry import agv_registry
            factory = agv_registry.get_default_factory(default="")
        except Exception:
            pass
        if not factory:
            from unified_mqtt import LINE_AGV_FACTORY
            factory = LINE_AGV_FACTORY or "VietDuc"
        over = {}
        path = os.getenv("ELEVATOR_UELEV_CONFIG", os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                               "elevator_uelev.json"))
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    over = json.load(fh) or {}
            except Exception as ex:
                print(f"[ELEVATOR] đọc {path} lỗi: {ex}")
        factory = str(over.get("factory") or factory)
        out = []
        for e in elevs:
            eid = str(e["id"])
            levels = sorted(int(floor_nav.floor_level(f, mm)) for f in floor_nav.elevator_floors(eid, mm))
            if len(levels) < 2:
                continue
            callers = {}
            for lv in levels:
                dirs = []
                if lv < levels[-1]:
                    dirs.append("UP")
                if lv > levels[0]:
                    dirs.append("DN")
                callers[str(lv)] = {"device": f"call{lv}", "directions": dirs}
            ent = {"id": eid, "floors": levels, "master": "master", "callers": callers,
                   "allowed_routes": "all", "zones": [], "timing": {}}
            ent.update((over.get("elevators") or {}).get(eid, {}))
            out.append(ent)
        if not out:
            return None
        return CoordinatorConfig.from_dict({"factory": factory, "elevators": out})

    def _ensure(self) -> bool:
        with self._lock:
            if self._coord is not None:
                return True
            cfg = self._cfg or self._build_config()
            if cfg is None:
                return False
            kw = {"clock": self._clock} if self._clock is not None else {}
            self._coord = LibCoordinator(cfg, self._transport, on_event=None, **kw)
            self._coord.set_area_gating(AREA_GATING)
            self._coord.set_defer_until_ready(DEFER_CALL)
            self._coord.start()
            print(f"[ELEVATOR] uelev_v2 khởi động: factory={cfg.factory} "
                  f"thang={[(e.elevator_id, e.floors) for e in cfg.elevators]}")
            self._start_loop_thread()
            return True

    def _start_loop_thread(self) -> None:
        """Vòng nền (tick thư viện + thử lại sau lỗi). Chạy độc lập với việc thang đã khởi tạo xong hay chưa — nếu map chưa
        nạp (vd server vừa khởi động lại) thì lệnh thang lỗi vẫn phải được thử lại sau RIDE_RETRY_S."""
        if not self._autostart:
            return
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, name="elevator-bridge", daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        last_orphan = 0.0
        while True:
            time.sleep(0.2)
            try:
                self.tick()
                now = time.monotonic()
                if now - last_orphan > 1.0:
                    last_orphan = now
                    self.check_retries()
            except Exception as ex:
                import traceback
                print(f"[ELEVATOR] vòng nền lỗi: {type(ex).__name__}: {ex}")
                traceback.print_exc()

    def tick(self) -> None:
        """Tick thư viện rồi xử lý sự kiện (NGOÀI khoá thư viện — handler gọi vào hàng đợi, tránh khoá chéo)."""
        if self._coord is None:
            return
        self._coord.tick()
        for ev in self._coord.poll_events():
            try:
                self._on_event(ev)
            except Exception as ex:
                import traceback
                print(f"[ELEVATOR] xử lý sự kiện {ev.type.value} lỗi: {type(ex).__name__}: {ex}")
                traceback.print_exc()

    # ── Liên kết broker của CHÍNH server ──────────────────────────────────────
    def on_broker_link(self, up: bool) -> None:
        if isinstance(self._transport, ServerTransport):
            if up:
                self._transport.resubscribe()
            self._transport.notify_link(up)

    def on_uelev_message(self, topic: str, payload: bytes) -> None:
        if isinstance(self._transport, ServerTransport):
            self._ensure()
            self._transport.handle(topic, payload)

    # ── Khóa vùng thang ───────────────────────────────────────────────────────
    def _mono(self) -> float:
        return self._clock.monotonic() if self._clock is not None else time.monotonic()

    def _release_area(self, eid: str, why: str, agv: Optional[str] = None) -> bool:
        a = self._areas.pop(eid, None)
        ok = bool(self._coord and self._coord.release_area(eid, agv or (a or {}).get("agv")))
        if ok or a:
            print(f"[ELEVATOR] {eid}: NHẢ khóa vùng thang ({why}) — xe kế tiếp trong hàng đợi được gọi")
        return ok

    def release_area_manual(self, eid: str) -> bool:
        """Người vận hành nhả khóa vùng thang (xe hỏng/kẹt trong khu vực)."""
        a = self._areas.get(eid)
        return self._release_area(eid, "thủ công", agv=(a or {}).get("agv") or self._area_owner(eid))

    def _area_owner(self, eid: str) -> Optional[str]:
        try:
            for e in self._coord.snapshot().get("elevators", []):
                if e["elevator_id"] == eid and e.get("area_hold"):
                    return e["area_hold"]["agv_id"]
        except Exception:
            pass
        return None

    def _area_check(self, agv_id: str, tag) -> None:
        """Xe vừa ra khỏi cabin / kẹt trong vùng thang: tới node NGOÀI hành lang → đã qua mốc thoát → nhả khóa."""
        if tag is None:
            return
        for eid, a in list(self._areas.items()):
            if a["agv"] == agv_id and str(tag) not in a["nodes"]:
                self._release_area(eid, f"{agv_id} đã đi qua mốc thoát (tới thẻ {tag})")

    def _area_watchdog(self, now: float) -> None:
        for eid, a in list(self._areas.items()):
            if a["timeout"] is not None and now - a["since"] > a["timeout"]:
                msg = (f"Thang {eid}: {a['agv']} đứng ở hành lang thang quá {a['timeout']:.0f}s chưa đi qua mốc thoát — "
                       f"tự nhả khóa để xe khác được gọi")
                print(f"[ELEVATOR] CẢNH BÁO {msg}")
                self._io.alert(a["agv"], "ELEVATOR_AREA_TIMEOUT", msg)
                self._release_area(eid, "quá thời gian chờ xe thoát")
        # dự phòng: có khóa mà không có chuyến đang chạy và không có bản ghi xe thoát (mất đồng bộ) → nhả sau AREA_ORPHAN_S
        try:
            snap = self._coord.snapshot().get("elevators", []) if self._coord else []
        except Exception:
            snap = []
        for e in snap:
            eid, h = e["elevator_id"], e.get("area_hold")
            if h and e.get("active") is None and eid not in self._areas and h["since_s"] > AREA_ORPHAN_S:
                print(f"[ELEVATOR] CẢNH BÁO {eid}: khóa vùng thang của {h['agv_id']} không còn chuyến/bản ghi — nhả")
                self._coord.release_area(eid, h["agv_id"])

    # ── Tiện ích ──────────────────────────────────────────────────────────────
    @staticmethod
    def _set_cabin_floor(cab: str, fid: str) -> None:
        """Cabin dùng chung chỉ có 1 thẻ → tầng của xe đang ở thẻ đó = tầng thang đang đứng."""
        if not cab:
            return
        import floor_nav
        floor_nav.set_cabin_floor(cab, fid)

    def _lvl(self, fid: str) -> Optional[int]:
        import floor_nav
        return floor_nav.floor_level(fid)

    def _peek_ride_cmd(self, agv_id: str) -> Optional[tuple]:
        """(eid, fa, fb, w_b) từ lệnh elev_ride gần nhất trong hàng đợi của xe (hoặc đang chạy)."""
        import floor_nav
        run = self._io.running(agv_id)
        for c in ([run] if run else []) + list(self._io.queued(agv_id)):
            if c and c.get("command") == floor_nav.CMD_ELEV_RIDE:
                return floor_nav.parse_ride(c.get("dest_node"))
        return None

    def _complete(self, agv_id: str, notes: str, expect: tuple = ()) -> None:
        """Hoàn tất lệnh thang đang chạy của xe. `expect`: chỉ hoàn tất nếu lệnh đang chạy thuộc nhóm này (không phá lệnh
        khác khi sự kiện đến muộn)."""
        if expect:
            run = self._io.running(agv_id)
            if not run or run.get("command") not in expect:
                print(f"[ELEVATOR] {agv_id}: bỏ qua hoàn tất '{notes}' — lệnh đang chạy là "
                      f"{(run or {}).get('command')!r}, không phải {expect}")
                return
        self._io.complete(agv_id, notes)

    # ══════════════════════════════════════════════════════════════════════════
    # Giao diện chuỗi lệnh (giống ElevatorCoordinator cũ)
    # ══════════════════════════════════════════════════════════════════════════
    def book(self, eid: str, floor_id: str, agv_id: str) -> bool:
        if not self._ensure():
            print(f"[ELEVATOR] {eid}: uelev_v2 chưa có cấu hình thang (map chưa nạp?) — không đặt được")
            return False
        import floor_nav
        fa = floor_id.partition(">")[0]
        with self._lock:
            ctx = self._ctx.get(agv_id)
            peek = self._peek_ride_cmd(agv_id)
            fb = floor_id.partition(">")[2] or (peek[2] if peek else "")
            if ctx and not ctx.finished and ctx.eid == eid and ctx.fa == fa:
                # Chỉ là "đặt lại cùng yêu cầu" khi chuyến CHƯA lên cabin và cùng tầng đích. Ngược lại là chuyến CŨ còn sót
                # (vd người vận hành huỷ hàng đợi lúc xe đang đi thang rồi xe được đưa ra tay): dùng lại nó thì không có
                # ride mới, không có sự kiện STARTED → lệnh elev_book treo mãi (đúng lỗi AGV01 17:02 ngày 23/11).
                if not ctx.boarded and not ctx.exited and (not fb or ctx.fb == fb):
                    return True                  # đặt lại cùng yêu cầu (idempotent)
                print(f"[ELEVATOR] {eid}: {agv_id} có chuyến cũ {ctx.ride_id} ({ctx.fa}→{ctx.fb}, "
                      f"{'đã lên cabin' if ctx.boarded else 'chưa lên'}) còn sót — huỷ để đặt chuyến mới {fa}→{fb}")
                self._supersede_ctx(ctx, "superseded")
            la, lb = self._lvl(fa), self._lvl(fb)
            if la is None or lb is None:
                print(f"[ELEVATOR] {eid}: {agv_id} đặt thang {fa}→{fb!r} nhưng tầng không có số tầng")
                return False
            try:
                rid = self._coord.request_ride(agv_id, la, lb, elevator_id=eid)
            except RideRejected as ex:
                print(f"[ELEVATOR] {eid}: từ chối ride {agv_id} {la}→{lb}: {ex}")
                self._io.alert(agv_id, "ELEVATOR_ERROR", f"Thang {eid}: yêu cầu bị từ chối ({ex.reason})")
                return False
            c = _Ctx(agv=agv_id, eid=eid, fa=fa, fb=fb, ride_id=rid, created=time.monotonic())
            c.cab_a, c.cab_b = floor_nav.cabin_node(eid, fa) or "", floor_nav.cabin_node(eid, fb) or ""
            if peek:
                c.w_b = str(peek[3] or "")
            self._ctx[agv_id] = c
            self._by_ride[rid] = c
            print(f"[ELEVATOR] {eid}: {agv_id} đặt thang {fa}→{fb} (ride {rid}) — chờ tới lượt")
        return True

    def _supersede_ctx(self, ctx: "_Ctx", why: str) -> None:
        """Huỷ HẲN chuyến cũ còn sót của xe (kể cả xe từng vào cabin) và nhả khóa vùng thang nếu đang giữ cho xe đó. Gọi trong self._lock."""
        try:
            if self._coord is not None and not ctx.finished:
                self._coord.cancel_ride(ctx.ride_id, why, force=True)
        except Exception as ex:
            print(f"[ELEVATOR] huỷ chuyến cũ {ctx.ride_id} lỗi: {ex}")
        self._release_area(ctx.eid, f"chuyến cũ {ctx.ride_id} bị huỷ ({why})", agv=ctx.agv)
        self._drop(ctx)

    def request_open(self, eid: str, floor_id: str, agv_id: str) -> bool:
        if not self._ensure():
            return False
        fa = floor_id.partition(">")[0]
        with self._lock:
            ctx = self._ctx.get(agv_id)
        if ctx is None:                         # chưa đặt (server khởi động lại giữa chuỗi) → đặt luôn rồi chờ
            if not self.book(eid, fa, agv_id):
                return False
            with self._lock:
                ctx = self._ctx.get(agv_id)
        with self._lock:
            peek = self._peek_ride_cmd(agv_id)
            if peek and not ctx.w_b:
                ctx.w_b = str(peek[3] or "")
            if self._coord is not None:
                self._coord.agv_ready(ctx.ride_id)           # xe tới node chờ → được gọi Bộ gọi tầng
            if ctx.board_allowed and not ctx.revoked:
                done_now = True
            else:
                ctx.waiting_call = True
                done_now = False
        if done_now:
            self._register_tail(ctx)
            self._complete(agv_id, "elevator_open")
        else:
            print(f"[ELEVATOR] {eid}: {agv_id} tới node chờ — đợi cabin mở cửa (BOARD_ALLOWED)")
        return True

    def start_ride(self, eid: str, from_floor: str, to_floor: str, w_b: str, agv_id: str) -> bool:
        if not self._ensure():
            return False
        with self._lock:
            ctx = self._ctx.get(agv_id)
            if ctx is None:
                print(f"[ELEVATOR] {eid}: {agv_id} xin đi thang nhưng không có ride — bỏ")
                return False
            if w_b:
                ctx.w_b = str(w_b)
            ctx.waiting_ride = True
            exited = ctx.exited
        if exited:
            self._finish_ride_cmd(ctx)
            return True
        if not ctx.boarded:
            self._mark_boarded(ctx, "lệnh vào cabin hoàn tất")
        return True

    # ── Nhận lại chuyến của xe đang TRONG CABIN ───────────────────────────────────

    def has_ctx(self, agv_id: str) -> bool:
        with self._lock:
            c = self._ctx.get(agv_id)
            return c is not None and not (c.finished and not c.exited and not c.boarded)

    @staticmethod
    def _ctx_info(ctx: "_Ctx") -> dict:
        return {"eid": ctx.eid, "fa": ctx.fa, "fb": ctx.fb, "w_b": ctx.w_b, "entry_dir": ctx.entry_dir,
                "exit_dir": ctx.exit_dir, "exit_steps": [dict(x) for x in (ctx.exit_steps or [])]}

    def _persist_ctx(self, ctx: "_Ctx") -> None:
        """Lưu DB ngữ cảnh chuyến (chiều vào/ra cabin, plan thoát độc lập) — mất khi server khởi động lại thì xe đang trong
        cabin không biết thoát hướng nào."""
        import json
        info = self._ctx_info(ctx)
        self._persisted[ctx.agv] = info
        flag_store.replace("ride_ctx", ctx.agv, json.dumps(info, ensure_ascii=False))

    def load_persisted_ctx(self, rows) -> None:
        """Nạp lại từ DB lúc khởi động: rows = [(agv_id, json)]."""
        import json
        for agv, raw in rows:
            try:
                self._persisted[str(agv)] = json.loads(raw)
            except Exception:
                pass

    def adopt_inside(self, agv_id: str, eid: str, fa: str, fb: str, w_b: str = "", info: Optional[dict] = None) -> bool:
        """Xe ĐANG TRONG CABIN mà chuyến thang cũ không còn (server khởi động lại / ride lỗi): tạo chuyến mới ở pha TRANSIT
        (xem ElevatorUnit.adopt_inside) và ctx đã-lên-cabin để cầu nối tiếp tục như bình thường: tới đích → EXIT_ALLOWED → `run`."""
        if not self._ensure():
            return False
        import floor_nav
        info = info or self._persisted.get(agv_id) or {}
        if info and (info.get("eid"), info.get("fa"), info.get("fb")) != (eid, fa, fb):
            info = {}                                    # ngữ cảnh đã lưu thuộc chuyến khác
        with self._lock:
            old = self._ctx.get(agv_id)
            if old is not None and not old.finished and old.eid == eid and old.fa == fa:
                return True                              # đã có chuyến sống
            la, lb = self._lvl(fa), self._lvl(fb)
            if la is None or lb is None:
                print(f"[ELEVATOR] {eid}: {agv_id} nhận lại chuyến {fa}→{fb} nhưng tầng không có số tầng")
                return False
            try:
                rid = self._coord.adopt_inside(agv_id, la, lb, elevator_id=eid)
            except RideRejected as ex:
                print(f"[ELEVATOR] {eid}: chưa nhận lại được chuyến của {agv_id} ({ex.reason}) — thử lại sau")
                return False
            c = _Ctx(agv=agv_id, eid=eid, fa=fa, fb=fb, ride_id=rid, created=time.monotonic(),
                     started=True, board_allowed=True, boarded=True)
            c.cab_a = floor_nav.cabin_node(eid, fa) or ""
            c.cab_b = floor_nav.cabin_node(eid, fb) or ""
            c.w_b = str(w_b or info.get("w_b") or "")
            c.entry_dir = str(info.get("entry_dir") or "")
            c.exit_dir = str(info.get("exit_dir") or "")
            c.exit_steps = [dict(x) for x in (info.get("exit_steps") or [])]
            c.tail = bool(c.w_b and c.cab_a)
            run = self._io.running(agv_id)
            c.waiting_ride = bool(run and run.get("command") == floor_nav.CMD_ELEV_RIDE)
            self._ctx[agv_id] = c
            self._by_ride[rid] = c
        self._persist_ctx(c)
        print(f"[ELEVATOR] {eid}: NHẬN LẠI chuyến của {agv_id} đang ở trong cabin ({fa}→{fb}, ride {rid}) — thang đưa xe tới tầng {fb} rồi cho ra")
        clear = getattr(self._io, "clear_alert", None)
        if clear is not None:
            try:
                clear(agv_id, "ELEVATOR_ERROR")
            except Exception:
                pass
        return True

    def release(self, eid: str, agv_id: str) -> bool:
        with self._lock:
            ctx = self._ctx.get(agv_id)
            if ctx is None:
                return True
            if not ctx.finished and not ctx.exited and self._coord is not None:
                self._coord.cancel_ride(ctx.ride_id, "release", force=False)
            self._drop(ctx)
        return True

    # ── Thử lại sau lỗi (KHÔNG xoá hàng đợi) ─────────────────────────────────────

    def _entering_cabin(self, ctx: "_Ctx") -> bool:
        """Xe đang chạy lệnh đi VÀO cabin (go_to node cabin / elev_ride)?"""
        import floor_nav
        run = self._io.running(ctx.agv)
        if not run:
            return False
        if run.get("command") == floor_nav.CMD_ELEV_RIDE:
            return True
        cabs = {str(ctx.cab_a), str(ctx.cab_b)} - {""}
        return run.get("command") == "go_to" and str(run.get("dest_node")) in cabs

    def _schedule_retry(self, agv_id: str, kind: str, command: str = "", dest=None, info: Optional[dict] = None) -> None:
        n = self._retry_n.get(agv_id, 0) + 1
        self._retry_n[agv_id] = n
        self._retry[agv_id] = {"kind": kind, "command": command, "dest": dest, "info": info,
                               "due": self._mono() + RIDE_RETRY_S}
        self._start_loop_thread()

    def retry_failed_command(self, agv_id: str, command: str, dest_node) -> None:
        """Lệnh thang (đặt/gọi/đi thang) vừa dispatch LỖI: giữ nguyên hàng đợi, chèn lại đúng lệnh đó sau RIDE_RETRY_S."""
        first = agv_id not in self._retry
        self._schedule_retry(agv_id, "cmd", command, dest_node)
        if first:
            print(f"[ELEVATOR] {agv_id}: lệnh {command} {dest_node or ''} lỗi — GIỮ hàng đợi, thử lại sau {RIDE_RETRY_S:.0f}s")

    def _process_retries(self) -> None:
        if not self._retry:
            return
        now = self._mono()
        for agv_id, info in list(self._retry.items()):
            if now < info["due"]:
                continue
            try:
                if info["kind"] == "adopt":
                    # Ride lỗi khi xe còn TRONG CABIN: nhận lại chuyến (xe đã ở trong — không cần xe online)
                    d = info.get("info") or {}
                    if self.adopt_inside(agv_id, d.get("eid", ""), d.get("fa", ""), d.get("fb", ""), d.get("w_b", ""), d):
                        self._retry.pop(agv_id, None)
                    else:
                        info["due"] = now + RIDE_RETRY_S
                    continue
                if info["kind"] == "cmd":
                    if self._io.running(agv_id):          # xe đang có lệnh khác → chờ tới khi rảnh
                        info["due"] = now + 2.0
                        continue
                    self._retry.pop(agv_id, None)
                    self._io.insert_next(agv_id, info["command"], info["dest"])
                    self._io.complete(agv_id, "elevator_cmd_retry")       # rảnh → lấy lệnh vừa chèn ra chạy lại
                else:
                    if not self._io.agv_available(agv_id):  # xe còn offline → chờ online lại rồi mới đặt lại thang
                        info["due"] = now + 2.0
                        continue
                    self._retry.pop(agv_id, None)
                    self._retry_ride_now(agv_id)
            except Exception as ex:
                print(f"[ELEVATOR] {agv_id}: thử lại sau lỗi thang bị lỗi: {type(ex).__name__}: {ex}")
                info["due"] = now + RIDE_RETRY_S

    def _retry_ride_now(self, agv_id: str) -> None:
        """Đặt lại chuyến thang cho xe: chèn [elev_call → (lệnh vào cabin / elev_ride)] lên đầu hàng đợi rồi hoàn tất lệnh
        đang treo — elev_call sẽ đặt chuyến MỚI (request_open tự đặt khi chưa có ride) rồi chờ cabin mở cửa."""
        import floor_nav
        run = self._io.running(agv_id)
        peek = self._peek_ride_cmd(agv_id)
        if not run or not peek:
            return                      # không có lệnh thang nào để làm lại (elev_call kế tiếp, nếu có, sẽ tự đặt thang)
        eid, fa, _fb, _wb = peek
        cmd, dest = run.get("command"), run.get("dest_node")
        redo = None
        if cmd == floor_nav.CMD_ELEV_CALL:
            redo = None                 # chính elev_call đang treo → chèn lại một bản
        elif cmd == floor_nav.CMD_ELEV_RIDE or (cmd == "go_to" and str(dest) == str(floor_nav.cabin_node(eid, fa) or "")):
            redo = (cmd, dest)          # xe đã/đang vào cabin rồi dừng: gọi lại thang, sau đó làm lại bước vào cabin/đi thang
        else:
            return                      # xe đang đi tới node chờ / chuỗi chưa tới bước gọi thang → elev_call sau đó tự đặt lại
        if redo is not None:
            self._io.insert_next(agv_id, redo[0], redo[1])
        self._io.insert_next(agv_id, floor_nav.CMD_ELEV_CALL, f"{eid}@{fa}")
        print(f"[ELEVATOR] {eid}: {agv_id} — đặt lại chuyến thang {fa} (lần thử {self._retry_n.get(agv_id, 1)})")
        self._io.complete(agv_id, "elevator_ride_retry")

    def check_retries(self) -> None:
        """Dọn ride mồ côi: chủ không còn lệnh thang nào trong hàng đợi (bị huỷ/lỗi) quá ORPHAN_S → huỷ ride."""
        self._process_retries()
        if self._coord is None:
            return
        self._area_watchdog(self._mono())
        now = time.monotonic()
        with self._lock:
            ctxs = list(self._ctx.values())
        for ctx in ctxs:
            if ctx.exited or ctx.finished:
                continue
            # Quyền vào cabin bị thu hồi mà xe vẫn chưa vào quá REVOKED_WARN_S: ride (và khóa vùng thang) vẫn đang giữ chỗ.
            # KHÔNG tự huỷ ride (lệnh elev_* của xe còn trong hàng đợi — huỷ sẽ đứt chuỗi, xe kẹt giữa chừng) — chỉ cảnh báo 1 lần.
            if (ctx.revoked and not ctx.boarded and ctx.revoked_at > 0 and not ctx.revoked_warned
                    and now - ctx.revoked_at > REVOKED_WARN_S):
                ctx.revoked_warned = True
                print(f"[ELEVATOR] {ctx.eid}: ⚠️ {ctx.agv} bị thu hồi quyền vào cabin {now - ctx.revoked_at:.0f}s mà vẫn chưa vào — "
                      f"ride {ctx.ride_id} đang giữ thang/khóa vùng; kiểm tra xe (hoặc nhả khóa tay)")
            if self._has_elevator_cmd(ctx.agv):
                ctx.stale_since = 0.0
            elif ctx.stale_since <= 0:
                ctx.stale_since = now
            elif now - ctx.stale_since > ORPHAN_S and not ctx.boarded:
                print(f"[ELEVATOR] {ctx.eid}: {ctx.agv} không còn lệnh thang nào (bị huỷ?) — huỷ ride {ctx.ride_id}")
                self._coord.cancel_ride(ctx.ride_id, "orphan", force=False)
                with self._lock:
                    self._drop(ctx)
            elif now - ctx.stale_since > ORPHAN_S and ctx.boarded and not ctx.exited and self._left_cabin(ctx):
                # Chuyến đã "lên cabin" nhưng hàng đợi thang bị huỷ và xe đã được đưa RA NGOÀI cabin (tay/deba): chuyến không bao giờ
                # nhận được agv_exited → thang bị giữ ở pha EXITING + khóa vùng mãi, chặn mọi chuyến sau.
                print(f"[ELEVATOR] {ctx.eid}: {ctx.agv} đã ra khỏi cabin và không còn lệnh thang — huỷ chuyến mồ côi {ctx.ride_id}, nhả thang")
                with self._lock:
                    self._supersede_ctx(ctx, "orphan_left_cabin")

    def _left_cabin(self, ctx: "_Ctx") -> bool:
        """Thẻ hiện tại của xe nằm NGOÀI các node cabin của chuyến (xe biết vị trí)."""
        try:
            tag = self._io.agv_tag(ctx.agv)
        except Exception:
            return False
        if tag in (None, 0, "0", ""):
            return False
        return str(tag) not in ({str(ctx.cab_a), str(ctx.cab_b)} - {""})

    def _has_elevator_cmd(self, agv_id: str) -> bool:
        try:
            import floor_nav
            run = self._io.running(agv_id)
            cmds = ([run["command"]] if run else []) + [c["command"] for c in self._io.queued(agv_id)]
            return any(c in floor_nav.ELEVATOR_COMMANDS for c in cmds)
        except Exception:
            return True

    def _drop(self, ctx: _Ctx, keep_persist: bool = False) -> None:
        if not keep_persist:
            self._persisted.pop(ctx.agv, None)
            flag_store.remove_group("ride_ctx", ctx.agv)
        if not ctx.exited and not ctx.boarded:
            # chuyến bị bỏ khi xe CHƯA vào cabin (huỷ/mồ côi/lỗi): nhả khóa vùng ngay — sự kiện CANCELLED có thể tới sau khi
            # ctx đã bị xoá (khi đó _on_event bỏ qua) nên không thể chờ nó. Chỉ nhả nếu đúng xe chủ khóa.
            self._release_area(ctx.eid, f"ride của {ctx.agv} bị bỏ trước khi vào cabin", agv=ctx.agv)
        self._ctx.pop(ctx.agv, None) if self._ctx.get(ctx.agv) is ctx else None
        self._by_ride.pop(ctx.ride_id, None)
        self.release_claims(ctx.agv)

    # ══════════════════════════════════════════════════════════════════════════
    # Nối đuôi plan: sau WAIT_SYS ở cabin → đổi chiều → chạy → thẻ thoát W_B (xe mất mạng khi cabin đóng cửa)
    # ══════════════════════════════════════════════════════════════════════════
    def _register_tail(self, ctx: _Ctx) -> None:
        if ctx.w_b and ctx.cab_a:
            ctx.tail = True
            ctx.entry_dir = ""
        else:
            print(f"[ELEVATOR] {ctx.eid}: {ctx.agv} thiếu node thoát/cabin — KHÔNG nối đuôi plan được")

    def _turn_tail(self, agv_id: str, ctx: _Ctx, steps: list, cab: int, wb: int, d_in: str, turn: str):
        """Các bước plan để xe ĐANG ĐỨNG ở thẻ cabin quay 90° (turn='L'|'R') rồi chạy tới thẻ thoát `wb`, dựng bằng
        line_agv_plan_builder (cùng mẫu bước với mọi cú rẽ khác). None nếu thiếu node chờ vào (không dựng được)."""
        import floor_nav
        from line_agv_plan_builder import build_plan_window, build_edge_speeds, build_edge_lidar
        mm = floor_nav._mm()
        wa = floor_nav.wait_node(ctx.eid, ctx.fa, mm) or (str(steps[-2]["t"]) if len(steps) >= 2 else "")
        if not wa:
            print(f"[ELEVATOR] {ctx.eid}: {agv_id} không biết node chờ vào cabin — KHÔNG dựng được bước quay")
            return None
        na = dict(getattr(mm, "node_actions", None) or {})
        cfg = dict(na.get(str(cab)) or {})
        cfg["turn_allowed"] = "yes"
        cfg["turn_map"] = {f"{wa}_{wb}": "left" if turn == "L" else "right"}
        na[str(cab)] = cfg
        roads = getattr(mm, "roads", None) or []
        plan = build_plan_window(
            [str(cab), str(wb)], 0, 1, getattr(mm, "points", None) or {}, True, "transit",
            node_actions=na, direction=d_in,
            edge_speeds=build_edge_speeds(roads), edge_lidar=build_edge_lidar(roads),
            agv_id=agv_id, initial_prev_tag=str(wa))
        return plan["d"]

    def plan_tail(self, agv_id: str, order: dict):
        ctx = self._ctx.get(agv_id)
        if ctx is None or not ctx.tail or ctx.exited or not isinstance(order, dict) or order.get("c") != "plan":
            return order
        steps = order.get("d") or []
        try:
            cab, wb = int(ctx.cab_a), int(ctx.w_b)
        except (TypeError, ValueError):
            return order
        if not steps or steps[-1].get("t") != cab or steps[-1].get("a") != ACT_WAIT_SYS:
            return order                            # chưa phải cửa sổ cuối tới cabin
        if any(s.get("t") == wb for s in steps):
            return order                            # đã nối rồi (gửi lại cùng plan)
        d_in = self._io.route_direction(agv_id)
        if d_in not in ("fwd", "bwd"):
            d_in = next((("bwd" if s["a"] == ACT_DIR_BWD else "fwd") for s in reversed(steps)
                         if s.get("a") in (ACT_DIR_FWD, ACT_DIR_BWD)), "fwd")
        ctx.entry_dir = d_in
        # Cách ra theo cạnh cửa vào/ra của cabin (floor_nav.plan_cabin_exit); chưa khai báo cạnh cửa → cùng cạnh = lùi ra
        import floor_nav
        xp = floor_nav.cabin_exit_for(ctx.eid, ctx.fa, ctx.fb, d_in, agv_id)
        if xp is None:                              # decompose đã chặn; phòng hờ → hành vi cũ (đổi chiều rồi ra)
            xp = {"exit_dir": "bwd" if d_in == "fwd" else "fwd", "turns": [], "kind": "reverse"}
        ctx.exit_dir = xp["exit_dir"]
        if xp["turns"]:
            # Quay tại chỗ: dựng bằng CHÍNH plan builder như mọi cú rẽ khác (DIR hiện tại → LIDAR_OFF → TURN →
            # LIDAR_ON → SPEED → RUN → WAIT_SYS ở thẻ thoát). Hướng rẽ khai báo tường minh qua turn_map của node cabin
            # (cặp node chờ vào → node thoát) thay vì suy từ toạ độ; giữ nguyên chiều tiến/lùi lúc vào.
            tail = self._turn_tail(agv_id, ctx, steps, cab, wb, d_in, xp["turns"][0])
            if tail is None:
                return order
        else:
            d_out = ACT_DIR_FWD if xp["exit_dir"] == "fwd" else ACT_DIR_BWD
            tail = [{"t": cab, "a": ACT_LIDAR_ON, "v": 0}, {"t": cab, "a": d_out, "v": 0}]
            if LIDAR_GATE_ACTION:
                tail.append({"t": cab, "a": LIDAR_GATE_ACTION, "v": 0})
            tail += [{"t": cab, "a": ACT_RUN, "v": 0}, {"t": wb, "a": ACT_WAIT_SYS, "v": 0}]
        # Bản ĐỘC LẬP của đoạn đuôi (bắt đầu bằng DIR) — gửi như plan mới nếu `run` không thoát được WAIT_SYS ở cabin
        ctx.exit_steps = ([dict(s) for s in tail] if xp["turns"] else [tail[1], tail[0]] + tail[2:])
        out = dict(order)
        out["d"] = list(steps) + tail
        how = {"reverse": "đổi chiều", "straight": "đi thẳng xuyên cabin", "turn": f"quay {''.join(xp['turns'])}"}[xp["kind"]]
        print(f"[ELEVATOR] {agv_id}: nối đuôi plan — cabin {cab} chờ EXIT_ALLOWED → {how}, "
              f"{'tiến' if xp['exit_dir'] == 'fwd' else 'lùi'} ra thẻ {wb} (+{len(tail)} bước)")
        self._persist_ctx(ctx)
        return out

    # ══════════════════════════════════════════════════════════════════════════
    # Vào/ra cabin — phát hiện từ thẻ RFID của xe
    # ══════════════════════════════════════════════════════════════════════════
    def on_agv_state(self, agv_id: str, tag, driving: bool = False) -> None:
        self._area_check(agv_id, tag)
        ctx = self._ctx.get(agv_id)
        if ctx is None or self._coord is None or tag is None:
            return
        t = str(tag)
        if not ctx.boarded and ctx.cab_a and t == str(ctx.cab_a):
            self._mark_boarded(ctx, f"xe tới thẻ cabin {t}")
        elif ctx.boarded and not ctx.exited and ctx.w_b and t == str(ctx.w_b):
            self._mark_exited(ctx)
        elif ctx.exit_allowed and not ctx.exited and ctx.cab_a and t == str(ctx.cab_a):
            now = time.monotonic()
            if ctx.exit_steps and now - ctx.last_run_at >= RUN_RESEND_S and now - ctx.exit_plan_at >= 2 * RUN_RESEND_S \
                    and self._io.agv_available(agv_id):
                # `run` đã gửi mà xe vẫn đứng ở cabin (firmware không thoát WAIT_SYS bằng run, cũng không báo cmd_ack):
                # gửi PLAN MỚI cabin → thẻ thoát, như mọi cửa sổ plan tiếp theo sau 1 lần dừng
                ctx.exit_plan_at = now
                print(f"[ELEVATOR] {agv_id}: `run` không nhả được xe khỏi cabin {t} sau {RUN_RESEND_S:.0f}s — gửi PLAN ra thẻ {ctx.w_b}")
                self._io.send_plan(agv_id, ctx.exit_steps)
            elif not ctx.exit_steps and now - ctx.last_run_at >= RUN_RESEND_S and self._io.pending_cmd(agv_id) is None \
                    and self._io.agv_available(agv_id):
                ctx.last_run_at = now
                print(f"[ELEVATOR] {agv_id}: thẻ vẫn là cabin {t} sau {RUN_RESEND_S:.0f}s — gửi lại run")
                self._io.send_run(agv_id)

    def _mark_boarded(self, ctx: _Ctx, why: str) -> None:
        with self._lock:
            if ctx.boarded:
                return
            ok = bool(self._coord and self._coord.agv_boarded(ctx.ride_id))
            if ok:
                ctx.boarded = True
        if ok:
            self._set_cabin_floor(ctx.cab_a, ctx.fa)
            print(f"[ELEVATOR] {ctx.eid}: {ctx.agv} đã VÀO cabin ({why}) → báo thư viện")
            self._io.finish_cabin_leg(ctx.agv, ctx.cab_a)
        elif not ctx.warned:
            ctx.warned = True
            print(f"[ELEVATOR] {ctx.eid}: agv_boarded({ctx.ride_id}) chưa được nhận ({why}) — thử lại ở state sau")

    def _mark_exited(self, ctx: _Ctx) -> None:
        with self._lock:
            if ctx.exited:
                return
            ok = bool(self._coord and self._coord.agv_exited(ctx.ride_id))
            if not ok:
                return                               # ride chưa ở EXITING (xe ra sớm?) — thử lại ở state sau
            ctx.exited = True
        try:
            import floor_nav
            corridor = floor_nav.exit_corridor(ctx.cab_b, ctx.w_b, eid=ctx.eid, fid=ctx.fb)
        except Exception:
            corridor = [str(ctx.cab_b), str(ctx.w_b)]
        self._areas[ctx.eid] = {"agv": ctx.agv, "nodes": set(corridor), "since": self._mono(),
                                "timeout": AREA_CLEAR_TIMEOUT_S, "why": "xe đang thoát hành lang thang"}
        print(f"[ELEVATOR] {ctx.eid}: khóa vùng thang giữ tới khi {ctx.agv} đi qua mốc thoát (ra khỏi hành lang {corridor})")
        d_out = ctx.exit_dir or ("bwd" if ctx.entry_dir == "fwd" else "fwd")
        self._set_cabin_floor(ctx.cab_b, ctx.fb)
        self._io.sync_exit_state(ctx.agv, ctx.cab_b, d_out)
        print(f"[ELEVATOR] {ctx.eid}: {ctx.agv} đã RA tới thẻ {ctx.w_b} → báo thư viện")
        # Phòng khi lệnh `go_to cabin` chưa kịp hoàn tất (xe mất mạng, event tới cabin rơi mất)
        import floor_nav
        run = self._io.running(ctx.agv)
        if run and run.get("command") == "go_to" and str(run.get("dest_node")) == str(ctx.cab_a):
            self._io.complete(ctx.agv, "elev_boarded_missed")
        elif ctx.waiting_ride:
            self._finish_ride_cmd(ctx)

    def _finish_ride_cmd(self, ctx: _Ctx) -> None:
        import floor_nav
        with self._lock:
            ctx.waiting_ride = False
        self._complete(ctx.agv, "elevator_arrived", expect=(floor_nav.CMD_ELEV_RIDE,))

    # ══════════════════════════════════════════════════════════════════════════
    # Sự kiện thư viện
    # ══════════════════════════════════════════════════════════════════════════
    def _on_event(self, ev) -> None:
        import floor_nav
        T = EventType
        ctx = self._by_ride.get(ev.ride_id) if ev.ride_id else None
        if ev.type == T.WARNING:
            reason = ev.data.get("reason")
            if reason not in ("cabin_offline",):          # cabin_offline: bình thường (cửa đóng) — không log
                print(f"[ELEVATOR] {ev.elevator_id}: CẢNH BÁO {reason} {ev.data} ({ev.agv_id})")
            return
        if ev.type == T.ZONE_RELEASED:
            print(f"[ELEVATOR] {ev.elevator_id}: nhả khoá tầng {ev.data}")
            return
        if ctx is None:
            return
        if ev.type == T.STARTED:
            ctx.started = True
            self.release_claims(ctx.agv)
            print(f"[ELEVATOR] {ctx.eid}: tới lượt {ctx.agv} — gọi thang tới tầng {ctx.fa}")
            # Bước đầu của chuỗi chạy NGAY trong lệnh đang chạy (thường là go_to gốc) — xem main._start_ride_chain
            self._complete(ctx.agv, "elevator_booked", expect=(floor_nav.CMD_ELEV_BOOK, "go_to", "go_charge", "go_wait"))   # go_charge/go_wait: chuỗi thang khởi động từ lệnh về trạm/chờ
        elif ev.type == T.BOARD_ALLOWED:
            was_revoked = ctx.revoked
            ctx.board_allowed, ctx.revoked = True, False
            ctx.revoked_at = 0.0
            self._set_cabin_floor(ctx.cab_a, ctx.fa)        # cabin ở tầng đón: hướng rẽ tới/ra node chờ tính theo mặt cabin này
            print(f"[ELEVATOR] {ctx.eid}: cabin mở cửa tầng {ctx.fa} — {ctx.agv} được VÀO")
            if ctx.waiting_call:
                ctx.waiting_call = False
                self._register_tail(ctx)
                self._complete(ctx.agv, "elevator_open", expect=(floor_nav.CMD_ELEV_CALL,))
            elif was_revoked and ctx.tail and not ctx.boarded:
                self._io.send_run(ctx.agv)                  # đã bị dừng lúc BOARD_REVOKED → nhả lại (07 §3 mục 7)
        elif ev.type == T.BOARD_REVOKED:
            ctx.board_allowed, ctx.revoked = False, True
            ctx.revoked_at, ctx.revoked_warned = time.monotonic(), False
            print(f"[ELEVATOR] {ctx.eid}: THU HỒI quyền vào cabin của {ctx.agv}")
            if ctx.tail and not ctx.boarded:
                self._io.send_stop(ctx.agv)
        elif ev.type == T.EXIT_ALLOWED:
            ctx.exit_allowed = True
            ctx.last_run_at = time.monotonic()
            self._set_cabin_floor(ctx.cab_b, ctx.fb)
            print(f"[ELEVATOR] {ctx.eid}: tới tầng {ctx.fb} và mở cửa — {ctx.agv} được RA (gửi run)")
            self._io.send_run(ctx.agv)
        elif ev.type == T.COMPLETED:
            if ctx.eid not in self._areas:                        # không có bản ghi thoát → đừng giữ khóa
                self._release_area(ctx.eid, "chuyến hoàn tất", agv=ctx.agv)
            ctx.finished = True
            self._retry_n.pop(ctx.agv, None)
            print(f"[ELEVATOR] {ctx.eid}: ride {ctx.ride_id} của {ctx.agv} HOÀN TẤT")
            if ctx.waiting_ride:
                self._finish_ride_cmd(ctx)
        elif ev.type in (T.FAILED, T.CANCELLED):
            reason = ev.data.get("reason", "")
            inside = bool(ev.data.get("agv_inside"))
            if inside:     # xe còn trong cabin: GIỮ khóa tới khi xe ra khỏi hành lang (hoặc người vận hành nhả) — không timeout
                self._areas[ctx.eid] = {"agv": ctx.agv, "nodes": {str(ctx.cab_a), str(ctx.cab_b)}, "since": self._mono(),
                                        "timeout": None, "why": "xe còn trong cabin"}
                print(f"[ELEVATOR] {ctx.eid}: ride lỗi khi {ctx.agv} còn TRONG CABIN — giữ khóa vùng thang tới khi xe ra/nhả tay")
            else:
                self._release_area(ctx.eid, f"ride {ev.type.value}", agv=ctx.agv)
            ctx.finished = True
            if ev.type == T.CANCELLED and not ctx.waiting_call and not ctx.waiting_ride:
                self._drop(ctx)
                return
            print(f"[ELEVATOR] {ctx.eid}: ride {ctx.ride_id} {ev.type.value} ({reason}) xe trong cabin={inside}")
            self._io.alert(ctx.agv, "ELEVATOR_ERROR",
                           f"Thang {ctx.eid}: {reason or ev.type.value}" + (" — XE ĐANG TRONG CABIN" if inside else ""))
            # TUYỆT ĐỐI không xoá hàng đợi lệnh của xe khi ride lỗi (lệnh dang dở phải còn nguyên để xe làm nốt):
            #  • xe TRONG CABIN (hoặc đã vào cabin): chỉ cảnh báo + giữ khóa vùng thang — người vận hành xử lý thang rồi hàng đợi chạy tiếp;
            #  • xe CHƯA vào cabin (kể cả đang offline): dừng xe nếu đang tiến vào cabin, rồi sau RIDE_RETRY_S ĐẶT LẠI thang
            #    (đặt chuyến mới + gọi lại + đi thang) — tự lặp tới khi thang phục vụ được.
            offline = not self._io.agv_available(ctx.agv)
            in_cabin = inside or (ctx.boarded and not ctx.exited)
            if ctx.exited:
                print(f"[ELEVATOR] {ctx.eid}: ride {ctx.ride_id} lỗi sau khi {ctx.agv} đã ra khỏi cabin — GIỮ hàng đợi, xe đi tiếp")
            elif in_cabin:
                self._persist_ctx(ctx)
                self._schedule_retry(ctx.agv, "adopt", info=self._ctx_info(ctx))
                print(f"[ELEVATOR] {ctx.eid}: ride {ctx.ride_id} lỗi nhưng {ctx.agv} còn trong cabin — GIỮ NGUYÊN hàng đợi lệnh, "
                      f"sau {RIDE_RETRY_S:.0f}s NHẬN LẠI chuyến (đưa xe tới tầng {ctx.fb} rồi cho ra)")
            else:
                if self._entering_cabin(ctx) and not offline:
                    self._io.send_stop(ctx.agv)        # xe đang tiến vào cabin mà ride đã hỏng (cửa có thể đóng) → dừng
                self._schedule_retry(ctx.agv, "ride")
                print(f"[ELEVATOR] {ctx.eid}: ride {ctx.ride_id} lỗi, {ctx.agv} chưa vào cabin"
                      f"{' (đang offline)' if offline else ''} — GIỮ hàng đợi, thử đặt lại thang sau {RIDE_RETRY_S:.0f}s")
            self._drop(ctx, keep_persist=bool(in_cabin and not ctx.exited))

    # ══════════════════════════════════════════════════════════════════════════
    # UI
    # ══════════════════════════════════════════════════════════════════════════
    def status(self) -> list[dict]:
        import floor_nav
        out = []

        def _metas() -> dict:
            try:
                return {str(m.get("id")): m for m in (getattr(floor_nav._mm(), "elevators", None) or [])}
            except Exception:
                return {}
        metas = _metas()
        if not metas:
            # Server vừa khởi động: bản đồ chưa nạp (nạp lười khi có lệnh đầu tiên) → trang theo dõi báo thang "chưa kết nối"
            # dù thiết bị vẫn online. Nạp bản đồ của 1 xe để biết thang, rồi dựng thư viện điều phối (nhận state thang).
            try:
                from agv_registry import agv_registry
                from mqtt_client import ensure_map_loaded_sync
                for aid in agv_registry.all_ids():
                    mid = agv_registry.get_map_id(aid)
                    if mid:
                        ensure_map_loaded_sync(str(mid))
                        break
            except Exception as ex:
                print(f"[ELEVATOR] nạp bản đồ để hiển thị thang lỗi: {type(ex).__name__}: {ex}")
            metas = _metas()
        if metas and self._coord is None:
            self._ensure()
        snap = {}
        if self._coord is not None:
            snap = {e["elevator_id"]: e for e in self._coord.snapshot().get("elevators", [])}
        for eid, m in metas.items():
            s = snap.get(eid) or {}
            act = s.get("active") or {}
            lv = s.get("floor")
            door = s.get("door_open")
            state = "unknown" if (lv is None and door is None) else (
                "moving" if lv is None else ("open" if door else "closed"))
            out.append({
                "id": eid, "name": m.get("name") or eid, "state": state, "level": lv,
                "floor": floor_nav.floor_id_of_level(lv) if lv is not None else None,
                "owner": act.get("agv_id"), "phase": (act.get("state") or "").lower(),
                "queue": [r["agv_id"] for r in (s.get("queue") or [])],
                "area_hold": s.get("area_hold"), "area_note": (self._areas.get(eid) or {}).get("why"),
                "backend": "uelev_v2", "devices": s.get("devices"),
            })
        return out

    def on_state(self, eid: str, state: str, level) -> None:
        """Tin elevator/v1 cũ — backend uelev_v2 bỏ qua."""
        return
