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
const CSS_PATH = resolve(process.cwd(), "src", "styles.css");
const DOC_PATH = resolve(process.cwd(), "..", "..", "docs", "DESIGN.md");
if (!existsSync(CSS_PATH)) throw new Error("找不到 styles.css");
if (!existsSync(DOC_PATH)) throw new Error("找不到 DESIGN.md");
const cssText = readFileSync(CSS_PATH, "utf8");
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

const cssTokens = tokensIn(rootBlock(cssText));
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
});

describe("漂移棘轮（只允许变小）", () => {
  it("低于 12px 的 font-size 数量不超过预算", () => {
    // 2026-09-14 骨架层落地后：226。每收敛一批就下调。
    const BUDGET = 226;
    const sizes = (cssText.match(/font-size:\s*[0-9.]+px/g) ?? []).map((decl: string) =>
      parseFloat(decl.replace(/[^0-9.]/g, "")),
    );
    const total = sizes.length;
    const below = sizes.filter((value: number) => value < 12).length;
    expect(total).toBeGreaterThan(0);
    expect(below).toBeLessThanOrEqual(BUDGET);
  });

  it("用裸 ease 关键字的过渡数量不超过预算", () => {
    // 2026-09-14：16。缓动必须走 var(--ease-*) / var(--spring-*)。
    const BUDGET = 16;
    const lines = cssText.split(/\r?\n/);
    const bare = lines.filter(
      (line: string) => /transition\s*:|animation\s*:/.test(line) && /(?<!-)\bease\b/.test(line),
    ).length;
    expect(bare).toBeLessThanOrEqual(BUDGET);
  });

  it("不在 §7 刻度上的 border-radius 数量不超过预算", () => {
    // 2026-09-14：73。刻度只允许 6 / 8 / 12 / 16，其余进棘轮。
    const BUDGET = 73;
    const scale = new Set([0, 6, 8, 12, 16]);
    const offScale = (cssText.match(/border-radius:\s*([0-9]+)px/g) ?? [])
      .map((match: string) => parseInt(match.replace(/\D+/g, ""), 10))
      .filter((value: number) => !scale.has(value)).length;
    expect(offScale).toBeLessThanOrEqual(BUDGET);
  });

  it("过渡里的裸毫秒值数量不超过预算", () => {
    // 2026-09-14：5。时长必须走 var(--dur-*)。
    const BUDGET = 5;
    const rootEnd = cssText.indexOf("\n}", cssText.indexOf(":root {"));
    const body = cssText.slice(rootEnd);
    const bare = body.split(/\r?\n/).filter(
      (line: string) => /transition\s*:|animation\s*:/.test(line) && /\b[0-9]+m?s\b/.test(line),
    ).length;
    expect(bare).toBeLessThanOrEqual(BUDGET);
  });
});
