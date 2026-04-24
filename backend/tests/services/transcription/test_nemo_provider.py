import logging
from pathlib import Path
from types import SimpleNamespace
import sys

import numpy as np
import pytest

from app.services.transcription.nemo_provider import NemoSidecarWorkerClient, NemoStreamingProvider


class FakeWorkerClient:
    def __init__(self, transcripts: list[dict[str, object]] | None = None) -> None:
        self.start_calls = 0
        self.stop_calls = 0
        self.decode_calls = 0
        self.audio_paths: list[Path] = []
        self._transcripts = transcripts or [{"transcript": "Thanks for calling Lloyds Bank."}]

    async def start(self) -> None:
        self.start_calls += 1

    async def decode(self, *, audio_path: Path) -> dict[str, object]:
        assert audio_path.exists()
        self.decode_calls += 1
        self.audio_paths.append(audio_path)
        index = min(self.decode_calls - 1, len(self._transcripts) - 1)
        return self._transcripts[index]

    async def stop(self) -> None:
        self.stop_calls += 1


@pytest.mark.asyncio
async def test_nemo_provider_requires_configured_model_path() -> None:
    provider = NemoStreamingProvider(
        settings=SimpleNamespace(
            nemo_model_path="",
            nemo_python_executable="",
            nemo_min_audio_secs=0.01,
            nemo_decode_hop_secs=0.01,
        ),
    )

    async def emit_event(chunk) -> None:  # noqa: ANN001
        return None

    with pytest.raises(FileNotFoundError):
        await provider.start(emit_event=emit_event)


@pytest.mark.asyncio
async def test_nemo_provider_decodes_buffered_audio_into_transcript_chunks(tmp_path: Path) -> None:
    emitted = []
    model_path = tmp_path / "parakeet.nemo"
    model_path.write_text("stub")
    worker = FakeWorkerClient()

    async def emit_event(chunk) -> None:  # noqa: ANN001
        emitted.append(chunk)

    provider = NemoStreamingProvider(
        settings=SimpleNamespace(
            nemo_model_path=str(model_path),
            nemo_python_executable="",
            nemo_min_audio_secs=0.01,
            nemo_decode_hop_secs=0.01,
        ),
        worker_client_factory=lambda **_: worker,
    )

    await provider.start(emit_event=emit_event)
    await provider.push_audio(
        source="microphone",
        pcm=np.ones(320, dtype=np.float32),
        sample_rate=16_000,
    )

    assert len(emitted) == 1
    assert emitted[0].text == "Thanks for calling Lloyds Bank."
    assert emitted[0].source == "microphone"
    assert worker.start_calls == 1
    assert worker.decode_calls == 1


@pytest.mark.asyncio
async def test_nemo_provider_reuses_persistent_worker_across_multiple_decodes(tmp_path: Path) -> None:
    emitted = []
    model_path = tmp_path / "parakeet.nemo"
    model_path.write_text("stub")
    worker = FakeWorkerClient(
        transcripts=[
            {"transcript": "Thanks for calling"},
            {"transcript": "Thanks for calling Lloyds Bank"},
        ]
    )

    async def emit_event(chunk) -> None:  # noqa: ANN001
        emitted.append(chunk)

    provider = NemoStreamingProvider(
        settings=SimpleNamespace(
            nemo_model_path=str(model_path),
            nemo_python_executable="",
            nemo_min_audio_secs=0.01,
            nemo_decode_hop_secs=0.01,
        ),
        worker_client_factory=lambda **_: worker,
    )

    await provider.start(emit_event=emit_event)
    await provider.push_audio(
        source="microphone",
        pcm=np.ones(320, dtype=np.float32),
        sample_rate=16_000,
    )
    await provider.push_audio(
        source="microphone",
        pcm=np.ones(320, dtype=np.float32),
        sample_rate=16_000,
    )
    await provider.stop()

    assert [chunk.text for chunk in emitted] == ["Thanks for calling", "Lloyds Bank"]
    assert worker.start_calls == 1
    assert worker.decode_calls == 2
    assert worker.stop_calls == 1


@pytest.mark.asyncio
async def test_nemo_provider_logs_model_load_and_asr_stream_lifecycle(tmp_path: Path, caplog) -> None:  # noqa: ANN001
    emitted = []
    model_path = tmp_path / "parakeet.nemo"
    model_path.write_text("stub")
    worker = FakeWorkerClient()

    async def emit_event(chunk) -> None:  # noqa: ANN001
        emitted.append(chunk)

    caplog.set_level(logging.INFO)
    provider = NemoStreamingProvider(
        settings=SimpleNamespace(
            nemo_model_path=str(model_path),
            nemo_python_executable="",
            nemo_min_audio_secs=0.01,
            nemo_decode_hop_secs=0.01,
        ),
        worker_client_factory=lambda **_: worker,
    )

    await provider.start(emit_event=emit_event)
    await provider.push_audio(
        source="microphone",
        pcm=np.ones(320, dtype=np.float32),
        sample_rate=16_000,
    )
    await provider.stop()

    assert len(emitted) == 1
    assert "loading nemo provider" in caplog.text.lower()
    assert str(model_path) in caplog.text
    assert "persistent nemo worker started" in caplog.text.lower()
    assert "asr transcription started: source=microphone" in caplog.text.lower()
    assert "nemo decode started" in caplog.text.lower()
    assert "nemo decode completed" in caplog.text.lower()
    assert "asr transcription stopped: source=microphone" in caplog.text.lower()
    assert "persistent nemo worker stopped" in caplog.text.lower()


@pytest.mark.asyncio
async def test_nemo_sidecar_worker_client_ignores_non_json_stdout_lines(tmp_path: Path) -> None:
    audio_path = tmp_path / "sample.wav"
    audio_path.write_text("stub")
    script_path = tmp_path / "fake_nemo_worker.py"
    script_path.write_text(
        "\n".join(
            [
                "import json",
                "import sys",
                'print(\"startup noise\", flush=True)',
                'print(json.dumps({\"type\": \"ready\"}), flush=True)',
                "for line in sys.stdin:",
                "    request = json.loads(line)",
                "    if request.get('type') == 'decode':",
                '        print(\"decode noise\", flush=True)',
                '        print(json.dumps({\"type\": \"decode_result\", \"ok\": True, \"transcript\": \"hello\", \"confidence\": 0.0}), flush=True)',
                "    elif request.get('type') == 'shutdown':",
                "        break",
            ]
        )
    )

    client = NemoSidecarWorkerClient(
        model_path=tmp_path / "model.nemo",
        python_executable=sys.executable,
        script_path=script_path,
    )

    await client.start()
    result = await client.decode(audio_path=audio_path)
    await client.stop()

    assert result["transcript"] == "hello"
