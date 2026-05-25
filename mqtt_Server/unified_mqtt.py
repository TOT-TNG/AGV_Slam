"""
unified_mqtt.py — Unified MQTT routing layer
----------------------------------------------
Xử lý MQTT cho cả 2 loại AGV trên cùng 1 broker:

  Line AGV:  uagv/v2/{factory}/{agv_id}/{kind}
  VDA5050:   uagv/v3/{manufacturer}/{agv_id}/{kind}
             vda5050/agv/{agv_id}/{kind}              ← format dự phòng

Flow:
  on_message → TopicRouter.parse() → LINE  → LineAGVHandler.dispatch()
                                   → VDA5050 → on_message_vda5050() (logic gốc)
"""
from __future__ import annotations

import os
import json
import time
from typing import Optional

from agv_registry import agv_registry, AGV_TYPE_LINE, AGV_TYPE_VDA5050

# ─── Env ──────────────────────────────────────────────────────────────────────
LINE_AGV_VERSION       = os.getenv("LINE_AGV_MQTT_VERSION", "v2").strip()
LINE_AGV_FACTORY       = os.getenv("LINE_AGV_FACTORY", "").strip()   # fallback từ config
UAGV_INTERFACE_NAME    = os.getenv("UAGV_INTERFACE_NAME", "uagv").strip() or "uagv"
UAGV_MAJOR_VERSION     = os.getenv("UAGV_MAJOR_VERSION", "v3").strip() or "v3"
QOS                    = int(os.getenv("MQTT_QOS", "0"))


# ═══════════════════════════════════════════════════════════════════════════════
# TopicRouter
# ═══════════════════════════════════════════════════════════════════════════════

class TopicRouter:
    """
    Phân tích MQTT topic → (agv_type, agv_id, message_kind).

    Patterns hỗ trợ:
      uagv/v2/{factory}/{agv_id}/{kind}          → LINE
      uagv/v3/{manufacturer}/{agv_id}/{kind}     → VDA5050
      vda5050/agv/{agv_id}/{kind}                → VDA5050 (fallback)
    """

    def parse(self, topic: str) -> tuple[str, str, str]:
        """Returns (agv_type, agv_id, message_kind). agv_type = 'LINE'|'VDA5050'|''"""
        parts = topic.split("/")

        # uagv/{version}/{...}/{agv_id}/{kind}
        if len(parts) == 5 and parts[0] == UAGV_INTERFACE_NAME:
            version  = parts[1]
            agv_id   = parts[3]
            kind     = parts[4]

            if version == LINE_AGV_VERSION:           # v2 → Line AGV
                return AGV_TYPE_LINE, agv_id, kind
            if version == UAGV_MAJOR_VERSION:         # v3 → VDA5050
                return AGV_TYPE_VDA5050, agv_id, kind

        # vda5050/agv/{agv_id}/{kind}
        if len(parts) == 4 and parts[0] == "vda5050" and parts[1] == "agv":
            return AGV_TYPE_VDA5050, parts[2], parts[3]

        # Camera topic: convQR/...
        if parts and parts[0] == "convQR":
            return "CAMERA", "", ""

        # Không xác định → để VDA5050 handler tự parse (backward compat)
        return AGV_TYPE_VDA5050, "", ""

    def is_line_topic(self, topic: str) -> bool:
        agv_type, _, _ = self.parse(topic)
        return agv_type == AGV_TYPE_LINE


# ═══════════════════════════════════════════════════════════════════════════════
# Subscription setup
# ═══════════════════════════════════════════════════════════════════════════════

