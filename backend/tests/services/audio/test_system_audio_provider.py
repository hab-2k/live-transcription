"""Tests for the provider-backed system audio integration.

Covers three layers:
  1. Unit – binary discovery, status/target parsing, subprocess wiring
  2. Read-loop – PCM decoding and frame delivery
  3. Binary contract – CLI shape exposed by the native helper
"""

from __future__ import annotations

import json
import struct
import subprocess
import sys
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from app.contracts.session import SystemAudioSelection
from app.services.audio.base import AudioFrame
from app.services.audio.system_audio_provider import (
    BLOCK_SAMPLES,
    PROVIDER_SCREEN_CAPTURE_KIT,
    SAMPLE_RATE,
    ScreenCaptureKitSystemAudioProvider,
    SystemAudioProviderStatus,
    SystemAudioTarget,
    _find_binary,
)

BYTES_PER_SAMPLE = 4


def _pcm_bytes(n_samples: int, value: float = 0.5) -> bytes:
    return struct.pack(f"{n_samples}f", *([value] * n_samples))


def _block(value: float = 0.5) -> bytes:
    return _pcm_bytes(BLOCK_SAMPLES, value)


@pytest.fixture
def make_read_loop_provider():
    def _factory(stdout_bytes: bytes) -> tuple[ScreenCaptureKitSystemAudioProvider, list[AudioFrame]]:
        provider = ScreenCaptureKitSystemAudioProvider()
        fake_proc = MagicMock()
        fake_proc.stdout = BytesIO(stdout_bytes)
        provider._process = fake_proc

        received: list[AudioFrame] = []

        async def sink(frame: AudioFrame) -> None:
            received.append(frame)

        provider._on_audio = sink
        return provider, received

    return _factory


class TestFindBinary:
    def test_returns_debug_path_when_exists(self, tmp_path: Path) -> None:
        debug_bin = tmp_path / ".build" / "debug" / "system-audio-capture"
        debug_bin.parent.mkdir(parents=True)
        debug_bin.touch()

        with patch("app.services.audio.system_audio_provider._MACOS_BUILD_DIR", tmp_path):
            result = _find_binary()

        assert result == str(debug_bin)

    def test_returns_release_path_when_debug_absent(self, tmp_path: Path) -> None:
        release_bin = tmp_path / ".build" / "release" / "system-audio-capture"
        release_bin.parent.mkdir(parents=True)
        release_bin.touch()

        with patch("app.services.audio.system_audio_provider._MACOS_BUILD_DIR", tmp_path):
            result = _find_binary()

        assert result == str(release_bin)

    def test_raises_file_not_found_when_absent(self, tmp_path: Path) -> None:
        with patch("app.services.audio.system_audio_provider._MACOS_BUILD_DIR", tmp_path):
            with pytest.raises(FileNotFoundError, match="system-audio-capture"):
                _find_binary()


class TestProviderStatus:
    def test_reports_unsupported_state_on_non_darwin(self) -> None:
        with patch("sys.platform", "linux"):
            status = ScreenCaptureKitSystemAudioProvider().get_status()

        assert status == SystemAudioProviderStatus(
            provider=PROVIDER_SCREEN_CAPTURE_KIT,
            state="unsupported",
            message="System audio capture is only supported on macOS.",
        )

    def test_maps_status_json_from_subprocess(self, tmp_path: Path) -> None:
        binary = tmp_path / ".build" / "debug" / "system-audio-capture"
        binary.parent.mkdir(parents=True)
        binary.touch()
        payload = json.dumps(
            {
                "provider": PROVIDER_SCREEN_CAPTURE_KIT,
                "state": "permission_required",
                "message": "Screen Recording permission is required.",
            }
        )

        with (
            patch("app.services.audio.system_audio_provider._MACOS_BUILD_DIR", tmp_path),
            patch("sys.platform", "darwin"),
            patch(
                "subprocess.run",
                return_value=MagicMock(returncode=0, stdout=payload, stderr=""),
            ) as mock_run,
        ):
            status = ScreenCaptureKitSystemAudioProvider().get_status()

        assert status.state == "permission_required"
        assert status.provider == PROVIDER_SCREEN_CAPTURE_KIT
        assert status.message == "Screen Recording permission is required."
        assert "--status" in mock_run.call_args[0][0]

    def test_returns_error_status_when_status_command_fails(self, tmp_path: Path) -> None:
        binary = tmp_path / ".build" / "debug" / "system-audio-capture"
        binary.parent.mkdir(parents=True)
        binary.touch()

        with (
            patch("app.services.audio.system_audio_provider._MACOS_BUILD_DIR", tmp_path),
            patch("sys.platform", "darwin"),
            patch(
                "subprocess.run",
                return_value=MagicMock(returncode=1, stdout="", stderr="boom"),
            ),
        ):
            status = ScreenCaptureKitSystemAudioProvider().get_status()

        assert status.state == "error"
        assert "boom" in status.message


