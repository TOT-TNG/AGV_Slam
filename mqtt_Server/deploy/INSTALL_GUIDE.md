# Hướng dẫn cài đặt AGVmqtt Server

Tài liệu này hướng dẫn cài đặt server AGVmqtt lên 1 máy mới (Windows hoặc Linux),
đóng vai trò máy trung gian: **1 card mạng có internet** (Web UI/mobile/Telegram)
+ **1 card mạng local không internet** (giao tiếp trực tiếp với AGV qua MQTT).

---

## 1. Yêu cầu hệ thống

- Python 3.10+ (đã dùng để phát triển; bản mới hơn thường vẫn chạy được)
- PostgreSQL (đang dùng bản 18, các bản 13+ đều tương thích)
- Mosquitto (MQTT broker)
- 2 card mạng (nếu triển khai theo mô hình trung gian internet + local)

---

## 2. Chuẩn bị mạng (2 card mạng)

1. Card **internet**: cắm/kết nối bình thường, dùng cho Web UI từ xa, app mobile,
   Telegram bot (báo lỗi).
2. Card **local** (nối AGV): đặt **IP tĩnh** cố định, ví dụ `192.168.0.200/24` —
   **không dùng DHCP**, vì IP đổi mỗi lần cắm lại sẽ làm sai cấu hình broker.
   - Windows: Control Panel → Network Connections → chọn card → Properties →
     IPv4 → Use the following IP address → điền IP tĩnh.
   - Linux: cấu hình qua Netplan/NetworkManager tuỳ distro.
3. Ghi lại đúng IP tĩnh này — sẽ dùng ở bước 6 và bước 9.

---

## 3. Cài đặt tự động (khuyến nghị)

Toàn bộ nằm trong `mqtt_Server/deploy/`. Script tự cài Python/PostgreSQL/Mosquitto
(nếu máy chưa có), tạo virtualenv, cài package, tạo database + bảng cần thiết.

### Windows (PowerShell, quyền Administrator khuyến nghị)

```
cd mqtt_Server
deploy\install.bat
```

Giữ lại danh sách AGV đã lưu mặc định. Muốn DB hoàn toàn trống:
```
deploy\install.bat --no-seed
```

### Linux

```
cd mqtt_Server
bash deploy/install.sh
```

> Nếu máy không dùng Debian/Ubuntu (không có `apt-get`), tự cài Python3
> (kèm `python3-venv`, `python3-pip`), PostgreSQL, Mosquitto trước, rồi chạy
> thẳng `python3 deploy/setup.py`.

> **Có sẵn file backup đầy đủ dữ liệu (AGV/bản đồ/lịch trình đã cấu hình)?**
> Sau khi script tạo xong database rỗng, phục hồi thẳng bằng backup thay vì dùng
> seed mặc định — xem mục "Phục hồi nhanh từ bản backup đầy đủ" ở Bước 4 bên dưới.

---

## 4. Cài đặt thủ công (nếu không dùng script)

1. Cài Python, PostgreSQL, Mosquitto theo hướng dẫn chính thức của từng phần mềm.
2. Tạo virtualenv + cài package:
   ```
   python -m venv .venv
   .venv\Scripts\pip install -r requirements.txt      (Windows)
   .venv/bin/pip install -r requirements.txt           (Linux)
   ```
3. Tạo database `TOT_AGV` (hoặc tên khác, nhớ khớp với bước 6) rồi chạy:
   ```
   psql -U postgres -d TOT_AGV -f deploy/schema_core.sql
   psql -U postgres -d TOT_AGV -f deploy/seed_agv_devices.sql   (tuỳ chọn — giữ AGV cũ)
   ```

### Phục hồi nhanh từ bản backup đầy đủ (khuyến nghị nếu đã có sẵn)

Nếu đã có file backup đầy đủ database (`deploy/backup/TOT_AGV_full_backup.sql` — export
từ máy đã cấu hình sẵn AGV/bản đồ/lịch trình/tích hợp...), **bỏ qua bước 3 ở trên**
(không cần chạy `schema_core.sql`/`seed_agv_devices.sql`) — phục hồi thẳng bằng file backup:

1. Tạo database rỗng (tên phải khớp bước 6, mặc định `TOT_AGV`):
   ```
   createdb -U postgres TOT_AGV
   ```
