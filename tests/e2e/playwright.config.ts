/**
 * Playwright configuration for GA onboarding e2e tests.
 *
 * Runs against a live HA instance (see ga_onboarding.spec.ts for setup).
 * The HA_BASE_URL env var controls the target (default: http://localhost:8123).
 *
 * Usage:
 *   npx playwright test --config tests/e2e/playwright.config.ts
 */

import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./",
  testMatch: "**/*.spec.ts",

  // Each test gets a fresh browser context
  fullyParallel: false, // onboarding state is shared — run sequentially

  // Retry flaky tests once in CI
  retries: process.env.CI ? 1 : 0,

  // Timeout per test (includes waiting for HA to start)
  timeout: 60_000,

  reporter: process.env.CI
    ? [["github"], ["html", { open: "never", outputFolder: "tests/e2e/report" }]]
    : [["list"], ["html", { open: "on-failure", outputFolder: "tests/e2e/report" }]],

  use: {
    baseURL: process.env.HA_BASE_URL ?? "http://localhost:8123",
    // Always use headless in CI
    headless: true,
    // Capture screenshots on failure for debugging
    screenshot: "only-on-failure",
    // Capture video on failure
    video: "retain-on-failure",
    // Trace on first retry
    trace: "on-first-retry",
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],

  // Output directory for test artifacts
  outputDir: "tests/e2e/artifacts",
});
