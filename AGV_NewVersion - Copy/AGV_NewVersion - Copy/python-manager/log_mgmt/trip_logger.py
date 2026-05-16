"""
log_mgmt/trip_logger.py  — 6. Log Management
----------------------------------------------
Migrate từ agv_instance.py:
  - AGV.ensure_log_header()
  - AGV.log_trip_finish()
"""
from __future__ import annotations
import csv
import os
import time
import datetime

LOG_DIR = os.path.join(os.path.dirname(__file__), '..', 'logs')
LOG_HEADER = "timestamp,date,agv_id,task_type,duration,target_node\n"


def ensure_log_header(agv_id: str, filepath: str | None = None) -> str:
    """
    Tạo file log CSV với header nếu chưa tồn tại.
    Trả về đường dẫn file log.
    """
    if filepath is None:
        filepath = os.path.join(LOG_DIR, f"{agv_id}_trips.csv")
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    if not os.path.exists(filepath):
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(LOG_HEADER)
    return filepath


def log_trip_finish(agv_id: str, task_type: str, duration: int,
                    target_node: int, filepath: str | None = None):
    """
    Ghi 1 dòng log khi chuyến đi kết thúc.
    Migrate từ AGV.log_trip_finish() trong agv_instance.py.
    """
    if filepath is None:
        filepath = os.path.join(LOG_DIR, f"{agv_id}_trips.csv")
    ensure_log_header(agv_id, filepath)
    now = datetime.datetime.now()
    with open(filepath, 'a', encoding='utf-8') as f:
        f.write(f"{int(time.time())},"
                f"{now.strftime('%Y-%m-%d')},"
                f"{agv_id},{task_type},{duration},{target_node}\n")


def query_trips(agv_id: str, date: str | None = None,
                task_type: str | None = None) -> list[dict]:
    """
    Truy vấn log chuyến đi theo agv_id, ngày, loại nhiệm vụ.
    Trả về list[dict] (các dòng CSV đã parse).
    """
    filepath = os.path.join(LOG_DIR, f"{agv_id}_trips.csv")
    if not os.path.exists(filepath):
        return []
    rows = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if date and row.get('date') != date:
                    continue
                if task_type and row.get('task_type') != task_type:
                    continue
                rows.append(row)
    except Exception as e:
        print(f"[TripLogger] Error reading {filepath}: {e}")
    return rows
