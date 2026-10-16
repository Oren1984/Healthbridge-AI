import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Bot, Info, Send, User } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router";
import { Badge, Button, Card, ErrorState, Input, Notice, PageHeader, Select, StatusBadge } from "../components/ui";
import { api } from "../lib/api";
import { useMe } from "../lib/auth";
import { useI18n } from "../lib/i18n";
import type { AgentReply } from "../lib/types";

interface Turn { role: "user" | "assistant"; text?: string; reply?: AgentReply }
interface Shared { patient: { id: string; full_name: string } }

function Reply({ r }: { r: AgentReply }) {
  const { t } = useI18n();
  const qc = useQueryClient();
  const [actionState, setActionState] = useState<"pending" | "confirmed" | "cancelled">("pending");
  const confirm = useMutation({ mutationFn: (path: string) => api.post(path), onSuccess: (_, path) => { setActionState(path.endsWith("confirm") ? "confirmed" : "cancelled"); qc.invalidateQueries(); } });
  const tone = r.mode === "refusal" ? "warn" : r.mode === "local_llm" ? "violet" : r.mode === "fallback" ? "warn" : "neutral";
  return (
    <div className="flex flex-col gap-3" data-testid="assistant-reply" data-mode={r.mode} data-intent={r.intent}>
      <p className="whitespace-pre-wrap text-sm" dir="auto">{r.answer}</p>
      {r.warnings.map((w) => <Notice key={w} tone="warn" icon={<AlertTriangle className="size-4 mt-0.5" aria-hidden />}>{w}</Notice>)}
      {r.items.length > 0 && (
        <ul className="flex flex-col gap-1.5">
          {r.items.map((it, i) => (
            <li key={i} className="text-sm flex flex-wrap items-center gap-2">
              {it.link ? <Link className="text-brand hover:underline" to={it.link} dir="auto">{it.title ?? it.text ?? it.slug ?? t("help.allArticles")}</Link> : <span dir="auto">{it.text}</span>}
              {it.status && <StatusBadge status={it.status} />}
            </li>
          ))}
        </ul>
      )}
      {r.sources.length > 0 && (
        <details className="rounded-lg border border-line p-3" open>
          <summary className="cursor-pointer text-sm font-medium">{t("assistant.sources")} ({r.sources.length})</summary>
          <ul className="mt-2 flex flex-col gap-3">
            {r.sources.map((s) => (
              <li key={s.ref} className="text-sm" data-testid="assistant-source">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone="brand">{s.ref}</Badge>
                  <Link className="text-brand hover:underline" to={`/app/documents/${s.document_id}`}>{s.title}</Link>
                  {s.suspicious && <Badge tone="danger" icon={<AlertTriangle className="size-3" aria-hidden />}>{t("assistant.suspicious")}</Badge>}
                  <span className="text-xs text-muted">score {s.score.toFixed(2)}</span>
                </div>
                <blockquote className="mt-1 border-s-2 border-line ps-3 text-muted text-xs whitespace-pre-wrap" dir="auto">{s.excerpt}</blockquote>
              </li>
            ))}
          </ul>
        </details>
      )}
      {r.pending_action && (
        <div className="rounded-lg border border-brand p-3 flex flex-col gap-2">
          <p className="text-sm font-medium" dir="auto">“{r.pending_action.payload.title}”</p>
          {actionState === "pending" ? (
            <div className="flex gap-2">
              <Button size="sm" onClick={() => confirm.mutate(`/assistant/actions/${r.pending_action!.id}/confirm`)} loading={confirm.isPending} data-testid="confirm-action">{t("assistant.confirmAction")}</Button>
              <Button size="sm" variant="secondary" onClick={() => confirm.mutate(`/assistant/actions/${r.pending_action!.id}/cancel`)}>{t("assistant.cancelAction")}</Button>
            </div>
          ) : <Notice tone={actionState === "confirmed" ? "ok" : "neutral"}>{actionState === "confirmed" ? t("assistant.actionDone") : t("common.cancel")}</Notice>}
        </div>
      )}
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
        <Badge tone={tone as never}>{r.mode}</Badge><span>{r.label}</span>
        {r.tools_used.length > 0 && <span>· tools: {r.tools_used.join(", ")}</span>}
      </div>
    </div>
  );
}

