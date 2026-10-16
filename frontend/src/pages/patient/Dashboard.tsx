import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Bell, CalendarClock, ClipboardCheck, Eye, HeartPulse, Share2 } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router";
import { Badge, Card, EmptyState, ErrorState, Spinner, StatusBadge } from "../../components/ui";
import { api } from "../../lib/api";
import { useMe } from "../../lib/auth";
import { useFormat } from "../../lib/format";
import { gapTitle } from "../../lib/gapText";
import { useI18n } from "../../lib/i18n";
import type { AuditEntry, Consultation, Doc, Gap, Grant, JourneyEvent, Notification, Rec, Task } from "../../lib/types";

function Stat({ to, icon, value, label, tone }: { to: string; icon: ReactNode; value: number | string; label: string; tone: string }) {
  return (
    <Link to={to} className="card p-4 flex items-center gap-3 hover:border-brand" data-testid={`stat-${to.split("/").pop()}`}>
      <div className={`rounded-lg p-2.5 ${tone}`}>{icon}</div>
      <div><div className="text-2xl font-semibold leading-none">{value}</div><div className="text-sm text-muted mt-1">{label}</div></div>
    </Link>
  );
}

function ViewAll({ to }: { to: string }) {
  const { t } = useI18n();
  return <Link to={to} className="inline-flex items-center gap-1 text-sm text-brand hover:underline">{t("dash.viewAll")}<ArrowRight className="size-4 rtl:-scale-x-100" aria-hidden /></Link>;
}

