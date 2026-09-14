import { expect, test, type Page } from "@playwright/test";

/**
 * E18 question bank: the Practice view that lists every generated question with
 * its status, bookmarks it, and starts practice from a single question. Follows
 * the suite convention (see interaction.spec.ts): every /api call is mocked with
 * a precise pattern, so this needs no backend and no live model.
 */

const SHELF = {
  attribution: { kind: "local_extension", sources: [] },
};

const WRONG_QUESTION = {
  ...SHELF,
  id: 3, type: "short_answer", type_label: "简答题",
  question: "为什么 Dijkstra 不能处理负权边？", options: [],
  concepts: ["图论"], difficulty: "medium", source: "算法导论",
  created_at: "2026-09-08T00:00:00+00:00",
  state: "incorrect", bookmarked: true, bookmarked_at: "2026-09-09T00:00:00+00:00",
  last_attempt: {
    attempt_id: 11, user_answer: "因为有环", verdict: "incorrect",
    is_correct: false, feedback: "负权会让已确定的路径变短。",
    answered_at: "2026-09-08T01:00:00+00:00",
  },
  answer: "负权边会破坏贪心的前提。",
  explanation: "Dijkstra 假设已确定的最短距离不会再被更新。",
};

const CORRECT_QUESTION = {
  ...SHELF,
  id: 2, type: "single_choice", type_label: "单选题",
  question: "下面哪个排序是稳定的？", options: ["快排", "归并"],
  concepts: ["排序"], difficulty: "easy", source: "算法导论",
  created_at: "2026-09-07T00:00:00+00:00",
  state: "correct", bookmarked: false, bookmarked_at: "",
  last_attempt: {
    attempt_id: 10, user_answer: "归并", verdict: "correct",
    is_correct: true, feedback: "正确。", answered_at: "2026-09-07T01:00:00+00:00",
  },
  answer: "归并", explanation: "",
};

const UNANSWERED_QUESTION = {
  ...SHELF,
  id: 1, type: "true_false", type_label: "判断题",
  question: "BFS 一定能求出最短路径。", options: [],
  concepts: ["图论"], difficulty: "hard", source: "图论讲义",
  created_at: "2026-09-06T00:00:00+00:00",
  state: "unanswered", bookmarked: false, bookmarked_at: "",
  last_attempt: null,
};

const ALL_QUESTIONS = [WRONG_QUESTION, CORRECT_QUESTION, UNANSWERED_QUESTION];

const json = (body: unknown) => ({ contentType: "application/json", body: JSON.stringify(body) });

function settingsPayload() {
  return {
    workspace_name: "测试空间",
    default_provider: "deepseek",
    providers: [{ name: "deepseek", configured: true, model: "deepseek-chat" }],
    search_providers: [{ name: "auto", configured: true }],
    mcp_enabled: false,
    skills: [],
    preferences: {
      schema_version: 4,
      revision: 0,
      assistant: { display_name: "Bobodan", teaching_style: "guided", answer_depth: "standard", feedback_strength: "gentle" },
      user: { display_name: "", profile: "", long_term_goal: "" },
      appearance: { reading_font: "jin-kai", body_font_size: 16, content_width: 720, paper_texture: true, session_density: "comfortable", motion: "system" },
      ai: { default_provider: "deepseek", task_providers: { wiki_discovery: "default", wiki_drafting: "default" } },
      wiki: { default_mode: "standard", guide_completed: false, budget: { max_requests: 24, max_input_tokens: 300000, max_output_tokens: 40000 } },
      memory: { enabled: true },
      search: { provider: "auto", permission: "ask", jina_fallback: true },
      skills: { enabled_names: [] },
    },
  };
}

