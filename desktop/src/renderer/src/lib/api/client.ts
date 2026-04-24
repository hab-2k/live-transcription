import type { SessionSetup } from "../state/sessionReducer";
import type {
  CoachingNudgeEvent,
  RuleFlagEvent,
  SessionEvent,
  SessionStatusEvent,
  TranscriptEvent,
  VoiceActivityEvent,
} from "../types/session";

type StartSessionResponse = {
  session_id: string;
};

type PauseCoachingResponse = {
  status: string;
  session_id: string;
};

type BackendSummary = {
  strengths: string[];
  missed_opportunities: string[];
  flagged_moments: string[];
};

export type StopSessionResponse = {
  status: string;
  session_id: string;
  summary: {
    strengths: string[];
    missedOpportunities: string[];
    flaggedMoments: string[];
  } | null;
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
      asr_provider: "nemo",
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

function normalizeSummary(summary: BackendSummary | null) {
  if (summary === null) {
    return null;
  }

  return {
    strengths: summary.strengths,
    missedOpportunities: summary.missed_opportunities,
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
