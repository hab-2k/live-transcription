import { describe, expect, it } from "vitest";

import {
  createInitialSessionState,
  sessionReducer,
  type SessionState,
} from "../lib/state/sessionReducer";

function createLiveState(): SessionState {
  return sessionReducer(createInitialSessionState(true), {
    type: "start_session",
    setup: {
      captureMode: "mic_only",
      persona: "colleague_contact",
      microphoneDeviceId: "Test Mic",
    },
  });
}

describe("sessionReducer", () => {
  it("tracks coaching pause state from backend session events", () => {
    const liveState = createLiveState();

    const paused = sessionReducer(liveState, {
      type: "ingest_event",
      event: {
        type: "session_status",
        status: "coaching_paused",
        session_id: "session-123",
      },
    });

    const resumed = sessionReducer(paused, {
      type: "ingest_event",
      event: {
        type: "session_status",
        status: "coaching_resumed",
        session_id: "session-123",
      },
    });

    expect(paused.coachingPaused).toBe(true);
    expect(resumed.coachingPaused).toBe(false);
  });

  it("stores the backend summary when the session completes", () => {
    const liveState = createLiveState();

    const ended = sessionReducer(liveState, {
      type: "complete_session",
      summary: {
        strengths: ["Clear ownership statement"],
        missedOpportunities: ["Could confirm the next step sooner"],
        flaggedMoments: ["Missing reassurance in the opening"],
      },
    });

    expect(ended.status).toBe("ended");
    expect(ended.summary?.strengths).toEqual(["Clear ownership statement"]);
  });
});
