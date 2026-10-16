import re
import uuid
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app import audit
from app.api.serializers import document_out, event_out, recommendation_out
from app.authz import AccessPolicy
from app.config import get_settings
from app.db import get_db
from app.deps import get_current_user, require_clinical
from app.models import (
    Document, DocumentChunk, FollowUpTask, JourneyEvent, Organization, Recommendation, User, utcnow,
)
from app.security.ratelimit import limiter
from app.security.storage import get_storage
from app.services import documents as docsvc
from app.services.care_gaps import evaluate_patient
from app.services.extraction import UploadRejected
from app.services.fhir import export_bundle

router = APIRouter(tags=["documents"])


def _audit_access(db: Session, user: User, action: str, doc: Document) -> None:
    audit.record(db, action, actor=user, resource_type="document", resource_id=doc.id, patient_id=doc.patient_id,
                 detail={"category": doc.category})


@router.get("/organizations")
def organizations(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from app.api.serializers import org_out

    return [org_out(o) for o in db.execute(select(Organization).order_by(Organization.name)).scalars()]


@router.get("/patients/{patient_id}/documents")
def list_documents(patient_id: uuid.UUID, q: str | None = Query(None, max_length=200),
                   category: str | None = Query(None, max_length=40), include_versions: bool = False,
                   db: Session = Depends(get_db), user: User = Depends(require_clinical)):
    policy = AccessPolicy(db, user)
    policy.require_section(patient_id, "documents")
    ids = policy.accessible_document_ids(patient_id)
    if not ids:
        return []
    stmt = select(Document).where(Document.id.in_(ids))
    if not include_versions:
        stmt = stmt.where(Document.is_latest.is_(True))
    if category:
        stmt = stmt.where(Document.category == category)
    if q:
        like = "%" + re.sub(r"([%_\\])", r"\\\1", q) + "%"
        chunk_match = select(DocumentChunk.document_id).where(DocumentChunk.tsv.op("@@")(
            func.plainto_tsquery("simple", q)))
        stmt = stmt.where(or_(Document.title.ilike(like, escape="\\"), Document.source_detected.ilike(like, escape="\\"),
                              Document.id.in_(chunk_match)))
    docs = db.execute(stmt.order_by(Document.document_date.desc().nulls_last(), Document.created_at.desc())).scalars().all()
    if not policy.is_self(patient_id):
        audit.record(db, "documents.list", actor=user, resource_type="patient", resource_id=patient_id,
                     patient_id=patient_id, detail={"count": len(docs)})
        db.commit()
    return [document_out(d) for d in docs]


@router.post("/patients/{patient_id}/documents", status_code=201)
def upload_document(patient_id: uuid.UUID, file: UploadFile = File(...),
                    title: str | None = Form(None, max_length=300), category: str | None = Form(None, max_length=40),
                    organization_id: uuid.UUID | None = Form(None), event_id: uuid.UUID | None = Form(None),
                    db: Session = Depends(get_db), user: User = Depends(require_clinical)):
    policy = AccessPolicy(db, user)
    policy.require_self(patient_id, "document.upload")
    if not limiter.hit(f"upload:{user.id}", 20, 60):
        raise HTTPException(429, "Too many uploads. Please wait a minute.")
    max_bytes = get_settings().max_upload_bytes
    data = file.file.read(max_bytes + 1)
    if event_id:
        ev = db.get(JourneyEvent, event_id)
        if not ev or ev.patient_id != patient_id:
            raise HTTPException(404, "Event not found")
    if organization_id and not db.get(Organization, organization_id):
        raise HTTPException(422, "Unknown organization")
    try:
        doc = docsvc.create_document(db, patient_id, user, file.filename or "upload", data, max_bytes=max_bytes,
                                     title=title or None, category=category or None,
                                     organization_id=organization_id, event_id=event_id)
    except UploadRejected as exc:
        db.rollback()
        audit.record(db, "document.upload", actor=user, outcome="denied", patient_id=patient_id,
                     detail={"reason": exc.code}, commit=True)
        return JSONResponse(status_code=422, content={"detail": exc.message, "code": exc.code})
    except docsvc.DuplicateDocument as exc:
        db.rollback()
        return JSONResponse(status_code=409, content={"detail": "This exact file has already been uploaded.",
                                                      "code": "duplicate", "existing_id": str(exc.existing.id)})
    audit.record(db, "document.upload", actor=user, resource_type="document", resource_id=doc.id, patient_id=patient_id,
                 detail={"size": doc.size_bytes, "mime": doc.mime_type})
    db.commit()
    db.refresh(doc)
    return document_out(doc)


@router.get("/documents/{document_id}")
def get_document(document_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_clinical)):
    policy = AccessPolicy(db, user)
    doc = policy.get_document(document_id)
    accessible = policy.accessible_document_ids(doc.patient_id)
    versions = db.execute(select(Document).where(Document.lineage_id == doc.lineage_id, Document.deleted_at.is_(None))
                          .order_by(Document.version)).scalars().all()
    recs = db.execute(select(Recommendation).where(Recommendation.document_id == doc.id)
                      .order_by(Recommendation.char_start.nulls_last())).scalars().all()
    events = db.execute(select(JourneyEvent).where(JourneyEvent.documents.any(Document.id == doc.id))).scalars().all()
    out = document_out(doc, include_text=True)
    out["versions"] = [{"id": str(v.id), "version": v.version, "created_at": v.created_at.isoformat(),
                        "is_latest": v.is_latest} for v in versions if v.id in accessible]
    out["recommendations"] = [recommendation_out(r) for r in recs]
    out["events"] = [event_out(e, accessible) for e in events] if policy.can_view_patient_section(doc.patient_id, "journey") else []
    out["can_edit"] = policy.is_self(doc.patient_id)
    _audit_access(db, user, "document.view", doc)
    db.commit()
    return out