export default function Assistant() {
  const me = useMe();
  const { t } = useI18n();
  const [params] = useSearchParams();
  const shared = useQuery({ queryKey: ["shared-with-me"], queryFn: () => api.get<Shared[]>("/shared-with-me"), enabled: me.role === "professional" });
  const status = useQuery({ queryKey: ["assistant-status"], queryFn: () => api.get<{ mode: string; embedding_provider: string; ollama: { reachable: boolean; model_available: boolean } | null }>("/assistant/status") });
  const [patientId, setPatientId] = useState(me.role === "patient" ? me.id : params.get("patient") ?? "");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [msg, setMsg] = useState("");
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (me.role === "professional" && !patientId && shared.data?.length) setPatientId(shared.data[0].patient.id);
  }, [shared.data, patientId, me.role]);
  useEffect(() => {
    // Block body: scrollIntoView may return a Promise, which must not become the effect cleanup.
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns]);

  const ask = useMutation({
    mutationFn: (message: string) => api.post<AgentReply>("/assistant/query", { patient_id: patientId, message }),
    onSuccess: (reply) => setTurns((x) => [...x, { role: "assistant", reply }]),
  });
  const send = (text: string) => {
    if (!text.trim() || !patientId) return;
    setTurns((x) => [...x, { role: "user", text }]);
    setMsg("");
    ask.mutate(text);
  };
  const submit = (e: FormEvent) => { e.preventDefault(); send(msg); };
  const suggestions = [t("assistant.suggest1"), t("assistant.suggest2"), t("assistant.suggest3"), t("assistant.suggest4")];

  return (
    <>
      <PageHeader title={t("assistant.title")} subtitle={t("assistant.subtitle")} help="ai-limitations" />
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1fr_320px]">
        <Card className="flex flex-col min-h-[60vh]">
          {me.role === "professional" && (
            <div className="mb-4 max-w-sm">
              <Select aria-label={t("assistant.patient")} value={patientId} onChange={(e) => { setPatientId(e.target.value); setTurns([]); }}>
                {shared.data?.length === 0 && <option value="">{t("pro.noPatients")}</option>}
                {shared.data?.map((s) => <option key={s.patient.id} value={s.patient.id}>{s.patient.full_name}</option>)}
              </Select>
            </div>
          )}
          <div className="flex-1 flex flex-col gap-4 overflow-y-auto" aria-live="polite" data-testid="assistant-transcript">
            {turns.length === 0 && (
              <div className="flex flex-wrap gap-2">
                {suggestions.map((s) => <Button key={s} size="sm" variant="secondary" onClick={() => send(s)} disabled={!patientId}>{s}</Button>)}
              </div>
            )}
            {turns.map((tn, i) => (
              <div key={i} className={`flex gap-3 ${tn.role === "user" ? "justify-end" : ""}`}>
                {tn.role === "assistant" && <div className="rounded-full bg-brand-soft p-2 h-fit text-brand"><Bot className="size-4" aria-hidden /></div>}
                <div className={`max-w-[85%] rounded-2xl px-4 py-3 ${tn.role === "user" ? "bg-brand text-on-brand" : "bg-surface-2"}`}>
                  {tn.text && <p className="text-sm whitespace-pre-wrap" dir="auto">{tn.text}</p>}
                  {tn.reply && <Reply r={tn.reply} />}
                </div>
                {tn.role === "user" && <div className="rounded-full bg-surface-2 p-2 h-fit"><User className="size-4" aria-hidden /></div>}
              </div>
            ))}
            {ask.isPending && <p className="text-sm text-muted">{t("common.loading")}</p>}
            {ask.error && <ErrorState error={ask.error} />}
            <div ref={endRef} />
          </div>
          <form onSubmit={submit} className="mt-4 flex gap-2">
            <Input value={msg} onChange={(e) => setMsg(e.target.value)} placeholder={t("assistant.placeholder")} aria-label={t("assistant.placeholder")} maxLength={1000} dir="auto" data-testid="assistant-input" />
            <Button type="submit" disabled={!msg.trim() || !patientId} loading={ask.isPending} icon={<Send className="size-4 rtl:-scale-x-100" aria-hidden />}>{t("assistant.send")}</Button>
          </form>
        </Card>
        <div className="flex flex-col gap-4">
          <Card title={t("assistant.mode")}>
            <p className="text-sm"><Badge tone={status.data?.mode === "ollama" ? "violet" : "neutral"}>{status.data?.mode ?? "…"}</Badge></p>
            {status.data?.ollama && <p className="mt-2 text-xs text-muted">Ollama: {status.data.ollama.reachable ? "reachable" : "unreachable"} · model {status.data.ollama.model_available ? "available" : "missing"}</p>}
            <p className="mt-2 text-xs text-muted">Embeddings: {status.data?.embedding_provider}</p>
          </Card>
          <Notice tone="info" icon={<Info className="size-4 mt-0.5" aria-hidden />}>{t("assistant.limits")} <Link className="underline" to="/app/help/ai-limitations">{t("common.learnMore")}</Link></Notice>
        </div>
      </div>
    </>
  );
}
