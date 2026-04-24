import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SummaryScreen } from "../features/summary/SummaryScreen";

describe("SummaryScreen", () => {
  it("shows the after-call summary once the session is stopped", () => {
    render(
      <SummaryScreen
        summary={{
          strengths: ["Clear ownership statement"],
          missedOpportunities: ["Could slow down the explanation"],
          flaggedMoments: ["Missing reassurance in the opening"],
        }}
      />,
    );

    expect(screen.getByRole("heading", { name: /call summary/i })).toBeInTheDocument();
  });
});
