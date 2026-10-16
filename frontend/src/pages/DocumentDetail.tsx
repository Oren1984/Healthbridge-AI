import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Download, Pencil, RefreshCw, Trash2, Upload, X } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { CATEGORIES, useOrgs } from "../components/panels/DocumentsPanel";
import {
  Badge, Button, Card, Dialog, EmptyState, ErrorState, Field, Input, KeyVal, Notice, PageHeader, Select, Spinner, StatusBadge,
  TermChips, Textarea,
} from "../components/ui";
import { api } from "../lib/api";
import { useFormat } from "../lib/format";
import { useI18n } from "../lib/i18n";
import type { DocDetail, Rec } from "../lib/types";

const KINDS = ["follow_up_visit", "lab_test", "imaging", "referral", "other"];

function Highlighted({ text, recs }: { text: string; recs: Rec[] }) {
  const parts = useMemo(() => {
    const ranges = recs.filter((r) => r.char_start !== null && r.char_end !== null && r.review_status !== "rejected")
      .sort((a, b) => a.char_start! - b.char_start!);
    const out: ReactNode[] = [];
    let pos = 0;
    for (const r of ranges) {
      if (r.char_start! < pos) continue;
      out.push(text.slice(pos, r.char_start!));
      out.push(<mark key={r.id} id={`passage-${r.id}`} className="passage">{text.slice(r.char_start!, r.char_end!)}</mark>);
      pos = r.char_end!;
    }
    out.push(text.slice(pos));
    return out;
  }, [text, recs]);
  return <div className="doc-text text-sm leading-relaxed" dir="auto" data-testid="doc-text">{parts}</div>;
}

function RecRow({ r, canEdit }: { r: Rec; canEdit: boolean }) {
  const { t, tx } = useI18n();
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(r.text);
  const [kind, setKind] = useState(r.kind);
  const [timeframe, setTimeframe] = useState(r.timeframe_text ?? "");
  const review = useMutation({ mutationFn: (body: object) => api.patch(`/recommendations/${r.id}`, body), onSuccess: () => { setEditing(false); qc.invalidateQueries(); } });
  const track = useMutation({ mutationFn: () => api.post(`/recommendations/${r.id}/track`), onSuccess: () => qc.invalidateQueries() });
  return (
    <li className="py-3 flex flex-col gap-2" data-testid="rec-row">
      <div className="flex flex-wrap items-start gap-2">
        <Badge tone="brand">{tx("kind", r.kind)}</Badge>
        <button className="flex-1 text-start text-sm font-medium hover:text-brand" dir="auto"
          onClick={() => document.getElementById(`passage-${r.id}`)?.scrollIntoView({ behavior: "smooth", block: "center" })}>{r.text}</button>
        <StatusBadge status={r.review_status} />
      </div>
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
        <span>{r.timeframe_text ? `${t("rec.timeframe")}: ${r.timeframe_text}` : t("rec.noDue")}</span>
        <TermChips terms={r.targets} />
        {r.original_text && <span dir="auto">{t("rec.originalText")}: “{r.original_text}”</span>}
        <Badge>{r.source}</Badge>
      </div>
      {canEdit && !editing && (
        <div className="flex flex-wrap gap-2">
          {r.review_status === "pending_review" && <Button size="sm" variant="secondary" icon={<Check className="size-4" aria-hidden />} onClick={() => review.mutate({ action: "confirm" })}>{t("rec.confirm")}</Button>}
          <Button size="sm" variant="ghost" icon={<Pencil className="size-4" aria-hidden />} onClick={() => setEditing(true)}>{t("rec.correct")}</Button>
          {r.review_status !== "rejected" && <Button size="sm" variant="ghost" icon={<X className="size-4" aria-hidden />} onClick={() => review.mutate({ action: "reject" })}>{t("rec.reject")}</Button>}
          {r.review_status !== "rejected" && <Button size="sm" onClick={() => track.mutate()} loading={track.isPending} disabled={track.isSuccess} data-testid="track-rec">{track.isSuccess ? t("rec.tracked") : t("rec.track")}</Button>}
        </div>
      )}
      {editing && (
        <div className="flex flex-col gap-3 rounded-lg border border-line p-3">
          <Field label={t("rec.text")}>{(id) => <Textarea id={id} value={text} onChange={(e) => setText(e.target.value)} dir="auto" />}</Field>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label={t("rec.kind")}>{(id) => <Select id={id} value={kind} onChange={(e) => setKind(e.target.value)}>{KINDS.map((k) => <option key={k} value={k}>{tx("kind", k)}</option>)}</Select>}</Field>
            <Field label={t("rec.timeframe")}>{(id) => <Input id={id} value={timeframe} onChange={(e) => setTimeframe(e.target.value)} />}</Field>
          </div>
          <div className="flex gap-2">
            <Button size="sm" onClick={() => review.mutate({ action: "correct", text, kind, timeframe_text: timeframe })} loading={review.isPending}>{t("common.save")}</Button>
            <Button size="sm" variant="secondary" onClick={() => setEditing(false)}>{t("common.cancel")}</Button>
          </div>
        </div>
      )}
      {(review.error || track.error) && <ErrorState error={review.error ?? track.error} />}
    </li>
  );
}

