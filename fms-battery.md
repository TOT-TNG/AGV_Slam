# Hướng dẫn tích hợp cho dev FMS — Báo Pin Yếu & Khóa Sạc AGV (Hướng B)

> **Đối tượng:** Dev phát triển FMS thật (Server điều phối).
> **Áp dụng cho:** AGV KÉO (`Arduino Mega 2560` + `ESP32-C5 bridge`).
> **Cơ chế ACK lệnh tức thời (`cmd_ack`):** dùng chung quy tắc trong [fms-command-ack.md](fms-command-ack.md).
> **Code tham chiếu phía client:** `python-manager/agv/agv_instance.py`, `python-manager/agv/comm_adapter.py`, `python-manager/gui/app_shell.py`.

---

## 1. Tổng quan & nguyên lý vận hành

Mạch đo dung lượng pin trên xe xuất tín hiệu digital vào **chân 37 (`PIN_PIN_YEU`)** của Arduino Mega (cấu hình `INPUT` + điện trở kéo xuống GND ngoài):
- **`LOW` (0V):** Pin bình thường.
- **`HIGH` (3.3–5V):** Pin yếu (≤ 20%).
- **Chống nhiễu (debounce):** Arduino chỉ xác nhận đổi trạng thái khi tín hiệu giữ ổn định liên tục **≥ 3 giây** (tránh tụt áp thoáng qua khi đề-pa / nâng móc).

### Quy tắc chia vai giữa AGV và FMS
1. **Khi phát hiện pin yếu ngoài đường (`battery_low = true`, `battery_blocking = false`):**
   - Arduino **KHÔNG dừng xe giữa đường** và **KHÔNG khóa nhận plan**. Xe kêu 1 lượt còi ngắn (~5 giây) rồi tự tắt, tiếp tục hoàn tất hành trình hiện tại.
   - FMS thấy `battery_low == true` (hoặc `errors` có `BATTERY_LOW`) ⇒ **không giao đơn hàng mới** cho xe này; sau khi xe xong chuyến hiện tại, FMS gửi **plan điều xe về trạm sạc** có bước cuối là **Action Code `35` (`ACT_WAIT_CHARGE`)**.
2. **Khi xe về tới trạm sạc (thực thi `ACT_WAIT_CHARGE = 35` lúc `battery_low == true`):**
   - Arduino bật **`battery_blocking = true`**, giữ thông báo `"Pin yeu - dang cho sac"` trên HMI, phát event `"battery_need_charge"`.
   - Trong lúc `battery_blocking == true`:
     - Arduino **từ chối mọi `plan` và `run`** mới gửi xuống.
     - Công nhân ấn các nút gọi xe / "Tiếp tục" / chọn tổ trên HMI sẽ bị chặn và xe **kêu 1 lượt còi ngắn (~5 giây)** cảnh báo.
3. **Mở khóa sau khi sạc (~2 tiếng):**
   - FMS theo dõi thời gian sạc tại trạm (mặc định **2 giờ = 7200 giây**). Khi đủ thời gian **và** `state.battery_low == false` (chân 37 đã về 0V), FMS gửi lệnh **`{"c":"battery_unlock","id":"<8hex>","ts":<epoch>}`** trên topic `instantActions`.
   - Arduino xóa `battery_blocking = false`, xóa thông báo HMI về `"SAN SANG"`, phản hồi `cmd_ack = <id>`.
   - **Fallback an toàn trên Arduino:** Nếu đã đủ 2 tiếng sạc tại trạm **và** chân 37 đã về 0V (`battery_low == false`) mà FMS chưa gửi `battery_unlock` (hoặc mất mạng), Arduino sẽ tự mở khóa & xóa thông báo HMI để tránh kẹt xe.

---

## 2. Sơ đồ luồng bản tin

