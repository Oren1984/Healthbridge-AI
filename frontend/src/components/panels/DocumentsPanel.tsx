import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileJson, FileText, Lock, Search, Upload } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router";
import { api, ApiError, qs } from "../../lib/api";
import { useFormat } from "../../lib/format";
import { useI18n } from "../../lib/i18n";
import type { Doc, Org } from "../../lib/types";
import { Badge, Button, Dialog, EmptyState, ErrorState, Field, Input, Notice, Select, Spinner, StatusBadge } from "../ui";

export const CATEGORIES = ["consultation_note", "lab_result", "imaging_report", "referral", "discharge_summary",
  "consultation_summary", "fhir_record", "other"];

export function useOrgs() {
  return useQuery({ queryKey: ["orgs"], queryFn: () => api.get<Org[]>("/organizations"), staleTime: 600_000 });
}

function useDebounced<T>(v: T, ms = 300) {
  const [d, setD] = useState(v);
  useEffect(() => {
    const id = setTimeout(() => setD(v), ms);
    return () => clearTimeout(id);
  }, [v, ms]);
  return d;
}

export function UploadDialog({ patientId, open, onClose }: { patientId: string; open: boolean; onClose: () => void }) {
  const { t, tx } = useI18n();
  const qc = useQueryClient();
  const orgs = useOrgs();
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [category, setCategory] = useState("");
  const [org, setOrg] = useState("");
  const [result, setResult] = useState<{ ok?: Doc; dup?: string; err?: unknown } | null>(null);
  const meta = useQuery({ queryKey: ["meta"], queryFn: () => api.get<{ max_upload_mb: number }>("/meta"), staleTime: Infinity });

  const m = useMutation({
    mutationFn: async () => {
      const fd = new FormData();
      fd.append("file", file!);
      if (title) fd.append("title", title);
      if (category) fd.append("category", category);
      if (org) fd.append("organization_id", org);
      return api.upload<Doc>(`/patients/${patientId}/documents`, fd);
    },
    onSuccess: (d) => {
      setResult({ ok: d });
      qc.invalidateQueries();
    },
    onError: (e) => {
      if (e instanceof ApiError && e.status === 409) setResult({ dup: e.body?.existing_id });
      else setResult({ err: e });
    },
  });

  const reset = () => {
    setFile(null); setTitle(""); setCategory(""); setOrg(""); setResult(null);
    if (fileRef.current) fileRef.current.value = "";
  };

  function submit(e: FormEvent) {
    e.preventDefault();
    if (file) m.mutate();
  }

  return (
    <Dialog open={open} onClose={() => { reset(); onClose(); }} title={t("docs.upload")}
      footer={result?.ok ? (
        <>
          <Button variant="secondary" onClick={reset}>{t("docs.upload")}</Button>
          <Link to={`/app/documents/${result.ok.id}`} className="inline-flex items-center rounded-lg bg-brand px-4 py-2 text-sm font-medium text-on-brand">{t("common.open")}</Link>
        </>
      ) : (
        <>
          <Button variant="secondary" onClick={() => { reset(); onClose(); }}>{t("common.cancel")}</Button>
          <Button type="submit" form="upload-form" disabled={!file} loading={m.isPending} data-testid="upload-submit">{t("docs.upload")}</Button>
        </>
      )}>
      {result?.ok ? (
        <Notice tone="ok">{t("docs.uploaded")}</Notice>
      ) : (
        <form id="upload-form" onSubmit={submit} className="flex flex-col gap-4">
          <p className="text-sm text-muted">{t("docs.uploadHint", { mb: meta.data?.max_upload_mb ?? 10 })}</p>
          <Field label={t("docs.chooseFile")} required>
            {(id) => <Input id={id} ref={fileRef} type="file" accept=".pdf,.txt,.md,.json" onChange={(e) => setFile(e.target.files?.[0] ?? null)} data-testid="upload-file" />}
          </Field>
          <Field label={t("docs.titleOptional")}>{(id) => <Input id={id} value={title} onChange={(e) => setTitle(e.target.value)} maxLength={300} />}</Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={t("docs.category")}>
              {(id) => (
                <Select id={id} value={category} onChange={(e) => setCategory(e.target.value)}>
                  <option value="">{t("docs.categoryAuto")}</option>
                  {CATEGORIES.map((c) => <option key={c} value={c}>{tx("cat", c)}</option>)}
                </Select>
              )}
            </Field>
            <Field label={t("docs.organization")}>
              {(id) => (
                <Select id={id} value={org} onChange={(e) => setOrg(e.target.value)}>
                  <option value="">{t("docs.orgAuto")}</option>
                  {orgs.data?.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
                </Select>
              )}
            </Field>
          </div>
          {result?.dup && (
            <Notice tone="warn">{t("docs.duplicate")} <Link className="underline" to={`/app/documents/${result.dup}`}>{t("docs.openExisting")}</Link></Notice>
          )}
          {result?.err ? <ErrorState error={result.err} /> : null}
        </form>
      )}
    </Dialog>
  );
}

export function DocumentsPanel({ patientId, canUpload }: { patientId: string; canUpload: boolean }) {
  const { t, tx } = useI18n();
  const f = useFormat();
  const [q, setQ] = useState("");
  const [category, setCategory] = useState("");
  const [upload, setUpload] = useState(false);
  const dq = useDebounced(q);
  const docs = useQuery({
    queryKey: ["docs", patientId, dq, category],
    queryFn: () => api.get<Doc[]>(`/patients/${patientId}/documents${qs({ q: dq, category })}`),
    refetchInterval: (query) => (query.state.data?.some((d) => d.status === "pending" || d.status === "processing") ? 2000 : false),
  });

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-3">
        <div className="relative flex-1 min-w-56">
          <Search className="absolute start-3 top-1/2 -translate-y-1/2 size-4 text-muted" aria-hidden />
          <Input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("docs.searchPlaceholder")}
            aria-label={t("common.search")} className="ps-9" />
        </div>
        <Select value={category} onChange={(e) => setCategory(e.target.value)} aria-label={t("docs.category")} className="w-auto">
          <option value="">{t("common.all")}</option>
          {CATEGORIES.map((c) => <option key={c} value={c}>{tx("cat", c)}</option>)}
        </Select>
        {canUpload && <Button icon={<Upload className="size-4" aria-hidden />} onClick={() => setUpload(true)} data-testid="open-upload">{t("docs.upload")}</Button>}
      </div>
      {docs.isLoading && <Spinner />}
      {docs.error && <ErrorState error={docs.error} onRetry={() => docs.refetch()} />}
      {docs.data && docs.data.length === 0 && (
        <EmptyState title={t("docs.empty")} action={canUpload ? <Button onClick={() => setUpload(true)}>{t("docs.upload")}</Button> : undefined} />
      )}
      {docs.data && docs.data.length > 0 && (
        <ul className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3" data-testid="document-list">
          {docs.data.map((d) => (
            <li key={d.id}>
              <Link to={`/app/documents/${d.id}`} className="card flex h-full flex-col gap-2 p-4 hover:border-brand">
                <div className="flex items-start gap-3">
                  <div className="rounded-lg bg-brand-soft p-2 text-brand">
                    {d.category === "fhir_record" ? <FileJson className="size-5" aria-hidden /> : <FileText className="size-5" aria-hidden />}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="font-medium leading-snug line-clamp-2" dir="auto">{d.title}</p>
                    <p className="text-xs text-muted mt-0.5">{d.organization?.name ?? d.source_detected ?? t("common.unknownOrg")}</p>
                  </div>
                </div>
                <div className="mt-auto flex flex-wrap items-center gap-1.5 pt-1">
                  <StatusBadge status={d.status} />
                  <Badge>{tx("cat", d.category)}</Badge>
                  {d.version > 1 && <Badge tone="info">{t("docs.v", { n: d.version })}</Badge>}
                  <span className="ms-auto inline-flex items-center gap-1 text-xs text-muted">
                    <Lock className="size-3" aria-label={t("docs.encrypted")} /> {f.date(d.document_date ?? d.created_at)}
                  </span>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
      {canUpload && <UploadDialog patientId={patientId} open={upload} onClose={() => setUpload(false)} />}
    </div>
  );
}
