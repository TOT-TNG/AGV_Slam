"""
Multi-AGV Visual Simulator
──────────────────────────
Cách dùng:
  1. Nhấn [+ Thêm] để thêm AGV ảo vào danh sách
  2. Chọn AGV trong danh sách, cấu hình:
       - Thẻ bắt đầu: nhập số hoặc nhấn [📍 Pick] rồi click thẻ trên bản đồ
       - Hướng đầu xe: chọn từ dropdown (hướng đầu xe đang nhìn lúc bắt đầu)
       - Thẻ đích: nhập số hoặc nhấn [🏁 Pick] rồi click thẻ trên bản đồ
       - Loại nhiệm vụ: delivery / return_charge / …
       - Nhấn [✔ Áp dụng] để lưu cấu hình
  3. Nhấn [▶ Khởi tạo] để tính toán đường đi cho tất cả AGV
  4. Nhấn [⟶ Bước tất cả] để tiến 1 bước (tất cả AGV di chuyển đồng thời)
     Hoặc chọn AGV rồi nhấn [⟶ Bước AGV này] để chỉ tiến 1 bước AGV đó
  5. Nhấn [▶ Tự động] để chạy tự động với khoảng cách thời gian tuỳ chọn

Xung đột:
  • Node conflict: 2 xe muốn đến cùng 1 thẻ → xe ưu tiên thấp chờ
  • Head-on tức thì: A→B và B→A cùng lúc → xe ưu tiên thấp tính lại đường
  • Lookahead (SIPP-like): phát hiện đối đầu trước N bước
      - Thử đường vòng: nếu chi phí ≤ (1 + ngưỡng%) → đi ngay
      - Không có / quá dài → kế hoạch dừng tại thẻ an toàn trước hành lang
        (xe vẫn tiếp tục đến đó rồi mới dừng chờ, không dừng sớm)
  • Thứ tự ưu tiên: return_charge > delivery > return_charge_empty > return_empty
"""

import tkinter as tk
from tkinter import ttk
import math
import json
import os
from collections import defaultdict


# ─── SimZoneTracker ─────────────────────────────────────────────────────────
class _SimZoneTracker:
    """
    Lightweight zone reservation cho mô phỏng (không dùng async queue).

    Quy tắc:
      • Mỗi zone có `tokens` = số AGV được vào đồng thời (mặc định 1).
      • Khi AGV vào bất kỳ node nào của zone → giữ token.
      • Khi AGV rời TOÀN BỘ node của zone → trả token.
      • AGV khác muốn vào cùng zone khi đã đủ tokens → BỊ BLOCK.

    Đọc config từ cùng file zones.json của ZoneManager thực.
    """

    def __init__(self, config_path: str = "config/zones.json"):
        self._zones: dict[str, dict] = {}          # id → {nodes, tokens, holders}
        self._node_to_zones: dict[int, list] = defaultdict(list)
        self._passing_bays: dict[str, dict] = {}   # id → {branch_node, siding_nodes, main_corridor}
        self._load(config_path)

    def _load(self, path: str):
        if not os.path.exists(path):
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            items = data if isinstance(data, list) else data.get("zones", [])
            for cfg in items:
                zid       = cfg.get("id") or cfg.get("name", "")
                zone_type = cfg.get("type", "").upper()
                nodes     = set(int(n) for n in cfg.get("nodes", []))

                if zone_type == "PASSING_BAY":
                    # Vùng tránh (Passing Bay / Siding) — không dùng token thông thường
                    self._passing_bays[zid] = {
                        "branch_node":   int(cfg["branch_node"]),
                        "siding_nodes":  [int(n) for n in cfg.get("siding_nodes", [])],
                        "main_corridor": [int(n) for n in cfg.get("nodes", [])],
                    }
                else:
                    tokens = int(cfg.get("tokens", 1))
                    self._zones[zid] = {"nodes": nodes, "tokens": tokens, "holders": set()}
                    for n in nodes:
                        self._node_to_zones[n].append(zid)
            print(f"[SimZone] Loaded {len(self._zones)} zone(s), "
                  f"{len(self._passing_bays)} passing bay(s) from {path}")
        except Exception as e:
            print(f"[SimZone] Cannot load {path}: {e}")

    def reset(self):
        """Giải phóng tất cả tokens — gọi khi reset / init simulation."""
        for z in self._zones.values():
            z["holders"].clear()

    def zone_ids_for(self, node: int) -> list[str]:
        return self._node_to_zones.get(node, [])

    def can_enter(self, agv_id: str, node: int) -> tuple[bool, str]:
        """Kiểm tra AGV có thể vào node không. (bool, lý do nếu False)."""
        for zid in self._node_to_zones.get(node, []):
            z = self._zones[zid]
            if agv_id in z["holders"]:
                continue                           # đã giữ token → OK
            if len(z["holders"]) >= z["tokens"]:
                blocker = ", ".join(sorted(z["holders"]))
                return False, f"zone '{zid}' [{len(z['holders'])}/{z['tokens']} slot] bị {blocker} giữ"
        return True, ""

    def on_agv_moved(self, agv_id: str, new_node: int):
        """
        Gọi sau khi AGV di chuyển đến new_node.
        Cấp token zone mới; giải phóng zone nếu AGV đã hoàn toàn rời.
        """
        for zid, z in self._zones.items():
            in_zone = new_node in z["nodes"]
            if in_zone:
                z["holders"].add(agv_id)
            else:
                z["holders"].discard(agv_id)   # rời zone → trả token

    def release_all(self, agv_id: str):
        """Giải phóng tất cả token của AGV (gọi khi done/error)."""
        for z in self._zones.values():
            z["holders"].discard(agv_id)

    @property
    def loaded(self) -> bool:
        return bool(self._zones)


TASK_PRIORITY = {
    "return_charge":       0,
    "delivery":            1,
    "return_charge_empty": 2,
    "return_empty":        3,
}

AGV_COLORS = [
    "#e74c3c", "#3498db", "#2ecc71", "#f39c12",
    "#9b59b6", "#1abc9c", "#e67e22", "#34495e",
]

TASK_LABELS = [
    "delivery",
    "return_charge",
    "return_charge_empty",
    "return_empty",
]

