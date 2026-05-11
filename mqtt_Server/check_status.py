import urllib.request, json

def get(path):
    with urllib.request.urlopen(f'http://127.0.0.1:8001{path}') as r:
        print(path, json.loads(r.read().decode()))

get('/debug/agvs')
get('/agv/AGV01')
get('/agv/AGV03')
get('/agv/AGV02')