@router.get("/documents/{document_id}/download")
def download_document(document_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_clinical)):
    policy = AccessPolicy(db, user)
    doc = policy.get_document(document_id, "document.download")
    data = get_storage().get(doc.storage_key)
    _audit_access(db, user, "document.download", doc)
    db.commit()
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", doc.original_filename)[:120] or "document"
    return Response(content=data, media_type="application/octet-stream", headers={
        "Content-Disposition": f'attachment; filename="{safe}"', "X-Content-Type-Options": "nosniff",
        "Cache-Control": "no-store"})


class DocumentPatch(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=300)
    category: str | None = None
    document_date: date | None = None
    organization_id: uuid.UUID | None = None
    author_name: str | None = Field(None, max_length=200)


@router.patch("/documents/{document_id}")
def patch_document(document_id: uuid.UUID, body: DocumentPatch, db: Session = Depends(get_db),
                   user: User = Depends(require_clinical)):
    policy = AccessPolicy(db, user)
    doc = policy.get_document(document_id, "document.update")
    policy.require_self(doc.patient_id, "document.update")
    changes = body.model_dump(exclude_unset=True)
    if "category" in changes and changes["category"] not in docsvc.CATEGORIES:
        raise HTTPException(422, "Unknown category")
    if changes.get("organization_id") and not db.get(Organization, changes["organization_id"]):
        raise HTTPException(422, "Unknown organization")
    for k, v in changes.items():
        setattr(doc, k, v)
    if "document_date" in changes:
        db.execute(Recommendation.__table__.update().where(Recommendation.document_id == doc.id)
                   .values(documented_at=doc.document_date))
    audit.record(db, "document.update", actor=user, resource_type="document", resource_id=doc.id,
                 patient_id=doc.patient_id, detail={"fields": sorted(changes)})
    db.flush()
    evaluate_patient(db, doc.patient_id)
    db.commit()
    db.refresh(doc)
    return document_out(doc)


