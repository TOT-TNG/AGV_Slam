from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sim.core.faults import FaultManager
from sim.core.human_agent import HumanAgent
from sim.core.models import Pose2D, RouteProgress, VehicleSize, Velocity2D
from sim.core.power import PowerManager
from sim.core.state_machine import AGVMode, AGVRunState
from sim.map.graph import Edge, Graph
from sim.utils.geometry import clamp, distance, distance_point_to_polygon, distance_point_to_oriented_rect, heading_to, normalize_angle, point_in_polygon
from sim.vda5050.messages import build_connection, build_factsheet, build_state, build_visualization
from sim.vda5050.mqtt_client import MQTTSettings, VDAMQTTClient


@dataclass
class AGVAgent:
    manufacturer: str
    agv_id: str
    agv_type: str
    graph: Graph
    mqtt_settings: MQTTSettings
    start_node: str
    max_speed: float
    max_accel: float
    stop_distance: float
    size: VehicleSize
    battery_drain_per_second: float
    color: tuple[int, int, int]
    state_publish_hz: float
    connection_publish_hz: float
    visualization_publish_hz: float
    layer: int = 0

    pose: Pose2D = field(init=False)
    state_pose: Pose2D = field(init=False)
    velocity: Velocity2D = field(default_factory=Velocity2D)
    mode: AGVMode = AGVMode.AUTOMATIC
    run_state: AGVRunState = AGVRunState.IDLE
    last_node_id: str = field(init=False)
    route: RouteProgress = field(default_factory=RouteProgress)
    battery: float = 100.0
    paused: bool = False
    obstacle_active: bool = False
    obstacle_distance: float = field(init=False)
    obstacle_lidar_hit: bool = False
    obstacle_point: tuple[float, float] = field(init=False)
    peer_stop_active: bool = False
    peer_stop_agv_id: str = ''
    peer_stop_distance: float = 0.0
    human_stop_active: bool = False
    human_stop_id: str = ''
    human_stop_distance: float = 0.0
    mqtt_disabled_by_operator: bool = False
    charging: bool = False
    battery_current: float = -5.0
    loads: List[Dict[str, Any]] = field(default_factory=list)
    node_actions_by_node_id: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    executed_node_action_ids: set[str] = field(default_factory=set)
    info_messages: List[Dict[str, Any]] = field(default_factory=list)
    action_states: List[Dict[str, Any]] = field(default_factory=list)
    node_states: List[Dict[str, Any]] = field(default_factory=list)
    edge_states: List[Dict[str, Any]] = field(default_factory=list)
    lidar_banks: List[List[tuple[float, float]]] = field(default_factory=list)
    active_lidar_bank: int = 0

    def __post_init__(self) -> None:
        start = self.graph.get_node(self.start_node)
        self.layer = start.layer
        self.pose = Pose2D(start.x, start.y, 0.0)
        self.state_pose = Pose2D(start.x, start.y, 0.0)
        self.last_node_id = self.start_node
        self.faults = FaultManager()
        self.power = PowerManager()
        self.obstacle_distance = self.stop_distance
        self.obstacle_point = (start.x + self.stop_distance, start.y)
        if not self.lidar_banks:
            self.lidar_banks = [self._default_lidar_polygon()]
        self.update_publish_rates(
            state_publish_hz=self.state_publish_hz,
            connection_publish_hz=self.connection_publish_hz,
            visualization_publish_hz=self.visualization_publish_hz,
        )
        self._state_elapsed = 0.0
        self._connection_elapsed = 0.0
        self._visualization_elapsed = 0.0

        self.mqtt = VDAMQTTClient(
            manufacturer=self.manufacturer,
            agv_id=self.agv_id,
            settings=self.mqtt_settings,
            on_order=self.handle_order,
            on_instant_actions=self.handle_instant_actions,
            on_connected=self._handle_mqtt_connected,
        )
        self.mqtt.connect()
        self.publish_factsheet()

    # ----------------------------- MQTT and VDA layer -----------------------------
    def _handle_mqtt_connected(self) -> None:
        self.publish_factsheet()
        self.publish_connection()
        self.publish_state()

    def publish_factsheet(self) -> None:
        if not self._mqtt_publish_ready():
            return
        msg = build_factsheet(self.manufacturer, self.agv_id, self.size.length, self.size.width)
        msg['typeSpecification']['seriesName'] = self.agv_type
        self.mqtt.publish('factsheet', msg, qos=1, retain=True)

    def publish_connection(self) -> None:
        if not self._mqtt_publish_ready():
            return
        msg = build_connection(self.manufacturer, self.agv_id, online=self.mqtt.connected)
        self.mqtt.publish('connection', msg, qos=1, retain=True)

    def publish_offline_connection(self) -> None:
        if not self.power.power_on or not self.mqtt.connected:
            return
        msg = build_connection(self.manufacturer, self.agv_id, online=False)
        self.mqtt.publish('connection', msg, qos=1, retain=True)

    def publish_visualization(self) -> None:
        if not self._mqtt_publish_ready():
            return
        msg = build_visualization(
            self.manufacturer,
            self.agv_id,
            self.pose.x,
            self.pose.y,
            self.pose.theta,
            self.velocity.linear,
            self.graph.layer_map_name(self.layer),
        )
        self.mqtt.publish('visualization', msg)

    def build_state_message(self) -> dict[str, Any]:
        fatal_stop = self.faults.has_error_level('FATAL') or self.run_state == AGVRunState.FAILED
        safety_stop = self._safety_stop_active()
        state_pose = self._state_report_pose()
        return build_state(
            manufacturer=self.manufacturer,
            serial_number=self.agv_id,
            order_id=self.route.order_id,
            order_update_id=self.route.order_update_id,
            x=state_pose.x,
            y=state_pose.y,
            theta=state_pose.theta,
            speed=self.velocity.linear,
            driving=self.run_state == AGVRunState.MOVING and self.velocity.linear > 0.01,
            paused=self.paused or self._safety_stop_active(),
            operating_mode=self.mode.value,
            battery_charge=self.battery,
            battery_low=self.battery <= 20.0,
            charging=self.charging,
            battery_current=self.battery_current,
            last_node_id=self.last_node_id,
            map_id=self.graph.layer_map_name(self.layer),
            node_states=self.node_states,
            edge_states=self.edge_states,
            action_states=self.action_states,
            loads=list(self.loads),
            errors=list(self.faults.errors),
            info=list(self.info_messages),
            safety_state={
                'eStop': 'AUTOACK' if fatal_stop else 'NONE',
                'activeEmergenceStop': fatal_stop,
                'fieldViolation': safety_stop,
            },
        )

    def _state_report_pose(self) -> Pose2D:
        if self._is_line_agv():
            return self.state_pose
        return self.pose

    def _is_line_agv(self) -> bool:
        return self.agv_type.strip().upper() == 'LINE'

    def publish_state(self) -> None:
        if not self._mqtt_publish_ready():
            return
        self.mqtt.publish('state', self.build_state_message(), qos=0)

    def _mqtt_publish_ready(self) -> bool:
        return (
            self.power.power_on
            and not self.mqtt_disabled_by_operator
            and self.mqtt.enabled
            and self.mqtt.connected
        )

    def update_publish_rates(
        self,
        *,
        state_publish_hz: float,
        connection_publish_hz: float,
        visualization_publish_hz: float,
    ) -> None:
        self.state_publish_hz = self._positive_rate(state_publish_hz)
        self.connection_publish_hz = self._positive_rate(connection_publish_hz)
        self.visualization_publish_hz = self._positive_rate(visualization_publish_hz)
        self._state_interval = 1.0 / self.state_publish_hz
        self._connection_interval = 1.0 / self.connection_publish_hz
        self._visualization_interval = 1.0 / self.visualization_publish_hz

    @staticmethod
    def _positive_rate(value: float, *, fallback: float = 1.0) -> float:
        try:
            rate = float(value)
        except (TypeError, ValueError):
            rate = fallback
        return max(0.05, rate)

    def check_peer_stop_distance(self, peers: List[AGVAgent]) -> None:
        was_active = self.peer_stop_active
        previous_peer_id = self.peer_stop_agv_id
        nearest_id = ''
        nearest_distance = 999999.0
        lidar_polygon = self.active_lidar_polygon_world()
        for peer in peers:
            if peer is self:
                continue
            d = self._distance_peer_to_lidar(peer, lidar_polygon)
            if d >= 999999.0:
                d = distance_point_to_oriented_rect(
                    (self.pose.x, self.pose.y),
                    (peer.pose.x, peer.pose.y),
                    peer.pose.theta,
                    peer.size.length,
                    peer.size.width,
                )
            if d < nearest_distance:
                nearest_distance = d
                nearest_id = peer.agv_id

        if nearest_id and nearest_distance <= 0.0:
            self.peer_stop_active = True
            self.peer_stop_agv_id = nearest_id
            self.peer_stop_distance = nearest_distance
            if self.mode != AGVMode.MANUAL:
                self.velocity = Velocity2D()
                self.run_state = AGVRunState.PAUSED
            self._set_peer_warning(active=True)
            if not was_active or previous_peer_id != nearest_id:
                self.publish_state()
            return

        self.peer_stop_active = False
        self.peer_stop_agv_id = ''
        self.peer_stop_distance = 0.0
        self._set_peer_warning(active=False)
        if was_active:
            self.publish_state()

    def _distance_peer_to_lidar(self, peer: AGVAgent, lidar_polygon: list[tuple[float, float]]) -> float:
        if len(lidar_polygon) < 3:
            return 999999.0
        peer_points = self._peer_body_points(peer)
        if any(point_in_polygon(point, lidar_polygon) for point in peer_points):
            return 0.0
        if any(self._point_in_peer_body(point, peer) for point in lidar_polygon):
            return 0.0
        return min(distance_point_to_polygon(point, lidar_polygon) for point in peer_points)

    @staticmethod
    def _peer_body_points(peer: AGVAgent) -> list[tuple[float, float]]:
        half_l = peer.size.length / 2.0
        half_w = peer.size.width / 2.0
        cos_t = math.cos(peer.pose.theta)
        sin_t = math.sin(peer.pose.theta)
        points = [(peer.pose.x, peer.pose.y)]
        for lx, ly in [(half_l, -half_w), (half_l, half_w), (-half_l, half_w), (-half_l, -half_w)]:
            points.append((peer.pose.x + lx * cos_t - ly * sin_t, peer.pose.y + lx * sin_t + ly * cos_t))
        return points

    @staticmethod
    def _point_in_peer_body(point: tuple[float, float], peer: AGVAgent) -> bool:
        return distance_point_to_oriented_rect(
                point,
                (peer.pose.x, peer.pose.y),
                peer.pose.theta,
                peer.size.length,
                peer.size.width,
            ) <= 0.0

    def check_human_stop_distance(self, humans: List[HumanAgent]) -> None:
        was_active = self.human_stop_active
        previous_human_id = self.human_stop_id
        nearest_id = ''
        nearest_distance = 999999.0
        lidar_polygon = self.active_lidar_polygon_world()
        for human in humans:
            if len(lidar_polygon) >= 3:
                d = max(0.0, distance_point_to_polygon((human.pose.x, human.pose.y), lidar_polygon) - human.radius)
            else:
                d = max(0.0, distance((self.pose.x, self.pose.y), (human.pose.x, human.pose.y)) - human.radius)
            if d < nearest_distance:
                nearest_distance = d
                nearest_id = human.human_id

        if nearest_id and nearest_distance <= 0.0:
            self.human_stop_active = True
            self.human_stop_id = nearest_id
            self.human_stop_distance = nearest_distance
            if self.mode != AGVMode.MANUAL:
                self.velocity = Velocity2D()
                self.run_state = AGVRunState.PAUSED
            self._set_human_warning(active=True)
            if not was_active or previous_human_id != nearest_id:
                self.publish_state()
            return

        self.human_stop_active = False
        self.human_stop_id = ''
        self.human_stop_distance = 0.0
        self._set_human_warning(active=False)
        if was_active:
            self.publish_state()

    # ----------------------------- order and actions -----------------------------
    def handle_order(self, payload: dict[str, Any]) -> None:
        if not self.power.power_on:
            return
        if self.faults.has_error_level('FATAL'):
            return

        nodes = self._extract_order_nodes(payload)
        if len(nodes) < 2:
            self.faults.add('ORDER_INVALID', 'Order must contain at least 2 nodes', 'ERROR')
            return

        computed_path = self._expand_route(nodes)
        if not computed_path:
            self.faults.add('ROUTE_NOT_FOUND', 'No graph route found for requested order', 'ERROR')
            return
        node_actions = self._extract_node_actions(payload)

        self.route = RouteProgress(
            order_id=str(payload.get('orderId', 'order-sim')),
            order_update_id=int(payload.get('orderUpdateId', 0)),
            path_nodes=computed_path[1:],
            current_index=0,
            goal_node_id=computed_path[-1],
        )
        self.node_actions_by_node_id = node_actions
        self.executed_node_action_ids.clear()
        self.node_states = [
            {
                'nodeId': n,
                'sequenceId': idx,
                'released': True,
                **({'actions': node_actions[n]} if n in node_actions else {}),
            }
            for idx, n in enumerate(computed_path)
        ]
        self.edge_states = []
        for idx in range(len(computed_path) - 1):
            edge = self.graph.find_edge(computed_path[idx], computed_path[idx + 1])
            if edge:
                self.edge_states.append({'edgeId': edge.edge_id, 'sequenceId': idx, 'released': True})
        self.action_states = []
        for actions in node_actions.values():
            for action in actions:
                self._set_action_state(
                    str(action.get('actionId', f'node-action-{len(self.action_states)+1}')),
                    str(action.get('actionType', '')),
                    'WAITING',
                    'Waiting for node execution',
                )
        self.info_messages = [{'infoType': 'ORDER_ACCEPTED', 'infoDescription': f'Accepted {self.route.order_id}'}]
        self.paused = False
        self.run_state = AGVRunState.MOVING
        if self.last_node_id in self.node_actions_by_node_id:
            self._execute_node_actions(self.last_node_id)
        self.publish_state()

    def handle_instant_actions(self, payload: dict[str, Any]) -> None:
        actions = payload.get('instantActions', payload.get('actions', []))
        for item in actions:
            raw_action_type = str(item.get('actionType', ''))
            action_type = self._normalize_action_type(raw_action_type)
            action_id = str(item.get('actionId', f'act-{len(self.action_states)+1}'))
            if action_type in {'startpause', 'pause', 'stop'}:
                self.paused = True
                self.run_state = AGVRunState.PAUSED
                self._set_action_state(action_id, raw_action_type, 'FINISHED', 'Paused by instant action')
            elif action_type in {'stoppause', 'resume', 'start'}:
                self.paused = False
                if self.route.active:
                    self.run_state = AGVRunState.MOVING
                else:
                    self.run_state = AGVRunState.IDLE
                self._set_action_state(action_id, raw_action_type, 'FINISHED', 'Resumed by instant action')
            elif action_type in {'cancelorder', 'cancel'}:
                requested_order_id = self._get_action_parameter(item, 'orderId')
                if requested_order_id and self.route.order_id and requested_order_id != self.route.order_id:
                    self._set_action_state(action_id, raw_action_type, 'FAILED', 'cancelOrder orderId does not match active order')
                    self.publish_state()
                    continue
                self.cancel_order()
                self._set_action_state(action_id, raw_action_type, 'FINISHED', 'Order cancelled')
            elif action_type == 'clearerrors':
                self.faults.clear()
                self._set_action_state(action_id, raw_action_type, 'FINISHED', 'Errors cleared')
            elif action_type == 'factsheetrequest':
                self.publish_factsheet()
                self._set_action_state(action_id, raw_action_type, 'FINISHED', 'Factsheet published')
            elif action_type == 'staterequest':
                self._set_action_state(action_id, raw_action_type, 'FINISHED', 'State publish requested')
            elif action_type == 'visualizationrequest':
                self.publish_visualization()
                self._set_action_state(action_id, raw_action_type, 'FINISHED', 'Visualization published')
            elif action_type in {'startcharging', 'startcharge', 'stopcharging', 'stopcharge', 'pick', 'drop'}:
                self._execute_vda_action(item, source='instant')
            elif action_type == 'starthibernation':
                self.velocity = Velocity2D()
                self.mode = AGVMode.INTERVENED
                self.run_state = AGVRunState.PAUSED
                self.info_messages = [{'infoType': 'HIBERNATION', 'infoDescription': 'Simulated hibernation mode active'}]
                self._set_action_state(action_id, raw_action_type, 'FINISHED', 'Hibernation started')
            elif action_type == 'stophibernation':
                self.mode = AGVMode.AUTOMATIC
                if self.route.active and not self.paused:
                    self.run_state = AGVRunState.MOVING
                else:
                    self.run_state = AGVRunState.IDLE
                self.info_messages = [item for item in self.info_messages if item.get('infoType') != 'HIBERNATION']
                self._set_action_state(action_id, raw_action_type, 'FINISHED', 'Hibernation stopped')
            elif action_type == 'shutdown':
                self._set_action_state(action_id, raw_action_type, 'FINISHED', 'Shutdown executed')
                self.publish_state()
                self.power_off()
                continue
            elif action_type == 'updatecertificate':
                self._set_action_state(action_id, raw_action_type, 'FINISHED', 'Certificate update accepted by simulator')
            elif action_type == 'trigger':
                self._set_action_state(action_id, raw_action_type, 'FINISHED', 'Trigger acknowledged by simulator')
            else:
                self._set_action_state(action_id, raw_action_type, 'FAILED', 'Unsupported instant action')
            self.publish_state()

    @staticmethod
    def _normalize_action_type(action_type: str) -> str:
        return ''.join(ch for ch in action_type.lower() if ch.isalnum())

    @staticmethod
    def _get_action_parameter(action: dict[str, Any], key: str) -> Optional[str]:
        params = action.get('actionParameters', [])
        if isinstance(params, dict):
            value = params.get(key)
            return str(value) if value is not None else None
        if not isinstance(params, list):
            return None
        for item in params:
            if not isinstance(item, dict):
                continue
            item_key = item.get('key', item.get('name'))
            if item_key == key:
                value = item.get('value')
                return str(value) if value is not None else None
        return None

    def _execute_vda_action(self, action: dict[str, Any], *, source: str) -> None:
        raw_action_type = str(action.get('actionType', ''))
        action_type = self._normalize_action_type(raw_action_type)
        action_id = str(action.get('actionId', f'{source}-{raw_action_type}-{len(self.action_states)+1}'))
        self._set_action_state(action_id, raw_action_type, 'RUNNING', f'{raw_action_type} running')

        if action_type in {'startcharging', 'startcharge'}:
            self.set_charging(True, publish=False)
            self._set_action_state(action_id, raw_action_type, 'FINISHED', 'Charging started')
        elif action_type in {'stopcharging', 'stopcharge'}:
            self.set_charging(False, publish=False)
            self._set_action_state(action_id, raw_action_type, 'FINISHED', 'Charging stopped')
        elif action_type == 'pick':
            if self.charging:
                self._set_action_state(action_id, raw_action_type, 'FAILED', 'Stop charging before pick')
                return
            load_id = self._get_action_parameter(action, 'loadId') or self._get_action_parameter(action, 'loadID')
            load_type = self._get_action_parameter(action, 'loadType') or 'sim_load'
            self.pick_load(load_id=load_id or f'load-{self.agv_id}', load_type=load_type, publish=False)
            self._set_action_state(action_id, raw_action_type, 'FINISHED', 'Load picked')
        elif action_type == 'drop':
            if self.charging:
                self._set_action_state(action_id, raw_action_type, 'FAILED', 'Stop charging before drop')
                return
            self.drop_load(publish=False)
            self._set_action_state(action_id, raw_action_type, 'FINISHED', 'Load dropped')
        else:
            self._set_action_state(action_id, raw_action_type, 'FAILED', 'Unsupported action')

    def _execute_node_actions(self, node_id: str) -> None:
        actions = self.node_actions_by_node_id.get(node_id, [])
        for action in actions:
            action_id = str(action.get('actionId', f'node-{node_id}-{len(self.executed_node_action_ids)+1}'))
            if action_id in self.executed_node_action_ids:
                continue
            self.executed_node_action_ids.add(action_id)
            self._execute_vda_action(action, source=f'node-{node_id}')
        if actions:
            self.publish_state()

    def _set_action_state(self, action_id: str, action_type: str, status: str, result_description: str) -> None:
        self.action_states = [s for s in self.action_states if s.get('actionId') != action_id]
        self.action_states.append({
            'actionId': action_id,
            'actionType': action_type,
            'actionStatus': status,
            'actionResult': status,
            'resultDescription': result_description,
            'actionResultDescription': result_description,
        })

    def set_charging(self, active: bool, *, publish: bool = True) -> None:
        self.charging = active
        self.battery_current = 10.0 if active else -5.0
        info_type = 'CHARGING_STARTED' if active else 'CHARGING_STOPPED'
        description = 'Charging current set to 10 A' if active else 'Discharging current set to -5 A'
        self.info_messages = [item for item in self.info_messages if item.get('infoType') not in {'CHARGING_STARTED', 'CHARGING_STOPPED'}]
        self.info_messages.append({'infoType': info_type, 'infoDescription': description})
        if publish:
            self.publish_state()

    def pick_load(self, *, load_id: str, load_type: str = 'sim_load', publish: bool = True) -> None:
        self.loads = [{
            'loadId': load_id,
            'loadType': load_type,
            'loadPosition': 'onBoard',
            'boundingBoxReference': {'x': 0.0, 'y': 0.0, 'z': 0.0, 'theta': 0.0},
            'loadDimensions': {'length': 0.6, 'width': 0.4, 'height': 0.25},
        }]
        self.info_messages = [item for item in self.info_messages if item.get('infoType') not in {'LOAD_PICKED', 'LOAD_DROPPED'}]
        self.info_messages.append({'infoType': 'LOAD_PICKED', 'infoDescription': f'Picked {load_id}'})
        if publish:
            self.publish_state()

    def drop_load(self, *, publish: bool = True) -> None:
        dropped = self.loads[0]['loadId'] if self.loads else 'load'
        self.loads.clear()
        self.info_messages = [item for item in self.info_messages if item.get('infoType') not in {'LOAD_PICKED', 'LOAD_DROPPED'}]
        self.info_messages.append({'infoType': 'LOAD_DROPPED', 'infoDescription': f'Dropped {dropped}'})
        if publish:
            self.publish_state()

    def cancel_order(self) -> None:
        self.route = RouteProgress()
        self.velocity = Velocity2D()
        self.node_states.clear()
        self.edge_states.clear()
        self.node_actions_by_node_id.clear()
        self.executed_node_action_ids.clear()
        self.paused = False
        self.run_state = AGVRunState.IDLE

    def _extract_order_nodes(self, payload: dict[str, Any]) -> List[str]:
        nodes: List[str] = []
        for item in payload.get('nodes', []):
            node_id = item.get('nodeId')
            if isinstance(node_id, str):
                nodes.append(node_id)
        if not nodes and 'targetNodeId' in payload:
            nodes = [self.last_node_id, str(payload['targetNodeId'])]
        if nodes and nodes[0] != self.last_node_id:
            nodes.insert(0, self.last_node_id)
        return nodes

    def _extract_node_actions(self, payload: dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
        node_actions: Dict[str, List[Dict[str, Any]]] = {}
        for node in payload.get('nodes', []):
            node_id = node.get('nodeId')
            if not isinstance(node_id, str):
                continue
            actions = node.get('actions', node.get('nodeActions', node.get('node_actions', [])))
            if isinstance(actions, dict):
                actions = [actions]
            if not isinstance(actions, list):
                continue
            cleaned_actions = [action for action in actions if isinstance(action, dict)]
            if cleaned_actions:
                node_actions[node_id] = cleaned_actions
        return node_actions

    def _expand_route(self, requested_nodes: List[str]) -> List[str]:
        full_path: List[str] = [requested_nodes[0]]
        for src, dst in zip(requested_nodes, requested_nodes[1:]):
            segment = self._shortest_path(src, dst)
            if not segment:
                return []
            full_path.extend(segment[1:])
        return full_path

    def _shortest_path(self, start: str, goal: str) -> List[str]:
        if start == goal:
            return [start]
        pq: list[tuple[float, str]] = [(0.0, start)]
        came_from: dict[str, Optional[str]] = {start: None}
        cost_so_far: dict[str, float] = {start: 0.0}

        while pq:
            _, current = heapq.heappop(pq)
            if current == goal:
                break
            for nxt in self.graph.adjacency.get(current, []):
                if self.graph.get_node(nxt).layer != self.layer:
                    continue
                c = cost_so_far[current] + distance(
                    (self.graph.get_node(current).x, self.graph.get_node(current).y),
                    (self.graph.get_node(nxt).x, self.graph.get_node(nxt).y),
                )
                if nxt not in cost_so_far or c < cost_so_far[nxt]:
                    cost_so_far[nxt] = c
                    priority = c
                    heapq.heappush(pq, (priority, nxt))
                    came_from[nxt] = current

        if goal not in came_from:
            return []

        path = [goal]
        while path[-1] != start:
            prev = came_from[path[-1]]
            if prev is None:
                break
            path.append(prev)
        path.reverse()
        return path

    # ----------------------------- operator controls -----------------------------
    def inject_warning(self) -> None:
        self.faults.add('SIM_WARNING', 'Injected warning from operator panel', 'WARNING')

    def inject_error(self) -> None:
        self.faults.add('SIM_ERROR', 'Injected error from operator panel', 'ERROR')
        self.run_state = AGVRunState.PAUSED

    def inject_fatal(self) -> None:
        self.faults.add('SIM_FATAL', 'Injected fatal error from operator panel', 'FATAL')
        self.run_state = AGVRunState.FAILED
        self.velocity = Velocity2D()
        self.publish_state()

    def clear_errors(self) -> None:
        self.faults.clear()
        if self.power.power_on:
            if self.route.active and not self.paused:
                self.run_state = AGVRunState.MOVING
            elif self.route.active and self.paused:
                self.run_state = AGVRunState.PAUSED
            else:
                self.run_state = AGVRunState.IDLE

    def toggle_obstacle(self) -> None:
        self.obstacle_active = not self.obstacle_active
        if self.obstacle_active:
            self.obstacle_distance = self.stop_distance
            self.obstacle_point = self._default_obstacle_point()
            self.obstacle_lidar_hit = self._obstacle_point_in_lidar()
            self._set_obstacle_warning(active=self.obstacle_lidar_hit)
        else:
            self.obstacle_lidar_hit = False
            self._set_obstacle_warning(active=False)
            if self.route.active and not self.paused and self.power.power_on:
                self.run_state = AGVRunState.MOVING
        self.publish_state()

    def _set_obstacle_warning(self, *, active: bool) -> None:
        self.faults.remove('OBSTACLE_IN_STOP_DISTANCE')
        self.info_messages = [item for item in self.info_messages if item.get('infoType') != 'OBSTACLE']
        if not active:
            return

        description = f'Obstacle touches lidar bank {self.active_lidar_bank + 1} at {self.obstacle_distance:.2f} m'
        self.faults.add('OBSTACLE_IN_STOP_DISTANCE', description, 'WARNING')
        self.info_messages.append({
            'infoType': 'OBSTACLE',
            'infoDescription': description,
        })

    def _set_peer_warning(self, *, active: bool) -> None:
        self.faults.remove('PEER_AGV_IN_STOP_DISTANCE')
        self.info_messages = [item for item in self.info_messages if item.get('infoType') != 'AGV_PROXIMITY']
        if not active:
            return

        description = (
            f'AGV {self.peer_stop_agv_id} body touches lidar bank {self.active_lidar_bank + 1}'
        )
        self.faults.add('PEER_AGV_IN_STOP_DISTANCE', description, 'WARNING')
        self.info_messages.append({
            'infoType': 'AGV_PROXIMITY',
            'infoDescription': description,
        })

    def _set_human_warning(self, *, active: bool) -> None:
        self.faults.remove('HUMAN_IN_STOP_DISTANCE')
        self.info_messages = [item for item in self.info_messages if item.get('infoType') != 'HUMAN_PROXIMITY']
        if not active:
            return

        description = (
            f'Human {self.human_stop_id} touches lidar bank {self.active_lidar_bank + 1}'
        )
        self.faults.add('HUMAN_IN_STOP_DISTANCE', description, 'WARNING')
        self.info_messages.append({
            'infoType': 'HUMAN_PROXIMITY',
            'infoDescription': description,
        })

    def pause(self) -> None:
        self.paused = True
        self.run_state = AGVRunState.PAUSED

    def resume(self) -> None:
        self.paused = False
        if self.route.active:
            self.run_state = AGVRunState.MOVING
        else:
            self.run_state = AGVRunState.IDLE

    def power_off(self) -> None:
        self.publish_offline_connection()
        self.power.shutdown()
        self.velocity = Velocity2D()
        self.run_state = AGVRunState.POWER_OFF
        self.mqtt.disconnect()

    def power_on(self) -> None:
        self.power.startup()
        self.mqtt_disabled_by_operator = False
        self.mqtt.connect()
        self.publish_factsheet()
        if self.route.active:
            self.run_state = AGVRunState.MOVING if not self.paused else AGVRunState.PAUSED
        else:
            self.run_state = AGVRunState.IDLE

    def mqtt_disconnect(self) -> None:
        self.publish_offline_connection()
        self.mqtt_disabled_by_operator = True
        self.mqtt.disconnect()

    def mqtt_reconnect(self) -> None:
        self.mqtt_disabled_by_operator = False
        self.mqtt.reconnect()

    def _safety_stop_active(self) -> bool:
        return self.obstacle_lidar_hit or self.peer_stop_active or self.human_stop_active

    def active_lidar_polygon_local(self) -> list[tuple[float, float]]:
        if not self.lidar_banks:
            self.lidar_banks = [self._default_lidar_polygon()]
        self.active_lidar_bank = max(0, min(self.active_lidar_bank, len(self.lidar_banks) - 1))
        return self.lidar_banks[self.active_lidar_bank]

    def active_lidar_polygon_world(self) -> list[tuple[float, float]]:
        return [self.local_lidar_point_to_world(x, y) for x, y in self.active_lidar_polygon_local()]

    def max_lidar_range(self) -> float:
        ranges = [
            math.hypot(x, y)
            for bank in self.lidar_banks
            for x, y in bank
        ]
        return max(ranges, default=self.stop_distance)

    def local_lidar_point_to_world(self, x: float, y: float) -> tuple[float, float]:
        cos_t = math.cos(self.pose.theta)
        sin_t = math.sin(self.pose.theta)
        return self.pose.x + x * cos_t - y * sin_t, self.pose.y + x * sin_t + y * cos_t

    def world_point_to_lidar_local(self, x: float, y: float) -> tuple[float, float]:
        dx = x - self.pose.x
        dy = y - self.pose.y
        cos_t = math.cos(self.pose.theta)
        sin_t = math.sin(self.pose.theta)
        return dx * cos_t + dy * sin_t, -dx * sin_t + dy * cos_t

    def set_lidar_bank(self, bank_index: int, points: list[tuple[float, float]]) -> None:
        cleaned = [(float(x), float(y)) for x, y in points]
        while len(self.lidar_banks) <= bank_index:
            self.lidar_banks.append(self._default_lidar_polygon())
        self.lidar_banks[bank_index] = cleaned
        self.active_lidar_bank = bank_index
        self.obstacle_lidar_hit = self._obstacle_point_in_lidar()
        self._set_obstacle_warning(active=self.obstacle_lidar_hit)

    @staticmethod
    def _default_lidar_polygon() -> list[tuple[float, float]]:
        return [(0.0, -0.8), (1.8, -1.0), (2.2, 0.0), (1.8, 1.0), (0.0, 0.8)]

    def _default_obstacle_point(self) -> tuple[float, float]:
        return self.local_lidar_point_to_world(self.size.length / 2.0 + self.stop_distance, 0.0)

    # ----------------------------- simulation update -----------------------------
    def update(self, dt: float) -> None:
        self._state_elapsed += dt
        self._connection_elapsed += dt
        self._visualization_elapsed += dt

        if not self.power.power_on:
            self.velocity = Velocity2D()
            return

        if self.charging:
            self.battery = min(100.0, self.battery + max(self.battery_drain_per_second * 8.0, 0.02) * dt)
        else:
            self.battery = max(0.0, self.battery - self.battery_drain_per_second * dt)
        if self.battery <= 15.0 and not self.faults.has_error_level('WARNING'):
            self.faults.add('BATTERY_LOW', 'Battery charge below 15%', 'WARNING')

        if self._connection_elapsed >= self._connection_interval:
            self.publish_connection()
            self._connection_elapsed = 0.0

        if self._visualization_elapsed >= self._visualization_interval:
            self.publish_visualization()
            self._visualization_elapsed = 0.0

        self._update_motion(dt)

        if self._state_elapsed >= self._state_interval:
            self.publish_state()
            self._state_elapsed = 0.0

    def _update_motion(self, dt: float) -> None:
        if self.faults.has_error_level('FATAL'):
            self.velocity = Velocity2D()
            self.run_state = AGVRunState.FAILED
            return

        if self.mode == AGVMode.MANUAL:
            return

        if self._obstacle_in_stop_distance():
            self.velocity = Velocity2D()
            self.run_state = AGVRunState.PAUSED
            return

        if self.peer_stop_active:
            self.velocity = Velocity2D()
            self.run_state = AGVRunState.PAUSED
            self._set_peer_warning(active=True)
            return

        if self.human_stop_active:
            self.velocity = Velocity2D()
            self.run_state = AGVRunState.PAUSED
            self._set_human_warning(active=True)
            return

        if self.paused or self.faults.blocking():
            self.velocity.linear = max(0.0, self.velocity.linear - self.max_accel * dt * 2.0)
            if self.velocity.linear <= 0.001:
                self.velocity.linear = 0.0
            self.run_state = AGVRunState.PAUSED if self.route.active else AGVRunState.IDLE
            return
        self._set_obstacle_warning(active=False)

        target_id = self.route.current_target_node
        if not target_id:
            self.velocity = Velocity2D()
            if self.run_state not in {AGVRunState.FAILED, AGVRunState.POWER_OFF}:
                self.run_state = AGVRunState.IDLE
            return

        edge = self.graph.find_edge(self.last_node_id, target_id) if self.last_node_id else None
        if edge and edge.edge_type == 'bezier':
            self._update_bezier_motion(edge, self.last_node_id, target_id, dt)
            return

        self._update_linear_motion(target_id, dt)

    def _update_linear_motion(self, target_id: str, dt: float) -> None:
        target = self.graph.get_node(target_id)
        dx = target.x - self.pose.x
        dy = target.y - self.pose.y
        dist = math.hypot(dx, dy)
        desired_heading = heading_to((self.pose.x, self.pose.y), (target.x, target.y))
        heading_err = normalize_angle(desired_heading - self.pose.theta)
        self.pose.theta = normalize_angle(self.pose.theta + clamp(heading_err, -2.4 * dt, 2.4 * dt))

        slow_down_distance = max(self.stop_distance, 0.12)
        desired_speed = min(self.max_speed, self.max_speed * dist / slow_down_distance)
        self.velocity.linear = clamp(
            self.velocity.linear + math.copysign(self.max_accel * dt, desired_speed - self.velocity.linear),
            0.0,
            self.max_speed,
        )
        if abs(heading_err) > 0.4:
            self.velocity.linear = min(self.velocity.linear, 0.35)

        self.pose.x += math.cos(self.pose.theta) * self.velocity.linear * dt
        self.pose.y += math.sin(self.pose.theta) * self.velocity.linear * dt
        self.run_state = AGVRunState.MOVING

        if dist <= 0.12:
            self._complete_current_target(target_id)

    def _update_bezier_motion(self, edge: Edge, from_node_id: str, target_id: str, dt: float) -> None:
        curve_length = max(0.1, self._bezier_length(edge, from_node_id, target_id))
        closest_t = self._closest_bezier_t(edge, from_node_id, target_id)
        remaining = max(0.0, (1.0 - closest_t) * curve_length)

        lookahead_m = max(0.25, min(0.9, self.velocity.linear * 0.8 + 0.35))
        target_t = min(1.0, closest_t + lookahead_m / curve_length)
        target_point = self._bezier_point(edge, from_node_id, target_id, target_t)
        end_node = self.graph.get_node(target_id)
        end_dist = math.hypot(end_node.x - self.pose.x, end_node.y - self.pose.y)

        desired_heading = heading_to((self.pose.x, self.pose.y), target_point)
        heading_err = normalize_angle(desired_heading - self.pose.theta)
        self.pose.theta = normalize_angle(self.pose.theta + clamp(heading_err, -2.4 * dt, 2.4 * dt))

        slow_down_distance = max(self.stop_distance, 0.25)
        desired_speed = min(self.max_speed, self.max_speed * remaining / slow_down_distance)
        self.velocity.linear = clamp(
            self.velocity.linear + math.copysign(self.max_accel * dt, desired_speed - self.velocity.linear),
            0.0,
            self.max_speed,
        )
        if abs(heading_err) > 0.45:
            self.velocity.linear = min(self.velocity.linear, 0.35)

        self.pose.x += math.cos(self.pose.theta) * self.velocity.linear * dt
        self.pose.y += math.sin(self.pose.theta) * self.velocity.linear * dt
        self.run_state = AGVRunState.MOVING

        if closest_t >= 0.985 or end_dist <= 0.12:
            self._complete_current_target(target_id)

    def _complete_current_target(self, target_id: str) -> None:
        target = self.graph.get_node(target_id)
        self.pose.x = target.x
        self.pose.y = target.y
        self.state_pose.x = target.x
        self.state_pose.y = target.y
        self.state_pose.theta = self.pose.theta
        self.layer = target.layer
        self.last_node_id = target_id
        self.route.current_index += 1
        self.velocity.linear = 0.0
        self._execute_node_actions(target_id)
        if not self.route.active:
            self.run_state = AGVRunState.FINISHED
            self.info_messages = [{'infoType': 'ORDER_FINISHED', 'infoDescription': f'Finished {self.route.order_id}'}]
            self.route = RouteProgress(order_id=self.route.order_id, order_update_id=self.route.order_update_id)
        else:
            self.run_state = AGVRunState.MOVING

    def _bezier_points(self, edge: Edge, from_node_id: str, to_node_id: str) -> tuple[tuple[float, float], ...]:
        start = self.graph.get_node(from_node_id)
        end = self.graph.get_node(to_node_id)
        if (
            edge.control1_x is None
            or edge.control1_y is None
            or edge.control2_x is None
            or edge.control2_y is None
        ):
            c1, c2 = self.graph.default_bezier_controls(edge.from_node, edge.to_node)
        else:
            c1 = (edge.control1_x, edge.control1_y)
            c2 = (edge.control2_x, edge.control2_y)

        if edge.from_node == from_node_id and edge.to_node == to_node_id:
            return (start.x, start.y), c1, c2, (end.x, end.y)
        return (start.x, start.y), c2, c1, (end.x, end.y)

    def _bezier_point(self, edge: Edge, from_node_id: str, to_node_id: str, t: float) -> tuple[float, float]:
        p0, p1, p2, p3 = self._bezier_points(edge, from_node_id, to_node_id)
        inv = 1.0 - t
        x = inv ** 3 * p0[0] + 3.0 * inv * inv * t * p1[0] + 3.0 * inv * t * t * p2[0] + t ** 3 * p3[0]
        y = inv ** 3 * p0[1] + 3.0 * inv * inv * t * p1[1] + 3.0 * inv * t * t * p2[1] + t ** 3 * p3[1]
        return x, y

    def _closest_bezier_t(self, edge: Edge, from_node_id: str, to_node_id: str) -> float:
        best_t = 0.0
        best_d = 999999.0
        for idx in range(41):
            t = idx / 40.0
            x, y = self._bezier_point(edge, from_node_id, to_node_id, t)
            d = (x - self.pose.x) ** 2 + (y - self.pose.y) ** 2
            if d < best_d:
                best_d = d
                best_t = t
        return best_t

    def _bezier_length(self, edge: Edge, from_node_id: str, to_node_id: str) -> float:
        length = 0.0
        prev = self._bezier_point(edge, from_node_id, to_node_id, 0.0)
        for idx in range(1, 41):
            point = self._bezier_point(edge, from_node_id, to_node_id, idx / 40.0)
            length += math.hypot(point[0] - prev[0], point[1] - prev[1])
            prev = point
        return length

    def _obstacle_in_stop_distance(self) -> bool:
        if not self.obstacle_active:
            self.obstacle_lidar_hit = False
            return False
        self.obstacle_distance = distance((self.pose.x, self.pose.y), self.obstacle_point)
        self.obstacle_lidar_hit = self._obstacle_point_in_lidar()
        if self.obstacle_lidar_hit:
            self._set_obstacle_warning(active=True)
            return True
        self._set_obstacle_warning(active=False)
        return False

    def _obstacle_point_in_lidar(self) -> bool:
        return point_in_polygon(self.obstacle_point, self.active_lidar_polygon_world())
