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
    vi.unstubAllGlobals();
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

  it("shows the summary screen even when stop returns no summary payload", async () => {
    class MockWebSocket {
      onmessage: ((event: { data: string }) => void) | null = null;

      constructor(_url: string) {}

      close() {}
    }

    vi.stubGlobal("WebSocket", MockWebSocket);
    globalThis.fetch = vi.fn((input, init) => {
      if (typeof input === "string" && input.endsWith("/api/devices")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([{ id: "Test Mic", label: "Test Mic", kind: "input" }]),
        });
      }

      if (typeof input === "string" && input.endsWith("/api/sessions") && init?.method === "POST") {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ session_id: "session-123" }),
        });
      }

      if (
        typeof input === "string" &&
        input.endsWith("/api/sessions/session-123/stop") &&
        init?.method === "POST"
      ) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              status: "stopped",
              session_id: "session-123",
              summary: null,
            }),
        });
      }

      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve([]),
      });
    }) as unknown as typeof fetch;

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /start session/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /start session/i }));

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /live coaching console/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /stop session/i }));

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /call summary/i })).toBeInTheDocument();
    });
  });
});
