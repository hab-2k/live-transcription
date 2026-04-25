from __future__ import annotations

import asyncio
import concurrent.futures
import logging
from datetime import datetime, timezone
from typing import Any

import numpy as np

from app.services.transcription.base import EventSink, TranscriptChunk
from app.services.transcription.provider_updates import ProviderTranscriptUpdate, UpdateSink

logger = logging.getLogger(__name__)

_DEFAULT_MODEL_ID = "mlx-community/parakeet-tdt-0.6b-v2"

# Buffer at least this many seconds of audio before sending to the
# transcriber.  Small chunks cause per_feature mel-normalization in
# parakeet-mlx to produce meaningless statistics, corrupting features.
_MIN_BUFFER_SECS = 0.5


class ParakeetUnifiedProvider:
    name = "parakeet_unified"

    def __init__(self, settings: Any, model: str = "") -> None:
        self.settings = settings
        self._emit_event: EventSink | None = None
        self._emit_update: UpdateSink | None = None

        # Priority: explicit model param > settings > default
        raw = model.strip() if model else ""
        if not raw:
            raw = str(getattr(settings, "parakeet_model_path", "") or "").strip()
        # Ignore paths to .nemo files — those are for the NeMo provider, not parakeet-mlx
        if not raw or raw.endswith(".nemo"):
            raw = _DEFAULT_MODEL_ID
        self._model_id = raw

        self._model: Any = None
        self._stream_ctx: Any = None
        self._transcriber: Any = None
        self._executor: concurrent.futures.ThreadPoolExecutor | None = None
        self._lock = asyncio.Lock()
        self._prev_finalized_count: int = 0
        self._prev_draft_text: str = ""
        self._total_samples: dict[str, int] = {}
        self._sample_rates: dict[str, int] = {}
        self._audio_buffers: dict[str, list[np.ndarray]] = {}
        self._audio_buffer_samples: dict[str, int] = {}

    async def start(
        self,
        *,
        emit_update: UpdateSink | None = None,
        emit_event: EventSink | None = None,
    ) -> None:
        self._emit_event = emit_event
        self._emit_update = emit_update
        self._prev_finalized_count = 0
        self._prev_draft_text = ""
        self._total_samples.clear()
        self._sample_rates.clear()
        self._audio_buffers.clear()
        self._audio_buffer_samples.clear()

        logger.info("parakeet_unified provider starting: model=%s", self._model_id)
        async with self._lock:
            try:
                self._model, self._stream_ctx, self._transcriber = await self._run_on_executor(
                    self._load_model_and_open_stream
                )
            except Exception:
                self._emit_event = None
                self._emit_update = None
                self._model = None
                self._stream_ctx = None
                self._transcriber = None
                await self._shutdown_executor()
                raise

        logger.info("parakeet_unified provider ready (streaming context open)")

    async def push_audio(self, *, source: str, pcm: Any, sample_rate: int) -> None:
        if self._emit_event is None and self._emit_update is None:
            return

        samples = np.asarray(pcm, dtype=np.float32).reshape(-1)
        if samples.size == 0:
            return

        if source not in self._total_samples:
            self._sample_rates[source] = sample_rate
            self._total_samples[source] = 0
            logger.info("stream started: source=%s sample_rate=%d", source, sample_rate)

        self._total_samples[source] += samples.size

        # Accumulate audio so each add_audio call has enough frames for
        # stable per_feature mel normalization inside parakeet-mlx.
        buf = self._audio_buffers.setdefault(source, [])
        buf.append(samples)
        self._audio_buffer_samples[source] = self._audio_buffer_samples.get(source, 0) + samples.size

        min_samples = int(_MIN_BUFFER_SECS * sample_rate)
        if self._audio_buffer_samples[source] < min_samples:
            return

        chunk = np.concatenate(buf)
        buf.clear()
        self._audio_buffer_samples[source] = 0

        await self._send_audio_to_transcriber(source=source, samples=chunk)

    async def _send_audio_to_transcriber(self, *, source: str, samples: np.ndarray) -> None:
        async with self._lock:
            transcriber = self._transcriber
            if transcriber is None:
                return

            try:
                finalized, draft = await self._run_on_executor(
                    lambda: self._add_audio_and_snapshot(transcriber, samples)
                )
            except Exception:
                logger.exception("add_audio failed: source=%s", source)
                return

            self._prev_finalized_count = len(finalized)

            # Combine finalized + draft into a single progressive text.
            # Emitting finalized deltas as is_final=True would close the
            # timeline turn prematurely and cause duplication; instead we
            # emit the full running text as a partial and let
            # finalize_utterance / silence detection close the turn.
            combined = self._tokens_to_text(finalized + draft)
            if not combined:
                self._prev_draft_text = ""
                return

        if combined != self._prev_draft_text:
            self._prev_draft_text = combined
            await self._emit_delta(source=source, text=combined, is_final=False)

    async def finalize_utterance(self, *, source: str) -> bool:
        if self._emit_event is None and self._emit_update is None:
            return False

        # Flush any buffered audio so it's included in the finalized result.
        await self._flush_audio_buffer(source)

        async with self._lock:
            transcriber = self._transcriber
            model = self._model
            if transcriber is None or model is None:
                return False

            try:
                final_text = await self._run_on_executor(
                    lambda: self._current_result_text(transcriber)
                )
            except Exception:
                logger.exception("utterance snapshot failed: source=%s", source)
                return False

            try:
                await self._run_on_executor(self._reopen_stream)
            except Exception:
                logger.exception("utterance stream rollover failed: source=%s", source)
                return False

        if not final_text:
            return False

        logger.info("utterance finalized: source=%s text=%r", source, final_text)
        await self._emit_delta(source=source, text=final_text, is_final=True)
        return True

    async def stop(self) -> None:
        if self._emit_event is None and self._emit_update is None:
            return

        # Flush any remaining buffered audio before stopping.
        for source in list(self._audio_buffers):
            await self._flush_audio_buffer(source)

        stop_source = (
            next(reversed(self._total_samples))
            if len(self._total_samples) == 1
            else "mixed"
        )

        for source, total in self._total_samples.items():
            sr = self._sample_rates.get(source, 16000)
            logger.info("stream stopped: source=%s total_secs=%.2f", source, total / sr)

        self._total_samples.clear()
        self._sample_rates.clear()
        self._audio_buffers.clear()
        self._audio_buffer_samples.clear()

        pending_stop_updates: list[tuple[str, str]] = []

        # Close the streaming context
        async with self._lock:
            transcriber = self._transcriber
            if transcriber is not None:
                try:
                    finalized, draft = await self._run_on_executor(
                        lambda: self._snapshot_tokens(transcriber)
                    )
                except Exception:
                    logger.exception("stream snapshot failed during stop")
                else:
                    if len(finalized) > self._prev_finalized_count:
                        new_final_text = self._tokens_to_text(
                            finalized[self._prev_finalized_count :]
                        )
                        self._prev_finalized_count = len(finalized)
                        if new_final_text:
                            pending_stop_updates.append(("finalized", new_final_text))

                    draft_text = self._tokens_to_text(draft)
                    if draft_text:
                        pending_stop_updates.append(("draft", draft_text))
                        self._prev_draft_text = ""

            if self._stream_ctx is not None:
                try:
                    await self._run_on_executor(
                        lambda: self._stream_ctx.__exit__(None, None, None)
                    )
                except Exception:
                    logger.exception("stream context exit failed")
                self._stream_ctx = None
                self._transcriber = None
                logger.info("parakeet streaming context closed")

            self._model = None

        for update_kind, text in pending_stop_updates:
            logger.info("%s on stop: %r", update_kind, text)
            await self._emit_delta(source=stop_source, text=text, is_final=True)

        await self._shutdown_executor()
        self._emit_event = None
        self._emit_update = None

    async def _flush_audio_buffer(self, source: str) -> None:
        buf = self._audio_buffers.get(source)
        if not buf:
            return
        chunk = np.concatenate(buf)
        buf.clear()
        self._audio_buffer_samples[source] = 0
        if chunk.size > 0:
            await self._send_audio_to_transcriber(source=source, samples=chunk)

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

    def _load_model_and_open_stream(self) -> tuple[Any, Any, Any]:
        from parakeet_mlx import from_pretrained

        model = from_pretrained(self._model_id)
        stream_ctx, transcriber = self._open_stream_for_model(model)
        return model, stream_ctx, transcriber

    def _add_audio_and_snapshot(self, transcriber: Any, samples: np.ndarray) -> tuple[list[Any], list[Any]]:
        import mlx.core as mx

        transcriber.add_audio(mx.array(samples))
        return self._snapshot_tokens(transcriber)

    @staticmethod
    def _open_stream_for_model(model: Any) -> tuple[Any, Any]:
        stream_ctx = model.transcribe_stream(
            context_size=(256, 256),
            depth=1,
        )
        transcriber = stream_ctx.__enter__()
        return stream_ctx, transcriber

    def _reopen_stream(self) -> None:
        if self._stream_ctx is not None:
            self._stream_ctx.__exit__(None, None, None)

        if self._model is None:
            raise RuntimeError("Parakeet model is not loaded")

        self._stream_ctx, self._transcriber = self._open_stream_for_model(self._model)
        self._prev_finalized_count = 0
        self._prev_draft_text = ""

    @staticmethod
    def _snapshot_tokens(transcriber: Any) -> tuple[list[Any], list[Any]]:
        return list(transcriber.finalized_tokens), list(transcriber.draft_tokens)

    @classmethod
    def _current_result_text(cls, transcriber: Any) -> str:
        result = getattr(transcriber, "result", None)
        text = str(getattr(result, "text", "") or "").strip()
        if text:
            return text

        finalized, draft = cls._snapshot_tokens(transcriber)
        return cls._tokens_to_text(finalized + draft)

    @staticmethod
    def _tokens_to_text(tokens: list[Any]) -> str:
        return "".join(str(getattr(token, "text", "")) for token in tokens).strip()

    async def _run_on_executor(self, func):
        loop = asyncio.get_running_loop()
        executor = self._ensure_executor()
        return await loop.run_in_executor(executor, func)

    def _ensure_executor(self) -> concurrent.futures.ThreadPoolExecutor:
        if self._executor is None:
            self._executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix="parakeet-unified",
            )
        return self._executor

    async def _shutdown_executor(self) -> None:
        executor = self._executor
        if executor is None:
            return

        self._executor = None
        await asyncio.to_thread(executor.shutdown, wait=True)
