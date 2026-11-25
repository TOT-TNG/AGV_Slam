# 11 — TÀI LIỆU DÀNH CHO DEV FMS: GỬI `depart`, BIẾT ĐÃ NHẬN, BIẾT ĐÃ TỚI, NHẢ AGV RA

> Đối tượng: dev FMS tích hợp với Master thang máy qua MQTT.
> Hợp đồng kỹ thuật chính thức: [04-giao-thuc-mqtt.md](04-giao-thuc-mqtt.md). Giải thích `depart`: [10-lenh-depart.md](10-lenh-depart.md).
> Nếu dùng `ElevatorCoordinator` (Python) thì các bước dưới đây đã được làm sẵn; tài liệu này dành cho FMS tự viết phần gửi lệnh.

## 1. Tóm tắt 5 dòng

1. Gửi **một** lệnh `depart` vào `uelev/v2/{factory}/{elevatorId}/master/instantActions` (QoS 1).
2. **Không có topic ACK riêng.** Phản hồi nằm trong `master/state` → `actionStates[]`, khớp theo `actionId`.
3. `RUNNING` = Master **đã nhận lệnh**. Thường thấy trong < 1 giây khi Master online.
4. Cabin đóng cửa thì Master **mất Wi-Fi** — không thấy `FINISHED` là bình thường. Chỉ cần `RUNNING`.
5. Cabin tới tầng đích, Master tự giữ cửa; FMS thấy `state` mới thì nhả AGV ra.

## 2. Gửi lệnh `depart`

Topic: `uelev/v2/Vietduc/ELV01/master/instantActions`, QoS 1.

```json
{"headerId": 1, "timestamp": "2026-11-13T04:30:00.000Z", "version": "2.0.0",
 "manufacturer": "Vietduc", "serialNumber": "ELV01-master",
 "actions": [
   {"actionType": "depart", "actionId": "a1b2c3d4e5f6", "blockingType": "NONE",
    "actionParameters": [
      {"key": "toFloor", "value": 2},
      {"key": "holdTtlS", "value": 120}
    ]}
 ]}
```

| Tham số | Bắt buộc | Mặc định | Dải |
|---|---|---|---|
| `toFloor` | Có | — | 1..3 |
| `holdTtlS` | Không | 300 | 1..600 (ngoài dải → `FAILED ttl_out_of_range`) |
| `pulseMs` | Không | 1000 | 100..5000 |
| `fastCloseMs` | Không | 3000 | 100..10000 |

**Quy tắc `actionId`** (hay gây lỗi):
- Tối đa **19 ký tự**.
- **Khác nhau mỗi lệnh mới.** Master nhớ 8 `actionId` gần nhất; gặp lại `actionId` đã có thì **không chạy lại**, chỉ báo lại trạng thái cũ.
- Khi **gửi lại vì chưa thấy phản hồi** thì dùng **đúng `actionId` cũ** (không tạo mới), để không chạy lệnh hai lần.

## 3. Biết Master đã nhận lệnh chưa

Subscribe `uelev/v2/Vietduc/ELV01/master/state`. Trong gói có:

```json
"actionStates": [
  {"actionId": "a1b2c3d4e5f6", "actionType": "depart",
   "actionStatus": "RUNNING", "resultDescription": ""}
]
```

| `actionStatus` | Ý nghĩa | FMS làm gì |
|---|---|---|
| `RUNNING` | **Đã nhận**, đang đóng cửa / gọi tầng | Coi như lệnh đã giao thành công. Chuyển sang chờ cabin tới |
| `FINISHED` | Đã bấm xong xung gọi tầng; từ đây Master tự canh | Như trên (có thể không bao giờ thấy, xem §3.2) |
| `FAILED` | Bị từ chối, xem `resultDescription` | Xử lý lỗi theo bảng §3.1 |

### 3.1 Lỗi `FAILED`

| `resultDescription` | Khi nào | Gợi ý xử lý |
|---|---|---|
| `already_at_floor` | Cabin đang ở sẵn `toFloor` | Không phải lỗi nghiêm trọng, không đụng relay nào. Kiểm tra lại yêu cầu |
| `floor_out_of_range` | `toFloor` ngoài 1..3 | Sửa tham số |
| `ttl_out_of_range` | `holdTtlS` ngoài 1..600 | Sửa tham số |
| `superseded` | Có `depart` mới / `releaseDoor` chen vào | Lệnh cũ bị thay thế |
| `cancelled` | `reset` hoặc nút X0 | Hủy chủ động |
| `handed_to_fms` | (ở `FINISHED`) FMS gửi `holdDoor` chen vào | FMS nhận lại quyền giữ cửa, Master không tự giữ nữa |

