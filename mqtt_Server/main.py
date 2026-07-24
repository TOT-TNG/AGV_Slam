# main.py - PHIÊN BẢN HOÀN CHỈNH 2025 - REAL-TIME ĐA CLIENT + BROADCAST MỌI SỰ KIỆN
import log_buffer   # phải import đầu tiên để hook builtins.print trước mọi module khác
from fastapi import FastAPI, HTTPException, APIRouter, UploadFile, File, Form, Request, WebSocket
from pydantic import BaseModel
from fastapi.responses import StreamingResponse, FileResponse, HTMLResponse, RedirectResponse, JSONResponse
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
from mqtt_client import (
    start_mqtt,
    setup_unified_mqtt,
    send_order,
    agv_manager,
    map_manager,
    ensure_map_loaded_sync,
    _remember_pending_reroute_apply,
    _remember_head_on_assignment,
    send_instant_action,
    send_pick_action,
    stop_mqtt,
    set_app,
    send_agv_to_special_target,
    cancel_agv_order,
    get_agv_special_targets,
    switch_mqtt_mode,
    get_mqtt_mode,
)
from order_builder import build_order
from map_configure_api import router as map_config_router
import integration_engine
from traffic_core import (
    TrafficEngine,
    TopologyMap as TrafficTopologyMap,
    Node as TrafficNode,
    Edge as TrafficEdge,
    TrafficAction,
    RerouteStrategy,
)
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
import builtins
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from typing import List, Dict
import json

# Fix Windows terminal encoding (cp1252 → utf-8) để print tiếng Việt không crash
if hasattr(sys.stdout, 'buffer') and getattr(sys.stdout, 'encoding', 'utf-8').lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'buffer') and getattr(sys.stderr, 'encoding', 'utf-8').lower() != 'utf-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

traffic_engine = TrafficEngine()
_last_main_log_ts: dict[str, float] = {}

# Ensure every runtime import path resolves to the same live module instance.
# Without this, `mqtt_client.py` can import `main` as a second module object
# (for example when this file is launched as `__main__` or via a package path),
# which duplicates `traffic_engine` and causes API route activation and MQTT
# telemetry handling to see different traffic state.
_this_module = sys.modules[__name__]
sys.modules["main"] = _this_module
sys.modules["mqtt_Server.main"] = _this_module


def print(*args, **kwargs):
    text = " ".join(str(arg) for arg in args)
    now = time.time()

    if "[WS] Đã broadcast pose AGV" in text:
        key = "ws_pose"
        if now - _last_main_log_ts.get(key, 0.0) < 2.0:
            return
        _last_main_log_ts[key] = now

    builtins.print(*args, **kwargs)
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
        occupied_nodes = set()
        for other_agv in agv_manager.list_agvs():
            other_id = str(other_agv.get("agv_id") or other_agv.get("id") or "").strip()
            if not other_id or other_id == agv_id:
                continue
            last_node = _normalize_graph_node_id(other_agv.get("lastNodeId"), graph)
            if last_node:
                occupied_nodes.add(str(last_node))

        occupied_nodes.discard(str(start))
        occupied_nodes.discard(str(dest))
        if occupied_nodes:
            g.remove_nodes_from(node for node in occupied_nodes if node in g)
        try:
            return nx.shortest_path(g, source=str(start), target=str(dest), weight="weight")
        except Exception:
            return None

edge_coordinator = EdgeCoordinator()


def _normalize_graph_node_id(node_id: str | None, graph) -> str | None:
    if node_id is None:
        return None
    token = str(node_id).strip()
    if not token:
        return None
    if token in graph:
        return token
    upper = token.upper()
    if upper.startswith("N") and token[1:] in graph:
        return token[1:]
    return token


def _format_path_for_agv_node_ids(path: list[str], agv_last_node_id: str | None) -> list[str]:
    raw_last = str(agv_last_node_id or "").strip()
    if not raw_last:
        return [str(node) for node in path]
    if not raw_last.upper().startswith("N"):
        return [str(node) for node in path]
    formatted = []
    for node in path:
        token = str(node).strip()
        if token.upper().startswith("N"):
            formatted.append(token)
        else:
            formatted.append(f"N{token}")
    return formatted


def _build_traffic_topology_from_loaded_map() -> TrafficTopologyMap:
    nodes = [
        TrafficNode(node_id=str(node_id), x=float(pos[0]), y=float(pos[1]))
        for node_id, pos in map_manager.points.items()
    ]

    # Build từ roads list — tôn trọng move_direction
    # move_direction: 0=both, 1=forward(src→dst), 2=backward(dst→src), 3=blocked
    edges = []
    seen_physical: set[str] = set()   # tránh tạo duplicate cho 2-chiều

    for r in (getattr(map_manager, 'roads', []) or []):
        src_id   = str(r['id_source'])
        dst_id   = str(r['id_dest'])
        mdir     = int(r.get('move_direction') or 0)
        length   = float(r.get('distance') or 1.0)
        max_speed = float(r.get('speed') or 0.5)
        phys_id  = "__".join(sorted((src_id, dst_id)))

        if mdir == 3:               # blocked — bỏ qua hoàn toàn
            continue

        if mdir == 0:               # 2 chiều — tạo 1 edge bidirectional=True
            if phys_id in seen_physical:
                continue            # đã tạo từ lần lặp ngược
            seen_physical.add(phys_id)
            edges.append(TrafficEdge(
                edge_id=f"{src_id}_to_{dst_id}",
                from_node=src_id, to_node=dst_id,
                length=length, max_speed=max_speed,
                bidirectional=True,             # TopologyMap tự tạo reverse
                physical_edge_id=phys_id,
            ))

        elif mdir == 1:             # 1 chiều tiến src→dst
            edges.append(TrafficEdge(
                edge_id=f"{src_id}_to_{dst_id}",
                from_node=src_id, to_node=dst_id,
                length=length, max_speed=max_speed,
                bidirectional=False,
                physical_edge_id=phys_id,
            ))

        elif mdir == 2:             # 1 chiều lùi → đảo thành dst→src
            edges.append(TrafficEdge(
                edge_id=f"{dst_id}_to_{src_id}",
                from_node=dst_id, to_node=src_id,
                length=length, max_speed=max_speed,
                bidirectional=False,
                physical_edge_id=phys_id,
            ))

    # Bezier curves — luôn 2 chiều (không có move_direction trong DB)
    for src, dst, data in map_manager.graph.edges(data=True):
        if int(data.get('move_direction', 0)) != 0:
            continue    # roads đã xử lý ở trên
        src_id = str(src); dst_id = str(dst)
        phys_id = "__".join(sorted((src_id, dst_id)))
        if phys_id in seen_physical:
            continue
        # Edge này đến từ benzier (không có trong roads_data)
        in_roads = any(
            (str(r['id_source']) == src_id and str(r['id_dest']) == dst_id) or
            (str(r['id_source']) == dst_id and str(r['id_dest']) == src_id)
            for r in (getattr(map_manager, 'roads', []) or [])
        )
        if in_roads:
            continue
        seen_physical.add(phys_id)
        edges.append(TrafficEdge(
            edge_id=f"{src_id}_to_{dst_id}",
            from_node=src_id, to_node=dst_id,
            length=float(data.get('weight') or 1.0),
            max_speed=float(data.get('speed') or 0.5),
            bidirectional=True,
            physical_edge_id=phys_id,
        ))

    return TrafficTopologyMap(nodes, edges)


def ensure_traffic_topology_from_loaded_map(map_id: str) -> None:
    map_ref = str(map_id or "").strip()
    if not map_ref:
        raise ValueError("map_id is required")

    resolved_map_id = ensure_map_loaded_sync(map_ref) or map_ref
    resolved_map_id = str(resolved_map_id).strip()

    if (
        not resolved_map_id
        or str(map_manager.current_map_id) != resolved_map_id
        or map_manager.graph.number_of_nodes() == 0
    ):
        raise ValueError(
            f"Map {map_ref} could not be resolved/loaded in MapManager "
            f"(current={map_manager.current_map_id})"
        )

    # Only build and set topology once per map_id — resetting on every call destroys the
    # shared StateStore and makes cross-AGV state lookups always return None.
    if not traffic_engine.has_map(resolved_map_id):
        traffic_engine.set_topology(resolved_map_id, _build_traffic_topology_from_loaded_map())
    return resolved_map_id


def _route_to_node_path(route) -> list[str]:
    if route is None or not getattr(route, "segments", None):
        return []
    return [str(route.start_node)] + [str(segment.to_node) for segment in route.segments]


def _line_agv_dispatch_to_charge(agv_id: str) -> None:
    """
    Dispatch Line AGV về trạm sạc.
    Gọi từ _on_battery_event callback trong mqtt_client.
    """
    try:
        from mqtt_client import (
            send_order,
            plan_path_for_order,
            resolve_special_target_node,
            get_agv_runtime_info,
        )
        from line_agv_plan_builder import (
            build_line_plan, build_plan_window, build_edge_speeds, build_edge_lidar,
        )
        from line_agv_handler import line_agv_handler

        info = get_agv_runtime_info(agv_id)
        current_node = info["current_node"]
        if not current_node:
            print(f"[LINE_CHARGE] {agv_id}: không biết vị trí hiện tại")
            return

        target_info = resolve_special_target_node(agv_id, "charge")
        target_node = target_info["node_id"]

        if str(current_node) == str(target_node):
            print(f"[LINE_CHARGE] {agv_id}: đã ở trạm sạc {target_node}")
            return

        route_nodes, _ = plan_path_for_order(agv_id, current_node, target_node)
        path = [str(n["nodeId"]) for n in route_nodes]
        if not path:
            print(f"[LINE_CHARGE] {agv_id}: không tìm được đường về trạm sạc")
            return

        points       = getattr(map_manager, "points",       {}) or {}
        node_actions = getattr(map_manager, "node_actions", {}) or {}
        roads        = getattr(map_manager, "roads",        []) or []
        edge_spd     = build_edge_speeds(roads)
        edge_lidar   = build_edge_lidar(roads)
        _lstate_chg      = line_agv_handler.state_store.get(agv_id)
        _prev_chg        = str(_lstate_chg.prev_tag) if (_lstate_chg and _lstate_chg.prev_tag) else None
        _last_tdir_chg   = getattr(_lstate_chg, 'last_transit_direction', '') if _lstate_chg else ''
        _is_post_chg_c   = (getattr(_lstate_chg, 'task_lifecycle', '') or '') == "charging"
        _initial_prev_chg = _prev_chg if (_last_tdir_chg == 'bwd' and not _is_post_chg_c) else None
        _rt_chg = line_agv_handler.set_route(agv_id, path, "return_charge")
        # Gửi cửa sổ đầu (≤LOOKAHEAD node) — rolling gửi tiếp nếu đường dài.
        plan = build_plan_window(
            full_path=path, w_start=0, w_end=_rt_chg.window_end, points=points,
            is_final=_rt_chg.is_complete, task_type="return_charge",
            node_actions=node_actions, edge_speeds=edge_spd, edge_lidar=edge_lidar,
            agv_id=agv_id, initial_prev_tag=_initial_prev_chg)
        send_order(agv_id, plan)
        print(f"[LINE_CHARGE] {agv_id}: dispatched to charge {target_node} | path={path}")

    except Exception as e:
        print(f"[LINE_CHARGE] {agv_id}: dispatch error: {e}")


def build_order_for_traffic_route(
    agv_id: str,
    route,
    agv_state: dict,
    order_id: str | None = None,
    order_update_id: int = 0,
):
    from agv_registry import agv_registry

    node_path = _route_to_node_path(route)

    # ── Line AGV: trả về plan {"c":"plan","id":...,"d":[...]} ─────────────────
    if agv_registry.is_line(agv_id):
        from line_agv_plan_builder import build_plan_window, first_window_end
        from line_agv_handler import line_agv_handler

        str_path  = [str(p) for p in node_path]
        points    = getattr(map_manager, "points", {}) or {}
        task_type = str(agv_state.get("task_type", "delivery") or "delivery")
        cmd_id    = str(order_id)[:8] if order_id else None

        # Lưu route để handler quản lý rolling plan
        line_agv_handler.set_route(agv_id, str_path, task_type)

        # Lấy prev_tag để tính turn tại node đầu tiên nếu cần
        _lstate_trt      = line_agv_handler.state_store.get(agv_id)
        _prev_trt        = str(_lstate_trt.prev_tag) if (_lstate_trt and _lstate_trt.prev_tag) else None
        _last_tdir_trt   = getattr(_lstate_trt, 'last_transit_direction', '') if _lstate_trt else ''
        _is_post_chg_trt = (getattr(_lstate_trt, 'task_lifecycle', '') or '') == "charging"
        _initial_prev_trt = _prev_trt if (_last_tdir_trt == 'bwd' and not _is_post_chg_trt) else None

        # Chỉ gửi cửa sổ đầu tiên
        w_end    = first_window_end(str_path)
        is_final = (w_end == len(str_path) - 1)
        plan = build_plan_window(
            full_path=str_path,
            w_start=0,
            w_end=w_end,
            points=points,
            is_final=is_final,
            task_type=task_type,
            cmd_id=cmd_id,
            agv_id=agv_id,
            initial_prev_tag=_initial_prev_trt,
        )
        return plan, str_path

    # ── VDA5050: giữ nguyên logic cũ ─────────────────────────────────────────
    external_path = _format_path_for_agv_node_ids(node_path, agv_state.get("lastNodeId"))
    coords_lookup = {}
    if getattr(map_manager, "points", None):
        for node_id, pos in map_manager.points.items():
            coords_lookup[str(node_id)] = (pos[0], pos[1], 0.0)
            coords_lookup[f"N{str(node_id)}"] = (pos[0], pos[1], 0.0)
    order = build_order(
        agv_id=agv_id,
        path=external_path,
        coords=coords_lookup,
        manufacture=agv_state.get("manufacturer", "TNG:TOT"),
        SerialNumber=agv_state.get("serialNumber", agv_id),
        version="2.0",
        order_id=order_id,
        order_update_id=order_update_id,
        horizon=None,
    )
    return order, external_path


def _apply_immediate_route_controls(map_id: str, requested_agv_id: str | None = None) -> dict[str, object]:
    results = traffic_engine.evaluate_map_controls(str(map_id))
    hold_for_reroute: set[str] = set()
    requested_override: dict[str, object] | None = None

    for source_agv_id, source_result in results.items():
        source_decision = source_result.decision
        source_reroute = source_result.reroute_result
        if (
            source_decision is None
            or source_reroute is None
            or not source_reroute.success
            or source_reroute.route is None
            or source_reroute.strategy == RerouteStrategy.SPEED_ONLY
        ):
            continue
        related_agv_id = str(source_decision.related_agv_id or "").strip()
        if related_agv_id:
            hold_for_reroute.add(related_agv_id)

    for target_agv_id, target_result in results.items():
        target_state = agv_manager.get_agv(target_agv_id) or {}
        target_decision = target_result.decision
        target_reroute = target_result.reroute_result

        if (
            target_reroute is not None
            and target_reroute.success
            and target_reroute.route is not None
            and target_reroute.strategy != RerouteStrategy.SPEED_ONLY
        ):
            next_order_id = str(target_state.get("orderId") or uuid.uuid4())
            next_update_id = int(target_state.get("orderUpdateId") or 0) + 1
            reroute_order, reroute_path = build_order_for_traffic_route(
                target_agv_id,
                target_reroute.route,
                target_state,
                order_id=next_order_id,
                order_update_id=next_update_id,
            )
            _remember_pending_reroute_apply(
                target_agv_id,
                next_order_id,
                next_update_id,
                [segment.edge_id for segment in target_reroute.route.segments],
            )
            send_order(target_agv_id, reroute_order)
            agv_manager.set_order(target_agv_id, next_order_id, next_update_id)
            traffic_engine.activate_route(target_agv_id, str(map_id), target_reroute.route)
            if requested_agv_id and target_agv_id == requested_agv_id:
                requested_override = {
                    "order_id": next_order_id,
                    "order_update_id": next_update_id,
                    "path": reroute_path,
                    "rerouted": True,
                }
            continue

        if target_agv_id in hold_for_reroute:
            if not target_state.get("paused"):
                send_instant_action(target_agv_id, "PAUSE")
            continue

        if target_decision is None:
            continue

        if target_decision.action in {TrafficAction.WAIT, TrafficAction.STOP}:
            if not target_state.get("paused"):
                send_instant_action(target_agv_id, "PAUSE")

    return requested_override or {}


def _apply_immediate_head_on_assignment(
    map_id: str,
    requested_agv_id: str | None = None,
    requested_route=None,
) -> dict[str, object]:
    map_key = str(map_id or "").strip()
    if not map_key or not requested_agv_id or requested_route is None:
        return {}
    assignments = traffic_engine.resolve_immediate_head_on(
        map_key,
        requested_agv_id=str(requested_agv_id),
        requested_route=requested_route,
    )
    if not assignments:
        return {}

    requested_override: dict[str, object] = {}
    for assignment in assignments:
        loser = str(assignment.get("loser") or "")
        winner = str(assignment.get("winner") or "")
        combined_route = assignment.get("route")
        if not loser or combined_route is None:
            continue

        loser_state_data = agv_manager.get_agv(loser) or {}
        next_order_id = str(loser_state_data.get("orderId") or uuid.uuid4())
        next_update_id = int(loser_state_data.get("orderUpdateId") or 0) + 1
        reroute_order, reroute_path = build_order_for_traffic_route(
            loser,
            combined_route,
            loser_state_data,
            order_id=next_order_id,
            order_update_id=next_update_id,
        )
        _remember_pending_reroute_apply(
            loser,
            next_order_id,
            next_update_id,
            [segment.edge_id for segment in combined_route.segments],
        )
        send_order(loser, reroute_order)
        agv_manager.set_order(loser, next_order_id, next_update_id)

        winner_state_data = agv_manager.get_agv(winner) or {}
        if winner and not winner_state_data.get("paused"):
            send_instant_action(winner, "PAUSE")

        try:
            resource_node = assignment.get("resource") or assignment.get("branch_node")
            _remember_head_on_assignment(winner, loser, resource_node)
        except Exception:
            pass

        print(
            f"[HEAD_ON_ASSIGN] engine winner={winner} loser={loser} "
            f"resource={assignment.get('resource')} branch={assignment.get('branch_node')} "
            f"reroute_path={reroute_path}"
        )

        if requested_agv_id and str(requested_agv_id) == loser:
            requested_override = {
                "order_id": next_order_id,
                "order_update_id": next_update_id,
                "path": reroute_path,
                "rerouted": True,
                "winner": winner,
                "loser": loser,
            }
    return requested_override or {}


def sync_traffic_route_from_state(
    agv_id: str,
    map_id: str,
    node_states: list,
    current_hint_node: str | None = None,
    allow_rehydrate: bool = True,
):
    if not allow_rehydrate:
        return None

    existing = traffic_engine.get_route(agv_id)
    if existing is not None:
        return existing

    ordered_nodes = []
    for item in sorted(
        [ns for ns in (node_states or []) if isinstance(ns, dict)],
        key=lambda ns: int(ns.get("sequenceId", 0)),
    ):
        node_id = _normalize_graph_node_id(item.get("nodeId"), map_manager.graph)
        if not node_id:
            continue
        node_id = str(node_id)
        if not ordered_nodes or ordered_nodes[-1] != node_id:
            ordered_nodes.append(node_id)

    if len(ordered_nodes) < 2:
        return None

    return traffic_engine.activate_route_from_node_path(
        agv_id=agv_id,
        map_id=str(map_id),
        node_path=ordered_nodes,
        current_hint_node=_normalize_graph_node_id(current_hint_node, map_manager.graph),
        reason="STATE_REHYDRATED",
    )

class ReleaseRequest(BaseModel):
    agv_id: str
class AgvActionRequest(BaseModel):
    agv_id: str

class SetTagRequest(BaseModel):
    agv_id: str
    node_id: str
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
                    agv_manager.set_connection(agv_id, "OFFLINE")
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
    app.state.shutting_down = False

    set_app(app)

    # ── Load AGV registry từ DB (agv_devices) ────────────────────────────────
    # Ưu tiên DB; fallback về simulator.json nếu DB chưa sẵn sàng
    try:
        from agv_registry import agv_registry as _registry
        if app.state.db_pool:
            _registry.load_from_db()
            print(f"[REGISTRY] Loaded from DB: {_registry}")
        else:
            raise RuntimeError("DB pool not ready")
    except Exception as _re:
        print(f"[REGISTRY] DB load failed ({_re}), falling back to simulator.json")
        try:
            import json as _json, os as _os
            _cfg_path = _os.path.join(_os.path.dirname(__file__), "..", "agv_vda5050_simulator", "config", "simulator.json")
            if _os.path.exists(_cfg_path):
                with open(_cfg_path, encoding="utf-8") as _f:
                    _sim = _json.load(_f)
                from agv_registry import agv_registry as _registry
                _registry.load_from_config(_sim.get("agvs", []))
        except Exception as _fe:
            print(f"[REGISTRY] Fallback also failed: {_fe}")

    # ── Khởi tạo unified MQTT (dùng registry vừa load) ───────────────────────
    try:
        import json as _json, os as _os
        _cfg_path = _os.path.join(_os.path.dirname(__file__), "..", "agv_vda5050_simulator", "config", "simulator.json")
        _server_cfg: dict = {}
        if _os.path.exists(_cfg_path):
            with open(_cfg_path, encoding="utf-8") as _f:
                _sim = _json.load(_f)
            _server_cfg = {
                "factory":      _sim.get("mqtt", {}).get("interface_name", "uagv"),
                "manufacturer": _sim.get("manufacturer", "tot"),
            }
        setup_unified_mqtt([], _server_cfg)   # agv_cfgs rỗng — registry đã load từ DB
    except Exception as _ue:
        print(f"[UNIFIED_MQTT] init warning (non-fatal): {_ue}")

    # Khởi động MQTT
    print("[MQTT] Đang khởi động và chờ AGV kết nối thực tế...")
    app.state.mqtt_connected = start_mqtt()
    app.state.offline_stop = asyncio.Event()
    app.state.offline_task = asyncio.create_task(monitor_offline(app.state.offline_stop))
    if not app.state.mqtt_connected:
        print("[WARNING] MQTT broker is unavailable; server continues without broker state stream")

    # ── Tạo bảng + migration cột nếu chưa có ────────────────────────────────────
    if app.state.db_pool:
        try:
            async with app.state.db_pool.acquire() as _conn:
                await _conn.execute("""
                    CREATE TABLE IF NOT EXISTS agv_task_executions (
                        id            SERIAL PRIMARY KEY,
                        cmd_id        VARCHAR(16) UNIQUE NOT NULL,
                        agv_id        VARCHAR(50),
                        command       VARCHAR(50),
                        dest_node     VARCHAR(100),
                        status        VARCHAR(20) DEFAULT 'queued',
                        queued_at     TIMESTAMPTZ DEFAULT NOW(),
                        started_at    TIMESTAMPTZ,
                        completed_at  TIMESTAMPTZ,
                        notes         TEXT
                    )
                """)
                print("[DB] Table agv_task_executions ready")
                # Cột session để nhóm các lệnh theo 1 lượt workflow
                await _conn.execute(
                    "ALTER TABLE agv_task_executions ADD COLUMN IF NOT EXISTS session_id VARCHAR(40)"
                )
                await _conn.execute(
                    "ALTER TABLE agv_task_executions ADD COLUMN IF NOT EXISTS session_label VARCHAR(200)"
                )
                print("[DB] Columns agv_task_executions.session_id/session_label ensured")
                # Cột agv_devices
                await _conn.execute(
                    "ALTER TABLE agv_devices ADD COLUMN IF NOT EXISTS map_id TEXT"
                )
                await _conn.execute(
                    "ALTER TABLE agv_devices ADD COLUMN IF NOT EXISTS factory TEXT"
                )
                print("[DB] Columns agv_devices.map_id / factory ensured")
                await _conn.execute(
                    "ALTER TABLE agv_devices ADD COLUMN IF NOT EXISTS last_tag TEXT"
                )
                # Thông tin mạng AGV (cập nhật tự động từ MQTT info topic)
                for _col in ("subnet TEXT", "gateway TEXT", "dns TEXT"):
                    await _conn.execute(
                        f"ALTER TABLE agv_devices ADD COLUMN IF NOT EXISTS {_col}"
                    )
                print("[DB] Columns agv_devices.last_tag / subnet / gateway / dns ensured")
                # Cột khả năng lùi (MỚI — cho xe đầu kéo/rơ-moóc chỉ đi 1 chiều
                # tiến). DEFAULT TRUE → mọi AGV hiện có (carry) tự động giữ
                # nguyên hành vi cũ, không cần khai báo gì thêm.
                await _conn.execute(
                    "ALTER TABLE agv_devices ADD COLUMN IF NOT EXISTS can_reverse BOOLEAN DEFAULT TRUE"
                )
                print("[DB] Column agv_devices.can_reverse ensured")
                try:
                    from agv_registry import agv_registry as _registry_rev
                    _registry_rev.load_reverse_capability()
                except Exception as _rre:
                    print(f"[REGISTRY] load_reverse_capability warning (non-fatal): {_rre}")
                # Cột LIDAR cho map roads / benziers
                await _conn.execute(
                    "ALTER TABLE agv_map_roads ADD COLUMN IF NOT EXISTS lidar_off BOOLEAN DEFAULT FALSE"
                )
                await _conn.execute(
                    "ALTER TABLE agv_map_roads ADD COLUMN IF NOT EXISTS lidar_off_dir TEXT DEFAULT 'none'"
                )
                await _conn.execute(
                    "ALTER TABLE agv_map_benziers ADD COLUMN IF NOT EXISTS lidar_off BOOLEAN DEFAULT FALSE"
                )
                await _conn.execute(
                    "ALTER TABLE agv_map_benziers ADD COLUMN IF NOT EXISTS lidar_off_dir TEXT DEFAULT 'none'"
                )
                print("[DB] Columns agv_map_roads/benziers.lidar_off / lidar_off_dir ensured")
                # Cột thông tin người gửi lệnh trên bảng agv_tasks
                await _conn.execute(
                    "ALTER TABLE agv_tasks ADD COLUMN IF NOT EXISTS operator_name TEXT"
                )
                await _conn.execute(
                    "ALTER TABLE agv_tasks ADD COLUMN IF NOT EXISTS operator_id TEXT"
                )
                print("[DB] Columns agv_tasks.operator_name / operator_id ensured")
                await _conn.execute(
                    "ALTER TABLE agv_tasks ADD COLUMN IF NOT EXISTS order_info JSONB"
                )
                print("[DB] Column agv_tasks.order_info ensured")
        except Exception as _te:
            print(f"[DB] Create table error (non-fatal): {_te}")

    # ── Integration engine ────────────────────────────────────────────────────
    if app.state.db_pool:
        integration_engine.set_pool(app.state.db_pool)
        try:
            await integration_engine.ensure_tables()
        except Exception as _ie:
            print(f"[INTEGRATION] ensure_tables error (non-fatal): {_ie}")

    # ── Khôi phục vị trí AGV Line từ DB (last_tag) ───────────────────────────
    try:
        async with app.state.db_pool.acquire() as _c:
            _rows = await _c.fetch(
                "SELECT name, last_tag FROM agv_devices WHERE last_tag IS NOT NULL"
            )
        if _rows:
            from line_agv_handler import line_agv_handler as _lah
            for _r in _rows:
                _agv_id = str(_r["name"]).strip()
                _tag_str = str(_r["last_tag"]).strip()
                if _tag_str.lstrip("-").isdigit():
                    _lah.override_position(_agv_id, int(_tag_str))
                    print(f"[STARTUP] Restored last_tag={_tag_str} for {_agv_id}")
    except Exception as _re:
        print(f"[STARTUP] Restore last_tag failed (non-fatal): {_re}")

    # ── Khởi tạo AGVTaskQueue ─────────────────────────────────────────────────
    try:
        from task_queue import agv_task_queue as _queue
        if app.state.db_pool:
            _queue.set_pool(app.state.db_pool)

        def _queue_dispatch(cmd) -> bool:
            from task_queue import CMD_GO_TO, CMD_GO_CHARGE, CMD_GO_WAIT, CMD_STOP, CMD_RESUME
            from mqtt_client import (
                send_agv_to_special_target, send_instant_action,
                send_line_command, plan_path_for_order,
            )
            from agv_registry import agv_registry
            try:
                if cmd.command == CMD_STOP:
                    if agv_registry.is_line(cmd.agv_id):
                        return send_line_command(cmd.agv_id, "stop")
                    return send_instant_action(cmd.agv_id, "PAUSE")
                if cmd.command == CMD_RESUME:
                    if agv_registry.is_line(cmd.agv_id):
                        return send_line_command(cmd.agv_id, "run")
                    return send_instant_action(cmd.agv_id, "RESUME")
                if cmd.command == CMD_GO_CHARGE:
                    send_agv_to_special_target(cmd.agv_id, "charge")
                    return True
                if cmd.command == CMD_GO_WAIT:
                    send_agv_to_special_target(cmd.agv_id, "wait")
                    return True
                if cmd.command == CMD_GO_TO and cmd.dest_node:
                    return bool(_dispatch_go_to(cmd.agv_id, cmd.dest_node,
                                                start_node=getattr(cmd, "start_node", None),
                                                session_id=getattr(cmd, "session_id", None)))
                return False
            except Exception as _e:
                print(f"[QUEUE_DISPATCH] error: {_e}")
                cmd.notes = str(_e)   # lưu lỗi thật để API trả về
                return False

        _queue.dispatch_fn = _queue_dispatch
        print("[QUEUE] AGVTaskQueue ready")
    except Exception as _qe:
        print(f"[QUEUE] init error (non-fatal): {_qe}")

    print("[SYSTEM] Hệ thống đã sẵn sàng!")
    print("[INFO] AGV sẽ xuất hiện khi gửi state thật qua MQTT")
    print("[INFO] Real-time broadcast đã hoạt động – MỌI thay đổi đều thông báo đến tất cả client")

    if app.state.db_pool and app.state.mqtt_connected:
        print("[SUCCESS] TOÀN BỘ HỆ THỐNG SẴN SÀNG! (MQTT + DB + Dashboard + Real-time)")
    elif app.state.db_pool:
        print("[WARNING] DB + Dashboard are ready, but MQTT broker is not connected")
    else:
        print("[WARNING] DB CHƯA KẾT NỐI – Chỉ có MQTT + Dashboard")

    # ── Khởi động scheduler lịch tự động ──────────────────────────────────────
    if app.state.db_pool:
        try:
            from schedule_manager import init_scheduler
            _sched = init_scheduler(app.state.db_pool)
            await _sched.init_table()
            _sched.start()
        except Exception as _se:
            print(f"[SCHEDULER] init error: {_se}")

    # ── Telegram Bot ───────────────────────────────────────────────────────────
    try:
        from telegram_bot import start_bot as _start_bot, set_pool as _tg_set_pool
        if app.state.db_pool:
            _tg_set_pool(app.state.db_pool)
        asyncio.create_task(_start_bot())
    except Exception as _tge:
        print(f"[TELEGRAM] init error (non-fatal): {_tge}")

    yield
    app.state.shutting_down = True
    stop_mqtt()

    # ── Dừng Telegram Bot ──────────────────────────────────────────────────────
    try:
        from telegram_bot import stop_bot as _stop_bot
        await _stop_bot()
    except Exception as _tge:
        print(f"[TELEGRAM] stop error (non-fatal): {_tge}")

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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(map_config_router)
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


