import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LiveScreen } from "../features/live/LiveScreen";
import type { SessionState } from "../lib/state/sessionReducer";

const stateWithTranscript: SessionState = {
  status: "live",
  coachingPaused: false,
  transcript: [
    {
      type: "transcript_turn",
      turn_id: "turn-1",
      revision: 1,
      event: "finalized",
      role: "colleague",
      source: "microphone",
      text: "Thanks for calling.",
      is_final: true,
      started_at: "2026-04-23T10:41:11Z",
      ended_at: "2026-04-23T10:41:13Z",
      confidence: 0.93,
    },
    {
      type: "transcript_turn",
      turn_id: "turn-2",
      revision: 1,
      event: "finalized",
      role: "customer",
      source: "blackhole",
      text: "I'm calling about a payment.",
      is_final: true,
      started_at: "2026-04-23T10:41:14Z",
      ended_at: "2026-04-23T10:41:17Z",
      confidence: 0.9,
    },
  ],
  nudges: [
    {
      type: "coaching_nudge",
      title: "Show ownership",
      message: "Confirm the next step clearly.",
      timestamp: "2026-04-23T10:41:19Z",
      priority: "normal",
      source_turn_ids: ["turn-1"],
    },
  ],
  voiceActivity: {
    microphone: { level: 0, active: false },
    blackhole: { level: 0, active: false },
  },
  debugEnabled: true,
  debugOpen: false,
  debugLogs: [],
  lastRuleFlags: [],
  setup: {
    captureMode: "mic_plus_blackhole",
    persona: "colleague_contact",
    microphoneDeviceId: "Test Mic",
    transcription: {
      provider: "parakeet_unified",
      model: "mlx-community/parakeet-tdt-0.6b-v2",
      latencyPreset: "balanced",
      segmentation: {
        policy: "source_turns",
      },
      coaching: {
        windowPolicy: "finalized_turns",
      },
      vad: {
        provider: "silero_vad",
        threshold: 0.5,
        minSilenceMs: 600,
      },
    },
  },
  summary: null,
  endedView: "summary",
};

afterEach(() => {
  cleanup();
});

describe("LiveScreen", () => {
  it("renders transcript rows and pause/stop controls", () => {
    render(
      <LiveScreen
        mode="live"
        onApplyTranscription={vi.fn()}
        onBackToSetup={vi.fn()}
        onBackToSummary={vi.fn()}
        state={stateWithTranscript}
        onPauseCoaching={vi.fn()}
        onStopSession={vi.fn()}
        onToggleDebug={vi.fn()}
      />,
    );

    expect(screen.getByText(/customer audio/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /pause coaching/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /stop session/i })).toBeInTheDocument();
  });

  it("renders a single live transcript lane for mic-only sessions", () => {
    render(
      <LiveScreen
        mode="live"
        onApplyTranscription={vi.fn()}
        onBackToSetup={vi.fn()}
        onBackToSummary={vi.fn()}
        state={{
          ...stateWithTranscript,
          setup: {
            ...stateWithTranscript.setup,
            captureMode: "mic_only",
          },
        }}
        onPauseCoaching={vi.fn()}
        onStopSession={vi.fn()}
        onToggleDebug={vi.fn()}
      />,
    );

    expect(screen.getByText(/live transcript/i)).toBeInTheDocument();
    expect(screen.queryByText(/colleague audio/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/customer audio/i)).not.toBeInTheDocument();
    expect(screen.getByText(/thanks for calling/i)).toBeInTheDocument();
    expect(screen.getByText(/i'm calling about a payment/i)).toBeInTheDocument();
  });

  it("applies advanced transcription settings from the live debug drawer", () => {
    const onApplyTranscription = vi.fn();

    render(
      <LiveScreen
        mode="live"
        onApplyTranscription={onApplyTranscription}
        onBackToSetup={vi.fn()}
        onBackToSummary={vi.fn()}
        state={{
          ...stateWithTranscript,
          debugOpen: true,
        }}
        onPauseCoaching={vi.fn()}
        onStopSession={vi.fn()}
        onToggleDebug={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByLabelText(/transcription provider/i), {
      target: { value: "nemo" },
    });
    fireEvent.click(screen.getByRole("button", { name: /apply transcription settings/i }));

    expect(onApplyTranscription).toHaveBeenCalledWith(
      expect.objectContaining({
        provider: "nemo",
      }),
    );
  });

  it("renders review navigation instead of live controls when showing an ended transcript", () => {
    render(
      <LiveScreen
        mode="review"
        onApplyTranscription={vi.fn()}
        onBackToSetup={vi.fn()}
        onBackToSummary={vi.fn()}
        state={{
          ...stateWithTranscript,
          status: "ended",
          endedView: "transcript",
        }}
        onPauseCoaching={vi.fn()}
        onStopSession={vi.fn()}
        onToggleDebug={vi.fn()}
      />,
    );

    expect(screen.getByRole("heading", { name: /transcript review/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /pause coaching/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /stop session/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /back to summary/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /back to setup/i })).toBeInTheDocument();
  });
});
