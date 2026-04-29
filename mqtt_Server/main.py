# main.py - PHIÃŠN Báº¢N HOÃ€N CHá»ˆNH 2025 - REAL-TIME ÄA CLIENT + BROADCAST Má»ŒI Sá»° KIá»†N
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Request, WebSocket
from pydantic import BaseModel
from fastapi.responses import StreamingResponse, FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import sys
# Äáº£m báº£o import Ä‘Æ°á»£c cÃ¡c module ná»™i bá»™ khi cháº¡y tá»« thÆ° má»¥c gá»‘c
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
from model import MoveCommand, ActionRequest
import zoneinfo as ZonInfo
import base64
import os
from map_manager import MapManager
from mqtt_client import start_mqtt, send_order, agv_manager, send_instant_action
from order_builder import build_order
from traffic_core import Edge, HealthState, Node, RerouteStrategy, Telemetry, TopologyMap, TrafficEngine, TrafficState
from contextlib import asynccontextmanager
from pathlib import Path
import sys

# báº£o Ä‘áº£m import Ä‘Æ°á»£c Web_UI khi cháº¡y tá»« mqtt_Server
import asyncio
import uuid
import asyncpg
import io
import time
import uvicorn
import base64
import networkx as nx
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from typing import List, Dict
import json

# ==========================
# KHá»žI Táº O MANAGER
# ==========================
map_manager = MapManager()
class EdgeCoordinator:
    """
    Äiá»u phá»‘i trÃ¡nh xung Ä‘á»™t: khÃ³a edge theo AGV.
    ÄÆ¡n giáº£n: khÃ³a edge 2 chiá»u (graph undirected) cho tá»›i khi AGV nháº­n lá»‡nh má»›i.
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
        """TÃ¬m Ä‘Æ°á»ng trÃ¡nh cÃ¡c edge Ä‘ang bá»‹ khÃ³a bá»Ÿi AGV khÃ¡c."""
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
traffic_engine = TrafficEngine()
current_agv_pos = {"x": None, "y": None, "theta": 0, "map_id": None}
_last_traffic_log_signature: dict[str, tuple] = {}
_preview_sync_guard: dict[str, dict[str, object]] = {}
_preview_motion_memory: dict[str, dict[str, object]] = {}
PREVIEW_SYNC_GUARD_SEC = 2.5
_preview_rejection_memory: dict[str, dict[str, object]] = {}
PREVIEW_FORCE_RESYNC_REPEAT = 3
PREVIEW_FORCE_RESYNC_SEC = 2.5
ORDER_DEDUPE_WINDOW_SEC = 1.5
_recent_order_cache: dict[tuple[str, str, str, tuple[str, ...]], dict[str, object]] = {}

class ReleaseRequest(BaseModel):
    agv_id: str


def _log_traffic_once(key: str, signature: tuple, message: str) -> None:
    if _last_traffic_log_signature.get(key) == signature:
        return
    _last_traffic_log_signature[key] = signature
    print(message)


def _order_dedupe_key(agv_id: str, map_id: str, destination: str, requested_path: List[str]) -> tuple[str, str, str, tuple[str, ...]]:
    return (str(agv_id), str(map_id), str(destination), tuple(str(node) for node in requested_path))


def _remember_order_result(key: tuple[str, str, str, tuple[str, ...]], response: dict) -> None:
    _recent_order_cache[key] = {
        "ts": time.monotonic(),
        "response": dict(response),
    }


def _get_recent_order_result(key: tuple[str, str, str, tuple[str, ...]]) -> dict | None:
    cached = _recent_order_cache.get(key)
    if not cached:
        return None
    age = time.monotonic() - float(cached.get("ts", 0.0))
    if age > ORDER_DEDUPE_WINDOW_SEC:
        _recent_order_cache.pop(key, None)
        return None
    response = dict(cached.get("response", {}))
    response["status"] = "Duplicate order ignored"
    response["deduplicated"] = True
    return response


def _edge_is_bidirectional(move_direction) -> bool:
    return move_direction in (None, "", 0, "0", 2, "2", "BOTH", "BIDIRECTIONAL", "TWO_WAY")


def _telemetry_health_state(state_data: dict) -> HealthState:
    if state_data.get("error"):
        return HealthState.ERROR
    last_update = state_data.get("last_update")
    if last_update:
        try:
            ts = datetime.fromisoformat(str(last_update).replace("Z", "+00:00"))
            if datetime.now(timezone.utc) - ts > timedelta(seconds=OFFLINE_THRESHOLD_SEC):
                return HealthState.OFFLINE
        except Exception:
            pass
    return HealthState.OK


def _telemetry_traffic_state(state_data: dict) -> TrafficState:
    if state_data.get("paused"):
        return TrafficState.WAITING
    if state_data.get("orderId"):
        return TrafficState.MOVING
    return TrafficState.IDLE


def _build_route_path(route) -> list:
    return [route.start_node] + [segment.to_node for segment in route.segments]


def _normalize_node_token(value) -> str:
    text = str(value or "").strip()
    if len(text) >= 2 and text[0] in {"N", "n"} and text[1:].isdigit():
        return text[1:]
    return text


def _dedupe_consecutive_nodes(path: list[str]) -> list[str]:
    result: list[str] = []
    for node_id in path:
        node_text = _normalize_node_token(node_id)
        if not node_text:
            continue
        if result and result[-1] == node_text:
            continue
        result.append(node_text)
    return result


def _to_vda_node_token(value) -> str:
    text = str(value or "").strip()
    if not text:
        return text
    if len(text) >= 2 and text[0] in {"N", "n"} and text[1:].isdigit():
        return f"N{text[1:]}"
    if text.isdigit():
        return f"N{text}"
    return text


def _to_vda_path(path: list[str]) -> list[str]:
    return [_to_vda_node_token(node_id) for node_id in _dedupe_consecutive_nodes(path) if _to_vda_node_token(node_id)]


def _to_vda_coords_lookup(coords_lookup: dict | None) -> dict:
    if not coords_lookup:
        return {}
    converted: dict = {}
    for node_id, coords in coords_lookup.items():
        converted[_to_vda_node_token(node_id)] = coords
    return converted


def _collapse_preview_backtracks(path: list[str]) -> list[str]:
    stack: list[str] = []
    for node_id in _dedupe_consecutive_nodes(path):
        if len(stack) >= 2 and node_id == stack[-2]:
            # Collapse immediate oscillation A->B->A that often appears in echoed
            # preview state while the AGV is rotating or confirming a reroute.
            stack.pop()
            continue
        if stack and stack[-1] == node_id:
            continue
        stack.append(node_id)
    return stack


def _simplify_preview_path(path: list[str]) -> list[str]:
    previous: list[str] | None = None
    current = _dedupe_consecutive_nodes(path)
    while previous != current:
        previous = current
        current = _collapse_preview_backtracks(current)
    return current


def _preview_path_has_excessive_loops(path: list[str]) -> bool:
    normalized = _dedupe_consecutive_nodes(path)
    if len(normalized) < 3:
        return False
    for idx in range(len(normalized) - 2):
        if normalized[idx] == normalized[idx + 2]:
            return True
    unique_count = len(set(normalized))
    if unique_count == 0:
        return False
    if len(normalized) >= unique_count * 2:
        return True
    repeated_nodes = sum(1 for node_id in set(normalized) if normalized.count(node_id) > 2)
    return repeated_nodes > 0


def _remember_local_route_override(agv_id: str, path: list[str], reason: str, hold_seconds: float = PREVIEW_SYNC_GUARD_SEC) -> None:
    _preview_sync_guard[agv_id] = {
        "until": time.time() + max(0.5, hold_seconds),
        "path": tuple(_dedupe_consecutive_nodes(path)),
        "reason": reason,
    }


def _route_nodes_from_state_path(route) -> list[str]:
    if route is None:
        return []
    return _dedupe_consecutive_nodes(_build_route_path(route))


def _first_hop(path: list[str]) -> tuple[str | None, str | None]:
    normalized = _dedupe_consecutive_nodes(path)
    if len(normalized) < 2:
        return None, None
    return normalized[0], normalized[1]


def _remember_motion_hint(agv_id: str, current_route, current_hint_node: str | None) -> None:
    route_nodes = _route_nodes_from_state_path(current_route)
    if not route_nodes:
        return

    hint = _normalize_node_token(current_hint_node)
    start_index = 0
    if hint and hint in route_nodes:
        start_index = route_nodes.index(hint)

    remaining = route_nodes[start_index:]
    if len(remaining) < 2:
        return

    _preview_motion_memory[agv_id] = {
        "route_nodes": tuple(route_nodes),
        "remaining_nodes": tuple(remaining),
        "expected_hop": (remaining[0], remaining[1]),
        "hint_node": hint,
        "updated_at": time.time(),
    }


def _preview_conflicts_with_current_route(agv_id: str, current_route, preview_path: list[str], current_hint_node: str | None) -> bool:
    normalized_preview = _dedupe_consecutive_nodes(preview_path)
    route_nodes = _route_nodes_from_state_path(current_route)
    if not route_nodes or len(normalized_preview) < 2:
        return False

    hint = _normalize_node_token(current_hint_node)
    remaining_route = route_nodes
    if hint and hint in route_nodes:
        idx = route_nodes.index(hint)
        remaining_route = route_nodes[idx:]

    if len(remaining_route) >= 2:
        expected_start, expected_next = remaining_route[0], remaining_route[1]
        preview_start, preview_next = normalized_preview[0], normalized_preview[1]

        # Reject immediate reverse hop: local expects A->B but preview says A->X (X != B)
        if preview_start == expected_start and preview_next != expected_next:
            return True

        # Reject preview that starts by stepping back to the previous route node
        if len(route_nodes) >= 2 and hint and hint in route_nodes:
            hint_idx = route_nodes.index(hint)
            if hint_idx > 0:
                previous_node = route_nodes[hint_idx - 1]
                if preview_start == hint and preview_next == previous_node:
                    return True

    # Reject preview that does not share the same forward prefix while a local route exists.
    shared_prefix = 0
    for left, right in zip(remaining_route, normalized_preview):
        if left != right:
            break
        shared_prefix += 1
    if shared_prefix == 0 and len(remaining_route) >= 2 and len(normalized_preview) >= 2:
        return True

    return False


def _preview_conflicts_with_motion_memory(agv_id: str, preview_path: list[str]) -> bool:
    memory = _preview_motion_memory.get(agv_id)
    if not memory:
        return False

    if time.time() - float(memory.get("updated_at", 0.0) or 0.0) > 3.0:
        return False

    normalized_preview = _dedupe_consecutive_nodes(preview_path)
    if len(normalized_preview) < 2:
        return False

    expected_hop = tuple(memory.get("expected_hop") or ())
    if len(expected_hop) != 2:
        return False

    preview_hop = (normalized_preview[0], normalized_preview[1])

    # If current local route says A->B, reject preview A->C
    if preview_hop[0] == expected_hop[0] and preview_hop[1] != expected_hop[1]:
        return True

    return False

def _remember_rejected_preview(agv_id: str, preview_path: list[str], current_hint_node: str | None) -> None:
    normalized_preview = tuple(_dedupe_consecutive_nodes(preview_path))
    if len(normalized_preview) < 2:
        return

    now = time.time()
    memory = _preview_rejection_memory.get(agv_id)

    if (
        memory
        and tuple(memory.get("path") or ()) == normalized_preview
        and str(memory.get("hint") or "") == str(current_hint_node or "")
        and now - float(memory.get("updated_at", 0.0) or 0.0) <= PREVIEW_FORCE_RESYNC_SEC
    ):
        memory["count"] = int(memory.get("count", 0)) + 1
        memory["updated_at"] = now
        return

    _preview_rejection_memory[agv_id] = {
        "path": normalized_preview,
        "hint": current_hint_node,
        "count": 1,
        "updated_at": now,
    }


def _clear_rejected_preview_memory(agv_id: str) -> None:
    _preview_rejection_memory.pop(agv_id, None)


def _should_force_resync_to_preview(agv_id: str, current_route, preview_path: list[str], current_hint_node: str | None) -> bool:
    memory = _preview_rejection_memory.get(agv_id)
    if not memory:
        return False

    now = time.time()
    if now - float(memory.get("updated_at", 0.0) or 0.0) > PREVIEW_FORCE_RESYNC_SEC:
        return False

    normalized_preview = tuple(_dedupe_consecutive_nodes(preview_path))
    if tuple(memory.get("path") or ()) != normalized_preview:
        return False

    if int(memory.get("count", 0)) < PREVIEW_FORCE_RESYNC_REPEAT:
        return False

    local_nodes = _route_nodes_from_state_path(current_route)
    hint = _normalize_node_token(current_hint_node)

    # Náº¿u hint hiá»‡n táº¡i khÃ´ng cÃ²n náº±m trÃªn local route,
    # hoáº·c náº±m trÃªn preview nhÆ°ng khÃ´ng thuá»™c prefix local,
    # thÃ¬ coi preview Ä‘Ã£ trá»Ÿ thÃ nh thá»±c táº¿ vÃ  force sync.
    if hint:
        if hint not in local_nodes and hint in normalized_preview:
            return True

        if hint in normalized_preview and hint in local_nodes:
            local_idx = local_nodes.index(hint)
            preview_idx = list(normalized_preview).index(hint)
            local_remaining = local_nodes[local_idx:]
            preview_remaining = list(normalized_preview)[preview_idx:]

            if local_remaining[:2] != preview_remaining[:2]:
                return True

    return False


def _should_accept_preview_sync(agv_id: str, current_route, preview_path: list[str], current_hint_node: str | None) -> bool:
    normalized_preview = _dedupe_consecutive_nodes(preview_path)
    if len(normalized_preview) < 2:
        return False
    if _preview_path_has_excessive_loops(normalized_preview):
        return False

    if current_route is None:
        return True

    guard = _preview_sync_guard.get(agv_id)
    if guard and float(guard.get("until", 0.0) or 0.0) > time.time():
        guarded_path = tuple(guard.get("path") or ())
        if guarded_path and tuple(normalized_preview) != guarded_path:
            return False

    local_nodes = _route_nodes_from_state_path(current_route)
    hint = _normalize_node_token(current_hint_node)

    if hint and hint in normalized_preview and hint not in local_nodes:
        return True

    if hint and hint in local_nodes and hint in normalized_preview:
        local_remaining = local_nodes[local_nodes.index(hint) :]
        preview_remaining = normalized_preview[normalized_preview.index(hint) :]
        if local_remaining[:2] == preview_remaining[:2]:
            return True

    if _preview_conflicts_with_current_route(agv_id, current_route, normalized_preview, current_hint_node):
        return False
    if _preview_conflicts_with_motion_memory(agv_id, normalized_preview):
        return False

    shared_prefix = 0
    for left, right in zip(local_nodes, normalized_preview):
        if left != right:
            break
        shared_prefix += 1
    return shared_prefix >= 1


def _parse_edge_preview(edge_state: dict) -> tuple[str | None, str | None]:
    start_node = edge_state.get("startNodeId")
    end_node = edge_state.get("endNodeId")
    if start_node and end_node:
        return _normalize_node_token(start_node), _normalize_node_token(end_node)
    edge_id = str(edge_state.get("edgeId") or "").strip()
    if "_to_" in edge_id:
        left, right = edge_id.split("_to_", 1)
        right = right.replace("__rev", "")
        if left and right:
            return left, right
    return None, None


def _extract_preview_path(state_data: dict) -> list[str]:
    last_node = _normalize_node_token(state_data.get("lastNodeId"))
    edge_states = sorted(
        [edge for edge in (state_data.get("edgeStates") or []) if isinstance(edge, dict)],
        key=lambda item: int(item.get("sequenceId", 10**9)),
    )
    node_states = sorted(
        [node for node in (state_data.get("nodeStates") or []) if isinstance(node, dict)],
        key=lambda item: int(item.get("sequenceId", 10**9)),
    )

    edge_path: list[str] = []
    for edge_state in edge_states:
        start_node, end_node = _parse_edge_preview(edge_state)
        if not start_node or not end_node:
            continue
        if not edge_path:
            edge_path.extend([start_node, end_node])
            continue
        if edge_path[-1] != start_node:
            edge_path.append(start_node)
        edge_path.append(end_node)
    edge_path = _dedupe_consecutive_nodes(edge_path)
    if edge_path:
        if last_node:
            if last_node in edge_path:
                edge_path = edge_path[edge_path.index(last_node) :]
            elif edge_path[0] != last_node:
                edge_path.insert(0, last_node)
        edge_path = _simplify_preview_path(edge_path)
        if len(edge_path) >= 2:
            return edge_path

    node_path = []
    if last_node:
        node_path.append(last_node)
    for node_state in node_states:
        node_id = _normalize_node_token(node_state.get("nodeId"))
        if not node_id:
            continue
        status = str(node_state.get("nodeStatus") or "").upper()
        if status in {"FINISHED", "DONE"} and node_id == last_node:
            continue
        node_path.append(node_id)
    node_path = _simplify_preview_path(node_path)
    return node_path if len(node_path) >= 2 else []


def _send_control_action_if_needed(agv_id: str, action: str | None):
    if action is None:
        return
    last_action = agv_manager.get_last_control_action(agv_id)
    if last_action == action:
        return
    send_instant_action(agv_id, action)
    agv_manager.set_last_control_action(agv_id, action)


def _clear_control_action(agv_id: str):
    agv_manager.set_last_control_action(agv_id, None)


def _send_route_order(agv_id: str, route, coords_lookup: dict, reason: str, order_id: str | None = None, order_update_id: int = 0):
    path = _build_route_path(route)
    agv = agv_manager.get_agv(agv_id) or {}
    final_order_id = order_id or str(uuid.uuid4())
    vda_path = _to_vda_path(path)
    vda_coords_lookup = _to_vda_coords_lookup(coords_lookup)
    order = build_order(
        agv_id=agv_id,
        path=vda_path,
        coords=vda_coords_lookup,
        manufacture=agv.get("manufacturer", "TNG:TOT"),
        SerialNumber=agv.get("serialNumber", agv_id),
        version="2.0",
        order_id=final_order_id,
        order_update_id=order_update_id,
        horizon=3,
    )
    agv_manager.set_order(agv_id, final_order_id, order_update_id)
    agv_manager.set_pending_path(agv_id, path)
    send_order(agv_id, order)
    return path, final_order_id


def _route_path_matches_pending(agv_id: str, path: list[str]) -> bool:
    pending_path = agv_manager.get_pending_path(agv_id) or []
    return _dedupe_consecutive_nodes(pending_path) == _dedupe_consecutive_nodes(path)


async def ensure_traffic_topology(map_id: str):
    if traffic_engine.has_map(map_id):
        return
    if pool is None:
        raise RuntimeError("Database pool not initialized")

    async with pool.acquire() as conn:
        point_rows = await conn.fetch(
            """
            SELECT name_id, x, y
            FROM agv_map_points
            WHERE map_id = $1
            """,
            map_id,
        )
        road_rows = await conn.fetch(
            """
            SELECT id_source, id_dest, distance, speed, move_direction
            FROM agv_map_roads
            WHERE map_id = $1
            """,
            map_id,
        )
        benzier_rows = await conn.fetch(
            """
            SELECT id_source, id_dest, speed, move_direction
            FROM agv_map_benziers
            WHERE map_id = $1
            """,
            map_id,
        )

    point_map = {str(row["name_id"]): (float(row["x"] or 0.0), float(row["y"] or 0.0)) for row in point_rows}
    node_ids = set(point_map.keys())
    for row in road_rows:
        node_ids.add(str(row["id_source"]))
        node_ids.add(str(row["id_dest"]))
    for row in benzier_rows:
        node_ids.add(str(row["id_source"]))
        node_ids.add(str(row["id_dest"]))

    nodes = [
        Node(node_id=node_id, x=point_map.get(node_id, (0.0, 0.0))[0], y=point_map.get(node_id, (0.0, 0.0))[1])
        for node_id in sorted(node_ids)
    ]
    edges = []
    for row in road_rows:
        src = str(row["id_source"])
        dst = str(row["id_dest"])
        edges.append(
            Edge(
                edge_id=f"{src}_to_{dst}",
                from_node=src,
                to_node=dst,
                length=float(row["distance"] or 1.0),
                max_speed=float(row["speed"] or 0.6),
                bidirectional=_edge_is_bidirectional(row["move_direction"]),
                physical_edge_id="::".join(sorted((src, dst))),
            )
        )
    for row in benzier_rows:
        src = str(row["id_source"])
        dst = str(row["id_dest"])
        sx, sy = point_map.get(src, (0.0, 0.0))
        dx, dy = point_map.get(dst, (0.0, 0.0))
        edges.append(
            Edge(
                edge_id=f"{src}_to_{dst}_curve",
                from_node=src,
                to_node=dst,
                length=max(((sx - dx) ** 2 + (sy - dy) ** 2) ** 0.5, 1.0),
                max_speed=float(row["speed"] or 0.4),
                bidirectional=_edge_is_bidirectional(row["move_direction"]),
                physical_edge_id="::".join(sorted((src, dst))),
            )
        )

    traffic_engine.set_topology(map_id, TopologyMap(nodes, edges))


async def handle_traffic_state_update(agv_id: str, state_data: dict):
    raw_map = state_data.get("map_id") or state_data.get("mapCurrent")
    if not raw_map or app.state.db_pool is None:
        return None

    resolved_map = await map_manager.resolve_map_id(app.state.db_pool, str(raw_map))
    map_id = resolved_map or str(raw_map)
    await map_manager.load_from_db(app.state.db_pool, map_id)
    await ensure_traffic_topology(map_id)

    current_route = traffic_engine.get_route(agv_id)
    current_hint_node = _normalize_node_token(state_data.get("lastNodeId"))

    if current_route is not None:
        _remember_motion_hint(agv_id, current_route, current_hint_node)

    current_route = traffic_engine.get_route(agv_id)
    current_hint_node = _normalize_node_token(state_data.get("lastNodeId"))
    preview_path = _extract_preview_path(state_data)

    # CHá»ˆ cho phÃ©p rehydrate tá»« preview khi CHÆ¯A cÃ³ active route
    accepted_preview = False
    if preview_path and _should_accept_preview_sync(agv_id, current_route, preview_path, current_hint_node):
        previous_path = _route_nodes_from_state_path(current_route)
        preview_route = traffic_engine.activate_route_from_node_path(
            agv_id=agv_id,
            map_id=map_id,
            node_path=preview_path,
            current_hint_node=str(current_hint_node) if current_hint_node else None,
            reason="STATE_PREVIEW_VDA5050" if current_route is None else "STATE_PREVIEW_SYNC",
        )
        if preview_route is not None:
            preview_edges = [segment.edge_id for segment in preview_route.segments]
            if current_route is None:
                print(
                    f"[TRAFFIC] RehydratedFromPreview | agv={agv_id} | map={map_id} "
                    f"| path={preview_path} | edges={preview_edges}"
                )
            elif previous_path != _build_route_path(preview_route):
                print(
                    f"[TRAFFIC] PreviewRouteSync | agv={agv_id} | map={map_id} "
                    f"| path={preview_path} | edges={preview_edges}"
                )
            current_route = preview_route
            _remember_motion_hint(agv_id, current_route, current_hint_node)
            _clear_rejected_preview_memory(agv_id)
            accepted_preview = True

        if not accepted_preview:
            _remember_rejected_preview(agv_id, preview_path, current_hint_node)

            if current_route is not None and _should_force_resync_to_preview(agv_id, current_route, preview_path, current_hint_node):
                recovery_route = traffic_engine.activate_route_from_node_path(
                    agv_id=agv_id,
                    map_id=map_id,
                    node_path=preview_path,
                    current_hint_node=str(current_hint_node) if current_hint_node else None,
                    reason="STATE_DIVERGENCE_RECOVERY",
                )
                if recovery_route is not None:
                    print(
                        f"[TRAFFIC] PreviewRouteRecovery | agv={agv_id} | map={map_id} "
                        f"| hint={current_hint_node} | preview={preview_path}"
                    )
                    current_route = recovery_route
                    _remember_motion_hint(agv_id, current_route, current_hint_node)
                    _clear_rejected_preview_memory(agv_id)
                    accepted_preview = True

        if not accepted_preview and current_route is not None:
            print(
                f"[TRAFFIC] PreviewRouteRejected | agv={agv_id} | map={map_id} "
                f"| hint={current_hint_node} | preview={preview_path} "
                f"| local={_route_nodes_from_state_path(current_route)}"
            )
                
    elif current_route is None:
        pending_path = agv_manager.get_pending_path(agv_id)
        if pending_path and len(pending_path) >= 2:
            normalized_pending_path = _dedupe_consecutive_nodes(pending_path)
            rehydrated = traffic_engine.activate_route_from_node_path(
                agv_id=agv_id,
                map_id=map_id,
                node_path=normalized_pending_path,
                current_hint_node=str(current_hint_node) if current_hint_node else None,
                reason="PENDING_PATH_REHYDRATE",
            )
            if rehydrated is not None:
                print(
                    f"[TRAFFIC] RehydratedRoute | agv={agv_id} | map={map_id} "
                    f"| edges={[segment.edge_id for segment in rehydrated.segments]}"
                )
                current_route = rehydrated
                _remember_motion_hint(agv_id, current_route, current_hint_node)
            else:
                print(
                    f"[TRAFFIC] RehydrateSkipped | agv={agv_id} | map={map_id} "
                    f"| current_hint={current_hint_node} | pending_path={normalized_pending_path}"
                )

    if current_route is None:
        pending_destination = agv_manager.get_pending_destination(agv_id)
        start_hint = _normalize_node_token(state_data.get("lastNodeId"))
        if pending_destination and start_hint:
            planner_result = traffic_engine.plan_route(
                map_id=str(map_id),
                agv_id=agv_id,
                start_node=start_hint,
                goal_node=_normalize_node_token(pending_destination["destination"]),
                reason="STATE_PENDING_DESTINATION",
            )
            if planner_result.success and planner_result.route is not None:
                traffic_engine.activate_route(agv_id, str(map_id), planner_result.route)
                agv_manager.set_pending_path(agv_id, planner_result.node_path)
                current_route = planner_result.route
                _remember_motion_hint(agv_id, current_route, start_hint)
                print(
                    f"[TRAFFIC] PlannedRouteFromPending | agv={agv_id} | map={map_id} "
                    f"| path={planner_result.node_path} | edges={planner_result.edge_path}"
                )

    timestamp_text = state_data.get("timestamp")
    timestamp_value = time.time()
    if timestamp_text:
        try:
            timestamp_value = datetime.fromisoformat(str(timestamp_text).replace("Z", "+00:00")).timestamp()
        except Exception:
            timestamp_value = time.time()

    telemetry = Telemetry(
        agv_id=agv_id,
        x=float(state_data.get("x", 0.0)),
        y=float(state_data.get("y", 0.0)),
        speed=float(((state_data.get("velocity") or {}).get("vx")) or 0.0),
        heading_deg=float(state_data.get("theta", 0.0)),
        timestamp=timestamp_value,
        health_state=_telemetry_health_state(state_data),
        traffic_state=_telemetry_traffic_state(state_data),
    )

    update = traffic_engine.handle_telemetry(map_id, telemetry)
    current_agv_pos.update({"x": telemetry.x, "y": telemetry.y, "theta": telemetry.heading_deg, "map_id": map_id})

    if update.decision:
        _log_traffic_once(
            f"decision:{agv_id}",
            (
                update.decision.action.value,
                update.decision.reason,
                update.decision.related_agv_id,
            ),
            f"[TRAFFIC] {agv_id} | action={update.decision.action.value} "
            f"| reason={update.decision.reason} | related={update.decision.related_agv_id}",
        )
    if update.reroute_request:
        _log_traffic_once(
            f"reroute_request:{agv_id}",
            (
                update.reroute_request.reason,
                tuple(update.reroute_request.avoid_edges),
                tuple(update.reroute_request.avoid_zones),
            ),
            f"[REROUTE] {agv_id} | reason={update.reroute_request.reason} "
            f"| avoid_edges={update.reroute_request.avoid_edges}",
        )
    if update.reroute_result:
        route_edges = []
        if update.reroute_result.route and update.reroute_result.route.segments:
            route_edges = [segment.edge_id for segment in update.reroute_result.route.segments]
        planner_message = (
            update.reroute_result.planner_result.message
            if update.reroute_result.planner_result
            else ""
        )
        _log_traffic_once(
            f"reroute_result:{agv_id}",
            (
                bool(update.reroute_result.success),
                update.reroute_result.strategy.value,
                update.reroute_result.reason,
                tuple(route_edges),
            ),
            f"[REROUTE RESULT] {agv_id} | success={update.reroute_result.success} "
            f"| strategy={update.reroute_result.strategy.value} | reason={update.reroute_result.reason} "
            f"| edges={route_edges} | planner={planner_message}",
        )

    if update.decision:
        control_action = None
        if update.decision.action.value in {"STOP", "WAIT"}:
            control_action = "PAUSE"
        elif update.decision.action.value == "PROCEED":
            control_action = "RESUME"
        _send_control_action_if_needed(agv_id, control_action)
        asyncio.create_task(
            broadcast_update(
                {
                    "type": "traffic_decision",
                    "agv_id": agv_id,
                    "map_id": map_id,
                    "action": update.decision.action.value,
                    "reason": update.decision.reason,
                    "timestamp": datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).isoformat(),
                }
            )
        )

    if (
        update.reroute_result
        and update.reroute_result.success
        and update.reroute_result.strategy != RerouteStrategy.SPEED_ONLY
        and update.reroute_result.route
        and update.reroute_result.route.segments
    ):
        reroute_route = update.reroute_result.route
        reroute_path = _build_route_path(reroute_route)
        if _route_path_matches_pending(agv_id, reroute_path):
            return update
        coords_lookup = {k: (v[0], v[1], 0.0) for k, v in map_manager.points.items()} if getattr(map_manager, "points", None) else {}
        order_info = agv_manager.get_order(agv_id)
        current_order_id = order_info["order_id"] or str(uuid.uuid4())
        next_update_id = order_info["order_update_id"] + 1
        path, _ = _send_route_order(
            agv_id=agv_id,
            route=reroute_route,
            coords_lookup=coords_lookup,
            reason=update.reroute_result.reason,
            order_id=current_order_id,
            order_update_id=next_update_id,
        )
        _remember_local_route_override(agv_id, path, update.reroute_result.reason)
        _remember_motion_hint(agv_id, reroute_route, path[0] if path else current_hint_node)
        _send_control_action_if_needed(agv_id, "RESUME")
        asyncio.create_task(
            broadcast_update(
                {
                    "type": "traffic_reroute",
                    "agv_id": agv_id,
                    "map_id": map_id,
                    "path": path,
                    "order_id": current_order_id,
                    "order_update_id": next_update_id,
                    "reason": update.reroute_result.reason,
                    "timestamp": datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).isoformat(),
                }
            )
        )

    return update


# ==========================
# OFFLINE MONITOR
# ==========================
OFFLINE_THRESHOLD_SEC = 6
OFFLINE_CHECK_INTERVAL_SEC = 2

async def monitor_offline(stop_event: asyncio.Event):
    alerted = set()
    while not stop_event.is_set():
        try:
            agvs = agv_manager.list_agvs()
            now = datetime.now(timezone.utc)
            for agv_id, info in agvs.items():
                last_update = info.get("last_update")
                offline = True
                if last_update:
                    try:
                        ts = datetime.fromisoformat(last_update.replace("Z", "+00:00"))
                        offline = (now - ts).total_seconds() > OFFLINE_THRESHOLD_SEC
                    except Exception:
                        offline = True
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
                if not offline and agv_id in alerted:
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
    print("[DB] Äang thá»­ káº¿t ná»‘i PostgreSQL...")
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
            print(f"[DB] Káº¾T Ná»I THÃ€NH CÃ”NG!")
            print(f"    â†’ Database: {result[0]}")
            print(f"    â†’ User: {result[1]}")
            print(f"    â†’ PostgreSQL: {result[2][:60]}...")
        return pool
    except Exception as e:
        print(f"[DB] Káº¾T Ná»I THáº¤T Báº I!")
        print(f"    â†’ Lá»—i: {e}")
        print(f"    â†’ URL: {DATABASE_URL}")
        print("    â†’ Gá»¢I Ã: docker-compose up -d db hoáº·c kiá»ƒm tra PostgreSQL Ä‘ang cháº¡y")
        return None

async def close_pool():
    global pool
    if pool:
        await pool.close()
        print("[DB] ÄÃ£ Ä‘Ã³ng káº¿t ná»‘i PostgreSQL")

# ==========================
# LIFESPAN â€“ KHá»žI Äá»˜NG & Táº®T á»¨NG Dá»¤NG
# ==========================
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[LIFESPAN] Khá»Ÿi Ä‘á»™ng á»©ng dá»¥ng...")

    # Káº¿t ná»‘i DB
    app.state.db_pool = await create_pool()
    app.state.loop = asyncio.get_running_loop()

    # Khá»Ÿi Ä‘á»™ng MQTT
    print("[MQTT] Äang khá»Ÿi Ä‘á»™ng vÃ  chá» AGV káº¿t ná»‘i thá»±c táº¿...")
    start_mqtt()
    app.state.offline_stop = asyncio.Event()
    app.state.offline_task = asyncio.create_task(monitor_offline(app.state.offline_stop))

    print("[SYSTEM] Há»‡ thá»‘ng Ä‘Ã£ sáºµn sÃ ng!")
    print("[INFO] AGV sáº½ xuáº¥t hiá»‡n khi gá»­i state tháº­t qua MQTT")
    print("[INFO] Real-time broadcast Ä‘Ã£ hoáº¡t Ä‘á»™ng â€“ Má»ŒI thay Ä‘á»•i Ä‘á»u thÃ´ng bÃ¡o Ä‘áº¿n táº¥t cáº£ client")

    if app.state.db_pool:
        print("[SUCCESS] TOÃ€N Bá»˜ Há»† THá»NG Sáº´N SÃ€NG! (MQTT + DB + Dashboard + Real-time)")
    else:
        print("[WARNING] DB CHÆ¯A Káº¾T Ná»I â€“ Chá»‰ cÃ³ MQTT + Dashboard")

    yield

    print("[LIFESPAN] Äang táº¯t á»©ng dá»¥ng...")
    if getattr(app.state, "offline_stop", None):
        app.state.offline_stop.set()
    if getattr(app.state, "offline_task", None):
        try:
            await app.state.offline_task
        except Exception as e:
            print(f"[OFFLINE] Task stop error: {e}")
    await close_pool()

# ==========================
# Táº O APP
# ==========================
app = FastAPI(
    title="TOT AGV Fleet Manager",
    version="2025.11",
    lifespan=lifespan,
    docs_url="/api-agv",
    redoc_url="/api-agv-redoc",
    openapi_url="/openapi.json"
)
app.state.traffic_engine = traffic_engine
app.state.handle_traffic_state_update = handle_traffic_state_update

# ==========================
# WEBSOCKET CONNECTION MANAGER + BROADCAST
# ==========================
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"[WS] Client má»›i káº¿t ná»‘i â€“ Tá»•ng: {len(self.active_connections)} client(s)")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            print(f"[WS] Client ngáº¯t â€“ CÃ²n láº¡i: {len(self.active_connections)} client(s)")

    async def broadcast(self, message: Dict):
        if not self.active_connections:
            return
        print(f"[WS] BROADCAST â†’ {len(self.active_connections)} client(s): {message.get('type', 'unknown')}")
        dead_connections = []
        for conn in self.active_connections:
            try:
                await conn.send_json(message)
            except Exception as e:
                print(f"[WS] Lá»—i gá»­i Ä‘áº¿n 1 client: {e}")
                dead_connections.append(conn)
        # XÃ³a cÃ¡c client cháº¿t
        for dead in dead_connections:
            self.active_connections.remove(dead)

manager = ConnectionManager()

# HÃ m tiá»‡n Ã­ch Ä‘á»ƒ gá»i tá»« báº¥t ká»³ Ä‘Ã¢u
async def broadcast_update(data: dict):
    """Gá»­i thÃ´ng bÃ¡o real-time Ä‘áº¿n táº¥t cáº£ dashboard Ä‘ang má»Ÿ"""
    await manager.broadcast(data)
async def broadcast_agv_pose(agv_id: str, x: float, y: float, theta: float, map_id: str):
    """Gá»­i vá»‹ trÃ­ AGV Ä‘áº¿n táº¥t cáº£ dashboard Ä‘ang má»Ÿ"""
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
    print(f"[WS] ÄÃ£ broadcast pose AGV {agv_id}: ({x:.2f}, {y:.2f}) Î¸={theta:.1f}Â° | Map: {map_id}")
# GÃ¡n vÃ o app.state Ä‘á»ƒ dÃ¹ng á»Ÿ nÆ¡i khÃ¡c náº¿u cáº§n
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
            # Giá»¯ káº¿t ná»‘i sá»‘ng â€“ cÃ³ thá»ƒ xá»­ lÃ½ lá»‡nh tá»« client sau nÃ y
            data = await websocket.receive_text()
            # Náº¿u cáº§n xá»­ lÃ½ lá»‡nh tá»« dashboard thÃ¬ thÃªm á»Ÿ Ä‘Ã¢y
    except Exception as e:
        print(f"[WS] Client ngáº¯t do lá»—i: {e}")
    finally:
        manager.disconnect(websocket)

# ==========================
# PHá»¤C Vá»¤ FILE TÄ¨NH + AGV MAP UI
# ==========================
STATIC_DIR = BASE_DIR / "static"
MAP_DIR = BASE_DIR / "maps"
app.mount("/static", StaticFiles(directory=STATIC_DIR, html=True), name="static")
app.mount("/maps", StaticFiles(directory=MAP_DIR), name="maps")

@app.get("/")
@app.get("/AgvMap")
@app.get("/AgvMap.html")
async def agv_map():
    return FileResponse(STATIC_DIR / "AgvMap.html")

@app.get("/home")
async def home_redirect():
    return RedirectResponse(url="http://192.168.88.253:8050/home")

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
# Gá»¬I Lá»†NH DI CHUYá»‚N AGV (vá»›i broadcast)
# ==========================
@app.post("/order")
async def move_agv(cmd: MoveCommand):
    try:
        print(f"[API] Nháº­n lá»‡nh move: {cmd.agv_id} â†’ {cmd.destination}")
        agv = agv_manager.get_agv(cmd.agv_id)
        if not agv:
            raise HTTPException(status_code=404, detail=f"AGV '{cmd.agv_id}' khÃ´ng tá»“n táº¡i")

        # Check connectivity (offline if no state > 1.5s)
        last_update_str = agv.get("last_update")
        is_offline = False
        if not last_update_str:
            is_offline = True
        else:
            try:
                ts = datetime.fromisoformat(last_update_str.replace("Z", "+00:00"))
                if datetime.now(timezone.utc) - ts > timedelta(seconds=1.5):
                    is_offline = True
            except Exception:
                is_offline = True
        if is_offline:
            raise HTTPException(status_code=503, detail="AGV mat ket noi, vui long ket noi lai de su dung")

        #default_map_id = "98"
        # Æ¯u tiÃªn map_id do client gá»­i; náº¿u khÃ´ng cÃ³ thÃ¬ dÃ¹ng mapCurrent hoáº·c default
        raw_map = cmd.map_id or agv.get("mapCurrent") or agv.get("map_id")
        # Cho phÃ©p raw_map lÃ  name (tang_4) hoáº·c id (98)
        if not raw_map:
            raise HTTPException(status_code=400, detail="Missing map_id/mapCurrent from AGV or request.")
        resolved_map = await map_manager.resolve_map_id(app.state.db_pool, str(raw_map))
        if not resolved_map:
            raise HTTPException(status_code=404, detail=f"Map not found in DB for '{raw_map}'.")
        map_id = resolved_map
        if not map_id:
            raise HTTPException(status_code=400, detail="KhÃ´ng xÃ¡c Ä‘á»‹nh Ä‘Æ°á»£c map_id/mapCurrent.")

        if app.state.db_pool is None:
            raise HTTPException(status_code=503, detail="Database pool not initialized")

        await map_manager.load_from_db(app.state.db_pool, str(map_id))
        await ensure_traffic_topology(str(map_id))
        if map_manager.graph.number_of_nodes() == 0:
            raise HTTPException(status_code=404, detail=f"Map '{raw_map}' resolve thÃ nh '{map_id}' nhÆ°ng graph trong DB Ä‘ang rá»—ng.")

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
            # fallback: láº¥y node Ä‘áº§u tiÃªn trong graph
            start_node = list(map_manager.graph.nodes)[0]
        if not start_node:
            start_node = "StartPoint"
        # Ã©p vá» string Ä‘á»ƒ khá»›p vá»›i graph
        start_node = _normalize_node_token(start_node)
        dest_node = _normalize_node_token(cmd.destination)

        requested_path = _dedupe_consecutive_nodes(cmd.path or [])
        dedupe_key = _order_dedupe_key(cmd.agv_id, str(map_id), dest_node, requested_path)
        cached_response = _get_recent_order_result(dedupe_key)
        if cached_response is not None:
            print(
                f"[ORDER DEDUPE] Ignored duplicate move for {cmd.agv_id} -> {dest_node} "
                f"| map={map_id} | path={requested_path or '-'}"
            )
            return cached_response
        planner_result = None
        route_to_activate = None
        path = []

        if len(requested_path) >= 2:
            if requested_path[0] != start_node:
                if start_node in requested_path:
                    requested_path = requested_path[requested_path.index(start_node) :]
                else:
                    requested_path.insert(0, start_node)
            requested_path = _dedupe_consecutive_nodes(requested_path)
            route_to_activate = traffic_engine.activate_route_from_node_path(
                agv_id=cmd.agv_id,
                map_id=str(map_id),
                node_path=requested_path,
                current_hint_node=str(start_node) if start_node else None,
                reason="API_MOVE_PATH",
            )
            if route_to_activate is None:
                raise HTTPException(
                    status_code=409,
                    detail=f"Requested path is invalid for current topology: {requested_path}",
                )
            path = requested_path
        else:
            planner_result = traffic_engine.plan_route(
                map_id=str(map_id),
                agv_id=cmd.agv_id,
                start_node=start_node,
                goal_node=dest_node,
                reason="API_MOVE",
            )
            if not planner_result.success or planner_result.route is None:
                raise HTTPException(status_code=409, detail=planner_result.message)
            route_to_activate = planner_result.route
            path = planner_result.node_path

        if not path or len(path) < 2:
            raise HTTPException(
                status_code=409,
                detail=f"Resolved path is too short for order: start={start_node}, destination={dest_node}, path={path}",
            )

        order_id = str(uuid.uuid4())
        # Build order theo full path (VDA5050)
        # chuáº©n bá»‹ coords cho nodePosition
        coords_lookup = {k: (v[0], v[1], 0.0) for k, v in map_manager.points.items()} if getattr(map_manager, "points", None) else {}
        vda_path = _to_vda_path(path)
        vda_coords_lookup = _to_vda_coords_lookup(coords_lookup)
        order = build_order(
            agv_id=cmd.agv_id,
            path=vda_path,
            coords=vda_coords_lookup,
            manufacture=agv.get("manufacturer", "TNG:TOT"),
            SerialNumber=agv.get("serialNumber", cmd.agv_id),
            version="2.0",
            order_id=order_id,
            order_update_id=0,
            horizon=None  # release toÃ n bá»™, cÃ³ thá»ƒ giáº£m náº¿u muá»‘n incremental
        )

        agv_manager.set_order(cmd.agv_id, order_id, 0)
        agv_manager.set_pending_path(cmd.agv_id, path)
        traffic_engine.activate_route(cmd.agv_id, str(map_id), route_to_activate)
        _remember_local_route_override(cmd.agv_id, path, "API_MOVE", hold_seconds=1.5)
        _remember_motion_hint(cmd.agv_id, route_to_activate, start_node)
        send_order(cmd.agv_id, order)
        _clear_control_action(cmd.agv_id)

        print(f"[ORDER] THÃ€NH CÃ”NG! Order: {order_id[:8]} â†’ {dest_node}")

        # BROADCAST: CÃ³ ngÆ°á»i vá»«a gá»­i lá»‡nh di chuyá»ƒn
        asyncio.create_task(broadcast_update({
            "type": "external_command",
            "action": "MOVE",
            "agv_id": cmd.agv_id,
            "destination": dest_node,
            "path": path,
            "order_id": order_id[:8],
            "timestamp": datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).isoformat()
        }))

        response_payload = {
            "status": "Order sent successfully",
            "orderId": order_id,
            "path": path,
            "agv": cmd.agv_id,
            "destination": dest_node
        }
        _remember_order_result(
            _order_dedupe_key(cmd.agv_id, str(map_id), dest_node, path),
            response_payload,
        )
        return response_payload

    except HTTPException:
        raise
    except Exception as e:
        print("[ERROR] Lá»—i khi xá»­ lÃ½ /order:")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

app.state.move_agv_func = move_agv

# ==========================
# Gá»¬I Lá»†NH Tá»¨C THÃŒ (PAUSE/RESUME) + BROADCAST
# ==========================
@app.post("/action")
def send_action(req: ActionRequest):
    try:
        print(f"[ACTION] Gá»­i lá»‡nh tá»©c thÃ¬: {req.action_type} â†’ AGV {req.agv_id}")
        send_instant_action(req.agv_id, req.action_type)

        # BROADCAST: CÃ³ ngÆ°á»i vá»«a PAUSE/RESUME
        asyncio.create_task(broadcast_update({
            "type": "external_command",
            "action": req.action_type,
            "agv_id": req.agv_id,
            "timestamp": datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).isoformat()
        }))

        return {"status": "OK", "message": f"{req.action_type} Ä‘Ã£ gá»­i tá»›i {req.agv_id}"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# ==========================
# GIáº¢I PHÃ“NG KHÃ“A ÄÆ¯á»œNG KHI AGV HOÃ€N THÃ€NH (MANUAL API)
# ==========================
@app.post("/order/release")
def release_order(req: ReleaseRequest):
    """
    Gá»i API nÃ y khi AGV hoÃ n thÃ nh order Ä‘á»ƒ giáº£i phÃ³ng edge-locks.
    CÃ³ thá»ƒ gá»i tá»« callback MQTT state/feedback náº¿u muá»‘n tá»± Ä‘á»™ng.
    """
    traffic_engine.release_agv(req.agv_id)
    agv_manager.clear_pending_path(req.agv_id)
    _clear_control_action(req.agv_id)
    return {"status": "OK", "message": f"ÄÃ£ giáº£i phÃ³ng khÃ³a Ä‘Æ°á»ng cho {req.agv_id}"}

# ==========================
# UPLOAD MAP HOÃ€N CHá»ˆNH + BROADCAST MAP Má»šI
# ==========================

# ==========================
# Láº¤Y Dá»® LIá»†U MAP (Ä‘Ã£ cÃ³)
# ==========================
@app.get("/api/map/full")
async def get_full_map(map_id: str):
    async with app.state.db_pool.acquire() as conn:
        # Map info
        map_row = await conn.fetchrow("SELECT * FROM maps WHERE map_id = $1", map_id)
        if not map_row:
            raise HTTPException(404, "Map khÃ´ng tá»“n táº¡i")

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
    Sá»¬A Lá»–I: Tráº£ vá» JSON list thay vÃ¬ HTML Response.
    Frontend mong Ä‘á»£i má»™t array JSON: [{"id": 1, "name": "Map A"}, ...]
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

        # CHUYá»‚N Äá»”I Káº¾T QUáº¢ DB SANG LIST/ARRAY JSON
        map_list = []
        for r in rows:
            # Äáº£m báº£o trÆ°á»ng name khÃ´ng null
            name = r["name"] if r["name"] is not None else f"Map ID {r['id']}" 
            map_list.append({
                "id": str(r["id"]),
                "name": name
            })
        
        # FastAPI sáº½ tá»± Ä‘á»™ng chuyá»ƒn list Python nÃ y thÃ nh JSON Response há»£p lá»‡
        return map_list
    
    except Exception as e:
        print(f"Lá»—i khi táº£i danh sÃ¡ch map tá»« DB: {e}")
        # Tráº£ vá» lá»—i 500 náº¿u DB gáº·p sá»± cá»‘
        raise HTTPException(status_code=500, detail="Lá»—i khi truy váº¥n database Ä‘á»ƒ láº¥y danh sÃ¡ch map")

    
@app.get("/api/maps/{map_id}")
async def get_map_detail(map_id: str):
    async with pool.acquire() as conn:
        # Láº¥y thÃ´ng tin map
        map_info = await conn.fetchrow("""
            SELECT id, name, origin_x, origin_y, origin_theta, image_path 
            FROM agv_maps 
            WHERE id = $1
        """, map_id)
        if not map_info:
            raise HTTPException(404, "Map khÃ´ng tá»“n táº¡i")

        # Láº¥y points
        points = await conn.fetch("""
            SELECT name_id, name, x, y 
            FROM agv_map_points 
            WHERE map_id = $1
        """, map_id)

        # Láº¥y roads
        roads = await conn.fetch("""
            SELECT id_source, id_dest, 
                   point_start_x, point_start_y, 
                   point_end_x, point_end_y,
                   move_direction, width
            FROM agv_map_roads 
            WHERE map_id = $1
        """, map_id)
        
        # =========================================================================
        # [Má»šI] Láº¤Y ÄÆ¯á»œNG CONG BEZIER
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
            "name": map_info["name"] or "KhÃ´ng tÃªn",
            "origin_x": map_info["origin_x"],
            "origin_y": map_info["origin_y"],
            "origin_theta": map_info["origin_theta"],
            "image_path": f"/maps/{map_info['id']}.png",  # phá»¥c vá»¥ qua static
            "points": [dict(p) for p in points],
            "roads": [dict(r) for r in roads],
            "benziers": [dict(b) for b in benziers] # THÃŠM TRÆ¯á»œNG BEZIERS VÃ€O PHáº¢N Há»’I
        }
    
@app.post("/api/agv/position")
async def update_position(request: Request):
    try:
        data = await request.json()
        agv_id = data.get("agv_id", "AGV_01")        # â† Láº¥y ID AGV (ráº¥t quan trá»ng!)
        map_id = str(data.get("map_id", ""))
        x = float(data.get("x", 0))
        y = float(data.get("y", 0))
        theta = float(data.get("theta", 0))

        # Gá»¬I Vá»Š TRÃ QUA WEBSOCKET Äáº¾N Táº¤T Cáº¢ DASHBOARD
        await broadcast_agv_pose(agv_id, x, y, theta, map_id)

        # (TÃ¹y chá»n) lÆ°u vÃ o biáº¿n global náº¿u cáº§n dÃ¹ng á»Ÿ nÆ¡i khÃ¡c
        # current_agv_pos = {"map_id": map_id, "x": x, "y": y, "theta": theta}

        return {"status": "ok", "agv_id": agv_id, "broadcasted": True}
    except Exception as e:
        print(f"[ERROR] Lá»—i parse pose: {e}")
        raise HTTPException(400, "Invalid position data")
    
@app.get("/api/agv/position")
async def get_position(map_id: str = None):
    global current_agv_pos
    if current_agv_pos["x"] is not None:
        if map_id is None or current_agv_pos["map_id"] == map_id:
            return current_agv_pos
    return {"x": None, "y": None, "theta": 0, "map_id": None}

# ==========================
# [Má»šI] UPLOAD MAP HOÃ€N CHá»ˆNH Báº°NG JSON THUáº¦N (2025 STANDARD)
# ==========================
@app.post("/api/agv/map/upload-full")
async def agv_upload_full_json(request: Request):
    global last_map_id

    try:
        payload = await request.json()
    except Exception as e:
        print("Lá»—i parse JSON:", e)
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # In JSON nháº­n Ä‘Æ°á»£c Ä‘á»ƒ debug
    print("\n" + "="*80)
    print("NHáº¬N ÄÆ¯á»¢C MAP Má»šI Tá»ª AGV")
    print("="*80)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print("="*80 + "\n")

    # ================== Láº¤Y THÃ”NG TIN Tá»ª robot_maps ==================
    robot_maps = payload.get("robot_maps") or payload.get("map_info") or payload
    map_name_from_root = str(payload.get("mapName", "")).strip()

    raw_map_id = robot_maps.get("id")
    map_name = str(robot_maps.get("name", map_name_from_root) or "").strip()
    if not map_name:
        map_name = "map_unknown"

    existing_map_id = None
    if not raw_map_id and map_name and pool is not None:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id
                FROM agv_maps
                WHERE name = $1
                LIMIT 1
                """,
                map_name,
            )
            if row:
                existing_map_id = str(row["id"])

    map_id = str(raw_map_id or existing_map_id or str(uuid.uuid4()))

    origin_x = float(robot_maps.get("x", 0))
    origin_y = float(robot_maps.get("y", 0))
    origin_theta = float(robot_maps.get("theta", 0))
    layer = int(robot_maps.get("layer", 0))

    # Thá»i gian sá»­a
    modify_time_str = robot_maps.get("modifytime")
    if modify_time_str and len(modify_time_str) >= 10:
        try:
            modify_time = datetime.strptime(modify_time_str, "%Y-%m-%d %H:%M:%S")
            modify_time = modify_time.replace(tzinfo=timezone(timedelta(hours=7)))
        except:
            modify_time = datetime.now(timezone(timedelta(hours=7)))
    else:
        modify_time = datetime.now(timezone(timedelta(hours=7)))

    # ================== LÆ¯U áº¢NH ==================
    image_b64 = robot_maps.get("image", "")
    if not image_b64:
        print("KhÃ´ng cÃ³ áº£nh base64!")

    image_path = None
    if image_b64:
        if image_b64.startswith("data:"):
            image_b64 = image_b64.split(",", 1)[1]

        try:
            image_data = base64.b64decode(image_b64)
            if len(image_data) < 1000:  # quÃ¡ nhá» â†’ lá»—i base64
                raise Exception("Base64 quÃ¡ ngáº¯n")
        except Exception as e:
            print("Lá»—i decode áº£nh:", e)
            raise HTTPException(status_code=400, detail=f"Invalid image base64: {e}")

        os.makedirs("maps", exist_ok=True)
        image_path = f"maps/{map_id}.png"
        with open(image_path, "wb") as f:
            f.write(image_data)

        print(f"ÄÃ£ lÆ°u áº£nh thÃ nh cÃ´ng: {image_path} ({len(image_data)} bytes)")

    # ================== LÆ¯U DB ==================
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

            # XÃ³a dá»¯ liá»‡u cÅ©
            # ÄÃƒ THÃŠM Báº¢NG agv_map_benziers VÃ€O ÄÃ‚Y
            for table in ["agv_map_points", "agv_map_roads", "agv_map_codes", "agv_map_benziers"]: 
                await conn.execute(f"DELETE FROM {table} WHERE map_id = $1", map_id)

            # LÆ°u points (cÃ³ thá»ƒ rá»—ng)
            points = payload.get("robot_points", [])
            for p in points:
                point_name = str(p.get("name", "") or map_name)
                await conn.execute("""
                    INSERT INTO agv_map_points
                    (map_id, name_id, name, x, y, theta, type, zone, action, carrier, available, accuracy)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
                """, map_id,
                    str(p.get("name_id", "")),
                    point_name,
                    p.get("x"), p.get("y"), p.get("theta"),
                    p.get("type", 0), p.get("zone", ""), p.get("action"),
                    p.get("carrier", 0), p.get("available", False), p.get("accuracy", 0))

            # LÆ°u roads (cÃ³ thá»ƒ rá»—ng)
            roads = payload.get("robot_roads", [])
            for r in roads:
                road_name = str(r.get("name", "") or map_name)
                point_start = r.get("point_start", [0, 0])
                point_end = r.get("point_end", [0, 0])
                await conn.execute("""
                    INSERT INTO agv_map_roads
                    (map_id, name, id_source, id_dest,
                     point_start_x, point_start_y, point_end_x, point_end_y,
                     width, speed, move_direction, distance)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
                """, map_id, road_name,
                    str(r["id_source"]), str(r["id_dest"]),
                    point_start[0], point_start[1],
                    point_end[0], point_end[1],
                    r.get("width", 0.95), r.get("speed", 0.3),
                    r.get("move_direction", 0), r.get("distance", 0))

            # LÆ°u codes (cÃ³ thá»ƒ rá»—ng)
            codes = payload.get("robot_code", [])
            for c in codes:
                await conn.execute("""
                    INSERT INTO agv_map_codes (map_id, code_id, code, x, y, theta)
                    VALUES ($1,$2,$3,$4,$5,$6)
                """, map_id, c.get("id"), c.get("code", ""), c.get("x"), c.get("y"), c.get("theta"))
                
            # =========================================================================
            # [Má»šI] LÆ¯U ÄÆ¯á»œNG CONG BEZIER
            # =========================================================================
            benziers = payload.get("robot_benziers", [])

            if benziers:
                print(f"  | Benziers: {len(benziers)}")
                for b in benziers:
                    bezier_name = str(b.get("name", "") or map_name)
                    point_start = b.get("point_start", [0, 0])
                    point_end = b.get("point_end", [0, 0])
                    curve_point_start = b.get("curve_point_start", [0, 0])
                    curve_point_end = b.get("curve_point_end", [0, 0])
                    
                    # ChÃ¨n dá»¯ liá»‡u Bezier vÃ o báº£ng agv_map_benziers
                    await conn.execute("""
                        INSERT INTO agv_map_benziers (
                            map_id, name, id_source, id_dest,
                            point_start_x, point_start_y, point_end_x, point_end_y,
                            curve_point_start_x, curve_point_start_y, curve_point_end_x, curve_point_end_y,
                            width, speed, move_direction
                        )
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
                    """, map_id, bezier_name,
                        str(b["id_source"]), str(b["id_dest"]),
                        point_start[0], point_start[1],
                        point_end[0], point_end[1],
                        curve_point_start[0], curve_point_start[1],
                        curve_point_end[0], curve_point_end[1],
                        b.get("width", 0.3), b.get("speed", 0.3),
                        b.get("move_direction", 0)
                    )
            # =========================================================================

    print(f"Upload map thÃ nh cÃ´ng! ID: {map_id} | TÃªn: {map_name} | Points: {len(points)} | Roads: {len(roads)} | Codes: {len(codes)} | Benziers: {len(benziers)}\n")

    return {
        "status": "success",
        "map_id": map_id,
        "map_name": map_name,
        "image_saved": image_path,
        "points": len(points),
        "roads": len(roads),
        "codes": len(codes),
        "benziers": len(benziers), # THÃŠM Sá» LÆ¯á»¢NG BEZIER VÃ€O PHáº¢N Há»’I
        "server_time": datetime.now(timezone(timedelta(hours=7))).isoformat()
    }

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
