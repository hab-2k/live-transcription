from app.services.transcription.normalizer import normalize_chunk


def test_normalize_chunk_returns_transcript_event() -> None:
    event = normalize_chunk(
        source="microphone",
        role="colleague",
        text="I can help with that",
        is_partial=False,
        started_at="2026-04-23T18:00:00Z",
        ended_at="2026-04-23T18:00:01Z",
        confidence=0.93,
    )

    assert event.type == "transcript"
