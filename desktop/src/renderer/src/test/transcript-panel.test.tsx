import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TranscriptPanel } from "../features/live/TranscriptPanel";

describe("TranscriptPanel", () => {
  it("shows shared audio rows for mic-only mode without diarization", () => {
    render(
      <TranscriptPanel
        transcript={[
          {
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
          },
        ]}
      />,
    );

    expect(screen.getByText(/shared audio/i)).toBeInTheDocument();
  });

  it("marks non-final transcript turns as provisional rows", () => {
    const { container } = render(
      <TranscriptPanel
        transcript={[
          {
            type: "transcript_turn",
            turn_id: "turn-1",
            revision: 2,
            event: "updated",
            role: "shared",
            source: "microphone",
            text: "I can help with that today.",
            is_final: false,
            started_at: "2026-04-23T18:00:00Z",
            ended_at: "2026-04-23T18:00:03Z",
            confidence: 0.93,
          },
        ]}
      />,
    );

    expect(container.querySelector(".transcript-row--partial")).not.toBeNull();
  });
});
