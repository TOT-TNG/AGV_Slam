from typing import Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
import json

router = APIRouter(prefix="/api/map/node", tags=["Map Node Config"])

class MapNodeConfigRequest(BaseModel):
    mapId: str
    nodeId: str
    config: dict

class MapNodeClearRequest(BaseModel):
    mapId: str
    nodeId: str

@router.post("/config")
async def save_node_config(payload: MapNodeConfigRequest, request: Request):
    pool = request.app.state.db_pool
    map_id = (payload.mapId or "").strip()
    node_id = str(payload.nodeId or "").strip()

    if not map_id:
        raise HTTPException(status_code=400, detail="mapId là bắt buộc")
    if not node_id:
        raise HTTPException(status_code=400, detail="nodeId là bắt buộc")

    config = payload.config or {}
    name = (config.get("name") or "").strip()
    location_type = (config.get("locationType") or "").strip().upper()
    default_action = (config.get("defaultAction") or "").strip().upper()

    action_json = {
        "locationType": location_type,
        "defaultAction": default_action
    }

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
        """
        UPDATE public.agv_map_points
        SET
            name = $1,
            action = $2::jsonb
        WHERE map_id = $3
        AND name_id = $4
        RETURNING id, map_id, name_id, name, action, x, y
        """,
        name if name else None,
        json.dumps(action_json),
        map_id,
        node_id,
    )

        if not row:
            raise HTTPException(status_code=404, detail="Không tìm thấy node")

        return {
            "success": True,
            "message": "Đã lưu cấu hình node thành công",
            "data": {
                "id": row["id"],
                "mapId": row["map_id"],
                "nodeId": row["name_id"],
                "name": row["name"],
                "action": row["action"],
                "x": row["x"],
                "y": row["y"],
            },
        }

@router.delete("/config")
async def clear_node_config(payload: MapNodeClearRequest, request: Request):
    pool = request.app.state.db_pool
    map_id = (payload.mapId or "").strip()
    node_id = str(payload.nodeId or "").strip()

    if not map_id:
        raise HTTPException(status_code=400, detail="mapId là bắt buộc")
    if not node_id:
        raise HTTPException(status_code=400, detail="nodeId là bắt buộc")

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE public.agv_map_points
            SET name = NULL, action = NULL
            WHERE map_id = $1 AND name_id = $2
            RETURNING id, map_id, name_id
            """,
            map_id,
            node_id,
        )

        if not row:
            raise HTTPException(status_code=404, detail="Không tìm thấy node")

        return {
            "success": True,
            "message": "Đã xóa cấu hình node thành công",
            "data": {
                "id": row["id"],
                "mapId": row["map_id"],
                "nodeId": row["name_id"],
            },
        }