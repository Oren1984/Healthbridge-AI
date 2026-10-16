import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import en, { type TKey } from "../i18n/en";
import he from "../i18n/he";

export type Lang = "en" | "he";
const dicts = { en, he };

interface I18n {
  lang: Lang;
  dir: "ltr" | "rtl";
  setLang: (l: Lang) => void;
  t: (key: TKey, params?: Record<string, string | number>) => string;
  /** Translate a dynamic key (status/category/etc.) with a readable fallback. */
  tx: (prefix: string, value: string | null | undefined) => string;
}

const Ctx = createContext<I18n | null>(null);

function initialLang(): Lang {
  try {
    const saved = localStorage.getItem("hb.lang");
    if (saved === "en" || saved === "he") return saved;
  } catch {
    /* storage unavailable */
  }
  return navigator.language?.startsWith("he") ? "he" : "en";
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(initialLang);
  const dir = lang === "he" ? "rtl" : "ltr";

  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = dir;
  }, [lang, dir]);

  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    try {
      localStorage.setItem("hb.lang", l);
    } catch {
      /* ignore */
    }
  }, []);

  const t = useCallback(
    (key: TKey, params?: Record<string, string | number>) => {
      let s: string = dicts[lang][key] ?? en[key] ?? key;
      if (params) for (const [k, v] of Object.entries(params)) s = s.split(`{${k}}`).join(String(v));
      return s;
    },
    [lang],
  );

  const tx = useCallback(
    (prefix: string, value: string | null | undefined) => {
      if (!value) return "—";
      const key = `${prefix}.${value}` as TKey;
      return (dicts[lang] as Record<string, string>)[key] ?? value.replace(/_/g, " ");
    },
    [lang],
  );

  const value = useMemo(() => ({ lang, dir, setLang, t, tx }) as I18n, [lang, dir, setLang, t, tx]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useI18n() {
  const c = useContext(Ctx);
  if (!c) throw new Error("I18nProvider missing");
  return c;
}