def schedule_broadcast_update(data: dict) -> None:
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(broadcast_update(data))
        return
    except RuntimeError:
        pass

    loop = getattr(app.state, "loop", None)
    if loop is not None:
        asyncio.run_coroutine_threadsafe(broadcast_update(data), loop)


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
STATIC_DIR  = BASE_DIR / "static"
MAP_DIR     = BASE_DIR.parent / "maps"
WEB_UI_DIR  = BASE_DIR.parent / "Web_UI" / "assets"
MAP_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static",  StaticFiles(directory=STATIC_DIR,  html=True), name="static")
app.mount("/maps",    StaticFiles(directory=MAP_DIR),                 name="maps")
app.mount("/ui",      StaticFiles(directory=WEB_UI_DIR,  html=True), name="web_ui")

@app.get("/journal")
async def serve_journal():
    """Trang Nhật ký hệ thống."""
    return FileResponse(WEB_UI_DIR / "journal.html")

@app.get("/api/map/slam-image/{map_id}")
async def get_slam_image_flipped(map_id: str):
    """Trả về ảnh SLAM đã flip ngang (horizontal mirror) để dùng trong map editor."""
    import io
    img_path = MAP_DIR / f"{map_id}.png"
    if not img_path.exists():
        raise HTTPException(status_code=404, detail=f"Image not found: {map_id}.png")
    try:
        from PIL import Image as PILImage
        img = PILImage.open(img_path).convert("RGBA")
        flipped = img.transpose(PILImage.Transpose.FLIP_LEFT_RIGHT)
        buf = io.BytesIO()
        flipped.save(buf, format="PNG")
        buf.seek(0)
        return StreamingResponse(buf, media_type="image/png",
                                 headers={"Cache-Control": "max-age=3600"})
    except ImportError:
        pass
    try:
        import cv2
        img_cv = cv2.imread(str(img_path))
        flipped_cv = cv2.flip(img_cv, 1)
        _, buf_cv = cv2.imencode(".png", flipped_cv)
        return StreamingResponse(io.BytesIO(buf_cv.tobytes()), media_type="image/png",
                                 headers={"Cache-Control": "max-age=3600"})
    except ImportError:
        pass
    return FileResponse(img_path)  # fallback: ảnh gốc nếu không có PIL/cv2


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
async def home_redirect(request: Request):
    host = request.url.hostname
    return RedirectResponse(url=f"http://{host}:8050/home")

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
            # LINE AGV không nằm trong agv_manager — dùng _dispatch_go_to thay thế
            from agv_registry import agv_registry
            if agv_registry.is_line(cmd.agv_id):
                try:
                    ok = await asyncio.to_thread(
                        _dispatch_go_to, cmd.agv_id, cmd.destination,
                        start_node=None, session_id=cmd.session_id or None
                    )
                    order_id = str(uuid.uuid4())
                    # Sau lệnh cuối của batch → tự về sạc
                    if cmd.return_to_charge:
                        from task_queue import agv_task_queue as _tq, CMD_GO_CHARGE
                        _tq.dispatch_or_queue(cmd.agv_id, CMD_GO_CHARGE, session_id=cmd.session_id or None)
                        print(f"[API] {cmd.agv_id}: return_to_charge queued sau session={cmd.session_id}")
                    return {"orderId": order_id, "status": "dispatched", "agv_type": "LINE"}
                except Exception as _le:
                    raise HTTPException(status_code=400, detail=f"LINE AGV dispatch lỗi: {_le}")
            raise HTTPException(status_code=404, detail=f"AGV '{cmd.agv_id}' không tồn tại")

        # Warn if AGV state is stale but do not block the order — let MQTT handle delivery.
        last_seen_mono = agv.get("last_seen_mono")
        if last_seen_mono is None or time.monotonic() - float(last_seen_mono) > 30.0:
            print(f"[ORDER][WARN] AGV {cmd.agv_id} last_seen_mono={last_seen_mono} — may be offline, sending order anyway")

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
        start_node = _normalize_graph_node_id(start_node, map_manager.graph) or str(start_node)
        dest_node = _normalize_graph_node_id(cmd.destination, map_manager.graph) or str(cmd.destination)

        ensure_traffic_topology_from_loaded_map(str(map_id))
        order_id = str(uuid.uuid4())
        planner_route = None
        external_path: list[str]

        if cmd.path:
            requested_nodes: list[str] = []
            for raw_node in cmd.path:
                normalized = _normalize_graph_node_id(raw_node, map_manager.graph)
                if not normalized:
                    raise HTTPException(status_code=400, detail=f"Node trong path khong hop le: {raw_node}")
                normalized = str(normalized)
                if not requested_nodes or requested_nodes[-1] != normalized:
                    requested_nodes.append(normalized)

            if not requested_nodes:
                raise HTTPException(status_code=400, detail="Path rong")

            if requested_nodes[0] != str(start_node):
                requested_nodes.insert(0, str(start_node))
            if requested_nodes[-1] != str(dest_node):
                requested_nodes.append(str(dest_node))

            planner_route = traffic_engine.activate_route_from_node_path(
                agv_id=cmd.agv_id,
                map_id=str(map_id),
                node_path=requested_nodes,
                current_hint_node=agv.get("lastNodeId"),
                reason="API_MOVE_PATH",
            )
            if planner_route is None:
                raise HTTPException(status_code=409, detail="Khong kich hoat duoc route tu path yeu cau")
            external_path = _format_path_for_agv_node_ids(
                _route_to_node_path(planner_route),
                agv.get("lastNodeId"),
            )
        else:
            blocked_edges = traffic_engine.get_reserved_edges(str(map_id), exclude_agv=cmd.agv_id)
            planner_result = traffic_engine.plan_route(
                map_id=str(map_id),
                agv_id=cmd.agv_id,
                start_node=str(start_node),
                goal_node=str(dest_node),
                blocked_edges=blocked_edges,
                reason="API_MOVE",
            )
            if not planner_result.success or planner_result.route is None:
                raise HTTPException(status_code=409, detail=f"Khong tim thay duong (co the bi AGV khac khoa) tu {start_node} den {dest_node}")
            planner_route = planner_result.route
            traffic_engine.activate_route(cmd.agv_id, str(map_id), planner_route)
            external_path = _format_path_for_agv_node_ids(
                _route_to_node_path(planner_route),
                agv.get("lastNodeId"),
            )
            if len(external_path) < 2:
                return {
                    "status": "AGV already at destination",
                    "orderId": order_id,
                    "path": external_path,
                    "agv": cmd.agv_id,
                    "destination": dest_node,
                }
        # Immediate conflict pre-emption removed: _apply_immediate_route_controls and
        # _apply_immediate_head_on_assignment called evaluate_map_controls synchronously,
        # blocking the event loop for several seconds with 3+ active routes and generating
        # false PAUSE actions. Traffic control is handled reactively by the MQTT handler.
        # Build order theo full path (VDA5050)
        # chuẩn bị coords cho nodePosition
        coords_lookup = {}
        if getattr(map_manager, "points", None):
            for k, v in map_manager.points.items():
                coords_lookup[str(k)] = (v[0], v[1], 0.0)
                coords_lookup[f"N{str(k)}"] = (v[0], v[1], 0.0)
        order = build_order(
            agv_id=cmd.agv_id,
            path=external_path,
            coords=coords_lookup,
            manufacture=agv.get("manufacturer", "TNG:TOT"),
            SerialNumber=agv.get("serialNumber", cmd.agv_id),
            version="2.0",
            order_id=order_id,
            order_update_id=0,
            horizon=None  # release toàn bộ, có thể giảm nếu muốn incremental
        )

        agv_manager.set_order(cmd.agv_id, order_id, 0)
        edge_coordinator.release(cmd.agv_id)
        send_order(cmd.agv_id, order)

        print(f"[ORDER] THÀNH CÔNG! Order: {order_id[:8]} → {dest_node}")

        # BROADCAST: Có người vừa gửi lệnh di chuyển
        asyncio.create_task(broadcast_update({
            "type": "external_command",
            "action": "MOVE",
            "agv_id": cmd.agv_id,
            "destination": dest_node,
            "path": external_path,
            "order_id": order_id[:8],
            "timestamp": datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).isoformat()
        }))

        return {
            "status": "Order sent successfully",
            "orderId": order_id,
            "path": external_path,
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
        schedule_broadcast_update({
            "type": "external_command",
            "action": req.action_type,
            "agv_id": req.agv_id,
            "timestamp": datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).isoformat()
        })

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
    traffic_engine.release_agv(req.agv_id)
    return {"status": "OK", "message": f"Đã giải phóng khóa đường cho {req.agv_id}"}

# ==========================
# EXPORT MAP → LINE AGV (map_data.json) + VDA5050 topology reload
# ==========================

_LINE_AGV_MAP_PATH = os.path.join(
    os.path.dirname(__file__), "..",
    "AGV_NewVersion - Copy", "AGV_NewVersion - Copy",
    "python-manager", "config", "map_data.json"
)

# move_direction từ Web UI → w (weight/directionality) trong map_data.json
# 0=both → w=1 (bidirectional: planner add cả 2 chiều)
# 1=forward → w=2 (1 chiều u→v)
# 2=backward → w=2 (1 chiều v→u, đảo u/v khi tạo edge)
# 3=blocked → bỏ qua
_MDIR_TO_W = {0: 1, 1: 2, 2: 2, 3: None}

# locationType → type/role cho Line AGV
_LOC_TYPE_MAP = {
    "CHARGER": ("station", "charger"),
    "CONVEYOR": ("station", "pickup"),
    "DROPOFF": ("station", "dropoff"),
    "HOME": ("station", "home"),
    "BUFFER": ("normal", "wait"),
    "PARKING": ("normal", "parking"),
}


def _build_line_agv_map(points: list, roads: list, benziers: list = None) -> dict:
    """Convert từ DB format → map_data.json format cho Line AGV."""
    import json as _json

    nodes = {}
    for p in points:
        nid = str(p["name_id"])
        action = p.get("action") or {}
        if isinstance(action, str):
            try:
                action = _json.loads(action)
            except Exception:
                action = {}
        loc_type = str(action.get("locationType") or "").upper()
        node_type, node_role = _LOC_TYPE_MAP.get(loc_type, ("normal", None))
        entry = {
            "x": float(p["x"]),
            "y": float(p["y"]),
            "disp_x": float(p["x"]),
            "disp_y": float(p["y"]),
            "type": node_type,
        }
        if node_role:
            entry["role"] = node_role
        if p.get("name"):
            entry["name"] = p["name"]
        entry["actions"] = []
        nodes[nid] = entry

    def _road_to_edge(r, is_bezier=False):
        src = str(r["id_source"])
        dst = str(r["id_dest"])
        mdir = int(r.get("move_direction") or 0)
        w = _MDIR_TO_W.get(mdir)
        if w is None:
            return None  # blocked → skip
        speed_ms = float(r.get("speed") or 0.5)
        p_val = int(speed_ms * 100) if speed_ms > 0 else 0

        if is_bezier:
            # Tính khoảng cách từ tọa độ đầu-cuối
            try:
                dx = float(r["point_end_x"]) - float(r["point_start_x"])
                dy = float(r["point_end_y"]) - float(r["point_start_y"])
                dist = round((dx**2 + dy**2) ** 0.5, 3)
            except Exception:
                dist = 1.0
        else:
            dist = float(r.get("distance") or 1.0)

        if mdir == 2:  # backward → đảo u/v
            src, dst = dst, src

        edge_entry = {"u": _to_int(src), "v": _to_int(dst), "w": w, "a": 3, "p": p_val}
        if dist and dist != 1.0:
            edge_entry["distance"] = dist
        return edge_entry

    edges = []
    for r in roads:
        e = _road_to_edge(r, is_bezier=False)
        if e:
            edges.append(e)
    for b in (benziers or []):
        e = _road_to_edge(b, is_bezier=True)
        if e:
            edges.append(e)

    return {"nodes": nodes, "edges": edges}


def _to_int(node_id: str):
    """Cố gắng convert node_id sang int (Line AGV dùng int tag); fallback về string."""
    try:
        return int(node_id)
    except (ValueError, TypeError):
        return node_id


class MapExportRequest(BaseModel):
    map_id: str


@app.post("/api/map/export")
async def export_map(req: MapExportRequest, request: Request):
    """
    Đồng bộ bản đồ từ DB sang:
    1. Line AGV: ghi ra map_data.json (với edge speed, direction)
    2. VDA5050: invalidate topology cache → rebuild lần sau khi cần
    """
    pool = request.app.state.db_pool
    if not pool:
        raise HTTPException(status_code=503, detail="Database pool not initialized")

    map_id = str(req.map_id).strip()
    if not map_id:
        raise HTTPException(status_code=400, detail="map_id is required")

    # ── Load từ DB ─────────────────────────────────────────────────────────────
    try:
        async with pool.acquire() as conn:
            points_rows = await conn.fetch(
                "SELECT name_id, x, y, name, action FROM agv_map_points WHERE CAST(map_id AS TEXT)=$1",
                map_id,
            )
            roads_rows = await conn.fetch(
                "SELECT id_source, id_dest, speed, move_direction, distance, width "
                "FROM agv_map_roads WHERE CAST(map_id AS TEXT)=$1",
                map_id,
            )
            benziers_rows = await conn.fetch(
                "SELECT id_source, id_dest, speed, move_direction, "
                "point_start_x, point_start_y, point_end_x, point_end_y "
                "FROM agv_map_benziers WHERE CAST(map_id AS TEXT)=$1",
                map_id,
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB query failed: {e}")

    points   = [dict(r) for r in points_rows]
    roads    = [dict(r) for r in roads_rows]
    benziers = [dict(r) for r in benziers_rows]

    if not points:
        raise HTTPException(status_code=404, detail=f"Map {map_id} not found or has no points")

    result = {"map_id": map_id, "nodes": len(points), "edges": len(roads) + len(benziers)}

    # ── 1. Export cho Line AGV ─────────────────────────────────────────────────
    line_map = _build_line_agv_map(points, roads, benziers)
    try:
        line_path = os.path.abspath(_LINE_AGV_MAP_PATH)
        os.makedirs(os.path.dirname(line_path), exist_ok=True)
        import json as _json
        with open(line_path, "w", encoding="utf-8") as f:
            _json.dump(line_map, f, ensure_ascii=False, indent=2)
        result["line_agv_export"] = f"OK → {line_path}"
        print(f"[MAP_EXPORT] Line AGV map_data.json saved: {line_path} "
              f"({len(line_map['nodes'])} nodes, {len(line_map['edges'])} edges)")
    except Exception as e:
        result["line_agv_export"] = f"ERROR: {e}"
        print(f"[MAP_EXPORT] Line AGV export failed: {e}")

    # ── 2. VDA5050: invalidate topology cache + reload map_manager ─────────────
    try:
        # Xóa context cũ khỏi traffic engine → lần sau gọi ensure_topology sẽ rebuild với speed mới
        with traffic_engine._lock:
            traffic_engine._contexts.pop(map_id, None)
        result["vda5050_topology"] = "cache_invalidated"
    except Exception as e:
        result["vda5050_topology"] = f"warn: {e}"

    # Force reload map_manager để có roads data với speed đầy đủ
    try:
        map_manager.current_map_id = None   # buộc load lại
        await map_manager.load_from_db(pool, map_id)
        result["vda5050_map_manager"] = "reloaded"
    except Exception as e:
        result["vda5050_map_manager"] = f"warn: {e}"

    return {"status": "ok", **result}


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
            SELECT name_id, name, x, y, action, type, speed
            FROM agv_map_points
            WHERE map_id = $1
        """, map_id)

        # Lấy roads
        roads = await conn.fetch("""
            SELECT id_source, id_dest,
                   point_start_x, point_start_y,
                   point_end_x, point_end_y,
                   move_direction, width, speed, distance
            FROM agv_map_roads
            WHERE map_id = $1
        """, map_id)

        # Lấy bezier curves
        benziers = await conn.fetch("""
            SELECT id_source, id_dest,
                   point_start_x, point_start_y,
                   point_end_x, point_end_y,
                   curve_point_start_x, curve_point_start_y,
                   curve_point_end_x, curve_point_end_y,
                   move_direction, width, speed
            FROM agv_map_benziers
            WHERE map_id = $1
        """, map_id)

        return {
            "id": map_info["id"],
            "name": map_info["name"] or "Không tên",
            "origin_x": map_info["origin_x"],
            "origin_y": map_info["origin_y"],
            "origin_theta": map_info["origin_theta"],
            "image_path": f"/maps/{map_info['id']}.png" if map_info['image_path'] else None,
            "robot_points": [
                {
                    "name_id": str(p["name_id"]),
                    "name": p["name"],
                    "x": float(p["x"]),
                    "y": float(p["y"]),
                    "type": int(p["type"]) if p["type"] is not None else 0,
                    "speed": float(p["speed"]) if p["speed"] is not None else 0.5,
                    "action": p["action"] if p["action"] is not None else None,
                }
                for p in points
            ],
            "roads": [dict(r) for r in roads],
            "benziers": [dict(b) for b in benziers],
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

    # Xây action_json đầy đủ — lưu tất cả fields từ frontend
    action_json: dict = {}

    def _s(key, upper=False, lower=False):
        v = (config.get(key) or "").strip()
        if not v or v.lower() == "none":
            return
        action_json[key] = v.upper() if upper else (v.lower() if lower else v)

    _s("locationType",  upper=True)
    _s("defaultAction", upper=True)
    _s("agvCompat")
    _s("arrival_action", lower=True)
    _s("approach_dir",   lower=True)
    _s("fwd_turn",       lower=True)
    _s("bwd_turn",       lower=True)
    # Block (vùng tới hạn openTCS-style): tên block + loại (single/same_dir)
    _s("block")                       # tên block (vd 'JX_2', 'corridor_A')
    _s("block_type", lower=True)      # 'single' (1 xe) | 'same_dir' (cùng chiều)
    # supply_group: list hoặc string (tương thích cả 2 format cũ/mới)
    sg_raw = config.get("supply_group")
    if isinstance(sg_raw, list):
        sg_list = [s.strip() for s in sg_raw if isinstance(s, str) and s.strip()]
        if sg_list:
            action_json["supply_group"] = sg_list
    elif isinstance(sg_raw, str) and sg_raw.strip():
        # Backward-compat: chuỗi cũ → chuyển thành list
        action_json["supply_group"] = [s.strip() for s in sg_raw.split(",") if s.strip()]

    # turn_map (dict)
    tm = config.get("turn_map")
    if isinstance(tm, dict) and tm:
        action_json["turn_map"] = tm

    # team (int, chỉ dùng cho DROPOFF)
    team_raw = config.get("team")
    if team_raw is not None:
        try:
            action_json["team"] = int(team_raw)
        except (ValueError, TypeError):
            pass

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


@router.get("/supply-groups")
async def get_supply_groups(map_id: str, request: Request):
    """Trả về danh sách các tổ cấp hàng và node tương ứng.
    Mỗi (node, tổ) là 1 entry riêng — 1 node có thể phục vụ nhiều tổ."""
    pool = request.app.state.db_pool
    import json as _json
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT name_id, name, action
            FROM public.agv_map_points
            WHERE map_id = $1
              AND action IS NOT NULL
              AND action->'supply_group' IS NOT NULL
            ORDER BY name_id
            """,
            map_id,
        )
    result = []
    for row in rows:
        act = row["action"] or {}
        if isinstance(act, str):
            try:
                act = _json.loads(act)
            except Exception:
                act = {}
        sg = act.get("supply_group")
        if not sg:
            continue
        # Chuẩn hóa: cả array lẫn string cũ đều xử lý được
        if isinstance(sg, list):
            groups = [s.strip() for s in sg if isinstance(s, str) and s.strip()]
        elif isinstance(sg, str):
            groups = [s.strip() for s in sg.split(",") if s.strip()]
        else:
            continue
        for g in groups:
            result.append({
                "node_id":        str(row["name_id"]),
                "node_name":      row["name"] or str(row["name_id"]),
                "supply_group":   g,
                "arrival_action": act.get("arrival_action", ""),
            })
    result.sort(key=lambda x: (x["supply_group"], int(x["node_id"]) if x["node_id"].isdigit() else x["node_id"]))
    return {"supply_groups": result, "map_id": map_id}


@app.options("/api/agv/map/upload-full")
async def upload_full_preflight():
    return JSONResponse({}, headers={
        "Access-Control-Allow-Origin":  "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
    })


@app.post("/api/agv/map/upload-full")
async def agv_upload_full_json(request: Request):
    global last_map_id
    _CORS = {"Access-Control-Allow-Origin": "*"}

    try:
        payload = await request.json()
    except Exception as e:
        print("Lỗi parse JSON:", e)
        return JSONResponse({"error": "Invalid JSON", "detail": str(e)}, status_code=400, headers=_CORS)

    try:
        _upload_result = await _do_upload_map(payload)
        return JSONResponse(_upload_result, headers=_CORS)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[UPLOAD-MAP ERROR] {e}")
        return JSONResponse({"error": str(e)}, status_code=500, headers=_CORS)


