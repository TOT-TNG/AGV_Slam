"""
unified_main.py — Entry point cho toàn bộ AGVmqtt
--------------------------------------------------
Chạy đồng thời:
  • Line AGV system : MQTT v2 + traffic engine (WHCA*, RollingRePlanner, EdgeReservation)
  • VDA5050 system  : FastAPI + MQTT v3 (từ mqtt_Server/)

Usage:
  cd C:\\Users\\Admin\\Desktop\\AGVmqtt
  python unified_main.py

Cấu hình chính: agv_vda5050_simulator/config/simulator.json
  - Thêm "agv_type": "LINE" vào AGV nào là line từ
  - Các AGV còn lại (SLAM, QR, ...) sẽ được xử lý theo VDA5050

Line AGV MQTT settings: AGV_NewVersion - Copy/.../config/settings.json
VDA5050 FastAPI  : http://0.0.0.0:8000
"""
from __future__ import annotations

import sys
import os
import threading
import time
import json
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT_DIR    = Path(__file__).resolve().parent
MQTT_SERVER = ROOT_DIR / "mqtt_Server"
LINE_MGR    = ROOT_DIR / "AGV_NewVersion - Copy" / "AGV_NewVersion - Copy" / "python-manager"

# mqtt_Server phải là đầu tiên để 'import main' tìm thấy mqtt_Server/main.py
for _p in (str(MQTT_SERVER), str(LINE_MGR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ── Load config từ simulator.json ─────────────────────────────────────────────
_cfg_path = ROOT_DIR / "agv_vda5050_simulator" / "config" / "simulator.json"
with open(_cfg_path, encoding="utf-8") as _f:
    _sim = json.load(_f)

_mqtt_cfg     = _sim.get("mqtt", {})
_factory      = _mqtt_cfg.get("interface_name", "uagv")
_manufacturer = _sim.get("manufacturer", "tot")
_all_agv_cfgs = _sim.get("agvs", [])

# ── Đọc MQTT mode (local / cloud) từ mqtt_mode.json ──────────────────────────
_CLOUD_BROKER = "iot.tot360.com.vn"
_CLOUD_PORT   = 8883
_CLOUD_USER   = "iot_user"
_CLOUD_PASS   = "d7xvk5pKkqsKKMd"
_MODE_FILE    = ROOT_DIR / "mqtt_Server" / "mqtt_mode.json"

def _read_mode() -> str:
    try:
        if _MODE_FILE.exists():
            with open(_MODE_FILE) as _mf:
                return json.load(_mf).get("mode", "local")
    except Exception:
        pass
    return os.environ.get("MQTT_MODE", "local").lower()

_mqtt_mode = _read_mode()
if _mqtt_mode == "cloud":
    _broker = _CLOUD_BROKER
    _port   = _CLOUD_PORT
    print(f"[UNIFIED] MQTT mode=cloud → {_CLOUD_BROKER}:{_CLOUD_PORT}")
else:
    _broker = _mqtt_cfg.get("host", _mqtt_cfg.get("broker", "localhost"))
    _port   = int(_mqtt_cfg.get("port", 1883))
    print(f"[UNIFIED] MQTT mode=local → {_broker}:{_port}")

# Phân loại AGV: agv_type == "LINE" → Line AGV, còn lại → VDA5050
_line_cfgs = [a for a in _all_agv_cfgs if str(a.get("agv_type", "")).upper() == "LINE"]
_vda_cfgs  = [a for a in _all_agv_cfgs if str(a.get("agv_type", "")).upper() != "LINE"]

# ── Init AGV registry (dùng chung cho cả 2 hệ thống) ─────────────────────────
from agv_registry import agv_registry
agv_registry.load_from_config(_all_agv_cfgs)

# Báo mqtt_Server KHÔNG subscribe v2 topics (unified_main xử lý riêng)
os.environ["LINE_AGV_MQTT_EXTERNAL"] = "1"

print(f"[UNIFIED] AGV registry: {agv_registry}")
print(f"[UNIFIED] Line AGVs: {[a.get('agv_id') for a in _line_cfgs]}")
print(f"[UNIFIED] VDA5050 AGVs: {[a.get('agv_id') for a in _vda_cfgs]}")

# ══════════════════════════════════════════════════════════════════════════════
# LINE AGV SUBSYSTEM
# ══════════════════════════════════════════════════════════════════════════════

_line_agvs: list = []
_line_ctx = None

if _line_cfgs:
    # Chuyển cwd sang thư mục python-manager vì config dùng đường dẫn tương đối
    _saved_cwd = os.getcwd()
    os.chdir(str(LINE_MGR))

    try:
        # ── Load Line AGV config (settings.json) ──────────────────────────────
        from config_mgmt.settings_io import load_config as _load_line
        _line_cfg = _load_line()

        # MQTT broker từ simulator.json (ưu tiên) hoặc settings.json
        _line_broker = _broker
        _line_port   = _port
        _line_factory = _factory  # dùng interface_name từ simulator.json

        # ── Khởi tạo AppContext và các subsystem ──────────────────────────────
        from core.context              import AppContext
        from traffic.planner           import Planner
        from traffic.reservation       import ZoneManager
        from traffic.conflict_manager  import WHCAPlanner, RollingRePlanner
        from traffic.fleet_state       import FleetStateManager
        from traffic.edge_reservation  import EdgeReservationManager
        from agv.workflow_engine       import WorkflowEngine
        from dispatch.request_handler  import RequestHandler
        from dispatch.scheduler        import Scheduler

        _line_ctx             = AppContext(config=_line_cfg)
        _line_ctx.planner     = Planner("config/map_data.json")
        _zones = "config/zones.json"
        _line_ctx.zone_mgr    = ZoneManager(_zones if os.path.exists(_zones) else "")
        _line_ctx.whca        = WHCAPlanner(_line_ctx, lookahead=_line_cfg.get("lookahead", 6))
        _line_ctx.replanner   = RollingRePlanner(_line_ctx)
        _line_ctx.fleet_state = FleetStateManager(_line_ctx)
        _line_ctx.edge_mgr    = EdgeReservationManager()
        _line_ctx.workflow_engine = WorkflowEngine("config/tag_actions.json")
        _line_ctx.request_handler = RequestHandler(_line_ctx)
        _line_ctx.scheduler   = Scheduler(_line_ctx)

        # ── Tạo MQTT client riêng cho Line AGV (v2) ───────────────────────────
        import paho.mqtt.client as _paho
        _line_mqtt = _paho.Client(_paho.CallbackAPIVersion.VERSION1, "LineAGV_Manager")
        _line_ctx.mqtt = _line_mqtt

        # ── Tạo AGV instances từ simulator.json (LINE entries) ────────────────
        from agv.agv_instance import AGV as _LineAGV

        for _cfg in _line_cfgs:
            # Chuyển key agv_id → id (AGV class dùng config['id'])
            _agv_cfg = {
                **_cfg,
                "id":       str(_cfg.get("agv_id") or _cfg.get("id") or ""),
                "factory":  _line_factory,
                "hardware": _line_cfg.get("hardware", "hardware"),
            }
            _agv_obj = _LineAGV(_agv_cfg, _line_mqtt)
            _agv_obj.app_config = _line_cfg
            _agv_obj.zone_mgr   = _line_ctx.zone_mgr
            _agv_obj.edge_mgr   = _line_ctx.edge_mgr
            _line_ctx.agv_list.append(_agv_obj)
            _line_agvs.append(_agv_obj)

        print(f"[LINE_AGV] Khởi tạo {len(_line_agvs)} Line AGV(s): "
              f"{[a.id for a in _line_agvs]}")

        # ── Wire line_agv_handler → AGV.update_state() ────────────────────────
        # line_agv_handler (trong mqtt_Server) parse state v2 và gọi callback này
        from line_agv_handler import line_agv_handler
        _agv_lookup: dict[str, _LineAGV] = {a.id: a for a in _line_agvs}

        def _on_line_state_changed(state):
            agv = _agv_lookup.get(state.agv_id)
            if not agv:
                return
            try:
                payload = {
                    "lastNodeId":    str(state.current_tag),
                    "prev_tag":      state.prev_tag,
                    "driving":       state.driving,
                    "paused":        state.paused,
                    "battery":       state.battery,
                    "operatingMode": state.operating_mode,
                    "ack":           state.last_ack,
                }
                agv.update_state(payload)
            except Exception as _e:
                print(f"[LINE_AGV] update_state error ({state.agv_id}): {_e}")

        line_agv_handler.on_state_changed = _on_line_state_changed

        # ── Cấu hình MQTT on_connect / on_message cho Line AGV ────────────────
        _LINE_VER = os.getenv("LINE_AGV_MQTT_VERSION", "v2")

        def _line_on_connect(client, userdata, flags, rc):
            if rc == 0:
                print(f"[LINE_AGV] MQTT connected → {_line_broker}:{_line_port}")
                # Dùng wildcard '+' cho factory để nhận từ tất cả các AGV Line
                # bất kể factory name (VietDuc, TNG, ...) được cấu hình trong DB
                for _kind in ("state", "connection"):
                    _topic = f"uagv/{_LINE_VER}/+/+/{_kind}"
                    client.subscribe(_topic, qos=0)
                    print(f"[LINE_AGV] Subscribed: {_topic}")
            else:
                print(f"[LINE_AGV] MQTT connect failed rc={rc}")

        def _line_on_message(client, userdata, msg):
            try:
                _parts = msg.topic.split("/")
                if len(_parts) == 5:
                    _agv_id = _parts[3]
                    _kind   = _parts[4]
                    _payload_str = msg.payload.decode("utf-8", errors="replace")
                    line_agv_handler.dispatch(_agv_id, _kind, _payload_str)
            except Exception as _e:
                print(f"[LINE_AGV] on_message error: {_e}")

        _line_mqtt.on_connect = _line_on_connect
        _line_mqtt.on_message = _line_on_message

        # ── Kết nối broker (TLS nếu mode=cloud) ──────────────────────────────
        try:
            if _mqtt_mode == "cloud":
                import ssl as _ssl
                _line_mqtt.username_pw_set(_CLOUD_USER, _CLOUD_PASS)
                _line_mqtt.tls_set(cert_reqs=_ssl.CERT_NONE)
                _line_mqtt.tls_insecure_set(True)
                print(f"[LINE_AGV] TLS+auth configured for cloud broker")
            _line_mqtt.connect(_line_broker, _line_port, keepalive=60)
            _line_mqtt.loop_start()
        except Exception as _e:
            print(f"[LINE_AGV] MQTT connect failed: {_e}")
            print(f"[LINE_AGV] Tiếp tục không có MQTT (traffic engine vẫn chạy)")

        # ── Traffic loop (WHCA* + RollingRePlanner + ZoneManager) ─────────────
        def _traffic_loop():
            print("[LINE_AGV] Traffic loop bắt đầu (interval=500ms)")
            while True:
                try:
                    if _line_ctx.whca:
                        _line_ctx.whca.tick()
                    if _line_ctx.replanner:
                        _line_ctx.replanner.tick()
                    if _line_ctx.zone_mgr:
                        _line_ctx.zone_mgr.tick()
                except Exception as _e:
                    print(f"[LINE_AGV] Traffic loop error: {_e}")
                time.sleep(0.5)

        _t = threading.Thread(target=_traffic_loop, daemon=True, name="LineAGV-Traffic")
        _t.start()

    finally:
        os.chdir(_saved_cwd)  # Khôi phục cwd để FastAPI hoạt động đúng

else:
    print("[UNIFIED] Không có Line AGV nào trong config — bỏ qua Line AGV subsystem")


# ══════════════════════════════════════════════════════════════════════════════
# VDA5050 FastAPI SERVER
# ══════════════════════════════════════════════════════════════════════════════

print("\n[VDA5050] Khởi động FastAPI server tại http://0.0.0.0:8000 ...")
print("[VDA5050] Nhấn Ctrl+C để thoát\n")

import uvicorn
import main as _vda_main   # mqtt_Server/main.py (đã có trong sys.path)

uvicorn.run(
    _vda_main.app,
    host="0.0.0.0",
    port=8000,
    log_level="info",
)
