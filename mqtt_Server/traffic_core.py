from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from heapq import heappop, heappush
from math import atan2, hypot, pi
from typing import Dict, Iterable, List, Optional, Tuple
import threading
import time
import state_management as predictive_state


class HealthState(str, Enum):
    OK = "OK"
    WARNING = "WARNING"
    ERROR = "ERROR"
    OFFLINE = "OFFLINE"


class TrafficState(str, Enum):
    IDLE = "IDLE"
    MOVING = "MOVING"
    WAITING = "WAITING"
    BLOCKED = "BLOCKED"
    REROUTING = "REROUTING"
    STOPPED = "STOPPED"


class OccupancyType(str, Enum):
    NODE = "NODE"
    EDGE = "EDGE"
    ZONE = "ZONE"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class TrafficAction(str, Enum):
    PROCEED = "PROCEED"
    WAIT = "WAIT"
    SLOW_DOWN = "SLOW_DOWN"
    STOP = "STOP"
    REROUTE = "REROUTE"


class ConflictType(str, Enum):
    HEAD_ON = "HEAD_ON"
    SAME_DIRECTION_BLOCKAGE = "SAME_DIRECTION_BLOCKAGE"
    INTERSECTION_CONFLICT = "INTERSECTION_CONFLICT"
    LOCAL_BLOCKAGE = "LOCAL_BLOCKAGE"
    RESOURCE_RESERVATION_CONFLICT = "RESOURCE_RESERVATION_CONFLICT"
    DEADLOCK_LOOP = "DEADLOCK_LOOP"


class PlannerAlgorithm(str, Enum):
    ASTAR = "ASTAR"
    DIJKSTRA = "DIJKSTRA"


class RerouteStrategy(str, Enum):
    SPEED_ONLY = "SPEED_ONLY"
    LOCAL_REROUTE = "LOCAL_REROUTE"
    FULL_REROUTE = "FULL_REROUTE"


@dataclass(slots=True)
class Node:
    node_id: str
    x: float
    y: float
    zone_id: Optional[str] = None


@dataclass(slots=True)
class Edge:
    edge_id: str
    from_node: str
    to_node: str
    length: float
    max_speed: float
    zone_id: Optional[str] = None
    blocked: bool = False
    bidirectional: bool = False
    physical_edge_id: Optional[str] = None


@dataclass(slots=True)
class RouteSegment:
    edge_id: str
    from_node: str
    to_node: str
    planned_speed: Optional[float] = None


@dataclass(slots=True)
class PlannedRoute:
    route_id: str
    agv_id: str
    start_node: str
    goal_node: str
    segments: List[RouteSegment]
    route_version: int = 1
    reason: Optional[str] = None


@dataclass(slots=True)
class PlannerRequest:
    agv_id: str
    start_node: str
    goal_node: str
    blocked_edges: List[str] | None = None
    blocked_zones: List[str] | None = None
    hard_blocked_edges: List[str] | None = None
    hard_blocked_zones: List[str] | None = None
    avoid_edges: List[str] | None = None
    avoid_zones: List[str] | None = None
    preferred_max_speed: Optional[float] = None
    route_version: int = 1
    reason: Optional[str] = None
    algorithm: PlannerAlgorithm = PlannerAlgorithm.ASTAR


@dataclass(slots=True)
class RouteCandidate:
    node_path: List[str]
    edge_path: List[str]
    total_cost: float
    estimated_time: float


@dataclass(slots=True)
class PlannerResult:
    success: bool
    request: PlannerRequest
    route: Optional[PlannedRoute]
    total_cost: Optional[float]
    estimated_time: Optional[float]
    node_path: List[str]
    edge_path: List[str]
    message: str


@dataclass(slots=True)
class Telemetry:
    agv_id: str
    x: float
    y: float
    speed: float
    heading_deg: float
    timestamp: float
    health_state: HealthState = HealthState.OK
    traffic_state: TrafficState = TrafficState.IDLE


@dataclass(slots=True)
class AGVTrafficState:
    agv_id: str
    timestamp: float
    x: float
    y: float
    speed: float
    heading_deg: float
    current_node: Optional[str]
    current_edge: Optional[str]
    current_zone: Optional[str]
    offset_on_edge: Optional[float]
    route_id: Optional[str]
    route_progress_index: Optional[int]
    next_node: Optional[str]
    health_state: HealthState
    traffic_state: TrafficState
    last_reached_node: Optional[str] = None
    node_sequence_index: int = 0
    edge_sequence_index: int = 0


@dataclass(slots=True)
class TrafficOccupancy:
    agv_id: str
    resource_id: str
    occupancy_type: OccupancyType
    time_from: float
    time_to: float
    confidence: float
    physical_resource_id: Optional[str] = None
    route_progress_index: Optional[int] = None


@dataclass(slots=True)
class CollisionAlert:
    agv_id_1: str
    agv_id_2: str
    resource_id: str
    occupancy_type: OccupancyType
    overlap_from: float
    overlap_to: float
    risk_level: RiskLevel
    detail: str


@dataclass(slots=True)
class TrafficSnapshot:
    generated_at: float
    states: Dict[str, AGVTrafficState]
    occupancies: List[TrafficOccupancy]
    alerts: List[CollisionAlert]


@dataclass(slots=True)
class PriorityContext:
    agv_id: str
    delivering: bool = False
    delivery_completed: bool = False
    priority_boost: int = 0
    route_lock_order: int = 0


@dataclass(slots=True)
class ReservationClaim:
    agv_id: str
    edge_id: Optional[str]
    physical_edge_id: Optional[str]
    from_node: Optional[str]
    to_node: Optional[str]
    next_node: Optional[str]
    route_progress_index: Optional[int]
    last_reached_node: Optional[str]
    preview_nodes: List[str] = field(default_factory=list)
    preview_edges: List[str] = field(default_factory=list)
    eta_to_node_s: Dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class ConflictRecord:
    conflict_id: str
    conflict_type: ConflictType
    agv_ids: List[str]
    resource_id: str
    risk_level: RiskLevel
    detail: str


@dataclass(slots=True)
class TrafficDecision:
    agv_id: str
    action: TrafficAction
    reason: str
    target_speed: Optional[float] = None
    related_conflict_id: Optional[str] = None
    related_agv_id: Optional[str] = None


@dataclass(slots=True)
class RerouteRequest:
    agv_id: str
    reason: str
    avoid_edges: List[str]
    avoid_zones: List[str]
    related_conflict_id: Optional[str] = None


@dataclass(slots=True)
class ConflictManagementResult:
    conflicts: List[ConflictRecord]
    decisions: List[TrafficDecision]
    reroute_requests: List[RerouteRequest]


@dataclass(slots=True)
class SpeedProfile:
    agv_id: str
    target_speed: float
    reason: str


@dataclass(slots=True)
class DynamicReroutingPolicy:
    speed_reduction_factor: float = 0.6
    crawl_speed: float = 0.2
    stop_speed: float = 0.0
    prefer_speed_only_for_soft_conflict: bool = True
    use_full_reroute_for_deadlock: bool = True


@dataclass(slots=True)
class DynamicReroutingResult:
    agv_id: str
    success: bool
    strategy: RerouteStrategy
    reason: str
    route: Optional[PlannedRoute]
    planner_result: Optional[PlannerResult]
    speed_profile: Optional[SpeedProfile]
    message: str


@dataclass(slots=True)
class EngineUpdateResult:
    state: AGVTrafficState
    snapshot: TrafficSnapshot
    conflict_result: ConflictManagementResult
    decision: Optional[TrafficDecision]
    reroute_request: Optional[RerouteRequest]
    reroute_result: Optional[DynamicReroutingResult]


class TopologyMap:
    def __init__(self, nodes: Iterable[Node], edges: Iterable[Edge]) -> None:
        self.nodes: Dict[str, Node] = {node.node_id: node for node in nodes}
        self.edges: Dict[str, Edge] = {edge.edge_id: edge for edge in edges}
        self.outgoing: Dict[str, List[Edge]] = {node_id: [] for node_id in self.nodes}

        base_edges = list(self.edges.values())
        for edge in base_edges:
            self.outgoing.setdefault(edge.from_node, []).append(edge)
            if edge.bidirectional:
                reverse_edge = Edge(
                    edge_id=f"{edge.edge_id}__rev",
                    from_node=edge.to_node,
                    to_node=edge.from_node,
                    length=edge.length,
                    max_speed=edge.max_speed,
                    zone_id=edge.zone_id,
                    blocked=edge.blocked,
                    bidirectional=False,
                    physical_edge_id=edge.physical_edge_id or edge.edge_id,
                )
                self.edges[reverse_edge.edge_id] = reverse_edge
                self.outgoing.setdefault(reverse_edge.from_node, []).append(reverse_edge)

    def get_node(self, node_id: str) -> Node:
        return self.nodes[node_id]

    def get_edge(self, edge_id: str) -> Edge:
        return self.edges[edge_id]

    def get_outgoing_edges(self, node_id: str) -> List[Edge]:
        return self.outgoing.get(node_id, [])

    def euclidean_distance(self, from_node: str, to_node: str) -> float:
        a = self.get_node(from_node)
        b = self.get_node(to_node)
        return hypot(a.x - b.x, a.y - b.y)

    def nearest_node(self, x: float, y: float, max_distance: float = 0.75) -> Optional[Node]:
        nearest: Optional[Tuple[Node, float]] = None
        for node in self.nodes.values():
            distance = hypot(x - node.x, y - node.y)
            if nearest is None or distance < nearest[1]:
                nearest = (node, distance)
        if nearest is None:
            return None
        return nearest[0] if nearest[1] <= max_distance else None

    def edge_progress(self, x: float, y: float, edge: Edge) -> Optional[float]:
        start = self.get_node(edge.from_node)
        end = self.get_node(edge.to_node)
        vx = end.x - start.x
        vy = end.y - start.y
        seg_len_sq = vx * vx + vy * vy
        if seg_len_sq == 0:
            return None

        wx = x - start.x
        wy = y - start.y
        t = (wx * vx + wy * vy) / seg_len_sq
        if t < -0.15 or t > 1.15:
            return None

        proj_x = start.x + t * vx
        proj_y = start.y + t * vy
        if hypot(x - proj_x, y - proj_y) > 0.75:
            return None

        return min(1.0, max(0.0, t)) * edge.length

    def edge_projection_distance(self, x: float, y: float, edge: Edge) -> Optional[float]:
        start = self.get_node(edge.from_node)
        end = self.get_node(edge.to_node)
        vx = end.x - start.x
        vy = end.y - start.y
        seg_len_sq = vx * vx + vy * vy
        if seg_len_sq == 0:
            return None

        wx = x - start.x
        wy = y - start.y
        t = (wx * vx + wy * vy) / seg_len_sq
        if t < -0.15 or t > 1.15:
            return None

        proj_t = min(1.0, max(0.0, t))
        proj_x = start.x + proj_t * vx
        proj_y = start.y + proj_t * vy
        return hypot(x - proj_x, y - proj_y)


@dataclass(slots=True)
class PlannerCostPolicy:
    distance_weight: float = 1.0
    travel_time_weight: float = 2.0
    avoid_edge_penalty: float = 1000.0
    avoid_zone_penalty: float = 800.0
    blocked_penalty: float = 1_000_000.0
    low_speed_penalty_weight: float = 1.0


class CostModel:
    def __init__(self, policy: PlannerCostPolicy) -> None:
        self.policy = policy

    def edge_cost(
        self,
        edge: Edge,
        blocked_edges: set[str],
        blocked_zones: set[str],
        avoid_edges: set[str],
        avoid_zones: set[str],
        preferred_max_speed: Optional[float],
        blocked_physical_edges: Optional[set[str]] = None,
        avoid_physical_edges: Optional[set[str]] = None,
    ) -> float:
        cost = self.policy.distance_weight * edge.length
        effective_speed = edge.max_speed
        if preferred_max_speed is not None:
            effective_speed = min(effective_speed, preferred_max_speed)
        effective_speed = max(effective_speed, 0.1)
        cost += self.policy.travel_time_weight * (edge.length / effective_speed)
        cost += self.policy.low_speed_penalty_weight * (1.0 / effective_speed)

        physical_id = edge.physical_edge_id or edge.edge_id
        if (
            edge.blocked
            or edge.edge_id in blocked_edges
            or physical_id in (blocked_physical_edges or set())
            or (edge.zone_id and edge.zone_id in blocked_zones)
        ):
            cost += self.policy.blocked_penalty
        if edge.edge_id in avoid_edges or physical_id in (avoid_physical_edges or set()):
            cost += self.policy.avoid_edge_penalty
        if edge.zone_id and edge.zone_id in avoid_zones:
            cost += self.policy.avoid_zone_penalty
        return cost


