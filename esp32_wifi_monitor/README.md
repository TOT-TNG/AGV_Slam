# ESP32-C5 WiFi 5GHz Signal Monitor

Firmware ESP-IDF cho ESP32-C5: kiểm tra liên tục cường độ tín hiệu WiFi 5GHz,
đẩy dữ liệu về backend `mqtt_Server` (qua Cloud Gateway trên VPS) để vẽ biểu
đồ phổ tín hiệu và cảnh báo khi tín hiệu yếu.

## Kiến trúc dữ liệu

```
ESP32-C5 ──HTTPS──▶ https://iot.tot360.com.vn/acs/api/wifi/report   (mẫu RSSI liên tục)
         ──HTTPS──▶ https://iot.tot360.com.vn/acs/api/wifi/alert    (sự kiện yếu/outage/phục hồi)
                     header: X-Gateway-Key: <key của nhà máy>
                            │
                            ▼
         Cloud Gateway (VPS, cloud_gateway/gateway/gateway.py)
         forward theo X-Gateway-Key tới đúng nhà máy qua tunnel frp
                            │
                            ▼
         mqtt_Server/main.py (port 8000, tại nhà máy)
         lưu vào bảng wifi_signal_samples / wifi_signal_events
         trong cùng DB Postgres TOT_AGV với dữ liệu AGV
                            │
                            ▼
         Web_UI (Dash, port 8050) → sidebar "Tín hiệu WiFi"
         /assets/wifi_signal.html — biểu đồ + cảnh báo
```

`X-Gateway-Key` dùng ở đây **chính là** key định tuyến sẵn có của nhà máy
trên Cloud Gateway (không phải bí mật riêng cho thiết bị WiFi monitor) —
gateway dựa vào key này để biết forward request tới nhà máy nào.

## Logic cảnh báo (đúng theo yêu cầu)

- Đo RSSI mỗi `WIFI_MON_SAMPLE_INTERVAL_S` giây (mặc định 10s), luôn gửi mẫu
  về `/api/wifi/report` — nguồn cho biểu đồ phổ tín hiệu.
- RSSI < ngưỡng yếu (`WIFI_MON_RSSI_WEAK`, mặc định -70dBm) → chuyển trạng
  thái **WEAK**, gửi cảnh báo `weak_signal` ngay, sau đó **1 phút/lần**
  (`WIFI_MON_ALERT_INTERVAL_S`) nếu vẫn còn yếu.
- Sau **5 cảnh báo liên tiếp** (`WIFI_MON_OUTAGE_ALERT_COUNT`) mà chưa hồi
  phục → chuyển **OUTAGE**, bắt đầu tính giờ, gửi sự kiện `outage_start`.
- Khi RSSI ≥ ngưỡng tốt (`WIFI_MON_RSSI_GOOD`, mặc định -65dBm) → gửi sự
  kiện `recovered` (kèm `outage_seconds` nếu đã từng vào OUTAGE), quay về
  **GOOD**.

## Phạm vi v1 — giới hạn đã biết

- "Tín hiệu yếu" nghĩa là RSSI thấp **trong khi vẫn còn kết nối AP**. Khi
  mất kết nối hoàn toàn (`WIFI_EVENT_STA_DISCONNECTED`), thiết bị không có
  đường nào để báo real-time — firmware chỉ tự động `esp_wifi_connect()`
  lại và gửi sự kiện `disconnected`/`reconnected` best-effort khi có thể.
- **Không có** cơ chế lưu-và-gửi-lại (store-and-forward) dữ liệu trong lúc
  mất mạng — các mẫu/khoảng thời gian offline sẽ không xuất hiện trên biểu
  đồ. Đây là quyết định phạm vi có chủ đích cho v1, không phải thiếu sót.
- `esp_wifi_set_band_mode(WIFI_BAND_MODE_5G_ONLY)` trong `main.c` dành cho
  chip dual-band (ESP-IDF 5.3+) — kiểm tra tên API/enum này khớp với phiên
  bản ESP-IDF cài đặt thực tế khi build, vì đây là API tương đối mới.

## Cấu hình & build

```
cd esp32_wifi_monitor
idf.py set-target esp32c5
idf.py menuconfig     # vào "WiFi Signal Monitor Configuration", điền:
                       #   - SSID/mật khẩu mạng 5GHz cần kiểm tra
                       #   - X-Gateway-Key của nhà máy
                       #   - Device ID (duy nhất nếu có nhiều thiết bị)
idf.py build
idf.py -p <PORT> flash monitor
```

`sdkconfig` (chứa mật khẩu WiFi thật sau khi menuconfig) không commit vào
git — xem `.gitignore`. Chỉ `sdkconfig.defaults` (giá trị mặc định an toàn)
được commit.

## Nhiều thiết bị

Mỗi ESP32-C5 flash với `WIFI_MON_DEVICE_ID` khác nhau (vd `WIFI-MON-01`,
`WIFI-MON-02`, đặt ở các khu vực khác nhau trong nhà máy) — dashboard lọc
theo `device_id`.
