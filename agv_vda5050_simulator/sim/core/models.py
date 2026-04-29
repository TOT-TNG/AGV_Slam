from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(slots=True)
class Pose2D:
    x: float
    y: float
    theta: float = 0.0


@dataclass(slots=True)
class Velocity2D:
    linear: float = 0.0
    angular: float = 0.0


@dataclass(slots=True)
class VehicleSize:
    length: float
    width: float


@dataclass
class RouteProgress:
    order_id: str = ''
    order_update_id: int = 0
    path_nodes: List[str] = field(default_factory=list)
    current_index: int = 0
    goal_node_id: Optional[str] = None

    @property
    def active(self) -> bool:
        return len(self.path_nodes) > 0 and self.current_index < len(self.path_nodes)

    @property
    def current_target_node(self) -> Optional[str]:
        if not self.active:
            return None
        return self.path_nodes[self.current_index]

    @property
    def previous_node(self) -> Optional[str]:
        if self.current_index <= 0 or not self.path_nodes:
            return None
        return self.path_nodes[self.current_index - 1]
