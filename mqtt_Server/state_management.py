from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import hypot
from typing import Dict, Iterable, List, Optional, Tuple
import threading


class ConflictKind(str, Enum):
    NODE = "NODE"
    EDGE_SAME_DIRECTION = "EDGE_SAME_DIRECTION"
    EDGE_HEAD_ON = "EDGE_HEAD_ON"
    EDGE_MERGE = "EDGE_MERGE"


class ConflictSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class ControlAction(str, Enum):
    PROCEED = "PROCEED"
    SLOW_DOWN = "SLOW_DOWN"
    WAIT = "WAIT"
    STOP = "STOP"


@dataclass(slots=True)
class Node:
    node_id: str
    x: float
    y: float


@dataclass(slots=True)
class Edge:
    edge_id: str
    from_node: str
    to_node: str
    length: float
    max_speed: float
    physical_edge_id: Optional[str] = None
    bidirectional: bool = False


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


@dataclass(slots=True)
class AGVState:
    agv_id: str
    timestamp: float
    x: float
    y: float
    heading_deg: float
    speed: float
    current_node: Optional[str]
    current_edge: Optional[str]
    next_node: Optional[str]
    offset_on_edge: Optional[float] = None
    route_progress_index: Optional[int] = None
    paused: bool = False
    meta: Dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class OccupancyWindow:
    agv_id: str
    resource_id: str
    resource_type: str
    time_from: float
    time_to: float
    from_node: Optional[str] = None
    to_node: Optional[str] = None
    physical_resource_id: Optional[str] = None
    segment_index: Optional[int] = None


@dataclass(slots=True)
class PredictedTrajectory:
    agv_id: str
    generated_at: float
    horizon_s: float
    windows: List[OccupancyWindow]
    eta_by_node: Dict[str, float]
    eta_by_edge: Dict[str, float]


@dataclass(slots=True)
class PredictedConflict:
    conflict_id: str
    kind: ConflictKind
    severity: ConflictSeverity
    agv_ids: Tuple[str, str]
    resource_id: str
    overlap_from: float
    overlap_to: float
    detail: str


@dataclass(slots=True)
class SpeedRecommendation:
    agv_id: str
    action: ControlAction
    target_speed: Optional[float]
    reason: str
    related_agv_id: Optional[str] = None
    related_conflict_id: Optional[str] = None


@dataclass(slots=True)
class StateSnapshot:
    generated_at: float
    states: Dict[str, AGVState]
    routes: Dict[str, PlannedRoute]
    trajectories: Dict[str, PredictedTrajectory]
    conflicts: List[PredictedConflict]
    recommendations: Dict[str, SpeedRecommendation]


class TopologyMap:
    def __init__(self, nodes: Iterable[Node], edges: Iterable[Edge]) -> None:
        self.nodes: Dict[str, Node] = {node.node_id: node for node in nodes}
        self.edges: Dict[str, Edge] = {}
        self.outgoing: Dict[str, List[Edge]] = {node_id: [] for node_id in self.nodes}

        for edge in edges:
            self._add_edge(edge)
            if edge.bidirectional:
                reverse = Edge(
                    edge_id=f"{edge.edge_id}__rev",
                    from_node=edge.to_node,
                    to_node=edge.from_node,
                    length=edge.length,
                    max_speed=edge.max_speed,
                    physical_edge_id=edge.physical_edge_id or edge.edge_id,
                    bidirectional=False,
                )
                self._add_edge(reverse)

    def _add_edge(self, edge: Edge) -> None:
        self.edges[edge.edge_id] = edge
        self.outgoing.setdefault(edge.from_node, []).append(edge)

    def get_edge(self, edge_id: str) -> Edge:
        return self.edges[edge_id]

    def get_node(self, node_id: str) -> Node:
        return self.nodes[node_id]

    def distance(self, a: str, b: str) -> float:
        left = self.get_node(a)
        right = self.get_node(b)
        return hypot(left.x - right.x, left.y - right.y)


