"""
SimulationPanel — Giao diện mô phỏng lệnh AGV (Dry Run UI).
"""
import math
import tkinter as tk
from tkinter import ttk, messagebox
from simulation.simulation_engine import (SimulationEngine, TASK_TYPES,
    ACT_TURN_L, ACT_TURN_R, ACT_SPEED,
    ACT_WAIT_SYS, ACT_WAIT_USER, ACT_DIR_FWD, ACT_DIR_BWD,
    ACT_LIDAR_OFF, ACT_LIDAR_ON, ACT_RUN)


class SimulationPanel(ttk.Frame):
    """
    Panel mô phỏng lệnh AGV — nhúng trực tiếp vào tab (không còn là Toplevel).
    """

    def __init__(self, parent, sim_engine: SimulationEngine, traffic_manager, app_config: dict):
        super().__init__(parent)
        self.sim         = sim_engine
        self.tm          = traffic_manager
        self.cfg         = app_config
        self._last_steps = []
        self._last_start = 0
        self._last_end   = 0
        self._last_task  = "delivery"

        self.pack(fill='both', expand=True)
        self._build_ui()
        self._load_override_text()
        self._refresh_map_stats()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Top title bar
        top = ttk.Frame(self, padding=(12, 6))
        top.pack(fill='x')
        ttk.Label(top, text="🔬 Mô phỏng Lệnh AGV",
                  font=("Arial", 13, "bold")).pack(side='left')
        ttk.Label(top,
                  text="  Kiểm tra hành vi hệ thống · ✏ = đang bị Override  ",
                  foreground="#666").pack(side='left')

        # PanedWindow ngang: left config | right output
        pw = tk.PanedWindow(self, orient='horizontal', sashwidth=5, bg="#bbbbbb")
        pw.pack(fill='both', expand=True, padx=6, pady=(0, 6))

        # ── LEFT ──────────────────────────────────────────────────────────────
        left = ttk.Frame(pw, padding=10)
        pw.add(left, minsize=230)

        row = 0
        ttk.Label(left, text="⚙ Tham số mô phỏng",
                  font=("Arial", 11, "bold")).grid(row=row, column=0, columnspan=2, sticky='w',
                                                     pady=(0, 8))
        row += 1

        def _lbl_ent(label, var, row, note=""):
            ttk.Label(left, text=label).grid(row=row, column=0, sticky='w', pady=2)
            ttk.Entry(left, textvariable=var, width=10).grid(row=row, column=1, sticky='w')
            if note:
                ttk.Label(left, text=note, foreground="#888",
                          font=("Arial", 8)).grid(row=row + 1, column=0, columnspan=2, sticky='w')
            return row + (2 if note else 1)

        self.var_start    = tk.StringVar()
        self.var_end      = tk.StringVar()
        self._prev_tag_map = {}  # display label -> actual prev_tag (int or None)

        # --- Thẻ bắt đầu (bind FocusOut/Return để refresh hướng) ---
        ttk.Label(left, text="Thẻ bắt đầu:").grid(row=row, column=0, sticky='w', pady=2)
        ent_start = ttk.Entry(left, textvariable=self.var_start, width=10)
        ent_start.grid(row=row, column=1, sticky='w')
        ent_start.bind('<FocusOut>', self._refresh_dir_options)
        ent_start.bind('<Return>',   self._refresh_dir_options)
        row += 1

        # --- Hướng xe (Combobox động từ graph) ---
        ttk.Label(left, text="Hướng xe đang đi:").grid(row=row, column=0, sticky='w', pady=2)
        row += 1
        self.cmb_dir = ttk.Combobox(left, state='readonly', width=24)
        self.cmb_dir['values'] = ["— Nhập thẻ bắt đầu trước —"]
        self.cmb_dir.current(0)
        self.cmb_dir.grid(row=row, column=0, columnspan=2, sticky='ew')
        row += 1
        self.lbl_dir_note = ttk.Label(left, text="", foreground="#888", font=("Arial", 8))
        self.lbl_dir_note.grid(row=row, column=0, columnspan=2, sticky='w')
        row += 1

        ttk.Separator(left, orient='h').grid(row=row, column=0, columnspan=2, sticky='ew', pady=6)
        row += 1

        ttk.Label(left, text="Loại nhiệm vụ:").grid(row=row, column=0, sticky='w')
        row += 1
        self.var_task = tk.StringVar()
        cb = ttk.Combobox(left, textvariable=self.var_task, state='readonly', width=28)
        cb['values'] = [f"{k}  —  {v}" for k, v in TASK_TYPES]
        cb.grid(row=row, column=0, columnspan=2, sticky='ew')
        cb.current(1)   # default: delivery
        row += 1

        ttk.Separator(left, orient='h').grid(row=row, column=0, columnspan=2, sticky='ew', pady=6)
        row += 1
        row = _lbl_ent("Thẻ đích:", self.var_end, row)

        ttk.Separator(left, orient='h').grid(row=row, column=0, columnspan=2, sticky='ew', pady=8)
        row += 1

        ttk.Button(left, text="▶  Chạy Mô Phỏng",
                   command=self._run_sim).grid(row=row, column=0, columnspan=2, sticky='ew', pady=2)
        row += 1
        ttk.Button(left, text="🏥  Kiểm tra Bản đồ",
                   command=self._run_health).grid(row=row, column=0, columnspan=2, sticky='ew', pady=2)
        row += 1
        ttk.Button(left, text="🗺  Mô phỏng Đa AGV",
                   command=self._open_multi_sim).grid(row=row, column=0, columnspan=2, sticky='ew', pady=2)
        row += 1

        ttk.Separator(left, orient='h').grid(row=row, column=0, columnspan=2, sticky='ew', pady=8)
        row += 1

        ttk.Label(left, text="Bản đồ hiện tại:", font=("Arial", 9, "bold")).grid(
            row=row, column=0, columnspan=2, sticky='w')
        row += 1
        ttk.Label(left, text="Thẻ (nodes):", foreground="#555").grid(row=row, column=0, sticky='w')
        self.lbl_nodes = ttk.Label(left, text="—", font=("Arial", 10, "bold"))
        self.lbl_nodes.grid(row=row, column=1, sticky='w')
        row += 1
        ttk.Label(left, text="Kết nối (edges):", foreground="#555").grid(row=row, column=0, sticky='w')
        self.lbl_edges = ttk.Label(left, text="—", font=("Arial", 10, "bold"))
        self.lbl_edges.grid(row=row, column=1, sticky='w')

        # ── RIGHT: paned dọc (log top | override bottom) ──────────────────────
        right_pw = tk.PanedWindow(pw, orient='vertical', sashwidth=5, bg="#aaaaaa")
        pw.add(right_pw, minsize=650)

        # Log frame
        log_lf = ttk.LabelFrame(right_pw, text="📋 Kết quả mô phỏng", padding=4)
        right_pw.add(log_lf, minsize=320)

        # Toolbar trên log
        log_tb = ttk.Frame(log_lf)
        log_tb.pack(fill='x', pady=(0, 4))
        ttk.Button(log_tb, text="🗺 Xem trên bản đồ",
                   command=self._show_on_map).pack(side='left', padx=2)

        self.txt_log = tk.Text(log_lf, font=("Courier New", 9), wrap='none',
                                bg="#1e1e1e", fg="#d4d4d4",
                                insertbackground="white", state='disabled')
        sb_ly = ttk.Scrollbar(log_lf, orient='vertical',   command=self.txt_log.yview)
        sb_lx = ttk.Scrollbar(log_lf, orient='horizontal', command=self.txt_log.xview)
        self.txt_log.configure(yscrollcommand=sb_ly.set, xscrollcommand=sb_lx.set)
        sb_ly.pack(side='right', fill='y')
        sb_lx.pack(side='bottom', fill='x')
        self.txt_log.pack(fill='both', expand=True)

        self.txt_log.tag_configure("header",   foreground="#4EC9B0", font=("Courier New", 9, "bold"))
        self.txt_log.tag_configure("turn",     foreground="#CE9178")
        self.txt_log.tag_configure("speed",    foreground="#DCDCAA")
        self.txt_log.tag_configure("dest",     foreground="#4EC9B0", font=("Courier New", 9, "bold"))
        self.txt_log.tag_configure("override", foreground="#F48771", font=("Courier New", 9, "bold"))
        self.txt_log.tag_configure("normal",   foreground="#d4d4d4")
        self.txt_log.tag_configure("warning",  foreground="#FFD700")
        self.txt_log.tag_configure("error",    foreground="#F44747", font=("Courier New", 9, "bold"))

        # Override frame
        ov_lf = ttk.LabelFrame(right_pw,
            text="✏  Quy tắc can thiệp hành vi  (Override Rules)", padding=4)
        right_pw.add(ov_lf, minsize=160)

        ttk.Label(ov_lf,
            text="Gõ quy tắc → [Áp dụng] để xem thay đổi  |  [Lưu Rules] để ghi nhớ cho lần sau",
            foreground="#666", font=("Arial", 8)).pack(anchor='w')

        self.txt_ov = tk.Text(ov_lf, font=("Courier New", 9), height=8,
                               bg="#252526", fg="#d4d4d4", insertbackground="white",
                               undo=True, wrap='none')
        sb_ovy = ttk.Scrollbar(ov_lf, orient='vertical',   command=self.txt_ov.yview)
        sb_ovx = ttk.Scrollbar(ov_lf, orient='horizontal', command=self.txt_ov.xview)
        self.txt_ov.configure(yscrollcommand=sb_ovy.set, xscrollcommand=sb_ovx.set)
        sb_ovy.pack(side='right', fill='y')
        sb_ovx.pack(side='bottom', fill='x')
        self.txt_ov.pack(fill='both', expand=True)

        self.txt_ov.tag_configure("comment", foreground="#608B4E")

        # Button bar
        bb = ttk.Frame(ov_lf)
        bb.pack(fill='x', pady=(4, 0))
        ttk.Button(bb, text="✏ Áp dụng Override",  command=self._apply_ov).pack(side='left', padx=2)
        ttk.Button(bb, text="💾 Lưu Rules",         command=self._save_ov).pack(side='left', padx=2)
        ttk.Button(bb, text="🔄 Hoàn tác về đã lưu", command=self._load_override_text).pack(side='left', padx=2)
        ttk.Button(bb, text="📥 Tải về dữ liệu mô phỏng",
                   command=self._load_sim_to_override).pack(side='left', padx=2)
        ttk.Button(bb, text="❓ Hướng dẫn cú pháp", command=self._show_help).pack(side='right', padx=2)
        self.lbl_status = ttk.Label(bb, text="", foreground="#888")
        self.lbl_status.pack(side='left', padx=8)

    # ── Simulation ────────────────────────────────────────────────────────────

    def _run_sim(self):
        try:
            start = int(self.var_start.get())
        except ValueError:
            self._log_error("Thẻ bắt đầu phải là số nguyên.")
            return
        try:
            end = int(self.var_end.get())
        except ValueError:
            self._log_error("Thẻ đích phải là số nguyên.")
            return

        g = self.tm.graph
        if not g.has_node(start):
            self._log_error(
                f"Thẻ {start} không tồn tại trong bản đồ ({len(g.nodes)} thẻ hiện có).")
            return
        if not g.has_node(end):
            self._log_error(
                f"Thẻ đích {end} không tồn tại trong bản đồ ({len(g.nodes)} thẻ hiện có).")
            return

        # Đọc hướng từ combobox
        self._refresh_dir_options()  # đảm bảo map đã cập nhật
        sel         = self.cmb_dir.get()
        prev        = self._prev_tag_map.get(sel, None)    # dùng cho pathfinding bias
        facing_tag  = self._facing_tag_map.get(sel, None)  # dùng cho rotation detection

        task = self._get_task_type()

        steps, err = self.sim.dry_run(start, prev, end, task, facing_tag=facing_tag)
        if err:
            self._log_error(f"LỖI: {err}")
            return

        self._last_steps = steps
        self._last_start = start
        self._last_end   = end
        self._last_task  = task

        log = self.sim.format_log(steps, start, end, task)
        self._write_colored_log(log)
        self.lbl_status.config(
            text=f"✓ Mô phỏng: {len(steps)} thẻ", foreground="#2ecc71")

    def _apply_ov(self):
        if not self._last_steps:
            self._log_error("Chạy mô phỏng trước khi áp dụng override.")
            return
        ov_text  = self.txt_ov.get("1.0", "end")
        modified, applied, warns = self.sim.apply_overrides_from_text(
            ov_text, self._last_steps, self._last_task)
        log = self.sim.format_log(modified, self._last_start, self._last_end, self._last_task)
        if warns:
            log += "\n\n⚠ CẢNH BÁO OVERRIDE:\n" + "\n".join(f"  • {w}" for w in warns)
        self._write_colored_log(log)
        self.lbl_status.config(
            text=f"✓ Áp dụng {applied} override(s)" + (f"  ⚠ {len(warns)} cảnh báo" if warns else ""),
            foreground="#f39c12" if warns else "#2ecc71")

    def _save_ov(self):
        try:
            self.sim.save_overrides_text(self.txt_ov.get("1.0", "end"))
            self.lbl_status.config(text="✓ Đã lưu override rules.", foreground="#2ecc71")
        except Exception as e:
            self.lbl_status.config(text=f"Lỗi lưu: {e}", foreground="#e74c3c")

    def _load_override_text(self):
        text = self.sim.load_overrides_text()
        self.txt_ov.delete("1.0", "end")
        self.txt_ov.insert("1.0", text)
        self._highlight_comments()

    def _load_sim_to_override(self):
        """
        Issue 4: Chuyển dữ liệu mô phỏng hiện tại thành override rules và đổ vào editor.
        Người dùng chỉnh sửa trực tiếp trên đó thay vì phải gõ tay từ đầu.
        """
        if not self._last_steps:
            self.lbl_status.config(text="⚠ Chạy mô phỏng trước.", foreground="#f39c12")
            return

        from simulation.simulation_engine import (ACTION_CODE_TO_NAME,
            ACT_TURN_L, ACT_TURN_R, ACT_RUN,
            ACT_DIR_FWD, ACT_DIR_BWD, ACT_LIDAR_OFF, ACT_LIDAR_ON)
        task = self._last_task
        tc   = self.cfg.get('traffic', {})
        SPD_SLOW = int(tc.get('speed_slow', 60))
        SPD_FAST = int(tc.get('speed_fast', 120))

        lines = [
            f"# === Dữ liệu mô phỏng: {task} | Thẻ {self._last_start} → Thẻ {self._last_end} ===",
            "# Chỉnh sửa trực tiếp rồi nhấn [Áp dụng Override] để xem hiệu lực.",
            "# Cú pháp: Thẻ <id> [<task>]: <lệnh_cũ> -> <lệnh_mới>",
            "#",
        ]

        # Mã lệnh được hiển thị trong dữ liệu (bao gồm cả lệnh tự động)
        SHOW_CODES = {
            ACT_TURN_L:   "TURN_L",
            ACT_TURN_R:   "TURN_R",
            ACT_RUN:      "RUN",
            ACT_DIR_FWD:  "DIR_TIEN",
            ACT_DIR_BWD:  "DIR_LUI",
            ACT_LIDAR_OFF: "LIDAR_OFF",
            ACT_LIDAR_ON:  "LIDAR_ON",
            9:             "ROTATE_180",
        }

        for step in self._last_steps:
            tag = step['tag']
            nav = step['nav_action']

            # 1. Các lệnh tự động trong step['actions'] (LIDAR_OFF/ON, quay, đổi chiều...)
            for a in step['actions']:
                code = a['code']
                if code == 4:  # ACT_SPEED
                    if a['value'] == SPD_SLOW:
                        lines.append(f"Thẻ {tag} [{task}]: SPEED_SLOW -> SPEED_SLOW")
                    elif a['value'] == SPD_FAST:
                        lines.append(f"Thẻ {tag} [{task}]: SPEED_FAST -> SPEED_FAST")
                elif code in SHOW_CODES:
                    name = SHOW_CODES[code]
                    lines.append(f"Thẻ {tag} [{task}]: {name} -> {name}")

            # 2. Nav action (TURN_L/R/RUN ở cuối mỗi thẻ)
            nav_name = ACTION_CODE_TO_NAME.get(nav['code'], f"ACT_{nav['code']}")
            if nav['code'] in (ACT_TURN_L, ACT_TURN_R, ACT_RUN):
                lines.append(f"Thẻ {tag} [{task}]: {nav_name} -> {nav_name}")

        text = "\n".join(lines) + "\n"

        # Đổ vào editor (thay thế nội dung hiện tại)
        self.txt_ov.delete("1.0", "end")
        self.txt_ov.insert("1.0", text)
        self._highlight_comments()
        self.lbl_status.config(
            text=f"✓ Đã tải {len(self._last_steps)} thẻ vào Override Editor.",
            foreground="#2ecc71")

    def _run_health(self):
        result = self.tm.map_health_check()
        sep  = "═" * 62
        sep2 = "─" * 62
        lines = [sep, "  KIỂM TRA BẢN ĐỒ (Map Health Check)", sep]
        lines.append(f"  Thẻ: {len(self.tm.graph.nodes)}   Kết nối: {len(self.tm.graph.edges)}")
        lines.append(sep2)
        if result["errors"]:
            for e in result["errors"]:
                lines.append(f"  ✗ {e}")
        else:
            lines.append("  ✓ Không phát hiện lỗi nghiêm trọng.")
        if result["warnings"]:
            lines.append(sep2)
            for w in result["warnings"]:
                lines.append(f"  ⚠ {w}")
        lines.append(sep)
        self._write_colored_log("\n".join(lines))

    def _show_help(self):
        win = tk.Toplevel(self)
        win.title("Hướng dẫn cú pháp Override Rules")
        win.geometry("600x480")
        txt = tk.Text(win, font=("Courier New", 10), bg="#1e1e1e", fg="#d4d4d4",
                      wrap='word', padx=8, pady=8)
        txt.pack(fill='both', expand=True)
        txt.insert("1.0", """\
═══════════════════════════════════════════════════════════
  HƯỚNG DẪN CÚ PHÁP OVERRIDE RULES
═══════════════════════════════════════════════════════════

Cú pháp:  Thẻ <id> [<loại_task>]: <hành_động_cũ> -> <hành_động_mới>

▌ <loại_task> (tùy chọn, mặc định = any):
  any                    Áp dụng mọi loại nhiệm vụ
  pickup                 Chỉ khi đi lấy hàng
  delivery               Chỉ khi đi giao hàng
  return                 Chỉ khi về trạm chờ
  return_charge          Chỉ khi về trạm sạc

▌ Hành động điều hướng:
  RUN          Đi thẳng (mặc định nếu không có gì)
  TURN_L       Rẽ trái tại giao lộ
  TURN_R       Rẽ phải tại giao lộ
  WAIT_SYS     Dừng chờ hệ thống (vd: điểm đích)
  WAIT_USER    Dừng chờ người dùng xác nhận

▌ Hành động tốc độ:
  SPEED_SLOW   Tốc độ chậm (do hệ thống tự tính trước cua)
  SPEED_FAST   Tốc độ nhanh
  SPEED_NONE   XÓA lệnh đổi tốc độ tại thẻ này

▌ Các lệnh đặc biệt:
  LIDAR_OFF -> REMOVE    Xóa lệnh tắt lidar tại thẻ này

═══════════════════════════════════════════════════════════
  VÍ DỤ
═══════════════════════════════════════════════════════════

Thẻ 8: SPEED_SLOW -> SPEED_NONE
   → Bỏ qua giảm tốc tại thẻ 8 (mọi task)

Thẻ 9 [any]: TURN_L -> TURN_R
   → Đổi rẽ trái thành rẽ phải tại thẻ 9

Thẻ 12 [delivery]: RUN -> WAIT_USER
   → Dừng chờ người xác nhận khi delivery tại thẻ 12

Thẻ 7: LIDAR_OFF -> REMOVE
   → Không tắt lidar trước cua tại thẻ 7

═══════════════════════════════════════════════════════════
  GHI CHÚ QUAN TRỌNG
═══════════════════════════════════════════════════════════

• Ký hiệu ✏ trong log = hành động đó đang bị override
• Nhấn [Lưu Rules] → quy tắc được ghi vào file
  config/sim_overrides.txt và được nhớ cho lần sau
• Override chỉ hoạt động trong mô phỏng
  (không tự động gửi xuống AGV thật)
""")
        txt.config(state='disabled')

    def _open_multi_sim(self):
        from simulation.multi_sim_panel import MultiSimPanel
        MultiSimPanel(self, self.tm, self.sim)

    def _show_on_map(self):
        if not self._last_steps:
            messagebox.showwarning("Chưa có dữ liệu",
                                   "Chạy mô phỏng trước rồi mới xem bản đồ.", parent=self)
            return
        SimMapView(self, self.tm, self._last_steps,
                   self._last_start, self._last_end, self._last_task)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_task_type(self):
        raw = self.var_task.get()
        return raw.split("  —  ")[0].strip() if "  —  " in raw else raw

    def _refresh_map_stats(self):
        g = self.tm.graph
        self.lbl_nodes.config(text=str(len(g.nodes)))
        self.lbl_edges.config(text=str(len(g.edges)))

    def _log_error(self, msg):
        self.txt_log.config(state='normal')
        self.txt_log.delete("1.0", "end")
        self.txt_log.insert("1.0", msg, "error")
        self.txt_log.config(state='disabled')
        self.lbl_status.config(text="Lỗi", foreground="#e74c3c")

    def _write_colored_log(self, text):
        self.txt_log.config(state='normal')
        self.txt_log.delete("1.0", "end")
        for line in text.splitlines(keepends=True):
            if line.startswith("═") or "MÔ PHỎNG:" in line or "TỔNG KẾT:" in line:
                tag = "header"
            elif line.startswith("─") or ("Thẻ" in line and "ĐÍCH" in line):
                tag = "dest"
            elif "⚡" in line or "ĐÍCH SẠC" in line:
                tag = "warning"
            elif "↻" in line or "TURN_L" in line or "TURN_R" in line:
                tag = "turn"
            elif "SPEED" in line:
                tag = "speed"
            elif "✏ Override" in line:
                tag = "override"
            elif "✗" in line or "LỖI" in line:
                tag = "error"
            elif "⚠" in line or "CẢNH BÁO" in line:
                tag = "warning"
            else:
                tag = "normal"
            self.txt_log.insert("end", line, tag)
        self.txt_log.config(state='disabled')
        self.txt_log.yview_moveto(0)

    def _refresh_dir_options(self, *_):
        """
        Cập nhật Combobox hướng xe dựa theo các node kết nối VÀO start_tag.
        Mỗi option hiển thị giờ đồng hồ xấp xỉ hướng xe đang hướng khi đến start_tag.
        Quy ước: 12h = lên (y giảm trên màn hình), 3h = phải, 6h = xuống, 9h = trái.
        """
        import math
        try:
            start = int(self.var_start.get())
        except ValueError:
            self.cmb_dir['values'] = ["— Nhập thẻ bắt đầu trước —"]
            self.cmb_dir.current(0)
            self._prev_tag_map = {}
            self.lbl_dir_note.config(text="")
            return

        g = self.tm.graph
        if not g.has_node(start):
            self.cmb_dir['values'] = [f"⚠ Thẻ {start} không có trong bản đồ"]
            self.cmb_dir.current(0)
            self._prev_tag_map = {}
            self.lbl_dir_note.config(text="")
            return

        def _gxy(ndata):
            return (ndata.get('disp_x', ndata.get('x', 0)),
                    ndata.get('disp_y', ndata.get('y', 0)))
        sx, sy = _gxy(g.nodes[start])

        # Chỉ hiển thị hướng RA (successors) — tránh chọn hướng vào một chiều
        # VD: 72 chỉ có outgoing → 412; không cho chọn "12h → 411" vì 411→72 là đường vào
        all_neighbors = sorted(set(g.successors(start)))

        options = ["— Không xác định (Dijkstra thuần) —"]
        self._prev_tag_map   = {"— Không xác định (Dijkstra thuần) —": None}
        self._facing_tag_map = {"— Không xác định (Dijkstra thuần) —": None}

        for nb in all_neighbors:
            px, py = _gxy(g.nodes[nb])
            # Outward: start → neighbor (hướng đầu xe nhìn ra)
            dx, dy = px - sx, py - sy
            angle_deg = math.degrees(math.atan2(-dy, dx))
            clock_angle = (90 - angle_deg) % 360
            hour = round(clock_angle / 30) % 12
            hour = 12 if hour == 0 else hour
            label = f"{hour:>2}h  →  Thẻ {nb}"
            options.append(label)

            # facing_tag = nb (đầu xe đang hướng về nb)
            # Dùng cho rotation detection: vin = vector(start → nb) = hướng đầu xe
            self._facing_tag_map[label] = nb

            # prev_tag cho pathfinding: node ngược chiều nb (bias Dijkstra theo hướng xe)
            # Nếu không có node ngược thực sự → None (fallback Dijkstra thuần)
            fmag = math.hypot(dx, dy)
            best_prev, best_dot = None, 1.0
            for nb2 in all_neighbors:
                if nb2 == nb:
                    continue
                nx2, ny2 = _gxy(g.nodes[nb2])
                dnx, dny = nx2 - sx, ny2 - sy
                mag2 = math.hypot(dnx, dny)
                if fmag < 1e-6 or mag2 < 1e-6:
                    continue
                dot2 = (dx * dnx + dy * dny) / (fmag * mag2)
                if dot2 < best_dot:
                    best_dot, best_prev = dot2, nb2
            self._prev_tag_map[label] = best_prev if (best_prev is not None and best_dot < 0) else None

        cur_sel = self.cmb_dir.get()
        self.cmb_dir['values'] = options
        # Giữ lựa chọn cũ nếu vẫn còn hợp lệ
        if cur_sel in options:
            self.cmb_dir.set(cur_sel)
        else:
            self.cmb_dir.current(0)

        n = len(all_neighbors)
        note = f"{n} hướng kết nối — " + ("ngã tư" if n == 4 else
                                            "ngã ba" if n == 3 else
                                            "ngã năm" if n == 5 else
                                            f"{n} cạnh")
        self.lbl_dir_note.config(text=note)

    def _highlight_comments(self):
        self.txt_ov.tag_remove("comment", "1.0", "end")
        content = self.txt_ov.get("1.0", "end")
        for lineno, line in enumerate(content.splitlines(), 1):
            if line.strip().startswith("#"):
                self.txt_ov.tag_add("comment", f"{lineno}.0", f"{lineno}.end")


