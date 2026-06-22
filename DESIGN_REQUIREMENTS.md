# Tài liệu Yêu cầu Thiết kế Giao diện
## Hệ thống Điều khiển AGV — TOT ACS
**Phiên bản:** 1.0  
**Ngày:** 2026-05-29  
**Dành cho:** Đội thiết kế Web UI

---

## 1. TỔNG QUAN HỆ THỐNG

**TOT ACS (AGV Control System)** là hệ thống giám sát và điều phối robot vận chuyển tự động (AGV) trong nhà máy/kho vận. Giao diện web được xây dựng bằng Dash (Python) kết hợp với các trang HTML/JS thuần nhúng qua iframe.

### 1.1 Công nghệ hiện tại
- Framework: **Plotly Dash** (Python) + HTML/CSS/JS thuần
- Backend API: **FastAPI** (REST, chạy cổng 8000)
- Giao tiếp real-time: **MQTT** (paho) + HTTP Polling
- Ngôn ngữ hỗ trợ: **Tiếng Việt** (mặc định), Tiếng Anh (i18n)

### 1.2 Màu sắc chủ đạo hiện tại

| Vai trò | Mã màu | Mô tả |
|---------|--------|-------|
| Nền chính | `#0b1326` / `#050d1a` | Tối đậm navy |
| Panel | `rgba(15,23,42,0.45)` | Tối + blur backdrop |
| Viền | `rgba(255,255,255,0.09)` | Trắng mờ |
| Accent chính | `#adc6ff` / `#4d8eff` | Xanh dương nhạt |
| Accent phụ | `#ddb7ff` | Tím nhạt |
| Online / OK | `#22c55e` | Xanh lá |
| Warning | `#ffb700` / `#eab308` | Cam/vàng |
| Error / Danger | `#ef4444` | Đỏ |
| MQTT Cloud | `#00d4ff` | Cyan |

### 1.3 Typography hiện tại

| Loại | Font | Cỡ |
|------|------|----|
| Tiêu đề | Inter / Space Grotesk | 18–24px |
| Nội dung | Inter | 12–14px |
| Code / ID / Timestamp | JetBrains Mono | 9–12px |

---

## 2. CẤU TRÚC ĐIỀU HƯỚNG (NAVIGATION)

### 2.1 Sidebar — Cột trái cố định

```
TOT ACS  [Logo]
──────────────────────────
🏠  Home
🗺  Map
    ├─ Create Map
    ├─ Map Configure
    └─ AGV Map  [↗ link ngoài]
📋  Task Manager
    ├─ Create Task
    ├─ Task List
    └─ Thực hiện tác vụ
🤖  AGV Manager
📔  Nhật ký
    ├─ Lịch sử hoạt động
    └─ Logs
📊  Statistic  [chưa có chức năng]
❓  Help  [chưa có chức năng]
```

**Hành vi:**
- Submenu Map / Task / Nhật ký có thể mở rộng/thu gọn
- Mục đang active được highlight
- Khi ở sub-page, submenu cha tự mở

### 2.2 Topbar — Hàng ngang trên cùng

Từ trái sang phải:

| Vị trí | Thành phần | Chức năng |
|--------|-----------|-----------|
| Trái | Tiêu đề "AGV Control System (ACS)" | Tĩnh |
| Giữa | Badge MQTT Mode + nút "Đổi" | Toggle Local ↔ Cloud, polling 5s |
| Phải | Nút ngôn ngữ (VIE/ENG) | Dropdown chọn ngôn ngữ |
| Phải | Avatar + Tên người dùng | Dropdown → Logout |

**Badge MQTT Mode:**
- `MQTT: LOCAL 🏠` — xanh lá `#22c55e`
- `MQTT: CLOUD ☁` — cyan `#00d4ff`
- `MQTT: ?` — xám `#8c909f` (chưa kết nối)

---

## 3. CÁC TRANG & MÀN HÌNH CHI TIẾT

---

### 3.1 Trang Đăng nhập (`/login`)

**Mục đích:** Xác thực người dùng trước khi vào hệ thống.

#### Thành phần UI

