// Captures documentation screenshots from the RUNNING application (no mockups).
// Usage (stack running): node scripts/capture-screenshots.mjs
// Resets the demo to the "showcase" scenario first.
import { chromium, request } from "@playwright/test";
import { mkdirSync } from "node:fs";

const BASE = process.env.HB_BASE_URL ?? "http://127.0.0.1:8083";
const OUT = new URL("../../docs/screenshots/", import.meta.url);
const PASSWORD = "Demo-Passw0rd!";
mkdirSync(OUT, { recursive: true });
const path = (n) => decodeURIComponent(new URL(`${n}.png`, OUT).pathname).replace(/^\/([A-Z]:)/, "$1");

async function reset() {
  const api = await request.newContext({ baseURL: BASE });
  const r = await api.post("/api/auth/login", { data: { email: "admin@healthbridge.test", password: PASSWORD } });
  const { csrf_token } = await r.json();
  const x = await api.post("/api/admin/demo/reset", { data: { confirm: "RESET", scenario: "showcase" }, headers: { "X-CSRF-Token": csrf_token } });
  if (!x.ok()) throw new Error("reset failed");
  await api.dispose();
}

async function session(browser, email, opts = {}) {
  const ctx = await browser.newContext({ locale: "en-US", viewport: { width: 1440, height: 900 }, permissions: ["camera", "microphone"], ...opts });
  const page = await ctx.newPage();
  await page.goto(`${BASE}/login`);
  await page.getByLabel(/email/i).fill(email);
  await page.getByLabel(/password/i).fill(PASSWORD);
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL(/\/app\//);
  return { ctx, page };
}

async function shot(page, url, name, prep) {
  await page.goto(`${BASE}${url}`);
  await page.waitForLoadState("networkidle");
  if (prep) await prep(page);
  await page.waitForTimeout(600);
  await page.screenshot({ path: path(name) });
  console.log("captured", name);
}

await reset();
const browser = await chromium.launch({ args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"] });
const noa = await session(browser, "noa@patient.healthbridge.test");
await shot(noa.page, "/", "01-patient-dashboard");
await shot(noa.page, "/app/journey", "02-medical-journey");
await shot(noa.page, "/app/care-gaps", "03-care-gap-intelligence");
await shot(noa.page, "/app/documents", "04-documents");
await shot(noa.page, "/app/documents", "05-document-detail", async (p) => {
  await p.getByTestId("document-list").getByText("Cedar Ridge Cardiology Clinic - Consultation Letter").click();
  await p.waitForLoadState("networkidle");
});
await shot(noa.page, "/app/sharing", "06-sharing-center");
await shot(noa.page, "/app/assistant", "07-ai-assistant", async (p) => {
  await p.getByTestId("assistant-input").fill("What did the cardiologist recommend about the echocardiogram?");
  await p.getByTestId("assistant-input").press("Enter");
  await p.getByTestId("assistant-reply").first().waitFor();
});
await shot(noa.page, "/app/help", "08-help-center");

const pro = await session(browser, "dr.morgan@pro.healthbridge.test");
await shot(pro.page, "/app/pro", "09-professional-workspace");
await shot(pro.page, "/app/pro", "10-consultation-detail", async (p) => {
  await p.getByTestId("pro-consultation").first().click();
  await p.waitForLoadState("networkidle");
});
const consultUrl = pro.page.url();

// Global Care Room with three real participants (separate sessions)
const bennett = await session(browser, "dr.bennett@pro.healthbridge.test");
for (const s of [noa, pro, bennett]) await s.page.goto(`${consultUrl}/room`);
for (const s of [noa, pro, bennett]) await s.page.getByTestId("participant-count").filter({ hasText: "3" }).waitFor({ timeout: 45_000 });
await noa.page.waitForTimeout(2500);
await noa.page.screenshot({ path: path("11-global-care-room") });
console.log("captured 11-global-care-room");
for (const s of [noa, pro, bennett]) await s.page.goto(`${BASE}/app/consultations`);

// Hebrew / RTL and mobile
await noa.page.getByTestId("lang-toggle").click();
await shot(noa.page, "/app/care-gaps", "12-care-gaps-hebrew-rtl");
await noa.page.getByTestId("lang-toggle").click();
const mobile = await session(browser, "noa@patient.healthbridge.test", { viewport: { width: 390, height: 844 } });
await shot(mobile.page, "/app/dashboard", "13-mobile-dashboard");
const admin = await session(browser, "admin@healthbridge.test");
await shot(admin.page, "/app/admin", "14-administration");
await browser.close();
