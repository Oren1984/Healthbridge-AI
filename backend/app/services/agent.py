"""Bounded, tool-based healthcare-continuity assistant.

Boundaries (enforced in code, not by prompt):
- Guardrails run on the user message *before* any tool executes; diagnosis, prescribing,
  treatment changes and external sending are refused.
- Only tools in `TOOLS` can run. Read tools receive data already filtered by AccessPolicy.
- The only state-changing capability (`propose_followup_task`) creates an inert proposal; the
  change happens only when the user confirms it through a separate, authorized API call.
- Deterministic mode (default) uses templates over retrieved records — never presented as model
  reasoning. Local-LLM mode only rewrites retrieved evidence and is validated, else it falls back.
"""
import re
import uuid
from types import SimpleNamespace
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.authz import AccessPolicy
from app.models import AssistantAction, CareGap, FollowUpTask, JourneyEvent, Recommendation, User
from app.observability import metrics
from app.services import llm, rag

PROHIBITED = re.compile(
    r"(?i)\bdiagnos\w*|what (disease|illness|condition) (do|might|could) i have|do i have (cancer|a disease|an? \w+ disease)|"
    r"\bprescri\w*|\bdosage\b|\bdose\b|how (much|many) .*(take|mg|pills)|should i (take|stop|start|increase|decrease|change)|"
    r"change (my )?(treatment|medication|medicine)|which (drug|medication|medicine)|"
    r"אבחנה|לאבחן|אבחון|מרשם|מינון|כמה (מ\"ג|כדורים)|האם (לקחת|להפסיק)|איזו (מחלה|תרופה)|לשנות (את )?הטיפול"
)
EXTERNAL_SEND = re.compile(r"(?i)\b(send|email|forward|upload|share)\b.*\b(to|with)\b.*(@|\bemail\b|insurer|employer|\bhttp)|שלח.*(מייל|לביטוח)")

INTENTS = [
    ("create_task", re.compile(r"(?i)remind me|create (a )?(task|follow-?up)|add (a )?(task|follow-?up)|צור משימה|הוסף משימה|תזכיר")),
    ("help", re.compile(r"(?i)^(how (do|can) i|how to|where (do|can) i|help\b)|איך (אני )?|^עזרה")),
    ("questions", re.compile(r"(?i)question|ask (my |the )?(doctor|physician|specialist)|prepare for|שאלות|להכין")),
    ("gaps", re.compile(r"(?i)\bgaps?\b|missing|unresolved|not verified|unverified|unknown|incomplete|פער|חסר|לא ידוע|לא מאומת")),
    ("followups", re.compile(r"(?i)follow-?ups?|pending|open (tasks|items)|to-?do|what('s| is) (left|open)|מעקב|משימות|פתוח")),
    ("journey", re.compile(r"(?i)timeline|journey|history|summar|what happened|overview|ציר הזמן|מסע|היסטוריה|סכם|סיכום")),
]

HELP_TOPICS = [
    (re.compile(r"(?i)shar|consent|revok|access|שיתוף|הרשא|ביטול"), "sharing-and-revocation"),
    (re.compile(r"(?i)upload|document|file|pdf|העלא|מסמך"), "uploading-documents"),
    (re.compile(r"(?i)video|meeting|consult|camera|call|room|וידאו|פגישה|ייעוץ"), "video-consultations"),
    (re.compile(r"(?i)gap|missing|unknown|פער"), "understanding-care-gaps"),
    (re.compile(r"(?i)privacy|audit|history|פרטיות"), "privacy-and-audit"),
    (re.compile(r"(?i)\bai\b|assistant|עוזר"), "ai-limitations"),
]

TOOLS = {  # name -> read_only
    "search_documents": True,
    "list_care_gaps": True,
    "list_followups": True,
    "journey_summary": True,
    "suggest_questions": True,
    "help_navigation": True,
    "propose_followup_task": False,
}

