"""Global Care Connect: consultations, meeting access, notes, summaries and handoffs."""
import secrets
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.api.serializers import consultation_out, summary_out, user_brief
from app.authz import AccessPolicy
from app.config import get_settings
from app.db import get_db
from app.deps import require_clinical, require_patient
from app.models import (
    ConsentGrant, Consultation, ConsultationNote, ConsultationParticipant, ConsultationSummary, Document, Handoff,
    JourneyEvent, Recommendation, SummaryApproval, User, utcnow,
)
from app.observability import log_event, metrics
from app.security.ratelimit import limiter
from app.security.storage import get_storage
from app.services import rag
from app.services.care_gaps import evaluate_patient
from app.services.extraction import find_terms
from app.services.meetings import create_join_token
from app.services.notifications import notify

import hashlib
import logging

router = APIRouter(tags=["consultations"])
log = logging.getLogger(__name__)
JOIN_EARLY = timedelta(hours=2)
JOIN_LATE = timedelta(hours=4)


def _professionals(c: Consultation) -> list[ConsultationParticipant]:
    return [p for p in c.participants if p.meeting_role == "professional" and p.invite_status != "declined"]


def _notify_participants(db: Session, c: Consultation, actor: User, title: str, body: str | None = None) -> None:
    for p in c.participants:
        if p.user_id != actor.id and p.invite_status != "declined":
            notify(db, p.user_id, "consultation_update", title, body, f"/app/consultations/{c.id}")


# ------------------------------------------------------------------ scheduling
class ConsultationIn(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    purpose: str | None = Field(None, max_length=3000)
    scheduled_start: datetime
    duration_minutes: int = Field(45, ge=10, le=240)
    professional_ids: list[uuid.UUID] = Field(min_length=1, max_length=6)
    document_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)


class ConsultationPatch(BaseModel):
    title: str | None = Field(None, min_length=3, max_length=300)
    purpose: str | None = Field(None, max_length=3000)
    scheduled_start: datetime | None = None
    duration_minutes: int | None = Field(None, ge=10, le=240)


@router.get("/consultations")
def my_consultations(db: Session = Depends(get_db), user: User = Depends(require_clinical)):
    rows = db.execute(select(Consultation).join(ConsultationParticipant).where(
        ConsultationParticipant.user_id == user.id, ConsultationParticipant.invite_status != "declined")
        .order_by(Consultation.scheduled_start.desc())).scalars().unique().all()
    return [consultation_out(c, user) for c in rows]


@router.post("/consultations", status_code=201)
def create_consultation(body: ConsultationIn, db: Session = Depends(get_db), user: User = Depends(require_patient)):
    if body.scheduled_start.tzinfo is None:
        raise HTTPException(422, "scheduled_start must include a timezone offset")
    pros = []
    for pid in dict.fromkeys(body.professional_ids):
        p = db.get(User, pid)
        if not p or p.role != "professional" or not p.is_active or not p.professional \
                or p.professional.verification_status != "simulated_verified":
            raise HTTPException(422, "All invitees must be active, verified professionals.")
        pros.append(p)
    docs = []
    if body.document_ids:
        docs = db.execute(select(Document).where(Document.id.in_(body.document_ids), Document.patient_id == user.id,
                                                 Document.deleted_at.is_(None))).scalars().all()
        if len(docs) != len(set(body.document_ids)):
            raise HTTPException(404, "Document not found")
    c = Consultation(patient_id=user.id, title=body.title, purpose=body.purpose, scheduled_start=body.scheduled_start,
                     duration_minutes=body.duration_minutes, room_name="hb-" + secrets.token_hex(12), created_by=user.id)
    c.participants.append(ConsultationParticipant(user_id=user.id, meeting_role="patient", invite_status="accepted"))
    for p in pros:
        c.participants.append(ConsultationParticipant(user_id=p.id, meeting_role="professional"))
    c.documents = list(docs)
    db.add(c)
    db.flush()
    audit.record(db, "consultation.create", actor=user, resource_type="consultation", resource_id=c.id, patient_id=user.id,
                 detail={"professionals": len(pros), "documents": len(docs)})
    for p in pros:
        notify(db, p.id, "consultation_update", f"Consultation invitation from {user.full_name}",
               f"{body.title} — {body.scheduled_start.isoformat()}", f"/app/consultations/{c.id}")
    evaluate_patient(db, user.id)
    db.commit()
    db.refresh(c)
    return consultation_out(c, user)