async def _do_upload_map(payload: dict):
    global last_map_id

    print("[UPLOAD-MAP] Nhận payload, đang xử lý...")

    # ================== AUTO-CREATE TABLES IF NOT EXIST ==================
    if pool is None:
        raise Exception("Database pool chưa khởi tạo")
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS agv_maps (
                id           TEXT PRIMARY KEY,
                name         TEXT,
                origin_x     FLOAT DEFAULT 0,
                origin_y     FLOAT DEFAULT 0,
                origin_theta FLOAT DEFAULT 0,
                image_path   TEXT,
                modify_time  TIMESTAMPTZ DEFAULT NOW(),
                layer        INT DEFAULT 0,
                updated_at   TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS agv_map_points (
                id        SERIAL PRIMARY KEY,
                map_id    TEXT REFERENCES agv_maps(id) ON DELETE CASCADE,
                name_id   TEXT,
                name      TEXT,
                x         FLOAT, y FLOAT, theta FLOAT DEFAULT 0,
                type      INT DEFAULT 0,
                zone      TEXT DEFAULT '',
                action    JSONB DEFAULT '{}',
                speed     FLOAT DEFAULT 0.5,
                carrier   INT DEFAULT 0,
                available BOOLEAN DEFAULT FALSE,
                accuracy  INT DEFAULT 0
            )
        """)
        # Index hỗ trợ query nhanh team mapping (action->>'team')
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_map_points_team
            ON agv_map_points ((action->>'team'))
            WHERE action->>'locationType' = 'DROPOFF'
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS agv_map_roads (
                id             SERIAL PRIMARY KEY,
                map_id         TEXT REFERENCES agv_maps(id) ON DELETE CASCADE,
                name           TEXT DEFAULT '',
                id_source      TEXT, id_dest TEXT,
                point_start_x  FLOAT, point_start_y FLOAT,
                point_end_x    FLOAT, point_end_y FLOAT,
                width          FLOAT DEFAULT 0.95,
                speed          FLOAT DEFAULT 0.3,
                move_direction INT DEFAULT 0,
                distance       FLOAT DEFAULT 0,
                lidar_off      BOOLEAN DEFAULT FALSE,
                lidar_off_dir  TEXT DEFAULT 'none'
            )
        """)
        await conn.execute("""
            ALTER TABLE agv_map_roads
            ADD COLUMN IF NOT EXISTS lidar_off BOOLEAN DEFAULT FALSE
        """)
        await conn.execute("""
            ALTER TABLE agv_map_roads
            ADD COLUMN IF NOT EXISTS lidar_off_dir TEXT DEFAULT 'none'
        """)
        await conn.execute("""
            ALTER TABLE agv_map_roads
            ADD COLUMN IF NOT EXISTS speed_bwd FLOAT
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS agv_map_benziers (
                id                    SERIAL PRIMARY KEY,
                map_id                TEXT REFERENCES agv_maps(id) ON DELETE CASCADE,
                name                  TEXT DEFAULT '',
                id_source             TEXT, id_dest TEXT,
                point_start_x         FLOAT, point_start_y FLOAT,
                point_end_x           FLOAT, point_end_y FLOAT,
                curve_point_start_x   FLOAT, curve_point_start_y FLOAT,
                curve_point_end_x     FLOAT, curve_point_end_y FLOAT,
                width                 FLOAT DEFAULT 0.3,
                speed                 FLOAT DEFAULT 0.3,
                move_direction        INT DEFAULT 0,
                lidar_off             BOOLEAN DEFAULT FALSE,
                lidar_off_dir         TEXT DEFAULT 'none'
            )
        """)
        await conn.execute("""
            ALTER TABLE agv_map_benziers
            ADD COLUMN IF NOT EXISTS lidar_off BOOLEAN DEFAULT FALSE
        """)
        await conn.execute("""
            ALTER TABLE agv_map_benziers
            ADD COLUMN IF NOT EXISTS lidar_off_dir TEXT DEFAULT 'none'
        """)
        await conn.execute("""
            ALTER TABLE agv_map_benziers
            ADD COLUMN IF NOT EXISTS speed_bwd FLOAT
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS agv_map_codes (
                id      SERIAL PRIMARY KEY,
                map_id  TEXT REFERENCES agv_maps(id) ON DELETE CASCADE,
                code_id TEXT, code TEXT,
                x FLOAT, y FLOAT, theta FLOAT DEFAULT 0
            )
        """)

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
    if pool is None:
        raise HTTPException(status_code=503, detail="Database pool chưa khởi tạo")
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
                # Đảm bảo action là JSON string trước khi insert vào cột jsonb
                _action = p.get("action")
                if isinstance(_action, dict):
                    _action = json.dumps(_action, ensure_ascii=False)
                elif _action is None:
                    _action = "{}"
                await conn.execute("""
                    INSERT INTO agv_map_points
                    (map_id, name_id, name, x, y, theta, type, zone, action, speed, carrier, available, accuracy)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,$10,$11,$12,$13)
                """, map_id,
                    str(p.get("name_id", "")),
                    p.get("name", ""),
                    p.get("x"), p.get("y"), p.get("theta"),
                    p.get("type", 0), p.get("zone", ""), _action,
                    float(p.get("speed", 0.5)),
                    p.get("carrier", 0), p.get("available", False), p.get("accuracy", 0))

            # Lưu roads (có thể rỗng)
            roads = payload.get("robot_roads", [])
            for r in roads:
                point_start = r.get("point_start", [0, 0])
                point_end = r.get("point_end", [0, 0])
                _speed_bwd = r.get("speed_bwd")
                _speed_bwd = float(_speed_bwd) if _speed_bwd not in (None, "") else None
                await conn.execute("""
                    INSERT INTO agv_map_roads
                    (map_id, name, id_source, id_dest,
                     point_start_x, point_start_y, point_end_x, point_end_y,
                     width, speed, move_direction, distance, lidar_off, lidar_off_dir, speed_bwd)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
                """, map_id, r.get("name", ""),
                    str(r["id_source"]), str(r["id_dest"]),
                    point_start[0], point_start[1],
                    point_end[0], point_end[1],
                    r.get("width", 0.95), r.get("speed", 0.3),
                    r.get("move_direction", 0), r.get("distance", 0),
                    bool(r.get("lidar_off", False)),
                    str(r.get("lidar_off_dir") or "none"),
                    _speed_bwd)

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
                    _b_speed_bwd = b.get("speed_bwd")
                    _b_speed_bwd = float(_b_speed_bwd) if _b_speed_bwd not in (None, "") else None
                    await conn.execute("""
                        INSERT INTO agv_map_benziers (
                            map_id, name, id_source, id_dest,
                            point_start_x, point_start_y, point_end_x, point_end_y,
                            curve_point_start_x, curve_point_start_y, curve_point_end_x, curve_point_end_y,
                            width, speed, move_direction, lidar_off, lidar_off_dir, speed_bwd
                        )
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18)
                    """, map_id, b.get("name", ""),
                        str(b["id_source"]), str(b["id_dest"]),
                        point_start[0], point_start[1],
                        point_end[0], point_end[1],
                        curve_point_start[0], curve_point_start[1],
                        curve_point_end[0], curve_point_end[1],
                        b.get("width", 0.3), b.get("speed", 0.3),
                        b.get("move_direction", 0), bool(b.get("lidar_off", False)),
                        str(b.get("lidar_off_dir") or "none"),
                        _b_speed_bwd
                    )
            # =========================================================================

    print(f"Upload map thành công! ID: {map_id} | Tên: {map_name} | Points: {len(points)} | Roads: {len(roads)} | Benziers: {len(benziers)}")

    return {
        "status": "success",
        "map_id": map_id,
        "map_name": map_name,
        "image_saved": image_path,
        "points": len(points),
        "roads": len(roads),
        "codes": len(codes),
        "benziers": len(benziers),
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
    Cập nhật tất cả task pending/running của AGV thành cancelled trong DB.
    """
    try:
        print(f"[API] Nhận lệnh hủy order: AGV={req.agv_id}")

        result = await asyncio.to_thread(cancel_agv_order, req.agv_id)

        # Xóa in-memory task queue (queue_size về 0 ngay lập tức)
        from task_queue import agv_task_queue as _tq
        _tq.cancel_all(req.agv_id)
        _cancel_pending_locate_then_charge(req.agv_id)

        # Cập nhật DB: đánh dấu tất cả task pending/running của AGV thành cancelled
        if pool:
            async with pool.acquire() as conn:
                status_str = await conn.execute(
                    """UPDATE agv_tasks
                       SET status = 'cancelled', updated_at = NOW()
                       WHERE agv_id = $1 AND status IN ('pending', 'running')""",
                    req.agv_id,
                )
                # status_str dạng "UPDATE N"
                print(f"[CANCEL] DB update: {status_str} task → cancelled cho AGV {req.agv_id}")

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

@app.post("/api/agv/set-tag")
async def api_set_tag(req: SetTagRequest):
    """Gán thủ công vị trí AGV (node RFID) khi khởi động hoặc cần căn chỉnh."""
    try:
        node_id_str = str(req.node_id).strip()
        if not node_id_str.lstrip("-").isdigit():
            raise HTTPException(400, f"node_id không hợp lệ: {req.node_id!r}")

        tag_int = int(node_id_str)

        from line_agv_handler import line_agv_handler as _lah
        _lah.override_position(req.agv_id, tag_int)

        # Lưu vào DB để restore sau khi server restart
        if pool:
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE agv_devices SET last_tag=$1 WHERE name=$2",
                    node_id_str, req.agv_id,
                )

        print(f"[SET_TAG] {req.agv_id}: gán thủ công vị trí → node {tag_int}")
        return {"success": True, "agv_id": req.agv_id, "node_id": tag_int}

    except HTTPException:
        raise
    except Exception as e:
        print("[ERROR] /api/agv/set-tag:", e)
        raise HTTPException(status_code=400, detail=str(e))


# ==========================
# MOBILE APP AUTH (no real auth — local network only)
# ==========================

@app.post("/api/auth/login")
async def mobile_auth_login(request: Request):
    """Login endpoint cho mobile app. Hệ thống local network không cần auth thật.
    Nhận bất kỳ username nào và trả token giả để mobile tiếp tục."""
    try:
        data = await request.json()
    except Exception:
        data = {}
    username = str(data.get("username", "operator")).strip() or "operator"
    return {
        "success": True,
        "token": f"acs-mobile-{username}",
        "user": {
            "name": username,
            "maNS": username,
            "tenDonVi": "TOT ACS",
            "tenPhongBan": "AGV Control",
            "maChiNhanh": "1",
        }
    }


# ==========================
# TASK MANAGER API
# ==========================

@app.get("/api/tasks")
async def get_tasks(limit: int = 200, status: str = None):
    async with pool.acquire() as conn:
        if status and status != "all":
            rows = await conn.fetch(
                "SELECT * FROM agv_tasks WHERE status=$1 ORDER BY created_at DESC LIMIT $2",
                status, limit,
            )
        else:
            rows = await conn.fetch(
                "SELECT * FROM agv_tasks ORDER BY created_at DESC LIMIT $1", limit
            )
    return [
        {**dict(r), "created_at": r["created_at"].isoformat(), "updated_at": r["updated_at"].isoformat()}
        for r in rows
    ]


@app.post("/api/tasks")
async def create_task(request: Request):
    if not pool:
        raise HTTPException(503, "Database chưa sẵn sàng")

    data = await request.json()
    agv_id        = (data.get("agv_id") or "").strip()
    destination   = (data.get("destination") or "").strip()
    map_id        = (data.get("map_id") or "").strip() or None
    notes         = (data.get("notes") or "").strip()
    operator_name    = (data.get("operator_name") or "").strip() or None
    operator_id      = (data.get("operator_id") or "").strip() or None
    session_id       = (data.get("session_id") or "").strip() or None
    return_to_charge = bool(data.get("return_to_charge", False))
    send_order       = data.get("send_order", True)
    # Thông tin đơn hàng từ WMS (tuỳ chọn): {"product_code": ..., "type": ..., "quantity": ...}
    raw_order_info = data.get("order_info")
    import json as _json
    if isinstance(raw_order_info, dict) and raw_order_info:
        order_info = _json.dumps(raw_order_info, ensure_ascii=False)
    elif isinstance(raw_order_info, str) and raw_order_info.strip():
        order_info = raw_order_info.strip()
    else:
        order_info = None

    if not agv_id or not destination:
        raise HTTPException(400, "agv_id và destination là bắt buộc")

    print(f"[TASK] {agv_id}→{destination} | operator={operator_name!r} id={operator_id!r} | raw_keys={list(data.keys())}")

    import uuid as _uuid
    task_id = str(_uuid.uuid4())

    # Luôn INSERT vào DB trước — dù gửi lệnh thành công hay không
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO agv_tasks (task_id, agv_id, destination, map_id, status, notes, operator_name, operator_id, order_info) "
                "VALUES ($1,$2,$3,$4,'pending',$5,$6,$7,$8::jsonb)",
                task_id, agv_id, destination, map_id, notes, operator_name, operator_id, order_info,
            )
    except Exception as e:
        print(f"[TASK] INSERT thất bại: {e}")
        raise HTTPException(500, f"Lỗi lưu DB: {e}")

    # Các điểm đặc biệt (WAIT, CHARGE…) → chỉ lưu, không gửi /order
    VIRTUAL_DESTINATIONS = {"WAIT", "CHARGE", "HOME", "STANDBY"}
    if destination.upper() in VIRTUAL_DESTINATIONS or not send_order:
        return {"task_id": task_id, "status": "pending", "order_id": ""}

    # Gửi lệnh di chuyển thực sự
    try:
        cmd = MoveCommand(agv_id=agv_id, destination=destination, map_id=map_id,
                          session_id=session_id, return_to_charge=return_to_charge)
        result = await move_agv(cmd)
        order_id = result.get("orderId", "")
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE agv_tasks SET status='running', order_id=$1, updated_at=NOW() WHERE task_id=$2",
                order_id, task_id,
            )
        return {"task_id": task_id, "status": "running", "order_id": order_id}
    except HTTPException as e:
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE agv_tasks SET status='failed', updated_at=NOW() WHERE task_id=$1", task_id
            )
        asyncio.create_task(integration_engine.fire_callbacks(
            task_id, "failed",
            {"task_id": task_id, "agv_id": agv_id, "destination": destination,
             "map_id": map_id, "status": "failed", "operator_name": operator_name, "operator_id": operator_id}
        ))
        return {"task_id": task_id, "status": "failed", "error": e.detail}
    except Exception as e:
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE agv_tasks SET status='failed', updated_at=NOW() WHERE task_id=$1", task_id
            )
        asyncio.create_task(integration_engine.fire_callbacks(
            task_id, "failed",
            {"task_id": task_id, "agv_id": agv_id, "destination": destination,
             "map_id": map_id, "status": "failed", "operator_name": operator_name, "operator_id": operator_id}
        ))
        return {"task_id": task_id, "status": "failed", "error": str(e)}


@app.post("/api/tasks/{task_id}/cancel")
async def cancel_task(task_id: str):
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM agv_tasks WHERE task_id=$1", task_id)
        if not row:
            raise HTTPException(404, "Task không tồn tại")
        await conn.execute(
            "UPDATE agv_tasks SET status='cancelled', updated_at=NOW() WHERE task_id=$1", task_id
        )
    try:
        await asyncio.to_thread(cancel_agv_order, row["agv_id"])
    except Exception:
        pass
    asyncio.create_task(
        integration_engine.fire_callbacks(task_id, "cancelled", dict(row) | {"status": "cancelled"})
    )
    return {"status": "cancelled", "task_id": task_id}


@app.post("/api/tasks/{task_id}/done")
async def mark_task_done(task_id: str):
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE agv_tasks SET status='done', updated_at=NOW() WHERE task_id=$1", task_id
        )
        row = await conn.fetchrow("SELECT * FROM agv_tasks WHERE task_id=$1", task_id)
    asyncio.create_task(
        integration_engine.fire_callbacks(task_id, "completed", dict(row) if row else {"task_id": task_id, "status": "done"})
    )
    return {"status": "done", "task_id": task_id}


# ══════════════════════════════════════════════════════════════════════════════
# INTEGRATION API
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/integrations")
async def api_list_integrations():
    return await integration_engine.list_integrations()

@app.post("/api/integrations")
async def api_create_integration(request: Request):
    data = await request.json()
    try:
        result = await integration_engine.create_integration(data)
        return result
    except Exception as e:
        raise HTTPException(400, str(e))

@app.get("/api/integrations/{conn_id}")
async def api_get_integration(conn_id: str):
    row = await integration_engine.get_integration(conn_id)
    if not row:
        raise HTTPException(404, "Không tìm thấy kết nối")
    return row

@app.put("/api/integrations/{conn_id}")
async def api_update_integration(conn_id: str, request: Request):
    data = await request.json()
    result = await integration_engine.update_integration(conn_id, data)
    if not result:
        raise HTTPException(404, "Không tìm thấy kết nối")
    return result

@app.delete("/api/integrations/{conn_id}")
async def api_delete_integration(conn_id: str):
    ok = await integration_engine.delete_integration(conn_id)
    if not ok:
        raise HTTPException(404, "Không tìm thấy kết nối")
    return {"deleted": True, "conn_id": conn_id}

@app.get("/api/integrations/{conn_id}/logs")
async def api_integration_logs(conn_id: str, limit: int = 100):
    return await integration_engine.get_logs(conn_id, limit)

@app.post("/api/integrations/{conn_id}/test")
async def api_test_integration(conn_id: str):
    return await integration_engine.test_callback(conn_id)

@app.post("/api/agv/tot/{conn_id}")
async def api_webhook_inbound(conn_id: str, request: Request):
    """Endpoint nhận lệnh từ WMS/ERP."""
    # Lấy API key từ header Authorization hoặc query param
    auth_header = request.headers.get("Authorization", "")
    api_key = auth_header.replace("Bearer ", "").replace("bearer ", "").strip()
    if not api_key:
        api_key = request.query_params.get("api_key", "")
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Body phải là JSON hợp lệ")
    try:
        result = await integration_engine.handle_webhook(conn_id, api_key, body)
        # Tự động dispatch task nếu có agv_id và destination
        if result.get("agv_id") and result.get("destination"):
            try:
                cmd = MoveCommand(
                    agv_id=result["agv_id"],
                    destination=result["destination"],
                    map_id=body.get("map_id"),
                )
                mv = await move_agv(cmd)
                if pool:
                    async with pool.acquire() as _c:
                        await _c.execute(
                            "UPDATE agv_tasks SET status='running', order_id=$1 WHERE task_id=$2",
                            mv.get("orderId", ""), result["task_id"],
                        )
                result["order_id"] = mv.get("orderId", "")
                result["status"] = "running"
            except Exception as _de:
                print(f"[WEBHOOK] dispatch error: {_de}")
        return result
    except PermissionError as e:
        raise HTTPException(401, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))


# ==========================
# WORKFLOW TEMPLATE API
# ==========================

@app.get("/api/workflow-templates")
async def list_workflow_templates():
    import json as _json, traceback as _tb
    try:
        if not pool:
            return JSONResponse({"error": "Database chưa sẵn sàng"}, status_code=503)
        async with pool.acquire() as conn:
            # Tạo bảng nếu chưa tồn tại
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS agv_workflow_templates (
                    id SERIAL PRIMARY KEY,
                    template_id VARCHAR(36) DEFAULT gen_random_uuid()::text UNIQUE,
                    name VARCHAR(200) NOT NULL,
                    steps JSONB NOT NULL DEFAULT '[]',
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            rows = await conn.fetch(
                "SELECT id, template_id, name, steps, created_at, updated_at "
                "FROM agv_workflow_templates ORDER BY created_at ASC"
            )
        result = []
        for r in rows:
            steps = r["steps"]
            if isinstance(steps, str):
                try: steps = _json.loads(steps)
                except Exception: steps = []
            result.append({
                "id": r["id"],
                "template_id": r["template_id"],
                "name": r["name"],
                "steps": steps,
                "step_count": len(steps) if isinstance(steps, list) else 0,
                "created_at": r["created_at"].isoformat(),
                "updated_at": r["updated_at"].isoformat(),
            })
        return result
    except Exception as e:
        _tb.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/workflow-templates")
async def save_workflow_template(request: Request):
    import uuid as _uuid, json as _json, traceback as _tb
    try:
        if not pool:
            return JSONResponse({"error": "Database chưa sẵn sàng"}, status_code=503)

        data = await request.json()
        name        = (data.get("name") or "").strip()
        steps       = data.get("steps") or []
        template_id = (data.get("template_id") or "").strip() or str(_uuid.uuid4())

        if not name:
            return JSONResponse({"error": "Tên workflow là bắt buộc"}, status_code=400)
        if not isinstance(steps, list):
            steps = []

        async with pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS agv_workflow_templates (
                    id SERIAL PRIMARY KEY,
                    template_id VARCHAR(36) DEFAULT gen_random_uuid()::text UNIQUE,
                    name VARCHAR(200) NOT NULL,
                    steps JSONB NOT NULL DEFAULT '[]',
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            # Kiểm tra trùng tên (loại trừ chính template đang update)
            existing = await conn.fetchrow(
                "SELECT template_id FROM agv_workflow_templates WHERE name=$1 AND template_id!=$2",
                name, template_id
            )
            if existing:
                return JSONResponse(
                    {"error": f"Tên \"{name}\" đã tồn tại, vui lòng chọn tên khác"},
                    status_code=409
                )

            await conn.execute("""
                INSERT INTO agv_workflow_templates (template_id, name, steps)
                VALUES ($1, $2, $3::jsonb)
                ON CONFLICT (template_id) DO UPDATE
                    SET name=$2, steps=$3::jsonb, updated_at=NOW()
            """, template_id, name, _json.dumps(steps, ensure_ascii=False))

        print(f"[WORKFLOW] Lưu thành công: {name} | {len(steps)} bước | id={template_id[:8]}")
        return {"template_id": template_id, "name": name, "step_count": len(steps)}

    except Exception as e:
        _tb.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)


@app.delete("/api/workflow-templates/{template_id}")
async def delete_workflow_template(template_id: str):
    if not pool:
        raise HTTPException(503, "Database chưa sẵn sàng")
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM agv_workflow_templates WHERE template_id=$1", template_id
        )
    if result == "DELETE 0":
        raise HTTPException(404, "Template không tồn tại")
    return {"status": "deleted", "template_id": template_id}


@app.post("/api/agv/registry/reload")
async def reload_agv_registry():
    """
    Reload agv_registry từ bảng agv_devices trong DB.
    Gọi sau khi thêm/xóa AGV qua Web UI AGV Manager để server nhận biết ngay.
    """
    try:
        from agv_registry import agv_registry as _registry
        await asyncio.to_thread(_registry.load_from_db)
        return {
            "status": "ok",
            "line_agvs":    _registry.line_agv_ids(),
            "vda5050_agvs": _registry.vda5050_agv_ids(),
            "ip_map":       _registry.ip_index(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/agv/registry")
async def get_agv_registry():
    """Xem danh sách AGV đã đăng ký và phân loại hiện tại."""
    from agv_registry import agv_registry as _registry
    return {
        "line_agvs":    _registry.line_agv_ids(),
        "vda5050_agvs": _registry.vda5050_agv_ids(),
        "ip_map":       _registry.ip_index(),
        "total":        len(_registry.all_ids()),
    }


# ════════════════════════════════════════════════════════════════════════════
# EXECUTE TASK — AGV điều phối tức thì / hàng chờ
# ════════════════════════════════════════════════════════════════════════════

# Tracking staging/transit dispatches: khi dispatch đến staging node, đánh dấu
# để lần dispatch TIẾP THEO đến đúng staging node đó dùng task_type='transit'.
# Format: {(agv_id, staging_node_id)}
_pending_staging_transits: set = set()

# Gom lệnh cả lượt cấp hàng (Line AGV): chờ ~1s thu thập đủ các lệnh cùng session
# rồi sinh lệnh lấy hàng tại TẤT CẢ điểm cấp TRƯỚC, mới tới các lệnh giao + sạc.
# Format: {(agv_id, session_id): {"commands": [(cmd,dest,start)], "task": asyncio.Task, "session_label": str}}
_supply_batch: dict = {}
_SUPPLY_BATCH_DELAY_SEC = 1.0

def _line_agv_occupied_nodes(exclude_agv: str) -> dict[str, str]:
    """
    Trả về {node_id: agv_id} — nodes bị AGV khác chiếm.
    Bao gồm 2 trường hợp:
      1. AGV đang trong lifecycle state (picking/delivering/charging) tại node đó.
      2. AGV đang trong route với node đó là FINAL DESTINATION (đang trên đường đến).
         → Tránh "same-destination conflict": 2 xe cùng đến 1 điểm.
    """
    occupied: dict[str, str] = {}
    try:
        from line_agv_handler import line_agv_handler as _lah
        # Case 1: lifecycle state tại node hiện tại (picking/delivering/charging)
        for _oid, _st in _lah.state_store._states.items():
            if _oid == exclude_agv or _st is None:
                continue
            if _st.task_lifecycle in ('picking', 'delivering', 'charging'):
                _cur = str(_st.current_tag or "").strip()
                if _cur:
                    occupied[_cur] = _oid
        # Case 2: final destination của route đang chạy (xe đang trên đường đến)
        for _oid, _route in _lah._routes.items():
            if _oid == exclude_agv or not _route or not _route.full_path:
                continue
            if _route.task_type in ('transit',):
                continue
            _dest = str(_route.full_path[-1]).strip()
            if _dest and _dest not in occupied:
                occupied.setdefault(_dest, _oid)
        # Case 3: xe đang dừng im tại node (no active route, no lifecycle) — trạng thái
        # bounce/between-commands. Xe VẪN ĐANG CHIẾM node đó về mặt vật lý.
        # Dùng setdefault để không override Case 1/2 đã có.
        for _oid, _st in _lah.state_store._states.items():
            if _oid == exclude_agv or _st is None:
                continue
            if not _st.driving and _st.current_tag and not _st.task_lifecycle:
                # Chỉ mark occupied nếu không có route active (đang giữa 2 lệnh)
                if not _lah._routes.get(_oid):
                    _cur = str(_st.current_tag).strip()
                    if _cur:
                        occupied.setdefault(_cur, _oid)
    except Exception:
        pass
    return occupied


def _required_supply_node(node_actions: dict, dest_node) -> str | None:
    """Supply node phục vụ team của dest_node (giống Phase 0 của planner).

    Trả về node_id (str) của điểm cấp hàng cho tổ của dest_node, hoặc None nếu
    dest_node không phải dropoff có team / không có điểm cấp tương ứng.
    """
    end_na = node_actions.get(str(dest_node)) or {}
    team = end_na.get('team')
    if not team:
        return None
    team_str = str(team)
    for snid, sncfg in (node_actions or {}).items():
        sncfg = sncfg or {}
        if str(sncfg.get('arrival_action', '') or '').lower() == 'wait_sys':
            sg = sncfg.get('supply_group') or []
            if isinstance(sg, str):
                sg = [s.strip() for s in sg.split(',')]
            if team_str in [str(g) for g in sg]:
                return str(snid)
    return None


def _sort_supplies_by_distance(supplies: list[str], current_node) -> list[str]:
    """Sắp xếp các điểm cấp theo khoảng cách path từ current_node (gần → xa).

    Dùng để xe lấy hàng theo một lượt quét xuôi (điểm gần trạm trước), tránh đi
    tới-lui. Nếu không tính được khoảng cách → giữ nguyên thứ tự.
    """
    if not supplies or not current_node:
        return list(supplies)
    try:
        import networkx as _nx
        g = getattr(map_manager, 'line_graph', None) or getattr(map_manager, 'graph', None)
        if g is None:
            return list(supplies)

        def _d(s):
            try:
                return _nx.shortest_path_length(g, str(current_node), str(s), weight='weight')
            except Exception:
                return float('inf')

        return sorted(supplies, key=_d)
    except Exception:
        return list(supplies)


def _order_by_real_path(nodes: list[str], current_node) -> list[str]:
    """Sắp xếp các node theo ĐÚNG THỨ TỰ xe sẽ gặp thật trên đường đi, lấy trực
    tiếp từ đường đi THẬT (danh sách node nối tiếp nhau) tính từ current_node —
    KHÔNG suy luận qua 1 con số khoảng cách đơn thuần như _sort_supplies_by_distance.

    Lý do cần hàm riêng: trong 1 bản đồ dạng VÒNG KÍN, so khoảng cách bằng SỐ có
    thể bị sai bởi đường tắt/hướng đo (đã xảy ra thực tế: đo "khoảng cách ngược
    về staging" cho 2 node kề nhau 107→108 lại cho ra thứ tự ngược, khiến xe phải
    vòng gần hết bản đồ mới quay lại được node đã đi qua). Cách chắc chắn nhất là
    lấy thẳng danh sách node của đường đi THẬT (không phải suy luận từ con số) —
    node nào xuất hiện ở vị trí sớm hơn trên đường đi thì bắt buộc gặp trước.

    Cách làm: tính đường đi thật tới node XA NHẤT trong nhóm (path dài nhất) —
    mọi node còn lại (nếu cùng nằm trên 1 hành lang xuôi, không nhánh rẽ khác)
    sẽ tự nhiên nằm trên chính con đường đó; xếp theo đúng VỊ TRÍ chúng xuất
    hiện trên path đó.
    """
    if not nodes or not current_node:
        return list(nodes)
    if len(nodes) <= 1:
        return list(nodes)
    try:
        import networkx as _nx
        g = getattr(map_manager, 'line_graph', None) or getattr(map_manager, 'graph', None)
        if g is None:
            return list(nodes)

        paths: dict[str, list] = {}
        for n in nodes:
            try:
                paths[str(n)] = _nx.shortest_path(g, str(current_node), str(n), weight='weight')
            except Exception:
                paths[str(n)] = None
        valid = {n: p for n, p in paths.items() if p}
        if not valid:
            return list(nodes)

        farthest = max(valid, key=lambda n: len(valid[n]))
        farthest_path = valid[farthest]
        pos = {node: i for i, node in enumerate(farthest_path)}

        def _key(n):
            n = str(n)
            if n in pos:
                return (0, pos[n])
            # Không nằm trên đường đi tới node xa nhất (nhánh khác/bất thường,
            # hiếm gặp với map dạng vòng đơn) → xếp sau tất cả node xác định
            # được, theo độ dài path riêng của nó.
            return (1, len(valid.get(n) or []))

        return sorted(nodes, key=_key)
    except Exception:
        return list(nodes)


def _order_pickups_for_forward_loop(nodes: list[str], staging_node: str) -> list[str]:
    """Sắp xếp các node lấy hàng cho xe rơ-moóc (CHỈ TIẾN, không lùi được)
    theo đúng thứ tự BẮT BUỘC phải ghé trong 1 vòng — Tổ XA trạm nhất trước,
    Tổ GẦN trạm nhất cuối cùng (rồi mới thả hàng đầy tại staging_node).

    KHÔNG dùng shortest_path_length(vị_trí_hiện_tại → node) đơn thuần: bản đồ
    đường vòng cho xe rơ-moóc thường có ĐƯỜNG TẮT ở đoạn đầu (vd tại 1 vài
    node giao lộ) cho phép đi thẳng tới các Tổ GẦN trạm hơn, bỏ qua đoạn giữa
    dẫn tới các Tổ XA hơn — khiến 1 Tổ XA thật sự lại tính RA khoảng cách
    NGẮN hơn 1 Tổ gần (do có đường tắt), suy luận SAI thứ tự.
    Cũng KHÔNG dùng "khả năng tới-được" (has_path) giữa các node — vì đoạn
    gần trạm sạc thường có cạnh 2 chiều (approach_dir cả 2 hướng), tạo thành
    1 vòng kín khiến MỌI node "tới được" lẫn nhau, không phân biệt được thứ tự.

    Cách đúng và tổng quát: đo khoảng cách từ MỖI node NGƯỢC VỀ staging_node
    (điểm chắc chắn phải quay về SAU KHI đã ghé het các Tổ) — Tổ càng XA
    staging_node (phải đi qua nhiều node hơn để về tới đó) thì càng cần
    ghé TRƯỚC; Tổ càng GẦN staging_node thì ghé SAU CÙNG. Hướng đo này không
    bị ảnh hưởng bởi đường tắt ở đầu vòng (vì đường tắt chỉ có ích khi ĐI RA,
    không phải khi tính từ 1 node cụ thể NGƯỢC VỀ đích cuối).
    """
    if len(nodes) <= 1:
        return list(nodes)
    try:
        import networkx as _nx
        g = getattr(map_manager, 'line_graph', None) or getattr(map_manager, 'graph', None)
        if g is None or not staging_node:
            return list(nodes)

        def _d(n):
            try:
                return _nx.shortest_path_length(g, str(n), str(staging_node), weight='weight')
            except Exception:
                return -1.0   # không tính được → coi như gần nhất, xếp cuối

        return sorted(nodes, key=_d, reverse=True)
    except Exception:
        return list(nodes)


def _dispatch_go_to(agv_id: str, dest_node: str, start_node: str | None = None,
                    session_id: str | None = None) -> bool:
    """Tính đường + gửi order (LINE hoặc VDA5050) từ vị trí hiện tại đến dest_node.

    session_id: lượt cấp hàng hiện tại — dùng để chỉ lấy hàng MỘT lần mỗi supply
    node trong một lượt. Các lệnh giao hàng sau trong cùng session sẽ đi một mạch
    qua supply node đã lấy mà không dừng lại chờ xác nhận.
    """
    from mqtt_client import (
        get_agv_runtime_info, plan_path_for_order,
        send_agv_to_special_target, send_order,
    )
    from agv_registry import agv_registry
    info         = get_agv_runtime_info(agv_id)
    current_node = info.get("current_node")

    # Nếu không biết vị trí và có start_node từ UI → lưu vào state_store rồi dùng
    if not current_node and start_node:
        if agv_registry.is_line(agv_id):
            from line_agv_handler import line_agv_handler
            try:
                line_agv_handler.override_position(agv_id, int(start_node))
                current_node = start_node
                print(f"[DISPATCH] {agv_id}: used manual start_node={start_node}")
            except (ValueError, TypeError):
                pass

    if not current_node:
        raise ValueError(
            f"{agv_id}: không biết vị trí hiện tại — "
            f"hãy chọn 'Vị trí xuất phát' trên bản đồ trước khi gửi lệnh"
        )
    if str(current_node) == str(dest_node):
        # AGV đã ở đích rồi — coi như hoàn thành, trigger auto-dispatch lệnh tiếp
        # Thay vì raise error, notify queue để chạy lệnh kế tiếp
        print(f"[DISPATCH] {agv_id}: đã ở tại {dest_node} — auto-complete, dispatch tiếp")
        try:
            from task_queue import agv_task_queue as _atq_done
            _atq_done.on_agv_completed(agv_id, notes="already_at_dest")
        except Exception:
            pass
        return True

    _is_staging_dispatch = False   # sẽ được set True nếu staging redirect xảy ra

    # ── Bỏ qua lệnh lấy hàng đã hoàn tất trong lượt (no-op) ───────────────────
    # Khi finalize sinh lệnh go_to(điểm cấp) nhưng điểm đó đã được lấy hàng (vd do
    # split cơ hội trên đường tới điểm cấp khác) → auto-complete, không quay lại.
    if session_id and agv_registry.is_line(agv_id):
        _dest_na_skip = (getattr(map_manager, 'node_actions', {}) or {}).get(str(dest_node)) or {}
        _dest_is_supply_skip = (
            str(_dest_na_skip.get('arrival_action', '') or '').lower() == 'wait_sys'
            and bool(_dest_na_skip.get('supply_group'))
        )
        if _dest_is_supply_skip:
            from task_queue import agv_task_queue as _atq_skip
            if _atq_skip.session_has_pickup(session_id, dest_node):
                print(f"[DISPATCH] {agv_id}: điểm cấp {dest_node} đã lấy hàng trong lượt "
                      f"→ bỏ qua (auto-complete)")
                try:
                    _atq_skip.on_agv_completed(agv_id, notes="pickup_already_done")
                except Exception:
                    pass
                return True

    # ── Kiểm tra destination node đang bị AGV khác chiếm (lifecycle) ────────────
    # Thay vì đứng yên ở vị trí hiện tại (có thể rất xa), tiến gần đến đích và chờ
    # tại một "staging node" 1-3 node trước đích — giảm thời gian chờ khi đích trống.
    if agv_registry.is_line(agv_id):
        _occ = _line_agv_occupied_nodes(exclude_agv=agv_id)
        _claimer = _occ.get(str(dest_node).strip())
        # CLAIM-TỪ-XA: node đích bị coi "occupied" có thể CHỈ vì xe khác ĐANG TRÊN ĐƯỜNG
        # tới đó (Case 2 destination-claim) — xe đó CHƯA ở vật lý tại đích. Nếu xe YÊU CẦU
        # lại GẦN đích hơn xe claim → cho xe gần ĐI TRƯỚC, KHÔNG bắt chờ (đúng ý user: "chưa
        # có xe nào ở node 19 mà báo occupied"). Quan trọng hơn: nếu requester đang đứng
        # NGAY TRÊN đường tới đích của claimer (vd AGV01 ở 64 chặn AGV02 lên 19) thì bắt
        # requester chờ = DEADLOCK (claimer không tới đích được). CHỈ áp dụng khi claimer
        # CHƯA ở đích; nếu claimer ĐANG Ở đích (picking) thì vẫn phải chờ thật.
        if _claimer and str(current_node) != str(dest_node):
            try:
                from line_agv_handler import line_agv_handler as _lah_cl
                _cl_st  = _lah_cl.state_store.get(_claimer)
                _cl_cur = (str(_cl_st.current_tag)
                           if (_cl_st and _cl_st.current_tag is not None) else None)
            except Exception:
                _cl_cur = None
            if _cl_cur is not None and _cl_cur != str(dest_node):
                try:
                    from line_agv_handler import requester_closer_than_claimer as _rcc
                    _g_cl = map_manager.line_graph if map_manager.line_graph else map_manager.graph
                    if _rcc(_g_cl, current_node, _cl_cur, dest_node):
                        print(f"[DISPATCH] {agv_id}: dest {dest_node} mới chỉ 'claim từ xa' "
                              f"bởi {_claimer} (ở {_cl_cur}) — TÔI gần hơn → ĐI TRƯỚC "
                              f"lấy/giao, không chờ")
                        _claimer = None
                except Exception:
                    pass
        if _claimer and str(current_node) != str(dest_node):
            # Kiểm tra xem AGV chiếm dest có đang ở trạng thái stationary không
            # (bounce/between-commands: không driving, không lifecycle, không route).
            # Nếu stationary → KHÔNG stage (staging node nằm trên return path của nó → deadlock).
            # Thay vào đó: đứng yên tại chỗ chờ.
            _claimer_stationary = False
            try:
                from line_agv_handler import line_agv_handler as _lah_cs
                _occ_cs_st = _lah_cs.state_store.get(_claimer)
                _occ_cs_rt = _lah_cs._routes.get(_claimer)
                _claimer_stationary = (
                    _occ_cs_st is not None
                    and not _occ_cs_st.driving
                    and not _occ_cs_st.task_lifecycle
                    and not _occ_cs_rt
                )
            except Exception:
                pass
            if _claimer_stationary:
                # AGV chiếm dest đang trong trạng thái stationary (bounce state).
                # Không stage để tránh chặn đường về của nó → deadlock.
                print(f"[DISPATCH] {agv_id}: dest {dest_node} occupied by stationary "
                      f"{_claimer} (bounce) — đứng yên tại {current_node}, chờ xe rời")
                try:
                    from line_agv_handler import line_agv_handler as _lah_csw
                    _st_csw = _lah_csw.state_store.get(agv_id)
                    if _st_csw:
                        _st_csw.pending_retry_cmd     = 'go_to'
                        _st_csw.pending_retry_dest    = str(dest_node)
                        _st_csw.pending_retry_session = session_id
                    from task_queue import agv_task_queue as _atq_csw
                    # auto_dispatch=False: giải phóng xe để pending_retry dispatch LẠI
                    # go_to khi đích trống, KHÔNG chạy lệnh kế (go_charge) → không bỏ
                    # giao hàng đi sạc.
                    _atq_csw.on_agv_completed(agv_id, notes='dest_wait_bounce',
                                              auto_dispatch=False)
                except Exception:
                    from task_queue import agv_task_queue as _atq_csw2, CMD_GO_TO as _CGT_csw2
                    _atq_csw2.insert_next(agv_id, _CGT_csw2, dest_node=str(dest_node))
                return True
            # Tính đường đến đích để tìm staging node gần đích nhất còn trống
            _staging_node = None
            _orig_dest = str(dest_node)
            try:
                _st_route, _ = plan_path_for_order(agv_id, current_node, dest_node,
                                                   session_id=session_id)
                _st_path = [str(n.get("nodeId") or n) for n in _st_route]
                # Thu thập tất cả nodes trên path của xe khác (tránh đỗ cản đường về)
                _other_paths: set[str] = set()
                try:
                    from line_agv_handler import line_agv_handler as _lah_st
                    for _oid, _r in _lah_st._routes.items():
                        if _oid == agv_id or not _r or not _r.full_path:
                            continue
                        _other_paths.update(str(n) for n in _r.full_path)
                except Exception:
                    pass
                # Tìm node 2-4 bước trước đích, không bị chiếm, không trên đường xe khác,
                # không là vị trí hiện tại. Bắt đầu từ 4 bước trước để đảm bảo ≥2 node gap.
                for _si in range(max(1, len(_st_path) - 5), len(_st_path) - 1):
                    _cand = str(_st_path[_si])
                    if (_cand not in _occ
                            and _cand != str(current_node)
                            and _cand not in _other_paths):
                        _staging_node = _cand
                        break
                # Fallback: nếu không tìm được node tránh đường xe khác, cho phép dùng
                # bất kỳ node trống nhưng phải cách đích ít nhất 2 node (≥2 node từ dest).
                if not _staging_node:
                    for _si in range(max(1, len(_st_path) - 4), len(_st_path) - 2):
                        _cand = str(_st_path[_si])
                        if _cand not in _occ and _cand != str(current_node):
                            _staging_node = _cand
                            break
            except Exception:
                pass

            if _staging_node:
                print(f"[DISPATCH] {agv_id}: dest {_orig_dest} occupied by {_claimer} "
                      f"→ staging at {_staging_node} (sẽ tiến gần hơn, queue lại đích)")
                from task_queue import agv_task_queue as _atq_st, CMD_GO_TO as _CGT_st
                _atq_st.insert_next(agv_id, _CGT_st, dest_node=_orig_dest)
                dest_node = _staging_node   # override → dispatch đến staging, fall-through
                _is_staging_dispatch = True
            else:
                # Đã ở ngay trước đích (hoặc toàn path bị chiếm) → reactive wait:
                # pending_retry_cmd='go_to' để _check_waiting_agvs trigger khi xe cản rời.
                print(f"[DISPATCH] {agv_id}: dest {_orig_dest} occupied by {_claimer} "
                      f"— đứng yên tại {current_node}, chờ xe rời rồi retry")
                try:
                    from line_agv_handler import line_agv_handler as _lah_dw
                    _st_dw = _lah_dw.state_store.get(agv_id)
                    if _st_dw:
                        _st_dw.pending_retry_cmd     = 'go_to'
                        _st_dw.pending_retry_dest    = _orig_dest
                        _st_dw.pending_retry_session = session_id
                    # Ghi INTENT ROUTE = đường tới đích DÙ đang đứng chờ → xe khác (vd
                    # AGV01 đi sạc) thấy ý định "18→5→17" của xe chờ → né node 5, đi lối
                    # khác (17→6), KHÔNG đâm đầu vào. Xe đang chờ deregistered nên nếu
                    # không set intent thì xe khác "không thấy" nó → đi xuyên qua.
                    try:
                        from line_agv_handler import traffic_coordinator as _tc_dw
                        _intent_dw = locals().get('_st_path')
                        if _intent_dw and len(_intent_dw) >= 2:
                            _tc_dw.set_intent_route(agv_id, _intent_dw)
                    except Exception:
                        pass
                    from task_queue import agv_task_queue as _atq_wn2c
                    # auto_dispatch=False: giải phóng xe để pending_retry dispatch LẠI
                    # go_to 17 khi đích trống, KHÔNG chạy lệnh kế (go_charge) đứng sau
                    # trong hàng đợi → KHÔNG bỏ giao hàng để đi sạc.
                    _atq_wn2c.on_agv_completed(agv_id, notes='dest_wait',
                                               auto_dispatch=False)
                except Exception:
                    from task_queue import agv_task_queue as _atq_wn2, CMD_GO_TO as _CGT_wn2
                    _atq_wn2.insert_next(agv_id, _CGT_wn2, dest_node=_orig_dest)
                return True

    # Xóa map cache để đảm bảo node_actions (arrival_action) luôn được đọc mới từ DB
    map_manager.current_map_id = None
    route_nodes, route_edges = plan_path_for_order(agv_id, current_node, dest_node,
                                                   session_id=session_id)

    if agv_registry.is_line(agv_id):
        from line_agv_plan_builder import (
            build_line_plan, build_plan_window, build_edge_speeds, build_edge_lidar,
            ACTION_REVERSE_BLIND, ACTION_TURN_L, ACTION_TURN_R,
            ACTION_SPEED, ACTION_DIR_FWD, SPEED_SLOW,
            ACTION_LIDAR_OFF, ACTION_LIDAR_ON,
        )
        from line_agv_handler import line_agv_handler, traffic_coordinator as _tc_dispatch
        path         = [str(n.get("nodeId") or n) for n in route_nodes]

        # ── MỚI: xe KHÔNG lùi được (đầu kéo/rơ-moóc) — nếu path vừa lập cần
        # LÙI ngay từ đầu (path[1]==prev_tag) mà KHÔNG phải trường hợp an toàn
        # (vừa lùi vào/ở trạm sạc nên mặt đã quay sẵn hướng đó) → path này bất
        # khả thi vật lý cho xe 1 chiều tiến. Reroute né cạnh đó tìm đường thay
        # thế toàn tiến; không có → huỷ dispatch (KHÔNG gửi lệnh lùi xe không
        # thực hiện được, tránh xe trôi tự do rồi off_route lặp vô hạn).
        # AGV carry (can_reverse=True, mặc định) hoàn toàn không đụng.
        if not agv_registry.can_reverse(agv_id) and len(path) >= 2:
            _lstate_cr = line_agv_handler.state_store.get(agv_id)
            _prev_cr   = str(_lstate_cr.prev_tag) if (_lstate_cr and _lstate_cr.prev_tag) else None
            # "Cần lùi" KHÔNG chỉ xảy ra khi path[1] trùng hệt prev_tag (lùi kiểu
            # ping-pong 1 bước) — trên 1 đoạn đường THẲNG (vd 21-81-82 nối tiếp
            # nhau), xe vừa đi 21→82 (đi NGANG QUA 81) rồi dispatch quay LẠI 81 để
            # thả hàng cũng là lùi thật, dù path[1]=81 ≠ prev_tag=21. Trước đây bỏ
            # sót case này → xe cứ tiến thẳng (DIR_FWD) qua luôn điểm cần dừng,
            # lệch route (off_route) rồi mới báo lỗi ở dispatch KẾ TIẾP — quá trễ,
            # xe đã lỡ chạy vào chỗ không định tới. Dùng hình học: so hướng đang
            # tiến (prev_tag→path[0]) với hướng sắp đi (path[0]→path[1]) — góc
            # gần 180° (cos < -0.5) → chắc chắn là lùi, bất kể path[1] có bằng
            # prev_tag hay không.
            _needs_reverse_cr = bool(_prev_cr and str(path[1]) == _prev_cr)
            if _prev_cr and not _needs_reverse_cr:
                try:
                    import math as _math_cr
                    _pts_cr = getattr(map_manager, "points", {}) or {}
                    _p_prev_cr = _pts_cr.get(_prev_cr)
                    _p_cur_cr  = _pts_cr.get(str(path[0]))
                    _p_next_cr = _pts_cr.get(str(path[1]))
                    if _p_prev_cr and _p_cur_cr and _p_next_cr:
                        _in_vec_cr  = (_p_cur_cr[0] - _p_prev_cr[0], _p_cur_cr[1] - _p_prev_cr[1])
                        _out_vec_cr = (_p_next_cr[0] - _p_cur_cr[0], _p_next_cr[1] - _p_cur_cr[1])
                        _mag_in_cr  = _math_cr.hypot(*_in_vec_cr)
                        _mag_out_cr = _math_cr.hypot(*_out_vec_cr)
                        if _mag_in_cr > 1e-6 and _mag_out_cr > 1e-6:
                            _cos_cr = ((_in_vec_cr[0] * _out_vec_cr[0] + _in_vec_cr[1] * _out_vec_cr[1])
                                       / (_mag_in_cr * _mag_out_cr))
                            if _cos_cr < -0.5:
                                _needs_reverse_cr = True
                                print(f"[DISPATCH] {agv_id}: phát hiện lùi qua hình học "
                                      f"(prev={_prev_cr}→{path[0]}→{path[1]}, cos={_cos_cr:.2f})")
                except Exception:
                    pass
            if _needs_reverse_cr:
                _cur_cfg_cr   = (getattr(map_manager, "node_actions", {}) or {}).get(str(path[0])) or {}
                _approach_cr  = str(_cur_cfg_cr.get("approach_dir")   or "").lower()
                _arrival_cr   = str(_cur_cfg_cr.get("arrival_action") or "").lower()
                _lifecycle_cr = (getattr(_lstate_cr, 'task_lifecycle', '') or '') == "charging"
                _last_tdir_cr = getattr(_lstate_cr, 'last_transit_direction', '') if _lstate_cr else ''
                # Node có sẵn kịch bản "lùi mù + quay đầu" chuyên dụng khi RA trạm
                # (exit_reverse_ms/exit_turn) → AN TOÀN, không phải "cần lùi giữa
                # đường" — kịch bản đó xử lý riêng ở _trailer_exit_steps bên dưới
                # (lùi mù theo thời gian rồi quay, KHÔNG đi qua path/graph edge
                # thường) — sau khi quay xong, đi tiếp theo path[0]→path[1] thực
                # chất là hướng TIẾN mới của xe, không phải lùi giữa đường.
                # KHÔNG suy rộng ra "mọi trạm sạc đều an toàn" — trạm sạc tiến
                # thẳng vào (không approach_dir=bwd, không có kịch bản lùi+quay)
                # mà chỉ có 1 đường ra trùng đường vào vẫn là bẫy cụt thật sự cho
                # xe 1 chiều tiến, cần cảnh báo như cũ.
                _has_exit_maneuver_cr = (
                    bool(_cur_cfg_cr.get("exit_reverse_ms"))
                    and str(_cur_cfg_cr.get("exit_turn") or "").lower() in ("left", "right")
                )
                _already_safe_cr = (
                    (_approach_cr == "bwd")
                    or (_arrival_cr == "wait_charge")
                    or _has_exit_maneuver_cr
                    or _lifecycle_cr
                    or (_last_tdir_cr == "bwd")
                )
                if not _already_safe_cr:
                    _rerouted_cr = False
                    _avoided_edge_cr = (path[0], path[1])
                    try:
                        import networkx as _nx_cr
                        _g_cr = (map_manager.line_graph.copy() if map_manager.line_graph
                                 else map_manager.graph.copy())
                        if _g_cr.has_edge(path[0], path[1]):
                            _g_cr.remove_edge(path[0], path[1])
                        if _g_cr.has_edge(path[1], path[0]):
                            _g_cr.remove_edge(path[1], path[0])
                        _alt_path_cr = _nx_cr.shortest_path(_g_cr, source=path[0],
                                                             target=dest_node, weight='weight')
                        path = [str(n) for n in _alt_path_cr]
                        _rerouted_cr = True
                        print(f"[DISPATCH] {agv_id}: xe không lùi được — né cạnh cần lùi "
                              f"{_avoided_edge_cr}, đường thay thế → {path}")
                    except Exception as _e_cr:
                        print(f"[DISPATCH] {agv_id}: xe không lùi được — KHÔNG tìm được "
                              f"đường thay thế toàn tiến ({_e_cr}). Map thiếu nhánh vòng "
                              f"tại đây cho xe 1 chiều tiến.")
                    if not _rerouted_cr:
                        try:
                            from telegram_bot import notify_error as _tg_notify_cr
                            _tg_notify_cr(
                                f"⚠️ AGV {agv_id}: không tìm được đường KHÔNG cần lùi "
                                f"(map thiếu nhánh vòng tại node {path[0]}) — huỷ dispatch, "
                                f"xe đứng yên chờ kiểm tra map.")
                        except Exception:
                            pass
                        return False

        points       = getattr(map_manager, "points",       {}) or {}
        node_actions = getattr(map_manager, "node_actions", {}) or {}
        roads        = getattr(map_manager, "roads",        []) or []
        edge_spd     = build_edge_speeds(roads)
        edge_lidar   = build_edge_lidar(roads)

        # Ghi TUYẾN ĐẦY ĐỦ (intent) tới đích — dù bên dưới chia đoạn (supply/lùi),
        # xe KHÁC vẫn né được cả tuyến đầy đủ này (penalty routing).
        # KHI STAGING (đỗ gần đích vì đích bị chiếm): intent phải là đường tới ĐÍCH THẬT
        # (_st_path), KHÔNG phải đường tới node staging — nếu không, xe khác KHÔNG thấy
        # đoạn còn lại (vd AGV02 staging→18 nhưng sẽ đi 18→5→17; AGV01 sạc phải né node 5).
        _intent_path = path
        if _is_staging_dispatch:
            _sp = locals().get('_st_path')
            if _sp and len(_sp) >= 2:
                _intent_path = [str(n) for n in _sp]
        _tc_dispatch.set_intent_route(agv_id, _intent_path)

        # ── Xử lý head-on conflict còn sót sau phase plan ───────────────────
        # near_only=True: chỉ check DISPATCH_HORIZON edges đầu tiên.
        # near_only=False: check TOÀN BỘ path tại dispatch time.
        _head_on_dispatch = _tc_dispatch.find_head_on(agv_id, path, near_only=False)
        # find_head_on trả về (idx, agv_id) cho head-on, hoặc negative int cho following.
        # Negative int (following) → không cần xử lý head-on, bỏ qua.
        if not isinstance(_head_on_dispatch, tuple):
            _head_on_dispatch = None
        # BẤT ĐỐI XỨNG: chỉ xe YẾU hơn mới nhường (đỗ side/chờ). Xe MẠNH hơn đi đường
        # ngắn, KHÔNG nhường — xe yếu sẽ né. Tránh CẢ HAI cùng nhường → dao động/kẹt.
        # ƯU TIÊN THẬT theo đích (KHÔNG để rank mặc định 2 khi chưa registered → winner
        # delivery vừa picking xong né nhầm → cả 2 cùng né, đâm — đúng lỗi user thấy).
        from mqtt_client import _planner_dest_priority as _pdp_ho
        _my_prio_ho = _pdp_ho(node_actions or {}, dest_node)
        _my_prio_ho = _tc_dispatch._registered.get(agv_id, {}).get('priority', _my_prio_ho)
        if (_head_on_dispatch is not None
                and not _tc_dispatch.should_avoid_path_of(agv_id, _head_on_dispatch[1],
                                                          my_priority=_my_prio_ho)):
            print(f"[DISPATCH] {agv_id}: HEAD-ON với {_head_on_dispatch[1]} — TÔI ưu tiên "
                  f"(mạnh hơn) → đi tiếp, để {_head_on_dispatch[1]} né")
            _head_on_dispatch = None
        if _head_on_dispatch is not None:
            _ho_idx, _ho_other = _head_on_dispatch
            _lstate_ho = line_agv_handler.state_store.get(agv_id)
            _cur_tag_ho = str(_lstate_ho.current_tag) if (_lstate_ho and _lstate_ho.current_tag) else None

            # Dùng last_plan_direction làm hướng transit, nhưng nếu đang ở CHARGER
            # thì phải dùng 'fwd' (ra khỏi trạm phải tiến, không phải lùi thêm).
            # Tổng quát: mọi trạm sạc đều không có đường phía sau.
            _ho_dir_raw = (getattr(_lstate_ho, 'last_plan_direction', 'fwd') or 'fwd') if _lstate_ho else 'fwd'
            # Kiểm tra lifecycle charging thêm ngoài locationType
            if (getattr(_lstate_ho, 'task_lifecycle', '') or '') == 'charging':
                _ho_dir_raw = 'fwd'
            from line_agv_handler import _charger_exit_direction as _ced
            _ho_dir = _ced(_cur_tag_ho or '', _ho_dir_raw)

            # Thử tìm nhánh phụ (parking node) để tránh ra không cản đường chính
            _parking = _tc_dispatch.find_parking_node(agv_id, path, _ho_idx, _ho_other)

            # initial_prev_tag cho plan đỗ-né/dừng-chờ: cú RẼ tại node ĐẦU (vị trí xe) phụ
            # thuộc node TRƯỚC (prev_tag THẬT). Thiếu nó (=None) → plan KHÔNG có TURN tại
            # node đầu → xe đi THẲNG thay vì rẽ → off_route (vd đỗ ['4','9'] từ node 4: cần
            # rẽ 19→4→9=left nhưng initial_prev_tag=None → đi thẳng 4→18, dừng bất ngờ tại
            # 18). BỎ tính turn CHỈ khi xe đang Ở TRẠM SẠC (heading thực ≠ prev_tag).
            _init_prev_park = None
            if (_lstate_ho is not None
                    and getattr(_lstate_ho, 'prev_tag', None) is not None and path):
                _cur_cfg_park = node_actions.get(str(path[0])) or {}
                _is_charger_park = (
                    str(_cur_cfg_park.get('locationType', '')).upper() == 'CHARGER'
                    or str(_cur_cfg_park.get('arrival_action', '')).lower() == 'wait_charge')
                if not _is_charger_park:
                    _init_prev_park = str(_lstate_ho.prev_tag)

            if _parking and _parking[0] != _cur_tag_ho:
                _park_node, _entry_node = _parking
                _entry_idx = path.index(_entry_node) if _entry_node in path else (_ho_idx - 1)
                _transit_path = path[:_entry_idx + 1] + [_park_node]
                print(f"[DISPATCH] {agv_id}: HEAD-ON với {_ho_other} → "
                      f"đỗ tại {_park_node} (qua {_entry_node}, dir={_ho_dir}), queue tiếp→{dest_node}")
                _park_plan = build_line_plan(
                    _transit_path, points, task_type="transit",
                    node_actions=node_actions, direction=_ho_dir,
                    edge_speeds=edge_spd, edge_lidar=edge_lidar,
                    agv_id=agv_id, initial_prev_tag=_init_prev_park,
                )
                _rt_park = line_agv_handler.set_route(agv_id, _transit_path, "transit", direction=_ho_dir)
                _rt_park.window_end  = len(_transit_path) - 1
                _rt_park.is_complete = True
                send_order(agv_id, _park_plan)
                from task_queue import agv_task_queue as _atq_ho, CMD_GO_TO as _CGT_ho
                _atq_ho.insert_next(agv_id, _CGT_ho, dest_node=str(dest_node))
                return True

            # Không có nhánh phụ: dừng tại node cuối trước conflict trên đường chính.
            # Quan trọng: safe_wait node KHÔNG được nằm trong future path của xe kia
            # (nếu nằm trong đó thì sẽ gây conflict mới tại chính safe_wait node đó)
            _safe_wait = _tc_dispatch.find_safe_wait_node(path, _ho_idx)
            _other_reg_sw  = _tc_dispatch._registered.get(_ho_other, {})
            _other_fut_sw  = set(_other_reg_sw.get('path', [])[_other_reg_sw.get('current_idx', 0):])
            if _safe_wait and _safe_wait != path[0] and _safe_wait != path[-1] \
                    and _safe_wait != _cur_tag_ho \
                    and _safe_wait not in _other_fut_sw:
                print(f"[DISPATCH] {agv_id}: HEAD-ON với {_ho_other} (không có nhánh phụ) — "
                      f"dừng tại {_safe_wait} (dir={_ho_dir}), queue tiếp→{dest_node}")
                _wait_path  = path[:path.index(_safe_wait) + 1]
                _wait_plan  = build_line_plan(
                    _wait_path, points, task_type="transit",
                    node_actions=node_actions, direction=_ho_dir,
                    edge_speeds=edge_spd, edge_lidar=edge_lidar,
                    agv_id=agv_id, initial_prev_tag=_init_prev_park,
                )
                _rt_wait = line_agv_handler.set_route(agv_id, _wait_path, "transit", direction=_ho_dir)
                _rt_wait.window_end  = len(_wait_path) - 1
                _rt_wait.is_complete = True
                send_order(agv_id, _wait_plan)
                from task_queue import agv_task_queue as _atq_ho2, CMD_GO_TO as _CGT_ho2
                _atq_ho2.insert_next(agv_id, _CGT_ho2, dest_node=str(dest_node))
                return True

            # Không tìm được parking/safe_wait → thử tìm side node của vị trí hiện tại
            # (conflict_idx=0 nghĩa là xe đang đứng ngay tại điểm xung đột)
            _side_found = False
            if _cur_tag_ho:
                try:
                    from mqtt_client import map_manager as _mm_side
                    _g_side = _mm_side.line_graph if _mm_side.line_graph else _mm_side.graph
                    if _g_side and _cur_tag_ho in _g_side:
                        _other_reg = _tc_dispatch._registered.get(_ho_other, {})
                        _other_cur_idx = _other_reg.get('current_idx', 0)
                        _other_full = _other_reg.get('path', [])
                        _other_future = set(_other_full[_other_cur_idx:])
                        _path_set = set(path)

                        # Ưu tiên 1: side node không trên bất kỳ đường nào của xe kia
                        _side_candidates = [
                            str(n) for n in _g_side.neighbors(_cur_tag_ho)
                            if str(n) not in _path_set and str(n) not in _other_future
                        ]

                        # Ưu tiên 2 (bottleneck): không có side node thuần → cho phép đi theo
                        # chiều cùng với xe kia (FOLLOWING = không đâm nhau) để nhường đường.
                        # Ví dụ: AGV02 tại node 19 (bottleneck), AGV01 đi 4→19→3 (bwd).
                        # AGV02 đi 19→3 = cùng chiều (following), cho phép nhường chỗ.
                        if not _side_candidates and _other_full:
                            _following_candidates = []
                            for _nb in _g_side.neighbors(_cur_tag_ho):
                                _nb_str = str(_nb)
                                if _nb_str in _path_set:
                                    continue  # vẫn trên đường mình đang đi → skip
                                # Kiểm tra cùng chiều (following) với xe kia
                                try:
                                    _idx_cur = _other_full.index(_cur_tag_ho)
                                    _idx_nb  = _other_full.index(_nb_str)
                                    if _idx_nb > _idx_cur:
                                        # xe kia đi cur→nb = cùng chiều → following, an toàn
                                        _following_candidates.append(_nb_str)
                                except ValueError:
                                    pass
                            if _following_candidates:
                                _side_candidates = _following_candidates
                                print(f"[DISPATCH] {agv_id}: bottleneck yield — "
                                      f"di theo chiều xe kia (following) để nhường")

                        if _side_candidates:
                            _side_candidates.sort(key=lambda n: _g_side.degree(str(n)))
                            _side_node = _side_candidates[0]
                            print(f"[DISPATCH] {agv_id}: HEAD-ON idx=0 → đỗ tại side node={_side_node}, queue→{dest_node}")
                            _side_path = [_cur_tag_ho, _side_node]
                            _side_plan = build_line_plan(
                                _side_path, points, task_type="transit",
                                node_actions=node_actions, direction="fwd",
                                edge_speeds=edge_spd, edge_lidar=edge_lidar,
                                agv_id=agv_id, initial_prev_tag=None,
                            )
                            _rt_side = line_agv_handler.set_route(agv_id, _side_path, "transit", direction="fwd")
                            _rt_side.window_end  = 1
                            _rt_side.is_complete = True
                            send_order(agv_id, _side_plan)
                            from task_queue import agv_task_queue as _atq_side, CMD_GO_TO as _CGT_side
                            _atq_side.insert_next(agv_id, _CGT_side, dest_node=str(dest_node))
                            _side_found = True
                except Exception as _se:
                    print(f"[DISPATCH] {agv_id}: side-node fallback error: {_se}")

            if not _side_found:
                print(f"[DISPATCH] {agv_id}: HEAD-ON với {_ho_other} — "
                      f"không có side node, dừng tại {_cur_tag_ho} chờ xe kia clear")
                from task_queue import agv_task_queue as _atq_wait, CMD_GO_TO as _CGT_wait
                _atq_wait.insert_next(agv_id, _CGT_wait, dest_node=str(dest_node))
            return True

        # Kiểm tra AGV có đang trong simulation mode không (cần trước node_actions override)
        _is_sim_agv = False
        try:
            from simulation_manager import _sim_active_agvs as _sim_set
            _is_sim_agv = agv_id in _sim_set
        except Exception:
            pass

        # ── Simulation: clear approach_dir='bwd' cho tất cả node TRỪ trạm sạc ─
        # Trạm sạc (path[0] với locationType=CHARGER/wait_charge) cần giữ 'bwd'
        # để backward-transit detection hoạt động đúng khi thoát trạm.
        # Node thường có approach_dir='bwd' → clear để tránh bwd_arrival sai.
        def _is_charger_node(cfg):
            if not isinstance(cfg, dict): return False
            return (str(cfg.get('locationType', '')).upper() == 'CHARGER' or
                    str(cfg.get('arrival_action', '')).lower() == 'wait_charge')

        if _is_sim_agv and path:
            _orig_na_sim = getattr(map_manager, 'node_actions', {}) or {}

            _bwd_to_clear = []
            for _i, _n in enumerate(path):
                _k = str(_n)
                _cfg = node_actions.get(_k) or {}
                if not isinstance(_cfg, dict) or _cfg.get('approach_dir') != 'bwd':
                    continue
                # path[0] = trạm sạc thật → giữ 'bwd' cho backward-transit exit
                if _i == 0 and _is_charger_node(_orig_na_sim.get(_k, {})):
                    continue
                _bwd_to_clear.append(_k)

            if _bwd_to_clear:
                node_actions = dict(node_actions)
                for _k in _bwd_to_clear:
                    node_actions[_k] = dict(node_actions[_k])
                    node_actions[_k]['approach_dir'] = 'none'

        # Đọc prev_tag để xác định hướng xe đang nhìn
        _lstate      = line_agv_handler.state_store.get(agv_id)
        _prev_tag    = str(_lstate.prev_tag) if (_lstate and _lstate.prev_tag) else None
        print(f"[DISPATCH] {agv_id}: path={path} prev_tag={_prev_tag} "
              f"node_actions_count={len(node_actions)} edge_speeds_count={len(edge_spd)}")

        # ── Phát hiện đoạn lùi đầu đường ──────────────────────────────────────
        # Khi directional planner quyết định xe phải lùi trước (path[1] == prev_tag),
        # tách đoạn lùi và gửi trước; phần còn lại queue tiếp theo.
        # Backward transit detection: chạy bình thường cho cả simulation.
        # - Trạm sạc (charger): _at_charge_bwd=True → "post-backward fwd exit" ✓
        # - Pingpong reversal (path[1]==prev): backward transit thật → AGV lùi đúng ✓
        # - Node thường đi tiếp: path[1] != prev_tag → không vào block này ✓
        if _prev_tag and len(path) >= 2 and str(path[1]) == _prev_tag:
            _last_tdir_bwd = getattr(_lstate, 'last_transit_direction', '') if _lstate else ''
            # Kiểm tra xe có đang ở trạm sạc không (approach_dir=bwd HOẶC arrival_action=wait_charge).
            # Nếu có: xe đã lùi vào trạm (kể cả thủ công), front đang hướng ra ngoài → phải TIẾN.
            _cur_node_cfg    = node_actions.get(str(path[0])) or {}
            _cur_approach    = str(_cur_node_cfg.get("approach_dir")    or "").lower()
            _cur_arrival     = str(_cur_node_cfg.get("arrival_action")  or "").lower()
            _lifecycle_chg   = (getattr(_lstate, 'task_lifecycle', '') or '') == "charging"
            # Node có sẵn kịch bản lùi mù + quay đầu chuyên dụng (exit_reverse_ms/
            # exit_turn) → cũng coi như "đã hướng ra ngoài rồi" giống approach_dir=bwd,
            # để rơi xuống nhánh direction=fwd bên dưới — _trailer_exit_steps (xây
            # riêng ở phần dispatch phía sau) sẽ chèn đúng lùi mù+quay, KHÔNG để
            # nhánh "cần lùi thật" tự dựng đoạn lùi bằng RFID thường (sai cho xe
            # rơ-moóc không lùi được). CHỈ áp dụng cho xe KHÔNG lùi được — xe carry
            # (can_reverse=True) vẫn dùng nhánh "cần lùi thật" như cũ nếu path yêu
            # cầu, vì lùi RFID bình thường hoàn toàn ổn với xe carry.
            _has_exit_maneuver_chg = (
                not agv_registry.can_reverse(agv_id)
                and bool(_cur_node_cfg.get("exit_reverse_ms"))
                and str(_cur_node_cfg.get("exit_turn") or "").lower() in ("left", "right")
            )
            _at_charge_bwd   = (_cur_approach == "bwd") or (_cur_arrival == "wait_charge") \
                                or _lifecycle_chg or _has_exit_maneuver_chg
            if _last_tdir_bwd == "bwd" or _at_charge_bwd:
                # AGV vừa lùi vào (server-route hoặc thủ công) — front đang hướng ra đường chính.
                # path[1]==prev_tag chỉ nghĩa là route đi qua node đó theo chiều TIẾN.
                # Không cần transit lùi, chuyển sang tiến (direction="fwd").
                if _lstate:
                    _lstate.last_transit_direction = ''
                print(f"[DISPATCH] {agv_id}: post-backward route → skip transit, dùng direction=fwd"
                      f" (reason: last_tdir={_last_tdir_bwd!r} at_charge_bwd={_at_charge_bwd})")
                # _line_dir = "fwd" mặc định ở dưới, direction-inference sẽ không chạy (đã clear)
            else:
                # Cần lùi thật: tìm điểm cuối đoạn lùi và gửi transit
                bwd_end  = 1
                cur_from = _prev_tag
                for _bi in range(1, len(path) - 1):
                    if str(path[_bi + 1]) == str(cur_from):
                        cur_from = path[_bi]
                        bwd_end  = _bi + 1
                    else:
                        break

                bwd_seg = path[:bwd_end + 1]
                print(f"[DISPATCH] {agv_id}: backward start → bwd_seg={bwd_seg}, tiếp→{dest_node}")
                # set_route TRƯỚC để tính window CẮT theo RESERVATION (node kế của đoạn lùi
                # có thể đang bị xe khác giữ). Build plan THEO window đó — GIỐNG nhánh forward —
                # KHÔNG build full bwd_seg rồi gửi bất kể reservation. Nếu node kế bị giữ →
                # window=[0→0] → plan CHỈ giữ tại node hiện tại, KHÔNG lái vào node tranh chấp
                # (tránh 2 xe cùng lao vào 1 node = ĐÂM, đúng log AGV01 17→5 trong khi AGV02
                # giữ node 5). Node kế trống → window đầy đủ → plan y hệt build_line_plan cũ.
                _rt_bwd  = line_agv_handler.set_route(agv_id, bwd_seg, "transit", direction="bwd")
                bwd_plan = build_plan_window(
                    full_path=bwd_seg, w_start=0, w_end=_rt_bwd.window_end, points=points,
                    is_final=_rt_bwd.is_complete, task_type="transit",
                    node_actions=node_actions, direction="bwd",
                    edge_speeds=edge_spd, edge_lidar=edge_lidar, agv_id=agv_id,
                    initial_prev_tag=None)
                send_order(agv_id, bwd_plan)
                from task_queue import agv_task_queue as _atq, CMD_GO_TO as _CGT
                _atq.insert_next(agv_id, _CGT, dest_node=str(dest_node))
                return True

        # ── Tìm intermediate node đầu tiên có arrival_action → split route ────
        # Nếu đích là CHARGER → bỏ qua split tại wait_sys/wait_user trên đường đi.
        # Nếu đích là DROPOFF có team → chỉ dừng tại supply node phục vụ đúng team đó.
        from task_queue import agv_task_queue as _atq_pick
        _dest_cfg_split = node_actions.get(str(dest_node)) or {}
        _dest_is_charger_split = (
            str(_dest_cfg_split.get('locationType', '')).upper() == 'CHARGER'
            or str(_dest_cfg_split.get('arrival_action', '')).lower() == 'wait_charge'
        )
        # Tìm team của đích (nếu có) để lọc supply node phù hợp
        _dest_team_raw = _dest_cfg_split.get('team')
        _dest_team_str = str(_dest_team_raw) if _dest_team_raw is not None else None

        # Nếu ĐÍCH chính là một supply node (lệnh lấy hàng tường minh từ multi-team
        # panel) → đánh dấu đã lấy hàng tại đó cho session này. Các lệnh giao hàng
        # sau trong cùng lượt sẽ đi một mạch qua node này, không dừng lấy lại.
        _dest_supply_raw = _dest_cfg_split.get('supply_group') or []
        if isinstance(_dest_supply_raw, str):
            _dest_supply_raw = [s.strip() for s in _dest_supply_raw.split(',') if s.strip()]
        _dest_is_supply = (
            str(_dest_cfg_split.get('arrival_action', '')).lower() == 'wait_sys'
            and bool(_dest_supply_raw)
        )
        if _dest_is_supply:
            # KHÔNG đánh dấu pickup tại đây (lúc DISPATCH). Nếu xe off-route TRƯỚC khi tới
            # supply node thì pickup CHƯA xảy ra; đánh dấu sớm → re-dispatch bị auto-complete
            # bỏ qua → xe KHÔNG BAO GIỜ lấy hàng (lỗi: AGV02 đi lạc 2→10 rồi bỏ qua 19, giao
            # thẳng). Đánh dấu khi xe THỰC SỰ tới supply node (lifecycle 'picking' trong
            # line_agv_handler._handle_event).
            print(f"[DISPATCH] {agv_id}: pickup node {dest_node} (session={session_id}) → "
                  f"sẽ đánh dấu khi xe TỚI; giao hàng sau không dừng lại tại đây")

        # ── Tập điểm cấp CẦN cho cả lượt (session) ────────────────────────────
        # = supply node của tổ đang xử lý (nếu là delivery) + tất cả tổ đang chờ
        # trong queue cùng session. Khi đang đi LẤY HÀNG (dest là supply node, không
        # có team) → split logic dùng tập này để chỉ dừng tại điểm cấp THỰC SỰ cần,
        # tránh dừng nhầm tại supply node khác trên đường (phục vụ tổ ngoài lượt).
        _batch_required_supplies: set[str] = set()
        if session_id:
            _batch_dests = list(_atq_pick.session_queued_dests(agv_id, session_id, "go_to"))
            if _required_supply_node(node_actions, dest_node):
                _batch_dests.append(str(dest_node))
            for _bd in _batch_dests:
                _bs = _required_supply_node(node_actions, _bd)
                if _bs:
                    _batch_required_supplies.add(str(_bs))

        # Xe rơ-moóc VỪA RỜI TRẠM SẠC (path[0]=CHARGER) — nếu đường đi ngang qua node
        # 'trailer_empty_staging' (điểm lấy hàng rỗng cố định gần trạm) TRƯỚC KHI xe
        # đã có hàng (hook chưa raised) → PHẢI dừng lấy hàng ở đó, dù dispatch thẳng
        # (không qua API trailer-roundtrip). Trước đây cờ này CHỈ được đọc bởi API
        # trailer-roundtrip (chèn hẳn 1 leg riêng) — dispatch thẳng đi ngang qua node
        # không hề biết, nên chạy xuyên qua luôn, không dừng lấy hàng.
        # CHỈ áp dụng chặng RA (rời trạm sạc) — không áp dụng cho các dispatch giữa
        # đường/về trạm khác, đúng như vai trò "node chỉ dùng lúc đi" của staging node.
        _agv_type_trailer_split = (agv_registry.get_config(agv_id).get('agv_type') == 'trailer')
        _dispatch_from_charger_split = (
            str((node_actions.get(str(path[0])) or {}).get('locationType') or '').upper() == 'CHARGER'
        )

        split_idx = None
        for _si in range(1, len(path) - 1):
            _node_cfg = node_actions.get(str(path[_si])) or {}
            _acfg = str(_node_cfg.get("arrival_action") or "").lower()
            print(f"[DISPATCH] check intermediate node={path[_si]} "
                  f"arrival_action={_acfg!r} cfg={_node_cfg}")
            # ── CỬA TỰ ĐỘNG: node có door_id — kiểm tra TRƯỚC mọi thứ khác (độc
            # lập với arrival_action, không bị lọc theo session/supply_group như
            # nhánh wait_sys/wait_user phía dưới). Xem door_coordinator.py +
            # PROTOCOL_GUIDE.md mục "Cửa tự động (Gate Controller)".
            # Suy ra CHIỀU đi qua bằng trạng thái đã theo dõi TRONG door_coordinator
            # (xe này đã "vào" cửa từ node nào chưa) — KHÔNG dùng node liền kề
            # trong path (2 node của 1 cửa có thể cách xa nhau qua nhiều node
            # trung gian, đã xảy ra thực tế và làm sai hoàn toàn nếu so liền kề).
            # is_exit_arrival=True → xe ĐÃ vào cửa từ phía kia, đây là lượt RA,
            # không cần dừng. False → lượt VÀO, PHẢI dừng ở đây xin mở, bất kể xa
            # đích cuối bao nhiêu (giống hệt cách split cho supply/trailer node
            # bên dưới).
            _door_id_split = str(_node_cfg.get('door_id') or '').strip()
            if _door_id_split:
                from door_coordinator import door_coordinator as _door_co_split
                if _door_co_split.is_exit_arrival(_door_id_split, agv_id, str(path[_si])):
                    print(f"[DISPATCH] {agv_id}: node {path[_si]} = cửa tự động "
                          f"'{_door_id_split}' — xe đang RA khỏi cửa (đã băng qua), "
                          f"không cần dừng")
                    continue
                split_idx = _si
                print(f"[DISPATCH] {agv_id}: node {path[_si]} = cửa tự động "
                      f"'{_door_id_split}' — xe đang TIẾN VÀO, dừng xin mở cửa "
                      f"trước khi qua")
                break
            if (not _acfg
                    and _agv_type_trailer_split
                    and _dispatch_from_charger_split
                    and str(_node_cfg.get('trailer_empty_staging') or '').lower() == 'yes'
                    and str(getattr(_lstate, 'hook_state', None) or '') != 'raised'):
                from line_agv_handler import _pending_empty_pickup_legs
                # Đánh dấu TRƯỚC khi gửi lệnh — arrival handler cần thấy dấu này ngay
                # khi xe tới (cùng pattern với execute_trailer_roundtrip).
                _pending_empty_pickup_legs.add((agv_id, str(path[_si])))
                split_idx = _si
                print(f"[DISPATCH] {agv_id}: node {path[_si]} = điểm lấy hàng rỗng cố định "
                      f"gần trạm (trailer_empty_staging), xe vừa rời trạm sạc → dừng lấy "
                      f"hàng trước khi đi tiếp")
                break
            if _acfg in ("wait_user", "wait_sys", "wait_charge"):
                # Node trailer_staging (thả đầy, vd 81) / trailer_empty_staging (lấy
                # rỗng, vd 82) CHỈ được phép "hoạt động" (dừng + kích hoạt móc) khi
                # nó THỰC SỰ là ĐÍCH của lượt dispatch này — KHÔNG kích hoạt khi chỉ
                # đi NGANG QUA trên đường tới 1 đích khác. 2 node này thường nằm trên
                # CÙNG 1 đoạn đường thẳng (ra trạm rồi mới tới Tổ, về từ Tổ rồi mới
                # vào trạm) nên bất kỳ dispatch nào đi qua đoạn đó cũng sẽ đi ngang cả
                # 2 node — nếu cả 2 đều có arrival_action='wait_user' (để dùng được
                # khi LÀ đích) thì sẽ bị dừng+kích hoạt SAI mỗi lần đi ngang, kể cả
                # đang đi chiều ngược lại chưa hề mang/lấy hàng gì. Ví dụ lỗi thật:
                # dispatch RA trạm hướng tới 82 (lấy rỗng), đi ngang 81 trước — nếu
                # không chặn, 81 (trailer_staging) sẽ bị coi là "tới nơi, nhả hàng"
                # dù xe còn CHƯA hề lấy hàng gì cả.
                _is_trailer_role_node = (
                    str(_node_cfg.get('trailer_staging') or '').lower() == 'yes'
                    or str(_node_cfg.get('trailer_empty_staging') or '').lower() == 'yes'
                )
                if _is_trailer_role_node and str(path[_si]) != str(dest_node):
                    print(f"[DISPATCH] {agv_id}: bỏ qua node trailer-role {path[_si]} "
                          f"(không phải đích của lượt này {dest_node}) — đi ngang qua, "
                          f"không kích hoạt móc")
                    continue
                # Đã lấy hàng tại supply node này trong session hiện tại → đi một mạch qua,
                # KHÔNG dừng lại chờ xác nhận nữa (fix: lùi về điểm lấy hàng / dừng lặp lại).
                if _acfg == 'wait_sys' and _atq_pick.session_has_pickup(session_id, path[_si]):
                    print(f"[DISPATCH] {agv_id}: bỏ qua supply node {path[_si]} "
                          f"(đã lấy hàng trong session {session_id}) — đi thẳng")
                    continue
                if _dest_is_charger_split and _acfg in ("wait_sys", "wait_user"):
                    # Đang về trạm sạc → không dừng tại điểm cấp hàng giữa đường
                    continue
                if _is_staging_dispatch and _acfg in ("wait_sys", "wait_user"):
                    # Staging transit: đi đến vị trí chờ tạm, không dừng lấy hàng giữa đường.
                    # Việc lấy hàng sẽ xảy ra khi dispatch delivery thực sự sau staging.
                    continue
                if _acfg == 'wait_sys' and session_id:
                    # Lượt cấp hàng: chỉ dừng tại điểm cấp THỰC SỰ cần cho lượt này
                    # (tổ đang giao + các tổ đang chờ). Tránh dừng nhầm tại supply node
                    # phục vụ tổ ngoài lượt — kể cả khi đang trên đường đi lấy hàng.
                    if str(path[_si]) not in _batch_required_supplies:
                        print(f"[DISPATCH] {agv_id}: bỏ qua supply node {path[_si]} "
                              f"(không thuộc lượt cấp hiện tại)")
                        continue
                elif _acfg == 'wait_sys' and _dest_team_str:
                    # Không có session → lọc theo team của đích (hành vi cũ).
                    # Chỉ dừng tại supply node NẾU nó phục vụ đúng team của đích.
                    _sg_raw = _node_cfg.get('supply_group') or []
                    if isinstance(_sg_raw, str):
                        _sg_raw = [s.strip() for s in _sg_raw.split(',') if s.strip()]
                    _sg_strs = [str(g) for g in _sg_raw]
                    if _sg_strs and _dest_team_str not in _sg_strs:
                        # Supply node này không phục vụ team đang giao → bỏ qua
                        continue
                split_idx = _si
                # KHÔNG đánh dấu pickup tại đây — đánh dấu khi xe THỰC SỰ tới supply node
                # (lifecycle 'picking'). Tránh: split tại S, off-route trước khi tới S →
                # re-dispatch bỏ qua S → giao hàng mà chưa lấy.
                break

        # Đọc last_transit_direction TRƯỚC khi clear (để detect post-backward-transit)
        _last_tdir_pre  = getattr(_lstate, 'last_transit_direction', '') if _lstate else ''
        # Phân biệt: 'bwd' từ transit thường vs từ trạm sạc (return_charge)
        _is_post_charge = (getattr(_lstate, 'task_lifecycle', '') or '') == "charging"

        # initial_prev_tag: truyền để plan builder tính góc rẽ tại start node DỰA VÀO
        # hướng xe đến từ prev_tag. Điều này CHỈ ĐÚNG khi xe đang đi xuyên qua node
        # (heading = hướng từ prev_tag tới node).
        #
        # NGOẠI LỆ — xe XUẤT PHÁT TỪ TRẠM SẠC (node hiện tại là CHARGER): trạm sạc có
        # approach_dir=bwd → xe LÙI VÀO, mặt quay RA NGOÀI. Khi xuất phát, xe đi THẲNG
        # theo hướng đang quay (ra khỏi trạm), KHÔNG theo hướng prev_tag (prev_tag chỉ là
        # node trước đó, không phải heading thực của xe đang đỗ). Vậy phải BỎ tính turn
        # tại node đầu (_initial_prev=None) → xe đi thẳng ra, rẽ tại ngã rẽ kế tiếp.
        # TỔNG QUÁT: áp dụng cho MỌI node có locationType=CHARGER (không hardcode node nào)
        # và cho mọi lần xuất phát, không chỉ khi lifecycle='charging' (_is_post_charge).
        _cur_node_cfg_exit = node_actions.get(str(path[0])) or {} if path else {}
        _exit_from_charger = (
            str(_cur_node_cfg_exit.get('locationType', '')).upper() == 'CHARGER'
            or str(_cur_node_cfg_exit.get('arrival_action', '')).lower() == 'wait_charge'
        )
        # CHỈ bỏ tính turn khi xe ĐANG Ở TRẠM SẠC (path[0]=CHARGER) — đó mới là lúc
        # heading thực ≠ prev_tag. KHÔNG dùng _is_post_charge (lifecycle='charging'):
        # cờ này CÒN SÓT sau khi xe đã rời trạm → ở node thường (vd node 1) vẫn bị bỏ
        # rẽ → xe đi THẲNG (1→12) thay vì rẽ (1→2). Khi đã ra node thường, prev_tag là
        # heading đúng nên phải tính turn bình thường.
        _suppress_initial_turn = _exit_from_charger
        if _exit_from_charger:
            print(f"[DISPATCH] {agv_id}: xuất phát từ trạm sạc {path[0]} "
                  f"(locationType=CHARGER) → đi thẳng ra, không tính turn theo prev_tag={_prev_tag}")
        _initial_prev = _prev_tag if not _suppress_initial_turn else None
        _initial_arrived_bwd = (_last_tdir_pre == 'bwd' and not _suppress_initial_turn)

        # ── MỚI: xe rơ-moóc rời trạm sạc — lùi vào trạm nên mũi quay VÀO TRONG,
        # phải lùi mù (theo thời gian, không theo thẻ) một đoạn rồi quay đầu tại
        # chỗ để đổi mũi ra hướng tiến, TRƯỚC KHI đi theo plan bình thường. Chỉ
        # áp dụng khi trạm đó có cấu hình exit_reverse_ms/exit_turn (bỏ trống =
        # không đổi gì, giữ nguyên hành vi "đi thẳng ra" như carry hiện tại).
        _trailer_exit_steps = []
        if _exit_from_charger and agv_registry.get_config(agv_id).get('agv_type') == 'trailer':
            _exit_ms   = int(_cur_node_cfg_exit.get('exit_reverse_ms') or 0)
            _exit_turn = str(_cur_node_cfg_exit.get('exit_turn') or '').strip().lower()
            if _exit_ms > 0 and _exit_turn in ('left', 'right'):
                _turn_action = ACTION_TURN_L if _exit_turn == 'left' else ACTION_TURN_R
                # Ép tốc độ CHẬM quanh thao tác lùi+quay: không dựa vào tốc độ còn sót lại
                # từ lệnh trước đó (có thể là tốc độ tiếp cận trạm sạc, hoặc mặc định firmware).
                # Dùng đúng tốc độ đã cấu hình cho cạnh path[0]->path[1] (nếu có), fallback SPEED_SLOW
                # (KHÔNG dùng SPEED_FAST) để đảm bảo luôn chậm khi chưa rõ tốc độ cạnh.
                _exit_edge_key = f"{path[0]}_{path[1]}" if len(path) > 1 else None
                _exit_spd = edge_spd.get(_exit_edge_key, SPEED_SLOW) if _exit_edge_key else SPEED_SLOW
                # KHÔNG chèn DIR_BWD/SPEED trước REVERSE_BLIND nữa: nghi vấn firmware xử lý
                # SPEED (a=4) là chạy NGAY theo chiều đang có tại thời điểm đó (có thể vẫn
                # còn là FWD của lệnh trước, DIR_BWD chưa kịp chốt) → xe chạy tiến trước khi
                # REVERSE_BLIND kịp phát huy tác dụng. REVERSE_BLIND tự thân đã là "lùi mù
                # theo thời gian" nên không cần DIR_BWD/SPEED phụ trợ đứng trước nó.
                # Tắt Lidar quanh SUỐT thao tác lùi mù + quay (giống mọi thao tác rẽ
                # khác trong hệ thống luôn tắt Lidar trước khi rẽ, bật lại sau) —
                # trước đây bỏ sót, khiến cảm biến vẫn hoạt động lúc lùi/quay tại
                # trạm (không gian hẹp, sát vật cản xung quanh) → báo vật cản giả.
                # QUAN TRỌNG: "t" PHẢI là số nguyên (int), giống hệt phần còn lại của
                # plan (build_line_plan dùng tag=int(...)) — path[0] là STRING (path
                # luôn được str() hoá), nếu để nguyên chuỗi thì payload có "t" LẪN LỘN
                # kiểu dữ liệu (vài bước "t":"10" dạng chuỗi, các bước khác "t":10 dạng
                # số) trong CÙNG 1 plan. Bộ chunker phía firmware (ESP32) chỉ xử lý đúng
                # khi "t" là số — gặp chuỗi thì giải mã sai thành "t":0 cho toàn bộ các
                # bước trong gói đó (đã xác nhận qua log UART RX thực tế của firmware).
                _exit_tag = int(path[0])
                _trailer_exit_steps = [
                    {"t": _exit_tag, "a": ACTION_LIDAR_OFF, "v": 0},
                    {"t": _exit_tag, "a": ACTION_REVERSE_BLIND, "v": _exit_ms},
                    {"t": _exit_tag, "a": _turn_action, "v": 0},
                    {"t": _exit_tag, "a": ACTION_LIDAR_ON, "v": 0},
                    {"t": _exit_tag, "a": ACTION_DIR_FWD, "v": 0},
                    {"t": _exit_tag, "a": ACTION_SPEED, "v": _exit_spd},
                ]
                print(f"[DISPATCH] {agv_id}: xe rơ-moóc rời trạm {path[0]} → "
                      f"chèn TẮT Lidar + lùi mù {_exit_ms}ms + quay {_exit_turn} + BẬT Lidar + "
                      f"DIR_FWD + SPEED={_exit_spd} trước khi tiến ra")

        # ── Simulation: inject turn_map entry còn thiếu ─────────────────────
        # Khi simulation dispatch (13→1→2), node 1 turn_map thường chỉ có entries
        # cho chiều ngược (2_13_fwd) chứ không có 13_2_fwd.
        # Suy ra entry thiếu từ entry đối xứng: nếu `{next}_{prev}_{dir}=X` thì thử
        # dùng X cho `{prev}_{next}_{dir}` (hợp lý cho ngã 3/4 đối xứng).
        # Đồng thời truyền initial_prev_tag để plan builder tra được turn_map.
        if _is_sim_agv and _prev_tag and path and len(path) >= 2:
            _sim_start = str(path[0])
            _sim_next  = str(path[1])
            _start_na  = node_actions.get(_sim_start) or {}
            if isinstance(_start_na, dict):
                _tm = _start_na.get('turn_map') or {}
                _need_fwd = f"{_prev_tag}_{_sim_next}_fwd"
                _need_bwd = f"{_prev_tag}_{_sim_next}_bwd"
                if _need_fwd not in _tm or _need_bwd not in _tm:
                    # Tìm entry đối xứng: {next}_{prev}_{dir}
                    _sym_fwd = f"{_sim_next}_{_prev_tag}_fwd"
                    _sym_bwd = f"{_sim_next}_{_prev_tag}_bwd"
                    if _sym_fwd in _tm or _sym_bwd in _tm:
                        # Có entry đối xứng → inject entry thiếu
                        node_actions = dict(node_actions)
                        _start_na = dict(_start_na)
                        _tm = dict(_tm)
                        if _need_fwd not in _tm and _sym_fwd in _tm:
                            _tm[_need_fwd] = _tm[_sym_fwd]
                        if _need_bwd not in _tm and _sym_bwd in _tm:
                            _tm[_need_bwd] = _tm[_sym_bwd]
                        _start_na['turn_map'] = _tm
                        node_actions[_sim_start] = _start_na
                        print(f"[SIM] {agv_id}: injected turn_map "
                              f"{_need_fwd}={_tm.get(_need_fwd)} at node {_sim_start}")
            # Truyền initial_prev_tag để plan builder tra được turn_map vừa inject
            _initial_prev = _prev_tag

        # Khi AGV vừa xong bwd transit → tiếp tục direction=bwd (rẽ + lùi tiếp).
        # KHÔNG dùng direction=fwd vì firmware có thể chạy tiến trước khi rẽ.
        _line_dir = "bwd" if (_last_tdir_pre == 'bwd' and not _is_post_charge) else "fwd"

        if _lstate:
            _lstate.last_transit_direction = ''
        print(f"[DISPATCH] {agv_id}: direction={_line_dir} "
              f"(last_tdir={_last_tdir_pre!r}, post_charge={_is_post_charge})")

        # ── Xác định task_type đúng cho dispatch này ─────────────────────────
        # Staging transit: khi dispatch đến staging node được đánh dấu từ lần trước
        _staging_transit_key = (agv_id, str(dest_node))
        _dest_na_tt = node_actions.get(str(dest_node)) or {}
        _dest_arrival_tt = str(_dest_na_tt.get('arrival_action') or '').lower()
        _dest_loc_tt     = str(_dest_na_tt.get('locationType') or '').upper()
        global _pending_staging_transits
        if _staging_transit_key in _pending_staging_transits:
            _eff_task_type = 'transit'
            _pending_staging_transits.discard(_staging_transit_key)
            print(f"[DISPATCH] {agv_id}: staging transit → task_type=transit (node {dest_node})")
        elif _dest_arrival_tt == 'wait_charge' or _dest_loc_tt == 'CHARGER':
            _eff_task_type = 'return_charge'
        else:
            _eff_task_type = 'delivery'

        if split_idx is not None:
            first_seg = path[:split_idx + 1]
            # First segment (pickup/supply stop): luôn dùng 'delivery' kể cả khi transit
            # Chỉ segment TIẾP THEO đến staging node mới là transit
            _first_seg_task = 'delivery'
            # set_route tính cửa sổ rolling (window_end=first_window_end, is_complete).
            # Chỉ gửi CỬA SỔ ĐẦU (≤LOOKAHEAD node) — tránh tràn UART buffer Arduino khi
            # đoạn dài. Phần còn lại do rolling (arrived_wait_sys → _send_window) gửi tiếp.
            _rt = line_agv_handler.set_route(agv_id, first_seg, _first_seg_task, direction=_line_dir)
            _rt.has_exit_steps = bool(_trailer_exit_steps)
            plan = build_plan_window(
                full_path=first_seg, w_start=0, w_end=_rt.window_end, points=points,
                is_final=_rt.is_complete, task_type=_first_seg_task,
                node_actions=node_actions, direction=_line_dir,
                edge_speeds=edge_spd, edge_lidar=edge_lidar, agv_id=agv_id,
                initial_prev_tag=_initial_prev, initial_arrived_bwd=_initial_arrived_bwd)
            if _trailer_exit_steps:
                plan["d"] = _trailer_exit_steps + plan.get("d", [])
            send_order(agv_id, plan)
            from task_queue import agv_task_queue as _atq, CMD_GO_TO as _CGT
            # Nếu staging, đánh dấu để dispatch tiếp theo đến staging dùng transit
            if _is_staging_dispatch:
                _pending_staging_transits.add((agv_id, str(dest_node)))
            _atq.insert_next(agv_id, _CGT, dest_node=str(dest_node))
            print(f"[DISPATCH] {agv_id}: route split tại node {path[split_idx]}, "
                  f"first_seg={first_seg}, window=[0→{_rt.window_end}] final={_rt.is_complete}, tiếp→{dest_node}")
        else:
            # No split: nếu là staging dispatch trực tiếp (không qua supply node trên đường),
            # dùng 'transit' ngay để tránh lifecycle 'picking' tại staging node.
            _no_split_task = _eff_task_type
            if _is_staging_dispatch and _no_split_task == 'delivery':
                _no_split_task = 'transit'
            _rt = line_agv_handler.set_route(agv_id, path, _no_split_task, direction=_line_dir)
            _rt.has_exit_steps = bool(_trailer_exit_steps)
            # Chỉ gửi CỬA SỔ ĐẦU — rolling sẽ gửi tiếp khi path dài (tránh tràn buffer).
            plan = build_plan_window(
                full_path=path, w_start=0, w_end=_rt.window_end, points=points,
                is_final=_rt.is_complete, task_type=_no_split_task,
                node_actions=node_actions, direction=_line_dir,
                edge_speeds=edge_spd, edge_lidar=edge_lidar, agv_id=agv_id,
                initial_prev_tag=_initial_prev, initial_arrived_bwd=_initial_arrived_bwd)
            if _trailer_exit_steps:
                plan["d"] = _trailer_exit_steps + plan.get("d", [])
            send_order(agv_id, plan)
            print(f"[DISPATCH] {agv_id}: no-split window=[0→{_rt.window_end}] final={_rt.is_complete} "
                  f"(len={len(path)})")
        print(f"[DISPATCH] {agv_id}: node_actions keys={list(node_actions.keys())[:10]}")
    else:
        # ── VDA5050: ưu tiên traffic-engine-aware planning ─────────────────────
        # Dùng blocked_edges để tránh đường đã bị xe khác đặt trước (proactive).
        # Nếu thất bại → fallback về basic Dijkstra (đã tính ở trên).
        _te_success = False
        try:
            info_map = get_agv_runtime_info(agv_id)
            _raw_map = info_map.get("raw_map") or info_map.get("resolved_map_id") or ""
            _te_map_id = ensure_traffic_topology_from_loaded_map(str(_raw_map)) if _raw_map else None
            if _raw_map and _te_map_id and traffic_engine.has_map(_te_map_id):
                _traffic_map_id = _te_map_id
                if True:
                    _blocked = traffic_engine.get_reserved_edges(
                        _traffic_map_id, exclude_agv=agv_id
                    )
                    _plan_result = traffic_engine.plan_route(
                        map_id=_traffic_map_id,
                        agv_id=agv_id,
                        start_node=str(current_node),
                        goal_node=str(dest_node),
                        blocked_edges=_blocked,
                        reason="DISPATCH_GO_TO",
                    )
                    if _plan_result.success and _plan_result.route:
                        traffic_engine.activate_route(agv_id, _traffic_map_id, _plan_result.route)
                        agv_state_data = agv_manager.get_agv(agv_id) or {}
                        te_order, te_path = build_order_for_traffic_route(
                            agv_id, _plan_result.route, agv_state_data
                        )
                        from mqtt_client import send_generated_order
                        send_generated_order(agv_id, te_order)
                        print(f"[DISPATCH] {agv_id}: traffic-aware route → {te_path}")
                        _te_success = True
        except Exception as _te_err:
            print(f"[DISPATCH] {agv_id}: traffic-aware planning failed ({_te_err}) — fallback Dijkstra")

        if not _te_success:
            from mqtt_client import build_order_with_path, send_generated_order
            order = build_order_with_path(agv_id, route_nodes, route_edges, end_action_type=None)
            send_generated_order(agv_id, order)
    return True


import datetime as _dt

# Ngưỡng online/offline — giống hệt Web_UI/agv_manager.py STATUS_THRESHOLD_SECONDS
_AGV_ONLINE_THRESHOLD_SEC = 30

def _conn_from_last_seen(last_seen) -> str:
    """Tính connection status từ DB last_seen — cùng logic với AGVManager."""
    if not last_seen:
        return "OFFLINE"
    try:
        now_utc = _dt.datetime.now(_dt.timezone.utc)
        # Đảm bảo timezone-aware để tránh lỗi so sánh
        ls = last_seen if last_seen.tzinfo else last_seen.replace(tzinfo=_dt.timezone.utc)
        return "ONLINE" if (now_utc - ls).total_seconds() <= _AGV_ONLINE_THRESHOLD_SEC else "OFFLINE"
    except Exception:
        return "OFFLINE"


@app.get("/api/execute/agv-list")
async def execute_agv_list():
    """Danh sách AGV từ bảng agv_devices, kết hợp trạng thái real-time.
    Dùng psycopg2 (sync trong thread) — cùng pattern với agv_manager.py."""
    from line_agv_handler import line_agv_handler
    from task_queue import agv_task_queue

    # ── Đọc từ DB bằng psycopg2 (giống agv_manager.py, không bị lỗi INET type) ─
    def _fetch_devices():
        import psycopg2, os
        cfg = {
            "host":     os.environ.get("PGHOST",     "localhost"),
            "port":     os.environ.get("PGPORT",     "5432"),
            "user":     os.environ.get("PGUSER",     "postgres"),
            "password": os.environ.get("PGPASSWORD", "ducmanh1801"),
            "dbname":   os.environ.get("PGDATABASE", "TOT_AGV"),
        }
        conn = psycopg2.connect(**cfg)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT name, agv_type, CAST(ip AS TEXT), port, factory, last_seen, "
                    "subnet, gateway, dns, map_id, COALESCE(can_reverse, TRUE) "
                    "FROM agv_devices ORDER BY name"
                )
                return cur.fetchall()
        finally:
            conn.close()

    try:
        db_rows = await asyncio.to_thread(_fetch_devices)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"DB error: {e}")

    # psycopg2 trả về tuple: (name, agv_type, ip_text, port, factory, last_seen, subnet, gateway, dns, map_id, can_reverse)
    result = []
    for (name, agv_type_raw, ip_text, port, factory_val, last_seen, subnet_val, gateway_val, dns_val, map_id_val, can_reverse_val) in db_rows:
        agv_id       = str(name)
        agv_type_raw = str(agv_type_raw or "")
        is_line      = not agv_type_raw.lower().startswith("slam")
        agv_type     = "LINE" if is_line else "VDA5050"
        last_seen_iso = last_seen.isoformat() if last_seen else None

        if is_line:
            st = line_agv_handler.state_store.get(agv_id)
            # Dùng DB last_seen — cùng nguồn dữ liệu với AGVManager
            # last_seen được cập nhật bởi agv_heartbeat.touch() mỗi khi nhận bất kỳ MQTT nào
            line_conn = _conn_from_last_seen(last_seen)
            result.append({
                "agv_id":           agv_id,
                "agv_type":         agv_type,
                "agv_type_raw":     agv_type_raw,
                "ip":               ip_text or None,
                "port":             port,
                "factory":          factory_val or "",
                "last_seen":        last_seen_iso,
                "current_node":     (str(st.current_tag)
                                     if (st and st.current_tag is not None) else None),
                "battery":          st.battery if st else None,
                "battery_low":      st.battery_low if st else False,
                "battery_blocking": st.battery_blocking if st else False,
                "driving":          st.driving if st else False,
                "paused":           st.paused if st else False,
                "connection":       line_conn,
                "operating_mode":   st.operating_mode if st else "MANUAL",
                "task_lifecycle":   st.task_lifecycle if st else None,
                "hook_pending":     st.hook_pending if st else None,
                "hook_state":       st.hook_state if st else None,
                "is_busy":          agv_task_queue.is_busy(agv_id),
                "queue_size":       agv_task_queue.queue_size(agv_id),
                "running_cmd":      agv_task_queue.get_running(agv_id),
                "subnet":           subnet_val  or None,
                "gateway":          gateway_val or None,
                "dns":              dns_val     or None,
                "map_id":           str(map_id_val) if map_id_val else None,
                "can_reverse":      bool(can_reverse_val),
            })
        else:
            st   = agv_manager.get_agv(agv_id) or {}
            batt = (st.get("batteryState") or {}).get("batteryCharge")
            result.append({
                "agv_id":           agv_id,
                "agv_type":         agv_type,
                "agv_type_raw":     agv_type_raw,
                "ip":               ip_text or None,
                "port":             port,
                "factory":          factory_val or "",
                "last_seen":        last_seen_iso,
                "current_node":     str(st.get("lastNodeId") or "") or None,
                "battery":          batt,
                "battery_low":      False,
                "battery_blocking": False,
                "driving":          bool(st.get("driving")),
                "paused":           bool(st.get("paused")),
                "connection":       _conn_from_last_seen(last_seen),
                "operating_mode":   st.get("operatingMode", "MANUAL"),
                "is_busy":          agv_task_queue.is_busy(agv_id),
                "queue_size":       agv_task_queue.queue_size(agv_id),
                "running_cmd":      agv_task_queue.get_running(agv_id),
                "subnet":           subnet_val  or None,
                "gateway":          gateway_val or None,
                "dns":              dns_val     or None,
                "map_id":           str(map_id_val) if map_id_val else None,
                "can_reverse":      bool(can_reverse_val),
            })

    return {"agvs": result, "total": len(result)}


@app.post("/api/simulation/start")
async def simulation_start(request: Request):
    """Bắt đầu phiên chạy mô phỏng cho 1 AGV."""
    import simulation_manager as _sm
    body = await request.json()
    agv_id       = str(body.get("agv_id", "")).strip()
    route        = [str(n) for n in (body.get("route") or []) if n]
    route_type   = str(body.get("route_type", "loop"))
    total_cycles = int(body.get("total_cycles", 10))
    delay_s      = float(body.get("delay_s", 1.0))

    if not agv_id:
        raise HTTPException(400, "agv_id required")
    if len(route) < 2:
        raise HTTPException(400, "Lộ trình cần ít nhất 2 node")
    if total_cycles < 1 or total_cycles > 9999:
        raise HTTPException(400, "total_cycles: 1–9999")

    # Hủy lệnh cũ đang chờ
    from task_queue import agv_task_queue
    agv_task_queue.cancel_all(agv_id)

    sess = _sm.create_session(agv_id, route, route_type, total_cycles, delay_s)
    task = asyncio.create_task(_sm.run_session(sess))
    sess._task = task
    return {"success": True, "session": sess.to_dict()}


@app.post("/api/simulation/pause/{session_id}")
async def simulation_pause(session_id: str):
    import simulation_manager as _sm
    sess = _sm.get_session(session_id)
    if not sess:
        raise HTTPException(404, "Session không tồn tại")
    if sess.status == "running":
        sess.status = "paused"
    return {"success": True, "session": sess.to_dict()}


@app.post("/api/simulation/resume/{session_id}")
async def simulation_resume(session_id: str):
    import simulation_manager as _sm
    sess = _sm.get_session(session_id)
    if not sess:
        raise HTTPException(404, "Session không tồn tại")
    if sess.status == "paused":
        sess.status = "running"
    return {"success": True, "session": sess.to_dict()}


@app.post("/api/simulation/stop/{session_id}")
async def simulation_stop(session_id: str):
    import simulation_manager as _sm
    from task_queue import agv_task_queue
    sess = _sm.get_session(session_id)
    if not sess:
        raise HTTPException(404, "Session không tồn tại")
    sess.status = "stopped"
    if sess._task and not sess._task.done():
        sess._task.cancel()
    agv_task_queue.cancel_all(sess.agv_id)
    _sm.remove_session(session_id)
    return {"success": True, "stopped": session_id}


@app.get("/api/simulation/status/{agv_id}")
async def simulation_status(agv_id: str):
    import simulation_manager as _sm
    sess = _sm.get_session_by_agv(agv_id)
    if not sess:
        return {"active": False, "session": None}
    return {"active": sess.status in ("running", "paused"), "session": sess.to_dict()}


@app.get("/api/simulation/list")
async def simulation_list():
    import simulation_manager as _sm
    return {"sessions": _sm.list_sessions()}


@app.get("/api/simulation/route/{agv_id}")
async def simulation_route(agv_id: str):
    """Trả về lộ trình mô phỏng để vẽ trên bản đồ."""
    import simulation_manager as _sm
    sess = _sm.get_session_by_agv(agv_id)
    if not sess or sess.status not in ("running", "paused"):
        return {"active": False, "route": [], "current_dest": None}
    return {
        "active":       True,
        "route":        sess.full_sequence,
        "current_dest": sess.current_dest,
        "current_step": sess.current_step,
        "route_type":   sess.route_type,
        "total_cycles": sess.total_cycles,
        "current_cycle":sess.current_cycle,
    }


@app.get("/api/execute/team-nodes")
async def execute_team_nodes(map_id: str | None = None):
    """
    Trả về danh sách các node DROPOFF có gán số Tổ — dùng để người dùng chọn
    'Tổ X' thay vì phải biết số node cụ thể.

    Hỗ trợ CẢ 2 kiểu cấu hình:
      - Kiểu cũ: action.team (1 số nguyên/1 node) — AGV carry, map cũ.
      - Kiểu mới: action.trailer_role=='drop' + action.trailer_drop_teams
        (mảng số Tổ dùng CHUNG 1 node) — xe rơ-moóc. THIẾU nhánh này khiến
        map chỉ cấu hình kiểu mới trả về danh sách Tổ RỖNG — người dùng phải
        chọn thẳng node thô, bỏ qua toàn bộ cơ chế Trailer Roundtrip.
    """
    async with app.state.db_pool.acquire() as conn:
        mid = str(map_id) if map_id else str(map_manager.current_map_id or "")
        rows = await conn.fetch(
            """SELECT name_id, name, action
               FROM agv_map_points
               WHERE CAST(map_id AS TEXT) = $1
                 AND (
                     (action->>'locationType' = 'DROPOFF' AND (action->>'team') IS NOT NULL)
                     OR (action->>'trailer_role' = 'drop' AND jsonb_typeof(action->'trailer_drop_teams') = 'array')
                 )""",
            mid,
        )
    result: list[dict] = []
    seen_teams: set[int] = set()
    for r in rows:
        act = r["action"] or {}
        if isinstance(act, str):
            import json as _j; act = _j.loads(act)
        team_num = act.get("team")
        if team_num is not None and int(team_num) not in seen_teams:
            seen_teams.add(int(team_num))
            result.append({
                "node_id":  str(r["name_id"]),
                "name":     r["name"] or str(r["name_id"]),
                "team":     int(team_num),
                "label":    f"Tổ {team_num}",
                "action":   act,
            })
        for _t in (act.get("trailer_drop_teams") or []):
            try:
                _tn = int(str(_t).strip())
            except (TypeError, ValueError):
                continue
            if _tn in seen_teams:
                continue
            seen_teams.add(_tn)
            result.append({
                "node_id":  str(r["name_id"]),
                "name":     r["name"] or str(r["name_id"]),
                "team":     _tn,
                "label":    f"Tổ {_tn}",
                "action":   act,
            })
    result.sort(key=lambda x: x["team"])
    return {"teams": result, "total": len(result)}


async def _resolve_team_node(map_id: str, team: int, agv_type: str, want_pickup: bool) -> str | None:
    """Tìm node phục vụ 1 Tổ, ưu tiên node đánh dấu đúng agv_type (team_agv_type),
    fallback node không đánh dấu (dùng chung mọi loại xe). Node đánh dấu cho loại
    KHÁC thì bỏ qua — cho phép map tách hẳn vị trí thả rỗng/lấy đầy riêng theo xe.

    Ưu tiên 1: field 'trailer_role' TƯỜNG MINH ('drop'|'pickup') + cùng số Tổ —
    không quan tâm locationType/arrival_action là gì (2 node cùng Tổ, chỉ khác
    Vai trò, các field khác có thể giống hệt nhau, vd cùng DROPOFF).
    Ưu tiên 1b (dùng chung nhiều Tổ): 1 node THẢ RỖNG hoặc LẤY ĐẦY dùng CHUNG
    cho nhiều Tổ — khai tường minh qua field 'trailer_pickup_teams' (pickup)
    hoặc 'trailer_drop_teams' (drop) (mảng số Tổ, vd [1,2]) thay vì field
    'team' đơn (chỉ chứa được 1 số). KHÔNG suy luận qua supply_group — tránh
    lặp lại bug do suy luận sai (map chung field với cơ chế carry cũ).
    Ưu tiên 2 (map chưa cấu hình trailer_role/trailer_*_teams): suy luận
    theo cơ chế cũ — want_pickup=False → DROPOFF/wait_user + team;
    want_pickup=True → wait_sys + supply_group chứa team.
    """
    import json as _j
    role = "pickup" if want_pickup else "drop"
    shared_field = "trailer_pickup_teams" if want_pickup else "trailer_drop_teams"
    async with app.state.db_pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT name_id, action FROM agv_map_points
               WHERE CAST(map_id AS TEXT) = $1
                 AND action->>'trailer_role' = $2
                 AND (action->>'team')::int = $3""",
            str(map_id), role, team,
        )
        if not rows:
            rows = await conn.fetch(
                f"""SELECT name_id, action FROM agv_map_points
                   WHERE CAST(map_id AS TEXT) = $1
                     AND action->>'trailer_role' = $2
                     AND action->'{shared_field}' ? $3::text""",
                str(map_id), role, str(team),
            )
        if not rows:
            if want_pickup:
                rows = await conn.fetch(
                    """SELECT name_id, action FROM agv_map_points
                       WHERE CAST(map_id AS TEXT) = $1
                         AND action->>'arrival_action' = 'wait_sys'
                         AND action->'supply_group' ? $2::text""",
                    str(map_id), str(team),
                )
            else:
                # Node "thả rỗng" có thể là locationType=DROPOFF HOẶC chỉ là điểm
                # giao hàng thường (arrival_action=wait_user) được gán thêm số Tổ —
                # AGV carry vẫn dùng node đó bình thường (chờ xác nhận), không đổi gì.
                rows = await conn.fetch(
                    """SELECT name_id, action FROM agv_map_points
                       WHERE CAST(map_id AS TEXT) = $1
                         AND (action->>'locationType' = 'DROPOFF'
                              OR action->>'arrival_action' = 'wait_user')
                         AND (action->>'team')::int = $2""",
                    str(map_id), team,
                )
    exact, generic = [], []
    for r in rows:
        act = r["action"] or {}
        if isinstance(act, str):
            act = _j.loads(act)
        tat = str(act.get("team_agv_type") or "").strip().lower()
        if tat == agv_type:
            exact.append(str(r["name_id"]))
        elif not tat:
            generic.append(str(r["name_id"]))
    if exact:
        return exact[0]
    if generic:
        return generic[0]
    return None


