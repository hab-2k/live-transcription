from app.services.audio.base import AudioFrame


class FakeCapture:
    def __init__(self, frames: list[AudioFrame] | None = None) -> None:
        self.frames = (
            frames
            if frames is not None
            else [AudioFrame(source="microphone", pcm=[0.1, 0.2], sample_rate=16_000)]
        )
        self.started = False
        self.stopped = False

    async def start(self, config, on_audio) -> None:  # noqa: ANN001
        self.started = True
        for frame in self.frames:
            await on_audio(frame)

    async def stop(self) -> None:
        self.stopped = True
