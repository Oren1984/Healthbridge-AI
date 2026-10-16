/**
 * Golden scenario, end to end through the UI with three separate browser sessions:
 * a patient in Israel and two international physicians (US, UK).
 */
import { expect, test, type Page } from "@playwright/test";
import { fileURLToPath } from "node:url";
import { SAMPLES, login, resetDemo, session } from "./helpers";

test.describe.configure({ mode: "serial" });

const LETTER = fileURLToPath(new URL("05-cedar-ridge-cardiology-letter.pdf", SAMPLES));
let letterUrl = "";
let consultationUrl = "";

test.beforeAll(async () => {
  await resetDemo("fresh");
});

async function gapCard(page: Page, text: RegExp) {
  return page.getByTestId("gap-card").filter({ hasText: text }).first();
}

test("1-3. patient uploads the specialist letter; journey and recommendations update", async ({ page }) => {
  await login(page, "noa");
  await page.goto("/app/documents");
  await page.getByTestId("open-upload").click();
  await page.getByTestId("upload-file").setInputFiles(LETTER);
  await page.getByTestId("upload-submit").click();
  await page.getByRole("link", { name: /^open$/i }).click();
  await expect(page.getByText("Processed").first()).toBeVisible({ timeout: 30_000 });
  letterUrl = page.url();
  await expect(page.getByTestId("rec-row")).toHaveCount(5);
  await expect(page.getByTestId("doc-text")).toContainText("Transthoracic echocardiogram within 6 weeks");
  await expect(page.locator("mark.passage")).toHaveCount(5);

  await page.goto("/app/journey");
  await expect(page.getByTestId("journey-list")).toContainText("Cedar Ridge Cardiology Clinic - Consultation Letter");
});

test("4-5. care gap shows completion cannot be verified; clarification item created", async ({ page }) => {
  await login(page, "noa");
  await page.goto("/app/care-gaps");
  const echo = await gapCard(page, /Transthoracic echocardiogram within 6 weeks/);
  await expect(echo).toHaveAttribute("data-status", "unknown");
  await expect(echo).toContainText("An imaging report dated after the recommendation");
  await expect(echo).toContainText("CG-001");
  await echo.getByTestId("create-clarification").click();
  await expect(echo).toContainText("Clarification item created");

  await page.goto("/app/tasks");
  await expect(page.getByTestId("task-item").filter({ hasText: "Clarify: Imaging follow-up" })).toBeVisible();
});

test("6-7. patient shares selected documents and schedules a multi-physician consultation", async ({ page }) => {
  await login(page, "noa");
  await page.goto("/app/sharing");
  await page.getByTestId("new-sharing").click();
  const morganValue = await page.getByTestId("grantee-select").locator("option", { hasText: "Rachel Morgan" }).getAttribute("value");
  await page.getByTestId("grantee-select").selectOption(morganValue!);
  await page.getByRole("checkbox", { name: /Cedar Ridge Cardiology Clinic - Consultation Letter/ }).check();
  await page.getByTestId("review-sharing").click();
  await expect(page.getByTestId("sharing-preview")).toContainText("Dr. Rachel Morgan will be able to see");
  await page.getByTestId("approve-sharing").click();
  await expect(page.getByTestId("grant-row").filter({ hasText: "Rachel Morgan" })).toContainText("Active");

  await page.goto("/app/consultations");
  await page.getByTestId("new-consultation").click();
  await page.getByTestId("consult-title").fill("International cardiology second opinion");
  await page.getByTestId("pro-Morgan").check();
  await page.getByTestId("pro-Bennett").check();
  await page.getByRole("checkbox", { name: /Cedar Ridge Cardiology Clinic - Consultation Letter/ }).check();
  await page.getByTestId("schedule-submit").click();
  await expect(page).toHaveURL(/\/app\/consultations\/[0-9a-f-]+$/);
  consultationUrl = page.url();
  await page.getByTestId("share-participants").click();
  await page.getByTestId("confirm-share-participants").click();
  await expect(page.getByText("Dr. Oliver Bennett").first()).toBeVisible();
});

test("authorization: non-shared documents and non-participants are denied", async ({ browser }) => {
  const bennett = await session(browser, "bennett");
  await bennett.page.goto(consultationUrl);
  await expect(bennett.page.getByText("Shared with you").first()).toBeVisible();
  // A document Noa never shared with anyone
  const noa = await session(browser, "noa");
  await noa.page.goto("/app/documents");
  await noa.page.getByTestId("document-list").getByText("Family Medicine Visit Summary").click();
  const privateDoc = noa.page.url();
  await bennett.page.goto(privateDoc);
  await expect(bennett.page.getByRole("alert")).toContainText(/not found/i);
  // A professional who is not a participant
  const ronen = await session(browser, "ronen");
  await ronen.page.goto(consultationUrl);
  await expect(ronen.page.getByRole("alert")).toContainText(/not found/i);
  await Promise.all([bennett.ctx.close(), noa.ctx.close(), ronen.ctx.close()]);
});