def setup_subscriptions(client, config: dict) -> None:
    """
    Subscribe topic dựa trên loại AGV được cấu hình.
    Gọi từ on_connect() của mqtt_client.py.
    """
    factory      = config.get("factory", LINE_AGV_FACTORY or "default")
    manufacturer = config.get("manufacturer", os.getenv("UAGV_MANUFACTURER", "tot"))

    has_line  = agv_registry.has_line_agvs()
    has_vda   = agv_registry.has_vda5050_agvs()

    # ── Line AGV (v2) ─────────────────────────────────────────────────────────
    # Bỏ qua nếu unified_main.py đã xử lý bằng client riêng (tránh double-subscribe)
    _line_external = os.getenv("LINE_AGV_MQTT_EXTERNAL", "0") == "1"
    if has_line and not _line_external:
        for kind in ("state", "connection"):
            topic = f"{UAGV_INTERFACE_NAME}/{LINE_AGV_VERSION}/{factory}/+/{kind}"
            client.subscribe(topic, qos=QOS)
            print(f"[UNIFIED_MQTT] Subscribed (LINE): {topic}")
    elif has_line and _line_external:
        print(f"[UNIFIED_MQTT] Line AGV v2 subscriptions handled externally (unified_main)")

    # ── VDA5050 (v3) — đã subscribe trong on_connect gốc, không cần lặp lại ──
    # Chỉ in thông báo để rõ ràng
    if has_vda:
        print(f"[UNIFIED_MQTT] VDA5050 subscriptions (v3 / vda5050): handled by existing on_connect")

    print(f"[UNIFIED_MQTT] Registry: {agv_registry}")


# ═══════════════════════════════════════════════════════════════════════════════
# UnifiedPublisher
# ═══════════════════════════════════════════════════════════════════════════════

class UnifiedPublisher:
    """
    Publish MQTT đúng topic theo loại AGV.
    Line AGV → uagv/v2/{factory}/{agv_id}/{kind}
    VDA5050  → uagv/v3/{manufacturer}/{agv_id}/{kind}  +  vda5050/agv/{agv_id}/{kind}
    """

    def __init__(self, client, config: dict):
        self._client       = client
        self._factory      = config.get("factory", LINE_AGV_FACTORY or "default")
        self._manufacturer = config.get("manufacturer",
                                        os.getenv("UAGV_MANUFACTURER", "tot"))

    # ── Gửi order / plan ──────────────────────────────────────────────────────
    def send_order(self, agv_id: str, payload) -> None:
        body = payload if isinstance(payload, (str, bytes)) else json.dumps(payload)
        topics = self._order_topics(agv_id)
        for topic in topics:
            self._client.publish(topic, body, qos=QOS)

    # ── Gửi instantActions ───────────────────────────────────────────────────
    def send_instant(self, agv_id: str, payload) -> None:
        body = payload if isinstance(payload, (str, bytes)) else json.dumps(payload)
        topics = self._instant_topics(agv_id)
        for topic in topics:
            self._client.publish(topic, body, qos=QOS)

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _order_topics(self, agv_id: str) -> list[str]:
        if agv_registry.is_line(agv_id):
            factory = agv_registry.get_factory(agv_id, default=self._factory)
            return [f"{UAGV_INTERFACE_NAME}/{LINE_AGV_VERSION}/{factory}/{agv_id}/order"]
        return [
            f"vda5050/agv/{agv_id}/order",
            f"{UAGV_INTERFACE_NAME}/{UAGV_MAJOR_VERSION}/{self._manufacturer}/{agv_id}/order",
        ]

    def _instant_topics(self, agv_id: str) -> list[str]:
        if agv_registry.is_line(agv_id):
            factory = agv_registry.get_factory(agv_id, default=self._factory)
            return [f"{UAGV_INTERFACE_NAME}/{LINE_AGV_VERSION}/{factory}/{agv_id}/instantActions"]
        return [
            f"vda5050/agv/{agv_id}/instantActions",
            f"{UAGV_INTERFACE_NAME}/{UAGV_MAJOR_VERSION}/{self._manufacturer}/{agv_id}/instantActions",
        ]


# ── Module-level singleton router ─────────────────────────────────────────────
topic_router = TopicRouter()

# Publisher được tạo sau khi có client + config (gọi init_publisher())
_publisher: Optional[UnifiedPublisher] = None


def init_publisher(client, config: dict) -> UnifiedPublisher:
    global _publisher
    _publisher = UnifiedPublisher(client, config)
    return _publisher


def get_publisher() -> Optional[UnifiedPublisher]:
    return _publisher
