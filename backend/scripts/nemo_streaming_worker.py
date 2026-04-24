from __future__ import annotations

import argparse
import copy
import json
import logging
import math
import sys
import time
from contextlib import redirect_stdout
from pathlib import Path


DEFAULT_CHUNK_LEN_SECS = 1.6
DEFAULT_TOTAL_BUFFER_SECS = 4.0
DEFAULT_MAX_STEPS_PER_TIMESTEP = 5


class BufferedNemoRuntime:
    def __init__(self, *, model_path: Path) -> None:
        import torch
        from omegaconf import OmegaConf, open_dict

        from nemo.collections.asr.models import ASRModel
        from nemo.collections.asr.parts.submodules.rnnt_decoding import RNNTDecodingConfig

        self._model_path = model_path
        self._map_location = torch.device("cpu")
        self._asr_model = ASRModel.restore_from(str(model_path), map_location=self._map_location)
        self._model_cfg = copy.deepcopy(self._asr_model._cfg)

        OmegaConf.set_struct(self._model_cfg.preprocessor, False)
        self._model_cfg.preprocessor.dither = 0.0
        self._model_cfg.preprocessor.pad_to = 0
        OmegaConf.set_struct(self._model_cfg.preprocessor, True)

        self._asr_model.freeze()
        self._asr_model = self._asr_model.to(self._map_location)

        self._decoding_cfg = OmegaConf.create(
            {
                "decoding": OmegaConf.structured(RNNTDecodingConfig()),
                "stateful_decoding": False,
                "batch_size": 1,
                "chunk_len_in_secs": DEFAULT_CHUNK_LEN_SECS,
                "total_buffer_in_secs": DEFAULT_TOTAL_BUFFER_SECS,
                "max_steps_per_timestep": DEFAULT_MAX_STEPS_PER_TIMESTEP,
            }
        )
        with open_dict(self._decoding_cfg.decoding):
            self._decoding_cfg.decoding.strategy = "greedy"
            self._decoding_cfg.decoding.preserve_alignments = True
            self._decoding_cfg.decoding.fused_batch_size = -1
            self._decoding_cfg.decoding.beam.return_best_hypothesis = True

        self._asr_model.change_decoding_strategy(self._decoding_cfg.decoding)

        feature_stride = self._model_cfg.preprocessor["window_stride"]
        self._model_stride_in_secs = feature_stride * self._asr_model.encoder.subsampling_factor
        self._tokens_per_chunk = math.ceil(self._decoding_cfg.chunk_len_in_secs / self._model_stride_in_secs)
        self._mid_delay = math.ceil(
            (
                self._decoding_cfg.chunk_len_in_secs
                + (self._decoding_cfg.total_buffer_in_secs - self._decoding_cfg.chunk_len_in_secs) / 2
            )
            / self._model_stride_in_secs
        )

    def decode(self, *, audio_path: Path) -> dict[str, object]:
        import soundfile as sf

        from nemo.collections.asr.parts.utils.streaming_utils import BatchedFrameASRTDT
        from nemo.collections.asr.parts.utils.transcribe_utils import get_buffered_pred_feat_rnnt

        audio_info = sf.info(str(audio_path))
        frame_asr = BatchedFrameASRTDT(
            asr_model=self._asr_model,
            frame_len=self._decoding_cfg.chunk_len_in_secs,
            total_buffer=self._decoding_cfg.total_buffer_in_secs,
            batch_size=self._decoding_cfg.batch_size,
            max_steps_per_timestep=self._decoding_cfg.max_steps_per_timestep,
            stateful_decoding=self._decoding_cfg.stateful_decoding,
        )

        started_at = time.perf_counter()
        hyps = get_buffered_pred_feat_rnnt(
            asr=frame_asr,
            tokens_per_chunk=self._tokens_per_chunk,
            delay=self._mid_delay,
            model_stride_in_secs=self._model_stride_in_secs,
            batch_size=self._decoding_cfg.batch_size,
            manifest=None,
            filepaths=[str(audio_path)],
            accelerator="cpu",
        )
        elapsed_secs = time.perf_counter() - started_at

        return {
            "transcript": hyps[0].text if hyps else "",
            "confidence": 0.0,
            "audio_duration_secs": round(audio_info.frames / audio_info.samplerate, 3),
            "elapsed_secs": round(elapsed_secs, 3),
        }


def emit(payload: dict[str, object]) -> None:
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    model_path = Path(args.model_path)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [nemo-worker] %(message)s",
    )

    if not model_path.exists():
        logging.error("NeMo model path does not exist: %s", model_path)
        return 1

    try:
        runtime = BufferedNemoRuntime(model_path=model_path)
    except Exception:
        logging.exception("Failed to load NeMo model")
        return 1

    logging.info("NeMo model loaded: %s", model_path)
    emit({"type": "ready", "model_path": str(model_path)})

    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            logging.error("Received invalid JSON request")
            continue

        request_type = request.get("type")
        if request_type == "shutdown":
            logging.info("Shutdown requested")
            return 0

        if request_type != "decode":
            emit(
                {
                    "type": "decode_result",
                    "ok": False,
                    "error": f"Unsupported request type: {request_type}",
                }
            )
            continue

        audio_path = Path(str(request.get("audio_path", "")))
        try:
            with redirect_stdout(sys.stderr):
                result = runtime.decode(audio_path=audio_path)
        except Exception:
            logging.exception("Decode failed for %s", audio_path)
            emit(
                {
                    "type": "decode_result",
                    "ok": False,
                    "error": f"Decode failed for {audio_path}",
                }
            )
            continue

        emit(
            {
                "type": "decode_result",
                "ok": True,
                **result,
            }
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
