"""Document intake (synchronous, in the request) and processing (asynchronous, in the worker)."""
import hashlib
import json
import logging
import uuid
from datetime import datetime, time, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import audit
from app.models import (
    Document,
    EventDocument,
    JourneyEvent,
    Organization,
    Recommendation,
    User,
    utcnow,
)
from app.observability import log_event, metrics
from app.security.storage import get_storage
from app.services import extraction, rag
from app.services.fhir import import_fhir
from app.services.notifications import notify

log = logging.getLogger(__name__)

CATEGORIES = ["consultation_note", "lab_result", "imaging_report", "referral", "discharge_summary",
              "consultation_summary", "fhir_record", "other"]


class DuplicateDocument(Exception):
    def __init__(self, existing: Document) -> None:
        super().__init__("duplicate")
        self.existing = existing


def create_document(db: Session, patient_id: uuid.UUID, uploader: User, filename: str, data: bytes, *,
                    max_bytes: int, title: str | None = None, category: str | None = None,
                    organization_id: uuid.UUID | None = None, parent: Document | None = None,
                    event_id: uuid.UUID | None = None) -> Document:
    validated = extraction.validate_upload(filename, data, max_bytes)
    sha = hashlib.sha256(data).hexdigest()
    dup = db.execute(select(Document).where(Document.patient_id == patient_id, Document.sha256 == sha,
                                            Document.deleted_at.is_(None))).scalars().first()
    if dup:
        raise DuplicateDocument(dup)
    storage_key = get_storage().put(data)
    doc = Document(
        id=uuid.uuid4(), patient_id=patient_id, uploaded_by=uploader.id, organization_id=organization_id,
        title=(title or filename.rsplit(".", 1)[0])[:300], category=category if category in CATEGORIES else "other",
        original_filename=filename[:255], mime_type=validated.mime_type, size_bytes=len(data), sha256=sha,
        storage_key=storage_key, encrypted=True, status="pending",
        lineage_id=parent.lineage_id if parent else uuid.uuid4(), version=(parent.version + 1) if parent else 1,
        import_report={"user_title": bool(title), "user_category": bool(category), "link_event_id": str(event_id) if event_id else None},
    )
    db.add(doc)
    if parent:
        parent.is_latest = False
        db.flush()
        for link in db.execute(select(EventDocument).where(EventDocument.document_id == parent.id)).scalars().all():
            db.add(EventDocument(event_id=link.event_id, document_id=doc.id))
    db.flush()
    metrics.incr("documents.uploaded")
    return doc


def _kind_for(doc: Document) -> str:
    return {"application/pdf": "pdf", "application/fhir+json": "fhir"}.get(doc.mime_type, "text")


_EVENT_FOR_CATEGORY = {
    "lab_result": "lab_test", "imaging_report": "imaging", "referral": "referral",
    "discharge_summary": "hospital_visit", "consultation_summary": "international_consultation",
}
_EVENT_FOR_ORG_KIND = {"hmo": "hmo_consultation", "private_clinic": "specialist_consultation",
                       "hospital": "hospital_visit", "international_clinic": "international_consultation",
                       "laboratory": "lab_test", "imaging": "imaging"}


def _event_type(doc: Document, org: Organization | None) -> str:
    if doc.category in _EVENT_FOR_CATEGORY:
        return _EVENT_FOR_CATEGORY[doc.category]
    if org and org.kind in _EVENT_FOR_ORG_KIND:
        return _EVENT_FOR_ORG_KIND[org.kind]
    return "specialist_consultation" if doc.category == "consultation_note" else "other"


def _occurred(d) -> datetime:
    return datetime.combine(d, time(9, 0), tzinfo=timezone.utc)


