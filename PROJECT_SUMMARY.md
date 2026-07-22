# Tóm tắt Project: AGVmqtt — TOT ACS

**Ngày tổng hợp:** 2026-06-19  
**Tên hệ thống:** TOT ACS (AGV Control System)  
**Phiên bản giao thức:** VDA5050 v2.0 + Line AGV Protocol (RFID-based)

---

## 1. Tổng quan

TOT ACS là hệ thống điều phối robot vận chuyển tự động (AGV) trong nhà máy/kho vận.  
Hệ thống quản lý **hai loại AGV** hoàn toàn khác nhau song song:

| Loại | Protocol | Phần cứng | Path planning |
|------|----------|-----------|---------------|
| **VDA5050 AGV** (SLAM) | VDA5050 v2.0 qua MQTT | WiFi trực tiếp | Graph + A*/Dijkstra |
| **Line AGV** (RFID) | Custom JSON qua MQTT | ESP32-C5 → UART → Arduino Mega | RFID tag sequence + sliding window |

**Stack kỹ thuật:**
- **Backend API:** FastAPI (port 8000) + asyncpg (PostgreSQL connection pool)
- **Web UI:** Plotly Dash (port 8050) + HTML/CSS/JS thuần nhúng qua iframe
- **MQTT:** paho-mqtt, hỗ trợ Local broker (1883) và Cloud broker `iot.tot360.com.vn` (TLS 8883)
- **Database:** PostgreSQL — tên DB: `TOT_AGV`, user: `postgres`
- **Ngôn ngữ UI:** Tiếng Việt (mặc định) + Tiếng Anh (i18n)

**Server IP mặc định:** `192.168.0.200` (local broker, FastAPI)

---

## 2. Cấu trúc thư mục

```
AGVmqtt/
├── mqtt_Server/          ← Backend chính (FastAPI + MQTT + Traffic engine)
├── Web_UI/               ← Giao diện Dash (Python)
├── agv_vda5050_simulator/ ← Simulator VDA5050 (Pygame)
├── maps/                 ← Ảnh bản đồ PNG
├── unified_main.py       ← Entry point chạy toàn bộ hệ thống
├── PROTOCOL_GUIDE.md     ← Tài liệu giao thức Line AGV (ESP32/Arduino)
├── DESIGN_REQUIREMENTS.md ← Tài liệu yêu cầu thiết kế UI
└── .venv/                ← Python virtual environment
```

---

## 3. mqtt_Server — Backend chính

### 3.1 Entry point & API

**`main.py`** — FastAPI app + khởi tạo toàn hệ thống
- Khởi tạo `TrafficEngine` (singleton)
- Đăng ký `EdgeCoordinator` (điều phối khóa edge đơn giản)
- Gắn router `map_configure_api`
- Expose các endpoint: `/order`, `/action`, `/pick`, `/agv/list`, `/agv/cancel`, `/AgvMap.html`, `/logs`, v.v.
- WebSocket broadcast pose AGV real-time
- Tích hợp `asyncpg` pool (PostgreSQL) qua `lifespan`

**`model.py`** — Pydantic schema
- `MoveCommand`, `ActionRequest`, `PickRequest`
- `MapNode`, `MapEdge`, `MapUploadFullJson` (upload bản đồ dạng JSON + base64 ảnh)

**`order_builder.py`** — Xây dựng VDA5050 order packet
- Hàm `build_order()`: tạo JSON order với `nodes[]` + `edges[]` theo spec VDA5050

### 3.2 MQTT Client

**`mqtt_client.py`** — Kết nối MQTT + publish/subscribe
- Hỗ trợ 2 mode: `local` (1883) và `cloud` (TLS 8883, `iot.tot360.com.vn`)
- Mode được lưu trong `mqtt_mode.json`, toggle qua API
- Subscribe các topic: `vda5050/+/+/state`, `uagv/+/+/state`, `line/#`
- Publish order, instantActions, speed commands
- `REROUTE_APPLY_HOLD_SEC = 8.0` — delay apply reroute sau khi tính xong
- Hằng số cấu hình qua env: `MQTT_QOS`, `MQTT_BROKER`, `MQTT_PORT`, `UAGV_INTERFACE_NAME`

### 3.3 Traffic Engine (Dual Engine Architecture)

#### TrafficEngine — `traffic_core.py` (~7400 dòng)
Engine chính điều phối toàn bộ giao thông VDA5050:

| Thành phần | Mô tả |
|-----------|-------|
| `TrafficEngine` | Class chính — reservation arbitration, winner selection |
| `TopologyMap` | Đồ thị bản đồ (nodes + edges + zones) |
| `_MapContext` | Cầu nối giữa TrafficEngine và StateManagementEngine (~line 2596) |
| A*/Dijkstra | Path planning với dynamic rerouting |
| Wait-graph DFS | Phát hiện deadlock |

