# agv_simulator.py - AGV GIẢ LẬP TỰ ĐỘNG ĐI + GỬI STATE
import paho.mqtt.client as mqtt
import json
import time
import random

BROKER = "192.168.88.253"
PORT = 1883
AGV_ID = "QR-SLAM-AGV-001"

# Danh sách node để giả lập di chuyển
PATH = ["StartPoint", "NodeA", "NodeB", "Dock01", "NodeC", "StartPoint"]

client = mqtt.Client(f"simulator_{AGV_ID}")
client.connect(BROKER, PORT, 60)
client.loop_start()

def send_state(last_node, battery=95.0, order_id="", paused=False):
    state = {
        "headerId": int(time.time()),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "version": "1.1",
        "manufacturer": "TNG:TOT",
        "serialNumber": AGV_ID,
        "lastNodeId": last_node,
        "orderId": order_id,
        "orderUpdateId": 0,
        "agvPosition": {"x": 0, "y": 0, "theta": 0, "mapId": "map1"},
        "velocity": {"vx": 0.3, "vy": 0, "omega": 0},
        "batteryState": {"batteryCharge": battery},
        "paused": paused,
        "operationMode": "AUTOMATIC",
        "error": [],
        "nodeStates": [] if not order_id else [
            {"nodeId": last_node, "nodeStatus": "FINISHED"}
        ]
    }
    topic = f"vda5050/agv/{AGV_ID}/state"
    client.publish(topic, json.dumps(state))
    print(f"[SIMULATOR] Đã đến: {last_node} | Gửi state → dashboard")

print(f"[SIMULATOR] AGV {AGV_ID} bắt đầu chạy vòng...")
time.sleep(2)

# Đăng ký ban đầu
send_state("StartPoint", battery=95.0)

# Bắt đầu vòng lặp di chuyển
current_idx = 0
while True:
    current_node = PATH[current_idx]
    
    # Giả lập đang đến node hiện tại
    send_state(current_node, battery=round(95 - current_idx*2, 1), order_id="c487449c")
    time.sleep(4)  # thời gian di chuyển 1 node
    
    current_idx = (current_idx + 1) % len(PATH)