async def _find_trailer_staging_node(map_id: str) -> str | None:
    """Tìm node được đánh dấu 'trailer_staging=yes' trên map — điểm thả hàng
    đầy cố định, dùng chung cho MỌI Tổ (không cần nhập tay lúc dispatch)."""
    async with app.state.db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT name_id FROM agv_map_points
               WHERE CAST(map_id AS TEXT) = $1
                 AND action->>'trailer_staging' = 'yes'
               LIMIT 1""",
            str(map_id),
        )
    return str(row["name_id"]) if row else None


async def _find_trailer_empty_staging_node(map_id: str) -> str | None:
    """Node đánh dấu 'trailer_empty_staging=yes' — điểm lấy hàng rỗng cố định
    gần trạm (đầu quy trình, trước khi ra Tổ). TUỲ CHỌN — có thể trùng với
    node trailer_staging (1 node dùng chung cả 2 chức năng)."""
    async with app.state.db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT name_id FROM agv_map_points
               WHERE CAST(map_id AS TEXT) = $1
                 AND action->>'trailer_empty_staging' = 'yes'
               LIMIT 1""",
            str(map_id),
        )
    return str(row["name_id"]) if row else None


class TrailerRoundtripRequest(BaseModel):
    agv_id:       str
    team:         int
    staging_node: str | None = None   # tuỳ chọn — bỏ trống sẽ tự tìm node đánh dấu trailer_staging trên map


