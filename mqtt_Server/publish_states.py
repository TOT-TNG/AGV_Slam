import paho.mqtt.client as mqtt
import json
import time

BROKER = "192.168.1.15"
PORT = 1883

client = mqtt.Client()
client.connect(BROKER, PORT, 60)
client.loop_start()

def pub(agv, x, y, node):
    payload = {
        "headerId": int(time.time() * 1000),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "version": "3.0.0",
        "manufacturer": "tot",
        "serialNumber": agv,
        "mapCurrent": "map_demo",
        "orderId": "",
        "orderUpdateId": 0,
        "lastNodeId": node,
        "nodeStates": [{"nodeId": node, "sequenceId": 0, "released": True}],
        "edgeStates": [],
        "agvPosition": {"x": x, "y": y, "theta": 0, "mapId": "map_demo"},
        "velocity": {"vx": 0, "vy": 0, "omega": 0},
        "paused": False,
    }
    topics = [f"vda5050/agv/{agv}/state", f"uagv/v3/tot/{agv}/state"]
    for topic in topics:
        client.publish(topic, json.dumps(payload), qos=1).wait_for_publish()

if __name__ == '__main__':
    pub('AGV01', 24.09, 12.12, 'N19')
    pub('AGV02', 10.0, 2.0, 'N2')
    pub('AGV03', 17.919, 6.031, 'N4')
    time.sleep(0.5)
    client.loop_stop()
    client.disconnect()
    print('published')