class TestTargetListing:
    def test_returns_empty_list_on_non_darwin(self) -> None:
        with patch("sys.platform", "linux"):
            assert ScreenCaptureKitSystemAudioProvider().list_targets() == []

    def test_parses_targets_from_json(self, tmp_path: Path) -> None:
        binary = tmp_path / ".build" / "debug" / "system-audio-capture"
        binary.parent.mkdir(parents=True)
        binary.touch()
        payload = json.dumps(
            [
                {
                    "id": "screen_capture_kit:1234",
                    "name": "Microsoft Teams",
                    "kind": "application",
                    "icon_hint": None,
                    "metadata": {"pid": 1234, "bundle_id": "com.microsoft.teams2"},
                }
            ]
        )

        with (
            patch("app.services.audio.system_audio_provider._MACOS_BUILD_DIR", tmp_path),
            patch("sys.platform", "darwin"),
            patch(
                "subprocess.run",
                return_value=MagicMock(returncode=0, stdout=payload, stderr=""),
            ) as mock_run,
        ):
            targets = ScreenCaptureKitSystemAudioProvider().list_targets()

        assert targets == [
            SystemAudioTarget(
                id="screen_capture_kit:1234",
                name="Microsoft Teams",
                kind="application",
                icon_hint=None,
                metadata={"pid": 1234, "bundle_id": "com.microsoft.teams2"},
            )
        ]
        assert "--list-targets" in mock_run.call_args[0][0]

    def test_returns_empty_list_when_binary_missing(self) -> None:
        with (
            patch("sys.platform", "darwin"),
            patch(
                "app.services.audio.system_audio_provider._find_binary",
                side_effect=FileNotFoundError("missing"),
            ),
        ):
            assert ScreenCaptureKitSystemAudioProvider().list_targets() == []


class TestProviderLifecycle:
    @pytest.mark.asyncio
    async def test_start_raises_provider_status_message_when_capture_is_not_available(self) -> None:
        provider = ScreenCaptureKitSystemAudioProvider()

        with patch.object(
            provider,
            "get_status",
            return_value=SystemAudioProviderStatus(
                provider=PROVIDER_SCREEN_CAPTURE_KIT,
                state="permission_required",
                message="Grant Screen Recording permission first.",
            ),
        ):
            with pytest.raises(ValueError, match="Grant Screen Recording permission first."):
                await provider.start(
                    selection=SystemAudioSelection(
                        provider=PROVIDER_SCREEN_CAPTURE_KIT,
                        target_id="screen_capture_kit:1234",
                    ),
                    sample_rate=SAMPLE_RATE,
                    on_audio=AsyncMock(),
                )

    @pytest.mark.asyncio
    async def test_start_rejects_selection_for_wrong_provider(self) -> None:
        provider = ScreenCaptureKitSystemAudioProvider()

        with pytest.raises(ValueError, match="provider"):
            await provider.start(
                selection=SystemAudioSelection(provider="other", target_id="x"),
                sample_rate=SAMPLE_RATE,
                on_audio=AsyncMock(),
            )

    @pytest.mark.asyncio
    async def test_start_validates_target_id_against_current_targets(self) -> None:
        provider = ScreenCaptureKitSystemAudioProvider()

        with (
            patch.object(
                provider,
                "get_status",
                return_value=SystemAudioProviderStatus(
                    provider=PROVIDER_SCREEN_CAPTURE_KIT,
                    state="available",
                    message="Ready to capture system audio.",
                ),
            ),
            patch.object(provider, "list_targets", return_value=[]),
        ):
            with pytest.raises(ValueError, match="Unknown system audio target"):
                await provider.start(
                    selection=SystemAudioSelection(
                        provider=PROVIDER_SCREEN_CAPTURE_KIT,
                        target_id="screen_capture_kit:missing",
                    ),
                    sample_rate=SAMPLE_RATE,
                    on_audio=AsyncMock(),
                )

    @pytest.mark.asyncio
    async def test_start_spawns_capture_process_with_target_id_and_sample_rate(self) -> None:
        provider = ScreenCaptureKitSystemAudioProvider()
        fake_proc = MagicMock()
        fake_proc.stdout = BytesIO(b"")

        with (
            patch.object(
                provider,
                "get_status",
                return_value=SystemAudioProviderStatus(
                    provider=PROVIDER_SCREEN_CAPTURE_KIT,
                    state="available",
                    message="Ready to capture system audio.",
                ),
            ),
            patch.object(
                provider,
                "list_targets",
                return_value=[
                    SystemAudioTarget(
                        id="screen_capture_kit:1234",
                        name="Teams",
                        kind="application",
                    )
                ],
            ),
            patch("app.services.audio.system_audio_provider._find_binary", return_value="/fake/bin"),
            patch("subprocess.Popen", return_value=fake_proc) as mock_popen,
        ):
            await provider.start(
                selection=SystemAudioSelection(
                    provider=PROVIDER_SCREEN_CAPTURE_KIT,
                    target_id="screen_capture_kit:1234",
                ),
                sample_rate=24_000,
                on_audio=AsyncMock(),
            )
            await provider.stop()

        cmd = mock_popen.call_args[0][0]
        assert "--capture" in cmd
        assert "--target-id" in cmd
        assert "screen_capture_kit:1234" in cmd
        assert "--sample-rate" in cmd
        assert "24000" in cmd

    @pytest.mark.asyncio
    async def test_stop_is_idempotent(self) -> None:
        provider = ScreenCaptureKitSystemAudioProvider()
        await provider.stop()
        await provider.stop()


