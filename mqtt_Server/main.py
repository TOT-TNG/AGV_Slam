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
    set_local_broker_config,
    get_factory_config,
    set_factory_config,
    test_broker_connection,
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
        if _lstate_chg and _is_post_chg_c:
            # Đọc xong xóa ngay (giống last_transit_direction) — không để 'charging'
            # nằm lại chặn mất cơ chế off_route của chặng tiếp theo. Xem giải thích
            # đầy đủ ở _dispatch_go_to.
            _lstate_chg.task_lifecycle = None
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


def _vda5050_dest_action(node_actions: dict, dest_node) -> tuple[str | None, dict]:
    """Suy ra action VDA5050 (PICKUP/DROP) cần gắn ở node đích, dựa trên field
    'defaultAction' (PICKUP/DROP/CHARGE/NONE) — đây là field DUY NHẤT
    MapConfigure hiển thị cho MỌI loại node (khác 'arrival_action' chỉ hiện cho
    node RFID/Line AGV). Trả về (action_type, action_dict); action_type=None
    nghĩa là node thường/CHARGE/NONE — không cần dừng chờ xác nhận."""
    cfg = (node_actions or {}).get(str(dest_node)) or {}
    default_action = str(cfg.get("defaultAction") or "").strip().upper()
    if default_action not in ("PICKUP", "DROP"):
        return None, {}
    action = {
        "actionType": default_action,
        "actionId": f"{default_action.lower()}_{dest_node}_{int(time.time())}",
        "blockingType": "HARD",
        "actionParameters": [],
    }
    return default_action, action


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
        if _lstate_trt and _is_post_chg_trt:
            # Đọc xong xóa ngay — xem giải thích đầy đủ ở _dispatch_go_to.
            _lstate_trt.task_lifecycle = None
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

    # Gắn action PICKUP/DROP ở node đích nếu MapConfigure có đặt defaultAction —
    # node đích là node CUỐI CÙNG của order nên tự nhiên xe dừng lại đó (VDA5050
    # hết node released là dừng); việc CÓ dừng chờ xác nhận người dùng hay không
    # do task_queue quyết định (xem agv_manager.pending_confirm_node), action ở
    # đây chỉ để order thể hiện đúng ý định, không phải cơ chế chặn chính.
    node_actions_vda = getattr(map_manager, "node_actions", {}) or {}
    dest_action_type, dest_action = _vda5050_dest_action(node_actions_vda, node_path[-1])
    actions_map = {external_path[-1]: [dest_action]} if dest_action_type else None

    order = build_order(
        agv_id=agv_id,
        path=external_path,
        coords=coords_lookup,
        manufacture=agv_state.get("manufacturer", "TNG:TOT"),
        SerialNumber=agv_state.get("serialNumber", agv_id),
        version="3.0.0",
        order_id=order_id,
        order_update_id=order_update_id,
        horizon=None,
        actions=actions_map,
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
# KHÔI PHỤC HÀNG ĐỢI SAU KHI SERVER KHỞI ĐỘNG LẠI
# ==========================
async def _restore_task_queue(pool, queue) -> None:
    """Dựng lại hàng đợi lệnh của các Line AGV từ DB (lệnh 'running'/'queued' còn sót, chưa quá cũ). Lệnh đang chạy dở
    nằm đầu hàng đợi; sau khi xe online, đứng yên và biết vị trí thì monitor_line_offline mới chạy lệnh đầu (từ VỊ TRÍ THẬT)."""
    try:
        _flag_store.set_pool(pool)      # từ đây mọi thay đổi cờ trạng thái được ghi xuyên DB
        from agv_registry import agv_registry as _reg_rq
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT cmd_id, agv_id, command, dest_node, status,
                       EXTRACT(EPOCH FROM queued_at) AS queued_at, session_id, session_label,
                       chain_leg, start_node, seq
                FROM agv_task_executions
                WHERE status IN ('running', 'queued')
                ORDER BY agv_id, (status = 'running') DESC, seq NULLS LAST, queued_at
            """)
            keep, drop = [], []
            for r in rows:
                (keep if _reg_rq.is_line(str(r["agv_id"])) else drop).append(dict(r))
            if drop:                      # AGV không phải Line (hoặc đã xoá khỏi registry): không có cơ chế khôi phục → coi là rác
                await conn.execute(
                    "UPDATE agv_task_executions SET status='error', completed_at=NOW(), "
                    "notes=COALESCE(NULLIF(notes,''),'') || ' [stale: AGV không còn trong registry]' "
                    "WHERE cmd_id = ANY($1::text[])", [d["cmd_id"] for d in drop])
        restored = queue.restore_from_rows(keep)
        await _restore_runtime_flags(pool, queue, restored, keep)
        if restored:
            print(f"[QUEUE] KHÔI PHỤC hàng đợi sau khi server khởi động lại: "
                  f"{', '.join(f'{a}={n} lệnh' for a, n in restored.items())} — chạy tiếp khi xe online & đứng yên")
    except Exception as e:
        print(f"[QUEUE] khôi phục hàng đợi lỗi (non-fatal): {type(e).__name__}: {e}")


async def _restore_runtime_flags(pool, queue, restored: dict, keep_rows: list) -> None:
    """Khôi phục các cờ trước đây chỉ nằm trong RAM (xem persistent_flags.py) cho các AGV có hàng đợi vừa khôi phục: cờ điểm lấy
    rỗng, cờ chỉ-xác-nhận, cờ staging-transit, theo dõi lấy hàng theo lượt, ngữ cảnh chuyến thang. Cờ của AGV/lượt đã hết lệnh
    hoặc quá cũ bị xoá (tránh cờ mồ côi làm xe dừng/đi sai ở lần sau)."""
    try:
        from persistent_flags import FlagStore
        import line_agv_handler as _lah_mod
        _flag_store.set_pool(pool)
        agvs = sorted(restored.keys())
        sessions = sorted({(str(r.get("session_id")) if r.get("session_id") else "__none__") for r in keep_rows
                           if str(r.get("agv_id")) in restored})
        _max_age_s = float(os.getenv("QUEUE_RESTORE_MAX_AGE_H", "12") or 12) * 3600.0
        async with pool.acquire() as conn:
            await FlagStore.purge(conn, {"empty_pickup": agvs, "confirm_only": agvs, "staging_transit": agvs,
                                         "ride_ctx": agvs, "session_pickup": sessions}, _max_age_s)
            rows = await FlagStore.load(conn, ("empty_pickup", "confirm_only", "staging_transit", "session_pickup", "ride_ctx"))
        by = {}
        for kind, grp, key in rows:
            by.setdefault(kind, []).append((grp, key))
        _lah_mod._pending_empty_pickup_legs.load(by.get("empty_pickup", []))
        _lah_mod._pending_confirm_only_legs.load(by.get("confirm_only", []))
        _pending_staging_transits.load(by.get("staging_transit", []))
        queue.restore_session_pickups(by.get("session_pickup", []))
        try:
            from elevator_coordinator import elevator_coordinator as _ec_rf
            _ld = getattr(_ec_rf, "load_persisted_ctx", None)
            if _ld is not None:
                _ld(by.get("ride_ctx", []))
        except Exception as _e_ec:
            print(f"[QUEUE] nạp ngữ cảnh chuyến thang lỗi: {_e_ec}")
        _n = {k: len(v) for k, v in by.items() if v}
        if _n:
            print(f"[QUEUE] khôi phục cờ trạng thái: {_n}")
    except Exception as e:
        print(f"[QUEUE] khôi phục cờ trạng thái lỗi (non-fatal): {type(e).__name__}: {e}")


def _restored_queue_ready(lah, agv_id: str) -> bool:
    """Xe có hàng đợi vừa khôi phục đã sẵn sàng nhận lệnh đầu chưa: online ổn định, đứng yên, biết vị trí thật,
    không có route/plan giữ, và không đang chờ người xác nhận (lấy/giao hàng, móc)."""
    from line_agv_handler import line_state_online
    st = lah.state_store.get(agv_id)
    if st is None or not line_state_online(st) or st.online_streak < GHOST_ONLINE_STREAK:
        return False
    if not st.real_state_seen:       # vị trí mới chỉ là last_tag khôi phục từ DB (xe có thể đang im lặng, vd trong cabin) — chờ state thật
        return False
    if st.ghost or st.driving or st.current_tag in (None, 0):
        return False
    if lah._routes.get(agv_id) is not None or st.task_lifecycle or st.hook_pending:
        return False
    try:
        from mqtt_client import _HELD_PLANS
        if agv_id in _HELD_PLANS:
            return False
    except Exception:
        pass
    return True


def _adopt_restored_in_cabin(lah, agv_id: str) -> None:
    """Hàng đợi vừa khôi phục có lệnh đầu là `elev_ride` và vị trí cuối biết được của xe là NODE CABIN: xe đang im lặng trong cabin
    (mất Wi-Fi khi cửa đóng) — KHÔNG chờ xe online mà nhận lại chuyến thang ngay để thang đưa xe tới tầng đích, giữ cửa và cho ra
    (lệnh `run` bị giữ tới khi xe online lại). Gọi trong luồng riêng; idempotent."""
    from task_queue import agv_task_queue as _q
    import floor_nav as _fn
    head = _q.peek_head(agv_id)
    st = lah.state_store.get(agv_id)
    if head is None or st is None or head.command != _fn.CMD_ELEV_RIDE or st.current_tag in (None, 0):
        return
    try:
        from mqtt_client import ensure_map_loaded_sync, get_agv_runtime_info
        _info = get_agv_runtime_info(agv_id) or {}
        _raw = _info.get("raw_map") or _info.get("resolved_map_id")
        if _raw:
            ensure_map_loaded_sync(str(_raw))
    except Exception as _e:
        print(f"[QUEUE] {agv_id}: nạp bản đồ để nhận lại chuyến thang lỗi: {_e}")
        return
    eid, fa, fb, wb = _fn.parse_ride(head.dest_node)
    cabins = {str(_fn.cabin_node(eid, fa) or ""), str(_fn.cabin_node(eid, fb) or "")} - {""}
    if str(st.current_tag) not in cabins:
        return
    from elevator_coordinator import elevator_coordinator as _ec
    _adopt, _has = getattr(_ec, "adopt_inside", None), getattr(_ec, "has_ctx", None)
    if _adopt is None or (_has is not None and _has(agv_id)):
        return
    _adopt(agv_id, eid, fa, fb, wb)


def _prepare_restored_head(lah, agv_id: str, user_initiated: bool = False) -> bool:
    """Chuẩn bị LỆNH ĐẦU của hàng đợi vừa khôi phục để chạy từ vị trí thật của xe. True = chạy được; False = giữ hàng đợi (đã
    báo người vận hành / đặt chờ xác nhận). `user_initiated`: người vận hành vừa xác nhận (web hoặc nút trên xe) — KHÔNG đặt lại
    "chờ xác nhận" nữa (họ vừa xác nhận rồi). Gọi cả khi xe tự sẵn sàng (_kick_restored_queue) lẫn khi người vận hành bấm xác nhận
    qua BẤT KỲ đường nào (qua AGVTaskQueue.on_agv_completed) — kết quả giống hệt nhau."""
    from task_queue import agv_task_queue as _q
    import floor_nav as _fn
    head = _q.peek_head(agv_id)
    st = lah.state_store.get(agv_id)
    if head is None or st is None or st.current_tag in (None, 0):
        return True
    tag = str(st.current_tag)
    # Server vừa khởi động lại: bản đồ CHƯA được nạp (chỉ nạp khi có yêu cầu lập đường đầu tiên) — nạp trước để cấu hình thang,
    # lập đường và tra cứu node đều dùng được ngay (nếu không, lệnh thang đầu tiên báo "chưa có cấu hình thang").
    try:
        from mqtt_client import ensure_map_loaded_sync, get_agv_runtime_info
        _info_k = get_agv_runtime_info(agv_id) or {}
        _raw_k = _info_k.get("raw_map") or _info_k.get("resolved_map_id")
        if _raw_k:
            ensure_map_loaded_sync(str(_raw_k))
    except Exception as _e_map:
        print(f"[QUEUE] {agv_id}: nạp bản đồ trước khi chạy tiếp hàng đợi lỗi: {_e_map}")
    # Lệnh đang đi thang dở: ride cũ đã mất theo RAM của server.
    if head.command == _fn.CMD_ELEV_RIDE:
        from elevator_coordinator import elevator_coordinator as _ec_k
        eid, fa, fb, _wb = _fn.parse_ride(head.dest_node)
        cabins = {str(_fn.cabin_node(eid, fa) or ""), str(_fn.cabin_node(eid, fb) or "")} - {""}
        _has_ctx = getattr(_ec_k, "has_ctx", None)
        if _has_ctx is not None and _has_ctx(agv_id):
            pass          # chuyến đã được NHẬN LẠI (xe trong cabin lúc server khởi động) hoặc còn sống → dispatch elev_ride bình thường
        elif tag in cabins:
            _adopt = getattr(_ec_k, "adopt_inside", None)
            if _adopt is not None and _adopt(agv_id, eid, fa, fb, _wb):
                print(f"[QUEUE] {agv_id}: đang trong cabin {tag} — đã NHẬN LẠI chuyến thang {fa}→{fb}")
            else:
                _q.pop_restored(agv_id)           # backend thang không hỗ trợ / thang đang bận xe khác: giữ hàng đợi, báo người vận hành
                msg = (f"Server khởi động lại khi {agv_id} đang ở trong cabin {tag}: hàng đợi lệnh được GIỮ NGUYÊN "
                       f"({_q.queue_size(agv_id)} lệnh) nhưng chưa nhận lại được chuyến thang — kiểm tra thang rồi huỷ/chạy tiếp lệnh")
                print(f"[QUEUE] {msg}")
                lah._set_alert(agv_id, st, "ELEVATOR_ERROR", msg)
                return False
        else:
            _q.insert_next(agv_id, _fn.CMD_ELEV_CALL, dest_node=f"{eid}@{fa}")   # gọi lại thang (đặt chuyến mới) trước khi vào cabin
    # Xe đã đứng sẵn ĐÚNG node đích của lệnh đầu và đích đó cần xác nhận người (lấy/giao hàng): server vừa khởi động lại
    # nên không còn trạng thái lifecycle — đặt lại để xe CHỜ xác nhận thay vì tự đi tiếp bỏ qua bước lấy/giao.
    if not user_initiated and head.command == "go_to" and head.dest_node and str(head.dest_node) == tag:
        try:
            from mqtt_client import map_manager as _mm_rq
            _arr = str(((getattr(_mm_rq, "node_actions", {}) or {}).get(tag) or {}).get("arrival_action") or "").lower()
        except Exception:
            _arr = ""
        if _arr in ("wait_sys", "wait_user"):
            _q.pop_restored(agv_id)
            st.task_lifecycle = "picking"
            print(f"[QUEUE] {agv_id}: server vừa khởi động lại, xe đang ở đích {tag} của lệnh dang dở — CHỜ XÁC NHẬN "
                  f"(web hoặc nút xác nhận/tiếp tục trên xe) rồi hàng đợi chạy tiếp")
            return False
    return True


def _kick_restored_queue(lah, agv_id: str) -> None:
    """Chạy lệnh đầu của hàng đợi đã khôi phục (gọi trong luồng riêng — dispatch chờ lại event loop)."""
    from task_queue import agv_task_queue as _q
    if _q.is_busy(agv_id):                       # đã có lệnh chạy (vd người vận hành xác nhận, hàng đợi tự chạy tiếp)
        _q.pop_restored(agv_id)
        return
    head = _q.peek_head(agv_id)
    if head is None:
        _q.pop_restored(agv_id)
        return
    if _prepare_restored_head(lah, agv_id) is False:
        return                                   # (hàm chuẩn bị đã bỏ AGV khỏi danh sách chờ khi cần giữ lại)
    _q.pop_restored(agv_id)
    st = lah.state_store.get(agv_id)
    print(f"[QUEUE] {agv_id}: xe sẵn sàng tại {st.current_tag} — chạy tiếp hàng đợi đã khôi phục "
          f"(lệnh đầu: {head.command} {head.dest_node or ''})")
    _q.on_agv_completed(agv_id, notes="restored_after_restart")


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
# LINE AGV OFFLINE MONITOR
# ==========================
# PHÁT HIỆN THỰC TẾ (2026-09-23): monitor_offline() ở trên CHỈ theo dõi
# agv_manager (VDA5050) — Line AGV (AGV01/03/04) không bao giờ vào agv_manager
# (mqtt_client.on_message() trả sớm cho Line AGV, xem comment ở đó). Cơ chế
# phát hiện mất kết nối DUY NHẤT cho Line AGV là _on_connection() trong
# line_agv_handler.py — HOÀN TOÀN THỤ ĐỘNG, chỉ fire khi có gói MQTT
# "connection" tường minh (LWT) gửi tới. Nếu xe "treo" (firmware đứng, không
# rớt mạng sạch) → không LWT nào được gửi → không có tín hiệu gì cả, mọi cơ
# chế cứu-kẹt trong line_agv_handler.py (resend plan, retry móc, obstacle-
# timeout...) đều CHỈ chạy khi có state message MỚI từ đúng xe đó tới — xe im
# lặng hoàn toàn thì KHÔNG cơ chế nào tự kích được nữa. Log thực tế: AGV04 gửi
# lệnh HẠ móc tại node 106, sau đó không còn 1 state message nào nữa — xe
# "biến mất" khỏi log hơn 3 phút mà không có bất kỳ cảnh báo nào.
# Watchdog này lấp đúng lỗ hổng: theo dõi last_update của TỪNG Line AGV, cảnh
# báo khi quá LINE_OFFLINE_THRESHOLD_SEC giây không có state message MỚI dù
# connection_state vẫn đang "ONLINE" (khác ca đã có LWT rõ ràng — ca đó đã có
# _on_connection xử lý).
LINE_OFFLINE_THRESHOLD_SEC = 20.0
LINE_OFFLINE_CHECK_INTERVAL_SEC = 5.0

GHOST_ONLINE_STREAK = 2   # số lượt kiểm tra online liên tiếp mới gỡ xe ma (chống wifi chập chờn)


def _ghost_nodes_of(lah, agv_id: str, st) -> list:
    """Vùng xe có thể đang chiếm khi mất tín hiệu: node cuối biết được → hết cửa sổ đã gửi."""
    from line_agv_handler import traffic_coordinator as tc
    cur = str(st.current_tag) if st.current_tag not in (None, 0) else None
    route = lah._routes.get(agv_id)
    nodes = [cur] if cur else []
    if route is not None and route.full_path:
        fp = [str(n) for n in route.full_path]
        reg = tc._registered.get(agv_id)
        i = reg['current_idx'] if reg else (fp.index(cur) if cur in fp else 0)
        nodes += [n for n in fp[i:route.window_end + 1] if n not in nodes]
    return nodes


def _line_offline_tick(lah, agv_id: str, st) -> None:
    """Xe offline lúc ĐANG CÓ LỆNH/đang chạy → xe MA (vẫn chiếm vùng cửa sổ đã gửi, hiện mờ
    trên map). Offline lúc đứng yên → ẩn hẳn, nhả mọi giữ chỗ. Online lại cần
    GHOST_ONLINE_STREAK lượt liên tiếp mới gỡ ma và khôi phục."""
    from line_agv_handler import traffic_coordinator as tc, line_state_online
    if line_state_online(st):
        st.online_streak += 1
        st.offline_decided = False
        if st.ghost:
            if st.online_streak >= GHOST_ONLINE_STREAK:
                _ghost_release(lah, agv_id, st, recovered=True)
        else:
            tc.resume_online(agv_id)
        return
    st.online_streak = 0
    if st.offline_decided:
        return
    st.offline_decided = True
    # Nhớ lệnh hàng đợi đang chạy lúc mất tín hiệu: xe online lại mà lệnh còn dang dở thì PHẢI làm nốt (resume_after_offline)
    try:
        from task_queue import agv_task_queue as _atq_off
        _run_off = _atq_off.get_running(agv_id)
        if _run_off and str(_run_off.get("command") or "") in ("go_to", "go_charge", "go_wait"):
            st.resume_cmd_id = _run_off.get("cmd_id")
    except Exception as _e_off:
        print(f"[RESUME] {agv_id}: ghi nhớ lệnh đang chạy lúc offline lỗi: {_e_off}")
    route = lah._routes.get(agv_id)
    if st.driving or (route is not None and not route.is_complete and route.full_path):
        st.ghost = True
        st.ghost_since = time.time()
        st.ghost_nodes = _ghost_nodes_of(lah, agv_id, st)
        tc.hold_ghost(agv_id, st.ghost_nodes)
        lah._set_alert(agv_id, st, "signal_lost",
                       f"Mất tín hiệu khi đang chạy — giữ chỗ node {','.join(st.ghost_nodes)}")
        print(f"[GHOST] {agv_id}: mất tín hiệu khi đang chạy → xe ma, giữ {st.ghost_nodes}")
    else:
        tc.suspend_offline(agv_id)


def _ghost_release(lah, agv_id: str, st, recovered: bool) -> None:
    """Gỡ xe ma. recovered=True: xe online lại → khôi phục giữ chỗ, vị trí lệch vùng ma thì
    huỷ route để dò lại. recovered=False: người vận hành gỡ → coi như xe không còn trên đường."""
    from line_agv_handler import traffic_coordinator as tc, line_state_online
    nodes = list(st.ghost_nodes)
    st.ghost = False
    st.ghost_nodes = []
    lah._clear_alert(st, "signal_lost")
    if recovered and line_state_online(st):
        tc.resume_online(agv_id)
        if st.current_tag not in (None, 0) and str(st.current_tag) not in nodes:
            lah.clear_route(agv_id)
            tc.deregister(agv_id)
            print(f"[GHOST] {agv_id}: online lại tại {st.current_tag} ngoài vùng {nodes} → huỷ route")
        else:
            print(f"[GHOST] {agv_id}: online lại, tiếp tục")
    else:
        tc.suspend_offline(agv_id)
        print(f"[GHOST] {agv_id}: gỡ xe ma (vận hành xác nhận)")


async def monitor_line_offline(stop_event: asyncio.Event):
    alerted: set[str] = set()
    while not stop_event.is_set():
        try:
            from line_agv_handler import line_agv_handler as _lah_mon
            now_t = time.time()
            for agv_id, st in _lah_mon.state_store._states.raw_items():
                if st is None or st.last_update <= 0:
                    continue   # chưa từng nhận state nào — chưa kết nối, không phải "mất kết nối"
                _line_offline_tick(_lah_mon, agv_id, st)
                # Xe vừa online lại sau mất tín hiệu (vd vào thang): làm nốt lệnh dang dở. Chạy trong luồng riêng vì
                # dispatch chờ lại chính event loop này.
                if st.resume_cmd_id and st.online_streak >= GHOST_ONLINE_STREAK and not st.ghost:
                    await asyncio.to_thread(_lah_mon.resume_after_offline, agv_id, st)
                # Hàng đợi vừa khôi phục sau khi server khởi động lại: chạy lệnh đầu khi xe sẵn sàng
                from task_queue import agv_task_queue as _atq_rs
                if agv_id in _atq_rs._restore_pending:
                    if _restored_queue_ready(_lah_mon, agv_id):
                        await asyncio.to_thread(_kick_restored_queue, _lah_mon, agv_id)
                    else:
                        await asyncio.to_thread(_adopt_restored_in_cabin, _lah_mon, agv_id)
                stale = (now_t - st.last_update) > LINE_OFFLINE_THRESHOLD_SEC
                still_online = (st.connection_state == "ONLINE")

                if stale and still_online and agv_id not in alerted:
                    alerted.add(agv_id)
                    _msg = (f"{agv_id}: không có state message mới > "
                            f"{LINE_OFFLINE_THRESHOLD_SEC:.0f}s dù connection vẫn 'ONLINE' — "
                            f"nghi xe treo/mất kết nối ngầm (không LWT), cần kiểm tra trực tiếp")
                    print(f"[LINE_OFFLINE] {_msg}")
                    asyncio.create_task(broadcast_update({
                        "type": "assistant_alert",
                        "agv_id": agv_id,
                        "level": "error",
                        "title": "Line AGV mất tín hiệu",
                        "message": _msg,
                        "timestamp": datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).isoformat()
                    }))
                    try:
                        from telegram_bot import notify_error as _tg_notify_line_off
                        _tg_notify_line_off(f"⚠️ {_msg}")
                    except Exception as _e_tg_line_off:
                        print(f"[LINE_OFFLINE] Telegram gửi lỗi: {_e_tg_line_off}")

                if (not stale) and agv_id in alerted:
                    alerted.discard(agv_id)

        except Exception as e:
            print(f"[LINE_OFFLINE] Monitor error: {e}")

        await asyncio.sleep(LINE_OFFLINE_CHECK_INTERVAL_SEC)

# PHÁT HIỆN THỰC TẾ (2026-09-29, deadlock AGV03↔AGV04 tại node 28↔104): khi 1 AGV
# thua head-on mà KHÔNG có nhánh né nào (đường đơn, không side node), nó chỉ được
# đặt state.pending_retry_cmd rồi đứng yên — việc retry lại lệnh này HOÀN TOÀN dựa
# vào _check_waiting_agvs() được kích bởi 1 AGV KHÁC đổi tag (line_agv_handler.py).
# Nếu AGV đang "chặn" nó cũng đứng yên chờ NGƯỢC LẠI (chờ chính AGV đang pending
# rời đi) — vd 2 xe cùng cần đi qua 1 cạnh duy nhất theo 2 chiều ngược nhau, không
# nhánh phụ — thì KHÔNG BAO GIỜ có ai đổi tag để kích lại → cả 2 đứng yên vô thời
# hạn (đúng log thực tế: AGV03 "đang chờ conflict tại 24 quá lâu" lặp lại tới hết
# log, AGV04 im lặng hoàn toàn sau khi vào pending_retry, không có gì đánh thức).
# Vá bằng 1 watchdog ĐỘC LẬP với việc có ai đổi tag hay không: quét định kỳ mọi AGV
# đang pending_retry_cmd, nếu đứng vậy quá PENDING_RETRY_STUCK_THRESHOLD_SEC giây
# liên tục thì TỰ kích lại _check_waiting_agvs() (retry tính toán lại từ đầu, không
# ép di chuyển bừa — an toàn y hệt retry do event kích, chỉ khác nguồn kích).
PENDING_RETRY_STUCK_THRESHOLD_SEC = 20.0
PENDING_RETRY_CHECK_INTERVAL_SEC  = 5.0

async def monitor_pending_retry_stuck(stop_event: asyncio.Event):
    since: dict[str, float] = {}
    while not stop_event.is_set():
        try:
            from line_agv_handler import line_agv_handler as _lah_pr
            now_t = time.monotonic()
            stuck_any = False
            for agv_id, st in list(_lah_pr.state_store._states.items()):
                if st is not None and st.pending_retry_cmd:
                    t0 = since.setdefault(agv_id, now_t)
                    if now_t - t0 >= PENDING_RETRY_STUCK_THRESHOLD_SEC:
                        stuck_any = True
                else:
                    since.pop(agv_id, None)
            if stuck_any:
                print(f"[PENDING_RETRY] Phát hiện AGV đứng yên ở pending_retry_cmd quá "
                      f"{PENDING_RETRY_STUCK_THRESHOLD_SEC:.0f}s không ai kích lại → "
                      f"tự retry định kỳ (đề phòng 2 xe cùng chờ nhau, không tag nào đổi)")
                # PHẢI chạy ở luồng riêng: _check_waiting_agvs → dispatch → plan_path_for_order CHỜ kết quả từ chính
                # event loop này; gọi thẳng trên loop = tự đóng băng loop 30s×3 mỗi lần (mô phỏng 2026-11-09: API treo,
                # xe đứng im hàng chục phút, "lập đường quá 30s" lặp lại, ensure_map_loaded_sync TimeoutError).
                await asyncio.get_running_loop().run_in_executor(
                    None, _lah_pr._check_waiting_agvs, "__periodic_watchdog__")
                since.clear()
        except Exception as e:
            print(f"[PENDING_RETRY] Monitor error: {e}")
        await asyncio.sleep(PENDING_RETRY_CHECK_INTERVAL_SEC)

# PHÁT HIỆN THỰC TẾ (2026-10-08, mô phỏng 5 xe/3 trạm sạc): khi "Về trạm" thấy
# TẤT CẢ trạm sạc đều có xe/đã giữ chỗ, mqtt_client.send_agv_to_special_target
# chuyển xe sang "wait" (điểm chờ đã cấu hình trên map) và đặt
# state.charge_station_wait=True — CỐ Ý KHÔNG dùng pending_retry_cmd (cờ đó bị
# main.monitor_pending_retry_stuck/_check_waiting_agvs XOÁ ngay khi driving=True,
# đúng lúc xe đang lái TỚI điểm chờ, nên không sống sót qua được chặng lái đó).
# Watchdog RIÊNG này quét các xe đang charge_station_wait=True, hễ đã TỚI nơi
# VÀ rảnh hẳn (không còn lái/không còn lệnh chạy) → tự gọi lại "Về trạm", để
# dispatch_or_queue/resolve_special_target_node tự đánh giá lại xem đã có trạm
# sạc nào trống chưa — KHÔNG ép đi, an toàn y hệt 1 lần bấm "Về trạm" tay.
CHARGE_STATION_WAIT_RETRY_INTERVAL_SEC = 15.0

async def monitor_charge_station_wait(stop_event: asyncio.Event):
    while not stop_event.is_set():
        try:
            from line_agv_handler import line_agv_handler as _lah_cw
            from task_queue import agv_task_queue as _atq_cw, CMD_GO_CHARGE as _CGC_cw
            for agv_id, st in list(_lah_cw.state_store._states.items()):
                if (st is not None and st.charge_station_wait
                        and not st.driving and not _atq_cw.is_busy(agv_id)):
                    print(f"[CHARGE_STATION_WAIT] {agv_id}: đang ở điểm chờ, rảnh hẳn "
                          f"→ tự thử lại 'Về trạm' (đề phòng không ai kích lại)")
                    # luồng riêng — xem ghi chú ở monitor_pending_retry_stuck (dispatch chờ lại chính event loop)
                    await asyncio.get_running_loop().run_in_executor(
                        None, _atq_cw.dispatch_or_queue, agv_id, _CGC_cw, None, None, None,
                        'charge_station_wait_retry')
        except Exception as e:
            print(f"[CHARGE_STATION_WAIT] Monitor error: {e}")
        await asyncio.sleep(CHARGE_STATION_WAIT_RETRY_INTERVAL_SEC)

# PHÁT HIỆN THỰC TẾ (mô phỏng, 2026-10-06, va chạm SIM03/SIM05 tại node 24):
# lớp "AN TOÀN VẬT LÝ" trong line_agv_handler._send_window() chỉ so khớp
# current_tag của các xe khác TẠI ĐÚNG THỜI ĐIỂM gửi lệnh — nếu node đích
# đang trống lúc đó, cửa sổ được gửi bình thường. Nhưng 1 cửa sổ di chuyển
# thật tốn VÀI GIÂY để xe thực sự tới (realtime cho xe thật, hoặc thời gian
# mô phỏng cho xe ảo) — nếu 1 xe KHÁC kịp tới ĐÚNG node đích đó TRONG lúc xe
# này còn đang chạy, _send_window() không còn cơ hội chặn nữa (lệnh đã gửi
# xong). Vá bằng watchdog ĐỘC LẬP, chạy liên tục suốt quá trình di chuyển
# (không chỉ 1 lần lúc gửi lệnh): quét mọi AGV đang driving=True, tính node
# ngay sau current_tag trên route đang chạy, so khớp TRỰC TIẾP với current_tag
# của MỌI xe khác — nếu trùng, GỬI STOP KHẨN CẤP ngay (không chờ xe tới hẳn
# nơi mới xử lý). Cùng nguyên lý với lớp đã có, chỉ khác là chạy LẶP LẠI
# trong suốt hành trình thay vì 1 lần duy nhất.
PHYSICAL_COLLISION_CHECK_INTERVAL_SEC = 1.0

# PHÁT HIỆN THỰC TẾ (2026-10-08, AGV01/AGV03 tại node 7 VÀ AGV03/AGV04 tại
# node 28 — CÙNG MỘT NGÀY, 2 lần không phải 1): cả 2 lần đều chỉ được bắt bởi
# watchdog NÀY (chạy mỗi PHYSICAL_COLLISION_CHECK_INTERVAL_SEC=1.0s), KHÔNG
# phải bởi lớp reservation/arbiter lúc dispatch — vì xe CHIẾM node đó chỉ vừa
# vật lý tới đó (tag đổi) SAU KHI xe kia đã được cấp quyền đi tới node đó từ
# trước (reservation hợp lệ lúc cấp). Để rơi vào tay thuần watchdog theo chu kỳ
# nghĩa là có tới 1 giây xe vẫn tiến thêm về phía nguy hiểm trước khi bị chặn —
# ĐỦ GẦN để trong log thực tế AGV03/AGV04 chỉ cách nhau đúng lúc STOP được gửi.
# Fix: tách phần quét ra hàm thuần (không async) để gọi được NGAY LẬP TỨC mỗi
# khi 1 AGV đổi tag (xem line_agv_handler._on_state) — KHÔNG chờ tick kế tiếp
# của vòng lặp 1s. Vòng lặp async dưới đây GIỮ LẠI làm lưới an toàn phụ (bắt
# các ca driving=True mà không có tag-change gần đây kích hoạt, vd xe vừa được
# dispatch tiến vào ngay cạnh 1 xe đã đứng yên từ trước).
_physical_collision_alerted: set[str] = set()


def physical_collision_scan_once() -> None:
    """1 lượt quét toàn bộ AGV đang driving=True, so khớp node kế tiếp trên
    route với current_tag THẬT của MỌI xe khác — gọi được ĐỒNG BỘ (sync) từ cả
    watchdog theo chu kỳ (dưới) và trực tiếp từ _on_state mỗi khi có tag đổi."""
    try:
        from line_agv_handler import line_agv_handler as _lah_pc
        from mqtt_client import send_line_command as _slc_pc
        states = list(_lah_pc.state_store._states.items())
        risky_now: set[str] = set()
        for agv_id, st in states:
            if st is None or not st.driving or st.current_tag is None:
                continue
            route = _lah_pc._routes.get(agv_id)
            if route is None or not route.full_path:
                continue
            cur_str = str(st.current_tag)
            if cur_str not in route.full_path:
                continue
            idx = route.full_path.index(cur_str)
            if idx + 1 >= len(route.full_path):
                continue
            next_node = route.full_path[idx + 1]
            for other_id, other_st in states:
                if other_id == agv_id or other_st is None:
                    continue
                if other_st.current_tag is not None and str(other_st.current_tag) == next_node:
                    risky_now.add(agv_id)
                    if agv_id not in _physical_collision_alerted:
                        _physical_collision_alerted.add(agv_id)
                        _msg = (f"{agv_id}: node {next_node} phía trước đang bị "
                                f"{other_id} CHIẾM VẬT LÝ (phát hiện GIỮA lúc đang "
                                f"chạy, không chỉ lúc gửi lệnh) — đã gửi STOP khẩn cấp")
                        print(f"[PHYSICAL_COLLISION_RISK] {_msg}")
                        try:
                            _slc_pc(agv_id, "stop")
                        except Exception as _e_stop_pc:
                            print(f"[PHYSICAL_COLLISION_RISK] gửi STOP {agv_id} lỗi: {_e_stop_pc}")
                        # PHÁT HIỆN THỰC TẾ (mô phỏng, 2026-10-07): lệnh stop() đưa
                        # firmware về MANUAL (đúng giao thức) nhưng KHÔNG có gì tự
                        # kích gửi lại lệnh sau đó — nếu để vậy, xe đứng im VĨNH VIỄN
                        # dù đường phía trước đã thông từ lâu (đúng ca thực tế: SIM02
                        # dừng tại 15, không bao giờ đi tiếp). Dùng LẠI nguyên cơ chế
                        # "vừa hết lỗi, đứng yên → GỬI LẠI cửa sổ" đã có sẵn cho
                        # error_code (xem _had_error trong line_agv_handler._on_state)
                        # — đánh dấu CHÍNH XÁC như 1 đợt lỗi, watchdog đó tự resend
                        # (kèm tự "run" khôi phục AUTOMATIC) ngay khi an toàn trở lại.
                        _lah_pc._had_error[agv_id] = True
                        _lah_pc._set_alert(agv_id, st, "PHYSICAL_COLLISION_RISK", _msg)
                        try:
                            from telegram_bot import notify_error as _tg_notify_pc
                            _tg_notify_pc(f"⚠️ {_msg}")
                        except Exception as _e_tg_pc:
                            print(f"[PHYSICAL_COLLISION_RISK] Telegram gửi lỗi: {_e_tg_pc}")
                    break
        # Lớp 2: HAI xe cùng sắp vào MỘT node (cả hai đang chạy, chưa xe nào tới) — lớp trên chỉ bắt khi node
        # đã có xe đứng. Cả hai đều đã được cấp cửa sổ vào node đó (đua cấp phép / đổi đường cùng lúc) nên
        # chỉ còn cách dừng bên THUA phân xử, bên thắng đi tiếp rồi bên thua được tự gửi lại cửa sổ.
        try:
            from line_agv_handler import traffic_coordinator as _tc_pc
            _nexts: dict[str, str] = {}
            for agv_id, st in states:
                if st is None or not st.driving or st.current_tag is None:
                    continue
                route = _lah_pc._routes.get(agv_id)
                if route is None or not route.full_path:
                    continue
                cur_str = str(st.current_tag)
                if cur_str not in route.full_path:
                    continue
                idx = route.full_path.index(cur_str)
                if idx + 1 < len(route.full_path) and idx + 1 <= getattr(route, 'window_end', idx + 1):
                    _nexts[agv_id] = str(route.full_path[idx + 1])
            _ids = sorted(_nexts)
            for _i in range(len(_ids)):
                for _j in range(_i + 1, len(_ids)):
                    a, b = _ids[_i], _ids[_j]
                    if _nexts[a] != _nexts[b]:
                        continue
                    loser = b if _tc_pc._arbitrate(a, b, _nexts[a]) == a else a
                    risky_now.add(loser)
                    if loser not in _physical_collision_alerted:
                        _physical_collision_alerted.add(loser)
                        _winner = a if loser == b else b
                        _msg = (f"{loser}: {loser} và {_winner} CÙNG sắp vào node {_nexts[a]} — "
                                f"{loser} thua phân xử, đã gửi STOP khẩn cấp")
                        print(f"[PHYSICAL_COLLISION_RISK] {_msg}")
                        try:
                            _slc_pc(loser, "stop")
                        except Exception as _e_stop2:
                            print(f"[PHYSICAL_COLLISION_RISK] gửi STOP {loser} lỗi: {_e_stop2}")
                        _lah_pc._had_error[loser] = True
                        _st_l = _lah_pc.state_store.get(loser)
                        if _st_l is not None:
                            _lah_pc._set_alert(loser, _st_l, "PHYSICAL_COLLISION_RISK", _msg)
        except Exception as _e_l2:
            print(f"[PHYSICAL_COLLISION_RISK] lớp 2 lỗi: {_e_l2}")
        for agv_id in list(_physical_collision_alerted):
            if agv_id not in risky_now:
                _physical_collision_alerted.discard(agv_id)
                _st_clear = _lah_pc.state_store.get(agv_id)
                if _st_clear is not None:
                    _lah_pc._clear_alert(_st_clear, "PHYSICAL_COLLISION_RISK")
    except Exception as e:
        print(f"[PHYSICAL_COLLISION_RISK] Monitor error: {e}")


# PHÁT HIỆN THỰC TẾ (mô phỏng, 2026-10-09): lớp quét trên chỉ chặn được
# TRƯỚC khi 1 xe tới node bị chiếm — nó chỉ so next_node = full_path[idx+1]
# TRÊN ROUTE CỦA CHÍNH agv_id đó với current_tag của xe khác, KHÔNG BAO GIỜ
# so sánh current_tag CỦA CHÍNH agv_id với current_tag của xe khác (vị trí
# NGAY LÚC NÀY). Khi tag của 1 xe đổi THẲNG tới đúng node 1 xe khác đang
# đứng (STOP gửi không kịp, hoặc dừng do lỗi khác rồi mới nhận order), lớp
# trên không bắt được nữa — log thực tế: SIM03 vẫn va chạm thật với SIM04 tại
# node 27 dù lớp trên đã bắn STOP đúng nhiều lần cho các lần SIM03 TIẾN GẦN
# node đó trước đó (SIM04 đứng im ở 27 từ trước, do LOCATE_THEN_CHARGE bỏ
# cuộc sau 120s — không có order mới nào gửi nữa). Thêm lớp 2 ĐỘC LẬP: so
# khớp current_tag giữa MỌI CẶP xe (không cần driving) — trùng tag → ĐANG
# va chạm vật lý THẬT (không chỉ rủi ro) → STOP CẢ HAI ngay.
_physical_overlap_alerted: set[frozenset] = set()


def physical_overlap_scan_once() -> None:
    """Lớp 2: phát hiện va chạm ĐÃ XẢY RA (2 xe cùng báo đúng 1 tag ngay lúc
    này) — bổ sung cho physical_collision_scan_once() (chỉ bắt được NGUY CƠ
    trước khi tới, không bắt được lúc đã trùng)."""
    try:
        from line_agv_handler import line_agv_handler as _lah_ov
        from mqtt_client import send_line_command as _slc_ov
        states = list(_lah_ov.state_store._states.items())
        overlapping_pairs_now: set[frozenset] = set()
        for i, (agv_id, st) in enumerate(states):
            if st is None or st.current_tag is None:
                continue
            for other_id, other_st in states[i + 1:]:
                if other_st is None or other_st.current_tag is None:
                    continue
                if str(st.current_tag) != str(other_st.current_tag):
                    continue
                pair = frozenset((agv_id, other_id))
                overlapping_pairs_now.add(pair)
                if pair in _physical_overlap_alerted:
                    continue
                _physical_overlap_alerted.add(pair)
                _msg = (f"{agv_id} và {other_id} ĐANG CÙNG báo node {st.current_tag} "
                        f"(va chạm vật lý THẬT, không chỉ nguy cơ) — gửi STOP cả hai")
                print(f"[PHYSICAL_COLLISION_ACTIVE] {_msg}")
                for _vid, _vst in ((agv_id, st), (other_id, other_st)):
                    try:
                        _slc_ov(_vid, "stop")
                    except Exception as _e_stop_ov:
                        print(f"[PHYSICAL_COLLISION_ACTIVE] gửi STOP {_vid} lỗi: {_e_stop_ov}")
                    _lah_ov._had_error[_vid] = True
                    # KHOÁ xe: off_route ngay sau STOP không được re-dispatch (đã làm xe chạy lại sau va chạm 2026-11-20 16:21)
                    _lah_ov.__dict__.setdefault('_collision_hold', {})[_vid] = time.monotonic()
                    _lah_ov._set_alert(_vid, _vst, "PHYSICAL_COLLISION_ACTIVE", _msg)
                try:
                    from telegram_bot import notify_error as _tg_notify_ov
                    _tg_notify_ov(f"🚨 {_msg}")
                except Exception as _e_tg_ov:
                    print(f"[PHYSICAL_COLLISION_ACTIVE] Telegram gửi lỗi: {_e_tg_ov}")
        for pair in list(_physical_overlap_alerted):
            if pair not in overlapping_pairs_now:
                _physical_overlap_alerted.discard(pair)
                for vid in pair:
                    _vst_clear = _lah_ov.state_store.get(vid)
                    if _vst_clear is not None:
                        _lah_ov._clear_alert(_vst_clear, "PHYSICAL_COLLISION_ACTIVE")
    except Exception as e:
        print(f"[PHYSICAL_COLLISION_ACTIVE] Monitor error: {e}")


async def monitor_physical_collision_risk(stop_event: asyncio.Event):
    while not stop_event.is_set():
        physical_collision_scan_once()
        physical_overlap_scan_once()
        await asyncio.sleep(PHYSICAL_COLLISION_CHECK_INTERVAL_SEC)


# Dò + phá bế tắc DÂY CHUYỀN nhiều xe (xem LineAGVHandler._break_stall_cycles)
# — không cần chạy sát mỗi giây như watchdog va chạm vật lý trên (đây là lớp
# bảo hiểm CUỐI cho ca hiếm, chỉ kích hoạt sau khi đã đứng im > STALL_BYPASS_SEC
# = 25s), 5s/lần là đủ nhanh để không kéo dài thêm đáng kể so với ngưỡng đó.
STALL_CYCLE_CHECK_INTERVAL_SEC = 5.0


async def monitor_stall_cycles(stop_event: asyncio.Event):
    while not stop_event.is_set():
        try:
            from line_agv_handler import line_agv_handler as _lah_cyc
            _lah_cyc._break_stall_cycles()
        except Exception as e:
            print(f"[TRAFFIC] monitor_stall_cycles error: {e}")
        await asyncio.sleep(STALL_CYCLE_CHECK_INTERVAL_SEC)
# ==========================
# DATABASE CONFIG
# ==========================
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:ducmanh1801@localhost:5432/TOT_AGV")
pool = None

# Port API thật luôn 8000 (mặc định) — mô phỏng fleet set API_PORT khác (vd
# 8001) để chạy SONG SONG với server sản xuất trên cùng máy, không tranh port.
API_PORT = int(os.getenv("API_PORT", "8000"))

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
    app.state.line_offline_stop = asyncio.Event()
    app.state.line_offline_task = asyncio.create_task(monitor_line_offline(app.state.line_offline_stop))
    app.state.pending_retry_stop = asyncio.Event()
    app.state.pending_retry_task = asyncio.create_task(monitor_pending_retry_stuck(app.state.pending_retry_stop))
    app.state.charge_station_wait_stop = asyncio.Event()
    app.state.charge_station_wait_task = asyncio.create_task(
        monitor_charge_station_wait(app.state.charge_station_wait_stop))
    app.state.physical_collision_stop = asyncio.Event()
    app.state.physical_collision_task = asyncio.create_task(
        monitor_physical_collision_risk(app.state.physical_collision_stop))
    app.state.stall_cycle_stop = asyncio.Event()
    app.state.stall_cycle_task = asyncio.create_task(
        monitor_stall_cycles(app.state.stall_cycle_stop))
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

                # Cột phục vụ KHÔI PHỤC hàng đợi sau khi server khởi động lại (thứ tự, cờ chuỗi thang, vị trí xuất phát)
                await _conn.execute("ALTER TABLE agv_task_executions ADD COLUMN IF NOT EXISTS seq DOUBLE PRECISION")
                await _conn.execute("ALTER TABLE agv_task_executions ADD COLUMN IF NOT EXISTS chain_leg BOOLEAN DEFAULT FALSE")
                await _conn.execute("ALTER TABLE agv_task_executions ADD COLUMN IF NOT EXISTS start_node VARCHAR(100)")
                from persistent_flags import FlagStore as _FS_init
                await _FS_init.ensure_table(_conn)      # cờ trạng thái ghi xuyên DB (khôi phục sau khi khởi động lại)

                # ── Lệnh 'running'/'queued' còn sót từ lần chạy trước ─────────────────────────
                # Hàng đợi (task_queue.py) nằm trong RAM nhưng nay được LƯU DB kèm thứ tự: lệnh còn sót mà chưa quá cũ
                # (QUEUE_RESTORE_MAX_AGE_H, mặc định 12 giờ) sẽ được KHÔI PHỤC sau khi server sẵn sàng (xem
                # _restore_task_queue) để xe làm nốt. Lệnh quá cũ (server tắt lâu) mới bị coi là rác, tránh tính nhầm
                # "chuyến đang chạy" mãi mãi trong thống kê.
                _max_age_s = float(os.getenv("QUEUE_RESTORE_MAX_AGE_H", "12") or 12) * 3600.0
                _stale = await _conn.execute("""
                    UPDATE agv_task_executions
                    SET status = 'error', completed_at = NOW(),
                        notes = COALESCE(NULLIF(notes, ''), '') || ' [stale: bỏ rơi từ lần chạy trước]'
                    WHERE status IN ('running', 'queued')
                      AND COALESCE(started_at, queued_at) < NOW() - make_interval(secs => $1::double precision)
                """, _max_age_s)
                print(f"[DB] Dọn lệnh quá cũ 'running'/'queued' từ lần chạy trước: {_stale}")

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
                # Chế độ vận hành xe kéo (theo từng xe) — mặc định = hành vi cũ.
                await _conn.execute(
                    "ALTER TABLE agv_devices ADD COLUMN IF NOT EXISTS op_mode TEXT DEFAULT 'roundtrip'"
                )
                await _conn.execute(
                    "ALTER TABLE agv_devices ADD COLUMN IF NOT EXISTS return_mode TEXT DEFAULT 'charge'"
                )
                print("[DB] Columns agv_devices.op_mode / return_mode ensured")
                try:
                    from agv_registry import agv_registry as _registry_rev
                    _registry_rev.load_reverse_capability()
                    _registry_rev.load_op_mode()
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
                await _conn.execute(
                    "ALTER TABLE agv_map_roads ADD COLUMN IF NOT EXISTS speed_bwd FLOAT"
                )
                await _conn.execute(
                    "ALTER TABLE agv_map_benziers ADD COLUMN IF NOT EXISTS speed_bwd FLOAT"
                )
                print("[DB] Columns agv_map_roads/benziers.lidar_off / lidar_off_dir / speed_bwd ensured")
                # Hướng đi RIÊNG theo loại xe (JSON {"trailer":"forward",...}) — chỉ HẠN CHẾ thêm so với
                # hướng chung move_direction (vd cạnh 2 chiều nhưng rơ-moóc chỉ được đi 1 chiều).
                # Nhiều tầng / 1 map: danh sách tầng (JSON) + tầng của từng node / cạnh
                await _conn.execute(
                    "ALTER TABLE agv_maps ADD COLUMN IF NOT EXISTS floors JSONB"
                )
                await _conn.execute(
                    "ALTER TABLE agv_maps ADD COLUMN IF NOT EXISTS elevators JSONB"
                )
                for _t_fl in ("agv_map_points", "agv_map_roads", "agv_map_benziers"):
                    await _conn.execute(
                        f"ALTER TABLE {_t_fl} ADD COLUMN IF NOT EXISTS floor_id TEXT DEFAULT ''"
                    )
                print("[DB] Columns agv_maps.floors / agv_map_*.floor_id ensured")
                await _conn.execute(
                    "ALTER TABLE agv_map_roads ADD COLUMN IF NOT EXISTS type_directions TEXT"
                )
                await _conn.execute(
                    "ALTER TABLE agv_map_benziers ADD COLUMN IF NOT EXISTS type_directions TEXT"
                )
                print("[DB] Columns agv_map_roads/benziers.type_directions ensured")
                # Cột khoảng cách thật (nhập tay ở Map Editor) — benziers chưa có cột
                # distance nào từ trước, roads thì có sẵn nhưng thiếu cờ đánh dấu
                # "đã nhập tay" để phân biệt với giá trị tự tính theo toạ độ vẽ.
                await _conn.execute(
                    "ALTER TABLE agv_map_roads ADD COLUMN IF NOT EXISTS distance_manual BOOLEAN DEFAULT FALSE"
                )
                await _conn.execute(
                    "ALTER TABLE agv_map_benziers ADD COLUMN IF NOT EXISTS distance FLOAT"
                )
                await _conn.execute(
                    "ALTER TABLE agv_map_benziers ADD COLUMN IF NOT EXISTS distance_manual BOOLEAN DEFAULT FALSE"
                )
                print("[DB] Columns agv_map_roads/benziers.distance / distance_manual ensured")
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

                # ── Giám sát tín hiệu WiFi 5GHz (thiết bị ESP32-C5) ───────────────
                await _conn.execute("""
                    CREATE TABLE IF NOT EXISTS wifi_signal_samples (
                        id           BIGSERIAL PRIMARY KEY,
                        device_id    VARCHAR(64) NOT NULL,
                        rssi         SMALLINT NOT NULL,
                        ssid         VARCHAR(64),
                        channel      SMALLINT,
                        band         VARCHAR(8) DEFAULT '5GHz',
                        recorded_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                """)
                await _conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_wifi_samples_device_time "
                    "ON wifi_signal_samples (device_id, recorded_at DESC)"
                )
                await _conn.execute("""
                    CREATE TABLE IF NOT EXISTS wifi_signal_events (
                        id                SERIAL PRIMARY KEY,
                        device_id         VARCHAR(64) NOT NULL,
                        event_type        VARCHAR(20) NOT NULL,
                        rssi              SMALLINT,
                        consecutive_count SMALLINT,
                        outage_seconds    INTEGER,
                        recorded_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                """)
                await _conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_wifi_events_device_time "
                    "ON wifi_signal_events (device_id, recorded_at DESC)"
                )
                # BSSID (MAC của AP) — phục vụ quản lý roaming AGV: biết AGV
                # đang bám AP nào, và ghi lại sự kiện 'roamed' khi đổi AP.
                await _conn.execute(
                    "ALTER TABLE wifi_signal_samples ADD COLUMN IF NOT EXISTS bssid VARCHAR(17)"
                )
                await _conn.execute(
                    "ALTER TABLE wifi_signal_events ADD COLUMN IF NOT EXISTS old_bssid VARCHAR(17)"
                )
                await _conn.execute(
                    "ALTER TABLE wifi_signal_events ADD COLUMN IF NOT EXISTS new_bssid VARCHAR(17)"
                )
                # Nhiễu nền RF (dBm, đo qua promiscuous mode ~60s/lần, thưa
                # hơn RSSI) — dùng tính SNR = rssi - noise_floor trên dashboard.
                await _conn.execute(
                    "ALTER TABLE wifi_signal_samples ADD COLUMN IF NOT EXISTS noise_floor SMALLINT"
                )
                print("[DB] Tables wifi_signal_samples / wifi_signal_events ready")
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
                    _stg_drop = _carry_return_staging(cmd.agv_id)
                    if _stg_drop:
                        # Chế độ carry_hook + drop_cart: ghé điểm thả cố định (tự thả xe
                        # hàng, tự đi tiếp) rồi mới về sạc → đổi lệnh đang chạy thành
                        # go_to staging và xếp lại go_charge ngay sau đó.
                        print(f"[CARRY] {cmd.agv_id}: kéo xe hàng tới {_stg_drop} thả rồi mới về sạc")
                        cmd.command   = CMD_GO_TO
                        cmd.dest_node = _stg_drop
                        _queue.insert_next(cmd.agv_id, CMD_GO_CHARGE, dest_node=None)
                        return bool(_dispatch_go_to(cmd.agv_id, _stg_drop,
                                                    session_id=getattr(cmd, "session_id", None)))
                    send_agv_to_special_target(cmd.agv_id, "charge")
                    return True
                if cmd.command == CMD_GO_WAIT:
                    send_agv_to_special_target(cmd.agv_id, "wait")
                    return True
                if cmd.command == CMD_GO_TO and cmd.dest_node:
                    return bool(_dispatch_go_to(cmd.agv_id, cmd.dest_node,
                                                start_node=getattr(cmd, "start_node", None),
                                                session_id=getattr(cmd, "session_id", None)))
                # ── THANG MÁY (xem floor_nav.py / elevator_coordinator.py) ───────────────────
                import floor_nav as _fn_q
                if cmd.command in _fn_q.ELEVATOR_COMMANDS:
                    from elevator_coordinator import elevator_coordinator as _ec_q
                    ok_el = False
                    if cmd.command == _fn_q.CMD_ELEV_BOOK:
                        _eid, _fid = _fn_q.parse_call(cmd.dest_node)
                        ok_el = _ec_q.book(_eid, _fid, cmd.agv_id)
                    elif cmd.command == _fn_q.CMD_ELEV_CALL:
                        _eid, _fid = _fn_q.parse_call(cmd.dest_node)
                        ok_el = _ec_q.request_open(_eid, _fid, cmd.agv_id)
                    elif cmd.command == _fn_q.CMD_ELEV_RIDE:
                        _eid, _fa, _fb, _wb = _fn_q.parse_ride(cmd.dest_node)
                        ok_el = _ec_q.start_ride(_eid, _fa, _fb, _wb, cmd.agv_id)
                    else:   # CMD_ELEV_RELEASE
                        ok_el = _ec_q.release(str(cmd.dest_node), cmd.agv_id)
                        if ok_el:
                            _queue.on_agv_completed(cmd.agv_id, notes="elevator_released")
                    if not ok_el:
                        # Lỗi giữa chuỗi đi thang (đặt/gọi/đi thang không được): KHÔNG xoá hàng đợi (mất lệnh dang dở) — giữ
                        # nguyên các lệnh còn lại (xe không tự đi tiếp vì lệnh kế chỉ chạy khi lệnh này xong) và đặt lịch
                        # thử lại đúng lệnh vừa lỗi. Backend cũ (legacy) không có cơ chế này → giữ hành vi huỷ chuỗi.
                        _retry = getattr(_ec_q, "retry_failed_command", None)
                        if _retry is not None:
                            _retry(cmd.agv_id, cmd.command, cmd.dest_node)
                        else:
                            _queue.cancel_queue(cmd.agv_id)
                    return bool(ok_el)
                return False
            except Exception as _e:
                # PHÁT HIỆN THỰC TẾ (2026-10-01): str(_e) có thể RỖNG (exception không
                # kèm message, vd lỗi kiểu dữ liệu/race ở sâu trong _dispatch_go_to) —
                # log trước đây chỉ in "[QUEUE_DISPATCH] error: " trống trơn, không cách
                # nào biết lỗi THẬT nằm ở đâu để sửa gốc (đúng ca AGV04 kẹt vĩnh viễn,
                # không rõ nguyên nhân từ log). In kèm traceback đầy đủ.
                import traceback as _tb_qd
                print(f"[QUEUE_DISPATCH] error ({cmd.agv_id}): {type(_e).__name__}: {_e}")
                _tb_qd.print_exc()
                cmd.notes = f"{type(_e).__name__}: {_e}"
                return False

        _queue.dispatch_fn = _queue_dispatch
        from line_agv_handler import line_agv_handler as _lah_rp
        _queue.restore_prepare_fn = lambda _agv: _prepare_restored_head(_lah_rp, _agv, user_initiated=True)
        print("[QUEUE] AGVTaskQueue ready")
        if app.state.db_pool:
            await _restore_task_queue(app.state.db_pool, _queue)
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
    if getattr(app.state, "line_offline_stop", None):
        app.state.line_offline_stop.set()
    if getattr(app.state, "line_offline_task", None):
        try:
            await app.state.line_offline_task
        except Exception as e:
            print(f"[LINE_OFFLINE] Task stop error: {e}")
    if getattr(app.state, "pending_retry_stop", None):
        app.state.pending_retry_stop.set()
    if getattr(app.state, "pending_retry_task", None):
        try:
            await app.state.pending_retry_task
        except Exception as e:
            print(f"[PENDING_RETRY] Task stop error: {e}")
    if getattr(app.state, "charge_station_wait_stop", None):
        app.state.charge_station_wait_stop.set()
    if getattr(app.state, "charge_station_wait_task", None):
        try:
            await app.state.charge_station_wait_task
        except Exception as e:
            print(f"[CHARGE_STATION_WAIT] Task stop error: {e}")
    if getattr(app.state, "physical_collision_stop", None):
        app.state.physical_collision_stop.set()
    if getattr(app.state, "physical_collision_task", None):
        try:
            await app.state.physical_collision_task
        except Exception as e:
            print(f"[PHYSICAL_COLLISION_RISK] Task stop error: {e}")
    if getattr(app.state, "stall_cycle_stop", None):
        app.state.stall_cycle_stop.set()
    if getattr(app.state, "stall_cycle_task", None):
        try:
            await app.state.stall_cycle_task
        except Exception as e:
            print(f"[TRAFFIC] stall_cycle Task stop error: {e}")
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
            version="3.0.0",
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
        map_manager.invalidate_load_cache()   # buộc load lại
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
            SELECT id, name, origin_x, origin_y, origin_theta, image_path, floors, elevators
            FROM agv_maps
            WHERE id = $1
        """, map_id)
        if not map_info:
            raise HTTPException(404, "Map không tồn tại")

        # Lấy points
        points = await conn.fetch("""
            SELECT name_id, name, x, y, action, type, speed, COALESCE(floor_id, '') AS floor_id
            FROM agv_map_points
            WHERE map_id = $1
        """, map_id)

        # Lấy roads
        roads = await conn.fetch("""
            SELECT id_source, id_dest,
                   point_start_x, point_start_y,
                   point_end_x, point_end_y,
                   move_direction, width, speed, distance,
                   COALESCE(distance_manual, FALSE) AS distance_manual, type_directions,
                   COALESCE(lidar_off, FALSE) AS lidar_off,
                   COALESCE(lidar_off_dir, 'none') AS lidar_off_dir, speed_bwd,
                   COALESCE(floor_id, '') AS floor_id
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
                   move_direction, width, speed, distance,
                   COALESCE(distance_manual, FALSE) AS distance_manual, type_directions,
                   COALESCE(lidar_off, FALSE) AS lidar_off,
                   COALESCE(lidar_off_dir, 'none') AS lidar_off_dir, speed_bwd,
                   COALESCE(floor_id, '') AS floor_id
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
            "floors": _floors_for_response(map_info),
            "elevators": _elevators_for_response(map_info),
            "robot_points": [
                {
                    "floor_id": p["floor_id"],
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


@app.post("/api/maps/{map_id}/copy")
async def copy_map(map_id: str, request: Request):
    """Sao chép TOÀN BỘ 1 bản đồ (points/roads/benziers/codes + ảnh nền) thành
    1 bản đồ MỚI độc lập — map_id mới sinh (cùng quy ước Date.now() dạng chuỗi
    mà map_editor.html dùng khi tạo map mới), KHÔNG đụng gì tới bản đồ nguồn."""
    if pool is None:
        raise HTTPException(status_code=503, detail="Database pool chưa khởi tạo")
    try:
        body = await request.json()
    except Exception:
        body = {}
    new_name = (body.get("name") or "").strip()
    new_map_id = str(int(time.time() * 1000))

    async with pool.acquire() as conn:
        await _ensure_map_schema(conn)
        async with conn.transaction():
            src = await conn.fetchrow("SELECT * FROM agv_maps WHERE id = $1", map_id)
            if not src:
                raise HTTPException(status_code=404, detail="Map không tồn tại")
            final_name = new_name or f"{src['name'] or map_id} (copy)"

            # Ảnh nền: copy sang file RIÊNG cho map mới — độc lập hoàn toàn với
            # map nguồn (không chia sẻ file, khớp đúng ý "y hệt vậy" nhưng tách rời).
            new_image_path = None
            if src["image_path"]:
                src_file = MAP_DIR / f"{map_id}.png"
                if src_file.exists():
                    (MAP_DIR / f"{new_map_id}.png").write_bytes(src_file.read_bytes())
                    new_image_path = f"maps/{new_map_id}.png"

            # Danh sách tầng: copy ảnh nền các tầng ngoài tầng đầu sang tên file mới
            new_floors = None
            if src["floors"]:
                _fl_raw = src["floors"]
                if isinstance(_fl_raw, str):
                    _fl_raw = json.loads(_fl_raw)
                new_floors = []
                for _i_fl, _f_fl in enumerate(_fl_raw):
                    _g_fl = dict(_f_fl)
                    if _i_fl == 0:
                        _g_fl["image_path"] = new_image_path
                    elif _f_fl.get("image_path"):
                        _sf = MAP_DIR / f"{map_id}__{_f_fl['id']}.png"
                        if _sf.exists():
                            (MAP_DIR / f"{new_map_id}__{_f_fl['id']}.png").write_bytes(_sf.read_bytes())
                            _g_fl["image_path"] = f"maps/{new_map_id}__{_f_fl['id']}.png"
                        else:
                            _g_fl["image_path"] = None
                    new_floors.append(_g_fl)

            await conn.execute("""
                INSERT INTO agv_maps (id, name, origin_x, origin_y, origin_theta,
                                       resolution, image_path, modify_time, layer, floors, elevators)
                VALUES ($1, $2, $3, $4, $5, $6, $7, NOW(), $8, $9::jsonb, $10::jsonb)
            """, new_map_id, final_name, src["origin_x"], src["origin_y"],
                src["origin_theta"], src["resolution"], new_image_path, src["layer"],
                json.dumps(new_floors, ensure_ascii=False) if new_floors else None,
                json.dumps(_elevators_for_response(src), ensure_ascii=False) if src["elevators"] else None)

            await conn.execute("""
                INSERT INTO agv_map_points
                    (map_id, name_id, name, x, y, theta, type, zone, action,
                     speed, carrier, available, accuracy, floor_id)
                SELECT $2, name_id, name, x, y, theta, type, zone, action,
                       speed, carrier, available, accuracy, floor_id
                FROM agv_map_points WHERE map_id = $1
            """, map_id, new_map_id)

            await conn.execute("""
                INSERT INTO agv_map_roads
                    (map_id, name, id_source, id_dest, point_start_x, point_start_y,
                     point_end_x, point_end_y, width, speed, move_direction,
                     distance, distance_manual, lidar_off, lidar_off_dir, speed_bwd, type_directions, floor_id)
                SELECT $2, name, id_source, id_dest, point_start_x, point_start_y,
                       point_end_x, point_end_y, width, speed, move_direction,
                       distance, distance_manual, lidar_off, lidar_off_dir, speed_bwd, type_directions, floor_id
                FROM agv_map_roads WHERE map_id = $1
            """, map_id, new_map_id)

            await conn.execute("""
                INSERT INTO agv_map_benziers
                    (map_id, name, id_source, id_dest, point_start_x, point_start_y,
                     point_end_x, point_end_y, curve_point_start_x, curve_point_start_y,
                     curve_point_end_x, curve_point_end_y, width, speed, move_direction,
                     lidar_off, lidar_off_dir, speed_bwd, distance, distance_manual, type_directions, floor_id)
                SELECT $2, name, id_source, id_dest, point_start_x, point_start_y,
                       point_end_x, point_end_y, curve_point_start_x, curve_point_start_y,
                       curve_point_end_x, curve_point_end_y, width, speed, move_direction,
                       lidar_off, lidar_off_dir, speed_bwd, distance, distance_manual, type_directions, floor_id
                FROM agv_map_benziers WHERE map_id = $1
            """, map_id, new_map_id)

            await conn.execute("""
                INSERT INTO agv_map_codes (map_id, code_id, code, x, y, theta)
                SELECT $2, code_id, code, x, y, theta
                FROM agv_map_codes WHERE map_id = $1
            """, map_id, new_map_id)

    print(f"[MAP] Đã sao chép map {map_id} → {new_map_id} ({final_name})")
    return {"id": new_map_id, "name": final_name}


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


# router này (GET /supply-groups) trước đây không được gắn vào app → 404; gắn sau map_config_router
# nên route trùng (/config) vẫn ưu tiên bản trong map_configure_api.
app.include_router(router)


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


async def _ensure_map_schema(conn) -> None:
    """Đảm bảo đủ bảng/cột cho bản đồ (agv_maps + node/edge) — dùng chung cho cả
    luồng upload thủ công (HTTP /api/agv/map/upload-full) lẫn AGV SLAM tự gửi bản
    đồ quét về qua MQTT (xem handle_slam_map_upload)."""
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
    # Tỉ lệ ảnh/thế giới thật (m/pixel) — bản đồ AGV SLAM quét về cần cột này để
    # MapConfigure vẽ đúng tỉ lệ; bản đồ upload thủ công trước giờ không có, để
    # NULL (frontend tự fallback theo RES_DEFAULT).
    await conn.execute("""
        ALTER TABLE agv_maps ADD COLUMN IF NOT EXISTS resolution DOUBLE PRECISION
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
            distance_manual BOOLEAN DEFAULT FALSE,
            lidar_off      BOOLEAN DEFAULT FALSE,
            lidar_off_dir  TEXT DEFAULT 'none'
        )
    """)
    await conn.execute("""
        ALTER TABLE agv_map_roads
        ADD COLUMN IF NOT EXISTS distance_manual BOOLEAN DEFAULT FALSE
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
            lidar_off_dir         TEXT DEFAULT 'none',
            distance              FLOAT,
            distance_manual       BOOLEAN DEFAULT FALSE
        )
    """)
    await conn.execute("""
        ALTER TABLE agv_map_benziers
        ADD COLUMN IF NOT EXISTS distance_manual BOOLEAN DEFAULT FALSE
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
        ALTER TABLE agv_map_benziers
        ADD COLUMN IF NOT EXISTS distance FLOAT
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS agv_map_codes (
            id      SERIAL PRIMARY KEY,
            map_id  TEXT REFERENCES agv_maps(id) ON DELETE CASCADE,
            code_id TEXT, code TEXT,
            x FLOAT, y FLOAT, theta FLOAT DEFAULT 0
        )
    """)
    # Nhiều tầng trong 1 map (cùng map_id): agv_maps.floors = danh sách tầng (JSON), mỗi
    # node/cạnh mang floor_id của tầng mình ('' = tầng đầu, dữ liệu cũ).
    await conn.execute("ALTER TABLE agv_maps ADD COLUMN IF NOT EXISTS floors JSONB")
    # Danh sách thang máy của map: [{id,name,note}] — node loại 'elevator' (action.elevator_id)
    # cùng id trên các tầng khác nhau = cùng 1 thang.
    await conn.execute("ALTER TABLE agv_maps ADD COLUMN IF NOT EXISTS elevators JSONB")
    for _t_fl in ("agv_map_points", "agv_map_roads", "agv_map_benziers"):
        await conn.execute(f"ALTER TABLE {_t_fl} ADD COLUMN IF NOT EXISTS floor_id TEXT DEFAULT ''")


def _clean_floor_id(raw, fallback: str) -> str:
    """ID tầng an toàn để dùng trong tên file / khoá (chỉ chữ-số-_-)."""
    import re as _re_fl
    fid = _re_fl.sub(r"[^A-Za-z0-9_-]", "", str(raw or ""))[:24]
    return fid or fallback


def _floor_image_url(img_rel, v=None) -> str | None:
    """'maps/xxx.png' (đường dẫn lưu DB) → '/maps/xxx.png?v=..' (URL cho trình duyệt)."""
    if not img_rel:
        return None
    url = "/" + str(img_rel).lstrip("/")
    return f"{url}?v={v}" if v else url


def _build_floors_for_save(map_id: str, floors_in) -> list:
    """Chuẩn hoá danh sách tầng từ editor → danh sách lưu vào agv_maps.floors.
    Ảnh nền: tầng đầu dùng file cũ {map_id}.png (tương thích ngược), tầng khác {map_id}__{fid}.png.
    `image` (base64) = ảnh mới; `keep_image` = giữ file đang có; còn lại = không ảnh."""
    out, used = [], set()
    for i, f in enumerate(floors_in or []):
        if not isinstance(f, dict):
            continue
        fid = _clean_floor_id(f.get("id"), f"F{i + 1}")
        while fid in used:
            fid += "x"
        used.add(fid)
        stem = map_id if not out else f"{map_id}__{fid}"
        img_rel, img_v = None, None
        b64 = f.get("image") or ""
        if b64:
            img_rel = _save_map_image(stem, b64)
            if img_rel:
                img_v = int(time.time())
        elif f.get("keep_image") and (MAP_DIR / f"{stem}.png").exists():
            img_rel = f"maps/{stem}.png"
            img_v = f.get("image_v")
        try:
            res = float(f.get("resolution")) if f.get("resolution") not in (None, "") else None
        except (TypeError, ValueError):
            res = None
        out.append({
            "id": fid,
            "name": str(f.get("name") or f"Tầng {len(out) + 1}")[:60],
            "note": str(f.get("note") or "")[:300],
            "level": f.get("level") if isinstance(f.get("level"), (int, float)) else len(out) + 1,
            "origin_x": float(f.get("origin_x") or 0),
            "origin_y": float(f.get("origin_y") or 0),
            "resolution": res,
            "image_path": img_rel,
            "image_v": img_v,
        })
    return out


def _clean_elevators(raw) -> list:
    """Chuẩn hoá danh sách thang máy từ editor ([{id,name,note}]) — bỏ trùng id, cắt độ dài."""
    out, used = [], set()
    for i, e in enumerate(raw or []):
        if not isinstance(e, dict):
            continue
        eid = _clean_floor_id(e.get("id"), f"E{i + 1}")
        if eid in used:
            continue
        used.add(eid)
        out.append({
            "id": eid,
            "name": str(e.get("name") or eid)[:60],
            "note": str(e.get("note") or "")[:300],
        })
    return out


def _elevators_for_response(map_row) -> list:
    raw = map_row["elevators"] if "elevators" in map_row.keys() else None
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = None
    return raw or []


def _floors_for_response(map_row) -> list:
    """Danh sách tầng trả cho editor. Map cũ (chưa có floors) → 1 tầng 'F1' lấy từ cột cũ."""
    raw = map_row["floors"] if "floors" in map_row.keys() else None
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = None
    if not raw:
        return [{
            "id": "F1", "name": "Tầng 1", "note": "", "level": 1,
            "origin_x": map_row["origin_x"], "origin_y": map_row["origin_y"],
            "resolution": None,
            "image_path": _floor_image_url(f"maps/{map_row['id']}.png") if map_row["image_path"] else None,
        }]
    res = []
    for f in raw:
        g = dict(f)
        g["image_path"] = _floor_image_url(f.get("image_path"), f.get("image_v"))
        res.append(g)
    return res


def _save_map_image(map_id: str, image_b64: str) -> str | None:
    """Giải mã ảnh bản đồ base64 và ghi ra MAP_DIR/{map_id}.png — dùng chung cho
    upload thủ công (HTTP) lẫn AGV SLAM gửi bản đồ quét về (MQTT). Trả về
    image_path dạng "maps/{map_id}.png" (khớp cột agv_maps.image_path) hoặc None
    nếu không có/không giải mã được ảnh."""
    if not image_b64:
        return None
    if image_b64.startswith("data:"):
        image_b64 = image_b64.split(",", 1)[1]
    try:
        image_data = base64.b64decode(image_b64)
        if len(image_data) < 1000:  # quá nhỏ → lỗi base64
            raise Exception("Base64 quá ngắn")
    except Exception as e:
        print(f"[MAP] Lỗi decode ảnh: {e}")
        return None

    MAP_DIR.mkdir(parents=True, exist_ok=True)
    image_file = MAP_DIR / f"{map_id}.png"
    with open(image_file, "wb") as f:
        f.write(image_data)
    print(f"[MAP] Đã lưu ảnh: {image_file} ({len(image_data)} bytes)")
    return f"maps/{map_id}.png"


async def handle_slam_map_upload(agv_id: str, payload: dict) -> dict:
    """AGV SLAM gửi bản đồ quét laser về qua MQTT (topic .../map, xem on_message
    trong mqtt_client.py) — lưu ảnh + upsert agv_maps. KHÁC upload thủ công
    (_do_upload_map): KHÔNG đụng agv_map_points/roads/benziers — node/edge do
    người dùng đặt tay qua MapConfigure vẫn giữ nguyên qua các lần quét lại.

    Payload kỳ vọng: {mapId?, mapName?, resolution?, origin:{x,y,theta}, image}
    """
    global last_map_id
    if pool is None:
        print(f"[SLAM_MAP] {agv_id}: DB pool chưa khởi tạo, bỏ qua")
        return {"status": "error", "detail": "db pool not ready"}

    map_id   = str(payload.get("mapId") or uuid.uuid4())
    map_name = str(payload.get("mapName") or "").strip() or f"map_{map_id}"
    resolution = payload.get("resolution")
    resolution = float(resolution) if resolution not in (None, "") else None
    origin = payload.get("origin") or {}
    origin_x = float(origin.get("x", 0) or 0)
    origin_y = float(origin.get("y", 0) or 0)
    origin_theta = float(origin.get("theta", 0) or 0)

    image_path = _save_map_image(map_id, payload.get("image") or "")

    async with pool.acquire() as conn:
        await _ensure_map_schema(conn)
        is_new = not await conn.fetchval("SELECT 1 FROM agv_maps WHERE id = $1", map_id)
        if is_new:
            await conn.execute("""
                INSERT INTO agv_maps (id, name, origin_x, origin_y, origin_theta, image_path, resolution)
                VALUES ($1,$2,$3,$4,$5,$6,$7)
            """, map_id, map_name, origin_x, origin_y, origin_theta, image_path, resolution)
            print(f"[SLAM_MAP] {agv_id}: tạo map mới {map_id} ({map_name}) từ bản đồ quét")
        else:
            await conn.execute("""
                UPDATE agv_maps SET
                    name = CASE WHEN $2 <> '' THEN $2 ELSE name END,
                    origin_x = $3, origin_y = $4, origin_theta = $5,
                    image_path = COALESCE($6, image_path),
                    resolution = COALESCE($7, resolution),
                    updated_at = NOW()
                WHERE id = $1
            """, map_id, map_name, origin_x, origin_y, origin_theta, image_path, resolution)
            print(f"[SLAM_MAP] {agv_id}: cập nhật map {map_id} — giữ nguyên node/edge đã đặt")

        # Bản đồ AGV vừa gửi về coi là bản đồ hiện tại của chính nó
        await conn.execute("UPDATE agv_devices SET map_id = $1 WHERE name = $2", map_id, agv_id)

    last_map_id = map_id
    return {"status": "success", "map_id": map_id, "map_name": map_name,
            "image_saved": image_path, "is_new": is_new}


async def _do_upload_map(payload: dict):
    global last_map_id

    print("[UPLOAD-MAP] Nhận payload, đang xử lý...")

    # ================== AUTO-CREATE TABLES IF NOT EXIST ==================
    if pool is None:
        raise Exception("Database pool chưa khởi tạo")
    async with pool.acquire() as conn:
        await _ensure_map_schema(conn)

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

    image_path = _save_map_image(map_id, image_b64) if image_b64 else None
    if image_b64 and not image_path:
        raise HTTPException(status_code=400, detail="Invalid image base64")

    # ── Nhiều tầng (editor gửi payload["floors"]); không có → map 1 tầng như cũ ──
    floors_list = _build_floors_for_save(map_id, payload.get("floors")) if payload.get("floors") else []
    floor_ids = {f["id"] for f in floors_list}
    first_floor_id = floors_list[0]["id"] if floors_list else ""
    if floors_list and floors_list[0].get("image_path"):
        image_path = floors_list[0]["image_path"]      # ảnh tầng đầu = ảnh chính của map (cột cũ)

    # Danh sách thang máy: chỉ ghi khi editor gửi (có key) — [] nghĩa là đã xoá hết thang
    elevators_json = (json.dumps(_clean_elevators(payload.get("elevators")), ensure_ascii=False)
                      if "elevators" in payload else None)

    def _fl_of(item) -> str:
        fid = str(item.get("floor") or "")
        return fid if fid in floor_ids else first_floor_id

    # ================== LƯU DB ==================
    if pool is None:
        raise HTTPException(status_code=503, detail="Database pool chưa khởi tạo")
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Upsert map
            await conn.execute("""
                INSERT INTO agv_maps (id, name, origin_x, origin_y, origin_theta, image_path, modify_time, layer, floors, elevators)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,$10::jsonb)
                ON CONFLICT (id) DO UPDATE SET
                    name=EXCLUDED.name,
                    origin_x=EXCLUDED.origin_x,
                    origin_y=EXCLUDED.origin_y,
                    origin_theta=EXCLUDED.origin_theta,
                    image_path=COALESCE(EXCLUDED.image_path, agv_maps.image_path),
                    modify_time=EXCLUDED.modify_time,
                    layer=EXCLUDED.layer,
                    floors=COALESCE(EXCLUDED.floors, agv_maps.floors),
                    elevators=COALESCE(EXCLUDED.elevators, agv_maps.elevators),
                    updated_at=NOW()
            """, map_id, map_name, origin_x, origin_y, origin_theta, image_path, modify_time, layer,
                json.dumps(floors_list, ensure_ascii=False) if floors_list else None, elevators_json)

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
                    (map_id, name_id, name, x, y, theta, type, zone, action, speed, carrier, available, accuracy, floor_id)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,$10,$11,$12,$13,$14)
                """, map_id,
                    str(p.get("name_id", "")),
                    p.get("name", ""),
                    p.get("x"), p.get("y"), p.get("theta"),
                    p.get("type", 0), p.get("zone", ""), _action,
                    float(p.get("speed", 0.5)),
                    p.get("carrier", 0), p.get("available", False), p.get("accuracy", 0),
                    _fl_of(p))

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
                     width, speed, move_direction, distance, lidar_off, lidar_off_dir, speed_bwd, distance_manual,
                     type_directions, floor_id)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18)
                """, map_id, r.get("name", ""),
                    str(r["id_source"]), str(r["id_dest"]),
                    point_start[0], point_start[1],
                    point_end[0], point_end[1],
                    r.get("width", 0.95), r.get("speed", 0.3),
                    r.get("move_direction", 0), r.get("distance", 0),
                    bool(r.get("lidar_off", False)),
                    str(r.get("lidar_off_dir") or "none"),
                    _speed_bwd, bool(r.get("distance_manual", False)),
                    _td_json(r.get("type_directions")), _fl_of(r))

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
                    _b_distance = b.get("distance")
                    _b_distance = float(_b_distance) if _b_distance not in (None, "", 0) else None
                    await conn.execute("""
                        INSERT INTO agv_map_benziers (
                            map_id, name, id_source, id_dest,
                            point_start_x, point_start_y, point_end_x, point_end_y,
                            curve_point_start_x, curve_point_start_y, curve_point_end_x, curve_point_end_y,
                            width, speed, move_direction, lidar_off, lidar_off_dir, speed_bwd, distance, distance_manual,
                            type_directions, floor_id
                        )
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22)
                    """, map_id, b.get("name", ""),
                        str(b["id_source"]), str(b["id_dest"]),
                        point_start[0], point_start[1],
                        point_end[0], point_end[1],
                        curve_point_start[0], curve_point_start[1],
                        curve_point_end[0], curve_point_end[1],
                        b.get("width", 0.3), b.get("speed", 0.3),
                        b.get("move_direction", 0), bool(b.get("lidar_off", False)),
                        str(b.get("lidar_off_dir") or "none"),
                        _b_speed_bwd, _b_distance, bool(b.get("distance_manual", False)),
                        _td_json(b.get("type_directions")), _fl_of(b)
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
from persistent_flags import PersistentPairSet as _PPS_main, flag_store as _flag_store
_pending_staging_transits = _PPS_main("staging_transit")   # set[(agv_id, node)] — ghi xuyên DB (persistent_flags)

# Gom lệnh cả lượt cấp hàng (Line AGV): chờ ~1s thu thập đủ các lệnh cùng session
# rồi sinh lệnh lấy hàng tại TẤT CẢ điểm cấp TRƯỚC, mới tới các lệnh giao + sạc.
# Format: {(agv_id, session_id): {"commands": [(cmd,dest,start)], "task": asyncio.Task, "session_label": str}}
_supply_batch: dict = {}
_SUPPLY_BATCH_DELAY_SEC = 1.0

def _line_state_online(st) -> bool:
    from line_agv_handler import line_state_online
    return line_state_online(st)


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
            if not _line_state_online(_lah.state_store.get(_oid)):
                continue   # xe offline = không tồn tại, không giữ đích
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
        # Case 4: xe MA (mất tín hiệu khi đang chạy) — giữ cả vùng cửa sổ đã gửi.
        for _oid, _st in _lah.state_store._states.items():
            if _oid != exclude_agv and _st is not None and _st.ghost:
                for _n in _st.ghost_nodes:
                    occupied.setdefault(str(_n), _oid)
    except Exception:
        pass
    return occupied


def _required_supply_node(node_actions: dict, dest_node,
                           agv_id: str | None = None,
                           current_node: str | None = None) -> str | None:
    """Supply node phục vụ team của dest_node (giống Phase 0 của planner).

    Trả về node_id (str) của điểm cấp hàng cho tổ của dest_node, hoặc None nếu
    dest_node không phải dropoff có team / không có điểm cấp tương ứng.

    PHÁT HIỆN THỰC TẾ (2026-10-02): trước đây trả về node ĐẦU TIÊN khớp
    supply_group theo thứ tự lặp dict (cố định, không liên quan vị trí/tình
    trạng xe) — nếu người dùng đánh dấu NHIỀU node tương đương cùng 1
    supply_group (vd 98 và 99 đều là điểm lấy/trả hàng, cố ý không phân biệt
    cứng để linh động theo plan tối ưu), hàm luôn chọn CÙNG 1 node cố định
    (vd luôn 98) dù node tương đương đang rảnh gần hơn. Sửa: gom HẾT các node
    khớp supply_group rồi dùng _nearest_of() (đã dùng cho staging/pickup
    tương đương ở trên) để chọn node GẦN NHẤT và còn TRỐNG — y hệt cách xử lý
    "nhiều node tương đương" đã có, chỉ khác ở đây áp dụng cho supply_group.
    """
    end_na = node_actions.get(str(dest_node)) or {}
    team = end_na.get('team')
    if not team:
        return None
    team_str = str(team)
    candidates: list[str] = []
    for snid, sncfg in (node_actions or {}).items():
        sncfg = sncfg or {}
        if str(sncfg.get('arrival_action', '') or '').lower() == 'wait_sys':
            sg = sncfg.get('supply_group') or []
            if isinstance(sg, str):
                sg = [s.strip() for s in sg.split(',')]
            if team_str in [str(g) for g in sg]:
                candidates.append(str(snid))
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    return _nearest_of(candidates, current_node, exclude_agv=agv_id)


def _reevaluate_supply_node(dest_node: str, agv_id: str,
                             current_node: str | None) -> str | None:
    """Khi 1 AGV đang pending_retry tới ĐÚNG 1 supply node cố định (vd 98, bị
    chiếm lúc dispatch) và được kích retry lại (xem _check_waiting_agvs) —
    đánh giá lại NGAY LÚC RETRY xem có node tương đương cùng supply_group (vd
    99) đã trống chưa, thay vì bám cứng node cũ đã chọn từ lúc đầu.

    PHÁT HIỆN THỰC TẾ (2026-10-03): 3 AGV cùng khởi động, 2 node cấp hàng
    tương đương (98/99) — 2 xe đầu lấy hết 2 node, xe thứ 3 không còn candidate
    trống nào nên rơi vào nhánh "đứng yên chờ retry ĐÚNG node cũ" (generic,
    không biết gì về node thay thế) — dù node thay thế rất có thể ĐÃ TRỐNG vào
    đúng lúc retry (xe khác đã lấy/trả hàng xong, rời node). Trả về node thay
    thế nếu có; None nếu dest_node không phải supply node (không có
    supply_group) hoặc không có node tương đương nào khác trống hơn.
    """
    try:
        node_actions = map_manager.node_actions
    except Exception:
        return None
    cfg = node_actions.get(str(dest_node)) or {}
    if str(cfg.get('arrival_action') or '').lower() != 'wait_sys':
        return None
    sg = cfg.get('supply_group') or []
    if isinstance(sg, str):
        sg = [s.strip() for s in sg.split(',')]
    sg = [str(s) for s in sg if str(s).strip()]
    if not sg:
        return None
    candidates: list[str] = []
    for snid, sncfg in (node_actions or {}).items():
        sncfg = sncfg or {}
        if str(sncfg.get('arrival_action', '') or '').lower() != 'wait_sys':
            continue
        osg = sncfg.get('supply_group') or []
        if isinstance(osg, str):
            osg = [s.strip() for s in osg.split(',')]
        if any(str(s) in sg for s in osg):
            candidates.append(str(snid))
    if len(candidates) <= 1:
        return None
    return _nearest_of(candidates, current_node, exclude_agv=agv_id)


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


# Rơ-moóc (xe 1 chiều tiến) TIẾN vào trạm sạc ngõ cụt nên mũi xe quay VÀO trong; khi có việc phải
# LÙI mù một đoạn rồi QUAY đầu để đổi mũi ra ngoài (kịch bản exit_reverse_ms/exit_turn của trạm).
# Trạm sạc ngõ cụt chưa cấu hình kịch bản này → dùng mặc định theo đúng quy ước vận hành:
# lùi 3 giây rồi quay. Cấu hình RIÊNG của trạm (nếu có) luôn được ưu tiên hơn mặc định.
TRAILER_EXIT_REVERSE_MS_DEFAULT = 3000
TRAILER_EXIT_TURN_DEFAULT = "left"


def _with_trailer_exit_defaults(agv_id: str, node_id: str, cfg: dict) -> dict:
    """Trả bản sao cfg của node; nếu node là TRẠM SẠC NGÕ CỤT, xe là rơ-moóc và trạm chưa khai
    exit_reverse_ms/exit_turn thì bổ sung mặc định (lùi 3s + quay). Mọi trường hợp khác giữ nguyên."""
    from agv_registry import agv_registry as _reg_ex
    cfg = dict(cfg or {})
    try:
        if cfg.get("exit_reverse_ms") and str(cfg.get("exit_turn") or "").lower() in ("left", "right"):
            return cfg
        if str(_reg_ex.get_config(agv_id).get("agv_type") or "").lower() != "trailer":
            return cfg
        if not (str(cfg.get("locationType", "")).upper() == "CHARGER"
                or str(cfg.get("arrival_action", "")).lower() == "wait_charge"):
            return cfg
        g = getattr(map_manager, "_line_graph_base", None) or getattr(map_manager, "_graph_base", None)
        nid = str(node_id)
        if g is None or nid not in g:
            return cfg
        nbrs = set(g.successors(nid)) | set(g.predecessors(nid)) if g.is_directed() else set(g.neighbors(nid))
        if len(nbrs) <= 1:   # ngõ cụt thật sự
            cfg.setdefault("exit_reverse_ms", TRAILER_EXIT_REVERSE_MS_DEFAULT)
            if str(cfg.get("exit_turn") or "").lower() not in ("left", "right"):
                cfg["exit_turn"] = TRAILER_EXIT_TURN_DEFAULT
    except Exception:
        pass
    return cfg


def _trailer_turnaround_charger(agv_id: str, cur: str, prev: str | None) -> str | None:
    """Xe KHÔNG lùi được kẹt trong nhánh cụt (lối ra duy nhất là quay lại đúng node vừa tới) → tìm
    TRẠM SẠC mà xe đi TIẾN tới được (không quay lại prev) để dùng làm chỗ QUAY ĐẦU: tiến vào trạm
    rồi, khi có việc, lùi mù + quay đầu ra (kịch bản thoát trạm). Chỉ chọn trạm xe được phép vào,
    đang trống, đúng loại xe. Phải gọi trong phạm vi agv_scope của xe (đồ thị đã lọc vùng cấm)."""
    import networkx as _nx_ta
    from line_agv_handler import (line_agv_handler as _lah_ta, _charger_siding_ok as _cso_ta,
                                  _nodes_busy_for as _nbf_ta)
    g = map_manager.line_graph
    if g is None or cur not in g:
        return None
    g2 = g.copy()
    for a, b in ((cur, prev), (prev, cur)):
        if a and b and g2.has_edge(a, b):
            g2.remove_edge(a, b)
    busy = _nbf_ta(agv_id, _lah_ta)
    best = None
    for ch in map_manager.charger_nodes():
        if ch == cur or ch not in g2 or not _cso_ta(agv_id, ch, busy):
            continue
        try:
            path = _nx_ta.shortest_path(g2, cur, ch, weight="weight")
        except Exception:
            continue
        if best is None or len(path) < len(best[1]):
            best = (ch, path)
    return best[0] if best else None


def _td_json(v):
    """Chuẩn hoá hướng riêng theo loại xe từ payload Map Editor → chuỗi JSON lưu DB (hoặc None).
    Chỉ nhận loại xe carry|tow|trailer và hướng forward|backward|blocked (CHỈ hạn chế thêm)."""
    import json as _j_td
    if isinstance(v, str):
        try:
            v = _j_td.loads(v)
        except Exception:
            return None
    if not isinstance(v, dict):
        return None
    clean = {str(k).lower(): str(val).lower() for k, val in v.items()
             if str(k).lower() in ("carry", "tow", "trailer")
             and str(val).lower() in ("forward", "backward", "blocked")}
    return _j_td.dumps(clean) if clean else None


def _in_agv_scope(fn):
    """Chạy hàm (agv_id, ...) trong VÙNG HOẠT ĐỘNG của xe — xem MapManager.agv_scope."""
    import functools as _ft

    @_ft.wraps(fn)
    def _w(agv_id, *a, **k):
        from mqtt_client import map_manager as _mm_sc
        with _mm_sc.agv_scope(agv_id):
            return fn(agv_id, *a, **k)
    return _w


# Chờ đích bị xe KHÁC đứng yên chiếm: sau EVICT giây mà xe chiếm đang rảnh (không lệnh nào) → đuổi nó
# đi (về sạc/đỗ) để nhả đích; sau ABANDON giây vẫn chưa trống → bỏ lệnh này để xe nhận việc khác
# (không chờ vô hạn). {agv_id: (dest, mốc bắt đầu chờ, đã_đuổi)}
DEST_WAIT_EVICT_SEC   = 90.0
DEST_WAIT_ABANDON_SEC = 240.0
_DEST_WAIT_SINCE: dict = {}
_EMPTY_STAGING_REDIRECTING: set = set()   # xe đang chuyển sang điểm lấy rỗng tương đương (chống đệ quy)
# Xe vừa LÙI tới node (last_transit_direction='bwd') mà lệnh kế tiếp quay lại đúng node vừa đến: mũi xe đang hướng về node đó
# nên phải TIẾN (không lùi tiếp — lùi tiếp đẩy xe ra phía ngược lại / cuối đường). Đặt False để quay lại hành vi cũ ("lùi tiếp").
# PHÁT HIỆN THỰC TẾ (2026-11-20, xe thật): 7 lần liên tiếp xe chạy ngược chiều lệnh sau khi bấm xác nhận ở node vừa lùi tới
# (14→15, 15→35, 34→33, 33→13…). Lưu ý ghi chú cũ 2026-10-01 (AGV04 node 21): ép fwd từng làm xe rẽ lệch — nếu tái diễn thì tắt cờ này.
RETRACE_FWD_AFTER_BWD_ARRIVAL = True


@_in_agv_scope
def _start_ride_chain(agv_id: str, steps: list, session_id: str | None = None) -> bool:
    """Chạy chuỗi đi thang do floor_nav.decompose() sinh ra: các bước SAU xếp ở ĐẦU hàng đợi theo đúng thứ tự,
    bước ĐẦU chạy ngay trong lệnh đang chạy (đặt thang hoặc đi tới node chờ). Lệnh đang chạy hoàn tất khi bước đầu
    xong (đặt thang được cấp / xe tới node chờ) rồi hàng đợi tự chạy tiếp."""
    import floor_nav as _fn_rc
    from task_queue import agv_task_queue as _atq_rc
    _last_i = len(steps) - 1
    for _i, (_c, _a) in reversed(list(enumerate(steps))[1:]):
        _cmd_rc = _atq_rc.insert_next(agv_id, _c, dest_node=_a)
        # go_to cuối chuỗi = ĐÍCH THẬT của lượt (xe phải dừng chờ xác nhận); các go_to trước nó chỉ là chặng trung gian
        _atq_rc.mark_chain_leg(_cmd_rc, (_c == "go_to" and _i != _last_i))
    first_cmd, first_arg = steps[0]
    if first_cmd == _fn_rc.CMD_ELEV_BOOK:
        from elevator_coordinator import elevator_coordinator as _ec_rc
        _eid, _fid = _fn_rc.parse_call(first_arg)
        return bool(_ec_rc.book(_eid, _fid, agv_id))
    return bool(_dispatch_go_to(agv_id, first_arg, session_id=session_id))


@_in_agv_scope
def _dispatch_go_to(agv_id: str, dest_node: str, start_node: str | None = None,
                    session_id: str | None = None) -> bool:
    """Tính đường + gửi order (LINE hoặc VDA5050) từ vị trí hiện tại đến dest_node.

    session_id: lượt cấp hàng hiện tại — dùng để chỉ lấy hàng MỘT lần mỗi supply
    node trong một lượt. Các lệnh giao hàng sau trong cùng session sẽ đi một mạch
    qua supply node đã lấy mà không dừng lại chờ xác nhận.
    """
    global _pending_staging_transits
    from mqtt_client import (
        get_agv_runtime_info, plan_path_for_order,
        send_agv_to_special_target, send_order,
    )
    from agv_registry import agv_registry
    # VÙNG CẤM: đích xe này không được vào → báo lỗi NGAY, TRƯỚC khi vào nhánh "đích đang bận
    # → chờ rồi thử lại" (pending_retry). Nếu để lọt vào đó, lệnh sẽ bị thử lại mãi mãi mỗi khi
    # có xe khác di chuyển nhưng lần nào cũng bị từ chối (đúng lỗi SIM03 rơ-moóc không nhúc nhích).
    if not map_manager.is_node_allowed(agv_id, dest_node):
        raise ValueError(
            f"Node {dest_node} nằm trong VÙNG CẤM của loại xe "
            f"'{agv_registry.get_config(agv_id).get('agv_type')}' (xe {agv_id}) — không thể điều xe tới đó")
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

    # ── ĐÍCH KHÁC TẦNG → chuỗi đi thang máy (xem floor_nav.py) ───────────────────
    # Tách thành: go_to node-chờ-trước-cabin → gọi thang → vào cabin → đi thang → ra → nhả thang → go_to đích.
    # Bước đầu chạy ngay (đệ quy, cùng tầng nên không lặp lại nhánh này); các bước sau xếp ở ĐẦU hàng đợi
    # theo đúng thứ tự (giống cách tách route tại node trung gian bên dưới).
    if agv_registry.is_line(agv_id):
        import floor_nav as _fn_fl
        # Bản đồ có thể CHƯA được nạp vào MapManager (lần dispatch đầu sau khi khởi động — plan_path nạp
        # lười ở phía dưới) → nạp trước để biết tầng/thang. Có cache nên gọi lại gần như không tốn gì.
        try:
            from mqtt_client import ensure_map_loaded_sync as _eml_fl
            _eml_fl(str(agv_registry.get_map_id(agv_id) or ""))
        except Exception as _e_eml:
            print(f"[ELEVATOR] nạp bản đồ trước khi kiểm tra tầng lỗi: {_e_eml}")
        # Cabin DÙNG CHUNG thuộc mọi tầng thang dừng (node chỉ lưu floor_id của 1 tầng) → đi tới cabin là cùng tầng,
        # không dựng chuỗi thang: bước "go_to cabin" của chính chuỗi đi thang từ tầng khác tầng lưu của cabin
        # (vd xe ở tầng 3, cabin lưu F1) bị coi là khác tầng → decompose lỗi "Node cabin trùng mục tiêu".
        if (_fn_fl.multi_floor(map_manager)
                and not _fn_fl.is_shared_cabin(dest_node, map_manager)
                and _fn_fl.floor_of(current_node, map_manager) != _fn_fl.floor_of(dest_node, map_manager)):
            from task_queue import agv_task_queue as _atq_fl
            # decompose() tự từ chối (ValueError) xe không ra được cabin: cabin 1 cửa bắt xe lùi ra nên xe không lùi/quay
            # được (rơ-moóc/xe kéo) chỉ đi được thang có cửa ra ĐỐI DIỆN cửa vào (khai báo cạnh cửa trong Map Editor)
            _steps_fl = _fn_fl.decompose(agv_id, str(current_node), str(dest_node), map_manager)
            print(f"[ELEVATOR] {agv_id}: đích {dest_node} khác tầng với {current_node} → chuỗi đi thang: "
                  f"{' → '.join(f'{c}:{a}' for c, a in _steps_fl)}")
            return _start_ride_chain(agv_id, _steps_fl, session_id)

    _is_staging_dispatch = False   # sẽ được set True nếu staging redirect xảy ra

    # PHÁT HIỆN THỰC TẾ (2026-09-28): task_lifecycle='charging' được set khi AGV
    # vào trạm sạc, nhưng KHÔNG có chỗ nào xóa khi rời trạm sạc — cờ nằm lại
    # suốt chặng transit đầu tiên sau khi rời. Hàm này đọc cờ đó ở nhiều chỗ bên
    # dưới CHỈ để biết "vừa rời trạm sạc → tính hướng kiểu nào", đọc 1 lần rồi
    # phải xóa ngay (giống hệt last_transit_direction) — nếu không, khi xe sau
    # đó chạy lệch khỏi route đã lập (tag lạ ngoài full_path — lỗi firmware
    # thật), cơ chế off_route (line_agv_handler.py dòng ~2110, điều kiện
    # `not state.task_lifecycle`) bị cờ 'charging' còn sót chặn mất hoàn toàn,
    # xe đứng im vô thời hạn không ai cứu (đúng log thực tế: AGV03 rời trạm 1 →
    # lệch qua node 12 → kẹt >8 phút không 1 dòng log, tới khi bị hủy lệnh thủ
    # công). Capture 1 lần duy nhất ở đây, dùng lại cho mọi nhánh bên dưới.
    _was_leaving_charger = False
    if agv_registry.is_line(agv_id):
        from line_agv_handler import line_agv_handler as _lah_lc
        _st_lc = _lah_lc.state_store.get(agv_id)
        if _st_lc and _st_lc.task_lifecycle == "charging":
            _was_leaving_charger = True
            _st_lc.task_lifecycle = None

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
        if not _claimer:
            _DEST_WAIT_SINCE.pop(agv_id, None)
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
                _abandon_dw = False
                try:
                    _now_dw = time.monotonic()
                    _dw = _DEST_WAIT_SINCE.get(agv_id)
                    if not _dw or _dw[0] != str(dest_node):
                        _dw = [str(dest_node), _now_dw, False]
                        _DEST_WAIT_SINCE[agv_id] = _dw
                    _waited_dw = _now_dw - _dw[1]
                    from task_queue import agv_task_queue as _atq_dw, CMD_GO_CHARGE as _CGC_dw
                    if (_waited_dw >= DEST_WAIT_EVICT_SEC and not _dw[2]
                            and _atq_dw.get_running(_claimer) is None
                            and _atq_dw.queue_size(_claimer) == 0):
                        _dw[2] = True
                        print(f"[DISPATCH] {agv_id}: chờ đích {dest_node} đã {_waited_dw:.0f}s, "
                              f"{_claimer} đang rảnh → ĐUỔI {_claimer} đi (về sạc) để nhả đích")
                        _atq_dw.dispatch_or_queue(_claimer, _CGC_dw, session_id=None)
                    elif _waited_dw >= DEST_WAIT_ABANDON_SEC:
                        _abandon_dw = True
                except Exception as _e_dw:
                    print(f"[DISPATCH] {agv_id}: xử lý chờ đích lâu lỗi: {_e_dw}")
                if _abandon_dw:
                    print(f"[DISPATCH] {agv_id}: chờ đích {dest_node} quá {DEST_WAIT_ABANDON_SEC:.0f}s "
                          f"(bị {_claimer} chiếm) → BỎ lệnh này, nhận việc khác")
                    _DEST_WAIT_SINCE.pop(agv_id, None)
                    try:
                        from line_agv_handler import line_agv_handler as _lah_ab
                        _st_ab = _lah_ab.state_store.get(agv_id)
                        if _st_ab:
                            _st_ab.pending_retry_cmd     = None
                            _st_ab.pending_retry_dest    = None
                            _st_ab.pending_retry_session = None
                        from task_queue import agv_task_queue as _atq_ab
                        _atq_ab.on_agv_completed(agv_id, notes='dest_blocked_timeout')
                    except Exception as _e_ab:
                        print(f"[DISPATCH] {agv_id}: bỏ lệnh lỗi: {_e_ab}")
                    return True
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
                # CHỈ suy luận bằng hình học tâm-node tại NÚT GIAO THẬT (bậc cạnh
                # >= 3, vd ngã ba/ngã tư) — nơi path có thể chọn 1 hướng đối nghịch
                # hẳn với hướng xe đang tới. Tại node HÀNH LANG ĐƠN TUYẾN (bậc 2 —
                # chỉ nối đúng 2 hàng xóm, không có nhánh rẽ nào khác, vd chuỗi
                # 81-82-50 chỉ có 1 edge 2 chiều giữa mỗi cặp), đi sang hàng xóm
                # CÒN LẠI (khác prev_tag) LUÔN LÀ TIẾN TIẾP tự nhiên dọc đường ray
                # đơn — không có lựa chọn nào khác nên không thể là lùi thật, bất
                # kể đường vẽ cong bao nhiêu. Toạ độ tâm node chỉ là điểm neo hiển
                # thị, KHÔNG phải tiếp tuyến thật của đường cong (bezier) nên vector
                # thẳng nối tâm 2 node dễ suy ra góc "giả" — từng gây báo nhầm
                # "cần lùi" cho 1 đoạn hành lang cong hoàn toàn đi được (map thực tế
                # dùng đường cong theo đúng bố trí nhà máy).
                _deg_graph_cr = getattr(map_manager, "line_graph", None) or getattr(map_manager, "graph", None)
                _degree_cr = None
                try:
                    if _deg_graph_cr is not None and path[0] in _deg_graph_cr:
                        _degree_cr = _deg_graph_cr.degree(path[0])
                except Exception:
                    _degree_cr = None
                # Bảng rẽ (turn_map) của node do người dùng nhập CÓ dòng cho đúng cặp prev→next với giá
                # trị left/right/straight = cú rẽ hợp lệ đã được khai báo → KHÔNG phải lùi dù góc gắt
                # (vd 29→26→28 góc ~131° nhưng node 26 khai báo 29_28 = left). Chỉ suy luận bằng hình
                # học khi bảng rẽ không nói gì về cặp này.
                _tm_cr = ((getattr(map_manager, "node_actions", {}) or {}).get(str(path[0])) or {}).get("turn_map") or {}
                _tm_val_cr = str(_tm_cr.get(f"{_prev_cr}_{path[1]}_fwd") or "").lower()
                if _tm_val_cr in ("left", "right", "straight"):
                    pass   # rẽ đã khai báo trong bảng rẽ
                elif _degree_cr is not None and _degree_cr <= 2:
                    pass   # hành lang đơn tuyến — không cần (và không nên) suy luận hình học
                else:
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
                                    print(f"[DISPATCH] {agv_id}: phát hiện lùi qua hình học tại "
                                          f"ngã rẽ (prev={_prev_cr}→{path[0]}→{path[1]}, "
                                          f"bậc={_degree_cr}, cos={_cos_cr:.2f})")
                    except Exception:
                        pass
            if _needs_reverse_cr:
                _cur_cfg_cr   = _with_trailer_exit_defaults(
                    agv_id, str(path[0]),
                    (getattr(map_manager, "node_actions", {}) or {}).get(str(path[0])) or {})
                _approach_cr  = str(_cur_cfg_cr.get("approach_dir")   or "").lower()
                _arrival_cr   = str(_cur_cfg_cr.get("arrival_action") or "").lower()
                _lifecycle_cr = _was_leaving_charger
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
                        # PHƯƠNG ÁN CUỐI (xe 1 chiều tiến kẹt trong nhánh cụt, vd rơ-moóc giao hàng
                        # xong ở cuối nhánh): lối ra duy nhất là quay lại đúng node vừa tới = phải
                        # lùi. Thay vì bỏ lệnh và đứng im vĩnh viễn, cho xe TIẾN vào TRẠM SẠC ngõ
                        # cụt gần đó để quay đầu (ra khỏi trạm bằng lùi mù + quay), rồi đi tiếp
                        # đích gốc — đúng cách vận hành rơ-moóc.
                        try:
                            _ta_ch = _trailer_turnaround_charger(agv_id, str(path[0]), _prev_cr)
                        except Exception as _e_ta:
                            _ta_ch = None
                            print(f"[DISPATCH] {agv_id}: tìm trạm quay đầu lỗi: {_e_ta}")
                        if _ta_ch:
                            print(f"[DISPATCH] {agv_id}: kẹt trong nhánh cụt (không lùi được) → "
                                  f"đi TIẾN vào trạm sạc {_ta_ch} để quay đầu, sau đó đi tiếp {dest_node}")
                            from task_queue import agv_task_queue as _atq_ta, CMD_GO_TO as _CGT_ta
                            _pending_staging_transits.add((agv_id, str(_ta_ch)))
                            _atq_ta.insert_next(agv_id, _CGT_ta, dest_node=str(dest_node))
                            _atq_ta.on_agv_completed(agv_id, notes='trailer_turnaround',
                                                     auto_dispatch=False)
                            return _dispatch_go_to(agv_id, str(_ta_ch), session_id=session_id)
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
            # PHÁT HIỆN THỰC TẾ (2026-09-24): các nhánh đỗ-né head-on dưới đây đều
            # `insert_next(dest_node=str(dest_node))` để "quay lại đích sau khi né" —
            # ĐÚNG khi lệnh dispatch NÀY là lệnh nghiệp vụ THẬT (dest_node = đích giao/
            # lấy hàng thật). NHƯNG khi hàm này được gọi LỒNG BÊN TRONG 1 lượt đỗ-né
            # siding đã đang chạy (`_yield_to_siding` ở line_agv_handler.py — state.
            # yield_cmd đang set, đích THẬT đã lưu riêng ở state.yield_dest), dest_node
            # ở đây chỉ là NODE SIDING TẠM (nội bộ), không phải đích nghiệp vụ. Vẫn
            # insert_next(dest_node=siding tạm) sẽ để lại 1 lệnh "mồ côi" trong hàng
            # đợi — khi cơ chế resume-yield (line_agv_handler._check_waiting_agvs)
            # phát hiện winner đã rời và nhảy thẳng resume tới yield_dest (bỏ qua hàng
            # đợi), lệnh mồ côi này KHÔNG bị dọn, nằm chờ tới lượt rồi bị dequeue nhầm
            # như 1 điểm giao/lấy hàng thật (đúng log thực tế: AGV04 sau khi giao ở
            # 106 xong lại bị điều tới đúng node siding tạm cũ và HẠ MÓC nhầm ở đó).
            # Khi đang lồng trong yield (yield_cmd đã set) → BỎ QUA insert_next ở các
            # nhánh dưới; việc quay về đích thật đã được `_check_waiting_agvs` đảm nhiệm
            # qua yield_dest, không cần (và không nên) thêm entry vào hàng đợi chung.
            _in_nested_yield_ho = bool(_lstate_ho and getattr(_lstate_ho, 'yield_cmd', None))

            # Dùng last_plan_direction làm hướng transit, nhưng nếu đang ở CHARGER
            # thì phải dùng 'fwd' (ra khỏi trạm phải tiến, không phải lùi thêm).
            # Tổng quát: mọi trạm sạc đều không có đường phía sau.
            _ho_dir_raw = (getattr(_lstate_ho, 'last_plan_direction', 'fwd') or 'fwd') if _lstate_ho else 'fwd'
            # Kiểm tra lifecycle charging thêm ngoài locationType
            if _was_leaving_charger:
                _ho_dir_raw = 'fwd'
            # Backward-start: nếu path[1] CHÍNH LÀ prev_tag (route mới đi NGƯỢC lại
            # đúng cạnh xe vừa đi qua để tới node hiện tại) → BẮT BUỘC lùi ra trước,
            # giống hệt điều kiện đã dùng ở nhánh dispatch chính phía trên (khối
            # "backward start"). THIẾU check này khiến nhánh đỗ-né head-on gửi TIẾN
            # khi lẽ ra phải LÙI — xe đi thẳng vào chỗ không có đường (vd rời điểm
            # thả hàng rỗng bằng tiến thay vì lùi ra đúng lối vừa vào).
            if (_lstate_ho is not None and getattr(_lstate_ho, 'prev_tag', None) is not None
                    and path and len(path) >= 2 and str(path[1]) == str(_lstate_ho.prev_tag)):
                try:
                    if agv_registry.can_reverse(agv_id):
                        _ho_dir_raw = 'bwd'
                except Exception:
                    pass
            from line_agv_handler import _charger_exit_direction as _ced
            _ho_dir = _ced(_cur_tag_ho or '', _ho_dir_raw)

            # Thử tìm nhánh phụ (parking node) để tránh ra không cản đường chính.
            # CHỐNG DAO ĐỘNG (2026-09-23): nếu vừa đỗ-né HEAD-ON với ĐÚNG xe này
            # trong PARKING_COOLDOWN giây → bỏ qua đỗ-né tiếp (rơi xuống dừng-chờ
            # tại chỗ bên dưới), tránh xe bị dispatch đi tới lui giữa 2 node đỗ-né
            # sát nhau mỗi khi xe kia vẫn chưa kịp rời (gốc log: AGV03 bị đẩy đi
            # 106↔31 liên tục 3 lần trong ~4s rồi đứng im hẳn không phản hồi).
            from line_agv_handler import PARKING_COOLDOWN as _PARKING_COOLDOWN_HO
            _park_ts_ho = _tc_dispatch._parking_ts.get(agv_id)
            # PHÁT HIỆN THỰC TẾ (2026-10-02): cooldown này TRƯỚC ĐÂY chỉ canh gác
            # nhánh "_parking" (find_parking_node) — nhánh "safe_wait" (dừng tại node
            # cuối trước conflict, ~line 3816) và nhánh "side_node" (đỗ tại hàng xóm
            # của vị trí hiện tại, ~line 3844) hoàn toàn KHÔNG bị cooldown chặn, nên
            # mỗi lần dispatch head-on được gọi lại (off_route/retry lặp lại khi vẫn
            # còn xung đột) có thể rơi vào MỘT NHÁNH KHÁC mỗi lần (vd lần này safe_wait
            # chọn được node, lần sau safe_wait bị future-path xe kia chặn → rơi xuống
            # side_node) → xe bị dispatch nảy qua nảy lại giữa 2 điểm đỗ khác nhau mỗi
            # vài giây, dù xung đột với CHÍNH xe đó chưa hề thay đổi (đúng log thực tế:
            # AGV04 nảy 7↔2↔7↔11 với AGV01 trong 6 giây). Mở rộng cooldown ra chắn CẢ
            # 3 nhánh — hễ vừa né xe này xong (bất kể né bằng cách nào) thì trong
            # PARKING_COOLDOWN giây tiếp theo KHÔNG né lại nữa, chỉ đứng yên chờ.
            _cooldown_active_ho = bool(
                _park_ts_ho and _park_ts_ho[1] == _ho_other
                and time.monotonic() - _park_ts_ho[0] < _PARKING_COOLDOWN_HO
            )
            if _cooldown_active_ho:
                print(f"[DISPATCH] {agv_id}: vừa đỗ-né HEAD-ON với {_ho_other} "
                      f"< {_PARKING_COOLDOWN_HO:.0f}s → KHÔNG đỗ-né tiếp (chống dao "
                      f"động), dừng chờ tại chỗ cho tới khi xe kia rời hẳn")
                _parking = None
            else:
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
                _tc_dispatch._parking_ts[agv_id] = (time.monotonic(), _ho_other)
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
                if not _in_nested_yield_ho:
                    from task_queue import agv_task_queue as _atq_ho, CMD_GO_TO as _CGT_ho
                    if _is_staging_dispatch:
                        # dest_node ở đây là node STAGING tạm (đích thật đã bị chiếm, xem
                        # block "dest ... occupied" phía trên), KHÔNG phải điểm lấy/thả hàng
                        # thật — đánh dấu để dispatch kế tiếp tới đây dùng task=transit (xem
                        # _pending_staging_transits ở dispatch_go_to). Thiếu dấu này, lệnh
                        # go_to re-queue bên dưới sẽ bị coi là 'delivery' bình thường khi
                        # dispatch lại, khiến arrival tại node staging bị hiểu nhầm là "tới
                        # nơi, nhả hàng" → gửi hạ móc SAI chỗ (lỗi thực tế: AGV hạ móc tại
                        # node staging thay vì đích thật).
                        _pending_staging_transits.add((agv_id, str(dest_node)))
                    _atq_ho.insert_next(agv_id, _CGT_ho, dest_node=str(dest_node))
                else:
                    print(f"[DISPATCH] {agv_id}: đang lồng trong yield-siding (đích thật="
                          f"{_lstate_ho.yield_dest}) → KHÔNG queue thêm resume tới node "
                          f"tạm {dest_node} (tránh rác hàng đợi)")
                return True

            # Không có nhánh phụ: dừng tại node cuối trước conflict trên đường chính.
            # Quan trọng: safe_wait node KHÔNG được nằm trong future path của xe kia
            # (nếu nằm trong đó thì sẽ gây conflict mới tại chính safe_wait node đó)
            _safe_wait = None if _cooldown_active_ho else _tc_dispatch.find_safe_wait_node(path, _ho_idx)
            _other_reg_sw  = _tc_dispatch._registered.get(_ho_other, {})
            _other_fut_sw  = set(_other_reg_sw.get('path', [])[_other_reg_sw.get('current_idx', 0):])
            if _safe_wait and _safe_wait != path[0] and _safe_wait != path[-1] \
                    and _safe_wait != _cur_tag_ho \
                    and _safe_wait not in _other_fut_sw:
                _tc_dispatch._parking_ts[agv_id] = (time.monotonic(), _ho_other)
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
                if not _in_nested_yield_ho:
                    from task_queue import agv_task_queue as _atq_ho2, CMD_GO_TO as _CGT_ho2
                    if _is_staging_dispatch:
                        # Xem comment ở nhánh "đỗ tại _park_node" phía trên — dest_node ở
                        # đây cũng chỉ là node staging tạm, không phải đích thật.
                        _pending_staging_transits.add((agv_id, str(dest_node)))
                    _atq_ho2.insert_next(agv_id, _CGT_ho2, dest_node=str(dest_node))
                else:
                    print(f"[DISPATCH] {agv_id}: đang lồng trong yield-siding (đích thật="
                          f"{_lstate_ho.yield_dest}) → KHÔNG queue thêm resume tới node "
                          f"tạm {dest_node} (tránh rác hàng đợi)")
                return True

            # Không tìm được parking/safe_wait → thử tìm side node của vị trí hiện tại
            # (conflict_idx=0 nghĩa là xe đang đứng ngay tại điểm xung đột)
            _side_found = False
            if _cur_tag_ho and not _cooldown_active_ho:
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
                            _tc_dispatch._parking_ts[agv_id] = (time.monotonic(), _ho_other)
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
                            if not _in_nested_yield_ho:
                                from task_queue import agv_task_queue as _atq_side, CMD_GO_TO as _CGT_side
                                if _is_staging_dispatch:
                                    # Xem comment ở nhánh "đỗ tại _park_node" phía trên —
                                    # dest_node ở đây cũng chỉ là node staging tạm.
                                    _pending_staging_transits.add((agv_id, str(dest_node)))
                                _atq_side.insert_next(agv_id, _CGT_side, dest_node=str(dest_node))
                            else:
                                print(f"[DISPATCH] {agv_id}: đang lồng trong yield-siding "
                                      f"(đích thật={_lstate_ho.yield_dest}) → KHÔNG queue "
                                      f"thêm resume tới node tạm {dest_node} (tránh rác hàng đợi)")
                            _side_found = True
                except Exception as _se:
                    print(f"[DISPATCH] {agv_id}: side-node fallback error: {_se}")

            if not _side_found:
                # PHÁT HIỆN THỰC TẾ (2026-09-21): trước đây chỉ insert_next() rồi return
                # True — KHÔNG hề gọi set_route()/register() (không có nhánh phụ để đi)
                # và KHÔNG giải phóng _running trong task_queue → AGV đứng yên VĨNH VIỄN,
                # không có gì (không route, không pending_retry) để bất kỳ cơ chế nào
                # (bao gồm _check_waiting_agvs — chỉ quét _routes hoặc pending_retry_cmd)
                # quay lại đánh thức khi xe kia đã đi qua xong (đúng lỗi thực tế: AGV03
                # đứng im ở 103 dù AGV01 đã đi hết đoạn xung đột từ lâu, không báo lỗi).
                # Sửa theo ĐÚNG mẫu đã dùng cho "dest bị chiếm" (_st_dw/_st_csw ở trên):
                # giải phóng _running (auto_dispatch=False, không tự chạy lệnh kế tiếp
                # trong queue) + đặt pending_retry_cmd để _check_waiting_agvs() tự kích
                # lại go_to này ngay khi có xe khác đổi tag (thường là xe đang chặn vừa
                # nhúc nhích qua node xung đột).
                print(f"[DISPATCH] {agv_id}: HEAD-ON với {_ho_other} — "
                      f"không có side node, dừng tại {_cur_tag_ho} chờ xe kia clear")
                try:
                    _st_ho_wait = line_agv_handler.state_store.get(agv_id)
                    if _st_ho_wait:
                        _st_ho_wait.pending_retry_cmd     = 'go_to'
                        _st_ho_wait.pending_retry_dest    = str(dest_node)
                        _st_ho_wait.pending_retry_session = session_id
                    from task_queue import agv_task_queue as _atq_wait
                    _atq_wait.on_agv_completed(agv_id, notes='headon_no_side_wait',
                                               auto_dispatch=False)
                except Exception as _e_ho_wait:
                    print(f"[DISPATCH] {agv_id}: head-on no-side-node wait setup error: "
                          f"{_e_ho_wait}")
                    from task_queue import agv_task_queue as _atq_wait2, CMD_GO_TO as _CGT_wait2
                    _atq_wait2.insert_next(agv_id, _CGT_wait2, dest_node=str(dest_node))
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
            _cur_node_cfg    = _with_trailer_exit_defaults(
                agv_id, str(path[0]), node_actions.get(str(path[0])) or {})
            _cur_approach    = str(_cur_node_cfg.get("approach_dir")    or "").lower()
            _cur_arrival     = str(_cur_node_cfg.get("arrival_action")  or "").lower()
            _lifecycle_chg   = _was_leaving_charger
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
            # PHÁT HIỆN THỰC TẾ (2026-10-02): node CỤT THẬT (degree<2 trên đồ thị —
            # chỉ 1 cạnh nối, vd 104/105/106) mà KHÔNG được gắn approach_dir=bwd (vì
            # việc xe lùi tới đó là do PATHFINDER chọn lùi ở đoạn cuối, không phải do
            # cấu hình tay node) vẫn phải coi như "đã lùi vào, mũi xe hướng ra" y hệt
            # charger — vì node cụt chỉ có đúng 1 hướng vật lý để đi tiếp (ra ngoài),
            # không có "lùi tiếp" nào khác ngoài lùi xuyên qua tận cùng đường (ra khỏi
            # map). Thiếu check này khiến AGV03 lùi vào 104 thả hàng rỗng xong, dispatch
            # kế lại tiếp tục lùi (rơi vào nhánh "cần lùi thật" dưới) → lùi xuyên qua
            # hết node 104 ra ngoài map. Cùng quy tắc degree-based đã dùng đúng ở
            # resolve_departure_direction() (line_agv_handler.py) — tổng quát hoá vào
            # đây để nhánh dispatch chính không còn thiếu trường hợp này.
            #
            # PHÁT HIỆN THỰC TẾ (2026-10-02, bổ sung): bản sửa trên ONLY đúng khi xe
            # ĐÃ LÙI vào node cụt (mũi hướng ra, giống charger). Nếu xe TIẾN vào node
            # cụt (mũi hướng VÀO, vd AGV01 tiến 30→105, AGV03 tiến 28→104) thì
            # _is_dead_end=True vẫn bị OR thẳng vào _at_charge_bwd → nhánh "skip
            # transit, dùng fwd" chạy SAI, đẩy xe tiến tiếp xuyên qua node cụt ra khỏi
            # map (đúng log thực tế: AGV01 "105→98 direction=fwd (last_tdir='fwd')",
            # AGV03 "104→103 direction=fwd (last_tdir='')" — cả 2 đều vừa TIẾN vào,
            # không phải lùi vào). Phải phân biệt theo CHIỀU VỪA DÙNG ĐỂ TỚI đó
            # (_last_tdir_bwd, đọc TRƯỚC khi bị clear): chỉ coi "mũi đã hướng ra" khi
            # chặng vừa xong là 'bwd'; nếu là 'fwd' (hoặc không rõ) → mũi đang hướng
            # VÀO tận cùng, phải rơi xuống nhánh dưới (cần lùi thật) để lùi đúng ra lại.
            _is_dead_end = False
            try:
                _g_de = map_manager.line_graph if map_manager.line_graph else map_manager.graph
                if _g_de is not None and _g_de.has_node(str(path[0])):
                    # QUAN TRỌNG (phát hiện thực tế 2026-10-02): graph ở đây LUÔN là
                    # DiGraph (map_manager.py:73 "DiGraph để pathfinding tôn trọng
                    # chiều đi") — 1 cạnh 2 chiều (move_direction=0, đa số cạnh) được
                    # add CẢ 2 hướng (src→dst VÀ dst→src), nên .degree() cộng CẢ 2
                    # chiều: 1 node cụt thật (chỉ 1 hàng xóm) báo degree=2, không phải
                    # 1 — khiến check "degree<2" phía trên KHÔNG BAO GIỜ đúng, vô hiệu
                    # hoàn toàn bản sửa "node cụt phải đổi chiều" (đúng lỗi thực tế:
                    # AGV03 lùi vào 103 xong, bấm xác nhận xong vẫn tiếp tục lùi ra
                    # khỏi map, dù 103 là node cụt). Sửa: đếm số HÀNG XÓM KHÁC NHAU
                    # thật (không phân biệt chiều cạnh) thay vì cộng degree.
                    if _g_de.is_directed():
                        _n_neighbors_de = len(set(_g_de.successors(str(path[0])))
                                               | set(_g_de.predecessors(str(path[0]))))
                    else:
                        _n_neighbors_de = len(set(_g_de.neighbors(str(path[0]))))
                    _is_dead_end = _n_neighbors_de < 2
            except Exception:
                pass
            _at_charge_bwd   = (_cur_approach == "bwd") or (_cur_arrival == "wait_charge") \
                                or _is_charger_node(_cur_node_cfg) \
                                or _lifecycle_chg or _has_exit_maneuver_chg \
                                or (_is_dead_end and _last_tdir_bwd == 'bwd')
            # PHÁT HIỆN THỰC TẾ (2026-10-01): điều kiện TRƯỚC ĐÂY là
            # `_last_tdir_bwd == "bwd" or _at_charge_bwd` — ép sang "fwd" bất kỳ khi
            # nào chặng lùi VỪA XONG là 'bwd', KỂ CẢ khi node hiện tại KHÔNG phải
            # trạm sạc/điểm cần lùi ra (_at_charge_bwd=False). Điều này ngược hẳn với
            # đúng 3 trường hợp đã ghi trong comment ở trên (pingpong KHÔNG phải trạm
            # sạc phải "lùi đúng ✓", chỉ trạm sạc mới "chuyển fwd ✓") — cùng tiền đề
            # sai đã rút lại ở _cur_needs_bwd_exit (main.py._dispatch_go_to) và ở
            # _try_line_reroute (line_agv_handler.py): mũi xe không tự đổi hướng chỉ
            # vì chặng trước là lùi, nó chỉ đổi khi THỰC SỰ có cú rẽ vật lý (ở đây là
            # lùi-vào/lùi-ra trạm sạc — rẽ thật). Đúng log thực tế: AGV04 lùi 21→19
            # (tránh head-on, không phải trạm sạc), dispatch kế path=['19','21',...]
            # bị ép direction=fwd + rẽ tại 21 → mũi xe lệch hướng thật, phải can
            # thiệp thủ công. Sửa: CHỈ ép fwd khi thực sự _at_charge_bwd; pingpong
            # không-phải-trạm-sạc rơi xuống nhánh else (tiếp tục lùi, đúng comment).
            _retrace_fwd = (RETRACE_FWD_AFTER_BWD_ARRIVAL and not _at_charge_bwd and _last_tdir_bwd == 'bwd')
            if _at_charge_bwd or _retrace_fwd:
                # AGV vừa lùi vào (server-route hoặc thủ công) — front đang hướng ra đường chính.
                # path[1]==prev_tag chỉ nghĩa là route đi qua node đó theo chiều TIẾN.
                # Không cần transit lùi, chuyển sang tiến (direction="fwd").
                # _retrace_fwd: xe vừa LÙI tới node này từ prev_tag ⇒ mũi xe hướng về prev_tag ⇒ quay lại prev_tag là TIẾN.
                if _lstate:
                    _lstate.last_transit_direction = ''
                print(f"[DISPATCH] {agv_id}: post-backward route → skip transit, dùng direction=fwd"
                      f" (reason: last_tdir={_last_tdir_bwd!r} at_charge_bwd={_at_charge_bwd} retrace_fwd={_retrace_fwd})")
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
            if _required_supply_node(node_actions, dest_node, agv_id, path[0]):
                _batch_dests.append(str(dest_node))
            for _bd in _batch_dests:
                _bs = _required_supply_node(node_actions, _bd, agv_id, path[0])
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
        # AGV kéo ('tow') chạy CHUNG cơ chế này — nhưng hook_state mốc "đã có hàng"
        # ĐẢO NGƯỢC so với rơ-moóc (xem line_agv_handler._is_tow_agv): rơ-moóc dùng
        # 'raised' (mốc này ĐÃ xác nhận đúng thực tế — rơ-moóc hiện đang dừng lấy
        # rỗng bình thường), AGV kéo phải dùng 'lowered'.
        _agv_type_bt_split = str(agv_registry.get_config(agv_id).get('agv_type') or '').strip().lower()
        _agv_type_trailer_split = _agv_type_bt_split in ('trailer', 'tow')
        _hook_has_cargo_split = 'lowered' if _agv_type_bt_split == 'tow' else 'raised'
        _dispatch_from_charger_split = (
            str((node_actions.get(str(path[0])) or {}).get('locationType') or '').upper() == 'CHARGER'
        )
        # Lượt đi tới ĐIỂM CHỜ / TRẠM SẠC (kể cả chặng trung gian của chuỗi đi thang): chỉ ĐI QUA các node lấy/thả hàng
        # (trailer_empty_staging, trailer_staging, điểm cấp supply wait_sys/wait_user) — KHÔNG dừng. Cửa tự động và thang máy
        # vẫn xử lý bình thường (nhánh door_id bên dưới không bị ảnh hưởng).
        _pass_through_pickups = _atq_pick.heading_to_special(agv_id)

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
                    and not _pass_through_pickups
                    and _agv_type_trailer_split
                    and _dispatch_from_charger_split
                    and str(_node_cfg.get('trailer_empty_staging') or '').lower() == 'yes'
                    and str(getattr(_lstate, 'hook_state', None) or '') != _hook_has_cargo_split):
                from line_agv_handler import _pending_empty_pickup_legs
                # NHIỀU điểm lấy rỗng TƯƠNG ĐƯƠNG (vd node 4 và 25 cùng 'trailer_empty_staging'):
                # nếu node trên đường đi đang bị xe KHÁC chiếm/nhắm tới mà còn node tương đương
                # TRỐNG → chuyển sang node trống đó thay vì cùng dừng ở 1 node rồi tranh chấp
                # (log 2026-11-19: AGV01 và AGV02 rời trạm cách nhau 12s đều dừng ở node 4,
                # node 25 y hệt cấu hình bị bỏ qua). Hết node trống → giữ hành vi cũ (dừng ở đây, chờ).
                if agv_id not in _EMPTY_STAGING_REDIRECTING:
                    try:
                        _es_here = str(path[_si])
                        _es_occ = _line_agv_occupied_nodes(agv_id)
                        from line_agv_handler import path_claimed_by_other as _pcb_es

                        def _es_blocker(_node, _pth):
                            # node đã có xe đứng/nhắm tới, HOẶC đường tới node đó đang bị xe khác chiếm (chưa tới nơi)
                            return _es_occ.get(str(_node)) or _pcb_es(agv_id, [str(x) for x in _pth[1:]])
                        _es_blk_here = _es_blocker(_es_here, path[:_si + 1])
                        if _es_blk_here:
                            import networkx as _nx_es
                            _g_es = getattr(map_manager, 'line_graph', None) or getattr(map_manager, 'graph', None)
                            _es_free = []
                            for _n, _c in (node_actions or {}).items():
                                if (str((_c or {}).get('trailer_empty_staging') or '').lower() != 'yes'
                                        or str((_c or {}).get('arrival_action') or '')
                                        or str(_n) in (_es_here, str(path[0]))):
                                    continue
                                try:
                                    _pth_es = _nx_es.shortest_path(_g_es, str(path[0]), str(_n), weight='weight')
                                except Exception:
                                    continue
                                if not _es_blocker(_n, _pth_es):
                                    _es_free.append(str(_n))
                            _es_alt = _nearest_of(_es_free, str(path[0]), exclude_agv=agv_id) if _es_free else None
                            if _es_alt:
                                print(f"[DISPATCH] {agv_id}: điểm lấy rỗng {_es_here} đang bị "
                                      f"{_es_blk_here} chiếm (đứng/đang tới/đang đi qua đường dẫn tới đó) → chuyển sang "
                                      f"điểm tương đương THÔNG THOÁNG {_es_alt}, rồi đi tiếp {dest_node}")
                                _pending_empty_pickup_legs.add((agv_id, _es_alt))
                                from task_queue import agv_task_queue as _atq_es, CMD_GO_TO as _CGT_es
                                _atq_es.insert_next(agv_id, _CGT_es, dest_node=str(dest_node))
                                _EMPTY_STAGING_REDIRECTING.add(agv_id)
                                try:
                                    return _dispatch_go_to(agv_id, _es_alt, session_id=session_id)
                                finally:
                                    _EMPTY_STAGING_REDIRECTING.discard(agv_id)
                    except Exception as _e_es:
                        print(f"[DISPATCH] {agv_id}: chọn điểm lấy rỗng tương đương lỗi: {_e_es}")
                # Đánh dấu TRƯỚC khi gửi lệnh — arrival handler cần thấy dấu này ngay
                # khi xe tới (cùng pattern với execute_trailer_roundtrip).
                _pending_empty_pickup_legs.add((agv_id, str(path[_si])))
                split_idx = _si
                print(f"[DISPATCH] {agv_id}: node {path[_si]} = điểm lấy hàng rỗng cố định "
                      f"gần trạm (trailer_empty_staging), xe vừa rời trạm sạc → dừng lấy "
                      f"hàng trước khi đi tiếp")
                break
            if _pass_through_pickups and (
                    _acfg in ("wait_user", "wait_sys")
                    or str(_node_cfg.get('trailer_staging') or '').lower() == 'yes'
                    or str(_node_cfg.get('trailer_empty_staging') or '').lower() == 'yes'):
                print(f"[DISPATCH] {agv_id}: lượt về trạm/điểm chờ → đi thẳng qua node {path[_si]} "
                      f"(bỏ qua chức năng lấy/thả hàng)")
                continue
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
        _is_post_charge = _was_leaving_charger

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
        _cur_node_cfg_exit = (_with_trailer_exit_defaults(
            agv_id, str(path[0]), node_actions.get(str(path[0])) or {}) if path else {})
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

        # Khi AGV vừa xong bwd transit → CHỈ tiếp tục direction=bwd nếu node HIỆN TẠI
        # (path[0], điểm xuất phát của lệnh dispatch MỚI này) thật sự cần lùi ra
        # (approach_dir=bwd hoặc arrival_action=wait_charge — ngõ cụt/điểm lấy-hàng
        # chỉ lùi được). last_tdir_pre='bwd' chỉ nói "đoạn TRƯỚC đã lùi xong" — nếu
        # lệnh này là 1 command MỚI hoàn toàn (path[1] != prev_tag, không qua khối
        # pingpong ở trên) và node hiện tại là node giao thường (không cần lùi ra),
        # thì đó là dấu vết CŨ của đoạn lùi đã hoàn tất, KHÔNG có lý do để áp bwd
        # cho toàn bộ tuyến mới (khác hẳn, có thể rẽ nhánh sang hướng khác).
        # TỔNG QUÁT: cùng nguyên tắc đã áp dụng cho _try_line_reroute() ở
        # line_agv_handler.py — chỉ giữ bwd khi node hiện tại CẤU TRÚC cần lùi ra,
        # không suy diễn từ lịch sử đoạn transit trước đó.
        # Bug thực tế TƯỞNG đã sửa: AGV04 lùi ra 98→6 (đúng, node 98 cần lùi), rồi
        # lệnh tiếp theo 6→10→99→13→14→... bị gán bwd theo cờ cũ dù node 6 là ngã
        # giao bình thường → xe lùi dài qua hàng loạt node không liên quan.
        #
        # PHÁT HIỆN THỰC TẾ (2026-10-01, RÚT LẠI bản sửa trên): điều kiện
        # `_cur_needs_bwd_exit` (chỉ giữ bwd khi node HIỆN TẠI có approach_dir=bwd/
        # wait_charge) dựa trên tiền đề SAI — mũi xe KHÔNG tự "reset" về hướng tiến
        # chỉ vì node hiện tại không được đánh dấu riêng. Sau khi lùi (DIR_BWD) từ
        # 106 ra 32 mà KHÔNG có cú rẽ nào xảy ra giữa đường, mũi xe VẪN đang quay
        # về hướng 106 — y hệt trước khi bắt đầu lùi. Nếu dispatch kế ÉP sang
        # direction=fwd + rẽ (vì node 32 không có approach_dir=bwd), xe sẽ RẼ MŨI
        # theo lệnh rồi TIẾN theo hướng mũi MỚI đó — hoàn toàn KHÁC với "lùi tiếp
        # về 30" (mũi vẫn hướng 106, chỉ đánh lái phần đuôi) — có thể đẩy xe lệch
        # hẳn ra khỏi line/bản đồ (đúng ca thực tế: AGV01 + AGV04 cùng kẹt cứng tại
        # 32→30→105 sau khi bị ép sang fwd). Quay lại quy tắc gốc: hễ chặng lùi
        # TRƯỚC ĐÓ chưa bị "tiêu thụ" bởi 1 dispatch khác (last_tdir vẫn còn 'bwd')
        # thì mũi xe vẫn y nguyên hướng cũ → PHẢI tiếp tục lùi, bất kể node hiện
        # tại có đánh dấu approach_dir hay không. (Case AGV04 10→11→12 "trôi dạt"
        # trước đây rất có thể là CÙNG lỗi thực thi rẽ/overshoot ở tầng
        # firmware/execution — ép sang fwd chỉ dịch chuyển chỗ lộ lỗi, không sửa
        # được gốc — nên không đổi hướng xử lý vì lo tái phát ca đó.)
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
                initial_prev_tag=_initial_prev, initial_arrived_bwd=_initial_arrived_bwd,
                skip_initial_dir=bool(_trailer_exit_steps))
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
                initial_prev_tag=_initial_prev, initial_arrived_bwd=_initial_arrived_bwd,
                skip_initial_dir=bool(_trailer_exit_steps))
            if _trailer_exit_steps:
                plan["d"] = _trailer_exit_steps + plan.get("d", [])
            send_order(agv_id, plan)
            print(f"[DISPATCH] {agv_id}: no-split window=[0→{_rt.window_end}] final={_rt.is_complete} "
                  f"(len={len(path)})")
        print(f"[DISPATCH] {agv_id}: node_actions keys={list(node_actions.keys())[:10]}")
    else:
        # ── VDA5050: cửa tự động trên đường đi — TÁCH route giống hệt cách Line
        # AGV đang làm (xem khối "CỬA TỰ ĐỘNG" phía trên, quanh biến split_idx):
        # nếu gặp node có door_id CHƯA mở (is_exit_arrival=False → lượt VÀO) TRƯỚC
        # khi tới đích thật, dispatch CHẶNG NÀY chỉ tới node cửa đó thôi, đích
        # gốc được chèn vào đầu hàng đợi để tự động chạy tiếp khi cửa xác nhận mở
        # (xem door_coordinator._resume_agv đã tổng quát hoá cho VDA5050).
        node_actions_vda = getattr(map_manager, "node_actions", {}) or {}
        _orig_dest_node_vda = dest_node
        _path_ids_vda = [str(n.get("nodeId")) for n in route_nodes]
        _door_split_idx_vda = None
        for _i_vda in range(1, len(_path_ids_vda) - 1):
            _door_id_vda = str((node_actions_vda.get(_path_ids_vda[_i_vda]) or {}).get('door_id') or '').strip()
            if not _door_id_vda:
                continue
            from door_coordinator import door_coordinator as _door_co_vda
            if _door_co_vda.is_exit_arrival(_door_id_vda, agv_id, _path_ids_vda[_i_vda]):
                continue   # đang RA khỏi cửa (đã băng qua) — không cần dừng
            _door_split_idx_vda = _i_vda
            break
        if _door_split_idx_vda is not None:
            dest_node   = _path_ids_vda[_door_split_idx_vda]
            route_nodes = route_nodes[: _door_split_idx_vda + 1]
            route_edges = route_edges[: _door_split_idx_vda]
            from task_queue import agv_task_queue as _atq_vda_door, CMD_GO_TO as _CGT_vda_door
            _atq_vda_door.insert_next(agv_id, _CGT_vda_door, dest_node=str(_orig_dest_node_vda))
            print(f"[DISPATCH] {agv_id}: VDA5050 route tách tại cửa tự động node "
                  f"{dest_node}, đích gốc {_orig_dest_node_vda} chèn tiếp vào hàng đợi")

        # ── VDA5050: ưu tiên traffic-engine-aware planning ─────────────────────
        # Dùng blocked_edges để tránh đường đã bị xe khác đặt trước (proactive).
        # Nếu thất bại → fallback về basic Dijkstra (đã tính ở trên).
        #
        # Đánh dấu pending_confirm_node TRƯỚC khi gửi order, để nhánh paused=True
        # trong mqtt_client.py biết KHÔNG auto-complete queue ngay khi xe hết node
        # released — 2 lý do cần giữ xe lại tại node đích của CHẶNG NÀY:
        #   (a) vừa tách route tại node cửa (_door_split_idx_vda ở trên) — chỉ
        #       được đi tiếp khi cửa THẬT SỰ xác nhận mở (door_coordinator._resume_agv
        #       tự xoá cờ này + dispatch tiếp khi có xác nhận, KHÔNG cần người bấm);
        #   (b) node đích cần xác nhận thủ công PICKUP/DROP (theo defaultAction
        #       trên MapConfigure) — xác nhận qua /api/execute/lifecycle-ack.
        _dest_action_type, _ = _vda5050_dest_action(node_actions_vda, dest_node)
        _needs_hold_vda = (_door_split_idx_vda is not None) or bool(_dest_action_type)
        agv_manager.set_pending_confirm(agv_id, str(dest_node) if _needs_hold_vda else None)

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
                        print(f"[DISPATCH] {agv_id}: traffic-aware route → {te_path}"
                              f"{f' (chờ xác nhận {_dest_action_type} tại {dest_node})' if _dest_action_type else ''}")
                        _te_success = True
        except Exception as _te_err:
            print(f"[DISPATCH] {agv_id}: traffic-aware planning failed ({_te_err}) — fallback Dijkstra")

        if not _te_success:
            from mqtt_client import build_order_with_path, send_generated_order
            order = build_order_with_path(agv_id, route_nodes, route_edges, end_action_type=_dest_action_type)
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


def _line_agv_alert(st, connection: str) -> "dict | None":
    """Cảnh báo hệ thống đang hiển thị cho UI/map — đọc field có cấu trúc đã
    được line_agv_handler ghi tại các điểm phát hiện lỗi đã có (xem
    LineAGVHandler._set_alert/_clear_alert), KHÔNG tự thêm phát hiện mới. Nếu
    không có cảnh báo nào nhưng mất kết nối MQTT → tổng hợp 1 cảnh báo OFFLINE
    từ field connection đã tính sẵn (_conn_from_last_seen).

    Cảnh báo từ TIẾN TRÌNH NGOÀI (set_external_alert, vd sim_monitor.py) có
    thêm field `expires_at` — hết hạn mà KHÔNG được refresh (bên ngoài không
    còn thấy vi phạm nữa) thì coi như không có, rơi về nhánh OFFLINE/None."""
    alert = getattr(st, "active_alert", None) if st else None
    if alert:
        expires_at = alert.get("expires_at")
        if expires_at is None or time.time() <= expires_at:
            return {**alert, "elapsed_sec": round(time.time() - alert["since"], 1)}
    if connection != "ONLINE":
        return {"kind": "OFFLINE", "message": "Mất kết nối MQTT", "elapsed_sec": None}
    return None


@app.get("/api/execute/traffic-stats")
async def execute_traffic_stats():
    """Thống kê điều phối của process NÀY (sản xuất tại 8000, mô phỏng tại
    port riêng — mỗi process tự có bộ đếm riêng, không lẫn nhau). Dùng cho
    màn 'Mô phỏng Fleet' hiển thị số lần gặp ngã tư/xử lý và số lần lỗi/kẹt."""
    from line_agv_handler import get_traffic_stats
    return get_traffic_stats()


@app.post("/api/execute/traffic-stats/reset")
async def execute_traffic_stats_reset():
    """Xoá thống kê điều phối của process này — gọi khi bắt đầu 1 lượt mô
    phỏng mới để số liệu không lẫn từ lượt chạy trước."""
    from line_agv_handler import reset_traffic_stats
    reset_traffic_stats()
    return {"success": True}


@app.get("/api/execute/agv-list")
async def execute_agv_list():
    """Danh sách AGV từ bảng agv_devices, kết hợp trạng thái real-time.
    Dùng psycopg2 (sync trong thread) — cùng pattern với agv_manager.py."""
    from line_agv_handler import line_agv_handler
    from task_queue import agv_task_queue
    from agv_registry import agv_registry

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
                "op_mode":          agv_registry.op_mode(agv_id),
                "return_mode":      agv_registry.return_mode(agv_id),
                "alert":            _line_agv_alert(st, line_conn),
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


def _nearest_of(candidates: list[str], near_node: str | None,
                 exclude_agv: str | None = None) -> str | None:
    """Trong nhiều node TƯƠNG ĐƯƠNG NHAU (cùng đánh dấu 1 chức năng, vd 2 điểm
    staging ở 2 đầu nhà xưởng), chọn node GẦN `near_node` NHẤT theo đường đi
    thật trên map — thay vì lấy tuỳ ý (thứ tự trong DB, không liên quan vị trí
    xe). Không có `near_node`/graph hoặc chỉ có 1 candidate → trả candidate đầu
    tiên (giữ hành vi cũ, an toàn khi thiếu dữ liệu).

    `exclude_agv` (id của xe đang cần chọn node): nếu truyền vào, LOẠI TRƯỚC
    các candidate đang bị XE KHÁC chiếm/nhắm tới (xem _line_agv_occupied_nodes)
    — nếu vẫn còn candidate khác TRỐNG thì ưu tiên candidate trống đó (dù xa
    hơn 1 chút), tránh xe phải ĐỨNG CHỜ ở node đã có xe khác trong khi node
    tương đương ngay gần đó đang rảnh (đúng phản ánh thực tế: gọi 2 lệnh gần
    nhau, xe sau lẽ ra nên tự chuyển sang node tương đương còn trống thay vì
    cùng nhắm 1 node rồi phải chờ/né nhau). Nếu CẢ HAI đều bị chiếm → vẫn chọn
    theo khoảng cách như bình thường (không có lựa chọn nào tốt hơn)."""
    if not candidates:
        return None
    if exclude_agv and len(candidates) > 1:
        try:
            _occupied = _line_agv_occupied_nodes(exclude_agv)
        except Exception:
            _occupied = {}
        _free = [c for c in candidates if c not in _occupied]
        if _free and len(_free) < len(candidates):
            print(f"[STAGING] {exclude_agv}: {[c for c in candidates if c in _occupied]} "
                  f"đang bị xe khác chiếm → ưu tiên node trống {_free}")
        if _free:
            candidates = _free
    if len(candidates) == 1 or not near_node:
        return candidates[0]
    try:
        import networkx as _nx
        import contextlib as _cl
        # Khoảng cách theo đường đi THẬT của loại xe này (hướng riêng/vùng cấm), không phải đồ thị thô.
        with (map_manager.agv_scope(exclude_agv) if exclude_agv else _cl.nullcontext()):
            g = getattr(map_manager, 'line_graph', None) or getattr(map_manager, 'graph', None)
            if g is None:
                return candidates[0]
            best, best_d = candidates[0], None
            for c in candidates:
                try:
                    d = _nx.shortest_path_length(g, str(near_node), str(c), weight='weight')
                except Exception:
                    continue
                if best_d is None or d < best_d:
                    best, best_d = c, d
        return best
    except Exception:
        return candidates[0]


async def _find_trailer_staging_node(map_id: str, near_node: str | None = None,
                                      exclude_agv: str | None = None) -> str | None:
    """Tìm node được đánh dấu 'trailer_staging=yes' trên map — điểm thả hàng
    đầy cố định, dùng chung cho MỌI Tổ (không cần nhập tay lúc dispatch).

    Map có thể có NHIỀU node cùng đánh dấu (2 điểm tương đương ở 2 khu vực
    khác nhau) — trước đây luôn lấy CỐ ĐỊNH 1 node bất kể xe đang ở đâu (LIMIT 1
    theo thứ tự DB), khiến xe đi ngang qua 1 node tương đương rồi vẫn phải đi
    tiếp tới node kia (đúng phản ánh thực tế: 2 node chức năng như nhau nhưng
    xe luôn phải vòng về 1 node cố định). Truyền `near_node` (vị trí AGV lúc
    sắp ghé staging) để chọn node GẦN NHẤT trong số các node hợp lệ. Truyền
    `exclude_agv` (id chính xe này) để ưu tiên node ĐANG TRỐNG nếu xe khác đã
    nhắm/chiếm node gần nhất — xem _nearest_of()."""
    async with app.state.db_pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT name_id FROM agv_map_points
               WHERE CAST(map_id AS TEXT) = $1
                 AND action->>'trailer_staging' = 'yes'""",
            str(map_id),
        )
    return _nearest_of([str(r["name_id"]) for r in rows], near_node, exclude_agv)


