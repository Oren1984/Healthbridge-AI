"""Explicit output shapes. Nothing is serialized implicitly from ORM objects."""
from app.models import (
    CareGap,
    ConsentGrant,
    Consultation,
    ConsultationSummary,
    Document,
    FollowUpTask,
    JourneyEvent,
    Notification,
    Organization,
    Recommendation,
    User,
    utcnow,
)


def iso(v):
    return v.isoformat() if v else None


def org_out(o: Organization | None) -> dict | None:
    if not o:
        return None
    return {"id": str(o.id), "name": o.name, "name_he": o.name_he, "kind": o.kind, "country": o.country,
            "city": o.city, "synthetic": o.synthetic}


def user_brief(u: User | None) -> dict | None:
    if not u:
        return None
    out = {"id": str(u.id), "full_name": u.full_name, "role": u.role, "country": u.country, "timezone": u.timezone}
    if u.professional:
        p = u.professional
        out["professional"] = {"specialty": p.specialty, "verification_status": p.verification_status,
                               "organization": org_out(p.organization)}
    return out


def user_out(u: User) -> dict:
    out = {**user_brief(u), "email": u.email, "locale": u.locale, "is_active": u.is_active,
           "last_login_at": iso(u.last_login_at)}
    if u.professional:
        out["professional"]["license_number"] = u.professional.license_number
        out["professional"]["verified_at"] = iso(u.professional.verified_at)
    if u.patient:
        out["patient"] = {"date_of_birth": iso(u.patient.date_of_birth),
                          "default_share_days": u.patient.default_share_days,
                          "show_access_alerts": u.patient.show_access_alerts}
    return out


def document_out(d: Document, include_text: bool = False) -> dict:
    out = {
        "id": str(d.id), "patient_id": str(d.patient_id), "title": d.title, "category": d.category,
        "original_filename": d.original_filename, "mime_type": d.mime_type, "size_bytes": d.size_bytes,
        "status": d.status, "status_detail": d.status_detail, "document_date": iso(d.document_date),
        "author_name": d.author_name, "source_detected": d.source_detected, "language": d.language,
        "organization": org_out(d.organization), "version": d.version, "lineage_id": str(d.lineage_id),
        "is_latest": d.is_latest, "duplicate_of_id": str(d.duplicate_of_id) if d.duplicate_of_id else None,
        "encrypted": d.encrypted, "created_at": iso(d.created_at), "processed_at": iso(d.processed_at),
        "uploaded_by": str(d.uploaded_by),
        "import_report": (d.import_report or {}).get("fhir"),
    }
    if include_text:
        out["extracted_text"] = d.extracted_text
    return out


def event_out(e: JourneyEvent, visible_doc_ids: set | None = None) -> dict:
    docs = [x for x in e.documents if x.deleted_at is None and (visible_doc_ids is None or x.id in visible_doc_ids)]
    return {
        "id": str(e.id), "event_type": e.event_type, "title": e.title, "description": e.description,
        "organization": org_out(e.organization), "occurred_at": iso(e.occurred_at),
        "verification_status": e.verification_status, "provenance": e.provenance,
        "provenance_detail": e.provenance_detail, "consultation_id": str(e.consultation_id) if e.consultation_id else None,
        "documents": [{"id": str(x.id), "title": x.title, "category": x.category} for x in docs],
        "hidden_documents": len([x for x in e.documents if x.deleted_at is None]) - len(docs),
        "created_at": iso(e.created_at),
    }


def recommendation_out(r: Recommendation) -> dict:
    return {
        "id": str(r.id), "document_id": str(r.document_id) if r.document_id else None,
        "document_title": r.document.title if r.document else None,
        "event_id": str(r.event_id) if r.event_id else None, "kind": r.kind, "text": r.text,
        "original_text": r.original_text, "passage": r.passage, "char_start": r.char_start, "char_end": r.char_end,
        "timeframe_text": r.timeframe_text, "due_date": iso(r.due_date), "targets": [t for t in (r.target or "").split(",") if t],
        "review_status": r.review_status, "source": r.source, "documented_at": iso(r.documented_at),
        "reviewed_at": iso(r.reviewed_at), "created_at": iso(r.created_at),
    }


