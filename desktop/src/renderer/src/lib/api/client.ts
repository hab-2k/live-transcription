import type { SessionSetup, SummaryView } from "../state/sessionReducer";
import type {
  CoachingNudgeEvent,
  RuleFlagEvent,
  SessionEvent,
  SessionStatusEvent,
  TranscriptionConfig,
  TranscriptEvent,
  TranscriptTurnEvent,
  VoiceActivityEvent,
} from "../types/session";

type StartSessionResponse = {
  session_id: string;
};

type PauseCoachingResponse = {
  status: string;
  session_id: string;
};

type UpdateTranscriptionResponse = {
  status: string;
  session_id: string;
};

type BackendSummary = {
  recap: string;
  strengths: string[];
  weaknesses: string[];
  flagged_moments: string[];
};

export type StopSessionResponse = {
  status: string;
  session_id: string;
  summary: SummaryView | null;
};

type DesktopBridge = {
  backendUrl?: string;
};

async function readJsonResponse<T>(response: Response | { ok?: boolean; status?: number; json: () => Promise<unknown> }) {
  const payload = (await response.json()) as T | { detail?: string };

  if (response.ok === false) {
    const detail =
      isRecord(payload) && typeof payload["detail"] === "string"
        ? payload["detail"]
        : `Request failed${typeof response.status === "number" ? ` (${response.status})` : ""}`;
    throw new Error(detail);
  }

  return payload as T;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function serializeTranscriptionConfig(config: TranscriptionConfig) {
  return {
    provider: config.provider,
    model: config.model,
    latency_preset: config.latencyPreset,
    segmentation: {
      policy: config.segmentation.policy,
      ...(config.segmentation.silenceFinalizeMs != null && {
        silence_finalize_ms: config.segmentation.silenceFinalizeMs,
      }),
    },
    coaching: {
      window_policy: config.coaching.windowPolicy,
    },
    vad: {
      provider: config.vad.provider,
      threshold: config.vad.threshold,
      min_silence_ms: config.vad.minSilenceMs,
    },
  };
}

function isTranscriptEvent(value: Record<string, unknown>): value is TranscriptEvent {
  return (
    value["type"] === "transcript" &&
    typeof value["role"] === "string" &&
    typeof value["source"] === "string" &&
    typeof value["text"] === "string" &&
    typeof value["is_partial"] === "boolean" &&
    typeof value["started_at"] === "string" &&
    typeof value["ended_at"] === "string" &&
    typeof value["confidence"] === "number"
  );
}

function isTranscriptTurnEvent(value: Record<string, unknown>): value is TranscriptTurnEvent {
  return (
    value["type"] === "transcript_turn" &&
    typeof value["turn_id"] === "string" &&
    typeof value["revision"] === "number" &&
    (value["event"] === "started" ||
      value["event"] === "updated" ||
      value["event"] === "finalized") &&
    typeof value["role"] === "string" &&
    typeof value["source"] === "string" &&
    typeof value["text"] === "string" &&
    typeof value["is_final"] === "boolean" &&
    typeof value["started_at"] === "string" &&
    typeof value["ended_at"] === "string" &&
    typeof value["confidence"] === "number"
  );
}

function isCoachingNudgeEvent(value: Record<string, unknown>): value is CoachingNudgeEvent {
  return (
    value["type"] === "coaching_nudge" &&
    typeof value["title"] === "string" &&
    typeof value["message"] === "string" &&
    typeof value["timestamp"] === "string" &&
    (value["priority"] === "normal" || value["priority"] === "high") &&
    Array.isArray(value["source_turn_ids"])
  );
}

function isSessionStatusEvent(value: Record<string, unknown>): value is SessionStatusEvent {
  return value["type"] === "session_status" && typeof value["status"] === "string";
}

function isVoiceActivityEvent(value: Record<string, unknown>): value is VoiceActivityEvent {
  return (
    value["type"] === "voice_activity" &&
    typeof value["source"] === "string" &&
    typeof value["level"] === "number" &&
    typeof value["active"] === "boolean"
  );
}

function isRuleFlagEvent(value: Record<string, unknown>): value is RuleFlagEvent {
  return (
    value["type"] === "rule_flag" &&
    typeof value["code"] === "string" &&
    typeof value["message"] === "string" &&
    typeof value["timestamp"] === "string"
  );
}

export function parseSessionEvent(input: unknown): SessionEvent {
  if (!isRecord(input)) {
    throw new Error("Session event must be an object");
  }

  if (isTranscriptEvent(input)) {
    return input;
  }

  if (isTranscriptTurnEvent(input)) {
    return input;
  }

  if (isCoachingNudgeEvent(input)) {
    return input;
  }

  if (isSessionStatusEvent(input)) {
    return input;
  }

  if (isRuleFlagEvent(input)) {
    return input;
  }

  if (isVoiceActivityEvent(input)) {
    return input;
  }

  throw new Error("Unsupported session event");
}

function toWebSocketUrl(baseUrl: string): string {
  if (baseUrl.startsWith("https://")) {
    return `wss://${baseUrl.slice("https://".length)}`;
  }

  if (baseUrl.startsWith("http://")) {
    return `ws://${baseUrl.slice("http://".length)}`;
  }

  return baseUrl;
}

export function getBackendUrl(): string {
  const bridge = (globalThis as typeof globalThis & { desktopBridge?: DesktopBridge })
    .desktopBridge;
  const backendUrl = bridge?.backendUrl?.trim();

  return backendUrl ? backendUrl : "http://localhost:8000";
}

export function connectSessionEvents(
  sessionId: string,
  onEvent: (event: SessionEvent) => void,
  baseUrl: string,
) {
  const socket = new WebSocket(`${toWebSocketUrl(baseUrl)}/api/sessions/${sessionId}/events`);

  socket.onmessage = (message) => {
    onEvent(parseSessionEvent(JSON.parse(message.data)));
  };

  return () => socket.close();
}

export async function startSession(
  setup: SessionSetup,
  baseUrl: string,
): Promise<StartSessionResponse> {
  const response = await fetch(`${baseUrl}/api/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      capture_mode: setup.captureMode,
      microphone_device_id: setup.microphoneDeviceId,
      persona: setup.persona,
      coaching_profile: "empathy",
      asr_provider: setup.transcription.provider,
      transcription: serializeTranscriptionConfig(setup.transcription),
    }),
  });
  return readJsonResponse<StartSessionResponse>(response);
}

export async function setCoachingPaused(
  sessionId: string,
  paused: boolean,
  baseUrl: string,
): Promise<PauseCoachingResponse> {
  const response = await fetch(`${baseUrl}/api/sessions/${sessionId}/pause-coaching`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ paused }),
  });
  return readJsonResponse<PauseCoachingResponse>(response);
}

export async function setTranscriptionConfig(
  sessionId: string,
  transcription: TranscriptionConfig,
  baseUrl: string,
): Promise<UpdateTranscriptionResponse> {
  const response = await fetch(`${baseUrl}/api/sessions/${sessionId}/transcription-config`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(serializeTranscriptionConfig(transcription)),
  });
  return readJsonResponse<UpdateTranscriptionResponse>(response);
}

function normalizeSummary(summary: BackendSummary | null): SummaryView | null {
  if (summary === null) {
    return null;
  }

  return {
    recap: summary.recap,
    strengths: summary.strengths,
    weaknesses: summary.weaknesses,
    flaggedMoments: summary.flagged_moments,
  };
}

export async function stopSession(
  sessionId: string,
  baseUrl: string,
): Promise<StopSessionResponse> {
  const response = await fetch(`${baseUrl}/api/sessions/${sessionId}/stop`, {
    method: "POST",
  });
  const payload = await readJsonResponse<{
    status: string;
    session_id: string;
    summary: BackendSummary | null;
  }>(response);

  return {
    status: payload.status,
    session_id: payload.session_id,
    summary: normalizeSummary(payload.summary),
  };
}
