import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SetupScreen } from "../features/setup/SetupScreen";

describe("SetupScreen", () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);

      if (url.endsWith("/api/devices")) {
        return Promise.resolve({
          json: () =>
            Promise.resolve([
              { id: "Test Mic", label: "Test Mic", kind: "input" },
            ]),
        });
      }

      if (url.endsWith("/api/system-audio")) {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              provider: "screen_capture_kit",
              state: "available",
              message: "Ready to capture system audio.",
              targets: [
                {
                  id: "screen_capture_kit:1234",
                  name: "Microsoft Teams",
                  kind: "application",
                  icon_hint: null,
                },
              ],
            }),
        });
      }

      throw new Error(`Unexpected fetch: ${url}`);
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
    const startButton = screen.getAllByRole("button", { name: /start session/i }).at(-1);
    if (!startButton) {
      throw new Error("Start session button not found");
    }

    fireEvent.click(startButton);

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

  it("renders provider status and submits the selected system audio target", async () => {
    const onStart = vi.fn();

    render(<SetupScreen onStart={onStart} />);

    await waitFor(() => {
      expect(screen.getByText("Ready to capture system audio.")).toBeInTheDocument();
    });

    const targetSelect = screen.getAllByLabelText(/target application/i).at(-1);
    if (!targetSelect) {
      throw new Error("Target application select not found");
    }

    fireEvent.change(targetSelect, {
      target: { value: "screen_capture_kit:1234" },
    });
    const startButton = screen.getAllByRole("button", { name: /start session/i }).at(-1);
    if (!startButton) {
      throw new Error("Start session button not found");
    }

    fireEvent.click(startButton);

    expect(onStart).toHaveBeenCalledWith(
      expect.objectContaining({
        systemAudioSelection: {
          provider: "screen_capture_kit",
          targetId: "screen_capture_kit:1234",
        },
      }),
    );
  });
});