| Thành phần | Chi tiết |
|-----------|---------|
| Language selector | Góc trên phải, dropdown: "Tiếng Việt" / "English" |
| Logo | `/assets/icon.png` + tên hệ thống |
| Tiêu đề | "Hệ thống điều khiển AGV" (vi) / "AGV Control System" (en) |
| Subtitle | "Kết nối tự động hóa thông minh" |
| Input Username | Text input, label "Tên đăng nhập" |
| Input Password | Password input, label "Mật khẩu" |
| Nút "Đăng nhập" | Primary button, toàn chiều rộng form |
| Footer | Copyright "© Bản quyền thuộc TOT-TNG" |
| Footer link | "Liên hệ: tot360.com.vn" (góc dưới phải) |

#### Hành vi
- Nhập sai: hiển thị thông báo lỗi inline
- Đăng nhập thành công: redirect sang `/home`

---

### 3.2 Trang Chủ (`/home`)

**Mục đích:** Dashboard tổng quan nhanh về trạng thái hệ thống.

#### Thành phần UI

| Thành phần | Chi tiết |
|-----------|---------|
| Header | "System Overview" |
| Card "AGV Online" | Hiển thị số AGV đang hoạt động, label "Currently active AGVs" |
| Card "Tasks Today" | Số tác vụ trong ngày, label "Total tasks executed" |
| Card "Errors" | Số lỗi, label "Reported system issues" |
| Pie Chart | Biểu đồ trạng thái tác vụ (Plotly): Completed / Pending / In Progress |

**Màu biểu đồ:**
- Completed: `#00d4ff`
- Pending: `#b366ff`
- In Progress: `#00ff9d`

> **Lưu ý:** Dữ liệu hiện là mẫu tĩnh. Cần kết nối API thực.

---

### 3.3 Trang Quản lý AGV (`/agv-manager`)

**Mục đích:** Xem, thêm, cấu hình, xóa các AGV trong hệ thống.

#### Layout
- Header row: Tiêu đề + badge số lượng + nút "+ Add AGV"
- Grid cards: `auto-fill, minmax(240px, 1fr)`
- Panel thêm mới: Slide in từ phải (420px wide)

#### AGV Card (mỗi AGV)

| Trường | Chi tiết |
|--------|---------|
| Icon AGV | Ảnh theo loại: slam, carry, tow, trailer (42×42px) |
| Tên AGV | H5, bold |
| Loại | Text nhỏ (slam_qr / LINE) |
| IP Address | Monospace |
| Port | Monospace |
| Factory | Text |
| Bản đồ được gán | Text |
| Badge trạng thái | "Online" (xanh lá) / "Offline" (xám) |
| Nút "Configure" | Primary, mở panel cấu hình |
| Nút "Delete" | Danger, xác nhận rồi xóa |

#### Panel Thêm AGV (Slide-in từ phải)

| Trường | Loại |
|--------|------|
| AGV Name | Text input |
| Factory | Text input (tên MQTT factory) |
| IP Address | Text input |
| Port | Number input |
| AGV Type | Dropdown: `slam_qr` (VDA5050) / `carry` / `tow` / `trailer` (Line AGV) |
| Bản đồ | Dropdown (từ API `/api/maps/list`) |
| Nút "Save" | Primary |
| Nút "Close" | Secondary |

#### API
- `GET /api/agv-devices` — lấy danh sách AGV
- `POST /api/agv-devices` — thêm AGV mới
- `DELETE /api/agv-devices/{id}` — xóa AGV

---

### 3.4 Trang Tạo Tác vụ (`/task-create`)

**Mục đích:** Tạo và lưu quy trình vận hành (workflow) gồm nhiều bước cho AGV.

#### Layout: 3 cột

```
[Left Sidebar 280px] | [Center Canvas flex-1] | [Right Properties 320px]
```

---

#### Left Sidebar — Thư viện tác vụ

**Phần 1 — Basic Actions (có thể kéo thả hoặc click thêm):**

| Action | Icon | Màu | Mô tả |
|--------|------|-----|-------|
| Move — Đi đến điểm | `directions_car` | `#adc6ff` | AGV di chuyển đến node chỉ định |
| Charge — Sạc pin | `bolt` | `#fbbf24` | AGV về trạm sạc |
| Wait Zone — Về khu chờ | `pause_circle` | `#c2c6d6` | AGV về khu chờ |
| Wait — Chờ tại chỗ | `hourglass_empty` | `#a5b4fc` | AGV đứng yên N giây |

