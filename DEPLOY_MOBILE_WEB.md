# Tài liệu triển khai AGV Mobile Web lên Cloud

## Kiến trúc tổng quan

```
[Trình duyệt / Mobile]
        │ HTTPS
        ▼
[Nginx Docker - iot.tot360.com.vn]
        │
        ├── /mobile/  ──►  [agv-mobile container :3001]  (Flutter Web App)
        │
        └── /acs/     ──►  [AGV Cloud Gateway :9000]
                                    │ HTTP + WebSocket
                                    ▼
                           [frps :8090 - phân phối theo Host header]
                                    │
                           ┌────────┴────────┐
                           ▼                 ▼
                    [Nhà máy A]        [Nhà máy B]
                    (frpc running)     (frpc running)
                    FastAPI :8000      FastAPI :8000
```

---

## 1. Chuẩn bị VPS

- Ubuntu/Debian VPS với Docker đã cài sẵn
- Domain `iot.tot360.com.vn` đã trỏ DNS về IP VPS
- SSL certificate cho `iot.tot360.com.vn` (Let's Encrypt)
- Docker nginx container đang chạy, mount conf từ `~/tng-infra/nginx/conf/`

---

## 2. Cài đặt frps trên VPS

### 2.1 Cài frps

```bash
# Download frp (ví dụ v0.61.0)
wget https://github.com/fatedier/frp/releases/download/v0.61.0/frp_0.61.0_linux_amd64.tar.gz
tar -xzf frp_0.61.0_linux_amd64.tar.gz
cp frp_0.61.0_linux_amd64/frps /usr/local/bin/
```

### 2.2 Cấu hình `/etc/frp/frps.toml`

```toml
bindPort = 7500
vhostHTTPPort = 8090
subdomainHost = "tot360.internal"
auth.token = "SECRET_TOKEN_NGAU_NHIEN"   # thay bằng token thực
log.to = "/var/log/frps.log"
log.level = "info"
```

### 2.3 Tạo systemd service

```bash
cat > /etc/systemd/system/frps.service << 'EOF'
[Unit]
Description=frp server
After=network.target

[Service]
ExecStart=/usr/local/bin/frps -c /etc/frp/frps.toml
Restart=always

[Install]
WantedBy=multi-user.target
EOF

systemctl enable frps
systemctl start frps
```

---

## 3. Cài đặt AGV Cloud Gateway

### 3.1 Tạo thư mục và file

```bash
mkdir -p /etc/agv-gateway
```

### 3.2 File `/etc/agv-gateway/gateway.py`

```python
import asyncio, json, logging
from pathlib import Path
import httpx
import websockets as ws_client
from fastapi import FastAPI, Request, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import Response, JSONResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [GATEWAY] %(message)s")
log = logging.getLogger(__name__)

app = FastAPI()
CONFIG_FILE = Path(__file__).parent / "factories.json"
FRP_HTTP_PORT = 8090
SUBDOMAIN_HOST = "tot360.internal"

def load_factories():
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        log.error("Không đọc được factories.json: %s", e)
        return {}

@app.get("/_gateway/health")
async def health():
    factories = load_factories()
    return {"status": "ok", "factories_registered": list(factories.keys()), "total": len(factories)}

@app.api_route("/{path:path}", methods=["GET","POST","PUT","DELETE","PATCH"])
async def forward(path: str, request: Request):
    key = request.headers.get("X-Gateway-Key", "").strip()
    if not key:
        raise HTTPException(400, detail="Thiếu header 'X-Gateway-Key'")
    factories = load_factories()
    if key not in factories:
        raise HTTPException(403, detail="Gateway key không hợp lệ")
    factory  = factories[key]
    frp_host = factory["frp_host"]
    target   = f"http://127.0.0.1:{FRP_HTTP_PORT}/{path}"
    host_hdr = f"{frp_host}.{SUBDOMAIN_HOST}"
    forward_headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in ("host", "x-gateway-key", "content-length")
    }
    forward_headers["Host"] = host_hdr
    body = await request.body()
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.request(
                method=request.method, url=target,
                headers=forward_headers, content=body,
                params=dict(request.query_params),
            )
        return Response(content=resp.content, status_code=resp.status_code,
                        media_type=resp.headers.get("content-type","application/json"))
    except httpx.ConnectError:
        return JSONResponse(status_code=502, content={"error": f"Không kết nối được nhà máy '{factory.get('name')}'"})
    except httpx.TimeoutException:
        return JSONResponse(status_code=504, content={"error": f"Nhà máy '{factory.get('name')}' không phản hồi"})

@app.websocket("/ws")
async def ws_proxy(websocket: WebSocket, key: str = ""):
    factories = load_factories()
    if not key or key not in factories:
        await websocket.close(code=4003, reason="Invalid gateway key")
        return
    factory  = factories[key]
    frp_host = factory["frp_host"]
    target   = f"ws://127.0.0.1:{FRP_HTTP_PORT}/ws"
    host_hdr = f"{frp_host}.{SUBDOMAIN_HOST}"
    await websocket.accept()
    try:
        async with ws_client.connect(target, extra_headers={"Host": host_hdr}) as factory_ws:
            async def to_factory():
                try:
                    async for msg in websocket.iter_text():
                        await factory_ws.send(msg)
                except: pass
            async def to_client():
                try:
                    async for msg in factory_ws:
                        await websocket.send_text(str(msg))
                except: pass
            tasks = [asyncio.create_task(to_factory()), asyncio.create_task(to_client())]
            _done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for t in pending: t.cancel()
    except Exception as e:
        log.error("WS proxy lỗi: %s", e)
        try: await websocket.close(code=1011)
        except: pass
```

> **Lưu ý quan trọng:** Dùng `extra_headers` (không phải `additional_headers`) để tương thích với websockets >= 13.x.

### 3.3 File `/etc/agv-gateway/requirements.txt`

```
fastapi==0.115.0
uvicorn[standard]==0.32.0
httpx==0.28.0
websockets==13.1
```

### 3.4 File `/etc/agv-gateway/factories.json`

```json
{
  "KEY_TNG_VietDuc": {
    "name": "TNG Việt Đức",
    "frp_host": "vietduc"
  }
}
```

> Thêm nhà máy mới: chỉ cần thêm entry vào file này, **không cần restart gateway**.

### 3.5 Cài dependencies và tạo systemd service

```bash
pip install -r /etc/agv-gateway/requirements.txt

cat > /etc/systemd/system/agv-gateway.service << 'EOF'
[Unit]
Description=AGV Cloud Gateway
After=network.target

[Service]
WorkingDirectory=/etc/agv-gateway
ExecStart=uvicorn gateway:app --host 0.0.0.0 --port 9000 --workers 2
Restart=always

[Install]
WantedBy=multi-user.target
EOF

systemctl enable agv-gateway
systemctl start agv-gateway
```

---

## 4. Cấu hình Nginx

Thêm vào file `~/tng-infra/nginx/conf/dashboard.conf` (trong server block 443):

```nginx
# AGV Cloud Gateway
location ^~ /acs/ {
    proxy_pass         http://172.18.0.1:9000/;
    proxy_set_header   Host              $host;
    proxy_set_header   X-Real-IP         $remote_addr;
    proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header   X-Forwarded-Proto $scheme;

    proxy_http_version 1.1;
    proxy_set_header   Upgrade    $http_upgrade;
    proxy_set_header   Connection "upgrade";

    proxy_read_timeout 86400s;
    proxy_send_timeout 30s;
}

# AGV Mobile Web App
location ^~ /mobile/ {
    proxy_pass http://172.18.0.1:3001/;
}
```

> **Quan trọng:** KHÔNG tạo server block riêng cho `iot.tot360.com.vn` — sẽ conflict với `dashboard.conf`.

Reload nginx:
```bash
docker exec nginx nginx -t && docker exec nginx nginx -s reload
```

---

## 5. Cài đặt frpc tại nhà máy

### 5.1 File `frpc.toml` tại máy Windows nhà máy

```toml
serverAddr = "<IP_VPS>"
serverPort = 7500
auth.token = "SECRET_TOKEN_NGAU_NHIEN"   # phải khớp với frps

[[proxies]]
name = "agv-web-vietduc"
type = "http"
localIP = "127.0.0.1"
localPort = 8000
subdomain = "vietduc"   # phải khớp với frp_host trong factories.json
```

### 5.2 Chạy frpc

```bash
frpc -c frpc.toml
```

---

## 6. Sửa source code Flutter app

### 6.1 Các thay đổi bắt buộc trong source code

**a) `lib/services/api_service.dart`** — thêm gateway key support:
- Dùng `String.fromEnvironment('API_BASE_URL')` thay vì hardcode URL
- Thêm `_headers()` tự động gắn `X-Gateway-Key`
- Auth login dùng `AUTH_BASE_URL` riêng (không qua gateway)
- `wsUrl` thêm `?key=` vào WebSocket URL

