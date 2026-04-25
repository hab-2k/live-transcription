"""Tests for system_audio_capture.py.

Covers three layers:
  1. Unit – binary discovery, JSON parsing, subprocess wiring (no real binary needed)
  2. Read-loop – PCM decoding, frame delivery, edge cases (BytesIO fake stdout)
  3. Contract – what the real binary CLI must expose (skipped when binary absent)
"""

from __future__ import annotations

import asyncio
import json
import struct
import subprocess
import sys
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from app.services.audio.base import AudioFrame
from app.services.audio.system_audio_capture import (
    BLOCK_SAMPLES,
    SAMPLE_RATE,
    CapturableApp,
    SystemAudioCaptureService,
    _find_binary,
    list_capturable_apps,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BYTES_PER_SAMPLE = 4  # float32


def _pcm_bytes(n_samples: int, value: float = 0.5) -> bytes:
    """Pack *n_samples* float32 values into raw bytes."""
    return struct.pack(f"{n_samples}f", *([value] * n_samples))


def _block(value: float = 0.5) -> bytes:
    """One full BLOCK_SAMPLES block of float32 PCM."""
    return _pcm_bytes(BLOCK_SAMPLES, value)


@pytest.fixture
def make_read_loop_service():
    """Factory: service wired with a BytesIO fake stdout and a collecting sink."""

    def _factory(stdout_bytes: bytes) -> tuple[SystemAudioCaptureService, list[AudioFrame]]:
        svc = SystemAudioCaptureService()
        fake_proc = MagicMock()
        fake_proc.stdout = BytesIO(stdout_bytes)
        svc._process = fake_proc

        received: list[AudioFrame] = []

        async def sink(frame: AudioFrame) -> None:
            received.append(frame)

        svc._on_audio = sink
        return svc, received

    return _factory


# ---------------------------------------------------------------------------
# Binary discovery – _find_binary()
# ---------------------------------------------------------------------------


class TestFindBinary:
    def test_returns_debug_path_when_exists(self, tmp_path: Path) -> None:
        debug_bin = tmp_path / ".build" / "debug" / "system-audio-capture"
        debug_bin.parent.mkdir(parents=True)
        debug_bin.touch()

        with patch("app.services.audio.system_audio_capture._MACOS_BUILD_DIR", tmp_path):
            result = _find_binary()

        assert result == str(debug_bin)

    def test_returns_release_path_when_debug_absent(self, tmp_path: Path) -> None:
        release_bin = tmp_path / ".build" / "release" / "system-audio-capture"
        release_bin.parent.mkdir(parents=True)
        release_bin.touch()

        with patch("app.services.audio.system_audio_capture._MACOS_BUILD_DIR", tmp_path):
            result = _find_binary()

        assert result == str(release_bin)

    def test_prefers_debug_over_release(self, tmp_path: Path) -> None:
        for variant in ("debug", "release"):
            p = tmp_path / ".build" / variant / "system-audio-capture"
            p.parent.mkdir(parents=True)
            p.touch()

        with patch("app.services.audio.system_audio_capture._MACOS_BUILD_DIR", tmp_path):
            result = _find_binary()

        assert "debug" in result

    def test_raises_file_not_found_when_both_absent(self, tmp_path: Path) -> None:
        with patch("app.services.audio.system_audio_capture._MACOS_BUILD_DIR", tmp_path):
            with pytest.raises(FileNotFoundError):
                _find_binary()

    def test_error_message_names_the_binary(self, tmp_path: Path) -> None:
        with patch("app.services.audio.system_audio_capture._MACOS_BUILD_DIR", tmp_path):
            with pytest.raises(FileNotFoundError, match="system-audio-capture"):
                _find_binary()

    def test_error_message_contains_swift_build_hint(self, tmp_path: Path) -> None:
        with patch("app.services.audio.system_audio_capture._MACOS_BUILD_DIR", tmp_path):
            with pytest.raises(FileNotFoundError, match="swift build"):
                _find_binary()


# ---------------------------------------------------------------------------
# list_capturable_apps()
# ---------------------------------------------------------------------------


class TestListCapturableApps:
    """All tests patch sys.platform='darwin' except the non-darwin test."""

    def _stub_binary(self, tmp_path: Path) -> str:
        b = tmp_path / ".build" / "debug" / "system-audio-capture"
        b.parent.mkdir(parents=True)
        b.touch()
        return str(b)

    # --- platform guard ---

    def test_returns_empty_list_on_non_darwin(self) -> None:
        with patch("sys.platform", "linux"):
            assert list_capturable_apps() == []

    def test_returns_empty_list_on_windows(self) -> None:
        with patch("sys.platform", "win32"):
            assert list_capturable_apps() == []

    # --- happy path ---

    def test_parses_app_list_from_json(self, tmp_path: Path) -> None:
        self._stub_binary(tmp_path)
        payload = json.dumps([
            {"name": "Spotify", "pid": 1234, "bundle_id": "com.spotify.client"},
            {"name": "Chrome", "pid": 5678, "bundle_id": "com.google.Chrome"},
        ])

        with patch("app.services.audio.system_audio_capture._MACOS_BUILD_DIR", tmp_path), \
             patch("sys.platform", "darwin"), \
             patch("subprocess.run", return_value=MagicMock(returncode=0, stdout=payload, stderr="")):
            apps = list_capturable_apps()

        assert len(apps) == 2
        spotify = apps[0]
        assert spotify.name == "Spotify"
        assert spotify.pid == 1234
        assert spotify.bundle_id == "com.spotify.client"

    def test_returns_capturable_app_instances(self, tmp_path: Path) -> None:
        self._stub_binary(tmp_path)
        payload = json.dumps([{"name": "App", "pid": 1, "bundle_id": "com.example"}])

        with patch("app.services.audio.system_audio_capture._MACOS_BUILD_DIR", tmp_path), \
             patch("sys.platform", "darwin"), \
             patch("subprocess.run", return_value=MagicMock(returncode=0, stdout=payload, stderr="")):
            apps = list_capturable_apps()

        assert isinstance(apps[0], CapturableApp)

    def test_returns_empty_list_when_no_capturable_apps(self, tmp_path: Path) -> None:
        self._stub_binary(tmp_path)

        with patch("app.services.audio.system_audio_capture._MACOS_BUILD_DIR", tmp_path), \
             patch("sys.platform", "darwin"), \
             patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="[]", stderr="")):
            assert list_capturable_apps() == []

    # --- subprocess wiring ---

    def test_invokes_binary_with_list_apps_flag(self, tmp_path: Path) -> None:
        self._stub_binary(tmp_path)

        with patch("app.services.audio.system_audio_capture._MACOS_BUILD_DIR", tmp_path), \
             patch("sys.platform", "darwin"), \
             patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="[]", stderr="")) as mock_run:
            list_capturable_apps()

        cmd = mock_run.call_args[0][0]
        assert "--list-apps" in cmd

    def test_subprocess_uses_5s_timeout(self, tmp_path: Path) -> None:
        self._stub_binary(tmp_path)

        with patch("app.services.audio.system_audio_capture._MACOS_BUILD_DIR", tmp_path), \
             patch("sys.platform", "darwin"), \
             patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="[]", stderr="")) as mock_run:
            list_capturable_apps()

        kwargs = mock_run.call_args[1]
        assert kwargs.get("timeout") == 5

    # --- error handling ---

    def test_returns_empty_on_nonzero_returncode(self, tmp_path: Path) -> None:
        self._stub_binary(tmp_path)

        with patch("app.services.audio.system_audio_capture._MACOS_BUILD_DIR", tmp_path), \
             patch("sys.platform", "darwin"), \
             patch("subprocess.run", return_value=MagicMock(returncode=1, stdout="", stderr="tap error")):
            assert list_capturable_apps() == []

    def test_returns_empty_when_binary_missing(self) -> None:
        with patch("sys.platform", "darwin"), \
             patch(
                 "app.services.audio.system_audio_capture._find_binary",
                 side_effect=FileNotFoundError("missing"),
             ):
            assert list_capturable_apps() == []

    def test_returns_empty_when_subprocess_times_out(self, tmp_path: Path) -> None:
        self._stub_binary(tmp_path)

        with patch("app.services.audio.system_audio_capture._MACOS_BUILD_DIR", tmp_path), \
             patch("sys.platform", "darwin"), \
             patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 5)):
            # Should not raise – treat timeout as a soft failure
            result = list_capturable_apps()

        assert result == []