@app.post("/api/execute/trailer-roundtrip")
async def execute_trailer_roundtrip(req: TrailerRoundtripRequest):
    """
    Điều phối chu trình cho AGV rơ-moóc/đầu kéo phục vụ 1 Tổ:
      0. (tuỳ chọn) → node lấy hàng rỗng cố định gần trạm — tới nơi chờ, cảm
         biến tự hạ móc khi xe hàng rỗng được đưa vào — CHỜ XÁC NHẬN TRÊN WEB
         (giống hệt chặng lấy hàng đầy tại Tổ, không tự động đi tiếp).
         Chỉ chèn nếu map đã đánh dấu 'trailer_empty_staging=yes'; không có
         thì bỏ qua, giữ đúng hành vi 4 chặng cũ (xe coi như đã có sẵn hàng rỗng).
      1. → node thả rỗng (Tổ, đường đi)   — tới nơi tự nâng móc thả rỗng, TỰ ĐỘNG đi tiếp
      2. → node lấy đầy (Tổ, đường về)    — tới nơi chờ (móc đã nâng sẵn từ chặng 1)
      3. (cảm biến tự hạ móc khi xe đầy gắn xong) — CHỜ XÁC NHẬN TRÊN WEB
      4. → staging_node (vd node 19)      — tới nơi tự nâng móc thả đầy, TỰ ĐỘNG đi tiếp
      5. → về trạm (go_charge)
    """
    from task_queue import agv_task_queue, CMD_GO_TO, CMD_GO_CHARGE
    from agv_registry import agv_registry
    from mqtt_client import get_agv_runtime_info
    from line_agv_handler import _pending_empty_pickup_legs

    agv_id = req.agv_id.strip()
    if agv_id not in agv_registry.all_ids():
        raise HTTPException(status_code=404, detail=f"AGV '{agv_id}' không tìm thấy")

    agv_type = str(agv_registry.get_config(agv_id).get("agv_type") or "").strip().lower()
    if agv_type != "trailer":
        raise HTTPException(status_code=400,
            detail=f"Lệnh này chỉ dành cho AGV loại trailer (AGV '{agv_id}' là loại '{agv_type}')")

    info   = get_agv_runtime_info(agv_id)
    map_id = info.get("resolved_map_id")
    if not map_id:
        raise HTTPException(status_code=400, detail=f"AGV {agv_id} chưa có map hiện tại")

    drop_node = await _resolve_team_node(map_id, req.team, agv_type, want_pickup=False)
    if not drop_node:
        raise HTTPException(status_code=404,
            detail=f"Không tìm thấy node thả rỗng cho Tổ {req.team} (map={map_id}, loại xe={agv_type})")

    pickup_node = await _resolve_team_node(map_id, req.team, agv_type, want_pickup=True)
    if not pickup_node:
        raise HTTPException(status_code=404,
            detail=f"Không tìm thấy node lấy đầy cho Tổ {req.team} (map={map_id}, loại xe={agv_type})")

    staging_node = (req.staging_node or "").strip()
    if not staging_node:
        staging_node = await _find_trailer_staging_node(map_id)
        if not staging_node:
            raise HTTPException(status_code=404,
                detail=f"Map {map_id} chưa đánh dấu node 'Điểm thả hàng đầy cố định (Staging)' "
                       f"— vào Tạo bản đồ, chọn node và tick ô đó.")

    # Điểm lấy hàng rỗng cố định gần trạm — TUỲ CHỌN, bỏ qua chặng này nếu map
    # chưa cấu hình (giữ đúng hành vi 4 chặng cũ, không bắt buộc).
    empty_staging_node = await _find_trailer_empty_staging_node(map_id)

    # Chèn theo thứ tự NGƯỢC — insert_next luôn chèn vào ĐẦU hàng đợi, nên gọi
    # từ chặng CUỐI về chặng ĐẦU để thứ tự thực thi đúng:
    # (lấy rỗng) → drop → pickup → staging → charge.
    agv_task_queue.insert_next(agv_id, CMD_GO_CHARGE, dest_node=None)
    agv_task_queue.insert_next(agv_id, CMD_GO_TO, dest_node=staging_node)
    agv_task_queue.insert_next(agv_id, CMD_GO_TO, dest_node=pickup_node)
    agv_task_queue.insert_next(agv_id, CMD_GO_TO, dest_node=drop_node)
    if empty_staging_node:
        # Đánh dấu TRƯỚC khi chèn lệnh — arrival handler cần thấy dấu này ngay
        # khi xe tới, tránh race nếu xe tới rất nhanh.
        _pending_empty_pickup_legs.add((agv_id, str(empty_staging_node)))
        agv_task_queue.insert_next(agv_id, CMD_GO_TO, dest_node=empty_staging_node)

    # Nếu xe đang rảnh, kích hoạt chặng đầu ngay (dùng lại đúng cơ chế auto-dispatch
    # của on_agv_completed — an toàn kể cả khi không có gì đang "running").
    if not agv_task_queue.is_busy(agv_id):
        agv_task_queue.on_agv_completed(agv_id, notes="trailer_roundtrip_start", auto_dispatch=True)

    return {
        "success": True, "agv_id": agv_id, "team": req.team, "agv_type": agv_type,
        "legs": {
            "0_pick_empty": empty_staging_node or "(không cấu hình — bỏ qua chặng này)",
            "1_drop_empty": drop_node,
            "2_pick_full":  pickup_node,
            "3_confirm":    "chờ xác nhận web sau khi cảm biến hạ móc",
            "4_staging":    staging_node,
            "5_return":     "go_charge",
        },
    }


