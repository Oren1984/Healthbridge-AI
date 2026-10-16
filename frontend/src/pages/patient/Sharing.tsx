import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Clock, FileText, Info, ShieldCheck, UserRound } from "lucide-react";
import { useState } from "react";
import { CATEGORIES } from "../../components/panels/DocumentsPanel";
import {
  Badge, Button, Card, Dialog, EmptyState, ErrorState, Field, Input, Notice, PageHeader, Select, Spinner, StatusBadge,
} from "../../components/ui";
import { api } from "../../lib/api";
import { useMe } from "../../lib/auth";
import { useFormat } from "../../lib/format";
import { useI18n } from "../../lib/i18n";
import type { Doc, Grant, Handoff, UserBrief } from "../../lib/types";

interface Preview { grantee: UserBrief; documents: Doc[]; categories: string[]; categories_note: string; sections: Record<string, boolean>; expires_at: string; revocation_notice: string }

function NewGrant({ onClose }: { onClose: () => void }) {
  const me = useMe();
  const { t, tx } = useI18n();
  const f = useFormat();
  const qc = useQueryClient();
  const pros = useQuery({ queryKey: ["professionals"], queryFn: () => api.get<UserBrief[]>("/professionals") });
  const docs = useQuery({ queryKey: ["docs", me.id, "", ""], queryFn: () => api.get<Doc[]>(`/patients/${me.id}/documents`) });
  const [grantee, setGrantee] = useState("");
  const [docIds, setDocIds] = useState<string[]>([]);
  const [cats, setCats] = useState<string[]>([]);
  const [journey, setJourney] = useState(false);
  const [gaps, setGaps] = useState(false);
  const [days, setDays] = useState(me.patient?.default_share_days ?? 14);
  const [purpose, setPurpose] = useState("");
  const body = { grantee_id: grantee, document_ids: docIds, categories: cats, include_journey: journey, include_care_gaps: gaps, days, purpose: purpose || null };
  const preview = useMutation({ mutationFn: () => api.post<Preview>(`/patients/${me.id}/grants/preview`, body) });
  const create = useMutation({ mutationFn: () => api.post(`/patients/${me.id}/grants`, body), onSuccess: () => { qc.invalidateQueries(); onClose(); } });
  const toggle = (arr: string[], v: string, set: (x: string[]) => void) => set(arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v]);
  const nothing = !docIds.length && !cats.length && !journey && !gaps;

  return (
    <Dialog open onClose={onClose} title={preview.data ? t("sharing.reviewTitle") : t("sharing.new")} wide
      footer={preview.data ? (
        <><Button variant="secondary" onClick={() => preview.reset()}>{t("common.back")}</Button>
          <Button onClick={() => create.mutate()} loading={create.isPending} data-testid="approve-sharing" icon={<ShieldCheck className="size-4" aria-hidden />}>{t("sharing.approve")}</Button></>
      ) : (
        <><Button variant="secondary" onClick={onClose}>{t("common.cancel")}</Button>
          <Button onClick={() => preview.mutate()} disabled={!grantee || nothing} loading={preview.isPending} data-testid="review-sharing">{t("sharing.review")}</Button></>
      )}>
      {preview.data ? (
        <div className="flex flex-col gap-4" data-testid="sharing-preview">
          <p className="font-medium">{t("sharing.willSee", { name: preview.data.grantee.full_name })}</p>
          <ul className="flex flex-col gap-1.5">
            {preview.data.documents.map((d) => <li key={d.id} className="flex items-center gap-2 text-sm"><FileText className="size-4 text-muted" aria-hidden /><span dir="auto">{d.title}</span><Badge>{tx("cat", d.category)}</Badge></li>)}
            {preview.data.sections.journey && <li className="text-sm">• {t("sharing.journey")}</li>}
            {preview.data.sections.care_gaps && <li className="text-sm">• {t("sharing.gaps")}</li>}
          </ul>
          {preview.data.categories.length > 0 && <Notice tone="warn">{preview.data.categories_note}</Notice>}
          <p className="text-sm inline-flex items-center gap-1.5"><Clock className="size-4" aria-hidden />{t("sharing.until", { date: f.dateTime(preview.data.expires_at) })}</p>
          <Notice tone="neutral">{preview.data.revocation_notice}</Notice>
          {create.error && <ErrorState error={create.error} />}
        </div>
      ) : (
        <div className="flex flex-col gap-5">
          <Field label={t("sharing.recipient")} required>{(id) => (
            <Select id={id} value={grantee} onChange={(e) => setGrantee(e.target.value)} data-testid="grantee-select">
              <option value="">{t("sharing.selectRecipient")}</option>
              {pros.data?.map((p) => <option key={p.id} value={p.id}>{p.full_name} — {p.professional?.specialty}, {p.professional?.organization?.name} ({p.country})</option>)}
            </Select>)}</Field>
          <fieldset>
            <legend className="text-sm font-medium mb-2">{t("sharing.documents")}</legend>
            <div className="max-h-56 overflow-y-auto rounded-lg border border-line divide-y divide-line">
              {docs.data?.map((d) => (
                <label key={d.id} className="flex items-center gap-3 px-3 py-2 text-sm cursor-pointer hover:bg-surface-2">
                  <input type="checkbox" checked={docIds.includes(d.id)} onChange={() => toggle(docIds, d.id, setDocIds)} className="size-4 accent-[var(--primary)]" />
                  <span className="flex-1" dir="auto">{d.title}</span><Badge>{tx("cat", d.category)}</Badge>
                </label>
              ))}
            </div>
          </fieldset>
          <fieldset>
            <legend className="text-sm font-medium mb-2">{t("sharing.categories")}</legend>
            <div className="flex flex-wrap gap-2">
              {CATEGORIES.map((c) => (
                <label key={c} className="inline-flex items-center gap-2 rounded-lg border border-line px-2.5 py-1.5 text-sm cursor-pointer">
                  <input type="checkbox" checked={cats.includes(c)} onChange={() => toggle(cats, c, setCats)} className="size-4 accent-[var(--primary)]" />{tx("cat", c)}
                </label>
              ))}
            </div>
          </fieldset>
          <fieldset className="flex flex-col gap-2">
            <legend className="text-sm font-medium mb-1">{t("sharing.sections")}</legend>
            <label className="inline-flex items-center gap-2 text-sm"><input type="checkbox" checked={journey} onChange={(e) => setJourney(e.target.checked)} className="size-4 accent-[var(--primary)]" />{t("sharing.journey")}</label>
            <label className="inline-flex items-center gap-2 text-sm"><input type="checkbox" checked={gaps} onChange={(e) => setGaps(e.target.checked)} className="size-4 accent-[var(--primary)]" />{t("sharing.gaps")}</label>
          </fieldset>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={`${t("sharing.duration")} (${t("common.days")})`}>{(id) => <Input id={id} type="number" min={1} max={365} value={days} onChange={(e) => setDays(Number(e.target.value))} />}</Field>
            <Field label={t("sharing.purpose")}>{(id) => <Input id={id} value={purpose} maxLength={300} onChange={(e) => setPurpose(e.target.value)} />}</Field>
          </div>
          {nothing && grantee && <p className="text-sm text-muted">{t("sharing.nothingSelected")}</p>}
          {preview.error && <ErrorState error={preview.error} />}
        </div>
      )}
    </Dialog>
  );
}

