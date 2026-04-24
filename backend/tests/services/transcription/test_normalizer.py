from app.services.transcription import normalizer
from app.services.transcription.provider_updates import ProviderTranscriptUpdate


def test_normalize_chunk_returns_transcript_event() -> None:
    event = normalizer.normalize_chunk(
        source="microphone",
        role="colleague",
        text="I can help with that",
        is_partial=False,
        started_at="2026-04-23T18:00:00Z",
        ended_at="2026-04-23T18:00:01Z",
        confidence=0.93,
    )

    assert event.type == "transcript"


def test_normalize_turn_event_returns_transcript_turn_event() -> None:
    assert hasattr(normalizer, "normalize_turn_event")

    update = ProviderTranscriptUpdate(
        stream_id="microphone",
        source="microphone",
        text="I can help with that",
        is_final=False,
        started_at="2026-04-23T18:00:00Z",
        ended_at="2026-04-23T18:00:01Z",
        confidence=0.93,
    )

    event = normalizer.normalize_turn_event(
        turn_id="turn-1",
        revision=2,
        event="updated",
        role="colleague",
        update=update,
    )

    assert event.type == "transcript_turn"
