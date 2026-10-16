import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router";
import { homeFor } from "../lib/nav";
import { Button, ErrorState, Field, Input } from "../components/ui";
import { useAuth } from "../lib/auth";
import { useI18n } from "../lib/i18n";
import { PublicShell } from "./PublicShell";

export default function Login() {
  const { t } = useI18n();
  const { login } = useAuth();
  const nav = useNavigate();
  const loc = useLocation() as { state?: { from?: string; email?: string; password?: string } };
  const [email, setEmail] = useState(loc.state?.email ?? "");
  const [password, setPassword] = useState(loc.state?.password ?? "");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const u = await login(email.trim(), password);
      nav(loc.state?.from ?? homeFor(u.role), { replace: true });
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <PublicShell>
      <div className="mx-auto max-w-md px-4 py-12">
        <div className="card p-6">
          <h1 className="text-xl font-semibold">{t("auth.title")}</h1>
          <form onSubmit={submit} className="mt-6 flex flex-col gap-4" noValidate>
            <Field label={t("auth.email")} required>
              {(id) => <Input id={id} type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required />}
            </Field>
            <Field label={t("auth.password")} required>
              {(id) => <Input id={id} type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />}
            </Field>
            {error ? <ErrorState error={error} /> : null}
            <Button type="submit" loading={busy}>{t("auth.submit")}</Button>
          </form>
          <p className="mt-5 text-sm text-muted">
            {t("auth.demoHint")} <Link to="/demo" className="text-brand underline">{t("landing.demo")}</Link>
          </p>
        </div>
      </div>
    </PublicShell>
  );
}
