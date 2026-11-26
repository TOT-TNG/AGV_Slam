# mqtt_client.py
import json
import datetime
import time
import uuid
import os
import math
import re
import asyncio
import concurrent.futures
import builtins
import threading
from typing import Optional
from urllib.parse import unquote
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor
import paho.mqtt.client as mqtt

from agv_manager import AGVManager
from fastapi import FastAPI
from map_manager import MapManager

# ==========================
# MQTT Configuration
# ==========================

# ── Cloud broker (iot.tot360.com.vn) ─────────────────────────────────────────
_CLOUD_BROKER = "iot.tot360.com.vn"
_CLOUD_PORT   = 8883
_CLOUD_USER   = os.getenv("MQTT_CLOUD_USER", "iot_user")
_CLOUD_PASS   = os.getenv("MQTT_CLOUD_PASS", "d7xvk5pKkqsKKMd")

# ── Local broker (Mosquitto của máy chạy server) — user/password mặc định ────
_LOCAL_USER = "tot_agv"
_LOCAL_PASS = "TNG12345"

# ── Mode config file (mqtt_mode.json cạnh mqtt_client.py) ────────────────────
_MQTT_MODE_FILE = Path(__file__).parent / "mqtt_mode.json"

def _load_mqtt_mode() -> str:
    # MQTT_MODE_OVERRIDE: dùng RIÊNG cho mô phỏng (simulation/) để đảm bảo
    # tiến trình main.py mô phỏng KHÔNG BAO GIỜ vô tình đọc mqtt_mode.json
    # thật (file CHUNG với server sản xuất, có thể đang ở "cloud") và kết nối
    # nhầm vào broker cloud thật. Production không set biến này → hành vi
    # giữ nguyên 100% (file vẫn thắng như trước).
    override = os.getenv("MQTT_MODE_OVERRIDE", "").strip().lower()
    if override:
        return override
    try:
        if _MQTT_MODE_FILE.exists():
            with open(_MQTT_MODE_FILE) as f:
                return json.load(f).get("mode", "local")
    except Exception:
        pass
    return os.getenv("MQTT_MODE", "local").lower()

def _read_mode_file() -> dict:
    try:
        if _MQTT_MODE_FILE.exists():
            with open(_MQTT_MODE_FILE) as f:
                d = json.load(f)
                return d if isinstance(d, dict) else {}
    except Exception:
        pass
    return {}

def _write_mode_file(data: dict) -> None:
    try:
        with open(_MQTT_MODE_FILE, "w") as f:
            json.dump(data, f)
    except Exception as e:
        print(f"[MQTT] Cannot save mode file: {e}")

def _save_mqtt_mode(mode: str) -> None:
    d = _read_mode_file()      # giữ nguyên các khoá khác (cấu hình broker local)
    d["mode"] = mode
    _write_mode_file(d)

def _local_broker_cfg() -> dict:
    """Địa chỉ + tài khoản broker LOCAL: cấu hình lưu từ giao diện (mqtt_mode.json → "local") > biến môi trường >
    mặc định (localhost:1883, tot_agv). Địa chỉ broker phụ thuộc mạng từng nhà máy (có thể là máy/IP khác) nên cho cấu
    hình trên giao diện. MQTT_MODE_OVERRIDE (mô phỏng) BỎ QUA file này — file dùng chung với server sản xuất, không
    được để mô phỏng nối nhầm vào broker thật."""
    saved = {} if os.getenv("MQTT_MODE_OVERRIDE", "").strip() else (_read_mode_file().get("local") or {})
    host = str(saved.get("host") or os.getenv("MQTT_BROKER", "localhost")).strip() or "localhost"
    try:
        port = int(saved.get("port") or os.getenv("MQTT_PORT", "1883"))
    except (TypeError, ValueError):
        port = 1883
    # user/password đã lưu (kể cả chuỗi rỗng = nối ẩn danh) thắng env/mặc định
    user = str(saved["user"]).strip() if "user" in saved else os.getenv("MQTT_USER", _LOCAL_USER).strip()
    password = str(saved["password"]) if "password" in saved else os.getenv("MQTT_PASS", _LOCAL_PASS)
    return {"host": host, "port": port, "user": user, "password": password}

def _resolve_broker_port(mode: str) -> tuple[str, int]:
    if mode == "cloud":
        return _CLOUD_BROKER, _CLOUD_PORT
    cfg = _local_broker_cfg()
    return cfg["host"], cfg["port"]

def _configure_client_for_mode(c, mode: str) -> None:
    """Cài TLS + auth cho client theo mode trước khi connect."""
    import ssl as _ssl
    if mode == "cloud":
        c.username_pw_set(_CLOUD_USER, _CLOUD_PASS)
        c.tls_set(cert_reqs=_ssl.CERT_NONE)
        c.tls_insecure_set(True)
        print(f"[MQTT] Mode=cloud → TLS+auth configured for {_CLOUD_BROKER}:{_CLOUD_PORT}")
    else:
        # Mosquitto local bật user/password (cùng tài khoản cho server/xe/thang) → mặc định sẵn trong code như cloud,
        # chuyển sang chế độ local là chạy, không phải đặt biến môi trường. Đặt MQTT_USER rỗng để nối ẩn danh
        # (vd broker mô phỏng cổng 1884 không có mật khẩu — gửi kèm user/pass vẫn được chấp nhận).
        cfg = _local_broker_cfg()
        if cfg["user"]:
            c.username_pw_set(cfg["user"], cfg["password"])
        print(f"[MQTT] Mode=local → {cfg['host']}:{cfg['port']} ({'user ' + cfg['user'] if cfg['user'] else 'ẩn danh'})")

# ── Khởi tạo mode + broker/port ──────────────────────────────────────────────
MQTT_MODE = _load_mqtt_mode()
BROKER, PORT = _resolve_broker_port(MQTT_MODE)

QOS = int(os.getenv("MQTT_QOS", "0"))
UAGV_INTERFACE_NAME = os.getenv("UAGV_INTERFACE_NAME", "uagv").strip() or "uagv"
UAGV_MAJOR_VERSION = os.getenv("UAGV_MAJOR_VERSION", "v3").strip() or "v3"
UAGV_MANUFACTURER = os.getenv("UAGV_MANUFACTURER", "tot").strip() or "tot"

# Cửa tự động (gate) — xem PROTOCOL_GUIDE.md mục "Cửa tự động (Gate Controller)"
GATE_INTERFACE_NAME = os.getenv("GATE_MQTT_INTERFACE", "gate").strip() or "gate"
GATE_MQTT_VERSION   = os.getenv("GATE_MQTT_VERSION", "v1").strip() or "v1"
# Thang máy — cùng kiểu cửa tự động (xem elevator_coordinator.py / PROTOCOL_GUIDE.md mục 17)
ELEVATOR_INTERFACE_NAME = os.getenv("ELEVATOR_MQTT_INTERFACE", "elevator").strip() or "elevator"
ELEVATOR_MQTT_VERSION   = os.getenv("ELEVATOR_MQTT_VERSION", "v1").strip() or "v1"

agv_manager = AGVManager()
map_manager = MapManager()
_map_id_cache: dict[str, str] = {}
_mqtt_stopping = False
MQTT_VERBOSE_LOG = os.getenv("MQTT_VERBOSE_LOG", "0").strip().lower() in {"1", "true", "yes", "on"}
_last_state_log_ts: dict[str, float] = {}
_last_filtered_log_ts: dict[str, float] = {}
_recent_published_action_ids: dict[str, float] = {}
_last_instant_action_sent: dict[tuple[str, str], float] = {}
_last_traffic_control_action: dict[str, str] = {}
_pending_reroute_apply: dict[str, dict[str, object]] = {}
_pending_head_on_assignments: dict[str, dict[str, object]] = {}
_peer_stop_states: dict[str, dict] = {}         # agv_id -> {"peer_id": str, "since": float}
_peer_stop_resolved_pairs: set = set()          # frozenset({agv_a, agv_b}) pairs already resolved this cycle
_last_state_print: dict[str, tuple] = {}        # agv_id -> (node, order, battery%, paused) đã log lần trước
# Yield-on-edge: AGV dừng giữa edge chờ node tranh chấp được clear bởi winner
# {agv_id: {"contested_node": str, "winner_agv_id": str, "since": float}}
_yield_states: dict[str, dict] = {}
YIELD_TIMEOUT_SEC = 30.0  # Sau timeout này, yield hết hiệu lực và trả về normal flow
# Proactive node blocking: track which node each AGV is currently heading to
# {agv_id: to_node_str}  — updated every time AGV's current_edge changes
_agv_incoming_node: dict[str, str] = {}
# Pairs already proactively rerouted this reservation cycle: frozenset({incoming_agv_id, affected_agv_id})
_proactive_rerouted_pairs: set = set()
# Idle-block proactive reroute dedup: frozenset({"agv@vN", "idle_other_node"}) — keyed by route version
_idle_block_proactive_done: set = set()
INSTANT_ACTION_COOLDOWN_SEC = float(os.getenv("INSTANT_ACTION_COOLDOWN_SEC", "10.0"))
PEER_STOP_REROUTE_TIMEOUT_SEC = float(os.getenv("PEER_STOP_REROUTE_TIMEOUT_SEC", "3.0"))
REROUTE_APPLY_HOLD_SEC = float(os.getenv("REROUTE_APPLY_HOLD_SEC", "3.0"))
# PHÁT HIỆN THỰC TẾ (2026-10-08): AGV01 hạ móc nhả hàng tại 98 rồi Về trạm được
# dispatch NGAY sau đó — bước "deba" (xem _start_locate_then_charge) chạy tiến
# ngay lúc xe hàng vừa nhả RA có thể còn chắn ngay trước đầu AGV (chưa kịp kéo
# ra khỏi đường), mà "deba" không được traffic/obstacle engine bảo vệ → xe
# đứng im hẳn không nhúc nhích, phải người vận hành bấm Stop rồi gọi lại tay
# mới chạy được. Chờ 1 nhịp ngắn sau hook_lowered trước khi chạy "deba" cho xe
# hàng kịp được kéo ra, KHÔNG áp dụng khi Về trạm được gọi vì lý do khác (vd
# người dùng bấm tay giữa đường, không liên quan tới vừa nhả hàng).
LOCATE_AFTER_DROPOFF_GRACE_SEC = float(os.getenv("LOCATE_AFTER_DROPOFF_GRACE_SEC", "3.0"))
# Chờ tối đa bao lâu cho thẻ kế trống trước khi "deba" dò vị trí (xem _start_locate_then_charge).
PLAN_PATH_TIMEOUT_SEC = float(os.getenv("PLAN_PATH_TIMEOUT_SEC", "30.0"))
LOCATE_DEPARTURE_CLEAR_MAX_SEC = float(os.getenv("LOCATE_DEPARTURE_CLEAR_MAX_SEC", "30.0"))
# Số lần tối đa _locate_then_charge_loop_coro TỰ huỷ+gọi lại "Về trạm" khi "deba"
# đứng im hẳn (driving chưa từng =True) — chặn lặp vô hạn nếu xe thật sự kẹt vật
# lý/mất kết nối; hết số lần này thì rơi về mốc ~120s báo cần kiểm tra tay như cũ.
LOCATE_STUCK_MAX_AUTO_RETRIES = int(os.getenv("LOCATE_STUCK_MAX_AUTO_RETRIES", "3"))

# ════════════════════════════════════════════════════════════════════════════
# ConflictWaitManager
# ════════════════════════════════════════════════════════════════════════════
# Lịch trình backoff giữa các lần retry reroute (giây)
_WAIT_RETRY_BACKOFF = [2.0, 4.0, 8.0, 15.0, 30.0]
_WAIT_PRIORITY_BOOST_AFTER_S = float(os.getenv("WAIT_PRIORITY_BOOST_S", "20.0"))
_WAIT_FORCE_RESUME_AFTER_S   = float(os.getenv("WAIT_FORCE_RESUME_S",   "90.0"))
_WAIT_MAX_RETRIES            = int(os.getenv("WAIT_MAX_RETRIES", "8"))


class _WaitEntry:
    __slots__ = (
        "agv_id", "winner_agv_id", "contested_resource",
        "reroute_reason", "since", "last_retry",
        "retry_count", "priority_boosted",
    )
    def __init__(self, agv_id, winner_agv_id, contested_resource, reason):
        self.agv_id             = agv_id
        self.winner_agv_id      = winner_agv_id
        self.contested_resource = contested_resource   # node_id hoặc physical_edge_id
        self.reroute_reason     = reason
        self.since              = time.time()
        self.last_retry         = 0.0
        self.retry_count        = 0
        self.priority_boosted   = False


class ConflictWaitManager:
    """
    Quản lý thông minh các AGV bị WAIT do không còn đường reroute.

    Flow:
      1. register(agv_id, winner, resource, reason)  ← gọi khi reroute fail + WAIT gán
      2. tick(...)  ← gọi mỗi lần nhận state update (trước vòng lặp per-AGV)
         - Kiểm tra winner đã clear resource chưa
         - Nếu cleared → retry plan_route với backoff
         - Thành công → gửi order mới + RESUME + release
         - Vẫn fail → tăng backoff, thử lại sau
         - Sau N retry → bỏ qua blocked edges (bare route)
         - Sau hard timeout → force RESUME
      3. release(agv_id)  ← gọi khi reroute thành công ở nơi khác
    """

    def __init__(self):
        self._waiting: dict[str, _WaitEntry] = {}
        self._lock = threading.Lock()

    # ── Public API ─────────────────────────────────────────────────────────
    def register(
        self,
        agv_id: str,
        winner_agv_id: Optional[str],
        contested_resource: str,
        reason: str,
    ) -> None:
        with self._lock:
            existing = self._waiting.get(agv_id)
            # Không ghi đè nếu cùng winner (tránh reset retry counter)
            if existing and existing.winner_agv_id == winner_agv_id:
                return
            self._waiting[agv_id] = _WaitEntry(agv_id, winner_agv_id, contested_resource, reason)
        print(f"[WAIT_MGR] ↳ {agv_id} WAIT | winner={winner_agv_id} | resource={contested_resource}")

    def release(self, agv_id: str, reason: str = "") -> bool:
        with self._lock:
            entry = self._waiting.pop(agv_id, None)
        if entry:
            elapsed = time.time() - entry.since
            print(f"[WAIT_MGR] ✓ {agv_id} released | waited={elapsed:.1f}s "
                  f"retries={entry.retry_count} | {reason}")
            return True
        return False

    def is_waiting(self, agv_id: str) -> bool:
        return agv_id in self._waiting

    def all_waiting(self) -> list:
        return list(self._waiting.keys())

    # ── tick — gọi sau evaluate_map_controls, trước vòng per-AGV ──────────
    def tick(
        self,
        map_control_results: dict,
        traffic_map_id: str,
        traffic_engine_ref,
        agv_manager_ref,
    ) -> None:
        """Kiểm tra & retry reroute cho tất cả AGV đang chờ."""
        if not self._waiting:
            return

        now = time.time()
        with self._lock:
            to_process = list(self._waiting.items())

        for agv_id, entry in to_process:
            agv_state = agv_manager_ref.get_agv(agv_id) or {}
            winner_id = entry.winner_agv_id

            # ── 1. Hard timeout → force resume ──────────────────────────────
            elapsed = now - entry.since
            if elapsed >= _WAIT_FORCE_RESUME_AFTER_S:
                print(f"[WAIT_MGR] ⚠ {agv_id} FORCE RESUME (hard timeout {elapsed:.0f}s)")
                _send_traffic_control_action(agv_id, "RESUME")
                self.release(agv_id, "force_resume_hard_timeout")
                continue

            # ── 2. Priority boost sau ngưỡng ────────────────────────────────
            if not entry.priority_boosted and elapsed >= _WAIT_PRIORITY_BOOST_AFTER_S:
                self._boost_priority(agv_id, entry, traffic_engine_ref)

            # ── 3. Kiểm tra winner đã clear resource chưa ──────────────────
            winner_cleared = self._check_winner_cleared(
                winner_id, entry.contested_resource, map_control_results, agv_manager_ref
            )
            if not winner_cleared:
                continue

            # ── 4. Backoff: đủ thời gian retry chưa? ───────────────────────
            idx = min(entry.retry_count, len(_WAIT_RETRY_BACKOFF) - 1)
            if now - entry.last_retry < _WAIT_RETRY_BACKOFF[idx]:
                continue

            entry.last_retry = now
            entry.retry_count += 1

            # ── 5. Thử reroute ──────────────────────────────────────────────
            self._attempt_reroute(
                entry, agv_state, traffic_map_id, traffic_engine_ref, agv_manager_ref
            )

    # ── Internal helpers ───────────────────────────────────────────────────
    def _check_winner_cleared(
        self,
        winner_id: Optional[str],
        contested: str,
        map_control_results: dict,
        agv_manager_ref,
    ) -> bool:
        """
        True nếu winner đã rời khỏi vùng tranh chấp.
        Kiểm tra cả từ traffic engine state lẫn agv_manager state.
        """
        if not winner_id:
            return True

        # Ưu tiên dùng traffic engine state (chính xác nhất)
        winner_result = map_control_results.get(winner_id)
        if winner_result is not None:
            ws = winner_result.state
            cn = str(contested).strip()
            if ws.current_node and str(ws.current_node).strip() == cn:
                return False
            if ws.current_edge:
                to_n = _to_node_of_edge(ws.current_edge)
                if to_n and str(to_n).strip() == cn:
                    return False
            return True

        # Fallback: agv_manager raw state
        winner_raw = agv_manager_ref.get_agv(winner_id)
        if not winner_raw:
            return True   # winner offline → cleared
        last_node = str(winner_raw.get("lastNodeId") or "").strip()
        cur_edge  = str(winner_raw.get("currentEdge") or "").strip()
        if last_node == str(contested).strip():
            return False
        if contested in cur_edge:
            return False
        return True

    def _boost_priority(self, agv_id: str, entry: _WaitEntry, traffic_engine_ref) -> None:
        """Tăng priority tạm thời cho AGV đã chờ quá lâu."""
        try:
            from traffic_core import PriorityContext
            # Score = thời gian chờ (giây) / 10 → tăng dần theo thời gian
            boost = int((time.time() - entry.since) / 10) + 5
            ctx = PriorityContext(priority_score=boost)
            traffic_engine_ref._priority_contexts[agv_id] = ctx
            entry.priority_boosted = True
            print(f"[WAIT_MGR] ↑ {agv_id} priority boosted (+{boost}) after "
                  f"{time.time()-entry.since:.0f}s waiting")
        except Exception as e:
            print(f"[WAIT_MGR] priority boost failed: {e}")

    def _attempt_reroute(
        self,
        entry: _WaitEntry,
        agv_state: dict,
        traffic_map_id: str,
        traffic_engine_ref,
        agv_manager_ref,
    ) -> None:
        agv_id = entry.agv_id
        try:
            from main import (
                build_order_for_traffic_route,
                _remember_pending_reroute_apply,
                traffic_engine as _te,
            )

            start_node = str(
                agv_state.get("lastNodeId") or agv_state.get("currentNode") or ""
            ).strip()
            if not start_node:
                return

            route = traffic_engine_ref._routes.get(agv_id)
            if not route or not route.segments:
                # Không có route → không biết đích → force resume
                print(f"[WAIT_MGR] {agv_id} no active route → force resume")
                _send_traffic_control_action(agv_id, "RESUME")
                self.release(agv_id, "no_active_route_force_resume")
                return

            goal_node = str(route.segments[-1].to_node)
            if start_node == goal_node:
                # Đã đến đích → release
                self.release(agv_id, "already_at_goal")
                return

            # Blocked edges: retry < 4 → chỉ tránh resource conflict
            #                retry ≥ 4 → thêm toàn bộ winner's route
            #                retry ≥ max → bare (không blocked)
            blocked: list[str] = []
            if entry.retry_count < _WAIT_MAX_RETRIES:
                blocked = traffic_engine_ref.get_reserved_edges(
                    traffic_map_id, exclude_agv=agv_id
                )
                if entry.retry_count >= 4 and entry.winner_agv_id:
                    winner_route = traffic_engine_ref._routes.get(entry.winner_agv_id)
                    if winner_route:
                        blocked += [s.edge_id for s in winner_route.segments]

            plan = traffic_engine_ref.plan_route(
                map_id=traffic_map_id,
                agv_id=agv_id,
                start_node=start_node,
                goal_node=goal_node,
                blocked_edges=blocked,
                reason=f"WAIT_MGR_RETRY_{entry.retry_count}",
            )

            if not plan.success or not plan.route:
                # Lần thử cuối: bare route (không blocked edges nào)
                if entry.retry_count >= _WAIT_MAX_RETRIES:
                    plan = traffic_engine_ref.plan_route(
                        map_id=traffic_map_id,
                        agv_id=agv_id,
                        start_node=start_node,
                        goal_node=goal_node,
                        blocked_edges=[],
                        reason="WAIT_MGR_BARE",
                    )
                if not plan.success or not plan.route:
                    # Vẫn không có đường → nếu đã retry quá nhiều → force resume
                    if entry.retry_count >= _WAIT_MAX_RETRIES:
                        print(f"[WAIT_MGR] ⚠ {agv_id} max retries → force RESUME")
                        _send_traffic_control_action(agv_id, "RESUME")
                        self.release(agv_id, "max_retries_force_resume")
                    else:
                        print(f"[WAIT_MGR] {agv_id} retry #{entry.retry_count} still no route "
                              f"| msg={getattr(plan, 'message', '?')}")
                    return

            # ── Reroute thành công ─────────────────────────────────────────
            next_oid = str(agv_state.get("orderId") or uuid.uuid4())
            next_uid = int(agv_state.get("orderUpdateId") or 0) + 1
            reroute_order, reroute_path = build_order_for_traffic_route(
                agv_id, plan.route, agv_state,
                order_id=next_oid, order_update_id=next_uid,
            )
            _remember_pending_reroute_apply(
                agv_id, next_oid, next_uid,
                [s.edge_id for s in plan.route.segments],
            )
            send_order(agv_id, reroute_order)
            traffic_engine_ref.activate_route(agv_id, traffic_map_id, plan.route)

            # RESUME sau khi gửi order
            action_state = agv_state.get("actionState") or {}
            if agv_state.get("paused") and not action_state.get("simPauseHold"):
                _send_traffic_control_action(agv_id, "RESUME")

            self.release(agv_id, f"rerouted_ok_retry_{entry.retry_count} → {reroute_path}")
            print(f"[WAIT_MGR] ✓ {agv_id} rerouted retry #{entry.retry_count} → {reroute_path}")

        except Exception as e:
            print(f"[WAIT_MGR] {agv_id} attempt_reroute error: {e}")


_conflict_wait_mgr = ConflictWaitManager()


# ==========================
# YIELD-ON-EDGE HELPERS
# ==========================

def _extract_contested_node_from_reason(reason: str) -> Optional[str]:
    """Trích contested node từ reason string, ví dụ 'NODE_AHEAD_17' → '17'."""
    if not reason:
        return None
    if "NODE_AHEAD_" in reason:
        after = reason.split("NODE_AHEAD_")[-1]
        node = after.split("_")[0].split(" ")[0].strip()
        return node if node else None
    return None


def _to_node_of_edge(edge_id: str) -> Optional[str]:
    """Trả về to_node của edge dựa trên naming convention 'A_to_B' và 'A_to_B__rev'."""
    if not edge_id:
        return None
    is_rev = edge_id.endswith("__rev")
    base = edge_id[:-5] if is_rev else edge_id  # strip "__rev" (5 chars)
    parts = base.split("_to_")
    if len(parts) != 2:
        return None
    from_node, to_node = parts[0].strip(), parts[1].strip()
    # Reversed edge đi ngược chiều: from_node của base trở thành to_node
    return from_node if is_rev else to_node


def _winner_cleared_contested_node(
    contested_node: str,
    winner_agv_id: Optional[str],
    map_control_results: dict,
) -> bool:
    """True nếu winner đã qua khỏi contested_node (không còn ở đó hoặc đang tiến đến đó).

    Loser chỉ nên resume khi winner:
    1. current_node != contested_node (không đứng tại node đó)
    2. current_edge không dẫn ĐẾN contested_node (không đang tiến vào node đó)
    """
    if not winner_agv_id:
        return True  # Không biết winner → giả định đã clear
    winner_result = map_control_results.get(str(winner_agv_id))
    if winner_result is None:
        return True  # Winner không trong map → giả định đã clear
    ws = winner_result.state
    cn = str(contested_node).strip()
    # Winner đang đứng tại contested_node?
    if ws.current_node and str(ws.current_node).strip() == cn:
        return False
    # Winner đang tiến VÀO contested_node (mid-edge, to_node == cn)?
    if ws.current_edge:
        to_n = _to_node_of_edge(ws.current_edge)
        if to_n and str(to_n).strip() == cn:
            return False
    return True  # Winner đã qua hoặc không liên quan


def print(*args, **kwargs):
    text = " ".join(str(arg) for arg in args)
    now = time.time()

    if "[MQTT] Raw payload:" in text and not MQTT_VERBOSE_LOG:
        return

    if "[MQTT]" in text and "topic:" in text and not MQTT_VERBOSE_LOG:
        return

    if "[STATE] AGV " in text and "MQTT THẬT" in text:
        key = "state_banner"
        if now - _last_filtered_log_ts.get(key, 0.0) < 2.0:
            return
        _last_filtered_log_ts[key] = now

    if text.startswith("   ") and not MQTT_VERBOSE_LOG:
        return

    if "[DB] resolve_map_id_sync" in text or "[DB] ensure_map_loaded_sync" in text:
        if now - _last_filtered_log_ts.get(text, 0.0) < 5.0:
            return
        _last_filtered_log_ts[text] = now

    builtins.print(*args, **kwargs)


def _remember_pending_reroute_apply(
    agv_id: str,
    order_id: str,
    order_update_id: int,
    route_edges: list[str],
) -> None:
    _pending_reroute_apply[str(agv_id)] = {
        "order_id": str(order_id or "").strip(),
        "order_update_id": int(order_update_id or 0),
        "route_edges": [str(edge_id).strip() for edge_id in route_edges if str(edge_id or "").strip()],
        "since": time.time(),
    }


def _remember_head_on_assignment(winner: str, loser: str, resource_node: str | None = None) -> None:
    _pending_head_on_assignments[str(winner)] = {
        "winner": str(winner),
        "loser": str(loser),
        "resource_node": str(resource_node) if resource_node else None,
        "since": time.time(),
    }


def _get_head_on_assignment(winner: str) -> dict | None:
    return _pending_head_on_assignments.get(str(winner))


def _clear_head_on_assignment(winner: str) -> None:
    _pending_head_on_assignments.pop(str(winner), None)


def _send_peer_stop_reroute(agv_id: str, reroute_result, engine, map_id: str) -> bool:
    """Send reroute order for an AGV from a peer-stop reroute result. Returns True on success."""
    try:
        from traffic_core import RerouteStrategy
        from main import build_order_for_traffic_route
        if not (reroute_result and reroute_result.success and reroute_result.route
                and reroute_result.strategy != RerouteStrategy.SPEED_ONLY):
            return False
        state_data = agv_manager.get_agv(agv_id) or {}
        next_order_id = str(state_data.get("orderId") or uuid.uuid4())
        next_update_id = int(state_data.get("orderUpdateId") or 0) + 1
        reroute_order, reroute_path = build_order_for_traffic_route(
            agv_id, reroute_result.route, state_data,
            order_id=next_order_id, order_update_id=next_update_id,
        )
        print(f"[PEER_STOP] Rerouting agv={agv_id} path={reroute_path}")
        _remember_pending_reroute_apply(agv_id, next_order_id, next_update_id,
                                        [seg.edge_id for seg in reroute_result.route.segments])
        send_order(agv_id, reroute_order)
        engine.activate_route(agv_id, map_id, reroute_result.route)
        return True
    except Exception as exc:
        print(f"[PEER_STOP] _send_peer_stop_reroute failed for {agv_id}: {exc}")
        return False


def _handle_mutual_peer_stop(agv_a: str, agv_b: str, engine, map_id: str) -> None:
    """
    Resolve LIDAR peer-stop conflict.
    winner_override=agv_a means agv_a is the stopped one and agv_b is the detected peer (one-sided).
    Idle AGVs always win; the moving AGV must reroute around them.
    When no alternate path exists, do nothing — LIDAR already holds the AGV; no PAUSE needed.
    """
    try:
        winner, loser = engine.determine_peer_collision_winner(map_id, agv_a, agv_b)
        peer_is_idle = engine._routes.get(winner) is None  # winner has no active route

        print(f"[PEER_STOP] Resolving: winner={winner} (idle={peer_is_idle}) loser={loser}")

        if peer_is_idle:
            # Idle winner stays put → reroute the loser (moving AGV) around the idle winner's node.
            # Pass idle_agv_id=winner so force_reroute uses the engine's internal node format
            # (avoids MQTT "N21" vs topology "21" prefix mismatch in blocked_node comparison).
            idle_node = str((agv_manager.get_agv(winner) or {}).get("lastNodeId") or "").strip()
            print(f"[PEER_STOP] Idle winner={winner} at node={idle_node}, rerouting loser={loser} around it")
            reroute_result = engine.force_reroute_around_idle_peer(
                map_id, loser, idle_node, idle_agv_id=winner
            )
            if _send_peer_stop_reroute(loser, reroute_result, engine, map_id):
                return
            # No alternate path exists in the topology → LIDAR holds loser naturally
            print(f"[PEER_STOP] No alternate path for {loser} around idle {winner} at {idle_node}; LIDAR holds it")
            return

        # Both AGVs moving → reroute the loser via standard head-on mechanism
        deferred = engine._deferred_head_on.get(loser) or {}
        avoid_edges = list(deferred.get("avoid_edges") or [])
        reroute_result = engine.force_reroute_for_peer_collision(map_id, loser, avoid_edges, winner)
        if _send_peer_stop_reroute(loser, reroute_result, engine, map_id):
            _remember_head_on_assignment(winner, loser)
            return

        # Loser couldn't reroute → try treating loser as idle-blocked (reroute around loser's node)
        loser_node = str((agv_manager.get_agv(loser) or {}).get("lastNodeId") or "").strip()
        print(f"[PEER_STOP] Standard reroute failed for loser={loser}, trying around node={loser_node}")
        fallback = engine.force_reroute_around_idle_peer(map_id, winner, loser_node)
        if _send_peer_stop_reroute(winner, fallback, engine, map_id):
            return

        # No reroute possible for either side → LIDAR already handles the stop, no server PAUSE needed
        print(f"[PEER_STOP] No reroute found for {agv_a} vs {agv_b}; leaving LIDAR to control")
    except Exception as exc:
        print(f"[PEER_STOP] Error resolving peer stop ({agv_a} vs {agv_b}): {exc}")


def _clear_pending_reroute_apply(agv_id: str) -> None:
    _pending_reroute_apply.pop(str(agv_id), None)


def _is_pending_reroute_applied(agv_id: str, state_data: dict) -> bool:
    guard = _pending_reroute_apply.get(str(agv_id))
    if not guard:
        return True

    current_order_id = str(state_data.get("orderId") or "").strip()
    try:
        current_update_id = int(state_data.get("orderUpdateId") or 0)
    except Exception:
        current_update_id = 0

    expected_order_id = str(guard.get("order_id") or "").strip()
    expected_update_id = int(guard.get("order_update_id") or 0)
    if current_order_id == expected_order_id and current_update_id >= expected_update_id:
        _clear_pending_reroute_apply(agv_id)
        return True

    if time.time() - float(guard.get("since") or 0.0) >= REROUTE_APPLY_HOLD_SEC:
        print(
            f"[REROUTE] Hold timeout waiting order ack from {agv_id} "
            f"| expected={expected_order_id}/{expected_update_id} "
            f"| current={current_order_id}/{current_update_id} → clearing guard"
        )
        _clear_pending_reroute_apply(agv_id)
        return True
    return False

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