class PathSearchEngine:
    def __init__(self, topology: TopologyMap, cost_model: CostModel) -> None:
        self.topology = topology
        self.cost_model = cost_model

    def find_path(self, request: PlannerRequest) -> RouteCandidate | None:
        if request.algorithm == PlannerAlgorithm.DIJKSTRA:
            return self._dijkstra(request)
        return self._astar(request)

    def _astar(self, request: PlannerRequest) -> RouteCandidate | None:
        start = request.start_node
        goal = request.goal_node
        blocked_edges = set(request.blocked_edges or [])
        blocked_zones = set(request.blocked_zones or [])
        hard_blocked_edges = set(request.hard_blocked_edges or [])
        hard_blocked_zones = set(request.hard_blocked_zones or [])
        avoid_edges = set(request.avoid_edges or [])
        avoid_zones = set(request.avoid_zones or [])
        blocked_physical_edges = {
            self.topology.get_edge(edge_id).physical_edge_id or edge_id
            for edge_id in blocked_edges
            if edge_id in self.topology.edges
        }
        hard_blocked_physical_edges = {
            self.topology.get_edge(edge_id).physical_edge_id or edge_id
            for edge_id in hard_blocked_edges
            if edge_id in self.topology.edges
        }
        avoid_physical_edges = {
            self.topology.get_edge(edge_id).physical_edge_id or edge_id
            for edge_id in avoid_edges
            if edge_id in self.topology.edges
        }

        open_heap: List[Tuple[float, float, str]] = []
        heappush(open_heap, (0.0, 0.0, start))
        came_from: Dict[str, Tuple[str, str]] = {}
        g_score: Dict[str, float] = {start: 0.0}
        eta_to_node: Dict[str, float] = {start: 0.0}
        visited: set[str] = set()

        while open_heap:
            _, current_cost, current_node = heappop(open_heap)
            if current_node in visited:
                continue
            visited.add(current_node)

            if current_node == goal:
                return self._build_candidate(came_from, start, goal, g_score[goal], eta_to_node[goal])

            for edge in self.topology.get_outgoing_edges(current_node):
                physical_id = edge.physical_edge_id or edge.edge_id
                if edge.edge_id in hard_blocked_edges or physical_id in hard_blocked_physical_edges:
                    continue
                if edge.zone_id and edge.zone_id in hard_blocked_zones:
                    continue
                if edge.blocked and (edge.edge_id in hard_blocked_edges or physical_id in hard_blocked_physical_edges):
                    continue
                next_node = edge.to_node
                step_cost = self.cost_model.edge_cost(
                    edge=edge,
                    blocked_edges=blocked_edges,
                    blocked_zones=blocked_zones,
                    avoid_edges=avoid_edges,
                    avoid_zones=avoid_zones,
                    preferred_max_speed=request.preferred_max_speed,
                    blocked_physical_edges=blocked_physical_edges,
                    avoid_physical_edges=avoid_physical_edges,
                )
                tentative = current_cost + step_cost
                if tentative < g_score.get(next_node, float("inf")):
                    came_from[next_node] = (current_node, edge.edge_id)
                    g_score[next_node] = tentative
                    speed = min(edge.max_speed, request.preferred_max_speed) if request.preferred_max_speed else edge.max_speed
                    speed = max(speed, 0.1)
                    eta_to_node[next_node] = eta_to_node[current_node] + (edge.length / speed)
                    heuristic = self.topology.euclidean_distance(next_node, goal)
                    heappush(open_heap, (tentative + heuristic, tentative, next_node))
        return None

    def _dijkstra(self, request: PlannerRequest) -> RouteCandidate | None:
        start = request.start_node
        goal = request.goal_node
        blocked_edges = set(request.blocked_edges or [])
        blocked_zones = set(request.blocked_zones or [])
        hard_blocked_edges = set(request.hard_blocked_edges or [])
        hard_blocked_zones = set(request.hard_blocked_zones or [])
        avoid_edges = set(request.avoid_edges or [])
        avoid_zones = set(request.avoid_zones or [])
        blocked_physical_edges = {
            self.topology.get_edge(edge_id).physical_edge_id or edge_id
            for edge_id in blocked_edges
            if edge_id in self.topology.edges
        }
        hard_blocked_physical_edges = {
            self.topology.get_edge(edge_id).physical_edge_id or edge_id
            for edge_id in hard_blocked_edges
            if edge_id in self.topology.edges
        }
        avoid_physical_edges = {
            self.topology.get_edge(edge_id).physical_edge_id or edge_id
            for edge_id in avoid_edges
            if edge_id in self.topology.edges
        }

        open_heap: List[Tuple[float, str]] = []
        heappush(open_heap, (0.0, start))
        came_from: Dict[str, Tuple[str, str]] = {}
        distance: Dict[str, float] = {start: 0.0}
        eta_to_node: Dict[str, float] = {start: 0.0}

        while open_heap:
            current_cost, current_node = heappop(open_heap)
            if current_node == goal:
                return self._build_candidate(came_from, start, goal, distance[goal], eta_to_node[goal])
            if current_cost > distance.get(current_node, float("inf")):
                continue

            for edge in self.topology.get_outgoing_edges(current_node):
                physical_id = edge.physical_edge_id or edge.edge_id
                if edge.edge_id in hard_blocked_edges or physical_id in hard_blocked_physical_edges:
                    continue
                if edge.zone_id and edge.zone_id in hard_blocked_zones:
                    continue
                if edge.blocked and (edge.edge_id in hard_blocked_edges or physical_id in hard_blocked_physical_edges):
                    continue
                next_node = edge.to_node
                step_cost = self.cost_model.edge_cost(
                    edge=edge,
                    blocked_edges=blocked_edges,
                    blocked_zones=blocked_zones,
                    avoid_edges=avoid_edges,
                    avoid_zones=avoid_zones,
                    preferred_max_speed=request.preferred_max_speed,
                    blocked_physical_edges=blocked_physical_edges,
                    avoid_physical_edges=avoid_physical_edges,
                )
                tentative = current_cost + step_cost
                if tentative < distance.get(next_node, float("inf")):
                    came_from[next_node] = (current_node, edge.edge_id)
                    distance[next_node] = tentative
                    speed = min(edge.max_speed, request.preferred_max_speed) if request.preferred_max_speed else edge.max_speed
                    speed = max(speed, 0.1)
                    eta_to_node[next_node] = eta_to_node[current_node] + (edge.length / speed)
                    heappush(open_heap, (tentative, next_node))
        return None

    @staticmethod
    def _build_candidate(
        came_from: Dict[str, Tuple[str, str]],
        start: str,
        goal: str,
        total_cost: float,
        estimated_time: float,
    ) -> RouteCandidate:
        node_path = [goal]
        edge_path: List[str] = []
        current = goal
        while current != start:
            previous_node, edge_id = came_from[current]
            edge_path.append(edge_id)
            node_path.append(previous_node)
            current = previous_node
        node_path.reverse()
        edge_path.reverse()
        return RouteCandidate(node_path=node_path, edge_path=edge_path, total_cost=total_cost, estimated_time=estimated_time)


class RouteBuilder:
    def __init__(self, topology: TopologyMap) -> None:
        self.topology = topology

    def build(self, request: PlannerRequest, candidate: RouteCandidate) -> PlannedRoute:
        segments: List[RouteSegment] = []
        for edge_id in candidate.edge_path:
            edge = self.topology.get_edge(edge_id)
            speed = edge.max_speed
            if request.preferred_max_speed is not None:
                speed = min(speed, request.preferred_max_speed)
            segments.append(
                RouteSegment(
                    edge_id=edge.edge_id,
                    from_node=edge.from_node,
                    to_node=edge.to_node,
                    planned_speed=max(speed, 0.1),
                )
            )
        return PlannedRoute(
            route_id=f"route_{request.agv_id}_v{request.route_version}",
            agv_id=request.agv_id,
            start_node=request.start_node,
            goal_node=request.goal_node,
            segments=segments,
            route_version=request.route_version,
            reason=request.reason,
        )


class PlannerService:
    def __init__(self, topology: TopologyMap, policy: PlannerCostPolicy | None = None) -> None:
        self.topology = topology
        self.policy = policy or PlannerCostPolicy()
        self.search_engine = PathSearchEngine(topology, CostModel(self.policy))
        self.route_builder = RouteBuilder(topology)

    def plan(self, request: PlannerRequest) -> PlannerResult:
        if request.start_node not in self.topology.nodes:
            return PlannerResult(False, request, None, None, None, [], [], f"Unknown start node: {request.start_node}")
        if request.goal_node not in self.topology.nodes:
            return PlannerResult(False, request, None, None, None, [], [], f"Unknown goal node: {request.goal_node}")
        if request.start_node == request.goal_node:
            route = PlannedRoute(
                route_id=f"route_{request.agv_id}_v{request.route_version}",
                agv_id=request.agv_id,
                start_node=request.start_node,
                goal_node=request.goal_node,
                segments=[],
                route_version=request.route_version,
                reason=request.reason,
            )
            return PlannerResult(True, request, route, 0.0, 0.0, [request.start_node], [], "AGV already at destination")

        candidate = self.search_engine.find_path(request)
        if candidate is None:
            return PlannerResult(False, request, None, None, None, [], [], "No feasible path found")

        route = self.route_builder.build(request, candidate)
        return PlannerResult(True, request, route, candidate.total_cost, candidate.estimated_time, candidate.node_path, candidate.edge_path, "Route planned successfully")


@dataclass(slots=True)
class _TrackedAgv:
    telemetry: Telemetry
    state: AGVTrafficState
    route: Optional[PlannedRoute] = None


class StateStore:
    def __init__(self) -> None:
        self._tracked: Dict[str, _TrackedAgv] = {}
        self._lock = threading.RLock()

    def upsert(self, telemetry: Telemetry, state: AGVTrafficState, route: Optional[PlannedRoute]) -> None:
        with self._lock:
            # Preserve existing route if new one is None (maintains route during state updates)
            existing = self._tracked.get(telemetry.agv_id)
            final_route = route if route is not None else (existing.route if existing else None)
            self._tracked[telemetry.agv_id] = _TrackedAgv(telemetry=telemetry, state=state, route=final_route)

    def all(self) -> List[_TrackedAgv]:
        with self._lock:
            return list(self._tracked.values())

    def get(self, agv_id: str) -> Optional[_TrackedAgv]:
        with self._lock:
            return self._tracked.get(agv_id)


class PositionTracker:
    def __init__(self, topology: TopologyMap, node_snap_distance: float = 0.75) -> None:
        self.topology = topology
        self.node_snap_distance = node_snap_distance
        self.edge_snap_distance = 0.9

    def locate(
        self,
        telemetry: Telemetry,
        route: Optional[PlannedRoute],
    ) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[float], Optional[int], Optional[str], Optional[str], int, int]:
        nearest_node = self.topology.nearest_node(telemetry.x, telemetry.y, self.node_snap_distance)

        if route and route.segments:
            best_edge_id: Optional[str] = None
            best_offset: Optional[float] = None
            best_progress_index: Optional[int] = None
            best_distance = float("inf")
            next_node: Optional[str] = None
            current_zone: Optional[str] = None
            last_reached_node: Optional[str] = None
            node_seq = 0
            edge_seq = 0

            for idx, segment in enumerate(route.segments):
                edge = self.topology.get_edge(segment.edge_id)
                offset = self.topology.edge_progress(telemetry.x, telemetry.y, edge)
                if offset is None:
                    continue

                start = self.topology.get_node(edge.from_node)
                end = self.topology.get_node(edge.to_node)
                vx = end.x - start.x
                vy = end.y - start.y
                seg_len_sq = vx * vx + vy * vy
                if seg_len_sq == 0:
                    continue
                t = ((telemetry.x - start.x) * vx + (telemetry.y - start.y) * vy) / seg_len_sq
                proj_x = start.x + max(0.0, min(1.0, t)) * vx
                proj_y = start.y + max(0.0, min(1.0, t)) * vy
                distance = hypot(telemetry.x - proj_x, telemetry.y - proj_y)

                if distance < best_distance:
                    best_distance = distance
                    best_edge_id = edge.edge_id
                    best_offset = offset
                    best_progress_index = idx
                    next_node = edge.to_node
                    current_zone = edge.zone_id
                    last_reached_node = edge.from_node if offset > 0.15 else None
                    node_seq = idx
                    edge_seq = idx

            if best_edge_id is not None:
                edge = self.topology.get_edge(best_edge_id)
                if best_offset is not None and best_offset >= max(0.0, edge.length - 0.15):
                    last_reached_node = edge.to_node
                    node_seq = (best_progress_index or 0) + 1
                    edge_seq = (best_progress_index or 0) + 1

            if nearest_node is not None:
                if best_edge_id is None:
                    inferred_progress: Optional[int] = None
                    inferred_next_node: Optional[str] = None
                    for idx, segment in enumerate(route.segments):
                        if segment.from_node == nearest_node.node_id:
                            inferred_progress = idx
                            inferred_next_node = segment.to_node
                            break
                        if segment.to_node == nearest_node.node_id:
                            inferred_progress = min(idx + 1, len(route.segments) - 1)
                    last_reached_node = nearest_node.node_id
                    return (
                        nearest_node.node_id,
                        None,
                        nearest_node.zone_id,
                        None,
                        inferred_progress,
                        inferred_next_node,
                        last_reached_node,
                        inferred_progress or 0,
                        inferred_progress or 0,
                    )
                current_node = None
                if best_offset is not None:
                    edge = self.topology.get_edge(best_edge_id)
                    snap_margin = min(0.25, max(0.1, edge.length * 0.15))
                    if best_offset <= snap_margin:
                        current_node = edge.from_node
                    elif best_offset >= max(0.0, edge.length - snap_margin):
                        current_node = edge.to_node
                return (
                    current_node,
                    best_edge_id,
                    current_zone or nearest_node.zone_id,
                    best_offset,
                    best_progress_index,
                    next_node,
                    last_reached_node,
                    node_seq,
                    edge_seq,
                )

            return (None, best_edge_id, current_zone, best_offset, best_progress_index, next_node, last_reached_node, node_seq, edge_seq)

        inferred = self._infer_edge_without_route(telemetry)
        if inferred is not None:
            return inferred

        if nearest_node is not None:
            return (nearest_node.node_id, None, nearest_node.zone_id, None, None, None, nearest_node.node_id, 0, 0)

        return (None, None, None, None, None, None, None, 0, 0)

    def _infer_edge_without_route(
        self,
        telemetry: Telemetry,
    ) -> Optional[Tuple[Optional[str], Optional[str], Optional[str], Optional[float], Optional[int], Optional[str], Optional[str], int, int]]:
        best_edge: Optional[Edge] = None
        best_offset: Optional[float] = None
        best_distance = float("inf")
        best_heading_error = float("inf")

        heading_rad = self._normalize_heading(telemetry.heading_deg)

        for edge in self.topology.edges.values():
            offset = self.topology.edge_progress(telemetry.x, telemetry.y, edge)
            if offset is None:
                continue
            distance = self.topology.edge_projection_distance(telemetry.x, telemetry.y, edge)
            if distance is None or distance > self.edge_snap_distance:
                continue
            heading_error = self._heading_error(heading_rad, edge)
            if (
                distance < best_distance - 1e-6
                or (abs(distance - best_distance) <= 0.05 and heading_error < best_heading_error)
            ):
                best_edge = edge
                best_offset = offset
                best_distance = distance
                best_heading_error = heading_error

        if best_edge is None or best_offset is None:
            return None

        current_node = None
        next_node = best_edge.to_node
        last_reached_node = best_edge.from_node
        snap_margin = min(0.25, max(0.1, best_edge.length * 0.15))

        if best_offset <= snap_margin:
            current_node = best_edge.from_node
            last_reached_node = best_edge.from_node
            next_node = best_edge.to_node
        elif best_offset >= max(0.0, best_edge.length - snap_margin):
            current_node = best_edge.to_node
            last_reached_node = best_edge.to_node
            next_node = None

        return (
            current_node,
            best_edge.edge_id,
            best_edge.zone_id,
            best_offset,
            0,
            next_node,
            last_reached_node,
            0,
            0,
        )

    @staticmethod
    def _normalize_heading(raw_heading: float) -> float:
        if -2 * pi - 0.1 <= raw_heading <= 2 * pi + 0.1:
            return raw_heading
        return raw_heading * pi / 180.0

    def _heading_error(self, heading_rad: float, edge: Edge) -> float:
        start = self.topology.get_node(edge.from_node)
        end = self.topology.get_node(edge.to_node)
        edge_heading = atan2(end.y - start.y, end.x - start.x)
        delta = abs((heading_rad - edge_heading + pi) % (2 * pi) - pi)
        return delta
    