2. Phục hồi toàn bộ dữ liệu (bảng + cấu hình AGV/bản đồ/lịch trình/tích hợp) từ backup:
   ```
   psql -U postgres -d TOT_AGV -f deploy/backup/TOT_AGV_full_backup.sql
   ```
   File backup đã có sẵn `--clean --if-exists` nên chạy lại nhiều lần vẫn an toàn (tự
   xoá bảng cũ trước khi tạo lại, không báo lỗi "already exists").

Sau bước này, máy mới đã có ĐẦY ĐỦ AGV/bản đồ/lịch trình/tích hợp y hệt máy gốc — không
cần cấu hình lại gì thêm (ngoại trừ IP mạng ở bước 6, luôn phải chỉnh riêng theo từng máy).

> **Tạo bản backup mới** (từ máy đang chạy, sau khi đã cấu hình xong, để mang đi cài máy
> khác): chạy lệnh sau trên máy nguồn (thay đúng đường dẫn `deploy/backup/` của máy đó):
> ```
> pg_dump -U postgres -d TOT_AGV --no-owner --no-privileges --clean --if-exists -f deploy/backup/TOT_AGV_full_backup.sql
> ```
> Lệnh sẽ hỏi mật khẩu Postgres nếu chưa cấu hình `.pgpass`/`pgpass.conf` — nhập bình
> thường, không ảnh hưởng gì.

---

## 5. Cấu hình broker MQTT (Mosquitto)

Copy `deploy/mosquitto.conf.template` vào đúng vị trí cấu hình Mosquitto rồi
khởi động lại dịch vụ:

- **Windows**: đè vào `C:\Program Files\mosquitto\mosquitto.conf`, sau đó
  `Restart-Service mosquitto` (hoặc qua `services.msc`).
- **Linux**: copy vào `/etc/mosquitto/conf.d/agvmqtt.conf`, sau đó
  `sudo systemctl restart mosquitto`.

Nội dung mặc định: lắng nghe port **1883** trên mọi card mạng, **không yêu cầu
TLS, không yêu cầu username/password** (`allow_anonymous true`).

Kiểm tra broker đã lắng nghe đúng chưa:
```powershell
Get-NetTCPConnection -LocalPort 1883
Test-NetConnection -ComputerName <IP-card-local> -Port 1883
```
`TcpTestSucceeded` phải là `True`.

---

## 6. Cấu hình server

1. Mở `mqtt_Server/mqtt_client.py`, tìm dòng:
   ```python
   return os.getenv("MQTT_BROKER", "192.168.0.200").strip(), int(os.getenv("MQTT_PORT", "1883"))
   ```
   Đổi `"192.168.0.200"` thành đúng **IP tĩnh của card local** đã đặt ở bước 2
   (hoặc để nguyên nếu đã đặt static IP đúng giá trị này).
   Có thể thay vì sửa code, đặt biến môi trường `MQTT_BROKER`/`MQTT_PORT` — code
   sẽ ưu tiên biến môi trường nếu có.

   ⚠️ **Port luôn là `1883`** (plain, không TLS) cho broker local — **không đổi
   thành `8883`**, đó là port riêng cho broker cloud (TLS).

2. Xác nhận `mqtt_Server/mqtt_mode.json` là:
   ```json
   {"mode": "local"}
   ```
   (script `setup.py` đã tự ghi sẵn; nếu chỉnh tay thì kiểm tra lại file này).

---

## 7. Chạy thử server

```
.venv\Scripts\python.exe main.py        (Windows)
.venv/bin/python3 main.py               (Linux)
```

Log mong đợi (không có dòng `Broker connect error`):
```
[MQTT] Connected with result code 0
[MQTT] Subscribed (LINE v2): uagv/v2/+/+/state
...
[SUCCESS] TOÀN BỘ HỆ THỐNG SẴN SÀNG! (MQTT + DB + Dashboard + Real-time)
```

Nếu thấy `[MQTT] Broker connect error: timed out` hoặc `actively refused` →
xem mục **11. Xử lý sự cố** bên dưới.

Web UI truy cập qua: `http://<IP-bất-kỳ-của-máy>:8000`

---

## 8. Chạy nền tự động (khuyến nghị cho máy sản xuất)

Chạy thử ở bước 7 thành công rồi mới làm bước này.

