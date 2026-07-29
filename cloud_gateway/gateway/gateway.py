"""
Cloud API Gateway cho hệ thống AGV.
Nhận request từ Mobile Web, đọc X-Gateway-Key header (HTTP) hoặc ?key= (WebSocket),
tra cứu factories.json rồi forward về đúng nhà máy qua frp tunnel.
"""
import asyncio
import json
import logging
from pathlib import Path

import httpx
import websockets as ws_client
from fastapi import FastAPI, Request, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import Response, JSONResponse, HTMLResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [GATEWAY] %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(title="AGV Cloud Gateway", version="1.0.0")

CONFIG_FILE  = Path(__file__).parent / "factories.json"
FRP_HTTP_PORT = 8090   # phải khớp vhostHTTPPort trong frps.toml
SUBDOMAIN_HOST = "tot360.internal"  # phải khớp subdomainHost trong frps.toml

# Trang tổng hợp thống kê NHIỀU nhà máy cùng lúc (xem tần suất sử dụng AGV từ xa).
# KHÔNG dùng Gateway Key của từng nhà máy (mỗi key chỉ được phép thấy đúng 1 nhà
# máy) — theo yêu cầu KHÔNG làm auth riêng, chỉ dựa vào việc biết đúng URL. Để
# giảm rủi ro lộ URL bị đoán ra, dùng 1 đoạn slug dài ngẫu nhiên thay vì đường dẫn
# dễ đoán kiểu "/dashboard". Đổi FLEET_SLUG này thành chuỗi khác nếu nghi bị lộ.
FLEET_SLUG = "fleet-x7qd92mz"


def load_factories() -> dict:
    """Đọc lại file mỗi request — thêm nhà máy không cần restart."""
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        log.error("Không đọc được factories.json: %s", e)
        return {}


# ─── Health check ────────────────────────────────────────────────────────────

@app.get("/_gateway/health")
async def health():
    factories = load_factories()
    return {
        "status": "ok",
        "factories_registered": list(factories.keys()),
        "total": len(factories),
    }


# ─── Fleet overview: tổng hợp tần suất sử dụng AGV TẤT CẢ nhà máy ───────────
# PHẢI đăng ký TRƯỚC route catch-all forward() bên dưới, nếu không catch-all sẽ
# nuốt mất các path này (coi là forward tới 1 nhà máy, thiếu X-Gateway-Key → 400).

