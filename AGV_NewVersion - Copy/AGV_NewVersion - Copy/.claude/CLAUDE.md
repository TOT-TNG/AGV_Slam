# AGV FLEET MANAGEMENT SYSTEM — BỘ NÃO DỰ ÁN

## 1. Kiến trúc 3 lớp (System Overview)

```
[Python Manager] ←─ MQTT ─→ [ESP32-C5] ←─ UART/JSON ─→ [Arduino Mega 2560]
 Fleet Manager              Gateway                      Low-level Controller
 VDA5050 Server             WiFi Bridge                  Motor / Sensor / Safety
```

| Layer | Vai trò | File chính |
|-------|---------|-----------|
| **Arduino Mega 2560** | Điều khiển vận hành thực (motor, sensor, PID, safety) | `arduino-firmware/src/main.ino` |
| **ESP32-C5** | Bridge MQTT ↔ UART, không xử lý logic | `esp-firmware/src/main.ino` |
| **Python Manager** | Fleet Management, Pathfinding, Traffic, GUI | `python-manager/` |

> Chi tiết từng lớp: xem `.claude/rules/design.md`
> Quy tắc lập trình: xem `.claude/rules/tech-defaults.md`
> Cách làm việc: xem `.claude/rules/workflow.md`

## 2. Giao thức giao tiếp (Protocol)

### MQTT Topics (VDA5050-compatible)
- `uagv/v2/{FACTORY}/{AGV_ID}/order` — Server → AGV (plan)
- `uagv/v2/{FACTORY}/{AGV_ID}/instantActions` — Server → AGV (lệnh tức thời)
- `uagv/v2/{FACTORY}/{AGV_ID}/state` — AGV → Server (trạng thái)
- `uagv/v2/{FACTORY}/{AGV_ID}/connection` — Last Will / ONLINE

### JSON UART (ESP32 ↔ Arduino, 115200 baud)
```json
// Server → Arduino (qua ESP32): Plan
{"c":"plan","id":"uuid","d":[{"t":101,"a":3,"v":0},{"t":102,"a":6,"v":0}]}

// Server → Arduino (qua ESP32): Lệnh tức thời
{"c":"stop"} | {"c":"run"} | {"c":"reset"}

// Arduino → Server (qua ESP32): Trạng thái
{"tag":101,"status":"auto","error":"","action_info":"running","ack":"uuid"}
```

## 3. Action Codes (đồng bộ Python ↔ Arduino)

| Code | Tên | Mô tả |
|------|-----|-------|
| 1 | WAIT_SYS | Chờ hệ thống |
| 2 | WAIT_USER | Chờ nút bấm người dùng |
| 3 | RUN | Chạy thẳng |
| 4 | SPEED | Cài tốc độ (v = 0–255) |
| 5 | TURN_R | Rẽ phải |
| 6 | TURN_L | Rẽ trái |
| 7 | REVERSE | Chạy lùi |
| 8 | ROTATE_180 | Quay 180° |
| 11 | CHARGE | Sạc pin tự động |
| 20 | LIDAR_OFF | Tắt cảm biến vật cản |
| 21 | LIDAR_ON | Bật cảm biến vật cản |
| 28 | BRAKE_ON | Đóng phanh |
| 29 | BRAKE_OFF | Mở phanh |

## 4. Quy tắc bắt buộc

1. **Safety first**: `checkSafety()` luôn có độ ưu tiên cao nhất trên Arduino.
2. **Non-blocking**: Không dùng `delay()` trong loop Arduino hay `time.sleep()` trong GUI Python.
3. **JSON only**: Mọi giao tiếp ESP↔Arduino dùng JSON, không dùng format cũ `<TOPIC:ID:DATA:ACK>`.
4. **VDA5050 alignment**: Mọi tính năng mới phải tương thích chuẩn VDA5050 v2.0.0.
5. **Mỗi layer làm đúng việc**: Arduino KHÔNG chứa logic nghiệp vụ; Python KHÔNG điều khiển motor trực tiếp.
