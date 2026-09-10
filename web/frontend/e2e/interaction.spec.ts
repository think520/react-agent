import { expect, test, type Page } from "@playwright/test";

/**
 * E4 interaction flow, verified in a real browser against deterministic SSE
 * replays (tests/README.md: business contracts live in Python route tests; the
 * browser layer guards the flow). The single-process app is expected on :8000.
 */

test.use({ baseURL: "http://127.0.0.1:8000" });

const QUESTIONS = [{ id: "q1", prompt: "你系统学算法主要为了什么？", options: ["求职面试", "打牢基础"] }];

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

const PAUSED_ARTIFACT = {
  type: "ask_user", artifact_id: "i1", status: "awaiting_input", closure: "", questions: QUESTIONS,
};

/** The server projection right after the paused run: the card is still open. */
const SESSION_DETAIL_PAUSED = {
  ...{ chat_session_id: "s1", name: "测试会话", name_source: "fallback", created_at: "2026-09-10T00:00:00+00:00", last_active: "2026-09-10T00:00:00+00:00", message_count: 2, provider_name: "deepseek", model_name: "test" },
  messages: [
    { role: "user", content: "帮我安排学习路线" },
    { role: "assistant", content: "问题卡已经在你那边了。", artifacts: [PAUSED_ARTIFACT] },
  ],
};

const SESSION_DETAIL = {
  chat_session_id: "s1", name: "测试会话", name_source: "fallback",
  created_at: "2026-09-10T00:00:00+00:00", last_active: "2026-09-10T00:00:00+00:00",
  message_count: 3, provider_name: "deepseek", model_name: "test",
  messages: [
    { role: "user", content: "帮我安排学习路线" },
    { role: "assistant", content: "问题卡已经在你那边了。", artifacts: [ANSWERED_ARTIFACT] },
    { role: "assistant", content: "好的，我按求职面试方向安排路线。" },
  ],
};

/**
 * Only the routes that must be deterministic are intercepted; everything else
 * (settings, libraries, documents, health) hits the real single-process app,
 * so the shell boots exactly as it does in production.
 */
async function mockBoot(page: Page) {
  await page.addInitScript(() => localStorage.setItem("bobodan:onboarding:v1", "complete"));
}

test("answering the card resumes the turn without inventing a user bubble", async ({ page }) => {
  await mockBoot(page);
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
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ chat_session_id: "s1", artifact: ANSWERED_ARTIFACT }),
    });
  });
  // After the answer the app re-reads the session, so the projection must follow.
  await page.route("**/api/chat/sessions/s1", (route) => route.fulfill({
    contentType: "application/json",
    body: JSON.stringify(answered ? SESSION_DETAIL : SESSION_DETAIL_PAUSED),
  }));

  await page.goto("/chat");
  const composer = page.getByRole("textbox", { name: "消息" });
  await composer.fill("帮我安排学习路线");
  await composer.press("Enter");

  // The run assigns the session id and the app then navigates + remounts, so
  // wait for that to settle before touching the card.
  await page.waitForURL(/\/chat\/s1/, { timeout: 15000 });
  const card = page.locator(".ask-user-card");
  await expect(card).toBeVisible();
  await expect(card).toContainText("你系统学算法主要为了什么？");

  const bubblesBefore = await page.locator(".user-message").count();
  await card.getByRole("button", { name: "求职面试" }).click();
  await card.getByRole("button", { name: "提交" }).click();

  await expect.poll(() => answerBodies.length).toBe(1);
  expect(answerBodies[0]).toMatchObject({ chat_session_id: "s1", answers: [{ id: "q1", answer: "求职面试" }] });

  // The paused turn continues, and the answer itself is not a user message.
  await expect(page.locator(".assistant-message").last()).toContainText("我按求职面试方向安排路线");
  // The card resolved in place with the chosen answer.
  await expect(page.locator(".ask-user-card")).toContainText("已回答");
  await expect(page.locator(".ask-user-card")).toContainText("求职面试");
  expect(await page.locator(".user-message").count()).toBe(bubblesBefore);
});

test("a skipped card says it was skipped instead of claiming an answer", async ({ page }) => {
  await mockBoot(page);
  await page.route("**/api/chat/sessions/s1", (route) => route.fulfill({
    contentType: "application/json",
    body: JSON.stringify({
      ...SESSION_DETAIL,
      messages: [
        { role: "user", content: "帮我安排学习路线" },
        {
          role: "assistant", content: "问题卡已经在你那边了。",
          artifacts: [{ type: "ask_user", artifact_id: "i1", status: "graded", closure: "skipped_by_next_message", questions: QUESTIONS, answers: [], outcome: { skipped: true } }],
        },
      ],
    }),
  }));

  await page.goto("/chat/s1");
  const card = page.locator(".ask-user-card");
  await expect(card).toContainText("没有作答，已跳过");
  await expect(card).toContainText("未回答");
  await expect(card).not.toContainText("已回答");
});
