"""Upload validation and deterministic document understanding.

Everything here is a pure function over bytes/text so it can be unit-tested and replayed.
Uploaded content is only ever *parsed* — never executed, rendered as HTML, or evaluated.
"""
import io
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date

from pypdf import PdfReader

ALLOWED_EXTENSIONS = {".pdf": "application/pdf", ".txt": "text/plain", ".md": "text/markdown",
                      ".json": "application/fhir+json"}
# Markers of active content in PDFs. Their presence causes rejection.
_PDF_ACTIVE = [b"/JavaScript", b"/JS", b"/Launch", b"/EmbeddedFile", b"/RichMedia", b"/XFA", b"/SubmitForm"]
_BINARY_SIGNATURES = [b"MZ", b"PK\x03\x04", b"\x7fELF", b"\x89PNG", b"\xff\xd8\xff", b"GIF8", b"%PDF", b"\xd0\xcf\x11\xe0"]


class UploadRejected(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class ValidatedUpload:
    kind: str  # pdf | text | fhir
    mime_type: str
    extension: str


def _extension(filename: str) -> str:
    name = filename.strip().lower()
    return name[name.rfind("."):] if "." in name else ""


def validate_upload(filename: str, data: bytes, max_bytes: int) -> ValidatedUpload:
    if not data:
        raise UploadRejected("empty", "The file is empty.")
    if len(data) > max_bytes:
        raise UploadRejected("too_large", f"The file exceeds the {max_bytes // (1024 * 1024)} MB limit.")
    if len(filename) > 255 or any(c in filename for c in "\x00/\\"):
        raise UploadRejected("bad_filename", "The file name is not allowed.")
    ext = _extension(filename)
    if ext not in ALLOWED_EXTENSIONS:
        raise UploadRejected("unsupported_type", "Only PDF, plain text (.txt, .md) and FHIR JSON (.json) files are supported.")

    if ext == ".pdf":
        if not data.startswith(b"%PDF-"):
            raise UploadRejected("signature_mismatch", "The file content is not a PDF.")
        for marker in _PDF_ACTIVE:
            if re.search(re.escape(marker) + rb"(?![A-Za-z])", data):
                raise UploadRejected("active_content", "PDFs containing scripts, embedded files or launch actions are rejected.")
        try:
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted:
                raise UploadRejected("encrypted_pdf", "Password-protected PDFs are not supported.")
            root = reader.trailer["/Root"]
            names = root.get("/Names")
            if names is not None and "/JavaScript" in names.get_object():
                raise UploadRejected("active_content", "PDFs containing scripts are rejected.")
            _ = len(reader.pages)
        except UploadRejected:
            raise
        except Exception as exc:  # malformed structure
            raise UploadRejected("malformed_pdf", "The PDF could not be parsed.") from exc
        return ValidatedUpload("pdf", "application/pdf", ext)

    if any(data.startswith(sig) for sig in _BINARY_SIGNATURES):
        raise UploadRejected("signature_mismatch", "The file content does not match its extension.")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise UploadRejected("bad_encoding", "Text files must be UTF-8 encoded.") from exc
    if "\x00" in text:
        raise UploadRejected("binary_content", "The file contains binary content.")

    if ext == ".json":
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as exc:
            raise UploadRejected("bad_json", "The JSON file could not be parsed.") from exc
        from app.services.fhir import SUPPORTED_IMPORT_TYPES

        if not isinstance(obj, dict) or obj.get("resourceType") not in SUPPORTED_IMPORT_TYPES:
            raise UploadRejected(
                "unsupported_fhir",
                "JSON uploads must be a FHIR R4 resource of a supported type: " + ", ".join(sorted(SUPPORTED_IMPORT_TYPES)),
            )
        return ValidatedUpload("fhir", "application/fhir+json", ext)
    return ValidatedUpload("text", ALLOWED_EXTENSIONS[ext], ext)


# ------------------------------------------------------------------ text extraction
@dataclass
class ExtractionResult:
    text: str
    status: str  # processed | needs_review
    detail: str | None = None


def extract_text(kind: str, data: bytes) -> ExtractionResult:
    if kind == "pdf":
        reader = PdfReader(io.BytesIO(data))
        pages = [(p.extract_text() or "") for p in reader.pages[:200]]
        text = normalize_text("\n\n".join(pages))
        if len(text.strip()) < 20:
            return ExtractionResult(text, "needs_review",
                                    "No machine-readable text was found (possibly a scanned image). OCR is not "
                                    "supported — please enter the key details manually.")
        return ExtractionResult(text, "processed")
    if kind == "text":
        return ExtractionResult(normalize_text(data.decode("utf-8-sig")), "processed")
    raise ValueError(f"extract_text does not handle kind={kind}")


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    # strip control characters except newline/tab
    text = "".join(c for c in text if c in "\n\t" or unicodedata.category(c)[0] != "C")
    return text.strip()


def detect_language(text: str) -> str:
    hebrew = sum(1 for c in text if "֐" <= c <= "׿")
    latin = sum(1 for c in text if c.isascii() and c.isalpha())
    return "he" if hebrew > latin else "en"


# ------------------------------------------------------------------ metadata
_DATE_LABEL = re.compile(
    r"(?im)^\s*(?:date(?: of (?:visit|service|report|consultation|discharge|admission))?|visit date|report date|"
    r"collection date|תאריך(?: ביקור)?)\s*[:\-]\s*(\d{4}-\d{2}-\d{2}|\d{1,2}[/.]\d{1,2}[/.]\d{4})"
)
_ANY_ISO = re.compile(r"\b(20\d{2}|19\d{2})-(\d{2})-(\d{2})\b")
_AUTHOR = re.compile(r"(?:Dr\.?|Doctor|ד\"ר|ד״ר)\s+([A-Z֐-׿][\w֐-׿'\-]+(?:\s+[A-Z֐-׿][\w֐-׿'\-]+)?)")
_FACILITY = re.compile(r"(?im)^\s*(?:clinic|facility|institution|hospital|laboratory|provider|מוסד|מרפאה)\s*[:\-]\s*(.+)$")


def parse_date(value: str) -> date | None:
    """ISO (YYYY-MM-DD) or day-first (DD/MM/YYYY, the Israeli convention)."""
    try:
        if "-" in value:
            y, m, d = value.split("-")
        else:
            d, m, y = re.split(r"[/.]", value)
        return date(int(y), int(m), int(d))
    except (ValueError, TypeError):
        return None


@dataclass
class DocumentMetadata:
    title: str | None = None
    document_date: date | None = None
    author: str | None = None
    source: str | None = None
    organization_name: str | None = None
    category: str = "other"
    language: str = "en"


_CATEGORY_RULES = [
    ("discharge_summary", re.compile(r"(?i)discharge summary|סיכום שחרור|מכתב שחרור")),
    ("consultation_summary", re.compile(r"(?i)consultation summary \(healthbridge\)")),
    ("imaging_report", re.compile(r"(?i)imaging report|radiology report|ultrasound report|x-ray report|echocardiogram report|דו\"ח הדמיה|פענוח")),
    ("lab_result", re.compile(r"(?i)laboratory (?:report|results?)|lab results?|test results|תוצאות מעבדה|תוצאות בדיק")),
    ("referral", re.compile(r"(?i)^\s*referral\b|referral letter|מכתב הפניה|^\s*הפניה")),
    ("consultation_note", re.compile(r"(?i)consultation|clinic visit|visit summary|office visit|ביקור|ייעוץ|סיכום ביקור")),
]


def extract_metadata(text: str, organization_names: list[str]) -> DocumentMetadata:
    md = DocumentMetadata(language=detect_language(text))
    head = text[:1500]
    for line in text.splitlines():
        if line.strip():
            md.title = line.strip()[:200]
            break
    m = _DATE_LABEL.search(text)
    if m:
        md.document_date = parse_date(m.group(1))
    if not md.document_date:
        m2 = _ANY_ISO.search(head)
        if m2:
            md.document_date = parse_date(m2.group(0))
    a = _AUTHOR.search(text)
    if a:
        md.author = a.group(0).strip()
    lowered = head.lower()
    for name in sorted(organization_names, key=len, reverse=True):
        if name.lower() in lowered:
            md.organization_name = name
            md.source = name
            break
    if not md.source:
        f = _FACILITY.search(head)
        if f:
            md.source = f.group(1).strip()[:300]
    # The heading decides the category; the body is only a fallback (a letter that *mentions*
    # "the laboratory report" is not a laboratory report).
    heading = "\n".join([ln for ln in text.splitlines() if ln.strip()][:2])
    for zone in (heading, head):
        match = next((category for category, rx in _CATEGORY_RULES if rx.search(zone)), None)
        if match:
            md.category = match
            break
    return md


# ------------------------------------------------------------------ clinical terms
# Canonical, deliberately small vocabulary used to match recommendations to evidence.
TERMS: dict[str, list[str]] = {
    "cbc": [r"\bcbc\b", r"complete blood count", r"ספירת דם"],
    "lipid_panel": [r"lipid", r"cholesterol", r"\bldl\b", r"פרופיל שומנים", r"שומנים", r"כולסטרול"],
    "hba1c": [r"hba1c", r"a1c", r"hemoglobin a1c", r"המוגלובין מסוכרר"],
    "tsh": [r"\btsh\b", r"thyroid"],
    "troponin": [r"troponin"],
    "echocardiogram": [r"echocardiogra", r"\becho\b", r"אקו לב", r"אקוקרדיוגרפיה"],
    "stress_test": [r"stress test", r"ergometr", r"מבחן מאמץ"],
    "holter": [r"holter", r"הולטר"],
    "chest_xray": [r"chest x-?ray", r"צילום חזה"],
    "ecg": [r"\becg\b", r"\bekg\b", r"electrocardiogra", r"א\.ק\.ג"],
    "cardiology": [r"cardiolog", r"קרדיולוג"],
    "endocrinology": [r"endocrinolog", r"אנדוקרינולוג"],
}
_TERM_RX = {k: re.compile("|".join(v), re.IGNORECASE) for k, v in TERMS.items()}


def find_terms(text: str) -> list[str]:
    return sorted(k for k, rx in _TERM_RX.items() if rx.search(text))


# ------------------------------------------------------------------ recommendations
_TRIGGER = re.compile(
    r"(?i)\b(recommend(?:ed|s|ation)?|follow[- ]?up|should (?:undergo|have|perform|schedule|repeat|see)|"
    r"please (?:schedule|perform|repeat|book|arrange)|refer(?:red|ral)? to|second opinion|to be repeated|"
    r"repeat (?:the )?\w+|return for|re-?evaluat\w*|is advised|advised to)\b"
    r"|מומלץ|המלצה|המלצות|מעקב|הפניה|להפנות|לבצע|לחזור|יש לקבוע|בדיקה חוזרת|לתאם"
)
_NEGATION = re.compile(r"(?i)\b(no|not|without)\b[^.]*\b(needed|required|necessary|indicated)\b|אין צורך|לא נדרש")
_SECTION_HEADER = re.compile(r"(?i)^\s*(recommendations?|plan|follow[- ]?up plan|המלצות|תכנית(?: טיפול)?|המלצה)\s*:?\s*$")
_BULLET = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")
_TIMEFRAME = re.compile(
    r"(?i)\b(?:within|in|after|in about|in approximately)\s+(?:\d+|one|two|three|four|five|six|eight|ten|twelve)"
    r"(?:\s*(?:-|to)\s*\d+)?\s+(?:day|week|month|year)s?\b"
    r"|(?:בעוד|תוך|בתוך)\s+(?:\d+|שבוע|חודש|שבועיים|חודשיים)\s*(?:ימים|שבועות|חודשים)?"
)
_DUE = re.compile(r"(?i)\b(?:by|before|no later than|until|עד)\s+(\d{4}-\d{2}-\d{2}|\d{1,2}[/.]\d{1,2}[/.]\d{4})")
_CLAUSE_SPLIT = re.compile(r"(?i)\b(?:after|once|following|when|upon)\b|לאחר|אחרי")

_KIND_RULES = [
    ("referral", re.compile(r"(?i)refer|second opinion|הפניה|להפנות|חוות דעת שנייה")),
    ("imaging", re.compile(r"(?i)echocardiogra|\becho\b|ultrasound|x-?ray|\bmri\b|\bct\b|imaging|scan|mammogra|stress test|"
                           r"holter|\becg\b|\bekg\b|אקו|אולטרסאונד|צילום|הדמיה|מבחן מאמץ|הולטר")),
    ("lab_test", re.compile(r"(?i)blood test|\bcbc\b|lipid|hba1c|cholesterol|troponin|\btsh\b|\blab|panel|urine|בדיקת דם|ספירת דם|שומנים|מעבדה|בדיקות דם")),
    ("follow_up_visit", re.compile(r"(?i)follow[- ]?up|visit|appointment|return|clinic|מעקב|ביקור|תור")),
]


@dataclass
class ExtractedRecommendation:
    kind: str
    text: str
    passage: str
    char_start: int
    char_end: int
    timeframe_text: str | None = None
    due_date: date | None = None
    targets: list[str] = field(default_factory=list)


def classify_kind(sentence: str) -> str:
    head = _CLAUSE_SPLIT.split(sentence, maxsplit=1)[0]
    for kind, rx in _KIND_RULES:
        if rx.search(head):
            return kind
    for kind, rx in _KIND_RULES:  # fall back to whole sentence
        if rx.search(sentence):
            return kind
    return "other"


def _segments(text: str):
    """Yield (start, end, segment, in_plan_section) — lines, split further into sentences."""
    pos = 0
    in_section = False
    for raw_line in text.split("\n"):
        line_start = pos
        pos += len(raw_line) + 1
        if not raw_line.strip():
            in_section = False
            continue
        if _SECTION_HEADER.match(raw_line):
            in_section = True
            continue
        if raw_line.rstrip().endswith(":") and len(raw_line.strip()) < 40:
            in_section = False
        for m in re.finditer(r"[^.!?]+(?:[.!?]+|$)", raw_line):
            seg = m.group(0)
            if seg.strip():
                s = line_start + m.start() + (len(seg) - len(seg.lstrip()))
                e = line_start + m.end() - (len(seg) - len(seg.rstrip()))
                yield s, e, text[s:e], in_section or bool(_BULLET.match(raw_line))


def extract_recommendations(text: str) -> list[ExtractedRecommendation]:
    results: list[ExtractedRecommendation] = []
    seen: set[str] = set()
    for start, end, seg, in_section in _segments(text):
        cleaned = _BULLET.sub("", seg).strip()
        if len(cleaned) < 8:
            continue
        triggered = bool(_TRIGGER.search(cleaned))
        kind = classify_kind(cleaned)
        if not triggered and not (in_section and kind != "other"):
            continue
        if _NEGATION.search(cleaned):
            continue
        key = re.sub(r"\W+", " ", cleaned.lower()).strip()
        if key in seen:
            continue
        seen.add(key)
        tf = _TIMEFRAME.search(cleaned)
        due = _DUE.search(cleaned)
        passage_start = start + (seg.find(cleaned) if cleaned in seg else 0)
        results.append(
            ExtractedRecommendation(
                kind=kind,
                text=cleaned,
                passage=text[passage_start:passage_start + len(cleaned)],
                char_start=passage_start,
                char_end=passage_start + len(cleaned),
                timeframe_text=tf.group(0) if tf else None,
                due_date=parse_date(due.group(1)) if due else None,
                # Targets come from the action clause: "stress test after the echocardiogram" targets the stress test.
                targets=find_terms(_CLAUSE_SPLIT.split(cleaned, maxsplit=1)[0]) or find_terms(cleaned),
            )
        )
    return results