# Màu đường gốc (nhạt hơn màu AGV, hiển thị toàn bộ hành trình)
def _faded(hex_color: str, alpha: float = 0.35) -> str:
    """Pha màu hex với nền trắng theo alpha."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    r2 = int(r * alpha + 255 * (1 - alpha))
    g2 = int(g * alpha + 255 * (1 - alpha))
    b2 = int(b * alpha + 255 * (1 - alpha))
    return f"#{r2:02x}{g2:02x}{b2:02x}"


# ─────────────────────────── Virtual AGV ──────────────────────────────────────

class VirtualAGV:
    _counter = 0

    def __init__(self, agv_id=None, color=None):
        VirtualAGV._counter += 1
        self.id    = agv_id or f"AGV{VirtualAGV._counter:02d}"
        self.color = color  or AGV_COLORS[(VirtualAGV._counter - 1) % len(AGV_COLORS)]

        self.start_tag:    int | None = None
        self.facing_tag:   int | None = None
        self.end_tag:      int | None = None
        self.task_type:    str        = "delivery"

        # Simulation state
        self.path:         list[int]  = []   # đường hiện tại (có thể đã reroute)
        self.original_path: list[int] = []   # đường ban đầu khi khởi tạo
        self.current_idx:  int        = 0
        self.status:       str        = "idle"
        self.wait_reason:  str        = ""
        self.steps_data:   list[dict] = []
        self.planned_hold_at: int | None = None  # thẻ dừng trước xung đột (SIPP-like)
        self.bypassing:       bool       = False  # đang đi theo đường vùng tránh (Passing Bay)
        self.bypass_exit_idx: int        = -1     # current_idx khi hoàn thành đường vòng siding

    @property
    def current_tag(self) -> int | None:
        if self.path and 0 <= self.current_idx < len(self.path):
            return self.path[self.current_idx]
        return self.start_tag

    @property
    def prev_tag(self) -> int | None:
        if self.current_idx > 0 and self.path:
            return self.path[self.current_idx - 1]
        return None

    @property
    def next_tag(self) -> int | None:
        if self.path and self.current_idx + 1 < len(self.path):
            return self.path[self.current_idx + 1]
        return None

    @property
    def priority(self) -> int:
        return TASK_PRIORITY.get(self.task_type, 9)


# ─────────────────────────── Panel ────────────────────────────────────────────

class MultiSimPanel(tk.Toplevel):

    def __init__(self, parent, traffic_manager, sim_engine):
        super().__init__(parent)
        self.tm  = traffic_manager
        self.sim = sim_engine
        self._sim_zones = _SimZoneTracker("config/zones.json")

        self.title("🗺  Mô phỏng Đa AGV")
        self.geometry("1420x860")
        self.resizable(True, True)
        self.minsize(900, 600)

        self.agv_list:    list[VirtualAGV] = []
        self._is_running  = False
        self._run_job     = None
        self._step_count  = 0
        self._pick_mode:  str | None = None
        self._facing_map: dict[str, int | None] = {}

        self._build_ui()
        self.after(300, self._auto_fit_map)

    # ══════════════════════════════ UI BUILD ══════════════════════════════════

    def _build_ui(self):
        paned = tk.PanedWindow(self, orient=tk.HORIZONTAL, sashwidth=5, bg="#ccc")
        paned.pack(fill="both", expand=True)

        # ── LEFT ──────────────────────────────────────────────────────────────
        left = tk.Frame(paned, width=330, bg="#f4f4f4")
        paned.add(left, minsize=300)

        tk.Label(left, text="🗺  Mô phỏng Đa AGV",
                 font=("Segoe UI", 11, "bold"), bg="#f4f4f4").pack(pady=(8, 2))

        # ── AGV list ──
        lf_list = tk.LabelFrame(left, text="Danh sách AGV", padx=4, pady=4, bg="#f4f4f4")
        lf_list.pack(fill="x", padx=8, pady=4)

        cols = ("id", "clr", "start", "end", "status")
        self.tv = ttk.Treeview(lf_list, columns=cols, show="headings",
                               height=6, selectmode="browse")
        for c, w, lbl in [("id",5,"ID"),("clr",3,"●"),("start",5,"Từ"),
                           ("end",5,"Đến"),("status",8,"Trạng thái")]:
            self.tv.heading(c, text=lbl)
            self.tv.column(c, width=w*13, anchor="center")
        self.tv.pack(fill="x")
        self.tv.bind("<<TreeviewSelect>>", self._on_agv_select)

        btn_row = tk.Frame(lf_list, bg="#f4f4f4")
        btn_row.pack(fill="x", pady=(4, 0))
        tk.Button(btn_row, text="+ Thêm",  command=self._add_agv,    width=9).pack(side="left", padx=2)
        tk.Button(btn_row, text="− Xóa",   command=self._remove_agv, width=9).pack(side="left", padx=2)
        tk.Button(btn_row, text="Xóa tất", command=self._clear_all,  width=9).pack(side="left", padx=2)

        # ── AGV config ──
        lf_cfg = tk.LabelFrame(left, text="Cấu hình AGV đang chọn", padx=4, pady=4, bg="#f4f4f4")
        lf_cfg.pack(fill="x", padx=8, pady=4)

        self._var_start  = tk.StringVar()
        self._var_facing = tk.StringVar()
        self._var_end    = tk.StringVar()
        self._var_task   = tk.StringVar(value="delivery")

        def _row(lbl, var, choices=None):
            r = tk.Frame(lf_cfg, bg="#f4f4f4")
            r.pack(fill="x", pady=1)
            tk.Label(r, text=lbl, width=13, anchor="w", bg="#f4f4f4").pack(side="left")
            if choices is not None:
                w = ttk.Combobox(r, textvariable=var, values=choices,
                                 state="readonly", width=17)
            else:
                w = tk.Entry(r, textvariable=var, width=10)
            w.pack(side="left", fill="x", expand=True)
            return w

        _row("Thẻ bắt đầu:", self._var_start)
        self._cb_facing = _row("Hướng đầu xe:", self._var_facing,
                               choices=["— chọn thẻ BĐ trước —"])
        _row("Thẻ đích:",    self._var_end)
        _row("Nhiệm vụ:",    self._var_task, choices=TASK_LABELS)
        self._var_start.trace_add("write", self._refresh_facing)

        # Pick buttons + hướng dẫn
        tk.Label(lf_cfg,
                 text="💡 Pick: nhấn nút bên dưới rồi click thẻ bất kỳ trên BẢN ĐỒ bên phải",
                 fg="#555", font=("Segoe UI", 7), wraplength=290, justify="left",
                 bg="#f4f4f4").pack(anchor="w", pady=(4, 1))

        pick_row = tk.Frame(lf_cfg, bg="#f4f4f4")
        pick_row.pack(fill="x")
        tk.Button(pick_row, text="📍 Pick bắt đầu",
                  command=lambda: self._enter_pick("start"), width=14).pack(side="left", padx=2)
        tk.Button(pick_row, text="🏁 Pick đích",
                  command=lambda: self._enter_pick("end"),   width=14).pack(side="left", padx=2)

        self._lbl_pick_hint = tk.Label(lf_cfg, text="",
                                       fg="#e74c3c", font=("Segoe UI", 8, "bold"),
                                       bg="#f4f4f4")
        self._lbl_pick_hint.pack()

        tk.Button(lf_cfg, text="✔ Áp dụng cấu hình", command=self._apply_config,
                  bg="#27ae60", fg="white").pack(fill="x", pady=(4, 0))

        # ── Simulation controls ──
        lf_ctrl = tk.LabelFrame(left, text="Điều khiển mô phỏng", padx=4, pady=4, bg="#f4f4f4")
        lf_ctrl.pack(fill="x", padx=8, pady=4)

        tk.Button(lf_ctrl, text="▶ Khởi tạo đường đi (tất cả AGV)",
                  command=self._init_simulation,
                  bg="#2980b9", fg="white").pack(fill="x", pady=2)

        # Bước tiếp — 2 nút: tất cả và riêng lẻ
        step_row = tk.Frame(lf_ctrl, bg="#f4f4f4")
        step_row.pack(fill="x", pady=2)
        tk.Button(step_row, text="⟶ Bước tất cả",
                  command=self._step, width=14).pack(side="left", padx=2)
        tk.Button(step_row, text="⟶ Bước AGV này",
                  command=self._step_selected, width=14).pack(side="left", padx=2)
        tk.Button(step_row, text="↩ Hoàn tác",
                  command=self._undo_selected, width=10).pack(side="left", padx=2)

        auto_row = tk.Frame(lf_ctrl, bg="#f4f4f4")
        auto_row.pack(fill="x", pady=2)
        self._btn_run = tk.Button(auto_row, text="▶ Tự động",
                                  command=self._toggle_run, width=14)
        self._btn_run.pack(side="left", padx=2)

        spd_row = tk.Frame(lf_ctrl, bg="#f4f4f4")
        spd_row.pack(fill="x", pady=2)
        tk.Label(spd_row, text="ms/bước:", bg="#f4f4f4").pack(side="left")
        self._var_speed = tk.IntVar(value=700)
        ttk.Spinbox(spd_row, from_=100, to=5000, increment=100,
                    textvariable=self._var_speed, width=7).pack(side="left", padx=4)

        la_row = tk.Frame(lf_ctrl, bg="#f4f4f4")
        la_row.pack(fill="x", pady=2)
        tk.Label(la_row, text="Nhìn trước (bước):", bg="#f4f4f4").pack(side="left")
        self._var_lookahead = tk.IntVar(value=2)
        ttk.Spinbox(la_row, from_=0, to=10, increment=1,
                    textvariable=self._var_lookahead, width=4).pack(side="left", padx=4)
        tk.Label(la_row, text="(0=tắt)", fg="#888", font=("Segoe UI", 7),
                 bg="#f4f4f4").pack(side="left")

        dt_row = tk.Frame(lf_ctrl, bg="#f4f4f4")
        dt_row.pack(fill="x", pady=2)
        tk.Label(dt_row, text="Ngưỡng đường vòng:", bg="#f4f4f4").pack(side="left")
        self._var_detour_threshold = tk.IntVar(value=30)
        ttk.Spinbox(dt_row, from_=0, to=300, increment=10,
                    textvariable=self._var_detour_threshold, width=5).pack(side="left", padx=4)
        tk.Label(dt_row, text="% dài hơn tối đa", fg="#888", font=("Segoe UI", 7),
                 bg="#f4f4f4").pack(side="left")

        tk.Button(lf_ctrl, text="↺ Reset mô phỏng", command=self._reset_sim,
                  bg="#c0392b", fg="white").pack(fill="x", pady=2)

        self._lbl_step = tk.Label(lf_ctrl, text="Bước: 0  |  Còn: 0",
                                  font=("Segoe UI", 9, "bold"), bg="#f4f4f4")
        self._lbl_step.pack()

        # ── Chú thích màu đường ──
        lf_legend = tk.LabelFrame(left, text="Chú thích", padx=4, pady=4, bg="#f4f4f4")
        lf_legend.pack(fill="x", padx=8, pady=(0, 4))
        tk.Label(lf_legend,
                 text="━━━  Đường ban đầu (nhạt)\n"
                      "╌╌╌  Đường còn lại (đậm)\n"
                      "- - -  Đường tính lại (tím)\n"
                      "⏳ #N  Dự kiến dừng trước xung đột",
                 justify="left", font=("Courier New", 8), bg="#f4f4f4").pack(anchor="w")

        # ── Log ──
        lf_log = tk.LabelFrame(left, text="Nhật ký", padx=4, pady=4, bg="#f4f4f4")
        lf_log.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self._txt_log = tk.Text(lf_log, bg="#0d1117", fg="#e6edf3",
                                font=("Courier New", 8), state="disabled",
                                wrap="word", relief="flat")
        sb_log = ttk.Scrollbar(lf_log, command=self._txt_log.yview)
        self._txt_log.configure(yscrollcommand=sb_log.set)
        sb_log.pack(side="right", fill="y")
        self._txt_log.pack(fill="both", expand=True)

        for t, c in [("conflict","#ff6b6b"), ("wait","#ffa94d"), ("move","#69db7c"),
                     ("reroute","#da77f2"),  ("done","#74c0fc"), ("info","#868e96"),
                     ("action", "#63e6be"),  ("head","#ffd43b")]:
            self._txt_log.tag_config(t, foreground=c)

        # ── RIGHT: Map ──
        right = tk.Frame(paned, bg="white")
        paned.add(right, minsize=650)

        from gui.map_widget import MapWidget
        self._map = MapWidget(right, self.tm, agv_list=[])
        self._map.tool = "monitor"
        self._map.pack(fill="both", expand=True)
        self._map.bind("<Button-1>", self._on_map_click)

        # Hook draw_map: mỗi lần MapWidget redraw (kể cả animate loop 100ms),
        # tự động vẽ lại AGV overlays lên trên — tránh AGV biến mất.
        _orig_draw = self._map.draw_map
        _panel = self
        def _hooked_draw():
            _orig_draw()
            _panel._draw_virtual_agvs()
        self._map.draw_map = _hooked_draw

    # ════════════════════════════ Map rendering ════════════════════════════════

    def _auto_fit_map(self):
        g = self.tm.graph
        if not g.nodes:
            self._map.draw_map()
            return
        xs = [g.nodes[n].get("x", 0) for n in g.nodes]
        ys = [g.nodes[n].get("y", 0) for n in g.nodes]
        w  = self._map.winfo_width()  or 900
        h  = self._map.winfo_height() or 700
        pad = 70
        sc = min((w - 2*pad) / (max(xs) - min(xs) + 1e-6),
                 (h - 2*pad) / (max(ys) - min(ys) + 1e-6),
                 3.0)
        self._map.scale    = sc
        self._map.offset_x = pad - min(xs) * sc
        self._map.offset_y = pad - min(ys) * sc
        self._full_redraw()

    def _full_redraw(self):
        """Vẽ lại toàn bộ bản đồ. AGV overlay tự động được vẽ theo hook."""
        self._map.draw_map()

    def _fast_redraw(self):
        """Chỉ update AGV overlay — không redraw bản đồ → không nhấp nháy."""
        self._map.delete("vsim")
        self._draw_virtual_agvs()

    def _redraw_map(self):
        self._full_redraw()

    def _draw_virtual_agvs(self):
        """Vẽ marker + đường đi của tất cả AGV ảo lên canvas (style giống tab giám sát)."""
        g  = self.tm.graph
        mw = self._map

        for agv in self.agv_list:
            tag = agv.current_tag
            if not tag or not g.has_node(tag):
                continue

            # Dùng disp_xy để khớp với vị trí hiển thị (tránh lệch hướng khi node đã kéo thả)
            def _dxy(n): nd = g.nodes.get(n, {}); return (nd.get('disp_x', nd.get('x', 0)), nd.get('disp_y', nd.get('y', 0)))
            x, y  = _dxy(tag)
            sx, sy = mw.to_screen(x, y)

            # ── Heading vector ──
            hx, hy = 1.0, 0.0
            ref = agv.next_tag or agv.prev_tag or agv.facing_tag
            if ref and g.has_node(ref):
                rx_r, ry_r = _dxy(ref)
                rx = rx_r - x
                ry = ry_r - y
                mag = math.sqrt(rx**2 + ry**2)
                if mag > 1e-6:
                    hx, hy = rx / mag, ry / mag
            # Chuẩn hóa
            mag = math.sqrt(hx**2 + hy**2)
            if mag > 1e-6:
                hx, hy = hx/mag, hy/mag

            # ── Đường gốc (nhạt, nét liền) — toàn bộ hành trình ban đầu ──
            if agv.original_path and len(agv.original_path) > 1:
                faded = _faded(agv.color, 0.38)
                coords = []
                for pt in agv.original_path:
                    if g.has_node(pt):
                        wx2, wy2 = _dxy(pt)
                        px2, py2 = mw.to_screen(wx2, wy2)
                        coords.extend([px2, py2])
                if len(coords) >= 4:
                    mw.create_line(coords, fill=faded, width=3, tags="vsim")

            # ── Đoạn đã đi (trung bình, nét liền) ──
            done_part = agv.path[:agv.current_idx + 1]
            if len(done_part) > 1:
                faded2 = _faded(agv.color, 0.6)
                coords = []
                for pt in done_part:
                    if g.has_node(pt):
                        wx2, wy2 = _dxy(pt)
                        px2, py2 = mw.to_screen(wx2, wy2)
                        coords.extend([px2, py2])
                if len(coords) >= 4:
                    mw.create_line(coords, fill=faded2, width=2, tags="vsim")

            # ── Đường còn lại (đậm, dashed) ──
            remaining = agv.path[agv.current_idx:]
            if len(remaining) > 1:
                coords = []
                for pt in remaining:
                    if g.has_node(pt):
                        wx2, wy2 = _dxy(pt)
                        px2, py2 = mw.to_screen(wx2, wy2)
                        coords.extend([px2, py2])
                if len(coords) >= 4:
                    mw.create_line(coords, fill=agv.color, width=2,
                                   dash=(6, 3), tags="vsim")

            # ── Màu viền theo trạng thái ──
            outline_col = {"moving":  "#2ecc71", "waiting": "#f39c12",
                           "done":    "#3498db", "error":   "#e74c3c",
                           "idle":    "#aaa"}.get(agv.status, "#aaa")

            # ── Hình chữ nhật AGV (giống tab giám sát) ──
            HL = 15   # half-length (dọc hướng đi)
            HW = 9    # half-width  (ngang)
            px = -hy  # vector vuông góc
            py =  hx
            corners = [
                sx + hx*HL + px*HW, sy + hy*HL + py*HW,   # đầu-phải
                sx + hx*HL - px*HW, sy + hy*HL - py*HW,   # đầu-trái
                sx - hx*HL - px*HW, sy - hy*HL - py*HW,   # đuôi-trái
                sx - hx*HL + px*HW, sy - hy*HL + py*HW,   # đuôi-phải
            ]
            mw.create_polygon(corners, fill=agv.color, outline=outline_col,
                              width=3, tags="vsim")

            # Mũi tên trắng từ tâm → đầu xe
            mw.create_line(sx, sy,
                           sx + hx*(HL - 2), sy + hy*(HL - 2),
                           fill="white", width=2,
                           arrow=tk.LAST, arrowshape=(7, 9, 3), tags="vsim")

            # Tên AGV (bên cạnh, xoay theo hướng đi — giống giám sát)
            angle_deg = -math.degrees(math.atan2(hy, hx))
            if angle_deg < -90 or angle_deg > 90:
                angle_deg += 180
            lbl_px = -hy; lbl_py = hx   # vuông góc trái hướng đi
            if lbl_py > 0:              # lấy bên nào ở phía trên màn hình
                lbl_px, lbl_py = hy, -hx
            mw.create_text(sx + lbl_px*(HW + 10), sy + lbl_py*(HW + 10),
                           text=agv.id, fill="black",
                           font=("Arial", 8, "bold"), angle=angle_deg, tags="vsim")

            # Icon trạng thái + số thẻ
            icon = {"waiting": "⏸", "done": "✓", "error": "✗"}.get(agv.status, "")
            status_txt = f"{icon}#{tag}" if icon else f"#{tag}"
            mw.create_text(sx, sy + HL + 8, text=status_txt,
                           fill=outline_col, font=("Arial", 7, "bold"), tags="vsim")

    # ══════════════════════════ AGV list helpers ═══════════════════════════════

    def _refresh_tv(self):
        # Giữ selection hiện tại để khôi phục sau khi rebuild
        prev_sel = self.tv.selection()
        for row in self.tv.get_children():
            self.tv.delete(row)
        for agv in self.agv_list:
            status_lbl = {
                "idle": "chờ", "moving": "đang đi", "waiting": "⏸ chờ xung đột",
                "done": "✓ xong", "error": "✗ lỗi",
            }.get(agv.status, agv.status)
            self.tv.insert("", "end", iid=agv.id, values=(
                agv.id, "●",
                agv.start_tag or "—",
                agv.end_tag   or "—",
                status_lbl,
            ), tags=(agv.id,))
            self.tv.tag_configure(agv.id, foreground=agv.color)
        # Khôi phục selection (giữ item đã chọn dù rebuild)
        for iid in prev_sel:
            if self.tv.exists(iid):
                self.tv.selection_set(iid)

    def _selected_agv(self) -> "VirtualAGV | None":
        sel = self.tv.selection()
        if not sel:
            return None
        return next((a for a in self.agv_list if a.id == sel[0]), None)

    def _add_agv(self):
        idx = len(self.agv_list)
        agv = VirtualAGV(agv_id=f"AGV{idx+1:02d}",
                         color=AGV_COLORS[idx % len(AGV_COLORS)])
        self.agv_list.append(agv)
        self._refresh_tv()
        self.tv.selection_set(agv.id)
        self._on_agv_select()

    def _remove_agv(self):
        agv = self._selected_agv()
        if agv:
            self.agv_list.remove(agv)
            self._refresh_tv()
            self._fast_redraw()

    def _clear_all(self):
        self.agv_list.clear()
        VirtualAGV._counter = 0
        self._refresh_tv()
        self._fast_redraw()

    def _on_agv_select(self, *_):
        agv = self._selected_agv()
        if not agv:
            return
        self._var_start.set(str(agv.start_tag) if agv.start_tag else "")
        self._var_end.set(str(agv.end_tag)     if agv.end_tag   else "")
        self._var_task.set(agv.task_type)
        self._refresh_facing()
        if agv.facing_tag:
            for lbl, ft in self._facing_map.items():
                if ft == agv.facing_tag:
                    self._var_facing.set(lbl)
                    break

    # ══════════════════════════ Facing dropdown ════════════════════════════════

    def _refresh_facing(self, *_):
        self._facing_map = {"— Không xác định (Dijkstra thuần) —": None}
        opts = ["— Không xác định (Dijkstra thuần) —"]
        g = self.tm.graph
        try:
            start = int(self._var_start.get())
        except ValueError:
            self._cb_facing["values"] = opts; self._cb_facing.current(0); return
        if not g.has_node(start):
            self._cb_facing["values"] = opts; self._cb_facing.current(0); return

        snd = g.nodes[start]
        sx = snd.get('disp_x', snd.get('x', 0))
        sy = snd.get('disp_y', snd.get('y', 0))
        # Chỉ hiển thị hướng RA (successors) — loại bỏ cạnh một chiều vào
        for nb in sorted(set(g.successors(start))):
            nnd = g.nodes[nb]
            px = nnd.get('disp_x', nnd.get('x', 0))
            py = nnd.get('disp_y', nnd.get('y', 0))
            angle_deg = math.degrees(math.atan2(-(py-sy), px-sx))
            clock_ang = (90 - angle_deg) % 360
            hour = round(clock_ang / 30) % 12
            hour = 12 if hour == 0 else hour
            lbl = f"{hour:>2}h  →  Thẻ {nb}"
            opts.append(lbl)
            self._facing_map[lbl] = nb

        self._cb_facing["values"] = opts
        self._cb_facing.current(0)

    # ══════════════════════════ Config apply ═══════════════════════════════════

    def _apply_config(self):
        agv = self._selected_agv()
        if not agv:
            return
        try:    agv.start_tag = int(self._var_start.get())
        except ValueError: pass
        try:    agv.end_tag   = int(self._var_end.get())
        except ValueError: pass
        agv.task_type  = self._var_task.get()
        agv.facing_tag = self._facing_map.get(self._var_facing.get())
        self._refresh_tv()
        self._fast_redraw()
        self._log("info",
                  f"✔ {agv.id}: thẻ {agv.start_tag} → {agv.end_tag} | {agv.task_type} "
                  f"| hướng đầu xe→{agv.facing_tag}")

    # ══════════════════════════ Map pick ═══════════════════════════════════════

    def _enter_pick(self, mode: str):
        self._pick_mode = mode
        hints = {
            "start": "⬅ Đang chờ click — nhấp vào thẻ trên bản đồ để đặt BẮT ĐẦU",
            "end":   "⬅ Đang chờ click — nhấp vào thẻ trên bản đồ để đặt ĐÍCH",
        }
        self._lbl_pick_hint.config(text=hints[mode])

    def _on_map_click(self, event):
        if not self._pick_mode:
            return
        node = self._nearest_node(event.x, event.y)
        if node is None:
            return
        if self._pick_mode == "start":
            self._var_start.set(str(node))
            self._refresh_facing()
        else:
            self._var_end.set(str(node))
        self._pick_mode = None
        self._lbl_pick_hint.config(text="")

    def _nearest_node(self, cx: float, cy: float, threshold: float = 30) -> int | None:
        g = self.tm.graph; mw = self._map
        best, best_d = None, threshold
        for nid in g.nodes:
            wx = g.nodes[nid].get("x", 0); wy = g.nodes[nid].get("y", 0)
            sx2, sy2 = mw.to_screen(wx, wy)
            d = math.sqrt((sx2 - cx)**2 + (sy2 - cy)**2)
            if d < best_d:
                best_d, best = d, nid
        return best

    # ══════════════════════════ Simulation init ════════════════════════════════

    def _facing_to_prev(self, start_tag: int, facing_tag: int | None) -> int | None:
        if facing_tag is None:
            return None
        g = self.tm.graph
        if not (g.has_node(start_tag) and g.has_node(facing_tag)):
            return None
        def _dxy2(n): nd = g.nodes.get(n, {}); return nd.get('disp_x', nd.get('x', 0)), nd.get('disp_y', nd.get('y', 0))
        sx, sy = _dxy2(start_tag)
        ftx, fty = _dxy2(facing_tag)
        fx, fy = ftx - sx, fty - sy
        fmag = math.sqrt(fx**2 + fy**2)
        if fmag < 1e-6:
            return None
        all_nb = set(g.predecessors(start_tag)) | set(g.successors(start_tag))
        best_prev, best_dot = None, 1.0
        for nb in all_nb:
            if nb == facing_tag:
                continue
            nbx, nby = _dxy2(nb)
            dx = nbx - sx
            dy = nby - sy
            mag = math.sqrt(dx**2 + dy**2)
            if mag < 1e-6:
                continue
            dot = (fx*dx + fy*dy) / (fmag * mag)
            if dot < best_dot:
                best_dot, best_prev = dot, nb
        return best_prev if (best_prev is not None and best_dot < 0) else None

    def _init_simulation(self):
        self._reset_sim(keep_config=True)
        for agv in self.agv_list:
            if not agv.start_tag or not agv.end_tag:
                agv.status = "error"
                self._log("conflict", f"⚠ {agv.id}: chưa cấu hình start/end")
                continue
            prev_node = self._facing_to_prev(agv.start_tag, agv.facing_tag)
            try:
                path = self.tm.find_path_directed(agv.start_tag, agv.end_tag, prev_node)
            except Exception as exc:
                agv.status = "error"
                self._log("conflict", f"⚠ {agv.id} lỗi pathfinding: {exc}")
                continue
            if not path:
                agv.status = "error"
                self._log("conflict", f"⚠ {agv.id}: không tìm được đường")
                continue

            agv.path          = list(path)
            agv.original_path = list(path)
            agv.current_idx   = 0
            agv.status        = "moving"

            try:
                steps, _ = self.sim.dry_run(
                    agv.start_tag, prev_node, agv.end_tag,
                    agv.task_type, facing_tag=agv.facing_tag,
                )
                agv.steps_data = steps or []
            except Exception:
                agv.steps_data = []

            pstr = " → ".join(str(t) for t in path)
            self._log("info", f"✔ {agv.id}: [{pstr}]")

        self._step_count = 0
        n_active = sum(1 for a in self.agv_list if a.status == "moving")
        self._lbl_step.config(text=f"Bước: 0  |  Còn: {n_active}")
        self._refresh_tv()
        self._full_redraw()   # full redraw sau khởi tạo

    # ══════════════════════════ Step logic ════════════════════════════════════

    def _build_conflict_tables(self):
        """Trả về (occupied, active_edges) tại bước hiện tại."""
        occupied: dict[int, str] = {}
        active_edges: dict[tuple, str] = {}
        for agv in self.agv_list:
            if agv.status not in ("done", "error") and agv.current_tag:
                occupied[agv.current_tag] = agv.id
            if agv.status in ("moving", "waiting") and agv.next_tag:
                active_edges[(agv.current_tag, agv.next_tag)] = agv.id
        return occupied, active_edges

    def _lookahead_headon(self, agv: VirtualAGV) -> "tuple[str|None, VirtualAGV|None, int]":
        """
        Nhìn trước N bước (N = giá trị spinbox): kiểm tra cạnh đối đầu trong hành lang.

        Quy tắc nhường:
          • Thứ tự ưu tiên: task priority thấp hơn → nhường; cùng priority → ID lớn hơn → nhường.
          • Bất đối xứng: chỉ đúng 1 AGV nhận conflict → không deadlock đồng thời.

        Trả về (reason, other_agv, conflict_step) trong đó:
          conflict_step = chỉ số trong a_win tại đó cạnh xung đột bắt đầu
          (0 = cạnh ngay tiếp theo current, 1 = cách 1 bước, ...)
        """
        lookahead = self._var_lookahead.get()
        if lookahead <= 0:
            return None, None, 0
        # AGV đang đi qua siding → không áp dụng lookahead thông thường
        if agv.bypassing:
            return None, None, 0

        a_win = agv.path[agv.current_idx : agv.current_idx + lookahead + 1]
        a_edges: set[tuple] = set()
        for i in range(len(a_win) - 1):
            a_edges.add((a_win[i], a_win[i + 1]))

        for other in self.agv_list:
            if other.id == agv.id or other.status in ("done", "error", "idle"):
                continue

            # ── Tìm cạnh đối đầu ───────────────────────────────────────────
            b_win = other.path[other.current_idx : other.current_idx + lookahead + 1]
            conflict_edge = None
            for j in range(len(b_win) - 1):
                u, v = b_win[j], b_win[j + 1]   # cạnh của B: u → v
                if (v, u) in a_edges:             # cạnh ngược: v → u ∈ A's path
                    conflict_edge = (v, u)
                    break
            if conflict_edge is None:
                continue

            # ── Ai phải nhường? ─────────────────────────────────────────────
            a_prio = agv.priority
            b_prio = other.priority
            a_yields = (a_prio > b_prio) or (a_prio == b_prio and agv.id > other.id)

            if a_yields:
                # Tìm vị trí cạnh xung đột trong a_win
                conflict_a_step = 0
                for ci in range(len(a_win) - 1):
                    if a_win[ci] == conflict_edge[0] and a_win[ci + 1] == conflict_edge[1]:
                        conflict_a_step = ci
                        break
                return (
                    f"hành lang đối đầu với {other.id} tại cạnh "
                    f"{conflict_edge[0]}↔{conflict_edge[1]} "
                    f"(nhìn trước {lookahead} bước, bước +{conflict_a_step})",
                    other,
                    conflict_a_step,
                )
        return None, None, 0

    def _process_one_agv(self, agv: VirtualAGV, occupied: dict, active_edges: dict):
        """Xử lý 1 AGV: di chuyển hoặc chờ. Cập nhật occupied & active_edges inplace."""
        next_t = agv.next_tag
        if next_t is None:
            agv.status = "done"
            self._log("done", f"  ✓ {agv.id} đến đích thẻ {agv.current_tag}")
            return

        self._log_step_actions(agv)

        blocked_by: str | None = None

        # ── Check 1: node conflict (1 bước) ───────────────────────────────────
        # Ràng buộc vật lý cứng: không thể di chuyển vào ô đang có AGV khác,
        # bất kể mức ưu tiên. Ưu tiên chỉ áp dụng cho đối đầu (Check 2/3).
        if next_t in occupied and occupied[next_t] != agv.id:
            blocked_by = f"node {next_t} bị {occupied[next_t]} chiếm"

        # ── Check 2: head-on tức thì (1 bước) ────────────────────────────────
        # Bất đối xứng: chỉ AGV có ưu tiên THẤP HƠN (hoặc ID lớn hơn khi bằng) nhường
        if blocked_by is None and (next_t, agv.current_tag) in active_edges:
            other_id  = active_edges[(next_t, agv.current_tag)]
            other_agv = next((a for a in self.agv_list if a.id == other_id), None)
            a_yields = other_agv and (
                (agv.priority > other_agv.priority) or
                (agv.priority == other_agv.priority and agv.id > other_agv.id)
            )
            if a_yields:
                new_path = self._reroute(agv, exclude_edge=(agv.current_tag, next_t))
                if new_path and new_path != agv.path[agv.current_idx:]:
                    old_next = agv.next_tag
                    agv.path = agv.path[:agv.current_idx] + new_path
                    agv.planned_hold_at = None
                    self._draw_reroute_path(agv, new_path)
                    self._log("reroute",
                              f"  ↺ {agv.id} tính lại đường tránh đối đầu {other_id} "
                              f"({old_next}→{agv.next_tag})")
                    active_edges.pop((agv.current_tag, old_next), None)
                    if agv.next_tag:
                        active_edges[(agv.current_tag, agv.next_tag)] = agv.id
                else:
                    blocked_by = f"đối đầu {other_id} tại cạnh {agv.current_tag}↔{next_t}"

        # ── Check 4: Zone reservation ─────────────────────────────────────────
        # Nếu next_t thuộc zone đang bị chiếm → chờ (bất kể ưu tiên).
        # Zone = ngã ba/tư hoặc hành lang đặt trong zone manager config.
        if blocked_by is None and self._sim_zones.loaded:
            ok, reason = self._sim_zones.can_enter(agv.id, next_t)
            if not ok:
                blocked_by = f"thẻ {next_t}: {reason}"

        # ── Check 3: lookahead N bước — phát hiện hành lang đối đầu sớm ──────
        # Khi phát hiện đối đầu K bước phía trước:
        #   • Thử tìm đường vòng. Nếu chi phí ≤ (1 + threshold%) → đi ngay.
        #   • Nếu không có đường vòng hoặc quá dài → kế hoạch dừng tại thẻ an toàn
        #     cách K bước (AGV vẫn TIẾP TỤC đến đó rồi mới dừng).
        if blocked_by is None:
            if agv.planned_hold_at is not None:
                # Đang di chuyển đến điểm dừng đã lên kế hoạch
                la_reason2, _, _ = self._lookahead_headon(agv)
                if la_reason2 is None:
                    # Hành lang đã thông → hủy kế hoạch dừng
                    self._log("info",
                              f"  ✔ {agv.id} hành lang thông, hủy điểm dừng #{agv.planned_hold_at}")
                    agv.planned_hold_at = None
                elif agv.current_tag == agv.planned_hold_at:
                    # Đã đến điểm dừng, conflict vẫn còn → chờ ở đây
                    blocked_by = f"giữ vị trí #{agv.planned_hold_at}: {la_reason2}"
                # else: đang tiến đến planned_hold_at, không block
            else:
                la_reason, la_other, la_k = self._lookahead_headon(agv)
                if la_reason and la_other is not None:
                    # Thử tìm đường vòng
                    new_path = self._reroute(agv)
                    if new_path and new_path != agv.path[agv.current_idx:]:
                        orig_cost   = self._path_cost(agv.path[agv.current_idx:])
                        detour_cost = self._path_cost(new_path)
                        threshold   = self._var_detour_threshold.get() / 100.0
                        if detour_cost <= orig_cost * (1.0 + threshold):
                            # Đường vòng chấp nhận → đi ngay
                            old_str = " → ".join(
                                str(t) for t in agv.path[agv.current_idx:agv.current_idx + 5])
                            agv.path = agv.path[:agv.current_idx] + new_path
                            agv.planned_hold_at = None
                            self._draw_reroute_path(agv, new_path)
                            self._log("reroute",
                                      f"  ↺ {agv.id} vòng tránh hành lang "
                                      f"(chi phí {detour_cost:.1f} ≤ {orig_cost*(1+threshold):.1f}): "
                                      f"{old_str}... → {agv.next_tag}")
                        else:
                            # Đường vòng quá dài → dừng trước cửa hành lang
                            hold_idx  = agv.current_idx + max(la_k, 0)
                            hold_node = (agv.path[hold_idx]
                                         if hold_idx < len(agv.path) else agv.current_tag)
                            if hold_node == agv.current_tag:
                                blocked_by = la_reason
                            else:
                                agv.planned_hold_at = hold_node
                                self._log("wait",
                                          f"  ⏳ {agv.id} đường vòng quá dài "
                                          f"({detour_cost:.1f} > {orig_cost*(1+threshold):.1f}), "
                                          f"dự kiến dừng tại #{hold_node}")
                    else:
                        # Không có đường vòng → dừng trước cửa hành lang
                        hold_idx  = agv.current_idx + max(la_k, 0)
                        hold_node = (agv.path[hold_idx]
                                     if hold_idx < len(agv.path) else agv.current_tag)
                        if hold_node == agv.current_tag:
                            blocked_by = la_reason
                        else:
                            agv.planned_hold_at = hold_node
                            self._log("wait",
                                      f"  ⏳ {agv.id} không có đường vòng, "
                                      f"dự kiến dừng tại #{hold_node}")

        if blocked_by:
            agv.status      = "waiting"
            agv.wait_reason = blocked_by
            self._log("wait", f"  ⏸ {agv.id} CHỜ: {blocked_by}")
        else:
            agv.status      = "moving"
            agv.wait_reason = ""
            # Xóa vị trí cũ khỏi occupied trước khi di chuyển
            # (để AGV khác biết chỗ này đã trống trong cùng bước)
            old_tag = agv.current_tag
            if old_tag and occupied.get(old_tag) == agv.id:
                del occupied[old_tag]
            agv.current_idx += 1
            occupied[agv.current_tag] = agv.id
            # Cập nhật zone tracker sau khi di chuyển
            if self._sim_zones.loaded:
                self._sim_zones.on_agv_moved(agv.id, agv.current_tag)
            self._log("move", f"  → {agv.id} tiến đến thẻ {agv.current_tag}")
            if agv.current_idx >= len(agv.path) - 1:
                agv.status           = "done"
                agv.planned_hold_at  = None
                if self._sim_zones.loaded:
                    self._sim_zones.release_all(agv.id)
                self._log("done", f"  ✓ {agv.id} HOÀN THÀNH!")

    def _step(self):
        """Tiến 1 bước — tất cả AGV đang active."""
        active = [a for a in self.agv_list if a.status in ("moving", "waiting")]
        if not active:
            self._log("info", "═══ Mô phỏng kết thúc ═══")
            self._stop_auto()
            return

        self._step_count += 1
        n_active = sum(1 for a in self.agv_list if a.status not in ("done", "error"))
        self._lbl_step.config(text=f"Bước: {self._step_count}  |  Còn: {n_active}")
        self._log("head", f"─── Bước {self._step_count} ───")

        # Kiểm tra & áp dụng vùng tránh (Passing Bay) trước khi xử lý từng AGV
        self._apply_passing_bays()

        # Clear bypassing flag khi AGV đã hoàn thành đường siding
        for agv in self.agv_list:
            if agv.bypassing and agv.current_idx >= agv.bypass_exit_idx:
                agv.bypassing       = False
                agv.bypass_exit_idx = -1
                self._log("info", f"  ✔ {agv.id} đã ra khỏi siding, tiếp tục hành trình")

        occupied, active_edges = self._build_conflict_tables()
        for agv in sorted(active, key=lambda a: a.priority):
            self._process_one_agv(agv, occupied, active_edges)

        # ── Phát hiện BẾ TẮC THỰC SỰ (tất cả chờ lẫn nhau) ──────────────
        still_active = [a for a in self.agv_list if a.status in ("moving", "waiting")]
        if still_active and all(a.status == "waiting" for a in still_active):
            sorted_by_prio = sorted(still_active, key=lambda a: (a.priority, a.id))
            lowest  = sorted_by_prio[-1]
            highest = sorted_by_prio[0]

            def _try_reroute(agv: VirtualAGV) -> bool:
                new_path = self._reroute(agv)
                if new_path and new_path != agv.path[agv.current_idx:]:
                    old_str = " → ".join(str(t) for t in agv.path[agv.current_idx:agv.current_idx+4])
                    agv.path = agv.path[:agv.current_idx] + new_path
                    agv.planned_hold_at = None
                    agv.status = "moving"
                    agv.wait_reason = ""
                    self._draw_reroute_path(agv, new_path)
                    self._log("reroute",
                              f"  ↺ [bế tắc] {agv.id} tính lại đường "
                              f"({'có lùi' if any(new_path[i] not in list(self.tm.graph.successors(new_path[i-1])) for i in range(1, len(new_path))) else 'tiến'}): "
                              f"{old_str}... → {agv.next_tag}")
                    return True
                return False

            # Bước 1: Thử reroute từng xe (ưu tiên thấp trước, rồi cao)
            # _escape_route() bên trong _reroute cho phép đi ngược cạnh 1 chiều
            resolved = _try_reroute(lowest) or _try_reroute(highest)

            # Bước 2: Circular ZONE deadlock — force-release token của xe thấp nhất
            if not resolved and self._sim_zones.loaded and all(
                "zone" in (a.wait_reason or "") for a in still_active
            ):
                self._sim_zones.release_all(lowest.id)
                lowest.wait_reason = "nhường zone (circular deadlock)"
                self._log("resolve",
                          f"  ⚡ [zone deadlock] {lowest.id} nhường zone token "
                          f"→ {highest.id} có thể tiến qua")
                occupied2, active_edges2 = self._build_conflict_tables()
                self._process_one_agv(highest, occupied2, active_edges2)
                resolved = True

            if not resolved:
                self._log("error",
                          f"  ⛔ BẾ TẮC KHÔNG GIẢI ĐƯỢC: tất cả AGV đang chờ lẫn nhau, "
                          f"không có đường thay thế. Hãy hoàn tác và điều chỉnh tuyến đường.")
                self._stop_auto()

        self._refresh_tv()
        self._fast_redraw()   # ← không nhấp nháy

    def _step_selected(self):
        """Tiến 1 bước chỉ cho AGV đang được chọn trong danh sách."""
        agv = self._selected_agv()
        if not agv:
            self._log("info", "⚠ Chọn 1 AGV trong danh sách trước")
            return
        if agv.status not in ("moving", "waiting"):
            self._log("info", f"⚠ {agv.id} không ở trạng thái di chuyển (status: {agv.status})")
            return

        self._step_count += 1
        self._log("head", f"─── Bước {self._step_count} [{agv.id}] ───")

        occupied, active_edges = self._build_conflict_tables()
        self._process_one_agv(agv, occupied, active_edges)

        n_active = sum(1 for a in self.agv_list if a.status not in ("done", "error"))
        self._lbl_step.config(text=f"Bước: {self._step_count}  |  Còn: {n_active}")
        self._refresh_tv()
        self._fast_redraw()

    def _undo_selected(self):
        """Lùi AGV đang chọn về 1 bước (Ctrl+Z cho từng AGV)."""
        agv = self._selected_agv()
        if not agv:
            self._log("info", "⚠ Chọn 1 AGV trong danh sách trước")
            return
        if agv.current_idx <= 0:
            self._log("info", f"⚠ {agv.id} đang ở vị trí đầu, không thể hoàn tác")
            return

        prev_tag = agv.path[agv.current_idx - 1]
        agv.current_idx -= 1
        # Nếu trạng thái là done → đưa về moving để có thể tiếp tục
        if agv.status == "done":
            agv.status = "moving"
        agv.wait_reason = ""
        self._step_count = max(0, self._step_count - 1)
        self._log("info",
                  f"  ↩ {agv.id} hoàn tác: quay về thẻ {agv.current_tag} (từ {prev_tag})")
        n_active = sum(1 for a in self.agv_list if a.status not in ("done", "error"))
        self._lbl_step.config(text=f"Bước: {self._step_count}  |  Còn: {n_active}")
        self._refresh_tv()
        self._fast_redraw()

    def _draw_reroute_path(self, agv: VirtualAGV, new_path: list):
        """Vẽ tạm đường tính lại bằng màu tím đậm lên canvas."""
        g  = self.tm.graph
        mw = self._map
        coords = []
        for pt in new_path:
            if g.has_node(pt):
                wx = g.nodes[pt].get("x", 0)
                wy = g.nodes[pt].get("y", 0)
                px2, py2 = mw.to_screen(wx, wy)
                coords.extend([px2, py2])
        if len(coords) >= 4:
            mw.create_line(coords, fill="#9b59b6", width=3,
                           dash=(4, 2), tags="vsim")

    def _log_step_actions(self, agv: VirtualAGV):
        idx = agv.current_idx
        if not agv.steps_data or idx >= len(agv.steps_data):
            return
        step = agv.steps_data[idx]
        acts = [a["label"] for a in step.get("actions", [])]
        nav  = step.get("nav_action", {}).get("label", "")
        if acts or nav:
            parts = "  ".join(acts + ([nav] if nav else []))
            self._log("action", f"  [{agv.id}@{agv.current_tag}] {parts}")

    def _reroute(self, agv: VirtualAGV, exclude_edge=None) -> list | None:
        g = self.tm.graph
        saved = None
        if exclude_edge:
            ed = g.get_edge_data(*exclude_edge)
            if ed is not None:
                saved = ed.get("allowed", True)
                ed["allowed"] = False
        try:
            prev_node = agv.path[agv.current_idx - 1] if agv.current_idx > 0 else None
            result = self.tm.find_path_directed(agv.current_tag, agv.end_tag, prev_node)
            # Nếu không tìm được đường tiến (hoặc trả về đường cũ) → thử đi lùi thoát bế tắc
            if not result or result == agv.path[agv.current_idx:]:
                result = self._escape_route(agv.current_tag, agv.end_tag, g)
            return result
        except Exception:
            return None
        finally:
            if exclude_edge and saved is not None:
                ed = g.get_edge_data(*exclude_edge)
                if ed is not None:
                    ed["allowed"] = saved

    def _apply_passing_bays(self):
        """
        Kiểm tra vùng tránh (Passing Bay / Siding) khi 2 AGV đi ngược chiều trên 1 hành lang.

        Cấu hình zones.json:
          {"id":"bay1","type":"PASSING_BAY","branch_node":123,
           "nodes":[121,122,123,124,125],   ← corridor theo thứ tự
           "siding_nodes":[126,131]}         ← siding từ branch đến cuối

        Luật:
          • Xe gần branch hơn → đi vào siding (đến đầu siding, chờ, quay lại)
          • Xe xa hơn → đi thẳng (sẽ tự nhiên chờ nếu branch bị chiếm)
          • Tie-break: task priority thấp hơn (số lớn hơn) → vào siding; cùng priority → ID lớn hơn → vào siding
        """
        if not self._sim_zones._passing_bays:
            return

        for bay in self._sim_zones._passing_bays.values():
            branch    = bay['branch_node']
            siding    = bay['siding_nodes']        # [s1, s2, ..., sEnd] theo thứ tự branch→end
            corridor  = bay['main_corridor']       # [c0, c1, ..., cN] theo thứ tự

            if not siding:
                continue

            # Tìm AGV đang hoạt động trên main corridor (chưa bypassing)
            bay_set = set(corridor)
            active = [
                a for a in self.agv_list
                if a.status in ('moving', 'waiting')
                and a.current_tag in bay_set
                and not a.bypassing
            ]
            if len(active) < 2:
                continue

            # Tìm cặp đi NGƯỢC CHIỀU nhau trên corridor
            handled = set()
            for i, agv_a in enumerate(active):
                for agv_b in active[i + 1:]:
                    pair = frozenset({agv_a.id, agv_b.id})
                    if pair in handled:
                        continue

                    # Vị trí index trên corridor
                    try:
                        idx_a = corridor.index(agv_a.current_tag)
                        idx_b = corridor.index(agv_b.current_tag)
                    except ValueError:
                        continue

                    # Hướng đi kế tiếp
                    next_a = agv_a.next_tag
                    next_b = agv_b.next_tag
                    if next_a is None or next_b is None:
                        continue

                    idx_na = corridor.index(next_a) if next_a in corridor else -1
                    idx_nb = corridor.index(next_b) if next_b in corridor else -1
                    if idx_na < 0 or idx_nb < 0:
                        continue

                    dir_a = 1 if idx_na > idx_a else -1
                    dir_b = 1 if idx_nb > idx_b else -1
                    if dir_a == dir_b:
                        continue  # Cùng chiều → không đối đầu

                    # Cả 2 cần đi qua branch_node
                    branch_idx = corridor.index(branch) if branch in corridor else -1
                    if branch_idx < 0:
                        continue

                    remaining_a = agv_a.path[agv_a.current_idx:]
                    remaining_b = agv_b.path[agv_b.current_idx:]
                    if branch not in remaining_a or branch not in remaining_b:
                        continue

                    # Khoảng cách đến branch (số bước)
                    steps_a = abs(idx_a - branch_idx)
                    steps_b = abs(idx_b - branch_idx)

                    # Xe gần branch hơn → vào siding
                    if steps_a < steps_b:
                        go_siding, go_straight = agv_a, agv_b
                    elif steps_b < steps_a:
                        go_siding, go_straight = agv_b, agv_a
                    else:
                        # Equidistant: priority thấp hơn (số lớn) → siding; cùng → ID lớn → siding
                        if agv_a.priority != agv_b.priority:
                            go_siding   = agv_a if agv_a.priority > agv_b.priority else agv_b
                            go_straight = agv_b if agv_a.priority > agv_b.priority else agv_a
                        else:
                            go_siding   = agv_a if agv_a.id > agv_b.id else agv_b
                            go_straight = agv_b if agv_a.id > agv_b.id else agv_a

                    # Xây dựng đường vào siding và quay lại
                    rem = go_siding.path[go_siding.current_idx:]
                    b_pos = rem.index(branch)
                    path_to_branch   = rem[:b_pos + 1]          # [..., branch]
                    path_after_branch= rem[b_pos + 1:]           # [next_on_main, ..., dest]

                    siding_in     = list(siding)                 # branch→s1→...→sEnd
                    siding_return = list(reversed(siding))       # sEnd→...→s1→branch (không gồm branch ở đầu)
                    # Tránh double branch: siding_return bắt đầu từ sEnd, kết thúc tại s1, sau đó thêm branch lại
                    new_rem = path_to_branch + siding_in + siding_return + [branch] + path_after_branch

                    go_siding.path            = go_siding.path[:go_siding.current_idx] + new_rem
                    go_siding.bypassing       = True
                    # Khi nào thoát: sau khi qua đoạn siding_return về branch lần 2
                    exit_in_rem               = b_pos + len(siding_in) + len(siding_return) + 1  # index của branch lần 2 trong new_rem
                    go_siding.bypass_exit_idx = go_siding.current_idx + exit_in_rem
                    go_siding.planned_hold_at = None

                    handled.add(pair)
                    self._draw_reroute_path(go_siding, new_rem)
                    self._log("reroute",
                              f"  🔀 [passing bay] {go_siding.id} vào siding "
                              f"{siding} (nhường {go_straight.id} đi thẳng)")

    def _path_cost(self, path: list[int]) -> float:
        """Tính tổng chi phí đường đi dựa theo edge weight."""
        g = self.tm.graph
        total = 0.0
        for i in range(len(path) - 1):
            u, v = path[i], path[i + 1]
            if g.has_edge(u, v):
                total += g[u][v].get('weight', 1)
            else:
                total += 1
        return max(total, 1.0)

    def _escape_route(self, start: int, end: int, g) -> list | None:
        """
        Tìm đường thoát khi không còn đường tiến (bế tắc trong hành lang 1 chiều).
        Cho phép đi ngược cạnh (predecessors) với penalty cao.
        Ví dụ: AGV01@999 muốn đến 101 nhưng 74 bị chặn
          → 999←61 (ngược) ←24 (ngược) ←51 (ngược) →111 →110 →101
        """
        import heapq
        BACKWARD_COST = 20   # penalty mỗi cạnh ngược

        INF = float('inf')
        dist: dict[int, float] = {start: 0}
        prev: dict[int, int | None] = {start: None}
        heap = [(0, start)]

        while heap:
            cost, node = heapq.heappop(heap)
            if node == end:
                break
            if cost > dist.get(node, INF):
                continue

            # ── Cạnh tiến (forward) ─────────────────────────
            for nb in g.successors(node):
                if not g[node][nb].get('allowed', True):
                    continue
                w = g[node][nb].get('weight', 1)
                nc = cost + w
                if nc < dist.get(nb, INF):
                    dist[nb] = nc
                    prev[nb] = node
                    heapq.heappush(heap, (nc, nb))

            # ── Cạnh lùi (backward — đi ngược cung) ─────────
            for nb in g.predecessors(node):
                w = g[nb][node].get('weight', 1)
                nc = cost + w + BACKWARD_COST
                if nc < dist.get(nb, INF):
                    dist[nb] = nc
                    prev[nb] = node
                    heapq.heappush(heap, (nc, nb))

        if end not in prev:
            return None

        path: list[int] = []
        node: int | None = end
        while node is not None:
            path.append(node)
            node = prev.get(node)
        path.reverse()
        return path if path and path[0] == start else None

    # ══════════════════════════ Auto-run ══════════════════════════════════════

    def _toggle_run(self):
        if self._is_running:
            self._stop_auto()
        else:
            self._is_running = True
            self._btn_run.config(text="⏸ Dừng")
            self._auto_step()

    def _auto_step(self):
        if not self._is_running:
            return
        if not any(a.status in ("moving", "waiting") for a in self.agv_list):
            self._stop_auto()
            return
        self._step()
        self._run_job = self.after(self._var_speed.get(), self._auto_step)

    def _stop_auto(self):
        self._is_running = False
        self._btn_run.config(text="▶ Tự động")
        if self._run_job:
            self.after_cancel(self._run_job)
            self._run_job = None

    def _reset_sim(self, keep_config: bool = False):
        self._stop_auto()
        self._sim_zones.reset()          # giải phóng tất cả zone tokens
        for agv in self.agv_list:
            agv.path             = []
            agv.original_path    = []
            agv.current_idx      = 0
            agv.status           = "idle"
            agv.wait_reason      = ""
            agv.planned_hold_at  = None
            agv.bypassing        = False
            agv.bypass_exit_idx  = -1
            if not keep_config:
                agv.steps_data = []
        self._step_count = 0
        self._lbl_step.config(text="Bước: 0  |  Còn: 0")
        self._txt_log.config(state="normal")
        self._txt_log.delete("1.0", "end")
        self._txt_log.config(state="disabled")
        self._refresh_tv()
        self._fast_redraw()

    # ══════════════════════════ Log ═══════════════════════════════════════════

    def _log(self, tag: str, msg: str):
        self._txt_log.config(state="normal")
        self._txt_log.insert("end", msg + "\n", tag)
        self._txt_log.see("end")
        self._txt_log.config(state="disabled")
