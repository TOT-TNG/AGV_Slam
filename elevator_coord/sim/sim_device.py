"""
sim_device.py — Lõi chung của thiết bị giả (đúng hợp đồng docs/04 §3.3, §5):
  * kết nối: LWT + ONLINE retained, subscribe instantActions + manager/connection
  * khử trùng action theo actionId, giữ 8 action gần nhất trong actionStates
  * publish state khi đổi (cách nhau >= min_gap_s) và heartbeat mỗi heartbeat_s
Đây cũng là *reference behavior* cho firmware thật (firmware/…).
"""
from __future__ import annotations

import json
import math
from typing import Any, Dict, List, Optional, Tuple

from .. import protocol as P
from ..clock import Clock
from .fake_broker import FakeBroker, FakeClient


class SimDevice:
    kind = ""

    def __init__(self, broker: FakeBroker, clock: Clock, factory: str, elevator_id: str, device_id: str,
                 heartbeat_s: float = 1.0, min_gap_s: float = 0.1) -> None:
        self.broker = broker
        self.clock = clock
        self.factory = factory
        self.elevator_id = elevator_id
        self.device_id = device_id
        self.heartbeat_s = heartbeat_s
        self.min_gap_s = min_gap_s
        self.t_state = P.topic_state(factory, elevator_id, device_id)
        self.t_actions = P.topic_actions(factory, elevator_id, device_id)
        self.t_conn = P.topic_connection(factory, elevator_id, device_id)
        self.t_mgr = P.manager_connection_topic(factory)
        self._hdr = P.HeaderCounter()
        self.history: List[P.ActionState] = []
        self.executed: List[Tuple[str, str, Dict[str, Any]]] = []   # (type, id, params) — để test kiểm đếm
        self.powered = True
        self.net = True                 # False = mất mạng nhưng thiết bị VẪN chạy (cabin đóng cửa)
        self.manager_online = True
        self._last_sig: Optional[str] = None
        self._last_pub = -1e9
        will_payload = P.build_connection(self._header(self.t_conn), P.CONN_BROKEN)
        self.client: FakeClient = broker.client(f"{elevator_id}-{device_id}", (self.t_conn, will_payload, 1, True))
        self.client.set_message_handler(self._on_message)
        self.client.subscribe(self.t_actions)
        self.client.subscribe(self.t_mgr)
        self._publish_online()

    # ---------------- kết nối ----------------
    def _header(self, topic: str) -> Dict[str, Any]:
        return P.build_header(self._hdr.next(topic), self.clock.wall(), self.factory,
                              self.elevator_id, self.device_id)

    def _publish_online(self) -> None:
        self.client.publish(self.t_conn, P.build_connection(self._header(self.t_conn), P.CONN_ONLINE),
                            qos=1, retain=True)

    def power_off(self) -> None:
        """Mất điện/Wi-Fi: broker bắn LWT."""
        self.powered = False
        self.broker.kill(self.client)

    def net_down(self) -> None:
        """Mất mạng (cabin đóng cửa): broker bắn LWT, thiết bị vẫn chạy logic cục bộ nhưng không gửi/nhận được gì."""
        if self.net:
            self.net = False
            self.broker.kill(self.client)

    def net_up(self) -> None:
        """Có mạng lại: gửi ONLINE (retained) rồi state ngay."""
        if not self.net:
            self.net = True
            self.broker.revive(self.client)
            self._publish_online()
            self._last_sig = None
            self._last_pub = -1e9

    def power_on(self) -> None:
        """Khởi động lại: output về LOW, quên lịch sử action."""
        self.powered = True
        self.history.clear()
        self._boot()
        self.broker.revive(self.client)
        self._publish_online()
        self._last_sig = None

    # ---------------- nhận message ----------------
    def _on_message(self, topic: str, payload: bytes) -> None:
        if not self.powered or not self.net:
            return
        if topic == self.t_mgr:
            try:
                online = P.parse_connection(payload) == P.CONN_ONLINE
            except P.ProtocolError:
                return
            if self.manager_online and not online:
                self.on_manager_lost()
            self.manager_online = online
            return
        if topic != self.t_actions:
            return
        try:
            actions = P.parse_actions(payload)
        except P.ProtocolError:
            return
        now = self.clock.monotonic()
        for typ, aid, params in actions:
            if any(h.action_id == aid for h in self.history):
                continue                                   # khử trùng: KHÔNG thực thi lại
            st = P.ActionState(aid, typ, P.ST_WAITING)
            self.history.append(st)
            del self.history[:-P.ACTION_HISTORY]
            self.executed.append((typ, aid, params))
            self._exec(st, typ, params, now)

    # ---------------- hook cho lớp con ----------------
    def _boot(self) -> None: ...
    def on_manager_lost(self) -> None: ...
    def _exec(self, st: P.ActionState, typ: str, params: Dict[str, Any], now: float) -> None: ...
    def _logic(self, now: float) -> None: ...
    def _build_state(self) -> str: ...

    # ---------------- vòng lặp ----------------
    def tick(self) -> None:
        if not self.powered:
            return
        now = self.clock.monotonic()
        self._logic(now)
        if not self.net:
            return
        payload = self._build_state()
        sig = self._signature(payload)
        due_change = sig != self._last_sig and (now - self._last_pub) >= self.min_gap_s
        due_beat = (now - self._last_pub) >= self.heartbeat_s
        if due_change or due_beat:
            self.client.publish(self.t_state, payload, qos=0, retain=False)
            self._last_sig = sig
            self._last_pub = now

    @staticmethod
    def _signature(payload: str) -> str:
        obj = json.loads(payload)
        for k in ("headerId", "timestamp", "diag"):
            obj.pop(k, None)
        el = obj.get("elevator")
        if isinstance(el, dict):
            el.pop("holdTtlS", None)
        h = (obj.get("caller") or {}).get("hall")
        if isinstance(h, dict):
            h.pop("ttlS", None)
        return json.dumps(obj, sort_keys=True)

    @staticmethod
    def ceil_s(x: float) -> int:
        return max(0, int(math.ceil(x)))
