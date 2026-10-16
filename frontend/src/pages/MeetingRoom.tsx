import "@livekit/components-styles";
import {
  LiveKitRoom, RoomAudioRenderer, VideoConference, useConnectionState, useParticipants, useTracks,
} from "@livekit/components-react";
import { useQuery } from "@tanstack/react-query";
import { ConnectionState, Track } from "livekit-client";
import { ArrowLeft, FileLock2, FileText, PanelRight, ShieldCheck, Users } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { Badge, Button, ErrorState, Spinner } from "../components/ui";
import { api } from "../lib/api";
import { useI18n } from "../lib/i18n";
import type { Consultation } from "../lib/types";

interface JoinInfo { token: string; url: string; room: string; identity: string; expires_in: number }

function RoomStatus() {
  const { t } = useI18n();
  const participants = useParticipants();
  const state = useConnectionState();
  const remoteVideo = useTracks([Track.Source.Camera], { onlySubscribed: true }).filter((tr) => !tr.participant.isLocal).length;
  return (
    <div className="flex items-center gap-2 text-sm">
      <Badge tone={state === ConnectionState.Connected ? "ok" : "warn"} className="capitalize" >
        <span data-testid="connection-state">{state}</span>
      </Badge>
      <Badge tone="info" icon={<Users className="size-3.5" aria-hidden />}>
        <span data-testid="participant-count">{participants.length}</span>&nbsp;{t("room.participants", { count: "" }).trim()}
      </Badge>
      <span className="sr-only" data-testid="remote-video-count">{remoteVideo}</span>
    </div>
  );
}

export default function MeetingRoom() {
  const { id = "" } = useParams();
  const { t } = useI18n();
  const nav = useNavigate();
  const [join, setJoin] = useState<JoinInfo | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [panel, setPanel] = useState(true);
  const requested = useRef(false);
  const c = useQuery({ queryKey: ["consultation", id], queryFn: () => api.get<Consultation>(`/consultations/${id}`) });

  const presence = useCallback((event: string, detail?: string) => {
    api.post(`/consultations/${id}/presence`, { event, detail: detail?.slice(0, 200) }).catch(() => undefined);
  }, [id]);

  useEffect(() => {
    if (requested.current) return;
    requested.current = true;
    api.post<JoinInfo>(`/consultations/${id}/join`).then(setJoin).catch(setError);
  }, [id]);

  return (
    <div className="flex h-screen flex-col bg-bg">
      <header className="flex flex-wrap items-center gap-3 border-b border-line bg-surface px-4 py-2.5">
        <Link to={`/app/consultations/${id}`} className="rounded-md p-1.5 hover:bg-surface-2" aria-label={t("common.back")}><ArrowLeft className="size-5 rtl:-scale-x-100" aria-hidden /></Link>
        <div className="min-w-0 flex-1">
          <h1 className="truncate font-semibold">{t("room.title")} · {c.data?.title}</h1>
          <p className="text-xs text-muted inline-flex items-center gap-1"><ShieldCheck className="size-3.5" aria-hidden />{t("room.privacy")}</p>
        </div>
        <Button size="sm" variant="ghost" onClick={() => setPanel(!panel)} aria-pressed={panel} icon={<PanelRight className="size-4" aria-hidden />}>{t("room.documents")}</Button>
      </header>
      {error ? (
        <div className="p-6 max-w-xl mx-auto w-full"><ErrorState error={error} /><p className="mt-3 text-sm text-muted">{t("room.errorHint")}</p></div>
      ) : !join ? (
        <Spinner label={t("room.connecting")} />
      ) : (
        <LiveKitRoom serverUrl={join.url} token={join.token} connect video audio className="flex min-h-0 flex-1"
          onConnected={() => presence("joined")}
          onDisconnected={() => { presence("left"); nav(`/app/consultations/${id}`); }}
          onError={(e) => { presence("connection_error", e.message); setError(new Error(`${t("room.error")} (${e.message})`)); }}>
          <div className="flex min-h-0 flex-1 flex-col">
            <div className="flex items-center gap-2 border-b border-line bg-surface px-4 py-1.5"><RoomStatus /></div>
            <div className="flex min-h-0 flex-1">
              <div className="min-w-0 flex-1" data-testid="video-conference" data-lk-theme="default"><VideoConference /></div>
              {panel && (
                <aside className="hidden md:flex w-72 flex-col gap-3 border-s border-line bg-surface p-4 overflow-y-auto" aria-label={t("room.documents")}>
                  <h2 className="font-semibold text-sm">{t("room.documents")}</h2>
                  {c.data?.documents.length === 0 && <p className="text-sm text-muted">{t("common.none")}</p>}
                  <ul className="flex flex-col gap-2">
                    {c.data?.documents.map((d) => (
                      <li key={d.id} className="text-sm flex items-start gap-2">
                        {d.accessible ? <FileText className="size-4 mt-0.5 text-brand" aria-hidden /> : <FileLock2 className="size-4 mt-0.5 text-muted" aria-hidden />}
                        {d.accessible
                          ? <a href={`/app/documents/${d.id}`} target="_blank" rel="noreferrer" className="text-brand hover:underline">{d.title}</a>
                          : <span className="text-muted">{d.title} — {t("consult.notAccessible")}</span>}
                      </li>
                    ))}
                  </ul>
                  <p className="mt-auto text-xs text-muted">{t("consult.recordingOff")}</p>
                </aside>
              )}
            </div>
          </div>
          <RoomAudioRenderer />
        </LiveKitRoom>
      )}
    </div>
  );
}