T = {
    "en": {
        "label_det": "Deterministic mode — assembled from your records by rules. This is not AI reasoning.",
        "label_llm": "Local AI model output — generated from the cited excerpts only. Verify against the sources.",
        "label_fallback": "The local AI model was unavailable or its output failed validation, so this answer was assembled by rules.",
        "refuse_clinical": "I can't diagnose conditions, recommend medication or doses, or change treatment. Those decisions belong to your healthcare professionals. I can help you find what your documents say, see open follow-ups, or prepare questions for your next consultation.",
        "refuse_external": "I can't send medical information outside HealthBridge. To share with a professional, use the Sharing Center, where you choose exactly what is shared and for how long.",
        "insufficient": "I couldn't find supporting evidence for that in the documents available to you. I won't guess. Try different words, or check whether the relevant document has been uploaded or shared.",
        "found": "Here is what the documents say (quoted directly):",
        "no_gaps": "No unresolved continuity items were found.",
        "gaps": "Items that are open, unknown or need clarification:",
        "no_tasks": "There are no open follow-up tasks.",
        "tasks": "Open follow-up tasks:",
        "journey": "Your recorded healthcare journey (most recent first):",
        "no_journey": "No journey events are recorded yet.",
        "questions": "Administrative questions you could raise at your next consultation:",
        "no_questions": "Nothing currently needs clarification, so there are no suggested questions.",
        "help": "This Help Center article covers it:",
        "help_none": "Open the Help Center to browse all topics:",
        "task_proposed": "I've prepared this follow-up task. It will only be created if you confirm it:",
        "task_need_title": "Tell me what the task should say, e.g. \"remind me to request the echocardiogram report\".",
        "task_patient_only": "Only the patient can create follow-up tasks through the assistant.",
        "suspicious": "One quoted passage contains text that looks like instructions. It was treated purely as document content and not followed.",
        "pending_review": "extracted, awaiting review",
        "no_due": "no documented due date",
    },
    "he": {
        "label_det": "מצב דטרמיניסטי — התשובה הורכבה מהרשומות שלך באמצעות כללים. זו אינה הסקה של בינה מלאכותית.",
        "label_llm": "פלט ממודל AI מקומי — נוצר מהקטעים המצוטטים בלבד. יש לאמת מול המקורות.",
        "label_fallback": "מודל ה-AI המקומי לא היה זמין או שהפלט שלו לא עבר בדיקה, ולכן התשובה הורכבה באמצעות כללים.",
        "refuse_clinical": "איני יכול לאבחן, להמליץ על תרופות או מינונים, או לשנות טיפול. החלטות אלה שייכות לאנשי המקצוע המטפלים בך. אני יכול לעזור למצוא מה כתוב במסמכים, להציג משימות מעקב פתוחות או להכין שאלות לייעוץ הבא.",
        "refuse_external": "איני יכול לשלוח מידע רפואי אל מחוץ ל-HealthBridge. לשיתוף עם איש מקצוע השתמש/י במרכז השיתוף, שם בוחרים בדיוק מה משותף ולכמה זמן.",
        "insufficient": "לא מצאתי ראיות תומכות לכך במסמכים הזמינים לך. לא אנחש. נסה/י ניסוח אחר, או בדוק/י שהמסמך הרלוונטי הועלה או שותף.",
        "found": "זה מה שכתוב במסמכים (ציטוט ישיר):",
        "no_gaps": "לא נמצאו פריטי רצף טיפול פתוחים.",
        "gaps": "פריטים פתוחים, לא ידועים או הדורשים הבהרה:",
        "no_tasks": "אין משימות מעקב פתוחות.",
        "tasks": "משימות מעקב פתוחות:",
        "journey": "המסע הרפואי המתועד שלך (מהחדש לישן):",
        "no_journey": "עדיין לא תועדו אירועים.",
        "questions": "שאלות מנהליות שאפשר להעלות בייעוץ הבא:",
        "no_questions": "אין כרגע פריטים הדורשים הבהרה, ולכן אין שאלות מוצעות.",
        "help": "מאמר מרכז העזרה הבא עוסק בכך:",
        "help_none": "פתח/י את מרכז העזרה לעיון בכל הנושאים:",
        "task_proposed": "הכנתי את משימת המעקב הבאה. היא תיווצר רק לאחר אישורך:",
        "task_need_title": "כתוב/י מה המשימה צריכה לומר, למשל \"תזכיר לי לבקש את תוצאות האקו\".",
        "task_patient_only": "רק המטופל/ת יכול/ה ליצור משימות מעקב דרך העוזר.",
        "suspicious": "אחד הקטעים המצוטטים מכיל טקסט שנראה כמו הוראות. הוא טופל כתוכן מסמך בלבד ולא בוצע.",
        "pending_review": "חולץ, ממתין לבדיקה",
        "no_due": "אין תאריך יעד מתועד",
    },
}


@dataclass
class AgentResponse:
    answer: str
    intent: str
    mode: str  # deterministic | local_llm | fallback | refusal
    label: str
    tools_used: list[str] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)
    items: list[dict] = field(default_factory=list)
    insufficient_evidence: bool = False
    pending_action: dict | None = None
    warnings: list[str] = field(default_factory=list)


class ToolNotAllowed(Exception):
    pass


