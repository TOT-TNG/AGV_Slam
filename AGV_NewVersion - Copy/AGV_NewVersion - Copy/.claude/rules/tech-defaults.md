# TECH DEFAULTS — Mặc định kỹ thuật từng layer

## 1. Arduino Mega 2560

### Thư viện
- `ArduinoJson` v6 (KHÔNG dùng v7 — RAM hạn chế trên Mega)
- `ModbusMaster` (nếu có driver Modbus)
- `Nextion` (HMI display, Serial2 @ 9600 baud)

### UART Assignment
| Serial | Dùng cho | Baud |
|--------|---------|------|
| Serial (USB) | Debug log | 115200 |
| Serial1 | RFID JY-L8800 | 9600 |
| Serial2 | HMI Nextion | 9600 |
| Serial3 (TX3=14, RX3=15) | ESP32 bridge | 115200 |

### Pinout chuẩn
| Component | Pin | Type |
|-----------|-----|------|
| Lidar Zone 1 (an toàn) | 3 | INPUT_PULLUP |
| Lidar Zone 2 | 6 | INPUT_PULLUP |
| Bumper | 9 | INPUT_PULLUP |
| Brake (phanh) | 26 | OUTPUT — LOW=mở, HIGH=đóng |
| Charge Relay | 34 | OUTPUT |
| Tower Light Yellow | 31 | OUTPUT |
| Tower Light Green | 32 | OUTPUT |
| PWM Motor Trái | 10 | OUTPUT |
| PWM Motor Phải | 11 | OUTPUT |
| Direction Motor Trái | 44 | OUTPUT |
| Direction Motor Phải | 45 | OUTPUT |

### Quy ước code Arduino
- Global variables: `camelCase` (VD: `motorRunning`, `currentTag`)
- Defines/Macros: `UPPER_CASE` (VD: `SPEED_FAST`, `ACT_TURN_L`)
- Tuyệt đối không dùng `String` object trong vòng lặp PID → dùng `char[]`
- `SERIAL_RX_BUFFER_SIZE 1024` phải khai báo TRƯỚC mọi `#include`
- `listenJson()` phải là non-blocking (accumulator pattern, không dùng `readStringUntil`)

### Safety logic (bất biến)
```cpp
bool isSafeToRun() {
  return !MC_STOP_BTN && !MC_EMG && !MC_BUMPER && !MC_LIDAR1 && !MC_ERROR;
}
// checkSafety() gọi trong mỗi iteration của loop() — KHÔNG được skip
```

## 2. ESP32-C5

### Thư viện (PlatformIO)
```ini
lib_deps =
    bblanchon/ArduinoJson @ ^6.21.3
    knolleary/PubSubClient @ ^2.8
platform = https://github.com/pioarduino/platform-espressif32/releases/download/55.03.37/platform-espressif32.zip
```

### UART tới Arduino
- UART1: RX=GPIO4, TX=GPIO5
- Baud: 115200, SERIAL_8N1
- Nối dây: ESP GPIO5(TX) → Arduino pin15(RX3) | ESP GPIO4(RX) ← Arduino pin14(TX3)

### MQTT chuẩn
- Broker: cấu hình trong `platformio.ini` hoặc `config.h` — KHÔNG hardcode trong `main.ino`
- Port: 8883 (TLS) hoặc 1883 (local test)
- `setInsecure()` được phép với broker nội bộ
- Không dùng `configTime()` / SNTP — gây crash trên ESP-IDF 5.x
- `setBufferSize(2048)` — plan JSON có thể lớn hơn default 256 bytes

### Quy ước code ESP32
- ESP32 **chỉ bridge**, không chứa logic nghiệp vụ
- Mọi quyết định (reservation, re-route, speed) thực hiện ở Python
- Nhận JSON từ MQTT → forward nguyên vẹn xuống Arduino UART
- Nhận JSON từ Arduino UART → đóng gói VDA5050 header → publish MQTT

## 3. Python Manager

### Thư viện
```bash
pip install paho-mqtt networkx
# tkinter có sẵn trong Python standard library
```

### Quy ước code Python
- Class: `PascalCase` (`TrafficManager`, `AgvInstance`)
- Function/variable: `snake_case` (`current_tag`, `find_path`)
- Constants: `UPPER_CASE` (`SPEED_FAST = 200`, `LOOKAHEAD = 5`)
- Luôn bọc parse JSON trong `try/except json.JSONDecodeError`
- Dùng `self.after(ms, callback)` thay `time.sleep()` trong Tkinter

### Cấu trúc bản đồ (map.json)
```python
# Node attributes (NetworkX)
G.nodes[n]['x']       # float, tọa độ thực (mét)
G.nodes[n]['y']       # float
G.nodes[n]['type']    # "normal"|"intersection"|"station"|"charger"
G.nodes[n]['actions'] # list[dict] — lệnh thực hiện tại node

# Edge attributes
G.edges[u,v]['weight']       # float, khoảng cách (mét)
G.edges[u,v]['direction']    # "fwd"|"bwd"|"both"
G.edges[u,v]['actions']      # lệnh khi BẮT ĐẦU vào cạnh
G.edges[u,v]['end_actions']  # lệnh khi KẾT THÚC cạnh
```

### Log format (activity_log.csv)
```
timestamp, agv_id, from_node, to_node, duration_s, status
2026-01-01T10:00:00, AGV01, 101, 205, 45.2, completed
```

## 4. Cấu hình tốc độ (mặc định)
| Biến | Giá trị | Ghi chú |
|------|---------|---------|
| `SPEED_FAST` | 200 | Chạy thẳng |
| `SPEED_SLOW` | 120 | Trước/trong cua |
| `LOOKAHEAD` | 5 | Số node gửi trước |
| `RESERVATION_TIMEOUT` | 30s | Thời gian chờ tối đa |
| `HEARTBEAT_INTERVAL` | 1000ms | Arduino gửi state định kỳ |
