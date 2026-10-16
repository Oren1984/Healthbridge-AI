import { JourneyPanel } from "../../components/panels/JourneyPanel";
import { PageHeader } from "../../components/ui";
import { useMe } from "../../lib/auth";
import { useI18n } from "../../lib/i18n";

export default function JourneyPage() {
  const me = useMe();
  const { t } = useI18n();
  return (
    <>
      <PageHeader title={t("journey.title")} subtitle={t("journey.subtitle")} help="medical-journey" />
      <JourneyPanel patientId={me.id} canEdit />
    </>
  );
}
