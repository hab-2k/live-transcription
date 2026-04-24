import { describe, expect, it } from "vitest";

import {
  createDefaultTranscriptionConfig,
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
      transcription: createDefaultTranscriptionConfig("mic_only"),
    },
  });
}

describe("sessionReducer", () => {
  it("revises a transcript turn in place until it is finalized", () => {
    const liveState = createLiveState();

    const started = sessionReducer(liveState, {
      type: "ingest_event",
      event: {
        type: "transcript_turn",
        turn_id: "turn-1",
        revision: 1,
        event: "started",
        role: "shared",
        source: "microphone",
        text: "Thanks",
        is_final: false,
        started_at: "2026-04-24T08:00:00Z",
        ended_at: "2026-04-24T08:00:01Z",
        confidence: 0.9,
      },
    });

    const updated = sessionReducer(started, {
      type: "ingest_event",
      event: {
        type: "transcript_turn",
        turn_id: "turn-1",
        revision: 2,
        event: "updated",
        role: "shared",
        source: "microphone",
        text: "Thanks for calling",
        is_final: false,
        started_at: "2026-04-24T08:00:00Z",
        ended_at: "2026-04-24T08:00:02Z",
        confidence: 0.92,
      },
    });

    const finalized = sessionReducer(updated, {
      type: "ingest_event",
      event: {
        type: "transcript_turn",
        turn_id: "turn-1",
        revision: 3,
        event: "finalized",
        role: "shared",
        source: "microphone",
        text: "Thanks for calling support",
        is_final: true,
        started_at: "2026-04-24T08:00:00Z",
        ended_at: "2026-04-24T08:00:03Z",
        confidence: 0.95,
      },
    });

    expect(started.transcript).toHaveLength(1);
    expect(updated.transcript).toHaveLength(1);
    expect(finalized.transcript).toHaveLength(1);
    expect(finalized.transcript[0]).toMatchObject({
      turn_id: "turn-1",
      revision: 3,
      text: "Thanks for calling support",
      is_final: true,
    });
  });

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