def _link_or_create_event(db: Session, doc: Document, org: Organization | None) -> JourneyEvent:
    link_id = (doc.import_report or {}).get("link_event_id")
    if link_id:
        ev = db.get(JourneyEvent, uuid.UUID(link_id))
        if ev and ev.patient_id == doc.patient_id:
            if doc not in ev.documents:
                ev.documents.append(doc)
            return ev
    existing = db.execute(select(JourneyEvent).join(EventDocument).where(EventDocument.document_id == doc.id)).scalars().first()
    if existing:
        return existing
    etype = _event_type(doc, org)
    when = _occurred(doc.document_date) if doc.document_date else doc.created_at
    if doc.document_date and doc.organization_id:  # attach to a matching manual event on the same day
        candidates = db.execute(select(JourneyEvent).where(
            JourneyEvent.patient_id == doc.patient_id, JourneyEvent.organization_id == doc.organization_id,
            JourneyEvent.event_type == etype)).scalars()
        for ev in candidates:
            if abs((ev.occurred_at.date() - doc.document_date).days) <= 1:
                ev.documents.append(doc)
                if ev.verification_status in ("unverified", "patient_reported"):
                    ev.verification_status = "documented"
                return ev
    ev = JourneyEvent(
        patient_id=doc.patient_id, event_type=etype, title=doc.title, organization_id=doc.organization_id,
        occurred_at=when, verification_status="documented" if doc.document_date else "unverified",
        provenance="document", provenance_detail=f"Created from document '{doc.title}' ({doc.original_filename})",
        created_by=doc.uploaded_by,
    )
    ev.documents.append(doc)
    db.add(ev)
    db.flush()
    return ev