```mermaid
sequenceDiagram
    participant AGV as "AGV (Arduino + ESP32)"
    participant FMS as "FMS (Server)"

    Note over AGV: Dang chay giao hang -> chan 37 HIGH >= 3s
    AGV->>FMS: state: battery_low=true, battery_blocking=false, errors[BATTERY_LOW], event="battery_low"
    FMS->>AGV: instantActions: {"c":"ack_event","d":"battery_low","ts":...}
    Note over FMS: Khong giao don moi; doi xe xong chuyen hien tai

    FMS->>AGV: order: plan [..., {"t": <charger_tag>, "a": 35, "v": 0}]
    Note over AGV: Xe chay ve tram sac -> thuc thi ACT_WAIT_CHARGE (35)
    AGV->>FMS: state: event="arrived_wait_sys", tag=<charger_tag>
    AGV->>FMS: state: battery_low=true, battery_blocking=true, errors[BATTERY_LOW], event="battery_need_charge"
    FMS->>AGV: instantActions: {"c":"ack_event","d":"battery_need_charge","ts":...}
    Note over FMS: Bat dau dem thoi gian sac (~2h)

    Note over AGV: Pin da sac hoi phuc -> chan 37 LOW (0V) >= 3s
    AGV->>FMS: state: battery_low=false, battery_blocking=true, errors=[]

    Note over FMS: Du 2h AND battery_low == false
    FMS->>AGV: instantActions: {"c":"battery_unlock","id":"b1c2d3e4","ts":...}
    AGV->>FMS: state: battery_low=false, battery_blocking=false, cmd_ack="b1c2d3e4"
```

---

## 3. Hợp đồng bản tin MQTT

### 3.1. AGV → FMS (`uagv/v2/{factory}/{agvId}/state`)

ESP32-C5 forward nguyên JSON từ Arduino và gắn thêm header VDA5050 (`headerId`, `timestamp`, `version`, `manufacturer`, `serialNumber`, `rssi`, `mac`). Các gói có field `"event"` **bỏ qua giới hạn tần suất 2s** của ESP32 và gửi lên MQTT ngay lập tức.

| Field | Kiểu | Khi nào xuất hiện | Ý nghĩa cho FMS |
|---|---|---|---|
| `battery_low` | `bool` | **Mọi gói state** (heartbeat ~1s) | `true` = chân 37 đang `HIGH` ổn định ≥ 3s (pin yếu ≤ 20%); `false` = pin đã về 0V |
| `battery_blocking` | `bool` | **Mọi gói state** (heartbeat ~1s) | `true` = xe đang khóa sạc tại trạm, từ chối mọi `plan` và `run`; `false` = sẵn sàng nhận lệnh |
| `errors[]` | `array` | Khi `battery_low == true` | Chứa phần tử `{"errorType":"BATTERY_LOW","errorLevel":"WARNING"}` (tự biến mất khi `battery_low == false`) |
| `event` | `string` | Tức thời (1 lần khi chuyển trạng thái) | `"battery_low"` (vừa phát hiện pin yếu) hoặc `"battery_need_charge"` (vừa khóa sạc tại trạm, hoặc vừa từ chối `plan`/`run` lúc đang khóa sạc) |
| `cmd_ack` | `string` | Sau khi nhận lệnh tức thời có `id` | Trả lại đúng `id` của lệnh `battery_unlock` (xem [fms-command-ack.md](fms-command-ack.md) §2.2) |

> **Lưu ý độ tin cậy:** Kênh `event` giúp FMS phản ứng tức thời (< 100 ms), nhưng **nguồn sự thật chính** là 2 field bền vững `battery_low` và `battery_blocking` có mặt trong **mọi bản tin state định kỳ**. Nếu 1 gói `event` bị rơi do mất Wi-Fi, gói heartbeat 1s tiếp theo vẫn đồng bộ lại trạng thái chính xác.

#### Ví dụ JSON thực tế theo 3 giai đoạn

**Giai đoạn 1 — Phát hiện pin yếu khi đang chạy ngoài đường:**
```json
{
  "headerId": 120,
  "timestamp": "2026-11-23T06:30:10.123Z",
  "version": "2.0.0",
  "manufacturer": "Vietduc",
  "serialNumber": "AGV01",
  "lastNodeId": 42,
  "tag": 42,
  "prev_tag": 41,
  "operatingMode": "AUTOMATIC",
  "driving": true,
  "paused": false,
  "errors": [
    { "errorType": "BATTERY_LOW", "errorLevel": "WARNING" }
  ],
  "safetyState": { "eStop": "NONE" },
  "battery_low": true,
  "battery_blocking": false,
  "action_info": "running",
  "event": "battery_low"
}
```

**Giai đoạn 2 — Đã về tới trạm sạc (`ACT_WAIT_CHARGE`) và khóa nhận đơn:**
```json
{
  "headerId": 145,
  "timestamp": "2026-11-23T06:32:05.456Z",
  "version": "2.0.0",
  "manufacturer": "Vietduc",
  "serialNumber": "AGV01",
  "lastNodeId": 10,
  "tag": 10,
  "operatingMode": "MANUAL",
  "driving": false,
  "paused": true,
  "errors": [
    { "errorType": "BATTERY_LOW", "errorLevel": "WARNING" }
  ],
  "battery_low": true,
  "battery_blocking": true,
  "action_info": "idle",
  "event": "battery_need_charge"
}
```