function GrantRow({ g, onRevoke }: { g: Grant; onRevoke?: () => void }) {
  const { t, tx } = useI18n();
  const f = useFormat();
  return (
    <li className="py-3 flex flex-wrap items-start gap-3" data-testid="grant-row">
      <UserRound className="size-5 mt-0.5 text-muted" aria-hidden />
      <div className="flex-1 min-w-0">
        <p className="font-medium">{g.grantee.full_name} <span className="text-sm text-muted">· {g.grantee.professional?.specialty} · {g.grantee.country}</span></p>
        <p className="text-sm text-muted">
          {[...g.documents.map((d) => d.title), ...g.categories.map((c) => `${tx("cat", c)} (*)`),
            ...(g.include_journey ? [t("sharing.journey")] : []), ...(g.include_care_gaps ? [t("sharing.gaps")] : [])].join(" · ")}
        </p>
        <p className="text-xs text-muted mt-0.5">{g.purpose ? `${g.purpose} · ` : ""}{f.date(g.starts_at)} → {f.date(g.revoked_at ?? g.expires_at)}</p>
      </div>
      <StatusBadge status={g.state} />
      {onRevoke && <Button size="sm" variant="danger" onClick={onRevoke} data-testid="revoke-grant">{t("sharing.revoke")}</Button>}
    </li>
  );
}

