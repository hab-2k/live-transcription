import pytest

from app.contracts.session import SessionConfig, TranscriptionConfig
from app.services.events.broadcaster import EventBroadcaster
from app.services.session_manager import SessionManager
from app.services.transcription.provider_updates import ProviderTranscriptUpdate
from tests.fakes.fake_capture import FakeCapture


class EmittingProvider:
    def __init__(self, name: str, text: str) -> None:
        self.name = name
        self.text = text
        self.start_calls = 0
        self.stop_calls = 0
        self._emit_update = None

    async def start(self, *, emit_update=None, emit_event=None) -> None:  # noqa: ANN001
        self.start_calls += 1
        self._emit_update = emit_update

    async def push_audio(self, *, source: str, pcm, sample_rate: int) -> None:  # noqa: ANN001
        assert self._emit_update is not None
        await self._emit_update(
            ProviderTranscriptUpdate(
                stream_id=source,
                source=source,
                text=self.text,
                is_final=True,
                started_at="2026-04-24T08:00:00Z",
                ended_at="2026-04-24T08:00:01Z",
                confidence=0.9,
            )
        )

    async def stop(self) -> None:
        self.stop_calls += 1


@pytest.mark.asyncio
async def test_reconfiguring_transcription_preserves_finalized_turns_and_restarts_provider() -> None:
    providers = {
        "parakeet_unified": EmittingProvider("parakeet_unified", "Thanks for calling."),
        "nemo": EmittingProvider("nemo", "I can take the next step."),
    }
    manager = SessionManager(
        capture_service=FakeCapture(frames=[]),
        provider_factory=lambda provider_name: providers[provider_name],
        broadcaster=EventBroadcaster(),
    )

    session_id = await manager.start_session(
        SessionConfig(
            capture_mode="mic_only",
            microphone_device_id="Built-in Microphone",
            persona="colleague_contact",
            coaching_profile="empathy",
            asr_provider="parakeet_unified",
            transcription={
                "provider": "parakeet_unified",
                "latency_preset": "balanced",
                "segmentation": {"policy": "fixed_lines"},
                "coaching": {"window_policy": "finalized_turns"},
                "vad": {
                    "provider": "silero_vad",
                    "threshold": 0.5,
                    "min_silence_ms": 700,
                },
            },
        )
    )

    await providers["parakeet_unified"].push_audio(
        source="microphone",
        pcm=[0.1, 0.2],
        sample_rate=16_000,
    )
    await manager.set_transcription_config(
        session_id,
        TranscriptionConfig(
            provider="nemo",
            latency_preset="balanced",
            segmentation={"policy": "source_turns"},
            coaching={"window_policy": "finalized_turns"},
            vad={
                "provider": "silero_vad",
                "threshold": 0.55,
                "min_silence_ms": 600,
            },
        ),
    )
    await providers["nemo"].push_audio(
        source="microphone",
        pcm=[0.1, 0.2],
        sample_rate=16_000,
    )

    events = manager.list_events(session_id)
    transcript_turns = [event for event in events if event.type == "transcript_turn"]

    assert [turn.text for turn in transcript_turns if turn.is_final] == [
        "Thanks for calling.",
        "I can take the next step.",
    ]
    assert any(event.type == "session_status" and event.status == "transcription_reconfigured" for event in events)
    assert providers["parakeet_unified"].stop_calls == 1
    assert providers["nemo"].start_calls == 1
