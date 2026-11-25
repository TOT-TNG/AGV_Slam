"""
setup_sim_db.py — Tạo database mô phỏng TÁCH BIỆT HOÀN TOÀN khỏi TOT_AGV thật.

KHÔNG đụng tới database nguồn (TOT_AGV) ngoài việc ĐỌC (SELECT) để copy bản đồ.
Chạy 1 lần (hoặc mỗi khi muốn reset sạch) trước khi chạy mô phỏng:

    python setup_sim_db.py --agv-count 15

Sau khi chạy xong, database "TOT_AGV_SIM" sẽ có:
  - Bản đồ (--map-id, mặc định TOT_Test) copy từ TOT_AGV (chỉ đọc, không đổi gì ở nguồn).
  - N xe ảo SIM01..SIMnn trong agv_devices (--agv-type: tow|trailer|carry|mixed).
  - Bảng agv_tasks rỗng, sẵn sàng cho /api/tasks (main.py tự ensure cột khi khởi động).
"""
from __future__ import annotations

import argparse
import json
import sys

import psycopg2
import psycopg2.extras

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

SOURCE_DB  = "postgresql://postgres:ducmanh1801@localhost:5432/TOT_AGV"
ADMIN_DB   = "postgresql://postgres:ducmanh1801@localhost:5432/postgres"
SIM_DBNAME = "TOT_AGV_SIM"
SIM_DB     = f"postgresql://postgres:ducmanh1801@localhost:5432/{SIM_DBNAME}"
DEFAULT_MAP_ID = "1788938884681"   # TOT_Test — mặc định khi không chọn map khác
VALID_AGV_TYPES = {"tow", "trailer", "carry", "mixed"}
# Các "loại xe" dùng trong --agv-mix (số lượng từng loại, chạy CÙNG LÚC trên 1 map):
#   tow          xe kéo, chu trình tự động lấy/cấp hàng (op_mode=roundtrip)
#   tow_hook     xe kéo chở hàng có móc (carry_hook), về thẳng trạm sạc
#   tow_hook_drop xe kéo carry_hook + kéo xe hàng tới điểm thả cố định rồi mới sạc
#   tow_fixed    xe kéo thùng cố định, không móc (carry_fixed)
#   trailer      rơ-moóc (chỉ tiến, không lùi)
#   carry        xe chở thường
# kind -> (agv_type, op_mode, return_mode)
MIX_KINDS = {
    "tow":           ("tow",     "roundtrip",   "charge"),
    "tow_hook":      ("tow",     "carry_hook",  "charge"),
    "tow_hook_drop": ("tow",     "carry_hook",  "drop_cart"),
    "tow_fixed":     ("tow",     "carry_fixed", "charge"),
    "trailer":       ("trailer", "roundtrip",   "charge"),
    "carry":         ("carry",   "roundtrip",   "charge"),
}


def parse_mix(text: str) -> list[str]:
    """'tow=6,trailer=4' -> ['tow']*6 + ['trailer']*4 (giữ thứ tự khai báo)."""
    kinds: list[str] = []
    for part in (text or "").split(","):
        part = part.strip()
        if not part:
            continue
        k, _, v = part.partition("=")
        k = k.strip()
        if k not in MIX_KINDS:
            raise SystemExit(f"--agv-mix: loại '{k}' không hợp lệ (hợp lệ: {', '.join(MIX_KINDS)})")
        try:
            n = int(v)
        except ValueError:
            raise SystemExit(f"--agv-mix: số lượng của '{k}' không hợp lệ: {v!r}")
        if n < 0:
            raise SystemExit(f"--agv-mix: số lượng của '{k}' phải >= 0")
        kinds += [k] * n
    return kinds


