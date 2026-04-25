export type TranscriptRole = "colleague" | "customer" | "shared" | "unknown";
export type TranscriptSource = "microphone" | "system" | "mixed";
export type TranscriptionProvider = "parakeet_unified" | "nemo";
export type SystemAudioProviderId = "screen_capture_kit" | "wasapi_process_loopback" | "none";
export type SystemAudioProviderState = "available" | "permission_required" | "unsupported" | "error";
export type TranscriptionLatencyPreset = "balanced" | "low_latency" | "high_accuracy";
export type TranscriptionSegmentationPolicy = "source_turns" | "fixed_lines";
export type TranscriptionCoachingWindowPolicy = "finalized_turns" | "recent_text";
export type TranscriptionVadProvider = "silero_vad" | "disabled";

export type TranscriptionModel = "mlx-community/parakeet-tdt-0.6b-v2";

export type TranscriptionConfig = {
  provider: TranscriptionProvider;
  model: TranscriptionModel;
  latencyPreset: TranscriptionLatencyPreset;
  segmentation: {
    policy: TranscriptionSegmentationPolicy;
    silenceFinalizeMs?: number;
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

export type SystemAudioSelection = {
  provider: SystemAudioProviderId | string;
  targetId: string;
};

export type SystemAudioTarget = {
  id: string;
  name: string;
  kind: string;
  iconHint: string | null;
};

export type SystemAudioAvailability = {
  provider: SystemAudioProviderId | string;
  state: SystemAudioProviderState;
  message: string;
  targets: SystemAudioTarget[];
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
