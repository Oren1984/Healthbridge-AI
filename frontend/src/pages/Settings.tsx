import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { Button, Card, ErrorState, Field, Input, Notice, PageHeader, Select, StatusBadge } from "../components/ui";
import { api } from "../lib/api";
import { useAuth, useMe } from "../lib/auth";
import { useI18n } from "../lib/i18n";
import { applyTheme, getThemePref, type ThemePref } from "../lib/theme";
import type { Me } from "../lib/types";

const ZONES = ["Asia/Jerusalem", "Europe/London", "America/New_York", "America/Chicago", "America/Los_Angeles", "Europe/Paris", "UTC"];

export default function Settings() {
  const me = useMe();
  const { setUser } = useAuth();
  const { t, setLang } = useI18n();
  const [name, setName] = useState(me.full_name);
  const [locale, setLocale] = useState(me.locale);
  const [tz, setTz] = useState(me.timezone);
  const [theme, setTheme] = useState<ThemePref>(getThemePref());
  const [pw, setPw] = useState({ current_password: "", new_password: "" });
  const save = useMutation({
    mutationFn: () => api.patch<{ user: Me }>("/auth/me", { full_name: name, locale, timezone: tz }),
    onSuccess: (r) => { setUser(r.user); setLang(r.user.locale); },
  });
  const changePw = useMutation({ mutationFn: () => api.post("/auth/change-password", pw), onSuccess: () => setPw({ current_password: "", new_password: "" }) });
  const zones = ZONES.includes(me.timezone) ? ZONES : [me.timezone, ...ZONES];

  return (
    <>
      <PageHeader title={t("settings.title")} help="language-and-accessibility" />
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2 max-w-5xl">
        <Card title={t("settings.profile")}>
          <form className="flex flex-col gap-4" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
            <Field label={t("auth.email")}>{(id) => <Input id={id} value={me.email} disabled />}</Field>
            <Field label={t("settings.name")}>{(id) => <Input id={id} value={name} onChange={(e) => setName(e.target.value)} />}</Field>
            <Field label={t("settings.language")}>{(id) => <Select id={id} value={locale} onChange={(e) => setLocale(e.target.value as "en" | "he")}><option value="en">English</option><option value="he">עברית</option></Select>}</Field>
            <Field label={t("settings.timezone")}>{(id) => <Select id={id} value={tz} onChange={(e) => setTz(e.target.value)}>{zones.map((z) => <option key={z}>{z}</option>)}</Select>}</Field>
            <Button type="submit" loading={save.isPending} className="self-start">{t("common.save")}</Button>
            {save.isSuccess && <Notice tone="ok">{t("settings.saved")}</Notice>}
            {save.error && <ErrorState error={save.error} />}
          </form>
        </Card>
        <div className="flex flex-col gap-6">
          <Card title={t("settings.theme")}>
            <div role="radiogroup" aria-label={t("settings.theme")} className="flex gap-2">
              {(["light", "dark", "system"] as ThemePref[]).map((p) => (
                <Button key={p} role="radio" aria-checked={theme === p} variant={theme === p ? "primary" : "secondary"} size="sm" onClick={() => { setTheme(p); applyTheme(p); }}>{t(`settings.${p}` as never)}</Button>
              ))}
            </div>
          </Card>
          <Card title={t("settings.password")}>
            <form className="flex flex-col gap-4" onSubmit={(e) => { e.preventDefault(); changePw.mutate(); }}>
              <Field label={t("settings.current")}>{(id) => <Input id={id} type="password" autoComplete="current-password" value={pw.current_password} onChange={(e) => setPw({ ...pw, current_password: e.target.value })} />}</Field>
              <Field label={t("settings.new")} hint="≥10 characters, 3 of: lower, upper, digit, symbol">{(id, d) => <Input id={id} aria-describedby={d} type="password" autoComplete="new-password" value={pw.new_password} onChange={(e) => setPw({ ...pw, new_password: e.target.value })} />}</Field>
              <Button type="submit" variant="secondary" className="self-start" loading={changePw.isPending} disabled={!pw.current_password || !pw.new_password}>{t("settings.password")}</Button>
              {changePw.isSuccess && <Notice tone="ok">{t("settings.saved")}</Notice>}
              {changePw.error && <ErrorState error={changePw.error} />}
            </form>
          </Card>
          {me.professional && (
            <Card title={t("settings.verification")}>
              <div className="flex items-center gap-2 text-sm"><StatusBadge status={me.professional.verification_status} /> <span className="text-muted">{me.professional.license_number}</span></div>
              <p className="mt-2 text-sm text-muted">{t("settings.verificationNote")}</p>
            </Card>
          )}
        </div>
      </div>
    </>
  );
}
