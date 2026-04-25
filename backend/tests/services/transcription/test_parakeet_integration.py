"""Integration tests for ParakeetUnifiedProvider with real audio and model.

Requires parakeet_mlx and the MLX model to be available. These tests
are slow (model load + real inference) and are skipped when the model
is not installed or the --run-slow flag is not passed to pytest.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from app.services.transcription.parakeet_unified_provider import ParakeetUnifiedProvider

# Fixtures are at the project root, not inside backend/
# Path chain: test_parakeet_integration.py -> transcription/ -> services/ -> tests/ -> backend/ -> project-root/
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
FIXTURES_DIR = _PROJECT_ROOT / "fixtures" / "audio"


def _load_audio_file(name: str) -> tuple[np.ndarray, int]:
    """Load a WAV file returning (pcm_float32, sample_rate)."""
    import soundfile as sf

    data, sr = sf.read(str(FIXTURES_DIR / name), dtype="float32")
    if data.ndim > 1:
        data = data.mean(axis=1)  # mono downmix
    return data, sr


@pytest.fixture
def provider():
    """Create a ParakeetUnifiedProvider with no settings (default MLX model)."""
    return ParakeetUnifiedProvider(settings=type("Empty", (), {})())


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.asyncio
async def test_transcribe_real_audio_single_source(provider: ParakeetUnifiedProvider) -> None:
    """Feed real benchmark audio through the provider; expect non-empty transcript."""
    assert FIXTURES_DIR.is_dir(), f"fixtures/audio not found at {FIXTURES_DIR}"
    assert (FIXTURES_DIR / "benchmark_call.wav").exists(), "benchmark_call.wav missing"

    pcm, sr = _load_audio_file("benchmark_call.wav")

    # Resample to 16kHz if needed (parakeet-mlx expects 16k)
    if sr != 16_000:
        import librosa
        pcm = librosa.resample(pcm, orig_sr=sr, target_sr=16_000)
        sr = 16_000

    updates: list = []

    async def emit_update(update) -> None:
        updates.append(update)

    await provider.start(emit_update=emit_update)

    # Feed audio in 1-second chunks to exercise the streaming path
    chunk_size = sr
    for i in range(0, len(pcm), chunk_size):
        await provider.push_audio(
            source="microphone",
            pcm=pcm[i : i + chunk_size],
            sample_rate=sr,
        )

    # Finalize any remaining partial
    await provider.finalize_utterance(source="microphone")
    await provider.stop()

    # Should have received at least some transcript text
    texts = [u.text for u in updates if u.text.strip()]
    assert texts, "Expected non-empty transcript from real audio"
    # All updates should be tagged with the correct source
    assert all(u.source == "microphone" for u in updates)


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.asyncio
async def test_transcribe_real_audio_dual_source_isolation(
    provider: ParakeetUnifiedProvider,
) -> None:
    """Push audio to both mic and system sources; verify independent transcripts."""
    assert FIXTURES_DIR.is_dir(), f"fixtures/audio not found at {FIXTURES_DIR}"

    pcm, sr = _load_audio_file("benchmark_call.wav")

    if sr != 16_000:
        import librosa
        pcm = librosa.resample(pcm, orig_sr=sr, target_sr=16_000)
        sr = 16_000

    updates: list = []

    async def emit_update(update) -> None:
        updates.append(update)

    await provider.start(emit_update=emit_update)

    # Interleave mic and system audio chunks
    chunk_size = sr
    for i in range(0, len(pcm), chunk_size):
        chunk = pcm[i : i + chunk_size]
        # Alternate sources to exercise concurrent stream handling
        await provider.push_audio(source="microphone", pcm=chunk, sample_rate=sr)
        await provider.push_audio(source="system", pcm=chunk * 0.5, sample_rate=sr)

    await provider.finalize_utterance(source="microphone")
    await provider.finalize_utterance(source="system")
    await provider.stop()

    mic_texts = [u.text for u in updates if u.source == "microphone" and u.text.strip()]
    sys_texts = [u.text for u in updates if u.source == "system" and u.text.strip()]

    assert mic_texts, "Expected non-empty mic transcript"
    assert sys_texts, "Expected non-empty system transcript"
