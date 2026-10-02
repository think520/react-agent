import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api, streamChat } from "../lib/api";
import type { PracticeSession } from "../types";
import { PracticePage } from "./PracticePage";

const hoisted = vi.hoisted(() => ({
  ctx: {} as Record<string, unknown>,
  navigate: vi.fn(),
  streamChat: vi.fn(),
  /** W1 E5 用例需要"没有练习 id"的创建视图，其余用例固定 7。 */
  practiceId: "7",
}));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return {
    ...actual,
    useNavigate: () => hoisted.navigate,
    useOutletContext: () => hoisted.ctx,
    useParams: () => ({ practiceSessionId: hoisted.practiceId }),
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
      startPractice: vi.fn(),
      streamQuestionPipeline: vi.fn(),
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
  hoisted.practiceId = "7";
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

// W1 E15：小结不能与事实相反 —— partial 不进错题本，就不能说"错题已加入复习队列"。
it("只有 partial 的一轮，小结不说'错题已入队'", async () => {
  vi.mocked(api.practice).mockResolvedValue({
    ...session,
    status: "completed",
    attempts: [{
      question_id: 11, user_answer: "大概是 RAG", is_correct: false,
      verdict: "partial", feedback: "基本正确。",
    }],
    progress: { answered: 1, total: 1, correct: 0, partial: 1, wrong: 0, current_index: 1, completed: true },
  } as never);

  render(<PracticePage />);

  expect(await screen.findByText(/另有 1 题基本正确/)).toBeTruthy();
  expect(screen.getByText(/没有进错题本/)).toBeTruthy();
  expect(screen.queryByText(/错题和薄弱点已经加入复习队列/)).toBeNull();
});

it("真的答错时才说错题已入队", async () => {
  vi.mocked(api.practice).mockResolvedValue({
    ...session,
    status: "completed",
    attempts: [{
      question_id: 11, user_answer: "不知道", is_correct: false,
      verdict: "incorrect", feedback: "参考答案：…",
    }],
    progress: { answered: 1, total: 1, correct: 0, partial: 0, wrong: 1, current_index: 1, completed: true },
  } as never);

  render(<PracticePage />);

  expect(await screen.findByText(/错题和薄弱点已经加入复习队列/)).toBeTruthy();
});

// W1 E14：练习辅导会话要声明自己的类别，否则它会作为普通聊天出现在主会话列表里。
it("辅导对话声明 sessionKind=practice", async () => {
  render(<PracticePage />);
  await screen.findByText("什么是 RAG？");
  fireEvent.click(screen.getByRole("button", { name: "问 AI" }));
  fireEvent.click(screen.getByRole("button", { name: "发送" }));
  await waitFor(() => expect(streamChat).toHaveBeenCalledTimes(1));

  const prefs = vi.mocked(streamChat).mock.calls[0][3] as { sessionKind?: string };
  expect(prefs.sessionKind).toBe("practice");
});

// W1 E5 第二批：勾选逐题生成后走 SSE 管线，**边出边显示**；出完才开练习。
it("逐题生成：边出边显示，出完再开练习", async () => {
  hoisted.practiceId = "";  // 没有练习 id → 渲染"开始一轮练习"创建视图
  let emit: ((event: unknown) => void) | null = null;
  vi.mocked(api.streamQuestionPipeline).mockImplementation(((_body: unknown, onEvent: (event: unknown) => void) => {
    emit = onEvent;
    return new Promise<void>(() => {});
  }) as never);
  vi.mocked(api.startPractice).mockResolvedValue({ practice_session_id: 12 } as never);

  render(<PracticePage />);
  fireEvent.change(await screen.findByLabelText(/想练习什么/), { target: { value: "极限" } });
  fireEvent.click(screen.getByLabelText(/逐题生成/));
  fireEvent.submit(document.querySelector("form.practice-create")!);

  await waitFor(() => expect(api.streamQuestionPipeline).toHaveBeenCalled());
  const [payload] = vi.mocked(api.streamQuestionPipeline).mock.calls[0] as unknown as [{ topic: string }];
  expect(payload.topic).toBe("极限");

  await act(async () => {
    emit?.({
      event: "quiz_question_emitted", index: 0, total: 2, question_id: 11,
      question: { id: 11, question: "第一题", type: "single_choice", options: ["A. 甲", "B. 乙"], difficulty: "hard" },
    });
  });
  expect(await screen.findByText("第一题")).toBeTruthy();
  expect(screen.getByText(/已就绪 1 道/)).toBeTruthy();
  // W1 E5：实时列表是**可读卡片**（题型 + 难度 + 选项），不是只列一行题干。
  expect(screen.getByText("单选题")).toBeTruthy();
  expect(screen.getByText("较难难度")).toBeTruthy();
  expect(screen.getByText("A. 甲")).toBeTruthy();
  expect(screen.getByText("B. 乙")).toBeTruthy();

  await act(async () => {
    emit?.({ event: "pipeline_done", question_ids: [11, 12], total: 2 });
  });
  await waitFor(() => expect(api.startPractice).toHaveBeenCalledWith(undefined, [11, 12], "practice"));
});
