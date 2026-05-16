"""
traffic/reservation.py  — 2.2 Reservation
-------------------------------------------
Migrate từ zone_manager.py (Zone + ZoneManager — toàn bộ class).
Node reservation (clear_reservations, try_reserve_path, get_reserved_by)
đã nằm trong traffic/planner.py → TrafficManager.
"""
from __future__ import annotations
import json
import os
import time
from collections import defaultdict

# ─── Priority Mapping ─────────────────────────────────────────────────────────
# Số nhỏ hơn = ưu tiên cao hơn
MISSION_PRIORITY = {
    "delivery":                  1,
    "pickup":                    2,
    "return_reversing_charge":   3,
    "return_charge":             3,
    "homing_search":             4,
    "idle":                     99,
}


# ─── Zone ─────────────────────────────────────────────────────────────────────
class Zone:
    """Đại diện cho một vùng bảo vệ trên bản đồ."""

    def __init__(self, cfg: dict):
        self.id      = cfg["id"]
        self.name    = cfg.get("name", self.id)
        self.type    = cfg.get("type", "INTERSECTION")   # INTERSECTION | SINGLE_LANE | RESOURCE | BYPASS
        self.nodes   = set(int(n) for n in cfg.get("nodes", []))
        self.tokens  = int(cfg.get("tokens", 1))         # số AGV tối đa được vào cùng lúc
        self.holders: set  = set()                       # agv_id đang giữ token
        self.queue:   list = []                          # [(priority, timestamp, agv_id)]

        # BYPASS zone: danh sách điểm dừng chờ, sắp xếp từ sâu nhất → gần cửa vào nhất
        self.slots:    list = [int(s) for s in cfg.get("slots", [])]
        self.slot_map: dict = {s: None for s in self.slots}  # slot_node → agv_id | None

    # ── Kiểm tra ──────────────────────────────────────────────────────────────
    def is_full(self) -> bool:
        return len(self.holders) >= self.tokens

    def is_held_by(self, agv_id: str) -> bool:
        return agv_id in self.holders

    def in_queue(self, agv_id: str) -> bool:
        return any(a == agv_id for _, _, a in self.queue)

    # ── Cấp / Nhả token ───────────────────────────────────────────────────────
    def grant(self, agv_id: str):
        self.holders.add(agv_id)
        self._remove_from_queue(agv_id)

    def release(self, agv_id: str):
        self.holders.discard(agv_id)
        self._remove_from_queue(agv_id)

    def enqueue(self, agv_id: str, priority: int):
        if not self.in_queue(agv_id):
            self.queue.append((priority, time.time(), agv_id))
            self.queue.sort(key=lambda x: (x[0], x[1]))

    def next_in_queue(self):
        """Trả về agv_id ưu tiên nhất đang chờ (hoặc None)."""
        return self.queue[0][2] if self.queue else None

    def _remove_from_queue(self, agv_id: str):
        self.queue = [(p, t, a) for p, t, a in self.queue if a != agv_id]

    def __repr__(self):
        return (f"Zone({self.id!r} nodes={self.nodes} "
                f"holders={self.holders} queue={[a for _,_,a in self.queue]})")


