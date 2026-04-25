import sys
import threading
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest

from app.services.transcription.parakeet_unified_provider import ParakeetUnifiedProvider


class FakeToken:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeTranscriber:
    def __init__(self) -> None:
        self.finalized_tokens: list[FakeToken] = []
        self.draft_tokens: list[FakeToken] = []
        self.audio_calls: list[object] = []

    def add_audio(self, audio) -> None:
        self.audio_calls.append(audio)
        if len(self.audio_calls) == 1:
            self.draft_tokens = [FakeToken("hello")]
        elif len(self.audio_calls) == 2:
            self.finalized_tokens = [FakeToken("hello")]
            self.draft_tokens = [FakeToken("world")]


class PiecewiseTranscriber(FakeTranscriber):
    def add_audio(self, audio) -> None:
        self.audio_calls.append(audio)
        self.draft_tokens = [
            FakeToken("H"),
            FakeToken("e"),
            FakeToken("l"),
            FakeToken("l"),
            FakeToken("o"),
            FakeToken(","),
            FakeToken(" world"),
            FakeToken("!"),
        ]


class FakeStreamCtx:
    def __init__(self, transcriber: FakeTranscriber) -> None:
        self._transcriber = transcriber
        self.exited = False

    def __enter__(self) -> FakeTranscriber:
        return self._transcriber

    def __exit__(self, *args) -> None:
        self.exited = True


class FakeModel:
    def __init__(self, transcriber: FakeTranscriber) -> None:
        self._transcriber = transcriber

    def transcribe_stream(self, **kwargs) -> FakeStreamCtx:
        return FakeStreamCtx(self._transcriber)


class CyclingModel:
    def __init__(self, transcribers: list[FakeTranscriber]) -> None:
        self._transcribers = list(transcribers)
        self.stream_contexts: list[FakeStreamCtx] = []

    def transcribe_stream(self, **kwargs) -> FakeStreamCtx:
        transcriber = self._transcribers.pop(0)
        ctx = FakeStreamCtx(transcriber)
        self.stream_contexts.append(ctx)
        return ctx


def _make_provider(transcriber: FakeTranscriber, source: str = "microphone") -> ParakeetUnifiedProvider:
    model = FakeModel(transcriber)
    provider = ParakeetUnifiedProvider(
        settings=SimpleNamespace(parakeet_model_path="fake-model"),
    )
    provider._model = model
    stream_ctx = model.transcribe_stream()
    provider._stream_ctxs[source] = stream_ctx
    provider._transcribers[source] = stream_ctx.__enter__()
    return provider


class ThreadBoundTranscriber(FakeTranscriber):
    def __init__(self) -> None:
        super().__init__()
        self.owner_thread_id: int | None = None
        self.add_thread_ids: list[int] = []

    def bind_current_thread(self) -> None:
        current = threading.get_ident()
        if self.owner_thread_id is None:
            self.owner_thread_id = current
            return
        if self.owner_thread_id != current:
            raise RuntimeError(
                f"transcriber used from thread {current}, expected {self.owner_thread_id}"
            )

    def add_audio(self, audio) -> None:
        self.add_thread_ids.append(threading.get_ident())
        self.bind_current_thread()
        super().add_audio(audio)


class ThreadBoundStreamCtx(FakeStreamCtx):
    def __init__(self, transcriber: ThreadBoundTranscriber) -> None:
        super().__init__(transcriber)
        self.enter_thread_id: int | None = None
        self.exit_thread_id: int | None = None

    def __enter__(self) -> ThreadBoundTranscriber:
        self.enter_thread_id = threading.get_ident()
        self._transcriber.bind_current_thread()
        return super().__enter__()

    def __exit__(self, *args) -> None:
        self.exit_thread_id = threading.get_ident()
        self._transcriber.bind_current_thread()
        super().__exit__(*args)


class ThreadBoundModel(FakeModel):
    def __init__(self, stream_ctx: ThreadBoundStreamCtx) -> None:
        self._stream_ctx = stream_ctx

    def transcribe_stream(self, **kwargs) -> ThreadBoundStreamCtx:
        return self._stream_ctx


