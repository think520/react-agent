import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api, streamChat } from "../lib/api";
import type { PracticeSession } from "../types";
import { PracticePage } from "./PracticePage";

const hoisted = vi.hoisted(() => ({
  ctx: {} as Record<string, unknown>,
  navigate: vi.fn(),
  streamChat: vi.fn(),
}));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return {
    ...actual,
    useNavigate: () => hoisted.navigate,
    useOutletContext: () => hoisted.ctx,
    useParams: () => ({ practiceSessionId: "7" }),
  };
});

vi.mock("../lib/motion", () => ({ prefersReducedMotion: true }));

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return {
    ...actual,
    streamChat: hoisted.streamChat,
    api: {
      ...actual.api,
      practice: vi.fn(),
      generateSessionTitle: vi.fn(),
    },
  };
});

const session: PracticeSession = {
  practice_session_id: 7,
  status: "active",
  origin: "practice",
  questions: [{
    id: 11,
    type: "short_answer",
    type_label: "简答题",
    question: "什么是 RAG？",
    options: [],
    concepts: ["RAG"],
  }],
  attempts: [],
  progress: { answered: 0, total: 1, correct: 0, current_index: 0, completed: false },
};

beforeEach(() => {
  hoisted.ctx = {
    activeLibrary: { library_id: "library-a" },
    refreshSessions: vi.fn().mockResolvedValue(undefined),
    selectedDocumentIds: ["doc-1"],
    selectedDocuments: [],
  };
  vi.mocked(api.practice).mockResolvedValue(session);
  vi.mocked(api.generateSessionTitle).mockResolvedValue({} as never);
  vi.mocked(streamChat).mockImplementation(async (...args) => {
    const onEvent = args[4];
    onEvent({ event: "run_started", data: { run_id: "run-1", chat_session_id: "tutor-session-1" } });
    onEvent({ event: "run_completed", data: { chat_session_id: "tutor-session-1", termination_reason: "final_answer" } });
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("PracticePage AI tutor", () => {
  it("reuses the same chat session for follow-up questions on one quiz question", async () => {
    render(<PracticePage />);
    await screen.findByText("什么是 RAG？");
    fireEvent.click(screen.getByRole("button", { name: "问 AI" }));

    fireEvent.click(screen.getByRole("button", { name: "发送" }));
    await waitFor(() => expect(streamChat).toHaveBeenCalledTimes(1));
    expect(vi.mocked(streamChat).mock.calls[0][1]).toBeUndefined();

    fireEvent.click(screen.getByRole("button", { name: "发送" }));
    await waitFor(() => expect(streamChat).toHaveBeenCalledTimes(2));
    expect(vi.mocked(streamChat).mock.calls[1][1]).toBe("tutor-session-1");
  });
});

// R11/F10（2026-09-28 审查）：辅导会话关联原来只存在组件 ref 里，重新挂载就没了。
beforeEach(() => {
  window.sessionStorage.clear();
});

it("R11: reuses tutor session after remounting the same practice", async () => {
  const view = render(<PracticePage />);
  await screen.findByText("什么是 RAG？");
  fireEvent.click(screen.getByRole("button", { name: "问 AI" }));
  fireEvent.click(screen.getByRole("button", { name: "发送" }));
  await waitFor(() => expect(streamChat).toHaveBeenCalledTimes(1));

  view.unmount();
  render(<PracticePage />);
  await screen.findByText("什么是 RAG？");
  fireEvent.click(screen.getByRole("button", { name: "问 AI" }));
  fireEvent.click(screen.getByRole("button", { name: "发送" }));
  await waitFor(() => expect(streamChat).toHaveBeenCalledTimes(2));

  expect(vi.mocked(streamChat).mock.calls[1][1]).toBe("tutor-session-1");
});

it("isolates tutor sessions for identical practice and question IDs in different libraries", async () => {
  const view = render(<PracticePage />);
  await screen.findByText("什么是 RAG？");
  fireEvent.click(screen.getByRole("button", { name: "问 AI" }));
  fireEvent.click(screen.getByRole("button", { name: "发送" }));
  await waitFor(() => expect(streamChat).toHaveBeenCalledTimes(1));
  view.unmount();

  hoisted.ctx.activeLibrary = { library_id: "library-b" };
  const other = render(<PracticePage />);
  await screen.findByText("什么是 RAG？");
  fireEvent.click(screen.getByRole("button", { name: "问 AI" }));
  fireEvent.click(screen.getByRole("button", { name: "发送" }));
  await waitFor(() => expect(streamChat).toHaveBeenCalledTimes(2));
  expect(vi.mocked(streamChat).mock.calls[1][1]).toBeUndefined();
  other.unmount();

  hoisted.ctx.activeLibrary = { library_id: "library-a" };
  render(<PracticePage />);
  await screen.findByText("什么是 RAG？");
  fireEvent.click(screen.getByRole("button", { name: "问 AI" }));
  fireEvent.click(screen.getByRole("button", { name: "发送" }));
  await waitFor(() => expect(streamChat).toHaveBeenCalledTimes(3));
  expect(vi.mocked(streamChat).mock.calls[2][1]).toBe("tutor-session-1");
});
