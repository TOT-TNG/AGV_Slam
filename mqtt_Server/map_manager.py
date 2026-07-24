import networkx as nx


class MapManager:
    """
    Xây graph từ DB (bảng agv_map_roads / agv_map_benziers) để tìm đường ngắn nhất theo map đang chọn.
    """

    def __init__(self):
        self.graph = nx.Graph()
        self.current_map_id = None

        # Dùng cho planner / nearest node:
        # { "19": (x, y), "20": (x, y), ... }
        self.points = {}

        # Dùng cho UI nếu cần:
        # [ {name_id, name, x, y, action}, ... ]
        self.robot_points = []

        # Toàn bộ road data (có speed, move_direction) cho topology builder và export
        self.roads = []   # [ {id_source, id_dest, speed, move_direction, distance, width} ]
        self.all_points = []  # [ {name_id, name, x, y, action, agv_compat} ] đầy đủ cho export

        # Sub-graph và points chỉ dành cho Line AGV (node có agvCompat RFID/both)
        self.line_graph   = nx.DiGraph()
        self.line_points:  dict = {}   # {name_id: (x, y)}
        self.node_actions: dict = {}   # {name_id: action_dict} chứa fwd_turn/bwd_turn

    async def resolve_map_id(self, pool, value: str):
        """
        Cho phép truyền vào map_id hoặc map name.
        Trả về map_id thật (id trong bảng agv_maps) nếu tìm thấy.
        """
        if not value:
            return None

        value = str(value).strip()
        print(f"[MapManager] resolve_map_id() input = {value}")

        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, name
                FROM agv_maps
                WHERE CAST(id AS TEXT) = $1 OR name = $1
                LIMIT 1
                """,
                value,
            )

        if row:
            print(f"[MapManager] resolve_map_id() matched: id={row['id']} | name={row['name']}")
            return str(row["id"])

        print(f"[MapManager] resolve_map_id() NOT FOUND for value={value}")
        return None

    async def load_from_db(self, pool, map_id: str):
        """
        Đọc roads từ DB và build graph. Cache theo map_id thật.
        """
        if not map_id:
            raise ValueError("map_id is required to load graph")

        map_id = str(map_id).strip()

        if self.current_map_id == map_id and self.graph.number_of_nodes() > 0:
            print(f"[MapManager] Using cached graph | map_id={map_id}")
            return

        # DiGraph để pathfinding tôn trọng chiều đi (move_direction)
        g = nx.DiGraph()

        async with pool.acquire() as conn:
            roads = await conn.fetch(
                """
                SELECT id_source, id_dest, distance, speed, speed_bwd, move_direction, width,
                       COALESCE(lidar_off, FALSE) AS lidar_off,
                       COALESCE(lidar_off_dir, 'none') AS lidar_off_dir
                FROM agv_map_roads
                WHERE CAST(map_id AS TEXT) = $1
                """,
                map_id,
            )

            benziers = await conn.fetch(
                """
                SELECT id_source, id_dest, speed, speed_bwd, move_direction,
                       point_start_x, point_start_y, point_end_x, point_end_y,
                       COALESCE(lidar_off, FALSE) AS lidar_off,
                       COALESCE(lidar_off_dir, 'none') AS lidar_off_dir
                FROM agv_map_benziers
                WHERE CAST(map_id AS TEXT) = $1
                """,
                map_id,
            )

            points = await conn.fetch(
                """
                SELECT name_id, x, y, name, action
                FROM agv_map_points
                WHERE CAST(map_id AS TEXT) = $1
                """,
                map_id,
            )

        roads_data = []
        for r in roads:
            src = str(r["id_source"])
            dst = str(r["id_dest"])
            weight = float(r["distance"]) if r["distance"] is not None else 1.0
            speed  = float(r["speed"])  if r["speed"]    is not None else 0.5
            mdir   = int(r["move_direction"]) if r["move_direction"] is not None else 0
            width  = float(r["width"]) if r["width"] is not None else 0.95
            attrs  = dict(weight=weight, speed=speed, move_direction=mdir)

            g.add_node(src)
            g.add_node(dst)

            # 0=both, 1=forward(src→dst), 2=backward(dst→src), 3=blocked
            if mdir == 0:           # 2 chiều
                g.add_edge(src, dst, **attrs)
                g.add_edge(dst, src, **attrs)
            elif mdir == 1:         # 1 chiều tiến
                g.add_edge(src, dst, **attrs)
            elif mdir == 2:         # 1 chiều lùi (đảo hướng)
                g.add_edge(dst, src, **attrs)
            # mdir == 3 (blocked): thêm node nhưng không thêm edge

            lidar_off     = bool(r["lidar_off"]) if r["lidar_off"] is not None else False
            lidar_off_dir = str(r["lidar_off_dir"] or "none").strip().lower()
            speed_bwd     = float(r["speed_bwd"]) if r["speed_bwd"] is not None else None
            roads_data.append({
                "id_source": src, "id_dest": dst,
                "speed": speed, "speed_bwd": speed_bwd, "move_direction": mdir,
                "distance": weight, "width": width,
                "lidar_off": lidar_off,
                "lidar_off_dir": lidar_off_dir,
            })

        for b in benziers:
            src = str(b["id_source"])
            dst = str(b["id_dest"])
            b_speed = float(b["speed"]) if b["speed"] is not None else 0.5
            b_mdir  = int(b["move_direction"]) if b["move_direction"] is not None else 0
            # Tính distance từ tọa độ đầu-cuối
            try:
                dx = float(b["point_end_x"]) - float(b["point_start_x"])
                dy = float(b["point_end_y"]) - float(b["point_start_y"])
                b_weight = (dx**2 + dy**2) ** 0.5 or 1.0
            except Exception:
                b_weight = 1.0
            b_lidar_off     = bool(b["lidar_off"]) if b.get("lidar_off") is not None else False
            b_lidar_off_dir = str(b.get("lidar_off_dir") or "none").strip().lower()
            b_speed_bwd     = float(b["speed_bwd"]) if b.get("speed_bwd") is not None else None
            b_attrs = dict(weight=b_weight, speed=b_speed, move_direction=b_mdir)
            g.add_node(src)
            g.add_node(dst)
            if b_mdir == 0:
                g.add_edge(src, dst, **b_attrs)
                g.add_edge(dst, src, **b_attrs)
            elif b_mdir == 1:
                g.add_edge(src, dst, **b_attrs)
            elif b_mdir == 2:
                g.add_edge(dst, src, **b_attrs)
            roads_data.append({
                "id_source": src, "id_dest": dst,
                "speed": b_speed, "speed_bwd": b_speed_bwd, "move_direction": b_mdir,
                "distance": b_weight, "width": 0.3,
                "lidar_off": b_lidar_off,
                "lidar_off_dir": b_lidar_off_dir,
            })

        # Dữ liệu point cho planner
        point_dict = {
            str(p["name_id"]): (float(p["x"]), float(p["y"]))
            for p in points
        }

        import json as _json_mm
        all_points = []
        rfid_node_ids: set = set()
        for row in points:
            try:
                act = row["action"] or {}
                if isinstance(act, str):
                    act = _json_mm.loads(act)
            except Exception:
                act = {}
            agv_compat = str(act.get("agvCompat") or "slam_qr")
            nid = str(row["name_id"])
            all_points.append({
                "name_id":   nid,
                "name":      row["name"] or "",
                "x":         float(row["x"]),
                "y":         float(row["y"]),
                "action":    row["action"] if row["action"] is not None else None,
                "agv_compat": agv_compat,
            })
            if agv_compat in ("RFID", "both"):
                rfid_node_ids.add(nid)

        # Sub-graph cho Line AGV: chỉ bao gồm node RFID / both
        line_g = g.__class__()
        for nid in rfid_node_ids:
            if g.has_node(nid):
                line_g.add_node(nid)
        for u, v, data in g.edges(data=True):
            if u in rfid_node_ids and v in rfid_node_ids:
                line_g.add_edge(u, v, **data)
        line_points = {nid: xy for nid, xy in point_dict.items() if nid in rfid_node_ids}

        # Dữ liệu point cho UI / debug nếu cần
        robot_points = all_points[:]

        # node_actions: {name_id_str: action_dict} — dùng để đọc fwd_turn/bwd_turn
        node_actions: dict = {}
        for row in points:
            nid = str(row["name_id"])
            try:
                act = row["action"] or {}
                if isinstance(act, str):
                    act = _json_mm.loads(act)
            except Exception:
                act = {}
            node_actions[nid] = act

        self.graph = g
        self.points = point_dict
        self.robot_points = robot_points
        self.all_points = all_points
        self.roads = roads_data
        self.current_map_id = map_id
        self.line_graph   = line_g
        self.line_points  = line_points
        self.node_actions = node_actions  # {nid: {agvCompat, fwd_turn, bwd_turn, ...}}

        print(
            f"[MapManager] Loaded graph from DB | map_id={map_id} | "
            f"nodes={g.number_of_nodes()} | edges={g.number_of_edges()}"
        )
        print(f"[MapManager] Points loaded for planner: {len(self.points)}")
        print(f"[MapManager] Points loaded for UI: {len(self.robot_points)}")
        print(f"[MapManager] Line AGV nodes (RFID/both): {len(rfid_node_ids)}")

    def nearest_node(self, x: float, y: float):
        """Tìm node gần nhất theo tọa độ (x,y) từ agv_map_points đã load."""
        if not self.points:
            return None

        best = None
        best_dist = None

        for name_id, (px, py) in self.points.items():
            d2 = (px - x) ** 2 + (py - y) ** 2
            if best_dist is None or d2 < best_dist:
                best_dist = d2
                best = name_id

        return best

    def shortest_path(self, start: str, end: str):
        if self.graph.number_of_nodes() == 0:
            print("[MapManager] Graph empty, call load_from_db before shortest_path")
            return None

        try:
            path = nx.shortest_path(
                self.graph,
                source=str(start),
                target=str(end),
                weight="weight"
            )
            print(f"[MapManager] Đường đi ngắn nhất: {' → '.join(path)}")
            return path

        except nx.NodeNotFound as e:
            print(f"[MapManager] Lỗi NodeNotFound: {e}")
            print(f"[MapManager] Nodes hiện có: {list(self.graph.nodes)}")
            return None

    def line_shortest_path(self, start: str, end: str):
        """Tìm đường đi cho Line AGV — chỉ qua node RFID/both.
        Fallback về full graph nếu line_graph chưa có node (map chưa set agvCompat).
        """
        g = self.line_graph
        if g is None or g.number_of_nodes() == 0:
            print("[MapManager] line_graph rỗng — fallback full graph (map chưa cấu hình agvCompat)")
            return self.shortest_path(start, end)
        # Kiểm tra node start/end có trong line_graph không
        if not g.has_node(str(start)) or not g.has_node(str(end)):
            missing = []
            if not g.has_node(str(start)): missing.append(f"start={start}")
            if not g.has_node(str(end)):   missing.append(f"end={end}")
            print(f"[MapManager] line_graph thiếu node {missing} — fallback full graph")
            return self.shortest_path(start, end)
        try:
            path = nx.shortest_path(g, source=str(start), target=str(end), weight="weight")
            print(f"[MapManager] Line AGV path: {' → '.join(path)}")
            return path
        except nx.NetworkXNoPath:
            print(f"[MapManager] line_graph: không có đường {start}→{end} — fallback full graph")
            return self.shortest_path(start, end)
        except nx.NodeNotFound as e:
            print(f"[MapManager] line_shortest_path NodeNotFound: {e}")
            return None

        except nx.NetworkXNoPath:
            print(f"[MapManager] Không có đường đi từ {start} đến {end}")
            print(f"[MapManager] Edges: {list(self.graph.edges)}")
            return None

    def line_directional_path(self, start: str, end: str, came_from: str | None) -> list | None:
        """
        Tìm đường cho Line AGV có xét đến hướng hiện tại và quyền quay tại node.

        came_from: node AGV vừa đến start từ đó (prev_tag).
        Thuật toán: Augmented A* với state (node, prev_node).
        - Nếu cần quay tại node X mà X có turn_allowed=no: bỏ qua nhánh đó.
        - Cho phép lùi (backward movement) với penalty nhỏ để tránh kẹt.
        - Fallback: line_shortest_path nếu không tìm được đường thỏa mãn.
        """
        import math
        from heapq import heappush, heappop
        from line_agv_plan_builder import get_turn_direction

        if not came_from:
            return self.line_shortest_path(start, end)

        g = self.line_graph
        if g is None or g.number_of_nodes() < 2:
            return self.shortest_path(start, end)

        start, end, came_from = str(start), str(end), str(came_from)
        if not g.has_node(start) or not g.has_node(end):
            return self.line_shortest_path(start, end)

        points       = self.line_points or self.points
        node_actions = self.node_actions

        def h(nid: str) -> float:
            p1, p2 = points.get(nid), points.get(end)
            return math.hypot(p1[0]-p2[0], p1[1]-p2[1]) if p1 and p2 else 0.0

        BWD_PENALTY  = 2.0   # Cost thêm cho mỗi bước lùi (ưu tiên tiến)
        TURN_PENALTY = 0.5   # Cost thêm khi phải quay (ưu tiên thẳng)

        # State: (node_id, came_from_id)
        counter  = 0
        best_g: dict[tuple[str,str], float] = {}
        init_state = (start, came_from)
        init_g     = 0.0
        best_g[init_state] = init_g
        # heap: (f, counter, node, prev, path)
        open_set = [(init_g + h(start), counter, start, came_from, [start])]

        while open_set:
            f, _, cur, prev, path = heappop(open_set)
            state = (cur, prev)
            g_cur = best_g.get(state, float('inf'))
            # Stale check
            if f - h(cur) > g_cur + 1e-6:
                continue

            if cur == end:
                return path

            for nbr, edata in g[cur].items():
                edge_w = float(edata.get('weight', 1.0))

                if nbr == prev:
                    # Backward movement: lùi về node trước đó
                    new_g = g_cur + edge_w + BWD_PENALTY
                else:
                    turn = get_turn_direction(prev, cur, nbr, points)
                    ta   = str(node_actions.get(cur, {}).get('turn_allowed', 'yes')).lower()
                    if turn is not None and ta == 'no':
                        continue  # không được quay ở đây
                    new_g = g_cur + edge_w + (TURN_PENALTY if turn is not None else 0.0)

                new_state = (nbr, cur)
                if new_g < best_g.get(new_state, float('inf')):
                    best_g[new_state] = new_g
                    counter += 1
                    heappush(open_set, (new_g + h(nbr), counter, nbr, cur, path + [nbr]))

        print(f"[MapManager] directional path không tìm được {start}→{end} (came_from={came_from}), fallback")
        return self.line_shortest_path(start, end)
