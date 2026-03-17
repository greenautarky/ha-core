/**
 * GA Custom Onboarding — End-to-End Tests
 *
 * Tests the full 5-step GA onboarding flow against a real HA instance
 * (stock amd64 container with the GA frontend wheel installed).
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
 *   HA_USERNAME   — admin username for reset endpoint (default: admin)
 *   HA_PASSWORD   — admin password for reset endpoint (default: changeme)
 */

import { expect, test, type Page } from "@playwright/test";

const BASE_URL = process.env.HA_BASE_URL ?? "http://localhost:8123";
const ADMIN_USER = process.env.HA_USERNAME ?? "admin";
const ADMIN_PASS = process.env.HA_PASSWORD ?? "changeme";
const ONBOARDING_URL = `${BASE_URL}/greenautarky-setup.html`;
const TIMEOUT = 30_000;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Log in as admin and return a Bearer token.
 *
 * In CI the token is pre-provisioned by the Phase 1 onboarding step and
 * stored in the ADMIN_TOKEN environment variable (set via $GITHUB_ENV).
 * HA does not support grant_type=password, so we rely on the pre-provisioned
 * token in automated environments.
 */
async function getAdminToken(): Promise<string> {
  // Use the pre-provisioned token from CI (set by Phase 1 onboarding step)
  const envToken = process.env.ADMIN_TOKEN ?? process.env.HA_ADMIN_TOKEN;
  if (envToken) {
    return envToken;
  }
  throw new Error(
    "No admin token available. Set ADMIN_TOKEN or HA_ADMIN_TOKEN environment variable. " +
      "HA does not support grant_type=password — obtain a token via the auth_code flow."
  );
}

/** Reset GA onboarding state so the wizard can run again. */
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

/** Check GA onboarding status. */
async function getOnboardingStatus(): Promise<Record<string, unknown>> {
  const resp = await fetch(`${BASE_URL}/api/greenautarky_onboarding/status`);
  return resp.json();
}

/**
 * Fill the user creation form. The form uses ha-form with shadow DOM,
 * so we target inputs by their type/autocomplete attributes.
 * Default mode is email: fields are email, password, password_confirm.
 * We switch to username mode first since the test names reference usernames.
 */
async function fillUserForm(
  page: Page,
  username: string,
  password: string
): Promise<void> {
  const formHost = page.locator("ga-setup-create-user");

  // Switch to username mode (default is email)
  await formHost.locator("a.toggle-link").click();

  // Fill username — the first text input after switching
  const usernameInput = formHost.locator("ha-textfield input[type='text']").first();
  await usernameInput.waitFor({ state: "attached", timeout: 10_000 });
  await usernameInput.fill(username);

  // Fill password — first password input
  const passwordInputs = formHost.locator("ha-textfield input[type='password']");
  await passwordInputs.first().fill(password);

  // Fill password confirm — second password input
  await passwordInputs.nth(1).fill(password);

  // Wait a moment for form validation to settle
  await page.waitForTimeout(500);

  // Click submit button ("Konto erstellen")
  await formHost.locator("ha-button").click();
}

// ---------------------------------------------------------------------------
// Test fixtures — reset state before each test
// ---------------------------------------------------------------------------

