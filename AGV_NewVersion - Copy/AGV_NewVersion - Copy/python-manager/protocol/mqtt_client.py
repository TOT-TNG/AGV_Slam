"""
protocol/mqtt_client.py  — MQTT Client Setup
---------------------------------------------
Migrate từ main.py: MQTT setup block (lines 345–359), App.btn_connect_mqtt.
"""
from __future__ import annotations
import ssl
import paho.mqtt.client as mqtt
from typing import TYPE_CHECKING
from log_mgmt.system_logger import sys_log, LOG_SYSTEM, LOG_ERROR

if TYPE_CHECKING:
    from core.context import AppContext


def setup(ctx: AppContext) -> mqtt.Client:
    """
    Khởi tạo MQTT client, wire callbacks, kết nối broker.
    Gán ctx.mqtt và ctx.mqtt_connected.

    Dùng lại ctx.mqtt nếu đã tồn tại (được tạo trong main.py và gán cho
    agv.mqtt trước khi setup() được gọi) — tránh tạo ra 2 client khác nhau
    khiến agv.mqtt.publish() publish trên client chưa kết nối.
    """
    from protocol.message_handler import on_connect, on_disconnect, on_message, _set_context
    _set_context(ctx)

    if ctx.mqtt is None:
        ctx.mqtt = mqtt.Client("Python_Manager_Server")
    client = ctx.mqtt
    client.on_connect    = on_connect
    client.on_disconnect = on_disconnect
    client.on_message    = on_message

    _connect(ctx)
    return client


def _connect(ctx: AppContext):
    """Kết nối tới broker từ config. Tự động thử lại qua loop."""
    client = ctx.mqtt
    cfg    = ctx.config.get('mqtt', {})
    if cfg.get('username'):
        client.username_pw_set(cfg['username'], cfg['password'])

    port = int(cfg.get('port', 1883))
    if port == 8883:
        client.tls_set(cert_reqs=ssl.CERT_NONE)
        client.tls_insecure_set(True)
        client._tls_set_done = True

    try:
        broker = cfg.get('broker', 'localhost')
        client.connect(broker, port, 60)
        client.loop_start()
        sys_log(LOG_SYSTEM, "mqtt_client", f"Connecting → {broker}:{port}")
    except Exception as e:
        sys_log(LOG_ERROR, "mqtt_client", f"Cannot connect to MQTT Broker: {e}")


def reconnect(ctx: AppContext):
    """Kết nối lại (gọi từ GUI Settings sau khi đổi broker)."""
    try:
        ctx.mqtt.disconnect()
    except Exception:
        pass
    _connect(ctx)
