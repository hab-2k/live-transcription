from pathlib import Path

import numpy as np
import pytest

from app.contracts.session import SessionConfig, TranscriptionConfig
from app.services.audio.base import AudioFrame
from app.services.coaching.nudge_service import NudgeService
from app.services.coaching.rule_engine import RuleEngine
from app.services.events.broadcaster import EventBroadcaster
from app.services.session_manager import SessionManager
from app.services.transcription.provider_updates import ProviderTranscriptUpdate
from tests.fakes.fake_capture import FakeCapture
from tests.fakes.fake_provider import FakeProvider


class StubPromptBuilder:
    def __init__(self, persona_name: str) -> None:
        self.persona_name = persona_name

    def build(self, transcript: list[dict[str, object]], flags: list[dict[str, object]]) -> str:
        return f"persona:{self.persona_name} turns:{len(transcript)} flags:{len(flags)}"


class RecordingLLMClient:
    def __init__(self, *, base_url: str, model: str) -> None:
        self.base_url = base_url
        self.model = model
        self.prompts: list[str] = []

    async def complete(self, *, prompt: str) -> dict[str, str]:
        self.prompts.append(prompt)
        return {"message": f"Use {self.model} from {self.base_url}"}


class UpdatingProvider:
    name = "fake_updates"

    def __init__(self) -> None:
        self._emit_update = None
        self.start_calls = 0
        self.stop_calls = 0
        self.push_calls = 0

    async def start(self, *, emit_update=None, emit_event=None) -> None:  # noqa: ANN001
        self.start_calls += 1
        self._emit_update = emit_update

    async def push_audio(self, *, source: str, pcm, sample_rate: int) -> None:  # noqa: ANN001
        assert self._emit_update is not None
        payloads = [
            ProviderTranscriptUpdate(
                stream_id=source,
                source=source,
                text="Thanks",
                is_final=False,
                started_at="2026-04-24T08:00:00Z",
                ended_at="2026-04-24T08:00:00Z",
                confidence=0.9,
            ),
            ProviderTranscriptUpdate(
                stream_id=source,
                source=source,
                text="Thanks for calling",
                is_final=True,
                started_at="2026-04-24T08:00:00Z",
                ended_at="2026-04-24T08:00:01Z",
                confidence=0.92,
            ),
        ]
        payload = payloads[min(self.push_calls, len(payloads) - 1)]
        self.push_calls += 1
        await self._emit_update(payload)

    async def stop(self) -> None:
        self.stop_calls += 1


class NamedProvider:
    def __init__(self, name: str) -> None:
        self.name = name
        self.start_calls = 0
        self.stop_calls = 0

    async def start(self, *, emit_update=None, emit_event=None) -> None:  # noqa: ANN001
        self.start_calls += 1

    async def push_audio(self, *, source: str, pcm, sample_rate: int) -> None:  # noqa: ANN001
        return None

    async def stop(self) -> None:
        self.stop_calls += 1


class DeltaUpdatingProvider:
    name = "fake_delta_updates"

    def __init__(self) -> None:
        self._emit_update = None
        self.push_calls = 0

    async def start(self, *, emit_update=None, emit_event=None) -> None:  # noqa: ANN001
        self._emit_update = emit_update

    async def push_audio(self, *, source: str, pcm, sample_rate: int) -> None:  # noqa: ANN001
        assert self._emit_update is not None
        payloads = [
            ProviderTranscriptUpdate(
                stream_id=source,
                source=source,
                text="Thanks",
                is_final=False,
                started_at="2026-04-24T08:00:00Z",
                ended_at="2026-04-24T08:00:00Z",
                confidence=0.9,
            ),
            ProviderTranscriptUpdate(
                stream_id=source,
                source=source,
                text="for calling",
                is_final=True,
                started_at="2026-04-24T08:00:00Z",
                ended_at="2026-04-24T08:00:01Z",
                confidence=0.92,
            ),
        ]
        payload = payloads[min(self.push_calls, len(payloads) - 1)]
        self.push_calls += 1
        await self._emit_update(payload)

    async def stop(self) -> None:
        return None


