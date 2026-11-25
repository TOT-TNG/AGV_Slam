"""
agv_cmd_channel.py — Gửi `run`/`stop` tới Line AGV có xác nhận theo ID (09-ack-lenh-fms.md §2.2).

Xe vào thang → cabin đóng cửa → mất Wi-Fi; MQTT QoS0 không có ACK tầng ứng dụng nên lệnh gửi lúc đó
rơi hẳn. Kênh này: gắn `id` (≤ 9 ký tự) vào lệnh, giữ lệnh trong hàng chờ, gửi lặp CÙNG `id` mỗi
RETRY_S giây cho tới khi `state.cmd_ack == id` (tối đa MAX_SENDS lần gửi). Thiết bị OFFLINE → giữ
lệnh, KHÔNG gửi, KHÔNG đếm lần gửi; online lại → gửi bù.

Module thuần (không import mqtt_client/line_agv_handler) để test không cần broker: nơi dùng gọi
`configure(publish=…, is_available=…)` một lần.

Chế độ (env AGV_CMD_ACK_MODE):
  auto   (mặc định) xe đã từng báo `cmd_ack` → chờ đúng ACK; xe chưa từng báo (firmware cũ) → coi lệnh
         xong theo state: run ⇔ paused=false, stop ⇔ driving=false ∧ paused=false (§2.2 mục 8).
  strict luôn chờ `cmd_ack` (firmware đã nạp lại cho cả đội xe).
  off    gửi một lần như trước đây (không id, không gửi lặp).
"""
from __future__ import annotations

import os
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Callable, Dict, Optional

RETRY_S = 3.0          # chưa thấy cmd_ack sau chừng này → gửi lại cùng id
MAX_SENDS = 4          # 1 lần gửi đầu + tối đa 3 lần gửi lặp (§2.2 mục 3)
STATE_STALE_S = 5.0    # state cũ hơn mức này = chưa có thông tin về xe (§1)

ACK_CMDS = ("run", "stop")   # CHỈ run/stop có cmd_ack; `reset` KHÔNG gắn id (Arduino khởi động lại → mất cmd_ack)


def _mode() -> str:
    m = os.environ.get("AGV_CMD_ACK_MODE", "auto").strip().lower()
    return m if m in ("auto", "strict", "off") else "auto"


@dataclass
class _Pending:
    cmd: str
    cmd_id: str
    sends: int = 0
    sent_at: float = -1e9
    held_logged: bool = False


