import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TranscriptPanel } from "../features/live/TranscriptPanel";

describe("TranscriptPanel lanes", () => {
  it("renders separate colleague and customer transcript lanes", () => {
    render(
      <TranscriptPanel
        transcript={[
          {
            type: "transcript",
            role: "colleague",
            source: "microphone",
            text: "Thanks for calling.",
            is_partial: false,
            started_at: "2026-04-23T18:00:00Z",
            ended_at: "2026-04-23T18:00:01Z",
            confidence: 0.92,
          },
          {
            type: "transcript",
            role: "customer",
            source: "blackhole",
            text: "I'm calling about a payment.",
            is_partial: false,
            started_at: "2026-04-23T18:00:02Z",
            ended_at: "2026-04-23T18:00:03Z",
            confidence: 0.9,
          },
        ]}
      />,
    );

    expect(screen.getByText(/colleague audio/i)).toBeInTheDocument();
    expect(screen.getByText(/customer audio/i)).toBeInTheDocument();
  });
});