**Giai đoạn 3 — Pin đã hồi (chân 37 về 0V) nhưng vẫn giữ khóa chờ đủ 2 tiếng:**
```json
{
  "lastNodeId": 10,
  "tag": 10,
  "errors": [],
  "battery_low": false,
  "battery_blocking": true,
  "action_info": "idle"
}
```

---

### 3.2. FMS → AGV

#### 1) ACK sự kiện (`uagv/v2/{factory}/{agvId}/instantActions`)
Gửi ngay khi nhận `"event": "battery_low"` hoặc `"event": "battery_need_charge"`:
```json
{"c": "ack_event", "d": "battery_low", "ts": 1767225600}
```
```json
{"c": "ack_event", "d": "battery_need_charge", "ts": 1767225600}
```

#### 2) Điều xe về trạm sạc (`uagv/v2/{factory}/{agvId}/order`)
Gửi plan bình thường tới thẻ trạm sạc, **bước cuối cùng bắt buộc dùng Action Code `35` (`ACT_WAIT_CHARGE`)**:
```json
{
  "c": "plan",
  "id": "a1b2c3d4",
  "ts": 1767225610,
  "d": [
    {"t": 42, "a": 4, "v": 120},
    {"t": 42, "a": 3, "v": 0},
    {"t": 10, "a": 35, "v": 0}
  ]
}
```
> **Tình huống đặc biệt (khởi động xe ngay tại trạm sạc khi pin đã yếu sẵn):** Lúc mới bật nguồn, Arduino chưa biết mình đang ở trạm sạc (`atChargerStation = false`) nên chỉ báo `battery_low = true, battery_blocking = false`. Nếu FMS thấy `tag == <charger_tag>` và `battery_low == true`, FMS có thể không giao đơn, hoặc gửi 1 plan 1 bước `{"c":"plan","id":"...","d":[{"t":10,"a":35,"v":0}]}` để kích khóa sạc `battery_blocking = true` + hiện thông báo HMI ngay trên xe.

#### 3) Mở khóa sau khi sạc đủ (`uagv/v2/{factory}/{agvId}/instantActions`)
```json
{
  "c": "battery_unlock",
  "id": "b1c2d3e4",
  "ts": 1767232800
}
```
- `id`: chuỗi tối đa **9 ký tự** (khuyên 8 ký tự hex). Arduino báo lại `"cmd_ack": "b1c2d3e4"` trong mọi gói state kế tiếp và khử trùng nếu FMS gửi lặp cùng `id`.
- Gửi lại cùng `id` mỗi ~3 giây (tối đa 3 lần) nếu chưa thấy `state.cmd_ack == id` hoặc `state.battery_blocking == false`.
- **Mở khóa cưỡng bức:** Lệnh `battery_unlock` luôn mở khóa ngay (kể cả chưa đủ 2 giờ hoặc chân 37 vẫn đang `HIGH`) để vận hành có thể kéo xe đi bảo trì/đổi bộ sạc khi cần.

---

## 4. Giả mã xử lý phía FMS

```python
CHARGE_MIN_SECONDS = 7200  # 2 giờ

def on_agv_state(agv, state):
    agv.battery_low      = bool(state.get("battery_low", False))
    agv.battery_blocking = bool(state.get("battery_blocking", False))

    ev = state.get("event")
    if ev in ("battery_low", "battery_need_charge"):
        publish_instant(agv, {"c": "ack_event", "d": ev, "ts": now_epoch()})

    # Xác nhận lệnh battery_unlock đã tới Arduino
    if agv.pending_unlock_id and state.get("cmd_ack") == agv.pending_unlock_id:
        agv.pending_unlock_id = None

    # 1. Xe đang rảnh ở ngoài trạm sạc mà pin yếu -> điều về trạm sạc (cuối plan có a=35)
    if agv.battery_low and not agv.battery_blocking and agv.is_idle() and not agv.at_charger():
        dispatch_return_to_charger(agv)  # bước cuối: {"t": charger_tag, "a": 35, "v": 0}

    # 2. Xe đã ở trạm sạc + đang battery_blocking -> bắt đầu đếm 2h
    if agv.battery_blocking and agv.at_charger():
        if agv.charge_start_ts is None:
            agv.charge_start_ts = now()
    elif not agv.battery_blocking:
        agv.charge_start_ts = None

    # 3. Đủ 2h + tín hiệu pin đã hồi (battery_low == False) -> mở khóa
    if (agv.battery_blocking
            and agv.charge_start_ts is not None
            and (now() - agv.charge_start_ts) >= CHARGE_MIN_SECONDS
            and not agv.battery_low):
        send_battery_unlock_with_retry(agv)

def can_assign_new_order(agv) -> bool:
    # Không giao đơn hàng mới cho xe đang pin yếu hoặc đang khóa sạc
    if agv.battery_low or agv.battery_blocking:
        return False
    return agv.is_available()
```

