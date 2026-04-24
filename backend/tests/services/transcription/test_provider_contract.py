from app.services.transcription.base import TranscriptChunk


def test_provider_contract_requires_normalized_chunks() -> None:
    chunk = TranscriptChunk(
        source="microphone",
        text="thanks for calling",
        is_partial=True,
        started_at="2026-04-23T18:00:00Z",
        ended_at="2026-04-23T18:00:01Z",
        confidence=0.87,
    )

    assert chunk.source == "microphone"
