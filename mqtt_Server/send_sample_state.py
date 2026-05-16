from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

import paho.mqtt.client as mqtt


SERVER_BASE_URL = "http://127.0.0.1:8000"
MQTT_BROKER = os.getenv("MQTT_BROKER", "192.168.1.25").strip()
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))

STAGING_NODE_POSES: dict[str, tuple[float, float, float]] = {
    "2":  (10.00, 2.00, 0.0),
    "3":  (18.00, 2.00, 0.0),
    "17": (24.01, 8.33, 0.4),
    "19": (24.09, 12.12, 0.3),
    "21": (30.02, 9.99, 1.6),
}


SCENARIOS: dict[str, list[dict[str, object]]] = {
    "corridor_wait": [
        # Dua AGV03 vao N21 truoc, sau do AGV01 di qua N21 de test WAIT.
        {
            "agv_id": "AGV03",
            "destination": "21",
            #"path": ["3", "18", "17", "21"],
            "wait_before": 0.0,
            "note": "AGV03 chiem N21",
        },
        {
            "agv_id": "AGV01",
            "destination": "20",
            #"path": ["1", "2", "3", "18", "17", "21", "20"],
            "wait_before": 2.0,
            "note": "AGV01 buoc di qua N21 de gap AGV03",
        },
    ],
    "triple_conflict": [
        # AGV03 giu N21. AGV01 co y di qua N21 den N20.
        # Neu AGV01 bi reroute sang nhanh N23 thi AGV02 da chiem N23 san.
        {
            "agv_id": "AGV03",
            "destination": "21",
            #"path": ["3", "18", "17", "21"],
            "wait_before": 0.0,
            "note": "AGV03 chiem N21",
        },
        {
            "agv_id": "AGV01",
            "destination": "20",
            #"path": ["1", "2", "3", "18", "17", "21", "20"],
            "wait_before": 1.5,
            "note": "AGV01 di vao hanh lang N21 de toi N20",
        },
        {
            "agv_id": "AGV02",
            "destination": "23",
            #"path": ["2", "3", "18", "22", "23"],
            "wait_before": 3.0,
            "note": "AGV02 chiem nhanh N23 de chan reroute cua AGV01",
        },
    ],
    "head_on_20_23": [
        # Dua AGV02 len N23 truoc, sau do AGV01 huong toi N20 de ep planner nghien cuu nhanh 20-23.
        {
            "agv_id": "AGV02",
            "destination": "23",
            #"path": ["2", "3", "18", "22", "23"],
            "wait_before": 0.0,
            "note": "AGV02 len N23 truoc",
        },
        {
            "agv_id": "AGV01",
            "destination": "20",
            #"path": ["1", "2", "3", "18", "22", "23", "20"],
            "wait_before": 2.0,
            "note": "AGV01 di qua nhanh 23 de toi N20",
        },
    ],
    "slowdown_merge": [
        # Hai AGV di cung hanh lang 3 -> 18 -> 22 voi do lech nho.
        # Muc tieu la de State Management khuyen nghi SLOW_DOWN thay vi hard WAIT.
        {
            "agv_id": "AGV03",
            "destination": "22",
            #"path": ["3", "18", "22"],
            "wait_before": 0.0,
            "note": "AGV03 vao corridor 3-18-22 truoc",
        },
        {
            "agv_id": "AGV02",
            "destination": "23",
            #"path": ["2", "3", "18", "22", "23"],
            "wait_before": 0.8,
            "note": "AGV02 bam theo cung hanh lang; mong doi predictor ra SLOW_DOWN",
        },
    ],
    "paused_blocker_midroute": [
        {
            "type": "order",
            "agv_id": "AGV03",
            "destination": "21",
            "wait_before": 0.0,
            "note": "AGV03 vao route giao cat truoc",
        },
        {
            "type": "order",
            "agv_id": "AGV01",
            "destination": "20",
            "wait_before": 1.5,
            "note": "AGV01 di vao nhanh chung",
        },
        {
            "type": "order",
            "agv_id": "AGV02",
            "destination": "23",
            "wait_before": 3.0,
            "note": "AGV02 di vao node tranh chap",
        },
        {
            "type": "state",
            "agv_id": "AGV03",
            "wait_before": 8.0,
            "paused": True,
            "duration_sec": 6.0,
            "repeat_interval_sec": 0.75,
            "note": "Gia lap AGV03 dung giua edge trong vai giay",
        },
    ],
    "error_blocker_midroute": [
        {
            "type": "order",
            "agv_id": "AGV03",
            "destination": "21",
            "wait_before": 0.0,
            "note": "AGV03 vao route giao cat truoc",
        },
        {
            "type": "order",
            "agv_id": "AGV01",
            "destination": "20",
            "wait_before": 1.5,
            "note": "AGV01 di vao nhanh chung",
        },
        {
            "type": "order",
            "agv_id": "AGV02",
            "destination": "23",
            "wait_before": 3.0,
            "note": "AGV02 di vao node tranh chap",
        },
        {
            "type": "state",
            "agv_id": "AGV03",
            "paused": True,
            "error_description": "Injected simulator fault mid-route",
            "wait_before": 8.0,
            "note": "Gia lap AGV03 loi giua duong",
        },
    ],
    "same_direction_stalled_blocker": [
        # AGV03 enters the 3-18-22 corridor first and is then held near N22.
        # AGV02 is forced onto the same corridor right behind it by explicit path.
        # Then AGV03 is held in paused state long enough to make AGV02
        # escalate from WAIT_HOLD into reroute/escape instead of waiting forever.
        {
            "type": "order",
            "agv_id": "AGV03",
            "destination": "22",
            "path": ["3", "18", "22"],
            "wait_before": 0.0,
            "note": "AGV03 enters the shared corridor first and stops at N22",
        },
        {
            "type": "order",
            "agv_id": "AGV02",
            "destination": "23",
            "path": ["3", "18", "22", "23"],
            "wait_before": 1.0,
            "note": "AGV02 is forced to follow the same corridor behind AGV03",
        },
        {
            "type": "state",
            "agv_id": "AGV03",
            "wait_before": 6.0,
            "paused": True,
            "duration_sec": 8.0,
            "repeat_interval_sec": 0.75,
            "note": "Hold AGV03 in the corridor to create a same-direction local jam",
        },
    ],
    "head_on_multi_edge_corridor": [
        # Stage AGV01 onto the right side first, then launch AGV03 and AGV01
        # into the same multi-edge corridor in opposite directions:
        #   AGV03: 3 -> 4 -> 17 -> 19
        #   AGV01: 19 -> 17 -> 4 -> 3
        # Expected result: head-on detection should trigger on the whole corridor,
        # not just a single physical edge, and one AGV should yield/reroute.
        {
            "type": "order",
            "agv_id": "AGV01",
            "destination": "19",
            "path": ["1", "6", "5", "4", "17", "19"],
            "wait_before": 0.0,
            "phase": "PHASE 1",
            "note": "Stage AGV01 onto N19 before the head-on test",
        },
        {
            "type": "await_node",
            "agv_id": "AGV01",
            "node_id": "19",
            "wait_before": 0.2,
            "timeout_sec": 60.0,
            "phase": "PHASE 1",
            "note": "Wait until AGV01 reaches N19",
        },
        {
            "type": "teleport",
            "agv_id": "AGV03",
            "node_id": "3",
            "wait_before": 0.3,
            "duration_sec": 1.5,
            "repeat_interval_sec": 0.5,
            "phase": "PHASE 2",
            "note": "Reset AGV03 to clean state at N3 before head-on test",
        },
        {
            "type": "order",
            "agv_id": "AGV03",
            "destination": "19",
            "path": ["3", "4", "17", "19"],
            "wait_before": 0.6,
            "phase": "PHASE 2",
            "note": "AGV03 enters the corridor from the left",
        },
        {
            "type": "order",
            "agv_id": "AGV01",
            "destination": "3",
            "path": ["19", "17", "4", "3"],
            "wait_before": 0.8,
            "phase": "PHASE 2",
            "note": "AGV01 enters the same corridor from the right",
        },
    ],
    "wait_cycle_triangle": [
        # Order-only deadlock-cycle test.
        # Stage in an order that has already proven feasible on this map:
        #   AGV03 -> N21
        #   AGV01 -> N20
        #   AGV02 -> N23
        #
        # Then request a cyclic swap:
        #   AGV01: 20 -> 23
        #   AGV02: 23 -> 21
        #   AGV03: 21 -> 20
        #
        # Expected wait graph:
        #   AGV01 waits AGV02, AGV02 waits AGV03, AGV03 waits AGV01.
        {
            "type": "order",
            "agv_id": "AGV03",
            "destination": "21",
            "wait_before": 0.0,
            "phase": "PHASE 1",
            "note": "Stage AGV03 onto N21 first",
        },
        {
            "type": "await_node",
            "agv_id": "AGV03",
            "node_id": "21",
            "wait_before": 0.2,
            "timeout_sec": 60.0,
            "phase": "PHASE 1",
            "note": "Wait until AGV03 reaches N21",
        },
        {
            "type": "order",
            "agv_id": "AGV01",
            "destination": "20",
            "wait_before": 0.4,
            "phase": "PHASE 1",
            "note": "Stage AGV01 onto N20 second",
        },
        {
            "type": "await_node",
            "agv_id": "AGV01",
            "node_id": "20",
            "wait_before": 0.6,
            "timeout_sec": 60.0,
            "phase": "PHASE 1",
            "note": "Wait until AGV01 reaches N20",
        },
        {
            "type": "order",
            "agv_id": "AGV02",
            "destination": "23",
            "wait_before": 0.8,
            "phase": "PHASE 1",
            "note": "Stage AGV02 onto N23 last",
        },
        {
            "type": "await_node",
            "agv_id": "AGV02",
            "node_id": "23",
            "wait_before": 1.0,
            "timeout_sec": 60.0,
            "phase": "PHASE 1",
            "note": "Wait until AGV02 reaches N23",
        },
        {
            "type": "order",
            "agv_id": "AGV01",
            "destination": "23",
            "wait_before": 1.3,
            "phase": "PHASE 2",
            "note": "AGV01 now wants node held by AGV02",
        },
        {
            "type": "order",
            "agv_id": "AGV02",
            "destination": "21",
            "wait_before": 1.4,
            "phase": "PHASE 2",
            "note": "AGV02 now wants node held by AGV03",
        },
        {
            "type": "order",
            "agv_id": "AGV03",
            "destination": "20",
            "wait_before": 1.5,
            "phase": "PHASE 2",
            "note": "AGV03 now wants node held by AGV01",
        },
    ],
}


