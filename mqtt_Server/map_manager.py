import contextlib
import contextvars
import time

import networkx as nx

MAP_RELOAD_MIN_SEC = 3.0   # bản đồ vừa nạp trong khoảng này thì không nạp lại từ DB (xem load_from_db)


class MapManager:
    """
    Xây graph từ DB (bảng agv_map_roads / agv_map_benziers) để tìm đường ngắn nhất theo map đang chọn.
    """

    def __init__(self):
        # ── VÙNG HOẠT ĐỘNG theo loại xe ───────────────────────────────────────
        # `graph` / `line_graph` là PROPERTY: bình thường trả đồ thị gốc; khi code đang
        # chạy trong `with map_manager.agv_scope(agv_id):` thì trả đồ thị ĐÃ LOẠI các
        # node mà loại xe đó KHÔNG được phép vào (node có `allowed_agv_types` không chứa
        # loại xe). Nhờ vậy mọi nơi tìm đường/đường vòng/chỗ đỗ/trạm sạc dùng
        # map_manager.graph|line_graph đều tự tuân thủ vùng cấm mà không phải sửa từng chỗ.
        # ContextVar (không phải thread-local): đúng cho cả code đồng bộ chạy trong thread
        # lẫn coroutine asyncio xen kẽ nhau trên cùng 1 thread (plan_path_async).
        self._forbidden_var = contextvars.ContextVar("mm_forbidden_nodes", default=None)
        self._view_cache: dict = {}
        self._graph_base = nx.Graph()
        self._line_graph_base = nx.DiGraph()
        self.current_map_id = None
        self._loaded_map_id = None
        self._loaded_ts = 0.0
        self._type_dir_cols_ok = False   # đã ALTER TABLE thêm cột type_directions (chỉ cần 1 lần/tiến trình)

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
        self.line_points:  dict = {}   # {name_id: (x, y)}
        self.node_actions: dict = {}   # {name_id: action_dict} chứa fwd_turn/bwd_turn
        self.edge_type_dirs: dict = {}      # (src,dst) -> {loại xe: forward|backward|blocked}
        # Nhiều tầng / thang máy (xem floor_nav.py): mỗi tầng 1 đồ thị con riêng (chưa có cạnh liên tầng)
        self.node_floor: dict = {}          # {name_id: floor_id}  ('' / thiếu = tầng đầu)
        self.floors: list = []              # [{id, name, level}] theo thứ tự tầng trong map
        self.elevators: list = []           # [{id, name, note}]
        self.elev_nodes: dict = {}          # {(elevator_id, floor_id): name_id} — node cabin của thang ở tầng đó
        # Cabin DÙNG CHUNG: 1 thẻ RFID trong cabin, cùng số ở mọi tầng; cạnh nối tới node chờ của từng tầng.
        # elev_nodes khi đó trỏ cùng 1 node cho mọi tầng thang dừng; elev_wait cho biết node chờ theo tầng.
        self.shared_cabins: set = set()     # {name_id} cabin có hàng xóm ở ≥2 tầng
        self.elev_queue: dict = {}          # {(elevator_id, floor_id): [name_id,...]} — điểm xếp hàng khai báo THỦ CÔNG (Map Editor)
        self.elev_exit: dict = {}           # {(elevator_id, floor_id): [name_id,...]} — mốc thoát khu vực thang khai báo thủ công
        self.elev_zone: frozenset = frozenset()   # cabin + điểm chờ/thoát thang: vùng cấm, KHÔNG tính vào giao thông/ngã tư (thang tự khóa vùng)
        self.elev_wait: dict = {}           # {(elevator_id, floor_id): name_id} — node chờ (hàng xóm của cabin) ở tầng đó
        self.cabin_xy: dict = {}            # {cabin: {floor_id: (x, y)}} vị trí mặt cabin theo tầng (toạ độ thế giới)
        self.relax_directions: bool = False   # True khi đang nạp từ DB mô phỏng (xem load_from_db)

    # ── Vùng hoạt động theo loại xe ───────────────────────────────────────────
    @property
    def graph(self):
        return self._scoped_view(self._graph_base)

    @graph.setter
    def graph(self, g):
        self._graph_base = g
        self._view_cache.clear()

    @property
    def line_graph(self):
        return self._scoped_view(self._line_graph_base)

    @line_graph.setter
    def line_graph(self, g):
        self._line_graph_base = g
        self._view_cache.clear()

    def _scoped_view(self, base):
        scope = self._forbidden_var.get()
        if not scope or base is None:
            return base
        forb, terminal, fedges = scope
        key = (id(base), forb, terminal, fedges)
        hit = self._view_cache.get(key)
        if hit is None or hit[0] is not base:
            # Cạnh có hướng bị loại với loại xe này:
            #   - trạm sạc là ĐIỂM CUỐI: không có cạnh đi tiếp ra khỏi trạm (trừ trạm xe đang đứng);
            #   - hướng riêng theo loại xe (vd rơ-moóc chỉ được đi 1 chiều trên đoạn này).
            # Chỉ áp dụng cho đồ thị có hướng.
            if (terminal or fedges) and base.is_directed():
                edge_filter = (lambda u, v, _t=terminal, _f=fedges:
                               str(u) not in _t and (str(u), str(v)) not in _f)
            else:
                edge_filter = nx.filters.no_filter
            hit = (base, nx.subgraph_view(
                base, filter_node=lambda n, _f=forb: str(n) not in _f, filter_edge=edge_filter))
            self._view_cache[key] = hit
        return hit[1]

    @staticmethod
    def _agv_type_of(agv_id: str) -> str:
        try:
            from agv_registry import agv_registry
            return str(agv_registry.get_config(agv_id).get("agv_type") or "").strip().lower()
        except Exception:
            return ""

    def forbidden_nodes_for_type(self, agv_type: str) -> set:
        """Node mà loại xe `agv_type` KHÔNG được vào. Node không khai `allowed_agv_types`
        (hoặc rỗng) = mọi loại xe đều được. Xe không rõ loại -> không giới hạn."""
        agv_type = str(agv_type or "").strip().lower()
        if not agv_type:
            return set()
        out = set()
        for nid, act in (self.node_actions or {}).items():
            allowed = (act or {}).get("allowed_agv_types") if isinstance(act, dict) else None
            if isinstance(allowed, str):
                allowed = [a.strip() for a in allowed.split(",")]
            allowed = [str(a).strip().lower() for a in (allowed or []) if str(a).strip()]
            if allowed and agv_type not in allowed:
                out.add(str(nid))
        return out

    def forbidden_nodes(self, agv_id: str) -> set:
        return self.forbidden_nodes_for_type(self._agv_type_of(agv_id))

    def is_node_allowed(self, agv_id: str, node_id) -> bool:
        return str(node_id) not in self.forbidden_nodes(agv_id)

    def forbidden_edges_for_type(self, agv_type: str) -> frozenset:
        """Các cạnh CÓ HƯỚNG (u, v) mà loại xe `agv_type` KHÔNG được đi, theo cài đặt hướng riêng
        của từng cạnh (edge_type_dirs). Giá trị trên cạnh gốc src→dst:
          forward  → chỉ được src→dst  (cấm dst→src)
          backward → chỉ được dst→src  (cấm src→dst)
          blocked  → cấm cả 2 chiều
        Chỉ HẠN CHẾ thêm so với hướng chung của cạnh, không mở rộng."""
        agv_type = str(agv_type or "").strip().lower()
        out = set()
        if not agv_type:
            return frozenset()
        for (src, dst), dirs in (self.edge_type_dirs or {}).items():
            d = dirs.get(agv_type)
            if d == "forward":
                out.add((dst, src))
            elif d == "backward":
                out.add((src, dst))
            elif d == "blocked":
                out.add((src, dst))
                out.add((dst, src))
        return frozenset(out)

    def forbidden_edges(self, agv_id: str) -> frozenset:
        return self.forbidden_edges_for_type(self._agv_type_of(agv_id))

    def charger_nodes(self) -> set:
        """Mọi node là trạm sạc (locationType=CHARGER hoặc arrival_action=wait_charge)."""
        out = set()
        for nid, act in (self.node_actions or {}).items():
            if not isinstance(act, dict):
                continue
            if (str(act.get("locationType", "")).upper() == "CHARGER"
                    or str(act.get("arrival_action", "")).lower() == "wait_charge"):
                out.add(str(nid))
        return out

    @contextlib.contextmanager
    def agv_scope(self, agv_id: str):
        """Trong khối `with`, graph/line_graph = đồ thị riêng của xe này:
          - đã loại các node loại xe này KHÔNG được vào (vùng cấm, allowed_agv_types);
          - trạm sạc là ĐIỂM CUỐI: không có cạnh đi tiếp ra khỏi trạm (xe không thể "chạy quá"
            trạm sạc ra ngoài bản đồ; đường đi chỉ có thể KẾT THÚC tại trạm sạc).
        Node xe ĐANG ĐỨNG được giữ nguyên (xe vẫn phải rời đi được dù cấu hình đổi sau khi xe đã
        ở đó). Lồng nhau được; an toàn với thread và asyncio (mỗi task một phạm vi)."""
        forb = self.forbidden_nodes(agv_id)
        terminal = self.charger_nodes()
        keep = None
        try:
            from line_agv_handler import line_agv_handler
            st = line_agv_handler.state_store.get(agv_id)
            if st is not None and st.current_tag is not None:
                keep = str(st.current_tag)
        except Exception:
            pass
        if keep:
            forb = forb - {keep}
            terminal = terminal - {keep}
        fedges = self.forbidden_edges(agv_id)
        scope = ((frozenset(forb), frozenset(terminal), fedges)
                 if (forb or terminal or fedges) else None)
        token = self._forbidden_var.set(scope)
        try:
            yield
        finally:
            self._forbidden_var.reset(token)

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

    def invalidate_load_cache(self) -> None:
        """Buộc lần load_from_db kế tiếp đọc lại DB (sau khi người dùng lưu bản đồ)."""
        self.current_map_id = None
        self._loaded_ts = 0.0

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

        # Dispatch đặt current_map_id=None trước MỖI lần lập đường để đọc node_actions mới → 6 xe cùng lập
        # đường = 6 lần nạp lại cả bản đồ + 2 câu ALTER TABLE (khoá bảng) mỗi lần, làm event loop nghẽn và
        # lập đường quá 30s (mô phỏng 2026-11-05: lệnh bị mất, xe đứng 20+ phút). Bản đồ vừa nạp < 3s trước
        # thì dùng lại — vẫn đủ "mới" cho mọi chỉnh sửa của người dùng. Lưu bản đồ gọi invalidate_load_cache().
        if (self._loaded_map_id == map_id and self.graph.number_of_nodes() > 0
                and time.monotonic() - self._loaded_ts < MAP_RELOAD_MIN_SEC):
            self.current_map_id = map_id
            return

        # DiGraph để pathfinding tôn trọng chiều đi (move_direction)
        g = nx.DiGraph()

        async with pool.acquire() as conn:
            # PHÁT HIỆN THỰC TẾ (2026-10-10): bản đồ dùng cho mô phỏng (chạy
            # trên DB riêng TOT_AGV_SIM — xem simulation/setup_sim_db.py
            # SIM_DBNAME) chỉ để stress-test tránh nhau/điều phối ngã tư, KHÔNG
            # cần ai cấu hình tay move_direction/turn_allowed cho từng
            # road/node (mục đích khác hẳn bản đồ sản xuất, nơi hướng đi PHẢI
            # khớp layout thật). Tự động coi MỌI road 2 chiều + MỌI ngã rẽ được
            # phép ở DB này — xe vẫn tiến/lùi/rẽ tuỳ ý (trừ xe có can_reverse=
            # False, đọc riêng ở agv_registry, không liên quan gì tới đây).
            # KHÔNG đụng tới cấu hình CHỨC NĂNG node (block/team/charger/door/
            # zone...) — những cái đó vẫn đọc nguyên từ action như cũ.
            _db_name = await conn.fetchval("SELECT current_database()")
            relax_directions = (_db_name == "TOT_AGV_SIM")

            # Cột hướng riêng theo loại xe: bảo đảm tồn tại trước khi SELECT (DB cũ chưa có).
            if not self._type_dir_cols_ok:
                await conn.execute("ALTER TABLE agv_map_roads ADD COLUMN IF NOT EXISTS type_directions TEXT")
                await conn.execute("ALTER TABLE agv_map_benziers ADD COLUMN IF NOT EXISTS type_directions TEXT")
                self._type_dir_cols_ok = True

            roads = await conn.fetch(
                """
                SELECT id_source, id_dest, distance, speed, speed_bwd, move_direction, width,
                       COALESCE(lidar_off, FALSE) AS lidar_off,
                       COALESCE(lidar_off_dir, 'none') AS lidar_off_dir,
                       type_directions
                FROM agv_map_roads
                WHERE CAST(map_id AS TEXT) = $1
                """,
                map_id,
            )

            benziers = await conn.fetch(
                """
                SELECT id_source, id_dest, speed, speed_bwd, move_direction, distance,
                       point_start_x, point_start_y, point_end_x, point_end_y,
                       COALESCE(lidar_off, FALSE) AS lidar_off,
                       COALESCE(lidar_off_dir, 'none') AS lidar_off_dir,
                       type_directions
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

        # Thông tin tầng + thang máy — truy vấn RIÊNG và bọc try: cột floor_id/floors/elevators có thể chưa
        # tồn tại (DB cũ chưa nâng cấp) → map 1 tầng vẫn nạp bình thường, không bao giờ hỏng vì phần này.
        _node_floor: dict = {}
        _floors_meta: list = []
        _elev_meta: list = []
        try:
            async with pool.acquire() as _conn_fl:
                for _r_fl in await _conn_fl.fetch(
                        "SELECT name_id, COALESCE(floor_id, '') AS floor_id FROM agv_map_points "
                        "WHERE CAST(map_id AS TEXT) = $1", map_id):
                    _node_floor[str(_r_fl["name_id"])] = str(_r_fl["floor_id"] or "")
                _mrow = await _conn_fl.fetchrow(
                    "SELECT floors, elevators FROM agv_maps WHERE CAST(id AS TEXT) = $1", map_id)
                if _mrow:
                    import json as _json_fl
                    def _as_list(v):
                        if isinstance(v, str):
                            try:
                                v = _json_fl.loads(v)
                            except Exception:
                                v = None
                        return v if isinstance(v, list) else []
                    _floors_meta = _as_list(_mrow["floors"])
                    _elev_meta = _as_list(_mrow["elevators"])
        except Exception as _e_fl:
            print(f"[MapManager] bỏ qua thông tin tầng/thang (non-fatal): {_e_fl}")

        roads_data = []
        edge_type_dirs: dict = {}

        def _collect_td(src_, dst_, raw_):
            import json as _json_td
            try:
                d = _json_td.loads(raw_) if isinstance(raw_, str) and raw_ else (raw_ or {})
            except Exception:
                d = {}
            if isinstance(d, dict):
                clean = {str(k).lower(): str(v).lower() for k, v in d.items()
                         if str(v).lower() in ("forward", "backward", "blocked")}
                if clean:
                    edge_type_dirs[(src_, dst_)] = clean

        for r in roads:
            src = str(r["id_source"])
            dst = str(r["id_dest"])
            _collect_td(src, dst, r["type_directions"])
            weight = float(r["distance"]) if r["distance"] is not None else 1.0
            speed  = float(r["speed"])  if r["speed"]    is not None else 0.5
            mdir   = int(r["move_direction"]) if r["move_direction"] is not None else 0
            if relax_directions:
                mdir = 0
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
            _collect_td(src, dst, b["type_directions"])
            b_speed = float(b["speed"]) if b["speed"] is not None else 0.5
            b_mdir  = int(b["move_direction"]) if b["move_direction"] is not None else 0
            if relax_directions:
                b_mdir = 0
            # Khoảng cách thật (nhập tay ở Map Editor) được ưu tiên; chỉ tự tính
            # từ tọa độ đầu-cuối khi chưa có giá trị nhập tay (distance NULL).
            if b["distance"] is not None:
                b_weight = float(b["distance"])
            else:
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
            if relax_directions and isinstance(act, dict) and str(act.get("turn_allowed", "")).lower() == "no":
                act = {**act, "turn_allowed": "yes"}
            node_actions[nid] = act

        self.graph = g
        self.points = point_dict
        self.robot_points = robot_points
        self.all_points = all_points
        self.roads = roads_data
        self.current_map_id = map_id
        self._loaded_map_id = map_id
        self._loaded_ts = time.monotonic()
        self.line_graph   = line_g
        self.line_points  = line_points
        self.node_actions = node_actions  # {nid: {agvCompat, fwd_turn, bwd_turn, ...}}
        self.edge_type_dirs = edge_type_dirs
        self.relax_directions = relax_directions

        # Tầng + thang máy: chuẩn hoá. Map 1 tầng (hoặc chưa khai báo) → floors rỗng/1 phần tử, elev_nodes rỗng.
        _floors_norm = []
        for _i_f, _f in enumerate(_floors_meta):
            if not isinstance(_f, dict) or not _f.get("id"):
                continue
            try:
                _lvl = int(_f.get("level")) if _f.get("level") is not None else _i_f + 1
            except (TypeError, ValueError):
                _lvl = _i_f + 1
            _floors_norm.append({"id": str(_f["id"]), "name": str(_f.get("name") or _f["id"]), "level": _lvl})
        _first_fl = _floors_norm[0]["id"] if _floors_norm else ""
        _valid_fl = {f["id"] for f in _floors_norm}
        # Tầng hiện tại của cabin dùng chung (floor_nav.set_cabin_floor) là TRẠNG THÁI chạy, không có trong DB: nạp lại
        # bản đồ (xảy ra sau mỗi vài giây khi có lệnh) mà dựng node_floor từ DB sẽ đưa cabin về tầng lưu → xe trong thang
        # hiện sai tầng + lập đường sai. Cùng bản đồ thì giữ lại tầng cabin đang đứng.
        _prev_cabin_fl = ({c: self.node_floor.get(c) for c in self.shared_cabins}
                          if getattr(self, "_cabin_floor_map", None) == map_id else {})
        self.floors = _floors_norm
        self.node_floor = {n: (f if f in _valid_fl else _first_fl) for n, f in _node_floor.items()} \
            if len(_floors_norm) > 1 else {}
        self.elevators = [e for e in _elev_meta if isinstance(e, dict) and e.get("id")]
        _elev_nodes, _elev_wait, _shared = {}, {}, set()
        if len(_floors_norm) > 1:
            _elev_nodes, _elev_wait, _shared = self.derive_elevator_nodes(g, node_actions, self.node_floor, _first_fl)
        self.elev_nodes = _elev_nodes
        self.elev_wait = _elev_wait
        self.elev_queue, self.elev_exit = {}, {}
        self.elev_zone = frozenset()
        for _nid, _act in node_actions.items():
            _role = str((_act or {}).get("elev_role") or "").lower() if isinstance(_act, dict) else ""
            _ref = str((_act or {}).get("elev_ref") or "").strip() if isinstance(_act, dict) else ""
            if _role in ("zone", "queue", "exit") and _ref:
                # "zone" = 1 node vừa là điểm chờ (xe đi VÀO thang) vừa là mốc thoát (xe đi RA); queue/exit là kiểu cũ
                _k = (_ref, self.node_floor.get(str(_nid), _first_fl))
                if _role in ("zone", "queue"):
                    self.elev_queue.setdefault(_k, []).append(str(_nid))
                if _role in ("zone", "exit"):
                    self.elev_exit.setdefault(_k, []).append(str(_nid))
        self.elev_zone = frozenset({str(v) for v in _elev_nodes.values()}
                                   | {n for L in self.elev_queue.values() for n in L}
                                   | {n for L in self.elev_exit.values() for n in L})
        self.shared_cabins = _shared
        self.cabin_xy = self.derive_cabin_xy(_shared, node_actions, self.node_floor, point_dict)
        if _shared:
            from floor_nav import set_cabin_floor as _set_cab_fl
            for _c, _fid in _prev_cabin_fl.items():
                if _c in _shared and _fid in _valid_fl and self.node_floor.get(_c) != _fid:
                    _set_cab_fl(_c, _fid, self)
        self._cabin_floor_map = map_id
        if len(_floors_norm) > 1:
            print(f"[MapManager] Nhiều tầng: {[(f['id'], f['level']) for f in _floors_norm]} | "
                  f"thang={[e['id'] for e in self.elevators]} | node thang={dict(_elev_nodes)}"
                  + (f" | cabin dùng chung={sorted(_shared)}" if _shared else ""))

        print(
            f"[MapManager] Loaded graph from DB | map_id={map_id} | "
            f"nodes={g.number_of_nodes()} | edges={g.number_of_edges()}"
            + (" | MÔ PHỎNG: đã bỏ qua move_direction/turn_allowed (mọi road "
               "2 chiều, mọi ngã rẽ được phép)" if relax_directions else "")
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

    @staticmethod
    def derive_elevator_nodes(g, node_actions: dict, node_floor: dict, first_floor: str):
        """(elev_nodes, elev_wait, shared_cabins) từ đồ thị + node loại thang (action.elevator_id).
        Cabin có hàng xóm ở ≥2 tầng = cabin DÙNG CHUNG: 1 node cho mọi tầng thang dừng, node chờ là hàng xóm của
        cabin trên tầng đó. Ngược lại (mỗi tầng 1 node cabin riêng) giữ cách cũ: cabin = node ở tầng của nó."""
        elev_nodes: dict = {}
        elev_wait: dict = {}
        shared: set = set()
        for nid, act in node_actions.items():
            eid = str((act or {}).get("elevator_id") or "").strip() if isinstance(act, dict) else ""
            if not eid:
                continue
            nb_by_floor: dict = {}
            if g.has_node(nid):
                for nb in sorted(set(g.successors(nid)) | set(g.predecessors(nid))):
                    nb_by_floor.setdefault(node_floor.get(str(nb), first_floor), str(nb))
            if len(nb_by_floor) >= 2:
                shared.add(nid)
                for fid, wn in nb_by_floor.items():
                    elev_nodes.setdefault((eid, fid), nid)
                    elev_wait.setdefault((eid, fid), wn)
            else:
                elev_nodes.setdefault((eid, node_floor.get(nid, first_floor)), nid)
        return elev_nodes, elev_wait, shared

    @staticmethod
    def derive_cabin_xy(shared: set, node_actions: dict, node_floor: dict, points: dict) -> dict:
        """Vị trí của cabin dùng chung theo từng tầng: tầng lưu trong DB = toạ độ node; các tầng khác lấy từ
        action.cabin_facets (Map Editor ghi). Thiếu thì tầng đó dùng toạ độ node. set_cabin_floor() đặt points[cabin]
        theo bảng này để hướng rẽ tại node chờ (tính theo toạ độ node trước nó) đúng với tầng thang đang đứng."""
        out: dict = {}
        for cab in shared:
            base = points.get(cab)
            if base is None:
                continue
            m = {str(node_floor.get(cab, "")): (float(base[0]), float(base[1]))}
            cf = (node_actions.get(cab) or {}).get("cabin_facets")
            if isinstance(cf, dict):
                for fid, xy in cf.items():
                    try:
                        m[str(fid)] = (float(xy["x"]), float(xy["y"]))
                    except (KeyError, TypeError, ValueError):
                        pass
            out[cab] = m
        return out

    def line_floor_view(self, start: str, end: str, floor: str | None = None):
        """line_graph giới hạn trong MỘT tầng khi map có cabin thang dùng chung: cabin nối node chờ của nhiều tầng
        nên không giới hạn thì đường ngắn nhất có thể đi xuyên tầng qua cabin (không có thang thật chạy). Trong
        view, cabin chỉ còn hàng xóm cùng tầng = node cụt đúng như floor_nav yêu cầu. Tầng lấy theo `floor`, hoặc
        theo start/end (node không phải cabin). Không có cabin dùng chung / không xác định được tầng → line_graph."""
        g = self.line_graph
        shared = self.shared_cabins
        if not shared or g is None:
            return g
        fl = floor
        if fl is None:
            for n in (str(start), str(end)):
                if n not in shared and n in self.node_floor:
                    fl = self.node_floor[n]
                    break
        if fl is None:
            return g
        keep = [n for n in g.nodes if n in shared or self.node_floor.get(n) == fl]
        return g.subgraph(keep)

    def line_shortest_path(self, start: str, end: str, floor: str | None = None):
        """Tìm đường đi cho Line AGV — chỉ qua node RFID/both.
        Fallback về full graph nếu line_graph chưa có node (map chưa set agvCompat).
        `floor`: ép tìm trong 1 tầng (cần khi start và end đều là cabin dùng chung).
        """
        g = self.line_graph
        if self.shared_cabins and g is not None and g.number_of_nodes() > 0:
            v = self.line_floor_view(start, end, floor)
            if v is not g and g.has_node(str(start)) and g.has_node(str(end)):
                if not (v.has_node(str(start)) and v.has_node(str(end))):
                    print(f"[MapManager] {start}→{end} khác tầng — cần đi thang, không có đường trong 1 tầng")
                    return None
                try:
                    path = nx.shortest_path(v, source=str(start), target=str(end), weight="weight")
                    print(f"[MapManager] Line AGV path: {' → '.join(path)}")
                    return path
                except nx.NetworkXNoPath:
                    print(f"[MapManager] line_graph (1 tầng): không có đường {start}→{end}")
                    return None
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

    def line_directional_path(self, start: str, end: str, came_from: str | None,
                               can_reverse: bool = True) -> list | None:
        """
        Tìm đường cho Line AGV có xét đến hướng hiện tại và quyền quay tại node.

        came_from: node AGV vừa đến start từ đó (prev_tag).
        can_reverse: xe có lùi được không (False cho trailer/tow không lùi được)
            — khi False, bước lùi bị phạt RẤT NẶNG (gần như loại bỏ) thay vì chỉ
            BWD_PENALTY nhẹ như xe lùi được, để pathfinder không bao giờ đề xuất
            1 đường cần lùi cho xe vật lý không lùi được. Việc veto sau khi tính
            đường ở dispatch (main.py) vẫn giữ nguyên làm lớp bảo hiểm dự phòng.
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
        if self.shared_cabins:
            g = self.line_floor_view(start, end)    # không đi xuyên tầng qua cabin dùng chung

        start, end, came_from = str(start), str(end), str(came_from)
        if not g.has_node(start) or not g.has_node(end):
            return self.line_shortest_path(start, end)

        points       = self.line_points or self.points
        node_actions = self.node_actions

        def h(nid: str) -> float:
            # Chi phí cạnh (weight) tính bằng MÉT còn toạ độ vẽ tính bằng pixel → khoảng cách Euclid KHÔNG cùng đơn vị,
            # dùng làm heuristic sẽ lớn hơn chi phí thật hàng chục lần (không admissible) khiến A* chạy tham lam, bỏ qua
            # đường vòng/ngã rẽ rẻ hơn mà chọn đường lùi. Đồ thị nhỏ → dùng Dijkstra (h=0) để luôn ra đường tối ưu.
            return 0.0

        # Xe không lùi được: phạt gần như vô hạn để loại bỏ mọi bước lùi khỏi
        # lựa chọn (thay vì chỉ ưu tiên tiến nhẹ như xe lùi được).
        BWD_PENALTY  = 2.0 if can_reverse else 1_000_000.0
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
