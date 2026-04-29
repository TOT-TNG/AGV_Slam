from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from typing import Any, Optional

from sim.vda5050.mqtt_client import MQTTSettings

try:
    import paho.mqtt.client as mqtt
except Exception:  # pragma: no cover
    mqtt = None


class ElevatorCommandError(ValueError):
    pass


@dataclass
class ElevatorAgent:
    elevator_id: int
    node_id: str
    mqtt_settings: MQTTSettings
    floors: list[int] = field(default_factory=lambda: [0])
    floor_nodes: dict[int, str] = field(default_factory=dict)
    current_floor: int = 0
    target_floor: int = 0
    door: str = 'closed'
    status: str = 'idle'
    occupied_by: str = ''
    travel_time_per_floor_s: float = 2.0

    def __post_init__(self) -> None:
        self.elevator_id = int(self.elevator_id)
        self.floors = sorted({int(floor) for floor in self.floors} or {int(self.current_floor)})
        self.current_floor = int(self.current_floor)
        self.target_floor = int(self.target_floor or self.current_floor)
        self.floor_nodes = {int(floor): str(node_id) for floor, node_id in self.floor_nodes.items()}
        if not self.floor_nodes:
            self.floor_nodes = {floor: self.node_id for floor in self.floors}
        self._move_remaining_s = 0.0
        self._lock = threading.RLock()
        self._connected = False
        self._last_publish_s = 0.0
        self.last_error = ''
        self.last_publish_topic = ''
        self.last_publish_ok = False
        self.client: Optional[Any] = None
        self._enabled = self.mqtt_settings.enabled and mqtt is not None
        if self._enabled:
            self.client = mqtt.Client(client_id=f'sim_elevator_{self.elevator_id}', protocol=mqtt.MQTTv311)
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.reconnect_delay_set(min_delay=1, max_delay=10)
            self.connect()
        elif mqtt is None:
            self.last_error = 'paho-mqtt is not installed'
        else:
            self.last_error = 'MQTT disabled by config'

    @property
    def topic(self) -> str:
        return f'/elevator{self.elevator_id}/state'

    def connect(self) -> None:
        if not self._enabled or self.client is None:
            return
        try:
            self.client.connect_async(self.mqtt_settings.host, self.mqtt_settings.port, self.mqtt_settings.keepalive)
            self.client.loop_start()
            self.last_error = ''
        except Exception as exc:
            self._connected = False
            self.last_error = str(exc)

    def disconnect(self) -> None:
        if not self._enabled or self.client is None:
            return
        try:
            self.client.loop_stop()
            self.client.disconnect()
        except Exception:
            pass
        self._connected = False

    def publish_state(self, *, retain: bool = False) -> bool:
        with self._lock:
            self.last_publish_topic = self.topic
            self.last_publish_ok = False
            if not self._enabled or self.client is None:
                return False
            if not self._connected:
                self.last_error = 'MQTT is offline'
                return False
            try:
                self.client.publish(self.topic, json.dumps(self.build_state()), qos=0, retain=retain)
                self.last_publish_ok = True
                self.last_error = ''
                return True
            except Exception as exc:
                self._connected = False
                self.last_error = str(exc)
                return False

    def build_state(self) -> dict[str, Any]:
        return {
            'elevator_id': self.elevator_id,
            'current_floor': self.current_floor,
            'target_floor': self.target_floor,
            'door': self.door,
            'status': self.status,
            'occupied_by': self.occupied_by,
        }

    def snapshot(self) -> dict[str, Any]:
        return {
            **self.build_state(),
            'node_id': self.node_id,
            'floors': list(self.floors),
            'floor_nodes': {str(k): v for k, v in sorted(self.floor_nodes.items())},
            'travel_time_per_floor_s': self.travel_time_per_floor_s,
        }

    def call(self, *, job_id: str, floor: int) -> dict[str, Any]:
        with self._lock:
            self._require_job(job_id)
            self._require_floor(floor)
            self.door = 'closed'
            self._start_move(int(floor))
            self.publish_state()
            return self.build_state()

    def open_door(self, *, job_id: str) -> dict[str, Any]:
        with self._lock:
            self._require_job(job_id)
            if self.status == 'moving':
                raise ElevatorCommandError('Cannot open door while elevator is moving')
            self.door = 'open'
            self.status = 'door_open'
            self.publish_state()
            return self.build_state()

    def close_door(self, *, job_id: str) -> dict[str, Any]:
        with self._lock:
            self._require_job(job_id)
            self.door = 'closed'
            if self.status == 'door_open':
                self.status = 'idle'
            self.publish_state()
            return self.build_state()

    def go(self, *, job_id: str, target_floor: int) -> dict[str, Any]:
        with self._lock:
            self._require_job(job_id)
            self._require_floor(target_floor)
            if self.door != 'closed':
                raise ElevatorCommandError('Close door before moving elevator')
            self._start_move(int(target_floor))
            self.publish_state()
            return self.build_state()

    def release(self, *, job_id: str) -> dict[str, Any]:
        with self._lock:
            self._require_job(job_id)
            if self.status == 'moving':
                raise ElevatorCommandError('Cannot release elevator while it is moving')
            self.occupied_by = ''
            self.status = 'idle'
            self.publish_state()
            return self.build_state()

    def update(self, dt: float) -> bool:
        with self._lock:
            if self.status != 'moving':
                return False
            self._move_remaining_s = max(0.0, self._move_remaining_s - dt)
            if self._move_remaining_s > 0.0:
                return False
            self.current_floor = self.target_floor
            self.status = 'idle'
            self.publish_state()
            return True

    def set_occupied_by(self, agv_id: str) -> None:
        with self._lock:
            self.occupied_by = agv_id

    def floor_node(self, floor: int) -> Optional[str]:
        return self.floor_nodes.get(int(floor))

    def _start_move(self, target_floor: int) -> None:
        self.target_floor = int(target_floor)
        if self.target_floor == self.current_floor:
            self.status = 'idle'
            self._move_remaining_s = 0.0
            return
        self.status = 'moving'
        self._move_remaining_s = max(0.1, abs(self.target_floor - self.current_floor) * self.travel_time_per_floor_s)

    def _require_floor(self, floor: int) -> None:
        if int(floor) not in self.floors:
            raise ElevatorCommandError(f'Floor {floor} is not served by elevator {self.elevator_id}')

    @staticmethod
    def _require_job(job_id: str) -> None:
        if not str(job_id).strip():
            raise ElevatorCommandError('job_id is required')

    def _on_connect(self, client: Any, userdata: Any, flags: Any, rc: int, properties: Any = None) -> None:
        self._connected = (rc == 0)
        if self._connected:
            self.last_error = ''
            self.publish_state(retain=True)
        else:
            self.last_error = f'MQTT connect rc={rc}'

    def _on_disconnect(self, client: Any, userdata: Any, rc: int, properties: Any = None) -> None:
        self._connected = False
        if rc != 0:
            self.last_error = f'MQTT disconnected rc={rc}'