@router.get("/consultations/{cid}")
def get_consultation(cid: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_clinical)):
    policy = AccessPolicy(db, user)
    c = policy.get_consultation(cid)
    out = consultation_out(c, user)
    accessible = policy.accessible_document_ids(c.patient_id)
    out["documents"] = [{"id": str(d.id), "title": d.title, "category": d.category, "accessible": d.id in accessible}
                        for d in c.documents if d.deleted_at is None]
    notes = db.execute(select(ConsultationNote).where(ConsultationNote.consultation_id == c.id)
                       .order_by(ConsultationNote.created_at)).scalars().all()
    out["notes"] = [{"id": str(n.id), "author": user_brief(n.author), "content": n.content,
                     "created_at": n.created_at.isoformat()} for n in notes]
    out["can_manage"] = policy.is_self(c.patient_id)
    out["is_professional_participant"] = policy.is_professional_participant(c)
    out["join_window"] = {"opens": (c.scheduled_start - JOIN_EARLY).isoformat(),
                          "closes": (c.scheduled_start + timedelta(minutes=c.duration_minutes) + JOIN_LATE).isoformat()}
    return out


@router.patch("/consultations/{cid}")
def update_consultation(cid: uuid.UUID, body: ConsultationPatch, db: Session = Depends(get_db),
                        user: User = Depends(require_patient)):
    policy = AccessPolicy(db, user)
    c = policy.get_consultation(cid)
    policy.require_self(c.patient_id, "consultation.update")
    if c.status in ("completed", "cancelled"):
        raise HTTPException(409, "This consultation can no longer be changed.")
    changes = body.model_dump(exclude_unset=True)
    if changes.get("scheduled_start") and changes["scheduled_start"].tzinfo is None:
        raise HTTPException(422, "scheduled_start must include a timezone offset")
    for k, v in changes.items():
        setattr(c, k, v)
    if "scheduled_start" in changes:
        c.reminder_sent = False
    audit.record(db, "consultation.update", actor=user, resource_type="consultation", resource_id=c.id,
                 patient_id=c.patient_id, detail={"fields": sorted(changes)})
    _notify_participants(db, c, user, f"Consultation updated: {c.title}", c.scheduled_start.isoformat())
    db.commit()
    return consultation_out(c, user)


class RespondIn(BaseModel):
    decision: str = Field(pattern="^(accept|decline)$")


@router.post("/consultations/{cid}/respond")
def respond(cid: uuid.UUID, body: RespondIn, db: Session = Depends(get_db), user: User = Depends(require_clinical)):
    policy = AccessPolicy(db, user)
    c = policy.get_consultation(cid)
    me = next(p for p in c.participants if p.user_id == user.id)
    if me.meeting_role != "professional":
        raise HTTPException(409, "Only invited professionals respond to invitations.")
    me.invite_status = "accepted" if body.decision == "accept" else "declined"
    audit.record(db, f"consultation.{body.decision}", actor=user, resource_type="consultation", resource_id=c.id,
                 patient_id=c.patient_id)
    notify(db, c.patient_id, "consultation_update", f"{user.full_name} {me.invite_status} your consultation invitation",
           c.title, f"/app/consultations/{c.id}")
    db.commit()
    return consultation_out(c, user)


@router.post("/consultations/{cid}/cancel")
def cancel(cid: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_patient)):
    policy = AccessPolicy(db, user)
    c = policy.get_consultation(cid)
    policy.require_self(c.patient_id, "consultation.cancel")
    if c.status == "completed":
        raise HTTPException(409, "Completed consultations cannot be cancelled.")
    c.status = "cancelled"
    audit.record(db, "consultation.cancel", actor=user, resource_type="consultation", resource_id=c.id, patient_id=c.patient_id)
    _notify_participants(db, c, user, f"Consultation cancelled: {c.title}")
    evaluate_patient(db, c.patient_id)
    db.commit()
    return consultation_out(c, user)


class DocsIn(BaseModel):
    document_ids: list[uuid.UUID] = Field(min_length=1, max_length=50)
    days: int = Field(14, ge=1, le=90)


