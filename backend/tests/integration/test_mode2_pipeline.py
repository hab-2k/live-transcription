import pytest

from app.contracts.session import SessionConfig
from app.services.audio.base import AudioFrame
from app.services.events.broadcaster import EventBroadcaster
from app.services.session_manager import SessionManager
from tests.fakes.fake_capture import FakeCapture
from tests.fakes.fake_provider import FakeProvider


@pytest.mark.asyncio
async def test_mode2_maps_microphone_to_colleague_and_blackhole_to_customer() -> None:
    manager = SessionManager(
        capture_service=FakeCapture(
            frames=[
                AudioFrame(source="microphone", pcm=[0.1], sample_rate=16_000),
                AudioFrame(source="blackhole", pcm=[0.2], sample_rate=16_000),
            ]
        ),
        provider=FakeProvider(),
        broadcaster=EventBroadcaster(),
    )

    session_id = await manager.start_session(
        SessionConfig(
            capture_mode="mic_plus_blackhole",
            microphone_device_id="Built-in Microphone",
            persona="colleague_contact",
            coaching_profile="empathy",
            asr_provider="nemo",
        )
    )

    events = manager.list_events(session_id)

    assert [event.role for event in events[:2]] == ["colleague", "customer"]