def _install_fake_mlx(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_mlx = ModuleType("mlx")
    fake_mlx_core = ModuleType("mlx.core")
    fake_mlx_core.array = lambda samples: samples
    fake_mlx.core = fake_mlx_core
    monkeypatch.setitem(sys.modules, "mlx", fake_mlx)
    monkeypatch.setitem(sys.modules, "mlx.core", fake_mlx_core)


@pytest.mark.asyncio
async def test_provider_keeps_parakeet_stream_on_one_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    transcriber = ThreadBoundTranscriber()
    stream_ctx = ThreadBoundStreamCtx(transcriber)
    model = ThreadBoundModel(stream_ctx)
    emitted = []

    fake_parakeet_mlx = ModuleType("parakeet_mlx")
    fake_parakeet_mlx.from_pretrained = lambda model_id: model

    monkeypatch.setitem(sys.modules, "parakeet_mlx", fake_parakeet_mlx)
    _install_fake_mlx(monkeypatch)

    provider = ParakeetUnifiedProvider(
        settings=SimpleNamespace(parakeet_model_path="fake-model"),
    )

    async def emit_update(update) -> None:
        emitted.append(update)

    await provider.start(emit_update=emit_update)
    await provider.push_audio(
        source="microphone",
        pcm=np.ones(8000, dtype=np.float32),
        sample_rate=16_000,
    )
    await provider.stop()

    # Streaming emits combined (finalized+draft) as partial; stop finalizes
    assert [update.text for update in emitted] == ["hello", "hello"]
    assert [update.is_final for update in emitted] == [False, True]
    assert transcriber.owner_thread_id is not None
    assert transcriber.add_thread_ids == [transcriber.owner_thread_id]
    assert stream_ctx.enter_thread_id == transcriber.owner_thread_id
    assert stream_ctx.exit_thread_id == transcriber.owner_thread_id


@pytest.mark.asyncio
async def test_provider_emits_combined_partial_updates(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_mlx(monkeypatch)
    transcriber = FakeTranscriber()
    provider = _make_provider(transcriber)
    emitted = []

    async def emit_update(update) -> None:
        emitted.append(update)

    provider._emit_update = emit_update

    await provider.push_audio(
        source="microphone",
        pcm=np.ones(8000, dtype=np.float32),
        sample_rate=16_000,
    )

    # First push: draft only → combined text "hello"
    assert len(emitted) == 1
    assert emitted[0].text == "hello"
    assert emitted[0].is_final is False

    await provider.push_audio(
        source="microphone",
        pcm=np.ones(8000, dtype=np.float32),
        sample_rate=16_000,
    )

    # Second push: finalized "hello" + draft "world" → combined "helloworld"
    assert len(emitted) == 2
    assert emitted[1].text == "helloworld"
    assert emitted[1].is_final is False

    await provider.stop()


@pytest.mark.asyncio
async def test_provider_concatenates_token_pieces_without_extra_spaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_mlx(monkeypatch)
    transcriber = PiecewiseTranscriber()
    provider = _make_provider(transcriber)
    emitted = []

    async def emit_update(update) -> None:
        emitted.append(update)

    provider._emit_update = emit_update

    await provider.push_audio(
        source="microphone",
        pcm=np.ones(8000, dtype=np.float32),
        sample_rate=16_000,
    )

    assert [update.text for update in emitted] == ["Hello, world!"]
    assert emitted[0].is_final is False

    await provider.stop()


@pytest.mark.asyncio
async def test_provider_finalizes_open_draft_on_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_mlx(monkeypatch)
    transcriber = FakeTranscriber()
    provider = _make_provider(transcriber)
    emitted = []

    async def emit_update(update) -> None:
        emitted.append(update)

    provider._emit_update = emit_update

    await provider.push_audio(
        source="microphone",
        pcm=np.ones(8000, dtype=np.float32),
        sample_rate=16_000,
    )
    await provider.stop()

    # Streaming emits partial "hello"; stop emits final "hello"
    assert [update.text for update in emitted] == ["hello", "hello"]
    assert [update.is_final for update in emitted] == [False, True]


@pytest.mark.asyncio
async def test_provider_finalize_utterance_rolls_stream_and_emits_final(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_mlx(monkeypatch)
    first = FakeTranscriber()
    first.draft_tokens = [FakeToken("hello")]
    second = FakeTranscriber()
    model = CyclingModel([first, second])
    provider = ParakeetUnifiedProvider(
        settings=SimpleNamespace(parakeet_model_path="fake-model"),
    )
    provider._model = model
    provider._stream_ctxs["microphone"] = model.transcribe_stream()
    provider._transcribers["microphone"] = provider._stream_ctxs["microphone"].__enter__()
    emitted = []

    async def emit_update(update) -> None:
        emitted.append(update)

    provider._emit_update = emit_update

    finalized = await provider.finalize_utterance(source="microphone")

    assert finalized is True
    assert [update.text for update in emitted] == ["hello"]
    assert [update.is_final for update in emitted] == [True]
    assert model.stream_contexts[0].exited is True
    assert provider._transcribers["microphone"] is second


@pytest.mark.asyncio
async def test_provider_buffers_small_chunks_and_flushes_on_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_mlx(monkeypatch)
    transcriber = FakeTranscriber()
    provider = _make_provider(transcriber)
    async def noop(_): pass
    provider._emit_update = noop

    # A tiny chunk should be buffered, not forwarded immediately
    await provider.push_audio(
        source="microphone",
        pcm=np.ones(100, dtype=np.float32),
        sample_rate=16_000,
    )
    assert len(transcriber.audio_calls) == 0

    # Flush happens on stop
    await provider.stop()
    assert len(transcriber.audio_calls) == 1


@pytest.mark.asyncio
async def test_provider_sends_when_buffer_threshold_reached(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_mlx(monkeypatch)
    transcriber = FakeTranscriber()
    provider = _make_provider(transcriber)
    async def noop(_): pass
    provider._emit_update = noop

    # Send enough audio to exceed the 0.5s buffer threshold (8000 samples at 16kHz)
    await provider.push_audio(
        source="microphone",
        pcm=np.ones(8000, dtype=np.float32),
        sample_rate=16_000,
    )
    assert len(transcriber.audio_calls) == 1

    await provider.stop()


@pytest.mark.asyncio
async def test_provider_isolates_mic_and_system_streams(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each source gets its own transceiver instance; audio never mixes between them."""
    _install_fake_mlx(monkeypatch)
    mic_transcriber = FakeTranscriber()
    sys_transcriber = FakeTranscriber()
    model = CyclingModel([mic_transcriber, sys_transcriber])

    fake_parakeet_mlx = ModuleType("parakeet_mlx")
    fake_parakeet_mlx.from_pretrained = lambda model_id: model

    monkeypatch.setitem(sys.modules, "parakeet_mlx", fake_parakeet_mlx)

    provider = ParakeetUnifiedProvider(
        settings=SimpleNamespace(parakeet_model_path="fake-model"),
    )
    emitted = []

    async def emit_update(update) -> None:
        emitted.append(update)

    await provider.start(emit_update=emit_update)

    # Push audio to mic source — opens mic transcriber
    await provider.push_audio(
        source="microphone",
        pcm=np.ones(8000, dtype=np.float32),
        sample_rate=16_000,
    )
    assert "microphone" in provider._transcribers
    assert len(mic_transcriber.audio_calls) == 1
    assert len(sys_transcriber.audio_calls) == 0

    # Push audio to system source — opens system transcriber
    await provider.push_audio(
        source="system",
        pcm=np.ones(8000, dtype=np.float32),
        sample_rate=16_000,
    )
    assert "system" in provider._transcribers
    assert len(mic_transcriber.audio_calls) == 1
    assert len(sys_transcriber.audio_calls) == 1

    # Verify emitted deltas are tagged with correct source
    mic_updates = [u for u in emitted if u.source == "microphone"]
    sys_updates = [u for u in emitted if u.source == "system"]
    assert len(mic_updates) == 1
    assert len(sys_updates) == 1

    # Finalize mic — system transcriber should be unaffected
    assert provider._transcribers.get("system") is not None

    # Push more audio to system — still works on its own transcriber
    await provider.push_audio(
        source="system",
        pcm=np.ones(8000, dtype=np.float32),
        sample_rate=16_000,
    )
    assert len(sys_transcriber.audio_calls) == 2
    assert len(mic_transcriber.audio_calls) == 1

    await provider.stop()
