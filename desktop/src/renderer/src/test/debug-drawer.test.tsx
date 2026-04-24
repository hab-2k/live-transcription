import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DebugDrawer } from "../features/debug/DebugDrawer";

describe("DebugDrawer", () => {
  it("hides the debug drawer when the feature flag is off", () => {
    render(
      <DebugDrawer
        enabled={false}
        open={false}
        logs={[]}
        onClose={vi.fn()}
      />,
    );

    expect(screen.queryByText(/coaching engine/i)).toBeNull();
  });
});