def task_out(t: FollowUpTask) -> dict:
    return {
        "id": str(t.id), "patient_id": str(t.patient_id), "kind": t.kind, "title": t.title, "description": t.description,
        "recommendation_id": str(t.recommendation_id) if t.recommendation_id else None,
        "care_gap_id": str(t.care_gap_id) if t.care_gap_id else None,
        "owner_id": str(t.owner_id) if t.owner_id else None, "due_date": iso(t.due_date),
        "due_date_source": t.due_date_source, "status": t.status,
        "evidence_document_id": str(t.evidence_document_id) if t.evidence_document_id else None,
        "completion_note": t.completion_note, "completed_at": iso(t.completed_at), "verified_at": iso(t.verified_at),
        "reminder_days_before": t.reminder_days_before, "created_at": iso(t.created_at), "updated_at": iso(t.updated_at),
    }


def gap_out(g: CareGap) -> dict:
    from app.services.care_gaps import RULES

    return {
        "id": str(g.id), "rule_id": g.rule_id, "rule": RULES.get(g.rule_id), "title": g.title,
        "description": g.description, "status": g.status, "computed_status": g.computed_status,
        "review_status": g.review_status, "supporting_evidence": g.supporting_evidence,
        "missing_evidence": g.missing_evidence, "document_ids": g.document_ids, "relevant_dates": g.relevant_dates,
        "suggested_clarification": g.suggested_clarification, "params": g.params,
        "recommendation_id": str(g.recommendation_id) if g.recommendation_id else None, "active": g.active,
        "review_note": g.review_note, "reviewed_at": iso(g.reviewed_at),
        "first_detected_at": iso(g.first_detected_at), "last_evaluated_at": iso(g.last_evaluated_at),
    }


REDACTED_TEXT = "Details come from information that has not been shared with you."


def gap_view(g: CareGap, policy) -> dict:
    """Care gap as seen by `policy.user`.

    Patients see everything. Other viewers (professionals with care-gap access) only see content whose source they
    can already see: documents in their consent scope, journey events and tasks only with journey access, and
    consultations they participate in. Anything else is dropped or replaced with REDACTED_TEXT.
    """
    out = gap_out(g)
    if policy.is_self(g.patient_id):
        return out
    import uuid as _uuid

    from sqlalchemy import select

    visible = {str(i) for i in policy.accessible_document_ids(g.patient_id)}
    journey = policy.can_view_patient_section(g.patient_id, "journey")
    rec_ids = {e["id"] for e in g.supporting_evidence if e.get("type") == "recommendation"}
    if g.recommendation_id:
        rec_ids.add(str(g.recommendation_id))
    rec_doc = {}
    if rec_ids:
        rows = policy.db.execute(select(Recommendation.id, Recommendation.document_id)
                                 .where(Recommendation.id.in_([_uuid.UUID(r) for r in rec_ids]))).all()
        rec_doc = {str(rid): (str(did) if did else None) for rid, did in rows}
    consults = {}
    for cid in {e["id"] for e in g.supporting_evidence if e.get("type") == "consultation"}:
        c = policy.db.get(Consultation, _uuid.UUID(cid))
        consults[cid] = bool(c) and any(p.user_id == policy.user.id and p.invite_status != "declined" for p in c.participants)

    def allowed(e: dict) -> bool:
        kind = e.get("type")
        if kind == "document":
            return e["id"] in visible
        if kind == "recommendation":
            d = rec_doc.get(e["id"])
            return d is None or d in visible
        if kind in ("event", "task"):
            return journey
        if kind == "consultation":
            return consults.get(e["id"], False)
        return False  # handoffs and any future evidence type: never shown to other viewers

    out["supporting_evidence"] = [e for e in g.supporting_evidence if allowed(e)]
    out["document_ids"] = [d for d in g.document_ids if d in visible]
    rec_source = rec_doc.get(str(g.recommendation_id)) if g.recommendation_id else None
    # Title/suggestion/params come from the recommendation's document, the gap's own documents, a journey event
    # (CG-006 date mismatch, CG-008) or a consultation (CG-004); hide them when that source is out of scope.
    kinds = {e.get("type") for e in g.supporting_evidence}
    hidden_source = (
        (rec_source is not None and rec_source not in visible)
        or (not g.recommendation_id and bool(g.document_ids) and not any(d in visible for d in g.document_ids))
        or (g.rule_id in ("CG-006", "CG-008") and "event" in kinds and not journey)
        or (g.rule_id == "CG-004" and not any(consults.values())))
    if hidden_source:
        out["title"] = f"{(g.title.split(':', 1)[0] if ':' in g.title else 'Recommendation')}: {REDACTED_TEXT}"
        out["suggested_clarification"] = None
        out["params"] = {k: v for k, v in (g.params or {}).items() if k in ("kind", "label", "pending_review")} | {
            "text": REDACTED_TEXT, "title": REDACTED_TEXT, "redacted": True}
        out["relevant_dates"] = {k: v for k, v in (g.relevant_dates or {}).items() if k != "documented_timeframe"}
    if g.rule_id in ("CG-009", "CG-005"):  # findings about other professionals' access
        out["title"] = "Information sharing item"
        out["description"] = REDACTED_TEXT
        out["suggested_clarification"] = None
        out["params"] = {"redacted": True}
        out["supporting_evidence"], out["missing_evidence"], out["document_ids"] = [], [], []
        out["relevant_dates"] = {k: v for k, v in (g.relevant_dates or {}).items() if k == "evaluated"}
    out["redacted_for_viewer"] = out != gap_out(g)
    return out


