import tkinter as tk
from tkinter import simpledialog, ttk
import math
import time
import copy

class MapWidget(tk.Canvas):
    def __init__(self, parent, traffic_manager, agv_list):
        super().__init__(parent, bg="white", highlightthickness=0)
        
        self.tm = traffic_manager
        self.agv_list = agv_list
        self.action_map = {} # Sẽ được Main update
        self.lang_data = {}
        self.current_lang = "en"
        
        # Editor State
        self.selected_node = None       # Primary (last) selected node
        self.selected_nodes = set()     # Multi-select set (always contains selected_node)
        self.selected_edge = None       # Tuple (u, v) của cạnh đang được chọn
        self.dragging_node = None
        self._drag_history_pushed = False  # Chỉ push history 1 lần khi bắt đầu kéo
        self.tool = "monitor" # monitor, select, node, edge
        self.next_node_id = 1000
        self.temp_edge_start = None
        self.temp_mouse_pos = None
        self.get_id_callback = None # Hàm lấy ID từ Main GUI

        # Undo / Redo History
        self._history = []      # Danh sách snapshot trước đó
        self._redo_stack = []   # Danh sách snapshot đã undo (để redo lại)
        self._MAX_HISTORY = 50  # Giới hạn số bước lưu
        
        # Zoom & Pan
        self.scale = 1.0
        self.offset_x = 0
        self.offset_y = 0
        self.is_panning = False
        self.last_pan_x = 0
        self.last_pan_y = 0
        
        self.tooltip_window = None # Popup hiển thị thông tin
        self._agv_anim = {}  # {agv_id: (phase, last_tick)} — animation state per AGV
        self.zone_mgr = None  # Inject từ main.py sau khi khởi tạo

        # ── AGV Position Input mode ──────────────────────────────────────────────
        # {agv_id: {'wx':float,'wy':float,'angle':float,'node':int|None,'prev_node':int|None}}
        self._pos_input_agvs     = {}   # Manual positions set by user
        self._pos_input_active   = False
        self._dragging_agv_pos   = None  # agv_id đang kéo
        self._drag_agv_last      = (0, 0)
        self.on_apply_positions  = None  # Callback: {agv_id:(node,prev_node)} → main.py xử lý

        # ── Manual Control Animation ─────────────────────────────────────────────
        # Độc lập với auto-mode animation — dùng khi điều khiển thủ công
        # 'move': {'dx': float, 'dy': float, 'sx': float, 'sy': float,
        #          'start_t': float, 'duration': float, 'angle_rad': float}
        # 'turn': {'from_angle': float, 'to_angle': float,
        #          'start_t': float, 'duration': float, 'sx': float, 'sy': float}
        self._manual_anim   = {}   # {agv_id: {'type': 'move'|'turn', ...}}
        self._manual_angles = {}   # {agv_id: float(rad)} — hướng lưu sau khi quay xong

        # Zone label drag
        self._zone_label_offsets    = {}   # {zone_id: (world_dx, world_dy)}
        self._zone_label_screen_pos = {}   # {zone_id: (sx, sy)} — cập nhật mỗi draw_map
        self._dragging_zone_label   = None # zone_id đang kéo
        self._drag_label_last       = (0, 0)

        # ── Rubber-band multi-select ─────────────────────────────────────────
        self._rubber_start  = None   # (sx, sy) điểm bắt đầu kéo chọn
        self._rubber_rect   = None   # canvas item id của hình chữ nhật chọn
        self._rubber_active = False  # đang vẽ rubber-band?

        # ── Tỉ lệ thực tế ────────────────────────────────────────────────────
        self.meters_per_unit = 0.01  # 1 world-unit = 0.01 m (bản đồ lớn hơn thực tế 100 lần; cấu hình trong Settings)

        # ── Hiển thị chiều dài cạnh trên bản đồ ─────────────────────────────
        self.show_real_length    = True   # Hiển thị chiều dài thực (weight * meters_per_unit)
        self.show_display_length = False  # Hiển thị chiều dài hiển thị (khoảng cách hình học trên canvas)

        # Callback gọi mỗi khi scale thay đổi: on_zoom_changed(new_scale)
        self.on_zoom_changed = None

        # Bind Events
        self.bind("<Button-1>", self.on_click)
        self.bind("<B1-Motion>", self.on_drag)
        self.bind("<ButtonRelease-1>", self.on_release)
        self.bind("<Button-3>", self.on_right_click) # Right click
        self.bind("<Double-Button-1>", self.on_double_click) # Edit Node
        self.bind("<MouseWheel>", self.on_zoom) # Zoom Windows
        self.bind("<Button-4>", self.on_zoom)   # Zoom Linux Scroll Up
        self.bind("<Button-5>", self.on_zoom)   # Zoom Linux Scroll Down
        self.bind("<Motion>", self.on_mouse_move) # Hover event
        # Keyboard shortcuts (canvas phải có focus - gọi focus_set() khi click)
        self.bind("<Control-z>", lambda e: self.undo())
        self.bind("<Control-Z>", lambda e: self.undo())
        self.bind("<Control-y>", lambda e: self.redo())
        self.bind("<Control-Y>", lambda e: self.redo())
        self.bind("<Delete>", lambda e: self.delete_selected())
        self.bind("<BackSpace>", lambda e: self.delete_selected())
        # ── Arrow keys: di chuyển node đang chọn ────────────────────────────
        self.bind("<Left>",  lambda _: self._move_selected(-1,  0))
        self.bind("<Right>", lambda _: self._move_selected(+1,  0))
        self.bind("<Up>",    lambda _: self._move_selected( 0, -1))
        self.bind("<Down>",  lambda _: self._move_selected( 0, +1))
        # ── Right-button drag: pan (khi không có context menu) ───────────────
        self.bind("<B3-Motion>", self._on_right_drag)
        self.bind("<ButtonRelease-3>", self._on_right_release)
        self._rpan_last  = (0, 0)
        self._rpan_moved = False   # True nếu đã kéo, không show context menu

        # Start Animation Loop
        self.animate()

    def set_zone_manager(self, zone_mgr):
        """Inject ZoneManager để vẽ overlay và mở Zone Editor."""
        self.zone_mgr = zone_mgr

    def set_action_map(self, action_map):
        self.action_map = action_map

    def set_lang_data(self, lang_data, current_lang):
        self.lang_data = lang_data
        self.current_lang = current_lang

    def t(self, key):
        """Dịch ngôn ngữ"""
        return self.lang_data.get(self.current_lang, {}).get(key, key)

    # ── Schematic Layout helpers ──────────────────────────────────────────────
    def _disp_xy(self, nid):
        """Tọa độ HIỂN THỊ của node.
        Nếu node có disp_x/disp_y (đã kéo trong chế độ Schematic) → dùng đó.
        Nếu không → fallback về x/y (tọa độ thực vật lý).
        Tọa độ x/y luôn giữ nguyên để tính trọng số cạnh / pathfinding."""
        n = self.tm.graph.nodes[nid]
        return n.get('disp_x', n.get('x', 0)), n.get('disp_y', n.get('y', 0))

    def reset_display_positions(self):
        """Xóa disp_x/disp_y của các node đã chọn (hoặc tất cả nếu không chọn gì)
        để chúng quay về vị trí thực x/y."""
        nodes = list(self.selected_nodes) if self.selected_nodes else list(self.tm.graph.nodes)
        if not nodes:
            return
        self._push_history()
        for nid in nodes:
            if nid in self.tm.graph.nodes:
                self.tm.graph.nodes[nid].pop('disp_x', None)
                self.tm.graph.nodes[nid].pop('disp_y', None)
        self.draw_map()

    def to_screen(self, wx, wy):
        """Chuyển tọa độ thực (World) sang tọa độ màn hình (Screen)"""
        sx = (wx * self.scale) + self.offset_x
        sy = (wy * self.scale) + self.offset_y
        return sx, sy

    def to_world(self, sx, sy):
        """Chuyển tọa độ màn hình sang tọa độ thực"""
        wx = (sx - self.offset_x) / self.scale
        wy = (sy - self.offset_y) / self.scale
        return wx, wy

    def get_node_at_pos(self, pos):
        # pos là tọa độ màn hình; dùng disp_xy để so sánh với vị trí HIỂN THỊ
        wx, wy = self.to_world(pos[0], pos[1])
        for node_id in self.tm.graph.nodes:
            nx, ny = self._disp_xy(node_id)
            dist = math.hypot(wx - nx, wy - ny)
            if dist < 15 / self.scale:
                return node_id
        return None

    def get_edge_at_pos(self, pos):
        """Tìm cạnh (Edge) gần vị trí chuột nhất — dùng vị trí hiển thị (disp_xy)"""
        wx, wy = self.to_world(pos[0], pos[1])
        threshold = 10 / self.scale
        for u, v, _attrs in self.tm.graph.edges(data=True):
            if u in self.tm.graph.nodes and v in self.tm.graph.nodes:
                dx1, dy1 = self._disp_xy(u)
                dx2, dy2 = self._disp_xy(v)
                dist = self.point_to_line_dist(wx, wy, dx1, dy1, dx2, dy2)
                if dist < threshold:
                    return (u, v)
        return None

    def point_to_line_dist(self, px, py, x1, y1, x2, y2):
        # Tính độ dài đoạn thẳng bình phương
        l2 = (x1-x2)**2 + (y1-y2)**2
        if l2 == 0: return math.hypot(px-x1, py-y1)
        # Tính hình chiếu t
        t = ((px-x1)*(x2-x1) + (py-y1)*(y2-y1)) / l2
        t = max(0, min(1, t))
        # Điểm chiếu
        proj_x = x1 + t * (x2-x1)
        proj_y = y1 + t * (y2-y1)
        return math.hypot(px-proj_x, py-proj_y)

    def _get_zone_label_at(self, sx, sy):
        """Trả về zone_id nếu click trong vùng nhãn, ngược lại None."""
        for zone_id, (lx, ly) in self._zone_label_screen_pos.items():
            if abs(sx - lx) < 72 and abs(sy - ly) < 14:
                return zone_id
        return None

    def on_click(self, event):
        self.focus_set()  # Canvas nhận focus bàn phím để Ctrl+Z, Del hoạt động

        # ── AGV Position Input: click để kéo AGV ────────────────────────────
        if self._pos_input_active:
            agv_id = self._get_agv_pos_at_screen(event.x, event.y)
            if agv_id:
                self._dragging_agv_pos = agv_id
                self._drag_agv_last    = (event.x, event.y)
                return

        # ── Zone label drag: kiểm tra trước mọi tool khác ──────────────────
        z_id = self._get_zone_label_at(event.x, event.y)
        if z_id:
            self._dragging_zone_label = z_id
            self._drag_label_last     = (event.x, event.y)
            return

        wx, wy = self.to_world(event.x, event.y)
        if self.tool == "node":
            # Lấy ID từ GUI bên ngoài nếu có
            new_id = self.next_node_id
            if self.get_id_callback:
                try:
                    new_id = int(self.get_id_callback())
                except:
                    pass

            self._push_history()  # Lưu trạng thái trước khi thêm node
            self.tm.add_node(new_id, wx, wy)
            self.draw_map()

        elif self.tool == "edge":
            node_id = self.get_node_at_pos((event.x, event.y))
            if node_id:
                self.temp_edge_start = node_id
                self.temp_mouse_pos = (event.x, event.y)

        elif self.tool == "select" or self.tool == "monitor":
            node_id = self.get_node_at_pos((event.x, event.y))
            ctrl_held = bool(event.state & 0x4)
            if node_id:
                self.dragging_node = node_id
                self._drag_history_pushed = False
                if ctrl_held:
                    # Toggle in multi-select
                    if node_id in self.selected_nodes:
                        self.selected_nodes.discard(node_id)
                        self.selected_node = next(iter(self.selected_nodes), None)
                    else:
                        self.selected_nodes.add(node_id)
                        self.selected_node = node_id
                else:
                    self.selected_nodes = {node_id}
                    self.selected_node = node_id
                self.selected_edge = None
                self.draw_map()
            else:
                edge = self.get_edge_at_pos((event.x, event.y))
                if edge:
                    self.selected_edge = edge
                    if not ctrl_held:
                        self.selected_node = None
                        self.selected_nodes.clear()
                    self.draw_map()
                else:
                    # Kéo chuột trái trên vùng trống → bắt đầu rubber-band chọn nhóm
                    # (Pan bằng chuột PHẢI hoặc chuột giữa)
                    if not ctrl_held:
                        self.selected_edge = None
                        self.selected_nodes.clear()
                        self.selected_node = None
                    self._rubber_start  = (event.x, event.y)
                    self._rubber_active = True
                    self.hide_tooltip()

    def on_drag(self, event):
        # ── AGV Position drag ────────────────────────────────────────────────
        if self._dragging_agv_pos:
            wx, wy = self.to_world(event.x, event.y)
            pos = self._pos_input_agvs[self._dragging_agv_pos]
            pos['wx'], pos['wy'] = wx, wy
            pos['node'] = None  # Clear snap khi đang kéo
            self.draw_map()
            return

        # ── Zone label drag ──────────────────────────────────────────────────
        if self._dragging_zone_label:
            lx, ly = self._drag_label_last
            dx_screen = event.x - lx
            dy_screen = event.y - ly
            self._drag_label_last = (event.x, event.y)
            old = self._zone_label_offsets.get(self._dragging_zone_label, (0.0, 0.0))
            self._zone_label_offsets[self._dragging_zone_label] = (
                old[0] + dx_screen / self.scale,
                old[1] + dy_screen / self.scale,
            )
            self.draw_map()
            return

        # ── Rubber-band selection drag ────────────────────────────────────────
        if self._rubber_active and self._rubber_start:
            if self._rubber_rect:
                self.delete(self._rubber_rect)
            x0, y0 = self._rubber_start
            self._rubber_rect = self.create_rectangle(
                x0, y0, event.x, event.y,
                outline="#2980b9", fill="#aed6f1",
                stipple="gray25", dash=(4, 2), width=1,
                tags="rubber_band"
            )
            return

        wx, wy = self.to_world(event.x, event.y)

        if self.is_panning:
            self.hide_tooltip()
            dx = event.x - self.last_pan_x
            dy = event.y - self.last_pan_y
            self.offset_x += dx
            self.offset_y += dy
            self.last_pan_x = event.x
            self.last_pan_y = event.y
            self.draw_map()
        elif self.tool == "select" and self.dragging_node:
            if not self._drag_history_pushed:
                self._push_history()
                self._drag_history_pushed = True
            if len(self.selected_nodes) > 1 and self.dragging_node in self.tm.graph.nodes:
                # Multi-drag: move all selected nodes by same delta (Schematic: chỉ đổi disp_x/y)
                old_dx, old_dy = self._disp_xy(self.dragging_node)
                ddx, ddy = wx - old_dx, wy - old_dy
                for n in self.selected_nodes:
                    if n in self.tm.graph.nodes:
                        cdx, cdy = self._disp_xy(n)
                        self.tm.graph.nodes[n]['disp_x'] = cdx + ddx
                        self.tm.graph.nodes[n]['disp_y'] = cdy + ddy
            else:
                # Single drag: chỉ đổi vị trí hiển thị, giữ nguyên x/y vật lý
                self.tm.graph.nodes[self.dragging_node]['disp_x'] = wx
                self.tm.graph.nodes[self.dragging_node]['disp_y'] = wy
            self.draw_map()
        elif self.tool == "edge" and self.temp_edge_start:
            self.temp_mouse_pos = (event.x, event.y)
            self.draw_map()

    def on_release(self, event):
        if self.tool == "edge" and self.temp_edge_start:
            end_node = self.get_node_at_pos((event.x, event.y))
            if end_node and end_node != self.temp_edge_start:
                self._push_history()  # Lưu trạng thái trước khi thêm cạnh
                self.tm.add_edge(self.temp_edge_start, end_node)
                print(f"Connected {self.temp_edge_start} -> {end_node}")
            self.temp_edge_start = None
            self.temp_mouse_pos = None
            self.draw_map()

        # ── Stop AGV position drag → snap to nearest node ────────────────────
        if self._dragging_agv_pos:
            wx, wy = self.to_world(event.x, event.y)
            self._snap_agv_to_nearest(self._dragging_agv_pos, wx, wy)
            self._dragging_agv_pos = None
            self.draw_map()
            return

        # ── Stop zone label drag ─────────────────────────────────────────────
        if self._dragging_zone_label:
            self._dragging_zone_label = None
            self.draw_map()
            return

        # ── Kết thúc rubber-band: chọn objects trong hình chữ nhật ─────────────
        if self._rubber_active:
            self._rubber_active = False
            if self._rubber_rect:
                self.delete(self._rubber_rect)
                self._rubber_rect = None
            if self._rubber_start:
                x0, y0 = self._rubber_start
                x1, y1 = event.x, event.y
                self._rubber_start = None
                # Chuẩn hoá bounding box (kéo bất kỳ hướng nào)
                lx, rx = min(x0, x1), max(x0, x1)
                ty, by = min(y0, y1), max(y0, y1)
                if rx - lx > 4 and by - ty > 4:   # chỉ xét nếu rect đủ lớn
                    ctrl_held = bool(event.state & 0x4)
                    if not ctrl_held:
                        self.selected_nodes.clear()
                        self.selected_edge = None
                    # Chọn tất cả node nằm trong rect
                    for nid in self.tm.graph.nodes:
                        sx, sy = self.to_screen(*self._disp_xy(nid))
                        if lx <= sx <= rx and ty <= sy <= by:
                            self.selected_nodes.add(nid)
                    self.selected_node = next(iter(self.selected_nodes), None)
                    self.draw_map()
            return

        self.is_panning = False
        self.dragging_node = None
        self._drag_history_pushed = False  # Reset cờ sau khi thả chuột

    # ── Right-button pan ─────────────────────────────────────────────────────
    def _on_right_drag(self, event):
        if not self._rpan_moved:
            self._rpan_last  = (event.x, event.y)
            self._rpan_moved = True
            return
        lx, ly = self._rpan_last
        dx, dy = event.x - lx, event.y - ly
        if abs(dx) > 1 or abs(dy) > 1:
            self.offset_x += dx
            self.offset_y += dy
            self._rpan_last = (event.x, event.y)
            self.draw_map()

    def _on_right_release(self, *_):
        self._rpan_moved = False
        # Thông báo zoom_changed (giữ nguyên scale, nhưng offset thay đổi)
        if self.on_zoom_changed:
            self.on_zoom_changed(self.scale)

    # ── Arrow key: di chuyển node chọn theo bước nhỏ ────────────────────────
    def _move_selected(self, dx_sign: int, dy_sign: int):
        """Di chuyển các node đã chọn theo hướng mũi tên.
        Mỗi lần nhấn = 0.5m (nếu meters_per_unit=1 thì step=0.5 world-unit).
        Giữ Shift → bước lớn hơn 5×.
        """
        if not self.selected_nodes:
            return
        step = 0.5 / max(self.meters_per_unit, 1e-6)   # 0.5 m theo world-unit
        self._push_history()
        for nid in self.selected_nodes:
            if nid in self.tm.graph.nodes:
                cdx, cdy = self._disp_xy(nid)
                self.tm.graph.nodes[nid]['disp_x'] = cdx + dx_sign * step
                self.tm.graph.nodes[nid]['disp_y'] = cdy + dy_sign * step
        self.draw_map()

    def on_right_click(self, event):
        # ── AGV Position Input: right-click để xoay AGV ──────────────────────
        if self._pos_input_active:
            agv_id = self._get_agv_pos_at_screen(event.x, event.y)
            if agv_id:
                menu = tk.Menu(self, tearoff=0)
                menu.add_command(label="↻ Quay phải 90°",
                                 command=lambda: self._rotate_agv(agv_id, +1))
                menu.add_command(label="↺ Quay trái 90°",
                                 command=lambda: self._rotate_agv(agv_id, -1))
                menu.add_separator()
                pos = self._pos_input_agvs[agv_id]
                info = f"Thẻ: {pos['node']}  Prev: {pos['prev_node']}  Góc: {pos['angle']:.0f}°"
                menu.add_command(label=info, state="disabled")
                menu.tk_popup(event.x_root, event.y_root)
                return

        # Ưu tiên 1: Nếu click vào Node -> Edit Node
        node_id = self.get_node_at_pos((event.x, event.y))
        if node_id:
            self.open_node_editor(node_id)
        else:
            # Ưu tiên 2: Hủy thao tác vẽ Edge nếu đang vẽ
            self.temp_edge_start = None
            self.draw_map()

    def on_double_click(self, event):
        # 1. Kiểm tra click vào Node
        node_id = self.get_node_at_pos((event.x, event.y))
        if node_id:
            self.open_node_editor(node_id)
            return

        # 2. Kiểm tra click vào Edge
        edge = self.get_edge_at_pos((event.x, event.y))
        if edge:
            # Ctrl+double-click → chỉnh chiều dài cạnh
            if event.state & 0x4:
                self._edit_edge_length(edge)
            else:
                self.open_edge_editor(edge[0], edge[1])

    def _edit_edge_length(self, edge):
        """Ctrl+double-click lên cạnh → dialog nhập chiều dài thực + tùy chọn hiển thị."""
        u, v = edge
        edge_data = self.tm.graph.get_edge_data(u, v)
        if edge_data is None:
            return

        # Tính chiều dài hiện tại
        current_weight = edge_data.get('weight', 1)
        current_real_m = current_weight * self.meters_per_unit
        wu, wv = self._disp_xy(u), self._disp_xy(v)
        disp_geo = math.hypot(wv[0] - wu[0], wv[1] - wu[1])
        disp_m   = disp_geo * self.meters_per_unit

        # Tạo dialog
        dlg = tk.Toplevel(self)
        dlg.title(f"Cạnh {u} → {v}  —  Chiều dài")
        dlg.resizable(False, False)
        dlg.grab_set()

        pad = dict(padx=10, pady=4)

        # ── Chiều dài thực ────────────────────────────────────────────────────
        tk.Label(dlg, text="Chiều dài thực (m):", anchor='w').grid(row=0, column=0, sticky='w', **pad)
        var_real = tk.DoubleVar(value=round(current_real_m, 3))
        ent_real = tk.Entry(dlg, textvariable=var_real, width=14)
        ent_real.grid(row=0, column=1, sticky='w', **pad)
        ent_real.select_range(0, 'end')
        ent_real.focus_set()

        # ── Chiều dài hiển thị (read-only thông tin) ──────────────────────────
        tk.Label(dlg, text="Chiều dài trên bản đồ (m):", anchor='w').grid(row=1, column=0, sticky='w', **pad)
        tk.Label(dlg, text=f"{disp_m:.3f} m  (hình học, không đổi)",
                 fg="#555555").grid(row=1, column=1, sticky='w', **pad)

        # ── Tỉ lệ (thông tin) ────────────────────────────────────────────────
        ratio_str = f"× {current_real_m/disp_m:.2f}" if disp_m > 1e-6 else "N/A"
        tk.Label(dlg, text="Tỉ lệ thực / hiển thị:", anchor='w').grid(row=2, column=0, sticky='w', **pad)
        tk.Label(dlg, text=ratio_str, fg="#888888").grid(row=2, column=1, sticky='w', **pad)

        tk.Frame(dlg, height=1, bg="#cccccc").grid(row=3, column=0, columnspan=2, sticky='ew', padx=10, pady=2)

        # ── Checkboxes hiển thị ───────────────────────────────────────────────
        var_show_real = tk.BooleanVar(value=self.show_real_length)
        var_show_disp = tk.BooleanVar(value=self.show_display_length)
        tk.Checkbutton(dlg, text="Hiển thị chiều dài thực trên bản đồ",
                       variable=var_show_real).grid(row=4, column=0, columnspan=2, sticky='w', padx=10, pady=2)
        tk.Checkbutton(dlg, text="Hiển thị chiều dài bản đồ (hình học)",
                       variable=var_show_disp).grid(row=5, column=0, columnspan=2, sticky='w', padx=10, pady=2)

        tk.Frame(dlg, height=1, bg="#cccccc").grid(row=6, column=0, columnspan=2, sticky='ew', padx=10, pady=2)

        # ── Buttons ───────────────────────────────────────────────────────────
        def _ok():
            try:
                new_m = float(var_real.get())
            except (ValueError, tk.TclError):
                return
            if new_m <= 0:
                return
            self._push_history()
            self.tm.graph[u][v]['weight'] = new_m / self.meters_per_unit
            self.show_real_length    = var_show_real.get()
            self.show_display_length = var_show_disp.get()
            self.draw_map()
            dlg.destroy()

        def _cancel():
            # Vẫn áp dụng thay đổi checkbox dù hủy nhập chiều dài
            self.show_real_length    = var_show_real.get()
            self.show_display_length = var_show_disp.get()
            self.draw_map()
            dlg.destroy()

        frm_btn = tk.Frame(dlg)
        frm_btn.grid(row=7, column=0, columnspan=2, pady=8)
        tk.Button(frm_btn, text="✔ Lưu", command=_ok,     width=10, bg="#27ae60", fg="white").pack(side='left',  padx=4)
        tk.Button(frm_btn, text="✖ Hủy", command=_cancel, width=10).pack(side='left', padx=4)

        dlg.bind("<Return>", lambda _: _ok())
        dlg.bind("<Escape>", lambda _: _cancel())
        dlg.wait_window()

    def on_mouse_move(self, event):
        """Xử lý hiển thị Tooltip khi hover chuột"""
        if self.is_panning or self.dragging_node:
            self.hide_tooltip()
            return

        # 1. Check Node Hover
        node_id = self.get_node_at_pos((event.x, event.y))
        if node_id:
            self.show_node_tooltip(node_id, event.x, event.y)
            return

        # 2. Check Edge Hover
        edge = self.get_edge_at_pos((event.x, event.y))
        if edge:
            self.show_edge_tooltip(edge, event.x, event.y)
            return

        # 3. Nothing hovered
        self.hide_tooltip()

    def format_action_list(self, actions):
        """Helper để format danh sách action thành text dễ đọc"""
        if not actions: return ""
        lines = []
        for item in actions:
            code = 0
            val = 0
            if isinstance(item, dict):
                code = item.get('a', 0)
                val = item.get('v', 0)
            else:
                code = int(item)
            
            name = self.action_map.get(code, str(code)).split(' - ')[-1] # Lấy tên ngắn gọn
            lines.append(f"  • {name} (v={val})")
        return "\n".join(lines)

    def show_node_tooltip(self, node_id, x, y):
        node_data = self.tm.graph.nodes[node_id]
        role = node_data.get('role', 'none')
        actions = node_data.get('actions', [])
        
        text = f"Node: {node_id}\nType: {node_data.get('type', 'normal')}"
        if role != 'none': text += f"\nRole: {role.upper()}"
        
        act_str = self.format_action_list(actions)
        if act_str: text += f"\nActions:\n{act_str}"
        
        self.create_tooltip(text, x, y)

    def show_edge_tooltip(self, edge, x, y):
        u, v = edge
        data = self.tm.graph.edges[u, v]
        nav_act = data.get('a', 3)
        nav_name = self.action_map.get(nav_act, str(nav_act)).split(' - ')[-1]
        
        allowed   = data.get('allowed', True)
        direction = data.get('direction', 'forward')
        allow_str = "✅ Cho phép" if allowed else "🚫 Bị chặn"
        dir_str   = "⬆ Tiến" if direction == 'forward' else "⬇ Lùi"
        text = f"Route: {u} -> {v}  [{allow_str}] [{dir_str}]\nNav: {nav_name}"

        start_acts = self.format_action_list(data.get('actions', []))
        if start_acts: text += f"\nStart Acts:\n{start_acts}"

        end_acts = self.format_action_list(data.get('end_actions', []))
        if end_acts: text += f"\nEnd Acts:\n{end_acts}"
        
        self.create_tooltip(text, x, y)

    def create_tooltip(self, text, x, y):
        self.hide_tooltip() # Xóa cái cũ trước
        self.tooltip_window = tk.Toplevel(self)
        self.tooltip_window.wm_overrideredirect(True) # Bỏ thanh tiêu đề
        self.tooltip_window.geometry(f"+{self.winfo_rootx() + x + 15}+{self.winfo_rooty() + y + 15}")
        
        lbl = tk.Label(self.tooltip_window, text=text, justify='left', 
                       bg="#ffffe0", fg="black", relief="solid", borderwidth=1, font=("Arial", 9))
        lbl.pack()

    def hide_tooltip(self):
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None

    def open_node_editor(self, node_id):
        """Mở cửa sổ chỉnh sửa thuộc tính Node (ID, Type, Actions)"""
        dialog = tk.Toplevel(self)
        dialog.title(f"{self.t('ed_title_node')} {node_id}")
        dialog.geometry("400x450")
        node_data = self.tm.graph.nodes[node_id]
        current_actions = node_data.get('actions', [])
        
        # 1. Node ID
        ttk.Label(dialog, text=self.t("ed_node_id")).pack(pady=5)
        ent_id = ttk.Entry(dialog)
        ent_id.insert(0, str(node_id))
        ent_id.pack()
        
        # 2. Node Function (Merged Type & Role)
        # Định nghĩa mapping để hiển thị thân thiện hơn
        # Wait/Delivery are managed via Station Settings tab, not manually here
        FUNC_MAP = {
            "Normal Path (Đường đi)":  {"type": "normal",       "role": "none"},
            "Intersection (Giao lộ)":  {"type": "intersection", "role": "none"},
            "Charger (Trạm sạc)":      {"type": "station",      "role": "charger"},
        }
        # Reverse map để tìm key từ value hiện tại
        curr_type = node_data.get('type', 'normal')
        curr_role = node_data.get('role', 'none')
        current_func_name = "Normal Path (Đường đi)" # Default
        
        for name, attrs in FUNC_MAP.items():
            if attrs['type'] == curr_type and attrs['role'] == curr_role:
                current_func_name = name
                break

        ttk.Label(dialog, text=self.t("ed_func")).pack(pady=5)
        cb_func = ttk.Combobox(dialog, values=list(FUNC_MAP.keys()), width=30, state="readonly")
        cb_func.set(current_func_name)
        cb_func.pack()

        # 3. Action List (Multi-action support)
        ttk.Label(dialog, text=self.t("ed_act_seq")).pack(pady=(10, 0))
        
        frm_actions = ttk.Frame(dialog)
        frm_actions.pack(fill='both', expand=True, padx=10, pady=5)
        
        # Listbox hiển thị các action đã chọn
        lst_actions = tk.Listbox(frm_actions, height=6)
        lst_actions.pack(fill='x', expand=True, pady=2)
        
        # Load existing actions (Support both int and dict format)
        for item in current_actions:
            code = 0
            val = 0
            if isinstance(item, dict):
                code = item.get('a', 0)
                val = item.get('v', 0)
            else: # Old format
                code = int(item)
                val = 0
            
            name = self.action_map.get(code, str(code))
            display_str = f"{name} [v={val}]"
            lst_actions.insert(tk.END, display_str)
            
        # Controls thêm/xóa action
        frm_btns = ttk.Frame(frm_actions)
        frm_btns.pack(fill='x')
        
        # Combobox chọn Action mới
        cb_new_action = ttk.Combobox(frm_btns, values=list(self.action_map.values()), state="readonly", width=15)
        cb_new_action.pack(side='left', fill='x', expand=True)
        if self.action_map: cb_new_action.current(0)
        
        # Entry for value
        ttk.Label(frm_btns, text="v:").pack(side='left', padx=(2,0))
        ent_act_val = ttk.Entry(frm_btns, width=5)
        ent_act_val.insert(0, "0")
        ent_act_val.pack(side='left', padx=2)
        
        def add_action():
            selection = cb_new_action.get()
            val_str = ent_act_val.get()
            if selection:
                display = f"{selection} [v={val_str}]"
                lst_actions.insert(tk.END, display)
            
        def remove_action():
            sel = lst_actions.curselection()
            if sel:
                lst_actions.delete(sel)
                
        ttk.Button(frm_btns, text="+", width=3, command=add_action).pack(side='left')
        ttk.Button(frm_btns, text="-", width=3, command=remove_action).pack(side='left')
        def save_changes():
            try:
                new_id = int(ent_id.get())
                selected_func = cb_func.get()
                new_attrs = FUNC_MAP.get(selected_func, {"type": "normal", "role": "none"})
                self._push_history()  # Lưu trước khi sửa thuộc tính node
                
                new_type = new_attrs['type']
                new_role = new_attrs['role']

                # Parse actions from Listbox
                new_actions_list = []
                for item in lst_actions.get(0, tk.END):
                    try:
                        # Parse string: "4 - Change Speed [v=50]"
                        parts = item.split(' - ')
                        code = int(parts[0].strip())
                        
                        val = 0
                        if '[v=' in item:
                            val_str = item.split('[v=')[1].split(']')[0]
                            val = int(val_str)
                            
                        new_actions_list.append({"a": code, "v": val})
                    except Exception as e:
                        print(f"Error parsing node action '{item}': {e}")

                # Cập nhật dữ liệu
                self.tm.graph.nodes[node_id]['type'] = new_type
                self.tm.graph.nodes[node_id]['role'] = new_role
                self.tm.graph.nodes[node_id]['actions'] = new_actions_list
                
                if new_id != node_id:
                    if self.tm.relabel_node(node_id, new_id):
                        self.selected_node = new_id
                
                self.draw_map()
                dialog.destroy()
            except ValueError:
                tk.messagebox.showerror("Error", "Invalid Node ID or Value")
        
        ttk.Button(dialog, text=self.t("ed_save"), command=save_changes).pack(pady=10)

    def open_edge_editor(self, u, v):
        """Mở cửa sổ chỉnh sửa thuộc tính Cạnh (Action di chuyển)"""
        dialog = tk.Toplevel(self)
        dialog.title(f"{self.t('ed_title_edge')}: {u} <-> {v}")
        dialog.geometry("550x650") # Tăng kích thước
        
        # Lấy danh sách action để fill vào combobox
        # Sắp xếp theo ID để dễ nhìn
        sorted_actions = sorted(self.action_map.items())
        action_values = [val for key, val in sorted_actions]
        
        # --- Helper Function để tạo UI cho 1 chiều ---
        def create_direction_ui(parent, node_from, node_to, result_holder):
            frame = ttk.LabelFrame(parent, text=f"Direction: {node_from}  --->  {node_to}")
            frame.pack(fill='x', padx=10, pady=10)

            edge_data = self.tm.graph.get_edge_data(node_from, node_to)
            if edge_data is None:
                # Nút tạo nhanh cạnh ngược chiều nếu chưa có
                def create_reverse_edge():
                    self._push_history()  # Lưu trước khi tạo cạnh ngược
                    # Tạo cạnh với action mặc định là 3 (RUN)
                    self.tm.add_edge(node_from, node_to, action=3)
                    self.draw_map()
                    dialog.destroy()
                    # Mở lại cửa sổ editor để cập nhật UI
                    self.open_edge_editor(u, v)

                ttk.Label(frame, text=self.t("ed_no_conn"), foreground="gray").pack(side='left', padx=5, pady=10)
                ttk.Button(frame, text=self.t("ed_create_conn"), command=create_reverse_edge).pack(side='right', padx=5, pady=10)
                return
            
            curr_act = edge_data.get('a', 3) # Default RUN
            curr_start_acts = edge_data.get('actions', [])
            curr_end_acts = edge_data.get('end_actions', [])
            curr_str = self.action_map.get(curr_act, f"{curr_act} - Unknown")
            curr_param = edge_data.get('p', 0)
            curr_allowed   = edge_data.get('allowed', True)
            curr_direction = edge_data.get('direction', 'forward')

            # --- SECTION 0: ALLOWED + DIRECTION ---
            f_flags = ttk.Frame(frame)
            f_flags.pack(fill='x', padx=5, pady=(4, 0))

            var_allowed = tk.BooleanVar(value=curr_allowed)
            chk_allowed = ttk.Checkbutton(f_flags, text="✅ Cho phép đi (Allowed)", variable=var_allowed)
            chk_allowed.pack(side='left', padx=4)

            ttk.Label(f_flags, text="  Chiều AGV:").pack(side='left')
            var_direction = tk.StringVar(value=curr_direction)
            cb_dir = ttk.Combobox(f_flags, textvariable=var_direction,
                                  values=["forward", "backward"], state='readonly', width=10)
            cb_dir.pack(side='left', padx=4)
            ttk.Label(f_flags, text="(forward=tiến, backward=lùi)", foreground="#888",
                      font=("Arial", 8)).pack(side='left')

            result_holder['var_allowed']   = var_allowed
            result_holder['var_direction'] = var_direction

            # --- SECTION 1: MAIN NAVIGATION (Di chuyển chính) ---
            f_nav = ttk.LabelFrame(frame, text=self.t("ed_nav_main"))
            f_nav.pack(fill='x', padx=5, pady=5)
            
            cb = ttk.Combobox(f_nav, values=action_values, state="readonly")
            cb.set(curr_str)
            cb.pack(side='left', fill='x', expand=True, padx=5, pady=5)
            
            ttk.Label(f_nav, text="Param (v):").pack(side='left')
            ent_param = ttk.Entry(f_nav, width=8)
            ent_param.insert(0, str(curr_param))
            ent_param.pack(side='left', padx=5)

            # --- SECTION 2: SPECIAL TASKS (Nhiệm vụ đặc biệt) ---
            sub_frame = ttk.LabelFrame(frame, text=self.t("ed_task_spec"))
            sub_frame.pack(fill='x', padx=5, pady=5)
            
            # Helper cho Listbox Action
            def create_action_list_ui(container, label_text, initial_acts):
                lbl = ttk.Label(container, text=label_text, font=("Arial", 8, "bold"))
                lbl.pack(anchor='w')
                
                lst = tk.Listbox(container, height=4, width=30)
                lst.pack(fill='x', pady=2)
                
                # Load existing actions (Support both int and dict format)
                for item in initial_acts:
                    code = 0
                    val = 0
                    if isinstance(item, dict):
                        code = item.get('a', 0)
                        val = item.get('v', 0)
                    else:
                        code = int(item)
                        val = 0
                    
                    name = self.action_map.get(code, str(code))
                    display_str = f"{name} [v={val}]"
                    lst.insert(tk.END, display_str)
                    
                btn_box = ttk.Frame(container)
                btn_box.pack(fill='x')
                
                # Combobox chọn Action
                cb_add = ttk.Combobox(btn_box, values=action_values, state="readonly", width=12)
                cb_add.pack(side='left', fill='x', expand=True)
                if action_values: cb_add.current(0)
                
                # Entry nhập Value cho Action
                ttk.Label(btn_box, text="v:").pack(side='left', padx=(2,0))
                ent_act_val = ttk.Entry(btn_box, width=5)
                ent_act_val.insert(0, "0")
                ent_act_val.pack(side='left', padx=2)
                
                def add_item():
                    act_str = cb_add.get()
                    val_str = ent_act_val.get().strip()
                    if not val_str: val_str = "0"
                    
                    if act_str:
                        # Format hiển thị: "4 - Change Speed [v=50]"
                        display = f"{act_str} [v={val_str}]"
                        lst.insert(tk.END, display)
                
                def del_item():
                    sel = lst.curselection()
                    if sel: lst.delete(sel)
                    
                ttk.Button(btn_box, text="+", width=3, command=add_item).pack(side='left')
                ttk.Button(btn_box, text="-", width=3, command=del_item).pack(side='left')
                
                return lst

            # Start Actions UI
            f_start = ttk.Frame(sub_frame); f_start.pack(side='left', fill='both', expand=True, padx=2)
            lst_start = create_action_list_ui(f_start, f"{self.t('ed_start_act')} ({node_from}):", curr_start_acts)
            
            # End Actions UI
            f_end = ttk.Frame(sub_frame); f_end.pack(side='left', fill='both', expand=True, padx=2)
            lst_end = create_action_list_ui(f_end, f"{self.t('ed_end_act')} ({node_to}):", curr_end_acts)
            
            # Lưu tham chiếu vào result_holder để hàm save lấy dữ liệu
            result_holder['cb'] = cb
            result_holder['ent_param'] = ent_param
            result_holder['lst_start'] = lst_start
            result_holder['lst_end'] = lst_end

        # --- UI cho Chiều đi (U -> V) ---
        res_uv = {}
        create_direction_ui(dialog, u, v, res_uv)
        
        # --- UI cho Chiều về (V -> U) ---
        res_vu = {}
        create_direction_ui(dialog, v, u, res_vu)
        
        def save_edge():
            self._push_history()  # Lưu trước khi sửa thuộc tính cạnh
            def get_codes_from_listbox(lstbox):
                # Trả về danh sách dict: [{"a": 1, "v": 0}, {"a": 4, "v": 50}]
                actions_list = []
                for item in lstbox.get(0, tk.END):
                    try:
                        # Parse string: "4 - Change Speed [v=50]"
                        parts = item.split(' - ')
                        code = int(parts[0].strip())
                        
                        val = 0
                        if '[v=' in item:
                            val_str = item.split('[v=')[1].split(']')[0]
                            val = int(val_str)
                            
                        actions_list.append({"a": code, "v": val})
                    except Exception as e:
                        print(f"Error parsing edge action '{item}': {e}")
                return actions_list

            # Lưu chiều U->V
            if 'cb' in res_uv:
                sel = res_uv['cb'].get()
                if sel:
                    code      = int(sel.split(' - ')[0])
                    s_acts    = get_codes_from_listbox(res_uv['lst_start'])
                    e_acts    = get_codes_from_listbox(res_uv['lst_end'])
                    param     = int(res_uv['ent_param'].get()) if res_uv['ent_param'].get().isdigit() else 0
                    allowed_v = res_uv.get('var_allowed', tk.BooleanVar(value=True)).get()
                    dir_v     = res_uv.get('var_direction', tk.StringVar(value='forward')).get()

                    self.tm.add_edge(u, v, action=code, actions=s_acts, end_actions=e_acts,
                                     action_param=param, allowed=allowed_v, direction=dir_v)
                    print(f"Updated {u}->{v}: Nav={code}, Allowed={allowed_v}, Dir={dir_v}")

            # Lưu chiều V->U
            if 'cb' in res_vu:
                sel = res_vu['cb'].get()
                if sel:
                    code      = int(sel.split(' - ')[0])
                    s_acts    = get_codes_from_listbox(res_vu['lst_start'])
                    e_acts    = get_codes_from_listbox(res_vu['lst_end'])
                    param     = int(res_vu['ent_param'].get()) if res_vu['ent_param'].get().isdigit() else 0
                    allowed_v = res_vu.get('var_allowed', tk.BooleanVar(value=True)).get()
                    dir_v     = res_vu.get('var_direction', tk.StringVar(value='forward')).get()

                    self.tm.add_edge(v, u, action=code, actions=s_acts, end_actions=e_acts,
                                     action_param=param, allowed=allowed_v, direction=dir_v)
                    print(f"Updated {v}->{u}: Nav={code}, Allowed={allowed_v}, Dir={dir_v}")
                    
            dialog.destroy()
            
        ttk.Button(dialog, text=self.t("ed_save_change"), command=save_edge).pack(pady=10)

    def on_zoom(self, event):
        # Zoom logic
        scale_factor = 1.1
        if event.num == 5 or event.delta < 0:
            scale_factor = 0.9
        
        # Zoom tại tâm chuột (cơ bản: zoom tại gốc 0,0 rồi dịch chuyển)
        # Để đơn giản, ta zoom tại góc trên trái hoặc tâm màn hình hiện tại
        self.scale *= scale_factor
        # Giới hạn zoom
        if self.scale < 0.05: self.scale = 0.05
        if self.scale > 20.0: self.scale = 20.0
        self.draw_map()
        if self.on_zoom_changed:
            self.on_zoom_changed(self.scale)

    def animate(self):
        self.draw_map()
        # Schedule next frame (100ms = 10fps)
        self.after(100, self.animate)

    def draw_map(self):
        self.delete("all")
        
        # Draw Edges
        for u, v, attrs in self.tm.graph.edges(data=True):
            if u in self.tm.graph.nodes and v in self.tm.graph.nodes:
                start_pos = self.to_screen(*self._disp_xy(u))
                end_pos   = self.to_screen(*self._disp_xy(v))

                # Highlight cạnh được chọn bằng màu đỏ / dày hơn
                is_selected_edge = (self.selected_edge == (u, v))
                line_color = "#e74c3c" if is_selected_edge else "black"
                line_width = 3 if is_selected_edge else 1

                self.create_line(start_pos[0], start_pos[1], end_pos[0], end_pos[1],
                                 arrow=tk.LAST, fill=line_color, width=line_width)

                # Draw direction dot + edge length label
                mid_x = (start_pos[0] + end_pos[0]) / 2
                mid_y = (start_pos[1] + end_pos[1]) / 2
                dot_color = "#e74c3c" if is_selected_edge else "black"
                self.create_oval(mid_x-2, mid_y-2, mid_x+2, mid_y+2, fill=dot_color)

                # Hiển thị chiều dài cạnh (thực và/hoặc trên bản đồ)
                # Nếu cạnh ngược (v→u) cũng tồn tại, chỉ vẽ nhãn 1 lần (cho cạnh có u < v)
                reverse_exists = self.tm.graph.has_edge(v, u)
                skip_label = reverse_exists and (u > v)
                if not skip_label and self.scale > 0.4 and self.meters_per_unit > 0 and (self.show_real_length or self.show_display_length):
                    lbl_col = "#c0392b" if is_selected_edge else "#555555"
                    # Xoay label song song với cạnh, đặt bên trái hướng đi
                    ex_px = end_pos[0] - start_pos[0]
                    ey_px = end_pos[1] - start_pos[1]
                    edge_len_px = math.hypot(ex_px, ey_px)
                    if edge_len_px > 1e-6:
                        ux, uy = ex_px / edge_len_px, ey_px / edge_len_px
                        lx = mid_x + (-uy) * 10
                        ly = mid_y + ( ux) * 10
                        angle_deg = -math.degrees(math.atan2(ey_px, ex_px))
                        if angle_deg < -90 or angle_deg > 90:
                            angle_deg += 180
                    else:
                        lx, ly, angle_deg = mid_x, mid_y - 10, 0

                    # Tính chiều dài thực (từ weight)
                    real_m = attrs.get('weight', 1) * self.meters_per_unit
                    # Tính chiều dài hiển thị trên bản đồ (khoảng cách hình học ÷ scale → world units → mét)
                    wu, wv = self._disp_xy(u), self._disp_xy(v)
                    disp_geo = math.hypot(wv[0] - wu[0], wv[1] - wu[1])
                    disp_m   = disp_geo * self.meters_per_unit

                    parts = []
                    if self.show_real_length:
                        parts.append(f"{real_m:.1f}m")
                    if self.show_display_length:
                        parts.append(f"[{disp_m:.1f}m]")
                    label_text = "  ".join(parts)
                    if label_text:
                        self.create_text(lx, ly, text=label_text,
                                         fill=lbl_col, font=("Segoe UI", 7),
                                         angle=angle_deg)

        # Draw planned routes for each AGV as dashed colored lines (Monitor mode only)
        if self.tool == "monitor":
            num_agvs = len(self.agv_list)
            for agv_idx, agv in enumerate(self.agv_list):
                if not agv.full_path or len(agv.full_path) < 2:
                    continue
                fill_color = getattr(agv, 'color', '#3498db')
                if not fill_color or not isinstance(fill_color, str):
                    fill_color = '#3498db'
                path = agv.full_path
                # Perpendicular offset: spread routes so they don't overlap
                offset_mag = (agv_idx - (num_agvs - 1) / 2.0) * 5
                for i in range(len(path) - 1):
                    u, v = path[i], path[i + 1]
                    if u not in self.tm.graph.nodes or v not in self.tm.graph.nodes:
                        continue
                    x1, y1 = self.to_screen(*self._disp_xy(u))
                    x2, y2 = self.to_screen(*self._disp_xy(v))
                    dx, dy = x2 - x1, y2 - y1
                    length = math.sqrt(dx * dx + dy * dy) or 1
                    ox = (-dy / length) * offset_mag
                    oy = (dx / length) * offset_mag
                    self.create_line(
                        x1 + ox, y1 + oy, x2 + ox, y2 + oy,
                        fill=fill_color, width=2, dash=(10, 6)
                    )

        # Draw Temp Line (Elastic line when dragging)
        if self.tool == "edge" and self.temp_edge_start and self.temp_mouse_pos:
            sx, sy = self.to_screen(*self._disp_xy(self.temp_edge_start))
            ex, ey = self.temp_mouse_pos
            self.create_line(sx, sy, ex, ey, dash=(4, 2), fill="gray")

        # ── Draw Zone Overlays ─────────────────────────────────────────────────
        if self.zone_mgr:
            _ZONE_COLORS = {
                "INTERSECTION": "#FF8C00",
                "SINGLE_LANE":  "#0066CC",
                "RESOURCE":     "#9933CC",
                "BYPASS":       "#00AA44",   # Xanh lá = vùng né (luôn được vào)
            }
            for zone in self.zone_mgr.zones.values():
                valid_nodes = [n for n in zone.nodes if self.tm.graph.has_node(n)]
                if not valid_nodes:
                    continue
                # Bounding box với padding
                xs = [self._disp_xy(n)[0] for n in valid_nodes]
                ys = [self._disp_xy(n)[1] for n in valid_nodes]
                PAD = 18 / self.scale
                x1, y1 = min(xs) - PAD, min(ys) - PAD
                x2, y2 = max(xs) + PAD, max(ys) + PAD
                sx1, sy1 = self.to_screen(x1, y1)
                sx2, sy2 = self.to_screen(x2, y2)
                color = _ZONE_COLORS.get(zone.type, "#888888")
                # Nền stipple (giả trong suốt)
                self.create_rectangle(sx1, sy1, sx2, sy2,
                                      outline=color, width=2, dash=(6, 3),
                                      fill=color, stipple="gray12")
                # Nhãn zone — có thể kéo để tránh chồng chéo
                default_sx = (sx1 + sx2) / 2
                default_sy = sy1 - 8
                odx, ody   = self._zone_label_offsets.get(zone.id, (0, 0))
                lx = default_sx + odx * self.scale
                ly = default_sy + ody * self.scale
                self._zone_label_screen_pos[zone.id] = (lx, ly)
                holders  = list(zone.holders)
                hold_str = f" [{', '.join(holders)}]" if holders else ""
                # Hiệu ứng kéo: viền nền khi đang drag
                is_dragging = (self._dragging_zone_label == zone.id)
                bg_col = "#fffbe6" if is_dragging else ""
                if is_dragging:
                    self.create_rectangle(lx - 70, ly - 12, lx + 70, ly + 4,
                                          fill="#fffbe6", outline=color, width=1)
                self.create_text(lx, ly, text=f"⬡ {zone.name}{hold_str}",
                                 fill=color, font=("Arial", 8, "bold"), anchor='s')

        # Draw Nodes  (dùng disp_xy cho Schematic Layout)
        for node_id, attrs in self.tm.graph.nodes(data=True):
            x, y = self.to_screen(*self._disp_xy(node_id))
            color = "blue"
            if attrs.get('type') == 'station':
                color = "green"
            
            # Vẽ viền khác cho các Role đặc biệt
            role = attrs.get('role', 'none')
            width = 1
            if role == 'charger': width = 3; color = "orange"
            elif role == 'wait': width = 3; color = "cyan"
            
            if node_id == self.selected_node:
                color = "yellow"
            elif node_id in self.selected_nodes:
                color = "#ffe066"  # Light yellow for multi-select

            r = 10
            self.create_oval(x-r, y-r, x+r, y+r, fill=color, outline="black", width=width)
            self.create_text(x+14, y-8, text=str(node_id), fill="black", anchor='w')
            # Show team label for wait nodes
            if role == 'wait':
                team_id = attrs.get('team_id', '')
                if team_id != '':
                    self.create_text(x, y + r + 10, text=f"Tổ {team_id}", fill="#005580", font=("Arial", 7, "bold"))
            # Show charger name for charger nodes
            elif role == 'charger':
                chg_name = attrs.get('name', '')
                if chg_name:
                    self.create_text(x, y + r + 10, text=chg_name, fill="#b35a00", font=("Arial", 7, "bold"))

        # Draw AGVs (Only in Monitor Mode)
        if self.tool == "monitor":
            now_tick = time.time()
            unknown_count = 0
            for agv in self.agv_list:
                try:
                    # Bug fix: khi position_input đang active và AGV có trong overlay,
                    # bỏ qua normal rendering để tránh vẽ 2 icon (1 normal + 1 pos_input)
                    if self._pos_input_active and agv.id in self._pos_input_agvs:
                        continue

                    draw_x, draw_y = 0, 0
                    is_running = (agv.status == "auto" and agv.action_info == "running")
                    has_next = False  # Có node tiếp theo để nội suy không

                    # 1. Nếu có tag trong map
                    if agv.current_tag in self.tm.graph.nodes:
                        start_x, start_y = self.to_screen(*self._disp_xy(agv.current_tag))
                        draw_x, draw_y = start_x, start_y

                        # 2. Nội suy vị trí — dùng phase counter độc lập (không phụ thuộc MQTT)
                        if is_running and agv.full_path:
                            try:
                                if agv.current_tag in agv.full_path:
                                    idx = agv.full_path.index(agv.current_tag)
                                    if idx < len(agv.full_path) - 1:
                                        next_tag = agv.full_path[idx + 1]
                                        if next_tag in self.tm.graph.nodes:
                                            end_x, end_y = self.to_screen(*self._disp_xy(next_tag))
                                            has_next = True

                                            # Phase counter: tăng liên tục 0→1 rồi reset về 0 (không đảo chiều)
                                            # CYCLE được điều chỉnh theo tỉ lệ chiều dài thực / chiều dài hiển thị
                                            BASE_CYCLE = 2.0  # giây khi chiều dài thực == chiều dài hiển thị
                                            edge_data_anim = self.tm.graph.get_edge_data(agv.current_tag, next_tag) or {}
                                            real_w   = edge_data_anim.get('weight', 1)
                                            wu_a, wv_a = self._disp_xy(agv.current_tag), self._disp_xy(next_tag)
                                            geo_w    = math.hypot(wv_a[0] - wu_a[0], wv_a[1] - wu_a[1]) or 1
                                            # CYCLE tỉ lệ với real_length/visual_length (cạnh dài thực thì di chuyển chậm hơn trên màn hình)
                                            CYCLE = BASE_CYCLE * (real_w / geo_w)
                                            CYCLE = max(0.2, CYCLE)  # Tối thiểu 0.2s để tránh nhấp nháy
                                            phase, last_tick = self._agv_anim.get(agv.id, (0.0, now_tick))
                                            delta = now_tick - last_tick
                                            phase += delta / CYCLE
                                            if phase >= 1.0:
                                                phase -= 1.0  # Reset về 0, không đảo chiều
                                            self._agv_anim[agv.id] = (phase, now_tick)

                                            progress = min(phase, 0.92)
                                            draw_x = start_x + (end_x - start_x) * progress
                                            draw_y = start_y + (end_y - start_y) * progress
                            except Exception:
                                pass
                        else:
                            # Không di chuyển → reset phase về 0
                            self._agv_anim[agv.id] = (0.0, now_tick)
                    else:
                        # AGV chưa có vị trí / tag lạ → xếp hàng ở góc
                        start_x = 50
                        start_y = 40
                        gap = 60
                        max_per_row = 10
                        col = unknown_count % max_per_row
                        row = unknown_count // max_per_row
                        draw_x = start_x + col * gap
                        draw_y = start_y + row * gap
                        unknown_count += 1
                        self._agv_anim[agv.id] = (0.0, now_tick)

                    # ── Sau khi lùi vào trạm: lưu góc đầu xe ĐÚNG (hướng RA khỏi trạm) ──
                    # agv_instance set _clear_heading_flag=True khi return_reversing_charge xong
                    # Trước đây: xóa _manual_angles → fallback dùng prev_tag→current_tag = 6 giờ (sai)
                    # Bây giờ: SET _manual_angles = ngược chiều di chuyển = đầu xe hướng ra ngoài trạm
                    if getattr(agv, '_clear_heading_flag', False):
                        agv._clear_heading_flag = False
                        self._manual_anim.pop(agv.id, None)
                        ct = getattr(agv, 'current_tag', 0)
                        pt = getattr(agv, 'prev_tag', 0)
                        if (pt > 0 and ct > 0
                                and self.tm.graph.has_node(pt)
                                and self.tm.graph.has_node(ct)):
                            cx_w, cy_w = self._disp_xy(ct)
                            px_w, py_w = self._disp_xy(pt)
                            # Chiều di chuyển khi đến trạm: prev→current (= chiều lùi đuôi xe)
                            # Đầu xe = ngược lại → cộng π
                            head_angle = math.atan2(cy_w - py_w, cx_w - px_w) + math.pi
                            self._manual_angles[agv.id] = head_angle
                        else:
                            self._manual_angles.pop(agv.id, None)

                    # ── Manual Animation Override ────────────────────────────────
                    # Nếu có animation thủ công (deba / turn), override draw_x/draw_y/dx_arr/dy_arr
                    _manim = self._manual_anim.get(agv.id)
                    _manim_angle_rad = None  # None = không override hướng
                    if _manim:
                        elapsed = now_tick - _manim['start_t']
                        dur     = _manim['duration']
                        t       = min(elapsed / dur, 1.0) if dur > 0 else 1.0

                        if _manim['type'] == 'move':
                            # Tự dừng khi MQTT xác nhận tag mới (AGV đã đến node kế)
                            if agv.current_tag != _manim.get('from_node', agv.current_tag):
                                del self._manual_anim[agv.id]
                                _manim = None
                            else:
                                # Nội suy vị trí bằng WORLD coords → convert to screen tại draw time
                                # → đúng kể cả khi zoom/pan sau khi animation bắt đầu
                                f_sx, f_sy = self.to_screen(_manim['from_wx'], _manim['from_wy'])
                                t_sx, t_sy = self.to_screen(_manim['to_wx'],   _manim['to_wy'])
                                draw_x = f_sx + (t_sx - f_sx) * t
                                draw_y = f_sy + (t_sy - f_sy) * t
                                _manim_angle_rad = _manim['angle_rad']
                                if t >= 1.0:
                                    del self._manual_anim[agv.id]

                        elif _manim['type'] == 'turn':
                            # Auto-rotation: dừng sớm nếu AGV đã rời thẻ quay
                            if (_manim.get('auto_rotation')
                                    and agv.current_tag != _manim.get('at_tag')):
                                self._manual_angles[agv.id] = _manim['to_angle']
                                del self._manual_anim[agv.id]
                                _manim = None
                            else:
                                ease_t = math.sin(t * math.pi / 2)  # ease-out
                                angle  = _manim['from_angle'] + (_manim['to_angle'] - _manim['from_angle']) * ease_t
                                _manim_angle_rad = angle
                                # Vị trí từ world coords
                                draw_x, draw_y = self.to_screen(_manim['wx'], _manim['wy'])
                                if t >= 1.0:
                                    self._manual_angles[agv.id] = _manim['to_angle']
                                    del self._manual_anim[agv.id]

                    # Giữ hướng sau quay nếu không có animation và AGV đang dừng
                    # Khi is_running=True: prev_tag→current_tag chính xác hơn
                    elif agv.id in self._manual_angles and not is_running:
                        _manim_angle_rad = self._manual_angles[agv.id]

                    # Màu sắc
                    fill_color = getattr(agv, 'color', '#3498db')
                    if not fill_color or not isinstance(fill_color, str):
                        fill_color = '#3498db'

                    # --- Vector hướng đầu AGV ---
                    dx_arr, dy_arr = 1.0, 0.0
                    dir_known = False

                    # Khi AGV đang chạy: ưu tiên hướng TIẾP THEO (current → next)
                    # → hiển thị chính xác ngay tại điểm quay (không còn lag 1 thẻ)
                    # Dùng disp_xy để khớp với vị trí hiển thị trên bản đồ (tránh lệch hướng
                    # khi node đã được kéo thả trên map editor: disp_x ≠ x).
                    if is_running and agv.full_path and agv.current_tag in agv.full_path:
                        try:
                            _idx = agv.full_path.index(agv.current_tag)
                            if _idx < len(agv.full_path) - 1:
                                _nt = agv.full_path[_idx + 1]
                                if _nt in self.tm.graph.nodes and agv.current_tag in self.tm.graph.nodes:
                                    _cx, _cy = self._disp_xy(agv.current_tag)
                                    _nx, _ny = self._disp_xy(_nt)
                                    dx_arr = _nx - _cx
                                    dy_arr = _ny - _cy
                                    dir_known = True
                        except Exception:
                            pass

                    # Khi idle / dừng: dùng hướng lần di chuyển cuối (prev → current)
                    if not dir_known:
                        prev_t = getattr(agv, 'prev_tag', 0)
                        if (prev_t and prev_t != agv.current_tag
                                and prev_t in self.tm.graph.nodes
                                and agv.current_tag in self.tm.graph.nodes):
                            _px, _py = self._disp_xy(prev_t)
                            _cx, _cy = self._disp_xy(agv.current_tag)
                            dx_arr = _cx - _px
                            dy_arr = _cy - _py
                            dir_known = True

                    # Fallback: current → next ngay cả khi không running
                    if not dir_known and agv.full_path and agv.current_tag in agv.full_path:
                        try:
                            _idx = agv.full_path.index(agv.current_tag)
                            if _idx < len(agv.full_path) - 1:
                                _nt = agv.full_path[_idx + 1]
                                if _nt in self.tm.graph.nodes and agv.current_tag in self.tm.graph.nodes:
                                    _cx, _cy = self._disp_xy(agv.current_tag)
                                    _nx, _ny = self._disp_xy(_nt)
                                    dx_arr = _nx - _cx
                                    dy_arr = _ny - _cy
                        except Exception:
                            pass

                    # Manual animation override hướng (move/turn)
                    # _manim_angle_rad từ start_auto_rotation đã tính đúng hướng ĐẦU xe
                    # (kể cả khi lùi — xử lý trong start_auto_rotation với is_bwd flip)
                    if _manim_angle_rad is not None:
                        dx_arr = math.cos(_manim_angle_rad)
                        dy_arr = math.sin(_manim_angle_rad)
                    else:
                        # Chuẩn hóa vector hướng thông thường
                        _len = math.sqrt(dx_arr**2 + dy_arr**2)
                        if _len > 0:
                            dx_arr /= _len
                            dy_arr /= _len
                        else:
                            dx_arr, dy_arr = 1.0, 0.0

                    # Đảo chiều vector hiển thị khi xe đang chạy lùi:
                    #   - return_reversing_charge: luôn flip (kể cả khi đỗ tại trạm)
                    #   - DIR_BWD trong plan thông thường: flip khi đang điều hướng
                    # Chỉ áp dụng khi KHÔNG có animation (animation đã tự xử lý flip)
                    _is_bwd_display = (
                        getattr(agv, 'current_task_type', '') == 'return_reversing_charge'
                        or (getattr(agv, 'is_navigating', False)
                            and getattr(agv, '_current_dir', 7) == 8)  # 8 = ACT_DIR_BWD
                    )
                    if _manim_angle_rad is None and _is_bwd_display:
                        dx_arr, dy_arr = -dx_arr, -dy_arr

                    # --- Vẽ hình chữ nhật AGV theo hướng đầu xe ---
                    HL = 15  # half-length (đuôi ↔ đầu)
                    HW = 9   # half-width
                    perp_x = -dy_arr  # vector vuông góc (bên phải của hướng đi)
                    perp_y =  dx_arr
                    corners = [
                        draw_x + dx_arr*HL + perp_x*HW,
                        draw_y + dy_arr*HL + perp_y*HW,   # đầu-phải
                        draw_x + dx_arr*HL - perp_x*HW,
                        draw_y + dy_arr*HL - perp_y*HW,   # đầu-trái
                        draw_x - dx_arr*HL - perp_x*HW,
                        draw_y - dy_arr*HL - perp_y*HW,   # đuôi-trái
                        draw_x - dx_arr*HL + perp_x*HW,
                        draw_y - dy_arr*HL + perp_y*HW,   # đuôi-phải
                    ]
                    self.create_polygon(corners, fill=fill_color, outline="black", width=2)

                    # Mũi tên trắng từ tâm → đầu xe
                    self.create_line(
                        draw_x, draw_y,
                        draw_x + dx_arr * (HL - 2),
                        draw_y + dy_arr * (HL - 2),
                        fill="white", width=2,
                        arrow=tk.LAST, arrowshape=(7, 9, 3)
                    )

                    # --- Tên AGV: đặt vuông góc với chiều đi, xoay chữ theo hướng AGV ---
                    # Chọn bên vuông góc "phía trên" nhất trong screen (y nhỏ hơn = cao hơn)
                    p1x, p1y = dy_arr, -dx_arr    # bên trái hướng đi
                    p2x, p2y = -dy_arr, dx_arr    # bên phải hướng đi
                    if p1y <= p2y:
                        lbl_px, lbl_py = p1x, p1y
                    else:
                        lbl_px, lbl_py = p2x, p2y
                    label_x = draw_x + lbl_px * (HW + 10)
                    label_y = draw_y + lbl_py * (HW + 10)
                    # Góc xoay chữ: theo chiều đi, tránh chữ ngược
                    angle_deg = -math.degrees(math.atan2(dy_arr, dx_arr))
                    if angle_deg < -90 or angle_deg > 90:
                        angle_deg += 180
                    self.create_text(label_x, label_y, text=agv.id,
                                     fill="black", font=("Arial", 8, "bold"),
                                     angle=angle_deg)

                except Exception as e:
                    print(f"Error drawing AGV {agv.id}: {e}")

        # ── AGV Position Input: overlay kéo thả ────────────────────────────────
        self._draw_pos_input_agvs()

    # =========================================================
    # ZONE MANAGER DIALOG
    # =========================================================
    def open_zone_manager_dialog(self, zones_file="config/zones.json"):
        """Mở cửa sổ quản lý Zone: thêm, sửa, xóa zone — lưu vào zones.json."""
        if not self.zone_mgr:
            tk.messagebox.showerror("Zone Manager", "ZoneManager chưa được khởi tạo.")
            return

        dialog = tk.Toplevel(self)
        dialog.title("Quản lý Zone Giao thông")
        dialog.geometry("720x480")
        dialog.grab_set()

        # Ánh xạ: nhãn tiếng Việt → key nội bộ (lưu vào file)
        ZONE_TYPE_MAP = {
            "Ngã tư / Ngã ba":             "INTERSECTION",
            "Hành lang 1 chiều":           "SINGLE_LANE",
            "Tài nguyên (Trạm sạc, Cửa)":  "RESOURCE",
            "Vùng né / Bypass":            "BYPASS",
        }
        ZONE_TYPE_LABELS  = list(ZONE_TYPE_MAP.keys())
        ZONE_KEY_TO_LABEL = {v: k for k, v in ZONE_TYPE_MAP.items()}
        ZONE_TYPE_HINT = {
            "Ngã tư / Ngã ba":
                "≥2 đường giao nhau — xe đến từ nhiều hướng.\n"
                "Token=1: chỉ 1 xe trong vùng giao nhau cùng lúc.",
            "Hành lang 1 chiều":
                "Đường hẹp chỉ 1 xe qua, 2 đầu vào/ra.\n"
                "Token=1: xe tiếp theo chờ cho đến khi xe trước ra hết.",
            "Tài nguyên (Trạm sạc, Cửa)":
                "Thiết bị dùng chung: trạm sạc, cửa tự động, thang máy.\n"
                "Token = số lượng trạm/khe sạc song song.",
            "Vùng né / Bypass":
                "Pocket/ngách trên đường đơn chiều để 1 xe vào chờ.\n"
                "Token KHÔNG áp dụng — xe luôn được vào bypass.\n"
                "WHCA* tự reroute xe ưu tiên thấp vào đây khi phát hiện\n"
                "2 xe ngược chiều trên cùng tuyến đường đơn.",
        }

        # ── Layout ──────────────────────────────────────────
        frm_left  = ttk.Frame(dialog, padding=8)
        frm_left.pack(side='left', fill='both', expand=True)
        frm_right = ttk.Frame(dialog, padding=8, width=280)
        frm_right.pack(side='right', fill='y')
        frm_right.pack_propagate(False)

        # ── Left: Zone List ──────────────────────────────────
        ttk.Label(frm_left, text="Danh sách Zone", font=("Arial", 10, "bold")).pack(anchor='w')
        cols = ("id", "name", "type", "tokens", "nodes")
        tree = ttk.Treeview(frm_left, columns=cols, show='headings', height=12)
        tree.heading("id",     text="ID");     tree.column("id",     width=120)
        tree.heading("name",   text="Tên");    tree.column("name",   width=130)
        tree.heading("type",   text="Loại");   tree.column("type",   width=90)
        tree.heading("tokens", text="Token");  tree.column("tokens", width=45)
        tree.heading("nodes",  text="Nodes");  tree.column("nodes",  width=120)
        tree.pack(fill='both', expand=True)

        def refresh_tree():
            tree.delete(*tree.get_children())
            for z in self.zone_mgr.zones.values():
                tree.insert("", "end", iid=z.id, values=(
                    z.id, z.name, z.type, z.tokens,
                    ", ".join(str(n) for n in sorted(z.nodes))
                ))

        refresh_tree()

        # ── Right: Edit Form ─────────────────────────────────
        ttk.Label(frm_right, text="Thêm / Sửa Zone", font=("Arial", 10, "bold")).pack(anchor='w', pady=(0, 6))

        frm_field = ttk.Frame(frm_right)
        frm_field.pack(fill='x')

        def lbl(text): return ttk.Label(frm_field, text=text)

        lbl("Zone ID:").grid(row=0, column=0, sticky='w', pady=2)
        var_id = tk.StringVar()
        ttk.Entry(frm_field, textvariable=var_id, width=22).grid(row=0, column=1, sticky='ew', pady=2)

        lbl("Tên Zone:").grid(row=1, column=0, sticky='w', pady=2)
        var_name = tk.StringVar()
        ttk.Entry(frm_field, textvariable=var_name, width=22).grid(row=1, column=1, sticky='ew', pady=2)

        lbl("Loại:").grid(row=2, column=0, sticky='w', pady=2)
        var_type = tk.StringVar(value=ZONE_TYPE_LABELS[0])
        cb_type = ttk.Combobox(frm_field, textvariable=var_type, values=ZONE_TYPE_LABELS,
                               state="readonly", width=24)
        cb_type.grid(row=2, column=1, sticky='ew', pady=2)

        lbl("Tokens:").grid(row=3, column=0, sticky='w', pady=2)
        var_tokens = tk.IntVar(value=1)
        ttk.Spinbox(frm_field, from_=1, to=10, textvariable=var_tokens,
                    width=6).grid(row=3, column=1, sticky='w', pady=2)

        frm_field.columnconfigure(1, weight=1)

        # Mô tả loại zone + gợi ý token (cập nhật khi đổi combobox)
        lbl_hint = ttk.Label(frm_right, text=ZONE_TYPE_HINT[ZONE_TYPE_LABELS[0]],
                             foreground="#005580", font=("Arial", 8),
                             wraplength=260, justify='left')
        lbl_hint.pack(anchor='w', pady=(4, 0))

        def on_type_change(*_):
            lbl_hint.config(text=ZONE_TYPE_HINT.get(var_type.get(), ""))
        var_type.trace_add("write", on_type_change)

        # Node listbox
        ttk.Label(frm_right, text="Nodes trong Zone:", font=("Arial", 9)).pack(anchor='w', pady=(8, 2))
        lst_nodes = tk.Listbox(frm_right, height=6, selectmode='extended')
        lst_nodes.pack(fill='x')

        frm_node_btn = ttk.Frame(frm_right)
        frm_node_btn.pack(fill='x', pady=2)

        def add_node_manual():
            val = simpledialog.askinteger("Node ID", "Nhập ID node:", parent=dialog)
            if val is not None and self.tm.graph.has_node(val):
                items = list(lst_nodes.get(0, tk.END))
                if str(val) not in items:
                    lst_nodes.insert(tk.END, str(val))
            elif val is not None:
                tk.messagebox.showwarning("Không tìm thấy", f"Node {val} không có trên bản đồ.", parent=dialog)

        def del_node():
            for i in reversed(lst_nodes.curselection()):
                lst_nodes.delete(i)

        def load_from_selection():
            """Tự động điền nodes từ các thẻ đang được chọn trên bản đồ."""
            if not self.selected_nodes:
                tk.messagebox.showinfo("Gợi ý", "Chưa chọn node nào trên bản đồ.\nCtrl+Click để chọn nhiều node.", parent=dialog)
                return
            lst_nodes.delete(0, tk.END)
            for n in sorted(self.selected_nodes):
                lst_nodes.insert(tk.END, str(n))

        ttk.Button(frm_node_btn, text="+ Thêm node", command=add_node_manual).pack(side='left', padx=1)
        ttk.Button(frm_node_btn, text="- Xóa",        command=del_node).pack(side='left', padx=1)
        ttk.Button(frm_node_btn, text="📌 Từ chọn",   command=load_from_selection).pack(side='left', padx=1)

        # ── Populate form when tree row selected ──────────────
        def on_tree_select(_event):
            sel = tree.selection()
            if not sel:
                return
            z = self.zone_mgr.zones.get(sel[0])
            if not z:
                return
            var_id.set(z.id)
            var_name.set(z.name)
            var_type.set(ZONE_KEY_TO_LABEL.get(z.type, z.type))
            var_tokens.set(z.tokens)
            lst_nodes.delete(0, tk.END)
            for n in sorted(z.nodes):
                lst_nodes.insert(tk.END, str(n))

        tree.bind("<<TreeviewSelect>>", on_tree_select)

        # ── Action Buttons ────────────────────────────────────
        ttk.Separator(frm_right, orient='horizontal').pack(fill='x', pady=8)

        def save_zone():
            zid   = var_id.get().strip()
            zname = var_name.get().strip()
            if not zid or not zname:
                tk.messagebox.showwarning("Thiếu dữ liệu", "Vui lòng điền Zone ID và Tên.", parent=dialog)
                return
            raw_nodes = lst_nodes.get(0, tk.END)
            nodes = []
            for item in raw_nodes:
                try:
                    nodes.append(int(item))
                except ValueError:
                    pass
            if not nodes:
                tk.messagebox.showwarning("Thiếu nodes", "Vui lòng thêm ít nhất 1 node vào zone.", parent=dialog)
                return
            cfg = {"id": zid, "name": zname,
                   "type": ZONE_TYPE_MAP.get(var_type.get(), var_type.get()),
                   "tokens": var_tokens.get(), "nodes": nodes}
            self.zone_mgr.add_or_update_zone(cfg)
            refresh_tree()
            # Clear form
            var_id.set(""); var_name.set(""); var_tokens.set(1)
            lst_nodes.delete(0, tk.END)

        def delete_zone():
            sel = tree.selection()
            if not sel:
                return
            zid = sel[0]
            if tk.messagebox.askyesno("Xác nhận", f"Xóa zone '{zid}'?", parent=dialog):
                self.zone_mgr.delete_zone(zid)
                refresh_tree()

        def save_and_close():
            self.zone_mgr.save(zones_file)
            self.draw_map()
            dialog.destroy()

        ttk.Button(frm_right, text="💾 Lưu Zone này",  command=save_zone,     width=22).pack(fill='x', pady=2)
        ttk.Button(frm_right, text="❌ Xóa Zone chọn", command=delete_zone,   width=22).pack(fill='x', pady=2)
        ttk.Separator(frm_right, orient='horizontal').pack(fill='x', pady=6)
        ttk.Button(frm_right, text="✅ Lưu file & Đóng", command=save_and_close,
                   style="Accent.TButton" if 'Accent.TButton' in ttk.Style().theme_names() else "TButton",
                   width=22).pack(fill='x', pady=2)

        ttk.Label(frm_right, text="Tip: Ctrl+Click chọn nhiều\nnode trên bản đồ rồi\nnhấn '📌 Từ chọn'",
                  foreground="gray", font=("Arial", 8)).pack(anchor='w', pady=(10, 0))

    # =========================================================
    # MANUAL CONTROL ANIMATION
    # =========================================================
    def start_manual_move(self, agv_id, direction, speed_pwm, from_node):
        """Bắt đầu animation di chuyển thủ công khi nhận lệnh DEBA.
        direction: 'toi' | 'lui'
        speed_pwm: 0-255 (từ slider)
        from_node: node hiện tại của AGV
        Lưu WORLD coordinates — tránh lỗi khi zoom/pan sau khi animation bắt đầu.
        """
        print(f"[ANIM] start_manual_move called: agv={agv_id} dir={direction} spd={speed_pwm} from={from_node}")
        if from_node not in self.tm.graph.nodes:
            print(f"[ANIM] from_node {from_node} not in graph — animation skipped")
            return
        agv_obj = next((a for a in self.agv_list if a.id == agv_id), None)
        if agv_obj is None:
            print(f"[ANIM] agv_id {agv_id} not found in agv_list — animation skipped")
            return

        # Dùng _disp_xy() để đồng bộ với hệ tọa độ hiển thị (có thể khác x/y nếu schematic mode)
        cx, cy = self._disp_xy(from_node)

        # Xác định vector hướng di chuyển (display world space)
        prev_t = getattr(agv_obj, 'prev_tag', 0)
        if prev_t and prev_t in self.tm.graph.nodes:
            px, py = self._disp_xy(prev_t)
            heading_x, heading_y = cx - px, cy - py
        elif agv_id in self._manual_angles:
            heading_x = math.cos(self._manual_angles[agv_id])
            heading_y = math.sin(self._manual_angles[agv_id])
        else:
            # Fallback: lấy neighbor đầu tiên làm hướng
            nbs = list(self.tm.graph.neighbors(from_node))
            if nbs and nbs[0] in self.tm.graph.nodes:
                nx0, ny0 = self._disp_xy(nbs[0])
                heading_x, heading_y = nx0 - cx, ny0 - cy
            else:
                heading_x, heading_y = 1.0, 0.0

        if direction == 'lui':
            heading_x, heading_y = -heading_x, -heading_y

        _hlen = math.hypot(heading_x, heading_y)
        if _hlen > 0:
            heading_x /= _hlen
            heading_y /= _hlen

        # Chọn neighbor phù hợp nhất với hướng di chuyển — không có threshold cứng
        best_node, best_dot = None, -999.0
        # Xét cả neighbor đi và đến (graph có thể là directed)
        candidates = set(self.tm.graph.neighbors(from_node))
        if hasattr(self.tm.graph, 'predecessors'):
            candidates |= set(self.tm.graph.predecessors(from_node))
        for nb in candidates:
            if nb not in self.tm.graph.nodes:
                continue
            nx_, ny_ = self._disp_xy(nb)
            dx_, dy_ = nx_ - cx, ny_ - cy
            dist = math.hypot(dx_, dy_)
            if dist == 0:
                continue
            dot = (dx_ / dist) * heading_x + (dy_ / dist) * heading_y
            if dot > best_dot:
                best_dot, best_node = dot, nb

        if best_node is None:
            print(f"[ANIM] start_manual_move: no neighbor found for {from_node}")
            return

        nx_w, ny_w = self._disp_xy(best_node)

        # Duration: dùng display distance — tỉ lệ với khoảng cách thực qua edge weight
        geo_w_world = math.hypot(nx_w - cx, ny_w - cy) or 1
        edge_data   = (self.tm.graph.get_edge_data(from_node, best_node)
                       or self.tm.graph.get_edge_data(best_node, from_node) or {})
        real_w      = edge_data.get('weight', geo_w_world)
        # BASE_CYCLE=2s tại speed_pwm=200; scale theo real/geo ratio và speed
        duration    = 2.0 * (real_w / geo_w_world) * (200.0 / max(speed_pwm, 10))
        duration    = max(0.5, min(duration, 30.0))

        angle_rad = math.atan2(heading_y, heading_x)
        print(f"[ANIM] start_manual_move: {from_node}→{best_node} dir={direction} dur={duration:.1f}s angle={math.degrees(angle_rad):.0f}°")
        self._manual_anim[agv_id] = {
            'type':      'move',
            'from_wx':   cx,    'from_wy': cy,    # display-world coords — convert to screen tại draw time
            'to_wx':     nx_w,  'to_wy':   ny_w,
            'angle_rad': angle_rad,
            'start_t':   time.time(),
            'duration':  duration,
            'from_node': from_node,
        }

    def start_manual_turn(self, agv_id, turn_dir):
        """Bắt đầu animation quay 90° trong 7 giây.
        turn_dir: 'L' (trái) | 'R' (phải)
        Lưu WORLD coordinates cho vị trí AGV.
        """
        agv_obj = next((a for a in self.agv_list if a.id == agv_id), None)
        if agv_obj is None:
            return

        # Góc hiện tại (rad) — ưu tiên góc đã lưu sau quay trước
        if agv_id in self._manual_angles:
            from_angle = self._manual_angles[agv_id]
        else:
            ct = agv_obj.current_tag
            pt = getattr(agv_obj, 'prev_tag', 0)
            from_angle = 0.0
            if ct in self.tm.graph.nodes and pt in self.tm.graph.nodes:
                cx_, cy_ = self._disp_xy(ct)
                px_, py_ = self._disp_xy(pt)
                from_angle = math.atan2(cy_ - py_, cx_ - px_)

        to_angle = from_angle + (math.pi / 2 if turn_dir == 'R' else -math.pi / 2)

        # Vị trí display-world của AGV
        ct = agv_obj.current_tag
        if ct in self.tm.graph.nodes:
            wx, wy = self._disp_xy(ct)
        else:
            wx, wy = 0.0, 0.0

        self._manual_anim[agv_id] = {
            'type':       'turn',
            'from_angle': from_angle,
            'to_angle':   to_angle,
            'start_t':    time.time(),
            'duration':   5.5,   # 5.5 giây cho 90°
            'wx':         wx,    # WORLD coords
            'wy':         wy,
        }

    def start_auto_rotation(self, agv_id, at_tag, next_tag, duration=7.0):
        """Animation quay cho auto-navigation (90°=7s, 180°=14s).
        Chạy đến hết duration hoặc khi AGV rời at_tag (tag thay đổi).
        at_tag: thẻ AGV đang đứng khi quay.
        next_tag: thẻ tiếp theo AGV sẽ đến sau khi quay xong (xác định hướng đích).
        """
        agv_obj = next((a for a in self.agv_list if a.id == agv_id), None)
        if agv_obj is None:
            return

        # Khi xe chạy lùi (return_reversing_charge hoặc DIR_BWD trong plan),
        # đầu xe hướng NGƯỢC chiều di chuyển.
        # Cần flip góc bắt đầu và góc đích để animation thể hiện đúng hướng ĐẦU xe.
        is_bwd = (getattr(agv_obj, 'current_task_type', '') == 'return_reversing_charge'
                  or getattr(agv_obj, '_current_dir', 7) == 8)  # 8 = ACT_DIR_BWD

        # Góc ban đầu: hướng ĐẦU xe trước khi quay
        prev_t = getattr(agv_obj, 'prev_tag', 0)
        ct     = at_tag
        if agv_id in self._manual_angles:
            # _manual_angles luôn lưu hướng ĐẦU xe — không cần flip thêm
            from_angle = self._manual_angles[agv_id]
        elif prev_t and prev_t in self.tm.graph.nodes and ct in self.tm.graph.nodes:
            px, py = self._disp_xy(prev_t)
            cx, cy = self._disp_xy(ct)
            from_angle = math.atan2(cy - py, cx - px)
            if is_bwd:
                from_angle += math.pi  # chiều di chuyển → hướng đầu xe (ngược nhau khi lùi)
        else:
            from_angle = 0.0

        # Góc đích: hướng ĐẦU xe sau khi quay xong
        if next_tag and next_tag in self.tm.graph.nodes and ct in self.tm.graph.nodes:
            cx, cy = self._disp_xy(ct)
            nx, ny = self._disp_xy(next_tag)
            to_angle = math.atan2(ny - cy, nx - cx)
            if is_bwd:
                to_angle += math.pi  # khi lùi: đầu xe hướng ngược chiều sẽ di chuyển
        else:
            to_angle = from_angle + math.pi  # fallback: 180°

        # Chuẩn hóa → quay theo đường ngắn nhất
        diff = to_angle - from_angle
        while diff >  math.pi: diff -= 2 * math.pi
        while diff < -math.pi: diff += 2 * math.pi
        to_angle = from_angle + diff

        # Vị trí AGV (giữ nguyên tại at_tag trong suốt animation)
        wx, wy = self._disp_xy(ct) if ct in self.tm.graph.nodes else (0.0, 0.0)

        self._manual_anim[agv_id] = {
            'type':          'turn',
            'from_angle':    from_angle,
            'to_angle':      to_angle,
            'start_t':       time.time(),
            'duration':      duration,
            'wx':            wx,
            'wy':            wy,
            'auto_rotation': True,   # dừng sớm khi tag thay đổi
            'at_tag':        at_tag,
        }
        print(f"[ANIM] auto_rotation: {agv_id} @ tag {at_tag} "
              f"{math.degrees(from_angle):.0f}°→{math.degrees(to_angle):.0f}° dur={duration:.1f}s")

    def stop_manual_anim(self, agv_id):
        """Dừng animation thủ công — gọi khi có MQTT update thẻ mới hoặc lệnh stop."""
        self._manual_anim.pop(agv_id, None)

    # =========================================================
    # AGV POSITION INPUT
    # =========================================================
    def open_position_input(self):
        """Kích hoạt chế độ Nhập vị trí AGV — AGV hiện ra, có thể kéo và xoay."""
        self._pos_input_active = True
        # Khởi tạo vị trí ban đầu cho từng AGV từ current_tag
        self._pos_input_agvs.clear()
        for agv in self.agv_list:
            if agv.current_tag > 0 and self.tm.graph.has_node(agv.current_tag):
                node_data = self.tm.graph.nodes[agv.current_tag]
                angle = self._angle_from_prev(agv.current_tag, agv.prev_tag)
                self._pos_input_agvs[agv.id] = {
                    'wx': node_data['x'], 'wy': node_data['y'],
                    'angle': angle, 'node': agv.current_tag, 'prev_node': agv.prev_tag,
                    'color': getattr(agv, 'color', '#3498db'),
                }
            else:
                # AGV chưa có vị trí → đặt ở vùng trắng bên trái canvas
                idx = list(a.id for a in self.agv_list).index(agv.id)
                self._pos_input_agvs[agv.id] = {
                    'wx': -60.0, 'wy': 20.0 + idx * 40,
                    'angle': 0.0, 'node': None, 'prev_node': None,
                    'color': getattr(agv, 'color', '#3498db'),
                }
        self.draw_map()

    def close_position_input(self):
        self._pos_input_active = False
        self._dragging_agv_pos = None
        self._pos_input_agvs.clear()   # Xóa stale data — tránh ghost icons
        self.draw_map()

    def _angle_from_prev(self, curr_tag, prev_tag):
        """Tính góc (độ) của vector hướng prev→curr. 0=phải, 90=xuống."""
        if not prev_tag or not self.tm.graph.has_node(prev_tag) or not self.tm.graph.has_node(curr_tag):
            return 0.0
        pc = self.tm.graph.nodes[curr_tag]
        pp = self.tm.graph.nodes[prev_tag]
        return math.degrees(math.atan2(pc['y'] - pp['y'], pc['x'] - pp['x']))

    def _compute_prev_from_angle(self, node_id, angle_deg):
        """
        Từ node_id + heading angle → tìm prev_node phù hợp nhất (node phía sau xe).

        Xét TẤT CẢ láng giềng (predecessors + successors) vì prev_tag là node nằm phía
        sau theo hướng vật lý — không bắt buộc là predecessor trong đồ thị có hướng.
        Ví dụ: node 101 heading trái (về phía 71): 71 là successor (101→71) nhưng
        lại là node phía SAU xe → đây là prev_node đúng.
        """
        if not self.tm.graph.has_node(node_id):
            return None
        hx = math.cos(math.radians(angle_deg))
        hy = math.sin(math.radians(angle_deg))
        best_prev, best_score = None, -2.0
        c = self.tm.graph.nodes[node_id]
        # Xét cả predecessors lẫn successors (bất kể chiều edge)
        seen = set()
        for nb in list(self.tm.graph.predecessors(node_id)) + list(self.tm.graph.successors(node_id)):
            if nb in seen:
                continue
            seen.add(nb)
            p = self.tm.graph.nodes[nb]
            dx, dy = p['x'] - c['x'], p['y'] - c['y']
            dist = math.hypot(dx, dy)
            if dist < 1e-6:
                continue
            # Score: láng giềng phía SAU xe (ngược hướng heading) → score cao nhất
            score = -(hx * dx / dist + hy * dy / dist)
            if score > best_score:
                best_score, best_prev = score, nb
        # Chỉ trả về node nếu nó thực sự nằm phía SAU xe (score > 0).
        # score = 0 nghĩa là vuông góc; score < 0 nghĩa là phía trước → trả None.
        return best_prev if best_score > 0 else None

    def _get_agv_pos_at_screen(self, sx, sy):
        """Trả về agv_id nếu click trong vùng AGV icon (position_input mode)."""
        if not self._pos_input_active:
            return None
        for agv_id, pos in self._pos_input_agvs.items():
            asx, asy = self.to_screen(pos['wx'], pos['wy'])
            if abs(sx - asx) < 18 and abs(sy - asy) < 14:
                return agv_id
        return None

    def _snap_agv_to_nearest(self, agv_id, wx, wy):
        """Snap AGV đến node gần nhất (trong 30px screen), cập nhật angle."""
        pos = self._pos_input_agvs[agv_id]
        best_node, best_dist = None, float('inf')
        for nid, attrs in self.tm.graph.nodes(data=True):
            nx_, ny_ = attrs.get('x', 0), attrs.get('y', 0)
            # Khoảng cách screen
            asx, asy = self.to_screen(wx, wy)
            nsx, nsy = self.to_screen(nx_, ny_)
            d = math.hypot(asx - nsx, asy - nsy)
            if d < best_dist:
                best_dist, best_node = d, nid
        if best_node is not None and best_dist < 30:
            ndata = self.tm.graph.nodes[best_node]
            pos['wx'], pos['wy'] = ndata['x'], ndata['y']
            pos['node'] = best_node
            pos['prev_node'] = self._compute_prev_from_angle(best_node, pos['angle'])
        else:
            pos['wx'], pos['wy'] = wx, wy
            pos['node'] = None
            pos['prev_node'] = None

    def _rotate_agv(self, agv_id, direction=1):
        """Xoay AGV 90° (direction=+1 CW, -1 CCW). Cập nhật prev_node sau khi xoay."""
        if agv_id not in self._pos_input_agvs:
            return
        pos = self._pos_input_agvs[agv_id]
        pos['angle'] = (pos['angle'] + direction * 90) % 360
        if pos['node']:
            pos['prev_node'] = self._compute_prev_from_angle(pos['node'], pos['angle'])
        self.draw_map()

    def apply_agv_positions(self):
        """Gọi callback để áp dụng vị trí đã đặt lên server-side AGV objects."""
        if not self.on_apply_positions:
            return
        result = {}
        for agv_id, pos in self._pos_input_agvs.items():
            if pos['node'] is not None:
                result[agv_id] = (pos['node'], pos['prev_node'])
        if result:
            self.on_apply_positions(result)
        self.close_position_input()

    def _draw_pos_input_agvs(self):
        """Vẽ AGV icons ở vị trí manual trong position_input mode."""
        if not self._pos_input_active:
            return
        for agv_id, pos in self._pos_input_agvs.items():
            sx, sy   = self.to_screen(pos['wx'], pos['wy'])
            angle    = pos['angle']
            color    = pos.get('color', '#3498db')
            dx = math.cos(math.radians(angle))
            dy = math.sin(math.radians(angle))
            HL, HW   = 15, 9
            px_, py_ = -dy, dx   # perp vector
            corners  = [
                sx + dx*HL + px_*HW, sy + dy*HL + py_*HW,
                sx + dx*HL - px_*HW, sy + dy*HL - py_*HW,
                sx - dx*HL - px_*HW, sy - dy*HL - py_*HW,
                sx - dx*HL + px_*HW, sy - dy*HL + py_*HW,
            ]
            is_drag  = (self._dragging_agv_pos == agv_id)
            outline  = "red" if is_drag else "black"
            self.create_polygon(corners, fill=color, outline=outline, width=2)
            self.create_line(sx, sy, sx+dx*(HL-2), sy+dy*(HL-2),
                             fill="white", width=2, arrow=tk.LAST, arrowshape=(7,9,3))
            self.create_text(sx, sy+HL+8, text=agv_id,
                             fill=color, font=("Arial", 7, "bold"))
            # Hiển thị node đang snap đến
            if pos['node']:
                self.create_text(sx, sy-HL-6, text=f"→thẻ {pos['node']}",
                                 fill="gray", font=("Arial", 7))

    def set_tool(self, tool_name):
        self.tool = tool_name
        self.selected_edge = None
        self.selected_node = None
        self.selected_nodes.clear()
        self.draw_map()
        print(f"Tool selected: {tool_name}")

    # =========================================================
    # UNDO / REDO / DELETE
    # =========================================================

    def _make_snapshot(self):
        """Tạo bản chụp trạng thái bản đồ hiện tại (deep copy)"""
        return {
            "nodes": {nid: copy.deepcopy(dict(data))
                      for nid, data in self.tm.graph.nodes(data=True)},
            "edges": [(u, v, copy.deepcopy(dict(data)))
                      for u, v, data in self.tm.graph.edges(data=True)]
        }

    def _push_history(self):
        """Lưu snapshot hiện tại vào stack Undo. Xóa Redo stack."""
        snap = self._make_snapshot()
        self._history.append(snap)
        if len(self._history) > self._MAX_HISTORY:
            self._history.pop(0)
        self._redo_stack.clear()

    def _apply_snapshot(self, snapshot):
        """Khôi phục bản đồ từ snapshot"""
        self.tm.graph.clear()
        for nid, data in snapshot["nodes"].items():
            self.tm.graph.add_node(nid, **copy.deepcopy(data))
        for u, v, data in snapshot["edges"]:
            self.tm.graph.add_edge(u, v, **copy.deepcopy(data))
        self.selected_node = None
        self.selected_nodes.clear()
        self.selected_edge = None

    def undo(self):
        """Hoàn tác thao tác gần nhất (Ctrl+Z)"""
        if not self._history:
            return
        # Lưu trạng thái hiện tại vào redo stack
        self._redo_stack.append(self._make_snapshot())
        # Khôi phục trạng thái trước
        self._apply_snapshot(self._history.pop())
        self.draw_map()
        print(f"Undo — history left: {len(self._history)}")

    def redo(self):
        """Làm lại thao tác đã undo (Ctrl+Y)"""
        if not self._redo_stack:
            return
        # Lưu trạng thái hiện tại vào history
        self._history.append(self._make_snapshot())
        # Khôi phục trạng thái sau
        self._apply_snapshot(self._redo_stack.pop())
        self.draw_map()
        print(f"Redo — redo left: {len(self._redo_stack)}")

    def delete_selected(self):
        """Xóa node hoặc edge đang được chọn (phím Del hoặc nút Xóa)"""
        if self.selected_nodes:
            self._push_history()
            for n in list(self.selected_nodes):
                if n in self.tm.graph.nodes:
                    self.tm.graph.remove_node(n)
            self.selected_nodes.clear()
            self.selected_node = None
            self.draw_map()
        elif self.selected_edge is not None:
            self._push_history()
            u, v = self.selected_edge
            self.selected_edge = None
            if self.tm.graph.has_edge(u, v):
                self.tm.graph.remove_edge(u, v)
                print(f"Deleted edge: {u} -> {v}")
            self.draw_map()

    def align_horizontal(self):
        """Căn ngang: đặt tất cả node đã chọn về cùng tọa độ Y hiển thị (trung bình)"""
        nodes = [n for n in self.selected_nodes if n in self.tm.graph.nodes]
        if len(nodes) < 2:
            return
        self._push_history()
        avg_y = sum(self._disp_xy(n)[1] for n in nodes) / len(nodes)
        for n in nodes:
            self.tm.graph.nodes[n]['disp_y'] = avg_y
        self.draw_map()

    def align_vertical(self):
        """Căn dọc: đặt tất cả node đã chọn về cùng tọa độ X hiển thị (trung bình)"""
        nodes = [n for n in self.selected_nodes if n in self.tm.graph.nodes]
        if len(nodes) < 2:
            return
        self._push_history()
        avg_x = sum(self._disp_xy(n)[0] for n in nodes) / len(nodes)
        for n in nodes:
            self.tm.graph.nodes[n]['disp_x'] = avg_x
        self.draw_map()