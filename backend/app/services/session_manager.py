from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Awaitable, Callable
from uuid import uuid4

from app.contracts.events import CoachingNudgeEvent, RuleFlagEvent, SessionEvent, SessionStatusEvent, TranscriptEvent, VoiceActivityEvent
from app.contracts.session import SessionConfig, TranscriptionConfig
from app.services.audio.base import AudioFrame, CaptureService
from app.services.audio.device_service import DeviceService
from app.services.coaching.llm_client import OpenAICompatibleClient
from app.services.coaching.nudge_service import NudgeService
from app.services.coaching.prompt_builder import PromptBuilder
from app.services.coaching.rule_engine import RuleEngine
from app.services.coaching.summary_service import CallSummary, SummaryService
from app.services.debug.debug_store import DebugStore
from app.services.diarization.base import Diarizer
from app.services.events.broadcaster import EventBroadcaster
from app.services.transcription.base import TranscriptChunk, TranscriptionProvider
from app.services.transcription.provider_updates import ProviderTranscriptUpdate
from app.services.transcription.normalizer import normalize_chunk, role_for_chunk
from app.services.transcription.timeline import TranscriptTimelineAssembler


@dataclass(slots=True)
class SessionRuntime:
    config: SessionConfig
    coaching_paused: bool
    prompt_builder: PromptBuilder | None
    llm_client: OpenAICompatibleClient | None
    timeline: TranscriptTimelineAssembler
    emit_update: Callable[[ProviderTranscriptUpdate], Awaitable[None]] | None = None
    emit_event: Callable[[TranscriptChunk], Awaitable[None]] | None = None


