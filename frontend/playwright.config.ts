import { defineConfig, devices } from "@playwright/test";

/**
 * E2E tests run against the full Docker Compose stack (http://localhost:8083).
 * They share one database, so they run serially; global setup resets the demo data.
 * Chromium's fake media devices provide real camera/microphone streams for WebRTC.
 * 127.0.0.1, not localhost: the port is published on IPv4 loopback only, and on Windows a refused ::1 attempt
 * adds seconds to every new connection.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 120_000,
  expect: { timeout: 15_000 },
  reporter: [["list"], ["json", { outputFile: "test-results/e2e-results.json" }]],
  globalSetup: "./e2e/global-setup.ts",
  use: {
    baseURL: process.env.HB_BASE_URL ?? "http://127.0.0.1:8083",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    permissions: ["camera", "microphone"],
    launchOptions: { args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"] },
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } }],
});
