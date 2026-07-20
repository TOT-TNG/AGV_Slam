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
        self._can_reverse: dict[str, bool] = {}   # agv_id → có lùi được không (mặc định True nếu không có)

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

    def get_default_factory(self, default: str = "VietDuc") -> str:
        """Trả về factory THẬT của BẤT KỲ AGV nào đã đăng ký factory (khác rỗng) —
        dùng cho các tính năng KHÔNG gắn với 1 agv_id cụ thể (vd cửa tự động).
        Duyệt trực tiếp _config thay vì gọi get_factory() từng AGV — get_factory()
        tự trả về `default` ("VietDuc") ngay khi AGV đó chưa cấu hình, nên nếu chỉ
        lấy get_factory() của AGV ĐẦU TIÊN trong all_ids(), có thể vô tình "ăn"
        đúng cái default che mất factory thật của các AGV khác (đã xảy ra thực tế:
        nhà máy cấu hình "Vonhai" nhưng lấy nhầm về "VietDuc"). 1 server local chỉ
        phục vụ ĐÚNG 1 nhà máy nên factory của AGV bất kỳ (miễn có cấu hình) là
        chính xác để dùng chung."""
        for _cfg in self._config.values():
            _f = str(_cfg.get("factory") or "").strip()
            if _f:
                return _f
        return default

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


    # ── Khả năng lùi (MỚI — hoàn toàn độc lập với load_from_db/load_from_config
    # ở trên để KHÔNG đụng logic nạp registry đang chạy ổn định). AGV không có
    # dữ liệu / cột chưa tồn tại trong DB → mặc định can_reverse=True, tức giữ
    # nguyên hành vi hiện tại cho MỌI AGV đang có (chỉ carry, đều lùi được). ──
    def load_reverse_capability(self, db_url: str = _DB_URL) -> None:
        """Nạp cột agv_devices.can_reverse (nếu có). Lỗi/cột chưa tồn tại → bỏ
        qua im lặng, mọi agv_id giữ mặc định can_reverse=True."""
        try:
            import psycopg2
        except ImportError:
            return
        try:
            conn = psycopg2.connect(db_url)
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute("SELECT name, can_reverse FROM agv_devices")
                rows = cur.fetchall()
            conn.close()
        except Exception as e:
            print(f"[REGISTRY] load_reverse_capability skipped: {e}")
            return
        for name, can_rev in rows:
            if can_rev is not None:
                self._can_reverse[str(name).strip()] = bool(can_rev)
        print(f"[REGISTRY] can_reverse=False cho: "
              f"{[k for k, v in self._can_reverse.items() if not v]}")

    def can_reverse(self, agv_id: str) -> bool:
        """True (mặc định) trừ khi AGV được đánh dấu rõ ràng KHÔNG lùi được
        (xe đầu kéo/rơ-moóc — chỉ đi 1 chiều tiến)."""
        return self._can_reverse.get(str(agv_id).strip(), True)


# ── Module-level singleton ────────────────────────────────────────────────────
agv_registry = AgvRegistry()