@router.post("/consultations/{cid}/documents")
def attach_documents(cid: uuid.UUID, body: DocsIn, db: Session = Depends(get_db), user: User = Depends(require_patient)):
    """Attach documents to the consultation agenda. Attaching does NOT grant access."""
    policy = AccessPolicy(db, user)
    c = policy.get_consultation(cid)
    policy.require_self(c.patient_id, "consultation.documents")
    docs = db.execute(select(Document).where(Document.id.in_(body.document_ids), Document.patient_id == user.id,
                                             Document.deleted_at.is_(None))).scalars().all()
    if len(docs) != len(set(body.document_ids)):
        raise HTTPException(404, "Document not found")
    for d in docs:
        if d not in c.documents:
            c.documents.append(d)
    audit.record(db, "consultation.documents", actor=user, resource_type="consultation", resource_id=c.id,
                 patient_id=c.patient_id, detail={"added": len(docs)})
    evaluate_patient(db, c.patient_id)
    db.commit()
    return get_consultation(cid, db, user)


@router.post("/consultations/{cid}/share")
def share_with_participants(cid: uuid.UUID, body: DocsIn, db: Session = Depends(get_db), user: User = Depends(require_patient)):
    """Patient explicitly grants every professional participant access to the selected documents."""
    policy = AccessPolicy(db, user)
    c = policy.get_consultation(cid)
    policy.require_self(c.patient_id, "consent.grant")
    docs = db.execute(select(Document).where(Document.id.in_(body.document_ids), Document.patient_id == user.id,
                                             Document.deleted_at.is_(None))).scalars().all()
    if len(docs) != len(set(body.document_ids)):
        raise HTTPException(404, "Document not found")
    now = utcnow()
    created = 0
    for p in _professionals(c):
        g = ConsentGrant(patient_id=user.id, grantee_id=p.user_id, purpose=f"Consultation: {c.title}"[:300],
                         consultation_id=c.id, starts_at=now, expires_at=now + timedelta(days=body.days))
        g.documents = list(docs)
        db.add(g)
        db.flush()
        created += 1
        audit.record(db, "consent.grant", actor=user, resource_type="grant", resource_id=g.id, patient_id=user.id,
                     detail={"grantee_id": str(p.user_id), "documents": len(docs), "days": body.days,
                             "consultation_id": str(c.id)})
        notify(db, p.user_id, "sharing_invitation", f"{user.full_name} shared {len(docs)} document(s) for '{c.title}'",
               None, f"/app/consultations/{c.id}")
    for d in docs:
        if d not in c.documents:
            c.documents.append(d)
    evaluate_patient(db, user.id)
    db.commit()
    return {"grants_created": created}


# ------------------------------------------------------------------ meeting access
@router.post("/consultations/{cid}/join")
def join(cid: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_clinical)):
    if not limiter.hit(f"join:{user.id}", 20, 60):
        raise HTTPException(429, "Too many join attempts.")
    policy = AccessPolicy(db, user)
    c = policy.get_consultation(cid, "meeting.join")
    if c.status not in ("scheduled", "in_progress"):
        audit.record_denied(db, "meeting.join", user, resource_type="consultation", resource_id=c.id,
                            patient_id=c.patient_id, detail={"reason": c.status})
        raise HTTPException(409, f"This consultation is {c.status}.")
    now = utcnow()
    opens = c.scheduled_start - JOIN_EARLY
    closes = c.scheduled_start + timedelta(minutes=c.duration_minutes) + JOIN_LATE
    if not (opens <= now <= closes):
        audit.record_denied(db, "meeting.join", user, resource_type="consultation", resource_id=c.id,
                            patient_id=c.patient_id, detail={"reason": "outside_window"})
        raise HTTPException(409, "The meeting room is only open from 2 hours before the start until 4 hours after the end. "
                                 "The patient can reschedule the consultation.")
    me = next(p for p in c.participants if p.user_id == user.id)
    if me.meeting_role == "professional" and me.invite_status == "invited":
        me.invite_status = "accepted"
    try:
        token = create_join_token(c.room_name, str(user.id), user.full_name)
    except RuntimeError:
        raise HTTPException(503, "Video service is not configured.")
    me.last_token_at = now
    if c.status == "scheduled":
        c.status = "in_progress"
    audit.record(db, "meeting.token_issued", actor=user, resource_type="consultation", resource_id=c.id,
                 patient_id=c.patient_id, detail={"ttl_seconds": get_settings().livekit_token_ttl_seconds})
    db.commit()
    metrics.incr("meeting.tokens_issued")
    return {"token": token, "url": get_settings().livekit_public_url, "room": c.room_name, "identity": str(user.id),
            "expires_in": get_settings().livekit_token_ttl_seconds}


