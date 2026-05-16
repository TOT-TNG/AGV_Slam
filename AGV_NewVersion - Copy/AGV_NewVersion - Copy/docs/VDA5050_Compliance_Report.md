# Báo cáo Tuân thủ VDA5050 — Hệ thống AGV

> **Phiên bản chuẩn tham chiếu:** VDA5050 v2.0.0  
> **Ngày cập nhật:** 2026-04-04  
> **Trạng thái:** Đã nâng cấp — xem §4 để biết chi tiết  
> **Phạm vi:** Python Manager ↔ ESP32 ↔ Arduino Mega

---

## 1. Tổng quan VDA5050

VDA5050 là tiêu chuẩn giao tiếp giữa **Hệ thống quản lý xe AGV (FMS/MC)** và **xe AGV**, dùng giao thức **MQTT**. Tiêu chuẩn định nghĩa:

- Cấu trúc **topic MQTT** cố định: `{interface}/{majorVersion}/{manufacturer}/{serialNumber}/{topicName}`
- Định dạng **JSON message** với các trường header bắt buộc
- **6 loại topic** riêng biệt cho từng mục đích
- Cơ chế **state machine** và **xác nhận** chặt chẽ

---

## 2. Kiến trúc Hệ thống

```
Python Manager (FMS)
    │  MQTT  (VDA5050 topics)
    │
[MQTT Broker]
    │
ESP32 (MQTT↔UART Bridge)
    │  UART 115200 baud  (JSON nội bộ)
    │
Arduino Mega (AGV Controller)
    │
Hardware: Motor, RFID, LIDAR, HMI
```

**Phân công vai trò:**
- **Python Manager**: FMS — lập kế hoạch, gửi order/instantActions, nhận state
- **ESP32**: Bridge — forward MQTT→UART và UART→MQTT; thêm VDA5050 headers; quản lý connection topic
- **Arduino**: AGV Controller — thực thi plan, điều khiển motor, đọc RFID; gửi state qua UART

---

## 3. Cấu trúc Topic (Sau nâng cấp — VDA5050 §5.2)

### 3.1 Format chuẩn

```
uagv/v2/{manufacturer}/{serialNumber}/{topicName}
```

| Biến | Giá trị | VDA5050 field |
|------|---------|---------------|
| `interface` | `uagv` | Cố định theo chuẩn |
| `majorVersion` | `v2` | Phiên bản VDA5050 |
| `manufacturer` | `VietDuc` (config `factory`) | Tên nhà máy/nhà sản xuất |
| `serialNumber` | `AGV01` (config `id`) | ID xe |

### 3.2 Bảng topic đầy đủ

| Topic | Chiều | Mục đích | retain |
|-------|-------|----------|--------|
| `uagv/v2/VietDuc/AGV01/state` | AGV → FMS | Trạng thái tổng thể (~1Hz) | No |
| `uagv/v2/VietDuc/AGV01/order` | FMS → AGV | Gửi lộ trình (plan) | No |
| `uagv/v2/VietDuc/AGV01/instantActions` | FMS → AGV | Lệnh tức thì (run/stop/action...) | No |
| `uagv/v2/VietDuc/AGV01/connection` | AGV → FMS | Kết nối + Last Will | **Yes** |
| `uagv/v2/VietDuc/AGV01/factsheet` | AGV → FMS | Thông số kỹ thuật AGV | **Yes** |

> **Wildcard Python subscribe:**  
> `uagv/v2/VietDuc/+/state` — tất cả AGV state trong factory  
> `uagv/v2/VietDuc/+/connection` — theo dõi kết nối tất cả AGV

---

## 4. Đánh giá Tuân thủ (Sau nâng cấp)

### 4.1 ✅ Đã đạt / Đã nâng cấp

