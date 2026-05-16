"""
gui/log_view.py  — System Log Viewer
--------------------------------------
Tab hiển thị log hệ thống theo phong cách terminal.
- Live: nhận log mới từ system_logger listener
- History: chọn ngày để đọc file log cũ
- Auto-scroll, filter theo level, tìm kiếm
"""
from __future__ import annotations
import datetime
import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

from log_mgmt.system_logger import (
    register_listener, unregister_listener,
    get_log_dates, read_log_file,
    LOG_INFO, LOG_WARN, LOG_ERROR,
    LOG_MQTT_IN, LOG_MQTT_OUT, LOG_SYSTEM, LOG_TRAFFIC, LOG_DISPATCH, LOG_ARDUINO,
)

if TYPE_CHECKING:
    pass

# ── Màu sắc theo level (terminal style) ────────────────────────────────────────
_LEVEL_COLORS: dict[str, str] = {
    LOG_INFO:     "#d4d4d4",   # Trắng xám
    LOG_WARN:     "#e5c07b",   # Vàng
    LOG_ERROR:    "#e06c75",   # Đỏ
    LOG_MQTT_IN:  "#61afef",   # Xanh dương (nhận từ xe)
    LOG_MQTT_OUT: "#98c379",   # Xanh lá (gửi xuống xe)
    LOG_SYSTEM:   "#c678dd",   # Tím (sự kiện hệ thống)
    LOG_TRAFFIC:  "#56b6c2",   # Cyan (điều phối)
    LOG_DISPATCH: "#d19a66",   # Cam (phân công)
    LOG_ARDUINO:  "#be5046",   # Đỏ tối (UART/Arduino)
}
_DEFAULT_COLOR = "#abb2bf"
_BG_COLOR      = "#1e1e1e"
_TOOLBAR_BG    = "#252526"
_TIMESTAMP_COL = "#5c6370"


def _level_of_line(line: str) -> str:
    """Trích level từ dòng log: '12:34:56.789  [MQTT_IN  ]  ...' → 'MQTT_IN'"""
    try:
        start = line.index('[') + 1
        end   = line.index(']', start)
        return line[start:end].strip()
    except ValueError:
        return ""


def build_panel(shell):
    """Tạo và hiển thị Log View vào content_frame của AppShell."""
    shell.frm_log = tk.Frame(shell.content_frame, bg=_BG_COLOR)
    shell.frm_log.pack(fill='both', expand=True)
    _LogView(shell.frm_log, shell)


