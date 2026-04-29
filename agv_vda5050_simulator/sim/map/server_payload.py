from __future__ import annotations

import base64
import json
import math
import zlib
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from sim.map.graph import Edge, Graph, Node


def build_map_upload_payload(
    graph: Graph,
    *,
    background_path: Optional[Path],
    upload_config: dict[str, Any],
) -> dict[str, Any]:
    map_name = str(upload_config.get('name') or graph.map_name)
    map_identifier = upload_config.get('id')
    if map_identifier in (None, '', 0, '0'):
        map_identifier = upload_config.get('map_id')
    if map_identifier in (None, '', 0, '0'):
        map_identifier = graph.map_id
    if map_identifier in (None, ''):
        map_identifier = 0
    default_speed = float(upload_config.get('default_speed', 0.3))
    road_width = float(upload_config.get('road_width', 0.95))

    map_info = {
        'id': map_identifier,
        'name': map_name,
        'x': float(upload_config.get('x', upload_config.get('origin_x', 0.0))),
        'y': float(upload_config.get('y', upload_config.get('origin_y', 0.0))),
        'theta': float(upload_config.get('theta', 0.0)),
        'image': _read_image_base64(background_path),
        'modifytime': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'layer': int(upload_config.get('layer', 0)),
    }
    payload = {
        'robot_points': [_node_to_robot_point(node, map_name) for node in sorted(graph.nodes.values(), key=lambda n: n.node_id)],
        'robot_roads': _build_robot_roads(graph, map_name=map_name, default_speed=default_speed, road_width=road_width),
        'robot_benziers': _build_robot_benziers(graph, map_name=map_name, default_speed=default_speed, road_width=road_width),
        'robot_actions': [],
        'robot_code': [_node_to_robot_code(node, map_name) for node in sorted(graph.nodes.values(), key=lambda n: n.node_id)],
    }
    if bool(upload_config.get('wrap_map_info', True)):
        payload = {'map_info': map_info, **payload}
    else:
        payload = {**map_info, **payload}
    return payload


def upload_map_payload(url: str, payload: dict[str, Any], *, timeout_s: float = 10.0) -> tuple[int, str]:
    body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    request = Request(
        url,
        data=body,
        headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
        method='POST',
    )
    try:
        with urlopen(request, timeout=timeout_s) as response:
            response_body = response.read().decode('utf-8', errors='replace')
            return int(response.status), response_body
    except HTTPError as exc:
        response_body = exc.read().decode('utf-8', errors='replace')
        return int(exc.code), response_body


def _read_image_base64(path: Optional[Path]) -> str:
    if path is None or not path.exists():
        return ''
    return base64.b64encode(path.read_bytes()).decode('ascii')


def _node_to_robot_point(node: Node, map_name: str) -> dict[str, Any]:
    point_id = _server_point_id(node.node_id)
    return {
        'name_id': point_id,
        'x': float(node.x),
        'y': float(node.y),
        'theta': 0,
        'name': map_name,
        'type': _server_point_type(node.node_type),
        'zone': '',
        'action': None,
        'carrier': 0,
        'available': False,
        'accuracy': 0,
        'map': map_name,
    }


def _node_to_robot_code(node: Node, map_name: str) -> dict[str, Any]:
    point_id = _server_point_id(node.node_id)
    return {
        'id': _server_numeric_id(point_id),
        'code': point_id,
        'x': float(node.x),
        'y': float(node.y),
        'theta': 0,
        'map': map_name,
    }


def _build_robot_roads(graph: Graph, *, map_name: str, default_speed: float, road_width: float) -> list[dict[str, Any]]:
    roads: list[dict[str, Any]] = []
    for edge in sorted(graph.edges.values(), key=lambda e: e.edge_id):
        if edge.edge_type != 'line':
            continue
        roads.append(_edge_to_robot_road(graph, edge, edge.from_node, edge.to_node, map_name, default_speed, road_width))
        if edge.bidirectional:
            roads.append(_edge_to_robot_road(graph, edge, edge.to_node, edge.from_node, map_name, default_speed, road_width))
    return roads


def _build_robot_benziers(graph: Graph, *, map_name: str, default_speed: float, road_width: float) -> list[dict[str, Any]]:
    benziers: list[dict[str, Any]] = []
    for edge in sorted(graph.edges.values(), key=lambda e: e.edge_id):
        if edge.edge_type != 'bezier':
            continue
        benziers.append(_edge_to_robot_bezier(graph, edge, edge.from_node, edge.to_node, map_name, default_speed, road_width))
        if edge.bidirectional:
            benziers.append(_edge_to_robot_bezier(graph, edge, edge.to_node, edge.from_node, map_name, default_speed, road_width))
    return benziers


def _edge_to_robot_road(
    graph: Graph,
    edge: Edge,
    source_id: str,
    dest_id: str,
    map_name: str,
    default_speed: float,
    road_width: float,
) -> dict[str, Any]:
    source = graph.nodes[source_id]
    dest = graph.nodes[dest_id]
    return {
        'name': map_name,
        'point_start': [float(source.x), float(source.y)],
        'point_end': [float(dest.x), float(dest.y)],
        'width': road_width,
        'id_source': _server_point_id(source_id),
        'id_dest': _server_point_id(dest_id),
        'speed': float(edge.max_speed if edge.max_speed is not None else default_speed),
        'move_direction': 0,
        'map': map_name,
        'distance': math.hypot(dest.x - source.x, dest.y - source.y),
    }


def _edge_to_robot_bezier(
    graph: Graph,
    edge: Edge,
    source_id: str,
    dest_id: str,
    map_name: str,
    default_speed: float,
    road_width: float,
) -> dict[str, Any]:
    road = _edge_to_robot_road(graph, edge, source_id, dest_id, map_name, default_speed, road_width)
    c1, c2 = graph.default_bezier_controls(edge.from_node, edge.to_node)
    control1 = [float(edge.control1_x if edge.control1_x is not None else c1[0]), float(edge.control1_y if edge.control1_y is not None else c1[1])]
    control2 = [float(edge.control2_x if edge.control2_x is not None else c2[0]), float(edge.control2_y if edge.control2_y is not None else c2[1])]
    if source_id != edge.from_node:
        control1, control2 = control2, control1
    road.update({
        'control1': control1,
        'control2': control2,
    })
    return road


def _server_point_id(node_id: str) -> str:
    if len(node_id) > 1 and node_id[0].upper() == 'N' and node_id[1:].isdigit():
        return node_id[1:]
    return node_id


def _server_numeric_id(point_id: str) -> int:
    try:
        return int(point_id)
    except ValueError:
        return zlib.crc32(point_id.encode('utf-8')) % 1_000_000


def _server_point_type(node_type: str) -> int:
    return {
        'intersection': 0,
        'station': 1,
        'charger': 2,
        'dock': 3,
        'elevator': 4,
    }.get(node_type, 0)
