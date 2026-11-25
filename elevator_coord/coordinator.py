"""
coordinator.py — ElevatorCoordinator: điều phối thang máy cho AGV (docs/03, docs/05).

Một ElevatorUnit / thang: 1 ride đang chạy + hàng đợi + Zone Lock + kênh lệnh tin cậy.
Facade ElevatorCoordinator: định tuyến message MQTT, API cho FMS, phát sự kiện.

Không thread, không sleep: FMS gọi tick() đều đặn (100–500 ms) và on_message() khi có tin.
"""
from __future__ import annotations

import logging
import threading
from collections import deque
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

from . import protocol as P
from .clock import Clock, SystemClock
from .command_channel import Command, CommandChannel, CommandStatus
from .config import CoordinatorConfig, ElevatorConfig
from .devices import DeviceProxy
from .ride import (EventType, Ride, RideEvent, RideRejected, RideState, TERMINAL)
from .transport import Transport
from .zone_lock import ZoneLocks

log = logging.getLogger("elevator_coord")

EventCallback = Callable[[RideEvent], None]
_MAX_STEPS_PER_TICK = 8
_KEEP_HISTORY = 200


class ElevatorUnit:
    def __init__(self, cfg: ElevatorConfig, factory: str, transport: Transport,
                 clock: Clock, emit: Callable[[RideEvent], None]) -> None:
        self.cfg = cfg
        self.t = cfg.timing
        self.factory = factory
        self.transport = transport
        self.clock = clock
        self._emit_cb = emit
        self._hdr = P.HeaderCounter()

        self.master = DeviceProxy(cfg.master_device, P.KIND_MASTER)
        self.callers: Dict[int, DeviceProxy] = {
            fl: DeviceProxy(c.device_id, P.KIND_CALLER) for fl, c in cfg.callers.items()}
        self._by_device: Dict[str, DeviceProxy] = {self.master.device_id: self.master}
        self._by_device.update({p.device_id: p for p in self.callers.values()})

        self.zones = ZoneLocks({z.floor: (z.timeout_s, z.release_floor) for z in cfg.zones if z.enabled})
        self._now = 0.0
        self._link_up = True       # kết nối của CHÍNH FMS tới broker (xem ElevatorCoordinator.set_link_state)
        self.channel = CommandChannel(self._publish_action, self.t.cmd_retry_s, self.t.cmd_max_retries,
                                      is_available=self._dev_available)
        self.queue: List[Ride] = []
        self.active: Optional[Ride] = None
        # Cổng khóa VÙNG thang (opt-in, FMS bật qua set_area_gating): từ lúc 1 xe được cấp lượt tới khi FMS gọi release_area
        # (xe đã đi qua mốc thoát khỏi khu vực thang) KHÔNG xe nào khác được cấp lượt (gọi thang) — xe sau xếp hàng FIFO.
        self.area_gating = False
        # Opt-in: được cấp lượt (khóa vùng, giữ chỗ đầu hàng) nhưng CHƯA gọi Bộ gọi tầng cho tới khi FMS báo xe ĐÃ TỚI node chờ
        # (agv_ready). Tránh bộ gọi sáng/gọi liên tục lúc xe còn đang chạy từ xa tới.
        self.defer_until_ready = False
        self.area_hold: Optional[str] = None
        self.area_hold_at = 0.0
        self.rides: Dict[str, Ride] = {}
        self._seq = 0
        self._ride_n = 0

    # ================================================================ I/O
    def _publish_action(self, device_id: str, action: Dict[str, Any]) -> None:
        topic = P.topic_actions(self.factory, self.cfg.elevator_id, device_id)
        header = P.build_header(self._hdr.next(topic), self.clock.wall(), self.factory,
                                self.cfg.elevator_id, device_id)
        self.transport.publish(topic, P.build_instant_actions(header, [action]), qos=1, retain=False)

    def _dev_available(self, device_id: str) -> bool:
        """Presence gating: chỉ gửi/đếm gửi lặp khi thiết bị ONLINE và state còn mới."""
        p = self._by_device.get(device_id)
        return self._link_up and p is not None and p.available(self._now, self.t.state_stale_s)

    def set_link(self, up: bool) -> None:
        self._link_up = up

    def _send(self, device_id: str, action_type: str, params: Optional[Dict[str, Any]], now: float,
              force: bool = False) -> Command:
        self._now = now
        return self.channel.send(device_id, action_type, params, now, force=force)

    def on_state(self, device_id: str, state: P.DeviceState, now: float) -> None:
        proxy = self._by_device.get(device_id)
        if proxy is None:
            return
        proxy.update_state(state, now)
        self.channel.on_action_states(device_id, state.action_states, now)

    def on_connection(self, device_id: str, conn: str) -> None:
        proxy = self._by_device.get(device_id)
        if proxy is not None:
            proxy.update_connection(conn)

    def emit(self, typ: EventType, r: Optional[Ride], now: float, **data: Any) -> None:
        self._emit_cb(RideEvent(typ, r.ride_id if r else None, r.agv_id if r else None,
                                self.cfg.elevator_id, self.clock.wall(), data))

    # ================================================================ API
    def request_ride(self, agv_id: str, from_floor: int, to_floor: int, priority: int, now: float) -> str:
        reason = self.cfg.check_route(from_floor, to_floor)
        if reason:
            raise RideRejected(reason, f"{from_floor}->{to_floor}")
        for r in list(self.queue) + ([self.active] if self.active else []):
            if r.agv_id == agv_id and r.state != RideState.RELEASING:     # RELEASING = đang dọn, xe đã xong việc
                if (r.from_floor, r.to_floor) == (from_floor, to_floor):
                    return r.ride_id          # idempotent: FMS gửi lại cùng yêu cầu
                raise RideRejected("agv_busy", f"{agv_id} đang có ride {r.ride_id}")
        self._ride_n += 1
        self._seq += 1
        rid = f"{self.cfg.elevator_id}-R{self._ride_n:05d}"
        r = Ride(ride_id=rid, elevator_id=self.cfg.elevator_id, agv_id=agv_id,
                 from_floor=from_floor, to_floor=to_floor,
                 direction=self.cfg.hall_direction(from_floor, to_floor),
                 priority=priority, seq=self._seq, created_at=now, state_since=now,
                 agv_ready=not self.defer_until_ready)
        self.queue.append(r)
        self.rides[rid] = r
        self.emit(EventType.QUEUED, r, now, **{"from": from_floor, "to": to_floor})
        return rid

    def adopt_inside(self, agv_id: str, from_floor: int, to_floor: int, priority: int, now: float) -> str:
        """NHẬN LẠI chuyến của xe ĐÃ Ở TRONG CABIN mà chuyến cũ không còn (FMS vừa khởi động lại mất RAM, hoặc ride cũ lỗi
        khi xe còn trong cabin). Bỏ qua hàng đợi/gọi tầng/đón: vào thẳng pha TRANSIT như thể xe đã lên và `depart` đã gửi —
        pha TRANSIT tự xử lý mọi tình huống cabin thật: chưa rời tầng đi (gửi lại `depart`), đang đi, đã tới đích
        (→ ARRIVED → EXIT_ALLOWED), hoặc đỗ nhầm tầng khác (Transit Guard gọi lại tầng đích).
        Idempotent: xe đã có ride đang chạy → trả ride đó. Raise RideRejected nếu thang đang phục vụ xe khác."""
        reason = self.cfg.check_route(from_floor, to_floor)
        if reason:
            raise RideRejected(reason, f"{from_floor}->{to_floor}")
        act = self.active
        if act is not None:
            if act.agv_id == agv_id and act.state != RideState.RELEASING:
                return act.ride_id
            raise RideRejected("elevator_busy", f"thang đang phục vụ {act.agv_id} ({act.ride_id} {act.state.value})")
        if self.area_hold is not None and self.area_hold != agv_id:
            raise RideRejected("area_busy", f"vùng thang đang khóa cho {self.area_hold}")
        for q in [x for x in self.queue if x.agv_id == agv_id]:         # ride cũ còn xếp hàng của chính xe này → huỷ (xe đã ở trong)
            self.queue.remove(q)
            q.outcome = RideState.CANCELLED
            q.reason = "adopted"
            self._finalize(q, now)
        self._ride_n += 1
        self._seq += 1
        rid = f"{self.cfg.elevator_id}-R{self._ride_n:05d}"
        r = Ride(ride_id=rid, elevator_id=self.cfg.elevator_id, agv_id=agv_id,
                 from_floor=from_floor, to_floor=to_floor,
                 direction=self.cfg.hall_direction(from_floor, to_floor),
                 priority=priority, seq=self._seq, created_at=now, state_since=now, started_at=now,
                 board_announced=True, agv_ready=True, boarded=True)
        zone = self.zones.get(to_floor)
        if zone is not None and zone.can_acquire(agv_id):
            r.zone_floor = to_floor
            r.zone_new = zone.acquire(agv_id, now)
        self.rides[rid] = r
        self.active = r
        if self.area_gating:
            self.area_hold, self.area_hold_at = agv_id, now
        self._goto(r, RideState.TRANSIT, now)
        r.data["depart_at"] = now
        r.data["call_sent_at"] = now - self.t.call_retry_s     # chưa rời tầng xuất phát → gửi `depart` ngay lượt đầu
        r.data["adopted"] = True
        log.info("%s: NHẬN LẠI chuyến của %s đang trong cabin (%s->%s)", rid, agv_id, from_floor, to_floor)
        return rid

    def agv_boarded(self, ride_id: str, now: float) -> bool:
        r = self.rides.get(ride_id)
        if r is None or r is not self.active or r.boarded:
            return False
        ok_states = (RideState.BOARDING,)
        late_states = (RideState.WAIT_ELEVATOR, RideState.HOLDING, RideState.RECOVER_BOARD)
        if r.state in ok_states or (r.state in late_states and r.board_announced):
            # Nếu đã báo BOARD_ALLOWED mà cabin bị gọi đi giữa chừng (xe đã vào): ưu tiên chở xe đi tiếp.
            r.boarded = True
            self._goto(r, RideState.DEPARTING, now)
            return True
        log.warning("agv_boarded(%s) bị bỏ qua: ride ở %s", ride_id, r.state.value)
        return False

    def agv_exited(self, ride_id: str, now: float) -> bool:
        r = self.rides.get(ride_id)
        if r is None or r is not self.active or r.state != RideState.EXITING:
            return False
        r.exited = True
        r.outcome = RideState.COMPLETED
        self._goto(r, RideState.RELEASING, now)
        return True

    def cancel_ride(self, ride_id: str, reason: str, force: bool, now: float) -> bool:
        r = self.rides.get(ride_id)
        if r is None or r.state in TERMINAL:
            return False
        if r in self.queue:
            self.queue.remove(r)
            r.outcome = RideState.CANCELLED
            r.reason = reason
            self._finalize(r, now)
            return True
        if r is not self.active or r.state == RideState.RELEASING:
            return False
        if r.agv_inside and not force:
            log.warning("cancel_ride(%s) bị từ chối: xe đang trong cabin (dùng force=True)", ride_id)
            return False
        r.outcome = RideState.CANCELLED
        r.reason = reason
        self._goto(r, RideState.RELEASING, now)
        return True

    def force_release_zone(self, floor: int, now: float) -> bool:
        z = self.zones.get(floor)
        if z is None or not z.release():
            return False
        self.emit(EventType.ZONE_RELEASED, None, now, floor=floor, reason="forced")
        return True

    # ================================================================ tick
    def start(self, now: float) -> None:
        """Đưa mọi thiết bị về trạng thái an toàn (docs/05 §4.6)."""
        for dev in self._by_device:
            self._send(dev, P.ACT_RESET, None, now, force=True)

    def tick(self, now: float) -> None:
        self._now = now
        for p in self._by_device.values():
            p.refresh_availability(now, self.t.state_stale_s, self._link_up)
        self.channel.tick(now)
        self._expire_zones(now)
        self._expire_queue(now)
        self._admit(now)
        if self.active is not None:
            for _ in range(_MAX_STEPS_PER_TICK):
                r = self.active
                if r is None:
                    break
                before = r.state
                self._step(r, now)
                if self.active is not r or r.state == before:
                    break
        self._heal_leaks(now)
        self._prune()

    # ================================================================ admission
    def _admit(self, now: float) -> None:
        if self.active is not None or not self.queue:
            return
        for r in sorted(self.queue, key=lambda x: (-x.priority, x.seq)):
            if self.area_hold is not None and self.area_hold != r.agv_id:
                continue          # vùng thang còn xe trước chưa thoát hẳn: chưa cho gọi (hàng đợi giữ nguyên thứ tự FIFO)
            zone = self.zones.get(r.to_floor)
            if zone is not None and not zone.can_acquire(r.agv_id):
                continue          # bị Zone Lock chặn: KHÔNG chặn các ride khác (docs/05 §1)
            caller = self.callers[r.from_floor]
            # Chỉ cần Bộ gọi tầng online. Master trong cabin có thể đang mất mạng (cabin đỗ, cửa đóng):
            # gọi thang bằng Bộ gọi trước, Master có mạng lại khi cabin tới và mở cửa.
            if not caller.available(now, self.t.state_stale_s):
                continue          # Bộ gọi chưa sẵn sàng: đứng chờ trong hàng đợi
            if zone is not None:
                r.zone_floor = r.to_floor
                r.zone_new = zone.acquire(r.agv_id, now)
            self.queue.remove(r)
            self.active = r
            if self.area_gating:
                self.area_hold, self.area_hold_at = r.agv_id, now
            r.started_at = now
            self._goto(r, RideState.CALLING_HALL, now)
            self.emit(EventType.STARTED, r, now)
            return

    def agv_ready(self, ride_id: str) -> bool:
        """Xe đã tới node chờ: ride được phép gọi Bộ gọi tầng."""
        r = self.rides.get(ride_id)
        if r is None:
            return False
        r.agv_ready = True
        return True

    def release_area(self, agv_id: Optional[str] = None) -> bool:
        """Nhả khóa vùng thang (xe đã thoát hẳn / huỷ / thủ công). agv_id: chỉ nhả nếu đúng chủ khóa."""
        if self.area_hold is None or (agv_id is not None and self.area_hold != agv_id):
            return False
        log.info("%s: nhả khóa vùng thang của %s", self.cfg.elevator_id, self.area_hold)
        self.area_hold = None
        return True

    def _expire_queue(self, now: float) -> None:
        if self.t.queue_timeout_s <= 0:
            return
        for r in list(self.queue):
            if now - r.created_at > self.t.queue_timeout_s:
                self.queue.remove(r)
                r.outcome = RideState.FAILED
                r.reason = "queue_timeout"
                self._finalize(r, now)

    def _expire_zones(self, now: float) -> None:
        for z in self.zones.expired(now):
            owner = z.owner
            z.release()
            log.warning("Zone Lock tầng %d hết hạn (chủ %s)", z.floor, owner)
            self.emit(EventType.ZONE_RELEASED, None, now, floor=z.floor, reason="watchdog", owner=owner)

    # ================================================================ helpers
    def _goto(self, r: Ride, state: RideState, now: float) -> None:
        log.info("%s: %s -> %s", r.ride_id, r.state.value, state.value)
        r.state = state
        r.state_since = now
        r.cmds = {}
        r.cond = {}
        r.phase = {}

    def _cmd(self, r: Ride, key: str, device: str, typ: str, params: Optional[Dict[str, Any]], now: float) -> Command:
        c = r.cmds.get(key)
        if c is None:
            c = self._send(device, typ, params, now)
            r.cmds[key] = c
        return c

    def _run_seq(self, r: Ride, name: str, steps: List[Tuple[str, str, Optional[Dict[str, Any]]]], now: float) -> str:
        """Chạy tuần tự: bước i+1 chỉ gửi khi bước i đã FINISHED. -> 'running'|'done'|'failed'."""
        for i, (dev, typ, params) in enumerate(steps):
            c = self._cmd(r, f"{name}:{i}", dev, typ, params, now)
            if c.failed:
                return "failed"
            if not c.done:
                return "running"
        return "done"

    def _keepalive(self, r: Ride, key: str, device: str, typ: str, params: Dict[str, Any],
                   now: float, send_first: bool) -> None:
        """Làm mới TTL: gửi lại action loại `typ` với actionId MỚI mỗi ttl_refresh_s."""
        k = "ka:" + key
        last = r.phase.get(k)
        if last is None:
            r.phase[k] = now
            if send_first:
                self._send(device, typ, params, now)
            return
        if now - last >= self.t.ttl_refresh_s:
            r.phase[k] = now
            self._send(device, typ, params, now)

    def _stable(self, r: Ride, key: str, cond: bool, now: float, secs: float) -> bool:
        if not cond:
            r.cond.pop(key, None)
            return False
        t0 = r.cond.setdefault(key, now)
        return (now - t0) >= secs

    def _ms(self, now: float) -> Optional[P.MasterState]:
        st = self.master.usable_state(now, self.t.state_stale_s)
        return st if isinstance(st, P.MasterState) else None

    @staticmethod
    def _door_ok(ms: P.MasterState) -> bool:
        return ms.door_open is True or not ms.door_sensor_valid

    def _car_at(self, r: Ride, floor: int, now: float, key: str) -> bool:
        ms = self._ms(now)
        ok = ms is not None and ms.floor == floor and self._door_ok(ms)
        return self._stable(r, key, ok, now, self.t.arrival_stable_s)

    def _wrong_floor(self, r: Ride, expected: int, now: float) -> bool:
        ms = self._ms(now)
        bad = ms is not None and ms.floor is not None and ms.floor != expected
        return self._stable(r, "wrong", bad, now, self.t.wrong_floor_s)

    def _master_gone(self, now: float) -> bool:
        return self.master.unavailable_for(now) > self.t.device_offline_s

    @staticmethod
    def _over(since: float, limit: float, now: float) -> bool:
        """Quá hạn `limit` giây kể từ `since`? limit <= 0 nghĩa là CHỜ VÔ HẠN (không bao giờ quá hạn)."""
        return limit > 0 and now - since > limit

    def _fail(self, r: Ride, reason: str, now: float) -> None:
        log.warning("%s FAILED: %s", r.ride_id, reason)
        r.outcome = RideState.FAILED
        r.reason = reason
        self._goto(r, RideState.RELEASING, now)

    def _begin_recovery(self, r: Ride, now: float) -> None:
        r.recoveries += 1
        if self.t.max_recoveries and r.recoveries > self.t.max_recoveries:
            self._fail(r, "recovery_exhausted", now)
            return
        if r.state == RideState.BOARDING:
            self.emit(EventType.BOARD_REVOKED, r, now, floor=self._floor_now(now))
        self._goto(r, RideState.RECOVER_BOARD, now)

    def _floor_now(self, now: float) -> Optional[int]:
        ms = self._ms(now)
        return ms.floor if ms else None

    # ================================================================ state machine
    def _step(self, r: Ride, now: float) -> None:
        fn = {
            RideState.CALLING_HALL: self._st_calling_hall,
            RideState.WAIT_ELEVATOR: self._st_wait_elevator,
            RideState.HOLDING: self._st_holding,
            RideState.BOARDING: self._st_boarding,
            RideState.RECOVER_BOARD: self._st_recover_board,
            RideState.DEPARTING: self._st_departing,
            RideState.TRANSIT: self._st_transit,
            RideState.ARRIVED: self._st_arrived,
            RideState.EXITING: self._st_exiting,
            RideState.RELEASING: self._st_releasing,
        }.get(r.state)
        if fn is not None:
            fn(r, now)

    def _st_calling_hall(self, r: Ride, now: float) -> None:
        if not r.agv_ready:
            # xe chưa tới node chờ: chưa gọi thang; quá lâu thì bỏ (xe kẹt/hỏng — không giữ thang mãi)
            if self._over(r.state_since, self.t.elevator_wait_timeout_s, now):
                self._fail(r, "agv_not_ready", now)
            return
        caller = self.callers[r.from_floor]
        if caller.unavailable_for(now) > self.t.device_offline_s:
            return self._fail(r, "caller_offline", now)
        c = self._cmd(r, "hall", caller.device_id, P.ACT_HALL_CALL,
                      {"direction": r.direction, "ttlS": self.t.hall_ttl_s}, now)
        r.data["hall_used"] = True
        if c.status == CommandStatus.FAILED:
            return self._fail(r, f"hall_call_failed:{c.result}", now)
        if c.status == CommandStatus.EXPIRED:
            return self._fail(r, "caller_offline", now)
        cs = caller.state
        if c.done and isinstance(cs, P.CallerState) and cs.hall_active:
            return self._goto(r, RideState.WAIT_ELEVATOR, now)
        # Đã FINISHED nhưng relay không còn active (TTL hết trong lúc FMS/mạng gián đoạn): gọi lại với
        # actionId mới, nếu không ride kẹt ở đây mãi (pha này không có timeout riêng).
        fresh = caller.usable_state(now, self.t.state_stale_s)
        if (c.done and isinstance(fresh, P.CallerState) and not fresh.hall_active
                and now - c.finished_at >= self.t.hall_recall_grace_s):
            n = r.data.get("hall_recalls", 0)
            if self.t.call_retries > 0 and n >= self.t.call_retries:
                return self._fail(r, "caller_offline", now)
            r.data["hall_recalls"] = n + 1
            r.cmds.pop("hall", None)

    def _st_wait_elevator(self, r: Ride, now: float) -> None:
        # Master offline là bình thường ở đây (cabin đang đi/đỗ cửa đóng) -> chỉ có elevator_wait_timeout_s giới hạn.
        caller = self.callers[r.from_floor]
        self._keepalive(r, "hall", caller.device_id, P.ACT_HALL_CALL,
                        {"direction": r.direction, "ttlS": self.t.hall_ttl_s}, now,
                        send_first=r.recoveries > 0)
        if self._car_at(r, r.from_floor, now, "ready"):
            return self._goto(r, RideState.HOLDING, now)
        if self._over(r.state_since, self.t.elevator_wait_timeout_s, now):
            self._fail(r, "elevator_timeout", now)

    def _st_holding(self, r: Ride, now: float) -> None:
        if self._master_gone(now):
            return self._fail(r, "master_offline", now)
        m = self.master.device_id
        c = self._cmd(r, "hold", m, P.ACT_HOLD_DOOR, {"ttlS": self.t.hold_ttl_s}, now)
        if c.failed:
            return self._fail(r, "hold_failed", now)
        ms = self._ms(now)
        if not (c.done and ms is not None and ms.door_hold):
            if self._over(r.state_since, self.t.hold_timeout_s, now):
                self._fail(r, "hold_failed", now)
            return
        r.phase.setdefault("hold_ok_at", now)
        self._keepalive(r, "hold", m, P.ACT_HOLD_DOOR, {"ttlS": self.t.hold_ttl_s}, now, send_first=False)
        if self._wrong_floor(r, r.from_floor, now):
            return self._begin_recovery(r, now)
        if now - r.phase["hold_ok_at"] < self.t.hold_verify_s:
            return
        if not (ms.floor == r.from_floor and self._door_ok(ms)):
            return self._begin_recovery(r, now)       # cabin rời đi/cửa đóng trong lúc kiểm lại
        if r.data.get("hall_used"):
            caller = self.callers[r.from_floor]
            rc = self._cmd(r, "rel_hall", caller.device_id, P.ACT_RELEASE_HALL, None, now)
            if not (rc.settled or not caller.available(now, self.t.state_stale_s)):
                return
        self._goto(r, RideState.BOARDING, now)

    def _st_boarding(self, r: Ride, now: float) -> None:
        if not r.phase.get("announced"):
            r.phase["announced"] = True
            r.board_announced = True
            self.emit(EventType.BOARD_ALLOWED, r, now, floor=r.from_floor)
        # Cabin vào vùng chết Wi-Fi lúc xe đang lên: dung sai dài hơn (boarding_offline_s); lệnh giữ cửa
        # nằm trong hàng chờ và gửi lại ngay khi Master online.
        if self.master.unavailable_for(now) > max(self.t.device_offline_s, self.t.boarding_offline_s):
            return self._fail(r, "master_offline", now)
        self._warn_cabin_offline_boarding(r, now)
        self._keepalive(r, "hold", self.master.device_id, P.ACT_HOLD_DOOR,
                        {"ttlS": self.t.hold_ttl_s}, now, send_first=True)
        if self._wrong_floor(r, r.from_floor, now):
            return self._begin_recovery(r, now)
        if self._over(r.state_since, self.t.board_timeout_s, now):
            self._fail(r, "board_timeout", now)

    def _st_recover_board(self, r: Ride, now: float) -> None:
        m = self.master.device_id
        res = self._run_seq(r, "rec", [
            (m, P.ACT_RELEASE_DOOR, None),
            (m, P.ACT_FAST_CLOSE, {"durationMs": self.t.fast_close_ms}),
            (m, P.ACT_CALL_FLOOR, {"floor": r.from_floor, "pulseMs": self.t.call_pulse_ms}),
        ], now)
        if res == "done":
            self._goto(r, RideState.WAIT_ELEVATOR, now)
        elif res == "failed":
            self._fail(r, "recover_failed", now)

    def _depart_params(self, r: Ride) -> Dict[str, Any]:
        # exit_timeout_s = 0 (chờ vô hạn) -> TTL giữ cửa tối đa 600 s (Master tự làm mới nhờ keepalive của FMS)
        return {"toFloor": r.to_floor, "holdTtlS": min(int(self.t.exit_timeout_s) or 600, 600),
                "pulseMs": self.t.call_pulse_ms, "fastCloseMs": self.t.fast_close_ms}

    def _st_departing(self, r: Ride, now: float) -> None:
        """MỘT lệnh `depart` (như `Ins` của hệ cũ): Master tự nhả giữ cửa, đóng nhanh, gọi tầng và tự giữ cửa
        khi tới nơi — không phụ thuộc mạng. Chỉ cần Master NHẬN lệnh (RUNNING) là sang TRANSIT, không chờ
        FINISHED (có thể không kịp về vì cabin đóng cửa là mất mạng)."""
        m = self.master.device_id
        c = self._cmd(r, "dep", m, P.ACT_DEPART, self._depart_params(r), now)
        ms = self._ms(now)
        if c.status == CommandStatus.FAILED:
            return self._fail(r, "depart_failed", now)
        arrived = ms is not None and ms.floor == r.to_floor
        if c.done or c.accepted or arrived:
            r.data["depart_at"] = now
            r.data["call_sent_at"] = now
            return self._goto(r, RideState.TRANSIT, now)
        if c.status == CommandStatus.EXPIRED or self._over(r.state_since, self.t.transit_timeout_s, now):
            self._fail(r, "depart_failed", now)

    def _st_transit(self, r: Ride, now: float) -> None:
        t = self.t
        m = self.master.device_id
        # Cabin mất mạng khi đi là BÌNH THƯỜNG -> không fail vì offline, chỉ có transit_timeout_s giới hạn.
        self._warn_cabin_offline(r, now)
        if self._over(r.data["depart_at"], t.transit_timeout_s, now):
            return self._fail(r, "transit_timeout", now)
        ms = self._ms(now)

        # 1) đã tới đích?
        if self._car_at(r, r.to_floor, now, "arr"):
            return self._goto(r, RideState.ARRIVED, now)
        if ms is None:
            return

        # 2) Transit Guard đang chạy chuỗi khắc phục?
        gname = r.phase.get("guard_seq")
        if gname is not None:
            res = self._run_seq(r, gname, [(m, P.ACT_DEPART, self._depart_params(r))], now)
            if res == "failed":
                return self._fail(r, "transit_guard_failed", now)
            if res == "done":
                r.phase.pop("guard_seq")
                r.cond.pop("guard", None)
                r.data["call_sent_at"] = now
            return

        # 3) cabin có rời tầng xuất phát không? Không -> gửi lại xung gọi tầng (PLC bỏ lỡ xung)
        if ms.floor != r.from_floor:
            r.data["left_origin"] = True
        if not r.data.get("left_origin") and now - r.data["call_sent_at"] >= t.call_retry_s:
            n = r.data.get("call_resends", 0)
            # call_retries > 0: quá số lần gọi lại mà cabin vẫn chưa rời tầng -> FAILED (elevator_not_moving).
            # call_retries = 0 (mặc định): gọi lại mãi tới khi thang di chuyển/tới nơi — thang thật có thể chậm hơn 80 s.
            if t.call_retries > 0 and n >= t.call_retries:
                return self._fail(r, "elevator_not_moving", now)
            r.data["call_resends"] = n + 1
            r.data["call_sent_at"] = now
            # Master đang tự canh depart (tự gọi lại tầng) -> FMS chỉ đếm; không canh nữa thì đặt lại depart.
            if ms.depart_phase is None:            # Master không còn canh depart (vd khởi động lại) -> đặt lại
                self._send(m, P.ACT_DEPART, self._depart_params(r), now)

        # 4) Transit Guard: cabin dừng ở tầng thật ≠ đích
        if ms.floor is not None and ms.floor != r.to_floor:
            if ms.door_sensor_valid:
                cond, need = ms.door_open is True, t.transit_guard_s
            else:
                cond = ms.floor != r.from_floor or bool(r.data.get("left_origin"))
                need = t.transit_guard_nodoor_s
            if r.phase.get("guard_floor") != ms.floor:
                r.phase["guard_floor"] = ms.floor
                r.cond.pop("guard", None)
            if self._stable(r, "guard", cond, now, need):
                n = r.data.get("guards", 0) + 1
                r.data["guards"] = n
                if t.max_recoveries and n > t.max_recoveries:
                    return self._fail(r, "transit_stuck", now)
                log.warning("%s: Transit Guard #%d — kẹt ở tầng %s, gọi lại tầng %s",
                            r.ride_id, n, ms.floor, r.to_floor)
                self.emit(EventType.WARNING, r, now, reason="transit_guard", stuck_floor=ms.floor, attempt=n)
                r.phase["guard_seq"] = f"guard{n}"
        else:
            r.cond.pop("guard", None)

    def _warn_cabin_offline_boarding(self, r: Ride, now: float) -> None:
        if self.master.unavailable_for(now) > self.t.device_offline_s and not r.data.get("offline_warned"):
            r.data["offline_warned"] = True
            self.emit(EventType.WARNING, r, now, reason="cabin_offline", agv_inside=r.agv_inside)

    def _warn_cabin_offline(self, r: Ride, now: float) -> None:
        if self._master_gone(now) and not r.data.get("offline_warned"):
            r.data["offline_warned"] = True
            self.emit(EventType.WARNING, r, now, reason="cabin_offline", agv_inside=r.agv_inside)

    def _st_arrived(self, r: Ride, now: float) -> None:
        self._warn_cabin_offline(r, now)
        c = self._cmd(r, "hold", self.master.device_id, P.ACT_HOLD_DOOR, {"ttlS": self.t.hold_ttl_s}, now)
        if c.failed:
            return self._fail(r, "arrive_hold_failed", now)
        ms = self._ms(now)
        if c.done and ms is not None and ms.door_hold:
            self.emit(EventType.EXIT_ALLOWED, r, now, floor=r.to_floor)
            return self._goto(r, RideState.EXITING, now)
        if self._over(r.state_since, self.t.hold_timeout_s, now):
            self._fail(r, "arrive_hold_failed", now)

    def _st_exiting(self, r: Ride, now: float) -> None:
        self._warn_cabin_offline(r, now)
        self._keepalive(r, "hold", self.master.device_id, P.ACT_HOLD_DOOR,
                        {"ttlS": self.t.hold_ttl_s}, now, send_first=False)
        if self._over(r.state_since, self.t.exit_timeout_s, now):
            self._fail(r, "exit_timeout", now)

    def _st_releasing(self, r: Ride, now: float) -> None:
        cmds: List[Tuple[Command, DeviceProxy]] = []
        if r.data.get("hall_used"):
            caller = self.callers[r.from_floor]
            cmds.append((self._cmd(r, "rel_hall", caller.device_id, P.ACT_RELEASE_HALL, None, now), caller))
        cmds.append((self._cmd(r, "rel_door", self.master.device_id, P.ACT_RELEASE_DOOR, None, now), self.master))
        pending = [(c, p) for c, p in cmds
                   if not c.settled and p.available(now, self.t.state_stale_s)]
        if not pending:
            return self._finalize(r, now)
        if now - r.state_since > self.t.cleanup_timeout_s:
            self.emit(EventType.WARNING, r, now, reason="cleanup_unconfirmed",
                      devices=[p.device_id for _, p in pending])
            self._finalize(r, now)

    # ================================================================ finalize
    def _finalize(self, r: Ride, now: float) -> None:
        outcome = r.outcome or RideState.FAILED
        r.state = outcome
        r.state_since = now
        r.finished_at = now
        r.cmds, r.cond, r.phase = {}, {}, {}
        if self.active is r:
            self.active = None

        # --- Zone Lock (docs/05 §4.4) ---
        if outcome == RideState.COMPLETED:
            # xe chủ khóa về tới release_floor (mặc định tầng thấp nhất) -> nhả mọi khóa nó đang giữ
            for zl in self.zones.owned_by(r.agv_id):
                if r.to_floor == zl.release_floor and zl.release(r.agv_id):
                    self.emit(EventType.ZONE_RELEASED, r, now, floor=zl.floor, reason="owner_returned_to_release_floor")
        elif outcome != RideState.COMPLETED and r.zone_floor is not None and r.zone_new and not r.boarded:
            z = self.zones.get(r.zone_floor)
            if z is not None and z.release(r.agv_id):
                self.emit(EventType.ZONE_RELEASED, r, now, floor=r.zone_floor, reason="ride_aborted_before_boarding")

        if outcome == RideState.COMPLETED:
            self.emit(EventType.COMPLETED, r, now)
        elif outcome == RideState.CANCELLED:
            self.emit(EventType.CANCELLED, r, now, reason=r.reason)
        else:
            self.emit(EventType.FAILED, r, now, reason=r.reason, agv_inside=r.agv_inside)
        log.info("%s kết thúc: %s %s", r.ride_id, outcome.value, r.reason)

    def _prune(self) -> None:
        done = [r for r in self.rides.values() if r.state in TERMINAL]
        if len(done) > _KEEP_HISTORY:
            done.sort(key=lambda x: x.finished_at or 0.0)
            for r in done[: len(done) - _KEEP_HISTORY]:
                del self.rides[r.ride_id]

    # ================================================================ tự chữa rò rỉ
    def _heal_leaks(self, now: float) -> None:
        owned_floor = self.active.from_floor if self.active else None
        for p in [self.master, *self.callers.values()]:
            st = p.usable_state(now, self.t.state_stale_s)
            if st is None:
                p.leak_since = None
                continue
            if isinstance(st, P.MasterState):
                leaking = st.door_hold and self.active is None
            else:
                leaking = st.hall_active and not (self.active is not None and st.floor == owned_floor)
            if not leaking:
                p.leak_since = None
                continue
            if p.leak_since is None:
                p.leak_since = now
            if (now - p.leak_since >= self.t.leak_grace_s
                    and now - p.last_reset_at >= self.t.leak_reset_interval_s):
                p.last_reset_at = now
                log.warning("thiết bị %s rò rỉ relay không có ride sở hữu -> reset", p.device_id)
                self.emit(EventType.WARNING, None, now, reason="leak_reset", device=p.device_id)
                self._send(p.device_id, P.ACT_RESET, None, now)

    # ================================================================ snapshot
    def snapshot(self, now: float) -> Dict[str, Any]:
        def dev(p: DeviceProxy) -> Dict[str, Any]:
            return {"available": p.available(now, self.t.state_stale_s), "connection": p.connection}
        ms = self.master.state if isinstance(self.master.state, P.MasterState) else None
        return {
            "elevator_id": self.cfg.elevator_id,
            "floor": ms.floor if ms else None,
            "door_open": ms.door_open if ms else None,
            "door_hold": ms.door_hold if ms else None,
            "active": self.active.public() if self.active else None,
            "queue": [r.public() for r in sorted(self.queue, key=lambda x: (-x.priority, x.seq))],
            "area_hold": ({"agv_id": self.area_hold, "since_s": round(now - self.area_hold_at, 1)}
                          if self.area_hold is not None else None),
            "zones": self.zones.snapshot(),
            "devices": {p.device_id: dev(p) for p in self._by_device.values()},
        }