test("8-9. functional video session with three participants in separate browser sessions", async ({ browser }) => {
  const people = await Promise.all((["noa", "morgan", "bennett"] as const).map((w) => session(browser, w)));
  for (const p of people) await p.page.goto(`${consultationUrl}/room`);
  for (const p of people) {
    await expect(p.page.getByTestId("connection-state")).toHaveText(/connected/i, { timeout: 30_000 });
    await expect(p.page.getByTestId("participant-count")).toHaveText("3", { timeout: 30_000 });
    // Real subscribed remote camera tracks (fake device media), not mocked UI state.
    await expect.poll(async () => Number(await p.page.getByTestId("remote-video-count").textContent()), { timeout: 30_000 }).toBeGreaterThanOrEqual(2);
  }
  // Authorized document review from within the room
  await expect(people[1].page.getByRole("link", { name: /Cedar Ridge Cardiology Clinic - Consultation Letter/ })).toBeVisible();
  await people[0].page.screenshot({ path: "test-results/video-room-patient.png" });
  await Promise.all(people.map((p) => p.ctx.close()));
});

test("10-12. physician-approved summary links to the journey; status changes only with evidence", async ({ browser }) => {
  const morgan = await session(browser, "morgan");
  const bennett = await session(browser, "bennett");
  await morgan.page.goto(consultationUrl);
  await morgan.page.getByTestId("note-input").fill("Agree that the echocardiogram should be completed first.");
  await morgan.page.getByTestId("add-note").click();
  await morgan.page.getByTestId("complete-consultation").click();
  await morgan.page.getByTestId("write-summary").click();
  await morgan.page.getByTestId("summary-discussion").fill("Reviewed the Cedar Ridge letter with the patient. Discussed the planned echocardiogram and stress test.");
  await morgan.page.getByTestId("add-followup").click();
  await morgan.page.getByTestId("followup-input").fill("Share the echocardiogram report with the consultation team");
  await morgan.page.getByTestId("save-summary").click();
  await morgan.page.getByTestId("approve-summary").click();
  await expect(morgan.page.getByTestId("summary-view")).toHaveAttribute("data-status", "pending_approval");
  await expect(morgan.page.getByTestId("summary-view")).toContainText("Waiting for approval from Dr. Oliver Bennett");

  await bennett.page.goto(consultationUrl);
  await bennett.page.getByTestId("approve-summary").click();
  await expect(bennett.page.getByTestId("summary-view")).toHaveAttribute("data-status", "approved");

  const noa = await session(browser, "noa");
  await noa.page.goto(consultationUrl);
  await noa.page.getByTestId("ack-summary").click();
  await expect(noa.page.getByText(/Acknowledged/)).toBeVisible();

  await noa.page.goto("/app/journey");
  const ev = noa.page.getByTestId("journey-list").locator("li").filter({ hasText: "International cardiology second opinion" });
  await expect(ev).toContainText("Professional-confirmed");

  await noa.page.goto("/app/care-gaps");
  await noa.page.getByRole("tab", { name: /^All/ }).click();
  await expect(await gapCard(noa.page, /Referral outcome: Consider a second opinion/)).toHaveAttribute("data-status", "completed_verified");
  const echo = await gapCard(noa.page, /Transthoracic echocardiogram within 6 weeks/);
  await expect(echo).toHaveAttribute("data-status", "unknown"); // no imaging report -> still not verified
  await Promise.all([morgan.ctx.close(), bennett.ctx.close(), noa.ctx.close()]);
});

test("13. access audit is visible to the patient, and revocation takes effect", async ({ browser }) => {
  const noa = await session(browser, "noa");
  await noa.page.goto("/app/privacy");
  await noa.page.getByLabel("Only others' activity").check();
  await expect(noa.page.getByTestId("audit-table")).toContainText("Dr. Rachel Morgan");
  await expect(noa.page.getByTestId("audit-table")).toContainText("meeting.token_issued");

  await noa.page.goto("/app/sharing");
  const activeMorgan = noa.page.getByTestId("grant-row").filter({ hasText: "Rachel Morgan" }).filter({ has: noa.page.getByTestId("revoke-grant") });
  await expect(activeMorgan.first()).toBeVisible(); // list loaded
  while (await activeMorgan.count()) {
    const before = await activeMorgan.count();
    await activeMorgan.first().getByTestId("revoke-grant").click();
    await noa.page.getByTestId("confirm-revoke").click();
    await expect(activeMorgan).toHaveCount(before - 1);
  }
  const morgan = await session(browser, "morgan");
  await morgan.page.goto(letterUrl);
  await expect(morgan.page.getByRole("alert")).toContainText(/not found/i);
  await Promise.all([noa.ctx.close(), morgan.ctx.close()]);
});
