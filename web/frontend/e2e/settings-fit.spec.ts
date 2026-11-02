import { expect, test } from "@playwright/test";

function settingsPayload() {
  return {
    workspace_name: "测试空间",
    default_provider: "deepseek",
    providers: [{ name: "deepseek", configured: true, model: "deepseek-chat" }],
    search_providers: [{ name: "auto", configured: true }, { name: "tavily", configured: false }, { name: "exa", configured: true }],
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

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("bobodan:onboarding:v1", "complete"));
  await page.route("**/api/health", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ ok: true }) }));
  await page.route("**/api/libraries", (route) => route.fulfill({
    contentType: "application/json",
    body: JSON.stringify({
      active_library_id: "library-1",
      libraries: [{ library_id: "library-1", name: "测试资料库", created_at: "", last_opened_at: "", active: true, available: true }],
    }),
  }));
  await page.route("**/api/settings", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(settingsPayload()) }));
  await page.route("**/api/chat/sessions", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ sessions: [] }) }));
  await page.route("**/api/kb/documents?collection=all", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ documents: [] }) }));
  await page.route("**/api/kb/documents?collection=material", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ documents: [] }) }));
  await page.route("**/api/kb/wiki/coverage", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ documents: [], counts: { uncovered: 0, partial: 0, covered: 0, stale: 0 } }) }));
  await page.route("**/api/learning/review-queue", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ due_concepts: [], wrong_answers: [], weaknesses: [] }) }));
});

// L2-5（计算样式契约）：设置对话框的高度上限与底部主操作，必须在低高度视口里真的可见。
// 1280x600 是 Windows 桌面端常见的最小可用窗口，旧的 min-height: 620px 会在这里把
// 「保存助手设置」挤出视口，只能靠内容区滚动去够。
test("设置对话框在 1280x600 下不越界，助手设置的保存按钮可见", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name === "mobile", "移动端是全屏 sheet，桌面窗口约束在这里不适用");
  await page.setViewportSize({ width: 1280, height: 600 });
  await page.goto("/chat?settings=assistant");

  const dialog = page.getByRole("dialog", { name: "设置" });
  await expect(dialog).toBeVisible();

  const dialogBox = await dialog.boundingBox();
  expect(dialogBox).not.toBeNull();
  expect(dialogBox!.y).toBeGreaterThanOrEqual(-1);
  expect(dialogBox!.y + dialogBox!.height).toBeLessThanOrEqual(601);

  const save = dialog.getByRole("button", { name: "保存助手设置" });
  await expect(save).toBeVisible();
  const saveBox = await save.boundingBox();
  expect(saveBox).not.toBeNull();
  expect(saveBox!.y + saveBox!.height).toBeLessThanOrEqual(601);

  // 主操作固定在对话框底部，不随内容区滚动而离开视口。
  const footerSticks = await dialog.locator(".settings-main").evaluate((main) => {
    const footer = document.querySelector(".settings-dialog-footer");
    if (!footer) return false;
    const dialogEl = document.querySelector(".settings-dialog");
    if (!dialogEl) return false;
    return dialogEl.contains(footer) && main.scrollHeight >= main.clientHeight;
  });
  expect(footerSticks).toBe(true);
});

test("助手设置的主操作在 1440x960 也固定在对话框底部", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name === "mobile", "移动端是全屏 sheet，桌面窗口约束在这里不适用");
  await page.setViewportSize({ width: 1440, height: 960 });
  await page.goto("/chat?settings=assistant");

  const dialog = page.getByRole("dialog", { name: "设置" });
  await expect(dialog).toBeVisible();
  const dialogBox = await dialog.boundingBox();
  expect(dialogBox).not.toBeNull();
  expect(dialogBox!.height).toBeLessThanOrEqual(840.5);

  const footer = dialog.locator(".settings-dialog-footer");
  await expect(footer).toBeVisible();
  const dialogBottom = dialogBox!.y + dialogBox!.height;
  const footerBox = await footer.boundingBox();
  expect(footerBox).not.toBeNull();
  expect(dialogBottom - (footerBox!.y + footerBox!.height)).toBeLessThanOrEqual(1.5);
});
