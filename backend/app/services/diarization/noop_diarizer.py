from app.services.transcription.base import TranscriptChunk


class NoopDiarizer:
    async def process(self, chunks: list[TranscriptChunk]) -> list[TranscriptChunk]:
        return chunks
