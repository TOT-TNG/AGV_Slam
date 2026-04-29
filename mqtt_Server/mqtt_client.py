# mqtt_client.py
import json
import datetime
import time
import uuid
import math
import paho.mqtt.client as mqtt
from agv_manager import AGVManager
import asyncio
from fastapi import FastAPI

# ==========================
# MQTT Configuration
# ==========================
BROKER = "192.168.88.253"
PORT = 1883
QOS = 0
UAGV_INTERFACE_NAME = "uagv"
UAGV_MAJOR_VERSION = "v3"

agv_manager = AGVManager()

# ==========================
# ALERT STATE (assistant)
# ==========================
ALERT_COOLDOWN_SEC = 60
BATTERY_DROP_PERCENT = 5.0
BATTERY_DROP_WINDOW_SEC = 600
STUCK_DISTANCE_THRESHOLD = 0.05
STUCK_COUNT_THRESHOLD = 5

_last_battery = {}
_last_pos = {}
_stuck_count = {}
_last_alert_ts = {}
_last_error_signature = {}
_last_state_log_signature = {}


def _normalize_node_id(value) -> str:
    text = str(value or "").strip()
    if len(text) >= 2 and text[0] in {"N", "n"} and text[1:].isdigit():
        return text[1:]
    return text

def _should_emit(agv_id: str, key: str, now_ts: float, cooldown: int = ALERT_COOLDOWN_SEC) -> bool:
    last = _last_alert_ts.get((agv_id, key), 0)
    if now_ts - last < cooldown:
        return False
    _last_alert_ts[(agv_id, key)] = now_ts
    return True

def _emit_alert(agv_id: str, title: str, message: str, level: str = "warning"):
    app = get_app()
    ws_func = app.state.send_websocket_update
    if not ws_func:
        return
    payload = {
        "type": "assistant_alert",
        "agv_id": agv_id,
        "level": level,
        "title": title,
        "message": message,
        "timestamp": datetime.datetime.now().isoformat()
    }
    async def send_ws():
        await ws_func(payload)
    run_async_in_thread(send_ws())

def detect_alerts(agv_id: str, state_data: dict):
    now_ts = time.time()

    # AGV error reported
    errors = state_data.get("error") or []
    if errors:
        signature = json.dumps(errors, sort_keys=True, ensure_ascii=False)
        if _last_error_signature.get(agv_id) != signature and _should_emit(agv_id, "error", now_ts):
            first = errors[0] if isinstance(errors, list) else {}
            err_msg = first.get("errorDescription") or first.get("errorLevel") or "AGV reported error"
            _emit_alert(agv_id, "AGV error", f"{agv_id}: {err_msg}", level="error")
        _last_error_signature[agv_id] = signature

    # Map missing
    if not state_data.get("map_id"):
        if _should_emit(agv_id, "map_missing", now_ts):
            _emit_alert(agv_id, "Map missing", f"{agv_id}: map_id is empty", level="warning")

    # Battery drop too fast
    battery = (state_data.get("batteryState") or {}).get("batteryCharge")
    if isinstance(battery, (int, float)):
        last = _last_battery.get(agv_id)
        if last:
            prev_batt, prev_ts = last
            drop = prev_batt - float(battery)
            if drop >= BATTERY_DROP_PERCENT and (now_ts - prev_ts) <= BATTERY_DROP_WINDOW_SEC:
                if _should_emit(agv_id, "battery_drop", now_ts):
                    _emit_alert(
                        agv_id,
                        "Battery drop",
                        f"{agv_id}: battery dropped {drop:.1f}% in {int(now_ts - prev_ts)}s",
                        level="warning",
                    )
        _last_battery[agv_id] = (float(battery), now_ts)

    # Stuck detection while order is active
    order_id = state_data.get("orderId")
    x = float(state_data.get("x", 0.0))
    y = float(state_data.get("y", 0.0))
    if order_id:
        last_pos = _last_pos.get(agv_id)
        if last_pos:
            px, py = last_pos
            dist = math.hypot(x - px, y - py)
            if dist < STUCK_DISTANCE_THRESHOLD:
                _stuck_count[agv_id] = _stuck_count.get(agv_id, 0) + 1
            else:
                _stuck_count[agv_id] = 0
            if _stuck_count.get(agv_id, 0) >= STUCK_COUNT_THRESHOLD:
                if _should_emit(agv_id, "stuck", now_ts):
                    _emit_alert(agv_id, "Possible stuck", f"{agv_id}: no movement for a while", level="warning")
                _stuck_count[agv_id] = 0
        _last_pos[agv_id] = (x, y)
    else:
        _stuck_count[agv_id] = 0
        _last_pos[agv_id] = (x, y)