**b) `lib/setting_screen.dart`** — thêm UI nhập Gateway Key

**c) Tất cả file dart có URL `http://appmobile.tng.vn`** — đổi sang `https://`:
```
login_screen.dart
product_count.dart
task_execute_screen.dart
```

**d) `pubspec.yaml`** — hạ SDK constraint để tương thích Flutter 3.24.5:
```yaml
environment:
  sdk: ">=3.5.0 <4.0.0"
```

### 6.2 Dockerfile

```dockerfile
FROM debian:bookworm-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git wget unzip xz-utils zip ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ARG FLUTTER_VERSION=3.24.5
ENV FLUTTER_HOME=/opt/flutter
ENV PATH="${FLUTTER_HOME}/bin:${FLUTTER_HOME}/bin/cache/dart-sdk/bin:${PATH}"

RUN git clone --depth 1 --branch ${FLUTTER_VERSION} \
    https://github.com/flutter/flutter.git ${FLUTTER_HOME} \
    && flutter config --enable-web \
    && flutter precache --web \
    && flutter doctor -v

WORKDIR /app
COPY pubspec.yaml pubspec.lock ./
RUN flutter pub get

COPY . .

ARG API_BASE_URL=http://192.168.0.200:8000

RUN flutter build web \
    --release \
    --web-renderer html \
    --dart-define=API_BASE_URL=${API_BASE_URL} \
    --base-href=/mobile/

FROM nginx:1.27-alpine AS production
COPY --from=builder /app/build/web /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

---

## 7. Build và deploy Flutter Web App

### 7.1 Trên VPS — clone repo và build

```bash
# Clone repo Mobile_TOT
git clone https://github.com/TOT-TNG/Mobile_TOT.git ~/Mobile_TOT

