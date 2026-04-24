from __future__ import annotations

import argparse
import base64
import json
import logging
import sys
from pathlib import Path

import numpy as np

logger = logging.getLogger("parakeet-worker")


def emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()


def _extract_increment(previous: str, current: str) -> str:
    prev_words = previous.split()
    curr_words = current.split()
    shared = 0
    for p, c in zip(prev_words, curr_words):
        if p != c:
            break
        shared += 1
    return " ".join(curr_words[shared:]).strip()


class StreamingSession:
    """
    Wraps a single live streaming session using NeMo's cache-aware streaming API.
    The model and its weights are shared; only the streaming state is per-session.
    """

    def __init__(self, wrapper, asr_model) -> None:
        from nemo.collections.asr.inference.utils.context_manager import CacheAwareContext
        from nemo.collections.asr.parts.utils.streaming_utils import CacheAwareStreamingAudioBuffer

        self._wrapper = wrapper
        self._streaming_buffer = CacheAwareStreamingAudioBuffer(model=asr_model)
        self._context = CacheAwareContext()
        self._previous_hypotheses = None
        self._step_num = 0
        self._stream_id: int | None = None
        self._full_text = ""

    def push_audio(self, samples: np.ndarray) -> str:
        """Append raw float32 samples. Returns any new text produced."""
        if self._stream_id is None:
            _, _, self._stream_id = self._streaming_buffer.append_audio(samples, stream_id=-1)
        else:
            self._streaming_buffer.append_audio(samples, stream_id=self._stream_id)
        return self._drain(is_final=False)

    def finalize(self) -> str:
        """Flush remaining audio. Returns any final text produced."""
        if self._streaming_buffer.buffer is None:
            return ""
        return self._drain(is_final=True)

    def _drain(self, is_final: bool) -> str:
        drop_extra = self._wrapper.drop_extra_pre_encoded
        parts: list[str] = []

        for chunk_audio, chunk_lengths in iter(self._streaming_buffer):
            is_last = self._streaming_buffer.is_buffer_empty()
            keep_all = is_final and is_last
            drop = drop_extra if self._step_num != 0 else 0

            best_hyp, self._context = self._wrapper.stream_step(
                processed_signal=chunk_audio,
                processed_signal_length=chunk_lengths,
                context=self._context,
                previous_hypotheses=self._previous_hypotheses,
                drop_extra_pre_encoded=drop,
                keep_all_outputs=keep_all,
            )
            self._previous_hypotheses = best_hyp
            self._step_num += 1

            new_full = best_hyp[0].text if best_hyp else ""
            delta = _extract_increment(self._full_text, new_full)
            if delta:
                self._full_text = new_full
                parts.append(delta)

        return " ".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", required=True)
    args = parser.parse_args()
    model_path = Path(args.model_path)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [parakeet-worker] %(message)s",
    )

    if not model_path.exists():
        logger.error("Model path not found: %s", model_path)
        return 1

    try:
        from nemo.collections.asr.inference.model_wrappers.cache_aware_rnnt_inference_wrapper import (
            CacheAwareRNNTInferenceWrapper,
        )
        from nemo.collections.asr.parts.submodules.rnnt_decoding import RNNTDecodingConfig

        wrapper = CacheAwareRNNTInferenceWrapper(
            model_name=str(model_path),
            decoding_cfg=RNNTDecodingConfig(),
            device="cpu",
            compute_dtype="float32",
            use_amp=False,
        )
        asr_model = wrapper.asr_model
    except Exception:
        logger.exception("Failed to load model")
        return 1

    logger.info("Model loaded: %s", model_path)
    emit({"type": "ready", "model_path": str(model_path)})

    session: StreamingSession | None = None

    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            logger.error("Invalid JSON on stdin")
            continue

        req_type = request.get("type")

        if req_type == "shutdown":
            logger.info("Shutdown requested")
            return 0

        if req_type == "reset":
            session = StreamingSession(wrapper, asr_model)
            emit({"type": "reset_ok"})
            continue

        if req_type == "push_chunk":
            if session is None:
                session = StreamingSession(wrapper, asr_model)

            raw_bytes = base64.b64decode(request.get("audio_b64", ""))
            samples = np.frombuffer(raw_bytes, dtype=np.float32).copy()

            try:
                delta = session.push_audio(samples)
            except Exception:
                logger.exception("push_audio failed")
                emit({"type": "chunk_result", "ok": False, "error": "push_audio failed"})
                continue

            emit({"type": "chunk_result", "ok": True, "text": delta})
            continue

        if req_type == "finalize":
            if session is None:
                emit({"type": "finalize_result", "ok": True, "text": ""})
                continue

            try:
                delta = session.finalize()
            except Exception:
                logger.exception("finalize failed")
                emit({"type": "finalize_result", "ok": False, "error": "finalize failed"})
                session = None
                continue

            session = None
            emit({"type": "finalize_result", "ok": True, "text": delta})
            continue

        emit({"type": "error", "error": f"Unknown request type: {req_type!r}"})

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
