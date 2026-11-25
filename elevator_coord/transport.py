"""
transport.py — Giao diện truyền thông MQTT tối giản + adapter paho (tùy chọn).

Coordinator chỉ cần 3 thao tác: publish / subscribe / nhận message. Nhờ vậy:
  * test dùng FakeBroker (sim/fake_broker.py), không cần paho/broker;
  * dev FMS có thể tự viết adapter cho thư viện MQTT khác trong ~20 dòng.
"""
from __future__ import annotations

import logging
import ssl
from typing import Callable, List, Optional, Protocol, Union

log = logging.getLogger("elevator_coord.transport")

MessageHandler = Callable[[str, bytes], None]


class Transport(Protocol):
    def publish(self, topic: str, payload: str, qos: int = 1, retain: bool = False) -> None: ...

    def subscribe(self, topic_filter: str, qos: int = 1) -> None: ...

    def set_message_handler(self, handler: MessageHandler) -> None:
        """handler(topic, payload_bytes). Có thể được gọi từ thread khác của thư viện MQTT."""


class PahoTransport:
    """
    Adapter cho paho-mqtt (1.x và 2.x).

    Hai cách dùng:
      1) Dùng lại client MQTT sẵn có của FMS (khuyến nghị):
             t = PahoTransport(existing_client)
         Adapter dùng `message_callback_add()` theo từng filter nên KHÔNG ghi đè `on_message` của FMS.
         paho mặc định clean_session=True => mất subscribe khi reconnect: gọi `t.resubscribe()`
         trong `on_connect` của FMS.
      2) Chạy độc lập (thử với Mosquitto):  t = PahoTransport.standalone("host", 1883)
    """

    def __init__(self, client) -> None:
        self._client = client
        self._handler: Optional[MessageHandler] = None
        self._filters: List[tuple] = []
        self._link_handler: Optional[Callable[[bool], None]] = None

    def set_link_handler(self, handler: Callable[[bool], None]) -> None:
        """handler(up): kết nối của FMS tới broker lên/xuống (standalone tự gọi; dùng client sẵn có thì
        FMS gọi `notify_link(True/False)` trong on_connect/on_disconnect của mình)."""
        self._link_handler = handler

    def notify_link(self, up: bool) -> None:
        if self._link_handler is not None:
            self._link_handler(up)

    @classmethod
    def standalone(cls, host: str, port: int = 1883, username: Optional[str] = None,
                   password: Optional[str] = None, tls: bool = False,
                   client_id: str = "elevator-coordinator", keepalive: int = 15) -> "PahoTransport":
        import paho.mqtt.client as mqtt  # import trễ: paho là tùy chọn
        try:
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id)   # paho >= 2.0
        except AttributeError:
            client = mqtt.Client(client_id)                                     # paho 1.x
        if username:
            client.username_pw_set(username, password)
        if tls:
            client.tls_set(cert_reqs=ssl.CERT_NONE)
            client.tls_insecure_set(True)
        self = cls(client)
        def _on_connect(c, u, f, rc, *a):
            self.resubscribe()
            self.notify_link(rc == 0)
        client.on_connect = _on_connect
        client.on_disconnect = lambda c, u, rc, *a: self.notify_link(False)
        client.reconnect_delay_set(min_delay=1, max_delay=30)
        client.connect_async(host, port, keepalive)
        client.loop_start()
        return self

    def set_message_handler(self, handler: MessageHandler) -> None:
        self._handler = handler

    def subscribe(self, topic_filter: str, qos: int = 1) -> None:
        self._filters.append((topic_filter, qos))
        self._client.message_callback_add(topic_filter, self._on_message)
        self._client.subscribe(topic_filter, qos)

    def resubscribe(self) -> None:
        for flt, qos in self._filters:
            self._client.subscribe(flt, qos)

    def publish(self, topic: str, payload: str, qos: int = 1, retain: bool = False) -> None:
        self._client.publish(topic, payload, qos=qos, retain=retain)

    def _on_message(self, client, userdata, msg) -> None:
        if self._handler is not None:
            try:
                self._handler(msg.topic, msg.payload)
            except Exception:   # không để lỗi logic làm chết thread mạng của paho
                log.exception("lỗi khi xử lý message %s", msg.topic)
