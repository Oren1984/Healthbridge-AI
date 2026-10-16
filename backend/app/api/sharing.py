"""Patient-controlled sharing (consent grants) and access transparency."""
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app import audit
from app.api.serializers import document_out, grant_out, user_brief
from app.authz import AccessPolicy
from app.db import get_db
from app.deps import require_clinical, require_patient, require_professional
from app.models import AuditEvent, ConsentGrant, Document, ProfessionalProfile, User, utcnow
from app.services.care_gaps import evaluate_patient
from app.services.documents import CATEGORIES
from app.services.notifications import notify

router = APIRouter(tags=["sharing"])

REVOCATION_NOTICE = ("Revoking stops any further access through HealthBridge from that moment. It cannot recall "
                     "information the professional already viewed or downloaded, and it does not override legal "
                     "record-keeping obligations of healthcare providers.")


@router.get("/professionals")
def directory(q: str | None = Query(None, max_length=100), db: Session = Depends(get_db),
              user: User = Depends(require_clinical)):
    stmt = select(User).join(ProfessionalProfile).where(User.role == "professional", User.is_active.is_(True),
                                                        ProfessionalProfile.verification_status == "simulated_verified")
    if q:
        like = f"%{q.replace('%', '').replace('_', '')}%"
        stmt = stmt.where(or_(User.full_name.ilike(like), ProfessionalProfile.specialty.ilike(like)))
    return [user_brief(u) for u in db.execute(stmt.order_by(User.full_name)).scalars()]


class GrantIn(BaseModel):
    grantee_id: uuid.UUID
    document_ids: list[uuid.UUID] = Field(default_factory=list, max_length=200)
    categories: list[str] = Field(default_factory=list, max_length=10)
    include_journey: bool = False
    include_care_gaps: bool = False
    days: int = Field(14, ge=1, le=365)
    purpose: str | None = Field(None, max_length=300)
    consultation_id: uuid.UUID | None = None


def _resolve(db: Session, patient_id: uuid.UUID, body: GrantIn) -> tuple[User, list[Document], list[Document]]:
    grantee = db.get(User, body.grantee_id)
    if not grantee or grantee.role != "professional" or not grantee.is_active or not grantee.professional \
            or grantee.professional.verification_status != "simulated_verified":
        raise HTTPException(422, "Recipient must be an active, verified professional.")
    bad = [c for c in body.categories if c not in CATEGORIES]
    if bad:
        raise HTTPException(422, f"Unknown categories: {', '.join(bad)}")
    docs = []
    if body.document_ids:
        docs = db.execute(select(Document).where(Document.id.in_(body.document_ids), Document.patient_id == patient_id,
                                                 Document.deleted_at.is_(None))).scalars().all()
        if len(docs) != len(set(body.document_ids)):
            raise HTTPException(404, "One or more documents were not found.")
    by_category = []
    if body.categories:
        by_category = db.execute(select(Document).where(Document.patient_id == patient_id, Document.deleted_at.is_(None),
                                                        Document.category.in_(body.categories))).scalars().all()
    if not docs and not body.categories and not body.include_journey and not body.include_care_gaps:
        raise HTTPException(422, "Select at least one document, category or section to share.")
    return grantee, list(docs), list(by_category)


@router.post("/patients/{patient_id}/grants/preview")
def preview(patient_id: uuid.UUID, body: GrantIn, db: Session = Depends(get_db), user: User = Depends(require_patient)):
    AccessPolicy(db, user).require_self(patient_id, "consent.preview")
    grantee, docs, by_cat = _resolve(db, patient_id, body)
    all_docs = {d.id: d for d in docs + by_cat}
    now = utcnow()
    return {
        "grantee": user_brief(grantee),
        "documents": [document_out(d) for d in all_docs.values()],
        "categories": body.categories,
        "categories_note": "Category sharing also covers documents of these categories that you upload later, until the grant ends.",
        "sections": {"journey": body.include_journey, "care_gaps": body.include_care_gaps,
                     "tasks": body.include_journey},
        "starts_at": now.isoformat(), "expires_at": (now + timedelta(days=body.days)).isoformat(),
        "revocation_notice": REVOCATION_NOTICE,
    }


