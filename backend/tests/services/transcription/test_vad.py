import importlib
import importlib.util

import numpy as np


class FakeSileroModel:
    def __init__(self, scores: list[float]) -> None:
        self._scores = scores
        self._index = 0

    def __call__(self, frame: np.ndarray, sample_rate: int) -> float:  # noqa: ARG002
        score = self._scores[min(self._index, len(self._scores) - 1)]
        self._index += 1
        return score


def test_silero_vad_wrapper_reports_speech_activity() -> None:
    assert importlib.util.find_spec("app.services.transcription.vad") is not None

    vad_module = importlib.import_module("app.services.transcription.vad")
    vad = vad_module.SileroVadService(model=FakeSileroModel([0.9]), threshold=0.5, min_silence_ms=600)

    decision = vad.detect(np.ones(320, dtype=np.float32), sample_rate=16_000)

    assert decision.active is True


def test_silero_vad_wrapper_applies_silence_hangover() -> None:
    vad_module = importlib.import_module("app.services.transcription.vad")
    vad = vad_module.SileroVadService(model=FakeSileroModel([0.9, 0.1, 0.1]), threshold=0.5, min_silence_ms=30)

    first = vad.detect(np.ones(320, dtype=np.float32), sample_rate=16_000)
    second = vad.detect(np.zeros(320, dtype=np.float32), sample_rate=16_000)
    third = vad.detect(np.zeros(320, dtype=np.float32), sample_rate=16_000)

    assert first.active is True
    assert second.active is True
    assert third.active is False
