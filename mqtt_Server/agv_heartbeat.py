"""
agv_heartbeat.py — Cập nhật last_seen cho AGV khi nhận MQTT state
-------------------------------------------------------------------
Chạy update DB trong background thread, debounce 2 giây/AGV để tránh
hammer DB mỗi lần nhận message.
"""
from __future__ import annotations

import os
import time
import threading
from typing import Optional

_DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:ducmanh1801@localhost:5432/TOT_AGV",
)

# Debounce: chỉ update DB mỗi AGV tối đa 1 lần / 2 giây
_DEBOUNCE_SEC = 2.0
_last_update: dict[str, float] = {}   # agv_id → monotonic timestamp
_lock = threading.Lock()


def _do_update(agv_id: str, last_tag: str | None = None) -> None:
    try:
        import psycopg2
        conn = psycopg2.connect(_DB_URL)
        conn.autocommit = True
        with conn.cursor() as cur:
            if last_tag is not None:
                cur.execute(
                    "UPDATE agv_devices SET last_seen = now(), last_tag = %s WHERE name = %s",
                    (last_tag, agv_id),
                )
            else:
                cur.execute(
                    "UPDATE agv_devices SET last_seen = now() WHERE name = %s",
                    (agv_id,),
                )
        conn.close()
    except Exception:
        pass   # DB chưa sẵn sàng hoặc AGV chưa được đăng ký → im lặng


def touch(agv_id: str, tag: int | None = None) -> None:
    """
    Gọi khi nhận được MQTT state từ agv_id.
    Update last_seen (và last_tag nếu có) trong DB (debounced, non-blocking).
    """
    now = time.monotonic()
    with _lock:
        last = _last_update.get(agv_id, 0.0)
        if now - last < _DEBOUNCE_SEC:
            return
        _last_update[agv_id] = now

    tag_str = str(tag) if tag is not None else None
    t = threading.Thread(target=_do_update, args=(agv_id, tag_str), daemon=True)
    t.start()
