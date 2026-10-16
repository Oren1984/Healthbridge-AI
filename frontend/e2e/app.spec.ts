import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { fileURLToPath } from "node:url";
import { SAMPLES, login } from "./helpers";

test.describe.configure({ mode: "serial" });
// Sign in once and reuse the session: repeated logins would (correctly) hit the per-account rate limit.
const NOA_STATE = "e2e/.auth/noa.json"; // created in global-setup (showcase scenario)
const EMPTY = { cookies: [], origins: [] };
test.use({ storageState: NOA_STATE });

test("patient and professional login land on their home screens", async ({ page }) => {
  await login(page, "noa");
  await expect(page).toHaveURL(/\/app\/dashboard/);
  await expect(page.getByRole("heading", { name: /Hello, Noa/ })).toBeVisible();
  await page.getByRole("button", { name: /sign out/i }).click();
  await login(page, "morgan");
  await expect(page).toHaveURL(/\/app\/pro/);
  await expect(page.getByTestId("shared-patients")).toContainText("Noa Ben-David");
});

test("invalid credentials show a generic error", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel(/email/i).fill("noa@patient.healthbridge.test");
  await page.getByLabel(/password/i).fill("wrong-password");
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page.getByRole("alert")).toContainText("Invalid email or password.");
});

test("demo scenario page lists synthetic accounts and signs in", async ({ browser }) => {
  const ctx = await browser.newContext({ storageState: EMPTY }); // isolated: must not sign out the shared session
  const page = await ctx.newPage();
  await page.goto("/demo");
  await expect(page.getByText("Golden scenario — ready to consult")).toBeVisible();
  await page.getByTestId("demo-login-bennett").click();
  await expect(page).toHaveURL(/\/app\/pro/);
  await ctx.close();
});

test("malicious upload is rejected with a clear reason", async ({ page }) => {
  await page.goto("/app/dashboard");
  await page.goto("/app/documents");
  await page.getByTestId("open-upload").click();
  await page.getByTestId("upload-file").setInputFiles({ name: "invoice.pdf", mimeType: "application/pdf", buffer: Buffer.from("MZ\x90\x00 not a pdf") });
  await page.getByTestId("upload-submit").click();
  await expect(page.getByRole("alert")).toContainText("The file content is not a PDF.");
});

