# Triển khai Cloud Gateway — AGV Remote Control qua Internet

> Phiên bản: 1.0 — 25/06/2026
> Mục tiêu: Cho phép Mobile Web gửi lệnh điều khiển AGV từ Internet xuống Server Local tại nhà máy
> Domain: `https://iot.tot360.com.vn`

---

## Tổng quan kiến trúc

```
[Mobile Web]
     │  HTTPS + header "X-Gateway-Key: KEY_TNG_SONGCONG"
     ▼
[Nginx :443]  ──── iot.tot360.com.vn (SSL termination)
     │
     ▼
[Cloud API Gateway :9000]  ← gateway.py — đọc key, forward request
     │  HTTP nội bộ
     ▼
[frp Server :8090]  ← frps — nhận tunnel từ các nhà máy
     │  tunnel TCP (factory chủ động kết nối ra, port 7500)
     ▼
[frp Client]  ← frpc chạy trên Server nhà máy
     │
     ▼
[FastAPI Local :8000]  ← mqtt_Server/main.py — endpoint đã có sẵn
     │
     ▼
[AGV / MQTT Broker nội bộ]
```

**Tại sao dùng frp thay VPN:**
- frp dùng TCP port 443/7500 → IT nhà máy hầu như không block
- Không cần biết IP public của nhà máy (factory chủ động kết nối ra)
- Không cần cấu hình IP gì thêm — chỉ cần biết địa chỉ cloud server
- Thêm nhà máy mới: cài frpc + thêm 1 dòng config, không cần chạm cloud

---

## Các file và vị trí quan trọng

| File | Nơi đặt | Mục đích |
|------|---------|----------|
| `/usr/local/bin/frps` | Cloud VPS | Binary frp server |
| `/etc/frp/frps.toml` | Cloud VPS | Cấu hình frp server |
| `/etc/systemd/system/frps.service` | Cloud VPS | Auto-start frps |
| `/etc/agv-gateway/factories.json` | Cloud VPS | Danh sách nhà máy + Gateway Key |
| `/etc/agv-gateway/gateway.py` | Cloud VPS | Cloud API Gateway service |
| `/etc/systemd/system/agv-gateway.service` | Cloud VPS | Auto-start gateway |
| `/etc/nginx/sites-available/iot.tot360.com.vn` | Cloud VPS | Nginx config |
| `frpc.toml` | Server nhà máy | Cấu hình frp client (mỗi nhà máy 1 file) |

---

## Phase 1 — frp Server trên Cloud VPS

### 1.1 Cài đặt frps

```bash
# Tải frp (kiểm tra version mới nhất tại github.com/fatedier/frp/releases)
wget https://github.com/fatedier/frp/releases/download/v0.62.1/frp_0.62.1_linux_amd64.tar.gz
tar -xzf frp_*.tar.gz
cp frp_*/frps /usr/local/bin/
chmod +x /usr/local/bin/frps

# Tạo thư mục config
mkdir -p /etc/frp
```

### 1.2 File `/etc/frp/frps.toml`

```toml
# Port factory client kết nối vào
bindPort = 7500

# Port frp dùng nội bộ để phân phối HTTP request đến từng factory
vhostHTTPPort = 8090

# Token xác thực — PHẢI KHỚP với frpc.toml bên factory
# Đổi thành chuỗi ngẫu nhiên dài trước khi deploy thật
auth.token = "THAY_BANG_SECRET_TOKEN_NGAU_NHIEN"

# Log
log.to    = "/var/log/frps.log"
log.level = "info"
```

### 1.3 File `/etc/systemd/system/frps.service`

```ini
[Unit]
Description=frp server (AGV Cloud Gateway)
After=network.target

[Service]
ExecStart=/usr/local/bin/frps -c /etc/frp/frps.toml
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable --now frps

# Kiểm tra
systemctl status frps
curl http://localhost:8090   # trả lỗi frp là OK
```

### 1.4 Mở firewall

```bash
# Port factory kết nối vào
ufw allow 7500/tcp comment "frp tunnel"

# Port 443 cho HTTPS (nếu chưa mở)
ufw allow 443/tcp
```

---

## Phase 2 — Cloud API Gateway

