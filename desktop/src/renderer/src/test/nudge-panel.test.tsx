import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { NudgePanel } from "../features/live/NudgePanel";

describe("NudgePanel", () => {
  it("renders short nudges with timestamps", () => {
    render(
      <NudgePanel
        nudges={[
          {
            type: "coaching_nudge",
            title: "Lead with reassurance",
            message: "Lead with reassurance.",
            timestamp: "2026-04-23T10:41:19Z",
            priority: "normal",
            source_turn_ids: ["turn-1"],
          },
        ]}
      />,
    );

    expect(screen.getByText("Lead with reassurance.")).toBeInTheDocument();
    expect(screen.getByText("10:41:19")).toBeInTheDocument();
  });
});
