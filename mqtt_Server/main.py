# main.py - PHIÊN BẢN HOÀN CHỈNH 2025 - REAL-TIME ĐA CLIENT + BROADCAST MỌI SỰ KIỆN
from fastapi import FastAPI, HTTPException, APIRouter, UploadFile, File, Form, Request, WebSocket
from pydantic import BaseModel
from fastapi.responses import StreamingResponse, FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import sys
import time
# Đảm bảo import được các module nội bộ khi chạy từ thư mục gốc
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
from model import MoveCommand, ActionRequest, PickRequest
import zoneinfo as ZonInfo
import base64
import os
from map_manager import MapManager
from mqtt_client import (
    start_mqtt,
    send_order,
    agv_manager,
    send_instant_action,
    send_pick_action,
    stop_mqtt,
    set_app,
    send_agv_to_special_target,
    cancel_agv_order,
    get_agv_special_targets,
)
from order_builder import build_order
from map_configure_api import router as map_config_router
from contextlib import asynccontextmanager
from pathlib import Path
import sys

# bảo đảm import được Web_UI khi chạy từ mqtt_Server
import asyncio
import uuid
import asyncpg
import io
import uvicorn
import base64
import networkx as nx
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from typing import List, Dict
import json

# ==========================
# KHỞI TẠO MANAGER
# ==========================
map_manager = MapManager()
class EdgeCoordinator:
    """
    Điều phối tránh xung đột: khóa edge theo AGV.
    Đơn giản: khóa edge 2 chiều (graph undirected) cho tới khi AGV nhận lệnh mới.
    """
    def __init__(self):
        self.edge_locks = {}  # (u,v sorted) -> agv_id
        self.agv_paths = {}   # agv_id -> list edges locked

    def _norm(self, a, b):
        return tuple(sorted((str(a), str(b))))

    def release(self, agv_id: str):
        edges = self.agv_paths.pop(agv_id, [])
        for e in edges:
            if self.edge_locks.get(e) == agv_id:
                del self.edge_locks[e]

    def lock_path(self, agv_id: str, path: list):
        self.release(agv_id)
        locked = []
        for i in range(len(path) - 1):
            e = self._norm(path[i], path[i+1])
            self.edge_locks[e] = agv_id
            locked.append(e)
        self.agv_paths[agv_id] = locked

    def find_path(self, graph, start, dest, agv_id: str):
        """Tìm đường tránh các edge đang bị khóa bởi AGV khác."""
        if graph.number_of_nodes() == 0:
            return None
        g = graph.copy()
        to_remove = [e for e, owner in self.edge_locks.items() if owner != agv_id]
        g.remove_edges_from(to_remove)
        try:
            return nx.shortest_path(g, source=str(start), target=str(dest), weight="weight")
        except Exception:
            return None

edge_coordinator = EdgeCoordinator()

class ReleaseRequest(BaseModel):
    agv_id: str
class AgvActionRequest(BaseModel):
    agv_id: str
# ==========================
# OFFLINE MONITOR
# ==========================
OFFLINE_THRESHOLD_SEC = 3
OFFLINE_CHECK_INTERVAL_SEC = 2

async def monitor_offline(stop_event: asyncio.Event):
    alerted = set()
    while not stop_event.is_set():
        try:
            agvs = agv_manager.list_agvs()
            now_mono = time.monotonic()

            for agv_id, info in agvs.items():
                last_seen = info.get("last_seen_mono")
                offline = (last_seen is None) or ((now_mono - float(last_seen)) > OFFLINE_THRESHOLD_SEC)

                if offline and agv_id not in alerted:
                    alerted.add(agv_id)
                    asyncio.create_task(broadcast_update({
                        "type": "assistant_alert",
                        "agv_id": agv_id,
                        "level": "error",
                        "title": "AGV offline",
                        "message": f"{agv_id}: no state update > {OFFLINE_THRESHOLD_SEC}s",
                        "timestamp": datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).isoformat()
                    }))

                if (not offline) and agv_id in alerted:
                    alerted.remove(agv_id)

        except Exception as e:
            print(f"[OFFLINE] Monitor error: {e}")

        await asyncio.sleep(OFFLINE_CHECK_INTERVAL_SEC)
# ==========================
# DATABASE CONFIG
# ==========================
DATABASE_URL = "postgresql://postgres:ducmanh1801@localhost:5432/TOT_AGV"
pool = None

