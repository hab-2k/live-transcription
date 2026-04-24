from app.contracts import events as event_contracts
from app.contracts.session import SessionConfig
from app.core.config import Settings


def test_transcript_event_uses_ui_safe_shape() -> None:
    event = event_contracts.TranscriptEvent(
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


def test_transcript_turn_event_uses_stable_turn_shape() -> None:
    assert hasattr(event_contracts, "TranscriptTurnEvent")

    event = event_contracts.TranscriptTurnEvent(
        turn_id="turn-1",
        revision=2,
        event="updated",
        role="shared",
        source="microphone",
        text="thanks for calling",
        is_final=False,
        started_at="2026-04-24T08:00:00Z",
        ended_at="2026-04-24T08:00:01Z",
        confidence=0.92,
    )

    assert event.model_dump()["turn_id"] == "turn-1"


def test_session_config_accepts_nested_transcription_runtime_options() -> None:
    config = SessionConfig(
        capture_mode="mic_only",
        microphone_device_id="Built-in Microphone",
        persona="colleague_contact",
        coaching_profile="empathy",
        asr_provider="parakeet_unified",
        transcription={
            "provider": "parakeet_unified",
            "latency_preset": "balanced",
            "segmentation": {"policy": "source_turns"},
            "coaching": {"window_policy": "finalized_turns"},
            "vad": {
                "provider": "silero_vad",
                "threshold": 0.5,
                "min_silence_ms": 600,
            },
        },
    )

    payload = config.model_dump()

    assert "transcription" in payload
    assert payload["transcription"]["provider"] == "parakeet_unified"


def test_settings_expose_transcription_runtime_defaults() -> None:
    settings = Settings(_env_file=None)

    assert hasattr(settings, "transcription_latency_preset")
    assert hasattr(settings, "transcription_vad_provider")
