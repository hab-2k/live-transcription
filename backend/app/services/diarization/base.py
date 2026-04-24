from typing import Protocol

from app.services.transcription.base import TranscriptChunk


class Diarizer(Protocol):
    async def process(self, chunks: list[TranscriptChunk]) -> list[TranscriptChunk]:
        """Optionally relabel or split chunks."""
