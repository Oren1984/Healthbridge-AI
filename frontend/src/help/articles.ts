export type Block = { h?: string; p?: string; list?: string[] };
export interface Article {
  slug: string;
  category: "start" | "patients" | "professionals" | "privacy" | "ai" | "troubleshooting";
  audience: ("patient" | "professional" | "admin")[];
  context: string[]; // app paths where this article is contextual help
  related: string[];
  en: { title: string; summary: string; body: Block[] };
  he: { title: string; summary: string; body: Block[] };
}

export const CATEGORIES = {
  start: { en: "Getting started", he: "צעדים ראשונים" },
  patients: { en: "For patients", he: "למטופלים" },
  professionals: { en: "For professionals", he: "לאנשי מקצוע" },
  privacy: { en: "Privacy & sharing", he: "פרטיות ושיתוף" },
  ai: { en: "AI & care gaps", he: "בינה מלאכותית ופערים" },
  troubleshooting: { en: "Troubleshooting", he: "פתרון תקלות" },
} as const;

export const ARTICLES: Article[] = [
  {
    slug: "getting-started-patient", category: "start", audience: ["patient"], context: ["/app/dashboard"],
    related: ["uploading-documents", "medical-journey", "understanding-care-gaps"],
    en: {
      title: "Getting started as a patient",
      summary: "What HealthBridge does for you and the first three things to do.",
      body: [
        { p: "HealthBridge puts you at the centre of your healthcare information. It gathers documents from different organizations into one journey, shows which recommendations still need follow-up, and lets you decide exactly who can see what." },
        { h: "First steps", list: [
          "Upload a recent medical document on the Documents page (PDF, text or FHIR JSON).",
          "Review the recommendations HealthBridge extracted — confirm, correct or reject each one.",
          "Open Care gaps to see what is verified, open, unknown or needs clarification.",
        ] },
        { h: "Your dashboard", p: "The dashboard summarises items needing attention, upcoming consultations, active sharing permissions and recent access to your records. Every number links to the screen with the details." },
        { p: "This environment uses synthetic data only. Never upload real medical records." },
      ],
    },
    he: {
      title: "צעדים ראשונים כמטופל/ת",
      summary: "מה HealthBridge עושה עבורך ושלושת הדברים הראשונים לעשות.",
      body: [
        { p: "HealthBridge מציבה אותך במרכז המידע הרפואי שלך. היא מאחדת מסמכים מארגונים שונים למסע אחד, מראה אילו המלצות עדיין דורשות מעקב, ומאפשרת לך להחליט בדיוק מי רואה מה." },
        { h: "צעדים ראשונים", list: [
          "העלאת מסמך רפואי עדכני בעמוד המסמכים (PDF, טקסט או FHIR JSON).",
          "בדיקת ההמלצות שחולצו — אישור, תיקון או דחייה של כל אחת.",
          "מעבר לפערי רצף כדי לראות מה מאומת, פתוח, לא ידוע או דורש הבהרה.",
        ] },
        { h: "לוח הבקרה", p: "לוח הבקרה מסכם פריטים הדורשים תשומת לב, התייעצויות קרובות, הרשאות שיתוף פעילות וגישה אחרונה לרשומות שלך. כל מספר מוביל למסך הפרטים." },
        { p: "סביבה זו משתמשת בנתונים סינתטיים בלבד. אין להעלות רשומות רפואיות אמיתיות." },
      ],
    },
  },
  {
    slug: "getting-started-professional", category: "start", audience: ["professional"], context: ["/app/pro"],
    related: ["video-consultations", "consultation-summaries", "professional-verification"],
    en: {
      title: "Getting started as a healthcare professional",
      summary: "How patient-controlled access works from the professional side.",
      body: [
        { p: "In HealthBridge the patient decides what you can see. Your workspace lists only patients who have shared information with you, and only the specific documents, categories or sections they selected." },
        { h: "What you can do", list: [
          "Review documents a patient shared with you, until the permission ends.",
          "Join consultations you are invited to and add consultation notes.",
          "Write, revise and approve consultation summaries, and propose follow-up actions.",
          "Acknowledge summaries handed off to you.",
        ] },
        { h: "What you cannot do", p: "Being invited to a consultation does not give you access to the patient's records. If something is marked “Not shared with you”, ask the patient — they can share it from the consultation page or the Sharing Center." },
      ],
    },
    he: {
      title: "צעדים ראשונים לאנשי מקצוע",
      summary: "כיצד פועלת גישה בשליטת המטופל מצד איש המקצוע.",
      body: [
        { p: "ב-HealthBridge המטופל מחליט מה תוכל/י לראות. סביבת העבודה מציגה רק מטופלים ששיתפו איתך מידע, ורק את המסמכים, הקטגוריות או האזורים שבחרו." },
        { h: "מה אפשר לעשות", list: [
          "לעיין במסמכים שמטופל שיתף איתך, עד שההרשאה מסתיימת.",
          "להצטרף להתייעצויות שהוזמנת אליהן ולהוסיף הערות.",
          "לכתוב, לעדכן ולאשר סיכומי התייעצות ולהציע פעולות מעקב.",
          "לאשר קבלה של סיכומים שהועברו אליך.",
        ] },
        { h: "מה אי אפשר לעשות", p: "הזמנה להתייעצות אינה מעניקה גישה לרשומות המטופל. אם פריט מסומן \"לא שותף איתך\", יש לבקש מהמטופל — הוא יכול לשתף מעמוד ההתייעצות או ממרכז השיתוף." },
      ],
    },
  },
  {
    slug: "uploading-documents", category: "patients", audience: ["patient"], context: ["/app/documents"],
    related: ["troubleshooting-documents", "fhir-import-export", "medical-journey"],
    en: {
      title: "Uploading and reviewing documents",
      summary: "Supported formats, what happens after upload, and how to correct extracted details.",
      body: [
        { h: "Supported files", list: ["PDF with selectable text", "Plain text (.txt, .md), including Hebrew", "FHIR R4 JSON resources or Bundles (see the FHIR article)"] },
        { p: "Files up to 10 MB are accepted. Files are checked for type, signature and active content (for example scripts inside PDFs) and rejected if unsafe. Uploaded content is never executed." },
        { h: "After upload", p: "Processing runs in the background: text is extracted, the date, organization and author are detected, recommendations are identified, the document is indexed for search, and an event is added to your journey. You'll get a notification when it finishes." },
        { h: "Review and correct", p: "Each extracted recommendation shows the exact passage it came from. Confirm it, correct the wording, or reject it if it was misread. You can also correct the document's title, date, category or organization. The original file is never changed." },
        { h: "Versions and duplicates", p: "Upload a corrected file as a new version to keep the history. Uploading the exact same file twice is blocked; documents with identical text are flagged." },
      ],
    },
    he: {
      title: "העלאה ובדיקה של מסמכים",
      summary: "פורמטים נתמכים, מה קורה אחרי ההעלאה וכיצד לתקן פרטים שחולצו.",
      body: [
        { h: "קבצים נתמכים", list: ["PDF עם טקסט שניתן לבחירה", "טקסט פשוט (‎.txt, .md), כולל עברית", "משאבי FHIR R4 JSON או Bundle (ראו מאמר FHIR)"] },
        { p: "מתקבלים קבצים עד 10MB. הקבצים נבדקים לסוג, חתימה ותוכן פעיל (למשל סקריפטים בתוך PDF) ונדחים אם אינם בטוחים. תוכן שהועלה לעולם אינו מורץ." },
        { h: "אחרי ההעלאה", p: "העיבוד מתבצע ברקע: חילוץ טקסט, זיהוי תאריך, ארגון ומחבר, זיהוי המלצות, אינדוקס לחיפוש והוספת אירוע למסע. תתקבל התראה בסיום." },
        { h: "בדיקה ותיקון", p: "כל המלצה שחולצה מציגה את הקטע המדויק שממנו נלקחה. אפשר לאשר, לתקן את הנוסח או לדחות אם נקראה בטעות. ניתן גם לתקן כותרת, תאריך, קטגוריה או ארגון. הקובץ המקורי לעולם אינו משתנה." },
        { h: "גרסאות וכפילויות", p: "העלאת קובץ מתוקן כגרסה חדשה שומרת על ההיסטוריה. העלאה כפולה של אותו קובץ נחסמת; מסמכים עם טקסט זהה מסומנים." },
      ],
    },
  },
  {
    slug: "medical-journey", category: "patients", audience: ["patient", "professional"], context: ["/app/journey"],
    related: ["uploading-documents", "understanding-care-gaps"],
    en: {
      title: "Reading your medical journey",
      summary: "Event types, provenance and verification labels.",
      body: [
        { p: "The journey is a single timeline of healthcare events from every source — HMO visits, specialists, hospitals, laboratories, imaging and international consultations." },
        { h: "Verification labels", list: [
          "Documented — supported by a document in HealthBridge.",
          "Patient-reported — entered by you, without a supporting document yet.",
          "Professional-confirmed — confirmed by an approved consultation summary.",
          "Unverified — recorded, but its date or details are not supported by a document.",
        ] },
        { h: "Provenance", p: "Each event shows where it came from: a document, a manual entry, a FHIR import, or a HealthBridge consultation. Open an event to see related documents, linked recommendations and who can currently see it." },
      ],
    },
    he: {
      title: "קריאת המסע הרפואי",
      summary: "סוגי אירועים, מקור הרישום ותוויות אימות.",
      body: [
        { p: "המסע הוא ציר זמן אחד של אירועים רפואיים מכל המקורות — קופת חולים, מומחים, בתי חולים, מעבדות, הדמיה והתייעצויות בינלאומיות." },
        { h: "תוויות אימות", list: [
          "מתועד — נתמך במסמך ב-HealthBridge.",
          "דיווח מטופל — הוזן על ידך, עדיין ללא מסמך תומך.",
          "אושר ע\"י איש מקצוע — אושר בסיכום התייעצות מאושר.",
          "לא מאומת — נרשם, אך התאריך או הפרטים אינם נתמכים במסמך.",
        ] },
        { h: "מקור הרישום", p: "כל אירוע מציג מאין הגיע: ממסמך, הזנה ידנית, ייבוא FHIR או התייעצות ב-HealthBridge. פתיחת אירוע מציגה מסמכים קשורים, המלצות מקושרות ומי יכול לראות אותו כעת." },
      ],
    },
  },
  {
    slug: "understanding-care-gaps", category: "ai", audience: ["patient", "professional"], context: ["/app/care-gaps"],
    related: ["follow-ups", "ai-limitations", "medical-journey"],
    en: {
      title: "Understanding care gap findings",
      summary: "What each status means and why “unknown” never means “not done”.",
      body: [
        { p: "Care gap intelligence runs fixed, documented rules over your records. It is not an AI model and it does not assess urgency, diagnose, or recommend treatment." },
        { h: "Statuses", list: [
          "Completed & verified — supporting evidence exists (for example a later report or letter).",
          "Open — a follow-up is documented as pending.",
          "Unknown — the records don't show whether it happened. It may have happened elsewhere.",
          "Requires clarification — information conflicts or is insufficient (for example two different timeframes).",
          "Not applicable — an authorized user recorded why it doesn't need tracking.",
        ] },
        { h: "What you see for each finding", p: "The rule that triggered it, the supporting evidence, what evidence is missing, the relevant dates and a suggested administrative question you could ask. You can create a clarification item, flag it, or mark it not applicable with a reason." },
        { h: "Replay", p: "“Replay for a date” recomputes the findings as of an earlier date without changing anything — useful for understanding why a finding appeared." },
      ],
    },
    he: {
      title: "הבנת ממצאי פערי רצף",
      summary: "מה פירוש כל סטטוס ומדוע \"לא ידוע\" לעולם אינו \"לא בוצע\".",
      body: [
        { p: "זיהוי פערי הרצף מריץ כללים קבועים ומתועדים על הרשומות שלך. זה אינו מודל בינה מלאכותית, והוא אינו מעריך דחיפות, אינו מאבחן ואינו ממליץ על טיפול." },
        { h: "סטטוסים", list: [
          "הושלם ואומת — קיימת ראיה תומכת (למשל פענוח או מכתב מאוחר יותר).",
          "פתוח — מעקב מתועד כממתין.",
          "לא ידוע — הרשומות אינן מראות אם זה קרה. ייתכן שקרה במקום אחר.",
          "דורש הבהרה — המידע סותר או חסר (למשל שתי מסגרות זמן שונות).",
          "לא רלוונטי — משתמש מורשה תיעד מדוע אין צורך במעקב.",
        ] },
        { h: "מה מוצג לכל ממצא", p: "הכלל שהפעיל אותו, הראיות התומכות, הראיות החסרות, התאריכים הרלוונטיים ושאלה מנהלית מוצעת. אפשר ליצור פריט הבהרה, לסמן לבירור או לסמן כלא רלוונטי עם נימוק." },
        { h: "הרצה לתאריך", p: "\"הרצה לתאריך\" מחשבת את הממצאים נכון לתאריך קודם, ללא שינוי דבר — שימושי להבנת הסיבה להופעת ממצא." },
      ],
    },
  },
  {
    slug: "follow-ups", category: "patients", audience: ["patient"], context: ["/app/tasks"],
    related: ["understanding-care-gaps", "uploading-documents"],
    en: {
      title: "Tracking follow-ups",
      summary: "Creating, completing and verifying follow-up and clarification items.",
      body: [
        { p: "Turn any recommendation into a follow-up with “Track as follow-up”, or create a clarification item from a care gap. You can also add your own." },
        { h: "Due dates", p: "HealthBridge never invents deadlines. A due date appears only when it was explicitly written in a document or entered by you. Documented timeframes such as “within 6 weeks” are shown as written." },
        { h: "Completing", list: [
          "Mark complete without a document → recorded as “reported done — no evidence”. The related care gap stays unknown.",
          "Attach an evidence document (for example the test report) → the item becomes completed & verified.",
          "Nothing closes automatically, and an assistant suggestion can never close an item.",
        ] },
        { p: "Every change is recorded in the item's history. Reminders appear in Notifications according to your preferences." },
      ],
    },
    he: {
      title: "מעקב אחר משימות",
      summary: "יצירה, השלמה ואימות של פריטי מעקב והבהרה.",
      body: [
        { p: "כל המלצה ניתנת להפוך למעקב באמצעות \"מעקב כמשימה\", או ליצור פריט הבהרה מפער רצף. אפשר גם להוסיף פריטים משלך." },
        { h: "תאריכי יעד", p: "HealthBridge לעולם אינה ממציאה מועדים. תאריך יעד מופיע רק אם נכתב במפורש במסמך או הוזן על ידך. מסגרות זמן כמו \"תוך 6 שבועות\" מוצגות כפי שנכתבו." },
        { h: "השלמה", list: [
          "סימון כהושלם ללא מסמך ← נרשם כ\"דווח כבוצע — ללא ראיה\". הפער הקשור נשאר \"לא ידוע\".",
          "צירוף מסמך ראיה (למשל פענוח הבדיקה) ← הפריט הופך ל\"הושלם ואומת\".",
          "דבר אינו נסגר אוטומטית, והצעת העוזר לעולם אינה סוגרת פריט.",
        ] },
        { p: "כל שינוי נרשם בהיסטוריית הפריט. תזכורות מופיעות בהתראות בהתאם להעדפותיך." },
      ],
    },
  },
  {
    slug: "sharing-and-revocation", category: "privacy", audience: ["patient", "professional"], context: ["/app/sharing"],
    related: ["privacy-and-audit", "video-consultations"],
    en: {
      title: "Sharing information and revoking access",
      summary: "How consent grants work, what recipients see, and the limits of revocation.",
      body: [
        { h: "Creating a permission", list: [
          "Choose a verified professional.",
          "Select specific documents, whole categories (which also cover future uploads of that category), and optionally your journey or care gap findings.",
          "Choose how long access lasts (1–365 days).",
          "Review the exact list of what will be shared, then approve.",
        ] },
        { h: "Enforcement", p: "Every request a professional makes is checked on the server against active permissions — for listings, document views, downloads and assistant searches. Nothing is shared just because someone is in a consultation with you." },
        { h: "Revocation", p: "Revoking stops further access through HealthBridge immediately. It cannot recall information the professional already viewed or downloaded, and it does not override healthcare providers' legal duties to keep clinical records." },
        { h: "Handoffs", p: "A professional can ask to share a consultation summary with a colleague. Nothing is shared until you approve the request in the Sharing Center." },
      ],
    },
    he: {
      title: "שיתוף מידע וביטול גישה",
      summary: "כיצד פועלות הרשאות, מה רואים הנמענים ומה גבולות הביטול.",
      body: [
        { h: "יצירת הרשאה", list: [
          "בחירת איש מקצוע מאומת.",
          "בחירת מסמכים מסוימים, קטגוריות שלמות (הכוללות גם העלאות עתידיות מאותה קטגוריה) ובאופן אופציונלי את המסע או ממצאי פערי הרצף.",
          "בחירת משך הגישה (1–365 ימים).",
          "בדיקת הרשימה המדויקת של מה ישותף, ואז אישור.",
        ] },
        { h: "אכיפה", p: "כל בקשה של איש מקצוע נבדקת בשרת מול ההרשאות הפעילות — ברשימות, בצפייה, בהורדה ובחיפושי העוזר. דבר אינו משותף רק משום שמישהו נמצא איתך בהתייעצות." },
        { h: "ביטול", p: "ביטול מפסיק מיד גישה נוספת דרך HealthBridge. הוא אינו יכול להשיב מידע שאיש המקצוע כבר צפה בו או הוריד, ואינו גובר על חובות חוקיות של נותני שירותי בריאות לשמור רשומות." },
        { h: "העברות", p: "איש מקצוע יכול לבקש לשתף סיכום התייעצות עם עמית. דבר אינו משותף עד שתאשר/י את הבקשה במרכז השיתוף." },
      ],
    },
  },
  {
    slug: "video-consultations", category: "patients", audience: ["patient", "professional"], context: ["/app/consultations"],
    related: ["troubleshooting-video", "consultation-summaries", "sharing-and-revocation"],
    en: {
      title: "International video consultations",
      summary: "Scheduling, time zones, joining the room and sharing documents during a consultation.",
      body: [
        { h: "Scheduling", p: "Patients schedule consultations and invite one or more verified professionals. Each participant sees the time in their own time zone." },
        { h: "Joining", p: "The room opens two hours before the start time. Joining issues a short-lived, room-specific access token. You can turn your camera and microphone on or off, share your screen, and chat with participants." },
        { h: "Documents", p: "Documents on the agenda are visible to professionals only if you share them. Use “Share with participants” to grant every professional in the consultation time-limited access." },
        { h: "Privacy", p: "Consultations are not recorded or transcribed, and in-meeting chat is not stored. Video and audio travel over encrypted WebRTC to the self-hosted media server." },
        { h: "After the consultation", p: "A participant marks it completed; the professionals then write and approve the summary." },
      ],
    },
    he: {
      title: "התייעצויות וידאו בינלאומיות",
      summary: "קביעה, אזורי זמן, כניסה לחדר ושיתוף מסמכים במהלך התייעצות.",
      body: [
        { h: "קביעה", p: "מטופלים קובעים התייעצויות ומזמינים איש מקצוע מאומת אחד או יותר. כל משתתף רואה את השעה באזור הזמן שלו." },
        { h: "כניסה", p: "החדר נפתח שעתיים לפני שעת ההתחלה. הכניסה מנפיקה אסימון גישה קצר-מועד לחדר הספציפי. אפשר להפעיל ולכבות מצלמה ומיקרופון, לשתף מסך ולשוחח בצ'אט." },
        { h: "מסמכים", p: "מסמכים בסדר היום גלויים לאנשי מקצוע רק אם שיתפת אותם. \"שיתוף עם המשתתפים\" מעניק לכל אנשי המקצוע בהתייעצות גישה מוגבלת בזמן." },
        { h: "פרטיות", p: "ההתייעצויות אינן מוקלטות או מתומללות, והצ'אט אינו נשמר. הווידאו והשמע עוברים ב-WebRTC מוצפן לשרת המדיה המאוחסן עצמאית." },
        { h: "אחרי ההתייעצות", p: "משתתף מסמן אותה כהושלמה; אנשי המקצוע כותבים ומאשרים את הסיכום." },
      ],
    },
  },
  {
    slug: "consultation-summaries", category: "professionals", audience: ["professional", "patient"], context: [],
    related: ["video-consultations", "sharing-and-revocation"],
    en: {
      title: "Consultation summaries and approvals",
      summary: "Versions, individual approvals and what happens when a summary is approved.",
      body: [
        { p: "Any participating professional can write the summary: discussion, their own observation, proposed follow-up actions and referenced documents (only documents shared with them)." },
        { h: "Automatic draft", p: "“Assemble draft from notes” collects the professionals' own consultation notes into a draft. It adds no clinical content, is clearly labelled, and must be edited and approved like any other version." },
        { h: "Approval", p: "Each participating professional approves individually. The summary becomes approved only when all of them have approved. HealthBridge never infers agreement. Any change creates a new version and requires approval again." },
        { h: "When approved", p: "The summary is saved as a document, linked to the journey event, proposed follow-ups become recommendations, and care gaps are re-evaluated. The patient is asked to acknowledge it." },
      ],
    },
    he: {
      title: "סיכומי התייעצות ואישורים",
      summary: "גרסאות, אישורים אישיים ומה קורה כשסיכום מאושר.",
      body: [
        { p: "כל איש מקצוע משתתף יכול לכתוב את הסיכום: דיון, התרשמות אישית, פעולות מעקב מוצעות ומסמכים שאוזכרו (רק מסמכים ששותפו איתו)." },
        { h: "טיוטה אוטומטית", p: "\"הרכבת טיוטה מההערות\" אוספת את הערות ההתייעצות של אנשי המקצוע לטיוטה. היא אינה מוסיפה תוכן קליני, מסומנת בבירור, ויש לערוך ולאשר אותה ככל גרסה אחרת." },
        { h: "אישור", p: "כל איש מקצוע משתתף מאשר בנפרד. הסיכום מאושר רק כשכולם אישרו. HealthBridge לעולם אינה מניחה הסכמה. כל שינוי יוצר גרסה חדשה ומחייב אישור מחדש." },
        { h: "לאחר האישור", p: "הסיכום נשמר כמסמך ומקושר לאירוע במסע, פעולות המעקב המוצעות הופכות להמלצות, ופערי הרצף מחושבים מחדש. המטופל מתבקש לאשר קבלה." },
      ],
    },
  },
  {
    slug: "privacy-and-audit", category: "privacy", audience: ["patient", "professional", "admin"], context: ["/app/privacy"],
    related: ["sharing-and-revocation", "synthetic-data"],
    en: {
      title: "Privacy, audit history and your data rights",
      summary: "What is recorded, how the audit log is protected and how to export your data.",
      body: [
        { p: "Every access to your records is recorded: views, downloads, uploads, sharing changes, assistant questions (without their text) and denied attempts. You can see this history on the Privacy & audit page." },
        { h: "Tamper evidence", p: "Each audit record is chained to the previous one with a keyed hash. An administrator can verify the chain; any modification breaks it." },
        { h: "What is never logged", p: "Document content, passwords, access tokens, and the text of assistant conversations or in-meeting chat." },
        { h: "Your rights in this demo", list: ["View your full access history", "Export your records as FHIR R4", "Delete documents you uploaded", "Revoke sharing at any time"] },
        { p: "This is a demonstration and does not claim compliance with HIPAA, GDPR or Israeli privacy regulations. See the project documentation for the regulatory analysis." },
      ],
    },
    he: {
      title: "פרטיות, יומן גישה וזכויותיך",
      summary: "מה נרשם, כיצד היומן מוגן וכיצד לייצא את הנתונים.",
      body: [
        { p: "כל גישה לרשומות שלך נרשמת: צפיות, הורדות, העלאות, שינויי שיתוף, שאלות לעוזר (ללא תוכנן) וניסיונות שנדחו. ההיסטוריה זמינה בעמוד פרטיות ויומן גישה." },
        { h: "עמידות לשינויים", p: "כל רשומת ביקורת משורשרת לקודמתה באמצעות גיבוב מבוסס מפתח. מנהל מערכת יכול לאמת את השרשרת; כל שינוי שובר אותה." },
        { h: "מה לעולם אינו נרשם", p: "תוכן מסמכים, סיסמאות, אסימוני גישה, ותוכן שיחות עם העוזר או צ'אט בפגישה." },
        { h: "הזכויות שלך בהדגמה", list: ["צפייה בהיסטוריית הגישה המלאה", "ייצוא הרשומות כ-FHIR R4", "מחיקת מסמכים שהעלית", "ביטול שיתוף בכל עת"] },
        { p: "זוהי הדגמה ואינה טוענת לעמידה ב-HIPAA, GDPR או בתקנות הפרטיות בישראל. ניתוח רגולטורי מופיע בתיעוד הפרויקט." },
      ],
    },
  },
  {
    slug: "ai-limitations", category: "ai", audience: ["patient", "professional", "admin"], context: ["/app/assistant"],
    related: ["understanding-care-gaps", "privacy-and-audit"],
    en: {
      title: "What the assistant can and cannot do",
      summary: "Modes, boundaries and how answers are grounded in your documents.",
      body: [
        { h: "It can", list: ["Search documents you are authorized to see and quote the relevant passages", "List open follow-ups and unresolved care gaps", "Summarize your journey", "Suggest administrative questions for your next consultation", "Point you to the right help article", "Propose a follow-up item — which is created only if you confirm it"] },
        { h: "It cannot", list: ["Diagnose, prescribe, suggest doses or change treatment", "See documents you are not authorized to see", "Send information outside HealthBridge", "Change approved clinical records"] },
        { h: "Modes", p: "Deterministic mode (default) assembles answers from your records using rules and says so — it is not presented as AI reasoning. An optional local language model (Ollama) can rephrase answers from the quoted excerpts; its output is checked for citations and prohibited content, and the assistant falls back to deterministic mode if the check fails or the model is unavailable." },
        { h: "Untrusted content", p: "Text inside documents is treated as data. Passages that look like instructions are flagged and never followed." },
      ],
    },
    he: {
      title: "מה העוזר יכול ומה אינו יכול לעשות",
      summary: "מצבים, גבולות וכיצד התשובות מבוססות על המסמכים שלך.",
      body: [
        { h: "הוא יכול", list: ["לחפש במסמכים שמותר לך לראות ולצטט את הקטעים הרלוונטיים", "להציג מעקבים פתוחים ופערי רצף", "לסכם את המסע", "להציע שאלות מנהליות להתייעצות הבאה", "להפנות למאמר העזרה המתאים", "להציע פריט מעקב — שנוצר רק אם תאשר/י"] },
        { h: "הוא אינו יכול", list: ["לאבחן, לרשום תרופות, להציע מינונים או לשנות טיפול", "לראות מסמכים שאינך מורשה לראות", "לשלוח מידע אל מחוץ ל-HealthBridge", "לשנות רשומות קליניות מאושרות"] },
        { h: "מצבים", p: "המצב הדטרמיניסטי (ברירת מחדל) מרכיב תשובות מהרשומות באמצעות כללים ומציין זאת — הוא אינו מוצג כהסקה של בינה מלאכותית. מודל שפה מקומי אופציונלי (Ollama) יכול לנסח מחדש תשובות מהקטעים המצוטטים; הפלט נבדק לציטוטים ולתוכן אסור, והעוזר חוזר למצב הדטרמיניסטי אם הבדיקה נכשלת או שהמודל אינו זמין." },
        { h: "תוכן לא מהימן", p: "טקסט בתוך מסמכים מטופל כנתונים. קטעים הנראים כהוראות מסומנים ולעולם אינם מבוצעים." },
      ],
    },
  },
  {
    slug: "fhir-import-export", category: "patients", audience: ["patient", "professional"], context: [],
    related: ["uploading-documents"],
    en: {
      title: "FHIR import and export",
      summary: "Which HL7 FHIR R4 resources are supported and what is ignored.",
      body: [
        { h: "Import", p: "Upload a .json file containing a FHIR R4 resource or Bundle. Supported: Encounter, Observation, DiagnosticReport, ServiceRequest, CarePlan, DocumentReference (plain-text attachments). Patient resources are skipped because you are the subject." },
        { h: "Import report", p: "Each FHIR document shows what was imported, what was skipped (unsupported resource types), which fields were ignored, any validation errors, and which declared profiles were not validated." },
        { h: "Export", p: "Privacy & audit → Export downloads your records as a FHIR R4 collection Bundle (metadata level)." },
        { p: "HealthBridge is FHIR-compatible for this subset only. It is not a conformant FHIR server and does not validate profiles or terminology." },
      ],
    },
    he: {
      title: "ייבוא וייצוא FHIR",
      summary: "אילו משאבי HL7 FHIR R4 נתמכים ומה לא נקלט.",
      body: [
        { h: "ייבוא", p: "העלאת קובץ ‎.json המכיל משאב FHIR R4 או Bundle. נתמכים: Encounter, Observation, DiagnosticReport, ServiceRequest, CarePlan, DocumentReference (קבצים מצורפים בטקסט פשוט). משאבי Patient מדולגים כי את/ה הנושא." },
        { h: "דוח ייבוא", p: "לכל מסמך FHIR מוצג מה יובא, מה דולג (סוגי משאבים לא נתמכים), אילו שדות לא נקלטו, שגיאות אימות, ואילו פרופילים מוצהרים לא אומתו." },
        { h: "ייצוא", p: "פרטיות ויומן גישה ← ייצוא מוריד את הרשומות כ-Bundle מסוג collection ב-FHIR R4 (ברמת מטא-נתונים)." },
        { p: "HealthBridge תואמת FHIR לתת-קבוצה זו בלבד. זה אינו שרת FHIR תקני והוא אינו מאמת פרופילים או מינוח." },
      ],
    },
  },
  {
    slug: "professional-verification", category: "professionals", audience: ["professional", "admin"], context: [],
    related: ["getting-started-professional"],
    en: {
      title: "Professional verification (simulated)",
      summary: "What “verified” means in this demonstration.",
      body: [
        { p: "Professional accounts show a verification status. In this demonstration an administrator sets it manually. No medical licence, registry or identity check is performed." },
        { p: "Only professionals marked verified can receive sharing permissions or consultation invitations. A real deployment would need verification against the relevant licensing authority in each country, plus identity proofing." },
      ],
    },
    he: {
      title: "אימות אנשי מקצוע (מדומה)",
      summary: "מה פירוש \"מאומת\" בהדגמה זו.",
      body: [
        { p: "חשבונות אנשי מקצוע מציגים סטטוס אימות. בהדגמה זו מנהל מערכת קובע אותו ידנית. לא מתבצעת בדיקת רישיון, מרשם או זהות." },
        { p: "רק אנשי מקצוע מאומתים יכולים לקבל הרשאות שיתוף או הזמנות להתייעצות. פריסה אמיתית תחייב אימות מול רשות הרישוי בכל מדינה ואימות זהות." },
      ],
    },
  },
  {
    slug: "troubleshooting-video", category: "troubleshooting", audience: ["patient", "professional"], context: [],
    related: ["video-consultations"],
    en: {
      title: "Video troubleshooting",
      summary: "Camera, microphone and connection problems.",
      body: [
        { list: [
          "Allow camera and microphone access when the browser asks. If you blocked it, use the lock icon in the address bar to allow it and reload.",
          "Close other applications that may be using the camera.",
          "“Outside join window” means the room isn't open yet (it opens 2 hours before the start) or has closed. The patient can reschedule.",
          "“Could not connect to the video service” usually means the LiveKit service isn't running or its ports are blocked. In the local setup it needs TCP 7880–7881 and UDP 50000–50060 on this computer.",
          "Joining from another device on your network requires setting LIVEKIT_NODE_IP to this computer's LAN address (see the deployment guide).",
        ] },
      ],
    },
    he: {
      title: "פתרון תקלות וידאו",
      summary: "בעיות מצלמה, מיקרופון וחיבור.",
      body: [
        { list: [
          "יש לאשר גישה למצלמה ולמיקרופון כשהדפדפן מבקש. אם נחסמה, השתמש/י בסמל המנעול בשורת הכתובת כדי לאפשר ולרענן.",
          "סגור/י יישומים אחרים שעשויים להשתמש במצלמה.",
          "\"מחוץ לחלון הכניסה\" פירושו שהחדר עדיין לא נפתח (נפתח שעתיים לפני ההתחלה) או שנסגר. המטופל יכול לשנות מועד.",
          "\"לא ניתן להתחבר לשירות הווידאו\" פירושו בדרך כלל ששירות LiveKit אינו פועל או שהפורטים חסומים. בהתקנה המקומית נדרשים TCP 7880–7881 ו-UDP 50000–50060 במחשב זה.",
          "הצטרפות ממכשיר אחר ברשת מחייבת להגדיר LIVEKIT_NODE_IP לכתובת ה-LAN של מחשב זה (ראו מדריך הפריסה).",
        ] },
      ],
    },
  },
  {
    slug: "troubleshooting-documents", category: "troubleshooting", audience: ["patient"], context: [],
    related: ["uploading-documents"],
    en: {
      title: "Document upload troubleshooting",
      summary: "Why an upload was rejected or needs review.",
      body: [
        { list: [
          "Unsupported type — only PDF, .txt, .md and FHIR .json are accepted.",
          "Content does not match extension — the file's signature doesn't match its name (for example a renamed program). It is rejected for safety.",
          "Active content — PDFs with scripts, launch actions or embedded files are rejected.",
          "Needs manual review — no machine-readable text was found, usually a scanned image. OCR is not supported; correct the details and add recommendations manually.",
          "Already uploaded — the identical file exists; open the existing one or upload a new version instead.",
        ] },
      ],
    },
    he: {
      title: "פתרון תקלות בהעלאת מסמכים",
      summary: "מדוע העלאה נדחתה או דורשת בדיקה.",
      body: [
        { list: [
          "סוג לא נתמך — מתקבלים רק PDF,‏ ‎.txt,‏ ‎.md ו-FHIR ‎.json.",
          "התוכן אינו תואם לסיומת — חתימת הקובץ אינה תואמת לשמו (למשל תוכנה ששמה שונה). הקובץ נדחה מטעמי בטיחות.",
          "תוכן פעיל — קובצי PDF עם סקריפטים, פעולות הפעלה או קבצים מוטמעים נדחים.",
          "דורש בדיקה ידנית — לא נמצא טקסט קריא, בדרך כלל תמונה סרוקה. OCR אינו נתמך; יש לתקן פרטים ולהוסיף המלצות ידנית.",
          "כבר הועלה — קובץ זהה קיים; פתח/י את הקיים או העלה/י גרסה חדשה.",
        ] },
      ],
    },
  },
  {
    slug: "synthetic-data", category: "privacy", audience: ["patient", "professional", "admin"], context: [],
    related: ["privacy-and-audit", "ai-limitations"],
    en: {
      title: "About this demonstration",
      summary: "Synthetic data, no real integrations, not for clinical use.",
      body: [
        { p: "HealthBridge AI is a research and engineering demonstration. Every patient, professional, organization and document is fictional. There are no connections to real HMOs, hospitals, laboratories or registries." },
        { p: "It is not a clinically validated medical product, makes no diagnostic or treatment decisions, and must not be used for real patient care. Real deployment would require clinical validation, regulatory assessment, real identity and licence verification, and production security infrastructure." },
      ],
    },
    he: {
      title: "אודות הדגמה זו",
      summary: "נתונים סינתטיים, ללא חיבורים אמיתיים, לא לשימוש קליני.",
      body: [
        { p: "HealthBridge AI היא הדגמת מחקר והנדסה. כל המטופלים, אנשי המקצוע, הארגונים והמסמכים בדויים. אין חיבורים לקופות חולים, בתי חולים, מעבדות או מרשמים אמיתיים." },
        { p: "זה אינו מוצר רפואי מאומת קלינית, אינו מקבל החלטות אבחון או טיפול, ואין להשתמש בו לטיפול במטופלים אמיתיים. פריסה אמיתית תחייב תיקוף קליני, הערכה רגולטורית, אימות זהות ורישיון אמיתי ותשתית אבטחה ייצורית." },
      ],
    },
  },
  {
    slug: "language-and-accessibility", category: "start", audience: ["patient", "professional", "admin"], context: ["/app/settings"],
    related: ["getting-started-patient"],
    en: {
      title: "Language, time zones and accessibility",
      summary: "Switching Hebrew/English, dark mode and keyboard use.",
      body: [
        { list: [
          "Switch between English and Hebrew from the top bar; the layout switches between left-to-right and right-to-left. Your choice can be saved in Settings.",
          "Original documents are always shown in their original language and direction. Translations, where offered, are never treated as authoritative.",
          "Times are shown in your time zone (set in Settings); consultation pages also show each participant's local time.",
          "Every screen works with the keyboard. Use “Skip to main content” at the top of the page. Dialogs close with Escape.",
          "Statuses are always shown with text and an icon, not colour alone. Dark mode is available from the top bar.",
        ] },
      ],
    },
    he: {
      title: "שפה, אזורי זמן ונגישות",
      summary: "מעבר בין עברית לאנגלית, מצב כהה ושימוש במקלדת.",
      body: [
        { list: [
          "מעבר בין עברית לאנגלית מהסרגל העליון; הפריסה מתחלפת בין שמאל-לימין לימין-לשמאל. ניתן לשמור את הבחירה בהגדרות.",
          "מסמכים מקוריים מוצגים תמיד בשפתם ובכיוונם המקוריים. תרגומים, כשהם מוצעים, לעולם אינם מחייבים.",
          "השעות מוצגות באזור הזמן שלך (בהגדרות); בעמודי התייעצות מוצגת גם השעה המקומית של כל משתתף.",
          "כל מסך פועל במקלדת. השתמש/י ב\"דילוג לתוכן הראשי\" בראש העמוד. חלונות נסגרים במקש Escape.",
          "סטטוסים מוצגים תמיד בטקסט ובסמל, לא בצבע בלבד. מצב כהה זמין בסרגל העליון.",
        ] },
      ],
    },
  },
];

export function articleFor(slug: string) {
  return ARTICLES.find((a) => a.slug === slug);
}