class TestReadLoop:
    @pytest.mark.asyncio
    async def test_delivers_one_frame_per_block(self, make_read_loop_provider) -> None:
        provider, received = make_read_loop_provider(_block() + _block())
        await provider._read_loop(SAMPLE_RATE)

        assert len(received) == 2

    @pytest.mark.asyncio
    async def test_delivers_system_source_frames(self, make_read_loop_provider) -> None:
        provider, received = make_read_loop_provider(_block())
        await provider._read_loop(SAMPLE_RATE)

        assert received[0].source == "system"

    @pytest.mark.asyncio
    async def test_decodes_float32_pcm(self, make_read_loop_provider) -> None:
        provider, received = make_read_loop_provider(_block(0.25))
        await provider._read_loop(SAMPLE_RATE)

        assert isinstance(received[0].pcm, np.ndarray)
        assert received[0].pcm.dtype == np.float32
        np.testing.assert_allclose(received[0].pcm, 0.25, atol=1e-6)

    @pytest.mark.asyncio
    async def test_delivers_partial_final_block(self, make_read_loop_provider) -> None:
        provider, received = make_read_loop_provider(_pcm_bytes(512))
        await provider._read_loop(SAMPLE_RATE)

        assert len(received) == 1
        assert len(received[0].pcm) == 512


def _binary_path() -> str | None:
    try:
        return _find_binary()
    except FileNotFoundError:
        return None


_BINARY_PRESENT = _binary_path() is not None
_skip_no_binary = pytest.mark.skipif(
    not _BINARY_PRESENT, reason="system-audio-capture binary not built"
)
_skip_non_darwin = pytest.mark.skipif(sys.platform != "darwin", reason="macOS only")


@_skip_non_darwin
@_skip_no_binary
class TestBinaryContract:
    def test_status_command_outputs_valid_json(self) -> None:
        result = subprocess.run(
            [_binary_path(), "--status"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0, f"stderr: {result.stderr}"
        payload = json.loads(result.stdout)
        assert payload["provider"] == PROVIDER_SCREEN_CAPTURE_KIT
        assert payload["state"] in {"available", "permission_required", "unsupported", "error"}

    def test_list_targets_outputs_valid_json(self) -> None:
        result = subprocess.run(
            [_binary_path(), "--list-targets"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0, f"stderr: {result.stderr}"
        payload = json.loads(result.stdout)
        assert isinstance(payload, list)

    def test_invalid_target_fails_capture(self) -> None:
        result = subprocess.run(
            [_binary_path(), "--capture", "--target-id", "screen_capture_kit:missing", "--sample-rate", "16000"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode != 0