def _is_app_shutting_down() -> bool:
    try:
        app = get_app()
        return bool(getattr(app.state, "shutting_down", False))
    except Exception:
        return False


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
        return True
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

def _legacy_resolve_map_id_sync_unused(raw_map: str) -> str | None:
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


def _legacy_ensure_map_loaded_sync_unused(raw_map: str) -> str | None:
    """
    Resolve raw_map từ MQTT sang map_id thật và đảm bảo graph đã được load
    vào shared MapManager trước khi traffic xử lý telemetry.
    """
    raw_map = str(raw_map or "").strip()
    if not raw_map:
        return None

    try:
        app = get_app()
        loop = getattr(app.state, "loop", None)
        pool = getattr(app.state, "db_pool", None)

        if not loop or not loop.is_running() or pool is None:
            return resolve_map_id_sync(raw_map) or raw_map

        resolved_map_id = resolve_map_id_sync(raw_map) or raw_map

        if (
            str(map_manager.current_map_id) != str(resolved_map_id)
            or map_manager.graph.number_of_nodes() == 0
        ):
            fut = asyncio.run_coroutine_threadsafe(
                map_manager.load_from_db(pool, str(resolved_map_id)),
                loop,
            )
            fut.result(timeout=5)

        return str(resolved_map_id)
    except Exception as e:
        print(f"[DB] ensure_map_loaded_sync thất bại cho raw_map={raw_map}: {e}")
        return resolve_map_id_sync(raw_map) or raw_map

def resolve_map_id_sync(raw_map: str) -> str | None:
    """
    Chuyen doi raw_map tu MQTT thanh map_id that trong database.
    Co cache va bo qua DB khi app dang shutdown.
    """
    raw_map = str(raw_map or "").strip()
    if not raw_map:
        return None

    cached = _map_id_cache.get(raw_map)
    if cached:
        return cached

    try:
        if _mqtt_stopping or _is_app_shutting_down():
            return raw_map

        app = get_app()
        loop = getattr(app.state, "loop", None)
        pool = getattr(app.state, "db_pool", None)

        if not loop or not loop.is_running() or pool is None:
            return raw_map

        fut = asyncio.run_coroutine_threadsafe(
            map_manager.resolve_map_id(pool, raw_map),
            loop,
        )
        resolved = fut.result(timeout=5)
        resolved_value = str(resolved).strip() if resolved else raw_map
        if resolved_value:
            _map_id_cache[raw_map] = resolved_value
        return resolved_value
    except Exception as e:
        if not (_mqtt_stopping or _is_app_shutting_down()):
            detail = str(e) or e.__class__.__name__
            print(f"[DB] resolve_map_id_sync that bai cho raw_map={raw_map}: {detail}")
        return raw_map