class RouteProgressTracker:
    def update_state(
        self,
        telemetry: Telemetry,
        route: Optional[PlannedRoute],
        located: Tuple[Optional[str], Optional[str], Optional[str], Optional[float], Optional[int], Optional[str], Optional[str], int, int],
    ) -> AGVTrafficState:
        (
            current_node,
            current_edge,
            current_zone,
            offset_on_edge,
            route_progress_index,
            next_node,
            last_reached_node,
            node_sequence_index,
            edge_sequence_index,
        ) = located
        return AGVTrafficState(
            agv_id=telemetry.agv_id,
            timestamp=telemetry.timestamp,
            x=telemetry.x,
            y=telemetry.y,
            speed=telemetry.speed,
            heading_deg=telemetry.heading_deg,
            current_node=current_node,
            current_edge=current_edge,
            current_zone=current_zone,
            offset_on_edge=offset_on_edge,
            route_id=route.route_id if route else None,
            route_progress_index=route_progress_index,
            next_node=next_node,
            health_state=telemetry.health_state,
            traffic_state=telemetry.traffic_state,
            last_reached_node=last_reached_node,
            node_sequence_index=node_sequence_index,
            edge_sequence_index=edge_sequence_index,
        )


class OccupancyPredictor:
    def __init__(self, topology: TopologyMap, prediction_horizon_s: float = 8.0) -> None:
        self.topology = topology
        self.prediction_horizon_s = prediction_horizon_s

    def predict(self, state: AGVTrafficState, route: Optional[PlannedRoute]) -> List[TrafficOccupancy]:
        # Handle stationary AGV - lock down current position with high confidence
        if state.speed <= 0.01:
            now = state.timestamp
            occupancies: List[TrafficOccupancy] = []
            if state.current_edge:
                edge = self.topology.get_edge(state.current_edge)
                occupancies.append(
                    TrafficOccupancy(
                        agv_id=state.agv_id,
                        resource_id=state.current_edge,
                        occupancy_type=OccupancyType.EDGE,
                        time_from=now,
                        time_to=now + 5.0,  # longer hold for stopped AGVs
                        confidence=0.99,
                        physical_resource_id=edge.physical_edge_id or state.current_edge,
                        route_progress_index=state.route_progress_index,
                    )
                )
            if state.current_node:
                occupancies.append(
                    TrafficOccupancy(
                        agv_id=state.agv_id,
                        resource_id=state.current_node,
                        occupancy_type=OccupancyType.NODE,
                        time_from=now,
                        time_to=now + 5.0,  # longer hold for stopped AGVs
                        confidence=0.99,
                        physical_resource_id=state.current_node,
                        route_progress_index=state.route_progress_index,
                    )
                )
            if occupancies:
                return occupancies
            return []
        
        if route is None or state.route_progress_index is None:
            return self._predict_from_local_state(state)

        occupancies: List[TrafficOccupancy] = []
        remaining_horizon = self.prediction_horizon_s
        time_cursor = state.timestamp
        start_index = state.route_progress_index

        for idx in range(start_index, len(route.segments)):
            segment = route.segments[idx]
            edge = self.topology.get_edge(segment.edge_id)
            if edge.blocked:
                break

            speed = segment.planned_speed or min(max(state.speed, 0.1), edge.max_speed)
            edge_remaining = edge.length
            if idx == start_index and state.offset_on_edge is not None:
                edge_remaining = max(0.0, edge.length - state.offset_on_edge)

            travel_time = edge_remaining / max(speed, 0.1)
            if travel_time <= 0:
                continue

            allocated = min(travel_time, remaining_horizon)
            occupancies.append(
                TrafficOccupancy(
                    agv_id=state.agv_id,
                    resource_id=edge.edge_id,
                    occupancy_type=OccupancyType.EDGE,
                    time_from=time_cursor,
                    time_to=time_cursor + allocated,
                    confidence=max(0.4, 0.95 - (idx - start_index) * 0.1),
                    physical_resource_id=edge.physical_edge_id or edge.edge_id,
                    route_progress_index=idx,
                )
            )
            occupancies.append(
                TrafficOccupancy(
                    agv_id=state.agv_id,
                    resource_id=edge.to_node,
                    occupancy_type=OccupancyType.NODE,
                    time_from=max(time_cursor, time_cursor + allocated - 0.25),
                    time_to=time_cursor + allocated + 0.25,
                    confidence=max(0.4, 0.9 - (idx - start_index) * 0.1),
                    physical_resource_id=edge.to_node,
                    route_progress_index=idx,
                )
            )
            if edge.zone_id:
                occupancies.append(
                    TrafficOccupancy(
                        agv_id=state.agv_id,
                        resource_id=edge.zone_id,
                        occupancy_type=OccupancyType.ZONE,
                        time_from=time_cursor,
                        time_to=time_cursor + allocated,
                        confidence=max(0.35, 0.9 - (idx - start_index) * 0.1),
                        physical_resource_id=edge.zone_id,
                        route_progress_index=idx,
                    )
                )

            time_cursor += allocated
            remaining_horizon -= allocated
            if remaining_horizon <= 0:
                break

        return occupancies

    def _predict_from_local_state(self, state: AGVTrafficState) -> List[TrafficOccupancy]:
        if not state.current_edge:
            if state.current_node:
                now = state.timestamp
                return [
                    TrafficOccupancy(
                        agv_id=state.agv_id,
                        resource_id=state.current_node,
                        occupancy_type=OccupancyType.NODE,
                        time_from=now,
                        time_to=now + self.prediction_horizon_s,
                        confidence=0.7,
                        physical_resource_id=state.current_node,
                        route_progress_index=state.route_progress_index,
                    )
                ]
            return []

        now = state.timestamp
        edge = self.topology.get_edge(state.current_edge)
        occupancies: List[TrafficOccupancy] = [
            TrafficOccupancy(
                agv_id=state.agv_id,
                resource_id=edge.edge_id,
                occupancy_type=OccupancyType.EDGE,
                time_from=now,
                time_to=now + min(2.5, self.prediction_horizon_s),
                confidence=0.82,
                physical_resource_id=edge.physical_edge_id or edge.edge_id,
                route_progress_index=state.route_progress_index,
            )
        ]

        target_node = state.next_node or state.current_node or edge.to_node
        if target_node:
            occupancies.append(
                TrafficOccupancy(
                    agv_id=state.agv_id,
                    resource_id=target_node,
                    occupancy_type=OccupancyType.NODE,
                    time_from=now,
                    time_to=now + min(1.5, self.prediction_horizon_s),
                    confidence=0.7,
                    physical_resource_id=target_node,
                    route_progress_index=state.route_progress_index,
                )
            )
        if edge.zone_id:
            occupancies.append(
                TrafficOccupancy(
                    agv_id=state.agv_id,
                    resource_id=edge.zone_id,
                    occupancy_type=OccupancyType.ZONE,
                    time_from=now,
                    time_to=now + min(2.5, self.prediction_horizon_s),
                    confidence=0.65,
                    physical_resource_id=edge.zone_id,
                    route_progress_index=state.route_progress_index,
                )
            )
        return occupancies


class CollisionPredictor:
    def detect(self, occupancies: List[TrafficOccupancy]) -> List[CollisionAlert]:
        alerts: List[CollisionAlert] = []
        by_resource: Dict[Tuple[str, OccupancyType], List[TrafficOccupancy]] = {}

        for occupancy in occupancies:
            resource_key = occupancy.physical_resource_id or occupancy.resource_id
            by_resource.setdefault((resource_key, occupancy.occupancy_type), []).append(occupancy)

        for (resource_id, occupancy_type), items in by_resource.items():
            items = sorted(items, key=lambda item: (item.time_from, item.time_to))
            for index, left in enumerate(items):
                for right in items[index + 1 :]:
                    if left.agv_id == right.agv_id:
                        continue
                    overlap_from = max(left.time_from, right.time_from)
                    overlap_to = min(left.time_to, right.time_to)
                    if overlap_to <= overlap_from:
                        continue
                    overlap = overlap_to - overlap_from
                    alerts.append(
                        CollisionAlert(
                            agv_id_1=left.agv_id,
                            agv_id_2=right.agv_id,
                            resource_id=resource_id,
                            occupancy_type=occupancy_type,
                            overlap_from=overlap_from,
                            overlap_to=overlap_to,
                            risk_level=self._risk_from_overlap(overlap, occupancy_type, left.confidence, right.confidence),
                            detail=f"Predicted overlap {overlap:.2f}s on {occupancy_type.value} {resource_id}",
                        )
                    )

        return alerts

    @staticmethod
    def _risk_from_overlap(overlap_s: float, occupancy_type: OccupancyType, conf_a: float, conf_b: float) -> RiskLevel:
        weighted_overlap = overlap_s * min(conf_a, conf_b)
        if occupancy_type == OccupancyType.EDGE:
            if weighted_overlap >= 3.0:
                return RiskLevel.CRITICAL
            if weighted_overlap >= 1.5:
                return RiskLevel.HIGH
            if weighted_overlap >= 0.7:
                return RiskLevel.MEDIUM
            return RiskLevel.LOW
        if occupancy_type == OccupancyType.NODE:
            if weighted_overlap >= 1.0:
                return RiskLevel.HIGH
            if weighted_overlap >= 0.4:
                return RiskLevel.MEDIUM
            return RiskLevel.LOW
        if weighted_overlap >= 2.5:
            return RiskLevel.HIGH
        if weighted_overlap >= 1.0:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW


class StateManagementService:
    def __init__(self, topology: TopologyMap, prediction_horizon_s: float = 8.0) -> None:
        self.topology = topology
        self.store = StateStore()
        self.position_tracker = PositionTracker(topology)
        self.route_progress_tracker = RouteProgressTracker()
        self.occupancy_predictor = OccupancyPredictor(topology, prediction_horizon_s)
        self.collision_predictor = CollisionPredictor()

    def ingest_telemetry(self, telemetry: Telemetry, route: Optional[PlannedRoute] = None) -> AGVTrafficState:
        located = self.position_tracker.locate(telemetry, route)
        state = self.route_progress_tracker.update_state(telemetry, route, located)
        self.store.upsert(telemetry, state, route)
        return state

    def build_snapshot(self) -> TrafficSnapshot:
        states: Dict[str, AGVTrafficState] = {}
        occupancies: List[TrafficOccupancy] = []
        for tracked in self.store.all():
            states[tracked.state.agv_id] = tracked.state
            occupancies.extend(self.occupancy_predictor.predict(tracked.state, tracked.route))
        alerts = self.collision_predictor.detect(occupancies)
        return TrafficSnapshot(generated_at=time.time(), states=states, occupancies=occupancies, alerts=alerts)

    def get_state(self, agv_id: str) -> Optional[AGVTrafficState]:
        tracked = self.store.get(agv_id)
        return tracked.state if tracked is not None else None


class PriorityResolver:
    def rank(self, agv_id: str, context: Optional[PriorityContext], state: Optional[AGVTrafficState]) -> Tuple[int, int, str]:
        mission_rank = 1
        if context is not None:
            if context.delivering:
                mission_rank = 0
            elif context.delivery_completed:
                mission_rank = 2
        health_rank = 0 if state is None or state.health_state == HealthState.OK else 1
        boost = -(context.priority_boost if context is not None else 0)
        route_lock_rank = context.route_lock_order if context and context.route_lock_order > 0 else 10**9
        return mission_rank, health_rank + boost, route_lock_rank, agv_id

    def choose_winner(self, agv_a: str, agv_b: str, priority_contexts: Dict[str, PriorityContext], states: Dict[str, AGVTrafficState]) -> str:
        return agv_a if self.rank(agv_a, priority_contexts.get(agv_a), states.get(agv_a)) <= self.rank(agv_b, priority_contexts.get(agv_b), states.get(agv_b)) else agv_b