class StateRepository:
    def __init__(self) -> None:
        self._states: Dict[str, AGVState] = {}
        self._routes: Dict[str, PlannedRoute] = {}
        self._lock = threading.RLock()

    def upsert_state(self, state: AGVState) -> None:
        with self._lock:
            self._states[state.agv_id] = state

    def upsert_route(self, route: PlannedRoute) -> None:
        with self._lock:
            self._routes[route.agv_id] = route

    def set_route(self, agv_id: str, route: Optional[PlannedRoute]) -> None:
        with self._lock:
            if route is None:
                self._routes.pop(agv_id, None)
            else:
                self._routes[agv_id] = route

    def get_state(self, agv_id: str) -> Optional[AGVState]:
        with self._lock:
            return self._states.get(agv_id)

    def get_route(self, agv_id: str) -> Optional[PlannedRoute]:
        with self._lock:
            return self._routes.get(agv_id)

    def snapshot(self) -> Tuple[Dict[str, AGVState], Dict[str, PlannedRoute]]:
        with self._lock:
            return dict(self._states), dict(self._routes)


class TrajectoryPredictor:
    def __init__(
        self,
        topology: TopologyMap,
        horizon_s: float = 8.0,
        min_speed: float = 0.1,
        node_hold_s: float = 0.5,
        edge_tail_hold_s: float = 0.25,
    ) -> None:
        self.topology = topology
        self.horizon_s = horizon_s
        self.min_speed = min_speed
        self.node_hold_s = node_hold_s
        self.edge_tail_hold_s = edge_tail_hold_s

    def predict(self, state: AGVState, route: Optional[PlannedRoute]) -> PredictedTrajectory:
        now = state.timestamp
        windows: List[OccupancyWindow] = []
        eta_by_node: Dict[str, float] = {}
        eta_by_edge: Dict[str, float] = {}

        if route is None or not route.segments:
            self._predict_stationary(now, state, windows)
            return PredictedTrajectory(state.agv_id, now, self.horizon_s, windows, eta_by_node, eta_by_edge)

        start_index = state.route_progress_index or 0
        if start_index < 0 or start_index >= len(route.segments):
            start_index = 0

        time_cursor = now
        if state.current_node:
            windows.append(
                OccupancyWindow(
                    agv_id=state.agv_id,
                    resource_id=state.current_node,
                    resource_type="NODE",
                    time_from=now,
                    time_to=now + self.node_hold_s,
                )
            )
            eta_by_node[state.current_node] = 0.0

        for idx, segment in enumerate(route.segments[start_index:], start=start_index):
            edge = self.topology.get_edge(segment.edge_id)
            travel_speed = max(min(segment.planned_speed or max(state.speed, self.min_speed), edge.max_speed), self.min_speed)
            remaining = edge.length
            if idx == start_index and state.current_edge == edge.edge_id and state.offset_on_edge is not None:
                remaining = max(0.0, edge.length - state.offset_on_edge)
            if remaining <= 0.0:
                remaining = min(edge.length, 0.01)

            travel_time = remaining / travel_speed
            edge_end = time_cursor + travel_time
            if edge_end > now + self.horizon_s:
                edge_end = now + self.horizon_s

            physical_id = edge.physical_edge_id or edge.edge_id
            windows.append(
                OccupancyWindow(
                    agv_id=state.agv_id,
                    resource_id=edge.edge_id,
                    resource_type="EDGE",
                    time_from=time_cursor,
                    time_to=edge_end,
                    from_node=edge.from_node,
                    to_node=edge.to_node,
                    physical_resource_id=physical_id,
                    segment_index=idx,
                )
            )
            edge_eta = max(0.0, time_cursor - now)
            self._record_edge_eta(eta_by_edge, edge.edge_id, edge_eta)
            self._record_edge_eta(eta_by_edge, physical_id, edge_eta)

            node_start = edge_end
            node_end = min(now + self.horizon_s, edge_end + self.node_hold_s)
            windows.append(
                OccupancyWindow(
                    agv_id=state.agv_id,
                    resource_id=edge.to_node,
                    resource_type="NODE",
                    time_from=node_start,
                    time_to=node_end,
                    from_node=edge.from_node,
                    to_node=edge.to_node,
                    segment_index=idx,
                )
            )
            eta_by_node[edge.to_node] = max(0.0, edge_end - now)

            time_cursor = edge_end + self.edge_tail_hold_s
            if time_cursor >= now + self.horizon_s:
                break

        return PredictedTrajectory(state.agv_id, now, self.horizon_s, windows, eta_by_node, eta_by_edge)

    def _predict_stationary(self, now: float, state: AGVState, windows: List[OccupancyWindow]) -> None:
        hold_to = now + self.horizon_s
        if state.current_edge:
            edge = self.topology.get_edge(state.current_edge)
            physical_id = edge.physical_edge_id or edge.edge_id
            windows.append(
                OccupancyWindow(
                    agv_id=state.agv_id,
                    resource_id=edge.edge_id,
                    resource_type="EDGE",
                    time_from=now,
                    time_to=hold_to,
                    from_node=edge.from_node,
                    to_node=edge.to_node,
                    physical_resource_id=physical_id,
                )
            )
        if state.current_node:
            windows.append(
                OccupancyWindow(
                    agv_id=state.agv_id,
                    resource_id=state.current_node,
                    resource_type="NODE",
                    time_from=now,
                    time_to=hold_to,
                )
            )

    @staticmethod
    def _record_edge_eta(eta_by_edge: Dict[str, float], resource_id: Optional[str], eta: float) -> None:
        if not resource_id:
            return
        current = eta_by_edge.get(resource_id)
        if current is None or eta < current:
            eta_by_edge[resource_id] = eta