@router.post("/patients/{patient_id}/grants", status_code=201)
def create_grant(patient_id: uuid.UUID, body: GrantIn, db: Session = Depends(get_db), user: User = Depends(require_patient)):
    policy = AccessPolicy(db, user)
    policy.require_self(patient_id, "consent.grant")
    grantee, docs, _ = _resolve(db, patient_id, body)
    if body.consultation_id:
        policy.get_consultation(body.consultation_id)
    now = utcnow()
    g = ConsentGrant(patient_id=patient_id, grantee_id=grantee.id, categories=body.categories,
                     include_journey=body.include_journey, include_care_gaps=body.include_care_gaps,
                     purpose=body.purpose, consultation_id=body.consultation_id, starts_at=now,
                     expires_at=now + timedelta(days=body.days))
    g.documents = docs
    db.add(g)
    db.flush()
    audit.record(db, "consent.grant", actor=user, resource_type="grant", resource_id=g.id, patient_id=patient_id,
                 detail={"grantee_id": str(grantee.id), "documents": len(docs), "categories": body.categories,
                         "journey": body.include_journey, "care_gaps": body.include_care_gaps, "days": body.days})
    notify(db, grantee.id, "sharing_invitation", f"{user.full_name} shared health information with you",
           f"Access until {g.expires_at.date().isoformat()}.", f"/app/pro/patients/{patient_id}")
    evaluate_patient(db, patient_id)
    db.commit()
    db.refresh(g)
    return grant_out(g)


@router.get("/patients/{patient_id}/grants")
def list_grants(patient_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_patient)):
    AccessPolicy(db, user).require_self(patient_id, "consent.list")
    grants = db.execute(select(ConsentGrant).where(ConsentGrant.patient_id == patient_id)
                        .order_by(ConsentGrant.created_at.desc())).scalars().all()
    return {"grants": [grant_out(g) for g in grants], "revocation_notice": REVOCATION_NOTICE}


@router.post("/grants/{grant_id}/revoke")
def revoke(grant_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_patient)):
    g = db.get(ConsentGrant, grant_id)
    if not g:
        raise HTTPException(404, "Not found")
    AccessPolicy(db, user).require_self(g.patient_id, "consent.revoke")
    if g.revoked_at:
        return grant_out(g)
    g.revoked_at = utcnow()
    audit.record(db, "consent.revoke", actor=user, resource_type="grant", resource_id=g.id, patient_id=g.patient_id,
                 detail={"grantee_id": str(g.grantee_id)})
    notify(db, g.grantee_id, "sharing_invitation", f"{user.full_name} ended a sharing permission",
           "You no longer have access to the previously shared information.", "/app/pro")
    db.flush()
    evaluate_patient(db, g.patient_id)
    db.commit()
    return grant_out(g)


@router.get("/patients/{patient_id}/access-log")
def access_log(patient_id: uuid.UUID, only_others: bool = False, limit: int = Query(200, le=500),
               db: Session = Depends(get_db), user: User = Depends(require_patient)):
    """Everything recorded about this patient's records, including denied attempts."""
    AccessPolicy(db, user).require_self(patient_id, "access_log.view")
    stmt = select(AuditEvent).where(AuditEvent.patient_id == patient_id)
    if only_others:
        # People other than the patient (system processing is excluded from "others").
        stmt = stmt.where(AuditEvent.actor_id.is_not(None), AuditEvent.actor_id != patient_id)
    events = db.execute(stmt.order_by(AuditEvent.id.desc()).limit(limit)).scalars().all()
    actors = {}
    out = []
    for e in events:
        if e.actor_id and e.actor_id not in actors:
            a = db.get(User, e.actor_id)
            actors[e.actor_id] = user_brief(a) if a else None
        out.append({"id": e.id, "ts": e.ts.isoformat(), "action": e.action, "outcome": e.outcome,
                    "resource_type": e.resource_type, "resource_id": e.resource_id,
                    "actor": actors.get(e.actor_id) if e.actor_id else {"full_name": "HealthBridge system", "role": "system"},
                    "detail": e.detail})
    return out


@router.get("/shared-with-me")
def shared_with_me(db: Session = Depends(get_db), user: User = Depends(require_professional)):
    now = utcnow()
    grants = db.execute(select(ConsentGrant).where(
        ConsentGrant.grantee_id == user.id, ConsentGrant.revoked_at.is_(None), ConsentGrant.starts_at <= now,
        ConsentGrant.expires_at > now).order_by(ConsentGrant.expires_at)).scalars().all()
    patients: dict = {}
    for g in grants:
        p = db.get(User, g.patient_id)
        entry = patients.setdefault(str(g.patient_id), {"patient": {"id": str(p.id), "full_name": p.full_name,
                                                                    "country": p.country, "timezone": p.timezone},
                                                        "grants": []})
        entry["grants"].append(grant_out(g))
    return list(patients.values())
