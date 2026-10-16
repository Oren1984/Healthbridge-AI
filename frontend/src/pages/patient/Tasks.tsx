import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, ClipboardCheck, History, Link2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link } from "react-router";
import {
  Badge, Button, Dialog, EmptyState, ErrorState, Field, Input, Notice, PageHeader, Select, Spinner, StatusBadge, Tabs, Textarea,
} from "../../components/ui";
import { api } from "../../lib/api";
import { useMe } from "../../lib/auth";
import { useFormat } from "../../lib/format";
import { useI18n } from "../../lib/i18n";
import type { Doc, Task } from "../../lib/types";

function CompleteDialog({ task, mode, onClose }: { task: Task; mode: "complete" | "verify" | "dismiss"; onClose: () => void }) {
  const { t } = useI18n();
  const qc = useQueryClient();
  const docs = useQuery({ queryKey: ["docs", task.patient_id, "", ""], queryFn: () => api.get<Doc[]>(`/patients/${task.patient_id}/documents`) });
  const [evidence, setEvidence] = useState("");
  const [note, setNote] = useState("");
  const m = useMutation({
    mutationFn: () => api.post(`/tasks/${task.id}/${mode}`, { note: note || null, evidence_document_id: evidence || null }),
    onSuccess: () => { qc.invalidateQueries(); onClose(); },
  });
  const submit = (e: FormEvent) => { e.preventDefault(); m.mutate(); };
  const title = mode === "dismiss" ? t("tasks.dismiss") : mode === "verify" ? t("tasks.verify") : t("tasks.completeTitle");
  return (
    <Dialog open onClose={onClose} title={title}
      footer={<><Button variant="secondary" onClick={onClose}>{t("common.cancel")}</Button>
        <Button type="submit" form="complete-task" loading={m.isPending} disabled={(mode === "verify" && !evidence) || (mode === "dismiss" && note.trim().length < 5)}>{t("common.confirm")}</Button></>}>
      <form id="complete-task" onSubmit={submit} className="flex flex-col gap-4">
        <p className="font-medium" dir="auto">{task.title}</p>
        {mode !== "dismiss" && (
          <>
            <Notice>{t("tasks.evidenceHint")}</Notice>
            <Field label={t("tasks.evidence")}>{(id) => (
              <Select id={id} value={evidence} onChange={(e) => setEvidence(e.target.value)} data-testid="evidence-select">
                {mode === "complete" && <option value="">{t("tasks.noEvidence")}</option>}
                {mode === "verify" && <option value="">—</option>}
                {docs.data?.map((d) => <option key={d.id} value={d.id}>{d.title}</option>)}
              </Select>)}</Field>
          </>
        )}
        <Field label={mode === "dismiss" ? t("common.reason") : t("common.notes")} required={mode === "dismiss"}>
          {(id) => <Textarea id={id} value={note} onChange={(e) => setNote(e.target.value)} />}
        </Field>
        {m.error && <ErrorState error={m.error} />}
      </form>
    </Dialog>
  );
}

function HistoryDialog({ task, onClose }: { task: Task; onClose: () => void }) {
  const { t } = useI18n();
  const f = useFormat();
  const q = useQuery({ queryKey: ["task-history", task.id], queryFn: () => api.get<{ ts: string; action: string; actor: string | null; detail: Record<string, unknown> }[]>(`/tasks/${task.id}/history`) });
  return (
    <Dialog open onClose={onClose} title={t("tasks.history")}>
      {q.isLoading && <Spinner />}
      <ol className="flex flex-col gap-2">
        {q.data?.map((h, i) => (
          <li key={i} className="text-sm"><span className="text-muted">{f.dateTime(h.ts)}</span> · {h.action} · {h.actor} {h.detail?.status ? <StatusBadge status={String(h.detail.status)} /> : null}</li>
        ))}
      </ol>
    </Dialog>
  );
}

function NewTask({ patientId, onClose }: { patientId: string; onClose: () => void }) {
  const { t } = useI18n();
  const qc = useQueryClient();
  const [form, setForm] = useState({ title: "", description: "", due_date: "", reminder_days_before: "" });
  const m = useMutation({
    mutationFn: () => api.post(`/patients/${patientId}/tasks`, {
      title: form.title, description: form.description || null, due_date: form.due_date || null,
      reminder_days_before: form.reminder_days_before ? Number(form.reminder_days_before) : null,
    }),
    onSuccess: () => { qc.invalidateQueries(); onClose(); },
  });
  return (
    <Dialog open onClose={onClose} title={t("tasks.new")}
      footer={<><Button variant="secondary" onClick={onClose}>{t("common.cancel")}</Button><Button type="submit" form="new-task" loading={m.isPending}>{t("common.save")}</Button></>}>
      <form id="new-task" onSubmit={(e) => { e.preventDefault(); m.mutate(); }} className="flex flex-col gap-4">
        <Field label={t("journey.newTitle")} required>{(id) => <Input id={id} required minLength={3} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />}</Field>
        <Field label={t("journey.newDesc")}>{(id) => <Textarea id={id} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />}</Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={t("tasks.dueDate")} hint={t("common.optional")}>{(id, d) => <Input id={id} aria-describedby={d} type="date" value={form.due_date} onChange={(e) => setForm({ ...form, due_date: e.target.value })} />}</Field>
          <Field label={t("tasks.reminder")}>{(id) => <Input id={id} type="number" min={0} max={60} value={form.reminder_days_before} onChange={(e) => setForm({ ...form, reminder_days_before: e.target.value })} />}</Field>
        </div>
        {m.error && <ErrorState error={m.error} />}
      </form>
    </Dialog>
  );
}