class TrailerMultiPickupRequest(BaseModel):
    agv_id: str
    teams:  list[int]


@app.post("/api/execute/trailer-multi-pickup")
async def execute_trailer_multi_pickup(req: TrailerMultiPickupRequest):
    """
    Gom LẤY HÀNG ĐẦY từ NHIỀU Tổ trong 1 chuyến (milk run) cho AGV rơ-moóc —
    dùng khi mỗi Tổ đã có sẵn xe hàng đầy riêng chờ (chặng thả rỗng cho từng
    Tổ đã làm trước đó, riêng lẻ — KHÔNG thuộc API này):
      1. Tính khoảng cách từ vị trí xe hiện tại tới điểm lấy đầy của từng Tổ,
         sắp GẦN → XA.
      2. Tổ GẦN NHẤT: móc cơ khí đầy đủ như bình thường (nâng móc chờ → người
         dùng bấm Hạ móc → xác nhận web) — dùng đúng logic pickup mặc định,
         không cần đánh dấu gì thêm.
      3. Các Tổ SAU: CHỈ dừng + chờ xác nhận thủ công (nút "ĐÃ LẤY HÀNG XONG"
         hiện có) — KHÔNG móc lại, vì hàng được công nhân chuyển tay từ xe
         của Tổ đó sang xe đang được kéo theo AGV.
      4. Sau Tổ cuối: về node staging (thả hàng đầy) → sạc — như luồng cũ.
    """
    from task_queue import agv_task_queue, CMD_GO_TO, CMD_GO_CHARGE
    from agv_registry import agv_registry
    from mqtt_client import get_agv_runtime_info
    from line_agv_handler import _pending_confirm_only_legs

    agv_id = req.agv_id.strip()
    if agv_id not in agv_registry.all_ids():
        raise HTTPException(status_code=404, detail=f"AGV '{agv_id}' không tìm thấy")

    agv_type = str(agv_registry.get_config(agv_id).get("agv_type") or "").strip().lower()
    if agv_type != "trailer":
        raise HTTPException(status_code=400,
            detail=f"Lệnh này chỉ dành cho AGV loại trailer (AGV '{agv_id}' là loại '{agv_type}')")

    if not req.teams:
        raise HTTPException(status_code=400, detail="Cần chọn ít nhất 1 Tổ")

    info   = get_agv_runtime_info(agv_id)
    map_id = info.get("resolved_map_id")
    if not map_id:
        raise HTTPException(status_code=400, detail=f"AGV {agv_id} chưa có map hiện tại")
    current_node = info.get("current_node")

    # Resolve node lấy đầy cho từng Tổ — báo lỗi ngay nếu Tổ nào thiếu cấu hình,
    # tránh chèn 1 chuyến dở dang (thiếu 1 Tổ giữa chừng sẽ rất khó xử lý sau).
    pickup_by_team: dict[int, str] = {}
    for team in req.teams:
        node = await _resolve_team_node(map_id, team, agv_type, want_pickup=True)
        if not node:
            raise HTTPException(status_code=404,
                detail=f"Không tìm thấy node lấy đầy cho Tổ {team} (map={map_id})")
        pickup_by_team[team] = str(node)

    # Nhiều Tổ có thể dùng CHUNG 1 node lấy hàng (trailer_pickup_teams) — gộp
    # lại, chỉ dừng 1 lần tại node đó, phục vụ đủ các Tổ cùng lúc.
    teams_by_node: dict[str, list[int]] = {}
    for team, node in pickup_by_team.items():
        teams_by_node.setdefault(node, []).append(team)
    unique_nodes = list(teams_by_node.keys())

    staging_node = await _find_trailer_staging_node(map_id)
    if not staging_node:
        raise HTTPException(status_code=404,
            detail=f"Map {map_id} chưa đánh dấu node 'Điểm thả hàng đầy cố định (Staging)' "
                   f"— vào Tạo bản đồ, chọn node và tick ô đó.")

    # Xe rơ-moóc CHỈ TIẾN — sắp theo khoảng cách NGƯỢC VỀ staging_node (xa nhất
    # trước), KHÔNG dùng khoảng cách thuận từ vị trí hiện tại (xem docstring
    # _order_pickups_for_forward_loop để biết lý do: đường tắt ở đầu vòng có
    # thể khiến Tổ xa lại tính ra khoảng cách thuận ngắn hơn Tổ gần).
    sorted_nodes = _order_pickups_for_forward_loop(unique_nodes, staging_node)

    # Chèn theo thứ tự NGƯỢC — insert_next luôn chèn vào ĐẦU hàng đợi.
    agv_task_queue.insert_next(agv_id, CMD_GO_CHARGE, dest_node=None)
    agv_task_queue.insert_next(agv_id, CMD_GO_TO, dest_node=staging_node)
    # Các node THỨ 2 trở đi (xa dần) — đánh dấu "chỉ xác nhận" TRƯỚC khi chèn.
    for node in reversed(sorted_nodes[1:]):
        _pending_confirm_only_legs.add((agv_id, node))
        agv_task_queue.insert_next(agv_id, CMD_GO_TO, dest_node=node)
    # Node GẦN NHẤT — móc cơ khí đầy đủ, không đánh dấu gì (dùng logic mặc định).
    agv_task_queue.insert_next(agv_id, CMD_GO_TO, dest_node=sorted_nodes[0])

    if not agv_task_queue.is_busy(agv_id):
        agv_task_queue.on_agv_completed(agv_id, notes="trailer_multi_pickup_start", auto_dispatch=True)

    return {
        "success": True, "agv_id": agv_id, "teams": req.teams,
        "legs": {
            "0_hook_pickup":        {"node": sorted_nodes[0], "teams": teams_by_node[sorted_nodes[0]]},
            "confirm_only_pickups": [{"node": n, "teams": teams_by_node[n]} for n in sorted_nodes[1:]],
            "staging":              staging_node,
            "return":               "go_charge",
        },
    }


@app.get("/api/execute/map-nodes")
async def execute_map_nodes():
    """Danh sách node từ bản đồ đang load (dùng để chọn điểm đến)."""
    points    = getattr(map_manager, "all_points", []) or []
    map_id    = getattr(map_manager, "current_map_id", None)
    node_list = [
        {
            "node_id": str(p.get("name_id", "")),
            "name":    p.get("name") or str(p.get("name_id", "")),
            "x":       p.get("x"),
            "y":       p.get("y"),
            "action":  p.get("action"),
        }
        for p in points
        if p.get("name_id") is not None
    ]
    return {"map_id": map_id, "nodes": node_list, "total": len(node_list)}


@app.get("/api/execute/agv-positions")
async def execute_agv_positions(map_id: str):
    """Vị trí thực tế của các AGV được gán cho bản đồ map_id.
    Tra cứu agv_map_points bằng current_node từ live state."""
    from line_agv_handler import line_agv_handler

    def _fetch(mid: str):
        import psycopg2, os
        cfg = {
            "host":     os.environ.get("PGHOST",     "localhost"),
            "port":     os.environ.get("PGPORT",     "5432"),
            "user":     os.environ.get("PGUSER",     "postgres"),
            "password": os.environ.get("PGPASSWORD", "ducmanh1801"),
            "dbname":   os.environ.get("PGDATABASE", "TOT_AGV"),
        }
        conn = psycopg2.connect(**cfg)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT name, agv_type, last_seen FROM agv_devices WHERE map_id = %s",
                    (mid,)
                )
                devices = cur.fetchall()
                cur.execute(
                    "SELECT CAST(name_id AS TEXT), x, y FROM agv_map_points "
                    "WHERE CAST(map_id AS TEXT) = %s",
                    (mid,)
                )
                pts = {r[0]: {"x": float(r[1] or 0), "y": float(r[2] or 0)}
                       for r in cur.fetchall()}
            return devices, pts
        finally:
            conn.close()

    try:
        devices, pts = await asyncio.to_thread(_fetch, map_id)
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))

    result = []
    for (name, agv_type_raw, dev_last_seen) in devices:
        agv_id       = str(name)
        agv_type_raw = str(agv_type_raw or "")
        is_line      = not agv_type_raw.lower().startswith("slam")

        # Dùng DB last_seen cho tất cả loại AGV — cùng logic với AGVManager
        connection = _conn_from_last_seen(dev_last_seen)

        if is_line:
            st           = line_agv_handler.state_store.get(agv_id)
            current_node = str(st.current_tag) if (st and st.current_tag is not None and st.current_tag != 0) else None
            driving  = st.driving if st else False
            battery  = st.battery if st else None
        else:
            st           = agv_manager.get_agv(agv_id) or {}
            current_node = str(st.get("lastNodeId") or "") or None
            driving      = bool(st.get("driving"))
            battery      = st.get("batteryState", {}).get("batteryCharge") if st else None

        pt = pts.get(current_node) if current_node else None
        result.append({
            "agv_id":       agv_id,
            "agv_type_raw": agv_type_raw,
            "x":            pt["x"] if pt else None,
            "y":            pt["y"] if pt else None,
            "current_node": current_node,
            "connection":   connection,
            "driving":      driving,
            "battery":      battery,
            "has_position": pt is not None,
        })

    return {"positions": result, "map_id": map_id}


@app.get("/api/execute/agv-routes")
async def execute_agv_routes(map_id: str):
    """Trả về route đang di chuyển của các AGV trên bản đồ map_id."""
    from line_agv_handler import line_agv_handler
    from task_queue import agv_task_queue

    def _fetch_devices(mid: str):
        import psycopg2, os
        cfg = {
            "host":     os.environ.get("PGHOST",     "localhost"),
            "port":     os.environ.get("PGPORT",     "5432"),
            "user":     os.environ.get("PGUSER",     "postgres"),
            "password": os.environ.get("PGPASSWORD", "ducmanh1801"),
            "dbname":   os.environ.get("PGDATABASE", "TOT_AGV"),
        }
        conn = psycopg2.connect(**cfg)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT name, agv_type FROM agv_devices WHERE map_id = %s", (mid,))
                return cur.fetchall()
        finally:
            conn.close()

    try:
        devices = await asyncio.to_thread(_fetch_devices, map_id)
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))

    routes = {}
    for (name, agv_type_raw) in devices:
        agv_id       = str(name)
        is_line      = not str(agv_type_raw or "").lower().startswith("slam")

        if is_line:
            st    = line_agv_handler.state_store.get(agv_id)
            route = line_agv_handler.get_route(agv_id)

            current_node = str(st.current_tag) if (st and st.current_tag is not None) else None
            prev_node    = str(st.prev_tag)    if (st and st.prev_tag)                else None
            next_node    = str(st.next_tag)    if (st and st.next_tag)                else None
            driving      = st.driving if st else False

            path        = []
            current_idx = 0
            if route and route.full_path:
                path = route.full_path
                if current_node and current_node in path:
                    current_idx = path.index(current_node)

            running_cmd = agv_task_queue.get_running(agv_id)
            dest_node   = str(running_cmd["dest_node"]) if (running_cmd and running_cmd.get("dest_node")) else None

            routes[agv_id] = {
                "current_node": current_node,
                "prev_node":    prev_node,
                "next_node":    next_node,
                "dest_node":    dest_node,
                "path":         path,
                "current_idx":  current_idx,
                "driving":      driving,
                "agv_type":     "LINE",
            }
        else:
            st           = agv_manager.get_agv(agv_id) or {}
            current_node = str(st.get("lastNodeId") or "") or None
            driving      = bool(st.get("driving"))
            running_cmd  = agv_task_queue.get_running(agv_id)
            dest_node    = str(running_cmd["dest_node"]) if (running_cmd and running_cmd.get("dest_node")) else None

            routes[agv_id] = {
                "current_node": current_node,
                "prev_node":    None,
                "next_node":    None,
                "dest_node":    dest_node,
                "path":         [current_node] if current_node else [],
                "current_idx":  0,
                "driving":      driving,
                "agv_type":     "SLAM",
            }

    return {"routes": routes, "map_id": map_id}


@app.get("/api/execute/traffic-status")
async def execute_traffic_status():
    """Trạng thái TrafficCoordinator: đường đi đã đăng ký + head-on warnings."""
    from line_agv_handler import traffic_coordinator as _tc, _line_blocked_edges
    return {
        "registered": _tc.get_status(),
        "blocked_edges": list(_line_blocked_edges.keys()),
    }


@app.get("/api/execute/traffic-log")
async def execute_traffic_log(n: int = 200):
    """
    Lọc log buffer lấy ra các dòng liên quan đến điều phối giao thông.
    Hữu ích để debug traffic mà không bị chìm trong HTTP access log.
    Tham số ?n=200 để lấy N dòng gần nhất (mặc định 200).
    """
    from log_buffer import get_logs
    _KEYWORDS = (
        "[TRAFFIC]", "[PLAN]", "[DISPATCH]",
        "[LINE_AGV]", "[STATION]", "[QUEUE]",
        "HEAD-ON", "head-on", "parking", "conflict",
        "reserve edge", "release edge", "released all",
        "set_route", "off_route", "obstacle",
        "lifecycle", "wait_sys", "wait_charge",
    )
    all_lines = get_logs()
    filtered = [
        ln for ln in all_lines
        if any(kw in ln for kw in _KEYWORDS)
    ]
    # Trả n dòng cuối
    return {
        "total_filtered": len(filtered),
        "lines": filtered[-n:],
    }


class ExecuteDispatchRequest(BaseModel):
    agv_id:        str
    command:       str              # go_to | go_charge | go_wait | stop | resume
    dest_node:     str | None = None    # bắt buộc khi command=go_to
    start_node:    str | None = None    # override vị trí xuất phát
    session_id:    str | None = None    # nhóm các bước của cùng 1 lượt workflow
    session_label: str | None = None    # tên workflow / nhãn hiển thị


