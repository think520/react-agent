import { expect, test, type Page } from "@playwright/test";

import { mockApi } from "./fixtures/mockApi";

// L2 计算样式契约（DESIGN.md §16.3）：证明运行时**计算出来**的值，而不是只证明源码文本。
// L2-1 阅读器字号见 reader-font-size.spec.ts；L2-5 设置视口约束见 settings-fit.spec.ts。
// 这里补 L2-2 主题对比度（4 种主题 × 对比度组合）、L2-3 表面阶梯与发丝边、L2-4 界面字号下限。

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

/** 等布局与字体真的落定，替代固定 waitForTimeout。 */
async function settle(page: Page) {
  await expect(page.locator(".sidebar")).toBeVisible();
  await page.evaluate(async () => { await document.fonts.ready; });
  await page.evaluate(() => new Promise<void>((resolve) => {
    requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
  }));
}

test.beforeEach(async ({ page: _page }, testInfo) => {
  test.skip(testInfo.project.name === "mobile", "移动端另有一套全屏布局，这里的桌面窗口/GUI 契约不适用");
});

// L2-2：高对比是**计算出来**的对比度承诺，不是源码里的颜色清单。
// 阈值与 lib/themeContrast.test.ts 的 WCAG AA 表一致；四组组合全测 ——
// 上一次真出事的组合是「浅色 + 高对比」（muted 曾被压到 1.10:1），只测暗色等于漏掉它。
const CONTRAST_FLOORS = [
  { label: "浅色 + 普通", theme: "light", contrast: "normal", floors: { ink: 12, muted: 4.5, faint: 4.5 } },
  { label: "浅色 + 高对比", theme: "light", contrast: "high", floors: { ink: 12, muted: 7, faint: 7 } },
  { label: "暗色 + 普通", theme: "dark", contrast: "normal", floors: { ink: 10, muted: 4.5, faint: 4.5 } },
  { label: "暗色 + 高对比", theme: "dark", contrast: "high", floors: { ink: 7, muted: 7, faint: 7 } },
] as const;

for (const combo of CONTRAST_FLOORS) {
  test("L2-2 " + combo.label + " 的正文对比度实测达标", async ({ page }) => {
    await mockApi(page, { appearance: { theme: combo.theme, contrast: combo.contrast } });
    await page.goto("/chat");
    await expect(page.locator("html")).toHaveAttribute("data-theme", combo.theme);
    await expect(page.locator("html")).toHaveAttribute("data-contrast", combo.contrast);

    const paper = await tokenColor(page, "--paper", true);
    const ink = await tokenColor(page, "--ink");
    const muted = await tokenColor(page, "--muted");
    const faint = await tokenColor(page, "--faint");

    const ratios = {
      ink: contrastRatio(ink.rgb, paper.rgb),
      muted: contrastRatio(muted.rgb, paper.rgb),
      faint: contrastRatio(faint.rgb, paper.rgb),
    };
    for (const key of ["ink", "muted", "faint"] as const) {
      const floor = combo.floors[key];
      expect(ratios[key], combo.label + " 的 " + key + " 对 paper 实测 " + ratios[key].toFixed(2) + ":1，要求 ≥ " + floor + ":1").toBeGreaterThanOrEqual(floor);
    }
  });
}

// L2-3：表面阶梯 0/1/2/3 与发丝外环，必须在浏览器里真的算成这些颜色和这个环。
// 2026-11-02 抓到的真缺陷：.welcome-view .composer（两个类）压过 M3 的 .composer（一个类），
// 把「surface 3 + 发丝环」整条覆盖 —— 这条契约就是它的回归探针。
test("L2-3 表面阶梯与发丝外环的计算值符合 DESIGN 4.4/4.5", async ({ page }) => {
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
  expect(composer.boxShadow, "首页输入区也必须有发丝环（welcome 变体不得整体覆盖）").toContain("0px 0px 0px 1px");
});

// L2-4：界面字号下限 12px —— 之前只有「源码里不许写 <12px」的 L1 契约，
// 计算值仍可能被继承、浏览器默认字号或缩放拉低，这里直接量渲染后的值。
// 覆盖 7 个 DOM 页面；**知识地图不在覆盖范围内**：它的节点与标签由 Sigma 画在
// canvas 上，DOM 里没有文字节点，字号只能靠 GraphCanvas 的渲染参数保证。
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
  ["题库", "/practice/bank"],
  ["复习", "/review"],
  ["资料库", "/library"],
  ["笔记", "/notes"],
  ["设置", "/chat?settings=appearance"],
] as const) {
  test("L2-4 " + label + "页没有小于 12px 的可见文字（计算值）", async ({ page }) => {
    await mockApi(page);
    await page.goto(path);
    await settle(page);
    const violations = await smallTextViolations(page);
    expect(violations, label + "页出现小于 12px 的文字：" + JSON.stringify(violations)).toEqual([]);
  });
}
