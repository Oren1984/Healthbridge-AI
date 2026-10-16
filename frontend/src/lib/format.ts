import { useI18n } from "./i18n";

export function useFormat() {
  const { lang } = useI18n();
  const locale = lang === "he" ? "he-IL" : "en-GB";
  return {
    date: (iso: string | null | undefined, tz?: string) =>
      iso ? new Intl.DateTimeFormat(locale, { dateStyle: "medium", ...(tz ? { timeZone: tz } : {}) }).format(new Date(iso.length === 10 ? `${iso}T12:00:00Z` : iso)) : "—",
    // dateStyle/timeStyle cannot be combined with timeZoneName, so explicit fields are used with a zone.
    dateTime: (iso: string | null | undefined, tz?: string) =>
      iso ? new Intl.DateTimeFormat(locale, tz
        ? { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", timeZone: tz, timeZoneName: "short" }
        : { dateStyle: "medium", timeStyle: "short" }).format(new Date(iso)) : "—",
    time: (iso: string, tz?: string) =>
      new Intl.DateTimeFormat(locale, { hour: "2-digit", minute: "2-digit", ...(tz ? { timeZone: tz, timeZoneName: "short" } : {}) }).format(new Date(iso)),
    relative: (iso: string) => {
      const diff = (new Date(iso).getTime() - Date.now()) / 1000;
      const rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
      const abs = Math.abs(diff);
      if (abs < 60) return rtf.format(Math.round(diff), "second");
      if (abs < 3600) return rtf.format(Math.round(diff / 60), "minute");
      if (abs < 86400) return rtf.format(Math.round(diff / 3600), "hour");
      return rtf.format(Math.round(diff / 86400), "day");
    },
    bytes: (n: number) => (n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(1)} KB` : `${(n / 1048576).toFixed(1)} MB`),
  };
}

export function toLocalInput(d: Date) {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
