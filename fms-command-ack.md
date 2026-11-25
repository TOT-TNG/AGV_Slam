# Hướng dẫn cho dev FMS — Xác nhận (ACK) lệnh theo ID, chống mất lệnh khi mất mạng

> Đối tượng: dev FMS thật (không dùng `python-manager`). Hai nhóm thiết bị có cơ chế ACK theo ID lệnh:
> **AGV** (ESP32 + Arduino) và **thiết bị thang máy** (master cabin + bộ gọi tầng).
> Nguyên tắc chung: **gửi lặp cùng ID cho tới khi thấy ID đó được báo lại; thiết bị khử trùng theo ID nên lặp không chạy lại lệnh.**

## 0. Vì sao cần

Xe vào thang, cabin đóng cửa là mất Wi-Fi vài chục giây tới hàng giờ. MQTT publish không có ACK ở tầng ứng dụng
(thiết bị dùng PubSubClient: subscribe/publish QoS0, session sạch) ⇒ lệnh gửi lúc đó **rơi hẳn, broker không giữ**.
FMS phải tự: (1) biết thiết bị đang offline, (2) giữ lệnh, (3) gửi lại cho tới khi có xác nhận.

## 1. Biết thiết bị online hay không

| Nguồn | Thiết bị | Ý nghĩa |
|-------|---------|---------|
| `uagv/v2/{factory}/{agvId}/connection` (retained + LWT) | AGV | `ONLINE` / `CONNECTIONBROKEN`. LWT bắn sau ~22 s (keep-alive 15 s) |
| `uelev/v2/{factory}/{elevatorId}/{deviceId}/connection` (retained + LWT) | Thang | như trên |
| Tuổi của bản tin `state` (mỗi ~1 s) | cả hai | state cũ hơn ~5 s = chưa có thông tin |

Khả dụng = `connectionState == ONLINE` **và** state còn mới. Nhận bất kỳ `state` mới nào cũng chứng tỏ thiết bị đã có mạng lại
(đừng chờ riêng bản tin `connection`).

**Offline ⇒ GIỮ lệnh trong hàng chờ, KHÔNG gửi, KHÔNG tính vào số lần gửi lặp. Online lại ⇒ gửi bù ngay.**
Khi giữ: lệnh cùng loại thay nhau (VD `run` rồi `stop` thì chỉ còn `stop`; plan mới thay plan cũ — dựng lại plan lúc gửi bù vì vị trí xe có thể đã đổi).

**Chính FMS mất broker** thì state của mọi thiết bị đều cũ đi — đó không phải lỗi của thiết bị. Khi đó: tạm dừng đếm "thiết bị offline",
không gửi/đếm lệnh lặp; có kết nối lại thì đếm lại từ đầu (xem `ElevatorCoordinator.set_link_state()` trong `elevator/elevator_coord`).

## 2. AGV (`uagv/v2/{factory}/{agvId}/…`)

### 2.1 Plan (`order`) — ACK có sẵn từ trước

| | |
|--|--|
| Gửi | `{"c":"plan","d":[…],"id":"a1b2c3d4","ts":…}` — mỗi lần gửi (kể cả gửi lại) dùng **`id` mới** |
| ACK | Mọi bản tin state có field **`ack`** = `id` của plan Arduino nhận gần nhất (ESP chia chunk + Arduino báo `chunk_ack` nội bộ, FMS không thấy) |
| Gửi lại | Chưa thấy `ack == id` sau ~4 s ⇒ gửi lại. Không gửi lại nếu xe đã đứng ở thẻ đầu của plan (plan đã được nhận; gửi lại sẽ rẽ 2 lần) |

### 2.2 Lệnh tức thời (`instantActions`) — MỚI: `cmd_ack`

Trước đây `run`/`stop` không có ACK. Nay thêm:

```jsonc
// FMS → AGV  (topic …/instantActions)
{"c":"run","ts":1767225600,"id":"9f3a1c2e"}

// AGV → FMS  (topic …/state, có trong MỌI bản tin state sau khi nhận lệnh, cho tới khi có lệnh mới mang id khác)
{ "orderId":"a1b2c3d4", "ack":"a1b2c3d4", "cmd_ack":"9f3a1c2e", "paused":false, "driving":true, … }
```

