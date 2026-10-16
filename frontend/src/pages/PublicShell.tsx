import { Moon, Sun } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link } from "react-router";
import { Badge } from "../components/ui";
import { useI18n } from "../lib/i18n";
import { applyTheme } from "../lib/theme";

export function PublicShell({ children }: { children: ReactNode }) {
  const { t, lang, setLang } = useI18n();
  const [dark, setDark] = useState(() => document.documentElement.dataset.theme === "dark");
  return (
    <div className="min-h-screen flex flex-col">
      <a href="#main" className="skip-link rounded-lg bg-brand px-3 py-2 text-on-brand">{t("nav.skip")}</a>
      <header className="flex items-center gap-3 px-4 sm:px-8 py-4">
        <Link to="/" className="flex items-center gap-2.5">
          <img src="/favicon.svg" alt="" className="size-8" />
          <span className="font-semibold">{t("app.name")}</span>
        </Link>
        <Badge tone="warn">{t("app.synthetic")}</Badge>
        <div className="flex-1" />
        <button onClick={() => setLang(lang === "en" ? "he" : "en")} className="rounded-md px-2 py-1 text-sm font-medium hover:bg-surface-2" data-testid="lang-toggle">
          {t("nav.language")}
        </button>
        <button onClick={() => { applyTheme(dark ? "light" : "dark"); setDark(!dark); }} className="rounded-md p-1.5 hover:bg-surface-2"
          aria-label={t("nav.theme")} aria-pressed={dark}>
          {dark ? <Sun className="size-5" aria-hidden /> : <Moon className="size-5" aria-hidden />}
        </button>
      </header>
      <main id="main" tabIndex={-1} className="flex-1 focus:outline-none">{children}</main>
      <footer className="px-4 sm:px-8 py-6 text-xs text-muted border-t border-line">{t("app.disclaimer")}</footer>
    </div>
  );
}