async def _finalize_supply_batch(key: tuple) -> None:
    """Sau khi gom đủ lệnh cùng lượt cấp hàng: sinh lệnh lấy hàng tại TẤT CẢ điểm
    cấp (sắp theo khoảng cách, gần trạm trước) TRƯỚC, rồi mới tới các lệnh giao +
    sạc — enqueue theo đúng thứ tự đó. Mỗi điểm cấp dừng + chờ xác nhận như nhau."""
    batch = _supply_batch.pop(key, None)
    if not batch or not batch.get("commands"):
        return
    agv_id, session_id = key
    session_label = batch.get("session_label")
    cmds = batch["commands"]   # [(command, dest_node, start_node), ...] theo thứ tự nhận

    from task_queue import agv_task_queue, CMD_GO_TO, CMD_GO_CHARGE
    from mqtt_client import get_agv_runtime_info

    # DEDUPE go_to trùng CÙNG đích trong 1 lượt (giữ lần xuất hiện ĐẦU) — gốc: 1 node
    # thả rỗng (trailer_drop_teams) có thể phục vụ NHIỀU Tổ cùng lúc (vd node 101
    # dùng chung cho Tổ 32 VÀ Tổ 22) — nếu app/Web UI gọi dispatch riêng cho TỪNG Tổ
    # (không gộp theo node), batch sẽ nhận 2 lệnh go_to(101) giống hệt nhau. Xe rơ-moóc
    # CHỈ TIẾN nên "ghé lại" node ĐÃ THẢ chỉ có thể đi vòng HẾT sơ đồ (đã hết hàng
    # rỗng để thả) — tốn quãng đường thừa, có lúc còn làm dispatch THẤT BẠI hẳn giữa
    # đường (đã xảy ra thực tế: vòng dư qua 102→...→204→203→202→201→...→101 bị lệch
    # route giữa chừng → off_route re-dispatch từ node giữa route KHÔNG tìm được
    # đường tiến hợp lệ → toàn bộ hàng đợi phía sau — kể cả lệnh lấy hàng đầy tại
    # 202/201 — không bao giờ chạy tới).
    _seen_go_to: set[str] = set()
    _deduped_cmds = []
    for (c, d, s) in cmds:
        if c == CMD_GO_TO and d:
            if str(d) in _seen_go_to:
                print(f"[BATCH] {agv_id}: bỏ lệnh go_to({d}) trùng — đã có trong lượt này")
                continue
            _seen_go_to.add(str(d))
        _deduped_cmds.append((c, d, s))
    cmds = _deduped_cmds

    # Lấy current_node + load node_actions của map AGV
    na = {}
    current_node = None
    try:
        info = get_agv_runtime_info(agv_id)
        current_node = info.get("current_node")
        if not current_node:
            for (_c, _d, _s) in cmds:
                if _s:
                    current_node = str(_s)
                    break
        _rid = info.get("resolved_map_id") or info.get("raw_map")
        pool = getattr(app.state, "db_pool", None)
        if _rid and pool is not None:
            try:
                await map_manager.load_from_db(pool, str(_rid))
            except Exception as _le:
                print(f"[BATCH] {agv_id}: load_from_db lỗi ({_le}) — dùng node_actions hiện có")
        na = getattr(map_manager, "node_actions", {}) or {}
    except Exception as _e:
        print(f"[BATCH] {agv_id}: finalize chuẩn bị lỗi: {_e}")
        na = getattr(map_manager, "node_actions", {}) or {}

    # Xe rơ-moóc — CHIỀU ĐI (thả rỗng): CHỈ Tổ XA staging/trạm sạc NHẤT trong
    # số các Tổ được gọi mới thực sự dừng + hạ móc thả xe rỗng thật. Các Tổ
    # gần hơn nằm trên đường đi qua tới Tổ xa nhất đó chỉ DỪNG + CHỜ NGƯỜI DÙNG
    # xác nhận thủ công rồi đi tiếp — KHÔNG đụng móc (giống hệt cơ chế đã có ở
    # chiều VỀ lấy đầy, xem `_full_pickup_nodes`/`_pending_confirm_only_legs`
    # phía dưới). ĐỔI Ý so với quyết định trước đó (từng chốt "dừng thả thật ở
    # TẤT CẢ") theo yêu cầu mới nhất của người dùng — thứ tự chèn cụ thể ở khối
    # sắp xếp `_drop_order` ngay dưới `_agv_type_bt`/`_map_id_bt`.
    _all_drop_dests_pretrim: list[str] = [
        str(d) for (c, d, s) in cmds
        if c == CMD_GO_TO and d
        and str((na.get(str(d)) or {}).get('trailer_role', '') or '').lower() == 'drop'
    ]

    # Điểm cấp cần (union theo các tổ giao hàng), giữ thứ tự xuất hiện rồi sắp theo khoảng cách
    # _required_supply_node() chỉ nhận diện được cơ chế CARRY (field 'team' đơn
    # + supply_group/wait_sys) — xe rơ-moóc dùng field riêng (trailer_role/
    # trailer_drop_teams/trailer_empty_staging), nên với dest là node kiểu
    # trailer, hàm này luôn trả None → "required" rỗng, không bao giờ tự chèn
    # bước lấy hàng rỗng. Xử lý RIÊNG cho xe rơ-moóc ngay dưới đây.
    required: list[str] = []
    for (c, d, s) in cmds:
        if c == CMD_GO_TO and d:
            sup = _required_supply_node(na, d)
            if sup and sup not in required:
                required.append(str(sup))
    required = _sort_supplies_by_distance(required, current_node)

    # Xe rơ-moóc: nếu móc CHƯA đang hạ (= chưa có hàng rỗng gắn sẵn từ chặng
    # trước), phải LẤY RỖNG tại node cố định (trailer_empty_staging) TRƯỚC
    # MỌI lệnh GIAO trong lượt BATCH này — bất kể lượt này tới từ app/BATCH
    # (không qua API /api/execute/trailer-roundtrip) hay không. Nếu không có
    # bước này, BATCH đặt qua app sẽ bỏ thẳng qua node lấy hàng, đi giao luôn.
    #
    # CHỈ áp dụng khi lượt này THỰC SỰ có lệnh giao (CMD_GO_TO) — nếu lượt chỉ
    # có go_charge/go_wait (vd người dùng đang giữa đường bấm "Về trạm" để huỷ
    # dở chừng, không giao gì nữa) thì KHÔNG được bắt xe vòng qua lấy hàng rỗng
    # — xe không định giao gì nữa nên không cần mang thêm hàng rỗng, chỉ cần về
    # thẳng trạm sạc theo đúng ý người dùng.
    _has_delivery_leg = any(c == CMD_GO_TO for (c, d, s) in cmds)
    _trailer_pickup_node: str | None = None
    _agv_type_bt = ""
    _map_id_bt: str | None = None
    try:
        from agv_registry import agv_registry as _areg_bt
        _agv_type_bt = str(_areg_bt.get_config(agv_id).get('agv_type') or '').strip().lower()
        if _agv_type_bt == 'trailer' and _has_delivery_leg:
            _map_id_bt = info.get("resolved_map_id") or info.get("raw_map") if info else None
            from line_agv_handler import line_agv_handler as _lah_bt
            _lstate_bt = _lah_bt.state_store.get(agv_id)
            _hook_state_bt = getattr(_lstate_bt, 'hook_state', None) if _lstate_bt else None
            if _hook_state_bt != 'lowered' and _map_id_bt:
                _empty_node_bt = await _find_trailer_empty_staging_node(str(_map_id_bt))
                if _empty_node_bt and str(_empty_node_bt) != str(current_node):
                    _trailer_pickup_node = str(_empty_node_bt)
        elif _agv_type_bt == 'trailer' and not _has_delivery_leg:
            print(f"[BATCH] {agv_id}: lượt chỉ có go_charge/go_wait (không giao gì) "
                  f"— bỏ qua bước lấy hàng rỗng, về thẳng trạm")
    except Exception as _e_bt:
        print(f"[BATCH] {agv_id}: kiem tra lay hang rong (xe ro-moc) loi: {_e_bt}")

    # Sắp xếp lại thứ tự thả rỗng theo khoảng cách: node nào GẶP TRƯỚC trên
    # đường đi ra (tính từ vị trí hiện tại/vừa rời trạm) thì ghé TRƯỚC (chỉ
    # xác nhận thủ công), node XA NHẤT trên đường ra ghé CUỐI (thả thật).
    #
    # QUAN TRỌNG: KHÔNG dùng lại _order_pickups_for_forward_loop(nodes,
    # staging_node) rồi đảo ngược — từng thử và SAI thật (log AGV01 gọi Tổ ứng
    # node 108+107: hàm đó đo khoảng cách NGƯỢC VỀ staging_node, tức đo phần
    # ĐUÔI vòng (return leg). Vì đây là 1 VÒNG KÍN, node nào GẦN staging đo
    # theo hướng NGƯỢC VỀ lại chính là node đã đi được XA NHẤT quanh vòng (gần
    # hoàn thành vòng) — với cặp 108/107 kề nhau, 108 (đi qua 107 mới tới) lại
    # bị tính "gần staging hơn" 107 → đảo ngược cho ra ['108','107'], khiến xe
    # dispatch 108 TRƯỚC dù 107 mới là node gặp trước trên đường ra thật —
    # 107 nằm SAU 108 trên hướng đó nên phải vòng gần hết cả bản đồ mới quay
    # lại được (đúng lỗi log: '108 → 16 → 19 → 208 → ... → 106 → 107', 22 node).
    #
    # Cách ĐÚNG: lấy thẳng đường đi THẬT (danh sách node, không phải 1 con số
    # khoảng cách) từ vị trí hiện tại tới node xa nhất trong nhóm — dùng
    # _order_by_real_path(), tránh hẳn lớp lỗi do suy luận qua con số khoảng
    # cách (đã xảy ra thực tế với cặp 107/108).
    _staging_bt: str | None = None
    if _agv_type_bt == 'trailer' and len(_all_drop_dests_pretrim) > 1:
        _all_drop_dests_pretrim = _order_by_real_path(
            _all_drop_dests_pretrim, current_node)
        from line_agv_handler import _pending_confirm_only_legs as _pcol_drop
        for _dp_confirm in _all_drop_dests_pretrim[:-1]:
            _pcol_drop.add((agv_id, _dp_confirm))
        print(f"[BATCH] {agv_id}: thứ tự thả rỗng theo đường đi ra (gặp trước→gặp "
              f"sau, chỉ node CUỐI thả thật): {_all_drop_dests_pretrim}")

    # Xe rơ-moóc — LẤY HÀNG ĐẦY theo TỪNG TỔ: _required_supply_node() (dùng cho
    # carry ở trên) không nhận diện được field trailer_role/trailer_drop_teams
    # (xem comment ở khối `required` phía trên) nên bước "lấy đầy" cho xe rơ-moóc
    # bị bỏ sót hoàn toàn — xe đi ngang node lấy đầy (trailer_role='pickup') mà
    # không dừng, vì node đó chưa từng được enqueue thành 1 lệnh go_to riêng.
    # Tra CHỦ ĐỘNG bằng _resolve_team_node() (đúng field trailer_pickup_teams,
    # giống hệt cơ chế /api/execute/trailer-multi-pickup) cho từng Tổ xuất hiện
    # trong 'trailer_drop_teams' của các đích giao trong lượt này.
    #
    # THỨ TỰ: KHÔNG chèn pickup ngay sau drop của CHÍNH tổ đó (sẽ bắt xe rơ-moóc
    # đi 1 VÒNG LẶP RIÊNG cho mỗi tổ — CHỈ TIẾN nên phải vòng hết 1 lượt quanh sơ
    # đồ mới lấy được hàng của tổ vừa thả, rồi lại phải đi NGANG QUA đúng node thả
    # của tổ kế tiếp (không dừng) trước khi vòng lại — trùng lặp hoàn toàn quãng
    # đường vừa đi). ĐÚNG cách (khớp _order_pickups_for_forward_loop/milk-run đã
    # thống nhất trước đó): thả rỗng HẾT các tổ theo đúng thứ tự cmds (đường ra),
    # rồi mới LẤY ĐẦY hết các tổ theo thứ tự XA staging TRƯỚC — vì đường về tự
    # nhiên đi ngang các node lấy đầy theo đúng thứ tự ngược đó trong 1 VÒNG DUY
    # NHẤT, không cần quay lại đường cũ.
    _full_pickup_nodes: list[str] = []
    if _agv_type_bt == 'trailer' and _map_id_bt:
        _seen_full_pickup: set[str] = set()
        for d in _all_drop_dests_pretrim:
            _d_na = na.get(str(d)) or {}
            for _tm in (_d_na.get('trailer_drop_teams') or []):
                try:
                    _tm_int = int(_tm)
                except (TypeError, ValueError):
                    continue
                try:
                    _pk_node = await _resolve_team_node(str(_map_id_bt), _tm_int, 'trailer', want_pickup=True)
                except Exception as _e_pk:
                    print(f"[BATCH] {agv_id}: resolve lay day To {_tm_int} loi: {_e_pk}")
                    _pk_node = None
                if _pk_node and _pk_node not in _seen_full_pickup and _pk_node != str(d):
                    _seen_full_pickup.add(_pk_node)
                    _full_pickup_nodes.append(_pk_node)

        if _full_pickup_nodes:
            if not _staging_bt:
                _staging_bt = await _find_trailer_staging_node(str(_map_id_bt))
            _full_pickup_nodes = _order_pickups_for_forward_loop(_full_pickup_nodes, _staging_bt or "")

    # Trong các node lấy-đầy: CHỈ node XA staging NHẤT (ghé đầu tiên, sorted[0])
    # mới thực sự MÓC CƠ KHÍ (nâng → chờ xe hàng đầy thật → hạ → xác nhận web) —
    # khớp đúng cơ chế /api/execute/trailer-multi-pickup đã có. Các node SAU đó
    # (gần staging hơn) chỉ DỪNG + CHỜ NGƯỜI DÙNG xác nhận thủ công để đi tiếp —
    # KHÔNG nâng/hạ móc lại (hàng được chuyển tay từ xe Tổ đó sang xe đang kéo,
    # móc đã có xe hàng từ node đầu tiên rồi). Đánh dấu qua _pending_confirm_only_legs
    # (dùng chung với arrived_wait_sys/arrived_wait_user trong line_agv_handler.py).
    if len(_full_pickup_nodes) > 1:
        from line_agv_handler import _pending_confirm_only_legs as _pcol_bt
        for _pk_confirm in _full_pickup_nodes[1:]:
            _pcol_bt.add((agv_id, _pk_confirm))

    # Sau khi lấy đầy xong (nếu có) — xe đang mang xe hàng ĐẦY, phải GHÉ QUA
    # staging_node (trailer_staging='yes') để nhả xe hàng đầy TRƯỚC khi sạc.
    # Trước đây bước này hoàn toàn vắng mặt trong luồng batch (chỉ có ở
    # execute_trailer_roundtrip/trailer-multi-pickup) → xe đi thẳng từ điểm lấy
    # đầy cuối cùng tới go_charge, đi NGANG QUA staging (vd node 81) mà không
    # dừng — đúng lỗi thực tế: xe về ngang 81 không thả hàng đầy.
    _post_pickup_nodes: list[str] = list(_full_pickup_nodes)
    if _agv_type_bt == 'trailer' and _full_pickup_nodes:
        if not _staging_bt and _map_id_bt:
            _staging_bt = await _find_trailer_staging_node(str(_map_id_bt))
        if _staging_bt and _staging_bt not in _post_pickup_nodes:
            _post_pickup_nodes.append(_staging_bt)

    # Lệnh cuối: [lấy hàng rỗng xe rơ-moóc (nếu cần)] + [lấy hàng tại điểm cấp carry]
    # + [TẤT CẢ lệnh giao gốc, bỏ pickup tường minh trùng] + [TẤT CẢ lấy-đầy-theo-tổ
    # theo thứ tự xa staging trước + staging cuối cùng — chèn ngay TRƯỚC lệnh
    # go_charge cuối nếu có, nếu không thì cuối cùng]
    final: list = []
    if _trailer_pickup_node:
        from line_agv_handler import _pending_empty_pickup_legs as _pepl_bt
        # Đánh dấu TRƯỚC khi enqueue — arrival handler cần thấy dấu này ngay
        # khi xe tới (cùng pattern với execute_trailer_roundtrip / _dispatch_go_to).
        _pepl_bt.add((agv_id, _trailer_pickup_node))
        final.append((CMD_GO_TO, _trailer_pickup_node, None))
    final.extend((CMD_GO_TO, str(sup), None) for sup in required)

    _drop_set = set(_all_drop_dests_pretrim)
    _drop_inserted = False
    _charge_idx = next((i for i, (c, d, s) in enumerate(cmds) if c == CMD_GO_CHARGE), None)
    for _idx, (c, d, s) in enumerate(cmds):
        if c == CMD_GO_TO and d and str(d) in required:
            continue   # đã sinh lệnh lấy hàng ở trên
        if c == CMD_GO_TO and d and str(d) in _drop_set:
            # Chèn TẤT CẢ lệnh thả theo đúng thứ tự khoảng cách đã sắp ở trên
            # (gần→xa), 1 LẦN DUY NHẤT tại vị trí lệnh thả ĐẦU TIÊN gặp trong
            # cmds gốc — bỏ qua các lần gặp sau (đã nằm trong _drop_order rồi).
            if not _drop_inserted:
                final.extend((CMD_GO_TO, _dp, None) for _dp in _all_drop_dests_pretrim)
                _drop_inserted = True
            continue
        if _idx == _charge_idx and _post_pickup_nodes:
            final.extend((CMD_GO_TO, _pk, None) for _pk in _post_pickup_nodes)
        final.append((c, d, s))
    if _charge_idx is None and _post_pickup_nodes:
        final.extend((CMD_GO_TO, _pk, None) for _pk in _post_pickup_nodes)

    print(f"[BATCH] {agv_id}: lượt {session_id} → lấy hàng rỗng (xe rơ-moóc)="
          f"{_trailer_pickup_node!r}, lấy hàng {required} TRƯỚC, "
          f"rồi giao {[d for (c, d, s) in cmds if c == CMD_GO_TO and d and str(d) not in required]}"
          f"{f', sau đó lấy đầy: {_full_pickup_nodes[0]} (móc thật)' if _full_pickup_nodes else ''}"
          f"{f' → {_full_pickup_nodes[1:]} (chỉ dừng chờ xác nhận)' if len(_full_pickup_nodes) > 1 else ''}"
          f"{f' → staging {_staging_bt} (thả hàng đầy)' if (_staging_bt and _staging_bt in _post_pickup_nodes) else ''}")

    for (c, d, s) in final:
        try:
            await asyncio.to_thread(
                agv_task_queue.dispatch_or_queue,
                agv_id, c, d, s, session_id, session_label,
            )
        except Exception as _de:
            print(f"[BATCH] {agv_id}: enqueue lỗi cmd={c} dest={d}: {_de}")


async def _supply_batch_timer(key: tuple, delay: float) -> None:
    try:
        await asyncio.sleep(delay)
    except asyncio.CancelledError:
        return
    try:
        await _finalize_supply_batch(key)
    except Exception as _e:
        print(f"[BATCH] finalize lỗi: {_e}")


@app.post("/api/execute/dispatch")
async def execute_dispatch(req: ExecuteDispatchRequest):
    """
    Gửi lệnh cho AGV.
    - Nếu AGV rảnh  → dispatch ngay, trả về status=dispatched
    - Nếu AGV đang bận → xếp hàng chờ, trả về status=queued
    - Line AGV + session_id → gom lệnh ~1s rồi lập kế hoạch lấy hàng cả lượt
    """
    from task_queue import agv_task_queue, CMD_GO_TO
    from agv_registry import agv_registry
    from line_agv_handler import line_agv_handler
    from mqtt_client import get_agv_runtime_info

    agv_id  = req.agv_id.strip()
    command = req.command.strip()

    # Validate AGV tồn tại
    if agv_id not in agv_registry.all_ids():
        raise HTTPException(status_code=404, detail=f"AGV '{agv_id}' không tìm thấy")

    # Validate dest_node khi go_to
    if command == CMD_GO_TO and not req.dest_node:
        raise HTTPException(status_code=400, detail="dest_node bắt buộc khi command=go_to")

    # Kiểm tra battery_blocking (chặn lệnh không phải go_charge)
    info = get_agv_runtime_info(agv_id)
    if info["agv_state"].get("battery_blocking") and command != "go_charge":
        raise HTTPException(
            status_code=409,
            detail=f"AGV {agv_id} đang bị khóa do pin yếu — chỉ cho phép lệnh 'go_charge'",
        )

    # ── Gom lệnh cả lượt cấp hàng (Line AGV + session_id) ─────────────────────
    # Chờ ~1s thu thập đủ các lệnh cùng session rồi sinh lệnh lấy hàng tại TẤT CẢ
    # điểm cấp TRƯỚC, mới giao. Tránh xe chạy khi chưa biết đủ lượt → đi tới-lui.
    # Chỉ gom go_to/go_charge/go_wait; stop/resume vẫn xử lý tức thì.
    if (agv_registry.is_line(agv_id) and req.session_id
            and command in (CMD_GO_TO, "go_charge", "go_wait")):
        key = (agv_id, req.session_id)
        batch = _supply_batch.setdefault(
            key, {"commands": [], "task": None, "session_label": req.session_label})
        batch["commands"].append((command, req.dest_node, req.start_node))
        _old_task = batch.get("task")
        if _old_task:
            _old_task.cancel()
        batch["task"] = asyncio.create_task(_supply_batch_timer(key, _SUPPLY_BATCH_DELAY_SEC))
        return {
            "agv_id":     agv_id,
            "command":    command,
            "dest_node":  req.dest_node,
            "status":     "collecting",
            "queue_size": agv_task_queue.queue_size(agv_id),
            "message":    f"Đang gom lệnh cấp hàng cho {agv_id}…",
        }

    # Chạy trong thread pool để tránh deadlock:
    # dispatch_or_queue → _dispatch_go_to → plan_path_for_order dùng
    # asyncio.run_coroutine_threadsafe(...).result() — phải gọi từ ngoài event loop thread
    cmd, dispatched = await asyncio.to_thread(
        agv_task_queue.dispatch_or_queue,
        agv_id,
        command,
        req.dest_node,
        req.start_node,
        req.session_id,
        req.session_label,
    )

    from task_queue import STATUS_FAILED, STATUS_QUEUED
    if not dispatched and cmd.status == STATUS_FAILED:
        raise HTTPException(
            status_code=422,
            detail=cmd.notes or "Dispatch thất bại — kiểm tra log server",
        )

    return {
        "cmd_id":     cmd.cmd_id,
        "agv_id":     agv_id,
        "command":    command,
        "dest_node":  req.dest_node,
        "start_node": req.start_node,
        "status":     "dispatched" if dispatched else "queued",
        "queue_size": agv_task_queue.queue_size(agv_id),
        "message":    (
            f"Lệnh đã được gửi đến {agv_id}"
            if dispatched else
            f"AGV {agv_id} đang bận — lệnh đã xếp vào hàng chờ (vị trí #{agv_task_queue.queue_size(agv_id)})"
        ),
    }


def _sync_manual_lidar(agv_id: str, force_on: bool = False) -> None:
    """
    Đồng bộ Lidar khi lái THỦ CÔNG (D-pad / Chạy thử đến node) — lệnh 'deba'
    là instant action gửi thẳng xuống firmware, KHÔNG đi qua plan builder nên
    KHÔNG tự áp dụng cấu hình "Tắt Lidar" trên node như lúc chạy theo Plan.
    Gọi hàm này TRƯỚC mỗi lần gửi 'deba' để tự bật/tắt Lidar theo đúng cấu
    hình của node xe đang đứng — chỉ gửi lại khi trạng thái THAY ĐỔI (tránh
    spam lệnh mỗi 400-500ms). force_on=True để ép bật lại (lúc dừng/hoàn tất).
    """
    from line_agv_handler import line_agv_handler
    from mqtt_client import map_manager, send_line_command
    from line_agv_plan_builder import ACTION_LIDAR_OFF, ACTION_LIDAR_ON

    state = line_agv_handler.state_store.get(agv_id)
    if not state:
        return

    want_off = False
    if not force_on and state.current_tag is not None:
        node_actions = getattr(map_manager, "node_actions", {}) or {}
        cfg = node_actions.get(str(state.current_tag)) or {}
        want_off = str(cfg.get("lidar_off", "no")).lower() == "yes"

    if state.manual_lidar_off == want_off:
        return   # đã đúng trạng thái rồi, không gửi lại
    send_line_command(agv_id, "action", a=(ACTION_LIDAR_OFF if want_off else ACTION_LIDAR_ON), v=0)
    state.manual_lidar_off = want_off


@app.post("/api/execute/manual-control")
async def manual_control(request: Request):
    """Điều khiển thủ công Line AGV qua bàn phím."""
    from agv_registry import agv_registry
    from mqtt_client import send_line_command
    body = await request.json()
    agv_id  = str(body.get("agv_id", "")).strip()
    action  = str(body.get("action", "")).strip()   # up | down | left | right | stop

    if not agv_id:
        raise HTTPException(400, "agv_id required")
    if not agv_registry.is_line(agv_id):
        raise HTTPException(400, "Chỉ hỗ trợ Line AGV")

    spd = int(body.get("speed", 150))
    if action == "up":
        _sync_manual_lidar(agv_id)
        ok = send_line_command(agv_id, "deba", spd=spd, dir="toi")
    elif action == "down":
        _sync_manual_lidar(agv_id)
        ok = send_line_command(agv_id, "deba", spd=spd, dir="lui")
    elif action == "right":
        ok = send_line_command(agv_id, "action", a=5, v=0)
    elif action == "left":
        ok = send_line_command(agv_id, "action", a=6, v=0)
    elif action == "stop":
        _sync_manual_lidar(agv_id, force_on=True)
        ok = send_line_command(agv_id, "stop")
    else:
        raise HTTPException(400, f"action không hợp lệ: {action}")

    return {"ok": ok, "agv_id": agv_id, "action": action}


async def _test_drive_keepalive_loop(agv_id: str, seq: int, spd: int) -> None:
    """
    "deba" chỉ khiến AGV chạy tới thẻ KẾ TIẾP rồi tự dừng (driving=False) —
    không phải lệnh chạy liên tục vô hạn (giống hệt lý do nút ↑ trên D-pad
    phải gửi lặp lại mỗi 500ms khi giữ nút). Vòng lặp này gửi lại "deba" đều
    đặn để duy trì chuyển động cho tới khi tới đúng tag mục tiêu (test_drive_target
    bị xoá) hoặc bị huỷ/thay thế bởi lượt chạy thử khác (test_drive_seq đổi).
    """
    # KHÔNG giới hạn thời gian — cố ý: dùng để chạy thử liên tục dài hạn, phát
    # hiện lỗi cơ khí/chương trình phát sinh khi chạy lâu. Chỉ dừng khi tới đúng
    # tag mục tiêu, hoặc bị huỷ thủ công (test-drive-cancel), hoặc AGV mất kết nối.
    from mqtt_client import send_line_command
    from line_agv_handler import line_agv_handler
    while True:
        await asyncio.sleep(0.4)
        state = line_agv_handler.state_store.get(agv_id)
        if not state or state.test_drive_seq != seq or not state.test_drive_target:
            return
        _sync_manual_lidar(agv_id)
        send_line_command(agv_id, "deba", spd=spd, dir="toi")


@app.post("/api/execute/test-drive-to-node")
async def test_drive_to_node(request: Request):
    """
    Chạy thử thủ công: AGV chỉ cần ONLINE (không cần map/route đã cấu hình đúng).
    Cho xe chạy tiến liên tục, tự dừng khi đọc được đúng tag mục tiêu (so trực
    tiếp qua RFID, không qua pathfinding/node_actions).
    """
    from agv_registry import agv_registry
    from mqtt_client import send_line_command
    from line_agv_handler import line_agv_handler
    body = await request.json()
    agv_id      = str(body.get("agv_id", "")).strip()
    target_node = str(body.get("target_node", "")).strip()
    spd         = int(body.get("speed", 150))

    if not agv_id:
        raise HTTPException(400, "agv_id required")
    if not target_node:
        raise HTTPException(400, "target_node required")
    if not agv_registry.is_line(agv_id):
        raise HTTPException(400, "Chỉ hỗ trợ Line AGV")

    state = line_agv_handler.state_store.get_or_create(agv_id)
    if state.connection_state != "ONLINE":
        raise HTTPException(400, f"AGV {agv_id} chưa ONLINE")

    state.test_drive_seq += 1
    my_seq = state.test_drive_seq
    state.test_drive_target = target_node
    _sync_manual_lidar(agv_id)
    ok = send_line_command(agv_id, "deba", spd=spd, dir="toi")
    asyncio.create_task(_test_drive_keepalive_loop(agv_id, my_seq, spd))
    print(f"[TEST-DRIVE] {agv_id}: chạy tiến tới tag {target_node} (speed={spd})")
    return {"ok": ok, "agv_id": agv_id, "target_node": target_node}


@app.post("/api/execute/test-drive-cancel/{agv_id}")
async def test_drive_cancel(agv_id: str):
    """Huỷ chạy thử — dừng xe và xoá tag mục tiêu đang chờ."""
    from mqtt_client import send_line_command
    from line_agv_handler import line_agv_handler
    agv_id = agv_id.strip()
    state = line_agv_handler.state_store.get(agv_id)
    if state:
        state.test_drive_target = None
        state.test_drive_seq += 1
    _sync_manual_lidar(agv_id, force_on=True)
    ok = send_line_command(agv_id, "stop")
    return {"ok": ok, "agv_id": agv_id}


@app.post("/api/execute/line-action")
async def line_action(request: Request):
    """
    Gửi action code tức thì cho Line AGV qua instantActions.
    Dùng cho: âm thanh (22-27), đèn (32-34), móc hàng (30-31), phanh (28-29).
    Payload: {"c":"action","a":ACTION_CODE,"v":VALUE}
    """
    from agv_registry import agv_registry
    from mqtt_client import send_line_command
    body = await request.json()
    agv_id      = str(body.get("agv_id", "")).strip()
    action_code = int(body.get("action_code", 0))
    value       = int(body.get("value", 0))

    if not agv_id:
        raise HTTPException(400, "agv_id required")
    if not agv_registry.is_line(agv_id):
        raise HTTPException(400, "Chỉ hỗ trợ Line AGV")
    if action_code <= 0:
        raise HTTPException(400, "action_code không hợp lệ")

    ok = send_line_command(agv_id, "action", a=action_code, v=value)
    return {"ok": ok, "agv_id": agv_id, "action_code": action_code, "value": value}


class GateCommandRequest(BaseModel):
    door_num: str    # số thứ tự cửa (vd "1") — server tự ghép thành "gate1"
    cmd:      str    # "open" | "close"


@app.post("/api/execute/gate-command")
async def execute_gate_command(req: GateCommandRequest):
    """
    Mở/đóng THỦ CÔNG 1 cửa tự động — dùng cho Điều khiển thủ công (Quản lý AGV).
    Gửi THẲNG lệnh MQTT tới bộ điều khiển cửa (giống sendLineAction cho móc/đèn/
    nhạc), KHÔNG đi qua door_coordinator (không gắn với AGV/xe nào đang chờ) —
    xem PROTOCOL_GUIDE.md mục "Cửa tự động (Gate Controller)".
    """
    cmd = req.cmd.strip().lower()
    if cmd not in ("open", "close"):
        raise HTTPException(400, "cmd phải là 'open' hoặc 'close'")
    door_num = req.door_num.strip()
    if not door_num.isdigit() or int(door_num) <= 0:
        raise HTTPException(400, "Số thứ tự cửa phải là số nguyên dương")

    from mqtt_client import send_gate_command
    door_id = f"gate{door_num}"
    ok = send_gate_command(door_id, cmd)
    return {"success": ok, "door_id": door_id, "cmd": cmd}


@app.post("/api/execute/request-position/{agv_id}")
async def request_agv_position(agv_id: str):
    """Gửi lệnh yêu cầu AGV Line báo vị trí hiện tại (ping firmware)."""
    from agv_registry import agv_registry
    from mqtt_client import send_line_command
    agv_id = agv_id.strip()
    if not agv_registry.is_line(agv_id):
        raise HTTPException(400, "Chỉ hỗ trợ Line AGV")
    # Gửi instant action "report" — firmware phản hồi bằng 1 state message
    ok = send_line_command(agv_id, "report")
    return {"sent": ok, "agv_id": agv_id,
            "note": "AGV sẽ publish state trong vài giây nếu firmware hỗ trợ lệnh 'report'"}


@app.get("/api/execute/queue-status/{agv_id}")
async def queue_status(agv_id: str):
    """Trạng thái hàng chờ: lệnh đang chạy + danh sách chờ."""
    from task_queue import agv_task_queue
    return agv_task_queue.status_summary(agv_id.strip())


def _cancel_pending_locate_then_charge(agv_id: str) -> None:
    """
    Huỷ vòng dò-vị-trí-bằng-deba đang chờ (nếu có) — nếu không, vòng lặp không biết
    lệnh Về trạm vừa bị huỷ, vẫn tiếp tục chờ quẹt thẻ rồi tự nối lệnh Về trạm thật
    sau khi người dùng đã bấm hủy. Đồng thời gửi "stop" phòng khi xe đang chạy dở
    "deba" giữa chừng (agv_task_queue.cancel_running/cancel_all không tự gửi lệnh
    dừng thật xuống xe, chỉ dọn bookkeeping phía server).
    """
    from line_agv_handler import line_agv_handler
    from agv_registry import agv_registry
    state = line_agv_handler.state_store.get(agv_id)
    if state:
        state.locate_then_charge_seq += 1
    if agv_registry.is_line(agv_id):
        from mqtt_client import send_line_command
        send_line_command(agv_id, "stop")


@app.delete("/api/execute/cancel-running/{agv_id}")
async def cancel_running_cmd(agv_id: str):
    """Force-cancel lệnh đang stuck, giải phóng AGV."""
    from task_queue import agv_task_queue
    from line_agv_handler import line_agv_handler, traffic_coordinator as _tc
    agv_id = agv_id.strip()
    _tc.deregister(agv_id)
    line_agv_handler.clear_route(agv_id)
    _cancel_pending_locate_then_charge(agv_id)
    result = agv_task_queue.cancel_running(agv_id)
    if result is None:
        return {"cancelled": False, "message": f"Không có lệnh đang chạy cho {agv_id}"}
    return {"cancelled": True, "cmd": result}


@app.delete("/api/execute/cancel-queue/{agv_id}")
async def cancel_queue_cmds(agv_id: str):
    """Hủy toàn bộ lệnh đang chờ (chưa chạy) của AGV."""
    from task_queue import agv_task_queue
    n = agv_task_queue.cancel_queue(agv_id.strip())
    return {"cancelled_count": n, "agv_id": agv_id}