DDL = """
CREATE TABLE IF NOT EXISTS agv_devices (
    name         text PRIMARY KEY,
    agv_type     text NOT NULL,
    ip           inet,
    port         integer,
    last_seen    timestamptz,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    map_id       text,
    factory      text,
    last_tag     text,
    subnet       text,
    gateway      text,
    dns          text,
    can_reverse  boolean DEFAULT true
);

CREATE TABLE IF NOT EXISTS agv_maps (
    id            text PRIMARY KEY,
    name          text NOT NULL,
    origin_x      double precision NOT NULL DEFAULT 0,
    origin_y      double precision NOT NULL DEFAULT 0,
    origin_theta  double precision NOT NULL DEFAULT 0,
    resolution    double precision NOT NULL DEFAULT 0.05,
    image_path    text,
    modify_time   timestamptz,
    layer         integer DEFAULT 0,
    created_at    timestamptz DEFAULT now(),
    updated_at    timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agv_map_points (
    id         serial PRIMARY KEY,
    map_id     text,
    name_id    text NOT NULL,
    name       text,
    x          double precision NOT NULL,
    y          double precision NOT NULL,
    theta      double precision NOT NULL DEFAULT 0,
    type       integer DEFAULT 0,
    zone       text,
    action     jsonb,
    carrier    integer DEFAULT 0,
    available  boolean DEFAULT false,
    accuracy   integer DEFAULT 0,
    speed      double precision DEFAULT 0.5
);

CREATE TABLE IF NOT EXISTS agv_map_roads (
    id               serial PRIMARY KEY,
    map_id           text,
    name             text,
    id_source        text NOT NULL,
    id_dest          text NOT NULL,
    point_start_x    double precision NOT NULL DEFAULT 0,
    point_start_y    double precision NOT NULL DEFAULT 0,
    point_end_x      double precision NOT NULL DEFAULT 0,
    point_end_y      double precision NOT NULL DEFAULT 0,
    width            double precision DEFAULT 0.95,
    speed            double precision DEFAULT 0.3,
    move_direction   integer DEFAULT 0,
    distance         double precision,
    lidar_off        boolean DEFAULT false,
    lidar_off_dir    text DEFAULT 'none',
    speed_bwd        double precision,
    type_directions  text,
    distance_manual  boolean DEFAULT false
);

CREATE TABLE IF NOT EXISTS agv_map_benziers (
    id                    serial PRIMARY KEY,
    map_id                text,
    name                  varchar,
    id_source             varchar,
    id_dest               varchar,
    point_start_x         double precision,
    point_start_y         double precision,
    point_end_x           double precision,
    point_end_y           double precision,
    curve_point_start_x   double precision,
    curve_point_start_y   double precision,
    curve_point_end_x     double precision,
    curve_point_end_y     double precision,
    width                 double precision DEFAULT 0.3,
    speed                 double precision DEFAULT 0.3,
    move_direction        integer DEFAULT 0,
    lidar_off             boolean DEFAULT false,
    lidar_off_dir         text DEFAULT 'none',
    speed_bwd             double precision,
    type_directions       text,
    distance              double precision,
    distance_manual       boolean DEFAULT false
);

CREATE TABLE IF NOT EXISTS agv_tasks (
    id             serial PRIMARY KEY,
    task_id        varchar DEFAULT (gen_random_uuid())::text,
    agv_id         varchar NOT NULL,
    destination    varchar NOT NULL,
    map_id         varchar,
    status         varchar DEFAULT 'pending',
    order_id       varchar,
    notes          text,
    created_at     timestamptz DEFAULT now(),
    updated_at     timestamptz DEFAULT now(),
    operator_name  text,
    operator_id    text,
    order_info     jsonb
);
"""


def _ensure_sim_database() -> None:
    conn = psycopg2.connect(ADMIN_DB)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname=%s", (SIM_DBNAME,))
        if cur.fetchone():
            print(f"[SETUP_SIM] database {SIM_DBNAME} đã tồn tại — giữ nguyên "
                  f"(dùng --reset nếu muốn xoá sạch làm lại)")
        else:
            cur.execute(f'CREATE DATABASE "{SIM_DBNAME}"')
            print(f"[SETUP_SIM] đã tạo database {SIM_DBNAME}")
    conn.close()


def _drop_sim_database() -> None:
    conn = psycopg2.connect(ADMIN_DB)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname=%s AND pid <> pg_backend_pid()", (SIM_DBNAME,)
        )
        cur.execute(f'DROP DATABASE IF EXISTS "{SIM_DBNAME}"')
    conn.close()
    print(f"[SETUP_SIM] đã xoá database {SIM_DBNAME} (nếu có)")


