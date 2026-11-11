import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { graphPalette, LIGHT_GRAPH_PALETTE } from "./graphPalette";

/** 知识地图画布配色契约（2026-11-11）：节点在两种主题的纸面上都要看得见。 */
const TOKENS = readFileSync(resolve(process.cwd(), "src/styles/tokens.css"), "utf8").replace(/\r\n/g, "\n");

function block(selector: string): Record<string, string> {
  const start = TOKENS.indexOf(selector + " {");
  const open = TOKENS.indexOf("{", start);
  const body = TOKENS.slice(open + 1, TOKENS.indexOf("}", open));
  const map: Record<string, string> = {};
  for (const match of body.matchAll(/(--[a-z0-9-]+)\s*:\s*([^;]+);/g)) map[match[1]] = match[2].trim();
  return map;
}

function luminance(value: string): number {
  const raw = value.replace("#", "");
  const [r, g, b] = [0, 2, 4].map((i) => {
    const c = parseInt(raw.slice(i, i + 2), 16) / 255;
    return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function ratio(a: string, b: string): number {
  const [x, y] = [luminance(a), luminance(b)];
  return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
}

const light = block(":root");
const dark = { ...light, ...block('[data-theme="dark"]') };

describe("graphPalette", () => {
  it("keeps the light node colors unchanged and takes ink / paper from the tokens", () => {
    const palette = graphPalette("light", (name) => light[name] ?? "");
    // 节点与边的颜色和改造前逐项相同；纸面与主色改为跟随令牌（旧写死值 #faf8f4 与令牌 #faf9f5 差 1/255）。
    const { inkBlue, paperSoft, paperLabel, ...nodes } = palette;
    const { inkBlue: _i, paperSoft: _p, paperLabel: _l, ...previousNodes } = LIGHT_GRAPH_PALETTE;
    expect(nodes).toEqual(previousNodes);
    expect(inkBlue).toBe(light["--blue"]);
    expect(paperSoft).toBe(light["--paper-soft"]);
    expect(paperLabel).toBe("rgba(250,249,245,0.94)");
  });

  it("follows the dark theme: label plates darken, ink lightens", () => {
    const palette = graphPalette("dark", (name) => dark[name] ?? "");
    expect(palette.paperSoft).toBe(dark["--paper-soft"]);
    expect(palette.inkBlue).toBe(dark["--blue"]);
    expect(palette.paperLabel.startsWith("rgba(36,34,32,")).toBe(true);
    // 标签文字落在标签贴片上：正文级对比度。
    expect(ratio(palette.inkBlue, palette.paperSoft)).toBeGreaterThanOrEqual(4.5);
  });

  it.each(["slateNode", "detailNode", "sageSoft", "selectedNode", "newConcept"] as const)(
    "%s stays visible as a graphic on both papers (>= 3:1)",
    (key) => {
      const lightPalette = graphPalette("light", (name) => light[name] ?? "");
      const darkPalette = graphPalette("dark", (name) => dark[name] ?? "");
      expect(ratio(darkPalette[key], dark["--paper"])).toBeGreaterThanOrEqual(3);
      expect(ratio(lightPalette[key], light["--paper"])).toBeGreaterThan(1.8);
    },
  );
});