async def _call_factory_json(client: httpx.AsyncClient, frp_host: str, path: str,
                              params: dict | None = None) -> dict:
    """Gọi 1 endpoint JSON của 1 nhà máy qua tunnel, trả kết quả hoặc lỗi rõ ràng."""
    host_hdr = f"{frp_host}.{SUBDOMAIN_HOST}"
    target   = f"http://127.0.0.1:{FRP_HTTP_PORT}/{path.lstrip('/')}"
    try:
        resp = await client.get(target, headers={"Host": host_hdr}, params=params or {})
        if resp.status_code == 200:
            return {"ok": True, "data": resp.json()}
        return {"ok": False, "error": f"HTTP {resp.status_code}"}
    except httpx.ConnectError:
        return {"ok": False, "error": "Tunnel đứt — frpc tại nhà máy không kết nối"}
    except httpx.TimeoutException:
        return {"ok": False, "error": "Nhà máy không phản hồi (timeout)"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get(f"/_gateway/{FLEET_SLUG}/data")
async def fleet_overview_data(period: str = "month"):
    """
    Gọi song song TẤT CẢ nhà máy trong factories.json, lấy thống kê task
    (tần suất/tỉ lệ hoàn thành-thất bại-hủy) + số AGV online/tổng — gộp vào
    1 response duy nhất để xem so sánh giữa các nhà máy.
    """
    factories = load_factories()

    async def _one(key: str, factory: dict) -> dict:
        frp_host = factory["frp_host"]
        entry = {"key": key, "name": factory.get("name", frp_host), "frp_host": frp_host}
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                stats_res, agvs_res = await asyncio.gather(
                    _call_factory_json(client, frp_host, "/api/statistics/tasks", {"period": period}),
                    _call_factory_json(client, frp_host, "/api/execute/agv-list"),
                )

            if stats_res["ok"]:
                s = (stats_res["data"] or {}).get("summary") or {}
                entry["stats"] = {
                    "total":     s.get("total", 0),     "completed": s.get("completed", 0),
                    "failed":    s.get("failed", 0),    "cancelled": s.get("cancelled", 0),
                    "running":   s.get("running", 0),   "queued":    s.get("queued", 0),
                }
            else:
                entry["stats_error"] = stats_res["error"]

            if agvs_res["ok"]:
                raw = agvs_res["data"]
                agv_list = raw if isinstance(raw, list) else (raw or {}).get("agvs", [])
                online = sum(1 for a in agv_list if str((a or {}).get("connection", "")).upper() == "ONLINE")
                entry["agvs"] = {"online": online, "total": len(agv_list)}
            else:
                entry["agvs_error"] = agvs_res["error"]
        except Exception as e:
            # 1 nhà máy lỗi bất thường (format lạ, exception nội bộ...) KHÔNG được
            # kéo sập cả trang — ghi lỗi riêng cho đúng nhà máy đó, các nhà máy khác
            # vẫn hiển thị bình thường.
            log.error("fleet_overview: lỗi xử lý nhà máy %s: %s", key, e)
            entry.setdefault("stats_error", str(e))
            entry.setdefault("agvs_error", str(e))

        return entry

    results = await asyncio.gather(*[_one(k, f) for k, f in factories.items()])
    return {"period": period, "factories": list(results)}


@app.get(f"/_gateway/{FLEET_SLUG}")
async def fleet_overview_page():
    return HTMLResponse(_FLEET_HTML)


_FLEET_HTML = r"""<!doctype html>
<html lang="vi"><head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Tổng hợp AGV — Mọi nhà máy</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  body{margin:0;background:#0b1326;color:#fff;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
  .wrap{max-width:1100px;margin:0 auto;padding:20px 16px}
  h1{font-size:18px;margin:0 0 4px}
  .sub{color:#8ea0c2;font-size:12px;margin-bottom:18px}
  select,button{background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.2);color:#fff;
    border-radius:8px;padding:6px 12px;font-size:13px;cursor:pointer}
  table{width:100%;border-collapse:collapse;margin-top:16px;font-size:13px}
  th,td{padding:8px 10px;text-align:left;border-bottom:1px solid rgba(255,255,255,.08)}
  th{color:#8ea0c2;font-weight:600;font-size:11px;text-transform:uppercase}
  .ok{color:#34d399}.bad{color:#fb7185}.warn{color:#fbbf24}
  .chartwrap{height:320px;position:relative;margin-top:24px;background:rgba(255,255,255,.03);
    border-radius:12px;padding:16px}
  .err{font-size:11px;color:#fb7185}
</style>
</head><body>
<div class="wrap">
  <h1>📊 Tổng hợp tần suất sử dụng AGV — Mọi nhà máy</h1>
  <div class="sub">Xem trực tiếp từ xa, không cần vào từng nhà máy riêng lẻ.</div>
  <select id="period" onchange="load()">
    <option value="week">Tuần này</option>
    <option value="month" selected>Tháng này</option>
    <option value="quarter">Quý này</option>
    <option value="year">Năm nay</option>
  </select>
  <button onclick="load()">🔄 Làm mới</button>

  <table>
    <thead><tr>
      <th>Nhà máy</th><th>AGV online</th><th>Tổng task</th>
      <th>Hoàn thành</th><th>Thất bại</th><th>Đã hủy</th><th>Đang chạy</th>
    </tr></thead>
    <tbody id="tbody"><tr><td colspan="7">Đang tải…</td></tr></tbody>
  </table>

  <div class="chartwrap"><canvas id="chart"></canvas></div>
</div>
<script>
let chart = null;
async function load() {
  const period = document.getElementById('period').value;
  const tbody = document.getElementById('tbody');
  tbody.innerHTML = '<tr><td colspan="7">Đang tải…</td></tr>';
  try {
    // Dùng path tuyệt đối dựa theo URL hiện tại — KHÔNG dùng "data?..." tương đối:
    // nếu URL trang không có dấu "/" cuối, trình duyệt hiểu "data" là NGANG HÀNG
    // với slug (mất luôn đoạn fleet-x7qd92mz khỏi path) → rơi vào route forward()
    // cũ cần X-Gateway-Key.
    const dataUrl = location.pathname.replace(/\/+$/, '') + `/data?period=${period}`;
    const res = await fetch(dataUrl);
    const d = await res.json();
    if (!res.ok || !Array.isArray(d.factories)) {
      throw new Error(d.detail || d.error || `Server trả về không đúng định dạng (HTTP ${res.status})`);
    }
    renderTable(d.factories);
    renderChart(d.factories);
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="7" class="err">Lỗi tải dữ liệu: ${e.message}</td></tr>`;
  }
}
function renderTable(factories) {
  const tbody = document.getElementById('tbody');
  if (!factories.length) { tbody.innerHTML = '<tr><td colspan="7">Chưa có nhà máy nào đăng ký.</td></tr>'; return; }
  tbody.innerHTML = factories.map(f => {
    const agv = f.agvs ? `<span class="ok">${f.agvs.online}</span> / ${f.agvs.total}`
                        : `<span class="err">${f.agvs_error || 'lỗi'}</span>`;
    if (!f.stats) {
      return `<tr><td>${f.name}</td><td>${agv}</td>
        <td colspan="5" class="err">${f.stats_error || 'Không lấy được thống kê'}</td></tr>`;
    }
    const s = f.stats;
    return `<tr><td>${f.name}</td><td>${agv}</td>
      <td>${s.total}</td><td class="ok">${s.completed}</td>
      <td class="bad">${s.failed}</td><td class="warn">${s.cancelled}</td><td>${s.running}</td></tr>`;
  }).join('');
}
function renderChart(factories) {
  const ok = factories.filter(f => f.stats);
  if (chart) chart.destroy();
  chart = new Chart(document.getElementById('chart'), {
    type: 'bar',
    data: {
      labels: ok.map(f => f.name),
      datasets: [
        { label: 'Hoàn thành', data: ok.map(f => f.stats.completed),
          backgroundColor: 'rgba(52,211,153,.75)', borderColor: '#34d399', borderWidth: 1.5,
          borderRadius: 6, borderSkipped: false },
        { label: 'Thất bại/Hủy', data: ok.map(f => f.stats.failed + f.stats.cancelled),
          backgroundColor: 'rgba(251,113,133,.75)', borderColor: '#fb7185', borderWidth: 1.5,
          borderRadius: 6, borderSkipped: false },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { labels: { color: '#fff' } } },
      scales: {
        x: { ticks: { color: 'rgba(255,255,255,.75)' }, grid: { color: 'rgba(255,255,255,.05)' } },
        y: { ticks: { color: 'rgba(255,255,255,.75)' }, grid: { color: 'rgba(255,255,255,.08)' }, beginAtZero: true },
      },
    },
  });
}
load();
</script>
</body></html>
"""


# ─── Forward tất cả request còn lại ─────────────────────────────────────────

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def forward(path: str, request: Request):
    key = request.headers.get("X-Gateway-Key", "").strip()
    if not key:
        raise HTTPException(400, detail="Thiếu header 'X-Gateway-Key'")

    factories = load_factories()
    if key not in factories:
        log.warning("Gateway key không hợp lệ: %s (IP: %s)", key, request.client.host)
        raise HTTPException(403, detail=f"Gateway key không hợp lệ")

    factory   = factories[key]
    frp_host  = factory["frp_host"]
    target    = f"http://127.0.0.1:{FRP_HTTP_PORT}/{path}"
    host_hdr  = f"{frp_host}.{SUBDOMAIN_HOST}"

    # Giữ nguyên toàn bộ headers trừ những cái cần thay thế
    forward_headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in ("host", "x-gateway-key", "content-length")
    }
    forward_headers["Host"] = host_hdr

    body = await request.body()

    log.info("→ %s [%s] /%s", factory.get("name", frp_host), key[:8] + "...", path)

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.request(
                method  = request.method,
                url     = target,
                headers = forward_headers,
                content = body,
                params  = dict(request.query_params),
            )

        log.info("← %s HTTP %d", factory.get("name", frp_host), resp.status_code)
        return Response(
            content    = resp.content,
            status_code= resp.status_code,
            media_type = resp.headers.get("content-type", "application/json"),
        )

    except httpx.ConnectError:
        log.error("Tunnel đứt: %s (%s)", factory.get("name"), frp_host)
        return JSONResponse(
            status_code=502,
            content={"error": f"Không kết nối được nhà máy '{factory.get('name')}'. "
                              "Kiểm tra frpc service tại nhà máy."},
        )
    except httpx.TimeoutException:
        log.error("Timeout: %s (%s)", factory.get("name"), frp_host)
        return JSONResponse(
            status_code=504,
            content={"error": f"Nhà máy '{factory.get('name')}' không phản hồi sau 20 giây."},
        )


