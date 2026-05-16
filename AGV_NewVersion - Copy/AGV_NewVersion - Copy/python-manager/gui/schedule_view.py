"""
gui/schedule_view.py  — Schedule Tab
--------------------------------------
build_panel(app: AppShell) — xây dựng full-width schedule panel:
  - Tiêu đề
  - Treeview danh sách nhiệm vụ (Time / Target / Trips / Status)
  - Controls: thêm / xóa / reset pending

Tất cả logic (save_config) inline — không cần thêm phương thức vào AppShell.
Migrate từ main.py App.show_schedule_view() (lines 4860–4970).
"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gui.app_shell import AppShell


def build_panel(app: 'AppShell') -> None:
    """Xây dựng schedule panel vào app.content_frame (full width)."""
    ctx    = app.ctx
    config = ctx.config

    app.frm_schedule = ttk.Frame(app.content_frame, padding=20)
    app.frm_schedule.pack(fill='both', expand=True)

    ttk.Label(app.frm_schedule, text=app.t("title_schedule"),
              font=("Arial", 16, "bold")).pack(pady=(0, 10))

    # ── Task table ────────────────────────────────────────────────────────────
    tbl_frame = ttk.Frame(app.frm_schedule)
    tbl_frame.pack(fill='both', expand=True)

    cols = ("Time", "Target", "Trips", "Status")
    tree = ttk.Treeview(tbl_frame, columns=cols, show='headings')
    tree.heading("Time",   text=app.t("col_sch_time"))
    tree.heading("Target", text=app.t("col_sch_target"))
    tree.heading("Trips",  text=app.t("col_sch_trips"))
    tree.heading("Status", text=app.t("col_sch_status"))
    tree.column("Time",   width=90)
    tree.column("Target", width=300)
    tree.column("Trips",  width=80)
    tree.column("Status", width=110)

    sb = ttk.Scrollbar(tbl_frame, orient='vertical', command=tree.yview)
    tree.configure(yscrollcommand=sb.set)
    sb.pack(side='right', fill='y')
    tree.pack(fill='both', expand=True)

    # ── Helpers ───────────────────────────────────────────────────────────────
    def get_target_label(team_id):
        for st in config.get('station_config', []):
            if st['id'] == team_id:
                return f"Tổ {st['id']}: {st['name']} (→ Thẻ {st['delivery']})"
        return str(team_id)

    tasks = config.get('schedule_tasks', [])
    for t in tasks:
        tree.insert("", "end", values=(
            t['time'], get_target_label(t['target']),
            t.get('trips', 1), t['status']))

    # ── Controls ──────────────────────────────────────────────────────────────
    frm = ttk.Frame(app.frm_schedule)
    frm.pack(fill='x', pady=10)

    ttk.Label(frm, text="Giờ (HH:MM):").pack(side='left')
    ent_time = ttk.Entry(frm, width=8)
    ent_time.pack(side='left', padx=5)

    ttk.Label(frm, text="Đích / Tổ:").pack(side='left')
    station_options = [
        f"Tổ {st['id']}: {st['name']} (→ Thẻ {st['delivery']})"
        for st in config.get('station_config', [])
    ]
    cb_target = ttk.Combobox(frm, values=station_options, width=30, state='readonly')
    if station_options:
        cb_target.current(0)
    cb_target.pack(side='left', padx=5)

    ttk.Label(frm, text=app.t("lbl_trips")).pack(side='left')
    ent_trips = ttk.Entry(frm, width=5)
    ent_trips.insert(0, "1")
    ent_trips.pack(side='left', padx=5)

    def add_task():
        t_str    = ent_time.get().strip()
        sel      = cb_target.get()
        trip_str = ent_trips.get()
        if not t_str or not sel:
            return
        try:
            team_id = int(sel.split(":")[0].replace("Tổ", "").strip())
        except (ValueError, IndexError):
            messagebox.showerror("Error", "Invalid selection")
            return
        trips    = int(trip_str) if trip_str.isdigit() else 1
        new_task = {"time": t_str, "target": team_id, "trips": trips,
                    "status": "pending", "type": "delivery"}
        tasks.append(new_task)
        config['schedule_tasks'] = tasks
        app.save_config()
        tree.insert("", "end", values=(t_str, get_target_label(team_id), trips, "pending"))

    def del_task():
        sel = tree.selection()
        if sel:
            idx = tree.index(sel[0])
            del tasks[idx]
            config['schedule_tasks'] = tasks
            app.save_config()
            tree.delete(sel[0])

    def reset_all():
        if not messagebox.askyesno("Xác nhận",
                                   "Reset trạng thái tất cả nhiệm vụ về 'pending'?"):
            return
        for t in tasks:
            t['status'] = 'pending'
        config['schedule_tasks'] = tasks
        app.save_config()
        for item in tree.get_children():
            tree.delete(item)
        for t in tasks:
            tree.insert("", "end", values=(
                t['time'], get_target_label(t['target']),
                t.get('trips', 1), t['status']))

    ttk.Button(frm, text=app.t("btn_add_task"), command=add_task).pack(side='left', padx=10)
    ttk.Button(frm, text=app.t("btn_del_task"), command=del_task).pack(side='left', padx=4)
    ttk.Button(frm, text="🔄 Reset pending",   command=reset_all).pack(side='left', padx=4)