Quy tắc:
1. `id`: chuỗi **tối đa 9 ký tự** (khuyên 8 hex). Dài hơn bị Arduino bỏ qua cả ACK lẫn khử trùng.
2. Thấy `state.cmd_ack == id` ⇒ lệnh **đã tới Arduino** ⇒ dừng gửi lặp.
3. Chưa thấy sau ~3 s ⇒ gửi lại **cùng `id`**, tối đa 3 lần (rồi báo lỗi/bỏ qua, tránh lặp vô hạn).
4. Gửi lặp cùng `id`: Arduino **không chạy lại** (chỉ báo lại `cmd_ack`) ⇒ `run` lặp không làm xe khựng.
5. `cmd_ack` chỉ nói "đã nhận", **không** nói "đã chạy". Có chủ ý bỏ qua `run`: xe đang `STATE_HOOK_FIX` (móc lỗi chờ sửa tay) hoặc
   `STATE_WAIT_LIDAR` (lidar dài đang bị chắn). Cần biết xe đã chạy thì đối chiếu `state.paused` / `driving`.
6. `id` của lệnh tức thời **không** làm đổi `ack`/`orderId` của plan (hai field riêng).
7. **Không gắn `id` cho `reset`**: Arduino khởi động lại nên mất `cmd_ack` ⇒ bạn sẽ gửi `reset` lặp mãi.
8. Firmware Arduino cũ chưa có `cmd_ack`: dự phòng bằng state — `run` coi là xong khi `paused=false`; `stop` khi `driving=false ∧ paused=false`.

Chu trình khuyến nghị (giả mã):

```python
def send_motion(cmd):                       # cmd = "run" | "stop"
    pending.motion = Pending(cmd, id=uuid4().hex[:8], tries=0)   # lệnh sau đè lệnh trước
    flush()

def flush():                                # gọi khi: có lệnh mới / thiết bị ONLINE lại / mỗi state mới
    p = pending.motion
    if p and device.available() and now - p.sent_at > 3.0 and p.tries <= 3:
        publish(instantActions, {"c": p.cmd, "ts": now_epoch(), "id": p.id})
        p.sent_at, p.tries = now, p.tries + 1

def on_state(s):
    if pending.motion and s.get("cmd_ack") == pending.motion.id:
        pending.motion = None               # xong
    flush()
```

### 2.3 Kênh ngược (AGV → FMS) — đã có

| Sự kiện | Field trong state | FMS phải gửi lại |
|---------|-------------------|------------------|
| Event (`obstacle`, `door_blocked`, …) | `event` | `{"c":"ack_event","d":"<event>"}` |
| Kết quả nâng/hạ móc | `hook_report` + `hook_report_seq` (kèm `event` song song) | `{"c":"ack_event","d":"<hook_report>","seq":<seq>}` — chưa ACK thì Arduino gửi lặp mãi |

## 3. Thiết bị thang máy (`uelev/v2/{factory}/{elevatorId}/{deviceId}/…`)

Đây là hợp đồng đầy đủ ở `elevator/docs/04-giao-thuc-mqtt.md` §3, §6; tóm tắt phần liên quan ACK:

1. Mỗi lệnh có **`actionId`** (chuỗi duy nhất toàn hệ, tối đa 19 ký tự). Mỗi message `instantActions` chứa 1 action.
2. Thiết bị báo lại trong `state.actionStates[]` (8 action gần nhất): `actionStatus` ∈ `WAITING`/`RUNNING`/`FINISHED`/`FAILED` + `resultDescription`.
3. FMS gửi lại **cùng `actionId`** mỗi 1 s (`cmd_retry_s`) tới khi thấy ID đó trong `actionStates`; tối đa 10 lần ⇒ coi là `EXPIRED`.
   Thiết bị khử trùng theo `actionId` (nhớ ≥ 8 ID) ⇒ không chạy lại xung/relay.
4. **Offline thì không đếm lần gửi lặp** (mục 1). Master cabin có thể offline hàng giờ khi cửa đóng; bộ gọi tầng thường online.
5. **`RUNNING` đã đủ coi là "đã nhận"** với `depart`: Master tự làm cả chuỗi (nhả giữ cửa → đóng nhanh → gọi tầng → tự giữ cửa khi tới),
   `FINISHED` có thể không bao giờ về vì cửa đóng là mất mạng. Lệnh `EXPIRED` mà `FINISHED` đến muộn vẫn tính là xong.
