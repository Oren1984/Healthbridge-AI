import { CareGapsPanel } from "../../components/panels/CareGapsPanel";
import { PageHeader } from "../../components/ui";
import { useMe } from "../../lib/auth";
import { useI18n } from "../../lib/i18n";

export default function CareGapsPage() {
  const me = useMe();
  const { t } = useI18n();
  return (
    <>
      <PageHeader title={t("careGaps.title")} subtitle={t("careGaps.subtitle")} help="understanding-care-gaps" />
      <CareGapsPanel patientId={me.id} isPatient />
    </>
  );
}