async def create_pool():
    global pool
    print("[DB] Đang thử kết nối PostgreSQL...")
    try:
        pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=1,
            max_size=10,
            timeout=30,
            command_timeout=60
        )
        async with pool.acquire() as conn:
            result = await conn.fetchrow("SELECT current_database(), current_user, version();")
            print(f"[DB] KẾT NỐI THÀNH CÔNG!")
            print(f"    → Database: {result[0]}")
            print(f"    → User: {result[1]}")
            print(f"    → PostgreSQL: {result[2][:60]}...")
        return pool
    except Exception as e:
        print(f"[DB] KẾT NỐI THẤT BẠI!")
        print(f"    → Lỗi: {e}")
        print(f"    → URL: {DATABASE_URL}")
        print("    → GỢI Ý: docker-compose up -d db hoặc kiểm tra PostgreSQL đang chạy")
        return None

async def close_pool():
    global pool
    if pool:
        await pool.close()
        print("[DB] Đã đóng kết nối PostgreSQL")

# ==========================
# LIFESPAN – KHỞI ĐỘNG & TẮT ỨNG DỤNG
# ==========================
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[LIFESPAN] Khởi động ứng dụng...")

    # Kết nối DB
    app.state.db_pool = await create_pool()
    app.state.loop = asyncio.get_running_loop()

    set_app(app)

    # Khởi động MQTT
    print("[MQTT] Đang khởi động và chờ AGV kết nối thực tế...")
    start_mqtt()
    app.state.offline_stop = asyncio.Event()
    app.state.offline_task = asyncio.create_task(monitor_offline(app.state.offline_stop))

    print("[SYSTEM] Hệ thống đã sẵn sàng!")
    print("[INFO] AGV sẽ xuất hiện khi gửi state thật qua MQTT")
    print("[INFO] Real-time broadcast đã hoạt động – MỌI thay đổi đều thông báo đến tất cả client")

    if app.state.db_pool:
        print("[SUCCESS] TOÀN BỘ HỆ THỐNG SẴN SÀNG! (MQTT + DB + Dashboard + Real-time)")
    else:
        print("[WARNING] DB CHƯA KẾT NỐI – Chỉ có MQTT + Dashboard")

    yield
    stop_mqtt()

    print("[LIFESPAN] Đang tắt ứng dụng...")
    if getattr(app.state, "offline_stop", None):
        app.state.offline_stop.set()
    if getattr(app.state, "offline_task", None):
        try:
            await app.state.offline_task
        except Exception as e:
            print(f"[OFFLINE] Task stop error: {e}")
    await close_pool()

# ==========================
# TẠO APP
# ==========================
app = FastAPI(
    title="TOT AGV Fleet Manager",
    version="2025.11",
    lifespan=lifespan,
    docs_url="/api-agv",
    redoc_url="/api-agv-redoc",
    openapi_url="/openapi.json"
)
app.include_router(map_config_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://192.168.0.61:8050",
        #"http://192.168.0.61:8050",
        # "http://192.168.0.61:*",   # nếu muốn cho phép mọi port trên IP này (test tạm)
        # "*"                        # test tạm cho phép tất cả (không nên để lâu)
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# ==========================
# WEBSOCKET CONNECTION MANAGER + BROADCAST
# ==========================
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"[WS] Client mới kết nối – Tổng: {len(self.active_connections)} client(s)")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            print(f"[WS] Client ngắt – Còn lại: {len(self.active_connections)} client(s)")

    async def broadcast(self, message: Dict):
        if not self.active_connections:
            return
        print(f"[WS] BROADCAST → {len(self.active_connections)} client(s): {message.get('type', 'unknown')}")
        dead_connections = []
        for conn in self.active_connections:
            try:
                await conn.send_json(message)
            except Exception as e:
                print(f"[WS] Lỗi gửi đến 1 client: {e}")
                dead_connections.append(conn)
        # Xóa các client chết
        for dead in dead_connections:
            self.active_connections.remove(dead)

manager = ConnectionManager()

# Hàm tiện ích để gọi từ bất kỳ đâu
async def broadcast_update(data: dict):
    """Gửi thông báo real-time đến tất cả dashboard đang mở"""
    await manager.broadcast(data)