export default function Dashboard() {
  const me = useMe();
  const { t, tx, lang } = useI18n();
  const f = useFormat();
  const pid = me.id;
  const gaps = useQuery({ queryKey: ["gaps", pid], queryFn: () => api.get<Gap[]>(`/patients/${pid}/care-gaps`) });
  const tasks = useQuery({ queryKey: ["tasks", pid], queryFn: () => api.get<Task[]>(`/patients/${pid}/tasks`) });
  const consults = useQuery({ queryKey: ["consultations"], queryFn: () => api.get<Consultation[]>("/consultations") });
  const grants = useQuery({ queryKey: ["grants", pid], queryFn: () => api.get<{ grants: Grant[] }>(`/patients/${pid}/grants`) });
  const journey = useQuery({ queryKey: ["journey", pid, "", "", "", ""], queryFn: () => api.get<JourneyEvent[]>(`/patients/${pid}/journey`) });
  const docs = useQuery({ queryKey: ["docs", pid, "", ""], queryFn: () => api.get<Doc[]>(`/patients/${pid}/documents`) });
  const recs = useQuery({ queryKey: ["recs", pid, "pending"], queryFn: () => api.get<Rec[]>(`/patients/${pid}/recommendations?review_status=pending_review`) });
  const access = useQuery({ queryKey: ["access", pid, true], queryFn: () => api.get<AuditEntry[]>(`/patients/${pid}/access-log?only_others=true&limit=8`) });
  const notes = useQuery({ queryKey: ["notifications"], queryFn: () => api.get<{ items: Notification[]; unread: number }>("/notifications") });

  if (gaps.isLoading || tasks.isLoading) return <Spinner />;
  if (gaps.error) return <ErrorState error={gaps.error} onRetry={() => gaps.refetch()} />;

  const attention = (gaps.data ?? []).filter((g) => ["unknown", "requires_clarification", "open"].includes(g.status));
  const clarify = attention.filter((g) => g.status !== "open");
  const openTasks = (tasks.data ?? []).filter((x) => x.status === "open");
  const upcoming = (consults.data ?? []).filter((c) => ["scheduled", "in_progress"].includes(c.status));
  const activeGrants = (grants.data?.grants ?? []).filter((g) => g.state === "active");
  const showAccess = me.patient?.show_access_alerts !== false;

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">{t("dash.greeting", { name: me.full_name.split(" ")[0] })}</h1>
        <p className="text-sm text-muted mt-1">{t("dash.subtitle")}</p>
      </header>
      <div className="grid gap-3 grid-cols-2 lg:grid-cols-4">
        <Stat to="/app/care-gaps" icon={<HeartPulse className="size-5" aria-hidden />} value={clarify.length} label={t("dash.openGaps")} tone="bg-violet-soft text-violet" />
        <Stat to="/app/tasks" icon={<ClipboardCheck className="size-5" aria-hidden />} value={openTasks.length} label={t("dash.openTasks")} tone="bg-info-soft text-info" />
        <Stat to="/app/consultations" icon={<CalendarClock className="size-5" aria-hidden />} value={upcoming.length} label={t("dash.upcoming")} tone="bg-brand-soft text-brand" />
        <Stat to="/app/sharing" icon={<Share2 className="size-5" aria-hidden />} value={activeGrants.length} label={t("dash.activeShares")} tone="bg-ok-soft text-ok" />
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <div className="xl:col-span-2 flex flex-col gap-6">
          <Card title={t("dash.infoGaps")} action={<ViewAll to="/app/care-gaps" />}>
            {attention.length === 0 ? <EmptyState title={t("careGaps.empty")} /> : (
              <ul className="divide-y divide-line">
                {attention.slice(0, 6).map((g) => (
                  <li key={g.id} className="py-2.5 flex items-start gap-3">
                    <Link to={`/app/care-gaps?gap=${g.id}`} className="flex-1 text-sm hover:text-brand" dir="auto">{gapTitle(g, lang, tx)}</Link>
                    <StatusBadge status={g.status} />
                  </li>
                ))}
              </ul>
            )}
          </Card>
          {(recs.data?.length ?? 0) > 0 && (
            <Card title={t("dash.pendingReview")} action={<Badge tone="warn">{recs.data!.length}</Badge>}>
              <ul className="divide-y divide-line">
                {recs.data!.slice(0, 5).map((r) => (
                  <li key={r.id} className="py-2.5 flex flex-wrap items-center gap-2 text-sm">
                    <Badge tone="brand">{tx("kind", r.kind)}</Badge>
                    <Link to={`/app/documents/${r.document_id}`} className="flex-1 hover:text-brand" dir="auto">{r.text}</Link>
                  </li>
                ))}
              </ul>
            </Card>
          )}
          <Card title={t("dash.recentJourney")} action={<ViewAll to="/app/journey" />}>
            <ul className="divide-y divide-line">
              {(journey.data ?? []).slice(0, 5).map((e) => (
                <li key={e.id} className="py-2.5 flex flex-wrap items-center gap-2 text-sm">
                  <time className="text-muted w-28 shrink-0" dateTime={e.occurred_at}>{f.date(e.occurred_at)}</time>
                  <Link to={`/app/journey?event=${e.id}`} className="flex-1 min-w-40 hover:text-brand" dir="auto">{e.title}</Link>
                  <StatusBadge status={e.verification_status} />
                </li>
              ))}
            </ul>
          </Card>
        </div>
        <div className="flex flex-col gap-6">
          <Card title={t("dash.upcoming")} action={<ViewAll to="/app/consultations" />}>
            {upcoming.length === 0 ? <p className="text-sm text-muted">{t("consult.empty")}</p> : (
              <ul className="flex flex-col gap-3">
                {upcoming.map((c) => (
                  <li key={c.id}>
                    <Link to={`/app/consultations/${c.id}`} className="block rounded-lg border border-line p-3 hover:border-brand">
                      <p className="text-sm font-medium">{c.title}</p>
                      <p className="text-xs text-muted mt-0.5">{f.dateTime(c.scheduled_start, me.timezone)}</p>
                      <p className="text-xs text-muted mt-0.5">{c.participants.filter((p) => p.meeting_role === "professional").map((p) => `${p.user.full_name} (${p.user.country})`).join(", ")}</p>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Card>
          {showAccess && (
            <Card title={t("dash.recentAccess")} action={<ViewAll to="/app/privacy" />}>
              {(access.data ?? []).length === 0 ? <p className="text-sm text-muted">{t("dash.noAccess")}</p> : (
                <ul className="flex flex-col gap-2">
                  {access.data!.map((a) => (
                    <li key={a.id} className="flex items-start gap-2 text-sm">
                      <Eye className="size-4 mt-0.5 text-muted shrink-0" aria-hidden />
                      <span className="flex-1"><span className="font-medium">{a.actor?.full_name}</span> · {a.action} <span className="text-muted">· {f.relative(a.ts)}</span></span>
                      {a.outcome === "denied" && <Badge tone="danger">{t("privacy.denied")}</Badge>}
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          )}
          <Card title={t("dash.notifications")} action={<ViewAll to="/app/notifications" />}>
            <ul className="flex flex-col gap-2">
              {(notes.data?.items ?? []).slice(0, 4).map((n) => (
                <li key={n.id} className="flex items-start gap-2 text-sm">
                  <Bell className={`size-4 mt-0.5 shrink-0 ${n.read_at ? "text-muted" : "text-brand"}`} aria-hidden />
                  <span className={n.read_at ? "text-muted" : ""} dir="auto">{n.title}</span>
                </li>
              ))}
            </ul>
          </Card>
          <Card title={t("dash.recentDocs")} action={<ViewAll to="/app/documents" />}>
            <ul className="flex flex-col gap-2">
              {(docs.data ?? []).slice(0, 4).map((d) => (
                <li key={d.id} className="flex items-center gap-2 text-sm">
                  <Link to={`/app/documents/${d.id}`} className="flex-1 truncate hover:text-brand" dir="auto">{d.title}</Link>
                  <StatusBadge status={d.status} />
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </div>
    </div>
  );
}
