import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useHandoffStore } from "../stores/handoffStore";
import { ChatPage } from "./ChatPage";

const hoisted = vi.hoisted(() => ({
  ctx: {} as Record<string, unknown>,
  skipInteraction: vi.fn(),
}));

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
vi.mock("../lib/api", async (original) => {
  const actual = await original<typeof import("../lib/api")>();
  return {
    ...actual,
    streamChat: vi.fn(),
    api: { ...actual.api, skipInteraction: hoisted.skipInteraction },
  };
});

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

// W1 E11：回答被输出上限截断 → 说清楚，并给出"接着写"。
it("被截断的回答会提示，并且能接着写", async () => {
  hoisted.ctx.activeLibrary = { library_id: "audit-library" };
  vi.mocked(streamChat).mockImplementation(async (...args) => {
    args[4]({ event: "run_started", data: { run_id: "r", chat_session_id: "s1" } });
    args[4]({ event: "answer_truncated", data: { continuing: false, continues: 2 } });
    args[4]({ event: "run_completed", data: { chat_session_id: "s1", termination_reason: "final_answer" } });
  });
  render(<MemoryRouter initialEntries={["/chat"]}><ChatPage /></MemoryRouter>);

  const composer = screen.getByRole("textbox", { name: "消息" });
  fireEvent.change(composer, { target: { value: "写一篇很长的回答" } });
  fireEvent.submit(composer.closest("form")!);

  expect(await screen.findByText(/被输出长度上限截断了/)).toBeTruthy();
  // 「接着写」在流收尾前是禁用的（sending 还没清）—— 等它可点再点。
  const continueButton = screen.getByRole("button", { name: "接着写" });
  await waitFor(() => expect(continueButton).toBeEnabled());
  fireEvent.click(continueButton);

  await waitFor(() => expect(streamChat).toHaveBeenCalledTimes(2));
  expect(vi.mocked(streamChat).mock.calls[1][0]).toContain("继续写");
});

it("续写进行中不打断用户（不提示）", async () => {
  hoisted.ctx.activeLibrary = { library_id: "audit-library" };
  vi.mocked(streamChat).mockImplementation(async (...args) => {
    args[4]({ event: "run_started", data: { run_id: "r", chat_session_id: "s2" } });
    args[4]({ event: "answer_truncated", data: { continuing: true, continues: 1 } });
  });
  render(<MemoryRouter initialEntries={["/chat"]}><ChatPage /></MemoryRouter>);

  const composer = screen.getByRole("textbox", { name: "消息" });
  fireEvent.change(composer, { target: { value: "继续写" } });
  fireEvent.submit(composer.closest("form")!);

  await waitFor(() => expect(streamChat).toHaveBeenCalledTimes(1));
  expect(screen.queryByText(/被输出长度上限截断了，没有写完/)).toBeNull();
});

// W1 E4：跳过 ask_user 卡片 → 关闭交互 **并且**唤醒暂停的那一轮（补回上一轮撤掉的用例）。
it("跳过选择会恢复暂停的那一轮", async () => {
  hoisted.ctx.activeLibrary = { library_id: "audit-library" };
  hoisted.skipInteraction.mockResolvedValue({ chat_session_id: "s1", artifact: {} });
  vi.mocked(streamChat).mockImplementation(async (...args) => {
    args[4]({ event: "run_started", data: { run_id: "r", chat_session_id: "s1" } });
    args[4]({ event: "chat_artifact", data: { artifact: {
      type: "ask_user", artifact_id: "i1", status: "awaiting_input",
      questions: [{ id: "q1", prompt: "先学哪个？", options: ["甲", "乙"] }],
    } } });
  });
  render(<MemoryRouter initialEntries={["/chat"]}><ChatPage /></MemoryRouter>);

  const composer = screen.getByRole("textbox", { name: "消息" });
  fireEvent.change(composer, { target: { value: "帮我安排一下" } });
  fireEvent.submit(composer.closest("form")!);

  const skip = await screen.findByRole("button", { name: "先不答，跳过" }, { timeout: 2000 });
  await waitFor(() => expect(skip).toBeEnabled(), { timeout: 2000 });
  fireEvent.click(skip);

  await waitFor(() => expect(hoisted.skipInteraction).toHaveBeenCalledWith("i1", "s1"), { timeout: 2000 });
  await waitFor(() => expect(streamChat).toHaveBeenCalledTimes(2), { timeout: 2000 });
  expect(vi.mocked(streamChat).mock.calls[1][3]).toEqual(
    expect.objectContaining({ resumeInteractionId: "i1" }),
  );
}, 15000);
