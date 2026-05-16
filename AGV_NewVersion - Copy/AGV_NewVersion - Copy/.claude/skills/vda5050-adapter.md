---
name: vda5050-adapter
description: Đảm bảo hệ thống tuân thủ chuẩn VDA5050 v2.0.0. Dùng khi tích hợp FMS mới, thêm loại AGV (QR/SLAM), hoặc kiểm tra compliance trước khi kết nối với hệ thống ngoài.
---

# Skill: VDA5050 Adapter

## Khi nào dùng
- Kết nối với FMS (Fleet Management System) của bên thứ 3
- Thêm AGV loại mới (QR Code, SLAM) vào hệ thống
- Validate message format trước khi deploy
- Implement VDA5050 interface đầy đủ

## MQTT Topic Structure (VDA5050 v2.0.0)

```
uagv/v2/{manufacturer}/{serialNumber}/order          # FMS → AGV
uagv/v2/{manufacturer}/{serialNumber}/instantActions # FMS → AGV (tức thời)
uagv/v2/{manufacturer}/{serialNumber}/state          # AGV → FMS
uagv/v2/{manufacturer}/{serialNumber}/visualization  # AGV → FMS (real-time pos)
uagv/v2/{manufacturer}/{serialNumber}/connection     # AGV → FMS (Last Will)
uagv/v2/{manufacturer}/{serialNumber}/factsheet      # AGV → FMS (retain=true)
```

## Message Schemas

```python
# Header chuẩn (phải có trong mọi message)
def build_header(seq_id: int) -> dict:
    return {
        "headerId": seq_id,
        "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "version": "2.0.0",
        "manufacturer": FACTORY,
        "serialNumber": AGV_ID
    }

# Order message (FMS → AGV)
def build_order(order_id: str, order_update_id: int, nodes: list, edges: list) -> dict:
    return {
        **build_header(next_seq()),
        "orderId": order_id,
        "orderUpdateId": order_update_id,
        "nodes": [
            {
                "nodeId": str(n["id"]),
                "sequenceId": i * 2,          # Chẵn cho node
                "released": True,
                "nodePosition": {"x": n["x"], "y": n["y"], "mapId": "floor1"},
                "actions": n.get("actions", [])
            }
            for i, n in enumerate(nodes)
        ],
        "edges": [
            {
                "edgeId": f"{e['u']}_{e['v']}",
                "sequenceId": i * 2 + 1,      # Lẻ cho edge
                "startNodeId": str(e["u"]),
                "endNodeId": str(e["v"]),
                "released": True,
                "actions": e.get("actions", [])
            }
            for i, e in enumerate(edges)
        ]
    }

# State message (AGV → FMS)
def build_state(agv) -> dict:
    return {
        **build_header(next_seq()),
        "orderId": agv.current_order_id or "",
        "orderUpdateId": agv.current_order_update_id or 0,
        "lastNodeId": str(agv.current_tag),
        "lastNodeSequenceId": agv.last_seq_id,
        "driving": agv.is_driving,
        "operatingMode": "AUTOMATIC",          # AUTOMATIC|MANUAL|SEMIAUTOMATIC
        "nodeStates": agv.node_states,
        "edgeStates": agv.edge_states,
        "batteryState": {
            "batteryCharge": agv.battery_percent,
            "charging": agv.is_charging
        },
        "errors": agv.active_errors,
        "informations": [],
        "safetyState": {
            "eStop": "NONE",                    # NONE|MANUAL|REMOTE|AUTOACK
            "fieldViolation": agv.lidar_triggered
        }
    }
```

## Adapter cho Line-following AGV (hiện tại)

```python
class LineFolowingVDA5050Adapter:
    """Chuyển đổi giữa internal format và VDA5050."""

    def order_to_internal_plan(self, vda_order: dict) -> dict:
        """VDA5050 order → internal {"c":"plan","d":[...]} cho Arduino."""
        nodes = vda_order.get("nodes", [])
        plan_d = []
        for node in nodes:
            node_id = int(node["nodeId"])
            for action in node.get("actions", []):
                action_type = action.get("actionType", "")
                plan_d.append({
                    "t": node_id,
                    "a": ACTION_TYPE_MAP.get(action_type, 3),
                    "v": int(action.get("actionParameters", [{}])[0].get("value", 0))
                })
        return {"c": "plan", "id": vda_order["orderId"][:8], "d": plan_d}

    def internal_state_to_vda(self, raw_state: dict) -> dict:
        """Arduino state JSON → VDA5050 state message."""
        return build_state_from_raw(raw_state)

# Map giữa VDA5050 actionType và internal action code
ACTION_TYPE_MAP = {
    "startPause": 1,        # WAIT_SYS
    "stopPause": 3,         # RUN
    "startCharging": 11,    # CHARGE
    "cancelOrder": 1,       # WAIT_SYS (dừng chờ)
    "turn_right": 5,        # TURN_R
    "turn_left": 6,         # TURN_L
    "set_speed": 4,         # SPEED
}
```

## Checklist VDA5050 Compliance
- [ ] headerId tăng đơn điệu (monotonic) trong session
- [ ] timestamp theo ISO 8601 UTC: `2026-01-01T10:00:00.000Z`
- [ ] sequenceId: node=chẵn (0,2,4...), edge=lẻ (1,3,5...)
- [ ] connection Last Will: `connectionState: "CONNECTIONBROKEN"`
- [ ] factsheet publish với `retain=true` khi kết nối MQTT
- [ ] state publish ít nhất mỗi 1 giây khi đang chạy
- [ ] orderId giữ nguyên trong suốt 1 nhiệm vụ
- [ ] orderUpdateId tăng khi cùng orderId có update mới