def _http_json(method: str, path: str, payload: dict[str, object] | None = None) -> dict[str, object]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{SERVER_BASE_URL}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def post_move(command: dict[str, object]) -> dict[str, object]:
    return _http_json("POST", "/order", command)


def post_action(command: dict[str, object]) -> dict[str, object]:
    return _http_json("POST", "/action", command)


def get_agv_state(agv_id: str) -> dict[str, object]:
    return _http_json("GET", f"/agv/{agv_id}")


def _normalize_node_token(node_id: object) -> str:
    token = str(node_id or "").strip()
    if not token:
        return ""
    upper = token.upper()
    if upper.startswith("N") and len(token) > 1:
        return token[1:].strip()
    return token
 

def publish_state_override(
    agv_id: str,
    *,
    paused: bool = False,
    error_description: str | None = None,
    force_zero_velocity: bool = False,
    base_state: dict[str, object] | None = None,
    sim_pause_hold: bool = False,
    last_node_id: str | None = None,
    x: float | None = None,
    y: float | None = None,
    theta: float | None = None,
    order_id: str | None = None,
    order_update_id: int | None = None,
    node_states: list[object] | None = None,
    edge_states: list[object] | None = None,
    order_status: str | None = None,
) -> None:
    current = dict(base_state or get_agv_state(agv_id))
    map_current = str(current.get("map_id") or current.get("mapCurrent") or "map_demo")
    x = float(current.get("x") if x is None else x or 0.0)
    y = float(current.get("y") if y is None else y or 0.0)
    theta = float(current.get("theta") if theta is None else theta or 0.0)
    battery_charge = float((current.get("batteryState") or {}).get("batteryCharge") or 95.0)
    order_id = str(current.get("orderId") if order_id is None else order_id or "")
    order_update_id = int(current.get("orderUpdateId") if order_update_id is None else order_update_id or 0)
    last_node_id = str(current.get("lastNodeId") if last_node_id is None else last_node_id or "")
    manufacturer = str(current.get("manufacturer") or "tot")
    serial_number = str(current.get("serialNumber") or agv_id)

    error_payload = []
    if error_description:
        error_payload.append(
            {
                "errorLevel": "ERROR",
                "errorDescription": error_description,
                "errorReferences": [],
            }
        )

    velocity_payload = current.get("velocity") or {"vx": 0.0, "vy": 0.0, "omega": 0.0}
    if paused or force_zero_velocity:
        velocity_payload = {"vx": 0.0, "vy": 0.0, "omega": 0.0}

    payload = {
        "headerId": int(time.time() * 1000),
        "timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "version": "2.0",
        "manufacturer": manufacturer,
        "serialNumber": serial_number,
        "mapCurrent": map_current,
        "orderId": order_id,
        "orderUpdateId": order_update_id,
        "lastNodeId": last_node_id,
        "nodeStates": list(current.get("nodeStates") or []) if node_states is None else node_states,
        "edgeStates": list(current.get("edgeStates") or []) if edge_states is None else edge_states,
        "agvPosition": {
            "x": x,
            "y": y,
            "theta": theta,
            "mapId": map_current,
        },
        "velocity": velocity_payload,
        "batteryState": current.get("batteryState") or {"batteryCharge": battery_charge},
        "load": current.get("load") or {},
        "paused": paused,
        "operationMode": current.get("operationMode") or "AUTOMATIC",
        **({"orderStatus": order_status} if order_status else {}),
        "actionState": {
            **(current.get("actionState") or {}),
            **({"simPauseHold": True} if sim_pause_hold else {}),
        },
        "error": error_payload,
    }

    client = mqtt.Client(client_id=f"sample_state_{agv_id}_{int(time.time())}")
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_start()
    try:
        payload_text = json.dumps(payload, ensure_ascii=False)
        topics = [
            f"vda5050/agv/{agv_id}/state",
            f"uagv/v3/tot/{agv_id}/state",
        ]
        publish_infos = [client.publish(topic, payload_text, qos=1) for topic in topics]
        for info in publish_infos:
            info.wait_for_publish(timeout=2.0)
        time.sleep(0.2)
    finally:
        client.loop_stop()
        client.disconnect()


