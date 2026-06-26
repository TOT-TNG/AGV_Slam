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
from fastapi.responses import Response, JSONResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [GATEWAY] %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(title="AGV Cloud Gateway", version="1.0.0")

CONFIG_FILE  = Path(__file__).parent / "factories.json"
FRP_HTTP_PORT = 8090   # phải khớp vhostHTTPPort trong frps.toml
SUBDOMAIN_HOST = "tot360.internal"  # phải khớp subdomainHost trong frps.toml


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
