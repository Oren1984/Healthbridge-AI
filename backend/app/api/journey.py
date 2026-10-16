import re
import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app import audit
from app.api.serializers import event_out, recommendation_out, task_out, user_brief
from app.authz import AccessPolicy
from app.db import get_db
from app.deps import require_clinical
from app.models import ConsentGrant, FollowUpTask, JourneyEvent, Organization, Recommendation, User, utcnow
from app.services.care_gaps import evaluate_patient
from app.services.extraction import find_terms

router = APIRouter(tags=["journey"])

EVENT_TYPES = ["hmo_consultation", "specialist_consultation", "hospital_visit", "lab_test", "imaging", "referral",
               "discharge", "follow_up_appointment", "international_consultation", "other"]
REC_KINDS = ["follow_up_visit", "lab_test", "imaging", "referral", "other"]


@router.get("/patients/{patient_id}/journey")
def list_journey(patient_id: uuid.UUID, type: str | None = Query(None, max_length=40),
                 q: str | None = Query(None, max_length=200), date_from: date | None = None,
                 date_to: date | None = None, organization_id: uuid.UUID | None = None,
                 db: Session = Depends(get_db), user: User = Depends(require_clinical)):
    policy = AccessPolicy(db, user)
    policy.require_section(patient_id, "journey")
    stmt = select(JourneyEvent).where(JourneyEvent.patient_id == patient_id)
    if type:
        stmt = stmt.where(JourneyEvent.event_type == type)
    if organization_id:
        stmt = stmt.where(JourneyEvent.organization_id == organization_id)
    if date_from:
        stmt = stmt.where(JourneyEvent.occurred_at >= datetime.combine(date_from, datetime.min.time()).astimezone())
    if date_to:
        stmt = stmt.where(JourneyEvent.occurred_at <= datetime.combine(date_to, datetime.max.time()).astimezone())
    if q:
        like = "%" + re.sub(r"([%_\\])", r"\\\1", q) + "%"
        stmt = stmt.outerjoin(Organization, Organization.id == JourneyEvent.organization_id).where(or_(
            JourneyEvent.title.ilike(like, escape="\\"), JourneyEvent.description.ilike(like, escape="\\"),
            Organization.name.ilike(like, escape="\\")))
    events = db.execute(stmt.order_by(JourneyEvent.occurred_at.desc())).scalars().unique().all()
    visible = policy.accessible_document_ids(patient_id)
    if not policy.is_self(patient_id):
        audit.record(db, "journey.view", actor=user, resource_type="patient", resource_id=patient_id, patient_id=patient_id)
        db.commit()
    return [event_out(e, visible) for e in events]


@router.get("/journey/{event_id}")
def get_event(event_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_clinical)):
    e = db.get(JourneyEvent, event_id)
    if not e:
        raise HTTPException(404, "Not found")
    policy = AccessPolicy(db, user)
    if not policy.can_view_patient_section(e.patient_id, "journey"):
        raise policy.deny("journey.view", "event", event_id, e.patient_id)
    visible = policy.accessible_document_ids(e.patient_id)
    out = event_out(e, visible)
    recs = db.execute(select(Recommendation).where(or_(
        Recommendation.event_id == e.id, Recommendation.document_id.in_([d.id for d in e.documents])))).scalars().all()
    out["recommendations"] = [recommendation_out(r) for r in recs if r.document_id is None or r.document_id in visible]
    if policy.is_self(e.patient_id):
        # Who can currently see this event or its documents.
        now = utcnow()
        grants = db.execute(select(ConsentGrant).where(
            ConsentGrant.patient_id == e.patient_id, ConsentGrant.revoked_at.is_(None),
            ConsentGrant.starts_at <= now, ConsentGrant.expires_at > now)).scalars().all()
        doc_ids = {d.id for d in e.documents}
        viewers = {}
        for g in grants:
            sees_docs = bool(doc_ids & {d.id for d in g.documents}) or any(d.category in (g.categories or []) for d in e.documents)
            if g.include_journey or sees_docs:
                viewers[g.grantee_id] = {**user_brief(g.grantee), "via": "journey" if g.include_journey else "documents",
                                         "expires_at": g.expires_at.isoformat()}
        out["authorized_viewers"] = list(viewers.values())
    return out