class ReservationArbiter:
    def __init__(self, topology: TopologyMap, priority_resolver: PriorityResolver) -> None:
        self._topology = topology
        self.priority_resolver = priority_resolver

    def build_claims(self, states: Dict[str, AGVTrafficState], routes: Dict[str, PlannedRoute]) -> Dict[str, ReservationClaim]:
        claims: Dict[str, ReservationClaim] = {}
        for agv_id, state in states.items():
            route = routes.get(agv_id)
            edge_id = state.current_edge
            physical_edge_id = self._normalize_physical(edge_id)
            from_node = None
            to_node = None
            next_node = state.next_node
            progress = state.route_progress_index
            preview_nodes: List[str] = []
            preview_edges: List[str] = []
            eta_to_node_s: Dict[str, float] = {}
            if route and progress is not None and 0 <= progress < len(route.segments):
                segment = route.segments[progress]
                edge_id = segment.edge_id
                physical_edge_id = self._normalize_physical(segment.edge_id)
                from_node = segment.from_node
                to_node = segment.to_node
                next_node = segment.to_node
                preview_segments = route.segments[progress : progress + 3]
                preview_edges = [item.edge_id for item in preview_segments]
                preview_nodes = [segment.from_node] + [item.to_node for item in preview_segments]
                eta_cursor = 0.0
                for idx, preview_segment in enumerate(preview_segments):
                    preview_edge = self._topology.get_edge(preview_segment.edge_id)
                    edge_speed = preview_segment.planned_speed or min(max(state.speed, 0.1), preview_edge.max_speed)
                    edge_speed = max(edge_speed, 0.1)
                    edge_remaining = preview_edge.length
                    if idx == 0 and state.current_edge == preview_edge.edge_id and state.offset_on_edge is not None:
                        edge_remaining = max(0.0, preview_edge.length - state.offset_on_edge)
                    eta_cursor += edge_remaining / edge_speed
                    eta_to_node_s[preview_segment.to_node] = eta_cursor
            elif edge_id and state.last_reached_node and state.next_node:
                from_node = state.last_reached_node
                to_node = state.next_node
                preview_edges = [edge_id]
                preview_nodes = [state.last_reached_node, state.next_node]
                edge = self._topology.get_edge(edge_id)
                speed = max(min(max(state.speed, 0.1), edge.max_speed), 0.1)
                remaining = edge.length
                if state.offset_on_edge is not None:
                    remaining = max(0.0, edge.length - state.offset_on_edge)
                eta_to_node_s[state.next_node] = remaining / speed
            claims[agv_id] = ReservationClaim(
                agv_id,
                edge_id,
                physical_edge_id,
                from_node,
                to_node,
                next_node,
                progress,
                state.last_reached_node,
                preview_nodes,
                preview_edges,
                eta_to_node_s,
            )
        return claims

    def arbitrate(
        self,
        states: Dict[str, AGVTrafficState],
        routes: Dict[str, PlannedRoute],
        priority_contexts: Dict[str, PriorityContext],
    ) -> Tuple[List[ConflictRecord], Dict[str, TrafficDecision], Dict[str, RerouteRequest]]:
        claims = self.build_claims(states, routes)
        conflicts: List[ConflictRecord] = []
        decisions: Dict[str, TrafficDecision] = {}
        reroutes: Dict[str, RerouteRequest] = {}

        current_node_owner: Dict[str, str] = {}
        for agv_id, state in states.items():
            if state.current_node and state.health_state == HealthState.OK:
                owner = current_node_owner.get(state.current_node)
                current_node_owner[state.current_node] = agv_id if owner is None else self.priority_resolver.choose_winner(owner, agv_id, priority_contexts, states)

        for node_id, owner in current_node_owner.items():
            decisions[owner] = TrafficDecision(owner, TrafficAction.PROCEED, f"Holding node {node_id}")

        by_node: Dict[str, List[str]] = {}
        for agv_id, claim in claims.items():
            if claim.next_node:
                by_node.setdefault(claim.next_node, []).append(agv_id)

        node_winner: Dict[str, str] = {}
        for node_id, agv_ids in by_node.items():
            winner = current_node_owner.get(node_id) or self._winner_for_node(node_id, agv_ids, claims, priority_contexts, states)
            node_winner[node_id] = winner
            decisions.setdefault(winner, TrafficDecision(winner, TrafficAction.PROCEED, f"Node reservation winner {node_id}", related_agv_id=self._first_other(agv_ids, winner)))
            for agv_id in agv_ids:
                if agv_id == winner:
                    continue
                loser_state = states.get(agv_id)
                loser_claim = claims.get(agv_id)
                conflict_id = f"node_{node_id}_{agv_id}"
                conflicts.append(
                    ConflictRecord(
                        conflict_id=conflict_id,
                        conflict_type=ConflictType.INTERSECTION_CONFLICT,
                        agv_ids=[winner, agv_id],
                        resource_id=node_id,
                        risk_level=RiskLevel.HIGH if len(agv_ids) > 2 or node_id in current_node_owner else RiskLevel.MEDIUM,
                        detail=f"Node {node_id} reserved by {winner}",
                    )
                )
                approaching_reserved_node = (
                    loser_state is not None
                    and loser_state.current_node != node_id
                    and loser_claim is not None
                    and loser_claim.next_node == node_id
                )
                if approaching_reserved_node:
                    decisions[agv_id] = TrafficDecision(
                        agv_id,
                        TrafficAction.REROUTE,
                        f"Reroute to avoid reserved node {node_id} owned by {winner}",
                        related_conflict_id=conflict_id,
                        related_agv_id=winner,
                    )
                    avoid_edges = [loser_claim.edge_id] if loser_claim and loser_claim.edge_id else []
                    reroutes[agv_id] = RerouteRequest(
                        agv_id=agv_id,
                        reason=f"NODE_AHEAD_{node_id}",
                        avoid_edges=avoid_edges,
                        avoid_zones=[],
                        related_conflict_id=conflict_id,
                    )
                else:
                    decisions[agv_id] = TrafficDecision(
                        agv_id,
                        TrafficAction.WAIT,
                        f"Wait for {winner} to clear node {node_id}",
                        related_conflict_id=conflict_id,
                        related_agv_id=winner,
                    )

        by_physical: Dict[str, List[str]] = {}
        for agv_id, claim in claims.items():
            if claim.physical_edge_id:
                by_physical.setdefault(claim.physical_edge_id, []).append(agv_id)

        for physical_id, agv_ids in by_physical.items():
            if len(agv_ids) <= 1:
                continue
            winner = self._winner_for_physical(physical_id, agv_ids, claims, priority_contexts, states)
            winner_claim = claims[winner]
            if winner_claim.next_node and node_winner.get(winner_claim.next_node) not in {None, winner}:
                winner = node_winner[winner_claim.next_node]
                winner_claim = claims[winner]

            decisions[winner] = TrafficDecision(winner, TrafficAction.PROCEED, f"Corridor winner {physical_id}", related_agv_id=self._first_other(agv_ids, winner))
            for agv_id in agv_ids:
                if agv_id == winner:
                    continue
                loser_claim = claims[agv_id]
                if loser_claim.next_node and node_winner.get(loser_claim.next_node) not in {None, agv_id}:
                    continue
                conflict_id = f"corridor_{physical_id}_{agv_id}"
                conflicts.append(
                    ConflictRecord(
                        conflict_id=conflict_id,
                        conflict_type=ConflictType.RESOURCE_RESERVATION_CONFLICT,
                        agv_ids=[winner, agv_id],
                        resource_id=physical_id,
                        risk_level=RiskLevel.HIGH,
                        detail=f"Physical corridor {physical_id} reserved by {winner}",
                    )
                )
                decisions[agv_id] = TrafficDecision(agv_id, TrafficAction.REROUTE, f"Yield corridor {physical_id} to {winner}", related_conflict_id=conflict_id, related_agv_id=winner)
                reroutes[agv_id] = RerouteRequest(agv_id, f"YIELD_{physical_id}", [loser_claim.edge_id] if loser_claim.edge_id else [], [], conflict_id)

        self._apply_head_on_resolution(claims, states, priority_contexts, conflicts, decisions, reroutes)
        self._apply_preview_node_resolution(
            claims,
            states,
            priority_contexts,
            current_node_owner,
            node_winner,
            conflicts,
            decisions,
            reroutes,
        )
        return conflicts, decisions, reroutes

    def _winner_from_group(self, agv_ids: List[str], priority_contexts: Dict[str, PriorityContext], states: Dict[str, AGVTrafficState]) -> str:
        winner = agv_ids[0]
        for candidate in agv_ids[1:]:
            winner = self.priority_resolver.choose_winner(winner, candidate, priority_contexts, states)
        return winner

    def _winner_for_node(
        self,
        node_id: str,
        agv_ids: List[str],
        claims: Dict[str, ReservationClaim],
        priority_contexts: Dict[str, PriorityContext],
        states: Dict[str, AGVTrafficState],
    ) -> str:
        return self._winner_by_eta(
            agv_ids,
            lambda agv_id: self._eta_to_node(node_id, claims.get(agv_id), states.get(agv_id)),
            priority_contexts,
            states,
        )

    def _winner_for_physical(
        self,
        physical_id: str,
        agv_ids: List[str],
        claims: Dict[str, ReservationClaim],
        priority_contexts: Dict[str, PriorityContext],
        states: Dict[str, AGVTrafficState],
    ) -> str:
        return self._winner_by_eta(
            agv_ids,
            lambda agv_id: self._eta_to_physical(physical_id, claims.get(agv_id), states.get(agv_id)),
            priority_contexts,
            states,
        )

    def _winner_by_eta(
        self,
        agv_ids: List[str],
        eta_getter,
        priority_contexts: Dict[str, PriorityContext],
        states: Dict[str, AGVTrafficState],
    ) -> str:
        winner = agv_ids[0]
        winner_eta = eta_getter(winner)
        for candidate in agv_ids[1:]:
            candidate_eta = eta_getter(candidate)
            if candidate_eta is not None and (winner_eta is None or candidate_eta < winner_eta - 0.25):
                winner = candidate
                winner_eta = candidate_eta
                continue
            if winner_eta is not None and candidate_eta is not None and abs(candidate_eta - winner_eta) <= 0.25:
                winner = self.priority_resolver.choose_winner(winner, candidate, priority_contexts, states)
                winner_eta = eta_getter(winner)
                continue
            if winner_eta is None and candidate_eta is None:
                winner = self.priority_resolver.choose_winner(winner, candidate, priority_contexts, states)
                winner_eta = eta_getter(winner)
        return winner

    @staticmethod
    def _eta_to_node(node_id: str, claim: Optional[ReservationClaim], state: Optional[AGVTrafficState]) -> Optional[float]:
        if claim is None or state is None:
            return None
        if state.current_node == node_id:
            return 0.0
        return claim.eta_to_node_s.get(node_id)

    @staticmethod
    def _eta_to_physical(physical_id: str, claim: Optional[ReservationClaim], state: Optional[AGVTrafficState]) -> Optional[float]:
        if claim is None or state is None or claim.physical_edge_id != physical_id:
            return None
        current_physical = None
        if state.current_edge:
            current_physical = state.current_edge[:-5] if state.current_edge.endswith("__rev") else state.current_edge
        if current_physical == physical_id:
            return 0.0
        if claim.next_node:
            return claim.eta_to_node_s.get(claim.next_node, 0.0)
        return 0.0

    @staticmethod
    def _normalize_physical(edge_id: Optional[str]) -> Optional[str]:
        if edge_id is None:
            return None
        return edge_id[:-5] if edge_id.endswith("__rev") else edge_id

    @staticmethod
    def _first_other(agv_ids: List[str], current: str) -> Optional[str]:
        for agv_id in agv_ids:
            if agv_id != current:
                return agv_id
        return None

    def _apply_head_on_resolution(
        self,
        claims: Dict[str, ReservationClaim],
        states: Dict[str, AGVTrafficState],
        priority_contexts: Dict[str, PriorityContext],
        conflicts: List[ConflictRecord],
        decisions: Dict[str, TrafficDecision],
        reroutes: Dict[str, RerouteRequest],
    ) -> None:
        agv_ids = list(claims.keys())
        for index, agv_a in enumerate(agv_ids):
            claim_a = claims[agv_a]
            if not claim_a.physical_edge_id or not claim_a.from_node or not claim_a.to_node:
                continue
            for agv_b in agv_ids[index + 1 :]:
                claim_b = claims[agv_b]
                if claim_b.physical_edge_id != claim_a.physical_edge_id:
                    continue
                if not claim_b.from_node or not claim_b.to_node:
                    continue
                if claim_a.from_node != claim_b.to_node or claim_a.to_node != claim_b.from_node:
                    continue
                winner = self._winner_for_physical(
                    claim_a.physical_edge_id,
                    [agv_a, agv_b],
                    claims,
                    priority_contexts,
                    states,
                )
                loser = agv_b if winner == agv_a else agv_a
                conflict_id = f"head_on_{claim_a.physical_edge_id}_{loser}"
                conflicts.append(
                    ConflictRecord(
                        conflict_id=conflict_id,
                        conflict_type=ConflictType.HEAD_ON,
                        agv_ids=[winner, loser],
                        resource_id=claim_a.physical_edge_id,
                        risk_level=RiskLevel.CRITICAL,
                        detail=f"Head-on conflict on physical edge {claim_a.physical_edge_id}: {winner} keeps corridor, {loser} yields",
                    )
                )
                decisions[winner] = TrafficDecision(
                    winner,
                    TrafficAction.PROCEED,
                    f"Head-on priority on corridor {claim_a.physical_edge_id}",
                    related_conflict_id=conflict_id,
                    related_agv_id=loser,
                )
                decisions[loser] = TrafficDecision(
                    loser,
                    TrafficAction.REROUTE,
                    f"Head-on reroute for corridor {claim_a.physical_edge_id}",
                    related_conflict_id=conflict_id,
                    related_agv_id=winner,
                )
                loser_claim = claims[loser]
                avoid_edges = []
                if loser_claim.edge_id:
                    avoid_edges.append(loser_claim.edge_id)
                reroutes[loser] = RerouteRequest(
                    agv_id=loser,
                    reason=f"HEAD_ON_{claim_a.physical_edge_id}",
                    avoid_edges=avoid_edges,
                    avoid_zones=[],
                    related_conflict_id=conflict_id,
                )

    def _apply_preview_node_resolution(
        self,
        claims: Dict[str, ReservationClaim],
        states: Dict[str, AGVTrafficState],
        priority_contexts: Dict[str, PriorityContext],
        current_node_owner: Dict[str, str],
        node_winner: Dict[str, str],
        conflicts: List[ConflictRecord],
        decisions: Dict[str, TrafficDecision],
        reroutes: Dict[str, RerouteRequest],
    ) -> None:
        node_contenders: Dict[str, List[Tuple[str, int]]] = {}
        for agv_id, claim in claims.items():
            for depth, node_id in enumerate(claim.preview_nodes[1:], start=1):
                if not node_id:
                    continue
                if depth > 3:
                    break
                node_contenders.setdefault(node_id, []).append((agv_id, depth))

        for node_id, contenders in node_contenders.items():
            if len(contenders) <= 1:
                continue
            agv_ids = [agv_id for agv_id, _ in contenders]
            winner = (
                current_node_owner.get(node_id)
                or node_winner.get(node_id)
                or self._winner_for_node(node_id, agv_ids, claims, priority_contexts, states)
            )
            for loser, depth in contenders:
                if loser == winner:
                    continue
                if depth > 2:
                    continue
                loser_claim = claims.get(loser)
                loser_state = states.get(loser)
                # Preview claims should not overturn a decision for the AGV's immediate next node.
                # Immediate-node ownership is already resolved in the earlier node reservation pass.
                if loser_claim is not None and loser_claim.next_node == node_id:
                    continue
                if loser_state is not None and loser_state.current_node == node_id:
                    continue
                existing = decisions.get(loser)
                if existing and existing.action in {TrafficAction.PROCEED, TrafficAction.WAIT}:
                    continue
                conflict_id = f"preview_node_{node_id}_{loser}"
                conflicts.append(
                    ConflictRecord(
                        conflict_id=conflict_id,
                        conflict_type=ConflictType.INTERSECTION_CONFLICT,
                        agv_ids=[winner, loser],
                        resource_id=node_id,
                        risk_level=RiskLevel.HIGH if depth == 1 else RiskLevel.MEDIUM,
                        detail=f"Preview node {node_id} reserved by {winner}; {loser} must yield before entering lookahead corridor",
                    )
                )
                avoid_edges = []
                if loser_claim is not None and loser_claim.preview_edges:
                    avoid_edges.append(loser_claim.preview_edges[0])
                decisions[loser] = TrafficDecision(
                    loser,
                    TrafficAction.REROUTE,
                    f"Preview reroute to avoid future reserved node {node_id} owned by {winner}",
                    related_conflict_id=conflict_id,
                    related_agv_id=winner,
                )
                reroutes[loser] = RerouteRequest(
                    agv_id=loser,
                    reason=f"PREVIEW_NODE_AHEAD_{node_id}",
                    avoid_edges=avoid_edges,
                    avoid_zones=[],
                    related_conflict_id=conflict_id,
                )