class ConflictPredictor:
    def __init__(self, safety_gap_s: float = 0.35) -> None:
        self.safety_gap_s = safety_gap_s

    def detect(self, trajectories: Dict[str, PredictedTrajectory]) -> List[PredictedConflict]:
        conflicts: List[PredictedConflict] = []
        agv_ids = list(trajectories.keys())
        for i, left_agv in enumerate(agv_ids):
            left = trajectories[left_agv]
            for right_agv in agv_ids[i + 1 :]:
                right = trajectories[right_agv]
                conflicts.extend(self._compare_pair(left, right))
        return conflicts

    def _compare_pair(self, left: PredictedTrajectory, right: PredictedTrajectory) -> List[PredictedConflict]:
        results: List[PredictedConflict] = []
        for left_window in left.windows:
            for right_window in right.windows:
                overlap = self._overlap(left_window.time_from, left_window.time_to, right_window.time_from, right_window.time_to)
                if overlap is None:
                    continue

                if left_window.resource_type == "NODE" and right_window.resource_type == "NODE":
                    if left_window.resource_id != right_window.resource_id:
                        continue
                    results.append(
                        self._make_conflict(
                            ConflictKind.NODE,
                            left.agv_id,
                            right.agv_id,
                            left_window.resource_id,
                            overlap,
                            f"Both AGVs will occupy node {left_window.resource_id}",
                        )
                    )
                    continue

                if left_window.resource_type == "EDGE" and right_window.resource_type == "EDGE":
                    left_physical = left_window.physical_resource_id or left_window.resource_id
                    right_physical = right_window.physical_resource_id or right_window.resource_id
                    if left_physical != right_physical:
                        continue

                    if (
                        left_window.from_node == right_window.to_node
                        and left_window.to_node == right_window.from_node
                    ):
                        kind = ConflictKind.EDGE_HEAD_ON
                        detail = f"Head-on conflict on physical edge {left_physical}"
                    elif left_window.from_node == right_window.from_node and left_window.to_node == right_window.to_node:
                        kind = ConflictKind.EDGE_SAME_DIRECTION
                        detail = f"Same-direction overlap on physical edge {left_physical}"
                    else:
                        kind = ConflictKind.EDGE_MERGE
                        detail = f"Merge conflict on physical edge {left_physical}"

                    results.append(
                        self._make_conflict(kind, left.agv_id, right.agv_id, left_physical, overlap, detail)
                    )
        return results

    def _make_conflict(
        self,
        kind: ConflictKind,
        left_agv: str,
        right_agv: str,
        resource_id: str,
        overlap: Tuple[float, float],
        detail: str,
    ) -> PredictedConflict:
        overlap_from, overlap_to = overlap
        duration = max(0.0, overlap_to - overlap_from)
        severity = ConflictSeverity.WARNING
        if kind == ConflictKind.EDGE_HEAD_ON or duration >= 1.5:
            severity = ConflictSeverity.CRITICAL
        elif duration <= 0.5:
            severity = ConflictSeverity.INFO
        return PredictedConflict(
            conflict_id=f"{kind.value.lower()}_{left_agv}_{right_agv}_{resource_id}",
            kind=kind,
            severity=severity,
            agv_ids=(left_agv, right_agv),
            resource_id=resource_id,
            overlap_from=overlap_from,
            overlap_to=overlap_to,
            detail=detail,
        )

    def _overlap(self, a_from: float, a_to: float, b_from: float, b_to: float) -> Optional[Tuple[float, float]]:
        start = max(a_from, b_from) - self.safety_gap_s
        end = min(a_to, b_to) + self.safety_gap_s
        if end <= start:
            return None
        return start, end


