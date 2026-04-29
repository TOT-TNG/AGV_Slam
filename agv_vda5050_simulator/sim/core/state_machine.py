from __future__ import annotations

from enum import Enum


class AGVMode(str, Enum):
    STARTUP = 'STARTUP'
    AUTOMATIC = 'AUTOMATIC'
    SEMIAUTOMATIC = 'SEMIAUTOMATIC'
    MANUAL = 'MANUAL'
    INTERVENED = 'INTERVENED'
    SERVICE = 'SERVICE'
    TEACH_IN = 'TEACH_IN'


class AGVRunState(str, Enum):
    IDLE = 'IDLE'
    MOVING = 'MOVING'
    PAUSED = 'PAUSED'
    ACTION = 'ACTION'
    FINISHED = 'FINISHED'
    FAILED = 'FAILED'
    POWER_OFF = 'POWER_OFF'
