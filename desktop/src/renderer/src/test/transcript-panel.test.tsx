import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TranscriptPanel } from "../features/live/TranscriptPanel";

describe("TranscriptPanel", () => {
  it("shows shared audio rows for mic-only mode without diarization", () => {
    render(
      <TranscriptPanel
        transcript={[
          {
            type: "transcript",
            role: "shared",
            source: "microphone",
            text: "I can help with that.",
            is_partial: false,
            started_at: "2026-04-23T18:00:00Z",
            ended_at: "2026-04-23T18:00:02Z",
            confidence: 0.91,
          },
        ]}
      />,
    );

    expect(screen.getByText(/shared audio/i)).toBeInTheDocument();
  });
});
