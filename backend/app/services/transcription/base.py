from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol

from app.services.transcription.provider_updates import ProviderTranscriptUpdate, UpdateSink


@dataclass(slots=True)
class TranscriptChunk:
    source: str
    text: str
    is_partial: bool
    started_at: str
    ended_at: str
    confidence: float


EventSink = Callable[[TranscriptChunk], Awaitable[None]]


class TranscriptionProvider(Protocol):
    name: str

    async def start(
        self,
        *,
        emit_update: UpdateSink | None = None,
        emit_event: EventSink | None = None,
    ) -> None:
        """Start the provider."""

    async def push_audio(self, *, source: str, pcm: Any, sample_rate: int) -> None:
        """Push an audio frame to the provider."""

    async def stop(self) -> None:
        """Stop the provider."""
