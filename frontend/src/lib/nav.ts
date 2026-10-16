import type { Role } from "./types";

export function homeFor(role: Role) {
  return role === "patient" ? "/app/dashboard" : role === "professional" ? "/app/pro" : "/app/admin";
}