---

## 5. Checklist tích hợp cho dev FMS

- [ ] Đọc `state.battery_low` và `state.battery_blocking` trong mọi gói `.../state`.
- [ ] Loại AGV khỏi danh sách nhận đơn mới ngay khi `battery_low == true` **hoặc** `battery_blocking == true`.
- [ ] Không dừng đột ngột khi xe đang chạy giữa đường — chờ xong chuyến hiện tại rồi gửi plan về trạm sạc kết thúc bằng `ACT_WAIT_CHARGE` (`a = 35`).
- [ ] Gửi `ack_event` khi nhận `"event": "battery_low"` hoặc `"event": "battery_need_charge"` (không đẩy 2 event này vào hàng đợi nút bấm giao/cấp hàng).
- [ ] Hiển thị cảnh báo pin yếu trên giao diện (có thể đọc trực tiếp `battery_low` hoặc mảng `errors[]` có `errorType == "BATTERY_LOW"`).
- [ ] Khi `battery_blocking == true` tại trạm sạc: bắt đầu đếm 2 giờ; khi đủ 2 giờ **và** `battery_low == false`, gửi `{"c":"battery_unlock","id":"<8hex>","ts":<epoch>}` và theo dõi `cmd_ack`.
- [ ] Hỗ trợ nút thao tác thủ công trên FMS gửi `battery_unlock` khi kỹ thuật viên cần mở khóa sớm để bảo trì.

---

## 6. Thử nghiệm nhanh bằng Mosquitto CLI

```bash
# 1. Theo dõi bản tin state của AGV01 (lọc các gói liên quan tới pin/unlock)
mosquitto_sub -h <broker> -p 8883 -u <user> -P <pass> \
  -t 'uagv/v2/Vietduc/AGV01/state' -v

# 2. Giả lập FMS gửi ACK cho event battery_need_charge
mosquitto_pub -h <broker> -p 8883 -u <user> -P <pass> \
  -t 'uagv/v2/Vietduc/AGV01/instantActions' \
  -m '{"c":"ack_event","d":"battery_need_charge","ts":1767225600}'

# 3. Giả lập FMS gửi plan dừng chờ sạc tại thẻ 10 (ACT_WAIT_CHARGE = 35)
mosquitto_pub -h <broker> -p 8883 -u <user> -P <pass> \
  -t 'uagv/v2/Vietduc/AGV01/order' \
  -m '{"c":"plan","id":"chg00001","ts":1767225610,"d":[{"t":10,"a":35,"v":0}]}'

# 4. Giả lập FMS mở khóa sạc (kiểm tra state trả về "cmd_ack":"ulk00001" và "battery_blocking":false)
mosquitto_pub -h <broker> -p 8883 -u <user> -P <pass> \
  -t 'uagv/v2/Vietduc/AGV01/instantActions' \
  -m '{"c":"battery_unlock","id":"ulk00001","ts":1767232800}'
```

---

## 7. Điều kiện triển khai & ghi chú mở rộng

- **Cần nạp lại firmware Arduino Mega** (`arduino-firmware`). **KHÔNG cần sửa hay nạp lại ESP32-C5**.
- **Phần cứng chân 37:** Đã đấu điện trở pull-down ngoài (4.7 kΩ–10 kΩ xuống GND), tín hiệu pin yếu mức `HIGH` (≤ 5V). Khi chưa đấu mạch cảm biến có thể tắt tạm bằng cách comment `#define ENABLE_BATTERY_SENSOR` trong `arduino-firmware/src/sensors.h`.
- **Mở rộng VDA5050 `batteryState` (tùy chọn về sau):** Nếu giao diện FMS cần thêm object chuẩn VDA5050 `"batteryState": {"batteryCharge": 20|80, "charging": bool}`, có thể bọc chuyển đổi từ `battery_low`/`battery_blocking` ngay trên `esp-firmware-C5/src/uart_bridge.cpp` mà không tốn thêm SRAM của Arduino Mega.
