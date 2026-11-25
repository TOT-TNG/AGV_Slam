# 09 — TEST THỦ CÔNG BỘ GỌI + MASTER THANG QUA MQTT (hướng dẫn cho dev)

Mục đích: dev gửi tay từng lệnh tới 3 bộ gọi tầng (`call1/2/3`) và master thang (`master`) để kiểm tra
phần cứng/firmware, **không cần FMS/coordinator**. Hợp đồng đầy đủ: [04-giao-thuc-mqtt.md](04-giao-thuc-mqtt.md).

## 1. Điều kiện trước khi test

1. **TẮT coordinator/FMS thật.** Coordinator có cơ chế tự chữa rò rỉ: thấy relay đang bật mà không có
   chuyến (ride) nào sở hữu thì sau vài giây nó gửi `reset` → lệnh giữ cửa/gọi tầng bạn gửi tay sẽ bị xóa.
   Ngược lại, FMS thoát (LWT `uagv/v2/Vietduc/manager/connection` ≠ `ONLINE`) cũng làm thiết bị nhả relay.
   Không ai publish topic `manager/connection` thì thiết bị mặc định coi FMS còn sống (không nhả).
2. Thiết bị đã nạp firmware đúng tầng (caller: `CALLER_FLOOR` trong `caller/src/config.h`), đã có
   `secrets.h` đúng Wi-Fi/broker, và log boot có `[MQTT] ONLINE ELV01-<deviceId>`. Đèn **Y0 (GPIO6)** sáng = đã lên MQTT.
3. Broker test: `192.168.0.200:1883`, **không TLS**, user `tot_agv` (mật khẩu hỏi người phụ trách).
   Broker thật `iot.tot360.com.vn:8883` dùng TLS.

## 2. Bảng chân relay (tham chiếu để đo/nghe relay)

| Bộ gọi | Y2 (GPIO15) | Y3 (GPIO16) | Hướng hỗ trợ |
|---|---|---|---|
| `call1` (tầng 1) | UP | — | chỉ UP |
| `call2` (tầng 2) | UP | DN | UP, DN |
| `call3` (tầng 3) | — | DN | chỉ DN |

Master: Y2 = giữ cửa, Y3 = **đóng** cửa nhanh, Y4/Y5/Y6 = gọi tầng 1/2/3. Y0 = đèn Wi-Fi/MQTT, Y1 = đèn hoạt động.

## 3. Topic

Gốc: `uelev/v2/Vietduc/ELV01/<deviceId>` với `<deviceId>` ∈ `master`, `call1`, `call2`, `call3`.

| Topic | Hướng | QoS | Dùng để |
|---|---|---|---|
| `.../instantActions` | bạn → thiết bị | 1 | Gửi lệnh |
| `.../state` | thiết bị → bạn | 0 | Xem trạng thái (khi đổi + mỗi 1 s) |
| `.../connection` | thiết bị → bạn | 1, retained | `ONLINE` / `CONNECTIONBROKEN` (Last Will, ~22 s sau khi rớt) |

## 4. Quan sát trước khi gửi lệnh

```bash
mosquitto_sub -h 192.168.0.200 -p 1883 -u tot_agv -P <pass> -t 'uelev/v2/Vietduc/#' -v
```

Phải thấy `.../connection` = `ONLINE` cho cả 4 thiết bị và `.../state` đến mỗi giây. Thiếu thiết bị nào
thì xử lý thiết bị đó (Wi-Fi, secrets, nguồn) trước khi test lệnh.

## 5. Định dạng lệnh

Publish vào `uelev/v2/Vietduc/ELV01/<deviceId>/instantActions`, QoS 1:

```json
{"headerId": 1, "timestamp": "2026-11-12T04:30:00.000Z", "version": "2.0.0",
 "manufacturer": "Vietduc", "serialNumber": "ELV01-<deviceId>",
 "actions": [
   {"actionType": "<loại>", "actionId": "<duy nhất>", "blockingType": "NONE",
    "actionParameters": [{"key": "<khóa>", "value": <giá trị>}]}
 ]}
```

Quy tắc bắt buộc:
- **`actionId` khác nhau mỗi lần gửi, tối đa 19 ký tự.** Dùng lại cùng id thì thiết bị coi là lệnh trùng, **không thực thi lại**, chỉ báo lại kết quả cũ.
- **`timestamp` dùng giờ UTC thật** (ISO 8601, có `Z`). Thiết bị đồng bộ đồng hồ từ trường này; điền giờ giả làm lệch giờ trong `state`.
- `serialNumber` = `ELV01-<deviceId>` (vd `ELV01-call2`). Mỗi message nên chỉ 1 action.
- Tham số không bắt buộc có thể bỏ khỏi `actionParameters`.

## 6. Kịch bản test

### 6.1 Ba bộ gọi — `hallCall` / `releaseHall`