async def broadcast_agv_pose(agv_id: str, x: float, y: float, theta: float, map_id: str):
    """Gửi vị trí AGV đến tất cả dashboard đang mở"""
    pose_data = {
        "type": "agv_pose_update",
        "map_id": map_id,
        "poses": {
            agv_id: {
                "x": x,
                "y": y,
                "theta": theta
            }
        }
    }
    await manager.broadcast(pose_data)
    print(f"[WS] Đã broadcast pose AGV {agv_id}: ({x:.2f}, {y:.2f}) θ={theta:.1f}° | Map: {map_id}")
# Gán vào app.state để dùng ở nơi khác nếu cần
app.state.send_websocket_update = broadcast_update

app.state.broadcast_agv_pose = broadcast_agv_pose

# ==========================
# WEBSOCKET ENDPOINT
# ==========================
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Giữ kết nối sống – có thể xử lý lệnh từ client sau này
            data = await websocket.receive_text()
            # Nếu cần xử lý lệnh từ dashboard thì thêm ở đây
    except Exception as e:
        print(f"[WS] Client ngắt do lỗi: {e}")
    finally:
        manager.disconnect(websocket)

# ==========================
# PHỤC VỤ FILE TĨNH + AGV MAP UI
# ==========================
STATIC_DIR = BASE_DIR / "static"
MAP_DIR = BASE_DIR.parent / "maps"
MAP_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR, html=True), name="static")
app.mount("/maps", StaticFiles(directory=MAP_DIR), name="maps")

@app.get("/")
@app.get("/AgvMap")
@app.get("/AgvMap.html")
async def agv_map():
    return FileResponse(
        STATIC_DIR / "AgvMap.html",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )

@app.get("/home")
async def home_redirect():
    return RedirectResponse(url="http://192.168.0.61:8050/home")

# ==========================
# DEBUG ROUTES
# ==========================
@app.get("/debug/agvs")
def debug_agvs():
    return {"agvs": agv_manager.list_agvs()}

@app.get("/agv/{agv_id}")
def get_agv_status(agv_id: str):
    agv = agv_manager.get_agv(agv_id)
    if not agv:
        raise HTTPException(status_code=404, detail="AGV not found")
    return agv