async def _find_trailer_empty_staging_node(map_id: str, near_node: str | None = None,
                                            exclude_agv: str | None = None) -> str | None:
    """Node đánh dấu 'trailer_empty_staging=yes' — điểm lấy hàng rỗng cố định
    gần trạm (đầu quy trình, trước khi ra Tổ). TUỲ CHỌN — có thể trùng với
    node trailer_staging (1 node dùng chung cả 2 chức năng).

    Cùng lý do chọn NODE GẦN NHẤT như _find_trailer_staging_node() — xem giải
    thích ở đó."""
    async with app.state.db_pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT name_id FROM agv_map_points
               WHERE CAST(map_id AS TEXT) = $1
                 AND action->>'trailer_empty_staging' = 'yes'""",
            str(map_id),
        )
    return _nearest_of([str(r["name_id"]) for r in rows], near_node, exclude_agv)


_carry_cart_dropped: set = set()   # agv_id đã đi thả xe hàng ở lượt "về trạm" này (chặn lặp)


def _carry_return_staging(agv_id: str) -> str | None:
    """Xe kéo ở chế độ carry_hook + return_mode=drop_cart, đang kéo xe hàng (móc
    đã nâng) và được lệnh "về trạm sạc" → trả node 'trailer_staging' (điểm thả cố
    định) gần nhất để ghé thả xe hàng TRƯỚC khi sạc. Trả None = đi sạc thẳng.
    Mỗi lượt chỉ ghé 1 lần (_carry_cart_dropped) để lệnh go_charge chèn lại sau đó
    không bị chặn tiếp."""
    from agv_registry import agv_registry as _reg
    from line_agv_handler import line_agv_handler as _lah
    from mqtt_client import map_manager as _mm
    if agv_id in _carry_cart_dropped:
        _carry_cart_dropped.discard(agv_id)
        return None
    if _reg.op_mode(agv_id) != "carry_hook" or _reg.return_mode(agv_id) != "drop_cart":
        return None
    st = _lah.state_store.get(agv_id)
    if not st or st.hook_state != "raised":     # tow: raised = đang khoá xe hàng
        return None
    na = getattr(_mm, "node_actions", {}) or {}
    cands = [str(n) for n, a in na.items()
             if str((a or {}).get("trailer_staging", "")).lower() == "yes"]
    near = str(st.current_tag) if st.current_tag is not None else None
    node = _nearest_of(cands, near, agv_id) if cands else None
    if not node:
        print(f"[CARRY] {agv_id}: return_mode=drop_cart nhưng map chưa đánh dấu node "
              f"'Điểm thả hàng cố định (Staging)' → đi sạc thẳng")
        return None
    if near == node:
        return None
    _carry_cart_dropped.add(agv_id)
    return node


def _find_waiting_nodes() -> list[str]:
    """Danh sách node được đánh dấu 'waiting_node=yes' trên Map Editor — dùng để
    giải bí hoàn toàn khi CẢ HỆ THỐNG đứng im (xem _dispatch_to_waiting_node()).
    Đọc trực tiếp từ map_manager.node_actions (đã nạp sẵn trong tiến trình),
    KHÔNG query DB mới — theo đúng pattern in-memory đã dùng ở
    door_coordinator.find_paired_door_node (node_actions.items() loop)."""
    out: list[str] = []
    for nid, cfg in (getattr(map_manager, 'node_actions', {}) or {}).items():
        if isinstance(cfg, dict) and str(cfg.get('waiting_node', '')).lower() == 'yes':
            out.append(str(nid))
    return out


def _pick_stall_victim(stalled_agv_ids: list[str],
                        waiting_nodes: list[str]) -> tuple[str, str] | None:
    """Chọn xe 'nạn nhân' đi vào node chờ trong số các xe đang cùng bí hoàn toàn
    (xem TrafficCoordinator.check_global_stall()). Tie-break ĐÃ XÁC NHẬN với
    người dùng: ƯU TIÊN THẤP NHẤT thắng trước; hoà ưu tiên thì xe GẦN node chờ
    nhất (ít node hơn trên đường tới node chờ) thắng. Trả về (agv_id,
    waiting_node) đã chọn, hoặc None nếu không xe nào có đường tới bất kỳ node
    chờ nào (vd map thiếu cấu hình, hoặc node chờ đang đúng vị trí hiện tại)."""
    from line_agv_handler import line_agv_handler as _lah_pick, traffic_coordinator as _tc_pick
    _charger_fallback_nodes = map_manager.charger_nodes()
    best: tuple | None = None   # (-số xe bị chặn, priority, distance, agv_id, waiting_node)

    def _blocked_by(agv_id: str, cur_tag: str) -> int:
        """Số xe KHÁC trong nhóm bí có node `cur_tag` nằm trên phần đường CÒN LẠI của họ = xe này đang chặn
        bấy nhiêu xe. Cử nhầm xe không chặn ai (vd đứng ngoài vòng khoá) thì không giải được bí."""
        n = 0
        for other in stalled_agv_ids:
            if other == agv_id:
                continue
            reg = _tc_pick._registered.get(other) or {}
            path = [str(x) for x in (reg.get('path') or [])]
            idx = int(reg.get('current_idx', 0) or 0)
            if cur_tag in path[idx + 1:]:
                n += 1
        return n

    for agv_id in stalled_agv_ids:
        lstate = _lah_pick.state_store.get(agv_id)
        cur = str(lstate.current_tag) if (lstate and lstate.current_tag is not None) else None
        if not cur:
            continue
        priority = _tc_pick._registered.get(agv_id, {}).get('priority', 2)
        blocks = _blocked_by(agv_id, cur)
        _forb_pick = map_manager.forbidden_nodes(agv_id)   # vùng cấm của loại xe này
        # NHIỀU TẦNG: xe đang trong cabin thang không thể "đi nhường" (phải ra khỏi thang trước), và điểm né phải CÙNG TẦNG
        # với xe (PHÁT HIỆN THỰC TẾ 2026-11-20: bộ điều phối chọn trạm sạc 27 ở F1 cho AGV01 đang ở cabin F2 → bị từ chối).
        _mf_pick = False
        try:
            import floor_nav as _fn_pick
            _mf_pick = _fn_pick.multi_floor(map_manager)
            if _mf_pick and cur in {str(c) for c in (getattr(map_manager, 'shared_cabins', None) or ())}:
                continue
        except Exception:
            _mf_pick = False
        for wnode in waiting_nodes:
            if cur == wnode or str(wnode) in _forb_pick:
                continue
            if _mf_pick:
                try:
                    if _fn_pick.floor_of(cur, map_manager) != _fn_pick.floor_of(str(wnode), map_manager):
                        continue
                except Exception:
                    pass
            if wnode in _charger_fallback_nodes:
                # trạm sạc chỉ được dùng làm điểm né nếu CÒN TRỐNG và đúng loại xe
                from line_agv_handler import _charger_siding_ok as _cso, _nodes_busy_for as _nbf
                if not _cso(agv_id, wnode, _nbf(agv_id, _lah_pick)):
                    continue
            try:
                with map_manager.agv_scope(agv_id):
                    path = map_manager.line_shortest_path(cur, wnode)
            except Exception:
                path = None
            if not path:
                continue
            cand = (-blocks, priority, len(path), agv_id, wnode)
            if best is None or cand[:3] < best[:3]:
                best = cand
    if best is None:
        return None
    return best[3], best[4]


def _dispatch_to_waiting_node(stalled_agv_ids: list[str]) -> None:
    """Được gọi từ line_agv_handler.TrafficCoordinator.check_global_stall() khi
    CẢ HỆ THỐNG bí hoàn toàn (N xe khoá chéo nhau qua reservation — vd xe A chờ
    node đang bị xe B "giữ chỗ trước" trong khi B lại đang đứng chờ chính A —
    _is_deadlocked_with chỉ bắt được đúng 2 xe, không bắt được vòng 3+ xe). Cử
    xe ưu tiên thấp nhất (tie-break: gần node chờ nhất — đã xác nhận với người
    dùng) vào 1 node chờ đã đánh dấu trên Map Editor để nhường đường cho các xe
    còn lại; node chờ chỉ là 1 node BÌNH THƯỜNG được xe khác thấy "bị chiếm"
    qua đúng cơ chế reservation/arbitration sẵn có — KHÔNG cần code mới ở
    TrafficCoordinator cho việc này. Lệnh THẬT đang chạy của xe nạn nhân được
    giữ lại (insert_next) để tự resume qua đúng cơ chế pending-retry/off_route
    re-dispatch đã có, khi đường thông."""
    waiting_nodes = _find_waiting_nodes()
    picked = _pick_stall_victim(stalled_agv_ids, waiting_nodes) if waiting_nodes else None
    if not picked:
        # Không có node chờ dùng được → DỰ PHÒNG: trạm sạc làm điểm né (chỉ xe không bị cấm, trạm
        # trống, đúng loại xe; trạm sạc là điểm cuối bản đồ nên xe vào rồi dừng hẳn).
        _chargers = sorted(map_manager.charger_nodes())
        if _chargers:
            picked = _pick_stall_victim(stalled_agv_ids, _chargers)
            if picked:
                print(f"[STALL] hết node chờ → dùng TRẠM SẠC {picked[1]} làm điểm né cho {picked[0]}")
    if not waiting_nodes and not picked:
        print(f"[STALL] {len(stalled_agv_ids)} xe cùng bí hoàn toàn nhưng chưa có node "
              f"chờ nào được cấu hình (và không có trạm sạc trống) — đánh dấu 'waiting_node' "
              f"cho 1 node trên Map Editor để kích hoạt tính năng nhường đường tự động")
        return
    if not picked:
        print(f"[STALL] {len(stalled_agv_ids)} xe cùng bí nhưng không xe nào có đường "
              f"tới node chờ đã cấu hình — bỏ qua lượt này")
        return
    victim, wnode = picked
    from task_queue import agv_task_queue as _atq_stall, CMD_GO_TO as _CGT_stall
    run = _atq_stall._running.get(victim)
    orig_dest = str(run.dest_node) if (run and run.dest_node) else None
    if not orig_dest:
        print(f"[STALL] {victim}: không xác định được đích đang chạy — bỏ qua lượt này")
        return
    print(f"[STALL] Cả hệ thống bí hoàn toàn ({', '.join(stalled_agv_ids)}) → cử {victim} "
          f"(chặn nhiều xe nhất, rồi ưu tiên thấp nhất) vào node chờ {wnode} để nhường đường; đích gốc {orig_dest} "
          f"giữ lại, tự resume khi đường thông")
    try:
        from line_agv_handler import line_agv_handler as _lah_stall, traffic_coordinator as _tc_stall
        # Tháo dỡ route/registration đang chạy dở — ĐÚNG cặp gọi đã dùng ở nhánh
        # "off_route" (line_agv_handler.py) để chuyển xe sang 1 lệnh khác an toàn.
        _lah_stall._routes.pop(victim, None)
        _tc_stall.deregister(victim)
        # Đánh dấu đây là chặng TRANSIT (không phải đích giao/lấy hàng thật) —
        # ĐÚNG cơ chế _pending_staging_transits đã dùng cho staging/off_route,
        # tránh _dispatch_go_to coi node chờ là đích thật rồi hạ móc/chờ HMI nhầm.
        _pending_staging_transits.add((victim, str(wnode)))
        _atq_stall.insert_next(victim, _CGT_stall, dest_node=orig_dest)
        _atq_stall.on_agv_completed(victim, notes='stall_to_waiting_node', auto_dispatch=False)
        _dispatch_go_to(victim, wnode, session_id=None)
    except Exception as e:
        print(f"[STALL] {victim}: lỗi khi dispatch vào node chờ: {e}")


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
    if agv_type not in ("trailer", "tow"):
        raise HTTPException(status_code=400,
            detail=f"Lệnh này chỉ dành cho AGV loại trailer/tow (AGV '{agv_id}' là loại '{agv_type}')")

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
        # near_node=pickup_node: xe sẽ TỚI staging NGAY SAU KHI lấy đầy ở pickup_node
        # (chặng 2→4), nên "gần" phải tính từ đó chứ không phải vị trí xuất phát.
        staging_node = await _find_trailer_staging_node(
            map_id, near_node=pickup_node, exclude_agv=agv_id)
        if not staging_node:
            raise HTTPException(status_code=404,
                detail=f"Map {map_id} chưa đánh dấu node 'Điểm thả hàng đầy cố định (Staging)' "
                       f"— vào Tạo bản đồ, chọn node và tick ô đó.")

    # Điểm lấy hàng rỗng cố định gần trạm — TUỲ CHỌN, bỏ qua chặng này nếu map
    # chưa cấu hình (giữ đúng hành vi 4 chặng cũ, không bắt buộc).
    # near_node=vị trí HIỆN TẠI của xe — đây là chặng ĐẦU TIÊN xe sẽ đi tới.
    empty_staging_node = await _find_trailer_empty_staging_node(
        map_id, near_node=info.get("current_node"), exclude_agv=agv_id)

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
    if agv_type not in ("trailer", "tow"):
        raise HTTPException(status_code=400,
            detail=f"Lệnh này chỉ dành cho AGV loại trailer/tow (AGV '{agv_id}' là loại '{agv_type}')")

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

    staging_node = await _find_trailer_staging_node(
        map_id, near_node=current_node, exclude_agv=agv_id)
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
            if not (st and st.ghost) and not _line_state_online(st):
                continue   # xe offline không hiện trên bản đồ theo dõi (xe ma thì vẫn hiện)
            current_node = str(st.current_tag) if (st and st.current_tag is not None and st.current_tag != 0) else None
            driving  = st.driving if st else False
            battery  = st.battery if st else None
        else:
            if connection != "ONLINE":
                continue
            st           = agv_manager.get_agv(agv_id) or {}
            current_node = str(st.get("lastNodeId") or "") or None
            driving      = bool(st.get("driving"))
            battery      = st.get("batteryState", {}).get("batteryCharge") if st else None

        pt = pts.get(current_node) if current_node else None
        # Xe trong cabin thang DÙNG CHUNG: node cabin chỉ lưu floor_id/toạ độ của 1 tầng, nhưng cabin đang ở tầng thang
        # đứng (floor_nav.set_cabin_floor cập nhật khi thang tới nơi) → xe hiện ở tầng đó, đúng mặt cabin của tầng đó.
        floor_id = None
        try:
            import floor_nav as _fn_pos
            if (current_node and _fn_pos.multi_floor(map_manager)
                    and str(map_manager.current_map_id) == str(map_id)
                    and _fn_pos.is_shared_cabin(current_node, map_manager)):
                floor_id = _fn_pos.floor_of(current_node, map_manager) or None
                cxy = (getattr(map_manager, "cabin_xy", None) or {}).get(current_node, {}).get(str(floor_id))
                if cxy:
                    pt = {"x": float(cxy[0]), "y": float(cxy[1])}
        except Exception:
            floor_id = None
        result.append({
            "agv_id":       agv_id,
            "agv_type_raw": agv_type_raw,
            "x":            pt["x"] if pt else None,
            "y":            pt["y"] if pt else None,
            "floor_id":     floor_id,
            "current_node": current_node,
            "connection":   connection,
            "driving":      driving,
            "battery":      battery,
            "has_position": pt is not None,
            "alert":        _line_agv_alert(st, connection) if is_line else None,
            "ghost":        bool(is_line and st and st.ghost),
            "ghost_nodes":  list(st.ghost_nodes) if (is_line and st and st.ghost) else [],
        })

    return {"positions": result, "map_id": map_id}


@app.post("/api/execute/agv-ghost-clear")
async def execute_agv_ghost_clear(payload: dict):
    """Người vận hành xác nhận xe mất tín hiệu đã được gỡ khỏi đường → bỏ xe ma."""
    from line_agv_handler import line_agv_handler
    agv_id = str(payload.get("agv_id") or "")
    st = line_agv_handler.state_store.get(agv_id)
    if st is None or not st.ghost:
        raise HTTPException(status_code=404, detail="Xe không ở trạng thái mất tín hiệu")
    _ghost_release(line_agv_handler, agv_id, st, recovered=False)
    return {"ok": True}


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
            sup = _required_supply_node(na, d, agv_id, current_node)
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
        # AGV kéo ('tow') chạy CHUNG quy trình 4 chặng với rơ-moóc (lấy rỗng → thả
        # ở Tổ → lấy đầy → staging) — chỉ khác trạng thái hook_state ĐÍCH biểu thị
        # "đã có hàng gắn sẵn": 'lowered' cho rơ-moóc, 'raised' cho AGV kéo (quy
        # trình móc ngược nhau — xem line_agv_handler._is_tow_agv).
        _is_trailer_family_bt = _agv_type_bt in ('trailer', 'tow')
        _hook_attached_target_bt = 'raised' if _agv_type_bt == 'tow' else 'lowered'
        if _is_trailer_family_bt and _has_delivery_leg:
            _map_id_bt = info.get("resolved_map_id") or info.get("raw_map") if info else None
            from line_agv_handler import line_agv_handler as _lah_bt
            _lstate_bt = _lah_bt.state_store.get(agv_id)
            _hook_state_bt = getattr(_lstate_bt, 'hook_state', None) if _lstate_bt else None
            if _hook_state_bt != _hook_attached_target_bt and _map_id_bt:
                _empty_node_bt = await _find_trailer_empty_staging_node(
                    str(_map_id_bt), near_node=current_node, exclude_agv=agv_id)
                if _empty_node_bt and str(_empty_node_bt) != str(current_node):
                    _trailer_pickup_node = str(_empty_node_bt)
        elif _is_trailer_family_bt and not _has_delivery_leg:
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
    if _is_trailer_family_bt and len(_all_drop_dests_pretrim) > 1:
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
    if _is_trailer_family_bt and _map_id_bt:
        _seen_full_pickup: set[str] = set()
        for d in _all_drop_dests_pretrim:
            _d_na = na.get(str(d)) or {}
            for _tm in (_d_na.get('trailer_drop_teams') or []):
                try:
                    _tm_int = int(_tm)
                except (TypeError, ValueError):
                    continue
                try:
                    # Dùng ĐÚNG loại xe của agv_id (không hardcode 'trailer') để
                    # _resolve_team_node ưu tiên đúng node đánh dấu team_agv_type
                    # riêng cho AGV kéo, nếu map có tách vị trí lấy đầy theo loại xe.
                    _pk_node = await _resolve_team_node(str(_map_id_bt), _tm_int, _agv_type_bt, want_pickup=True)
                except Exception as _e_pk:
                    print(f"[BATCH] {agv_id}: resolve lay day To {_tm_int} loi: {_e_pk}")
                    _pk_node = None
                if _pk_node and _pk_node not in _seen_full_pickup and _pk_node != str(d):
                    _seen_full_pickup.add(_pk_node)
                    _full_pickup_nodes.append(_pk_node)

        if _full_pickup_nodes:
            if not _staging_bt:
                _staging_bt = await _find_trailer_staging_node(
                    str(_map_id_bt), near_node=current_node, exclude_agv=agv_id)
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
    if _is_trailer_family_bt and _full_pickup_nodes:
        if not _staging_bt and _map_id_bt:
            # near_node = node lấy-đầy CUỐI CÙNG — xe sẽ ĐI THẲNG từ đó tới staging,
            # nên "gần" phải tính từ đó (không phải vị trí xuất phát của cả lượt).
            _staging_bt = await _find_trailer_staging_node(
                str(_map_id_bt), near_node=_full_pickup_nodes[-1], exclude_agv=agv_id)
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

    from task_queue import STATUS_ERROR, STATUS_QUEUED
    if not dispatched and cmd.status == STATUS_ERROR:
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


@app.post("/api/execute/hook-confirm")
async def hook_confirm(request: Request):
    """Xác nhận móc hàng THỦ CÔNG (nút trên Web UI, sau khi người vận hành đã
    đưa xe hàng vào) — server tự chọn ĐÚNG lệnh theo loại AGV thay vì gửi cứng
    action_code=31 'Hạ móc' như trước (chỉ đúng cho rơ-moóc, SAI hướng với AGV
    kéo — xem line_agv_handler.confirm_hook_manual/_is_tow_agv để biết vì sao
    2 loại xe cần lệnh ngược nhau)."""
    from agv_registry import agv_registry
    from line_agv_handler import line_agv_handler
    body = await request.json()
    agv_id = str(body.get("agv_id", "")).strip()
    if not agv_id:
        raise HTTPException(400, "agv_id required")
    if not agv_registry.is_line(agv_id):
        raise HTTPException(400, "Chỉ hỗ trợ Line AGV")
    result = line_agv_handler.confirm_hook_manual(agv_id)
    if not result.get("ok"):
        raise HTTPException(400, result.get("error") or "Lỗi xác nhận móc")
    return {"ok": True, "agv_id": agv_id, **result}


class GateCommandRequest(BaseModel):
    door_num: str    # số thứ tự cửa (vd "1") — server tự ghép thành "gate1"
    cmd:      str    # "open" | "close"


@app.get("/api/execute/elevators")
async def execute_elevators():
    """Trạng thái runtime các thang máy (thiết bị báo + xe đang giữ + hàng đợi) — UI ghép với danh sách thang
    của bản đồ (mapData.elevators) theo id."""
    from elevator_coordinator import elevator_coordinator
    # status() có thể nạp bản đồ (ensure_map_loaded_sync chờ event loop) → chạy ở thread riêng, không chặn/đứng loop
    return {"elevators": await asyncio.to_thread(elevator_coordinator.status)}


# ── Danh mục thang đã khai báo (dùng chung cho điều khiển thủ công + Map Editor) ─────────────────────
# Bảng elevator_catalog: id (khớp elevator_id trong topic MQTT và trong Map Editor), tên, nhà máy, ghi chú.
# "Đã kết nối" lấy từ elevator_registry (connection/LWT hoặc tin state sống) — xem elevator_registry.py.
async def _ensure_elevator_catalog(conn) -> None:
    existed = await conn.fetchval("SELECT to_regclass('elevator_catalog') IS NOT NULL")
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS elevator_catalog (
            id TEXT PRIMARY KEY, name TEXT, factory TEXT DEFAULT '', note TEXT DEFAULT ''
        )""")
    if existed:      # chỉ nhập từ bản đồ MỘT LẦN khi tạo bảng (xoá hết thang thì không tự nhập lại)
        return
    # Lần đầu: gom các thang đã khai báo sẵn trong các bản đồ vào danh mục
    rows = await conn.fetch("SELECT elevators FROM agv_maps WHERE elevators IS NOT NULL")
    seen = {}
    for r in rows:
        raw = r["elevators"]
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except ValueError:
                continue
        for e in raw or []:
            if isinstance(e, dict) and e.get("id") and str(e["id"]) not in seen:
                seen[str(e["id"])] = (str(e.get("name") or e["id"])[:60], str(e.get("note") or "")[:300])
    for eid, (name, note) in seen.items():
        await conn.execute("INSERT INTO elevator_catalog (id, name, factory, note) VALUES ($1,$2,'',$3) "
                           "ON CONFLICT (id) DO NOTHING", eid, name, note)
    if seen:
        print(f"[ELEVATOR] Danh mục thang trống — đã nhập {len(seen)} thang từ bản đồ: {sorted(seen)}")