class _LogView(tk.Frame):
    MAX_LINES = 5000   # Giữ tối đa để tránh memory leak

    def __init__(self, parent, shell):
        super().__init__(parent, bg=_BG_COLOR)
        self.pack(fill='both', expand=True)
        self._shell      = shell
        self._auto_scroll = tk.BooleanVar(value=True)
        self._show_levels = {lvl: tk.BooleanVar(value=True) for lvl in _LEVEL_COLORS}
        self._search_var  = tk.StringVar()
        self._live_mode   = True    # True = xem live, False = xem file ngày cũ
        self._line_count  = 0

        self._build_toolbar()
        self._build_text_area()
        self._build_statusbar()

        # Đăng ký nhận log mới
        register_listener(self._on_new_log_line)
        self.bind("<Destroy>", self._on_destroy)

        # Load log hôm nay khi mở
        self._load_today()

    # ── Toolbar ────────────────────────────────────────────────────────────────

    def _build_toolbar(self):
        tb = tk.Frame(self, bg=_TOOLBAR_BG, pady=4)
        tb.pack(fill='x', side='top')

        # Tiêu đề
        tk.Label(tb, text="📋 System Log", bg=_TOOLBAR_BG, fg="#abb2bf",
                 font=("Consolas", 11, "bold")).pack(side='left', padx=10)

        # Separator
        ttk.Separator(tb, orient='vertical').pack(side='left', fill='y', padx=6, pady=2)

        # Chọn ngày
        tk.Label(tb, text="Ngày:", bg=_TOOLBAR_BG, fg="#abb2bf",
                 font=("Consolas", 10)).pack(side='left', padx=(4, 2))
        self._date_var = tk.StringVar(value="[Live]")
        self._date_combo = ttk.Combobox(tb, textvariable=self._date_var,
                                        width=14, state='readonly',
                                        font=("Consolas", 10))
        self._date_combo.pack(side='left', padx=2)
        self._date_combo.bind("<<ComboboxSelected>>", self._on_date_selected)
        self._refresh_date_list()

        # Nút Live
        self._btn_live = tk.Button(
            tb, text="⚡ Live", command=self._switch_to_live,
            bg="#1a6fa8", fg="white", relief="flat",
            font=("Consolas", 9, "bold"), padx=6, pady=2)
        self._btn_live.pack(side='left', padx=4)

        # Nút Refresh
        tk.Button(
            tb, text="🔄 Refresh", command=self._refresh_current,
            bg="#3a3a3a", fg="#abb2bf", relief="flat",
            font=("Consolas", 9), padx=6, pady=2
        ).pack(side='left', padx=2)

        ttk.Separator(tb, orient='vertical').pack(side='left', fill='y', padx=6, pady=2)

        # Filter levels
        tk.Label(tb, text="Filter:", bg=_TOOLBAR_BG, fg="#abb2bf",
                 font=("Consolas", 9)).pack(side='left', padx=(0, 4))
        level_labels = {
            LOG_MQTT_IN:  "MQTT↓", LOG_MQTT_OUT: "MQTT↑",
            LOG_ERROR:    "ERR",   LOG_WARN:     "WARN",
            LOG_TRAFFIC:  "TRAF",  LOG_DISPATCH: "DISP",
            LOG_SYSTEM:   "SYS",   LOG_INFO:     "INFO",
        }
        for lvl, label in level_labels.items():
            color = _LEVEL_COLORS.get(lvl, _DEFAULT_COLOR)
            cb = tk.Checkbutton(
                tb, text=label, variable=self._show_levels[lvl],
                command=self._apply_filter,
                bg=_TOOLBAR_BG, fg=color, selectcolor="#333333",
                activebackground=_TOOLBAR_BG, activeforeground=color,
                font=("Consolas", 9), bd=0)
            cb.pack(side='left', padx=1)

        # Search
        ttk.Separator(tb, orient='vertical').pack(side='left', fill='y', padx=6, pady=2)
        tk.Label(tb, text="🔍", bg=_TOOLBAR_BG, fg="#abb2bf").pack(side='left')
        tk.Entry(tb, textvariable=self._search_var, width=16,
                 bg="#2d2d2d", fg="#abb2bf", insertbackground="#abb2bf",
                 relief="flat", font=("Consolas", 10)
                 ).pack(side='left', padx=4)
        self._search_var.trace_add("write", lambda *_: self._apply_filter())

        # Nút Clear
        tk.Button(
            tb, text="🗑 Clear", command=self._clear,
            bg="#3a3a3a", fg="#e06c75", relief="flat",
            font=("Consolas", 9), padx=6, pady=2
        ).pack(side='right', padx=8)

        # Auto-scroll
        tk.Checkbutton(
            tb, text="Auto-scroll", variable=self._auto_scroll,
            bg=_TOOLBAR_BG, fg="#abb2bf", selectcolor="#333333",
            activebackground=_TOOLBAR_BG, activeforeground="#abb2bf",
            font=("Consolas", 9), bd=0
        ).pack(side='right', padx=4)

    # ── Text area ──────────────────────────────────────────────────────────────

    def _build_text_area(self):
        frm = tk.Frame(self, bg=_BG_COLOR)
        frm.pack(fill='both', expand=True, side='top')

        self._txt = tk.Text(
            frm,
            bg=_BG_COLOR, fg=_DEFAULT_COLOR,
            font=("Consolas", 10),
            insertbackground="#abb2bf",
            state='disabled',
            wrap='none',
            relief='flat',
            bd=0,
            selectbackground="#264f78",
        )
        # Scrollbars
        vsb = ttk.Scrollbar(frm, orient='vertical',   command=self._txt.yview)
        hsb = ttk.Scrollbar(frm, orient='horizontal', command=self._txt.xview)
        self._txt.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        hsb.pack(side='bottom', fill='x')
        vsb.pack(side='right',  fill='y')
        self._txt.pack(side='left', fill='both', expand=True)

        # Tags màu theo level
        for lvl, color in _LEVEL_COLORS.items():
            self._txt.tag_configure(f"lvl_{lvl}", foreground=color)
        self._txt.tag_configure("ts",     foreground=_TIMESTAMP_COL)
        self._txt.tag_configure("hidden", elide=True)

        # Tạm dừng auto-scroll khi người dùng kéo thanh cuộn
        vsb.bind("<ButtonPress-1>",   lambda e: self._auto_scroll.set(False))
        self._txt.bind("<MouseWheel>", lambda e: self._auto_scroll.set(False))

    def _build_statusbar(self):
        self._status_var = tk.StringVar(value="")
        sb = tk.Label(self, textvariable=self._status_var,
                      bg="#007acc", fg="white",
                      font=("Consolas", 9), anchor='w', padx=8)
        sb.pack(fill='x', side='bottom')

    # ── Log rendering ──────────────────────────────────────────────────────────

    def _append_line(self, line: str):
        """Thêm 1 dòng vào Text widget với màu phù hợp."""
        if not line.strip():
            return

        level   = _level_of_line(line)
        visible = self._show_levels.get(level, tk.BooleanVar(value=True))

        # Filter theo search keyword
        kw = self._search_var.get().strip().lower()
        if kw and kw not in line.lower():
            return

        # Chọn tag màu
        tag = f"lvl_{level}" if level in _LEVEL_COLORS else ""

        self._txt.configure(state='normal')

        # Giới hạn số dòng
        if self._line_count >= self.MAX_LINES:
            self._txt.delete("1.0", "500.end+1c")
            self._line_count -= 500

        # Thêm dòng với tag
        start_idx = self._txt.index('end')
        self._txt.insert('end', line)
        if tag:
            # Tô màu timestamp riêng (phần đầu đến dấu '[')
            end_ts = line.find('[')
            if end_ts > 0:
                self._txt.tag_add("ts", f"{start_idx}", f"{start_idx}+{end_ts}c")
                self._txt.tag_add(tag, f"{start_idx}+{end_ts}c", 'end-1c')
            else:
                self._txt.tag_add(tag, start_idx, 'end-1c')

        # Ẩn nếu level bị filter tắt
        if not visible.get():
            line_num = start_idx.split('.')[0]
            self._txt.tag_add("hidden", f"{line_num}.0", f"{line_num}.end+1c")

        self._line_count += 1
        self._txt.configure(state='disabled')

        if self._auto_scroll.get():
            self._txt.see('end')

        self._status_var.set(
            f"  Dòng: {self._line_count}  |  "
            f"{'🟢 Live' if self._live_mode else '📂 File: ' + self._date_var.get()}"
        )

    def _load_lines(self, content: str):
        """Nạp toàn bộ nội dung (khi load file)."""
        self._txt.configure(state='normal')
        self._txt.delete("1.0", 'end')
        self._txt.configure(state='disabled')
        self._line_count = 0
        for line in content.splitlines(keepends=True):
            self._append_line(line)

    # ── Filter (ẩn/hiện dòng theo level/keyword) ───────────────────────────────

    def _apply_filter(self):
        """Re-load nội dung hiện tại với filter mới."""
        if self._live_mode:
            # Live: không thể re-load dễ dàng → thông báo
            self._status_var.set("  Filter áp dụng cho dòng mới. Nhấn Refresh để lọc toàn bộ.")
        else:
            self._refresh_current()

    # ── Event handlers ─────────────────────────────────────────────────────────

    def _on_new_log_line(self, line: str):
        """Callback từ system_logger — chạy trên thread MQTT, phải dùng after()."""
        if self._live_mode:
            self._shell.after(0, lambda l=line: self._append_line(l))

    def _on_date_selected(self, event=None):
        date = self._date_var.get()
        if date == "[Live]":
            self._switch_to_live()
        else:
            self._live_mode = False
            self._btn_live.config(bg="#3a3a3a")
            content = read_log_file(date)
            self._load_lines(content)

    def _switch_to_live(self):
        self._live_mode = True
        self._btn_live.config(bg="#1a6fa8")
        self._date_var.set("[Live]")
        # Load log hôm nay từ file + hiện live tiếp theo
        self._load_today()

    def _load_today(self):
        today = datetime.date.today().isoformat()
        content = read_log_file(today)
        self._load_lines(content)

    def _refresh_current(self):
        if self._live_mode:
            self._load_today()
        else:
            date = self._date_var.get()
            if date not in ("[Live]", ""):
                self._load_lines(read_log_file(date))

    def _refresh_date_list(self):
        dates = get_log_dates()
        values = ["[Live]"] + dates
        self._date_combo['values'] = values

    def _clear(self):
        self._txt.configure(state='normal')
        self._txt.delete("1.0", 'end')
        self._txt.configure(state='disabled')
        self._line_count = 0

    def _on_destroy(self, event):
        unregister_listener(self._on_new_log_line)
