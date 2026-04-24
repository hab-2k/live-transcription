from typing import Any

from app.services.transcription.base import TranscriptionProvider
from app.services.transcription.nemo_provider import NemoStreamingProvider


def build_provider(provider_name: str, settings: Any) -> TranscriptionProvider:
    if provider_name == "nemo":
        return NemoStreamingProvider(settings=settings)

    raise ValueError(f"Unsupported provider: {provider_name}")
