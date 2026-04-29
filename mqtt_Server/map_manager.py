# map_manager.py
import networkx as nx


def _is_int_like(value: str) -> bool:
    try:
        int(str(value).strip())
        return True
    except Exception:
        return False

class MapManager:
    """
    Xây graph từ DB (bảng agv_map_roads) để tìm đường ngắn nhất theo map đang chọn.
    """

    def __init__(self):
        self.graph = nx.Graph()
        self.current_map_id = None
        self.points = {}

    async def resolve_map_id(self, pool, value: str):
        """
        Cho phép truyền vào map_id hoặc map name. Trả về map_id (id trong bảng agv_maps) nếu tìm thấy.
        """
        if not value:
            return None
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id FROM agv_maps
                WHERE id = $1 OR name = $1
                LIMIT 1
                """,
                value,
            )
        return str(row["id"]) if row else None

    async def load_from_db(self, pool, map_id: str):
        """
        Đọc roads từ DB và build graph. Cache theo map_id.
        """
        if not map_id:
            raise ValueError("map_id is required to load graph")

        if self.current_map_id == map_id and self.graph.number_of_nodes() > 0:
            return

        g = nx.Graph()
        async with pool.acquire() as conn:
            map_name = None
            if not _is_int_like(map_id):
                row = await conn.fetchrow(
                    """
                    SELECT name
                    FROM agv_maps
                    WHERE id = $1 OR name = $1
                    LIMIT 1
                    """,
                    map_id,
                )
                if row:
                    map_name = str(row["name"] or "").strip() or None

            if map_name and not _is_int_like(map_id):
                roads = await conn.fetch(
                    """
                    SELECT id_source, id_dest, distance
                    FROM agv_map_roads
                    WHERE name = $1
                    """,
                    map_name,
                )
                benziers = await conn.fetch(
                    """
                    SELECT id_source, id_dest
                    FROM agv_map_benziers
                    WHERE name = $1
                    """,
                    map_name,
                )
                points = await conn.fetch(
                    """
                    SELECT name_id, x, y
                    FROM agv_map_points
                    WHERE name = $1
                    """,
                    map_name,
                )
            else:
                roads = await conn.fetch(
                    """
                    SELECT id_source, id_dest, distance
                    FROM agv_map_roads
                    WHERE map_id = $1
                    """,
                    map_id,
                )
                benziers = await conn.fetch(
                    """
                    SELECT id_source, id_dest
                    FROM agv_map_benziers
                    WHERE map_id = $1
                    """,
                    map_id,
                )
                points = await conn.fetch(
                    """
                    SELECT name_id, x, y
                    FROM agv_map_points
                    WHERE map_id = $1
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

        self.graph = g
        self.points = {str(p["name_id"]): (float(p["x"]), float(p["y"])) for p in points}
        self.current_map_id = map_id
        print(
            f"[MapManager] Loaded graph from DB | map_id={map_id} | nodes={g.number_of_nodes()} | edges={g.number_of_edges()}"
        )
        print(f"[MapManager] Points loaded: {len(self.points)}")

    def nearest_node(self, x: float, y: float):
        """Tìm node gần nhất theo tọa độ (x,y) từ agv_map_points đã load."""
        if not getattr(self, "points", None):
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
            path = nx.shortest_path(self.graph, source=str(start), target=str(end), weight="weight")
            print(f"[MapManager] Đường đi ngắn nhất: {' → '.join(path)}")
            return path
        except nx.NodeNotFound as e:
            print(f"[MapManager] Lỗi: {e}")
            print(f"[MapManager] Nodes hiện có: {list(self.graph.nodes)}")
            return None
        except nx.NetworkXNoPath:
            print(f"[MapManager] Không có đường đi từ {start} đến {end}")
            print(f"[MapManager] Edges: {list(self.graph.edges)}")
            return None