def grant_out(g: ConsentGrant) -> dict:
    now = utcnow()
    state = "revoked" if g.revoked_at else ("expired" if g.expires_at <= now else ("scheduled" if g.starts_at > now else "active"))
    return {
        "id": str(g.id), "patient_id": str(g.patient_id), "grantee": user_brief(g.grantee),
        "documents": [{"id": str(d.id), "title": d.title, "category": d.category} for d in g.documents if d.deleted_at is None],
        "categories": g.categories, "include_journey": g.include_journey, "include_care_gaps": g.include_care_gaps,
        "purpose": g.purpose, "consultation_id": str(g.consultation_id) if g.consultation_id else None,
        "starts_at": iso(g.starts_at), "expires_at": iso(g.expires_at), "revoked_at": iso(g.revoked_at),
        "created_at": iso(g.created_at), "state": state,
    }


def consultation_out(c: Consultation, viewer: User | None = None) -> dict:
    return {
        "id": str(c.id), "patient_id": str(c.patient_id), "title": c.title, "purpose": c.purpose,
        "scheduled_start": iso(c.scheduled_start), "duration_minutes": c.duration_minutes, "status": c.status,
        "created_at": iso(c.created_at), "completed_at": iso(c.completed_at), "recording": "disabled",
        "participants": [{"user": user_brief(p.user), "meeting_role": p.meeting_role, "invite_status": p.invite_status,
                          "joined_at": iso(p.joined_at), "left_at": iso(p.left_at)} for p in c.participants],
        "documents": [{"id": str(d.id), "title": d.title, "category": d.category} for d in c.documents if d.deleted_at is None],
        "my_invite_status": next((p.invite_status for p in c.participants if viewer and p.user_id == viewer.id), None),
    }


def summary_out(s: ConsultationSummary, professional_ids: list) -> dict:
    approvals = {a.professional_id: a for a in s.approvals}
    return {
        "id": str(s.id), "consultation_id": str(s.consultation_id), "version": s.version, "status": s.status,
        "discussion": s.discussion, "observations": s.observations, "proposed_followups": s.proposed_followups,
        "referenced_document_ids": s.referenced_document_ids, "ai_generated_draft": s.ai_generated_draft,
        "author": user_brief(s.author), "created_at": iso(s.created_at), "approved_at": iso(s.approved_at),
        "patient_acknowledged_at": iso(s.patient_acknowledged_at),
        "document_id": str(s.document_id) if s.document_id else None,
        "approvals": [{"professional": user_brief(a.professional), "decision": a.decision, "comment": a.comment,
                       "at": iso(a.created_at)} for a in s.approvals],
        "awaiting_approval_from": [str(pid) for pid in professional_ids if pid not in approvals
                                   or approvals[pid].decision != "approved"],
    }


def notification_out(n: Notification) -> dict:
    return {"id": str(n.id), "kind": n.kind, "title": n.title, "body": n.body, "link": n.link,
            "channel": n.channel, "created_at": iso(n.created_at), "read_at": iso(n.read_at)}