**Enums quan trọng:**
- `TrafficState`: IDLE / MOVING / WAITING / BLOCKED / REROUTING / STOPPED
- `ConflictType`: HEAD_ON / SAME_DIRECTION_BLOCKAGE / INTERSECTION_CONFLICT / DEADLOCK_LOOP / ...
- `TrafficAction`: PROCEED / WAIT / SLOW_DOWN / STOP / REROUTE
- `RerouteStrategy`: SPEED_ONLY / LOCAL_REROUTE / FULL_REROUTE

**Winner selection priority tuple:** `(mission_rank, health_rank+boost, route_lock_order, agv_id)` — giá trị nhỏ hơn = ưu tiên cao hơn

#### StateManagementEngine — `state_management.py` (~800 dòng)
Engine dự báo bổ sung:
- Horizon dự báo 8 giây
- `OccupancyWindow` — phát hiện overlap quỹ đạo
- Đề xuất tốc độ: PROCEED / SLOW_DOWN / WAIT
- Phân loại conflict: NODE / EDGE_SAME_DIRECTION / EDGE_HEAD_ON / EDGE_MERGE

**Luồng xử lý chính:**
```
/order endpoint → plan route → activate_route
→ evaluate_map_controls() [per AGV telemetry cycle]
→ _evaluate_agv_locked()
→ conflict resolution
→ MQTT publish order / speed command
```

### 3.4 Line AGV System

**`line_agv_handler.py`** — Handler cho Line AGV (RFID-based)
- Parse state từ MQTT (`lastNodeId`, `prev_tag`, `ack`, `driving`, `battery`, v.v.)
- Tích hợp với VDA5050 traffic: `_line_blocked_edges` (edge AGV line đang chiếm)
- Phát hiện xung đột chủ động: `TRAFFIC_LOOKAHEAD = 6 node`
- Head-on standoff: `HEADON_STANDOFF = 2 node` — dừng cách xa điểm tranh chấp
- Cơ chế lùi nhường đường với `BACKUP_COOLDOWN = 30s`
- Reroute obstacle với `REROUTE_COOLDOWN = 18s` (chống dao động)
- Offline timeout: `OFFLINE_TIMEOUT_SEC = 30s`

**`line_agv_plan_builder.py`** — Xây plan cho Line AGV
- Plan dạng `{"c":"plan","id":"...","d":[...]}`
- Sliding window `LOOKAHEAD = 4 node` (tránh tràn UART buffer Arduino 128B)
- Cuối cửa sổ trung gian dùng `WAIT_SYS` để server tiếp tục dispatch
- Retry ACK timeout: `RETRY_TIMEOUT = 4.0s`

**Action codes (khớp với Arduino firmware):**

| Code | Tên | Ý nghĩa |
|------|-----|---------|
| 1 | WAIT_SYS | Dừng chờ hệ thống |
| 3 | RUN | Chạy thẳng |
| 4 | SPEED | Đặt tốc độ (0-255) |
| 5 | TURN_R | Rẽ phải 90° |
| 6 | TURN_L | Rẽ trái 90° |
| 7 | DIR_FWD | Chiều tiến |
| 8 | DIR_BWD | Chiều lùi |
| 20 | LIDAR_OFF | Tắt cảm biến vật cản (bắt buộc trước TURN) |
| 21 | LIDAR_ON | Bật cảm biến vật cản |
| 35 | WAIT_CHARGE | Đến trạm sạc |

**Tốc độ mặc định:** FAST=120, SLOW=60, STOP=30 (Arduino byte, hệ số 240)

### 3.5 Quản lý trạng thái & hàng chờ

**`agv_manager.py`** — AGV state store (in-memory, thread-safe)
- Cập nhật trạng thái qua MQTT (`update_status`)
- `last_seen_mono` (monotonic) cho phát hiện offline
- Lưu `currentOrderId`, `currentOrderUpdateId`, `pending_path`

**`agv_registry.py`** — Registry phân loại AGV
- Load từ DB (`agv_devices`)
- `slam*` → VDA5050; còn lại (tow/carry/trailer) → LINE
- Index phụ: `ip_str → agv_id`

**`task_queue.py`** — Hàng chờ lệnh per-AGV
- Mỗi AGV có 1 `deque` riêng
- Command types: `go_to`, `go_charge`, `go_wait`, `stop`, `resume`
- Status: queued / running / completed / failed / cancelled
- Persist vào bảng `agv_task_executions` (PostgreSQL)
- `session_id` + `session_label` để nhóm các bước trong cùng workflow