class PresenceIn(BaseModel):
    event: str = Field(pattern="^(joined|left|connection_error|reconnecting|reconnected)$")
    detail: str | None = Field(None, max_length=200)


@router.post("/consultations/{cid}/presence")
def presence(cid: uuid.UUID, body: PresenceIn, db: Session = Depends(get_db), user: User = Depends(require_clinical)):
    """Client-side connection diagnostics (no media or chat content)."""
    policy = AccessPolicy(db, user)
    c = policy.get_consultation(cid)
    me = next(p for p in c.participants if p.user_id == user.id)
    if body.event == "joined":
        me.joined_at, me.left_at = utcnow(), None
    elif body.event == "left":
        me.left_at = utcnow()
    metrics.incr(f"meeting.{body.event}")
    log_event(log, "meeting.presence", consultation_id=str(c.id), event=body.event, error=body.detail)
    audit.record(db, f"meeting.{body.event}", actor=user, resource_type="consultation", resource_id=c.id,
                 patient_id=c.patient_id, detail={"detail": body.detail} if body.detail else {})
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ notes & completion
class NoteIn(BaseModel):
    content: str = Field(min_length=2, max_length=5000)


@router.post("/consultations/{cid}/notes", status_code=201)
def add_note(cid: uuid.UUID, body: NoteIn, db: Session = Depends(get_db), user: User = Depends(require_clinical)):
    policy = AccessPolicy(db, user)
    c = policy.get_consultation(cid)
    if not policy.is_professional_participant(c):
        raise HTTPException(403, "Only participating professionals add consultation notes.")
    n = ConsultationNote(consultation_id=c.id, author_id=user.id, content=body.content.strip())
    db.add(n)
    db.flush()
    audit.record(db, "consultation.note", actor=user, resource_type="consultation", resource_id=c.id, patient_id=c.patient_id)
    db.commit()
    return {"id": str(n.id), "author": user_brief(user), "content": n.content, "created_at": n.created_at.isoformat()}


def _consultation_event(db: Session, c: Consultation) -> JourneyEvent:
    ev = db.execute(select(JourneyEvent).where(JourneyEvent.consultation_id == c.id)).scalars().first()
    if ev:
        return ev
    countries = {p.user.country for p in _professionals(c)}
    pros = ", ".join(p.user.full_name for p in _professionals(c))
    org_id = next((p.user.professional.organization_id for p in _professionals(c) if p.user.professional), None)
    ev = JourneyEvent(patient_id=c.patient_id, event_type="international_consultation" if countries - {"IL"} else "specialist_consultation",
                      title=c.title, description=f"HealthBridge video consultation with {pros}", organization_id=org_id,
                      occurred_at=c.scheduled_start, verification_status="unverified", provenance="consultation",
                      provenance_detail="Recorded from a HealthBridge consultation; awaiting an approved summary",
                      consultation_id=c.id)
    db.add(ev)
    db.flush()
    return ev


@router.post("/consultations/{cid}/complete")
def complete(cid: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_clinical)):
    policy = AccessPolicy(db, user)
    c = policy.get_consultation(cid)
    if not (policy.is_self(c.patient_id) or policy.is_professional_participant(c)):
        raise HTTPException(403, "Not permitted")
    if c.status not in ("scheduled", "in_progress"):
        raise HTTPException(409, f"This consultation is {c.status}.")
    c.status, c.completed_at = "completed", utcnow()
    _consultation_event(db, c)
    audit.record(db, "consultation.complete", actor=user, resource_type="consultation", resource_id=c.id, patient_id=c.patient_id)
    _notify_participants(db, c, user, f"Consultation completed: {c.title}", "A summary can now be drafted and approved.")
    db.flush()
    evaluate_patient(db, c.patient_id)
    db.commit()
    return consultation_out(c, user)


# ------------------------------------------------------------------ summaries
class ObservationIn(BaseModel):
    text: str = Field(min_length=2, max_length=3000)


class FollowupIn(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    description: str | None = Field(None, max_length=1000)


class SummaryIn(BaseModel):
    discussion: str = Field(min_length=10, max_length=20000)
    observation: str | None = Field(None, max_length=3000)
    proposed_followups: list[FollowupIn] = Field(default_factory=list, max_length=20)
    referenced_document_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)
    ai_generated_draft: bool = False