def ensure_map_loaded_sync(raw_map: str) -> str | None:
    """
    Resolve raw_map va dam bao shared MapManager da load xong graph.
    """
    raw_map = str(raw_map or "").strip()
    if not raw_map:
        return None

    try:
        if _mqtt_stopping or _is_app_shutting_down():
            return _map_id_cache.get(raw_map) or raw_map

        app = get_app()
        loop = getattr(app.state, "loop", None)
        pool = getattr(app.state, "db_pool", None)

        if not loop or not loop.is_running() or pool is None:
            return _map_id_cache.get(raw_map) or resolve_map_id_sync(raw_map) or raw_map

        resolved_map_id = _map_id_cache.get(raw_map) or resolve_map_id_sync(raw_map) or raw_map
        _map_id_cache[raw_map] = str(resolved_map_id)

        if str(map_manager.current_map_id) == str(resolved_map_id) and map_manager.graph.number_of_nodes() > 0:
            return str(resolved_map_id)

        fut = asyncio.run_coroutine_threadsafe(
            map_manager.load_from_db(pool, str(resolved_map_id)),
            loop,
        )
        fut.result(timeout=5)
        return str(resolved_map_id)
    except Exception as e:
        if not (_mqtt_stopping or _is_app_shutting_down()):
            detail = str(e) or e.__class__.__name__
            print(f"[DB] ensure_map_loaded_sync that bai cho raw_map={raw_map}: {detail}")
        return _map_id_cache.get(raw_map) or resolve_map_id_sync(raw_map) or raw_map


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
    Lấy thông tin runtime cần thiết để điều hướng AGV.
    Hỗ trợ cả Line AGV (đọc từ line_agv_handler) và VDA5050 (đọc từ agv_manager).
    """
    from agv_registry import agv_registry

    if agv_registry.is_line(agv_id):
        # Line AGV: đọc từ line_agv_handler.state_store
        from line_agv_handler import line_agv_handler
        line_state = line_agv_handler.state_store.get(agv_id)
        current_node = (str(line_state.current_tag)
                        if (line_state is not None
                            and line_state.current_tag is not None
                            and line_state.current_tag != 0)
                        else None)
        # Ưu tiên map_id từ DB (agv_devices.map_id), fallback map_manager.current_map_id
        raw_map = (
            agv_registry.get_map_id(agv_id)
            or str(getattr(map_manager, "current_map_id", "") or "").strip()
        )
        resolved_map_id = raw_map or None
        agv_state = {
            "lastNodeId":       current_node,
            "map_id":           raw_map,
            "battery_low":      line_state.battery_low if line_state else False,
            "battery_blocking": line_state.battery_blocking if line_state else False,
        }
        return {
            "agv_state":       agv_state,
            "current_node":    current_node,
            "raw_map":         raw_map,
            "resolved_map_id": resolved_map_id,
        }

    # VDA5050: giữ nguyên logic cũ
    agv_state    = agv_manager.get_agv(agv_id) or {}
    current_node = str(agv_state.get("lastNodeId") or "").strip() or None
    raw_map      = (
        agv_state.get("map_id")
        or agv_state.get("mapCurrent")
        or ""
    )
    raw_map         = str(raw_map).strip()
    resolved_map_id = resolve_map_id_sync(raw_map) if raw_map else None

    return {
        "agv_state":       agv_state,
        "current_node":    current_node,
        "raw_map":         raw_map,
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

    from agv_registry import agv_registry as _reg
    _is_line = _reg.is_line(agv_id)

    # type integer trong DB: 2=charger, 5=buffer(wait zone), 7=wait
    _TYPE_INT = {"charge": 2, "wait": 5}
    type_int = _TYPE_INT.get(target_type)

    # ── Bước 1: tìm TẤT CẢ trạm phù hợp ──────────────────────────────────────
    all_stations: list[dict] = []
    if type_int is not None:
        all_stations = find_all_nodes_by_type_via_pool(resolved_map_id, type_int, line_agv=_is_line)

    # Fallback tên nếu không có node theo type
    if not all_stations:
        single = find_named_node_with_action_via_pool(resolved_map_id, candidates, line_agv=_is_line)
        if single and single.get("node_id"):
            all_stations = [single]

    # Fallback arrival_action JSONB
    if not all_stations:
        fallback_action = {"charge": "wait_charge", "wait": "wait_sys"}.get(target_type)
        if fallback_action:
            single = find_node_by_arrival_action_via_pool(
                resolved_map_id, fallback_action, line_agv=_is_line
            )
            if single and single.get("node_id"):
                all_stations = [single]

    if not all_stations:
        raise ValueError(
            f"Không tìm thấy node {target_type} trong map {resolved_map_id} | candidates={candidates}"
        )

    # ── MỚI: lọc trạm theo agv_type nếu trạm được đánh dấu dành riêng (station_agv_type)
    # — trạm KHÔNG đánh dấu (trống) coi như dùng chung, không đụng map cũ chưa cấu hình.
    # action trả về từ DB có thể là str (JSON thô, chưa parse) — luôn parse an toàn trước khi .get().
    def _station_action_dict(s):
        _a = s.get("action")
        if isinstance(_a, str):
            try:
                import json as _json_sa
                return _json_sa.loads(_a) if _a else {}
            except Exception:
                return {}
        return _a or {}

    if target_type == "charge" and len(all_stations) > 1:
        _req_agv_type = str(_reg.get_config(agv_id).get("agv_type") or "").strip().lower()
        _typed_stations = [
            s for s in all_stations
            if not str(_station_action_dict(s).get("station_agv_type") or "").strip()
            or str(_station_action_dict(s).get("station_agv_type") or "").strip().lower() == _req_agv_type
        ]
        if _typed_stations:
            if len(_typed_stations) != len(all_stations):
                print(f"[STATION] {agv_id}: lọc theo agv_type='{_req_agv_type}' — "
                      f"{len(_typed_stations)}/{len(all_stations)} trạm phù hợp")
            all_stations = _typed_stations
        else:
            print(f"[STATION] {agv_id}: KHÔNG có trạm nào khớp agv_type='{_req_agv_type}' "
                  f"trong {len(all_stations)} trạm — dùng tạm tất cả (kiểm tra lại cấu hình map)")

    # ── VÙNG CẤM: bỏ trạm sạc/chờ nằm trong vùng loại xe này không được vào ──
    _forb_st = map_manager.forbidden_nodes(agv_id)
    if _forb_st:
        _allowed_st = [x for x in all_stations if str(x.get("node_id")).strip() not in _forb_st]
        if not _allowed_st:
            raise ValueError(
                f"Mọi node {target_type} của map đều nằm trong vùng cấm của xe {agv_id} "
                f"(loại '{_reg.get_config(agv_id).get('agv_type')}') — kiểm tra lại cấu hình vùng hoạt động")
        if len(_allowed_st) != len(all_stations):
            print(f"[STATION] {agv_id}: vùng cấm loại {len(all_stations) - len(_allowed_st)}/"
                  f"{len(all_stations)} trạm {target_type}")
        all_stations = _allowed_st

    # ── NHIỀU TẦNG: ưu tiên trạm CÙNG TẦNG với xe (đỡ phải đi thang). Tầng của xe không có trạm nào →
    # giữ nguyên danh sách (xe sẽ đi thang sang tầng có trạm — xem send_agv_to_special_target).
    try:
        import floor_nav as _fn_st
        if _fn_st.multi_floor(map_manager):
            _cur_st = info.get("current_node")
            if _cur_st:
                _fl_cur = _fn_st.floor_of(_cur_st, map_manager)
                _same_fl = [x for x in all_stations
                            if _fn_st.floor_of(x.get("node_id"), map_manager) == _fl_cur]
                if _same_fl and len(_same_fl) != len(all_stations):
                    print(f"[STATION] {agv_id}: ưu tiên trạm cùng tầng ({len(_same_fl)}/{len(all_stations)})")
                    all_stations = _same_fl
    except Exception as _e_stf:
        print(f"[STATION] lọc trạm theo tầng lỗi (bỏ qua): {_e_stf}")

    # ── Bước 2: chọn trạm ít bị "claim" nhất ─────────────────────────────────
    node_info, all_occupied = _pick_least_claimed_station(all_stations, agv_id, resolved_map_id)
    if not node_info:
        node_info = all_stations[0]

    # ── Đặt chỗ ngay — trước khi route được set (tránh race condition) ────────
    # CHỈ đặt chỗ khi CÒN trạm trống thật (all_occupied=False) — nếu TẤT CẢ đã
    # có xe/đã giữ chỗ, send_agv_to_special_target() sẽ chuyển xe này sang
    # "wait" thay vì chiếm thêm 1 "chỗ" ảo lên trạm đang đầy.
    if len(all_stations) > 1 and not all_occupied:
        reserve_station(node_info["node_id"], agv_id)

    print(f"[SPECIAL] {agv_id}: '{target_type}' → node={node_info['node_id']} "
          f"name={node_info.get('name')} (từ {len(all_stations)} trạm)")

    return {
        "node_id": str(node_info["node_id"]).strip(),
        "name": node_info.get("name"),
        "action": node_info.get("action"),
        "resolved_map_id": resolved_map_id,
        "all_occupied": all_occupied,
    }

def _locate_then_charge_loop_coro(agv_id: str, seq: int, spd: int, baseline_tag, jog_dir: str = 'fwd'):
    """
    CHỈ CHỜ, KHÔNG gửi lại "deba" — đúng 1 lần gửi duy nhất (trong
    _start_locate_then_charge) y hệt 1 lần bấm nút chạy thủ công, xe tự chạy hết quãng
    tới thẻ kế tiếp rồi tự dừng. Gửi lặp lại mỗi lần đã gây giật cục (đè lên hành trình
    xe đang tự chạy dở) — bỏ hẳn, chỉ còn vòng lặp này để: (1) phát hiện khi nào tag đổi
    → nối tiếp lệnh Về trạm thật, (2) phát hiện khi bị huỷ (seq đổi) → dừng theo dõi.

    jog_dir: hướng ('fwd'/'bwd') mà lệnh "deba" đã chạy — lệnh "deba" là lệnh THỦ
    CÔNG, đi TẮT qua toàn bộ hệ thống route/plan nên KHÔNG tự cập nhật
    last_transit_direction như 1 route bình thường. Thiếu bước gán lại này, lệnh
    "Về trạm" THẬT tiếp theo (send_agv_to_special_target) sẽ đọc last_transit_direction
    CŨ (từ TRƯỚC lúc dò vị trí) → tính sai hướng chặng kế → xe lại phải lùi/sửa
    hướng thêm 1 lần nữa (đúng lỗi thực tế: "lùi tận 2 lần xong mới quay đúng").
    """
    async def _run():
        from line_agv_handler import line_agv_handler
        _ticks = 0
        _retried = False
        _warned = False
        _ever_driving = False
        _jog_cmd = "lui" if jog_dir == "bwd" else "toi"
        while True:
            await asyncio.sleep(0.4)
            _ticks += 1
            state = line_agv_handler.state_store.get(agv_id)
            if not state or state.locate_then_charge_seq != seq:
                return   # bị huỷ (người dùng hủy lệnh) / thay thế bởi lượt dò vị trí khác
            if state.driving:
                # Xe THẬT SỰ đang chạy (dù chưa quẹt được thẻ mới) → đây là ca dò
                # vị trí HỢP LỆ đang chậm (có thể >20s, xem comment mốc ~20s dưới),
                # KHÔNG phải ca "deba" bị nuốt/bị cản đứng im hẳn → không tự huỷ.
                _ever_driving = True
            # QUAN TRỌNG: "deba" là lệnh THỦ CÔNG duy nhất, không có sự kiện xác
            # nhận nào khác ngoài đổi tag — nếu lệnh bị "nuốt" (vd xe còn MANUAL,
            # dù đã tự phục hồi ở _start_locate_then_charge vẫn có thể trượt do
            # race khác) thì tag KHÔNG BAO GIỜ đổi → vòng lặp này chờ MÃI MÃI,
            # xe "đứng im không về sạc" mà không có bất kỳ cảnh báo nào. Phát hiện
            # thực tế 2026-09-17. Chỉ retry ĐÚNG 1 LẦN và CHỈ KHI xác nhận xe chưa
            # hề nhúc nhích (driving=False suốt) — không đụng vào xe đang chạy dở
            # dang (đã bỏ resend-định-kỳ trước đây vì gây giật cục).
            if not _retried and _ticks == 15 and not state.driving:   # ~6s chưa nhúc nhích
                print(f"[LOCATE_THEN_CHARGE] {agv_id}: sau ~6s vẫn chưa thấy xe di "
                      f"chuyển (tag vẫn ={baseline_tag}) — gửi lại 'deba' 1 lần "
                      f"(nghi lệnh trước bị bỏ qua)")
                send_line_command(agv_id, "deba", spd=spd, dir=_jog_cmd)
                _retried = True
            elif not _warned and _ticks == 50:   # ~20s tổng vẫn không đổi tag → CẢNH BÁO
                # QUAN TRỌNG (phát hiện thực tế 2026-09-18): trước đây `return` ở đây
                # DỪNG HẲN việc theo dõi — nhưng "deba" là lệnh mù, không được traffic
                # engine bảo vệ (có thể bị AGV khác cản đường vật lý làm chậm hẳn), nên
                # 1 lượt dò vị trí HOÀN TOÀN HỢP LỆ vẫn có thể mất >20s (đã thấy tới
                # ~34s khi có AGV khác hoạt động gần đó). Dừng theo dõi ngay tại mốc 20s
                # khiến xe SAU ĐÓ vẫn tự đi tới thẻ mới (vật lý đã xong) nhưng không còn
                # ai lắng nghe để tiếp tục lệnh "Về trạm" → xe đứng im tại vị trí dò
                # được, không phải trạm sạc, đúng lỗi thực tế "tiến về node 13 rồi đứng
                # im". Chỉ CẢNH BÁO (không dừng loop) — vẫn tiếp tục chờ tới mốc hẳn
                # thật sự bên dưới.
                print(f"[LOCATE_THEN_CHARGE] {agv_id}: CẢNH BÁO — sau ~20s vẫn KHÔNG "
                      f"xác nhận được vị trí mới (tag vẫn ={baseline_tag}) — có thể đang "
                      f"bị cản đường vật lý (lệnh dò-vị-trí không được traffic engine bảo "
                      f"vệ). Vẫn tiếp tục theo dõi thêm, sẽ tự nối tiếp 'Về trạm' ngay khi "
                      f"quẹt được thẻ mới.")
                _warned = True
            elif _ticks == 88 and not _ever_driving:   # ~35s, driving CHƯA từng = True
                # PHÁT HIỆN THỰC TẾ (2026-10-08): AGV01 "deba" bị nuốt/cản hẳn sau khi
                # vừa hạ móc tại 98 — driving luôn =False suốt từ lúc gửi "deba" tới
                # lúc người vận hành bấm Stop rồi gọi lại tay ~65s sau (lúc đó tag đổi
                # thành công NGAY). Khác hẳn ca "đang chạy chậm" ở mốc ~20s trên (đó có
                # driving=True thật, chỉ là CHƯA quẹt được thẻ mới) — ca NÀY xe chưa hề
                # nhúc nhích 1 chút nào, KHÔNG cần chờ tới 120s mới báo rồi bắt người
                # vận hành tự làm lại — tự làm ĐÚNG việc người vận hành đã làm (huỷ lệnh
                # Về trạm đang kẹt rồi gọi lại), tối đa vài lần, để không lặp vô hạn nếu
                # xe thật sự kẹt/mất kết nối.
                try:
                    from task_queue import agv_task_queue as _atq_lc, CMD_GO_CHARGE as _CGC_LC
                    _retries = state.locate_then_charge_auto_retries
                    if _retries < LOCATE_STUCK_MAX_AUTO_RETRIES:
                        state.locate_then_charge_auto_retries = _retries + 1
                        print(f"[LOCATE_THEN_CHARGE] {agv_id}: sau ~35s vẫn KHÔNG hề nhúc "
                              f"nhích (driving luôn False, khác ca đang chạy chậm) — TỰ huỷ "
                              f"lệnh 'Về trạm' đang kẹt và gọi lại (lần {_retries + 1}/"
                              f"{LOCATE_STUCK_MAX_AUTO_RETRIES}), y hệt hành động người vận "
                              f"hành bấm Stop rồi gọi lại tay")
                        _atq_lc.insert_next(agv_id, _CGC_LC, dest_node=None)
                        _atq_lc.on_agv_completed(agv_id, notes='locate_then_charge_stuck_auto_retry')
                        return
                except Exception as _e_lc:
                    print(f"[LOCATE_THEN_CHARGE] {agv_id}: tự huỷ+gọi lại lỗi: {_e_lc}")
            elif _ticks >= 300:   # ~120s tổng vẫn không đổi tag → THẬT SỰ kẹt/mất kết nối
                print(f"[LOCATE_THEN_CHARGE] {agv_id}: sau ~120s vẫn KHÔNG xác nhận được "
                      f"vị trí mới (tag vẫn ={baseline_tag}) — xe có thể đang kẹt vật "
                      f"lý/mất kết nối thật sự. Dừng theo dõi tự động — cần kiểm tra xe "
                      f"{agv_id} và gọi lại 'Về trạm' thủ công nếu cần.")
                return
            if state.current_tag is not None and state.current_tag != baseline_tag:
                state.locate_then_charge_auto_retries = 0   # lượt dò vị trí này đã thành công
                # Tag THẬT SỰ mới (khác baseline lúc bắt đầu) — xác nhận vị trí đáng tin,
                # không chỉ dựa vào current_tag "not None" (giá trị cũ có thể vẫn còn từ
                # trước, không phản ánh vị trí vật lý hiện tại nếu xe bị đẩy tay).
                print(f"[LOCATE_THEN_CHARGE] {agv_id}: đã xác nhận vị trí thật tag={state.current_tag} "
                      f"(vị trí cũ trong hệ thống trước đó: {baseline_tag}) — tiếp tục lệnh Về trạm")
                # QUAN TRỌNG: lệnh "deba" KHÔNG có sự kiện xác nhận "đã dừng hẳn" (khác
                # arrived_wait_sys của plan thường) — server chỉ biết tag đã đổi, xe CÓ
                # THỂ còn đang trớn/chưa dừng hẳn dù đã quẹt được thẻ mới. Nếu gửi NGAY
                # lệnh rẽ thật (DIR_BWD+TURN) lúc xe còn trớn, xe trôi thêm 1 đoạn rồi
                # mới rẽ được — đúng lỗi thực tế "lùi thẳng tiếp nửa đường mới quay".
                # Chờ thêm tới khi state.driving=False (firmware tự báo dừng qua state
                # message bình thường) trước khi gửi tiếp, tối đa ~1.6s phòng hờ.
                for _ in range(8):
                    if not state.driving:
                        break
                    await asyncio.sleep(0.2)
                # Đồng bộ last_transit_direction theo ĐÚNG chiều vừa "deba" (xem
                # docstring) trước khi tính chặng thật tiếp theo.
                state.last_transit_direction = jog_dir
                try:
                    from main import _sync_manual_lidar as _sml_locate
                    _sml_locate(agv_id, force_on=True)
                except Exception:
                    pass
                try:
                    # QUAN TRỌNG: phải chạy qua asyncio.to_thread — _run() này đang thực thi
                    # NGAY TRÊN event loop chính (được lịch bằng run_coroutine_threadsafe nhắm
                    # thẳng vào loop đó). Nếu gọi send_agv_to_special_target() trực tiếp ở đây,
                    # các hàm tra cứu DB bên trong nó (find_all_nodes_by_type_via_pool...) lại
                    # tự bridge ngược về CHÍNH loop đang bị chặn để chờ nó — tự deadlock, luôn
                    # timeout sau 5s. Mọi nơi khác gọi send_agv_to_special_target() đều đi qua
                    # asyncio.to_thread (main.py) đúng vì lý do này.
                    await asyncio.to_thread(
                        send_agv_to_special_target, agv_id, "charge", False
                    )
                except Exception as e:
                    print(f"[LOCATE_THEN_CHARGE] {agv_id}: lỗi khi tiếp tục Về trạm sau khi dò vị trí: {e}")
                return
    return _run()


def _start_locate_then_charge(agv_id: str, spd: int = 70) -> None:
    """
    Trước khi Về trạm, LUÔN chạy 1 đoạn ngắn (lệnh "deba", bỏ qua hoàn toàn
    pathfinding/traffic engine) tới khi quẹt được 1 thẻ RFID MỚI (khác vị trí đang
    lưu trong hệ thống) — dùng cho MỌI lần gọi Về trạm của Line AGV, kể cả khi hệ
    thống đang "biết" 1 vị trí, vì vị trí đó có thể đã LỖI THỜI (xe bị đẩy tay sang
    chỗ khác mà chưa đi qua thẻ nào để cập nhật lại — current_tag vẫn giữ giá trị
    cũ, không tự về None).

    Hướng chạy KHÔNG còn hard-code "tiến" nữa — tính theo layout thật qua
    `resolve_departure_direction()`: nếu xe vừa TIẾN vào node hiện tại (vd điểm
    cấp hàng của xe carry là 1 điểm cụt) thì đoạn dò-vị-trí này phải LÙI ra
    trước, ngược lại (vd vừa lùi vào trạm sạc) thì vẫn tiến ra như cũ.

    Đánh đổi đã xác nhận với người vận hành: tốn thêm vài giây di chuyển mỗi lần gọi
    Về trạm (kể cả các lần hệ thống tự gọi lại nội bộ sau khi né xe khác), và trong
    lúc chạy "deba" xe KHÔNG được traffic engine bảo vệ (không giữ chỗ node/cạnh,
    không né xe khác) — chấp nhận đổi lấy việc luôn xác nhận đúng vị trí thật.
    """
    from line_agv_handler import line_agv_handler
    state = line_agv_handler.state_store.get_or_create(agv_id)
    state.locate_then_charge_seq += 1
    my_seq = state.locate_then_charge_seq
    baseline_tag = state.current_tag
    # Hàm này có thể được gọi NGAY TRÊN event loop (vd lifecycle_ack → hàng đợi → auto-dispatch 'go_charge'). Phần dưới
    # có time.sleep (chờ thẻ kế trống tới 30s, chờ nhả hàng) và, khi bỏ deba, tra DB qua cầu nối về CHÍNH loop đó →
    # chặn cả loop (mọi xe đứng, plan_path_for_order TimeoutError) + tự deadlock (mô phỏng 2026-11-05: SIM03 không về
    # được trạm sạc, kẹt 30+ phút). → luôn chạy phần chờ/gửi trong luồng riêng, trả về ngay.
    import threading as _th
    _th.Thread(target=_locate_then_charge_worker, args=(agv_id, spd, my_seq, baseline_tag),
               name=f"locate-charge-{agv_id}", daemon=True).start()


def _locate_then_charge_worker(agv_id: str, spd: int, my_seq: int, baseline_tag) -> None:
    from line_agv_handler import line_agv_handler, resolve_departure_direction
    state = line_agv_handler.state_store.get_or_create(agv_id)
    if state.locate_then_charge_seq != my_seq:
        return   # đã có lần gọi Về trạm mới hơn

    # Vừa nhả hàng (hook_lowered) gần đây → chờ hết nhịp còn thiếu cho xe hàng
    # kịp được kéo ra khỏi đường trước khi "deba" chạy tiến (xem comment hằng
    # số LOCATE_AFTER_DROPOFF_GRACE_SEC ở trên).
    if state.hook_lowered_at > 0:
        _since_dropoff = time.monotonic() - state.hook_lowered_at
        if _since_dropoff < LOCATE_AFTER_DROPOFF_GRACE_SEC:
            _wait_s = LOCATE_AFTER_DROPOFF_GRACE_SEC - _since_dropoff
            print(f"[LOCATE_THEN_CHARGE] {agv_id}: vừa nhả hàng {_since_dropoff:.1f}s trước "
                  f"→ chờ thêm {_wait_s:.1f}s cho xe hàng kịp kéo ra khỏi đường trước khi deba")
            time.sleep(_wait_s)

    _jog_dir = resolve_departure_direction(agv_id, baseline_tag)
    _jog_dir_cmd = "lui" if _jog_dir == "bwd" else "toi"
    # "deba" chạy MÙ tới thẻ kế (không giữ chỗ, không né) → nếu thẻ kế đang có xe khác đứng thì xe đè lên
    # nhau (mô phỏng 2026-11-03: SIM06 deba 71→54 khi SIM05 đứng ở 54, SIM04→58 khi SIM02 đứng ở 58 —
    # va chạm kéo dài ~1 phút). Chờ tối đa LOCATE_DEPARTURE_CLEAR_MAX_SEC cho thẻ kế trống rồi mới chạy.
    try:
        _g_dep = map_manager.line_graph if map_manager.line_graph else map_manager.graph
        _bt = str(baseline_tag) if baseline_tag is not None else None
        if _bt is not None and _g_dep is not None and _bt in _g_dep:
            # Không biết chắc firmware sẽ "deba" tới thẻ nào (tiến/lùi theo hướng mũi xe, không nhất thiết là prev_tag:
            # mô phỏng 2026-11-04 SIM05 bật/lùi 71→70→71 rồi deba lui về 54 — không phải 70) → coi MỌI hàng xóm là
            # đích có thể. Báo động giả chỉ khiến xe đi đường thường thay vì dò vị trí — vẫn đúng và an toàn.
            _cands = [str(x) for x in _g_dep.neighbors(_bt)]
            # baseline_tag có thể LỖI THỜI (xe vừa bị STOP giữa 2 thẻ rồi "đồng bộ" tag về cũ) → xe thật có thể đã ở
            # thẻ kề baseline, deba sẽ chạy tiếp qua thẻ kề kế đó (mô phỏng 2026-11-06: SIM02 baseline 50, thật ở 48,
            # deba lùi 48→46 đè SIM05 đang đứng ở 46). Xét cả hàng xóm bậc 2.
            for _n1 in list(_cands):
                for _n2 in _g_dep.neighbors(_n1):
                    if str(_n2) != _bt and str(_n2) not in _cands:
                        _cands.append(str(_n2))
            from line_agv_handler import traffic_coordinator as _tc_dep
            _t_dep = time.monotonic()
            _warned = False
            _occ = []
            while True:
                _occ = [o for o, st in line_agv_handler.state_store._states.items()
                        if o != agv_id and st is not None and st.current_tag is not None
                        and str(st.current_tag) in _cands]
                # xe khác SẮP tới một trong các thẻ đó (còn trong 3 node kế của route đã đăng ký) cũng tính là chiếm.
                # Không đòi `driving`: xe chạy theo cửa sổ nên giữa 2 cửa sổ nó đứng 1-2s (mô phỏng 2026-11-04:
                # SIM05 dừng ở 57 giữa 2 cửa sổ, SIM02 deba 55→56 đúng lúc SIM05 vào 56 → va chạm)
                for _o2, _r2 in list(_tc_dep._registered.items()):
                    _p2 = [str(n) for n in _r2.get('path', [])]
                    _i2 = _r2.get('current_idx', 0)
                    if (_o2 != agv_id and _o2 not in _occ
                            and any(n in _cands or n == _bt for n in _p2[_i2 + 1:_i2 + 4])):
                        _occ.append(_o2)
                if not _occ or time.monotonic() - _t_dep >= LOCATE_DEPARTURE_CLEAR_MAX_SEC:
                    break
                if not _warned:
                    print(f"[LOCATE_THEN_CHARGE] {agv_id}: thẻ kế {_cands} đang có {_occ} đứng → "
                          f"chờ (tối đa {LOCATE_DEPARTURE_CLEAR_MAX_SEC:.0f}s) rồi mới deba, tránh đè lên xe kia")
                    _warned = True
                time.sleep(1.0)
            if _occ:
                # Hết hạn chờ mà thẻ kế VẪN có xe → KHÔNG chạy mù đè lên xe đó (mô phỏng 2026-11-04: SIM05 deba
                # 63→64 khi SIM01 còn đứng ở 64, va chạm >1 phút). Bỏ bước dò vị trí, đi thẳng "Về trạm" bằng
                # đường đi thường (có engine giao thông giữ chỗ / né xe) — vị trí hiện tại đã được hệ thống biết.
                print(f"[LOCATE_THEN_CHARGE] {agv_id}: sau {LOCATE_DEPARTURE_CLEAR_MAX_SEC:.0f}s thẻ kế {_cands} "
                      f"vẫn có {_occ} → BỎ deba mù, đi thẳng Về trạm bằng đường thường")
                for _try in range(12):   # lỗi tạm (DB bận...) không được bỏ rơi xe: thử lại, nếu không xe đứng mãi tại chỗ
                    try:
                        send_agv_to_special_target(agv_id, "charge", False)
                        break
                    except Exception as _e_dep2:
                        print(f"[LOCATE_THEN_CHARGE] {agv_id}: Về trạm (không dò vị trí) lỗi (lần {_try + 1}/12): {_e_dep2}")
                        if state.locate_then_charge_seq != my_seq:
                            break
                        time.sleep(5.0)
                return
    except Exception as _e_dep:
        print(f"[LOCATE_THEN_CHARGE] {agv_id}: kiểm tra thẻ kế lỗi: {_e_dep}")
    print(f"[LOCATE_THEN_CHARGE] {agv_id}: chạy {'lùi' if _jog_dir == 'bwd' else 'tiến'} "
          f"(deba) xác nhận vị trí thật trước khi Về trạm "
          f"(vị trí cũ trong hệ thống: {baseline_tag})")
    try:
        from main import _sync_manual_lidar as _sml_locate0
        _sml_locate0(agv_id)
    except Exception:
        pass
    # QUAN TRỌNG: cùng lỗi đã gặp với lệnh "plan" (_send_line_order) — nếu xe còn
    # đang ở MANUAL (sót từ 1 lần stop/obstacle trước), gửi "deba" lúc này vẫn
    # được ACK (rc=0) nhưng KHÔNG được thực thi (xe không nhúc nhích) → tag không
    # bao giờ đổi → _locate_then_charge_loop_coro chờ vô thời hạn, xe "đứng im
    # không về sạc". Tự phục hồi AUTOMATIC trước, giống hệt _send_line_order.
    if state.operating_mode == "MANUAL":
        print(f"[LOCATE_THEN_CHARGE] {agv_id}: đang ở MANUAL (còn sót từ lần stop "
              f"trước) → gửi 'run' khôi phục AUTOMATIC trước khi gửi 'deba'")
        send_line_command(agv_id, "run")
        time.sleep(0.3)
    send_line_command(agv_id, "deba", spd=spd, dir=_jog_dir_cmd)

    app = get_app()
    loop = getattr(app.state, "loop", None)
    if loop and loop.is_running():
        asyncio.run_coroutine_threadsafe(
            _locate_then_charge_loop_coro(agv_id, my_seq, spd, baseline_tag, jog_dir=_jog_dir), loop
        )
    else:
        print(f"[LOCATE_THEN_CHARGE] {agv_id}: không lấy được event loop đang chạy — "
              f"chỉ gửi được 1 lần deba, có thể không đủ để tới thẻ RFID kế tiếp")


def _in_agv_scope(fn):
    """Chạy hàm (agv_id, ...) trong VÙNG HOẠT ĐỘNG của xe: vùng cấm + hướng riêng theo loại xe
    (type_directions) + trạm sạc là điểm cuối áp cho mọi đường tính trong hàm (vd side node, đường thay thế)."""
    import functools as _ft

    @_ft.wraps(fn)
    def _w(agv_id, *a, **k):
        with map_manager.agv_scope(agv_id):
            return fn(agv_id, *a, **k)
    return _w


@_in_agv_scope
def send_agv_to_special_target(agv_id: str, target_type: str, _require_locate: bool = True) -> dict:
    """
    Gửi AGV tới node đặc biệt:
    - charge: đi tới trạm sạc
    - wait: đi tới khu chờ

    _require_locate: chỉ dùng nội bộ — False khi hàm này được gọi lại từ
    _locate_then_charge_loop_coro (đã xác nhận vị trí thật xong), để tránh
    vòng lặp gọi lại chính nó vô hạn.

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

    if target_type == "charge" and _require_locate:
        from agv_registry import agv_registry as _reg_sat
        if _reg_sat.is_line(agv_id):
            # LUÔN chạy "chạy tiến xác nhận vị trí" (deba) dù xe đang đứng sẵn ở
            # đúng trạm sạc — đây là hành vi CỐ Ý: người vận hành có thể chủ động
            # gửi lại lệnh "Về trạm" để ép xe CHUẨN LẠI VỊ TRÍ (tiến ra tìm 1 thẻ
            # mới rồi tự tính đường quay lại, chỉ dừng hẳn khi đọc lại đúng thẻ
            # trạm sạc) — KHÔNG bỏ qua bước này chỉ vì current_tag hiện đang trùng
            # trạm đích (giá trị cũ có thể không phản ánh đúng vị trí vật lý thật).
            # NGOẠI LỆ: xe vừa TỚI node (event arrived_wait_* → firmware đọc thẻ, vị trí chắc chắn) và chưa bị gửi plan/stop/deba
            # mới (chưa di chuyển) → KHÔNG cần dò vị trí: dò = chạy mù tới thẻ kế (vd giao xong ở 14 → tự chạy sang 15 rồi
            # mới lùi về). Trạm sạc chính nó vẫn dò (người vận hành chủ động chuẩn lại vị trí).
            from line_agv_handler import line_agv_handler as _lah_trust
            _st_trust = _lah_trust.state_store.get(agv_id)
            _cfg_cur = (getattr(map_manager, "node_actions", {}) or {}).get(str(current_node)) or {}
            _at_charger = (str(_cfg_cur.get("locationType", "")).upper() == "CHARGER"
                           or str(_cfg_cur.get("arrival_action", "")).lower() == "wait_charge")
            _trusted = bool(_st_trust is not None and _st_trust.position_confirmed_tag is not None
                            and str(_st_trust.position_confirmed_tag) == str(current_node) and not _at_charger)
            if not _trusted:
                _start_locate_then_charge(agv_id)
                return {
                    "success": True, "agv_id": agv_id,
                    "target_type": target_type, "target_node": None,
                    "target_name": None, "map_id": resolved_map_id,
                    "path": [], "pending": "locate_then_charge",
                }
            print(f"[SPECIAL] {agv_id}: vừa tới node {current_node} (event arrived) — vị trí chắc chắn, BỎ dò vị trí (deba), về trạm thẳng")

    if not current_node:
        # Trước đây rơi thẳng vào plan_path_for_order() bên dưới với current_node=None
        # → agv_state không có x/y → nearest_node(0,0) chọn ĐẠI 1 node gần toạ độ (0,0)
        # trên bản đồ rồi vẫn lập/gửi lộ trình từ node sai đó, KHÔNG báo lỗi gì — xe đi
        # lệch mà không ai biết vì sao. Chặn ở đây, báo lỗi rõ (giống _dispatch_go_to).
        raise ValueError(
            f"{agv_id}: không biết vị trí hiện tại — "
            f"hãy chọn 'Vị trí xuất phát' trên bản đồ trước khi gửi lệnh"
        )

    target_info = resolve_special_target_node(agv_id, target_type)

    # PHÁT HIỆN THỰC TẾ (2026-10-08, mô phỏng 5 xe/3 trạm sạc): TẤT CẢ trạm sạc
    # đều đang có xe/đã giữ chỗ (all_occupied) nhưng vẫn cứ dispatch xe này
    # tới 1 trạm (đã có xe) như bình thường — xe chỉ "xếp hàng" ngay tại cổng
    # trạm sạc đó (cơ chế "dest occupied" chung), KHÔNG đi tới điểm chờ đã cấu
    # hình trên map (Map Editor) như vận hành thực tế mong đợi. Chuyển sang
    # "wait" NGAY (xe rời khỏi khu trạm sạc, không đứng chắn đường ai) và đặt
    # cờ charge_station_wait=True — main.monitor_charge_station_wait (watchdog
    # riêng, KHÔNG dùng pending_retry_cmd vì cờ đó bị xoá ngay khi driving=True,
    # đúng lúc xe đang lái TỚI điểm chờ) sẽ tự gọi lại "Về trạm" ngay khi xe đã
    # TỚI điểm chờ VÀ rảnh hẳn, KHÔNG cần người vận hành gọi lại tay. Chỉ áp
    # dụng cho Line AGV (field của LineAGVState); VDA5050 giữ hành vi cũ.
    if target_type == "charge" and target_info.get("all_occupied"):
        from agv_registry import agv_registry as _reg_redirect
        if _reg_redirect.is_line(agv_id):
            from line_agv_handler import line_agv_handler as _lah_redirect
            _st_redirect = _lah_redirect.state_store.get_or_create(agv_id)
            _st_redirect.charge_station_wait = True
            print(f"[SPECIAL] {agv_id}: TẤT CẢ trạm sạc đều có xe/đã giữ chỗ → "
                  f"chuyển sang 'wait' tại điểm chờ đã cấu hình, tự thử lại "
                  f"'Về trạm' sau khi có trạm trống")
            return send_agv_to_special_target(agv_id, "wait", False)

    if target_type == "charge":
        # Có trạm trống thật → đang đi sạc ĐÚNG nghĩa, không còn gì để
        # monitor_charge_station_wait phải tự thử lại nữa (tránh nó cứ gọi
        # lại go_charge thêm 1 lần dư sau khi xe đã lên đường tới trạm).
        from agv_registry import agv_registry as _reg_clear
        if _reg_clear.is_line(agv_id):
            from line_agv_handler import line_agv_handler as _lah_clear
            _st_clear = _lah_clear.state_store.get(agv_id)
            if _st_clear is not None:
                _st_clear.charge_station_wait = False

    target_node = target_info["node_id"]

    print(
        f"[SPECIAL] AGV={agv_id} | target_type={target_type} | "
        f"current_node={current_node} | raw_map={raw_map} | "
        f"resolved_map_id={resolved_map_id} | target_node={target_node}"
    )

    # ── NHIỀU TẦNG: trạm sạc/chờ nằm ở TẦNG KHÁC → đi thang tới tầng đó trước, rồi chạy lại lệnh
    # go_charge/go_wait (lúc đó xe đã cùng tầng với trạm → chọn trạm + vào trạm như bình thường).
    from agv_registry import agv_registry as _reg_fl2
    if _reg_fl2.is_line(agv_id):
        import floor_nav as _fn_fl2
        if (_fn_fl2.multi_floor(map_manager)
                and _fn_fl2.floor_of(current_node, map_manager) != _fn_fl2.floor_of(target_node, map_manager)):
            # decompose() tự từ chối xe không ra được cabin (xe không lùi/quay được chỉ đi thang có cửa ra đối diện)
            from task_queue import (agv_task_queue as _atq_fl2, CMD_GO_CHARGE as _CGC_fl2,
                                    CMD_GO_WAIT as _CGW_fl2)
            _steps_fl2 = _fn_fl2.decompose(agv_id, str(current_node), str(target_node), map_manager)
            _final_fl2 = _CGC_fl2 if target_type == "charge" else _CGW_fl2
            _rest_fl2 = list(_steps_fl2[1:-1]) + [(_final_fl2, None)]
            print(f"[ELEVATOR] {agv_id}: trạm {target_type} node {target_node} ở tầng khác → chuỗi đi thang: "
                  f"{' → '.join(f'{c}:{a}' for c, a in _steps_fl2[:-1])} → {_final_fl2}")
            from main import _start_ride_chain as _src_fl2
            _src_fl2(agv_id, [_steps_fl2[0]] + _rest_fl2)
            return {
                "success": True, "agv_id": agv_id,
                "target_type": target_type, "target_node": target_node,
                "target_name": target_info.get("name"), "map_id": resolved_map_id,
                "path": [], "pending": "elevator",
            }

    route_nodes, route_edges = plan_path_for_order(agv_id, current_node, target_node)

    from agv_registry import agv_registry
    if agv_registry.is_line(agv_id):
        from line_agv_plan_builder import (
            build_line_plan, build_plan_window, build_edge_speeds, build_edge_lidar,
        )
        from line_agv_handler import line_agv_handler
        from task_queue import agv_task_queue as _atq_s, CMD_GO_TO as _CGT_S, CMD_GO_CHARGE as _CGC_S, CMD_GO_WAIT as _CGW_S
        path         = [str(n.get("nodeId") or n) for n in route_nodes]
        points       = getattr(map_manager, "points",       {}) or {}
        node_actions = getattr(map_manager, "node_actions", {}) or {}
        roads        = getattr(map_manager, "roads",        []) or []
        edge_spd     = build_edge_speeds(roads)
        edge_lidar   = build_edge_lidar(roads)
        line_task    = "return_charge" if target_type == "charge" else "system"

        # Đọc hướng xe hiện tại
        _lstate   = line_agv_handler.state_store.get(agv_id)
        _prev_tag = str(_lstate.prev_tag) if (_lstate and _lstate.prev_tag) else None
        # PHÁT HIỆN THỰC TẾ (2026-09-28): task_lifecycle='charging' không có chỗ
        # nào xóa khi rời trạm sạc — đọc 1 lần ở đây rồi xóa ngay (giống hệt
        # last_transit_direction), không để nó nằm lại chặn mất cơ chế off_route
        # ở chặng kế tiếp. Xem giải thích đầy đủ ở _dispatch_go_to (main.py).
        _was_leaving_charger = bool(_lstate and _lstate.task_lifecycle == "charging")
        if _was_leaving_charger:
            _lstate.task_lifecycle = None

        # ── HEAD-ON check trước khi xử lý backward transit ───────────────────
        # send_agv_to_special_target có code dispatch riêng, không qua _dispatch_go_to
        # nên phải check HEAD-ON ở đây để phát hiện conflict với xe khác đang dừng/đi
        try:
            from line_agv_handler import traffic_coordinator as _tc_s
            from line_agv_handler import _charger_exit_direction as _ced_s
            # WAIT-BASED: KHÔNG maneuver (đỗ/né sang node tùy ý) lúc dispatch — gây Line
            # AGV đi sai hướng, ra khỏi line, kẹt. Cứ dispatch tuyến bình thường; khi xe
            # chạy tới gần vùng tranh chấp, _check_rolling_plan (runtime) sẽ tự DỪNG CHỜ
            # (reservation/arbiter quyết ai đi trước; deadlock → lùi về prev_tag).
            # (Khối maneuver cũ bên dưới bị tắt bằng _ho_s=None; giữ lại để tham khảo.)
            _ho_s = None
            if _ho_s is not None:
                _ho_idx_s, _ho_other_s = _ho_s
                _cur_tag_s = str(_lstate.current_tag) if (_lstate and _lstate.current_tag) else None
                # Xác định hướng dựa trên backward transit detection:
                # nếu path[1]==prev_tag → AGV cần đi lùi (bwd) để quay đầu trở lại
                # Dùng cùng logic với backward transit detection trong hàm này
                _need_bwd_s = (
                    _prev_tag and len(path) >= 2
                    and str(path[1]) == _prev_tag
                    and not (getattr(_lstate, 'last_transit_direction', '') == 'bwd'
                             if _lstate else False)
                )
                _ho_dir_raw_s = 'bwd' if _need_bwd_s else 'fwd'
                if _was_leaving_charger:
                    _ho_dir_raw_s = 'fwd'
                _ho_dir_s = _ced_s(_cur_tag_s or '', _ho_dir_raw_s)

                _parking_s = _tc_s.find_parking_node(agv_id, path, _ho_idx_s, _ho_other_s)
                if _parking_s and _parking_s[0] != _cur_tag_s:
                    _park_node_s, _entry_node_s = _parking_s
                    _entry_idx_s = path.index(_entry_node_s) if _entry_node_s in path else (_ho_idx_s - 1)
                    _transit_s   = path[:_entry_idx_s + 1] + [_park_node_s]
                    _park_dir_s  = _ced_s(_transit_s[0] if _transit_s else '', _ho_dir_s)
                    _park_plan_s = build_line_plan(
                        _transit_s, points, task_type="transit",
                        node_actions=node_actions, direction=_park_dir_s,
                        edge_speeds=edge_spd, edge_lidar=edge_lidar,
                        agv_id=agv_id, initial_prev_tag=None,
                    )
                    _rt_s = line_agv_handler.set_route(agv_id, _transit_s, "transit", direction=_park_dir_s)
                    _rt_s.window_end  = len(_transit_s) - 1
                    _rt_s.is_complete = True
                    send_generated_order(agv_id, _park_plan_s)
                    _next_cmd_s = _CGC_S if target_type == "charge" else _CGW_S
                    _atq_s.insert_next(agv_id, _next_cmd_s)
                    print(f"[SPECIAL] {agv_id}: HEAD-ON với {_ho_other_s} → "
                          f"đỗ tại {_park_node_s} (dir={_park_dir_s}), queue tiếp")
                    return {
                        "success": True, "agv_id": agv_id,
                        "target_type": target_type, "target_node": target_node,
                        "target_name": target_info.get("name"),
                        "map_id": resolved_map_id, "path": path,
                    }
                else:
                    # Không có nhánh phụ → check safe_wait
                    # BOUNCE PREVENTION: loại trừ prev_tag để tránh dao động 18↔5
                    _prev_s = str(_prev_tag) if _prev_tag else None
                    _safe_s = _tc_s.find_safe_wait_node(path, _ho_idx_s)
                    _other_reg_s = _tc_s._registered.get(_ho_other_s, {})
                    _other_fut_s = set(_other_reg_s.get('path', [])[_other_reg_s.get('current_idx', 0):])
                    if (_safe_s and _safe_s != path[0] and _safe_s != path[-1]
                            and _safe_s != _cur_tag_s and _safe_s not in _other_fut_s
                            and _safe_s != _prev_s):
                        _wait_s   = path[:path.index(_safe_s) + 1]
                        _wait_dir_s = _ced_s(_wait_s[0] if _wait_s else '', _ho_dir_s)
                        _wait_plan_s = build_line_plan(
                            _wait_s, points, task_type="transit",
                            node_actions=node_actions, direction=_wait_dir_s,
                            edge_speeds=edge_spd, edge_lidar=edge_lidar,
                            agv_id=agv_id, initial_prev_tag=None,
                        )
                        _rt_sw = line_agv_handler.set_route(agv_id, _wait_s, "transit", direction=_wait_dir_s)
                        _rt_sw.window_end  = len(_wait_s) - 1
                        _rt_sw.is_complete = True
                        send_generated_order(agv_id, _wait_plan_s)
                        _next_cmd_s = _CGC_S if target_type == "charge" else _CGW_S
                        _atq_s.insert_next(agv_id, _next_cmd_s)
                        print(f"[SPECIAL] {agv_id}: HEAD-ON với {_ho_other_s} (safe_wait={_safe_s}, dir={_wait_dir_s})")
                        return {
                            "success": True, "agv_id": agv_id,
                            "target_type": target_type, "target_node": target_node,
                            "target_name": target_info.get("name"),
                            "map_id": resolved_map_id, "path": path,
                        }
                    else:
                        # Parking và safe_wait đều fail → tìm side_node từ vị trí hiện tại
                        # (ví dụ: tại node 18, neighbor là node 5 không trên conflict path)
                        _side_found_s = False
                        if _cur_tag_s:
                            try:
                                from line_agv_handler import traffic_coordinator as _tc_sn
                                _g_sn = map_manager.line_graph if map_manager.line_graph else map_manager.graph
                                if _g_sn and _cur_tag_s in _g_sn:
                                    _path_set_sn = set(path)
                                    _other_reg_sn = _tc_sn._registered.get(_ho_other_s, {})
                                    _other_fut_sn = set(_other_reg_sn.get('path', [])[_other_reg_sn.get('current_idx', 0):])
                                    _side_cands_sn = [
                                        str(n) for n in _g_sn.neighbors(_cur_tag_s)
                                        if str(n) not in _path_set_sn
                                        and str(n) not in _other_fut_sn
                                        and str(n) != _prev_s   # BOUNCE PREVENTION
                                    ]
                                    if not _side_cands_sn and _other_reg_sn:
                                        # Bottleneck: thử following direction
                                        _other_path_sn = _other_reg_sn.get('path', [])
                                        for _nb in _g_sn.neighbors(_cur_tag_s):
                                            _nb_str = str(_nb)
                                            if _nb_str in _path_set_sn:
                                                continue
                                            try:
                                                _idx_c = _other_path_sn.index(_cur_tag_s)
                                                _idx_n = _other_path_sn.index(_nb_str)
                                                if _idx_n > _idx_c:
                                                    _side_cands_sn.append(_nb_str)
                                            except ValueError:
                                                pass
                                    if _side_cands_sn:
                                        _side_cands_sn.sort(key=lambda n: _g_sn.degree(str(n)))
                                        _side_prev_tag = str(_lstate.prev_tag) if (_lstate and _lstate.prev_tag) else None
                                        _side_dir_try  = _ced_s(_cur_tag_s, _ho_dir_s)
                                        import networkx as _nx_sn2

                                        def _is_side_navigable_sn(_path, _prev, _dir, _na):
                                            """
                                            Kiểm tra tổng quát: path đến side_node có điều hướng rõ ràng không.
                                            Áp dụng cho MỌI map layout:
                                              - Path multi-hop (>=3 nodes): an toàn — junction có turn_map.
                                              - Path 1-hop [A, B] nếu B == prev_tag: an toàn — hướng bwd tự nhiên.
                                              - Path 1-hop [A, B] nếu có turn_map entry '{prev}_{B}_{dir}': an toàn.
                                              - Path 1-hop [A, B] nếu geometry thẳng (prev→A→B ~0°): an toàn —
                                                firmware đi thẳng không cần turn command. Ví dụ: node 17 nằm giữa
                                                5 và 6 trên một đường thẳng, đi bwd từ 17 về 6 là tự nhiên.
                                            """
                                            if len(_path) < 2:
                                                return False
                                            if len(_path) >= 3:
                                                return True  # multi-hop: junction nodes có turn_map
                                            # 1-hop: [A, B]
                                            _b = str(_path[1])
                                            if not _prev or str(_b) == str(_prev):
                                                return True  # B là prev → hướng bwd tự nhiên
                                            # Kiểm tra turn_map
                                            _tm = (_na.get(str(_path[0])) or {}).get('turn_map') or {}
                                            if f"{_prev}_{_b}_{_dir}" in _tm:
                                                return True  # explicit turn_map entry → navigable
                                            # Fallback: geometry — nếu prev→A→B thẳng (không rẽ),
                                            # AGV đi tự nhiên không cần turn command.
                                            try:
                                                from line_agv_plan_builder import get_turn_direction
                                                _pts_sn = getattr(map_manager, 'points', {}) or {}
                                                _geo = get_turn_direction(_prev, str(_path[0]), _b, _pts_sn)
                                                if _geo is None:
                                                    return True  # đường thẳng → an toàn
                                            except Exception:
                                                pass
                                            return False  # có góc rẽ nhưng không có turn_map → không an toàn

                                        for _snc in _side_cands_sn:
                                            try:
                                                _side_path_s = list(_nx_sn2.shortest_path(
                                                    _g_sn, source=str(_cur_tag_s),
                                                    target=str(_snc), weight='weight'
                                                ))
                                            except Exception:
                                                _side_path_s = [_cur_tag_s, _snc]
                                            if not _is_side_navigable_sn(_side_path_s, _side_prev_tag, _side_dir_try, node_actions):
                                                print(f"[SPECIAL] {agv_id}: side_node {_snc} ambiguous navigation → bỏ qua")
                                                continue
                                            _side_node_s = _snc
                                            _side_found_s = True
                                            break
                                        if _side_found_s:
                                            _side_plan_s = build_line_plan(
                                                _side_path_s, points, task_type="transit",
                                                node_actions=node_actions, direction=_side_dir_try,
                                                edge_speeds=edge_spd, edge_lidar=edge_lidar,
                                                agv_id=agv_id, initial_prev_tag=_side_prev_tag,
                                            )
                                            _rt_sn = line_agv_handler.set_route(agv_id, _side_path_s, "transit", direction=_side_dir_try)
                                            _rt_sn.window_end  = len(_side_path_s) - 1
                                            _rt_sn.is_complete = True
                                            send_generated_order(agv_id, _side_plan_s)
                                            _next_cmd_s = _CGC_S if target_type == "charge" else _CGW_S
                                            _atq_s.insert_next(agv_id, _next_cmd_s)
                                            print(f"[SPECIAL] {agv_id}: HEAD-ON side_node={_side_node_s} path={_side_path_s} (dir={_side_dir_try}), queue tiếp")
                            except Exception as _se:
                                print(f"[SPECIAL] side_node error: {_se}")
                        if not _side_found_s:
                            # Không tìm được chỗ đỗ không-bounce → đứng yên chờ xe kia rời.
                            # 1. Hoàn thành task hiện tại để giải phóng _running (không stuck queue)
                            try:
                                from task_queue import agv_task_queue as _atq_cpl
                                _atq_cpl.on_agv_completed(agv_id, notes='bounce_wait')
                            except Exception:
                                pass
                            # 2. Set pending_retry_cmd để _check_waiting_agvs trigger khi xe cản rời
                            _retry_cmd = 'go_charge' if target_type == 'charge' else 'go_wait'
                            try:
                                from line_agv_handler import line_agv_handler as _lah_br
                                _st_br = _lah_br.state_store.get(agv_id)
                                if _st_br:
                                    _st_br.pending_retry_cmd = _retry_cmd
                            except Exception:
                                pass
                            print(f"[SPECIAL] {agv_id}: HEAD-ON với {_ho_other_s} — "
                                  f"bounce detected, đứng yên tại {_cur_tag_s} chờ xe kia rời")
                        return {
                            "success": True, "agv_id": agv_id,
                            "target_type": target_type, "target_node": target_node,
                            "target_name": target_info.get("name"),
                            "map_id": resolved_map_id, "path": path,
                        }
        except Exception as _ho_err:
            print(f"[SPECIAL] head-on check error in send_agv_to_special_target: {_ho_err}")

        # Ghi TUYẾN ĐẦY ĐỦ (intent) tới đích cuối — dù bên dưới có chia đoạn lùi (17→5)
        # rồi queue phần còn lại, xe KHÁC vẫn né được cả tuyến 5→18→4→19→…→13.
        try:
            from line_agv_handler import traffic_coordinator as _tc_intent
            _tc_intent.set_intent_route(agv_id, path)
        except Exception:
            pass

        # Xử lý đoạn lùi đầu đường (nếu planner chọn lùi trước)
        if _prev_tag and len(path) >= 2 and str(path[1]) == _prev_tag:
            _last_tdir_bwd = getattr(_lstate, 'last_transit_direction', '') if _lstate else ''
            # Kiểm tra xe có đang ở trạm sạc không (approach_dir=bwd HOẶC arrival_action=wait_charge).
            _cur_node_cfg  = node_actions.get(str(path[0])) or {}
            _cur_approach  = str(_cur_node_cfg.get("approach_dir")   or "").lower()
            _cur_arrival   = str(_cur_node_cfg.get("arrival_action") or "").lower()
            _lifecycle_chg = _was_leaving_charger
            _at_charge_bwd = (_cur_approach == "bwd") or (_cur_arrival == "wait_charge") or _lifecycle_chg
            # Rơ-moóc đứng ở trạm có kịch bản lùi mù + quay đầu: KHÔNG lùi thẳng dọc đường cũ (đúng lỗi 26/11: lệnh khu chờ gửi DIR_BWD
            # 10→11, xe lùi vào vật cản). Rơi xuống nhánh dưới, nơi bước lùi mù + quay được chèn (giống go_to).
            _trailer_script = False
            try:
                from main import _trailer_has_exit_script as _ths
                _trailer_script = _ths(agv_id, str(path[0]), _cur_node_cfg)
            except Exception as _e_ths:
                print(f"[SPECIAL] {agv_id}: kiểm tra kịch bản thoát trạm lỗi (bỏ qua): {_e_ths}")
            if _last_tdir_bwd == "bwd" or _at_charge_bwd or _trailer_script:
                # AGV lùi vào (server-route hoặc thủ công) — front hướng ra ngoài → TIẾN.
                if _lstate:
                    _lstate.last_transit_direction = ''
                print(f"[SPECIAL] {agv_id}: post-backward route → skip transit, dùng direction=fwd"
                      f" (reason: last_tdir={_last_tdir_bwd!r} at_charge_bwd={_at_charge_bwd})")
            else:
                bwd_end  = 1
                cur_from = _prev_tag
                for _bi in range(1, len(path) - 1):
                    if str(path[_bi + 1]) == str(cur_from):
                        cur_from = path[_bi]
                        bwd_end  = _bi + 1
                    else:
                        break
                bwd_seg  = path[:bwd_end + 1]
                # QUAN TRỌNG: nếu đoạn lùi này ĐÃ tới thẳng đích cuối (target_node) —
                # trường hợp thường gặp khi target_node CHỈ CÁCH vị trí hiện tại 1-2 node
                # (vd vừa "chạy tiến xác nhận vị trí" ra khỏi trạm sạc rồi lùi ngay lại) —
                # đây chính là CHẶNG CUỐI, không phải 1 đoạn lùi TẠM giữa đường. Trước đây
                # luôn gắn cứng task_type="transit" + queue thêm 1 lệnh go_charge/go_wait
                # NGAY CẢ KHI đoạn lùi đã là toàn bộ hành trình → xe tới đích xong lại chạy
                # lại TOÀN BỘ chu trình "chạy tiến xác nhận vị trí" một lần nữa (đúng lỗi
                # thực tế: 1 lệnh "Về trạm" thực hiện thành 2 lần ra/vào trạm liên tiếp).
                # Đồng thời "transit" luôn kết thúc bằng WAIT_SYS (1) chứ không phải
                # WAIT_CHARGE (35) dù đích thật là trạm sạc — sai cả arrival action.
                _bwd_is_final = str(bwd_seg[-1]) == str(target_node)
                _bwd_task     = line_task if _bwd_is_final else "transit"
                # QUAN TRỌNG (phát hiện thực tế): build_line_plan() luôn build TRỌN
                # đoạn lùi (w_end=len-1), BỎ QUA hoàn toàn cửa sổ an toàn mà
                # set_route() vừa tính (có thể CẮT ngắn vì conflict/reservation phía
                # trước — vd node đích đang bị xe khác giữ). Trước đây gọi
                # build_line_plan() TRƯỚC rồi set_route() SAU và vứt luôn kết quả →
                # xe vẫn bị lệnh chạy hết TRỌN đoạn lùi dù traffic engine đã quyết
                # định "chờ tại node an toàn" (log "window CẮT theo conflict" không
                # có tác dụng gì lên plan thực sự gửi xuống xe). Phải set_route()
                # TRƯỚC để lấy window_end đã được CẮT theo an toàn, rồi build plan
                # đúng bằng cửa sổ đó (build_plan_window, không phải build_line_plan).
                _rt_bwd_s = line_agv_handler.set_route(agv_id, bwd_seg, _bwd_task, direction="bwd")
                bwd_plan = build_plan_window(
                    full_path=bwd_seg, w_start=0, w_end=_rt_bwd_s.window_end,
                    points=points, is_final=_rt_bwd_s.is_complete, task_type=_bwd_task,
                    node_actions=node_actions, direction="bwd",
                    edge_speeds=edge_spd, edge_lidar=edge_lidar,
                    agv_id=agv_id, initial_prev_tag=None)
                send_generated_order(agv_id, bwd_plan)
                if not _bwd_is_final:
                    # Đoạn lùi TẠM (chưa tới đích) — dùng CMD_GO_CHARGE/CMD_GO_WAIT để
                    # giữ đúng task_type cho chặng CÒN LẠI sau khi lùi xong.
                    _next_cmd = _CGC_S if target_type == "charge" else _CGW_S
                    _atq_s.insert_next(agv_id, _next_cmd)
                return {
                    "success": True,
                    "agv_id": agv_id,
                    "target_type": target_type,
                    "target_node": target_node,
                    "target_name": target_info.get("name"),
                    "map_id": resolved_map_id,
                    "planId": bwd_plan.get("id"),
                    "path": path,
                }

        # Đọc last_transit_direction TRƯỚC khi clear
        _last_tdir_pre  = getattr(_lstate, 'last_transit_direction', '') if _lstate else ''
        _is_post_charge = _was_leaving_charger

        # initial_prev_tag: tính góc rẽ tại start node theo hướng đến từ prev_tag — chỉ
        # đúng khi xe đi xuyên qua node. NGOẠI LỆ: xe xuất phát từ TRẠM SẠC (CHARGER):
        # trạm approach_dir=bwd → xe lùi vào, mặt quay ra ngoài → xuất phát đi THẲNG theo
        # hướng đang quay, không theo prev_tag → bỏ tính turn tại node đầu. TỔNG QUÁT cho
        # MỌI node locationType=CHARGER (không hardcode), mọi lần ra trạm (không chỉ charging).
        _cur_cfg_exit = (node_actions.get(str(path[0])) or {}) if path else {}
        _exit_from_charger = (
            str(_cur_cfg_exit.get('locationType', '')).upper() == 'CHARGER'
            or str(_cur_cfg_exit.get('arrival_action', '')).lower() == 'wait_charge'
        )
        # CHỈ bỏ tính turn khi xe ĐANG Ở TRẠM SẠC (path[0]=CHARGER). KHÔNG dùng
        # _is_post_charge (lifecycle='charging' còn sót sau khi rời trạm → ở node
        # thường vẫn bị bỏ rẽ → đi thẳng nhầm node).
        _suppress_initial_turn = _exit_from_charger
        _initial_prev        = _prev_tag if not _suppress_initial_turn else None
        _initial_arrived_bwd = (_last_tdir_pre == 'bwd' and not _suppress_initial_turn)

        # Khi AGV vừa xong bwd transit → tiếp tục direction=bwd (rẽ + lùi tiếp).
        # KHÔNG dùng direction=fwd vì firmware có thể chạy tiến trước khi rẽ.
        _line_dir = "bwd" if (_last_tdir_pre == 'bwd' and not _is_post_charge) else "fwd"

        if _lstate:
            _lstate.last_transit_direction = ''
        print(f"[SPECIAL] {agv_id}: direction={_line_dir} "
              f"(last_tdir={_last_tdir_pre!r}, post_charge={_is_post_charge})")

        # ── CỬA TỰ ĐỘNG trên đường đi: tách route tại node cửa đầu tiên mà xe đang TIẾN VÀO (giống _dispatch_go_to) ──
        # Xe dừng ở node cửa (WAIT_SYS), line_agv_handler._handle_door_arrival xin mở và giữ xe tới khi cửa xác nhận mở, rồi
        # resume_after_door cho hàng đợi chạy tiếp lệnh khu chờ/về trạm xếp sẵn dưới đây. Trước đây hàm này không tách route nên
        # xe chạy xuyên qua cửa khi chưa mở (26/11). Hướng THOÁT cửa (đã vào từ node khác của cùng cửa) thì đi thẳng.
        _door_split_s = None
        try:
            from door_coordinator import door_coordinator as _dc_s
            for _si_s in range(1, len(path) - 1):
                _did_s = str((node_actions.get(str(path[_si_s])) or {}).get('door_id') or '').strip()
                if not _did_s:
                    continue
                if _dc_s.is_exit_arrival(_did_s, agv_id, str(path[_si_s])):
                    continue
                _door_split_s = _si_s
                print(f"[SPECIAL] {agv_id}: node {path[_si_s]} = cửa tự động '{_did_s}' — xe TIẾN VÀO, dừng xin mở cửa trước khi qua")
                break
        except Exception as _e_dr:
            print(f"[SPECIAL] {agv_id}: kiểm tra cửa tự động lỗi (bỏ qua): {_e_dr}")
        if _door_split_s is not None:
            path = path[:_door_split_s + 1]
            line_task = "delivery"      # chặng tới cửa kết thúc bằng WAIT_SYS như go_to
        _rt = line_agv_handler.set_route(agv_id, path, line_task, direction=_line_dir)
        # Xe RƠ-MOÓC rời trạm sạc (mũi quay vào trong): phải lùi mù + quay đầu TRƯỚC khi tiến ra — cùng kịch bản với dispatch go_to
        # (main._build_trailer_exit_steps). Trước đây chỉ go_to có; lệnh khu chờ/về trạm bỏ sót nên rơ-moóc không đi ra được.
        _te_steps = []
        try:
            if _exit_from_charger:
                from main import _build_trailer_exit_steps as _bte, _with_trailer_exit_defaults as _wted
                _te_steps = _bte(agv_id, path, True, _wted(agv_id, str(path[0]), _cur_cfg_exit), edge_spd)
        except Exception as _e_te:
            print(f"[SPECIAL] {agv_id}: tạo bước lùi mù thoát trạm lỗi (bỏ qua): {_e_te}")
        _rt.has_exit_steps = bool(_te_steps)
        # Gửi CỬA SỔ ĐẦU (≤LOOKAHEAD node) — rolling gửi tiếp nếu đường dài (tránh tràn buffer)
        order = build_plan_window(
            full_path=path, w_start=0, w_end=_rt.window_end, points=points,
            is_final=_rt.is_complete, task_type=line_task,
            node_actions=node_actions, direction=_line_dir,
            edge_speeds=edge_spd, edge_lidar=edge_lidar, agv_id=agv_id,
            initial_prev_tag=_initial_prev, initial_arrived_bwd=_initial_arrived_bwd,
            skip_initial_dir=bool(_te_steps))
        if _te_steps:
            order["d"] = _te_steps + order.get("d", [])
        send_generated_order(agv_id, order)
        if _door_split_s is not None:
            _atq_s.insert_next(agv_id, _CGC_S if target_type == "charge" else _CGW_S)
        return {
            "success": True,
            "agv_id": agv_id,
            "target_type": target_type,
            "target_node": target_node,
            "target_name": target_info.get("name"),
            "map_id": resolved_map_id,
            "planId": order.get("id"),
            "path": path,
        }

    # VDA5050: giữ nguyên logic cũ
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

