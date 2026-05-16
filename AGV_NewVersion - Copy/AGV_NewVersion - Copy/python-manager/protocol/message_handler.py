"""
protocol/message_handler.py  — MQTT Message Dispatcher
-------------------------------------------------------
Migrate từ main.py: on_connect, on_disconnect, _find_agv_from_topic, on_message.
"""
from __future__ import annotations
import json
from typing import TYPE_CHECKING
from log_mgmt.system_logger import sys_log, LOG_MQTT_IN, LOG_WARN, LOG_SYSTEM, LOG_ERROR

if TYPE_CHECKING:
    from core.context import AppContext

# Context được set từ mqtt_client.setup()
_ctx: AppContext | None = None


def _set_context(ctx: AppContext):
    global _ctx
    _ctx = ctx


def _find_agv_from_topic(topic: str):
    """Trích AGV từ topic VDA5050: uagv/v2/{factory}/{agv_id}/{name}"""
    parts = topic.split('/')
    if len(parts) != 5:
        return None
    agv_id = parts[3]
    for agv in _ctx.agv_list:
        if agv.id == agv_id:
            return agv
    return None


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        _ctx.mqtt_connected = True
        sys_log(LOG_SYSTEM, "mqtt_client", "Connected to MQTT Broker")
        factory = _ctx.config.get('factory', 'default')
        wildcard_state = f"uagv/v2/{factory}/+/state"
        wildcard_conn  = f"uagv/v2/{factory}/+/connection"
        client.subscribe(wildcard_state)
        client.subscribe(wildcard_conn)
        sys_log(LOG_SYSTEM, "mqtt_client", f"Subscribed: {wildcard_state}")
        sys_log(LOG_SYSTEM, "mqtt_client", f"Subscribed: {wildcard_conn}")
    else:
        sys_log(LOG_ERROR, "mqtt_client", f"Failed to connect, return code {rc}")


def on_disconnect(client, userdata, rc):
    _ctx.mqtt_connected = False
    sys_log(LOG_SYSTEM, "mqtt_client", f"Disconnected from MQTT Broker (rc={rc})")


def on_message(client, userdata, msg):
    topic = msg.topic
    try:
        payload = msg.payload.decode('utf-8')
    except (UnicodeDecodeError, ValueError) as e:
        sys_log(LOG_WARN, "mqtt_client", f"payload non-UTF8 từ '{topic}' — bỏ qua. Lỗi: {e}")
        return
    sys_log(LOG_MQTT_IN, "mqtt_client", f"{topic}  >>  {payload}")

    parts = topic.split('/')
    if len(parts) != 5:
        return
    topic_name = parts[4]
    agv = _find_agv_from_topic(topic)

    if topic_name == 'state':
        if agv:
            agv.update_state(payload)
        else:
            sys_log(LOG_WARN, "mqtt_client",
                    f"AGV '{parts[3]}' không khớp config: {[a.id for a in _ctx.agv_list]}")

    elif topic_name == 'connection':
        if agv:
            try:
                data = json.loads(payload)
                state = data.get('connectionState', 'OFFLINE')
                agv.update_connection_state(state)
                sys_log(LOG_SYSTEM, "mqtt_client", f"{agv.id} connection → {state}")
            except Exception:
                pass
