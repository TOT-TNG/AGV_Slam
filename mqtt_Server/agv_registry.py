"""
agv_registry.py — AGV type registry
--------------------------------------
Singleton được load từ DB (bảng agv_devices) hoặc từ config khi server khởi động.

Quy tắc phân loại:
  agv_type bắt đầu bằng "slam" → VDA5050
  Tất cả còn lại (tow, carry, trailer, ...)  → LINE

Index phụ:
  _ip_index: {ip_str: agv_id}  — tra cứu AGV từ địa chỉ IP
"""
from __future__ import annotations

import os
from typing import Optional

AGV_TYPE_LINE    = "LINE"
AGV_TYPE_VDA5050 = "VDA5050"

_DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:ducmanh1801@localhost:5432/TOT_AGV",
)


def _classify(agv_type: str) -> str:
    """slam* → VDA5050, mọi type khác → LINE."""
    return AGV_TYPE_VDA5050 if str(agv_type or "").lower().startswith("slam") else AGV_TYPE_LINE


class AgvRegistry:
    def __init__(self):
        self._type:     dict[str, str]  = {}   # agv_id → "LINE" | "VDA5050"
        self._config:   dict[str, dict] = {}   # agv_id → raw config dict
        self._ip_index: dict[str, str]  = {}   # ip_str → agv_id

    # ── Load từ DB (agv_devices) ──────────────────────────────────────────────
    def load_from_db(self, db_url: str = _DB_URL) -> None:
        """
        Đọc toàn bộ agv_devices từ PostgreSQL.
        Gọi khi server khởi động (sau khi DB pool sẵn sàng).
        """
        try:
            import psycopg2
        except ImportError:
            print("[REGISTRY] psycopg2 not available — skipping DB load")
            return
        try:
            conn = psycopg2.connect(db_url)
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT name, agv_type, ip, factory, map_id FROM agv_devices ORDER BY name"
                )
                rows = cur.fetchall()
            conn.close()
        except Exception as e:
            print(f"[REGISTRY] DB load failed: {e}")
            return

        self._type.clear()
        self._config.clear()
        self._ip_index.clear()

        for name, agv_type, ip, factory, map_id in rows:
            agv_id   = str(name).strip()
            reg_type = _classify(agv_type or "")
            self._type[agv_id]   = reg_type
            self._config[agv_id] = {
                "agv_id":   agv_id,
                "agv_type": agv_type or "",
                "reg_type": reg_type,
                "ip":       str(ip) if ip else "",
                "factory":  str(factory).strip() if factory else "",
                "map_id":   str(map_id).strip() if map_id else "",
            }
            if ip:
                self._ip_index[str(ip).strip()] = agv_id

        print(f"[REGISTRY] Loaded from DB: {len(self._type)} AGV(s) — "
              f"LINE={self.line_agv_ids()} VDA5050={self.vda5050_agv_ids()}")

    # ── Load từ config list (simulator.json hoặc truyền thẳng) ───────────────
    def load_from_config(self, agv_configs: list[dict]) -> None:
        """
        Đọc danh sách AGV từ config dict và phân loại.
        agv_type bắt đầu bằng 'slam' → VDA5050, còn lại → LINE.
        """
        self._type.clear()
        self._config.clear()
        self._ip_index.clear()
        for cfg in agv_configs:
            agv_id = str(cfg.get("agv_id") or cfg.get("id") or "").strip()
            if not agv_id:
                continue
            raw_type = str(cfg.get("agv_type", "")).strip()
            reg_type = _classify(raw_type)
            self._type[agv_id]   = reg_type
            self._config[agv_id] = {**cfg, "reg_type": reg_type}
            ip = str(cfg.get("ip") or "").strip()
            if ip:
                self._ip_index[ip] = agv_id

    # ── Query theo agv_id ─────────────────────────────────────────────────────
    def get_type(self, agv_id: str) -> Optional[str]:
        return self._type.get(str(agv_id).strip())

    def is_line(self, agv_id: str) -> bool:
        return self.get_type(agv_id) == AGV_TYPE_LINE

    def is_vda5050(self, agv_id: str) -> bool:
        t = self.get_type(agv_id)
        return t is None or t == AGV_TYPE_VDA5050   # None → chưa đăng ký → fallback VDA5050

    def get_config(self, agv_id: str) -> dict:
        return self._config.get(str(agv_id).strip(), {})

    def get_factory(self, agv_id: str, default: str = "VietDuc") -> str:
        """Trả về factory của AGV (dùng trong MQTT topic uagv/v2/{factory}/{agv_id}/...)."""
        return self._config.get(str(agv_id).strip(), {}).get("factory", "") or default

    def get_map_id(self, agv_id: str, default: str = "") -> str:
        """Trả về map_id của AGV từ DB (bảng agv_devices.map_id)."""
        return self._config.get(str(agv_id).strip(), {}).get("map_id", "") or default

    # ── Query theo IP ─────────────────────────────────────────────────────────
    def get_by_ip(self, ip: str) -> Optional[str]:
        """Trả về agv_id đã đăng ký với IP này, hoặc None."""
        return self._ip_index.get(str(ip).strip())

    def get_type_by_ip(self, ip: str) -> Optional[str]:
        agv_id = self.get_by_ip(ip)
        return self.get_type(agv_id) if agv_id else None

    # ── Lists ─────────────────────────────────────────────────────────────────
    def line_agv_ids(self) -> list[str]:
        return [k for k, v in self._type.items() if v == AGV_TYPE_LINE]

    def vda5050_agv_ids(self) -> list[str]:
        return [k for k, v in self._type.items() if v == AGV_TYPE_VDA5050]

    def has_line_agvs(self) -> bool:
        return any(v == AGV_TYPE_LINE for v in self._type.values())

    def has_vda5050_agvs(self) -> bool:
        return not self._type or any(v == AGV_TYPE_VDA5050 for v in self._type.values())

    def all_ids(self) -> list[str]:
        return list(self._type.keys())

    def ip_index(self) -> dict[str, str]:
        return dict(self._ip_index)

    def __repr__(self) -> str:
        return (f"AgvRegistry(line={self.line_agv_ids()}, "
                f"vda5050={self.vda5050_agv_ids()}, "
                f"ip_count={len(self._ip_index)})")


# ── Module-level singleton ────────────────────────────────────────────────────
agv_registry = AgvRegistry()
