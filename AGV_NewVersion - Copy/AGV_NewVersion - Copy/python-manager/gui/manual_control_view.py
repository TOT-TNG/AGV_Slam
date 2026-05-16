"""
gui/manual_control_view.py  — Manual Control Tab
--------------------------------------------------
build_panel(app: AppShell) — xây dựng layout:
  - frm_manual (right, fixed 320px) với scrollable inner
  - map_widget (left, fill remaining)

Controls bên trong:
  - AGV selector + status label + Set Position button
  - Emergency Stop + Reset Arduino
  - Speed slider + Set button
  - Direction (Tiến / Lùi)
  - Turn left / right + Rotate 180
  - DEBA (chạy đến 1 thẻ kế tiếp rồi dừng)
  - Lidar ON/OFF
  - Brake ON/OFF
  - Lights (Vàng / Xanh / Tắt)
  - Sound / Buzzer
  - Hook raise / lower
  - Raw command entry

Migrate từ main.py App.show_manual_control_view() (lines 2867–3180).
"""
from __future__ import annotations
import json
import tkinter as tk
from tkinter import ttk, messagebox
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gui.app_shell import AppShell


def build_panel(app: 'AppShell') -> None:
    """Xây dựng panel điều khiển thủ công bên phải + map_widget bên trái."""
    ctx = app.ctx

    # ── Right panel (fixed width) ─────────────────────────────────────────────
    app.frm_manual = tk.Frame(app.content_frame, bg="#f0f0f0", width=320)
    app.frm_manual.pack(side='right', fill='y')
    app.frm_manual.pack_propagate(False)

    # ── Map widget (left, fills remaining) ────────────────────────────────────
    app.map_widget.pack(side='left', fill='both', expand=True)
    app.map_widget.set_tool("monitor")

    # ── Scrollable inner frame ────────────────────────────────────────────────
    canvas_c   = tk.Canvas(app.frm_manual, bg="#f0f0f0", highlightthickness=0)
    scrollbar_c = ttk.Scrollbar(app.frm_manual, orient='vertical', command=canvas_c.yview)
    canvas_c.configure(yscrollcommand=scrollbar_c.set)
    scrollbar_c.pack(side='right', fill='y')
    canvas_c.pack(side='left', fill='both', expand=True)

    inner   = tk.Frame(canvas_c, bg="#f0f0f0")
    inn_win = canvas_c.create_window((0, 0), window=inner, anchor='nw')

    def _on_inner_configure(e):
        canvas_c.configure(scrollregion=canvas_c.bbox('all'))
        canvas_c.itemconfig(inn_win, width=canvas_c.winfo_width())

    inner.bind('<Configure>', _on_inner_configure)
    canvas_c.bind('<Configure>', lambda e: canvas_c.itemconfig(inn_win, width=e.width))
    canvas_c.bind('<MouseWheel>',
                  lambda e: canvas_c.yview_scroll(int(-1 * (e.delta / 120)), 'units'))

    pad = {'padx': 8, 'pady': 3}

    # ── Title ─────────────────────────────────────────────────────────────────
    tk.Label(inner, text="🕹️  Điều Khiển Thủ Công", font=("Arial", 12, "bold"),
             bg="#2c3e50", fg="white").pack(fill='x', pady=(0, 4))

    # ── AGV selector + status ─────────────────────────────────────────────────
    frm_agv = tk.LabelFrame(inner, text="AGV & Vị trí", bg="#f0f0f0",
                             font=("Arial", 9, "bold"))
    frm_agv.pack(fill='x', **pad)

    app._manual_agv_var = tk.StringVar()
    agv_ids = [a.id for a in ctx.agv_list]
    if agv_ids:
        app._manual_agv_var.set(agv_ids[0])

    cb_agv = ttk.Combobox(frm_agv, textvariable=app._manual_agv_var,
                           values=agv_ids, state='readonly', width=14)
    cb_agv.grid(row=0, column=0, padx=5, pady=4, sticky='w')

    app._lbl_manual_status = tk.Label(frm_agv, text="—", bg="#f0f0f0",
                                       font=("Arial", 8), fg="#555555", justify='left')
    app._lbl_manual_status.grid(row=0, column=1, padx=4, sticky='w')

    def _get_agv():
        sel = app._manual_agv_var.get()
        return next((a for a in ctx.agv_list if a.id == sel), None)

    def _open_set_pos():
        app.map_widget.on_apply_positions = app._manual_apply_positions
        app.map_widget.open_position_input()
        btn_setpos.config(state='disabled', text="Đang đặt…")

    btn_setpos = tk.Button(frm_agv, text="📍 Đặt vị trí AGV",
                            bg="#2980b9", fg="white", font=("Arial", 8, "bold"),
                            command=_open_set_pos)
    btn_setpos.grid(row=1, column=0, columnspan=2, padx=5, pady=(0, 4), sticky='ew')

    def _refresh_status(*_):
        agv = _get_agv()
        if agv:
            tag     = agv.current_tag if agv.current_tag else "—"
            bat     = getattr(agv, 'battery', '?')
            err     = getattr(agv, 'error_code', 0)
            err_str = f" ⚠{err}" if err else ""
            app._lbl_manual_status.config(
                text=f"Tag:{tag}  Pin:{bat}%  {agv.status}{err_str}")
        if hasattr(app, 'frm_manual') and app.frm_manual.winfo_exists():
            app.after(800, _refresh_status)

    cb_agv.bind('<<ComboboxSelected>>', _refresh_status)
    _refresh_status()

    # ── Action senders ────────────────────────────────────────────────────────
    def _send_action(action_code, value=0):
        agv = _get_agv()
        if not agv:
            return
        payload = json.dumps({"c": "action", "a": action_code, "v": value})
        agv.mqtt.publish(agv.topic_instant, payload)
        print(f"[MANUAL] {agv.id} ← action={action_code} v={value}")

    _manual_dir = {"v": "toi"}

    def _send_cmd(cmd_str):
        agv = _get_agv()
        if not agv:
            return
        if cmd_str == "deba":
            spd     = app._manual_speed_var.get()
            dir_str = "fwd" if _manual_dir["v"] == "toi" else "bwd"
            payload = json.dumps({"c": "run", "v": int(spd), "p": dir_str})
            agv.mqtt.publish(agv.topic_instant, payload)
            print(f"[MANUAL] {agv.id} ← deba dir={_manual_dir['v']} spd={spd}")
            app.map_widget.start_manual_move(agv.id, _manual_dir["v"], spd, agv.current_tag)
            return
        if cmd_str == "stop":
            app.map_widget.stop_manual_anim(agv.id)
        agv.send_command(cmd_str)
        print(f"[MANUAL] {agv.id} ← cmd={cmd_str}")

    # ── Emergency stop + Reset ────────────────────────────────────────────────
    tk.Button(inner, text="⛔  DỪNG KHẨN CẤP  ⛔",
              font=("Arial", 11, "bold"), bg="#c0392b", fg="white", height=2,
              command=lambda: _send_cmd("stop")).pack(fill='x', padx=8, pady=(6, 2))

    def _do_reset():
        agv = _get_agv()
        if not agv:
            return
        if messagebox.askyesno("Reset Arduino",
                               f"Reset Arduino của {agv.id}?\n"
                               "Xe sẽ khởi động lại, mất kết nối ~3 giây."):
            agv.send_command("reset")
            print(f"[RESET] Sent reset to {agv.id}")

    tk.Button(inner, text="🔄  Reset / Xóa lỗi Arduino",
              font=("Arial", 9, "bold"), bg="#e67e22", fg="white",
              command=_do_reset).pack(fill='x', padx=8, pady=(0, 6))

    # ── Speed ─────────────────────────────────────────────────────────────────
    frm_spd = tk.LabelFrame(inner, text="Tốc độ (PWM 0–255)", bg="#f0f0f0",
                             font=("Arial", 9, "bold"))
    frm_spd.pack(fill='x', **pad)
    app._manual_speed_var = tk.IntVar(value=150)
    tk.Scale(frm_spd, from_=0, to=255, orient='horizontal',
             variable=app._manual_speed_var, length=180, bg="#f0f0f0").pack(side='left', padx=5)
    tk.Label(frm_spd, textvariable=app._manual_speed_var, width=4,
             bg="#f0f0f0", font=("Arial", 10, "bold")).pack(side='left')
    tk.Button(frm_spd, text="Đặt",
              command=lambda: _send_action(4, app._manual_speed_var.get()),
              bg="#2980b9", fg="white", width=6).pack(side='left', padx=4, pady=4)

    # ── Direction + Turns ─────────────────────────────────────────────────────
    frm_move = tk.LabelFrame(inner, text="Di chuyển", bg="#f0f0f0",
                              font=("Arial", 9, "bold"))
    frm_move.pack(fill='x', **pad)

    frm_dir = tk.Frame(frm_move, bg="#f0f0f0")
    frm_dir.pack(fill='x', pady=4)

    def _set_dir_fwd():
        _manual_dir["v"] = "toi"
        btn_dir_fwd.config(relief='sunken')
        btn_dir_bwd.config(relief='raised')
        _send_action(7)

    def _set_dir_bwd():
        _manual_dir["v"] = "lui"
        btn_dir_bwd.config(relief='sunken')
        btn_dir_fwd.config(relief='raised')
        _send_action(8)

    btn_dir_fwd = tk.Button(frm_dir, text="⬆ Chiều Tiến", width=14,
                             bg="#27ae60", fg="white", font=("Arial", 9, "bold"),
                             relief='sunken', command=_set_dir_fwd)
    btn_dir_fwd.pack(side='left', padx=4)
    btn_dir_bwd = tk.Button(frm_dir, text="⬇ Chiều Lùi", width=14,
                             bg="#8e44ad", fg="white", font=("Arial", 9, "bold"),
                             command=_set_dir_bwd)
    btn_dir_bwd.pack(side='left', padx=4)

    def _send_turn(action_code, turn_dir):
        _send_action(action_code)
        agv = _get_agv()
        if agv:
            app.map_widget.start_manual_turn(agv.id, turn_dir)

    frm_turn = tk.Frame(frm_move, bg="#f0f0f0")
    frm_turn.pack(fill='x', pady=4)
    tk.Button(frm_turn, text="↰  Quay Trái", width=14, bg="#f39c12", fg="white",
              font=("Arial", 9, "bold"),
              command=lambda: _send_turn(6, 'L')).pack(side='left', padx=4)
    tk.Button(frm_turn, text="↱  Quay Phải", width=14, bg="#f39c12", fg="white",
              font=("Arial", 9, "bold"),
              command=lambda: _send_turn(5, 'R')).pack(side='left', padx=4)
    tk.Button(frm_move, text="↺  Quay 180°", width=14, bg="#e67e22", fg="white",
              font=("Arial", 9, "bold"),
              command=lambda: _send_action(9)).pack(padx=4, pady=(0, 4))

    # ── DEBA ──────────────────────────────────────────────────────────────────
    frm_deba = tk.LabelFrame(inner, text="DEBA — Chạy đến 1 thẻ kế tiếp rồi DỪNG",
                              bg="#fef9e7", font=("Arial", 9, "bold"), fg="#7d6608")
    frm_deba.pack(fill='x', **pad)
    tk.Label(frm_deba,
             text="⚠ Khác lệnh chạy thường: Xe đi đến\n"
                  "đúng 1 thẻ RFID kế tiếp rồi dừng hẳn.\n"
                  "Vị trí bản đồ cập nhật tự động qua MQTT.",
             bg="#fef9e7", fg="#7d6608", font=("Arial", 8),
             justify='left').pack(anchor='w', padx=6, pady=2)
    tk.Button(frm_deba, text="▶  Gửi lệnh DEBA",
              font=("Arial", 10, "bold"), bg="#d4ac0d", fg="white",
              command=lambda: _send_cmd("deba")).pack(fill='x', padx=6, pady=(0, 6))

    # ── Lidar ─────────────────────────────────────────────────────────────────
    frm_lid = tk.LabelFrame(inner, text="Cảm biến Lidar / Vật cản", bg="#f0f0f0",
                             font=("Arial", 9, "bold"))
    frm_lid.pack(fill='x', **pad)
    frm_lid_btns = tk.Frame(frm_lid, bg="#f0f0f0")
    frm_lid_btns.pack(fill='x', pady=4)
    tk.Button(frm_lid_btns, text="🟢 BẬT Lidar", width=14,
              bg="#1abc9c", fg="white", font=("Arial", 9, "bold"),
              command=lambda: _send_action(21)).pack(side='left', padx=4)
    tk.Button(frm_lid_btns, text="🔴 TẮT Lidar", width=14,
              bg="#95a5a6", fg="white", font=("Arial", 9, "bold"),
              command=lambda: _send_action(20)).pack(side='left', padx=4)

    # ── Brake ─────────────────────────────────────────────────────────────────
    frm_brk = tk.LabelFrame(inner, text="Phanh (Brake)", bg="#f0f0f0",
                             font=("Arial", 9, "bold"))
    frm_brk.pack(fill='x', **pad)
    frm_brk_btns = tk.Frame(frm_brk, bg="#f0f0f0")
    frm_brk_btns.pack(fill='x', pady=4)
    tk.Button(frm_brk_btns, text="🔒 Phanh ON",  width=14, bg="#7f8c8d", fg="white",
              font=("Arial", 9),
              command=lambda: _send_action(28)).pack(side='left', padx=4)
    tk.Button(frm_brk_btns, text="🔓 Phanh OFF", width=14, bg="#bdc3c7", fg="black",
              font=("Arial", 9),
              command=lambda: _send_action(29)).pack(side='left', padx=4)

    # ── Lights ────────────────────────────────────────────────────────────────
    frm_den = tk.LabelFrame(inner, text="Đèn hiệu", bg="#f0f0f0",
                             font=("Arial", 9, "bold"))
    frm_den.pack(fill='x', **pad)
    frm_den_btns = tk.Frame(frm_den, bg="#f0f0f0")
    frm_den_btns.pack(fill='x', pady=4)
    tk.Button(frm_den_btns, text="🟡 Vàng", width=8, bg="#f1c40f", fg="black",
              font=("Arial", 9), command=lambda: _send_action(32)).pack(side='left', padx=4)
    tk.Button(frm_den_btns, text="🟢 Xanh", width=8, bg="#2ecc71", fg="white",
              font=("Arial", 9), command=lambda: _send_action(33)).pack(side='left', padx=4)
    tk.Button(frm_den_btns, text="⬛ Tắt",  width=8, bg="#555555", fg="white",
              font=("Arial", 9), command=lambda: _send_action(34)).pack(side='left', padx=4)

    # ── Sound ─────────────────────────────────────────────────────────────────
    frm_nhac = tk.LabelFrame(inner, text="Âm thanh (Buzzer/Nhạc)", bg="#f0f0f0",
                              font=("Arial", 9, "bold"))
    frm_nhac.pack(fill='x', **pad)
    nhac_items = [("▶ Khởi động", 22), ("■ Dừng nhạc", 23),
                  ("🔔 Xin cấp liệu", 24), ("🚪 Mở cửa", 25),
                  ("↗ Xin rẽ", 26), ("🔕 Tắt nhạc", 27)]
    frm_n1 = tk.Frame(frm_nhac, bg="#f0f0f0"); frm_n1.pack(fill='x', pady=2)
    frm_n2 = tk.Frame(frm_nhac, bg="#f0f0f0"); frm_n2.pack(fill='x', pady=(0, 4))
    for i, (lbl, code) in enumerate(nhac_items):
        parent = frm_n1 if i < 3 else frm_n2
        tk.Button(parent, text=lbl, width=12, bg="#ecf0f1", fg="#2c3e50",
                  font=("Arial", 8),
                  command=lambda c=code: _send_action(c)).pack(side='left', padx=3)

    # ── Hook ──────────────────────────────────────────────────────────────────
    frm_hook = tk.LabelFrame(inner, text="Móc hàng", bg="#f0f0f0",
                              font=("Arial", 9, "bold"))
    frm_hook.pack(fill='x', **pad)
    frm_hook_btns = tk.Frame(frm_hook, bg="#f0f0f0")
    frm_hook_btns.pack(fill='x', pady=4)
    tk.Button(frm_hook_btns, text="⬆ Nâng móc", width=14, bg="#3498db", fg="white",
              font=("Arial", 9), command=lambda: _send_action(30)).pack(side='left', padx=4)
    tk.Button(frm_hook_btns, text="⬇ Hạ móc",  width=14, bg="#2980b9", fg="white",
              font=("Arial", 9), command=lambda: _send_action(31)).pack(side='left', padx=4)

    # ── Raw command ───────────────────────────────────────────────────────────
    frm_raw = tk.LabelFrame(inner, text="Lệnh hệ thống (nâng cao)", bg="#f0f0f0",
                             font=("Arial", 9, "bold"))
    frm_raw.pack(fill='x', **pad)
    tk.Label(frm_raw, text="Gõ lệnh c= và nhấn Gửi:",
             bg="#f0f0f0", font=("Arial", 8)).pack(anchor='w', padx=6, pady=(4, 0))
    frm_raw_inp = tk.Frame(frm_raw, bg="#f0f0f0")
    frm_raw_inp.pack(fill='x', padx=6, pady=(0, 6))
    var_raw = tk.StringVar()
    tk.Entry(frm_raw_inp, textvariable=var_raw, width=16,
             font=("Consolas", 10)).pack(side='left', padx=(0, 4))
    tk.Button(frm_raw_inp, text="Gửi", bg="#7f8c8d", fg="white",
              command=lambda: _send_cmd(var_raw.get()) if var_raw.get() else None
              ).pack(side='left')
