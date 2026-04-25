from app.services.transcription.normalizer import role_for_chunk
from app.services.transcription.base import TranscriptChunk


def test_role_for_chunk_maps_dual_source_audio() -> None:
    assert (
        role_for_chunk(
            chunk=TranscriptChunk(
                source="microphone",
                text="hello",
                is_partial=False,
                started_at="2026-04-23T18:00:00Z",
                ended_at="2026-04-23T18:00:01Z",
                confidence=0.9,
            ),
            capture_mode="mic_plus_system",
        )
        == "colleague"
    )
