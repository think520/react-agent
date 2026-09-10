import { expect, test, type Page } from "@playwright/test";

/**
 * E4 interaction flow: the card, the answer, and the resumed turn. Follows the
 * suite convention (see app.spec.ts): every /api call is mocked with a precise
 * pattern and the SSE stream is replayed deterministically, so this needs no
 * backend and no live model.
 */

const QUESTIONS = [{ id: "q1", prompt: "你系统学算法主要为了什么？", options: ["求职面试", "打牢基础"] }];

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

const json = (body: unknown) => ({ contentType: "application/json", body: JSON.stringify(body) });

const PAUSED_STREAM = [
  'event: run_started\ndata: {"run_id":"r1","chat_session_id":"s1"}\n\n',
  'event: status\ndata: {"phase":"completed","message":"等待你做出选择","tool_name":"ask_user"}\n\n',
  `event: chat_artifact\ndata: ${JSON.stringify({ artifact: { type: "ask_user", artifact_id: "i1", status: "awaiting_input", questions: QUESTIONS } })}\n\n`,
  'event: run_completed\ndata: {"chat_session_id":"s1","termination_reason":"paused"}\n\n',
].join("");

const CONTINUATION_STREAM = [
  'event: run_started\ndata: {"run_id":"r2","chat_session_id":"s1"}\n\n',
  'event: message_delta\ndata: {"content":"好的，我按求职面试方向安排路线。"}\n\n',
  'event: run_completed\ndata: {"chat_session_id":"s1","termination_reason":"final_answer"}\n\n',
].join("");

const ANSWERED_ARTIFACT = {
  type: "ask_user", artifact_id: "i1", status: "graded", closure: "answered",
  questions: QUESTIONS, answers: [{ id: "q1", answer: "求职面试" }],
};

const SESSION_BASE = {
  chat_session_id: "s1", name: "测试会话", name_source: "fallback",
  created_at: "2026-09-10T00:00:00+00:00", last_active: "2026-09-10T00:00:00+00:00",
  provider_name: "deepseek", model_name: "test",
};

/** Right after the paused run: the card is still open. */
const SESSION_PAUSED = {
  ...SESSION_BASE, message_count: 2,
  messages: [
    { role: "user", content: "帮我安排学习路线" },
    { role: "assistant", content: "问题卡已经在你那边了。", artifacts: [{ type: "ask_user", artifact_id: "i1", status: "awaiting_input", closure: "", questions: QUESTIONS }] },
  ],
};

/** After the answer: resolved in place, followed by the resumed turn. */
const SESSION_ANSWERED = {
  ...SESSION_BASE, message_count: 3,
  messages: [
    { role: "user", content: "帮我安排学习路线" },
    { role: "assistant", content: "问题卡已经在你那边了。", artifacts: [ANSWERED_ARTIFACT] },
    { role: "assistant", content: "好的，我按求职面试方向安排路线。" },
  ],
};

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
}

test("answering the card resumes the turn without inventing a user bubble", async ({ page }) => {
  await mockShell(page);
  const answerBodies: Array<Record<string, unknown>> = [];
  let answered = false;

  await page.route("**/api/chat/runs", async (route) => {
    const body = JSON.parse(route.request().postData() || "{}");
    await route.fulfill({
      contentType: "text/event-stream",
      body: body.resume_interaction_id ? CONTINUATION_STREAM : PAUSED_STREAM,
    });
  });
  await page.route("**/api/chat/interactions/i1/answer", async (route) => {
    answerBodies.push(JSON.parse(route.request().postData() || "{}"));
    answered = true;
    await route.fulfill(json({ chat_session_id: "s1", artifact: ANSWERED_ARTIFACT }));
  });
  await page.route("**/api/chat/sessions/s1", (route) => route.fulfill(
    json(answered ? SESSION_ANSWERED : SESSION_PAUSED),
  ));

  await page.goto("/chat");
  const composer = page.getByRole("textbox", { name: "消息" });
  await composer.fill("帮我安排学习路线");
  await composer.press("Enter");

  // The run assigns the session id and the app then navigates + remounts.
  await page.waitForURL(/\/chat\/s1/, { timeout: 15000 });
  const card = page.locator(".ask-user-card");
  await expect(card).toBeVisible();
  await expect(card).toContainText("你系统学算法主要为了什么？");

  // Exactly the original message: the card answer must never add a user bubble.
  await expect(page.locator(".user-message")).toHaveCount(1);
  await card.getByRole("button", { name: "求职面试" }).click();
  await card.getByRole("button", { name: "提交" }).click();

  await expect.poll(() => answerBodies.length).toBe(1);
  expect(answerBodies[0]).toMatchObject({ chat_session_id: "s1", answers: [{ id: "q1", answer: "求职面试" }] });

  // The paused turn continues, and the answer is not a user message.
  await expect(page.locator(".assistant-message").last()).toContainText("我按求职面试方向安排路线");
  await expect(page.locator(".ask-user-card")).toContainText("已回答");
  await expect(page.locator(".ask-user-card")).toContainText("求职面试");
  await expect(page.locator(".user-message")).toHaveCount(1);
});

test("a skipped card says it was skipped instead of claiming an answer", async ({ page }) => {
  await mockShell(page);
  await page.route("**/api/chat/sessions/s1", (route) => route.fulfill(json({
    ...SESSION_BASE, message_count: 2,
    messages: [
      { role: "user", content: "帮我安排学习路线" },
      {
        role: "assistant", content: "问题卡已经在你那边了。",
        artifacts: [{ type: "ask_user", artifact_id: "i1", status: "graded", closure: "skipped_by_next_message", questions: QUESTIONS, answers: [], outcome: { skipped: true } }],
      },
    ],
  })));

  await page.goto("/chat/s1");
  const card = page.locator(".ask-user-card");
  await expect(card).toContainText("没有作答，已跳过");
  await expect(card).toContainText("未回答");
  await expect(card).not.toContainText("已回答");
});