class EventIn(BaseModel):
    event_type: str
    title: str = Field(min_length=2, max_length=300)
    description: str | None = Field(None, max_length=5000)
    organization_id: uuid.UUID | None = None
    occurred_at: datetime


class EventPatch(BaseModel):
    event_type: str | None = None
    title: str | None = Field(None, min_length=2, max_length=300)
    description: str | None = Field(None, max_length=5000)
    organization_id: uuid.UUID | None = None
    occurred_at: datetime | None = None


def _validate_event(db: Session, data: dict) -> None:
    if data.get("event_type") and data["event_type"] not in EVENT_TYPES:
        raise HTTPException(422, "Unknown event type")
    if data.get("organization_id") and not db.get(Organization, data["organization_id"]):
        raise HTTPException(422, "Unknown organization")
    if data.get("occurred_at") and data["occurred_at"].tzinfo is None:
        raise HTTPException(422, "occurred_at must include a timezone offset")


@router.post("/patients/{patient_id}/journey", status_code=201)
def create_event(patient_id: uuid.UUID, body: EventIn, db: Session = Depends(get_db), user: User = Depends(require_clinical)):
    AccessPolicy(db, user).require_self(patient_id, "journey.create")
    _validate_event(db, body.model_dump())
    e = JourneyEvent(patient_id=patient_id, **body.model_dump(), verification_status="patient_reported",
                     provenance="manual", provenance_detail="Entered by the patient", created_by=user.id)
    db.add(e)
    db.flush()
    audit.record(db, "journey.create", actor=user, resource_type="event", resource_id=e.id, patient_id=patient_id)
    evaluate_patient(db, patient_id)
    db.commit()
    db.refresh(e)
    return event_out(e)


@router.patch("/journey/{event_id}")
def update_event(event_id: uuid.UUID, body: EventPatch, db: Session = Depends(get_db), user: User = Depends(require_clinical)):
    e = db.get(JourneyEvent, event_id)
    if not e:
        raise HTTPException(404, "Not found")
    AccessPolicy(db, user).require_self(e.patient_id, "journey.update")
    changes = body.model_dump(exclude_unset=True)
    _validate_event(db, changes)
    for k, v in changes.items():
        setattr(e, k, v)
    audit.record(db, "journey.update", actor=user, resource_type="event", resource_id=e.id, patient_id=e.patient_id,
                 detail={"fields": sorted(changes)})
    db.flush()
    evaluate_patient(db, e.patient_id)
    db.commit()
    return event_out(e)


# ------------------------------------------------------------------ recommendations
@router.get("/patients/{patient_id}/recommendations")
def list_recommendations(patient_id: uuid.UUID, review_status: str | None = None, db: Session = Depends(get_db),
                         user: User = Depends(require_clinical)):
    policy = AccessPolicy(db, user)
    policy.require_section(patient_id, "documents")
    visible = policy.accessible_document_ids(patient_id)
    journey_ok = policy.can_view_patient_section(patient_id, "journey")
    stmt = select(Recommendation).where(Recommendation.patient_id == patient_id)
    if review_status:
        stmt = stmt.where(Recommendation.review_status == review_status)
    recs = db.execute(stmt.order_by(Recommendation.documented_at.desc().nulls_last())).scalars().all()
    return [recommendation_out(r) for r in recs
            if (r.document_id in visible) or (r.document_id is None and journey_ok)]


class RecommendationIn(BaseModel):
    kind: str
    text: str = Field(min_length=4, max_length=2000)
    timeframe_text: str | None = Field(None, max_length=200)
    due_date: date | None = None
    document_id: uuid.UUID | None = None


