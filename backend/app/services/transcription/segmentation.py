from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class SegmentationPolicy:
    capture_mode: str
    silence_finalize_ms: int
    max_chars: int

    @classmethod
    def for_capture_mode(cls, capture_mode: str, *, silence_finalize_ms: int | None = None) -> "SegmentationPolicy":
        if capture_mode == "mic_plus_system":
            return cls(capture_mode=capture_mode, silence_finalize_ms=silence_finalize_ms or 400, max_chars=100)
        return cls(capture_mode="mic_only", silence_finalize_ms=silence_finalize_ms or 600, max_chars=120)

    def should_finalize(self, *, current_text: str, silence_ms: int, source: str) -> bool:  # noqa: ARG002
        text = current_text.strip()
        if not text:
            return False
        if silence_ms >= self.silence_finalize_ms:
            return True
        return len(text) >= self.max_chars and text[-1] in ".!?"

    def should_split_on_source_change(self, *, current_source: str, incoming_source: str) -> bool:
        return self.capture_mode == "mic_plus_system" and current_source != incoming_source
