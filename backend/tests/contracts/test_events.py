from app.contracts.events import TranscriptEvent


def test_transcript_event_uses_ui_safe_shape() -> None:
    event = TranscriptEvent(
        type="transcript",
        role="shared",
        source="microphone",
        text="hello",
        is_partial=False,
        started_at="2026-04-23T18:00:00Z",
        ended_at="2026-04-23T18:00:01Z",
        confidence=0.91,
    )

    assert event.model_dump()["role"] == "shared"
