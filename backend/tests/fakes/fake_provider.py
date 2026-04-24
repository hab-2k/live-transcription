from app.services.transcription.base import TranscriptChunk


class FakeProvider:
    name = "fake"

    def __init__(self) -> None:
        self.started = False
        self.stopped = False
        self._emit_event = None

    async def start(self, *, emit_event) -> None:  # noqa: ANN001
        self.started = True
        self._emit_event = emit_event

    async def push_audio(self, *, source: str, pcm, sample_rate: int) -> None:  # noqa: ANN001
        assert self._emit_event is not None
        await self._emit_event(
            TranscriptChunk(
                source=source,
                text="Thanks for calling Lloyds Bank.",
                is_partial=False,
                started_at="2026-04-23T18:00:00Z",
                ended_at="2026-04-23T18:00:01Z",
                confidence=0.92,
            )
        )

    async def stop(self) -> None:
        self.stopped = True
