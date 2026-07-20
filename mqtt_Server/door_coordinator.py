"""
Điều phối cửa tự động cho Line AGV.

Bối cảnh: một số node trên bản đồ nằm sát 1 cửa tự động (kho lạnh, khu vực
kiểm soát ra/vào...). Xe phải xin mở cửa trước khi băng qua, và server phải
báo đóng lại sau khi xe đã qua hẳn.

Thiết kế (thống nhất với người dùng — xem lịch sử trao đổi, không lặp lại ở
đây): mỗi cửa gắn với ĐÚNG 2 node trên bản đồ (2 phía của cửa), cùng gán 1
`door_id` trong node_actions — KHÔNG cần nhãn "ngoài/trong" tĩnh, hướng được
suy ra lúc chạy từ `prev_tag` của xe so với node còn lại:
  - Tới 1 trong 2 node mà KHÔNG phải từ node kia sang → ĐANG TIẾN VÀO cửa
    → xin MỞ, xe đứng chờ tới khi cửa xác nhận mở xong.
  - Tới 1 trong 2 node MÀ từ node kia sang (vừa băng qua) → ĐÃ QUA cửa
    → báo cửa có thể đóng (chỉ đóng thật khi không còn xe nào khác đang qua).

Xem PROTOCOL_GUIDE.md mục "Cửa tự động (Gate Controller)" để biết giao thức
MQTT đầy đủ giữa server và bộ điều khiển cửa (dành cho đội firmware).

Giao thức bên trong module này với line_agv_handler.py:
  - request_open(door_id, agv_id): gọi khi xe TỚI node cửa (chiều tiến vào),
    xe đã dừng hẳn (WAIT_SYS/WAIT_USER) chờ được cho đi tiếp.
  - notify_exit(door_id, agv_id): gọi khi xe BĂNG QUA cửa (tag mới là 1 trong
    2 node, tag cũ là node còn lại) — KHÔNG cần xe dừng, chạy nền.
  - check_retries(): gọi định kỳ (mỗi state message bất kỳ AGV nào) để phát
    hiện timeout chờ xác nhận mở cửa và tự gửi lại — áp dụng đúng bài học từ
    lỗi nâng móc không phản hồi (xem HOOK_RAISE_TIMEOUT ở line_agv_handler.py).
"""
import time
from dataclasses import dataclass, field

DOOR_OPEN_TIMEOUT      = 6.0   # giây chờ xác nhận MỞ trước khi gửi lại
DOOR_OPEN_MAX_RETRIES  = 2     # số lần gửi lại tối đa trước khi bỏ cuộc tự động


def find_paired_door_node(node_actions: dict, door_id: str, exclude_node: str) -> str | None:
    """Tìm node CÒN LẠI của cùng 1 cửa (cùng door_id, khác node hiện tại)."""
    if not door_id:
        return None
    for nid, cfg in (node_actions or {}).items():
        if str(nid) == str(exclude_node):
            continue
        if str((cfg or {}).get('door_id') or '') == str(door_id):
            return str(nid)
    return None


@dataclass
class _DoorInfo:
    state:        str   = "closed"   # "closed"|"opening"|"open"|"closing"|"error"
    in_transit:   set   = field(default_factory=set)   # agv_id đang ở giữa 2 node của cửa
    waiting:      set   = field(default_factory=set)   # agv_id đang đứng CHỜ xác nhận mở
    open_sent_at: float = 0.0
    open_retries: int   = 0


