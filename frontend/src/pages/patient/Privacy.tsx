import { useMutation, useQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { useState } from "react";
import { Badge, Button, Card, ErrorState, Field, Input, Notice, PageHeader, Spinner } from "../../components/ui";
import { api } from "../../lib/api";
import { useAuth, useMe } from "../../lib/auth";
import { useFormat } from "../../lib/format";
import { useI18n } from "../../lib/i18n";
import type { AuditEntry, Me } from "../../lib/types";

export default function Privacy() {
  const me = useMe();
  const { setUser } = useAuth();
  const { t, tx } = useI18n();
  const f = useFormat();
  const [others, setOthers] = useState(false);
  const log = useQuery({ queryKey: ["access", me.id, others], queryFn: () => api.get<AuditEntry[]>(`/patients/${me.id}/access-log?only_others=${others}&limit=300`) });
  const [days, setDays] = useState(me.patient?.default_share_days ?? 14);
  const [alerts, setAlerts] = useState(me.patient?.show_access_alerts ?? true);
  const save = useMutation({
    mutationFn: () => api.patch<{ user: Me }>("/auth/me", { default_share_days: days, show_access_alerts: alerts }),
    onSuccess: (r) => setUser(r.user),
  });

  return (
    <>
      <PageHeader title={t("privacy.title")} subtitle={t("privacy.subtitle")} help="privacy-and-audit"
        actions={<a href={`/api/patients/${me.id}/fhir/export`} className="inline-flex items-center gap-2 rounded-lg border border-line bg-surface px-4 py-2 text-sm font-medium hover:bg-surface-2">
          <Download className="size-4" aria-hidden />{t("privacy.export")}</a>} />
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <Card className="xl:col-span-2" title={t("privacy.title")}
          action={<label className="inline-flex items-center gap-2 text-sm"><input type="checkbox" checked={others} onChange={(e) => setOthers(e.target.checked)} className="size-4 accent-[var(--primary)]" />{t("privacy.onlyOthers")}</label>}>
          {log.isLoading && <Spinner />}
          {log.error && <ErrorState error={log.error} />}
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="audit-table">
              <thead className="text-start text-xs text-muted">
                <tr><th className="text-start py-2 pe-3 font-medium">{t("common.date")}</th><th className="text-start py-2 pe-3 font-medium">{t("privacy.actor")}</th>
                  <th className="text-start py-2 pe-3 font-medium">{t("privacy.action")}</th><th className="text-start py-2 font-medium">{t("privacy.outcome")}</th></tr>
              </thead>
              <tbody className="divide-y divide-line">
                {log.data?.map((e) => (
                  <tr key={e.id}>
                    <td className="py-2 pe-3 whitespace-nowrap text-muted">{f.dateTime(e.ts)}</td>
                    <td className="py-2 pe-3">{e.actor?.full_name}{e.actor?.role && e.actor.role !== "system" ? <span className="text-muted"> · {tx("role", e.actor.role)}</span> : null}</td>
                    <td className="py-2 pe-3"><code className="text-xs">{e.action}</code>{e.resource_type ? <span className="text-muted text-xs"> · {e.resource_type}</span> : null}</td>
                    <td className="py-2"><Badge tone={e.outcome === "denied" ? "danger" : "ok"}>{e.outcome === "denied" ? t("privacy.denied") : t("privacy.success")}</Badge></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
        <div className="flex flex-col gap-6">
          <Card title={t("privacy.prefs")}>
            <div className="flex flex-col gap-4">
              <Field label={t("privacy.defaultDays")}>{(id) => <Input id={id} type="number" min={1} max={365} value={days} onChange={(e) => setDays(Number(e.target.value))} />}</Field>
              <label className="inline-flex items-center gap-2 text-sm"><input type="checkbox" checked={alerts} onChange={(e) => setAlerts(e.target.checked)} className="size-4 accent-[var(--primary)]" />{t("privacy.alerts")}</label>
              <Button onClick={() => save.mutate()} loading={save.isPending}>{t("common.save")}</Button>
              {save.isSuccess && <Notice tone="ok">{t("settings.saved")}</Notice>}
            </div>
          </Card>
          <Card title={t("privacy.rights")}><p className="text-sm text-muted">{t("privacy.rightsBody")}</p></Card>
        </div>
      </div>
    </>
  );
}