### 3.2 Vì sao có thể không thấy phản hồi

1. **Đọc sai chỗ**: không có topic `ack` riêng. Phải tìm `actionId` trong `actionStates[]` của `master/state`.
2. **Bỏ lỡ `RUNNING`**: `depart` đi từ `RUNNING` sang `FINISHED` sau khoảng 4 giây (3 giây đóng cửa + 1 giây gọi tầng). Nếu poll thưa thì có thể chỉ thấy `FINISHED` — vẫn tính là đã nhận.
3. **Cabin đã đóng cửa**: Master mất Wi-Fi, không còn gửi `state`. FMS sẽ không thấy `FINISHED`; **đây là bình thường**. Chỉ cần đã thấy `RUNNING` một lần.
4. **Master offline lúc gửi**: kiểm tra `master/connection` (`ONLINE`?) và tuổi của `state` (≤ 5 s mới coi là khả dụng). Nếu offline, **giữ lệnh trong hàng chờ, gửi khi Master `ONLINE` lại**, không tính đó là lần gửi lặp.
5. **`actionId` trùng hoặc dài quá 19 ký tự**: Master bỏ qua.
6. `actionStates` chỉ giữ **8 mục gần nhất**; đọc sớm, đừng dựa vào việc nó tồn tại lâu.

### 3.3 Cơ chế gửi lặp khuyến nghị

```
publish(instantActions, QoS1)
   ├─ thấy actionId trong actionStates → xong (RUNNING/FINISHED/FAILED)
   └─ chưa thấy sau 1 s → gửi LẠI CÙNG actionId
         tối đa 10 lần → coi là EXPIRED (thiết bị có vấn đề)
```
Nếu sau đó vẫn thấy `FINISHED` trong `actionStates` thì vẫn tính là lệnh đã xong (xác nhận đến muộn).

### 3.4 Chẩn đoán nhanh

Serial của Master (115200) in:
```
[LENH] NHAN 'depart' id=a1b2c3d4e5f6
[LENH] -> 'depart' id=a1b2c3d4e5f6 ket qua: RUNNING
```
Thấy hai dòng này nghĩa là Master đã nhận lệnh; nếu FMS vẫn không thấy, lỗi nằm ở đường `state` (subscribe sai topic, broker, ACL).

## 4. Biết cabin đã tới tầng đích

Không có sự kiện "đã tới" riêng. FMS suy ra từ `state`:

```json
"elevator": {"floor": 2, "depart": null, "doorHold": true, "doorHoldAuto": true, "holdTtlS": 112}
```

Dấu hiệu cabin đã tới và Master đang giữ cửa:
- `elevator.floor` == tầng đích
- `elevator.depart` == `null`
- `elevator.doorHold` == `true` (và `doorHoldAuto` == `true`)

Trong lúc đi, `depart.phase` đổi `closing → calling → transit`. Khi cabin đóng cửa thì Master mất mạng, sẽ **có mạng lại cùng lúc cửa mở** ở tầng đích. Có thể thấy `connection` chuyển `CONNECTIONBROKEN → ONLINE`.

Master tự giữ cửa khi cabin dừng ổn định ≥ 2 giây ở tầng đích, trong `holdTtlS` giây. Giữ cửa tự động **không bị nhả khi mất mạng**. Chỉ nhả khi: hết `holdTtlS`, `releaseDoor`, `reset`, hoặc nút X0.

## 5. Nhả AGV ra khỏi cabin

1. Thấy cabin đã tới tầng đích (§4) và Master online.
2. Gửi `{"c":"run"}` qua `instantActions` của AGV. AGV vừa mất mạng trong cabin, **có thể chưa online**, nên:
   - chỉ gửi khi AGV online;
   - **gửi lặp mỗi ~3 giây tới khi thẻ RFID của AGV đổi** (nghĩa là xe đã chạy).
