import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { CalendarClock, CheckCircle2, FileText, History, Lightbulb, MinusCircle, RefreshCw, Scale } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { api } from "../../lib/api";
import { useFormat } from "../../lib/format";
import { gapDescription, gapRule, gapSuggestion, gapTitle, missingText } from "../../lib/gapText";
import { useI18n } from "../../lib/i18n";
import type { Evidence, Gap } from "../../lib/types";
import { Badge, Button, Dialog, EmptyState, ErrorState, Field, Input, Notice, Spinner, StatusBadge, Tabs, Textarea } from "../ui";

function EvidenceLink({ e, isPatient }: { e: Evidence; isPatient: boolean }) {
  const label = <span dir="auto">{e.label}</span>;
  const inner = e.type === "document"
    ? <Link className="text-brand hover:underline" to={`/app/documents/${e.id}`}>{label}</Link>
    : e.type === "event" && isPatient ? <Link className="text-brand hover:underline" to={`/app/journey?event=${e.id}`}>{label}</Link>
    : e.type === "consultation" ? <Link className="text-brand hover:underline" to={`/app/consultations/${e.id}`}>{label}</Link>
    : label;
  return (
    <li className="flex items-start gap-2 text-sm">
      <FileText className="size-4 mt-0.5 text-muted shrink-0" aria-hidden />
      <span>{inner}{e.detail && <span className="text-muted"> — {e.detail}</span>}</span>
    </li>
  );
}