async def find_named_node_with_action_async(
    pool,
    map_id: str,
    candidates: list[str],
    line_agv: bool = False,
) -> dict | None:
    """
    Tìm node theo map_id và danh sách tên có thể trong agv_map_points.
    line_agv=True: chỉ trả về node có agvCompat RFID/both (hoặc chưa cấu hình — backward compat).
    """
    map_id = str(map_id or "").strip()
    if not map_id or not candidates:
        return None

    # Clause lọc agvCompat cho Line AGV
    # Node chưa set agvCompat (NULL/rỗng) → backward compat: vẫn cho Line AGV dùng
    compat_clause = (
        """
        AND (
            action IS NULL
            OR COALESCE(action->>'agvCompat', '') = ''
            OR action->>'agvCompat' IN ('RFID', 'both')
        )
        """
        if line_agv else ""
    )

    try:
        async with pool.acquire() as conn:
            for name in candidates:
                row = await conn.fetchrow(
                    f"""
                    SELECT name_id, name, action
                    FROM agv_map_points
                    WHERE CAST(map_id AS TEXT) = $1
                      AND (
                            LOWER(TRIM(COALESCE(name, ''))) = LOWER(TRIM($2))
                         OR LOWER(TRIM(COALESCE(name_id, ''))) = LOWER(TRIM($2))
                      )
                      {compat_clause}
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

def find_named_node_with_action_via_pool(
    map_id: str,
    candidates: list[str],
    line_agv: bool = False,
) -> dict | None:
    """
    Wrapper sync để gọi hàm async tra node map bằng app.state.db_pool.
    line_agv=True: chỉ trả node agvCompat RFID/both (hoặc chưa cấu hình).
    """
    try:
        app = get_app()
        loop = getattr(app.state, "loop", None)
        pool = getattr(app.state, "db_pool", None)

        if not loop or not loop.is_running() or pool is None:
            print("[DB] db_pool hoặc event loop chưa sẵn sàng")
            return None

        fut = asyncio.run_coroutine_threadsafe(
            find_named_node_with_action_async(pool, map_id, candidates, line_agv=line_agv),
            loop
        )
        return fut.result(timeout=20)
    except Exception as e:
        print(f"[DB] find_named_node_with_action_via_pool thất bại | map_id={map_id} | candidates={candidates} | lỗi={e}")
        return None

async def find_node_by_type_async(
    pool,
    map_id: str,
    node_type: int,
    line_agv: bool = False,
) -> dict | None:
    """
    Tìm node theo loại trạm — ưu tiên JSONB action->>'locationType' vì đây là
    giá trị map editor luôn lưu (VD: 'CHARGER', 'BUFFER', 'WAIT', 'PARKING', 'HOME').
    Fallback về cột type INTEGER (2=charger, 5=buffer, 6=parking, 7=wait).
    """
    # Map type int → locationType string (map_editor lưu n.type.toUpperCase())
    _LOCATION_TYPES: dict[int, list[str]] = {
        2: ["CHARGER"],
        5: ["BUFFER", "WAIT", "PARKING", "HOME"],
        6: ["PARKING", "BUFFER"],
        7: ["WAIT",   "BUFFER"],
    }
    location_types = _LOCATION_TYPES.get(node_type, [])
    try:
        async with pool.acquire() as conn:
            row = None
            # Ưu tiên 1: JSONB locationType (ví dụ: CHARGER, BUFFER, WAIT...)
            if location_types:
                row = await conn.fetchrow(
                    """
                    SELECT name_id, name, action
                    FROM agv_map_points
                    WHERE CAST(map_id AS TEXT) = $1
                      AND action->>'locationType' = ANY($2::text[])
                    LIMIT 1
                    """,
                    str(map_id),
                    location_types,
                )
            # Fallback: cột type INTEGER
            if row is None:
                row = await conn.fetchrow(
                    """
                    SELECT name_id, name, action
                    FROM agv_map_points
                    WHERE CAST(map_id AS TEXT) = $1
                      AND type = $2
                    LIMIT 1
                    """,
                    str(map_id),
                    node_type,
                )
            if row and row.get("name_id") is not None:
                return {
                    "node_id": str(row["name_id"]).strip(),
                    "name": row.get("name"),
                    "action": row.get("action"),
                }
        return None
    except Exception as e:
        print(f"[DB] find_node_by_type_async thất bại | map_id={map_id} | type={node_type} | lỗi={e}")
        return None


def find_node_by_type_via_pool(
    map_id: str,
    node_type: int,
    line_agv: bool = False,
) -> dict | None:
    """Sync wrapper: tìm node theo type integer (2=charger, 5=buffer/wait)."""
    try:
        app = get_app()
        loop = getattr(app.state, "loop", None)
        pool = getattr(app.state, "db_pool", None)
        if not loop or not loop.is_running() or pool is None:
            return None
        fut = asyncio.run_coroutine_threadsafe(
            find_node_by_type_async(pool, map_id, node_type, line_agv=line_agv),
            loop,
        )
        return fut.result(timeout=5)
    except Exception as e:
        print(f"[DB] find_node_by_type_via_pool thất bại | map_id={map_id} | type={node_type} | lỗi={e}")
        return None


async def find_all_nodes_by_type_async(
    pool,
    map_id: str,
    node_type: int,
    line_agv: bool = False,
) -> list[dict]:
    """Trả về TẤT CẢ nodes có locationType/type khớp (dùng để chọn trạm tốt nhất)."""
    _LOCATION_TYPES: dict[int, list[str]] = {
        2: ["CHARGER"],
        5: ["BUFFER", "WAIT", "PARKING", "HOME"],
        6: ["PARKING", "BUFFER"],
        7: ["WAIT", "BUFFER"],
    }
    location_types = _LOCATION_TYPES.get(node_type, [])
    try:
        async with pool.acquire() as conn:
            rows = []
            if location_types:
                rows = await conn.fetch(
                    """
                    SELECT name_id, name, action
                    FROM agv_map_points
                    WHERE CAST(map_id AS TEXT) = $1
                      AND action->>'locationType' = ANY($2::text[])
                    ORDER BY name_id
                    """,
                    str(map_id), location_types,
                )
            if not rows:
                rows = await conn.fetch(
                    """
                    SELECT name_id, name, action
                    FROM agv_map_points
                    WHERE CAST(map_id AS TEXT) = $1 AND type = $2
                    ORDER BY name_id
                    """,
                    str(map_id), node_type,
                )
            return [
                {"node_id": str(r["name_id"]).strip(), "name": r.get("name"), "action": r.get("action")}
                for r in rows if r.get("name_id") is not None
            ]
    except Exception as e:
        print(f"[DB] find_all_nodes_by_type_async lỗi | map_id={map_id} | type={node_type} | {e}")
        return []


def find_all_nodes_by_type_via_pool(
    map_id: str,
    node_type: int,
    line_agv: bool = False,
) -> list[dict]:
    """Sync wrapper: tìm tất cả nodes theo type.
    Danh sách trạm (sạc/chờ) gần như tĩnh nên có cache: event loop bận làm DB quá hạn thì dùng bản cũ
    thay vì trả [] (trước đây [] khiến báo sai "Không tìm thấy node charge" và xe bị bỏ rơi)."""
    key = (str(map_id), node_type, bool(line_agv))
    hit = _NODES_BY_TYPE_CACHE.get(key)
    if hit and time.monotonic() - hit[0] < NODES_BY_TYPE_CACHE_TTL_SEC:
        return list(hit[1])
    try:
        app  = get_app()
        loop = getattr(app.state, "loop", None)
        pool = getattr(app.state, "db_pool", None)
        if not loop or not loop.is_running() or pool is None:
            return list(hit[1]) if hit else []
        fut = asyncio.run_coroutine_threadsafe(
            find_all_nodes_by_type_async(pool, map_id, node_type, line_agv=line_agv),
            loop,
        )
        try:
            res = fut.result(timeout=20)
        except concurrent.futures.TimeoutError:
            fut.cancel()
            raise
        if res:
            _NODES_BY_TYPE_CACHE[key] = (time.monotonic(), list(res))
        return res
    except Exception as e:
        print(f"[DB] find_all_nodes_by_type_via_pool lỗi | {type(e).__name__}: {e}"
              f"{' → dùng cache cũ' if hit else ''}")
        return list(hit[1]) if hit else []


_NODES_BY_TYPE_CACHE: dict = {}
NODES_BY_TYPE_CACHE_TTL_SEC = 60.0


# ── Station reservation: đặt chỗ ngay khi pick, trước khi route được set ─────
# {station_node_id: agv_id} — chỉ ghi khi AGV được phân công về trạm đó
_station_reservations: dict[str, str] = {}
_station_reservations_lock = __import__("threading").Lock()


def reserve_station(station_node: str, agv_id: str) -> None:
    """Đặt chỗ trạm ngay khi chọn xong — trước khi route được set."""
    with _station_reservations_lock:
        # Xóa reservation cũ của cùng AGV trước (tránh leak khi re-dispatch)
        for k in list(_station_reservations):
            if _station_reservations[k] == agv_id:
                del _station_reservations[k]
        _station_reservations[station_node] = agv_id
    print(f"[STATION] Reserved: node={station_node} → {agv_id} | all={dict(_station_reservations)}")


def release_station(agv_id: str, reason: str = "") -> None:
    """Giải phóng reservation khi AGV đến trạm, rời trạm, hoặc lệnh bị hủy."""
    with _station_reservations_lock:
        removed = {k: v for k, v in _station_reservations.items() if v == agv_id}
        for k in removed:
            del _station_reservations[k]
    if removed:
        print(f"[STATION] Released: {agv_id} → {list(removed.keys())} ({reason})")


def _pick_least_claimed_station(
    station_nodes: list[dict],
    requesting_agv_id: str,
    map_id: str,
) -> tuple[dict | None, bool]:
    """
    Trong danh sách station_nodes, chọn trạm bị "claim" ít nhất.
    Claim = AGV đang đứng tại trạm (weight 2) hoặc đang có route đích đến đó (weight 1)
    hoặc đã được reserve_station() giữ chỗ (weight 10).

    Trả (node_info, all_occupied) — all_occupied=True khi NGAY CẢ trạm ít bị claim
    nhất cũng đang có xe khác đứng VẬT LÝ hoặc đã được reserve (claims>=2) → không
    còn trạm nào thật sự trống, caller (send_agv_to_special_target) dùng để quyết
    định đưa xe này sang "wait" thay vì xếp hàng chờ ngay tại 1 trạm đã có xe.
    """
    if not station_nodes:
        return None, False
    if len(station_nodes) == 1:
        return station_nodes[0], False

    node_ids = {n["node_id"]: n for n in station_nodes}
    claims   = {nid: 0 for nid in node_ids}

    # ── Reservation (đặt chỗ tức thì — weight cao nhất) ──────────────────────
    with _station_reservations_lock:
        _res_snapshot = dict(_station_reservations)
    for _res_node, _res_agv in _res_snapshot.items():
        if _res_agv != requesting_agv_id and _res_node in claims:
            claims[_res_node] += 10   # reservation > bất kỳ heuristic nào

    # ── VDA5050: kiểm tra vị trí hiện tại ──────────────────────────────────
    for agv_id, state in agv_manager.list_agvs().items():
        if agv_id == requesting_agv_id:
            continue
        cur_node = str(state.get("lastNodeId") or "").strip()
        if cur_node in claims:
            claims[cur_node] += 2  # đang đứng tại trạm → ưu tiên né

    # ── VDA5050: kiểm tra route đang đi (đích cuối) ─────────────────────────
    try:
        from main import traffic_engine as _te
        for agv_id, route in _te._routes.items():
            if agv_id == requesting_agv_id or not route or not route.segments:
                continue
            goal = str(route.segments[-1].to_node).strip()
            if goal in claims:
                claims[goal] += 1
    except Exception:
        pass

    # ── Line AGV: kiểm tra vị trí + đích route ──────────────────────────────
    try:
        from line_agv_handler import line_agv_handler as _lah
        # Vị trí hiện tại
        for agv_id, st in _lah.state_store._states.items():
            if agv_id == requesting_agv_id or st is None:
                continue
            cur_tag = str(st.current_tag or "").strip()
            if cur_tag in claims:
                claims[cur_tag] += 2
        # Destination từ _routes (KHÔNG phải LineAGVState.route)
        for agv_id, route in _lah._routes.items():
            if agv_id == requesting_agv_id or not route or not route.full_path:
                continue
            dest_tag = str(route.full_path[-1]).strip()
            if dest_tag in claims:
                claims[dest_tag] += 1
    except Exception:
        pass

    # ── Đường tới trạm bị XE KHÁC đang đứng chặn? ───────────────────────────────────────────────────────
    # PHÁT HIỆN THỰC TẾ (25/11, AGV01 về sạc từ node 4): 2 trạm (1 và 27) cùng 0 claim → chọn trạm 1 theo thứ tự, nhưng đường tới trạm 1
    # đi qua node 2 nơi AGV03 đang đỗ → AGV01 đứng chờ head-on ~70 s ở node 4 (tới khi hệ thống ép AGV03 nhường), trong khi trạm 27
    # (4→3→27) hoàn toàn thông. Cộng điểm phạt theo số node TRÊN ĐƯỜNG (không tính node xuất phát và chính trạm) đang có xe khác đứng;
    # chỉ dùng để chọn giữa các trạm — KHÔNG ảnh hưởng cờ all_occupied (theo claim thật của trạm).
    path_penalty = {nid: 0 for nid in node_ids}
    try:
        from line_agv_handler import line_agv_handler as _lah_pp
        _me = _lah_pp.state_store.get(requesting_agv_id)
        _g_pp = map_manager.line_graph if map_manager.line_graph else map_manager.graph
        if _me is not None and _me.current_tag not in (None, 0) and _g_pp is not None:
            _start = str(_me.current_tag)
            _stationary = {}
            for _oid, _ost in _lah_pp.state_store._states.items():
                if _oid == requesting_agv_id or _ost is None or _ost.current_tag in (None, 0):
                    continue
                _stationary[str(_ost.current_tag)] = _oid
            if _start in _g_pp:
                import networkx as _nx_pp
                for nid in node_ids:
                    if nid == _start or nid not in _g_pp:
                        continue
                    try:
                        _path = _nx_pp.shortest_path(_g_pp, _start, nid, weight="weight")
                    except Exception:
                        path_penalty[nid] += 5            # không có đường tới trạm này → tránh
                        continue
                    _blocked = [n for n in _path[1:-1] if n in _stationary]
                    if _blocked:
                        path_penalty[nid] += 3 * len(_blocked)
                        print(f"[STATION] {requesting_agv_id}: đường tới trạm {nid} {_path} bị chặn bởi "
                              f"{[(n, _stationary[n]) for n in _blocked]} → phạt {3 * len(_blocked)}")
    except Exception as _e_pp:
        print(f"[STATION] tính đường bị chặn lỗi (bỏ qua): {_e_pp}")

    # ── Mức ưu tiên cấu hình trên node (action.station_priority, số NHỎ = ưu tiên CAO; không khai = thấp nhất) ──
    # Thứ tự chọn: node CHƯA ai chiếm/giữ/đang tới/bị chắn đường trước → rồi ưu tiên cao → rồi ít bị chiếm. Không node nào khai ưu tiên thì
    # kết quả y hệt cách chọn cũ (điểm thấp nhất, hoà lấy node đầu danh sách).
    def _prio_of(nid):
        a = (node_ids.get(nid) or {}).get("action")
        if isinstance(a, str):
            try:
                import json as _json_pr
                a = _json_pr.loads(a) if a else {}
            except Exception:
                a = {}
        try:
            v = int((a or {}).get("station_priority") or 0)
        except (TypeError, ValueError):
            v = 0
        return v if v > 0 else 9999

    def _rank(nid):
        score = claims[nid] + path_penalty.get(nid, 0)
        return (score > 0, _prio_of(nid), score, claims[nid])

    best_id = min(claims, key=_rank)
    all_occupied = claims[best_id] >= 2
    print(f"[STATION] {requesting_agv_id}: chọn trạm={best_id} | claims={claims}"
          f"{' | phạt đường=' + str({k: v for k, v in path_penalty.items() if v}) if any(path_penalty.values()) else ''}"
          f"{' | TẤT CẢ trạm đều có xe/đã giữ chỗ' if all_occupied else ''}")
    return node_ids[best_id], all_occupied


async def find_node_by_arrival_action_async(
    pool,
    map_id: str,
    arrival_action_value: str,
    line_agv: bool = False,
) -> dict | None:
    """Fallback: tìm node theo action->>'arrival_action' trong JSONB khi tìm theo tên thất bại."""
    compat_clause = (
        """
        AND (
            action IS NULL
            OR COALESCE(action->>'agvCompat', '') = ''
            OR action->>'agvCompat' IN ('RFID', 'both')
        )
        """
        if line_agv else ""
    )
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                SELECT name_id, name, action
                FROM agv_map_points
                WHERE CAST(map_id AS TEXT) = $1
                  AND action IS NOT NULL
                  AND action->>'arrival_action' = $2
                  {compat_clause}
                LIMIT 1
                """,
                str(map_id),
                arrival_action_value,
            )
            if row and row.get("name_id") is not None:
                return {
                    "node_id": str(row["name_id"]).strip(),
                    "name": row.get("name"),
                    "action": row.get("action"),
                }
        return None
    except Exception as e:
        print(f"[DB] find_node_by_arrival_action_async thất bại | map_id={map_id} | arrival_action={arrival_action_value} | lỗi={e}")
        return None


def find_node_by_arrival_action_via_pool(
    map_id: str,
    arrival_action_value: str,
    line_agv: bool = False,
) -> dict | None:
    """Sync wrapper: tìm node theo arrival_action JSONB khi tìm tên thất bại."""
    try:
        app = get_app()
        loop = getattr(app.state, "loop", None)
        pool = getattr(app.state, "db_pool", None)
        if not loop or not loop.is_running() or pool is None:
            return None
        fut = asyncio.run_coroutine_threadsafe(
            find_node_by_arrival_action_async(pool, map_id, arrival_action_value, line_agv=line_agv),
            loop,
        )
        return fut.result(timeout=5)
    except Exception as e:
        print(f"[DB] find_node_by_arrival_action_via_pool thất bại | map_id={map_id} | arrival_action={arrival_action_value} | lỗi={e}")
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


def _planner_dest_priority(node_actions: dict, end_node) -> int:
    """Ưu tiên (priority) của xe đang lập kế hoạch suy theo LOẠI node đích:
    CHARGER/wait_charge → return_charge(1); còn lại → delivery(3). Dùng khi xe CHƯA
    registered (vd vừa picking xong) để KHÔNG bị rank mặc định 2 → né nhầm xe khác."""
    _cfg = (node_actions or {}).get(str(end_node)) or {}
    if (str(_cfg.get('locationType', '')).upper() == 'CHARGER'
            or str(_cfg.get('arrival_action', '')).lower() == 'wait_charge'):
        return 1
    return 3


def _planner_should_avoid(my_prio: int, my_id: str,
                          other_prio: int, other_id: str) -> bool:
    """me có nên NÉ đường other không? CHỈ khi other MẠNH hơn theo (priority, id).
    Antisymmetric → đúng 1 xe né. Dùng my_prio THẬT (không mặc định 2) để xe winner
    KHÔNG né nhầm (gốc lỗi: cả 2 cùng né → đâm)."""
    return (other_prio, str(other_id)) > (my_prio, str(my_id))


def _path_is_headon_against(my_dir_edges: set, other_path: list,
                            other_cur: int = 0) -> bool:
    """True nếu other_path đi NGƯỢC chiều ta trên ≥1 cạnh vật lý CHUNG (head-on).
    my_dir_edges = tập cạnh CÓ HƯỚNG (a,b) của đường ta. Xe kia đi a→b mà ta đi b→a
    trên cùng cạnh = head-on. Cùng chiều hoàn toàn (following) hoặc rời nhau → False.
    Dùng để chỉ NÉ xe ngược chiều, KHÔNG bắt xe đi vòng tránh xe cùng chiều (following)."""
    for _j in range(other_cur, len(other_path) - 1):
        if (str(other_path[_j + 1]), str(other_path[_j])) in my_dir_edges:
            return True
    return False


def _agv_future_path(oid: str, tc, lah) -> list:
    """Phần đường CÒN LẠI của xe `oid` (ưu tiên tuyến đầy đủ intent, tính từ vị trí thật)."""
    intent = tc._intent_route.get(oid)
    if intent and len(intent) >= 2:
        try:
            st = lah.state_store.get(oid)
            if st and st.current_tag is not None:
                return [str(n) for n in intent[intent.index(str(st.current_tag)):]]
        except ValueError:
            pass
        return [str(n) for n in intent]
    reg = tc._registered.get(oid, {}) or {}
    return [str(n) for n in (reg.get('path') or [])[int(reg.get('current_idx', 0) or 0):]]


class _HeadOnWait(Exception):
    """Báo hiệu: HEAD-ON nhưng chọn chờ → bỏ qua đường thay thế."""


HEADON_WAIT_MAX_SHARED_EDGES = 4   # đoạn đối đầu dài tới mức này vẫn ưu tiên CHỜ xe kia đi qua


def _head_on_should_wait(agv_id: str, opp_id: str, my_path: list) -> bool:
    """HEAD-ON với `opp_id`: True = nên ĐỨNG CHỜ xe kia đi qua (không đi đường vòng).
    Chờ khi: xe kia đang chạy (sẽ đi qua nhanh), đoạn chung ngắn, và KHÔNG xe thứ 3 nào cũng cần các node
    của đoạn đó. Có xe thứ 3 cần đoạn đó (tuyến sẽ đông) hoặc xe kia đứng yên (chặn lâu) → đi vòng."""
    try:
        from line_agv_handler import line_agv_handler as _lah, traffic_coordinator as _tc
        mine = [str(n) for n in my_path]
        my_edges = {frozenset((mine[i], mine[i + 1])) for i in range(len(mine) - 1)}
        opp = _agv_future_path(opp_id, _tc, _lah)
        shared = {frozenset((opp[i], opp[i + 1])) for i in range(len(opp) - 1)} & my_edges
        if not shared or len(shared) > HEADON_WAIT_MAX_SHARED_EDGES:
            return False
        ost = _lah.state_store.get(opp_id)
        if ost is not None and not getattr(ost, 'driving', False):
            return False                       # xe kia đang đứng yên → có thể chặn lâu
        shared_nodes = {n for e in shared for n in e}
        for oid in set(_tc._registered) | set(_tc._intent_route):
            if oid in (agv_id, opp_id):
                continue
            if shared_nodes & set(_agv_future_path(oid, _tc, _lah)):
                return False                   # xe thứ 3 cũng cần đoạn này
        return True
    except Exception:
        return False


async def plan_path_async(agv_id: str, start_node_id: str | None, end_node_id: str,
                          session_id: str | None = None):
    """Bọc _plan_path_async_impl trong VÙNG HOẠT ĐỘNG của xe: đồ thị tìm đường đã loại các
    node xe này không được vào (xem MapManager.agv_scope); đích nằm trong vùng cấm → báo
    lỗi rõ ràng ngay, không đi tìm đường."""
    if end_node_id is not None and not map_manager.is_node_allowed(agv_id, end_node_id):
        from agv_registry import agv_registry as _areg_zone
        raise ValueError(
            f"Node {end_node_id} nằm trong VÙNG CẤM của loại xe "
            f"'{_areg_zone.get_config(agv_id).get('agv_type')}' (xe {agv_id}) — không thể điều xe tới đó")
    with map_manager.agv_scope(agv_id):
        result = await _plan_path_async_impl(agv_id, start_node_id, end_node_id, session_id)
    # Lớp bảo vệ CUỐI: dù planner nào đã tính đường, tuyệt đối không giao đường có node cấm
    # (trừ node xuất phát — xe đang đứng sẵn ở đó thì vẫn phải rời đi được).
    try:
        _nodes = [str(n.get("nodeId")) for n in (result[0] or [])]
        _bad = [n for n in _nodes[1:] if n in map_manager.forbidden_nodes(agv_id)]
    except Exception:
        _bad = []
    if _bad:
        raise ValueError(f"Đường đi của {agv_id} đi qua node thuộc VÙNG CẤM {_bad} — huỷ lệnh, "
                         f"kiểm tra lại cấu hình vùng hoạt động của map")
    # Trạm sạc là ĐIỂM CUỐI bản đồ: đường đi chỉ được KẾT THÚC tại trạm sạc, không được đi XUYÊN
    # qua (đi quá sẽ ra ngoài bản đồ). Node xuất phát (xe đang đứng) và node cuối được miễn.
    try:
        _chs = map_manager.charger_nodes()
        _thru = [n for n in _nodes[1:-1] if n in _chs]
    except Exception:
        _thru = []
    if _thru:
        raise ValueError(f"Đường đi của {agv_id} đi XUYÊN qua trạm sạc {_thru} (điểm cuối bản đồ) — "
                         f"huỷ lệnh")
    # Hướng riêng theo loại xe: tuyệt đối không giao đường đi NGƯỢC chiều cho phép của loại xe này
    # (vd rơ-moóc trên đoạn chỉ được đi 1 chiều).
    try:
        _fe = map_manager.forbidden_edges(agv_id)
        _bad_e = [(a, b) for a, b in zip(_nodes, _nodes[1:]) if (a, b) in _fe]
    except Exception:
        _bad_e = []
    if _bad_e:
        raise ValueError(f"Đường đi của {agv_id} đi NGƯỢC chiều cho phép của loại xe trên cạnh {_bad_e} — "
                         f"huỷ lệnh, kiểm tra cài đặt hướng riêng theo loại xe của cạnh")
    return result


