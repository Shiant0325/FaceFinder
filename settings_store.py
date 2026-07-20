from __future__ import annotations

from pathlib import Path
from typing import Dict

from utils import read_json, write_json

DEFAULT_SETTINGS = {
    "setup_completed": False,
    "device_mode": "auto",
    "detector_size": 320,
    "threshold": 0.50,
    "min_size_kb": 8,
    "output_base": "",
    "last_destination": "",
}


class SettingsStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.values: Dict = {**DEFAULT_SETTINGS, **read_json(self.path, {})}

    def get(self, key: str, default=None):
        return self.values.get(key, default)

    def set(self, key: str, value) -> None:
        self.values[key] = value
        self.save()

    def update(self, **values) -> None:
        self.values.update(values)
        self.save()

    def save(self) -> None:
        write_json(self.path, self.values)
