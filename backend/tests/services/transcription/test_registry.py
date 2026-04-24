import inspect

from app.services.transcription.registry import build_provider


def test_registry_builds_nemo_provider_by_name() -> None:
    provider = build_provider(provider_name="nemo", settings={})

    assert provider.name == "nemo"
    assert "emit_update" in inspect.signature(provider.start).parameters


def test_registry_builds_parakeet_unified_provider_by_name() -> None:
    provider = build_provider(provider_name="parakeet_unified", settings={})

    assert provider.name == "parakeet_unified"
