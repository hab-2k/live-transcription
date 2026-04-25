from __future__ import annotations

from app.services.audio.base import AudioSink, CaptureService, SystemAudioProvider
from app.services.audio.sounddevice_capture import SAMPLE_RATE
from app.contracts.session import SessionConfig


class CompositeCaptureService:
    def __init__(
        self,
        *,
        microphone_capture: CaptureService,
        system_audio_provider: SystemAudioProvider,
    ) -> None:
        self._microphone_capture = microphone_capture
        self._system_audio_provider = system_audio_provider

    async def start(self, config: SessionConfig, on_audio: AudioSink) -> None:
        if config.capture_mode == "mic_plus_system" and config.system_audio_selection is None:
            raise ValueError("System audio selection is required for microphone + system capture.")

        await self._microphone_capture.start(config=config, on_audio=on_audio)

        if config.capture_mode != "mic_plus_system":
            return

        try:
            await self._system_audio_provider.start(
                selection=config.system_audio_selection,
                sample_rate=SAMPLE_RATE,
                on_audio=on_audio,
            )
        except Exception:
            await self._microphone_capture.stop()
            raise

    async def stop(self) -> None:
        await self._system_audio_provider.stop()
        await self._microphone_capture.stop()