export default function Sharing() {
  const me = useMe();
  const { t } = useI18n();
  const qc = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [revoking, setRevoking] = useState<Grant | null>(null);
  const q = useQuery({ queryKey: ["grants", me.id], queryFn: () => api.get<{ grants: Grant[]; revocation_notice: string }>(`/patients/${me.id}/grants`) });
  const handoffs = useQuery({ queryKey: ["handoffs"], queryFn: () => api.get<Handoff[]>("/handoffs") });
  const revoke = useMutation({ mutationFn: (id: string) => api.post(`/grants/${id}/revoke`), onSuccess: () => { qc.invalidateQueries(); setRevoking(null); } });
  const decide = useMutation({ mutationFn: ({ id, decision }: { id: string; decision: string }) => api.post(`/handoffs/${id}/decide`, { decision }), onSuccess: () => qc.invalidateQueries() });
  const active = (q.data?.grants ?? []).filter((g) => g.state === "active" || g.state === "scheduled");
  const ended = (q.data?.grants ?? []).filter((g) => g.state === "expired" || g.state === "revoked");
  const pendingHandoffs = (handoffs.data ?? []).filter((h) => h.status === "pending_patient_approval");

  return (
    <>
      <PageHeader title={t("sharing.title")} subtitle={t("sharing.subtitle")} help="sharing-and-revocation"
        actions={<Button onClick={() => setCreating(true)} data-testid="new-sharing">{t("sharing.new")}</Button>} />
      {q.isLoading && <Spinner />}
      {q.error && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <div className="xl:col-span-2 flex flex-col gap-6">
          {pendingHandoffs.length > 0 && (
            <Card title={t("sharing.handoffs")}>
              <ul className="divide-y divide-line">
                {pendingHandoffs.map((h) => (
                  <li key={h.id} className="py-3 flex flex-wrap items-center gap-3">
                    <div className="flex-1 text-sm"><span className="font-medium">{h.from.full_name}</span> → <span className="font-medium">{h.to.full_name}</span>: {h.consultation?.title}{h.note && <p className="text-muted" dir="auto">“{h.note}”</p>}</div>
                    <Button size="sm" onClick={() => decide.mutate({ id: h.id, decision: "approve" })}>{t("sharing.approveHandoff")}</Button>
                    <Button size="sm" variant="secondary" onClick={() => decide.mutate({ id: h.id, decision: "decline" })}>{t("sharing.declineHandoff")}</Button>
                  </li>
                ))}
              </ul>
            </Card>
          )}
          <Card title={t("sharing.active")}>
            {active.length === 0 ? <EmptyState title={t("sharing.noActive")} /> : (
              <ul className="divide-y divide-line">{active.map((g) => <GrantRow key={g.id} g={g} onRevoke={() => setRevoking(g)} />)}</ul>
            )}
          </Card>
          <Card title={t("sharing.history")}>
            <ul className="divide-y divide-line">{ended.map((g) => <GrantRow key={g.id} g={g} />)}</ul>
          </Card>
        </div>
        <Card title={t("sharing.legal")}>
          <div className="flex gap-2 text-sm text-muted"><Info className="size-4 mt-0.5 shrink-0" aria-hidden /><p>{q.data?.revocation_notice}</p></div>
        </Card>
      </div>
      {creating && <NewGrant onClose={() => setCreating(false)} />}
      <Dialog open={!!revoking} onClose={() => setRevoking(null)} title={t("sharing.revoke")}
        footer={<><Button variant="secondary" onClick={() => setRevoking(null)}>{t("common.cancel")}</Button>
          <Button variant="danger" loading={revoke.isPending} onClick={() => revoking && revoke.mutate(revoking.id)} data-testid="confirm-revoke">{t("sharing.revoke")}</Button></>}>
        <p>{revoking && t("sharing.revokeConfirm", { name: revoking.grantee.full_name })}</p>
        <p className="mt-3 text-sm text-muted">{q.data?.revocation_notice}</p>
      </Dialog>
    </>
  );
}