# Fix SDK constraint nếu cần
sed -i 's/sdk: \^3\.7\.2/sdk: ">=3.5.0 <4.0.0"/' ~/Mobile_TOT/app_tot/pubspec.yaml

# Fix http -> https cho appmobile URLs
sed -i 's|http://appmobile\.tng\.vn|https://appmobile.tng.vn|g' \
  ~/Mobile_TOT/app_tot/lib/login_screen.dart \
  ~/Mobile_TOT/app_tot/lib/task_execute_screen.dart \
  ~/Mobile_TOT/app_tot/lib/product_count.dart

# Build Docker image
cd ~/Mobile_TOT/app_tot
docker build \
  --build-arg API_BASE_URL=https://iot.tot360.com.vn/acs \
  -t ducmanh1801/agv-mobile:latest \
  --progress=plain \
  .
```

### 7.2 Push lên Docker Hub

```bash
docker login -u ducmanh1801
docker push ducmanh1801/agv-mobile:latest
```

### 7.3 Chạy container

```bash
docker run -d \
  --name agv-mobile \
  --restart unless-stopped \
  -p 3001:80 \
  ducmanh1801/agv-mobile:latest
```

### 7.4 Khi có code mới — cập nhật

```bash
cd ~/Mobile_TOT && git pull

# Re-apply các fix (nếu bị reset bởi git pull)
sed -i 's/sdk: \^3\.7\.2/sdk: ">=3.5.0 <4.0.0"/' app_tot/pubspec.yaml
sed -i 's|http://appmobile\.tng\.vn|https://appmobile.tng.vn|g' \
  app_tot/lib/login_screen.dart \
  app_tot/lib/task_execute_screen.dart \
  app_tot/lib/product_count.dart

