from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Sequence

import sounddevice as sd


@dataclass(slots=True)
class AudioDevice:
    id: str
    label: str
    kind: Literal["input", "loopback"]


@dataclass(slots=True)
class DeviceValidationResult:
    is_valid: bool
    reason: str | None = None


class DeviceService:
    def __init__(self, devices: Sequence[AudioDevice] | None = None) -> None:
        self._override_devices = list(devices) if devices else None

    def list_devices(self) -> list[AudioDevice]:
        if self._override_devices is not None:
            return list(self._override_devices)
        return self._query_system_devices()

    def validate_microphone(self, device_id: str) -> DeviceValidationResult:
        for device in self.list_devices():
            if device.id == device_id:
                return DeviceValidationResult(is_valid=True)
        return DeviceValidationResult(is_valid=False, reason=f"Unknown microphone device: {device_id}")

    @staticmethod
    def _query_system_devices() -> list[AudioDevice]:
        result: list[AudioDevice] = []
        raw = sd.query_devices()
        devices: list[dict[str, Any]] = list(raw) if not isinstance(raw, dict) else [raw]
        for dev in devices:
            if dev["max_input_channels"] > 0:
                name = dev["name"]
                kind: Literal["input", "loopback"] = (
                    "loopback" if "blackhole" in name.lower() else "input"
                )
                result.append(AudioDevice(id=name, label=name, kind=kind))
        return result
