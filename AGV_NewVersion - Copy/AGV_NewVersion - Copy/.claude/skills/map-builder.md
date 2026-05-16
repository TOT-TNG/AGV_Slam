---
name: map-builder
description: Tạo, chỉnh sửa, và validate bản đồ AGV (NetworkX DiGraph + JSON). Dùng khi thêm node/edge mới, thay đổi layout nhà máy, hoặc gán actions cho node/edge.
---

# Skill: Map Builder

## Khi nào dùng
- Thêm node/edge mới vào bản đồ
- Gán role cho node (station, charger, intersection)
- Gán actions cho node hoặc edge
- Validate bản đồ trước khi chạy thực tế
- Export/import map.json

## Cấu trúc bản đồ chuẩn

```python
import networkx as nx
import json

def create_empty_map() -> nx.DiGraph:
    G = nx.DiGraph()
    return G

def add_node(G, node_id: int, x: float, y: float,
             node_type: str = "normal", actions: list = None):
    """
    node_type: "normal" | "intersection" | "station" | "charger"
    actions: [{"a": 3, "v": 0}, ...]  # action codes thực hiện tại node
    """
    G.add_node(node_id, x=x, y=y, type=node_type, actions=actions or [])

def add_edge(G, u: int, v: int, weight: float = 1.0,
             direction: str = "fwd", actions: list = None, end_actions: list = None):
    """
    direction: "fwd" | "bwd" | "both"
    actions: lệnh khi BẮT ĐẦU vào cạnh (VD: giảm tốc)
    end_actions: lệnh khi KẾT THÚC cạnh (VD: phát nhạc)
    """
    G.add_edge(u, v, weight=weight, direction=direction,
               actions=actions or [], end_actions=end_actions or [])
    if direction == "both":
        G.add_edge(v, u, weight=weight, direction=direction,
                   actions=actions or [], end_actions=end_actions or [])
```

## Export/Import map.json

```python
def export_map(G: nx.DiGraph, filepath: str):
    data = {
        "nodes": [
            {"id": n, **G.nodes[n]}
            for n in G.nodes()
        ],
        "edges": [
            {"u": u, "v": v, **G.edges[u, v]}
            for u, v in G.edges()
        ]
    }
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def import_map(filepath: str) -> nx.DiGraph:
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    G = nx.DiGraph()
    for node in data["nodes"]:
        nid = node.pop("id")
        G.add_node(nid, **node)
    for edge in data["edges"]:
        u, v = edge.pop("u"), edge.pop("v")
        G.add_edge(u, v, **edge)
    return G
```

## Validation bản đồ

```python
def validate_map(G: nx.DiGraph) -> list[str]:
    errors = []
    # 1. Kiểm tra connectivity
    if not nx.is_weakly_connected(G):
        errors.append("WARN: Bản đồ không liên thông — có node bị cô lập")
    # 2. Kiểm tra node type hợp lệ
    valid_types = {"normal", "intersection", "station", "charger"}
    for n in G.nodes():
        t = G.nodes[n].get("type", "")
        if t not in valid_types:
            errors.append(f"ERROR: Node {n} có type không hợp lệ: '{t}'")
    # 3. Kiểm tra edge tham chiếu node tồn tại
    for u, v in G.edges():
        if u not in G.nodes() or v not in G.nodes():
            errors.append(f"ERROR: Edge ({u},{v}) tham chiếu node không tồn tại")
    # 4. Kiểm tra có ít nhất 1 charger
    chargers = [n for n in G.nodes() if G.nodes[n].get("type") == "charger"]
    if not chargers:
        errors.append("WARN: Không có node charger — AGV không thể tự sạc")
    return errors
```

## Checklist khi build map
- [ ] Mọi intersection node phải có ít nhất 3 edges
- [ ] Cạnh 2 chiều dùng `direction="both"` — tránh duplicate thủ công
- [ ] Node ID = RFID tag ID thực tế trên xe (quan trọng!)
- [ ] Station node gán đúng role trước khi test dispatch
- [ ] Chạy `validate_map()` sau mỗi lần chỉnh sửa
- [ ] Backup map.json trước khi thay đổi lớn