| Hạng mục | VDA5050 | Hiện trạng | File thay đổi |
|----------|---------|------------|---------------|
| Transport | MQTT | ✅ MQTT | — |
| **Topic format** | `uagv/v2/{mfr}/{sn}/...` | ✅ Đã chuẩn hóa | ESP32 C5/S3, Python agv_instance.py, main.py |
| **Mandatory header** | headerId, timestamp, version, manufacturer, serialNumber | ✅ ESP32 thêm vào mọi state message | ESP32 C5/S3 (`addVdaHeader()`) |
| **Connection topic + Last Will** | CONNECTIONBROKEN khi mất mạng | ✅ MQTT Will + publish ONLINE | ESP32 C5/S3 (`reconnect()`) |
| **Factsheet** | Thông số AGV, retain=true | ✅ Publish khi connect | ESP32 C5/S3 (`publishFactsheet()`) |
| **instantActions topic** | Topic riêng cho lệnh tức thì | ✅ Tách khỏi order | Python `send_command()`, `send_btn_pic()`, ... |
| **operatingMode** | AUTOMATIC/SEMIAUTOMATIC/MANUAL | ✅ Arduino gửi | Arduino `publishJson()` |
| **driving / paused** | bool | ✅ Arduino gửi | Arduino `publishJson()` |
| **errors[]** | Array với errorType/Level/Description | ✅ Array, obstacle detection | Arduino `publishJson()` |
| **safetyState** | eStop, fieldViolation | ✅ Arduino gửi | Arduino `publishJson()` |
| **nodeStates[]** | Danh sách node còn lại trong plan | ✅ Toàn bộ node còn lại (lookahead n node, cấu hình qua Python) | Arduino `publishJson()` |
| **orderId** | ID của order hiện tại | ✅ Từ lastRecvCmdId | Arduino `publishJson()` |
| **lastNodeId** | Node RFID cuối đọc được | ✅ String(currentTag) | Arduino `publishJson()` |
| **NTP timestamp** | ISO8601 trong mọi bản tin | ✅ ESP32 đồng bộ NTP pool.ntp.org | ESP32 C5/S3 (`getTimestamp()`) |
| **Connection state parsing** | Python nhận ONLINE/OFFLINE | ✅ `update_connection_state()` | Python agv_instance.py, main.py |
| **batteryState** | `batteryCharge`, `charging`, `batteryVoltage` | ✅ Cảm biến digital PIN_PIN_YEU — LOW=OK(80%), HIGH=Yếu(20%); AGV từ chối plan khi yếu | Arduino `publishJson()`, Python `agv_instance.py` |

---

### 4.2 ✅ Ghi chú về Order message format

**Order message format** sử dụng custom payload `{c:"plan", d:[{t,a,v}]}` gửi qua **đúng topic VDA5050** `uagv/v2/.../order`. Đây là **custom extension hợp lệ** — VDA5050 quy định tên topic, không cấm payload tùy chỉnh. Trong hệ thống khép kín (Python Manager ↔ Arduino), đây là lựa chọn tối ưu vì:
- AGV dò line RFID, không có tọa độ x/y → cấu trúc Node+Edge chuẩn không mang thêm giá trị
- Payload nhỏ gọn, ít overhead hơn Node+Edge → phù hợp UART 115200 baud
- Chỉ cần chuyển đổi sang Node+Edge nếu tích hợp FMS bên thứ ba

### 4.3 ⚠️ Đã nâng cấp một phần (hybrid)

| Hạng mục | VDA5050 chuẩn | Thực tế | Lý do |
| **lastNodeSequenceId** | Đơn điệu tăng trong toàn bộ order | Gửi `currentMissionIndex` (index trong plan hiện tại) | Không có khái niệm sequence toàn cục |
| **newBaseRequest** | AGV yêu cầu base mới khi gần hết | Luôn `false` (Python tự quản lý rolling segment) | FMS đã tự dispatch segment tiếp theo |

---

### 4.3 ❌ Không thể nâng cấp (thiếu phần cứng)

| Hạng mục | Lý do không thể | Ghi chú |
|----------|-----------------|---------|
| `agvPosition.x / y / theta` | Không có encoder / IMU | AGV dò line, vị trí chỉ biết tại thẻ RFID |
| `velocity.vx / vy / omega` | Không có encoder tốc độ | Không đo được vận tốc thực |
| `batteryState.batteryVoltage` | Không có ADC đo điện áp | Luôn = 0.0 (cảm biến digital, không phải analog) |
| `loads[]` | Không có cảm biến tải | Thêm được nếu lắp load cell |
| `distanceSinceLastNode` | Không có encoder quãng đường | Luôn = 0 |
| `visualization topic` | Cần tọa độ thực thời | Phụ thuộc agvPosition |

---

## 5. Chi tiết Bản tin

### 5.1 State (AGV → FMS) — `uagv/v2/{factory}/{id}/state`