### 2.1 File `/etc/agv-gateway/factories.json`

```json
{
  "KEY_TNG_SONGCONG": {
    "name": "TNG Sông Công",
    "frp_host": "songcong"
  },
  "KEY_TNG_HANOI": {
    "name": "TNG Hà Nội",
    "frp_host": "hanoi"
  }
}
```

> **Thêm nhà máy mới:** thêm 1 entry vào file này, không cần restart service.
> `frp_host` phải khớp với `subdomain` trong `frpc.toml` của nhà máy đó.

### 2.2 File `/etc/agv-gateway/gateway.py`

```python
"""
Cloud API Gateway — nhận request từ Mobile Web, forward đến đúng nhà máy qua frp tunnel.
Đọc X-Gateway-Key header để xác định nhà máy, tra cứu trong factories.json.
"""
import json
import httpx
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import Response

app = FastAPI()

CONFIG_FILE = Path("/etc/agv-gateway/factories.json")
FRP_HTTP_PORT = 8090   # khớp với vhostHTTPPort trong frps.toml

def load_factories() -> dict:
    return json.loads(CONFIG_FILE.read_text())

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def forward(path: str, request: Request):
    key = request.headers.get("X-Gateway-Key", "").strip()
    if not key:
        raise HTTPException(400, "Thiếu header X-Gateway-Key")

    factories = load_factories()
    if key not in factories:
        raise HTTPException(403, f"Gateway key '{key}' không hợp lệ")

    factory = factories[key]
    # frp resolve subdomain dạng: {subdomain}.{domain_gốc}
    # Nhưng vì gọi nội bộ qua localhost:8090, dùng Host header để frp biết forward đi đâu
    frp_host = factory["frp_host"]
    target_url = f"http://127.0.0.1:{FRP_HTTP_PORT}/{path}"

    body = await request.body()
    forward_headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in ("host", "x-gateway-key", "content-length")
    }
    # frp dùng Host header để route đến đúng factory
    forward_headers["Host"] = f"{frp_host}.tot360.internal"

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.request(
                method  = request.method,
                url     = target_url,
                headers = forward_headers,
                content = body,
                params  = dict(request.query_params),
            )
    except httpx.ConnectError:
        raise HTTPException(502, f"Không kết nối được nhà máy '{factory['name']}' — tunnel có thể đang đứt")
    except httpx.TimeoutException:
        raise HTTPException(504, f"Nhà máy '{factory['name']}' không phản hồi trong 20 giây")

    return Response(
        content    = resp.content,
        status_code= resp.status_code,
        media_type = resp.headers.get("content-type", "application/json"),
    )
```

### 2.3 Cài dependencies và chạy

```bash
pip install fastapi uvicorn httpx

# Test thử
uvicorn gateway:app --host 127.0.0.1 --port 9000 --reload
```

### 2.4 File `/etc/systemd/system/agv-gateway.service`

```ini
[Unit]
Description=AGV Cloud API Gateway
After=network.target frps.service

[Service]
WorkingDirectory=/etc/agv-gateway
ExecStart=/usr/bin/python3 -m uvicorn gateway:app --host 127.0.0.1 --port 9000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable --now agv-gateway
systemctl status agv-gateway
```

---

## Phase 3 — Nginx + SSL

### 3.1 Lấy SSL certificate (miễn phí, tự gia hạn)

```bash
apt install certbot python3-certbot-nginx
certbot --nginx -d iot.tot360.com.vn
```

### 3.2 File `/etc/nginx/sites-available/iot.tot360.com.vn`

```nginx
server {
    listen 443 ssl;
    server_name iot.tot360.com.vn;

    ssl_certificate     /etc/letsencrypt/live/iot.tot360.com.vn/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/iot.tot360.com.vn/privkey.pem;

    # Toàn bộ request → Cloud API Gateway
    location / {
        proxy_pass         http://127.0.0.1:9000;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_read_timeout 30s;
    }
}

# Redirect HTTP → HTTPS
server {
    listen 80;
    server_name iot.tot360.com.vn;
    return 301 https://$host$request_uri;
}
```

```bash
ln -s /etc/nginx/sites-available/iot.tot360.com.vn /etc/nginx/sites-enabled/
nginx -t
systemctl reload nginx
```