@app.delete("/api/execute/cancel-all/{agv_id}")
async def cancel_all_cmds(agv_id: str):
    """Hủy lệnh đang chạy + toàn bộ hàng chờ (dùng khi AGV bị stuck)."""
    from task_queue import agv_task_queue
    from line_agv_handler import line_agv_handler, traffic_coordinator as _tc
    agv_id = agv_id.strip()
    _tc.deregister(agv_id)
    line_agv_handler.clear_route(agv_id)
    _cancel_pending_locate_then_charge(agv_id)
    result = agv_task_queue.cancel_all(agv_id)
    return {"agv_id": agv_id, **result}


@app.delete("/api/execute/cancel-cmd/{cmd_id}")
async def cancel_single_cmd(cmd_id: str):
    """Hủy 1 lệnh cụ thể trong hàng chờ theo cmd_id."""
    from task_queue import agv_task_queue
    ok = agv_task_queue.cancel_cmd(cmd_id.strip())
    if not ok:
        raise HTTPException(404, f"Không tìm thấy lệnh {cmd_id} trong hàng chờ")
    return {"cancelled": True, "cmd_id": cmd_id}


@app.post("/api/execute/enter-config-mode/{agv_id}")
async def enter_config_mode(agv_id: str, factory: str | None = None):
    """
    Yêu cầu Line AGV (ESP32-C5) vào AP Config Mode.

    Gửi {"c":"config"} tới uagv/v2/{FACTORY}/{AGV_ID}/instantActions.
    Tham số `factory` cho phép chỉ định factory name khác (dùng khi AGV bị config nhầm factory).

    ESP tự xử lý: lưu cờ NVS → restart → phát SoftAP "configAGV" (mở).
    """
    from mqtt_client import send_line_command, _line_agv_topic, client as _mqtt_client
    from agv_registry import agv_registry
    from task_queue import agv_task_queue
    import json as _json

    agv_id = agv_id.strip()

    # Hủy hàng chờ trước để tránh auto-dispatch sau khi AGV reconnect
    agv_task_queue.cancel_all(agv_id)

    if factory:
        # Dùng factory tùy chỉnh — publish thẳng đến topic chỉ định
        # (bypass agv_registry để có thể rescue AGV bị nhầm factory)
        _factory   = factory.strip()
        _line_ver  = __import__("os").getenv("LINE_AGV_MQTT_VERSION", "v2")
        _iface     = __import__("os").getenv("UAGV_INTERFACE_NAME", "uagv")
        _topic     = f"{_iface}/{_line_ver}/{_factory}/{agv_id}/instantActions"
        _payload   = _json.dumps({"c": "config"})
        result     = _mqtt_client.publish(_topic, _payload, qos=1)
        ok         = result.rc == 0
        print(f"[CONFIG] {agv_id}: config → {_topic} | rc={result.rc}")
    else:
        # Dùng factory từ registry (bình thường)
        ok = await asyncio.to_thread(send_line_command, agv_id, "config")

    if not ok:
        raise HTTPException(503, f"Không thể gửi lệnh đến {agv_id} — kiểm tra kết nối MQTT")

    return {
        "success": True,
        "agv_id":  agv_id,
        "factory": factory or "registry",
        "message": f"{agv_id} đang vào AP Config Mode. Kết nối WiFi 'configAGV' → http://192.168.4.1",
    }


@app.post("/api/execute/lifecycle-ack/{agv_id}")
async def lifecycle_ack(agv_id: str):
    """
    Xác nhận lifecycle event (lấy hàng / giao hàng) cho Line AGV.
    Gọi khi người dùng nhấn "Đã lấy hàng" hoặc "Đã giao hàng xong" trên frontend.
    → Xóa task_lifecycle + gọi on_agv_completed để dispatch lệnh tiếp theo trong queue.
    """
    from line_agv_handler import line_agv_handler
    from task_queue import agv_task_queue
    agv_id = agv_id.strip()
    state = line_agv_handler.state_store.get(agv_id)
    if not state:
        raise HTTPException(404, f"AGV '{agv_id}' không có trạng thái")
    if not state.task_lifecycle:
        raise HTTPException(400, "AGV không ở trạng thái lifecycle (picking/delivering)")
    lc = state.task_lifecycle
    state.task_lifecycle = None
    # Xóa route để animated arrow dừng ngay
    line_agv_handler.clear_route(agv_id)
    agv_task_queue.on_agv_completed(agv_id, notes=f"lifecycle:{lc}:confirmed")
    print(f"[LIFECYCLE] {agv_id}: confirmed '{lc}' via UI")
    return {"success": True, "agv_id": agv_id, "confirmed": lc}


@app.get("/api/execute/history")
async def execute_history(agv_id: str | None = None, limit: int = 50):
    """Lịch sử lệnh đã thực hiện từ DB."""
    from task_queue import agv_task_queue
    return {"history": agv_task_queue.get_history(agv_id, limit)}


@app.get("/api/journal/history")
async def journal_history(
    agv_id: str | None = None,
    status: str | None = None,
    limit: int = 200,
):
    """Lịch sử lệnh cho trang Nhật ký — hỗ trợ filter theo AGV và trạng thái."""
    from task_queue import agv_task_queue
    rows = agv_task_queue.get_history(agv_id, limit)
    if status:
        rows = [r for r in rows if r.get("status") == status]
    return {"history": rows, "total": len(rows)}


class AgvMapAssignRequest(BaseModel):
    agv_id: str
    map_id: str | None = None   # None = xóa gán bản đồ


@app.post("/api/agv/assign-map")
async def assign_agv_map(req: AgvMapAssignRequest):
    """Gán hoặc xóa bản đồ cho AGV trong agv_devices."""
    import psycopg2, os as _os
    _DB = _os.getenv("DATABASE_URL", "postgresql://postgres:ducmanh1801@localhost:5432/TOT_AGV")

    def _run():
        conn = psycopg2.connect(_DB)
        conn.autocommit = True
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE agv_devices SET map_id = %s WHERE name = %s",
                    (req.map_id or None, req.agv_id.strip()),
                )
                if cur.rowcount == 0:
                    raise ValueError(f"AGV '{req.agv_id}' không tìm thấy")
                # Lấy tên bản đồ để trả về
                map_name = None
                if req.map_id:
                    cur.execute("SELECT name FROM agv_maps WHERE CAST(id AS TEXT) = %s", (str(req.map_id),))
                    row = cur.fetchone()
                    map_name = row[0] if row else req.map_id
            return map_name
        finally:
            conn.close()

    try:
        map_name = await asyncio.to_thread(_run)
        # Reload registry để AGV nhận map mới ngay
        try:
            from agv_registry import agv_registry as _reg
            _reg.load_from_db()
        except Exception:
            pass
        return {"success": True, "agv_id": req.agv_id, "map_id": req.map_id, "map_name": map_name}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class AgvIdentityRequest(BaseModel):
    old_agv_id: str
    new_agv_id: str
    factory:    str = "TOT"


@app.post("/api/agv/update-identity")
async def update_agv_identity(req: AgvIdentityRequest):
    """
    Cập nhật Tên AGV và Factory trong agv_devices.
    Nếu tên thay đổi → đổi primary key (rename = DELETE + INSERT trong transaction).
    """
    import psycopg2, os as _os
    _DB = _os.getenv("DATABASE_URL", "postgresql://postgres:ducmanh1801@localhost:5432/TOT_AGV")

    old_id = req.old_agv_id.strip()
    new_id = req.new_agv_id.strip()
    factory = req.factory.strip() or "TOT"

    def _run():
        conn = psycopg2.connect(_DB)
        try:
            with conn.cursor() as cur:
                if old_id == new_id:
                    # Chỉ update factory
                    cur.execute("UPDATE agv_devices SET factory = %s WHERE name = %s", (factory, old_id))
                    if cur.rowcount == 0:
                        raise ValueError(f"AGV '{old_id}' không tìm thấy")
                    conn.commit()
                    return False  # không rename
                else:
                    # Đổi tên: copy row với tên mới rồi xóa tên cũ (trong transaction)
                    cur.execute("""
                        INSERT INTO agv_devices (name, agv_type, ip, port, map_id, factory, last_seen, subnet, gateway, dns)
                        SELECT %s, agv_type, ip, port, map_id, %s, last_seen, subnet, gateway, dns
                        FROM agv_devices WHERE name = %s
                        ON CONFLICT (name) DO NOTHING
                    """, (new_id, factory, old_id))
                    if cur.rowcount == 0:
                        raise ValueError(f"AGV '{old_id}' không tìm thấy hoặc tên '{new_id}' đã tồn tại")
                    cur.execute("DELETE FROM agv_devices WHERE name = %s", (old_id,))
                    conn.commit()
                    return True  # đã rename
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    try:
        renamed = await asyncio.to_thread(_run)
        # Reload registry
        try:
            from agv_registry import agv_registry as _reg
            _reg.load_from_db()
        except Exception:
            pass
        return {"success": True, "renamed": renamed, "agv_id": new_id, "factory": factory}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class AgvCapabilityRequest(BaseModel):
    agv_id:      str
    can_reverse: bool


@app.post("/api/agv/update-capability")
async def update_agv_capability(req: AgvCapabilityRequest):
    """Cập nhật cờ can_reverse cho AGV đã tồn tại (xe đầu kéo/rơ-moóc chỉ đi
    1 chiều tiến → can_reverse=False). Dùng cho AGV thêm TRƯỚC khi có công tắc
    này trong panel 'Thêm AGV', hoặc muốn đổi lại sau này."""
    import psycopg2, os as _os
    _DB = _os.getenv("DATABASE_URL", "postgresql://postgres:ducmanh1801@localhost:5432/TOT_AGV")
    agv_id = req.agv_id.strip()

    def _run():
        conn = psycopg2.connect(_DB)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE agv_devices SET can_reverse = %s WHERE name = %s",
                    (req.can_reverse, agv_id),
                )
                if cur.rowcount == 0:
                    raise ValueError(f"AGV '{agv_id}' không tìm thấy")
                conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    try:
        await asyncio.to_thread(_run)
        from agv_registry import agv_registry as _reg
        _reg.load_reverse_capability()
        return {"success": True, "agv_id": agv_id, "can_reverse": req.can_reverse}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class AgvNetworkInfoRequest(BaseModel):
    agv_id:  str
    ip:      str | None = None
    subnet:  str | None = None
    gateway: str | None = None
    dns:     str | None = None


@app.post("/api/agv/network-info")
async def save_agv_network_info(req: AgvNetworkInfoRequest):
    """Lưu thủ công thông tin mạng AGV (IP, subnet, gateway, DNS) vào agv_devices."""
    import psycopg2, os as _os
    _DB = _os.getenv("DATABASE_URL", "postgresql://postgres:ducmanh1801@localhost:5432/TOT_AGV")
    def _run():
        conn = psycopg2.connect(_DB)
        conn.autocommit = True
        try:
            with conn.cursor() as cur:
                fields, vals = [], []
                if req.ip:
                    fields.append("ip = %s::inet"); vals.append(req.ip)
                if req.subnet:
                    fields.append("subnet = %s");  vals.append(req.subnet)
                if req.gateway:
                    fields.append("gateway = %s"); vals.append(req.gateway)
                if req.dns:
                    fields.append("dns = %s");     vals.append(req.dns)
                if fields:
                    vals.append(req.agv_id)
                    cur.execute(
                        f"UPDATE agv_devices SET {', '.join(fields)} WHERE name = %s",
                        vals,
                    )
                    if cur.rowcount == 0:
                        raise ValueError(f"AGV '{req.agv_id}' không tìm thấy")
        finally:
            conn.close()
    try:
        await asyncio.to_thread(_run)
        return {"success": True, "agv_id": req.agv_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/journal/missions")
async def journal_missions(agv_id: str | None = None, limit: int = 200):
    """Lịch sử theo mission/workflow — mỗi lượt giao việc 1 dòng, gom tất cả điểm đến."""
    from task_queue import agv_task_queue
    return {"missions": agv_task_queue.get_mission_history(agv_id, limit)}


@app.get("/api/journal/logs")
async def journal_logs(limit: int = 500):
    """Trả về log server gần nhất (in-memory buffer)."""
    return {"logs": log_buffer.get_logs(limit)}


@app.get("/api/statistics/tasks")
async def statistics_tasks(
    period: str = "month",          # week | month | quarter | year | custom
    date_from: str | None = None,   # ISO date: 2026-05-01
    date_to:   str | None = None,   # ISO date: 2026-05-31
    agv_id:    str | None = None,
):
    """
    Thống kê nhiệm vụ theo khoảng thời gian.
    Trả về:
      - summary: tổng số, hoàn thành, thất bại, hủy, đang chạy
      - by_status: phân bổ theo trạng thái (cho pie chart)
      - by_day: số nhiệm vụ theo ngày (cho bar/line chart)
      - by_agv: số nhiệm vụ theo từng AGV
      - top_destinations: top 10 điểm đến
      - avg_duration_s: thời gian trung bình (giây) cho lệnh completed
    """
    import psycopg2, os
    from datetime import datetime, timedelta, date

    DB_URL = os.getenv("DATABASE_URL", "postgresql://postgres:ducmanh1801@localhost:5432/TOT_AGV")

    # ── Tính khoảng thời gian ──────────────────────────────────────────────────
    today = date.today()
    if period == "week":
        d_from = today - timedelta(days=today.weekday())   # thứ Hai đầu tuần
        d_to   = today
    elif period == "month":
        d_from = today.replace(day=1)
        d_to   = today
    elif period == "quarter":
        q_start_month = ((today.month - 1) // 3) * 3 + 1
        d_from = today.replace(month=q_start_month, day=1)
        d_to   = today
    elif period == "year":
        d_from = today.replace(month=1, day=1)
        d_to   = today
    elif period == "custom" and date_from and date_to:
        d_from = datetime.fromisoformat(date_from).date()
        d_to   = datetime.fromisoformat(date_to).date()
    else:
        d_from = today.replace(day=1)
        d_to   = today

    def _run():
        conn = psycopg2.connect(DB_URL)
        try:
            with conn.cursor() as cur:
                agv_clause = "AND agv_id = %s" if agv_id else ""
                base_params = [str(d_from), str(d_to)]
                if agv_id:
                    base_params.append(agv_id)

                # ── 1. Summary ─────────────────────────────────────────────────
                cur.execute(f"""
                    SELECT
                        COUNT(*) AS total,
                        SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) AS completed,
                        SUM(CASE WHEN status='failed'    THEN 1 ELSE 0 END) AS failed,
                        SUM(CASE WHEN status='cancelled' THEN 1 ELSE 0 END) AS cancelled,
                        SUM(CASE WHEN status='running'   THEN 1 ELSE 0 END) AS running,
                        SUM(CASE WHEN status='queued'    THEN 1 ELSE 0 END) AS queued,
                        ROUND(AVG(
                            CASE WHEN status='completed' AND started_at IS NOT NULL AND completed_at IS NOT NULL
                            THEN EXTRACT(EPOCH FROM (completed_at - started_at)) END
                        )::numeric, 1) AS avg_duration_s
                    FROM agv_task_executions
                    WHERE DATE(queued_at) BETWEEN %s AND %s {agv_clause}
                """, base_params)
                row = cur.fetchone()
                summary = {
                    "total": int(row[0] or 0),
                    "completed": int(row[1] or 0),
                    "failed":    int(row[2] or 0),
                    "cancelled": int(row[3] or 0),
                    "running":   int(row[4] or 0),
                    "queued":    int(row[5] or 0),
                    "avg_duration_s": float(row[6]) if row[6] else None,
                }

                # ── 2. By status (pie) ─────────────────────────────────────────
                cur.execute(f"""
                    SELECT status, COUNT(*) FROM agv_task_executions
                    WHERE DATE(queued_at) BETWEEN %s AND %s {agv_clause}
                    GROUP BY status ORDER BY COUNT(*) DESC
                """, base_params)
                by_status = [{"status": r[0], "count": int(r[1])} for r in cur.fetchall()]

                # ── 3. By day (bar chart) ──────────────────────────────────────
                cur.execute(f"""
                    SELECT
                        DATE(queued_at) AS day,
                        COUNT(*) AS total,
                        SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) AS completed,
                        SUM(CASE WHEN status='failed' OR status='cancelled' THEN 1 ELSE 0 END) AS failed
                    FROM agv_task_executions
                    WHERE DATE(queued_at) BETWEEN %s AND %s {agv_clause}
                    GROUP BY DATE(queued_at) ORDER BY day
                """, base_params)
                by_day = [
                    {"day": str(r[0]), "total": int(r[1]),
                     "completed": int(r[2]), "failed": int(r[3])}
                    for r in cur.fetchall()
                ]

                # ── 4. By AGV ──────────────────────────────────────────────────
                cur.execute(f"""
                    SELECT agv_id, COUNT(*) AS total,
                        SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) AS completed,
                        SUM(CASE WHEN status='failed' OR status='cancelled' THEN 1 ELSE 0 END) AS failed
                    FROM agv_task_executions
                    WHERE DATE(queued_at) BETWEEN %s AND %s {agv_clause}
                    GROUP BY agv_id ORDER BY total DESC
                """, base_params)
                by_agv = [
                    {"agv_id": r[0], "total": int(r[1]),
                     "completed": int(r[2]), "failed": int(r[3])}
                    for r in cur.fetchall()
                ]

                # ── 5. Top destinations ────────────────────────────────────────
                cur.execute(f"""
                    SELECT dest_node, COUNT(*) AS cnt
                    FROM agv_task_executions
                    WHERE DATE(queued_at) BETWEEN %s AND %s
                      AND dest_node IS NOT NULL AND dest_node <> '' {agv_clause}
                    GROUP BY dest_node ORDER BY cnt DESC LIMIT 10
                """, base_params)
                top_destinations = [{"node": r[0], "count": int(r[1])} for r in cur.fetchall()]

                return {
                    "period": period,
                    "date_from": str(d_from),
                    "date_to":   str(d_to),
                    "summary":   summary,
                    "by_status": by_status,
                    "by_day":    by_day,
                    "by_agv":    by_agv,
                    "top_destinations": top_destinations,
                }
        finally:
            conn.close()

    try:
        return await asyncio.to_thread(_run)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Statistics query error: {e}")


@app.get("/api/statistics/trips")
async def statistics_trips(
    period: str = "month",
    date_from: str | None = None,
    date_to:   str | None = None,
    agv_id:    str | None = None,
):
    """
    Thống kê chuyến đi (mission = nhóm session_id).
    Dữ liệu cùng nguồn với Lịch sử hoạt động AGV.

    Trả về:
      - summary : tổng chuyến, hoàn thành, thất bại, hủy, đang chạy
      - total_active_time_s : tổng thời gian xe đang thực sự di chuyển (giây)
      - avg_trip_duration_s  : thời gian trung bình 1 chuyến (giây)
      - avg_steps_per_trip   : số lệnh trung bình mỗi chuyến
      - by_day   : chuyến theo ngày
      - by_agv   : chuyến theo từng xe
      - by_status: phân bổ trạng thái chuyến
      - by_label : top 8 loại workflow
    """
    import psycopg2, os
    from datetime import datetime, timedelta, date

    DB_URL = os.getenv("DATABASE_URL", "postgresql://postgres:ducmanh1801@localhost:5432/TOT_AGV")

    today = date.today()
    if period == "week":
        d_from = today - timedelta(days=today.weekday())
        d_to   = today
    elif period == "month":
        d_from = today.replace(day=1)
        d_to   = today
    elif period == "quarter":
        q_start_month = ((today.month - 1) // 3) * 3 + 1
        d_from = today.replace(month=q_start_month, day=1)
        d_to   = today
    elif period == "year":
        d_from = today.replace(month=1, day=1)
        d_to   = today
    elif period == "custom" and date_from and date_to:
        d_from = datetime.fromisoformat(date_from).date()
        d_to   = datetime.fromisoformat(date_to).date()
    else:
        d_from = today.replace(day=1)
        d_to   = today

    def _run():
        conn = psycopg2.connect(DB_URL)
        try:
            with conn.cursor() as cur:

                agv_clause = "AND agv_id = %s" if agv_id else ""
                base_params = [str(d_from), str(d_to)] + ([agv_id] if agv_id else [])

                # ── Kiểm tra cột session_id ────────────────────────────────────
                cur.execute("""
                    SELECT EXISTS(
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='agv_task_executions' AND column_name='session_id'
                    )
                """)
                has_session = cur.fetchone()[0]
                null_filter = "AND session_id IS NOT NULL" if has_session else ""

                # ── CTE: gom theo session ──────────────────────────────────────
                # Với rows không có session_id → mỗi cmd là 1 chuyến (backward compat)
                trip_cte = f"""
                WITH trips AS (
                    -- Chuyến có session_id: gom lại
                    {"SELECT session_id AS trip_id, agv_id, session_label AS label," if has_session else "SELECT NULL AS trip_id, agv_id, command AS label,"}
                        MIN(queued_at)     AS trip_start,
                        MAX(completed_at)  AS trip_end,
                        COUNT(*)           AS step_count,
                        COALESCE(SUM(
                            CASE WHEN status='completed'
                                  AND started_at IS NOT NULL
                                  AND completed_at IS NOT NULL
                            THEN EXTRACT(EPOCH FROM (completed_at - started_at))
                            ELSE 0 END
                        ), 0)              AS active_s,
                        CASE
                            WHEN SUM(CASE WHEN status IN ('running','queued') THEN 1 ELSE 0 END) > 0 THEN 'running'
                            WHEN SUM(CASE WHEN status='failed'    THEN 1 ELSE 0 END) > 0 THEN 'failed'
                            WHEN SUM(CASE WHEN status='cancelled' THEN 1 ELSE 0 END) > 0 THEN 'cancelled'
                            WHEN SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) = COUNT(*) THEN 'completed'
                            ELSE 'running'
                        END AS status
                    FROM agv_task_executions
                    WHERE DATE(queued_at) BETWEEN %s AND %s
                      {null_filter} {agv_clause}
                    {"GROUP BY session_id, agv_id, session_label" if has_session else "GROUP BY cmd_id, agv_id, command"}
                )
                """

                # ── 1. Summary ──────────────────────────────────────────────────
                cur.execute(trip_cte + """
                    SELECT
                        COUNT(*)                                            AS total,
                        SUM(CASE WHEN status='completed'  THEN 1 ELSE 0 END) AS completed,
                        SUM(CASE WHEN status='failed'     THEN 1 ELSE 0 END) AS failed,
                        SUM(CASE WHEN status='cancelled'  THEN 1 ELSE 0 END) AS cancelled,
                        SUM(CASE WHEN status='running'    THEN 1 ELSE 0 END) AS running,
                        ROUND(SUM(active_s)::numeric, 0)                    AS total_active_s,
                        ROUND(AVG(
                            CASE WHEN status='completed'
                                  AND trip_end IS NOT NULL AND trip_start IS NOT NULL
                            THEN EXTRACT(EPOCH FROM (trip_end - trip_start)) END
                        )::numeric, 1)                                      AS avg_trip_s,
                        ROUND(AVG(step_count)::numeric, 1)                  AS avg_steps
                    FROM trips
                """, base_params)
                r = cur.fetchone()
                summary = {
                    "total":     int(r[0] or 0),
                    "completed": int(r[1] or 0),
                    "failed":    int(r[2] or 0),
                    "cancelled": int(r[3] or 0),
                    "running":   int(r[4] or 0),
                }
                total_active_s   = float(r[5]) if r[5] else 0.0
                avg_trip_s       = float(r[6]) if r[6] else None
                avg_steps        = float(r[7]) if r[7] else None

                # ── 2. By day ───────────────────────────────────────────────────
                cur.execute(trip_cte + """
                    SELECT
                        DATE(trip_start)  AS day,
                        COUNT(*)          AS total,
                        SUM(CASE WHEN status='completed'  THEN 1 ELSE 0 END) AS completed,
                        SUM(CASE WHEN status IN ('failed','cancelled') THEN 1 ELSE 0 END) AS failed,
                        ROUND(SUM(active_s)::numeric, 0) AS active_s
                    FROM trips
                    GROUP BY DATE(trip_start)
                    ORDER BY day
                """, base_params)
                by_day = [
                    {"day": str(r[0]), "total": int(r[1]),
                     "completed": int(r[2]), "failed": int(r[3]),
                     "active_s": float(r[4] or 0)}
                    for r in cur.fetchall()
                ]

                # ── 3. By AGV ───────────────────────────────────────────────────
                cur.execute(trip_cte + """
                    SELECT agv_id,
                        COUNT(*) AS total,
                        SUM(CASE WHEN status='completed'  THEN 1 ELSE 0 END) AS completed,
                        SUM(CASE WHEN status IN ('failed','cancelled') THEN 1 ELSE 0 END) AS failed,
                        ROUND(SUM(active_s)::numeric, 0) AS active_s,
                        ROUND(AVG(
                            CASE WHEN status='completed' AND trip_end IS NOT NULL AND trip_start IS NOT NULL
                            THEN EXTRACT(EPOCH FROM (trip_end - trip_start)) END
                        )::numeric, 1) AS avg_trip_s
                    FROM trips
                    GROUP BY agv_id ORDER BY total DESC
                """, base_params)
                by_agv = [
                    {"agv_id": r[0], "total": int(r[1]),
                     "completed": int(r[2]), "failed": int(r[3]),
                     "active_s": float(r[4] or 0),
                     "avg_trip_s": float(r[5]) if r[5] else None}
                    for r in cur.fetchall()
                ]

                # ── 4. By status ────────────────────────────────────────────────
                cur.execute(trip_cte + """
                    SELECT status, COUNT(*) AS cnt FROM trips
                    GROUP BY status ORDER BY cnt DESC
                """, base_params)
                by_status = [{"status": r[0], "count": int(r[1])} for r in cur.fetchall()]

                # ── 5. By workflow label (top 8) ────────────────────────────────
                cur.execute(trip_cte + """
                    SELECT label, COUNT(*) AS cnt FROM trips
                    WHERE label IS NOT NULL AND label <> ''
                    GROUP BY label ORDER BY cnt DESC LIMIT 8
                """, base_params)
                by_label = [{"label": r[0], "count": int(r[1])} for r in cur.fetchall()]

                return {
                    "period": period,
                    "date_from": str(d_from),
                    "date_to":   str(d_to),
                    "summary":   summary,
                    "total_active_time_s": total_active_s,
                    "avg_trip_duration_s": avg_trip_s,
                    "avg_steps_per_trip":  avg_steps,
                    "by_day":    by_day,
                    "by_agv":    by_agv,
                    "by_status": by_status,
                    "by_label":  by_label,
                }
        finally:
            conn.close()

    try:
        return await asyncio.to_thread(_run)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Trip statistics error: {e}")


@app.get("/statistics")
async def serve_statistics():
    """Trang Thống kê."""
    return FileResponse(WEB_UI_DIR / "statistics.html")


@app.get("/api/execute/queue-status")
async def execute_queue_status(agv_id: str):
    """Trạng thái hàng chờ real-time của 1 AGV."""
    from task_queue import agv_task_queue
    return agv_task_queue.status_summary(agv_id)


@app.delete("/api/execute/cancel-queue/{agv_id}")
async def execute_cancel_queue(agv_id: str):
    """Xóa toàn bộ hàng chờ của AGV (không hủy lệnh đang chạy)."""
    from task_queue import agv_task_queue
    count = agv_task_queue.cancel_queue(agv_id)
    return {"agv_id": agv_id, "cancelled": count}


# ══════════════════════════════════════════════════════════════════════════════
# MQTT MODE CONFIG
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/api/registry/reload")
async def api_reload_registry():
    """Reload agv_registry từ DB — gọi sau khi thêm/sửa AGV qua UI."""
    from agv_registry import agv_registry as _reg
    def _reload():
        _reg.load_from_db()
        _reg.load_reverse_capability()   # MỚI — nạp lại can_reverse cùng lúc
        return {"line": _reg.line_agv_ids(), "vda5050": _reg.vda5050_agv_ids()}
    result = await asyncio.to_thread(_reload)
    print(f"[REGISTRY] Reloaded via API: {result}")
    return {"ok": True, "registry": result}


@app.get("/api/config/mqtt-mode")
async def api_get_mqtt_mode():
    """Trả về mode MQTT đang dùng (local / cloud)."""
    return get_mqtt_mode()


class MqttModeRequest(BaseModel):
    mode: str   # "local" | "cloud"

@app.post("/api/config/mqtt-mode")
async def api_set_mqtt_mode(req: MqttModeRequest):
    """Đổi mode MQTT và kết nối lại ngay.
    mode='local'  → broker nội bộ (không TLS)
    mode='cloud'  → iot.tot360.com.vn:8883 (TLS, iot_user)
    """
    result = await asyncio.to_thread(switch_mqtt_mode, req.mode)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


# ════════════════════════════════════════════════════════════════════════════
# SCHEDULE — Lập lịch tự động cho AGV
# ════════════════════════════════════════════════════════════════════════════

class ScheduleCreateRequest(BaseModel):
    agv_id:           str
    command:          str                   # go_to | wf:<id> | ...
    map_id:           str | None  = None    # bản đồ để resolve tổ đích
    team_id:          int | None  = None    # số tổ đích
    priority:         int         = 3       # 1=khẩn cấp … 5=rất thấp
    schedule_type:    str         = "once"  # once | daily | interval
    scheduled_at:     str | None  = None    # ISO string (once)
    time_of_day:      str | None  = None    # HH:MM (daily)
    days_of_week:     list[int] | None = None  # [1..7] (daily)
    interval_minutes: int | None  = None    # (interval)
    label:            str         = ""


@app.get("/api/schedule/upcoming")
async def schedule_upcoming():
    """Danh sách lịch đang active, sắp xếp gần → xa."""
    from schedule_manager import get_scheduler
    sched = get_scheduler()
    if not sched:
        raise HTTPException(503, "Scheduler chưa sẵn sàng")
    return {"schedules": await sched.get_upcoming()}


@app.post("/api/schedule/create")
async def schedule_create(req: ScheduleCreateRequest):
    from schedule_manager import get_scheduler
    import datetime as _dt
    sched = get_scheduler()
    if not sched:
        raise HTTPException(503, "Scheduler chưa sẵn sàng")

    data = req.model_dump()
    # Parse scheduled_at string → datetime nếu có
    if data.get('scheduled_at'):
        try:
            sat = _dt.datetime.fromisoformat(data['scheduled_at'])
            if sat.tzinfo is None:
                sat = sat.replace(tzinfo=_dt.timezone(
                    _dt.timedelta(hours=7)))
            data['scheduled_at'] = sat
        except Exception:
            data['scheduled_at'] = None

    result = await sched.create(data)
    return result


@app.put("/api/schedule/{sid}/toggle")
async def schedule_toggle(sid: str):
    from schedule_manager import get_scheduler
    sched = get_scheduler()
    if not sched:
        raise HTTPException(503, "Scheduler chưa sẵn sàng")
    row = await sched.toggle(sid)
    if not row:
        raise HTTPException(404, "Không tìm thấy lịch")
    return row


@app.delete("/api/schedule/{sid}")
async def schedule_delete(sid: str):
    from schedule_manager import get_scheduler
    sched = get_scheduler()
    if not sched:
        raise HTTPException(503, "Scheduler chưa sẵn sàng")
    ok = await sched.delete(sid)
    if not ok:
        raise HTTPException(404, "Không tìm thấy lịch")
    return {"deleted": True, "id": sid}


@app.get("/api/schedule/teams")
async def schedule_teams():
    """Danh sách các tổ (team) từ DROPOFF nodes của map đang dùng."""
    if not pool:
        raise HTTPException(503, "DB chưa sẵn sàng")
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT DISTINCT (action->>'team')::integer AS team_id "
            "FROM agv_map_points "
            "WHERE type=3 AND action->>'team' IS NOT NULL "
            "ORDER BY 1"
        )
    return {"teams": [{"team_id": r['team_id'],
                       "label": f"Tổ {r['team_id']}"} for r in rows if r['team_id']]}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