**Phần 2 — Quick Templates:**

| Template | Nội dung |
|---------|---------|
| Nhận & Giao hàng | Move (pickup) → Move (dropoff) |
| Sạc rồi chờ | Charge → Wait Zone |
| Tuần tra | Move → Move → Move → ... |

**Phần 3 — Saved Workflows:**
- Danh sách tên workflow đã lưu (từ API)
- Mỗi item: tên + số bước + nút xóa (×)
- Click: Tải workflow đó vào canvas

**Footer:**
- Nút "💾 Lưu quy trình" (primary, full width)

---

#### Center Canvas — Workflow Editor

**Toolbar:**
- Dropdown chọn bản đồ (`map-select`)
- Input tên workflow (`task-name`)
- Zoom in / out buttons
- Badge: "🟢 Sẵn sàng" / trạng thái

**Canvas (scrollable):**
- Nền: grid pattern tối
- Các **Step Cards** xếp dọc, nối bằng mũi tên:

```
┌─────────────────────────────┐
│  1  🚗  Move — Đi đến điểm  │
│       Dropdown: [chọn node] │
│                           × │
└─────────────────────────────┘
              ↓
┌─────────────────────────────┐
│  2  ⚡  Charge — Sạc pin    │
│       [Trạm sạc tự động]    │
│                           × │
└─────────────────────────────┘
```

- Click vào step card: Mở Properties panel bên phải
- Nút xóa (×) trên mỗi card

**Footer canvas:**
- Left: "Bước: N" + thông báo kết quả
- Right: Nút "🗑 Xóa hết" + Nút "▶️ Mô phỏng"

---

#### Right Panel — Properties (slide-in)

Hiển thị khi chọn một bước:

| Trường | Loại | Điều kiện |
|--------|------|----------|
| Thời gian chờ (giây) | Number input 1–3600 | Chỉ hiện với bước Wait |
| Tốc độ (m/s) | Slider 0.1–2.0 | Tất cả bước |
| Ghi chú | Textarea | Tất cả bước |
| Độ ưu tiên | Buttons: "Bình thường" / "Cao" / "Khẩn" | Tất cả bước |
| Nút "🔄 Cập nhật" | Primary | — |

#### API
- `GET /api/workflow-templates` — danh sách workflow đã lưu
- `POST /api/workflow-templates` — lưu workflow mới
- `GET /api/maps/list` — danh sách bản đồ

---

### 3.5 Trang Danh sách Tác vụ (`/task-list`)

**Mục đích:** Xem, tìm kiếm, sửa tên, xóa các workflow đã lưu.

#### Thành phần UI

| Thành phần | Chi tiết |
|-----------|---------|
| Header | Tiêu đề "Danh sách Tác vụ" + badge "N tác vụ" |
| Search input | Placeholder "Tìm theo tên tác vụ...", filter real-time |
| Nút Refresh | Icon làm mới, gọi lại API |
| Bảng danh sách | Xem bên dưới |
| Phân trang | 15 items/trang, nút Prev/Next + số trang |

#### Bảng (columns)

| Cột | Nội dung |
|-----|---------|
| STT | Số thứ tự |
| Tên tác vụ | Tên + icon workflow |
| Thao tác (steps) | Preview các bước (text ngắn) |
| Thời gian tạo | Format datetime, monospace |
| Sửa | Icon bút chì → mở modal đổi tên |
| Xóa | Icon thùng rác → xóa với xác nhận |

**Modal sửa tên:**
- Input: Tên mới
- Nút "💾 Lưu" + "Hủy"
- Status message inline

#### API
- `GET /api/workflow-templates`
- `POST /api/workflow-templates` — cập nhật tên
- `DELETE /api/workflow-templates/{id}`

---

### 3.6 Trang Thực hiện Tác vụ (`/task-execute`) ⭐ TRANG CHÍNH

**Mục đích:** Điều phối AGV theo thời gian thực — chọn AGV, chọn quy trình, gán điểm đến trên bản đồ, gửi lệnh, giám sát thực thi.

#### Layout: 2 cột

```
[Left Panel ~35%] | [Right Panel ~65%]
```

---

#### LEFT PANEL

