import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileLock2, FileText, Lock, Plus, Sparkles, Trash2, Video } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import {
  Badge, Button, ButtonLink, Card, Dialog, EmptyState, ErrorState, Field, Input, Notice, PageHeader, Select, Spinner, StatusBadge, Textarea,
} from "../components/ui";
import { api } from "../lib/api";
import { useMe } from "../lib/auth";
import { toLocalInput, useFormat } from "../lib/format";
import { useI18n } from "../lib/i18n";
import type { Consultation, Handoff, Summary, UserBrief } from "../lib/types";

function SummaryEditor({ c, base, onClose }: { c: Consultation; base?: Summary; onClose: () => void }) {
  const { t } = useI18n();
  const qc = useQueryClient();
  const me = useMe();
  const [discussion, setDiscussion] = useState(base?.discussion ?? "");
  const [observation, setObservation] = useState(base?.observations.find((o) => o.author_id === me.id)?.text ?? "");
  const [followups, setFollowups] = useState<{ title: string; description?: string | null }[]>(base?.proposed_followups ?? []);
  const [refs, setRefs] = useState<string[]>(base?.referenced_document_ids ?? []);
  const [aiDraft, setAiDraft] = useState(base?.ai_generated_draft ?? false);
  const [draftLabel, setDraftLabel] = useState<string | null>(null);
  const draft = useMutation({
    mutationFn: () => api.post<{ discussion: string; referenced_document_ids: string[]; label: string }>(`/consultations/${c.id}/summaries/draft`),
    onSuccess: (d) => { setDiscussion(d.discussion); setRefs(d.referenced_document_ids.filter((id) => c.documents.find((x) => x.id === id)?.accessible)); setAiDraft(true); setDraftLabel(d.label); },
  });
  const save = useMutation({
    mutationFn: () => api.post(`/consultations/${c.id}/summaries`, {
      discussion, observation: observation || null, proposed_followups: followups.filter((x) => x.title.trim().length >= 3),
      referenced_document_ids: refs, ai_generated_draft: aiDraft,
    }),
    onSuccess: () => { qc.invalidateQueries(); onClose(); },
  });
  return (
    <Dialog open onClose={onClose} title={base ? t("summary.newVersion") : t("summary.write")} wide
      footer={<><Button variant="secondary" onClick={onClose}>{t("common.cancel")}</Button><Button onClick={() => save.mutate()} disabled={discussion.trim().length < 10} loading={save.isPending} data-testid="save-summary">{t("common.save")}</Button></>}>
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" variant="secondary" icon={<Sparkles className="size-4" aria-hidden />} onClick={() => draft.mutate()} loading={draft.isPending}>{t("summary.draftFromNotes")}</Button>
          {aiDraft && <Badge tone="violet">{t("summary.aiBadge")}</Badge>}
        </div>
        {draftLabel && <Notice tone="warn">{t("summary.draftLabel")}</Notice>}
        <Field label={t("summary.discussion")} required>{(id) => <Textarea id={id} className="min-h-40" value={discussion} onChange={(e) => setDiscussion(e.target.value)} dir="auto" data-testid="summary-discussion" />}</Field>
        <Field label={t("summary.observation")}>{(id) => <Textarea id={id} value={observation} onChange={(e) => setObservation(e.target.value)} dir="auto" />}</Field>
        <fieldset className="flex flex-col gap-2">
          <legend className="text-sm font-medium mb-1">{t("summary.followups")}</legend>
          {followups.map((fu, i) => (
            <div key={i} className="flex gap-2">
              <Input aria-label={t("summary.followups")} value={fu.title} onChange={(e) => setFollowups(followups.map((x, j) => (j === i ? { ...x, title: e.target.value } : x)))} data-testid="followup-input" />
              <Button size="sm" variant="ghost" aria-label={t("common.delete")} onClick={() => setFollowups(followups.filter((_, j) => j !== i))} icon={<Trash2 className="size-4" aria-hidden />} />
            </div>
          ))}
          <Button size="sm" variant="secondary" className="self-start" icon={<Plus className="size-4" aria-hidden />} onClick={() => setFollowups([...followups, { title: "" }])} data-testid="add-followup">{t("summary.addFollowup")}</Button>
        </fieldset>
        <fieldset>
          <legend className="text-sm font-medium mb-1">{t("summary.referenced")}</legend>
          {c.documents.filter((d) => d.accessible).map((d) => (
            <label key={d.id} className="flex items-center gap-2 text-sm"><input type="checkbox" className="size-4 accent-[var(--primary)]" checked={refs.includes(d.id)} onChange={() => setRefs(refs.includes(d.id) ? refs.filter((x) => x !== d.id) : [...refs, d.id])} />{d.title}</label>
          ))}
        </fieldset>
        {(draft.error || save.error) && <ErrorState error={draft.error ?? save.error} />}
      </div>
    </Dialog>
  );
}

