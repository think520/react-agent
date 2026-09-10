import { expect, test } from "@playwright/test";

/**
 * Smoke suite (tests/README.md Playwright policy): the browser layer only
 * guards "the app opens and its primary surfaces work". Business contracts
 * live in Python route tests; stable scenario flows live in app.spec.ts.
 */

test.beforeEach(async ({ page }) => {
  // Smoke tests target the everyday app, not the first-run wizard.
  await page.addInitScript(() => localStorage.setItem("bobodan:onboarding:v1", "complete"));
  await page.route("**/api/health", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ ok: true }) }));
  await page.route("**/api/kb/documents?collection=all", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ documents: [] }) }));
  await page.route("**/api/libraries", (route) => route.fulfill({
    contentType: "application/json",
    body: JSON.stringify({
      active_library_id: "library-1",
      libraries: [{ library_id: "library-1", name: "测试资料库", created_at: "", last_opened_at: "", active: true, available: true }],
    }),
  }));
});

test("app boots and primary routes render", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator(".app-shell")).toBeVisible();
  await expect(page.locator(".brand-row")).toContainText("Bobodan");

  for (const path of ["/library", "/practice", "/review", "/notes", "/knowledge-map"]) {
    await page.goto(path);
    await expect(page.locator(".app-shell")).toBeVisible();
    // No route-level crash boundary on any primary page.
    await expect(page.getByText("页面出了点问题")).toHaveCount(0);
  }
});

test("composer accepts input and slash palette opens", async ({ page }) => {
  await page.goto("/");
  const composer = page.getByRole("textbox", { name: "消息" });
  await expect(composer).toBeVisible();
  await composer.fill("/");
  await expect(page.getByRole("listbox", { name: "命令与技能" })).toBeVisible();
  await composer.fill("");
});

test("settings dialog opens from topbar and closes on Escape", async ({ page }, testInfo) => {
  await page.route("**/api/settings", (route) => route.fulfill({
    contentType: "application/json",
    body: JSON.stringify({
      workspace_name: "测试空间",
      default_provider: "deepseek",
      providers: [{ name: "deepseek", configured: true, model: "deepseek-chat" }],
      search_providers: [{ name: "auto", configured: true }],
      mcp_enabled: false,
      skills: [],
      preferences: {
        schema_version: 4, revision: 0,
        assistant: { display_name: "Bobodan", teaching_style: "guided", answer_depth: "standard", feedback_strength: "gentle" },
        user: { display_name: "", profile: "", long_term_goal: "" },
        appearance: { reading_font: "jin-kai", body_font_size: 16, content_width: 720, paper_texture: true, session_density: "comfortable", motion: "system" },
        ai: { default_provider: "deepseek", task_providers: { wiki_discovery: "default", wiki_drafting: "default" } },
        wiki: { default_mode: "standard", guide_completed: false, budget: { max_requests: 24, max_input_tokens: 300000, max_output_tokens: 40000 } },
        memory: { enabled: true },
        search: { provider: "auto", permission: "ask", jina_fallback: true },
        skills: { enabled_names: [] },
      },
    }),
  }));
  await page.goto(testInfo.project.name === "desktop" ? "/" : "/?settings=assistant");
  // Desktop opens settings through the topbar gear; narrow/mobile take the
  // URL deep link (the drawer transition makes the click path flaky).
  if (testInfo.project.name === "desktop") {
    await page.getByRole("button", { name: "打开设置" }).click();
  }
  const dialog = page.getByRole("dialog", { name: "设置" });
  await expect(dialog).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
});
