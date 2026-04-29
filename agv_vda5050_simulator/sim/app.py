from __future__ import annotations

from pathlib import Path
from typing import Any

from sim.core.simulator import Simulator
from sim.map.loader import load_graph, load_json
from sim.ui.pygame_app import PygameApp
from sim.utils.helpers import ensure_generated_map


def run() -> None:
    root = Path(__file__).resolve().parent.parent
    cfg = load_json(root / 'config' / 'simulator.json')
    ensure_generated_map(root / cfg['map']['background'], root / cfg['map']['graph_file'])
    graph_file = root / cfg['map']['graph_file']
    graph_data = load_json(graph_file)
    if isinstance(graph_data.get('agvs'), list):
        cfg['agvs'] = graph_data['agvs']
    if isinstance(graph_data.get('humans'), list):
        cfg['humans'] = graph_data['humans']
    if isinstance(graph_data.get('elevators'), list):
        cfg['elevators'] = graph_data['elevators']
    graph = load_graph(graph_file)
    configured_map_id = str((cfg.get('map') or {}).get('map_id') or '').strip()
    if configured_map_id:
        graph.map_id = configured_map_id

    simulator = Simulator(root=root, config=cfg, graph=graph)
    app = PygameApp(root=root, config=cfg, graph=graph, simulator=simulator)
    app.run()