class ElevatorCoordinator:
    """Facade cho FMS. Xem docs/07-tich-hop-fms.md."""

    def __init__(self, config: CoordinatorConfig, transport: Transport,
                 clock: Optional[Clock] = None, on_event: Optional[EventCallback] = None) -> None:
        config.validate()
        self.config = config
        self.transport = transport
        self.clock: Clock = clock or SystemClock()
        self._on_event = on_event
        self._events: Deque[RideEvent] = deque(maxlen=1000)
        self._lock = threading.RLock()
        self._started = False
        self.stats = {"bad_messages": 0, "unknown_device_messages": 0}
        self.units: Dict[str, ElevatorUnit] = {
            e.elevator_id: ElevatorUnit(e, config.factory, transport, self.clock, self._emit)
            for e in config.elevators}
        self._ride_unit: Dict[str, ElevatorUnit] = {}

    # ---- vòng đời ----
    def set_link_state(self, up: bool) -> None:
        """Báo kết nối của CHÍNH FMS tới broker (gọi từ on_connect/on_disconnect của MQTT client).
        Mất broker thì mọi state thiết bị cũ đi — đó là lỗi của FMS, không phải của thiết bị: tạm dừng
        đếm `device_offline_s` và gửi lệnh; có mạng lại thì đếm từ đầu và gửi bù lệnh trong hàng chờ."""
        with self._lock:
            for u in self.units.values():
                u.set_link(up)

    def start(self) -> None:
        with self._lock:
            hook = getattr(self.transport, "set_link_handler", None)
            if hook is not None:
                hook(self.set_link_state)
            self.transport.set_message_handler(self.on_message)
            for e in self.config.elevators:
                self.transport.subscribe(P.state_filter(self.config.factory, e.elevator_id), 0)
                self.transport.subscribe(P.connection_filter(self.config.factory, e.elevator_id), 1)
            now = self.clock.monotonic()
            for u in self.units.values():
                u.start(now)
            self._started = True

    def stop(self) -> None:
        """Dừng chủ động: nhả mọi thiết bị (reset) rồi không xử lý nữa."""
        with self._lock:
            now = self.clock.monotonic()
            for u in self.units.values():
                for dev in u._by_device:
                    u._send(dev, P.ACT_RESET, None, now)
            self._started = False

    # ---- vòng lặp ----
    def tick(self) -> None:
        with self._lock:
            if not self._started:
                return
            now = self.clock.monotonic()
            for u in self.units.values():
                u.tick(now)

    def on_message(self, topic: str, payload: bytes) -> None:
        with self._lock:
            parsed = P.parse_topic(topic)
            if parsed is None:
                return
            factory, elev, device, kind = parsed
            unit = self.units.get(elev)
            if factory != self.config.factory or unit is None or device not in unit._by_device:
                self.stats["unknown_device_messages"] += 1
                return
            now = self.clock.monotonic()
            try:
                if kind == "state":
                    proxy = unit._by_device[device]
                    unit.on_state(device, P.parse_state(proxy.kind, payload), now)
                elif kind == "connection":
                    unit.on_connection(device, P.parse_connection(payload))
            except P.ProtocolError as e:
                self.stats["bad_messages"] += 1
                log.warning("message hỏng %s: %s", topic, e)

    # ---- API cho FMS ----
    def request_ride(self, agv_id: str, from_floor: int, to_floor: int, *,
                     elevator_id: Optional[str] = None, priority: int = 0) -> str:
        with self._lock:
            ecfg = self.config.get(elevator_id)
            if ecfg is None:
                raise RideRejected("unknown_elevator", str(elevator_id))
            unit = self.units[ecfg.elevator_id]
            rid = unit.request_ride(agv_id, from_floor, to_floor, priority, self.clock.monotonic())
            self._ride_unit[rid] = unit
            return rid

    def adopt_inside(self, agv_id: str, from_floor: int, to_floor: int, *,
                     elevator_id: Optional[str] = None, priority: int = 0) -> str:
        """Nhận lại chuyến của xe đã ở trong cabin (xem ElevatorUnit.adopt_inside)."""
        with self._lock:
            ecfg = self.config.get(elevator_id)
            if ecfg is None:
                raise RideRejected("unknown_elevator", str(elevator_id))
            unit = self.units[ecfg.elevator_id]
            rid = unit.adopt_inside(agv_id, from_floor, to_floor, priority, self.clock.monotonic())
            self._ride_unit[rid] = unit
            return rid

    def agv_boarded(self, ride_id: str) -> bool:
        with self._lock:
            u = self._ride_unit.get(ride_id)
            return bool(u and u.agv_boarded(ride_id, self.clock.monotonic()))

    def agv_exited(self, ride_id: str) -> bool:
        with self._lock:
            u = self._ride_unit.get(ride_id)
            return bool(u and u.agv_exited(ride_id, self.clock.monotonic()))

    def cancel_ride(self, ride_id: str, reason: str = "cancelled", force: bool = False) -> bool:
        with self._lock:
            u = self._ride_unit.get(ride_id)
            return bool(u and u.cancel_ride(ride_id, reason, force, self.clock.monotonic()))

    def set_defer_until_ready(self, enabled: bool, elevator_id: Optional[str] = None) -> None:
        """Bật: ride chỉ gọi Bộ gọi tầng sau agv_ready(ride_id) (mặc định TẮT cho test/sim cũ)."""
        with self._lock:
            for eid, u in self.units.items():
                if elevator_id is None or eid == elevator_id:
                    u.defer_until_ready = bool(enabled)

    def agv_ready(self, ride_id: str) -> bool:
        with self._lock:
            u = self._ride_unit.get(ride_id)
            return bool(u and u.agv_ready(ride_id))

    def set_area_gating(self, enabled: bool, elevator_id: Optional[str] = None) -> None:
        """Bật/tắt cổng khóa vùng thang (mặc định TẮT — các test/sim cũ không phải gọi release_area)."""
        with self._lock:
            for eid, u in self.units.items():
                if elevator_id is None or eid == elevator_id:
                    u.area_gating = bool(enabled)
                    if not enabled:
                        u.area_hold = None

    def release_area(self, elevator_id: str, agv_id: Optional[str] = None) -> bool:
        with self._lock:
            u = self.units.get(elevator_id)
            return bool(u and u.release_area(agv_id))

    def force_release_zone(self, floor: int, elevator_id: Optional[str] = None) -> bool:
        with self._lock:
            ecfg = self.config.get(elevator_id)
            return bool(ecfg and self.units[ecfg.elevator_id].force_release_zone(floor, self.clock.monotonic()))

    def get_ride(self, ride_id: str) -> Optional[Ride]:
        with self._lock:
            u = self._ride_unit.get(ride_id)
            return u.rides.get(ride_id) if u else None

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            now = self.clock.monotonic()
            return {"elevators": [u.snapshot(now) for u in self.units.values()], "stats": dict(self.stats)}

    def poll_events(self) -> List[RideEvent]:
        with self._lock:
            out = list(self._events)
            self._events.clear()
            return out

    # ---- nội bộ ----
    def _emit(self, ev: RideEvent) -> None:
        self._events.append(ev)
        if self._on_event is not None:
            try:
                self._on_event(ev)
            except Exception:
                log.exception("on_event callback lỗi")