**Phần trên (~65%) — Danh sách AGV**

Label "Lựa chọn AGV" + badge `N/M Online`

Mỗi **AGV Card:**

| Thành phần | Chi tiết |
|-----------|---------|
| Icon AGV | Ảnh theo loại, filter xám nếu offline |
| Tên AGV | Bold 13px, màu sáng nếu online, xám nếu offline |
| Type badge | "LINE" (cyan) / "SLAM" (tím) |
| Queue badge | "+N chờ" (cam) — hiển thị nếu có lệnh chờ |
| Dot trạng thái | Xanh lá: SẴN SÀNG / Vàng: ĐANG CHẠY / Xám: OFFLINE |
| Label trạng thái | Text nhỏ JetBrains Mono |
| TAG hiện tại | "TAG: X" (xám, nhỏ) |
| IP Address | Text nhỏ xám |
| Pin (nếu có) | Progress bar + % + icon battery |
| Lệnh đang chạy | Badge nhỏ vàng "▶ command → dest_node" |

- **Click card** (nếu online): Chọn AGV, highlight card

---

**Phần dưới (~35%) — Workflow Selection**

- Label "Quy trình vận hành"
- **Dropdown** chọn workflow (từ API)
- **Preview bước** (nếu đã chọn): Danh sách bước nhỏ, monospace, nền tối nhạt

---

#### RIGHT PANEL

**Hàng trên — Map Controls**

| Thành phần | Chi tiết |
|-----------|---------|
| Icon bản đồ | Material icon |
| Dropdown bản đồ | Chọn bản đồ để hiển thị |
| Badge tên bản đồ | Tên rút gọn (max 16 ký tự) |
| Nút "+" | Zoom in |
| Nút "−" | Zoom out |
| Nút "Fit" | Fit toàn bản đồ vào khung (màu xanh) |

---

**Khu vực bản đồ SVG (chiếm phần lớn)**

- Nền: `#050d1a`
- Kéo để pan, cuộn để zoom
- **Fullscreen button** (góc trên phải): Toggle fullscreen
- **Empty state**: Icon warehouse mờ + "Chọn bản đồ để xem"

**Rendering bản đồ:**

| Thành phần | Style hiện tại |
|-----------|---------------|
| Edges (road) | Xám `#e1e2e7`, dày 12px, linecap square |
| Bezier curves | Xám `#e1e2e7`, dày 12px |
| Mũi tên hướng | Tam giác đặc nhỏ `#e1e2e7`, cách đều |
| Nodes (bình thường) | Tròn `#e1e2e7`, r=14px, không viền |
| Nodes (selected) | Tròn màu step color, viền trắng 2px |
| Nodes (start) | Tròn vàng `#ffb700`, viền trắng |
| Label nodes | Bên trong circle, tối `#0c0e12`, bold JetBrains Mono |
| Badge số bước | Vòng tròn nhỏ góc trên phải của node |
| Pulse ring | Animation cho active step |
| AGV icon | Hình chữ nhật bo góc + mũi tên hướng |
| Route highlight | Polyline sáng theo màu AGV, glow effect |

**Khi fullscreen: Panel AGV status** (góc dưới trái)
- Header: "Fleet" + "N/M online"
- Mỗi AGV: dot màu + tên + trạng thái + điểm đến tiếp theo nếu đang chạy

---

**Các row phụ (hiển thị có điều kiện)**

**Row xác nhận vị trí** (id=`start-node-row`) — Hiện khi Line AGV chưa xác nhận vị trí:
- Icon cảnh báo ⚠ + text "VỊ TRÍ AGV CHƯA XÁC NHẬN"
- Hint: "Server chưa nhận state từ AGV..."
- Nút "Ping AGV" — gửi yêu cầu AGV báo vị trí
- Dropdown chọn node thực tế
- Nút "📍 Gán vị trí"

**Row thông báo** (id=`notif-row`) — Hiện theo trạng thái:
- OFFLINE: cảnh báo mất kết nối
- Đang chạy lệnh: thông tin lệnh + điểm đến
- Lỗi: text đỏ
- Vị trí hiện tại

**Step Destination Selectors** (id=`step-dest-area`, scroll, max-height 140px):
- Một row per bước trong workflow đang chọn
- Mỗi row: badge số thứ tự (màu riêng) + tên bước + dropdown chọn node (hoặc tự động)
- Có thể click node trên bản đồ để chọn cho bước đang active