# ─── WebSocket proxy ─────────────────────────────────────────────────────────

@app.websocket("/ws")
async def ws_proxy(websocket: WebSocket, key: str = ""):
    """Proxy WebSocket /ws đến nhà máy. Key truyền qua query param ?key=..."""
    factories = load_factories()
    if not key or key not in factories:
        log.warning("WS: gateway key không hợp lệ: '%s'", key)
        await websocket.close(code=4003, reason="Invalid gateway key")
        return

    factory  = factories[key]
    frp_host = factory["frp_host"]
    target   = f"ws://127.0.0.1:{FRP_HTTP_PORT}/ws"
    host_hdr = f"{frp_host}.{SUBDOMAIN_HOST}"

    await websocket.accept()
    log.info("WS → %s [%s]", factory.get("name", frp_host), key[:8] + "...")

    try:
        async with ws_client.connect(target, additional_headers={"Host": host_hdr}) as factory_ws:

            async def relay_client_to_factory():
                try:
                    async for msg in websocket.iter_text():
                        await factory_ws.send(msg)
                except (WebSocketDisconnect, Exception):
                    pass

            async def relay_factory_to_client():
                try:
                    async for msg in factory_ws:
                        await websocket.send_text(str(msg))
                except Exception:
                    pass

            tasks = [
                asyncio.create_task(relay_client_to_factory()),
                asyncio.create_task(relay_factory_to_client()),
            ]
            _done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for t in pending:
                t.cancel()

        log.info("WS ✗ %s đã đóng", factory.get("name", frp_host))

    except Exception as e:
        log.error("WS proxy lỗi: %s", e)
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
