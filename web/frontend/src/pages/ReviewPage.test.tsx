import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../lib/api";
import { ReviewPage } from "./ReviewPage";

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return {
    ...actual,
    api: {
      ...actual.api,
      reviewQueue: vi.fn(),
      generateWrongAnswerVariant: vi.fn(),
      generateQuestions: vi.fn(),
      startPractice: vi.fn(),
    },
  };
});

function renderPage() {
  return render(<MemoryRouter><ReviewPage /></MemoryRouter>);
}

beforeEach(() => {
  vi.mocked(api.reviewQueue).mockResolvedValue({
    due_concepts: [],
    wrong_answers: [],
    weaknesses: [],
    wrong_total: 0,
    personalization: [],
    next_review: {
      concept: "Dijkstra 最短路径",
      status: "learning",
      next_review: "2026-09-26T02:00:00Z",
    },
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("ReviewPage queue explanations", () => {
  it("shows the next scheduled review when nothing is due", async () => {
    renderPage();

    expect(await screen.findByText("今天没有到期内容")).toBeInTheDocument();
    expect(screen.getByText(/下一次复习：.*Dijkstra 最短路径/)).toBeInTheDocument();
  });

  it("explains why wrong answers and weaknesses can overlap", async () => {
    vi.mocked(api.reviewQueue).mockResolvedValue({
      due_concepts: [],
      wrong_answers: [{ question: "为什么需要松弛操作？", question_id: 1 }],
      // 真契约：reason 由后端算出来（W1 E9）。以前这里的 mock 是自己编的，
      // 于是"界面能显示后端给的原因"这件事从来没被验证过。
      weaknesses: [{ concept: "最短路径", reason: "近 5 次作答里错了 3 次", total_attempts: 5, wrong_count: 3, error_rate: 0.6 }],
      wrong_total: 1,
      personalization: [],
      next_review: null,
    });

    renderPage();

    expect(await screen.findByText(/错题表示最近一次未答对的题/)).toBeInTheDocument();
    expect(screen.getByText(/薄弱点来自更长期的表现汇总/)).toBeInTheDocument();
    // 后端给的原因要真的上屏（不是那句兜底话）。
    expect(screen.getByText("近 5 次作答里错了 3 次")).toBeInTheDocument();
    expect(screen.queryByText("建议进行针对性练习")).toBeNull();
  });

  it("后端没给原因时才退回兜底说明（老数据）", async () => {
    vi.mocked(api.reviewQueue).mockResolvedValue({
      due_concepts: [],
      wrong_answers: [],
      weaknesses: [{ concept: "最短路径" }],
      wrong_total: 0,
      personalization: [],
      next_review: null,
    });

    renderPage();

    expect(await screen.findByText("建议进行针对性练习")).toBeInTheDocument();
  });
});

describe("到期复习的变式通道（W1 E9）", () => {
  it("带着'最近一次答错'的到期项走变式通道，而不是重放原题", async () => {
    vi.mocked(api.reviewQueue).mockResolvedValue({
      due_concepts: [{ concept: "最短路径", status: "learning", question_ids: [7], last_attempt_id: 11 }],
      wrong_answers: [],
      weaknesses: [],
      wrong_total: 0,
      personalization: [],
      next_review: null,
    });
    vi.mocked(api.generateWrongAnswerVariant).mockResolvedValue({ question_id: 42, mode: "variant" } as never);
    vi.mocked(api.startPractice).mockResolvedValue({ practice_session_id: 9 } as never);

    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /开始复习/ }));

    await waitFor(() => expect(api.generateWrongAnswerVariant).toHaveBeenCalledWith(11));
    expect(api.startPractice).toHaveBeenCalledWith(undefined, [42], "review");
    expect(api.generateQuestions).not.toHaveBeenCalled();
  });

  it("没有作答历史的新概念才按概念出题", async () => {
    vi.mocked(api.reviewQueue).mockResolvedValue({
      due_concepts: [{ concept: "新概念", status: "learning", question_ids: [], last_attempt_id: null }],
      wrong_answers: [],
      weaknesses: [],
      wrong_total: 0,
      personalization: [],
      next_review: null,
    });
    vi.mocked(api.generateQuestions).mockResolvedValue({ question_ids: [5] } as never);
    vi.mocked(api.startPractice).mockResolvedValue({ practice_session_id: 9 } as never);

    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /开始复习/ }));

    await waitFor(() => expect(api.generateQuestions).toHaveBeenCalledWith("新概念"));
    expect(api.generateWrongAnswerVariant).not.toHaveBeenCalled();
  });
});