# ==========================
# GỬI LỆNH DI CHUYỂN AGV (với broadcast)
# ==========================
@app.post("/order")
async def move_agv(cmd: MoveCommand):
    try:
        print(f"[API] Nhận lệnh move: {cmd.agv_id} → {cmd.destination}")
        agv = agv_manager.get_agv(cmd.agv_id)
        if not agv:
            raise HTTPException(status_code=404, detail=f"AGV '{cmd.agv_id}' không tồn tại")

        # Check connectivity (offline if no state > 1.5s)
        last_update_str = agv.get("last_update")
        is_offline = False
        if not last_update_str:
            is_offline = True
        else:
            try:
                ts = datetime.fromisoformat(last_update_str.replace("Z", "+00:00"))
                if datetime.now(timezone.utc) - ts > timedelta(seconds=3):
                    is_offline = True
            except Exception:
                is_offline = True
        if is_offline:
            raise HTTPException(status_code=503, detail="AGV mat ket noi, vui long ket noi lai de su dung")

        default_map_id = "98"
        # Ưu tiên map_id do client gửi; nếu không có thì dùng mapCurrent hoặc default
        raw_map = cmd.map_id or agv.get("mapCurrent") or agv.get("map_id") or default_map_id
        # Cho phép raw_map là name (tang_4) hoặc id (98)
        resolved_map = await map_manager.resolve_map_id(app.state.db_pool, str(raw_map))
        map_id = resolved_map or default_map_id
        if not map_id:
            raise HTTPException(status_code=400, detail="Không xác định được map_id/mapCurrent.")

        if app.state.db_pool is None:
            raise HTTPException(status_code=503, detail="Database pool not initialized")

        await map_manager.load_from_db(app.state.db_pool, str(map_id))
        if map_manager.graph.number_of_nodes() == 0 and str(map_id) != default_map_id:
            print(f"[ORDER] Graph rỗng cho map_id={map_id}, thử fallback {default_map_id}")
            await map_manager.load_from_db(app.state.db_pool, default_map_id)
            map_id = default_map_id

        start_node = agv.get("lastNodeId")
        if not start_node:
            try:
                pose_x = float(agv.get("x", 0))
                pose_y = float(agv.get("y", 0))
                nearest = map_manager.nearest_node(pose_x, pose_y)
                if nearest:
                    start_node = nearest
            except Exception:
                start_node = None
        if not start_node and map_manager.graph.number_of_nodes() > 0:
            # fallback: lấy node đầu tiên trong graph
            start_node = list(map_manager.graph.nodes)[0]
        if not start_node:
            start_node = "StartPoint"
        # ép về string để khớp với graph
        start_node = str(start_node)
        dest_node = str(cmd.destination)

        path = edge_coordinator.find_path(map_manager.graph, start_node, dest_node, cmd.agv_id)
        if not path:
            raise HTTPException(status_code=409, detail=f"Kh?ng t?m th?y ???ng (c? th? b? AGV kh?c kh?a) t? {start_node} ? {dest_node}")

        order_id = str(uuid.uuid4())
        # Build order theo full path (VDA5050)
        # chuẩn bị coords cho nodePosition
        coords_lookup = {k: (v[0], v[1], 0.0) for k, v in map_manager.points.items()} if getattr(map_manager, "points", None) else {}
        order = build_order(
            agv_id=cmd.agv_id,
            path=path,
            coords=coords_lookup,
            manufacture=agv.get("manufacturer", "TNG:TOT"),
            SerialNumber=agv.get("serialNumber", cmd.agv_id),
            version="2.0",
            order_id=order_id,
            order_update_id=0,
            horizon=None  # release toàn bộ, có thể giảm nếu muốn incremental
        )

        agv_manager.set_order(cmd.agv_id, order_id, 0)
        edge_coordinator.lock_path(cmd.agv_id, path)
        send_order(cmd.agv_id, order)

        print(f"[ORDER] THÀNH CÔNG! Order: {order_id[:8]} → {dest_node}")

        # BROADCAST: Có người vừa gửi lệnh di chuyển
        asyncio.create_task(broadcast_update({
            "type": "external_command",
            "action": "MOVE",
            "agv_id": cmd.agv_id,
            "destination": dest_node,
            "path": path,
            "order_id": order_id[:8],
            "timestamp": datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).isoformat()
        }))

        return {
            "status": "Order sent successfully",
            "orderId": order_id,
            "path": path,
            "agv": cmd.agv_id,
            "destination": dest_node
        }

    except Exception as e:
        print("[ERROR] Lỗi khi xử lý /order:")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# ==========================
