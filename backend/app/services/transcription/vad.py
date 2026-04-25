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

    def reset(self) -> None:
        """Reset internal state at utterance boundaries."""


class SileroVadService:
    def __init__(self, *, model: Any | None = None, threshold: float = 0.5, min_silence_ms: int = 600) -> None:
        self._model = model or self._load_default_model()
        self._threshold = threshold
        self._min_silence_ms = min_silence_ms
        self._silence_ms = 0
        self._post_speech_silence_ms = 0
        self._speech_active = False

    def detect(self, frame: np.ndarray, *, sample_rate: int) -> VadDecision:
        score = self._score(frame, sample_rate=sample_rate)
        frame_ms = max(int(round((len(frame) / max(sample_rate, 1)) * 1000)), 1)

        if score >= self._threshold:
            self._silence_ms = 0
            self._post_speech_silence_ms = 0
            self._speech_active = True
        else:
            self._silence_ms += frame_ms
            if self._silence_ms >= self._min_silence_ms:
                if self._speech_active:
                    # Speech just went inactive — start counting
                    # post-speech silence from zero so downstream
                    # segmentation has a clean window to evaluate.
                    self._post_speech_silence_ms = 0
                    self._speech_active = False
                else:
                    self._post_speech_silence_ms += frame_ms

        return VadDecision(
            active=self._speech_active,
            speech_confidence=score,
            silence_ms=self._post_speech_silence_ms,
        )

    def reset(self) -> None:
        """Reset model hidden state and counters at utterance boundaries."""
        # if hasattr(self._model, "reset_states"):
        #     self._model.reset_states()
        self._silence_ms = 0
        self._post_speech_silence_ms = 0
        self._speech_active = False

    @staticmethod
    def _load_default_model() -> Any:
        try:
            from silero_vad import load_silero_vad
        except ImportError as exc:  # pragma: no cover - exercised only when dependency is absent
            raise RuntimeError("silero-vad is not installed") from exc

        return load_silero_vad()

    def _score(self, frame: np.ndarray, *, sample_rate: int) -> float:
        try:
            import torch
        except ImportError:
            torch = None

        scores: list[float] = []
        for chunk in self._iter_model_chunks(frame, sample_rate=sample_rate, torch_module=torch):
            result = self._model(chunk, sample_rate)
            if hasattr(result, "item"):
                scores.append(float(result.item()))
            else:
                scores.append(float(result))

        if not scores:
            return 0.0
        return max(scores)

    @staticmethod
    def _iter_model_chunks(frame: np.ndarray, *, sample_rate: int, torch_module: Any | None):
        chunk_size = SileroVadService._chunk_size(sample_rate)
        samples = np.asarray(frame, dtype=np.float32).reshape(-1)
        if samples.size == 0:
            return

        remainder = samples.size % chunk_size
        if remainder:
            pad_width = chunk_size - remainder
            samples = np.pad(samples, (0, pad_width))

        for start in range(0, samples.size, chunk_size):
            chunk = samples[start : start + chunk_size]
            if torch_module is not None:
                yield torch_module.as_tensor(chunk)
            else:
                yield chunk

    @staticmethod
    def _chunk_size(sample_rate: int) -> int:
        if sample_rate == 16_000:
            return 512
        if sample_rate == 8_000:
            return 256
        raise ValueError(
            "Silero VAD supports 8000 Hz and 16000 Hz audio only; "
            f"received {sample_rate} Hz"
        )