def publish_state_override_for_duration(
    agv_id: str,
    *,
    paused: bool = False,
    error_description: str | None = None,
    force_zero_velocity: bool = False,
    duration_sec: float = 0.0,
    repeat_interval_sec: float = 1.0,
    sim_pause_hold: bool = False,
    last_node_id: str | None = None,
    x: float | None = None,
    y: float | None = None,
    theta: float | None = None,
    order_id: str | None = None,
    order_update_id: int | None = None,
    node_states: list[object] | None = None,
    edge_states: list[object] | None = None,
    order_status: str | None = None,
) -> None:
    duration_sec = max(0.0, float(duration_sec))
    repeat_interval_sec = max(0.2, float(repeat_interval_sec))
    frozen_state = get_agv_state(agv_id)

    if duration_sec <= 0.0:
        publish_state_override(
            agv_id,
            paused=paused,
            error_description=error_description,
            force_zero_velocity=force_zero_velocity,
            base_state=frozen_state,
            sim_pause_hold=sim_pause_hold,
            last_node_id=last_node_id,
            x=x,
            y=y,
            theta=theta,
            order_id=order_id,
            order_update_id=order_update_id,
            node_states=node_states,
            edge_states=edge_states,
            order_status=order_status,
        )
        return

    deadline = time.monotonic() + duration_sec
    while True:
        publish_state_override(
            agv_id,
            paused=paused,
            error_description=error_description,
            force_zero_velocity=force_zero_velocity,
            base_state=frozen_state,
            sim_pause_hold=sim_pause_hold,
            last_node_id=last_node_id,
            x=x,
            y=y,
            theta=theta,
            order_id=order_id,
            order_update_id=order_update_id,
            node_states=node_states,
            edge_states=edge_states,
            order_status=order_status,
        )
        if time.monotonic() >= deadline:
            break
        time.sleep(repeat_interval_sec)


