"""
fake_broker.py — Broker MQTT giả trong bộ nhớ (wildcard +/#, retained, LWT, mất gói).

Giao hàng KHÔNG đồng bộ: publish() chỉ xếp hàng, pump() mới phát — tránh đệ quy và cho phép
test xác định thứ tự. Mỗi FakeClient thỏa giao diện `Transport`.
"""
from __future__ import annotations

import random
from collections import deque
from typing import Callable, Deque, Dict, List, Optional, Tuple

from ..clock import Clock

DropRule = Callable[[str, str], bool]   # (topic, payload_str) -> True nếu mất gói


def topic_matches(flt: str, topic: str) -> bool:
    fp, tp = flt.split("/"), topic.split("/")
    for i, f in enumerate(fp):
        if f == "#":
            return True
        if i >= len(tp):
            return False
        if f != "+" and f != tp[i]:
            return False
    return len(fp) == len(tp)


class FakeClient:
    def __init__(self, broker: "FakeBroker", name: str,
                 will: Optional[Tuple[str, str, int, bool]] = None) -> None:
        self.broker = broker
        self.name = name
        self.will = will
        self.connected = True
        self._handler: Optional[Callable[[str, bytes], None]] = None
        self.filters: List[str] = []

    # --- Transport ---
    def set_message_handler(self, handler: Callable[[str, bytes], None]) -> None:
        self._handler = handler

    def subscribe(self, topic_filter: str, qos: int = 1) -> None:
        if topic_filter not in self.filters:
            self.filters.append(topic_filter)
        self.broker._deliver_retained(self, topic_filter)

    def publish(self, topic: str, payload: str, qos: int = 1, retain: bool = False) -> None:
        if not self.connected:
            return
        self.broker._enqueue(topic, payload, retain)

    # --- tiện ích test ---
    def _receive(self, topic: str, payload: str) -> None:
        if self.connected and self._handler is not None:
            self._handler(topic, payload.encode("utf-8"))


class FakeBroker:
    def __init__(self, clock: Clock, seed: int = 0) -> None:
        self.clock = clock
        self.rng = random.Random(seed)
        self.clients: List[FakeClient] = []
        self.retained: Dict[str, str] = {}
        self._queue: Deque[Tuple[str, str, bool]] = deque()
        self._drop: List[DropRule] = []
        self.log: List[Tuple[float, str, str]] = []     # (t, topic, payload) — mọi gói ĐÃ được nhận (chưa tính mất)
        self.dropped: List[Tuple[float, str, str]] = []

    def client(self, name: str, will: Optional[Tuple[str, str, int, bool]] = None) -> FakeClient:
        c = FakeClient(self, name, will)
        self.clients.append(c)
        return c

    # --- mất gói ---
    def add_drop_rule(self, rule: DropRule) -> DropRule:
        self._drop.append(rule)
        return rule

    def remove_drop_rule(self, rule: DropRule) -> None:
        if rule in self._drop:
            self._drop.remove(rule)

    def clear_drop_rules(self) -> None:
        self._drop.clear()

    # --- ngắt kết nối bất thường (kích LWT) ---
    def kill(self, client: FakeClient) -> None:
        if not client.connected:
            return
        client.connected = False
        if client.will:
            topic, payload, _qos, retain = client.will
            self._enqueue(topic, payload, retain)

    def revive(self, client: FakeClient) -> None:
        client.connected = True
        for f in client.filters:
            self._deliver_retained(client, f)

    # --- nội bộ ---
    def _enqueue(self, topic: str, payload: str, retain: bool) -> None:
        self._queue.append((topic, payload, retain))

    def _deliver_retained(self, client: FakeClient, flt: str) -> None:
        for topic, payload in list(self.retained.items()):
            if topic_matches(flt, topic):
                self._queue.append(("\0" + client.name + "\0" + topic, payload, False))

    def pump(self, limit: int = 100000) -> int:
        n = 0
        while self._queue and n < limit:
            topic, payload, retain = self._queue.popleft()
            n += 1
            target: Optional[str] = None
            if topic.startswith("\0"):          # gói retained gửi riêng cho 1 client mới subscribe
                _, target, topic = topic.split("\0", 2)
            now = self.clock.monotonic()
            if any(rule(topic, payload) for rule in self._drop):
                self.dropped.append((now, topic, payload))
                continue
            self.log.append((now, topic, payload))
            if retain and target is None:
                if payload == "":
                    self.retained.pop(topic, None)
                else:
                    self.retained[topic] = payload
            for c in list(self.clients):
                if target is not None and c.name != target:
                    continue
                if any(topic_matches(f, topic) for f in c.filters):
                    c._receive(topic, payload)
        return n

    # --- truy vấn log ---
    def published(self, topic_filter: str) -> List[Tuple[float, str, str]]:
        return [x for x in self.log if topic_matches(topic_filter, x[1])]
