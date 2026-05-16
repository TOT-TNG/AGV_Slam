"""
gui/app_shell.py  — Main Application Shell
-------------------------------------------
Migrate từ main.py App class:
  - App.__init__ → AppShell.__init__
  - Navigation, auth, language, background loops
  - show_*_view() methods delegate sang view modules
"""
from __future__ import annotations
import os
import json
import time
import socket
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog, colorchooser
import datetime
from typing import TYPE_CHECKING

from gui.lang import LANG
from gui.map_widget import MapWidget

if TYPE_CHECKING:
    from core.context import AppContext


class AppShell(tk.Tk):
    """
    Cửa sổ chính — navigation + tab routing.
    Mỗi tab content được load từ module gui/*_view.py.
    """

    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.title("AGV Fleet Manager")
        self.geometry("1000x700")

        self.current_user = None
        self.is_logged_in = False
        self.current_lang = ctx.config.get('language', 'vi')

        # Đọc chart colors / node names cho stats view
        self.chart_colors = ctx.config.get("chart_colors", {
            "pickup": "#3498db", "delivery": "#2ecc71",
            "return": "#f1c40f", "idle": "#95a5a6", "trip_bar": "#9b59b6"
        })
        self.node_names = ctx.config.get("station_map", {})

        # ── Main Layout ───────────────────────────────────────────────────────
        self.nav_frame = tk.Frame(self, bg="#2c3e50", width=80)
        self.nav_frame.pack(side='left', fill='y')

        self.tool_frame = ttk.Frame(self, width=220, padding=10)
        self.tool_frame.pack(side='left', fill='y', expand=False)

        self.content_frame = tk.Frame(self, bg="white")
        self.content_frame.pack(side='right', expand=True, fill='both')

        # ── Map Widget ─────────────────────────────────────────────────────────
        self.map_widget = MapWidget(self.content_frame, ctx.planner, ctx.agv_list)
        self.map_widget.get_id_callback = self.get_current_node_id
        self.map_widget.set_lang_data(LANG, self.current_lang)
        _map_cfg = ctx.config.get('map', {})
        self.map_widget.meters_per_unit = _map_cfg.get('meters_per_unit', 0.01)
        if 'zoom' in _map_cfg:
            self.map_widget.scale    = float(_map_cfg['zoom'])
            self.map_widget.offset_x = float(_map_cfg.get('offset_x', 0))
            self.map_widget.offset_y = float(_map_cfg.get('offset_y', 0))
        if ctx.zone_mgr:
            self.map_widget.set_zone_manager(ctx.zone_mgr)
        self.update_map_actions()

        # Bind rotation animation callback
        for _agv in ctx.agv_list:
            _agv.on_init_turn_anim_cb = (
                lambda aid, ct, nt, dur, mw=self.map_widget:
                    mw.start_auto_rotation(aid, ct, nt, dur)
            )

        # ── Navigation buttons ─────────────────────────────────────────────────
        self._nav_buttons: dict[str, tk.Button] = {}
        self._active_nav_key = None

        self.create_nav_button("nav_monitor",  self.show_monitor_view)
        self.create_nav_button("nav_editor",   self.show_editor_view)
        self.create_nav_button("nav_manual",   self.show_manual_control_view)
        self.create_nav_button("nav_stats",    self.show_stats_view)
        self.create_nav_button("nav_settings", self.show_settings_view)
        self.create_nav_button("nav_schedule", self.show_schedule_view)
        self.create_nav_button("nav_sim",      self.show_sim_view)
        self.create_nav_button("nav_burnin",   self.show_burnin_view)
        self.create_nav_button("nav_log",      self.show_log_view)

        self.btn_nav_login = tk.Button(
            self.nav_frame, text=self.t("nav_login"), command=self.handle_login_click,
            bg="#2c3e50", fg="white", relief="flat",
            font=("Arial", 10, "bold"), height=3, width=8)
        self.btn_nav_login.pack(side='bottom', pady=20, padx=2)
        self.btn_nav_login.bind("<Enter>", lambda e: self.btn_nav_login.config(bg="#34495e"))
        self.btn_nav_login.bind("<Leave>", lambda e: self.btn_nav_login.config(bg="#2c3e50"))

        self.lock_interface()
        self.after(100, self._dev_autologin)       # DEV: bỏ để dùng login thật
        # self.after(100, self.open_login_window)  # PROD
        self.after(1000, self.update_connection_status)

        # ── Start background loops ─────────────────────────────────────────────
        self.after(1000, self._run_traffic_control)
        self.after(1000, self._run_hmi_handler)
        self.after(5000, self._run_scheduler)

    # ── Translation ───────────────────────────────────────────────────────────

    def t(self, key: str) -> str:
        return LANG.get(self.current_lang, LANG['en']).get(key, key)

    # ── Navigation ────────────────────────────────────────────────────────────

    def create_nav_button(self, text_key: str, command):
        def _cmd(key=text_key):
            command()
            self._set_active_tab(key)
        btn = tk.Button(
            self.nav_frame, text=self.t(text_key), command=_cmd,
            bg="#2c3e50", fg="white", relief="flat",
            font=("Arial", 10, "bold"), height=3, width=8)
        btn.pack(pady=5, padx=2)
        btn.bind("<Enter>", lambda e, b=btn, k=text_key:
                 b.config(bg="#34495e") if self._active_nav_key != k else None)
        btn.bind("<Leave>", lambda e, b=btn, k=text_key:
                 b.config(bg="#2c3e50") if self._active_nav_key != k else None)
        self._nav_buttons[text_key] = btn
        return btn

    def _set_active_tab(self, key: str):
        self._active_nav_key = key
        for k, b in self._nav_buttons.items():
            b.config(bg="#1a6fa8" if k == key else "#2c3e50")

    def hide_all_content(self):
        self.map_widget.pack_forget()
        for attr in ('frm_settings', 'frm_stats', 'frm_manual',
                     'frm_schedule', 'frm_sim', 'frm_burnin', 'frm_log'):
            if hasattr(self, attr):
                try:
                    getattr(self, attr).pack_forget()
                except Exception:
                    pass
        if getattr(self.map_widget, '_pos_input_active', False):
            self.map_widget.close_position_input()

    def clear_tool_panel(self):
        for widget in self.tool_frame.winfo_children():
            widget.destroy()

    def update_map_actions(self):
        from agv.agv_instance import SYSTEM_ACTIONS
        combined = SYSTEM_ACTIONS.copy()
        for act in self.ctx.config.get('custom_actions', []):
            try:
                combined[int(act['id'])] = f"{act['id']} - {act['name']}"
            except Exception:
                pass
        self.map_widget.set_action_map(combined)

    # ── Auth ──────────────────────────────────────────────────────────────────

    def lock_interface(self):
        self.map_widget.pack_forget()
        if hasattr(self, 'tool_frame'):
            self.tool_frame.pack_forget()
        for attr in ('frm_settings', 'frm_stats', 'frm_manual',
                     'frm_schedule', 'frm_sim', 'frm_burnin', 'frm_log'):
            if hasattr(self, attr):
                try:
                    getattr(self, attr).pack_forget()
                except Exception:
                    pass
        for widget in self.nav_frame.winfo_children():
            if isinstance(widget, tk.Button) and widget != self.btn_nav_login:
                widget.config(state="disabled")

    def unlock_interface(self):
        for widget in self.nav_frame.winfo_children():
            if isinstance(widget, tk.Button):
                widget.config(state="normal")
        self.tool_frame.pack(side='left', fill='y', expand=False)
        self.show_monitor_view()

    def handle_login_click(self):
        if self.current_user:
            if messagebox.askyesno(self.t("lbl_login_title"), self.t("msg_logout_confirm")):
                self.current_user = None
                self.is_logged_in = False
                self.btn_nav_login.config(text=self.t("nav_login"))
                self.lock_interface()
                self.open_login_window()
        else:
            self.open_login_window()

    def open_login_window(self):
        win = tk.Toplevel(self)
        win.title(self.t("lbl_login_title"))
        win.geometry("300x250")
        if not self.is_logged_in:
            win.transient(self)
            win.grab_set()
            win.protocol("WM_DELETE_WINDOW", lambda: self.destroy())
        ttk.Label(win, text=self.t("lbl_username")).pack(pady=(20, 5))
        ent_user = ttk.Entry(win)
        ent_user.pack(pady=5)
        ent_user.focus_set()
        ttk.Label(win, text=self.t("lbl_password")).pack(pady=5)
        frm_pass = ttk.Frame(win)
        frm_pass.pack(pady=5)
        ent_pass = ttk.Entry(frm_pass, show="*")
        ent_pass.pack(side='left')
        btn_toggle = ttk.Button(frm_pass, text=self.t("btn_show_pass"), width=5)
        btn_toggle.config(command=lambda: self.toggle_password_visibility(ent_pass, btn_toggle))
        btn_toggle.pack(side='left', padx=5)

        def do_login(event=None):
            u, p = ent_user.get(), ent_pass.get()
            if u == "admin" and p == "TNG12345":
                self._finish_login({"username": "admin", "role": "admin"}, "admin\n(admin)", win)
                return
            users = self.ctx.config.get('users', [])
            found = next((user for user in users if user['username'] == u), None)
            if found and found.get('password') == p:
                self._finish_login(found, f"{found['username']}\n({found['role']})", win)
            else:
                messagebox.showerror("Login", self.t("msg_login_fail"))

        win.bind('<Return>', do_login)
        ttk.Button(win, text=self.t("btn_login_action"), command=do_login).pack(pady=20)

    def _finish_login(self, user: dict, btn_text: str, win):
        self.current_user = user
        self.is_logged_in = True
        self.btn_nav_login.config(text=btn_text)
        self.unlock_interface()
        messagebox.showinfo("Login", self.t("msg_login_success"))
        win.destroy()

    def toggle_password_visibility(self, entry_widget, btn_widget=None):
        if entry_widget.cget("show") == "*":
            entry_widget.config(show="")
            if btn_widget:
                btn_widget.config(text=self.t("btn_hide_pass"))
        else:
            entry_widget.config(show="*")
            if btn_widget:
                btn_widget.config(text=self.t("btn_show_pass"))

    def _dev_autologin(self):
        """DEV MODE — auto login admin. Comment this and uncomment open_login_window for prod."""
        self.current_user = {"username": "admin", "role": "admin"}
        self.is_logged_in = True
        self.unlock_interface()
        self.btn_nav_login.config(text="admin\n(dev)")

    # ── Language ──────────────────────────────────────────────────────────────

    def toggle_language(self):
        self.current_lang = "en" if self.current_lang == "vi" else "vi"
        self.ctx.config['language'] = self.current_lang
        self.map_widget.set_lang_data(LANG, self.current_lang)
        self.save_config()
        _prev_active = self._active_nav_key
        self._nav_buttons = {}
        self._active_nav_key = None
        for widget in self.nav_frame.winfo_children():
            widget.destroy()
        self.create_nav_button("nav_monitor",  self.show_monitor_view)
        self.create_nav_button("nav_editor",   self.show_editor_view)
        self.create_nav_button("nav_manual",   self.show_manual_control_view)
        self.create_nav_button("nav_stats",    self.show_stats_view)
        self.create_nav_button("nav_settings", self.show_settings_view)
        self.create_nav_button("nav_schedule", self.show_schedule_view)
        if _prev_active:
            self._set_active_tab(_prev_active)
        login_text = self.t("nav_login")
        if self.current_user:
            login_text = f"{self.current_user['username']}\n({self.current_user['role']})"
        self.btn_nav_login = tk.Button(
            self.nav_frame, text=login_text, command=self.handle_login_click,
            bg="#2c3e50", fg="white", relief="flat",
            font=("Arial", 10, "bold"), height=3, width=8)
        self.btn_nav_login.pack(side='bottom', pady=20, padx=2)
        self.btn_nav_login.bind("<Enter>", lambda e: self.btn_nav_login.config(bg="#34495e"))
        self.btn_nav_login.bind("<Leave>", lambda e: self.btn_nav_login.config(bg="#2c3e50"))
        self.show_settings_view()

    # ── Connection status ─────────────────────────────────────────────────────

    def update_connection_status(self):
        connected = self.ctx.mqtt_connected
        _cv_wifi_ok   = (hasattr(self, 'cv_wifi')   and self.cv_wifi.winfo_exists())
        _cv_broker_ok = (hasattr(self, 'cv_broker') and self.cv_broker.winfo_exists())
        if _cv_wifi_ok or _cv_broker_ok:
            broker_color = "#2ecc71" if connected else "gray"
            if _cv_broker_ok:
                self.cv_broker.itemconfig("status", fill=broker_color)
            wifi_color = "gray"
            if connected:
                wifi_color = "#2ecc71"
            if wifi_color == "gray":
                try:
                    broker_ip = self.ctx.config['mqtt']['broker']
                    port = self.ctx.config['mqtt']['port']
                    sock = socket.create_connection((broker_ip, port), timeout=0.2)
                    if sock:
                        wifi_color = "#2ecc71"
                        sock.close()
                except Exception:
                    pass
            if wifi_color == "gray":
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    s.connect(("8.8.8.8", 80))
                    local_ip = s.getsockname()[0]
                    s.close()
                    if not local_ip.startswith("127."):
                        wifi_color = "#2ecc71"
                except Exception:
                    pass
            if _cv_wifi_ok:
                self.cv_wifi.itemconfig("status", fill=wifi_color)
        if hasattr(self, 'lbl_mqtt_conn_status'):
            try:
                if connected:
                    self.lbl_mqtt_conn_status.config(text="✔ Đã kết nối", foreground="#2ecc71")
                else:
                    self.lbl_mqtt_conn_status.config(text="✘ Mất kết nối", foreground="red")
            except Exception:
                pass
        if hasattr(self, 'lbl_active_topics'):
            try:
                agv_list = self.ctx.agv_list
                if agv_list:
                    lines = []
                    for agv in agv_list:
                        lines.append(f"  {agv.id}:")
                        lines.append(f"    SUB → {agv.topic_order}")
                        lines.append(f"    PUB → {agv.topic_state}")
                    self.lbl_active_topics.config(text="\n".join(lines), foreground="#2c3e50")
                else:
                    self.lbl_active_topics.config(text="(Chưa có AGV)", foreground="gray")
            except Exception:
                pass
        self.after(2000, self.update_connection_status)

    # ── Config save ───────────────────────────────────────────────────────────

    def save_config(self):
        from config_mgmt.settings_io import save_config
        save_config(self.ctx.config)

    # ── Background loops (wired via tk.after) ─────────────────────────────────

    def _run_traffic_control(self):
        """Traffic control loop (500ms)."""
        ctx = self.ctx
        congestion_timeout = ctx.config.get('traffic', {}).get('deadlock_timeout', 10)
        for agv in ctx.agv_list:
            if agv.is_navigating and agv.full_path:
                try:
                    if agv.current_tag in agv.full_path:
                        idx        = agv.full_path.index(agv.current_tag)
                        next_nodes = agv.full_path[idx+1: idx+3]
                        allowed    = ctx.planner.try_reserve_path(agv.id, agv.current_tag, next_nodes)
                        if not allowed:
                            if agv.blocked_start_time is None:
                                agv.blocked_start_time = time.time()
                            else:
                                elapsed = time.time() - agv.blocked_start_time
                                if elapsed > congestion_timeout:
                                    blocked_node = next_nodes[0]
                                    target_node  = agv.full_path[-1]
                                    new_path = ctx.planner.find_path_avoiding(
                                        agv.current_tag, target_node, avoid_nodes=[blocked_node])
                                    if new_path:
                                        _prev_bp = agv.prev_tag if agv.prev_tag > 0 else None
                                        agv.set_path(new_path, ctx.planner.graph, agv.current_task_type)
                                        agv.blocked_start_time = None
                                    else:
                                        agv.blocked_start_time = time.time()
                        else:
                            agv.blocked_start_time = None
                except ValueError:
                    pass

        # Edge conflict check
        from traffic.conflict_manager import RollingRePlanner as _RC
        for agv in ctx.agv_list:
            if not agv.is_navigating or not agv.next_tag:
                if agv.edge_hold:
                    agv.edge_hold = False
                    if agv._edge_hold_segment:
                        agv.resume_from_edge_hold()
                continue
            edge_blocked, blocker = _RC.check_edge_conflict(agv, ctx.agv_list)
            if edge_blocked and blocker:
                from traffic.conflict_manager import MISSION_PRIORITY
                if MISSION_PRIORITY.get(agv.current_task_type, 99) >= MISSION_PRIORITY.get(blocker.current_task_type, 99):
                    agv.edge_hold = True
            else:
                if agv.edge_hold:
                    agv.resume_from_edge_hold()

        # Rolling re-plan
        ctx.replanner.tick(ctx.agv_list, ctx.planner)

        # WHCA* planner
        for agv in ctx.agv_list:
            if agv.is_navigating:
                ctx.whca.update_plan(agv)
            else:
                ctx.whca.clear_plan(agv.id)
                if agv.whca_hold:
                    agv.whca_hold    = False
                    agv.whca_waiting = False

        for agv in ctx.agv_list:
            if not agv.is_navigating or agv.zone_waiting:
                continue
            should_hold, reason = ctx.whca.should_hold(agv.id)
            if should_hold and not agv.whca_hold:
                conflict_nodes = ctx.whca.get_conflict_nodes(agv.id)
                bypassed = False
                if conflict_nodes and agv.full_path and agv.current_tag:
                    first_conflict = conflict_nodes[0]
                    target_node    = agv.full_path[-1]
                    bypass_zone, slot_node = ctx.zone_mgr.find_bypass_zone_for_conflict(agv.current_tag)
                    if bypass_zone and slot_node:
                        slot_path = ctx.planner.find_path_smart(
                            agv.current_tag, slot_node, prev_node=agv.prev_tag,
                            soft_avoid={first_conflict: 60})
                        if slot_path:
                            reserved = ctx.zone_mgr.request_bypass_slot(agv.id, bypass_zone.id)
                            if reserved:
                                agv.bypass_dest    = target_node
                                agv.bypass_zone_id = bypass_zone.id
                                agv.set_path(slot_path, ctx.planner.graph, agv.current_task_type)
                                agv.blocked_start_time = None
                                bypassed = True
                    if not bypassed:
                        soft_map    = {n: 60 for n in conflict_nodes}
                        bypass_path = ctx.planner.find_path_smart(
                            agv.current_tag, target_node, prev_node=agv.prev_tag, soft_avoid=soft_map)
                        if bypass_path and bypass_path != agv.full_path:
                            agv.set_path(bypass_path, ctx.planner.graph, agv.current_task_type)
                            agv.blocked_start_time = None
                            bypassed = True
                if not bypassed:
                    agv.whca_hold = True
            elif not should_hold and agv.whca_hold:
                agv.whca_hold = False
                if agv.whca_waiting:
                    agv.resume_from_whca()

        # Bypass slot exit
        for agv in ctx.agv_list:
            if not agv.bypass_holding:
                continue
            dest = agv.bypass_dest
            slot = agv.current_tag
            if not dest or not ctx.planner.graph.has_node(dest):
                continue
            exit_path  = ctx.planner.find_path_directed(slot, dest, prev_node=agv.prev_tag)
            if not exit_path:
                continue
            exit_nodes = set(exit_path[1: ctx.whca.window + 2])
            lane_clear = not any(
                a.id != agv.id and a.current_tag in exit_nodes
                and (a.is_navigating or a.bypass_holding)
                for a in ctx.agv_list)
            if lane_clear:
                agv.bypass_holding = False
                agv.bypass_dest    = None
                ctx.zone_mgr.release_bypass_slot(agv.id)
                agv.bypass_zone_id = None
                agv.set_path(exit_path, ctx.planner.graph, agv.current_task_type)

        # Zone manager
        if ctx.zone_mgr and ctx.zone_mgr.is_enabled():
            for agv in ctx.agv_list:
                if agv.current_tag:
                    if agv.is_navigating:
                        ctx.zone_mgr.release_zones_not_in(agv.id, agv.current_tag)
                    else:
                        ctx.zone_mgr.release_all(agv.id)
            ready_agvs = ctx.zone_mgr.tick_waiting_agvs(ctx.agv_list)
            for agv in ready_agvs:
                agv.resume_from_zone_wait()

        self.after(500, self._run_traffic_control)

    def _run_hmi_handler(self):
        """HMI handler loop (1s). Delegates to RequestHandler."""
        if self.ctx.request_handler:
            self.ctx.request_handler.run_hmi_handler()
        self.after(1000, self._run_hmi_handler)

    def _run_scheduler(self):
        """Scheduler loop (10s). Delegates to Scheduler."""
        if self.ctx.scheduler:
            self.ctx.scheduler.run()
        self.after(10000, self._run_scheduler)

    # ── Shared helpers ────────────────────────────────────────────────────────

    def send_cmd(self, cmd: str):
        agv_id = getattr(self, 'cb_agv_sel', None)
        if agv_id:
            agv_id = agv_id.get()
        selected = next((a for a in self.ctx.agv_list if a.id == agv_id), None)
        if selected:
            selected.send_command(cmd)
            print(f"Sent {cmd} to {agv_id}")

    def btn_force_set_pos(self):
        agv_id = self.cb_agv_sel.get() if hasattr(self, 'cb_agv_sel') else None
        selected = next((a for a in self.ctx.agv_list if a.id == agv_id), None)
        if selected:
            node_str = simpledialog.askstring("Force Position", f"Enter current Node ID for {agv_id}:")
            if node_str and node_str.isdigit():
                node = int(node_str)
                selected.current_tag = node
                selected.last_update = time.time()
                print(f"Force set {agv_id} to Node {node}")

    def get_current_node_id(self) -> int:
        try:
            val = int(self.var_node_id.get())
            self.var_node_id.set(str(val + 1))
            return val
        except (AttributeError, ValueError):
            return 0

    def btn_load_map(self):
        filename = filedialog.askopenfilename(filetypes=[("JSON Files", "*.json")])
        if filename:
            self.ctx.planner.load_map(filename)
            self.ctx.config['map_file'] = filename
            self.save_config()
            self.map_widget.draw_map()
            if hasattr(self, 'lbl_map_name'):
                self.lbl_map_name.config(text=f"Map: {os.path.basename(filename)}")
            print(f"Loaded map: {filename}")

    def btn_save_as(self):
        filename = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("JSON Files", "*.json")])
        if filename:
            self.ctx.planner.map_file = filename
            self.ctx.planner.save_map()
            self.ctx.config['map_file'] = filename
            self.save_config()
            if hasattr(self, 'lbl_map_name'):
                self.lbl_map_name.config(text=f"Map: {os.path.basename(filename)}")
            print(f"Saved map as: {filename}")

    def add_order_to_queue(self, team_id: int):
        if self.ctx.request_handler:
            self.ctx.request_handler.add_to_queue(team_id)

    def update_monitor_table(self):
        if not hasattr(self, 'tree_agv') or not self.tree_agv.winfo_exists():
            return
        for item in self.tree_agv.get_children():
            self.tree_agv.delete(item)
        for agv in self.ctx.agv_list:
            lifecycle       = getattr(agv, 'task_lifecycle', 'free')
            battery_low     = getattr(agv, 'battery_low',     False)
            battery_blocking = getattr(agv, 'battery_blocking', False)
            tag = rssi      = "N/A"
            row_tag         = "lost"
            if (time.time() - agv.last_update) < 3.0:
                tag     = str(agv.current_tag)
                rssi    = str(agv.rssi)
                row_tag = "bat_low" if battery_blocking else lifecycle
            if battery_blocking:
                bat_str = "🔴 Sạc"
            elif battery_low:
                bat_str = "⚠ Yếu"
            else:
                bat_str = "🟢 OK"
            self.tree_agv.insert("", "end",
                                 values=(agv.id, tag, lifecycle, rssi, bat_str),
                                 tags=(row_tag,))
            # Xử lý battery_blocking: điều về trạm + đếm 2h
            self._handle_battery_blocking(agv)
        # Queue label
        if hasattr(self, 'lbl_queue') and self.lbl_queue.winfo_exists():
            rh  = self.ctx.request_handler
            oq  = rh.order_queue if rh else []
            home_node = self.ctx.config.get('home_node_id', 10)
            if oq:
                avail = [a for a in self.ctx.agv_list if a.is_available([home_node])]
                q_text = f"Tổ đang chờ: {oq}"
                if avail:
                    q_status = f"⏳ Đang giao cho {avail[0].id}..."
                else:
                    busy = [a for a in self.ctx.agv_list
                            if a.is_navigating or a.task_lifecycle not in ("free", "idle", "")]
                    status_detail = f"{busy[0].id}: {busy[0].task_lifecycle}" if busy else f"chờ xe về trạm {home_node}"
                    q_status = f"🔴 Chờ xe rảnh ({status_detail})"
                self.lbl_queue.config(
                    text=f"{q_text}\n{q_status}", foreground="red" if not avail else "blue")
            else:
                self.lbl_queue.config(text="[Không có lệnh chờ]", foreground="gray")
        # Active tasks
        if hasattr(self, 'tree_routes') and self.tree_routes.winfo_exists():
            for item in self.tree_routes.get_children():
                self.tree_routes.delete(item)
            for agv in self.ctx.agv_list:
                if agv.full_path:
                    dest      = agv.full_path[-1]
                    task_type = getattr(agv, 'current_task_type', 'idle')
                    self.tree_routes.insert("", "end", values=(agv.id, dest, task_type))
        self.after(1000, self.update_monitor_table)

    # ── Battery blocking handler ──────────────────────────────────────────────

    def _handle_battery_blocking(self, agv) -> None:
        """Tự động điều AGV về trạm sạc khi battery_blocking=True,
        theo dõi thời gian sạc, và gửi battery_unlock sau ≥2h + pin đã hồi."""
        if not agv.battery_blocking:
            # Nếu không còn blocking → reset timer (phòng trường hợp đã unlock)
            agv._charge_start_time = None
            return

        chargers = self.ctx.config.get('chargers', [])
        if not chargers:
            return  # Chưa cấu hình trạm sạc

        # Xác định charger node gần nhất (theo path length)
        planner = self.ctx.planner
        best_charger_node = None
        best_len = float('inf')
        for c in chargers:
            cnode = c.get('id')
            if not cnode or not planner.graph.has_node(cnode):
                continue
            # Ưu tiên charger được gán cho AGV này
            assigned = c.get('assigned_agv', '')
            if assigned and str(assigned) != str(agv.id):
                continue  # bỏ qua charger gán cho xe khác
            try:
                path = planner.find_path(agv.current_tag, cnode)
                if path and len(path) < best_len:
                    best_len = len(path)
                    best_charger_node = cnode
            except Exception:
                pass

        # Fallback: thử tất cả charger nếu không có cái nào được gán cho xe này
        if best_charger_node is None:
            for c in chargers:
                cnode = c.get('id')
                if not cnode or not planner.graph.has_node(cnode):
                    continue
                try:
                    path = planner.find_path(agv.current_tag, cnode)
                    if path and len(path) < best_len:
                        best_len = len(path)
                        best_charger_node = cnode
                except Exception:
                    pass

        if best_charger_node is None:
            return  # Không tìm được trạm sạc

        # ── Bước 1: Điều về trạm nếu chưa đang điều ──────────────────────────
        already_going_to_charger = (
            agv.is_navigating
            and agv.full_path
            and agv.full_path[-1] == best_charger_node
        )
        at_charger = (agv.current_tag == best_charger_node)

        if not at_charger and not already_going_to_charger and not agv.is_navigating:
            path = planner.find_path_directed(
                agv.current_tag, best_charger_node, prev_node=agv.prev_tag
            )
            if not path:
                path = planner.find_path(agv.current_tag, best_charger_node)
            if path and len(path) > 1:
                agv.set_path(path, planner.graph, task_type="return")
                agv.task_lifecycle = "returning"
                print(f"[BAT] {agv.id}: Pin yếu → điều về trạm sạc {best_charger_node}")

        # ── Bước 2: Xe đã đến trạm → bắt đầu đếm giờ ────────────────────────
        if at_charger and agv._charge_start_time is None:
            agv._charge_start_time = time.time()
            print(f"[BAT] {agv.id}: Đã về trạm sạc {best_charger_node} — bắt đầu đếm 2h")

        # ── Bước 3: Kiểm tra điều kiện unlock ────────────────────────────────
        if agv._charge_start_time is not None:
            elapsed = time.time() - agv._charge_start_time
            if elapsed >= agv.CHARGE_MIN_SECONDS and not agv.battery_low:
                agv.send_command("battery_unlock")
                agv.battery_blocking    = False
                agv._charge_start_time  = None
                print(f"[BAT] {agv.id}: Đã sạc {elapsed/3600:.1f}h + pin hồi → gửi battery_unlock")

    # ── Position input helpers ────────────────────────────────────────────────

    def _apply_agv_positions(self, positions: dict):
        for agv in self.ctx.agv_list:
            if agv.id not in positions:
                continue
            node_id, prev_node = positions[agv.id]
            agv.current_tag   = node_id
            agv.prev_tag      = prev_node if prev_node else 0
            agv.action_info   = "idle"
            agv.status        = "auto"
            agv.is_navigating = False
            agv.task_lifecycle = "free"
            agv.full_path      = []
            print(f"[POS INPUT] {agv.id}: current={node_id}, prev={prev_node}")
        messagebox.showinfo("Đã áp dụng",
                            f"Đã cập nhật vị trí {len(positions)} AGV.\n"
                            "Có thể dispatch lệnh ngay bây giờ.")

    def _manual_apply_positions(self, positions: dict):
        for agv in self.ctx.agv_list:
            if agv.id not in positions:
                continue
            node_id, prev_node = positions[agv.id]
            agv.current_tag = node_id
            agv.prev_tag    = prev_node if prev_node else 0
            print(f"[MANUAL POS] {agv.id}: tag={node_id}, prev={prev_node}")
        self.map_widget.close_position_input()

    def _open_sim_panel(self):
        self.show_sim_view()

    # ── View routing ──────────────────────────────────────────────────────────

    def show_monitor_view(self):
        self._set_active_tab("nav_monitor")
        self.clear_tool_panel()
        self.hide_all_content()
        self.tool_frame.pack(side='left', fill='y', expand=False)
        from gui.monitor_view import build_panel
        build_panel(self)

    def show_editor_view(self):
        self._set_active_tab("nav_editor")
        self.clear_tool_panel()
        self.hide_all_content()
        self.tool_frame.pack(side='left', fill='y', expand=False)
        from gui.editor_view import build_panel
        build_panel(self)

    def show_settings_view(self):
        self._set_active_tab("nav_settings")
        self.clear_tool_panel()
        self.hide_all_content()
        self.tool_frame.pack_forget()
        from gui.settings_view import build_panel
        build_panel(self)

    def show_manual_control_view(self):
        self._set_active_tab("nav_manual")
        self.clear_tool_panel()
        self.hide_all_content()
        self.tool_frame.pack_forget()   # manual view creates its own right panel
        from gui.manual_control_view import build_panel
        build_panel(self)

    def show_stats_view(self):
        self._set_active_tab("nav_stats")
        self.clear_tool_panel()
        self.hide_all_content()
        self.tool_frame.pack_forget()
        from gui.stats_view import build_panel
        build_panel(self)

    def show_schedule_view(self):
        self._set_active_tab("nav_schedule")
        self.clear_tool_panel()
        self.hide_all_content()
        self.tool_frame.pack_forget()
        from gui.schedule_view import build_panel
        build_panel(self)

    def show_sim_view(self):
        self._set_active_tab("nav_sim")
        self.clear_tool_panel()
        self.hide_all_content()
        self.tool_frame.pack_forget()
        self.frm_sim = tk.Frame(self.content_frame, bg="white")
        self.frm_sim.pack(fill='both', expand=True)
        from simulation.sim_panel import SimulationPanel
        SimulationPanel(self.frm_sim, self.ctx.sim_engine, self.ctx.planner, self.ctx.config)

    def show_burnin_view(self):
        self._set_active_tab("nav_burnin")
        self.clear_tool_panel()
        self.hide_all_content()
        self.tool_frame.pack_forget()
        from gui.burnin_view import build_panel
        build_panel(self)

    def show_log_view(self):
        self._set_active_tab("nav_log")
        self.clear_tool_panel()
        self.hide_all_content()
        self.tool_frame.pack_forget()
        from gui.log_view import build_panel
        build_panel(self)

    # ── Map tool helper ───────────────────────────────────────────────────────

    def set_map_tool(self, tool: str):
        self.map_widget.set_tool(tool)

    def _update_map_name_label(self, filepath: str):
        name = os.path.basename(filepath)
        if hasattr(self, 'lbl_map_name'):
            self.lbl_map_name.config(text=f"Map: {name}")
        if hasattr(self, 'lbl_map_name_editor'):
            self.lbl_map_name_editor.config(text=f"📄 {name}")

    # ── Dispatch actions (wired from monitor_view) ────────────────────────────

    def btn_auto_dispatch_click(self):
        target_str = simpledialog.askstring("Gọi xe / Call AGV",
                                            "Nhập ID Tổ / Enter Team ID (e.g., 1, 4):")
        if not target_str:
            return
        if target_str.strip().isdigit():
            team_id = int(target_str.strip())
            self.add_order_to_queue(team_id)
            messagebox.showinfo("Info",
                                f"Đã thêm Tổ {team_id} vào hàng đợi.\n"
                                f"Team {team_id} call added to Queue.")
        else:
            messagebox.showwarning("Warning",
                                   "Vui lòng nhập số nguyên ID Tổ hợp lệ.\n"
                                   "Please enter a valid integer Team ID.")

    def btn_dispatch_click(self):
        import math as _m
        agv_id     = self.cb_agv_sel.get()
        target     = self.cb_target_node.get()
        start_mode = self.cb_start_node.get()
        task_type  = self.cb_task_type.get()
        planner    = self.ctx.planner

        selected_agv = next((a for a in self.ctx.agv_list if a.id == agv_id), None)
        if not selected_agv or not target:
            return
        try:
            start_node = (selected_agv.current_tag if start_mode == "Current Position"
                          else int(start_mode))
            if start_node == 0:
                print("AGV position unknown, please select a start node manually.")
                return
            target_int = int(target)

            _prev = selected_agv.prev_tag if selected_agv.prev_tag > 0 else None
            start_heading = None
            dir_label = self.cb_dispatch_dir.get() if hasattr(self, 'cb_dispatch_dir') else ""
            dir_entry = self._dispatch_facing_map.get(dir_label) \
                if hasattr(self, '_dispatch_facing_map') else None
            if isinstance(dir_entry, tuple):
                facing_nb, prev_nb = dir_entry
                if prev_nb is not None:
                    _prev = prev_nb
                try:
                    _sn = planner.graph.nodes[int(start_node)]
                    _fn = planner.graph.nodes[facing_nb]
                    _dx = _fn.get('disp_x', _fn.get('x', 0)) - _sn.get('disp_x', _sn.get('x', 0))
                    _dy = _fn.get('disp_y', _fn.get('y', 0)) - _sn.get('disp_y', _sn.get('y', 0))
                    _mag = _m.hypot(_dx, _dy)
                    if _mag > 1e-6:
                        start_heading = (_dx / _mag, _dy / _mag)
                except Exception:
                    pass

            path = planner.find_path_directed(int(start_node), target_int, prev_node=_prev)

            if not path:
                target_attrs = planner.graph.nodes.get(target_int, {})
                if target_attrs.get('role') == 'charger':
                    rev_src = planner.find_path(target_int, int(start_node))
                    if rev_src:
                        reverse_path_full = list(reversed(rev_src))
                        approach_node = (reverse_path_full[1]
                                         if len(reverse_path_full) >= 2 else None)
                        first_step_bwd = False
                        if _prev and approach_node and len(reverse_path_full) >= 2:
                            first_step_bwd = planner._backward_cost(
                                _prev, int(start_node), approach_node, 1) > 0
                        if first_step_bwd and approach_node and approach_node != int(start_node):
                            fwd_to_approach = planner.find_path_directed(
                                int(start_node), approach_node, prev_node=_prev)
                            if fwd_to_approach and len(fwd_to_approach) > 1:
                                selected_agv._pre_return_charger = {'node_id': target_int}
                                path = fwd_to_approach
                                task_type = "return_charge"
                            else:
                                path = reverse_path_full
                                task_type = "return_reversing_charge"
                        else:
                            path = reverse_path_full
                            task_type = "return_reversing_charge"

            if path:
                rh = self.ctx.request_handler
                _facing_tag = dir_entry[0] if isinstance(dir_entry, tuple) else None
                precomp_steps, sim_path = rh._run_dry_run_for_path(
                    path, _prev, task_type,
                    end_tag_override=target_int,
                    facing_tag=_facing_tag)
                if sim_path and sim_path != list(path):
                    path = sim_path
                selected_agv.set_path(path, planner.graph, task_type,
                                      start_heading=start_heading,
                                      precomp_steps=precomp_steps)
                selected_agv.task_lifecycle = "assigned"
                self.update_monitor_table()
                self.map_widget.draw_map()
            else:
                print(f"No path found from {start_node} to {target}")
        except ValueError:
            print("Invalid node ID")

    def btn_workflow_dispatch_click(self):
        import math as _m
        agv_id     = self.cb_agv_sel.get()
        start_mode = self.cb_start_node.get()
        team_str   = self.cb_workflow_team.get() if hasattr(self, 'cb_workflow_team') else ""
        planner    = self.ctx.planner

        selected_agv = next((a for a in self.ctx.agv_list if a.id == agv_id), None)
        if not selected_agv:
            messagebox.showwarning("Lỗi", "Chưa chọn AGV.")
            return
        if not team_str or "(Chưa cấu hình" in team_str:
            messagebox.showwarning("Lỗi", "Chưa cấu hình tổ. Vào Cài đặt → Station Config.")
            return
        try:
            start_node = (selected_agv.current_tag if start_mode == "Current Position"
                          else int(start_mode))
        except ValueError:
            messagebox.showwarning("Lỗi", "Vị trí bắt đầu không hợp lệ.")
            return
        if not start_node or not planner.graph.has_node(start_node):
            messagebox.showwarning("Lỗi", f"Thẻ bắt đầu {start_node} không tồn tại trên bản đồ.")
            return
        try:
            team_id = int(team_str.split("—")[0].strip())
        except (ValueError, IndexError):
            messagebox.showwarning("Lỗi", "Không đọc được ID tổ từ lựa chọn.")
            return

        station_cfg = self.ctx.config.get('station_config', [])
        team_cfg = next((t for t in station_cfg if t['id'] == team_id), None)
        if not team_cfg:
            messagebox.showerror("Lỗi", f"Không tìm thấy cấu hình Tổ {team_id} trong Settings.")
            return
        wait_node     = team_cfg.get('wait')
        delivery_node = team_cfg.get('delivery')
        if not wait_node or not delivery_node:
            messagebox.showerror("Lỗi", f"Tổ {team_id} thiếu cấu hình wait/delivery node.")
            return

        _prev = selected_agv.prev_tag if selected_agv.prev_tag > 0 else None
        start_heading = None
        dir_label = self.cb_dispatch_dir.get() if hasattr(self, 'cb_dispatch_dir') else ""
        dir_entry = self._dispatch_facing_map.get(dir_label) \
            if hasattr(self, '_dispatch_facing_map') else None
        _facing_wf = None
        if isinstance(dir_entry, tuple):
            facing_nb, prev_nb = dir_entry
            _facing_wf = facing_nb
            if prev_nb is not None:
                _prev = prev_nb
            try:
                _sn = planner.graph.nodes[int(start_node)]
                _fn = planner.graph.nodes[facing_nb]
                _dx = _fn.get('disp_x', _fn.get('x', 0)) - _sn.get('disp_x', _sn.get('x', 0))
                _dy = _fn.get('disp_y', _fn.get('y', 0)) - _sn.get('disp_y', _sn.get('y', 0))
                _mag = _m.hypot(_dx, _dy)
                if _mag > 1e-6:
                    start_heading = (_dx / _mag, _dy / _mag)
            except Exception:
                pass

        path = planner.find_path_directed(start_node, wait_node, prev_node=_prev)
        if not path:
            messagebox.showerror("Lỗi",
                                 f"Không tìm được đường từ {start_node} đến điểm chờ {wait_node}.")
            return

        rh = self.ctx.request_handler
        precomp_steps, sim_path = rh._run_dry_run_for_path(
            path, _prev, "pickup", facing_tag=_facing_wf)
        if sim_path and sim_path != list(path):
            path = sim_path
        selected_agv.set_path(path, planner.graph, task_type="pickup",
                              start_heading=start_heading,
                              precomp_steps=precomp_steps)
        selected_agv.task_lifecycle            = "assigned"
        selected_agv._pending_delivery_team    = team_id
        selected_agv._remaining_delivery_teams = [team_id]
        selected_agv._pickup_target_node       = wait_node
        selected_agv._mission_dest_node        = wait_node
        print(f"[WORKFLOW] {agv_id}: {start_node}→wait({wait_node})→delivery({delivery_node}) "
              f"heading={start_heading}  prev={_prev}")
        self.update_monitor_table()
        self.map_widget.draw_map()

    def _btn_reset_agv(self):
        agv_id = self.cb_agv_sel.get()
        selected_agv = next((a for a in self.ctx.agv_list if a.id == agv_id), None)
        if not selected_agv:
            return
        if messagebox.askyesno("Reset Arduino",
                               f"Reset Arduino của {agv_id}?\n"
                               "Xe sẽ khởi động lại, mất kết nối ~3 giây."):
            selected_agv.send_command("reset")
            print(f"[RESET] Sent reset to {agv_id}")

    def _show_task_log(self):
        from agv.agv_instance import ACTION_NAMES
        agv_id   = self.cb_agv_sel.get()
        agv_list = self.ctx.agv_list

        win = tk.Toplevel(self)
        win.title(f"📋 Log nhiệm vụ — {agv_id}")
        win.geometry("580x480")
        win.resizable(True, True)

        hdr = tk.Frame(win, bg="#2c3e50")
        hdr.pack(fill='x')
        tk.Label(hdr, text=f"AGV: {agv_id}", bg="#2c3e50", fg="white",
                 font=("Arial", 10, "bold")).pack(side='left', padx=8, pady=4)
        lbl_seg  = tk.Label(hdr, text="", bg="#2c3e50", fg="#aed6f1", font=("Arial", 9))
        lbl_seg.pack(side='left', padx=4)
        lbl_dest = tk.Label(hdr, text="", bg="#2c3e50", fg="#f9ca24",
                            font=("Arial", 9, "bold"))
        lbl_dest.pack(side='right', padx=8)

        leg = tk.Frame(win, bg="#ecf0f1")
        leg.pack(fill='x')
        for text, color in [("RUN", "#27ae60"), ("TURN_R/L", "#e67e22"),
                            ("ROTATE_180", "#c0392b"), ("DIR_FWD/BWD", "#8e44ad"),
                            ("SPEED", "#2980b9"), ("LIDAR/BRAKE", "#7f8c8d")]:
            tk.Label(leg, text=f"■ {text}", fg=color, bg="#ecf0f1",
                     font=("Arial", 8)).pack(side='left', padx=6)
        tk.Label(leg, text="● Đang ở", fg="#00cc44", bg="#ecf0f1",
                 font=("Arial", 8, "bold")).pack(side='left', padx=6)

        frame_lb = tk.Frame(win)
        frame_lb.pack(fill='both', expand=True, padx=6, pady=4)
        sb = tk.Scrollbar(frame_lb)
        sb.pack(side='right', fill='y')
        lb = tk.Listbox(frame_lb, yscrollcommand=sb.set, font=("Consolas", 9),
                        selectmode='browse', activestyle='none')
        lb.pack(fill='both', expand=True)
        sb.config(command=lb.yview)

        action_colors = {
            3: "#27ae60", 5: "#e67e22", 6: "#e67e22", 9: "#c0392b",
            7: "#8e44ad", 8: "#8e44ad", 4: "#2980b9",
            20: "#7f8c8d", 21: "#7f8c8d", 28: "#7f8c8d", 29: "#7f8c8d",
            1: "#95a5a6", 2: "#e74c3c",
        }
        _state = {'last_tag': None, 'last_plan_len': 0}

        def _populate(scroll_to_current=False):
            agv2 = next((a for a in agv_list if a.id == agv_id), None)
            if not agv2:
                return
            plan    = agv2.full_plan_data if agv2.full_plan_data else agv2.last_plan_data
            cur_tag = agv2.current_tag
            lb.delete(0, 'end')
            if not plan:
                lb.insert('end', "  (Chưa có dữ liệu — hãy giao nhiệm vụ trước)")
                lb.itemconfig(0, fg="#999999")
                return
            row_idx = 0
            first_cur_row = None
            prev_tag_val  = None
            for step in plan:
                tag  = step.get('t', '?')
                act  = step.get('a', 0)
                val  = step.get('v', 0)
                name = ACTION_NAMES.get(act, f"#{act}")
                if tag != prev_tag_val and prev_tag_val is not None:
                    lb.insert('end', "  " + "─" * 50)
                    lb.itemconfig(row_idx, fg="#dddddd")
                    row_idx += 1
                v_str  = f"  [v={val}]" if val else ""
                is_cur = (tag == cur_tag)
                dot    = "●" if is_cur else " "
                lb.insert('end', f"{dot} Thẻ {tag:>4}  │  {name:<14}{v_str}")
                color = "#00cc44" if is_cur else action_colors.get(act, "#333333")
                lb.itemconfig(row_idx, fg=color)
                if is_cur and first_cur_row is None:
                    first_cur_row = row_idx
                row_idx += 1
                prev_tag_val = tag
            nodes_str = " → ".join(str(n) for n in (agv2.last_plan_nodes or []))
            lbl_seg.config(text=f"Segment: {nodes_str}" if nodes_str else "")
            dest = agv2.full_path[-1] if agv2.full_path else "?"
            lbl_dest.config(text=f"Đích: {dest}")
            if scroll_to_current and first_cur_row is not None:
                lb.see(first_cur_row)

        _populate(scroll_to_current=True)

        def _auto_refresh():
            if not win.winfo_exists():
                return
            agv2 = next((a for a in agv_list if a.id == agv_id), None)
            if not agv2:
                win.after(1000, _auto_refresh)
                return
            cur_tag  = agv2.current_tag
            plan_len = len(agv2.full_plan_data) + len(agv2.last_plan_data)
            if cur_tag != _state['last_tag'] or plan_len != _state['last_plan_len']:
                _state['last_tag']      = cur_tag
                _state['last_plan_len'] = plan_len
                _populate(scroll_to_current=(cur_tag != _state['last_tag']))
            win.after(1000, _auto_refresh)

        win.after(1000, _auto_refresh)
        btn_row = tk.Frame(win)
        btn_row.pack(fill='x', padx=6, pady=(0, 6))
        tk.Button(btn_row, text="🔄 Làm mới",
                  command=lambda: _populate(scroll_to_current=True),
                  bg="#3498db", fg="white", font=("Arial", 9, "bold")).pack(side='left', padx=4)
        tk.Button(btn_row, text="✕ Đóng", command=win.destroy,
                  bg="#e74c3c", fg="white", font=("Arial", 9)).pack(side='right', padx=4)

    # ── Editor actions (wired from editor_view) ───────────────────────────────

    def btn_scan_special_tasks(self):
        g = self.ctx.planner.graph
        ACTION_NAMES_LOCAL = {
            0: "NOP", 1: "WAIT_SYS", 2: "WAIT_USER", 3: "RUN",
            4: "SPEED", 5: "TURN_R", 6: "TURN_L",
            7: "DIR_TIẾN", 8: "DIR_LÙI", 9: "ROTATE_180",
            11: "CHARGE", 20: "LIDAR_OFF", 21: "LIDAR_ON",
            22: "NHAC_START", 23: "NHAC_STOP", 24: "NHAC_XIN_LIEU",
            25: "NHAC_MO_CUA", 26: "NHAC_XIN_RE", 27: "NHAC_TAT",
            28: "BRAKE_ON", 29: "BRAKE_OFF",
            30: "HOOK_RAISE", 31: "HOOK_LOWER",
            32: "DEN_VANG", 33: "DEN_XANH", 34: "DEN_TAT",
        }

        def act_name(code):
            try:
                code = int(code)
            except (TypeError, ValueError):
                return str(code)
            custom = self.map_widget.action_map.get(code, "")
            if custom:
                return custom.split(' - ')[-1]
            return ACTION_NAMES_LOCAL.get(code, str(code))

        def fmt_list(lst):
            if not lst:
                return ""
            parts = []
            for item in lst:
                if isinstance(item, dict):
                    code = item.get('id', item.get('code', '?'))
                    val  = item.get('v', item.get('value', ''))
                    parts.append(f"{act_name(code)}(v={val})" if val else act_name(code))
                else:
                    parts.append(act_name(item))
            return ", ".join(parts)

        rows = []
        for u, v, data in g.edges(data=True):
            nav_a     = data.get('a', 3)
            direction = data.get('direction', 'forward')
            allowed   = data.get('allowed', True)
            actions   = data.get('actions', [])
            end_acts  = data.get('end_actions', [])
            is_special_nav = nav_a not in (0, 3)
            has_actions    = bool(actions)
            has_end_acts   = bool(end_acts)
            is_backward    = direction != 'forward'
            is_blocked     = not allowed
            if not any([is_special_nav, has_actions, has_end_acts, is_backward, is_blocked]):
                continue
            flags = []
            if is_special_nav: flags.append(f"Nav={act_name(nav_a)}")
            if has_actions:    flags.append(f"Đầu=[{fmt_list(actions)}]")
            if has_end_acts:   flags.append(f"Cuối=[{fmt_list(end_acts)}]")
            if is_backward:    flags.append("Chiều=LÙI")
            if is_blocked:     flags.append("BLOCKED")
            rows.append((u, v, ", ".join(flags)))

        dlg = tk.Toplevel(self)
        dlg.title(f"🔍 Nhiệm vụ đặc biệt — {len(rows)} cạnh")
        dlg.geometry("720x480")
        dlg.grab_set()

        frm_top = ttk.Frame(dlg)
        frm_top.pack(fill='x', padx=8, pady=(8, 2))
        map_file = getattr(self.ctx.planner, 'map_file', '')
        ttk.Label(frm_top,
                  text=f"Map: {os.path.basename(map_file)}  |  "
                       f"Tổng: {g.number_of_edges()} cạnh  |  "
                       f"Có nhiệm vụ ĐB: {len(rows)} cạnh",
                  font=("Segoe UI", 9)).pack(side='left')

        var_filter = tk.StringVar()
        ttk.Label(frm_top, text="   Lọc:").pack(side='left')
        ent_filter = ttk.Entry(frm_top, textvariable=var_filter, width=14)
        ent_filter.pack(side='left', padx=4)

        cols = ("edge", "details")
        tv = ttk.Treeview(dlg, columns=cols, show='headings', height=22)
        tv.heading("edge",    text="Cạnh (U→V)")
        tv.heading("details", text="Chi tiết nhiệm vụ đặc biệt")
        tv.column("edge",    width=110, anchor='center', stretch=False)
        tv.column("details", width=560)
        sb2 = ttk.Scrollbar(dlg, orient='vertical', command=tv.yview)
        tv.configure(yscrollcommand=sb2.set)
        tv.pack(side='left', fill='both', expand=True, padx=(8, 0), pady=4)
        sb2.pack(side='right', fill='y', pady=4, padx=(0, 4))

        all_rows = rows[:]

        def _populate(filter_text=""):
            tv.delete(*tv.get_children())
            ft = filter_text.strip().lower()
            for u, v, details in all_rows:
                label = f"{u} → {v}"
                if ft and ft not in label.lower() and ft not in details.lower():
                    continue
                tv.insert('', 'end', values=(label, details))

        _populate()
        var_filter.trace_add('write', lambda *_: _populate(var_filter.get()))

        def _on_select(event):
            sel = tv.selection()
            if not sel:
                return
            label = tv.item(sel[0], 'values')[0]
            try:
                parts = label.split('→')
                u = int(parts[0].strip())
                v = int(parts[1].strip())
                self.map_widget.selected_edge  = (u, v)
                self.map_widget.selected_node  = None
                self.map_widget.selected_nodes = set()
                self.map_widget.draw_map()
            except Exception:
                pass

        tv.bind('<<TreeviewSelect>>', _on_select)
        ttk.Button(dlg, text="Đóng", command=dlg.destroy).pack(pady=(0, 6))

    def open_workflow_manager_dialog(self):
        workflow_engine = self.ctx.workflow_engine
        if not workflow_engine:
            messagebox.showwarning("Workflow", "WorkflowEngine chưa được khởi tạo.")
            return

        dialog = tk.Toplevel(self)
        dialog.title("⚡ Workflow Manager — Nhiệm vụ đặc biệt theo Node")
        dialog.geometry("920x560")
        dialog.grab_set()

        MISSION_OPTIONS = ["any", "delivery", "pickup",
                           "return_charge", "return_reversing_charge"]
        STEP_TYPES = ["mqtt_publish", "wait_time", "agv_command",
                      "set_speed", "log_message"]
        STEP_TYPE_VI = {
            "mqtt_publish": "Gửi MQTT (PLC/relay/thiết bị)",
            "wait_time":    "Chờ N giây",
            "agv_command":  "Lệnh AGV (còi, dừng...)",
            "set_speed":    "Đổi tốc độ AGV",
            "log_message":  "Ghi log console",
        }

        frm_left  = ttk.Frame(dialog, padding=8)
        frm_left.pack(side='left', fill='both', expand=True)
        frm_right = ttk.Frame(dialog, padding=8, width=360)
        frm_right.pack(side='right', fill='y')
        frm_right.pack_propagate(False)

        ttk.Label(frm_left, text="Danh sách Rules",
                  font=("Arial", 10, "bold")).pack(anchor='w')
        cols = ("id", "tag", "mission", "desc", "steps", "block")
        tree = ttk.Treeview(frm_left, columns=cols, show='headings', height=14)
        for col, hdr_txt, w in [("id", "Rule ID", 130), ("tag", "Tag", 45),
                                  ("mission", "Mission", 100), ("desc", "Mô tả", 160),
                                  ("steps", "#", 25), ("block", "Block", 40)]:
            tree.heading(col, text=hdr_txt)
            tree.column(col, width=w)
        tree.pack(fill='both', expand=True)

        def refresh_tree():
            tree.delete(*tree.get_children())
            for r in workflow_engine.get_rules():
                tree.insert("", "end", iid=r.get("id", "?"), values=(
                    r.get("id", ""), r.get("tag_id", ""),
                    r.get("mission_type", "any"), r.get("description", ""),
                    len(r.get("steps", [])),
                    "✓" if r.get("blocking", False) else ""))

        refresh_tree()

        # Right panel — edit form (simplified)
        ttk.Label(frm_right, text="Chỉnh sửa Rule",
                  font=("Arial", 10, "bold")).pack(anchor='w', pady=(0, 6))
        ttk.Label(frm_right, text="(Chọn rule bên trái để chỉnh sửa)",
                  foreground="gray", font=("Arial", 9)).pack(anchor='w')

        frm_btn = ttk.Frame(frm_left)
        frm_btn.pack(fill='x', pady=4)

        def _delete_rule():
            sel = tree.selection()
            if not sel:
                return
            rule_id = sel[0]
            if messagebox.askyesno("Xóa Rule", f"Xóa rule '{rule_id}'?"):
                workflow_engine.delete_rule(rule_id)
                workflow_engine.save()
                refresh_tree()

        ttk.Button(frm_btn, text="➕ Thêm Rule",
                   command=lambda: messagebox.showinfo(
                       "Thêm Rule",
                       "Chỉnh sửa file config/tag_actions.json để thêm rule mới.")
                   ).pack(side='left', padx=2)
        ttk.Button(frm_btn, text="🗑️ Xóa Rule",
                   command=_delete_rule).pack(side='left', padx=2)
        ttk.Button(frm_btn, text="🔄 Làm mới",
                   command=refresh_tree).pack(side='left', padx=2)
        ttk.Button(dialog, text="Đóng",
                   command=dialog.destroy).pack(side='bottom', pady=6)

    # ── Position input (editor) ───────────────────────────────────────────────

    def _open_position_input(self):
        self.map_widget.on_apply_positions = self._apply_agv_positions
        self.map_widget.open_position_input()
        if not hasattr(self, '_pos_panel') or not self._pos_panel.winfo_exists():
            self._pos_panel = tk.Toplevel(self)
            self._pos_panel.title("📍 Vị trí AGV")
            self._pos_panel.geometry("280x130")
            self._pos_panel.resizable(False, False)
            self._pos_panel.attributes("-topmost", True)
            ttk.Label(self._pos_panel,
                      text="Kéo AGV đến vị trí mong muốn.\n"
                           "Chuột phải AGV → Quay phải / Quay trái.\n"
                           "Mũi tên trắng = hướng đầu xe.",
                      font=("Arial", 9), foreground="gray").pack(pady=8)
            frm = ttk.Frame(self._pos_panel)
            frm.pack(fill='x', padx=10, pady=4)
            ttk.Button(frm, text="✅ Áp dụng vị trí",
                       command=self._apply_and_close_pos_panel,
                       width=18).pack(side='left', padx=4)
            ttk.Button(frm, text="✖ Hủy",
                       command=self._cancel_pos_panel,
                       width=8).pack(side='left')
            self._pos_panel.protocol("WM_DELETE_WINDOW", self._cancel_pos_panel)

    def _apply_and_close_pos_panel(self):
        self.map_widget.apply_agv_positions()
        if hasattr(self, '_pos_panel') and self._pos_panel.winfo_exists():
            self._pos_panel.destroy()

    def _cancel_pos_panel(self):
        self.map_widget.close_position_input()
        if hasattr(self, '_pos_panel') and self._pos_panel.winfo_exists():
            self._pos_panel.destroy()

    # ── Settings helpers ──────────────────────────────────────────────────────

    def _rebuild_door_maps(self):
        """Rebuild door_check_map cho tất cả AGV từ config hiện tại."""
        door_sensors = self.ctx.config.get('door_sensors', [])
        door_map: dict = {}
        for d in door_sensors:
            tid = d.get('tag_id')
            if tid is not None:
                key = int(tid)
                door_map.setdefault(key, []).append(d)
        for agv in self.ctx.agv_list:
            agv._door_check_map = door_map
        print(f"[DOOR] Door map rebuilt: {len(door_sensors)} entry(s)")

    def save_network_settings(self):
        config = self.ctx.config
        config['mqtt']['broker']   = self.ent_broker.get()
        config['mqtt']['port']     = int(self.ent_port.get())
        config['mqtt']['username'] = self.ent_user.get()
        config['mqtt']['password'] = self.ent_pass.get()
        config['hardware'] = self.ent_hardware.get().strip()
        config['factory']  = self.ent_factory.get().strip()
        config['wifi']     = {"ssid": self.ent_ssid.get(),
                               "password": self.ent_wifi_pass.get()}
        self.save_config()
        hw = config['hardware']
        ft = config['factory']
        for agv in self.ctx.agv_list:
            agv_cfg_saved = next((a for a in config['agvs'] if a['id'] == agv.id), {})
            agv.topic_order = (agv_cfg_saved.get('topic_sub')
                               or f"uagv/v2/{ft}/{agv.id}/order")
            agv.topic_state = (agv_cfg_saved.get('topic_pub')
                               or f"uagv/v2/{ft}/{agv.id}/state")
        print("Network settings saved.")

    def btn_connect_mqtt(self):
        self.save_network_settings()
        config  = self.ctx.config
        broker   = config['mqtt']['broker']
        port     = int(config['mqtt']['port'])
        username = config['mqtt'].get('username', '')
        password = config['mqtt'].get('password', '')
        try:
            self.ctx.mqtt.disconnect()
        except Exception:
            pass
        try:
            import ssl
            if username:
                self.ctx.mqtt.username_pw_set(username, password)
            if port == 8883:
                if not getattr(self.ctx.mqtt, '_tls_set_done', False):
                    self.ctx.mqtt.tls_set(cert_reqs=ssl.CERT_NONE)
                    self.ctx.mqtt.tls_insecure_set(True)
                    self.ctx.mqtt._tls_set_done = True
            self.ctx.mqtt.connect(broker, port, 60)
            if hasattr(self, 'lbl_mqtt_conn_status'):
                self.lbl_mqtt_conn_status.config(text="Đang kết nối...",
                                                  foreground="orange")
            print(f"Connecting to MQTT: {broker}:{port}")
        except Exception as e:
            if hasattr(self, 'lbl_mqtt_conn_status'):
                self.lbl_mqtt_conn_status.config(text="Lỗi kết nối", foreground="red")
            print(f"MQTT connect error: {e}")

    def save_general_settings(self):
        config = self.ctx.config
        try:
            config['work_hours'] = float(self.ent_work_hours.get())
            config['version']    = self.ent_version.get().strip()
            config['dispatch_weights'] = {
                "distance": self.scale_dist.get(),
                "idle":     self.scale_idle.get(),
                "battery":  self.scale_bat.get(),
            }
            self.save_config()
            print("General settings saved.")
        except ValueError:
            messagebox.showerror("Error", "Invalid Work Hours")

    def save_traffic_settings(self):
        config = self.ctx.config
        try:
            config['traffic'] = {
                "safety_dist":      float(self.ent_safe_dist.get()),
                "deadlock_timeout": int(self.ent_deadlock.get()),
                "speed_fast":       int(self.ent_spd_fast.get()),
                "speed_slow":       int(self.ent_spd_slow.get()),
                "lookahead":        int(self.spn_lookahead.get()),
            }
            mpu = float(self.ent_map_mpu.get())
            config.setdefault('map', {})['meters_per_unit'] = mpu
            self.map_widget.meters_per_unit = mpu
            self.map_widget.draw_map()
            self.save_config()
            print(f"Traffic settings saved. Map scale: 1 unit = {mpu} m")
        except ValueError:
            messagebox.showerror("Error", "Invalid Input")

    def save_battery_settings(self):
        config = self.ctx.config
        try:
            config['battery'] = {
                "enabled":           self.var_bat_enable.get(),
                "low_threshold":     int(self.ent_low_bat.get()),
                "resume_threshold":  int(self.ent_resume_bat.get()),
            }
            self.save_config()
            print("Battery settings saved.")
        except ValueError:
            messagebox.showerror("Error", "Invalid Input")

    def save_alarm_settings(self):
        try:
            self.ctx.config['alarms'] = {
                "stuck_timeout": int(self.ent_stuck_time.get())}
            self.save_config()
        except ValueError:
            messagebox.showerror("Error", "Invalid Input")

    def save_user_settings(self):
        config = self.ctx.config
        u = self.ent_usr_name.get()
        r = self.cb_usr_role.get()
        if u and r:
            users = config.get('users', [])
            if any(user['username'] == u for user in users):
                messagebox.showerror("Error", "User already exists")
                return
            users.append({"username": u, "role": r})
            config['users'] = users
            self.save_config()
            self.tree_usr.insert("", "end", values=(u, r, "N/A"))
            messagebox.showinfo("Success", f"User {u} added.")
        else:
            messagebox.showerror("Error", "Missing fields")

    def save_integration_settings(self):
        try:
            self.ctx.config['integration'] = {
                "api_enabled": self.var_api_enable.get(),
                "api_port":    int(self.ent_api_port.get()),
            }
            self.save_config()
        except ValueError:
            messagebox.showerror("Error", "Invalid Port")

    def add_custom_action(self):
        config = self.ctx.config
        try:
            aid  = int(self.ent_act_id.get())
            name = self.ent_act_name.get()
            if aid < 20:
                messagebox.showwarning("Warning",
                                       "IDs 0-19 are reserved. Please use ID >= 20.")
                return
            if not name:
                return
            acts = config.get('custom_actions', [])
            acts = [a for a in acts if a['id'] != aid]
            acts.append({"id": aid, "name": name})
            acts.sort(key=lambda x: x['id'])
            config['custom_actions'] = acts
            self.save_config()
            self.show_settings_view()
            self.update_map_actions()
        except ValueError:
            messagebox.showerror("Error", "Invalid ID")

    def del_custom_action(self):
        sel = self.tree_act.selection() if hasattr(self, 'tree_act') else []
        if not sel:
            return
        vals = self.tree_act.item(sel[0])['values']
        try:
            aid = int(vals[0])
        except (IndexError, ValueError):
            return
        config = self.ctx.config
        config['custom_actions'] = [a for a in config.get('custom_actions', [])
                                     if a['id'] != aid]
        self.save_config()
        self.tree_act.delete(sel[0])
        self.update_map_actions()

    def refresh_agv_settings_tree(self):
        config   = self.ctx.config
        factory  = config.get('factory',  'default')
        hardware = config.get('hardware', 'hardware')
        for item in self.tree_settings_agv.get_children():
            self.tree_settings_agv.delete(item)
        for agv in config.get('agvs', []):
            color       = agv.get('color', '#3498db')
            agv_id      = agv['id']
            topic_sub   = (agv.get('topic_sub')
                           or f"AGV/{hardware}/{factory}/{agv_id}/sub")
            topic_pub   = (agv.get('topic_pub')
                           or f"AGV/{hardware}/{factory}/{agv_id}/pub")
            self.tree_settings_agv.insert("", "end",
                values=(agv_id, agv.get('ip', ''), topic_sub, topic_pub, "██████"),
                tags=(color,))
            self.tree_settings_agv.tag_configure(color, foreground=color)

    def on_agv_select(self, event):
        selected = self.tree_settings_agv.selection()
        if not selected:
            return
        item   = self.tree_settings_agv.item(selected[0])
        vals   = item['values']
        agv_id = str(vals[0])
        self.ent_agv_id.delete(0, 'end');  self.ent_agv_id.insert(0, agv_id)
        self.ent_agv_ip.delete(0, 'end');  self.ent_agv_ip.insert(0, vals[1])
        self.ent_agv_sub.delete(0, 'end'); self.ent_agv_sub.insert(0, vals[2])
        self.ent_agv_pub.delete(0, 'end'); self.ent_agv_pub.insert(0, vals[3])
        agv_cfg = next((a for a in self.ctx.config.get('agvs', [])
                        if str(a.get('id', '')) == agv_id), {})
        self.var_can_reverse.set(agv_cfg.get('can_reverse', True))
        tags  = self.tree_settings_agv.item(selected[0], 'tags')
        color = tags[0] if tags else "#3498db"
        self.current_agv_color = color
        self.btn_agv_color.config(bg=color)

    def pick_agv_color(self):
        color = colorchooser.askcolor(initialcolor=self.current_agv_color)[1]
        if color:
            self.current_agv_color = color
            self.btn_agv_color.config(bg=color)

    def btn_add_agv(self):
        config   = self.ctx.config
        agv_id   = self.ent_agv_id.get().strip()
        sub_val  = self.ent_agv_sub.get().strip()
        pub_val  = self.ent_agv_pub.get().strip()
        factory  = config.get('factory',  'default')
        hardware = config.get('hardware', 'hardware')
        if not sub_val:
            sub_val = f"AGV/{hardware}/{factory}/{agv_id}/sub"
        if not pub_val:
            pub_val = f"AGV/{hardware}/{factory}/{agv_id}/pub"
        new_cfg = {
            "id":          agv_id,
            "ip":          self.ent_agv_ip.get().strip(),
            "topic_sub":   sub_val,
            "topic_pub":   pub_val,
            "color":       self.current_agv_color,
            "can_reverse": self.var_can_reverse.get(),
        }
        config['agvs'] = [a for a in config.get('agvs', []) if a['id'] != agv_id]
        config['agvs'].append(new_cfg)
        self.save_config()
        cfg_full = {**new_cfg, 'factory': factory, 'hardware': hardware}
        existing = next((a for a in self.ctx.agv_list if a.id == agv_id), None)
        if existing:
            existing.ip          = new_cfg['ip']
            existing.color       = new_cfg['color']
            existing.can_reverse = new_cfg['can_reverse']
            existing.topic_order = sub_val
            existing.topic_state = pub_val
        else:
            from agv.agv_instance import AGV as _AGV
            new_agv = _AGV(cfg_full, self.ctx.mqtt)
            new_agv.app_config = config
            new_agv.zone_mgr   = self.ctx.zone_mgr
            self.ctx.agv_list.append(new_agv)
        print("AGV Added/Updated.")
        self.refresh_agv_settings_tree()

    def btn_del_agv(self):
        config = self.ctx.config
        agv_id = self.ent_agv_id.get()
        config['agvs'] = [a for a in config.get('agvs', []) if a['id'] != agv_id]
        self.save_config()
        for i, agv in enumerate(self.ctx.agv_list):
            if agv.id == agv_id:
                del self.ctx.agv_list[i]
                break
        print(f"AGV {agv_id} deleted.")
        self.refresh_agv_settings_tree()

    def refresh_chargers_settings_tree(self):
        config = self.ctx.config
        for item in self.tree_chargers.get_children():
            self.tree_chargers.delete(item)
        for charger in config.get('chargers', []):
            zone_str   = ", ".join(map(str, charger.get('reversing_zone', [])))
            homing_str = ", ".join(map(str, charger.get('homing_path', [])))
            name       = charger.get('name', f"Trạm {charger.get('id', '')}")
            self.tree_chargers.insert("", "end", values=(
                name, charger.get('node_id', ''), zone_str,
                charger.get('slow_speed', ''), homing_str,
                charger.get('assigned_agv', '')))

    def on_charger_select(self, event):
        selected = self.tree_chargers.selection()
        if not selected:
            return
        idx      = self.tree_chargers.index(selected[0])
        chargers = self.ctx.config.get('chargers', [])
        if idx >= len(chargers):
            return
        c = chargers[idx]
        self.ent_chg_id.delete(0,     'end'); self.ent_chg_id.insert(0,     str(c.get('id', '')))
        self.ent_chg_name.delete(0,   'end'); self.ent_chg_name.insert(0,   c.get('name', ''))
        self.ent_chg_node.delete(0,   'end'); self.ent_chg_node.insert(0,   str(c.get('node_id', '')))
        self.ent_chg_zone.delete(0,   'end'); self.ent_chg_zone.insert(0,
                                              ", ".join(map(str, c.get('reversing_zone', []))))
        self.ent_chg_speed.delete(0,  'end'); self.ent_chg_speed.insert(0,  str(c.get('slow_speed', '')))
        self.ent_chg_homing.delete(0, 'end'); self.ent_chg_homing.insert(0,
                                              ", ".join(map(str, c.get('homing_path', []))))
        self.ent_chg_agv.delete(0,    'end'); self.ent_chg_agv.insert(0,    c.get('assigned_agv', ''))

    def btn_add_charger(self):
        config = self.ctx.config
        try:
            charger_id   = int(self.ent_chg_id.get())
            charger_name = self.ent_chg_name.get().strip() or f"Trạm {charger_id}"
            node_id      = int(self.ent_chg_node.get())
            homing_path  = [int(x.strip()) for x in self.ent_chg_homing.get().split(',')
                            if x.strip().isdigit()]
            new_charger = {
                "id":           charger_id,
                "name":         charger_name,
                "node_id":      node_id,
                "reversing_zone": [int(x.strip()) for x in self.ent_chg_zone.get().split(',')
                                   if x.strip().isdigit()],
                "slow_speed":   int(self.ent_chg_speed.get() or 40),
                "homing_path":  homing_path,
                "assigned_agv": self.ent_chg_agv.get().strip(),
            }
            chargers = [c for c in config.get('chargers', []) if c.get('id') != charger_id]
            chargers.append(new_charger)
            chargers.sort(key=lambda x: x.get('id', 0))
            config['chargers'] = chargers
            self.save_config()
            self.refresh_chargers_settings_tree()
            g = self.ctx.planner.graph
            if g.has_node(node_id):
                g.nodes[node_id]['role'] = 'charger'
                g.nodes[node_id]['type'] = 'station'
                g.nodes[node_id]['name'] = charger_name
                self.ctx.planner.save_map()
                self.map_widget.draw_map()
        except ValueError:
            messagebox.showerror("Error", "Invalid Input")

    def btn_del_charger(self):
        config   = self.ctx.config
        selected = self.tree_chargers.selection()
        if not selected:
            messagebox.showwarning("Warning", "Please select a charger to delete.")
            return
        idx      = self.tree_chargers.index(selected[0])
        chargers = config.get('chargers', [])
        if idx >= len(chargers):
            return
        cid = chargers[idx].get('id')
        config['chargers'] = [c for c in chargers if c.get('id') != cid]
        self.save_config()
        self.refresh_chargers_settings_tree()

    def _clear_wait_node_map_role(self, tid, current_list):
        old_cfg = next((x for x in current_list if x['id'] == tid), None)
        if old_cfg:
            g = self.ctx.planner.graph
            if g.has_node(old_cfg['wait']):
                n = g.nodes[old_cfg['wait']]
                if n.get('team_id') == tid:
                    n['role'] = 'none'
                    n.pop('team_id', None)

    def update_station_config_list(self, add=True):
        config       = self.ctx.config
        current_list = config.get('station_config', [])
        if add:
            try:
                tid  = int(self.ent_st_id.get())
                name = self.ent_st_name.get()
                wait = int(self.ent_st_wait.get())
                dele = int(self.ent_st_del.get())
                self._clear_wait_node_map_role(tid, current_list)
                current_list = [x for x in current_list if x['id'] != tid]
                current_list.append({"id": tid, "name": name,
                                     "wait": wait, "delivery": dele})
                current_list.sort(key=lambda x: x['id'])
                g = self.ctx.planner.graph
                if g.has_node(wait):
                    g.nodes[wait]['role']    = 'wait'
                    g.nodes[wait]['type']    = 'station'
                    g.nodes[wait]['team_id'] = tid
                    self.ctx.planner.save_map()
                    self.map_widget.draw_map()
            except ValueError:
                messagebox.showerror("Error", "Invalid Input")
                return
        else:
            sel = self.tree_st.selection() if hasattr(self, 'tree_st') else []
            if not sel:
                return
            item = self.tree_st.item(sel[0])
            tid  = int(item['values'][0])
            self._clear_wait_node_map_role(tid, current_list)
            if next((x for x in current_list if x['id'] == tid), None):
                self.ctx.planner.save_map()
                self.map_widget.draw_map()
            current_list = [x for x in current_list if x['id'] != tid]
        config['station_config'] = current_list
        if hasattr(self, 'tree_st'):
            for item in self.tree_st.get_children():
                self.tree_st.delete(item)
            for st in current_list:
                self.tree_st.insert("", "end",
                                    values=(st['id'], st['name'],
                                            st['wait'], st['delivery']))

    def save_station_settings(self):
        config = self.ctx.config
        try:
            station_map = {}
            for st in config.get('station_config', []):
                if 'delivery' in st and 'name' in st:
                    station_map[str(st['delivery'])] = st['name']
            config['station_map'] = station_map
            self.node_names = station_map
            self.save_config()
            messagebox.showinfo("Thành công", "Đã lưu và đồng bộ cấu hình trạm.")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể lưu cấu hình trạm: {e}")

    def update_error_table(self):
        if hasattr(self, 'tree_err') and self.tree_err.winfo_exists():
            for item in self.tree_err.get_children():
                self.tree_err.delete(item)
            stuck_time = self.ctx.config.get('alarms', {}).get('stuck_timeout', 30)
            for agv in self.ctx.agv_list:
                err_msg = agv.get_error_status(stuck_time)
                if err_msg != "OK":
                    now = datetime.datetime.now().strftime("%H:%M:%S")
                    self.tree_err.insert("", "end",
                                         values=(agv.id, agv.error_code, err_msg, now))
            self.after(2000, self.update_error_table)

    # ── Stats / Charts (wired from stats_view) ────────────────────────────────

    def draw_charts(self):
        import os as _os
        self.canvas_stats.delete("all")
        y_current = 50
        config = self.ctx.config

        try:
            d_from = datetime.datetime.strptime(self.ent_date_from.get(), '%Y-%m-%d')
            d_to   = datetime.datetime.strptime(self.ent_date_to.get(),   '%Y-%m-%d')
            num_days = (d_to - d_from).days + 1
        except ValueError:
            return

        log_file = "logs/activity_log.csv"
        if not _os.path.exists(log_file):
            self.canvas_stats.create_text(400, 200,
                                           text="No Data Log Found",
                                           font=("Arial", 20))
            return

        agv_time_data = {agv['id']: {"pickup": 0, "delivery": 0, "return": 0}
                         for agv in config.get('agvs', [])}
        node_trip_data = {}

        try:
            with open(log_file, 'r') as f:
                next(f)
                for line in f:
                    parts = line.strip().split(',')
                    if len(parts) < 6:
                        continue
                    date, agv_id, task, duration, node = (
                        parts[1], parts[2], parts[3], int(parts[4]), parts[5])
                    try:
                        curr_date = datetime.datetime.strptime(date, '%Y-%m-%d')
                        if not (d_from <= curr_date <= d_to):
                            continue
                    except ValueError:
                        continue
                    if agv_id not in agv_time_data:
                        agv_time_data[agv_id] = {"pickup": 0, "delivery": 0, "return": 0}
                    if task in agv_time_data[agv_id]:
                        agv_time_data[agv_id][task] += duration
                    if task == "delivery":
                        node = str(node)
                        node_trip_data[node] = node_trip_data.get(node, 0) + 1
        except Exception as e:
            print(f"Error reading log: {e}")

        # ── Chart 1: Horizontal time distribution ─────────────────────────────
        self.canvas_stats.create_text(50, y_current - 20,
                                       text=self.t("chart_time_dist"),
                                       anchor='w', font=("Arial", 10, "bold"))
        MAX_WIDTH       = 600
        work_hours      = float(config.get('work_hours', 12))
        STANDARD_CAPACITY = num_days * work_hours * 3600

        for agv_id, times in agv_time_data.items():
            self.canvas_stats.create_text(50, y_current + 15,
                                           text=agv_id, anchor='e')
            x_curr       = 60
            total_active = sum(times.values())
            total_time_base = max(total_active, STANDARD_CAPACITY)
            idle_time    = total_time_base - total_active
            times["idle"] = idle_time
            px_per_sec   = MAX_WIDTH / total_time_base if total_time_base else 1

            for task in ["pickup", "delivery", "return", "idle"]:
                duration = times[task]
                width    = duration * px_per_sec
                if width > 0:
                    color = self.chart_colors.get(task, "#95a5a6")
                    self.canvas_stats.create_rectangle(
                        x_curr, y_current, x_curr + width, y_current + 30,
                        fill=color, outline="white")
                    if width > 40:
                        percent   = (duration / total_time_base) * 100
                        time_str  = self.format_duration(duration)
                        self.canvas_stats.create_text(
                            x_curr + width / 2, y_current + 15,
                            text=f"{int(percent)}%\n({time_str})",
                            fill="black", font=("Arial", 7))
                    x_curr += width
            y_current += 45

        # Legend Chart 1
        lx = 60
        ly = y_current + 10
        self.canvas_stats.create_text(lx, ly - 15, text=self.t("legend_click"),
                                       anchor='w', font=("Arial", 8, "italic"))
        for task, col in self.chart_colors.items():
            if task == "trip_bar":
                continue
            tag_id = f"legend_{task}"
            self.canvas_stats.create_rectangle(lx, ly, lx + 15, ly + 15,
                                                fill=col, tags=tag_id)
            self.canvas_stats.create_text(lx + 20, ly + 7,
                                           text=task.title(), anchor='w', tags=tag_id)
            self.canvas_stats.tag_bind(tag_id, "<Button-1>",
                                        lambda e, t=task: self.pick_chart_color(t))
            lx += 100
        y_current += 60

        # ── Chart 2: Vertical trips per station ───────────────────────────────
        self.canvas_stats.create_text(50, y_current,
                                       text=self.t("chart_trips"),
                                       anchor='w', font=("Arial", 10, "bold"))
        x_start    = 60
        MAX_HEIGHT = 150
        filtered_data = {k: v for k, v in node_trip_data.items()
                         if k in self.node_names}
        max_trips = max(filtered_data.values()) if filtered_data else 5
        if max_trips == 0:
            max_trips = 1
        scale_y = MAX_HEIGHT / max_trips
        base_y  = y_current + MAX_HEIGHT + 40

        for node, count in filtered_data.items():
            bar_h     = count * scale_y
            bar_color = self.chart_colors.get("trip_bar", "#9b59b6")
            self.canvas_stats.create_rectangle(
                x_start, base_y - bar_h, x_start + 40, base_y, fill=bar_color)
            display_name = self.node_names.get(node, f"Node {node}")
            self.canvas_stats.create_text(x_start + 20, base_y + 15,
                                           text=display_name, font=("Arial", 9))
            self.canvas_stats.create_text(x_start + 20, base_y - bar_h - 10,
                                           text=str(count))
            x_start += 60

        ly = base_y + 40
        self.canvas_stats.create_text(60, ly, text=self.t("legend_trip_color"),
                                       anchor='w')
        self.canvas_stats.create_rectangle(
            150, ly - 7, 165, ly + 8,
            fill=self.chart_colors.get("trip_bar", "#9b59b6"),
            tags="legend_trip_bar")
        self.canvas_stats.tag_bind("legend_trip_bar", "<Button-1>",
                                    lambda e: self.pick_chart_color("trip_bar"))

        self.canvas_stats.config(scrollregion=self.canvas_stats.bbox("all"))

    def format_duration(self, seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        return f"{h}h {m}p"

    def pick_chart_color(self, task: str):
        color_code = colorchooser.askcolor(title=f"Choose color for {task}")
        if color_code[1]:
            self.chart_colors[task] = color_code[1]
            self.ctx.config['chart_colors'] = self.chart_colors
            self.save_config()
            self.draw_charts()

    def generate_dummy_data(self):
        import os as _os
        import random as _random
        import time as _time
        log_file = "logs/activity_log.csv"
        _os.makedirs(_os.path.dirname(log_file), exist_ok=True)
        if not _os.path.exists(log_file):
            with open(log_file, 'w') as f:
                f.write("timestamp,date,agv_id,task_type,duration,target_node\n")
        agv_ids = [a.id for a in self.ctx.agv_list] if self.ctx.agv_list else ["AGV_01", "AGV_02"]
        tasks   = ["pickup", "delivery", "return"]
        nodes   = ([str(n) for n in self.ctx.planner.graph.nodes]
                   if self.ctx.planner.graph.nodes else ["101", "102", "103"])
        today   = datetime.datetime.now().strftime('%Y-%m-%d')
        with open(log_file, 'a') as f:
            for _ in range(10):
                ts   = int(_time.time())
                agv  = _random.choice(agv_ids)
                task = _random.choice(tasks)
                dur  = _random.randint(30, 300)
                node = _random.choice(nodes)
                f.write(f"{ts},{today},{agv},{task},{dur},{node}\n")
        print("Generated 10 dummy records.")
        self.draw_charts()

    def clear_simulation_data(self):
        from tkinter import messagebox as _mb
        if _mb.askyesno("Confirm", "Are you sure you want to clear all simulation logs?"):
            log_file = "logs/activity_log.csv"
            with open(log_file, 'w') as f:
                f.write("timestamp,date,agv_id,task_type,duration,target_node\n")
            print("Logs cleared.")
            self.draw_charts()

    # ── Burnin / Continuous Test (wired from burnin_view) ─────────────────────

    _BI_ACTIONS = [
        # (label,                               action_code, default_value)
        ("RUN — Đi thẳng",                             3,   0),
        ("TURN_L — Rẽ trái",                           6,   0),
        ("TURN_R — Rẽ phải",                           5,   0),
        ("SPEED — Tốc độ (nhập giá trị)",              4,  60),
        ("DIR_FWD — Chiều tiến ➡",                     7,   0),
        ("DIR_BWD — Chiều lùi ⬅",                      8,   0),
        ("WAIT_SYS — Chờ hệ thống",                    1,   0),
        ("WAIT_USER — Chờ người dùng",                 2,   0),
        ("LIDAR_OFF — Tắt Lidar",                     10,   0),
        ("LIDAR_ON — Bật Lidar",                      11,   0),
        ("WAIT_CHARGE — Chờ sạc pin",                 12,   0),
    ]

    def _bi_add_row(self, tag: int = 0, act_idx: int = 0, val: int = 0):
        """Thêm 1 dòng hành động vào bảng burnin."""
        rows = self._bi_rows
        idx  = len(rows)
        bg   = "#f0f4ff" if idx % 2 == 0 else "#ffffff"

        row_f = tk.Frame(self._bi_rows_frame, bg=bg, pady=2)
        row_f.pack(fill='x', padx=2, pady=1)

        num_lbl = tk.Label(row_f, text=str(idx + 1), width=3,
                           anchor='center', bg=bg, font=("Arial", 9))
        num_lbl.pack(side='left', padx=2)

        tag_var = tk.StringVar(value=str(tag) if tag else "")
        ttk.Entry(row_f, textvariable=tag_var, width=7,
                  justify='center', font=("Courier New", 10)).pack(side='left', padx=2)

        act_labels = [label for label, _, _ in self._BI_ACTIONS]
        act_var    = tk.StringVar()
        act_cb     = ttk.Combobox(row_f, textvariable=act_var,
                                   values=act_labels, state='readonly', width=30)
        act_cb.pack(side='left', padx=2)
        act_cb.current(act_idx)

        val_var = tk.StringVar(value=str(val))
        ttk.Entry(row_f, textvariable=val_var, width=8,
                  justify='center', font=("Courier New", 10)).pack(side='left', padx=2)

        def _on_act_change(e, cb=act_cb, vv=val_var):
            i = cb.current()
            if 0 <= i < len(self._BI_ACTIONS):
                _, _, dv = self._BI_ACTIONS[i]
                vv.set(str(dv))
        act_cb.bind('<<ComboboxSelected>>', _on_act_change)

        def _del(rf=row_f, rows=rows):
            entry = next((r for r in rows if r['frame'] is rf), None)
            if entry:
                rows.remove(entry)
            rf.destroy()
            self._bi_renumber()
        ttk.Button(row_f, text="✕", width=3, command=_del).pack(side='left', padx=4)

        rows.append({
            'frame':   row_f,
            'num_lbl': num_lbl,
            'tag_var': tag_var,
            'act_var': act_var,
            'act_cb':  act_cb,
            'val_var': val_var,
        })

    def _bi_renumber(self):
        for i, row in enumerate(self._bi_rows):
            bg = "#f0f4ff" if i % 2 == 0 else "#ffffff"
            row['num_lbl'].config(text=str(i + 1), bg=bg)
            row['frame'].config(bg=bg)

    def _bi_clear_rows(self):
        for row in list(self._bi_rows):
            row['frame'].destroy()
        self._bi_rows.clear()

    def _bi_build_plan(self):
        """Đọc bảng burnin, trả về plan_data list[dict] hoặc raise ValueError."""
        if not self._bi_rows:
            raise ValueError("Bảng hành động đang trống — hãy thêm ít nhất 1 dòng.")
        plan = []
        for i, row in enumerate(self._bi_rows):
            tag_str = row['tag_var'].get().strip()
            if not tag_str:
                raise ValueError(f"Dòng {i+1}: chưa nhập số thẻ.")
            try:
                tag = int(tag_str)
            except ValueError:
                raise ValueError(f"Dòng {i+1}: '{tag_str}' không phải số thẻ hợp lệ.")
            act_idx = row['act_cb'].current()
            if act_idx < 0 or act_idx >= len(self._BI_ACTIONS):
                raise ValueError(f"Dòng {i+1}: chưa chọn hành động.")
            _, code, _ = self._BI_ACTIONS[act_idx]
            val_str = row['val_var'].get().strip()
            try:
                val = int(val_str) if val_str else 0
            except ValueError:
                raise ValueError(f"Dòng {i+1}: giá trị '{val_str}' không hợp lệ.")
            plan.append({'t': tag, 'a': code, 'v': val})
        return plan

    def _bi_start(self):
        from tkinter import messagebox as _mb
        if self._bi_state.get('running'):
            return
        try:
            plan_data = self._bi_build_plan()
        except ValueError as e:
            _mb.showerror("Lỗi kế hoạch", str(e))
            return
        agv_id = self._bi_agv_var.get()
        agv    = next((a for a in self.ctx.agv_list if str(a.id) == agv_id), None)
        if not agv:
            _mb.showerror("Lỗi", "Không tìm thấy AGV đã chọn.")
            return
        loops = self._bi_loops_var.get()
        if loops < 1:
            _mb.showerror("Lỗi", "Số vòng lặp phải >= 1.")
            return
        target_tag = plan_data[-1]['t']
        self._bi_state = {
            'running':      True,
            'agv':          agv,
            'plan_data':    plan_data,
            'loops':        loops,
            'delay':        self._bi_delay_var.get(),
            'current_loop': 1,
            'target_tag':   target_tag,
            'dispatched':   False,
            'delay_until':  None,
        }
        self._bi_btn_start.config(state='disabled')
        self._bi_btn_stop.config(state='normal')
        self._bi_status_var.set("Đang chạy…")
        self._bi_loop_var.set(f"1 / {loops}")
        self._bi_tag_var.set(f"Thẻ {getattr(agv, 'current_tag', '?')}")
        summary = ' → '.join(f"T{r['t']}:{r['a']}" for r in plan_data)
        self._bi_log_msg(f"▶ Bắt đầu: {loops} vòng  ·  {len(plan_data)} bước")
        self._bi_log_msg(f"  Kế hoạch: {summary}")
        self._bi_log_msg(f"  Thẻ đích (cuối): {target_tag}")
        self._bi_dispatch()
        self.after(800, self._bi_poll)

    def _bi_dispatch(self):
        import json as _json
        import uuid as _uuid
        state     = self._bi_state
        agv       = state['agv']
        plan_data = state['plan_data']
        cmd_id    = str(_uuid.uuid4())[:8]
        payload   = _json.dumps({"c": "plan", "d": plan_data, "id": cmd_id})
        try:
            agv.mqtt.publish(agv.topic_order, payload)
        except Exception as e:
            self._bi_log_msg(f"  [LỖI MQTT] {e}")
            self._bi_stop()
            return
        agv.is_navigating  = True
        agv.task_lifecycle = "assigned"
        if hasattr(agv, 'last_sent_cmd_id'):
            agv.last_sent_cmd_id = cmd_id
        state['dispatched']  = True
        state['delay_until'] = None
        loop  = state['current_loop']
        loops = state['loops']
        self._bi_loop_var.set(f"{loop} / {loops}")
        self._bi_log_msg(
            f"  Vòng {loop}/{loops}: gửi {len(plan_data)} lệnh → AGV {agv.id}  [id={cmd_id}]")

    def _bi_poll(self):
        import time as _time
        if not self._bi_state.get('running'):
            return
        state = self._bi_state
        agv   = state['agv']
        nav_str = "đang đi" if getattr(agv, 'is_navigating', False) else "dừng"
        self._bi_tag_var.set(f"Thẻ {getattr(agv, 'current_tag', '?')} / {nav_str}")
        if state.get('dispatched') and state['delay_until'] is None:
            target  = state['target_tag']
            at_dest = (getattr(agv, 'current_tag', None) == target)
            not_nav = not getattr(agv, 'is_navigating', True)
            if at_dest and not_nav:
                delay = state['delay']
                state['delay_until'] = _time.time() + delay
                self._bi_log_msg(
                    f"  ✓ Đến Thẻ {target}"
                    + (f" — chờ {delay}s" if delay > 0 else ""))
                self._bi_status_var.set(
                    f"Chờ {delay}s…" if delay > 0 else "Chuẩn bị vòng tiếp…")
        if state['delay_until'] is not None and _time.time() >= state['delay_until']:
            state['delay_until'] = None
            state['dispatched']  = False
            state['current_loop'] += 1
            if state['current_loop'] > state['loops']:
                state['running'] = False
                total = state['loops']
                self._bi_status_var.set(f"✅ Hoàn thành {total} vòng!")
                self._bi_loop_var.set(f"{total} / {total}")
                self._bi_log_msg(f"✅ Hoàn thành tất cả {total} vòng lặp")
                self._bi_btn_start.config(state='normal')
                self._bi_btn_stop.config(state='disabled')
                return
            self._bi_status_var.set("Đang chạy…")
            self._bi_dispatch()
        self.after(800, self._bi_poll)

    def _bi_stop(self):
        self._bi_state['running'] = False
        self._bi_status_var.set("Đã dừng")
        self._bi_log_msg("⏹ Người dùng dừng")
        self._bi_btn_start.config(state='normal')
        self._bi_btn_stop.config(state='disabled')

    def _bi_log_msg(self, msg: str):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self._bi_log.config(state='normal')
        self._bi_log.insert('end', f"[{ts}] {msg}\n")
        self._bi_log.see('end')
        self._bi_log.config(state='disabled')

    def _bi_clear_log(self):
        self._bi_log.config(state='normal')
        self._bi_log.delete('1.0', 'end')
        self._bi_log.config(state='disabled')
