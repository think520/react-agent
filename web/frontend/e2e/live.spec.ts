import { expect, test } from "@playwright/test";

/**
 * 真实环境检查（默认跳过）：直接打本机正在运行的后端，不 mock 任何接口。
 *
 *   .venv\Scripts\python.exe -m cli.web_serve --no-browser --dev --port 8000
 *   cd web/frontend; $env:BOBODAN_E2E_LIVE = "1"; npx playwright test e2e/live.spec.ts
 *
 * CI 里没有后端，也没有真实资料库，所以默认 skip；但它记录的是"页内原文"这条
 * 主路径在真实数据上的行为，这是 mock 无法替代的那部分证据。
 */
test.skip(!process.env.BOBODAN_E2E_LIVE, "需要本机后端：设置 BOBODAN_E2E_LIVE=1");

const BASE = process.env.BOBODAN_E2E_BASE || "http://127.0.0.1:8000";

test("the reader renders the original file for a real document", async ({ page }) => {
  const registry = await (await page.request.get(BASE + "/api/libraries")).json();
  const libraryId = registry.active_library_id;
  const headers = { "X-Bobodan-Library-ID": libraryId };

  const listed = await (await page.request.get(BASE + "/api/kb/documents?collection=material", { headers })).json();
  const doc = (listed.documents || []).find((item: { has_original?: boolean }) => item.has_original);
  test.skip(!doc, "这个资料库里没有带原件的资料");

  await page.addInitScript(() => localStorage.setItem("bobodan:onboarding:v1", "complete"));
  await page.goto(BASE + "/library/read/" + doc.document_id + "?collection=material");

  // 默认就是原文，且是我们自己的排版（不是解析文本）
  await expect(page.locator(".reader-original")).toBeVisible({ timeout: 20_000 });
  await expect(page.locator(".reader-view-switch")).toBeVisible();

  // 切到分段视图：原文消失、解析文本出现
  await page.getByRole("button", { name: "按小节" }).click();
  await expect(page.locator(".reader-original")).toHaveCount(0);
  await expect(page.locator(".reader-prose")).toBeVisible();

  // 回到原文，再从章节导航跳一次：必须落到分段视图并且高亮那一段。
  // （章节导航靠 [data-chunk-id] 定位，那些节点只存在于分段视图——曾经在原文视图里
  //  点了毫无反应，这条断言就是钉住那次修复的。）
  await page.getByRole("button", { name: "原文" }).click();
  await expect(page.locator(".reader-original")).toBeVisible();

  await page.locator(".chapter-rail-zone").hover();
  await expect(page.locator(".chapter-rail")).toBeVisible();
  await page.locator(".chapter-rail div button").first().click();

  await expect(page.locator(".reader-original")).toHaveCount(0);
  await expect(page.locator(".reader-prose")).toBeVisible();
  await expect(page.locator("section.highlighted")).toHaveCount(1, { timeout: 10_000 });
});
test("a citation link lands on the cited chunk and offers the way back", async ({ page }) => {
  const registry = await (await page.request.get(BASE + "/api/libraries")).json();
  const headers = { "X-Bobodan-Library-ID": registry.active_library_id };
  const listed = await (await page.request.get(BASE + "/api/kb/documents?collection=material", { headers })).json();
  const doc = (listed.documents || []).find((item: { has_original?: boolean }) => item.has_original);
  test.skip(!doc, "这个资料库里没有带原件的资料");

  await page.addInitScript(() => localStorage.setItem("bobodan:onboarding:v1", "complete"));
  await page.goto(BASE + "/library/read/" + doc.document_id + "?collection=material");
  await page.getByRole("button", { name: "按小节" }).click();
  const chunkId = await page.locator("[data-chunk-id]").first().getAttribute("data-chunk-id");
  expect(chunkId).toBeTruthy();

  await page.goto(
    BASE + "/library/read/" + doc.document_id + "?collection=material&chunk=" + encodeURIComponent(chunkId as string),
  );
  await expect(page.locator(".reader-citation-bar")).toBeVisible({ timeout: 20_000 });
  await expect(page.locator("section.highlighted")).toHaveCount(1, { timeout: 10_000 });

  await page.getByRole("button", { name: "看原文" }).click();
  await expect(page.locator(".reader-original")).toBeVisible();
  await expect(page.locator(".reader-citation-bar")).toHaveCount(0);
});
test("searching the library lands on the matched chunk", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("bobodan:onboarding:v1", "complete"));
  await page.goto(BASE + "/library?collection=material");

  await page.locator(".document-search input").fill("向量检索");
  const hit = page.locator(".document-hit").first();
  await expect(hit).toBeVisible({ timeout: 20_000 });
  await hit.click();

  await expect(page.locator(".reader-citation-bar")).toBeVisible({ timeout: 20_000 });
  await expect(page.locator("section.highlighted")).toHaveCount(1, { timeout: 15_000 });
});
