"""
main_new.py  — Entry Point (sau tái cấu trúc)
----------------------------------------------
Chỉ làm 4 việc:
  1. Load config
  2. Khởi tạo AppContext (inject tất cả singleton)
  3. Wire MQTT protocol
  4. Khởi động GUI + API server

Không chứa business logic.
Đổi tên thành main.py khi migration hoàn tất.
"""
from __future__ import annotations


def main():
    # ── 1. Load config ────────────────────────────────────────────────
    from config_mgmt.settings_io import load_config
    config = load_config()

    # ── 2. Khởi tạo AppContext ────────────────────────────────────────
    from core.context import AppContext
    from traffic.planner           import Planner
    from traffic.reservation       import ZoneManager
    from traffic.conflict_manager  import WHCAPlanner, RollingRePlanner
    from traffic.fleet_state       import FleetStateManager
    from traffic.edge_reservation  import EdgeReservationManager
    from agv.workflow_engine        import WorkflowEngine
    from simulation.simulation_engine import SimulationEngine
    from dispatch.request_handler   import RequestHandler
    from dispatch.scheduler         import Scheduler
    import os

    map_path = os.path.join('config', 'map_data.json')

    ctx = AppContext(config=config)
    ctx.planner         = Planner(map_path)
    zones_path = os.path.join('config', 'zones.json')
    ctx.zone_mgr        = ZoneManager(zones_path if os.path.exists(zones_path) else "")
    ctx.whca            = WHCAPlanner(ctx, lookahead=config.get('lookahead', 6))
    ctx.replanner       = RollingRePlanner(ctx)
    ctx.fleet_state     = FleetStateManager(ctx)
    ctx.edge_mgr        = EdgeReservationManager()
    ctx.workflow_engine = WorkflowEngine('config/tag_actions.json')
    ctx.sim_engine      = SimulationEngine(ctx.planner, config)
    ctx.request_handler = RequestHandler(ctx)
    ctx.scheduler       = Scheduler(ctx)

    # Khởi tạo AGV instances từ config
    from agv.agv_instance import AGV
    import paho.mqtt.client as mqtt_lib
    mqtt_client = mqtt_lib.Client(mqtt_lib.CallbackAPIVersion.VERSION1, "Python_Manager_Server")
    ctx.mqtt = mqtt_client
    for agv_cfg in config.get('agvs', []):
        agv_cfg_full = {**agv_cfg,
                        'factory':  config.get('factory', 'default'),
                        'hardware': config.get('hardware', 'hardware')}
        agv = AGV(agv_cfg_full, mqtt_client)
        agv.app_config = config
        agv.zone_mgr   = ctx.zone_mgr
        agv.edge_mgr   = ctx.edge_mgr
        ctx.agv_list.append(agv)

    # ── 3. Wire MQTT ─────────────────────────────────────────────────
    from protocol import mqtt_client as mqtt_setup
    mqtt_setup.setup(ctx)

    # ── 4. Launch GUI + API ───────────────────────────────────────────
    from gui.app_shell import AppShell
    app = AppShell(ctx)
    ctx.gui_app = app
    app.mainloop()


if __name__ == '__main__':
    main()
