from typing import Literal

from pydantic import BaseModel


class SessionConfig(BaseModel):
    capture_mode: Literal["mic_only", "mic_plus_blackhole"]
    microphone_device_id: str
    persona: str
    coaching_profile: str
    asr_provider: str
    diarization_enabled: bool = False
    llm_base_url: str | None = None
    llm_model: str | None = None


class CoachingPauseRequest(BaseModel):
    paused: bool
