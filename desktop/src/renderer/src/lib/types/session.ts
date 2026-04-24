export type TranscriptRole = "colleague" | "customer" | "shared" | "unknown";
export type TranscriptSource = "microphone" | "blackhole" | "mixed";
export type TranscriptionProvider = "parakeet_unified" | "nemo";
export type TranscriptionLatencyPreset = "balanced" | "low_latency" | "high_accuracy";
export type TranscriptionSegmentationPolicy = "source_turns" | "fixed_lines";
export type TranscriptionCoachingWindowPolicy = "finalized_turns" | "recent_text";
export type TranscriptionVadProvider = "silero_vad" | "disabled";

export type TranscriptionConfig = {
  provider: TranscriptionProvider;
  latencyPreset: TranscriptionLatencyPreset;
  segmentation: {
    policy: TranscriptionSegmentationPolicy;
  };
  coaching: {
    windowPolicy: TranscriptionCoachingWindowPolicy;
  };
  vad: {
    provider: TranscriptionVadProvider;
    threshold: number;
    minSilenceMs: number;
  };
};

export type TranscriptEvent = {
  type: "transcript";
  role: TranscriptRole;
  source: TranscriptSource;
  text: string;
  is_partial: boolean;
  started_at: string;
  ended_at: string;
  confidence: number;
};

export type TranscriptTurnEvent = {
  type: "transcript_turn";
  turn_id: string;
  revision: number;
  event: "started" | "updated" | "finalized";
  role: TranscriptRole;
  source: TranscriptSource;
  text: string;
  is_final: boolean;
  started_at: string;
  ended_at: string;
  confidence: number;
};

export type CoachingNudgeEvent = {
  type: "coaching_nudge";
  title: string;
  message: string;
  timestamp: string;
  priority: "normal" | "high";
  source_turn_ids: string[];
};

export type SessionStatusEvent = {
  type: "session_status";
  status: string;
  session_id?: string;
};

export type RuleFlagEvent = {
  type: "rule_flag";
  code: string;
  message: string;
  timestamp: string;
};

export type VoiceActivityEvent = {
  type: "voice_activity";
  source: TranscriptSource;
  level: number;
  active: boolean;
};

export type SessionEvent =
  | TranscriptEvent
  | TranscriptTurnEvent
  | CoachingNudgeEvent
  | SessionStatusEvent
  | RuleFlagEvent
  | VoiceActivityEvent;
