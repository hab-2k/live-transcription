from __future__ import annotations

import pytest

from app.contracts.session import SessionConfig, SystemAudioSelection
from app.services.audio.base import AudioFrame
from app.services.audio.composite_capture import CompositeCaptureService
from app.services.audio.system_audio_provider import PROVIDER_SCREEN_CAPTURE_KIT


class FakeMicrophoneCapture:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False

    async def start(self, config, on_audio) -> None:  # noqa: ANN001
        self.started = True
        await on_audio(AudioFrame(source="microphone", pcm=[0.1], sample_rate=16_000))

    async def stop(self) -> None:
        self.stopped = True


class FakeSystemAudioProvider:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False
        self.selection = None
        self.sample_rate = None

    async def start(self, *, selection, sample_rate: int, on_audio) -> None:  # noqa: ANN001
        self.started = True
        self.selection = selection
        self.sample_rate = sample_rate
        await on_audio(AudioFrame(source="system", pcm=[0.2], sample_rate=sample_rate))

    async def stop(self) -> None:
        self.stopped = True


async def test_composite_capture_starts_provider_for_mic_plus_system() -> None:
    microphone = FakeMicrophoneCapture()
    system_audio = FakeSystemAudioProvider()
    capture = CompositeCaptureService(
        microphone_capture=microphone,
        system_audio_provider=system_audio,
    )
    frames: list[AudioFrame] = []

    async def on_audio(frame: AudioFrame) -> None:
        frames.append(frame)

    await capture.start(
        config=SessionConfig(
            capture_mode="mic_plus_system",
            microphone_device_id="Built-in Microphone",
            persona="manager",
            coaching_profile="empathy",
            asr_provider="nemo",
            system_audio_selection=SystemAudioSelection(
                provider=PROVIDER_SCREEN_CAPTURE_KIT,
                target_id="screen_capture_kit:1234",
            ),
        ),
        on_audio=on_audio,
    )

    assert microphone.started is True
    assert system_audio.started is True
    assert system_audio.selection.target_id == "screen_capture_kit:1234"
    assert [frame.source for frame in frames] == ["microphone", "system"]


async def test_composite_capture_rejects_missing_selection_before_starting_microphone() -> None:
    microphone = FakeMicrophoneCapture()
    system_audio = FakeSystemAudioProvider()
    capture = CompositeCaptureService(
        microphone_capture=microphone,
        system_audio_provider=system_audio,
    )

    async def on_audio(frame: AudioFrame) -> None:
        return None

    with pytest.raises(ValueError, match="System audio selection is required"):
        await capture.start(
            config=SessionConfig(
                capture_mode="mic_plus_system",
                microphone_device_id="Built-in Microphone",
                persona="manager",
                coaching_profile="empathy",
                asr_provider="nemo",
            ),
            on_audio=on_audio,
        )

    assert microphone.started is False
    assert system_audio.started is False


async def test_composite_capture_stops_microphone_and_system_audio() -> None:
    microphone = FakeMicrophoneCapture()
    system_audio = FakeSystemAudioProvider()
    capture = CompositeCaptureService(
        microphone_capture=microphone,
        system_audio_provider=system_audio,
    )

    async def on_audio(frame: AudioFrame) -> None:
        return None

    await capture.start(
        config=SessionConfig(
            capture_mode="mic_plus_system",
            microphone_device_id="Built-in Microphone",
            persona="manager",
            coaching_profile="empathy",
            asr_provider="nemo",
            system_audio_selection=SystemAudioSelection(
                provider=PROVIDER_SCREEN_CAPTURE_KIT,
                target_id="screen_capture_kit:1234",
            ),
        ),
        on_audio=on_audio,
    )

    await capture.stop()

    assert microphone.stopped is True
    assert system_audio.stopped is True