# ==========================
# ==========================
# LẤY APP TỪ MAIN MÀ KHÔNG GÂY CIRCULAR IMPORT
# ==========================
def get_app():
    import main
    return main.app
# ==========================
# CHẠY ASYNC TRONG THREAD MQTT (FIX NO EVENT LOOP)
# ==========================
def run_async_in_thread(coro):
    """??y coroutine v? ??ng event loop ch?nh c?a FastAPI khi ?ang ? thread MQTT."""
    try:
        app = get_app()
        app_loop = getattr(app.state, "loop", None)
        if app_loop and app_loop.is_running():
            future = asyncio.run_coroutine_threadsafe(coro, app_loop)

            def _report_error(done_future):
                try:
                    done_future.result()
                except Exception as exc:
                    print(f"[MQTT] Async task failed: {exc}")

            future.add_done_callback(_report_error)
            return
    except Exception as exc:
        print(f"[MQTT] Cannot schedule on app loop, fallback to local loop: {exc}")

    new_loop = asyncio.new_event_loop()
    try:
        new_loop.run_until_complete(coro)
    finally:
        new_loop.close()

# ==========================
# MQTT Event Handlers
# ==========================
def on_connect(client, userdata, flags, rc):
    print(f"[MQTT] Connected with result code {rc}")
    client.subscribe("vda5050/agv/+/state", qos=QOS)
    print("[MQTT] Subscribed: vda5050/agv/+/state")
    client.subscribe("vda5050/agv/+/instantActions", qos=QOS)
    print("[MQTT] Subscribed: vda5050/agv/+/instantActions")
    client.subscribe("vda5050/agv/+/order", qos=QOS)
    print("[MQTT] Subscribed: vda5050/agv/+/order")
    client.subscribe(f"{UAGV_INTERFACE_NAME}/{UAGV_MAJOR_VERSION}/+/+/state", qos=QOS)
    print(f"[MQTT] Subscribed: {UAGV_INTERFACE_NAME}/{UAGV_MAJOR_VERSION}/+/+/state")
    client.subscribe(f"{UAGV_INTERFACE_NAME}/{UAGV_MAJOR_VERSION}/+/+/instantActions", qos=QOS)
    print(f"[MQTT] Subscribed: {UAGV_INTERFACE_NAME}/{UAGV_MAJOR_VERSION}/+/+/instantActions")
    client.subscribe(f"{UAGV_INTERFACE_NAME}/{UAGV_MAJOR_VERSION}/+/+/order", qos=QOS)
    print(f"[MQTT] Subscribed: {UAGV_INTERFACE_NAME}/{UAGV_MAJOR_VERSION}/+/+/order")  # ĐÃ SUBSCRIBE


def _parse_topic(topic: str):
    topic_parts = topic.split("/")
    if len(topic_parts) >= 4 and topic_parts[0] == "vda5050" and topic_parts[1] == "agv":
        return topic_parts, topic_parts[2], topic_parts[3]
    if len(topic_parts) >= 5 and topic_parts[0] == UAGV_INTERFACE_NAME and topic_parts[1] == UAGV_MAJOR_VERSION:
        return topic_parts, topic_parts[3], topic_parts[4]
    return topic_parts, None, None


