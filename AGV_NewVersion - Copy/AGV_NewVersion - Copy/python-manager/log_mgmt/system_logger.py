"""
log_mgmt/system_logger.py  — System Event Logger
-------------------------------------------------
Ghi toàn bộ sự kiện hệ thống ra file log theo ngày.
Format: HH:MM:SS.mmm [LEVEL] [SOURCE] message

Cách dùng:
    from log_mgmt.system_logger import sys_log, LOG_MQTT_IN, LOG_MQTT_OUT
    sys_log("MQTT_IN", "message_handler", f"RECV {topic}: {payload}")
    sys_log("ERROR", "traffic", "Deadlock detected between AGV01 and AGV02")
"""
from __future__ import annotations
import os
import threading
import datetime
from typing import Callable

# ── Thư mục log ────────────────────────────────────────────────────────────────
_LOG_DIR = os.path.join(os.path.dirname(__file__), '..', 'logs', 'system')

# ── Level tags ─────────────────────────────────────────────────────────────────
LOG_INFO     = "INFO"
LOG_WARN     = "WARN"
LOG_ERROR    = "ERROR"
LOG_MQTT_IN  = "MQTT_IN"
LOG_MQTT_OUT = "MQTT_OUT"
LOG_SYSTEM   = "SYSTEM"
LOG_TRAFFIC  = "TRAFFIC"
LOG_DISPATCH = "DISPATCH"
LOG_ARDUINO  = "ARDUINO"

# ── Internal state ─────────────────────────────────────────────────────────────
_lock       = threading.Lock()
_listeners: list[Callable[[str], None]] = []   # GUI callbacks nhận log line
_current_date: str = ""
_log_file   = None


def _ensure_file():
    """Mở (hoặc rotate) file log theo ngày hiện tại."""
    global _log_file, _current_date
    today = datetime.date.today().isoformat()   # "2026-04-19"
    if today == _current_date and _log_file:
        return
    # Đóng file cũ nếu đang mở
    if _log_file:
        try:
            _log_file.close()
        except Exception:
            pass
    os.makedirs(_LOG_DIR, exist_ok=True)
    path = os.path.join(_LOG_DIR, f"system_{today}.log")
    _log_file   = open(path, 'a', encoding='utf-8', buffering=1)  # line-buffered
    _current_date = today


def sys_log(level: str, source: str, message: str):
    """
    Ghi 1 dòng log ra file + thông báo tất cả GUI listeners.

    Args:
        level:   LOG_INFO / LOG_ERROR / LOG_MQTT_IN / ...
        source:  tên module gọi, VD: "message_handler", "traffic", "agv01"
        message: nội dung log
    """
    now = datetime.datetime.now()
    line = f"{now.strftime('%H:%M:%S')}.{now.microsecond // 1000:03d}  [{level:<8}]  [{source}]  {message}\n"

    with _lock:
        try:
            _ensure_file()
            _log_file.write(line)
        except Exception as e:
            print(f"[SysLog] Cannot write log: {e}")

        # In ra terminal như cũ
        print(line, end='')

        # Thông báo GUI listeners (phải thread-safe — Tkinter gọi after())
        for cb in _listeners:
            try:
                cb(line)
            except Exception:
                pass


def register_listener(callback: Callable[[str], None]):
    """Đăng ký hàm callback nhận mỗi dòng log mới (dùng cho GUI)."""
    with _lock:
        if callback not in _listeners:
            _listeners.append(callback)


def unregister_listener(callback: Callable[[str], None]):
    with _lock:
        if callback in _listeners:
            _listeners.remove(callback)


def get_log_dates() -> list[str]:
    """Trả về danh sách ngày có file log, mới nhất trước."""
    if not os.path.exists(_LOG_DIR):
        return []
    dates = []
    for fname in os.listdir(_LOG_DIR):
        if fname.startswith("system_") and fname.endswith(".log"):
            date = fname[7:-4]   # "system_2026-04-19.log" → "2026-04-19"
            dates.append(date)
    return sorted(dates, reverse=True)


def read_log_file(date: str) -> str:
    """Đọc toàn bộ nội dung file log của ngày `date` (YYYY-MM-DD)."""
    path = os.path.join(_LOG_DIR, f"system_{date}.log")
    if not os.path.exists(path):
        return f"[Không tìm thấy log ngày {date}]\n"
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"[Lỗi đọc file: {e}]\n"


def close():
    """Đóng file log khi thoát ứng dụng."""
    global _log_file
    with _lock:
        if _log_file:
            try:
                _log_file.close()
            except Exception:
                pass
            _log_file = None
