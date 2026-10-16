"""Limited administration. Administrators never receive clinical content through these endpoints."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app import audit
from app.api.auth import EMAIL_PATTERN
from app.api.serializers import user_out
from app.config import get_settings
from app.db import get_db
from app.deps import require_admin
from app.models import (
    AppSetting, AuditEvent, AuthSession, Document, JobRun, Organization, PatientProfile, ProfessionalProfile, User,
    utcnow,
)
from app.observability import metrics
from app.security.passwords import hash_password, validate_password_strength
from app.security.storage import get_storage
from app.services.llm import get_ai_mode, ollama_status
from app.services.meetings import livekit_reachable

router = APIRouter(prefix="/admin", tags=["admin"])
SECURITY_ACTIONS = ("auth.", "admin.", "account.", "meeting.token")


@router.get("/users")
def users(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    return [user_out(u) for u in db.execute(select(User).order_by(User.role, User.full_name)).scalars()]


class UserIn(BaseModel):
    email: str = Field(pattern=EMAIL_PATTERN, max_length=254)
    full_name: str = Field(min_length=2, max_length=200)
    role: str = Field(pattern="^(patient|professional)$")
    password: str = Field(max_length=128)
    country: str = Field("IL", pattern="^[A-Z]{2}$")
    timezone: str = Field("Asia/Jerusalem", max_length=64)
    specialty: str | None = Field(None, max_length=100)
    organization_id: uuid.UUID | None = None


@router.post("/users", status_code=201)
def create_user(body: UserIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    if err := validate_password_strength(body.password):
        raise HTTPException(422, err)
    if db.execute(select(User.id).where(User.email == body.email.lower())).first():
        raise HTTPException(409, "Email already exists.")
    u = User(email=body.email.lower(), full_name=body.full_name, role=body.role, password_hash=hash_password(body.password),
             country=body.country, timezone=body.timezone)
    db.add(u)
    db.flush()
    if body.role == "patient":
        db.add(PatientProfile(user_id=u.id))
    else:
        if body.organization_id and not db.get(Organization, body.organization_id):
            raise HTTPException(422, "Unknown organization")
        db.add(ProfessionalProfile(user_id=u.id, specialty=body.specialty or "General practice",
                                   organization_id=body.organization_id, license_number=f"SYN-{str(u.id)[:8].upper()}",
                                   verification_status="pending"))
    audit.record(db, "admin.user_create", actor=admin, resource_type="user", resource_id=u.id, detail={"role": body.role})
    db.commit()
    db.refresh(u)
    return user_out(u)


class UserPatch(BaseModel):
    is_active: bool | None = None
    verification_status: str | None = Field(None, pattern="^(simulated_verified|pending|rejected)$")


@router.patch("/users/{user_id}")
def update_user(user_id: uuid.UUID, body: UserPatch, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "Not found")
    if u.id == admin.id and body.is_active is False:
        raise HTTPException(409, "You cannot deactivate your own account.")
    if body.is_active is not None:
        u.is_active = body.is_active
        if not body.is_active:
            for s in db.execute(select(AuthSession).where(AuthSession.user_id == u.id, AuthSession.revoked_at.is_(None))).scalars():
                s.revoked_at = utcnow()
    if body.verification_status:
        if not u.professional:
            raise HTTPException(409, "Only professional accounts have a verification status.")
        u.professional.verification_status = body.verification_status
        u.professional.verified_at = utcnow() if body.verification_status == "simulated_verified" else None
    audit.record(db, "admin.user_update", actor=admin, resource_type="user", resource_id=u.id,
                 detail={k: v for k, v in body.model_dump().items() if v is not None})
    db.commit()
    return user_out(u)


@router.get("/security-events")
def security_events(outcome: str | None = Query(None, pattern="^(success|denied|error)$"), limit: int = Query(200, le=1000),
                    db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Security-relevant events: authentication, admin actions and every denied access (metadata only)."""
    stmt = select(AuditEvent).where(or_(AuditEvent.outcome == "denied",
                                        *[AuditEvent.action.startswith(p) for p in SECURITY_ACTIONS]))
    if outcome:
        stmt = stmt.where(AuditEvent.outcome == outcome)
    rows = db.execute(stmt.order_by(AuditEvent.id.desc()).limit(limit)).scalars().all()
    return [{**audit.as_dict(e), "patient_ref": "present" if e.patient_id else None} for e in rows]


@router.get("/audit/verify")
def verify_audit(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    result = audit.verify_chain(db)
    audit.record(db, "admin.audit_verify", actor=admin, detail={"valid": result["valid"], "checked": result["checked"]})
    db.commit()
    return result


@router.get("/system")
def system(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    doc_status = dict(db.execute(select(Document.status, func.count()).group_by(Document.status)).all())
    roles = dict(db.execute(select(User.role, func.count()).group_by(User.role)).all())
    jobs = [{"job": j.job_name, "last_started_at": j.last_started_at.isoformat() if j.last_started_at else None,
             "last_finished_at": j.last_finished_at.isoformat() if j.last_finished_at else None,
             "last_status": j.last_status, "last_error": j.last_error, "runs": j.runs, "items_processed": j.items_processed}
            for j in db.execute(select(JobRun).order_by(JobRun.job_name)).scalars()]
    mode = get_ai_mode(db)
    return {
        "database": "ok", "storage_writable": get_storage().writable(), "livekit_reachable": livekit_reachable(),
        "ai_mode": mode, "ollama": ollama_status(), "demo_mode": get_settings().demo_mode,
        "documents_by_status": doc_status, "users_by_role": roles, "jobs": jobs, "metrics": metrics.snapshot(),
    }


class ConfigIn(BaseModel):
    ai_mode: str = Field(pattern="^(mock|ollama)$")


@router.get("/config")
def get_config(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    return {"ai_mode": get_ai_mode(db), "environment_default_ai_mode": get_settings().ai_mode}


@router.put("/config")
def put_config(body: ConfigIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    row = db.get(AppSetting, "ai_mode")
    if row:
        row.value = {"mode": body.ai_mode}
    else:
        db.add(AppSetting(key="ai_mode", value={"mode": body.ai_mode}))
    audit.record(db, "admin.config_update", actor=admin, detail={"ai_mode": body.ai_mode})
    db.commit()
    return get_config(db, admin)


class ResetIn(BaseModel):
    confirm: str
    scenario: str = Field("showcase", pattern="^(showcase|fresh)$")


@router.post("/demo/reset")
def reset_demo(body: ResetIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    if not get_settings().demo_mode:
        raise HTTPException(403, "Demo reset is disabled outside demo mode.")
    if body.confirm != "RESET":
        raise HTTPException(422, "Type RESET to confirm.")
    from app.services.seed import reset_and_seed

    db.close()
    summary = reset_and_seed(body.scenario)
    return {"ok": True, "scenario": body.scenario, **summary}
