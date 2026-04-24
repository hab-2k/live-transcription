import importlib
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest


@pytest.mark.asyncio
async def test_parakeet_unified_worker_client_ignores_non_json_stdout_lines(tmp_path: Path) -> None:
    assert importlib.util.find_spec("app.services.transcription.parakeet_unified_provider") is not None
    assert Path("backend/scripts/parakeet_unified_streaming_worker.py").is_file()

    provider_module = importlib.import_module("app.services.transcription.parakeet_unified_provider")

    audio_path = tmp_path / "sample.wav"
    audio_path.write_text("stub")
    script_path = tmp_path / "fake_parakeet_worker.py"
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

    client = provider_module.ParakeetUnifiedWorkerClient(
        model_path=tmp_path / "model.nemo",
        python_executable=sys.executable,
        script_path=script_path,
    )

    await client.start()
    result = await client.decode(audio_path=audio_path)
    await client.stop()

    assert result["transcript"] == "hello"


class FakeWorkerClient:
    def __init__(self, transcripts: list[dict[str, object]] | None = None) -> None:
        self.start_calls = 0
        self.stop_calls = 0
        self.decode_calls = 0
        self._transcripts = transcripts or [{"transcript": "Thanks for calling Lloyds Bank.", "confidence": 0.92}]

    async def start(self) -> None:
        self.start_calls += 1

    async def decode(self, *, audio_path: Path) -> dict[str, object]:
        assert audio_path.exists()
        result = self._transcripts[min(self.decode_calls, len(self._transcripts) - 1)]
        self.decode_calls += 1
        return result

    async def stop(self) -> None:
        self.stop_calls += 1


@pytest.mark.asyncio
async def test_parakeet_unified_provider_emits_provider_updates(tmp_path: Path) -> None:
    provider_module = importlib.import_module("app.services.transcription.parakeet_unified_provider")
    emitted = []
    model_path = tmp_path / "parakeet-unified.nemo"
    model_path.write_text("stub")
    worker = FakeWorkerClient()

    async def emit_update(update) -> None:  # noqa: ANN001
        emitted.append(update)

    provider = provider_module.ParakeetUnifiedProvider(
        settings=SimpleNamespace(
            parakeet_model_path=str(model_path),
            parakeet_python_executable="",
            parakeet_min_audio_secs=0.01,
            parakeet_decode_hop_secs=0.01,
        ),
        worker_client_factory=lambda **_: worker,
    )

    await provider.start(emit_update=emit_update)
    await provider.push_audio(
        source="microphone",
        pcm=np.ones(320, dtype=np.float32),
        sample_rate=16_000,
    )

    assert emitted[-1].stream_id == "microphone"
    assert emitted[-1].text == "Thanks for calling Lloyds Bank."
    assert worker.start_calls == 1
