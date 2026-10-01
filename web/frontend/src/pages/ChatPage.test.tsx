import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useHandoffStore } from "../stores/handoffStore";
import { ChatPage } from "./ChatPage";

const hoisted = vi.hoisted(() => ({ ctx: {} as Record<string, unknown> }));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useOutletContext: () => hoisted.ctx };
});

function shellContext() {
  return {
    refreshSessions: vi.fn().mockResolvedValue(undefined),
    refreshSettings: vi.fn().mockResolvedValue(null),
    sessions: [],
    settings: null,
    documents: [],
    selectedDocumentIds: [],
    selectedDocuments: [],
    openContext: vi.fn(),
    openConceptDetail: vi.fn(),
    showKnowledgeContext: vi.fn(),
    receiveKnowledgeContext: vi.fn(),
    clearKnowledgeContext: vi.fn(),
    showSourceContext: vi.fn(),
    clearDocumentScope: vi.fn(),
    activeLibrary: null,
    openLibrarySetup: vi.fn(),
    startDocumentImport: vi.fn(),
    documentImporting: false,
    libraryReady: true,
  };
}

beforeEach(() => {
  localStorage.clear();
  useHandoffStore.setState({ chatDraft: null });
  hoisted.ctx = shellContext();
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  localStorage.clear();
});

describe("ChatPage initialization", () => {
  it("keeps an in-memory draft when settings finish loading", async () => {
    const view = render(<MemoryRouter><ChatPage /></MemoryRouter>);
    const composer = screen.getByRole("textbox", { name: "消息" });

    fireEvent.change(composer, { target: { value: "帮我安排学习路线" } });
    localStorage.removeItem("bobodan:draft:new");

    hoisted.ctx.settings = {
      default_provider: "deepseek",
      providers: [{ name: "deepseek", configured: true, model: "deepseek-chat" }],
      skills: [],
      preferences: {
        revision: 0,
        assistant: { display_name: "Bobodan", answer_depth: "standard" },
        memory: { enabled: true },
      },
    };
    view.rerender(<MemoryRouter><ChatPage /></MemoryRouter>);

    await waitFor(() => expect(composer).toHaveValue("帮我安排学习路线"));
  });
});

import { streamChat } from "../lib/api";
vi.mock("../lib/api", async (original) => ({ ...await original<typeof import("../lib/api")>(), streamChat: vi.fn() }));

// R01/F05（2026-09-28 审查）：run_failed 之前服务端已经分配了会话，重试必须**沿用它**。
// 修之前：重试走的是路由参数（此时还是空的），于是又开了一个新会话，上一轮的历史找不回来。
it("R01: retry after run_failed preserves the allocated chat session", async () => {
  hoisted.ctx.activeLibrary = { library_id: "audit-library" };
  vi.mocked(streamChat).mockImplementation(async (...args) => {
    args[4]({ event: "run_started", data: { run_id: "r", chat_session_id: "allocated-session" } });
    throw new Error("provider unavailable");
  });
  render(<MemoryRouter initialEntries={["/chat"]}><ChatPage /></MemoryRouter>);
  const composer = screen.getByRole("textbox", { name: "消息" });
  fireEvent.change(composer, { target: { value: "请解释这段内容" } });
  fireEvent.submit(composer.closest("form")!);
  await waitFor(() => expect(streamChat).toHaveBeenCalledTimes(1), { timeout: 700 });
  await waitFor(() => expect(screen.getByRole("button", { name: "发送" })).toBeInTheDocument(), { timeout: 700 });

  fireEvent.click(screen.getByRole("button", { name: "重新发送本轮" }));
  await waitFor(() => expect(streamChat).toHaveBeenCalledTimes(2), { timeout: 700 });

  expect(vi.mocked(streamChat).mock.calls[1][1]).toBe("allocated-session");
  expect(vi.mocked(streamChat).mock.calls[1][3]).toEqual(expect.objectContaining({ retryFailed: true }));
});
