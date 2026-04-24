import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LiveScreen } from "../features/live/LiveScreen";
import type { SessionState } from "../lib/state/sessionReducer";

const stateWithTranscript: SessionState = {
  status: "live",
  coachingPaused: false,
  transcript: [
    {
      type: "transcript",
      role: "colleague",
      source: "microphone",
      text: "Thanks for calling.",
      is_partial: false,
      started_at: "2026-04-23T10:41:11Z",
      ended_at: "2026-04-23T10:41:13Z",
      confidence: 0.93,
    },
    {
      type: "transcript",
      role: "customer",
      source: "blackhole",
      text: "I'm calling about a payment.",
      is_partial: false,
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
  },
  summary: null,
};

describe("LiveScreen", () => {
  it("renders transcript rows and pause/stop controls", () => {
    render(
      <LiveScreen
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
});