def _parse_edge_length(text: str):
    """'3.5-4' -> (3.5, 4.0); '' -> None."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        lo, _, hi = text.partition("-")
        lo_f = float(lo); hi_f = float(hi) if hi else lo_f
    except ValueError:
        raise SystemExit(f"--edge-length không hợp lệ: {text!r} (vd 3.5-4)")
    if lo_f <= 0 or hi_f < lo_f:
        raise SystemExit(f"--edge-length không hợp lệ: {text!r}")
    return lo_f, hi_f


def _apply_edge_length(sim_conn, map_id: str, rng) -> None:
    """Đặt độ dài mọi cạnh (m) trong khoảng rng, xoay vòng 3 mức, distance_manual=TRUE (chỉ DB mô phỏng)."""
    lo, hi = rng
    levels = [lo, (lo + hi) / 2, hi]
    cur = sim_conn.cursor()
    n = 0
    for tbl in ("agv_map_roads", "agv_map_benziers"):
        cur.execute(f"SELECT id FROM {tbl} WHERE map_id=%s ORDER BY id", (map_id,))
        for i, (rid,) in enumerate(cur.fetchall()):
            cur.execute(f"UPDATE {tbl} SET distance=%s, distance_manual=TRUE WHERE id=%s", (levels[i % 3], rid))
            n += 1
    sim_conn.commit()
    print(f"[SETUP_SIM] đặt độ dài {n} cạnh trong {lo:g}-{hi:g} m (distance_manual, chỉ DB mô phỏng)")


def _clone_map(src_conn, sim_conn, map_id: str) -> None:
    sim_cur = sim_conn.cursor()
    sim_cur.execute(DDL)
    sim_conn.commit()

    # Xoá dữ liệu map cũ (nếu setup lại không --reset DB) để khỏi trùng khoá.
    sim_cur.execute("DELETE FROM agv_map_points WHERE map_id=%s", (map_id,))
    sim_cur.execute("DELETE FROM agv_map_roads WHERE map_id=%s", (map_id,))
    sim_cur.execute("DELETE FROM agv_map_benziers WHERE map_id=%s", (map_id,))
    sim_cur.execute("DELETE FROM agv_maps WHERE id=%s", (map_id,))
    sim_conn.commit()

    src_cur = src_conn.cursor()

    src_cur.execute(
        "SELECT id, name, origin_x, origin_y, origin_theta, resolution, "
        "image_path, layer FROM agv_maps WHERE id=%s", (map_id,)
    )
    row = src_cur.fetchone()
    if not row:
        raise RuntimeError(f"Không tìm thấy map_id={map_id} trong TOT_AGV nguồn")
    sim_cur.execute(
        "INSERT INTO agv_maps (id, name, origin_x, origin_y, origin_theta, "
        "resolution, image_path, layer) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", row
    )

    src_cur.execute(
        "SELECT map_id, name_id, name, x, y, theta, type, zone, action, "
        "carrier, available, accuracy, speed FROM agv_map_points WHERE map_id=%s",
        (map_id,),
    )
    pts = src_cur.fetchall()
    for r in pts:
        r = list(r)
        r[8] = psycopg2.extras.Json(r[8]) if r[8] is not None else None   # action jsonb
        sim_cur.execute(
            "INSERT INTO agv_map_points (map_id, name_id, name, x, y, theta, "
            "type, zone, action, carrier, available, accuracy, speed) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", r
        )

    # Cột hướng riêng theo loại xe có thể chưa có ở DB nguồn (server thật chưa khởi động lại sau
    # khi nâng cấp) → chỉ SELECT khi tồn tại, nếu không dùng NULL. KHÔNG sửa schema DB nguồn.
    def _src_has(table: str, col: str) -> bool:
        src_cur.execute("SELECT 1 FROM information_schema.columns WHERE table_name=%s AND column_name=%s",
                        (table, col))
        return src_cur.fetchone() is not None
    _td_roads = "type_directions" if _src_has("agv_map_roads", "type_directions") else "NULL::text"
    _td_benz  = "type_directions" if _src_has("agv_map_benziers", "type_directions") else "NULL::text"
    sim_cur.execute("ALTER TABLE agv_map_roads ADD COLUMN IF NOT EXISTS type_directions TEXT")
    sim_cur.execute("ALTER TABLE agv_map_benziers ADD COLUMN IF NOT EXISTS type_directions TEXT")

    src_cur.execute(
        "SELECT map_id, name, id_source, id_dest, point_start_x, point_start_y, "
        "point_end_x, point_end_y, width, speed, move_direction, distance, "
        f"lidar_off, lidar_off_dir, speed_bwd, distance_manual, {_td_roads} "
        "FROM agv_map_roads WHERE map_id=%s", (map_id,),
    )
    roads = src_cur.fetchall()
    for r in roads:
        sim_cur.execute(
            "INSERT INTO agv_map_roads (map_id, name, id_source, id_dest, "
            "point_start_x, point_start_y, point_end_x, point_end_y, width, "
            "speed, move_direction, distance, lidar_off, lidar_off_dir, "
            "speed_bwd, distance_manual, type_directions) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", r
        )

    src_cur.execute(
        "SELECT map_id, name, id_source, id_dest, point_start_x, point_start_y, "
        "point_end_x, point_end_y, curve_point_start_x, curve_point_start_y, "
        "curve_point_end_x, curve_point_end_y, width, speed, move_direction, "
        f"lidar_off, lidar_off_dir, speed_bwd, distance, distance_manual, {_td_benz} "
        "FROM agv_map_benziers WHERE map_id=%s", (map_id,),
    )
    benz = src_cur.fetchall()
    for r in benz:
        sim_cur.execute(
            "INSERT INTO agv_map_benziers (map_id, name, id_source, id_dest, "
            "point_start_x, point_start_y, point_end_x, point_end_y, "
            "curve_point_start_x, curve_point_start_y, curve_point_end_x, "
            "curve_point_end_y, width, speed, move_direction, lidar_off, "
            "lidar_off_dir, speed_bwd, distance, distance_manual, type_directions) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", r
        )

    # ── Nhiều tầng / thang máy: chép danh sách tầng, thang, và tầng của từng node/cạnh ──
    # (không chép thì map 3 tầng trong DB mô phỏng mất thông tin tầng → bản đồ vẽ CHỒNG các tầng)
    for tbl in ("agv_map_points", "agv_map_roads", "agv_map_benziers"):
        sim_cur.execute(f"ALTER TABLE {tbl} ADD COLUMN IF NOT EXISTS floor_id TEXT DEFAULT ''")
    sim_cur.execute("ALTER TABLE agv_maps ADD COLUMN IF NOT EXISTS floors JSONB")
    sim_cur.execute("ALTER TABLE agv_maps ADD COLUMN IF NOT EXISTS elevators JSONB")
    if _src_has("agv_maps", "floors"):
        src_cur.execute("SELECT floors, "
                        + ("elevators" if _src_has("agv_maps", "elevators") else "NULL::jsonb")
                        + " FROM agv_maps WHERE id=%s", (map_id,))
        fl, el = src_cur.fetchone()
        sim_cur.execute("UPDATE agv_maps SET floors=%s, elevators=%s WHERE id=%s",
                        (psycopg2.extras.Json(fl) if fl is not None else None,
                         psycopg2.extras.Json(el) if el is not None else None, map_id))
    if _src_has("agv_map_points", "floor_id"):
        src_cur.execute("SELECT name_id, COALESCE(floor_id,'') FROM agv_map_points WHERE map_id=%s", (map_id,))
        for nid, fid in src_cur.fetchall():
            sim_cur.execute("UPDATE agv_map_points SET floor_id=%s WHERE map_id=%s AND name_id=%s",
                            (fid, map_id, nid))
        for tbl in ("agv_map_roads", "agv_map_benziers"):
            src_cur.execute(f"SELECT id_source, id_dest, COALESCE(floor_id,'') FROM {tbl} WHERE map_id=%s", (map_id,))
            for a, b, fid in src_cur.fetchall():
                sim_cur.execute(f"UPDATE {tbl} SET floor_id=%s WHERE map_id=%s AND id_source=%s AND id_dest=%s",
                                (fid, map_id, a, b))

    normalize_sim_map(sim_cur, map_id)
    sim_conn.commit()
    print(f"[SETUP_SIM] copy map {map_id}: {len(pts)} point, {len(roads)} road, "
          f"{len(benz)} benzier")


_PIXEL_DIST_THRESHOLD = 60.0    # cạnh dài hơn mức này (mét) coi như đơn vị pixel
_SIM_EDGE_DIST = 4.0            # mọi cạnh = 4 m (mỗi cạnh ~8 s) — chỉnh từng cạnh sau nếu cần


def normalize_sim_map(sim_cur, map_id: str) -> None:
    """Chỉnh bản đồ trong DB MÔ PHỎNG (không đụng DB thật) để chạy được:
    - distance của map vẽ theo pixel (vd TNGF: 80-200) -> xe mất hàng trăm giây/cạnh, trông như đứng yên ở trạm sạc;
    - "Số tầng" (level) trùng nhau -> floor_nav từ chối mọi nhiệm vụ liên tầng."""
    sim_cur.execute("SELECT COALESCE(MAX(distance),0) FROM agv_map_roads WHERE map_id=%s", (map_id,))
    if (sim_cur.fetchone()[0] or 0) > _PIXEL_DIST_THRESHOLD:
        for tbl in ("agv_map_roads", "agv_map_benziers"):
            sim_cur.execute(f"UPDATE {tbl} SET distance=%s WHERE map_id=%s", (_SIM_EDGE_DIST, map_id))
        print(f"[SETUP_SIM] distance dạng pixel -> đặt mọi cạnh = {_SIM_EDGE_DIST:g} m (chỉ DB mô phỏng)")
    sim_cur.execute("SELECT floors FROM agv_maps WHERE id=%s", (map_id,))
    row = sim_cur.fetchone()
    floors = row[0] if row and row[0] else []
    seen, changed = set(), False
    for f in floors:
        lv = f.get("level")
        while lv in seen:
            lv = (lv or 0) + 1
            changed = True
        f["level"] = lv
        seen.add(lv)
    if changed:
        sim_cur.execute("UPDATE agv_maps SET floors=%s WHERE id=%s", (psycopg2.extras.Json(floors), map_id))
        print("[SETUP_SIM] 'Số tầng' trùng nhau -> đánh số lại (chỉ DB mô phỏng)")


def parse_start_nodes(text: str) -> dict[str, list[str]]:
    """'tow=221,222;trailer=224;carry=225' -> {'tow': ['221','222'], ...} (khoá = agv_type)."""
    out: dict[str, list[str]] = {}
    for part in (text or "").replace("|", ";").split(";"):
        part = part.strip()
        if not part:
            continue
        k, _, v = part.partition("=")
        k = k.strip().lower()
        if k not in ("tow", "trailer", "carry"):
            raise SystemExit(f"--start-nodes: loại xe '{k}' không hợp lệ (tow|trailer|carry)")
        out[k] = [n.strip() for n in v.split(",") if n.strip()]
    return out


def _node_info(sim_conn, map_id: str) -> dict[str, dict]:
    cur = sim_conn.cursor()
    cur.execute("SELECT name_id, action FROM agv_map_points WHERE map_id=%s", (map_id,))
    info = {}
    for nid, act in cur.fetchall():
        if isinstance(act, str):
            try:
                act = json.loads(act)
            except Exception:
                act = {}
        info[str(nid)] = act if isinstance(act, dict) else {}
    return info


def _node_allows(act: dict, agv_type: str) -> bool:
    """Node có cho loại xe này vào không (allowed_agv_types rỗng/thiếu = mọi loại)."""
    allowed = act.get("allowed_agv_types") or []
    if isinstance(allowed, str):
        allowed = allowed.split(",")
    allowed = [str(a).strip().lower() for a in allowed if str(a).strip()]
    return (not allowed) or agv_type in allowed


def _node_floors(sim_conn, map_id: str) -> tuple[dict[str, str], list[str]]:
    """(node → id tầng, danh sách id tầng theo thứ tự). Map 1 tầng / chưa có thông tin tầng → ({}, [])."""
    cur = sim_conn.cursor()
    cur.execute("SELECT floors FROM agv_maps WHERE id=%s", (map_id,))
    row = cur.fetchone()
    floors = [str(f.get("id")) for f in (row[0] or [])] if row and row[0] else []
    if len(floors) <= 1:
        return {}, floors
    cur.execute("SELECT name_id, COALESCE(floor_id,'') FROM agv_map_points WHERE map_id=%s", (map_id,))
    nf = {str(n): (f if f in floors else floors[0]) for n, f in cur.fetchall()}
    return nf, floors


def _auto_start_candidates(info: dict[str, dict], agv_type: str) -> list[str]:
    """Thứ tự ưu tiên chọn vị trí xuất phát tự động cho 1 loại xe: (1) trạm sạc dành cho loại
    xe đó hoặc dùng chung, (2) node chờ, (3) node thường — luôn bỏ node loại xe này bị cấm."""
    def num(n):
        return (0, int(n)) if str(n).isdigit() else (1, str(n))
    chargers, waiting, others = [], [], []
    for nid, act in info.items():
        if not _node_allows(act, agv_type):
            continue
        if act.get("locationType") == "CHARGER":
            st = str(act.get("station_agv_type") or "").strip().lower()
            if not st or st == agv_type:
                # trạm sạc ĐÚNG loại xe ưu tiên trước trạm dùng chung
                chargers.append((0 if st == agv_type else 1, num(nid), nid))
        elif act.get("waiting_node") == "yes":
            waiting.append((num(nid), nid))
        else:
            others.append((num(nid), nid))
    return ([c[2] for c in sorted(chargers)] + [w[1] for w in sorted(waiting)]
            + [o[1] for o in sorted(others)])


def _insert_sim_agvs(sim_conn, count: int, map_id: str, agv_type: str,
                     mix: list[str] | None = None,
                     start_nodes: dict[str, list[str]] | None = None) -> None:
    cur = sim_conn.cursor()
    cur.execute("ALTER TABLE agv_devices ADD COLUMN IF NOT EXISTS sim_start_node TEXT")
    info = _node_info(sim_conn, map_id)
    node_floor, floor_order = _node_floors(sim_conn, map_id)
    start_nodes = start_nodes or {}
    used: set[str] = set()
    # Node người dùng chỉ định phải tồn tại + loại xe đó được phép vào (kiểm tra TRƯỚC khi tạo xe)
    bad = []
    for t, nodes in start_nodes.items():
        for n in nodes:
            if n not in info:
                bad.append(f"node {n} (loại {t}) không có trong map {map_id}")
            elif not _node_allows(info[n], t):
                allowed = info[n].get("allowed_agv_types") or []
                allowed = allowed.split(",") if isinstance(allowed, str) else allowed
                bad.append(f"node {n} nằm trong VÙNG CẤM của loại '{t}' (node này chỉ cho: {', '.join(allowed)})")
    if bad:
        raise SystemExit("--start-nodes không hợp lệ: " + " | ".join(bad))
    queues = {t: list(nodes) for t, nodes in start_nodes.items()}
    cur.execute("ALTER TABLE agv_devices ADD COLUMN IF NOT EXISTS op_mode TEXT DEFAULT 'roundtrip'")
    cur.execute("ALTER TABLE agv_devices ADD COLUMN IF NOT EXISTS return_mode TEXT DEFAULT 'charge'")
    cur.execute("DELETE FROM agv_devices WHERE name LIKE 'SIM%%'")
    if mix:
        count = len(mix)
    names = []
    summary: dict[str, int] = {}
    for i in range(1, count + 1):
        name = f"SIM{i:02d}"
        names.append(name)
        if mix:
            this_type, op_mode, return_mode = MIX_KINDS[mix[i - 1]]
            summary[mix[i - 1]] = summary.get(mix[i - 1], 0) + 1
        else:
            # "mixed" (cũ) chia chẵn/lẻ giữa tow/trailer.
            this_type = agv_type
            if agv_type == "mixed":
                this_type = "tow" if i % 2 == 1 else "trailer"
            op_mode, return_mode = "roundtrip", "charge"
        # Đúng quy ước đã dùng cho xe thật (xem Web_UI/agv_manager.py: "xe đầu
        # kéo/rơ-moóc (chỉ tiến) truyền False") — xe ảo loại "trailer" cũng chỉ
        # được tiến, không lùi, để test được đúng nhánh pathfinder phạt nặng
        # bước lùi (map_manager.line_directional_path, BWD_PENALTY). "tow"/
        # "carry" vẫn lùi được như cũ.
        this_can_reverse = (this_type != "trailer")
        # Vị trí xuất phát: ưu tiên danh sách người dùng chỉ định cho loại xe này (lần lượt từng
        # xe), hết/không khai thì tự chọn trạm sạc phù hợp loại xe (không trùng xe khác).
        start = None
        q = queues.get(this_type) or []
        while q:
            cand = q.pop(0)
            if cand not in used:
                start = cand
                break
        if start is None:
            # Giữ đúng thứ tự ưu tiên cũ (trạm sạc → node chờ → node thường), KHÔNG ép rải đều theo tầng:
            # map nhiều tầng thường chỉ có trạm sạc ở 1 tầng — xe xuất phát ở đó, sang tầng khác bằng thang.
            start = next((c for c in _auto_start_candidates(info, this_type) if c not in used), None)
        if start:
            used.add(start)
        cur.execute(
            "INSERT INTO agv_devices (name, agv_type, factory, map_id, can_reverse, op_mode, return_mode, sim_start_node) "
            "VALUES (%s,%s,'SimFactory',%s,%s,%s,%s,%s)",
            (name, this_type, map_id, this_can_reverse, op_mode, return_mode, start),
        )
    sim_conn.commit()
    print(f"[SETUP_SIM] đã tạo {count} xe ảo ("
          f"{summary if mix else 'loại=' + agv_type}): {names}")
    cur.execute("SELECT name, agv_type, op_mode, sim_start_node FROM agv_devices "
                "WHERE name LIKE 'SIM%%' ORDER BY name")
    for n, t, om, sn in cur.fetchall():
        _fl = f" (tầng {node_floor.get(sn)})" if (sn and len(floor_order) > 1) else ""
        print(f"[SETUP_SIM]   {n}: {t}/{om} xuất phát tại node {sn or '(tự rải)'}{_fl}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--agv-count", type=int, default=15,
                     help="Số xe ảo (10-20 khuyến nghị), mặc định 15")
    ap.add_argument("--map-id", default=DEFAULT_MAP_ID,
                     help="map_id thật cần clone dữ liệu (node/road) để mô phỏng")
    ap.add_argument("--agv-type", default="tow", choices=sorted(VALID_AGV_TYPES),
                     help="Loại xe ảo: tow|trailer|carry|mixed (mixed=chia đều tow/trailer)")
    ap.add_argument("--agv-mix", default="",
                     help="Trộn nhiều loại xe, vd 'tow=6,tow_hook=2,tow_fixed=1,trailer=4,carry=4' "
                          "(có giá trị này thì BỎ QUA --agv-count/--agv-type, tổng xe = tổng số lượng). "
                          f"Loại hợp lệ: {', '.join(MIX_KINDS)}")
    ap.add_argument("--start-nodes", default="",
                     help="Vị trí xuất phát theo loại xe, vd 'tow=221,222;trailer=224;carry=225,226' "
                          "(lần lượt từng xe cùng loại; hết/không khai thì tự chọn trạm sạc phù hợp loại xe)")
    ap.add_argument("--edge-length", default="",
                     help="Ép độ dài mọi cạnh (mét) trong DB mô phỏng, vd '3.5-4' (xoay vòng 3 mức)")
    ap.add_argument("--reset", action="store_true",
                     help="Xoá sạch database mô phỏng cũ rồi tạo lại từ đầu")
    args = ap.parse_args()

    mix = parse_mix(args.agv_mix)
    if mix and not (1 <= len(mix) <= 50):
        raise SystemExit("--agv-mix: tổng số xe phải trong khoảng 1-50")
    if not mix and not (1 <= args.agv_count <= 50):
        raise SystemExit("--agv-count phải trong khoảng 1-50")

    if args.reset:
        _drop_sim_database()

    _ensure_sim_database()

    src_conn = psycopg2.connect(SOURCE_DB)
    sim_conn = psycopg2.connect(SIM_DB)
    try:
        _clone_map(src_conn, sim_conn, args.map_id)
        _rng = _parse_edge_length(args.edge_length)
        if _rng:
            _apply_edge_length(sim_conn, args.map_id, _rng)
        _insert_sim_agvs(sim_conn, args.agv_count, args.map_id, args.agv_type, mix,
                         parse_start_nodes(args.start_nodes))
    finally:
        src_conn.close()
        sim_conn.close()

    print("[SETUP_SIM] XONG. Database TOT_AGV thật KHÔNG bị thay đổi gì cả "
          "(chỉ đọc để copy).")
    print(f"[SETUP_SIM] Khi chạy mô phỏng, set biến môi trường:")
    print(f'  DATABASE_URL="{SIM_DB}"')


if __name__ == "__main__":
    main()