def _link_fields(eid: str, hub: dict) -> dict:
    """Trạng thái kết nối của 1 thang: ưu tiên thiết bị uelev/v2 (uelev_hub), không có thì elevator/v1 (elevator_registry)."""
    h = hub.get(eid)
    if h is not None:
        m = next((d for d in h["devices"] if d["device"] == h["master"]), None)
        link = "online" if h["online"] else (m["link"] if m else "never")
        return {"link_link": link, "link_online": h["online"], "link_source": "uelev/v2",
                "link_factory": ", ".join(h["factories"]), "link_last_seen_sec": m["last_seen_sec"] if m else None,
                "link_state": None, "link_level": h["floor"], "manual_hold": h["hold"], "ride_test": h.get("ride_test"), "devices": h["devices"], "factory_mixed": h["factory_mixed"]}
    from elevator_registry import elevator_registry
    info = elevator_registry.info(eid)
    return {**{f"link_{k}": v for k, v in info.items()}, "devices": [], "factory_mixed": False}


async def _elevator_catalog_view() -> dict:
    """Danh mục thang + kết nối (uelev/v2 hoặc elevator/v1) + tầng theo bản đồ đang nạp + thang mới phát hiện chưa khai báo."""
    from elevator_coordinator import elevator_coordinator
    from elevator_registry import elevator_registry
    from uelev_console import uelev_hub
    async with pool.acquire() as conn:
        await _ensure_elevator_catalog(conn)
        rows = await conn.fetch("SELECT id, name, factory, note FROM elevator_catalog ORDER BY id")
    runtime = {str(e["id"]): e for e in elevator_coordinator.status()}
    hub = uelev_hub.elevators()
    declared, ids = [], set()
    for r in rows:
        eid = r["id"]
        ids.add(eid)
        rt = runtime.get(eid) or {"id": eid, "state": None, "level": None, "floor": None, "owner": None,
                                  "phase": None, "queue": [], "floors": [], "hold": None}
        declared.append({**rt, "id": eid, "name": r["name"] or eid, "factory": r["factory"] or "",
                         "note": r["note"] or "", "in_map": eid in runtime, **_link_fields(eid, hub)})
    discovered = []
    for eid in sorted(set(hub) | set(elevator_registry.seen_ids())):
        if eid not in ids:
            f = _link_fields(eid, hub)
            discovered.append({"id": eid, **f, "factory": f["link_factory"]})
    return {"elevators": declared, "discovered": discovered}


