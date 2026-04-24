from __future__ import annotations

import asyncio
import json
import logging
import sys
import tempfile
import time
import wave
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

import numpy as np

from app.services.transcription.base import EventSink, TranscriptChunk

logger = logging.getLogger(__name__)


class WorkerClient(Protocol):
    async def start(self) -> None:
        """Boot the persistent worker."""

    async def decode(self, *, audio_path: Path) -> dict[str, object]:
        """Decode the given audio file."""

    async def stop(self) -> None:
        """Stop the persistent worker."""


WorkerClientFactory = Callable[..., WorkerClient]


@dataclass(slots=True)
class SourceBuffer:
    sample_rate: int
    chunks: list[np.ndarray] = field(default_factory=list)
    total_samples: int = 0
    last_decoded_samples: int = 0
    last_transcript: str = ""


class NemoSidecarWorkerClient:
    def __init__(self, *, model_path: Path, python_executable: str, script_path: Path) -> None:
        self._model_path = model_path
        self._python_executable = python_executable
        self._script_path = script_path
        self._process: asyncio.subprocess.Process | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._io_lock = asyncio.Lock()

    async def start(self) -> None:
        if self._process is not None:
            return

        logger.info(
            "starting persistent nemo worker process: model_path=%s python=%s script=%s",
            self._model_path,
            self._python_executable,
            self._script_path,
        )
        process = await asyncio.create_subprocess_exec(
            self._python_executable,
            str(self._script_path),
            "--model-path",
            str(self._model_path),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._process = process
        self._stderr_task = asyncio.create_task(self._drain_stderr())

        try:
            ready_message = await asyncio.wait_for(self._read_message(), timeout=120)
        except Exception:
            await self._force_stop()
            raise

        if ready_message.get("type") != "ready":
            await self._force_stop()
            raise RuntimeError(f"Unexpected NeMo worker startup response: {ready_message}")

    async def decode(self, *, audio_path: Path) -> dict[str, object]:
        async with self._io_lock:
            await self._write_message(
                {
                    "type": "decode",
                    "audio_path": str(audio_path),
                }
            )
            response = await self._read_message()

        if response.get("type") != "decode_result":
            raise RuntimeError(f"Unexpected NeMo worker decode response: {response}")

        if not response.get("ok", False):
            error = str(response.get("error", "unknown error"))
            raise RuntimeError(f"NeMo decode failed: {error}")

        return {
            "transcript": str(response.get("transcript", "")),
            "confidence": float(response.get("confidence", 0.0)),
        }

    async def stop(self) -> None:
        process = self._process
        if process is None:
            return

        try:
            async with self._io_lock:
                if process.returncode is None:
                    with suppress(Exception):
                        await self._write_message({"type": "shutdown"})
                    if process.stdin is not None and not process.stdin.is_closing():
                        process.stdin.close()

                try:
                    await asyncio.wait_for(process.wait(), timeout=10)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
        finally:
            await self._cleanup()

    async def _write_message(self, payload: dict[str, object]) -> None:
        process = self._require_process()
        if process.stdin is None:
            raise RuntimeError("NeMo worker stdin is unavailable")

        process.stdin.write((json.dumps(payload) + "\n").encode("utf-8"))
        await process.stdin.drain()

    async def _read_message(self) -> dict[str, object]:
        process = self._require_process()
        if process.stdout is None:
            raise RuntimeError("NeMo worker stdout is unavailable")

        while True:
            line = await process.stdout.readline()
            if not line:
                await process.wait()
                raise RuntimeError(f"NeMo worker exited before responding (returncode={process.returncode})")

            payload = line.decode("utf-8", errors="replace").strip()
            if not payload:
                continue

            try:
                return json.loads(payload)
            except json.JSONDecodeError:
                logger.info("nemo worker stdout: %s", payload)

    async def _drain_stderr(self) -> None:
        process = self._require_process()
        if process.stderr is None:
            return

        try:
            while True:
                line = await process.stderr.readline()
                if not line:
                    return
                logger.info("nemo worker: %s", line.decode("utf-8", errors="replace").rstrip())
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
        if self._stderr_task is not None:
            self._stderr_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._stderr_task
        self._stderr_task = None
        self._process = None

    def _require_process(self) -> asyncio.subprocess.Process:
        if self._process is None:
            raise RuntimeError("NeMo worker has not been started")
        return self._process


class NemoStreamingProvider:
    name = "nemo"

    def __init__(self, settings: Any, worker_client_factory: WorkerClientFactory | None = None) -> None:
        self.settings = settings
        self._emit_event: EventSink | None = None
        self._model_path_raw = str(getattr(settings, "nemo_model_path", "")).strip()
        self._model_path = Path(self._model_path_raw) if self._model_path_raw else None
        self._python_executable = getattr(settings, "nemo_python_executable", "") or sys.executable
        self._min_audio_secs = float(getattr(settings, "nemo_min_audio_secs", 1.6))
        self._decode_hop_secs = float(getattr(settings, "nemo_decode_hop_secs", 1.6))
        self._worker_script_path = Path(__file__).resolve().parents[3] / "scripts" / "nemo_streaming_worker.py"
        self._worker_client_factory = worker_client_factory or self._build_worker_client
        self._worker_client: WorkerClient | None = None
        self._buffers: dict[str, SourceBuffer] = {}
        self._lock = asyncio.Lock()

    async def start(self, *, emit_event: EventSink) -> None:
        if self._model_path is None or not self._model_path.is_file():
            raise FileNotFoundError(
                f"NeMo model path does not exist or is not a file: {self._model_path_raw or '<unset>'}"
            )

        logger.info(
            "loading nemo provider: model_path=%s python=%s min_audio_secs=%.2f decode_hop_secs=%.2f",
            self._model_path,
            self._python_executable,
            self._min_audio_secs,
            self._decode_hop_secs,
        )
        self._emit_event = emit_event
        self._buffers.clear()
        self._worker_client = self._worker_client_factory(
            model_path=self._model_path,
            python_executable=self._python_executable,
            script_path=self._worker_script_path,
        )
        try:
            await self._worker_client.start()
        except Exception:
            self._emit_event = None
            self._worker_client = None
            raise

        logger.info(
            "persistent nemo worker started: model_path=%s python=%s",
            self._model_path,
            self._python_executable,
        )
        logger.info("nemo provider ready")

    async def push_audio(self, *, source: str, pcm: Any, sample_rate: int) -> None:
        if self._emit_event is None:
            return

        samples = np.asarray(pcm, dtype=np.float32).reshape(-1)
        if samples.size == 0:
            return

        async with self._lock:
            buffer = self._buffers.get(source)
            if buffer is None:
                buffer = SourceBuffer(sample_rate=sample_rate)
                self._buffers[source] = buffer
                logger.info(
                    "asr transcription started: source=%s sample_rate=%d",
                    source,
                    sample_rate,
                )

            if buffer.sample_rate != sample_rate:
                raise ValueError(
                    f"Sample rate changed for source {source}: {buffer.sample_rate} -> {sample_rate}"
                )

            buffer.chunks.append(samples)
            buffer.total_samples += int(samples.size)

            buffered_secs = buffer.total_samples / sample_rate
            undecoded_secs = (buffer.total_samples - buffer.last_decoded_samples) / sample_rate
            if buffered_secs < self._min_audio_secs or undecoded_secs < self._decode_hop_secs:
                return

            await self._decode_source(source=source, buffer=buffer, is_final=False)

    async def stop(self) -> None:
        if self._emit_event is None:
            return

        worker_client = self._worker_client
        try:
            async with self._lock:
                for source, buffer in list(self._buffers.items()):
                    if buffer.total_samples == 0:
                        continue

                    if buffer.total_samples > buffer.last_decoded_samples:
                        await self._decode_source(source=source, buffer=buffer, is_final=True)

                    logger.info(
                        "asr transcription stopped: source=%s total_audio_secs=%.2f total_samples=%d",
                        source,
                        buffer.total_samples / buffer.sample_rate,
                        buffer.total_samples,
                    )

                self._buffers.clear()
        finally:
            self._emit_event = None
            self._worker_client = None

        if worker_client is not None:
            await worker_client.stop()
            logger.info("persistent nemo worker stopped")

        logger.info("nemo provider stopped")

    async def _decode_source(self, *, source: str, buffer: SourceBuffer, is_final: bool) -> None:
        if self._emit_event is None or buffer.total_samples == 0:
            return

        worker_client = self._worker_client
        if worker_client is None:
            raise RuntimeError("NeMo worker is not available")

        audio = np.concatenate(buffer.chunks) if len(buffer.chunks) > 1 else buffer.chunks[0]
        wav_path = await asyncio.to_thread(self._write_wav, audio, buffer.sample_rate)
        started_at = time.perf_counter()
        logger.info(
            "nemo decode started: source=%s is_final=%s buffered_secs=%.2f",
            source,
            is_final,
            buffer.total_samples / buffer.sample_rate,
        )
        try:
            result = await worker_client.decode(audio_path=wav_path)
        finally:
            wav_path.unlink(missing_ok=True)

        transcript = str(result.get("transcript", "")).strip()
        delta = self._extract_increment(buffer.last_transcript, transcript)
        buffer.last_transcript = transcript
        buffer.last_decoded_samples = buffer.total_samples

        if not delta:
            logger.info(
                "nemo decode completed: source=%s is_final=%s elapsed_ms=%.1f transcript_chars=%d emitted_delta_chars=0",
                source,
                is_final,
                (time.perf_counter() - started_at) * 1000,
                len(transcript),
            )
            return

        timestamp = datetime.now(timezone.utc).isoformat()
        logger.info(
            "nemo decode completed: source=%s is_final=%s elapsed_ms=%.1f transcript_chars=%d emitted_delta_chars=%d",
            source,
            is_final,
            (time.perf_counter() - started_at) * 1000,
            len(transcript),
            len(delta),
        )
        await self._emit_event(
            TranscriptChunk(
                source=source,
                text=delta,
                is_partial=not is_final,
                started_at=timestamp,
                ended_at=timestamp,
                confidence=float(result.get("confidence", 0.0)),
            )
        )

    @staticmethod
    def _build_worker_client(*, model_path: Path, python_executable: str, script_path: Path) -> WorkerClient:
        return NemoSidecarWorkerClient(
            model_path=model_path,
            python_executable=python_executable,
            script_path=script_path,
        )

    @staticmethod
    def _write_wav(audio: np.ndarray, sample_rate: int) -> Path:
        clipped = np.clip(audio, -1.0, 1.0)
        pcm16 = (clipped * 32767.0).astype(np.int16)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
            path = Path(handle.name)

        with wave.open(str(path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm16.tobytes())

        return path

    @staticmethod
    def _extract_increment(previous: str, current: str) -> str:
        previous_words = previous.split()
        current_words = current.split()

        shared = 0
        for previous_word, current_word in zip(previous_words, current_words):
            if previous_word != current_word:
                break
            shared += 1

        return " ".join(current_words[shared:]).strip()
