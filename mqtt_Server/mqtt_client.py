# mqtt_client.py
import json
import datetime
import time
import uuid
<<<<<<< HEAD
import math
import paho.mqtt.client as mqtt
from agv_manager import AGVManager
import asyncio
from fastapi import FastAPI
=======
import os
import math
import re
import asyncio
from urllib.parse import unquote

import psycopg2
from psycopg2.extras import RealDictCursor
import paho.mqtt.client as mqtt

from agv_manager import AGVManager
from fastapi import FastAPI
from map_manager import MapManager
>>>>>>> 83554841fd7d3c2ff850fed616c1ce8043939574

# ==========================
# MQTT Configuration
# ==========================
<<<<<<< HEAD
BROKER = "192.168.88.253"
PORT = 1883
QOS = 0
UAGV_INTERFACE_NAME = "uagv"
UAGV_MAJOR_VERSION = "v3"

agv_manager = AGVManager()
=======
BROKER = "192.168.0.61"
PORT = 1883
QOS = 0

agv_manager = AGVManager()
map_manager = MapManager()

# ==========================
# APP REFERENCE (FIX import main)
# ==========================
_mqtt_app = None


def set_app(app: FastAPI):
    global _mqtt_app
    _mqtt_app = app


def get_app():
    if _mqtt_app is None:
        raise RuntimeError("MQTT app chưa được set. Hãy gọi set_app(app) từ main.py trước start_mqtt().")
    return _mqtt_app

>>>>>>> 83554841fd7d3c2ff850fed616c1ce8043939574

# ==========================
# ALERT STATE (assistant)
# ==========================
ALERT_COOLDOWN_SEC = 60
BATTERY_DROP_PERCENT = 5.0
BATTERY_DROP_WINDOW_SEC = 600
STUCK_DISTANCE_THRESHOLD = 0.05
STUCK_COUNT_THRESHOLD = 5

_last_battery = {}
_last_pos = {}
_stuck_count = {}
_last_alert_ts = {}
_last_error_signature = {}
<<<<<<< HEAD
_last_state_log_signature = {}


def _normalize_node_id(value) -> str:
    text = str(value or "").strip()
    if len(text) >= 2 and text[0] in {"N", "n"} and text[1:].isdigit():
        return text[1:]
    return text

=======

# ==========================
# PostgreSQL Configuration
# ==========================
PG_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "Warehouse",
    "user": "postgres",
    "password": "ducmanh1801",
}

_pg_conn = None

