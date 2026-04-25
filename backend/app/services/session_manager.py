from __future__ import annotations

import logging
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable
from uuid import uuid4

from app.contracts.events import CoachingNudgeEvent, RuleFlagEvent, SessionEvent, SessionStatusEvent, TranscriptTurnEvent, VoiceActivityEvent
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
from app.services.transcription.normalizer import role_for_chunk
from app.services.transcription.runtime_controller import TranscriptionRuntimeController
from app.services.transcription.segmentation import SegmentationPolicy
from app.services.transcription.timeline import TranscriptTimelineAssembler
from app.services.transcription.vad import SileroVadService, VadDecision, VadService

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SessionRuntime:
    config: SessionConfig
    coaching_paused: bool
    prompt_builder: PromptBuilder | None
    llm_client: OpenAICompatibleClient | None
    timeline: TranscriptTimelineAssembler
    provider: TranscriptionProvider | None = None
    emit_update: Callable[[ProviderTranscriptUpdate], Awaitable[None]] | None = None
    emit_event: Callable[[TranscriptChunk], Awaitable[None]] | None = None
    segmentation_policy: SegmentationPolicy = field(
        default_factory=lambda: SegmentationPolicy.for_capture_mode("mic_only")
    )
    vad_services: dict[str, VadService] = field(default_factory=dict)
    forced_finalized_prefixes: dict[str, str] = field(default_factory=dict)


