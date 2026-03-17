/**
 * GA Custom Onboarding — End-to-End Tests
 *
 * Tests the full 5-step GA onboarding flow against a real HA instance.
 *
 * Preconditions (set up by CI before running these tests):
 *   - HA is running at BASE_URL (default http://localhost:8123)
 *   - Phase 1 (stock HA onboarding) is already completed — admin account exists
 *   - GA onboarding is in fresh state (not completed)
 *
 * Flow under test:
 *   welcome → gdpr → create user → info pages → analytics → redirect to /
 *
 * Environment variables:
 *   HA_BASE_URL   — HA instance URL (default: http://localhost:8123)
 *   ADMIN_TOKEN   — pre-provisioned admin bearer token (required)
 */

import { expect, test, type Page } from "@playwright/test";

const BASE_URL = process.env.HA_BASE_URL ?? "http://localhost:8123";
const ONBOARDING_URL = `${BASE_URL}/greenautarky-setup.html`;
const TIMEOUT = 30_000;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function getAdminToken(): Promise<string> {
  const envToken = process.env.ADMIN_TOKEN ?? process.env.HA_ADMIN_TOKEN;
  if (envToken) {
    return envToken;
  }
  throw new Error(
    "No admin token available. Set ADMIN_TOKEN environment variable."
  );
}

async function resetOnboarding(token: string): Promise<void> {
  const resp = await fetch(
    `${BASE_URL}/api/greenautarky_onboarding/reset`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    }
  );
  if (!resp.ok) {
    throw new Error(
      `Reset failed: ${resp.status} ${await resp.text()}`
    );
  }
}

async function getOnboardingStatus(): Promise<Record<string, unknown>> {
  const resp = await fetch(`${BASE_URL}/api/greenautarky_onboarding/status`);
  return resp.json();
}

/**
 * Navigate through: welcome → gdpr (check checkbox + submit).
 * Returns with the page on the user creation step.
 */
async function navigateToUserStep(page: Page): Promise<void> {
  await page.goto(ONBOARDING_URL);
  await page.locator("ga-setup-welcome").getByRole("button").first().click();
  await expect(page.locator("ga-setup-gdpr")).toBeAttached();
  await page.locator("ga-setup-gdpr ha-checkbox").click();
  await page.locator("ga-setup-gdpr").getByRole("button").first().click();
  await expect(page.locator("ga-setup-create-user")).toBeAttached();
}

/**
 * Fill the user creation form and submit.
 * Uses username mode. Targets inputs by autocomplete attribute
 * to reliably pierce shadow DOM.
 */
async function fillAndSubmitUserForm(
  page: Page,
  username: string,
  password: string
): Promise<void> {
  const formHost = page.locator("ga-setup-create-user");

  // Switch to username mode (default is email)
  await formHost.locator("a.toggle-link").click();
  await page.waitForTimeout(500);

  // Fill fields using autocomplete attributes (reliable shadow DOM piercing)
  const usernameInput = formHost.locator("input[autocomplete='username']");
  await usernameInput.waitFor({ state: "visible", timeout: 10_000 });
  await usernameInput.click();
  await usernameInput.type(username, { delay: 20 });

  const passwordInputs = formHost.locator("input[autocomplete='new-password']");
  await passwordInputs.first().click();
  await passwordInputs.first().type(password, { delay: 20 });

  await passwordInputs.nth(1).click();
  await passwordInputs.nth(1).type(password, { delay: 20 });

  // Wait for validation
  await page.waitForTimeout(1000);

  // Submit
  await formHost.locator("ha-button").click();
}

// ---------------------------------------------------------------------------
// Test fixtures — reset state before each test
// ---------------------------------------------------------------------------

test.beforeEach(async () => {
  const token = await getAdminToken();
  await resetOnboarding(token);

  const status = await getOnboardingStatus();
  expect(status.completed).toBe(false);
  expect(status.steps_done).toEqual([]);
});

// ---------------------------------------------------------------------------
// Tests — ordered so the full-flow test runs FIRST (before any state
// accumulates from partial test runs).
// ---------------------------------------------------------------------------

