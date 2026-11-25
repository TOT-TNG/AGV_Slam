"""
sim_fleet.py — "Firmware giả" cho N xe ảo (SIM01..SIMnn), nói ĐÚNG giao thức
MQTT thật mà line_agv_handler.py/mqtt_client.py đã dùng với AGV thật:

  Server → AGV (sim subscribe):
    uagv/v2/{factory}/{agv_id}/order           {"c":"plan","id":...,"d":[{t,a,v},...]}
    uagv/v2/{factory}/{agv_id}/instantActions  {"c":"run"|"stop"|"reset"|"report"|
                                                 "ack_event"|"action"|"deba"|"battery_unlock"}

  AGV → Server (sim publish):
    uagv/v2/{factory}/{agv_id}/state           {"lastNodeId","prev_tag","driving",
                                                 "operatingMode","error_code","battery",
                                                 "event","ack",...}
    uagv/v2/{factory}/{agv_id}/connection

v1: xe chạy ĐÚNG HOÀN HẢO theo plan nhận được (không mô phỏng lỗi cơ khí/rẽ sai/
mất gói) — mục tiêu là stress-test logic tránh nhau/deadlock của server THẬT,
không phải test độ bền phần cứng. Cờ --fault-rate để dành cho sau (chưa dùng).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field

import paho.mqtt.client as mqtt
import psycopg2

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

UAGV_INTERFACE = "uagv"
UAGV_VERSION   = "v2"

# Backend thang: "uelev_v2" = thiết bị thang giả nói giao thức uelev/v2 của phần cứng (sim_uelev.py);
# khác = thang giả cũ elevator/v1 open/close. PHẢI cùng giá trị với server mô phỏng (run_simulation.py truyền env).
ELEVATOR_BACKEND = os.getenv("ELEVATOR_BACKEND", "legacy").strip().lower()
UELEV = ELEVATOR_BACKEND in ("uelev_v2", "uelev", "v2")

# Action codes — PHẢI khớp line_agv_plan_builder.py
ACTION_WAIT_SYS    = 1
ACTION_WAIT_USER   = 2
ACTION_RUN         = 3
ACTION_SPEED       = 4
ACTION_TURN_R      = 5
ACTION_TURN_L      = 6
ACTION_DIR_FWD     = 7
ACTION_DIR_BWD     = 8
ACTION_LIDAR_OFF   = 20
ACTION_LIDAR_ON    = 21
ACTION_WAIT_CHARGE = 35
ACTION_HOOK_RAISE  = 30
ACTION_HOOK_LOWER  = 31
ACTION_REVERSE_BLIND = 36

_SPEED_FACTOR = 240.0   # khớp ms_to_speed_byte() trong line_agv_plan_builder.py
TURN_DURATION_SEC = 2.0  # thời gian giả định cho 1 lần rẽ 90°


def _speed_byte_to_ms(v: int) -> float:
    if not v or v <= 0:
        return 0.5
    return max(0.05, v / _SPEED_FACTOR)


@dataclass
class EdgeInfo:
    distance: float
    speed: float
    speed_bwd: float | None


# Thang máy giả lập — cùng giao thức với thiết bị thật (xem elevator_coordinator.py / PROTOCOL_GUIDE.md mục 17)
ELEVATOR_INTERFACE = "elevator"
ELEVATOR_VERSION   = "v1"
ELEV_DOOR_SEC  = 1.2    # thời gian mở / đóng cửa
ELEV_FLOOR_SEC = 1.8    # thời gian chạy qua 1 tầng


@dataclass
class SimElevator:
    elevator_id: str
    levels: list                 # số tầng thang dừng (đã sắp xếp)
    level: int                   # tầng hiện tại
    state: str = "closed"
    gen: int = 0                 # tăng mỗi lệnh mới → huỷ chuỗi đang chạy
    lock: threading.Lock = field(default_factory=threading.Lock)


@dataclass
class SimAgv:
    agv_id: str
    current_tag: str
    prev_tag: str = "0"
    driving: bool = False
    operating_mode: str = "AUTOMATIC"
    battery: int = 100
    lock: threading.Lock = field(default_factory=threading.Lock)
    gen: int = 0   # tăng mỗi lần nhận plan mới -> huỷ thread thực thi plan cũ
    reversing: bool = False   # chặng gần nhất đi LÙI (DIR_BWD) — để deba biết mũi xe đang quay về đâu
    hook_gen: int = 0   # tăng mỗi lần nhận lệnh nâng/hạ móc MỚI -> huỷ callback móc cũ (xem _handle_instant_action)
    cmd_ack: str = ""   # id lệnh run/stop gần nhất đã nhận (báo lại trong MỌI state; 09-ack-lenh-fms.md §2.2)
    offline: bool = False   # mô phỏng mất Wi-Fi (vd trong cabin đóng cửa): không publish state, bỏ qua mọi lệnh
    run_evt: threading.Event = field(default_factory=threading.Event)   # `run` tới → nhả WAIT_SYS đang giữ ở cabin


class SimFleet:
    def __init__(self, broker: str, port: int, db_url: str, factory: str, log_path: str):
        self.broker = broker
        self.port = port
        self.factory = factory
        self.db_url = db_url
        self.agvs: dict[str, SimAgv] = {}
        self.elevators: dict[str, SimElevator] = {}
        self.edges: dict[tuple[str, str], EdgeInfo] = {}
        self.points: set[str] = set()
        self.cabin_nodes: dict[str, str] = {}      # node cabin -> id thang
        self.uelev = None                          # UelevEmulator (chỉ khi ELEVATOR_BACKEND=uelev_v2)

        self.logger = logging.getLogger("sim_fleet")
        self.logger.setLevel(logging.INFO)
        h = logging.FileHandler(log_path, encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        self.logger.addHandler(h)
        self.logger.addHandler(logging.StreamHandler())

        self.client = mqtt.Client(client_id=f"sim_fleet_{uuid.uuid4().hex[:8]}", clean_session=True)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self._heartbeat_started = False

    # ── Khởi tạo dữ liệu bản đồ + xe ─────────────────────────────────────────
    def load_map_and_agvs(self) -> None:
        conn = psycopg2.connect(self.db_url)
        cur = conn.cursor()
        cur.execute("SELECT name FROM agv_devices WHERE factory=%s ORDER BY name", (self.factory,))
        names = [r[0] for r in cur.fetchall()]
        if not names:
            raise RuntimeError(f"Không có AGV nào với factory={self.factory!r} trong DB mô phỏng")

        cur.execute("SELECT DISTINCT map_id FROM agv_devices WHERE factory=%s LIMIT 1", (self.factory,))
        map_id = cur.fetchone()[0]

        cur.execute("SELECT name_id, action FROM agv_map_points WHERE map_id=%s", (map_id,))
        rows = cur.fetchall()
        self.points = {r[0] for r in rows}
        # Chỗ đỗ hợp lệ (waiting_node / trạm sạc) — xe khởi tạo ở đây trước, hết chỗ mới rải sang node khác
        parking = sorted(r[0] for r in rows if isinstance(r[1], dict) and (
            r[1].get("waiting_node") == "yes" or r[1].get("locationType") == "CHARGER"))

        # Thang máy: danh sách thang + các tầng thang dừng (node action.elevator_id × tầng của node)
        try:
            cur.execute("SELECT floors, elevators FROM agv_maps WHERE id=%s", (map_id,))
            row_fe = cur.fetchone()
            floors_meta = (row_fe[0] or []) if row_fe else []
            lvl_of = {str(f.get("id")): int(f.get("level")) for f in floors_meta if f.get("level") is not None}
            cur.execute("SELECT action, COALESCE(floor_id,''), name_id FROM agv_map_points WHERE map_id=%s", (map_id,))
            first_fid = str(floors_meta[0].get("id")) if floors_meta else ""
            served: dict[str, set] = {}
            pts_rows = cur.fetchall()
            floor_of = {str(nid): (fid or first_fid) for _a, fid, nid in pts_rows}
            # Cabin dùng chung (1 node cho mọi tầng): tầng thang dừng = tầng của các node hàng xóm cabin (giống
            # MapManager.derive_elevator_nodes); node cabin chỉ mang floor_id của 1 tầng nên không đủ.
            cur.execute("SELECT id_source, id_dest FROM agv_map_roads WHERE map_id=%s", (map_id,))
            nbr_floors: dict[str, set] = {}
            for s_, d_ in cur.fetchall():
                nbr_floors.setdefault(str(s_), set()).add(floor_of.get(str(d_), first_fid))
                nbr_floors.setdefault(str(d_), set()).add(floor_of.get(str(s_), first_fid))
            for act, fid, nid in pts_rows:
                eid = str((act or {}).get("elevator_id") or "") if isinstance(act, dict) else ""
                if eid:
                    fids = {fid or first_fid}
                    if len(nbr_floors.get(str(nid), ())) >= 2:
                        fids |= nbr_floors[str(nid)]
                    for f_ in fids:
                        lv = lvl_of.get(f_)
                        if lv is not None:
                            served.setdefault(eid, set()).add(lv)
                    if served.get(eid):
                        self.cabin_nodes[str(nid)] = eid
            for eid, lvls in served.items():
                ls = sorted(lvls)
                self.elevators[eid] = SimElevator(elevator_id=eid, levels=ls, level=ls[0])
        except Exception as e:
            conn.rollback()   # truy vấn lỗi làm hỏng transaction — dọn để các truy vấn sau vẫn chạy
            self.logger.info(f"[INIT] không nạp được thang máy: {e}")

        cur.execute(
            "SELECT id_source, id_dest, distance, speed, speed_bwd, move_direction "
            "FROM agv_map_roads WHERE map_id=%s", (map_id,),
        )
        for src, dst, dist, spd, spd_bwd, move_dir in cur.fetchall():
            dist = float(dist or 1.0)
            spd = float(spd or 0.3)
            if move_dir in (0, 1):
                self.edges[(src, dst)] = EdgeInfo(dist, spd, spd_bwd)
            if move_dir in (0, 2):
                self.edges[(dst, src)] = EdgeInfo(dist, float(spd_bwd or spd), spd)
        conn.close()

        # Vị trí xuất phát do setup_sim_db.py gán (cột sim_start_node: người dùng chỉ định theo loại
        # xe, hoặc tự chọn trạm sạc đúng loại xe). Cột/giá trị thiếu → rải như trước.
        planned: dict[str, str] = {}
        try:
            conn2 = psycopg2.connect(self.db_url)
            cur2 = conn2.cursor()
            cur2.execute("SELECT name, sim_start_node FROM agv_devices WHERE factory=%s", (self.factory,))
            planned = {r[0]: str(r[1]) for r in cur2.fetchall() if r[1]}
            conn2.close()
        except Exception:
            planned = {}
        pts_list = parking + sorted(self.points - set(parking))
        for i, name in enumerate(names):
            start_tag = planned.get(name)
            if start_tag not in self.points:
                start_tag = pts_list[i % len(pts_list)]
            self.agvs[name] = SimAgv(agv_id=name, current_tag=start_tag, prev_tag=start_tag)
        if self.elevators:
            self.logger.info(f"[INIT] thang máy giả lập: "
                              f"{ {k: v.levels for k, v in self.elevators.items()} }")
        self.logger.info(f"[INIT] map_id={map_id} points={len(self.points)} edges={len(self.edges)} "
                          f"agvs={names} (mỗi xe bắt đầu rải đều trên map, tránh dồn 1 node)")

    # ── MQTT ──────────────────────────────────────────────────────────────
    def _topic(self, agv_id: str, suffix: str) -> str:
        return f"{UAGV_INTERFACE}/{UAGV_VERSION}/{self.factory}/{agv_id}/{suffix}"

    def _on_connect(self, client, userdata, flags, rc):
        self.logger.info(f"[MQTT] connected rc={rc} broker={self.broker}:{self.port}")
        client.subscribe(f"{UAGV_INTERFACE}/{UAGV_VERSION}/{self.factory}/+/order", qos=1)
        client.subscribe(f"{UAGV_INTERFACE}/{UAGV_VERSION}/{self.factory}/+/instantActions", qos=1)
        if UELEV:
            self._start_uelev()
        else:
            client.subscribe(f"{ELEVATOR_INTERFACE}/{ELEVATOR_VERSION}/{self.factory}/+/cmd", qos=1)
            for el in self.elevators.values():
                self._publish_elevator(el)
        # PHÁT HIỆN THỰC TẾ (2026-10-06): _publish_connection() dùng retain=True
        # trước đây → broker GIỮ LẠI thông điệp đó mãi, ngay cả sau khi lần
        # chạy đó kết thúc. Lần chạy SAU (vd ít xe hơn, 5 thay vì 15) connect
        # lại ĐÚNG broker cũ (người dùng tự giữ Mosquitto sống giữa các lần
        # chạy) → nhận lại NGAY các "xác" SIM06..SIM15 từ lần trước, tưởng là
        # xe đang chạy thật. Dọn SẠCH mọi retained cũ (SIM01..SIM50, trùm hết
        # khoảng --agv-count 1-50 cho phép) bằng payload rỗng + retain=True
        # (đúng cách xoá retained message theo chuẩn MQTT) trước khi xe của
        # lần chạy NÀY tự công bố lại — không phụ thuộc lần chạy trước đã
        # dùng retain hay chưa (xoá payload rỗng vào topic trống cũng vô hại).
        for _i in range(1, 51):
            _ghost_id = f"SIM{_i:02d}"
            client.publish(self._topic(_ghost_id, "connection"), b"", qos=1, retain=True)
        for agv_id in self.agvs:
            self._publish_state(agv_id)
            self._publish_connection(agv_id)
        if not self._heartbeat_started:
            self._heartbeat_started = True
            threading.Thread(target=self._heartbeat_loop, daemon=True).start()

    def _heartbeat_loop(self) -> None:
        """PHÁT HIỆN THỰC TẾ (2026-10-07): trước đây sim CHỈ publish state lúc
        có sự kiện (tới nơi/móc/nhận lệnh) — không báo cáo định kỳ như firmware
        thật. Mọi watchdog phục hồi dựa trên state định kỳ (vd self._had_error
        trong line_agv_handler._on_state, dùng để tự gửi lại cửa sổ sau khi 1
        xe bị STOP khẩn cấp vì nguy cơ va chạm vật lý) chỉ được kiểm tra MỖI
        LẦN có state message mới tới — xe ảo bị dừng không bao giờ gửi thêm
        state nào nữa → không bao giờ được kiểm tra lại → kẹt vĩnh viễn TRONG
        MÔ PHỎNG (không phải lỗi thật, vì AGV thật luôn báo cáo định kỳ dù
        đang đứng yên). Thêm heartbeat để mô phỏng sát firmware thật hơn."""
        while True:
            time.sleep(2.0)
            for agv_id in list(self.agvs.keys()):
                try:
                    self._publish_state(agv_id)
                except Exception as e:
                    self.logger.info(f"[ERROR] heartbeat {agv_id} lỗi: {e}")

    def _start_uelev(self) -> None:
        if self.uelev is not None:
            self.uelev.on_paho_connect()
            return
        try:
            from sim_uelev import UelevEmulator
        except ImportError:
            from simulation.sim_uelev import UelevEmulator
        self.uelev = UelevEmulator(self.client, self.factory,
                                   {eid: el.levels for eid, el in self.elevators.items()},
                                   self.cabin_nodes, self.agvs, self.logger)
        self.uelev.set_publish_state(self._publish_state)
        self.uelev.start()

    def _on_message(self, client, userdata, msg):
        if self.uelev is not None and self.uelev.on_paho_message(msg.topic, msg.payload):
            return
        try:
            parts = msg.topic.split("/")
            if len(parts) != 5:
                return
            if parts[0] == ELEVATOR_INTERFACE:
                el = self.elevators.get(parts[3])
                if el is not None and parts[4] == "cmd":
                    self._handle_elevator_cmd(el, json.loads(msg.payload.decode("utf-8", errors="replace")))
                return
            agv_id, suffix = parts[3], parts[4]
            agv = self.agvs.get(agv_id)
            if agv is None:
                return
            data = json.loads(msg.payload.decode("utf-8", errors="replace"))
            if suffix == "order":
                self._handle_order(agv, data)
            elif suffix == "instantActions":
                self._handle_instant_action(agv, data)
        except Exception as e:
            self.logger.info(f"[ERROR] on_message lỗi: {e} | topic={msg.topic}")

    def _publish_state(self, agv_id: str, event: str | None = None, ack: str | None = None) -> None:
        agv = self.agvs[agv_id]
        payload = {
            "lastNodeId": str(agv.current_tag),
            "tag": str(agv.current_tag),
            "prev_tag": str(agv.prev_tag),
            "driving": agv.driving,
            "paused": False,
            "operatingMode": agv.operating_mode,
            "error_code": 0,
            "battery": agv.battery,
            "batteryState": {"batteryCharge": agv.battery},
            "battery_low": False,
            "battery_blocking": False,
        }
        if event:
            payload["event"] = event
        if ack:
            payload["ack"] = ack
        if agv.cmd_ack:
            payload["cmd_ack"] = agv.cmd_ack
        if agv.offline:
            return
        self.client.publish(self._topic(agv_id, "state"), json.dumps(payload, ensure_ascii=False), qos=1)

    def _publish_connection(self, agv_id: str) -> None:
        # KHÔNG retain — xe mô phỏng publish liên tục khi còn chạy; retain
        # chỉ khiến broker giữ lại "xác" sau khi lần chạy này kết thúc, gây
        # lẫn sang lần chạy sau (xem dọn dẹp ở _on_connect).
        self.client.publish(self._topic(agv_id, "connection"),
                             json.dumps({"connectionState": "ONLINE"}), qos=1, retain=False)

    # ── Xử lý lệnh từ server ──────────────────────────────────────────────
    def _handle_instant_action(self, agv: SimAgv, data: dict) -> None:
        cmd = str(data.get("c") or "")
        if agv.offline:
            return   # mất mạng: lệnh rơi hẳn (đúng như MQTT QoS0 + session sạch trên xe thật)
        cmd_id = str(data.get("id") or "")[:9]
        if cmd in ("run", "stop") and cmd_id:
            if cmd_id == agv.cmd_ack:
                # Gửi lặp cùng id: KHÔNG chạy lại, chỉ báo lại cmd_ack (như Arduino)
                self._publish_state(agv.agv_id)
                return
            agv.cmd_ack = cmd_id
        if cmd == "stop":
            with agv.lock:
                agv.driving = False
                agv.operating_mode = "MANUAL"
                agv.gen += 1   # huỷ mọi transit đang chạy
            self._publish_state(agv.agv_id)
        elif cmd == "run":
            with agv.lock:
                agv.operating_mode = "AUTOMATIC"
            agv.run_evt.set()      # nhả WAIT_SYS đang giữ ở cabin thang (07-tich-hop-fms.md §3)
            self._publish_state(agv.agv_id)
        elif cmd == "locate":
            # Đặt lại vị trí (xe vừa được thang chở sang tầng khác — xe không di chuyển nên không đọc thẻ mới)
            tag = str(data.get("tag"))
            prev = str(data.get("prev") or tag)
            if tag in self.points:
                with agv.lock:
                    agv.gen += 1
                    agv.driving = False
                    agv.prev_tag = prev
                    agv.current_tag = tag
                self.logger.info(f"[{agv.agv_id}] đặt lại vị trí → {tag} (prev {prev}) do thang máy")
                self._publish_state(agv.agv_id)
            else:
                self.logger.info(f"[{agv.agv_id}] locate tag lạ {tag!r} — bỏ qua")
        elif cmd == "reset":
            self._publish_state(agv.agv_id)
        elif cmd == "report":
            self._publish_state(agv.agv_id)
        elif cmd == "ack_event":
            pass   # server xác nhận đã nhận event — sim không cần resend, bỏ qua
        elif cmd == "deba":
            # Maneuver xác nhận vị trí (LOCATE_THEN_CHARGE) — v1 không mô phỏng
            # sạc chi tiết, chỉ phản hồi coi như đã xong để không treo server.
            # Xe thật chạy tới khi quẹt 1 thẻ MỚI rồi dừng → server (LOCATE_THEN_CHARGE) chỉ tiếp tục "Về trạm"
            # khi thấy TAG ĐỔI. Xe ảo trước đây không đổi tag → bước dò vị trí treo mãi. Nay nhích đúng 1 node:
            # 'lui' → về node trước (prev_tag), 'toi' → sang hàng xóm KHÁC prev_tag (hết lối thì quay lại).
            direction = str(data.get("dir") or "toi")
            cur = str(agv.current_tag)
            nbrs = [b for (a_, b) in self.edges if a_ == cur]
            prev = str(agv.prev_tag)
            # Mũi xe quay về hướng nào? Chặng trước đi TIẾN → mũi hướng đi tới (hàng xóm ≠ prev); chặng trước đi
            # LÙI → mũi hướng về prev. 'toi' đi theo mũi, 'lui' đi ngược mũi.
            nose_forward = not agv.reversing           # mũi hướng tới hàng xóm khác prev
            go_nose = (direction != "lui")
            go_away_from_prev = (go_nose == nose_forward)
            cand = [n for n in nbrs if n != prev]
            if go_away_from_prev:
                dest = cand[0] if cand else (nbrs[0] if nbrs else None)
            else:
                dest = prev if prev in nbrs else (nbrs[0] if nbrs else None)
            with agv.lock:
                agv.gen += 1   # huỷ plan đang chạy (nếu có) như firmware thật khi nhận deba
            def _finish_deba():
                # Giống firmware thật: báo driving=True suốt lúc chạy, tag đổi khi quẹt thẻ mới (vẫn driving),
                # rồi mới dừng + báo event — server bỏ qua đổi tag khi xe báo driving=False.
                if dest is not None:
                    with agv.lock:
                        agv.driving = True
                    self._publish_state(agv.agv_id)
                time.sleep(1.5)
                if dest is not None:
                    with agv.lock:
                        agv.prev_tag = agv.current_tag
                        agv.current_tag = dest
                        agv.reversing = (direction == "lui")
                    self._publish_state(agv.agv_id)
                    time.sleep(0.4)
                    with agv.lock:
                        agv.driving = False
                    self.logger.info(f"[{agv.agv_id}] deba {direction}: {cur} → {dest}")
                self._publish_state(agv.agv_id, event="arrived_wait_sys")
            threading.Thread(target=_finish_deba, daemon=True).start()
        elif cmd == "action":
            # PHÁT HIỆN THỰC TẾ (2026-10-06): a=30 (NÂNG)/a=31 (HẠ) trước đây
            # KHÔNG được phản hồi gì cả — server chờ mãi event hook_raised/
            # hook_lowered không bao giờ tới, gửi lại 2 lần rồi bỏ cuộc (dừng
            # hẳn watchdog retry), xe đứng im hàng chục/hàng trăm giây (đúng
            # STALL thấy được trong violations_*.jsonl) — làm nhiễu rất nhiều
            # lên log/test, che mất các lỗi điều phối thật cần tìm. Fix: trả
            # lời đúng event tương ứng sau 1 khoảng trễ ngắn, giống firmware
            # thật xử lý xong thao tác cơ khí.
            #
            # PHÁT HIỆN THỰC TẾ (2026-10-07): server NÂNG MÓC TRƯỚC 1 node cho
            # xe 'tow' sắp tới điểm lấy hàng (hook_prearmed_for — tối ưu thời
            # gian), rồi gửi tiếp lệnh HẠ THẬT ngay khi xe tới hẳn nơi. Nếu
            # quãng đường 1-node đó mô phỏng xong NHANH (vài giây), callback
            # trễ 1.0s của lệnh NÂNG trước có thể bắn event 'hook_raised' SAU
            # khi lệnh HẠ thật đã gửi — server nhận 'hook_raised' lạc (tưởng
            # là xác nhận NÂNG thật) NGAY TRƯỚC 'hook_lowered' đúng, làm lệch
            # hook_pending/task_lifecycle, xe đứng kẹt tại chỗ (không xe thật
            # nào bị vậy — hành trình giữa 2 node + móc cơ khí luôn chậm hơn
            # 1 giây giả này). Vá bằng hook_gen (giống gen cho plan): lệnh móc
            # MỚI tăng hook_gen → callback của lệnh CŨ tự biết lạc, không bắn
            # event nữa.
            a_code = data.get("a")
            if a_code in (ACTION_HOOK_RAISE, ACTION_HOOK_LOWER):
                event_name = "hook_raised" if a_code == ACTION_HOOK_RAISE else "hook_lowered"
                with agv.lock:
                    agv.hook_gen += 1
                    my_hook_gen = agv.hook_gen
                def _finish_hook():
                    time.sleep(1.0)
                    if agv.hook_gen != my_hook_gen:
                        return   # có lệnh móc MỚI hơn đã tới — event này lạc, bỏ qua
                    self._publish_state(agv.agv_id, event=event_name)
                threading.Thread(target=_finish_hook, daemon=True).start()
        elif cmd == "battery_unlock":
            pass

    # ── Thang máy giả lập ─────────────────────────────────────────────────
    def _publish_elevator(self, el: SimElevator) -> None:
        self.client.publish(
            f"{ELEVATOR_INTERFACE}/{ELEVATOR_VERSION}/{self.factory}/{el.elevator_id}/state",
            json.dumps({"state": el.state, "floor": el.level}), qos=1, retain=True)

    def _handle_elevator_cmd(self, el: SimElevator, data: dict) -> None:
        cmd = str(data.get("c") or "")
        with el.lock:
            el.gen += 1
            my_gen = el.gen
        self.logger.info(f"[ELEV {el.elevator_id}] nhận lệnh {data}")
        threading.Thread(target=self._run_elevator, args=(el, cmd, data.get("floor"), my_gen), daemon=True).start()

    def _set_elev(self, el: SimElevator, state: str, my_gen: int) -> bool:
        if el.gen != my_gen:
            return False
        el.state = state
        self._publish_elevator(el)
        return True

    def _run_elevator(self, el: SimElevator, cmd: str, floor, my_gen: int) -> None:
        if cmd == "close":
            if el.state != "closed":
                if not self._set_elev(el, "closing", my_gen):
                    return
                time.sleep(ELEV_DOOR_SEC)
            self._set_elev(el, "closed", my_gen)
            return
        if cmd != "open":
            return
        try:
            level = int(floor)
        except (TypeError, ValueError):
            self._set_elev(el, "error", my_gen)
            return
        if level not in el.levels:
            self.logger.info(f"[ELEV {el.elevator_id}] tầng {level} không có trong {el.levels} → error")
            self._set_elev(el, "error", my_gen)
            return
        if el.state == "open" and el.level == level:
            self._set_elev(el, "open", my_gen)        # idempotent: publish lại
            return
        if el.state in ("open", "opening", "closing"):
            if not self._set_elev(el, "closing", my_gen):
                return
            time.sleep(ELEV_DOOR_SEC)
            if not self._set_elev(el, "closed", my_gen):
                return
        if el.level != level:
            if not self._set_elev(el, "moving", my_gen):
                return
            time.sleep(ELEV_FLOOR_SEC * abs(level - el.level))
            if el.gen != my_gen:
                return
            el.level = level
        if not self._set_elev(el, "opening", my_gen):
            return
        time.sleep(ELEV_DOOR_SEC)
        self._set_elev(el, "open", my_gen)

    def _handle_order(self, agv: SimAgv, data: dict) -> None:
        if str(data.get("c")) != "plan" or agv.offline:
            return
        order_id = str(data.get("id") or "")
        steps = data.get("d") or []
        with agv.lock:
            agv.gen += 1
            my_gen = agv.gen
            agv.operating_mode = "AUTOMATIC"
        self._publish_state(agv.agv_id, ack=order_id)
        threading.Thread(target=self._run_plan, args=(agv, steps, my_gen), daemon=True).start()

    # ── Thực thi plan (đi chân thật theo thời gian ước tính) ───────────────
    def _run_plan(self, agv: SimAgv, steps: list[dict], my_gen: int) -> None:
        speed_byte = 120
        i = 0
        while i < len(steps):
            if agv.gen != my_gen:
                return   # plan đã bị thay/huỷ (stop hoặc plan mới tới)
            step = steps[i]
            a = step.get("a")
            v = step.get("v")

            if a == ACTION_DIR_BWD:
                agv.reversing = True
            elif a == ACTION_DIR_FWD:
                agv.reversing = False
            if a == ACTION_SPEED:
                speed_byte = int(v or speed_byte)
            elif a in (ACTION_TURN_R, ACTION_TURN_L):
                time.sleep(TURN_DURATION_SEC)
            elif (a == ACTION_WAIT_SYS and i < len(steps) - 1 and self.uelev is not None
                    and str(step.get("t")) in self.cabin_nodes):
                # Cabin thang (uelev_v2): WAIT_SYS GIỮA plan = XE ĐỨNG CHỜ trong cabin tới khi nhận `run`
                # (EXIT_ALLOWED), rồi chạy tiếp phần đuôi plan (đổi chiều → lùi ra thẻ thoát). Mặc định KHÔNG báo
                # event arrived_wait_sys (trường hợp khó: server phải tự phát hiện xe vào cabin qua thẻ RFID).
                with agv.lock:
                    agv.driving = False
                agv.run_evt.clear()
                self._publish_state(agv.agv_id, event=("arrived_wait_sys" if os.getenv("SIM_CABIN_EVENT") == "1" else None))
                self.logger.info(f"[{agv.agv_id}] đứng chờ trong cabin {step.get('t')} — chờ run (EXIT_ALLOWED)")
                while not agv.run_evt.wait(0.2):
                    if agv.gen != my_gen:
                        return
                if agv.gen != my_gen:
                    return
                self.logger.info(f"[{agv.agv_id}] nhận run — rời cabin")
            elif a == ACTION_WAIT_SYS and i < len(steps) - 1:
                # PROTOCOL_GUIDE.md "Đổi chiều lùi": WAIT_SYS GIỮA plan (trước DIR_BWD, sau khi
                # quay đầu 180° tại chỗ) chỉ là "dừng hẳn" ngắn rồi firmware TỰ chạy tiếp các step
                # còn lại — KHÔNG phải tới đích, không báo event. Trước đây sim coi mọi WAIT_SYS
                # là hết plan → báo arrived_wait_sys → server gửi lại đúng plan đó (lại quay đầu
                # + WAIT_SYS) → lặp vô hạn tại chỗ (SIM12 tại 201, SIM13 tại 202), server cảnh
                # báo "nghi firmware không thực thi plan" dù xe mô phỏng không hề lỗi.
                with agv.lock:
                    agv.driving = False
                self._publish_state(agv.agv_id)
                time.sleep(1.0)
            elif a in (ACTION_WAIT_SYS, ACTION_WAIT_USER, ACTION_WAIT_CHARGE):
                event = "arrived_wait_sys" if a in (ACTION_WAIT_SYS, ACTION_WAIT_CHARGE) \
                        else "arrived_wait_user"
                with agv.lock:
                    agv.driving = False
                self._publish_state(agv.agv_id, event=event)
                self.logger.info(f"[{agv.agv_id}] dừng tại {agv.current_tag} ({event}) — "
                                  f"chờ lệnh tiếp từ server")
                return   # chờ order/instantAction kế tiếp từ server
            elif a == ACTION_RUN:
                dest = self._find_next_tag(steps, i)
                if dest is None or dest == str(agv.current_tag):
                    pass
                else:
                    edge = self.edges.get((str(agv.current_tag), dest))
                    dist = edge.distance if edge else 1.0
                    speed_ms = _speed_byte_to_ms(speed_byte)
                    travel_time = max(0.3, dist / speed_ms)
                    with agv.lock:
                        agv.driving = True
                    self._publish_state(agv.agv_id)
                    self.logger.info(f"[{agv.agv_id}] chạy {agv.current_tag} → {dest} "
                                      f"(~{travel_time:.1f}s)")
                    slept = 0.0
                    step_chunk = 0.25
                    while slept < travel_time:
                        if agv.gen != my_gen:
                            return
                        time.sleep(min(step_chunk, travel_time - slept))
                        slept += step_chunk
                    with agv.lock:
                        if agv.gen != my_gen:
                            return
                        agv.prev_tag = agv.current_tag
                        agv.current_tag = dest
                        agv.driving = True   # vẫn coi là driving tới khi xử lý step tiếp (TURN/WAIT)
                    self._publish_state(agv.agv_id)
            # a is None (chỉ có 't' đổi, không hành động) hoặc DIR_FWD/DIR_BWD/LIDAR_*:
            # không cần giả lập độ trễ, bỏ qua.
            i += 1
        # Hết steps mà không gặp wait action nào — đứng yên lặng lẽ.
        with agv.lock:
            agv.driving = False
        self._publish_state(agv.agv_id)

    @staticmethod
    def _find_next_tag(steps: list[dict], run_idx: int) -> str | None:
        cur_tag = str(steps[run_idx].get("t"))
        for j in range(run_idx + 1, len(steps)):
            t = str(steps[j].get("t"))
            if t != cur_tag:
                return t
        return None

    def run_forever(self) -> None:
        self.client.connect(self.broker, self.port, keepalive=30)
        self.client.loop_forever()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--broker", default=os.getenv("MQTT_BROKER", "localhost"))
    ap.add_argument("--port", type=int, default=int(os.getenv("MQTT_PORT", "1884")))
    ap.add_argument("--db-url", default=os.getenv(
        "DATABASE_URL", "postgresql://postgres:ducmanh1801@localhost:5432/TOT_AGV_SIM"))
    ap.add_argument("--factory", default="SimFactory")
    ap.add_argument("--fault-rate", type=float, default=0.0,
                     help="Dành cho sau — v1 chưa dùng, luôn chạy hoàn hảo")
    ap.add_argument("--log-dir", default=os.path.join(os.path.dirname(__file__), "logs"))
    args = ap.parse_args()

    os.makedirs(args.log_dir, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(args.log_dir, f"fleet_{ts}.log")

    fleet = SimFleet(args.broker, args.port, args.db_url, args.factory, log_path)
    fleet.load_map_and_agvs()
    fleet.run_forever()


if __name__ == "__main__":
    main()