class AlertInterpreter:
    def build_conflicts(self, alerts: List[CollisionAlert], states: Dict[str, AGVTrafficState]) -> List[ConflictRecord]:
        conflicts: List[ConflictRecord] = []
        for index, alert in enumerate(alerts, start=1):
            conflict_type = ConflictType.RESOURCE_RESERVATION_CONFLICT
            if alert.occupancy_type == OccupancyType.NODE:
                conflict_type = ConflictType.INTERSECTION_CONFLICT
            elif alert.occupancy_type == OccupancyType.EDGE:
                state_a = states.get(alert.agv_id_1)
                state_b = states.get(alert.agv_id_2)
                if state_a and state_b and state_a.current_edge and state_b.current_edge and self._normalize_physical(state_a.current_edge) == self._normalize_physical(state_b.current_edge):
                    conflict_type = ConflictType.HEAD_ON
            conflicts.append(
                ConflictRecord(
                    conflict_id=f"alert_{index}_{alert.agv_id_1}_{alert.agv_id_2}",
                    conflict_type=conflict_type,
                    agv_ids=[alert.agv_id_1, alert.agv_id_2],
                    resource_id=alert.resource_id,
                    risk_level=alert.risk_level,
                    detail=alert.detail,
                )
            )
        return conflicts

    @staticmethod
    def _normalize_physical(edge_id: str) -> str:
        return edge_id[:-5] if edge_id.endswith("__rev") else edge_id


class ConflictManagementService:
    def __init__(self, topology: TopologyMap) -> None:
        self.priority_resolver = PriorityResolver()
        self.reservation_arbiter = ReservationArbiter(topology, self.priority_resolver)
        self.alert_interpreter = AlertInterpreter()

    def evaluate(
        self,
        states: Dict[str, AGVTrafficState],
        routes: Dict[str, PlannedRoute],
        alerts: List[CollisionAlert],
        priority_contexts: Optional[Dict[str, PriorityContext]] = None,
    ) -> ConflictManagementResult:
        priority_contexts = priority_contexts or {}
        resource_conflicts, decisions, reroutes = self.reservation_arbiter.arbitrate(states, routes, priority_contexts)
        alert_conflicts = self.alert_interpreter.build_conflicts(alerts, states)

        for conflict in alert_conflicts:
            if len(conflict.agv_ids) != 2:
                continue
            agv_a, agv_b = conflict.agv_ids
            winner = self.priority_resolver.choose_winner(agv_a, agv_b, priority_contexts, states)
            loser = agv_b if winner == agv_a else agv_a
            decisions.setdefault(winner, TrafficDecision(winner, TrafficAction.PROCEED, f"Priority over {conflict.conflict_type.value}", related_conflict_id=conflict.conflict_id, related_agv_id=loser))
            if loser not in decisions:
                action = TrafficAction.REROUTE if conflict.conflict_type in {ConflictType.HEAD_ON, ConflictType.RESOURCE_RESERVATION_CONFLICT} else TrafficAction.WAIT
                decisions[loser] = TrafficDecision(loser, action, f"Yield conflict {conflict.conflict_type.value} to {winner}", related_conflict_id=conflict.conflict_id, related_agv_id=winner)
                if action == TrafficAction.REROUTE:
                    loser_state = states.get(loser)
                    reroutes[loser] = RerouteRequest(
                        agv_id=loser,
                        reason=f"AVOID_{conflict.conflict_type.value}",
                        avoid_edges=[loser_state.current_edge] if loser_state and loser_state.current_edge else [],
                        avoid_zones=[loser_state.current_zone] if loser_state and loser_state.current_zone else [],
                        related_conflict_id=conflict.conflict_id,
                    )

        for agv_id, state in states.items():
            if state.health_state != HealthState.OK:
                decisions[agv_id] = TrafficDecision(agv_id, TrafficAction.STOP, "AGV health state is not OK")

        self._resolve_wait_cycles(states, priority_contexts, decisions, reroutes, alert_conflicts, resource_conflicts)

        return ConflictManagementResult(
            conflicts=self._dedup(resource_conflicts + alert_conflicts),
            decisions=list(decisions.values()),
            reroute_requests=list(reroutes.values()),
        )

    @staticmethod
    def _dedup(conflicts: List[ConflictRecord]) -> List[ConflictRecord]:
        seen = set()
        result: List[ConflictRecord] = []
        for conflict in conflicts:
            key = (conflict.conflict_type.value, tuple(sorted(conflict.agv_ids)), conflict.resource_id)
            if key in seen:
                continue
            seen.add(key)
            result.append(conflict)
        return result

    def _resolve_wait_cycles(
        self,
        states: Dict[str, AGVTrafficState],
        priority_contexts: Dict[str, PriorityContext],
        decisions: Dict[str, TrafficDecision],
        reroutes: Dict[str, RerouteRequest],
        alert_conflicts: List[ConflictRecord],
        resource_conflicts: List[ConflictRecord],
    ) -> None:
        wait_graph: Dict[str, str] = {}
        for agv_id, decision in decisions.items():
            if decision.action not in {TrafficAction.WAIT, TrafficAction.STOP, TrafficAction.REROUTE}:
                continue
            if decision.related_agv_id:
                wait_graph[agv_id] = decision.related_agv_id

        handled_pairs: set[Tuple[str, str]] = set()
        for agv_id, other_agv in wait_graph.items():
            reverse = wait_graph.get(other_agv)
            if reverse != agv_id:
                continue
            pair = tuple(sorted((agv_id, other_agv)))
            if pair in handled_pairs:
                continue
            handled_pairs.add(pair)

            winner = self.priority_resolver.choose_winner(agv_id, other_agv, priority_contexts, states)
            loser = other_agv if winner == agv_id else agv_id
            loser_state = states.get(loser)
            resource_id = loser_state.current_edge or loser_state.current_node or winner
            conflict_id = f"deadlock_{pair[0]}_{pair[1]}"
            deadlock_conflict = ConflictRecord(
                conflict_id=conflict_id,
                conflict_type=ConflictType.DEADLOCK_LOOP,
                agv_ids=[winner, loser],
                resource_id=resource_id,
                risk_level=RiskLevel.HIGH,
                detail=f"Mutual wait detected between {agv_id} and {other_agv}; {winner} gets priority",
            )
            alert_conflicts.append(deadlock_conflict)
            decisions[winner] = TrafficDecision(
                winner,
                TrafficAction.PROCEED,
                f"Deadlock priority over {loser}",
                related_conflict_id=conflict_id,
                related_agv_id=loser,
            )
            decisions[loser] = TrafficDecision(
                loser,
                TrafficAction.REROUTE,
                f"Deadlock resolution reroute for {winner}",
                related_conflict_id=conflict_id,
                related_agv_id=winner,
            )
            avoid_edges = [loser_state.current_edge] if loser_state and loser_state.current_edge else []
            avoid_zones = [loser_state.current_zone] if loser_state and loser_state.current_zone else []
            reroutes[loser] = RerouteRequest(
                agv_id=loser,
                reason="DEADLOCK_RESOLUTION",
                avoid_edges=avoid_edges,
                avoid_zones=avoid_zones,
                related_conflict_id=conflict_id,
            )


class RerouteTriggerAnalyzer:
    def __init__(self, policy: DynamicReroutingPolicy) -> None:
        self.policy = policy

    def choose_strategy(
        self,
        reroute_request: Optional[RerouteRequest],
        decision: Optional[TrafficDecision],
        blocked_edges: List[str],
        blocked_zones: List[str],
    ) -> RerouteStrategy:
        if reroute_request is not None:
            if reroute_request.reason in {"DEADLOCK", "DEADLOCK_RESOLUTION"} and self.policy.use_full_reroute_for_deadlock:
                return RerouteStrategy.FULL_REROUTE
            if reroute_request.avoid_edges or reroute_request.avoid_zones or blocked_edges or blocked_zones:
                return RerouteStrategy.LOCAL_REROUTE
            return RerouteStrategy.FULL_REROUTE

        if decision is not None:
            if decision.action in {TrafficAction.WAIT, TrafficAction.SLOW_DOWN} and self.policy.prefer_speed_only_for_soft_conflict:
                return RerouteStrategy.SPEED_ONLY
            if decision.action == TrafficAction.REROUTE:
                return RerouteStrategy.LOCAL_REROUTE if (blocked_edges or blocked_zones) else RerouteStrategy.FULL_REROUTE

        if blocked_edges or blocked_zones:
            return RerouteStrategy.LOCAL_REROUTE
        return RerouteStrategy.FULL_REROUTE


class SpeedController:
    def __init__(self, policy: DynamicReroutingPolicy) -> None:
        self.policy = policy

    def build_profile(self, state: AGVTrafficState, decision: Optional[TrafficDecision], reason: str) -> SpeedProfile:
        if decision is not None:
            if decision.action in {TrafficAction.WAIT, TrafficAction.STOP}:
                return SpeedProfile(state.agv_id, self.policy.stop_speed, reason)
            if decision.action == TrafficAction.SLOW_DOWN:
                target_speed = decision.target_speed if decision.target_speed is not None else max(self.policy.crawl_speed, state.speed * self.policy.speed_reduction_factor)
                return SpeedProfile(state.agv_id, target_speed, reason)
        return SpeedProfile(state.agv_id, max(self.policy.crawl_speed, state.speed * self.policy.speed_reduction_factor), reason)


