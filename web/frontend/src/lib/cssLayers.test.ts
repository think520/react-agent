import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";
import { appCssFiles, readAppCss } from "./cssSources";

/**
 * M1 CSS 分层的**结构契约**（2026-10-17）。
 *
 * 目的不是「检查代码风格」，而是钉住三件容易被后续改动悄悄破坏的事：
 * 1) 入口保持很小（≤120 行），别再把几千行规则塞回去；
 * 2) 字体声明只在 fonts.css 里，且只能本地 URL（关键 CSS 不含字体，首屏不被 40MB 字体拖住）；
 * 3) 令牌只在 tokens.css 的 :root 里定义一份（app.css 不得再冒出一个 :root）。
 */

const SRC = resolve(process.cwd(), "src");
const read = (relative: string) => readFileSync(resolve(SRC, relative), "utf8");

describe("CSS 分层契约（M1）", () => {
  it("入口 styles.css ≤ 120 行，且只做 @import 编排", () => {
    const entry = read("styles.css");
    expect(entry.split("\n").length).toBeLessThanOrEqual(120);
    expect(entry).toContain('@import "tailwindcss"');
    expect(entry).toContain("./styles/tokens.css");
    expect(entry).toContain("./styles/app.css");
    expect(entry).not.toContain("@font-face");
    expect(readAppCss()).not.toContain("@font-face");
  });

  it("字体声明只在 fonts.css，且全部本地 URL、无公共 CDN", () => {
    const fonts = read("styles/fonts.css");
    expect((fonts.match(/@font-face/g) || []).length).toBeGreaterThanOrEqual(3);
    expect(fonts).toContain("Luo-Regular.woff2");
    expect(fonts).toContain("TsangerJinKai02");
    for (const banned of ["fonts.googleapis.com", "fonts.gstatic.com", "jsdelivr", "unpkg"]) {
      expect(fonts.includes(banned)).toBe(false);
    }
    expect(/url\(\s*["']?https?:/i.test(fonts)).toBe(false);
  });

  it("字体是异步加载的，不在 main.tsx 静态导入", () => {
    const main = read("main.tsx");
    expect(main).toContain('import("./styles/fonts.css")');
    expect(main).not.toContain('import "./noto-serif-sc.css"');
    expect(main).not.toContain('import "./styles/fonts.css"');
  });

  it("令牌只定义一份：tokens.css 有 :root，页面样式里没有", () => {
    expect(read("styles/tokens.css")).toContain(":root");
    expect(read("styles/tokens.css")).toContain("--paper:");
    expect(readAppCss()).not.toMatch(/^:root\s*\{/m);
  });
});

describe("没有死选择器（2026-11-11）", () => {
  it("页面样式里的每个类名都在源码里出现（动态前缀除外）", async () => {
    const { readdirSync, statSync } = await import("node:fs");
    const walk = (dir: string): string[] => readdirSync(dir).flatMap((name) => {
      const full = resolve(dir, name);
      return statSync(full).isDirectory() ? walk(full) : [full];
    });
    const source = walk(SRC)
      .filter((file) => /\.(ts|tsx)$/.test(file) && !/\.test\.(ts|tsx)$/.test(file))
      .map((file) => readFileSync(file, "utf8"))
      .join("\n") + readFileSync(resolve(process.cwd(), "index.html"), "utf8");
    // 运行时拼出来的类名前缀：`confidence-${x}`、`level-${x}`、`notice-${tone}`、"diff-" + kind、`state-${x}`。
    const DYNAMIC = /^(confidence|level|notice|diff|state)-/;
    // 测试与契约直接引用、源码里只以前缀出现的类名。
    const ALLOWED = new Set(["skeleton"]);
    const css = readAppCss().replace(/\/\*[\s\S]*?\*\//g, "");
    const classes = new Set([...css.matchAll(/\.([a-zA-Z][a-zA-Z0-9_-]*)/g)].map((match) => match[1]));
    const dead = [...classes].filter((name) => !DYNAMIC.test(name) && !ALLOWED.has(name)
      && !new RegExp(`(?<![a-zA-Z0-9_-])${name}(?![a-zA-Z0-9_-])`).test(source));
    expect(dead).toEqual([]);
  });
});

describe("app.css 只做编排（2026-11-11 拆分）", () => {
  it("app.css 只有 @import，拆出的每个文件都被引入且存在", async () => {
    const { existsSync, readdirSync } = await import("node:fs");
    const index = read("styles/app.css").replace(/\/\*[\s\S]*?\*\//g, "").trim();
    expect(index.split(/\r?\n/).every((line) => line.startsWith("@import"))).toBe(true);
    const imported = appCssFiles();
    for (const name of imported) expect(existsSync(resolve(SRC, "styles", name)), name).toBe(true);
    const onDisk = readdirSync(resolve(SRC, "styles")).filter((name) => name.endsWith(".css") && !["app.css", "tokens.css", "fonts.css"].includes(name));
    expect(onDisk.sort()).toEqual([...imported].sort());
  });
});
