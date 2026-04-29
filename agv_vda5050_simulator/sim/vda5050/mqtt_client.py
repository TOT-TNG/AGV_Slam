from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from typing import Any, Callable, Optional

try:
    import paho.mqtt.client as mqtt
except Exception:  # pragma: no cover
    mqtt = None


OrderCallback = Callable[[dict[str, Any]], None]
ActionCallback = Callable[[dict[str, Any]], None]


@dataclass
class MQTTSettings:
    host: str
    port: int
    keepalive: int
    enabled: bool = True
    interface_name: str = 'uagv'
    major_version: str = 'v3'


class VDAMQTTClient:
    def __init__(
        self,
        *,
        manufacturer: str,
        agv_id: str,
        settings: MQTTSettings,
        on_order: OrderCallback,
        on_instant_actions: ActionCallback,
        on_connected: Optional[Callable[[], None]] = None,
    ) -> None:
        self.manufacturer = manufacturer
        self.agv_id = agv_id
        self.settings = settings
        self.on_order = on_order
        self.on_instant_actions = on_instant_actions
        self.on_connected = on_connected
        self.base_topic = f'{settings.interface_name}/{settings.major_version}/{manufacturer}/{agv_id}'
        self._connected = False
        self._enabled = settings.enabled and mqtt is not None
        self._lock = threading.Lock()
        self.client: Optional[Any] = None
        self.last_error = '' if self._enabled else self._disabled_reason()
        self.last_publish_suffix = ''
        self.last_publish_topic = ''
        self.last_publish_ok = False

        if self._enabled:
            self.client = mqtt.Client(client_id=f'sim_{agv_id}', protocol=mqtt.MQTTv311)
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.on_message = self._on_message
            self.client.reconnect_delay_set(min_delay=1, max_delay=10)

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def status_label(self) -> str:
        if not self._enabled:
            return 'DISABLED'
        return 'ONLINE' if self._connected else 'OFFLINE'

    def connect(self) -> None:
        if not self._enabled or self.client is None:
            self.last_error = self._disabled_reason()
            return
        try:
            self.client.connect_async(self.settings.host, self.settings.port, self.settings.keepalive)
            self.client.loop_start()
            self.last_error = ''
        except Exception as exc:
            self._connected = False
            self.last_error = str(exc)

    def disconnect(self) -> None:
        if not self._enabled or self.client is None:
            return
        try:
            self.client.loop_stop()
            self.client.disconnect()
        except Exception:
            pass
        self._connected = False

    def reconnect(self) -> None:
        self.disconnect()
        self.connect()

    def publish(self, suffix: str, payload: dict[str, Any], *, qos: int = 0, retain: bool = False) -> bool:
        self.last_publish_suffix = suffix
        self.last_publish_topic = f'{self.base_topic}/{suffix}'
        self.last_publish_ok = False
        if not self._enabled or self.client is None:
            self.last_error = self._disabled_reason()
            return False
        if not self._connected:
            self.last_error = 'MQTT is offline'
            return False
        try:
            self.client.publish(self.last_publish_topic, json.dumps(payload), qos=qos, retain=retain)
            self.last_publish_ok = True
            self.last_error = ''
            return True
        except Exception as exc:
            self._connected = False
            self.last_error = str(exc)
            return False

    def _on_connect(self, client: Any, userdata: Any, flags: Any, rc: int, properties: Any = None) -> None:
        self._connected = (rc == 0)
        if not self._connected:
            self.last_error = f'MQTT connect rc={rc}'
            return
        self.last_error = ''
        client.subscribe(f'{self.base_topic}/order', qos=1)
        client.subscribe(f'{self.base_topic}/instantActions', qos=1)
        if self.on_connected:
            self.on_connected()

    def _on_disconnect(self, client: Any, userdata: Any, rc: int, properties: Any = None) -> None:
        self._connected = False
        if rc != 0:
            self.last_error = f'MQTT disconnected rc={rc}'

    def _on_message(self, client: Any, userdata: Any, msg: Any) -> None:
        try:
            payload = json.loads(msg.payload.decode('utf-8'))
        except Exception:
            return
        if msg.topic.endswith('/order'):
            self.on_order(payload)
        elif msg.topic.endswith('/instantActions'):
            self.on_instant_actions(payload)

    @staticmethod
    def _disabled_reason() -> str:
        if mqtt is None:
            return 'paho-mqtt is not installed'
        return 'MQTT disabled by config'
