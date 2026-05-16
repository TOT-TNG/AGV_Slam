import json
import time
import os
import datetime
import math
import uuid
from log_mgmt.system_logger import sys_log, LOG_MQTT_OUT, LOG_SYSTEM, LOG_WARN, LOG_ERROR, LOG_DISPATCH

# Action Codes (Khớp với Arduino)
ACT_WAIT_SYS = 1
ACT_WAIT_USER = 2
ACT_RUN = 3
ACT_SPEED = 4
ACT_TURN_R = 5
ACT_TURN_L = 6
ACT_DIR_FWD   = 7   # Đặt chiều TIẾN
ACT_DIR_BWD   = 8   # Đặt chiều LÙI
ACT_ROTATE_1  = 9   # Quay 180° (đường thẳng, 1 lần)
ACT_LIDAR_OFF = 20  # Tắt cảm biến vật cản (lidar_bank1) — dùng trước khi quay/lùi
ACT_LIDAR_ON  = 21  # Bật cảm biến vật cản (lidar_bank0) — dùng sau khi quay xong
ACT_NHAC_START    = 22  # Phát nhạc khởi động
ACT_NHAC_STOP     = 23  # Dừng nhạc
ACT_NHAC_XIN_LIEU = 24  # Nhạc xin cấp liệu
ACT_NHAC_MO_CUA   = 25  # Nhạc mở cửa
ACT_NHAC_XIN_RE   = 26  # Nhạc xin rẽ
ACT_NHAC_TAT      = 27  # Tắt nhạc
ACT_BRAKE_ON      = 28  # Đóng phanh (dongthang)
ACT_BRAKE_OFF     = 29  # Mở phanh (mothang)
ACT_HOOK_RAISE    = 30  # Nâng móc hàng (stub)
ACT_HOOK_LOWER    = 31  # Hạ móc hàng (stub)
ACT_DEN_VANG      = 32  # Bật đèn vàng
ACT_DEN_XANH      = 33  # Bật đèn xanh
ACT_DEN_TAT       = 34  # Tắt đèn
ACT_WAIT_CHARGE   = 35  # Đến trạm sạc: đèn vàng + bật cảm biến phát, không bấm loa

# System Action Names (Mặc định, không xóa được)
SYSTEM_ACTIONS = {
    0: "0 - No Action / Normal",
    1: "1 - Wait System (Traffic)",
    2: "2 - Wait User (Confirm)",
    3: "3 - Run (Forward)",
    4: "4 - Change Speed",
    5: "5 - Turn Right",
    6: "6 - Turn Left",
    7: "7 - Reverse (Backwards)",
    8: "8 - Rotate 180 (Smart/Auto)",
    9: "9 - Rotate 180 (Force 2-Steps)",
    11: "11 - Charge Start (Auto)",
    20: "20 - Lidar OFF (bank1)",
    21: "21 - Lidar ON (bank0)",
    22: "22 - Nhạc: Khởi động",
    23: "23 - Nhạc: Dừng",
    24: "24 - Nhạc: Xin cấp liệu",
    25: "25 - Nhạc: Mở cửa",
    26: "26 - Nhạc: Xin rẽ",
    27: "27 - Nhạc: Tắt",
    28: "28 - Phanh: Đóng (Brake ON)",
    29: "29 - Phanh: Mở (Brake OFF)",
    30: "30 - Móc: Nâng lên",
    31: "31 - Móc: Hạ xuống",
    32: "32 - Đèn: Vàng",
    33: "33 - Đèn: Xanh",
    34: "34 - Đèn: Tắt",
}

# Human-readable action names dùng trong log / debug print
ACTION_NAMES = {
    1:  "WAIT_SYS",    2:  "WAIT_USER",
    3:  "RUN",         4:  "SPEED",
    5:  "TURN_R",      6:  "TURN_L",
    7:  "DIR_FWD",     8:  "DIR_BWD",
    9:  "ROTATE_180",
    20: "LIDAR_OFF",   21: "LIDAR_ON",
    22: "NHAC_START",  23: "NHAC_STOP",
    24: "NHAC_XIN_LIEU", 25: "NHAC_MO_CUA",
    26: "NHAC_XIN_RE", 27: "NHAC_TAT",
    28: "BRAKE_ON",    29: "BRAKE_OFF",
    30: "HOOK_RAISE",  31: "HOOK_LOWER",
    32: "DEN_VANG",    33: "DEN_XANH",   34: "DEN_TAT",
}

# Error Codes Mapping
ERROR_MAP = {
    0: "Normal",
    1: "Low Battery",
    2: "Motor Fault",
    3: "Line Lost (Derail)",
    4: "Obstacle Detected (Blocked)",
    5: "Emergency Stop Pressed"
}

# ── Hàm dùng chung cho cả AGV runtime và SimulationEngine ─────────────────────

def _node_disp_xy(node_attrs):
    """Trả về (x, y) hiển thị của node: ưu tiên disp_x/disp_y, fallback về x/y.
    Đồng bộ với logic _disp_xy() trong map_widget.py."""
    return (node_attrs.get('disp_x', node_attrs.get('x', 0)),
            node_attrs.get('disp_y', node_attrs.get('y', 0)))


def calc_turn_angle(g, n1, n2, n3):
    """Tính góc cua (°) tại n2 theo hướng n1→n2→n3.
    Trả về 180 = đi thẳng, 90 = vuông góc, 0 = quay đầu hoàn toàn.
    Dùng tọa độ hiển thị (disp_x/disp_y nếu có, không thì x/y)."""
    try:
        if not (g.has_node(n1) and g.has_node(n2) and g.has_node(n3)):
            return 180
        x1, y1 = _node_disp_xy(g.nodes[n1])
        x2, y2 = _node_disp_xy(g.nodes[n2])
        x3, y3 = _node_disp_xy(g.nodes[n3])
        v1x, v1y = x2 - x1, y2 - y1
        v2x, v2y = x3 - x2, y3 - y2
        a1 = math.atan2(v1y, v1x)
        a2 = math.atan2(v2y, v2x)
        deg = math.degrees(abs(a1 - a2))
        if deg > 180:
            deg = 360 - deg
        return 180 - deg
    except Exception:
        return 180


def auto_nav_action(g, prev_node, curr_node, next_node, _debug=False):
    """Xác định hướng rẽ tại curr_node từ tọa độ sơ đồ (dùng chung).

    Dùng disp_x/disp_y (tọa độ hiển thị, y tăng XUỐNG) ưu tiên hơn x/y vật lý.
    Lý do: x/y vật lý có thể không phản ánh layout hình học thực trên sơ đồ
    (ví dụ các node đã được kéo thả để sắp xếp lại trên màn hình).

    Cross product (tọa độ màn hình, y tăng XUỐNG):
      cross > 0 → clockwise → rẽ PHẢI (TURN_R)
      cross < 0 → counter-clockwise → rẽ TRÁI (TURN_L)
    """
    try:
        if not (g.has_node(prev_node) and g.has_node(curr_node) and g.has_node(next_node)):
            return ACT_RUN
        x1, y1 = _node_disp_xy(g.nodes[prev_node])
        x2, y2 = _node_disp_xy(g.nodes[curr_node])
        x3, y3 = _node_disp_xy(g.nodes[next_node])
        v1x, v1y = x2 - x1, y2 - y1
        v2x, v2y = x3 - x2, y3 - y2
        a1 = math.atan2(v1y, v1x)
        a2 = math.atan2(v2y, v2x)
        diff = math.degrees(abs(a1 - a2))
        if diff > 180:
            diff = 360 - diff
        turn_angle = 180 - diff
        if turn_angle >= 150:
            if _debug:
                print(f"[NAV-AUTO] {prev_node}→{curr_node}→{next_node}: thẳng "
                      f"(góc={turn_angle:.1f}°) v1=({v1x:.2f},{v1y:.2f}) v2=({v2x:.2f},{v2y:.2f})")
            return ACT_RUN
        cross = v1x * v2y - v1y * v2x
        result = ACT_TURN_R if cross > 0 else ACT_TURN_L
        if _debug:
            direction = "TURN_R" if result == ACT_TURN_R else "TURN_L"
            print(f"[NAV-AUTO] {prev_node}→{curr_node}→{next_node}: {direction} "
                  f"góc={turn_angle:.1f}° cross={cross:.3f} "
                  f"disp1=({x1:.1f},{y1:.1f}) disp2=({x2:.1f},{y2:.1f}) disp3=({x3:.1f},{y3:.1f})")
        return result
    except Exception:
        return ACT_RUN