---

## Phase 4 — frp Client tại Nhà máy

> Làm lại phase này cho mỗi nhà máy mới. Chỉ thay đổi `subdomain`.

### 4.1 — Windows (trường hợp thực tế của dự án này)

Toàn bộ máy nhà máy trong dự án này chạy Windows (`mqtt_Server/main.py`
qua `uvicorn`). Dùng bộ script có sẵn trong `cloud_gateway/factory/` —
**không tự cài tay theo kiểu Linux bên dưới**:

```powershell
cd cloud_gateway\factory
.\deploy_frpc.ps1 -Subdomain "<subdomain-nha-may>" -Token "<token-that>"
```

Script tự tải `frpc.exe` đúng version, tự sinh `frpc.toml`, tự cài Windows
Service bằng NSSM (không dùng `sc.exe` trực tiếp — `frpc.exe` không phải
service-aware binary nên `sc.exe create` tạo được nhưng không khởi động nổi),
và tự đọc log báo PASS/FAIL ngay tại chỗ. Chi tiết đầy đủ, bảng lỗi thường
gặp: xem `cloud_gateway/factory/README.md`.

### 4.2 — Linux (tham khảo, KHÔNG áp dụng cho máy nhà máy trong dự án này)

Phần dưới đây mô tả cách cài thủ công trên Linux — giữ lại để tham khảo nếu
sau này có nhà máy dùng Linux server, không áp dụng cho các máy Windows hiện tại.

```bash
wget https://github.com/fatedier/frp/releases/download/v0.62.1/frp_0.62.1_linux_amd64.tar.gz
tar -xzf frp_*.tar.gz
cp frp_*/frpc /usr/local/bin/
```

File `frpc.toml` (mỗi nhà máy khác nhau 1 chỗ: `subdomain`):
```toml
serverAddr = "iot.tot360.com.vn"
serverPort = 7500
auth.token = "THAY_BANG_SECRET_TOKEN_NGAU_NHIEN"

[[proxies]]
name      = "agv-local"
type      = "http"
localIP   = "127.0.0.1"
localPort = 8000          # port FastAPI local (mqtt_Server)
subdomain = "songcong"    # *** THAY ĐỔI CHO MỖI NHÀ MÁY *** — khớp frp_host trong factories.json
```

Cài service tự khởi động:
```bash
# /etc/systemd/system/frpc.service
[Unit]
Description=frp client (AGV tunnel to cloud)
After=network.target

[Service]
ExecStart=/usr/local/bin/frpc -c /etc/frp/frpc.toml
Restart=always
RestartSec=10   # thử kết nối lại sau 10s nếu mất kết nối

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable --now frpc
```

### 4.3 Cấu hình Dual NIC

| Card mạng | Kết nối | Default Gateway | Ghi chú |
|-----------|---------|-----------------|---------|
| Card 1 (Internet) | Modem của nhà máy | **Bật** (điền IP modem) | Dùng để frpc kết nối ra cloud |
| Card 2 (Nội bộ) | Switch nội bộ / AGV | **Để trống** | Cô lập hoàn toàn mạng AGV khỏi internet |

> Việc để trống Default Gateway ở Card 2 đảm bảo máy AGV không thể tự đi ra internet,
> và dữ liệu sản xuất không rò rỉ ra ngoài.

### 4.4 Kiểm tra tunnel

```bash
# Từ cloud VPS, gọi thử vào factory qua frp
curl -H "Host: songcong.tot360.internal" http://localhost:8090/
# → phải trả về response từ FastAPI local của nhà máy
```

> Với máy Windows dùng `deploy_frpc.ps1` (mục 4.1), script đã tự làm bước
> kiểm tra này ngay tại máy (đọc log local, báo PASS/FAIL) — không bắt buộc
> phải SSH vào VPS mới biết kết quả.

---

## Phase 5 — Cập nhật Mobile Web

### 5.1 Thêm header vào mọi request

