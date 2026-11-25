"""
protocol.py — HỢP ĐỒNG DỮ LIỆU MQTT (xem docs/04-giao-thuc-mqtt.md).

Dùng chung cho cả coordinator (FMS) và bộ mô phỏng thiết bị: topic, header VDA5050,
build/parse instantActions, state, connection.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union

VERSION = "2.0.0"
ROOT = "uelev"

# ---- actionType ----
ACT_CALL_FLOOR = "callFloor"
ACT_HOLD_DOOR = "holdDoor"
ACT_RELEASE_DOOR = "releaseDoor"
ACT_FAST_CLOSE = "fastClose"
ACT_DEPART = "depart"            # Master tự: nhả giữ cửa -> đóng nhanh -> gọi tầng -> TỰ giữ cửa khi tới (chạy được khi mất mạng)
ACT_RESET = "reset"
ACT_HALL_CALL = "hallCall"
ACT_RELEASE_HALL = "releaseHall"

MASTER_ACTIONS = (ACT_CALL_FLOOR, ACT_HOLD_DOOR, ACT_RELEASE_DOOR, ACT_FAST_CLOSE, ACT_DEPART, ACT_RESET)
CALLER_ACTIONS = (ACT_HALL_CALL, ACT_RELEASE_HALL, ACT_RESET)

# ---- actionStatus (VDA5050) ----
ST_WAITING = "WAITING"
ST_RUNNING = "RUNNING"
ST_FINISHED = "FINISHED"
ST_FAILED = "FAILED"

# ---- connectionState ----
CONN_ONLINE = "ONLINE"
CONN_BROKEN = "CONNECTIONBROKEN"
CONN_OFFLINE = "OFFLINE"

KIND_MASTER = "master"
KIND_CALLER = "caller"

ACTION_HISTORY = 8   # thiết bị giữ 8 action gần nhất trong actionStates


class ProtocolError(ValueError):
    pass


# ------------------------------------------------------------------ topic
def device_base(factory: str, elevator_id: str, device_id: str) -> str:
    return f"{ROOT}/v2/{factory}/{elevator_id}/{device_id}"


def topic_state(factory: str, elevator_id: str, device_id: str) -> str:
    return device_base(factory, elevator_id, device_id) + "/state"


def topic_actions(factory: str, elevator_id: str, device_id: str) -> str:
    return device_base(factory, elevator_id, device_id) + "/instantActions"


def topic_connection(factory: str, elevator_id: str, device_id: str) -> str:
    return device_base(factory, elevator_id, device_id) + "/connection"


def state_filter(factory: str, elevator_id: str) -> str:
    return f"{ROOT}/v2/{factory}/{elevator_id}/+/state"


def connection_filter(factory: str, elevator_id: str) -> str:
    return f"{ROOT}/v2/{factory}/{elevator_id}/+/connection"


def manager_connection_topic(factory: str) -> str:
    """Topic presence của FMS — ĐÃ CÓ SẴN (docs/manager-presence.md)."""
    return f"uagv/v2/{factory}/manager/connection"


def serial_number(elevator_id: str, device_id: str) -> str:
    return f"{elevator_id}-{device_id}"


def parse_topic(topic: str) -> Optional[Tuple[str, str, str, str]]:
    """uelev/v2/{factory}/{elev}/{device}/{kind} -> (factory, elev, device, kind) | None."""
    p = topic.split("/")
    if len(p) != 6 or p[0] != ROOT or p[1] != "v2":
        return None
    return p[2], p[3], p[4], p[5]


# ------------------------------------------------------------------ header
def iso_ts(epoch: float) -> str:
    ms = int(round((epoch - int(epoch)) * 1000))
    if ms == 1000:
        epoch, ms = epoch + 1, 0
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(epoch)) + f".{ms:03d}Z"


class HeaderCounter:
    """headerId tăng dần theo từng khóa (thường là topic)."""

    def __init__(self) -> None:
        self._n: Dict[str, int] = {}

    def next(self, key: str) -> int:
        n = self._n.get(key, -1) + 1
        if n > 0xFFFFFFFF:
            n = 0
        self._n[key] = n
        return n


def build_header(header_id: int, wall: float, factory: str, elevator_id: str, device_id: str) -> Dict[str, Any]:
    return {
        "headerId": header_id,
        "timestamp": iso_ts(wall),
        "version": VERSION,
        "manufacturer": factory,
        "serialNumber": serial_number(elevator_id, device_id),
    }


def new_action_id() -> str:
    return uuid.uuid4().hex[:12]


def action_dict(action_type: str, action_id: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "actionType": action_type,
        "actionId": action_id,
        "blockingType": "NONE",
        "actionParameters": [{"key": k, "value": v} for k, v in (params or {}).items()],
    }


def dumps(obj: Any) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def build_instant_actions(header: Dict[str, Any], actions: List[Dict[str, Any]]) -> str:
    return dumps({**header, "actions": actions})


def build_connection(header: Dict[str, Any], state: str) -> str:
    return dumps({**header, "connectionState": state})


# ------------------------------------------------------------------ model
@dataclass
class ActionState:
    action_id: str
    action_type: str
    status: str
    result: str = ""


@dataclass
class MasterState:
    floor: Optional[int] = None
    door_open: Optional[bool] = None
    door_sensor_valid: bool = True
    door_hold: bool = False
    hold_ttl_s: int = 0
    fast_close: bool = False
    call_pulse: Optional[int] = None
    door_hold_auto: bool = False            # True = Master tự giữ cửa khi tới tầng (depart)
    depart_phase: Optional[str] = None      # closing | calling | transit | None (Master không đang canh depart)
    depart_to: Optional[int] = None
    sensors: Dict[str, int] = field(default_factory=dict)
    errors: List[Dict[str, Any]] = field(default_factory=list)
    action_states: List[ActionState] = field(default_factory=list)
    timestamp: str = ""


@dataclass
class CallerState:
    floor: int = 0
    directions: Tuple[str, ...] = ()
    hall_active: bool = False
    hall_direction: Optional[str] = None
    hall_ttl_s: int = 0
    hall_relay: bool = False
    errors: List[Dict[str, Any]] = field(default_factory=list)
    action_states: List[ActionState] = field(default_factory=list)
    timestamp: str = ""


DeviceState = Union[MasterState, CallerState]


def _load(payload: Union[str, bytes, Dict[str, Any]]) -> Dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    try:
        obj = json.loads(payload)
    except (ValueError, TypeError) as e:
        raise ProtocolError(f"JSON hỏng: {e}") from e
    if not isinstance(obj, dict):
        raise ProtocolError("payload phải là object JSON")
    return obj


def _action_states(obj: Dict[str, Any]) -> List[ActionState]:
    out = []
    for a in obj.get("actionStates") or []:
        if not isinstance(a, dict) or "actionId" not in a:
            raise ProtocolError("actionStates có phần tử sai định dạng")
        out.append(ActionState(
            action_id=str(a["actionId"]),
            action_type=str(a.get("actionType", "")),
            status=str(a.get("actionStatus", "")),
            result=str(a.get("resultDescription", "")),
        ))
    return out


def parse_state(kind: str, payload: Union[str, bytes, Dict[str, Any]]) -> DeviceState:
    obj = _load(payload)
    if kind == KIND_MASTER:
        e = obj.get("elevator")
        if not isinstance(e, dict):
            raise ProtocolError("state master thiếu object 'elevator'")
        floor = e.get("floor")
        if floor is not None and not isinstance(floor, int):
            raise ProtocolError("elevator.floor phải là int hoặc null")
        door_open = e.get("doorOpen")
        dp = e.get("depart")
        return MasterState(
            floor=floor,
            door_open=None if door_open is None else bool(door_open),
            door_sensor_valid=bool(e.get("doorSensorValid", True)),
            door_hold=bool(e.get("doorHold", False)),
            hold_ttl_s=int(e.get("holdTtlS", 0) or 0),
            fast_close=bool(e.get("fastClose", False)),
            call_pulse=e.get("callPulse"),
            door_hold_auto=bool(e.get("doorHoldAuto", False)),
            depart_phase=str(dp.get("phase")) if isinstance(dp, dict) else None,
            depart_to=dp.get("toFloor") if isinstance(dp, dict) else None,
            sensors=dict(e.get("sensors") or {}),
            errors=list(obj.get("errors") or []),
            action_states=_action_states(obj),
            timestamp=str(obj.get("timestamp", "")),
        )
    if kind == KIND_CALLER:
        c = obj.get("caller")
        if not isinstance(c, dict):
            raise ProtocolError("state caller thiếu object 'caller'")
        h = c.get("hall") or {}
        return CallerState(
            floor=int(c.get("floor", 0)),
            directions=tuple(c.get("directions") or ()),
            hall_active=bool(h.get("active", False)),
            hall_direction=h.get("direction"),
            hall_ttl_s=int(h.get("ttlS", 0) or 0),
            hall_relay=bool(h.get("relay", False)),
            errors=list(obj.get("errors") or []),
            action_states=_action_states(obj),
            timestamp=str(obj.get("timestamp", "")),
        )
    raise ProtocolError(f"kind không hợp lệ: {kind}")


def parse_connection(payload: Union[str, bytes, Dict[str, Any]]) -> str:
    obj = _load(payload)
    return str(obj.get("connectionState", CONN_OFFLINE))


def parse_actions(payload: Union[str, bytes, Dict[str, Any]]) -> List[Tuple[str, str, Dict[str, Any]]]:
    """instantActions -> [(actionType, actionId, params)]. Dùng phía thiết bị/sim."""
    obj = _load(payload)
    acts = obj.get("actions")
    if not isinstance(acts, list):
        raise ProtocolError("instantActions thiếu 'actions'")
    out = []
    for a in acts:
        if not isinstance(a, dict) or "actionType" not in a or "actionId" not in a:
            raise ProtocolError("action thiếu actionType/actionId")
        params = {p["key"]: p.get("value") for p in (a.get("actionParameters") or []) if "key" in p}
        out.append((str(a["actionType"]), str(a["actionId"]), params))
    return out


# ------------------------------------------------------------------ build state (phía thiết bị)
def _action_states_json(states: List[ActionState]) -> List[Dict[str, Any]]:
    return [{"actionId": s.action_id, "actionType": s.action_type,
             "actionStatus": s.status, "resultDescription": s.result} for s in states]


def build_master_state(header: Dict[str, Any], st: MasterState, diag: Optional[Dict[str, Any]] = None) -> str:
    obj = {
        **header,
        "operatingMode": "AUTOMATIC",
        "actionStates": _action_states_json(st.action_states),
        "errors": st.errors,
        "elevator": {
            "floor": st.floor,
            "doorOpen": st.door_open,
            "doorSensorValid": st.door_sensor_valid,
            "doorHold": st.door_hold,
            "holdTtlS": st.hold_ttl_s,
            "fastClose": st.fast_close,
            "callPulse": st.call_pulse,
            "doorHoldAuto": st.door_hold_auto,
            "depart": ({"toFloor": st.depart_to, "phase": st.depart_phase} if st.depart_phase else None),
            "sensors": st.sensors,
        },
    }
    if diag:
        obj["diag"] = diag
    return dumps(obj)


def build_caller_state(header: Dict[str, Any], st: CallerState, diag: Optional[Dict[str, Any]] = None) -> str:
    obj = {
        **header,
        "operatingMode": "AUTOMATIC",
        "actionStates": _action_states_json(st.action_states),
        "errors": st.errors,
        "caller": {
            "floor": st.floor,
            "directions": list(st.directions),
            "hall": {
                "active": st.hall_active,
                "direction": st.hall_direction,
                "ttlS": st.hall_ttl_s,
                "relay": st.hall_relay,
            },
        },
    }
    if diag:
        obj["diag"] = diag
    return dumps(obj)
