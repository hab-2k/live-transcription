from typing import Literal

from app.contracts.events import TranscriptEvent, TranscriptTurnEvent
from app.services.transcription.base import TranscriptChunk
from app.services.transcription.provider_updates import ProviderTranscriptUpdate


def role_for_chunk(*, chunk: TranscriptChunk, capture_mode: Literal["mic_only", "mic_plus_blackhole"]) -> str:
    if capture_mode == "mic_only":
        return "shared"

    if chunk.source == "microphone":
        return "colleague"

    if chunk.source == "blackhole":
        return "customer"

    return "unknown"


def normalize_chunk(
    *,
    source: str,
    role: str,
    text: str,
    is_partial: bool,
    started_at: str,
    ended_at: str,
    confidence: float,
) -> TranscriptEvent:
    return TranscriptEvent(
        type="transcript",
        source=source,
        role=role,
        text=text,
        is_partial=is_partial,
        started_at=started_at,
        ended_at=ended_at,
        confidence=confidence,
    )


def normalize_turn_event(
    *,
    turn_id: str,
    revision: int,
    event: Literal["started", "updated", "finalized"],
    role: str,
    update: ProviderTranscriptUpdate,
    text: str | None = None,
    started_at: str | None = None,
) -> TranscriptTurnEvent:
    return TranscriptTurnEvent(
        type="transcript_turn",
        turn_id=turn_id,
        revision=revision,
        event=event,
        source=update.source,
        role=role,
        text=update.text if text is None else text,
        is_final=update.is_final,
        started_at=update.started_at if started_at is None else started_at,
        ended_at=update.ended_at,
        confidence=update.confidence,
    )
