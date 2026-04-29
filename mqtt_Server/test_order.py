# test_move.py
import requests
import json

# ĐÚNG: IP server + port 8000
url = "http://192.168.0.27:8000/order"

payload = {
    #"agv_id": "QR-SLAM-AGV-001",
    "agv_id": "qr-slam-agv-001",
    "destination": "1"
}

print("Đang gửi lệnh di chuyển đến http://192.168.0.27:8000/order ...")
try:
    response = requests.post(url, json=payload, timeout=10)
    print(f"Status code: {response.status_code}")

    # In raw text để xem thực sự server trả về cái gì
    print("Raw response text:")
    print(response.text)

    # Thử parse JSON nếu có
    try:
        data = response.json()
        print("JSON parsed:")
        print(json.dumps(data, indent=2, ensure_ascii=False))
    except json.JSONDecodeError as e:
        print("Không parse được JSON, response không phải JSON hoặc bị lỗi.")
        print(f"Chi tiết lỗi JSONDecodeError: {e}")

except requests.exceptions.ConnectionError:
    print("LỖI: Không kết nối được tới server!")
    print("→ Kiểm tra: server có đang chạy không? Có cùng mạng WiFi không?")
except requests.exceptions.Timeout:
    print("LỖI: Timeout – server không phản hồi")
except Exception as e:
    print(f"LỖI khác: {e}")
