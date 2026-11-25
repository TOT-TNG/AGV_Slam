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

Đây là hợp đồng đầy đủ ở `04-giao-thuc-mqtt.md` §3, §6; tóm tắt phần liên quan ACK:

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
   cabin đang `TRANSIT` offline là bình thường (chỉ cảnh báo). **Bản FMS này đã bỏ mọi giới hạn thời gian chờ thang**
   (`transit_timeout_s`, `board_timeout_s`, `exit_timeout_s`, `elevator_wait_timeout_s`, `hold_timeout_s`, `call_retries`, `max_recoveries` mặc định = 0 = chờ vô hạn):
   ride giữ lệnh tới khi thang tới nơi / được xác nhận. Đặt lại số > 0 trong `elevator_coord/config.py` nếu cần giới hạn.

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

# Thang: xem `04-giao-thuc-mqtt.md` §8
```

## 6. Điều kiện triển khai

- `cmd_ack` cần **nạp lại firmware Arduino** (không cần sửa ESP — ESP forward nguyên JSON state).
- Chưa kiểm chứng trên xe thật: cần theo dõi log `[PUB ERR]` (state quá lớn cho `txBuf`) sau khi nạp.
- Tham chiếu code: Python (`python-manager/agv/agv_instance.py`: `_deliver`, `_verify_motion_cmd`; `comm_adapter.py`),
  Arduino (`arduino-firmware/src/mission.cpp`: `lastCmdAckId`), thang (`elevator/elevator_coord/command_channel.py`, `coordinator.py`).

## 7. Xe offline rồi online lại — KHÔNG được mất lệnh dang dở

Xe vào thang → cabin đóng cửa → mất Wi-Fi có thể kéo dài rất lâu. Quy tắc phía FMS này:

- **Hàng đợi lệnh của xe không bao giờ bị xoá** khi ride thang lỗi (`elevator_bridge` không còn gọi `cancel_all`):
  - xe còn **trong cabin** (hoặc đã vào cabin): chỉ cảnh báo `ELEVATOR_ERROR` + giữ khóa vùng thang, hàng đợi giữ nguyên chờ người vận hành;
  - xe **chưa vào cabin** (online hay offline): nếu đang tiến vào cabin thì `stop`, rồi sau `RIDE_RETRY_S` (10 s) **tự đặt lại chuyến thang**
    (chèn lại `elev_call` + bước vào cabin/đi thang lên đầu hàng đợi) — lặp tới khi thang phục vụ được; xe offline thì chờ online lại mới đặt lại;
  - dispatch lệnh thang lỗi (đặt/gọi/đi thang bị từ chối, thang chưa khởi tạo vì map chưa nạp...): không xoá hàng đợi, chèn lại đúng lệnh đó sau 10 s.
- **`run`/`stop`, plan** gửi lúc xe offline được giữ, gửi bù khi có state mới (§2). Bảng điều khiển tay thang (`uelev_console`)
  cũng giữ lệnh vô hạn (`QUEUE_MAX_AGE_SEC = 0`).
- **Lệnh `go_to`/`go_charge`/`go_wait` đang chạy lúc xe mất tín hiệu** được ghi nhớ (`LineAGVState.resume_cmd_id`). Khi xe online lại
  (≥ 2 lượt kiểm tra liên tiếp, đứng yên, không còn là "xe ma", không còn plan giữ) mà server **không còn route khớp vị trí thật**
  (route bị huỷ khi xe ma online lại ở nơi khác, hoặc route cũ không chứa vị trí xe) → `LineAGVHandler.resume_after_offline()` chèn lại đúng lệnh
  rồi dựng route mới **từ vị trí thật** (cùng cơ chế `off_route`). Lệnh thang `elev_*` do `elevator_bridge` điều khiển; lệnh đang chờ xác nhận
  (lifecycle/móc) do cơ chế lifecycle lo — hai loại này không bị dựng lại.
- Test: `mqtt_Server/test_resume_after_offline.py`; mô phỏng: kịch bản `elevator_ride` với xe im lặng ~50 s trong cabin.

## 8. Server khởi động lại — hàng đợi lệnh được KHÔI PHỤC

Trước đây hàng đợi (`task_queue.py`) chỉ nằm trong RAM, khởi động lại là mất. Nay mỗi lệnh được ghi `agv_task_executions` kèm **thứ tự** (`seq`),
`chain_leg`, `start_node`; lúc khởi động `main._restore_task_queue` dựng lại hàng đợi của các Line AGV từ các dòng còn `running`/`queued`
(lệnh đang chạy dở nằm đầu; quá `QUEUE_RESTORE_MAX_AGE_H` = 12 giờ thì coi là rác như trước).

Lệnh đầu chỉ chạy khi xe **sẵn sàng** (`monitor_line_offline` → `_restored_queue_ready`): đã nhận **state thật** từ xe sau khi server khởi động
(vị trí `last_tag` khôi phục từ DB KHÔNG đủ), online ổn định, đứng yên, không route/plan giữ, không chờ xác nhận. Khi đó `_kick_restored_queue`:
- nạp bản đồ (server mới khởi động chưa nạp), rồi chạy lại lệnh đầu **từ vị trí thật** của xe;
- lệnh đầu là `elev_ride` (ride cũ đã mất): xe ngoài cabin → chèn `elev_call` để đặt chuyến mới; xe **đang trong cabin** → **NHẬN LẠI chuyến**
  (xem mục 9) — không cần chờ xe online (xe có thể im lặng trong cabin đóng cửa); thang đưa xe tới tầng đích, giữ cửa, gửi `run`;
- xe đang đứng ở đích cần xác nhận người (`wait_sys`/`wait_user`): đặt lại `lifecycle=picking`, chờ xác nhận rồi hàng đợi chạy tiếp;

Các cờ trước đây chỉ nằm trong RAM nay **ghi xuyên DB** (`persistent_flags.py`, bảng `agv_runtime_flags(kind, grp, key)`, ghi tuần tự) và được
khôi phục cùng hàng đợi (`main._restore_runtime_flags`): `_pending_empty_pickup_legs` (điểm lấy rỗng), `_pending_confirm_only_legs`
(chỉ xác nhận), `_pending_staging_transits`, theo dõi lấy hàng theo lượt (`session_pickup`) và ngữ cảnh chuyến thang (`ride_ctx`: chiều vào/ra
cabin, plan thoát độc lập). Cờ của AGV/lượt đã hết lệnh hoặc quá `QUEUE_RESTORE_MAX_AGE_H` bị xoá khi khởi động (tránh cờ mồ côi).
- Test: `test_queue_restore.py`, `test_elevator_bridge.py`; mô phỏng: tắt/khởi động lại server giữa chuyến `elevator_ride`.

## 9. NHẬN LẠI chuyến thang cho xe đang trong cabin

Khi chuyến thang cũ không còn mà xe đang ở trong cabin — **server khởi động lại** hoặc **ride lỗi/huỷ khi xe còn trong cabin** — thư viện có
`ElevatorCoordinator.adopt_inside(agv, from_floor, to_floor)`: tạo chuyến mới vào thẳng pha `TRANSIT` (xe coi như đã lên, bỏ qua hàng đợi/gọi tầng/đón).
Pha TRANSIT tự xử lý mọi tình huống cabin thật: chưa rời tầng đi → gửi lại `depart`; đang đi; đã tới đích → `ARRIVED` → `EXIT_ALLOWED`;
đỗ nhầm tầng khác (kể cả người vận hành tự bấm lên tầng 2) → Transit Guard gọi lại tầng đích. Cầu nối (`ElevatorBridge.adopt_inside`) dựng ctx
"đã vào cabin" (lấy chiều vào/ra + plan thoát từ `ride_ctx` đã lưu DB) để luồng ra cabin (`run`, plan dự phòng) chạy như bình thường.
- Ride lỗi khi xe trong cabin: sau `RIDE_RETRY_S` (10 s) tự nhận lại, lặp tới khi thang nhận (thang bận xe khác → chờ).
- Server khởi động lại: `_adopt_restored_in_cabin` nhận lại ngay khi vị trí cuối của xe là node cabin và lệnh đầu hàng đợi là `elev_ride`
  (không chờ xe online); `run` bị giữ bởi kênh lệnh tới khi xe online lại.
- Test: `test_elevator_bridge.py` (nhận lại sau khởi động lại; nhận lại sau ride huỷ khi xe trong cabin); mô phỏng: tắt/khởi động lại server khi xe ở cabin 7.

## 10. Bấm xác nhận/tiếp tục trực tiếp trên xe (HMI/firmware) ≡ xác nhận trên web

Mọi nút người vận hành bấm trên xe phải làm xe chạy tiếp GIỐNG HỆT nút tương ứng trên web (test `test_hmi_confirm.py` so từng cặp):

| Trạng thái xe | Nút web | Nút trên xe (event firmware) |
|---|---|---|
| Chờ "Đã lấy/giao hàng" (`task_lifecycle`) | `POST /api/execute/lifecycle-ack` | `confirm` hoặc `continue` → xoá chờ xác nhận, xoá route, `on_agv_completed` (cả hai nhánh đều chạy lệnh kế) |
| Chờ xác nhận móc (`hook_pending='pickup'`) | `POST /api/execute/hook-confirm` | **`confirm`** → `confirm_hook_manual` (gửi đúng lệnh móc theo loại xe); sau khi móc xong xe vào "Đã lấy hàng" và nút xác nhận/tiếp tục kế tiếp hoàn tất như trên. `continue` KHÔNG kích móc vì firmware cũng tự phát `continue` khi xe tới đích |
| Hàng đợi vừa KHÔI PHỤC sau khi server khởi động lại | lifecycle-ack | như trên; mọi đường kích hàng đợi đều đi qua `AGVTaskQueue.on_agv_completed` → `restore_prepare_fn` (`main._prepare_restored_head`: nạp bản đồ, nhận lại chuyến thang nếu xe trong cabin, gọi lại thang nếu ở ngoài, không đặt lại "chờ xác nhận" vì người vận hành vừa xác nhận) nên web, nút trên xe và tự động cho cùng kết quả |

## 11. Chuyến thang cũ còn sót (huỷ hàng đợi lúc xe đang đi thang)

Sự cố 23/11 17:02: người vận hành huỷ hàng đợi (16:59:10) khi AGV01 đang trong cabin giữa chuyến, rồi đưa xe ra bằng tay. Chuyến cũ không bao giờ nhận
`agv_exited` → thang kẹt pha `EXITING` + khóa vùng; lệnh `elev_book` của chuỗi mới trùng (cùng thang, cùng tầng nguồn) với ctx cũ nên `book()` trả True
"đặt lại cùng yêu cầu" mà KHÔNG tạo ride mới → không có sự kiện `STARTED` → `elev_book` treo mãi.
Sửa: (1) `book()` chỉ coi là đặt lại khi chuyến CHƯA lên cabin và cùng tầng đích; ngược lại huỷ hẳn chuyến cũ (`_supersede_ctx`: `cancel_ride(force)` +
nhả khóa + dọn ctx) rồi đặt chuyến mới; (2) `check_retries` dọn chuyến đã "lên cabin" mà xe đã ra ngoài cabin và không còn lệnh thang quá `ORPHAN_S`.
Test: `test_elevator_bridge.py` (hai ca cuối).

## 12. Xe lăn thẳng trước khi rẽ tại chỗ (node 30 → 7 vào thang)

Plan bắt đầu bằng cú RẼ tại ĐÚNG thẻ xe đang đứng (vd `{"t":30,"a":5}` rồi RUN). Bình thường xe quay ngay: `driving=True` và event `turn_busy` tới CÙNG gói
state, ~1,9 s sau plan. Có lần (AGV01: 20/11 15:54, 16:38; 21/11 08:53; 23/11 16:55, 17:13) xe bắt đầu lăn THẲNG sau ~1,2 s, không `turn_busy`, chạy hết đoạn
rồi mới quay sau 5–18 s. Server gửi plan đúng; nguyên nhân phía xe (nghi: race giữa `run` nhả WAIT_SYS và plan, hoặc vị trí dừng lệch thẻ) — chưa xác định.
Biện pháp phía server (`LineAGVHandler.arm_standing_turn/_check_standing_turn`): theo dõi plan rẽ tại chỗ (chỉ khi xe đang ĐỨNG lúc gửi); nếu xe `driving`
liên tục ≥ `STANDING_TURN_ROLL_S` (1,5 s) mà chưa có `turn_busy` và thẻ chưa đổi → `stop`, đợi `STANDING_TURN_RESEND_S` (2,5 s) rồi gửi lại ĐÚNG plan
(id mới); tối đa `STANDING_TURN_MAX_RETRIES` (2) lần, sau đó cảnh báo `TURN_NOT_STARTED`. Tắt bằng env `STANDING_TURN_GUARD=0`. Test: `test_standing_turn.py`.
Chưa kiểm chứng trên xe thật.

## 13. Chọn trạm sạc khi đường tới trạm bị xe khác đỗ chắn

Sự cố 25/11 09:24: AGV01 về sạc từ node 4, hai trạm (1 và 27) cùng 0 claim → chọn trạm 1 theo thứ tự, nhưng đường 4→3→2→1 đi qua node 2 nơi AGV03 đang đỗ → AGV01
đứng chờ head-on ~70 s ở node 4 (tới khi hệ thống ép AGV03 nhường, 09:25:40), trong khi trạm 27 (4→3→27) thông. `_pick_least_claimed_station` giờ cộng điểm phạt
(3/node) cho mỗi node TRÊN ĐƯỜNG tới trạm (không tính node xuất phát và chính trạm) đang có xe khác đứng; chỉ dùng để chọn giữa các trạm, không đổi cờ
`all_occupied`. Test: `test_station_path.py`.

