import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { vi } from "vitest";

import { SummaryScreen } from "../features/summary/SummaryScreen";

describe("SummaryScreen", () => {
  it("renders recap, renamed sections, and summary actions", () => {
    const onViewTranscript = vi.fn();
    const onStartNewCall = vi.fn();

    render(
      <SummaryScreen
        summary={{
          recap: "The caller asked about a payment and left partly reassured.",
          strengths: ["Clear ownership statement"],
          weaknesses: ["Could slow down the explanation"],
          flaggedMoments: ["Missing reassurance in the opening"],
        }}
        onStartNewCall={onStartNewCall}
        onViewTranscript={onViewTranscript}
      />,
    );

    expect(screen.getByRole("heading", { name: /call summary/i })).toBeInTheDocument();
    expect(screen.getByText(/call recap/i)).toBeInTheDocument();
    expect(screen.getByText(/weaknesses/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /view transcript/i }));
    fireEvent.click(screen.getByRole("button", { name: /start new call/i }));

    expect(onViewTranscript).toHaveBeenCalledTimes(1);
    expect(onStartNewCall).toHaveBeenCalledTimes(1);
  });

  it("renders an unavailable state when the LLM summary is missing", () => {
    render(
      <SummaryScreen summary={null} onStartNewCall={vi.fn()} onViewTranscript={vi.fn()} />,
    );

    expect(screen.getByText(/after-call summary unavailable/i)).toBeInTheDocument();
  });
});
