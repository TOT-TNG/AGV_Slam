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

        g = nx.Graph()

        async with pool.acquire() as conn:
            roads = await conn.fetch(
                """
                SELECT id_source, id_dest, distance
                FROM agv_map_roads
                WHERE CAST(map_id AS TEXT) = $1
                """,
                map_id,
            )

            benziers = await conn.fetch(
                """
                SELECT id_source, id_dest
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

        for r in roads:
            src = str(r["id_source"])
            dst = str(r["id_dest"])
            weight = float(r["distance"]) if r["distance"] is not None else 1.0
            g.add_node(src)
            g.add_node(dst)
            g.add_edge(src, dst, weight=weight)

        for b in benziers:
            src = str(b["id_source"])
            dst = str(b["id_dest"])
            g.add_node(src)
            g.add_node(dst)
            g.add_edge(src, dst, weight=1.0)

        # Dữ liệu point cho planner
        point_dict = {
            str(p["name_id"]): (float(p["x"]), float(p["y"]))
            for p in points
        }

        # Dữ liệu point cho UI / debug nếu cần
        robot_points = [
            {
                "name_id": str(row["name_id"]),
                "name": row["name"],
                "x": float(row["x"]),
                "y": float(row["y"]),
                "action": row["action"] if row["action"] is not None else None,
            }
            for row in points
        ]

        self.graph = g
        self.points = point_dict
        self.robot_points = robot_points
        self.current_map_id = map_id

        print(
            f"[MapManager] Loaded graph from DB | map_id={map_id} | "
            f"nodes={g.number_of_nodes()} | edges={g.number_of_edges()}"
        )
        print(f"[MapManager] Points loaded for planner: {len(self.points)}")
        print(f"[MapManager] Points loaded for UI: {len(self.robot_points)}")

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

        except nx.NetworkXNoPath:
            print(f"[MapManager] Không có đường đi từ {start} đến {end}")
            print(f"[MapManager] Edges: {list(self.graph.edges)}")
            return None