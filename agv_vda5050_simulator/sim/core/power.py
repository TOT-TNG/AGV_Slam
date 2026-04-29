from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PowerManager:
    power_on: bool = True

    def shutdown(self) -> None:
        self.power_on = False

    def startup(self) -> None:
        self.power_on = True
