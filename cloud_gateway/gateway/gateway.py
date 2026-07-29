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
async def fleet_overview_data():
    """
    Danh sách nhẹ TẤT CẢ nhà máy — chỉ số AGV online/tổng, dùng cho màn hình
    danh sách ban đầu (load nhanh). Xem chi tiết chuyến đi từng nhà máy qua
    endpoint /trips riêng, chỉ gọi khi bấm vào 1 nhà máy cụ thể.
    """
    factories = load_factories()

    async def _one(key: str, factory: dict) -> dict:
        frp_host = factory["frp_host"]
        entry = {"key": key, "name": factory.get("name", frp_host), "frp_host": frp_host}
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                agvs_res = await _call_factory_json(client, frp_host, "/api/execute/agv-list")

            if agvs_res["ok"]:
                raw = agvs_res["data"]
                agv_list = raw if isinstance(raw, list) else (raw or {}).get("agvs", [])
                online = sum(1 for a in agv_list if str((a or {}).get("connection", "")).upper() == "ONLINE")
                entry["agvs"] = {"online": online, "total": len(agv_list)}
            else:
                entry["agvs_error"] = agvs_res["error"]
        except Exception as e:
            log.error("fleet_overview data: lỗi xử lý nhà máy %s: %s", key, e)
            entry.setdefault("agvs_error", str(e))

        return entry

    results = await asyncio.gather(*[_one(k, f) for k, f in factories.items()])
    return {"factories": list(results)}