def on_message(client, userdata, msg):
    topic_parts, agv_id, message_kind = _parse_topic(msg.topic)

    try:
        # === DECODE PAYLOAD ===
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception as e:
            print(f"[MQTT] LỖI JSON: {e} | Raw: {msg.payload[:200]}")
            return

        # === XỬ LÝ STATE ===
        if message_kind == "state" and agv_id:
            agv_ip = "from_mqtt"

            pos = payload.get("agvPosition", {}) or {}
            map_id = payload.get("mapCurrent") or pos.get("mapId") or ""

            # Mạnh tay chuẩn hóa toạ độ nhận được
            x = (
                pos.get("x")
                or pos.get("X")
                or pos.get("posX")
                or pos.get("positionX")
                or 0.0
            )
            y = (
                pos.get("y")
                or pos.get("Y")
                or pos.get("posY")
                or pos.get("positionY")
                or 0.0
            )
            theta = pos.get("theta") or pos.get("Theta") or 0.0

            state_data = {
                "headerId": payload.get("headerId"),
                "timestamp": payload.get("timestamp"),
                "version": payload.get("version"),
                "manufacturer": payload.get("manufacturer"),
                "serialNumber": payload.get("serialNumber"),
                "mapCurrent": payload.get("mapCurrent"),
                "orderId": payload.get("orderId", ""),
                "orderUpdateId": payload.get("orderUpdateId", 0),
                "lastNodeId": payload.get("lastNodeId", ""),
                "nodeStates": payload.get("nodeStates", []),
                "edgeStates": payload.get("edgeStates", []),
                "agvPosition": pos,
                "velocity": payload.get("velocity"),
                "load": payload.get("load"),
                "paused": payload.get("paused", False),
                "batteryState": payload.get("batteryState", {}),
                "error": payload.get("error", []),
                "operationMode": payload.get("operationMode", "AUTOMATIC"),
                "actionState": payload.get("actionState", {}),
                "ipaddress": agv_ip,
                "x": x,
                "y": y,
                "theta": theta,
                "map_id": str(map_id)
            }

            # CẬP NHẬT AGV
            agv_manager.update_status(agv_id, state_data)
            detect_alerts(agv_id, state_data)
            app = get_app()
            traffic_handler = getattr(app.state, "handle_traffic_state_update", None)
            if traffic_handler:
                async def sync_traffic():
                    await traffic_handler(agv_id, state_data)
                run_async_in_thread(sync_traffic())

            state_log_signature = (
                str(state_data.get("lastNodeId") or ""),
                str(state_data.get("orderId") or ""),
                bool(state_data.get("paused")),
            )
            if _last_state_log_signature.get(agv_id) != state_log_signature:
                _last_state_log_signature[agv_id] = state_log_signature
                print(
                    f"[STATE] {agv_id} | node={state_data['lastNodeId'] or '-'} "
                    f"| order={state_data['orderId'] or '-'} | paused={state_data['paused']}"
                )

            # === GỬI WEBSOCKET ===
            app = get_app()
            ws_func = app.state.send_websocket_update
            if ws_func:
                async def send_ws():
                    await ws_func({
                        "type": "agv_state",
                        "agv_id": agv_id,
                        "lastNodeId": state_data['lastNodeId'],
                        "orderId": state_data['orderId'],
                        "batteryCharge": state_data['batteryState'].get('batteryCharge'),
                        "x": x,
                        "y": y,
                        "theta": theta,
                        "paused": state_data['paused'],
                        "timestamp": datetime.datetime.now().isoformat()
                    })
                run_async_in_thread(send_ws())

            # === BROADCAST POSE REALTIME LÊN DASHBOARD ===
            if map_id is not None:
                try:
                    from main import broadcast_agv_pose

                    async def send_pose():
                        await broadcast_agv_pose(agv_id, float(x), float(y), float(theta), str(map_id))

                    run_async_in_thread(send_pose())
                except Exception as e:
                    print(f"[WS] Lỗi broadcast pose: {e}")

            # === GIẢI PHÓNG KHÓA ĐƯỜNG KHI ORDER KẾT THÚC ===
            try:
                order_status = (payload.get("orderStatus") or "").upper()
                all_nodes_finished = payload.get("nodeStates") and all(ns.get("nodeStatus") == "FINISHED" for ns in payload["nodeStates"])
                should_release = order_status in ["FINISHED", "CANCELED", "ABORTED"]
                # Some AGVs only report completed nodeStates for already-passed nodes while the mission is still active.
                if not should_release and all_nodes_finished and not payload.get("orderId"):
                    should_release = True
                if should_release:
                    traffic_engine = getattr(app.state, "traffic_engine", None)
                    if traffic_engine:
                        traffic_engine.release_agv(agv_id)
                    agv_manager.clear_pending_path(agv_id)
                    agv_manager.set_last_control_action(agv_id, None)
                    print(f"[COORD] Released locks for {agv_id} | status={order_status or 'ALL_NODES_FINISHED'}")
            except Exception as e:
                print(f"[COORD] Release failed for {agv_id}: {e}")

            # === TỰ ĐỘNG GỬI ORDER UPDATE KHI HOÀN THÀNH NODE ===
            if False and payload.get("nodeStates"):
                for ns in payload["nodeStates"]:
                    if ns.get("nodeStatus") == "FINISHED":
                        node_id = ns["nodeId"]
                        print(f"[AUTO UPDATE] AGV {agv_id} HOÀN THÀNH node: {node_id}")

                        pending_path = agv_manager.get_pending_path(agv_id)
                        if pending_path and len(pending_path) > 1:
                            next_destination = pending_path[-1]
                            print(f"[AUTO UPDATE] Gửi order update đến: {next_destination}")

                            from model import MoveCommand
                            cmd = MoveCommand(agv_id=agv_id, destination=next_destination)

                            move_func = app.state.move_agv_func
                            if move_func:
                                async def send_move():
                                    await move_func(cmd)
                                run_async_in_thread(send_move())
                                print(f"[AUTO UPDATE] ĐÃ GỬI order update tự động cho {agv_id}")

        # === XỬ LÝ LỆNH MOVE TỪ MQTT EXPLORER ===
        elif message_kind == "order" and agv_id:
            if len(topic_parts) >= 2 and topic_parts[0] == "vda5050" and topic_parts[1] == "agv":
                return
            try:
                inbound_order_id = str(payload.get("orderId") or "").strip()
                inbound_update_id = int(payload.get("orderUpdateId") or 0)
                current_order = agv_manager.get_order(agv_id)
                if (
                    inbound_order_id
                    and inbound_order_id == str(current_order.get("order_id") or "").strip()
                    and inbound_update_id == int(current_order.get("order_update_id") or 0)
                ):
                    return

                nodes = payload.get("nodes") or []
                if not nodes:
                    return

                ordered_nodes = sorted(
                    [node for node in nodes if isinstance(node, dict)],
                    key=lambda item: int(item.get("sequenceId", 10**9)),
                )
                node_path = []
                for node in ordered_nodes:
                    node_id = _normalize_node_id(node.get("nodeId"))
                    if not node_id:
                        continue
                    if node_path and node_path[-1] == node_id:
                        continue
                    node_path.append(node_id)

                destination = node_path[-1] if node_path else ""
                if not destination:
                    return

                raw_map = (
                    payload.get("map_id")
                    or payload.get("mapCurrent")
                    or ((payload.get("agvPosition") or {}).get("mapId"))
                )

                from model import MoveCommand

                cmd = MoveCommand(
                    agv_id=agv_id,
                    destination=destination,
                    map_id=str(raw_map).strip() if raw_map else None,
                )
                agv_manager.set_pending_destination(agv_id, destination, str(raw_map).strip() if raw_map else None)
                agv_manager.clear_pending_path(agv_id)

                app = get_app()
                move_func = getattr(app.state, "move_agv_func", None)
                if move_func is None:
                    return

                async def send_move():
                    await move_func(cmd)

                run_async_in_thread(send_move())
                print(
                    f"[ORDER MQTT] {agv_id} | destination={destination} "
                    f"| requested_path={node_path if node_path else [destination]} "
                    f"| map={str(raw_map).strip() if raw_map else '-'}"
                )

            except Exception as e:
                print(f"[ORDER MQTT] L?i x? l? order: {e}")
                import traceback
                traceback.print_exc()

        elif "move" in topic_parts:
            agv_id = agv_id or (topic_parts[2] if len(topic_parts) > 2 else "")
            print(f"[MOVE COMMAND] Nhận lệnh di chuyển cho AGV: {agv_id}")

            try:
                move_data = payload
                destination = str(move_data.get("destination", "")).strip()
                if not destination:
                    print("[MOVE] LỖI: Không có destination!")
                    return

                # Lấy vị trí hiện tại
                current_state = agv_manager.get_status(agv_id)
                x = current_state.get("x", 0.0) if current_state else 0.0
                y = current_state.get("y", 0.0) if current_state else 0.0
                theta = current_state.get("theta", 0.0) if current_state else 0.0

                # Tạo order chuẩn VDA5050
                order = {
                    "headerId": int(time.time() * 1000),
                    "timestamp": datetime.datetime.now().isoformat() + "Z",
                    "version": "2.0",
                    "manufacturer": "TNG:TOT",
                    "serialNumber": agv_id,
                    "orderId": f"order_move_to_{destination}_{int(time.time())}",
                    "orderUpdateId": 0,
                    "nodes": [
                        {
                            "nodeId": "start",
                            "sequenceId": 0,
                            "released": True,
                            "nodePosition": {"x": x, "y": y, "theta": theta},
                            "actions": []
                        },
                        {
                            "nodeId": destination,
                            "sequenceId": 1,
                            "released": True,
                            "actions": [
                                {
                                    "actionId": f"move_to_{destination}",
                                    "actionType": "MOVE_TO_POSE",
                                    "blockingType": "HARD",
                                    "actionParameters": [
                                        {"key": "name", "value": destination}
                                    ]
                                }
                            ]
                        }
                    ],
                    "edges": [
                        {
                            "edgeId": f"edge_start_to_{destination}",
                            "sequenceId": 1,
                            "startNodeId": "start",
                            "endNodeId": destination,
                            "released": True,
                            "actions": []
                        }
                    ]
                }

                send_order(agv_id, order)
                print(f"[MOVE] ĐÃ GỬI order đến node {destination} thành công!")

                # Gửi thông báo realtime
                app = get_app()
                ws_func = app.state.send_websocket_update
                if ws_func:
                    async def notify():
                        await ws_func({
                            "type": "order_sent",
                            "agv_id": agv_id,
                            "destination": destination,
                            "orderId": order["orderId"]
                        })
                    run_async_in_thread(notify())

            except Exception as e:
                print(f"[MOVE] Lỗi xử lý lệnh move: {e}")
                import traceback
                traceback.print_exc()

        # === XỬ LÝ INSTANT ACTIONS ===
        elif message_kind == "instantActions" and agv_id:
            print(f"[ACTION] AGV {agv_id} nhận instantActions:")
            print(json.dumps(payload, indent=2, ensure_ascii=False))

            app = get_app()
            ws_func = app.state.send_websocket_update
            if ws_func:
                async def send_action_ws():
                    await ws_func({
                        "type": "instant_action",
                        "agv_id": agv_id,
                        "actions": payload
                    })
                run_async_in_thread(send_action_ws())

        else:
            print(f"[MQTT] Topic chưa xử lý: {msg.topic}")

    except Exception as e:
        print(f"[MQTT] LỖI XỬ LÝ TIN NHẮN: {e}")
        import traceback
        traceback.print_exc()