function SummaryView({ s, c, isPro, isPatient }: { s: Summary; c: Consultation; isPro: boolean; isPatient: boolean }) {
  const { t } = useI18n();
  const f = useFormat();
  const me = useMe();
  const qc = useQueryClient();
  const [comment, setComment] = useState("");
  const [handoff, setHandoff] = useState(false);
  const [to, setTo] = useState("");
  const [note, setNote] = useState("");
  const pros = useQuery({ queryKey: ["professionals"], queryFn: () => api.get<UserBrief[]>("/professionals"), enabled: handoff });
  const act = useMutation({ mutationFn: (p: { path: string; body?: object }) => api.post(p.path, p.body ?? {}), onSuccess: () => { qc.invalidateQueries(); setHandoff(false); } });
  const names = (ids: string[]) => c.participants.filter((p) => ids.includes(p.user.id)).map((p) => p.user.full_name).join(", ");
  const myDecision = s.approvals.find((a) => a.professional.id === me.id);
  const participantIds = new Set(c.participants.map((p) => p.user.id));
  return (
    <article className="flex flex-col gap-4" data-testid="summary-view" data-status={s.status}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold">{t("summary.version", { n: s.version })}</span>
        <StatusBadge status={s.status} />
        {s.ai_generated_draft && <Badge tone="violet" icon={<Sparkles className="size-3" aria-hidden />}>{t("summary.aiBadge")}</Badge>}
        <span className="text-xs text-muted">{s.author.full_name} · {f.dateTime(s.created_at)}</span>
      </div>
      <p className="whitespace-pre-wrap text-sm" dir="auto">{s.discussion}</p>
      {s.observations.length > 0 && (
        <section><h4 className="text-sm font-semibold mb-1">{t("summary.observations")}</h4>
          <ul className="flex flex-col gap-1 text-sm">{s.observations.map((o) => <li key={o.author_id}><span className="font-medium">{o.author_name}:</span> <span dir="auto">{o.text}</span></li>)}</ul></section>
      )}
      {s.proposed_followups.length > 0 && (
        <section><h4 className="text-sm font-semibold mb-1">{t("summary.followups")}</h4>
          <ul className="list-disc ps-5 text-sm">{s.proposed_followups.map((fu, i) => <li key={i} dir="auto">{fu.title}</li>)}</ul></section>
      )}
      <section>
        <h4 className="text-sm font-semibold mb-1">{t("summary.approvedBy")}</h4>
        <ul className="flex flex-wrap gap-1.5">{s.approvals.map((a) => <li key={a.professional.id}><Badge tone={a.decision === "approved" ? "ok" : "warn"}>{a.professional.full_name}: {a.decision === "approved" ? t("status.approved") : t("status.changes_requested")}{a.comment ? ` — ${a.comment}` : ""}</Badge></li>)}</ul>
        {s.status === "pending_approval" && s.awaiting_approval_from.length > 0 && <p className="mt-1 text-xs text-muted">{t("summary.awaiting", { names: names(s.awaiting_approval_from) })}</p>}
        <p className="mt-1 text-xs text-muted">{t("summary.consensusNote")}</p>
      </section>
      {s.document_id && <Link className="text-sm text-brand hover:underline inline-flex items-center gap-1" to={`/app/documents/${s.document_id}`}><FileText className="size-4" aria-hidden />{t("summary.title")}</Link>}
      {s.patient_acknowledged_at && <p className="text-xs text-muted">{t("summary.acknowledged", { date: f.dateTime(s.patient_acknowledged_at) })}</p>}
      {act.error && <ErrorState error={act.error} />}
      <div className="flex flex-wrap gap-2">
        {isPro && s.status === "pending_approval" && myDecision?.decision !== "approved" && (
          <>
            <Input className="max-w-xs" placeholder={t("common.notes")} aria-label={t("common.notes")} value={comment} onChange={(e) => setComment(e.target.value)} />
            <Button size="sm" onClick={() => act.mutate({ path: `/summaries/${s.id}/approve`, body: { comment: comment || null } })} data-testid="approve-summary">{t("summary.approve")}</Button>
            <Button size="sm" variant="secondary" disabled={!comment} onClick={() => act.mutate({ path: `/summaries/${s.id}/request-changes`, body: { comment } })}>{t("summary.requestChanges")}</Button>
          </>
        )}
        {isPatient && s.status === "approved" && !s.patient_acknowledged_at && <Button size="sm" onClick={() => act.mutate({ path: `/summaries/${s.id}/acknowledge` })} data-testid="ack-summary">{t("summary.acknowledge")}</Button>}
        {s.status === "approved" && (isPro || isPatient) && <Button size="sm" variant="secondary" onClick={() => setHandoff(true)}>{t("summary.handoff")}</Button>}
      </div>
      <Dialog open={handoff} onClose={() => setHandoff(false)} title={t("summary.handoff")}
        footer={<><Button variant="secondary" onClick={() => setHandoff(false)}>{t("common.cancel")}</Button><Button disabled={!to} loading={act.isPending} onClick={() => act.mutate({ path: `/summaries/${s.id}/handoffs`, body: { to_user_id: to, note: note || null } })}>{t("common.confirm")}</Button></>}>
        <div className="flex flex-col gap-4">
          {isPro && <Notice>{t("summary.handoffPatientNote")}</Notice>}
          <Field label={t("sharing.recipient")}>{(id) => <Select id={id} value={to} onChange={(e) => setTo(e.target.value)}><option value="">{t("sharing.selectRecipient")}</option>{pros.data?.filter((p) => !participantIds.has(p.id)).map((p) => <option key={p.id} value={p.id}>{p.full_name} — {p.professional?.specialty}</option>)}</Select>}</Field>
          <Field label={t("summary.handoffNote")}>{(id) => <Textarea id={id} value={note} onChange={(e) => setNote(e.target.value)} />}</Field>
        </div>
      </Dialog>
    </article>
  );
}

