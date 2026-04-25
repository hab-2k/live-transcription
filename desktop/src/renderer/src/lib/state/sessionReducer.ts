import type {
  CoachingNudgeEvent,
  RuleFlagEvent,
  SessionEvent,
  TranscriptionConfig,
  TranscriptTurnEvent,
  VoiceActivityEvent,
} from "../types/session";

export type CaptureMode = "mic_only" | "mic_plus_system";
export type Persona = "colleague_contact" | "manager";

export type SessionSetup = {
  captureMode: CaptureMode;
  persona: Persona;
  microphoneDeviceId: string;
  transcription: TranscriptionConfig;
  systemAudioPid?: number;
};

export type SummaryView = {
  recap: string;
  strengths: string[];
  weaknesses: string[];
  flaggedMoments: string[];
};

export type EndedView = "summary" | "transcript";

export type DebugLog = {
  id: string;
  label: string;
  message: string;
  timestamp: string;
};

export type VoiceActivity = {
  microphone: { level: number; active: boolean };
  system: { level: number; active: boolean };
};

export type SessionState = {
  status: "setup" | "live" | "ended";
  endedView: EndedView;
  coachingPaused: boolean;
  transcript: TranscriptTurnEvent[];
  nudges: CoachingNudgeEvent[];
  voiceActivity: VoiceActivity;
  debugEnabled: boolean;
  debugOpen: boolean;
  debugLogs: DebugLog[];
  lastRuleFlags: RuleFlagEvent[];
  setup: SessionSetup;
  summary: SummaryView | null;
};

type SessionAction =
  | { type: "start_session"; setup: SessionSetup }
  | { type: "update_transcription_config"; transcription: TranscriptionConfig }
  | { type: "complete_session"; summary: SummaryView | null }
  | { type: "show_ended_summary" }
  | { type: "show_ended_transcript" }
  | { type: "reset_session" }
  | { type: "toggle_debug" }
  | { type: "ingest_event"; event: SessionEvent };

export function createDefaultTranscriptionConfig(captureMode: CaptureMode): TranscriptionConfig {
  return {
    provider: "parakeet_unified",
    model: "mlx-community/parakeet-tdt-0.6b-v2",
    latencyPreset: "balanced",
    segmentation: {
      policy: captureMode === "mic_only" ? "fixed_lines" : "source_turns",
    },
    coaching: {
      windowPolicy: "finalized_turns",
    },
    vad: {
      provider: "silero_vad",
      threshold: 0.5,
      minSilenceMs: captureMode === "mic_only" ? 700 : 600,
    },
  };
}

const DEFAULT_SETUP: SessionSetup = {
  captureMode: "mic_plus_system",
  persona: "colleague_contact",
  microphoneDeviceId: "",
  transcription: createDefaultTranscriptionConfig("mic_plus_system"),
};

function makeDebugLog(label: string, message: string): DebugLog {
  return {
    id: `${label}-${message}`,
    label,
    message,
    timestamp: new Date().toISOString(),
  };
}

const INITIAL_VOICE_ACTIVITY: VoiceActivity = {
  microphone: { level: 0, active: false },
  system: { level: 0, active: false },
};

function upsertTranscriptTurn(
  transcript: TranscriptTurnEvent[],
  event: TranscriptTurnEvent,
): TranscriptTurnEvent[] {
  const index = transcript.findIndex((row) => row.turn_id === event.turn_id);

  if (index === -1) {
    return [...transcript, event];
  }

  if (transcript[index].revision >= event.revision) {
    return transcript;
  }

  const next = transcript.slice();
  next[index] = event;
  return next;
}

export function createInitialSessionState(debugEnabled: boolean): SessionState {
  return {
    status: "setup",
    endedView: "summary",
    coachingPaused: false,
    transcript: [],
    nudges: [],
    voiceActivity: INITIAL_VOICE_ACTIVITY,
    debugEnabled,
    debugOpen: false,
    debugLogs: [],
    lastRuleFlags: [],
    setup: DEFAULT_SETUP,
    summary: null,
  };
}

export function sessionReducer(state: SessionState, action: SessionAction): SessionState {
  switch (action.type) {
    case "start_session":
      return {
        ...state,
        status: "live",
        endedView: "summary",
        coachingPaused: false,
        debugOpen: false,
        transcript: [],
        nudges: [],
        voiceActivity: INITIAL_VOICE_ACTIVITY,
        lastRuleFlags: [],
        setup: action.setup,
        summary: null,
        debugLogs: [
          makeDebugLog("Devices", `Capture mode: ${action.setup.captureMode}`),
          makeDebugLog("Coaching engine", `Persona: ${action.setup.persona}`),
        ],
      };
    case "update_transcription_config":
      return {
        ...state,
        setup: {
          ...state.setup,
          transcription: action.transcription,
        },
        debugLogs: [
          makeDebugLog(
            "Transcription",
            `Provider: ${action.transcription.provider}, latency: ${action.transcription.latencyPreset}`,
          ),
          ...state.debugLogs,
        ].slice(0, 10),
      };
    case "complete_session":
      return {
        ...state,
        status: "ended",
        endedView: "summary",
        coachingPaused: false,
        debugOpen: false,
        summary: action.summary,
      };
    case "show_ended_summary":
      return state.status === "ended" ? { ...state, endedView: "summary" } : state;
    case "show_ended_transcript":
      return state.status === "ended" ? { ...state, endedView: "transcript" } : state;
    case "reset_session":
      return createInitialSessionState(state.debugEnabled);
    case "toggle_debug":
      if (!state.debugEnabled) {
        return state;
      }
      return {
        ...state,
        debugOpen: !state.debugOpen,
      };
    case "ingest_event":
      if (action.event.type === "transcript_turn") {
        return {
          ...state,
          transcript: upsertTranscriptTurn(state.transcript, action.event),
        };
      }

      if (action.event.type === "coaching_nudge") {
        return {
          ...state,
          nudges: [action.event, ...state.nudges].slice(0, 3),
        };
      }

      if (action.event.type === "rule_flag") {
        return {
          ...state,
          lastRuleFlags: [action.event, ...state.lastRuleFlags].slice(0, 5),
          debugLogs: [
            makeDebugLog("Rules", `${action.event.code}: ${action.event.message}`),
            ...state.debugLogs,
          ].slice(0, 10),
        };
      }

      if (action.event.type === "voice_activity") {
        const key = action.event.source === "system" ? "system" : "microphone";
        return {
          ...state,
          voiceActivity: {
            ...state.voiceActivity,
            [key]: { level: action.event.level, active: action.event.active },
          },
        };
      }

      if (action.event.type === "session_status") {
        return {
          ...state,
          coachingPaused:
            action.event.status === "coaching_paused"
              ? true
              : action.event.status === "coaching_resumed"
                ? false
                : state.coachingPaused,
          status: action.event.status === "stopped" ? "ended" : state.status,
          endedView: action.event.status === "stopped" ? "summary" : state.endedView,
        };
      }

      return state;
    default:
      return state;
  }
}
