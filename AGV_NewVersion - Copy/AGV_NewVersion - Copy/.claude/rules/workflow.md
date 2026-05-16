# WORKFLOW — Quy trình làm việc dự án AGV

## 1. Khi nhận một task mới

1. **Xác định layer bị ảnh hưởng**: Arduino / ESP32 / Python Manager / Tất cả.
2. **Đọc file liên quan** trước khi sửa — không đoán mò cấu trúc.
3. **Kiểm tra tác động cross-layer**: thay đổi Action Code hoặc JSON schema buộc phải cập nhật cả 3 layer.
4. **Không thêm tính năng ngoài yêu cầu** — đặc biệt với Arduino (RAM hạn chế).

## 2. Quy trình thêm tính năng mới

```
1. Thêm Action Code mới → cập nhật bảng trong CLAUDE.md
2. Sửa Arduino firmware → thêm case trong executeSingleAction()
3. Sửa Python Manager → thêm constant SYSTEM_ACTIONS / ACTION_MAP
4. Test: Python gửi plan → ESP bridge → Arduino thực hiện → Python nhận state
```

## 3. Quy trình debug giao tiếp UART

```
Bước 1: Mở Serial Monitor Arduino (115200) — xem [UART RX] log
Bước 2: Mở Serial Monitor ESP32 (115200) — xem [MQTT→UART] log
Bước 3: Nếu ESP log nhận MQTT nhưng Arduino không thấy → kiểm tra dây TX5→RX3(pin15)
Bước 4: Nếu không có log MQTT → kiểm tra broker kết nối (log [MQTT] Connected!)
Bước 5: Gửi thủ công {"c":"ping"} từ MQTT client → ESP phải forward → Arduino log [CMD] c=ping
```

## 4. Quy trình mở rộng sang AGV mới (QR / SLAM)

```
1. Tạo AGV class mới kế thừa AGVBase (python-manager/agv_instance.py)
2. Override phương thức _parse_state() cho format JSON của loại AGV mới
3. Đăng ký MQTT topic riêng: uagv/v2/{FACTORY}/{NEW_AGV_ID}/...
4. TrafficManager giữ nguyên — chỉ làm việc với node/edge trừu tượng
5. Map vẫn dùng NetworkX DiGraph — thêm thuộc tính 'agv_type' vào node nếu cần
```

## 5. Quy tắc commit

- Không commit file `.env`, credentials, hoặc địa chỉ IP thực.
- Mỗi commit chỉ thuộc 1 layer: `[arduino]`, `[esp32]`, `[python]`, `[config]`.
- Trước khi sửa Arduino firmware: ghi lại version đang chạy ổn định.

## 6. File quan trọng cần biết

| File | Vai trò |
|------|---------|
| `arduino-firmware/src/main.ino` | Toàn bộ firmware Arduino |
| `esp-firmware/src/main.ino` | ESP32-C5 MQTT bridge |
| `python-manager/agv_instance.py` | Logic 1 xe AGV |
| `python-manager/traffic/traffic_manager.py` | Điều phối đường đi |
| `python-manager/map_widget.py` | GUI bản đồ |
| `python-manager/map.json` | Dữ liệu bản đồ |
| `logs/activity_log.csv` | Lịch sử chuyến đi |
