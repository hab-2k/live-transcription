import { describe, expect, it, vi } from "vitest";

import {
  connectSessionEvents,
  getBackendUrl,
  parseSessionEvent,
  setCoachingPaused,
  setTranscriptionConfig,
  startSession,
  stopSession,
} from "../lib/api/client";
import { createDefaultTranscriptionConfig } from "../lib/state/sessionReducer";

describe("parseSessionEvent", () => {
  it("parses a transcript turn event without backend-specific fields", () => {
    const event = parseSessionEvent({
      type: "transcript_turn",
      turn_id: "turn-1",
      revision: 2,
      event: "updated",
      role: "customer",
      source: "blackhole",
      text: "I need help",
      is_final: false,
      started_at: "2026-04-23T18:00:00Z",
      ended_at: "2026-04-23T18:00:02Z",
      confidence: 0.88,
    });

    expect(event.type).toBe("transcript_turn");
    expect("provider" in event).toBe(false);
  });

  it("subscribes to session events over websocket using normalized events", () => {
    class MockWebSocket {
      static instances: MockWebSocket[] = [];
      onmessage: ((event: { data: string }) => void) | null = null;
      url: string;
      closed = false;

      constructor(url: string) {
        this.url = url;
        MockWebSocket.instances.push(this);
      }

      close() {
        this.closed = true;
      }
    }

    vi.stubGlobal("WebSocket", MockWebSocket);

    const onEvent = vi.fn();
    const disconnect = connectSessionEvents("session-123", onEvent, "http://localhost:8000");
    const socket = MockWebSocket.instances[0];

    socket.onmessage?.({
      data: JSON.stringify({
        type: "transcript_turn",
        turn_id: "turn-1",
        revision: 1,
        event: "started",
        role: "shared",
        source: "microphone",
        text: "I can help with that.",
        is_final: false,
        started_at: "2026-04-23T18:00:00Z",
        ended_at: "2026-04-23T18:00:02Z",
        confidence: 0.91,
      }),
    });

    expect(socket.url).toBe("ws://localhost:8000/api/sessions/session-123/events");
    expect(onEvent).toHaveBeenCalledTimes(1);

    disconnect();

    expect(socket.closed).toBe(true);
    vi.unstubAllGlobals();
  });

  it("uses the desktop bridge backend url override when available", () => {
    vi.stubGlobal("desktopBridge", { backendUrl: "http://127.0.0.1:9012" });

    expect(getBackendUrl()).toBe("http://127.0.0.1:9012");

    vi.unstubAllGlobals();
  });

  it("posts session setup including the selected LLM endpoint and model", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ session_id: "session-123" }),
    }) as unknown as typeof fetch;

    const response = await startSession(
      {
        captureMode: "mic_only",
        persona: "manager",
        microphoneDeviceId: "Test Mic",
        transcription: createDefaultTranscriptionConfig("mic_only"),
      },
      "http://localhost:8000",
    );

    expect(response.session_id).toBe("session-123");
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "http://localhost:8000/api/sessions",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          capture_mode: "mic_only",
          microphone_device_id: "Test Mic",
          persona: "manager",
          coaching_profile: "empathy",
          asr_provider: "parakeet_unified",
          transcription: {
            provider: "parakeet_unified",
            latency_preset: "balanced",
            segmentation: { policy: "fixed_lines" },
            coaching: { window_policy: "finalized_turns" },
            vad: {
              provider: "silero_vad",
              threshold: 0.5,
              min_silence_ms: 700,
            },
          },
        }),
      }),
    );
  });

  it("posts pause state to the backend", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ status: "coaching_paused", session_id: "session-123" }),
    }) as unknown as typeof fetch;

    const response = await setCoachingPaused("session-123", true, "http://localhost:8000");

    expect(response.status).toBe("coaching_paused");
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "http://localhost:8000/api/sessions/session-123/pause-coaching",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ paused: true }),
      }),
    );
  });

  it("posts transcription config updates to the backend", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ status: "transcription_reconfigured", session_id: "session-123" }),
    }) as unknown as typeof fetch;

    const response = await setTranscriptionConfig(
      "session-123",
      {
        provider: "nemo",
        latencyPreset: "balanced",
        segmentation: { policy: "source_turns" },
        coaching: { windowPolicy: "finalized_turns" },
        vad: {
          provider: "silero_vad",
          threshold: 0.55,
          minSilenceMs: 900,
        },
      },
      "http://localhost:8000",
    );

    expect(response.status).toBe("transcription_reconfigured");
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "http://localhost:8000/api/sessions/session-123/transcription-config",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          provider: "nemo",
          latency_preset: "balanced",
          segmentation: { policy: "source_turns" },
          coaching: { window_policy: "finalized_turns" },
          vad: {
            provider: "silero_vad",
            threshold: 0.55,
            min_silence_ms: 900,
          },
        }),
      }),
    );
  });

  it("returns the backend summary from the stop endpoint", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          status: "stopped",
          session_id: "session-123",
          summary: {
            strengths: ["Clear ownership statement"],
            missed_opportunities: ["Could confirm the next step sooner"],
            flagged_moments: ["Missing reassurance"],
          },
        }),
    }) as unknown as typeof fetch;

    const response = await stopSession("session-123", "http://localhost:8000");

    expect(response.summary?.strengths).toEqual(["Clear ownership statement"]);
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "http://localhost:8000/api/sessions/session-123/stop",
      expect.objectContaining({
        method: "POST",
      }),
    );
  });
});