test("FHIR upload is processed and shows its import report", async ({ page }) => {
  await page.goto("/app/dashboard");
  await page.goto("/app/documents");
  await page.getByTestId("open-upload").click();
  const fhir = { resourceType: "Observation", id: "e2e", status: "final", code: { text: "TSH" }, effectiveDateTime: "2026-09-20", valueQuantity: { value: 1.9, unit: "mIU/L" }, method: { text: "x" } };
  await page.getByTestId("upload-file").setInputFiles({ name: "tsh.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(fhir)) });
  await page.getByTestId("upload-submit").click();
  await page.getByRole("link", { name: /^open$/i }).click();
  await expect(page.getByText("FHIR import report")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("Observation/e2e: method")).toBeVisible();
});

test("assistant answers from sources, refuses diagnosis, and requires confirmation for actions", async ({ page }) => {
  await page.goto("/app/dashboard");
  await page.goto("/app/assistant");
  const input = page.getByTestId("assistant-input");
  await input.fill("echocardiogram recommendation");
  await input.press("Enter");
  const first = page.getByTestId("assistant-reply").last();
  await expect(first).toHaveAttribute("data-mode", "deterministic");
  await expect(first.getByTestId("assistant-source").first()).toContainText("Cedar Ridge");
  await input.fill("Please diagnose my chest pain");
  await input.press("Enter");
  await expect(page.getByTestId("assistant-reply").last()).toHaveAttribute("data-mode", "refusal");
  await input.fill("remind me to request the chest X-ray report");
  await input.press("Enter");
  await page.getByTestId("confirm-action").click();
  await expect(page.getByText("Follow-up created.")).toBeVisible();
  await page.goto("/app/tasks");
  await expect(page.getByTestId("task-list")).toContainText("Request the chest X-ray report");
});

test("follow-up completion without evidence stays unverified", async ({ page }) => {
  await page.goto("/app/dashboard");
  await page.goto("/app/tasks");
  const task = page.getByTestId("task-item").filter({ hasText: "Transthoracic echocardiogram" });
  await task.getByTestId("task-complete").click();
  await page.getByRole("dialog").getByRole("button", { name: "Confirm" }).click();
  await page.getByRole("tab", { name: /Completed/ }).click();
  await expect(page.getByTestId("task-item").filter({ hasText: "Transthoracic echocardiogram" })).toContainText("Reported done — no evidence");
});

test("Help Center navigation and search", async ({ page }) => {
  await page.goto("/app/dashboard");
  await page.goto("/app/help");
  await page.getByTestId("help-search").fill("revoke");
  await page.getByTestId("help-link").filter({ hasText: "Sharing information and revoking access" }).click();
  await expect(page.getByTestId("help-article")).toContainText("Revoking stops further access");
  await page.getByRole("link", { name: "Privacy, audit history and your data rights" }).click();
  await expect(page.getByTestId("help-article")).toContainText("Tamper evidence");
  // contextual help icon on a screen
  await page.goto("/app/care-gaps");
  await page.getByRole("link", { name: /Help for this page/ }).click();
  await expect(page.getByTestId("help-article")).toContainText("Understanding care gap findings");
});

test("Hebrew / English switching changes language and direction", async ({ page }) => {
  await page.goto("/app/dashboard");
  await page.getByTestId("lang-toggle").click();
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(page.locator("html")).toHaveAttribute("lang", "he");
  await expect(page.getByRole("link", { name: "פערי רצף טיפול" })).toBeVisible();
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl"); // persisted to the profile
  await page.getByTestId("lang-toggle").click();
  await expect(page.locator("html")).toHaveAttribute("dir", "ltr");
});

test("responsive mobile layout has a menu and no horizontal overflow", async ({ browser }) => {
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, storageState: NOA_STATE });
  const page = await ctx.newPage();
  await page.goto("/app/dashboard");
  for (const path of ["/app/dashboard", "/app/care-gaps", "/app/journey", "/app/sharing"]) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, path).toBeLessThanOrEqual(1);
  }
  await page.getByRole("button", { name: "Open menu" }).click();
  await page.getByRole("dialog").getByRole("link", { name: "Follow-ups" }).click();
  await expect(page).toHaveURL(/\/app\/tasks/);
  await ctx.close();
});

test("keyboard: skip link moves focus to main content", async ({ page }) => {
  await page.goto("/app/dashboard");
  await page.reload(); // fresh page load: the skip link is the first focusable element
  await expect(page.getByRole("heading", { name: /Hello, Noa/ })).toBeVisible();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to main content" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#main")).toBeFocused();
});

test("accessibility scans (axe, WCAG 2.x A/AA rules) on key screens", async ({ page }) => {
  // One session: logging in per page would trip the (intended) per-account login rate limit.
  await page.goto("/app/dashboard");
  const report: Record<string, string[]> = {};
  for (const path of ["/app/dashboard", "/app/documents", "/app/care-gaps", "/app/tasks", "/app/sharing", "/app/consultations", "/app/assistant", "/app/privacy", "/app/help"]) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
    report[path] = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical")
      .map((v) => `${v.id}: ${v.nodes.length} node(s) — ${v.help} — ${v.nodes[0]?.target.join(" ")}`);
  }
  expect(report).toEqual(Object.fromEntries(Object.keys(report).map((k) => [k, []])));
});

test("sample documents exist for the manual demo", async () => {
  const { existsSync } = await import("node:fs");
  expect(existsSync(fileURLToPath(new URL("05-cedar-ridge-cardiology-letter.pdf", SAMPLES)))).toBeTruthy();
});