class ElevatorCatalogRequest(BaseModel):
    id:      str
    name:    str = ""
    factory: str = ""
    note:    str = ""


@app.get("/api/elevators/catalog")
async def elevators_catalog_get():
    return await _elevator_catalog_view()


@app.post("/api/elevators/catalog")
async def elevators_catalog_save(req: ElevatorCatalogRequest):
    eid = req.id.strip()
    import re
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,40}", eid):
        raise HTTPException(400, "Mã thang chỉ gồm chữ, số, - _ . (tối đa 40 ký tự)")
    async with pool.acquire() as conn:
        await _ensure_elevator_catalog(conn)
        await conn.execute(
            "INSERT INTO elevator_catalog (id, name, factory, note) VALUES ($1,$2,$3,$4) "
            "ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name, factory=EXCLUDED.factory, note=EXCLUDED.note",
            eid, (req.name.strip() or eid)[:60], req.factory.strip()[:60], req.note.strip()[:300])
    return {"success": True, "id": eid}


# ── Điều khiển thang uelev/v2 (tách khỏi điều khiển thủ công AGV) ─────────────────────────────────────
class ElevatorActionRequest(BaseModel):
    elevator_id:  str
    device:       str = "master"        # master | call1, call2, ...
    action:       str                   # call_floor | depart | hold | release | fast_close | reset | hall_call | release_hall
    floor:        int | None = None     # call_floor / depart
    direction:    str | None = None     # hall_call: UP | DN
    duration_sec: float = 300.0         # hold: thời gian giữ cửa; depart: thời gian giữ cửa sau khi tới tầng
    close_on_end: bool = True           # hold: nhả + đóng nhanh khi hết giờ
    ttl_s:        int = 20              # hall_call: TTL relay (1..600 s) — hết TTL tự nhả (dead-man switch)
    force:        bool = False          # gửi cả khi thang đang phục vụ xe