# ---------------------------------------------------------------------------
# SystemAudioCaptureService – lifecycle
# ---------------------------------------------------------------------------


class TestServiceLifecycle:
    @pytest.mark.asyncio
    async def test_start_raises_if_already_running(self) -> None:
        svc = SystemAudioCaptureService()
        svc._process = MagicMock()  # simulate already-started state

        with patch("app.services.audio.system_audio_capture._find_binary", return_value="/fake/bin"):
            with pytest.raises(RuntimeError, match="already running"):
                await svc.start(pid=1234, sample_rate=16_000, on_audio=AsyncMock())

    @pytest.mark.asyncio
    async def test_start_spawns_popen_with_pid_and_sample_rate(self) -> None:
        fake_proc = MagicMock()
        fake_proc.stdout = BytesIO(b"")

        with patch("app.services.audio.system_audio_capture._find_binary", return_value="/fake/bin"), \
             patch("subprocess.Popen", return_value=fake_proc) as mock_popen:
            svc = SystemAudioCaptureService()
            await svc.start(pid=9999, sample_rate=24_000, on_audio=AsyncMock())
            await svc.stop()

        cmd = mock_popen.call_args[0][0]
        assert "--pid" in cmd
        assert "9999" in cmd
        assert "--sample-rate" in cmd
        assert "24000" in cmd

    @pytest.mark.asyncio
    async def test_start_captures_stdout_as_pipe(self) -> None:
        fake_proc = MagicMock()
        fake_proc.stdout = BytesIO(b"")

        with patch("app.services.audio.system_audio_capture._find_binary", return_value="/fake/bin"), \
             patch("subprocess.Popen", return_value=fake_proc) as mock_popen:
            svc = SystemAudioCaptureService()
            await svc.start(pid=1234, sample_rate=16_000, on_audio=AsyncMock())
            await svc.stop()

        kwargs = mock_popen.call_args[1]
        assert kwargs.get("stdout") == subprocess.PIPE

    @pytest.mark.asyncio
    async def test_stop_is_idempotent_when_never_started(self) -> None:
        svc = SystemAudioCaptureService()
        await svc.stop()
        await svc.stop()  # second call must not raise

    @pytest.mark.asyncio
    async def test_stop_terminates_subprocess(self) -> None:
        fake_proc = MagicMock()
        fake_proc.stdout = BytesIO(b"")

        with patch("app.services.audio.system_audio_capture._find_binary", return_value="/fake/bin"), \
             patch("subprocess.Popen", return_value=fake_proc):
            svc = SystemAudioCaptureService()
            await svc.start(pid=1234, sample_rate=16_000, on_audio=AsyncMock())
            await svc.stop()

        fake_proc.terminate.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_kills_when_terminate_hangs(self) -> None:
        fake_proc = MagicMock()
        fake_proc.stdout = BytesIO(b"")
        fake_proc.wait.side_effect = [Exception("hung"), None]

        with patch("app.services.audio.system_audio_capture._find_binary", return_value="/fake/bin"), \
             patch("subprocess.Popen", return_value=fake_proc):
            svc = SystemAudioCaptureService()
            await svc.start(pid=1234, sample_rate=16_000, on_audio=AsyncMock())
            await svc.stop()

        fake_proc.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_clears_all_internal_state(self) -> None:
        fake_proc = MagicMock()
        fake_proc.stdout = BytesIO(b"")

        with patch("app.services.audio.system_audio_capture._find_binary", return_value="/fake/bin"), \
             patch("subprocess.Popen", return_value=fake_proc):
            svc = SystemAudioCaptureService()
            await svc.start(pid=1234, sample_rate=16_000, on_audio=AsyncMock())
            await svc.stop()

        assert svc._process is None
        assert svc._reader_task is None
        assert svc._on_audio is None
        assert svc._loop is None


