"""
Điều phối cửa tự động cho Line AGV.

Bối cảnh: một số node trên bản đồ nằm sát 1 cửa tự động (kho lạnh, khu vực
kiểm soát ra/vào...). Xe phải xin mở cửa trước khi băng qua, và server phải
báo đóng lại sau khi xe đã qua hẳn.

Thiết kế: mỗi cửa gắn với ĐÚNG 2 node trên bản đồ (2 phía của cửa), cùng gán 1
`door_id` trong node_actions. QUAN TRỌNG: 2 node này KHÔNG bắt buộc phải liền
kề nhau (nối trực tiếp 1 cạnh) — thực tế có map mà 2 phía cửa cách nhau qua
nhiều node trung gian (khu vực trong cửa rộng). Vì vậy hướng đi (vào/ra)
KHÔNG suy ra từ so sánh prev_tag với node cặp (cách đó chỉ đúng khi 2 node
liền kề — đã thử và SAI trong thực tế, khiến không bao giờ phát hiện được lúc
xe thoát ra để đóng cửa). Thay vào đó, theo dõi TRỰC TIẾP theo từng xe: xe đã
"vào" cửa từ node nào — lần đến node CÒN LẠI tiếp theo (bất kể đi qua bao
nhiêu node ở giữa) chính là lúc "ra" cửa.

  - Xe tới 1 trong 2 node của cửa, và HIỆN CHƯA được ghi nhận đang ở giữa cửa
    → ĐANG TIẾN VÀO cửa → xin MỞ, xe đứng chờ tới khi cửa xác nhận mở xong.
    Ghi nhớ xe đã vào từ node nào.
  - Xe tới node CÒN LẠI của cùng cửa, trong khi ĐANG được ghi nhận đang ở giữa
    cửa (đã vào từ node kia) → ĐÃ QUA cửa → báo cửa có thể đóng (chỉ đóng thật
    khi không còn xe nào khác đang qua).

Xem PROTOCOL_GUIDE.md mục "Cửa tự động (Gate Controller)" để biết giao thức
MQTT đầy đủ giữa server và bộ điều khiển cửa (dành cho đội firmware).

Giao thức bên trong module này với line_agv_handler.py / main.py:
  - is_exit_arrival(door_id, agv_id, node): dùng ở CẢ lúc lập kế hoạch dispatch
    (main.py — quyết định có cần tách route dừng lại hay không) LẪN lúc xe
    thực sự tới node (line_agv_handler.py) — chỉ ĐỌC trạng thái, không thay đổi
    gì, nên gọi bao nhiêu lần cũng an toàn.
  - request_open(door_id, agv_id, node): gọi khi xe TỚI node cửa theo chiều
    TIẾN VÀO, xe đã dừng hẳn (WAIT_SYS/WAIT_USER) chờ được cho đi tiếp. Ghi
    nhớ node đã vào.
  - notify_exit(door_id, agv_id): gọi khi xe tới node CÒN LẠI (đã xác nhận qua
    is_exit_arrival) — KHÔNG cần xe dừng, chạy nền.
  - check_retries(): gọi định kỳ (mỗi state message bất kỳ AGV nào) để phát
    hiện timeout chờ xác nhận mở cửa và tự gửi lại — áp dụng đúng bài học từ
    lỗi nâng móc không phản hồi (xem HOOK_RAISE_TIMEOUT ở line_agv_handler.py).
"""
import time
from dataclasses import dataclass, field

DOOR_OPEN_TIMEOUT      = 6.0   # giây chờ xác nhận MỞ trước khi gửi lại
DOOR_OPEN_MAX_RETRIES  = 2     # số lần gửi lại tối đa trước khi bỏ cuộc tự động


def find_paired_door_node(node_actions: dict, door_id: str, exclude_node: str) -> str | None:
    """Tìm node CÒN LẠI của cùng 1 cửa (cùng door_id, khác node hiện tại).
    Chỉ dùng cho mục đích tham khảo/log — KHÔNG dùng để suy luận chiều vào/ra
    (xem docstring module — 2 node cửa có thể không liền kề)."""
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
    entry_node:   dict  = field(default_factory=dict)  # agv_id -> node đã VÀO cửa từ đó
    open_sent_at: float = 0.0
    open_retries: int   = 0


class DoorCoordinator:
    def __init__(self):
        self._doors: dict[str, _DoorInfo] = {}

    def _get(self, door_id: str) -> _DoorInfo:
        if door_id not in self._doors:
            self._doors[door_id] = _DoorInfo()
        return self._doors[door_id]

    # ── Xác định chiều: xe đang VÀO hay ĐÃ RA (chỉ đọc, không đổi trạng thái) ──
    def is_exit_arrival(self, door_id: str, agv_id: str, node: str) -> bool:
        """True nếu xe này đã ghi nhận ĐANG ở giữa cửa (đã vào từ 1 node KHÁC
        node hiện tại) — tức đây là lượt THOÁT RA, không phải lượt vào mới.
        Dùng được ở CẢ dispatch-time (main.py, quyết định có tách route dừng
        hay không) lẫn arrival-time (line_agv_handler.py)."""
        info = self._doors.get(door_id)
        if not info:
            return False
        entry = info.entry_node.get(agv_id)
        return entry is not None and str(entry) != str(node)

    # ── Xe TIẾN VÀO cửa ──────────────────────────────────────────────────────
    def request_open(self, door_id: str, agv_id: str, node: str) -> None:
        info = self._get(door_id)
        info.in_transit.add(agv_id)
        info.entry_node[agv_id] = str(node)
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

    # ── Xe ĐÃ RA cửa (không cần dừng) ─────────────────────────────────────────
    def notify_exit(self, door_id: str, agv_id: str) -> None:
        info = self._get(door_id)
        info.in_transit.discard(agv_id)
        info.waiting.discard(agv_id)
        info.entry_node.pop(agv_id, None)
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
            from agv_registry import agv_registry
            if agv_registry.is_line(agv_id):
                from line_agv_handler import line_agv_handler
                line_agv_handler.resume_after_door(agv_id)
            else:
                # VDA5050: node cửa luôn là đích cuối của 1 chặng riêng (xem
                # _dispatch_go_to trong main.py — đã TÁCH route tại node cửa VÀ
                # đánh dấu pending_confirm_node = node cửa đó, để nhánh paused=True
                # trong mqtt_client.py KHÔNG tự auto-complete ngay khi xe hết node
                # released — phải đúng lúc cửa xác nhận mở, tức NGAY ĐÂY, mới coi
                # chặng này xong và cho task_queue dispatch tiếp lệnh kế (đích gốc
                # đã insert_next lúc tách route).
                from mqtt_client import agv_manager
                agv_manager.set_pending_confirm(agv_id, None)
                from task_queue import agv_task_queue
                agv_task_queue.on_agv_completed(agv_id, notes="door_opened")
        except Exception as e:
            print(f"[DOOR] resume {agv_id} lỗi: {e}")


door_coordinator = DoorCoordinator()