def _summaries(db: Session, cid: uuid.UUID) -> list[ConsultationSummary]:
    return list(db.execute(select(ConsultationSummary).where(ConsultationSummary.consultation_id == cid)
                           .order_by(ConsultationSummary.version.desc())).scalars())


@router.get("/consultations/{cid}/summaries")
def list_summaries(cid: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_clinical)):
    c = AccessPolicy(db, user).get_consultation(cid)
    pros = [p.user_id for p in _professionals(c)]
    return [summary_out(s, pros) for s in _summaries(db, cid)]


@router.post("/consultations/{cid}/summaries/draft")
def draft_summary(cid: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_clinical)):
    """Assemble a draft from the professionals' own notes. Deterministic; adds no clinical content."""
    policy = AccessPolicy(db, user)
    c = policy.get_consultation(cid)
    if not policy.is_professional_participant(c):
        raise HTTPException(403, "Only participating professionals draft summaries.")
    notes = db.execute(select(ConsultationNote).where(ConsultationNote.consultation_id == c.id)
                       .order_by(ConsultationNote.created_at)).scalars().all()
    lines = [f"Consultation: {c.title} ({c.scheduled_start.date().isoformat()})",
             "Participants: " + ", ".join(p.user.full_name for p in c.participants if p.invite_status != "declined"), ""]
    lines += [f"- {n.author.full_name}: {n.content}" for n in notes] or ["- (No consultation notes were recorded.)"]
    return {"discussion": "\n".join(lines), "referenced_document_ids": [str(d.id) for d in c.documents],
            "proposed_followups": [], "ai_generated_draft": True,
            "label": "Automatically assembled draft from consultation notes. It contains only what professionals wrote "
                     "and must be reviewed, edited and approved by the participating professionals."}


def _check_referenced_docs(policy: AccessPolicy, c: Consultation, ids: list[uuid.UUID]) -> None:
    accessible = policy.accessible_document_ids(c.patient_id)
    if any(i not in accessible for i in ids):
        raise HTTPException(422, "You can only reference documents that are shared with you.")


@router.post("/consultations/{cid}/summaries", status_code=201)
def create_summary(cid: uuid.UUID, body: SummaryIn, db: Session = Depends(get_db), user: User = Depends(require_clinical)):
    policy = AccessPolicy(db, user)
    c = policy.get_consultation(cid)
    if not policy.is_professional_participant(c):
        raise HTTPException(403, "Only participating professionals author summaries.")
    if c.status != "completed":
        raise HTTPException(409, "Complete the consultation before writing its summary.")
    _check_referenced_docs(policy, c, body.referenced_document_ids)
    existing = _summaries(db, cid)
    prev = existing[0] if existing else None
    observations = list(prev.observations) if prev else []
    if body.observation:
        observations = [o for o in observations if o.get("author_id") != str(user.id)]
        observations.append({"author_id": str(user.id), "author_name": user.full_name, "text": body.observation.strip()})
    s = ConsultationSummary(consultation_id=c.id, version=(prev.version + 1) if prev else 1, status="pending_approval",
                            discussion=body.discussion.strip(), observations=observations,
                            proposed_followups=[f.model_dump() for f in body.proposed_followups],
                            referenced_document_ids=[str(i) for i in body.referenced_document_ids],
                            ai_generated_draft=body.ai_generated_draft, author_id=user.id)
    for old in existing:
        if old.status in ("draft", "pending_approval"):
            old.status = "superseded"
    db.add(s)
    db.flush()
    audit.record(db, "summary.create", actor=user, resource_type="summary", resource_id=s.id, patient_id=c.patient_id,
                 detail={"version": s.version, "ai_draft": s.ai_generated_draft})
    _notify_participants(db, c, user, f"Summary v{s.version} awaiting approval: {c.title}")
    db.commit()
    return summary_out(s, [p.user_id for p in _professionals(c)])


def _summary_ctx(db: Session, user: User, sid: uuid.UUID) -> tuple[ConsultationSummary, Consultation, AccessPolicy]:
    s = db.get(ConsultationSummary, sid)
    if not s:
        raise HTTPException(404, "Not found")
    policy = AccessPolicy(db, user)
    c = policy.get_consultation(s.consultation_id, "summary.view")
    return s, c, policy