**`schedule_manager.py`** — Lịch chạy tự động
- Bảng `agv_schedules` (PostgreSQL)
- Hỗ trợ: one-time, daily (time_of_day), weekly (days_of_week), interval (interval_minutes)
- Kiểm tra mỗi 30 giây, dispatch khi đến hạn
- Priority: 1 (Khẩn cấp) → 5 (Rất thấp)

**`simulation_manager.py`** — Phiên mô phỏng Test Run
- AGV tự chạy tuần hoàn theo lộ trình định sẵn
- Route types: `loop` (A→B→C→A) và `pingpong` (A→B→C→B→A)
- Theo dõi cycle stats (thời gian, số lần dispatch, lỗi)

### 3.6 Hạ tầng phụ trợ

**`map_manager.py`** — Quản lý bản đồ
- Xây đồ thị NetworkX từ DB (`agv_map_roads`, `agv_map_benziers`)
- `line_graph` (DiGraph) riêng cho Line AGV (node có `agvCompat=RFID/both`)
- `node_actions` lưu `fwd_turn/bwd_turn` tại mỗi node

**`map_configure_api.py`** — Router cấu hình node
- `POST /api/map/node/config` — lưu config node (locationType, name, actions)
- `POST /api/map/node/clear` — xóa config node

**`log_buffer.py`** — Ring buffer log in-memory
- Hook `builtins.print` ngay từ đầu để capture toàn bộ output
- Buffer 2000 dòng, expose qua `/logs` API

**`agv_heartbeat.py`** — Kiểm tra online/offline AGV  
**`agv_registry.py`** — Registry singleton phân loại AGV  
**`unified_mqtt.py`** — MQTT unified subscriber helper  
**`publish_states.py`** — Publish trạng thái định kỳ  

**`test_traffic_safety.py`** — Test an toàn giao thông Line AGV
- Chạy lại sau mỗi thay đổi traffic (regression guard)
- Dùng graph map thật từ DB (`map_id=1779790224391`)
- Kiểm tra: allocate-before-move, không giành node xe khác đang đứng

---

## 4. Web_UI — Giao diện Dash

### 4.1 Cấu trúc app

**`main.py`** — Entry point Dash app
- `app.title = "TOT ACS"`
- Global layout: `dcc.Location` + `dcc.Store` (lang, submenu) + `dbc.Toast`
- AI Assistant toast (hiển thị thông báo trợ lý ảo)
- Route động qua `dcc.Location` callback

**`i18n.py`** — Đa ngôn ngữ (Tiếng Việt mặc định + Tiếng Anh)
- `t(key, lang)` — dịch key theo ngôn ngữ
- Hỗ trợ toàn bộ UI strings: menu, form, status, error messages

### 4.2 Các trang (pages)

| File | Route | Chức năng |
|------|-------|-----------|
| `home.py` | `/` | Dashboard tổng quan: AGV online, tasks today, errors, biểu đồ task status |
| `map_view.py` | `/map/agvmap` | Nhúng iframe `AgvMap.html` (realtime map từ FastAPI) |
| `create_map.py` | `/map/create` | Editor bản đồ (ReactFlow) |
| `map_configure.py` | `/map/configure` | Cấu hình node/edge trên bản đồ |
| `agv_manager.py` | `/agv` | Quản lý danh sách AGV, kết nối DB |
| `task_create.py` | `/task/create` | Tạo task mới |
| `task_list.py` | `/task/list` | Danh sách task + trạng thái |
| `task_execute.py` | `/task/execute` | Thực hiện tác vụ |
| `journal_history.py` | `/log/history` | Lịch sử hoạt động |
| `journal_logs.py` | `/log/logs` | Server logs realtime |
| `statistics_page.py` | `/stat` | Thống kê (iframe `statistics.html`) |
| `login.py` | `/login` | Đăng nhập |

### 4.3 Assets (HTML/JS/CSS thuần)

| File | Mô tả |
|------|-------|
| `assets/MapConfigure.html` | Editor cấu hình bản đồ (HTML + JS) |
| `assets/map_editor.html` | Map editor với ReactFlow |
| `assets/task_execute.html` | Giao diện thực hiện task |
| `assets/journal.html` | Nhật ký hoạt động |
| `assets/agv_manager.html` | AGV manager nâng cao |
| `assets/statistics.html` | Trang thống kê |
| `assets/wf_reactflow.js/.css` | ReactFlow wrapper cho map editor |
| `assets/sidebar_menu.js` | Điều khiển sidebar |
| `assets/clientside.js` | Clientside callbacks Dash |
| `assets/style.css` | Style chủ đạo (dark navy theme) |
| `assets/agv_manager.css` | Style riêng AGV manager |

