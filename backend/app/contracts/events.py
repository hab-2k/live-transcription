from typing import Literal

from pydantic import BaseModel


class TranscriptEvent(BaseModel):
    type: Literal["transcript"] = "transcript"
    role: Literal["colleague", "customer", "shared", "unknown"]
    source: Literal["microphone", "system", "mixed"]
    text: str
    is_partial: bool
    started_at: str
    ended_at: str
    confidence: float


class TranscriptTurnEvent(BaseModel):
    type: Literal["transcript_turn"] = "transcript_turn"
    turn_id: str
    revision: int
    event: Literal["started", "updated", "finalized"]
    role: Literal["colleague", "customer", "shared", "unknown"]
    source: Literal["microphone", "system", "mixed"]
    text: str
    is_final: bool
    started_at: str
    ended_at: str
    confidence: float


class CoachingNudgeEvent(BaseModel):
    type: Literal["coaching_nudge"] = "coaching_nudge"
    title: str
    message: str
    timestamp: str
    priority: Literal["normal", "high"]
    source_turn_ids: list[str]


class RuleFlagEvent(BaseModel):
    type: Literal["rule_flag"] = "rule_flag"
    code: str
    message: str
    timestamp: str


class SessionStatusEvent(BaseModel):
    type: Literal["session_status"] = "session_status"
    status: str
    session_id: str | None = None


class VoiceActivityEvent(BaseModel):
    type: Literal["voice_activity"] = "voice_activity"
    source: Literal["microphone", "system", "mixed"]
    level: float
    active: bool


SessionEvent = (
    TranscriptEvent
    | TranscriptTurnEvent
    | CoachingNudgeEvent
    | RuleFlagEvent
    | SessionStatusEvent
    | VoiceActivityEvent
)
