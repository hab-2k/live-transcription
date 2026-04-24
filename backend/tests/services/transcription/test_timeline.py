import importlib
import importlib.util

from app.services.transcription.provider_updates import ProviderTranscriptUpdate


def build_update(*, text: str, is_final: bool) -> ProviderTranscriptUpdate:
    return ProviderTranscriptUpdate(
        stream_id="microphone",
        source="microphone",
        text=text,
        is_final=is_final,
        started_at="2026-04-24T08:00:00Z",
        ended_at="2026-04-24T08:00:01Z",
        confidence=0.91,
    )


def test_timeline_revises_open_turn_until_finalized() -> None:
    assert importlib.util.find_spec("app.services.transcription.timeline") is not None

    timeline_module = importlib.import_module("app.services.transcription.timeline")
    timeline = timeline_module.TranscriptTimelineAssembler()

    started = timeline.ingest(build_update(text="Thanks", is_final=False), role="shared")
    updated = timeline.ingest(build_update(text="Thanks for calling", is_final=False), role="shared")
    finalized = timeline.ingest(build_update(text="Thanks for calling", is_final=True), role="shared")

    assert started.turn_id == updated.turn_id == finalized.turn_id
    assert [started.revision, updated.revision, finalized.revision] == [1, 2, 3]
    assert finalized.is_final is True


def test_timeline_accumulates_delta_updates_into_full_turn_text() -> None:
    timeline_module = importlib.import_module("app.services.transcription.timeline")
    timeline = timeline_module.TranscriptTimelineAssembler()

    started = timeline.ingest(build_update(text="Thanks", is_final=False), role="shared")
    finalized = timeline.ingest(build_update(text="for calling", is_final=True), role="shared")

    assert started.text == "Thanks"
    assert finalized.text == "Thanks for calling"
    assert finalized.is_final is True
