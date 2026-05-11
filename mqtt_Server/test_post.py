import json
import urllib.request

payload = {
    "agv_id": "AGV01",
    "destination": "19",
    "map_id": "map_demo"
}
req = urllib.request.Request('http://127.0.0.1:8000/order', data=json.dumps(payload).encode('utf-8'), headers={'Content-Type':'application/json'})
try:
    with urllib.request.urlopen(req, timeout=5) as resp:
        print('RESP', resp.read().decode())
except Exception as e:
    print('ERR', e)
