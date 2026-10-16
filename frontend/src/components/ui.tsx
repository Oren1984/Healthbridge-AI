/** Small, accessible component set shared by every screen. */
import clsx from "clsx";
import { AlertCircle, CheckCircle2, CircleDashed, CircleHelp, HelpCircle, Inbox, Loader2, XCircle } from "lucide-react";
import {
  forwardRef, useEffect, useId, useRef, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode,
  type SelectHTMLAttributes, type TextareaHTMLAttributes,
} from "react";
import { Link } from "react-router";
import { useI18n } from "../lib/i18n";
import type { TKey } from "../i18n/en";

type Variant = "primary" | "secondary" | "ghost" | "danger";
const variants: Record<Variant, string> = {
  primary: "bg-brand text-on-brand hover:bg-brand-hover",
  secondary: "bg-surface text-ink border border-line hover:bg-surface-2",
  ghost: "text-ink hover:bg-surface-2",
  danger: "bg-danger text-white hover:opacity-90",
};

export const Button = forwardRef<HTMLButtonElement, ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant; size?: "sm" | "md"; loading?: boolean; icon?: ReactNode;
}>(function Button({ variant = "primary", size = "md", loading, icon, className, children, disabled, ...rest }, ref) {
  return (
    <button ref={ref} disabled={disabled || loading} {...rest}
      className={clsx("inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed",
        size === "sm" ? "px-2.5 py-1.5 text-sm" : "px-4 py-2 text-sm", variants[variant], className)}>
      {loading ? <Loader2 className="size-4 animate-spin" aria-hidden /> : icon}
      {children}
    </button>
  );
});

export function ButtonLink({ to, children, variant = "secondary", className, icon }: { to: string; children: ReactNode; variant?: Variant; className?: string; icon?: ReactNode }) {
  return (
    <Link to={to} className={clsx("inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors", variants[variant], className)}>
      {icon}{children}
    </Link>
  );
}