class SpeedControlPolicy:
    def __init__(
        self,
        crawl_speed: float = 0.2,
        min_speed: float = 0.1,
        stop_distance_buffer_s: float = 0.5,
        winner_gap_s: float = 0.35,
    ) -> None:
        self.crawl_speed = crawl_speed
        self.min_speed = min_speed
        self.stop_distance_buffer_s = stop_distance_buffer_s
        self.winner_gap_s = winner_gap_s

    def recommend(
        self,
        state: AGVState,
        trajectory: PredictedTrajectory,
        trajectories: Dict[str, PredictedTrajectory],
        conflicts: Iterable[PredictedConflict],
        locked_winner_agv: Optional[str] = None,
    ) -> SpeedRecommendation:
        relevant = [conflict for conflict in conflicts if state.agv_id in conflict.agv_ids]
        if not relevant:
            return SpeedRecommendation(state.agv_id, ControlAction.PROCEED, None, "No predicted conflicts")

        critical = [conflict for conflict in relevant if conflict.severity == ConflictSeverity.CRITICAL]
        target = critical[0] if critical else relevant[0]
        other_agv = target.agv_ids[1] if target.agv_ids[0] == state.agv_id else target.agv_ids[0]
        eta = self._eta_to_resource(state.agv_id, target.resource_id, trajectory)
        other_trajectory = trajectories.get(other_agv)
        other_eta = self._eta_to_resource(other_agv, target.resource_id, other_trajectory) if other_trajectory else None

        if locked_winner_agv is not None:
            if state.agv_id == locked_winner_agv:
                return SpeedRecommendation(
                    agv_id=state.agv_id,
                    action=ControlAction.PROCEED,
                    target_speed=None,
                    reason=f"Winner lock on conflict resource {target.resource_id}",
                    related_agv_id=other_agv,
                    related_conflict_id=target.conflict_id,
                )
            slowdown = self._slowdown_recommendation(
                state=state,
                trajectory=trajectory,
                target=target,
                other_agv=other_agv,
                delay_needed=self.stop_distance_buffer_s,
            )
            if slowdown is not None:
                return slowdown
            return SpeedRecommendation(
                agv_id=state.agv_id,
                action=ControlAction.WAIT,
                target_speed=0.0,
                reason=f"Yield to locked winner {locked_winner_agv} on {target.resource_id}",
                related_agv_id=other_agv,
                related_conflict_id=target.conflict_id,
            )

        if eta is None:
            return SpeedRecommendation(
                agv_id=state.agv_id,
                action=ControlAction.WAIT,
                target_speed=0.0,
                reason=f"Conflict on {target.resource_id} with unknown ETA; safest action is wait",
                related_agv_id=other_agv,
                related_conflict_id=target.conflict_id,
            )

        if other_eta is not None:
            eta_gap = eta - other_eta
            if eta_gap <= -self.winner_gap_s:
                return SpeedRecommendation(
                    agv_id=state.agv_id,
                    action=ControlAction.PROCEED,
                    target_speed=None,
                    reason=f"ETA winner on conflict resource {target.resource_id}",
                    related_agv_id=other_agv,
                    related_conflict_id=target.conflict_id,
                )

            if eta_gap >= self.winner_gap_s:
                delay_needed = eta_gap + self.stop_distance_buffer_s
                slowdown = self._slowdown_recommendation(
                    state=state,
                    trajectory=trajectory,
                    target=target,
                    other_agv=other_agv,
                    delay_needed=delay_needed,
                )
                if slowdown is not None:
                    return slowdown
                return SpeedRecommendation(
                    agv_id=state.agv_id,
                    action=ControlAction.WAIT,
                    target_speed=0.0,
                    reason=f"Yield to {other_agv} on conflict resource {target.resource_id}",
                    related_agv_id=other_agv,
                    related_conflict_id=target.conflict_id,
                )

            slowdown = self._slowdown_recommendation(
                state=state,
                trajectory=trajectory,
                target=target,
                other_agv=other_agv,
                delay_needed=self.stop_distance_buffer_s,
            )
            if slowdown is not None:
                return slowdown

        safe_arrival = target.overlap_to + self.stop_distance_buffer_s
        if safe_arrival <= trajectory.generated_at:
            return SpeedRecommendation(state.agv_id, ControlAction.PROCEED, None, "Conflict already cleared in prediction horizon")

        wait_time = safe_arrival - (trajectory.generated_at + eta)
        if wait_time <= 0.0:
            return SpeedRecommendation(
                agv_id=state.agv_id,
                action=ControlAction.PROCEED,
                target_speed=None,
                reason=f"Trajectory already clears {target.resource_id} safely",
                related_agv_id=other_agv,
                related_conflict_id=target.conflict_id,
            )

        slowdown = self._slowdown_recommendation(
            state=state,
            trajectory=trajectory,
            target=target,
            other_agv=other_agv,
            delay_needed=wait_time,
        )
        if slowdown is not None:
            return slowdown

        return SpeedRecommendation(
            agv_id=state.agv_id,
            action=ControlAction.WAIT,
            target_speed=0.0,
            reason=f"Hold before conflict resource {target.resource_id}",
            related_agv_id=other_agv,
            related_conflict_id=target.conflict_id,
        )

    def _slowdown_recommendation(
        self,
        state: AGVState,
        trajectory: PredictedTrajectory,
        target: PredictedConflict,
        other_agv: str,
        delay_needed: float,
    ) -> Optional[SpeedRecommendation]:
        eta = self._eta_to_resource(state.agv_id, target.resource_id, trajectory)
        if eta is None or delay_needed <= 0.0:
            return None
        if state.speed <= self.min_speed:
            return None

        remaining_distance = max(0.1, state.speed * max(eta, self.stop_distance_buffer_s))
        delayed_speed = remaining_distance / max(eta + delay_needed, self.min_speed)
        delayed_speed = max(self.min_speed, min(delayed_speed, state.speed))
        if delayed_speed < self.crawl_speed:
            return None

        return SpeedRecommendation(
            agv_id=state.agv_id,
            action=ControlAction.SLOW_DOWN,
            target_speed=delayed_speed,
            reason=f"Reduce speed to defer arrival at {target.resource_id}",
            related_agv_id=other_agv,
            related_conflict_id=target.conflict_id,
        )

    @staticmethod
    def _eta_to_resource(agv_id: str, resource_id: str, trajectory: PredictedTrajectory) -> Optional[float]:
        if trajectory is None:
            return None
        if resource_id in trajectory.eta_by_node:
            return trajectory.eta_by_node[resource_id]
        if resource_id in trajectory.eta_by_edge:
            return trajectory.eta_by_edge[resource_id]
        for window in trajectory.windows:
            if window.agv_id == agv_id and window.resource_id == resource_id:
                return max(0.0, window.time_from - trajectory.generated_at)
            if window.agv_id == agv_id and window.physical_resource_id == resource_id:
                return max(0.0, window.time_from - trajectory.generated_at)
        return None

