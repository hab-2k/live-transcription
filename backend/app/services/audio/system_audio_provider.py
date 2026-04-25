"""Provider-backed system audio capture helpers for macOS ScreenCaptureKit."""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from app.contracts.session import SystemAudioSelection
from app.services.audio.base import AudioFrame, AudioSink

logger = logging.getLogger(__name__)

PROVIDER_SCREEN_CAPTURE_KIT = "screen_capture_kit"
BINARY_NAME = "system-audio-capture"
_REPO_ROOT = Path(__file__).resolve().parents[4]
_MACOS_BUILD_DIR = _REPO_ROOT / "native" / "macos" / "SystemAudioCapture"

SAMPLE_RATE = 16_000
BLOCK_SAMPLES = 1024


@dataclass(slots=True)
class SystemAudioProviderStatus:
    provider: str
    state: str
    message: str


@dataclass(slots=True)
class SystemAudioTarget:
    id: str
    name: str
    kind: str
    icon_hint: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def _find_binary() -> str:
    debug_path = _MACOS_BUILD_DIR / ".build" / "debug" / BINARY_NAME
    if debug_path.is_file():
        return str(debug_path)

    release_path = _MACOS_BUILD_DIR / ".build" / "release" / BINARY_NAME
    if release_path.is_file():
        return str(release_path)

    raise FileNotFoundError(
        f"system-audio-capture binary not found. "
        f"Build it with: cd {_MACOS_BUILD_DIR} && swift build"
    )


class ScreenCaptureKitSystemAudioProvider:
    """Captures system audio through the native ScreenCaptureKit helper."""

    def __init__(self) -> None:
        self._process: subprocess.Popen[bytes] | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._on_audio: AudioSink | None = None

    def get_status(self) -> SystemAudioProviderStatus:
        if sys.platform != "darwin":
            return SystemAudioProviderStatus(
                provider=PROVIDER_SCREEN_CAPTURE_KIT,
                state="unsupported",
                message="System audio capture is only supported on macOS.",
            )

        try:
            binary = _find_binary()
        except FileNotFoundError as exc:
            return SystemAudioProviderStatus(
                provider=PROVIDER_SCREEN_CAPTURE_KIT,
                state="error",
                message=str(exc),
            )

        try:
            result = subprocess.run(
                [binary, "--status"],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except subprocess.TimeoutExpired:
            return SystemAudioProviderStatus(
                provider=PROVIDER_SCREEN_CAPTURE_KIT,
                state="error",
                message="Timed out while checking system audio status.",
            )

        if result.returncode != 0:
            message = result.stderr.strip() or "System audio status command failed."
            return SystemAudioProviderStatus(
                provider=PROVIDER_SCREEN_CAPTURE_KIT,
                state="error",
                message=message,
            )

        payload = json.loads(result.stdout)
        return SystemAudioProviderStatus(
            provider=str(payload.get("provider", PROVIDER_SCREEN_CAPTURE_KIT)),
            state=str(payload.get("state", "error")),
            message=str(payload.get("message", "")),
        )

    def list_targets(self) -> list[SystemAudioTarget]:
        if sys.platform != "darwin":
            return []

        try:
            binary = _find_binary()
        except FileNotFoundError:
            logger.warning("system-audio-capture binary not found; system audio targets unavailable")
            return []

        try:
            result = subprocess.run(
                [binary, "--list-targets"],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except subprocess.TimeoutExpired:
            logger.warning("list-targets timed out")
            return []

        if result.returncode != 0:
            logger.warning("list-targets failed: %s", result.stderr)
            return []

        payload = json.loads(result.stdout)
        return [
            SystemAudioTarget(
                id=str(item["id"]),
                name=str(item["name"]),
                kind=str(item["kind"]),
                icon_hint=item.get("icon_hint"),
                metadata=dict(item.get("metadata") or {}),
            )
            for item in payload
        ]

    async def start(
        self,
        *,
        selection: SystemAudioSelection,
        sample_rate: int,
        on_audio: AudioSink,
    ) -> None:
        if selection.provider != PROVIDER_SCREEN_CAPTURE_KIT:
            raise ValueError(f"Unsupported system audio provider: {selection.provider}")

        status = self.get_status()
        if status.state != "available":
            raise ValueError(status.message)

        if self._process is not None:
            raise RuntimeError("System audio provider already running")

        known_targets = {target.id for target in self.list_targets()}
        if selection.target_id not in known_targets:
            raise ValueError(f"Unknown system audio target: {selection.target_id}")

        binary = _find_binary()
        self._on_audio = on_audio
        self._process = subprocess.Popen(
            [
                binary,
                "--capture",
                "--target-id",
                selection.target_id,
                "--sample-rate",
                str(sample_rate),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE,
        )
        self._reader_task = asyncio.create_task(
            self._read_loop(sample_rate),
            name="system-audio-provider-reader",
        )
        self._stderr_task = asyncio.create_task(
            self._drain_stderr(),
            name="system-audio-provider-stderr",
        )

    async def stop(self) -> None:
        if self._reader_task is not None:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None

        if self._stderr_task is not None:
            self._stderr_task.cancel()
            try:
                await self._stderr_task
            except asyncio.CancelledError:
                pass
            self._stderr_task = None

        if self._process is not None:
            try:
                self._process.terminate()
                self._process.wait(timeout=3)
            except Exception:
                self._process.kill()
                self._process.wait(timeout=1)
            self._process = None

        self._on_audio = None

    async def _read_loop(self, sample_rate: int) -> None:
        assert self._process is not None
        if self._process.stdout is None:
            return

        bytes_per_block = BLOCK_SAMPLES * 4
        loop = asyncio.get_running_loop()

        try:
            while True:
                data = await loop.run_in_executor(None, self._process.stdout.read, bytes_per_block)
                if not data:
                    break

                n_samples = len(data) // 4
                if n_samples == 0:
                    continue

                pcm = np.frombuffer(data[: n_samples * 4], dtype=np.float32).copy()
                if self._on_audio is not None:
                    await self._on_audio(AudioFrame(source="system", pcm=pcm, sample_rate=sample_rate))
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("System audio read loop error")

    async def _drain_stderr(self) -> None:
        assert self._process is not None
        if self._process.stderr is None:
            return

        loop = asyncio.get_running_loop()
        try:
            while True:
                line = await loop.run_in_executor(None, self._process.stderr.readline)
                if not line:
                    break
                logger.info("system-audio-capture: %s", line.decode("utf-8", errors="replace").rstrip())
        except asyncio.CancelledError:
            raise