async function mockShell(page: Page) {
  await page.addInitScript(() => localStorage.setItem("bobodan:onboarding:v1", "complete"));
  await page.route("**/api/health", (route) => route.fulfill(json({ ok: true })));
  await page.route("**/api/settings", (route) => route.fulfill(json(settingsPayload())));
  await page.route("**/api/libraries", (route) => route.fulfill(json({
    active_library_id: "library-1",
    libraries: [{ library_id: "library-1", name: "测试资料库", created_at: "", last_opened_at: "", active: true, available: true }],
  })));
  await page.route("**/api/chat/sessions", (route) => route.fulfill(json({ sessions: [] })));
  await page.route("**/api/kb/documents?collection=all", (route) => route.fulfill(json({ documents: [] })));
  await page.route("**/api/kb/documents?collection=material", (route) => route.fulfill(json({ documents: [] })));
  await page.route("**/api/kb/wiki/coverage", (route) => route.fulfill(json({ documents: [], counts: { uncovered: 0, partial: 0, covered: 0, stale: 0 } })));
  await page.route("**/api/learning/review-queue", (route) => route.fulfill(json({
    due_concepts: [], wrong_answers: [], weaknesses: [], personalization: [],
  })));
  await page.route("**/api/quiz/sessions/active", (route) => route.fulfill(json({ sessions: [] })));
}

/** One handler for the whole bank surface, dispatched by path and method. */
async function mockBank(page: Page) {
  const state = { bookmarked: new Set<number>([WRONG_QUESTION.id]) };
  const bookmarks: Array<{ question_id: number; bookmarked: boolean }> = [];
  const practices: Array<Record<string, unknown>> = [];

  const item = (question: typeof WRONG_QUESTION) => ({
    ...question,
    bookmarked: state.bookmarked.has(question.id),
    bookmarked_at: state.bookmarked.has(question.id) ? "2026-09-09T00:00:00+00:00" : "",
  });

  await page.route("**/api/quiz/bank**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname.endsWith("/bookmark")) {
      const body = JSON.parse(request.postData() || "{}");
      bookmarks.push(body);
      if (body.bookmarked) state.bookmarked.add(body.question_id);
      else state.bookmarked.delete(body.question_id);
      return route.fulfill(json({ question_id: body.question_id, bookmarked: Boolean(body.bookmarked) }));
    }
    if (url.pathname.endsWith("/practice")) {
      const body = JSON.parse(request.postData() || "{}");
      practices.push(body);
      return route.fulfill(json({ practice_session_id: 42, question_ids: body.question_ids, questions: [] }));
    }
    const filter = url.searchParams.get("state") || "all";
    const difficulty = url.searchParams.get("difficulty");
    const source = url.searchParams.get("source");
    const items = ALL_QUESTIONS.map(item);
    const byState = (entry: typeof WRONG_QUESTION) => {
      if (filter === "incorrect") return entry.state === "incorrect";
      if (filter === "correct") return entry.state === "correct";
      if (filter === "partial") return entry.state === "partial";
      if (filter === "unanswered") return entry.state === "unanswered";
      if (filter === "bookmarked") return entry.bookmarked;
      return true;
    };
    const filtered = items
      .filter(byState)
      .filter((entry) => !difficulty || entry.difficulty === difficulty)
      .filter((entry) => !source || entry.source === source);
    return route.fulfill(json({
      items: filtered,
      total: filtered.length,
      overview: {
        total: items.length,
        unanswered: 1, correct: 1, partial: 0, incorrect: 1,
        bookmarked: state.bookmarked.size,
        by_type: { short_answer: 1, single_choice: 1, true_false: 1 },
        by_difficulty: { easy: 1, medium: 1, hard: 1 },
        by_concept: [{ concept: "图论", count: 2 }, { concept: "排序", count: 1 }],
        by_source: [
          { source: "算法导论", count: 2 },
          { source: "图论讲义", count: 1 },
        ],
      },
      state: filter, limit: 20, offset: 0,
    }));
  });

  await page.route("**/api/quiz/sessions/42", (route) => route.fulfill(json({
    practice_session_id: 42, status: "active", origin: "practice", personalization: [],
    questions: [{
      id: WRONG_QUESTION.id, type: "short_answer", type_label: "简答题",
      question: WRONG_QUESTION.question, options: [], concepts: ["图论"],
      difficulty: "medium", attribution: WRONG_QUESTION.attribution,
    }],
    attempts: [],
    progress: { answered: 0, total: 1, correct: 0, current_index: 0, completed: false },
  })));

  return { bookmarks, practices, state };
}

