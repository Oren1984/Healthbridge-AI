import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  Badge, Button, Card, ErrorState, Field, Input, Notice, PageHeader, Select, Spinner, StatusBadge, Tabs,
} from "../../components/ui";
import { useOrgs } from "../../components/panels/DocumentsPanel";
import { api } from "../../lib/api";
import { useFormat } from "../../lib/format";
import { useI18n } from "../../lib/i18n";
import type { Me } from "../../lib/types";

interface SystemInfo {
  database: string; storage_writable: boolean; livekit_reachable: boolean; ai_mode: string; demo_mode: boolean;
  ollama: { reachable: boolean; model: string; model_available: boolean };
  documents_by_status: Record<string, number>; users_by_role: Record<string, number>;
  jobs: { job: string; last_started_at: string | null; last_finished_at: string | null; last_status: string | null; last_error: string | null; runs: number; items_processed: number }[];
  metrics: { uptime_seconds: number; routes: Record<string, { count: number; errors: number; avg_ms: number; max_ms: number }>; counters: Record<string, number> };
}
interface SecEvent { id: number; ts: string; actor_id: string | null; actor_role: string | null; action: string; outcome: string; resource_type: string | null; detail: Record<string, unknown>; request_id: string | null }

function Users() {
  const { t, tx } = useI18n();
  const qc = useQueryClient();
  const orgs = useOrgs();
  const users = useQuery({ queryKey: ["admin-users"], queryFn: () => api.get<Me[]>("/admin/users") });
  const patch = useMutation({ mutationFn: ({ id, body }: { id: string; body: object }) => api.patch(`/admin/users/${id}`, body), onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-users"] }) });
  const [form, setForm] = useState({ email: "", full_name: "", role: "professional", password: "", country: "US", timezone: "America/New_York", specialty: "", organization_id: "" });
  const create = useMutation({ mutationFn: () => api.post("/admin/users", { ...form, organization_id: form.organization_id || null, specialty: form.specialty || null }), onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-users"] }) });
  return (
    <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
      <Card className="xl:col-span-2" title={t("admin.users")}>
        {users.isLoading && <Spinner />}
        {patch.error && <ErrorState error={patch.error} />}
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <tbody className="divide-y divide-line">
              {users.data?.map((u) => (
                <tr key={u.id}>
                  <td className="py-2 pe-3"><div className="font-medium">{u.full_name}</div><div className="text-xs text-muted">{u.email}</div></td>
                  <td className="py-2 pe-3"><Badge>{tx("role", u.role)}</Badge></td>
                  <td className="py-2 pe-3">{u.professional && <StatusBadge status={u.professional.verification_status} />}</td>
                  <td className="py-2 pe-3">{u.is_active ? <Badge tone="ok">{t("status.active")}</Badge> : <Badge tone="danger">{t("admin.deactivate")}</Badge>}</td>
                  <td className="py-2 text-end whitespace-nowrap">
                    {u.professional && u.professional.verification_status !== "simulated_verified" &&
                      <Button size="sm" variant="secondary" onClick={() => patch.mutate({ id: u.id, body: { verification_status: "simulated_verified" } })}>{t("admin.verifyPro")}</Button>}
                    {u.role !== "admin" && <Button size="sm" variant="ghost" onClick={() => patch.mutate({ id: u.id, body: { is_active: !u.is_active } })}>{u.is_active ? t("admin.deactivate") : t("admin.activate")}</Button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      <Card title={t("admin.createUser")}>
        <form className="flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
          <Field label={t("settings.name")}>{(id) => <Input id={id} value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />}</Field>
          <Field label={t("auth.email")}>{(id) => <Input id={id} type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />}</Field>
          <Field label={t("auth.password")}>{(id) => <Input id={id} type="password" autoComplete="new-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />}</Field>
          <Field label="Role">{(id) => <Select id={id} value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}><option value="professional">{tx("role", "professional")}</option><option value="patient">{tx("role", "patient")}</option></Select>}</Field>
          {form.role === "professional" && <>
            <Field label="Specialty">{(id) => <Input id={id} value={form.specialty} onChange={(e) => setForm({ ...form, specialty: e.target.value })} />}</Field>
            <Field label={t("docs.organization")}>{(id) => <Select id={id} value={form.organization_id} onChange={(e) => setForm({ ...form, organization_id: e.target.value })}><option value="">—</option>{orgs.data?.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}</Select>}</Field>
          </>}
          <Button type="submit" loading={create.isPending}>{t("admin.createUser")}</Button>
          {create.isSuccess && <Notice tone="ok">{t("settings.saved")}</Notice>}
          {create.error && <ErrorState error={create.error} />}
        </form>
      </Card>
    </div>
  );
}

function Security() {
  const { t } = useI18n();
  const f = useFormat();
  const [outcome, setOutcome] = useState("");
  const events = useQuery({ queryKey: ["admin-sec", outcome], queryFn: () => api.get<SecEvent[]>(`/admin/security-events${outcome ? `?outcome=${outcome}` : ""}`) });
  const verify = useMutation({ mutationFn: () => api.get<{ valid: boolean; checked: number; broken_at_id: number | null }>("/admin/audit/verify") });
  return (
    <Card title={t("admin.security")} action={
      <div className="flex gap-2">
        <Select value={outcome} onChange={(e) => setOutcome(e.target.value)} aria-label={t("privacy.outcome")} className="w-auto"><option value="">{t("common.all")}</option><option value="denied">denied</option><option value="success">success</option></Select>
        <Button size="sm" variant="secondary" onClick={() => verify.mutate()} loading={verify.isPending} data-testid="verify-audit">{t("admin.verify")}</Button>
      </div>}>
      {verify.data && <div className="mb-3"><Notice tone={verify.data.valid ? "ok" : "danger"}>{verify.data.valid ? t("admin.chainOk", { count: verify.data.checked }) : t("admin.chainBroken", { id: verify.data.broken_at_id ?? "?" })}</Notice></div>}
      {events.isLoading && <Spinner />}
      <div className="overflow-x-auto max-h-[60vh]">
        <table className="w-full text-sm">
          <tbody className="divide-y divide-line">
            {events.data?.map((e) => (
              <tr key={e.id}>
                <td className="py-1.5 pe-3 whitespace-nowrap text-muted">{f.dateTime(e.ts)}</td>
                <td className="py-1.5 pe-3"><code className="text-xs">{e.action}</code></td>
                <td className="py-1.5 pe-3">{e.actor_role ?? "—"}</td>
                <td className="py-1.5 pe-3"><Badge tone={e.outcome === "denied" ? "danger" : "ok"}>{e.outcome}</Badge></td>
                <td className="py-1.5 text-xs text-muted">{Object.keys(e.detail).length ? JSON.stringify(e.detail) : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function System() {
  const { t } = useI18n();
  const f = useFormat();
  const q = useQuery({ queryKey: ["admin-system"], queryFn: () => api.get<SystemInfo>("/admin/system"), refetchInterval: 15_000 });
  if (q.isLoading) return <Spinner />;
  if (q.error) return <ErrorState error={q.error} />;
  const s = q.data!;
  const ok = (b: boolean) => <Badge tone={b ? "ok" : "danger"}>{b ? "ok" : "unavailable"}</Badge>;
  return (
    <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
      <Card title={t("admin.system")}>
        <dl className="grid grid-cols-2 gap-3 text-sm">
          <dt>Database</dt><dd>{ok(s.database === "ok")}</dd>
          <dt>Document storage</dt><dd>{ok(s.storage_writable)}</dd>
          <dt>LiveKit</dt><dd>{ok(s.livekit_reachable)}</dd>
          <dt>Ollama (optional)</dt><dd><Badge tone={s.ollama.reachable ? "ok" : "neutral"}>{s.ollama.reachable ? `reachable · ${s.ollama.model_available ? "model ready" : "model missing"}` : "not running"}</Badge></dd>
          <dt>{t("admin.aiMode")}</dt><dd><Badge>{s.ai_mode}</Badge></dd>
          <dt>Uptime</dt><dd>{Math.round(s.metrics.uptime_seconds / 60)} min</dd>
          <dt>Documents</dt><dd>{Object.entries(s.documents_by_status).map(([k, v]) => `${k}: ${v}`).join(" · ")}</dd>
          <dt>Accounts</dt><dd>{Object.entries(s.users_by_role).map(([k, v]) => `${k}: ${v}`).join(" · ")}</dd>
        </dl>
      </Card>
      <Card title={t("admin.jobs")}>
        <ul className="flex flex-col gap-2 text-sm">
          {s.jobs.map((j) => (
            <li key={j.job} className="flex flex-wrap items-center gap-2">
              <code className="font-medium">{j.job}</code><Badge tone={j.last_status === "ok" ? "ok" : "danger"}>{j.last_status ?? "—"}</Badge>
              <span className="text-muted text-xs">runs {j.runs} · items {j.items_processed} · {f.relative(j.last_finished_at ?? j.last_started_at ?? new Date().toISOString())}{j.last_error ? ` · ${j.last_error}` : ""}</span>
            </li>
          ))}
        </ul>
        <h3 className="mt-4 mb-1 text-sm font-semibold">Counters</h3>
        <p className="text-xs text-muted">{Object.entries(s.metrics.counters).map(([k, v]) => `${k}=${v}`).join(" · ")}</p>
      </Card>
      <Card className="xl:col-span-2" title={t("admin.metrics")}>
        <div className="overflow-x-auto max-h-96">
          <table className="w-full text-xs">
            <thead><tr className="text-muted"><th className="text-start py-1">Route</th><th className="text-end">Count</th><th className="text-end">Errors</th><th className="text-end">Avg ms</th><th className="text-end">Max ms</th></tr></thead>
            <tbody className="divide-y divide-line">
              {Object.entries(s.metrics.routes).map(([r, m]) => <tr key={r}><td className="py-1"><code>{r}</code></td><td className="text-end">{m.count}</td><td className="text-end">{m.errors}</td><td className="text-end">{m.avg_ms}</td><td className="text-end">{m.max_ms}</td></tr>)}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

function Config() {
  const { t } = useI18n();
  const qc = useQueryClient();
  const cfg = useQuery({ queryKey: ["admin-config"], queryFn: () => api.get<{ ai_mode: string; environment_default_ai_mode: string }>("/admin/config") });
  const setMode = useMutation({ mutationFn: (ai_mode: string) => api.put("/admin/config", { ai_mode }), onSuccess: () => qc.invalidateQueries() });
  const [confirm, setConfirm] = useState("");
  const [scenario, setScenario] = useState("showcase");
  const reset = useMutation({ mutationFn: () => api.post<{ users: number; documents: number }>("/admin/demo/reset", { confirm, scenario }) });
  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
      <Card title={t("admin.aiMode")}>
        <div role="radiogroup" className="flex flex-col gap-2">
          {[["mock", t("admin.mock")], ["ollama", t("admin.ollama")]].map(([v, label]) => (
            <label key={v} className="inline-flex items-center gap-2 text-sm"><input type="radio" name="ai" checked={cfg.data?.ai_mode === v} onChange={() => setMode.mutate(v)} className="accent-[var(--primary)]" />{label}</label>
          ))}
        </div>
        <p className="mt-3 text-xs text-muted">Default from environment: {cfg.data?.environment_default_ai_mode}</p>
      </Card>
      <Card title={t("admin.reset")}>
        <div className="flex flex-col gap-3">
          <Select value={scenario} onChange={(e) => setScenario(e.target.value)} aria-label="Scenario"><option value="showcase">showcase</option><option value="fresh">fresh</option></Select>
          <Field label={t("admin.resetConfirm")}>{(id) => <Input id={id} value={confirm} onChange={(e) => setConfirm(e.target.value)} />}</Field>
          <Button variant="danger" disabled={confirm !== "RESET"} loading={reset.isPending} onClick={() => reset.mutate()}>{t("admin.reset")}</Button>
          {reset.isSuccess && <Notice tone="ok">{t("settings.saved")} ({reset.data.documents} documents)</Notice>}
          {reset.error && <ErrorState error={reset.error} />}
        </div>
      </Card>
    </div>
  );
}

export default function Admin() {
  const { t } = useI18n();
  const [tab, setTab] = useState("system");
  return (
    <>
      <PageHeader title={t("admin.title")} subtitle={t("admin.subtitle")} />
      <Tabs label={t("admin.title")} value={tab} onChange={setTab} tabs={[
        { id: "system", label: t("admin.system") }, { id: "users", label: t("admin.users") },
        { id: "security", label: t("admin.security") }, { id: "config", label: t("admin.config") },
      ]} />
      {tab === "system" && <System />}
      {tab === "users" && <Users />}
      {tab === "security" && <Security />}
      {tab === "config" && <Config />}
    </>
  );
}
