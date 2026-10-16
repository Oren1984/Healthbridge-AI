import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, BellOff } from "lucide-react";
import { useNavigate } from "react-router";
import { Badge, Button, Card, EmptyState, ErrorState, Notice, PageHeader, Spinner } from "../components/ui";
import { api } from "../lib/api";
import { useFormat } from "../lib/format";
import { useI18n } from "../lib/i18n";
import type { Notification } from "../lib/types";

export default function Notifications() {
  const { t, tx } = useI18n();
  const f = useFormat();
  const qc = useQueryClient();
  const nav = useNavigate();
  const q = useQuery({ queryKey: ["notifications"], queryFn: () => api.get<{ items: Notification[]; unread: number; delivery_note: string }>("/notifications") });
  const prefs = useQuery({ queryKey: ["notif-prefs"], queryFn: () => api.get<Record<string, boolean>>("/notifications/preferences") });
  const read = useMutation({ mutationFn: (id: string) => api.post(`/notifications/${id}/read`), onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }) });
  const readAll = useMutation({ mutationFn: () => api.post("/notifications/read-all"), onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }) });
  const setPref = useMutation({ mutationFn: (body: Record<string, boolean>) => api.put("/notifications/preferences", body), onSuccess: () => qc.invalidateQueries({ queryKey: ["notif-prefs"] }) });

  const open = (n: Notification) => {
    if (!n.read_at) read.mutate(n.id);
    if (n.link) nav(n.link);
  };

  return (
    <>
      <PageHeader title={t("notif.title")} actions={<Button variant="secondary" onClick={() => readAll.mutate()} disabled={!q.data?.unread}>{t("notif.markAll")}</Button>} />
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          {q.isLoading && <Spinner />}
          {q.error && <ErrorState error={q.error} />}
          {q.data?.items.length === 0 && <EmptyState icon={<BellOff className="size-8" aria-hidden />} title={t("notif.empty")} />}
          <ul className="divide-y divide-line" data-testid="notification-list">
            {q.data?.items.map((n) => (
              <li key={n.id}>
                <button onClick={() => open(n)} className="w-full text-start py-3 flex items-start gap-3 hover:bg-surface-2 rounded-lg px-2">
                  <Bell className={`size-4 mt-1 shrink-0 ${n.read_at ? "text-muted" : "text-brand"}`} aria-hidden />
                  <div className="flex-1 min-w-0">
                    <p className={`text-sm ${n.read_at ? "text-muted" : "font-medium"}`} dir="auto">{n.title}</p>
                    {n.body && <p className="text-xs text-muted mt-0.5" dir="auto">{n.body}</p>}
                    <p className="text-xs text-muted mt-0.5">{f.relative(n.created_at)} · {tx("notif.kind", n.kind)}</p>
                  </div>
                  {!n.read_at && <Badge tone="brand">●<span className="sr-only">unread</span></Badge>}
                </button>
              </li>
            ))}
          </ul>
        </Card>
        <Card title={t("notif.prefs")}>
          <Notice tone="neutral">{t("notif.inAppOnly")}</Notice>
          <ul className="mt-4 flex flex-col gap-2">
            {prefs.data && Object.entries(prefs.data).map(([k, v]) => (
              <li key={k}><label className="flex items-center justify-between gap-3 text-sm">
                <span>{tx("notif.kind", k)}</span>
                <input type="checkbox" role="switch" checked={v} onChange={(e) => setPref.mutate({ [k]: e.target.checked })} className="size-4 accent-[var(--primary)]" />
              </label></li>
            ))}
          </ul>
        </Card>
      </div>
    </>
  );
}
