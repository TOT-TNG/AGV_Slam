"""
gui/stats_view.py  — Operational Statistics Tab
-------------------------------------------------
build_panel(app: AppShell) — xây dựng full-width stats panel:
  - Header + info label
  - Date range filter (ent_date_from, ent_date_to)
  - Refresh / Generate Dummy / Clear Data buttons
  - Scrollable canvas (canvas_stats) for charts

Charts được vẽ bởi app.draw_charts() trong app_shell.py.
Migrate từ main.py App.show_stats_view() (lines 3183–3231).
"""
from __future__ import annotations
import datetime
import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gui.app_shell import AppShell


def build_panel(app: 'AppShell') -> None:
    """Xây dựng stats panel vào app.content_frame (full width, no tool_frame)."""
    app.frm_stats = ttk.Frame(app.content_frame, padding=20)
    app.frm_stats.pack(fill='both', expand=True)

    # ── Header & Controls (fixed at top) ─────────────────────────────────────
    frm_top = ttk.Frame(app.frm_stats)
    frm_top.pack(fill='x', side='top')

    ttk.Label(frm_top, text=app.t("lbl_op_stats"),
              font=("Arial", 18, "bold")).pack(side='left', pady=10)

    ttk.Label(frm_top,
              text="Ghi chú: Tên trạm được cấu hình trong Cài đặt -> Stations",
              font=("Arial", 8, "italic"),
              foreground="gray").pack(side='left', padx=20)

    # ── Date filter (packed to bottom of frm_top) ────────────────────────────
    frm_filter = ttk.Frame(frm_top)
    frm_filter.pack(fill='x', pady=5, side='bottom')

    ttk.Label(frm_filter, text=app.t("lbl_from")).pack(side='left')
    app.ent_date_from = ttk.Entry(frm_filter, width=12)
    app.ent_date_from.insert(0, datetime.datetime.now().strftime('%Y-%m-%d'))
    app.ent_date_from.pack(side='left', padx=5)

    ttk.Label(frm_filter, text=app.t("lbl_to")).pack(side='left')
    app.ent_date_to = ttk.Entry(frm_filter, width=12)
    app.ent_date_to.insert(0, datetime.datetime.now().strftime('%Y-%m-%d'))
    app.ent_date_to.pack(side='left', padx=5)

    ttk.Button(frm_filter, text=app.t("btn_refresh"),
               command=app.draw_charts).pack(side='left')
    ttk.Button(frm_filter, text=app.t("btn_gen_data"),
               command=app.generate_dummy_data).pack(side='right', padx=10)
    ttk.Button(frm_filter, text=app.t("btn_clear_data"),
               command=app.clear_simulation_data).pack(side='right', padx=2)

    # ── Scrollable canvas for charts ─────────────────────────────────────────
    app.stats_container = ttk.Frame(app.frm_stats)
    app.stats_container.pack(fill='both', expand=True, pady=5)

    app.canvas_stats = tk.Canvas(app.stats_container, bg="white")
    app.scrollbar_stats = ttk.Scrollbar(app.stats_container, orient="vertical",
                                         command=app.canvas_stats.yview)
    app.canvas_stats.configure(yscrollcommand=app.scrollbar_stats.set)

    app.scrollbar_stats.pack(side="right", fill="y")
    app.canvas_stats.pack(side="left", fill="both", expand=True)

    app.draw_charts()
