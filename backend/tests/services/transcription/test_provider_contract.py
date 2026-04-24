import inspect

import pytest

from app.services.transcription import base as transcription_base
from tests.fakes.fake_provider import FakeProvider


def test_provider_contract_requires_normalized_provider_updates() -> None:
    assert hasattr(transcription_base, "ProviderTranscriptUpdate")

    update = transcription_base.ProviderTranscriptUpdate(
        stream_id="microphone",
        source="microphone",
        text="thanks for calling",
        is_final=True,
        started_at="2026-04-23T18:00:00Z",
        ended_at="2026-04-23T18:00:01Z",
        confidence=0.87,
    )

    assert update.stream_id == "microphone"


@pytest.mark.asyncio
async def test_fake_provider_emits_provider_updates() -> None:
    provider = FakeProvider()
    emitted = []

    async def emit_update(update) -> None:  # noqa: ANN001
        emitted.append(update)

    assert "emit_update" in inspect.signature(provider.start).parameters

    await provider.start(emit_update=emit_update)
    await provider.push_audio(source="microphone", pcm=[0.1, 0.2], sample_rate=16_000)

    assert emitted[0].stream_id == "microphone"
    assert emitted[0].is_final is True
