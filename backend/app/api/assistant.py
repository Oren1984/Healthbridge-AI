import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import audit
from app.api.serializers import task_out
from app.authz import AccessPolicy
from app.db import get_db
from app.deps import require_clinical
from app.models import AssistantAction, FollowUpTask, User
from app.security.ratelimit import limiter
from app.services.agent import TOOLS, HealthBridgeAgent
from app.services.care_gaps import evaluate_patient
from app.services.embeddings import get_embedder
from app.services.llm import get_ai_mode, ollama_status

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.get("/status")
def status(db: Session = Depends(get_db), user: User = Depends(require_clinical)):
    mode = get_ai_mode(db)
    return {"mode": mode, "ollama": ollama_status() if mode == "ollama" else None,
            "embedding_provider": get_embedder().name,
            "tools": [{"name": k, "read_only": v} for k, v in TOOLS.items()]}


class QueryIn(BaseModel):
    patient_id: uuid.UUID
    message: str = Field(min_length=1, max_length=1000)


@router.post("/query")
def query(body: QueryIn, db: Session = Depends(get_db), user: User = Depends(require_clinical)):
    if not limiter.hit(f"assistant:{user.id}", 30, 60):
        raise HTTPException(429, "Too many questions. Please wait a minute.")
    policy = AccessPolicy(db, user)
    policy.require_section(body.patient_id, "documents")
    resp = HealthBridgeAgent(db, user, body.patient_id).respond(body.message)
    # Audit metadata only — never the question or answer text.
    audit.record(db, "assistant.query", actor=user, patient_id=body.patient_id,
                 detail={"intent": resp.intent, "mode": resp.mode, "tools": resp.tools_used, "sources": len(resp.sources),
                         "insufficient_evidence": resp.insufficient_evidence})
    db.commit()
    return resp.__dict__


def _action(db: Session, user: User, action_id: uuid.UUID) -> AssistantAction:
    a = db.get(AssistantAction, action_id)
    if not a or a.user_id != user.id:
        raise HTTPException(404, "Not found")
    if a.status != "pending":
        raise HTTPException(409, f"This action is already {a.status}.")
    return a


@router.post("/actions/{action_id}/confirm")
def confirm(action_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_clinical)):
    a = _action(db, user, action_id)
    AccessPolicy(db, user).require_self(a.patient_id, "assistant.confirm")  # re-authorize at execution time
    if a.action_type != "create_followup_task":
        raise HTTPException(400, "Unsupported action")
    t = FollowUpTask(patient_id=a.patient_id, kind="follow_up", title=a.payload["title"], owner_id=user.id,
                     created_by=user.id, description="Created from an assistant suggestion you confirmed.")
    db.add(t)
    a.status = "confirmed"
    db.flush()
    audit.record(db, "task.create", actor=user, resource_type="task", resource_id=t.id, patient_id=a.patient_id,
                 detail={"from": "assistant_confirmed"})
    evaluate_patient(db, a.patient_id)
    db.commit()
    return {"status": "confirmed", "task": task_out(t)}


@router.post("/actions/{action_id}/cancel")
def cancel(action_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_clinical)):
    a = _action(db, user, action_id)
    a.status = "cancelled"
    db.commit()
    return {"status": "cancelled"}