3. AGV lùi ra theo plan đã nạp sẵn từ trước khi vào cabin (AGV không nhận thêm plan trong cabin).
4. Khi AGV báo thẻ **thoát thang** ở tầng đích → FMS gọi `agv_exited(ride_id)` (nếu dùng coordinator).
5. Gửi `releaseDoor` để nhả cửa sớm. Không gửi thì cửa tự nhả sau `holdTtlS`.

## 6. Một lần chỉ một AGV trong cabin

Với `ElevatorCoordinator`, mỗi thang chỉ có **một ride active**. AGV khác sẽ nằm trong hàng đợi và **chưa được `BOARD_ALLOWED`** cho tới khi ride hiện tại xong (`agv_exited` → `releaseDoor`/`releaseHall` → `COMPLETED`). Vì vậy AGV đang chờ ở tầng đích chỉ được vào cabin sau khi AGV cũ đã báo tới thẻ thoát.

Nếu FMS **không** dùng coordinator thì **tự đảm bảo** điều này: không gửi `run` cho AGV vào cabin khi AGV trước chưa báo đã ra.

> **Giới hạn hiện tại (đã biết, chưa sửa):** nếu `agv_exited()` không được gọi (thẻ thoát hỏng, xe kẹt trong cabin) thì (nếu đặt `exit_timeout_s` > 0; **mặc định 0 = chờ vô hạn**) sau `exit_timeout_s` ride kết thúc `FAILED (exit_timeout, agv_inside=true)` và coordinator vẫn có thể nhận ride kế tiếp trong khi xe cũ còn trong cabin. Đang cân nhắc cơ chế chặn thang và tự mở chặn khi xe cũ đọc được thẻ ngoài cabin. **Trong lúc chưa có**, FMS nên coi `FAILED` kèm `agv_inside=true` là báo động và tự dừng gửi AGV mới vào thang đó.

## 7. Mất mạng

| Tình huống | Hành vi |
|---|---|
| Cabin đóng cửa, Master mất Wi-Fi | Bình thường. Master vẫn chạy `depart` tại chỗ |
| FMS hoặc broker mất > 10 s | Giữ cửa do **FMS đặt** bằng `holdDoor` **bị nhả**. Giữ cửa do **Master tự bật** (`doorHoldAuto=true`) **không** bị nhả |
| FMS gửi `holdDoor` chen vào lúc `depart` đang chạy | FMS nhận lại quyền giữ cửa: `depart` thành `FINISHED (handed_to_fms)`, `doorHoldAuto` thành `false`; từ đó mất FMS thì cửa nhả |
| FMS mất broker rồi có lại | Gửi bù lệnh đang chờ; đừng tính đó là lần gửi lặp |

FMS phải giữ presence (LWT + `ONLINE` retained) tại `uagv/v2/{factory}/manager/connection`. Master dựa vào topic này để biết FMS còn sống. Xem [manager-presence.md](../../.claude/docs/manager-presence.md).

## 8. Checklist cho dev

- [ ] Subscribe `master/state` và `master/connection`.
- [ ] `actionId` ≤ 19 ký tự, mỗi lệnh mới một id; gửi lại thì dùng lại id cũ.
- [ ] Coi `RUNNING` hoặc `FINISHED` là "Master đã nhận"; **đừng chờ `FINISHED`** (cabin có thể đã mất mạng).
- [ ] Phát hiện cabin tới bằng `floor == toFloor`, `depart == null`, `doorHold == true`.
- [ ] Nhả AGV bằng `run` **gửi lặp** tới khi AGV online và thẻ đổi.
- [ ] Gửi `releaseDoor` sau khi AGV ra.
- [ ] Không cho AGV thứ hai vào cabin khi AGV trước chưa báo đã ra (nhất là sau `FAILED agv_inside=true`).
- [ ] Giữ presence của FMS (§7).

## 9. Tham khảo

- Giao thức đầy đủ: [04-giao-thuc-mqtt.md](04-giao-thuc-mqtt.md) §3.1, §3.3, §4, §6
- Giải thích `depart`: [10-lenh-depart.md](10-lenh-depart.md)
- Tích hợp coordinator: [07-tich-hop-fms.md](07-tich-hop-fms.md)
- Test thủ công bằng MQTT: [09-test-thu-cong-mqtt.md](09-test-thu-cong-mqtt.md)
- Mẫu chạy được: `elevator/examples/fms_integration.py`
