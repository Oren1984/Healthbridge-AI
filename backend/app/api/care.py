"""Care gaps and follow-up tasks."""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.api.serializers import gap_view, task_out
from app.authz import AccessPolicy
from app.db import get_db
from app.deps import require_clinical
from app.models import AuditEvent, CareGap, Document, FollowUpTask, User, utcnow
from app.services.care_gaps import RULES, build_snapshot, evaluate_patient, evaluate_snapshot, finding_to_dict

router = APIRouter(tags=["care"])
_STATUS_ORDER = {"requires_clarification": 0, "unknown": 1, "open": 2, "completed_verified": 3, "not_applicable": 4}


@router.get("/care-gaps/rules")
def rules(user: User = Depends(require_clinical)):
    return [{"rule_id": k, "description": v} for k, v in RULES.items()]


@router.get("/patients/{patient_id}/care-gaps")
def list_gaps(patient_id: uuid.UUID, include_inactive: bool = False, db: Session = Depends(get_db),
              user: User = Depends(require_clinical)):
    policy = AccessPolicy(db, user)
    policy.require_section(patient_id, "care_gaps")
    stmt = select(CareGap).where(CareGap.patient_id == patient_id)
    if not include_inactive:
        stmt = stmt.where(CareGap.active.is_(True))
    gaps = db.execute(stmt).scalars().all()
    if not policy.is_self(patient_id):
        audit.record(db, "care_gaps.view", actor=user, resource_type="patient", resource_id=patient_id, patient_id=patient_id)
        db.commit()
    return sorted([gap_view(g, policy) for g in gaps], key=lambda g: (_STATUS_ORDER.get(g["status"], 9), g["rule_id"], g["title"]))


@router.post("/patients/{patient_id}/care-gaps/evaluate")
def evaluate(patient_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_clinical)):
    AccessPolicy(db, user).require_self(patient_id, "care_gaps.evaluate")
    result = evaluate_patient(db, patient_id)
    audit.record(db, "care_gaps.evaluate", actor=user, patient_id=patient_id, detail=result)
    db.commit()
    return result


@router.get("/patients/{patient_id}/care-gaps/replay")
def replay(patient_id: uuid.UUID, as_of: date | None = None, db: Session = Depends(get_db),
           user: User = Depends(require_clinical)):
    """Deterministic replay: recompute findings for a given date without persisting anything."""
    AccessPolicy(db, user).require_self(patient_id, "care_gaps.replay")
    as_of = as_of or utcnow().date()
    findings = evaluate_snapshot(build_snapshot(db, patient_id), as_of)
    return {"as_of": as_of.isoformat(), "rules": RULES, "findings": [finding_to_dict(f) for f in findings]}


class GapReview(BaseModel):
    action: str = Field(pattern="^(dismiss|clarify|reopen|create_clarification)$")
    note: str | None = Field(None, max_length=2000)


@router.post("/care-gaps/{gap_id}/review")
def review_gap(gap_id: uuid.UUID, body: GapReview, db: Session = Depends(get_db), user: User = Depends(require_clinical)):
    g = db.get(CareGap, gap_id)
    if not g:
        raise HTTPException(404, "Not found")
    policy = AccessPolicy(db, user)
    if not policy.can_view_patient_section(g.patient_id, "care_gaps"):
        raise policy.deny("care_gap.review", "care_gap", gap_id, g.patient_id)
    task = None
    if body.action == "dismiss":
        if not body.note or len(body.note.strip()) < 5:
            raise HTTPException(422, "A reason is required to dismiss an item.")
        g.review_status = "not_applicable"
    elif body.action == "clarify":
        g.review_status = "requires_clarification"
    elif body.action == "reopen":
        g.review_status = None
    else:
        policy.require_self(g.patient_id, "care_gap.create_clarification")
        task = db.execute(select(FollowUpTask).where(FollowUpTask.care_gap_id == g.id,
                                                     FollowUpTask.kind == "clarification",
                                                     FollowUpTask.status == "open")).scalars().first()
        if not task:
            task = FollowUpTask(patient_id=g.patient_id, care_gap_id=g.id, kind="clarification",
                                title=f"Clarify: {g.title}"[:300], description=g.suggested_clarification,
                                owner_id=user.id, created_by=user.id)
            db.add(task)
    if body.action != "create_clarification":
        g.review_note, g.reviewed_by, g.reviewed_at = body.note, user.id, utcnow()
    db.flush()
    audit.record(db, f"care_gap.{body.action}", actor=user, resource_type="care_gap", resource_id=g.id, patient_id=g.patient_id,
                 detail={"rule_id": g.rule_id, **({"task_id": str(task.id)} if task else {})})
    db.commit()
    out = gap_view(g, policy)
    if task:
        out["created_task"] = task_out(task)
    return out