**Manual Control Bar** (id=`manual-bar`) — Hiện khi chọn Line AGV:
- Label "Điều khiển thủ công"
- Toggle button "🎮 THỦ CÔNG"
- **D-pad** (grid 3×3) khi bật:

  ```
      [↑]
  [←] [■] [→]
      [↓]
  ```
  - ■ = Dừng khẩn cấp (đỏ)
  - Mũi tên = `sendManual('up/down/left/right')`
- **Speed slider**: 50–255, default 150
- **Override Position** (khi manual bật): Dropdown node + Nút "📍 Gán"

**Lifecycle Action Bar** (id=`lifecycle-bar`) — Hiện khi AGV chờ xác nhận thủ công:

| State | Icon | Text | Nút |
|-------|------|------|-----|
| Picking | inventory_2 (xanh lá) | "AGV ĐÃ ĐẾN ĐIỂM LẤY HÀNG" | "✓ ĐÃ LẤY HÀNG XONG" |
| Delivering | local_shipping (xanh dương) | "AGV ĐÃ ĐẾN ĐIỂM GIAO HÀNG" | "✓ ĐÃ GIAO HÀNG XONG" |

---

**Bottom Action Bar — Hàng dưới cùng**

| Vị trí | Thành phần |
|--------|-----------|
| Trái | Badge AGV đã chọn |
| Trái | "›" separator |
| Trái | Badge quy trình đã chọn (tím) |
| Trái | "›" separator |
| Trái | Badge điểm đến |
| Trái | Badge "+N HÀNG CHỜ" (cam, nếu có) |
| Phải | Nút "👥 +N HÀNG CHỜ" (nếu có) |
| Phải | Nút "🆘 DỪNG KHẨN CẤP" (đỏ, luôn hiển thị) |
| Phải | Nút "BẮT ĐẦU NHIỆM VỤ ▶" (xanh lá) |

- Nút BẮT ĐẦU: disabled khi chưa chọn đủ AGV + WF + điểm đến
- Click → Mở **Confirm Modal**

---

#### MODALS trong Task Execute

**1. Confirm Modal — Xác nhận gửi lệnh**
- Icon send (xanh dương)
- Tiêu đề: "Xác nhận gửi lệnh"
- Nội dung: AGV ID, loại AGV, tên workflow, điểm đến
- Nút: "Hủy" (secondary) + "✅ Gửi lệnh" (xanh lá)

**2. Queue Modal — Thông tin hàng chờ**
- Icon queue (cam)
- Tiêu đề: "Lệnh đã xếp hàng chờ"
- Nội dung text mô tả
- Nút: "OK, đã hiểu"

**3. Queue Manager Modal — Quản lý hàng chờ**
- Tiêu đề: "Quản lý hàng chờ — {AGV_ID}"
- Section "Đang thực hiện": 1 lệnh, nút "❌ Hủy lệnh đang chạy"
- Section "Hàng chờ": danh sách N lệnh, nút "🗑 Xóa hàng chờ"
- Nút "🗑 HỦY TẤT CẢ" (đỏ, toàn bộ)
- Nút "Đóng"

---

#### API trong Task Execute

| Endpoint | Method | Mục đích |
|---------|--------|---------|
| `/api/execute/agv-list` | GET | Danh sách AGV + trạng thái |
| `/api/workflow-templates` | GET | Danh sách workflow |
| `/api/maps/list` | GET | Danh sách bản đồ |
| `/api/maps/{mapId}` | GET | Nodes + edges của bản đồ |
| `/api/execute/agv-positions?map_id=X` | GET | Tọa độ AGV trên bản đồ |
| `/api/execute/agv-routes?map_id=X` | GET | Route AGV đang chạy |
| `/api/execute/request-position/{agv_id}` | POST | Ping AGV báo vị trí |
| `/api/agv/set-tag` | POST | Gán vị trí thủ công cho AGV |
| `/api/execute/dispatch` | POST | Gửi lệnh tác vụ |
| `/api/execute/emergency-stop` | POST | Dừng khẩn cấp |
| `/api/execute/lifecycle-confirm` | POST | Xác nhận hoàn thành bước thủ công |
| `/api/execute/queue-cancel` | POST | Hủy lệnh/hàng chờ |
| `/api/execute/manual-control` | POST | Điều khiển thủ công (Line AGV) |

