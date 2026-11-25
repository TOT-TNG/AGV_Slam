"""
sim_uelev.py — Thiết bị thang GIẢ nói giao thức uelev/v2 (04-giao-thuc-mqtt.md) cho mô phỏng fleet.

Dùng lại nguyên bộ thiết bị giả của thư viện elevator_coord (SimCar = PLC thang, SimMaster = Master cabin,
SimCaller = bộ gọi tầng — chính là "hành vi tham chiếu" cho firmware thật), chỉ thay broker giả trong bộ nhớ
bằng 1 shim chạy trên client MQTT THẬT của sim_fleet và thay đồng hồ ảo bằng đồng hồ thật.

Thêm 1 điều thực tế mà thư viện tự nó không biết: XE trong cabin mất mạng khi cửa đóng (cùng Master) và có mạng lại
cùng lúc cửa mở — `update_occupants()` đặt cờ offline cho xe ảo (sim_fleet bỏ qua mọi lệnh + không publish state).
"""
from __future__ import annotations

import os
import sys
import threading
import time
from typing import Callable, Dict, List, Optional

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from elevator_coord import protocol as P                      # noqa: E402
from elevator_coord.clock import SystemClock                  # noqa: E402
from elevator_coord.sim.fake_broker import topic_matches      # noqa: E402
from elevator_coord.sim.sim_caller import SimCaller           # noqa: E402
from elevator_coord.sim.sim_car import SimCar                 # noqa: E402
from elevator_coord.sim.sim_master import SimMaster           # noqa: E402


class _ShimClient:
    """Thay FakeClient: publish/subscribe/set_message_handler qua client MQTT thật; `connected=False` mô phỏng mất mạng."""

    def __init__(self, shim: "PahoShim", name: str, will) -> None:
        self.shim, self.name, self.will = shim, name, will
        self.connected = True
        self.filters: List[str] = []
        self._handler: Optional[Callable[[str, bytes], None]] = None

    def set_message_handler(self, handler) -> None:
        self._handler = handler

    def subscribe(self, topic_filter: str, qos: int = 1) -> None:
        if topic_filter not in self.filters:
            self.filters.append(topic_filter)
        self.shim.subscribe(topic_filter)
        self.shim.replay_retained(self, topic_filter)

    def publish(self, topic: str, payload: str, qos: int = 1, retain: bool = False) -> None:
        if self.connected:
            self.shim.paho.publish(topic, payload, qos=qos, retain=retain)


class PahoShim:
    """Giống FakeBroker nhưng giao hàng qua paho thật (không có pump — paho tự gọi dispatch())."""

    def __init__(self, paho_client) -> None:
        self.paho = paho_client
        self.clients: List[_ShimClient] = []
        self._subs: List[str] = []
        self._last: Dict[str, bytes] = {}        # tin cuối theo topic (giả lập retained cho thiết bị nối lại)

    def client(self, name: str, will=None) -> _ShimClient:
        c = _ShimClient(self, name, will)
        self.clients.append(c)
        return c

    def subscribe(self, flt: str) -> None:
        if flt not in self._subs:
            self._subs.append(flt)
        try:
            self.paho.subscribe(flt, qos=1)
        except Exception:
            pass

    def resubscribe(self) -> None:
        for f in self._subs:
            self.paho.subscribe(f, qos=1)

    def replay_retained(self, client: _ShimClient, flt: str) -> None:
        for t, p in list(self._last.items()):
            if topic_matches(flt, t) and client._handler is not None:
                client._handler(t, p)

    def kill(self, client: _ShimClient) -> None:
        if not client.connected:
            return
        client.connected = False
        if client.will:                           # LWT: broker bắn khi thiết bị mất kết nối
            topic, payload, qos, retain = client.will
            self.paho.publish(topic, payload, qos=qos, retain=retain)

    def revive(self, client: _ShimClient) -> None:
        client.connected = True
        for f in client.filters:
            self.replay_retained(client, f)

    def dispatch(self, topic: str, payload: bytes) -> None:
        if topic.startswith("uagv/") and topic.endswith("/manager/connection"):
            self._last[topic] = payload
        for c in list(self.clients):
            if c.connected and c._handler is not None and any(topic_matches(f, topic) for f in c.filters):
                c._handler(topic, payload)