class DynamicReroutingService:
    def __init__(
        self,
        topology: TopologyMap,
        planner_policy: Optional[PlannerCostPolicy] = None,
        rerouting_policy: Optional[DynamicReroutingPolicy] = None,
    ) -> None:
        self.topology = topology
        self.planner = PlannerService(topology, planner_policy)
        self.policy = rerouting_policy or DynamicReroutingPolicy()
        self.trigger_analyzer = RerouteTriggerAnalyzer(self.policy)
        self.speed_controller = SpeedController(self.policy)

    def handle(
        self,
        state: AGVTrafficState,
        current_route: PlannedRoute,
        reroute_request: Optional[RerouteRequest] = None,
        decision: Optional[TrafficDecision] = None,
        blocked_edges: Optional[List[str]] = None,
        blocked_zones: Optional[List[str]] = None,
        preferred_max_speed: Optional[float] = None,
    ) -> DynamicReroutingResult:
        blocked_edges = blocked_edges or []
        blocked_zones = blocked_zones or []
        strategy = self.trigger_analyzer.choose_strategy(reroute_request, decision, blocked_edges, blocked_zones)

        if strategy == RerouteStrategy.SPEED_ONLY:
            reason = reroute_request.reason if reroute_request else (decision.reason if decision else "SPEED_ONLY")
            return DynamicReroutingResult(
                agv_id=state.agv_id,
                success=True,
                strategy=strategy,
                reason=reason,
                route=current_route,
                planner_result=None,
                speed_profile=self.speed_controller.build_profile(state, decision, reason),
                message="Speed-only adjustment",
            )

        start_node = self._resolve_replan_start_node(state, current_route, strategy, reroute_request)
        if start_node is None:
            return DynamicReroutingResult(
                agv_id=state.agv_id,
                success=False,
                strategy=strategy,
                reason="START_NODE_UNKNOWN",
                route=None,
                planner_result=None,
                speed_profile=self.speed_controller.build_profile(state, decision, "Unknown replanning start node"),
                message="Cannot determine replanning start node",
            )

        avoid_edges = list(reroute_request.avoid_edges) if reroute_request else []
        avoid_zones = list(reroute_request.avoid_zones) if reroute_request else []
        if strategy == RerouteStrategy.LOCAL_REROUTE and state.current_edge and state.current_edge not in avoid_edges:
            avoid_edges.append(state.current_edge)
        if strategy == RerouteStrategy.LOCAL_REROUTE and state.current_zone and state.current_zone not in avoid_zones:
            avoid_zones.append(state.current_zone)

        planner_request = PlannerRequest(
            agv_id=state.agv_id,
            start_node=start_node,
            goal_node=current_route.goal_node,
            blocked_edges=blocked_edges,
            blocked_zones=blocked_zones,
            hard_blocked_edges=blocked_edges,
            hard_blocked_zones=blocked_zones,
            avoid_edges=avoid_edges,
            avoid_zones=avoid_zones,
            preferred_max_speed=preferred_max_speed,
            route_version=current_route.route_version + 1,
            reason=reroute_request.reason if reroute_request else (decision.reason if decision else strategy.value),
            algorithm=PlannerAlgorithm.ASTAR,
        )
        planner_result = self.planner.plan(planner_request)
        if not planner_result.success or planner_result.route is None or not planner_result.route.segments:
            return DynamicReroutingResult(
                agv_id=state.agv_id,
                success=False,
                strategy=strategy,
                reason=planner_request.reason or strategy.value,
                route=None,
                planner_result=planner_result,
                speed_profile=self.speed_controller.build_profile(state, decision, "Fallback to wait/slow due to failed reroute"),
                message=f"Reroute failed: {planner_result.message if planner_result else 'unknown'}",
            )

        planner_result.route = self._stitch_retreat_prefix(
            state=state,
            current_route=current_route,
            strategy=strategy,
            reroute_request=reroute_request,
            planned_route=planner_result.route,
        )

        if self._has_immediate_backtrack(planner_result.route):
            return DynamicReroutingResult(
                agv_id=state.agv_id,
                success=False,
                strategy=strategy,
                reason="BACKTRACK_LOOP",
                route=None,
                planner_result=planner_result,
                speed_profile=self.speed_controller.build_profile(state, decision, "Planner returned a backtracking loop"),
                message="Planner returned a route with immediate backtracking",
            )

        if self._is_materially_unchanged_route(state, current_route, planner_result.route):
            return DynamicReroutingResult(
                agv_id=state.agv_id,
                success=False,
                strategy=strategy,
                reason="UNCHANGED_ROUTE",
                route=None,
                planner_result=planner_result,
                speed_profile=self.speed_controller.build_profile(state, decision, "Planner returned unchanged route"),
                message="Planner did not produce a materially different route",
            )

        return DynamicReroutingResult(
            agv_id=state.agv_id,
            success=True,
            strategy=strategy,
            reason=planner_request.reason or strategy.value,
            route=planner_result.route,
            planner_result=planner_result,
            speed_profile=None,
            message="Reroute successful",
        )

    def _has_immediate_backtrack(self, route: PlannedRoute) -> bool:
        if not route.segments:
            return False

        node_path = [route.segments[0].from_node] + [segment.to_node for segment in route.segments]
        for idx in range(len(node_path) - 2):
            if node_path[idx] == node_path[idx + 2]:
                return True

        for left, right in zip(route.segments, route.segments[1:]):
            if left.from_node == right.to_node and left.to_node == right.from_node:
                return True
            left_physical = self.topology.get_edge(left.edge_id).physical_edge_id or left.edge_id
            right_physical = self.topology.get_edge(right.edge_id).physical_edge_id or right.edge_id
            if left_physical == right_physical:
                return True

        return False

    def _stitch_retreat_prefix(
        self,
        state: AGVTrafficState,
        current_route: PlannedRoute,
        strategy: RerouteStrategy,
        reroute_request: Optional[RerouteRequest],
        planned_route: PlannedRoute,
    ) -> PlannedRoute:
        if (
            strategy != RerouteStrategy.LOCAL_REROUTE
            or reroute_request is None
            or state.current_edge is None
            or state.route_progress_index is None
            or state.route_progress_index < 0
            or state.route_progress_index >= len(current_route.segments)
            or not self._is_conflict_retreat_reason(reroute_request.reason)
        ):
            return planned_route

        current_segment = current_route.segments[state.route_progress_index]
        if not planned_route.segments:
            return planned_route

        first_segment = planned_route.segments[0]
        if first_segment.from_node != current_segment.from_node:
            return planned_route

        offset = state.offset_on_edge
        if offset is not None and offset < 0.35:
            return planned_route

        reverse_edge_id = self._reverse_edge_id(current_segment.edge_id)
        reverse_edge = self.topology.edges.get(reverse_edge_id)
        if reverse_edge is None:
            return planned_route

        if reverse_edge.to_node != current_segment.from_node:
            return planned_route

        stitched_segments = [
            RouteSegment(
                edge_id=reverse_edge.edge_id,
                from_node=reverse_edge.from_node,
                to_node=reverse_edge.to_node,
                planned_speed=reverse_edge.max_speed,
            ),
            *planned_route.segments,
        ]
        return PlannedRoute(
            route_id=planned_route.route_id,
            agv_id=planned_route.agv_id,
            start_node=stitched_segments[0].from_node,
            goal_node=planned_route.goal_node,
            segments=stitched_segments,
            route_version=planned_route.route_version,
            reason=planned_route.reason,
        )

    @staticmethod
    def _reverse_edge_id(edge_id: str) -> str:
        return edge_id[:-5] if edge_id.endswith("__rev") else f"{edge_id}__rev"

    @staticmethod
    def _is_conflict_retreat_reason(reason: Optional[str]) -> bool:
        if not reason:
            return False
        return str(reason).startswith(("PREVIEW_NODE_AHEAD_", "NODE_AHEAD_", "EDGE_AHEAD_", "HEAD_ON", "DEADLOCK"))

    @staticmethod
    def _resolve_replan_start_node(
        state: AGVTrafficState,
        current_route: PlannedRoute,
        strategy: RerouteStrategy,
        reroute_request: Optional[RerouteRequest],
    ) -> Optional[str]:
        if state.route_progress_index is not None and 0 <= state.route_progress_index < len(current_route.segments):
            current_segment = current_route.segments[state.route_progress_index]
            if (
                strategy == RerouteStrategy.LOCAL_REROUTE
                and reroute_request is not None
                and state.current_edge is not None
            ):
                # Allow retreat to the previous node so the planner can search an escape path
                # instead of forcing the AGV to continue deeper into the conflicting corridor.
                return current_segment.from_node
            if state.offset_on_edge is not None:
                if state.offset_on_edge <= 0.15:
                    return current_segment.from_node
                return current_segment.to_node
            return current_segment.from_node
        if state.current_node:
            return state.current_node
        if state.next_node:
            return state.next_node
        return current_route.start_node or None

    def _is_materially_unchanged_route(
        self,
        state: AGVTrafficState,
        current_route: PlannedRoute,
        new_route: PlannedRoute,
    ) -> bool:
        start_index = state.route_progress_index or 0
        current_remaining = current_route.segments[start_index:] if current_route.segments else []
        new_segments = new_route.segments or []

        current_edges = [segment.edge_id for segment in current_remaining]
        new_edges = [segment.edge_id for segment in new_segments]
        if new_edges == current_edges:
            return True

        current_nodes = [current_remaining[0].from_node] + [segment.to_node for segment in current_remaining] if current_remaining else []
        new_nodes = [new_segments[0].from_node] + [segment.to_node for segment in new_segments] if new_segments else []
        if current_nodes and new_nodes and current_nodes == new_nodes:
            return True

        current_physical = [
            (self.topology.get_edge(segment.edge_id).physical_edge_id or segment.edge_id)
            for segment in current_remaining
            if segment.edge_id in self.topology.edges
        ]
        new_physical = [
            (self.topology.get_edge(segment.edge_id).physical_edge_id or segment.edge_id)
            for segment in new_segments
            if segment.edge_id in self.topology.edges
        ]
        return current_physical == new_physical and bool(current_physical)


@dataclass(slots=True)
class _MapContext:
    topology: TopologyMap
    planner: PlannerService
    state_service: StateManagementService
    conflict_service: ConflictManagementService
    rerouting_service: DynamicReroutingService
    predictive_engine: predictive_state.StateManagementEngine
    predictive_snapshot: Optional[predictive_state.StateSnapshot] = None