# ─── ZoneManager ──────────────────────────────────────────────────────────────
class ZoneManager:
    """
    Quản lý tập hợp các Zone.

    Interface chính:
        request_passage(agv_id, next_nodes, task_type) -> bool
        release_zones_not_in(agv_id, current_node)
        release_all(agv_id)
        tick_waiting_agvs(agv_list) -> list[AGV]
    """

    def __init__(self, zones_config_file: str = ""):
        self.zones:         dict = {}
        self.node_to_zones: dict = defaultdict(list)
        if zones_config_file:
            self._load(zones_config_file)

    # ── Load config ───────────────────────────────────────────────────────────
    def _load(self, path: str):
        if not os.path.exists(path):
            print(f"[ZoneMgr] Không tìm thấy file zones config: {path}. Chạy không có zone.")
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            for cfg in data.get("zones", []):
                z = Zone(cfg)
                self.zones[z.id] = z
                for node in z.nodes:
                    self.node_to_zones[node].append(z.id)
            print(f"[ZoneMgr] Đã load {len(self.zones)} zone(s): "
                  f"{[z.name for z in self.zones.values()]}")
        except Exception as e:
            print(f"[ZoneMgr] Lỗi load zones: {e}")

    # ── Core API ──────────────────────────────────────────────────────────────
    def request_passage(self, agv_id: str, next_nodes: list, task_type: str = "idle") -> bool:
        """
        AGV muốn đi vào next_nodes.
        Returns True nếu tất cả zone cấp token, False nếu phải chờ.
        """
        if not self.zones:
            return True

        required_zone_ids = self._get_zone_ids_for(next_nodes)
        if not required_zone_ids:
            return True

        priority    = MISSION_PRIORITY.get(task_type, 99)
        all_granted = True

        for z_id in required_zone_ids:
            zone = self.zones[z_id]

            if zone.is_held_by(agv_id):
                continue

            if zone.type == "BYPASS":
                zone.grant(agv_id)
                continue

            if not zone.is_full():
                zone.grant(agv_id)
                print(f"[ZoneMgr] ✓ {agv_id} → zone '{zone.name}' (token cấp)")
            else:
                zone.enqueue(agv_id, priority)
                holders_str = ", ".join(zone.holders)
                print(f"[ZoneMgr] ⏳ {agv_id} chờ zone '{zone.name}' "
                      f"(đang giữ: {holders_str}, queue: {[a for _,_,a in zone.queue]})")
                all_granted = False

        return all_granted

    def release_zones_not_in(self, agv_id: str, current_node: int):
        """Giải phóng token của các zone mà current_node KHÔNG thuộc về."""
        for zone in self.zones.values():
            if zone.is_held_by(agv_id) and current_node not in zone.nodes:
                zone.release(agv_id)
                print(f"[ZoneMgr] ↩ {agv_id} rời zone '{zone.name}' (tại node {current_node})")

    def release_all(self, agv_id: str):
        """Giải phóng TẤT CẢ token của AGV này."""
        released = []
        for zone in self.zones.values():
            if zone.is_held_by(agv_id):
                zone.release(agv_id)
                released.append(zone.name)
        if released:
            print(f"[ZoneMgr] ✗ {agv_id} nhả tất cả zone: {released}")

    def tick_waiting_agvs(self, agv_list: list) -> list:
        """
        Gọi mỗi chu kỳ traffic control (~500ms).
        Thử cấp token cho AGV đứng đầu hàng chờ khi có slot trống.
        Returns: danh sách AGV được cấp token và cần resume.
        """
        ready_agvs = []
        for zone in self.zones.values():
            if zone.is_full() or not zone.queue:
                continue
            next_agv_id = zone.next_in_queue()
            next_agv = next((a for a in agv_list if a.id == next_agv_id), None)
            if next_agv is None:
                zone._remove_from_queue(next_agv_id)
                continue
            if not next_agv.zone_waiting:
                zone._remove_from_queue(next_agv_id)
                continue
            segment = getattr(next_agv, '_zone_waiting_segment', [])
            if not segment:
                continue
            next_nodes = segment[1:]
            if self.request_passage(next_agv_id, next_nodes, next_agv.current_task_type):
                print(f"[ZoneMgr] ▶ {next_agv_id} được tiếp tục (zone '{zone.name}' freed)")
                ready_agvs.append(next_agv)
        return ready_agvs

    # ── Bypass Slot API ───────────────────────────────────────────────────────
    def request_bypass_slot(self, agv_id: str, zone_id: str) -> int | None:
        """Cấp slot cho AGV trong BYPASS zone. Trả về node_id hoặc None."""
        zone = self.zones.get(zone_id)
        if not zone or zone.type != "BYPASS" or not zone.slots:
            return None
        for slot in zone.slots:
            if zone.slot_map.get(slot) is None:
                zone.slot_map[slot] = agv_id
                print(f"[ZoneMgr] {agv_id} → bypass slot {slot} in '{zone.name}'")
                return slot
        return None

    def release_bypass_slot(self, agv_id: str):
        """Nhả slot của AGV trong tất cả BYPASS zone."""
        for zone in self.zones.values():
            if zone.type == "BYPASS":
                for slot in zone.slots:
                    if zone.slot_map.get(slot) == agv_id:
                        zone.slot_map[slot] = None
                        print(f"[ZoneMgr] {agv_id} nhả bypass slot {slot} trong '{zone.name}'")
                        return

    def get_zone_for_bypass_slot(self, tag_id: int):
        """Trả về zone nếu tag_id là slot trong BYPASS zone, ngược lại None."""
        for zone in self.zones.values():
            if zone.type == "BYPASS" and tag_id in zone.slot_map:
                return zone
        return None

    def find_bypass_zone_for_conflict(self, current_tag: int) -> tuple:
        """Tìm BYPASS zone có slot trống. Trả về (zone, slot_node) hoặc (None, None)."""
        for zone in self.zones.values():
            if zone.type != "BYPASS" or not zone.slots:
                continue
            for slot in zone.slots:
                if zone.slot_map.get(slot) is None:
                    return zone, slot
        return None, None

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _get_zone_ids_for(self, nodes: list) -> set:
        result = set()
        for n in nodes:
            for z_id in self.node_to_zones.get(int(n), []):
                result.add(z_id)
        return result

    # ── CRUD (dùng từ UI editor) ──────────────────────────────────────────────
    def add_or_update_zone(self, cfg: dict):
        z = Zone(cfg)
        self.zones[z.id] = z
        self._rebuild_index()
        print(f"[ZoneMgr] Zone '{z.name}' saved (id={z.id}, nodes={z.nodes})")

    def delete_zone(self, zone_id: str):
        if zone_id in self.zones:
            name = self.zones[zone_id].name
            del self.zones[zone_id]
            self._rebuild_index()
            print(f"[ZoneMgr] Zone '{name}' deleted.")

    def _rebuild_index(self):
        self.node_to_zones = defaultdict(list)
        for z in self.zones.values():
            for node in z.nodes:
                self.node_to_zones[node].append(z.id)

    def save(self, path: str):
        data = {"zones": []}
        for z in self.zones.values():
            entry = {
                "id":     z.id,
                "name":   z.name,
                "type":   z.type,
                "nodes":  sorted(list(z.nodes)),
                "tokens": z.tokens,
            }
            if z.slots:
                entry["slots"] = z.slots
            data["zones"].append(entry)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            print(f"[ZoneMgr] Saved {len(self.zones)} zone(s) to {path}")
        except Exception as e:
            print(f"[ZoneMgr] Error saving zones: {e}")

    def is_enabled(self) -> bool:
        return bool(self.zones)

    # ── Status (cho UI/debug) ─────────────────────────────────────────────────
    def get_status(self) -> dict:
        result = {}
        for z_id, zone in self.zones.items():
            result[z_id] = {
                "name":    zone.name,
                "type":    zone.type,
                "tokens":  zone.tokens,
                "holders": list(zone.holders),
                "queue":   [a for _, _, a in zone.queue],
                "nodes":   list(zone.nodes),
            }
        return result

    def print_status(self):
        if not self.zones:
            print("[ZoneMgr] Không có zone nào được cấu hình.")
            return
        print("─" * 50)
        print("[ZoneMgr] ZONE STATUS:")
        for zone in self.zones.values():
            queue_str = " → ".join(a for _, _, a in zone.queue) or "(trống)"
            print(f"  [{zone.type}] {zone.name}: "
                  f"holders={list(zone.holders)}, queue={queue_str}")
        print("─" * 50)
