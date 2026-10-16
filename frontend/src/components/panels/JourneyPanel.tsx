import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import {
  Building2, CalendarCheck, FileText, FlaskConical, Globe2, Hospital, ScanLine, Search, Send, Stethoscope, UserRound,
} from "lucide-react";
import { useState, type FormEvent, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router";
import { api, qs } from "../../lib/api";
import { toLocalInput, useFormat } from "../../lib/format";
import { useI18n } from "../../lib/i18n";
import type { JourneyEvent } from "../../lib/types";
import { Badge, Button, Dialog, EmptyState, ErrorState, Field, Input, KeyVal, Notice, Select, Spinner, StatusBadge, Textarea } from "../ui";
import { useOrgs } from "./DocumentsPanel";

export const EVENT_TYPES = ["hmo_consultation", "specialist_consultation", "hospital_visit", "lab_test", "imaging", "referral",
  "discharge", "follow_up_appointment", "international_consultation", "other"];

const ICONS: Record<string, ReactNode> = {
  hmo_consultation: <Stethoscope className="size-4" aria-hidden />, specialist_consultation: <UserRound className="size-4" aria-hidden />,
  hospital_visit: <Hospital className="size-4" aria-hidden />, lab_test: <FlaskConical className="size-4" aria-hidden />,
  imaging: <ScanLine className="size-4" aria-hidden />, referral: <Send className="size-4 rtl:-scale-x-100" aria-hidden />,
  discharge: <Hospital className="size-4" aria-hidden />, follow_up_appointment: <CalendarCheck className="size-4" aria-hidden />,
  international_consultation: <Globe2 className="size-4" aria-hidden />, other: <Building2 className="size-4" aria-hidden />,
};

function EventDetail({ id, onClose, canEdit }: { id: string; onClose: () => void; canEdit: boolean }) {
  const { t, tx } = useI18n();
  const f = useFormat();
  const q = useQuery({ queryKey: ["event", id], queryFn: () => api.get<JourneyEvent>(`/journey/${id}`) });
  const e = q.data;
  return (
    <Dialog open onClose={onClose} title={e?.title ?? t("common.loading")} wide>
      {q.isLoading && <Spinner />}
      {q.error && <ErrorState error={q.error} />}
      {e && (
        <div className="flex flex-col gap-5">
          <dl className="grid gap-4 sm:grid-cols-3">
            <KeyVal k={t("journey.type")} v={tx("event", e.event_type)} />
            <KeyVal k={t("common.date")} v={f.dateTime(e.occurred_at)} />
            <KeyVal k={t("journey.newOrg")} v={e.organization?.name ?? t("common.unknownOrg")} />
            <KeyVal k={t("journey.verification")} v={<StatusBadge status={e.verification_status} />} />
            <KeyVal k={t("journey.provenance")} v={`${tx("prov", e.provenance)}${e.provenance_detail ? ` — ${e.provenance_detail}` : ""}`} />
          </dl>
          {e.description && <p className="text-sm" dir="auto">{e.description}</p>}
          <section>
            <h3 className="text-sm font-semibold mb-2">{t("journey.documents")}</h3>
            {e.documents.length === 0 && <p className="text-sm text-muted">{t("common.none")}</p>}
            <ul className="flex flex-col gap-1">
              {e.documents.map((d) => (
                <li key={d.id}><Link to={`/app/documents/${d.id}`} className="inline-flex items-center gap-2 text-sm text-brand underline-offset-2 hover:underline">
                  <FileText className="size-4" aria-hidden />{d.title}</Link> <Badge>{tx("cat", d.category)}</Badge></li>
              ))}
            </ul>
            {e.hidden_documents > 0 && <p className="mt-1 text-xs text-muted">{t("journey.hiddenDocs", { count: e.hidden_documents })}</p>}
          </section>
          {e.recommendations && e.recommendations.length > 0 && (
            <section>
              <h3 className="text-sm font-semibold mb-2">{t("journey.recommendations")}</h3>
              <ul className="flex flex-col gap-2">
                {e.recommendations.map((r) => (
                  <li key={r.id} className="flex flex-wrap items-center gap-2 text-sm">
                    <Badge tone="brand">{tx("kind", r.kind)}</Badge><span dir="auto">{r.text}</span><StatusBadge status={r.review_status} />
                  </li>
                ))}
              </ul>
            </section>
          )}
          {canEdit && e.authorized_viewers && (
            <section>
              <h3 className="text-sm font-semibold mb-2">{t("journey.viewers")}</h3>
              {e.authorized_viewers.length === 0 ? <p className="text-sm text-muted">{t("journey.noViewers")}</p> : (
                <ul className="flex flex-col gap-1 text-sm">
                  {e.authorized_viewers.map((v) => (
                    <li key={v.id}>{v.full_name} · {v.via === "journey" ? t("journey.viaJourney") : t("journey.viaDocuments")} · {t("journey.until", { date: f.date(v.expires_at) })}</li>
                  ))}
                </ul>
              )}
            </section>
          )}
        </div>
      )}
    </Dialog>
  );
}

function AddEvent({ patientId, open, onClose }: { patientId: string; open: boolean; onClose: () => void }) {
  const { t, tx } = useI18n();
  const qc = useQueryClient();
  const orgs = useOrgs();
  const [form, setForm] = useState({ event_type: "hmo_consultation", title: "", description: "", organization_id: "", when: toLocalInput(new Date()) });
  const m = useMutation({
    mutationFn: () => api.post(`/patients/${patientId}/journey`, {
      event_type: form.event_type, title: form.title, description: form.description || null,
      organization_id: form.organization_id || null, occurred_at: new Date(form.when).toISOString(),
    }),
    onSuccess: () => { qc.invalidateQueries(); onClose(); },
  });
  const submit = (e: FormEvent) => { e.preventDefault(); m.mutate(); };
  return (
    <Dialog open={open} onClose={onClose} title={t("journey.add")}
      footer={<><Button variant="secondary" onClick={onClose}>{t("common.cancel")}</Button><Button type="submit" form="add-event" loading={m.isPending}>{t("common.save")}</Button></>}>
      <form id="add-event" onSubmit={submit} className="flex flex-col gap-4">
        <Notice>{t("journey.manualNote")}</Notice>
        <Field label={t("journey.type")}>{(id) => (
          <Select id={id} value={form.event_type} onChange={(e) => setForm({ ...form, event_type: e.target.value })}>
            {EVENT_TYPES.map((x) => <option key={x} value={x}>{tx("event", x)}</option>)}
          </Select>)}</Field>
        <Field label={t("journey.newTitle")} required>{(id) => <Input id={id} required minLength={2} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />}</Field>
        <Field label={t("journey.newWhen")} required>{(id) => <Input id={id} type="datetime-local" required value={form.when} onChange={(e) => setForm({ ...form, when: e.target.value })} />}</Field>
        <Field label={t("journey.newOrg")}>{(id) => (
          <Select id={id} value={form.organization_id} onChange={(e) => setForm({ ...form, organization_id: e.target.value })}>
            <option value="">—</option>{orgs.data?.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
          </Select>)}</Field>
        <Field label={t("journey.newDesc")}>{(id) => <Textarea id={id} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />}</Field>
        {m.error && <ErrorState error={m.error} />}
      </form>
    </Dialog>
  );
}

export function JourneyPanel({ patientId, canEdit }: { patientId: string; canEdit: boolean }) {
  const { t, tx } = useI18n();
  const f = useFormat();
  const [params, setParams] = useSearchParams();
  const [type, setType] = useState("");
  const [q, setQ] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [adding, setAdding] = useState(false);
  const selected = params.get("event");
  const events = useQuery({
    queryKey: ["journey", patientId, type, q, from, to],
    queryFn: () => api.get<JourneyEvent[]>(`/patients/${patientId}/journey${qs({ type, q, date_from: from, date_to: to })}`),
  });

  return (
    <div className="flex flex-col gap-4">
      <div className="card p-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-[1fr_auto_auto_auto_auto] items-end">
        <div className="relative">
          <Search className="absolute start-3 top-1/2 -translate-y-1/2 size-4 text-muted" aria-hidden />
          <Input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("common.search")} aria-label={t("common.search")} className="ps-9" />
        </div>
        <Select value={type} onChange={(e) => setType(e.target.value)} aria-label={t("journey.type")}>
          <option value="">{t("common.all")}</option>
          {EVENT_TYPES.map((x) => <option key={x} value={x}>{tx("event", x)}</option>)}
        </Select>
        <Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} aria-label={t("journey.from")} />
        <Input type="date" value={to} onChange={(e) => setTo(e.target.value)} aria-label={t("journey.to")} />
        {canEdit && <Button onClick={() => setAdding(true)}>{t("journey.add")}</Button>}
      </div>
      {events.isLoading && <Spinner />}
      {events.error && <ErrorState error={events.error} onRetry={() => events.refetch()} />}
      {events.data?.length === 0 && <EmptyState title={t("journey.empty")} />}
      {events.data && events.data.length > 0 && (
        <ol className="relative flex flex-col gap-3 border-s-2 border-line ms-3 ps-6" data-testid="journey-list">
          {events.data.map((e) => (
            <li key={e.id} className="relative">
              <span className={clsx("absolute -start-[37px] top-4 flex size-6 items-center justify-center rounded-full border-2 border-surface",
                e.verification_status === "documented" || e.verification_status === "professional_confirmed" ? "bg-brand text-on-brand" : "bg-warn-soft text-warn")}>
                {ICONS[e.event_type] ?? ICONS.other}
              </span>
              <button onClick={() => setParams({ event: e.id })} className="card w-full p-4 text-start hover:border-brand">
                <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
                  <time dateTime={e.occurred_at}>{f.date(e.occurred_at)}</time>
                  <span aria-hidden>·</span><span>{tx("event", e.event_type)}</span>
                  <span aria-hidden>·</span><span>{e.organization?.name ?? t("common.unknownOrg")}</span>
                </div>
                <p className="mt-1 font-medium" dir="auto">{e.title}</p>
                <div className="mt-2 flex flex-wrap items-center gap-1.5">
                  <StatusBadge status={e.verification_status} />
                  <Badge>{tx("prov", e.provenance)}</Badge>
                  {e.documents.length > 0 && <Badge tone="brand" icon={<FileText className="size-3" aria-hidden />}>{e.documents.length}</Badge>}
                  {e.hidden_documents > 0 && <span className="text-xs text-muted">{t("journey.hiddenDocs", { count: e.hidden_documents })}</span>}
                </div>
              </button>
            </li>
          ))}
        </ol>
      )}
      {selected && <EventDetail id={selected} canEdit={canEdit} onClose={() => { params.delete("event"); setParams(params); }} />}
      {canEdit && <AddEvent patientId={patientId} open={adding} onClose={() => setAdding(false)} />}
    </div>
  );
}
