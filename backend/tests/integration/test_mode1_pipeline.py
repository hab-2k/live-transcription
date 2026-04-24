import pytest

from app.contracts.session import SessionConfig
from app.services.events.broadcaster import EventBroadcaster
from app.services.session_manager import SessionManager
from tests.fakes.fake_capture import FakeCapture
from tests.fakes.fake_provider import FakeProvider


@pytest.mark.asyncio
async def test_mode1_session_emits_shared_transcript_turns() -> None:
    manager = SessionManager(
        capture_service=FakeCapture(),
        provider=FakeProvider(),
        broadcaster=EventBroadcaster(),
    )

    session_id = await manager.start_session(
        SessionConfig(
            capture_mode="mic_only",
            microphone_device_id="Built-in Microphone",
            persona="colleague_contact",
            coaching_profile="empathy",
            asr_provider="nemo",
        )
    )

    events = manager.list_events(session_id)

    assert any(event.type == "transcript_turn" and event.role == "shared" for event in events)
    assert not any(event.type == "transcript" for event in events)
