"""
config_mgmt/settings_io.py  — 7. Config Management
-----------------------------------------------------
Load/save cài đặt hệ thống. Migrate từ main.py (lines 169–214, 314–343, 4852–4854).
"""
from __future__ import annotations
import json
import os

CONFIG_PATH = 'config/settings.json'

DEFAULT_CONFIG = {
    "mqtt": {"broker": "localhost", "port": 1883, "username": "", "password": ""},
    "factory":  "NhaMayA",
    "hardware": "hardware",
    "version":  "1.0",
    "users": [],
    "map_file": "config/map_data.json",
    "wifi": {"ssid": "Factory_WiFi", "password": "password123"},
    "work_hours": 12,
    "dispatch_weights": {"distance": 80, "idle": 20, "battery": 0},
    "schedule_tasks": [],
    "language": "vi",
    "traffic": {"safety_dist": 2.0, "deadlock_timeout": 10,
                "speed_fast": 120, "speed_slow": 60, "lookahead": 3},
    "map": {"meters_per_unit": 0.01},
    "door_sensors": [],
    "elevators": [],
    "custom_actions": [
        {"id": 20, "name": "Lift Up"},
        {"id": 21, "name": "Lift Down"},
        {"id": 22, "name": "Horn Beep"},
    ],
    "alarms": {"stuck_timeout": 30},
    "integration": {"api_enabled": True, "api_port": 8000},
    "lookahead": 5,
    "homing_beacon_path": [],
    "chargers": [],
    "home_node_id": 10,
    "station_config": [
        {"id": 1, "name": "Team 1", "wait": 101, "delivery": 102},
        {"id": 2, "name": "Team 2", "wait": 101, "delivery": 104},
        {"id": 4, "name": "Team 4", "wait": 104, "delivery": 105},
    ],
    "station_map": {},
    "chart_colors": {
        "pickup": "#3498db", "delivery": "#2ecc71",
        "return": "#f1c40f", "idle": "#95a5a6", "trip_bar": "#9b59b6",
    },
    "agvs": [
        {"id": "AGV01", "ip": "192.168.1.10", "color": "#3498db"}
    ],
}


def load_config(path: str = CONFIG_PATH) -> dict:
    """Tải settings.json. Tạo file mặc định nếu chưa tồn tại."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print("Config file not found! Creating default config...")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(DEFAULT_CONFIG, f, indent=4, ensure_ascii=False)
        return dict(DEFAULT_CONFIG)


def save_config(config: dict, path: str = CONFIG_PATH):
    """Lưu config ra file JSON."""
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4, ensure_ascii=False)


def rebuild_door_maps(config: dict) -> dict[int, list[dict]]:
    """
    Build index {tag_id: [door_cfg, ...]} từ config['door_sensors'].
    Gọi lại mỗi khi door config thay đổi.
    """
    door_sensors = config.get('door_sensors', [])
    door_map: dict[int, list[dict]] = {}
    for d in door_sensors:
        tid = d.get('tag_id')
        if tid is not None:
            door_map.setdefault(int(tid), []).append(d)
    print(f"[DOOR] Door map rebuilt: {len(door_sensors)} entry(s) across {len(door_map)} tag(s)")
    return door_map


def find_door_cfg(config: dict, tag_id: int, prev_tag: int) -> dict | None:
    """
    Tìm door_cfg phù hợp với transition prev_tag → tag_id.
    entry_from=None → khớp mọi chiều.
    """
    for d in config.get('door_sensors', []):
        if d.get('tag_id') != tag_id:
            continue
        ef = d.get('entry_from')
        if ef is None or int(ef) == prev_tag:
            return d
    return None
