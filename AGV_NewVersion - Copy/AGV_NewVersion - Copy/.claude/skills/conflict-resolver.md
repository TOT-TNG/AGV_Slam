---
name: conflict-resolver
description: Xử lý xung đột giao thông giữa các AGV — reservation, deadlock detection, re-routing. Dùng khi debug tắc đường, thêm logic tránh va chạm, hoặc mở rộng sang nhiều xe hơn.
---

# Skill: Conflict Resolver

## Khi nào dùng
- Debug tình huống 2 xe chặn nhau (deadlock)
- Thêm logic reservation cho node/edge mới
- Implement dynamic re-routing khi có xung đột
- Mở rộng từ 2 xe lên N xe

## Reservation System chuẩn

```python
# python-manager/traffic/traffic_manager.py

class TrafficManager:
    def __init__(self, G: nx.DiGraph):
        self.G = G
        self._reservations: dict[int, str] = {}   # node_id → agv_id
        self._lock = threading.Lock()

    def reserve(self, node: int, agv_id: str) -> bool:
        """Trả về True nếu đặt chỗ thành công."""
        with self._lock:
            current = self._reservations.get(node)
            if current is None or current == agv_id:
                self._reservations[node] = agv_id
                return True
            return False  # Node bị xe khác chiếm

    def release(self, node: int, agv_id: str):
        with self._lock:
            if self._reservations.get(node) == agv_id:
                del self._reservations[node]

    def release_all(self, agv_id: str):
        """Gọi khi AGV disconnect/error."""
        with self._lock:
            to_remove = [n for n, a in self._reservations.items() if a == agv_id]
            for n in to_remove:
                del self._reservations[n]

    def release_passed_nodes(self, agv_id: str, up_to: int):
        """Giải phóng các node đã đi qua (lấy từ path history)."""
        with self._lock:
            to_remove = []
            for n, a in self._reservations.items():
                if a == agv_id and n != up_to:
                    to_remove.append(n)
            for n in to_remove:
                del self._reservations[n]
```

## Deadlock Detection

```python
def detect_deadlock(self, agv_list: list) -> list[tuple]:
    """
    Phát hiện deadlock: AGV A chờ node X (do AGV B), AGV B chờ node Y (do AGV A).
    Trả về list các cặp AGV bị deadlock.
    """
    deadlocks = []
    waiting = {}  # agv_id → node_id đang chờ
    holding = {}  # agv_id → set(node_id) đang giữ

    for agv in agv_list:
        if agv.blocked_on_node:
            waiting[agv.agv_id] = agv.blocked_on_node
        holding[agv.agv_id] = agv.reserved_nodes

    # Tìm cycle trong wait-for graph
    for agv_a, node_a in waiting.items():
        holder_of_a = self._reservations.get(node_a)
        if holder_of_a and holder_of_a in waiting:
            node_b = waiting[holder_of_a]
            if self._reservations.get(node_b) == agv_a:
                deadlocks.append((agv_a, holder_of_a))
    return deadlocks

def resolve_deadlock(self, agv_a: str, agv_b: str, agv_list: list):
    """Giải quyết deadlock: xe ưu tiên thấp hơn lui về node trước."""
    agv_a_obj = next(a for a in agv_list if a.agv_id == agv_a)
    agv_b_obj = next(a for a in agv_list if a.agv_id == agv_b)
    # Xe có priority thấp hơn (hoặc ID lớn hơn) nhường đường
    loser = agv_a_obj if agv_a_obj.priority <= agv_b_obj.priority else agv_b_obj
    loser.reverse_to_previous_node()   # Lui về 1 node
```

## Re-routing động

```python
def find_alternative_path(self, G, agv_id: str, from_node: int, to_node: int,
                           blocked_nodes: set) -> list | None:
    """Tìm đường thay thế tránh các node đang bị chiếm."""
    # Tạo subgraph loại trừ blocked nodes (trừ điểm đích)
    available = [n for n in G.nodes() if n not in blocked_nodes or n == to_node]
    sub = G.subgraph(available)
    try:
        return nx.shortest_path(sub, from_node, to_node, weight='weight')
    except nx.NetworkXNoPath:
        return None  # Không có đường thay thế → giữ WAIT_SYS
```

## Checklist khi implement conflict resolution
- [ ] `release_all()` gọi trong MQTT disconnect handler
- [ ] Reservation dùng threading.Lock() — Python Manager là multi-thread
- [ ] Timeout 30s: nếu AGV không di chuyển sau 30s → coi là stuck → release + alert
- [ ] Re-routing không gửi plan mới khi pending_ack_id chưa xong
- [ ] Log mọi deadlock detection: timestamp, agv_ids, nodes liên quan
- [ ] Test với 2 xe đi ngược chiều trên cùng 1 đoạn đường (case phổ biến nhất)