### Windows (dùng NSSM, quyền Administrator)
```
powershell -ExecutionPolicy Bypass -File deploy\install_service_windows.ps1
```
Script tự tải `nssm.exe` về `deploy\` (không phụ thuộc `winget` — nhiều máy
nhà máy không có sẵn), tạo service tên `AGVmqttServer` — tự khởi động cùng
Windows, tự restart nếu crash — rồi tự kiểm tra ngay tại chỗ (đọc trạng thái
service + xác nhận port 8000 đã lắng nghe), báo PASS/FAIL rõ ràng.
Log: `deploy\service_stdout.log` / `service_stderr.log`.

Gỡ bỏ: `deploy\nssm.exe remove AGVmqttServer confirm`

**Web UI (Dash, port 8050)** — cài thêm service riêng (tương tự cơ chế trên,
dùng chung `nssm.exe` đã tải), để dashboard cũng tự chạy nền/tự khởi động
cùng Windows, không cần mở PowerShell mở sẵn:
```
powershell -ExecutionPolicy Bypass -File deploy\install_service_webui_windows.ps1
```
Service tên `AGVWebUI`, phụ thuộc `AGVmqttServer` (khởi động sau). Log:
`deploy\service_webui_stdout.log` / `service_webui_stderr.log`.
Gỡ bỏ: `deploy\nssm.exe remove AGVWebUI confirm`

Chạy thử tay (không cài service, chỉ để test nhanh) cả 2 cùng lúc:
`deploy\run_all.ps1` — tự mở 2 cửa sổ PowerShell riêng cho `mqtt_Server`
và `Web_UI`.

### Linux (systemd)
```
sudo bash deploy/install_service_linux.sh
```
Kiểm tra: `sudo systemctl status agvmqtt` — Log: `journalctl -u agvmqtt -f`

Gỡ bỏ: `sudo systemctl disable --now agvmqtt`

**Web UI (Dash, port 8050)** — cài thêm service riêng (tương tự cơ chế trên,
dùng chung venv đã tạo sẵn):
```
sudo bash deploy/install_service_webui_linux.sh
```
Service tên `agv-webui`. Kiểm tra: `sudo systemctl status agv-webui` — Log:
`journalctl -u agv-webui -f`

Gỡ bỏ: `sudo systemctl disable --now agv-webui && sudo rm /etc/systemd/system/agv-webui.service`

Chạy thử tay (không cài service, chỉ để test nhanh) cả 2 cùng lúc trên Windows:
`deploy\run_all.ps1` — tự mở 2 cửa sổ PowerShell riêng cho `mqtt_Server`
và `Web_UI`. Trên Linux chạy tay bằng 2 terminal riêng (hoặc `&`/`tmux`) tương tự.

---

## 9. Cập nhật hệ thống (không cần cài lại từ đầu)

Sau lần cài đầu tiên, khi có code mới (git pull về, hoặc copy file cập nhật
thủ công), **không cần lặp lại toàn bộ Bước 3** (không cần cài lại
Python/PostgreSQL/Mosquitto, không tạo lại venv, không tạo lại database) —
chỉ cần chạy script cập nhật, nó tự nạp code mới lên venv/service đã có sẵn.

### Windows
```powershell
cd mqtt_Server
powershell -ExecutionPolicy Bypass -File deploy\update_windows.ps1
```

### Linux
```bash
cd mqtt_Server
bash deploy/update_linux.sh
```

Cả 2 script đều làm chung 1 quy trình:
1. `git pull` code mới nhất (nếu thư mục gốc là git repo; nếu cập nhật bằng
   copy file thủ công thì copy đè **trước** khi chạy script)
2. Cài lại `requirements.txt` vào **venv đã có sẵn** — chỉ cài thêm/nâng cấp
   gói thay đổi, không tạo venv mới
3. Chạy lại `schema_core.sql` — an toàn tuyệt đối (`CREATE TABLE IF NOT
   EXISTS`), **không xoá/mất dữ liệu**, chỉ đề phòng schema có thêm cột/bảng mới
4. Tự restart 2 service (`AGVmqttServer`/`AGVWebUI` trên Windows,
   `agvmqtt`/`agv-webui` trên Linux) để nạp code mới — bỏ qua service nào
   chưa cài

> Script **không đụng vào dữ liệu AGV/bản đồ/lịch trình đã cấu hình**. Muốn
> đồng bộ dữ liệu mới từ máy khác (không phải code), dùng riêng mục "Phục hồi
> nhanh từ bản backup đầy đủ" ở Bước 4, không lẫn với bước cập nhật này.

---

## 10. Mở firewall để truy cập từ máy khác trong LAN

Mặc định firewall chặn port lạ từ máy khác kết nối tới. Muốn máy khác trong
cùng mạng LAN mở được Web UI (bản đồ/cấu hình AGV) và Dashboard thống kê,
chạy trên **máy server**:

### Windows (PowerShell quyền Administrator)
```powershell
New-NetFirewallRule -DisplayName "AGVmqtt Web (8000)" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow
New-NetFirewallRule -DisplayName "AGVmqtt Dashboard (8050)" -Direction Inbound -Protocol TCP -LocalPort 8050 -Action Allow
```

### Linux (ufw — nếu dùng firewall khác như firewalld thì đổi lệnh tương ứng)
```bash
sudo ufw allow 8000/tcp comment "AGVmqtt Web"
sudo ufw allow 8050/tcp comment "AGVmqtt Dashboard"
```

Sau đó từ máy khác cùng LAN, mở trình duyệt vào:
- `http://<IP-máy-server>:8000` — bản đồ AGV, cấu hình bản đồ, quản lý AGV
- `http://<IP-máy-server>:8050` — dashboard thống kê

