from typing import Literal

from app.contracts.events import TranscriptEvent
from app.services.transcription.base import TranscriptChunk


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
