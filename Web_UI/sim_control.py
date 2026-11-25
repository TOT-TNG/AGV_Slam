"""
sim_control.py — Lớp mỏng điều khiển mô phỏng fleet (mqtt_Server/simulation/)
từ Web_UI (tiến trình Dash, port 8050).

Mô phỏng chạy server riêng ở 1 PORT KHÁC (--api-port, mặc định 8001) với
server sản xuất thật (luôn 8000) — nên chạy SONG SONG được, KHÔNG cần/được
đụng tới server/service sản xuất. KHÔNG viết lại logic orchestrate — chỉ
spawn/theo dõi/dừng đúng 1 tiến trình `run_simulation.py` (đã có sẵn, đã
kiểm chứng) và đọc TRỰC TIẾP các file log nó ghi ra để trả về trạng thái cho
trang web.

AN TOÀN (đã chốt với người dùng): port API mô phỏng KHÔNG được là 8000 (chặn
cứng, dù người dùng vô tình nhập) — nhưng KHÔNG cần/không còn kiểm tra port
8000 có bị chiếm hay không, vì mô phỏng không bao giờ đụng tới nó. Mosquitto
cho mô phỏng cũng KHÔNG tự quản lý — chỉ để run_simulation.py tự kiểm tra +
báo lỗi như hành vi gốc. Xe ảo KHÔNG bao giờ được ghi vào DB thật/dùng chung
TrafficCoordinator với xe thật — vẫn 1 DB/process riêng hoàn toàn.
"""
from __future__ import annotations

import glob
import json
import os
import socket
import subprocess
import sys
import time

from flask import Flask, jsonify, request

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
SIMULATION_DIR = os.path.join(_ROOT, "mqtt_Server", "simulation")
LOGS_DIR = os.path.join(SIMULATION_DIR, "logs")

PROD_API_PORT = 8000   # mqtt_Server/main.py thật — mô phỏng KHÔNG được dùng port này
MIN_AGV_COUNT, MAX_AGV_COUNT = 1, 50
VALID_AGV_TYPES = {"tow", "trailer", "carry", "mixed"}
# Các loại xe dùng trong "agv_mix" (số lượng từng loại chạy cùng lúc) — khớp MIX_KINDS trong
# mqtt_Server/simulation/setup_sim_db.py
VALID_MIX_KINDS = ("tow", "tow_hook", "tow_hook_drop", "tow_fixed", "trailer", "carry")

PG_HOST = os.environ.get("PGHOST", "localhost")
PG_PORT = os.environ.get("PGPORT", "5432")
PG_USER = os.environ.get("PGUSER", "postgres")
PG_PASS = os.environ.get("PGPASSWORD", "ducmanh1801")
SIM_DBNAME = "TOT_AGV_SIM"
PROD_DBNAME = os.environ.get("PGDATABASE_PROD", "TOT_AGV")
START_NODE_RE = None   # khởi tạo lười bên dưới (tránh import re ở đầu file)


def _pg(dbname: str):
    import psycopg2
    return psycopg2.connect(host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASS,
                            dbname=dbname, connect_timeout=3)


_STATE: dict = {"proc": None, "params": None, "started_at": None, "launcher_log": None,
                "stopped_by_user": False}


