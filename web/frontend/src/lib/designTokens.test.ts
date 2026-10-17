import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * DESIGN.md is only a constraint if something checks it. This file makes the
 * spec executable: the token table must equal :root, and the three known drifts
 * (font size, bare easing, off-scale radius) are ratcheted so they can only
 * shrink. Budgets come from the 2026-09-14 measurement; lower them as batches land.
 */

// vitest 跑在 jsdom 里，import.meta.url 不是 file:，所以用 cwd 定位源码文本。
//
// M1 分层（2026-10-17）后：入口 styles.css 只做 @import 编排，令牌在 styles/tokens.css，
// 规则在 styles/app.css。契约测试必须读**全部**样式 —— 否则「规则搬了家」会让棘轮静默失效。
const SRC = resolve(process.cwd(), "src");
const ENTRY_PATH = resolve(SRC, "styles.css");
const TOKENS_PATH = resolve(SRC, "styles", "tokens.css");
const DOC_PATH = resolve(process.cwd(), "..", "..", "docs", "DESIGN.md");
if (!existsSync(ENTRY_PATH)) throw new Error("找不到 styles.css");
if (!existsSync(TOKENS_PATH)) throw new Error("找不到 styles/tokens.css");
if (!existsSync(DOC_PATH)) throw new Error("找不到 DESIGN.md");
const tokensText = readFileSync(TOKENS_PATH, "utf8");
const cssText = [
  readFileSync(ENTRY_PATH, "utf8"),
  readFileSync(resolve(SRC, "styles", "tokens.css"), "utf8"),
  readFileSync(resolve(SRC, "styles", "app.css"), "utf8"),
  readFileSync(resolve(SRC, "styles", "fonts.css"), "utf8"),
].join("\n");
const docText = readFileSync(DOC_PATH, "utf8");

function normalize(value: string) {
  return value.replace(/\s+/g, "");
}

function tokensIn(block: string) {
  const tokens = new Map<string, string>();
  for (const match of block.matchAll(/(--[a-z0-9-]+)\s*:\s*([^;]+);/g)) {
    tokens.set(match[1], normalize(match[2]));
  }
  return tokens;
}

function rootBlock(css: string) {
  const start = css.indexOf(":root {");
  if (start < 0) throw new Error("styles.css 里找不到 :root 块");
  const end = css.indexOf("\n}", start);
  if (end < 0) throw new Error("styles.css 的 :root 块没有闭合");
  return css.slice(start, end);
}

function docTokenBlock(doc: string) {
  const marker = doc.indexOf("### CSS Tokens");
  if (marker < 0) throw new Error("DESIGN.md 里找不到 CSS Tokens 一节");
  const section = doc.slice(marker);
  const fence = section.indexOf("```css");
  if (fence < 0) throw new Error("CSS Tokens 一节里没有 css 代码块");
  const close = section.indexOf("```", fence + 6);
  if (close < 0) throw new Error("CSS Tokens 的代码块没有闭合");
  return section.slice(fence, close);
}

// The namespaces the doc owns. A new token in one of these must be documented.
const OWNED = [
  "--paper", "--paper-soft", "--paper-sunken", "--parchment",
  "--ink", "--muted", "--faint",
  "--border-subtle", "--border", "--border-strong",
  "--shadow-soft", "--shadow-lift", "--shadow-float", "--shadow-dialog",
  "--radius-sm", "--radius-md", "--radius-lg", "--radius-xl",
  "--space-1", "--space-2", "--space-3", "--space-4", "--space-5", "--space-6", "--space-7",
  "--ease-out", "--ease-in-out",
  "--dur-fast", "--dur-base", "--dur-slow",
  "--spring-micro", "--spring-base", "--spring-macro",
];

const cssTokens = tokensIn(rootBlock(tokensText));
const docTokens = tokensIn(docTokenBlock(docText));

