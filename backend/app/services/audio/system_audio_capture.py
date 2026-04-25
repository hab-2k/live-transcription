"""Native system audio capture via Core Audio Process Tap (macOS).

Spawns the `system-audio-capture` Swift CLI as a subprocess, reads raw
float32 PCM from its stdout, and delivers AudioFrame(source="system")
to the registered sink at the configured sample rate.
"""

from __future__ import annotations

import asyncio
import json
import logging
import struct
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from app.services.audio.base import AudioFrame, AudioSink

logger = logging.getLogger(__name__)

BINARY_NAME = "system-audio-capture"
_REPO_ROOT = Path(__file__).resolve().parents[4]  # backend/app/services/audio -> repo root
_MACOS_BUILD_DIR = _REPO_ROOT / "native" / "macos" / "SystemAudioCapture"

SAMPLE_RATE = 16_000
BLOCK_SAMPLES = 1024  # match mic capture block size


@dataclass(slots=True)
class CapturableApp:
    name: str
    pid: int
    bundle_id: str


def _find_binary() -> str:
    """Locate the system-audio-capture binary."""
    # Check if built via swift build (debug)
    debug_path = _MACOS_BUILD_DIR / ".build" / "debug" / BINARY_NAME
    if debug_path.is_file():
        return str(debug_path)

    # Check release
    release_path = _MACOS_BUILD_DIR / ".build" / "release" / BINARY_NAME
    if release_path.is_file():
        return str(release_path)

    raise FileNotFoundError(
        f"system-audio-capture binary not found. "
        f"Build it with: cd {_MACOS_BUILD_DIR} && swift build"
    )


def list_capturable_apps() -> list[CapturableApp]:
    """Return apps whose audio can be captured."""
    if sys.platform != "darwin":
        return []

    try:
        binary = _find_binary()
    except FileNotFoundError:
        logger.warning("system-audio-capture binary not found; capturable apps unavailable")
        return []

    try:
        result = subprocess.run(
            [binary, "--list-apps"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except subprocess.TimeoutExpired:
        logger.warning("list-apps timed out")
        return []

    if result.returncode != 0:
        logger.warning("list-apps failed: %s", result.stderr)
        return []

    apps = json.loads(result.stdout)
    return [
        CapturableApp(name=a["name"], pid=a["pid"], bundle_id=a["bundle_id"])
        for a in apps
    ]


class SystemAudioCaptureService:
    """Captures audio from a target process via Core Audio Process Tap."""

    def __init__(self) -> None:
        self._process: subprocess.Popen[bytes] | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._on_audio: AudioSink | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    async def start(self, pid: int, sample_rate: int, on_audio: AudioSink) -> None:
        if self._process is not None:
            raise RuntimeError("System audio capture already running")

        binary = _find_binary()
        self._on_audio = on_audio
        self._loop = asyncio.get_running_loop()

        self._process = subprocess.Popen(
            [binary, "--pid", str(pid), "--sample-rate", str(sample_rate)],
            stdout=subprocess.PIPE,
            stdin=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self._reader_task = asyncio.create_task(
            self._read_loop(sample_rate),
            name="system-audio-reader",
        )
        logger.info("System audio capture started: pid=%d sample_rate=%d", pid, sample_rate)

    async def stop(self) -> None:
        if self._reader_task is not None:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None

        if self._process is not None:
            try:
                self._process.terminate()
                self._process.wait(timeout=3)
            except Exception:
                self._process.kill()
                self._process.wait(timeout=1)
            self._process = None

        self._on_audio = None
        self._loop = None
        logger.info("System audio capture stopped")

    async def _read_loop(self, sample_rate: int) -> None:
        """Read raw float32 PCM from the subprocess stdout."""
        assert self._process is not None
        assert self._process.stdout is not None

        bytes_per_block = BLOCK_SAMPLES * 4  # float32 = 4 bytes
        loop = asyncio.get_running_loop()

        try:
            while True:
                data = await loop.run_in_executor(
                    None, self._process.stdout.read, bytes_per_block
                )
                if not data:
                    break

                # Convert raw bytes to float32 numpy array
                n_samples = len(data) // 4
                if n_samples == 0:
                    continue

                pcm = np.frombuffer(data[:n_samples * 4], dtype=np.float32).copy()
                frame = AudioFrame(source="system", pcm=pcm, sample_rate=sample_rate)

                if self._on_audio is not None:
                    await self._on_audio(frame)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("System audio read loop error")