class ElevatorRideTestRequest(BaseModel):
    elevator_id: str
    from_floor:  int            # tầng xe gọi thang
    to_floor:    int            # tầng xe đi tới
    board_s:     float = 3.5    # mô phỏng xe đi vào cabin
    exit_s:      float = 3.5    # mô phỏng xe đi ra khỏi cabin
    arrive_mode: str = "sensor"  # sensor (master tự báo tới) | timer (coi như tới sau travel_s) | manual (người vận hành bấm xác nhận)
    travel_s:    float = 10.0   # chế độ timer: thời gian thang chạy giữa các tầng
    force:       bool = False


@app.post("/api/elevator-console/ride-test")
async def elevator_console_ride_test(req: ElevatorRideTestRequest):
    """Bài test 1 chuyến xe đi thang (giả lập, không có AGV): gọi thang tới tầng A → mở cửa → trễ → đóng, đi tới tầng B →
    mở cửa → trễ → đóng. Chạy ở server, xem tiến trình qua ride_test trong /api/elevator-console/state."""
    from uelev_console import uelev_hub
    eid = req.elevator_id.strip()
    if req.from_floor == req.to_floor:
        raise HTTPException(400, "Tầng đi và tầng đến phải khác nhau")
    for f in (req.from_floor, req.to_floor):
        if f < -20 or f > 200:
            raise HTTPException(400, "Số tầng không hợp lệ")
    if not (0 <= req.board_s <= 30 and 0 <= req.exit_s <= 30):
        raise HTTPException(400, "Thời gian mô phỏng xe vào/ra phải từ 0 đến 30 giây")
    try:
        from elevator_coordinator import elevator_coordinator
        st = next((e for e in elevator_coordinator.status() if str(e.get("id")) == eid), None)
    except Exception:
        st = None
    if st and st.get("owner") and not req.force:
        raise HTTPException(409, f"Thang {eid} đang phục vụ xe {st['owner']} — chờ xe xong hoặc chọn gửi bất chấp")
    async with pool.acquire() as conn:
        await _ensure_elevator_catalog(conn)
        prefer = await conn.fetchval("SELECT factory FROM elevator_catalog WHERE id=$1", eid) or ""
    if not 1 <= req.travel_s <= 300:
        raise HTTPException(400, "Thời gian thang chạy phải từ 1 đến 300 giây")
    r = uelev_hub.start_ride_test(eid, req.from_floor, req.to_floor, req.board_s, req.exit_s, prefer,
                                  req.arrive_mode, req.travel_s)
    if not r.get("ok"):
        raise HTTPException(422, r.get("error") or "Không chạy được bài test")
    return {"success": True}


