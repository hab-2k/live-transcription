import importlib
import importlib.util

import numpy as np
import pytest
import torch


class FakeSileroModel:
    def __init__(self, scores: list[float]) -> None:
        self._scores = scores
        self._index = 0

    def __call__(self, frame: np.ndarray, sample_rate: int) -> float:  # noqa: ARG002
        score = self._scores[min(self._index, len(self._scores) - 1)]
        self._index += 1
        return score


class TensorExpectingSileroModel:
    def __call__(self, frame, sample_rate: int):  # noqa: ANN001, ARG002
        assert isinstance(frame, torch.Tensor)
        return torch.tensor(0.9)


class ChunkRecordingSileroModel:
    def __init__(self, scores: list[float]) -> None:
        self._scores = scores
        self._index = 0
        self.calls: list[tuple[torch.Tensor, int]] = []

    def __call__(self, frame, sample_rate: int):  # noqa: ANN001
        assert isinstance(frame, torch.Tensor)
        self.calls.append((frame.detach().clone(), sample_rate))
        score = self._scores[min(self._index, len(self._scores) - 1)]
        self._index += 1
        return torch.tensor(score)


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


def test_silero_vad_wrapper_converts_numpy_audio_to_torch_tensor() -> None:
    vad_module = importlib.import_module("app.services.transcription.vad")
    vad = vad_module.SileroVadService(
        model=TensorExpectingSileroModel(),
        threshold=0.5,
        min_silence_ms=600,
    )

    decision = vad.detect(np.ones(320, dtype=np.float32), sample_rate=16_000)

    assert decision.active is True


def test_silero_vad_wrapper_chunks_1024_sample_frames_for_16khz_model() -> None:
    vad_module = importlib.import_module("app.services.transcription.vad")
    model = ChunkRecordingSileroModel([0.2, 0.9])
    vad = vad_module.SileroVadService(model=model, threshold=0.5, min_silence_ms=600)

    decision = vad.detect(np.arange(1024, dtype=np.float32), sample_rate=16_000)

    assert decision.active is True
    assert decision.speech_confidence == pytest.approx(0.9)
    assert len(model.calls) == 2
    assert all(sample_rate == 16_000 for _, sample_rate in model.calls)
    assert all(call.shape == (512,) for call, _ in model.calls)
    np.testing.assert_array_equal(model.calls[0][0].numpy(), np.arange(512, dtype=np.float32))
    np.testing.assert_array_equal(model.calls[1][0].numpy(), np.arange(512, 1024, dtype=np.float32))