class DoorCoordinator:
    def __init__(self):
        self._doors: dict[str, _DoorInfo] = {}

    def _get(self, door_id: str) -> _DoorInfo:
        if door_id not in self._doors:
            self._doors[door_id] = _DoorInfo()
        return self._doors[door_id]

    # ── Xe TIẾN VÀO cửa ──────────────────────────────────────────────────────
    def request_open(self, door_id: str, agv_id: str) -> None:
        info = self._get(door_id)
        info.in_transit.add(agv_id)
        if info.state == "open":
            print(f"[DOOR] {door_id}: đã mở sẵn — {agv_id} đi qua ngay, không cần chờ")
            self._resume_agv(agv_id)
            return
        info.waiting.add(agv_id)
        if info.state == "opening":
            print(f"[DOOR] {door_id}: đang mở (xin bởi xe khác) — {agv_id} chờ cùng")
            return
        self._send_open(door_id)

    def _send_open(self, door_id: str) -> None:
        info = self._get(door_id)
        info.state = "opening"
        info.open_sent_at = time.monotonic()
        try:
            from mqtt_client import send_gate_command
            send_gate_command(door_id, "open")
            print(f"[DOOR] {door_id}: đã gửi lệnh MỞ")
        except Exception as e:
            print(f"[DOOR] {door_id}: gửi lệnh MỞ lỗi: {e}")

    def check_retries(self) -> None:
        """Gọi định kỳ — phát hiện cửa không xác nhận MỞ sau DOOR_OPEN_TIMEOUT giây."""
        _now = time.monotonic()
        for door_id, info in self._doors.items():
            if info.state != "opening" or info.open_sent_at <= 0:
                continue
            if _now - info.open_sent_at < DOOR_OPEN_TIMEOUT:
                continue
            if info.open_retries < DOOR_OPEN_MAX_RETRIES:
                info.open_retries += 1
                print(f"[DOOR] {door_id}: không thấy xác nhận MỞ sau "
                      f"{_now - info.open_sent_at:.1f}s → GỬI LẠI lần "
                      f"{info.open_retries}/{DOOR_OPEN_MAX_RETRIES}")
                self._send_open(door_id)
            else:
                print(f"[DOOR] {door_id}: đã gửi lại {DOOR_OPEN_MAX_RETRIES} lần vẫn "
                      f"không có xác nhận MỞ — dừng thử tự động, cần kiểm tra thủ công")
                info.state = "error"
                info.open_sent_at = 0.0

    # ── Nhận trạng thái cửa từ MQTT (gate/v1/{factory}/{door_id}/state) ──────
    def on_gate_state(self, door_id: str, gate_state: str) -> None:
        info = self._get(door_id)
        info.state = gate_state
        if gate_state == "open":
            info.open_sent_at = 0.0
            info.open_retries = 0
            waiting = list(info.waiting)
            info.waiting.clear()
            for agv_id in waiting:
                print(f"[DOOR] {door_id}: xác nhận MỞ — {agv_id} đi tiếp")
                self._resume_agv(agv_id)
        elif gate_state == "error":
            print(f"[DOOR] {door_id}: bộ điều khiển cửa báo LỖI — dừng thử tự động, "
                  f"cần kiểm tra thủ công")
            info.open_sent_at = 0.0

    # ── Xe BĂNG QUA cửa (không cần dừng) ─────────────────────────────────────
    def notify_exit(self, door_id: str, agv_id: str) -> None:
        info = self._get(door_id)
        info.in_transit.discard(agv_id)
        info.waiting.discard(agv_id)
        if info.in_transit:
            print(f"[DOOR] {door_id}: {agv_id} đã qua, còn {len(info.in_transit)} "
                  f"xe khác đang dùng cửa — GIỮ MỞ")
            return
        print(f"[DOOR] {door_id}: không còn xe nào đang qua — gửi lệnh ĐÓNG")
        info.state = "closing"
        try:
            from mqtt_client import send_gate_command
            send_gate_command(door_id, "close")
        except Exception as e:
            print(f"[DOOR] {door_id}: gửi lệnh ĐÓNG lỗi: {e}")

    def _resume_agv(self, agv_id: str) -> None:
        try:
            from line_agv_handler import line_agv_handler
            line_agv_handler.resume_after_door(agv_id)
        except Exception as e:
            print(f"[DOOR] resume {agv_id} lỗi: {e}")


door_coordinator = DoorCoordinator()