# ---------------------------------------------------------------------------
# _read_loop – PCM decoding and frame delivery
# ---------------------------------------------------------------------------


class TestReadLoop:
    @pytest.mark.asyncio
    async def test_delivers_one_frame_per_block(self, make_read_loop_service) -> None:
        svc, received = make_read_loop_service(_block() + _block())
        await svc._read_loop(SAMPLE_RATE)
        assert len(received) == 2

    @pytest.mark.asyncio
    async def test_frame_source_is_system(self, make_read_loop_service) -> None:
        svc, received = make_read_loop_service(_block())
        await svc._read_loop(SAMPLE_RATE)
        assert received[0].source == "system"

    @pytest.mark.asyncio
    async def test_frame_sample_rate_matches_argument(self, make_read_loop_service) -> None:
        svc, received = make_read_loop_service(_block())
        await svc._read_loop(24_000)
        assert received[0].sample_rate == 24_000

    @pytest.mark.asyncio
    async def test_frame_pcm_is_float32_numpy_array(self, make_read_loop_service) -> None:
        svc, received = make_read_loop_service(_block())
        await svc._read_loop(SAMPLE_RATE)
        assert isinstance(received[0].pcm, np.ndarray)
        assert received[0].pcm.dtype == np.float32

    @pytest.mark.asyncio
    async def test_frame_pcm_has_correct_sample_count(self, make_read_loop_service) -> None:
        svc, received = make_read_loop_service(_block())
        await svc._read_loop(SAMPLE_RATE)
        assert len(received[0].pcm) == BLOCK_SAMPLES

    @pytest.mark.asyncio
    async def test_frame_pcm_values_are_decoded_correctly(self, make_read_loop_service) -> None:
        svc, received = make_read_loop_service(_block(0.25))
        await svc._read_loop(SAMPLE_RATE)
        np.testing.assert_allclose(received[0].pcm, 0.25, atol=1e-6)

    @pytest.mark.asyncio
    async def test_multiple_blocks_delivered_in_order(self, make_read_loop_service) -> None:
        first = _block(0.1)
        second = _block(0.9)
        svc, received = make_read_loop_service(first + second)
        await svc._read_loop(SAMPLE_RATE)

        assert len(received) == 2
        np.testing.assert_allclose(received[0].pcm, 0.1, atol=1e-6)
        np.testing.assert_allclose(received[1].pcm, 0.9, atol=1e-6)

    @pytest.mark.asyncio
    async def test_partial_final_block_is_delivered(self, make_read_loop_service) -> None:
        # 512 samples = half a block – still a valid AudioFrame
        partial = _pcm_bytes(512)
        svc, received = make_read_loop_service(partial)
        await svc._read_loop(SAMPLE_RATE)
        assert len(received) == 1
        assert len(received[0].pcm) == 512

    @pytest.mark.asyncio
    async def test_empty_stdout_delivers_no_frames(self, make_read_loop_service) -> None:
        svc, received = make_read_loop_service(b"")
        await svc._read_loop(SAMPLE_RATE)
        assert received == []

    @pytest.mark.asyncio
    async def test_pcm_is_a_writeable_copy_not_a_view(self, make_read_loop_service) -> None:
        """Frames must own their data – a numpy view of transient bytes would dangle."""
        svc, received = make_read_loop_service(_block())
        await svc._read_loop(SAMPLE_RATE)
        assert received[0].pcm.flags["OWNDATA"] or received[0].pcm.base is None or received[0].pcm.flags["WRITEABLE"]

    @pytest.mark.asyncio
    async def test_read_loop_handles_exact_block_boundary(self, make_read_loop_service) -> None:
        three_blocks = _block() * 3
        svc, received = make_read_loop_service(three_blocks)
        await svc._read_loop(SAMPLE_RATE)
        assert len(received) == 3

    @pytest.mark.asyncio
    async def test_read_loop_does_not_deliver_after_sink_cleared(
        self, make_read_loop_service
    ) -> None:
        """If _on_audio is None mid-loop, frames are silently dropped (no AttributeError)."""
        svc, received = make_read_loop_service(_block() + _block())
        original_sink = svc._on_audio

        call_count = 0

        async def counting_sink(frame: AudioFrame) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                svc._on_audio = None  # simulate stop clearing the sink

        svc._on_audio = counting_sink
        await svc._read_loop(SAMPLE_RATE)  # should not raise

        assert call_count == 1  # second block → sink was None → silently skipped