class UelevEmulator:
    def __init__(self, paho_client, factory: str, elevators: Dict[str, list], cabin_nodes: Dict[str, str],
                 agvs: Dict[str, object], logger, car_kwargs: Optional[dict] = None) -> None:
        """elevators: {eid: [số tầng thang dừng, đã sắp xếp]}; cabin_nodes: {node cabin: eid}; agvs: SimAgv của fleet."""
        self.factory = factory
        self.logger = logger
        self.agvs = agvs
        self.cabin_nodes = cabin_nodes
        self.clock = SystemClock()
        self.shim = PahoShim(paho_client)
        self.lock = threading.RLock()
        self.cars: Dict[str, SimCar] = {}
        self.masters: Dict[str, SimMaster] = {}
        self.callers: Dict[str, List[SimCaller]] = {}
        self._publish_state_cb: Optional[Callable[[str], None]] = None
        kw = dict(travel_s=3.0, door_open_delay=1.0, door_open_hold=6.0, door_close_s=1.5)
        kw.update(car_kwargs or {})
        for eid, levels in elevators.items():
            if len(levels) < 2:
                continue
            car = SimCar(floors=tuple(levels), start_floor=levels[0], **kw)
            self.cars[eid] = car
            self.masters[eid] = SimMaster(self.shim, self.clock, car, factory, eid, "master", levels)
            cs = []
            for i, lv in enumerate(levels):
                dirs = (["UP"] if i < len(levels) - 1 else []) + (["DN"] if i > 0 else [])
                cs.append(SimCaller(self.shim, self.clock, car, factory, eid, f"call{lv}", lv, dirs))
            self.callers[eid] = cs
        self._thread: Optional[threading.Thread] = None
        self._offline: set = set()

    def set_publish_state(self, fn: Callable[[str], None]) -> None:
        self._publish_state_cb = fn

    def start(self) -> None:
        if self._thread is None and self.cars:
            self._thread = threading.Thread(target=self._loop, name="uelev-emulator", daemon=True)
            self._thread.start()
            self.logger.info(f"[UELEV] thiết bị thang giả khởi động: "
                             f"{ {e: list(c.floors) for e, c in self.cars.items()} }")

    def on_paho_message(self, topic: str, payload: bytes) -> bool:
        """True nếu là tin của thiết bị thang (uelev/…) hoặc presence server."""
        if topic.startswith("uelev/") or topic.endswith("/manager/connection"):
            with self.lock:
                self.shim.dispatch(topic, payload)
            return True
        return False

    def on_paho_connect(self) -> None:
        with self.lock:
            self.shim.resubscribe()

    # ── vòng thời gian thực ──────────────────────────────────────────────────
    def _loop(self) -> None:
        last = time.monotonic()
        while True:
            time.sleep(0.1)
            now = time.monotonic()
            dt = now - last
            last = now
            try:
                with self.lock:
                    for eid, car in self.cars.items():
                        car.step(dt, self.clock.monotonic())
                        self.masters[eid].tick()
                        for c in self.callers[eid]:
                            c.tick()
                    self.update_occupants()
            except Exception as ex:
                self.logger.info(f"[UELEV] vòng lặp lỗi: {type(ex).__name__}: {ex}")

    def update_occupants(self) -> None:
        """Xe đang ở node cabin: cửa đóng/đang chạy → xe + Master mất mạng; cửa mở → có mạng lại."""
        def closed_of(car) -> bool:
            return car.door in ("CLOSING", "CLOSED") or car.moving

        for eid, car in self.cars.items():
            master = self.masters[eid]
            occ = [a for a in self.agvs.values() if self.cabin_nodes.get(str(a.current_tag)) == eid]
            if occ and closed_of(car):
                if master.net:
                    master.net_down()
                for a in occ:
                    if not a.offline:
                        a.offline = True
                        self._offline.add(a.agv_id)
                        self.logger.info(f"[UELEV] {a.agv_id} MẤT MẠNG trong cabin {eid} (cửa đóng)")
            elif not master.net:
                master.net_up()
        for aid in list(self._offline):
            a = self.agvs[aid]
            eid = self.cabin_nodes.get(str(a.current_tag))
            car = self.cars.get(eid) if eid else None
            if car is None or not closed_of(car):
                a.offline = False
                self._offline.discard(aid)
                self.logger.info(f"[UELEV] {aid} CÓ MẠNG lại")
                if self._publish_state_cb:
                    self._publish_state_cb(aid)