async def _plan_path_async_impl(agv_id: str, start_node_id: str | None, end_node_id: str,
                                session_id: str | None = None):
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

    from agv_registry import agv_registry as _areg_plan

    if _areg_plan.is_line(agv_id):
        # Line AGV: lấy map_id từ registry (agv_devices.map_id), state từ line_agv_handler
        from line_agv_handler import line_agv_handler as _lah
        _line_st = _lah.state_store.get(agv_id)
        raw_map  = _areg_plan.get_map_id(agv_id) or \
                   str(getattr(map_manager, "current_map_id", "") or "").strip()
        _cur_tag = str(_line_st.current_tag) if (_line_st and _line_st.current_tag) else start_node_id
        agv_state = {
            "map_id":    raw_map,
            "lastNodeId": _cur_tag,
        }
    else:
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

    # Xác định loại AGV để chọn graph/points phù hợp
    from agv_registry import agv_registry as _reg
    _is_line = _reg.is_line(agv_id)

    # Tính đường đi ngắn nhất (Line AGV: direction-aware, tránh occupied nodes)
    if _is_line:
        _prev_tag = str(_line_st.prev_tag) if (_line_st and _line_st.prev_tag) else None

        # Lấy nodes bị Line AGV khác chiếm — CHỈ current position + final destination.
        # KHÔNG block intermediate nodes: xe khác sẽ đi qua trước khi mình đến,
        # block tất cả sẽ ngắt đồ thị và làm không tìm được đường.
        _occupied: set[str] = set()
        try:
            from line_agv_handler import line_agv_handler as _lah_plan
            # 1. Vị trí đang đứng (physically there — must avoid)
            for _oid, _ost in _lah_plan.state_store._states.items():
                if _oid == agv_id or _ost is None or _ost.current_tag is None:
                    continue
                _ct = str(_ost.current_tag).strip()
                if _ct and _ct != start_node and _ct != end_node:
                    _occupied.add(_ct)
            # 2. Điểm đến cuối của route non-transit (same-destination conflict prevention)
            # Xe khác đang đi đến cùng đích → tránh đường để planner tìm đường khác
            for _oid, _route in _lah_plan._routes.items():
                if _oid == agv_id or not _route or not _route.full_path:
                    continue
                if getattr(_route, 'task_type', '') in ('transit',):
                    continue  # transit không chiếm destination
                _dest = str(_route.full_path[-1]).strip()
                if _dest and _dest != start_node and _dest != end_node:
                    _occupied.add(_dest)
        except Exception:
            pass

        # ── Tính đường cơ bản ────────────────────────────────────────────────
        node_path = map_manager.line_directional_path(
            start_node, end_node, _prev_tag, can_reverse=_reg.can_reverse(agv_id))

        # ── Phase 0: Tìm supply node bắt buộc cho delivery này ─────────────────
        # Nếu đích là DROPOFF có team, tìm supply node phục vụ team đó.
        # Quy trình: AGV PHẢI đi qua supply node lấy hàng TRƯỚC rồi mới đến đích.
        # Điều này đúng cho MỌI bản đồ, không phụ thuộc vào node ID cụ thể.
        _req_supply = None
        try:
            _na_p0 = getattr(map_manager, 'node_actions', {}) or {}
            _end_na_p0 = _na_p0.get(str(end_node)) or {}
            _end_team_p0 = _end_na_p0.get('team')
            # Xe rơ-moóc dùng cơ chế trailer_role riêng (drop/pickup tường minh theo
            # tổ), KHÔNG dùng logic "bắt buộc qua supply node" này (vốn dành cho AGV
            # carry lấy hàng tại supply_group trước khi giao). Node đích của trailer
            # có thể trùng số team với 1 supply node carry khác (vd node 16 team=2 và
            # node 64 supply_group=['2','3']) mà không hề liên quan — nếu áp logic này
            # sẽ ép trailer đi vòng qua supply node không cần thiết.
            # AGV kéo ('tow') cũng dùng cơ chế trailer_role riêng như rơ-moóc — loại
            # trừ khỏi logic "bắt buộc qua supply node" y hệt lý do bên dưới.
            _is_trailer_p0 = (agv_registry.get_config(agv_id).get('agv_type') in ('trailer', 'tow'))
            if _end_team_p0 and not _is_trailer_p0:
                _end_team_str_p0 = str(_end_team_p0)
                for _snid_p0, _sncfg_p0 in _na_p0.items():
                    if str(_sncfg_p0.get('arrival_action', '') or '').lower() == 'wait_sys':
                        _sg_p0 = _sncfg_p0.get('supply_group') or []
                        if isinstance(_sg_p0, str):
                            _sg_p0 = [s.strip() for s in _sg_p0.split(',')]
                        if _end_team_str_p0 in [str(g) for g in _sg_p0]:
                            _req_supply = str(_snid_p0)
                            break  # lấy supply node đầu tiên tìm được
        except Exception:
            pass

        # Nếu supply node này ĐÃ lấy hàng trong session (lượt cấp) hiện tại →
        # KHÔNG ép đi qua nữa. Tránh detour `…→supply→…` lặp lại cho mỗi tổ
        # (nguyên nhân AGV "đi về node 64", U-turn lỗi → off_route sang node kế bên).
        if _req_supply and session_id is not None:
            try:
                from task_queue import agv_task_queue as _atq_pp
                if _atq_pp.session_has_pickup(session_id, _req_supply):
                    print(f"[PLAN] {agv_id}: supply {_req_supply} đã lấy hàng trong "
                          f"session {session_id} → KHÔNG ép đi qua nữa (đi thẳng tới đích)")
                    _req_supply = None
            except Exception as _e_pp:
                print(f"[PLAN] {agv_id}: session pickup check lỗi: {_e_pp}")

        # ── ƯU TIÊN THẬT của xe đang lập KH (dùng cho MỌI quyết định né: Phase 1
        # penalty, Phase 2 head-on). KHÔNG để rank mặc định 2 khi xe chưa registered
        # (vừa picking xong) → winner né nhầm → cả 2 cùng né, đâm. Suy theo đích.
        from line_agv_handler import traffic_coordinator as _tc_prio
        _my_prio_plan = _planner_dest_priority(
            getattr(map_manager, 'node_actions', {}) or {}, end_node)
        _my_prio_plan = _tc_prio._registered.get(agv_id, {}).get('priority', _my_prio_plan)

        # ── Phase 1: Tránh occupied nodes (current position + destination cuối) ─
        # Nếu có supply node bắt buộc → KHÔNG thêm vào occupied (dù bị chiếm cũng phải đi qua,
        # traffic logic sẽ xử lý chờ/né khi đến nơi).
        if _req_supply:
            _occupied.discard(_req_supply)

        # ── Phase 1: ROUTING TRÁNH XE KHÁC (traffic-aware, PHẠT MỀM) ──────────
        # Thay vì XOÁ node bị chiếm (cứng, dễ ngắt đồ thị), PHẠT (cộng weight) các
        # cạnh mà xe khác đang dùng (path đăng ký) + nặng hơn quanh vị trí xe đứng.
        # → planner ƯU TIÊN nhánh VÒNG thay thế nếu map có (vd 4-9-15-8-5 thay cho
        # 4-18-5), nhưng VẪN đi được đoạn đường ĐƠN khi không còn lối khác (4-19-64-2).
        # Phạt > chênh lệch quãng đường (cạnh ~80) để né được, nhưng hữu hạn để fallback.
        # NGƯỠNG đổi đường vòng thay vì chờ — áp dụng CHO CẢ 2 tình huống (head-on lẫn
        # cùng chiều/hội tụ): nếu đường vòng không dài hơn đường thẳng quá tỉ lệ này thì
        # đổi sang đi vòng ngay từ lúc lập kế hoạch (dispatch), còn dài hơn nữa (hoặc
        # không có đường vòng) thì vẫn đi đường thẳng và chờ nhau như cũ.
        # YÊU CẦU THỰC TẾ (2026-09-18, chạy 3 xe cùng lúc): dù còn nhiều đường khác đi
        # được, hệ thống vẫn ưu tiên đường NGẮN NHẤT rồi bắt xe đứng chờ nhau, chỉ đổi
        # đường vòng khi vòng đó rẻ (≤80% dài hơn) — không tận dụng hết các nhánh đường
        # sẵn có. Người dùng yêu cầu đảo ngược ưu tiên: "còn đường nào đi được thì ưu
        # tiên đi trước, đường ngắn nhất ưu tiên SAU".
        #
        # ĐÃ THỬ tăng lên 20.0 — GÂY REGRESSION THẬT (cùng ngày 2026-09-18, log kế
        # tiếp): với ngưỡng quá cao, planner chấp nhận cả đường vòng gấp hàng chục lần
        # (vd đi trọn 1 vòng quanh nhà xưởng) chỉ để né 1 xe đang dùng CHUNG 1 đoạn ngắn
        # — hệ quả xấu hơn cả vấn đề gốc:
        #   1) Node chỉ có 2 hàng xóm (vd 98: chỉ nối 6 và 15) — nếu nhánh vòng được
        #      chọn lại đi qua đúng hàng xóm xe VỪA TỚI (chưa qua), xe phải LÙI ra
        #      trước khi vòng, dù đi thẳng qua hàng xóm còn lại (không cần lùi) gần
        #      như luôn ngắn hơn nhiều — ngưỡng cao khiến planner bỏ qua chi phí lùi.
        #   2) Đường vòng dài, quanh co qua nhiều node hơn → tăng mạnh khả năng 2-3 xe
        #      cùng lúc chọn nhánh vòng chồng lấn nhau ở nhiều điểm khác nhau → mỗi xe
        #      "thắng" 1 đoạn head-on cục bộ khác nhau (arbiter tính theo từng cạnh,
        #      không đồng bộ toàn tuyến) → CẢ 2 xe cùng nghĩ mình thắng ở đoạn khác
        #      nhau, cùng đứng chờ nhau → deadlock toàn bộ 3 xe (đúng log thực tế: AGV01
        #      và AGV04 cùng báo "winner, chờ thua né" cho cùng 1 cặp xung đột, đứng im
        #      hoàn toàn nhiều phút, AGV03 xếp hàng phía sau cũng kẹt theo).
        # Hạ về mức vừa phải: đủ cao để né các đoạn tắc nghẽn thật (tăng nhiều so với
        # 0.8 gốc), nhưng không cao tới mức chấp nhận đường vòng gấp hàng chục lần hay
        # đường vòng cần lùi mới đi được.
        _REROUTE_RATIO = 2.0   # chỉnh tại đây nếu cần đổi ngưỡng sau này
        # 2 MỨC phạt theo tình huống (xem chi tiết ở vòng lặp bên dưới) — CẢ 2 đều dùng
        # CHUNG ngưỡng _REROUTE_RATIO ở trên, chỉ khác nhau ở chỗ: head-on còn có Phase 2
        # (bên dưới, xóa hẳn cạnh xe kia) làm lưới an toàn cuối nếu phạt mềm không đủ —
        # cùng chiều/hội tụ thì không cần, chờ nhau là đủ an toàn.
        try:
            import networkx as _nx
            _g_pen = (map_manager.line_graph.copy() if map_manager.line_graph
                      else map_manager.graph.copy())
            _PEN_POS  = 10000.0   # phạt nặng quanh vị trí xe khác đang đứng
            from line_agv_handler import (line_agv_handler as _lah_pen,
                                          traffic_coordinator as _tc_pen)

            # PHÁT HIỆN THỰC TẾ (2026-09-23): nx.shortest_path chạy LẠI trên graph
            # THUẦN KHOẢNG CÁCH (không tính chi phí rẽ như line_directional_path phía
            # trên) có thể HOÀ TUYỆT ĐỐI giữa 2 đường (vd 30→29→31 = 2.5+2.0 và
            # 30→32→31 = 2.0+2.5, cùng 4.5) mà KHÔNG cạnh nào của node_path gốc bị phạt
            # (xe khác không hề đụng đường đó) — tie-break của networkx (phụ thuộc thứ
            # tự trả về của SQL, không ổn định giữa các lần chạy) có thể đổi SANG đường
            # khác node_path gốc dù KHÔNG có lý do né nào, đè lên đường "gốc" (đã ưu
            # tiên đi thẳng/ít rẽ) bằng 1 đường vòng hơn VÔ CĂN CỨ — có thể lại trùng
            # đúng đường xe khác (gây tranh chấp mới thay vì né). Gốc log: AGV03 né
            # siding 30→31, đường thẳng 30→29→31 không đụng AGV04 nhưng bị đổi thành
            # 30→32→31 (đúng đường AGV04 cần dùng) chỉ vì hoà điểm khoảng cách.
            # FIX: so sánh CHI PHÍ THỰC (đã cộng phạt) của node_path gốc và _pen_path
            # ngay TRÊN _g_pen — chỉ đổi khi _pen_path THỰC SỰ rẻ hơn (có lý do né
            # thật, vd cạnh trên node_path gốc bị phạt), không đổi khi chỉ hoà điểm
            # (dùng bump ở nơi khác trong graph không liên quan node_path gốc).
            def _bump(_u, _v, _amt):
                if _g_pen.has_edge(_u, _v):
                    _g_pen[_u][_v]['weight'] = _g_pen[_u][_v].get('weight', 1.0) + _amt

            def _path_cost(_p):
                return sum(_g_pen[_p[_i]][_p[_i + 1]].get('weight', 1.0)
                           for _i in range(len(_p) - 1)) if _p and len(_p) > 1 else 0.0

            # ƯU TIÊN của CHÍNH xe đang lập kế hoạch: KHÔNG để mặc định 2 khi chưa
            # registered (xe vừa picking xong lập route giao hàng CHƯA đăng ký lại →
            # bị coi yếu hơn xe kia → NÉ NHẦM dù mình là winner → CẢ HAI cùng né, đâm
            # nhau). Suy theo loại node đích: CHARGER → return_charge(1), còn lại
            # delivery(3). Nếu đã registered thì dùng priority thật.
            def _should_avoid_pen(_other_id: str) -> bool:
                """Như should_avoid_path_of nhưng dùng _my_prio_plan cho xe đang lập KH
                (tránh lỗi rank mặc định 2 khi chưa registered)."""
                _op_prio = _tc_pen._registered.get(_other_id, {}).get('priority', 2)
                return _planner_should_avoid(_my_prio_plan, agv_id, _op_prio, _other_id)

            # 1. Phạt các cạnh trên path ĐĂNG KÝ (tương lai) của xe khác có route.
            #    Path[current_idx:] bắt đầu từ vị trí xe → tự bao hướng nó đi; KHÔNG
            #    phạt riêng vị trí (over-phạt cạnh nó KHÔNG đi → đẩy mình vào đúng
            #    đường nó → đâm).
            _routed = set()
            # Tập cạnh CÓ HƯỚNG trên đường TỰ NHIÊN của ta (node_path lúc này CHƯA bị
            # penalty sửa) → để phân biệt HEAD-ON (ngược chiều) vs FOLLOWING (cùng chiều).
            _my_dir_edges = {(str(node_path[_i]), str(node_path[_i + 1]))
                             for _i in range(len(node_path) - 1)} if node_path else set()
            # Quãng đường THẬT của đường ngắn nhất (chưa phạt) — làm mốc cho ngưỡng
            # "đường vòng chỉ dài hơn 50% thì vẫn nên đổi, dài hơn nữa mới chờ" dùng ở
            # nhánh CÙNG CHIỀU/HỘI TỤ bên dưới. Dựa trên 'distance' thật (xem tính năng
            # 'Khoảng cách thật' trong Map Editor) chứ không phải toạ độ vẽ.
            _direct_distance = sum(
                _g_pen[node_path[_i]][node_path[_i + 1]].get('weight', 1.0)
                for _i in range(len(node_path) - 1)
            ) if node_path and len(node_path) > 1 else 0.0
            # Duyệt CẢ xe đăng ký LẪN xe đang chờ có intent_route (deregistered nhưng
            # vẫn có ý định đi tới đích — vd xe chờ ở 18 sẽ đi 18→5→17) → né được.
            for _oid in (set(_tc_pen._registered) | set(_tc_pen._intent_route)):
                if _oid == agv_id:
                    continue
                _routed.add(_oid)
                # Ưu tiên TUYẾN ĐẦY ĐỦ (intent) — biết cả phần xe sẽ đi sau khi chia đoạn
                # HOẶC đang đứng chờ (vd 18→5→17 của xe chờ tới 17).
                _intent = _tc_pen._intent_route.get(_oid)
                if _intent and len(_intent) >= 2:
                    _op = _intent
                    # PHÁT HIỆN THỰC TẾ (2026-09-21): trước đây LUÔN _oc=0 (coi cả intent
                    # là "còn nguyên phía trước"), kể cả khi xe đó ĐÃ ĐI HẾT intent này và
                    # đang đứng yên chờ xác nhận thủ công tại ĐÍCH (vd tới điểm lấy hàng,
                    # chờ bấm xác nhận trên Web UI) — intent_route chỉ bị xoá hẳn lúc
                    # deregister() (khi xác nhận xong), nên trong lúc chờ này xe khác vẫn
                    # thấy "nó sắp đi qua các cạnh đó" dù thực tế đã đi qua xong từ lâu và
                    # đang đứng im ở cuối đường → gây phạt HEAD-ON/né nhầm vào các cạnh đã
                    # xong, bắt xe mình đi vòng vô ích để né 1 xe không hề còn di chuyển
                    # trên các cạnh đó nữa (đúng log: AGV01 phải vòng qua 26→27 để né cạnh
                    # 24↔28 dù AGV03 đã early đứng yên hẳn ở 103 chờ xác nhận). Suy ra vị
                    # trí THẬT trong intent bằng current_tag của xe đó — chỉ những cạnh
                    # TỪ VỊ TRÍ HIỆN TẠI trở đi mới còn là "tương lai" cần né.
                    _oc = 0
                    try:
                        _ost_intent = _lah_pen.state_store.get(_oid)
                        if _ost_intent and _ost_intent.current_tag is not None:
                            _oc = _intent.index(str(_ost_intent.current_tag))
                    except ValueError:
                        pass
                else:
                    _oreg = _tc_pen._registered.get(_oid, {})
                    _op = _oreg.get('path', []); _oc = _oreg.get('current_idx', 0)
                # NGÂN SÁCH ĐI VÒNG (m) cho xe chắn này: chỉ chấp nhận đường vòng dôi hơn đường thẳng nếu thời gian
                # dôi < thời gian ước tính chờ xe đó thoát (xe đang chạy & sắp rời → chờ ngắn → ngân sách nhỏ → giữ
                # đường thẳng; xe đỗ/đứng chờ → ngân sách lớn). Không bao giờ vượt ngưỡng tỉ lệ cũ.
                _budget_m = _REROUTE_RATIO * _direct_distance
                try:
                    from line_agv_handler import (estimate_clear_wait_sec as _ecw,
                                                  detour_allowance_sec as _das,
                                                  AGV_NOMINAL_SPEED_MPS as _vnom)
                    _budget_m = min(_budget_m, _das(_ecw(_oid, node_path)) * _vnom)
                except Exception:
                    pass
                # HEAD-ON: xe kia đi NGƯỢC chiều ta trên CÙNG cạnh vật lý. TRƯỚC ĐÂY phạt
                # CỨNG (luôn né bất kể xa bao nhiêu) — giờ đổi sang phạt MỀM tỉ lệ theo
                # _REROUTE_RATIO GIỐNG HỆT nhánh cùng chiều bên dưới: chỉ đổi đường vòng
                # nếu không dài hơn quá ngưỡng, còn không thì vẫn đi đường thẳng (Phase 2
                # bên dưới sẽ lo phần an toàn — dừng chờ tại điểm an toàn trước xung đột).
                # Head-on vẫn phạt theo TOÀN BỘ path xe kia (không chỉ cạnh chung) vì đối
                # đầu trực diện cần né sớm, không phải chỉ né đúng lúc chạm mặt.
                if _path_is_headon_against(_my_dir_edges, _op, _oc):
                    # BẤT ĐỐI XỨNG (CHỈ áp dụng cho head-on): chỉ né đường xe MẠNH hơn —
                    # chống dao động (cả 2 cùng né nhau sẽ cùng nhảy 1 nhánh → vẫn đâm ở
                    # nhánh mới). Xe mạnh giữ đường ngắn cố định, xe yếu né. Nhánh CÙNG
                    # CHIỀU/HỘI TỤ bên dưới KHÔNG cần bất đối xứng này — không phải nguy
                    # cơ va chạm trực diện, cả 2 xe đều được tự xét đổi đường rẻ hơn.
                    if not _should_avoid_pen(_oid):
                        continue
                    if _direct_distance <= 0:
                        continue
                    if _head_on_should_wait(agv_id, _oid, node_path):
                        continue   # chờ xe kia đi qua nhanh, không đi vòng (không xe thứ 3 nào cần đoạn đó)
                    _ho_edges = [(str(_op[_j]), str(_op[_j + 1]))
                                 for _j in range(_oc, len(_op) - 1)]
                    if not _ho_edges:
                        continue
                    _pen_ho_each = _budget_m / len(_ho_edges)
                    for _a, _b in _ho_edges:
                        _bump(_a, _b, _pen_ho_each); _bump(_b, _a, _pen_ho_each)
                    continue
                # CÙNG CHIỀU/HỘI TỤ (không đối đầu, chỉ tranh chung 1-2 cạnh trên đường):
                # KHÔNG bắt buộc né như head-on, nhưng NẾU có đường vòng chỉ dài hơn
                # đường thẳng không quá _REROUTE_RATIO thì vẫn nên đi vòng cho nhanh thay
                # vì đứng chờ — theo đúng yêu cầu thực tế (2 xe cùng cần qua 1 hành lang
                # chung nhưng đích khác nhau, có đường vòng chỉ dài hơn ~16-20% mà hệ
                # thống vẫn bắt chờ).
                # NGOẠI LỆ giữ nguyên như trước: xe kia đi tới ĐÚNG CÙNG ĐÍCH với mình
                # (leader/follower thật) → KHÔNG né, vì rồi cũng phải tới đúng chỗ nó,
                # đi vòng chỉ lãng phí (đúng lý do fix gốc: "xe dẫn đi vòng" vô ích).
                if not _op or str(_op[-1]) == str(end_node) or _direct_distance <= 0:
                    continue
                _shared_edges = ({(str(_op[_j]), str(_op[_j + 1]))
                                  for _j in range(_oc, len(_op) - 1)} & _my_dir_edges)
                if _shared_edges:
                    # Phạt MỀM, tỉ lệ theo đường thẳng của MÌNH: tổng phạt = _REROUTE_RATIO
                    # quãng đường thẳng, chia đều cho các cạnh tranh chấp — vừa đủ để planner
                    # chọn đường vòng khi đường vòng đó rẻ hơn (đường thẳng + phạt), tức
                    # đường vòng dài hơn KHÔNG QUÁ ngưỡng; nếu đường vòng dài hơn nữa (hoặc
                    # không có) thì đường thẳng (dù bị phạt) vẫn rẻ hơn → giữ nguyên, xe
                    # chờ nhau như cũ (không còn đường nào tốt hơn để đổi).
                    _pen_follow_each = _budget_m / len(_shared_edges)
                    for _a, _b in _shared_edges:
                        _bump(_a, _b, _pen_follow_each)
                # 1b. PHẠT CẢ NÚT GIAO chung (không chỉ cạnh chung): phát hiện thực tế
                # 2026-09-18 — 2 xe cùng cần đi QUA 1 node nhiều-hàng-xóm (vd node 28 nối
                # 24/27/30/104) nhưng theo 2 CẶP CẠNH khác nhau (xe kia vào từ 24 ra 104,
                # mình định vào từ 30 ra 27) → không cạnh nào trùng nên bước trên
                # (_shared_edges) không thấy được, KHÔNG phạt gì → planner vẫn chọn đường
                # xuyên qua ĐÚNG node đó → runtime vẫn tranh chấp y hệt vì reservation giữ
                # theo TỪNG NODE (không phải riêng từng cạnh) — đúng log: route vòng đã né
                # được cạnh 28→24 (đường AGV04 dùng) nhưng vẫn đi 30→28→27, tức là VẪN xuyên
                # 28 → vẫn dính "28 bị AGV04 khoá". Phạt thêm NHẸ (bằng đúng mức phạt cạnh ở
                # trên) cho MỌI cạnh chạm vào các node NẰM CHUNG giữa đường mình và đường
                # tương lai xe kia, để planner cân nhắc né hẳn qua ngả khác (vd 30→29→27,
                # không đụng 28) khi có, thay vì chỉ né đúng 2 cạnh xe kia đang dùng.
                # LƯU Ý: đặt SAU (không dùng "continue" của bước _shared_edges ở trên) và
                # NGUYÊN VẸN bên trong vòng for _oid — nếu không sẽ không chạy đúng lúc
                # _shared_edges rỗng (chính là trường hợp cần xử lý) hoặc chỉ chạy 1 lần
                # với _op/_oc của lần lặp cuối thay vì của từng xe khác.
                _other_future_nodes = {str(n) for n in _op[_oc:]} if _op else set()
                _my_dir_nodes = ({str(node_path[_i]) for _i in range(len(node_path))}
                                  if node_path else set())
                _shared_nodes = (_other_future_nodes & _my_dir_nodes) - {start_node, end_node}
                if _shared_nodes:
                    _pen_node_each = _budget_m / len(_shared_nodes)
                    for _sn in _shared_nodes:
                        if _sn not in _g_pen:
                            continue
                        for _nb in list(_g_pen.neighbors(_sn)):
                            _bump(_sn, _nb, _pen_node_each); _bump(_nb, _sn, _pen_node_each)
            # 2. Né VỊ TRÍ xe đang DỪNG — BẤT ĐỐI XỨNG: chỉ né vị trí xe MẠNH hơn (mình
            #    yếu → tránh), HOẶC xe đậu yên KHÔNG route (vật cản tĩnh). KHÔNG né vị trí
            #    xe YẾU hơn có route: mình mạnh → đi đường ngắn, dừng trước CHỜ nó dời
            #    (reserve không giành node nó đang đứng). Né vị trí xe yếu = nhảy nhánh
            #    khác → trùng nhánh nó → dao động/kẹt.
            for _oid2, _ost2 in _lah_pen.state_store._states.items():
                if (_oid2 == agv_id or _ost2 is None or _ost2.current_tag is None
                        or getattr(_ost2, 'driving', False)):
                    continue
                _reg2 = _oid2 in _tc_pen._registered
                if _reg2 and not _should_avoid_pen(_oid2):
                    continue   # xe YẾU hơn có route → KHÔNG né vị trí (chờ nó dời)
                _cn = str(_ost2.current_tag).strip()
                if _cn in (start_node, end_node) or _cn not in _g_pen:
                    continue
                for _nb in list(_g_pen.neighbors(_cn)):
                    _bump(_cn, _nb, _PEN_POS); _bump(_nb, _cn, _PEN_POS)

            _pen_path = _nx.shortest_path(_g_pen, source=start_node,
                                          target=end_node, weight='weight')
            if (_pen_path and list(_pen_path) != list(node_path)
                    and _path_cost(_pen_path) < _path_cost(node_path) - 1e-6):
                node_path = _pen_path
                print(f"[PLAN] {agv_id}: traffic-aware route (né đường xe khác qua nhánh "
                      f"vòng nếu có) → {node_path}")
        except Exception as _e_pen:
            print(f"[PLAN] {agv_id}: traffic-aware routing lỗi ({_e_pen}) — dùng path gốc")

        # ── Phase 1b: Buộc đi qua supply node nếu chưa có trên path ─────────
        # Trường hợp supply node không nằm trên đường ngắn nhất start→dest,
        # xây dựng 2-leg route: start → supply → dest để đảm bảo quy trình lấy hàng.
        # NGOẠI LỆ: không áp dụng nếu start_node nằm DOWNSTREAM của supply node
        # (tức là AGV đã qua supply đi tiếp → không cần quay lại lấy hàng lần nữa).
        if _req_supply and _req_supply not in node_path and _req_supply != start_node:
            try:
                import networkx as _nx
                _g_via = map_manager.line_graph.copy() if map_manager.line_graph else map_manager.graph.copy()
                _occ_no_supply = {n for n in _occupied if n != _req_supply}
                _g_via.remove_nodes_from(n for n in _occ_no_supply if n in _g_via)
                _leg1 = _nx.shortest_path(_g_via, source=start_node, target=_req_supply, weight='weight')
                _leg2 = _nx.shortest_path(_g_via, source=_req_supply, target=end_node, weight='weight')
                # Nếu start_node xuất hiện trong leg2 (downstream của supply) →
                # AGV đã qua supply rồi, đang ở vị trí tiếp theo → KHÔNG quay lại.
                if str(start_node) in [str(n) for n in _leg2[1:]]:
                    print(f"[PLAN] {agv_id}: {start_node} downstream của supply {_req_supply} "
                          f"(đã lấy hàng rồi) → bỏ qua Phase 1b")
                else:
                    _combined = list(_leg1) + list(_leg2[1:])
                    # Duplicate-node check ĐÃ BỊ XÓA: U-shape route (ví dụ 13→1→2→64→2→1→12→69)
                    # hoàn toàn hợp lệ khi supply ở "phía đối diện" với đích.
                    # True circular loop đã được bắt bởi check trên (start_node in leg2[1:]).
                    node_path = _combined
                    print(f"[PLAN] {agv_id}: route qua supply {_req_supply} (team {_end_team_p0}) → {node_path}")
            except Exception as _e:
                print(f"[PLAN] {agv_id}: không thể route qua supply {_req_supply}: {_e}")

        # ── Phase 2: Phát hiện head-on conflict, thử đường thay thế ─────────
        try:
            from line_agv_handler import traffic_coordinator as _tc
            _head_on = _tc.find_head_on(agv_id, node_path, near_only=False)
            # find_head_on trả về (idx, agv_id) cho head-on, hoặc negative int cho following.
            # Negative int → following conflict, không cần reroute tại dispatch.
            # BẤT ĐỐI XỨNG: chỉ xe YẾU hơn mới né (reroute hard); xe MẠNH giữ đường ngắn.
            if (isinstance(_head_on, tuple)
                    and not _tc.should_avoid_path_of(agv_id, _head_on[1],
                                                     my_priority=_my_prio_plan)):
                print(f"[PLAN] {agv_id}: HEAD-ON với {_head_on[1]} — TÔI ưu tiên (mạnh hơn) "
                      f"→ giữ đường ngắn, để {_head_on[1]} né")
                _head_on = None
            if isinstance(_head_on, tuple):
                _conflict_idx, _other_agv = _head_on
                print(f"[PLAN] {agv_id}: HEAD-ON với {_other_agv} tại edge "
                      f"{node_path[_conflict_idx]}→{node_path[_conflict_idx+1]} "
                      f"(idx={_conflict_idx}) — tìm đường thay thế")
                if _head_on_should_wait(agv_id, _other_agv, node_path):
                    print(f"[PLAN] {agv_id}: chờ {_other_agv} đi qua (không xe nào khác cần đoạn này) "
                          f"— không đi đường vòng")
                    raise _HeadOnWait()
                # Xóa các edges của xe kia ra khỏi graph để buộc dùng đường khác
                import networkx as _nx
                _g2 = map_manager.line_graph.copy() if map_manager.line_graph else map_manager.graph.copy()
                _other_reg = _tc._registered.get(_other_agv, {})
                _other_path = _other_reg.get('path', [])
                _other_cur  = _other_reg.get('current_idx', 0)
                # Xóa edges tương lai của xe kia
                for _j in range(_other_cur, len(_other_path) - 1):
                    _fn2, _tn2 = _other_path[_j], _other_path[_j + 1]
                    if _g2.has_edge(_fn2, _tn2):
                        _g2.remove_edge(_fn2, _tn2)
                    if _g2.has_edge(_tn2, _fn2):
                        _g2.remove_edge(_tn2, _fn2)
                try:
                    _alt2 = _nx.shortest_path(_g2, source=start_node, target=end_node, weight="weight")
                    # Kiểm tra: alternate path có còn đi qua supply node bắt buộc không?
                    # Nếu alternate BỎ QUA supply node → không dùng alternate (dù tránh HEAD-ON),
                    # vì quy trình BẮT BUỘC phải lấy hàng tại supply node trước.
                    # Traffic system sẽ xử lý HEAD-ON bằng cách dừng chờ tại conflict point.
                    if _req_supply and _req_supply not in _alt2 and _req_supply in node_path:
                        print(f"[PLAN] {agv_id}: alternate HEAD-ON bỏ qua supply {_req_supply} "
                              f"→ giữ path gốc (bắt buộc qua supply)")
                    else:
                        # NGƯỠNG _REROUTE_RATIO (xem Phase 1): chỉ nhận đường thay thế nếu
                        # KHÔNG dài hơn đường gốc quá tỉ lệ này — Phase 1 (phạt mềm) thường
                        # đã tự chọn đúng đường trong ngưỡng rồi nên node_path ở đây thường
                        # ĐÃ là lựa chọn hợp lệ; Phase 2 (xoá hẳn cạnh) là lưới an toàn cuối
                        # khi Phase 1 chưa đủ mạnh để né — vẫn cần so khoảng cách để không
                        # bắt xe đi vòng quá xa so với chờ tại chỗ.
                        _g_dist = map_manager.line_graph if map_manager.line_graph else map_manager.graph
                        def _path_dist_p2(_p):
                            try:
                                return sum(_g_dist[str(_p[_i])][str(_p[_i + 1])].get('weight', 1.0)
                                           for _i in range(len(_p) - 1))
                            except Exception:
                                return float('inf')
                        _cur_dist2 = _path_dist_p2(node_path)
                        _alt_dist2 = _path_dist_p2(_alt2)
                        if _cur_dist2 > 0 and _alt_dist2 > _cur_dist2 * (1 + _REROUTE_RATIO):
                            print(f"[PLAN] {agv_id}: đường thay thế HEAD-ON dài hơn quá "
                                  f"{_REROUTE_RATIO*100:.0f}% ({_alt_dist2:.1f}m vs {_cur_dist2:.1f}m) "
                                  f"— giữ đường thẳng, chờ tại điểm an toàn thay vì đi vòng quá xa")
                        else:
                            node_path = list(_alt2)
                            print(f"[PLAN] {agv_id}: đường thay thế tránh HEAD-ON → {node_path}")
                except Exception:
                    # Không có đường thay thế: giữ path gốc, _dispatch_go_to sẽ
                    # truncate tại điểm chờ an toàn và queue phần còn lại
                    print(f"[PLAN] {agv_id}: không có đường thay thế HEAD-ON "
                          f"— sẽ chờ tại điểm an toàn trước conflict")
        except _HeadOnWait:
            pass   # đã chọn chờ xe kia đi qua: giữ path gốc, điểm dừng an toàn do _dispatch_go_to lo
        except Exception as _te:
            print(f"[PLAN] head-on check error: {_te}")
    else:
        node_path = map_manager.shortest_path(start_node, end_node)
    if not node_path:
        raise ValueError(f"Không tìm được đường đi từ {start_node} -> {end_node}")

    print(f"[PLAN] shortest path ({'LINE' if _is_line else 'VDA5050'}): {' -> '.join(map(str, node_path))}")

    # Line AGV dùng line_points; fallback points nếu chưa cấu hình agvCompat
    _points_lookup = (map_manager.line_points or map_manager.points) if _is_line else map_manager.points

    # Convert sang route_nodes / route_edges
    route_nodes = []
    route_edges = []

    for node_id in node_path:
        point = _points_lookup.get(str(node_id)) or map_manager.points.get(str(node_id))
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

