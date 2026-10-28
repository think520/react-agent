import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * 主题对比度契约（2026-10-28 修订）。
 * 起因：高对比令牌初版只写了一套深色系浅色文字 —— 浅色用户打开高对比后 muted 掉到 1.10:1，
 * 契约测试只断言"令牌存在"所以全绿。这里改成按 WCAG 相对亮度**真的算比值**。
 */
const TOKENS = readFileSync(resolve(process.cwd(), "src/styles/tokens.css"), "utf8").replace(/\r\n/g, "\n");

function block(selector: string): Record<string, string> {
  const start = TOKENS.indexOf(selector);
  if (start < 0) throw new Error("找不到选择器 " + selector);
  const open = TOKENS.indexOf("{", start);
  const close = TOKENS.indexOf("}", open);
  const body = TOKENS.slice(open + 1, close);
  const map: Record<string, string> = {};
  for (const match of body.matchAll(/(--[a-z0-9-]+)\s*:\s*([^;]+);/g)) map[match[1]] = match[2].trim();
  return map;
}

function hex(value: string): [number, number, number] {
  const raw = value.trim().replace("#", "");
  const full = raw.length === 3 ? raw.split("").map((c) => c + c).join("") : raw;
  return [parseInt(full.slice(0, 2), 16), parseInt(full.slice(2, 4), 16), parseInt(full.slice(4, 6), 16)];
}

function luminance(value: string): number {
  const [r, g, b] = hex(value).map((channel) => {
    const c = channel / 255;
    return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function ratio(foreground: string, background: string): number {
  const a = luminance(foreground);
  const b = luminance(background);
  const [light, dark] = a > b ? [a, b] : [b, a];
  return (light + 0.05) / (dark + 0.05);
}

const root = block(":root");
const dark = block('[data-theme="dark"]');
const high = block('[data-contrast="high"]');
const darkHigh = block('[data-theme="dark"][data-contrast="high"]');

function theme(overrides: Array<Record<string, string>>): Record<string, string> {
  return Object.assign({}, root, ...overrides);
}

const lightNormal = theme([]);
const lightHigh = theme([high]);
const darkNormal = theme([dark]);
const darkHighTheme = theme([dark, darkHigh]);

describe("主题对比度（WCAG 2.1 AA）", () => {
  it("浅色：正文/次要/辅助文字都 ≥ 4.5:1", () => {
    expect(ratio(lightNormal["--ink"], lightNormal["--paper"])).toBeGreaterThanOrEqual(12);
    expect(ratio(lightNormal["--muted"], lightNormal["--paper"])).toBeGreaterThanOrEqual(4.5);
    expect(ratio(lightNormal["--faint"], lightNormal["--paper"])).toBeGreaterThanOrEqual(4.5);
  });

  it("浅色 + 高对比：文字必须更强，不能把静音文字变没", () => {
    expect(ratio(lightHigh["--ink"], lightHigh["--paper"])).toBeGreaterThanOrEqual(12);
    expect(ratio(lightHigh["--muted"], lightHigh["--paper"])).toBeGreaterThanOrEqual(7);
    expect(ratio(lightHigh["--faint"], lightHigh["--paper"])).toBeGreaterThanOrEqual(7);
    // 高对比必须比普通浅色更强（防止又写成深色系的浅色文字）
    expect(ratio(lightHigh["--muted"], lightHigh["--paper"])).toBeGreaterThan(ratio(lightNormal["--muted"], lightNormal["--paper"]));
  });

  it("暗色：≥ 4.5:1", () => {
    expect(ratio(darkNormal["--ink"], darkNormal["--paper"])).toBeGreaterThanOrEqual(10);
    expect(ratio(darkNormal["--muted"], darkNormal["--paper"])).toBeGreaterThanOrEqual(4.5);
    expect(ratio(darkNormal["--faint"], darkNormal["--paper"])).toBeGreaterThanOrEqual(4.5);
  });

  it("暗色 + 高对比：反向提亮，同样 ≥ 7:1", () => {
    expect(ratio(darkHighTheme["--muted"], darkHighTheme["--paper"])).toBeGreaterThanOrEqual(7);
    expect(ratio(darkHighTheme["--faint"], darkHighTheme["--paper"])).toBeGreaterThanOrEqual(7);
  });

  it("高对比必须按主题成对定义（浅色组不得复用深色的浅色文字）", () => {
    expect(Object.keys(high).length).toBeGreaterThan(0);
    expect(Object.keys(darkHigh).length).toBeGreaterThan(0);
    expect(hex(high["--muted"])[0] + hex(high["--muted"])[1] + hex(high["--muted"])[2]).toBeLessThan(
      hex(darkHigh["--muted"])[0] + hex(darkHigh["--muted"])[1] + hex(darkHigh["--muted"])[2],
    );
  });
});
