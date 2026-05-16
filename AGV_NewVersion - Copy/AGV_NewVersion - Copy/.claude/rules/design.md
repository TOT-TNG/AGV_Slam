# DESIGN — Kiến trúc & Quyết định thiết kế

## 1. State Machine Arduino (2 tầng)

```
Tầng 1: Tag Manager
  IDLE ──(nhận plan)──→ TRACKING ──(đọc RFID khớp tag)──→ MATCHED
    ↑                                                          │
    └────────────────────(hoàn thành tất cả tasks)────────────┘

Tầng 2: Command Executor (chạy khi MATCHED)
  tasks[0] → tasks[1] → ... → tasks[n] → Quay về TRACKING
  Mỗi task: SPEED/DIR/TURN (tức thời) | STOP | WAIT_HMI | WAIT_TIME | LIFT/CONV (blocking có timeout)
```

**Nguyên tắc**: `checkSafety()` có thể interrupt bất kỳ state nào → force IDLE + dừng motor.

## 2. Windowed Navigation (Python → Arduino)

```
Không gửi toàn bộ route một lần. Chỉ gửi lookahead = 5 node tiếp theo.
Khi AGV báo đã qua node N → Python gửi tiếp đoạn kế.

Lợi ích:
- Giảm RAM Arduino (plan chứa tối đa ~500 bytes)
- Cho phép re-route động mà không cần flush toàn bộ plan
- AGV vẫn di chuyển liên tục khi đường thẳng
```

## 3. Reservation System (Tránh va chạm)

```python
# Khi AGV A muốn đi qua node N:
if traffic_manager.reserve(node=N, agv="A"):
    send_plan_to_A()          # được phép
else:
    insert WAIT_SYS at node_before_N   # chặn tại node trước
    retry sau 1-2 giây

# Khi AGV A rời node N:
traffic_manager.release(node=N, agv="A")
```

**Deadlock prevention**: Phát hiện 2 xe đối đầu trên cạnh 2 chiều → xe có ưu tiên thấp hơn nhường đường.

## 4. Bản đồ (NetworkX DiGraph)

```json
// Node
{"id": 101, "x": 1.5, "y": 0.0, "type": "normal|station|intersection|charger",
 "actions": [{"a": 3, "v": 0}]}

// Edge
{"u": 101, "v": 102, "weight": 1.5, "direction": "fwd|bwd|both",
 "actions": [{"a": 4, "v": 150}],
 "end_actions": [{"a": 26, "v": 0}]}
```

**Type node**:
- `normal`: node thường trên đường đi
- `intersection`: giao lộ — yêu cầu reservation
- `station`: trạm giao/nhận hàng
- `charger`: trạm sạc tự động

## 5. Mở rộng đa loại AGV (VDA5050)

```
AGVBase (abstract)
  ├── LineFolowingAGV   ← hiện tại (RFID tag + line từ)
  ├── QrAGV             ← tương lai (QR code navigation)
  └── SlamAGV           ← tương lai (SLAM + LiDAR map)

Điểm chung (VDA5050 v2.0.0):
  - Cùng MQTT topic structure: uagv/v2/{factory}/{agvId}/...
  - Cùng state JSON schema (nodeStates, edgeStates, batteryState)
  - Cùng TrafficManager (node/edge reservation)
  - Khác nhau: cách localize (RFID vs QR vs SLAM pose)
```

## 6. Auto Speed Injection

```python
# Python tự động giảm tốc trước cua, tăng tốc sau cua
def inject_speed(path_nodes):
    for i in range(1, len(path_nodes) - 1):
        angle = compute_angle(path_nodes[i-1], path_nodes[i], path_nodes[i+1])
        if angle < 150:                        # góc cua sắc
            path_nodes[i-1].prepend(ACT_SPEED, SPEED_SLOW)  # giảm trước cua
            path_nodes[i+1].prepend(ACT_SPEED, SPEED_FAST)  # tăng sau cua
```

## 7. Quyết định thiết kế quan trọng

| Quyết định | Lý do |
|-----------|-------|
| ESP32 chỉ là bridge, không xử lý logic | Đơn giản hóa firmware ESP, dễ thay bằng hardware khác |
| JSON thay vì custom protocol | Dễ debug, dễ mở rộng, tương thích VDA5050 |
| Windowed path (lookahead=5) | Tiết kiệm RAM Arduino, cho phép re-route động |
| NetworkX DiGraph | Thuật toán path phong phú (Dijkstra, A*), dễ serialize sang JSON |
| VDA5050 topic từ đầu | Không phải refactor khi thêm QR/SLAM AGV sau này |