@router.post("/patients/{patient_id}/recommendations", status_code=201)
def create_recommendation(patient_id: uuid.UUID, body: RecommendationIn, db: Session = Depends(get_db),
                          user: User = Depends(require_clinical)):
    """Patients add manual entries; professionals with journey access may propose recommendations."""
    policy = AccessPolicy(db, user)
    if not (policy.is_self(patient_id) or policy.can_view_patient_section(patient_id, "journey")):
        raise policy.deny("recommendation.create", "patient", patient_id, patient_id)
    if body.kind not in REC_KINDS:
        raise HTTPException(422, "Unknown kind")
    if body.document_id:
        doc = policy.get_document(body.document_id)
        if doc.patient_id != patient_id:
            raise HTTPException(404, "Not found")
    is_pro = user.role == "professional"
    r = Recommendation(patient_id=patient_id, document_id=body.document_id, kind=body.kind, text=body.text.strip(),
                       timeframe_text=body.timeframe_text, due_date=body.due_date, target=",".join(find_terms(body.text)),
                       review_status="confirmed" if not is_pro else "pending_review",
                       source="professional" if is_pro else "manual", proposed_by=user.id,
                       documented_at=utcnow().date())
    db.add(r)
    db.flush()
    audit.record(db, "recommendation.create", actor=user, resource_type="recommendation", resource_id=r.id,
                 patient_id=patient_id, detail={"source": r.source})
    if is_pro:
        from app.services.notifications import notify

        notify(db, patient_id, "followup_pending", f"{user.full_name} proposed a follow-up",
               "Review the proposal in Follow-ups.", "/app/tasks")
    evaluate_patient(db, patient_id)
    db.commit()
    return recommendation_out(r)


class RecommendationReview(BaseModel):
    action: str = Field(pattern="^(confirm|correct|reject)$")
    text: str | None = Field(None, min_length=4, max_length=2000)
    kind: str | None = None
    timeframe_text: str | None = Field(None, max_length=200)
    due_date: date | None = None


@router.patch("/recommendations/{rec_id}")
def review_recommendation(rec_id: uuid.UUID, body: RecommendationReview, db: Session = Depends(get_db),
                          user: User = Depends(require_clinical)):
    r = db.get(Recommendation, rec_id)
    if not r:
        raise HTTPException(404, "Not found")
    policy = AccessPolicy(db, user)
    policy.require_self(r.patient_id, "recommendation.review")
    if body.action == "correct":
        if body.kind and body.kind not in REC_KINDS:
            raise HTTPException(422, "Unknown kind")
        if body.text and body.text != r.text:
            r.original_text = r.original_text or r.text
            r.text = body.text.strip()
            r.target = ",".join(find_terms(r.text))
        if body.kind:
            r.kind = body.kind
        if body.timeframe_text is not None:
            r.timeframe_text = body.timeframe_text or None
        if body.due_date is not None:
            r.due_date = body.due_date
        r.review_status = "corrected"
    else:
        r.review_status = "confirmed" if body.action == "confirm" else "rejected"
    r.reviewed_by, r.reviewed_at = user.id, utcnow()
    audit.record(db, f"recommendation.{body.action}", actor=user, resource_type="recommendation", resource_id=r.id,
                 patient_id=r.patient_id)
    db.flush()
    evaluate_patient(db, r.patient_id)
    db.commit()
    return recommendation_out(r)


@router.post("/recommendations/{rec_id}/track", status_code=201)
def track_recommendation(rec_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_clinical)):
    """Create a follow-up task from a recommendation (due date only if one was documented)."""
    r = db.get(Recommendation, rec_id)
    if not r:
        raise HTTPException(404, "Not found")
    AccessPolicy(db, user).require_self(r.patient_id, "task.create")
    if r.review_status == "rejected":
        raise HTTPException(409, "Rejected recommendations cannot be tracked.")
    existing = db.execute(select(FollowUpTask).where(FollowUpTask.recommendation_id == r.id,
                                                     FollowUpTask.kind == "follow_up")).scalars().first()
    if existing:
        return task_out(existing)
    if r.review_status == "pending_review":
        r.review_status, r.reviewed_by, r.reviewed_at = "confirmed", user.id, utcnow()
    t = FollowUpTask(patient_id=r.patient_id, recommendation_id=r.id, kind="follow_up", title=r.text[:300],
                     description=f"Documented timeframe: {r.timeframe_text}" if r.timeframe_text else None,
                     owner_id=user.id, due_date=r.due_date, due_date_source="documented" if r.due_date else None,
                     created_by=user.id)
    db.add(t)
    db.flush()
    audit.record(db, "task.create", actor=user, resource_type="task", resource_id=t.id, patient_id=r.patient_id,
                 detail={"from": "recommendation"})
    evaluate_patient(db, r.patient_id)
    db.commit()
    return task_out(t)