# ==========================
# MQTT Setup
# ==========================
client = mqtt.Client(client_id=f"server_{uuid.uuid4().hex[:8]}", clean_session=True)
client.on_connect = on_connect
client.on_message = on_message


def _publish_topic_candidates(agv_id: str, suffix: str) -> list[str]:
    agv_info = agv_manager.get_agv(agv_id, {}) or {}
    manufacturer = str(agv_info.get("manufacturer") or "tot")
    return [
        f"vda5050/agv/{agv_id}/{suffix}",
        f"{UAGV_INTERFACE_NAME}/{UAGV_MAJOR_VERSION}/{manufacturer}/{agv_id}/{suffix}",
    ]


def start_mqtt():
    try:
        client.connect(BROKER, PORT, keepalive=60)
        client.loop_start()
        print(f"[MQTT] Đã kết nối và lắng nghe trên {BROKER}:{PORT}")
    except Exception as e:
        print(f"[MQTT] LỖI KẾT NỘI BROKER: {e}")


# ==========================
# ORDER & ACTION Sending
# ==========================
def send_order(agv_id: str, order: dict):
    payload_str = json.dumps(order, ensure_ascii=False)
    result_codes = []
    for topic in _publish_topic_candidates(agv_id, "order"):
        result = client.publish(topic, payload_str, qos=1)
        result_codes.append(f"{topic} rc={result.rc}")
    print(f"[ORDER OUT] {agv_id} | orderId={order.get('orderId')} | {' | '.join(result_codes)}")


def send_instant_action(agv_id: str, action_type: str):
    if action_type not in ["PAUSE", "RESUME"]:
        print(f"[MQTT] Hành động không hợp lệ: {action_type}")
        return

    action_msg = {
        "headerId": int(time.time()),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "version": "1.1",
        "manufacturer": "AGVCorp",
        "serialNumber": agv_id,
        "actions": [{
            "actionId": str(uuid.uuid4()),
            "actionType": action_type,
            "blockingType": "HARD" if action_type == "PAUSE" else "SOFT"
        }]
    }
    payload = json.dumps(action_msg, ensure_ascii=False)
    for topic in _publish_topic_candidates(agv_id, "instantActions"):
        client.publish(topic, payload, qos=0)
    print(f"[MQTT] ĐÃ GỬI instantAction → {agv_id}: {action_type}")
