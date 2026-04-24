from __future__ import annotations

from pathlib import Path

from app.services.transcription.nemo_provider import NemoSidecarWorkerClient


class ParakeetUnifiedWorkerClient(NemoSidecarWorkerClient):
    def __init__(self, *, model_path: Path, python_executable: str, script_path: Path) -> None:
        super().__init__(
            model_path=model_path,
            python_executable=python_executable,
            script_path=script_path,
        )
