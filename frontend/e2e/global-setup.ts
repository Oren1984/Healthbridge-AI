import { request } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { BASE, EMAIL, PASSWORD, resetDemo } from "./helpers";

export const NOA_STATE = "e2e/.auth/noa.json";

/** Showcase data for app.spec (golden-scenario.spec resets to "fresh" itself) plus one reusable patient session. */
export default async function globalSetup() {
  await resetDemo("showcase");
  mkdirSync("e2e/.auth", { recursive: true });
  const api = await request.newContext({ baseURL: BASE });
  const r = await api.post("/api/auth/login", { data: { email: EMAIL.noa, password: PASSWORD } });
  if (!r.ok()) throw new Error(`login failed: ${r.status()}`);
  await api.storageState({ path: NOA_STATE });
  await api.dispose();
}
