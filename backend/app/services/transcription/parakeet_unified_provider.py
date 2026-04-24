from __future__ import annotations

from pathlib import Path
import sys

from app.services.transcription.nemo_provider import NemoStreamingProvider
from app.services.transcription.nemo_provider import NemoSidecarWorkerClient


class ParakeetUnifiedWorkerClient(NemoSidecarWorkerClient):
    def __init__(self, *, model_path: Path, python_executable: str, script_path: Path) -> None:
        super().__init__(
            model_path=model_path,
            python_executable=python_executable,
            script_path=script_path,
        )


class ParakeetUnifiedProvider(NemoStreamingProvider):
    name = "parakeet_unified"

    def __init__(self, settings, worker_client_factory=None) -> None:  # noqa: ANN001
        super().__init__(settings=settings, worker_client_factory=worker_client_factory or self._build_worker_client)
        self._model_path_raw = str(
            getattr(settings, "parakeet_model_path", getattr(settings, "nemo_model_path", ""))
        ).strip()
        self._model_path = Path(self._model_path_raw) if self._model_path_raw else None
        self._python_executable = (
            getattr(settings, "parakeet_python_executable", "")
            or getattr(settings, "nemo_python_executable", "")
            or sys.executable
        )
        self._min_audio_secs = float(
            getattr(settings, "parakeet_min_audio_secs", getattr(settings, "nemo_min_audio_secs", 1.6))
        )
        self._decode_hop_secs = float(
            getattr(settings, "parakeet_decode_hop_secs", getattr(settings, "nemo_decode_hop_secs", 1.6))
        )
        self._worker_script_path = Path(__file__).resolve().parents[3] / "scripts" / "parakeet_unified_streaming_worker.py"

    @staticmethod
    def _build_worker_client(*, model_path: Path, python_executable: str, script_path: Path):
        return ParakeetUnifiedWorkerClient(
            model_path=model_path,
            python_executable=python_executable,
            script_path=script_path,
        )
