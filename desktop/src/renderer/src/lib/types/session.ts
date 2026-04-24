export type TranscriptRole = "colleague" | "customer" | "shared" | "unknown";
export type TranscriptSource = "microphone" | "blackhole" | "mixed";

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
  | CoachingNudgeEvent
  | SessionStatusEvent
  | RuleFlagEvent
  | VoiceActivityEvent;