def plan_path_for_order(agv_id: str, start_node_id: str | None, end_node_id: str,
                        session_id: str | None = None):
    """
    Gọi async planner từ thread MQTT.

    session_id: lượt cấp hàng hiện tại — planner dùng để bỏ ép detour qua supply
    node đã lấy hàng trong lượt (đi thẳng tới đích thay vì quay lại điểm lấy hàng).
    """
    app = get_app()
    loop = getattr(app.state, "loop", None)
    if not loop or not loop.is_running():
        raise RuntimeError("FastAPI event loop chưa sẵn sàng")

    # Lập đường chạy trên event loop và nạp lại map từ DB mỗi lần → nhiều xe cùng lập có thể >10s.
    # Quá hạn mà KHÔNG huỷ thì coroutine vẫn chạy tiếp vô ích, còn lệnh của xe bị mất (xe đứng im vĩnh viễn).
    # Nên chờ lâu hơn, huỷ coroutine khi quá hạn và thử lại vài lần.
    last_err: Exception | None = None
    for _attempt in range(3):
        fut = asyncio.run_coroutine_threadsafe(
            plan_path_async(agv_id, start_node_id, end_node_id, session_id),
            loop
        )
        try:
            return fut.result(timeout=PLAN_PATH_TIMEOUT_SEC)
        except concurrent.futures.TimeoutError as e:
            fut.cancel()
            last_err = e
            print(f"[PLAN] {agv_id}: lập đường quá {PLAN_PATH_TIMEOUT_SEC:.0f}s (lần {_attempt + 1}/3) → thử lại")
    raise last_err if last_err else RuntimeError("plan_path_for_order: không lập được đường")


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
        "version": "3.0.0",
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
    """Gửi order — tự phân nhánh Line AGV / VDA5050 theo registry."""
    send_order(agv_id, order)


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
def _should_emit(agv_id: str, key: str, now_ts: float, cooldown: int = ALERT_COOLDOWN_SEC) -> bool:
    last = _last_alert_ts.get((agv_id, key), 0)
    if now_ts - last < cooldown:
        return False
    _last_alert_ts[(agv_id, key)] = now_ts
    return True


def _emit_alert(agv_id: str, title: str, message: str, level: str = "warning"):
    app = get_app()
    ws_func = app.state.send_websocket_update
    if not ws_func:
        return

    payload = {
        "type": "assistant_alert",
        "agv_id": agv_id,
        "level": level,
        "title": title,
        "message": message,
        "timestamp": datetime.datetime.now().isoformat()
    }

    async def send_ws():
        await ws_func(payload)

    run_async_in_thread(send_ws())


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


# ==========================
# AGV INFO SYNC FROM TOPIC
# ==========================
_synced_agv_factories: dict[str, str] = {}         # {agv_id: factory đã sync}
_sync_candidate:       dict[str, tuple] = {}       # {agv_id: (factory, first_seen_ts)}
_SYNC_STABLE_SEC = 8.0   # factory phải ổn định X giây mới cập nhật DB

def _sync_agv_from_topic(agv_id: str, factory_from_topic: str) -> None:
    """
    Khi Line AGV gửi state, đọc factory từ MQTT topic (uagv/v2/{factory}/{agv_id}/state)
    và tự động cập nhật vào agv_devices nếu khác DB.
    Debounce: factory phải ổn định _SYNC_STABLE_SEC giây liên tiếp mới thật sự update.
    Chạy async để không block MQTT thread.
    """
    if not factory_from_topic or factory_from_topic in ("manager",):
        return
    # Skip nếu đã sync cùng factory này rồi
    if _synced_agv_factories.get(agv_id) == factory_from_topic:
        return

    # Debounce: ghi nhận candidate, chỉ proceed nếu đã ổn định đủ thời gian
    now = time.monotonic()
    cand = _sync_candidate.get(agv_id)
    if cand and cand[0] == factory_from_topic:
        if now - cand[1] < _SYNC_STABLE_SEC:
            return   # chưa đủ stable, đợi thêm
        # Stable đủ → proceed
    else:
        # Factory khác hoặc chưa có candidate → reset timer
        _sync_candidate[agv_id] = (factory_from_topic, now)
        return   # chưa đủ stable

    def _do_sync():
        try:
            from agv_registry import agv_registry as _reg
            current_factory = _reg.get_factory(agv_id, default=None) or ""
            if factory_from_topic == current_factory:
                _synced_agv_factories[agv_id] = factory_from_topic
                return

            import psycopg2
            _DB = os.getenv("DATABASE_URL", "postgresql://postgres:ducmanh1801@localhost:5432/TOT_AGV")
            _conn = psycopg2.connect(_DB)
            _conn.autocommit = True
            with _conn.cursor() as _cur:
                # Chỉ cập nhật factory nếu AGV đã có trong DB
                # KHÔNG tự tạo mới — tránh restore lại AGV đã bị xóa
                _cur.execute(
                    "UPDATE agv_devices SET factory = %s WHERE name = %s",
                    (factory_from_topic, agv_id),
                )
                if _cur.rowcount == 0:
                    # AGV không có trong DB (đã bị xóa hoặc chưa đăng ký) → bỏ qua
                    _synced_agv_factories[agv_id] = factory_from_topic  # cache để tránh spam log
                    return
            _conn.close()
            # Reload registry để nhận biết factory mới
            _reg.load_from_db()
            _synced_agv_factories[agv_id] = factory_from_topic
            print(f"[AGV_SYNC] {agv_id}: factory {current_factory!r} → {factory_from_topic!r}")
        except Exception as _e:
            print(f"[AGV_SYNC] {agv_id}: sync error: {_e}")

    # Chạy trong thread riêng để không block MQTT
    import threading as _th
    _th.Thread(target=_do_sync, daemon=True).start()


def _sync_agv_network_info(agv_id: str, ip: str, subnet: str, gateway: str, dns: str) -> None:
    """
    Cập nhật thông tin mạng AGV vào agv_devices từ topic uagv/v2/{F}/{ID}/info.
    Chạy trong thread riêng để không block MQTT.
    """
    def _do():
        try:
            import psycopg2
            _DB = os.getenv("DATABASE_URL", "postgresql://postgres:ducmanh1801@localhost:5432/TOT_AGV")
            _conn = psycopg2.connect(_DB)
            _conn.autocommit = True
            with _conn.cursor() as _cur:
                # Cập nhật từng field nếu có giá trị
                _fields, _vals = [], []
                if ip:
                    _fields.append("ip = %s::inet")
                    _vals.append(ip)
                if subnet:
                    _fields.append("subnet = %s")
                    _vals.append(subnet)
                if gateway:
                    _fields.append("gateway = %s")
                    _vals.append(gateway)
                if dns:
                    _fields.append("dns = %s")
                    _vals.append(dns)
                if _fields:
                    _vals.append(agv_id)
                    _cur.execute(
                        f"UPDATE agv_devices SET {', '.join(_fields)} WHERE name = %s",
                        _vals,
                    )
            _conn.close()
            print(f"[AGV_INFO] {agv_id}: ip={ip} subnet={subnet} gateway={gateway} dns={dns}")
        except Exception as _e:
            print(f"[AGV_INFO] {agv_id}: sync error: {_e}")

    import threading as _th
    _th.Thread(target=_do, daemon=True).start()


# ==========================
# FMS PRESENCE HELPERS (Phần 1 spec)
# ==========================

# Topic được latch lần đầu khi start_mqtt() gọi — bảo đảm LWT và ONLINE
# dùng đúng cùng một topic, không bị lệch nếu _unified_config thay đổi sau đó.
_fms_manager_topic_cache: str | None = None

# headerId tăng đơn điệu theo yêu cầu VDA5050 (mỗi lần publish +1).
_manager_conn_hid: int = 0


_FACTORY_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


def _configured_factory() -> str:
    """Môi trường nhà máy (factory) đặt trên giao diện: mqtt_mode.json → "factory". MQTT_MODE_OVERRIDE (mô phỏng) bỏ qua."""
    if os.getenv("MQTT_MODE_OVERRIDE", "").strip():
        return ""
    f = str(_read_mode_file().get("factory") or "").strip()
    return f if _FACTORY_RE.match(f) else ""


def get_factory_config() -> dict:
    """Factory đang hiệu lực + nguồn + topic presence + factory từng xe (DB) để giao diện cảnh báo lệch."""
    topic = _fms_manager_topic()
    eff = topic.split("/")[2] if topic.count("/") >= 3 else ""
    cfg = _configured_factory()
    source = "ui" if cfg else ("env" if os.getenv("LINE_AGV_FACTORY", "").strip() else "agv")
    agvs = {}
    try:
        from agv_registry import agv_registry as _reg
        for aid in _reg.all_ids():
            agvs[aid] = _reg.get_factory(aid, default="") or ""
    except Exception:
        pass
    return {"configured": cfg, "effective": eff, "source": source, "topic": topic, "agvs": agvs}


def set_factory_config(factory: str, apply_agvs: bool = True) -> dict:
    """Lưu factory, (tuỳ chọn) gán cho mọi xe trong DB, xoá retained presence cũ và kết nối lại để LWT/presence theo topic mới."""
    if os.getenv("MQTT_MODE_OVERRIDE", "").strip():
        return {"ok": False, "error": "Server mô phỏng không được đổi factory (file dùng chung với server thật)"}
    factory = (factory or "").strip()
    if not _FACTORY_RE.match(factory):
        return {"ok": False, "error": "Factory chỉ gồm chữ, số, '-' hoặc '_' (tối đa 32 ký tự), không có khoảng trắng hay '/'"}
    old_topic = _fms_manager_topic()
    d = _read_mode_file()
    d["factory"] = factory
    _write_mode_file(d)
    updated = 0
    if apply_agvs:
        try:
            import psycopg2
            _DB = os.getenv("DATABASE_URL", "postgresql://postgres:ducmanh1801@localhost:5432/TOT_AGV")
            _conn = psycopg2.connect(_DB)
            _conn.autocommit = True
            with _conn.cursor() as _cur:
                _cur.execute("UPDATE agv_devices SET factory = %s WHERE COALESCE(factory,'') <> %s", (factory, factory))
                updated = _cur.rowcount
            _conn.close()
            from agv_registry import agv_registry as _reg
            _reg.load_from_db()
            _synced_agv_factories.clear()
        except Exception as e:
            print(f"[FACTORY] không gán được factory cho xe trong DB: {e}")
    print(f"[FACTORY] đặt factory = {factory!r} (gán cho {updated} xe trong DB)")
    res = switch_mqtt_mode(MQTT_MODE)            # tạo client mới → will_set + presence ONLINE theo topic mới
    new_topic = _fms_manager_topic()
    if res.get("ok") and old_topic != new_topic:
        try:
            client.publish(old_topic, b"", qos=1, retain=True)       # xoá retained presence của factory cũ
            print(f"[FACTORY] đã xoá retained {old_topic}")
        except Exception as e:
            print(f"[FACTORY] xoá retained cũ lỗi: {e}")
    return {"ok": bool(res.get("ok")), "factory": factory, "topic": new_topic, "agvs_updated": updated, "old_topic": old_topic}


def _fms_manager_topic() -> str:
    """Topic hiện diện FMS: uagv/v2/{FACTORY}/manager/connection.

    Ưu tiên LINE_AGV_FACTORY (env var) → factory từ agv_registry → fallback "VietDuc".
    KHÔNG dùng _unified_config["factory"] vì đó là interface_name ("uagv"), không phải
    tên nhà máy.  Cache sau lần tính đầu để will_set() và on_connect dùng cùng topic.
    """
    global _fms_manager_topic_cache
    if _fms_manager_topic_cache:
        return _fms_manager_topic_cache

    try:
        from unified_mqtt import LINE_AGV_FACTORY, LINE_AGV_VERSION
        version = LINE_AGV_VERSION
    except Exception:
        LINE_AGV_FACTORY = ""
        version = os.getenv("LINE_AGV_MQTT_VERSION", "v2")

    factory = _configured_factory() or LINE_AGV_FACTORY   # giao diện (mqtt_mode.json) > env var LINE_AGV_FACTORY

    if not factory:
        # Lấy factory từ agv_registry (AGV đầu tiên có factory đã đăng ký)
        try:
            from agv_registry import agv_registry as _reg
            for _aid in _reg.all_ids():
                _f = _reg.get_factory(_aid)
                if _f:
                    factory = _f
                    break
        except Exception:
            pass

    if not factory:
        factory = "VietDuc"   # fallback cuối cùng theo spec firmware

    _fms_manager_topic_cache = f"{UAGV_INTERFACE_NAME}/{version}/{factory}/manager/connection"
    print(f"[FMS] Manager topic = {_fms_manager_topic_cache}")
    return _fms_manager_topic_cache


def reset_fms_topic_cache() -> None:
    """Xóa cache topic — gọi trước start_mqtt() khi factory/version thay đổi."""
    global _fms_manager_topic_cache
    _fms_manager_topic_cache = None


def _fms_presence_payload(conn_state: str) -> str:
    """Tạo payload connection message theo chuẩn VDA5050.

    manufacturer lấy từ phần {FACTORY} trong topic để nhất quán.
    headerId=0 cho LWT (broker-generated), tăng từ 1 cho ONLINE/CONNECTIONBROKEN live.
    """
    global _manager_conn_hid
    _manager_conn_hid += 1

    # Trích factory từ topic cache đã tính (uagv/v2/{factory}/manager/connection)
    _topic_parts = _fms_manager_topic().split("/")
    _mfr = _topic_parts[2] if len(_topic_parts) >= 5 else UAGV_MANUFACTURER

    return json.dumps({
        "headerId":        _manager_conn_hid,
        "timestamp":       datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "version":         "2.0.0",
        "manufacturer":    _mfr,
        "serialNumber":    "manager",
        "connectionState": conn_state,
    })


# ==========================
# MQTT Event Handlers
# ==========================
def on_connect(client, userdata, flags, rc):
    print(f"[MQTT] Connected with result code {rc}")
    _elevator_broker_link(rc == 0)
    client.subscribe("vda5050/agv/+/state", qos=QOS)
    print("[MQTT] Subscribed: vda5050/agv/+/state")
    client.subscribe(f"{UAGV_INTERFACE_NAME}/{UAGV_MAJOR_VERSION}/+/+/state", qos=QOS)
    print(f"[MQTT] Subscribed: {UAGV_INTERFACE_NAME}/{UAGV_MAJOR_VERSION}/+/+/state")

    # Connection / LWT topics (VDA5050)
    client.subscribe("vda5050/agv/+/connection", qos=QOS)
    print("[MQTT] Subscribed: vda5050/agv/+/connection")
    client.subscribe(f"{UAGV_INTERFACE_NAME}/{UAGV_MAJOR_VERSION}/+/+/connection", qos=QOS)
    print(f"[MQTT] Subscribed: {UAGV_INTERFACE_NAME}/{UAGV_MAJOR_VERSION}/+/+/connection")

    client.subscribe("vda5050/agv/+/instantActions", qos=QOS)
    print("[MQTT] Subscribed: vda5050/agv/+/instantActions")
    client.subscribe(f"{UAGV_INTERFACE_NAME}/{UAGV_MAJOR_VERSION}/+/+/instantActions", qos=QOS)
    print(f"[MQTT] Subscribed: {UAGV_INTERFACE_NAME}/{UAGV_MAJOR_VERSION}/+/+/instantActions")

    client.subscribe("vda5050/agv/+/order", qos=QOS)
    print("[MQTT] Subscribed: vda5050/agv/+/order")
    client.subscribe(f"{UAGV_INTERFACE_NAME}/{UAGV_MAJOR_VERSION}/+/+/order", qos=QOS)
    print(f"[MQTT] Subscribed: {UAGV_INTERFACE_NAME}/{UAGV_MAJOR_VERSION}/+/+/order")

    # AGV SLAM gửi bản đồ quét laser về (không thuộc chuẩn VDA5050 gốc — tự thêm
    # theo đúng quy ước topic đang dùng cho state/connection/order/instantActions).
    client.subscribe("vda5050/agv/+/map", qos=QOS)
    print("[MQTT] Subscribed: vda5050/agv/+/map")
    client.subscribe(f"{UAGV_INTERFACE_NAME}/{UAGV_MAJOR_VERSION}/+/+/map", qos=QOS)
    print(f"[MQTT] Subscribed: {UAGV_INTERFACE_NAME}/{UAGV_MAJOR_VERSION}/+/+/map")

    # Camera băng tải
    client.subscribe("convQR/+/+/+/pub", qos=QOS)
    print("[MQTT] Subscribed: convQR/+/+/+/pub")

    # ── Line AGV v2 — luôn subscribe wildcard, không phụ thuộc registry ──────
    # Wildcard factory + agv_id: nhận từ mọi Line AGV bất kể factory name
    _line_ver = os.getenv("LINE_AGV_MQTT_VERSION", "v2")
    for _kind in ("state", "connection", "info"):
        _t = f"{UAGV_INTERFACE_NAME}/{_line_ver}/+/+/{_kind}"
        client.subscribe(_t, qos=QOS)
        print(f"[MQTT] Subscribed (LINE v2): {_t}")

    # ── Cửa tự động (gate) — trạng thái từ bộ điều khiển cửa ─────────────────
    # Xem PROTOCOL_GUIDE.md mục "Cửa tự động (Gate Controller)"
    _gate_state_topic = f"{GATE_INTERFACE_NAME}/{GATE_MQTT_VERSION}/+/+/state"
    client.subscribe(_gate_state_topic, qos=QOS)
    print(f"[MQTT] Subscribed (GATE): {_gate_state_topic}")

    # ── Thang máy — trạng thái từ bộ điều khiển thang ────────────────────────
    _elev_state_topic = f"{ELEVATOR_INTERFACE_NAME}/{ELEVATOR_MQTT_VERSION}/+/+/state"
    client.subscribe(_elev_state_topic, qos=QOS)
    print(f"[MQTT] Subscribed (ELEVATOR): {_elev_state_topic}")
    # connection (Last Will ONLINE/OFFLINE) — để biết thang nào đang kết nối; thang không gửi thì bỏ qua
    client.subscribe(f"{ELEVATOR_INTERFACE_NAME}/{ELEVATOR_MQTT_VERSION}/+/+/connection", qos=QOS)

    # ── Thang máy thật giao thức uelev/v2 — luôn nghe mọi thang/thiết bị (bảng điều khiển tay, nhận diện kết nối)
    # ĐỘC LẬP với ELEVATOR_BACKEND và bản đồ. QoS 1 vì tin connection (LWT) quan trọng.
    for _uk in ("state", "connection"):
        client.subscribe(f"uelev/v2/+/+/+/{_uk}", qos=1)
    print("[MQTT] Subscribed (UELEV): uelev/v2/+/+/+/{state,connection}")

    # ── Setup_subscriptions (VDA5050 + thông báo registry) ───────────────────
    try:
        from unified_mqtt import setup_subscriptions
        from agv_registry import agv_registry
        _cfg = getattr(client, "_unified_config", {})
        setup_subscriptions(client, _cfg)
    except Exception as _e:
        print(f"[UNIFIED_MQTT] setup_subscriptions error: {_e}")

    # ── Publish FMS presence ONLINE (Phần 1 spec) ────────────────────────────
    try:
        _topic = _fms_manager_topic()
        client.publish(_topic, _fms_presence_payload("ONLINE"), qos=1, retain=True)
        print(f"[MQTT] FMS presence ONLINE → {_topic}")
    except Exception as _e:
        print(f"[MQTT] FMS presence publish error: {_e}")


def _elevator_broker_link(up: bool) -> None:
    """Báo backend thang uelev_v2 biết SERVER mất/có lại broker (để không coi thiết bị thang là offline oan)."""
    try:
        from elevator_coordinator import elevator_coordinator as _ec_l
        _h = getattr(_ec_l, "on_broker_link", None)
        if _h is not None:
            _h(up)
    except Exception as _e_l:
        print(f"[ELEVATOR] báo trạng thái broker lỗi: {_e_l}")


def on_disconnect(client, userdata, rc):
    print(f"[MQTT] Disconnected rc={rc}")
    _elevator_broker_link(False)
    if rc != 0:
        # Mất kết nối broker đột ngột — mark toàn bộ AGV là UNKNOWN
        for _aid in list(agv_manager.list_agvs().keys()):
            agv_manager.set_connection(_aid, "UNKNOWN")
        print("[MQTT] All AGV states marked UNKNOWN (broker disconnected)")


def on_subscribe(client, userdata, mid, granted_qos):
    print(f"[MQTT] Subscribed mid={mid}, granted_qos={granted_qos}")

def build_charge_name_candidates() -> list[str]:
    return ["CHARGE", "Charge", "ChargeStation", "Trạm sạc", "Sac", "Sạc"]

def build_wait_name_candidates() -> list[str]:
    return ["WAIT", "Wait", "Waiting", "Khu chờ", "Cho", "Chờ"]

def _parse_agv_topic(topic_parts: list[str]) -> tuple[str | None, str | None]:
    if len(topic_parts) >= 4 and topic_parts[0] == "vda5050" and topic_parts[1] == "agv":
        return topic_parts[2], topic_parts[3]
    if (
        len(topic_parts) >= 5
        and topic_parts[0] == UAGV_INTERFACE_NAME
        and topic_parts[1] == UAGV_MAJOR_VERSION
    ):
        return topic_parts[3], topic_parts[4]
    return None, None


def _publish_topic_candidates(agv_id: str, suffix: str, manufacturer: str | None = None) -> list[str]:
    """VDA5050 topics only — dùng cho AGV VDA5050. Line AGV dùng _line_agv_topic().

    manufacturer: nếu không truyền, tự đọc field 'factory' của ĐÚNG agv_id này từ
    agv_registry (giống hệt cách _line_agv_topic() làm cho Line AGV) — mỗi nhà
    máy 1 giá trị factory riêng, xe SLAM cùng nhà máy tự nhiên chung 1 namespace
    topic, KHÔNG lẫn với xe ở nhà máy khác dùng chung server. Chỉ rơi về
    UAGV_MANUFACTURER (biến môi trường) khi AGV đó chưa cấu hình factory gì cả.
    """
    if manufacturer is None:
        try:
            from agv_registry import agv_registry as _reg_pub
            manufacturer = _reg_pub.get_factory(agv_id, default=UAGV_MANUFACTURER)
        except Exception:
            manufacturer = UAGV_MANUFACTURER
    maker = (manufacturer or UAGV_MANUFACTURER).strip() or UAGV_MANUFACTURER
    return [
        f"vda5050/agv/{agv_id}/{suffix}",
        f"{UAGV_INTERFACE_NAME}/{UAGV_MAJOR_VERSION}/{maker}/{agv_id}/{suffix}",
    ]


def _line_agv_topic(agv_id: str, suffix: str) -> str:
    """Topic chuẩn cho Line AGV: uagv/v2/{factory}/{agv_id}/{suffix}
    Factory đọc từ agv_registry theo AGV cụ thể, fallback LINE_AGV_FACTORY.
    """
    from unified_mqtt import LINE_AGV_VERSION, LINE_AGV_FACTORY
    from agv_registry import agv_registry as _reg
    factory = _reg.get_factory(agv_id, default=(LINE_AGV_FACTORY or "VietDuc"))
    return f"{UAGV_INTERFACE_NAME}/{LINE_AGV_VERSION}/{factory}/{agv_id}/{suffix}"


