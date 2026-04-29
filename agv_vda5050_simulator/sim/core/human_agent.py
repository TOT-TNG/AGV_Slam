from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Optional

from sim.core.models import Pose2D
from sim.map.graph import Edge
from sim.map.graph import Graph
from sim.utils.geometry import clamp, heading_to, normalize_angle


@dataclass
class HumanAgent:
    human_id: str
    graph: Graph
    pose: Pose2D
    radius: float = 0.22
    speed: float = 0.55
    color: tuple[int, int, int] = (230, 90, 85)
    paused: bool = False
    layer: int = 0
    target_x: float = field(init=False)
    target_y: float = field(init=False)
    wait_time: float = field(default=0.0, init=False)
    current_node_id: Optional[str] = field(default=None, init=False)
    previous_node_id: Optional[str] = field(default=None, init=False)
    target_node_id: Optional[str] = field(default=None, init=False)
    route_points: list[tuple[float, float]] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        self.pose.x = clamp(self.pose.x, 0.0, self.graph.width_m)
        self.pose.y = clamp(self.pose.y, 0.0, self.graph.height_m)
        self.graph.ensure_layer(self.layer)
        self._snap_to_nearest_node()
        self.target_x = self.pose.x
        self.target_y = self.pose.y
        self.pick_new_target()

    def update(self, dt: float) -> None:
        if self.paused:
            return

        if self.wait_time > 0.0:
            self.wait_time = max(0.0, self.wait_time - dt)
            return

        dx = self.target_x - self.pose.x
        dy = self.target_y - self.pose.y
        dist = math.hypot(dx, dy)
        if dist <= 0.04:
            self.pose.x = self.target_x
            self.pose.y = self.target_y
            if self.route_points:
                self._advance_route_point()
            else:
                self.current_node_id = self.target_node_id or self._nearest_node_id(self.pose.x, self.pose.y)
                self.target_node_id = None
                self.wait_time = random.uniform(0.2, 1.4)
                self.pick_new_target()
            return

        self.pose.theta = normalize_angle(heading_to((self.pose.x, self.pose.y), (self.target_x, self.target_y)))
        step = min(dist, self.speed * dt)
        self.pose.x = clamp(self.pose.x + dx / dist * step, 0.0, self.graph.width_m)
        self.pose.y = clamp(self.pose.y + dy / dist * step, 0.0, self.graph.height_m)

    def pick_new_target(self) -> None:
        if self.graph.nodes:
            self._pick_graph_target()
            return

        margin = min(max(self.radius, 0.05), max(self.graph.width_m, self.graph.height_m) / 4.0)
        min_x = margin if self.graph.width_m > margin * 2.0 else 0.0
        max_x = self.graph.width_m - margin if self.graph.width_m > margin * 2.0 else self.graph.width_m
        min_y = margin if self.graph.height_m > margin * 2.0 else 0.0
        max_y = self.graph.height_m - margin if self.graph.height_m > margin * 2.0 else self.graph.height_m
        self.target_x = random.uniform(min_x, max_x)
        self.target_y = random.uniform(min_y, max_y)

    def place(self, x: float, y: float) -> None:
        self.pose.x = clamp(x, 0.0, self.graph.width_m)
        self.pose.y = clamp(y, 0.0, self.graph.height_m)
        self._snap_to_nearest_node()
        self.route_points.clear()
        self.target_node_id = None
        self.target_x = self.pose.x
        self.target_y = self.pose.y
        self.wait_time = 0.2

    def _pick_graph_target(self) -> None:
        if self.current_node_id not in self.graph.nodes:
            self._snap_to_nearest_node()
        if self.current_node_id not in self.graph.nodes:
            return

        neighbors = [
            node_id
            for node_id in self.graph.adjacency.get(self.current_node_id, [])
            if self.graph.nodes[node_id].layer == self.layer
        ]
        if self.previous_node_id in neighbors and len(neighbors) > 1:
            neighbors.remove(self.previous_node_id)
        if not neighbors:
            self.target_x = self.pose.x
            self.target_y = self.pose.y
            return

        next_node_id = random.choice(neighbors)
        self.previous_node_id = self.current_node_id
        self.target_node_id = next_node_id
        edge = self.graph.find_edge(self.current_node_id, next_node_id)
        if edge and edge.edge_type == 'bezier':
            self.route_points = self._bezier_route_points(edge, self.current_node_id, next_node_id)
        else:
            node = self.graph.get_node(next_node_id)
            self.route_points = [(node.x, node.y)]
        self._advance_route_point()

    def _advance_route_point(self) -> None:
        if not self.route_points:
            return
        self.target_x, self.target_y = self.route_points.pop(0)

    def _snap_to_nearest_node(self) -> None:
        node_id = self._nearest_node_id(self.pose.x, self.pose.y)
        if node_id is None:
            return
        node = self.graph.get_node(node_id)
        self.pose.x = node.x
        self.pose.y = node.y
        self.layer = node.layer
        self.current_node_id = node_id
        self.previous_node_id = None

    def _nearest_node_id(self, x: float, y: float) -> Optional[str]:
        best_id = None
        best_d = 999999.0
        for node in self.graph.nodes.values():
            if node.layer != self.layer:
                continue
            d = (node.x - x) ** 2 + (node.y - y) ** 2
            if d < best_d:
                best_d = d
                best_id = node.node_id
        return best_id

    def _bezier_route_points(self, edge: Edge, from_node_id: str, to_node_id: str) -> list[tuple[float, float]]:
        p0, p1, p2, p3 = self._bezier_points(edge, from_node_id, to_node_id)
        points = []
        for idx in range(1, 17):
            t = idx / 16.0
            inv = 1.0 - t
            x = inv ** 3 * p0[0] + 3.0 * inv * inv * t * p1[0] + 3.0 * inv * t * t * p2[0] + t ** 3 * p3[0]
            y = inv ** 3 * p0[1] + 3.0 * inv * inv * t * p1[1] + 3.0 * inv * t * t * p2[1] + t ** 3 * p3[1]
            points.append((x, y))
        return points

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
