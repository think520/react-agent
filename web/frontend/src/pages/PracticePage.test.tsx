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
