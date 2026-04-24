import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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

  it("shows advanced transcription controls behind the setup gear button", async () => {
    const onStart = vi.fn();

    render(<SetupScreen debugEnabled onStart={onStart} />);

    await waitFor(() => {
      expect(screen.getByLabelText(/microphone/i)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /advanced transcription/i }));
    fireEvent.change(screen.getByLabelText(/transcription provider/i), {
      target: { value: "nemo" },
    });
    fireEvent.change(screen.getByLabelText(/vad minimum silence/i), {
      target: { value: "900" },
    });
    fireEvent.click(screen.getByRole("button", { name: /start session/i }));

    expect(screen.getByLabelText(/capture mode/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/persona/i)).toBeInTheDocument();
    expect(onStart).toHaveBeenCalledWith(
      expect.objectContaining({
        transcription: expect.objectContaining({
          provider: "nemo",
          vad: expect.objectContaining({
            minSilenceMs: 900,
          }),
        }),
      }),
    );
  });
});
