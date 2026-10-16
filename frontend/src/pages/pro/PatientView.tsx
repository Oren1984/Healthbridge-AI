import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router";
import { CareGapsPanel } from "../../components/panels/CareGapsPanel";
import { DocumentsPanel } from "../../components/panels/DocumentsPanel";
import { JourneyPanel } from "../../components/panels/JourneyPanel";
import { ButtonLink, EmptyState, Notice, PageHeader, Spinner, Tabs } from "../../components/ui";
import { api } from "../../lib/api";
import { useFormat } from "../../lib/format";
import { useI18n } from "../../lib/i18n";
import type { Grant } from "../../lib/types";

export default function PatientView() {
  const { pid = "" } = useParams();
  const { t } = useI18n();
  const f = useFormat();
  const [tab, setTab] = useState("docs");
  const shared = useQuery({ queryKey: ["shared-with-me"], queryFn: () => api.get<{ patient: { id: string; full_name: string }; grants: Grant[] }[]>("/shared-with-me") });
  if (shared.isLoading) return <Spinner />;
  const entry = shared.data?.find((s) => s.patient.id === pid);
  if (!entry) return <EmptyState title={t("errors.notFound")} body={t("pro.noPatients")} action={<ButtonLink to="/app/pro">{t("common.back")}</ButtonLink>} />;
  const journey = entry.grants.some((g) => g.include_journey);
  const gaps = entry.grants.some((g) => g.include_care_gaps);
  const until = entry.grants.map((g) => g.expires_at).sort().slice(-1)[0];

  return (
    <>
      <PageHeader title={entry.patient.full_name} subtitle={t("pro.access", { date: f.dateTime(until) })} />
      <div className="mb-4"><Notice tone="neutral">{t("pro.subtitle")}</Notice></div>
      <Tabs label={entry.patient.full_name} value={tab} onChange={setTab} tabs={[
        { id: "docs", label: t("pro.tabDocs") }, { id: "journey", label: t("pro.tabJourney") }, { id: "gaps", label: t("pro.tabGaps") },
      ]} />
      {tab === "docs" && <DocumentsPanel patientId={pid} canUpload={false} />}
      {tab === "journey" && (journey ? <JourneyPanel patientId={pid} canEdit={false} /> : <EmptyState title={t("pro.noSection")} />)}
      {tab === "gaps" && (gaps ? <CareGapsPanel patientId={pid} isPatient={false} /> : <EmptyState title={t("pro.noSection")} />)}
      <div className="mt-6"><ButtonLink to={`/app/assistant?patient=${pid}`}>{t("pro.tabAssistant")}</ButtonLink></div>
    </>
  );
}