class SessionManager:
    def __init__(
        self,
        *,
        capture_service: CaptureService,
        provider: TranscriptionProvider,
        broadcaster: EventBroadcaster,
        device_service: DeviceService | None = None,
        diarizer: Diarizer | None = None,
        rule_engine: RuleEngine | None = None,
        prompt_builder: PromptBuilder | None = None,
        prompt_builder_factory: Callable[[str], PromptBuilder] | None = None,
        llm_client: OpenAICompatibleClient | None = None,
        llm_client_factory: Callable[[SessionConfig], OpenAICompatibleClient] | None = None,
        nudge_service: NudgeService | None = None,
        summary_service: SummaryService | None = None,
        debug_store: DebugStore | None = None,
    ) -> None:
        self.capture_service = capture_service
        self.provider = provider
        self.broadcaster = broadcaster
        self.device_service = device_service
        self.diarizer = diarizer
        self.rule_engine = rule_engine
        self.prompt_builder = prompt_builder
        self.prompt_builder_factory = prompt_builder_factory
        self.llm_client = llm_client
        self.llm_client_factory = llm_client_factory
        self.nudge_service = nudge_service
        self.summary_service = summary_service
        self.debug_store = debug_store
        self._events: dict[str, list[SessionEvent]] = defaultdict(list)
        self._runtimes: dict[str, SessionRuntime] = {}
        self._summaries: dict[str, CallSummary] = {}
        self._active_session_id: str | None = None
        self._vad_threshold: float = 0.01

    async def start_session(self, config: SessionConfig) -> str:
        if self.device_service is not None:
            validation = self.device_service.validate_microphone(config.microphone_device_id)
            if not validation.is_valid:
                raise ValueError(validation.reason or "Unknown microphone device")

        session_id = str(uuid4())
        self._runtimes[session_id] = SessionRuntime(
            config=config,
            coaching_paused=False,
            prompt_builder=self._create_prompt_builder(config),
            llm_client=self._create_llm_client(config),
            timeline=TranscriptTimelineAssembler(),
        )

        async def emit_event(chunk: TranscriptChunk) -> None:
            await self._handle_transcript_chunk(session_id=session_id, config=config, chunk=chunk)

        async def emit_update(update: ProviderTranscriptUpdate) -> None:
            await self._handle_provider_update(session_id=session_id, update=update)

        self._runtimes[session_id].emit_event = emit_event
        self._runtimes[session_id].emit_update = emit_update
        self._active_session_id = session_id
        await self._start_provider(runtime=self._runtimes[session_id])
        await self.capture_service.start(config=config, on_audio=self._handle_audio_frame)
        return session_id

    async def stop_session(self, session_id: str) -> CallSummary | None:
        runtime = self._runtimes.get(session_id)
        if runtime is None:
            return self._summaries.get(session_id)

        if self.summary_service is not None:
            transcript = [
                event.model_dump()
                for event in self._events.get(session_id, [])
                if getattr(event, "type", None) == "transcript"
            ]
            self._summaries[session_id] = self.summary_service.build(transcript)

        await self.capture_service.stop()
        await self.provider.stop()
        if self._active_session_id == session_id:
            self._active_session_id = None
        del self._runtimes[session_id]
        return self._summaries.get(session_id)

    def list_events(self, session_id: str) -> list[SessionEvent]:
        return list(self._events.get(session_id, []))

    def get_summary(self, session_id: str) -> CallSummary | None:
        return self._summaries.get(session_id)

    async def set_coaching_paused(self, session_id: str, paused: bool) -> str:
        runtime = self._runtimes.get(session_id)
        if runtime is None:
            raise KeyError(session_id)

        runtime.coaching_paused = paused
        status = "coaching_paused" if paused else "coaching_resumed"
        event = SessionStatusEvent(status=status, session_id=session_id)
        self._events[session_id].append(event)
        await self.broadcaster.publish(session_id, event.model_dump())
        return status

    async def set_transcription_config(self, session_id: str, transcription: TranscriptionConfig) -> str:
        runtime = self._runtimes.get(session_id)
        if runtime is None:
            raise KeyError(session_id)

        await self.provider.stop()
        runtime.config = runtime.config.model_copy(
            update={
                "transcription": transcription,
                "asr_provider": transcription.provider,
            }
        )

        await self._start_provider(runtime=runtime)

        status = SessionStatusEvent(status="transcription_reconfigured", session_id=session_id)
        self._events[session_id].append(status)
        await self.broadcaster.publish(session_id, status.model_dump())
        return status.status

    async def _handle_audio_frame(self, frame: AudioFrame) -> None:
        await self.provider.push_audio(
            source=frame.source,
            pcm=frame.pcm,
            sample_rate=frame.sample_rate,
        )

        if self._active_session_id is not None:
            await self._emit_voice_activity(self._active_session_id, frame)

    async def _start_provider(self, *, runtime: SessionRuntime) -> None:
        try:
            await self.provider.start(
                emit_update=runtime.emit_update,
                emit_event=runtime.emit_event,
            )
        except TypeError:
            if runtime.emit_event is None:
                raise
            await self.provider.start(emit_event=runtime.emit_event)

    async def _emit_voice_activity(self, session_id: str, frame: AudioFrame) -> None:
        try:
            pcm = frame.pcm
            rms = float(math.sqrt(sum(float(s) ** 2 for s in pcm) / max(len(pcm), 1)))
        except (TypeError, ValueError):
            rms = 0.0
        level = min(rms / 0.15, 1.0)
        event = VoiceActivityEvent(
            source=frame.source,
            level=round(level, 3),
            active=rms >= self._vad_threshold,
        )
        await self.broadcaster.publish(session_id, event.model_dump())

    async def _handle_transcript_chunk(
        self,
        *,
        session_id: str,
        config: SessionConfig,
        chunk: TranscriptChunk,
    ) -> None:
        chunks = [chunk]
        if config.diarization_enabled and self.diarizer is not None:
            chunks = await self.diarizer.process(chunks)

        for current_chunk in chunks:
            event = normalize_chunk(
                source=current_chunk.source,
                role=role_for_chunk(chunk=current_chunk, capture_mode=config.capture_mode),
                text=current_chunk.text,
                is_partial=current_chunk.is_partial,
                started_at=current_chunk.started_at,
                ended_at=current_chunk.ended_at,
                confidence=current_chunk.confidence,
            )
            self._events[session_id].append(event)
            await self.broadcaster.publish(session_id, event.model_dump())
            if not current_chunk.is_partial:
                await self._maybe_emit_coaching_events(session_id=session_id, current_chunk=current_chunk)

    async def _handle_provider_update(
        self,
        *,
        session_id: str,
        update: ProviderTranscriptUpdate,
    ) -> None:
        runtime = self._runtimes.get(session_id)
        if runtime is None:
            return

        chunk = TranscriptChunk(
            source=update.source,
            text=update.text,
            is_partial=not update.is_final,
            started_at=update.started_at,
            ended_at=update.ended_at,
            confidence=update.confidence,
        )
        role = role_for_chunk(chunk=chunk, capture_mode=runtime.config.capture_mode)
        turn_event = runtime.timeline.ingest(update, role=role)
        self._events[session_id].append(turn_event)
        await self.broadcaster.publish(session_id, turn_event.model_dump())

        await self._handle_transcript_chunk(
            session_id=session_id,
            config=runtime.config,
            chunk=chunk,
        )

    async def _maybe_emit_coaching_events(self, *, session_id: str, current_chunk: TranscriptChunk) -> None:
        runtime = self._runtimes.get(session_id)
        if runtime is None or runtime.coaching_paused:
            return

        if not all([self.rule_engine, runtime.prompt_builder, runtime.llm_client, self.nudge_service]):
            return

        transcript_window = [
            event.model_dump()
            for event in self._events[session_id]
            if getattr(event, "type", None) == "transcript"
        ][-6:]
        rule_result = self.rule_engine.evaluate(transcript=transcript_window)

        for flag in rule_result.flags:
            if not self._flag_already_present(session_id=session_id, code=flag.code):
                self._events[session_id].append(flag)
                await self.broadcaster.publish(session_id, flag.model_dump())

        prompt = runtime.prompt_builder.build(
            transcript=transcript_window,
            flags=[flag.model_dump() for flag in rule_result.flags],
        )
        try:
            completion = await runtime.llm_client.complete(prompt=prompt)
        except Exception:
            status = SessionStatusEvent(status="coaching_unavailable", session_id=session_id)
            self._events[session_id].append(status)
            await self.broadcaster.publish(session_id, status.model_dump())
            if self.debug_store is not None:
                self.debug_store.record("llm_error", "Coaching paused after endpoint failure")
            return
        message = completion["message"].strip()

        if self.nudge_service.should_emit(message):
            nudge = CoachingNudgeEvent(
                title=message.rstrip("."),
                message=message,
                timestamp=current_chunk.ended_at,
                priority="normal",
                source_turn_ids=[f"{session_id}:{len(transcript_window)}"],
            )
            self._events[session_id].append(nudge)
            await self.broadcaster.publish(session_id, nudge.model_dump())

    def _flag_already_present(self, *, session_id: str, code: str) -> bool:
        return any(
            isinstance(event, RuleFlagEvent) and event.code == code
            for event in self._events.get(session_id, [])
        )

    def _create_prompt_builder(self, config: SessionConfig) -> PromptBuilder | None:
        if self.prompt_builder_factory is not None:
            return self.prompt_builder_factory(config.persona)
        return self.prompt_builder

    def _create_llm_client(self, config: SessionConfig) -> OpenAICompatibleClient | None:
        if self.llm_client_factory is not None:
            return self.llm_client_factory(config)
        return self.llm_client
