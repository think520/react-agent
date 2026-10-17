import { describe, expect, it } from "vitest";

import { resolveTheme } from "./theme";

describe("主题解析（W-F6）", () => {
  it("浅色/深色偏好直接生效", () => {
    expect(resolveTheme("light", true)).toBe("light");
    expect(resolveTheme("dark", false)).toBe("dark");
  });

  it("跟随系统时按系统偏好解析", () => {
    expect(resolveTheme("system", true)).toBe("dark");
    expect(resolveTheme("system", false)).toBe("light");
  });
});