@router.post("/documents/{document_id}/versions", status_code=201)
def upload_version(document_id: uuid.UUID, file: UploadFile = File(...), db: Session = Depends(get_db),
                   user: User = Depends(require_clinical)):
    policy = AccessPolicy(db, user)
    parent = policy.get_document(document_id, "document.version")
    policy.require_self(parent.patient_id, "document.version")
    if not parent.is_latest:
        raise HTTPException(409, "Only the latest version can be superseded.")
    max_bytes = get_settings().max_upload_bytes
    data = file.file.read(max_bytes + 1)
    try:
        doc = docsvc.create_document(db, parent.patient_id, user, file.filename or "upload", data, max_bytes=max_bytes,
                                     title=parent.title, category=parent.category,
                                     organization_id=parent.organization_id, parent=parent)
    except UploadRejected as exc:
        db.rollback()
        return JSONResponse(status_code=422, content={"detail": exc.message, "code": exc.code})
    except docsvc.DuplicateDocument as exc:
        db.rollback()
        return JSONResponse(status_code=409, content={"detail": "This exact file has already been uploaded.",
                                                      "code": "duplicate", "existing_id": str(exc.existing.id)})
    audit.record(db, "document.version", actor=user, resource_type="document", resource_id=doc.id,
                 patient_id=doc.patient_id, detail={"parent": str(parent.id), "version": doc.version})
    db.commit()
    db.refresh(doc)
    return document_out(doc)


@router.post("/documents/{document_id}/reprocess")
def reprocess(document_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_clinical)):
    policy = AccessPolicy(db, user)
    doc = policy.get_document(document_id, "document.reprocess")
    policy.require_self(doc.patient_id, "document.reprocess")
    doc.status, doc.status_detail, doc.attempts = "pending", None, 0
    audit.record(db, "document.reprocess", actor=user, resource_type="document", resource_id=doc.id, patient_id=doc.patient_id)
    db.commit()
    return document_out(doc)


@router.delete("/documents/{document_id}")
def delete_document(document_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_clinical)):
    """Patient-initiated deletion: removes the stored file and search index; metadata is tombstoned."""
    policy = AccessPolicy(db, user)
    doc = policy.get_document(document_id, "document.delete")
    policy.require_self(doc.patient_id, "document.delete")
    doc.deleted_at = utcnow()
    doc.extracted_text = None
    db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == doc.id))
    db.execute(FollowUpTask.__table__.update().where(FollowUpTask.evidence_document_id == doc.id)
               .values(evidence_document_id=None))
    if doc.is_latest and doc.version > 1:
        prev = db.execute(select(Document).where(Document.lineage_id == doc.lineage_id, Document.deleted_at.is_(None),
                                                 Document.id != doc.id).order_by(Document.version.desc())).scalars().first()
        if prev:
            prev.is_latest = True
    get_storage().delete(doc.storage_key)
    audit.record(db, "document.delete", actor=user, resource_type="document", resource_id=doc.id, patient_id=doc.patient_id)
    db.flush()
    evaluate_patient(db, doc.patient_id)
    db.commit()
    return {"ok": True}


@router.get("/patients/{patient_id}/fhir/export")
def fhir_export(patient_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_clinical)):
    policy = AccessPolicy(db, user)
    policy.require_self(patient_id, "fhir.export")
    patient = db.get(User, patient_id)
    events = db.execute(select(JourneyEvent).where(JourneyEvent.patient_id == patient_id)).scalars().all()
    docs = db.execute(select(Document).where(Document.patient_id == patient_id, Document.deleted_at.is_(None))).scalars().all()
    recs = db.execute(select(Recommendation).where(Recommendation.patient_id == patient_id,
                                                   Recommendation.review_status != "rejected")).scalars().all()
    tasks = db.execute(select(FollowUpTask).where(FollowUpTask.patient_id == patient_id)).scalars().all()
    audit.record(db, "fhir.export", actor=user, resource_type="patient", resource_id=patient_id, patient_id=patient_id,
                 detail={"entries": 1 + len(events) + len(docs) + len(recs) + len(tasks)})
    db.commit()
    return JSONResponse(export_bundle(patient, events, docs, recs, tasks), media_type="application/fhir+json",
                        headers={"Content-Disposition": 'attachment; filename="healthbridge-export.fhir.json"'})
