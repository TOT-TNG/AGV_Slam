---
name: agv-debug
description: Debug hệ thống AGV end-to-end — từ UART không giao tiếp, MQTT mất kết nối, đến xe không nhận plan hoặc dừng giữa đường. Dùng khi cần chẩn đoán lỗi nhanh.
---

# Skill: AGV Debug

## Khi nào dùng
- Arduino không nhận được data từ ESP32
- MQTT không kết nối được
- Xe nhận plan nhưng không di chuyển
- Xe dừng giữa đường không rõ lý do
- JSON parse lỗi trên Arduino

## Sơ đồ debug nhanh (Flow)

```
Vấn đề: Arduino không nhận data từ ESP
    │
    ├─ Kiểm tra Serial Monitor ESP: có "[MQTT] Connected!" không?
    │      Không → MQTT chưa kết nối → xem mục [MQTT Debug]
    │      Có ↓
    ├─ Publish test message lên topic order
    │      ESP log có "[MQTT→UART] ... len=XX" không?
    │      Không → Sai topic → kiểm tra topic name
    │      Có ↓
    ├─ Arduino Serial Monitor có "[UART RX] len=XX" không?
    │      Không → Vấn đề phần cứng UART → xem [UART Debug]
    │      Có ↓
    └─ Arduino log có "[CMD] c=plan" không?
           Không → JSON parse lỗi → xem [JSON Debug]
           Có → Logic lỗi → xem [Logic Debug]
```

## [MQTT Debug]

```python
# Kiểm tra kết nối broker
# Serial Monitor ESP phải thấy:
# [MQTT] Connecting iot.tot360.com.vn:8883
# [MQTT] Connected!           ← nếu thấy dòng này = OK
# [MQTT] Failed rc=-2         ← timeout, broker không phản hồi
# [MQTT] Failed rc=-4         ← sai credentials
# [MQTT] Failed rc=5          ← unauthorized

# Test nhanh bằng mosquitto_pub:
mosquitto_pub -h iot.tot360.com.vn -p 8883 --cafile ca.crt \
  -u iot_user -P d7xvk5pKkqsKKMd \
  -t "uagv/v2/VietDuc/AGV01/instantActions" \
  -m '{"c":"stop"}'

# Nếu broker nội bộ (port 1883, không TLS):
# Sửa esp-firmware/src/main.ino:
# const int MQTT_PORT = 1883;
# WiFiClient plainClient;  // thay WiFiClientSecure
# PubSubClient mqttClient(plainClient);
```

## [UART Debug]

```
Kiểm tra phần cứng:
1. Đo voltage TX ESP (GPIO5) khi idle: phải ~3.3V
2. Đo voltage RX Arduino (pin15) khi idle: phải nhận ~3.3V
3. Kiểm tra GND chung: Arduino GND và ESP GND nối nhau chưa?
4. Dây nối đúng chiều:
   ESP GPIO5 (TX) → Arduino pin15 (RX3)
   ESP GPIO4 (RX) ← Arduino pin14 (TX3)

Test UART software:
// Thêm vào loop() của ESP để test:
ArduinoUART.println("{\"c\":\"ping\"}");  // Gửi ping định kỳ
// Arduino phải log: [CMD] c=ping

// Nếu Arduino không thấy gì:
Serial.print("[DBG] UART avail=");
Serial.println(UART_ESP.available());  // Phải > 0 khi ESP gửi
```

## [JSON Debug]

```cpp
// Arduino: thêm log chi tiết trong listenJson()
Serial.print(F("[RAW] len=")); Serial.print(rxLen);
Serial.print(F(" hex: "));
for(int i=0;i<min(rxLen,20);i++) {
  Serial.print((uint8_t)_ubuf[i], HEX);
  Serial.print(' ');
}
Serial.println();

// Các lỗi JSON phổ biến:
// "IncompleteInput" → JSON bị cắt giữa chừng
//   → Nguyên nhân: MQTT buffer ESP nhỏ hơn plan JSON
//   → Fix: mqttClient.setBufferSize(2048) trong ESP setup()

// "InvalidInput" → có ký tự rác trước '{'
//   → Nguyên nhân: println() gửi \r\n, _ubuf bắt đầu bằng \r
//   → Fix: listenJson() đã skip ký tự != '{' — kiểm tra lại logic

// "NoMemory" → StaticJsonDocument quá nhỏ
//   → Fix: tăng kích thước doc: StaticJsonDocument<2048> doc;
```

## [Logic Debug]

```cpp
// Arduino không thực hiện action sau khi nhận plan:
// 1. Kiểm tra currentTag có khớp tag trong plan không:
Serial.print(F("[DBG] currentTag=")); Serial.print(currentTag);
Serial.print(F(" plan[0].tag=")); Serial.println(missionPlan[0].tag);

// 2. Kiểm tra safety flags:
Serial.print(F("[SAFETY] STOP=")); Serial.print(digitalRead(STOP_BTN));
Serial.print(F(" EMG=")); Serial.print(digitalRead(EMG_PIN));
Serial.print(F(" BUMPER=")); Serial.print(digitalRead(CB_VACHAM));
Serial.print(F(" LIDAR1=")); Serial.println(digitalRead(CBVC1));

// 3. Xe dừng giữa đường — kiểm tra WAIT_SYS:
// Nếu action = 1 (WAIT_SYS) → xe đang chờ Python gửi lệnh tiếp
// Python cần publish: {"c":"run"} hoặc plan window tiếp theo
```

## Công cụ test nhanh

```python
# python-manager/tools/test_mqtt.py
import paho.mqtt.client as mqtt, json, time

client = mqtt.Client()
client.connect("192.168.1.100", 1883)  # broker local

# Gửi ping test
client.publish("uagv/v2/VietDuc/AGV01/instantActions",
               json.dumps({"c": "ping"}))

# Gửi plan nhỏ test
test_plan = {
    "c": "plan", "id": "test0001",
    "d": [{"t": 101, "a": 3, "v": 0}, {"t": 102, "a": 1, "v": 0}]
}
client.publish("uagv/v2/VietDuc/AGV01/order", json.dumps(test_plan))
```
