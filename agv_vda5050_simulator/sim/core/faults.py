from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class FaultManager:
    errors: List[Dict[str, str]] = field(default_factory=list)

    def add(self, error_type: str, description: str, level: str) -> None:
        self.remove(error_type)
        self.errors.append({
            'errorType': error_type,
            'errorDescription': description,
            'errorLevel': level,
        })

    def remove(self, error_type: str) -> None:
        self.errors = [item for item in self.errors if item.get('errorType') != error_type]

    def clear(self) -> None:
        self.errors.clear()

    def has_error_level(self, *levels: str) -> bool:
        valid = set(levels)
        return any(item.get('errorLevel') in valid for item in self.errors)

    def blocking(self) -> bool:
        return self.has_error_level('ERROR', 'FATAL')
