from pathlib import Path

import pytest

from app.contracts.session import SessionConfig
from app.services.audio.base import AudioFrame
from app.services.coaching.llm_client import OpenAICompatibleClient
from app.services.coaching.nudge_service import NudgeService
from app.services.coaching.prompt_builder import PromptBuilder
from app.services.coaching.rule_engine import RuleEngine
from app.services.events.broadcaster import EventBroadcaster
from app.services.session_manager import SessionManager
from tests.fakes.fake_capture import FakeCapture
from tests.fakes.fake_provider import FakeProvider


class StubLLMClient(OpenAICompatibleClient):
    def __init__(self) -> None:
        pass

    async def complete(self, *, prompt: str) -> dict[str, str]:
        return {"message": "Lead with reassurance."}


@pytest.mark.asyncio
async def test_recent_transcript_window_produces_one_live_nudge() -> None:
    manager = SessionManager(
        capture_service=FakeCapture(
            frames=[
                AudioFrame(source="microphone", pcm=[0.1, 0.2], sample_rate=16_000),
                AudioFrame(source="microphone", pcm=[0.1, 0.2], sample_rate=16_000),
                AudioFrame(source="microphone", pcm=[0.1, 0.2], sample_rate=16_000),
            ]
        ),
        provider=FakeProvider(),
        broadcaster=EventBroadcaster(),
        rule_engine=RuleEngine.from_file(Path("backend/config/rules/default.yaml")),
        prompt_builder=PromptBuilder.from_file(Path("backend/config/personas/colleague_contact.yaml")),
        llm_client=StubLLMClient(),
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

    assert any(event.type == "coaching_nudge" for event in events)
