import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import { BlockErrorBoundary } from "./ErrorBoundary";

function Bomb(): never {
  throw new Error("boom");
}

describe("BlockErrorBoundary", () => {
  it("renders children when nothing throws", () => {
    render(<BlockErrorBoundary><span>ok</span></BlockErrorBoundary>);
    expect(screen.getByText("ok")).toBeInTheDocument();
  });

  it("catches a throwing child and renders the quiet fallback", () => {
    // React logs the error to console; silence it for a clean test run.
    const spy = vi.spyOn(console, "error").mockImplementation(() => undefined);
    try {
      render(<BlockErrorBoundary><Bomb /></BlockErrorBoundary>);
      expect(screen.getByText(/此卡片暂时无法显示/)).toBeInTheDocument();
    } finally {
      spy.mockRestore();
    }
  });
});
