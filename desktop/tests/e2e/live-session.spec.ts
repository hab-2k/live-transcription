import { _electron as electron, expect, test } from "@playwright/test";
import path from "node:path";

test("setup to live to summary flow", async () => {
  let markStartHandled: (() => void) | null = null;
  let markStopHandled: (() => void) | null = null;
  const sessionStarted = new Promise<void>((resolve) => {
    markStartHandled = resolve;
  });
  const sessionStopped = new Promise<void>((resolve) => {
    markStopHandled = resolve;
  });

  const app = await electron.launch({
    args: [path.join(process.cwd(), "dist-electron/main/index.js")],
  });

  try {
    const context = app.context();
    await context.route("**/api/devices", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([{ id: "Test Mic", label: "Test Mic", kind: "input" }]),
      });
    });
    await context.route("**/api/sessions", async (route) => {
      if (route.request().method() !== "POST") {
        await route.continue();
        return;
      }
      markStartHandled?.();
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({ session_id: "session-123" }),
      });
    });
    await context.route("**/api/sessions/session-123/stop", async (route) => {
      markStopHandled?.();
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "stopped",
          session_id: "session-123",
          summary: {
            strengths: ["Clear ownership statement"],
            missed_opportunities: ["Could confirm the next step sooner"],
            flagged_moments: ["Missing reassurance in the opening"],
          },
        }),
      });
    });

    const window = await app.firstWindow();

    await expect(window.getByRole("heading", { name: /start session/i })).toBeVisible();
    await window.getByRole("button", { name: /start session/i }).click();
    await sessionStarted;
    await expect(window.getByRole("heading", { name: /live coaching console/i })).toBeVisible();
    await window.waitForTimeout(100);
    await window.getByRole("button", { name: /stop session/i }).click();
    await sessionStopped;
    await expect(window.getByRole("heading", { name: /call summary/i })).toBeVisible();
  } finally {
    await app.close();
  }
});