@app.post("/api/elevator-console/release-area")
async def elevator_console_release_area(req: ElevatorCatalogRequest):
    """Nhả KHÓA VÙNG thang bằng tay (xe trước kẹt/hỏng trong hành lang thang, xe sau đang xếp hàng chờ). body: {"id": mã thang}"""
    from elevator_coordinator import elevator_coordinator
    fn = getattr(elevator_coordinator, "release_area_manual", None)
    if fn is None:
        raise HTTPException(501, "Backend thang hiện không có khóa vùng thang (chỉ có ở uelev_v2)")
    return {"success": bool(fn(req.id.strip()))}


@app.post("/api/elevator-console/ride-test/confirm")
async def elevator_console_ride_test_confirm(req: ElevatorCatalogRequest):
    """Chế độ manual: người vận hành xác nhận thang đã tới tầng bài test đang chờ. body: {"id": "<mã thang>"}"""
    from uelev_console import uelev_hub
    return {"success": uelev_hub.confirm_arrival(req.id.strip())}


@app.post("/api/elevator-console/ride-test/cancel")
async def elevator_console_ride_test_cancel(req: ElevatorCatalogRequest):
    from uelev_console import uelev_hub
    return {"success": uelev_hub.cancel_ride_test(req.id.strip())}      # body: {"id": "<mã thang>"}


