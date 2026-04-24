from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np


@dataclass(slots=True)
class VadDecision:
    active: bool
    speech_confidence: float
    silence_ms: int


class VadService(Protocol):
    def detect(self, frame: np.ndarray, *, sample_rate: int) -> VadDecision:
        """Return normalized speech-activity state for one frame."""


class SileroVadService:
    def __init__(self, *, model: Any | None = None, threshold: float = 0.5, min_silence_ms: int = 600) -> None:
        self._model = model or self._load_default_model()
        self._threshold = threshold
        self._min_silence_ms = min_silence_ms
        self._silence_ms = 0
        self._speech_active = False

    def detect(self, frame: np.ndarray, *, sample_rate: int) -> VadDecision:
        score = self._score(frame, sample_rate=sample_rate)
        frame_ms = max(int(round((len(frame) / max(sample_rate, 1)) * 1000)), 1)

        if score >= self._threshold:
            self._silence_ms = 0
            self._speech_active = True
        else:
            self._silence_ms += frame_ms
            if self._silence_ms >= self._min_silence_ms:
                self._speech_active = False

        return VadDecision(
            active=self._speech_active,
            speech_confidence=score,
            silence_ms=self._silence_ms,
        )

    @staticmethod
    def _load_default_model() -> Any:
        try:
            from silero_vad import load_silero_vad
        except ImportError as exc:  # pragma: no cover - exercised only when dependency is absent
            raise RuntimeError("silero-vad is not installed") from exc

        return load_silero_vad()

    def _score(self, frame: np.ndarray, *, sample_rate: int) -> float:
        result = self._model(frame, sample_rate)
        if hasattr(result, "item"):
            return float(result.item())
        return float(result)