# ══════════════════════════════════════════════════════════════════════════════
# SimMapView — Mini bản đồ xem kết quả mô phỏng
# ══════════════════════════════════════════════════════════════════════════════

class SimMapView(tk.Toplevel):
    """Cửa sổ bản đồ mini hiển thị path mô phỏng với màu action và hướng xe."""

    # Màu theo loại action
    _ACTION_COLOR = {
        ACT_TURN_L:   "#F0A500",  # cam — quay trái
        ACT_TURN_R:   "#E87722",  # cam đậm — quay phải
        ACT_WAIT_SYS: "#E74C3C",  # đỏ — chờ hệ thống
        ACT_WAIT_USER:"#E67E22",  # cam tối — chờ người dùng
        ACT_DIR_BWD:  "#9B59B6",  # tím — chuyển chiều lùi
        ACT_DIR_FWD:  "#3498DB",  # xanh dương — chuyển chiều tiến
    }
    _NODE_R   = 10   # bán kính node (px)
    _ARROW_L  = 20   # chiều dài mũi tên hướng (px)
    _PAD      = 60   # padding quanh bản đồ (px)

    def __init__(self, parent, tm, steps, start_node, end_node, task_type):
        super().__init__(parent)
        self.tm        = tm
        self.steps     = steps          # list of {tag, actions:[{code,value,label,...}]}
        self.start_node = start_node
        self.end_node   = end_node
        self.task_type  = task_type

        self.title(f"🗺 Bản đồ mô phỏng: Thẻ {start_node} → {end_node}  [{task_type}]")
        self.geometry("900x680")
        self.resizable(True, True)
        self.lift()
        self.focus_force()

        self._build_ui()
        self.bind("<Configure>", lambda e: self._redraw())

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Legend toolbar
        tb = ttk.Frame(self, padding=(6, 4))
        tb.pack(fill='x')
        ttk.Label(tb, text="Chú thích:", font=("Arial", 9, "bold")).pack(side='left', padx=(0, 6))
        for label, color in [
            ("Path",      "#2ECC71"),
            ("TURN",      "#F0A500"),
            ("WAIT_SYS",  "#E74C3C"),
            ("WAIT_USER", "#E67E22"),
            ("BWD",       "#9B59B6"),
            ("Bắt đầu",   "#00BFFF"),
            ("Đích",      "#FF4136"),
        ]:
            fr = tk.Frame(tb, bg=color, width=12, height=12)
            fr.pack(side='left', padx=2, pady=2)
            ttk.Label(tb, text=label, font=("Arial", 8)).pack(side='left', padx=(0, 8))

        # Canvas
        self.canvas = tk.Canvas(self, bg="#1a1a2e", highlightthickness=0)
        self.canvas.pack(fill='both', expand=True, padx=4, pady=(0, 4))
        self.canvas.bind("<MouseWheel>", self._on_scroll)
        self.canvas.bind("<ButtonPress-1>", self._on_pan_start)
        self.canvas.bind("<B1-Motion>",     self._on_pan_move)
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._scale = 1.0

        self.after(50, self._redraw)   # vẽ sau khi window đã có kích thước thật

    # ── Coordinate helpers ────────────────────────────────────────────────────

    def _node_xy(self, node_id):
        """Trả về (disp_x, disp_y) từ graph."""
        nd = self.tm.graph.nodes.get(node_id, {})
        x = nd.get('disp_x', nd.get('x', 0.0))
        y = nd.get('disp_y', nd.get('y', 0.0))
        return float(x), float(y)

    def _to_screen(self, wx, wy):
        """World → screen (canvas px)."""
        return (wx * self._scale + self._ox + self._pan_x,
                wy * self._scale + self._oy + self._pan_y)

    # ── Drawing ───────────────────────────────────────────────────────────────

    def _redraw(self):
        self.canvas.delete("all")
        g      = self.tm.graph
        W      = self.canvas.winfo_width()
        H      = self.canvas.winfo_height()
        if W < 10 or H < 10:
            return

        # Tính bounding box toàn bộ node trong graph
        xs = [self._node_xy(n)[0] for n in g.nodes if g.has_node(n)]
        ys = [self._node_xy(n)[1] for n in g.nodes if g.has_node(n)]
        if not xs:
            return
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        span_x = max_x - min_x or 1
        span_y = max_y - min_y or 1
        PAD    = self._PAD

        sx = (W - 2 * PAD) / span_x
        sy = (H - 2 * PAD) / span_y
        self._scale = min(sx, sy)
        self._ox = PAD - min_x * self._scale
        self._oy = PAD - min_y * self._scale

        # Xây dựng tập node và edge của path mô phỏng
        path_nodes  = [s['tag'] for s in self.steps]
        path_set    = set(path_nodes)
        # map node → dominant action codes tại đó
        node_actions: dict[int, list] = {}
        node_heading: dict[int, tuple] = {}   # node → (dx, dy) unit vector heading
        # Trạng thái chiều lùi tích lũy qua các bước (không reset mỗi vòng lặp)
        step_bwd = self.task_type in ("return_reversing_charge", "return_charge")

        for i, step in enumerate(self.steps):
            nd   = step['tag']
            acts = [a['code'] for a in step.get('actions', [])]
            node_actions[nd] = acts

            # Cập nhật trạng thái chiều từ action tại step này (trước khi tính heading)
            for a in step.get('actions', []):
                if a['code'] == ACT_DIR_BWD:
                    step_bwd = True
                elif a['code'] == ACT_DIR_FWD:
                    step_bwd = False

            # Hướng xe tại node này: dùng path sequence
            if i + 1 < len(self.steps):
                nx_n = self.steps[i + 1]['tag']
                wx, wy = self._node_xy(nd)
                nx, ny = self._node_xy(nx_n)
                dx, dy = nx - wx, ny - wy
            elif i > 0:
                wx, wy = self._node_xy(self.steps[i - 1]['tag'])
                cx, cy = self._node_xy(nd)
                dx, dy = cx - wx, cy - wy
            else:
                dx, dy = 1.0, 0.0
            # Khi lùi: đầu xe ngược chiều di chuyển
            if step_bwd:
                dx, dy = -dx, -dy
            mag = math.hypot(dx, dy)
            node_heading[nd] = (dx / mag, dy / mag) if mag > 1e-6 else (1.0, 0.0)

        # ── Vẽ tất cả edges (nền) ──
        for u, v in g.edges():
            if not (g.has_node(u) and g.has_node(v)):
                continue
            ux, uy = self._to_screen(*self._node_xy(u))
            vx, vy = self._to_screen(*self._node_xy(v))
            self.canvas.create_line(ux, uy, vx, vy,
                                    fill="#2c3e50", width=1)

        # ── Vẽ path mô phỏng (highlight edges) ──
        for i in range(len(path_nodes) - 1):
            a, b = path_nodes[i], path_nodes[i + 1]
            ax, ay = self._to_screen(*self._node_xy(a))
            bx, by = self._to_screen(*self._node_xy(b))
            self.canvas.create_line(ax, ay, bx, by,
                                    fill="#2ECC71", width=3, dash=(6, 3))

        # ── Vẽ tất cả nodes (nền) ──
        R = max(4, int(self._NODE_R * min(self._scale, 1.0)))
        for node_id in g.nodes():
            sx2, sy2 = self._to_screen(*self._node_xy(node_id))
            color = "#2c3e50" if node_id not in path_set else "#1e8449"
            self.canvas.create_oval(sx2 - R, sy2 - R, sx2 + R, sy2 + R,
                                    fill=color, outline="#444", width=1)

        # ── Vẽ nodes trong path với màu action + số thẻ + mũi tên hướng ──
        R2 = max(6, int(self._NODE_R * min(self._scale + 0.2, 1.2)))
        for i, step in enumerate(self.steps):
            nd   = step['tag']
            acts = node_actions.get(nd, [])
            sx2, sy2 = self._to_screen(*self._node_xy(nd))

            # Màu: ưu tiên action quan trọng nhất
            color = "#2ECC71"  # default: running
            for priority_code in (ACT_WAIT_SYS, ACT_WAIT_USER,
                                   ACT_TURN_L, ACT_TURN_R,
                                   ACT_DIR_BWD, ACT_DIR_FWD):
                if priority_code in acts:
                    color = self._ACTION_COLOR.get(priority_code, color)
                    break

            # Override màu cho start/end
            if nd == self.start_node:
                color = "#00BFFF"
            elif nd == self.end_node:
                color = "#FF4136"

            self.canvas.create_oval(sx2 - R2, sy2 - R2, sx2 + R2, sy2 + R2,
                                    fill=color, outline="white", width=2)

            # Số thẻ
            fs = max(7, min(10, int(self._scale * 6)))
            self.canvas.create_text(sx2, sy2 - R2 - 3,
                                    text=str(nd), fill="white",
                                    font=("Arial", fs, "bold"), anchor='s')

            # Mũi tên hướng xe
            hx, hy = node_heading.get(nd, (1.0, 0.0))
            AL     = max(12, int(self._ARROW_L * min(self._scale, 1.0)))
            ex, ey = sx2 + hx * AL, sy2 + hy * AL
            self.canvas.create_line(sx2, sy2, ex, ey,
                                    fill="white", width=2, arrow='last',
                                    arrowshape=(8, 10, 4))

            # Index bước
            self.canvas.create_text(sx2 + R2 + 2, sy2,
                                    text=f"#{i + 1}", fill="#aaaaaa",
                                    font=("Arial", max(6, fs - 1)), anchor='w')

            # Action labels nhỏ (không vẽ RUN / LIDAR)
            skip_codes = {ACT_RUN, ACT_LIDAR_OFF, ACT_LIDAR_ON}
            act_labels = []
            for a in step.get('actions', []):
                if a['code'] not in skip_codes:
                    act_labels.append(a.get('label', '')[:8])
            if act_labels:
                label_txt = " ".join(act_labels[:3])
                self.canvas.create_text(sx2, sy2 + R2 + 4,
                                        text=label_txt, fill="#FFD700",
                                        font=("Arial", max(6, fs - 1)), anchor='n')

        # Tiêu đề
        self.canvas.create_text(W / 2, 12,
            text=f"Mô phỏng: {self.task_type} | Thẻ {self.start_node} → {self.end_node} | {len(self.steps)} bước",
            fill="#ECF0F1", font=("Arial", 9, "bold"), anchor='n')

    # ── Pan / Zoom ────────────────────────────────────────────────────────────

    def _on_scroll(self, event):
        factor = 1.1 if event.delta > 0 else 0.9
        self._scale *= factor
        self._redraw()

    def _on_pan_start(self, event):
        self._drag_x = event.x
        self._drag_y = event.y

    def _on_pan_move(self, event):
        self._pan_x += event.x - self._drag_x
        self._pan_y += event.y - self._drag_y
        self._drag_x = event.x
        self._drag_y = event.y
        self._redraw()
