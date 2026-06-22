# Kế hoạch tích hợp AGV ↔ Hệ thống ngoài (WMS / ERP / MES)

> Phiên bản: 1.0 — 22/06/2026  
> Mục tiêu: Cho phép AGV server nhận lệnh từ và gửi kết quả về các hệ thống quản lý bên ngoài (WMS, ERP, MES…) thông qua giao diện cấu hình trực quan trên Web_UI.

---

## 1. Tổng quan kiến trúc

```
┌─────────────────────────────────────────────────────────────────┐
│                        AGV Server (FastAPI)                      │
│                                                                  │
│  ┌──────────────┐    ┌───────────────┐    ┌──────────────────┐  │
│  │  Webhook IN  │    │ Integration   │    │  Callback OUT    │  │
│  │ /api/webhook │◄───│   Engine      │───►│  HTTP POST       │  │
│  │ /{conn_id}   │    │  (asyncio)    │    │  to WMS/ERP      │  │
│  └──────────────┘    └───────────────┘    └──────────────────┘  │
│           │                  │                      ▲            │
│           ▼                  ▼                      │            │
│     AGV Task Queue    agv_integrations DB    Task Events         │
└─────────────────────────────────────────────────────────────────┘
         ▲  │                                         │  ▲
         │  │    Lệnh vào                 Kết quả ra  │  │
         │  ▼                                         ▼  │
┌─────────────────┐                       ┌─────────────────────┐
│   WMS / ERP     │                       │   WMS / ERP         │
│  (push order)   │                       │  (receive result)   │
└─────────────────┘                       └─────────────────────┘
```

**2 chiều giao tiếp:**

| Chiều | Mô tả | Giao thức |
|-------|-------|-----------|
| **Inbound** (WMS → AGV) | WMS gửi lệnh giao hàng, AGV thực thi | Webhook (HTTP POST) |
| **Outbound** (AGV → WMS) | AGV báo hoàn thành, gửi trạng thái | HTTP callback / REST |

---

## 2. Các loại tích hợp hỗ trợ

### 2.1 Inbound — Nhận lệnh từ WMS/ERP

WMS gọi vào AGV server để tạo task:

```
POST https://iot.tot360.com.vn/api/webhook/{connection_id}
Authorization: Bearer {api_key}
{
  "agv_id": "AGV01",          // hoặc để trống → auto-assign
  "destination": "96",
  "map_id": "1779790224391",
  "priority": 1,
  "external_order_id": "WMS-2026-00123",
  "notes": "Giao hàng cho Tổ 3"
}
```

### 2.2 Outbound — Báo kết quả về WMS/ERP

Khi task hoàn thành/thất bại, AGV server tự động gọi callback URL:

```
POST {callback_url}
Authorization: Bearer {wms_token}
{
  "event": "task_completed",
  "external_order_id": "WMS-2026-00123",
  "agv_id": "AGV01",
  "destination": "96",
  "status": "completed",
  "completed_at": "2026-06-22T14:30:00",
  "duration_seconds": 145
}
```

### 2.3 Polling — AGV chủ động hỏi WMS

Theo lịch (cron), AGV server gọi API WMS để lấy danh sách lệnh mới.

---

## 3. Cấu trúc database

### Bảng `agv_integrations` — Danh sách kết nối

```sql
CREATE TABLE agv_integrations (
    id           SERIAL PRIMARY KEY,
    conn_id      VARCHAR(36) UNIQUE DEFAULT gen_random_uuid()::text,
    name         VARCHAR(200) NOT NULL,          -- "WMS Nhà máy A"
    system_type  VARCHAR(50) DEFAULT 'generic',  -- wms | erp | mes | generic
    direction    VARCHAR(20) DEFAULT 'both',     -- inbound | outbound | both
    enabled      BOOLEAN DEFAULT TRUE,

    -- Inbound webhook
    api_key      VARCHAR(128),                   -- key WMS dùng để gọi vào
    map_id       TEXT,                           -- map AGV mặc định
    default_agv  VARCHAR(50),                    -- AGV mặc định (nếu không chỉ định)

    -- Outbound callback
    callback_url TEXT,                           -- URL WMS nhận kết quả
    callback_auth_type VARCHAR(20) DEFAULT 'bearer', -- bearer | basic | apikey | none
    callback_auth_value TEXT,                    -- token/password
    callback_events TEXT DEFAULT 'completed,failed', -- khi nào gọi callback

    -- Polling (optional)
    poll_enabled  BOOLEAN DEFAULT FALSE,
    poll_url      TEXT,
    poll_interval INT DEFAULT 60,               -- giây
    poll_auth_type  VARCHAR(20) DEFAULT 'bearer',
    poll_auth_value TEXT,
    poll_field_map  JSONB DEFAULT '{}',         -- map field WMS → AGV

    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW()
);
```

### Bảng `agv_integration_logs` — Lịch sử gọi API

