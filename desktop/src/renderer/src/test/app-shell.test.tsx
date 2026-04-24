import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../App";

describe("App", () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn((input, init) => {
      if (typeof input === "string" && input.endsWith("/api/devices")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([{ id: "Test Mic", label: "Test Mic", kind: "input" }]),
        });
      }

      if (typeof input === "string" && input.endsWith("/api/sessions") && init?.method === "POST") {
        return Promise.resolve({
          ok: false,
          json: () =>
            Promise.resolve({
              detail:
                "Parakeet Unified is not configured. Set LTD_PARAKEET_MODEL_PATH (or LTD_NEMO_MODEL_PATH as a fallback) to the local model artifact before starting a session.",
            }),
        });
      }

      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve([]),
      });
    }) as unknown as typeof fetch;
  });

  afterEach(() => {
    vi.restoreAllMocks();
    cleanup();
  });

  it("renders the setup entry point", async () => {
    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /start session/i })).toBeInTheDocument();
    });
  });

  it("stays on setup and shows a clear error when session start fails", async () => {
    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /start session/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /start session/i }));

    await waitFor(() => {
      expect(screen.getByText(/parakeet unified is not configured/i)).toBeInTheDocument();
    });

    expect(screen.getByRole("heading", { name: /start session/i })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /live coaching console/i })).not.toBeInTheDocument();
  });
});