class AGV:
    def __init__(self, config, mqtt_client):
        self.id = config['id']
        self.app_config  = {} # Config toàn cục, sẽ được gán từ Main
        self.ip          = config.get('ip', '0.0.0.0')
        self.color       = config.get('color', '#3498db')
        # Khả năng đi lùi: False = AGV chỉ đi tiến (không hỗ trợ reverse)
        self.can_reverse = bool(config.get('can_reverse', True))
        # Topics VDA5050 v2.0.0: uagv/v2/{manufacturer}/{serialNumber}/{topicName}
        # ưu tiên topic_pub/topic_sub từ config (nhập tay) nếu có
        factory  = config.get('factory',  'default')
        hardware = config.get('hardware', 'hardware')
        self.mac_address = ''
        self._factory  = factory
        self._hardware = hardware
        # AGV → FMS
        self.topic_state = (config.get('topic_pub')
                            or f"uagv/v2/{factory}/{self.id}/state")
        # FMS → AGV: lộ trình (order) và lệnh tức thì (instantActions) tách riêng
        self.topic_order   = (config.get('topic_sub')
                              or f"uagv/v2/{factory}/{self.id}/order")
        self.topic_instant = (config.get('topic_instant')
                              or f"uagv/v2/{factory}/{self.id}/instantActions")
        # Kết nối (AGV → FMS, theo dõi ONLINE/OFFLINE)
        self.topic_conn    = f"uagv/v2/{factory}/{self.id}/connection"
        self.mqtt = mqtt_client
        
        # Trạng thái
        self.current_tag = 0
        self.prev_tag = 0       # Thẻ trước đó — dùng để tính hướng đầu AGV
        self.status = "unknown" # auto/manual
        self.action_info = "idle"
        self.pending_request = None # Lưu yêu cầu từ nút bấm (return, confirm...)
        self.selected_targets = []  # Lưu danh sách tổ người dùng chọn (Point 4)
        self.last_update = 0
        self.error_code = 0
        self.last_move_time = time.time()
        self.battery = 0
        self.battery_low      = False   # Tín hiệu cảm biến: True khi PIN_PIN_YEU==HIGH
        self.battery_blocking = False   # True khi pin yếu + hành trình xong → chờ sạc
        self._charge_start_time = None  # Thời điểm AGV về trạm sạc với battery_blocking
        self.CHARGE_MIN_SECONDS = 7200  # Thời gian sạc tối thiểu trước khi unlock (2h)
        self.rssi = 0
        self.connected = False
        # VDA5050 State fields (cập nhật từ bản tin state)
        self.vda_header_id    = 0
        self.vda_timestamp    = ''
        self.vda_order_id     = ''
        self.operating_mode   = 'MANUAL'   # AUTOMATIC / SEMIAUTOMATIC / MANUAL
        self.driving          = False
        self.paused           = False
        self.node_states      = []         # Danh sách node còn lại trong plan
        self.safety_state     = {}         # {eStop, fieldViolation}
        self.vda_errors       = []         # Mảng lỗi VDA5050 [{errorType,...}]
        self.connection_state = 'OFFLINE'  # ONLINE / OFFLINE / CONNECTIONBROKEN
        
        # Navigation Logic
        self.full_path = [] # Đường đi đầy đủ từ A -> B
        self.lookahead = 6  # Số thẻ gửi trước — đủ để Arduino biết turn 2-3 thẻ trước
        self.is_navigating = False
        self.speed_overrides = {} # {node_id: speed_value}
        self.current_task_type = "idle" # idle, pickup, delivery, return
        self.task_lifecycle = "free" # free, assigned, picking, delivering, returning
        self.last_sent_cmd_id = None # ID của lệnh gửi đi gần nhất
        self._last_segment_nodes = []  # Segment cuối gửi (dùng cho retry)
        self._last_sent_time = 0       # Thời điểm gửi (dùng cho retry)
        self._start_direction = 7      # ACT_DIR_FWD mặc định
        self._current_dir     = 7      # Chiều hiện tại (theo dõi qua các segment)
        self.post_homing_action = None # Lưu hành động cần làm sau khi tìm thấy vị trí (VD: "return")
        self.blocked_start_time = None # Thời điểm bắt đầu bị kẹt giao thông

        # Zone Manager integration (được inject từ main.py)
        self.zone_mgr = None               # Tham chiếu đến ZoneManager (tuỳ chọn)
        self.zone_waiting = False          # Đang chờ zone token
        self._zone_waiting_segment = []    # Segment cần gửi khi zone được giải phóng

        # Rolling Re-plan integration (được inject từ main.py)
        # Callable(agv) → None : gọi ngay khi AGV đến thẻ mới, có thể cập nhật full_path
        self.on_tag_reached_hook = None

        # Rotation animation callback (được inject từ main.py)
        # Callable(agv_id, at_tag, next_tag, duration_sec) → kích hoạt animation quay trên bản đồ
        self.on_init_turn_anim_cb = None

        # Edge conflict hold (set bởi traffic loop khi phát hiện cạnh ngược chiều)
        self.edge_hold = False
        self._edge_hold_segment = []       # Segment giữ lại trong khi chờ cạnh thông

        # WHCA* Planner integration (cờ do traffic loop set, AGV chỉ đọc)
        self.whca_hold = False             # Traffic loop yêu cầu dừng proactive
        self.whca_waiting = False          # Đang chờ WHCA* giải phóng
        self._whca_pending_segment = []    # Segment bị treo do WHCA* hold

        # Forward-first return: khi route về trạm cần tiến đến điểm tiếp cận trước
        self._pre_return_charger = None  # Charger sẽ dispatch sau khi AGV tiến đến approach_node

        # Delivery queue: danh sách tổ còn cần giao (quản lý bởi run_hmi_handler)
        self._remaining_delivery_teams = []  # [team_id, ...] còn chờ giao
        self._current_delivery_team = None   # Tổ đang giao hiện tại (set bởi _dispatch_next_team)

        # Pickup/mission tracking: lưu đích đến để định tuyến lại khi off-route
        self._pickup_target_node = None  # Wait-node đang di chuyển đến (lifecycle=picking)
        self._mission_dest_node  = None  # Đích cuối của nhiệm vụ hiện tại (mọi lifecycle)

        # Bypass slot waiting (set bởi traffic loop)
        self.bypass_holding  = False   # Đang chờ trong bypass slot
        self.bypass_dest     = None    # Đích gốc trước khi vào bypass
        self.bypass_zone_id  = None    # Zone chứa slot đang đứng

        # Door Check Gate (Gate 3) — inject từ main.py
        # {tag_id: [list_of_door_configs]}  (1 tag có thể có 2 chiều)
        self._door_check_map = {}
        self.door_hold = False             # Đang chờ cửa mở
        self._door_hold_segment = []       # Segment giữ lại trong khi chờ cửa

        # Edge Reservation (Gate 0.5) — inject từ main.py
        self.edge_mgr = None               # EdgeReservationManager (tuỳ chọn)

        # Reverse-and-reroute state
        # Khi _reversing_to != 0: AGV đang lùi về node này.
        # update_state() sẽ bỏ qua navigation bình thường cho đến khi đến đích lùi.
        self._reversing_to: int = 0
        
        # Statistics
        self.stats = {
            "trips": 0,
            "total_time": 0,
            "start_time": time.time()
        }
        
        # Plan log — lưu plan_data gần nhất để hiển thị trong monitor
        self.last_plan_data   = []  # [{"t":tag,"a":action,"v":value}, ...]
        self.last_plan_nodes  = []  # segment_nodes gần nhất
        self.full_plan_data   = []  # Toàn bộ plan qua các segment của nhiệm vụ hiện tại

        # Heading vector khi dispatch thủ công (None = dùng prev_tag thay thế)
        self._start_heading   = None  # (hx, hy) unit vector, set từ btn_dispatch_click
        # Flag cho map_widget: xóa _manual_angles sau khi chuyến lùi về trạm kết thúc
        self._clear_heading_flag = False

        # Precomputed plan từ SimulationEngine.dry_run() — đảm bảo lệnh MQTT == simulation
        # Được set từ main.py trước khi gọi set_path (hoặc qua tham số precomp_steps)
        self._precomp_steps   = None  # list steps từ dry_run
        self._precomp_path    = None  # full_path tương ứng

        # Logging setup
        self.log_file = "logs/activity_log.csv"
        self.ensure_log_header()

    def update_state(self, payload):
        """Xử lý dữ liệu JSON VDA5050 từ ESP32 gửi lên"""
        try:
            data = json.loads(payload)

            # ── VDA5050 mandatory header ──────────────────────────────────────
            self.vda_header_id = data.get('headerId', 0)
            self.vda_timestamp = data.get('timestamp', '')

            # ── Vị trí: lastNodeId (VDA5050) = tag (backward compat) ─────────
            # tag là int (RFID), lastNodeId là string → parse cả hai
            last_node_str = data.get('lastNodeId', '')
            new_tag = int(last_node_str) if last_node_str.isdigit() else data.get('tag', 0)
            if self.current_tag != new_tag:
                self.last_move_time = time.time()
                # Nhả reservation cạnh vừa hoàn thành: prev→current (đã đến đích)
                if self.edge_mgr and self.current_tag and new_tag:
                    self.edge_mgr.release(self.id, self.current_tag, new_tag)
                self.prev_tag = self.current_tag
            self.current_tag = new_tag

            # Kiểm tra hoàn thành lùi về node: nếu đang lùi và đã đến đích lùi
            if self._reversing_to and new_tag == self._reversing_to:
                self._reversing_to = 0
                self._last_navigated_tag = None   # buộc gửi segment tiếp theo
                print(f"[REVERSE DONE] {self.id}: về {new_tag}, tiếp tục path mới")

            # Phục hồi prev_tag từ firmware sau khi Python restart
            firmware_prev = int(data.get('prev_tag', 0))
            if self.prev_tag == 0 and firmware_prev > 0 and firmware_prev != new_tag:
                self.prev_tag = firmware_prev
                print(f"[{self.id}] Recovered prev_tag={firmware_prev} from firmware (after restart)")

            # ── VDA5050 operating mode / driving / paused ────────────────────
            self.operating_mode = data.get('operatingMode', 'MANUAL')
            self.driving        = bool(data.get('driving', False))
            self.paused         = bool(data.get('paused',  False))
            self.vda_order_id   = data.get('orderId', '')
            self.node_states    = data.get('nodeStates', [])
            self.safety_state   = data.get('safetyState', {})
            self.vda_errors     = data.get('errors', [])

            # ── Backward-compat fields ────────────────────────────────────────
            self.status      = data.get('status', 'unknown')   # "auto"/"manual"
            self.action_info = data.get('action_info', 'idle')
            err_raw          = data.get('error', 0)
            self.error_code  = int(err_raw) if (err_raw != '' and err_raw is not None) else 0
            self.rssi        = data.get('rssi', 0)

            # ── Battery state ─────────────────────────────────────────────────
            # Backward-compat field (Arduino gửi trực tiếp)
            if 'battery_low' in data:
                self.battery_low = bool(data['battery_low'])
            # VDA5050 batteryState object (nếu có)
            batt_state = data.get('batteryState', {})
            if batt_state:
                charge = batt_state.get('batteryCharge', None)
                if charge is not None:
                    self.battery     = int(charge)
                    self.battery_low = charge <= 25

            # battery_blocking: Arduino báo hành trình xong + pin yếu → cần về sạc
            new_blocking = bool(data.get('battery_blocking', False))
            if new_blocking and not self.battery_blocking:
                # Vừa chuyển sang trạng thái blocking
                print(f"[{self.id}] ⚠ Pin yếu + hành trình xong → chờ điều về trạm sạc")
            self.battery_blocking = new_blocking

            # Sự kiện battery_need_charge: Arduino xác nhận đang ở trạng thái chặn
            if data.get('event') == 'battery_need_charge':
                self.battery_blocking = True
                print(f"[{self.id}] ⚠ AGV từ chối lệnh: pin yếu, cần điều về trạm sạc")

            # Lưu MAC từ ESP32 (thông tin tham khảo, hiển thị trong Settings)
            incoming_mac = data.get('mac', '')
            if incoming_mac:
                self.mac_address = incoming_mac
            
            # 1. Xử lý ACK từ AGV (AGV xác nhận đã nhận lệnh điều phối)
            if 'ack' in data and data['ack'] == self.last_sent_cmd_id:
                # print(f"AGV {self.id} ACKED command {self.last_sent_cmd_id}")
                self.last_sent_cmd_id = None # Reset sau khi đã confirm

            # RETRY: Nếu ACK chưa về sau 4 giây → gửi lại segment (tránh mất gói MQTT)
            # Chỉ retry khi đang điều hướng (is_navigating=True) để tránh retry sau khi chuyến xong
            # KHÔNG retry nếu AGV đang đứng ở tag đầu của plan → plan đã được nhận (tránh TURN 2 lần)
            RETRY_TIMEOUT = 4.0
            _seg = getattr(self, '_last_segment_nodes', [])
            _at_plan_start = bool(_seg) and self.current_tag == _seg[0]
            if (self.last_sent_cmd_id is not None
                    and self.is_navigating
                    and not _at_plan_start
                    and hasattr(self, '_last_sent_time')
                    and hasattr(self, '_last_segment_nodes')
                    and (time.time() - self._last_sent_time) > RETRY_TIMEOUT):
                print(f"RETRY: AGV {self.id} did not ACK in {RETRY_TIMEOUT}s. Resending segment.")
                self._send_segment(self._last_segment_nodes)

            # Xử lý sự kiện nút bấm hoặc xác nhận từ AGV gửi lên
            # Format mong đợi: {"event": "confirm", "targets": [1, 4]} hoặc {"event": "return"}
            if 'event' in data:
                event_name = data['event']
                self.send_server_ack(event_name)  # ACK ngay để Arduino xóa pendingEvent (không gửi lặp)
                # Chỉ ghi đè pending_request khi chưa có event nào đang chờ xử lý,
                # hoặc khi event mới khác event cũ (tránh mất "return" vừa được set bởi handler)
                if self.pending_request is None or self.pending_request == event_name:
                    self.pending_request = event_name
                    self.selected_targets = data.get('targets', [])

            self.last_update = time.time()
            self.connected = True
            
            # Logic tự động gửi tiếp đường đi khi AGV di chuyển
            # Chỉ gửi khi AGV tiến đến thẻ MỚI — tránh gửi lặp mỗi 500ms khi xe đứng yên
            # Đang trong quá trình lùi: không gửi segment navigation mới
            if self._reversing_to:
                return

            if self.is_navigating and self.current_tag in self.full_path:
                if self.current_tag != getattr(self, '_last_navigated_tag', None):
                    self._last_navigated_tag = self.current_tag
                    # Cập nhật _current_dir từ plan_data tại thẻ vừa đến
                    # (cần trước _check_turn_anim để start_auto_rotation biết chiều lùi/tiến)
                    for _step in self.full_plan_data:
                        if _step.get('t') == self.current_tag:
                            _a = _step.get('a', 0)
                            if _a == ACT_DIR_BWD:
                                self._current_dir = ACT_DIR_BWD
                            elif _a == ACT_DIR_FWD:
                                self._current_dir = ACT_DIR_FWD
                    # Animation quay khi AGV đến thẻ có lệnh TURN
                    self._check_turn_anim()
                    try:
                        idx = self.full_path.index(self.current_tag)
                        # Nếu đã đến đích
                        if idx == len(self.full_path) - 1:
                            self.is_navigating = False
                            self._reversing_to = 0
                            if self.edge_mgr:
                                self.edge_mgr.release_all(self.id)
                            self.stats["trips"] += 1
                            self.log_trip_finish()
                            # Khi kết thúc chuyến lùi về trạm: xóa turn animation angle
                            # để map_widget dùng prev_tag→current_tag+flip hiển thị hướng đúng
                            if self.current_task_type == "return_reversing_charge":
                                self._clear_heading_flag = True
                            print(f"{self.id} finished trip.")
                        else:
                            # ── Rolling Re-plan: tính lại path tại mỗi thẻ ──
                            # Hook được inject từ main.py; có thể cập nhật self.full_path
                            if self.on_tag_reached_hook:
                                try:
                                    self.on_tag_reached_hook(self)
                                    # Nếu path thay đổi, cập nhật idx theo path mới
                                    if self.current_tag in self.full_path:
                                        idx = self.full_path.index(self.current_tag)
                                    else:
                                        raise ValueError("current_tag not in new path")
                                except Exception:
                                    pass  # Hook lỗi → dùng path cũ, không crash

                            # Gửi tiếp đoạn đường tiếp theo (Windowed)
                            # Guard: chỉ gửi plan mới khi AGV gần cuối plan hiện tại.
                            # Nếu plan vừa gửi còn đủ coverage (idx < last_end - 1),
                            # KHÔNG gửi lại — tránh gửi TURN_L 2 lần khi turn nằm giữa plan.
                            _last_end = getattr(self, '_last_plan_end_idx', 0)
                            # Cập nhật nếu full_path bị rút ngắn sau re-plan
                            if _last_end >= len(self.full_path):
                                _last_end = len(self.full_path) - 1
                            if idx >= _last_end - 1:
                                # Roll plan từ thẻ HIỆN TẠI (idx) — KHÔNG phải idx+1.
                                # Lý do: firmware diễn giải phần tử ĐẦU TIÊN của plan là "vị trí hiện tại".
                                # Nếu plan bắt đầu tại idx+1 (thẻ tiếp theo chưa đến), firmware xử lý
                                # tất cả action trong plan ngay lập tức (kể cả DIR_BWD ở thẻ cuối) → xe lùi sớm.
                                # Bắt đầu từ idx (thẻ hiện tại) để firmware biết context đúng.
                                # Duplicate TURN tại currentTag được xử lý bởi Arduino lastTurnTag guard.
                                roll_start = idx
                                next_segment = self.full_path[roll_start: roll_start + 1 + self.lookahead]
                                if len(next_segment) > 1:
                                    # Cập nhật coverage index trước khi gửi
                                    # +1 vì plan bắt từ idx (currentTag) nên slot cuối là idx+lookahead
                                    self._last_plan_end_idx = min(
                                        roll_start + 1 + self.lookahead, len(self.full_path) - 1)
                                    # ── Gate 0: Edge Conflict Hold ────────────────
                                    if self.edge_hold:
                                        self._edge_hold_segment = next_segment
                                        self._send_hold()
                                    # ── Gate 0.5: Edge Reservation (head-on chặn trước) ──
                                    elif (self.edge_mgr
                                            and len(next_segment) >= 2
                                            and self.edge_mgr.is_blocked(
                                                next_segment[0], next_segment[1], self.id)[0]):
                                        # Cạnh ngược chiều đang bị AGV khác chiếm → giữ tại chỗ
                                        blocker = self.edge_mgr.is_blocked(
                                            next_segment[0], next_segment[1], self.id)[1]
                                        print(f"[EDGE_RES] {self.id}: edge "
                                              f"{next_segment[0]}→{next_segment[1]} "
                                              f"blocked by {blocker} — holding")
                                        self._edge_hold_segment = next_segment
                                        self._send_hold()
                                    # ── Gate 1: Zone Manager ──────────────────────
                                    elif (self.zone_mgr and
                                            not self.zone_mgr.request_passage(
                                                self.id, next_segment[1:], self.current_task_type)):
                                        self.zone_waiting = True
                                        self._zone_waiting_segment = next_segment
                                        self._send_hold()
                                    # ── Gate 2: WHCA* Proactive Hold ──────────────
                                    elif self.whca_hold:
                                        self.whca_waiting = True
                                        self._whca_pending_segment = next_segment
                                        self._send_hold()
                                    # ── Gate 3: Door Check ────────────────────────
                                    elif self._is_door_check():
                                        self._door_hold_segment = next_segment
                                        self.door_hold = True
                                        self._send_hold()
                                        self._send_door_check_cmd()
                                    else:
                                        self.zone_waiting = False
                                        self.whca_waiting = False
                                        self._send_segment(next_segment)
                    except ValueError:
                        pass
                    
        except Exception as e:
            print(f"Error parsing AGV {self.id} state: {e}")

    def set_path(self, path_nodes, graph, task_type="delivery", start_heading=None,
                 precomp_steps=None):
        """Nhận đường đi tổng thể và bắt đầu gửi đoạn đầu tiên.

        precomp_steps : kết quả dry_run từ SimulationEngine (list steps).
                        Nếu có, _send_segment sẽ dùng precomp thay vì tính toán thủ công
                        → lệnh MQTT khớp chính xác với simulation.
        """
        # Chặn điều phối khi đang trong trạng thái chờ sạc
        # (battery_blocking = True chỉ khi: hành trình xong + pin yếu → về trạm sạc)
        # Khi xe đang chạy dở (battery_low nhưng !battery_blocking): vẫn cho phép dispatch tiếp theo
        if self.battery_blocking:
            print(f"[{self.id}] ⚠ Từ chối điều phối: đang chờ sạc pin "
                  f"(battery_blocking=True). Python sẽ tự gửi battery_unlock sau 2h.")
            return

        # Đọc lookahead từ app_config (người dùng có thể thay đổi qua Settings)
        self.lookahead = int(self.app_config.get('traffic', {}).get('lookahead', self.lookahead))
        self.full_path = path_nodes
        self.graph_ref = graph # Lưu tham chiếu graph để tra cứu action
        self.is_navigating = True
        self.current_task_type = task_type
        self.trip_start_time = time.time()
        # Lưu ý: task_lifecycle sẽ được set ở main.py để quản lý logic nghiệp vụ

        # Xác định chiều di chuyển ban đầu — gửi lệnh đổi chiều ngay ở đầu path
        # return_reversing_charge: AGV lùi vào trạm sạc → action 8 (ACT_DIR_BWD)
        # Mọi task khác: GIỮ NGUYÊN _current_dir từ task trước (chiều vật lý hiện tại của AGV)
        # → AGV vừa về trạm bằng lùi, task mới sẽ inject DIR_FWD khi cần
        if task_type == "return_reversing_charge":
            self._start_direction = ACT_DIR_BWD
            self._current_dir     = ACT_DIR_BWD
        else:
            self._start_direction = ACT_DIR_FWD
            # Reset _current_dir về FWD khi bắt đầu task tiến.
            # Tránh: task cũ (return_reversing_charge) để lại BWD → heading correction sai
            # ở task mới (vin bị đảo dấu → skip turn hoặc turn ngược).
            self._current_dir     = ACT_DIR_FWD
        self._last_navigated_tag = None  # Reset để cho phép gửi segment ngay từ đầu
        self._start_heading   = start_heading  # (hx, hy) heading từ dispatch, None = dùng prev_tag
        self.full_plan_data   = []        # Reset log toàn nhiệm vụ khi bắt đầu task mới

        # Lưu precomputed plan từ dry_run (nếu có) — đảm bảo lệnh MQTT == simulation
        if precomp_steps is not None:
            self._precomp_steps = list(precomp_steps)
            self._precomp_path  = list(path_nodes)
            print(f"[PRECOMP] {self.id}: dùng dry-run plan ({len(precomp_steps)} bước)")
        else:
            self._precomp_steps = None
            self._precomp_path  = None

        # --- AUTO SPEED LOGIC ---
        self.speed_overrides = {}
        self._lidar_off_nodes = set()  # Nodes cần tắt lidar (trước khi quay)
        # Lấy cấu hình tốc độ từ app_config (nếu có), mặc định 60/120
        traffic_cfg = self.app_config.get('traffic', {})
        SPEED_SLOW = int(traffic_cfg.get('speed_slow', 60))
        SPEED_FAST = int(traffic_cfg.get('speed_fast', 120))
        
        # Trên đoạn đi lùi vào trạm sạc: chỉ giảm tốc, không tăng tốc
        is_return_task = task_type in ("return_reversing_charge", "return_charge")

        if len(path_nodes) >= 3:
            # Danh sách các index là điểm cua
            turn_indices = []
            # Duyệt qua các bộ 3 điểm: (i-1), i, (i+1)
            for i in range(1, len(path_nodes) - 1):
                prev_n = path_nodes[i-1]
                curr_n = path_nodes[i]
                next_n = path_nodes[i+1]

                # Tính góc cua tại node i
                angle = self._calculate_angle(prev_n, curr_n, next_n)
                if angle < 150:
                    turn_indices.append(i)

            # Áp dụng quy tắc tốc độ (Point 2 & 3)
            for i in range(len(path_nodes)):
                node = path_nodes[i]

                # Rule 1: Trước mỗi thẻ quay (i+1 là cua) -> Giảm tốc + tắt lidar
                if (i + 1) in turn_indices:
                    self.speed_overrides[node] = SPEED_SLOW
                    self._lidar_off_nodes.add(node)

                # Rule 2: Sau mỗi thẻ quay (i-1 là cua) -> Tăng tốc ở thẻ hiện tại (i)
                # Bỏ qua trên đoạn return (không tăng tốc khi đi lùi vào trạm)
                # Edge speed priority (bên dưới) sẽ override SPEED_FAST nếu cạnh có p > 0
                elif (i - 1) in turn_indices and not is_return_task:
                    if node not in self.speed_overrides:
                        self.speed_overrides[node] = SPEED_FAST

        # Rule 3: Khi bắt đầu nhiệm vụ mới (không phải return) → reset tốc độ nhanh tại thẻ đầu tiên
        # (Tránh AGV khởi hành chậm nếu tốc độ trước đó trên Arduino vẫn còn từ lần tiếp cận trạm sạc)
        if not is_return_task and path_nodes:
            first_node = path_nodes[0]
            if first_node not in self.speed_overrides:
                self.speed_overrides[first_node] = SPEED_FAST

        # Edge speed priority: nếu cạnh ra từ node có p > 0, dùng p thay cho tốc độ tự động.
        # Ngoại lệ: không override SPEED_SLOW (giảm tốc trước điểm cua — ưu tiên an toàn).
        if self.graph_ref:
            for i in range(len(path_nodes)):
                node = path_nodes[i]
                if i + 1 < len(path_nodes):
                    out_e = self.graph_ref.get_edge_data(node, path_nodes[i + 1]) or {}
                    ep = int(out_e.get('p', 0))
                    if ep > 0 and self.speed_overrides.get(node) != SPEED_SLOW:
                        self.speed_overrides[node] = ep

        # Gửi đoạn đầu tiên (Gate 1: Zone → Gate 2: WHCA*)
        print(f"[SET_PATH] {self.id}: full_path={self.full_path}  lookahead={self.lookahead}  heading={self._start_heading}")
        first_segment     = self.full_path[:self.lookahead + 1]
        first_nodes_ahead = first_segment[1:]
        if (self.zone_mgr and first_nodes_ahead and
                not self.zone_mgr.request_passage(self.id, first_nodes_ahead, task_type)):
            self.zone_waiting = True
            self._zone_waiting_segment = first_segment
            self._send_hold()
        elif self.whca_hold:
            self.whca_waiting = True
            self._whca_pending_segment = first_segment
            self._send_hold()
        elif self._is_door_check():
            self._door_hold_segment = first_segment
            self.door_hold = True
            self._send_hold()
            self._send_door_check_cmd()
        else:
            self.zone_waiting = False
            self.whca_waiting = False
            self._send_segment(first_segment)
        # Track index của tag CUỐI trong plan vừa gửi.
        # Dùng để tránh gửi plan mới khi AGV đang ở giữa plan hiện tại (lookahead > 1)
        self._last_plan_end_idx = min(self.lookahead, len(self.full_path) - 1)

        # Animation quay cho node đầu tiên (AGV đang đứng tại đây)
        if self.full_path:
            self._check_turn_anim(tag=self.full_path[0])

    def _check_turn_anim(self, tag=None):
        """Kiểm tra có lệnh quay tại thẻ hiện tại (hoặc tag chỉ định) và kích hoạt animation.
        Gọi khi AGV đến thẻ mới hoặc khi vừa set_path (cho node đầu tiên).
        Duration: 90° = 7s, 180° = 14s.
        """
        if not self.on_init_turn_anim_cb:
            return
        if not self.full_plan_data or not self.full_path:
            return
        tag = tag or self.current_tag
        if not tag:
            return

        # Đếm TURN_L, TURN_R, ROTATE_180 tại thẻ này trong plan
        turn_count = 0
        has_rotate_180 = False
        for step in self.full_plan_data:
            if step.get('t') == tag:
                a = step.get('a', 0)
                if a in (ACT_TURN_L, ACT_TURN_R):
                    turn_count += 1
                elif a == 9:  # ROTATE_180
                    has_rotate_180 = True

        if turn_count == 0 and not has_rotate_180:
            return

        # Duration: 7s per 90°
        if has_rotate_180 or turn_count >= 2:
            duration = 14.0  # 180° = 2 × 7s
        else:
            duration = 7.0   # 90° = 7s

        # Tìm next_tag từ full_path
        next_tag = None
        try:
            idx = self.full_path.index(tag)
            if idx + 1 < len(self.full_path):
                next_tag = self.full_path[idx + 1]
        except ValueError:
            pass

        if next_tag is not None:
            try:
                print(f"[TURN-ANIM] {self.id} @ tag {tag}: "
                      f"{turn_count}×TURN {'+ ROTATE_180 ' if has_rotate_180 else ''}"
                      f"→ next={next_tag} dur={duration:.0f}s")
                self.on_init_turn_anim_cb(self.id, int(tag), int(next_tag), duration)
            except Exception as e:
                print(f"[TURN-ANIM] error: {e}")

    def _build_plan_from_precomp(self, segment_nodes):
        """Xây dựng plan_data từ dry-run steps đã tính trước.
        Đảm bảo lệnh MQTT khớp chính xác với simulation.
        Trả về list [{t,a,v}] hoặc None nếu không dùng được (node không có trong precomp)."""
        plan_data = []
        for seg_node in segment_nodes:
            n = int(seg_node)
            try:
                idx = self._precomp_path.index(n)
            except ValueError:
                print(f"[PRECOMP-ERR] {self.id}: node {n} không có trong precomp path → fallback")
                return None
            step = self._precomp_steps[idx]
            # Pre-nav actions (speed, lidar, direction, initial turn,...)
            for act in step['actions']:
                plan_data.append({"t": n, "a": int(act['code']), "v": int(act['value'])})
            # Nav action — override tại đích cuối
            if step['is_destination']:
                node_role = step.get('node_role', 'none')
                if node_role == 'charger':
                    nav_code = ACT_WAIT_CHARGE
                elif self.current_task_type == "delivery":
                    nav_code = ACT_WAIT_USER
                else:
                    nav_code = ACT_WAIT_SYS
            else:
                nav_code = int(step['nav_action']['code'])
            # Không override TURN_L/R ở đây — simulation engine đã tính đúng góc.
            # Firmware dùng cảm biến dò line → luôn dừng ở line 90°, không cần can thiệp.
            plan_data.append({"t": n, "a": nav_code, "v": 0})
        return plan_data

    def _send_segment(self, segment_nodes):
        """Gửi một đoạn path xuống AGV"""
        # Reserve cạnh đầu tiên của segment (prevention head-on)
        if self.edge_mgr and len(segment_nodes) >= 2:
            self.edge_mgr.reserve(self.id, segment_nodes[0], segment_nodes[1])

        plan_data = []

        # ── Ưu tiên dùng precomputed plan từ dry_run (lệnh MQTT == simulation) ──
        _pc_ok = (self._precomp_steps is not None and
                  self._precomp_path is not None and
                  list(self.full_path) == self._precomp_path)
        if not _pc_ok:
            _reasons = []
            if self._precomp_steps is None: _reasons.append("steps=None")
            if self._precomp_path is None:  _reasons.append("path=None")
            if (self._precomp_path is not None and
                    list(self.full_path) != self._precomp_path):
                _reasons.append(f"full_path({len(self.full_path)})≠precomp_path({len(self._precomp_path)})")
            if _reasons:
                print(f"[PRECOMP-SKIP] {self.id}: {', '.join(_reasons)} → dùng tính toán thủ công")
        if _pc_ok:
            _precomp_data = self._build_plan_from_precomp(segment_nodes)
            if _precomp_data is not None:
                # Gửi plan từ precomp (bỏ qua toàn bộ phần tính toán thủ công)
                cmd_id = str(uuid.uuid4())[:8]
                self.last_sent_cmd_id    = cmd_id
                self._last_segment_nodes = segment_nodes
                self._last_sent_time     = time.time()
                self.last_plan_data      = list(_precomp_data)
                self.last_plan_nodes     = list(segment_nodes)
                if self.full_plan_data and segment_nodes:
                    overlap_tag = int(segment_nodes[0])
                    while self.full_plan_data and self.full_plan_data[-1].get('t') == overlap_tag:
                        self.full_plan_data.pop()
                self.full_plan_data.extend(_precomp_data)
                payload = json.dumps({"c": "plan", "d": _precomp_data, "id": cmd_id})
                steps_str = ", ".join(
                    f"t{s['t']}:{ACTION_NAMES.get(s['a'], '#' + str(s['a']))}"
                    for s in _precomp_data
                )
                sys_log(LOG_MQTT_OUT, self.id,
                        f"PLAN(sim) → {self.topic_order}  ({len(payload)}B)  [{steps_str}]")
                self.mqtt.publish(self.topic_order, payload)
                return
            else:
                sys_log(LOG_WARN, self.id, f"PRECOMP-FAIL: _build_plan_from_precomp trả về None "
                      f"→ fallback tính toán thủ công (segment={segment_nodes})")

        # Inject hướng / quay đầu xe tại node đầu tiên của full_path
        # Chỉ inject khi gửi segment bắt đầu từ node đầu tiên của full_path
        if segment_nodes and self.full_path and segment_nodes[0] == self.full_path[0]:
            curr_n = int(segment_nodes[0])
            g_ref  = self.graph_ref if hasattr(self, 'graph_ref') else None

            # Issue 1: Phát hiện và tính toán quay đầu xe tại node xuất phát
            # Nguyên lý: dot>0.5 → thẳng; 0.5>dot>-0.5 → 90°; dot<-0.5 → 180°
            # Chiều quay: cross>0 (screen CW) → TURN_R; cross<0 → TURN_L
            init_turn_cmds = []  # list (action_code,) cần inject trước khi tiến
            _turn_skip_reason = ""
            if not g_ref:
                _turn_skip_reason = "g_ref=None"
            elif len(segment_nodes) <= 1:
                _turn_skip_reason = "segment too short"
            elif not self.prev_tag or self._start_heading is not None:
                sh = self._start_heading
                if sh is None:
                    _turn_skip_reason = "prev_tag=0 (no heading)"
                    print(f"[TURN-WARN] {self.id} @ {curr_n}: prev_tag=0 và không có start_heading "
                          f"→ BỎ QUA lệnh quay đầu. Hướng xe chưa xác định (khởi động mới/chưa di chuyển). "
                          f"AGV sẽ đi thẳng theo hướng hiện tại — kiểm tra xe quay đúng chiều trước khi dispatch!")
                else:
                    # Dùng heading vector từ dispatch để tính lệnh quay đầu
                    next_n = segment_nodes[1]
                    first_edge = g_ref.get_edge_data(curr_n, next_n) or {}
                    if first_edge.get('direction', 'forward') != 'forward':
                        _turn_skip_reason = "first edge is backward (heading)"
                    else:
                        # Dùng disp_x/disp_y (y tăng XUỐNG) để nhất quán với auto_nav_action
                        cx, cy  = _node_disp_xy(g_ref.nodes.get(curr_n, {}))
                        nx, ny  = _node_disp_xy(g_ref.nodes.get(next_n, {}))
                        vout_x  = nx - cx
                        vout_y  = ny - cy
                        mag_out = math.sqrt(vout_x**2 + vout_y**2)
                        if mag_out <= 1e-6:
                            _turn_skip_reason = "zero vout (heading)"
                        else:
                            hx, hy  = sh
                            dot_n   = (hx*vout_x + hy*vout_y) / mag_out
                            cross_v = hx*vout_y - hy*vout_x
                            all_nb  = set(g_ref.predecessors(curr_n)) | set(g_ref.successors(curr_n))
                            n_conn  = len(all_nb)
                            print(f"[TURN-CHECK heading] {self.id} @ {curr_n}: "
                                  f"h=({hx:.2f},{hy:.2f}) → {next_n}  "
                                  f"dot={dot_n:.2f} cross={cross_v:.1f} n_conn={n_conn}")
                            if dot_n >= 0.5:
                                _turn_skip_reason = f"dot={dot_n:.2f} ≥ 0.5 (thẳng, không quay)"
                            elif dot_n < -0.5:
                                # n_conn<=2: đường thẳng → ROTATE_1 (180° 1 lần)
                                # n_conn>2:  ngã rẽ     → 2×TURN_L (firmware quay qua đường nhánh)
                                # n_conn<=2 (đường thẳng/cua): 1×TURN_L = 180° (firmware rotate in-place)
                                # n_conn>2  (ngã rẽ):           2×TURN_L = 2×90° = 180°
                                init_turn_cmds = [ACT_TURN_L] if n_conn <= 2 else [ACT_TURN_L, ACT_TURN_L]
                            else:
                                init_turn_cmds = [ACT_TURN_R if cross_v > 0 else ACT_TURN_L]
                    self._start_heading = None  # Tiêu thụ xong — chỉ dùng 1 lần
            elif self.prev_tag == segment_nodes[0]:
                _turn_skip_reason = (f"prev_tag({self.prev_tag})==start_node "
                                     f"→ KHÔNG XÁC ĐỊNH ĐƯỢC HƯỚNG ĐẦU XE! "
                                     f"Hãy chọn 'Hướng đầu xe' thủ công trong giao diện dispatch.")
            elif not g_ref.has_node(self.prev_tag):
                _turn_skip_reason = (f"prev_tag({self.prev_tag}) không có trong bản đồ "
                                     f"→ KHÔNG XÁC ĐỊNH ĐƯỢC HƯỚNG ĐẦU XE! "
                                     f"Hãy chọn 'Hướng đầu xe' thủ công trong giao diện dispatch.")
            else:
                next_n = segment_nodes[1]
                first_edge = g_ref.get_edge_data(curr_n, next_n) or {}
                if first_edge.get('direction', 'forward') != 'forward':
                    _turn_skip_reason = "first edge is backward"
                else:
                    # Dùng disp_x/disp_y (y tăng XUỐNG, nhất quán với auto_nav_action)
                    # Tránh sai chiều rẽ khi raw x/y dùng tọa độ vật lý y-up
                    px, py  = _node_disp_xy(g_ref.nodes.get(self.prev_tag, {}))
                    cx, cy  = _node_disp_xy(g_ref.nodes.get(curr_n, {}))
                    nx, ny  = _node_disp_xy(g_ref.nodes.get(next_n, {}))
                    vin_x   = cx - px
                    vin_y   = cy - py
                    # Nếu AGV đến start node bằng chiều LÙI: hướng vật lý ngược với vector path
                    # → đảo dấu vin để tính đúng hướng đầu xe thực tế
                    if self._current_dir == ACT_DIR_BWD:
                        vin_x = -vin_x
                        vin_y = -vin_y
                    vout_x  = nx - cx
                    vout_y  = ny - cy
                    mag_in  = math.sqrt(vin_x**2  + vin_y**2)
                    mag_out = math.sqrt(vout_x**2 + vout_y**2)
                    if mag_in <= 1e-6 or mag_out <= 1e-6:
                        _turn_skip_reason = f"zero mag_in={mag_in:.4f} mag_out={mag_out:.4f}"
                    else:
                        dot_n   = (vin_x*vout_x + vin_y*vout_y) / (mag_in * mag_out)
                        cross_v = vin_x * vout_y - vin_y * vout_x  # screen: >0=CW=RIGHT
                        all_nb  = set(g_ref.predecessors(curr_n)) | set(g_ref.successors(curr_n))
                        n_conn  = len(all_nb)
                        print(f"[TURN-CHECK] {self.id} @ {curr_n}: prev={self.prev_tag}→{curr_n}→{next_n} "
                              f"dot={dot_n:.2f} cross={cross_v:.1f} n_conn={n_conn}")
                        if dot_n >= 0.5:
                            _turn_skip_reason = f"dot={dot_n:.2f} ≥ 0.5 (straight, no turn)"
                        elif dot_n < -0.5:  # >120° → quay 180°
                            # n_conn<=2: đường thẳng → 1×TURN_L (180° in-place)
                            # n_conn>2:  ngã rẽ     → 2×TURN_L (2×90° = 180°)
                            init_turn_cmds = [ACT_TURN_L] if n_conn <= 2 else [ACT_TURN_L, ACT_TURN_L]
                        else:  # 60°-120° → quay 90° (1 lần)
                            init_turn_cmds = [ACT_TURN_R if cross_v > 0 else ACT_TURN_L]
            if _turn_skip_reason:
                prefix = "[TURN-WARN ⚠]" if "HƯỚNG ĐẦU XE" in _turn_skip_reason else "[TURN-SKIP]"
                print(f"{prefix} {self.id} @ {curr_n}: {_turn_skip_reason}")

            if init_turn_cmds:
                all_nb = set(g_ref.predecessors(curr_n)) | set(g_ref.successors(curr_n))
                n_conn = len(all_nb)
                plan_data.append({"t": curr_n, "a": ACT_LIDAR_OFF, "v": 0})
                for act in init_turn_cmds:
                    plan_data.append({"t": curr_n, "a": act, "v": 0})
                plan_data.append({"t": curr_n, "a": ACT_LIDAR_ON, "v": 0})
                plan_data.append({"t": curr_n, "a": ACT_DIR_FWD,  "v": 0})
                self._current_dir = ACT_DIR_FWD  # Đồng bộ trạng thái — tránh inject DIR_FWD trùng ở edge loop
                turn_desc = ("180° (1×TURN_L, đường thẳng)" if len(init_turn_cmds) == 1 and init_turn_cmds[0] == ACT_TURN_L
                             else ("180° (2×TURN_L, ngã rẽ)" if len(init_turn_cmds) >= 2 else "90°"))
                print(f"[ROTATE] {self.id} @ tag {curr_n}: {turn_desc}, n_conn={n_conn}")
                # Animation quay — giờ do _check_turn_anim xử lý (gọi ở cuối set_path)
                # Giữ comment để biết vị trí cũ; không gọi callback ở đây nữa
                # (tránh trigger 2 lần với _check_turn_anim)
            else:
                dir_code = getattr(self, '_start_direction', ACT_DIR_FWD)
                self._set_direction(plan_data, curr_n, dir_code, need_stop=False)

        for i in range(len(segment_nodes)):
            node = segment_nodes[i]
            node_data = self.graph_ref.nodes[node] if hasattr(self, 'graph_ref') and self.graph_ref.has_node(node) else {}

            # 0. Edge End Actions (Nhiệm vụ khi vừa đến đích của cạnh trước)
            if i > 0:
                prev_node = segment_nodes[i-1]
                prev_edge = self.graph_ref.get_edge_data(prev_node, node) if hasattr(self, 'graph_ref') else None
                if prev_edge and 'end_actions' in prev_edge:
                    for act in prev_edge['end_actions']:
                        if isinstance(act, dict):
                            plan_data.append({"t": int(node), "a": int(act.get('a', 0)), "v": int(act.get('v', 0))})
                        else:
                            plan_data.append({"t": int(node), "a": int(act), "v": 0})

            # --- AUTO SPEED + LIDAR INJECTION ---
            if node in self.speed_overrides:
                # Nếu là node giảm tốc trước điểm quay → tắt lidar trước
                if node in getattr(self, '_lidar_off_nodes', set()):
                    plan_data.append({"t": int(node), "a": ACT_LIDAR_OFF, "v": 0})
                plan_data.append({"t": int(node), "a": 4, "v": int(self.speed_overrides[node])})

            # 1. Node Actions (Nâng, Hạ, Chờ...)
            # WAIT_SYS/WAIT_USER chỉ inject tại đích CUỐI hành trình —
            # bỏ qua khi xe đi ngang qua node chờ của tổ khác (tránh xe dừng sai điểm)
            _is_trip_end = bool(self.full_path) and (node == self.full_path[-1])
            node_actions = node_data.get('actions', [])
            if node_actions:
                for act_code in node_actions:
                    if isinstance(act_code, dict):
                        _a = int(act_code.get('a', 0))
                        _v = int(act_code.get('v', 0))
                    else:
                        _a = int(act_code)
                        _v = 0
                    if _a in (ACT_WAIT_SYS, ACT_WAIT_USER) and not _is_trip_end:
                        continue  # bỏ qua lệnh chờ tại node trung gian
                    plan_data.append({"t": int(node), "a": _a, "v": _v})

            # 2. Edge Start Actions & Navigation
            nav_action = ACT_RUN
            value = 0

            if i < len(segment_nodes) - 1:
                next_node = segment_nodes[i+1]
                edge_data = self.graph_ref.get_edge_data(node, next_node) if hasattr(self, 'graph_ref') else None

                if edge_data:
                    # 2a. Edge Start Actions
                    if 'actions' in edge_data:
                        for act in edge_data['actions']:
                            if isinstance(act, dict):
                                plan_data.append({"t": int(node), "a": int(act.get('a', 0)), "v": int(act.get('v', 0))})
                            else:
                                plan_data.append({"t": int(node), "a": int(act), "v": 0})

                    # 2b-pre. Issue 2: Inject direction nếu edge cấu hình direction thay đổi
                    edge_dir     = edge_data.get('direction', 'forward')
                    target_dir_c = ACT_DIR_BWD if edge_dir == 'backward' else ACT_DIR_FWD

                    if target_dir_c == ACT_DIR_BWD and self._current_dir == ACT_DIR_FWD:
                        # Kiểm tra xem đuôi xe có đang hướng về next_node không
                        # Nếu vector (prev→curr) cùng chiều với (curr→next) → đuôi quay về
                        # prev, không hướng về next_node → cần quay 180° trước khi lùi
                        prev_for_rot = self._get_prev_node(segment_nodes, i)
                        needs_rotate_bwd = False
                        if prev_for_rot is not None and hasattr(self, 'graph_ref'):
                            g_r = self.graph_ref
                            pp = g_r.nodes.get(prev_for_rot, {})
                            pc = g_r.nodes.get(int(node), {})
                            pn = g_r.nodes.get(int(next_node), {})
                            vin_x  = _node_disp_xy(pc)[0] - _node_disp_xy(pp)[0]
                            vin_y  = _node_disp_xy(pc)[1] - _node_disp_xy(pp)[1]
                            vout_x = _node_disp_xy(pn)[0] - _node_disp_xy(pc)[0]
                            vout_y = _node_disp_xy(pn)[1] - _node_disp_xy(pc)[1]
                            mag_in  = math.sqrt(vin_x**2 + vin_y**2)
                            mag_out = math.sqrt(vout_x**2 + vout_y**2)
                            if mag_in > 1e-6 and mag_out > 1e-6:
                                dot = (vin_x*vout_x + vin_y*vout_y) / (mag_in * mag_out)
                                # dot > 0: cùng chiều → đuôi chưa hướng về next → cần quay
                                needs_rotate_bwd = (dot > 0.3)
                        if needs_rotate_bwd:
                            # Luôn 2×TURN_L: hoạt động với mọi layout (+/ngã tư)
                            plan_data.append({"t": int(node), "a": ACT_LIDAR_OFF, "v": 0})
                            plan_data.append({"t": int(node), "a": ACT_TURN_L, "v": 0})
                            plan_data.append({"t": int(node), "a": ACT_TURN_L, "v": 0})
                            plan_data.append({"t": int(node), "a": ACT_LIDAR_ON, "v": 0})
                            print(f"[BWD-ROT] @ tag {int(node)}: quay 180° trước khi lùi → {int(next_node)}")

                    # Dừng hẳn (WAIT_SYS) trước khi đổi chiều để firmware nhả phanh đúng cách
                    self._set_direction(plan_data, int(node), target_dir_c, need_stop=True)

                    # 2b. Navigation Action — ưu tiên: edge manual > auto-detect > RUN
                    # 'a':3 (ACT_RUN) là giá trị mặc định của map editor → không coi là override thủ công
                    manual_a = edge_data.get('a', 0)
                    if manual_a not in (0, ACT_RUN):  # 0=chưa đặt, 3=mặc định → dùng auto-detect
                        nav_action = manual_a
                    elif hasattr(self, 'graph_ref'):
                        prev_for_auto = self._get_prev_node(segment_nodes, i)
                        if prev_for_auto is not None:
                            nav_action = self._auto_nav_action(prev_for_auto, node, next_node)

                    # Flip hướng rẽ khi edge là backward:
                    # auto_nav tính theo góc tiến (đầu xe dẫn trước), khi lùi đuôi xe dẫn trước
                    # → hướng rẽ vật lý ngược lại. Áp dụng cho cả chuyển chiều lẫn lùi liên tục.
                    if nav_action in (ACT_TURN_L, ACT_TURN_R) and edge_dir == 'backward':
                        nav_action = ACT_TURN_R if nav_action == ACT_TURN_L else ACT_TURN_L
                        print(f"[BWD-FLIP] {self.id} @ tag {int(node)}: flip hướng rẽ → "
                              f"{'TURN_R' if nav_action == ACT_TURN_R else 'TURN_L'} (edge lùi)")

                    # 2c. Parameter (Speed/Value)
                    value = edge_data.get('p', 0)
                elif hasattr(self, 'graph_ref'):
                    prev_for_auto = self._get_prev_node(segment_nodes, i)
                    if prev_for_auto is not None:
                        nav_action = self._auto_nav_action(prev_for_auto, node, next_node)

            # Xử lý điểm cuối cùng của segment
            if i == len(segment_nodes) - 1:
                is_final_dest = bool(self.full_path) and (node == self.full_path[-1])
                if is_final_dest:
                    node_role = node_data.get('role', 'none')
                    if node_role == 'charger':
                        # Trạm sạc: đèn vàng + bật cảm biến phát, không loa/nhấp nháy
                        nav_action = ACT_WAIT_CHARGE
                    elif self.current_task_type == "delivery":
                        # Tổ giao hàng: nhạc đến tổ + nhấp nháy b11, chờ xác nhận giao hàng
                        nav_action = ACT_WAIT_USER
                    else:
                        # Điểm chờ cấp hàng (pickup) hoặc khác: nhạc xin cấp liệu + nhấp nháy b37
                        nav_action = ACT_WAIT_SYS

            # Không override TURN_L/R — firmware dùng cảm biến dò line 90°, luôn chính xác.
            # Simulation engine đã tính đúng góc; override n_conn≤2 gây mất TURN tại corner nodes.

            # Issue 4: Look-ahead — nếu nav_action là TURN và edge TIẾP THEO (i+1→i+2) là backward
            # → inject LÙI TRƯỚC khi rẽ (cảm biến sau bắt line); KHÔNG flip hướng rẽ
            if (nav_action in (ACT_TURN_L, ACT_TURN_R)
                    and self._current_dir == ACT_DIR_FWD
                    and i + 2 < len(segment_nodes)
                    and hasattr(self, 'graph_ref')):
                node_after_turn = segment_nodes[i + 1]
                node_after_next = segment_nodes[i + 2]
                look_edge = self.graph_ref.get_edge_data(node_after_turn, node_after_next) or {}
                if look_edge.get('direction', 'forward') == 'backward':
                    # Đổi chiều sang lùi trước rẽ → flip TURN_L↔TURN_R
                    # Lý do: xe lùi đuôi-trước; nếu tiến cần rẽ phải thì đuôi phải quay trái
                    # để đuôi hướng về path → flip ngược lại so với tiến.
                    self._set_direction(plan_data, int(node), ACT_DIR_BWD, need_stop=False)
                    nav_action = ACT_TURN_R if nav_action == ACT_TURN_L else ACT_TURN_L
                    print(f"[BWD-TURN] {self.id} @ tag {int(node)}: LÙI + flip → {('TURN_R' if nav_action == ACT_TURN_R else 'TURN_L')} "
                          f"→ {int(node_after_turn)} (lùi → {int(node_after_next)})")

            plan_data.append({"t": int(node), "a": int(nav_action), "v": int(value)})

        # Tạo ID cho gói tin để chờ ACK
        cmd_id = str(uuid.uuid4())[:8]
        self.last_sent_cmd_id = cmd_id
        self._last_segment_nodes = segment_nodes  # Lưu để retry nếu mất gói
        self._last_sent_time = time.time()

        # Lưu plan để hiển thị trong monitor log window
        self.last_plan_data  = list(plan_data)
        self.last_plan_nodes = list(segment_nodes)
        # Tích lũy vào full_plan_data — dùng cho log window (hiển thị toàn nhiệm vụ)
        # Overlap: roll_start=idx → segment mới bắt đầu từ current_tag đã có ở segment trước.
        # → Xóa tất cả step của segment[0] ở CUỐI full_plan_data (thay bằng phiên bản mới).
        if self.full_plan_data and segment_nodes:
            overlap_tag = int(segment_nodes[0])
            while self.full_plan_data and self.full_plan_data[-1].get('t') == overlap_tag:
                self.full_plan_data.pop()
        self.full_plan_data.extend(plan_data)

        payload = json.dumps({"c": "plan", "d": plan_data, "id": cmd_id})
        steps_str = ", ".join(
            f"t{s['t']}:{ACTION_NAMES.get(s['a'], '#' + str(s['a']))}"
            + (f"(v={s['v']})" if s['v'] else "")
            for s in plan_data
        )
        sys_log(LOG_MQTT_OUT, self.id,
                f"PLAN → {self.topic_order}  ({len(payload)}B)  [{steps_str}]")
        self.mqtt.publish(self.topic_order, payload)

    def send_command(self, cmd):
        """Lệnh tức thì (VDA5050 instantActions): run, stop, reset, deba...
        Gửi qua topic_instant (uagv/v2/{factory}/{id}/instantActions)."""
        payload = json.dumps({"c": cmd})
        sys_log(LOG_MQTT_OUT, self.id, f"CMD → {self.topic_instant}  {payload}")
        self.mqtt.publish(self.topic_instant, payload)

    def send_btn_pic(self, line_num: int, pic_value: int, sel_count: int = -1):
        """Cập nhật pic nút tổ — lệnh tức thì gửi qua instantActions."""
        payload: dict = {"c": "set_btn_pic", "line": line_num, "pic": pic_value}
        if sel_count >= 0:
            payload["sel"] = sel_count
        self.mqtt.publish(self.topic_instant, json.dumps(payload))

    def send_reset_team_btns(self):
        """Reset tất cả nút tổ — lệnh tức thì gửi qua instantActions."""
        payload = json.dumps({"c": "reset_team_btns"})
        self.mqtt.publish(self.topic_instant, payload)

    def send_server_ack(self, event_type):
        """ACK sự kiện từ AGV — lệnh tức thì gửi qua instantActions."""
        payload = json.dumps({"c": "ack_event", "d": event_type})
        self.mqtt.publish(self.topic_instant, payload)

    def update_connection_state(self, state: str):
        """Cập nhật trạng thái kết nối VDA5050: ONLINE / OFFLINE / CONNECTIONBROKEN."""
        self.connection_state = state
        self.connected = (state == 'ONLINE')
        print(f"[{self.id}] Connection: {state}")

    def is_available(self, valid_idle_nodes):
        """
        Kiểm tra AGV có sẵn sàng nhận lệnh mới không (Point 5).
        Điều kiện: Không lỗi, Đang Idle, Đang ở trạm (Home).
        """
        if self.error_code != 0: return False

        is_at_valid_spot = self.current_tag in valid_idle_nodes

        # Auto-heal: nếu AGV đang idle tại node hợp lệ nhưng Python vẫn giữ is_navigating=True
        # (xảy ra khi chuyến bị bỏ dở hoặc AGV bị chuyển manual giữa chừng)
        if self.is_navigating and self.action_info == "idle" and is_at_valid_spot:
            print(f"[AUTO-HEAL] {self.id} idle tại node hợp lệ nhưng is_navigating=True. Reset state.")
            self.is_navigating = False
            self.task_lifecycle = "free"
            self.full_path = []

        if self.is_navigating: return False

        # Chấp nhận sẵn sàng nếu đang Idle, vị trí thuộc danh sách cho phép và Lifecycle là Free
        return self.action_info == "idle" and is_at_valid_spot and self.task_lifecycle == "free"

    @property
    def next_tag(self):
        """Thẻ kế tiếp trong hành trình hiện tại (None nếu idle hoặc đã đến đích)."""
        if not self.is_navigating or not self.full_path or not self.current_tag:
            return None
        try:
            idx = self.full_path.index(self.current_tag)
            return self.full_path[idx + 1] if idx + 1 < len(self.full_path) else None
        except ValueError:
            return None

    def _get_prev_node(self, segment_nodes, i):
        """Lấy node trước node tại index i để phục vụ auto-detect turn.
        - Nếu i > 0: lấy từ segment hiện tại.
        - Nếu i == 0: ưu tiên prev_tag thực tế (tag AGV vừa qua), fallback về full_path.
          Lý do: full_path.index() trả về OCCURRENCE ĐẦU TIÊN, sai khi path có node lặp
          (ví dụ path 2 chặng: 40→74→...→106→...→74→73 → index(74)=1 thay vì 7).
        """
        if i > 0:
            return segment_nodes[i - 1]
        # Ưu tiên prev_tag vật lý — chính xác nhất cho rolling plan
        if self.prev_tag and self.prev_tag != segment_nodes[0]:
            return self.prev_tag
        # Fallback: tra full_path (đúng khi path không có node lặp)
        if self.full_path and segment_nodes:
            try:
                idx = self.full_path.index(segment_nodes[0])
                if idx > 0:
                    return self.full_path[idx - 1]
            except ValueError:
                pass
        return None

    def _set_direction(self, plan_data, tag_id, target_dir, need_stop=True):
        """
        Đặt chiều xe (tiến / lùi) an toàn.
        - Nếu chiều đã đúng: không làm gì.
        - Nếu đang di chuyển (need_stop=True) và cần đổi chiều:
          dừng xe (WAIT_SYS) trước, rồi mới đảo chiều.
        Tương đương firmware: chieului() / chieutien() tự kiểm tra rồi gọi dunglaigap().
        """
        if target_dir == self._current_dir:
            return
        if need_stop:
            plan_data.append({"t": int(tag_id), "a": ACT_WAIT_SYS, "v": 0})
        plan_data.append({"t": int(tag_id), "a": target_dir, "v": 0})
        self._current_dir = target_dir

    def _calculate_angle(self, n1, n2, n3):
        return calc_turn_angle(self.graph_ref, n1, n2, n3)

    def _auto_nav_action(self, prev_node, curr_node, next_node):
        return auto_nav_action(self.graph_ref, prev_node, curr_node, next_node)

    def send_reverse_to_node(self, target_node: int) -> None:
        """
        Gửi lệnh lùi ngay lập tức về target_node (thường là prev_tag).
        Dùng khi RollingRePlanner phát hiện HEAD-ON mid-edge và cần lùi để reroute.

        Sau khi AGV lùi về target_node, update_state() sẽ detect
        (_reversing_to == 0 sau khi arrive) và kích hoạt navigation bình thường
        theo full_path mới đã được RollingRePlanner cập nhật.
        """
        if not self.can_reverse:
            print(f"[REVERSE] {self.id}: AGV không hỗ trợ lùi (can_reverse=False), bỏ qua.")
            return

        cur = self.current_tag
        tgt = int(target_node)
        if not cur or cur == tgt:
            return

        # Cập nhật flag trạng thái trước khi gửi
        self._reversing_to = tgt
        self._last_navigated_tag = None   # reset để navigation resume đúng sau khi về

        # Nhả reservation cạnh đang đi (sẽ đi ngược lại)
        if self.edge_mgr:
            self.edge_mgr.release(self.id, cur, tgt)   # cur→tgt (hướng cũ, không dùng nữa)

        cmd_id = str(uuid.uuid4())[:8]
        self.last_sent_cmd_id   = cmd_id
        self._last_sent_time    = time.time()
        self._last_segment_nodes = [cur, tgt]

        plan_data = [
            {"t": int(cur), "a": ACT_LIDAR_OFF, "v": 0},   # tắt lidar trước khi lùi
            {"t": int(cur), "a": ACT_DIR_BWD,   "v": 0},   # set chiều lùi
            {"t": int(cur), "a": ACT_RUN,        "v": 0},   # bắt đầu chạy
            {"t": tgt,      "a": ACT_WAIT_SYS,  "v": 0},   # dừng tại target_node
            {"t": tgt,      "a": ACT_DIR_FWD,   "v": 0},   # reset về chiều tiến
            {"t": tgt,      "a": ACT_LIDAR_ON,  "v": 0},   # bật lại lidar
        ]
        payload = json.dumps({"c": "plan", "d": plan_data, "id": cmd_id})
        print(f"[REVERSE_CMD] {self.id}: lùi {cur}→{tgt}  (id={cmd_id})")
        self.mqtt.publish(self.topic_order, payload)

    def get_error_status(self, stuck_timeout=30):
        """Trả về chuỗi mô tả lỗi hoặc cảnh báo kẹt"""
        # 1. Lỗi từ phần cứng gửi lên
        if self.error_code in ERROR_MAP and self.error_code != 0:
            return f"ERR: {ERROR_MAP[self.error_code]}"
            
        # 2. Phát hiện kẹt (Stuck) do phần mềm tính toán
        if self.status == "auto" and self.action_info == "running":
            if (time.time() - self.last_move_time) > stuck_timeout:
                return "WARNING: Stuck / Blocked Timeout"
                
        return "OK"

    def _send_hold(self):
        """
        Giữ AGV tại node hiện tại bằng cách gửi plan chỉ có ACT_WAIT_SYS.
        Dùng khi Zone bị khoá — AGV dừng tại chỗ chờ token được cấp.
        """
        node = self.current_tag
        cmd_id = str(uuid.uuid4())[:8]
        self.last_sent_cmd_id   = cmd_id
        self._last_sent_time    = time.time()
        self._last_segment_nodes = [node]  # Để retry cũng chỉ gửi hold
        payload = json.dumps({
            "c": "plan",
            "d": [{"t": int(node), "a": ACT_WAIT_SYS, "v": 0}],
            "id": cmd_id
        })
        print(f"[ZONE HOLD] {self.id} chờ zone token tại tag {node}")
        self.mqtt.publish(self.topic_order, payload)

    def resume_from_zone_wait(self):
        """
        Gọi từ main khi Zone Manager cấp token cho AGV đang chờ.
        Tiếp tục gửi segment đã được lưu lại.
        """
        if self.zone_waiting and self._zone_waiting_segment:
            segment = self._zone_waiting_segment
            self.zone_waiting = False
            self._zone_waiting_segment = []
            print(f"[ZONE RESUME] {self.id} tiếp tục → {segment}")
            self._send_segment(segment)

    def resume_from_whca(self):
        """
        Gọi từ traffic loop khi WHCA* xác nhận xung đột đã được giải quyết.
        Tiếp tục gửi segment đang bị treo.
        """
        if self.whca_waiting and self._whca_pending_segment:
            segment = self._whca_pending_segment
            self.whca_waiting = False
            self.whca_hold    = False
            self._whca_pending_segment = []
            print(f"[WHCA* RESUME] {self.id} tiếp tục → {segment}")
            self._send_segment(segment)

    def resume_from_edge_hold(self):
        """
        Gọi từ traffic loop khi cạnh ngược chiều đã thông.
        Tiếp tục gửi segment đang bị treo.
        """
        if self.edge_hold and self._edge_hold_segment:
            segment = self._edge_hold_segment
            self.edge_hold = False
            self._edge_hold_segment = []
            print(f"[EDGE RESUME] {self.id} tiếp tục → {segment}")
            self._send_segment(segment)

    # ── Door Check Gate ───────────────────────────────────────────────────────
    def _is_door_check(self) -> bool:
        """
        Kiểm tra AGV hiện đang ở một điểm cần check cửa không.

        Tra cứu trong _door_check_map theo (current_tag, prev_tag):
          - Nếu entry_from == None → kích hoạt cho cả 2 chiều.
          - Nếu entry_from == prev_tag → kích hoạt đúng chiều cấu hình.
          - Nếu door_hold đang True → không kích hoạt lại (tránh vòng lặp).
        """
        if self.door_hold or not self._door_check_map:
            return False
        configs = self._door_check_map.get(int(self.current_tag), [])
        for cfg in configs:
            entry_from = cfg.get('entry_from')
            if entry_from is None:
                return True                         # Cả 2 chiều
            if self.prev_tag == int(entry_from):
                return True                         # Đúng chiều
        return False

    def _send_door_check_cmd(self):
        """
        Gửi lệnh {"c": "door_check"} xuống AGV.
        Arduino nhận lệnh này → kiểm tra lidar xa nhất → gửi door_blocked/door_clear.
        Lệnh này tách biệt với plan (không cần tag ID, AGV đã dừng tại đây).
        """
        payload = json.dumps({"c": "door_check"})
        print(f"[DOOR CHECK] {self.id} → {self.topic_order}: door_check at tag {self.current_tag} "
              f"(from {self.prev_tag})")
        self.mqtt.publish(self.topic_order, payload)

    def resume_from_door_hold(self):
        """Gọi từ run_hmi_handler khi server nhận 'door_clear' → tiếp tục navigation."""
        if self.door_hold and self._door_hold_segment:
            seg = self._door_hold_segment
            self.door_hold = False
            self._door_hold_segment = []
            print(f"[DOOR RESUME] {self.id} → cửa mở, tiếp tục: {seg}")
            self._send_segment(seg)

    def ensure_log_header(self):
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
        if not os.path.exists(self.log_file):
            with open(self.log_file, 'w') as f:
                f.write("timestamp,date,agv_id,task_type,duration,target_node\n")

    def log_trip_finish(self):
        duration = int(time.time() - self.trip_start_time)
        target_node = self.full_path[-1] if self.full_path else 0
        now = datetime.datetime.now()
        
        # Ghi log
        with open(self.log_file, 'a') as f:
            # timestamp, date, agv_id, task_type, duration, target_node
            f.write(f"{int(time.time())},{now.strftime('%Y-%m-%d')},{self.id},{self.current_task_type},{duration},{target_node}\n")
            
        # Reset lifecycle và clear path visualization
        # current_task_type KHÔNG reset ở đây → giữ lại để map_widget biết hướng đỗ tại trạm sạc
        self.task_lifecycle = "free"
        self.full_path = []         # Xóa nét đứt trên bản đồ sau khi hoàn thành chuyến
        self.last_sent_cmd_id = None  # Dừng RETRY sau khi chuyến kết thúc