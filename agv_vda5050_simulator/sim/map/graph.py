from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(slots=True)
class Node:
    node_id: str
    x: float
    y: float
    node_type: str = 'intersection'
    layer: int = 0


@dataclass(slots=True)
class Edge:
    edge_id: str
    from_node: str
    to_node: str
    bidirectional: bool = True
    max_speed: Optional[float] = None
    edge_type: str = 'line'
    control1_x: Optional[float] = None
    control1_y: Optional[float] = None
    control2_x: Optional[float] = None
    control2_y: Optional[float] = None
    layer: int = 0


@dataclass(slots=True)
class MapLayer:
    layer: int
    name: str
    background: Optional[str] = None


@dataclass
class Graph:
    map_name: str
    width_m: float
    height_m: float
    map_id: Optional[str] = None
    background: Optional[str] = None
    nodes: Dict[str, Node] = field(default_factory=dict)
    edges: Dict[str, Edge] = field(default_factory=dict)
    adjacency: Dict[str, List[str]] = field(default_factory=dict)
    edge_lookup: Dict[tuple[str, str], Edge] = field(default_factory=dict)
    layers: Dict[int, MapLayer] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.ensure_layer(0)

    def get_node(self, node_id: str) -> Node:
        return self.nodes[node_id]

    def rebuild_adjacency(self) -> None:
        self.adjacency = {node_id: [] for node_id in self.nodes}
        self.edge_lookup.clear()
        for edge in self.edges.values():
            self.adjacency.setdefault(edge.from_node, []).append(edge.to_node)
            self.edge_lookup[(edge.from_node, edge.to_node)] = edge
            if edge.bidirectional:
                self.adjacency.setdefault(edge.to_node, []).append(edge.from_node)
                self.edge_lookup[(edge.to_node, edge.from_node)] = edge

    def find_edge(self, from_node: str, to_node: str) -> Optional[Edge]:
        return self.edge_lookup.get((from_node, to_node))

    def ensure_layer(self, layer: int, *, name: Optional[str] = None, background: Optional[str] = None) -> MapLayer:
        layer = int(layer)
        existing = self.layers.get(layer)
        if existing:
            if name:
                existing.name = name
            if background:
                existing.background = background
            return existing
        item = MapLayer(layer=layer, name=name or f'Floor {layer}', background=background)
        self.layers[layer] = item
        return item

    def layer_ids(self) -> list[int]:
        ids = set(self.layers)
        ids.update(node.layer for node in self.nodes.values())
        ids.update(edge.layer for edge in self.edges.values())
        return sorted(ids)

    def layer_name(self, layer: int) -> str:
        item = self.layers.get(int(layer))
        return item.name if item else f'Floor {int(layer)}'

    def next_layer_id(self) -> int:
        ids = self.layer_ids()
        return (max(ids) + 1) if ids else 0

    def layer_map_name(self, layer: int) -> str:
        base_name = self.map_id or self.map_name
        if int(layer) == 0:
            return base_name
        return f'{base_name}_L{int(layer)}'

    def add_node(self, node_id: str, x: float, y: float, node_type: str = 'intersection', layer: int = 0) -> Node:
        if node_id in self.nodes:
            raise ValueError(f'Node {node_id} already exists')
        layer = int(layer)
        self.ensure_layer(layer)
        node = Node(node_id=node_id, x=float(x), y=float(y), node_type=node_type, layer=layer)
        self.nodes[node_id] = node
        self.adjacency.setdefault(node_id, [])
        return node

    def move_node(self, node_id: str, x: float, y: float) -> None:
        node = self.nodes[node_id]
        node.x = float(max(0.0, min(self.width_m, x)))
        node.y = float(max(0.0, min(self.height_m, y)))

    def delete_node(self, node_id: str) -> None:
        if node_id not in self.nodes:
            return
        del self.nodes[node_id]
        edge_ids = [eid for eid, edge in self.edges.items() if edge.from_node == node_id or edge.to_node == node_id]
        for eid in edge_ids:
            self.edges.pop(eid, None)
        self.rebuild_adjacency()

    def add_edge(
        self,
        edge_id: str,
        from_node: str,
        to_node: str,
        *,
        bidirectional: bool = True,
        max_speed: Optional[float] = None,
        edge_type: str = 'line',
        control1_x: Optional[float] = None,
        control1_y: Optional[float] = None,
        control2_x: Optional[float] = None,
        control2_y: Optional[float] = None,
        layer: Optional[int] = None,
    ) -> Edge:
        if edge_id in self.edges:
            raise ValueError(f'Edge {edge_id} already exists')
        if from_node not in self.nodes or to_node not in self.nodes:
            raise ValueError('Edge endpoints must exist in the graph')
        if from_node == to_node:
            raise ValueError('Self-loop edges are not supported')
        from_layer = self.nodes[from_node].layer
        to_layer = self.nodes[to_node].layer
        edge_layer = from_layer if layer is None else int(layer)
        if from_layer != to_layer:
            raise ValueError('Edges must connect nodes on the same layer')
        if edge_layer != from_layer:
            raise ValueError('Edge layer must match its endpoint layer')
        if self.find_edge(from_node, to_node):
            raise ValueError('An edge already exists between these nodes')
        normalized_type = edge_type.lower().strip()
        if normalized_type not in {'line', 'bezier'}:
            raise ValueError('Edge type must be line or bezier')
        if normalized_type == 'bezier' and (
            control1_x is None or control1_y is None or control2_x is None or control2_y is None
        ):
            (control1_x, control1_y), (control2_x, control2_y) = self.default_bezier_controls(from_node, to_node)
        edge = Edge(
            edge_id=edge_id,
            from_node=from_node,
            to_node=to_node,
            bidirectional=bidirectional,
            max_speed=max_speed,
            edge_type=normalized_type,
            control1_x=float(control1_x) if control1_x is not None else None,
            control1_y=float(control1_y) if control1_y is not None else None,
            control2_x=float(control2_x) if control2_x is not None else None,
            control2_y=float(control2_y) if control2_y is not None else None,
            layer=edge_layer,
        )
        self.edges[edge_id] = edge
        self.rebuild_adjacency()
        return edge

    def default_bezier_controls(self, from_node: str, to_node: str) -> tuple[tuple[float, float], tuple[float, float]]:
        a = self.nodes[from_node]
        b = self.nodes[to_node]
        dx = b.x - a.x
        dy = b.y - a.y
        length = (dx * dx + dy * dy) ** 0.5
        if length <= 1e-9:
            return (a.x, a.y), (b.x, b.y)
        offset = min(max(length * 0.25, 0.6), 2.5)
        nx = -dy / length
        ny = dx / length
        return (
            (
                max(0.0, min(self.width_m, a.x + dx / 3.0 + nx * offset)),
                max(0.0, min(self.height_m, a.y + dy / 3.0 + ny * offset)),
            ),
            (
                max(0.0, min(self.width_m, a.x + 2.0 * dx / 3.0 + nx * offset)),
                max(0.0, min(self.height_m, a.y + 2.0 * dy / 3.0 + ny * offset)),
            ),
        )

    def default_bezier_control(self, from_node: str, to_node: str) -> tuple[float, float]:
        c1, c2 = self.default_bezier_controls(from_node, to_node)
        return (c1[0] + c2[0]) / 2.0, (c1[1] + c2[1]) / 2.0

    def delete_edge(self, edge_id: str) -> None:
        self.edges.pop(edge_id, None)
        self.rebuild_adjacency()

    def toggle_edge_direction(self, edge_id: str) -> None:
        edge = self.edges[edge_id]
        edge.bidirectional = not edge.bidirectional
        self.rebuild_adjacency()

    def next_node_id(self, prefix: str = 'N') -> str:
        index = 1
        while f'{prefix}{index}' in self.nodes:
            index += 1
        return f'{prefix}{index}'

    def next_edge_id(self, prefix: str = 'E') -> str:
        index = 1
        while f'{prefix}{index}' in self.edges:
            index += 1
        return f'{prefix}{index}'

    def to_dict(self) -> dict:
        line_table = []
        bezier_table = []
        for edge in sorted(self.edges.values(), key=lambda e: e.edge_id):
            item = {
                'edge_id': edge.edge_id,
                'from_node': edge.from_node,
                'to_node': edge.to_node,
                'bidirectional': edge.bidirectional,
                'layer': edge.layer,
                **({'max_speed': edge.max_speed} if edge.max_speed is not None else {}),
            }
            if edge.edge_type == 'bezier':
                control1_x = edge.control1_x
                control1_y = edge.control1_y
                control2_x = edge.control2_x
                control2_y = edge.control2_y
                if control1_x is None or control1_y is None or control2_x is None or control2_y is None:
                    (control1_x, control1_y), (control2_x, control2_y) = self.default_bezier_controls(
                        edge.from_node,
                        edge.to_node,
                    )
                item.update({
                    'control1_x': round(float(control1_x), 3),
                    'control1_y': round(float(control1_y), 3),
                    'control2_x': round(float(control2_x), 3),
                    'control2_y': round(float(control2_y), 3),
                })
                bezier_table.append(item)
            else:
                line_table.append(item)

        return {
            'map_name': self.map_name,
            'width_m': self.width_m,
            'height_m': self.height_m,
            **({'background': self.background} if self.background else {}),
            'layers': [
                {
                    'layer': layer.layer,
                    'name': layer.name,
                    **({'background': layer.background} if layer.background else {}),
                }
                for layer in sorted(self.layers.values(), key=lambda item: item.layer)
            ],
            'node_table': [
                {
                    'node_id': node.node_id,
                    'x': round(node.x, 3),
                    'y': round(node.y, 3),
                    'node_type': node.node_type,
                    'layer': node.layer,
                }
                for node in sorted(self.nodes.values(), key=lambda n: n.node_id)
            ],
            'line_table': line_table,
            'bezier_table': bezier_table,
        }
