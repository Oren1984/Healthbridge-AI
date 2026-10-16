import { BookOpen, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router";
import { Badge, ButtonLink, Card, EmptyState, Input, PageHeader } from "../components/ui";
import { ARTICLES, CATEGORIES, articleFor } from "../help/articles";
import { useMe } from "../lib/auth";
import { useI18n } from "../lib/i18n";
import NotFound from "./NotFound";

export default function Help() {
  const { slug } = useParams();
  const { t, lang } = useI18n();
  const me = useMe();
  const [q, setQ] = useState("");
  const L = lang === "he" ? "he" : "en";

  const results = useMemo(() => {
    // Every word must match; long words match by stem so "revoke" finds "revoking".
    const words = q.trim().toLowerCase().split(/\s+/).filter(Boolean).map((w) => (w.length > 4 ? w.slice(0, w.length - 1) : w));
    const visible = ARTICLES.filter((a) => a.audience.includes(me.role));
    if (!words.length) return visible;
    return visible.filter((a) => {
      const c = a[L];
      const hay = [c.title, c.summary, ...c.body.flatMap((b) => [b.h ?? "", b.p ?? "", ...(b.list ?? [])])].join(" ").toLowerCase();
      return words.every((w) => hay.includes(w));
    });
  }, [q, me.role, L]);

  if (slug) {
    const a = articleFor(slug);
    if (!a) return <NotFound />;
    const c = a[L];
    return (
      <div className="max-w-3xl">
        <nav aria-label="breadcrumb" className="mb-3 text-sm text-muted"><Link to="/app/help" className="hover:underline">{t("help.title")}</Link> / {CATEGORIES[a.category][L]}</nav>
        <article className="card p-6" data-testid="help-article">
          <h1 className="text-2xl font-semibold">{c.title}</h1>
          <p className="mt-1 text-muted">{c.summary}</p>
          <div className="mt-6 flex flex-col gap-4 leading-relaxed">
            {c.body.map((b, i) => (
              <section key={i}>
                {b.h && <h2 className="text-lg font-semibold mb-1">{b.h}</h2>}
                {b.p && <p>{b.p}</p>}
                {b.list && <ul className="list-disc ps-5 flex flex-col gap-1">{b.list.map((x) => <li key={x}>{x}</li>)}</ul>}
              </section>
            ))}
          </div>
        </article>
        {a.related.length > 0 && (
          <Card className="mt-6" title={t("help.related")}>
            <ul className="flex flex-col gap-2">
              {a.related.map((r) => { const ra = articleFor(r); return ra ? <li key={r}><Link className="text-brand hover:underline" to={`/app/help/${r}`}>{ra[L].title}</Link></li> : null; })}
            </ul>
          </Card>
        )}
        <div className="mt-6"><ButtonLink to="/app/help">{t("help.allArticles")}</ButtonLink></div>
      </div>
    );
  }

  const byCat = Object.keys(CATEGORIES).map((cat) => ({ cat: cat as keyof typeof CATEGORIES, items: results.filter((a) => a.category === cat) })).filter((g) => g.items.length);
  return (
    <>
      <PageHeader title={t("help.title")} subtitle={t("help.subtitle")} />
      <div className="relative max-w-xl mb-6">
        <Search className="absolute start-3 top-1/2 -translate-y-1/2 size-4 text-muted" aria-hidden />
        <Input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("help.search")} aria-label={t("help.search")} className="ps-9" data-testid="help-search" />
      </div>
      {results.length === 0 && <EmptyState title={t("help.noResults")} />}
      <div className="flex flex-col gap-8">
        {byCat.map((g) => (
          <section key={g.cat}>
            <h2 className="mb-3 text-lg font-semibold">{CATEGORIES[g.cat][L]}</h2>
            <ul className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
              {g.items.map((a) => (
                <li key={a.slug}>
                  <Link to={`/app/help/${a.slug}`} className="card flex h-full gap-3 p-4 hover:border-brand" data-testid="help-link">
                    <BookOpen className="size-5 text-brand shrink-0 mt-0.5" aria-hidden />
                    <div><p className="font-medium">{a[L].title}</p><p className="text-sm text-muted mt-0.5">{a[L].summary}</p>
                      {a.context.length > 0 && <Badge className="mt-2" tone="brand">{t("help.contextual")}</Badge>}</div>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </>
  );
}
