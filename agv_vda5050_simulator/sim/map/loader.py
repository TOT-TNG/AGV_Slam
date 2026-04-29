from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sim.map.graph import Edge, Graph, Node


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def load_graph(path: Path) -> Graph:
    data = load_json(path)
    background = data.get('background', data.get('slam_map'))
    graph = Graph(
        map_name=data['map_name'],
        width_m=float(data['width_m']),
        height_m=float(data['height_m']),
        map_id=str(data['map_id']) if data.get('map_id') else None,
        background=str(background) if background else None,
    )
    _load_layer_metadata(graph, data)

    node_items = _layered_items(data, 'node_table', 'nodes')
    for item in node_items:
        node_id = str(item.get('node_id', item.get('id')))
        layer = int(item.get('layer', item.get('floor', 0)))
        graph.ensure_layer(layer)
        graph.nodes[node_id] = Node(
            node_id=node_id,
            x=float(item['x']),
            y=float(item['y']),
            node_type=item.get('node_type', item.get('type', 'intersection')),
            layer=layer,
        )
        graph.adjacency.setdefault(node_id, [])

    line_items = _layered_items(data, 'line_table')
    bezier_items = _layered_items(data, 'bezier_table')
    if (line_items is None and bezier_items is None) or (not line_items and not bezier_items and _has_layered_key(data, 'edges')):
        edges = _layered_items(data, 'edges') or []
        line_items = [item for item in edges if item.get('edge_type', item.get('type', 'line')) != 'bezier']
        bezier_items = [item for item in edges if item.get('edge_type', item.get('type')) == 'bezier']

    for item in line_items or []:
        edge_id = str(item.get('edge_id', item.get('id')))
        from_node = str(item.get('from_node', item.get('from')))
        to_node = str(item.get('to_node', item.get('to')))
        layer = int(item.get('layer', graph.nodes[from_node].layer if from_node in graph.nodes else 0))
        edge = Edge(
            edge_id=edge_id,
            from_node=from_node,
            to_node=to_node,
            bidirectional=bool(item.get('bidirectional', True)),
            max_speed=item.get('max_speed'),
            edge_type='line',
            layer=layer,
        )
        graph.edges[edge.edge_id] = edge

    for item in bezier_items or []:
        edge_id = str(item.get('edge_id', item.get('id')))
        from_node = str(item.get('from_node', item.get('from')))
        to_node = str(item.get('to_node', item.get('to')))
        layer = int(item.get('layer', graph.nodes[from_node].layer if from_node in graph.nodes else 0))
        control = item.get('control_point', {})
        (default_c1x, default_c1y), (default_c2x, default_c2y) = graph.default_bezier_controls(from_node, to_node)
        if 'control_x' in item or 'control_y' in item or control:
            old_cx = float(item.get('control_x', control.get('x', graph.default_bezier_control(from_node, to_node)[0])))
            old_cy = float(item.get('control_y', control.get('y', graph.default_bezier_control(from_node, to_node)[1])))
            start = graph.nodes[from_node]
            end = graph.nodes[to_node]
            default_c1x = start.x + (old_cx - start.x) * 2.0 / 3.0
            default_c1y = start.y + (old_cy - start.y) * 2.0 / 3.0
            default_c2x = end.x + (old_cx - end.x) * 2.0 / 3.0
            default_c2y = end.y + (old_cy - end.y) * 2.0 / 3.0
        edge = Edge(
            edge_id=edge_id,
            from_node=from_node,
            to_node=to_node,
            bidirectional=bool(item.get('bidirectional', True)),
            max_speed=item.get('max_speed'),
            edge_type='bezier',
            control1_x=float(item.get('control1_x', default_c1x)),
            control1_y=float(item.get('control1_y', default_c1y)),
            control2_x=float(item.get('control2_x', default_c2x)),
            control2_y=float(item.get('control2_y', default_c2y)),
            layer=layer,
        )
        graph.edges[edge.edge_id] = edge

    graph.rebuild_adjacency()
    return graph


def _load_layer_metadata(graph: Graph, data: dict[str, Any]) -> None:
    for item in data.get('layers', []):
        if not isinstance(item, dict):
            continue
        layer = int(item.get('layer', item.get('floor', 0)))
        graph.ensure_layer(
            layer,
            name=str(item.get('name', item.get('map_name', f'Floor {layer}'))),
            background=str(item['background']) if item.get('background') else None,
        )


def _layered_items(data: dict[str, Any], primary_key: str, legacy_key: str | None = None) -> list[dict[str, Any]] | None:
    if primary_key in data:
        return list(data.get(primary_key) or [])
    if legacy_key and legacy_key in data:
        return list(data.get(legacy_key) or [])

    layers = data.get('layers')
    if not isinstance(layers, list):
        return None

    items: list[dict[str, Any]] = []
    for layer_item in layers:
        if not isinstance(layer_item, dict):
            continue
        raw_items = layer_item.get(primary_key)
        if raw_items is None and legacy_key:
            raw_items = layer_item.get(legacy_key)
        if raw_items is None:
            continue
        layer = int(layer_item.get('layer', layer_item.get('floor', 0)))
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            item = dict(raw)
            item.setdefault('layer', layer)
            items.append(item)
    return items


def _has_layered_key(data: dict[str, Any], key: str) -> bool:
    if key in data:
        return True
    layers = data.get('layers')
    return isinstance(layers, list) and any(isinstance(item, dict) and key in item for item in layers)