```json
{
  "headerId": 42,
  "timestamp": "2026-04-04T10:30:00.000Z",
  "version": "2.0.0",
  "manufacturer": "VietDuc",
  "serialNumber": "AGV01",

  "lastNodeId": "107",
  "lastNodeSequenceId": 3,
  "orderId": "a3f7b2c1",
  "operatingMode": "AUTOMATIC",
  "driving": true,
  "paused": false,
  "newBaseRequest": false,

  "errors": [
    {
      "errorType": "OBSTACLE",
      "errorLevel": "WARNING",
      "errorDescription": "Obstacle detected by sensor"
    }
  ],

  "safetyState": {
    "eStop": false,
    "fieldViolation": true
  },

  "nodeStates": [
    {"nodeId": "107", "sequenceId": 3, "released": true},
    {"nodeId": "43",  "sequenceId": 4, "released": true},
    {"nodeId": "43",  "sequenceId": 5, "released": true}
  ],

  "batteryState": {
    "batteryCharge": 80,
    "charging": false,
    "batteryVoltage": 0.0,
    "reach": 0
  },
  "battery_low": false,

  "tag": 107,
  "prev_tag": 109,
  "status": "auto",
  "action_info": "running",
  "ack": "a3f7b2c1",
  "event": "",
  "rssi": -65,
  "mac": "A1B2C3D4E5F6"
}
```

> **Ghi chú:** Các trường `tag`, `status`, `action_info`, `ack`, `event` là backward-compat nội bộ, không thuộc VDA5050.

---

### 5.2 Order (FMS → AGV) — `uagv/v2/{factory}/{id}/order`

```json
{
  "c": "plan",
  "d": [
    {"t": 109, "a": 4, "v": 60},
    {"t": 109, "a": 8, "v": 0},
    {"t": 109, "a": 3, "v": 0},
    {"t": 107, "a": 6, "v": 0},
    {"t": 43,  "a": 4, "v": 120},
    {"t": 43,  "a": 3, "v": 0}
  ],
  "id": "a3f7b2c1"
}
```

> Topic chuẩn VDA5050, nội dung là custom extension (không dùng Node+Edge structure).

---

### 5.3 InstantActions (FMS → AGV) — `uagv/v2/{factory}/{id}/instantActions`

```json
{"c": "run"}
{"c": "stop"}
{"c": "reset"}
{"c": "ack_event", "d": "confirm"}
{"c": "action", "a": 6, "v": 0}
{"c": "set_btn_pic", "line": 3, "pic": 28}
{"c": "hmi", "cmd": "page 1"}
```

---

### 5.4 Connection (AGV → FMS) — `uagv/v2/{factory}/{id}/connection`

```json
{
  "headerId": 0,
  "timestamp": "2026-04-04T10:30:00.000Z",
  "version": "2.0.0",
  "manufacturer": "VietDuc",
  "serialNumber": "AGV01",
  "connectionState": "ONLINE"
}
```

`connectionState`: `ONLINE` | `OFFLINE` | `CONNECTIONBROKEN`  
`CONNECTIONBROKEN` là **MQTT Last Will** — broker tự gửi khi mất kết nối.

---

### 5.5 Factsheet (AGV → FMS) — `uagv/v2/{factory}/{id}/factsheet` (retain=true)

```json
{
  "headerId": 1,
  "timestamp": "2026-04-04T10:30:00.000Z",
  "version": "2.0.0",
  "manufacturer": "VietDuc",
  "serialNumber": "AGV01",
  "agvClass": "CARRIER",
  "maxLoadMass": 500,
  "maxSpeed": 1.5,
  "maxRotationSpeed": 0.5,
  "localizationType": "RFID",
  "navigationMode": "GUIDED",
  "batteryStateAvailable": true,
  "positionControlMode": "NONE",
  "agvGeometry": {"width": 0.6, "length": 1.2}
}
```

---

## 6. Sơ đồ Luồng Giao tiếp (Sau nâng cấp)