class RecordingProvider:
    name = "recording"

    def __init__(self) -> None:
        self.push_calls: list[tuple[str, np.ndarray, int]] = []

    async def start(self, *, emit_update=None, emit_event=None) -> None:  # noqa: ANN001
        return None

    async def push_audio(self, *, source: str, pcm, sample_rate: int) -> None:  # noqa: ANN001
        self.push_calls.append((source, np.asarray(pcm, dtype=np.float32), sample_rate))

    async def stop(self) -> None:
        return None


class PartialOnlyProvider:
    name = "partial_only"

    def __init__(self) -> None:
        self._emit_update = None
        self.push_calls = 0

    async def start(self, *, emit_update=None, emit_event=None) -> None:  # noqa: ANN001
        self._emit_update = emit_update

    async def push_audio(self, *, source: str, pcm, sample_rate: int) -> None:  # noqa: ANN001
        self.push_calls += 1
        assert self._emit_update is not None
        await self._emit_update(
            ProviderTranscriptUpdate(
                stream_id=source,
                source=source,
                text="Hello there",
                is_final=False,
                started_at="2026-04-24T08:00:00Z",
                ended_at="2026-04-24T08:00:00Z",
                confidence=0.9,
            )
        )

    async def stop(self) -> None:
        return None


class FlushablePartialProvider(PartialOnlyProvider):
    def __init__(self) -> None:
        super().__init__()
        self.finalize_calls = 0

    async def finalize_utterance(self, *, source: str) -> bool:
        self.finalize_calls += 1
        assert self._emit_update is not None
        await self._emit_update(
            ProviderTranscriptUpdate(
                stream_id=source,
                source=source,
                text="Hello there",
                is_final=True,
                started_at="2026-04-24T08:00:00Z",
                ended_at="2026-04-24T08:00:01Z",
                confidence=0.95,
            )
        )
        return True


class FakeVadService:
    def __init__(self, decisions: list[tuple[bool, float, int]]) -> None:
        self._decisions = decisions
        self._index = 0

    def detect(self, frame: np.ndarray, *, sample_rate: int):  # noqa: ANN001, ARG002
        active, speech_confidence, silence_ms = self._decisions[min(self._index, len(self._decisions) - 1)]
        self._index += 1
        from app.services.transcription.vad import VadDecision

        return VadDecision(
            active=active,
            speech_confidence=speech_confidence,
            silence_ms=silence_ms,
        )


@pytest.mark.asyncio
async def test_session_uses_selected_persona_and_llm_runtime() -> None:
    personas: list[str] = []
    llm_clients: list[RecordingLLMClient] = []

    def prompt_builder_factory(persona: str) -> StubPromptBuilder:
        personas.append(persona)
        return StubPromptBuilder(persona)

    def llm_client_factory(config: SessionConfig) -> RecordingLLMClient:
        client = RecordingLLMClient(
            base_url=config.llm_base_url or "",
            model=config.llm_model or "",
        )
        llm_clients.append(client)
        return client

    manager = SessionManager(
        capture_service=FakeCapture(),
        provider=FakeProvider(),
        broadcaster=EventBroadcaster(),
        rule_engine=RuleEngine.from_file(Path("backend/config/rules/default.yaml")),
        prompt_builder_factory=prompt_builder_factory,
        llm_client_factory=llm_client_factory,
        nudge_service=NudgeService(),
    )

    session_id = await manager.start_session(
        SessionConfig(
            capture_mode="mic_only",
            microphone_device_id="Built-in Microphone",
            persona="manager",
            coaching_profile="empathy",
            asr_provider="nemo",
            llm_base_url="http://localhost:1234/v1",
            llm_model="manager-model",
        )
    )

    events = manager.list_events(session_id)

    assert personas == ["manager"]
    assert [(client.base_url, client.model) for client in llm_clients] == [
        ("http://localhost:1234/v1", "manager-model")
    ]
    assert llm_clients[0].prompts == ["persona:manager turns:1 flags:0"]
    assert any(event.type == "coaching_nudge" for event in events)