(`<IP-máy-server>` là IP thật của card mạng LAN trên máy server — xem bằng
`ipconfig`/`ip addr`, **không dùng `localhost`** khi truy cập từ máy khác.)

Nếu vẫn không vào được từ máy khác sau khi mở firewall, kiểm tra theo thứ tự:
1. `ping <IP-máy-server>` từ máy client — xác nhận thông mạng.
2. Cả 2 máy cùng subnet (ví dụ cùng dải `192.168.1.x`).
3. Router/switch trung gian không chặn port nội bộ (hiếm gặp trong LAN thường).

---

## 11. Cấu hình AGV vật lý

Với mỗi AGV:
1. Bật AGV, kết nối WiFi vào access point riêng của AGV (`configAGV`).
2. Vào `192.168.4.1` trên trình duyệt.
3. Điền:
   - **Broker**: đúng IP tĩnh card local ở bước 2 (vd `192.168.0.200`)
   - **Port**: `1883`
   - **TLS**: tắt (nếu màn hình có tuỳ chọn TLS khoá port về 8883, tắt TLS trước)
   - **Username/Password**: để trống
4. Lưu, AGV sẽ khởi động lại và tự kết nối vào broker.

---

## 12. Tạo bản đồ

Nếu đã có layout vẽ sẵn bằng draw.io: vào **Create Map** trên Web UI, bấm
**"📐 Import draw.io"**, chọn file (phải export dạng **không nén** — draw.io:
File → Export as → XML, bỏ tick "Compressed"). Hệ thống tự tạo node (theo nhãn
số thẻ) + cạnh nối. Cấu hình hành động từng node (loại vị trí, tổ, vai trò
rơ-moóc...) và lưu bản đồ như bình thường sau khi import.

Sau đó vào **Quản lý AGV** → chọn AGV → tab Cấu hình → gán bản đồ vừa tạo.

---

## 13. Xử lý sự cố thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra / sửa |
|---|---|---|
| `Broker connect error: timed out` | IP trong `MQTT_BROKER` không khớp IP thật của card local | `ipconfig`/`ip addr` kiểm tra IP card local hiện tại, sửa lại cho khớp |
| `Broker connect error: ... actively refused` | Sai **port** (vd để 8883 thay vì 1883) hoặc Mosquitto chưa chạy | Kiểm tra `Get-Service mosquitto` / `systemctl status mosquitto`, xác nhận port `1883` |
| AGV không hiện online dù broker đã kết nối | AGV vật lý chưa cấu hình đúng broker/port, hoặc TLS đang bật sai port | Kiểm tra lại bước 11; thử `mosquitto_sub -h <ip> -t "uagv/v2/+/+/state"` xem có tin nào tới không |
| Lỗi Telegram `getaddrinfo failed` lúc khởi động | Card internet chưa có mạng lúc server khởi động | Bình thường, không ảnh hưởng AGV/MQTT — bot **không tự retry**, cần khởi động lại server sau khi có internet |
| `[UNIFIED_MQTT] init warning ... UTF-8 BOM` | File cấu hình có BOM ở đầu file (thường do lưu bằng Notepad trên Windows) | Không chặn hệ thống chạy (non-fatal), có thể bỏ qua |
| App báo thiếu bảng khi chạy trên DB mới | Chưa chạy `schema_core.sql` (2 bảng `agv_devices`/`agv_tasks` không tự tạo) | Chạy lại `deploy/setup.py` hoặc `psql -f deploy/schema_core.sql` |
| Máy khác trong LAN không mở được Web UI/Dashboard (nhưng `localhost` trên máy server vẫn vào bình thường) | Firewall chặn port 8000/8050 từ máy khác | Làm theo bước 10 (`New-NetFirewallRule`/`ufw` cho 2 port) |