6. **Gia hạn TTL** (`holdDoor`, `hallCall`): gửi **`actionId` MỚI** (để thiết bị thực thi lại), chu kỳ 10 s khi TTL 30 s.
   Gửi lại cùng `actionId` chỉ để đảm bảo giao nhận, không gia hạn.
7. TTL là dead-man switch trên thiết bị: hết TTL ⇒ relay nhả. Nếu gián đoạn dài hơn TTL, relay đã nhả dù lệnh từng `FINISHED` — FMS phải **nhìn state thực**
   (`caller.hall.active`, `elevator.doorHold`) và gọi lại với `actionId` mới nếu relay không còn bật (ví dụ `hallCall` đã `FINISHED` nhưng `hall.active=false`
   quá ~3 s ⇒ gửi `hallCall` mới; tối đa vài lần rồi báo lỗi).
8. Mất FMS (LWT `uagv/v2/{factory}/manager/connection` ≠ `ONLINE`) hoặc mất broker > 10 s ⇒ thiết bị tự nhả `holdDoor`/`hallCall` (trừ giữ cửa do Master tự bật khi tới tầng).
9. Ngưỡng offline gợi ý: bộ gọi tầng 30 s ⇒ `FAILED(caller_offline)`; cabin ở pha `BOARDING` 90 s ⇒ `FAILED(master_offline)`;
   cabin đang `TRANSIT` offline là bình thường (chỉ cảnh báo, giới hạn bởi `transit_timeout_s` = 360 s).

## 4. Checklist cho dev FMS

- [ ] Theo dõi presence (`connection` + tuổi `state`) cho từng AGV và từng thiết bị thang.
- [ ] Có hàng chờ lệnh theo thiết bị; offline thì giữ, online lại thì gửi bù (lệnh cùng loại: bản mới thay bản cũ).
- [ ] AGV: gắn `id` (≤ 9 ký tự) cho `run`/`stop`, đọc `state.cmd_ack`, gửi lặp cùng `id` mỗi 3 s tối đa 3 lần.
- [ ] AGV: plan dùng `id` mới mỗi lần gửi, đọc `state.ack`; ACK `event` và `hook_report` như §2.3.
- [ ] Thang: `actionId` duy nhất; gửi lặp cùng `actionId` mỗi 1 s theo `actionStates`; gia hạn TTL bằng `actionId` mới.
- [ ] Thang: `hallCall` đã `FINISHED` mà `hall.active=false` ⇒ gọi lại.
- [ ] Khi chính FMS mất broker: không coi thiết bị là offline, không đốt số lần gửi lặp.

## 5. Thử bằng tay (Mosquitto)

```bash
# AGV: gửi run với id, quan sát state có cmd_ack
mosquitto_pub -h <broker> -p 8883 -u <user> -P *** -t uagv/v2/Vietduc/AGV04/instantActions -q 1 \
  -m '{"c":"run","ts":1767225600,"id":"test0001"}'
mosquitto_sub -h <broker> -p 8883 -u <user> -P *** -t 'uagv/v2/Vietduc/AGV04/state' -v | grep cmd_ack
# Gửi lặp cùng id: log Arduino phải có "[CMD] Trung id - bo qua, bao lai cmd_ack", xe không khựng

# Thang: xem elevator/docs/04-giao-thuc-mqtt.md §8
```

## 6. Điều kiện triển khai

- `cmd_ack` cần **nạp lại firmware Arduino** (không cần sửa ESP — ESP forward nguyên JSON state).
- Chưa kiểm chứng trên xe thật: cần theo dõi log `[PUB ERR]` (state quá lớn cho `txBuf`) sau khi nạp.
- Tham chiếu code: Python (`python-manager/agv/agv_instance.py`: `_deliver`, `_verify_motion_cmd`; `comm_adapter.py`),
  Arduino (`arduino-firmware/src/mission.cpp`: `lastCmdAckId`), thang (`elevator/elevator_coord/command_channel.py`, `coordinator.py`).