test.beforeEach(async () => {
  const token = await getAdminToken();
  await resetOnboarding(token);

  // Verify fresh state
  const status = await getOnboardingStatus();
  expect(status.completed).toBe(false);
  expect(status.steps_done).toEqual([]);
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe("GA onboarding — full flow", () => {
  test("page loads and shows welcome step", async ({ page }) => {
    page.setDefaultTimeout(TIMEOUT);
    await page.goto(ONBOARDING_URL);

    // The Lit panel should render — wait for the card content
    await expect(page.locator("ha-panel-greenautarky-setup")).toBeAttached();

    // Welcome step should be visible (first step is 'welcome')
    await expect(page.locator("ga-setup-welcome")).toBeAttached();

    // No JS errors or alert dialogs
    const dialogs: string[] = [];
    page.on("dialog", (d) => {
      dialogs.push(d.message());
      d.dismiss();
    });
    expect(dialogs).toHaveLength(0);
  });

  test("welcome → gdpr step navigation works", async ({ page }) => {
    page.setDefaultTimeout(TIMEOUT);

    const dialogs: string[] = [];
    page.on("dialog", (d) => {
      dialogs.push(d.message());
      d.dismiss();
    });

    await page.goto(ONBOARDING_URL);
    await expect(page.locator("ga-setup-welcome")).toBeAttached();

    // Click the 'Next' / 'Get started' button on the welcome step
    await page
      .locator("ga-setup-welcome")
      .getByRole("button")
      .first()
      .click();

    // GDPR step should now be visible
    await expect(page.locator("ga-setup-gdpr")).toBeAttached();
    expect(dialogs).toHaveLength(0);
  });

  test("gdpr step accepts consent and advances", async ({ page }) => {
    page.setDefaultTimeout(TIMEOUT);

    const dialogs: string[] = [];
    page.on("dialog", (d) => {
      dialogs.push(d.message());
      d.dismiss();
    });

    await page.goto(ONBOARDING_URL);

    // Welcome → GDPR
    await page.locator("ga-setup-welcome").getByRole("button").first().click();
    await expect(page.locator("ga-setup-gdpr")).toBeAttached();

    // Check the GDPR acceptance checkbox, then submit
    await page.locator("ga-setup-gdpr ha-checkbox").click();
    await page.locator("ga-setup-gdpr").getByRole("button").first().click();

    // User creation step should be visible
    await expect(page.locator("ga-setup-create-user")).toBeAttached();
    expect(dialogs).toHaveLength(0);

    // Backend should reflect GDPR accepted
    const status = await getOnboardingStatus();
    expect(status.gdpr_accepted).toBe(true);
    expect((status.steps_done as string[]).includes("gdpr")).toBe(true);
  });

  test("user creation step creates a user and advances to info pages", async ({
    page,
  }) => {
    page.setDefaultTimeout(TIMEOUT);

    const dialogs: string[] = [];
    page.on("dialog", (d) => {
      dialogs.push(d.message());
      d.dismiss();
    });

    await page.goto(ONBOARDING_URL);

    // Welcome → GDPR → User
    await page.locator("ga-setup-welcome").getByRole("button").first().click();
    await expect(page.locator("ga-setup-gdpr")).toBeAttached();
    await page.locator("ga-setup-gdpr ha-checkbox").click();
    await page.locator("ga-setup-gdpr").getByRole("button").first().click();
    await expect(page.locator("ga-setup-create-user")).toBeAttached();

    // Fill and submit user form
    await fillUserForm(page, "testuser", "SecurePassword123!");

    // Info pages step should appear (after auth is established)
    await expect(page.locator("ga-setup-info-pages")).toBeAttached({
      timeout: 15_000,
    });
    expect(dialogs).toHaveLength(0);

    // Backend should show account step done
    const status = await getOnboardingStatus();
    expect((status.steps_done as string[]).includes("account")).toBe(true);
  });

  test("analytics step completes without Unauthorized error", async ({
    page,
  }) => {
    page.setDefaultTimeout(TIMEOUT);

    // Capture any alert dialogs — there should be NONE
    const dialogs: string[] = [];
    page.on("dialog", (d) => {
      dialogs.push(d.message());
      d.dismiss();
    });

    await page.goto(ONBOARDING_URL);

    // Walk through all steps
    // 1. Welcome
    await page.locator("ga-setup-welcome").getByRole("button").first().click();

    // 2. GDPR
    await expect(page.locator("ga-setup-gdpr")).toBeAttached();
    await page.locator("ga-setup-gdpr ha-checkbox").click();
    await page.locator("ga-setup-gdpr").getByRole("button").first().click();

    // 3. User creation
    await expect(page.locator("ga-setup-create-user")).toBeAttached();
    await fillUserForm(page, "e2euser", "SecurePassword123!");

    // 4. Info pages
    await expect(page.locator("ga-setup-info-pages")).toBeAttached({
      timeout: 15_000,
    });
    await page
      .locator("ga-setup-info-pages")
      .getByRole("button")
      .first()
      .click();

    // 5. Analytics — this is the step that previously failed with Unauthorized
    await expect(page.locator("ga-setup-analytics")).toBeAttached();
    await page
      .locator("ga-setup-analytics")
      .getByRole("button")
      .first()
      .click();

    // KEY ASSERTION: no "Failed to save: Unauthorized" dialog should appear
    expect(
      dialogs.filter((d) => d.toLowerCase().includes("unauthorized"))
    ).toHaveLength(0);
    expect(
      dialogs.filter((d) => d.toLowerCase().includes("failed to save"))
    ).toHaveLength(0);
  });

  test("complete flow — redirects to / after analytics", async ({ page }) => {
    page.setDefaultTimeout(TIMEOUT);

    const dialogs: string[] = [];
    page.on("dialog", (d) => {
      dialogs.push(d.message());
      d.dismiss();
    });

    await page.goto(ONBOARDING_URL);

    // Welcome → GDPR → User → Info pages → Analytics → Done
    await page.locator("ga-setup-welcome").getByRole("button").first().click();
    await expect(page.locator("ga-setup-gdpr")).toBeAttached();
    await page.locator("ga-setup-gdpr ha-checkbox").click();
    await page.locator("ga-setup-gdpr").getByRole("button").first().click();

    await expect(page.locator("ga-setup-create-user")).toBeAttached();
    await fillUserForm(page, "finaluser", "SecurePassword123!");

    await expect(page.locator("ga-setup-info-pages")).toBeAttached({
      timeout: 15_000,
    });
    await page
      .locator("ga-setup-info-pages")
      .getByRole("button")
      .first()
      .click();

    await expect(page.locator("ga-setup-analytics")).toBeAttached();
    await page
      .locator("ga-setup-analytics")
      .getByRole("button")
      .first()
      .click();

    // After completion the frontend calls completeGASetup() and redirects to /
    await page.waitForURL(`${BASE_URL}/`, { timeout: 15_000 });

    // No error dialogs at any point
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

  test("build version footer is visible", async ({ page }) => {
    page.setDefaultTimeout(TIMEOUT);
    await page.goto(ONBOARDING_URL);
    await expect(page.locator("ha-panel-greenautarky-setup")).toBeAttached();

    // The build-id footer should show a non-empty version string
    const buildId = page.locator(".build-id");
    await expect(buildId).toBeAttached();
    const text = await buildId.textContent();
    expect(text).toMatch(/^\d{8}\.\d+-[a-f0-9]+$/); // e.g. 20251105.1-a341d17
  });
});

test.describe("GA onboarding — reset endpoint", () => {
  test("reset allows re-running the wizard", async ({ page }) => {
    page.setDefaultTimeout(TIMEOUT);

    // Complete the flow once
    const dialogs: string[] = [];
    page.on("dialog", (d) => {
      dialogs.push(d.message());
      d.dismiss();
    });

    await page.goto(ONBOARDING_URL);
    await page.locator("ga-setup-welcome").getByRole("button").first().click();
    await expect(page.locator("ga-setup-gdpr")).toBeAttached();
    await page.locator("ga-setup-gdpr ha-checkbox").click();
    await page.locator("ga-setup-gdpr").getByRole("button").first().click();

    await expect(page.locator("ga-setup-create-user")).toBeAttached();
    await fillUserForm(page, "resetuser", "SecurePassword123!");

    await expect(page.locator("ga-setup-info-pages")).toBeAttached({
      timeout: 15_000,
    });
    await page
      .locator("ga-setup-info-pages")
      .getByRole("button")
      .first()
      .click();

    await expect(page.locator("ga-setup-analytics")).toBeAttached();
    await page
      .locator("ga-setup-analytics")
      .getByRole("button")
      .first()
      .click();

    await page.waitForURL(`${BASE_URL}/`, { timeout: 15_000 });

    // Verify completed
    let status = await getOnboardingStatus();
    expect(status.completed).toBe(true);

    // Reset via API
    const token = await getAdminToken();
    await resetOnboarding(token);

    // Verify reset
    status = await getOnboardingStatus();
    expect(status.completed).toBe(false);
    expect(status.steps_done).toEqual([]);

    // Wizard should be accessible again
    const resp = await fetch(`${BASE_URL}/greenautarky-setup`, {
      redirect: "manual",
    });
    expect(resp.status).toBe(302);
    expect(resp.headers.get("location")).toBe("/greenautarky-setup.html");

    expect(dialogs.filter((d) => d.toLowerCase().includes("error"))).toHaveLength(0);
  });
});