```javascript
// Ví dụ fetch API
const GATEWAY_KEY = "KEY_TNG_SONGCONG";  // lưu trong config app

async function callAGV(path, body) {
  const resp = await fetch(`https://iot.tot360.com.vn/${path}`, {
    method:  "POST",
    headers: {
      "Content-Type":  "application/json",
      "X-Gateway-Key": GATEWAY_KEY,
      "Authorization": `Bearer ${API_KEY}`,   // api_key của integration_engine
    },
    body: JSON.stringify(body),
  });
  return resp.json();
}
```

### 5.2 Ví dụ gửi lệnh tạo task

```http
POST https://iot.tot360.com.vn/api/webhook/{conn_id}
X-Gateway-Key: KEY_TNG_SONGCONG
Authorization: Bearer {api_key}
Content-Type: application/json

{
  "agv_id": "AGV01",
  "destination": "96",
  "external_order_id": "MOBILE-2026-001"
}
```

Response trả về **giống hệt** như gọi trực tiếp vào local server:
```json
{
  "task_id": "uuid...",
  "agv_id": "AGV01",
  "destination": "96",
  "status": "pending"
}
```

---

## Quy trình thêm nhà máy mới

Khi triển khai thêm 1 nhà máy, chỉ cần 2 việc — **không cần sửa code, không cần
hỏi lại, không cần SSH gì thêm ngoài bước 1**:

**1. Trên cloud** — thêm vào `/etc/agv-gateway/factories.json`:
```json
"KEY_TNG_BINHDUONG": {
  "name": "TNG Bình Dương",
  "frp_host": "binhduong"
}
```
Không cần restart bất kỳ service nào (gateway tự reload file mỗi request).

**2. Tại nhà máy mới** — mở PowerShell **với quyền Administrator** trên Server
nhà máy đó, chạy:
```powershell
cd cloud_gateway\factory
.\deploy_frpc.ps1 -Subdomain "binhduong" -Token "<auth.token thật, lấy từ /etc/frp/frps.toml trên VPS>"
```
Script `deploy_frpc.ps1` tự lo hết: tải `frpc.exe` đúng version (nếu chưa có),
sinh file `frpc.toml` với đúng `subdomain` (file này KHÔNG commit lên git —
chỉ nằm cục bộ tại `C:\frp\` trên từng máy), và cài/khởi động Windows Service
`frpc-agv` tự chạy lại cùng máy. Token dùng chung 1 giá trị cho mọi nhà máy
(không phải theo từng nhà máy) — chỉ `-Subdomain` là khác nhau mỗi lần.

Kiểm tra ngay sau khi chạy — script tự in ra 2 lệnh curl để test (1 test tunnel
trực tiếp từ VPS, 1 test qua gateway với Gateway Key thật của nhà máy đó).

---

## Troubleshooting

| Triệu chứng | Kiểm tra |
|-------------|----------|
| Mobile web nhận 403 | Gateway key sai hoặc chưa có trong `factories.json` |
| Mobile web nhận 502 | frpc của nhà máy đó đang ngắt — kiểm tra `systemctl status frpc` tại nhà máy |
| Mobile web nhận 504 | FastAPI local (:8000) không phản hồi — kiểm tra `mqtt_Server` có đang chạy không |
| frpc không kết nối được | Kiểm tra `auth.token` hai bên có khớp không; kiểm tra port 7500 đã mở trên cloud chưa |
| Tunnel kết nối nhưng request lỗi | Kiểm tra `subdomain` trong frpc.toml có khớp với `frp_host` trong factories.json không |

```bash
# Xem log cloud gateway
journalctl -u agv-gateway -f

# Xem log frp server
journalctl -u frps -f
tail -f /var/log/frps.log

# Xem log frp client tại nhà máy
journalctl -u frpc -f
```

---

## Tóm tắt effort

| Phase | Nội dung | Thời gian |
|-------|----------|-----------|
| 1 | frps trên cloud | ~2 giờ |
| 2 | Cloud API Gateway | ~3 giờ |
| 3 | Nginx + SSL | ~1 giờ |
| 4 | frpc tại nhà máy | ~1 giờ/nhà máy |
| 5 | Mobile web header | ~2 giờ |

**Tổng cloud + mobile:** ~1 ngày làm việc
**Mỗi nhà máy mới thêm vào:** ~1 giờ

---

*File này mô tả kiến trúc và quy trình triển khai — cập nhật khi có thay đổi hạ tầng hoặc thêm nhà máy.*