def wait_for_agv_node(
    agv_id: str,
    node_id: str,
    *,
    timeout_sec: float = 30.0,
    poll_interval_sec: float = 0.5,
) -> dict[str, object]:
    deadline = time.monotonic() + max(1.0, float(timeout_sec))
    target_node = _normalize_node_token(node_id)
    poll_interval_sec = max(0.2, float(poll_interval_sec))

    last_state: dict[str, object] | None = None
    while time.monotonic() < deadline:
        try:
            last_state = get_agv_state(agv_id)
        except Exception:
            time.sleep(poll_interval_sec)
            continue
        current_node = _normalize_node_token(last_state.get("lastNodeId"))
        if current_node == target_node:
            return last_state
        time.sleep(poll_interval_sec)

    raise TimeoutError(
        f"AGV {agv_id} did not reach node {target_node} within {timeout_sec:.1f}s "
        f"(lastNodeId={str((last_state or {}).get('lastNodeId') or '').strip()})"
    )


def run_step(step: dict[str, object], index: int, total: int) -> None:
    step_type = str(step.get("type") or "order").strip().lower()
    note = step.get("note") or "-"
    phase = str(step.get("phase") or "").strip()
    phase_prefix = f"[{phase}] " if phase else ""

    if step_type == "order":
        payload = {
            "agv_id": str(step["agv_id"]),
            "destination": str(step["destination"]),
        }
        if step.get("map_id"):
            payload["map_id"] = step["map_id"]
        if step.get("path"):
            payload["path"] = [str(node_id) for node_id in list(step["path"])]
        response = post_move(payload)
        print(
            f"{phase_prefix}[{index}/{total}] ORDER {payload['agv_id']} -> {payload['destination']} "
            f"| orderId={response.get('orderId')} | path={response.get('path')} | note={note}"
        )
        return

    if step_type == "action":
        payload = {
            "agv_id": str(step["agv_id"]),
            "action_type": str(step["action_type"]),
        }
        response = post_action(payload)
        if bool(step.get("sync_state")):
            publish_state_override_for_duration(
                payload["agv_id"],
                paused=str(payload["action_type"]).upper() == "PAUSE",
                force_zero_velocity=True,
                duration_sec=float(step.get("duration_sec", 0.0) or 0.0),
                repeat_interval_sec=float(step.get("repeat_interval_sec", 1.0) or 1.0),
                sim_pause_hold=bool(step.get("sim_pause_hold", False)),
            )
        print(
            f"{phase_prefix}[{index}/{total}] ACTION {payload['action_type']} -> {payload['agv_id']} "
            f"| status={response.get('status')} | note={note}"
        )
        return

    if step_type == "state":
        agv_id = str(step["agv_id"])
        paused = bool(step.get("paused", False))
        error_description = str(step.get("error_description") or "").strip() or None
        publish_state_override_for_duration(
            agv_id,
            paused=paused,
            error_description=error_description,
            force_zero_velocity=paused or bool(error_description),
            duration_sec=float(step.get("duration_sec", 0.0) or 0.0),
            repeat_interval_sec=float(step.get("repeat_interval_sec", 1.0) or 1.0),
            sim_pause_hold=paused,
        )
        print(
            f"{phase_prefix}[{index}/{total}] STATE {agv_id} "
            f"| paused={paused} | error={error_description or 'NONE'} | note={note}"
        )
        return

    if step_type == "teleport":
        agv_id = str(step["agv_id"])
        node_id = _normalize_node_token(step["node_id"])
        pose = STAGING_NODE_POSES.get(node_id)
        if pose is None:
            raise ValueError(f"Missing staging pose for node {node_id}")
        publish_state_override_for_duration(
            agv_id,
            paused=False,
            force_zero_velocity=True,
            duration_sec=float(step.get("duration_sec", 2.0) or 2.0),
            repeat_interval_sec=float(step.get("repeat_interval_sec", 0.5) or 0.5),
            last_node_id=f"N{node_id}",
            x=float(pose[0]),
            y=float(pose[1]),
            theta=float(pose[2]),
            order_id="",
            order_update_id=0,
            node_states=[],
            edge_states=[],
            order_status="FINISHED",
        )
        print(
            f"{phase_prefix}[{index}/{total}] TELEPORT {agv_id} -> N{node_id} "
            f"| pose=({pose[0]:.2f}, {pose[1]:.2f}, {pose[2]:.1f}) | note={note}"
        )
        return

    if step_type == "await_node":
        agv_id = str(step["agv_id"])
        node_id = str(step["node_id"])
        state = wait_for_agv_node(
            agv_id,
            node_id,
            timeout_sec=float(step.get("timeout_sec", 30.0) or 30.0),
            poll_interval_sec=float(step.get("poll_interval_sec", 0.5) or 0.5),
        )
        print(
            f"{phase_prefix}[{index}/{total}] AWAIT {agv_id} @ {node_id} "
            f"| orderId={state.get('orderId')} | note={note}"
        )
        return

    raise ValueError(f"Unsupported step type: {step_type}")


def run_scenario(scenario_name: str) -> None:
    moves = SCENARIOS[scenario_name]
    started_at = time.monotonic()
    print(f"Running scenario: {scenario_name}")
    announced_phases: set[str] = set()
    for index, move in enumerate(moves, start=1):
        wait_before = float(move.get("wait_before", 0.0))
        elapsed = time.monotonic() - started_at
        sleep_for = max(0.0, wait_before - elapsed)
        if sleep_for > 0.0:
            time.sleep(sleep_for)

        try:
            phase = str(move.get("phase") or "").strip()
            if phase and phase not in announced_phases:
                announced_phases.add(phase)
                print(f"\n=== {phase}: {scenario_name} ===")
            run_step(move, index, len(moves))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            print(f"[{index}/{len(moves)}] HTTP {exc.code}: {detail}")
            raise
        except Exception as exc:
            print(f"[{index}/{len(moves)}] Failed: {exc}")
            raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send controlled AGV move scenarios to /order")
    parser.add_argument(
        "--scenario",
        default="triple_conflict",
        choices=sorted(SCENARIOS.keys()),
        help="Scenario to execute",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_scenario(args.scenario)


if __name__ == "__main__":
    main()
