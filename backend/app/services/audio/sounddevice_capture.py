from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

import numpy as np
import sounddevice as sd

from app.contracts.session import SessionConfig
from app.services.audio.base import AudioFrame, AudioSink

logger = logging.getLogger(__name__)

# Capture settings
SAMPLE_RATE = 16_000
BLOCK_SIZE = 1024  # ~64ms at 16kHz
CHANNELS = 1


class SoundDeviceCaptureService:
    def __init__(self) -> None:
        self._on_audio: AudioSink | None = None
        self._config: SessionConfig | None = None
        self._streams: list[sd.InputStream] = []
        self._loop: asyncio.AbstractEventLoop | None = None

    async def start(self, config: SessionConfig, on_audio: AudioSink) -> None:
        self._config = config
        self._on_audio = on_audio
        self._loop = asyncio.get_running_loop()

        mic_device = self._find_device(config.microphone_device_id)
        if mic_device is None:
            logger.warning("Microphone '%s' not found, listing available devices:", config.microphone_device_id)
            logger.warning("%s", sd.query_devices())
            raise ValueError(f"Microphone device not found: {config.microphone_device_id}")

        mic_stream = sd.InputStream(
            device=mic_device,
            samplerate=SAMPLE_RATE,
            blocksize=BLOCK_SIZE,
            channels=CHANNELS,
            dtype="float32",
            callback=self._make_callback("microphone"),
        )
        self._streams.append(mic_stream)

        if config.capture_mode == "mic_plus_blackhole":
            bh_device = self._find_device("BlackHole")
            if bh_device is not None:
                bh_stream = sd.InputStream(
                    device=bh_device,
                    samplerate=SAMPLE_RATE,
                    blocksize=BLOCK_SIZE,
                    channels=CHANNELS,
                    dtype="float32",
                    callback=self._make_callback("blackhole"),
                )
                self._streams.append(bh_stream)
            else:
                logger.warning("BlackHole device not found, running mic-only")

        for stream in self._streams:
            stream.start()

        logger.info(
            "Capture started: mode=%s, streams=%d",
            config.capture_mode,
            len(self._streams),
        )

    async def stop(self) -> None:
        for stream in self._streams:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
        self._streams.clear()
        self._config = None
        self._on_audio = None
        self._loop = None
        logger.info("Capture stopped")

    def _find_device(self, name: str) -> int | None:
        devices: list[dict[str, Any]] = sd.query_devices()  # type: ignore[assignment]
        for i, dev in enumerate(devices):
            if name.lower() in dev["name"].lower() and dev["max_input_channels"] > 0:
                return i
        return None

    def _make_callback(self, source: str):
        def callback(indata: np.ndarray, frames: int, time_info: Any, status: sd.CallbackFlags) -> None:
            if status:
                logger.debug("sounddevice status (%s): %s", source, status)
            if self._on_audio is None or self._loop is None:
                return
            pcm = indata[:, 0].copy()
            frame = AudioFrame(source=source, pcm=pcm, sample_rate=SAMPLE_RATE)
            self._loop.call_soon_threadsafe(asyncio.ensure_future, self._on_audio(frame))

        return callback
