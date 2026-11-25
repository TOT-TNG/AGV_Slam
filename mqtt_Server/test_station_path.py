"""Test: chọn trạm sạc ưu tiên trạm có ĐƯỜNG TỚI không bị xe khác đang đứng chặn (sự cố 25/11: AGV01 chọn trạm 1 qua node 2 nơi AGV03 đỗ).
Chạy: PYTHONIOENCODING=utf-8 python test_station_path.py"""
import time

import networkx as nx

import mqtt_client as mc
from line_agv_handler import line_agv_handler as H, LineAGVRoute

_pass = _fail = 0


def check(cond, msg):
    global _pass, _fail
    if cond:
        _pass += 1
        print("  PASS:", msg)
    else:
        _fail += 1
        print("  FAIL:", msg)


# Bản đồ thu nhỏ: 4 - 3 - 2 - 1(trạm)   và   3 - 27(trạm)
g = nx.Graph()
for a, b in (("4", "3"), ("3", "2"), ("2", "1"), ("3", "27")):
    g.add_edge(a, b, weight=1.0)
mc.map_manager.line_graph = g
stations = [{"node_id": "1", "name": "S1"}, {"node_id": "27", "name": "S27"}]


def setup(me_tag, others):
    H.state_store._states.clear() if hasattr(H.state_store._states, "clear") else None
    st = H.state_store.get_or_create("AGV01")
    st.current_tag = me_tag
    st.connection_state = "ONLINE"
    st.last_update = time.time()
    H._routes.pop("AGV01", None)
    for aid, tag in others.items():
        o = H.state_store.get_or_create(aid)
        o.current_tag = tag
        o.connection_state = "ONLINE"
        o.last_update = time.time()
        H._routes.pop(aid, None)


print("[test] AGV03 đỗ ở node 2 (trên đường tới trạm 1) → chọn trạm 27")
setup(4, {"AGV03": 2})
node, occ = mc._pick_least_claimed_station(stations, "AGV01", "m")
check(node["node_id"] == "27" and occ is False, f"chọn trạm {node['node_id']} (all_occupied={occ})")

print("[test] không xe nào chắn → giữ hành vi cũ (hoà claim → trạm đầu danh sách)")
setup(4, {"AGV03": 23 if False else 9})
node, occ = mc._pick_least_claimed_station(stations, "AGV01", "m")
check(node["node_id"] == "1" and occ is False, f"chọn trạm {node['node_id']}")

print("[test] xe khác chắn CẢ HAI đường → vẫn chọn được 1 trạm (không lỗi), không đánh dấu all_occupied sai")
setup(4, {"AGV03": 2, "AGV04": 3})
node, occ = mc._pick_least_claimed_station(stations, "AGV01", "m")
check(node["node_id"] in ("1", "27") and occ is False, f"chọn trạm {node['node_id']}, all_occupied={occ}")

print("[test] trạm bị xe khác ĐANG ĐỨNG tại đó vẫn bị tính claim (không bị phạt đường che mất)")
setup(4, {"AGV03": 27})
node, occ = mc._pick_least_claimed_station(stations, "AGV01", "m")
check(node["node_id"] == "1", f"trạm 27 có xe → chọn trạm {node['node_id']}")

print("[test] không biết vị trí xe → không lỗi, rơi về hành vi cũ")
setup(None, {"AGV03": 2})
node, occ = mc._pick_least_claimed_station(stations, "AGV01", "m")
check(node["node_id"] in ("1", "27"), f"chọn trạm {node['node_id']}")

print()
print(f"KẾT QUẢ: {_pass} pass, {_fail} fail")
raise SystemExit(1 if _fail else 0)
