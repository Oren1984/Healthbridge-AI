/** Localized rendering of care-gap findings from rule_id + params (server text is English). */
import type { Gap } from "./types";

type Tx = (prefix: string, value: string | null | undefined) => string;

const KIND_HE: Record<string, string> = {
  referral: "תוצאת הפניה", lab_test: "מעקב מעבדה", imaging: "מעקב הדמיה", follow_up_visit: "ביקור מעקב", other: "המלצה",
};
const DESC_HE: Record<string, string> = {
  completed_verified: "קיים תיעוד תומך להשלמה.",
  open: "משימת מעקב מתועדת כממתינה.",
  unknown: "הרשומות הזמינות אינן מראות אם זה בוצע. אין פירוש הדבר שלא בוצע.",
  requires_clarification: "המידע סותר או חסר ולכן לא ניתן להסיק מסקנה אמינה.",
  not_applicable: "סומן כלא דורש מעקב על ידי משתמש מורשה.",
};
const RULE_HE: Record<string, string> = {
  "CG-001": "מעקב או הדמיה שהומלצו ללא תיעוד השלמה",
  "CG-002": "הפניה ללא תוצאה מתועדת",
  "CG-003": "המלצה לבדיקת מעבדה ללא תוצאה זמינה",
  "CG-004": "התייעצות שהושלמה ללא סיכום מאושר",
  "CG-005": "העברה ששותפה ולא אושרה על ידי איש המקצוע המקבל",
  "CG-006": "תאריכים סותרים בין אירוע למסמך שלו",
  "CG-007": "המלצות סותרות בין מסמכים",
  "CG-008": "מסמך צפוי לא התקבל",
  "CG-009": "מידע שאינו זמין למשתתף בהתייעצות",
};
const LABEL_HE: Record<string, string> = {
  "imaging report": "פענוח הדמיה", "laboratory result": "תוצאת מעבדה", "discharge summary": "מכתב שחרור",
  "consultation letter": "מכתב ייעוץ", "consultation summary": "סיכום התייעצות",
};

/** Placeholder for gap details whose source was not shared with the viewer (server sets params.redacted). */
const REDACTED_HE = "הפרטים מגיעים ממידע שלא שותף איתך.";
const SHARING_ITEM_HE = "פריט שיתוף מידע";
const isSharingItem = (g: Gap) => g.rule_id === "CG-005" || g.rule_id === "CG-009";

export function gapTitle(g: Gap, lang: string, tx: Tx): string {
  if (lang === "he" && g.params?.redacted) {
    if (isSharingItem(g)) return SHARING_ITEM_HE;
    const prefix = { "CG-004": "סיכום התייעצות טרם אושר", "CG-006": "אי-התאמה בתאריכים", "CG-008": "מסמך צפוי לא התקבל" }[g.rule_id]
      ?? KIND_HE[g.params.kind] ?? "המלצה";
    return `${prefix}: ${REDACTED_HE}`;
  }
  if (lang !== "he") {
    if (g.rule_id === "CG-007") return `Different timeframes documented for: ${(g.params?.targets ?? []).map((x: string) => tx("term", x)).join(", ")}`;
    return g.title;
  }
  const p = g.params ?? {};
  switch (g.rule_id) {
    case "CG-001": case "CG-002": case "CG-003":
      return `${KIND_HE[p.kind] ?? "המלצה"}: ${p.text ?? ""}`;
    case "CG-004": return `סיכום התייעצות טרם אושר: ${p.title}`;
    case "CG-005": return `העברה ל${p.to} טרם אושרה`;
    case "CG-006": return `אי-התאמה בתאריכים: ${p.title}`;
    case "CG-007": return `מסגרות זמן שונות עבור: ${(p.targets ?? []).map((x: string) => tx("term", x)).join(", ")}`;
    case "CG-008": return `${LABEL_HE[p.label] ?? p.label} צפוי לא התקבל: ${p.title}`;
    case "CG-009": return `${p.professional} אינו/ה רואה ${p.count} מסמכים רלוונטיים`;
    default: return g.title;
  }
}

