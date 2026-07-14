import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
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
    localStorage.clear();
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const path = String(input);
      if (path.endsWith("/api/health")) return jsonResponse({ ok: true });
      if (path.endsWith("/api/settings")) return jsonResponse({
        workspace_name: "study",
        default_provider: "local",
        providers: [{ name: "local", configured: true, model: "study-model" }],
        search_providers: [{ name: "auto", configured: true }, { name: "tavily", configured: false }, { name: "exa", configured: true }],
        mcp_enabled: false,
        skills: [],
        preferences: {
          schema_version: 3,
          revision: 0,
          assistant: { display_name: "Bobodan", teaching_style: "guided", answer_depth: "standard", feedback_strength: "gentle" },
          user: { display_name: "", profile: "", long_term_goal: "" },
          appearance: { reading_font: "jin-kai", body_font_size: 16, content_width: 720, paper_texture: true, session_density: "comfortable", motion: "system" },
          ai: { default_provider: "local" },
          memory: { enabled: true },
          search: { provider: "auto", permission: "ask", jina_fallback: true },
          skills: { enabled_names: [] },
        },
      });
      if (path.endsWith("/api/libraries")) return jsonResponse({ active_library_id: "library-1", libraries: [{ library_id: "library-1", name: "Study Library", created_at: "", last_opened_at: "", active: true, available: true }] });
      if (path.endsWith("/api/chat/sessions")) return jsonResponse({ sessions: [] });
      if (path.includes("/api/kb/documents")) return jsonResponse({ documents: [] });
      if (path.endsWith("/api/learning/review-queue")) return jsonResponse({ due_concepts: [], wrong_answers: [], weaknesses: [] });
      throw new Error(`Unexpected request: ${path}`);
    }));
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("shows the real study navigation and Today state", async () => {
    render(<MemoryRouter initialEntries={["/chat"]}><App /></MemoryRouter>);

    expect(screen.getByRole("heading", { name: "今天想学点什么？", level: 2 })).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "对话" }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: "练习" }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: "复习" }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: "资料库" }).length).toBeGreaterThan(0);
    expect((await screen.findAllByText("Study Library")).length).toBeGreaterThan(0);
  });

  it("opens settings from the library profile and restores the deep-linked section", async () => {
    localStorage.setItem("bobodan:onboarding:v1", "complete");
    render(<MemoryRouter initialEntries={["/chat?settings=appearance"]}><App /></MemoryRouter>);

    expect(await screen.findByRole("dialog", { name: "设置" })).toBeInTheDocument();
    expect(screen.getAllByText("界面与阅读").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "关闭设置" }));
    expect(screen.queryByRole("dialog", { name: "设置" })).not.toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: "打开设置" }).at(-1)!);
    expect(await screen.findByRole("dialog", { name: "设置" })).toBeInTheDocument();
  });

  it("keeps the settings button useful while the backend is offline", async () => {
    localStorage.setItem("bobodan:onboarding:v1", "complete");
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const path = String(input);
      if (path.endsWith("/api/health") || path.endsWith("/api/settings")) {
        return Promise.resolve(new Response(JSON.stringify({ error: { code: "offline", message: "后端不可用" } }), {
          status: 503,
          headers: { "Content-Type": "application/json" },
        }));
      }
      if (path.endsWith("/api/libraries")) return jsonResponse({ active_library_id: null, libraries: [] });
      throw new Error(`Unexpected request: ${path}`);
    }));

    render(<MemoryRouter initialEntries={["/chat"]}><App /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: "打开设置" }));

    const dialog = await screen.findByRole("dialog", { name: "设置" });
    expect(dialog).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "设置暂时不可用" })).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "重新连接" })).toBeInTheDocument();
  });
});
