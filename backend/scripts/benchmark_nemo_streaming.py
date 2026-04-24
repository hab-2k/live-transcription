from __future__ import annotations

import argparse
import asyncio
import copy
import json
import math
from pathlib import Path
import time


DEFAULT_CHUNK_LEN_SECS = 1.6
DEFAULT_TOTAL_BUFFER_SECS = 4.0
DEFAULT_MAX_STEPS_PER_TIMESTEP = 5


def _build_metrics(
    *,
    model_path: Path,
    audio_path: Path,
    transcript: str,
    audio_duration_secs: float,
    elapsed_secs: float,
    chunk_len_secs: float,
    partial_delay_secs: float,
) -> dict[str, object]:
    chunk_count = max(1, math.ceil(audio_duration_secs / chunk_len_secs))
    mean_chunk_compute_secs = elapsed_secs / chunk_count

    return {
        "provider": "nemo",
        "model_path": str(model_path),
        "audio_path": str(audio_path),
        "audio_duration_secs": round(audio_duration_secs, 3),
        "elapsed_secs": round(elapsed_secs, 3),
        "realtime_factor": round(elapsed_secs / audio_duration_secs, 3),
        "mean_partial_latency_ms": round((partial_delay_secs + mean_chunk_compute_secs) * 1000, 1),
        "final_latency_ms": round(elapsed_secs * 1000, 1),
        "chunk_len_secs": chunk_len_secs,
        "total_buffer_secs": DEFAULT_TOTAL_BUFFER_SECS,
        "partial_delay_secs": round(partial_delay_secs, 3),
        "transcript": transcript,
    }


def _run_nemo_buffered_benchmark(*, model_path: Path, audio_path: Path) -> dict[str, object]:
    import soundfile as sf
    import torch
    from omegaconf import OmegaConf, open_dict

    from nemo.collections.asr.models import ASRModel
    from nemo.collections.asr.parts.submodules.rnnt_decoding import RNNTDecodingConfig
    from nemo.collections.asr.parts.utils.streaming_utils import BatchedFrameASRTDT
    from nemo.collections.asr.parts.utils.transcribe_utils import get_buffered_pred_feat_rnnt

    map_location = torch.device("cpu")
    audio_info = sf.info(str(audio_path))
    audio_duration_secs = audio_info.frames / audio_info.samplerate

    asr_model = ASRModel.restore_from(str(model_path), map_location=map_location)
    model_cfg = copy.deepcopy(asr_model._cfg)
    OmegaConf.set_struct(model_cfg.preprocessor, False)
    model_cfg.preprocessor.dither = 0.0
    model_cfg.preprocessor.pad_to = 0
    OmegaConf.set_struct(model_cfg.preprocessor, True)

    asr_model.freeze()
    asr_model = asr_model.to(map_location)

    cfg = OmegaConf.create(
        {
            "decoding": OmegaConf.structured(RNNTDecodingConfig()),
            "stateful_decoding": False,
            "batch_size": 1,
            "chunk_len_in_secs": DEFAULT_CHUNK_LEN_SECS,
            "total_buffer_in_secs": DEFAULT_TOTAL_BUFFER_SECS,
            "max_steps_per_timestep": DEFAULT_MAX_STEPS_PER_TIMESTEP,
        }
    )
    with open_dict(cfg.decoding):
        cfg.decoding.strategy = "greedy"
        cfg.decoding.preserve_alignments = True
        cfg.decoding.fused_batch_size = -1
        cfg.decoding.beam.return_best_hypothesis = True

    asr_model.change_decoding_strategy(cfg.decoding)

    feature_stride = model_cfg.preprocessor["window_stride"]
    model_stride_in_secs = feature_stride * asr_model.encoder.subsampling_factor
    tokens_per_chunk = math.ceil(cfg.chunk_len_in_secs / model_stride_in_secs)
    mid_delay = math.ceil(
        (cfg.chunk_len_in_secs + (cfg.total_buffer_in_secs - cfg.chunk_len_in_secs) / 2) / model_stride_in_secs
    )
    partial_delay_secs = mid_delay * model_stride_in_secs

    frame_asr = BatchedFrameASRTDT(
        asr_model=asr_model,
        frame_len=cfg.chunk_len_in_secs,
        total_buffer=cfg.total_buffer_in_secs,
        batch_size=cfg.batch_size,
        max_steps_per_timestep=cfg.max_steps_per_timestep,
        stateful_decoding=cfg.stateful_decoding,
    )

    started_at = time.perf_counter()
    hyps = get_buffered_pred_feat_rnnt(
        asr=frame_asr,
        tokens_per_chunk=tokens_per_chunk,
        delay=mid_delay,
        model_stride_in_secs=model_stride_in_secs,
        batch_size=cfg.batch_size,
        manifest=None,
        filepaths=[str(audio_path)],
        accelerator="cpu",
    )
    elapsed_secs = time.perf_counter() - started_at
    transcript = hyps[0].text if hyps else ""

    return _build_metrics(
        model_path=model_path,
        audio_path=audio_path,
        transcript=transcript,
        audio_duration_secs=audio_duration_secs,
        elapsed_secs=elapsed_secs,
        chunk_len_secs=cfg.chunk_len_in_secs,
        partial_delay_secs=partial_delay_secs,
    )


async def run_nemo_buffered_benchmark(*, model_path: Path, audio_path: Path) -> dict[str, object]:
    return await asyncio.to_thread(
        _run_nemo_buffered_benchmark,
        model_path=model_path,
        audio_path=audio_path,
    )


async def run_benchmark(*, provider: str, model_path: str, audio: str) -> dict[str, object]:
    model = Path(model_path)
    audio_file = Path(audio)

    if provider != "nemo":
        raise ValueError(f"Unsupported provider for benchmark: {provider}")

    if not model.exists():
        raise FileNotFoundError(f"Model path does not exist: {model}")

    if not audio_file.exists():
        raise FileNotFoundError(f"Audio file does not exist: {audio_file}")

    return await run_nemo_buffered_benchmark(
        model_path=model,
        audio_path=audio_file,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", required=True)
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--audio", required=True)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    metrics = asyncio.run(
        run_benchmark(
            provider=args.provider,
            model_path=args.model_path,
            audio=args.audio,
        )
    )
    print(json.dumps(metrics, indent=2))