def process_document(db: Session, doc: Document) -> None:
    """Extract, index, link and evaluate. Caller commits."""
    from app.services.care_gaps import evaluate_patient

    doc.attempts += 1
    data = get_storage().get(doc.storage_key)
    kind = _kind_for(doc)
    flags = doc.import_report or {}
    fhir_result = None
    if kind == "fhir":
        fhir_result = import_fhir(json.loads(data.decode("utf-8-sig")))
        text, status, detail = fhir_result.text, "processed", None
        if fhir_result.report["errors"] and not fhir_result.report["imported"]:
            status, detail = "failed", "No FHIR resources could be imported: " + "; ".join(fhir_result.report["errors"][:3])
        flags = {**flags, "fhir": fhir_result.report}
        if not flags.get("user_category"):
            doc.category = "fhir_record"
        if not flags.get("user_title"):
            labels = [e.title for e in fhir_result.events if e.event_type == "lab_test" and e.title.startswith("Lab result")]
            labels = labels or [e.title for e in fhir_result.events] or [r.text for r in fhir_result.recommendations]
            doc.title = ("FHIR import: " + ", ".join(dict.fromkeys(labels))[:200]) if labels else "FHIR import"
    else:
        res = extraction.extract_text(kind, data)
        text, status, detail = res.text, res.status, res.detail

    doc.extracted_text = text
    doc.text_sha256 = hashlib.sha256(text.encode()).hexdigest() if text else None
    orgs = list(db.execute(select(Organization)).scalars())
    md = extraction.extract_metadata(text or "", [o.name for o in orgs])
    doc.language = md.language
    doc.document_date = doc.document_date or md.document_date
    doc.author_name = doc.author_name or md.author
    doc.source_detected = md.source
    if not doc.organization_id and md.organization_name:
        doc.organization_id = next(o.id for o in orgs if o.name == md.organization_name)
    if not flags.get("user_title") and md.title and kind != "fhir":
        doc.title = md.title
    if not flags.get("user_category") and doc.category == "other":
        doc.category = md.category
    if text and doc.text_sha256:
        twin = db.execute(select(Document.id).where(
            Document.patient_id == doc.patient_id, Document.text_sha256 == doc.text_sha256,
            Document.id != doc.id, Document.deleted_at.is_(None))).scalars().first()
        doc.duplicate_of_id = twin
    doc.import_report = flags

    if status == "failed":
        doc.status, doc.status_detail = "failed", detail
        doc.processed_at = utcnow()
        return

    rag.index_document(db, doc)
    org = db.get(Organization, doc.organization_id) if doc.organization_id else None
    event = _link_or_create_event(db, doc, org) if kind != "fhir" else None

    # Re-processing replaces only unreviewed extracted items; human-reviewed items are preserved.
    db.execute(delete(Recommendation).where(Recommendation.document_id == doc.id,
                                            Recommendation.review_status == "pending_review",
                                            Recommendation.source.in_(["extracted", "fhir"])))
    documented_at = doc.document_date or doc.created_at.date()
    if kind == "fhir":
        org_by_name = {o.name.lower(): o for o in orgs}
        seen_events: set[tuple] = set()
        for me in fhir_result.events:
            key = (me.event_type, me.occurred_at.date())
            if key in seen_events:  # e.g. an Encounter and its Observation on the same day
                continue
            seen_events.add(key)
            o = org_by_name.get((me.organization_name or "").lower())
            ev = JourneyEvent(patient_id=doc.patient_id, event_type=me.event_type, title=me.title[:300],
                              description=me.description or None, organization_id=o.id if o else None,
                              occurred_at=me.occurred_at, verification_status="documented",
                              provenance="fhir_import", provenance_detail=f"{me.fhir_ref} in '{doc.original_filename}'",
                              created_by=doc.uploaded_by)
            ev.documents.append(doc)
            db.add(ev)
        for mr in fhir_result.recommendations:
            db.add(Recommendation(patient_id=doc.patient_id, document_id=doc.id, kind=mr.kind, text=mr.text[:2000],
                                  passage=mr.text[:2000], source="fhir", documented_at=mr.authored_on or documented_at,
                                  target=",".join(extraction.find_terms(mr.text)), review_status="pending_review"))
        if fhir_result.events and not doc.document_date:
            doc.document_date = min(e.occurred_at for e in fhir_result.events).date()
    else:
        for r in extraction.extract_recommendations(text or ""):
            db.add(Recommendation(
                patient_id=doc.patient_id, document_id=doc.id, event_id=event.id if event else None, kind=r.kind,
                text=r.text, passage=r.passage, char_start=r.char_start, char_end=r.char_end,
                timeframe_text=r.timeframe_text, due_date=r.due_date, target=",".join(r.targets),
                review_status="pending_review", source="extracted", documented_at=documented_at))

    doc.status = status if status == "needs_review" else "processed"
    doc.status_detail = detail
    doc.processed_at = utcnow()
    db.flush()
    evaluate_patient(db, doc.patient_id)
    notify(db, doc.patient_id, "document_processed",
           f"Document processed: {doc.title[:200]}" if doc.status == "processed" else f"Document needs review: {doc.title[:200]}",
           detail, f"/app/documents/{doc.id}", dedupe_key=f"docproc:{doc.id}:{doc.attempts}")
    audit.record(db, "document.processed", resource_type="document", resource_id=doc.id, patient_id=doc.patient_id,
                 detail={"status": doc.status, "chunks": "indexed", "kind": kind})
    metrics.incr(f"documents.{doc.status}")
    log_event(log, "document.processed", document_id=str(doc.id), status=doc.status, kind=kind)


def process_pending(db_factory, limit: int = 5) -> int:
    """Claim and process pending documents (FOR UPDATE SKIP LOCKED). Returns count processed."""
    processed = 0
    for _ in range(limit):
        with db_factory() as db:
            doc = db.execute(select(Document).where(Document.status == "pending", Document.deleted_at.is_(None))
                             .order_by(Document.created_at).limit(1).with_for_update(skip_locked=True)).scalars().first()
            if not doc:
                break
            doc_id = doc.id
            try:
                doc.status = "processing"
                db.flush()
                process_document(db, doc)
                db.commit()
            except Exception as exc:
                db.rollback()
                metrics.incr("documents.failed")
                log_event(log, "document.processing_failed", logging.ERROR, document_id=str(doc_id),
                          error_type=type(exc).__name__)
                with db_factory() as db2:
                    d = db2.get(Document, doc_id)
                    if d:
                        d.attempts += 1
                        d.status = "failed" if d.attempts >= 3 else "pending"
                        d.status_detail = "Processing failed; the error has been logged." if d.status == "failed" else None
                        db2.commit()
            processed += 1
    return processed
