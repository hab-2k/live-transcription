import type {
  CoachingNudgeEvent,
  RuleFlagEvent,
  SessionEvent,
  TranscriptEvent,
  VoiceActivityEvent,
} from "../types/session";

export type CaptureMode = "mic_only" | "mic_plus_blackhole";
export type Persona = "colleague_contact" | "manager";

export type SessionSetup = {
  captureMode: CaptureMode;
  persona: Persona;
  microphoneDeviceId: string;
};

export type DebugLog = {
  id: string;
  label: string;
  message: string;
  timestamp: string;
};

export type VoiceActivity = {
  microphone: { level: number; active: boolean };
  blackhole: { level: number; active: boolean };
};

export type SessionState = {
  status: "setup" | "live" | "ended";
  coachingPaused: boolean;
  transcript: TranscriptEvent[];
  nudges: CoachingNudgeEvent[];
  voiceActivity: VoiceActivity;
  debugEnabled: boolean;
  debugOpen: boolean;
  debugLogs: DebugLog[];
  lastRuleFlags: RuleFlagEvent[];
  setup: SessionSetup;
  summary: {
    strengths: string[];
    missedOpportunities: string[];
    flaggedMoments: string[];
  } | null;
};

type SessionAction =
  | { type: "start_session"; setup: SessionSetup }
  | {
      type: "complete_session";
      summary: {
        strengths: string[];
        missedOpportunities: string[];
        flaggedMoments: string[];
      } | null;
    }
  | { type: "toggle_debug" }
  | { type: "ingest_event"; event: SessionEvent };

const DEFAULT_SETUP: SessionSetup = {
  captureMode: "mic_plus_blackhole",
  persona: "colleague_contact",
  microphoneDeviceId: "",
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
  blackhole: { level: 0, active: false },
};

export function createInitialSessionState(debugEnabled: boolean): SessionState {
  return {
    status: "setup",
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
    case "complete_session":
      return {
        ...state,
        status: "ended",
        coachingPaused: false,
        debugOpen: false,
        summary: action.summary,
      };
    case "toggle_debug":
      if (!state.debugEnabled) {
        return state;
      }
      return {
        ...state,
        debugOpen: !state.debugOpen,
      };
    case "ingest_event":
      if (action.event.type === "transcript") {
        return {
          ...state,
          transcript: [...state.transcript, action.event],
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
        const key = action.event.source === "blackhole" ? "blackhole" : "microphone";
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
        };
      }

      return state;
    default:
      return state;
  }
}