# GỬI LỆNH TỨC THÌ (PAUSE/RESUME) + BROADCAST
# ==========================
@app.post("/action")
def send_action(req: ActionRequest):
    try:
        print(f"[ACTION] Gửi lệnh tức thì: {req.action_type} → AGV {req.agv_id}")
        send_instant_action(req.agv_id, req.action_type)

        # BROADCAST: Có người vừa PAUSE/RESUME
        asyncio.create_task(broadcast_update({
            "type": "external_command",
            "action": req.action_type,
            "agv_id": req.agv_id,
            "timestamp": datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).isoformat()
        }))

        return {"status": "OK", "message": f"{req.action_type} đã gửi tới {req.agv_id}"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/pick")
def send_pick(req: PickRequest):
    try:
        print(f"[PICK] Gui lenh PICKUP (topic vda5050/agv/{req.agv_id}/order) -> AGV {req.agv_id}")
        send_pick_action(req.agv_id)
        return {"status": "OK", "message": f"PICKUP da gui toi {req.agv_id} qua topic vda5050/agv/{req.agv_id}/order"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ==========================
# GIẢI PHÓNG KHÓA ĐƯỜNG KHI AGV HOÀN THÀNH (MANUAL API)
# ==========================
@app.post("/order/release")
def release_order(req: ReleaseRequest):
    """
    Gọi API này khi AGV hoàn thành order để giải phóng edge-locks.
    Có thể gọi từ callback MQTT state/feedback nếu muốn tự động.
    """
    edge_coordinator.release(req.agv_id)
    return {"status": "OK", "message": f"Đã giải phóng khóa đường cho {req.agv_id}"}

# ==========================
# UPLOAD MAP HOÀN CHỈNH + BROADCAST MAP MỚI
# ==========================

# ==========================
# LẤY DỮ LIỆU MAP (đã có)
# ==========================
@app.get("/api/map/full")
async def get_full_map(map_id: str):
    async with app.state.db_pool.acquire() as conn:
        # Map info
        map_row = await conn.fetchrow("SELECT * FROM maps WHERE map_id = $1", map_id)
        if not map_row:
            raise HTTPException(404, "Map không tồn tại")

        # Nodes
        nodes = await conn.fetch("SELECT * FROM node WHERE map = $1", map_id)
        # Edges
        straight = await conn.fetch("SELECT * FROM edge_straight WHERE map = $1", map_id)
        curve = await conn.fetch("SELECT * FROM edge_curve WHERE map = $1", map_id)

        return {
            "map": dict(map_row),
            "nodes": [dict(n) for n in nodes],
            "edge_straight": [dict(e) for e in straight],
            "edge_curve": [dict(e) for e in curve]
        }

@app.get("/api/maps/list")
async def list_maps():
    """
    SỬA LỖI: Trả về JSON list thay vì HTML Response.
    Frontend mong đợi một array JSON: [{"id": 1, "name": "Map A"}, ...]
    """
    global pool
    if pool is None:
        raise HTTPException(status_code=503, detail="Database pool not initialized")
        
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, name
                FROM agv_maps 
                ORDER BY modify_time DESC
            """)

        # CHUYỂN ĐỔI KẾT QUẢ DB SANG LIST/ARRAY JSON
        map_list = []
        for r in rows:
            # Đảm bảo trường name không null
            name = r["name"] if r["name"] is not None else f"Map ID {r['id']}" 
            map_list.append({
                "id": str(r["id"]),
                "name": name
            })
        
        # FastAPI sẽ tự động chuyển list Python này thành JSON Response hợp lệ
        return map_list
    
    except Exception as e:
        print(f"Lỗi khi tải danh sách map từ DB: {e}")
        # Trả về lỗi 500 nếu DB gặp sự cố
        raise HTTPException(status_code=500, detail="Lỗi khi truy vấn database để lấy danh sách map")

    
@app.get("/api/maps/{map_id}")
async def get_map_detail(map_id: str):
    async with pool.acquire() as conn:
        # Lấy thông tin map
        map_info = await conn.fetchrow("""
            SELECT id, name, origin_x, origin_y, origin_theta, image_path 
            FROM agv_maps 
            WHERE id = $1
        """, map_id)
        if not map_info:
            raise HTTPException(404, "Map không tồn tại")

        # Lấy points
        points = await conn.fetch("""
            SELECT name_id, name, x, y , action
            FROM agv_map_points 
            WHERE map_id = $1
        """, map_id)

        # Lấy roads
        roads = await conn.fetch("""
            SELECT id_source, id_dest, 
                   point_start_x, point_start_y, 
                   point_end_x, point_end_y,
                   move_direction, width
            FROM agv_map_roads 
            WHERE map_id = $1
        """, map_id)
        
        # =========================================================================
        # [MỚI] LẤY ĐƯỜNG CONG BEZIER
        # =========================================================================
        benziers = await conn.fetch("""
            SELECT id_source, id_dest, 
                   point_start_x, point_start_y, 
                   point_end_x, point_end_y,
                   curve_point_start_x, curve_point_start_y,
                   curve_point_end_x, curve_point_end_y,
                   move_direction, width
            FROM agv_map_benziers
            WHERE map_id = $1
        """, map_id)
        # =========================================================================

        return {
            "id": map_info["id"],
            "name": map_info["name"] or "Không tên",
            "origin_x": map_info["origin_x"],
            "origin_y": map_info["origin_y"],
            "origin_theta": map_info["origin_theta"],
            "image_path": f"/maps/{map_info['id']}.png",  # phục vụ qua static
            "robot_points": [
                {
                    "name_id": str(p["name_id"]),
                    "name": p["name"],
                    "x": float(p["x"]),
                    "y": float(p["y"]),
                    "action": p["action"] if p["action"] is not None else None,
                }
                for p in points
            ],
            "roads": [dict(r) for r in roads],
            "benziers": [dict(b) for b in benziers] # THÊM TRƯỜNG BEZIERS VÀO PHẢN HỒI
        }
    
@app.post("/api/agv/position")
async def update_position(request: Request):
    try:
        data = await request.json()
        agv_id = data.get("agv_id", "AGV_01")        # ← Lấy ID AGV (rất quan trọng!)
        map_id = str(data.get("map_id", ""))
        x = float(data.get("x", 0))
        y = float(data.get("y", 0))
        theta = float(data.get("theta", 0))

        # GỬI VỊ TRÍ QUA WEBSOCKET ĐẾN TẤT CẢ DASHBOARD
        await broadcast_agv_pose(agv_id, x, y, theta, map_id)

        # (Tùy chọn) lưu vào biến global nếu cần dùng ở nơi khác
        # current_agv_pos = {"map_id": map_id, "x": x, "y": y, "theta": theta}

        return {"status": "ok", "agv_id": agv_id, "broadcasted": True}
    except Exception as e:
        print(f"[ERROR] Lỗi parse pose: {e}")
        raise HTTPException(400, "Invalid position data")
    
@app.get("/api/agv/position")
async def get_position(map_id: str = None):
    global current_agv_pos
    if current_agv_pos["x"] is not None:
        if map_id is None or current_agv_pos["map_id"] == map_id:
            return current_agv_pos
    return {"x": None, "y": None, "theta": 0, "map_id": None}

# ==========================
# [MỚI] UPLOAD MAP HOÀN CHỈNH BẰNG JSON THUẦN (2025 STANDARD)
# ==========================
router = APIRouter(prefix="/api/map/node", tags=["Map Node Config"])

class MapNodeConfigRequest(BaseModel):
    mapId: str
    nodeId: str
    config: dict

@router.post("/config")
async def save_node_config(payload: MapNodeConfigRequest, request: Request):
    pool = request.app.state.db_pool
    map_id = (payload.mapId or "").strip()
    node_id = str(payload.nodeId or "").strip()

    if not map_id:
        raise HTTPException(status_code=400, detail="mapId là bắt buộc")
    if not node_id:
        raise HTTPException(status_code=400, detail="nodeId là bắt buộc")

    config = payload.config or {}
    name = (config.get("name") or "").strip()
    location_type = (config.get("locationType") or "").strip().upper()
    default_action = (config.get("defaultAction") or "").strip().upper()

    action_json = {
        "locationType": location_type,
        "defaultAction": default_action
    }

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE public.agv_map_points
            SET name = $1, action = $2::jsonb
            WHERE map_id = $3 AND name_id = $4
            RETURNING id, map_id, name_id, name, action
            """,
            name if name else None,
            action_json,
            map_id,
            node_id,
        )

        if not row:
            raise HTTPException(status_code=404, detail="Không tìm thấy node")

        return {
            "success": True,
            "message": "Đã lưu cấu hình node thành công",
            "data": {
                "id": row["id"],
                "mapId": row["map_id"],
                "nodeId": row["name_id"],
                "name": row["name"],
                "action": row["action"],
            },
        }

@app.post("/api/agv/map/upload-full")
async def agv_upload_full_json(request: Request):
    global last_map_id

    try:
        payload = await request.json()
    except Exception as e:
        print("Lỗi parse JSON:", e)
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # In JSON nhận được để debug
    print("\n" + "="*80)
    print("NHẬN ĐƯỢC MAP MỚI TỪ AGV")
    print("="*80)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print("="*80 + "\n")

    # ================== LẤY THÔNG TIN TỪ robot_maps ==================
    robot_maps = payload.get("robot_maps", {})
    map_name_from_root = payload.get("mapName", "").strip()

    map_id = str(robot_maps.get("id") or str(uuid.uuid4())) # Dùng UUID tạm nếu thiếu ID

    map_name = robot_maps.get("name", map_name_from_root)
    if not map_name:
        map_name = f"map_{map_id}"

    origin_x = float(robot_maps.get("x", 0))
    origin_y = float(robot_maps.get("y", 0))
    origin_theta = float(robot_maps.get("theta", 0))
    layer = int(robot_maps.get("layer", 0))

    # Thời gian sửa
    modify_time_str = robot_maps.get("modifytime")
    if modify_time_str and len(modify_time_str) >= 10:
        try:
            modify_time = datetime.strptime(modify_time_str, "%Y-%m-%d %H:%M:%S")
            modify_time = modify_time.replace(tzinfo=timezone(timedelta(hours=7)))
        except:
            modify_time = datetime.now(timezone(timedelta(hours=7)))
    else:
        modify_time = datetime.now(timezone(timedelta(hours=7)))

    # ================== LƯU ẢNH ==================
    image_b64 = robot_maps.get("image", "")
    if not image_b64:
        print("Không có ảnh base64!")

    image_path = None
    if image_b64:
        if image_b64.startswith("data:"):
            image_b64 = image_b64.split(",", 1)[1]

        try:
            image_data = base64.b64decode(image_b64)
            if len(image_data) < 1000:  # quá nhỏ → lỗi base64
                raise Exception("Base64 quá ngắn")
        except Exception as e:
            print("Lỗi decode ảnh:", e)
            raise HTTPException(status_code=400, detail=f"Invalid image base64: {e}")

        MAP_DIR.mkdir(parents=True, exist_ok=True)
        image_file = MAP_DIR / f"{map_id}.png"
        image_path = f"maps/{map_id}.png"
        with open(image_file, "wb") as f:
            f.write(image_data)

        print(f"Đã lưu ảnh thành công: {image_file} ({len(image_data)} bytes)")

    # ================== LƯU DB ==================
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Upsert map
            await conn.execute("""
                INSERT INTO agv_maps (id, name, origin_x, origin_y, origin_theta, image_path, modify_time, layer)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                ON CONFLICT (id) DO UPDATE SET
                    name=EXCLUDED.name,
                    origin_x=EXCLUDED.origin_x,
                    origin_y=EXCLUDED.origin_y,
                    origin_theta=EXCLUDED.origin_theta,
                    image_path=EXCLUDED.image_path,
                    modify_time=EXCLUDED.modify_time,
                    layer=EXCLUDED.layer,
                    updated_at=NOW()
            """, map_id, map_name, origin_x, origin_y, origin_theta, image_path, modify_time, layer)

            # Xóa dữ liệu cũ
            # ĐÃ THÊM BẢNG agv_map_benziers VÀO ĐÂY
            for table in ["agv_map_points", "agv_map_roads", "agv_map_codes", "agv_map_benziers"]: 
                await conn.execute(f"DELETE FROM {table} WHERE map_id = $1", map_id)

            # Lưu points (có thể rỗng)
            points = payload.get("robot_points", [])
            for p in points:
                await conn.execute("""
                    INSERT INTO agv_map_points
                    (map_id, name_id, name, x, y, theta, type, zone, action, carrier, available, accuracy)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
                """, map_id,
                    str(p.get("name_id", "")),
                    p.get("name", ""),
                    p.get("x"), p.get("y"), p.get("theta"),
                    p.get("type", 0), p.get("zone", ""), p.get("action"),
                    p.get("carrier", 0), p.get("available", False), p.get("accuracy", 0))

            # Lưu roads (có thể rỗng)
            roads = payload.get("robot_roads", [])
            for r in roads:
                point_start = r.get("point_start", [0, 0])
                point_end = r.get("point_end", [0, 0])
                await conn.execute("""
                    INSERT INTO agv_map_roads
                    (map_id, name, id_source, id_dest,
                     point_start_x, point_start_y, point_end_x, point_end_y,
                     width, speed, move_direction, distance)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
                """, map_id, r.get("name", ""),
                    str(r["id_source"]), str(r["id_dest"]),
                    point_start[0], point_start[1],
                    point_end[0], point_end[1],
                    r.get("width", 0.95), r.get("speed", 0.3),
                    r.get("move_direction", 0), r.get("distance", 0))

            # Lưu codes (có thể rỗng)
            codes = payload.get("robot_code", [])
            for c in codes:
                await conn.execute("""
                    INSERT INTO agv_map_codes (map_id, code_id, code, x, y, theta)
                    VALUES ($1,$2,$3,$4,$5,$6)
                """, map_id, c.get("id"), c.get("code", ""), c.get("x"), c.get("y"), c.get("theta"))
                
            # =========================================================================
            # [MỚI] LƯU ĐƯỜNG CONG BEZIER
            # =========================================================================
            benziers = payload.get("robot_benziers", [])

            if benziers:
                print(f"  | Benziers: {len(benziers)}")
                for b in benziers:
                    point_start = b.get("point_start", [0, 0])
                    point_end = b.get("point_end", [0, 0])
                    curve_point_start = b.get("curve_point_start", [0, 0])
                    curve_point_end = b.get("curve_point_end", [0, 0])
                    
                    # Chèn dữ liệu Bezier vào bảng agv_map_benziers
                    await conn.execute("""
                        INSERT INTO agv_map_benziers (
                            map_id, name, id_source, id_dest,
                            point_start_x, point_start_y, point_end_x, point_end_y,
                            curve_point_start_x, curve_point_start_y, curve_point_end_x, curve_point_end_y,
                            width, speed, move_direction
                        )
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
                    """, map_id, b.get("name", ""),
                        str(b["id_source"]), str(b["id_dest"]),
                        point_start[0], point_start[1],
                        point_end[0], point_end[1],
                        curve_point_start[0], curve_point_start[1],
                        curve_point_end[0], curve_point_end[1],
                        b.get("width", 0.3), b.get("speed", 0.3),
                        b.get("move_direction", 0)
                    )
            # =========================================================================

    print(f"Upload map thành công! ID: {map_id} | Tên: {map_name} | Points: {len(points)} | Roads: {len(roads)} | Codes: {len(codes)} | Benziers: {len(benziers)}\n")

    return {
        "status": "success",
        "map_id": map_id,
        "map_name": map_name,
        "image_saved": image_path,
        "points": len(points),
        "roads": len(roads),
        "codes": len(codes),
        "benziers": len(benziers), # THÊM SỐ LƯỢNG BEZIER VÀO PHẢN HỒI
        "server_time": datetime.now(timezone(timedelta(hours=7))).isoformat()
    }

# ==========================
# AGV PANEL ACTIONS: CHARGE / WAIT / CANCEL
# ==========================
@app.get("/api/agv/targets")
async def api_get_agv_targets(agv_id: str):
    """
    Trả về node sạc và khu chờ theo map hiện tại của AGV.
    Dùng cho panel AGV ở frontend.
    """
    try:
        result = await asyncio.to_thread(get_agv_special_targets, agv_id)
        return result
    except Exception as e:
        print("[ERROR] /api/agv/targets:")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/agv/go-charge")
async def api_go_charge(req: AgvActionRequest):
    """
    Gửi AGV đi tới node sạc.
    """
    try:
        print(f"[API] Nhận lệnh đi sạc: AGV={req.agv_id}")

        result = await asyncio.to_thread(send_agv_to_special_target, req.agv_id, "charge")

        # broadcast realtime cho dashboard
        asyncio.create_task(broadcast_update({
            "type": "external_command",
            "action": "GO_CHARGE",
            "agv_id": req.agv_id,
            "target_node": result.get("target_node"),
            "target_name": result.get("target_name"),
            "path": result.get("path", []),
            "order_id": result.get("orderId"),
            "timestamp": datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).isoformat()
        }))

        return result

    except Exception as e:
        print("[ERROR] /api/agv/go-charge:")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/agv/go-wait")