---

### 3.7 Trang Cấu hình Bản đồ & Node (`/map-configure`)

**Mục đích:** Gán chức năng, loại vị trí, hành động cho từng node trên bản đồ. Cấu hình hướng rẽ cho Line AGV (RFID).

#### Layout: 2 cột

```
[Left — Map Canvas flex-1] | [Right Config Panel 380px]
```

---

#### LEFT — Map Canvas

**Top Bar** (có thể ẩn/hiện bằng nút toggle ↑/↓):
- Dropdown chọn bản đồ (`mapSelect`)
- Checkbox "Lật X" / "Lật Y" (flip bản đồ)
- Nút "Khôi phục khung nhìn"
- Info text: "Trạng thái: ..."

**Canvas (id=`map-container`):**
- Nền tối `#020617`
- Layers:
  - Canvas nền (ảnh bản đồ thực tế hoặc trắng)
  - Canvas overlay (edges/beziers)
  - Node layer (clickable divs)
- **Zoom**: Scroll chuột
- **Pan**: Kéo chuột

**Các loại node hiển thị:**

| Loại | Hình dạng | Màu |
|------|----------|-----|
| Chưa gán | Tròn | `#94a3b8` xám |
| Conveyor | Tròn | `#0ea5e9` xanh dương |
| Charger | Tròn | `#f59e0b` cam |
| Dropoff | Tròn | `#ef4444` đỏ |
| Home | Tròn | `#22c55e` xanh lá |
| Buffer | Tròn | `#a855f7` tím |
| Parking | Tròn | `#14b8a6` xanh ngọc |
| RFID (Line AGV) | Hình thoi | cam `#f97316` |
| Dùng chung | Hình vuông bo góc | cyan `#06b6d4` |

- Node được chọn: viền vàng `#facc15` + glow
- Hover: Scale 1.12 + glow xanh

---

#### RIGHT — Config Panel (380px)

Header: "Cấu hình Node" + "Nhấp chọn node..."

**Fields (read-only):**
- Map ID
- Node ID
- Tọa độ (x.xxx, y.xxx)

**Fields (có thể chỉnh sửa):**

| Trường | Loại | Giá trị |
|--------|------|---------|
| Tên chức năng | Text input | VD: "Conveyor01", "ChargeA-01" |
| Loại vị trí | Select | CONVEYOR / CHARGER / DROPOFF / HOME / BUFFER / PARKING |
| Hành động mặc định | Select | PICKUP / DROP / CHARGE / NONE |
| Tương thích AGV | Select | SLAM-QR (VDA5050) / RFID Tag (Line) / Cả hai |

**Phần cấu hình Line AGV** (hiện khi chọn RFID hoặc "Cả hai"):

| Trường | Loại | Giá trị |
|--------|------|---------|
| Rẽ chiều TIẾN | Select | Đi thẳng / ↷ Rẽ PHẢI / ↶ Rẽ TRÁI |
| Rẽ chiều LÙI | Select | Đi thẳng / ↷ Rẽ PHẢI / ↶ Rẽ TRÁI |
| Hành động khi đến | Select | Mặc định / ⚙ WAIT_SYS / 👤 WAIT_USER / 🔋 WAIT_CHARGE |
| Hướng tiếp cận | Select | Mặc định (tiến vào) / 🔄 BWD (lùi vào) |

**Buttons:**
- "💾 Lưu cấu hình node" — primary
- "🗑 Xóa toàn bộ gán" — danger

**Legend (luôn hiển thị):** Danh sách màu-loại node

#### API
- `GET /api/maps/{mapId}` — nodes + edges
- `POST /api/map/node/config` — lưu cấu hình
- `DELETE /api/map/node/config` — xóa cấu hình

---

### 3.8 Trang Tạo Bản đồ (`/create-map`)

**Mục đích:** Tạo bản đồ mới — đặt tên, upload ảnh nền, đặt origin/resolution, lưu vào hệ thống.

> Chi tiết cụ thể cần khảo sát thêm file `map_editor.html`.

---