function EditDetails({ d, onClose }: { d: DocDetail; onClose: () => void }) {
  const { t, tx } = useI18n();
  const qc = useQueryClient();
  const orgs = useOrgs();
  const [form, setForm] = useState({ title: d.title, category: d.category, document_date: d.document_date ?? "", organization_id: d.organization?.id ?? "" });
  const m = useMutation({
    mutationFn: () => api.patch(`/documents/${d.id}`, { title: form.title, category: form.category, document_date: form.document_date || null, organization_id: form.organization_id || null }),
    onSuccess: () => { qc.invalidateQueries(); onClose(); },
  });
  return (
    <Dialog open onClose={onClose} title={t("docs.editDetails")}
      footer={<><Button variant="secondary" onClick={onClose}>{t("common.cancel")}</Button><Button onClick={() => m.mutate()} loading={m.isPending}>{t("common.save")}</Button></>}>
      <div className="flex flex-col gap-4">
        <Field label={t("journey.newTitle")}>{(id) => <Input id={id} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />}</Field>
        <Field label={t("docs.category")}>{(id) => <Select id={id} value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>{CATEGORIES.map((c) => <option key={c} value={c}>{tx("cat", c)}</option>)}</Select>}</Field>
        <Field label={t("common.date")}>{(id) => <Input id={id} type="date" value={form.document_date} onChange={(e) => setForm({ ...form, document_date: e.target.value })} />}</Field>
        <Field label={t("docs.organization")}>{(id) => <Select id={id} value={form.organization_id} onChange={(e) => setForm({ ...form, organization_id: e.target.value })}><option value="">—</option>{orgs.data?.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}</Select>}</Field>
        {m.error && <ErrorState error={m.error} />}
      </div>
    </Dialog>
  );
}

function AddRec({ d, onClose }: { d: DocDetail; onClose: () => void }) {
  const { t, tx } = useI18n();
  const qc = useQueryClient();
  const [text, setText] = useState("");
  const [kind, setKind] = useState("follow_up_visit");
  const m = useMutation({ mutationFn: () => api.post(`/patients/${d.patient_id}/recommendations`, { kind, text, document_id: d.id }), onSuccess: () => { qc.invalidateQueries(); onClose(); } });
  return (
    <Dialog open onClose={onClose} title={t("rec.add")}
      footer={<><Button variant="secondary" onClick={onClose}>{t("common.cancel")}</Button><Button onClick={() => m.mutate()} disabled={text.length < 4} loading={m.isPending}>{t("common.save")}</Button></>}>
      <div className="flex flex-col gap-4">
        <Field label={t("rec.text")}>{(id) => <Textarea id={id} value={text} onChange={(e) => setText(e.target.value)} dir="auto" />}</Field>
        <Field label={t("rec.kind")}>{(id) => <Select id={id} value={kind} onChange={(e) => setKind(e.target.value)}>{KINDS.map((k) => <option key={k} value={k}>{tx("kind", k)}</option>)}</Select>}</Field>
        {m.error && <ErrorState error={m.error} />}
      </div>
    </Dialog>
  );
}

