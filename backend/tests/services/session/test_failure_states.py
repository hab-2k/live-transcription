from pathlib import Path

import pytest

from app.contracts.session import SessionConfig
from app.services.coaching.nudge_service import NudgeService
from app.services.coaching.prompt_builder import PromptBuilder
from app.services.coaching.rule_engine import RuleEngine
from app.services.events.broadcaster import EventBroadcaster
from app.services.session_manager import SessionManager
from tests.fakes.fake_capture import FakeCapture
from tests.fakes.fake_provider import FakeProvider


class FailingLLMClient:
    async def complete(self, *, prompt: str) -> dict[str, str]:
        raise RuntimeError("endpoint unavailable")


@pytest.mark.asyncio
async def test_llm_failure_keeps_transcription_running() -> None:
    manager = SessionManager(
        capture_service=FakeCapture(),
        provider=FakeProvider(),
        broadcaster=EventBroadcaster(),
        rule_engine=RuleEngine.from_file(Path("backend/config/rules/default.yaml")),
        prompt_builder=PromptBuilder.from_file(Path("backend/config/personas/colleague_contact.yaml")),
        llm_client=FailingLLMClient(),
        nudge_service=NudgeService(),
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

    assert any(event.type == "transcript_turn" for event in events)
    assert not any(event.type == "transcript" for event in events)
    assert any(event.type == "session_status" and event.status == "coaching_unavailable" for event in events)
