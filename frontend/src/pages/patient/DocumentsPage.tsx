import { DocumentsPanel } from "../../components/panels/DocumentsPanel";
import { PageHeader } from "../../components/ui";
import { useMe } from "../../lib/auth";
import { useI18n } from "../../lib/i18n";

export default function DocumentsPage() {
  const me = useMe();
  const { t } = useI18n();
  return (
    <>
      <PageHeader title={t("docs.title")} subtitle={t("docs.subtitle")} help="uploading-documents" />
      <DocumentsPanel patientId={me.id} canUpload />
    </>
  );
}
