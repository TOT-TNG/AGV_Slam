# Cài đặt tunnel cloud (frpc) tại máy nhà máy

Thư mục này dùng để kết nối server local (`mqtt_Server/main.py`, port 8000)
với Cloud Gateway trên VPS, để web mobile / dashboard truy cập được từ xa.

## Yêu cầu trước khi cài

- Windows, PowerShell **chạy với quyền Administrator**.
- `mqtt_Server/main.py` đã cài đặt và **đang chạy** (xem
  `mqtt_Server/deploy/INSTALL_GUIDE.md`) — script sẽ cảnh báo nếu chưa thấy
  gì lắng nghe ở port 8000, nhưng không bắt buộc phải chạy trước lúc cài đặt.
- Máy có kết nối Internet ra ngoài (card mạng Internet — xem mục Dual NIC
  trong `CLOUD_GATEWAY_DEPLOYMENT.md` nếu nhà máy dùng 2 card mạng tách biệt
  Internet/AGV).
- Có sẵn: `-Subdomain` (định danh nhà máy, phải khớp `frp_host` trong
  `factories.json` trên VPS) và `-Token` (auth.token thật của frps, hỏi
  người quản trị hệ thống nếu chưa có — **không** commit token này lên git).

## Cài đặt (nhà máy mới hoặc cài lại)

```powershell
cd cloud_gateway\factory
.\deploy_frpc.ps1 -Subdomain "<subdomain-nha-may>" -Token "<token-that>"
```

Script tự động, không cần thao tác gì thêm:
1. Kiểm tra đang chạy quyền Administrator, kiểm tra port 8000 đang có dịch vụ.
2. Thêm ngoại lệ Windows Defender cho `C:\frp` (frp hay bị AV báo nhầm virus).
3. Tải `frpc.exe` đúng version (nếu chưa có).
4. Sinh `frpc.toml` với đúng subdomain/token (không commit vào git).
5. Tải NSSM + cài Windows Service `frpc-agv` (tự khởi động cùng máy, tự
   restart nếu lỗi).
6. Đọc log ngay tại chỗ và báo **PASS/FAIL** — không cần quyền SSH vào VPS.

Chạy lại y hệt lệnh trên để cập nhật cấu hình (đổi token, đổi subdomain...)
— script tự dọn service cũ trước khi tạo lại.

## Kiểm tra thủ công sau khi cài

```powershell
Get-Service frpc-agv
Get-Content C:\frp\frpc-service.log -Tail 20
```
Log có `login to server success` + `start proxy success` là tunnel đã thông.

## Gỡ cài đặt

```powershell
.\uninstall_service.ps1                # gỡ service, giữ lại C:\frp
.\uninstall_service.ps1 -RemoveFiles    # gỡ service + xoá luôn C:\frp
```

## Lỗi thường gặp

| Log / triệu chứng | Nguyên nhân | Cách sửa |
|---|---|---|
| `token in login doesn't match token from configuration` | Token không khớp giữa máy này và `/etc/frp/frps.toml` trên VPS | Xác nhận đúng token thật, chạy lại `deploy_frpc.ps1` với `-Token` đúng |
| `connect to server error` | Sai `-ServerAddr`/`-ServerPort`, hoặc firewall/mạng chặn kết nối ra ngoài | Kiểm tra card mạng Internet, kiểm tra `-ServerPort` khớp `bindPort` trong `frps.toml` trên VPS |
| Tải `frpc.exe`/`nssm.exe` báo lỗi "virus or potentially unwanted software" | Windows Defender chặn (false positive, frp là tool tunneling hay bị nghi ngờ) | Script đã tự thêm exclusion; nếu vẫn lỗi, thêm tay tại Windows Security > Virus & threat protection > Exclusions > `C:\frp` |
| `Cannot start service` | Thường không còn xảy ra (đã chuyển sang dùng NSSM thay vì `sc.exe` thô) — nếu vẫn gặp, service cũ có thể do `sc.exe` tạo trước đây | Chạy `.\uninstall_service.ps1` rồi cài lại bằng `deploy_frpc.ps1` |
| PowerShell báo lỗi `Missing closing '}'` / ký tự lạ khi chạy `.ps1` | File `.ps1` chứa tiếng Việt có dấu nhưng thiếu BOM UTF-8, PowerShell 5.1 đọc sai encoding | Các file trong thư mục này đã cố tình viết không dấu để tránh lỗi này; nếu tự thêm nội dung, giữ nguyên tắc không dùng ký tự có dấu trong file `.ps1` |
| Web mobile vẫn không load được danh sách nhà máy dù tunnel đã thông | `factories.json` trên VPS chưa có entry cho nhà máy này, hoặc JSON bị lỗi cú pháp (dấu phẩy thừa, thiếu `}`) | `curl https://iot.tot360.com.vn/acs/_gateway/health` — nếu `total` thấp bất thường hoặc thiếu key, sửa lại `factories.json` trên VPS (dán đè nguyên khối, kiểm tra JSON hợp lệ trước khi lưu) |

## Thêm nhà máy mới

Xem mục "Quy trình thêm nhà máy mới" trong `../../CLOUD_GATEWAY_DEPLOYMENT.md`.
Tóm tắt: 1 dòng JSON trên VPS (`factories.json`) + 1 lệnh `deploy_frpc.ps1` tại
máy nhà máy mới. Không cần sửa gì trong repo.
