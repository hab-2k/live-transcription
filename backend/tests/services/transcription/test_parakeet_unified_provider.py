import importlib
import importlib.util
from pathlib import Path
import sys

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
