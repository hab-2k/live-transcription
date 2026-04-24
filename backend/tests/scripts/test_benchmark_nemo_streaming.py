import asyncio
import importlib.util
from pathlib import Path


def load_module():
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "benchmark_nemo_streaming.py"
    spec = importlib.util.spec_from_file_location("benchmark_nemo_streaming", script_path)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_run_benchmark_returns_metrics_from_nemo_backend(tmp_path, monkeypatch) -> None:
    module = load_module()
    model_path = tmp_path / "parakeet.nemo"
    audio_path = tmp_path / "call.wav"
    model_path.write_text("stub")
    audio_path.write_text("stub")

    async def fake_benchmark(*, model_path: Path, audio_path: Path) -> dict[str, object]:
        return {
            "provider": "nemo",
            "model_path": str(model_path),
            "audio_path": str(audio_path),
            "audio_duration_secs": 8.1,
            "elapsed_secs": 3.2,
            "realtime_factor": 0.39,
            "mean_partial_latency_ms": 3010.0,
            "final_latency_ms": 3200.0,
            "transcript": "Thank you for calling Lloyds Bank.",
        }

    monkeypatch.setattr(module, "run_nemo_buffered_benchmark", fake_benchmark, raising=False)

    metrics = asyncio.run(
        module.run_benchmark(
            provider="nemo",
            model_path=str(model_path),
            audio=str(audio_path),
        )
    )

    assert metrics["provider"] == "nemo"
    assert metrics["transcript"] == "Thank you for calling Lloyds Bank."