def on_message(client, userdata, msg):
    if _mqtt_stopping or _is_app_shutting_down():
        return

    # ── Cửa tự động (gate) — trạng thái từ bộ điều khiển cửa ─────────────────
    # Topic: gate/v1/{factory}/{door_id}/state — xem PROTOCOL_GUIDE.md.
    # Xử lý RIÊNG, SỚM NHẤT (trước unified routing của AGV) vì đây không phải
    # topic của AGV — topic_router không biết xử lý, sẽ rơi vào nhánh khác.
    try:
        _gate_parts = msg.topic.split("/")
        if (len(_gate_parts) == 5 and _gate_parts[0] == GATE_INTERFACE_NAME
                and _gate_parts[1] == GATE_MQTT_VERSION and _gate_parts[4] == "state"):
            _door_id = _gate_parts[3]
            _gate_data = json.loads(msg.payload.decode("utf-8", errors="replace"))
            _gate_state = str(_gate_data.get("state") or "").strip().lower()
            if _gate_state:
                from door_coordinator import door_coordinator
                print(f"[GATE_STATE] {_door_id}: {_gate_state}")
                door_coordinator.on_gate_state(_door_id, _gate_state)
            return
    except Exception as _e_gate:
        print(f"[GATE_STATE] parse error: {_e_gate}")

    # ── Thang máy giao thức uelev/v2 (phần cứng thật, thư viện elevator_coord) ──
    if msg.topic.startswith("uelev/"):
        try:
            from uelev_console import uelev_hub          # bảng điều khiển tay + nhận diện kết nối (luôn bật)
            uelev_hub.on_message(msg.topic, msg.payload, bool(msg.retain))
        except Exception as _e_h:
            print(f"[UELEV] hub lỗi: {type(_e_h).__name__}: {_e_h}")
        try:
            from elevator_coordinator import elevator_coordinator as _ec_u
            _h = getattr(_ec_u, "on_uelev_message", None)
            if _h is not None:
                _h(msg.topic, msg.payload)
        except Exception as _e_u:
            print(f"[ELEVATOR] uelev message lỗi: {type(_e_u).__name__}: {_e_u}")
        return

    # ── Thang máy — elevator/v1/{factory}/{elevator_id}/state ────────────────
    try:
        _el_parts = msg.topic.split("/")
        if (len(_el_parts) == 5 and _el_parts[0] == ELEVATOR_INTERFACE_NAME
                and _el_parts[1] == ELEVATOR_MQTT_VERSION and _el_parts[4] == "connection"):
            from elevator_registry import elevator_registry
            elevator_registry.on_connection(_el_parts[2], _el_parts[3], msg.payload)
            return
        if (len(_el_parts) == 5 and _el_parts[0] == ELEVATOR_INTERFACE_NAME
                and _el_parts[1] == ELEVATOR_MQTT_VERSION and _el_parts[4] == "state"):
            _el_id = _el_parts[3]
            _el_data = json.loads(msg.payload.decode("utf-8", errors="replace"))
            _el_state = str(_el_data.get("state") or "").strip().lower()
            if _el_state:
                from elevator_registry import elevator_registry
                elevator_registry.on_state(_el_parts[2], _el_id, _el_state, _el_data.get("floor"), bool(msg.retain))
                from elevator_coordinator import elevator_coordinator
                print(f"[ELEVATOR_STATE] {_el_id}: {_el_state} floor={_el_data.get('floor')}")
                elevator_coordinator.on_state(_el_id, _el_state, _el_data.get("floor"))
            return
    except Exception as _e_el:
        print(f"[ELEVATOR_STATE] parse error: {_e_el}")

    # ── Unified routing: nhận biết AGV từ topic + registry ───────────────────
    try:
        from unified_mqtt import topic_router
        from line_agv_handler import line_agv_handler
        from agv_registry import agv_registry, AGV_TYPE_LINE
        from agv_heartbeat import touch as _hb_touch

        agv_type_route, agv_id_route, kind_route = topic_router.parse(msg.topic)

        if agv_id_route:
            # Tra registry theo agv_id (ưu tiên DB — agv_type bắt đầu "slam" → VDA5050)
            reg_type = agv_registry.get_type(agv_id_route)
            if reg_type is None:
                # Dùng type từ topic parser nếu chưa có trong registry
                reg_type = agv_type_route
                # AGV chưa có trong registry (thêm sau khi server start) → reload
                try:
                    agv_registry.load_from_db()
                    reg_type = agv_registry.get_type(agv_id_route) or reg_type
                except Exception:
                    pass

            # Route LINE AGV → line_agv_handler
            if reg_type == AGV_TYPE_LINE:
                try:
                    payload_str = msg.payload.decode("utf-8", errors="replace")
                except Exception:
                    payload_str = ""
                line_agv_handler.dispatch(agv_id_route, kind_route, payload_str)
                # Update last_seen + last_tag sau khi state được parse
                if kind_route == "state":
                    _st = line_agv_handler.state_store.get(agv_id_route)
                    _tag = _st.current_tag if _st else None
                    _hb_touch(agv_id_route, tag=_tag)
                    _broadcast_line_agv_state(agv_id_route)
                    # Đồng bộ factory từ topic vào DB (tự động sau khi AGV config xong)
                    _topic_parts_r = msg.topic.split("/")
                    if len(_topic_parts_r) >= 4:
                        _sync_agv_from_topic(agv_id_route, _topic_parts_r[2])
                else:
                    _hb_touch(agv_id_route)
                return   # Line AGV handled — không đi vào VDA5050 flow

    except Exception as _route_err:
        print(f"[UNIFIED_MQTT] routing error: {_route_err}")
    # ─────────────────────────────────────────────────────────────────────────

    topic_parts = msg.topic.split("/")
    agv_id, message_kind = _parse_agv_topic(topic_parts)
    print(f"[MQTT] Nhận tin từ topic: {msg.topic}")
    if MQTT_VERBOSE_LOG:
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

        # === DECODE PAYLOAD ===
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception as e:
            print(f"[MQTT] LỖI JSON: {e} | Raw: {msg.payload[:200]}")
            return

        # === XỬ LÝ STATE ===
        if message_kind == "state" and agv_id:
            agv_ip = "from_mqtt"

            pos = payload.get("agvPosition", {}) or {}
            raw_map_id = payload.get("mapCurrent") or pos.get("mapId") or ""
            resolved_map_id = resolve_map_id_sync(str(raw_map_id)) if raw_map_id else None

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
                "map_id": str(resolved_map_id or raw_map_id or "").strip()
            }

            state_data["last_update_ts"] = time.time()
            state_data["last_seen_mono"] = time.monotonic()
            state_data["last_update"] = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")

            # ── Cửa tự động (gate) cho VDA5050 — phát hiện đổi node để biết lúc nào
            # xin mở/báo đã qua, giống hệt Line AGV (_handle_door_arrival trong
            # line_agv_handler.py). Phải lấy lastNodeId CŨ trước khi update_status
            # ghi đè. An toàn gọi request_open ngay khi đổi node (không cần chờ
            # thêm "đã dừng hẳn") vì _dispatch_go_to đã TÁCH route để node cửa
            # luôn là đích cuối của CHẶNG này — tới đó nghĩa là hết node released,
            # xe tự dừng đúng chuẩn VDA5050.
            _prev_node_door = str((agv_manager.get_agv(agv_id) or {}).get("lastNodeId") or "")
            _new_node_door  = str(state_data.get("lastNodeId") or "")

            # CẬP NHẬT AGV
            agv_manager.update_status(agv_id, state_data)
            detect_alerts(agv_id, state_data)

            if _new_node_door and _new_node_door != _prev_node_door:
                try:
                    _door_id_arr = str(
                        (getattr(map_manager, 'node_actions', {}) or {})
                        .get(_new_node_door, {}).get('door_id') or ''
                    ).strip()
                    if _door_id_arr:
                        from door_coordinator import door_coordinator as _door_co_arr
                        if _door_co_arr.is_exit_arrival(_door_id_arr, agv_id, _new_node_door):
                            _door_co_arr.notify_exit(_door_id_arr, agv_id)
                        else:
                            _door_co_arr.request_open(_door_id_arr, agv_id, _new_node_door)
                except Exception as _e_door_vda:
                    print(f"[DOOR] VDA5050 {agv_id}: lỗi xử lý cửa tại {_new_node_door}: {_e_door_vda}")

            # check_retries() cần được "tick" định kỳ để phát hiện timeout chờ mở
            # cửa — Line AGV đã gọi ở line_agv_handler.py mỗi state message; gọi
            # thêm ở đây để hoạt động cả khi đội xe chỉ toàn VDA5050 (không có
            # Line AGV nào gửi state để tick giúp).
            try:
                from door_coordinator import door_coordinator as _door_co_tick_vda
                _door_co_tick_vda.check_retries()
            except Exception as _e_door_tick_vda:
                print(f"[DOOR] VDA5050 check_retries lỗi: {_e_door_tick_vda}")

            # Cập nhật last_seen trong DB (giống LINE AGV, để AGVManager + các endpoint
            # dùng cùng nguồn dữ liệu nhất quán)
            try:
                from agv_heartbeat import touch as _hb_touch_vda
                _hb_touch_vda(agv_id)
            except Exception:
                pass

            # Parse PEER_STOP info for LIDAR collision resolution
            peer_stop_peer_id = None
            for _info_item in (payload.get("information") or []):
                if isinstance(_info_item, dict) and _info_item.get("infoType") == "PEER_STOP":
                    peer_stop_peer_id = str(_info_item.get("infoDescription") or "").strip() or None
                    break
            if peer_stop_peer_id:
                existing = _peer_stop_states.get(agv_id)
                if not existing or existing.get("peer_id") != peer_stop_peer_id:
                    _peer_stop_states[agv_id] = {"peer_id": peer_stop_peer_id, "since": time.time()}
                # else: keep existing entry to preserve original `since` timestamp
            else:
                prev_entry = _peer_stop_states.pop(agv_id, None)
                if prev_entry:
                    _peer_stop_resolved_pairs.discard(frozenset([agv_id, prev_entry.get("peer_id", "")]))

            _battery_pct = state_data['batteryState'].get('batteryCharge', 'N/A')
            _battery_key = round(_battery_pct) if isinstance(_battery_pct, (int, float)) else _battery_pct
            _state_key = (state_data['lastNodeId'], state_data['orderId'], _battery_key, state_data['paused'])
            if _last_state_print.get(agv_id) != _state_key:
                _last_state_print[agv_id] = _state_key
                print(f"\n[STATE] AGV {agv_id} ĐÃ CẬP NHẬT TỪ MQTT THẬT!")
                print(f"   → Node: {state_data['lastNodeId']}")
                print(f"   → Order: {state_data['orderId']}")
                print(f"   → Pin: {_battery_pct}%")
                print(f"   → Vị trí: x={float(x):.3f}, y={float(y):.3f}, θ={float(theta):.3f}")
                print(f"   → Paused: {state_data['paused']}\n")

            # === VDA5050: thông báo task_queue khi AGV vừa dừng (paused=True) ===
            # NGOẠI LỆ: nếu node đích cần dừng chờ xác nhận thủ công (PICKUP/DROP
            # — xem agv_manager.pending_confirm_node, set lúc dispatch trong
            # main.py._dispatch_go_to) và xe đang dừng ĐÚNG tại node đó → KHÔNG
            # auto-complete, để queue không tự chạy lệnh kế trước khi người dùng
            # xác nhận (tương đương task_lifecycle bên Line AGV). Xác nhận qua
            # /api/execute/lifecycle-ack (đã tổng quát hoá cho VDA5050).
            _prev_paused = getattr(agv_manager, "_prev_paused_states", {})
            was_paused   = _prev_paused.get(agv_id, False)
            now_paused   = bool(state_data.get("paused"))
            _pending_confirm_vda = agv_manager.get_pending_confirm(agv_id)
            _at_confirm_node = bool(_pending_confirm_vda) and (
                str(state_data.get("lastNodeId") or "") == str(_pending_confirm_vda))
            if not was_paused and now_paused:
                if _at_confirm_node:
                    print(f"[VDA5050] {agv_id}: tới {_pending_confirm_vda} — "
                          f"chờ xác nhận thủ công, không auto-complete")
                else:
                    try:
                        from task_queue import agv_task_queue as _tq
                        _tq.on_agv_completed(agv_id, notes="vda5050:paused")
                    except Exception as _qe:
                        pass
            _prev_paused[agv_id] = now_paused
            if not hasattr(agv_manager, "_prev_paused_states"):
                agv_manager._prev_paused_states = _prev_paused

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
            if raw_map_id is not None:
                try:
                    from main import broadcast_agv_pose

                    async def send_pose():
                        await broadcast_agv_pose(agv_id, float(x), float(y), float(theta), str(raw_map_id))

                    run_async_in_thread(send_pose())
                except Exception as e:
                    print(f"[WS] Lỗi broadcast pose: {e}")

            # === GIẢI PHÓNG KHÓA ĐƯỜNG KHI ORDER KẾT THÚC ===
            try:
                order_status = (payload.get("orderStatus") or "").upper()
                information_items = payload.get("information") or []
                info_statuses = {
                    str(item.get("infoType") or "").upper()
                    for item in information_items
                    if isinstance(item, dict)
                }
                all_nodes_finished = payload.get("nodeStates") and all(
                    ns.get("nodeStatus") in ["FINISHED", "DONE"] or ns.get("state") in ["FINISHED", "DONE"]
                    for ns in payload["nodeStates"]
                )
                finished_from_info = bool(
                    {"ORDER_FINISHED", "ORDER_CANCELED", "ORDER_ABORTED"} & info_statuses
                )
                route_is_finished = (
                    order_status in ["FINISHED", "CANCELED", "ABORTED"]
                    or all_nodes_finished
                    or finished_from_info
                )
                if route_is_finished:
                    from main import edge_coordinator, traffic_engine
                    edge_coordinator.release(agv_id)
                    traffic_engine.complete_route(agv_id)
                    _conflict_wait_mgr.release(agv_id, "route_finished")
                    release_reason = order_status or ("INFO_STATUS" if finished_from_info else "ALL_NODES_FINISHED")
                    print(f"[COORD] Released route reservations for {agv_id} | status={release_reason}")
            except Exception as e:
                print(f"[COORD] Release failed for {agv_id}: {e}")

        # === XỬ LÝ LỆNH MOVE TỪ MQTT EXPLORER ===
            try:
                if state_data.get("map_id") or raw_map_id:
                    from traffic_core import Telemetry, HealthState, TrafficState, TrafficAction, RerouteStrategy
                    from main import (
                        traffic_engine,
                        ensure_traffic_topology_from_loaded_map,
                        sync_traffic_route_from_state,
                        build_order_for_traffic_route,
                    )

                    traffic_map_id = ensure_traffic_topology_from_loaded_map(
                        str(state_data.get("map_id") or raw_map_id)
                    )
                    # When a reroute order was recently sent (pending), prevent the stale
                    # MQTT state (still reflecting the OLD order) from overwriting the newly
                    # activated escape route in the traffic engine.  The escape route must
                    # stay in place until the AGV acknowledges the new order.
                    _has_pending_reroute = _pending_reroute_apply.get(agv_id) is not None
                    sync_traffic_route_from_state(
                        agv_id=agv_id,
                        map_id=traffic_map_id,
                        node_states=payload.get("nodeStates") or [],
                        current_hint_node=state_data.get("lastNodeId"),
                        allow_rehydrate=not route_is_finished and not _has_pending_reroute,
                    )

                    velocity = payload.get("velocity") or {}
                    speed = abs(float(velocity.get("vx") or velocity.get("speed") or 0.0))
                    traffic_state = TrafficState.MOVING if speed > 0.01 else TrafficState.IDLE
                    if state_data.get("paused"):
                        traffic_state = TrafficState.WAITING
                    health_state = HealthState.OK
                    if state_data.get("error"):
                        health_state = HealthState.ERROR

                    engine_result = traffic_engine.handle_telemetry(
                        traffic_map_id,
                        Telemetry(
                            agv_id=agv_id,
                            x=float(x),
                            y=float(y),
                            speed=speed,
                            heading_deg=float(theta),
                            timestamp=time.time(),
                            health_state=health_state,
                            traffic_state=traffic_state,
                        ),
                    )
                    if MQTT_VERBOSE_LOG and engine_result.decision is not None:
                        print(
                            f"[TRAFFIC] {agv_id} | action={engine_result.decision.action.value} | "
                            f"reason={engine_result.decision.reason} | related={engine_result.decision.related_agv_id}"
                        )

                    # Proactive node blocking: when AGV enters its LAST route edge (approaching
                    # destination) or is idle on an edge, immediately reroute others heading
                    # to that same node.  Only fires for destination nodes to avoid false positives
                    # on shared transit nodes (e.g. both AGVs passing through N17 separately).
                    _cur_edge = traffic_engine.get_agv_current_edge(traffic_map_id, agv_id)
                    if _cur_edge:
                        _, _to_node = traffic_engine._parse_edge_node_ids(_cur_edge)
                        if _to_node:
                            # Check if _to_node is this AGV's actual destination (last seg) or idle
                            _agv_route = traffic_engine._routes.get(agv_id)
                            _is_dest_node = False
                            if _agv_route and _agv_route.segments:
                                _, _last_to = traffic_engine._parse_edge_node_ids(
                                    _agv_route.segments[-1].edge_id
                                )
                                _is_dest_node = (_last_to == _to_node)
                            elif not _agv_route:
                                # No active route → AGV is idle, will stop at to_node
                                _is_dest_node = True

                            if _is_dest_node:
                                _prev_incoming = _agv_incoming_node.get(agv_id)
                                if _prev_incoming != _to_node:
                                    if _prev_incoming:
                                        _proactive_rerouted_pairs.discard(
                                            frozenset([agv_id, _prev_incoming])
                                        )
                                    _agv_incoming_node[agv_id] = _to_node
                                    _pair_key = frozenset([agv_id, _to_node])
                                    if _pair_key not in _proactive_rerouted_pairs:
                                        _proactive_rerouted_pairs.add(_pair_key)
                                        _proactive_results = traffic_engine.proactive_reroute_for_incoming_node(
                                            traffic_map_id, agv_id, _to_node
                                        )
                                        for _affected_agv, _proactive_res in _proactive_results:
                                            _send_peer_stop_reroute(
                                                _affected_agv, _proactive_res,
                                                traffic_engine, str(traffic_map_id)
                                            )
                    else:
                        # AGV is at a node — clear its incoming reservation
                        _prev = _agv_incoming_node.pop(agv_id, None)
                        if _prev:
                            _proactive_rerouted_pairs.discard(frozenset([agv_id, _prev]))

                    # Proactive idle-block reroute: if THIS AGV's route passes through a node
                    # where another idle (finished) AGV is parked, reroute NOW before the
                    # moving AGV enters LIDAR range and gets hard-paused.
                    _cur_own_route = traffic_engine._routes.get(agv_id)
                    if _cur_own_route and _cur_own_route.segments:
                        for _idle_cand_id, _idle_cand_data in list(agv_manager.list_agvs().items()):
                            if _idle_cand_id == agv_id:
                                continue
                            if traffic_engine._routes.get(_idle_cand_id) is not None:
                                continue  # other AGV still has an active route — not idle
                            _idle_cand_node_raw = str(_idle_cand_data.get("lastNodeId") or "").strip()
                            if not _idle_cand_node_raw:
                                continue
                            _idle_cand_norm = re.sub(r'^[A-Za-z]+', '', _idle_cand_node_raw) or _idle_cand_node_raw
                            _route_passes_through_idle = any(
                                _idle_cand_norm in traffic_engine._parse_edge_node_ids(seg.edge_id)
                                for seg in _cur_own_route.segments
                            )
                            if not _route_passes_through_idle:
                                continue
                            # Nếu idle AGV đứng tại ĐÍCH ĐẾN của moving AGV, không reroute.
                            # Moving AGV CẦN đến đó – mọi reroute "quanh" đích đều vô nghĩa
                            # và tạo vòng lặp vô tận (mỗi route version mới vẫn kết thúc ở đích).
                            # Thay vào đó để moving AGV tiến đến đích bình thường.
                            _own_goal_norm = re.sub(
                                r'^[A-Za-z]+', '', str(_cur_own_route.goal_node or "")
                            ) or str(_cur_own_route.goal_node or "")
                            if _idle_cand_norm and _own_goal_norm and _idle_cand_norm == _own_goal_norm:
                                continue  # skip: idle AGV at destination of moving AGV
                            _idle_done_key = frozenset([
                                f"{agv_id}@v{_cur_own_route.route_version}",
                                f"idle_{_idle_cand_id}_{_idle_cand_norm}",
                            ])
                            if _idle_done_key in _idle_block_proactive_done:
                                continue
                            _idle_block_proactive_done.add(_idle_done_key)
                            print(
                                f"[PROACTIVE_IDLE] {agv_id} route v{_cur_own_route.route_version} "
                                f"passes through idle {_idle_cand_id} at {_idle_cand_norm} — rerouting early"
                            )
                            _idle_early_result = traffic_engine.force_reroute_around_idle_peer(
                                traffic_map_id, agv_id, _idle_cand_node_raw, idle_agv_id=_idle_cand_id
                            )
                            if _send_peer_stop_reroute(agv_id, _idle_early_result, traffic_engine, str(traffic_map_id)):
                                break  # one reroute per tick

                    # LIDAR peer-stop resolution (mutual or one-sided timeout)
                    if peer_stop_peer_id:
                        my_entry = _peer_stop_states.get(agv_id) or {}
                        peer_entry = _peer_stop_states.get(peer_stop_peer_id) or {}
                        peer_stopped_by = peer_entry.get("peer_id")
                        is_mutual = peer_stopped_by == agv_id
                        elapsed = time.time() - (my_entry.get("since") or time.time())
                        pair_key = frozenset([agv_id, peer_stop_peer_id])
                        if pair_key not in _peer_stop_resolved_pairs:
                            if is_mutual or elapsed >= PEER_STOP_REROUTE_TIMEOUT_SEC:
                                _peer_stop_resolved_pairs.add(pair_key)
                                # One-sided timeout: stopped AGV (agv_id) wins → reroute/move the peer
                                _handle_mutual_peer_stop(
                                    agv_id, peer_stop_peer_id,
                                    traffic_engine, str(traffic_map_id),
                                )

                    # Only run map-wide evaluation when at least one AGV has an active route.
                    # With all AGVs visible in the shared StateStore (after has_map fix), calling
                    # evaluate_map_controls unconditionally causes heavy conflict detection even
                    # for idle AGVs (3 AGVs × 3 pairs), blocking _lock for too long.
                    _has_any_route = bool(traffic_engine._routes)
                    map_control_results = (
                        traffic_engine.evaluate_map_controls(traffic_map_id)
                        if _has_any_route
                        else {agv_id: engine_result}
                    )
                    if (
                        engine_result.reroute_result is not None
                        and engine_result.reroute_result.success
                        and engine_result.reroute_result.route is not None
                        and engine_result.reroute_result.strategy != RerouteStrategy.SPEED_ONLY
                    ):
                        # Preserve the immediate successful reroute found during the
                        # telemetry-triggered evaluation. A subsequent map-wide
                        # reevaluation in the same tick can otherwise downgrade it
                        # back to WAIT before the reroute order is published.
                        map_control_results[agv_id] = engine_result

                    # ── ConflictWaitManager tick: retry reroute cho AGV đang chờ ──────
                    _conflict_wait_mgr.tick(
                        map_control_results=map_control_results,
                        traffic_map_id=traffic_map_id,
                        traffic_engine_ref=traffic_engine,
                        agv_manager_ref=agv_manager,
                    )
                    # Release các AGV đã reroute thành công (không còn trong wait state)
                    for _wid in list(_conflict_wait_mgr.all_waiting()):
                        _wr = map_control_results.get(_wid)
                        if _wr and _wr.reroute_result and _wr.reroute_result.success:
                            _conflict_wait_mgr.release(_wid, "reroute_success_external")

                    hold_for_reroute: set[str] = set()
                    for source_agv_id, source_result in map_control_results.items():
                        source_state_data = agv_manager.get_agv(source_agv_id) or {}
                        source_decision = source_result.decision
                        source_reroute_result = source_result.reroute_result
                        related_agv_id = str(source_decision.related_agv_id or "").strip() if source_decision is not None else ""
                        conflict_id = str(source_decision.related_conflict_id or "").strip() if source_decision is not None else ""
                        decision_reason = str(source_decision.reason or "").lower() if source_decision is not None else ""

                        if related_agv_id and (
                            (
                                source_decision is not None
                                and source_decision.action in {TrafficAction.WAIT, TrafficAction.STOP, TrafficAction.REROUTE}
                                and (
                                    conflict_id.startswith(
                                        (
                                            "planned_head_on_",
                                            "forced_head_on_",
                                            "direct_head_on_",
                                            "immediate_head_on_",
                                            "direct_overlap_",
                                        )
                                    )
                                    or "head-on" in decision_reason
                                    or "corridor" in decision_reason
                                    or "reroute" in decision_reason
                                )
                            )
                            or not _is_pending_reroute_applied(source_agv_id, source_state_data)
                        ):
                            hold_for_reroute.add(related_agv_id)

                        if (
                            source_decision is None
                            or source_reroute_result is None
                            or not source_reroute_result.success
                            or source_reroute_result.route is None
                            or source_reroute_result.strategy == RerouteStrategy.SPEED_ONLY
                        ):
                            continue
                        if related_agv_id:
                            hold_for_reroute.add(related_agv_id)

                    for target_agv_id, target_result in map_control_results.items():
                        target_state_data = agv_manager.get_agv(target_agv_id) or {}
                        target_decision = target_result.decision
                        target_reroute_result = target_result.reroute_result

                        if target_decision is not None and MQTT_VERBOSE_LOG:
                            print(
                                f"[TRAFFIC MAP] {target_agv_id} | action={target_decision.action.value} | "
                                f"reason={target_decision.reason} | related={target_decision.related_agv_id}"
                            )

                        if (
                            target_reroute_result is not None
                            and target_reroute_result.success
                            and target_reroute_result.route is not None
                            and target_reroute_result.strategy != RerouteStrategy.SPEED_ONLY
                        ):
                            # Guard: nếu AGV chưa acknowledge reroute trước, không gửi tiếp.
                            # Tránh order flood (gửi order liên tục mỗi tick khi escape thành công).
                            if not _is_pending_reroute_applied(target_agv_id, target_state_data):
                                continue
                            # Khi có reroute thực sự → xóa yield/wait state (AGV đổi đường)
                            _yield_states.pop(target_agv_id, None)
                            _conflict_wait_mgr.release(target_agv_id, "reroute_success_normal_flow")
                            next_order_id = str(target_state_data.get("orderId") or uuid.uuid4())
                            next_update_id = int(target_state_data.get("orderUpdateId") or 0) + 1
                            reroute_order, reroute_path = build_order_for_traffic_route(
                                target_agv_id,
                                target_reroute_result.route,
                                target_state_data,
                                order_id=next_order_id,
                                order_update_id=next_update_id,
                            )
                            if MQTT_VERBOSE_LOG:
                                print(f"[REROUTE] {target_agv_id} | reason={target_reroute_result.reason} | path={reroute_path}")
                            _remember_pending_reroute_apply(
                                target_agv_id,
                                next_order_id,
                                next_update_id,
                                [segment.edge_id for segment in target_reroute_result.route.segments],
                            )
                            send_order(target_agv_id, reroute_order)
                            traffic_engine.activate_route(
                                target_agv_id,
                                str(traffic_map_id),
                                target_reroute_result.route,
                            )
                            # If the AGV was paused (by a previous WAIT decision), send RESUME
                            # so it can immediately execute the new reroute order.  Without
                            # RESUME, the AGV stays paused and the reroute order never applies.
                            _rr_action_state = target_state_data.get("actionState") or {}
                            _rr_sim_pause = bool(_rr_action_state.get("simPauseHold"))
                            _rr_is_head_on = str(target_reroute_result.reason or "").startswith("HEAD_ON_")
                            if target_state_data.get("paused") and not _rr_sim_pause and (
                                target_agv_id not in _peer_stop_states or _rr_is_head_on
                            ):
                                _send_traffic_control_action(target_agv_id, "RESUME")
                                if _rr_is_head_on and target_agv_id in _peer_stop_states:
                                    # HEAD_ON reroute sends AGV away from the other AGV — safe to
                                    # clear peer-stop so the AGV can execute the new order immediately
                                    _peer_stop_states.pop(target_agv_id, None)
                            continue

                        if target_agv_id in hold_for_reroute:
                            _target_has_route = bool(traffic_engine._routes.get(target_agv_id))
                            if not _target_has_route:
                                # Only pause idle AGVs held in place while a moving AGV reroutes.
                                if not target_state_data.get("paused"):
                                    _send_traffic_control_action(target_agv_id, "PAUSE")
                                continue
                            # Active-route AGV: do not force-pause it via hold_for_reroute.
                            # Fall through to its own traffic decision (WAIT/PROCEED/REROUTE).

                        if not _is_pending_reroute_applied(target_agv_id, target_state_data):
                            # Do NOT send PAUSE here — it creates a deadlock where the server
                            # PAUSEs the AGV waiting for order acknowledgment, but the PAUSE
                            # prevents the AGV from processing the new order.
                            # If the AGV is currently paused from a previous PAUSE command,
                            # send RESUME so it can actually execute the new reroute order.
                            _pr_action_state = target_state_data.get("actionState") or {}
                            _pr_sim_pause = bool(_pr_action_state.get("simPauseHold"))
                            if target_state_data.get("paused") and not _pr_sim_pause and target_agv_id not in _peer_stop_states:
                                _send_traffic_control_action(target_agv_id, "RESUME")
                            continue

                        if target_decision is None:
                            continue

                        # === YIELD-ON-EDGE ===
                        # Nếu AGV đang trong yield state: chờ winner clear contested_node thì resume.
                        if target_agv_id in _yield_states:
                            ys = _yield_states[target_agv_id]
                            elapsed = time.time() - ys["since"]
                            if elapsed > YIELD_TIMEOUT_SEC:
                                # Timeout: xóa yield, trả lại normal flow bên dưới
                                _yield_states.pop(target_agv_id)
                                print(f"[YIELD] {target_agv_id} yield timeout ({elapsed:.0f}s) → fallback to normal")
                            else:
                                cleared = _winner_cleared_contested_node(
                                    ys["contested_node"], ys["winner_agv_id"], map_control_results
                                )
                                if cleared:
                                    _yield_states.pop(target_agv_id)
                                    _action_state = target_state_data.get("actionState") or {}
                                    if target_state_data.get("paused") and not _action_state.get("simPauseHold"):
                                        _send_traffic_control_action(target_agv_id, "RESUME")
                                        print(f"[YIELD] {target_agv_id} RESUME: N{ys['contested_node']} cleared by {ys['winner_agv_id']}")
                                # Còn đang chờ: không làm gì (đã PAUSE rồi)
                                continue

                        # Cơ hội yield mới: AGV đang mid-edge tiến đến đúng node tranh chấp.
                        # Thay vì reroute hoặc pause+retry, dừng tại chỗ trên edge và chờ winner qua.
                        _target_state = target_result.state
                        if (
                            target_decision.action in {TrafficAction.WAIT, TrafficAction.STOP}
                            and (target_reroute_result is None or not target_reroute_result.success)
                            and target_agv_id not in _yield_states
                            and _target_state.current_node is None       # mid-edge (chưa đến node)
                            and _target_state.current_edge is not None   # đang trên 1 edge cụ thể
                        ):
                            contested = _extract_contested_node_from_reason(target_decision.reason or "")
                            if contested:
                                edge_dest = _to_node_of_edge(_target_state.current_edge)
                                if edge_dest and str(edge_dest).strip() == str(contested).strip():
                                    winner_id = str(target_decision.related_agv_id) if target_decision.related_agv_id else None
                                    _yield_states[target_agv_id] = {
                                        "contested_node": contested,
                                        "winner_agv_id": winner_id,
                                        "since": time.time(),
                                    }
                                    print(f"[YIELD] {target_agv_id} yield trên edge {_target_state.current_edge} → N{contested} (winner={winner_id})")
                                    if not target_state_data.get("paused"):
                                        _send_traffic_control_action(target_agv_id, "PAUSE")
                                    continue

                        target_action_state = target_state_data.get("actionState") or {}
                        sim_pause_hold = bool(target_action_state.get("simPauseHold"))
                        if not target_state_data.get("paused"):
                            _last_traffic_control_action.pop(target_agv_id, None)
                        if target_decision.action in {TrafficAction.WAIT, TrafficAction.STOP}:
                            # Only pause AGVs that have an active route — idle AGVs receiving
                            # WAIT decisions (from false conflicts due to stale edge state)
                            # should not be paused as they are not moving.
                            _target_has_route = bool(traffic_engine._routes.get(target_agv_id))
                            if not target_state_data.get("paused") and _target_has_route:
                                _send_traffic_control_action(target_agv_id, "PAUSE")

                            # ── Đăng ký vào ConflictWaitManager nếu reroute fail ──────────
                            # Khi không còn đường reroute, theo dõi winner để tự động
                            # retry + RESUME khi winner clear resource tranh chấp.
                            if (
                                _target_has_route
                                and target_reroute_result is not None
                                and not target_reroute_result.success
                                and not _conflict_wait_mgr.is_waiting(target_agv_id)
                            ):
                                _wait_winner = str(target_decision.related_agv_id or "").strip() or None
                                _wait_resource = (
                                    _extract_contested_node_from_reason(target_decision.reason or "")
                                    or str(target_decision.related_conflict_id or "").strip()
                                    or str(_wait_winner or "unknown")
                                )
                                _conflict_wait_mgr.register(
                                    target_agv_id,
                                    _wait_winner,
                                    _wait_resource,
                                    str(target_reroute_result.message or target_decision.reason or ""),
                                )
                        elif target_decision.action == TrafficAction.PROCEED:
                            if target_state_data.get("paused") and not sim_pause_hold:
                                # If the winner is still physically stopped due to LIDAR detection,
                                # skip RESUME — the simulator will auto-resume once the loser
                                # moves far enough away and LIDAR clears naturally.
                                if target_agv_id in _peer_stop_states:
                                    continue
                                # If there was a recent head-on assignment involving this AGV,
                                # gate RESUME until 1) the loser has applied the reroute (order ack),
                                # and 2) the contested resource/node is no longer held by the loser.
                                headon = _get_head_on_assignment(target_agv_id)
                                if headon:
                                    loser = headon.get("loser")
                                    resource_node = headon.get("resource_node")
                                    loser_state = agv_manager.get_agv(loser) or {}
                                    # Wait for loser to acknowledge/apply the reroute order
                                    if not _is_pending_reroute_applied(loser, loser_state):
                                        continue
                                    # If a resource node was identified, ensure loser no longer
                                    # effectively holds that node before allowing RESUME.
                                    if resource_node:
                                        try:
                                            from types import SimpleNamespace

                                            loser_state_obj = SimpleNamespace(
                                                agv_id=loser,
                                                x=float(loser_state.get("x", 0) or 0),
                                                y=float(loser_state.get("y", 0) or 0),
                                                current_node=loser_state.get("lastNodeId") or loser_state.get("current_node"),
                                                last_reached_node=loser_state.get("last_reached_node") or loser_state.get("lastReachedNode"),
                                                current_edge=loser_state.get("currentEdge") or loser_state.get("current_edge"),
                                            )
                                            # If loser still holds the resource, do not resume winner yet
                                            if traffic_engine._agv_effectively_holds_node(str(traffic_map_id), loser_state_obj, resource_node):
                                                continue
                                        except Exception:
                                            # On any unexpected error, be conservative and continue holding
                                            continue
                                    # All guards passed -> clear head-on record and resume
                                    _clear_head_on_assignment(target_agv_id)
                                _send_traffic_control_action(target_agv_id, "RESUME")
            except Exception as e:
                print(f"[TRAFFIC] Integration failed for {agv_id}: {e}")

        elif "move" in topic_parts and agv_id:
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
                    "version": "3.0.0",
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

        # === XỬ LÝ CONNECTION / LWT (Phần 2 spec) ===
        elif message_kind == "connection" and agv_id:
            if agv_id == "manager":
                return   # Phần 1 spec — tin hiện diện FMS, bỏ qua

            raw_cs = str(payload.get("connectionState", "")).upper()
            if raw_cs == "ONLINE":
                conn_value = "ONLINE"
            elif raw_cs in ("OFFLINE", "CONNECTIONBROKEN"):
                conn_value = "OFFLINE"
            else:
                conn_value = "OFFLINE"

            # Bỏ qua retained OFFLINE cũ nếu AGV vừa gửi state gần đây
            if conn_value == "OFFLINE":
                _st = agv_manager.get_agv(agv_id)
                if _st:
                    _ls = _st.get("last_seen_mono")
                    if _ls and (time.monotonic() - float(_ls)) < 5.0:
                        print(f"[CONN] {agv_id}: ignored stale OFFLINE "
                              f"(state {time.monotonic()-float(_ls):.1f}s ago)")
                        return

            agv_manager.set_connection(agv_id, conn_value)

        # === XỬ LÝ INFO (thông tin mạng AGV sau khi cấu hình) ===
        elif message_kind == "info" and agv_id:
            # Firmware publish sau khi connect: ip, subnet, gateway, dns
            _ip      = str(payload.get("ip")      or "").strip()
            _subnet  = str(payload.get("subnet")  or payload.get("mask") or "").strip()
            _gateway = str(payload.get("gateway") or payload.get("gw")   or "").strip()
            _dns     = str(payload.get("dns")     or "").strip()
            if any([_ip, _subnet, _gateway, _dns]):
                _sync_agv_network_info(agv_id, _ip, _subnet, _gateway, _dns)

        # === XỬ LÝ INSTANT ACTIONS ===
        elif message_kind == "instantActions" and agv_id:
            action_ids = [
                str(item.get("actionId") or "").strip()
                for item in (payload.get("actions") or [])
                if isinstance(item, dict)
            ]
            if action_ids and all(action_id in _recent_published_action_ids for action_id in action_ids if action_id):
                return
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

        # === AGV SLAM GỬI BẢN ĐỒ QUÉT LASER VỀ ===
        elif message_kind == "map" and agv_id:
            print(f"[SLAM_MAP] Nhận bản đồ quét từ {agv_id}")

            async def _save_slam_map():
                from main import handle_slam_map_upload
                try:
                    result = await handle_slam_map_upload(agv_id, payload)
                    print(f"[SLAM_MAP] {agv_id}: {result}")
                except Exception as e:
                    print(f"[SLAM_MAP] {agv_id}: lỗi lưu bản đồ: {e}")
            run_async_in_thread(_save_slam_map())

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
client.on_connect    = on_connect
client.on_message    = on_message
client.on_disconnect = on_disconnect
client.socket_timeout = float(os.getenv("MQTT_SOCKET_TIMEOUT_SEC", "5"))
_configure_client_for_mode(client, MQTT_MODE)


