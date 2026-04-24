from app.services.transcription.base import TranscriptChunk


class NemoDiarizer:
    async def process(self, chunks: list[TranscriptChunk]) -> list[TranscriptChunk]:
        return chunks