```sql
CREATE TABLE agv_integration_logs (
    id           SERIAL PRIMARY KEY,
    conn_id      VARCHAR(36),
    direction    VARCHAR(10),   -- in | out
    event        VARCHAR(50),
    status_code  INT,
    request_body TEXT,
    response_body TEXT,
    error_msg    TEXT,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 4. Backend API endpoints

| Method | Endpoint | Mô tả |
|--------|----------|-------|
| `GET`  | `/api/integrations` | Danh sách kết nối |
| `POST` | `/api/integrations` | Tạo kết nối mới |
| `PUT`  | `/api/integrations/{id}` | Cập nhật |
| `DELETE` | `/api/integrations/{id}` | Xóa |
| `POST` | `/api/integrations/{id}/test` | Test kết nối (gửi ping) |
| `GET`  | `/api/integrations/{id}/logs` | Xem lịch sử gọi API |
| **`POST`** | **`/api/webhook/{conn_id}`** | **Nhận lệnh từ WMS (public)** |

---

## 5. Giao diện Web_UI

### Trang mới: `integration.html`

**Layout:**

```
┌─────────────────────────────────────────────────────┐
│ [+ Thêm kết nối]                    [🔍 Tìm kiếm]  │
├─────────────────────────────────────────────────────┤
│ ● WMS Nhà máy A        [WMS]  Inbound+Out  [●BẬT]  │
│   Webhook: /api/webhook/abc123                       │
│   Callback: https://wms.factory-a.com/agv/result    │
│   [Sửa] [Test] [Log] [Xóa]                         │
├─────────────────────────────────────────────────────┤
│ ○ ERP TNG              [ERP]  Outbound     [○TẮT]  │
│   Callback: http://erp.tng.vn/api/agv-done          │
│   [Sửa] [Test] [Log] [Xóa]                         │
└─────────────────────────────────────────────────────┘
```

**Dialog tạo/sửa kết nối — 3 tab:**
- Tab 1: **Thông tin cơ bản** (tên, loại hệ thống, bật/tắt)
- Tab 2: **Inbound** (API key, map AGV mặc định, field mapping)
- Tab 3: **Outbound** (callback URL, xác thực, sự kiện kích hoạt)

---

## 6. Field mapping (ánh xạ trường dữ liệu)

Cho phép WMS dùng tên field khác nhau:

```json
{
  "agv_id":      "robot_code",
  "destination": "drop_location",
  "map_id":      "warehouse_zone",
  "notes":       "order_description"
}
```

Cấu hình trên UI dạng bảng:

| Field AGV | ← | Field WMS |
|-----------|---|-----------|
| agv_id    |   | robot_code |
| destination |  | drop_location |
| notes     |   | order_description |

---

## 7. Kế hoạch thực hiện (4 phase)

### Phase 1 — Backend cơ bản ✅ Target: 1 ngày
- [ ] Tạo bảng `agv_integrations`, `agv_integration_logs`
- [ ] CRUD API `/api/integrations`
- [ ] Webhook endpoint `POST /api/webhook/{conn_id}`
- [ ] Xác thực API key đầu vào

### Phase 2 — Outbound callback ✅ Target: 1 ngày
- [ ] Hook vào task completion event
- [ ] Gửi HTTP callback khi task done/failed
- [ ] Retry 3 lần nếu callback thất bại
- [ ] Lưu log vào `agv_integration_logs`

### Phase 3 — Web UI ✅ Target: 1-2 ngày
- [ ] Trang `integration.html` với danh sách kết nối
- [ ] Dialog tạo/sửa (3 tab)
- [ ] Trang log xem lịch sử gọi API
- [ ] Nút Test kết nối

### Phase 4 — Polling & nâng cao ✅ Target: 1 ngày
- [ ] Polling scheduler (asyncio background task)
- [ ] Field mapping động
- [ ] Auto-assign AGV khi WMS không chỉ định AGV cụ thể
- [ ] Webhook signature verification (HMAC)

---

## 8. Ví dụ thực tế

### Kịch bản: WMS → AGV → WMS

```
1. WMS tạo lệnh giao hàng cho Tổ 3
   POST /api/webhook/abc123
   {"destination": "96", "external_order_id": "WMS-123"}

2. AGV server tạo task, giao cho AGV01

3. AGV01 hoàn thành → server gọi callback
   POST https://wms.factory.com/agv/done
   {"status": "completed", "external_order_id": "WMS-123"}

4. WMS cập nhật trạng thái đơn hàng
```

---

## 9. Bảo mật

- Mỗi kết nối có **API key riêng** (UUID v4, 32 ký tự)
- Callback dùng **Bearer token** hoặc **Basic auth** hoặc **API key header**
- Rate limiting: tối đa 60 request/phút mỗi webhook
- Log toàn bộ inbound/outbound (giữ 30 ngày)
- UI cấu hình yêu cầu đăng nhập admin

---

*File này là kế hoạch thiết kế — cập nhật khi có thay đổi yêu cầu.*
