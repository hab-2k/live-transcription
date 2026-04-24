from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol

from app.contracts.session import SessionConfig

AudioSink = Callable[["AudioFrame"], Awaitable[None]]


@dataclass(slots=True)
class AudioFrame:
    source: str
    pcm: Any
    sample_rate: int


class CaptureService(Protocol):
    async def start(self, config: SessionConfig, on_audio: AudioSink) -> None:
        """Start capture for a session."""

    async def stop(self) -> None:
        """Stop capture."""