cd app_tot
docker build --build-arg API_BASE_URL=https://iot.tot360.com.vn/acs \
  -t ducmanh1801/agv-mobile:latest .
docker push ducmanh1801/agv-mobile:latest
docker stop agv-mobile && docker rm agv-mobile
docker run -d --name agv-mobile --restart unless-stopped -p 3001:80 ducmanh1801/agv-mobile:latest
```

---

## 8. Sử dụng ứng dụng

1. Mở trình duyệt: `https://iot.tot360.com.vn/mobile/`
2. Đăng nhập bằng tài khoản nhân viên TNG
3. Vào **Settings** → nhập **Gateway Key** (ví dụ: `KEY_TNG_VietDuc`)
4. Lưu → app kết nối đến nhà máy tương ứng qua cloud

---

## 9. Thêm nhà máy mới

1. Cài và cấu hình frpc tại nhà máy mới (ví dụ subdomain `songcong3`)
2. Thêm entry vào `/etc/agv-gateway/factories.json` trên VPS:
   ```json
   "KEY_TNG_SongCong3": {
     "name": "TNG Sông Công 3",
     "frp_host": "songcong3"
   }
   ```
3. **Không cần restart** gateway — file được đọc lại mỗi request

---

## 10. Kiểm tra hệ thống

```bash
# Health check gateway (LUON qua prefix /acs/ khi goi tu ngoai qua Nginx -
# Nginx CHI proxy /acs/* toi gateway; goi thang /_gateway/health se roi vao
# location / (dashboard) va tra ve trang HTML khac, KHONG phai loi thuc su)
curl https://iot.tot360.com.vn/acs/_gateway/health

# Test tunnel nhà máy trực tiếp
curl -s -H "Host: vietduc.tot360.internal" http://127.0.0.1:8090/api/maps/list

# Test qua gateway
curl -s -H "X-Gateway-Key: KEY_TNG_VietDuc" http://127.0.0.1:9000/api/maps/list

# Xem log gateway
journalctl -u agv-gateway -n 50 --no-pager

# Xem log frps
tail -f /var/log/frps.log
```

---

## 11. Các lỗi thường gặp

| Lỗi | Nguyên nhân | Xử lý |
|-----|------------|-------|
| `400 Bad Request` từ gateway | Thiếu `X-Gateway-Key` header | Kiểm tra app đã set gateway key chưa |
| `403 Forbidden` từ gateway | Gateway key sai | Kiểm tra key trong `factories.json` |
| `502 Bad Gateway` | frpc tại nhà máy không kết nối | Kiểm tra frpc service tại nhà máy |
| `Mixed Content` HTTPS/HTTP | URL appmobile dùng `http://` | Đổi thành `https://` trong source code |
| WebSocket `additional_headers` error | Version websockets không tương thích | Dùng `extra_headers` thay thế |
| `flutter pub get` Dart SDK mismatch | pubspec yêu cầu Dart cao hơn Flutter có | Sửa sdk constraint trong pubspec.yaml |
| `location directive not allowed here` | Thêm location ngoài server block | Chỉ thêm location BÊN TRONG server `{}` |