```
Python Manager (FMS)                          ESP32 (Bridge)          Arduino (AGV)
        │                                          │                       │
        │── MQTT publish ──────────────────────►   │                       │
        │   uagv/v2/VietDuc/AGV01/order            │── UART JSON ────────► │
        │   {"c":"plan","d":[...],"id":"abc"}       │   (forward)           │  listenJson()
        │                                          │                       │  → parse plan
        │── MQTT publish ──────────────────────►   │                       │
        │   uagv/v2/VietDuc/AGV01/instantActions   │── UART JSON ────────► │
        │   {"c":"run"}                            │   (forward)           │  → deba()
        │                                          │                       │
        │◄── MQTT publish ──────────────────────   │◄── UART JSON ─────────│
        │   uagv/v2/VietDuc/AGV01/state            │   (Arduino state)     │  publishJson()
        │   {headerId, timestamp, version,         │   +VDA5050 headers    │
        │    lastNodeId, operatingMode,            │   +rssi, mac          │
        │    driving, paused, errors[],            │                       │
        │    safetyState, nodeStates[], ...}       │                       │
        │                                          │                       │
        │◄── MQTT publish (Last Will / retain) ─── │                       │
        │   uagv/v2/VietDuc/AGV01/connection       │ (on connect/disconnect)│
        │   {"connectionState":"ONLINE"}           │                       │
        │                                          │                       │
        │◄── MQTT publish (retain) ─────────────── │                       │
        │   uagv/v2/VietDuc/AGV01/factsheet        │ (on connect)          │
        │   {agvClass, maxSpeed, ...}              │                       │
```

---

## 7. Bảng Tổng hợp Cuối (Sau nâng cấp)

| Hạng mục | VDA5050 v2.0.0 | Hệ thống hiện tại | Trạng thái |
|----------|----------------|-------------------|------------|
| Transport | MQTT | MQTT | ✅ |
| Topic format | `uagv/v2/{mfr}/{sn}/topic` | `uagv/v2/{factory}/{id}/topic` | ✅ |
| Mandatory header | headerId, timestamp, version... | ✅ Thêm bởi ESP32 | ✅ |
| Order topic | `.../order` | ✅ | ✅ |
| InstantActions topic | `.../instantActions` | ✅ | ✅ |
| State topic | `.../state` | ✅ | ✅ |
| Connection + Last Will | `.../connection` | ✅ | ✅ |
| Factsheet | `.../factsheet` | ✅ retain | ✅ |
| operatingMode chuẩn | AUTOMATIC/SEMIAUTOMATIC/MANUAL | ✅ | ✅ |
| driving / paused | bool | ✅ | ✅ |
| errors[] | Array với errorType/Level | ✅ | ✅ |
| safetyState | eStop, fieldViolation | ✅ | ✅ |
| nodeStates[] | Toàn bộ node còn lại trong plan | ✅ Gửi đầy đủ, lookahead n node | ✅ |
| orderId | ✅ từ cmd_id | ✅ | ✅ |
| lastNodeId | string, RFID tag | ✅ | ✅ |
| NTP timestamp ISO8601 | ✅ | ✅ | ✅ |
| Order message format | Custom payload trong topic chuẩn | ✅ Topic đúng, payload custom extension hợp lệ | ✅ |
| agvPosition x/y/theta | ❌ Không có encoder/IMU | N/A | ❌ |
| velocity | ❌ Không có encoder tốc độ | N/A | ❌ |
| batteryState | ✅ Cảm biến digital PIN_PIN_YEU (D14) | `batteryCharge` 20%/80%; AGV từ chối plan khi pin yếu | ✅ |
| loads[] | ⏳ Pending — sẽ triển khai sau | Cần thêm cảm biến | ⏳ |
| visualization topic | ❌ Phụ thuộc agvPosition | N/A | ❌ |

**Tổng kết:** 17/20 hạng mục ✅ đạt | 1/20 ⏳ pending (loads[]) | 2/20 ❌ (thiếu phần cứng encoder/IMU)

---

## 8. Hướng dẫn Cấu hình

### 8.1 Trong ESP32 firmware (`#define`)

```cpp
#define AGV_ID   "AGV01"      // serialNumber — khớp với config Python
#define FACTORY  "VietDuc"    // manufacturer — khớp với config Python
```

### 8.2 Trong Python `config.json`

```json
{
  "factory":  "VietDuc",
  "agvs": [
    {"id": "AGV01", ...}
  ]
}
```

Topic tự động sinh: `uagv/v2/VietDuc/AGV01/state` (không cần cấu hình tay).

---

*Tài liệu cập nhật tự động từ mã nguồn: `python-manager/agv_instance.py`, `python-manager/main.py`, `arduino-firmware/src/main.ino`, `esp-firmware/src/main.ino`, `esp-firmware-S3/src/main.ino`.*