describe("DESIGN.md 与 styles.css 的 token 契约", () => {
  it("文档 token 表里的每一条都等于 :root 里的同名 token", () => {
    expect(docTokens.size).toBeGreaterThanOrEqual(30);
    const mismatched: string[] = [];
    for (const [name, value] of docTokens) {
      if (cssTokens.get(name) !== value) {
        mismatched.push(`${name}: 文档 ${value} / 代码 ${cssTokens.get(name) ?? "(缺失)"}`);
      }
    }
    expect(mismatched).toEqual([]);
  });

  it("代码里属于规格命名空间的 token 都写进了文档", () => {
    const undocumented = OWNED.filter((name) => cssTokens.has(name) && !docTokens.has(name));
    expect(undocumented).toEqual([]);
  });

  // 2026-09-24：吸顶标签栏写了 `background: var(--bg)`，而 --bg 这个 token 从来不存在，
  // 声明被浏览器整条丢掉 —— 于是滚动时正文从标签栏下面透出来（用户截图："透明条挡视野"）。
  // 同样的问题还有 3 处 var(--ink-blue)。这条门禁把"用了一个没定义的 token 且没有 fallback"
  // 直接变红：写错名字当场发现，而不是等用户看到透明的东西。
  it("没有 fallback 的 var(--x) 必须在样式里真的定义过", () => {
    const defined = new Set(
      Array.from(cssText.matchAll(/(--[a-z0-9-]+)\s*:/g)).map((match: RegExpMatchArray) => match[1]),
    );
    const usedWithoutFallback = Array.from(
      cssText.matchAll(/var\(\s*(--[a-z0-9-]+)\s*\)/g),
    ).map((match: RegExpMatchArray) => match[1]);
    const missing = Array.from(new Set(usedWithoutFallback)).filter((name: string) => !defined.has(name));
    expect(missing).toEqual([]);
  });
});

describe("漂移棘轮（只允许变小）", () => {
  it("低于 12px 的 font-size 必须是 0（§5 硬下限）", () => {
    // 2026-09-14 走完整条棘轮：226 → 208 → 195 → 167 → 43 → 0。
    // 从这一步起这不是预算而是门禁：任何新增的低于 12px 的字号都会直接失败。
    const BUDGET = 0;
    const sizes = (cssText.match(/font-size:\s*[0-9.]+px/g) ?? []).map((decl: string) =>
      parseFloat(decl.replace(/[^0-9.]/g, "")),
    );
    const total = sizes.length;
    const below = sizes.filter((value: number) => value < 12).length;
    expect(total).toBeGreaterThan(0);
    expect(below).toBeLessThanOrEqual(BUDGET);
  });

  it("用裸 ease 关键字的过渡数量不超过预算", () => {
    // 2026-09-14：16；Chat 页批次后：15。缓动必须走 var(--ease-*) / var(--spring-*)。
    const BUDGET = 15;
    const lines = cssText.split(/\r?\n/);
    const bare = lines.filter(
      (line: string) => /transition\s*:|animation\s*:/.test(line) && /(?<!-)\bease\b/.test(line),
    ).length;
    expect(bare).toBeLessThanOrEqual(BUDGET);
  });

  it("不在 §7 刻度上的 border-radius 数量不超过预算", () => {
    // 2026-09-14：73；Chat：69；Practice·Review：65；Library·Reader：60。刻度只允许 6 / 8 / 12 / 16，其余进棘轮。
    const BUDGET = 60;
    const scale = new Set([0, 6, 8, 12, 16]);
    const offScale = (cssText.match(/border-radius:\s*([0-9]+)px/g) ?? [])
      .map((match: string) => parseInt(match.replace(/\D+/g, ""), 10))
      .filter((value: number) => !scale.has(value)).length;
    expect(offScale).toBeLessThanOrEqual(BUDGET);
  });

  it("过渡/动画里的裸毫秒值必须是 0（时长只能走 var(--dur-*)）", () => {
    // 2026-09-14：5；Chat 页批次后：4；2026-10-17 M1：**归零**。
    //
    // 旧实现用「:root 之后」切片 ✗ —— 把 :root 之前的动画规则漏掉了，棘轮一直是**偏松**的：
    // 真实裸毫秒是 6 条，预算却只有 4。M1 拆层时暴露出来，已给 6 处动画时长上 token
    // （--dur-spin / --dur-ink / --dur-ink-soft / --dur-enter，值完全不变）并改为扫描**全部**样式。
    const BUDGET = 0;
    const bare = cssText.split(/\r?\n/).filter(
      (line: string) => /transition\s*:|animation\s*:/.test(line) && /\b[0-9]+m?s\b/.test(line),
    ).length;
    expect(bare).toBeLessThanOrEqual(BUDGET);
  });
});

/**
 * 纸张阶梯：三档表面必须可辨，但不能抢戏。
 * 2026-09-14 第一版把停靠面写成 #efeade，侧栏与右栏变成一条饱和的橄榄黄带——
 * 与画布差 9-19/255 且饱和度 0.35 > 画布的 0.29。暖纸的方向是往灰走，不是往黄走。
 */
