import { expect, type Browser, type BrowserContext, type Page, request } from "@playwright/test";

export const PASSWORD = "Demo-Passw0rd!";
export const EMAIL = {
  noa: "noa@patient.healthbridge.test",
  daniel: "daniel@patient.healthbridge.test",
  ronen: "dr.ronen@pro.healthbridge.test",
  morgan: "dr.morgan@pro.healthbridge.test",
  bennett: "dr.bennett@pro.healthbridge.test",
  admin: "admin@healthbridge.test",
} as const;
export type Who = keyof typeof EMAIL;
export const BASE = process.env.HB_BASE_URL ?? "http://127.0.0.1:8083";
export const SAMPLES = new URL("../../demo/sample-documents/", import.meta.url);

export async function login(page: Page, who: Who) {
  await page.goto("/login");
  await page.getByLabel(/email/i).fill(EMAIL[who]);
  await page.getByLabel(/password/i).fill(PASSWORD);
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page).toHaveURL(/\/app\//);
}

/** A separate browser context = separate cookies/session, like a different person's browser. */
export async function session(browser: Browser, who: Who): Promise<{ ctx: BrowserContext; page: Page }> {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await login(page, who);
  return { ctx, page };
}

export async function resetDemo(scenario: "fresh" | "showcase") {
  const api = await request.newContext({ baseURL: BASE });
  const r = await api.post("/api/auth/login", { data: { email: EMAIL.admin, password: PASSWORD } });
  const { csrf_token } = await r.json();
  const reset = await api.post("/api/admin/demo/reset", { data: { confirm: "RESET", scenario }, headers: { "X-CSRF-Token": csrf_token } });
  expect(reset.ok()).toBeTruthy();
  await api.dispose();
}