### 3.9 Trang Lịch sử Hoạt động (`/journal-history`)

**Mục đích:** Xem toàn bộ lịch sử các tác vụ đã/đang thực hiện, lọc và tra cứu.

#### Thành phần UI

| Thành phần | Chi tiết |
|-----------|---------|
| Filter "AGV" | Dropdown chọn AGV cụ thể hoặc "Tất cả" |
| Filter "Trạng thái" | Dropdown: Tất cả / Đang chạy / Hoàn thành / Thất bại / Đã hủy / Hàng chờ |
| Search input | Tìm theo task name, AGV ID, node |
| Nút Refresh | Làm mới dữ liệu |
| Info text | "N / M lượt" |
| Bảng dữ liệu | Xem bên dưới |

#### Bảng lịch sử (columns)

| Cột | Nội dung |
|-----|---------|
| STT | Số thứ tự |
| Tên workflow | Tên + số bước, Session ID (mono nhỏ) |
| AGV | Badge AGV ID (monospace) |
| Điểm đến | Danh sách node (badges) |
| Thời gian giao | Datetime |
| Thời gian hoàn thành | Datetime + duration (nếu completed) |
| Trạng thái | Badge màu: running/completed/failed/cancelled/queued |

**Badge màu trạng thái:**
- running: xanh dương `#60a5fa`
- completed: xanh lá `#4ade80`
- failed: đỏ `#f87171`
- cancelled: xám `#94a3b8`
- queued: vàng `#fbbf24`

**Real-time:** `setInterval(loadHistory, 10000)` — cập nhật mỗi 10 giây

#### API
- `GET /api/journal/missions?limit=300`

---

### 3.10 Trang Logs (`/journal-logs`)

**Mục đích:** Xem log hệ thống real-time dưới dạng terminal.

#### Thành phần UI

| Thành phần | Chi tiết |
|-----------|---------|
| Indicator "🔴 LIVE" | Text nhỏ, luôn hiển thị |
| Toggle Auto-scroll | Bật/tắt tự cuộn xuống dòng mới nhất |
| Search input | Lọc log theo substring |
| Level filter | Tất cả / Lỗi / Cảnh báo / [TRAFFIC] / [QUEUE] / [MQTT] / [CONN] |
| Log count | "N dòng" |
| Nút "Clear" | Xóa view (không xóa log thật) |
| Terminal area | Scroll, monospace, dark background |

**Màu log theo level:**
- ERROR: `#f87171` đỏ
- WARN: `#fde047` vàng
- OK/SUCCESS: `#4ade80` xanh lá
- INFO: `#7dd3fc` xanh dương
- Default: Trắng

**Format mỗi dòng:**
```
[2026-05-29 10:23:45] [INFO] AGV01 → dispatched to node 5
```

**Real-time:** `setInterval(loadLogs, 2000)` — cập nhật mỗi 2 giây

#### API
- `GET /api/journal/logs`

---

## 4. TOAST NOTIFICATIONS (Toàn cục)

Thông báo nhỏ xuất hiện ở **góc dưới giữa** màn hình, auto-dismiss:

| Loại | Màu nền | Ví dụ |
|------|---------|-------|
| success | Xanh lá | "✓ Đã gán AGV01 → node 5" |
| error | Đỏ | "❌ Không thể gửi lệnh" |
| info | Xanh dương | "ℹ AGV01 đang chạy..." |
| warning | Vàng/cam | "⚠ AGV01 chưa có vị trí" |

- Animation: Fade in + slide up
- Duration: ~3–4 giây

---

## 5. TRẠNG THÁI REAL-TIME

| Nguồn dữ liệu | Tần suất | Trang sử dụng |
|--------------|---------|--------------|
| Trạng thái AGV (`/api/execute/agv-list`) | Khi user tương tác | Task Execute |
| Vị trí AGV trên map | Khi user tương tác | Task Execute |
| Route AGV | Khi user tương tác | Task Execute |
| MQTT Mode (`/api/config/mqtt-mode`) | 5 giây | Topbar |
| Lịch sử tác vụ | 10 giây | Journal History |
| Logs hệ thống | 2 giây | Journal Logs |
| SVG Map render | Mỗi khi data thay đổi | Task Execute |

---

## 6. THÀNH PHẦN UI TÁI SỬ DỤNG

