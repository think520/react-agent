import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../lib/api";
import { ReviewPage } from "./ReviewPage";

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return {
    ...actual,
    api: { ...actual.api, reviewQueue: vi.fn() },
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
      weaknesses: [{ concept: "最短路径", reason: "连续两次答错" }],
      wrong_total: 1,
      personalization: [],
      next_review: null,
    });

    renderPage();

    expect(await screen.findByText(/错题表示最近一次未答对的题/)).toBeInTheDocument();
    expect(screen.getByText(/薄弱点来自更长期的表现汇总/)).toBeInTheDocument();
  });
});
