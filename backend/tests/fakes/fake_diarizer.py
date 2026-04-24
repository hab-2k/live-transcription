from app.services.transcription.base import TranscriptChunk


class FakeDiarizer:
    def __init__(self) -> None:
        self.was_called = False

    async def process(self, chunks: list[TranscriptChunk]) -> list[TranscriptChunk]:
        self.was_called = True
        return chunks
