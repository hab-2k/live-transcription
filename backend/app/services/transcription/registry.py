from typing import Any

from app.services.transcription.base import TranscriptionProvider
from app.services.transcription.nemo_provider import NemoStreamingProvider
from app.services.transcription.parakeet_unified_provider import ParakeetUnifiedProvider


def build_provider(provider_name: str, settings: Any) -> TranscriptionProvider:
    if provider_name == "nemo":
        return NemoStreamingProvider(settings=settings)

    if provider_name == "parakeet_unified":
        return ParakeetUnifiedProvider(settings=settings)

    raise ValueError(f"Unsupported provider: {provider_name}")
