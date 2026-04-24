from app.services.transcription.registry import build_provider


def test_registry_builds_nemo_provider_by_name() -> None:
    provider = build_provider(provider_name="nemo", settings={})

    assert provider.name == "nemo"