async def api_go_wait(req: AgvActionRequest):
    """
    Gửi AGV về khu chờ.
    """
    try:
        print(f"[API] Nhận lệnh về khu chờ: AGV={req.agv_id}")

        result = await asyncio.to_thread(send_agv_to_special_target, req.agv_id, "wait")

        # broadcast realtime cho dashboard
        asyncio.create_task(broadcast_update({
            "type": "external_command",
            "action": "GO_WAIT",
            "agv_id": req.agv_id,
            "target_node": result.get("target_node"),
            "target_name": result.get("target_name"),
            "path": result.get("path", []),
            "order_id": result.get("orderId"),
            "timestamp": datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).isoformat()
        }))

        return result

    except Exception as e:
        print("[ERROR] /api/agv/go-wait:")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/agv/cancel-order")
async def api_cancel_order(req: AgvActionRequest):
    """
    Hủy lệnh hiện tại của AGV bằng instant action.
    Đồng thời xóa pending drop trong mqtt_client nếu có.
    """
    try:
        print(f"[API] Nhận lệnh hủy order: AGV={req.agv_id}")

        result = await asyncio.to_thread(cancel_agv_order, req.agv_id)

        # broadcast realtime cho dashboard
        asyncio.create_task(broadcast_update({
            "type": "external_command",
            "action": "CANCEL",
            "agv_id": req.agv_id,
            "cancelled_order_id": result.get("cancelled_order_id"),
            "removed_pending_drop": result.get("removed_pending_drop", False),
            "timestamp": datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).isoformat()
        }))

        return result

    except Exception as e:
        print("[ERROR] /api/agv/cancel-order:")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=str(e))

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
