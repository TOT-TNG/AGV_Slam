"""
sim_task_gen.py — Giữ fleet mô phỏng luôn bận + tự xác nhận móc, để chạy được
NHIỀU GIỜ không cần người bấm nút, bằng cách gọi ĐÚNG 2 REST API thật mà
main.py đã có sẵn (không có API mới nào được thêm cho mô phỏng):

  GET  /api/execute/agv-list          — đọc is_busy/queue_size/hook_pending/driving
  POST /api/tasks                     — tạo tác vụ {agv_id, destination}
  POST /api/execute/hook-confirm      — tự xác nhận móc khi AGV đang chờ "pickup"
  POST /api/execute/lifecycle-ack     — tự xác nhận "Đã lấy/giao hàng" khi
                                         task_lifecycle là "picking"/"delivering"
                                         (bước THỦ CÔNG riêng, khác hook-confirm —
                                         xem line_agv_handler._handle_trailer_hook_arrival/
                                         main.py lifecycle_ack; thiếu bước này khiến xe
                                         đứng im vĩnh viễn sau khi móc xong, vì không ai
                                         bấm "Đã lấy hàng" trong mô phỏng)

Chạy nhắm vào main.py MÔ PHỎNG (đang chĩa DATABASE_URL/PG*/MQTT_PORT vào DB+broker
riêng) — không đụng gì tới AGV thật.

MỚI — chế độ KỊCH BẢN (--scenario <file.json>): thay cho sinh tác vụ ngẫu nhiên,
đọc 1 file JSON VIẾT TAY định sẵn mỗi xe đi đâu/lúc nào + "expectations" (không
va chạm, tới đích trong bao lâu...), để biết TRƯỚC xe nào phải đi đâu mà so sánh
với log/bản đồ thực tế — thay vì chạy ngẫu nhiên không biết trước kỳ vọng gì.
Xem simulation/scenarios/example_same_destination.json làm mẫu định dạng. Khi
dùng --scenario: chạy tới khi TẤT CẢ xe trong kịch bản hoàn tất route (hoặc hết
--timeout-s khai trong file), rồi tự đọc file vi phạm do sim_monitor.py ghi
(--violations-path) để so khớp "expectations", in + ghi báo cáo PASS/FAIL, rồi
THOÁT hẳn (không lặp vô hạn như chế độ ngẫu nhiên).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys
import time
import uuid

import psycopg2
import requests

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


def load_sim_nodes_and_agvs(db_url: str, factory: str) -> tuple[list[str], list[str]]:
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    cur.execute("SELECT name FROM agv_devices WHERE factory=%s ORDER BY name", (factory,))
    agv_ids = [r[0] for r in cur.fetchall()]
    cur.execute("SELECT DISTINCT map_id FROM agv_devices WHERE factory=%s LIMIT 1", (factory,))
    map_id = cur.fetchone()[0]
    cur.execute("SELECT name_id FROM agv_map_points WHERE map_id=%s", (map_id,))
    nodes = [r[0] for r in cur.fetchall()]
    conn.close()
    return agv_ids, nodes


def load_dropoff_nodes(db_url: str, factory: str) -> set[str]:
    """Node thả hàng thật (locationType=DROPOFF có gán tổ/team) — đích của tác vụ giao hàng.
    Giao ngẫu nhiên tới MỌI node (cả node thường) khiến xe chạy lòng vòng, không giống vận hành thật."""
    try:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT map_id FROM agv_devices WHERE factory=%s LIMIT 1", (factory,))
        map_id = cur.fetchone()[0]
        cur.execute("SELECT name_id FROM agv_map_points WHERE map_id=%s "
                    "AND action->>'locationType'='DROPOFF' AND COALESCE(action->>'team','')<>''", (map_id,))
        out = {str(r[0]) for r in cur.fetchall()}
        conn.close()
        return out
    except Exception:
        return set()


def load_zone_info(db_url: str, factory: str):
    """Đọc từ DB mô phỏng: loại từng xe, loại xe được phép của từng node (vùng hoạt động) và đồ thị
    đường đi — để sinh đích hợp lệ: xe chỉ được giao node nó được phép vào VÀ đi tới được từ vị trí
    hiện tại (cùng thành phần liên thông trong vùng của loại xe đó). Lỗi → trả None (giao ngẫu nhiên)."""
    try:
        import networkx as nx
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        cur.execute("SELECT name, agv_type, COALESCE(can_reverse, TRUE) FROM agv_devices WHERE factory=%s",
                    (factory,))
        _rows = cur.fetchall()
        agv_types = {r[0]: str(r[1] or "").strip().lower() for r in _rows}
        no_reverse = {r[0] for r in _rows if not r[2]}
        cur.execute("SELECT DISTINCT map_id FROM agv_devices WHERE factory=%s LIMIT 1", (factory,))
        map_id = cur.fetchone()[0]
        cur.execute("SELECT name_id, action FROM agv_map_points WHERE map_id=%s", (map_id,))
        allowed: dict = {}
        elev: dict = {}      # mã thang → các node cabin của thang đó (mỗi tầng 1 node) — nối các tầng với nhau
        for nid, act in cur.fetchall():
            if isinstance(act, str):
                try:
                    act = json.loads(act)
                except ValueError:
                    act = {}
            _eid = str((act or {}).get("elevator_id") or "").strip()
            if _eid:
                elev.setdefault(_eid, []).append(str(nid))
            lst = (act or {}).get("allowed_agv_types") or []
            if isinstance(lst, str):
                lst = lst.split(",")
            allowed[str(nid)] = [str(t).strip().lower() for t in lst if str(t).strip()]
        g = nx.Graph()
        g.add_nodes_from(allowed)
        # Cạnh có chiều RIÊNG theo loại xe (type_directions): lưu danh sách (src, dst, {type: dir})
        tdirs: list = []
        for tbl in ("agv_map_roads", "agv_map_benziers"):
            cur.execute("SELECT 1 FROM information_schema.columns WHERE table_name=%s "
                        "AND column_name='type_directions'", (tbl,))
            col = "type_directions" if cur.fetchone() else "NULL"
            cur.execute(f"SELECT id_source, id_dest, {col} FROM {tbl} WHERE map_id=%s", (map_id,))
            for a, b, td in cur.fetchall():
                g.add_edge(str(a), str(b))
                try:
                    d = json.loads(td) if isinstance(td, str) and td else (td or {})
                except ValueError:
                    d = {}
                tdirs.append((str(a), str(b), d if isinstance(d, dict) else {}))
        conn.close()
        return agv_types, allowed, g, no_reverse, tdirs, elev
    except Exception:
        return None


def reachable_destinations(zone, agv_id: str, current_node, all_nodes: list[str]) -> list[str]:
    """Các node xe `agv_id` được phép vào và đi tới được từ `current_node`. Không có dữ liệu vùng
    (zone=None) hoặc không biết vị trí → trả toàn bộ node như trước."""
    if not zone or current_node is None:
        return all_nodes
    import networkx as nx
    agv_types, allowed, g, no_reverse, tdirs, elev = zone
    t = agv_types.get(agv_id, "")
    ok = [n for n in g.nodes if (not allowed.get(n)) or t in allowed[n]]
    sub = g.subgraph(ok)
    cur = str(current_node)
    if cur not in sub:
        return all_nodes
    # Đồ thị CÓ HƯỚNG theo loại xe: cạnh thường 2 chiều, trừ khi type_directions hạn chế loại này
    dg = nx.DiGraph()
    dg.add_nodes_from(sub.nodes)
    for a, b, d in tdirs:
        if a not in sub or b not in sub:
            continue
        v = str(d.get(t, "")).lower()
        if v != "backward" and v != "blocked":
            dg.add_edge(a, b)
        if v != "forward" and v != "blocked":
            dg.add_edge(b, a)
    # Thang máy nối các tầng: xe LÙI ĐƯỢC đi sang tầng khác qua thang (cabin 1 cửa — vào tiến ra lùi); xe không lùi
    # được (rơ-moóc) bị server từ chối đi thang nên vẫn chỉ ở tầng của mình. Node cabin không bao giờ là đích.
    cabin_nodes = {n for ns in elev.values() for n in ns}
    if agv_id not in no_reverse:
        for ns_all in elev.values():
            ns_ok = [n for n in ns_all if n in sub]
            for a in ns_ok:
                for b in ns_ok:
                    if a != b:
                        dg.add_edge(a, b)
    reach = nx.descendants(dg, cur) if cur in dg else set()
    cand = [n for n in all_nodes if str(n) in reach and str(n) != cur and str(n) not in cabin_nodes]
    if agv_id in no_reverse:
        # Xe KHÔNG lùi được: phân tích theo TRẠNG THÁI (cạnh vừa đi u→v). Từ trạng thái (u→v) xe chỉ
        # được đi tiếp v→w với w != u (không quay đầu). Trạng thái "chết" = mọi đường tiếp theo đều dẫn
        # tới ngõ cụt không lối ra (vd hành lang 22-21-20-19-18 khi các cạnh ra khỏi nó bị cấm một chiều).
        # Ngõ cụt thật (bậc 1, trạm sạc/nhánh cụt) đã có kịch bản riêng (lùi mù + quay / quay đầu qua
        # trạm sạc) nên coi là lối thoát. Chỉ giao đích mà MỌI cách tới nó (từ vị trí hiện tại) đều "sống".
        def _succ(st):
            u, v = st
            return [(v, w) for w in dg.successors(v) if w != u]

        terminal = {n for n in sub.nodes if sub.degree(n) <= 1}
        states = list(dg.edges)
        dead = set()
        changed = True
        while changed:
            changed = False
            for st in states:
                if st in dead or st[1] in terminal:
                    continue
                if all(t in dead for t in _succ(st)):     # gồm cả trường hợp không có lối tiếp
                    dead.add(st)
                    changed = True
        if cur in terminal:     # đang ở ngõ cụt/trạm sạc: xe ra bằng kịch bản quay đầu → có thể đi mọi hướng
            start = [(cur, w) for w in dg.successors(cur)] if cur in dg else []
        else:
            start = [(pp, cur) for pp in dg.predecessors(cur)] if cur in dg else []
        seen = set(start)
        stack = list(start)
        while stack:
            for t in _succ(stack.pop()):
                if t not in seen:
                    seen.add(t)
                    stack.append(t)
        bad = {v for (u, v) in seen if (u, v) in dead}
        safe = [n for n in cand if str(n) not in bad]
        cand = safe or cand
    return cand or all_nodes


def _handle_hook_and_lifecycle(api_base: str, agv_id: str, row: dict,
                                logger: logging.Logger) -> bool:
    """Tự xác nhận móc/lifecycle nếu xe đang chờ bước thủ công — dùng chung cho
    cả 2 chế độ (ngẫu nhiên và kịch bản). Trả True nếu đã xử lý 1 bước chờ ở
    lượt này (gọi không nên dispatch task mới trong CÙNG lượt poll)."""
    if row.get("hook_pending") == "pickup":
        try:
            r = requests.post(f"{api_base}/api/execute/hook-confirm",
                               json={"agv_id": agv_id}, timeout=5)
            if r.status_code == 200:
                logger.info(f"[HOOK_CONFIRM] {agv_id} ok")
            else:
                logger.info(f"[HOOK_CONFIRM] {agv_id} lỗi {r.status_code}: {r.text}")
        except Exception as e:
            logger.info(f"[WARN] hook-confirm {agv_id} lỗi: {e}")
        return True

    if row.get("task_lifecycle") in ("picking", "delivering"):
        try:
            r = requests.post(f"{api_base}/api/execute/lifecycle-ack/{agv_id}", timeout=5)
            if r.status_code == 200:
                logger.info(f"[LIFECYCLE_ACK] {agv_id} ok ({row.get('task_lifecycle')})")
            else:
                logger.info(f"[LIFECYCLE_ACK] {agv_id} lỗi {r.status_code}: {r.text}")
        except Exception as e:
            logger.info(f"[WARN] lifecycle-ack {agv_id} lỗi: {e}")
        return True

    return False


def _dispatch_task(api_base: str, agv_id: str, dest: str, logger: logging.Logger) -> bool:
    try:
        r = requests.post(f"{api_base}/api/tasks", json={
            "agv_id": agv_id,
            "destination": dest,
            "notes": "sim_task_gen",
        }, timeout=5)
        body = r.json() if r.status_code < 300 else {}
        if r.status_code < 300 and body.get("status") in ("running", "pending"):
            logger.info(f"[TASK] {agv_id} → {dest}")
            return True
        logger.info(f"[TASK] {agv_id} → {dest} lỗi {r.status_code}: "
                    f"{body.get('error') or r.text}")
        return False
    except Exception as e:
        logger.info(f"[WARN] tạo task {agv_id} lỗi: {e}")
        return False


def _dispatch_session_task(api_base: str, agv_id: str, dest: str, logger: logging.Logger) -> bool:
    """Giao hàng ĐÚNG như app thật: POST /api/execute/dispatch kèm session_id (server gom lệnh, chèn bước
    LẤY HÀNG/điểm cấp TRƯỚC rồi mới giao). Khác /api/tasks (1 lệnh go_to trơn): với đích khác tầng, xe đi lấy hàng
    rồi mới đặt thang — nếu thang đang bận thì chờ ngay tại điểm lấy hàng thay vì đứng ở trạm sạc."""
    try:
        r = requests.post(f"{api_base}/api/execute/dispatch", json={
            "agv_id": agv_id, "command": "go_to", "dest_node": dest,
            "session_id": uuid.uuid4().hex, "session_label": "sim_task_gen",
        }, timeout=5)
        body = r.json() if r.status_code < 300 else {}
        if r.status_code < 300 and body.get("status") in ("collecting", "dispatched", "queued"):
            logger.info(f"[TASK] {agv_id} → {dest}")
            return True
        logger.info(f"[TASK] {agv_id} → {dest} lỗi {r.status_code}: {body.get('error') or r.text}")
        return False
    except Exception as e:
        logger.info(f"[WARN] tạo task {agv_id} lỗi: {e}")
        return False


MANUAL_RETURN_AFTER_SEC = 8.0     # chế độ giao lệnh: rảnh chừng này giây thì tự Về trạm
MANUAL_RETURN_RETRY_SEC = 60.0    # chưa vào trạm sạc sau chừng này giây thì gửi lại


def _dispatch_go_charge(api_base: str, agv_id: str, logger: logging.Logger) -> bool:
    """Gọi ĐÚNG API 'Về trạm' thật (POST /api/agv/go-charge) — xe tự chạy hết
    quy trình chuẩn (LOCATE_THEN_CHARGE, chọn trạm sạc ít bị chiếm nhất, hoặc
    tự chuyển sang điểm chờ đã cấu hình + tự retry nếu TẤT CẢ trạm sạc đều có
    xe — xem mqtt_client.send_agv_to_special_target/main.monitor_charge_station_wait),
    y hệt khi người vận hành bấm nút 'Về trạm' cho AGV thật."""
    try:
        r = requests.post(f"{api_base}/api/agv/go-charge", json={"agv_id": agv_id}, timeout=5)
        if r.status_code < 300:
            logger.info(f"[GO_CHARGE] {agv_id} → Về trạm")
            return True
        logger.info(f"[GO_CHARGE] {agv_id} lỗi {r.status_code}: {r.text}")
        return False
    except Exception as e:
        logger.info(f"[WARN] go-charge {agv_id} lỗi: {e}")
        return False


def run_random(args, logger: logging.Logger) -> None:
    """Chế độ CŨ — sinh tác vụ ngẫu nhiên liên tục cho xe đang rỗi, chạy vô hạn
    tới hết --duration-hours hoặc Ctrl+C. KHÔNG đổi hành vi so với trước khi có
    chế độ kịch bản."""
    agv_ids, nodes = load_sim_nodes_and_agvs(args.db_url, args.factory)
    if not agv_ids or not nodes:
        raise SystemExit("Không tìm thấy AGV/node mô phỏng trong DB — chạy setup_sim_db.py trước")
    logger.info(f"[INIT] {len(agv_ids)} xe mô phỏng, {len(nodes)} node — API base={args.api_base}")
    manual = bool(getattr(args, "manual", False))
    if manual:
        logger.info("[INIT] CHẾ ĐỘ GIAO LỆNH: không tự sinh tác vụ — xe chỉ chạy khi có người gửi lệnh "
                    "(vẫn tự xác nhận móc / 'đã lấy-giao hàng' để xe không treo chờ HMI; xong lệnh thì TỰ VỀ TRẠM "
                    f"sau {MANUAL_RETURN_AFTER_SEC:.0f}s, không để xe đứng ở đích chặn đường)")
    idle_since: dict[str, float] = {}     # agv_id -> mốc bắt đầu rảnh (chế độ giao lệnh)
    return_sent: dict[str, float] = {}    # agv_id -> lần cuối gửi 'Về trạm'

    zone = load_zone_info(args.db_url, args.factory)
    dropoffs = load_dropoff_nodes(args.db_url, args.factory)
    if dropoffs:
        logger.info(f"[INIT] đích giao hàng = {len(dropoffs)} node DROPOFF có tổ: {sorted(dropoffs, key=lambda x: (len(x), x))}")
    else:
        logger.info("[INIT] map không có node DROPOFF có tổ → giao tới node bất kỳ như cũ")
    tasks_created = 0
    deadline = time.time() + args.duration_hours * 3600 if args.duration_hours > 0 else None

    while True:
        if deadline and time.time() >= deadline:
            logger.info(f"[DONE] hết --duration-hours — tasks_created={tasks_created}")
            break
        try:
            resp = requests.get(f"{args.api_base}/api/execute/agv-list", timeout=5)
            resp.raise_for_status()
            rows = resp.json().get("agvs", [])
        except Exception as e:
            logger.info(f"[WARN] không gọi được agv-list: {e}")
            time.sleep(args.poll_interval)
            continue

        for row in rows:
            agv_id = row.get("agv_id")
            if agv_id not in agv_ids:
                continue   # bỏ qua AGV thật nếu lỡ cùng DB (không nên xảy ra khi tách biệt đúng)

            if _handle_hook_and_lifecycle(args.api_base, agv_id, row, logger):
                continue

            if manual:
                # Xong lệnh (rảnh, không lifecycle, chưa ở trạm sạc) → tự Về trạm; gửi lại nếu 60s sau vẫn đứng đó.
                idle = (row.get("connection") == "ONLINE" and not row.get("is_busy") and not row.get("driving")
                        and (row.get("queue_size") or 0) == 0 and not row.get("task_lifecycle"))
                _now = time.time()
                if not idle:
                    idle_since.pop(agv_id, None)
                else:
                    idle_since.setdefault(agv_id, _now)
                    if (_now - idle_since[agv_id] >= MANUAL_RETURN_AFTER_SEC
                            and _now - return_sent.get(agv_id, 0.0) >= MANUAL_RETURN_RETRY_SEC):
                        return_sent[agv_id] = _now
                        _dispatch_go_charge(args.api_base, agv_id, logger)
                continue

            is_busy = row.get("is_busy") or row.get("queue_size", 0) > 0
            if is_busy or row.get("driving"):
                continue

            cands = reachable_destinations(zone, agv_id, row.get("current_node"), nodes)
            if dropoffs:
                cands = [n for n in cands if str(n) in dropoffs] or cands
            dest = random.choice(cands)
            if dest == row.get("current_node"):
                continue
            if _dispatch_session_task(args.api_base, agv_id, dest, logger):
                tasks_created += 1

        time.sleep(args.poll_interval)


def _read_violations(path: str | None) -> list[dict]:
    if not path or not os.path.exists(path):
        return []
    out: list[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


def _evaluate_and_report(name: str, expectations: list, state: dict,
                          args, logger: logging.Logger) -> int:
    """So khớp 'expectations' của kịch bản với thực tế (violations ghi bởi
    sim_monitor.py + thời điểm từng xe hoàn tất route). In + ghi báo cáo
    PASS/FAIL. Trả exit code (0 = tất cả PASS, 1 = có FAIL)."""
    violations = _read_violations(args.violations_path)
    results = []
    all_pass = True

    for exp in expectations:
        etype = exp.get("type")
        if etype == "no_violations":
            kinds = exp.get("kinds")
            max_count = int(exp.get("max_count", 0))
            matched = [v for v in violations if not kinds or v.get("kind") in kinds]
            ok = len(matched) <= max_count
            desc = (f"no_violations kinds={kinds or 'ALL'} max={max_count} "
                    f"→ thực tế {len(matched)}")
        elif etype == "arrive":
            aid = exp.get("agv_id")
            exp_node = exp.get("node")
            within_s = float(exp.get("within_s", 1e9))
            st = state.get(aid) or {}
            done_at = st.get("done_at")
            # Xe "return_to_charge" kết thúc ở trạm sạc HOẶC điểm chờ (không ép 1
            # node cụ thể — xem run_scenario) → bỏ qua so khớp node, chỉ xét
            # within_s. Xe route thường thì vẫn phải khớp đúng node cuối route.
            if st.get("return_to_charge"):
                node_ok = True
                actual_last_node = None
            else:
                actual_last_node = (st.get("route") or [None])[-1]
                node_ok = exp_node is None or str(exp_node) == str(actual_last_node)
            ok = done_at is not None and done_at <= within_s and node_ok
            if not node_ok:
                desc = (f"arrive {aid} tại node {exp_node} → route kịch bản của {aid} "
                        f"kết thúc ở node {actual_last_node}, không khớp expectation")
            else:
                desc = (f"arrive {aid} within {within_s:.0f}s → "
                        f"{'chưa tới đích' if done_at is None else f'tới lúc {done_at:.1f}s'}")
        else:
            ok = False
            desc = f"loại expectation không hỗ trợ: {etype!r}"
        all_pass = all_pass and ok
        results.append({"ok": ok, "desc": desc, "expectation": exp})
        logger.info(f"[{'PASS' if ok else 'FAIL'}] {desc}")

    report = {
        "scenario": name,
        "overall": "PASS" if all_pass else "FAIL",
        "results": results,
        "agv_final_state": state,
        "violations_checked": len(violations),
    }
    ts = time.strftime("%Y%m%d_%H%M%S")
    report_path = args.report_path or os.path.join(
        args.log_dir, f"scenario_result_{name}_{ts}.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    logger.info(f"[SCENARIO] KẾT QUẢ: {report['overall']} — đã ghi {report_path}")
    print(f"\n{'=' * 70}\nKỊCH BẢN '{name}': {report['overall']}\n{'=' * 70}")
    return 0 if all_pass else 1


def run_scenario(args, logger: logging.Logger) -> int:
    """Chế độ KỊCH BẢN — đọc file JSON định sẵn mỗi xe đi đâu lúc nào, chạy tới
    khi XONG HẾT route của mọi xe hoặc hết --timeout-s (khai trong file, mặc
    định 300s), rồi tự so khớp 'expectations', in PASS/FAIL, ghi báo cáo, trả
    exit code (KHÔNG lặp vô hạn như chế độ ngẫu nhiên)."""
    with open(args.scenario, "r", encoding="utf-8") as f:
        scenario = json.load(f)

    name = scenario.get("name") or os.path.splitext(os.path.basename(args.scenario))[0]
    agv_specs: dict = scenario.get("agvs") or {}
    expectations: list = scenario.get("expectations") or []
    timeout_s = float(scenario.get("timeout_s", 300))

    if not agv_specs:
        raise SystemExit(f"Kịch bản '{name}' không có 'agvs' nào — không có gì để chạy")

    logger.info(f"[SCENARIO] '{name}' — {len(agv_specs)} xe, timeout={timeout_s:.0f}s")
    for aid, spec in agv_specs.items():
        logger.info(f"[SCENARIO]   {aid}: start_at={float(spec.get('start_at_s', 0)):.0f}s "
                    f"route={spec.get('route')}"
                    + (" → về trạm/điểm chờ" if spec.get("return_to_charge") else ""))

    scen_start = time.time()
    state: dict[str, dict] = {
        aid: {"idx": 0, "started": False, "done_at": None, "charge_dispatched": False,
              "route": [str(n) for n in (spec.get("route") or [])],
              "return_to_charge": bool(spec.get("return_to_charge", False))}
        for aid, spec in agv_specs.items()
    }

    while True:
        elapsed = time.time() - scen_start
        if all(st["done_at"] is not None for st in state.values()):
            logger.info(f"[SCENARIO] TẤT CẢ xe đã hoàn tất route sau {elapsed:.1f}s")
            break
        if elapsed >= timeout_s:
            logger.info(f"[SCENARIO] HẾT TIMEOUT {timeout_s:.0f}s — còn xe chưa hoàn tất route: "
                        f"{[a for a, st in state.items() if st['done_at'] is None]}")
            break

        try:
            resp = requests.get(f"{args.api_base}/api/execute/agv-list", timeout=5)
            resp.raise_for_status()
            rows = {r.get("agv_id"): r for r in resp.json().get("agvs", [])}
        except Exception as e:
            logger.info(f"[WARN] không gọi được agv-list: {e}")
            time.sleep(args.poll_interval)
            continue

        for aid, spec in agv_specs.items():
            st = state[aid]
            if st["done_at"] is not None:
                continue
            row = rows.get(aid)
            if row is None:
                continue

            if _handle_hook_and_lifecycle(args.api_base, aid, row, logger):
                continue

            route = [str(n) for n in (spec.get("route") or [])]
            return_to_charge = bool(spec.get("return_to_charge", False))
            is_busy = bool(row.get("is_busy") or row.get("queue_size", 0) > 0
                           or row.get("driving"))

            if not st["started"]:
                if elapsed >= float(spec.get("start_at_s", 0)) and not is_busy and route:
                    if _dispatch_task(args.api_base, aid, route[0], logger):
                        st["started"] = True
                        st["idx"] = 1
                continue

            if is_busy:
                continue

            if st["idx"] < len(route):
                if _dispatch_task(args.api_base, aid, route[st["idx"]], logger):
                    st["idx"] += 1
                continue

            # Hết route (đã tới đích route[-1]), xe đang rảnh.
            if not return_to_charge:
                # Chỉ coi là HOÀN TẤT nếu đúng đang ở node cuối cùng của route
                # (không phải rảnh vì lý do khác/lỗi dispatch).
                if route and str(row.get("current_node")) == route[-1]:
                    st["done_at"] = elapsed
                    logger.info(f"[SCENARIO] {aid}: hoàn tất route tại node {route[-1]} "
                                f"sau {elapsed:.1f}s")
                continue

            # return_to_charge=True — gọi ĐÚNG API "Về trạm" thật (/api/agv/go-charge)
            # 1 lần duy nhất, để xe tự chạy ĐỦ quy trình chuẩn (chọn trạm sạc ít bị
            # chiếm nhất, hoặc tự chuyển sang điểm chờ đã cấu hình + tự retry nếu
            # TẤT CẢ trạm sạc đều có xe — xem main.monitor_charge_station_wait).
            # Coi là HOÀN TẤT khi xe rảnh hẳn LẦN KẾ TIẾP sau đó — dù dừng ở trạm
            # sạc hay ở điểm chờ, CẢ 2 đều là "đi đúng, đủ quy trình" theo đúng ý
            # kịch bản (không ép phải tới đúng 1 node sạc cụ thể).
            if not st["charge_dispatched"]:
                if _dispatch_go_charge(args.api_base, aid, logger):
                    st["charge_dispatched"] = True
                continue

            st["done_at"] = elapsed
            logger.info(f"[SCENARIO] {aid}: hoàn tất round-trip (đã Về trạm/điểm chờ) "
                        f"sau {elapsed:.1f}s, đang ở node {row.get('current_node')}")

        time.sleep(args.poll_interval)

    # Chờ 1 nhịp cho sim_monitor.py (tiến trình riêng) kịp ghi hết violation
    # của những giây cuối vào file trước khi đọc lại để so khớp expectations.
    time.sleep(3.0)
    return _evaluate_and_report(name, expectations, state, args, logger)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--api-base", default=os.getenv("SIM_API_BASE", "http://localhost:8000"))
    ap.add_argument("--db-url", default=os.getenv(
        "DATABASE_URL", "postgresql://postgres:ducmanh1801@localhost:5432/TOT_AGV_SIM"))
    ap.add_argument("--factory", default="SimFactory")
    ap.add_argument("--poll-interval", type=float, default=3.0)
    ap.add_argument("--manual", action="store_true",
                     help="Chế độ giao lệnh: KHÔNG tự sinh tác vụ ngẫu nhiên, chỉ tự xác nhận móc/lifecycle; "
                          "xe chạy khi người dùng gửi lệnh (bỏ qua nếu dùng --scenario)")
    ap.add_argument("--duration-hours", type=float, default=0.0,
                     help="0 = chạy vô hạn (tới khi Ctrl+C) — chỉ áp dụng chế độ ngẫu nhiên, "
                          "bỏ qua khi dùng --scenario (dùng 'timeout_s' trong file kịch bản)")
    ap.add_argument("--log-dir", default=os.path.join(os.path.dirname(__file__), "logs"))
    ap.add_argument("--scenario", default=None,
                     help="Đường dẫn file JSON kịch bản test — có giá trị này thì BỎ QUA sinh "
                          "tác vụ ngẫu nhiên, chạy đúng kịch bản rồi thoát (xem "
                          "simulation/scenarios/example_same_destination.json làm mẫu)")
    ap.add_argument("--violations-path", default=None,
                     help="Đường dẫn violations_*.jsonl của sim_monitor.py CÙNG lượt chạy — để "
                          "so khớp expectation 'no_violations' (chỉ cần khi dùng --scenario)")
    ap.add_argument("--report-path", default=None,
                     help="Đường dẫn ghi báo cáo PASS/FAIL (mặc định "
                          "logs/scenario_result_<tên kịch bản>_<ts>.json)")
    args = ap.parse_args()

    os.makedirs(args.log_dir, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    logger = logging.getLogger("sim_task_gen")
    logger.setLevel(logging.INFO)
    fh = logging.FileHandler(os.path.join(args.log_dir, f"taskgen_{ts}.log"), encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    logger.addHandler(fh)
    logger.addHandler(logging.StreamHandler())

    if args.scenario:
        sys.exit(run_scenario(args, logger))
    else:
        run_random(args, logger)


if __name__ == "__main__":
    main()
