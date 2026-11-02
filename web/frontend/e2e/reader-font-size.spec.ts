import { expect, test, type Page } from "@playwright/test";

import { json as sharedJson, settingsPayload as baseSettingsPayload } from "./fixtures/mockApi";

/**
 * L2 契约：「设置 → 外观 → 正文字号」（appearance.body_font_size，15/16/17/18）
 * 必须真的到达阅读器正文的计算字号。
 *
 * 2026-10-28 修的 bug：.reader-prose 上叠了 5 处 font-size 声明，最后由
 * `.reader-article .reader-prose { font-size: 18px }`（特异性 0,2,0）全胜，
 * 偏好 15/16/17 在阅读视图里一律被写成 18px。这条契约走真实链路：
 * /api/settings → AppShell 把偏好写进 --body-font-size → CSS → 计算样式。
 * 15 一档同时是回归探针：写死的 16px / 18px 都会让它失败。
 */

const DOCUMENT = {
  document_id: "doc-1",
  source: "course/lesson.md",
  kind: "course_document",
  title: "第一课",
  collection: "material",
  content_role: "content",
  chunk_count: 2,
  relative_path: "course/lesson.md",
};

function settingsPayload(bodyFontSize: number) {
  const body = baseSettingsPayload();
  body.preferences.appearance.body_font_size = bodyFontSize;
  return body;
}

const json = sharedJson;

async function mockShell(page: Page, currentSize: () => number) {
  await page.route("**/api/health", (route) => route.fulfill(json({ ok: true })));
  await page.route("**/api/settings", (route) => route.fulfill(json(settingsPayload(currentSize()))));
  await page.route("**/api/libraries", (route) => route.fulfill(json({
    active_library_id: "library-1",
    libraries: [{ library_id: "library-1", name: "测试资料库", created_at: "", last_opened_at: "", active: true, available: true }],
  })));
  await page.route("**/api/chat/sessions", (route) => route.fulfill(json({ sessions: [] })));
  await page.route("**/api/learning/review-queue", (route) => route.fulfill(json({
    due_concepts: [], wrong_answers: [], weaknesses: [], personalization: [],
  })));
  await page.route("**/api/kb/documents?collection=all", (route) => route.fulfill(json({ documents: [DOCUMENT] })));
  await page.route("**/api/kb/documents?collection=material", (route) => route.fulfill(json({ documents: [DOCUMENT] })));
  await page.route("**/api/kb/wiki/coverage", (route) => route.fulfill(json({ documents: [], counts: { uncovered: 0, partial: 0, covered: 0, stale: 0 } })));
  await page.route("**/api/kb/documents/doc-1/anchors", (route) => route.fulfill(json({ anchors: [] })));
  await page.route("**/api/kb/documents/doc-1", (route) => route.fulfill(json({
    document: DOCUMENT,
    sections: [
      { chunk_id: "c1", heading: "第一节 概念", text: "正文。" },
      { chunk_id: "c2", heading: "第二节 推导", text: "更多正文。" },
    ],
  })));
  await page.route("**/api/memory/knowledge/by-document/doc-1", (route) => route.fulfill(json({ items: [] })));
  await page.route("**/api/memory/reading-progress/doc-1", (route) => route.fulfill(json({ progress: { document_id: "doc-1", progress: 0 } })));
  await page.route("**/api/graph/extractions", (route) => route.fulfill(json({ documents: {} })));
}

const proseLocator = (page: Page) => page.locator(".reader-article .reader-prose").first();

/** 阅读器正文当前的计算字号（px，浮点）。 */
const computedSize = (page: Page) =>
  proseLocator(page).evaluate((el) => parseFloat(getComputedStyle(el).fontSize));

/** AppShell 按偏好写到根元素上的变量值（如 "15px"）。 */
const bodyFontToken = (page: Page) =>
  page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue("--body-font-size").trim());

test("阅读器正文跟随设置的正文字号（15 与 18 都等于偏好值）", async ({ page }) => {
  let preferred = 15;
  await mockShell(page, () => preferred);
  await page.addInitScript(() => localStorage.setItem("bobodan:onboarding:v1", "complete"));

  await page.goto("/library/read/doc-1?collection=material");
  await expect(proseLocator(page)).toBeVisible();

  // 偏好 15：旧实现这里被 16px / 18px 覆盖，拿不到 15。
  await expect.poll(() => computedSize(page), { timeout: 10_000 }).toBe(15);
  expect(await bodyFontToken(page)).toBe("15px");

  // 偏好 18：同一个元素必须跟着偏好走，而不是卡在某个写死的档位。
  preferred = 18;
  await page.reload();
  await expect(proseLocator(page)).toBeVisible();
  await expect.poll(() => computedSize(page), { timeout: 10_000 }).toBe(18);
  expect(await bodyFontToken(page)).toBe("18px");
});
