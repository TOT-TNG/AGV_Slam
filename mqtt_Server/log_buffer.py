"""
log_buffer.py — Capture server print output vào in-memory ring buffer
và đồng thời ghi ra file log theo ngày (logs/server_YYYY-MM-DD.log),
mỗi dòng kèm timestamp cụ thể. File log quá 7 ngày sẽ tự động bị xóa.
Import module này SỚM (trước các import khác trong main.py) để bắt được toàn bộ log.
"""
import builtins as _builtins
import os
import time
import threading
from collections import deque
from datetime import datetime, timedelta

_MAX_LINES = 2000
_RETENTION_DAYS = 7
_MAX_FILE_BYTES = 200 * 1024 * 1024   # trần an toàn / ngày, tránh log phình vô hạn
_LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")

_lock      = threading.Lock()
_buf: deque = deque(maxlen=_MAX_LINES)
_orig_print = _builtins.print   # giữ bản gốc

_current_date: str | None = None
_current_file = None
_current_size = 0
_cap_notified = False


def _cleanup_old_logs() -> None:
    cutoff = datetime.now() - timedelta(days=_RETENTION_DAYS)
    try:
        names = os.listdir(_LOG_DIR)
    except FileNotFoundError:
        return
    for name in names:
        if not (name.startswith("server_") and name.endswith(".log")):
            continue
        try:
            file_date = datetime.strptime(name[len("server_"):-len(".log")], "%Y-%m-%d")
        except ValueError:
            continue
        if file_date < cutoff:
            try:
                os.remove(os.path.join(_LOG_DIR, name))
            except OSError:
                pass


def _get_file():
    global _current_date, _current_file, _current_size, _cap_notified
    today = datetime.now().strftime("%Y-%m-%d")
    if _current_file is None or _current_date != today:
        if _current_file is not None:
            try:
                _current_file.close()
            except Exception:
                pass
        os.makedirs(_LOG_DIR, exist_ok=True)
        path = os.path.join(_LOG_DIR, f"server_{today}.log")
        _current_file = open(path, "a", encoding="utf-8")
        _current_size = os.path.getsize(path) if os.path.exists(path) else 0
        _current_date = today
        _cap_notified = False
        _cleanup_old_logs()
    return _current_file


def _capture_print(*args, **kwargs):
    global _current_size, _cap_notified
    _orig_print(*args, **kwargs)
    try:
        text = " ".join(str(a) for a in args)
        if text.strip():
            now = time.time()
            with _lock:
                _buf.append({"t": round(now, 3), "m": text})
                f = _get_file()
                if _current_size < _MAX_FILE_BYTES:
                    stamp = datetime.fromtimestamp(now).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                    line = f"[{stamp}] {text}\n"
                    f.write(line)
                    f.flush()
                    _current_size += len(line.encode("utf-8"))
                elif not _cap_notified:
                    _cap_notified = True
                    cap_line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}] [LOG_BUFFER] Đã đạt trần {_MAX_FILE_BYTES // (1024*1024)}MB cho hôm nay — ngừng ghi file, log vẫn hiển thị qua RAM buffer.\n"
                    f.write(cap_line)
                    f.flush()
    except Exception:
        pass


_builtins.print = _capture_print   # hook toàn bộ print trong process


def get_logs(limit: int = 500, offset: int = 0) -> list[dict]:
    with _lock:
        lines = list(_buf)
    lines.reverse()   # mới nhất lên đầu
    return lines[offset: offset + limit]


def clear_logs() -> None:
    with _lock:
        _buf.clear()
