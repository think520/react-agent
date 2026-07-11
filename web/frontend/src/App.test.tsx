import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";

function jsonResponse(body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  }));
}

describe("Bobodan app shell", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const path = String(input);
      if (path.endsWith("/api/settings")) return jsonResponse({ workspace_name: "study", default_provider: "local", providers: [], mcp_enabled: false });
      if (path.endsWith("/api/chat/sessions")) return jsonResponse({ sessions: [] });
      if (path.endsWith("/api/kb/documents")) return jsonResponse({ documents: [] });
      if (path.endsWith("/api/learning/review-queue")) return jsonResponse({ due_concepts: [], wrong_answers: [], weaknesses: [] });
      throw new Error(`Unexpected request: ${path}`);
    }));
  });

  afterEach(() => vi.unstubAllGlobals());

  it("shows the real study navigation and Today state", async () => {
    render(<MemoryRouter initialEntries={["/chat"]}><App /></MemoryRouter>);

    expect(screen.getByRole("heading", { name: "今天想学点什么？", level: 2 })).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "对话" }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: "练习" }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: "复习" }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: "资料库" }).length).toBeGreaterThan(0);
    expect((await screen.findAllByText("study")).length).toBeGreaterThan(0);
  });
});