class AgvCommandChannel:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._pending: Dict[str, _Pending] = {}
        self._ack_capable: set = set()          # xe đã từng báo cmd_ack → firmware mới
        self._publish: Optional[Callable[[str, dict], bool]] = None
        self._available: Callable[[str], bool] = lambda _a: True
        self._clock: Callable[[], float] = time.monotonic
        self._on_expired: Optional[Callable[[str, str], None]] = None
        self._on_acked: Optional[Callable[[str, str], None]] = None
        self.stats = {"sent": 0, "resent": 0, "acked": 0, "expired": 0, "held": 0}

    # ---- cấu hình ----
    def configure(self, publish: Callable[[str, dict], bool],
                  is_available: Optional[Callable[[str], bool]] = None,
                  on_expired: Optional[Callable[[str, str], None]] = None,
                  clock: Optional[Callable[[], float]] = None,
                  on_acked: Optional[Callable[[str, str], None]] = None) -> None:
        self._publish = publish
        if is_available is not None:
            self._available = is_available
        self._on_expired = on_expired
        self._on_acked = on_acked
        if clock is not None:
            self._clock = clock

    # ---- API ----
    def send(self, agv_id: str, cmd: str) -> bool:
        """Đăng ký lệnh `run`/`stop`, gửi ngay nếu xe khả dụng. Lệnh sau ĐÈ lệnh trước (run rồi stop → chỉ
        còn stop). True = đã gửi hoặc đã xếp hàng chờ gửi."""
        if self._publish is None:
            return False
        if _mode() == "off" or cmd not in ACK_CMDS:
            return self._publish(agv_id, {"c": cmd})
        with self._lock:
            self._pending[agv_id] = _Pending(cmd=cmd, cmd_id=uuid.uuid4().hex[:8])
        return self._flush(agv_id)

    def on_state(self, agv_id: str, data: dict, paused: bool, driving: bool) -> None:
        """Gọi mỗi khi nhận state của xe: kiểm ACK, rồi gửi bù/lặp nếu cần."""
        ack = str(data.get("cmd_ack", "") or "").strip()
        acked_cmd = None
        with self._lock:
            if ack:
                self._ack_capable.add(agv_id)
            p = self._pending.get(agv_id)
            if p is None:
                return
            if ack and ack == p.cmd_id:
                self._pending.pop(agv_id, None)
                self.stats["acked"] += 1
                acked_cmd = p.cmd
            elif p.sends > 0 and _mode() == "auto" and agv_id not in self._ack_capable:
                done = (not paused) if p.cmd == "run" else (not driving and not paused)
                if done:                       # firmware cũ: không có cmd_ack → dựa vào state
                    self._pending.pop(agv_id, None)
                    self.stats["acked"] += 1
                    acked_cmd = p.cmd
        if acked_cmd is not None:
            if self._on_acked is not None:
                try:
                    self._on_acked(agv_id, acked_cmd)
                except Exception as e:
                    print(f"[CMD_ACK] on_acked lỗi: {e}")
            return
        self._flush(agv_id)

    def tick(self) -> None:
        """Quét hàng chờ (phòng khi không có state nào tới để kích gửi lặp)."""
        for agv_id in list(self._pending):
            self._flush(agv_id)

    def pending(self, agv_id: str) -> Optional[str]:
        p = self._pending.get(agv_id)
        return p.cmd if p else None

    def cancel(self, agv_id: str) -> None:
        with self._lock:
            self._pending.pop(agv_id, None)

    # ---- nội bộ ----
    def _flush(self, agv_id: str) -> bool:
        with self._lock:
            p = self._pending.get(agv_id)
            if p is None or self._publish is None:
                return False
            now = self._clock()
            if not self._available(agv_id):
                if not p.held_logged:           # chỉ log khi đổi trạng thái (không in heartbeat)
                    p.held_logged = True
                    self.stats["held"] += 1
                    print(f"[CMD_ACK] {agv_id}: offline — GIỮ lệnh '{p.cmd}' (id={p.cmd_id}), gửi bù khi online lại")
                return True
            if p.held_logged:
                p.held_logged = False
                print(f"[CMD_ACK] {agv_id}: online lại — gửi bù '{p.cmd}' (id={p.cmd_id})")
                p.sent_at = -1e9
            if now - p.sent_at < RETRY_S:
                return True
            if p.sends >= MAX_SENDS:
                self._pending.pop(agv_id, None)
                self.stats["expired"] += 1
                print(f"[CMD_ACK] {agv_id}: '{p.cmd}' (id={p.cmd_id}) KHÔNG được xác nhận sau {p.sends} lần gửi — bỏ")
                cb = self._on_expired
            else:
                cb = None
                p.sends += 1
                p.sent_at = now
                self.stats["resent" if p.sends > 1 else "sent"] += 1
                if p.sends > 1:
                    print(f"[CMD_ACK] {agv_id}: chưa thấy cmd_ack={p.cmd_id} → gửi lại '{p.cmd}' lần {p.sends}/{MAX_SENDS}")
                ok = self._publish(agv_id, {"c": p.cmd, "ts": int(time.time()), "id": p.cmd_id})
                return ok
        if cb is not None:
            try:
                cb(agv_id, p.cmd)
            except Exception as e:
                print(f"[CMD_ACK] on_expired lỗi: {e}")
        return False


agv_cmd_channel = AgvCommandChannel()
