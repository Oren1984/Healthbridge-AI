import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, Video } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { Badge, Button, Dialog, EmptyState, ErrorState, Field, Input, Notice, PageHeader, Spinner, StatusBadge, Textarea } from "../components/ui";
import { api } from "../lib/api";
import { useMe } from "../lib/auth";
import { toLocalInput, useFormat } from "../lib/format";
import { useI18n } from "../lib/i18n";
import type { Consultation, Doc, UserBrief } from "../lib/types";

function Schedule({ onClose }: { onClose: () => void }) {
  const me = useMe();
  const { t } = useI18n();
  const f = useFormat();
  const qc = useQueryClient();
  const nav = useNavigate();
  const pros = useQuery({ queryKey: ["professionals"], queryFn: () => api.get<UserBrief[]>("/professionals") });
  const docs = useQuery({ queryKey: ["docs", me.id, "", ""], queryFn: () => api.get<Doc[]>(`/patients/${me.id}/documents`) });
  const [title, setTitle] = useState("");
  const [purpose, setPurpose] = useState("");
  const [when, setWhen] = useState(toLocalInput(new Date(Date.now() + 15 * 60_000)));
  const [duration, setDuration] = useState(45);
  const [proIds, setProIds] = useState<string[]>([]);
  const [docIds, setDocIds] = useState<string[]>([]);
  const toggle = (arr: string[], v: string, set: (x: string[]) => void) => set(arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v]);
  const m = useMutation({
    mutationFn: () => api.post<Consultation>("/consultations", { title, purpose: purpose || null, scheduled_start: new Date(when).toISOString(), duration_minutes: duration, professional_ids: proIds, document_ids: docIds }),
    onSuccess: (c) => { qc.invalidateQueries(); nav(`/app/consultations/${c.id}`); },
  });
  const start = new Date(when);
  return (
    <Dialog open onClose={onClose} title={t("consult.new")} wide
      footer={<><Button variant="secondary" onClick={onClose}>{t("common.cancel")}</Button><Button onClick={() => m.mutate()} disabled={title.length < 3 || !proIds.length} loading={m.isPending} data-testid="schedule-submit">{t("consult.new")}</Button></>}>
      <div className="flex flex-col gap-4">
        <Field label={t("journey.newTitle")} required>{(id) => <Input id={id} value={title} onChange={(e) => setTitle(e.target.value)} data-testid="consult-title" />}</Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={t("consult.when")} required>{(id) => <Input id={id} type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} />}</Field>
          <Field label={t("consult.duration")}>{(id) => <Input id={id} type="number" min={10} max={240} value={duration} onChange={(e) => setDuration(Number(e.target.value))} />}</Field>
        </div>
        <fieldset>
          <legend className="text-sm font-medium mb-2">{t("consult.professionals")}</legend>
          <div className="flex flex-col gap-1.5">
            {pros.data?.map((p) => (
              <label key={p.id} className="flex flex-wrap items-center gap-3 rounded-lg border border-line px-3 py-2 text-sm cursor-pointer">
                <input type="checkbox" checked={proIds.includes(p.id)} onChange={() => toggle(proIds, p.id, setProIds)} className="size-4 accent-[var(--primary)]" data-testid={`pro-${p.full_name.split(" ").pop()}`} />
                <span className="flex-1">{p.full_name} · {p.professional?.specialty} · {p.professional?.organization?.name}</span>
                <Badge tone="info">{p.country} · {isNaN(start.getTime()) ? "" : f.time(start.toISOString(), p.timezone)}</Badge>
              </label>
            ))}
          </div>
        </fieldset>
        <fieldset>
          <legend className="text-sm font-medium mb-1">{t("consult.documents")}</legend>
          <p className="text-xs text-muted mb-2">{t("consult.agendaNote")}</p>
          <div className="max-h-40 overflow-y-auto rounded-lg border border-line divide-y divide-line">
            {docs.data?.map((d) => (
              <label key={d.id} className="flex items-center gap-3 px-3 py-2 text-sm cursor-pointer"><input type="checkbox" checked={docIds.includes(d.id)} onChange={() => toggle(docIds, d.id, setDocIds)} className="size-4 accent-[var(--primary)]" /><span dir="auto">{d.title}</span></label>
            ))}
          </div>
        </fieldset>
        <Field label={t("consult.purpose")}>{(id) => <Textarea id={id} value={purpose} onChange={(e) => setPurpose(e.target.value)} />}</Field>
        <Notice tone="neutral">{t("consult.recordingOff")}</Notice>
        {m.error && <ErrorState error={m.error} />}
      </div>
    </Dialog>
  );
}

export default function Consultations() {
  const me = useMe();
  const { t } = useI18n();
  const f = useFormat();
  const [creating, setCreating] = useState(false);
  const q = useQuery({ queryKey: ["consultations"], queryFn: () => api.get<Consultation[]>("/consultations") });
  return (
    <>
      <PageHeader title={t("consult.title")} subtitle={t("consult.subtitle")} help="video-consultations"
        actions={me.role === "patient" ? <Button onClick={() => setCreating(true)} icon={<CalendarClock className="size-4" aria-hidden />} data-testid="new-consultation">{t("consult.new")}</Button> : undefined} />
      {q.isLoading && <Spinner />}
      {q.error && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      {q.data?.length === 0 && <EmptyState icon={<Video className="size-8" aria-hidden />} title={t("consult.empty")} />}
      <ul className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        {q.data?.map((c) => (
          <li key={c.id}>
            <Link to={`/app/consultations/${c.id}`} className="card block p-4 hover:border-brand" data-testid="consultation-card">
              <div className="flex items-start gap-2">
                <p className="flex-1 font-medium">{c.title}</p>
                <StatusBadge status={c.status} />
              </div>
              <p className="mt-1 text-sm text-muted">{f.dateTime(c.scheduled_start, me.timezone)} · {c.duration_minutes} min</p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {c.participants.map((p) => <Badge key={p.user.id} tone={p.meeting_role === "patient" ? "brand" : "info"}>{p.user.full_name} · {p.user.country}</Badge>)}
              </div>
            </Link>
          </li>
        ))}
      </ul>
      {creating && <Schedule onClose={() => setCreating(false)} />}
    </>
  );
}