@pytest.mark.asyncio
async def test_paused_coaching_keeps_transcription_running_until_resumed() -> None:
    manager = SessionManager(
        capture_service=FakeCapture(frames=[]),
        provider=FakeProvider(),
        broadcaster=EventBroadcaster(),
        rule_engine=RuleEngine.from_file(Path("backend/config/rules/default.yaml")),
        prompt_builder_factory=lambda persona: StubPromptBuilder(persona),
        llm_client_factory=lambda config: RecordingLLMClient(
            base_url=config.llm_base_url or "http://localhost:11434/v1",
            model=config.llm_model or "local-model",
        ),
        nudge_service=NudgeService(),
    )

    session_id = await manager.start_session(
        SessionConfig(
            capture_mode="mic_only",
            microphone_device_id="Built-in Microphone",
            persona="colleague_contact",
            coaching_profile="empathy",
            asr_provider="nemo",
            llm_base_url="http://localhost:11434/v1",
            llm_model="local-model",
        )
    )

    await manager.set_coaching_paused(session_id, paused=True)
    await manager.provider.push_audio(source="microphone", pcm=[0.2, 0.1], sample_rate=16_000)

    paused_events = manager.list_events(session_id)

    assert any(event.type == "transcript_turn" for event in paused_events)
    assert not any(event.type == "transcript" for event in paused_events)
    assert any(event.type == "session_status" and event.status == "coaching_paused" for event in paused_events)
    assert not any(event.type == "coaching_nudge" for event in paused_events)

    await manager.set_coaching_paused(session_id, paused=False)
    await manager.provider.push_audio(source="microphone", pcm=[0.2, 0.1], sample_rate=16_000)

    resumed_events = manager.list_events(session_id)

    assert any(event.type == "session_status" and event.status == "coaching_resumed" for event in resumed_events)
    assert any(event.type == "coaching_nudge" for event in resumed_events)


@pytest.mark.asyncio
async def test_session_manager_broadcasts_turn_updates_and_finalized_turns() -> None:
    manager = SessionManager(
        capture_service=FakeCapture(frames=[]),
        provider=UpdatingProvider(),
        broadcaster=EventBroadcaster(),
    )

    session_id = await manager.start_session(
        SessionConfig(
            capture_mode="mic_only",
            microphone_device_id="Built-in Microphone",
            persona="colleague_contact",
            coaching_profile="empathy",
            asr_provider="parakeet_unified",
        )
    )

    await manager.provider.push_audio(source="microphone", pcm=[0.2, 0.1], sample_rate=16_000)
    await manager.provider.push_audio(source="microphone", pcm=[0.2, 0.1], sample_rate=16_000)

    events = manager.list_events(session_id)

    assert any(event.type == "transcript_turn" and event.event == "started" for event in events)
    assert any(event.type == "transcript_turn" and event.event == "finalized" for event in events)