def debug_pg_target():
    conn = _get_pg_conn()
    if not conn:
        return

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT current_database() AS db, current_schema() AS schema")
            print(f"[DB] Current target: {cur.fetchone()}")

            cur.execute("""
                SELECT table_schema, table_name
                FROM information_schema.tables
                WHERE table_name IN ('agv_map_points', 'BoxDeliveryHistories')
                ORDER BY table_schema, table_name
            """)
            rows = cur.fetchall()
            print(f"[DB] Visible tables: {rows}")
    except Exception as e:
        print(f"[DB] debug_pg_target failed: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
# ==========================
# Mapping files
# ==========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CAMERA_PICK_MAP_FILE = os.path.join(BASE_DIR, "camera_pick_map.json")
TEAM_DROP_MAP_FILE = os.path.join(BASE_DIR, "team_drop_map.json")

# ==========================
# DISPATCH STATE
# ==========================
_pending_drop_orders = {}   # agv_id -> {pickup_node, drop_order, box_code, to_team, created_at}
_last_dispatch_box = {}     # box_code -> timestamp
DISPATCH_DEBOUNCE_SEC = 10


# ==========================
# CONFIG / DB HELPERS
# ==========================
def load_json_file(path: str) -> dict:
    try:
        if not os.path.exists(path):
            print(f"[CFG] File not found: {path}")
            return {}
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception as e:
        print(f"[CFG] Failed to load {path}: {e}")
        return {}


def get_camera_pick_map() -> dict:
    return load_json_file(CAMERA_PICK_MAP_FILE)


def get_team_drop_map() -> dict:
    return load_json_file(TEAM_DROP_MAP_FILE)


def _get_pg_conn():
    global _pg_conn
    try:
        if _pg_conn is None or _pg_conn.closed != 0:
            _pg_conn = psycopg2.connect(
                host=PG_CONFIG["host"],
                port=PG_CONFIG["port"],
                dbname=PG_CONFIG["dbname"],
                user=PG_CONFIG["user"],
                password=PG_CONFIG["password"]
            )
        return _pg_conn
    except Exception as e:
        print(f"[DB] Cannot connect PostgreSQL: {e}")
        return None


def lookup_to_team_by_boxcode(box_code: str) -> str | None:
    """
    Lấy ToTeam mới nhất theo BoxCode từ BoxDeliveryHistories.
    """
    conn = _get_pg_conn()
    if not conn:
        return None

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT "ToTeam"
                FROM "BoxDeliveryHistories"
                WHERE "BoxCode" = %s
                ORDER BY "CreatedAt" DESC
                LIMIT 1
            """, (box_code,))
            row = cur.fetchone()
            return row["ToTeam"] if row and row.get("ToTeam") is not None else None
    except Exception as e:
        print(f"[DB] Query failed: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
        return None

def resolve_map_id_sync(raw_map: str) -> str | None:
    """
    Chuyển đổi raw_map (mapCurrent hoặc map_id từ AGV) thành map_id thật trong database.
    Gọi đồng bộ từ thread MQTT.
    """
    raw_map = str(raw_map or "").strip()
    if not raw_map:
        return None

    try:
        app = get_app()
        loop = getattr(app.state, "loop", None)
        pool = getattr(app.state, "db_pool", None)

        if not loop or not loop.is_running() or pool is None:
            return raw_map

        fut = asyncio.run_coroutine_threadsafe(
            map_manager.resolve_map_id(pool, raw_map),
            loop
        )
        resolved = fut.result(timeout=5)
        return str(resolved).strip() if resolved else raw_map
    except Exception as e:
        print(f"[DB] resolve_map_id_sync thất bại cho raw_map={raw_map}: {e}")
        return raw_map

def build_pickup_name_candidates(conv_id: str) -> list[str]:
    """
    Tạo danh sách tên pickup có thể khớp từ conv_id.
    Ví dụ:
    conv01 → ["conv01", "Conveyor01", "Conveyor1", "CONVEYOR01", "CONVEYOR1"]
    conv1  → ["conv1", "Conveyor1", "Conveyor01", "CONVEYOR1", "CONVEYOR01"]
    """
    conv_id = str(conv_id or "").strip()
    candidates = []

    if conv_id:
        candidates.append(conv_id)

    m = re.search(r"(\d+)$", conv_id, re.IGNORECASE)
    if m:
        num = m.group(1)
        candidates.extend([
            f"Conveyor{num}",
            f"Conveyor{num.zfill(2)}",
            f"CONVEYOR{num}",
            f"CONVEYOR{num.zfill(2)}",
        ])

    seen = set()
    result = []
    for x in candidates:
        k = x.lower()
        if k not in seen:
            seen.add(k)
            result.append(x)
    return result

def find_named_node_with_action(map_id: str, candidates: list[str]) -> dict | None:
    """
    Tìm node theo map_id và danh sách tên có thể trong agv_map_points.
    Trả về:
    {
        "node_id": "...",
        "name": "...",
        "action": {...} | None
    }
    """
    conn = _get_pg_conn()
    if not conn:
        return None

    map_id = str(map_id or "").strip()
    if not map_id or not candidates:
        return None

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            for name in candidates:
                cur.execute("""
                    SELECT name_id, name, action
                    FROM agv_map_points
                    WHERE CAST(map_id AS TEXT) = %s
                      AND (
                            LOWER(TRIM(COALESCE(name, ''))) = LOWER(TRIM(%s))
                         OR LOWER(TRIM(COALESCE(name_id, ''))) = LOWER(TRIM(%s))
                      )
                    LIMIT 1
                """, (map_id, name, name))
                row = cur.fetchone()
                if row and row.get("name_id") is not None:
                    return {
                        "node_id": str(row["name_id"]).strip(),
                        "name": row.get("name"),
                        "action": row.get("action"),
                    }
        return None
    except Exception as e:
        print(f"[DB] find_named_node_with_action thất bại | map_id={map_id} | candidates={candidates} | lỗi={e}")
        try:
            conn.rollback()
        except Exception:
            pass
        return None
def get_default_action_from_node(node_info: dict | None, fallback: str) -> str:
    """
    Lấy action.defaultAction từ action jsonb nếu có.
    Nếu không có thì trả về giá trị fallback.
    """
    if not node_info:
        return fallback

    action = node_info.get("action")
    if isinstance(action, dict):
        value = str(action.get("defaultAction") or "").strip().upper()
        if value:
            return value

    return fallback

def build_drop_name_candidates(to_team: str) -> list[str]:
    """
    Tạo danh sách tên drop có thể match từ ToTeam.
    Ví dụ:
    'Assembly A' → ['Assembly A', 'AssemblyA']
    """
    to_team = str(to_team or "").strip()
    candidates = []

    if to_team:
        candidates.append(to_team)

    compact = re.sub(r"\s+", "", to_team)
    if compact and compact.lower() != to_team.lower():
        candidates.append(compact)

    seen = set()
    result = []
    for x in candidates:
        k = x.lower()
        if k not in seen:
            seen.add(k)
            result.append(x)
    return result

def build_charge_name_candidates() -> list[str]:
    """
    Danh sách tên node có thể dùng làm trạm sạc.
    Ưu tiên match theo name hoặc name_id trong agv_map_points.
    """
    raw = [
        "CHARGE",
        "Charge",
        "CHARGING",
        "Charging",
        "SAC",
        "Sạc",
        "TRAM SAC",
        "Trạm sạc",
        "CHARGE_01",
        "CHARGER",
    ]

    seen = set()
    result = []
    for x in raw:
        k = x.strip().lower()
        if k and k not in seen:
            seen.add(k)
            result.append(x)
    return result


def build_wait_name_candidates() -> list[str]:
    """
    Danh sách tên node có thể dùng làm khu chờ.
    """
    raw = [
        "WAIT",
        "Wait",
        "WAITING",
        "Waiting",
        "CHO",
        "Chờ",
        "KHU CHO",
        "Khu chờ",
        "WAIT_01",
        "PARK",
        "PARKING",
    ]

    seen = set()
    result = []
    for x in raw:
        k = x.strip().lower()
        if k and k not in seen:
            seen.add(k)
            result.append(x)
    return result

def get_agv_runtime_info(agv_id: str) -> dict:
    """
    Lấy thông tin runtime cần thiết để điều hướng AGV:
    - current_node
    - raw_map
    - resolved_map_id
    """
    agv_state = agv_manager.get_agv(agv_id) or {}

    current_node = str(agv_state.get("lastNodeId") or "").strip() or None

    raw_map = (
        agv_state.get("map_id")
        or agv_state.get("mapCurrent")
        or ""
    )
    raw_map = str(raw_map).strip()

    resolved_map_id = resolve_map_id_sync(raw_map) if raw_map else None

    return {
        "agv_state": agv_state,
        "current_node": current_node,
        "raw_map": raw_map,
        "resolved_map_id": resolved_map_id,
    }


def resolve_special_target_node(agv_id: str, target_type: str) -> dict:
    """
    Tìm node đặc biệt theo loại:
    - charge
    - wait

    Trả về:
    {
        "node_id": "...",
        "name": "...",
        "action": {...} | None,
        "resolved_map_id": "..."
    }
    """
    info = get_agv_runtime_info(agv_id)
    resolved_map_id = info["resolved_map_id"]

    if not resolved_map_id:
        raise ValueError(f"AGV {agv_id} chưa có map hiện tại để tìm node {target_type}")

    target_type = str(target_type or "").strip().lower()
    if target_type == "charge":
        candidates = build_charge_name_candidates()
    elif target_type == "wait":
        candidates = build_wait_name_candidates()
    else:
        raise ValueError(f"Loại target không hợp lệ: {target_type}")

    node_info = find_named_node_with_action_via_pool(resolved_map_id, candidates)
    if not node_info or not node_info.get("node_id"):
        raise ValueError(
            f"Không tìm thấy node {target_type} trong map {resolved_map_id} | candidates={candidates}"
        )

    return {
        "node_id": str(node_info["node_id"]).strip(),
        "name": node_info.get("name"),
        "action": node_info.get("action"),
        "resolved_map_id": resolved_map_id,
    }

def send_agv_to_special_target(agv_id: str, target_type: str) -> dict:
    """
    Gửi AGV tới node đặc biệt:
    - charge: đi tới trạm sạc
    - wait: đi tới khu chờ

    Trả về dict để API trả lại cho frontend.
    """
    target_type = str(target_type or "").strip().lower()
    if target_type not in ["charge", "wait"]:
        raise ValueError("target_type phải là 'charge' hoặc 'wait'")

    info = get_agv_runtime_info(agv_id)
    current_node = info["current_node"]
    raw_map = info["raw_map"]
    resolved_map_id = info["resolved_map_id"]

    if not raw_map:
        raise ValueError(f"AGV {agv_id} chưa có mapCurrent/map_id")

    target_info = resolve_special_target_node(agv_id, target_type)
    target_node = target_info["node_id"]

    print(
        f"[SPECIAL] AGV={agv_id} | target_type={target_type} | "
        f"current_node={current_node} | raw_map={raw_map} | "
        f"resolved_map_id={resolved_map_id} | target_node={target_node}"
    )

    route_nodes, route_edges = plan_path_for_order(agv_id, current_node, target_node)

    # Hiện tại chỉ di chuyển tới node đặc biệt, chưa gắn action cuối
    order = build_order_with_path(
        agv_id,
        route_nodes,
        route_edges,
        end_action_type=None
    )

    send_generated_order(agv_id, order)

    return {
        "success": True,
        "agv_id": agv_id,
        "target_type": target_type,
        "target_node": target_node,
        "target_name": target_info.get("name"),
        "map_id": resolved_map_id,
        "orderId": order.get("orderId"),
        "path": [str(n.get("nodeId")) for n in route_nodes],
    }

async def find_named_node_with_action_async(pool, map_id: str, candidates: list[str]) -> dict | None:
    """
    Tìm node theo map_id và danh sách tên có thể trong agv_map_points
    bằng asyncpg pool đúng của hệ map.
    """
    map_id = str(map_id or "").strip()
    if not map_id or not candidates:
        return None

    try:
        async with pool.acquire() as conn:
            for name in candidates:
                row = await conn.fetchrow(
                    """
                    SELECT name_id, name, action
                    FROM agv_map_points
                    WHERE CAST(map_id AS TEXT) = $1
                      AND (
                            LOWER(TRIM(COALESCE(name, ''))) = LOWER(TRIM($2))
                         OR LOWER(TRIM(COALESCE(name_id, ''))) = LOWER(TRIM($2))
                      )
                    LIMIT 1
                    """,
                    map_id,
                    name,
                )
                if row and row.get("name_id") is not None:
                    return {
                        "node_id": str(row["name_id"]).strip(),
                        "name": row.get("name"),
                        "action": row.get("action"),
                    }
        return None
    except Exception as e:
        print(f"[DB] find_named_node_with_action_async thất bại | map_id={map_id} | candidates={candidates} | lỗi={e}")
        return None

def find_named_node_with_action_via_pool(map_id: str, candidates: list[str]) -> dict | None:
    """
    Wrapper sync để gọi hàm async tra node map bằng app.state.db_pool.
    """
    try:
        app = get_app()
        loop = getattr(app.state, "loop", None)
        pool = getattr(app.state, "db_pool", None)

        if not loop or not loop.is_running() or pool is None:
            print("[DB] db_pool hoặc event loop chưa sẵn sàng")
            return None

        fut = asyncio.run_coroutine_threadsafe(
            find_named_node_with_action_async(pool, map_id, candidates),
            loop
        )
        return fut.result(timeout=5)
    except Exception as e:
        print(f"[DB] find_named_node_with_action_via_pool thất bại | map_id={map_id} | candidates={candidates} | lỗi={e}")
        return None

def find_named_node_in_db(map_id: str, candidates: list[str]) -> str | None:
    """
    Tìm node trong agv_map_points theo map_id và danh sách tên có thể.
    Ưu tiên match theo name, fallback theo name_id.
    """
    conn = _get_pg_conn()
    if not conn:
        return None

    map_id = str(map_id or "").strip()
    if not map_id or not candidates:
        return None

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            for name in candidates:
                cur.execute("""
                    SELECT name_id, name
                    FROM agv_map_points
                    WHERE CAST(map_id AS TEXT) = %s
                      AND (
                            LOWER(TRIM(COALESCE(name, ''))) = LOWER(TRIM(%s))
                         OR LOWER(TRIM(COALESCE(name_id, ''))) = LOWER(TRIM(%s))
                      )
                    LIMIT 1
                """, (map_id, name, name))
                row = cur.fetchone()
                if row and row.get("name_id") is not None:
                    return str(row["name_id"]).strip()
        return None
    except Exception as e:
        print(f"[DB] find_named_node_in_db thất bại | map_id={map_id} | candidates={candidates} | lỗi={e}")
        try:
            conn.rollback()
        except Exception:
            pass
        return None
# QR / DISPATCH HELPERS
# ==========================
def extract_box_code(qr_text: str) -> str:
    """
    Trích BoxCode từ chuỗi QR có thể gồm URL + newline + code.
    Xử được cả trường hợp có URL encode như %0A.
    """
    if not qr_text:
        return ""

    s = unquote(qr_text).strip()

    lines = [ln.strip() for ln in s.splitlines() if ln.strip()]
    candidate = lines[-1] if lines else s

    m = re.search(r"/box/([^/?#\s]+)", candidate)
    if m:
        candidate = m.group(1)

    candidate = candidate.split("?", 1)[0].split("#", 1)[0].strip().strip("/")
    candidate = re.split(r"\s+", candidate)[-1]
    return candidate


def can_dispatch_box(box_code: str, cooldown: int = DISPATCH_DEBOUNCE_SEC) -> bool:
    now = time.time()
    last = _last_dispatch_box.get(box_code, 0)
    if now - last < cooldown:
        return False
    _last_dispatch_box[box_code] = now
    return True


def pick_available_agv() -> str | None:
    """
    TODO: Thay bằng logic chọn AGV thật.
    Tạm thời hardcode để test.
    """
    return "QR-SLAM-AGV-001"


async def plan_path_async(agv_id: str, start_node_id: str | None, end_node_id: str):
    """
    Dùng MapManager thật để tính path từ start -> end.

    Logic:
    1. Lấy map hiện tại của AGV (map_id/mapCurrent)
    2. Resolve map name -> map id thật trong bảng agv_maps
    3. Load graph từ DB bằng map_id thật
    4. Nếu không có start_node_id thì fallback nearest node theo x,y của AGV
    5. Tính shortest path
    6. Convert sang route_nodes / route_edges để build order VDA5050
    """
    app = get_app()
    pool = app.state.db_pool

    if pool is None:
        raise ValueError("Database pool chưa khởi tạo")

    agv_state = agv_manager.get_agv(agv_id) or {}

    # Lấy map hiện tại AGV
    raw_map = (
        agv_state.get("map_id")
        or agv_state.get("mapCurrent")
        or ""
    )
    raw_map = str(raw_map).strip()

    if not raw_map:
        raise ValueError(f"AGV {agv_id} chưa có map_id/mapCurrent nên không thể tính path")

    # Resolve map name -> map id thật trong DB
    resolved_map_id = await map_manager.resolve_map_id(pool, raw_map)
    if not resolved_map_id:
        raise ValueError(f"Không resolve được map_id từ raw_map='{raw_map}'")

    map_id = str(resolved_map_id).strip()
    print(f"[PLAN] raw_map={raw_map} -> resolved_map_id={map_id}")

    # Load graph
    await map_manager.load_from_db(pool, map_id)

    print(
        f"[PLAN] graph loaded | map_id={map_id} | "
        f"nodes={map_manager.graph.number_of_nodes()} | "
        f"edges={map_manager.graph.number_of_edges()}"
    )

    if map_manager.graph.number_of_nodes() == 0:
        raise ValueError(f"Graph rỗng sau khi load map_id={map_id}")

    # Xác định start node
    start_node = str(start_node_id).strip() if start_node_id else ""
    end_node = str(end_node_id).strip()

    if not end_node:
        raise ValueError("end_node_id đang rỗng")

    # Nếu không có start node rõ ràng thì lấy nearest node theo x,y
    if not start_node:
        x = float(agv_state.get("x", 0.0))
        y = float(agv_state.get("y", 0.0))
        nearest = map_manager.nearest_node(x, y)
        if not nearest:
            raise ValueError(
                f"Không tìm được nearest node cho AGV {agv_id} tại ({x}, {y})"
            )
        start_node = str(nearest)
        print(f"[PLAN] start_node fallback by nearest: {start_node}")
    else:
        print(f"[PLAN] start_node from AGV/current: {start_node}")

    print(f"[PLAN] end_node: {end_node}")

    # Tính đường đi ngắn nhất
    node_path = map_manager.shortest_path(start_node, end_node)
    if not node_path:
        raise ValueError(f"Không tìm được đường đi từ {start_node} -> {end_node}")

    print(f"[PLAN] shortest path: {' -> '.join(map(str, node_path))}")

    # Convert sang route_nodes / route_edges
    route_nodes = []
    route_edges = []

    for node_id in node_path:
        point = map_manager.points.get(str(node_id))
        if not point:
            raise ValueError(f"Thiếu tọa độ cho node {node_id} trong agv_map_points")

        px, py = point
        route_nodes.append({
            "nodeId": str(node_id),
            "nodePosition": {
                "x": float(px),
                "y": float(py),
                "theta": 0.0
            }
        })

    for i in range(len(node_path) - 1):
        src = str(node_path[i])
        dst = str(node_path[i + 1])

        route_edges.append({
            "edgeId": f"{src}_to_{dst}",
            "startNodeId": src,
            "endNodeId": dst
        })

    print(
        f"[PLAN] route ready | route_nodes={len(route_nodes)} | route_edges={len(route_edges)}"
    )

    return route_nodes, route_edges

def plan_path_for_order(agv_id: str, start_node_id: str | None, end_node_id: str):
    """
    Gọi async planner từ thread MQTT.
    """
    app = get_app()
    loop = getattr(app.state, "loop", None)
    if not loop or not loop.is_running():
        raise RuntimeError("FastAPI event loop chưa sẵn sàng")

    fut = asyncio.run_coroutine_threadsafe(
        plan_path_async(agv_id, start_node_id, end_node_id),
        loop
    )
    return fut.result(timeout=10)


def build_order_with_path(agv_id: str, route_nodes: list, route_edges: list, end_action_type: str | None = None):
    """
    Build order theo format bạn đang test thành công:
    - sequenceId xen kẽ: node 0,2,4 và edge 1,3,5
    - action đặt ở node cuối nếu có
    """
    now_iso = datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    order_id = str(uuid.uuid4())
    header_id = int(time.time() * 1000) % (2**32)

    order = {
        "headerId": header_id,
        "timestamp": now_iso,
        "version": "2.0",
        "manufacturer": "TNG:TOT",
        "serialNumber": agv_id,
        "orderId": order_id,
        "orderUpdateId": 0,
        "orderStatus": "NEW",
        "nodes": [],
        "edges": [],
    }

    seq = 0
    for n in route_nodes:
        node = {
            "nodeId": str(n["nodeId"]),
            "sequenceId": seq,
            "released": True,
            "nodePosition": n.get("nodePosition") or {},
            "actions": []
        }
        order["nodes"].append(node)
        seq += 2

    seq = 1
    for e in route_edges:
        edge = {
            "edgeId": e.get("edgeId") or f'{e["startNodeId"]}_to_{e["endNodeId"]}',
            "sequenceId": seq,
            "startNodeId": str(e["startNodeId"]),
            "endNodeId": str(e["endNodeId"]),
            "released": True,
            "actions": [],
            "trajectory": {}
        }
        order["edges"].append(edge)
        seq += 2

    if end_action_type and order["nodes"]:
        end_node_id = str(route_nodes[-1]["nodeId"])
        order["nodes"][-1]["actions"].append({
            "actionType": end_action_type,
            "actionId": f"{end_action_type.lower()}_{end_node_id}_{int(time.time())}",
            "blockingType": "HARD",
            "actionParameters": []
        })

    return order


def send_generated_order(agv_id: str, order: dict):
    topic = f"vda5050/agv/{agv_id}/order"
    payload_str = json.dumps(order, ensure_ascii=False)
    result = client.publish(topic, payload_str, qos=1)
    print(f"[MQTT] AUTO ORDER SENT -> {agv_id} | orderId={order.get('orderId')} | status={result.rc}")
    print(json.dumps(order, indent=2, ensure_ascii=False))


def has_finished_action(payload: dict, expected_node_id: str, expected_action_type: str) -> bool:
    """
    Kiểm tra trong nodeStates xem action tại node mong muốn đã FINISHED chưa.
    """
    node_states = payload.get("nodeStates") or []
    expected_node_id = str(expected_node_id)
    expected_action_type = str(expected_action_type).upper()

    for ns in node_states:
        node_id = str(ns.get("nodeId") or "")
        if node_id != expected_node_id:
            continue

        actions = ns.get("actions") or []
        for act in actions:
            action_type = str(act.get("actionType") or "").upper()
            action_status = str(act.get("actionStatus") or "").upper()

            if action_type == expected_action_type and action_status == "FINISHED":
                return True

    return False


def handle_camera_scan_message(msg):
    """
    Quy trình xử lý:
    - topic convQR/hw2602/dt/conv01/pub → lấy conv01
    - trích xuất BoxCode từ qr_data
    - tra cứu DB ngoài → ToTeam
    - chọn AGV
    - resolve map hiện tại của AGV
    - ưu tiên tìm pickup/drop từ DB
    - nếu không có mới fallback JSON
    """
    topic_parts = msg.topic.split("/")

    # hỗ trợ cả convQR/... và agv/convQR/...
    if len(topic_parts) == 6 and topic_parts[0] == "agv":
        topic_parts = topic_parts[1:]

    if len(topic_parts) != 5 or topic_parts[0] != "convQR" or topic_parts[4] != "pub":
        return

    conv_id = topic_parts[3]
    raw_text = msg.payload.decode("utf-8", errors="ignore").strip()
    print(f"[CAM] Nội dung payload: {raw_text}")

    try:
        data = json.loads(raw_text)
    except Exception:
        print("[CAM] JSON không hợp lệ")
        return

    print(f"[CAM] Dữ liệu đã parse: {data}")

    qr_text = (data.get("qr_data") or "").strip()
    if not qr_text:
        print("[CAM] Thiếu qr_data")
        return

    box_code = extract_box_code(qr_text)
    print(f"[CAM] BoxCode trích xuất: {box_code!r}")

    if not box_code:
        print(f"[CAM] Không thể trích xuất BoxCode từ qr_data: {qr_text!r}")
        return

    if not can_dispatch_box(box_code):
        print(f"[DISPATCH] Bỏ qua scan trùng lặp cho {box_code}")
        return

    # 1) Tra cứu DB ngoài → ToTeam
    to_team = lookup_to_team_by_boxcode(box_code)
    if to_team is None:
        print(f"[ROUTE] BoxCode={box_code} → ToTeam: (KHÔNG TÌM THẤY)")
        return

    to_team = str(to_team).strip()
    print(f"[ROUTE] BoxCode={box_code} → ToTeam: {to_team}")

    # 2) Chọn AGV
    agv_id = pick_available_agv()
    if not agv_id:
        print("[DISPATCH] Không có AGV nào rảnh")
        return

    agv_state = agv_manager.get_agv(agv_id) or {}
    current_node = str(agv_state.get("lastNodeId") or "").strip() or None

    raw_map = (
        agv_state.get("map_id")
        or agv_state.get("mapCurrent")
        or ""
    )
    raw_map = str(raw_map).strip()
    resolved_map_id = resolve_map_id_sync(raw_map) if raw_map else None

    print(
        f"[DISPATCH] AGV={agv_id} | current_node={current_node} | "
        f"raw_map={raw_map} | resolved_map_id={resolved_map_id}"
    )

    # 3) Pickup node: ưu tiên DB
    pickup_candidates = build_pickup_name_candidates(conv_id)
    pickup_node_info = None
    pickup_node = None

    if resolved_map_id:
        pickup_node_info = find_named_node_with_action_via_pool(resolved_map_id, pickup_candidates)
        if pickup_node_info:
            pickup_node = pickup_node_info["node_id"]
        print(f"[DISPATCH] pickup_candidates={pickup_candidates} → pickup_node(DB)={pickup_node}")

    if not pickup_node:
        camera_pick_map = get_camera_pick_map()
        pickup_node = camera_pick_map.get(conv_id)
        if pickup_node:
            print(f"[DISPATCH] pickup_node fallback từ JSON: conv_id={conv_id} → {pickup_node}")

    if not pickup_node:
        print(f"[CAM] Không có ánh xạ pickup cho conv_id={conv_id}")
        return

    pickup_action_type = get_default_action_from_node(pickup_node_info, "PICKUP")

    # 4) Drop node: ưu tiên DB
    drop_candidates = build_drop_name_candidates(to_team)
    drop_node_info = None
    drop_node = None

    if resolved_map_id:
        drop_node_info = find_named_node_with_action_via_pool(resolved_map_id, drop_candidates)
        if drop_node_info:
            drop_node = drop_node_info["node_id"]
        print(f"[DISPATCH] drop_candidates={drop_candidates} → drop_node(DB)={drop_node}")

    if not drop_node:
        team_drop_map = get_team_drop_map()
        drop_node = team_drop_map.get(to_team)
        if drop_node:
            print(f"[DISPATCH] drop_node fallback từ JSON: ToTeam={to_team} → {drop_node}")

    if not drop_node:
        print(f"[ROUTE] Không có ánh xạ drop cho ToTeam={to_team}, fallback về node 14")
        drop_node = "14"

    drop_action_type = get_default_action_from_node(drop_node_info, "DROP")

    print(
        f"[DISPATCH] KẾT QUẢ CUỐI | AGV={agv_id} | current_node={current_node} | "
        f"pickup_node={pickup_node} | pickup_action={pickup_action_type} | "
        f"drop_node={drop_node} | drop_action={drop_action_type}"
    )

    try:
        pickup_nodes, pickup_edges = plan_path_for_order(agv_id, current_node, pickup_node)
        pickup_order = build_order_with_path(
            agv_id,
            pickup_nodes,
            pickup_edges,
            end_action_type=pickup_action_type
        )

        drop_nodes, drop_edges = plan_path_for_order(agv_id, pickup_node, drop_node)
        drop_order = build_order_with_path(
            agv_id,
            drop_nodes,
            drop_edges,
            end_action_type=drop_action_type
        )
    except Exception as e:
        print(f"[DISPATCH] Lập kế hoạch đường đi thất bại: {e}")
        return

    _pending_drop_orders[agv_id] = {
        "pickup_node": str(pickup_node),
        "drop_order": drop_order,
        "box_code": box_code,
        "to_team": to_team,
        "created_at": time.time()
    }

    print(f"[DISPATCH] Đã lưu lệnh drop chờ xử lý cho AGV={agv_id}, box={box_code}")

    print("[DISPATCH] Lệnh PICKUP đã tạo:")
    print(json.dumps(pickup_order, indent=2, ensure_ascii=False))

    print("[DISPATCH] Lệnh DROP đã tạo:")
    print(json.dumps(drop_order, indent=2, ensure_ascii=False))

    send_generated_order(agv_id, pickup_order)
# ==========================
# ALERT HELPERS
# ==========================
>>>>>>> 83554841fd7d3c2ff850fed616c1ce8043939574
def _should_emit(agv_id: str, key: str, now_ts: float, cooldown: int = ALERT_COOLDOWN_SEC) -> bool:
    last = _last_alert_ts.get((agv_id, key), 0)
    if now_ts - last < cooldown:
        return False
    _last_alert_ts[(agv_id, key)] = now_ts
    return True

<<<<<<< HEAD
=======

>>>>>>> 83554841fd7d3c2ff850fed616c1ce8043939574
def _emit_alert(agv_id: str, title: str, message: str, level: str = "warning"):
    app = get_app()
    ws_func = app.state.send_websocket_update
    if not ws_func:
        return
<<<<<<< HEAD
=======

>>>>>>> 83554841fd7d3c2ff850fed616c1ce8043939574
    payload = {
        "type": "assistant_alert",
        "agv_id": agv_id,
        "level": level,
        "title": title,
        "message": message,
        "timestamp": datetime.datetime.now().isoformat()
    }
<<<<<<< HEAD
    async def send_ws():
        await ws_func(payload)
    run_async_in_thread(send_ws())

=======

    async def send_ws():
        await ws_func(payload)

    run_async_in_thread(send_ws())


>>>>>>> 83554841fd7d3c2ff850fed616c1ce8043939574
def detect_alerts(agv_id: str, state_data: dict):
    now_ts = time.time()

    # AGV error reported
    errors = state_data.get("error") or []
    if errors:
        signature = json.dumps(errors, sort_keys=True, ensure_ascii=False)
        if _last_error_signature.get(agv_id) != signature and _should_emit(agv_id, "error", now_ts):
            first = errors[0] if isinstance(errors, list) else {}
            err_msg = first.get("errorDescription") or first.get("errorLevel") or "AGV reported error"
            _emit_alert(agv_id, "AGV error", f"{agv_id}: {err_msg}", level="error")
        _last_error_signature[agv_id] = signature

    # Map missing
    if not state_data.get("map_id"):
        if _should_emit(agv_id, "map_missing", now_ts):
            _emit_alert(agv_id, "Map missing", f"{agv_id}: map_id is empty", level="warning")

    # Battery drop too fast
    battery = (state_data.get("batteryState") or {}).get("batteryCharge")
    if isinstance(battery, (int, float)):
        last = _last_battery.get(agv_id)
        if last:
            prev_batt, prev_ts = last
            drop = prev_batt - float(battery)
            if drop >= BATTERY_DROP_PERCENT and (now_ts - prev_ts) <= BATTERY_DROP_WINDOW_SEC:
                if _should_emit(agv_id, "battery_drop", now_ts):
                    _emit_alert(
                        agv_id,
                        "Battery drop",
                        f"{agv_id}: battery dropped {drop:.1f}% in {int(now_ts - prev_ts)}s",
                        level="warning",
                    )
        _last_battery[agv_id] = (float(battery), now_ts)

    # Stuck detection while order is active
    order_id = state_data.get("orderId")
    x = float(state_data.get("x", 0.0))
    y = float(state_data.get("y", 0.0))
    if order_id:
        last_pos = _last_pos.get(agv_id)
        if last_pos:
            px, py = last_pos
            dist = math.hypot(x - px, y - py)
            if dist < STUCK_DISTANCE_THRESHOLD:
                _stuck_count[agv_id] = _stuck_count.get(agv_id, 0) + 1
            else:
                _stuck_count[agv_id] = 0
            if _stuck_count.get(agv_id, 0) >= STUCK_COUNT_THRESHOLD:
                if _should_emit(agv_id, "stuck", now_ts):
                    _emit_alert(agv_id, "Possible stuck", f"{agv_id}: no movement for a while", level="warning")
                _stuck_count[agv_id] = 0
        _last_pos[agv_id] = (x, y)
    else:
        _stuck_count[agv_id] = 0
        _last_pos[agv_id] = (x, y)

<<<<<<< HEAD
# ==========================
# ==========================
# LẤY APP TỪ MAIN MÀ KHÔNG GÂY CIRCULAR IMPORT
# ==========================
def get_app():
    import main
    return main.app
# ==========================
# CHẠY ASYNC TRONG THREAD MQTT (FIX NO EVENT LOOP)
# ==========================
def run_async_in_thread(coro):
    """??y coroutine v? ??ng event loop ch?nh c?a FastAPI khi ?ang ? thread MQTT."""
    try:
        app = get_app()
        app_loop = getattr(app.state, "loop", None)
        if app_loop and app_loop.is_running():
            future = asyncio.run_coroutine_threadsafe(coro, app_loop)

            def _report_error(done_future):
                try:
                    done_future.result()
                except Exception as exc:
                    print(f"[MQTT] Async task failed: {exc}")

            future.add_done_callback(_report_error)
            return
    except Exception as exc:
        print(f"[MQTT] Cannot schedule on app loop, fallback to local loop: {exc}")

    new_loop = asyncio.new_event_loop()
    try:
        new_loop.run_until_complete(coro)
    finally:
        new_loop.close()
=======

# ==========================
# APP / ASYNC HELPERS
# ==========================
def run_async_in_thread(coro):
    """
    Đẩy coroutine sang event loop của FastAPI (main.py) thay vì chạy/đẻ loop trong thread MQTT.
    """
    app = get_app()
    loop = getattr(app.state, "loop", None)
    if loop and loop.is_running():
        asyncio.run_coroutine_threadsafe(coro, loop)
    else:
        asyncio.run(coro)

>>>>>>> 83554841fd7d3c2ff850fed616c1ce8043939574

# ==========================
# MQTT Event Handlers
# ==========================
def on_connect(client, userdata, flags, rc):
    print(f"[MQTT] Connected with result code {rc}")
    client.subscribe("vda5050/agv/+/state", qos=QOS)
    print("[MQTT] Subscribed: vda5050/agv/+/state")
<<<<<<< HEAD
    client.subscribe("vda5050/agv/+/instantActions", qos=QOS)
    print("[MQTT] Subscribed: vda5050/agv/+/instantActions")
    client.subscribe("vda5050/agv/+/order", qos=QOS)
    print("[MQTT] Subscribed: vda5050/agv/+/order")
    client.subscribe(f"{UAGV_INTERFACE_NAME}/{UAGV_MAJOR_VERSION}/+/+/state", qos=QOS)
    print(f"[MQTT] Subscribed: {UAGV_INTERFACE_NAME}/{UAGV_MAJOR_VERSION}/+/+/state")
    client.subscribe(f"{UAGV_INTERFACE_NAME}/{UAGV_MAJOR_VERSION}/+/+/instantActions", qos=QOS)
    print(f"[MQTT] Subscribed: {UAGV_INTERFACE_NAME}/{UAGV_MAJOR_VERSION}/+/+/instantActions")
    client.subscribe(f"{UAGV_INTERFACE_NAME}/{UAGV_MAJOR_VERSION}/+/+/order", qos=QOS)
    print(f"[MQTT] Subscribed: {UAGV_INTERFACE_NAME}/{UAGV_MAJOR_VERSION}/+/+/order")  # ĐÃ SUBSCRIBE


def _parse_topic(topic: str):
    topic_parts = topic.split("/")
    if len(topic_parts) >= 4 and topic_parts[0] == "vda5050" and topic_parts[1] == "agv":
        return topic_parts, topic_parts[2], topic_parts[3]
    if len(topic_parts) >= 5 and topic_parts[0] == UAGV_INTERFACE_NAME and topic_parts[1] == UAGV_MAJOR_VERSION:
        return topic_parts, topic_parts[3], topic_parts[4]
    return topic_parts, None, None


def on_message(client, userdata, msg):
    topic_parts, agv_id, message_kind = _parse_topic(msg.topic)

    try:
=======

    client.subscribe("vda5050/agv/+/instantActions", qos=QOS)
    print("[MQTT] Subscribed: vda5050/agv/+/instantActions")

    client.subscribe("vda5050/agv/+/order", qos=QOS)
    print("[MQTT] Subscribed: vda5050/agv/+/order")

    # Camera băng tải
    client.subscribe("convQR/+/+/+/pub", qos=QOS)
    print("[MQTT] Subscribed: convQR/+/+/+/pub")


def on_subscribe(client, userdata, mid, granted_qos):
    print(f"[MQTT] Subscribed mid={mid}, granted_qos={granted_qos}")

def build_charge_name_candidates() -> list[str]:
    return ["CHARGE", "Charge", "ChargeStation", "Trạm sạc", "Sac", "Sạc"]

def build_wait_name_candidates() -> list[str]:
    return ["WAIT", "Wait", "Waiting", "Khu chờ", "Cho", "Chờ"]

def on_message(client, userdata, msg):
    topic_parts = msg.topic.split("/")
    print(f"[MQTT] Nhận tin từ topic: {msg.topic}")
    print(f"[MQTT] Raw payload: {msg.payload!r}")

    try:
        # ✅ Handle camera topic first
                # ✅ Handle camera topic first
        if (
            (len(topic_parts) == 5 and topic_parts[0] == "convQR" and topic_parts[4] == "pub")
            or
            (len(topic_parts) == 6 and topic_parts[0] == "agv" and topic_parts[1] == "convQR" and topic_parts[5] == "pub")
        ):
            handle_camera_scan_message(msg)
            return

>>>>>>> 83554841fd7d3c2ff850fed616c1ce8043939574
        # === DECODE PAYLOAD ===
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception as e:
            print(f"[MQTT] LỖI JSON: {e} | Raw: {msg.payload[:200]}")
            return

        # === XỬ LÝ STATE ===
<<<<<<< HEAD
        if message_kind == "state" and agv_id:
=======
        if len(topic_parts) >= 4 and topic_parts[3] == "state":
            agv_id = topic_parts[2]
>>>>>>> 83554841fd7d3c2ff850fed616c1ce8043939574
            agv_ip = "from_mqtt"

            pos = payload.get("agvPosition", {}) or {}
            map_id = payload.get("mapCurrent") or pos.get("mapId") or ""

            # Mạnh tay chuẩn hóa toạ độ nhận được
            x = (
                pos.get("x")
                or pos.get("X")
                or pos.get("posX")
                or pos.get("positionX")
                or 0.0
            )
            y = (
                pos.get("y")
                or pos.get("Y")
                or pos.get("posY")
                or pos.get("positionY")
                or 0.0
            )
            theta = pos.get("theta") or pos.get("Theta") or 0.0

            state_data = {
                "headerId": payload.get("headerId"),
                "timestamp": payload.get("timestamp"),
                "version": payload.get("version"),
                "manufacturer": payload.get("manufacturer"),
                "serialNumber": payload.get("serialNumber"),
                "mapCurrent": payload.get("mapCurrent"),
                "orderId": payload.get("orderId", ""),
                "orderUpdateId": payload.get("orderUpdateId", 0),
                "lastNodeId": payload.get("lastNodeId", ""),
                "nodeStates": payload.get("nodeStates", []),
                "edgeStates": payload.get("edgeStates", []),
                "agvPosition": pos,
                "velocity": payload.get("velocity"),
                "load": payload.get("load"),
                "paused": payload.get("paused", False),
                "batteryState": payload.get("batteryState", {}),
                "error": payload.get("error", []),
                "operationMode": payload.get("operationMode", "AUTOMATIC"),
                "actionState": payload.get("actionState", {}),
                "ipaddress": agv_ip,
                "x": x,
                "y": y,
                "theta": theta,
                "map_id": str(map_id)
            }

<<<<<<< HEAD
            # CẬP NHẬT AGV
            agv_manager.update_status(agv_id, state_data)
            detect_alerts(agv_id, state_data)
            app = get_app()
            traffic_handler = getattr(app.state, "handle_traffic_state_update", None)
            if traffic_handler:
                async def sync_traffic():
                    await traffic_handler(agv_id, state_data)
                run_async_in_thread(sync_traffic())

            state_log_signature = (
                str(state_data.get("lastNodeId") or ""),
                str(state_data.get("orderId") or ""),
                bool(state_data.get("paused")),
            )
            if _last_state_log_signature.get(agv_id) != state_log_signature:
                _last_state_log_signature[agv_id] = state_log_signature
                print(
                    f"[STATE] {agv_id} | node={state_data['lastNodeId'] or '-'} "
                    f"| order={state_data['orderId'] or '-'} | paused={state_data['paused']}"
                )
=======
            state_data["last_update_ts"] = time.time()
            state_data["last_seen_mono"] = time.monotonic()
            state_data["last_update"] = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")

            # CẬP NHẬT AGV
            agv_manager.update_status(agv_id, state_data)
            detect_alerts(agv_id, state_data)

            print(f"\n[STATE] AGV {agv_id} ĐÃ CẬP NHẬT TỪ MQTT THẬT!")
            print(f"   → Node: {state_data['lastNodeId']}")
            print(f"   → Order: {state_data['orderId']}")
            print(f"   → Pin: {state_data['batteryState'].get('batteryCharge', 'N/A')}%")
            print(f"   → Vị trí: x={float(x):.3f}, y={float(y):.3f}, θ={float(theta):.3f}")
            print(f"   → Paused: {state_data['paused']}\n")

            # === Nếu pickup đã FINISHED tại pickup_node thì gửi drop_order ===
            try:
                pending = _pending_drop_orders.get(agv_id)
                if pending:
                    pickup_node = str(pending.get("pickup_node") or "")
                    current_last_node = str(state_data.get("lastNodeId") or "")

                    pickup_finished = has_finished_action(payload, pickup_node, "PICKUP")

                    if current_last_node == pickup_node and pickup_finished:
                        print(
                            f"[DISPATCH] AGV {agv_id} finished PICKUP at node {pickup_node}, sending DROP order..."
                        )
                        send_generated_order(agv_id, pending["drop_order"])
                        _pending_drop_orders.pop(agv_id, None)
            except Exception as e:
                print(f"[DISPATCH] Pending drop handling failed: {e}")
>>>>>>> 83554841fd7d3c2ff850fed616c1ce8043939574

            # === GỬI WEBSOCKET ===
            app = get_app()
            ws_func = app.state.send_websocket_update
            if ws_func:
                async def send_ws():
                    await ws_func({
                        "type": "agv_state",
                        "agv_id": agv_id,
                        "lastNodeId": state_data['lastNodeId'],
                        "orderId": state_data['orderId'],
                        "batteryCharge": state_data['batteryState'].get('batteryCharge'),
                        "x": x,
                        "y": y,
                        "theta": theta,
                        "paused": state_data['paused'],
                        "timestamp": datetime.datetime.now().isoformat()
                    })
                run_async_in_thread(send_ws())

            # === BROADCAST POSE REALTIME LÊN DASHBOARD ===
            if map_id is not None:
                try:
                    from main import broadcast_agv_pose

                    async def send_pose():
                        await broadcast_agv_pose(agv_id, float(x), float(y), float(theta), str(map_id))

                    run_async_in_thread(send_pose())
                except Exception as e:
                    print(f"[WS] Lỗi broadcast pose: {e}")

            # === GIẢI PHÓNG KHÓA ĐƯỜNG KHI ORDER KẾT THÚC ===
            try:
                order_status = (payload.get("orderStatus") or "").upper()
<<<<<<< HEAD
                all_nodes_finished = payload.get("nodeStates") and all(ns.get("nodeStatus") == "FINISHED" for ns in payload["nodeStates"])
                should_release = order_status in ["FINISHED", "CANCELED", "ABORTED"]
                # Some AGVs only report completed nodeStates for already-passed nodes while the mission is still active.
                if not should_release and all_nodes_finished and not payload.get("orderId"):
                    should_release = True
                if should_release:
                    traffic_engine = getattr(app.state, "traffic_engine", None)
                    if traffic_engine:
                        traffic_engine.release_agv(agv_id)
                    agv_manager.clear_pending_path(agv_id)
                    agv_manager.set_last_control_action(agv_id, None)
=======
                all_nodes_finished = payload.get("nodeStates") and all(
                    ns.get("nodeStatus") in ["FINISHED", "DONE"] or ns.get("state") in ["FINISHED", "DONE"]
                    for ns in payload["nodeStates"]
                )
                if order_status in ["FINISHED", "CANCELED", "ABORTED"] or all_nodes_finished:
                    from main import edge_coordinator
                    edge_coordinator.release(agv_id)
>>>>>>> 83554841fd7d3c2ff850fed616c1ce8043939574
                    print(f"[COORD] Released locks for {agv_id} | status={order_status or 'ALL_NODES_FINISHED'}")
            except Exception as e:
                print(f"[COORD] Release failed for {agv_id}: {e}")

<<<<<<< HEAD
            # === TỰ ĐỘNG GỬI ORDER UPDATE KHI HOÀN THÀNH NODE ===
            if False and payload.get("nodeStates"):
                for ns in payload["nodeStates"]:
                    if ns.get("nodeStatus") == "FINISHED":
                        node_id = ns["nodeId"]
                        print(f"[AUTO UPDATE] AGV {agv_id} HOÀN THÀNH node: {node_id}")

                        pending_path = agv_manager.get_pending_path(agv_id)
                        if pending_path and len(pending_path) > 1:
                            next_destination = pending_path[-1]
                            print(f"[AUTO UPDATE] Gửi order update đến: {next_destination}")

                            from model import MoveCommand
                            cmd = MoveCommand(agv_id=agv_id, destination=next_destination)

                            move_func = app.state.move_agv_func
                            if move_func:
                                async def send_move():
                                    await move_func(cmd)
                                run_async_in_thread(send_move())
                                print(f"[AUTO UPDATE] ĐÃ GỬI order update tự động cho {agv_id}")

        # === XỬ LÝ LỆNH MOVE TỪ MQTT EXPLORER ===
        elif message_kind == "order" and agv_id:
            if len(topic_parts) >= 2 and topic_parts[0] == "vda5050" and topic_parts[1] == "agv":
                return
            try:
                inbound_order_id = str(payload.get("orderId") or "").strip()
                inbound_update_id = int(payload.get("orderUpdateId") or 0)
                current_order = agv_manager.get_order(agv_id)
                if (
                    inbound_order_id
                    and inbound_order_id == str(current_order.get("order_id") or "").strip()
                    and inbound_update_id == int(current_order.get("order_update_id") or 0)
                ):
                    return

                nodes = payload.get("nodes") or []
                if not nodes:
                    return

                ordered_nodes = sorted(
                    [node for node in nodes if isinstance(node, dict)],
                    key=lambda item: int(item.get("sequenceId", 10**9)),
                )
                node_path = []
                for node in ordered_nodes:
                    node_id = _normalize_node_id(node.get("nodeId"))
                    if not node_id:
                        continue
                    if node_path and node_path[-1] == node_id:
                        continue
                    node_path.append(node_id)

                destination = node_path[-1] if node_path else ""
                if not destination:
                    return

                raw_map = (
                    payload.get("map_id")
                    or payload.get("mapCurrent")
                    or ((payload.get("agvPosition") or {}).get("mapId"))
                )

                from model import MoveCommand

                cmd = MoveCommand(
                    agv_id=agv_id,
                    destination=destination,
                    map_id=str(raw_map).strip() if raw_map else None,
                )
                agv_manager.set_pending_destination(agv_id, destination, str(raw_map).strip() if raw_map else None)
                agv_manager.clear_pending_path(agv_id)

                app = get_app()
                move_func = getattr(app.state, "move_agv_func", None)
                if move_func is None:
                    return

                async def send_move():
                    await move_func(cmd)

                run_async_in_thread(send_move())
                print(
                    f"[ORDER MQTT] {agv_id} | destination={destination} "
                    f"| requested_path={node_path if node_path else [destination]} "
                    f"| map={str(raw_map).strip() if raw_map else '-'}"
                )

            except Exception as e:
                print(f"[ORDER MQTT] L?i x? l? order: {e}")
                import traceback
                traceback.print_exc()

        elif "move" in topic_parts:
            agv_id = agv_id or (topic_parts[2] if len(topic_parts) > 2 else "")
=======
        # === XỬ LÝ LỆNH MOVE TỪ MQTT EXPLORER ===
        elif "move" in topic_parts:
            agv_id = topic_parts[2]
>>>>>>> 83554841fd7d3c2ff850fed616c1ce8043939574
            print(f"[MOVE COMMAND] Nhận lệnh di chuyển cho AGV: {agv_id}")

            try:
                move_data = payload
                destination = str(move_data.get("destination", "")).strip()
                if not destination:
                    print("[MOVE] LỖI: Không có destination!")
                    return

                # Lấy vị trí hiện tại
                current_state = agv_manager.get_status(agv_id)
                x = current_state.get("x", 0.0) if current_state else 0.0
                y = current_state.get("y", 0.0) if current_state else 0.0
                theta = current_state.get("theta", 0.0) if current_state else 0.0

                # Tạo order chuẩn VDA5050
                order = {
                    "headerId": int(time.time() * 1000),
                    "timestamp": datetime.datetime.now().isoformat() + "Z",
                    "version": "2.0",
                    "manufacturer": "TNG:TOT",
                    "serialNumber": agv_id,
                    "orderId": f"order_move_to_{destination}_{int(time.time())}",
                    "orderUpdateId": 0,
                    "nodes": [
                        {
                            "nodeId": "start",
                            "sequenceId": 0,
                            "released": True,
                            "nodePosition": {"x": x, "y": y, "theta": theta},
                            "actions": []
                        },
                        {
                            "nodeId": destination,
                            "sequenceId": 1,
                            "released": True,
                            "actions": [
                                {
                                    "actionId": f"move_to_{destination}",
                                    "actionType": "MOVE_TO_POSE",
                                    "blockingType": "HARD",
                                    "actionParameters": [
                                        {"key": "name", "value": destination}
                                    ]
                                }
                            ]
                        }
                    ],
                    "edges": [
                        {
                            "edgeId": f"edge_start_to_{destination}",
                            "sequenceId": 1,
                            "startNodeId": "start",
                            "endNodeId": destination,
                            "released": True,
                            "actions": []
                        }
                    ]
                }

                send_order(agv_id, order)
                print(f"[MOVE] ĐÃ GỬI order đến node {destination} thành công!")

                # Gửi thông báo realtime
                app = get_app()
                ws_func = app.state.send_websocket_update
                if ws_func:
                    async def notify():
                        await ws_func({
                            "type": "order_sent",
                            "agv_id": agv_id,
                            "destination": destination,
                            "orderId": order["orderId"]
                        })
                    run_async_in_thread(notify())

            except Exception as e:
                print(f"[MOVE] Lỗi xử lý lệnh move: {e}")
                import traceback
                traceback.print_exc()

        # === XỬ LÝ INSTANT ACTIONS ===
<<<<<<< HEAD
        elif message_kind == "instantActions" and agv_id:
=======
        elif len(topic_parts) >= 4 and topic_parts[3] == "instantActions":
            agv_id = topic_parts[2]
>>>>>>> 83554841fd7d3c2ff850fed616c1ce8043939574
            print(f"[ACTION] AGV {agv_id} nhận instantActions:")
            print(json.dumps(payload, indent=2, ensure_ascii=False))

            app = get_app()
            ws_func = app.state.send_websocket_update
            if ws_func:
                async def send_action_ws():
                    await ws_func({
                        "type": "instant_action",
                        "agv_id": agv_id,
                        "actions": payload
                    })
                run_async_in_thread(send_action_ws())

        else:
            print(f"[MQTT] Topic chưa xử lý: {msg.topic}")

    except Exception as e:
        print(f"[MQTT] LỖI XỬ LÝ TIN NHẮN: {e}")
        import traceback
        traceback.print_exc()


# ==========================
# MQTT Setup
# ==========================
client = mqtt.Client(client_id=f"server_{uuid.uuid4().hex[:8]}", clean_session=True)
client.on_connect = on_connect
client.on_message = on_message


<<<<<<< HEAD
def _publish_topic_candidates(agv_id: str, suffix: str) -> list[str]:
    agv_info = agv_manager.get_agv(agv_id, {}) or {}
    manufacturer = str(agv_info.get("manufacturer") or "tot")
    return [
        f"vda5050/agv/{agv_id}/{suffix}",
        f"{UAGV_INTERFACE_NAME}/{UAGV_MAJOR_VERSION}/{manufacturer}/{agv_id}/{suffix}",
    ]


=======
>>>>>>> 83554841fd7d3c2ff850fed616c1ce8043939574
def start_mqtt():
    try:
        client.connect(BROKER, PORT, keepalive=60)
        client.loop_start()
        print(f"[MQTT] Đã kết nối và lắng nghe trên {BROKER}:{PORT}")
    except Exception as e:
<<<<<<< HEAD
        print(f"[MQTT] LỖI KẾT NỘI BROKER: {e}")
=======
        print(f"[MQTT] LỖI KẾT NỐI BROKER: {e}")


def stop_mqtt():
    global client
    if client:
        print("[MQTT] Stopping...")
        try:
            client.disconnect()
        finally:
            client.loop_stop()
        print("[MQTT] Stopped")
>>>>>>> 83554841fd7d3c2ff850fed616c1ce8043939574


# ==========================
# ORDER & ACTION Sending
# ==========================
def send_order(agv_id: str, order: dict):
<<<<<<< HEAD
    payload_str = json.dumps(order, ensure_ascii=False)
    result_codes = []
    for topic in _publish_topic_candidates(agv_id, "order"):
        result = client.publish(topic, payload_str, qos=1)
        result_codes.append(f"{topic} rc={result.rc}")
    print(f"[ORDER OUT] {agv_id} | orderId={order.get('orderId')} | {' | '.join(result_codes)}")


def send_instant_action(agv_id: str, action_type: str):
    if action_type not in ["PAUSE", "RESUME"]:
        print(f"[MQTT] Hành động không hợp lệ: {action_type}")
        return

    action_msg = {
        "headerId": int(time.time()),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "version": "1.1",
        "manufacturer": "AGVCorp",
        "serialNumber": agv_id,
        "actions": [{
            "actionId": str(uuid.uuid4()),
            "actionType": action_type,
            "blockingType": "HARD" if action_type == "PAUSE" else "SOFT"
        }]
    }
    payload = json.dumps(action_msg, ensure_ascii=False)
    for topic in _publish_topic_candidates(agv_id, "instantActions"):
        client.publish(topic, payload, qos=0)
    print(f"[MQTT] ĐÃ GỬI instantAction → {agv_id}: {action_type}")
=======
    topic = f"vda5050/agv/{agv_id}/order"
    payload_str = json.dumps(order, ensure_ascii=False)
    result = client.publish(topic, payload_str, qos=1)
    print(f"[MQTT] ĐÃ GỬI order → {agv_id} | orderId={order.get('orderId')} | status={result.rc}")


def send_instant_action(agv_id: str, action_type: str):
    action = (action_type or "").upper().strip()

    if action == "PICK":
        action = "PICKUP"

    allowed_actions = ["PAUSE", "RESUME", "PICKUP", "CANCEL"]
    if action not in allowed_actions:
        print(f"[MQTT] Hành động không hợp lệ: {action}")
        return False

    agv_state = agv_manager.get_agv(agv_id) or {}
    manufacturer = agv_state.get("manufacturer") or "TNG:TOT"
    serial_number = agv_state.get("serialNumber") or agv_id

    topic = f"vda5050/agv/{agv_id}/instantActions"

    action_msg = {
        "headerId": int(time.time() * 1000),
        "timestamp": datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "version": "2.0",
        "manufacturer": manufacturer,
        "serialNumber": serial_number,
        "actions": [{
            "actionId": str(uuid.uuid4()),
            "actionType": action,
            "blockingType": "HARD",
            "actionParameters": []
        }]
    }

    payload = json.dumps(action_msg, ensure_ascii=False)
    result = client.publish(topic, payload, qos=1)

    print(f"[MQTT] ĐÃ GỬI instantAction → {agv_id}: {action}")
    print(f"[MQTT] Topic: {topic}")
    print(json.dumps(action_msg, indent=2, ensure_ascii=False))

    return result.rc == 0
def send_pick_action(agv_id: str):
    topic = f"vda5050/agv/{agv_id}/order"
    agv_state = agv_manager.get_agv(agv_id) or {}
    serial_number = agv_state.get("serialNumber") or agv_id
    current_node_id = agv_state.get("lastNodeId") or "CURRENT_NODE_ID"
    order_msg = {
        "orderId": f"pickup_now_{int(time.time())}",
        "orderUpdateId": int(time.time() * 1000),
        "orderStatus": "NEW",
        "version": "2.0.0",
        "serialNumber": serial_number,
        "nodes": [
            {
                "nodeId": str(current_node_id),
                "sequenceId": 0,
                "released": True,
                "actions": [
                    {
                        "actionType": "PICKUP",
                        "actionId": f"pickup_{int(time.time())}",
                        "blockingType": "HARD",
                        "actionParameters": []
                    }
                ]
            }
        ],
        "edges": []
    }
    payload = json.dumps(order_msg, ensure_ascii=False)
    client.publish(topic, payload, qos=0)
    print(f"[MQTT] SENT PICKUP ORDER -> {agv_id} | topic={topic}")

def cancel_agv_order(agv_id: str) -> dict:
    """
    Hủy lệnh hiện tại của AGV bằng instant action.
    Đồng thời xóa pending drop nếu có để tránh tự gửi tiếp DROP sau PICKUP.
    """
    agv_state = agv_manager.get_agv(agv_id) or {}
    current_order_id = str(agv_state.get("orderId") or "").strip()

    ok = send_instant_action(agv_id, "CANCEL")
    if not ok:
        raise RuntimeError(f"Gửi CANCEL thất bại cho AGV {agv_id}")

    removed_pending = _pending_drop_orders.pop(agv_id, None) is not None

    print(
        f"[CANCEL] AGV={agv_id} | current_order={current_order_id or '(empty)'} | "
        f"removed_pending_drop={removed_pending}"
    )

    return {
        "success": True,
        "agv_id": agv_id,
        "cancelled_order_id": current_order_id,
        "removed_pending_drop": removed_pending,
    }

def get_agv_special_targets(agv_id: str) -> dict:
    """
    Trả thông tin node sạc và khu chờ theo map hiện tại của AGV.
    """
    result = {
        "success": True,
        "agv_id": agv_id,
        "charge": None,
        "wait": None,
    }

    try:
        charge_info = resolve_special_target_node(agv_id, "charge")
        result["charge"] = {
            "node_id": charge_info["node_id"],
            "name": charge_info.get("name"),
            "map_id": charge_info.get("resolved_map_id"),
        }
    except Exception as e:
        result["charge_error"] = str(e)

    try:
        wait_info = resolve_special_target_node(agv_id, "wait")
        result["wait"] = {
            "node_id": wait_info["node_id"],
            "name": wait_info.get("name"),
            "map_id": wait_info.get("resolved_map_id"),
        }
    except Exception as e:
        result["wait_error"] = str(e)

    return result
>>>>>>> 83554841fd7d3c2ff850fed616c1ce8043939574