@router.post("/summaries/{sid}/observations", status_code=201)
def add_observation(sid: uuid.UUID, body: ObservationIn, db: Session = Depends(get_db), user: User = Depends(require_clinical)):
    """Adding a professional observation creates a new version (previous approvals do not carry over)."""
    s, c, policy = _summary_ctx(db, user, sid)
    if not policy.is_professional_participant(c):
        raise HTTPException(403, "Only participating professionals add observations.")
    if s.status not in ("pending_approval", "draft"):
        raise HTTPException(409, "Observations can be added only to the current draft.")
    return create_summary(c.id, SummaryIn(
        discussion=s.discussion, observation=body.text,
        proposed_followups=[FollowupIn(**f) for f in s.proposed_followups],
        referenced_document_ids=[uuid.UUID(x) for x in s.referenced_document_ids],
        ai_generated_draft=s.ai_generated_draft), db, user)


class DecisionIn(BaseModel):
    comment: str | None = Field(None, max_length=2000)


def _render_summary(c: Consultation, s: ConsultationSummary) -> str:
    lines = ["Consultation summary (HealthBridge)", f"Consultation: {c.title}",
             f"Date: {c.scheduled_start.date().isoformat()}", f"Version: {s.version}",
             "Participants: " + ", ".join(f"{p.user.full_name}" + (f" ({p.user.professional.specialty}, {p.user.country})"
                                                                  if p.user.professional else " (patient)")
                                          for p in c.participants if p.invite_status != "declined"),
             "", "Discussion:", s.discussion, ""]
    if s.observations:
        lines.append("Professional observations:")
        lines += [f"- {o['author_name']}: {o['text']}" for o in s.observations]
        lines.append("")
    if s.proposed_followups:
        lines.append("Recommendations:")
        lines += [f"- {f['title']}" + (f" — {f['description']}" if f.get("description") else "") for f in s.proposed_followups]
        lines.append("")
    lines.append("Approved by: " + ", ".join(a.professional.full_name for a in s.approvals if a.decision == "approved"))
    if s.ai_generated_draft:
        lines.append("Note: this summary started from an automatically assembled draft and was reviewed and approved by the professionals above.")
    return "\n".join(lines)


def _finalize(db: Session, c: Consultation, s: ConsultationSummary) -> None:
    """All participating professionals approved: publish as a document, link to the journey, add follow-ups."""
    s.status, s.approved_at = "approved", utcnow()
    for old in _summaries(db, c.id):
        if old.id != s.id and old.status == "approved":
            old.status = "superseded"
    text = _render_summary(c, s)
    data = text.encode()
    doc = Document(patient_id=c.patient_id, uploaded_by=s.author_id, title=f"Consultation summary: {c.title}"[:300],
                   category="consultation_summary", original_filename=f"consultation-summary-v{s.version}.txt",
                   mime_type="text/plain", size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                   storage_key=get_storage().put(data), status="processed", extracted_text=text,
                   text_sha256=hashlib.sha256(data).hexdigest(), document_date=c.scheduled_start.date(),
                   author_name=s.author.full_name, source_detected="HealthBridge consultation", language="en",
                   lineage_id=uuid.uuid4(), processed_at=utcnow(),
                   organization_id=next((p.user.professional.organization_id for p in _professionals(c) if p.user.professional), None))
    db.add(doc)
    db.flush()
    rag.index_document(db, doc)
    s.document_id = doc.id
    ev = _consultation_event(db, c)
    ev.documents.append(doc)
    ev.verification_status = "professional_confirmed"
    ev.provenance_detail = f"Summary v{s.version} approved by all participating professionals"
    for f in s.proposed_followups:
        rtext = f["title"] + (f" — {f['description']}" if f.get("description") else "")
        from app.services.extraction import classify_kind

        db.add(Recommendation(patient_id=c.patient_id, document_id=doc.id, event_id=ev.id, kind=classify_kind(rtext),
                              text=rtext[:2000], passage=rtext[:2000], source="professional", review_status="confirmed",
                              proposed_by=s.author_id, documented_at=c.scheduled_start.date(),
                              target=",".join(find_terms(rtext))))
    notify(db, c.patient_id, "consultation_update", f"Consultation summary approved: {c.title}",
           "Please review and acknowledge it.", f"/app/consultations/{c.id}")


