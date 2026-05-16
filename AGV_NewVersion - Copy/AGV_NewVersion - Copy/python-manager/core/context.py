"""
core/context.py
---------------
AppContext: Đối tượng trung tâm chứa toàn bộ singleton và shared state.
Thay thế pattern module-level globals trong main.py cũ.

Cách dùng:
    ctx = AppContext(config)
    ctx.agv_list.append(agv)
    ctx.mqtt.publish(...)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agv.agv_instance          import AGV
    from traffic.planner           import Planner
    from traffic.reservation       import ZoneManager
    from traffic.conflict_manager  import WHCAPlanner, RollingRePlanner
    from traffic.fleet_state       import FleetStateManager
    from traffic.edge_reservation  import EdgeReservationManager
    from agv.workflow_engine       import WorkflowEngine
    from simulation.simulation_engine import SimulationEngine


@dataclass
class AppContext:
    """
    Shared application context — được inject vào mọi subsystem.

    Tạo một lần duy nhất trong main.py, truyền xuống tất cả module
    thay vì dùng global variables.
    """
    # ── Config ────────────────────────────────────────────────────────────────
    config: dict = field(default_factory=dict)

    # ── Fleet ─────────────────────────────────────────────────────────────────
    agv_list: list = field(default_factory=list)           # List[AGV]
    order_queue: list = field(default_factory=list)        # List[dict] — hàng đợi nhiệm vụ

    # ── MQTT ──────────────────────────────────────────────────────────────────
    mqtt: Any = None                    # paho.mqtt.client.Client
    mqtt_connected: bool = False

    # ── Traffic subsystems ────────────────────────────────────────────────────
    planner: Any = None                 # traffic.planner.Planner
    zone_mgr: Any = None               # traffic.reservation.ZoneManager
    whca: Any = None                   # traffic.conflict_manager.WHCAPlanner
    replanner: Any = None              # traffic.conflict_manager.RollingRePlanner
    fleet_state: Any = None            # traffic.fleet_state.FleetStateManager
    edge_mgr: Any = None               # traffic.edge_reservation.EdgeReservationManager

    # ── Workflow & engines ────────────────────────────────────────────────────
    workflow_engine: Any = None        # agv.workflow_engine.WorkflowEngine
    sim_engine: Any = None             # simulation.simulation_engine.SimulationEngine

    # ── Dispatch subsystems ───────────────────────────────────────────────────
    request_handler: Any = None          # dispatch.request_handler.RequestHandler
    scheduler: Any = None               # dispatch.scheduler.Scheduler

    # ── GUI reference (optional — set sau khi App khởi tạo) ─────────────────
    gui_app: Any = None
