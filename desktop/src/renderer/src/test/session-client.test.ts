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
      source: "system",
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
            model: "mlx-community/parakeet-tdt-0.6b-v2",
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

  it("posts provider-backed system audio selection when present", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ session_id: "session-456" }),
    }) as unknown as typeof fetch;

    await startSession(
      {
        captureMode: "mic_plus_system",
        persona: "manager",
        microphoneDeviceId: "Test Mic",
        transcription: createDefaultTranscriptionConfig("mic_plus_system"),
        systemAudioSelection: {
          provider: "screen_capture_kit",
          targetId: "screen_capture_kit:1234",
        },
      },
      "http://localhost:8000",
    );

    expect(globalThis.fetch).toHaveBeenCalledWith(
      "http://localhost:8000/api/sessions",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          capture_mode: "mic_plus_system",
          microphone_device_id: "Test Mic",
          persona: "manager",
          coaching_profile: "empathy",
          asr_provider: "parakeet_unified",
          transcription: {
            provider: "parakeet_unified",
            model: "mlx-community/parakeet-tdt-0.6b-v2",
            latency_preset: "balanced",
            segmentation: { policy: "source_turns" },
            coaching: { window_policy: "finalized_turns" },
            vad: {
              provider: "silero_vad",
              threshold: 0.5,
              min_silence_ms: 600,
            },
          },
          system_audio_selection: {
            provider: "screen_capture_kit",
            target_id: "screen_capture_kit:1234",
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
        model: "mlx-community/parakeet-tdt-0.6b-v2",
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
          model: "mlx-community/parakeet-tdt-0.6b-v2",
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
            recap: "The caller asked about a payment and left partly reassured.",
            strengths: ["Clear ownership statement"],
            weaknesses: ["Could confirm the next step sooner"],
            flagged_moments: ["Missing reassurance"],
          },
        }),
    }) as unknown as typeof fetch;

    const response = await stopSession("session-123", "http://localhost:8000");

    expect(response.summary?.recap).toContain("payment");
    expect(response.summary?.strengths).toEqual(["Clear ownership statement"]);
    expect(response.summary?.weaknesses).toEqual(["Could confirm the next step sooner"]);
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "http://localhost:8000/api/sessions/session-123/stop",
      expect.objectContaining({
        method: "POST",
      }),
    );
  });

  it("preserves a null summary from the stop endpoint", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          status: "stopped",
          session_id: "session-123",
          summary: null,
        }),
    }) as unknown as typeof fetch;

    const response = await stopSession("session-123", "http://localhost:8000");

    expect(response.summary).toBeNull();
  });
});