export default function Tasks() {
  const me = useMe();
  const { t, tx } = useI18n();
  const f = useFormat();
  const qc = useQueryClient();
  const [tab, setTab] = useState("open");
  const [dialog, setDialog] = useState<{ task: Task; mode: "complete" | "verify" | "dismiss" | "history" } | null>(null);
  const [creating, setCreating] = useState(false);
  const q = useQuery({ queryKey: ["tasks", me.id], queryFn: () => api.get<Task[]>(`/patients/${me.id}/tasks`) });
  const reopen = useMutation({ mutationFn: (id: string) => api.post(`/tasks/${id}/reopen`), onSuccess: () => qc.invalidateQueries() });
  const all = q.data ?? [];
  const shown = tab === "open" ? all.filter((x) => x.status === "open") : tab === "done" ? all.filter((x) => x.status !== "open") : all;

  return (
    <>
      <PageHeader title={t("tasks.title")} subtitle={t("tasks.subtitle")} help="follow-ups"
        actions={<Button onClick={() => setCreating(true)}>{t("tasks.new")}</Button>} />
      <Tabs label={t("tasks.title")} value={tab} onChange={setTab} tabs={[
        { id: "open", label: t("tasks.filter.open"), count: all.filter((x) => x.status === "open").length },
        { id: "done", label: t("tasks.filter.done"), count: all.filter((x) => x.status !== "open").length },
        { id: "all", label: t("common.all"), count: all.length },
      ]} />
      {q.isLoading && <Spinner />}
      {q.error && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      {q.data && shown.length === 0 && <EmptyState icon={<ClipboardCheck className="size-8" aria-hidden />} title={t("tasks.empty")} />}
      <ul className="flex flex-col gap-3" data-testid="task-list">
        {shown.map((task) => (
          <li key={task.id} className="card p-4 flex flex-col gap-3" data-testid="task-item">
            <div className="flex flex-wrap items-start gap-2">
              <div className="flex-1 min-w-0">
                <p className="font-medium" dir="auto">{task.title}</p>
                {task.description && <p className="text-sm text-muted mt-0.5" dir="auto">{task.description}</p>}
              </div>
              <Badge tone={task.kind === "clarification" ? "violet" : "brand"}>{t(`tasks.kind.${task.kind}` as never)}</Badge>
              <StatusBadge status={task.status} />
            </div>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted">
              <span className="inline-flex items-center gap-1"><CalendarClock className="size-3.5" aria-hidden />
                {task.due_date ? `${t("tasks.due", { date: f.date(task.due_date) })} (${tx("tasks.dueSource", task.due_date_source)})` : t("tasks.noDue")}</span>
              {task.recommendation_id && <span className="inline-flex items-center gap-1"><Link2 className="size-3.5" aria-hidden />{t("tasks.fromRec")}</span>}
              {task.care_gap_id && <Link className="inline-flex items-center gap-1 text-brand hover:underline" to={`/app/care-gaps?gap=${task.care_gap_id}`}><Link2 className="size-3.5" aria-hidden />{t("nav.careGaps")}</Link>}
              {task.evidence_document_id && <Link className="text-brand hover:underline" to={`/app/documents/${task.evidence_document_id}`}>{t("tasks.evidence")}</Link>}
              {task.completion_note && <span dir="auto">“{task.completion_note}”</span>}
            </div>
            <div className="flex flex-wrap gap-2">
              {task.status === "open" && (
                <>
                  <Button size="sm" onClick={() => setDialog({ task, mode: "complete" })} data-testid="task-complete">{t("tasks.complete")}</Button>
                  <Button size="sm" variant="ghost" onClick={() => setDialog({ task, mode: "dismiss" })}>{t("tasks.dismiss")}</Button>
                </>
              )}
              {task.status === "completed_reported" && <Button size="sm" onClick={() => setDialog({ task, mode: "verify" })}>{t("tasks.verify")}</Button>}
              {task.status !== "open" && <Button size="sm" variant="secondary" onClick={() => reopen.mutate(task.id)}>{t("tasks.reopen")}</Button>}
              <Button size="sm" variant="ghost" icon={<History className="size-4" aria-hidden />} onClick={() => setDialog({ task, mode: "history" })}>{t("tasks.history")}</Button>
            </div>
          </li>
        ))}
      </ul>
      {dialog && dialog.mode === "history" && <HistoryDialog task={dialog.task} onClose={() => setDialog(null)} />}
      {dialog && dialog.mode !== "history" && <CompleteDialog task={dialog.task} mode={dialog.mode} onClose={() => setDialog(null)} />}
      {creating && <NewTask patientId={me.id} onClose={() => setCreating(false)} />}
    </>
  );
}
