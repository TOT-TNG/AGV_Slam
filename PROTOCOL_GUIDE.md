# Hướng dẫn Giao thức Điều phối AGV
**Dành cho lập trình viên Python Manager**

> Tài liệu này mô tả toàn bộ giao thức giao tiếp giữa Python Manager, ESP32 và Arduino,
> đủ để viết lại hoặc mở rộng Python Manager mà không cần đọc firmware.

---

## Mục lục

1. [Kiến trúc hệ thống](#1-kiến-trúc-hệ-thống)
2. [MQTT Topics](#2-mqtt-topics)
3. [Bản tin State — AGV → Server](#3-bản-tin-state--agv--server)
4. [Bản tin Plan (Order) — Server → AGV](#4-bản-tin-plan-order--server--agv)
5. [Lệnh tức thì (instantActions) — Server → AGV](#5-lệnh-tức-thì-instantactions--server--agv)
6. [Bảng Action Codes](#6-bảng-action-codes)
7. [Sự kiện (Events) từ AGV](#7-sự-kiện-events-từ-agv)
8. [Giao thức ACK và Retry](#8-giao-thức-ack-và-retry)
9. [Plan Chunker Protocol](#9-plan-chunker-protocol)
10. [Luồng điều phối một chuyến hoàn chỉnh](#10-luồng-điều-phối-một-chuyến-hoàn-chỉnh)
11. [Trạng thái kết nối (connection topic)](#11-trạng-thái-kết-nối-connection-topic)
12. [Pin yếu và Sạc tự động](#12-pin-yếu-và-sạc-tự-động)
13. [API Python quan trọng](#13-api-python-quan-trọng)
14. [Ví dụ code thực tế](#14-ví-dụ-code-thực-tế)
15. [Debug và Troubleshooting](#15-debug-và-troubleshooting)
16. [Cửa tự động (Gate Controller)](#16-cửa-tự-động-gate-controller)

---

## 1. Kiến trúc hệ thống

```
┌──────────────────┐        MQTT/TLS 8883       ┌──────────────────┐
│  Python Manager  │ ◄─────────────────────────► │    ESP32-C5      │
│  (Fleet Manager) │                             │  (WiFi Bridge)   │
│  Port 1883/8883  │                             │                  │
└──────────────────┘                             └────────┬─────────┘
                                                          │ UART 115200 baud
                                                          │ JSON + newline
                                                 ┌────────▼─────────┐
                                                 │  Arduino Mega    │
                                                 │  (Low-level Ctrl)│
                                                 │  Motor/Sensor    │
                                                 └──────────────────┘
```

| Layer | Vai trò | Không làm |
|-------|---------|-----------|
| **Python Manager** | Tính đường đi, điều phối, tránh va chạm, gửi plan | Điều khiển motor trực tiếp |
| **ESP32-C5** | Bridge MQTT ↔ UART, chia nhỏ plan (chunker) | Xử lý logic nghiệp vụ |
| **Arduino Mega** | Chạy motor, đọc RFID, PID, safety | Kết nối WiFi, routing |

**Nguyên tắc quan trọng nhất:**
- Python **không bao giờ** gửi lệnh điều khiển motor trực tiếp.
- Python chỉ gửi **plan** (danh sách thẻ RFID + action tại mỗi thẻ).
- Arduino tự quyết định tốc độ, phanh, góc cua dựa trên cảm biến.

---

## 2. MQTT Topics

### Cấu trúc (VDA5050 v2.0.0)

```
uagv/v2/{factory}/{agv_id}/{topic_name}
```

| Biến | Giá trị mặc định | Ghi chú |
|------|-----------------|---------|
| `factory` | `VietDuc` | Tên nhà máy, cấu hình trong `settings.json` |
| `agv_id` | `AGV01`, `AGV02`,... | ID riêng từng xe, cấu hình trong `agv_config` |

### Các topics đang dùng

| Topic | Hướng | Retained | Mục đích |
|-------|-------|----------|---------|
| `.../state` | AGV → Server | No | Trạng thái AGV định kỳ |
| `.../order` | Server → AGV | No | Gửi plan (lộ trình) |
| `.../instantActions` | Server → AGV | No | Lệnh tức thì (stop/run/...) |
| `.../connection` | Cả hai | **Yes** | Trạng thái kết nối (Last Will) |
| `.../factsheet` | AGV → Server | **Yes** | Thông số kỹ thuật AGV |

### Ví dụ topic thực tế

```
uagv/v2/VietDuc/AGV01/state          ← AGV01 báo trạng thái
uagv/v2/VietDuc/AGV01/order          → Python gửi plan cho AGV01
uagv/v2/VietDuc/AGV01/instantActions → Python gửi lệnh tức thì
uagv/v2/VietDuc/AGV01/connection     ← AGV01 báo ONLINE/OFFLINE
```

### Subscribe (Python phải SUB)

```python
client.subscribe("uagv/v2/VietDuc/+/state")       # nhận state tất cả xe
client.subscribe("uagv/v2/VietDuc/+/connection")   # nhận connection tất cả xe
```

---

## 3. Bản tin State — AGV → Server

Arduino gửi bản tin này mỗi khi:
- Đọc được thẻ RFID mới
- Có sự kiện (event) cần báo cáo
- Tốc độ heartbeat (khoảng 500ms–2s, tùy firmware)

### Cấu trúc JSON đầy đủ

```json
{
  "headerId": 42,
  "timestamp": "1970-01-01T00:10:25.123Z",
  "version": "2.0.0",
  "manufacturer": "VietDuc",
  "serialNumber": "AGV01",

  "orderId": "a1b2c3d4",
  "orderUpdateId": 0,
  "lastNodeId": "101",
  "lastNodeSequenceId": 3,
  "distanceSinceLastNode": 0.0,

  "operatingMode": "AUTOMATIC",
  "driving": true,
  "paused": false,
  "newBaseRequest": false,

  "nodeStates": [
    { "nodeId": "101", "sequenceId": 3, "released": true },
    { "nodeId": "102", "sequenceId": 4, "released": true }
  ],
  "edgeStates":   [],
  "actionStates": [],
  "loads":        [],
  "informations": [],

  "batteryState": {
    "batteryCharge": 80,
    "batteryVoltage": 0.0,
    "charging": false,
    "reach": 0
  },

  "errors": [
    {
      "errorType": "OBSTACLE",
      "errorLevel": "WARNING",
      "errorDescription": "Obstacle detected by sensor"
    }
  ],

  "safetyState": {
    "eStop": "NONE",
    "fieldViolation": false
  },

  "rssi": -68,
  "mac": "A4CF1234ABCD",

  "tag": 101,
  "prev_tag": 100,
  "status": "auto",
  "action_info": "running",
  "ack": "a1b2c3d4",

  "battery_low": false,
  "battery_blocking": false
}
```

### Giải thích từng field

#### Header (ESP32 tự thêm)

| Field | Kiểu | Mô tả |
|-------|------|-------|
| `headerId` | int | Tự tăng mỗi bản tin |
| `timestamp` | string | ISO 8601, năm 1970 (không có NTP — dùng millis()) |
| `version` | string | Luôn `"2.0.0"` |
| `manufacturer` | string | `"VietDuc"` |
| `serialNumber` | string | AGV ID, VD `"AGV01"` |
| `rssi` | int | Cường độ WiFi (dBm), ESP32 thêm |
| `mac` | string | MAC address WiFi, ESP32 thêm |

#### Vị trí và hành trình (VDA5050)

| Field | Kiểu | Mô tả |
|-------|------|-------|
| `lastNodeId` | string | Thẻ RFID vừa đọc được, dạng string (VD `"101"`) |
| `lastNodeSequenceId` | int | Index của thẻ trong plan hiện tại |
| `orderId` | string | ID của plan đang thực thi (từ `"id"` Python gửi xuống) |
| `orderUpdateId` | int | Luôn 0 hiện tại |
| `distanceSinceLastNode` | float | Luôn 0.0 (không có odometer) |
| `nodeStates` | array | Lookahead 5 node tiếp theo trong plan |

#### Trạng thái vận hành

| Field | Kiểu | Giá trị có thể | Mô tả |
|-------|------|----------------|-------|
| `operatingMode` | string | `AUTOMATIC` / `SEMIAUTOMATIC` / `MANUAL` | Chế độ hiện tại |
| `driving` | bool | true/false | Xe đang di chuyển |
| `paused` | bool | true/false | Xe đang chờ (WAIT_SYS/WAIT_USER) |

| `operatingMode` | Khi nào |
|-----------------|---------|
| `AUTOMATIC` | Đang chạy theo plan |
| `SEMIAUTOMATIC` | Đang thực hiện lệnh quay (TURN_L/TURN_R) |
| `MANUAL` | Xe bị stop, ở chế độ tay |

#### Safety

| Field | Kiểu | Mô tả |
|-------|------|-------|
| `safetyState.eStop` | string enum | `"NONE"` (bình thường) / `"MANUAL"` (xe đang IDLE thủ công) |
| `safetyState.fieldViolation` | bool | `true` khi cảm biến vật cản kích hoạt |

#### Backward-compatible fields (dành riêng hệ thống này)

| Field | Kiểu | Mô tả |
|-------|------|-------|
| `tag` | int | Giống `lastNodeId` nhưng là int |
| `prev_tag` | int | Thẻ trước đó — dùng để tính hướng đầu xe |
| `status` | string | `"auto"` hoặc `"manual"` |
| `action_info` | string | `"running"` hoặc `"idle"` |
| `ack` | string | ID của plan vừa nhận (xác nhận) |
| `event` | string | Tên sự kiện (xem Mục 7) |
| `battery_low` | bool | true khi cảm biến pin yếu |
| `battery_blocking` | bool | true khi xe từ chối lệnh vì pin yếu |

### Cách Python đọc state

```python
def update_state(self, payload: str):
    data = json.loads(payload)

    # Vị trí hiện tại
    last_node_str = data.get('lastNodeId', '')
    self.current_tag = int(last_node_str) if last_node_str.isdigit() \
                       else data.get('tag', 0)

    self.prev_tag       = int(data.get('prev_tag', 0))
    self.operating_mode = data.get('operatingMode', 'MANUAL')
    self.driving        = bool(data.get('driving', False))
    self.paused         = bool(data.get('paused', False))

    # ACK xác nhận xe đã nhận plan
    if data.get('ack') == self.last_sent_cmd_id:
        self.last_sent_cmd_id = None   # Plan đã được confirm

    # Sự kiện từ xe
    if 'event' in data:
        self.handle_event(data['event'], data)
```

---

## 4. Bản tin Plan (Order) — Server → AGV

### Mục đích

Plan là danh sách các bước `{thẻ RFID → hành động}`. Khi AGV đọc được thẻ RFID khớp với `t`, nó sẽ thực hiện action `a` với giá trị `v`.

### Format gửi

```
Topic: uagv/v2/VietDuc/AGV01/order
```

```json
{
  "c": "plan",
  "id": "a1b2c3d4",
  "d": [
    {"t": 100, "a": 4,  "v": 120},
    {"t": 100, "a": 3,  "v": 0},
    {"t": 101, "a": 4,  "v": 60},
    {"t": 101, "a": 20, "v": 0},
    {"t": 101, "a": 5,  "v": 0},
    {"t": 101, "a": 21, "v": 0},
    {"t": 101, "a": 4,  "v": 120},
    {"t": 101, "a": 3,  "v": 0},
    {"t": 102, "a": 2,  "v": 0}
  ]
}
```

| Field | Kiểu | Mô tả |
|-------|------|-------|
| `c` | string | Luôn là `"plan"` |
| `id` | string | UUID ngắn (8 ký tự) — xe sẽ ACK lại ID này |
| `d` | array | Danh sách bước, **mảng phẳng** (không lồng nhau) |
| `d[].t` | int | Tag RFID — khi xe đọc được thẻ này |
| `d[].a` | int | Action code (xem Mục 6) |
| `d[].v` | int | Giá trị tham số (tốc độ, thời gian,...) |

### Quy tắc cấu trúc plan

```
Plan cho đường đi: Tag100 → Tag101 → Tag102

[
  // Tại Tag100: đặt tốc độ 120, sau đó chạy thẳng
  {"t": 100, "a": 4, "v": 120},   // SPEED = 120
  {"t": 100, "a": 3, "v": 0},     // RUN (chạy thẳng về hướng tag tiếp theo)

  // Tại Tag101: giảm tốc → tắt lidar → rẽ phải → bật lidar → tăng tốc → chạy
  {"t": 101, "a": 4,  "v": 60},   // SPEED = 60 (giảm trước khi rẽ)
  {"t": 101, "a": 20, "v": 0},    // LIDAR_OFF (tắt cảm biến vật cản khi quay)
  {"t": 101, "a": 5,  "v": 0},    // TURN_R (rẽ phải)
  {"t": 101, "a": 21, "v": 0},    // LIDAR_ON (bật lại sau khi quay xong)
  {"t": 101, "a": 4,  "v": 120},  // SPEED = 120 (tăng tốc sau cua)
  {"t": 101, "a": 3,  "v": 0},    // RUN

  // Tại Tag102 (đích): chờ xác nhận người dùng
  {"t": 102, "a": 2, "v": 0}      // WAIT_USER
]
```

**Quy tắc:**
- Nhiều bước có cùng `t` = nhiều lệnh tại cùng 1 thẻ, thực hiện **theo thứ tự**.
- Bước cuối cùng của mỗi thẻ phải là lệnh điều hướng: `RUN`, `TURN_R`, `TURN_L`, `WAIT_SYS`, `WAIT_USER`, hoặc `WAIT_CHARGE`.
- Plan bắt đầu từ **thẻ hiện tại** của xe (overlap), không phải thẻ tiếp theo.

### Windowed Plan (Rolling)

Python không gửi toàn bộ lộ trình một lần. Chỉ gửi **lookahead = 6 node** tiếp theo. Khi xe báo đã đến node N, Python gửi tiếp từ node N đến N+6.

```
full_path = [100, 101, 102, 103, 104, 105, 106, 107]
lookahead = 6

Lần 1 (xe ở 100): gửi [100, 101, 102, 103, 104, 105, 106]
Lần 2 (xe đến 103): gửi [103, 104, 105, 106, 107]
```

Lợi ích: cho phép re-route giữa chừng, tiết kiệm RAM Arduino.

---

## 5. Lệnh tức thì (instantActions) — Server → AGV

```
Topic: uagv/v2/VietDuc/AGV01/instantActions
```

### Các lệnh hỗ trợ

```json
{ "c": "stop" }              // Dừng khẩn cấp, chuyển về MANUAL
{ "c": "run" }               // Tiếp tục chạy từ trạng thái dừng
{ "c": "run", "v": 150 }     // Chạy với tốc độ 150
{ "c": "run", "p": "fwd" }   // Chạy tiến (xóa plan hiện tại)
{ "c": "run", "p": "bwd" }   // Chạy lùi (xóa plan hiện tại)
{ "c": "reset" }             // Reset board Arduino
{ "c": "battery_unlock" }    // Mở khóa xe sau khi sạc đủ
{ "c": "ack_event", "d": "confirm" }  // ACK sự kiện "confirm" từ xe
{ "c": "set_btn_pic", "line": 3, "pic": 28 }  // Bật đèn nút tổ 3
{ "c": "reset_team_btns" }   // Tắt tất cả nút tổ
{ "c": "door_check" }        // Kiểm tra lidar cửa
```

### Tham số `run`

| Field | Ý nghĩa |
|-------|---------|
| `v` | Tốc độ (0–255), bỏ qua nếu không truyền |
| `p` | Hướng: `"fwd"` (tiến) hoặc `"bwd"` (lùi); bỏ qua để giữ hướng cũ |

---

## 6. Bảng Action Codes

> Đồng bộ hoàn toàn giữa Python (`agv_instance.py`) và Arduino (`mission.h`).

### Điều hướng

| Code | Tên | Mô tả | `v` |
|------|-----|-------|-----|
| 1 | `WAIT_SYS` | Dừng xe, chờ lệnh từ hệ thống | — |
| 2 | `WAIT_USER` | Dừng xe, chờ nhấn nút HMI xác nhận | — |
| 3 | `RUN` | Chạy thẳng đến thẻ tiếp theo | — |
| 4 | `SPEED` | Đặt tốc độ | 0–255 |
| 5 | `TURN_R` | Rẽ phải 90° | — |
| 6 | `TURN_L` | Rẽ trái 90° | — |
| 7 | `DIR_FWD` | Đặt chiều tiến (đầu xe dẫn) | — |
| 8 | `DIR_BWD` | Đặt chiều lùi (đuôi xe dẫn) | — |

### Cảm biến an toàn

| Code | Tên | Mô tả |
|------|-----|-------|
| 20 | `LIDAR_OFF` | Tắt cảm biến vật cản — **bắt buộc trước khi TURN** |
| 21 | `LIDAR_ON` | Bật lại cảm biến vật cản — **sau khi TURN xong** |

### Điều khiển đặc biệt

| Code | Tên | Mô tả |
|------|-----|-------|
| 28 | `BRAKE_ON` | Đóng phanh |
| 29 | `BRAKE_OFF` | Mở phanh |
| 35 | `WAIT_CHARGE` | Đến trạm sạc: đèn vàng + bật cảm biến, chờ |

### Âm thanh/Đèn

| Code | Tên | Code | Tên |
|------|-----|------|-----|
| 22 | `NHAC_START` | 23 | `NHAC_STOP` |
| 24 | `NHAC_XIN_LIEU` | 25 | `NHAC_MO_CUA` |
| 26 | `NHAC_XIN_RE` | 27 | `NHAC_TAT` |
| 32 | `DEN_VANG` | 33 | `DEN_XANH` |
| 34 | `DEN_TAT` | — | — |

### Móc hàng

| Code | Tên | Mô tả |
|------|-----|-------|
| 30 | `HOOK_RAISE` | Nâng móc hàng |
| 31 | `HOOK_LOWER` | Hạ móc hàng |

### Pattern chuẩn trước/sau TURN

```
Trước rẽ tại thẻ N:
  {"t": N-1, "a": 4,  "v": 60}    // Giảm tốc tại thẻ trước
  {"t": N-1, "a": 20, "v": 0}     // Tắt LIDAR tại thẻ trước
  {"t": N-1, "a": 3,  "v": 0}     // Chạy vào thẻ N

Tại thẻ N (thực hiện rẽ):
  {"t": N, "a": 5, "v": 0}        // TURN_R (hoặc TURN_L)
  {"t": N, "a": 21, "v": 0}       // Bật LIDAR lại
  {"t": N, "a": 4,  "v": 120}     // Tăng tốc sau cua
  {"t": N, "a": 3,  "v": 0}       // Chạy tiếp
```

### Đổi chiều lùi

```
Xe đang tiến (DIR_FWD), muốn lùi vào thẻ N:

  {"t": N-1, "a": 4,  "v": 60}     // Giảm tốc
  {"t": N-1, "a": 3,  "v": 0}      // Chạy tiến đến N-1

  {"t": N-1, "a": 1,  "v": 0}      // WAIT_SYS: dừng hẳn trước khi đổi chiều
  {"t": N-1, "a": 8,  "v": 0}      // DIR_BWD: đặt chiều lùi
  {"t": N-1, "a": 3,  "v": 0}      // Bắt đầu lùi

  {"t": N,   "a": 35, "v": 0}      // WAIT_CHARGE tại đích
```

---

## 7. Sự kiện (Events) từ AGV

Khi xe muốn thông báo điều gì đó lên server, nó thêm field `"event"` vào bản tin state.
Python **phải ACK ngay** để xe xóa event (tránh gửi lặp).

### Danh sách events

| Event | Khi nào | Dữ liệu kèm | Python cần làm |
|-------|---------|-------------|----------------|
| `"confirm"` | Người dùng bấm nút xác nhận giao hàng tại HMI | `"targets": [3, 4]` (số tổ đã giao) | Gửi `ack_event`, tiếp tục điều phối |
| `"return"` | Người dùng bấm nút yêu cầu xe về trạm | — | Gửi `ack_event`, điều xe về trạm sạc |
| `"battery_need_charge"` | Xe có pin yếu + hành trình xong | — | Gửi `ack_event`, điều xe về trạm sạc |

### Cách nhận và xử lý

```python
def on_state_received(data: dict):
    if 'event' not in data:
        return

    event_name = data['event']

    # Bước 1: ACK ngay để Arduino xóa pendingEvent
    agv.send_server_ack(event_name)   # gửi {"c": "ack_event", "d": event_name}

    # Bước 2: Xử lý theo loại event
    if event_name == 'confirm':
        teams_confirmed = data.get('targets', [])
        dispatch_next_delivery(agv, teams_confirmed)

    elif event_name == 'return':
        dispatch_return_to_charger(agv)

    elif event_name == 'battery_need_charge':
        agv.battery_blocking = True
        dispatch_return_to_charger(agv)
```

### Gửi ACK

```
Topic: uagv/v2/VietDuc/AGV01/instantActions
Payload: {"c": "ack_event", "d": "confirm"}
```

---

## 8. Giao thức ACK và Retry

### Plan ACK

```
Python gửi plan với "id": "a1b2c3d4"
    ↓
Arduino nhận plan → thực thi → báo về: { ..., "ack": "a1b2c3d4" }
    ↓
Python kiểm tra: data['ack'] == last_sent_cmd_id → xác nhận thành công
```

### Retry khi mất gói

Nếu sau 4 giây không nhận ACK (và xe vẫn đang điều hướng):

```python
RETRY_TIMEOUT = 4.0

if (self.last_sent_cmd_id is not None
        and self.is_navigating
        and (time.time() - self._last_sent_time) > RETRY_TIMEOUT):
    self._send_segment(self._last_segment_nodes)  # Gửi lại segment cũ
```

**Điều kiện không retry:**
- `is_navigating == False` (chuyến đã kết thúc)
- Xe đang đứng ở `segment_nodes[0]` (plan đã được nhận)

---

## 9. Plan Chunker Protocol

### Vấn đề

Arduino Mega có UART RX buffer chỉ **128 bytes**. Plan lớn (20–100 bước, 400–2000 bytes) sẽ bị tràn buffer → mất dữ liệu.

### Giải pháp

ESP32-C5 nhận plan đầy đủ từ Python, **tự động chia** thành gói 3 bước (~100 bytes mỗi gói), gửi từng gói và chờ Arduino ACK.

```
Python ──plan(20 bước)──► ESP32 ──chunk seq=0 (3 bước)──► Arduino ──chunk_ack seq=0──► ESP32
                                  ──chunk seq=1 (3 bước)──► Arduino ──chunk_ack seq=1──► ESP32
                                  ...
                                  ──chunk seq=6 (2 bước)──► Arduino (thực thi plan)
```

### Python KHÔNG cần làm gì thêm

Quá trình chunking hoàn toàn do ESP32 xử lý. Python chỉ gửi plan bình thường. Python nhận ACK theo `"id"` như bình thường.

### Format chunk (thông tin kỹ thuật)

```json
{
  "c": "plan",
  "id": "a1b2c3d4",
  "seq": 0,
  "total": 7,
  "d": [
    {"t": 100, "a": 4, "v": 120},
    {"t": 100, "a": 3, "v": 0},
    {"t": 101, "a": 4, "v": 60}
  ]
}
```

Arduino ACK mỗi chunk:
```json
{ "c": "chunk_ack", "seq": 0 }
```

---

## 10. Luồng điều phối một chuyến hoàn chỉnh

### Sơ đồ luồng

```
[1] Python tính đường đi A→B   (NetworkX Dijkstra/A*)
        ↓
[2] Python tính plan_data      (build_plan: inject speed, turn, lidar, direction)
        ↓
[3] Python gửi segment đầu     (publish "plan" + id)
        ↓
[4] ESP32 chunk → Arduino      (3 bước/gói + ACK)
        ↓
[5] Arduino thực thi plan      (chạy → đọc RFID → rẽ → đến đích)
        ↓
[6] Mỗi khi đến thẻ mới:
    Arduino gửi state (tag=N, ack=id)
        ↓
    Python nhận state:
    - Xác nhận ACK
    - Tính toán có cần gửi segment tiếp
        ↓
[7] Python gửi tiếp (rolling):  
    Nếu xe đã đến gần cuối plan → gửi segment N+1 đến N+lookahead
        ↓
[8] Xe đến đích (action = WAIT_USER hoặc WAIT_SYS):
    Arduino dừng, chờ
        ↓
[9] Arduino gửi event "confirm" (nếu WAIT_USER + người bấm nút)
        ↓
[10] Python nhận event:
     - Gửi ack_event
     - Dispatch chuyến tiếp theo
```

### Ví dụ code Python tổng quát

```python
def dispatch(agv, destination_tag, graph, task_type="delivery"):
    """Điều phối AGV đến đích."""

    # 1. Tính đường đi
    path = nx.shortest_path(graph, agv.current_tag, destination_tag,
                             weight='weight')

    # 2. Giao đường đi cho AGV — tự động gửi segment đầu
    agv.set_path(path, graph, task_type=task_type)
    # Khi xe di chuyển, update_state() tự gửi rolling plan tiếp theo
```

---

## 11. Trạng thái kết nối (connection topic)

```
Topic: uagv/v2/VietDuc/AGV01/connection   (RETAINED)
```

### Bản tin ONLINE (ESP32 gửi khi kết nối MQTT)

```json
{
  "headerId": 1,
  "timestamp": "...",
  "version": "2.0.0",
  "manufacturer": "VietDuc",
  "serialNumber": "AGV01",
  "connectionState": "ONLINE"
}
```

### Last Will (ESP32 đăng ký khi connect MQTT)

Broker tự gửi khi ESP32 ngắt kết nối đột ngột:

```json
{ ..., "connectionState": "CONNECTIONBROKEN" }
```

### Python xử lý

```python
def update_connection_state(self, state: str):
    self.connection_state = state
    self.connected = (state == 'ONLINE')
    if state == 'CONNECTIONBROKEN':
        # Xe mất kết nối đột ngột → cảnh báo, không dispatch thêm
        log_warning(f"{self.id} mất kết nối!")
```

| `connectionState` | Ý nghĩa |
|-------------------|---------|
| `ONLINE` | ESP32 đang kết nối MQTT |
| `OFFLINE` | ESP32 ngắt kết nối có chủ ý (chưa dùng) |
| `CONNECTIONBROKEN` | ESP32 mất kết nối đột ngột (Last Will) |

---

## 12. Pin yếu và Sạc tự động

### Flow phát hiện pin yếu

```
Cảm biến pin yếu (PIN_PIN_YEU) HIGH
    ↓
Arduino set battery_low = true
Arduino gửi state với:
    "battery_low": true
    "batteryState": {"batteryCharge": 20, ...}
    ↓
Python nhận:
    agv.battery_low = True
    agv.battery = 20   (%)
```

### Flow battery_blocking (chặn lệnh mới)

```
battery_low = true + xe vừa hoàn thành hành trình
    ↓
Arduino set battery_blocking = true
Arduino gửi event "battery_need_charge"
    ↓
Python nhận event:
    agv.battery_blocking = True
    → gửi ack_event
    → dispatch xe về trạm sạc
    ↓
Xe sạc đủ thời gian (2h) → Python gửi:
    {"c": "battery_unlock"}
    ↓
Arduino nhận:
    battery_blocking = false
    battery_low = false (đọc lại cảm biến)
```

### Kiểm tra trước khi dispatch

```python
if agv.battery_blocking:
    print("Xe đang sạc, không dispatch!")
    return

# OK để dispatch
agv.set_path(path, graph)
```

---

## 13. API Python quan trọng

Tất cả trong `python-manager/agv/agv_instance.py`:

### Gửi plan (lộ trình)

```python
agv.set_path(
    path_nodes,           # list[int] — danh sách tag RFID theo thứ tự
    graph,                # NetworkX DiGraph
    task_type="delivery", # "delivery" | "pickup" | "return_charge" | ...
    start_heading=None,   # (hx, hy) vector hướng đầu xe, None = tự tính từ prev_tag
    precomp_steps=None    # kết quả SimulationEngine.dry_run() nếu có
)
```

### Gửi lệnh tức thì

```python
agv.send_command("stop")        # Dừng khẩn cấp
agv.send_command("run")         # Tiếp tục
agv.send_command("reset")       # Reboot Arduino
agv.send_command("battery_unlock")  # Mở khóa sau sạc
```

### Giao tiếp HMI (điều khiển màn hình trên xe)

```python
agv.send_btn_pic(line_num=3, pic_value=28)   # Bật sáng nút tổ 3 (pic=28=bật, 27=tắt)
agv.send_reset_team_btns()                    # Tắt hết nút tổ
```

### ACK sự kiện

```python
agv.send_server_ack("confirm")    # ACK sự kiện "confirm"
agv.send_server_ack("return")     # ACK sự kiện "return"
```

### Kiểm tra trạng thái

```python
agv.is_available(valid_idle_nodes)  # True nếu xe rảnh, ở node hợp lệ, lifecycle=free
agv.get_error_status()              # "OK" hoặc "ERR: ..." hoặc "WARNING: Stuck..."
agv.next_tag                        # Property: thẻ tiếp theo trong hành trình
```

### Thuộc tính quan trọng

```python
agv.current_tag          # int: thẻ hiện tại
agv.prev_tag             # int: thẻ vừa qua (tính hướng đầu xe)
agv.is_navigating        # bool: đang di chuyển theo plan
agv.task_lifecycle       # "free" | "assigned" | "picking" | "delivering" | "returning"
agv.operating_mode       # "AUTOMATIC" | "SEMIAUTOMATIC" | "MANUAL"
agv.driving              # bool: đang di chuyển
agv.paused               # bool: đang chờ (WAIT_SYS/WAIT_USER)
agv.battery              # int: % pin (từ batteryState.batteryCharge)
agv.battery_low          # bool: cảm biến pin yếu
agv.battery_blocking     # bool: chặn lệnh mới (pin yếu + hành trình xong)
agv.vda_errors           # list: lỗi từ xe [{errorType, errorLevel, ...}]
agv.safety_state         # dict: {eStop: "NONE"/"MANUAL", fieldViolation: bool}
```

---

## 14. Ví dụ code thực tế

### Ví dụ 1: Setup và kết nối MQTT

```python
import paho.mqtt.client as mqtt
import json

BROKER = "iot.tot360.com.vn"
PORT   = 8883
FACTORY = "VietDuc"

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        # Subscribe tất cả xe trong factory
        client.subscribe(f"uagv/v2/{FACTORY}/+/state")
        client.subscribe(f"uagv/v2/{FACTORY}/+/connection")
        print("MQTT Connected!")

def on_message(client, userdata, msg):
    parts = msg.topic.split('/')
    if len(parts) != 5:
        return
    agv_id    = parts[3]
    topic_name = parts[4]
    payload   = msg.payload.decode('utf-8')
    data      = json.loads(payload)

    if topic_name == 'state':
        agv_list[agv_id].update_state(payload)
    elif topic_name == 'connection':
        state = data.get('connectionState', 'OFFLINE')
        agv_list[agv_id].update_connection_state(state)

client = mqtt.Client()
client.tls_set_context()        # TLS, hoặc client.tls_set() với cert file
client.tls_insecure_set(True)   # Bỏ qua verify cert (broker nội bộ)
client.username_pw_set("iot_user", "d7xvk5pKkqsKKMd")
client.on_connect = on_connect
client.on_message = on_message
client.connect(BROKER, PORT)
client.loop_start()
```

### Ví dụ 2: Gửi plan thủ công (không dùng AGV class)

```python
import uuid, json

def send_plan(client, agv_id, factory, plan_steps):
    """
    plan_steps: list of {"t": int, "a": int, "v": int}
    """
    cmd_id  = str(uuid.uuid4())[:8]
    topic   = f"uagv/v2/{factory}/{agv_id}/order"
    payload = json.dumps({"c": "plan", "id": cmd_id, "d": plan_steps})
    client.publish(topic, payload)
    return cmd_id

# Xe AGV01 đi từ tag 100 → 101 → 102 (đích, chờ xác nhận)
plan = [
    {"t": 100, "a": 4, "v": 120},   # SPEED 120
    {"t": 100, "a": 3, "v": 0},     # RUN

    {"t": 101, "a": 4,  "v": 60},   # SPEED 60 (trước cua)
    {"t": 101, "a": 20, "v": 0},    # LIDAR OFF
    {"t": 101, "a": 5,  "v": 0},    # TURN RIGHT
    {"t": 101, "a": 21, "v": 0},    # LIDAR ON
    {"t": 101, "a": 4,  "v": 120},  # SPEED 120
    {"t": 101, "a": 3,  "v": 0},    # RUN

    {"t": 102, "a": 2, "v": 0},     # WAIT_USER (chờ người bấm nút)
]

cmd_id = send_plan(client, "AGV01", "VietDuc", plan)
print(f"Plan sent, cmd_id={cmd_id}")
```

### Ví dụ 3: Dừng khẩn cấp tất cả xe

```python
def emergency_stop_all(client, factory, agv_ids):
    payload = json.dumps({"c": "stop"})
    for agv_id in agv_ids:
        topic = f"uagv/v2/{factory}/{agv_id}/instantActions"
        client.publish(topic, payload)
        print(f"STOP sent to {agv_id}")
```

### Ví dụ 4: Xử lý event từ xe

```python
def on_state_received(client, agv, data):
    if 'event' not in data:
        return

    event  = data['event']
    topic  = f"uagv/v2/VietDuc/{agv.id}/instantActions"

    # Bước 1: ACK ngay (quan trọng — tránh xe gửi lặp)
    ack_payload = json.dumps({"c": "ack_event", "d": event})
    client.publish(topic, ack_payload)

    # Bước 2: Xử lý
    if event == "confirm":
        confirmed_teams = data.get('targets', [])
        print(f"AGV {agv.id} giao cho tổ {confirmed_teams}")
        # Dispatch chuyến tiếp theo...

    elif event == "return":
        print(f"AGV {agv.id} yêu cầu về trạm")
        # Gửi plan về trạm sạc...

    elif event == "battery_need_charge":
        print(f"AGV {agv.id} pin yếu, cần sạc")
        agv.battery_blocking = True
        # Gửi plan về trạm sạc...
```

---

## 15. Debug và Troubleshooting

### Serial Monitor Arduino (115200 baud)

```
[UART RX] len=52 data={"c":"plan","id":"a1b2c3","seq":0,"total":3,...}
[CHUNK] ACK seq=0 steps=3
[CHUNK] ACK seq=1 steps=6
[PLAN] Received! Bat dau tu the 101
[PLAN] Tong buoc: 9
  [3] The 101: CHAY
  [4] The 102: TOC_DO(60)
  [5] The 102: LIDAR_OFF
  [6] The 102: RE_PHAI
  [7] The 102: LIDAR_ON
  [8] The 102: CHAY
  [9] The 103: WAIT_USER
```

### Kiểm tra UART OK

Khi Arduino khởi động, nó gửi `{"c":"ping"}`. ESP32 trả lời `{"c":"pong"}`.

```
[UART] Ping ← Arduino | Pong → Arduino (UART OK)
```

Nếu không thấy log này → kiểm tra dây TX/RX giữa ESP32 (GPIO4/5) và Arduino (pin 14/15).

### Kiểm tra MQTT

```
[MQTT] Connecting iot.tot360.com.vn:8883
[MQTT] Connected!
[Topics]
  state:   uagv/v2/VietDuc/AGV01/state
  order:   uagv/v2/VietDuc/AGV01/order
[MQTT] SUB: uagv/v2/VietDuc/AGV01/order
[MQTT] SUB: uagv/v2/VietDuc/AGV01/instantActions
```

### Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|-------------|-------------------|---------------|
| Xe không nhận plan | UART không OK | Xem log Arduino `[UART RX]` |
| Xe nhận plan nhưng không chạy | `battery_blocking = true` | Kiểm tra `"battery_blocking"` trong state |
| Plan bị lặp lại liên tục | Python retry vô hạn | Kiểm tra ACK logic, `last_sent_cmd_id` |
| Xe rẽ sai hướng | `prev_tag` sai → tính hướng sai | Kiểm tra `prev_tag` trong state |
| MQTT không kết nối | TLS cert / cổng sai | Dùng cổng 1883 để test không TLS |
| `[PLAN REJECT] Pin yeu` | `battery_blocking = true` | Gửi `{"c":"battery_unlock"}` |

### MQTT test nhanh (dùng MQTT Explorer hoặc mosquitto_pub)

```bash
# Gửi stop cho AGV01
mosquitto_pub -h iot.tot360.com.vn -p 8883 \
  --insecure -u iot_user -P d7xvk5pKkqsKKMd \
  -t "uagv/v2/VietDuc/AGV01/instantActions" \
  -m '{"c":"stop"}'

# Xem state của AGV01
mosquitto_sub -h iot.tot360.com.vn -p 8883 \
  --insecure -u iot_user -P d7xvk5pKkqsKKMd \
  -t "uagv/v2/VietDuc/+/state"
```

---

## 16. Cửa tự động (Gate Controller)

> Đây là giao thức **RIÊNG, MỚI**, dành cho bộ điều khiển cửa tự động (thiết bị
> ĐỘC LẬP với AGV — không phải ESP32-C5/Arduino gắn trên xe). Server (Python
> Manager) giao tiếp thẳng với bộ điều khiển cửa qua MQTT, không đi qua AGV.

### 16.1. Bối cảnh

Một số đoạn đường trên bản đồ đi qua 1 cửa tự động (kho lạnh, khu vực kiểm
soát ra/vào...). AGV phải dừng xin mở cửa trước khi băng qua, và server phải
ra lệnh đóng lại sau khi AGV đã qua hẳn — **hoàn toàn tự động, không cần người
xác nhận**. Cấu hình bản đồ: mỗi cửa gắn với **2 node liền kề** (2 phía của
cửa); AGV dừng ở node phía đang tiến tới để xin mở, đi qua node còn lại thì
server tự báo đóng.

### 16.2. MQTT Topics

```
gate/v1/{factory}/{door_id}/cmd     Server → Bộ điều khiển cửa   (lệnh mở/đóng)
gate/v1/{factory}/{door_id}/state   Bộ điều khiển cửa → Server   (trạng thái, RETAINED)
```

| Biến | Ví dụ | Ghi chú |
|------|-------|---------|
| `factory` | `VietDuc` | Cùng tên factory dùng cho AGV (biến môi trường `LINE_AGV_FACTORY`) |
| `door_id` | `gate1`, `gate2`,... | Quy ước CỐ ĐỊNH: `"gate" + số thứ tự`. Người tạo bản đồ chỉ nhập SỐ (1, 2, 3...) trên Web UI — hệ thống tự ghép thành `gate1`, `gate2`,... khi lưu, tránh gõ nhầm chữ hoa/thường/chính tả. Bộ điều khiển cửa cần đặt `door_id` của mình khớp ĐÚNG định dạng này (`gate` viết thường + số, không dấu cách) |

**`state` PHẢI publish với `retain=true`** — để server biết ngay trạng thái cửa
hiện tại nếu server restart giữa lúc cửa đang mở/đóng.

### 16.3. Lệnh MỞ/ĐÓNG — Server → Cửa

```json
{ "c": "open" }
{ "c": "close" }
```

| Field | Kiểu | Mô tả |
|-------|------|-------|
| `c` | string | `"open"` hoặc `"close"` |

### 16.4. Trạng thái cửa — Cửa → Server

```json
{ "state": "closed" }
{ "state": "opening" }
{ "state": "open" }
{ "state": "closing" }
{ "state": "error" }
```

| `state` | Khi nào publish |
|---------|-----------------|
| `closed` | Cửa đã đóng hoàn toàn (nghỉ, hoặc vừa đóng xong) |
| `opening` | Đang trong quá trình mở (ngay khi nhận lệnh `open`, TRƯỚC khi mở xong) |
| `open` | Đã mở HOÀN TOÀN (cảm biến/limit switch xác nhận) — **server chờ ĐÚNG tín hiệu này** để cho AGV băng qua |
| `closing` | Đang trong quá trình đóng |
| `error` | Kẹt, quá tải, cảm biến lỗi... — server sẽ DỪNG thử tự động, cần người kiểm tra |

**Quan trọng:** server chỉ coi là "mở xong" khi nhận đúng `state: "open"` — nếu
bộ điều khiển chỉ gửi `opening` mà không bao giờ gửi `open`, AGV sẽ đứng chờ
mãi (có retry, xem 16.5, nhưng vẫn cần cảm biến thật báo được `open`).

### 16.5. Timeout và Retry (phía server)

Nếu server gửi `open` mà không nhận được `state: "open"` sau **6 giây**, server
sẽ **gửi lại lệnh `open`** — tối đa **2 lần**. Bộ điều khiển cửa cần xử lý
lệnh `open` lặp lại một cách **an toàn (idempotent)**:
- Nếu đang mở dở (`opening`) mà nhận thêm `open` → có thể bỏ qua hoặc xác nhận
  lại, KHÔNG được gây ra hành vi bất thường (đảo chiều động cơ, kẹt...).
- Nếu đã `open` mà nhận thêm `open` → chỉ cần publish lại `state: "open"`.

Sau 2 lần gửi lại vẫn không thấy `open`, server dừng tự động thử và báo cần
kiểm tra thủ công — bộ điều khiển nên tận dụng `state: "error"` để báo lỗi
sớm hơn nếu tự phát hiện được sự cố (kẹt động cơ, quá dòng...), thay vì để
server phải chờ hết timeout.

### 16.6. Nhiều xe cùng dùng 1 cửa

Server tự theo dõi số AGV đang băng qua từng cửa — **chỉ gửi lệnh `close` khi
không còn AGV nào đang qua**. Bộ điều khiển cửa KHÔNG cần tự theo dõi việc
này, chỉ cần thực hiện đúng lệnh `open`/`close` server gửi và báo trạng thái
trung thực.

### 16.7. Sơ đồ luồng

```
AGV tiến gần cửa → dừng hẳn tại node trước cửa
        ↓
Server publish: gate/v1/{factory}/{door_id}/cmd = {"c":"open"}
        ↓
Cửa: publish state="opening" → (mở cơ khí) → publish state="open" (RETAINED)
        ↓
Server nhận state="open" → cho AGV đi tiếp, băng qua cửa
        ↓
AGV báo tag đã sang node phía bên kia cửa
        ↓
Server publish: gate/v1/{factory}/{door_id}/cmd = {"c":"close"}
   (CHỈ khi không còn AGV nào khác đang băng qua cửa này)
        ↓
Cửa: publish state="closing" → (đóng cơ khí) → publish state="closed"
```

### 16.8. Ví dụ code (bộ điều khiển cửa, tham khảo)

```python
import paho.mqtt.client as mqtt
import json

FACTORY = "VietDuc"
DOOR_ID = "gate1"
CMD_TOPIC   = f"gate/v1/{FACTORY}/{DOOR_ID}/cmd"
STATE_TOPIC = f"gate/v1/{FACTORY}/{DOOR_ID}/state"

def publish_state(client, state: str):
    client.publish(STATE_TOPIC, json.dumps({"state": state}), qos=1, retain=True)

def on_message(client, userdata, msg):
    data = json.loads(msg.payload)
    cmd = data.get("c")
    if cmd == "open":
        publish_state(client, "opening")
        # ... điều khiển động cơ mở cửa ...
        # khi cảm biến xác nhận mở hoàn toàn:
        publish_state(client, "open")
    elif cmd == "close":
        publish_state(client, "closing")
        # ... điều khiển động cơ đóng cửa ...
        publish_state(client, "closed")

client = mqtt.Client()
client.on_message = on_message
client.connect("iot.tot360.com.vn", 8883)
client.subscribe(CMD_TOPIC)
publish_state(client, "closed")   # trạng thái ban đầu khi khởi động
client.loop_forever()
```

### 16.9. Checklist cho đội firmware cửa

- [ ] Subscribe đúng topic lệnh: `gate/v1/{factory}/{door_id}/cmd`
- [ ] Publish trạng thái lên `gate/v1/{factory}/{door_id}/state` với `retain=true`
- [ ] Publish `state="open"` CHỈ khi cảm biến xác nhận mở hoàn toàn (không phải ngay khi bắt đầu mở)
- [ ] Xử lý lệnh `open`/`close` lặp lại an toàn (idempotent) — server có thể gửi lại
- [ ] Publish `state="closed"` ngay khi khởi động (trạng thái mặc định an toàn)
- [ ] Nếu phát hiện lỗi cơ khí, publish `state="error"` càng sớm càng tốt

---

## Phụ lục — Tóm tắt nhanh

### Checklist khi viết Python Manager mới

- [ ] Subscribe `uagv/v2/{factory}/+/state` và `+/connection`
- [ ] Parse `lastNodeId` (string) và `tag` (int) — cả hai đều là vị trí hiện tại
- [ ] Kiểm tra `ack` trong state để confirm plan đã được nhận
- [ ] Gửi `ack_event` ngay khi nhận `event` trong state
- [ ] Kiểm tra `battery_blocking` trước khi dispatch
- [ ] Plan bắt đầu từ thẻ **hiện tại** của xe (không phải thẻ tiếp theo)
- [ ] Luôn có `LIDAR_OFF` trước `TURN_L/R` và `LIDAR_ON` sau
- [ ] Không gửi plan > 6–7 node một lúc (rolling/windowed)
- [ ] Retry plan sau 4s nếu không nhận ACK (và xe không ở đầu plan)

### Giá trị mặc định tốc độ

| Hằng số | Giá trị | Khi dùng |
|---------|---------|---------|
| `SPEED_FAST` | 120 | Chạy thẳng |
| `SPEED_SLOW` | 60 | Trước/trong cua |
| `LOOKAHEAD` | 6 | Số node gửi trước |
| `RETRY_TIMEOUT` | 4.0s | Thời gian chờ ACK |