@router.post("/summaries/{sid}/approve")
def approve(sid: uuid.UUID, body: DecisionIn, db: Session = Depends(get_db), user: User = Depends(require_clinical)):
    s, c, policy = _summary_ctx(db, user, sid)
    if not policy.is_professional_participant(c):
        raise HTTPException(403, "Only participating professionals approve summaries.")
    if s.status != "pending_approval":
        raise HTTPException(409, f"This version is {s.status}.")
    a = next((x for x in s.approvals if x.professional_id == user.id), None)
    if a:
        a.decision, a.comment, a.created_at = "approved", body.comment, utcnow()
    else:
        s.approvals.append(SummaryApproval(professional_id=user.id, decision="approved", comment=body.comment))
    db.flush()
    db.refresh(s)
    audit.record(db, "summary.approve", actor=user, resource_type="summary", resource_id=s.id, patient_id=c.patient_id,
                 detail={"version": s.version})
    required = {p.user_id for p in _professionals(c)}
    approved = {x.professional_id for x in s.approvals if x.decision == "approved"}
    if required <= approved:
        _finalize(db, c, s)
        audit.record(db, "summary.approved_all", resource_type="summary", resource_id=s.id, patient_id=c.patient_id,
                     detail={"version": s.version, "approvers": len(approved)})
        db.flush()
        evaluate_patient(db, c.patient_id)
    db.commit()
    return summary_out(s, list(required))


@router.post("/summaries/{sid}/request-changes")
def request_changes(sid: uuid.UUID, body: DecisionIn, db: Session = Depends(get_db), user: User = Depends(require_clinical)):
    s, c, policy = _summary_ctx(db, user, sid)
    if not policy.is_professional_participant(c):
        raise HTTPException(403, "Only participating professionals review summaries.")
    if s.status != "pending_approval":
        raise HTTPException(409, f"This version is {s.status}.")
    if not body.comment:
        raise HTTPException(422, "Please describe the requested changes.")
    a = next((x for x in s.approvals if x.professional_id == user.id), None)
    if a:
        a.decision, a.comment, a.created_at = "changes_requested", body.comment, utcnow()
    else:
        s.approvals.append(SummaryApproval(professional_id=user.id, decision="changes_requested", comment=body.comment))
    audit.record(db, "summary.request_changes", actor=user, resource_type="summary", resource_id=s.id, patient_id=c.patient_id)
    _notify_participants(db, c, user, f"Changes requested on summary v{s.version}: {c.title}")
    db.commit()
    db.refresh(s)
    return summary_out(s, [p.user_id for p in _professionals(c)])


@router.post("/summaries/{sid}/acknowledge")
def acknowledge(sid: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_patient)):
    s, c, policy = _summary_ctx(db, user, sid)
    policy.require_self(c.patient_id, "summary.acknowledge")
    if s.status != "approved":
        raise HTTPException(409, "Only approved summaries can be acknowledged.")
    s.patient_acknowledged_at = s.patient_acknowledged_at or utcnow()
    audit.record(db, "summary.acknowledge", actor=user, resource_type="summary", resource_id=s.id, patient_id=c.patient_id)
    db.commit()
    return summary_out(s, [p.user_id for p in _professionals(c)])


# ------------------------------------------------------------------ handoffs
class HandoffIn(BaseModel):
    to_user_id: uuid.UUID
    note: str | None = Field(None, max_length=2000)
    days: int = Field(30, ge=1, le=180)


def _share_handoff(db: Session, h: Handoff, s: ConsultationSummary, days: int, actor: User) -> None:
    now = utcnow()
    g = ConsentGrant(patient_id=h.patient_id, grantee_id=h.to_user_id, purpose="Consultation summary handoff",
                     starts_at=now, expires_at=now + timedelta(days=days))
    g.documents = [db.get(Document, s.document_id)]
    db.add(g)
    db.flush()
    h.grant_id, h.status, h.shared_at = g.id, "shared", now
    audit.record(db, "consent.grant", actor=actor, resource_type="grant", resource_id=g.id, patient_id=h.patient_id,
                 detail={"grantee_id": str(h.to_user_id), "handoff_id": str(h.id), "days": days})
    notify(db, h.to_user_id, "handoff", "A consultation summary was handed off to you",
           h.note, "/app/pro")


