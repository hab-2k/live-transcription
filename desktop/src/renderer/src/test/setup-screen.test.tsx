import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SetupScreen } from "../features/setup/SetupScreen";

describe("SetupScreen", () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      json: () =>
        Promise.resolve([
          { id: "Test Mic", label: "Test Mic", kind: "input" },
        ]),
    }) as unknown as typeof fetch;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders only microphone, capture mode, and persona setup fields", async () => {
    render(<SetupScreen onStart={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByLabelText(/microphone/i)).toBeInTheDocument();
    });

    expect(screen.getByLabelText(/capture mode/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/persona/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/endpoint url/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/model name/i)).not.toBeInTheDocument();
  });
});
