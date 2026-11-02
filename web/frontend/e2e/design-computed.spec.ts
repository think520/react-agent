import { expect, test, type Page } from "@playwright/test";

// L2 计算样式契约（DESIGN.md §16.3）：证明运行时**计算出来**的值，而不是只证明源码文本。
// L2-1 阅读器字号见 reader-font-size.spec.ts；L2-5 设置视口约束见 settings-fit.spec.ts。
// 这里补 L2-2 主题对比度、L2-3 表面阶梯与发丝边、L2-4 界面字号下限。

function preferences(overrides: Record<string, unknown> = {}) {
  return {
    schema_version: 4,
    revision: 0,
    assistant: { display_name: "Bobodan", teaching_style: "guided", answer_depth: "standard", feedback_strength: "gentle" },
    user: { display_name: "", profile: "", long_term_goal: "" },
    appearance: { reading_font: "jin-kai", body_font_size: 16, content_width: 720, paper_texture: true, session_density: "comfortable", motion: "system", theme: "light", contrast: "normal" },
    ai: { default_provider: "deepseek", task_providers: { wiki_discovery: "default", wiki_drafting: "default" } },
    wiki: { default_mode: "standard", guide_completed: false, budget: { max_requests: 24, max_input_tokens: 300000, max_output_tokens: 40000 } },
    memory: { enabled: true },
    search: { provider: "auto", permission: "ask", jina_fallback: true },
    skills: { enabled_names: [] },
    ...overrides,
  };
}

async function mockApi(page: Page, prefs = preferences()) {
  await page.addInitScript(() => localStorage.setItem("bobodan:onboarding:v1", "complete"));
  await page.route("**/api/health", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ ok: true }) }));
  await page.route("**/api/libraries", (route) => route.fulfill({
    contentType: "application/json",
    body: JSON.stringify({
      active_library_id: "library-1",
      libraries: [{ library_id: "library-1", name: "测试资料库", created_at: "", last_opened_at: "", active: true, available: true }],
    }),
  }));
  await page.route("**/api/settings", (route) => route.fulfill({
    contentType: "application/json",
    body: JSON.stringify({
      workspace_name: "测试空间",
      default_provider: "deepseek",
      providers: [{ name: "deepseek", configured: true, model: "deepseek-chat" }],
      search_providers: [{ name: "auto", configured: true }],
      mcp_enabled: false,
      skills: [],
      preferences: prefs,
    }),
  }));
  await page.route("**/api/chat/sessions", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ sessions: [] }) }));
  await page.route("**/api/kb/documents?collection=all", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ documents: [] }) }));
  await page.route("**/api/kb/documents?collection=material", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ documents: [] }) }));
  await page.route("**/api/kb/wiki/coverage", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ documents: [], counts: { uncovered: 0, partial: 0, covered: 0, stale: 0 } }) }));
  await page.route("**/api/learning/review-queue", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ due_concepts: [], wrong_answers: [], weaknesses: [] }) }));
  await page.route("**/api/quiz/sessions/active", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ sessions: [] }) }));
}

/** 在页面里把任意 CSS 颜色解析成 sRGB 三元组（浏览器负责解析 oklch / color-mix）。 */
async function tokenColor(page: Page, variable: string, asBackground = false) {
  return page.evaluate(({ variable: name, asBackground: asBg }) => {
    const probe = document.createElement("div");
    probe.style.color = "var(" + name + ")";
    if (asBg) probe.style.backgroundColor = "var(" + name + ")";
    probe.style.position = "fixed";
    probe.style.left = "-9999px";
    document.body.appendChild(probe);
    const style = getComputedStyle(probe);
    const raw = asBg ? style.backgroundColor : style.color;
    probe.remove();
    const nums = (raw.match(/[0-9.]+/g) || []).map(Number);
    return { raw: raw, rgb: nums.slice(0, 3) };
  }, { variable, asBackground });
}

