from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from fastapi import UploadFile


class MoveCommand(BaseModel):
    agv_id: str
    destination: str
    map_id: Optional[str] = None
    path: Optional[List[str]] = None

class ActionRequest(BaseModel):
    agv_id: str
    manufacturer: str
    serial_number: str
    action_type: str #Pause hoặc Resume 

# ----------------- NODE & EDGE SCHEMA -----------------
class MapNode(BaseModel):
    id: str
    name_id: str
    name: str
    x: float
    y: float
    theta: float
    type: str
    available: bool = True

class MapEdge(BaseModel):
    id: str
    name: str
    id_source: str
    id_dest: str
    speed: float
    move_direction: str
    distance: float
    control_points: Optional[List[Dict[str, float]]] = None  # cho curve

# ----------------- MAIN UPLOAD SCHEMA (JSON ONLY) -----------------
class MapUploadFullJson(BaseModel):
    map_id: str
    map_name: str
    layer: str
    origin_x: float = 0.0
    origin_y: float = 0.0
    origin_theta: float = 0.0
    resolution: float = 0.05
    modify_time: str                     # ISO: 2025-11-17T16:38:00+07:00
    image_base64: str                     # BẮT BUỘC, gửi ảnh dưới dạng base64 string (không có data:image/png;base64,)
    
    nodes: List[MapNode] = []             # Danh sách object luôn, không cần string nữa
    edge_straight: List[MapEdge] = []
    edge_curve: List[MapEdge] = []
