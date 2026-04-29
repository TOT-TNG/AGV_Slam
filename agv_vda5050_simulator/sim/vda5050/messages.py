from __future__ import annotations

import itertools
import time
from typing import Any, Dict, List

HEADER_COUNTER = itertools.count(1)


def now_ms() -> int:
    return int(time.time() * 1000)


def base_header(manufacturer: str, serial_number: str) -> Dict[str, Any]:
    return {
        'headerId': next(HEADER_COUNTER),
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'manufacturer': manufacturer,
        'serialNumber': serial_number,
        'version': '3.0.0',
    }


def build_connection(manufacturer: str, serial_number: str, online: bool) -> Dict[str, Any]:
    msg = base_header(manufacturer, serial_number)
    msg.update({'connectionState': 'ONLINE' if online else 'OFFLINE'})
    return msg


def build_visualization(
    manufacturer: str,
    serial_number: str,
    x: float,
    y: float,
    theta: float,
    velocity: float,
    map_id: str,
) -> Dict[str, Any]:
    msg = base_header(manufacturer, serial_number)
    msg.update({
        'agvPosition': {'x': x, 'y': y, 'theta': theta, 'mapId': map_id},
        'velocity': {'vx': velocity, 'vy': 0.0, 'omega': 0.0},
    })
    return msg


def build_factsheet(manufacturer: str, serial_number: str, length: float, width: float) -> Dict[str, Any]:
    msg = base_header(manufacturer, serial_number)
    msg.update({
        'typeSpecification': {
            'agvClass': 'CARRIER',
            'seriesName': 'SIM',
            'physicalParameters': {
                'length': length,
                'width': width,
            },
        },
        'protocolFeatures': {
            'optionalParameters': [],
            'agvActions': [
                {'actionType': 'startPause', 'actionDescription': 'Pause vehicle motion', 'actionScopes': ['INSTANT']},
                {'actionType': 'stopPause', 'actionDescription': 'Resume vehicle motion', 'actionScopes': ['INSTANT']},
                {'actionType': 'cancelOrder', 'actionDescription': 'Cancel active order', 'actionScopes': ['INSTANT']},
                {'actionType': 'factsheetRequest', 'actionDescription': 'Publish factsheet', 'actionScopes': ['INSTANT']},
                {'actionType': 'stateRequest', 'actionDescription': 'Publish state', 'actionScopes': ['INSTANT']},
                {'actionType': 'visualizationRequest', 'actionDescription': 'Publish visualization', 'actionScopes': ['INSTANT']},
                {'actionType': 'clearErrors', 'actionDescription': 'Clear simulated errors', 'actionScopes': ['INSTANT']},
                {'actionType': 'startHibernation', 'actionDescription': 'Enter simulated hibernation', 'actionScopes': ['INSTANT']},
                {'actionType': 'stopHibernation', 'actionDescription': 'Leave simulated hibernation', 'actionScopes': ['INSTANT']},
                {'actionType': 'shutdown', 'actionDescription': 'Shutdown simulated AGV', 'actionScopes': ['INSTANT']},
                {'actionType': 'updateCertificate', 'actionDescription': 'Acknowledge certificate update request', 'actionScopes': ['INSTANT']},
                {'actionType': 'trigger', 'actionDescription': 'Acknowledge trigger request', 'actionScopes': ['INSTANT']},
                {'actionType': 'startCharging', 'actionDescription': 'Start simulated charging', 'actionScopes': ['NODE', 'INSTANT']},
                {'actionType': 'stopCharging', 'actionDescription': 'Stop simulated charging', 'actionScopes': ['NODE', 'INSTANT']},
                {'actionType': 'pick', 'actionDescription': 'Pick simulated load', 'actionScopes': ['NODE', 'INSTANT']},
                {'actionType': 'drop', 'actionDescription': 'Drop simulated load', 'actionScopes': ['NODE', 'INSTANT']},
            ],
        },
    })
    return msg


def build_state(
    *,
    manufacturer: str,
    serial_number: str,
    order_id: str,
    order_update_id: int,
    x: float,
    y: float,
    theta: float,
    speed: float,
    driving: bool,
    paused: bool,
    operating_mode: str,
    battery_charge: float,
    battery_low: bool,
    charging: bool,
    battery_current: float,
    last_node_id: str,
    map_id: str,
    node_states: List[Dict[str, Any]],
    edge_states: List[Dict[str, Any]],
    action_states: List[Dict[str, Any]],
    loads: List[Dict[str, Any]],
    errors: List[Dict[str, Any]],
    info: List[Dict[str, Any]],
    safety_state: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    msg = base_header(manufacturer, serial_number)
    msg.update({
        'orderId': order_id,
        'orderUpdateId': order_update_id,
        'lastNodeId': last_node_id,
        'lastNodeSequenceId': 0,
        'operatingMode': operating_mode,
        'driving': driving,
        'paused': paused,
        'pauseAllowed': True,
        'cancelAllowed': True,
        'newBaseRequest': False,
        'distanceSinceLastNode': 0.0,
        'agvPosition': {
            'x': x,
            'y': y,
            'theta': theta,
            'mapId': map_id,
            'positionInitialized': True,
            'localized': True,
        },
        'velocity': {
            'vx': speed,
            'vy': 0.0,
            'omega': 0.0,
        },
        'batteryState': {
            'batteryCharge': max(0.0, min(100.0, battery_charge)),
            'charging': charging,
            'reach': 100,
            'batteryLow': battery_low,
        },
        'powerSupply': {
            'stateOfCharge': max(0.0, min(100.0, battery_charge)),
            'batteryCurrent': battery_current,
            'charging': charging,
            'reach': 100,
            'batteryLow': battery_low,
        },
        'nodeStates': node_states,
        'edgeStates': edge_states,
        'actionStates': action_states,
        'instantActionStates': action_states,
        'zoneActionStates': [],
        'loads': loads,
        'errors': errors,
        'information': info,
        'safetyState': safety_state or {
            'eStop': 'NONE',
            'activeEmergenceStop': False,
            'fieldViolation': False,
        },
    })
    return msg
