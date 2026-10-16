import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, UserRound } from "lucide-react";
import { Link } from "react-router";
import { Badge, Button, Card, EmptyState, ErrorState, PageHeader, Spinner, StatusBadge } from "../../components/ui";
import { api } from "../../lib/api";
import { useMe } from "../../lib/auth";
import { useFormat } from "../../lib/format";
import { useI18n } from "../../lib/i18n";
import type { Consultation, Grant, Handoff } from "../../lib/types";

interface SharedPatient { patient: { id: string; full_name: string; country: string; timezone: string }; grants: Grant[] }

export default function Workspace() {
  const me = useMe();
  const { t, tx } = useI18n();
  const f = useFormat();
  const qc = useQueryClient();
  const shared = useQuery({ queryKey: ["shared-with-me"], queryFn: () => api.get<SharedPatient[]>("/shared-with-me") });
  const consults = useQuery({ queryKey: ["consultations"], queryFn: () => api.get<Consultation[]>("/consultations") });
  const handoffs = useQuery({ queryKey: ["handoffs"], queryFn: () => api.get<Handoff[]>("/handoffs") });
  const ack = useMutation({ mutationFn: (id: string) => api.post(`/handoffs/${id}/acknowledge`), onSuccess: () => qc.invalidateQueries() });
  const toMe = (handoffs.data ?? []).filter((h) => h.to.id === me.id && h.status === "shared");

  return (
    <>
      <PageHeader title={t("pro.title")} subtitle={t("pro.subtitle")} help="getting-started-professional" />
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <div className="xl:col-span-2 flex flex-col gap-6">
          <Card title={t("pro.patients")}>
            {shared.isLoading && <Spinner />}
            {shared.error && <ErrorState error={shared.error} />}
            {shared.data?.length === 0 && <EmptyState title={t("pro.noPatients")} />}
            <ul className="flex flex-col gap-3" data-testid="shared-patients">
              {shared.data?.map((s) => {
                const docs = new Set(s.grants.flatMap((g) => g.documents.map((d) => d.id))).size;
                const cats = [...new Set(s.grants.flatMap((g) => g.categories))];
                const journey = s.grants.some((g) => g.include_journey);
                const gaps = s.grants.some((g) => g.include_care_gaps);
                const until = s.grants.map((g) => g.expires_at).sort().slice(-1)[0];
                return (
                  <li key={s.patient.id}>
                    <Link to={`/app/pro/patients/${s.patient.id}`} className="flex flex-wrap items-center gap-3 rounded-lg border border-line p-3 hover:border-brand">
                      <UserRound className="size-5 text-muted" aria-hidden />
                      <div className="flex-1 min-w-0">
                        <p className="font-medium">{s.patient.full_name} <span className="text-sm text-muted">· {s.patient.country}</span></p>
                        <p className="text-xs text-muted">{t("pro.scope", { docs, cats: cats.length ? ` · ${cats.map((c) => tx("cat", c)).join(", ")}` : "", journey: journey ? ` · ${t("sharing.journey")}` : "", gaps: gaps ? ` · ${t("sharing.gaps")}` : "" })}</p>
                      </div>
                      <Badge tone="info">{t("pro.access", { date: f.date(until) })}</Badge>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </Card>
          <Card title={t("pro.consultations")}>
            {consults.data?.length === 0 && <EmptyState title={t("consult.empty")} />}
            <ul className="flex flex-col gap-2">
              {consults.data?.map((c) => (
                <li key={c.id}>
                  <Link to={`/app/consultations/${c.id}`} className="flex flex-wrap items-center gap-3 rounded-lg border border-line p-3 hover:border-brand" data-testid="pro-consultation">
                    <CalendarClock className="size-5 text-muted" aria-hidden />
                    <div className="flex-1 min-w-0"><p className="font-medium">{c.title}</p><p className="text-xs text-muted">{f.dateTime(c.scheduled_start, me.timezone)}</p></div>
                    {c.my_invite_status === "invited" && <Badge tone="warn">{tx("status", "invited")}</Badge>}
                    <StatusBadge status={c.status} />
                  </Link>
                </li>
              ))}
            </ul>
          </Card>
        </div>
        <Card title={t("pro.handoffs")}>
          {toMe.length === 0 && <p className="text-sm text-muted">{t("common.none")}</p>}
          <ul className="flex flex-col gap-3">
            {toMe.map((h) => (
              <li key={h.id} className="text-sm flex flex-col gap-1.5">
                <span><span className="font-medium">{h.from.full_name}</span>: {h.consultation?.title}</span>
                {h.note && <span className="text-muted" dir="auto">“{h.note}”</span>}
                <div className="flex gap-2">
                  {h.summary_document_id && <Link className="text-brand hover:underline" to={`/app/documents/${h.summary_document_id}`}>{t("summary.title")}</Link>}
                  {h.acknowledged_at ? <Badge tone="ok">{t("summary.acknowledged", { date: f.date(h.acknowledged_at) })}</Badge>
                    : <Button size="sm" onClick={() => ack.mutate(h.id)}>{t("pro.acknowledge")}</Button>}
                </div>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </>
  );
}
