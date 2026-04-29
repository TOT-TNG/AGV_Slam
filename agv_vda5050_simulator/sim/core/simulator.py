from __future__ import annotations

import math
import random
import threading
from pathlib import Path
from typing import Dict, List, Optional

from sim.core.agv_agent import AGVAgent
from sim.core.elevator_agent import ElevatorAgent
from sim.core.elevator_api import ElevatorAPIServer
from sim.core.human_agent import HumanAgent
from sim.core.models import Pose2D, Velocity2D, VehicleSize
from sim.map.graph import Graph
from sim.vda5050.mqtt_client import MQTTSettings

AGV_TYPES = ['SLAM', 'QR', 'LINE']
AGV_COLORS = [
    (40, 220, 80),
    (70, 150, 255),
    (255, 180, 50),
    (235, 90, 90),
    (170, 120, 255),
    (90, 210, 210),
]
HUMAN_COLORS = [
    (230, 90, 85),
    (245, 155, 70),
    (130, 95, 225),
    (65, 175, 160),
    (225, 105, 170),
]


class Simulator:
    def __init__(self, *, root: Path, config: dict, graph: Graph) -> None:
        self.root = root
        self.config = config
        self.graph = graph
        sim_cfg = config['simulation']
        self.tick_hz = float(sim_cfg['tick_hz'])
        self.tick_dt = 1.0 / self.tick_hz
        self.lock = threading.RLock()

        self.mqtt_settings = self._build_mqtt_settings(config['mqtt'])

        self.agvs: List[AGVAgent] = []
        for item in config['agvs']:
            self.agvs.append(self._build_agv(item))

        self.humans: List[HumanAgent] = []
        for item in config.get('humans', []):
            self.humans.append(self._build_human(item))

        self.elevators: List[ElevatorAgent] = []
        for item in config.get('elevators', []):
            self.elevators.append(self._build_elevator(item))

        self.elevator_api: Optional[ElevatorAPIServer] = None
        self.api_last_error = ''
        self._start_elevator_api()

    @staticmethod
    def _build_mqtt_settings(mqtt_cfg: dict) -> MQTTSettings:
        return MQTTSettings(
            host=mqtt_cfg['host'],
            port=int(mqtt_cfg['port']),
            keepalive=int(mqtt_cfg['keepalive']),
            enabled=bool(mqtt_cfg.get('enabled', True)),
            interface_name=str(mqtt_cfg.get('interface_name', 'uagv')),
            major_version=str(mqtt_cfg.get('major_version', 'v2')),
        )

    def update_mqtt_config(self, mqtt_cfg: dict) -> None:
        self.config['mqtt'] = mqtt_cfg
        agv_items = self.snapshot_agvs()
        elevator_items = self.snapshot_elevators()
        self.mqtt_settings = self._build_mqtt_settings(mqtt_cfg)
        self.replace_agvs(agv_items)
        self.replace_elevators(elevator_items)

    def update_map_upload_config(self, upload_cfg: dict) -> None:
        self.config['map_upload'] = upload_cfg

    def update_publish_config(self, publish_cfg: dict) -> None:
        sim_cfg = self.config.setdefault('simulation', {})
        sim_cfg.update(publish_cfg)
        for agv in self.agvs:
            agv.update_publish_rates(
                state_publish_hz=float(sim_cfg.get('state_publish_hz', 1.0)),
                connection_publish_hz=float(sim_cfg.get('connection_publish_hz', 0.2)),
                visualization_publish_hz=float(sim_cfg.get('visualization_publish_hz', 1.0)),
            )

    def update(self, dt: float) -> None:
        with self.lock:
            for human in self.humans:
                human.update(dt)

            for elevator in self.elevators:
                arrived = elevator.update(dt)
                if arrived:
                    self._transfer_occupied_agv_to_elevator_floor(elevator)

            agv_grid, agv_cell_size, max_agv_extent = self._build_agv_spatial_index()
            human_grid, human_cell_size, max_human_radius = self._build_human_spatial_index()
            for agv in self.agvs:
                agv.check_peer_stop_distance(self._nearby_agvs(agv, agv_grid, agv_cell_size, max_agv_extent))
                agv.check_human_stop_distance(self._nearby_humans(agv, human_grid, human_cell_size, max_human_radius))
            for agv in self.agvs:
                agv.update(dt)

    def get_agv_by_id(self, agv_id: str) -> Optional[AGVAgent]:
        return next((a for a in self.agvs if a.agv_id == agv_id), None)

    def get_elevator_by_id(self, elevator_id: str | int) -> Optional[ElevatorAgent]:
        return next((e for e in self.elevators if str(e.elevator_id) == str(elevator_id)), None)

    def next_elevator_id(self) -> int:
        elevator_ids = {elevator.elevator_id for elevator in self.elevators}
        index = 1
        while index in elevator_ids:
            index += 1
        return index

    def configure_elevator_floor_node(self, *, node_id: str, elevator_id: int = 1) -> ElevatorAgent:
        if node_id not in self.graph.nodes:
            raise ValueError(f'Node {node_id} not found')

        node = self.graph.nodes[node_id]
        node.node_type = 'elevator'
        self._remove_elevator_node_mappings(node_id, keep_elevator_id=elevator_id)
        elevator = self.get_elevator_by_id(elevator_id)
        replaced_node_id = None
        if elevator is None:
            elevator = self._build_elevator({
                'elevator_id': elevator_id,
                'node_id': node_id,
                'floors': [node.layer],
                'floor_nodes': {str(node.layer): node_id},
                'current_floor': node.layer,
                'target_floor': node.layer,
                'door': 'closed',
                'status': 'idle',
            })
            self.elevators.append(elevator)
        else:
            replaced_node_id = elevator.floor_nodes.get(node.layer)
            if node.layer not in elevator.floors:
                elevator.floors = sorted([*elevator.floors, node.layer])
            elevator.floor_nodes[node.layer] = node_id
            if not elevator.node_id or node.layer == 0:
                elevator.node_id = node_id
        if replaced_node_id and replaced_node_id != node_id:
            self._clear_unmapped_elevator_node(replaced_node_id)
        elevator.publish_state(retain=True)
        return elevator

    def _remove_elevator_node_mappings(self, node_id: str, *, keep_elevator_id: int) -> None:
        for elevator in self.elevators:
            if elevator.elevator_id == int(keep_elevator_id):
                continue
            removed_floors = [
                floor
                for floor, floor_node_id in elevator.floor_nodes.items()
                if floor_node_id == node_id
            ]
            for floor in removed_floors:
                elevator.floor_nodes.pop(floor, None)
            if removed_floors:
                elevator.floors = sorted(elevator.floor_nodes)
                elevator.publish_state(retain=True)

    def _clear_unmapped_elevator_node(self, node_id: str) -> None:
        node = self.graph.nodes.get(node_id)
        if node is None or node.node_type != 'elevator':
            return
        for elevator in self.elevators:
            if node_id in elevator.floor_nodes.values():
                return
        node.node_type = 'intersection'

    def add_agv(self, *, agv_type: Optional[str] = None, start_node: Optional[str] = None, layer: Optional[int] = None) -> AGVAgent:
        if not self.graph.nodes:
            raise ValueError('Cannot add AGV: map has no nodes')

        agv_id = self.next_agv_id()
        node_id = self._resolve_start_node(start_node, layer=layer)
        index = len(self.agvs)
        item = {
            'agv_id': agv_id,
            'agv_type': agv_type or AGV_TYPES[index % len(AGV_TYPES)],
            'start_node': node_id,
            'max_speed': 0.8,
            'max_accel': 0.5,
            'color': AGV_COLORS[index % len(AGV_COLORS)],
        }
        agv = self._build_agv(item)
        self.agvs.append(agv)
        return agv

    def add_agv_from_form(
        self,
        *,
        agv_type: str,
        length: float,
        width: float,
        stop_distance: float,
        start_node: Optional[str] = None,
        layer: Optional[int] = None,
    ) -> AGVAgent:
        if not self.graph.nodes:
            raise ValueError('Cannot add AGV: map has no nodes')

        agv_id = self.next_agv_id()
        node_id = self._resolve_start_node(start_node, layer=layer)
        index = len(self.agvs)
        item = {
            'agv_id': agv_id,
            'agv_type': agv_type,
            'start_node': node_id,
            'length': length,
            'width': width,
            'stop_distance': stop_distance,
            'layer': int(layer) if layer is not None else self.graph.nodes[node_id].layer,
            'max_speed': 0.8,
            'max_accel': 0.5,
            'color': AGV_COLORS[index % len(AGV_COLORS)],
        }
        agv = self._build_agv(item)
        self.agvs.append(agv)
        return agv

    def add_human(self, *, x: Optional[float] = None, y: Optional[float] = None, layer: int = 0) -> HumanAgent:
        index = len(self.humans)
        human_cfg = self.config.get('simulation', {}).get('human', {})
        radius = float(human_cfg.get('radius', 0.22))
        min_x, max_x = self._random_spawn_range(self.graph.width_m, radius)
        min_y, max_y = self._random_spawn_range(self.graph.height_m, radius)
        human = self._build_human({
            'human_id': self.next_human_id(),
            'x': random.uniform(min_x, max_x) if x is None else x,
            'y': random.uniform(min_y, max_y) if y is None else y,
            'radius': radius,
            'speed': float(human_cfg.get('speed', 0.55)),
            'color': HUMAN_COLORS[index % len(HUMAN_COLORS)],
            'layer': int(layer),
        })
        self.humans.append(human)
        return human

    def remove_human(self, human_id: Optional[str] = None) -> Optional[HumanAgent]:
        if not self.humans:
            return None
        if human_id is None:
            return self.humans.pop()
        for idx, human in enumerate(self.humans):
            if human.human_id == human_id:
                return self.humans.pop(idx)
        return None

    def remove_agv(self, agv_id: Optional[str] = None) -> Optional[AGVAgent]:
        if not self.agvs:
            return None
        if agv_id is None:
            agv = self.agvs.pop()
        else:
            agv = None
            for idx, item in enumerate(self.agvs):
                if item.agv_id == agv_id:
                    agv = self.agvs.pop(idx)
                    break
            if agv is None:
                return None
        agv.publish_offline_connection()
        agv.mqtt.disconnect()
        return agv

    def clear_humans(self) -> int:
        count = len(self.humans)
        self.humans.clear()
        return count

    def replace_agvs(self, agv_items: list[dict]) -> None:
        for agv in self.agvs:
            agv.publish_offline_connection()
            agv.mqtt.disconnect()
        self.agvs = [self._build_agv(item) for item in agv_items]

    def replace_humans(self, human_items: list[dict]) -> None:
        self.humans = [self._build_human(item) for item in human_items]

    def replace_elevators(self, elevator_items: list[dict]) -> None:
        for elevator in self.elevators:
            elevator.disconnect()
        self.elevators = [self._build_elevator(item) for item in elevator_items]

    def snapshot_agvs(self) -> list[dict]:
        return [
            {
                'agv_id': agv.agv_id,
                'agv_type': agv.agv_type,
                'length': round(agv.size.length, 3),
                'width': round(agv.size.width, 3),
                'stop_distance': round(agv.stop_distance, 3),
                'start_node': agv.start_node or agv.last_node_id,
                'last_node_id': agv.last_node_id,
                'max_speed': round(agv.max_speed, 3),
                'max_accel': round(agv.max_accel, 3),
                'active_lidar_bank': agv.active_lidar_bank,
                'lidar_banks': [
                    [{'x': round(x, 3), 'y': round(y, 3)} for x, y in bank]
                    for bank in agv.lidar_banks
                ],
                'color': list(agv.color),
                'battery': round(agv.battery, 1),
                'charging': agv.charging,
                'battery_current': round(agv.battery_current, 1),
                'loads': list(agv.loads),
                'layer': agv.layer,
                'pose': {
                    'x': round(agv.pose.x, 3),
                    'y': round(agv.pose.y, 3),
                    'theta': round(agv.pose.theta, 6),
                },
            }
            for agv in self.agvs
        ]

    def snapshot_humans(self) -> list[dict]:
        return [
            {
                'human_id': human.human_id,
                'x': round(human.pose.x, 3),
                'y': round(human.pose.y, 3),
                'theta': round(human.pose.theta, 6),
                'radius': round(human.radius, 3),
                'speed': round(human.speed, 3),
                'paused': human.paused,
                'color': list(human.color),
                'layer': human.layer,
            }
            for human in self.humans
        ]

    def snapshot_elevators(self) -> list[dict]:
        return [elevator.snapshot() for elevator in self.elevators]

    def set_graph(self, graph: Graph) -> None:
        self.graph = graph
        fallback_node = next(iter(graph.nodes.values()), None)
        for agv in self.agvs:
            agv.cancel_order()
            agv.graph = graph
            agv.velocity = Velocity2D()
            if fallback_node is None:
                agv.last_node_id = ''
                continue
            agv.start_node = fallback_node.node_id
            agv.last_node_id = fallback_node.node_id
            agv.layer = fallback_node.layer
            agv.pose.x = fallback_node.x
            agv.pose.y = fallback_node.y
            agv.pose.theta = 0.0
            agv.state_pose.x = fallback_node.x
            agv.state_pose.y = fallback_node.y
            agv.state_pose.theta = 0.0
        for human in self.humans:
            human.graph = graph
            human.place(human.pose.x, human.pose.y)
            human.pick_new_target()

    def next_agv_id(self) -> str:
        index = 1
        while f'AGV{index:02d}' in {agv.agv_id for agv in self.agvs}:
            index += 1
        return f'AGV{index:02d}'

    def next_human_id(self) -> str:
        index = 1
        while f'H{index:02d}' in {human.human_id for human in self.humans}:
            index += 1
        return f'H{index:02d}'

    def _resolve_start_node(self, node_id: Optional[str], *, layer: Optional[int] = None) -> str:
        if node_id in self.graph.nodes:
            return str(node_id)
        if layer is not None:
            fallback = next((node_id for node_id, node in self.graph.nodes.items() if node.layer == int(layer)), None)
            if fallback is not None:
                return fallback
        fallback = next(iter(self.graph.nodes), None)
        if fallback is None:
            raise ValueError('Cannot create AGV: map has no nodes')
        return fallback

    @staticmethod
    def _random_spawn_range(size: float, margin: float) -> tuple[float, float]:
        if size <= margin * 2.0:
            return 0.0, max(0.0, size)
        return margin, size - margin

    def _build_agv_spatial_index(self) -> tuple[dict[tuple[int, int, int], list[AGVAgent]], float, float]:
        if not self.agvs:
            return {}, 1.0, 0.0
        max_stop = max(max(agv.stop_distance, agv.max_lidar_range()) for agv in self.agvs)
        max_extent = max(math.hypot(agv.size.length, agv.size.width) * 0.5 for agv in self.agvs)
        cell_size = max(0.5, max_stop + max_extent)
        grid: dict[tuple[int, int, int], list[AGVAgent]] = {}
        for agv in self.agvs:
            grid.setdefault((agv.layer, *self._spatial_cell(agv.pose.x, agv.pose.y, cell_size)), []).append(agv)
        return grid, cell_size, max_extent

    def _build_human_spatial_index(self) -> tuple[dict[tuple[int, int, int], list[HumanAgent]], float, float]:
        if not self.humans:
            return {}, 1.0, 0.0
        max_stop = max((max(agv.stop_distance, agv.max_lidar_range()) for agv in self.agvs), default=1.0)
        max_radius = max(human.radius for human in self.humans)
        cell_size = max(0.5, max_stop + max_radius)
        grid: dict[tuple[int, int, int], list[HumanAgent]] = {}
        for human in self.humans:
            grid.setdefault((human.layer, *self._spatial_cell(human.pose.x, human.pose.y, cell_size)), []).append(human)
        return grid, cell_size, max_radius

    def _nearby_agvs(
        self,
        agv: AGVAgent,
        grid: dict[tuple[int, int, int], list[AGVAgent]],
        cell_size: float,
        max_peer_extent: float,
    ) -> list[AGVAgent]:
        if not grid:
            return []
        radius = max(agv.stop_distance, agv.max_lidar_range()) + max_peer_extent
        return self._nearby_from_grid(agv.pose.x, agv.pose.y, radius, grid, cell_size, agv.layer)

    def _nearby_humans(
        self,
        agv: AGVAgent,
        grid: dict[tuple[int, int, int], list[HumanAgent]],
        cell_size: float,
        max_human_radius: float,
    ) -> list[HumanAgent]:
        if not grid:
            return []
        radius = max(agv.stop_distance, agv.max_lidar_range()) + max_human_radius
        return self._nearby_from_grid(agv.pose.x, agv.pose.y, radius, grid, cell_size, agv.layer)

    @staticmethod
    def _nearby_from_grid(
        x: float,
        y: float,
        radius: float,
        grid: dict[tuple[int, int, int], list],
        cell_size: float,
        layer: int,
    ) -> list:
        cx, cy = Simulator._spatial_cell(x, y, cell_size)
        span = max(1, int(math.ceil(radius / cell_size)))
        items = []
        seen: set[int] = set()
        for gx in range(cx - span, cx + span + 1):
            for gy in range(cy - span, cy + span + 1):
                for item in grid.get((layer, gx, gy), []):
                    item_id = id(item)
                    if item_id in seen:
                        continue
                    seen.add(item_id)
                    items.append(item)
        return items

    @staticmethod
    def _spatial_cell(x: float, y: float, cell_size: float) -> tuple[int, int]:
        return math.floor(x / cell_size), math.floor(y / cell_size)

    def _build_agv(self, item: dict) -> AGVAgent:
        sim_cfg = self.config['simulation']
        size_cfg = sim_cfg['default_size']
        length = float(item.get('length', size_cfg['length']))
        width = float(item.get('width', size_cfg['width']))
        agv = AGVAgent(
            manufacturer=self.config['manufacturer'],
            agv_id=item['agv_id'],
            agv_type=str(item.get('agv_type', item.get('type', 'SLAM'))),
            graph=self.graph,
            mqtt_settings=self.mqtt_settings,
            start_node=self._resolve_start_node(item.get('start_node'), layer=item.get('layer')),
            max_speed=float(item.get('max_speed', 0.8)),
            max_accel=float(item.get('max_accel', 0.5)),
            stop_distance=float(item.get('stop_distance', sim_cfg.get('default_stop_distance', 0.9))),
            size=VehicleSize(length=length, width=width),
            battery_drain_per_second=float(sim_cfg.get('battery_drain_per_second', 0.005)),
            color=tuple(item.get('color', AGV_COLORS[0])),
            state_publish_hz=float(sim_cfg.get('state_publish_hz', 1.0)),
            connection_publish_hz=float(sim_cfg.get('connection_publish_hz', 0.2)),
            visualization_publish_hz=float(sim_cfg.get('visualization_publish_hz', 1.0)),
            layer=int(item.get('layer', 0)),
        )
        pose = item.get('pose')
        if isinstance(pose, dict):
            agv.pose.x = max(0.0, min(self.graph.width_m, float(pose.get('x', agv.pose.x))))
            agv.pose.y = max(0.0, min(self.graph.height_m, float(pose.get('y', agv.pose.y))))
            agv.pose.theta = float(pose.get('theta', agv.pose.theta))
        elif 'x' in item and 'y' in item:
            agv.pose.x = max(0.0, min(self.graph.width_m, float(item['x'])))
            agv.pose.y = max(0.0, min(self.graph.height_m, float(item['y'])))
            agv.pose.theta = float(item.get('theta', agv.pose.theta))
        saved_last_node = str(item.get('last_node_id', ''))
        if saved_last_node in self.graph.nodes:
            agv.last_node_id = saved_last_node
            agv.layer = self.graph.nodes[saved_last_node].layer
        else:
            agv.last_node_id = self._nearest_node_id(agv.pose.x, agv.pose.y, layer=agv.layer) or agv.last_node_id
        state_node = self.graph.nodes.get(agv.last_node_id)
        if state_node is not None:
            agv.state_pose.x = state_node.x
            agv.state_pose.y = state_node.y
            agv.state_pose.theta = agv.pose.theta
        agv.battery = max(0.0, min(100.0, float(item.get('battery', agv.battery))))
        agv.charging = bool(item.get('charging', agv.charging))
        agv.battery_current = float(item.get('battery_current', 10.0 if agv.charging else -5.0))
        loads = item.get('loads', [])
        if isinstance(loads, list):
            agv.loads = [load for load in loads if isinstance(load, dict)]
        lidar_banks = item.get('lidar_banks', [])
        if isinstance(lidar_banks, list) and lidar_banks:
            parsed_banks = []
            for bank in lidar_banks:
                if not isinstance(bank, list):
                    continue
                points = []
                for point in bank:
                    if isinstance(point, dict):
                        points.append((float(point.get('x', 0.0)), float(point.get('y', 0.0))))
                    elif isinstance(point, (list, tuple)) and len(point) >= 2:
                        points.append((float(point[0]), float(point[1])))
                if points:
                    parsed_banks.append(points)
            if parsed_banks:
                agv.lidar_banks = parsed_banks
                agv.active_lidar_bank = max(0, min(int(item.get('active_lidar_bank', 0)), len(parsed_banks) - 1))
        return agv

    def _build_human(self, item: dict) -> HumanAgent:
        human_cfg = self.config.get('simulation', {}).get('human', {})
        width = max(0.0, self.graph.width_m)
        height = max(0.0, self.graph.height_m)
        x = float(item.get('x', width * 0.5))
        y = float(item.get('y', height * 0.5))
        human = HumanAgent(
            human_id=str(item.get('human_id', item.get('id', self.next_human_id()))),
            graph=self.graph,
            pose=Pose2D(
                max(0.0, min(width, x)),
                max(0.0, min(height, y)),
                float(item.get('theta', 0.0)),
            ),
            radius=float(item.get('radius', human_cfg.get('radius', 0.22))),
            speed=float(item.get('speed', human_cfg.get('speed', 0.55))),
            color=tuple(item.get('color', HUMAN_COLORS[len(self.humans) % len(HUMAN_COLORS)])),
            paused=bool(item.get('paused', False)),
            layer=int(item.get('layer', 0)),
        )
        return human

    def _build_elevator(self, item: dict) -> ElevatorAgent:
        elevator_id = int(item.get('elevator_id', item.get('id', len(self.elevators) + 1)))
        node_id = str(item.get('node_id', ''))
        if not node_id and self.graph.nodes:
            node_id = next(iter(self.graph.nodes))
        floors = item.get('floors')
        floor_nodes = item.get('floor_nodes', {})
        if not floors:
            floors = sorted({node.layer for node in self.graph.nodes.values()}) or [0]
        elevator = ElevatorAgent(
            elevator_id=elevator_id,
            node_id=node_id,
            mqtt_settings=self.mqtt_settings,
            floors=[int(floor) for floor in floors],
            floor_nodes={int(k): str(v) for k, v in dict(floor_nodes).items()},
            current_floor=int(item.get('current_floor', item.get('floor', 0))),
            target_floor=int(item.get('target_floor', item.get('current_floor', item.get('floor', 0)))),
            door=str(item.get('door', 'closed')),
            status=str(item.get('status', 'idle')),
            occupied_by=str(item.get('occupied_by') or ''),
            travel_time_per_floor_s=float(item.get('travel_time_per_floor_s', 2.0)),
        )
        return elevator

    def _nearest_node_id(self, x: float, y: float, *, layer: Optional[int] = None) -> Optional[str]:
        best_id = None
        best_d = 999999.0
        for node in self.graph.nodes.values():
            if layer is not None and node.layer != int(layer):
                continue
            d = (node.x - x) ** 2 + (node.y - y) ** 2
            if d < best_d:
                best_d = d
                best_id = node.node_id
        return best_id

    def handle_elevator_api_command(self, elevator_id: str, command: str, body: dict) -> dict:
        with self.lock:
            elevator = self.get_elevator_by_id(elevator_id)
            if elevator is None:
                raise KeyError(f'Elevator {elevator_id} not found')

            job_id = str(body.get('job_id', '')).strip()
            if command == 'call':
                if 'floor' not in body:
                    raise ValueError('floor is required')
                response = elevator.call(job_id=job_id, floor=int(body['floor']))
            elif command == 'open-door':
                elevator.open_door(job_id=job_id)
                self._capture_agv_in_elevator(elevator, body.get('agv_id'))
                response = elevator.build_state()
            elif command == 'close-door':
                self._capture_agv_in_elevator(elevator, body.get('agv_id'))
                response = elevator.close_door(job_id=job_id)
            elif command == 'go':
                if 'target_floor' not in body:
                    raise ValueError('target_floor is required')
                response = elevator.go(job_id=job_id, target_floor=int(body['target_floor']))
            elif command == 'release':
                self._release_agv_from_elevator(elevator)
                response = elevator.release(job_id=job_id)
            else:
                raise ValueError(f'Unsupported elevator command: {command}')

            return response

    def elevator_api_state(self, elevator_id: Optional[str]) -> dict | list[dict]:
        with self.lock:
            if elevator_id is None:
                return [elevator.build_state() for elevator in self.elevators]
            elevator = self.get_elevator_by_id(elevator_id)
            if elevator is None:
                raise KeyError(f'Elevator {elevator_id} not found')
            return elevator.build_state()

    def _capture_agv_in_elevator(self, elevator: ElevatorAgent, requested_agv_id: object = None) -> None:
        if elevator.occupied_by:
            return
        agv = self.get_agv_by_id(str(requested_agv_id)) if requested_agv_id else None
        if agv is None:
            agv = self._nearest_agv_at_elevator(elevator)
        if agv is None:
            return
        elevator.set_occupied_by(agv.agv_id)
        agv.velocity = Velocity2D()
        agv.paused = True
        agv.publish_state()
        elevator.publish_state()

    def _release_agv_from_elevator(self, elevator: ElevatorAgent) -> None:
        agv = self.get_agv_by_id(elevator.occupied_by) if elevator.occupied_by else None
        if agv:
            agv.paused = False
            agv.publish_state()

    def _transfer_occupied_agv_to_elevator_floor(self, elevator: ElevatorAgent) -> None:
        agv = self.get_agv_by_id(elevator.occupied_by) if elevator.occupied_by else None
        if agv is None:
            return
        node_id = elevator.floor_node(elevator.current_floor)
        if node_id in self.graph.nodes:
            node = self.graph.nodes[node_id]
            agv.pose.x = node.x
            agv.pose.y = node.y
            agv.state_pose.x = node.x
            agv.state_pose.y = node.y
            agv.state_pose.theta = agv.pose.theta
            agv.last_node_id = node.node_id
            agv.layer = node.layer
        else:
            agv.layer = elevator.current_floor
        agv.velocity = Velocity2D()
        agv.paused = True
        agv.publish_state()

    def _nearest_agv_at_elevator(self, elevator: ElevatorAgent) -> Optional[AGVAgent]:
        node_id = elevator.floor_node(elevator.current_floor)
        node = self.graph.nodes.get(node_id or '')
        if node is None:
            return None
        best_agv = None
        best_d = 999999.0
        for agv in self.agvs:
            if agv.layer != node.layer:
                continue
            d = math.hypot(agv.pose.x - node.x, agv.pose.y - node.y)
            if d < best_d:
                best_d = d
                best_agv = agv
        return best_agv if best_d <= 0.75 else None

    def _start_elevator_api(self) -> None:
        api_cfg = self.config.get('api', {})
        if not bool(api_cfg.get('enabled', True)):
            return
        host = str(api_cfg.get('host', '127.0.0.1'))
        port = int(api_cfg.get('port', 8088))
        self.elevator_api = ElevatorAPIServer(
            host=host,
            port=port,
            command_handler=self.handle_elevator_api_command,
            state_handler=self.elevator_api_state,
        )
        if not self.elevator_api.start():
            self.api_last_error = self.elevator_api.last_error

    def shutdown(self) -> None:
        if self.elevator_api:
            self.elevator_api.stop()
        for elevator in self.elevators:
            elevator.disconnect()
        for agv in self.agvs:
            agv.publish_offline_connection()
            agv.mqtt.disconnect()
