"""
gui/monitor_view.py  — Monitor Tab
-------------------------------------
build_panel(app: AppShell) — xây dựng sidebar Monitor:
  - Connection indicators (WiFi / Broker)
  - AGV fleet status table
  - Order queue display
  - Dispatcher controls (AGV, start node, heading, target, task type)
  - Workflow dispatch (pickup → tổ giao hàng)
  - Manual command buttons (run / stop / reset / reverse)
  - Force Set Position
  - Debug panel (clear queue / clear routes)
  - Active Tasks panel (view + cancel)
  - Map name label

Migrate từ main.py App.show_monitor_view() (lines 1784–2047).
"""
from __future__ import annotations
import math
import os
import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gui.app_shell import AppShell


def build_panel(app: 'AppShell') -> None:
    """Xây dựng toàn bộ sidebar Monitor vào app.tool_frame và show app.map_widget."""
    ctx    = app.ctx
    config = ctx.config

    # ── Show map widget ───────────────────────────────────────────────────────
    app.map_widget.pack(fill='both', expand=True)
    app.map_widget.set_tool("monitor")

    # ── Connection Indicators ─────────────────────────────────────────────────
    frm_status = ttk.Frame(app.tool_frame)
    frm_status.pack(anchor='ne', pady=5, fill='x')

    _init_color = "#2ecc71" if ctx.mqtt_connected else "gray"
    app.cv_wifi = tk.Canvas(frm_status, width=15, height=15, highlightthickness=0)
    app.cv_wifi.pack(side='left', padx=2)
    app.cv_wifi.create_oval(2, 2, 13, 13, fill=_init_color, tags="status")
    ttk.Label(frm_status, text="WiFi", font=("Arial", 8)).pack(side='left', padx=(0, 5))

    app.cv_broker = tk.Canvas(frm_status, width=15, height=15, highlightthickness=0)
    app.cv_broker.pack(side='left', padx=2)
    app.cv_broker.create_oval(2, 2, 13, 13, fill=_init_color, tags="status")
    ttk.Label(frm_status, text="Broker", font=("Arial", 8)).pack(side='left')

    api_status = "ON" if config.get('integration', {}).get('api_enabled') else "OFF"
    api_port   = config.get('integration', {}).get('api_port', 8000)
    ttk.Label(app.tool_frame, text=f"API: {api_status} ({api_port})",
              font=("Arial", 8), foreground="gray").pack(anchor='ne')

    # ── Fleet status table ────────────────────────────────────────────────────
    ttk.Label(app.tool_frame, text=app.t("lbl_fleet_status"),
              font=("Arial", 12, "bold")).pack(pady=5)

    cols = ("ID", "Tag", "Lifecycle", "RSSI", "Pin")
    app.tree_agv = ttk.Treeview(app.tool_frame, columns=cols, show='headings', height=10)
    app.tree_agv.heading("ID",        text=app.t("col_id"))
    app.tree_agv.heading("Tag",       text=app.t("col_tag"))
    app.tree_agv.heading("Lifecycle", text="Lifecycle")
    app.tree_agv.heading("RSSI",      text=app.t("col_rssi"))
    app.tree_agv.heading("Pin",       text="Pin")
    app.tree_agv.column("ID",        width=50)
    app.tree_agv.column("Tag",       width=40)
    app.tree_agv.column("Lifecycle", width=70)
    app.tree_agv.column("RSSI",      width=40)
    app.tree_agv.column("Pin",       width=45)
    app.tree_agv.tag_configure("free",       background="#d5f5e3")
    app.tree_agv.tag_configure("assigned",   background="#fef9e7")
    app.tree_agv.tag_configure("picking",    background="#fdebd0")
    app.tree_agv.tag_configure("delivering", background="#fdebd0")
    app.tree_agv.tag_configure("returning",  background="#d6eaf8")
    app.tree_agv.tag_configure("lost",       background="#fadbd8")
    app.tree_agv.tag_configure("bat_low",    background="#f9ebea", foreground="#c0392b")
    app.tree_agv.pack(fill='x', pady=5)

    # ── Queue display ─────────────────────────────────────────────────────────
    ttk.Separator(app.tool_frame, orient='horizontal').pack(pady=10, fill='x')
    ttk.Label(app.tool_frame, text="Order Queue:",
              font=("Arial", 10, "bold")).pack(anchor='w')
    app.lbl_queue = ttk.Label(app.tool_frame, text="[Empty]", foreground="blue")
    app.lbl_queue.pack(anchor='w', pady=2)

    # ── Dispatcher controls ───────────────────────────────────────────────────
    ttk.Label(app.tool_frame, text=app.t("lbl_dispatcher"),
              font=("Arial", 12, "bold")).pack(pady=5)

    # Select AGV
    ttk.Label(app.tool_frame, text=app.t("lbl_select_agv")).pack(anchor='w')
    app.cb_agv_sel = ttk.Combobox(app.tool_frame,
                                   values=[agv.id for agv in ctx.agv_list])
    if ctx.agv_list:
        app.cb_agv_sel.current(0)
    app.cb_agv_sel.pack(fill='x', pady=2)

    # Select Start Node
    node_list = sorted([str(n) for n in ctx.planner.graph.nodes])
    ttk.Label(app.tool_frame, text=app.t("lbl_start_node")).pack(anchor='w')
    app.cb_start_node = ttk.Combobox(app.tool_frame,
                                      values=["Current Position"] + node_list)
    app.cb_start_node.current(0)
    app.cb_start_node.pack(fill='x', pady=2)

    # Direction / Heading
    ttk.Label(app.tool_frame, text="Hướng đầu xe:").pack(anchor='w')
    app._dispatch_facing_map = {}
    app.cb_dispatch_dir = ttk.Combobox(app.tool_frame, state='readonly')
    app.cb_dispatch_dir['values'] = ["— Chọn thẻ bắt đầu trước —"]
    app.cb_dispatch_dir.current(0)
    app.cb_dispatch_dir.pack(fill='x', pady=2)

    def _refresh_dispatch_dir(*_):
        sel = app.cb_start_node.get()
        g   = ctx.planner.graph
        app._dispatch_facing_map = {"— Tự động (Dijkstra) —": None}
        if sel == "Current Position":
            try:
                agv_id = app.cb_agv_sel.get()
                agv    = next(a for a in ctx.agv_list if str(a.id) == str(agv_id))
                start  = agv.current_tag
            except Exception:
                start  = 0
        else:
            try:
                start = int(sel)
            except ValueError:
                start = 0
        if not start or not g.has_node(start):
            app.cb_dispatch_dir['values'] = ["— Chọn thẻ bắt đầu trước —"]
            app.cb_dispatch_dir.current(0)
            return

        def _get_xy(ndata):
            return (ndata.get('disp_x', ndata.get('x', 0)),
                    ndata.get('disp_y', ndata.get('y', 0)))

        sx, sy = _get_xy(g.nodes[start])
        all_nb = sorted(set(g.successors(start)))
        opts   = ["— Tự động (Dijkstra) —"]
        for nb in all_nb:
            nx_, ny_ = _get_xy(g.nodes[nb])
            dx, dy   = nx_ - sx, ny_ - sy
            angle_deg   = math.degrees(math.atan2(-dy, dx))
            clock_angle = (90 - angle_deg) % 360
            hour  = round(clock_angle / 30) % 12
            hour  = 12 if hour == 0 else hour
            label = f"{hour:>2}h  →  Thẻ {nb}"
            opts.append(label)
            fmag = math.hypot(dx, dy)
            best_prev2, best_dot2 = None, 1.0
            for nb2 in all_nb:
                if nb2 == nb:
                    continue
                nx2, ny2 = _get_xy(g.nodes[nb2])
                dnx, dny = nx2 - sx, ny2 - sy
                mag2 = math.hypot(dnx, dny)
                if fmag < 1e-6 or mag2 < 1e-6:
                    continue
                dot2 = (dx * dnx + dy * dny) / (fmag * mag2)
                if dot2 < best_dot2:
                    best_dot2, best_prev2 = dot2, nb2
            app._dispatch_facing_map[label] = (nb, best_prev2 if best_dot2 < 0 else None)
        app.cb_dispatch_dir['values'] = opts
        app.cb_dispatch_dir.current(0)

    app.cb_start_node.bind("<<ComboboxSelected>>", _refresh_dispatch_dir)
    app.cb_agv_sel.bind("<<ComboboxSelected>>",   _refresh_dispatch_dir)

    # Select Target
    ttk.Label(app.tool_frame, text=app.t("lbl_target_node")).pack(anchor='w')
    app.cb_target_node = ttk.Combobox(app.tool_frame, values=node_list)
    app.cb_target_node.pack(fill='x', pady=2)

    # Task Type
    ttk.Label(app.tool_frame, text=app.t("lbl_task_type")).pack(anchor='w')
    app.cb_task_type = ttk.Combobox(app.tool_frame,
                                     values=["pickup", "delivery", "return"])
    app.cb_task_type.current(1)
    app.cb_task_type.pack(fill='x', pady=2)

    # Go button
    btn_frame = ttk.Frame(app.tool_frame)
    btn_frame.pack(fill='x', pady=10)
    ttk.Button(btn_frame, text=app.t("btn_go"),
               command=app.btn_dispatch_click).pack(side='left', expand=True, fill='x', padx=2)

    # ── Workflow dispatch ─────────────────────────────────────────────────────
    ttk.Separator(app.tool_frame, orient='horizontal').pack(fill='x', pady=4)
    ttk.Label(app.tool_frame, text="📦 Giao hàng đầy đủ (Pickup → Tổ):").pack(anchor='w')

    station_cfg = config.get('station_config', [])
    team_opts = ([f"{t['id']}  —  Wait:{t.get('wait','?')} → Tổ:{t.get('delivery','?')}"
                  for t in station_cfg]
                 if station_cfg else ["(Chưa cấu hình tổ)"])
    app.cb_workflow_team = ttk.Combobox(app.tool_frame, values=team_opts, state='readonly')
    if team_opts:
        app.cb_workflow_team.current(0)
    app.cb_workflow_team.pack(fill='x', pady=2)
    ttk.Button(app.tool_frame, text="📦 Giao cho Tổ này  (Vị trí + Hướng đã chọn)",
               command=app.btn_workflow_dispatch_click).pack(fill='x', pady=2)

    ttk.Separator(app.tool_frame, orient='horizontal').pack(fill='x', pady=4)

    # Auto dispatch
    ttk.Button(app.tool_frame, text=app.t("btn_auto_dispatch"),
               command=app.btn_auto_dispatch_click).pack(fill='x', pady=5)

    # Task log
    ttk.Button(app.tool_frame, text="📋 Log nhiệm vụ xe",
               command=app._show_task_log).pack(fill='x', pady=2)

    # ── Manual control ────────────────────────────────────────────────────────
    ttk.Label(app.tool_frame, text=app.t("lbl_manual")).pack(anchor='w', pady=(10, 0))
    man_frame = ttk.Frame(app.tool_frame)
    man_frame.pack(fill='x', pady=2)
    ttk.Button(man_frame, text=app.t("btn_run"),
               command=lambda: app.send_cmd("run")).pack(side='left', fill='x', expand=True)
    ttk.Button(man_frame, text=app.t("btn_stop"),
               command=lambda: app.send_cmd("stop")).pack(side='left', fill='x', expand=True)

    tk.Button(app.tool_frame, text=app.t("btn_reset_agv"),
              bg="#e67e22", fg="white", font=("Arial", 9, "bold"),
              command=app._btn_reset_agv).pack(pady=(4, 0), fill='x')

    ttk.Button(app.tool_frame, text=app.t("btn_reverse"),
               command=lambda: app.send_cmd("reverse")).pack(pady=5, fill='x')

    # Force Set Position
    ttk.Separator(app.tool_frame, orient='horizontal').pack(pady=10, fill='x')
    ttk.Button(app.tool_frame, text="📍 Force Set Position",
               command=app.btn_force_set_pos).pack(pady=2, fill='x')

    # ── Debug panel ───────────────────────────────────────────────────────────
    ttk.Separator(app.tool_frame, orient='horizontal').pack(pady=5, fill='x')
    lf_debug = ttk.LabelFrame(app.tool_frame, text="🔧 Debug")
    lf_debug.pack(fill='x', pady=2, padx=2)

    def _clear_queue():
        rh = ctx.request_handler
        if rh:
            rh.order_queue.clear()
        if hasattr(app, 'lbl_queue') and app.lbl_queue.winfo_exists():
            app.lbl_queue.config(text="[Empty]")
        print("DEBUG: Order queue cleared.")

    def _clear_all_routes():
        for agv in ctx.agv_list:
            agv.full_path = []
        app.map_widget.draw_map()
        print("DEBUG: All AGV routes cleared.")

    ttk.Button(lf_debug, text="🗑️ Xóa hàng đợi / Clear Queue",
               command=_clear_queue).pack(fill='x', pady=2, padx=4)
    ttk.Button(lf_debug, text="🗑️ Xóa nét đứt / Clear Routes",
               command=_clear_all_routes).pack(fill='x', pady=2, padx=4)

    # ── Active Tasks panel ────────────────────────────────────────────────────
    ttk.Separator(app.tool_frame, orient='horizontal').pack(pady=5, fill='x')
    lf_tasks = ttk.LabelFrame(app.tool_frame, text="🚦 Nhiệm vụ / Active Tasks")
    lf_tasks.pack(fill='x', pady=2, padx=2)

    task_cols = ("AGV", "→Đến", "Loại")
    app.tree_routes = ttk.Treeview(lf_tasks, columns=task_cols, show='headings', height=4)
    app.tree_routes.heading("AGV",  text="AGV")
    app.tree_routes.heading("→Đến", text="→ Đến")
    app.tree_routes.heading("Loại", text="Loại")
    app.tree_routes.column("AGV",  width=55)
    app.tree_routes.column("→Đến", width=55)
    app.tree_routes.column("Loại", width=70)
    app.tree_routes.pack(fill='x', pady=2, padx=4)

    def _cancel_selected_task():
        sel = app.tree_routes.selection()
        if not sel:
            return
        agv_id = str(app.tree_routes.item(sel[0])['values'][0])
        for agv in ctx.agv_list:
            if str(agv.id) == agv_id:
                agv.send_command("stop")
                agv.full_path         = []
                agv.is_navigating     = False
                agv.task_lifecycle    = "free"
                agv.current_task_type = "idle"
                app.map_widget.draw_map()
                app.update_monitor_table()
                print(f"Cancelled task for AGV {agv.id}")
                break

    ttk.Button(lf_tasks, text="❌ Hủy nhiệm vụ / Cancel Task",
               command=_cancel_selected_task).pack(fill='x', pady=2, padx=4)

    # ── Map name label ────────────────────────────────────────────────────────
    map_file = getattr(ctx.planner, 'map_file', '')
    app.lbl_map_name = ttk.Label(app.tool_frame,
                                  text=f"Map: {os.path.basename(map_file)}",
                                  wraplength=180)
    app.lbl_map_name.pack(pady=5)

    app.update_monitor_table()