export function gapDescription(g: Gap, lang: string): string {
  if (lang !== "he") return g.description;
  if (g.params?.redacted && isSharingItem(g)) return REDACTED_HE;
  if (g.rule_id === "CG-009") return `להתייעצות "${g.params.title}" יש מסמכים ב-HealthBridge שלא שותפו עם ${g.params.professional}. ייתכן שהמידע הגיע אליו/ה ממקור אחר.`;
  if (g.rule_id === "CG-007") return "שני מסמכים מתארים את אותו מעקב עם מסגרות זמן שונות. HealthBridge אינה מכריעה מי מהן נכונה.";
  if (g.rule_id === "CG-006") return "תאריך האירוע במסע והתאריך הכתוב במסמך שונים ביותר מיומיים, או שהמסמך מתוארך לעתיד.";
  if (g.rule_id === "CG-008") return "לאירוע זה אין מסמך מקושר מהסוג הצפוי ב-HealthBridge. ייתכן שהוא קיים אצל הספק.";
  return DESC_HE[g.computed_status] ?? g.description;
}

export function gapRule(g: Gap, lang: string): string {
  return lang === "he" ? RULE_HE[g.rule_id] ?? g.rule : g.rule;
}

export function gapSuggestion(g: Gap, lang: string): string | null {
  if (!g.suggested_clarification || lang !== "he") return g.suggested_clarification;
  const p = g.params ?? {};
  switch (g.rule_id) {
    case "CG-001": case "CG-002": case "CG-003":
      return `לברר עם המרפאה או הספק האם "${p.text}" בוצע, ולבקש את המסמך המתאים כדי להוסיפו לרשומות.`;
    case "CG-004": return "לבקש מאנשי המקצוע המשתתפים להשלים ולאשר את סיכום ההתייעצות.";
    case "CG-005": return `לוודא עם ${p.to} שהסיכום התקבל ונבדק.`;
    case "CG-006": return "לבדוק איזה תאריך נכון ולתקן את האירוע או את פרטי המסמך.";
    case "CG-007": return "לשאול את איש המקצוע המטפל איזו מסגרת זמן חלה.";
    case "CG-008": return `לבקש את ה${LABEL_HE[p.label] ?? p.label} מהספק ולהעלות אותו.`;
    case "CG-009": return `להחליט אם לשתף מסמכים אלה עם ${p.professional} לפני ההתייעצות (מרכז השיתוף).`;
    default: return g.suggested_clarification;
  }
}

export function missingText(m: string, lang: string, tx: Tx): string {
  const lab = m.match(/^Laboratory result for: (.+)$/);
  if (lab) {
    const terms = lab[1].split(", ").map((x) => tx("term", x)).join(", ");
    return lang === "he" ? `תוצאת מעבדה עבור: ${terms}` : `Laboratory result for: ${terms}`;
  }
  if (lang !== "he") return m;
  const map: [RegExp, string][] = [
    [/^A laboratory result dated after/, "תוצאת מעבדה מתאריך מאוחר להמלצה"],
    [/^An imaging report dated after/, "פענוח הדמיה מתאריך מאוחר להמלצה"],
    [/^Documentation of a follow-up visit/, "תיעוד ביקור מעקב לאחר ההמלצה"],
    [/^A consultation letter or summary documenting/, "מכתב או סיכום ייעוץ המתעד את תוצאת ההפניה"],
    [/^A document confirming completion/, "מסמך המאשר את ההשלמה (פענוח, תוצאה או מכתב)"],
    [/^A summary approved by/, "סיכום מאושר על ידי אנשי המקצוע המשתתפים"],
    [/^Acknowledgment from/, "אישור קבלה מאיש המקצוע המקבל"],
    [/^Confirmation of the correct/, "אישור התאריך הנכון"],
    [/^Clarification from the treating/, "הבהרה מאיש המקצוע המטפל איזו הנחיה חלה"],
    [/^An? (.+) for this event$/, "מסמך מתאים לאירוע זה"],
    [/^Patient decision on sharing/, "החלטת המטופל לגבי שיתוף"],
  ];
  for (const [rx, he] of map) if (rx.test(m)) return he;
  return m;
}
