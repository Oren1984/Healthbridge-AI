import { useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import {
  Activity, Bell, Bot, Briefcase, CalendarClock, ClipboardCheck, FileText, HeartPulse, HelpCircle, LayoutDashboard,
  LogOut, Menu, Moon, Settings, Share2, ShieldCheck, Sun, Wrench, X,
} from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router";
import { api } from "../lib/api";
import { useAuth, useMe } from "../lib/auth";
import { useI18n } from "../lib/i18n";
import { applyTheme, getThemePref } from "../lib/theme";
import type { TKey } from "../i18n/en";
import type { Me } from "../lib/types";
import { ErrorBoundary } from "./ErrorBoundary";
import { Badge } from "./ui";

interface NavItem { to: string; label: TKey; icon: ReactNode }

const ICON = "size-4.5 shrink-0";
const NAV: Record<string, NavItem[]> = {
  patient: [
    { to: "/app/dashboard", label: "nav.dashboard", icon: <LayoutDashboard className={ICON} aria-hidden /> },
    { to: "/app/journey", label: "nav.journey", icon: <Activity className={ICON} aria-hidden /> },
    { to: "/app/documents", label: "nav.documents", icon: <FileText className={ICON} aria-hidden /> },
    { to: "/app/care-gaps", label: "nav.careGaps", icon: <HeartPulse className={ICON} aria-hidden /> },
    { to: "/app/tasks", label: "nav.tasks", icon: <ClipboardCheck className={ICON} aria-hidden /> },
    { to: "/app/sharing", label: "nav.sharing", icon: <Share2 className={ICON} aria-hidden /> },
    { to: "/app/consultations", label: "nav.consultations", icon: <CalendarClock className={ICON} aria-hidden /> },
    { to: "/app/assistant", label: "nav.assistant", icon: <Bot className={ICON} aria-hidden /> },
    { to: "/app/privacy", label: "nav.privacy", icon: <ShieldCheck className={ICON} aria-hidden /> },
  ],
  professional: [
    { to: "/app/pro", label: "nav.workspace", icon: <Briefcase className={ICON} aria-hidden /> },
    { to: "/app/consultations", label: "nav.consultations", icon: <CalendarClock className={ICON} aria-hidden /> },
    { to: "/app/assistant", label: "nav.assistant", icon: <Bot className={ICON} aria-hidden /> },
  ],
  admin: [{ to: "/app/admin", label: "nav.admin", icon: <Wrench className={ICON} aria-hidden /> }],
};
const COMMON: NavItem[] = [
  { to: "/app/notifications", label: "nav.notifications", icon: <Bell className={ICON} aria-hidden /> },
  { to: "/app/help", label: "nav.help", icon: <HelpCircle className={ICON} aria-hidden /> },
  { to: "/app/settings", label: "nav.settings", icon: <Settings className={ICON} aria-hidden /> },
];

function useUnread() {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["notifications"],
    queryFn: () => api.get<{ unread: number }>("/notifications"),
    refetchInterval: 60_000,
  });
  useEffect(() => {
    let ws: WebSocket | null = null;
    let closed = false;
    let retry: number | undefined;
    const connect = () => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${location.host}/api/ws`);
      ws.onmessage = () => qc.invalidateQueries({ queryKey: ["notifications"] });
      ws.onclose = () => {
        if (!closed) retry = window.setTimeout(connect, 10_000);
      };
    };
    connect();
    return () => {
      closed = true;
      window.clearTimeout(retry);
      ws?.close();
    };
  }, [qc]);
  return q.data?.unread ?? 0;
}

function SideNav({ onNavigate }: { onNavigate?: () => void }) {
  const me = useMe();
  const { t } = useI18n();
  const unread = useUnread();
  const items = [...NAV[me.role], ...COMMON];
  return (
    <nav aria-label={t("nav.main")} className="flex flex-col gap-0.5">
      {items.map((it) => (
        <NavLink key={it.to} to={it.to} onClick={onNavigate} end={it.to === "/app/pro"}
          className={({ isActive }) => clsx("flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium",
            isActive ? "bg-brand-soft text-brand" : "text-muted hover:bg-surface-2 hover:text-ink")}>
          {it.icon}
          <span className="flex-1">{t(it.label)}</span>
          {it.to === "/app/notifications" && unread > 0 && (
            <span className="rounded-full bg-danger px-1.5 text-xs text-white" aria-label={`${unread}`}>{unread}</span>
          )}
        </NavLink>
      ))}
    </nav>
  );
}

function Brand() {
  const { t } = useI18n();
  return (
    <div className="flex items-center gap-2.5">
      <img src="/favicon.svg" alt="" className="size-8" />
      <div className="leading-tight">
        <div className="font-semibold">{t("app.name")}</div>
        <Badge tone="warn" className="mt-0.5">{t("app.synthetic")}</Badge>
      </div>
    </div>
  );
}

export function Layout() {
  const me = useMe();
  const { logout } = useAuth();
  const { t, lang, setLang, tx } = useI18n();
  const nav = useNavigate();
  const loc = useLocation();
  const [open, setOpen] = useState(false);
  const [dark, setDark] = useState(() => document.documentElement.dataset.theme === "dark");

  const firstRender = useRef(true);
  useEffect(() => {
    setOpen(false);
    // On client-side navigation, move focus to the new page's main region (announced by screen readers).
    if (firstRender.current) firstRender.current = false;
    else document.getElementById("main")?.focus({ preventScroll: true });
  }, [loc.pathname]);
  const { setUser } = useAuth();
  const switchLang = () => {
    const next = lang === "en" ? "he" : "en";
    setLang(next);
    // Persist to the profile so the choice survives reloads and other devices.
    api.patch<{ user: Me }>("/auth/me", { locale: next }).then((r) => setUser(r.user)).catch(() => undefined);
  };

  const toggleTheme = () => {
    const next = dark ? "light" : "dark";
    applyTheme(next);
    setDark(!dark);
  };
  useEffect(() => {
    applyTheme(getThemePref());
  }, []);

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[260px_1fr]">
      <a href="#main" onClick={(e) => { e.preventDefault(); document.getElementById("main")?.focus(); }} className="skip-link rounded-lg bg-brand px-3 py-2 text-on-brand">{t("nav.skip")}</a>
      <aside className="hidden lg:flex flex-col gap-6 border-e border-line bg-surface p-4 sticky top-0 h-screen overflow-y-auto">
        <Brand />
        <SideNav />
        <p className="mt-auto text-xs text-muted">{t("app.disclaimer")}</p>
      </aside>

      {open && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label={t("nav.main")}>
          <div className="absolute inset-0 bg-black/40" onClick={() => setOpen(false)} />
          <div className="absolute inset-y-0 start-0 flex w-72 flex-col gap-6 bg-surface p-4 overflow-y-auto">
            <div className="flex items-center justify-between">
              <Brand />
              <button onClick={() => setOpen(false)} aria-label={t("common.close")} className="p-1"><X className="size-5" aria-hidden /></button>
            </div>
            <SideNav onNavigate={() => setOpen(false)} />
          </div>
        </div>
      )}

      <div className="min-w-0 flex flex-col">
        <header className="sticky top-0 z-30 flex items-center gap-2 border-b border-line bg-surface/90 backdrop-blur px-4 py-2.5">
          <button className="lg:hidden p-1.5 rounded-md hover:bg-surface-2" onClick={() => setOpen(true)} aria-label={t("nav.menu")}>
            <Menu className="size-5" aria-hidden />
          </button>
          <div className="lg:hidden"><Brand /></div>
          <div className="flex-1" />
          <button onClick={switchLang} className="rounded-md px-2 py-1 text-sm font-medium hover:bg-surface-2"
            lang={lang === "en" ? "he" : "en"} data-testid="lang-toggle">
            {t("nav.language")}
          </button>
          <button onClick={toggleTheme} className="rounded-md p-1.5 hover:bg-surface-2" aria-label={t("nav.theme")} aria-pressed={dark}>
            {dark ? <Sun className="size-5" aria-hidden /> : <Moon className="size-5" aria-hidden />}
          </button>
          <div className="hidden sm:flex flex-col items-end leading-tight px-2">
            <span className="text-sm font-medium" data-testid="current-user">{me.full_name}</span>
            <span className="text-xs text-muted">{tx("role", me.role)}{me.professional ? ` · ${me.professional.specialty}` : ""}</span>
          </div>
          {/* Leave the protected route before clearing the user, so RequireAuth cannot record it as the next sign-in's "from". */}
          <button onClick={async () => { nav("/login", { replace: true }); await logout(); }} className="rounded-md p-1.5 hover:bg-surface-2" aria-label={t("nav.signOut")} title={t("nav.signOut")}>
            <LogOut className="size-5 rtl:-scale-x-100" aria-hidden />
          </button>
        </header>
        <main id="main" tabIndex={-1} className="flex-1 px-4 py-6 sm:px-6 lg:px-8 max-w-[1400px] w-full mx-auto focus:outline-none">
          <ErrorBoundary resetKey={loc.pathname}><Outlet /></ErrorBoundary>
        </main>
        <footer className="border-t border-line px-4 py-3 sm:px-6 lg:px-8 text-xs text-muted" data-testid="app-credit">{t("app.credit")}</footer>
      </div>
    </div>
  );
}