def _port_reachable(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _newest_matching(pattern: str, not_before: float) -> str | None:
    """File khớp `pattern` có mtime mới nhất, loại các file CŨ hơn lần chạy
    hiện tại (not_before) — tránh nhầm sang file của 1 lần chạy CLI trước."""
    candidates = [f for f in glob.glob(pattern) if os.path.getmtime(f) >= not_before - 5]
    if not candidates:
        return None
    return max(candidates, key=os.path.getmtime)


STALL_MIN_SEC = 300.0        # chỉ tính "kẹt" khi 1 xe đứng yên ≥ 5 phút liên tục
COLLISION_GAP_SEC = 30.0     # 2 bản ghi va chạm cùng cặp xe/node cách nhau > 30s = lần va chạm MỚI
STALL_GAP_SEC = 240.0        # sim_monitor ghi STALL mỗi ~130s/xe; cách nhau > 240s = đã hết kẹt


def _read_violations(violations_path: str) -> dict:
    """Gộp các bản ghi thô (sim_monitor ghi lặp lại mỗi lần poll) thành SỐ LẦN sự cố:
    va chạm (cùng cặp xe + node, liên tục = 1 lần) và kẹt ≥ 5 phút (cùng xe + node)."""
    collisions: list[dict] = []
    stalls: dict[tuple, list[dict]] = {}
    last_col: dict[tuple, dict] = {}
    jx_meet = 0
    jx_stuck: list[dict] = []
    if violations_path and os.path.exists(violations_path):
        with open(violations_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                kind, ts = rec.get("kind"), float(rec.get("ts") or 0)
                if kind == "COLLISION":
                    key = (tuple(sorted(rec.get("agv_ids") or [])), rec.get("tag"))
                    cur = last_col.get(key)
                    if cur is None or ts - cur["last_ts"] > COLLISION_GAP_SEC:
                        cur = {"ts": ts, "last_ts": ts, "kind": "COLLISION",
                               "agv_ids": list(key[0]), "tag": key[1]}
                        collisions.append(cur)
                        last_col[key] = cur
                    cur["last_ts"] = ts
                elif kind == "JUNCTION_MEET":
                    jx_meet += 1
                elif kind == "JUNCTION_STUCK":
                    jx_stuck.append({"ts": ts, "kind": kind, "agv_ids": rec.get("agv_ids") or [],
                                     "tag": rec.get("tag"), "idle_sec": rec.get("idle_sec")})
                elif kind == "STALL" and rec.get("agv_id"):
                    stalls.setdefault((rec["agv_id"], rec.get("tag")), []).append(rec)

    stall_incidents: list[dict] = []
    for (aid, tag), recs in stalls.items():
        recs.sort(key=lambda r: r.get("ts") or 0)
        run = [recs[0]]
        for r in recs[1:] + [None]:
            if r is not None and (r["ts"] - run[-1]["ts"]) <= STALL_GAP_SEC:
                run.append(r)
                continue
            dur = (run[-1]["ts"] - run[0]["ts"]) + float(run[0].get("idle_sec") or 0)
            if dur >= STALL_MIN_SEC:
                stall_incidents.append({"ts": run[-1]["ts"], "kind": "STALL", "agv_ids": [aid],
                                        "tag": tag, "idle_sec": round(dur)})
            if r is not None:
                run = [r]

    incidents = collisions + stall_incidents + jx_stuck
    affected: dict[str, int] = {}
    for inc in incidents:
        for aid in inc["agv_ids"]:
            affected[aid] = affected.get(aid, 0) + 1
    for inc in collisions:
        inc.pop("last_ts", None)
    recent = sorted(incidents, key=lambda i: -i["ts"])[:30]
    counts = {}
    if collisions:
        counts["COLLISION"] = len(collisions)
    if jx_stuck:
        counts["JUNCTION_STUCK"] = len(jx_stuck)
    if stall_incidents:
        counts["STALL"] = len(stall_incidents)
    return {
        "violation_counts": counts,
        "collision_count": len(collisions),
        "stall_count": len(stall_incidents),
        "junction_meet_count": jx_meet,
        "junction_stuck_count": len(jx_stuck),
        "total_violations": len(incidents),
        "most_affected_agvs": sorted(affected.items(), key=lambda kv: -kv[1])[:5],
        "recent_violations": recent,
    }


def _tail_lines(path: str, n: int) -> list[str]:
    if not path or not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return [ln.rstrip("\n") for ln in f.readlines()[-n:]]
    except OSError:
        return []


def register_routes(server: Flask) -> None:
    @server.route("/sim-control/start", methods=["POST"])
    def sim_control_start():
        proc = _STATE.get("proc")
        if proc is not None and proc.poll() is None:
            return jsonify({"ok": False, "error": "Mô phỏng đang chạy rồi — dừng trước khi bắt đầu lại."}), 409

        body = request.get_json(silent=True) or {}
        try:
            agv_count = int(body.get("agv_count", 15))
            duration_hours = float(body.get("duration_hours", 0))
            mqtt_port = int(body.get("mqtt_port", 1884))
            api_port = int(body.get("api_port", 8001))
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "Tham số không hợp lệ."}), 400

        map_id = str(body.get("map_id") or "").strip()
        agv_type = str(body.get("agv_type") or "tow").strip()
        mode = str(body.get("mode") or "natural").strip()
        if mode not in ("natural", "manual"):
            return jsonify({"ok": False, "error": "Chế độ mô phỏng không hợp lệ (natural hoặc manual)."}), 400

        # Trộn nhiều loại xe: {"tow": 6, "trailer": 4, ...} — có thì tổng số xe = tổng số lượng
        agv_mix = body.get("agv_mix") or {}
        mix_arg = ""
        if agv_mix:
            if not isinstance(agv_mix, dict):
                return jsonify({"ok": False, "error": "agv_mix không hợp lệ."}), 400
            parts = []
            for k, v in agv_mix.items():
                if k not in VALID_MIX_KINDS:
                    return jsonify({"ok": False, "error": f"Loại xe '{k}' không hợp lệ trong hỗn hợp."}), 400
                try:
                    n = int(v)
                except (TypeError, ValueError):
                    return jsonify({"ok": False, "error": f"Số lượng '{k}' không hợp lệ."}), 400
                if n < 0:
                    return jsonify({"ok": False, "error": f"Số lượng '{k}' phải >= 0."}), 400
                if n:
                    parts.append(f"{k}={n}")
            if parts:
                mix_arg = ",".join(parts)
                agv_count = sum(int(v) for v in agv_mix.values() if int(v) > 0)
            else:
                agv_mix = {}

        # Vị trí xuất phát theo loại xe: {"tow": "221,222", "trailer": "224", "carry": ""}
        import re as _re
        start_nodes = body.get("start_nodes") or {}
        start_arg_parts = []
        if not isinstance(start_nodes, dict):
            return jsonify({"ok": False, "error": "start_nodes không hợp lệ."}), 400
        clean_start_nodes = {}
        for k, v in start_nodes.items():
            if k not in ("tow", "trailer", "carry"):
                return jsonify({"ok": False, "error": f"Loại xe '{k}' không hợp lệ ở vị trí xuất phát."}), 400
            nodes = [n.strip() for n in str(v or "").replace(";", ",").split(",") if n.strip()]
            for n in nodes:
                if not _re.fullmatch(r"[A-Za-z0-9_\-]+", n):
                    return jsonify({"ok": False, "error": f"Node xuất phát '{n}' không hợp lệ."}), 400
            if nodes:
                clean_start_nodes[k] = ",".join(nodes)
                start_arg_parts.append(f"{k}={','.join(nodes)}")
        start_arg = ";".join(start_arg_parts)

        if not (MIN_AGV_COUNT <= agv_count <= MAX_AGV_COUNT):
            return jsonify({"ok": False, "error": f"Số xe phải trong khoảng {MIN_AGV_COUNT}-{MAX_AGV_COUNT}."}), 400
        if duration_hours < 0:
            return jsonify({"ok": False, "error": "Thời gian chạy không hợp lệ."}), 400
        if mqtt_port == 1883:
            return jsonify({"ok": False, "error": "Port MQTT mô phỏng không được dùng 1883 (port broker sản xuất)."}), 400
        if api_port == PROD_API_PORT:
            return jsonify({"ok": False, "error": f"Port API mô phỏng không được dùng {PROD_API_PORT} (port server sản xuất)."}), 400
        if not map_id:
            return jsonify({"ok": False, "error": "Vui lòng chọn bản đồ để mô phỏng."}), 400
        if agv_type not in VALID_AGV_TYPES:
            return jsonify({"ok": False, "error": f"Loại xe không hợp lệ (phải là {', '.join(sorted(VALID_AGV_TYPES))})."}), 400

        if _port_reachable("localhost", api_port):
            return jsonify({
                "ok": False,
                "error": f"Cổng {api_port} đang bị tiến trình khác chiếm — chọn port API "
                         f"mô phỏng khác hoặc dừng tiến trình đó trước.",
            }), 409

        os.makedirs(LOGS_DIR, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        launcher_log = os.path.join(LOGS_DIR, f"launcher_{ts}.log")
        log_f = open(launcher_log, "w", encoding="utf-8")

        started_at = time.time()
        proc = subprocess.Popen(
            [sys.executable, "run_simulation.py",
             "--agv-count", str(agv_count),
             "--duration-hours", str(duration_hours),
             "--mqtt-port", str(mqtt_port),
             "--api-port", str(api_port),
             "--map-id", map_id,
             "--agv-type", agv_type,
             "--agv-mix", mix_arg,
             "--start-nodes", start_arg,
             "--mode", mode],
            cwd=SIMULATION_DIR, stdout=log_f, stderr=subprocess.STDOUT,
        )
        _STATE.update({
            "proc": proc,
            "params": {"agv_count": agv_count, "duration_hours": duration_hours,
                       "mqtt_port": mqtt_port, "api_port": api_port,
                       "map_id": map_id, "agv_type": agv_type, "mode": mode,
                       "agv_mix": {k: int(v) for k, v in agv_mix.items() if int(v) > 0},
                       "start_nodes": clean_start_nodes},
            "started_at": started_at,
            "launcher_log": launcher_log,
            "stopped_by_user": False,
        })
        return jsonify({"ok": True})

    @server.route("/sim-control/stop", methods=["POST"])
    def sim_control_stop():
        proc = _STATE.get("proc")
        if proc is None or proc.poll() is not None:
            return jsonify({"ok": False, "error": "Không có mô phỏng nào đang chạy."}), 400
        # Giết cả CÂY tiến trình (run_simulation.py đẻ ra main.py mô phỏng/sim_fleet/
        # sim_task_gen/sim_monitor) — proc.terminate() không đủ, cùng gotcha uvicorn
        # reload=True orphan đã gặp và sửa trong run_simulation.py._stop_all().
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # PHÁT HIỆN THỰC TẾ (2026-10-06): taskkill buộc tiến trình thoát với exit
        # code KHÁC 0 (bị giết, không tự thoát sạch) — nếu không đánh dấu riêng,
        # /sim-control/status sẽ đọc rc≠0 và báo "error" (như thật sự bị lỗi) dù
        # đây là NGƯỜI DÙNG tự bấm Dừng, không phải lỗi gì cả.
        _STATE["stopped_by_user"] = True
        return jsonify({"ok": True})

    @server.route("/sim-control/fleet", methods=["GET"])
    def sim_control_fleet():
        """Danh sách xe mô phỏng hiện có trong DB mô phỏng: loại xe, chế độ vận hành, vị trí xuất phát."""
        try:
            conn = _pg(SIM_DBNAME)
            try:
                cur = conn.cursor()
                cur.execute("SELECT name, agv_type, COALESCE(op_mode,'roundtrip'), COALESCE(return_mode,'charge'), "
                            "sim_start_node FROM agv_devices WHERE name LIKE 'SIM%%' ORDER BY name")
                rows = cur.fetchall()
            finally:
                conn.close()
        except Exception as e:
            return jsonify({"ok": False, "error": str(e), "agvs": []})
        return jsonify({"ok": True, "agvs": [
            {"name": r[0], "agv_type": r[1], "op_mode": r[2], "return_mode": r[3], "start_node": r[4]}
            for r in rows]})

    @server.route("/sim-control/start-candidates", methods=["GET"])
    def sim_control_start_candidates():
        """Gợi ý vị trí xuất phát: trạm sạc + node chờ của map đã chọn (đọc DB thật, chỉ đọc),
        kèm loại xe được phép (station_agv_type / allowed_agv_types)."""
        map_id = str(request.args.get("map_id") or "").strip()
        if not map_id:
            return jsonify({"ok": False, "error": "thiếu map_id", "nodes": []})
        try:
            conn = _pg(PROD_DBNAME)
            try:
                cur = conn.cursor()
                cur.execute("SELECT name_id, action FROM agv_map_points WHERE map_id=%s", (map_id,))
                rows = cur.fetchall()
            finally:
                conn.close()
        except Exception as e:
            return jsonify({"ok": False, "error": str(e), "nodes": []})
        out = []
        for nid, act in rows:
            if isinstance(act, str):
                try:
                    act = json.loads(act)
                except ValueError:
                    act = {}
            act = act if isinstance(act, dict) else {}
            kind = ("charger" if act.get("locationType") == "CHARGER"
                    else "waiting" if act.get("waiting_node") == "yes" else None)
            if not kind:
                continue
            allowed = act.get("allowed_agv_types") or []
            if isinstance(allowed, str):
                allowed = [a.strip() for a in allowed.split(",") if a.strip()]
            out.append({"node": str(nid), "kind": kind,
                        "station_agv_type": str(act.get("station_agv_type") or ""),
                        "allowed": allowed})
        out.sort(key=lambda x: (x["kind"] != "charger", int(x["node"]) if x["node"].isdigit() else 10**9, x["node"]))
        return jsonify({"ok": True, "nodes": out})

    @server.route("/sim-control/status", methods=["GET"])
    def sim_control_status():
        proc = _STATE.get("proc")
        started_at = _STATE.get("started_at")

        if proc is None:
            return jsonify({"state": "idle", "params": None, "elapsed_sec": None,
                             "violation_counts": {}, "total_violations": 0,
                             "most_affected_agvs": [], "recent_violations": [],
                             "summary": None, "error_log": None})

        rc = proc.poll()
        if rc is None:
            state = "running"
        elif rc == 0 or _STATE.get("stopped_by_user"):
            # rc==0: tự thoát sạch (hết --duration-hours). stopped_by_user: bị
            # taskkill do NGƯỜI DÙNG bấm Dừng (rc gần như luôn ≠0 khi bị giết
            # cứng) — CẢ HAI đều là "đã dừng bình thường", không phải lỗi.
            state = "finished"
        else:
            state = "error"
        elapsed = (time.time() - started_at) if started_at else None

        sim_ready = False
        if state == "running":
            params = _STATE.get("params") or {}
            api_port = params.get("api_port")
            if api_port:
                sim_ready = _port_reachable("localhost", api_port, timeout=0.5)

        violations_path = _newest_matching(os.path.join(LOGS_DIR, "violations_*.jsonl"), started_at)
        summary_path = _newest_matching(os.path.join(LOGS_DIR, "summary_*.json"), started_at)

        result = {"state": state, "params": _STATE.get("params"), "elapsed_sec": elapsed,
                  "sim_ready": sim_ready}
        result.update(_read_violations(violations_path))

        summary = None
        if summary_path and state != "running":
            try:
                with open(summary_path, "r", encoding="utf-8") as f:
                    summary = json.load(f)
            except (OSError, json.JSONDecodeError):
                summary = None
        result["summary"] = summary

        result["error_log"] = "\n".join(_tail_lines(_STATE.get("launcher_log"), 20)) if state == "error" else None
        return jsonify(result)