@app.get(f"/_gateway/{FLEET_SLUG}/trips")
async def fleet_overview_trips(key: str, period: str = "month",
                                date_from: str | None = None, date_to: str | None = None):
    """Thống kê CHUYẾN ĐI chi tiết của đúng 1 nhà máy (bấm vào từ danh sách)."""
    factories = load_factories()
    factory = factories.get(key)
    if not factory:
        raise HTTPException(404, detail="Không tìm thấy nhà máy")

    params = {"period": period}
    if period == "custom" and date_from and date_to:
        params["date_from"] = date_from
        params["date_to"]   = date_to

    async with httpx.AsyncClient(timeout=15.0) as client:
        res = await _call_factory_json(client, factory["frp_host"], "/api/statistics/trips", params)

    if not res["ok"]:
        raise HTTPException(502, detail=res["error"])
    return res["data"]


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
  *{box-sizing:border-box}
  body{margin:0;background:radial-gradient(circle at 20% 0%,#101c3d,#0b1326 55%);color:#fff;
    font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;min-height:100vh}
  .wrap{max-width:1100px;margin:0 auto;padding:28px 18px 60px}
  h1{font-size:20px;margin:0 0 4px;font-weight:700}
  .sub{color:#8ea0c2;font-size:12.5px;margin-bottom:24px}
  select,button{background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.18);color:#fff;
    border-radius:9px;padding:7px 14px;font-size:13px;cursor:pointer;transition:background .15s}
  button:hover,select:hover{background:rgba(255,255,255,.14)}

  /* ── Danh sách nhà máy (card grid) ── */
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:14px;margin-top:18px}
  .card{background:rgba(255,255,255,.045);border:1px solid rgba(255,255,255,.08);border-radius:16px;
    padding:18px;cursor:pointer;transition:transform .15s,border-color .15s,background .15s}
  .card:hover{transform:translateY(-3px);border-color:rgba(129,140,248,.5);background:rgba(255,255,255,.07)}
  .card-name{font-size:14.5px;font-weight:700;margin-bottom:14px;display:flex;align-items:center;gap:8px}
  .dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}
  .dot.up{background:#34d399;box-shadow:0 0 8px #34d399}
  .dot.down{background:#fb7185}
  .agv-ring{display:flex;align-items:baseline;gap:6px}
  .agv-big{font-size:34px;font-weight:800;line-height:1}
  .agv-total{font-size:15px;color:#8ea0c2}
  .agv-lbl{font-size:11px;color:#8ea0c2;text-transform:uppercase;letter-spacing:.05em;margin-top:6px}
  .card-err{font-size:11.5px;color:#fb7185;margin-top:10px}
  .card-arrow{float:right;color:#8ea0c2;font-size:18px}

  /* ── Chi tiết 1 nhà máy ── */
  .backbtn{display:inline-flex;align-items:center;gap:4px;margin-bottom:14px}
  .kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin:18px 0}
  .kpi{background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08);border-radius:14px;padding:14px 16px}
  .kpi-lbl{font-size:11px;color:#8ea0c2;text-transform:uppercase;letter-spacing:.04em}
  .kpi-val{font-size:24px;font-weight:800;margin-top:4px}
  .charts{display:grid;grid-template-columns:2fr 1fr;gap:16px;margin-top:8px}
  @media (max-width:720px){.charts{grid-template-columns:1fr}}
  .chartcard{background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.08);
    border-radius:16px;padding:16px}
  .chartcard-title{font-size:12.5px;color:#8ea0c2;margin-bottom:10px;font-weight:600}
  .chartwrap{height:280px;position:relative}
  .err{font-size:12px;color:#fb7185;padding:16px 0}
  .loading{color:#8ea0c2;font-size:13px;padding:20px 0}
</style>
</head><body>
<div class="wrap" id="app">
  <h1>📊 Tổng hợp AGV — Mọi nhà máy</h1>
  <div id="content"></div>
</div>
<script>
let chartDay = null, chartStatus = null;
let factoriesCache = [];

function slugBase() { return location.pathname.replace(/\/+$/, ''); }

// ══ MÀN HÌNH 1: danh sách nhà máy ═══════════════════════════════════════════
async function showList() {
  const c = document.getElementById('content');
  c.innerHTML = `
    <div class="loading">Đang tải danh sách nhà máy…</div>`;
  try {
    const res = await fetch(`${slugBase()}/data`);
    const d = await res.json();
    if (!res.ok || !Array.isArray(d.factories)) {
      throw new Error(d.detail || `Server trả về không đúng định dạng (HTTP ${res.status})`);
    }
    factoriesCache = d.factories;
    renderList(d.factories);
  } catch (e) {
    c.innerHTML = `<div class="err">⚠ Lỗi tải dữ liệu: ${e.message}</div>`;
  }
}

function renderList(factories) {
  const c = document.getElementById('content');
  if (!factories.length) {
    c.innerHTML = '<div class="loading">Chưa có nhà máy nào đăng ký trong factories.json.</div>';
    return;
  }
  c.innerHTML = `
    <div style="margin-bottom:6px"><button onclick="showList()">🔄 Làm mới</button></div>
    <div class="grid">${factories.map(f => {
      if (!f.agvs) {
        return `<div class="card" onclick="showDetail('${f.key}','${escAttr(f.name)}')">
          <div class="card-name"><span class="dot down"></span>${f.name}</div>
          <div class="card-err">⚠ ${f.agvs_error || 'Không kết nối được'}</div>
        </div>`;
      }
      const { online, total } = f.agvs;
      return `<div class="card" onclick="showDetail('${f.key}','${escAttr(f.name)}')">
        <div class="card-name"><span class="dot ${online>0?'up':'down'}"></span>${f.name}<span class="card-arrow">›</span></div>
        <div class="agv-ring"><span class="agv-big">${online}</span><span class="agv-total">/ ${total}</span></div>
        <div class="agv-lbl">AGV đang hoạt động</div>
      </div>`;
    }).join('')}</div>`;
}
function escAttr(s) { return String(s).replace(/'/g, "\\'"); }

// ══ MÀN HÌNH 2: chi tiết chuyến đi 1 nhà máy ═════════════════════════════════
function onPeriodChange(sel, key, name) {
  const period = sel.value;
  if (period === 'custom') {
    // Chưa có ngày cụ thể — chỉ hiện 2 ô chọn ngày, chưa gọi API vội.
    document.getElementById('custom-range').style.display = 'flex';
    return;
  }
  showDetail(key, name, period);
}
function applyCustomRange(key, name) {
  const df = document.getElementById('date-from').value;
  const dt = document.getElementById('date-to').value;
  if (!df || !dt) return;
  showDetail(key, name, 'custom', df, dt);
}

async function showDetail(key, name, period, dateFrom, dateTo) {
  period = period || 'month';
  const c = document.getElementById('content');
  const isCustom = period === 'custom';
  c.innerHTML = `
    <div class="backbtn"><button onclick="showList()">← Danh sách nhà máy</button></div>
    <h2 style="margin:4px 0 2px;font-size:16px">${name}</h2>
    <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
      <select id="period" onchange="onPeriodChange(this,'${key}','${escAttr(name)}')">
        <option value="week"    ${period==='week'   ?'selected':''}>Tuần này</option>
        <option value="month"   ${period==='month'  ?'selected':''}>Tháng này</option>
        <option value="quarter" ${period==='quarter'?'selected':''}>Quý này</option>
        <option value="year"    ${period==='year'   ?'selected':''}>Năm nay</option>
        <option value="custom"  ${isCustom            ?'selected':''}>Ngày cụ thể…</option>
      </select>
      <div id="custom-range" style="display:${isCustom?'flex':'none'};gap:6px;align-items:center">
        <input type="date" id="date-from" value="${dateFrom||''}"
          style="background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.18);color:#fff;border-radius:8px;padding:5px 8px;font-size:13px"/>
        <span style="color:#8ea0c2">→</span>
        <input type="date" id="date-to" value="${dateTo||''}"
          style="background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.18);color:#fff;border-radius:8px;padding:5px 8px;font-size:13px"/>
        <button onclick="applyCustomRange('${key}','${escAttr(name)}')">Áp dụng</button>
      </div>
    </div>
    <div class="loading">${(isCustom && !(dateFrom && dateTo))
      ? 'Chọn khoảng ngày rồi bấm "Áp dụng".' : 'Đang tải chuyến đi…'}</div>`;

  if (isCustom && !(dateFrom && dateTo)) return;   // chờ người dùng chọn ngày rồi bấm Áp dụng

  try {
    let url = `${slugBase()}/trips?key=${encodeURIComponent(key)}&period=${period}`;
    if (isCustom) url += `&date_from=${dateFrom}&date_to=${dateTo}`;
    const res = await fetch(url);
    const d = await res.json();
    if (!res.ok) throw new Error(d.detail || `HTTP ${res.status}`);
    renderDetail(key, name, period, d);
  } catch (e) {
    document.getElementById('content').insertAdjacentHTML('beforeend',
      `<div class="err">⚠ Lỗi tải chuyến đi: ${e.message}</div>`);
  }
}

function fmtDur(sec) {
  if (sec == null) return '—';
  sec = Math.round(sec);
  const h = Math.floor(sec/3600), m = Math.floor((sec%3600)/60);
  if (h > 0) return `${h}h${m}p`;
  return `${m}p`;
}
function fmtDs(s) { const [,m,d] = (s||'').split('-'); return d && m ? `${d}/${m}` : (s||''); }

const STATUS_LABELS = {completed:'Hoàn thành', failed:'Thất bại', cancelled:'Đã hủy', running:'Đang chạy'};
const STATUS_COLORS = {completed:'#34d399', failed:'#fb7185', cancelled:'#94a3b8', running:'#fbbf24'};

function renderDetail(key, name, period, d) {
  const s = d.summary || {};
  const kpiHtml = `
    <div class="kpis">
      <div class="kpi"><div class="kpi-lbl">Tổng chuyến</div><div class="kpi-val">${s.total ?? 0}</div></div>
      <div class="kpi"><div class="kpi-lbl">Hoàn thành</div><div class="kpi-val" style="color:#34d399">${s.completed ?? 0}</div></div>
      <div class="kpi"><div class="kpi-lbl">Thất bại / Hủy</div><div class="kpi-val" style="color:#fb7185">${(s.failed ?? 0) + (s.cancelled ?? 0)}</div></div>
      <div class="kpi"><div class="kpi-lbl">TG hoạt động</div><div class="kpi-val">${fmtDur(d.total_active_time_s)}</div></div>
      <div class="kpi"><div class="kpi-lbl">TG TB / chuyến</div><div class="kpi-val">${fmtDur(d.avg_trip_duration_s)}</div></div>
    </div>
    <div class="charts">
      <div class="chartcard">
        <div class="chartcard-title">Chuyến đi theo ngày</div>
        <div class="chartwrap"><canvas id="chart-day"></canvas></div>
      </div>
      <div class="chartcard">
        <div class="chartcard-title">Trạng thái chuyến</div>
        <div class="chartwrap"><canvas id="chart-status"></canvas></div>
      </div>
    </div>`;
  document.getElementById('content').insertAdjacentHTML('beforeend', kpiHtml);

  const byDay = d.by_day || [];
  // ≤5 ngày trong khoảng lọc → 2 cột riêng (xanh/đỏ) dễ so sánh từng ngày;
  // >5 ngày → giữ cột+đường (đường rõ xu hướng hơn khi nhiều điểm).
  const daySpan = (d.date_from && d.date_to)
    ? Math.round((new Date(d.date_to) - new Date(d.date_from)) / 86400000) + 1
    : byDay.length;
  const failDataset = (daySpan <= 5)
    ? { label:'Thất bại/Hủy', type:'bar', data: byDay.map(r => r.failed),
        backgroundColor:'rgba(251,113,133,.75)', borderColor:'#fb7185', borderWidth:1.5,
        borderRadius:6, borderSkipped:false, order:1 }
    : { label:'Thất bại/Hủy', type:'line', data: byDay.map(r => r.failed),
        borderColor:'#fb7185', borderWidth:2, backgroundColor:'rgba(251,113,133,.1)',
        pointBackgroundColor:'#fb7185', pointBorderColor:'rgba(255,255,255,.9)',
        pointBorderWidth:1.5, pointRadius:4, pointHoverRadius:6, tension:.35, fill:false, order:0 };
  if (chartDay) chartDay.destroy();
  chartDay = new Chart(document.getElementById('chart-day'), {
    type: 'bar',
    data: {
      labels: byDay.map(r => fmtDs(r.day)),
      datasets: [
        { label: 'Hoàn thành', type: 'bar', data: byDay.map(r => r.completed),
          backgroundColor: 'rgba(52,211,153,.75)', borderColor: '#34d399', borderWidth: 1.5,
          borderRadius: 6, borderSkipped: false, order: 1 },
        failDataset,
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { labels: { color:'#fff', boxWidth:10, usePointStyle:true, pointStyle:'circle', font:{size:11} } } },
      scales: {
        x: { ticks:{ color:'rgba(255,255,255,.75)', font:{size:10} }, grid:{ color:'rgba(255,255,255,.05)' } },
        y: { ticks:{ color:'rgba(255,255,255,.75)', font:{size:10} }, grid:{ color:'rgba(255,255,255,.08)' }, beginAtZero:true },
      },
    },
  });

  const byStatus = d.by_status || [];
  if (chartStatus) chartStatus.destroy();
  chartStatus = new Chart(document.getElementById('chart-status'), {
    type: 'doughnut',
    data: {
      labels: byStatus.map(r => STATUS_LABELS[r.status] || r.status),
      datasets: [{ data: byStatus.map(r => r.count),
        backgroundColor: byStatus.map(r => STATUS_COLORS[r.status] || '#64748b'),
        borderColor: 'rgba(11,19,38,.9)', borderWidth: 3,
        hoverBorderColor: '#fff', hoverBorderWidth: 2, hoverOffset: 8 }],
    },
    options: {
      responsive: true, maintainAspectRatio: false, cutout: '62%',
      plugins: { legend: { position:'bottom', labels:{ color:'#fff', boxWidth:10, usePointStyle:true, pointStyle:'circle', font:{size:11} } } },
    },
  });
}

showList();
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