**Màu sắc chủ đạo:**
- Nền: `#0b1326` / `#050d1a` (navy tối)
- Accent: `#adc6ff` / `#4d8eff` (xanh dương)
- Online: `#22c55e` | Warning: `#ffb700` | Error: `#ef4444`
- MQTT Cloud: `#00d4ff` (cyan)

---

## 5. agv_vda5050_simulator — Simulator VDA5050

Simulator độc lập chạy bằng **Pygame**, dùng để test traffic engine mà không cần AGV thật.

```
agv_vda5050_simulator/
├── main.py             ← Entry point (gọi sim/app.py)
├── sim/
│   ├── app.py          ← Load config + khởi tạo Simulator + PygameApp
│   ├── core/simulator.py ← Logic mô phỏng
│   ├── map/loader.py   ← Load graph từ JSON
│   └── ui/pygame_app.py ← Render giao diện Pygame
├── tools/send_sample_orders.py ← Gửi order mẫu
└── config/
    ├── simulator.json  ← Cấu hình chính (broker, map, AGVs)
    ├── new_map.json    ← Bản đồ mẫu
    └── sample_graph.json
```

**Các loại agent được mô phỏng:** AGV, Human, Elevator

---

## 6. unified_main.py — Entry point thống nhất

Chạy song song cả hai hệ thống:
- **Line AGV system**: MQTT v2 + traffic engine (WHCA*, RollingRePlanner, EdgeReservation)
- **VDA5050 system**: FastAPI + MQTT v3

```bash
cd C:\Users\Admin\Desktop\AGVmqtt
python unified_main.py
```

Đọc config từ `agv_vda5050_simulator/config/simulator.json`.

---

## 7. Database (PostgreSQL — TOT_AGV)

Các bảng chính được sử dụng:

| Bảng | Mô tả |
|------|-------|
| `agv_devices` | Danh sách AGV (name, agv_type, ip, factory, map_id) |
| `agv_maps` | Bản đồ (id, name) |
| `agv_map_roads` | Cạnh đồ thị (id_source, id_dest, speed, move_direction, distance, width) |
| `agv_map_benziers` | Cạnh cong (bezier control points) |
| `agv_task_executions` | Lịch sử thực thi lệnh per-AGV |
| `agv_schedules` | Lịch chạy tự động |

**Connection string mặc định:** `postgresql://postgres:ducmanh1801@localhost:5432/TOT_AGV`

---

## 8. MQTT Topics chính

### VDA5050 AGV
| Direction | Topic pattern | Nội dung |
|-----------|--------------|---------|
| AGV → Server | `vda5050/{manufacturer}/{agv_id}/state` | Trạng thái VDA5050 |
| Server → AGV | `vda5050/{manufacturer}/{agv_id}/order` | Order JSON |
| Server → AGV | `vda5050/{manufacturer}/{agv_id}/instantActions` | Lệnh tức thì |

### Line AGV (RFID)
| Direction | Topic pattern | Nội dung |
|-----------|--------------|---------|
| AGV → Server | `line/{agv_id}/state` | State RFID (lastNodeId, ack, battery...) |
| Server → AGV | `line/{agv_id}/plan` | Plan JSON (action codes) |
| Server → AGV | `line/{agv_id}/cmd` | Lệnh tức thì |

### uAGV (protocol thứ 3)
| Direction | Topic pattern |
|-----------|--------------|
| AGV → Server | `uagv/{version}/{manufacturer}/{agv_id}/state` |
| Server → AGV | `uagv/{version}/{manufacturer}/{agv_id}/order` |

---

## 9. Kiến trúc phần cứng Line AGV

```
Python Manager (Server)
        │ MQTT/TLS 8883
        ▼
   ESP32-C5 (WiFi Bridge)
        │ UART 115200 baud
        │ JSON + newline
        ▼
  Arduino Mega (Low-level Control)
  — Motor / RFID / PID / Safety sensor
```

**Nguyên tắc cốt lõi:**
- Python **chỉ gửi plan** (danh sách RFID tag + action), **không điều khiển motor trực tiếp**
- Arduino tự quyết định tốc độ, phanh, góc cua dựa trên cảm biến
- ESP32 làm bridge MQTT ↔ UART, chia nhỏ plan (chunker protocol)

---

## 10. Các file config JSON quan trọng

| File | Mô tả |
|------|-------|
| `mqtt_Server/mqtt_mode.json` | Mode MQTT hiện tại (local/cloud) |
| `mqtt_Server/map.json` | Cache bản đồ local |
| `mqtt_Server/camera_pick_map.json` | Mapping camera → pick node |
| `mqtt_Server/team_drop_map.json` | Mapping team → drop node |
| `mqtt_Server/state.json` | Cache trạng thái |
| `agv_vda5050_simulator/config/simulator.json` | Cấu hình simulator (broker, AGV list, map) |