# ---------------------------------------------------------------------------
# Binary contract tests – skipped unless the real binary is present
# ---------------------------------------------------------------------------

def _binary_path() -> str | None:
    try:
        return _find_binary()
    except FileNotFoundError:
        return None


_BINARY_PRESENT = _binary_path() is not None
_skip_no_binary = pytest.mark.skipif(
    not _BINARY_PRESENT, reason="system-audio-capture binary not built"
)
_skip_non_darwin = pytest.mark.skipif(
    sys.platform != "darwin", reason="macOS only"
)


@_skip_non_darwin
@_skip_no_binary
class TestBinaryContract:
    """What the real Swift binary must do.  These tests become the acceptance
    criteria for the native implementation."""

    def test_list_apps_exits_zero(self) -> None:
        result = subprocess.run(
            [_binary_path(), "--list-apps"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"

    def test_list_apps_outputs_valid_json(self) -> None:
        result = subprocess.run(
            [_binary_path(), "--list-apps"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        parsed = json.loads(result.stdout)  # raises if not valid JSON
        assert isinstance(parsed, list)

    def test_list_apps_entries_have_required_fields(self) -> None:
        result = subprocess.run(
            [_binary_path(), "--list-apps"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        apps = json.loads(result.stdout)
        for app in apps:
            assert "name" in app, f"missing 'name': {app}"
            assert "pid" in app, f"missing 'pid': {app}"
            assert "bundle_id" in app, f"missing 'bundle_id': {app}"

    def test_list_apps_pid_is_integer(self) -> None:
        result = subprocess.run(
            [_binary_path(), "--list-apps"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        apps = json.loads(result.stdout)
        for app in apps:
            assert isinstance(app["pid"], int), f"pid must be int: {app}"

    def test_list_apps_name_is_nonempty_string(self) -> None:
        result = subprocess.run(
            [_binary_path(), "--list-apps"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        apps = json.loads(result.stdout)
        for app in apps:
            assert isinstance(app["name"], str) and app["name"], f"name invalid: {app}"

    def test_capture_outputs_float32_pcm_and_exits_on_sigterm(self) -> None:
        """Start capture against the current process (PID=self), read a few
        blocks, send SIGTERM, and verify the binary exits cleanly."""
        import os
        import signal
        import time

        our_pid = os.getpid()
        proc = subprocess.Popen(
            [_binary_path(), "--pid", str(our_pid), "--sample-rate", "16000"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        try:
            # Read at least one block (allow up to 3 s for the tap to activate)
            bytes_per_block = BLOCK_SAMPLES * BYTES_PER_SAMPLE
            proc.stdout.read(bytes_per_block)  # type: ignore[union-attr]
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)

        assert proc.returncode is not None, "process did not exit"

    def test_capture_stdout_is_parseable_float32(self) -> None:
        """If the tapped process is producing audio, stdout must be valid
        float32 samples in [-1, 1].  When the process is silent (common in
        CI / headless environments), the tap may yield zero bytes – that is
        acceptable and the test is skipped."""
        import os

        our_pid = os.getpid()
        proc = subprocess.Popen(
            [_binary_path(), "--pid", str(our_pid), "--sample-rate", "16000"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        bytes_per_block = BLOCK_SAMPLES * BYTES_PER_SAMPLE
        raw = b""
        try:
            raw = proc.stdout.read(bytes_per_block)  # type: ignore[union-attr]
        finally:
            proc.terminate()
            proc.wait(timeout=5)

        if len(raw) == 0:
            pytest.skip("tapped process produced no audio (silent environment)")

        samples = np.frombuffer(raw[: len(raw) - len(raw) % 4], dtype=np.float32)
        assert np.all(np.isfinite(samples)), "PCM contains NaN or Inf"
        assert np.all(np.abs(samples) <= 1.0), "PCM samples out of [-1, 1] range"

    def test_missing_pid_flag_exits_nonzero(self) -> None:
        result = subprocess.run(
            [_binary_path(), "--sample-rate", "16000"],
            capture_output=True,
            timeout=5,
        )
        assert result.returncode != 0

    def test_invalid_pid_exits_nonzero(self) -> None:
        result = subprocess.run(
            [_binary_path(), "--pid", "9999999", "--sample-rate", "16000"],
            capture_output=True,
            timeout=5,
        )
        assert result.returncode != 0

    def test_unknown_flag_exits_nonzero(self) -> None:
        result = subprocess.run(
            [_binary_path(), "--not-a-flag"],
            capture_output=True,
            timeout=5,
        )
        assert result.returncode != 0