function GapCard({ g, canReview, canCreate, highlight }: { g: Gap; canReview: boolean; canCreate: boolean; highlight: boolean }) {
  // canCreate is true only for the patient
  const { t, tx, lang } = useI18n();
  const f = useFormat();
  const qc = useQueryClient();
  const [dismiss, setDismiss] = useState(false);
  const [note, setNote] = useState("");
  const [created, setCreated] = useState(false);
  const review = useMutation({
    mutationFn: (body: { action: string; note?: string }) => api.post<Gap & { created_task?: unknown }>(`/care-gaps/${g.id}/review`, body),
    onSuccess: (r) => { if (r.created_task) setCreated(true); setDismiss(false); qc.invalidateQueries(); },
  });
  const suggestion = gapSuggestion(g, lang);
  const dates = Object.entries(g.relevant_dates).filter(([k, v]) => v && k !== "evaluated");
  return (
    <article id={`gap-${g.id}`} className={clsx("card p-5 flex flex-col gap-4", highlight && "ring-2 ring-brand")} data-testid="gap-card" data-status={g.status}>
      <header className="flex flex-wrap items-start gap-3">
        <div className="flex-1 min-w-0">
          <h3 className="font-semibold leading-snug" dir="auto">{gapTitle(g, lang, tx)}</h3>
          <p className="mt-1 text-sm text-muted">{gapDescription(g, lang)}</p>
          {g.params?.pending_review && <p className="mt-1 text-xs text-warn">{t("careGaps.pendingReview")}</p>}
        </div>
        <StatusBadge status={g.status} />
      </header>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <section>
          <h4 className="text-xs font-semibold uppercase tracking-wide text-muted mb-1.5">{t("careGaps.supporting")}</h4>
          {g.supporting_evidence.length === 0 ? <p className="text-sm text-muted">{t("common.none")}</p> : (
            <ul className="flex flex-col gap-1.5">{g.supporting_evidence.map((e, i) => <EvidenceLink key={i} e={e} isPatient={canCreate} />)}</ul>
          )}
        </section>
        <section>
          <h4 className="text-xs font-semibold uppercase tracking-wide text-muted mb-1.5">{t("careGaps.missing")}</h4>
          {g.missing_evidence.length === 0 ? <p className="text-sm text-muted">{t("common.none")}</p> : (
            <ul className="flex flex-col gap-1.5">
              {g.missing_evidence.map((m) => <li key={m} className="flex items-start gap-2 text-sm"><MinusCircle className="size-4 mt-0.5 text-warn shrink-0" aria-hidden />{missingText(m, lang, tx)}</li>)}
            </ul>
          )}
        </section>
      </div>
      <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted">
        <span className="inline-flex items-center gap-1"><Scale className="size-3.5" aria-hidden />{t("careGaps.rule")} {g.rule_id}: {gapRule(g, lang)}</span>
        {dates.map(([k, v]) => <span key={k} className="inline-flex items-center gap-1"><CalendarClock className="size-3.5" aria-hidden />{k.replace(/_/g, " ")}: {k === "documented_timeframe" ? v : f.date(v)}</span>)}
      </div>
      {suggestion && g.status !== "completed_verified" && g.status !== "not_applicable" && (
        <div className="rounded-lg bg-info-soft p-3 text-sm text-info flex gap-2">
          <Lightbulb className="size-4 mt-0.5 shrink-0" aria-hidden />
          <div><span className="font-medium">{t("careGaps.suggestion")}: </span><span dir="auto">{suggestion}</span></div>
        </div>
      )}
      {g.review_status && (
        <p className="text-xs text-muted inline-flex items-center gap-1"><History className="size-3.5" aria-hidden />
          {t("careGaps.reviewed", { date: f.date(g.reviewed_at), note: g.review_note ?? "" })} · {t("careGaps.computed", { status: tx("status", g.computed_status) })}</p>
      )}
      {created && <Notice tone="ok">{t("careGaps.itemCreated")} <Link className="underline" to="/app/tasks">{t("nav.tasks")}</Link></Notice>}
      {review.error && <ErrorState error={review.error} />}
      {canReview && g.status !== "completed_verified" && (
        <div className="flex flex-wrap gap-2">
          {canCreate && g.status !== "not_applicable" && (
            <Button size="sm" onClick={() => review.mutate({ action: "create_clarification" })} loading={review.isPending} data-testid="create-clarification">{t("careGaps.createItem")}</Button>
          )}
          {g.review_status ? (
            <Button size="sm" variant="secondary" onClick={() => review.mutate({ action: "reopen" })}>{t("careGaps.reopen")}</Button>
          ) : (
            <>
              {g.status !== "requires_clarification" && <Button size="sm" variant="secondary" onClick={() => review.mutate({ action: "clarify" })}>{t("careGaps.clarify")}</Button>}
              <Button size="sm" variant="ghost" onClick={() => setDismiss(true)}>{t("careGaps.dismiss")}</Button>
            </>
          )}
        </div>
      )}
      <Dialog open={dismiss} onClose={() => setDismiss(false)} title={t("careGaps.dismiss")}
        footer={<><Button variant="secondary" onClick={() => setDismiss(false)}>{t("common.cancel")}</Button>
          <Button disabled={note.trim().length < 5} loading={review.isPending} onClick={() => review.mutate({ action: "dismiss", note })}>{t("common.confirm")}</Button></>}>
        <Field label={t("careGaps.dismissReason")} required>{(id) => <Textarea id={id} value={note} onChange={(e) => setNote(e.target.value)} />}</Field>
      </Dialog>
    </article>
  );
}

const ATTENTION = ["requires_clarification", "unknown", "open"];

