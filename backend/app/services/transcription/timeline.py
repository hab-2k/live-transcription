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
    text: str
    started_at: str


def _merge_text(existing: str, incoming: str) -> str:
    left = existing.strip()
    right = incoming.strip()

    if not left:
        return right
    if not right:
        return left
    if right.startswith(left):
        return right
    if left.endswith(right):
        return left

    separator = "" if right[:1] in ".,!?:;" else " "
    return f"{left}{separator}{right}"


class TranscriptTimelineAssembler:
    def __init__(self) -> None:
        self._open_turns: dict[str, _OpenTurn] = {}

    def ingest(self, update: ProviderTranscriptUpdate, *, role: str) -> TranscriptTurnEvent:
        current = self._open_turns.get(update.stream_id)

        if current is None:
            current = _OpenTurn(
                turn_id=str(uuid4()),
                revision=1,
                text=update.text.strip(),
                started_at=update.started_at,
            )
            if not update.is_final:
                self._open_turns[update.stream_id] = current
            event_kind = "finalized" if update.is_final else "started"
        else:
            current.revision += 1
            current.text = _merge_text(current.text, update.text)
            event_kind = "finalized" if update.is_final else "updated"
            if update.is_final:
                self._open_turns.pop(update.stream_id, None)

        return normalize_turn_event(
            turn_id=current.turn_id,
            revision=current.revision,
            event=event_kind,
            role=role,
            update=update,
            text=current.text,
            started_at=current.started_at,
        )
