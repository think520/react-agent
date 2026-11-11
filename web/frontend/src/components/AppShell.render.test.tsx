import { act, cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useOutletContext } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AppShell } from "./AppShell";

/**
 * AppShell 的无关重渲染（2026-11-11 审查）：窗口每拉动 1px、每 30 秒健康检查，
 * 以前都会让当前页面整页重渲染（Outlet context 每次都是新对象）。
 */
const onRender = vi.fn();

function Probe() {
  onRender(useOutletContext());
  return <div>probe-page</div>;
}

function jsonResponse(body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } }));
}

beforeEach(() => {
  localStorage.setItem("bobodan:onboarding:v1", "complete");
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const path = String(input);
    if (path.endsWith("/api/health")) return jsonResponse({ ok: true });
    if (path.endsWith("/api/settings")) return jsonResponse({
      workspace_name: "study", default_provider: "local", providers: [], search_providers: [], mcp_enabled: false, skills: [],
      preferences: {
        schema_version: 4, revision: 0,
        assistant: { display_name: "Bobodan", teaching_style: "guided", answer_depth: "standard", feedback_strength: "gentle" },
        user: { display_name: "", profile: "", long_term_goal: "" },
        appearance: { reading_font: "jin-kai", body_font_size: 16, content_width: 720, paper_texture: true, session_density: "comfortable", motion: "system", theme: "light", contrast: "normal" },
        ai: { default_provider: "local", task_providers: {} }, wiki: { default_mode: "standard", guide_completed: false, budget: {} },
        memory: { enabled: true }, search: { provider: "auto", permission: "ask", jina_fallback: true }, skills: { enabled_names: [] },
      },
    });
    if (path.endsWith("/api/libraries")) return jsonResponse({ active_library_id: "l1", libraries: [{ library_id: "l1", name: "Study", created_at: "", last_opened_at: "", active: true, available: true }] });
    if (path.endsWith("/api/chat/sessions")) return jsonResponse({ sessions: [] });
    if (path.includes("/api/kb/documents")) return jsonResponse({ documents: [] });
    if (path.endsWith("/api/learning/review-queue")) return jsonResponse({ due_concepts: [], wrong_answers: [], weaknesses: [] });
    return jsonResponse({});
  }));
});

afterEach(() => { cleanup(); vi.unstubAllGlobals(); localStorage.clear(); });

async function mountShell() {
  render(<MemoryRouter initialEntries={["/probe"]}><Routes><Route element={<AppShell />}><Route path="probe" element={<Probe />} /></Route></Routes></MemoryRouter>);
  await screen.findByText("probe-page");
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 50)); });
}

describe("AppShell does not re-render the page for unrelated shell updates", () => {
  it("resizing within the same layout breakpoint does not re-render the page", async () => {
    window.innerWidth = 1440;
    await mountShell();
    const before = onRender.mock.calls.length;
    for (const width of [1430, 1420, 1400, 1380, 1360]) {
      await act(async () => {
        window.innerWidth = width;
        window.dispatchEvent(new Event("resize"));
      });
    }
    expect(onRender.mock.calls.length - before).toBe(0);
  });

  // 守卫（不是修复）：心跳成功本来就不写状态，这条钉住「拆出 useBackendHealth 后仍然如此」。
  it("a healthy heartbeat does not re-render the page", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      await mountShell();
      const before = onRender.mock.calls.length;
      await act(async () => { await vi.advanceTimersByTimeAsync(31_000); });
      await act(async () => { await vi.advanceTimersByTimeAsync(31_000); });
      expect(onRender.mock.calls.length - before).toBe(0);
    } finally {
      vi.useRealTimers();
    }
  });

  it("crossing a layout breakpoint still updates the shell", async () => {
    window.innerWidth = 1440;
    await mountShell();
    expect(document.querySelector(".desktop-panel-toggle[aria-label='收起右栏'], .desktop-panel-toggle[aria-label='展开右栏']")).not.toBeNull();
    await act(async () => {
      window.innerWidth = 900;
      window.dispatchEvent(new Event("resize"));
    });
    // 跨过 972 / 1288 两个断点：左右栏都进入自动收起，按钮文案随之变成「展开」。
    expect(screen.getByRole("button", { name: "展开左栏" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "展开右栏" })).toBeTruthy();
  });
});
