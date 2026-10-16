export type ThemePref = "light" | "dark" | "system";

export function getThemePref(): ThemePref {
  try {
    const v = localStorage.getItem("hb.theme");
    if (v === "light" || v === "dark" || v === "system") return v;
  } catch {
    /* ignore */
  }
  return "system";
}

export function applyTheme(pref: ThemePref) {
  const dark = pref === "dark" || (pref === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  try {
    localStorage.setItem("hb.theme", pref);
  } catch {
    /* ignore */
  }
}