test.describe.serial("GA onboarding — full flow", () => {
  test("complete flow — all 5 steps ending with redirect to /", async ({
    page,
  }) => {
    page.setDefaultTimeout(TIMEOUT);

    const dialogs: string[] = [];
    page.on("dialog", (d) => {
      dialogs.push(d.message());
      d.dismiss();
    });

    // 1. Welcome → 2. GDPR → 3. User creation
    await navigateToUserStep(page);
    await fillAndSubmitUserForm(page, "e2euser", "SecurePassword123!");

    // 4. Info pages
    await expect(page.locator("ga-setup-info-pages")).toBeAttached({
      timeout: 15_000,
    });
    await page
      .locator("ga-setup-info-pages")
      .getByRole("button")
      .first()
      .click();

    // 5. Analytics
    await expect(page.locator("ga-setup-analytics")).toBeAttached();
    await page
      .locator("ga-setup-analytics")
      .getByRole("button")
      .first()
      .click();

    // After completion the frontend redirects to /
    await page.waitForURL(`${BASE_URL}/`, { timeout: 15_000 });

    // KEY ASSERTIONS: no error dialogs at any point
    expect(
      dialogs.filter(
        (d) =>
          d.toLowerCase().includes("unauthorized") ||
          d.toLowerCase().includes("failed") ||
          d.toLowerCase().includes("fehler")
      )
    ).toHaveLength(0);

    // Backend should be marked complete
    const status = await getOnboardingStatus();
    expect(status.completed).toBe(true);
  });

  test("page loads and shows welcome step", async ({ page }) => {
    page.setDefaultTimeout(TIMEOUT);
    await page.goto(ONBOARDING_URL);

    await expect(page.locator("ha-panel-greenautarky-setup")).toBeAttached();
    await expect(page.locator("ga-setup-welcome")).toBeAttached();

    const dialogs: string[] = [];
    page.on("dialog", (d) => {
      dialogs.push(d.message());
      d.dismiss();
    });
    expect(dialogs).toHaveLength(0);
  });

  test("welcome → gdpr step navigation works", async ({ page }) => {
    page.setDefaultTimeout(TIMEOUT);

    await page.goto(ONBOARDING_URL);
    await expect(page.locator("ga-setup-welcome")).toBeAttached();

    await page
      .locator("ga-setup-welcome")
      .getByRole("button")
      .first()
      .click();

    await expect(page.locator("ga-setup-gdpr")).toBeAttached();
  });

  test("gdpr step accepts consent and advances", async ({ page }) => {
    page.setDefaultTimeout(TIMEOUT);

    await page.goto(ONBOARDING_URL);

    // Welcome → GDPR
    await page.locator("ga-setup-welcome").getByRole("button").first().click();
    await expect(page.locator("ga-setup-gdpr")).toBeAttached();

    // Check the GDPR acceptance checkbox, then submit
    await page.locator("ga-setup-gdpr ha-checkbox").click();
    await page.locator("ga-setup-gdpr").getByRole("button").first().click();

    // User creation step should be visible
    await expect(page.locator("ga-setup-create-user")).toBeAttached();

    // Backend should reflect GDPR accepted
    const status = await getOnboardingStatus();
    expect(status.gdpr_accepted).toBe(true);
    expect((status.steps_done as string[]).includes("gdpr")).toBe(true);
  });

  test("user creation step creates a user and advances to info pages", async ({
    page,
  }) => {
    page.setDefaultTimeout(TIMEOUT);

    await navigateToUserStep(page);
    await fillAndSubmitUserForm(page, "testuser2", "SecurePassword123!");

    // Info pages step should appear
    await expect(page.locator("ga-setup-info-pages")).toBeAttached({
      timeout: 15_000,
    });

    // Backend should show account step done
    const status = await getOnboardingStatus();
    expect((status.steps_done as string[]).includes("account")).toBe(true);
  });

  test("build version footer is visible", async ({ page }) => {
    page.setDefaultTimeout(TIMEOUT);
    await page.goto(ONBOARDING_URL);
    await expect(page.locator("ha-panel-greenautarky-setup")).toBeAttached();

    const buildId = page.locator(".build-id");
    await expect(buildId).toBeAttached();
    const text = await buildId.textContent();
    expect(text).toMatch(/^\d{8}\.\d+-[a-f0-9]+$/);
  });
});

test.describe("GA onboarding — reset endpoint", () => {
  test("reset API clears wizard state", async () => {
    // First complete the onboarding via API calls (no browser interaction needed)
    // Mark GDPR accepted
    await fetch(`${BASE_URL}/api/greenautarky_onboarding/gdpr`, {
      method: "POST",
      body: JSON.stringify({ accepted: true }),
    });

    // Verify GDPR is marked
    let status = await getOnboardingStatus();
    expect(status.gdpr_accepted).toBe(true);

    // Reset via API
    const token = await getAdminToken();
    await resetOnboarding(token);

    // Verify reset worked
    status = await getOnboardingStatus();
    expect(status.completed).toBe(false);
    expect(status.gdpr_accepted).toBe(false);
    expect(status.steps_done).toEqual([]);
  });

  test("reset endpoint requires admin auth", async () => {
    // Anonymous request should fail
    const resp = await fetch(
      `${BASE_URL}/api/greenautarky_onboarding/reset`,
      { method: "POST" }
    );
    expect(resp.status).toBe(401);
  });
});
