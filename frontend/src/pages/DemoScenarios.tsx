import { useQuery } from "@tanstack/react-query";
import { LogIn } from "lucide-react";
import { useNavigate } from "react-router";
import { homeFor } from "../lib/nav";
import { Badge, Button, Card, ErrorState, Spinner } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useI18n } from "../lib/i18n";
import type { Role } from "../lib/types";
import { PublicShell } from "./PublicShell";

interface DemoData {
  scenarios: { id: string; title: string; description: string }[];
  accounts: { key: string; email: string; name: string; role: Role; country: string; password: string; specialty?: string; verified?: boolean }[];
  note: string;
}

export default function DemoScenarios() {
  const { t, tx } = useI18n();
  const { login, logout, user } = useAuth();
  const nav = useNavigate();
  const q = useQuery({ queryKey: ["demo"], queryFn: () => api.get<DemoData>("/demo/scenarios") });

  async function signIn(email: string, password: string) {
    if (user) await logout();
    const u = await login(email, password);
    nav(homeFor(u.role));
  }

  return (
    <PublicShell>
      <div className="mx-auto max-w-5xl px-4 py-10">
        <h1 className="text-2xl font-semibold">{t("demo.title")}</h1>
        <p className="mt-1 text-muted">{t("demo.subtitle")}</p>
        {q.isLoading && <Spinner />}
        {q.error && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
        {q.data && (
          <div className="mt-6 grid gap-6">
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              {q.data.scenarios.map((s) => (
                <Card key={s.id} title={s.title}>
                  <p className="text-sm text-muted">{s.description}</p>
                </Card>
              ))}
            </div>
            <p className="text-sm text-muted">{t("demo.scenarioNote")}</p>
            <Card title={t("demo.golden")}>
              <ol className="list-decimal ps-5 text-sm space-y-1">
                {t("demo.steps").split(" · ").map((s) => <li key={s}>{s}</li>)}
              </ol>
            </Card>
            <Card title={t("demo.accounts")}>
              <ul className="divide-y divide-line">
                {q.data.accounts.map((a) => (
                  <li key={a.key} className="flex flex-wrap items-center gap-3 py-3">
                    <div className="min-w-0 flex-1">
                      <div className="font-medium">{a.name} <span className="text-muted text-sm">({a.country})</span></div>
                      <div className="text-sm text-muted break-all">{a.email} · <code>{a.password}</code></div>
                    </div>
                    <Badge tone={a.role === "patient" ? "brand" : a.role === "admin" ? "neutral" : "info"}>
                      {tx("role", a.role)}{a.specialty ? ` · ${a.specialty}` : ""}
                    </Badge>
                    {a.role === "professional" && !a.verified && <Badge tone="warn">{tx("status", "pending")}</Badge>}
                    <Button size="sm" variant="secondary" icon={<LogIn className="size-4 rtl:-scale-x-100" aria-hidden />}
                      onClick={() => signIn(a.email, a.password)} data-testid={`demo-login-${a.key}`}>
                      {t("demo.useAccount")} {a.name.split(" ").slice(-1)[0]}
                    </Button>
                  </li>
                ))}
              </ul>
            </Card>
          </div>
        )}
      </div>
    </PublicShell>
  );
}
