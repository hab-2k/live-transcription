from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable


@dataclass(slots=True)
class ProviderTranscriptUpdate:
    stream_id: str
    source: str
    text: str
    is_final: bool
    started_at: str
    ended_at: str
    confidence: float = 0.0
    sequence_number: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


UpdateSink = Callable[[ProviderTranscriptUpdate], Awaitable[None]]