class SessionManager:
    def __init__(
        self,
        *,
        capture_service: CaptureService,
        provider: TranscriptionProvider | None = None,
        provider_factory: Callable[..., TranscriptionProvider] | None = None,
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
        runtime_controller: TranscriptionRuntimeController | None = None,
        vad_service_factory: Callable[..., VadService] | None = None,
    ) -> None:
        self.capture_service = capture_service
        self.provider = provider
        self.provider_factory = provider_factory
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
        self.runtime_controller = runtime_controller or TranscriptionRuntimeController()
        self.vad_service_factory = vad_service_factory or self._build_vad_service
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
            segmentation_policy=SegmentationPolicy.for_capture_mode(
                config.capture_mode,
                silence_finalize_ms=config.transcription.segmentation.silence_finalize_ms if config.transcription else None,
            ),
        )

        async def emit_event(chunk: TranscriptChunk) -> None:
            await self._handle_provider_update(
                session_id=session_id,
                update=ProviderTranscriptUpdate(
                    stream_id=chunk.source,
                    source=chunk.source,
                    text=chunk.text,
                    is_final=not chunk.is_partial,
                    started_at=chunk.started_at,
                    ended_at=chunk.ended_at,
                    confidence=chunk.confidence,
                ),
            )

        async def emit_update(update: ProviderTranscriptUpdate) -> None:
            await self._handle_provider_update(session_id=session_id, update=update)

        self._runtimes[session_id].emit_event = emit_event
        self._runtimes[session_id].emit_update = emit_update
        self._active_session_id = session_id
        self._runtimes[session_id].provider = await self.runtime_controller.start(
            config=config,
            provider=self.provider,
            provider_factory=self.provider_factory,
            emit_update=emit_update,
            emit_event=emit_event,
        )
        await self.capture_service.start(config=config, on_audio=self._handle_audio_frame)
        return session_id

    async def stop_session(self, session_id: str) -> CallSummary | None:
        runtime = self._runtimes.get(session_id)
        if runtime is None:
            return self._summaries.get(session_id)

        await self.capture_service.stop()
        await self.runtime_controller.stop(runtime.provider)

        if self.summary_service is not None:
            transcript = [
                turn.model_dump()
                for turn in self._latest_turn_snapshots(session_id)
                if turn.is_final
            ]
            self._summaries[session_id] = self.summary_service.build(transcript)

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

        runtime.provider, runtime.config = await self.runtime_controller.reconfigure(
            current_provider=runtime.provider,
            current_config=runtime.config,
            transcription=transcription,
            provider=self.provider,
            provider_factory=self.provider_factory,
            emit_update=runtime.emit_update,
            emit_event=runtime.emit_event,
        )
        runtime.segmentation_policy = SegmentationPolicy.for_capture_mode(
            runtime.config.capture_mode,
            silence_finalize_ms=runtime.config.transcription.segmentation.silence_finalize_ms if runtime.config.transcription else None,
        )
        runtime.vad_services.clear()
        runtime.forced_finalized_prefixes.clear()

        status = SessionStatusEvent(status="transcription_reconfigured", session_id=session_id)
        self._events[session_id].append(status)
        await self.broadcaster.publish(session_id, status.model_dump())
        return status.status

    async def _handle_audio_frame(self, frame: AudioFrame) -> None:
        if self._active_session_id is None:
            return

        runtime = self._runtimes.get(self._active_session_id)
        if runtime is None or runtime.provider is None:
            return

        vad_decision = self._detect_vad(runtime=runtime, frame=frame)

        if vad_decision is None or vad_decision.active:
            await runtime.provider.push_audio(
                source=frame.source,
                pcm=frame.pcm,
                sample_rate=frame.sample_rate,
            )

        if vad_decision is not None:
            await self._maybe_finalize_turn_after_silence(
                session_id=self._active_session_id,
                runtime=runtime,
                frame=frame,
                vad_decision=vad_decision,
            )

        await self._emit_voice_activity(self._active_session_id, frame, vad_decision=vad_decision)

    async def _emit_voice_activity(
        self,
        session_id: str,
        frame: AudioFrame,
        *,
        vad_decision: VadDecision | None = None,
    ) -> None:
        try:
            pcm = frame.pcm
            rms = float(math.sqrt(sum(float(s) ** 2 for s in pcm) / max(len(pcm), 1)))
        except (TypeError, ValueError):
            rms = 0.0

        if vad_decision is not None:
            level = max(0.0, min(vad_decision.speech_confidence, 1.0))
            active = vad_decision.active
        else:
            level = min(rms / 0.15, 1.0)
            active = rms >= self._vad_threshold

        event = VoiceActivityEvent(
            source=frame.source,
            level=round(level, 3),
            active=active,
        )
        await self.broadcaster.publish(session_id, event.model_dump())

    async def _handle_provider_update(
        self,
        *,
        session_id: str,
        update: ProviderTranscriptUpdate,
    ) -> None:
        runtime = self._runtimes.get(session_id)
        if runtime is None:
            return

        update = self._rewrite_update_after_forced_finalize(runtime=runtime, update=update)
        if update is None:
            return

        chunk = TranscriptChunk(
            source=update.source,
            text=update.text,
            is_partial=not update.is_final,
            started_at=update.started_at,
            ended_at=update.ended_at,
            confidence=update.confidence,
        )
        if runtime.config.diarization_enabled and self.diarizer is not None:
            diarized_chunks = await self.diarizer.process([chunk])
            if diarized_chunks:
                chunk = diarized_chunks[0]
                update = ProviderTranscriptUpdate(
                    stream_id=update.stream_id,
                    source=chunk.source,
                    text=chunk.text,
                    is_final=not chunk.is_partial,
                    started_at=chunk.started_at,
                    ended_at=chunk.ended_at,
                    confidence=chunk.confidence,
                    sequence_number=update.sequence_number,
                    metadata=update.metadata,
                )
        role = role_for_chunk(chunk=chunk, capture_mode=runtime.config.capture_mode)
        turn_event = runtime.timeline.ingest(update, role=role)
        self._events[session_id].append(turn_event)
        await self.broadcaster.publish(session_id, turn_event.model_dump())

        if turn_event.is_final:
            await self._maybe_emit_coaching_events(session_id=session_id, current_turn=turn_event)

    async def _maybe_emit_coaching_events(
        self,
        *,
        session_id: str,
        current_turn: TranscriptTurnEvent,
    ) -> None:
        runtime = self._runtimes.get(session_id)
        if runtime is None or runtime.coaching_paused:
            return

        if not all([self.rule_engine, runtime.prompt_builder, runtime.llm_client, self.nudge_service]):
            return

        transcript_window = [turn.model_dump() for turn in self._coaching_window(session_id, runtime=runtime)]
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
                timestamp=current_turn.ended_at,
                priority="normal",
                source_turn_ids=[current_turn.turn_id],
            )
            self._events[session_id].append(nudge)
            await self.broadcaster.publish(session_id, nudge.model_dump())

    def _latest_turn_snapshots(self, session_id: str) -> list[TranscriptTurnEvent]:
        ordered_ids: list[str] = []
        latest_by_id: dict[str, TranscriptTurnEvent] = {}

        for event in self._events.get(session_id, []):
            if not isinstance(event, TranscriptTurnEvent):
                continue
            if event.turn_id not in latest_by_id:
                ordered_ids.append(event.turn_id)
            current = latest_by_id.get(event.turn_id)
            if current is None or event.revision > current.revision:
                latest_by_id[event.turn_id] = event

        return [latest_by_id[turn_id] for turn_id in ordered_ids]

    def _coaching_window(self, session_id: str, *, runtime: SessionRuntime) -> list[TranscriptTurnEvent]:
        turns = self._latest_turn_snapshots(session_id)
        policy = (
            runtime.config.transcription.coaching.window_policy
            if runtime.config.transcription is not None
            else "finalized_turns"
        )
        if policy == "recent_text":
            return turns[-6:]
        return [turn for turn in turns if turn.is_final][-6:]

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

    def _detect_vad(self, *, runtime: SessionRuntime, frame: AudioFrame) -> VadDecision | None:
        vad_service = self._get_vad_service(runtime=runtime, source=frame.source)
        if vad_service is None:
            return None
        return vad_service.detect(frame.pcm, sample_rate=frame.sample_rate)

    def _get_vad_service(self, *, runtime: SessionRuntime, source: str) -> VadService | None:
        transcription = runtime.config.transcription
        if transcription is None:
            return None

        vad_config = transcription.vad
        if vad_config.provider == "disabled":
            return None
        if vad_config.provider != "silero_vad":
            raise ValueError(f"Unsupported VAD provider: {vad_config.provider}")

        service = runtime.vad_services.get(source)
        if service is None:
            service = self.vad_service_factory(
                threshold=vad_config.threshold,
                min_silence_ms=vad_config.min_silence_ms,
            )
            runtime.vad_services[source] = service
        return service

    async def _maybe_finalize_turn_after_silence(
        self,
        *,
        session_id: str,
        runtime: SessionRuntime,
        frame: AudioFrame,
        vad_decision: VadDecision,
    ) -> None:
        if vad_decision.active:
            return

        current_text = runtime.timeline.open_text(frame.source)
        if not current_text:
            return
        if not runtime.segmentation_policy.should_finalize(
            current_text=current_text,
            silence_ms=vad_decision.silence_ms,
            source=frame.source,
        ):
            return

        provider_finalize = getattr(runtime.provider, "finalize_utterance", None)
        if callable(provider_finalize):
            flushed = await provider_finalize(source=frame.source)
            if flushed:
                runtime.forced_finalized_prefixes.pop(frame.source, None)
                return

        timestamp = datetime.now(timezone.utc).isoformat()
        role = role_for_chunk(
            chunk=TranscriptChunk(
                source=frame.source,
                text=current_text,
                is_partial=False,
                started_at=timestamp,
                ended_at=timestamp,
                confidence=0.0,
            ),
            capture_mode=runtime.config.capture_mode,
        )
        turn_event = runtime.timeline.finalize_open_turn(
            stream_id=frame.source,
            source=frame.source,
            role=role,
            ended_at=timestamp,
            confidence=0.0,
        )
        if turn_event is None:
            return

        runtime.forced_finalized_prefixes[frame.source] = turn_event.text
        self._events[session_id].append(turn_event)
        await self.broadcaster.publish(session_id, turn_event.model_dump())

        if turn_event.is_final:
            await self._maybe_emit_coaching_events(session_id=session_id, current_turn=turn_event)

    def _rewrite_update_after_forced_finalize(
        self,
        *,
        runtime: SessionRuntime,
        update: ProviderTranscriptUpdate,
    ) -> ProviderTranscriptUpdate | None:
        prefix = runtime.forced_finalized_prefixes.get(update.stream_id, "").strip()
        if not prefix:
            return update

        trimmed = self._trim_forced_prefix(update.text, prefix)
        if not trimmed:
            logger.info("suppressing duplicate provider update after silence finalize: %r", update.text)
            return None
        if trimmed != update.text.strip():
            runtime.forced_finalized_prefixes.pop(update.stream_id, None)
            return ProviderTranscriptUpdate(
                stream_id=update.stream_id,
                source=update.source,
                text=trimmed,
                is_final=update.is_final,
                started_at=update.started_at,
                ended_at=update.ended_at,
                confidence=update.confidence,
                sequence_number=update.sequence_number,
                metadata=update.metadata,
            )

        runtime.forced_finalized_prefixes.pop(update.stream_id, None)
        return update

    @staticmethod
    def _trim_forced_prefix(text: str, prefix: str) -> str:
        normalized_text = text.strip()
        normalized_prefix = prefix.strip()
        if not normalized_prefix:
            return normalized_text
        if normalized_text == normalized_prefix:
            return ""
        if normalized_text.startswith(normalized_prefix):
            return normalized_text[len(normalized_prefix) :].lstrip()
        return normalized_text

    @staticmethod
    def _build_vad_service(*, threshold: float, min_silence_ms: int) -> VadService:
        return SileroVadService(threshold=threshold, min_silence_ms=min_silence_ms)
