from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol

from app.contracts.session import SessionConfig, SystemAudioSelection

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


class SystemAudioProvider(Protocol):
    def get_status(self) -> Any:
        """Return provider readiness and permission state."""

    def request_permission(self) -> Any:
        """Prompt for permission when the provider supports it."""

    def list_targets(self) -> list[Any]:
        """Return user-selectable system audio targets."""

    async def start(
        self,
        *,
        selection: SystemAudioSelection,
        sample_rate: int,
        on_audio: AudioSink,
    ) -> None:
        """Start system audio capture."""

    async def stop(self) -> None:
        """Stop system audio capture."""
