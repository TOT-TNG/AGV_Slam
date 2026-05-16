"""
map_mgmt/map_io.py  — 5. Map Management
-----------------------------------------
Thin wrappers — delegates sang traffic.planner.TrafficManager.
Tất cả logic I/O đã migrate vào TrafficManager (traffic/planner.py).

Dùng trực tiếp TrafficManager nếu cần đầy đủ API (load/save/add_node/add_edge...).
"""
from __future__ import annotations
import json
import math
import networkx as nx


def load_map(filepath: str) -> nx.DiGraph:
    """Tải bản đồ từ file JSON → NetworkX DiGraph."""
    import os
    graph = nx.DiGraph()
    if not os.path.exists(filepath):
        return graph
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        for node_id, attrs in data.get('nodes', {}).items():
            graph.add_node(int(node_id), **attrs)
        for edge in data.get('edges', []):
            w = edge['w']
            if w == 1:
                n_u = graph.nodes.get(int(edge['u']), {})
                n_v = graph.nodes.get(int(edge['v']), {})
                geo = math.hypot(n_v.get('x', 0) - n_u.get('x', 0),
                                 n_v.get('y', 0) - n_u.get('y', 0))
                if geo > 0:
                    w = geo
            graph.add_edge(edge['u'], edge['v'], weight=w, a=edge['a'])
            e = graph.edges[edge['u'], edge['v']]
            if 'actions'     in edge: e['actions']     = edge['actions']
            if 'end_actions' in edge: e['end_actions'] = edge['end_actions']
            if 'p'           in edge: e['p']           = edge['p']
            e['allowed']   = edge.get('allowed',   True)
            e['direction'] = edge.get('direction', 'forward')
        print(f"[map_io] Loaded: {len(graph.nodes)} nodes, {len(graph.edges)} edges.")
    except Exception as exc:
        print(f"[map_io] Error loading map: {exc}")
    return graph


def save_map(graph: nx.DiGraph, filepath: str):
    """Lưu DiGraph → file JSON."""
    data = {"nodes": {}, "edges": []}
    for node_id, attrs in graph.nodes(data=True):
        data["nodes"][str(node_id)] = attrs
    for u, v, attrs in graph.edges(data=True):
        edge = {"u": u, "v": v, "w": attrs.get('weight', 1),
                "a": attrs.get('a', 3), "p": attrs.get('p', 0)}
        if 'actions'     in attrs: edge['actions']     = attrs['actions']
        if 'end_actions' in attrs: edge['end_actions'] = attrs['end_actions']
        if not attrs.get('allowed', True):
            edge['allowed'] = False
        if attrs.get('direction', 'forward') != 'forward':
            edge['direction'] = attrs['direction']
        data["edges"].append(edge)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)
    print(f"[map_io] Map saved to {filepath}.")
