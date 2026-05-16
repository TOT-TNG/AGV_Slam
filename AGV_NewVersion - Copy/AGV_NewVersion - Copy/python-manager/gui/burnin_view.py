"""
gui/burnin_view.py  — Burn-in / Continuous Test Tab
------------------------------------------------------
build_panel(app: AppShell) — xây dựng full-width burnin panel:
  - Title + subtitle
  - Controls bar: AGV selector, loop count, delay between loops
  - Status bar: status / loop / tag labels
  - PanedWindow:
      LEFT  — scrollable action table (tag | action | value | delete)
      RIGHT — dark log panel
  - Bottom toolbar: Add row / Clear all / Start / Stop

Các phương thức _bi_* sống trong AppShell (app_shell.py).
Migrate từ main.py App.show_burnin_view() (lines 4991–5127).
"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gui.app_shell import AppShell


def build_panel(app: 'AppShell') -> None:
    """Xây dựng burnin panel vào app.content_frame (full width)."""
    ctx = app.ctx

    app.frm_burnin = ttk.Frame(app.content_frame, padding=6)
    app.frm_burnin.pack(fill='both', expand=True)

    # ── Title ─────────────────────────────────────────────────────────────────
    ttk.Label(app.frm_burnin, text="🔄 Chạy thử liên tục",
              font=("Arial", 14, "bold")).pack(anchor='w', pady=(0, 2))
    ttk.Label(app.frm_burnin,
              text="Xây dựng chuỗi lệnh per-thẻ · Hệ thống gửi plan_data trực tiếp qua MQTT · Lặp N vòng",
              foreground="#666", font=("Arial", 9)).pack(anchor='w')
    ttk.Separator(app.frm_burnin, orient='horizontal').pack(fill='x', pady=6)

    # ── Controls bar ──────────────────────────────────────────────────────────
    ctrl = ttk.Frame(app.frm_burnin)
    ctrl.pack(fill='x', pady=(0, 4))

    ttk.Label(ctrl, text="AGV:").pack(side='left')
    agv_ids = [str(a.id) for a in ctx.agv_list]
    app._bi_agv_var = tk.StringVar(value=agv_ids[0] if agv_ids else "")
    ttk.Combobox(ctrl, textvariable=app._bi_agv_var,
                 values=agv_ids, state='readonly', width=8).pack(side='left', padx=(4, 12))

    ttk.Label(ctrl, text="Số vòng:").pack(side='left')
    app._bi_loops_var = tk.IntVar(value=10)
    ttk.Spinbox(ctrl, from_=1, to=9999, textvariable=app._bi_loops_var,
                width=7).pack(side='left', padx=(4, 12))

    ttk.Label(ctrl, text="Chờ giữa vòng (s):").pack(side='left')
    app._bi_delay_var = tk.IntVar(value=3)
    ttk.Spinbox(ctrl, from_=0, to=300, textvariable=app._bi_delay_var,
                width=6).pack(side='left', padx=(4, 0))

    # ── Status bar ────────────────────────────────────────────────────────────
    sbar = ttk.Frame(app.frm_burnin)
    sbar.pack(fill='x', pady=(0, 4))
    app._bi_status_var = tk.StringVar(value="Chờ cấu hình…")
    app._bi_loop_var   = tk.StringVar(value="—")
    app._bi_tag_var    = tk.StringVar(value="—")
    for lbl_text, var in [("Trạng thái:", app._bi_status_var),
                           ("Vòng:",       app._bi_loop_var),
                           ("Thẻ:",        app._bi_tag_var)]:
        ttk.Label(sbar, text=lbl_text, foreground="#555").pack(side='left', padx=(0, 2))
        ttk.Label(sbar, textvariable=var, font=("Arial", 9, "bold"),
                  foreground="#1a6fa8").pack(side='left', padx=(0, 14))

    # ── Main paned: table LEFT · log RIGHT ────────────────────────────────────
    pw = tk.PanedWindow(app.frm_burnin, orient='horizontal',
                        sashwidth=5, bg="#cccccc")
    pw.pack(fill='both', expand=True)

    # ─── LEFT: action table ───────────────────────────────────────────────────
    tbl_frame = ttk.Frame(pw, padding=4)
    pw.add(tbl_frame, minsize=480)

    # Column headers
    hdr = ttk.Frame(tbl_frame)
    hdr.pack(fill='x')
    ttk.Label(hdr, text="#",        width=3,  anchor='center',
              font=("Arial", 9, "bold")).pack(side='left', padx=2)
    ttk.Label(hdr, text="Thẻ",     width=7,  anchor='center',
              font=("Arial", 9, "bold")).pack(side='left', padx=2)
    ttk.Label(hdr, text="Hành động", width=32, anchor='w',
              font=("Arial", 9, "bold")).pack(side='left', padx=2)
    ttk.Label(hdr, text="Giá trị", width=8,  anchor='center',
              font=("Arial", 9, "bold")).pack(side='left', padx=2)
    ttk.Separator(tbl_frame, orient='horizontal').pack(fill='x', pady=2)

    # Scrollable canvas for rows
    canvas_wrap = ttk.Frame(tbl_frame)
    canvas_wrap.pack(fill='both', expand=True)
    app._bi_canvas = tk.Canvas(canvas_wrap, highlightthickness=0, bg="#f8f8f8")
    sb_y = ttk.Scrollbar(canvas_wrap, orient='vertical', command=app._bi_canvas.yview)
    app._bi_canvas.configure(yscrollcommand=sb_y.set)
    sb_y.pack(side='right', fill='y')
    app._bi_canvas.pack(side='left', fill='both', expand=True)

    app._bi_rows_frame  = ttk.Frame(app._bi_canvas)
    app._bi_canvas_win  = app._bi_canvas.create_window(
        (0, 0), window=app._bi_rows_frame, anchor='nw')

    def _on_rows_configure(e):
        app._bi_canvas.configure(scrollregion=app._bi_canvas.bbox('all'))
        app._bi_canvas.itemconfig(app._bi_canvas_win,
                                   width=app._bi_canvas.winfo_width())
    app._bi_rows_frame.bind('<Configure>', _on_rows_configure)
    app._bi_canvas.bind('<Configure>',
        lambda e: app._bi_canvas.itemconfig(app._bi_canvas_win, width=e.width))

    def _mw(e):
        app._bi_canvas.yview_scroll(int(-1 * (e.delta / 120)), 'units')
    app._bi_canvas.bind_all('<MouseWheel>', _mw)

    app._bi_rows = []

    # Bottom toolbar for table
    tbar = ttk.Frame(tbl_frame)
    tbar.pack(fill='x', pady=(4, 0))
    ttk.Button(tbar, text="➕ Thêm hành động",
               command=lambda: app._bi_add_row()).pack(side='left', padx=(0, 6))
    ttk.Button(tbar, text="🗑 Xóa tất cả",
               command=app._bi_clear_rows).pack(side='left', padx=(0, 20))
    app._bi_btn_start = ttk.Button(tbar, text="▶ Bắt đầu", command=app._bi_start)
    app._bi_btn_start.pack(side='left', padx=(0, 6))
    app._bi_btn_stop  = ttk.Button(tbar, text="⏹ Dừng",
                                    command=app._bi_stop, state='disabled')
    app._bi_btn_stop.pack(side='left')

    # ─── RIGHT: log ───────────────────────────────────────────────────────────
    right = ttk.Frame(pw, padding=4)
    pw.add(right)

    log_lf = ttk.LabelFrame(right, text="📋 Nhật ký", padding=4)
    log_lf.pack(fill='both', expand=True)
    app._bi_log = tk.Text(log_lf, font=("Courier New", 9), wrap='word',
                           bg="#1e1e1e", fg="#d4d4d4",
                           state='disabled', height=20)
    log_sb = ttk.Scrollbar(log_lf, orient='vertical', command=app._bi_log.yview)
    app._bi_log.configure(yscrollcommand=log_sb.set)
    log_sb.pack(side='right', fill='y')
    app._bi_log.pack(fill='both', expand=True)
    ttk.Button(right, text="🗑 Xóa nhật ký",
               command=app._bi_clear_log).pack(anchor='e', pady=(4, 0))

    app._bi_state = {'running': False}

    # Pre-populate example rows
    for tag, act_idx, val in [
        (109, 3, 60),    # SPEED 60
        (109, 0, 0),     # RUN
        (107, 1, 0),     # TURN_L
        (43,  3, 120),   # SPEED 120
        (43,  0, 0),     # RUN
    ]:
        app._bi_add_row(tag, act_idx, val)