export default function DocumentDetail() {
  const { id = "" } = useParams();
  const { t, tx } = useI18n();
  const f = useFormat();
  const nav = useNavigate();
  const qc = useQueryClient();
  const [dialog, setDialog] = useState<"edit" | "rec" | "delete" | "version" | null>(null);
  const [versionFile, setVersionFile] = useState<File | null>(null);
  const q = useQuery({
    queryKey: ["doc", id], queryFn: () => api.get<DocDetail>(`/documents/${id}`),
    refetchInterval: (query) => (["pending", "processing"].includes(query.state.data?.status ?? "") ? 1500 : false),
  });
  const reprocess = useMutation({ mutationFn: () => api.post(`/documents/${id}/reprocess`), onSuccess: () => qc.invalidateQueries() });
  const del = useMutation({ mutationFn: () => api.del(`/documents/${id}`), onSuccess: () => { qc.invalidateQueries(); nav("/app/documents"); } });
  const version = useMutation({
    mutationFn: () => { const fd = new FormData(); fd.append("file", versionFile!); return api.upload<{ id: string }>(`/documents/${id}/versions`, fd); },
    onSuccess: (r) => { qc.invalidateQueries(); setDialog(null); nav(`/app/documents/${r.id}`); },
  });

  if (q.isLoading) return <Spinner />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const d = q.data!;
  const busy = ["pending", "processing"].includes(d.status);

  return (
    <>
      <PageHeader title={d.title} subtitle={`${d.organization?.name ?? d.source_detected ?? t("common.unknownOrg")} · ${f.date(d.document_date)}`} help="uploading-documents"
        actions={<>
          <a href={`/api/documents/${d.id}/download`} className="inline-flex items-center gap-2 rounded-lg border border-line bg-surface px-4 py-2 text-sm font-medium hover:bg-surface-2"><Download className="size-4" aria-hidden />{t("common.download")}</a>
          {d.can_edit && <>
            <Button variant="secondary" icon={<Pencil className="size-4" aria-hidden />} onClick={() => setDialog("edit")}>{t("docs.editDetails")}</Button>
            <Button variant="secondary" icon={<Upload className="size-4" aria-hidden />} onClick={() => setDialog("version")} disabled={!d.is_latest}>{t("docs.newVersion")}</Button>
            <Button variant="ghost" icon={<RefreshCw className="size-4" aria-hidden />} onClick={() => reprocess.mutate()} loading={reprocess.isPending}>{t("docs.reprocess")}</Button>
            <Button variant="ghost" icon={<Trash2 className="size-4" aria-hidden />} onClick={() => setDialog("delete")} aria-label={t("common.delete")} />
          </>}
        </>} />
      {busy && <Notice tone="info">{t("docs.processing")}…</Notice>}
      {d.status === "needs_review" && d.status_detail && <div className="mb-4"><Notice tone="warn">{d.status_detail}</Notice></div>}
      {d.status === "failed" && <div className="mb-4"><Notice tone="danger">{d.status_detail}</Notice></div>}
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1fr_420px] mt-2">
        <Card title={t("docs.extractedText")}>
          {d.extracted_text ? <Highlighted text={d.extracted_text} recs={d.recommendations} /> : <EmptyState title={busy ? t("docs.processing") : t("common.none")} />}
        </Card>
        <div className="flex flex-col gap-6">
          <Card title={t("docs.metadata")}>
            <dl className="grid grid-cols-2 gap-4">
              <KeyVal k={t("common.status")} v={<StatusBadge status={d.status} />} />
              <KeyVal k={t("docs.category")} v={tx("cat", d.category)} />
              <KeyVal k={t("common.date")} v={f.date(d.document_date)} />
              <KeyVal k={t("docs.author")} v={d.author_name} />
              <KeyVal k={t("common.source")} v={d.source_detected} />
              <KeyVal k={t("docs.language")} v={d.language} />
              <KeyVal k={t("docs.size")} v={f.bytes(d.size_bytes)} />
              <KeyVal k={t("docs.uploadedAt")} v={f.dateTime(d.created_at)} />
              <KeyVal k={t("docs.original")} v={<span className="break-all">{d.original_filename}</span>} />
              <KeyVal k={t("docs.encrypted")} v={d.encrypted ? t("common.yes") : t("common.no")} />
            </dl>
            {d.duplicate_of_id && <div className="mt-3"><Notice tone="warn">{t("docs.duplicateOf")} — <Link className="underline" to={`/app/documents/${d.duplicate_of_id}`}>{t("common.open")}</Link></Notice></div>}
          </Card>
          <Card title={t("docs.recommendations")} action={d.can_edit ? <Button size="sm" variant="secondary" onClick={() => setDialog("rec")}>{t("rec.add")}</Button> : undefined}>
            {d.recommendations.length === 0 ? <p className="text-sm text-muted">{t("docs.noRecs")}</p> : (
              <ul className="divide-y divide-line" data-testid="rec-list">{d.recommendations.map((r) => <RecRow key={r.id} r={r} canEdit={d.can_edit} />)}</ul>
            )}
          </Card>
          {d.events.length > 0 && (
            <Card title={t("journey.title")}>
              <ul className="flex flex-col gap-2 text-sm">{d.events.map((e) => <li key={e.id}><Link className="text-brand hover:underline" to={`/app/journey?event=${e.id}`}>{f.date(e.occurred_at)} · {e.title}</Link> <StatusBadge status={e.verification_status} /></li>)}</ul>
            </Card>
          )}
          {d.versions.length > 1 && (
            <Card title={t("docs.versions")}>
              <ul className="flex flex-col gap-1.5 text-sm">
                {d.versions.map((v) => <li key={v.id}><Link className={v.id === d.id ? "font-semibold" : "text-brand hover:underline"} to={`/app/documents/${v.id}`}>{t("docs.v", { n: v.version })}</Link> · {f.dateTime(v.created_at)} {v.is_latest && <Badge tone="ok">{t("docs.latest")}</Badge>}</li>)}
              </ul>
            </Card>
          )}
          {d.import_report && (
            <Card title={t("docs.fhirReport")}>
              {(["imported", "skipped", "ignored_fields", "errors", "profiles_not_validated"] as const).map((k) => d.import_report![k]?.length ? (
                <div key={k} className="mb-3">
                  <h3 className="text-xs font-semibold text-muted mb-1">{t(({ imported: "docs.imported", skipped: "docs.skipped", ignored_fields: "docs.ignored", errors: "docs.errors", profiles_not_validated: "docs.profiles" } as const)[k])}</h3>
                  <ul className="text-xs flex flex-col gap-0.5">{d.import_report![k].map((x) => <li key={x}><code>{x}</code></li>)}</ul>
                </div>
              ) : null)}
            </Card>
          )}
        </div>
      </div>
      {dialog === "edit" && <EditDetails d={d} onClose={() => setDialog(null)} />}
      {dialog === "rec" && <AddRec d={d} onClose={() => setDialog(null)} />}
      <Dialog open={dialog === "delete"} onClose={() => setDialog(null)} title={t("common.delete")}
        footer={<><Button variant="secondary" onClick={() => setDialog(null)}>{t("common.cancel")}</Button><Button variant="danger" onClick={() => del.mutate()} loading={del.isPending}>{t("common.delete")}</Button></>}>
        <p className="text-sm">{t("docs.deleteConfirm")}</p>
      </Dialog>
      <Dialog open={dialog === "version"} onClose={() => setDialog(null)} title={t("docs.newVersion")}
        footer={<><Button variant="secondary" onClick={() => setDialog(null)}>{t("common.cancel")}</Button><Button onClick={() => version.mutate()} disabled={!versionFile} loading={version.isPending}>{t("docs.upload")}</Button></>}>
        <Field label={t("docs.chooseFile")}>{(fid) => <Input id={fid} type="file" accept=".pdf,.txt,.md,.json" onChange={(e) => setVersionFile(e.target.files?.[0] ?? null)} />}</Field>
        {version.error && <div className="mt-3"><ErrorState error={version.error} /></div>}
      </Dialog>
    </>
  );
}