# ------------------------------------------------------------------ tasks
@router.get("/patients/{patient_id}/tasks")
def list_tasks(patient_id: uuid.UUID, status: str | None = None, db: Session = Depends(get_db),
               user: User = Depends(require_clinical)):
    AccessPolicy(db, user).require_section(patient_id, "tasks")
    stmt = select(FollowUpTask).where(FollowUpTask.patient_id == patient_id)
    if status:
        stmt = stmt.where(FollowUpTask.status == status)
    tasks = db.execute(stmt.order_by(FollowUpTask.status, FollowUpTask.due_date.nulls_last(),
                                     FollowUpTask.created_at.desc())).scalars().all()
    return [task_out(t) for t in tasks]


class TaskIn(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    description: str | None = Field(None, max_length=3000)
    kind: str = Field("follow_up", pattern="^(follow_up|clarification)$")
    recommendation_id: uuid.UUID | None = None
    due_date: date | None = None
    owner_id: uuid.UUID | None = None
    reminder_days_before: int | None = Field(None, ge=0, le=60)


class TaskPatch(BaseModel):
    title: str | None = Field(None, min_length=3, max_length=300)
    description: str | None = Field(None, max_length=3000)
    due_date: date | None = None
    clear_due_date: bool = False
    owner_id: uuid.UUID | None = None
    reminder_days_before: int | None = Field(None, ge=0, le=60)


class TaskComplete(BaseModel):
    note: str | None = Field(None, max_length=2000)
    evidence_document_id: uuid.UUID | None = None


def _task_for(db: Session, user: User, task_id: uuid.UUID, action: str, self_only: bool = True) -> tuple[FollowUpTask, AccessPolicy]:
    t = db.get(FollowUpTask, task_id)
    if not t:
        raise HTTPException(404, "Not found")
    policy = AccessPolicy(db, user)
    if self_only:
        policy.require_self(t.patient_id, action)
    elif not policy.can_view_patient_section(t.patient_id, "tasks"):
        raise policy.deny(action, "task", task_id, t.patient_id)
    return t, policy


def _validate_owner(db: Session, policy: AccessPolicy, patient_id: uuid.UUID, owner_id: uuid.UUID | None) -> None:
    if owner_id is None or owner_id == patient_id:
        return
    owner = db.get(User, owner_id)
    if not owner or owner.role != "professional":
        raise HTTPException(422, "Owner must be the patient or a professional with access")
    if patient_id not in AccessPolicy(db, owner).accessible_patient_ids():
        raise HTTPException(422, "That professional does not currently have access to your records")


def _evidence_doc(db: Session, policy: AccessPolicy, patient_id: uuid.UUID, doc_id: uuid.UUID) -> Document:
    doc = policy.get_document(doc_id, "task.evidence")
    if doc.patient_id != patient_id:
        raise HTTPException(404, "Not found")
    return doc


def _done(db: Session, user: User, t: FollowUpTask, action: str) -> dict:
    t.updated_at = utcnow()
    audit.record(db, action, actor=user, resource_type="task", resource_id=t.id, patient_id=t.patient_id,
                 detail={"status": t.status})
    db.flush()
    evaluate_patient(db, t.patient_id)
    db.commit()
    return task_out(t)


@router.post("/patients/{patient_id}/tasks", status_code=201)
def create_task(patient_id: uuid.UUID, body: TaskIn, db: Session = Depends(get_db), user: User = Depends(require_clinical)):
    policy = AccessPolicy(db, user)
    policy.require_self(patient_id, "task.create")
    _validate_owner(db, policy, patient_id, body.owner_id)
    if body.recommendation_id:
        from app.models import Recommendation

        r = db.get(Recommendation, body.recommendation_id)
        if not r or r.patient_id != patient_id:
            raise HTTPException(404, "Recommendation not found")
    t = FollowUpTask(patient_id=patient_id, **body.model_dump(exclude={"owner_id"}), owner_id=body.owner_id or user.id,
                     due_date_source="user_entered" if body.due_date else None, created_by=user.id)
    db.add(t)
    db.flush()
    return _done(db, user, t, "task.create")


@router.patch("/tasks/{task_id}")
def update_task(task_id: uuid.UUID, body: TaskPatch, db: Session = Depends(get_db), user: User = Depends(require_clinical)):
    t, policy = _task_for(db, user, task_id, "task.update")
    changes = body.model_dump(exclude_unset=True)
    if "owner_id" in changes:
        _validate_owner(db, policy, t.patient_id, body.owner_id)
        t.owner_id = body.owner_id or t.patient_id
    for k in ("title", "description", "reminder_days_before"):
        if k in changes:
            setattr(t, k, changes[k])
    if body.clear_due_date:
        t.due_date, t.due_date_source = None, None
    elif body.due_date is not None:
        t.due_date, t.due_date_source = body.due_date, "user_entered"
    return _done(db, user, t, "task.update")


@router.post("/tasks/{task_id}/complete")
def complete_task(task_id: uuid.UUID, body: TaskComplete, db: Session = Depends(get_db), user: User = Depends(require_clinical)):
    """Explicit human completion. With an evidence document the task is verified; otherwise 'reported'."""
    t, policy = _task_for(db, user, task_id, "task.complete")
    t.completion_note, t.completed_by, t.completed_at = body.note, user.id, utcnow()
    if body.evidence_document_id:
        _evidence_doc(db, policy, t.patient_id, body.evidence_document_id)
        t.evidence_document_id, t.status, t.verified_by, t.verified_at = body.evidence_document_id, "completed_verified", user.id, utcnow()
    else:
        t.status = "completed_reported"
    return _done(db, user, t, "task.complete")


@router.post("/tasks/{task_id}/verify")
def verify_task(task_id: uuid.UUID, body: TaskComplete, db: Session = Depends(get_db), user: User = Depends(require_clinical)):
    """Attach evidence to a task. Patients or professionals with task access may verify."""
    t, policy = _task_for(db, user, task_id, "task.verify", self_only=False)
    if not body.evidence_document_id:
        raise HTTPException(422, "An evidence document is required to verify completion.")
    _evidence_doc(db, policy, t.patient_id, body.evidence_document_id)
    t.evidence_document_id, t.status, t.verified_by, t.verified_at = body.evidence_document_id, "completed_verified", user.id, utcnow()
    t.completed_at = t.completed_at or utcnow()
    t.completed_by = t.completed_by or user.id
    if body.note:
        t.completion_note = body.note
    return _done(db, user, t, "task.verify")


@router.post("/tasks/{task_id}/reopen")
def reopen_task(task_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_clinical)):
    t, _ = _task_for(db, user, task_id, "task.reopen")
    t.status, t.evidence_document_id, t.verified_by, t.verified_at, t.completed_at = "open", None, None, None, None
    return _done(db, user, t, "task.reopen")


@router.post("/tasks/{task_id}/dismiss")
def dismiss_task(task_id: uuid.UUID, body: TaskComplete, db: Session = Depends(get_db), user: User = Depends(require_clinical)):
    t, _ = _task_for(db, user, task_id, "task.dismiss")
    if not body.note or len(body.note.strip()) < 5:
        raise HTTPException(422, "A reason is required.")
    t.status, t.completion_note = "not_applicable", body.note
    return _done(db, user, t, "task.dismiss")


@router.get("/tasks/{task_id}/history")
def task_history(task_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_clinical)):
    _task_for(db, user, task_id, "task.history")
    events = db.execute(select(AuditEvent).where(AuditEvent.resource_type == "task", AuditEvent.resource_id == str(task_id))
                        .order_by(AuditEvent.id)).scalars().all()
    names = {}
    out = []
    for e in events:
        if e.actor_id and e.actor_id not in names:
            u = db.get(User, e.actor_id)
            names[e.actor_id] = u.full_name if u else None
        out.append({"ts": e.ts.isoformat(), "action": e.action, "actor": names.get(e.actor_id), "detail": e.detail})
    return out
