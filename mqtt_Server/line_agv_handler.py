"""
line_agv_handler.py — Handler cho Line AGV (RFID-based)
---------------------------------------------------------
Nhận MQTT state từ Line AGV (format v2), parse, cập nhật state store,
và thông báo cho VDA5050 traffic engine về edge đang bị chiếm.

State format Line AGV nhận được:
  {
    "lastNodeId": "101",        ← tag RFID hiện tại (string hoặc int)
    "tag": 101,                 ← backward compat
    "prev_tag": 100,            ← tag trước đó (tính hướng đi)
    "ack": "cmd_id",            ← xác nhận lệnh
    "driving": false,
    "paused": false,
    "batteryState": {"batteryCharge": 85},
    "battery": 85,              ← backward compat
    "battery_low": false,
    "battery_blocking": false,
    "event": "confirm" | "return" | "battery_need_charge",
    "operatingMode": "AUTOMATIC",
    "errors": [],
  }

Cross-type integration:
  - Khi LINE AGV chiếm edge (prev→cur), edge ID tương ứng được đưa vào
    _line_blocked_edges. VDA5050 route planner có thể query để tránh cạnh này.
  - Naming convention edge: "{from_tag}_to_{to_tag}" (khớp với VDA5050 map nếu
    cùng dùng integer node ID).
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Optional, Callable, Union

from agv_registry import agv_registry
from line_agv_plan_builder import (
    build_plan_window,
    first_window_end,
    LOOKAHEAD,
    RETRY_TIMEOUT,
)

# Ngưỡng thời gian không nhận state → coi là OFFLINE
OFFLINE_TIMEOUT_SEC = 30.0  # Line AGV chỉ pub state khi di chuyển — cần timeout dài hơn VDA5050


# ═══════════════════════════════════════════════════════════════════════════════
# LineAGVState — snapshot trạng thái 1 Line AGV
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class LineAGVState:
    agv_id:           str            = ""
    current_tag:      Optional[int]  = None  # None cho đến khi nhận RFID đầu tiên
    prev_tag:         int            = 0     # tag trước đó
    next_tag:         int            = 0     # tag tiếp theo (từ route đang chạy)
    battery:          int   = 0
    battery_low:      bool  = False
    battery_blocking: bool  = False
    driving:          bool  = False
    paused:           bool  = False
    operating_mode:   str   = "MANUAL"
    connection_state: str   = "OFFLINE"
    error_code:       int   = 0
    last_update:      float = 0.0   # 0 cho đến khi nhận state message đầu tiên
    last_ack:         str   = ""    # cmd_id vừa được AGV ACK

    # Edge đang chiếm: (from_tag, to_tag) — None nếu đứng yên tại node
    current_edge_pair: Optional[tuple[int, int]] = None


# ═══════════════════════════════════════════════════════════════════════════════
# LineAGVRoute — rolling plan state cho 1 Line AGV
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class LineAGVRoute:
    full_path:    list         # list[str] — toàn bộ đường đi
    task_type:    str  = "delivery"
    window_start: int  = 0    # index đầu cửa sổ hiện tại trong full_path
    window_end:   int  = 0    # index cuối cửa sổ hiện tại (inclusive)
    sent_cmd_id:  str  = ""   # cmd_id của plan vừa gửi
    sent_at:      float = 0.0 # thời điểm gửi plan cuối
    acked:        bool = False # đã nhận ACK cho plan này chưa
    is_complete:  bool = False # True khi cửa sổ cuối đã được gửi


# ═══════════════════════════════════════════════════════════════════════════════
# LineAGVStateStore
# ═══════════════════════════════════════════════════════════════════════════════

class LineAGVStateStore:
    def __init__(self):
        self._states: dict[str, LineAGVState] = {}

    def get(self, agv_id: str) -> Optional[LineAGVState]:
        return self._states.get(str(agv_id))

    def get_or_create(self, agv_id: str) -> LineAGVState:
        if agv_id not in self._states:
            self._states[agv_id] = LineAGVState(agv_id=agv_id)
        return self._states[agv_id]

    def all(self) -> dict[str, LineAGVState]:
        return dict(self._states)

    def snapshot(self) -> list[dict]:
        result = []
        for s in self._states.values():
            result.append({
                "agv_id":          s.agv_id,
                "current_tag":     s.current_tag,   # Optional[int]
                "prev_tag":        s.prev_tag,
                "next_tag":        s.next_tag,
                "battery":         s.battery,
                "battery_low":     s.battery_low,
                "battery_blocking": s.battery_blocking,
                "driving":         s.driving,
                "paused":          s.paused,
                "operating_mode":  s.operating_mode,
                "connection":      s.connection_state,
                "last_update":     s.last_update,
                "current_edge":    (f"{s.current_edge_pair[0]}→{s.current_edge_pair[1]}"
                                    if s.current_edge_pair else None),
            })
        return result


# ═══════════════════════════════════════════════════════════════════════════════
# Cross-type edge blocking
# ═══════════════════════════════════════════════════════════════════════════════

_line_blocked_edges: dict[str, str] = {}  # {edge_id: agv_id}


def get_line_agv_blocked_edges() -> list[str]:
    """VDA5050 route planner gọi hàm này để tránh các cạnh Line AGV đang chiếm."""
    return list(_line_blocked_edges.keys())


def _reserve_line_edge(agv_id: str, from_tag: int, to_tag: int) -> None:
    edge_id = f"{from_tag}_to_{to_tag}"
    _line_blocked_edges[edge_id] = agv_id
    print(f"[LINE_AGV] {agv_id}: reserve edge {edge_id}")


def _release_line_edge(agv_id: str, from_tag: int, to_tag: int) -> None:
    edge_id = f"{from_tag}_to_{to_tag}"
    if _line_blocked_edges.get(edge_id) == agv_id:
        del _line_blocked_edges[edge_id]
        print(f"[LINE_AGV] {agv_id}: release edge {edge_id}")


def _release_all_line_edges(agv_id: str) -> None:
    keys = [k for k, v in _line_blocked_edges.items() if v == agv_id]
    for k in keys:
        del _line_blocked_edges[k]
    if keys:
        print(f"[LINE_AGV] {agv_id}: released all edges {keys}")


# ═══════════════════════════════════════════════════════════════════════════════
# LineAGVHandler
# ═══════════════════════════════════════════════════════════════════════════════

class LineAGVHandler:
    """
    Nhận và xử lý MQTT messages từ Line AGV.
    Được gọi từ unified on_message khi topic thuộc v2.
    """

    def __init__(self):
        self.state_store = LineAGVStateStore()

        # ── Rolling plan state: {agv_id: LineAGVRoute} ────────────────────────
        self._routes: dict[str, LineAGVRoute] = {}

        # ── Callbacks (inject từ mqtt_client sau khi MQTT sẵn sàng) ──────────
        # send_window_fn(agv_id, plan_dict) — gửi plan đến AGV
        self.send_window_fn: Optional[Callable] = None
        # on_state_changed(LineAGVState) — notify GUI
        self.on_state_changed: Optional[Callable] = None
        # on_battery_event(agv_id, event_name, data) — xử lý pin yếu
        self.on_battery_event: Optional[Callable] = None
        # on_event(agv_id, event_name, data) — xử lý tất cả events
        self.on_event: Optional[Callable] = None

        # Pending commands: {agv_id: {cmd_id, sent_at, payload}}
        self._pending_cmds: dict[str, dict] = {}

    # ── Route management ──────────────────────────────────────────────────────

    def set_route(
        self,
        agv_id:    str,
        full_path: list,
        task_type: str = "delivery",
    ) -> LineAGVRoute:
        """
        Lưu route mới cho AGV và tính cửa sổ đầu tiên.
        Gọi từ build_order_for_traffic_route trước khi gửi plan.
        """
        str_path = [str(p) for p in full_path]
        w_end    = first_window_end(str_path)
        route    = LineAGVRoute(
            full_path=str_path,
            task_type=task_type,
            window_start=0,
            window_end=w_end,
            is_complete=(w_end == len(str_path) - 1),
        )
        self._routes[agv_id] = route
        print(f"[LINE_AGV] {agv_id}: set_route len={len(str_path)} "
              f"window=[0→{w_end}] final={route.is_complete}")
        return route

    def get_route(self, agv_id: str) -> Optional[LineAGVRoute]:
        return self._routes.get(agv_id)

    def clear_route(self, agv_id: str) -> None:
        self._routes.pop(agv_id, None)

    # ── Dispatch ──────────────────────────────────────────────────────────────

    def dispatch(self, agv_id: str, kind: str, payload_str: str) -> None:
        if kind == "state":
            self._on_state(agv_id, payload_str)
        elif kind == "connection":
            self._on_connection(agv_id, payload_str)

    # ── State handler ─────────────────────────────────────────────────────────

    def _on_state(self, agv_id: str, payload_str: str) -> None:
        try:
            data = json.loads(payload_str)
        except json.JSONDecodeError as e:
            print(f"[LINE_AGV] {agv_id}: JSON error: {e}")
            return

        state   = self.state_store.get_or_create(agv_id)
        old_tag = state.current_tag  # Optional[int]

        # ── Parse tag ─────────────────────────────────────────────────────────
        # Ưu tiên lastNodeId, fallback tag; bỏ qua nếu cả hai đều absent/rỗng
        raw_lid = data.get("lastNodeId")
        raw_tag = data.get("tag")
        last_node_raw = raw_lid if (raw_lid is not None and raw_lid != "") \
                        else (raw_tag if (raw_tag is not None and raw_tag != "") else None)

        if last_node_raw is not None:
            try:
                s = str(last_node_raw).strip()
                new_tag: Optional[int] = int(s) if s.lstrip("-").isdigit() else int(float(s))
            except (ValueError, TypeError):
                new_tag = old_tag   # giữ nguyên nếu parse lỗi
                print(f"[LINE_AGV] {agv_id}: parse tag failed raw={last_node_raw!r}")
        else:
            new_tag = old_tag   # không có tag trong payload — giữ nguyên vị trí

        # ── Parse prev_tag ────────────────────────────────────────────────────
        fw_prev = int(data.get("prev_tag", 0) or 0)
        if new_tag != old_tag and old_tag is not None:
            state.prev_tag = old_tag if old_tag else fw_prev
        elif state.prev_tag == 0 and fw_prev:
            state.prev_tag = fw_prev

        prev_tag = state.prev_tag

        # ── Cập nhật edge reservation ─────────────────────────────────────────
        if new_tag != old_tag and old_tag is not None and old_tag != 0 \
                and new_tag is not None and new_tag != 0:
            _release_line_edge(agv_id, prev_tag, old_tag)

        state.current_tag     = new_tag
        state.driving         = bool(data.get("driving", False))
        state.paused          = bool(data.get("paused",  False))
        state.operating_mode  = str(data.get("operatingMode", "MANUAL"))
        state.error_code      = int(data.get("error_code", 0) or 0)
        state.battery_low     = bool(data.get("battery_low", False))
        state.battery_blocking = bool(data.get("battery_blocking", False))
        state.last_update     = time.time()

        # Nhận được state message → AGV chắc chắn đang online
        if state.connection_state != "ONLINE":
            print(f"[LINE_AGV] {agv_id}: auto ONLINE (state message received)")
        state.connection_state = "ONLINE"

        # Battery (2 format)
        batt_obj = data.get("batteryState") or {}
        if batt_obj:
            state.battery = int(batt_obj.get("batteryCharge", state.battery) or state.battery)
        elif "battery" in data:
            state.battery = int(data["battery"] or 0)

        # ── ACK ───────────────────────────────────────────────────────────────
        ack_id = str(data.get("ack", "") or "").strip()
        if ack_id:
            state.last_ack = ack_id
            self._pending_cmds.pop(agv_id, None)
            # Đánh dấu acked cho rolling plan
            route = self._routes.get(agv_id)
            if route and route.sent_cmd_id == ack_id:
                route.acked = True

        # ── Cập nhật current_edge_pair ────────────────────────────────────────
        if state.driving and state.prev_tag and state.current_tag:
            state.current_edge_pair = (state.prev_tag, state.current_tag)
            _reserve_line_edge(agv_id, state.prev_tag, state.current_tag)
        else:
            if state.current_edge_pair:
                _release_all_line_edges(agv_id)
                state.current_edge_pair = None

        # ── Log thay đổi tag ──────────────────────────────────────────────────
        if new_tag != old_tag:
            print(f"[LINE_AGV] {agv_id}: tag {old_tag}→{new_tag}  "
                  f"bat={state.battery}%  bat_low={state.battery_low}  "
                  f"driving={state.driving}")
        elif old_tag is None and new_tag is None:
            print(f"[LINE_AGV] {agv_id}: state received (no tag in payload)")

        # ── Xử lý event từ xe ────────────────────────────────────────────────
        event_name = str(data.get("event", "") or "").strip()
        if event_name:
            self._handle_event(agv_id, event_name, data, state)

        # ── Rolling plan: kiểm tra có cần gửi cửa sổ tiếp không ─────────────
        if new_tag != old_tag:
            self._check_rolling_plan(agv_id, state)

        # ── Retry: gửi lại nếu không nhận ACK sau RETRY_TIMEOUT ──────────────
        self._check_retry(agv_id, state)

        # ── Callback thay đổi state ───────────────────────────────────────────
        if self.on_state_changed:
            try:
                self.on_state_changed(state)
            except Exception as e:
                print(f"[LINE_AGV] on_state_changed error: {e}")

    # ── Rolling plan ──────────────────────────────────────────────────────────

    def _check_rolling_plan(self, agv_id: str, state: LineAGVState) -> None:
        """Gửi cửa sổ tiếp theo nếu AGV đã đủ gần cuối cửa sổ hiện tại."""
        route = self._routes.get(agv_id)
        if route is None or route.is_complete:
            return
        if state.current_tag is None:
            return   # chưa biết vị trí

        tag_str = str(state.current_tag)
        try:
            current_idx = route.full_path.index(tag_str)
        except ValueError:
            return   # tag không thuộc route hiện tại

        if current_idx < route.window_start:
            return   # AGV chưa vào cửa sổ

        remaining = route.window_end - current_idx
        if remaining > LOOKAHEAD // 2:
            return   # Còn đủ dư, chưa cần gửi tiếp

        # Tính cửa sổ tiếp theo bắt đầu từ current_idx
        new_start = current_idx
        new_end   = min(current_idx + LOOKAHEAD, len(route.full_path) - 1)
        is_final  = (new_end == len(route.full_path) - 1)

        self._send_window(agv_id, route, new_start, new_end, is_final)

    def _send_window(
        self,
        agv_id:    str,
        route:     LineAGVRoute,
        w_start:   int,
        w_end:     int,
        is_final:  bool,
    ) -> None:
        """Build và gửi 1 cửa sổ plan."""
        if self.send_window_fn is None:
            print(f"[LINE_AGV] {agv_id}: send_window_fn chưa được inject!")
            return

        try:
            from map_manager import MapManager
            # Lấy points từ map_manager singleton (lazy import tránh circular)
            try:
                from mqtt_client import map_manager as _mm
                points = getattr(_mm, "points", {}) or {}
            except Exception:
                points = {}

            plan = build_plan_window(
                full_path=route.full_path,
                w_start=w_start,
                w_end=w_end,
                points=points,
                is_final=is_final,
                task_type=route.task_type,
            )

            route.window_start = w_start
            route.window_end   = w_end
            route.sent_cmd_id  = plan["id"]
            route.sent_at      = time.time()
            route.acked        = False
            route.is_complete  = is_final

            self.send_window_fn(agv_id, plan)
            print(f"[LINE_AGV] {agv_id}: sent window [{w_start}→{w_end}] "
                  f"id={plan['id']} final={is_final} steps={len(plan['d'])}")

        except Exception as e:
            print(f"[LINE_AGV] {agv_id}: _send_window error: {e}")

    # ── Retry ─────────────────────────────────────────────────────────────────

    def _check_retry(self, agv_id: str, state: LineAGVState) -> None:
        """Gửi lại plan nếu không nhận ACK sau RETRY_TIMEOUT."""
        route = self._routes.get(agv_id)
        if route is None or route.acked or not route.sent_cmd_id:
            return
        if time.time() - route.sent_at < RETRY_TIMEOUT:
            return
        # Không retry nếu xe đang đứng ở đầu cửa sổ (plan đã nhận, chưa di chuyển)
        tag_str = str(state.current_tag)
        if route.full_path and route.window_start < len(route.full_path):
            if tag_str == route.full_path[route.window_start]:
                return
        print(f"[LINE_AGV] {agv_id}: retry plan id={route.sent_cmd_id} "
              f"(no ACK after {RETRY_TIMEOUT}s)")
        self._send_window(
            agv_id, route,
            route.window_start, route.window_end,
            route.is_complete,
        )

    # ── Event handler ─────────────────────────────────────────────────────────

    def _handle_event(
        self,
        agv_id: str,
        event_name: str,
        data: dict,
        state: LineAGVState,
    ) -> None:
        print(f"[LINE_AGV] {agv_id}: event='{event_name}'")

        # Bước 1: gửi ACK ngay để AGV xóa pendingEvent
        # "continue", "confirm", "return" đều cần ack_event trước khi xử lý
        if self.on_event:
            try:
                self.on_event(agv_id, event_name, data)
            except Exception as e:
                print(f"[LINE_AGV] on_event callback error: {e}")
        else:
            # Fallback nếu callback chưa inject: tự gửi ack trực tiếp qua MQTT
            try:
                from mqtt_client import send_line_command as _slc
                _slc(agv_id, "ack_event", d=event_name)
                print(f"[LINE_AGV] {agv_id}: ACK (fallback) event='{event_name}'")
            except Exception as e:
                print(f"[LINE_AGV] {agv_id}: ACK fallback failed: {e}")

        # Bước 2: xử lý battery event
        if event_name == "battery_need_charge":
            state.battery_blocking = True
            if self.on_battery_event:
                try:
                    self.on_battery_event(agv_id, event_name, data)
                except Exception as e:
                    print(f"[LINE_AGV] on_battery_event callback error: {e}")

        # Bước 3: thông báo task_queue hoàn thành
        # "continue" = AGV đến đích, chờ hệ thống (tương đương "confirm")
        # "confirm"  = người dùng bấm nút HMI xác nhận
        # "return"   = xe đã về vị trí ban đầu
        _COMPLETE_EVENTS = ("confirm", "continue", "return", "battery_need_charge")
        if event_name in _COMPLETE_EVENTS:
            try:
                from task_queue import agv_task_queue
                agv_task_queue.on_agv_completed(agv_id, notes=f"event:{event_name}")
                print(f"[LINE_AGV] {agv_id}: task completed via event='{event_name}'")
            except Exception as e:
                print(f"[LINE_AGV] queue on_agv_completed error: {e}")

    # ── Connection handler ────────────────────────────────────────────────────

    def _on_connection(self, agv_id: str, payload_str: str) -> None:
        try:
            data       = json.loads(payload_str)
            conn_state = str(data.get("connectionState", "OFFLINE")).upper()
        except Exception:
            conn_state = "OFFLINE"

        state = self.state_store.get_or_create(agv_id)
        old   = state.connection_state

        # Bỏ qua LWT/retained cũ: nếu AGV vừa gửi state gần đây thì nó đang ONLINE thật
        if conn_state in ("OFFLINE", "CONNECTIONBROKEN") and state.last_update > 0:
            elapsed = time.time() - state.last_update
            if elapsed < OFFLINE_TIMEOUT_SEC:
                print(f"[LINE_AGV] {agv_id}: ignored stale '{conn_state}' "
                      f"(state nhận {elapsed:.1f}s trước < {OFFLINE_TIMEOUT_SEC}s)")
                return

        state.connection_state = conn_state

        if conn_state != old:
            print(f"[LINE_AGV] {agv_id}: connection {old}→{conn_state}")

        if conn_state in ("OFFLINE", "CONNECTIONBROKEN"):
            _release_all_line_edges(agv_id)
            state.current_edge_pair = None

    # ── Manual position override ─────────────────────────────────────────────

    def override_position(self, agv_id: str, tag: int) -> None:
        """Đặt thủ công vị trí AGV (dùng khi server mới khởi động chưa nhận state)."""
        state = self.state_store.get_or_create(agv_id)
        old   = state.current_tag
        state.current_tag = tag
        if state.last_update == 0.0:
            state.last_update = time.time()
        if state.connection_state != "ONLINE":
            state.connection_state = "ONLINE"
        print(f"[LINE_AGV] {agv_id}: position overridden {old}→{tag} (manual set)")

    # ── Pending command tracking ───────────────────────────────────────────────

    def record_sent_cmd(self, agv_id: str, cmd_id: str, payload) -> None:
        self._pending_cmds[agv_id] = {
            "cmd_id":  cmd_id,
            "sent_at": time.time(),
            "payload": payload,
        }
        # Cũng cập nhật route nếu có
        route = self._routes.get(agv_id)
        if route and cmd_id:
            route.sent_cmd_id = cmd_id
            route.sent_at     = time.time()
            route.acked       = False

    def get_pending_cmd(self, agv_id: str) -> Optional[dict]:
        return self._pending_cmds.get(agv_id)


# ── Module-level singleton ────────────────────────────────────────────────────
line_agv_handler = LineAGVHandler()
