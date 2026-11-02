import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  outputDir: "./test-results",
  fullyParallel: true,
  // The mocked specs are timing-sensitive (stream buffers, animations). Running
  // one worker per core starves the shared dev server and produces false
  // failures, so the suite is pinned to a stable worker count.
  workers: 2,
  reporter: "list",
  // Start the Vite dev server automatically: every spec mocks /api, so the
  // suite needs no backend and no manually started server.
  //
  // 注意 reuseExistingServer：复用已在跑的 dev server 时，Vite 可能还端着上一版
  // CSS，本地改完样式立刻跑 Playwright 有机会拿到过期计算样式，得到假阴性
  // （2026-11-02 验证 L2-3 时踩过：回退修复后第一次仍通过）。改 CSS 后要么重启
  // dev server，要么重跑同一条 spec 确认；CI 无既有 server，不受影响。
  webServer: {
    command: "npm run dev",
    url: "http://127.0.0.1:5173",
    reuseExistingServer: true,
    timeout: 120_000,
  },
  use: {
    baseURL: "http://127.0.0.1:5173",
    channel: "chrome",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 960 } } },
    { name: "narrow-desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1180, height: 820 } } },
    { name: "mobile", use: { ...devices["Pixel 7"] } },
  ],
});
