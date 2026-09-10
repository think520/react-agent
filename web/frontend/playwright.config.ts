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
