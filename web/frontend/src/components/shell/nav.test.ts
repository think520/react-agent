import { describe, expect, it } from "vitest";
import { navItems, pageMeta } from "./nav";

describe("一级导航与页面元信息", () => {
  it("每个一级导航都有页头标题和副标题", () => {
    for (const item of navItems) {
      const key = item.to.replace(/^\//, "").split("/")[0];
      const meta = pageMeta[key];
      expect(meta, "缺少一级导航 " + key + " 的 pageMeta").toBeTruthy();
      expect(meta[0].length).toBeGreaterThan(0);
      expect(meta[1].length).toBeGreaterThan(0);
    }
  });

  it("pageMeta 不包含不存在的一级导航键", () => {
    const routes = new Set(navItems.map((item: { to: string }) => item.to.replace(/^\//, "").split("/")[0]));
    for (const key of Object.keys(pageMeta)) {
      expect(routes.has(key), "pageMeta 里的 " + key + " 不是一级导航").toBe(true);
    }
  });
});
