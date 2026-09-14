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
  const sets: Array<{ id: number; name: string; question_ids: number[] }> = [];
  const setPractices: number[][] = [];
  let nextSetId = 1;

  const item = (question: typeof WRONG_QUESTION) => ({
    ...question,
    bookmarked: state.bookmarked.has(question.id),
    bookmarked_at: state.bookmarked.has(question.id) ? "2026-09-09T00:00:00+00:00" : "",
  });

  /** One filter implementation, shared by the list and by set creation. */
  const resolveItems = (params: URLSearchParams) => {
    const filter = params.get("state") || "all";
    const difficulty = params.get("difficulty");
    const source = params.get("source");
    const setId = params.get("set_id");
    const scoped = setId ? sets.find((entry) => String(entry.id) === setId) : undefined;
    return ALL_QUESTIONS.map(item)
      .filter((entry) => {
        if (filter === "incorrect") return entry.state === "incorrect";
        if (filter === "correct") return entry.state === "correct";
        if (filter === "partial") return entry.state === "partial";
        if (filter === "unanswered") return entry.state === "unanswered";
        if (filter === "bookmarked") return entry.bookmarked;
        return true;
      })
      .filter((entry) => !difficulty || entry.difficulty === difficulty)
      .filter((entry) => !source || entry.source === source)
      .filter((entry) => !scoped || scoped.question_ids.includes(entry.id));
  };

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
    const items = resolveItems(new URLSearchParams());
    const filtered = resolveItems(url.searchParams);
    const viewedSet = sets.find((entry) => String(entry.id) === url.searchParams.get("set_id"));
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
      set_id: viewedSet ? viewedSet.id : null,
      set_name: viewedSet ? viewedSet.name : "",
    }));
  });

  // The named practice sets are their own surface (E18 / D2 / D8).
  await page.route("**/api/quiz/sets**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const parts = url.pathname.split("/").filter(Boolean);
    const setId = parts.length > 3 ? Number(parts[3]) : 0;
    const found = sets.find((entry) => entry.id === setId);
    if (request.method() === "GET") {
      return route.fulfill(json({ sets: sets.map((entry) => ({
        id: entry.id,
        name: entry.name,
        created_at: "2026-09-11T00:00:00+00:00",
        updated_at: "2026-09-11T00:00:00+00:00",
        question_count: entry.question_ids.length,
      })) }));
    }
    if (request.method() === "POST" && !setId) {
      const body = JSON.parse(request.postData() || "{}");
      const params = new URLSearchParams();
      if (body.state) params.set("state", body.state);
      if (body.difficulty) params.set("difficulty", body.difficulty);
      if (body.source) params.set("source", body.source);
      const ids = (body.question_ids || []).length
        ? body.question_ids
        : resolveItems(params).map((entry) => entry.id);
      const created = { id: nextSetId++, name: body.name, question_ids: ids };
      sets.push(created);
      return route.fulfill(json({
        set_id: created.id, name: created.name,
        question_ids: ids, question_count: ids.length,
      }));
    }
    if (!found) {
      return route.fulfill(json({ error: { code: "question_set_not_found", message: "missing" } }));
    }
    if (request.method() === "PATCH") {
      found.name = JSON.parse(request.postData() || "{}").name;
      return route.fulfill(json({ set_id: found.id, name: found.name }));
    }
    if (request.method() === "DELETE" && url.pathname.endsWith("/" + found.id)) {
      sets.splice(sets.indexOf(found), 1);
      return route.fulfill(json({ set_id: found.id, deleted: true }));
    }
    if (request.method() === "POST" && url.pathname.endsWith("/items")) {
      const body = JSON.parse(request.postData() || "{}");
      if (!found.question_ids.includes(body.question_id)) found.question_ids.push(body.question_id);
      return route.fulfill(json({ set_id: found.id, question_id: body.question_id }));
    }
    if (request.method() === "DELETE" && url.pathname.includes("/items/")) {
      const questionId = Number(url.pathname.split("/").pop());
      found.question_ids = found.question_ids.filter((id) => id !== questionId);
      return route.fulfill(json({ set_id: found.id, question_id: questionId, removed: true }));
    }
    if (request.method() === "POST" && url.pathname.endsWith("/practice")) {
      setPractices.push([...found.question_ids]);
      return route.fulfill(json({ practice_session_id: 42, question_ids: found.question_ids, questions: [] }));
    }
    return route.fulfill(json({}));
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

  return { bookmarks, practices, state, sets, setPractices };
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
test("a named practice set can be created from a filter and practised", async ({ page }) => {
  await mockShell(page);
  const bank = await mockBank(page);

  await page.goto("/practice/bank");
  await page.getByRole("tab", { name: /错题/ }).click();
  await expect(page.locator(".bank-row")).toHaveCount(1);

  // The panel is a collapsed disclosure while no set exists, so it starts closed.
  await expect(page.locator(".bank-sets")).not.toHaveAttribute("open", "");
  await page.locator(".bank-sets > summary").click();
  await expect(page.locator(".bank-sets")).toHaveAttribute("open", "");

  // D2: the set carries the current filter, not a hand-picked list.
  await page.getByRole("textbox", { name: "练习集名称" }).fill("我的错题集");
  await page.getByRole("button", { name: /存为练习集/ }).click();
  await expect(page.locator(".bank-set-banner")).toContainText("我的错题集");
  expect(bank.sets[0]).toMatchObject({ name: "我的错题集", question_ids: [3] });

  // Viewing a set narrows the bank to it; leaving restores the whole bank.
  await expect(page.locator(".bank-row")).toHaveCount(1);
  await page.getByRole("button", { name: "返回全部题目" }).click();
  await page.getByRole("tab", { name: /全部/ }).click();
  await expect(page.locator(".bank-row")).toHaveCount(3);

  await page.getByRole("button", { name: "练这集" }).click();
  await expect.poll(() => bank.setPractices.length).toBe(1);
  expect(bank.setPractices[0]).toEqual([3]);
  await page.waitForURL(/\/practice\/42/);
});

test("the bank rows are readable and the question follows the reading size", async ({ page }) => {
  await mockShell(page);
  await mockBank(page);
  await page.goto("/practice/bank");
  await expect(page.locator(".bank-row")).toHaveCount(3);

  // DESIGN.md §5 floors: helper text >= 12px, nothing under it inside a row.
  const smallest = await page.locator(".bank-row").first().evaluate((row) => {
    let min = Number.POSITIVE_INFINITY;
    row.querySelectorAll("*").forEach((el) => {
      const own = Array.from(el.childNodes)
        .filter((node) => node.nodeType === 3)
        .map((node) => (node.textContent || "").trim())
        .join("");
      if (!own) return;
      const size = parseFloat(getComputedStyle(el).fontSize);
      if (size < min) min = size;
    });
    return min;
  });
  expect(smallest).toBeGreaterThanOrEqual(12);

  // The question reads at the user reading size, not a hard-coded value.
  const fixed = await page.locator(".bank-row h3").first().evaluate((el) => parseFloat(getComputedStyle(el).fontSize));
  await page.evaluate(() => document.documentElement.style.setProperty("--body-font-size", "18px"));
  const bumped = await page.locator(".bank-row h3").first().evaluate((el) => parseFloat(getComputedStyle(el).fontSize));
  expect(bumped).toBe(18);
  expect(bumped).toBeGreaterThan(fixed - 1);

  // Rows stay sheets, not voids, and the first one is reachable without scrolling.
  // Narrow viewports stack the filter row and the row actions, so the caps are
  // per-breakpoint; they still catch the previous 208px/460px regression.
  const wide = (page.viewportSize()?.width ?? 0) >= 1280;
  const rowBox = await page.locator(".bank-row").first().boundingBox();
  expect(rowBox!.height).toBeLessThanOrEqual(wide ? 200 : 340);
  expect(rowBox!.y).toBeLessThanOrEqual(wide ? 520 : 700);

  // Answers sit behind one deliberate affordance and are labelled when opened.
  // Fixture texts from WRONG_QUESTION / UNANSWERED_QUESTION above.
  const answered = page.locator(".bank-row").filter({ hasText: "为什么 Dijkstra 不能处理负权边？" });
  const unanswered = page.locator(".bank-row").filter({ hasText: "BFS 一定能求出最短路径。" });
  await expect(answered).toHaveCount(1);
  await expect(unanswered).toHaveCount(1);
  await expect(unanswered.locator(".bank-answer")).toHaveCount(0);
  await answered.getByText("查看参考答案与解析").click();
  await expect(answered.locator(".bank-answer-label").first()).toHaveText("你的答案");
  await expect(answered.locator(".bank-answer-label").last()).toHaveText("参考答案");
});
test("the practice page can search for existing questions instead of authoring them", async ({ page }) => {
  await mockShell(page);
  const bodies: Array<Record<string, unknown>> = [];
  await page.route("**/api/quiz/questions", async (route) => {
    bodies.push(JSON.parse(route.request().postData() || "{}"));
    return route.fulfill(json({
      status: "web_consent_required",
      query: "RAG 练习",
      reason: "搜现成的题必须联网读取公开资料。确认后 Bobodan 会搜索并只提取页面上已经存在的题目，不会自己编写。",
      suggested_query: null,
    }));
  });

  await page.goto("/practice");
  await page.getByRole("tab", { name: "搜现成的题" }).click();
  await page.locator("#practice-topic").fill("RAG 练习");
  await page.getByRole("button", { name: "联网搜题" }).click();

  // S6 / D9: the mode travels with the request, so the server never guesses.
  await expect.poll(() => bodies.length).toBe(1);
  expect(bodies[0]).toMatchObject({ mode: "search", query: "RAG 练习" });
  await expect(page.locator(".practice-web-consent")).toContainText("搜现成的题");
});
test("the bank exports Markdown and a backup file", async ({ page }) => {
  await mockShell(page);
  await mockBank(page);
  await page.route("**/api/quiz/export/markdown**", (route) => route.fulfill(json({
    markdown: "---\ntitle: 题库导出\n---\n\n## 错题（1）\n1. **Dijkstra**\n",
    count: 1,
    excluded_third_party: 1,
  })));
  await page.route("**/api/quiz/export/backup", (route) => route.fulfill(json({
    backup: { kind: "bobodan-question-bank", schema_version: 1, tables: { questions: [] } },
  })));

  await page.goto("/practice/bank");

  const markdownDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "导出 Markdown" }).click();
  expect((await markdownDownload).suggestedFilename()).toMatch(/\.md$/);
  // D9: excluding third-party questions is announced, not silent.
  await expect(page.locator(".notice-center")).toContainText("第三方");

  const backupDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "备份" }).click();
  expect((await backupDownload).suggestedFilename()).toMatch(/\.json$/);
});

test("restoring a backup warns before replacing the bank", async ({ page }) => {
  await mockShell(page);
  await mockBank(page);
  const bodies: Array<Record<string, unknown>> = [];
  await page.route("**/api/quiz/export/restore", async (route) => {
    bodies.push(JSON.parse(route.request().postData() || "{}"));
    return route.fulfill(json({ restored: { questions: 4 } }));
  });

  await page.goto("/practice/bank");
  await page.locator(".bank-restore input[type=file]").setInputFiles({
    name: "bank.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify({
      kind: "bobodan-question-bank", schema_version: 1, tables: {},
    })),
  });

  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("覆盖整个题库");
  await dialog.getByRole("button", { name: "覆盖题库" }).click();

  await expect.poll(() => bodies.length).toBe(1);
  expect((bodies[0].backup as Record<string, unknown>).kind).toBe("bobodan-question-bank");
});