test("past questions are browsable, filterable and re-practisable", async ({ page }) => {
  await mockShell(page);
  const bank = await mockBank(page);

  await page.goto("/practice");
  await page.getByRole("button", { name: "题库" }).click();
  await page.waitForURL(/\/practice\/bank/);

  const rows = page.locator(".bank-row");
  await expect(rows).toHaveCount(3);
  await expect(rows.first()).toContainText("为什么 Dijkstra 不能处理负权边？");
  await expect(page.locator(".bank-state.incorrect")).toHaveCount(1);
  await expect(page.locator(".bank-state.correct")).toHaveCount(1);
  await expect(page.locator(".bank-state.unanswered")).toHaveCount(1);

  // An unanswered question stays unanswered: no reference answer is rendered.
  const unansweredRow = rows.filter({ hasText: "BFS 一定能求出最短路径" });
  await expect(unansweredRow.locator(".bank-reveal")).toHaveCount(0);
  await expect(rows.filter({ hasText: "Dijkstra" }).locator(".bank-reveal")).toHaveCount(1);

  await page.getByRole("tab", { name: /错题/ }).click();
  await expect(rows).toHaveCount(1);
  await expect(rows.first()).toContainText("Dijkstra");

  await page.getByRole("button", { name: "练这题" }).click();
  await page.waitForURL(/\/practice\/42/);
  expect(bank.practices).toHaveLength(1);
  expect(bank.practices[0]).toMatchObject({ question_ids: [3], state: "all", limit: 5 });
  await expect(page.locator(".question-sheet h2")).toContainText("Dijkstra");
});

test("bookmarking a question goes through the API and flips the row", async ({ page }) => {
  await mockShell(page);
  const bank = await mockBank(page);

  await page.goto("/practice/bank");
  const row = page.locator(".bank-row").filter({ hasText: "BFS 一定能求出最短路径" });
  await expect(row).toContainText("未作答");
  await row.getByRole("button", { name: "收藏" }).click();

  await expect.poll(() => bank.bookmarks.length).toBe(1);
  expect(bank.bookmarks[0]).toEqual({ question_id: 1, bookmarked: true });
  await expect(row.getByRole("button", { name: "已收藏" })).toBeVisible();

  await page.getByRole("tab", { name: /已收藏/ }).click();
  await expect(page.locator(".bank-row")).toHaveCount(2);
});
test("difficulty and material filters narrow the bank and can be practised", async ({ page }) => {
  await mockShell(page);
  const bank = await mockBank(page);

  await page.goto("/practice/bank");
  await expect(page.locator(".bank-row")).toHaveCount(3);

  // 难度 is one of the D2 axes and had no UI before this pass.
  await page.getByRole("button", { name: "按难度筛选" }).click();
  await page.getByRole("option", { name: "简单" }).click();
  await expect(page.locator(".bank-row")).toHaveCount(1);
  await expect(page.locator(".bank-row").first()).toContainText("下面哪个排序是稳定的？");

  await page.getByRole("button", { name: "清除筛选" }).click();
  await expect(page.locator(".bank-row")).toHaveCount(3);

  // 资料 comes from the overview, so the menu is a real list of materials.
  await page.getByRole("button", { name: "按资料筛选" }).click();
  await page.getByRole("option", { name: /图论讲义/ }).click();
  await expect(page.locator(".bank-row")).toHaveCount(1);

  // "Practice what I am looking at" must send the whole filter set, not just state.
  await page.getByRole("button", { name: /练这 1 道题/ }).click();
  await expect.poll(() => bank.practices.length).toBe(1);
  expect(bank.practices[0]).toMatchObject({
    question_ids: [], state: "all", source: "图论讲义", limit: 5,
  });
  await page.waitForURL(/\/practice\/42/);
});
test("a bank question can be handed to chat with its stable id", async ({ page }) => {
  await mockShell(page);
  await mockBank(page);

  await page.goto("/practice/bank");
  const row = page.locator(".bank-row").filter({ hasText: "BFS 一定能求出最短路径" });
  await row.getByRole("button", { name: "问 AI" }).click();

  await page.waitForURL(/\/chat$/);
  // The draft names the id so the agent can read the same question back (D4).
  const composer = page.getByRole("textbox", { name: "消息" });
  await expect(composer).toHaveValue(/question_id=1/);
  await expect(composer).toHaveValue(/BFS 一定能求出最短路径/);
});
