"""Nhận diện thang máy đã kết nối server (elevator/v1) — KHÔNG điều khiển gì, chỉ ghi nhận bằng chứng "thang còn sống".

Bằng chứng, theo thứ tự ưu tiên (cái nào MỚI hơn thì thắng):
  1. elevator/v1/{factory}/{id}/connection  — ONLINE/OFFLINE (thang đặt Last Will; broker tự báo OFFLINE khi thang rớt).
  2. elevator/v1/{factory}/{id}/state       — tin trạng thái SỐNG (không retain) = thang đang gửi tin.
Tin state RETAINED mà broker giao lại lúc server vừa subscribe chỉ cho biết "đã từng thấy" (stale) — KHÔNG tính online,
vì thang tắt hẳn vẫn còn tin retain cũ trên broker.

Không có tin connection thì online = có tin state sống trong LIVE_TIMEOUT_SEC giây gần nhất (thang publish lại định kỳ).
"""
import json
import threading
import time

LIVE_TIMEOUT_SEC = 30.0


class _Seen:
    __slots__ = ("factory", "state", "level", "state_live_at", "state_any_at",
                 "conn", "conn_at", "msgs")

    def __init__(self):
        self.factory = ""
        self.state = None
        self.level = None
        self.state_live_at = None    # monotonic: tin state sống gần nhất
        self.state_any_at = None     # wall-clock: tin state bất kỳ (kể cả retained) gần nhất
        self.conn = None             # True/False/None theo topic connection
        self.conn_at = None          # monotonic: lúc nhận tin connection
        self.msgs = 0


class ElevatorRegistry:
    def __init__(self):
        self._lock = threading.Lock()
        self._seen: dict[str, _Seen] = {}

    def _get(self, eid: str) -> _Seen:
        s = self._seen.get(eid)
        if s is None:
            s = self._seen[eid] = _Seen()
        return s

    def on_state(self, factory: str, eid: str, state: str, level, retained: bool) -> None:
        with self._lock:
            s = self._get(eid)
            s.factory = factory or s.factory
            s.state, s.level = state, level
            s.state_any_at = time.time()
            s.msgs += 1
            if not retained:
                s.state_live_at = time.monotonic()

    def on_connection(self, factory: str, eid: str, payload: bytes) -> None:
        raw = payload.decode("utf-8", errors="replace").strip()
        val = raw
        try:
            d = json.loads(raw)
            if isinstance(d, dict):
                val = d.get("connectionState") or d.get("connection") or d.get("state") or d.get("status") or ""
            elif isinstance(d, str):
                val = d
        except ValueError:
            pass
        val = str(val).strip().upper()
        if val in ("ONLINE", "1", "TRUE", "CONNECTED"):
            online = True
        elif val in ("OFFLINE", "0", "FALSE", "CONNECTIONBROKEN", "DISCONNECTED"):
            online = False
        else:
            return
        with self._lock:
            s = self._get(eid)
            s.factory = factory or s.factory
            s.conn, s.conn_at = online, time.monotonic()

    @staticmethod
    def _link(s: _Seen) -> tuple[str, str]:
        """(link, nguồn): link ∈ online | offline | stale (chỉ có tin retained cũ) | never."""
        now = time.monotonic()
        live_ok = s.state_live_at is not None and now - s.state_live_at <= LIVE_TIMEOUT_SEC
        if s.conn is not None:
            # tin state sống MỚI hơn tin connection cuối → thang rõ ràng đang gửi tin
            if s.conn is False and s.state_live_at is not None and s.state_live_at >= (s.conn_at or 0) and live_ok:
                return "online", "state"
            return ("online" if s.conn else "offline"), "connection"
        if live_ok:
            return "online", "state"
        if s.state_live_at is not None:
            return "offline", "state"          # từng gửi tin sống nhưng đã im quá hạn
        if s.state_any_at is not None:
            return "stale", "retained"         # chỉ có tin retained cũ trên broker
        return "never", ""

    def info(self, eid: str) -> dict:
        with self._lock:
            s = self._seen.get(eid)
            if s is None:
                return {"link": "never", "online": False, "source": "", "last_seen_sec": None, "factory": "",
                        "state": None, "level": None, "msgs": 0}
            link, src = self._link(s)
            last = None
            if s.state_live_at is not None or s.conn_at is not None:
                last = min(time.monotonic() - t for t in (s.state_live_at, s.conn_at) if t is not None)
            elif s.state_any_at is not None:
                last = time.time() - s.state_any_at
            return {"link": link, "online": link == "online", "source": src,
                    "last_seen_sec": None if last is None else round(last, 1), "factory": s.factory,
                    "state": s.state, "level": s.level, "msgs": s.msgs}

    def seen_ids(self) -> list[str]:
        with self._lock:
            return list(self._seen.keys())


elevator_registry = ElevatorRegistry()
