import pytest

from app.contracts.session import SessionConfig
from app.services.events.broadcaster import EventBroadcaster
from app.services.session_manager import SessionManager
from tests.fakes.fake_capture import FakeCapture
from tests.fakes.fake_diarizer import FakeDiarizer
from tests.fakes.fake_provider import FakeProvider


@pytest.mark.asyncio
async def test_diarization_toggle_uses_configured_diarizer() -> None:
    fake_diarizer = FakeDiarizer()
    manager = SessionManager(
        capture_service=FakeCapture(),
        provider=FakeProvider(),
        broadcaster=EventBroadcaster(),
        diarizer=fake_diarizer,
    )

    await manager.start_session(
        SessionConfig(
            capture_mode="mic_only",
            microphone_device_id="Built-in Microphone",
            persona="colleague_contact",
            coaching_profile="empathy",
            asr_provider="nemo",
            diarization_enabled=True,
        )
    )

    assert fake_diarizer.was_called is True