@app.get("/api/elevator-console/state")
async def elevator_console_state():
    view = await _elevator_catalog_view()
    try:
        from elevator_coordinator import elevator_coordinator
        bridge_active = (elevator_coordinator.__class__.__name__ != "ElevatorCoordinator"
                         and getattr(elevator_coordinator, "_coord", None) is not None)
    except Exception:
        bridge_active = False
    return {**view, "bridge_active": bridge_active, "time": time.time()}


@app.post("/api/elevator-console/action")
async def elevator_console_action(req: ElevatorActionRequest):
    """Lệnh tay tới thang thật (uelev/v2 instantActions). Thang đang phục vụ xe → 409 trừ khi force."""
    from uelev_console import uelev_hub, PULSE_MS, FAST_CLOSE_MS
    eid, dev, act = req.elevator_id.strip(), req.device.strip() or "master", req.action.strip().lower()
    if not eid:
        raise HTTPException(400, "Thiếu mã thang")
    master_acts = {"call_floor", "depart", "hold", "release", "fast_close", "reset"}
    caller_acts = {"hall_call", "release_hall", "reset"}
    if act not in master_acts | caller_acts:
        raise HTTPException(400, f"Lệnh không hỗ trợ: {act}")
    if dev == "master" and act not in master_acts or dev != "master" and act not in caller_acts:
        raise HTTPException(400, f"Lệnh '{act}' không dùng cho thiết bị {dev}")
    if act in ("call_floor", "depart") and (req.floor is None or req.floor < -20 or req.floor > 200):
        raise HTTPException(400, "Cần số tầng hợp lệ")
    if act == "hall_call" and (req.direction or "").upper() not in ("UP", "DN"):
        raise HTTPException(400, "direction phải là UP hoặc DN")
    if not 5 <= req.duration_sec <= 3600:
        raise HTTPException(400, "Thời gian phải từ 5 giây đến 60 phút")

    # thang đang phục vụ xe? (bridge uelev_v2 hoặc legacy)
    try:
        from elevator_coordinator import elevator_coordinator
        st = next((e for e in elevator_coordinator.status() if str(e.get("id")) == eid), None)
    except Exception:
        st = None
    if st and st.get("owner") and not req.force:
        raise HTTPException(409, f"Thang {eid} đang phục vụ xe {st['owner']} — chờ xe xong hoặc chọn gửi bất chấp")

    async with pool.acquire() as conn:
        await _ensure_elevator_catalog(conn)
        prefer = await conn.fetchval("SELECT factory FROM elevator_catalog WHERE id=$1", eid) or ""
    from elevator_coord import protocol as P
    if act == "hold":
        r = uelev_hub.hold(eid, req.duration_sec, req.close_on_end, prefer)
    elif act == "release":
        r = uelev_hub.release(eid, prefer, fast_close=req.close_on_end)
    else:
        if act in ("call_floor", "depart", "fast_close") and dev == "master":
            uelev_hub.drop_hold(eid)           # lệnh đi/đóng thay thế giữ cửa tay đang chạy
        if act == "call_floor":
            r = uelev_hub.send(eid, dev, P.ACT_CALL_FLOOR, {"floor": req.floor, "pulseMs": PULSE_MS}, prefer)
        elif act == "depart":
            # thang ĐÃ ở tầng đích thì depart bị từ chối (already_at_floor) → go_to tự chuyển sang giữ cửa tại chỗ
            r = uelev_hub.go_to(eid, req.floor, req.duration_sec, prefer)
        elif act == "fast_close":
            m = uelev_hub._master_json(eid, prefer)
            if m and m.get("door_hold"):        # đang giữ cửa: fastClose bị từ chối (door_hold_active) → nhả rồi đóng nhanh
                r = uelev_hub.release(eid, prefer, fast_close=True)
            else:
                r = uelev_hub.send(eid, dev, P.ACT_FAST_CLOSE, {"durationMs": FAST_CLOSE_MS}, prefer)
        elif act == "hall_call":
            if not 1 <= req.ttl_s <= 600:
                raise HTTPException(400, "TTL gọi thang phải từ 1 đến 600 giây")
            r = uelev_hub.send(eid, dev, P.ACT_HALL_CALL, {"direction": req.direction.upper(), "ttlS": req.ttl_s}, prefer)
        elif act == "release_hall":
            r = uelev_hub.send(eid, dev, P.ACT_RELEASE_HALL, None, prefer)
        else:
            r = uelev_hub.send(eid, dev, P.ACT_RESET, None, prefer)
    if not r.get("ok"):
        if r.get("error"):      # thiết bị chưa từng báo tin trên broker → không biết factory/topic để gửi
            raise HTTPException(422, f"{r['error']}. Kiểm tra mã thang trong danh mục có trùng mã trên topic MQTT không (vd ELV01).")
        raise HTTPException(502, "Gửi lệnh MQTT thất bại (server chưa kết nối broker?)")
    return {"success": True, **r}


