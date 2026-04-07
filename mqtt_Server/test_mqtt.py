# test_mqtt.py
from mqtt_client import send_instant_action, start_mqtt
import time

if __name__ == "__main__":
    # === Khởi động MQTT trước khi gửi ===
    start_mqtt()
    time.sleep(1)  # chờ client kết nối xong

    # === Thông tin test ===
    agv_id = "qr-slam-agv-001"   # serialNumber hoặc ID AGV
    action_type = "PAUSE"        # hoặc "RESUME"
    #action_type = "RESUME"

    send_instant_action(agv_id, action_type)

    # chờ thêm để gói tin gửi xong
    time.sleep(2)