@router.post("/summaries/{sid}/handoffs", status_code=201)
def create_handoff(sid: uuid.UUID, body: HandoffIn, db: Session = Depends(get_db), user: User = Depends(require_clinical)):
    s, c, policy = _summary_ctx(db, user, sid)
    if not (policy.is_self(c.patient_id) or policy.is_professional_participant(c)):
        raise HTTPException(403, "Not permitted")
    if s.status != "approved" or not s.document_id:
        raise HTTPException(409, "Only approved summaries can be handed off.")
    to = db.get(User, body.to_user_id)
    if not to or to.role != "professional" or not to.professional or to.professional.verification_status != "simulated_verified":
        raise HTTPException(422, "Recipient must be a verified professional.")
    h = Handoff(patient_id=c.patient_id, summary_id=s.id, from_user_id=user.id, to_user_id=to.id, note=body.note)
    db.add(h)
    db.flush()
    if policy.is_self(c.patient_id):
        _share_handoff(db, h, s, body.days, user)
    else:
        notify(db, c.patient_id, "handoff", f"{user.full_name} asks to share a summary with {to.full_name}",
               "Nothing is shared until you approve.", "/app/sharing")
    audit.record(db, "handoff.create", actor=user, resource_type="handoff", resource_id=h.id, patient_id=c.patient_id,
                 detail={"to": str(to.id), "status": h.status})
    db.flush()
    evaluate_patient(db, c.patient_id)
    db.commit()
    return _handoff_out(db, h)


def _handoff_out(db: Session, h: Handoff) -> dict:
    s = db.get(ConsultationSummary, h.summary_id)
    c = db.get(Consultation, s.consultation_id) if s else None
    return {"id": str(h.id), "patient_id": str(h.patient_id), "summary_id": str(h.summary_id),
            "consultation": {"id": str(c.id), "title": c.title} if c else None,
            "summary_document_id": str(s.document_id) if s and s.document_id else None,
            "from": user_brief(db.get(User, h.from_user_id)), "to": user_brief(db.get(User, h.to_user_id)),
            "note": h.note, "status": h.status, "created_at": h.created_at.isoformat(),
            "shared_at": h.shared_at.isoformat() if h.shared_at else None,
            "acknowledged_at": h.acknowledged_at.isoformat() if h.acknowledged_at else None}


@router.get("/handoffs")
def list_handoffs(db: Session = Depends(get_db), user: User = Depends(require_clinical)):
    if user.role == "patient":
        stmt = select(Handoff).where(Handoff.patient_id == user.id)
    else:
        stmt = select(Handoff).where((Handoff.to_user_id == user.id) | (Handoff.from_user_id == user.id))
    return [_handoff_out(db, h) for h in db.execute(stmt.order_by(Handoff.created_at.desc())).scalars()]


class HandoffDecision(BaseModel):
    decision: str = Field(pattern="^(approve|decline)$")
    days: int = Field(30, ge=1, le=180)


@router.post("/handoffs/{hid}/decide")
def decide_handoff(hid: uuid.UUID, body: HandoffDecision, db: Session = Depends(get_db), user: User = Depends(require_patient)):
    h = db.get(Handoff, hid)
    if not h:
        raise HTTPException(404, "Not found")
    AccessPolicy(db, user).require_self(h.patient_id, "handoff.decide")
    if h.status != "pending_patient_approval":
        raise HTTPException(409, f"This handoff is {h.status}.")
    if body.decision == "approve":
        _share_handoff(db, h, db.get(ConsultationSummary, h.summary_id), body.days, user)
    else:
        h.status = "declined"
    audit.record(db, f"handoff.{body.decision}", actor=user, resource_type="handoff", resource_id=h.id, patient_id=h.patient_id)
    db.flush()
    evaluate_patient(db, h.patient_id)
    db.commit()
    return _handoff_out(db, h)


@router.post("/handoffs/{hid}/acknowledge")
def acknowledge_handoff(hid: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_clinical)):
    h = db.get(Handoff, hid)
    if not h or h.to_user_id != user.id:
        raise HTTPException(404, "Not found")
    if h.status != "shared":
        raise HTTPException(409, "Nothing has been shared yet.")
    h.acknowledged_at = h.acknowledged_at or utcnow()
    audit.record(db, "handoff.acknowledge", actor=user, resource_type="handoff", resource_id=h.id, patient_id=h.patient_id)
    notify(db, h.patient_id, "handoff", f"{user.full_name} acknowledged the handoff", None, "/app/sharing")
    db.flush()
    evaluate_patient(db, h.patient_id)
    db.commit()
    return _handoff_out(db, h)