@app.delete("/api/elevators/catalog/{elevator_id}")
async def elevators_catalog_delete(elevator_id: str):
    async with pool.acquire() as conn:
        await _ensure_elevator_catalog(conn)
        await conn.execute("DELETE FROM elevator_catalog WHERE id=$1", elevator_id)
    return {"success": True, "id": elevator_id}


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


class ElevatorCommandRequest(BaseModel):
    elevator_id: str          # id thang trong Map Editor (vd "E1")
    cmd:         str          # "open" | "close"
    floor:       int | None = None   # số tầng (level) — bắt buộc với "open": thang đi tới tầng đó rồi mở cửa
    force:       bool = False        # gửi cả khi thang đang phục vụ xe (có thể làm hỏng chuyến đi của xe)


@app.post("/api/execute/elevator-command")
async def execute_elevator_command(req: ElevatorCommandRequest):
    """
    Điều khiển THỦ CÔNG thang máy — dùng cho Điều khiển thủ công (Quản lý AGV) để thử kết nối thiết bị thang.
    Gửi THẲNG lệnh elevator/v1 (open kèm số tầng | close) tới bộ điều khiển thang, giống /gate-command, KHÔNG đi
    qua chuỗi đi thang của xe. Thang đang phục vụ một xe thì từ chối (409) trừ khi force=true.
    Trạng thái thang báo về qua GET /api/execute/elevators.
    """
    from elevator_coordinator import elevator_coordinator
    eid = req.elevator_id.strip()
    cmd = req.cmd.strip().lower()
    if not eid:
        raise HTTPException(400, "Thiếu id thang")
    if cmd not in ("open", "close"):
        raise HTTPException(400, "cmd phải là 'open' hoặc 'close'")
    if cmd == "open" and (req.floor is None or req.floor < 0):
        raise HTTPException(400, "Lệnh mở cần số tầng (level) hợp lệ")
    if elevator_coordinator.__class__.__name__ != "ElevatorCoordinator":
        # backend uelev/v2 nói giao thức khác (elevator_coord), không nhận lệnh elevator/v1 thô
        raise HTTPException(501, "Backend thang hiện là uelev_v2 — điều khiển thủ công chỉ hỗ trợ giao thức elevator/v1")
    st = next((e for e in elevator_coordinator.status() if str(e.get("id")) == eid), None)
    if st and st.get("owner") and not req.force:
        raise HTTPException(409, f"Thang {eid} đang phục vụ xe {st['owner']} — chờ xe xong hoặc chọn gửi bất chấp")

    from mqtt_client import send_elevator_command
    elevator_coordinator.release_hold(eid, close=False, why="có lệnh điều khiển tay mới")   # lệnh tay thay thế giữ cửa cũ
    ok = send_elevator_command(eid, cmd, req.floor if cmd == "open" else None)
    return {"success": ok, "elevator_id": eid, "cmd": cmd, "floor": req.floor if cmd == "open" else None}


class ElevatorHoldRequest(BaseModel):
    elevator_id:  str
    action:       str = "start"       # "start" | "release"
    floor:        int | None = None   # số tầng (level) cần giữ cửa mở (bắt buộc khi start)
    duration_sec: float = 300.0       # thời gian giữ tối đa (5 phút mặc định)
    close_on_end: bool = True         # đóng cửa khi hết giờ / khi thả


@app.post("/api/execute/elevator-hold")
async def execute_elevator_hold(req: ElevatorHoldRequest):
    """
    Giữ cửa thang MỞ thủ công (xe mất mạng/chưa có xe thật): thang đi tới tầng `floor`, mở cửa và giữ mở tới khi hết giờ
    hoặc thả (action="release"). Giữ bằng cách gửi lại "open" định kỳ trong luồng riêng (không phụ thuộc xe nào online).
    Tự thả khi xe bắt đầu chuyến đi thang hoặc thiết bị báo lỗi. Chỉ hỗ trợ backend elevator/v1.
    """
    from elevator_coordinator import elevator_coordinator
    eid = req.elevator_id.strip()
    act = req.action.strip().lower()
    if not eid:
        raise HTTPException(400, "Thiếu id thang")
    if elevator_coordinator.__class__.__name__ != "ElevatorCoordinator":
        raise HTTPException(501, "Backend thang hiện là uelev_v2 — giữ cửa thủ công chỉ hỗ trợ giao thức elevator/v1")
    if act == "release":
        was = elevator_coordinator.release_hold(eid, why="người vận hành thả")
        return {"success": True, "elevator_id": eid, "released": was}
    if act != "start":
        raise HTTPException(400, "action phải là 'start' hoặc 'release'")
    if req.floor is None or req.floor < 0:
        raise HTTPException(400, "Cần số tầng (level) hợp lệ để giữ cửa")
    if not 5 <= req.duration_sec <= 3600:
        raise HTTPException(400, "Thời gian giữ phải từ 5 giây đến 60 phút")
    st = next((e for e in elevator_coordinator.status() if str(e.get("id")) == eid), None)
    if st and st.get("owner") and st.get("phase") in ("close", "move", "exit"):
        raise HTTPException(409, f"Thang {eid} đang chạy chuyến của xe {st['owner']} — không giữ cửa lúc này")
    res = elevator_coordinator.hold_door(eid, req.floor, req.duration_sec, req.close_on_end)
    if not res.get("ok"):
        raise HTTPException(409, res.get("error") or "Không giữ cửa được")
    return {"success": True, "elevator_id": eid, **res}


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


@app.post("/api/execute/external-alert")
async def execute_external_alert(request: Request):
    """Nhận cảnh báo từ TIẾN TRÌNH NGOÀI (vd mqtt_Server/simulation/sim_monitor.py
    — theo dõi MQTT độc lập, KHÔNG chung process với server) để hiện NGAY lên
    map/UI (marker đỏ, xem LineAGVHandler.set_external_alert) — dùng TTL
    (`ttl_sec`, mặc định 8s) tự hết nếu không được gọi lại, vì bên ngoài
    không có cách nào báo CHÍNH XÁC lúc vi phạm kết thúc."""
    from line_agv_handler import line_agv_handler
    body = await request.json()
    agv_id  = str(body.get("agv_id", "")).strip()
    kind    = str(body.get("kind", "")).strip()
    message = str(body.get("message", "")).strip()
    ttl_sec = float(body.get("ttl_sec", 8.0))
    if not agv_id or not kind or not message:
        raise HTTPException(400, "agv_id, kind, message là bắt buộc")
    line_agv_handler.set_external_alert(agv_id, kind, message, ttl_sec)
    return {"ok": True}


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
    Xác nhận lifecycle event (lấy hàng / giao hàng) — dùng chung cho cả Line AGV
    và VDA5050. Gọi khi người dùng nhấn "Đã lấy hàng" / "Đã giao hàng xong".
    → Xoá trạng thái chờ + gọi on_agv_completed để dispatch lệnh tiếp theo trong queue.
    """
    from agv_registry import agv_registry
    from task_queue import agv_task_queue
    agv_id = agv_id.strip()

    if not agv_registry.is_line(agv_id):
        # ── VDA5050: pending_confirm_node (xem agv_manager.py + _dispatch_go_to) ──
        pending = agv_manager.get_pending_confirm(agv_id)
        if not pending:
            raise HTTPException(400, "AGV không ở trạng thái chờ xác nhận (PICKUP/DROP)")
        agv_manager.set_pending_confirm(agv_id, None)
        await asyncio.to_thread(agv_task_queue.on_agv_completed, agv_id, notes=f"lifecycle:vda5050:{pending}:confirmed")  # luồng riêng: auto-dispatch chờ lại chính event loop
        print(f"[LIFECYCLE] {agv_id}: confirmed tại node {pending} (VDA5050) via UI")
        return {"success": True, "agv_id": agv_id, "confirmed": pending}

    from line_agv_handler import line_agv_handler
    state = line_agv_handler.state_store.get(agv_id)
    if not state:
        raise HTTPException(404, f"AGV '{agv_id}' không có trạng thái")
    if not state.task_lifecycle:
        raise HTTPException(400, "AGV không ở trạng thái lifecycle (picking/delivering)")
    lc = state.task_lifecycle
    state.task_lifecycle = None
    # Ack TRỄ của bước lấy/giao hàng cũ đến khi xe đã chạy lệnh "Về trạm / Về chờ" mới: KHÔNG được xoá
    # route + đóng lệnh đó (xe sẽ bị bỏ lại giữa hành lang, không về tới trạm — mô phỏng 2026-11-03:
    # SIM01/SIM06 đứng ở 23/24 chặn đường rơ-moóc, cả đội đứng im). Chỉ dọn cờ lifecycle.
    _run_ack = agv_task_queue._running.get(agv_id)
    _rt_ack = line_agv_handler.get_route(agv_id)
    _ack_special = (_run_ack is not None and getattr(_run_ack, "command", None) in ("go_charge", "go_wait"))
    # Lệnh "Về trạm" gọi qua API /api/agv/go-charge KHÔNG đi qua hàng đợi (_running trống) nhưng xe có route
    # task_type='return_charge' đang chạy → cũng không được xoá route đó (xe về tới trạm mà không vào trạng thái sạc).
    _ack_special = _ack_special or (_rt_ack is not None and getattr(_rt_ack, "task_type", "") == "return_charge")
    if _ack_special:
        print(f"[LIFECYCLE] {agv_id}: bỏ qua ack '{lc}' trễ — xe đang chạy lệnh/route Về trạm")
        return {"success": True, "agv_id": agv_id, "confirmed": lc, "ignored": "running_special_cmd"}
    # Xóa route để animated arrow dừng ngay
    line_agv_handler.clear_route(agv_id)
    await asyncio.to_thread(agv_task_queue.on_agv_completed, agv_id, notes=f"lifecycle:{lc}:confirmed")  # luồng riêng: auto-dispatch chờ lại chính event loop
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
                        INSERT INTO agv_devices (name, agv_type, ip, port, map_id, factory, last_seen, subnet, gateway, dns, can_reverse,
                                                 op_mode, return_mode)
                        SELECT %s, agv_type, ip, port, map_id, %s, last_seen, subnet, gateway, dns, can_reverse,
                               op_mode, return_mode
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


class AgvOpModeRequest(BaseModel):
    agv_id:      str
    op_mode:     str = "roundtrip"   # roundtrip | carry_hook | carry_fixed
    return_mode: str = "charge"      # charge | drop_cart


@app.post("/api/agv/update-op-mode")
async def update_agv_op_mode(req: AgvOpModeRequest):
    """Đặt chế độ vận hành cho xe kéo (tow/trailer) — xem agv_registry.op_mode."""
    import psycopg2, os as _os
    from agv_registry import agv_registry as _reg
    agv_id = req.agv_id.strip()
    if req.op_mode not in _reg.OP_MODES:
        raise HTTPException(status_code=400, detail=f"op_mode phải là một trong {_reg.OP_MODES}")
    if req.return_mode not in _reg.RETURN_MODES:
        raise HTTPException(status_code=400, detail=f"return_mode phải là một trong {_reg.RETURN_MODES}")
    # drop_cart chỉ có nghĩa khi xe kéo xe hàng bằng móc
    return_mode = req.return_mode if req.op_mode == "carry_hook" else "charge"
    _DB = _os.getenv("DATABASE_URL", "postgresql://postgres:ducmanh1801@localhost:5432/TOT_AGV")

    def _run():
        conn = psycopg2.connect(_DB)
        try:
            with conn.cursor() as cur:
                cur.execute("UPDATE agv_devices SET op_mode = %s, return_mode = %s WHERE name = %s",
                            (req.op_mode, return_mode, agv_id))
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
        _reg.load_op_mode()
        return {"success": True, "agv_id": agv_id, "op_mode": req.op_mode, "return_mode": return_mode}
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

                # status='error' = dispatch lỗi TỰ ĐỘNG (không phải người dùng bấm Hủy) —
                # loại hẳn khỏi mọi số liệu thống kê (kể cả total), theo yêu cầu "Thất
                # bại"/"Hủy" chỉ tính khi có người chủ động bấm Hủy.
                err_clause = "AND status != 'error'"

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
                    WHERE DATE(queued_at) BETWEEN %s AND %s {agv_clause} {err_clause}
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
                    WHERE DATE(queued_at) BETWEEN %s AND %s {agv_clause} {err_clause}
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
                    WHERE DATE(queued_at) BETWEEN %s AND %s {agv_clause} {err_clause}
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
                    WHERE DATE(queued_at) BETWEEN %s AND %s {agv_clause} {err_clause}
                    GROUP BY agv_id ORDER BY total DESC
                """, base_params)
                by_agv = [
                    {"agv_id": r[0], "total": int(r[1]),
                     "completed": int(r[2]), "failed": int(r[3])}
                    for r in cur.fetchall()
                ]

                # ── 5. Top Tổ nhận hàng (chỉ điểm DROPOFF có gán Tổ — bỏ qua điểm
                # lấy hàng/pickup). KHÔNG join theo agv_devices.map_id — giá trị đó có
                # thể lệch/cũ so với map thật của lịch sử task (đã xác nhận thực tế:
                # map_id trong agv_devices khác map_id chứa node trong agv_map_points).
                # Có 2 kiểu cấu hình Tổ trên node, gộp cả 2 (UNION ALL):
                #   1. Node "team" thường (agvCompat thường): action->>'team'
                #   2. Node rơ-moóc (trailer_role): action->'trailer_drop_teams' — MẢNG
                #      nhiều Tổ cùng lúc, CHỈ lấy trailer_role='drop' (trả hàng),
                #      bỏ 'pickup' (lấy rơ-moóc) theo đúng yêu cầu.
                dest_agv_clause = "AND te.agv_id = %s" if agv_id else ""
                _dest_params = base_params + base_params
                cur.execute(f"""
                    SELECT team, COUNT(*) AS cnt FROM (
                        SELECT (mp.action->>'team')::int AS team
                        FROM agv_task_executions te
                        JOIN agv_map_points mp ON mp.name_id = te.dest_node
                        WHERE DATE(te.queued_at) BETWEEN %s AND %s
                          AND te.dest_node IS NOT NULL AND te.dest_node <> '' {dest_agv_clause}
                          AND mp.action->>'locationType' = 'DROPOFF'
                          AND mp.action->>'team' IS NOT NULL

                        UNION ALL

                        SELECT team_elem::int AS team
                        FROM agv_task_executions te
                        JOIN agv_map_points mp ON mp.name_id = te.dest_node
                        CROSS JOIN LATERAL jsonb_array_elements_text(mp.action->'trailer_drop_teams') AS team_elem
                        WHERE DATE(te.queued_at) BETWEEN %s AND %s
                          AND te.dest_node IS NOT NULL AND te.dest_node <> '' {dest_agv_clause}
                          AND mp.action->>'locationType' = 'DROPOFF'
                          AND mp.action->>'trailer_role' = 'drop'
                    ) x
                    GROUP BY team ORDER BY cnt DESC LIMIT 10
                """, _dest_params)
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
                      AND status != 'error'
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
        _reg.load_op_mode()
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


class MqttLocalConfigRequest(BaseModel):
    host:     str
    port:     int
    user:     str = ""
    password: str | None = None   # None/bỏ trống = giữ mật khẩu đang lưu


@app.post("/api/config/mqtt-local")
async def api_set_mqtt_local(req: MqttLocalConfigRequest):
    """Lưu địa chỉ + tài khoản broker LOCAL (mạng LAN riêng của nhà máy). Đang ở chế độ local thì kết nối lại ngay
    theo cấu hình mới; đang ở cloud thì chỉ lưu, dùng khi chuyển sang local."""
    result = await asyncio.to_thread(set_local_broker_config, req.host, req.port, req.user, req.password or None)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


class FactoryConfigRequest(BaseModel):
    factory: str
    apply_agvs: bool = True      # gán luôn factory này cho mọi xe đã đăng ký trong DB


@app.get("/api/config/factory")
async def api_get_factory():
    """Môi trường nhà máy (factory) đang hiệu lực, nguồn của nó, và factory từng xe để phát hiện lệch."""
    return await asyncio.to_thread(get_factory_config)


@app.post("/api/config/factory")
async def api_set_factory(req: FactoryConfigRequest):
    """Đặt factory (vd tngfh): lưu cấu hình, gán cho các xe, xoá retained presence cũ, kết nối lại MQTT."""
    result = await asyncio.to_thread(set_factory_config, req.factory, req.apply_agvs)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "không đổi được factory")
    return result


@app.post("/api/config/mqtt-local/test")
async def api_test_mqtt_local(req: MqttLocalConfigRequest):
    """Thử nối tới broker theo thông tin nhập (không đổi kết nối đang chạy, không lưu)."""
    return await asyncio.to_thread(test_broker_connection, req.host, req.port, req.user, req.password or None)


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


# ══════════════════════════════════════════════════════════════════════════
# Giám sát tín hiệu WiFi 5GHz (thiết bị ESP32-C5)
# Ngưỡng dùng để suy ra trạng thái hiện tại của thiết bị ở /api/wifi/devices —
# việc quyết định khi nào gửi cảnh báo weak_signal/outage_start/recovered là
# do chính firmware ESP32 tự làm (máy trạng thái cục bộ), server chỉ lưu lại.
# ══════════════════════════════════════════════════════════════════════════
WIFI_RSSI_GOOD_THRESHOLD = -65   # dBm, >= mức này coi là tín hiệu tốt
WIFI_RSSI_WEAK_THRESHOLD = -70   # dBm, < mức này coi là tín hiệu yếu
WIFI_DEVICE_STALE_SECONDS = 120  # mẫu cuối cũ hơn mức này → coi là offline


class WifiSampleIn(BaseModel):
    device_id: str
    rssi: int
    ssid: str | None = None
    channel: int | None = None
    band: str = "5GHz"
    bssid: str | None = None       # MAC của AP đang kết nối — phục vụ quản lý roaming AGV
    noise_floor: int | None = None  # dBm, đo thưa hơn rssi (~60s/lần) — dùng tính SNR


class WifiEventIn(BaseModel):
    device_id: str
    event_type: str   # weak_signal | outage_start | recovered | disconnected | reconnected | roamed
    rssi: int | None = None
    consecutive_count: int | None = None
    outage_seconds: int | None = None
    old_bssid: str | None = None   # chỉ dùng khi event_type == 'roamed'
    new_bssid: str | None = None


@app.post("/api/wifi/report")
async def wifi_report(body: WifiSampleIn):
    """Nhận 1 mẫu cường độ tín hiệu WiFi (RSSI) liên tục từ thiết bị ESP32-C5.
    Đây là nguồn dữ liệu cho biểu đồ 'phổ tín hiệu' trên dashboard."""
    import psycopg2, os

    DB_URL = os.getenv("DATABASE_URL", "postgresql://postgres:ducmanh1801@localhost:5432/TOT_AGV")

    def _run():
        conn = psycopg2.connect(DB_URL)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO wifi_signal_samples (device_id, rssi, ssid, channel, band, bssid, noise_floor) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (body.device_id, body.rssi, body.ssid, body.channel, body.band,
                     body.bssid, body.noise_floor),
                )
            conn.commit()
        finally:
            conn.close()

    try:
        await asyncio.to_thread(_run)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/wifi/alert")
async def wifi_alert(body: WifiEventIn):
    """Nhận 1 sự kiện tín hiệu WiFi (tín hiệu yếu / bắt đầu outage / đã phục
    hồi / mất kết nối / kết nối lại) từ thiết bị ESP32-C5."""
    import psycopg2, os

    DB_URL = os.getenv("DATABASE_URL", "postgresql://postgres:ducmanh1801@localhost:5432/TOT_AGV")

    def _run():
        conn = psycopg2.connect(DB_URL)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO wifi_signal_events "
                    "(device_id, event_type, rssi, consecutive_count, outage_seconds, old_bssid, new_bssid) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (body.device_id, body.event_type, body.rssi,
                     body.consecutive_count, body.outage_seconds,
                     body.old_bssid, body.new_bssid),
                )
            conn.commit()
        finally:
            conn.close()

    try:
        await asyncio.to_thread(_run)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/wifi/history")
async def wifi_history(device_id: str, hours: int = 24,
                        date_from: str | None = None, date_to: str | None = None):
    """Lịch sử mẫu RSSI + sự kiện của 1 thiết bị, dùng để vẽ biểu đồ phổ tín
    hiệu trên dashboard. Lọc theo `hours` (N giờ gần nhất) mặc định, hoặc
    theo khoảng thời gian tuyệt đối `date_from`/`date_to` (ISO 8601, ưu
    tiên hơn `hours` nếu cả 2 đều có mặt)."""
    import psycopg2, os

    DB_URL = os.getenv("DATABASE_URL", "postgresql://postgres:ducmanh1801@localhost:5432/TOT_AGV")

    if date_from and date_to:
        time_clause = "recorded_at >= %s AND recorded_at <= %s"
        time_params = (date_from, date_to)
    else:
        time_clause = "recorded_at >= NOW() - (%s || ' hours')::interval"
        time_params = (hours,)

    def _run():
        conn = psycopg2.connect(DB_URL)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT rssi, ssid, channel, band, recorded_at, bssid, noise_floor "
                    "FROM wifi_signal_samples "
                    f"WHERE device_id = %s AND {time_clause} "
                    "ORDER BY recorded_at ASC",
                    (device_id, *time_params),
                )
                samples = [
                    {"rssi": r[0], "ssid": r[1], "channel": r[2], "band": r[3],
                     "recorded_at": r[4].isoformat(), "bssid": r[5], "noise_floor": r[6]}
                    for r in cur.fetchall()
                ]
                cur.execute(
                    "SELECT event_type, rssi, consecutive_count, outage_seconds, recorded_at, "
                    "old_bssid, new_bssid "
                    "FROM wifi_signal_events "
                    f"WHERE device_id = %s AND {time_clause} "
                    "ORDER BY recorded_at ASC",
                    (device_id, *time_params),
                )
                events = [
                    {"event_type": r[0], "rssi": r[1], "consecutive_count": r[2],
                     "outage_seconds": r[3], "recorded_at": r[4].isoformat(),
                     "old_bssid": r[5], "new_bssid": r[6]}
                    for r in cur.fetchall()
                ]
            return {"samples": samples, "events": events}
        finally:
            conn.close()

    try:
        return await asyncio.to_thread(_run)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/wifi/devices")
async def wifi_devices():
    """Danh sách thiết bị giám sát WiFi kèm RSSI mới nhất và trạng thái hiện
    tại (good/weak/outage/offline), dùng cho dropdown lọc và dải trạng thái
    trực tiếp trên dashboard.

    'outage' lấy theo sự kiện outage_start/recovered mới nhất do chính
    firmware gửi lên (đúng nghĩa 'yếu kéo dài ≥ 5 lần cảnh báo liên tiếp'),
    không suy diễn lại từ ngưỡng RSSI thô — tránh lệch với máy trạng thái
    trên thiết bị."""
    import psycopg2, os
    from datetime import datetime, timezone

    DB_URL = os.getenv("DATABASE_URL", "postgresql://postgres:ducmanh1801@localhost:5432/TOT_AGV")

    def _run():
        conn = psycopg2.connect(DB_URL)
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT DISTINCT ON (device_id) device_id, rssi, ssid, recorded_at, bssid
                    FROM wifi_signal_samples
                    ORDER BY device_id, recorded_at DESC
                """)
                sample_rows = cur.fetchall()
                cur.execute("""
                    SELECT DISTINCT ON (device_id) device_id, event_type
                    FROM wifi_signal_events
                    WHERE event_type IN ('outage_start', 'recovered')
                    ORDER BY device_id, recorded_at DESC
                """)
                last_outage_event = {row[0]: row[1] for row in cur.fetchall()}
            devices = []
            now = datetime.now(timezone.utc)
            for device_id, rssi, ssid, recorded_at, bssid in sample_rows:
                age_s = (now - recorded_at).total_seconds()
                if age_s > WIFI_DEVICE_STALE_SECONDS:
                    state = "offline"
                elif last_outage_event.get(device_id) == "outage_start":
                    state = "outage"
                elif rssi >= WIFI_RSSI_GOOD_THRESHOLD:
                    state = "good"
                else:
                    state = "weak"
                devices.append({
                    "device_id": device_id, "rssi": rssi, "ssid": ssid, "bssid": bssid,
                    "state": state, "last_seen": recorded_at.isoformat(),
                })
            return {
                "devices": devices,
                "thresholds": {
                    "good": WIFI_RSSI_GOOD_THRESHOLD,
                    "weak": WIFI_RSSI_WEAK_THRESHOLD,
                },
            }
        finally:
            conn.close()

    try:
        return await asyncio.to_thread(_run)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=API_PORT, reload=True)
