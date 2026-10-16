"""Tamper-evident audit log.

Every record stores HMAC(key, prev_hash || canonical(record)). Records are appended inside a
transaction holding a Postgres advisory lock so the chain is linear. `verify_chain` recomputes it.
Details must never contain document content, passwords or tokens — only identifiers and codes.
"""
import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AuditEvent, User, utcnow

_LOCK_ID = 7_340_001
GENESIS = "0" * 64


def _canonical(e: AuditEvent) -> str:
    return json.dumps(
        {
            "ts": e.ts.astimezone(timezone.utc).isoformat(),
            "actor_id": str(e.actor_id) if e.actor_id else None,
            "actor_role": e.actor_role,
            "action": e.action,
            "resource_type": e.resource_type,
            "resource_id": e.resource_id,
            "patient_id": str(e.patient_id) if e.patient_id else None,
            "outcome": e.outcome,
            "detail": e.detail,
            "request_id": e.request_id,
            "ip": e.ip,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _digest(prev_hash: str, e: AuditEvent) -> str:
    key = get_settings().audit_hmac_key.encode()
    return hmac.new(key, (prev_hash + _canonical(e)).encode(), hashlib.sha256).hexdigest()


def record(
    db: Session,
    action: str,
    *,
    actor: User | None = None,
    outcome: str = "success",
    resource_type: str | None = None,
    resource_id: str | uuid.UUID | None = None,
    patient_id: uuid.UUID | None = None,
    detail: dict | None = None,
    request_id: str | None = None,
    ip: str | None = None,
    commit: bool = False,
) -> AuditEvent:
    """Append an audit record to the current transaction (commit=True to commit immediately)."""
    from app.observability import current_request_context

    ctx = current_request_context()
    db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _LOCK_ID})
    prev = db.execute(select(AuditEvent.hash).order_by(AuditEvent.id.desc()).limit(1)).scalar()
    ev = AuditEvent(
        ts=utcnow(),
        actor_id=actor.id if actor else None,
        actor_role=actor.role if actor else None,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id else None,
        patient_id=patient_id,
        outcome=outcome,
        detail=detail or {},
        request_id=request_id or ctx.get("request_id"),
        ip=ip or ctx.get("ip"),
        prev_hash=prev or GENESIS,
    )
    ev.hash = _digest(ev.prev_hash, ev)
    db.add(ev)
    db.flush()
    if commit:
        db.commit()
    return ev


def record_denied(db: Session, action: str, actor: User | None, **kw) -> None:
    """Denials are committed independently so they survive the request's rollback."""
    from app.db import SessionLocal

    with SessionLocal() as s:
        record(s, action, actor=actor, outcome="denied", **kw)
        s.commit()


def verify_chain(db: Session) -> dict:
    prev = GENESIS
    count = 0
    for ev in db.execute(select(AuditEvent).order_by(AuditEvent.id)).scalars():
        if ev.prev_hash != prev or _digest(prev, ev) != ev.hash:
            return {"valid": False, "checked": count, "broken_at_id": ev.id}
        prev = ev.hash
        count += 1
    return {"valid": True, "checked": count, "broken_at_id": None}


def as_dict(ev: AuditEvent) -> dict:
    return {
        "id": ev.id,
        "ts": ev.ts.isoformat() if isinstance(ev.ts, datetime) else ev.ts,
        "actor_id": str(ev.actor_id) if ev.actor_id else None,
        "actor_role": ev.actor_role,
        "action": ev.action,
        "resource_type": ev.resource_type,
        "resource_id": ev.resource_id,
        "outcome": ev.outcome,
        "detail": ev.detail,
        "request_id": ev.request_id,
    }