| # | Thiết bị | Lệnh | Tham số | Kết quả mong đợi |
|---|---|---|---|---|
| 1 | `call1` | `hallCall` | `direction="UP"`, `ttlS=20` | `FINISHED`; relay Y2 chạy chu kỳ **5 s bật / 1 s tắt** tới hết 20 s, rồi tự nhả; `caller.hall.active=true` |
| 2 | `call1` | `hallCall` | `direction="DN"`, `ttlS=20` | `FAILED`, `resultDescription="direction_unsupported"` |
| 3 | `call2` | `hallCall` | `"UP"`, `ttlS=20` | `FINISHED`; relay Y2 |
| 4 | `call2` | `hallCall` (khi #3 còn chạy) | `"DN"`, `ttlS=20` | `FAILED`, `opposite_direction_active` (UP/DN loại trừ nhau) |
| 5 | `call2` | `releaseHall` rồi `hallCall` `"DN"` | `ttlS=20` | Relay Y3 chạy, `FINISHED` |
| 6 | `call3` | `hallCall` | `"DN"`, `ttlS=20` | `FINISHED`; relay Y3 |
| 7 | `call3` | `hallCall` | `"UP"` | `FAILED`, `direction_unsupported` |
| 8 | bất kỳ caller | `releaseHall` hoặc `reset` | không | Relay nhả ngay, `FINISHED` |
| 9 | bất kỳ caller | `hallCall` | `ttlS=0` hoặc `601` | `FAILED`, `ttl_out_of_range` |

Kiểm tra thêm: gửi lại `hallCall` cùng hướng với `actionId` **mới** khi đang chạy = gia hạn TTL.
Tự nhả khi hết TTL (không cần `releaseHall`) là dead-man switch — phải đúng.

### 6.2 Master thang

| # | Lệnh | Tham số | Kết quả mong đợi |
|---|---|---|---|
| 1 | `callFloor` | `floor=1..3`, `pulseMs` (100–5000, mặc định 1000) | Xung HIGH 1 s lên Y4/Y5/Y6 tương ứng; `RUNNING` rồi `FINISHED`; `elevator.callPulse` = tầng đang xung |
| 2 | `callFloor` | `floor=4` | `FAILED`, `floor_out_of_range` |
| 3 | `holdDoor` | `ttlS=20` | Y2 lên, `FINISHED` ngay; tự nhả sau 20 s; `elevator.doorHold=true`, `holdTtlS` đếm ngược |
| 4 | `fastClose` (khi đang `holdDoor`) | `durationMs` tùy chọn | `FAILED`, `door_hold_active` |
| 5 | `releaseDoor` | không | Y2 xuống ngay |
| 6 | `fastClose` (sau khi nhả) | `durationMs=3000` | Xung HIGH 3 s lên Y3 (**đóng** cửa nhanh), `RUNNING` rồi `FINISHED` |
| 7 | `holdDoor` trong lúc `fastClose` đang xung | `ttlS=20` | `fastClose` bị hủy (`FAILED`, `preempted_by_hold`); Y2 và Y3 **không bao giờ cùng HIGH** |
| 8 | `depart` | `toFloor=n` (và tùy chọn `holdTtlS`, `pulseMs`, `fastCloseMs`) | Xem 6.3 |
| 9 | `reset` | không | Mọi output LOW, hủy xung và `depart` đang chạy |

### 6.3 `depart` — chuỗi tự động của master

Một lệnh `depart{toFloor}` = master tự làm cả chuỗi (không cần mạng, vì cabin đóng cửa thì mất Wi-Fi):

1. **Pha `closing`:** nhả giữ cửa Y2 → xung Y3 (đóng nhanh) `fastCloseMs` (mặc định 3 s).
2. **Pha `calling`:** xung gọi tầng `toFloor` (Y4/Y5/Y6) `pulseMs`. Lúc này lệnh báo `FINISHED`.
3. **Pha `transit`:** master tự canh cảm biến tầng X5/X6/X7:
   - 20 s chưa rời tầng xuất phát → gọi lại xung (tối đa 3 lần);
   - cabin dừng ổn định ở tầng đích **≥ 2 s** → **tự giữ cửa Y2** trong `holdTtlS` (mặc định 300 s), `elevator.doorHoldAuto=true`;
   - quá 10 phút không tới → bỏ canh.

Test `depart`:
- Cabin đang ở tầng đích → `FAILED`, `already_at_floor`, **không** đụng relay nào (giữ cửa cũ vẫn giữ).
- Chưa biết tầng hiện tại (cảm biến không ra tầng) → vẫn chạy chuỗi bình thường.
- Giữa chừng gửi `holdDoor` → `depart` thành `FINISHED (handed_to_fms)`, master không tự giữ cửa nữa.
- Giữa chừng gửi `releaseDoor` → `depart` thành `FAILED (superseded)`.
- Gửi `depart` mới → `depart` cũ `FAILED (superseded)`.
- Giữ cửa **tự bật** (`doorHoldAuto=true`) không bị nhả khi mất mạng; chỉ hết TTL, `reset`, `releaseDoor` hoặc nút X0 mới nhả.

## 7. Đọc kết quả trong `state`

Với mỗi thiết bị, `actionStates` giữ 8 action gần nhất (mới nhất cuối):

```json
{"actionId":"t0001","actionType":"hallCall","actionStatus":"FINISHED","resultDescription":""}
```

`actionStatus` ∈ `WAITING`, `RUNNING`, `FINISHED`, `FAILED`. Không thấy `actionId` vừa gửi trong `actionStates`
sau ~2 s nghĩa là thiết bị không nhận lệnh (kiểm tra topic, QoS, `serialNumber`, thiết bị còn `ONLINE` không).

Trường quan trọng:

| Thiết bị | Trường | Ý nghĩa |
|---|---|---|
| caller | `caller.hall.active` / `direction` / `ttlS` / `relay` | Đang gọi, hướng, TTL còn lại, mức relay tức thời (nhấp nháy 5 s/1 s) |
| caller | `diag.rssi` / `uptimeS` | Mức sóng Wi-Fi, thời gian chạy |
| master | `elevator.floor` | Tầng hiện tại (0/null nếu chưa xác định) |
| master | `elevator.doorHold` / `holdTtlS` / `doorHoldAuto` | Trạng thái Y2, TTL còn lại, giữ cửa do master tự bật |
| master | `elevator.fastClose` / `callPulse` | Y3 đang xung / tầng đang xung Y4–Y6 |
| master | `elevator.sensors` | X4..X7 thô, để chẩn đoán cảm biến tầng/cửa |
| master | `errors[]` | vd `FLOOR_SENSOR_INCONSISTENT` |

Kiểm tra bằng mắt: đèn **Y1** nháy ngắn khi nhận lệnh mới, sáng liên tục khi đang gọi/giữ cửa.

## 8. Ví dụ lệnh `mosquitto_pub`

```bash
# Bộ gọi tầng 2: gọi lên 20 s
mosquitto_pub -h 192.168.0.200 -p 1883 -u tot_agv -P <pass> -q 1 \
  -t uelev/v2/Vietduc/ELV01/call2/instantActions -m \
  '{"headerId":1,"timestamp":"2026-11-12T04:30:00.000Z","version":"2.0.0","manufacturer":"Vietduc","serialNumber":"ELV01-call2","actions":[{"actionType":"hallCall","actionId":"t0001","blockingType":"NONE","actionParameters":[{"key":"direction","value":"UP"},{"key":"ttlS","value":20}]}]}'

# Bộ gọi tầng 2: nhả
... -t uelev/v2/Vietduc/ELV01/call2/instantActions -m \
  '{"headerId":2,"timestamp":"...","version":"2.0.0","manufacturer":"Vietduc","serialNumber":"ELV01-call2","actions":[{"actionType":"releaseHall","actionId":"t0002","blockingType":"NONE","actionParameters":[]}]}'

# Master: gọi cabin tới tầng 3
... -t uelev/v2/Vietduc/ELV01/master/instantActions -m \
  '{"headerId":3,"timestamp":"...","version":"2.0.0","manufacturer":"Vietduc","serialNumber":"ELV01-master","actions":[{"actionType":"callFloor","actionId":"t0003","blockingType":"NONE","actionParameters":[{"key":"floor","value":3}]}]}'

# Master: giữ cửa 20 s
... -m '{"...","serialNumber":"ELV01-master","actions":[{"actionType":"holdDoor","actionId":"t0004","blockingType":"NONE","actionParameters":[{"key":"ttlS","value":20}]}]}'

# Master: depart tới tầng 2
... -m '{"...","serialNumber":"ELV01-master","actions":[{"actionType":"depart","actionId":"t0005","blockingType":"NONE","actionParameters":[{"key":"toFloor","value":2}]}]}'
```

Nhớ đổi `actionId` (`t0006`, `t0007`, ...) và dùng giờ UTC thật ở `timestamp` cho mỗi lần gửi.

## 9. Reset khi test xong hoặc kẹt

- Gửi `reset` (actionId mới) tới từng thiết bị: caller nhả relay, master nhả mọi output và hủy `depart`.
- Hoặc bấm nút **X0** (GPIO39) tại thiết bị: master `allOff`, caller nhả relay rồi khởi động lại.
- Cấp lại nguồn: mọi output về LOW lúc boot.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp |
|---|---|
| Lệnh gửi mà không thấy `actionId` trong `state` | Sai topic/`serialNumber`; thiết bị offline; dùng lại `actionId` cũ |
| Relay bật rồi tự tắt sau vài giây | Coordinator/FMS đang chạy và gửi `reset` (tự chữa rò rỉ) — tắt nó đi |
| `[MQTT] connect fail rc=-2` | Không tới được broker: sai host/port, hoặc TLS không khớp port (1883 ↔ TLS=0, 8883 ↔ TLS=1) |
| Không có log và đèn Y0 không sáng, chỉ có `[BOOT]` | Wi-Fi chưa kết nối: sai SSID/mật khẩu trong `secrets.h` |
| `[MQTT] ONLINE` lặp lại liên tục | Hai thiết bị trùng `clientId` (vd 2 mạch cùng `call1`) tranh nhau kết nối; hoặc Wi-Fi yếu |
| `direction_unsupported` | Hướng không có trên tầng đó (xem bảng mục 2) |
