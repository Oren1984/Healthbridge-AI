import { useAuth } from "../lib/auth";
import { useI18n } from "../lib/i18n";
import { ButtonLink, EmptyState } from "../components/ui";

export default function NotFound() {
  const { t } = useI18n();
  const { user } = useAuth();
  return (
    <div className="py-16">
      <EmptyState title={t("errors.notFound")} body={t("errors.notFoundBody")}
        action={<ButtonLink to={user ? "/app" : "/"} variant="primary">{t("errors.goHome")}</ButtonLink>} />
    </div>
  );
}
