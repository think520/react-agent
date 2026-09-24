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
test("the library folder sync button scans the folder and reports the result", async ({ page }) => {
  // ①（E17）：修前 `api.syncLibrary()` 全前端零调用——用户在资源管理器里把
  // 资料剪进资料库文件夹后，界面里没有任何办法发现它们。这条 live 检查对
  // 真实后端 + 真实资料库点一次按钮，要求它真的扫描并给出可读摘要。
  await page.addInitScript(() => localStorage.setItem("bobodan:onboarding:v1", "complete"));
  await page.goto(BASE + "/library?collection=material");

  const button = page.getByRole("button", { name: /同步文件夹/ });
  await expect(button).toBeVisible({ timeout: 20_000 });
  await button.click();

  const summary = page.locator(".library-sync-summary");
  await expect(summary).toBeVisible({ timeout: 120_000 });
  await expect(summary).toContainText(/已扫描 \d+ 份资料/);
  await expect(summary).toContainText(/跳过 \d+/);

  await summary.getByText("查看明细").click();
  await expect(summary).toContainText(/跳过（仓库元文件）/);
});
test("the library page shows the real folder tree", async ({ page }) => {
  // ②（E17）：树建在真实文件系统上——它必须显示资料库里的真实文件夹，
  // 并且**隐藏** Bobodan 自己的内部结构（.bobodan / wiki）。
  await page.addInitScript(() => localStorage.setItem("bobodan:onboarding:v1", "complete"));
  await page.goto(BASE + "/library?collection=material");

  const tree = page.locator(".library-tree");
  await expect(tree).toBeVisible({ timeout: 20_000 });
  // 真实库里有 ai-agents-from-zero 与 raw 两个真实文件夹
  // （Playwright 的 name 默认是子串匹配，会和"展开 …"的 aria-label 撞车，所以用 exact）
  await expect(tree.getByRole("button", { name: "ai-agents-from-zero", exact: true })).toBeVisible();
  await expect(tree.getByRole("button", { name: "raw", exact: true })).toBeVisible();
  // 内部结构不出现在树里
  await expect(tree.getByRole("button", { name: "wiki", exact: true })).toHaveCount(0);
  await expect(tree.getByRole("button", { name: ".bobodan", exact: true })).toHaveCount(0);

  // 2026-09-24 用户要求：中间的"我的资料"平铺列表与树功能重复、还占一栏，去掉了。
  // 资料库因此只有一套导航；搜索入口搬进了树面板（原来长在列表里），必须仍然好用。
  await expect(page.locator(".document-rail")).toHaveCount(0);
  const search = page.locator(".library-tree-pane .document-search input");
  await expect(search).toBeVisible();
  await search.fill("Dijkstra");
  await expect(tree.locator(".library-tree-name", { hasText: "Dijkstra" }).first()).toBeVisible({ timeout: 20_000 });
  await search.fill("");
  await expect(tree.locator(".library-tree-name", { hasText: "正则表达式" }).first()).toBeVisible({ timeout: 20_000 });
});
test("the library page reads a material in place", async ({ page }) => {
  // ④（E17）：点资料不再跳走 —— 资料库页自己渲染正文，并进标签条。
  // 这是 2026-09-24 审计发现的缺口（当时会 navigate 到 /library/read/:id）。
  await page.addInitScript(() => localStorage.setItem("bobodan:onboarding:v1", "complete"));
  await page.goto(BASE + "/library?collection=material");

  const tree = page.locator(".library-tree");
  await expect(tree).toBeVisible({ timeout: 20_000 });
  await tree.getByRole("button", { name: "ai-agents-from-zero", exact: true }).click();
  await tree.getByRole("button", { name: /^展开 ai-agents-from-zero$/ }).click();
  await tree.locator(".library-tree-open").first().click();

  await expect(page).toHaveURL(/\/library\?/);
  // ④ 第 3 步之后，资料库页的阅读区就是 DocumentReader 本身：它先按用户偏好选视图，
  // 有原件的资料默认落在「原文」。所以这里先断言正文出现，再切到「按小节」断言分段 ——
  // 这同时钉住了"资料库页也拿到了原文/按小节切换"这件新能力。
  await expect(page.locator(".document-reader .reader-prose").first()).toBeVisible({ timeout: 20_000 });
  const sectionsSwitch = page.locator(".document-reader .reader-view-switch").getByRole("button", { name: "按小节" });
  if (await sectionsSwitch.count()) {
    await sectionsSwitch.click();
  }
  await expect(page.locator(".document-reader .reader-prose section").first()).toBeVisible({ timeout: 20_000 });
  await expect(page.locator(".reader-tabs .reader-tab")).toHaveCount(1);

  // 布局回归（2026-09-24 用户截图）：标签条曾经是工作区网格的**第 4 个孩子**，一开标签
  // 3 列网格就自动换行 —— 阅读区被挤到下一行、列表被顶到阅读区的位置，整个分栏塌陷。
  // 同时钉住正文的可用宽度：三栏一起挤的话正文只剩四百来像素。
  const readerBox = await page.locator(".document-reader").boundingBox();
  const treeBox = await page.locator(".library-tree-pane").boundingBox();
  expect(readerBox!.width).toBeGreaterThan(treeBox!.width * 2);
  expect(readerBox!.x).toBeGreaterThanOrEqual(treeBox!.x + treeBox!.width - 1);
  // 资料库只有一套导航：中间的"我的资料"平铺列表已按用户要求去掉（与树重复、还占一栏）。
  await expect(page.locator(".document-rail")).toHaveCount(0);
});
