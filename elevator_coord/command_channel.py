"""
command_channel.py — Gửi lệnh tin cậy tới thiết bị (docs/04 §6).

Mỗi lệnh có `actionId`; gửi lặp CÙNG actionId mỗi `retry_s` tới khi thấy nó trong
`state.actionStates` với FINISHED/FAILED. Thiết bị khử trùng theo actionId nên lặp không
thực thi lại (xung `callFloor` chỉ chạy một lần).
"""
from __future__ import annotations

import enum
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from . import protocol as P

log = logging.getLogger("elevator_coord.cmd")


class CommandStatus(str, enum.Enum):
    PENDING = "PENDING"
    FINISHED = "FINISHED"
    FAILED = "FAILED"      # thiết bị trả FAILED
    EXPIRED = "EXPIRED"    # hết số lần gửi mà không thấy phản hồi


@dataclass
class Command:
    action_id: str
    device_id: str
    action_type: str
    params: Dict[str, Any]
    created_at: float
    last_sent: float = 0.0
    sends: int = 0
    status: CommandStatus = CommandStatus.PENDING
    result: str = ""
    finished_at: float = 0.0
    accepted: bool = False      # thiết bị đã báo RUNNING/FINISHED (nhận lệnh) — dùng khi FINISHED có thể không kịp về (mất mạng)

    @property
    def done(self) -> bool:
        return self.status == CommandStatus.FINISHED

    @property
    def failed(self) -> bool:
        return self.status in (CommandStatus.FAILED, CommandStatus.EXPIRED)

    @property
    def settled(self) -> bool:
        return self.status != CommandStatus.PENDING


class CommandChannel:
    def __init__(self, publish_action: Callable[[str, Dict[str, Any]], None],
                 retry_s: float, max_retries: int,
                 id_factory: Callable[[], str] = P.new_action_id,
                 keep_settled_s: float = 60.0,
                 is_available: Optional[Callable[[str], bool]] = None) -> None:
        """is_available(device_id): thiết bị đang ONLINE + state còn mới? Offline -> GIỮ lệnh trong hàng chờ,
        KHÔNG gửi và KHÔNG tính số lần gửi lặp; ngay khi online lại thì gửi (cabin đóng cửa có thể mất mạng hàng giờ)."""
        self._avail = is_available or (lambda _d: True)
        self._publish = publish_action
        self._retry_s = retry_s
        self._max_retries = max_retries
        self._new_id = id_factory
        self._keep_settled_s = keep_settled_s
        self._cmds: Dict[str, Command] = {}

    def send(self, device_id: str, action_type: str, params: Optional[Dict[str, Any]], now: float,
             force: bool = False) -> Command:
        cmd = Command(self._new_id(), device_id, action_type, dict(params or {}), created_at=now,
                      last_sent=-1e9)
        self._cmds[cmd.action_id] = cmd
        if force or self._avail(device_id):      # force: gửi ngay dù chưa biết presence (reset lúc khởi động)
            self._transmit(cmd, now)
        return cmd

    def _transmit(self, cmd: Command, now: float) -> None:
        cmd.sends += 1
        cmd.last_sent = now
        self._publish(cmd.device_id, P.action_dict(cmd.action_type, cmd.action_id, cmd.params))

    def on_action_states(self, device_id: str, states: List[P.ActionState], now: float) -> None:
        for s in states:
            cmd = self._cmds.get(s.action_id)
            if cmd is None or cmd.device_id != device_id:
                continue
            if cmd.status == CommandStatus.EXPIRED and s.status == P.ST_FINISHED:
                cmd.status = CommandStatus.FINISHED        # xác nhận đến muộn (thiết bị vừa online lại): vẫn tính là xong
                cmd.finished_at = now
                continue
            if cmd.settled:
                continue
            if s.status in (P.ST_RUNNING, P.ST_FINISHED):
                cmd.accepted = True
            if s.status == P.ST_FINISHED:
                cmd.status = CommandStatus.FINISHED
            elif s.status == P.ST_FAILED:
                cmd.status = CommandStatus.FAILED
                cmd.result = s.result
                log.warning("lệnh %s/%s FAILED: %s", device_id, cmd.action_type, s.result)
            else:
                continue
            cmd.finished_at = now

    def tick(self, now: float) -> None:
        for cmd in list(self._cmds.values()):
            if cmd.settled:
                if now - cmd.finished_at > self._keep_settled_s:
                    del self._cmds[cmd.action_id]
                continue
            if not self._avail(cmd.device_id):
                continue                          # offline: giữ lệnh, không đếm lần gửi
            if now - cmd.last_sent < self._retry_s:
                continue
            if cmd.sends > self._max_retries:
                cmd.status = CommandStatus.EXPIRED
                cmd.finished_at = now
                log.warning("lệnh %s/%s EXPIRED sau %d lần gửi", cmd.device_id, cmd.action_type, cmd.sends)
                continue
            self._transmit(cmd, now)

    def pending(self) -> List[Command]:
        return [c for c in self._cmds.values() if not c.settled]