class TrafficEngine:
    def __init__(self) -> None:
        self._contexts: Dict[str, _MapContext] = {}
        self._agv_map: Dict[str, str] = {}
        self._routes: Dict[str, PlannedRoute] = {}
        self._priority_contexts: Dict[str, PriorityContext] = {}
        self._route_lock_counter = 0
        self._reservations: Dict[str, List[str]] = {}
        self._reservation_window_size = 3
        self._reroute_guard: Dict[str, Dict[str, object]] = {}
        self._conflict_wait_guard: Dict[str, Dict[str, object]] = {}
        self._reroute_cooldown_sec = 1.8
        self._conflict_wait_timeout_sec = 10.0
        self._lock = threading.RLock()

    @staticmethod
    def _build_predictive_topology(topology: TopologyMap) -> predictive_state.TopologyMap:
        nodes = [
            predictive_state.Node(node_id=node.node_id, x=node.x, y=node.y)
            for node in topology.nodes.values()
        ]
        edges = [
            predictive_state.Edge(
                edge_id=edge.edge_id,
                from_node=edge.from_node,
                to_node=edge.to_node,
                length=edge.length,
                max_speed=edge.max_speed,
                physical_edge_id=edge.physical_edge_id,
                bidirectional=False,
            )
            for edge in topology.edges.values()
        ]
        return predictive_state.TopologyMap(nodes, edges)

    @staticmethod
    def _to_predictive_route(route: PlannedRoute) -> predictive_state.PlannedRoute:
        return predictive_state.PlannedRoute(
            route_id=route.route_id,
            agv_id=route.agv_id,
            start_node=route.start_node,
            goal_node=route.goal_node,
            segments=[
                predictive_state.RouteSegment(
                    edge_id=segment.edge_id,
                    from_node=segment.from_node,
                    to_node=segment.to_node,
                    planned_speed=segment.planned_speed,
                )
                for segment in route.segments
            ],
        )

    @staticmethod
    def _to_predictive_state(state: AGVTrafficState) -> predictive_state.AGVState:
        paused = state.traffic_state in {TrafficState.WAITING, TrafficState.BLOCKED, TrafficState.STOPPED}
        return predictive_state.AGVState(
            agv_id=state.agv_id,
            timestamp=state.timestamp,
            x=state.x,
            y=state.y,
            heading_deg=state.heading_deg,
            speed=state.speed,
            current_node=state.current_node,
            current_edge=state.current_edge,
            next_node=state.next_node,
            offset_on_edge=state.offset_on_edge,
            route_progress_index=state.route_progress_index,
            paused=paused,
            meta={
                "traffic_state": state.traffic_state.value if state.traffic_state else None,
                "health_state": state.health_state.value if state.health_state else None,
                "current_zone": state.current_zone,
            },
        )

    def _refresh_predictive_snapshot(self, context: _MapContext, now: Optional[float] = None) -> predictive_state.StateSnapshot:
        snapshot = context.predictive_engine.build_snapshot(at_time=now)
        context.predictive_snapshot = snapshot
        return snapshot

    @staticmethod
    def _sync_predictive_winner_from_decision(
        context: _MapContext,
        snapshot: Optional[predictive_state.StateSnapshot],
        decision: Optional[TrafficDecision],
    ) -> bool:
        if snapshot is None or decision is None or not decision.related_agv_id:
            return False

        if decision.action == TrafficAction.PROCEED:
            winner_agv = decision.agv_id
        elif decision.action in {TrafficAction.WAIT, TrafficAction.STOP, TrafficAction.SLOW_DOWN, TrafficAction.REROUTE}:
            winner_agv = decision.related_agv_id
        else:
            return False

        pair = {decision.agv_id, decision.related_agv_id}
        updated = False
        for conflict in snapshot.conflicts:
            if set(conflict.agv_ids) != pair:
                continue
            context.predictive_engine.lock_conflict_winner(
                conflict=conflict,
                winner_agv=winner_agv,
                generated_at=snapshot.generated_at,
            )
            updated = True
        return updated

    @staticmethod
    def _log_predictive_state(
        agv_id: str,
        snapshot: Optional[predictive_state.StateSnapshot],
    ) -> None:
        if snapshot is None:
            return
        recommendation = snapshot.recommendations.get(agv_id)
        if recommendation is None:
            return
        conflict_count = sum(1 for conflict in snapshot.conflicts if agv_id in conflict.agv_ids)
        if conflict_count <= 0 and recommendation.action == predictive_state.ControlAction.PROCEED:
            return
        print(
            f"[STATE MGMT] agv={agv_id} predicted_conflicts={conflict_count} "
            f"action={recommendation.action.value} target_speed={recommendation.target_speed} "
            f"reason={recommendation.reason} related={recommendation.related_agv_id}"
        )

    @staticmethod
    def _route_signature(route: Optional[PlannedRoute]) -> Tuple[str, ...]:
        if route is None:
            return tuple()
        return tuple(segment.edge_id for segment in route.segments)
    
    @staticmethod
    def _is_hard_conflict(decision: Optional[TrafficDecision], reroute_request: Optional[RerouteRequest]) -> bool:
        if decision and decision.action in {TrafficAction.WAIT, TrafficAction.STOP}:
            return True
        if reroute_request and str(reroute_request.reason).startswith(("PREVIEW_NODE_AHEAD_", "NODE_AHEAD_", "EDGE_AHEAD_", "HEAD_ON")):
            return True
        return False

    @staticmethod
    def _is_wait_hold_reason(reason: Optional[str]) -> bool:
        return bool(reason and str(reason).startswith("WAIT_HOLD:"))

    @staticmethod
    def _is_wait_first_reroute_reason(reason: Optional[str]) -> bool:
        if not reason:
            return False
        return str(reason).startswith(("PREVIEW_NODE_AHEAD_", "NODE_AHEAD_", "EDGE_AHEAD_", "YIELD_"))

    def _find_conflict_record(
        self,
        conflict_result: ConflictManagementResult,
        conflict_id: Optional[str],
    ) -> Optional[ConflictRecord]:
        if not conflict_id:
            return None
        for conflict in conflict_result.conflicts:
            if conflict.conflict_id == conflict_id:
                return conflict
        return None

    def _clear_wait_hold(self, agv_id: str) -> None:
        self._conflict_wait_guard.pop(agv_id, None)

    def _apply_wait_before_reroute_policy(
        self,
        agv_id: str,
        state: AGVTrafficState,
        conflict_result: ConflictManagementResult,
        decision: Optional[TrafficDecision],
        reroute_request: Optional[RerouteRequest],
    ) -> Tuple[Optional[TrafficDecision], Optional[RerouteRequest]]:
        reason = reroute_request.reason if reroute_request else (decision.reason if decision else None)
        if not self._is_wait_first_reroute_reason(reason):
            self._clear_wait_hold(agv_id)
            return decision, reroute_request

        conflict_id = (
            reroute_request.related_conflict_id
            if reroute_request is not None
            else (decision.related_conflict_id if decision is not None else None)
        )
        conflict = self._find_conflict_record(conflict_result, conflict_id)
        resource_id = (
            conflict.resource_id
            if conflict is not None
            else (
                reroute_request.avoid_edges[0]
                if reroute_request and reroute_request.avoid_edges
                else (state.current_edge or state.next_node or state.current_node or "unknown")
            )
        )
        related_agv_id = decision.related_agv_id if decision is not None else None
        guard = self._conflict_wait_guard.get(agv_id)
        now = time.time()
        if (
            guard is None
            or guard.get("resource_id") != resource_id
            or guard.get("related_agv_id") != related_agv_id
        ):
            guard = {
                "resource_id": resource_id,
                "related_agv_id": related_agv_id,
                "since": now,
            }
            self._conflict_wait_guard[agv_id] = guard

        waited_for = now - float(guard.get("since", now) or now)
        if waited_for < self._conflict_wait_timeout_sec:
            owner_text = related_agv_id or "another AGV"
            hold_reason = (
                f"WAIT_HOLD: Waiting for {owner_text} to clear conflict resource "
                f"{resource_id} ({int(waited_for)}s/{int(self._conflict_wait_timeout_sec)}s)"
            )
            return (
                TrafficDecision(
                    agv_id=agv_id,
                    action=TrafficAction.WAIT,
                    reason=hold_reason,
                    related_conflict_id=conflict_id,
                    related_agv_id=related_agv_id,
                ),
                None,
            )

        return decision, reroute_request

    @staticmethod
    def _is_ahead_conflict_reason(reason: Optional[str]) -> bool:
        if not reason:
            return False
        return str(reason).startswith(("PREVIEW_NODE_AHEAD_", "NODE_AHEAD_", "EDGE_AHEAD_", "HEAD_ON", "DEADLOCK"))

    def _should_suppress_reroute(self, agv_id: str, state: AGVTrafficState, reroute_request: Optional[RerouteRequest]) -> bool:
        guard = self._reroute_guard.get(agv_id)
        if not guard:
            return False
        now = time.time()
        if float(guard.get("cooldown_until", 0.0) or 0.0) <= now:
            return False
        reason = reroute_request.reason if reroute_request else None
        if reason and reason == guard.get("last_reason") and state.current_edge == guard.get("last_edge"):
            return True
        if (
            state.current_edge is not None
            and state.current_edge == guard.get("last_edge")
            and self._is_ahead_conflict_reason(reason)
            and self._is_ahead_conflict_reason(guard.get("last_reason"))
        ):
            return True
        return False

    def _would_flip_flop(self, agv_id: str, route: PlannedRoute) -> bool:
        guard = self._reroute_guard.get(agv_id) or {}
        history = list(guard.get("history") or [])
        new_signature = self._route_signature(route)
        if len(history) < 2:
            return False
        return history[-2] == new_signature and history[-1] != new_signature

    def _remember_reroute(self, agv_id: str, state: AGVTrafficState, reason: Optional[str], route: Optional[PlannedRoute]) -> None:
        guard = self._reroute_guard.setdefault(agv_id, {})
        history = list(guard.get("history") or [])
        if route is not None:
            signature = self._route_signature(route)
            if not history or history[-1] != signature:
                history.append(signature)
            history = history[-4:]
        guard.update({
            "history": history,
            "last_reason": reason,
            "last_edge": state.current_edge,
            "cooldown_until": time.time() + self._reroute_cooldown_sec,
        })

    def _clear_reroute_guard(self, agv_id: str) -> None:
        self._reroute_guard.pop(agv_id, None)

    def _collect_escape_blocked_edges(
        self,
        map_id: str,
        agv_id: str,
        state: AGVTrafficState,
        current_route: PlannedRoute,
    ) -> List[str]:
        blocked_edges = self.get_reserved_edges(map_id, exclude_agv=agv_id)
        if state.current_edge and state.current_edge not in blocked_edges:
            blocked_edges.append(state.current_edge)

        guard = self._reroute_guard.get(agv_id) or {}
        history = list(guard.get("history") or [])
        for signature in history[-3:]:
            if not signature:
                continue
            first_edge = signature[0]
            if first_edge not in blocked_edges:
                blocked_edges.append(first_edge)

        if current_route.segments:
            first_remaining = current_route.segments[state.route_progress_index or 0].edge_id if state.route_progress_index is not None and 0 <= state.route_progress_index < len(current_route.segments) else current_route.segments[0].edge_id
            if first_remaining not in blocked_edges:
                blocked_edges.append(first_remaining)
        return blocked_edges

    def _edges_touching_node(self, topology: TopologyMap, node_id: str) -> List[str]:
        edges: List[str] = []
        for edge in topology.edges.values():
            if edge.from_node == node_id or edge.to_node == node_id:
                edges.append(edge.edge_id)
        return edges

    def _edges_for_physical_resource(self, topology: TopologyMap, physical_id: str) -> List[str]:
        edges: List[str] = []
        for edge in topology.edges.values():
            normalized = edge.physical_edge_id or (edge.edge_id[:-5] if edge.edge_id.endswith("__rev") else edge.edge_id)
            if normalized == physical_id:
                edges.append(edge.edge_id)
        return edges

    def _collect_conflict_blocked_edges(
        self,
        context: _MapContext,
        map_id: str,
        agv_id: str,
        state: AGVTrafficState,
        current_route: PlannedRoute,
        conflict_result: ConflictManagementResult,
        decision: Optional[TrafficDecision],
        reroute_request: Optional[RerouteRequest],
    ) -> List[str]:
        blocked_edges = self.get_reserved_edges(map_id, exclude_agv=agv_id)
        topology = context.topology

        conflict_id = (
            reroute_request.related_conflict_id
            if reroute_request is not None
            else (decision.related_conflict_id if decision is not None else None)
        )
        conflict = self._find_conflict_record(conflict_result, conflict_id)
        reason = reroute_request.reason if reroute_request is not None else (decision.reason if decision is not None else None)
        resource_id = conflict.resource_id if conflict is not None else None
        related_agv_id = decision.related_agv_id if decision is not None else None

        if resource_id:
            if resource_id in topology.nodes:
                for edge_id in self._edges_touching_node(topology, resource_id):
                    if edge_id not in blocked_edges:
                        blocked_edges.append(edge_id)
            else:
                for edge_id in self._edges_for_physical_resource(topology, resource_id):
                    if edge_id not in blocked_edges:
                        blocked_edges.append(edge_id)

        if reason and str(reason).startswith(("NODE_AHEAD_", "PREVIEW_NODE_AHEAD_")):
            node_id = str(reason).split("_")[-1]
            if node_id in topology.nodes:
                for edge_id in self._edges_touching_node(topology, node_id):
                    if edge_id not in blocked_edges:
                        blocked_edges.append(edge_id)

        if related_agv_id:
            related_map = self._agv_map.get(related_agv_id)
            if related_map == map_id:
                related_context = self._contexts.get(map_id)
                related_state = related_context.state_service.get_state(related_agv_id) if related_context else None
                if related_state is not None:
                    if related_state.current_edge and related_state.current_edge not in blocked_edges:
                        blocked_edges.append(related_state.current_edge)
                    if related_state.current_node:
                        for edge_id in self._edges_touching_node(topology, related_state.current_node):
                            if edge_id not in blocked_edges:
                                blocked_edges.append(edge_id)
                for edge_id in self._windowed_reserved_edges(related_agv_id, map_id):
                    if edge_id not in blocked_edges:
                        blocked_edges.append(edge_id)

        guard = self._reroute_guard.get(agv_id) or {}
        history = list(guard.get("history") or [])
        for signature in history[-3:]:
            if not signature:
                continue
            for edge_id in signature[:2]:
                if edge_id not in blocked_edges:
                    blocked_edges.append(edge_id)

        if current_route.segments:
            start_index = state.route_progress_index or 0
            if 0 <= start_index < len(current_route.segments):
                for segment in current_route.segments[start_index : start_index + 2]:
                    if segment.edge_id not in blocked_edges:
                        blocked_edges.append(segment.edge_id)
        return blocked_edges

    def _attempt_escape_reroute(
        self,
        context: _MapContext,
        map_id: str,
        state: AGVTrafficState,
        current_route: PlannedRoute,
        decision: Optional[TrafficDecision],
        reroute_request: Optional[RerouteRequest],
    ) -> Optional[DynamicReroutingResult]:
        if not self._is_hard_conflict(decision, reroute_request):
            return None

        escape_request = RerouteRequest(
            agv_id=state.agv_id,
            reason="DEADLOCK_RESOLUTION",
            avoid_edges=list(reroute_request.avoid_edges) if reroute_request else [],
            avoid_zones=list(reroute_request.avoid_zones) if reroute_request else [],
            related_conflict_id=reroute_request.related_conflict_id if reroute_request else (decision.related_conflict_id if decision else None),
        )
        if state.current_edge and state.current_edge not in escape_request.avoid_edges:
            escape_request.avoid_edges.append(state.current_edge)

        escape_blocked_edges = self._collect_escape_blocked_edges(map_id, state.agv_id, state, current_route)
        escape_result = context.rerouting_service.handle(
            state=state,
            current_route=current_route,
            reroute_request=escape_request,
            decision=decision,
            blocked_edges=escape_blocked_edges,
        )
        print(
            f"[TRAFFIC CORE] escape_attempt agv={state.agv_id} "
            f"blocked_edges={escape_blocked_edges} success={escape_result.success if escape_result else None} "
            f"strategy={escape_result.strategy.value if escape_result else None} "
            f"message={escape_result.message if escape_result else None}"
        )
        if (
            escape_result.success
            and escape_result.route
            and escape_result.strategy != RerouteStrategy.SPEED_ONLY
        ):
            return escape_result
        return None

    def set_topology(self, map_id: str, topology: TopologyMap) -> None:
        with self._lock:
            predictive_topology = self._build_predictive_topology(topology)
            self._contexts[map_id] = _MapContext(
                topology=topology,
                planner=PlannerService(topology),
                state_service=StateManagementService(topology),
                conflict_service=ConflictManagementService(topology),
                rerouting_service=DynamicReroutingService(topology),
                predictive_engine=predictive_state.StateManagementEngine(predictive_topology),
            )

    def has_map(self, map_id: str) -> bool:
        with self._lock:
            return map_id in self._contexts

    def plan_route(
        self,
        map_id: str,
        agv_id: str,
        start_node: str,
        goal_node: str,
        blocked_edges: Optional[List[str]] = None,
        blocked_zones: Optional[List[str]] = None,
        avoid_edges: Optional[List[str]] = None,
        avoid_zones: Optional[List[str]] = None,
        preferred_max_speed: Optional[float] = None,
        reason: Optional[str] = None,
        route_version: Optional[int] = None,
    ) -> PlannerResult:
        with self._lock:
            context = self._contexts[map_id]
            current_route = self._routes.get(agv_id)
            request = PlannerRequest(
                agv_id=agv_id,
                start_node=start_node,
                goal_node=goal_node,
                blocked_edges=blocked_edges,
                blocked_zones=blocked_zones,
                hard_blocked_edges=blocked_edges,
                hard_blocked_zones=blocked_zones,
                avoid_edges=avoid_edges,
                avoid_zones=avoid_zones,
                preferred_max_speed=preferred_max_speed,
                reason=reason,
                route_version=route_version or ((current_route.route_version + 1) if current_route else 1),
            )
            return context.planner.plan(request)

    def activate_route(self, agv_id: str, map_id: str, route: PlannedRoute) -> None:
        with self._lock:
            self._agv_map[agv_id] = map_id
            self._refresh_route_lock_priority(agv_id, route)
            existing_route = self._routes.get(agv_id)
            is_new_mission = route.reason in {"API_MOVE", "API_MOVE_PATH", "STATE_PENDING_DESTINATION"}
            goal_changed = existing_route is not None and existing_route.goal_node != route.goal_node
            if is_new_mission or goal_changed:
                self._clear_reroute_guard(agv_id)
                self._clear_wait_hold(agv_id)
            self._routes[agv_id] = route
            self._reservations[agv_id] = [segment.edge_id for segment in route.segments]
            context = self._contexts.get(map_id)
            if context is not None:
                context.predictive_engine.upsert_route(self._to_predictive_route(route))

    def _refresh_route_lock_priority(self, agv_id: str, route: PlannedRoute) -> None:
        existing_context = self._priority_contexts.get(agv_id) or PriorityContext(agv_id=agv_id)
        existing_route = self._routes.get(agv_id)

        should_allocate_new_lock = existing_context.route_lock_order <= 0
        if existing_route is None:
            should_allocate_new_lock = True
        elif route.reason in {"API_MOVE", "API_MOVE_PATH", "STATE_PENDING_DESTINATION"}:
            should_allocate_new_lock = True
        elif existing_route.goal_node != route.goal_node:
            should_allocate_new_lock = True

        route_lock_order = existing_context.route_lock_order
        if should_allocate_new_lock:
            self._route_lock_counter += 1
            route_lock_order = self._route_lock_counter

        self._priority_contexts[agv_id] = PriorityContext(
            agv_id=agv_id,
            delivering=existing_context.delivering,
            delivery_completed=existing_context.delivery_completed,
            priority_boost=existing_context.priority_boost,
            route_lock_order=route_lock_order,
        )

    def release_agv(self, agv_id: str) -> None:
        with self._lock:
            map_id = self._agv_map.pop(agv_id, None)
            self._routes.pop(agv_id, None)
            self._reservations.pop(agv_id, None)
            self._priority_contexts.pop(agv_id, None)
            self._clear_reroute_guard(agv_id)
            self._clear_wait_hold(agv_id)
            if map_id is not None and map_id in self._contexts:
                self._contexts[map_id].predictive_engine.set_route(agv_id, None)

    def get_route(self, agv_id: str) -> Optional[PlannedRoute]:
        with self._lock:
            return self._routes.get(agv_id)

    def activate_route_from_node_path(
        self,
        agv_id: str,
        map_id: str,
        node_path: List[str],
        current_hint_node: Optional[str] = None,
        reason: str = "REHYDRATED_PATH",
    ) -> Optional[PlannedRoute]:
        with self._lock:
            context = self._contexts.get(map_id)
            if context is None:
                return None

            normalized = [str(node_id) for node_id in node_path if str(node_id)]
            if len(normalized) < 2:
                return None

            if current_hint_node:
                hint = str(current_hint_node)
                if hint in normalized:
                    hint_index = normalized.index(hint)
                    if hint_index < len(normalized) - 1:
                        normalized = normalized[hint_index:]

            segments: List[RouteSegment] = []
            for from_node, to_node in zip(normalized, normalized[1:]):
                edge = self._find_edge_between(context.topology, from_node, to_node)
                if edge is None:
                    return None
                segments.append(
                    RouteSegment(
                        edge_id=edge.edge_id,
                        from_node=edge.from_node,
                        to_node=edge.to_node,
                        planned_speed=max(edge.max_speed, 0.1),
                    )
                )

            if not segments:
                return None

            existing = self._routes.get(agv_id)
            route_version = (existing.route_version + 1) if existing else 1
            route = PlannedRoute(
                route_id=f"route_{agv_id}_v{route_version}",
                agv_id=agv_id,
                start_node=segments[0].from_node,
                goal_node=segments[-1].to_node,
                segments=segments,
                route_version=route_version,
                reason=reason,
            )
            self.activate_route(agv_id, map_id, route)
            return route

    def _windowed_reserved_edges(self, agv_id: str, map_id: str) -> List[str]:
        route = self._routes.get(agv_id)
        if route is None or self._agv_map.get(agv_id) != map_id:
            return []
        context = self._contexts.get(map_id)
        if context is None:
            return []
        state = context.state_service.get_state(agv_id)
        if state is None or state.route_progress_index is None:
            return self._reservations.get(agv_id, [])[: self._reservation_window_size]
        start_index = max(0, state.route_progress_index)
        if state.current_edge and start_index < len(route.segments):
            current_segment = route.segments[start_index]
            if current_segment.edge_id != state.current_edge:
                for idx, segment in enumerate(route.segments):
                    if segment.edge_id == state.current_edge:
                        start_index = idx
                        break
        end_index = min(len(route.segments), start_index + self._reservation_window_size)
        return [segment.edge_id for segment in route.segments[start_index:end_index]]

    @staticmethod
    def _find_edge_between(topology: TopologyMap, from_node: str, to_node: str) -> Optional[Edge]:
        exact_match: Optional[Edge] = None
        fallback_match: Optional[Edge] = None
        for edge in topology.get_outgoing_edges(from_node):
            if edge.to_node != to_node:
                continue
            if edge.edge_id.endswith("_curve"):
                fallback_match = edge
                continue
            exact_match = edge
            break
        return exact_match or fallback_match

    def get_reserved_edges(self, map_id: str, exclude_agv: Optional[str] = None) -> List[str]:
        with self._lock:
            reserved: List[str] = []
            for agv_id, edges in self._reservations.items():
                if agv_id == exclude_agv:
                    continue
                if self._agv_map.get(agv_id) != map_id:
                    continue
                windowed = self._windowed_reserved_edges(agv_id, map_id)
                reserved.extend(windowed if windowed else edges)
            return reserved

    def update_priority_context(self, context: PriorityContext) -> None:
        with self._lock:
            self._priority_contexts[context.agv_id] = context

    def ingest_telemetry(self, map_id: str, telemetry: Telemetry) -> AGVTrafficState:
        with self._lock:
            context = self._contexts[map_id]
            route = self._routes.get(telemetry.agv_id)
            self._agv_map[telemetry.agv_id] = map_id
            state = context.state_service.ingest_telemetry(telemetry, route)
            context.predictive_engine.upsert_state(self._to_predictive_state(state))
            if route is not None:
                context.predictive_engine.upsert_route(self._to_predictive_route(route))
            else:
                context.predictive_engine.set_route(telemetry.agv_id, None)
            return state

    def build_snapshot(self, map_id: str) -> TrafficSnapshot:
        with self._lock:
            return self._contexts[map_id].state_service.build_snapshot()

    def evaluate_map(self, map_id: str) -> ConflictManagementResult:
        with self._lock:
            context = self._contexts[map_id]
            snapshot = context.state_service.build_snapshot()
            self._refresh_predictive_snapshot(context, snapshot.generated_at)
            map_routes = {agv_id: route for agv_id, route in self._routes.items() if self._agv_map.get(agv_id) == map_id}
            return context.conflict_service.evaluate(snapshot.states, map_routes, snapshot.alerts, dict(self._priority_contexts))

    def handle_telemetry(self, map_id: str, telemetry: Telemetry) -> EngineUpdateResult:
        with self._lock:
            context = self._contexts[map_id]
            state = self.ingest_telemetry(map_id, telemetry)
            snapshot = context.state_service.build_snapshot()
            predictive_snapshot = self._refresh_predictive_snapshot(context, snapshot.generated_at)
            map_routes = {agv_id: route for agv_id, route in self._routes.items() if self._agv_map.get(agv_id) == map_id}
            conflict_result = context.conflict_service.evaluate(snapshot.states, map_routes, snapshot.alerts, dict(self._priority_contexts))

            decision_lookup = {decision.agv_id: decision for decision in conflict_result.decisions}
            reroute_lookup = {request.agv_id: request for request in conflict_result.reroute_requests}
            decision = decision_lookup.get(telemetry.agv_id)
            reroute_request = reroute_lookup.get(telemetry.agv_id)
            decision, reroute_request = self._apply_wait_before_reroute_policy(
                agv_id=telemetry.agv_id,
                state=state,
                conflict_result=conflict_result,
                decision=decision,
                reroute_request=reroute_request,
            )
            
            # SAFETY: If no route known and no explicit decision, default to WAIT to prevent blind movement
            current_route = self._routes.get(telemetry.agv_id)
            if decision is None and current_route is None:
                decision = TrafficDecision(
                    agv_id=telemetry.agv_id,
                    action=TrafficAction.WAIT,
                    reason="No active route; waiting for route assignment",
                )
            reroute_result: Optional[DynamicReroutingResult] = None
            current_route = self._routes.get(telemetry.agv_id)

            if decision or reroute_request or conflict_result.conflicts:
                active_route_edges = [segment.edge_id for segment in current_route.segments] if current_route and current_route.segments else []
                print(
                    f"[TRAFFIC CORE] agv={telemetry.agv_id} map={map_id} "
                    f"conflicts={len(conflict_result.conflicts)} decision={decision.action.value if decision else None} "
                    f"reroute_request={reroute_request.reason if reroute_request else None} "
                    f"route_edges={active_route_edges} current_node={state.current_node} current_edge={state.current_edge} "
                    f"has_route={current_route is not None}"
                )
            if self._sync_predictive_winner_from_decision(context, predictive_snapshot, decision):
                predictive_snapshot = self._refresh_predictive_snapshot(context, snapshot.generated_at)
            self._log_predictive_state(telemetry.agv_id, predictive_snapshot)

            should_attempt_reroute = reroute_request is not None or (
                decision is not None
                and decision.action in {TrafficAction.WAIT, TrafficAction.STOP, TrafficAction.SLOW_DOWN, TrafficAction.REROUTE}
                and not self._is_wait_hold_reason(decision.reason)
            )

            if current_route and should_attempt_reroute:
                blocked_edges: List[str] = []
                if self._should_suppress_reroute(telemetry.agv_id, state, reroute_request):
                    reroute_result = DynamicReroutingResult(
                        agv_id=telemetry.agv_id,
                        success=False,
                        strategy=RerouteStrategy.SPEED_ONLY,
                        reason=reroute_request.reason if reroute_request else (decision.reason if decision else "REROUTE_COOLDOWN"),
                        route=current_route,
                        planner_result=None,
                        speed_profile=context.rerouting_service.speed_controller.build_profile(state, decision, "Reroute cooldown guard"),
                        message="Suppressed repeated reroute during cooldown window",
                    )
                else:
                    blocked_edges = self._collect_conflict_blocked_edges(
                        context=context,
                        map_id=map_id,
                        agv_id=telemetry.agv_id,
                        state=state,
                        current_route=current_route,
                        conflict_result=conflict_result,
                        decision=decision,
                        reroute_request=reroute_request,
                    )
                    reroute_result = context.rerouting_service.handle(
                        state=state,
                        current_route=current_route,
                        reroute_request=reroute_request,
                        decision=decision,
                        blocked_edges=blocked_edges,
                    )
                    if reroute_result.success and reroute_result.route and reroute_result.strategy != RerouteStrategy.SPEED_ONLY and self._would_flip_flop(telemetry.agv_id, reroute_result.route):
                        reroute_result = DynamicReroutingResult(
                            agv_id=telemetry.agv_id,
                            success=False,
                            strategy=RerouteStrategy.SPEED_ONLY,
                            reason=reroute_result.reason,
                            route=current_route,
                            planner_result=reroute_result.planner_result,
                            speed_profile=context.rerouting_service.speed_controller.build_profile(state, decision, "Suppressed reroute oscillation"),
                            message="Suppressed reroute oscillation between alternating paths",
                        )
                print(
                    f"[TRAFFIC CORE] reroute_attempt agv={telemetry.agv_id} "
                    f"blocked_edges={blocked_edges} success={reroute_result.success if reroute_result else None} "
                    f"strategy={reroute_result.strategy.value if reroute_result else None} "
                    f"message={reroute_result.message if reroute_result else None}"
                )
                if (
                    reroute_result is not None
                    and not reroute_result.success
                    and self._is_hard_conflict(decision, reroute_request)
                ):
                    escape_result = self._attempt_escape_reroute(
                        context=context,
                        map_id=map_id,
                        state=state,
                        current_route=current_route,
                        decision=decision,
                        reroute_request=reroute_request,
                    )
                    if escape_result is not None:
                        reroute_result = escape_result
                if (
                    reroute_result is not None
                    and not reroute_result.success
                    and self._is_hard_conflict(decision, reroute_request)
                ):
                    fallback_reason = reroute_request.reason if reroute_request else (decision.reason if decision else "HARD_CONFLICT")
                    decision = TrafficDecision(
                        agv_id=telemetry.agv_id,
                        action=TrafficAction.WAIT,
                        reason=f"Waiting because reroute is not yet available ({fallback_reason})",
                        related_conflict_id=decision.related_conflict_id if decision else (reroute_request.related_conflict_id if reroute_request else None),
                        related_agv_id=decision.related_agv_id if decision else None,
                    )
                if reroute_result and reroute_result.route is not None:
                    self._remember_reroute(telemetry.agv_id, state, reroute_result.reason, reroute_result.route)
                if reroute_result.success and reroute_result.route and reroute_result.strategy != RerouteStrategy.SPEED_ONLY:
                    self.activate_route(telemetry.agv_id, map_id, reroute_result.route)
            elif decision and decision.action == TrafficAction.PROCEED:
                self._clear_wait_hold(telemetry.agv_id)

            return EngineUpdateResult(
                state=state,
                snapshot=snapshot,
                conflict_result=conflict_result,
                decision=decision,
                reroute_request=reroute_request,
                reroute_result=reroute_result,
            )
