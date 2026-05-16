"""
gui/editor_view.py  — Map Editor Tab
--------------------------------------
build_panel(app: AppShell) — xây dựng sidebar Map Editor:
  - Node ID input
  - Tool buttons (Select / Node / Edge / Delete)
  - Undo / Redo
  - Align horizontal / vertical
  - Reset display positions
  - Zone Manager
  - Workflow Manager
  - AGV Position Input
  - Save / Save As / Load map
  - Scan special tasks
  - Map filename + Zoom % entry

Migrate từ main.py App.show_editor_view() (lines 2048–2177).
"""
from __future__ import annotations
import os
import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gui.app_shell import AppShell


def build_panel(app: 'AppShell') -> None:
    """Xây dựng toàn bộ sidebar Editor vào app.tool_frame và show app.map_widget."""
    ctx = app.ctx

    # ── Show map widget ───────────────────────────────────────────────────────
    app.map_widget.pack(fill='both', expand=True)
    app.map_widget.set_tool("select")

    # ── Header ────────────────────────────────────────────────────────────────
    ttk.Label(app.tool_frame, text=app.t("lbl_map_editor"),
              font=("Arial", 12, "bold")).pack(pady=10)

    # ── Node ID input ─────────────────────────────────────────────────────────
    frm_id = ttk.Frame(app.tool_frame)
    frm_id.pack(fill='x', pady=5)
    ttk.Label(frm_id, text=app.t("lbl_next_id")).pack(side='left')
    app.var_node_id = tk.StringVar(value="105")
    ttk.Entry(frm_id, textvariable=app.var_node_id, width=10).pack(side='right')

    # ── Tool buttons ──────────────────────────────────────────────────────────
    ttk.Button(app.tool_frame, text=app.t("btn_tool_select"),
               command=lambda: app.set_map_tool("select")).pack(pady=2, fill='x')
    ttk.Button(app.tool_frame, text=app.t("btn_tool_node"),
               command=lambda: app.set_map_tool("node")).pack(pady=2, fill='x')
    ttk.Button(app.tool_frame, text=app.t("btn_tool_edge"),
               command=lambda: app.set_map_tool("edge")).pack(pady=2, fill='x')
    ttk.Button(app.tool_frame, text=app.t("btn_tool_delete"),
               command=app.map_widget.delete_selected).pack(pady=2, fill='x')

    ttk.Separator(app.tool_frame, orient='horizontal').pack(pady=6, fill='x')

    # ── Undo / Redo ───────────────────────────────────────────────────────────
    frm_undo = ttk.Frame(app.tool_frame)
    frm_undo.pack(fill='x', pady=2)
    ttk.Button(frm_undo, text=app.t("btn_undo"),
               command=app.map_widget.undo).pack(side='left', fill='x', expand=True, padx=(0, 1))
    ttk.Button(frm_undo, text=app.t("btn_redo"),
               command=app.map_widget.redo).pack(side='left', fill='x', expand=True, padx=(1, 0))

    # ── Alignment ─────────────────────────────────────────────────────────────
    frm_align = ttk.Frame(app.tool_frame)
    frm_align.pack(fill='x', pady=2)
    ttk.Button(frm_align, text="↔ Căn ngang",
               command=app.map_widget.align_horizontal).pack(
                   side='left', fill='x', expand=True, padx=(0, 1))
    ttk.Button(frm_align, text="↕ Căn dọc",
               command=app.map_widget.align_vertical).pack(
                   side='left', fill='x', expand=True, padx=(1, 0))

    ttk.Button(app.tool_frame, text="🔄 Reset vị trí hiển thị",
               command=app.map_widget.reset_display_positions).pack(pady=2, fill='x')

    ttk.Separator(app.tool_frame, orient='horizontal').pack(pady=6, fill='x')

    # ── Zone / Workflow / Position ────────────────────────────────────────────
    ttk.Button(app.tool_frame, text="⬡ Zone Manager",
               command=lambda: app.map_widget.open_zone_manager_dialog(
                   'config/zones.json')).pack(pady=2, fill='x')

    ttk.Button(app.tool_frame, text="⚡ Workflow",
               command=app.open_workflow_manager_dialog).pack(pady=2, fill='x')

    ttk.Button(app.tool_frame, text="📍 Nhập vị trí AGV",
               command=app._open_position_input).pack(pady=2, fill='x')

    ttk.Separator(app.tool_frame, orient='horizontal').pack(pady=6, fill='x')

    # ── Map I/O ───────────────────────────────────────────────────────────────
    ttk.Button(app.tool_frame, text=app.t("btn_save_map"),
               command=ctx.planner.save_map).pack(pady=2, fill='x')
    ttk.Button(app.tool_frame, text=app.t("btn_save_as"),
               command=app.btn_save_as).pack(pady=2, fill='x')
    ttk.Button(app.tool_frame, text=app.t("btn_load_map"),
               command=app.btn_load_map).pack(pady=2, fill='x')

    ttk.Button(app.tool_frame, text="🔍 Xem nhiệm vụ ĐB",
               command=app.btn_scan_special_tasks).pack(pady=2, fill='x')

    ttk.Separator(app.tool_frame, orient='horizontal').pack(pady=4, fill='x')

    # ── Map filename ──────────────────────────────────────────────────────────
    map_file = getattr(ctx.planner, 'map_file', '')
    app.lbl_map_name_editor = ttk.Label(app.tool_frame,
                                         text=f"📄 {os.path.basename(map_file)}",
                                         wraplength=190,
                                         font=("Segoe UI", 8),
                                         foreground="#2980b9")
    app.lbl_map_name_editor.pack(pady=(2, 0))

    # ── Zoom % ────────────────────────────────────────────────────────────────
    frm_zoom = ttk.Frame(app.tool_frame)
    frm_zoom.pack(fill='x', pady=4)
    ttk.Label(frm_zoom, text="🔍 Zoom:").pack(side='left')
    app._var_zoom_pct = tk.StringVar(value=f"{int(app.map_widget.scale * 100)}")
    ent_zoom = ttk.Entry(frm_zoom, textvariable=app._var_zoom_pct, width=6)
    ent_zoom.pack(side='left', padx=2)
    ttk.Label(frm_zoom, text="%").pack(side='left')

    def _apply_zoom_entry(event=None):
        try:
            pct       = float(app._var_zoom_pct.get().replace('%', ''))
            new_scale = max(0.05, min(20.0, pct / 100.0))
            app.map_widget.scale = new_scale
            ctx.config.setdefault('map', {})['zoom']     = new_scale
            ctx.config.setdefault('map', {})['offset_x'] = app.map_widget.offset_x
            ctx.config.setdefault('map', {})['offset_y'] = app.map_widget.offset_y
            app.save_config()
            app.map_widget.draw_map()
            app._var_zoom_pct.set(f"{int(new_scale * 100)}")
        except ValueError:
            pass

    ent_zoom.bind("<Return>",   _apply_zoom_entry)
    ent_zoom.bind("<FocusOut>", _apply_zoom_entry)

    def _on_zoom_changed(new_scale):
        if hasattr(app, '_var_zoom_pct'):
            app._var_zoom_pct.set(f"{int(new_scale * 100)}")
        ctx.config.setdefault('map', {})['zoom']     = new_scale
        ctx.config.setdefault('map', {})['offset_x'] = app.map_widget.offset_x
        ctx.config.setdefault('map', {})['offset_y'] = app.map_widget.offset_y

    app.map_widget.on_zoom_changed = _on_zoom_changed

    # Keyboard shortcuts for undo/redo when editor is active
    app.bind("<Control-z>", lambda _e: app.map_widget.undo())
    app.bind("<Control-Z>", lambda _e: app.map_widget.undo())
    app.bind("<Control-y>", lambda _e: app.map_widget.redo())
    app.bind("<Control-Y>", lambda _e: app.map_widget.redo())