class StateManagementEngine:
    def __init__(
        self,
        topology: TopologyMap,
        horizon_s: float = 8.0,
        safety_gap_s: float = 0.35,
        winner_lock_ttl_s: float = 2.5,
    ) -> None:
        self.topology = topology
        self.repository = StateRepository()
        self.trajectory_predictor = TrajectoryPredictor(topology, horizon_s=horizon_s)
        self.conflict_predictor = ConflictPredictor(safety_gap_s=safety_gap_s)
        self.speed_policy = SpeedControlPolicy()
        self.winner_lock_ttl_s = winner_lock_ttl_s
        self._winner_locks: Dict[str, Dict[str, object]] = {}

    def upsert_state(self, state: AGVState) -> None:
        self.repository.upsert_state(state)

    def upsert_route(self, route: PlannedRoute) -> None:
        self.repository.upsert_route(route)

    def set_route(self, agv_id: str, route: Optional[PlannedRoute]) -> None:
        self.repository.set_route(agv_id, route)

    def lock_conflict_winner(
        self,
        conflict: PredictedConflict,
        winner_agv: str,
        generated_at: Optional[float] = None,
    ) -> None:
        now = generated_at if generated_at is not None else 0.0
        self._winner_locks[self._winner_lock_key(conflict)] = {
            "winner_agv": winner_agv,
            "expires_at": now + self.winner_lock_ttl_s,
        }

    def build_snapshot(self, at_time: Optional[float] = None) -> StateSnapshot:
        states, routes = self.repository.snapshot()
        if not states:
            generated_at = at_time or 0.0
            return StateSnapshot(generated_at, {}, {}, {}, [], {})

        generated_at = at_time if at_time is not None else max(state.timestamp for state in states.values())
        trajectories: Dict[str, PredictedTrajectory] = {}
        for agv_id, state in states.items():
            trajectories[agv_id] = self.trajectory_predictor.predict(state, routes.get(agv_id))

        conflicts = self.conflict_predictor.detect(trajectories)
        winner_locks = self._refresh_winner_locks(generated_at, trajectories, conflicts)
        recommendations: Dict[str, SpeedRecommendation] = {}
        for agv_id, state in states.items():
            locked_winner_agv = None
            for conflict in conflicts:
                if agv_id not in conflict.agv_ids:
                    continue
                lock_key = self._winner_lock_key(conflict)
                lock = winner_locks.get(lock_key)
                if lock is not None:
                    locked_winner_agv = str(lock["winner_agv"])
                    break
            recommendations[agv_id] = self.speed_policy.recommend(
                state,
                trajectories[agv_id],
                trajectories,
                conflicts,
                locked_winner_agv=locked_winner_agv,
            )

        return StateSnapshot(
            generated_at=generated_at,
            states=states,
            routes=routes,
            trajectories=trajectories,
            conflicts=conflicts,
            recommendations=recommendations,
        )

    @staticmethod
    def _winner_lock_key(conflict: PredictedConflict) -> str:
        agv_pair = "::".join(sorted(conflict.agv_ids))
        return f"{conflict.kind.value}:{conflict.resource_id}:{agv_pair}"

    def _refresh_winner_locks(
        self,
        generated_at: float,
        trajectories: Dict[str, PredictedTrajectory],
        conflicts: List[PredictedConflict],
    ) -> Dict[str, Dict[str, object]]:
        active_keys: set[str] = set()
        refreshed: Dict[str, Dict[str, object]] = {}
        for conflict in conflicts:
            key = self._winner_lock_key(conflict)
            active_keys.add(key)
            existing = self._winner_locks.get(key)
            if existing is not None and float(existing.get("expires_at", 0.0) or 0.0) > generated_at:
                refreshed[key] = existing
                continue

            left_agv, right_agv = conflict.agv_ids
            left_eta = self.speed_policy._eta_to_resource(left_agv, conflict.resource_id, trajectories.get(left_agv))
            right_eta = self.speed_policy._eta_to_resource(right_agv, conflict.resource_id, trajectories.get(right_agv))
            if left_eta is None and right_eta is None:
                continue

            if right_eta is None or (left_eta is not None and left_eta <= right_eta):
                winner_agv = left_agv
            else:
                winner_agv = right_agv

            refreshed[key] = {
                "winner_agv": winner_agv,
                "expires_at": generated_at + self.winner_lock_ttl_s,
            }

        self._winner_locks = {
            key: value
            for key, value in refreshed.items()
            if key in active_keys and float(value.get("expires_at", 0.0) or 0.0) > generated_at
        }
        return self._winner_locks
