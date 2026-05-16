"""
gui/settings_view.py  — Settings Tab (full-width, no tool panel)
-----------------------------------------------------------------
build_panel(app: AppShell) — xây dựng Settings view:
  Tabs: Connection, General, Traffic, Battery, Alarms, Stations,
        Users, Custom Actions, Integration

Migrate từ main.py App.show_settings_view() (lines 2178–2863).
"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gui.app_shell import AppShell


def _make_scrollable_tab(outer: ttk.Frame) -> ttk.Frame:
    """Bọc nội dung tab trong Canvas + Scrollbar có scroll chuột."""
    canvas = tk.Canvas(outer, highlightthickness=0)
    vsb    = ttk.Scrollbar(outer, orient='vertical', command=canvas.yview)
    canvas.configure(yscrollcommand=vsb.set)
    vsb.pack(side='right', fill='y')
    canvas.pack(side='left', fill='both', expand=True)
    inner  = ttk.Frame(canvas, padding=10)
    win_id = canvas.create_window((0, 0), window=inner, anchor='nw')
    inner.bind('<Configure>',
               lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
    canvas.bind('<Configure>',
                lambda e: canvas.itemconfig(win_id, width=e.width))

    def _scroll(event):
        canvas.yview_scroll(int(-1 * (event.delta / 120)), 'units')
    outer.bind('<Enter>', lambda e: canvas.bind_all('<MouseWheel>', _scroll))
    outer.bind('<Leave>', lambda e: canvas.unbind_all('<MouseWheel>'))
    canvas.bind('<Enter>', lambda e: canvas.bind_all('<MouseWheel>', _scroll))
    inner.bind('<Enter>', lambda e: canvas.bind_all('<MouseWheel>', _scroll))
    return inner


def build_panel(app: 'AppShell') -> None:
    """Xây dựng full-width Settings view vào app.content_frame."""
    config = app.ctx.config

    app.frm_settings = ttk.Frame(app.content_frame, padding=20)
    app.frm_settings.pack(fill='both', expand=True)

    ttk.Label(app.frm_settings, text=app.t("lbl_sys_config"),
              font=("Arial", 18, "bold")).pack(pady=10)

    nb = ttk.Notebook(app.frm_settings)
    nb.pack(fill='both', expand=True)

    # ── Create outer tab frames ───────────────────────────────────────────────
    _tab_conn_outer     = ttk.Frame(nb)
    _tab_gen_outer      = ttk.Frame(nb)
    _tab_traffic_outer  = ttk.Frame(nb)
    _tab_battery_outer  = ttk.Frame(nb)
    _tab_alarm_outer    = ttk.Frame(nb)
    _tab_stations_outer = ttk.Frame(nb)
    _tab_user_outer     = ttk.Frame(nb)
    _tab_actions_outer  = ttk.Frame(nb)
    _tab_integ_outer    = ttk.Frame(nb)

    app.tab_conn     = _make_scrollable_tab(_tab_conn_outer)
    app.tab_gen      = _make_scrollable_tab(_tab_gen_outer)
    app.tab_traffic  = _make_scrollable_tab(_tab_traffic_outer)
    app.tab_battery  = _make_scrollable_tab(_tab_battery_outer)
    app.tab_alarm    = _make_scrollable_tab(_tab_alarm_outer)
    app.tab_stations = _make_scrollable_tab(_tab_stations_outer)
    app.tab_user     = _make_scrollable_tab(_tab_user_outer)
    app.tab_actions  = _make_scrollable_tab(_tab_actions_outer)
    app.tab_integ    = _make_scrollable_tab(_tab_integ_outer)

    nb.add(_tab_conn_outer,     text=app.t("tab_conn"))
    nb.add(_tab_gen_outer,      text=app.t("tab_gen"))
    nb.add(_tab_traffic_outer,  text=app.t("tab_traffic"))
    nb.add(_tab_battery_outer,  text=app.t("tab_bat"))
    nb.add(_tab_alarm_outer,    text=app.t("tab_alarm"))
    nb.add(_tab_stations_outer, text=app.t("tab_stations"))
    nb.add(_tab_user_outer,     text=app.t("tab_user"))
    nb.add(_tab_actions_outer,  text=app.t("tab_actions"))
    nb.add(_tab_integ_outer,    text=app.t("tab_integ"))

    # =========================================================================
    # TAB 1 — Connection & Fleet
    # =========================================================================
    lf_net = ttk.LabelFrame(app.tab_conn, text=app.t("lbl_net_set"))
    lf_net.pack(fill='x', pady=5)

    # WiFi
    frm_wifi = ttk.Frame(lf_net, padding=5)
    frm_wifi.pack(fill='x')
    ttk.Label(frm_wifi, text=app.t("lbl_wifi_ssid")).pack(side='left')
    app.ent_ssid = ttk.Entry(frm_wifi, width=20)
    app.ent_ssid.insert(0, config.get('wifi', {}).get('ssid', ''))
    app.ent_ssid.pack(side='left', padx=(0, 5))
    ttk.Label(frm_wifi, text=app.t("lbl_wifi_pass")).pack(side='left')
    app.ent_wifi_pass = ttk.Entry(frm_wifi, width=20, show="*")
    app.ent_wifi_pass.insert(0, config.get('wifi', {}).get('password', ''))
    app.ent_wifi_pass.pack(side='left', padx=(0, 5))
    app.btn_toggle_wifi_pass = ttk.Button(frm_wifi, text=app.t("btn_show_pass"), width=5)
    app.btn_toggle_wifi_pass.config(
        command=lambda: app.toggle_password_visibility(
            app.ent_wifi_pass, app.btn_toggle_wifi_pass))
    app.btn_toggle_wifi_pass.pack(side='left')

    # MQTT
    lf_mqtt = ttk.LabelFrame(lf_net, text=app.t("lbl_mqtt_broker"))
    lf_mqtt.pack(fill='x', padx=5, pady=5)
    grid_frm = ttk.Frame(lf_mqtt, padding=10)
    grid_frm.pack(fill='x')

    ttk.Label(grid_frm, text=app.t("lbl_broker_ip")).grid(row=0, column=0, sticky='w')
    app.ent_broker = ttk.Entry(grid_frm)
    app.ent_broker.insert(0, config.get('mqtt', {}).get('broker', ''))
    app.ent_broker.grid(row=0, column=1, padx=5, pady=5)

    ttk.Label(grid_frm, text=app.t("lbl_port")).grid(row=0, column=2, sticky='w')
    app.ent_port = ttk.Entry(grid_frm, width=10)
    app.ent_port.insert(0, config.get('mqtt', {}).get('port', 1883))
    app.ent_port.grid(row=0, column=3, padx=5, pady=5)

    ttk.Label(grid_frm, text=app.t("lbl_user")).grid(row=1, column=0, sticky='w')
    app.ent_user = ttk.Entry(grid_frm)
    app.ent_user.insert(0, config.get('mqtt', {}).get('username', ''))
    app.ent_user.grid(row=1, column=1, padx=5, pady=5)

    ttk.Label(grid_frm, text=app.t("lbl_pass")).grid(row=1, column=2, sticky='w')
    app.ent_pass = ttk.Entry(grid_frm, show="*")
    app.ent_pass.insert(0, config.get('mqtt', {}).get('password', ''))
    app.ent_pass.grid(row=1, column=3, padx=5, pady=5)
    app.btn_toggle_mqtt_pass = ttk.Button(grid_frm, text=app.t("btn_show_pass"), width=5)
    app.btn_toggle_mqtt_pass.config(
        command=lambda: app.toggle_password_visibility(
            app.ent_pass, app.btn_toggle_mqtt_pass))
    app.btn_toggle_mqtt_pass.grid(row=1, column=4, padx=2)

    # Factory / Hardware scope
    lf_scope = ttk.LabelFrame(lf_net, text="Phạm vi hệ thống (Topic Scope)")
    lf_scope.pack(fill='x', padx=5, pady=(0, 5))
    frm_scope = ttk.Frame(lf_scope, padding=8)
    frm_scope.pack(fill='x')
    ttk.Label(frm_scope, text="Hardware ID:").grid(row=0, column=0, sticky='w', padx=4, pady=3)
    app.ent_hardware = ttk.Entry(frm_scope, width=18)
    app.ent_hardware.insert(0, config.get('hardware', 'hardware'))
    app.ent_hardware.grid(row=0, column=1, padx=5, pady=3, sticky='w')
    ttk.Label(frm_scope, text="Nhà máy / Factory:").grid(row=0, column=2, sticky='w', padx=4, pady=3)
    app.ent_factory = ttk.Entry(frm_scope, width=18)
    app.ent_factory.insert(0, config.get('factory', 'NhaMayA'))
    app.ent_factory.grid(row=0, column=3, padx=5, pady=3, sticky='w')
    hw_val = config.get('hardware', 'hardware')
    fc_val = config.get('factory', 'NhaMayA')
    app.lbl_scope_preview = ttk.Label(frm_scope,
                                       text=f"Subscribe: AGV/{hw_val}/{fc_val}/+/pub",
                                       foreground="#2980b9")
    app.lbl_scope_preview.grid(row=1, column=0, columnspan=4, sticky='w', padx=4)

    def _update_scope_preview(*_):
        hw = app.ent_hardware.get().strip() or 'hardware'
        fc = app.ent_factory.get().strip() or 'NhaMayA'
        app.lbl_scope_preview.config(text=f"Subscribe: AGV/{hw}/{fc}/+/pub")

    app.ent_hardware.bind('<KeyRelease>', _update_scope_preview)
    app.ent_factory.bind('<KeyRelease>',  _update_scope_preview)

    frm_net_btns = ttk.Frame(lf_net)
    frm_net_btns.pack(pady=5)
    ttk.Button(frm_net_btns, text=app.t("btn_save_net"),
               command=app.save_network_settings).pack(side='left', padx=5)
    ttk.Button(frm_net_btns, text="🔌 Kết nối / Connect",
               command=app.btn_connect_mqtt).pack(side='left', padx=5)
    app.lbl_mqtt_conn_status = ttk.Label(frm_net_btns, text="", foreground="gray")
    app.lbl_mqtt_conn_status.pack(side='left', padx=5)

    # Active topic display
    lf_active_topics = ttk.LabelFrame(app.tab_conn, text="📡 Topic đang hoạt động (Runtime)")
    lf_active_topics.pack(fill='x', padx=5, pady=(2, 5))
    app.lbl_active_topics = ttk.Label(lf_active_topics, text="(Chưa có AGV)",
                                       foreground="gray",
                                       font=("Courier", 9), justify='left', anchor='w')
    app.lbl_active_topics.pack(fill='x', padx=8, pady=4)

    # AGV Management
    lf_agv = ttk.LabelFrame(app.tab_conn, text=app.t("lbl_agv_mgmt"))
    lf_agv.pack(fill='both', expand=True, pady=5)

    cols = ("ID", "IP", "Sub", "Pub", "Color")
    app.tree_settings_agv = ttk.Treeview(lf_agv, columns=cols, show='headings', height=5)
    for c, hdr, w in [("ID", app.t("col_id"), 80), ("IP", app.t("col_ip"), 80),
                       ("Sub", app.t("col_sub"), 80), ("Pub", app.t("col_pub"), 80),
                       ("Color", app.t("col_color"), 80)]:
        app.tree_settings_agv.heading(c, text=hdr)
        app.tree_settings_agv.column(c, width=w)
    app.tree_settings_agv.pack(side='left', fill='both', expand=True, padx=5, pady=5)
    app.refresh_agv_settings_tree()

    frm_edit = ttk.Frame(lf_agv)
    frm_edit.pack(side='right', fill='y', padx=5, pady=5)
    ttk.Label(frm_edit, text="ID:").pack(anchor='w')
    app.ent_agv_id = ttk.Entry(frm_edit); app.ent_agv_id.pack(fill='x')
    ttk.Label(frm_edit, text="IP:").pack(anchor='w')
    app.ent_agv_ip = ttk.Entry(frm_edit); app.ent_agv_ip.pack(fill='x')
    ttk.Label(frm_edit, text="Sub (topic nhận lệnh):").pack(anchor='w', pady=(4, 0))
    app.ent_agv_sub = ttk.Entry(frm_edit); app.ent_agv_sub.pack(fill='x')
    ttk.Label(frm_edit, text="Pub (topic gửi trạng thái):").pack(anchor='w', pady=(4, 0))
    app.ent_agv_pub = ttk.Entry(frm_edit); app.ent_agv_pub.pack(fill='x')
    ttk.Label(frm_edit, text="Color:").pack(anchor='w')
    app.current_agv_color = "#3498db"
    app.btn_agv_color = tk.Button(frm_edit, text="■", bg=app.current_agv_color,
                                   command=app.pick_agv_color)
    app.btn_agv_color.pack(fill='x', pady=2)
    app.var_can_reverse = tk.BooleanVar(value=True)
    ttk.Checkbutton(frm_edit, text="Hỗ trợ đi lùi (can_reverse)",
                    variable=app.var_can_reverse).pack(anchor='w', pady=4)
    ttk.Label(frm_edit, text="Bỏ chọn nếu AGV chỉ đi tiến",
              font=("Arial", 8), foreground="gray").pack(anchor='w')
    ttk.Button(frm_edit, text=app.t("btn_add_agv"),
               command=app.btn_add_agv).pack(pady=10, fill='x')
    ttk.Button(frm_edit, text=app.t("btn_del_agv"),
               command=app.btn_del_agv).pack(pady=5, fill='x')
    app.tree_settings_agv.bind("<<TreeviewSelect>>", app.on_agv_select)

    # =========================================================================
    # TAB 2 — General & Control
    # =========================================================================
    lf_sys = ttk.LabelFrame(app.tab_gen, text=app.t("lbl_sys_config"))
    lf_sys.pack(fill='x', pady=5)
    frm_sys = ttk.Frame(lf_sys, padding=5)
    frm_sys.pack(fill='x')
    ttk.Label(frm_sys, text="Phiên bản / Version:").grid(
        row=0, column=0, sticky='w', padx=5, pady=3)
    app.ent_version = ttk.Entry(frm_sys, width=15)
    app.ent_version.insert(0, config.get('version', '1.0'))
    app.ent_version.grid(row=0, column=1, padx=5, pady=3, sticky='w')
    ttk.Label(frm_sys, text="(Factory / Hardware → tab Kết nối)",
              foreground="gray").grid(row=0, column=2, sticky='w', padx=10)

    lf_gen = ttk.LabelFrame(app.tab_gen, text=app.t("lbl_work_param"))
    lf_gen.pack(fill='x', pady=5)
    ttk.Label(lf_gen, text=app.t("lbl_work_hours")).pack(side='left', padx=5)
    app.ent_work_hours = ttk.Entry(lf_gen, width=10)
    app.ent_work_hours.insert(0, str(config.get('work_hours', 12)))
    app.ent_work_hours.pack(side='left', padx=5)

    lf_rule = ttk.LabelFrame(app.tab_gen, text=app.t("lbl_dispatch_rule"))
    lf_rule.pack(fill='x', pady=10)
    weights = config.get('dispatch_weights', {"distance": 80, "idle": 20, "battery": 0})
    ttk.Label(lf_rule, text="Distance Priority (%):").grid(
        row=0, column=0, sticky='w', padx=5)
    app.scale_dist = tk.Scale(lf_rule, from_=0, to=100, orient='horizontal', length=200)
    app.scale_dist.set(weights.get('distance', 80))
    app.scale_dist.grid(row=0, column=1, padx=5)
    ttk.Label(lf_rule, text="Idle Time Priority (%):").grid(
        row=1, column=0, sticky='w', padx=5)
    app.scale_idle = tk.Scale(lf_rule, from_=0, to=100, orient='horizontal', length=200)
    app.scale_idle.set(weights.get('idle', 20))
    app.scale_idle.grid(row=1, column=1, padx=5)
    ttk.Label(lf_rule, text="Battery Priority (%):").grid(
        row=2, column=0, sticky='w', padx=5)
    app.scale_bat = tk.Scale(lf_rule, from_=0, to=100, orient='horizontal', length=200)
    app.scale_bat.set(weights.get('battery', 0))
    app.scale_bat.grid(row=2, column=1, padx=5)

    ttk.Button(app.tab_gen, text=app.t("btn_save_gen"),
               command=app.save_general_settings).pack(pady=10)
    ttk.Button(app.tab_gen, text=app.t("btn_lang_toggle"),
               command=app.toggle_language).pack(pady=20)

    # =========================================================================
    # TAB 3 — Traffic & Safety
    # =========================================================================
    ttk.Label(app.tab_traffic, text=app.t("lbl_traffic_param"),
              font=("Arial", 12, "bold")).pack(pady=10)

    lf_traffic = ttk.LabelFrame(app.tab_traffic, text="Safety")
    lf_traffic.pack(fill='x', pady=5)

    ttk.Label(lf_traffic, text=app.t("lbl_safe_dist")).grid(
        row=0, column=0, sticky='w', padx=5, pady=5)
    app.ent_safe_dist = ttk.Entry(lf_traffic)
    app.ent_safe_dist.grid(row=0, column=1)
    app.ent_safe_dist.insert(0, str(config.get('traffic', {}).get('safety_dist', 2.0)))

    ttk.Label(lf_traffic, text=app.t("lbl_deadlock_time")).grid(
        row=1, column=0, sticky='w', padx=5, pady=5)
    app.ent_deadlock = ttk.Entry(lf_traffic)
    app.ent_deadlock.grid(row=1, column=1)
    app.ent_deadlock.insert(0, str(config.get('traffic', {}).get('deadlock_timeout', 10)))

    ttk.Label(lf_traffic, text=app.t("lbl_speed_cfg"),
              font=("Arial", 10, "bold")).grid(row=2, column=0, sticky='w', pady=(10, 5))
    ttk.Label(lf_traffic, text=app.t("lbl_speed_fast")).grid(
        row=3, column=0, sticky='w', padx=5)
    app.ent_spd_fast = ttk.Entry(lf_traffic, width=10)
    app.ent_spd_fast.grid(row=3, column=1)
    spd_fast = config.get('traffic', {}).get('speed_fast', 120)
    app.ent_spd_fast.insert(0, str(spd_fast))
    ttk.Label(lf_traffic, text=f"≈ {spd_fast/255:.2f} m/s  (255 = 1 m/s)",
              foreground="gray", font=("Arial", 8)).grid(
                  row=3, column=2, sticky='w', padx=4)

    ttk.Label(lf_traffic, text=app.t("lbl_speed_slow")).grid(
        row=4, column=0, sticky='w', padx=5)
    app.ent_spd_slow = ttk.Entry(lf_traffic, width=10)
    app.ent_spd_slow.grid(row=4, column=1)
    spd_slow = config.get('traffic', {}).get('speed_slow', 60)
    app.ent_spd_slow.insert(0, str(spd_slow))
    ttk.Label(lf_traffic, text=f"≈ {spd_slow/255:.2f} m/s  (255 = 1 m/s)",
              foreground="gray", font=("Arial", 8)).grid(
                  row=4, column=2, sticky='w', padx=4)

    ttk.Label(lf_traffic, text="Lookahead (thẻ gửi trước):").grid(
        row=5, column=0, sticky='w', padx=5, pady=5)
    app.spn_lookahead = ttk.Spinbox(lf_traffic, from_=2, to=15, width=8)
    app.spn_lookahead.grid(row=5, column=1, sticky='w')
    app.spn_lookahead.set(str(config.get('traffic', {}).get('lookahead', 3)))
    ttk.Label(lf_traffic, text="(thẻ) — tăng nếu đường dài nhiều thẻ",
              foreground="gray", font=("Arial", 8)).grid(
                  row=5, column=2, sticky='w', padx=4)

    ttk.Separator(lf_traffic, orient='horizontal').grid(
        row=6, column=0, columnspan=3, sticky='ew', pady=(10, 4))
    ttk.Label(lf_traffic, text="Tỉ lệ bản đồ",
              font=("Arial", 10, "bold")).grid(row=7, column=0, sticky='w', pady=(0, 4))
    ttk.Label(lf_traffic, text="1 đơn vị bản đồ = X mét:").grid(
        row=8, column=0, sticky='w', padx=5)
    app.ent_map_mpu = ttk.Entry(lf_traffic, width=10)
    app.ent_map_mpu.grid(row=8, column=1, sticky='w')
    app.ent_map_mpu.insert(0, str(config.get('map', {}).get('meters_per_unit', 0.01)))
    ttk.Label(lf_traffic,
              text="(0.01 = bản đồ lớn hơn thực tế 100 lần — nhãn cạnh hiện m)",
              foreground="gray", font=("Arial", 8)).grid(
                  row=8, column=2, sticky='w', padx=4)

    ttk.Button(app.tab_traffic, text=app.t("btn_save_traffic"),
               command=app.save_traffic_settings).pack(pady=10)

    # Door Sensors
    lf_doors = ttk.LabelFrame(app.tab_traffic, text="🚪 Cảm biến Cửa (Door Sensors)")
    lf_doors.pack(fill='x', pady=6, padx=5)
    ttk.Label(lf_doors,
              text="Server tự động inject lệnh check cửa vào plan.\n"
                   "'Từ tag' = tag trước đó (xác định chiều). Để trống = cả 2 chiều.",
              font=("Arial", 8), foreground="gray").pack(anchor='w', padx=5)

    cols_door = ("tag", "from_tag", "name", "topic", "on", "off")
    app.tree_doors = ttk.Treeview(lf_doors, columns=cols_door, show='headings', height=4)
    for col, hdr, w in [("tag", "Tag", 40), ("from_tag", "Từ tag", 50),
                         ("name", "Tên cửa", 90), ("topic", "Relay Topic", 180),
                         ("on", "ON", 40), ("off", "OFF", 40)]:
        app.tree_doors.heading(col, text=hdr)
        app.tree_doors.column(col, width=w)
    app.tree_doors.pack(fill='x', padx=5, pady=4)

    for d in config.get('door_sensors', []):
        ef = d.get('entry_from', '')
        app.tree_doors.insert("", "end", values=(
            d.get('tag_id', 0), ef if ef is not None else '',
            d.get('name', ''), d.get('relay_topic', ''),
            d.get('relay_on_payload', '1'), d.get('relay_off_payload', '0')))

    frm_door_in = ttk.Frame(lf_doors)
    frm_door_in.pack(fill='x', padx=5, pady=2)
    ttk.Label(frm_door_in, text="Tag:").pack(side='left')
    app.ent_door_tag = ttk.Entry(frm_door_in, width=5); app.ent_door_tag.pack(side='left', padx=2)
    ttk.Label(frm_door_in, text="Từ tag:").pack(side='left', padx=(4, 0))
    app.ent_door_from = ttk.Entry(frm_door_in, width=5); app.ent_door_from.pack(side='left', padx=2)
    ttk.Label(frm_door_in, text="Tên:").pack(side='left', padx=(4, 0))
    app.ent_door_name = ttk.Entry(frm_door_in, width=9); app.ent_door_name.pack(side='left', padx=2)
    ttk.Label(frm_door_in, text="Relay Topic:").pack(side='left', padx=(4, 0))
    app.ent_door_topic = ttk.Entry(frm_door_in, width=20); app.ent_door_topic.pack(side='left', padx=2)
    ttk.Label(frm_door_in, text="ON:").pack(side='left', padx=(4, 0))
    app.ent_door_on = ttk.Entry(frm_door_in, width=4); app.ent_door_on.insert(0, "1")
    app.ent_door_on.pack(side='left', padx=1)
    ttk.Label(frm_door_in, text="OFF:").pack(side='left', padx=(4, 0))
    app.ent_door_off = ttk.Entry(frm_door_in, width=4); app.ent_door_off.insert(0, "0")
    app.ent_door_off.pack(side='left', padx=1)

    def _add_door():
        try:
            tag_id = int(app.ent_door_tag.get())
        except ValueError:
            messagebox.showwarning("Lỗi", "Tag ID phải là số nguyên.")
            return
        name  = app.ent_door_name.get().strip()
        topic = app.ent_door_topic.get().strip()
        if not topic:
            messagebox.showwarning("Lỗi", "Vui lòng nhập Relay Topic.")
            return
        on_p  = app.ent_door_on.get().strip() or "1"
        off_p = app.ent_door_off.get().strip() or "0"
        from_raw = app.ent_door_from.get().strip()
        entry_from = int(from_raw) if from_raw.isdigit() else None
        new_entry = {"tag_id": tag_id, "entry_from": entry_from, "name": name,
                     "relay_topic": topic, "relay_on_payload": on_p,
                     "relay_off_payload": off_p}
        doors = config.get('door_sensors', [])
        doors = [d for d in doors
                 if not (d.get('tag_id') == tag_id and d.get('entry_from') == entry_from)]
        doors.append(new_entry)
        config['door_sensors'] = doors
        app.save_config()
        app._rebuild_door_maps()
        app.tree_doors.delete(*app.tree_doors.get_children())
        for d in doors:
            ef = d.get('entry_from', '')
            app.tree_doors.insert("", "end", values=(
                d.get('tag_id', 0), ef if ef is not None else '',
                d.get('name', ''), d.get('relay_topic', ''),
                d.get('relay_on_payload', '1'), d.get('relay_off_payload', '0')))

    def _del_door():
        sel = app.tree_doors.selection()
        if not sel:
            return
        vals   = app.tree_doors.item(sel[0])['values']
        tag_id = int(vals[0])
        ef_raw = vals[1]
        entry_from = int(ef_raw) if str(ef_raw).isdigit() else None
        doors = [d for d in config.get('door_sensors', [])
                 if not (d.get('tag_id') == tag_id and d.get('entry_from') == entry_from)]
        config['door_sensors'] = doors
        app.save_config()
        app._rebuild_door_maps()
        app.tree_doors.delete(sel[0])

    def _on_door_select(_event):
        sel = app.tree_doors.selection()
        if not sel:
            return
        vals = app.tree_doors.item(sel[0])['values']
        for ent, val in [(app.ent_door_tag, vals[0]), (app.ent_door_from, vals[1]),
                          (app.ent_door_name, vals[2]), (app.ent_door_topic, vals[3]),
                          (app.ent_door_on, vals[4]), (app.ent_door_off, vals[5])]:
            ent.delete(0, 'end'); ent.insert(0, val)

    app.tree_doors.bind("<<TreeviewSelect>>", _on_door_select)
    frm_door_btn = ttk.Frame(lf_doors)
    frm_door_btn.pack(anchor='w', padx=5, pady=2)
    ttk.Button(frm_door_btn, text="➕ Thêm / Cập nhật",
               command=_add_door).pack(side='left', padx=2)
    ttk.Button(frm_door_btn, text="❌ Xóa chọn",
               command=_del_door).pack(side='left', padx=2)

    # Charging Stations
    lf_chargers = ttk.LabelFrame(app.tab_traffic, text=app.t("lbl_charger_setup"))
    lf_chargers.pack(fill='both', expand=True, pady=10, padx=5)

    cols_chg = ("Name", "Node", "RevZone", "Speed", "HomingPath", "AGV")
    app.tree_chargers = ttk.Treeview(lf_chargers, columns=cols_chg, show='headings', height=4)
    for col, hdr, w in [("Name", app.t("col_chg_name"), 100),
                         ("Node", app.t("col_chg_node"), 60),
                         ("RevZone", app.t("col_chg_zone"), 120),
                         ("Speed", app.t("col_chg_speed"), 60),
                         ("HomingPath", "Đường dẫn đường / Homing Path", 140),
                         ("AGV", "AGV phân công / Assigned AGV", 90)]:
        app.tree_chargers.heading(col, text=hdr)
        app.tree_chargers.column(col, width=w)
    app.tree_chargers.pack(side='left', fill='both', expand=True, padx=5, pady=5)

    frm_chg_edit = ttk.Frame(lf_chargers)
    frm_chg_edit.pack(side='right', fill='y', padx=5, pady=5)
    for lbl_text, attr in [("ID:", 'ent_chg_id'), ("Tên / Name:", 'ent_chg_name'),
                             ("Thẻ sạc / Node ID:", 'ent_chg_node'),
                             ("Vùng lùi / Rev. Zone (VD: 8,9):", 'ent_chg_zone'),
                             ("Tốc độ chậm / Slow Speed:", 'ent_chg_speed'),
                             ("Đường dẫn đường khi lạc / Homing Path (VD: 3,5,7,9):", 'ent_chg_homing'),
                             ("AGV phân công / Assigned AGV ID:", 'ent_chg_agv')]:
        ttk.Label(frm_chg_edit, text=lbl_text).pack(anchor='w')
        ent = ttk.Entry(frm_chg_edit, width=18)
        ent.pack(fill='x')
        setattr(app, attr, ent)
    ttk.Button(frm_chg_edit, text="➕ Thêm/Sửa",
               command=app.btn_add_charger).pack(pady=5, fill='x')
    ttk.Button(frm_chg_edit, text="❌ Xóa (Delete)",
               command=app.btn_del_charger).pack(fill='x')

    app.tree_chargers.bind("<<TreeviewSelect>>", app.on_charger_select)
    app.refresh_chargers_settings_tree()

    # =========================================================================
    # TAB 4 — Battery & Charging
    # =========================================================================
    ttk.Label(app.tab_battery, text=app.t("lbl_bat_mgmt"),
              font=("Arial", 12, "bold")).pack(pady=10)
    app.var_bat_enable = tk.BooleanVar(
        value=config.get('battery', {}).get('enabled', False))
    ttk.Checkbutton(app.tab_battery, text=app.t("chk_auto_charge"),
                    variable=app.var_bat_enable).pack(anchor='w', pady=5)

    lf_bat = ttk.LabelFrame(app.tab_battery, text="Thresholds")
    lf_bat.pack(fill='x', pady=5)
    ttk.Label(lf_bat, text=app.t("lbl_low_bat")).grid(
        row=0, column=0, sticky='w', padx=5, pady=5)
    app.ent_low_bat = ttk.Entry(lf_bat)
    app.ent_low_bat.grid(row=0, column=1)
    app.ent_low_bat.insert(0, str(config.get('battery', {}).get('low_threshold', 20)))
    ttk.Label(lf_bat, text=app.t("lbl_resume_bat")).grid(
        row=1, column=0, sticky='w', padx=5, pady=5)
    app.ent_resume_bat = ttk.Entry(lf_bat)
    app.ent_resume_bat.grid(row=1, column=1)
    app.ent_resume_bat.insert(0, str(config.get('battery', {}).get('resume_threshold', 80)))
    ttk.Button(app.tab_battery, text=app.t("btn_save_bat"),
               command=app.save_battery_settings).pack(pady=10)

    # =========================================================================
    # TAB 5 — Alarms & Errors
    # =========================================================================
    ttk.Label(app.tab_alarm, text=app.t("lbl_err_mgmt"),
              font=("Arial", 12, "bold")).pack(pady=10)
    frm_al_cfg = ttk.Frame(app.tab_alarm)
    frm_al_cfg.pack(fill='x', pady=5)
    ttk.Label(frm_al_cfg, text=app.t("lbl_stuck_time")).pack(side='left')
    app.ent_stuck_time = ttk.Entry(frm_al_cfg, width=10)
    app.ent_stuck_time.insert(0, str(config.get('alarms', {}).get('stuck_timeout', 30)))
    app.ent_stuck_time.pack(side='left', padx=5)
    ttk.Button(frm_al_cfg, text=app.t("btn_save_alarm"),
               command=app.save_alarm_settings).pack(side='left')

    ttk.Label(app.tab_alarm, text=app.t("lbl_active_err")).pack(anchor='w')
    cols_err = ("ID", "Code", "Desc", "Time")
    app.tree_err = ttk.Treeview(app.tab_alarm, columns=cols_err, show='headings', height=6)
    app.tree_err.heading("ID",   text=app.t("col_id"))
    app.tree_err.heading("Code", text=app.t("col_err_code"))
    app.tree_err.heading("Desc", text=app.t("col_desc"))
    app.tree_err.heading("Time", text=app.t("col_time"))
    app.tree_err.pack(fill='both', expand=True, pady=5)
    app.update_error_table()

    # =========================================================================
    # TAB 6 — Stations & Teams
    # =========================================================================
    ttk.Label(app.tab_stations, text=app.t("lbl_station_setup"),
              font=("Arial", 12, "bold")).pack(pady=10)

    cols_st = ("ID", "Name", "Wait", "Delivery")
    app.tree_st = ttk.Treeview(app.tab_stations, columns=cols_st, show='headings', height=8)
    for col, hdr, w, anc in [("ID", app.t("col_team_id"), 70, 'center'),
                               ("Name", app.t("col_name"), 120, 'w'),
                               ("Wait", app.t("col_wait_node"), 120, 'center'),
                               ("Delivery", app.t("col_del_node"), 120, 'center')]:
        app.tree_st.heading(col, text=hdr)
        app.tree_st.column(col, width=w, anchor=anc)
    app.tree_st.pack(fill='x', pady=5)

    for st in config.get('station_config', []):
        app.tree_st.insert("", "end", values=(st['id'], st['name'],
                                               st['wait'], st['delivery']))

    frm_st_edit = ttk.Frame(app.tab_stations)
    frm_st_edit.pack(fill='x', pady=5)
    ttk.Label(frm_st_edit, text="ID Tổ / Team ID:").pack(side='left')
    app.ent_st_id   = ttk.Entry(frm_st_edit, width=5);  app.ent_st_id.pack(side='left', padx=2)
    ttk.Label(frm_st_edit, text="Tên / Name:").pack(side='left')
    app.ent_st_name = ttk.Entry(frm_st_edit, width=15); app.ent_st_name.pack(side='left', padx=2)
    ttk.Label(frm_st_edit, text="Thẻ chờ / Wait:").pack(side='left')
    app.ent_st_wait = ttk.Entry(frm_st_edit, width=8);  app.ent_st_wait.pack(side='left', padx=2)
    ttk.Label(frm_st_edit, text="Thẻ giao / Delivery:").pack(side='left')
    app.ent_st_del  = ttk.Entry(frm_st_edit, width=8);  app.ent_st_del.pack(side='left', padx=2)
    ttk.Button(frm_st_edit, text="➕ Thêm/Sửa (Add/Update)",
               command=lambda: app.update_station_config_list(add=True)).pack(side='left', padx=5)
    ttk.Button(frm_st_edit, text="❌ Xóa (Delete)",
               command=lambda: app.update_station_config_list(add=False)).pack(side='left')

    ttk.Button(app.tab_stations, text="💾 Lưu Cấu hình / Save Config",
               command=app.save_station_settings).pack(pady=15)

    # =========================================================================
    # TAB 7 — Users & Permissions
    # =========================================================================
    ttk.Label(app.tab_user, text=app.t("lbl_user_mgmt"),
              font=("Arial", 12, "bold")).pack(pady=10)
    cols_usr = ("User", "Role", "Last")
    app.tree_usr = ttk.Treeview(app.tab_user, columns=cols_usr, show='headings', height=5)
    app.tree_usr.heading("User", text=app.t("col_name"))
    app.tree_usr.heading("Role", text=app.t("col_role"))
    app.tree_usr.heading("Last", text=app.t("col_last_login"))
    app.tree_usr.pack(fill='x', pady=5)
    for u in config.get('users', []):
        app.tree_usr.insert("", "end", values=(u['username'], u['role'], "N/A"))

    frm_usr = ttk.Frame(app.tab_user)
    frm_usr.pack(fill='x', pady=5)
    ttk.Label(frm_usr, text=app.t("lbl_user")).pack(side='left')
    app.ent_usr_name = ttk.Entry(frm_usr); app.ent_usr_name.pack(side='left', padx=5)
    ttk.Label(frm_usr, text=app.t("col_role")).pack(side='left')
    app.cb_usr_role = ttk.Combobox(frm_usr, values=["admin", "engineer", "operator"])
    app.cb_usr_role.pack(side='left', padx=5)
    ttk.Button(frm_usr, text=app.t("btn_add_user"),
               command=app.save_user_settings).pack(side='left', padx=10)

    # =========================================================================
    # TAB 8 — Custom Actions
    # =========================================================================
    ttk.Label(app.tab_actions, text=app.t("lbl_custom_actions"),
              font=("Arial", 12, "bold")).pack(pady=10)
    cols_act = ("ID", "Name")
    app.tree_act = ttk.Treeview(app.tab_actions, columns=cols_act, show='headings', height=8)
    app.tree_act.heading("ID",   text=app.t("col_act_id"))
    app.tree_act.heading("Name", text=app.t("col_act_name"))
    app.tree_act.column("ID",   width=80, anchor='center')
    app.tree_act.column("Name", width=300)
    app.tree_act.pack(fill='x', pady=5)
    for act in config.get('custom_actions', []):
        app.tree_act.insert("", "end", values=(act['id'], act['name']))

    frm_act_ctrl = ttk.Frame(app.tab_actions)
    frm_act_ctrl.pack(fill='x', pady=5)
    ttk.Label(frm_act_ctrl, text="ID:").pack(side='left')
    app.ent_act_id   = ttk.Entry(frm_act_ctrl, width=10);  app.ent_act_id.pack(side='left', padx=5)
    ttk.Label(frm_act_ctrl, text="Name:").pack(side='left')
    app.ent_act_name = ttk.Entry(frm_act_ctrl, width=30); app.ent_act_name.pack(side='left', padx=5)
    ttk.Button(frm_act_ctrl, text=app.t("btn_add_act"),
               command=app.add_custom_action).pack(side='left', padx=10)
    ttk.Button(frm_act_ctrl, text=app.t("btn_del_act"),
               command=app.del_custom_action).pack(side='left')
    ttk.Label(app.tab_actions,
              text="* Note: IDs 0-19 are reserved for System.",
              font=("Arial", 9, "italic"), foreground="gray").pack(anchor='w', pady=5)

    ttk.Separator(app.tab_actions, orient='horizontal').pack(fill='x', pady=10)
    ttk.Label(app.tab_actions, text="⚡ Workflow — Nhiệm vụ đặc biệt theo Node",
              font=("Arial", 11, "bold")).pack(anchor='w')
    ttk.Label(app.tab_actions,
              text="Cấu hình hành động tự động khi AGV đến từng thẻ RFID\n"
                   "(gửi MQTT, bật relay, bấm còi, chờ, đổi tốc độ...)",
              foreground="gray", font=("Arial", 9)).pack(anchor='w', pady=2)
    ttk.Button(app.tab_actions, text="⚡ Mở Workflow Manager",
               command=app.open_workflow_manager_dialog).pack(anchor='w', pady=6)

    # =========================================================================
    # TAB 9 — Integration
    # =========================================================================
    ttk.Label(app.tab_integ, text=app.t("lbl_sys_integ"),
              font=("Arial", 12, "bold")).pack(pady=10)
    app.var_api_enable = tk.BooleanVar(
        value=config.get('integration', {}).get('api_enabled', True))
    ttk.Checkbutton(app.tab_integ, text=app.t("chk_enable_api"),
                    variable=app.var_api_enable).pack(anchor='w', pady=5)

    frm_api = ttk.Frame(app.tab_integ)
    frm_api.pack(fill='x', pady=5)
    ttk.Label(frm_api, text=app.t("lbl_api_port")).pack(side='left')
    app.ent_api_port = ttk.Entry(frm_api)
    app.ent_api_port.insert(0, str(config.get('integration', {}).get('api_port', 8000)))
    app.ent_api_port.pack(side='left', padx=5)
    ttk.Label(app.tab_integ,
              text="External Systems can control AGVs via:\n"
                   "http://<server_ip>:<port>/api/v1/dispatch").pack(pady=20)
    ttk.Button(app.tab_integ, text=app.t("btn_save_integ"),
               command=app.save_integration_settings).pack(pady=10)
