"""
sim_monitor.py — Theo dõi CHỈ ĐỌC (subscribe state, không gửi lệnh gì) toàn bộ
fleet mô phỏng qua MQTT thật, độc lập hoàn toàn với state nội bộ của server
(để không bị "ăn gian" nếu chính server có bug không log) — tự phát hiện và
ghi JSONL các dấu hiệu lỗi điều phối giao thông:

  COLLISION    — ≥2 xe cùng current_tag trong lúc không phải cả 2 đứng yên
                 hợp lệ (driving=False lâu, không phải khoảnh khắc đi qua).
  HEADON_EDGE  — 2 xe thể hiện cặp (prev_tag,current_tag) đảo chiều của nhau
                 (cùng lúc trên cùng 1 cạnh, 2 hướng ngược).
  STALL        — 1 xe không đổi current_tag quá --stall-timeout giây trong
                 lúc có vẻ vẫn còn tác vụ (driving đã từng True gần đó).
  ERROR_CODE   — xe báo error_code != 0.
  TYPE_DIR_VIOLATION — server in "[TYPE_DIR]": route đi NGƯỢC hướng riêng theo loại xe (type_directions).
  SERVER_EXCEPTION — dòng "Traceback" xuất hiện trong log stdout main.py mô phỏng.

Khi dừng (Ctrl+C) hoặc hết --duration-hours: ghi + in summary_<ts>.json.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import sys
import threading
import time
import uuid
from collections import defaultdict

import paho.mqtt.client as mqtt
import requests

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

UAGV_INTERFACE = "uagv"
UAGV_VERSION   = "v2"


# Server in dòng này mỗi lần xe bị xe khác giữ chỗ tại 1 NGÃ TƯ (node degree≥3)
_JUNCTION_RE = re.compile(r"\[TRAFFIC\] (\S+): (\S+) là NÚT GIAO \(degree≥3\), bị (\S+) giữ chỗ")
JUNCTION_MEET_GAP_SEC  = 30.0    # cùng (xe chờ, node, xe giữ chỗ) cách nhau > 30s = lần gặp MỚI
JUNCTION_STUCK_GAP_SEC = 120.0   # dòng chờ cách nhau > 120s = xe đã qua được ngã tư (hết kẹt)
JUNCTION_STUCK_SEC     = 300.0   # chờ liên tục ≥ 5 phút tại 1 ngã tư = "kẹt ở ngã tư"

# Server in dòng này khi lập plan CÓ bước lùi (DIR_BWD) cho 1 xe. Xe không lùi được (rơ-moóc,
# agv-list: can_reverse=false) mà bị gửi lệnh lùi = server vi phạm ràng buộc của loại xe đó.
_REVERSE_RE = re.compile(r"\[PLAN\] (\S+) \| node \S+: DIR_BWD")
REVERSE_VIOLATION_GAP_SEC = 30.0   # cùng 1 xe: các dòng DIR_BWD cách nhau < 30s gộp thành 1 sự cố
NO_REVERSE_REFRESH_SEC    = 60.0   # tần suất hỏi lại danh sách xe không lùi được


class AgvObserved:
    __slots__ = ("current_tag", "prev_tag", "driving", "error_code", "last_change_ts", "last_update_ts", "busy_since")

    def __init__(self):
        self.current_tag = None
        self.prev_tag = None
        self.driving = False
        self.error_code = 0
        self.last_change_ts = time.time()
        self.last_update_ts = time.time()
        self.busy_since = None   # thời điểm xe bắt đầu có tác vụ (None = đang rảnh)


class SimMonitor:
    def __init__(self, broker: str, port: int, factory: str, violations_path: str,
                 stall_timeout: float, server_log_path: str | None, api_base: str | None):
        self.broker = broker
        self.port = port
        self.factory = factory
        self.stall_timeout = stall_timeout
        self.server_log_path = server_log_path
        self.api_base = api_base

        self.agvs: dict[str, AgvObserved] = defaultdict(AgvObserved)
        self.lock = threading.Lock()
        self.counts: dict[str, int] = defaultdict(int)
        self.worst_agv: dict[str, int] = defaultdict(int)
        self.start_ts = time.time()

        self._vf = open(violations_path, "a", encoding="utf-8")
        self._jx_meet: dict[tuple, float] = {}       # (xe chờ, node, xe giữ) -> ts dòng gần nhất
        self._jx_wait: dict[tuple, dict] = {}        # (xe chờ, node) -> {start,last,flagged}
        self._no_reverse: set[str] = set()            # xe có can_reverse=false (nạp từ agv-list)
        self._no_reverse_ts = 0.0
        self._reverse_last: dict[str, float] = {}     # xe -> ts lần cuối ghi sự cố lùi

        self.client = mqtt.Client(client_id=f"sim_monitor_{uuid.uuid4().hex[:8]}", clean_session=True)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    def _on_connect(self, client, userdata, flags, rc):
        print(f"[MONITOR] connected rc={rc} broker={self.broker}:{self.port}")
        client.subscribe(f"{UAGV_INTERFACE}/{UAGV_VERSION}/{self.factory}/+/state", qos=1)

    def _write_violation(self, kind: str, **fields) -> None:
        rec = {"ts": time.time(), "kind": kind, **fields}
        self._vf.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self._vf.flush()
        self.counts[kind] += 1
        for aid in (fields.get("agv_ids") or ([fields["agv_id"]] if "agv_id" in fields else [])):
            self.worst_agv[aid] += 1
        print(f"[VIOLATION] {kind}: {fields}")

    def _push_map_alert(self, agv_id: str, kind: str, message: str) -> None:
        """Đẩy cảnh báo lên server mô phỏng để hiện NGAY trên map (marker đỏ,
        xem main.py: POST /api/execute/external-alert) — KHÔNG chỉ nằm trong
        bảng text violations. TTL 12s (dài hơn nhịp quét lại) nên cảnh báo tự
        hết nếu không còn vi phạm, không cần gọi "clear" riêng. Lỗi gọi API
        KHÔNG được làm hỏng việc ghi log vi phạm chính — chỉ in cảnh báo console."""
        if not self.api_base:
            return
        try:
            requests.post(f"{self.api_base}/api/execute/external-alert",
                           json={"agv_id": agv_id, "kind": f"SIM_{kind}",
                                 "message": message, "ttl_sec": 12.0},
                           timeout=1.5)
        except Exception as e:
            print(f"[MONITOR] đẩy cảnh báo map cho {agv_id} lỗi (không ảnh hưởng log): {e}")

    def _on_message(self, client, userdata, msg):
        try:
            parts = msg.topic.split("/")
            if len(parts) != 5:
                return
            agv_id = parts[3]
            data = json.loads(msg.payload.decode("utf-8", errors="replace"))
        except Exception:
            return

        tag = data.get("lastNodeId") or data.get("tag")
        if tag is None or tag == "":
            return
        tag = str(tag)
        prev = str(data.get("prev_tag") or "0")
        driving = bool(data.get("driving", False))
        error_code = int(data.get("error_code", 0) or 0)

        with self.lock:
            obs = self.agvs[agv_id]
            now = time.time()
            if obs.current_tag != tag:
                obs.prev_tag = obs.current_tag
                obs.current_tag = tag
                obs.last_change_ts = now
            obs.driving = driving
            obs.error_code = error_code
            obs.last_update_ts = now

            if error_code != 0:
                self._write_violation("ERROR_CODE", agv_id=agv_id, tag=tag, error_code=error_code)
                self._push_map_alert(agv_id, "ERROR_CODE", f"Báo lỗi mã {error_code} tại node {tag}")

            # ── COLLISION: ≥2 xe cùng tag, không phải cả 2 đang driving=False
            # LÂU (đứng yên hợp lệ chờ task) — chỉ coi là va chạm nếu xe vừa
            # ĐẾN tag này trong vài giây gần nhất với 1 xe khác đã có mặt.
            same_tag_others = [oid for oid, o in self.agvs.items()
                                if oid != agv_id and o.current_tag == tag
                                and (now - o.last_update_ts) < 10.0]
            if same_tag_others:
                self._write_violation("COLLISION", agv_ids=[agv_id] + same_tag_others, tag=tag)
                for _aid in [agv_id] + same_tag_others:
                    _other = ", ".join(x for x in ([agv_id] + same_tag_others) if x != _aid)
                    self._push_map_alert(_aid, "COLLISION", f"Va chạm vật lý với {_other} tại node {tag}")

            # ── HEADON_EDGE: xe khác có (current,prev) đảo với (prev,current) của mình
            for oid, o in self.agvs.items():
                if oid == agv_id or o.current_tag is None or obs.prev_tag is None:
                    continue
                if (now - o.last_update_ts) > 10.0:
                    continue
                if o.current_tag == obs.prev_tag and o.prev_tag == obs.current_tag \
                        and obs.current_tag != obs.prev_tag:
                    edge = f"{obs.prev_tag}_{obs.current_tag}"
                    self._write_violation("HEADON_EDGE", agv_ids=[agv_id, oid], edge=edge)
                    self._push_map_alert(agv_id, "HEADON_EDGE", f"Đối đầu với {oid} trên cạnh {edge}")
                    self._push_map_alert(oid, "HEADON_EDGE", f"Đối đầu với {agv_id} trên cạnh {edge}")

    def _fetch_busy_agvs(self) -> set[str] | None:
        """Tập xe đang CÓ tác vụ (đang chạy lệnh hoặc còn lệnh trong hàng đợi) theo server
        mô phỏng. None nếu không hỏi được — khi đó bỏ qua lượt kiểm tra kẹt, không đoán mò."""
        if not self.api_base:
            return None
        try:
            r = requests.get(f"{self.api_base}/api/execute/agv-list", timeout=3)
            return {a["agv_id"] for a in r.json().get("agvs", [])
                    if a.get("is_busy") or (a.get("queue_size") or 0) > 0}
        except Exception:
            return None

    def _stall_watchdog(self, stop_event: threading.Event) -> None:
        """STALL = xe CÓ tác vụ nhưng không đổi node quá stall_timeout. Xe đang đỗ rảnh
        (chờ lệnh ở chỗ chờ/trạm sạc) KHÔNG phải kẹt nên không được tính."""
        while not stop_event.is_set():
            time.sleep(10)
            busy = self._fetch_busy_agvs()
            if busy is None:
                continue
            now = time.time()
            with self.lock:
                for agv_id, obs in self.agvs.items():
                    if obs.current_tag is None:
                        continue
                    if agv_id not in busy:
                        obs.busy_since = None
                        continue
                    if obs.busy_since is None:
                        obs.busy_since = now
                    idle = now - max(obs.last_change_ts, obs.busy_since)
                    if idle > self.stall_timeout:
                        self._write_violation("STALL", agv_id=agv_id, tag=obs.current_tag,
                                               idle_sec=round(idle, 1))
                        obs.last_change_ts = now   # tránh spam lặp lại mỗi 10s
                        obs.busy_since = now

    def _refresh_no_reverse(self) -> None:
        """Nạp (định kỳ) tập xe KHÔNG lùi được từ agv-list của server mô phỏng."""
        now = time.time()
        if not self.api_base or now - self._no_reverse_ts < NO_REVERSE_REFRESH_SEC:
            return
        self._no_reverse_ts = now
        try:
            r = requests.get(f"{self.api_base}/api/execute/agv-list", timeout=3)
            self._no_reverse = {a["agv_id"] for a in r.json().get("agvs", [])
                                if a.get("can_reverse") is False}
        except Exception:
            pass

    def _track_reverse(self, line: str) -> None:
        """Ghi REVERSE_FORBIDDEN khi server lập plan có bước LÙI cho xe không lùi được."""
        m = _REVERSE_RE.search(line)
        if not m:
            return
        self._refresh_no_reverse()
        agv_id = m.group(1)
        if agv_id not in self._no_reverse:
            return
        now = time.time()
        with self.lock:
            if now - self._reverse_last.get(agv_id, 0.0) > REVERSE_VIOLATION_GAP_SEC:
                self._write_violation("REVERSE_FORBIDDEN", agv_id=agv_id,
                                      detail="xe không lùi được (can_reverse=false) bị lập plan có bước lùi")
            self._reverse_last[agv_id] = now

    def _track_junction(self, line: str) -> None:
        """Đếm SỐ LẦN xe gặp nhau tại ngã tư và số lần kẹt ≥ 5 phút ở đó. Server in lại dòng
        mỗi lần xe tự kiểm tra lại (liên tục khi đang chờ) nên phải gộp theo khoảng cách thời
        gian, không đếm từng dòng."""
        m = _JUNCTION_RE.search(line)
        if not m:
            return
        waiter, node, owner = m.groups()
        now = time.time()
        with self.lock:
            k = (waiter, node, owner)
            if now - self._jx_meet.get(k, 0.0) > JUNCTION_MEET_GAP_SEC:
                self._write_violation("JUNCTION_MEET", agv_ids=[waiter, owner], tag=node)
            self._jx_meet[k] = now
            w = self._jx_wait.get((waiter, node))
            if w is None or now - w["last"] > JUNCTION_STUCK_GAP_SEC:
                w = {"start": now, "last": now, "flagged": False}
                self._jx_wait[(waiter, node)] = w
            w["last"] = now
            if not w["flagged"] and now - w["start"] >= JUNCTION_STUCK_SEC:
                w["flagged"] = True
                self._write_violation("JUNCTION_STUCK", agv_ids=[waiter, owner], tag=node,
                                      idle_sec=round(now - w["start"]))

    def _server_log_watchdog(self, stop_event: threading.Event) -> None:
        if not self.server_log_path:
            return
        while not os.path.exists(self.server_log_path) and not stop_event.is_set():
            time.sleep(1)
        if stop_event.is_set():
            return
        with open(self.server_log_path, "r", encoding="utf-8", errors="replace") as f:
            f.seek(0, os.SEEK_END)
            while not stop_event.is_set():
                line = f.readline()
                if not line:
                    time.sleep(0.5)
                    continue
                self._track_junction(line)
                self._track_reverse(line)
                if line.startswith("[TYPE_DIR]"):     # server báo route đi ngược hướng riêng theo loại xe
                    self._write_violation("TYPE_DIR_VIOLATION", line=line.rstrip()[:400])
                if "Traceback" in line or "Exception" in line:
                    self._write_violation("SERVER_EXCEPTION", line=line.rstrip())

    def write_summary(self, summary_path: str) -> None:
        duration = time.time() - self.start_ts
        worst = sorted(self.worst_agv.items(), key=lambda kv: -kv[1])[:5]
        summary = {
            "duration_sec": round(duration, 1),
            "agv_count": len(self.agvs),
            "violation_counts": dict(self.counts),
            "total_violations": sum(self.counts.values()),
            "most_affected_agvs": worst,
        }
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        print(f"[SUMMARY] {json.dumps(summary, ensure_ascii=False)}")
        print(f"[SUMMARY] đã ghi {summary_path}")

    def run(self, duration_hours: float, summary_path: str) -> None:
        self.client.connect(self.broker, self.port, keepalive=30)
        self.client.loop_start()

        stop_event = threading.Event()
        threading.Thread(target=self._stall_watchdog, args=(stop_event,), daemon=True).start()
        threading.Thread(target=self._server_log_watchdog, args=(stop_event,), daemon=True).start()

        deadline = time.time() + duration_hours * 3600 if duration_hours > 0 else None

        def _handle_sigint(signum, frame):
            raise KeyboardInterrupt

        signal.signal(signal.SIGINT, _handle_sigint)
        try:
            while True:
                if deadline and time.time() >= deadline:
                    break
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            stop_event.set()
            self.client.loop_stop()
            self.write_summary(summary_path)
            self._vf.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--broker", default=os.getenv("MQTT_BROKER", "localhost"))
    ap.add_argument("--port", type=int, default=int(os.getenv("MQTT_PORT", "1884")))
    ap.add_argument("--factory", default="SimFactory")
    ap.add_argument("--stall-timeout", type=float, default=120.0)
    ap.add_argument("--duration-hours", type=float, default=0.0)
    ap.add_argument("--server-log", default=None,
                     help="Đường dẫn stdout log của main.py mô phỏng, để bắt Traceback")
    ap.add_argument("--api-base", default=None,
                     help="http://localhost:<api_port> của server mô phỏng — để đẩy vi phạm "
                          "(COLLISION/HEADON_EDGE/ERROR_CODE) lên map NGAY qua marker đỏ. "
                          "Không truyền → vẫn ghi log/jsonl như cũ, chỉ không hiện lên map.")
    ap.add_argument("--log-dir", default=os.path.join(os.path.dirname(__file__), "logs"))
    ap.add_argument("--violations-path", default=None,
                     help="Đường dẫn CỐ ĐỊNH ghi violations (thay vì tự đặt tên theo timestamp) "
                          "— dùng khi run_simulation.py cần biết trước đường dẫn này để truyền "
                          "cho sim_task_gen.py --violations-path (chế độ --scenario)")
    args = ap.parse_args()

    os.makedirs(args.log_dir, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    violations_path = args.violations_path or os.path.join(args.log_dir, f"violations_{ts}.jsonl")
    summary_path = os.path.join(args.log_dir, f"summary_{ts}.json")

    monitor = SimMonitor(args.broker, args.port, args.factory, violations_path,
                          args.stall_timeout, args.server_log, args.api_base)
    print(f"[MONITOR] ghi vi phạm vào {violations_path}")
    monitor.run(args.duration_hours, summary_path)


if __name__ == "__main__":
    main()
