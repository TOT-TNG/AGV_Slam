"""
log_buffer.py — Capture server print output vào in-memory ring buffer.
Import module này SỚM (trước các import khác trong main.py) để bắt được toàn bộ log.
"""
import builtins as _builtins
import time
import threading
from collections import deque

_MAX_LINES = 2000
_lock      = threading.Lock()
_buf: deque = deque(maxlen=_MAX_LINES)
_orig_print = _builtins.print   # giữ bản gốc


def _capture_print(*args, **kwargs):
    _orig_print(*args, **kwargs)
    try:
        text = " ".join(str(a) for a in args)
        if text.strip():
            with _lock:
                _buf.append({"t": round(time.time(), 3), "m": text})
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