function hexChannels(value: string, name: string): [number, number, number] {
  const match = /^#([0-9a-f]{6})$/i.exec(value);
  if (!match) throw new Error(`${name} 不是 6 位 hex：${value}`);
  const n = parseInt(match[1], 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function saturation([r, g, b]: [number, number, number]) {
  const max = Math.max(r, g, b) / 255;
  const min = Math.min(r, g, b) / 255;
  const delta = max - min;
  if (delta === 0) return 0;
  const l = (max + min) / 2;
  return l > 0.5 ? delta / (2 - max - min) : delta / (max + min);
}

function luminance([r, g, b]: [number, number, number]) {
  return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
}

function pendingThemes() {
  const themes = [{ name: ":root", block: rootBlock(tokensText) }];
  for (const match of cssText.matchAll(/\[data-paper-texture="[a-z]+"\]\s*\{[^}]*\}/g)) {
    themes.push({ name: match[0].split("{")[0].trim(), block: match[0] });
  }
  return themes;
}

describe("纸张阶梯（可辨但不突兀）", () => {
  for (const theme of pendingThemes()) {
    const own = tokensIn(theme.block);
    const value = (name: string) => own.get(name) ?? cssTokens.get(name) ?? "";
    const paper = hexChannels(/(#[0-9a-f]{6})/i.exec(value("--paper"))?.[1] ?? "", `--paper (${theme.name})`);
    const soft = hexChannels(/(#[0-9a-f]{6})/i.exec(value("--paper-soft"))?.[1] ?? "", `--paper-soft (${theme.name})`);
    const sunken = hexChannels(/(#[0-9a-f]{6})/i.exec(value("--paper-sunken"))?.[1] ?? "", `--paper-sunken (${theme.name})`);

    it(`${theme.name} 的顺序是 停靠面 < 画布 < 抬升面`, () => {
      expect(luminance(sunken)).toBeLessThan(luminance(paper));
      expect(luminance(paper)).toBeLessThan(luminance(soft));
    });

    it(`${theme.name} 与画布每个通道的差不超过 8/255`, () => {
      const tooFar = [
        ["--paper-sunken", sunken],
        ["--paper-soft", soft],
      ]
        .filter(([, channels]) =>
          (channels as number[]).some((v, i) => Math.abs(v - paper[i]) > 8),
        )
        .map(([name]) => name);
      expect(tooFar).toEqual([]);
    });

    it(`${theme.name} 的停靠面更灰，不比画布更黄`, () => {
      expect(saturation(sunken)).toBeLessThanOrEqual(saturation(paper));
    });
  }
});

/**
 * W3 F14：字体契约（把 DESIGN.md 的字体气质/字体 Token 一节变成可执行约束）。
 *
 * 为什么值得单列：CJK 字体在 Windows 上很容易「看起来能显示、其实用了系统兜底」——
 * 显式点名 + 通用兜底 + 本地打包 + 表单控件继承，四条缺一条就会在用户机器上悄悄退化。
 */
describe("字体契约（W3 F14）", () => {
  const tokens = tokensIn(rootBlock(tokensText));

  it("每个字体栈都以通用族收尾", () => {
    const generics: Record<string, string> = {
      "--font-ui": "sans-serif",
      "--font-reading": "serif",
      "--font-article": "serif",
      "--font-brand": "serif",
      "--font-mono": "monospace",
    };
    for (const [token, generic] of Object.entries(generics)) {
      const stack = tokens.get(token);
      expect(stack, `${token} 未定义`).toBeTruthy();
      expect(stack!.endsWith(generic), `${token} 应以 ${generic} 收尾`).toBe(true);
    }
  });

  it("UI 与阅读字体都显式点名了 CJK 字族", () => {
    // tokensIn 会去掉空白，所以这里也按去空白后的字族名比较。
    const cjk = ["PingFangSC", "MicrosoftYaHei", "NotoSerifSC", "SourceHanSerifSC", "SongtiSC", "SimSun"];
    for (const token of ["--font-ui", "--font-reading", "--font-article"]) {
      const stack = tokens.get(token) || "";
      expect(cjk.some((family) => stack.includes(family)), `${token} 没有点名任何 CJK 字族`).toBe(true);
    }
  });

  it("长文正文用阅读/文章字体，不把品牌字体当长文唯一字体", () => {
    const prose = [".answer-prose", ".reader-prose"];
    for (const selector of prose) {
      const start = cssText.indexOf(selector + " {");
      if (start < 0) continue;
      const rule = cssText.slice(start, cssText.indexOf("}", start));
      expect(rule.includes("--font-brand"), `${selector} 不应用品牌字体（Luo 不是完整中文字库）`).toBe(false);
    }
    expect(cssText.includes(".answer-prose {") && cssText.includes("--font-reading")).toBe(true);
    expect(cssText.includes(".reader-prose {") && cssText.includes("--font-article")).toBe(true);
  });

  it("字体本地打包，CSS 不引公共 CDN", () => {
    for (const banned of ["fonts.googleapis.com", "fonts.gstatic.com", "jsdelivr", "unpkg"]) {
      expect(cssText.includes(banned), `styles.css 不该引用 ${banned}`).toBe(false);
    }
    const faces = [...cssText.matchAll(/@font-face\s*\{[^}]*\}/g)].map((match) => match[0]);
    expect(faces.length).toBeGreaterThan(0);
    for (const face of faces) {
      expect(/url\(\s*["']?https?:/i.test(face), `@font-face 不该用远程地址`).toBe(false);
    }
  });

  it("表单控件（含 select）都继承页面字体", () => {
    // F14 实测出的真缺口：button/input/textarea 有 font: inherit，select 没有，
    // Windows 上 select 会用系统 UI 字体渲染中文选项。
    const inheritSelectors = [...cssText.matchAll(/(^|\n)([^{}\n]*)\{([^}]*)\}/g)]
      .filter((match) => /font:\s*inherit/.test(match[3]))
      .map((match) => match[2].split(",").map((part) => part.trim()));
    const coversAll = inheritSelectors.some((parts) =>
      ["button", "input", "textarea", "select"].every((control) => parts.includes(control)),
    );
    expect(coversAll, "没有一条规则把 button/input/textarea/select 一起设为 font: inherit").toBe(true);
  });
});



describe("M3 视觉技法令牌（DESIGN.md §4.4 / §4.5）", () => {
  it("表面阶梯是既有纸面色的别名，不引入新色值", () => {
    const root = tokensIn(rootBlock(tokensText));
    expect(root.get("--surface-0")).toBe("var(--paper-sunken)");
    expect(root.get("--surface-1")).toBe("var(--paper)");
    expect(root.get("--surface-2")).toBe("var(--paper-soft)");
    expect(root.get("--surface-3")).toBe("var(--paper-soft)");
    const tones = ["--surface-0", "--surface-1", "--surface-2", "--surface-3"]
      .map((name) => (root.get(name) ?? "").replace(/var\(|\)/g, ""));
    expect(new Set(tones)).toEqual(new Set(["--paper-sunken", "--paper", "--paper-soft"]));
  });

  it("发丝边与外环已入 :root，并在 2dppx 下减半", () => {
    const root = tokensIn(rootBlock(tokensText));
    expect(root.get("--hairline")).toBe("1px");
    expect(root.get("--ring") ?? "").toContain("color-mix(");
    expect(tokensText).toMatch(/@media \(min-resolution: 2dppx\)[\s\S]{0,80}--hairline:\s*0\.5px/);
  });

  it("高度阶梯与圆角补充令牌齐全，且 §7 圆角棘轮不受影响", () => {
    const root = tokensIn(rootBlock(tokensText));
    for (const name of [
      "--radius-xs", "--radius-control", "--radius-panel", "--radius-pill",
      "--h-control-sm", "--h-control", "--h-control-lg",
    ]) {
      expect(root.has(name)).toBe(true);
    }
    // §7 四档仍在（棘轮扫描的是 border-radius 字面量，不动这四档）
    for (const name of ["--radius-sm", "--radius-md", "--radius-lg", "--radius-xl"]) {
      expect(root.has(name)).toBe(true);
    }
  });

  it("§4.6 文档表同步列出所有 M3 令牌", () => {
    const doc = tokensIn(docTokenBlock(docText));
    for (const name of [
      "--surface-0", "--surface-1", "--surface-2", "--surface-3",
      "--hairline", "--ring",
      "--radius-xs", "--radius-control", "--radius-panel", "--radius-pill",
      "--h-control-sm", "--h-control", "--h-control-lg",
    ]) {
      expect(doc.has(name)).toBe(true);
    }
  });
});

const APP_CSS = readFileSync(resolve(SRC, "styles", "app.css"), "utf8");

function lastRuleBody(css: string, selector: string): string {
  const escaped = selector.replace(/[.*+?^{}()|[\]\\$]/g, "\\$&");
  const re = new RegExp(escaped + "\\s*(?:,[^{]*)?\\{([^}]*)\\}", "g");
  let last = "";
  let match: RegExpExecArray | null;
  while ((match = re.exec(css)) !== null) last = match[1];
  return last;
}

describe("M3 浮层发丝边/外环（DESIGN.md §4.5）", () => {
  const overlays = [".ui-modal-panel", ".slash-palette", ".mention-palette", ".library-more-menu > div", ".notice"];

  it("关键浮层都使用 --hairline + --ring 外环", () => {
    for (const selector of overlays) {
      const body = lastRuleBody(APP_CSS, selector);
      expect(body, selector).toContain("var(--hairline)");
      expect(body, selector).toContain("var(--ring)");
    }
  });

  it("菜单与通知不再使用硬 rgba 描边", () => {
    for (const selector of [".slash-palette", ".mention-palette", ".library-more-menu > div", ".notice"]) {
      expect(lastRuleBody(APP_CSS, selector), selector).not.toMatch(/border:\s*1px solid rgba\(/);
    }
  });
});