export function CareGapsPanel({ patientId, isPatient }: { patientId: string; isPatient: boolean }) {
  const { t, tx, lang } = useI18n();
  const qc = useQueryClient();
  const [params] = useSearchParams();
  const focus = params.get("gap");
  const [tab, setTab] = useState("attention");
  const [replayOpen, setReplayOpen] = useState(false);
  const [asOf, setAsOf] = useState(new Date().toISOString().slice(0, 10));
  const gaps = useQuery({ queryKey: ["gaps", patientId], queryFn: () => api.get<Gap[]>(`/patients/${patientId}/care-gaps`) });
  const evaluate = useMutation({ mutationFn: () => api.post(`/patients/${patientId}/care-gaps/evaluate`), onSuccess: () => qc.invalidateQueries() });
  const replay = useMutation({ mutationFn: () => api.get<{ findings: (Omit<Gap, "id">)[] }>(`/patients/${patientId}/care-gaps/replay?as_of=${asOf}`) });

  useEffect(() => {
    if (focus && gaps.data) {
      const g = gaps.data.find((x) => x.id === focus);
      if (g && !ATTENTION.includes(g.status)) setTab("all");
      setTimeout(() => document.getElementById(`gap-${focus}`)?.scrollIntoView({ block: "center" }), 50);
    }
  }, [focus, gaps.data]);

  const all = gaps.data ?? [];
  const groups: Record<string, Gap[]> = {
    attention: all.filter((g) => ATTENTION.includes(g.status)),
    verified: all.filter((g) => g.status === "completed_verified"),
    dismissed: all.filter((g) => g.status === "not_applicable"),
    all,
  };
  const counts = (s: string) => all.filter((g) => g.status === s).length;

  return (
    <div className="flex flex-col gap-4">
      <Notice tone="neutral">{t("careGaps.disclaimer")}</Notice>
      <div className="grid gap-3 grid-cols-2 lg:grid-cols-5">
        {["requires_clarification", "unknown", "open", "completed_verified", "not_applicable"].map((s) => (
          <div key={s} className="card p-3">
            <div className="text-2xl font-semibold">{counts(s)}</div>
            <StatusBadge status={s} />
          </div>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex-1 min-w-0">
          <Tabs label={t("careGaps.title")} value={tab} onChange={setTab} tabs={[
            { id: "attention", label: `${tx("status", "unknown")} / ${tx("status", "requires_clarification")} / ${tx("status", "open")}`, count: groups.attention.length },
            { id: "verified", label: tx("status", "completed_verified"), count: groups.verified.length },
            { id: "dismissed", label: tx("status", "not_applicable"), count: groups.dismissed.length },
            { id: "all", label: t("common.all"), count: all.length },
          ]} />
        </div>
        {isPatient && (
          <>
            <Button size="sm" variant="secondary" icon={<RefreshCw className="size-4" aria-hidden />} onClick={() => evaluate.mutate()} loading={evaluate.isPending}>{t("careGaps.evaluate")}</Button>
            <Button size="sm" variant="secondary" icon={<History className="size-4" aria-hidden />} onClick={() => setReplayOpen(true)}>{t("careGaps.replay")}</Button>
          </>
        )}
      </div>
      {gaps.isLoading && <Spinner />}
      {gaps.error && <ErrorState error={gaps.error} onRetry={() => gaps.refetch()} />}
      {gaps.data && groups[tab].length === 0 && <EmptyState icon={<CheckCircle2 className="size-8" aria-hidden />} title={t("careGaps.empty")} />}
      <div className="flex flex-col gap-4">
        {groups[tab].map((g) => <GapCard key={g.id} g={g} canReview canCreate={isPatient} highlight={g.id === focus} />)}
      </div>
      <Dialog open={replayOpen} onClose={() => setReplayOpen(false)} title={t("careGaps.replay")} wide>
        <p className="text-sm text-muted mb-3">{t("careGaps.replayHint")}</p>
        <div className="flex gap-2 items-end mb-4">
          <Field label={t("common.date")}>{(id) => <Input id={id} type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} />}</Field>
          <Button onClick={() => replay.mutate()} loading={replay.isPending}>{t("careGaps.replay")}</Button>
        </div>
        {replay.error && <ErrorState error={replay.error} />}
        {replay.data && (
          <ul className="divide-y divide-line" data-testid="replay-results">
            {replay.data.findings.map((g, i) => (
              <li key={i} className="py-2 flex items-start gap-2 text-sm">
                <Badge>{g.rule_id}</Badge><span className="flex-1" dir="auto">{gapTitle(g as Gap, lang, tx)}</span><StatusBadge status={g.status} />
              </li>
            ))}
          </ul>
        )}
      </Dialog>
    </div>
  );
}
