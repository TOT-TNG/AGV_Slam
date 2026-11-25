"""
elevator_coord — Module điều phối thang máy cho AGV (MQTT / VDA5050-aligned).

Tài liệu: elevator/docs/. Điểm vào cho FMS:

    from elevator_coord import ElevatorCoordinator, CoordinatorConfig, PahoTransport
    cfg   = CoordinatorConfig.from_file("elevator/config/elevator.example.json")
    coord = ElevatorCoordinator(cfg, PahoTransport(existing_paho_client), on_event=handle_event)
    coord.start()
    ...
    rid = coord.request_ride("AGV01", from_floor=1, to_floor=3)
    # mỗi 100–500 ms:  coord.tick()
"""
from .clock import Clock, FakeClock, SystemClock
from .config import (CallerConfig, ConfigError, CoordinatorConfig, ElevatorConfig, Timing, ZoneConfig,
                     default_config)
from .coordinator import ElevatorCoordinator
from .ride import EventType, Ride, RideEvent, RideRejected, RideState
from .transport import PahoTransport, Transport

__all__ = [
    "Clock", "FakeClock", "SystemClock",
    "CallerConfig", "ConfigError", "CoordinatorConfig", "ElevatorConfig", "Timing", "ZoneConfig", "default_config",
    "ElevatorCoordinator", "EventType", "Ride", "RideEvent", "RideRejected", "RideState",
    "PahoTransport", "Transport",
]
__version__ = "1.0.0"
