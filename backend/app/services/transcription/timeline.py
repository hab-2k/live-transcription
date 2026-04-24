from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from app.contracts.events import TranscriptTurnEvent
from app.services.transcription.normalizer import normalize_turn_event
from app.services.transcription.provider_updates import ProviderTranscriptUpdate


@dataclass(slots=True)
class _OpenTurn:
    turn_id: str
    revision: int


class TranscriptTimelineAssembler:
    def __init__(self) -> None:
        self._open_turns: dict[str, _OpenTurn] = {}

    def ingest(self, update: ProviderTranscriptUpdate, *, role: str) -> TranscriptTurnEvent:
        current = self._open_turns.get(update.stream_id)

        if current is None:
            current = _OpenTurn(turn_id=str(uuid4()), revision=1)
            if not update.is_final:
                self._open_turns[update.stream_id] = current
            event_kind = "finalized" if update.is_final else "started"
        else:
            current.revision += 1
            event_kind = "finalized" if update.is_final else "updated"
            if update.is_final:
                self._open_turns.pop(update.stream_id, None)

        return normalize_turn_event(
            turn_id=current.turn_id,
            revision=current.revision,
            event=event_kind,
            role=role,
            update=update,
        )