def _broadcast_line_agv_state(agv_id: str) -> None:
    """Broadcast trạng thái Line AGV ra WebSocket (cùng format với VDA5050 agv_state)."""
    try:
        from line_agv_handler import line_agv_handler
        state = line_agv_handler.state_store.get(agv_id)
        if state is None:
            return
        app = get_app()
        ws_func = getattr(getattr(app, "state", None), "send_websocket_update", None)
        if not ws_func:
            return

        async def _send():
            await ws_func({
                "type":           "agv_state",
                "agv_id":         agv_id,
                "agv_kind":       "LINE",
                "lastNodeId":     str(state.current_tag),
                "prev_tag":       state.prev_tag,
                "batteryCharge":  state.battery,
                "battery_low":    state.battery_low,
                "battery_blocking": state.battery_blocking,
                "driving":        state.driving,
                "paused":         state.paused,
                "operatingMode":  state.operating_mode,
                "connection":     state.connection_state,
                "task_lifecycle": state.task_lifecycle,
                "timestamp":      datetime.datetime.now().isoformat(),
            })

        run_async_in_thread(_send())
    except Exception as e:
        print(f"[LINE_AGV] WS broadcast error: {e}")


def _setup_line_agv_callbacks() -> None:
    """
    Inject callbacks vào line_agv_handler sau khi MQTT client sẵn sàng.
    Gọi từ setup_unified_mqtt().
    """
    from line_agv_handler import line_agv_handler

    def _send_window(agv_id: str, plan: dict) -> None:
        _send_line_order(agv_id, plan)

    def _on_event(agv_id: str, event_name: str, data: dict) -> None:
        # ACK ngay để Arduino xóa pendingEvent
        send_line_command(agv_id, "ack_event", d=event_name)
        print(f"[LINE_AGV] ACK event '{event_name}' → {agv_id}")

    def _on_battery_event(agv_id: str, event_name: str, data: dict) -> None:
        # Dispatch xe về trạm sạc
        try:
            from main import _line_agv_dispatch_to_charge
            _line_agv_dispatch_to_charge(agv_id)
        except Exception as e:
            print(f"[LINE_AGV] battery dispatch to charge failed: {e}")

    line_agv_handler.send_window_fn    = _send_window
    line_agv_handler.on_event          = _on_event
    line_agv_handler.on_battery_event  = _on_battery_event
    print("[UNIFIED_MQTT] Line AGV callbacks injected")


def setup_unified_mqtt(agv_configs: list[dict], server_config: dict | None = None) -> None:
    """
    Khởi tạo unified MQTT layer: load agv_registry, gắn config vào client.
    Phải gọi TRƯỚC start_mqtt() để on_connect biết cần subscribe gì.

    agv_configs : danh sách dict từ config, mỗi dict có ít nhất {"agv_id", "agv_type"}
    server_config: dict chứa "factory", "manufacturer" (tuỳ chọn)
    """
    from agv_registry import agv_registry
    from unified_mqtt import init_publisher
    agv_registry.load_from_config(agv_configs)
    cfg = dict(server_config or {})
    # Gắn config vào client object để on_connect đọc được
    client._unified_config = cfg
    init_publisher(client, cfg)
    _setup_line_agv_callbacks()
    print(f"[UNIFIED_MQTT] Registry loaded: {agv_registry}")


def start_mqtt():
    global _mqtt_stopping, _manager_conn_hid
    try:
        _mqtt_stopping = False
        reset_fms_topic_cache()
        _manager_conn_hid = 0   # reset về 0 — LWT dùng hid=0, ONLINE sẽ là hid=1
        _topic = _fms_manager_topic()   # latch topic trước connect()

        # LWT: headerId=0 (broker-generated sentinel, không tăng counter live)
        # ESP chỉ kiểm tra connectionState, không validate headerId
        _lwt_payload = json.dumps({
            "headerId":        0,
            "timestamp":       datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "version":         "2.0.0",
            "manufacturer":    _topic.split("/")[2] if len(_topic.split("/")) >= 5 else UAGV_MANUFACTURER,
            "serialNumber":    "manager",
            "connectionState": "CONNECTIONBROKEN",
        })
        client.will_set(_topic, _lwt_payload, qos=1, retain=True)
        print(f"[MQTT] LWT set → {_topic}")
        # keepalive=30s → LWT bắn sau ~45s khi crash (spec khuyến nghị 15–30s)
        client.connect(BROKER, PORT, keepalive=30)
        client.loop_start()
        return True
    except Exception as e:
        print(f"[MQTT] Broker connect error: {e}")
        print(f"[MQTT] Broker config: host={BROKER} port={PORT}")
        return False


def stop_mqtt():
    global client, _mqtt_stopping
    if client:
        _mqtt_stopping = True
        print("[MQTT] Stopping...")
        try:
            # Publish CONNECTIONBROKEN trước khi disconnect clean (Phần 1 spec mục B)
            _topic = _fms_manager_topic()
            _info = client.publish(_topic, _fms_presence_payload("CONNECTIONBROKEN"), qos=1, retain=True)
            try:
                _info.wait_for_publish(timeout=2)
            except Exception:
                pass
            print(f"[MQTT] FMS presence CONNECTIONBROKEN → {_topic}")
            client.disconnect()
        finally:
            client.loop_stop()
        print("[MQTT] Stopped")


def switch_mqtt_mode(new_mode: str) -> dict:
    """Đổi mode kết nối MQTT (local / cloud) và kết nối lại ngay.
    Tạo client mới vì paho TLS phải cấu hình trước khi connect().
    """
    global client, BROKER, PORT, MQTT_MODE
    if new_mode not in ("local", "cloud"):
        return {"ok": False, "error": "mode phải là 'local' hoặc 'cloud'"}

    _save_mqtt_mode(new_mode)
    new_broker, new_port = _resolve_broker_port(new_mode)

    print(f"[MQTT] Switching {MQTT_MODE} → {new_mode}  ({new_broker}:{new_port})")
    stop_mqtt()
    reset_fms_topic_cache()          # factory có thể vừa đổi → tính lại topic presence/LWT

    # Reload registry từ DB trước khi tạo client mới
    try:
        from agv_registry import agv_registry as _reg
        _reg.load_from_db()
        print(f"[MQTT] Registry reloaded: {_reg}")
    except Exception as _re:
        print(f"[MQTT] Registry reload failed: {_re}")

    # Copy _unified_config từ client cũ (factory, manufacturer)
    _old_cfg = getattr(client, "_unified_config", {})

    # Tạo client mới (cần thiết vì TLS phải set trước connect)
    new_client = mqtt.Client(
        client_id=f"server_{uuid.uuid4().hex[:8]}",
        clean_session=True,
    )
    new_client.on_connect    = on_connect
    new_client.on_message    = on_message
    new_client.on_disconnect = on_disconnect
    new_client.socket_timeout = float(os.getenv("MQTT_SOCKET_TIMEOUT_SEC", "5"))
    new_client._unified_config = _old_cfg   # giữ lại config factory/manufacturer
    _configure_client_for_mode(new_client, new_mode)

    client     = new_client
    BROKER     = new_broker
    PORT       = new_port
    MQTT_MODE  = new_mode

    # Gắn lại callbacks Line AGV vào client mới
    try:
        _setup_line_agv_callbacks()
    except Exception:
        pass

    start_mqtt()
    return {"ok": True, "mode": new_mode, "broker": new_broker, "port": new_port}


def get_mqtt_mode() -> dict:
    cfg = _local_broker_cfg()
    return {"mode": MQTT_MODE, "broker": BROKER, "port": PORT,
            # cấu hình broker LOCAL (không trả mật khẩu, chỉ cho biết có hay không)
            "local": {"host": cfg["host"], "port": cfg["port"], "user": cfg["user"],
                      "has_password": bool(cfg["password"])}}


def set_local_broker_config(host: str, port, user: str, password: str | None) -> dict:
    """Lưu địa chỉ + tài khoản broker LOCAL (mqtt_mode.json). password=None → giữ mật khẩu đang lưu; user rỗng → nối
    ẩn danh. Đang ở chế độ local thì kết nối lại ngay theo cấu hình mới, chưa thì chỉ lưu cho lần chuyển sang local."""
    if os.getenv("MQTT_MODE_OVERRIDE", "").strip():
        # server mô phỏng dùng chung mqtt_mode.json với server sản xuất → không được ghi cấu hình thật từ đây
        return {"ok": False, "error": "Server mô phỏng không được đổi cấu hình broker (file dùng chung với server thật)"}
    host = (host or "").strip()
    if not host or len(host) > 253 or not all(ch.isalnum() or ch in ".-_:" for ch in host):
        return {"ok": False, "error": "Địa chỉ broker không hợp lệ (IP hoặc tên máy)"}
    try:
        port = int(port)
        if not 1 <= port <= 65535:
            raise ValueError
    except (TypeError, ValueError):
        return {"ok": False, "error": "Port phải là số từ 1 đến 65535"}
    user = (user or "").strip()

    d = _read_mode_file()
    old = d.get("local") if isinstance(d.get("local"), dict) else {}
    new_pw = (old.get("password") if "password" in old else _local_broker_cfg()["password"]) if password is None else password
    d["local"] = {"host": host, "port": port, "user": user, "password": new_pw if user else ""}
    _write_mode_file(d)
    print(f"[MQTT] Đã lưu cấu hình broker local: {host}:{port} ({'user ' + user if user else 'ẩn danh'})")

    if MQTT_MODE == "local":
        res = switch_mqtt_mode("local")
        res["applied"] = bool(res.get("ok"))
        return res
    return {"ok": True, "applied": False, "mode": MQTT_MODE, "broker": host, "port": port,
            "note": "Đã lưu — sẽ dùng khi chuyển sang chế độ LOCAL"}


def test_broker_connection(host: str, port, user: str, password: str | None, timeout: float = 4.0) -> dict:
    """Thử nối tới broker (không ảnh hưởng kết nối đang chạy của server). password=None → dùng mật khẩu đang lưu.
    Trả {ok, reason, detail}: reason = ok | unreachable | auth | refused."""
    import threading
    host = (host or "").strip()
    try:
        port = int(port)
    except (TypeError, ValueError):
        return {"ok": False, "reason": "refused", "detail": "Port không hợp lệ"}
    user = (user or "").strip()
    if password is None:
        password = _local_broker_cfg()["password"]
    done, result = threading.Event(), {}

    def _on_connect(c, ud, flags, rc, *a):
        result["rc"] = rc
        done.set()

    t = mqtt.Client(client_id=f"cfgtest_{uuid.uuid4().hex[:8]}", clean_session=True)
    if user:
        t.username_pw_set(user, password)
    t.on_connect = _on_connect
    try:
        t.connect_async(host, port, keepalive=10)
        t.loop_start()
        done.wait(timeout)
    except Exception as e:
        return {"ok": False, "reason": "unreachable", "detail": str(e)}
    finally:
        try:
            t.disconnect()
        except Exception:
            pass
        t.loop_stop()
    rc = result.get("rc")
    if rc is None:
        return {"ok": False, "reason": "unreachable",
                "detail": f"Không nối được {host}:{port} trong {int(timeout)}s (sai IP/port, broker chưa chạy, hoặc tường lửa)"}
    if rc == 0:
        return {"ok": True, "reason": "ok", "detail": f"Kết nối thành công tới {host}:{port}"}
    if rc in (4, 5):
        return {"ok": False, "reason": "auth", "detail": "Broker từ chối: sai user/password hoặc không được phép"}
    return {"ok": False, "reason": "refused", "detail": f"Broker từ chối kết nối (mã {rc})"}


# ==========================
# ORDER & ACTION Sending
# ==========================
def send_order(agv_id: str, order: dict):
    from agv_registry import agv_registry
    if agv_registry.is_line(agv_id):
        _send_line_order(agv_id, order)
    else:
        _send_vda5050_order(agv_id, order)


def _send_line_order(agv_id: str, order: dict) -> None:
    """Gửi plan {"c":"plan",...} đến Line AGV qua topic uagv/v2/..."""
    from line_agv_handler import line_agv_handler as _lah_order
    # Sau {"c":"stop"} (cancel/emergency stop), Arduino chuyển về MANUAL và
    # CHỈ quay lại AUTOMATIC khi nhận {"c":"run"} — gửi thẳng plan mới lúc
    # này vẫn được ACK nhưng KHÔNG được thực thi (không tắt Lidar, không
    # chạy động cơ), khiến cảm biến vật cản (chưa tắt) báo vật cản giả dù
    # xe chưa hề nhúc nhích. Tự động "run" khôi phục AUTOMATIC trước khi
    # gửi plan mới nếu phát hiện xe còn đang ở MANUAL từ lần stop trước.
    _st_order = _lah_order.state_store.get(agv_id)
    if _st_order is not None and _st_order.operating_mode == "MANUAL":
        print(f"[MQTT] LINE {agv_id}: đang ở MANUAL (còn sót từ lần stop trước) "
              f"→ gửi 'run' khôi phục AUTOMATIC trước khi gửi plan mới")
        send_line_command(agv_id, "run")
        # QUAN TRỌNG: firmware cần chút thời gian để thực sự chuyển MANUAL→
        # AUTOMATIC sau khi nhận 'run'. Gửi 'plan' NGAY LẬP TỨC (0ms) sau đó
        # vẫn được ACK (rc=0) nhưng KHÔNG được thực thi (xe vẫn ở MANUAL lúc
        # plan tới) — quan sát thực tế: AGV đứng im vô thời hạn hoặc lặp lại
        # chu kỳ arrived_wait_sys→resend plan hàng chục lần liên tục (~90s)
        # mà không tiến được bước nào. Chờ ngắn ở đây để plan chắc chắn tới
        # SAU khi firmware đã chuyển hẳn sang AUTOMATIC.
        time.sleep(0.3)
    # Backend thang uelev_v2: nối ĐUÔI plan (cabin → lùi ra → thẻ thoát) cho xe sắp vào cabin — xe mất mạng
    # khi cabin đóng cửa nên không nhận thêm plan (07-tich-hop-fms.md §3.1).
    try:
        from elevator_coordinator import elevator_coordinator as _ec_t
        order = _ec_t.plan_tail(agv_id, order) or order
    except Exception as _e_t:
        print(f"[ELEVATOR] nối đuôi plan lỗi: {_e_t}")
    # Xe offline / state cũ / server mất broker → GIỮ plan (09-ack-lenh-fms.md §1): publish lúc này rơi hẳn và
    # (nếu xe đang đứng ở thẻ đầu plan) cơ chế gửi lại theo ACK còn tưởng plan đã tới. Có state mới → flush_held_plan.
    if not _line_agv_available(agv_id):
        _hold_line_plan(agv_id, order)
        return
    _HELD_PLANS.pop(agv_id, None)           # plan mới thay plan đang giữ
    _publish_line_order(agv_id, order)


# Plan chờ gửi cho xe đang offline: {agv_id: {"order", "tag" (thẻ xe lúc giữ), "held_at"}} — mỗi xe tối đa 1 (plan mới đè)
_HELD_PLANS: dict = {}


def _publish_line_order(agv_id: str, order: dict) -> None:
    try:
        from line_agv_handler import line_agv_handler as _lah_pc
        _st_pc = _lah_pc.state_store.get(agv_id)
        if _st_pc is not None:
            _st_pc.position_confirmed_tag = None        # plan mới = xe sắp di chuyển → vị trí không còn chắc chắn
    except Exception:
        pass
    topic       = _line_agv_topic(agv_id, "order")
    payload_str = json.dumps(order, ensure_ascii=False)
    result      = client.publish(topic, payload_str, qos=1)
    cmd_id      = order.get("id", "")
    if result.rc != 0:
        print(f"[MQTT][WARN] LINE order FAILED agv={agv_id} rc={result.rc}")
    print(f"[MQTT] LINE plan → {agv_id} | id={cmd_id} | steps={len(order.get('d', []))} | rc={result.rc}")
    print(f"[MQTT] LINE payload: {payload_str}")
    from line_agv_handler import line_agv_handler
    line_agv_handler.record_sent_cmd(agv_id, cmd_id, order)
    try:
        line_agv_handler.arm_standing_turn(agv_id, order)
    except Exception as _e_arm:
        print(f"[MQTT] arm rẽ tại chỗ lỗi: {_e_arm}")


def _hold_line_plan(agv_id: str, order: dict) -> None:
    from line_agv_handler import line_agv_handler as _h
    st = _h.state_store.get(agv_id)
    tag = None if (st is None or st.current_tag is None) else str(st.current_tag)
    first = agv_id not in _HELD_PLANS
    _HELD_PLANS[agv_id] = {"order": order, "tag": tag, "held_at": time.time()}
    # Vẫn ghi route.sent_cmd_id để đối chiếu lúc flush (route đã bị thay/huỷ thì bỏ plan giữ)
    _h.record_sent_cmd(agv_id, order.get("id", ""), order)
    if first:                               # chỉ log khi đổi trạng thái
        print(f"[PLAN_HOLD] {agv_id}: offline — GIỮ plan id={order.get('id')} ({len(order.get('d', []))} bước), "
              f"gửi bù khi có state mới")


def flush_held_plan(agv_id: str) -> bool:
    """Gọi mỗi khi nhận state của xe: gửi bù plan đang giữ (với id MỚI — §2.1) nếu xe đã khả dụng lại. Bỏ plan giữ
    nếu route đã bị thay/huỷ, hoặc xe đã đổi thẻ khi offline (plan cũ tính từ vị trí khác — để cơ chế gửi lại/kẹt
    dựng lại theo vị trí thật). True = đã gửi."""
    h = _HELD_PLANS.get(agv_id)
    if h is None or not _line_agv_available(agv_id):
        return False
    _HELD_PLANS.pop(agv_id, None)
    from line_agv_handler import line_agv_handler as _h
    route = _h._routes.get(agv_id)
    order = dict(h["order"])
    if route is None or route.sent_cmd_id != order.get("id"):
        print(f"[PLAN_HOLD] {agv_id}: plan giữ id={order.get('id')} đã bị thay/huỷ — bỏ")
        return False
    st = _h.state_store.get(agv_id)
    cur = None if (st is None or st.current_tag is None) else str(st.current_tag)
    if h["tag"] is not None and cur != h["tag"]:
        print(f"[PLAN_HOLD] {agv_id}: xe đã đổi thẻ {h['tag']}→{cur} khi offline — bỏ plan giữ id={order.get('id')} "
              f"(dựng lại theo vị trí thật)")
        return False
    order["id"] = uuid.uuid4().hex[:8]
    print(f"[PLAN_HOLD] {agv_id}: online lại — gửi bù plan (id mới {order['id']})")
    _publish_line_order(agv_id, order)
    return True


def _send_vda5050_order(agv_id: str, order: dict) -> None:
    payload_str = json.dumps(order, ensure_ascii=False)
    results = []
    for topic in _publish_topic_candidates(agv_id, "order"):
        result = client.publish(topic, payload_str, qos=1)
        results.append((topic, result.rc))
    rc = results[-1][1] if results else -1
    if rc != 0:
        print(f"[MQTT][WARN] publish order FAILED agv={agv_id} rc={rc} — client connected={client.is_connected()}")
    print(f"[MQTT] ĐÃ GỬI order → {agv_id} | orderId={order.get('orderId')} | status={rc} | topics={[t for t,_ in results]}")


def send_line_command(agv_id: str, cmd: str, **kwargs) -> bool:
    """
    Gửi lệnh tức thì cho Line AGV qua topic uagv/v2/.../instantActions.
    cmd: "stop" | "run" | "reset" | "battery_unlock" | "ack_event" | ...
    kwargs: tham số bổ sung, VD: d="confirm", v=150, p="fwd"
    """
    # run/stop đi qua kênh có xác nhận theo ID (09-ack-lenh-fms.md): giữ lệnh khi xe offline
    # (vào thang mất Wi-Fi), gửi lặp cùng id tới khi state.cmd_ack khớp. Lệnh khác gửi thẳng.
    if cmd in ("stop", "reset"):
        _HELD_PLANS.pop(agv_id, None)       # dừng/reset: plan đang giữ không còn hiệu lực
    if cmd in ("stop", "reset", "deba"):
        try:
            from line_agv_handler import line_agv_handler as _lah_pc2
            _st_pc2 = _lah_pc2.state_store.get(agv_id)
            if _st_pc2 is not None:
                _st_pc2.position_confirmed_tag = None   # dừng giữa đường/chạy dò → thẻ có thể lệch vị trí thật
        except Exception:
            pass
    if cmd in _agv_cmd_channel_mod.ACK_CMDS and not kwargs:
        return _agv_cmd_channel.send(agv_id, cmd)
    payload = {"c": cmd}
    payload.update(kwargs)
    return _publish_line_instant(agv_id, payload)


def _publish_line_instant(agv_id: str, payload: dict) -> bool:
    topic = _line_agv_topic(agv_id, "instantActions")
    result = client.publish(topic, json.dumps(payload, ensure_ascii=False), qos=1)
    print(f"[LINE_CMD] → {agv_id}: {payload} | rc={result.rc}")
    return result.rc == 0


def _line_agv_available(agv_id: str) -> bool:
    """Xe khả dụng để nhận lệnh: server còn kết nối broker VÀ xe ONLINE với state còn mới (≤5 s).
    Xe chưa từng có state (server vừa khởi động) → coi là khả dụng, gửi thử như trước đây."""
    try:
        if not client.is_connected():
            return False        # chính server mất broker: không phải lỗi của xe → giữ lệnh, không đốt lượt gửi
        from line_agv_handler import line_agv_handler as _h
        st = _h.state_store.get(agv_id)
        if st is None or st.last_update <= 0:
            return True
        if st.connection_state in ("OFFLINE", "CONNECTIONBROKEN"):
            return False
        return (time.time() - st.last_update) <= _agv_cmd_channel_mod.STATE_STALE_S
    except Exception:
        return True


import agv_cmd_channel as _agv_cmd_channel_mod
_agv_cmd_channel = _agv_cmd_channel_mod.agv_cmd_channel
def _on_line_cmd_expired(agv_id: str, cmd: str) -> None:
    """`run`/`stop` hết lượt gửi mà xe không báo cmd_ack → cảnh báo lên map/UI (xe có thể không nhận lệnh)."""
    try:
        from line_agv_handler import line_agv_handler as _h
        _h._set_alert(agv_id, None, "CMD_NOT_ACKED",
                      f"Xe {agv_id} không xác nhận lệnh '{cmd}' sau {_agv_cmd_channel_mod.MAX_SENDS} lần gửi "
                      f"— kiểm tra mạng/firmware")
    except Exception as e:
        print(f"[CMD_ACK] cảnh báo CMD_NOT_ACKED lỗi: {e}")


def _on_line_cmd_acked(agv_id: str, cmd: str) -> None:
    """Xe xác nhận lại lệnh → hết cảnh báo CMD_NOT_ACKED (nếu đang treo)."""
    try:
        from line_agv_handler import line_agv_handler as _h
        _h._clear_alert(_h.state_store.get(agv_id), "CMD_NOT_ACKED")
    except Exception:
        pass


_agv_cmd_channel.configure(publish=_publish_line_instant, is_available=_line_agv_available,
                           on_expired=_on_line_cmd_expired, on_acked=_on_line_cmd_acked)


def send_gate_command(door_id: str, cmd: str) -> bool:
    """
    Gửi lệnh mở/đóng tới bộ điều khiển cửa tự động.
    cmd: "open" | "close" — xem PROTOCOL_GUIDE.md mục "Cửa tự động (Gate Controller)".
    Topic: gate/v1/{factory}/{door_id}/cmd

    Cửa không gắn với 1 AGV cụ thể nên không có agv_id để tra agv_registry trực
    tiếp — nhưng LINE_AGV_FACTORY (biến môi trường) THƯỜNG rỗng (chỉ là fallback
    dự phòng), factory THẬT của từng AGV được lưu RIÊNG trong DB (agv_devices.
    factory, đọc qua agv_registry.get_factory(agv_id)) — vd "Vonhai". Vì 1 server
    local chỉ phục vụ ĐÚNG 1 nhà máy (kiến trúc cloud gateway: mỗi nhà máy 1
    server riêng), lấy factory của BẤT KỲ AGV nào đã đăng ký làm factory dùng
    chung cho cửa là chính xác — tránh việc rơi về "VietDuc" sai be bét như đã
    xảy ra thực tế (nhà máy cấu hình "Vonhai" nhưng cửa gửi nhầm "VietDuc").
    """
    from unified_mqtt import LINE_AGV_FACTORY
    factory = None
    try:
        from agv_registry import agv_registry
        factory = agv_registry.get_default_factory(default="")
    except Exception as _e_fac:
        print(f"[GATE_CMD] tra factory từ agv_registry lỗi: {_e_fac}")
    factory = factory or LINE_AGV_FACTORY or "VietDuc"
    topic = f"{GATE_INTERFACE_NAME}/{GATE_MQTT_VERSION}/{factory}/{door_id}/cmd"
    payload = {"c": cmd}
    result = client.publish(topic, json.dumps(payload, ensure_ascii=False), qos=1)
    print(f"[GATE_CMD] → {door_id}: {payload} | rc={result.rc}")
    return result.rc == 0


def send_elevator_command(elevator_id: str, cmd: str, floor=None, quiet: bool = False) -> bool:
    """
    Gửi lệnh tới bộ điều khiển thang máy. cmd: "open" (kèm floor = số tầng: đi tới tầng đó rồi mở cửa)
    | "close". Topic: elevator/v1/{factory}/{elevator_id}/cmd — xem PROTOCOL_GUIDE.md mục 17.
    Factory lấy giống send_gate_command (1 server local phục vụ đúng 1 nhà máy).
    """
    from unified_mqtt import LINE_AGV_FACTORY
    factory = None
    try:
        from agv_registry import agv_registry
        factory = agv_registry.get_default_factory(default="")
    except Exception as _e_fac:
        print(f"[ELEVATOR_CMD] tra factory từ agv_registry lỗi: {_e_fac}")
    factory = factory or LINE_AGV_FACTORY or "VietDuc"
    topic = f"{ELEVATOR_INTERFACE_NAME}/{ELEVATOR_MQTT_VERSION}/{factory}/{elevator_id}/cmd"
    payload = {"c": cmd}
    if floor is not None:
        payload["floor"] = floor
    result = client.publish(topic, json.dumps(payload, ensure_ascii=False), qos=1)
    if not quiet:   # quiet: lệnh giữ cửa gửi lặp định kỳ — không in log mỗi lần
        print(f"[ELEVATOR_CMD] → {elevator_id}: {payload} | rc={result.rc}")
    return result.rc == 0


def send_instant_action(agv_id: str, action_type: str):
    from agv_registry import agv_registry
    if agv_registry.is_line(agv_id):
        return _send_line_instant(agv_id, action_type)
    return _send_vda5050_instant(agv_id, action_type)


def _send_line_instant(agv_id: str, action_type: str) -> bool:
    """Dịch VDA5050 action_type sang lệnh Line AGV tương đương."""
    action = (action_type or "").upper().strip()
    _cmd_map = {
        "PAUSE":  "stop",
        "RESUME": "run",
        "CANCEL": "stop",
    }
    cmd = _cmd_map.get(action)
    if not cmd:
        print(f"[LINE_CMD] action '{action}' không hỗ trợ cho Line AGV")
        return False
    return send_line_command(agv_id, cmd)


def _send_vda5050_instant(agv_id: str, action_type: str) -> bool:
    action = (action_type or "").upper().strip()

    if action == "PICK":
        action = "PICKUP"

    allowed_actions = ["PAUSE", "RESUME", "PICKUP", "CANCEL"]
    if action not in allowed_actions:
        print(f"[MQTT] Hành động không hợp lệ: {action}")
        return False

    cooldown_key = (str(agv_id), action)
    now_ts = time.time()
    if action in {"PAUSE", "RESUME"}:
        last_sent = _last_instant_action_sent.get(cooldown_key, 0.0)
        if now_ts - last_sent < INSTANT_ACTION_COOLDOWN_SEC:
            return True

    agv_state = agv_manager.get_agv(agv_id) or {}
    manufacturer = agv_state.get("manufacturer") or "TNG:TOT"
    serial_number = agv_state.get("serialNumber") or agv_id

    action_msg = {
        "headerId": int(time.time() * 1000),
        "timestamp": datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "version": "3.0.0",
        "manufacturer": manufacturer,
        "serialNumber": serial_number,
        "actions": [{
            "actionId": str(uuid.uuid4()),
            "actionType": action,
            "blockingType": "HARD",
            "actionParameters": []
        }]
    }

    stale_action_ids = [
        action_id
        for action_id, ts in _recent_published_action_ids.items()
        if now_ts - ts > 10.0
    ]
    for action_id in stale_action_ids:
        _recent_published_action_ids.pop(action_id, None)

    for item in action_msg.get("actions") or []:
        action_id = str(item.get("actionId") or "").strip()
        if action_id:
            _recent_published_action_ids[action_id] = now_ts
    _last_instant_action_sent[cooldown_key] = now_ts

    payload = json.dumps(action_msg, ensure_ascii=False)
    results = []
    # Try publish with small retry/backoff to improve reliability in lossy networks
    for topic in _publish_topic_candidates(agv_id, "instantActions"):
        published = False
        last_rc = None
        attempts = 0
        while not published and attempts < 3:
            try:
                info = client.publish(topic, payload, qos=1)
                last_rc = getattr(info, "rc", None)
                # wait a short time for the client to complete publish
                try:
                    info.wait_for_publish(timeout=2.0)
                except Exception:
                    pass
                # Consider published if info reports success or client confirms
                published = getattr(info, "is_published", lambda: False)() if hasattr(info, "is_published") else (last_rc == 0)
            except Exception as e:
                print(f"[MQTT] publish error for topic={topic}: {e}")
                published = False
            if not published:
                attempts += 1
                time.sleep(0.15 * attempts)
        results.append((topic, 0 if published else (last_rc or 1)))

    print(f"[MQTT] ĐÃ GỬI instantAction → {agv_id}: {action}")
    print(f"[MQTT] Topics: {results}")
    print(json.dumps(action_msg, indent=2, ensure_ascii=False))

    return any(rc == 0 for _, rc in results)


def _send_traffic_control_action(agv_id: str, action_type: str) -> bool:
    action = str(action_type or "").upper().strip()
    if not action:
        return False

    if _last_traffic_control_action.get(agv_id) == action:
        return True

    sent = send_instant_action(agv_id, action)
    if sent:
        _last_traffic_control_action[agv_id] = action
    return sent


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
    Hủy lệnh hiện tại của AGV.
    LINE AGV: gửi lệnh stop qua send_line_command.
    VDA5050: gửi instant action CANCEL.
    """
    from agv_registry import agv_registry

    if agv_registry.is_line(agv_id):
        from line_agv_handler import line_agv_handler
        ok = send_line_command(agv_id, "stop")
        line_agv_handler.clear_route(agv_id)
        removed_pending = _pending_drop_orders.pop(agv_id, None) is not None
        print(f"[CANCEL] LINE AGV={agv_id} | stop sent={ok} | removed_pending={removed_pending}")
        return {
            "success": ok,
            "agv_id": agv_id,
            "cancelled_order_id": "",
            "removed_pending_drop": removed_pending,
        }

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