export function Card({ children, className, title, action, id }: { children: ReactNode; className?: string; title?: ReactNode; action?: ReactNode; id?: string }) {
  const hid = useId();
  return (
    <section className={clsx("card p-5", className)} aria-labelledby={title ? hid : undefined} id={id}>
      {(title || action) && (
        <div className="mb-4 flex items-center justify-between gap-3">
          {title && <h2 id={hid} className="text-base font-semibold">{title}</h2>}
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

const tone: Record<string, string> = {
  ok: "bg-ok-soft text-ok", warn: "bg-warn-soft text-warn", danger: "bg-danger-soft text-danger",
  info: "bg-info-soft text-info", neutral: "bg-neutral-soft text-neutral", violet: "bg-violet-soft text-violet",
  brand: "bg-brand-soft text-brand",
};
export type Tone = keyof typeof tone;

export function Badge({ children, tone: t = "neutral", className, icon }: { children: ReactNode; tone?: Tone; className?: string; icon?: ReactNode }) {
  return <span className={clsx("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap", tone[t], className)}>{icon}{children}</span>;
}

const statusTone: Record<string, Tone> = {
  completed_verified: "ok", processed: "ok", approved: "ok", active: "ok", confirmed: "ok", documented: "ok",
  professional_confirmed: "ok", accepted: "ok", shared: "ok", completed: "ok", simulated_verified: "ok", corrected: "ok",
  open: "info", scheduled: "info", in_progress: "info", pending: "info", processing: "info", invited: "info",
  unknown: "warn", needs_review: "warn", pending_review: "warn", pending_approval: "warn", completed_reported: "warn",
  patient_reported: "warn", unverified: "warn", pending_patient_approval: "warn", changes_requested: "warn",
  requires_clarification: "violet",
  failed: "danger", rejected: "danger", revoked: "danger", declined: "danger", cancelled: "neutral",
  not_applicable: "neutral", expired: "neutral", superseded: "neutral", draft: "neutral", unsupported: "danger",
};
const statusIcon: Record<string, ReactNode> = {
  ok: <CheckCircle2 className="size-3.5" aria-hidden />, warn: <CircleHelp className="size-3.5" aria-hidden />,
  violet: <AlertCircle className="size-3.5" aria-hidden />, danger: <XCircle className="size-3.5" aria-hidden />,
  info: <CircleDashed className="size-3.5" aria-hidden />,
};

/** Status is always conveyed by text + icon, never by colour alone. */
export function StatusBadge({ status }: { status: string }) {
  const { tx } = useI18n();
  const t = statusTone[status] ?? "neutral";
  return <Badge tone={t} icon={statusIcon[t]}>{tx("status", status)}</Badge>;
}

export function Spinner({ label }: { label?: string }) {
  const { t } = useI18n();
  return (
    <div role="status" className="flex items-center gap-2 py-8 justify-center text-muted">
      <Loader2 className="size-5 animate-spin" aria-hidden /> <span>{label ?? t("common.loading")}</span>
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const { t } = useI18n();
  return (
    <div role="alert" className="rounded-xl border border-danger/30 bg-danger-soft p-4 text-danger flex items-start gap-3">
      <AlertCircle className="size-5 shrink-0 mt-0.5" aria-hidden />
      <div className="flex-1">
        <p className="font-medium">{t("common.error")}</p>
        <p className="text-sm">{error instanceof Error ? error.message : String(error)}</p>
      </div>
      {onRetry && <Button size="sm" variant="secondary" onClick={onRetry}>{t("common.retry")}</Button>}
    </div>
  );
}

export function EmptyState({ title, body, action, icon }: { title: string; body?: string; action?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center text-center gap-2 py-10 px-4">
      <div className="text-muted">{icon ?? <Inbox className="size-8" aria-hidden />}</div>
      <p className="font-medium">{title}</p>
      {body && <p className="text-sm text-muted max-w-md">{body}</p>}
      {action}
    </div>
  );
}

export function PageHeader({ title, subtitle, actions, help }: { title: string; subtitle?: string; actions?: ReactNode; help?: string }) {
  const { t } = useI18n();
  return (
    <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
          {help && (
            <Link to={`/app/help/${help}`} className="text-muted hover:text-brand" aria-label={`${t("help.contextual")}: ${title}`} title={t("help.contextual")}>
              <HelpCircle className="size-5" aria-hidden />
            </Link>
          )}
        </div>
        {subtitle && <p className="mt-1 text-sm text-muted max-w-3xl">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </header>
  );
}

const fieldBase = "w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink placeholder:text-muted disabled:opacity-60";

export function Field({ label, hint, children, id, required }: { label: string; hint?: string; children: (id: string, describedBy?: string) => ReactNode; id?: string; required?: boolean }) {
  const auto = useId();
  const fid = id ?? auto;
  const hid = hint ? `${fid}-hint` : undefined;
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={fid} className="text-sm font-medium">{label}{required && <span className="text-danger" aria-hidden> *</span>}</label>
      {children(fid, hid)}
      {hint && <p id={hid} className="text-xs text-muted">{hint}</p>}
    </div>
  );
}

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input({ className, ...p }, ref) {
  return <input ref={ref} {...p} className={clsx(fieldBase, className)} />;
});
export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(function Select({ className, ...p }, ref) {
  return <select ref={ref} {...p} className={clsx(fieldBase, className)} />;
});
export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(function Textarea({ className, ...p }, ref) {
  return <textarea ref={ref} {...p} className={clsx(fieldBase, "min-h-24", className)} />;
});

/** Native <dialog>: focus trapping, Esc to close and inert background come from the platform. */
export function Dialog({ open, onClose, title, children, footer, wide }: { open: boolean; onClose: () => void; title: string; children: ReactNode; footer?: ReactNode; wide?: boolean }) {
  const ref = useRef<HTMLDialogElement>(null);
  const hid = useId();
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);
  const { t } = useI18n();
  return (
    <dialog ref={ref} onClose={onClose} aria-labelledby={hid}
      className={clsx("card m-auto w-[calc(100%-2rem)] p-0 backdrop:backdrop-blur-sm", wide ? "max-w-3xl" : "max-w-lg")}>
      {open && (
        <div className="flex max-h-[85vh] flex-col">
          <div className="flex items-center justify-between border-b border-line px-5 py-4">
            <h2 id={hid} className="text-lg font-semibold">{title}</h2>
            <button onClick={onClose} className="rounded-md p-1 text-muted hover:bg-surface-2" aria-label={t("common.close")}>
              <XCircle className="size-5" aria-hidden />
            </button>
          </div>
          <div className="overflow-y-auto px-5 py-4">{children}</div>
          {footer && <div className="flex flex-wrap justify-end gap-2 border-t border-line px-5 py-3">{footer}</div>}
        </div>
      )}
    </dialog>
  );
}

export function Tabs({ tabs, value, onChange, label }: { tabs: { id: string; label: string; count?: number }[]; value: string; onChange: (id: string) => void; label: string }) {
  return (
    <div role="tablist" aria-label={label} className="flex gap-1 overflow-x-auto border-b border-line mb-4">
      {tabs.map((tb) => (
        <button key={tb.id} role="tab" aria-selected={value === tb.id} onClick={() => onChange(tb.id)}
          className={clsx("whitespace-nowrap px-3 py-2 text-sm font-medium border-b-2 -mb-px",
            value === tb.id ? "border-brand text-brand" : "border-transparent text-muted hover:text-ink")}>
          {tb.label}{tb.count !== undefined && <span className="ms-1.5 rounded-full bg-surface-2 px-1.5 text-xs">{tb.count}</span>}
        </button>
      ))}
    </div>
  );
}

export function Notice({ tone: t = "info", children, icon }: { tone?: Tone; children: ReactNode; icon?: ReactNode }) {
  return <div className={clsx("flex items-start gap-2 rounded-lg px-3 py-2 text-sm", tone[t])}>{icon ?? <AlertCircle className="size-4 mt-0.5 shrink-0" aria-hidden />}<div>{children}</div></div>;
}

export function KeyVal({ k, v }: { k: string; v: ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-xs text-muted">{k}</dt>
      <dd className="text-sm">{v ?? "—"}</dd>
    </div>
  );
}

export function TermChips({ terms }: { terms: string[] }) {
  const { tx } = useI18n();
  if (!terms.length) return null;
  return <span className="inline-flex flex-wrap gap-1">{terms.map((x) => <Badge key={x} tone="brand">{tx("term", x)}</Badge>)}</span>;
}

export function useT() {
  return useI18n().t as (k: TKey, p?: Record<string, string | number>) => string;
}