function relativeLuminance(rgb: number[]) {
  const channels = rgb.map((value) => {
    const channel = value / 255;
    return channel <= 0.03928 ? channel / 12.92 : Math.pow((channel + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
}

function contrastRatio(a: number[], b: number[]) {
  const light = relativeLuminance(a) >= relativeLuminance(b) ? a : b;
  const dark = light === a ? b : a;
  return (relativeLuminance(light) + 0.05) / (relativeLuminance(dark) + 0.05);
}

test.beforeEach(async ({ page: _page }, testInfo) => {
  test.skip(testInfo.project.name === "mobile", "移动端另有一套全屏布局，这里的桌面窗口/GUI 契约不适用");
});

// L2-2：高对比是**计算出来**的对比度承诺，不是源码里的颜色清单。
test("高对比暗色主题的正文与弱化文字对比度实测达到 7:1", async ({ page }) => {
  const dark = preferences();
  dark.appearance = { reading_font: "jin-kai", body_font_size: 16, content_width: 720, paper_texture: true, session_density: "comfortable", motion: "system", theme: "dark", contrast: "high" };
  await mockApi(page, dark);
  await page.goto("/chat");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.locator("html")).toHaveAttribute("data-contrast", "high");

  const paper = await tokenColor(page, "--paper", true);
  const ink = await tokenColor(page, "--ink");
  const muted = await tokenColor(page, "--muted");
  const faint = await tokenColor(page, "--faint");

  const inkRatio = contrastRatio(ink.rgb, paper.rgb);
  const mutedRatio = contrastRatio(muted.rgb, paper.rgb);
  const faintRatio = contrastRatio(faint.rgb, paper.rgb);
  expect(inkRatio, "ink 对 paper 的对比度（实测 " + inkRatio.toFixed(2) + ":1）").toBeGreaterThanOrEqual(7);
  expect(mutedRatio, "muted 对 paper 的对比度（实测 " + mutedRatio.toFixed(2) + ":1）").toBeGreaterThanOrEqual(7);
  expect(faintRatio, "faint 对 paper 的对比度（实测 " + faintRatio.toFixed(2) + ":1）").toBeGreaterThanOrEqual(7);
});

// L2-3：表面阶梯 0/1/2/3 与发丝外环，必须在浏览器里真的算成这些颜色和这个环。
test("表面阶梯与发丝外环的计算值符合 DESIGN 4.4/4.5", async ({ page }) => {
  await mockApi(page);
  await page.goto("/chat?settings=appearance");
  const dialog = page.getByRole("dialog", { name: "设置" });
  await expect(dialog).toBeVisible();

  const background = async (selector: string) =>
    page.locator(selector).first().evaluate((el) => getComputedStyle(el).backgroundColor);

  const surface0 = (await tokenColor(page, "--surface-0", true)).raw;
  const surface1 = (await tokenColor(page, "--surface-1", true)).raw;
  const surface2 = (await tokenColor(page, "--surface-2", true)).raw;
  const surface3 = (await tokenColor(page, "--surface-3", true)).raw;

  expect(await background(".sidebar"), "停靠栏 = surface 0").toBe(surface0);
  expect(await background(".settings-main"), "画布 = surface 1").toBe(surface1);
  expect(await background(".settings-section"), "卡片 = surface 2").toBe(surface2);
  expect(await background(".ui-modal-panel"), "浮层 = surface 3").toBe(surface3);

  const panel = await page.locator(".ui-modal-panel").first().evaluate((el) => {
    const style = getComputedStyle(el);
    return { borderWidth: style.borderTopWidth, boxShadow: style.boxShadow };
  });
  expect(panel.borderWidth, "浮层不再用实边框").toBe("0px");
  expect(panel.boxShadow).toContain("0px 0px 0px 1px");

  const composer = await page.locator(".composer").first().evaluate((el) => {
    const style = getComputedStyle(el);
    return { background: style.backgroundColor, borderWidth: style.borderTopWidth, boxShadow: style.boxShadow };
  });
  expect(composer.background).toBe(surface3);
  expect(composer.borderWidth).toBe("0px");
  expect(composer.boxShadow).toContain("0px 0px 0px 1px");
});

// L2-4：界面字号下限 12px —— 之前只有「源码里不许写 <12px」的 L1 契约，
// 计算值仍可能被继承、浏览器默认字号或缩放拉低，这里直接量渲染后的值。
async function smallTextViolations(page: Page) {
  return page.evaluate(() => {
    const violations: { tag: string; className: string; size: number; text: string }[] = [];
    for (const element of Array.from(document.querySelectorAll("body *"))) {
      const hasText = Array.from(element.childNodes).some((node) => node.nodeType === 3 && (node.textContent || "").trim().length > 0);
      if (!hasText) continue;
      const style = getComputedStyle(element);
      if (style.display === "none" || style.visibility === "hidden" || Number(style.opacity) === 0) continue;
      const rect = element.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) continue;
      const size = parseFloat(style.fontSize);
      if (size < 12 - 0.01) violations.push({ tag: element.tagName, className: String(element.className).slice(0, 60), size: size, text: (element.textContent || "").trim().slice(0, 24) });
    }
    return violations;
  });
}

for (const [label, path] of [
  ["对话", "/chat"],
  ["练习", "/practice"],
  ["资料库", "/library"],
  ["设置", "/chat?settings=appearance"],
] as const) {
  test(label + "页没有小于 12px 的可见文字（计算值）", async ({ page }) => {
    await mockApi(page);
    await page.goto(path);
    await page.waitForTimeout(600);
    const violations = await smallTextViolations(page);
    expect(violations, label + "页出现小于 12px 的文字：" + JSON.stringify(violations)).toEqual([]);
  });
}