class HealthBridgeAgent:
    def __init__(self, db: Session, user: User, patient_id: uuid.UUID) -> None:
        self.db = db
        self.user = user
        self.patient_id = patient_id
        self.policy = AccessPolicy(db, user)
        self.lang = user.locale if user.locale in T else "en"
        self.t = T[self.lang]
        self.tools_used: list[str] = []

    # -------------------------------------------------------- tool gate
    def _call(self, name: str, *args, **kwargs):
        if name not in TOOLS:
            raise ToolNotAllowed(name)
        self.tools_used.append(name)
        return getattr(self, f"tool_{name}")(*args, **kwargs)

    # -------------------------------------------------------- read tools
    def tool_search_documents(self, query: str) -> list[rag.RetrievedChunk]:
        allowed = self.policy.accessible_document_ids(self.patient_id)  # authorization BEFORE retrieval
        return rag.retrieve(self.db, self.patient_id, allowed, query, k=4)

    def tool_list_care_gaps(self) -> list[SimpleNamespace]:
        """Unresolved gaps, redacted for the viewer exactly like the care-gap API (gap_view)."""
        from app.api.serializers import gap_view

        if not self.policy.can_view_patient_section(self.patient_id, "care_gaps"):
            return []
        gaps = self.db.execute(select(CareGap).where(CareGap.patient_id == self.patient_id, CareGap.active.is_(True))).scalars()
        return [SimpleNamespace(**gap_view(g, self.policy)) for g in gaps
                if g.status in ("open", "unknown", "requires_clarification")]

    def tool_list_followups(self) -> list[FollowUpTask]:
        if not self.policy.can_view_patient_section(self.patient_id, "tasks"):
            return []
        return list(self.db.execute(select(FollowUpTask).where(
            FollowUpTask.patient_id == self.patient_id, FollowUpTask.status == "open")
            .order_by(FollowUpTask.due_date.nulls_last(), FollowUpTask.created_at)).scalars())

    def tool_journey_summary(self) -> list[JourneyEvent]:
        if not self.policy.can_view_patient_section(self.patient_id, "journey"):
            return []
        return list(self.db.execute(select(JourneyEvent).where(JourneyEvent.patient_id == self.patient_id)
                                    .order_by(JourneyEvent.occurred_at.desc()).limit(12)).scalars())

    def tool_suggest_questions(self) -> list[str]:
        return [g.suggested_clarification for g in self.tool_list_care_gaps() if g.suggested_clarification][:6]

    def tool_help_navigation(self, message: str) -> str | None:
        for rx, slug in HELP_TOPICS:
            if rx.search(message):
                return slug
        return None

    # -------------------------------------------------------- state-changing (proposal only)
    def tool_propose_followup_task(self, title: str) -> AssistantAction:
        action = AssistantAction(user_id=self.user.id, patient_id=self.patient_id,
                                 action_type="create_followup_task", payload={"title": title[:300]})
        self.db.add(action)
        self.db.flush()
        return action

    # -------------------------------------------------------- orchestration
    def respond(self, message: str) -> AgentResponse:
        message = message.strip()[:1000]
        metrics.incr("agent.queries")
        if PROHIBITED.search(message):
            metrics.incr("agent.refusals")
            return AgentResponse(self.t["refuse_clinical"], "refused_clinical", "refusal", self.t["label_det"])
        if EXTERNAL_SEND.search(message):
            metrics.incr("agent.refusals")
            return AgentResponse(self.t["refuse_external"], "refused_external", "refusal", self.t["label_det"])

        intent = next((name for name, rx in INTENTS if rx.search(message)), "search")
        handler = getattr(self, f"_handle_{intent}")
        resp: AgentResponse = handler(message)
        resp.tools_used = self.tools_used
        return resp

    def _det(self, answer: str, intent: str, **kw) -> AgentResponse:
        return AgentResponse(answer, intent, "deterministic", self.t["label_det"], **kw)

    def _handle_search(self, message: str) -> AgentResponse:
        chunks = self._call("search_documents", message)
        if not chunks:
            return self._det(self.t["insufficient"], "search", insufficient_evidence=True)
        sources = [{"ref": f"S{i + 1}", "document_id": str(c.document_id), "title": c.document_title,
                    "date": c.document_date, "excerpt": c.text[:600], "char_start": c.char_start,
                    "char_end": c.char_end, "score": c.score, "suspicious": c.suspicious}
                   for i, c in enumerate(chunks)]
        warnings = [self.t["suspicious"]] if any(c.suspicious for c in chunks) else []
        from app.services.llm import get_ai_mode

        if get_ai_mode(self.db) == "ollama":
            excerpts = [_strip_instructions(c.text) for c in chunks]
            try:
                answer = llm.compose_answer(message, excerpts, self.lang)
                if answer is None:
                    return AgentResponse(self.t["insufficient"], "search", "local_llm", self.t["label_llm"],
                                         insufficient_evidence=True, sources=sources, warnings=warnings)
                return AgentResponse(answer, "search", "local_llm", self.t["label_llm"], sources=sources, warnings=warnings)
            except llm.LLMUnavailable:
                lines = [self.t["found"]] + [f"[{s['ref']}] “{_first_sentences(s['excerpt'])}” — {s['title']}" for s in sources]
                return AgentResponse("\n".join(lines), "search", "fallback", self.t["label_fallback"], sources=sources, warnings=warnings)
        lines = [self.t["found"]] + [f"[{s['ref']}] “{_first_sentences(s['excerpt'])}” — {s['title']}" for s in sources]
        return self._det("\n".join(lines), "search", sources=sources, warnings=warnings)

    def _handle_gaps(self, message: str) -> AgentResponse:
        gaps = self._call("list_care_gaps")
        if not gaps:
            return self._det(self.t["no_gaps"], "gaps")
        items = [{"type": "care_gap", "id": str(g.id), "title": g.title, "status": g.status, "rule_id": g.rule_id,
                  "link": f"/app/care-gaps?gap={g.id}"} for g in gaps]
        lines = [self.t["gaps"]] + [f"• [{g.status}] {g.title}" for g in gaps]
        return self._det("\n".join(lines), "gaps", items=items)

    def _handle_followups(self, message: str) -> AgentResponse:
        tasks = self._call("list_followups")
        if not tasks:
            return self._det(self.t["no_tasks"], "followups")
        items = [{"type": "task", "id": str(t.id), "title": t.title, "status": t.status,
                  "due_date": t.due_date.isoformat() if t.due_date else None, "link": "/app/tasks"} for t in tasks]
        lines = [self.t["tasks"]] + [f"• {t.title} ({t.due_date.isoformat() if t.due_date else self.t['no_due']})" for t in tasks]
        return self._det("\n".join(lines), "followups", items=items)

    def _handle_journey(self, message: str) -> AgentResponse:
        events = self._call("journey_summary")
        if not events:
            return self._det(self.t["no_journey"], "journey")
        items = [{"type": "event", "id": str(e.id), "title": e.title, "date": e.occurred_at.date().isoformat(),
                  "event_type": e.event_type, "verification_status": e.verification_status,
                  "link": f"/app/journey?event={e.id}"} for e in events]
        lines = [self.t["journey"]] + [
            f"• {e.occurred_at.date().isoformat()} — {e.title}" + (f" ({e.organization.name})" if e.organization else "")
            for e in events]
        return self._det("\n".join(lines), "journey", items=items)

    def _handle_questions(self, message: str) -> AgentResponse:
        qs = self._call("suggest_questions")
        if not qs:
            return self._det(self.t["no_questions"], "questions")
        return self._det("\n".join([self.t["questions"]] + [f"{i + 1}. {q}" for i, q in enumerate(qs)]), "questions",
                         items=[{"type": "question", "text": q} for q in qs])

    def _handle_help(self, message: str) -> AgentResponse:
        slug = self._call("help_navigation", message)
        if slug:
            return self._det(self.t["help"], "help", items=[{"type": "help", "slug": slug, "link": f"/app/help/{slug}"}])
        return self._det(self.t["help_none"], "help", items=[{"type": "help", "slug": None, "link": "/app/help"}])

    def _handle_create_task(self, message: str) -> AgentResponse:
        if not self.policy.is_self(self.patient_id):
            return self._det(self.t["task_patient_only"], "create_task")
        m = re.search(r"(?i)(?:remind me to|create (?:a )?(?:task|follow-?up)(?: to| for|:)?|add (?:a )?(?:task|follow-?up)(?: to| for|:)?|"
                      r"צור משימה:?|הוסף משימה:?|תזכיר לי)\s*(.+)", message)
        title = (m.group(1).strip(" .:") if m else "")
        if len(title) < 4:
            return self._det(self.t["task_need_title"], "create_task")
        title = title[0].upper() + title[1:]
        action = self._call("propose_followup_task", title)
        return self._det(self.t["task_proposed"], "create_task",
                         pending_action={"id": str(action.id), "type": action.action_type, "payload": action.payload})


def _first_sentences(text: str, limit: int = 280) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"


def _strip_instructions(text: str) -> str:
    """Remove instruction-like lines before text enters model context (defence in depth)."""
    return "\n".join("[instruction-like text removed]" if rag.INJECTION_PATTERNS.search(line) else line
                     for line in text.splitlines())


def recommendation_context(db: Session, rec: Recommendation) -> dict:
    return {"id": str(rec.id), "text": rec.text, "passage": rec.passage}