export default function ConsultationDetail() {
  const { id = "" } = useParams();
  const me = useMe();
  const { t, tx } = useI18n();
  const f = useFormat();
  const qc = useQueryClient();
  const nav = useNavigate();
  const [note, setNote] = useState("");
  const [editor, setEditor] = useState<{ base?: Summary } | null>(null);
  const [shareOpen, setShareOpen] = useState(false);
  const [shareDays, setShareDays] = useState(14);
  const [resched, setResched] = useState<string | null>(null);
  const q = useQuery({ queryKey: ["consultation", id], queryFn: () => api.get<Consultation>(`/consultations/${id}`), refetchInterval: 15_000 });
  const summaries = useQuery({ queryKey: ["summaries", id], queryFn: () => api.get<Summary[]>(`/consultations/${id}/summaries`) });
  const handoffs = useQuery({ queryKey: ["handoffs"], queryFn: () => api.get<Handoff[]>("/handoffs") });
  const act = useMutation({ mutationFn: (p: { path: string; body?: object; method?: "patch" }) => (p.method === "patch" ? api.patch(p.path, p.body) : api.post(p.path, p.body ?? {})), onSuccess: () => { qc.invalidateQueries(); setNote(""); setShareOpen(false); setResched(null); } });

  if (q.isLoading) return <Spinner />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const c = q.data!;
  const isPatient = !!c.can_manage;
  const isPro = !!c.is_professional_participant;
  const active = ["scheduled", "in_progress"].includes(c.status);
  const windowOpen = c.join_window && new Date() >= new Date(c.join_window.opens) && new Date() <= new Date(c.join_window.closes);
  const current = summaries.data?.find((s) => s.status === "pending_approval") ?? summaries.data?.find((s) => s.status === "approved");
  const pendingAck = (handoffs.data ?? []).filter((h) => h.to.id === me.id && h.status === "shared" && !h.acknowledged_at && h.consultation?.id === c.id);

  return (
    <>
      <PageHeader title={c.title} subtitle={`${f.dateTime(c.scheduled_start, me.timezone)} · ${c.duration_minutes} min`} help="video-consultations"
        actions={<>
          <StatusBadge status={c.status} />
          {active && (windowOpen
            ? <Button icon={<Video className="size-4" aria-hidden />} onClick={() => nav(`/app/consultations/${c.id}/room`)} data-testid="join-room">{t("consult.join")}</Button>
            : <Badge tone="neutral">{t("consult.windowClosed")}</Badge>)}
          {active && (isPatient || isPro) && <Button variant="secondary" onClick={() => act.mutate({ path: `/consultations/${c.id}/complete` })} data-testid="complete-consultation">{t("consult.complete")}</Button>}
          {active && isPatient && <Button variant="ghost" onClick={() => setResched(toLocalInput(new Date(c.scheduled_start)))}>{t("consult.reschedule")}</Button>}
          {active && isPatient && <Button variant="ghost" onClick={() => act.mutate({ path: `/consultations/${c.id}/cancel` })}>{t("consult.cancel")}</Button>}
        </>} />
      {act.error && <div className="mb-4"><ErrorState error={act.error} /></div>}
      {isPro && c.my_invite_status === "invited" && (
        <div className="mb-4 flex flex-wrap gap-2 items-center"><Notice>{t("status.invited")}</Notice>
          <Button size="sm" onClick={() => act.mutate({ path: `/consultations/${c.id}/respond`, body: { decision: "accept" } })}>{t("consult.accept")}</Button>
          <Button size="sm" variant="secondary" onClick={() => act.mutate({ path: `/consultations/${c.id}/respond`, body: { decision: "decline" } })}>{t("consult.decline")}</Button></div>
      )}
      {pendingAck.map((h) => (
        <div key={h.id} className="mb-4 flex items-center gap-2"><Notice>{t("pro.handoffs")}: {h.from.full_name}</Notice><Button size="sm" onClick={() => act.mutate({ path: `/handoffs/${h.id}/acknowledge` })}>{t("pro.acknowledge")}</Button></div>
      ))}
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <div className="xl:col-span-2 flex flex-col gap-6">
          <Card title={t("summary.title")} action={isPro && c.status === "completed" ? (
            <Button size="sm" onClick={() => setEditor({ base: current })} data-testid="write-summary">{current ? t("summary.newVersion") : t("summary.write")}</Button>) : undefined}>
            {summaries.isLoading && <Spinner />}
            {!summaries.data?.length && <EmptyState title={t("summary.none")} />}
            {current && <SummaryView s={current} c={c} isPro={isPro} isPatient={isPatient} />}
            {(summaries.data?.length ?? 0) > 1 && (
              <details className="mt-4 text-sm"><summary className="cursor-pointer text-muted">{t("docs.versions")}</summary>
                <ul className="mt-2 flex flex-col gap-1">{summaries.data!.map((s) => <li key={s.id} className="flex gap-2 items-center">{t("summary.version", { n: s.version })} <StatusBadge status={s.status} /> <span className="text-muted">{s.author.full_name} · {f.dateTime(s.created_at)}</span></li>)}</ul>
              </details>
            )}
          </Card>
          <Card title={t("consult.notes")}>
            <p className="text-xs text-muted mb-3">{t("consult.notesHint")}</p>
            <ul className="flex flex-col gap-3 mb-4">
              {c.notes?.map((n) => <li key={n.id} className="rounded-lg bg-surface-2 p-3 text-sm"><div className="text-xs text-muted mb-1">{n.author.full_name} · {f.dateTime(n.created_at)}</div><p className="whitespace-pre-wrap" dir="auto">{n.content}</p></li>)}
            </ul>
            {isPro && (
              <div className="flex flex-col gap-2">
                <Textarea aria-label={t("consult.addNote")} value={note} onChange={(e) => setNote(e.target.value)} dir="auto" data-testid="note-input" />
                <Button className="self-end" size="sm" disabled={note.trim().length < 2} onClick={() => act.mutate({ path: `/consultations/${c.id}/notes`, body: { content: note } })} data-testid="add-note">{t("consult.addNote")}</Button>
              </div>
            )}
          </Card>
        </div>
        <div className="flex flex-col gap-6">
          <Card title={t("consult.participants")}>
            <ul className="flex flex-col gap-3">
              {c.participants.map((p) => (
                <li key={p.user.id} className="text-sm">
                  <div className="flex items-center gap-2"><span className="font-medium flex-1">{p.user.full_name}</span><StatusBadge status={p.invite_status} /></div>
                  <div className="text-xs text-muted">{p.user.professional ? `${p.user.professional.specialty} · ${p.user.professional.organization?.name} · ` : `${tx("role", "patient")} · `}{p.user.country}</div>
                  <div className="text-xs text-muted">{t("consult.localTime", { name: p.user.full_name.split(" ")[0], time: f.dateTime(c.scheduled_start, p.user.timezone) })}</div>
                </li>
              ))}
            </ul>
          </Card>
          <Card title={t("consult.documents")} action={isPatient && c.documents.length > 0 && active ? <Button size="sm" variant="secondary" onClick={() => setShareOpen(true)} data-testid="share-participants">{t("consult.share")}</Button> : undefined}>
            {c.documents.length === 0 ? <p className="text-sm text-muted">{t("common.none")}</p> : (
              <ul className="flex flex-col gap-2">
                {c.documents.map((d) => (
                  <li key={d.id} className="flex items-center gap-2 text-sm">
                    {d.accessible ? <FileText className="size-4 text-brand" aria-hidden /> : <FileLock2 className="size-4 text-muted" aria-hidden />}
                    {d.accessible ? <Link className="flex-1 text-brand hover:underline" to={`/app/documents/${d.id}`}>{d.title}</Link> : <span className="flex-1 text-muted">{d.title}</span>}
                    {!isPatient && <Badge tone={d.accessible ? "ok" : "neutral"}>{d.accessible ? t("consult.accessible") : t("consult.notAccessible")}</Badge>}
                  </li>
                ))}
              </ul>
            )}
            {isPatient && <p className="mt-3 text-xs text-muted">{t("consult.agendaNote")}</p>}
          </Card>
          {c.purpose && <Card title={t("consult.purpose")}><p className="text-sm whitespace-pre-wrap" dir="auto">{c.purpose}</p></Card>}
          <Notice tone="neutral" icon={<Lock className="size-4 mt-0.5" aria-hidden />}>{t("consult.recordingOff")}</Notice>
        </div>
      </div>
      {editor && <SummaryEditor c={c} base={editor.base} onClose={() => setEditor(null)} />}
      <Dialog open={shareOpen} onClose={() => setShareOpen(false)} title={t("consult.shareTitle")}
        footer={<><Button variant="secondary" onClick={() => setShareOpen(false)}>{t("common.cancel")}</Button><Button loading={act.isPending} onClick={() => act.mutate({ path: `/consultations/${c.id}/share`, body: { document_ids: c.documents.map((d) => d.id), days: shareDays } })} data-testid="confirm-share-participants">{t("sharing.approve")}</Button></>}>
        <ul className="list-disc ps-5 text-sm mb-3">{c.documents.map((d) => <li key={d.id}>{d.title}</li>)}</ul>
        <p className="text-sm mb-3">{c.participants.filter((p) => p.meeting_role === "professional" && p.invite_status !== "declined").map((p) => p.user.full_name).join(", ")}</p>
        <Field label={`${t("sharing.duration")} (${t("common.days")})`}>{(fid) => <Input id={fid} type="number" min={1} max={90} value={shareDays} onChange={(e) => setShareDays(Number(e.target.value))} />}</Field>
      </Dialog>
      <Dialog open={resched !== null} onClose={() => setResched(null)} title={t("consult.reschedule")}
        footer={<><Button variant="secondary" onClick={() => setResched(null)}>{t("common.cancel")}</Button><Button onClick={() => act.mutate({ method: "patch", path: `/consultations/${c.id}`, body: { scheduled_start: new Date(resched!).toISOString() } })}>{t("common.save")}</Button></>}>
        <Field label={t("consult.when")}>{(fid) => <Input id={fid} type="datetime-local" value={resched ?? ""} onChange={(e) => setResched(e.target.value)} />}</Field>
      </Dialog>
      <div className="mt-6"><ButtonLink to="/app/consultations">{t("common.back")}</ButtonLink></div>
    </>
  );
}
