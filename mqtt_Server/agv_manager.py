import threading
<<<<<<< HEAD
from datetime import datetime


class AGVManager:
=======
import time
from datetime import datetime, timezone

class AGVManager:
    """
    Quản lý danh sách AGV và trạng thái hiện tại của từng xe.
    Dữ liệu được cập nhật qua MQTT từ topic vda5050/agv/<id>/state
    """

>>>>>>> 83554841fd7d3c2ff850fed616c1ce8043939574
    def __init__(self):
        self.agvs = {}
        self.lock = threading.Lock()

<<<<<<< HEAD
    def update_status(self, agv_id: str, status_data: dict, ip_address: str = None):
        with self.lock:
            now = datetime.utcnow().isoformat() + "Z"
            previous = self.agvs.get(agv_id, {})
            merged = {
                **previous,
                **status_data,
                "last_update": now,
            }
            if ip_address:
                merged["ip_address"] = ip_address
            self.agvs[agv_id] = merged
=======
    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def update_status(self, agv_id: str, status_data: dict, ip_address: str = None):
        """
        Cập nhật trạng thái AGV khi nhận được gói tin state từ MQTT.
        - last_seen_mono: dùng cho luật offline (ổn định, không phụ thuộc giờ hệ thống)
        - last_update: dùng để hiển thị/debug (ISO UTC)
        - last_update_server: thời điểm server ghi nhận (ISO UTC)
        """
        with self.lock:
            prev_info = self.agvs.get(agv_id, {})

            now_iso = self._utc_now_iso()
            last_seen_mono = time.monotonic()

            # nếu mqtt_client đã set last_update thì giữ, nếu không thì dùng now_iso
            incoming_last_update = status_data.get("last_update") or now_iso

            new_info = {
                **prev_info,
                **status_data,

                # ✅ chuẩn để check offline
                "last_seen_mono": last_seen_mono,

                # ✅ timestamp cho UI/debug
                "last_update": incoming_last_update,
                "last_update_server": now_iso,
            }

            if ip_address:
                new_info["ip_address"] = ip_address

            self.agvs[agv_id] = new_info
>>>>>>> 83554841fd7d3c2ff850fed616c1ce8043939574

    def set_order(self, agv_id: str, order_id: str, order_update_id: int):
        with self.lock:
            info = self.agvs.get(agv_id, {})
            info["currentOrderId"] = order_id
<<<<<<< HEAD
            info["currentOrderUpdateId"] = int(order_update_id)
            self.agvs[agv_id] = info

    def get_order(self, agv_id: str):
        with self.lock:
            info = self.agvs.get(agv_id, {})
            return {
                "order_id": info.get("currentOrderId") or info.get("orderId"),
                "order_update_id": int(info.get("currentOrderUpdateId") or info.get("orderUpdateId") or 0),
            }

    def set_last_control_action(self, agv_id: str, action: str | None):
        with self.lock:
            info = self.agvs.get(agv_id, {})
            if action is None:
                info.pop("lastControlAction", None)
            else:
                info["lastControlAction"] = action
            self.agvs[agv_id] = info

    def get_last_control_action(self, agv_id: str):
        with self.lock:
            return self.agvs.get(agv_id, {}).get("lastControlAction")

=======
            info["currentOrderUpdateId"] = order_update_id
            self.agvs[agv_id] = info

>>>>>>> 83554841fd7d3c2ff850fed616c1ce8043939574
    def get_agv(self, agv_id: str, default=None):
        with self.lock:
            return self.agvs.get(agv_id, default)

<<<<<<< HEAD
    def get_status(self, agv_id: str, default=None):
        return self.get_agv(agv_id, default)

=======
>>>>>>> 83554841fd7d3c2ff850fed616c1ce8043939574
    def list_agvs(self):
        with self.lock:
            return dict(self.agvs)

    def set_ip(self, agv_id: str, ip: str):
        with self.lock:
<<<<<<< HEAD
            info = self.agvs.get(agv_id)
            if info is not None:
                info["ipaddress"] = ip
=======
            if agv_id in self.agvs:
                self.agvs[agv_id]["ipaddress"] = ip
>>>>>>> 83554841fd7d3c2ff850fed616c1ce8043939574

    def get_ip(self, agv_id: str):
        with self.lock:
            agv = self.agvs.get(agv_id)
            return agv.get("ipaddress") if agv else None

    def set_pending_path(self, agv_id: str, path: list):
        with self.lock:
<<<<<<< HEAD
            info = self.agvs.get(agv_id, {})
            info["pending_path"] = list(path)
            self.agvs[agv_id] = info

    def get_pending_path(self, agv_id: str):
        with self.lock:
            path = self.agvs.get(agv_id, {}).get("pending_path")
            return list(path) if path else None

    def clear_pending_path(self, agv_id: str):
        with self.lock:
            info = self.agvs.get(agv_id, {})
            info.pop("pending_path", None)
            self.agvs[agv_id] = info

    def set_pending_destination(self, agv_id: str, destination: str, map_id: str | None = None):
        with self.lock:
            info = self.agvs.get(agv_id, {})
            info["pending_destination"] = str(destination)
            if map_id is not None:
                info["pending_map_id"] = str(map_id)
            self.agvs[agv_id] = info

    def get_pending_destination(self, agv_id: str):
        with self.lock:
            info = self.agvs.get(agv_id, {})
            destination = info.get("pending_destination")
            map_id = info.get("pending_map_id")
            if not destination:
                return None
            return {"destination": str(destination), "map_id": str(map_id) if map_id else None}

    def register_agv(self, agv_id: str, ip_address: str):
        with self.lock:
            info = self.agvs.get(agv_id, {})
            info["ip_address"] = ip_address
            info["registered_at"] = datetime.utcnow().isoformat() + "Z"
            self.agvs[agv_id] = info
            print(f"[AGVManager] Registered AGV {agv_id} with IP {ip_address}")
=======
            self.agvs.setdefault(agv_id, {})
            self.agvs[agv_id]["pending_path"] = path

    def get_pending_path(self, agv_id: str):
        with self.lock:
            return self.agvs.get(agv_id, {}).get("pending_path")

    def register_agv(self, agv_id: str, ip_address: str):
        with self.lock:
            self.agvs[agv_id] = self.agvs.get(agv_id, {})
            self.agvs[agv_id]["ip_address"] = ip_address
            self.agvs[agv_id]["registered_at"] = self._utc_now_iso()
            # set last seen để khỏi bị offline ngay khi vừa register
            self.agvs[agv_id]["last_seen_mono"] = time.monotonic()
            self.agvs[agv_id]["last_update_server"] = self._utc_now_iso()
            print(f"[AGVManager] Registered AGV {agv_id} with IP {ip_address}")
>>>>>>> 83554841fd7d3c2ff850fed616c1ce8043939574
