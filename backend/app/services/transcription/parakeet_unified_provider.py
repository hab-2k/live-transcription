from __future__ import annotations

import asyncio
import base64
import json
import logging
import sys
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from app.services.transcription.base import EventSink, TranscriptChunk
from app.services.transcription.provider_updates import ProviderTranscriptUpdate, UpdateSink

logger = logging.getLogger(__name__)

# Accumulate at least this much new audio before sending to the worker.
# Keeps IPC overhead low while staying responsive.
_MIN_PUSH_SECS = 0.2


@dataclass(slots=True)
class _SourceBuffer:
    sample_rate: int
    pending: list[np.ndarray] = field(default_factory=list)
    pending_samples: int = 0
    total_samples: int = 0


class _WorkerClient:
    """
    Manages the parakeet_unified_streaming_worker subprocess.
    Protocol: push_chunk / finalize / reset / shutdown over stdin/stdout JSON lines.
    """

    def __init__(self, *, model_path: Path, python_executable: str, script_path: Path) -> None:
        self._model_path = model_path
        self._python_executable = python_executable
        self._script_path = script_path
        self._process: asyncio.subprocess.Process | None = None
        self._stderr_task: asyncio.Task | None = None
        self._io_lock = asyncio.Lock()

    async def start(self) -> None:
        if self._process is not None:
            return

        logger.info(
            "starting parakeet worker: model=%s python=%s script=%s",
            self._model_path,
            self._python_executable,
            self._script_path,
        )
        self._process = await asyncio.create_subprocess_exec(
            self._python_executable,
            str(self._script_path),
            "--model-path",
            str(self._model_path),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._stderr_task = asyncio.create_task(self._drain_stderr())

        try:
            msg = await asyncio.wait_for(self._read_message(), timeout=120)
        except Exception:
            await self._force_stop()
            raise

        if msg.get("type") != "ready":
            await self._force_stop()
            raise RuntimeError(f"Unexpected startup message from parakeet worker: {msg}")

    async def push_chunk(self, samples: np.ndarray) -> str:
        """Send new audio samples; return any new text produced."""
        audio_b64 = base64.b64encode(samples.astype(np.float32).tobytes()).decode("ascii")
        async with self._io_lock:
            await self._write({"type": "push_chunk", "audio_b64": audio_b64})
            msg = await self._read_message()
        if not msg.get("ok", False):
            raise RuntimeError(f"push_chunk failed: {msg.get('error')}")
        return str(msg.get("text", ""))

    async def finalize(self) -> str:
        """Flush remaining audio; return any final text."""
        async with self._io_lock:
            await self._write({"type": "finalize"})
            msg = await self._read_message()
        if not msg.get("ok", False):
            raise RuntimeError(f"finalize failed: {msg.get('error')}")
        return str(msg.get("text", ""))

    async def stop(self) -> None:
        process = self._process
        if process is None:
            return
        try:
            async with self._io_lock:
                if process.returncode is None:
                    with suppress(Exception):
                        await self._write({"type": "shutdown"})
                    if process.stdin and not process.stdin.is_closing():
                        process.stdin.close()
                    try:
                        await asyncio.wait_for(process.wait(), timeout=10)
                    except asyncio.TimeoutError:
                        process.kill()
                        await process.wait()
        finally:
            await self._cleanup()

    async def _write(self, payload: dict) -> None:
        process = self._require_process()
        if process.stdin is None:
            raise RuntimeError("Worker stdin is unavailable")
        process.stdin.write((json.dumps(payload) + "\n").encode())
        await process.stdin.drain()

    async def _read_message(self) -> dict:
        process = self._require_process()
        if process.stdout is None:
            raise RuntimeError("Worker stdout is unavailable")
        while True:
            line = await process.stdout.readline()
            if not line:
                await process.wait()
                raise RuntimeError(f"Parakeet worker exited unexpectedly (rc={process.returncode})")
            text = line.decode("utf-8", errors="replace").strip()
            if not text:
                continue
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                logger.info("parakeet worker stdout: %s", text)

    async def _drain_stderr(self) -> None:
        process = self._require_process()
        if process.stderr is None:
            return
        try:
            while True:
                line = await process.stderr.readline()
                if not line:
                    return
                logger.info("parakeet worker: %s", line.decode("utf-8", errors="replace").rstrip())
        except asyncio.CancelledError:
            raise

    async def _force_stop(self) -> None:
        process = self._process
        try:
            if process is not None and process.returncode is None:
                process.kill()
                await process.wait()
        finally:
            await self._cleanup()

    async def _cleanup(self) -> None:
        if self._stderr_task:
            self._stderr_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._stderr_task
        self._stderr_task = None
        self._process = None

    def _require_process(self) -> asyncio.subprocess.Process:
        if self._process is None:
            raise RuntimeError("Parakeet worker has not been started")
        return self._process


class ParakeetUnifiedProvider:
    name = "parakeet_unified"

    def __init__(self, settings: Any, worker_client_factory=None) -> None:
        self.settings = settings
        self._emit_event: EventSink | None = None
        self._emit_update: UpdateSink | None = None

        parakeet_path = str(getattr(settings, "parakeet_model_path", "") or "").strip()
        nemo_path = str(getattr(settings, "nemo_model_path", "") or "").strip()
        self._model_path_raw = parakeet_path or nemo_path
        self._model_path = Path(self._model_path_raw) if self._model_path_raw else None

        self._python_executable = (
            getattr(settings, "parakeet_python_executable", "")
            or getattr(settings, "nemo_python_executable", "")
            or sys.executable
        )
        self._worker_script_path = (
            Path(__file__).resolve().parents[3] / "scripts" / "parakeet_unified_streaming_worker.py"
        )
        self._worker_client_factory = worker_client_factory or _WorkerClient
        self._worker: _WorkerClient | None = None
        self._buffers: dict[str, _SourceBuffer] = {}
        self._lock = asyncio.Lock()

    async def start(
        self,
        *,
        emit_update: UpdateSink | None = None,
        emit_event: EventSink | None = None,
    ) -> None:
        if self._model_path is None or not self._model_path.is_file():
            raise FileNotFoundError(
                f"Parakeet model not found: {self._model_path_raw or '<unset>'}"
            )

        logger.info(
            "parakeet_unified provider starting: model=%s python=%s",
            self._model_path,
            self._python_executable,
        )
        self._emit_event = emit_event
        self._emit_update = emit_update
        self._buffers.clear()

        self._worker = self._worker_client_factory(
            model_path=self._model_path,
            python_executable=self._python_executable,
            script_path=self._worker_script_path,
        )
        try:
            await self._worker.start()
        except Exception:
            self._emit_event = None
            self._emit_update = None
            self._worker = None
            raise

        logger.info("parakeet_unified provider ready")

    async def push_audio(self, *, source: str, pcm: Any, sample_rate: int) -> None:
        if self._emit_event is None and self._emit_update is None:
            return

        samples = np.asarray(pcm, dtype=np.float32).reshape(-1)
        if samples.size == 0:
            return

        async with self._lock:
            buf = self._buffers.get(source)
            if buf is None:
                buf = _SourceBuffer(sample_rate=sample_rate)
                self._buffers[source] = buf
                logger.info("stream started: source=%s sample_rate=%d", source, sample_rate)

            buf.pending.append(samples)
            buf.pending_samples += samples.size
            buf.total_samples += samples.size

            min_push = int(_MIN_PUSH_SECS * sample_rate)
            if buf.pending_samples < min_push:
                return

            chunk = np.concatenate(buf.pending)
            buf.pending.clear()
            buf.pending_samples = 0

            worker = self._worker
            if worker is None:
                return

            try:
                delta = await worker.push_chunk(chunk)
            except Exception:
                logger.exception("push_chunk failed: source=%s", source)
                self._worker = None  # prevent further retries against a dead worker
                return

        if delta:
            await self._emit_delta(source=source, text=delta, is_final=False)

    async def stop(self) -> None:
        if self._emit_event is None and self._emit_update is None:
            return

        worker = self._worker
        self._worker = None

        async with self._lock:
            buffers = dict(self._buffers)
            self._buffers.clear()

        if worker is not None:
            for source, buf in buffers.items():
                # Flush any buffered audio not yet sent
                if buf.pending:
                    remaining = np.concatenate(buf.pending)
                    buf.pending.clear()
                    buf.pending_samples = 0
                    try:
                        delta = await worker.push_chunk(remaining)
                        if delta:
                            await self._emit_delta(source=source, text=delta, is_final=False)
                    except Exception:
                        logger.exception("final push_chunk failed: source=%s", source)

                # Finalize the streaming session
                try:
                    delta = await worker.finalize()
                    if delta:
                        await self._emit_delta(source=source, text=delta, is_final=True)
                except Exception:
                    logger.exception("finalize failed: source=%s", source)

                logger.info(
                    "stream stopped: source=%s total_secs=%.2f",
                    source,
                    buf.total_samples / buf.sample_rate,
                )

            await worker.stop()
            logger.info("parakeet worker stopped")

        self._emit_event = None
        self._emit_update = None

    async def _emit_delta(self, *, source: str, text: str, is_final: bool) -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        if self._emit_update is not None:
            await self._emit_update(
                ProviderTranscriptUpdate(
                    stream_id=source,
                    source=source,
                    text=text,
                    is_final=is_final,
                    started_at=timestamp,
                    ended_at=timestamp,
                    confidence=0.0,
                )
            )
        elif self._emit_event is not None:
            await self._emit_event(
                TranscriptChunk(
                    source=source,
                    text=text,
                    is_partial=not is_final,
                    started_at=timestamp,
                    ended_at=timestamp,
                    confidence=0.0,
                )
            )
