"""
traffic/planner.py  — 2.1 Planner + Map I/O
---------------------------------------------
Migrate toàn bộ từ traffic_manager.py (TrafficManager class + get_fleet_state).
Map I/O cũng nằm ở đây để tương thích — map_mgmt/map_io.py import lại từ đây.
"""
from __future__ import annotations
import networkx as nx
import json
import os
import math
import heapq


class TrafficManager:
    def __init__(self, map_file):
        self.map_file = map_file
        self.graph = nx.DiGraph()
        self.reservations = {}  # {node_id: agv_id}
        self.load_map()

    def load_map(self, file_path=None):
        if file_path:
            self.map_file = file_path

        if not os.path.exists(self.map_file):
            print("Map file not found, creating empty map.")
            return

        try:
            with open(self.map_file, 'r') as f:
                data = json.load(f)

            self.graph.clear()
            for node_id, attrs in data.get('nodes', {}).items():
                self.graph.add_node(int(node_id), **attrs)

            for edge in data.get('edges', []):
                w = edge['w']
                if w == 1:
                    n_u = self.graph.nodes.get(int(edge['u']), {})
                    n_v = self.graph.nodes.get(int(edge['v']), {})
                    geo = math.hypot(n_v.get('x', 0) - n_u.get('x', 0),
                                     n_v.get('y', 0) - n_u.get('y', 0))
                    if geo > 0:
                        w = geo
                self.graph.add_edge(edge['u'], edge['v'], weight=w, a=edge['a'])
                if 'actions'     in edge: self.graph.edges[edge['u'], edge['v']]['actions']     = edge['actions']
                if 'end_actions' in edge: self.graph.edges[edge['u'], edge['v']]['end_actions'] = edge['end_actions']
                if 'p'           in edge: self.graph.edges[edge['u'], edge['v']]['p']           = edge['p']
                self.graph.edges[edge['u'], edge['v']]['allowed']   = edge.get('allowed',   True)
                self.graph.edges[edge['u'], edge['v']]['direction']  = edge.get('direction', 'forward')

            print(f"Map loaded: {len(self.graph.nodes)} nodes, {len(self.graph.edges)} edges.")
        except Exception as e:
            print(f"Error loading map: {e}")

    def save_map(self):
        data = {"nodes": {}, "edges": []}
        for node_id, attrs in self.graph.nodes(data=True):
            data["nodes"][str(node_id)] = attrs

        for u, v, attrs in self.graph.edges(data=True):
            edge = {"u": u, "v": v, "w": attrs.get('weight', 1),
                    "a": attrs.get('a', 3), "p": attrs.get('p', 0)}
            if 'actions'     in attrs: edge['actions']     = attrs['actions']
            if 'end_actions' in attrs: edge['end_actions'] = attrs['end_actions']
            if not attrs.get('allowed', True):
                edge['allowed'] = False
            if attrs.get('direction', 'forward') != 'forward':
                edge['direction'] = attrs['direction']
            data["edges"].append(edge)

        with open(self.map_file, 'w') as f:
            json.dump(data, f, indent=4)
        print("Map saved.")

    def _allowed_view(self):
        return nx.subgraph_view(
            self.graph,
            filter_edge=lambda u, v: self.graph[u][v].get('allowed', True)
        )

    def find_path(self, start_node, end_node):
        try:
            return nx.shortest_path(self._allowed_view(),
                                    source=start_node, target=end_node, weight='weight')
        except nx.NetworkXNoPath:
            print(f"No path found from {start_node} to {end_node}")
            return None
        except Exception as e:
            print(f"Pathfinding error: {e}")
            return None

    def find_path_directed(self, start_node, end_node,
                           prev_node=None, backward_penalty=50):
        if (prev_node is None
                or not self.graph.has_node(prev_node)
                or not self.graph.has_node(start_node)
                or not self.graph.has_node(end_node)):
            return self.find_path(start_node, end_node)

        if start_node == end_node:
            return [start_node]

        INF = float('inf')
        dist      = {}
        came_from = {}
        start_state = (start_node, prev_node)
        dist[start_state] = 0
        heap = [(0, start_node, prev_node)]
        found_state = None

        while heap:
            cost, node, from_nd = heapq.heappop(heap)
            state = (node, from_nd)
            if cost > dist.get(state, INF):
                continue
            if node == end_node:
                found_state = state
                break
            for nb in self.graph.successors(node):
                if not self.graph[node][nb].get('allowed', True):
                    continue
                edge_w  = self.graph[node][nb].get('weight', 1)
                penalty = 0 if node == start_node else self._backward_cost(from_nd, node, nb, backward_penalty)
                new_cost = cost + edge_w + penalty
                ns = (nb, node)
                if new_cost < dist.get(ns, INF):
                    dist[ns]      = new_cost
                    came_from[ns] = state
                    heapq.heappush(heap, (new_cost, nb, node))

        if found_state is None:
            print(f"[DIR] {start_node}→{end_node}: no directed path, fallback.")
            return self.find_path(start_node, end_node)

        path, cur = [], found_state
        while cur is not None:
            path.append(cur[0])
            cur = came_from.get(cur)
        path.reverse()
        return path

    def _backward_cost(self, from_node, curr_node, next_node, penalty):
        try:
            pf = self.graph.nodes[from_node]
            pc = self.graph.nodes[curr_node]
            pn = self.graph.nodes[next_node]
            vin_x,  vin_y  = pc['x'] - pf['x'], pc['y'] - pf['y']
            vout_x, vout_y = pn['x'] - pc['x'],  pn['y'] - pc['y']
            mag_in  = math.sqrt(vin_x**2  + vin_y**2)
            mag_out = math.sqrt(vout_x**2 + vout_y**2)
            if mag_in < 1e-6 or mag_out < 1e-6:
                return 0
            dot = (vin_x * vout_x + vin_y * vout_y) / (mag_in * mag_out)
            return penalty if dot < -0.5 else 0
        except (KeyError, ZeroDivisionError):
            return 0

    def find_path_smart(self, start_node, end_node, prev_node=None,
                        soft_avoid=None, backward_penalty=50, soft_penalty=40):
        if not self.graph.has_node(start_node) or not self.graph.has_node(end_node):
            return self.find_path(start_node, end_node)
        if start_node == end_node:
            return [start_node]

        if soft_avoid is None:
            avoid_costs = {}
        elif isinstance(soft_avoid, dict):
            avoid_costs = soft_avoid
        else:
            avoid_costs = {n: soft_penalty for n in soft_avoid}

        G   = self.graph
        INF = float('inf')
        dist      = {}
        came_from = {}
        start_state = (start_node, prev_node)
        dist[start_state] = 0
        heap = [(0, start_node, prev_node)]
        found_state = None

        while heap:
            cost, node, from_nd = heapq.heappop(heap)
            state = (node, from_nd)
            if cost > dist.get(state, INF):
                continue
            if node == end_node:
                found_state = state
                break
            for nb in G.successors(node):
                if not G[node][nb].get('allowed', True):
                    continue
                edge_w   = G[node][nb].get('weight', 1)
                pen_bwd  = self._backward_cost(from_nd, node, nb, backward_penalty)
                pen_soft = avoid_costs.get(nb, 0)
                new_cost = cost + edge_w + pen_bwd + pen_soft
                ns = (nb, node)
                if new_cost < dist.get(ns, INF):
                    dist[ns]      = new_cost
                    came_from[ns] = state
                    heapq.heappush(heap, (new_cost, nb, node))

        if found_state is None:
            return self.find_path_directed(start_node, end_node, prev_node)

        path, cur = [], found_state
        while cur is not None:
            path.append(cur[0])
            cur = came_from.get(cur)
        path.reverse()
        return path

    def find_path_avoiding(self, start_node, end_node, avoid_nodes):
        try:
            temp_graph = self.graph.copy()
            temp_graph.remove_nodes_from(avoid_nodes)
            return nx.shortest_path(temp_graph, source=start_node,
                                    target=end_node, weight='weight')
        except (nx.NetworkXNoPath, nx.NetworkXError):
            return None

    def find_path_avoiding_edges(self, start_node, end_node,
                                 avoid_edges=None, prev_node=None,
                                 soft_avoid=None, backward_penalty=50):
        """
        Tìm đường tránh cứng một số edge cụ thể (hard-block theo cạnh).

        avoid_edges : list[(from, to)] — cạnh bị cấm hoàn toàn.
        prev_node   : node trước start (để tính backward penalty).
        soft_avoid  : dict {node: extra_cost} — tránh mềm (như find_path_smart).

        Fallback về find_path_smart nếu không tìm được.
        """
        if not self.graph.has_node(start_node) or not self.graph.has_node(end_node):
            return self.find_path(start_node, end_node)
        if start_node == end_node:
            return [start_node]

        blocked_edges = set()
        for e in (avoid_edges or []):
            blocked_edges.add((int(e[0]), int(e[1])))

        avoid_costs = dict(soft_avoid or {})
        G   = self.graph
        INF = float('inf')
        dist      = {}
        came_from = {}
        start_state = (start_node, prev_node)
        dist[start_state] = 0
        heap = [(0, start_node, prev_node)]
        found_state = None

        while heap:
            cost, node, from_nd = heapq.heappop(heap)
            state = (node, from_nd)
            if cost > dist.get(state, INF):
                continue
            if node == end_node:
                found_state = state
                break
            for nb in G.successors(node):
                if not G[node][nb].get('allowed', True):
                    continue
                if (node, nb) in blocked_edges:
                    continue                          # hard-block
                edge_w   = G[node][nb].get('weight', 1)
                pen_bwd  = self._backward_cost(from_nd, node, nb, backward_penalty)
                pen_soft = avoid_costs.get(nb, 0)
                new_cost = cost + edge_w + pen_bwd + pen_soft
                ns = (nb, node)
                if new_cost < dist.get(ns, INF):
                    dist[ns]      = new_cost
                    came_from[ns] = state
                    heapq.heappush(heap, (new_cost, nb, node))

        if found_state is None:
            # Fallback: không tránh edge nữa, dùng soft-avoid thông thường
            print(f"[PLANNER] find_path_avoiding_edges: no path "
                  f"{start_node}→{end_node} avoiding {avoid_edges}, fallback.")
            return self.find_path_smart(start_node, end_node, prev_node, soft_avoid)

        path, cur = [], found_state
        while cur is not None:
            path.append(cur[0])
            cur = came_from.get(cur)
        path.reverse()
        return path

    def add_node(self, node_id, x, y, node_type="normal", role="none", actions=None):
        if actions is None:
            actions = []
        self.graph.add_node(int(node_id), x=x, y=y, type=node_type,
                            role=role, actions=actions)

    def add_edge(self, u, v, action=3, actions=None, end_actions=None, action_param=0,
                 allowed=True, direction='forward', weight=None):
        if actions is None:     actions = []
        if end_actions is None: end_actions = []
        if weight is None:
            n_u = self.graph.nodes.get(int(u), {})
            n_v = self.graph.nodes.get(int(v), {})
            weight = math.hypot(n_v.get('x', 0) - n_u.get('x', 0),
                                n_v.get('y', 0) - n_u.get('y', 0)) or 1
        self.graph.add_edge(int(u), int(v), weight=weight, a=action, p=action_param,
                            actions=actions, end_actions=end_actions,
                            allowed=allowed, direction=direction)

    def relabel_node(self, old_id, new_id):
        if old_id in self.graph.nodes:
            nx.relabel_nodes(self.graph, {old_id: int(new_id)}, copy=False)
            print(f"Renamed node {old_id} to {new_id}")
            return True
        return False

    def clear_reservations(self, agv_id):
        keys = [k for k, v in self.reservations.items() if v == agv_id]
        for k in keys:
            del self.reservations[k]

    def try_reserve_path(self, agv_id, current_node, next_nodes):
        required_nodes = [current_node] + next_nodes
        for node, owner in list(self.reservations.items()):
            if owner == agv_id and node not in required_nodes:
                del self.reservations[node]
        for node in required_nodes:
            if node in self.reservations and self.reservations[node] != agv_id:
                return False
        for node in required_nodes:
            self.reservations[node] = agv_id
        return True

    def get_reserved_by(self, node_id):
        return self.reservations.get(node_id)

    def calculate_turn_angle(self, node_prev, node_curr, node_next):
        if not (self.graph.has_node(node_prev) and
                self.graph.has_node(node_curr) and
                self.graph.has_node(node_next)):
            return 180.0
        p1 = self.graph.nodes[node_prev]
        p2 = self.graph.nodes[node_curr]
        p3 = self.graph.nodes[node_next]
        v1x, v1y = p2['x'] - p1['x'], p2['y'] - p1['y']
        v2x, v2y = p3['x'] - p2['x'], p3['y'] - p2['y']
        if math.sqrt(v1x**2 + v1y**2) == 0 or math.sqrt(v2x**2 + v2y**2) == 0:
            return 180.0
        angle1 = math.atan2(v1y, v1x)
        angle2 = math.atan2(v2y, v2x)
        angle_deg = math.degrees(abs(angle1 - angle2))
        if angle_deg > 180:
            angle_deg = 360 - angle_deg
        return 180 - angle_deg

    def get_nodes_by_role(self, role):
        return [n for n, d in self.graph.nodes(data=True) if d.get('role') == role]

    def map_health_check(self) -> dict:
        G = self.graph
        errors, warnings = [], []
        for n in sorted(G.nodes()):
            role    = G.nodes[n].get('role', '')
            out_deg = G.out_degree(n)
            in_deg  = G.in_degree(n)
            if out_deg == 0 and role != 'charger':
                errors.append(f"SINK node {n} [{role}]: out_degree=0 — AGV đến đây bị kẹt.")
            if in_deg == 0 and role != 'charger':
                errors.append(f"SOURCE node {n} [{role}]: in_degree=0 — không có đường tiến VÀO.")
        seen = set()
        for u, v in G.edges():
            if G.has_edge(v, u) and (v, u) not in seen:
                seen.add((u, v))
                warnings.append(f"BIDIRECTIONAL {u}↔{v}: 2 chiều.")
        return {'errors': errors, 'warnings': warnings}

    def print_health_check(self):
        result = self.map_health_check()
        print(f"[MAP HEALTH] {len(self.graph.nodes)} nodes, {len(self.graph.edges)} edges")
        if result['errors']:
            for e in result['errors']:
                print(f"  ✗ {e}")
        else:
            print("  ✓ Không phát hiện lỗi nghiêm trọng.")
        for w in result['warnings']:
            print(f"  ⚠ {w}")


def get_fleet_state(agv_list: list) -> dict:
    """Snapshot trạng thái tức thời của toàn bộ fleet."""
    snapshot = {}
    for agv in agv_list:
        remaining = []
        if agv.is_navigating and agv.full_path and agv.current_tag in agv.full_path:
            idx = agv.full_path.index(agv.current_tag)
            remaining = agv.full_path[idx:]
        snapshot[agv.id] = {
            "current_tag"    : agv.current_tag,
            "next_tag"       : getattr(agv, 'next_tag', None),
            "prev_tag"       : agv.prev_tag,
            "remaining_path" : remaining,
            "task_type"      : agv.current_task_type,
            "is_navigating"  : agv.is_navigating,
        }
    return snapshot


# Alias để main_new.py có thể import: from traffic.planner import Planner
Planner = TrafficManager