@pytest.mark.asyncio
async def test_session_manager_rebuilds_provider_when_transcription_provider_changes() -> None:
    providers = {
        "parakeet_unified": NamedProvider("parakeet_unified"),
        "nemo": NamedProvider("nemo"),
    }
    manager = SessionManager(
        capture_service=FakeCapture(frames=[]),
        provider_factory=lambda provider_name, model="": providers[provider_name],
        broadcaster=EventBroadcaster(),
    )

    session_id = await manager.start_session(
        SessionConfig(
            capture_mode="mic_only",
            microphone_device_id="Built-in Microphone",
            persona="colleague_contact",
            coaching_profile="empathy",
            asr_provider="nemo",
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
    )

    status = await manager.set_transcription_config(
        session_id,
        TranscriptionConfig(
            provider="nemo",
            latency_preset="balanced",
            segmentation={"policy": "source_turns"},
            coaching={"window_policy": "finalized_turns"},
            vad={
                "provider": "silero_vad",
                "threshold": 0.5,
                "min_silence_ms": 600,
            },
        ),
    )

    assert providers["parakeet_unified"].start_calls == 1
    assert providers["parakeet_unified"].stop_calls == 1
    assert providers["nemo"].start_calls == 1
    assert status == "transcription_reconfigured"


@pytest.mark.asyncio
async def test_session_manager_accumulates_delta_provider_updates_into_one_turn() -> None:
    manager = SessionManager(
        capture_service=FakeCapture(frames=[]),
        provider=DeltaUpdatingProvider(),
        broadcaster=EventBroadcaster(),
    )

    session_id = await manager.start_session(
        SessionConfig(
            capture_mode="mic_only",
            microphone_device_id="Built-in Microphone",
            persona="colleague_contact",
            coaching_profile="empathy",
            asr_provider="parakeet_unified",
        )
    )

    await manager.provider.push_audio(source="microphone", pcm=[0.2, 0.1], sample_rate=16_000)
    await manager.provider.push_audio(source="microphone", pcm=[0.2, 0.1], sample_rate=16_000)

    events = [
        event for event in manager.list_events(session_id) if getattr(event, "type", None) == "transcript_turn"
    ]

    assert events[-1].text == "Thanks for calling"
    assert events[-1].is_final is True


@pytest.mark.asyncio
async def test_session_manager_uses_vad_to_gate_audio_before_provider() -> None:
    provider = RecordingProvider()
    manager = SessionManager(
        capture_service=FakeCapture(
            frames=[
                AudioFrame(source="microphone", pcm=np.zeros(1024, dtype=np.float32), sample_rate=16_000),
                AudioFrame(source="microphone", pcm=np.ones(1024, dtype=np.float32), sample_rate=16_000),
            ]
        ),
        provider=provider,
        broadcaster=EventBroadcaster(),
        vad_service_factory=lambda **_: FakeVadService(
            [
                (False, 0.05, 700),
                (True, 0.95, 0),
            ]
        ),
    )

    await manager.start_session(
        SessionConfig(
            capture_mode="mic_only",
            microphone_device_id="Built-in Microphone",
            persona="colleague_contact",
            coaching_profile="empathy",
            asr_provider="parakeet_unified",
            transcription=TranscriptionConfig(
                provider="parakeet_unified",
                model="mlx-community/parakeet-tdt-0.6b-v2",
                latency_preset="balanced",
                segmentation={"policy": "fixed_lines"},
                coaching={"window_policy": "finalized_turns"},
                vad={
                    "provider": "silero_vad",
                    "threshold": 0.5,
                    "min_silence_ms": 600,
                },
            ),
        )
    )

    assert len(provider.push_calls) == 1
    assert provider.push_calls[0][0] == "microphone"
    assert provider.push_calls[0][2] == 16_000


@pytest.mark.asyncio
async def test_session_manager_force_finalizes_open_turn_after_silence() -> None:
    provider = PartialOnlyProvider()
    manager = SessionManager(
        capture_service=FakeCapture(
            frames=[
                AudioFrame(source="microphone", pcm=np.ones(1024, dtype=np.float32), sample_rate=16_000),
                AudioFrame(source="microphone", pcm=np.zeros(1024, dtype=np.float32), sample_rate=16_000),
            ]
        ),
        provider=provider,
        broadcaster=EventBroadcaster(),
        vad_service_factory=lambda **_: FakeVadService(
            [
                (True, 0.95, 0),
                (False, 0.05, 700),
            ]
        ),
    )

    session_id = await manager.start_session(
        SessionConfig(
            capture_mode="mic_only",
            microphone_device_id="Built-in Microphone",
            persona="colleague_contact",
            coaching_profile="empathy",
            asr_provider="parakeet_unified",
            transcription=TranscriptionConfig(
                provider="parakeet_unified",
                model="mlx-community/parakeet-tdt-0.6b-v2",
                latency_preset="balanced",
                segmentation={"policy": "fixed_lines"},
                coaching={"window_policy": "finalized_turns"},
                vad={
                    "provider": "silero_vad",
                    "threshold": 0.5,
                    "min_silence_ms": 600,
                },
            ),
        )
    )

    events = [
        event for event in manager.list_events(session_id) if getattr(event, "type", None) == "transcript_turn"
    ]

    assert [event.event for event in events] == ["started", "finalized"]
    assert [event.text for event in events] == ["Hello there", "Hello there"]
    assert [event.is_final for event in events] == [False, True]


@pytest.mark.asyncio
async def test_session_manager_does_not_finalize_while_vad_is_still_active() -> None:
    provider = PartialOnlyProvider()
    manager = SessionManager(
        capture_service=FakeCapture(
            frames=[
                AudioFrame(source="microphone", pcm=np.ones(1024, dtype=np.float32), sample_rate=16_000),
                AudioFrame(source="microphone", pcm=np.zeros(1024, dtype=np.float32), sample_rate=16_000),
            ]
        ),
        provider=provider,
        broadcaster=EventBroadcaster(),
        vad_service_factory=lambda **_: FakeVadService(
            [
                (True, 0.95, 0),
                (True, 0.05, 700),
            ]
        ),
    )

    session_id = await manager.start_session(
        SessionConfig(
            capture_mode="mic_only",
            microphone_device_id="Built-in Microphone",
            persona="colleague_contact",
            coaching_profile="empathy",
            asr_provider="parakeet_unified",
            transcription=TranscriptionConfig(
                provider="parakeet_unified",
                model="mlx-community/parakeet-tdt-0.6b-v2",
                latency_preset="balanced",
                segmentation={"policy": "fixed_lines"},
                coaching={"window_policy": "finalized_turns"},
                vad={
                    "provider": "silero_vad",
                    "threshold": 0.5,
                    "min_silence_ms": 700,
                },
            ),
        )
    )

    events = [
        event for event in manager.list_events(session_id) if getattr(event, "type", None) == "transcript_turn"
    ]

    assert [event.event for event in events] == ["started", "updated"]
    assert all(event.is_final is False for event in events)


@pytest.mark.asyncio
async def test_session_manager_uses_provider_utterance_finalize_when_available() -> None:
    provider = FlushablePartialProvider()
    manager = SessionManager(
        capture_service=FakeCapture(
            frames=[
                AudioFrame(source="microphone", pcm=np.ones(1024, dtype=np.float32), sample_rate=16_000),
                AudioFrame(source="microphone", pcm=np.zeros(1024, dtype=np.float32), sample_rate=16_000),
            ]
        ),
        provider=provider,
        broadcaster=EventBroadcaster(),
        vad_service_factory=lambda **_: FakeVadService(
            [
                (True, 0.95, 0),
                (False, 0.05, 700),
            ]
        ),
    )

    session_id = await manager.start_session(
        SessionConfig(
            capture_mode="mic_only",
            microphone_device_id="Built-in Microphone",
            persona="colleague_contact",
            coaching_profile="empathy",
            asr_provider="parakeet_unified",
            transcription=TranscriptionConfig(
                provider="parakeet_unified",
                model="mlx-community/parakeet-tdt-0.6b-v2",
                latency_preset="balanced",
                segmentation={"policy": "fixed_lines"},
                coaching={"window_policy": "finalized_turns"},
                vad={
                    "provider": "silero_vad",
                    "threshold": 0.5,
                    "min_silence_ms": 600,
                },
            ),
        )
    )

    events = [
        event for event in manager.list_events(session_id) if getattr(event, "type", None) == "transcript_turn"
    ]

    assert provider.finalize_calls == 1
    assert [event.event for event in events] == ["started", "finalized"]
    assert [event.text for event in events] == ["Hello there", "Hello there"]
    assert [event.is_final for event in events] == [False, True]
