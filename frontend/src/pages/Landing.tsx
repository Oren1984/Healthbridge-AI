import { Activity, Globe2, HeartPulse, ShieldCheck } from "lucide-react";
import { ButtonLink } from "../components/ui";
import { useI18n } from "../lib/i18n";
import { PublicShell } from "./PublicShell";

export default function Landing() {
  const { t } = useI18n();
  const features = [
    { icon: <Activity className="size-6" aria-hidden />, title: t("landing.f1.title"), body: t("landing.f1.body") },
    { icon: <HeartPulse className="size-6" aria-hidden />, title: t("landing.f2.title"), body: t("landing.f2.body") },
    { icon: <Globe2 className="size-6" aria-hidden />, title: t("landing.f3.title"), body: t("landing.f3.body") },
    { icon: <ShieldCheck className="size-6" aria-hidden />, title: t("landing.f4.title"), body: t("landing.f4.body") },
  ];
  return (
    <PublicShell>
      <section className="px-4 sm:px-8 pt-10 pb-16 max-w-6xl mx-auto">
        <p className="text-sm font-semibold text-brand">{t("app.tagline")}</p>
        <h1 className="mt-3 text-4xl sm:text-5xl font-semibold tracking-tight max-w-3xl">{t("landing.title")}</h1>
        <p className="mt-5 text-lg text-muted max-w-2xl">{t("landing.subtitle")}</p>
        <div className="mt-8 flex flex-wrap gap-3">
          <ButtonLink to="/login" variant="primary">{t("landing.cta")}</ButtonLink>
          <ButtonLink to="/demo">{t("landing.demo")}</ButtonLink>
        </div>
        <div className="mt-14 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {features.map((f) => (
            <article key={f.title} className="card p-5">
              <div className="inline-flex rounded-lg bg-brand-soft p-2 text-brand">{f.icon}</div>
              <h2 className="mt-3 font-semibold">{f.title}</h2>
              <p className="mt-1.5 text-sm text-muted">{f.body}</p>
            </article>
          ))}
        </div>
      </section>
    </PublicShell>
  );
}