### 6.1 Buttons

| Loại | Màu | Dùng cho |
|------|-----|---------|
| Primary | `#4d8eff` xanh dương | Lưu, Xác nhận, Bắt đầu |
| Danger | `#ef4444` đỏ | Xóa, Hủy, Dừng khẩn cấp |
| Success | `#22c55e` xanh lá | Hoàn thành, Giao hàng xong |
| Warning | `#ffb700` cam/vàng | Cảnh báo, Queue |
| Secondary | `rgba(255,255,255,0.1)` | Đóng, Hủy |

### 6.2 Input Controls

| Loại | Style |
|------|-------|
| Text input | Nền `rgba(255,255,255,0.08)`, viền `rgba(255,255,255,0.1)`, chữ trắng |
| Select/Dropdown | Nền trắng, chữ tối `#111` (để đọc được trên dropdown native) |
| Slider | Accent color `#0ea5e9` |
| Checkbox | Accent color `#0ea5e9` |

### 6.3 Badges / Status Indicators

- Dot tròn 5–6px + text nhỏ monospace
- Màu theo trạng thái (xem phần 1.2)

### 6.4 Cards

- Nền `rgba(255,255,255,0.04)`, viền `rgba(255,255,255,0.07)`, border-radius 10px
- Hover: nền sáng hơn nhẹ, đôi khi `translateX(2px)`

### 6.5 Modals

- Overlay đen bán trong suốt: `rgba(0,0,0,0.7)`
- Panel modal: Tối, viền sáng, border-radius 12px
- Animation: Scale 0.95 → 1.0 + fade in

### 6.6 Tables

- Header sticky, nền tối hơn
- Rows: hover highlight nhẹ
- Font chữ: 12–13px

---

## 7. BIỂU ĐỒ & VISUALIZATIONS

| Trang | Loại biểu đồ | Thư viện | Mô tả |
|-------|-------------|---------|-------|
| Home | Pie chart | Plotly.js | Phân bố trạng thái tác vụ |
| Task Execute | SVG Map | Custom SVG | Bản đồ + vị trí AGV + route |
| Map Configure | Canvas 2D | Native Canvas | Bản đồ + nodes + edges |

---

## 8. ĐA NGÔN NGỮ (i18n)

Hệ thống hỗ trợ 2 ngôn ngữ:

| Key ví dụ | Tiếng Việt | Tiếng Anh |
|-----------|-----------|----------|
| `app.title` | "TOT ACS" | "TOT ACS" |
| `menu.home` | "Trang chủ" | "Home" |
| `menu.map` | "Bản đồ" | "Map" |
| `menu.task` | "Tác vụ" | "Task Manager" |
| `home.legend.title` | "Trạng thái tác vụ" | "Task Status" |

- Chọn ngôn ngữ: Lưu vào `lang-store` (Dash store)
- Áp dụng: Toàn bộ sidebar, topbar, labels

---

## 9. ĐỀ XUẤT CHO ĐỘI THIẾT KẾ

### 9.1 Điểm mạnh cần giữ lại
- Theme tối (dark mode) nhất quán
- Cấu trúc sidebar + topbar rõ ràng
- Màu sắc trạng thái AGV nhất quán (xanh/vàng/xám/đỏ)
- Monospace font cho dữ liệu kỹ thuật (ID, tọa độ, timestamp)

### 9.2 Các trang ưu tiên thiết kế lại
1. **Task Execute** — Trang sử dụng nhiều nhất, cần UX tốt nhất
2. **Map Configure** — Nhiều trường input phức tạp, cần layout rõ ràng
3. **AGV Manager** — Card grid cần thêm thông tin
4. **Home Dashboard** — Hiện chỉ là placeholder, cần data thật

### 9.3 Tính năng kỹ thuật bắt buộc giữ nguyên
- SVG-based map rendering (không đổi sang Canvas)
- Polling HTTP (không cần WebSocket mới)
- Iframe cho các trang HTML standalone
- API endpoints (không đổi)
- Màu sắc trạng thái AGV (xanh/vàng/xám theo trạng thái)

---

*Tài liệu này mô tả toàn bộ chức năng hiện có. Mọi chức năng mới nằm ngoài phạm vi tài liệu này.*
