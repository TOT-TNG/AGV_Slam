---
name: fleet-dispatch
description: Xây dựng hoặc debug logic điều phối đội xe AGV — task allocation, mission planning, windowed path sending. Dùng khi cần gửi plan cho xe, phân công nhiệm vụ, hoặc xử lý sự kiện từ xe.
---

# Skill: Fleet Dispatch

## Khi nào dùng
- Thêm logic phân công nhiệm vụ (xe nào đi trạm nào)
- Gửi plan (mission) xuống AGV
- Xử lý sự kiện xe báo về (tag mới, hoàn thành, lỗi)
- Implement windowed navigation (lookahead)

## Pattern chuẩn — gửi plan cho AGV

```python
# python-manager/agv_instance.py
LOOKAHEAD = 5

def send_next_window(self):
    """Gửi lookahead nodes tiếp theo cho AGV."""
    if self.path_remaining:
        window = self.path_remaining[:LOOKAHEAD]
        plan_nodes = self._build_plan_nodes(window)
        payload = {
            "c": "plan",
            "id": self._gen_id(),
            "d": plan_nodes
        }
        self.mqtt_client.publish(
            f"uagv/v2/{FACTORY}/{self.agv_id}/order",
            json.dumps(payload),
            qos=1
        )
        self.pending_ack_id = payload["id"]
        self.last_sent_window = window

def on_state_received(self, state: dict):
    """Xử lý state từ AGV."""
    tag = state.get("tag")
    ack = state.get("ack")

    # Xác nhận plan đã nhận
    if ack and ack == self.pending_ack_id:
        self.pending_ack_id = None

    # Tiến tới node tiếp theo
    if tag and tag != self.current_tag:
        self.current_tag = tag
        self.traffic_manager.release_passed_nodes(self.agv_id, up_to=tag)
        # Pop nodes đã qua khỏi path_remaining
        self.path_remaining = [n for n in self.path_remaining if n != tag]
        # Gửi window mới
        self.send_next_window()
```

## Pattern chuẩn — task allocation

```python
# python-manager/task_allocator.py
def assign_nearest_idle_agv(station_node: int, agv_list: list) -> str | None:
    """Tìm xe rảnh gần nhất với station_node."""
    best_agv = None
    best_cost = float('inf')
    for agv in agv_list:
        if agv.status != "idle":
            continue
        path = traffic_manager.find_path(agv.current_tag, station_node)
        if path and len(path) < best_cost:
            best_cost = len(path)
            best_agv = agv
    return best_agv

def dispatch(agv, from_node: int, to_node: int):
    path = traffic_manager.find_path(from_node, to_node)
    if not path:
        log.warning(f"No path from {from_node} to {to_node}")
        return False
    agv.set_path(path)
    agv.send_next_window()
    return True
```

## Checklist khi implement
- [ ] Plan ID là UUID ngắn (8 ký tự) để Arduino ACK lại
- [ ] Không gửi plan mới khi pending_ack_id chưa được clear
- [ ] Khi AGV báo lỗi: gửi `{"c":"stop"}` trước, rồi xử lý
- [ ] Release reservation khi xe disconnect hoặc timeout
