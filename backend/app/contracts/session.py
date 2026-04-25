from typing import Literal

from pydantic import BaseModel


class TranscriptionSegmentationConfig(BaseModel):
    policy: str
    silence_finalize_ms: int | None = None


class TranscriptionCoachingConfig(BaseModel):
    window_policy: str


class TranscriptionVadConfig(BaseModel):
    provider: str
    threshold: float
    min_silence_ms: int


class TranscriptionConfig(BaseModel):
    provider: str
    model: str = ""
    latency_preset: str
    segmentation: TranscriptionSegmentationConfig
    coaching: TranscriptionCoachingConfig
    vad: TranscriptionVadConfig


class SystemAudioSelection(BaseModel):
    provider: str
    target_id: str


class SessionConfig(BaseModel):
    capture_mode: Literal["mic_only", "mic_plus_system"]
    microphone_device_id: str
    persona: str
    coaching_profile: str
    asr_provider: str
    transcription: TranscriptionConfig | None = None
    diarization_enabled: bool = False
    llm_base_url: str | None = None
    llm_model: str | None = None
    system_audio_selection: SystemAudioSelection | None = None


class CoachingPauseRequest(BaseModel):
    paused: bool
