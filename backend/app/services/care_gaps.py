"""Care Gap Intelligence Engine — deterministic, evidence-based continuity checks.

Design
- `evaluate_snapshot()` is a pure function of an immutable `Snapshot` and an `as_of` date, so every
  finding can be replayed and unit-tested.
- Absence of evidence is reported as UNKNOWN — never as "not done". The engine never infers
  urgency, diagnoses, or suggests treatment; suggestions are administrative questions only.
- Status vocabulary: completed_verified | open | unknown | requires_clarification | not_applicable.
"""
import hashlib
import re
import uuid
from dataclasses import dataclass, field
from datetime import date

COMPLETED = "completed_verified"
OPEN = "open"
UNKNOWN = "unknown"
CLARIFY = "requires_clarification"
NOT_APPLICABLE = "not_applicable"

_GP = re.compile(r"(?i)family (physician|doctor)|\bgp\b|primary care|רופא(ת)? המשפחה")
LAB_TERMS = {"cbc", "lipid_panel", "hba1c", "tsh", "troponin"}
CONSULT_EVENTS = {"specialist_consultation", "international_consultation", "hmo_consultation", "follow_up_appointment"}
EXPECTED_DOC = {
    "imaging": ({"imaging_report"}, "imaging report"),
    "lab_test": ({"lab_result", "fhir_record"}, "laboratory result"),
    "hospital_visit": ({"discharge_summary"}, "discharge summary"),
    "discharge": ({"discharge_summary"}, "discharge summary"),
    "specialist_consultation": ({"consultation_note", "consultation_summary", "referral"}, "consultation letter"),
    "international_consultation": ({"consultation_summary", "consultation_note"}, "consultation summary"),
}

RULES = {
    "CG-001": "Recommended follow-up or imaging without documented completion",
    "CG-002": "Referral without a documented outcome",
    "CG-003": "Laboratory recommendation without an available result",
    "CG-004": "Completed consultation without an approved summary",
    "CG-005": "Shared handoff not acknowledged by the receiving professional",
    "CG-006": "Conflicting dates between an event and its document",
    "CG-007": "Contradictory recommendations across documents",
    "CG-008": "Expected document not received",
    "CG-009": "Information not available to a consultation participant",
}


# ------------------------------------------------------------------ snapshot types
@dataclass(frozen=True)
class RecSnap:
    id: uuid.UUID
    kind: str
    text: str
    targets: tuple[str, ...]
    documented_at: date | None
    document_id: uuid.UUID | None
    document_title: str | None
    review_status: str
    timeframe_text: str | None
    passage: str | None


@dataclass(frozen=True)
class DocSnap:
    id: uuid.UUID
    title: str
    category: str
    document_date: date | None
    terms: tuple[str, ...]
    organization_id: uuid.UUID | None


@dataclass(frozen=True)
class EventSnap:
    id: uuid.UUID
    event_type: str
    title: str
    occurred_on: date
    organization_id: uuid.UUID | None
    document_ids: tuple[uuid.UUID, ...]
    verification_status: str
    terms: tuple[str, ...]


@dataclass(frozen=True)
class TaskSnap:
    id: uuid.UUID
    recommendation_id: uuid.UUID | None
    kind: str
    status: str
    evidence_document_id: uuid.UUID | None
    completed_at: date | None


@dataclass(frozen=True)
class ConsultSnap:
    id: uuid.UUID
    title: str
    status: str
    scheduled_on: date
    has_approved_summary: bool
    professionals: tuple[tuple[uuid.UUID, str], ...]  # (user_id, display name)
    attached_document_ids: tuple[uuid.UUID, ...]


@dataclass(frozen=True)
class HandoffSnap:
    id: uuid.UUID
    status: str
    shared_on: date | None
    acknowledged: bool
    to_name: str


@dataclass(frozen=True)
class Snapshot:
    recommendations: tuple[RecSnap, ...] = ()
    documents: tuple[DocSnap, ...] = ()
    events: tuple[EventSnap, ...] = ()
    tasks: tuple[TaskSnap, ...] = ()
    consultations: tuple[ConsultSnap, ...] = ()
    handoffs: tuple[HandoffSnap, ...] = ()
    # professional_id -> set of document ids accessible via active grants
    access: dict = field(default_factory=dict)


@dataclass
class Finding:
    rule_id: str
    fingerprint: str
    title: str
    description: str
    status: str
    supporting_evidence: list[dict] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    document_ids: list[str] = field(default_factory=list)
    relevant_dates: dict = field(default_factory=dict)
    suggested_clarification: str | None = None
    recommendation_id: uuid.UUID | None = None
    params: dict = field(default_factory=dict)


def _fp(*parts) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:40]


def _ev(kind: str, obj_id, label: str, detail: str | None = None) -> dict:
    return {"type": kind, "id": str(obj_id), "label": label, **({"detail": detail} if detail else {})}


def _d(x: date | None) -> str | None:
    return x.isoformat() if x else None


# ------------------------------------------------------------------ rule helpers
def _task_state(snap: Snapshot, rec: RecSnap, docs: dict[uuid.UUID, DocSnap]):
    """Return (status|None, evidence, missing) derived from follow-up tasks linked to the rec."""
    tasks = [t for t in snap.tasks if t.recommendation_id == rec.id and t.kind == "follow_up"]
    if not tasks:
        return None, [], []
    # Most decisive task wins: verified > not_applicable > reported > open
    order = {"completed_verified": 0, "not_applicable": 1, "completed_reported": 2, "open": 3}
    t = sorted(tasks, key=lambda x: order.get(x.status, 9))[0]
    if t.status == "completed_verified" and t.evidence_document_id in docs:
        d = docs[t.evidence_document_id]
        return COMPLETED, [_ev("task", t.id, "Follow-up task verified with evidence"),
                           _ev("document", d.id, d.title, f"Evidence document dated {_d(d.document_date) or 'unknown'}")], []
    if t.status == "not_applicable":
        return NOT_APPLICABLE, [_ev("task", t.id, "Task dismissed by an authorized user")], []
    if t.status == "completed_reported":
        return UNKNOWN, [_ev("task", t.id, "Reported as completed without a supporting document")], \
            ["A document confirming completion (report, result or letter)"]
    return OPEN, [_ev("task", t.id, "Follow-up task documented as pending")], []


def _rec_evidence(rec: RecSnap) -> dict:
    return _ev("recommendation", rec.id, rec.text, f"From '{rec.document_title}'" if rec.document_title else None)


def _later(d: date | None, ref: date | None) -> bool:
    return d is not None and (ref is None or d >= ref)


# ------------------------------------------------------------------ rules
def rule_recommendation_completion(snap: Snapshot, docs, as_of: date) -> list[Finding]:
    """CG-001 (follow-up/imaging/other), CG-002 (referral), CG-003 (lab)."""
    out: list[Finding] = []
    for rec in snap.recommendations:
        if rec.review_status == "rejected":
            continue
        pending_note = " (extracted — awaiting human review)" if rec.review_status == "pending_review" else ""
        support = [_rec_evidence(rec)]
        missing: list[str] = []
        status: str | None = None
        doc_ids = [str(rec.document_id)] if rec.document_id else []
        rule = {"referral": "CG-002", "lab_test": "CG-003"}.get(rec.kind, "CG-001")
        targets = set(rec.targets)

        if rec.kind == "lab_test":
            wanted = targets & LAB_TERMS
            later = [d for d in docs.values() if d.category in ("lab_result", "fhir_record")
                     and _later(d.document_date, rec.documented_at) and d.id != rec.document_id]
            found = set().union(*[set(d.terms) for d in later]) if later else set()
            for d in later:
                if not wanted or set(d.terms) & wanted:
                    support.append(_ev("document", d.id, d.title, f"Result dated {_d(d.document_date)}"))
                    doc_ids.append(str(d.id))
            if later and (not wanted or wanted <= found):
                status = COMPLETED
            else:
                status = UNKNOWN
                gap_terms = sorted(wanted - found) if wanted else []
                missing.append("Laboratory result for: " + ", ".join(gap_terms) if gap_terms
                               else "A laboratory result dated after the recommendation")
        elif rec.kind == "referral":
            matches = []
            for e in snap.events:
                if e.event_type in ("specialist_consultation", "international_consultation") and \
                        _later(e.occurred_on, rec.documented_at) and (not targets or targets & set(e.terms)):
                    if rec.document_id in e.document_ids:
                        continue  # the event that produced the referral is not its outcome
                    matches.append(e)
            documented = [e for e in matches if e.document_ids]
            if documented:
                status = COMPLETED
                for e in documented:
                    support.append(_ev("event", e.id, e.title, f"Consultation on {_d(e.occurred_on)} with linked documentation"))
                    doc_ids += [str(x) for x in e.document_ids]
            else:
                status = UNKNOWN
                for e in matches:
                    support.append(_ev("event", e.id, e.title, f"Recorded on {_d(e.occurred_on)} without a document"))
                missing.append("A consultation letter or summary documenting the referral outcome")
        else:
            wanted_imaging = targets - LAB_TERMS - {"cardiology", "endocrinology"}
            if rec.kind == "imaging":
                later = [d for d in docs.values() if d.category == "imaging_report"
                         and _later(d.document_date, rec.documented_at)
                         and (not wanted_imaging or set(d.terms) & wanted_imaging)]
                if later:
                    status = COMPLETED
                    for d in later:
                        support.append(_ev("document", d.id, d.title, f"Report dated {_d(d.document_date)}"))
                        doc_ids.append(str(d.id))
                else:
                    status = UNKNOWN
                    missing.append("An imaging report dated after the recommendation"
                                   + (f" ({', '.join(sorted(wanted_imaging))})" if wanted_imaging else ""))
            else:  # follow_up_visit / other
                # Family-physician follow-ups match HMO visits; otherwise the visit must be with the
                # organization that issued the recommendation.
                src_org = docs[rec.document_id].organization_id if rec.document_id in docs else None
                to_gp = bool(_GP.search(rec.text))
                visits = [e for e in snap.events if e.event_type in CONSULT_EVENTS
                          and e.occurred_on > (rec.documented_at or date.min)
                          and ((e.event_type == "hmo_consultation") if to_gp
                               else (src_org is None or e.organization_id == src_org))
                          and rec.document_id not in e.document_ids]
                documented = [e for e in visits if e.document_ids]
                if documented:
                    status = COMPLETED
                    for e in documented:
                        support.append(_ev("event", e.id, e.title, f"Visit on {_d(e.occurred_on)} with linked documentation"))
                        doc_ids += [str(x) for x in e.document_ids]
                else:
                    status = UNKNOWN
                    for e in visits:
                        support.append(_ev("event", e.id, e.title, f"Visit on {_d(e.occurred_on)} without a document"))
                    missing.append("Documentation of a follow-up visit after the recommendation")

        # Tasks can only move status when evidence is not already conclusive.
        t_status, t_support, t_missing = _task_state(snap, rec, docs)
        if status != COMPLETED and t_status:
            status = t_status
            support += t_support
            missing += t_missing
        elif t_support:
            support += t_support

        title_kind = {"referral": "Referral outcome", "lab_test": "Laboratory follow-up",
                      "imaging": "Imaging follow-up", "follow_up_visit": "Follow-up visit"}.get(rec.kind, "Recommendation")
        descriptions = {
            COMPLETED: "Supporting documentation for completion is available.",
            OPEN: "A follow-up task is documented as pending.",
            UNKNOWN: "The available records do not establish whether this was done. This does not mean it was not done.",
            NOT_APPLICABLE: "Marked as not requiring further tracking by an authorized user.",
        }
        suggestion = None if status in (COMPLETED, NOT_APPLICABLE) else (
            f"Ask the clinic or provider whether \"{rec.text[:120]}\" has been completed, and request the "
            f"resulting document so it can be added to your records.")
        out.append(Finding(
            rule_id=rule, fingerprint=_fp(rule, rec.id),
            title=f"{title_kind}: {rec.text[:140]}",
            description=descriptions[status] + pending_note,
            status=status, supporting_evidence=support, missing_evidence=missing,
            document_ids=sorted(set(doc_ids)),
            relevant_dates={"recommendation_documented": _d(rec.documented_at), "evaluated": as_of.isoformat(),
                            **({"documented_timeframe": rec.timeframe_text} if rec.timeframe_text else {})},
            suggested_clarification=suggestion, recommendation_id=rec.id,
            params={"kind": rec.kind, "text": rec.text[:200], "pending_review": rec.review_status == "pending_review"},
        ))
    return out


def rule_missing_summary(snap: Snapshot, as_of: date) -> list[Finding]:
    out = []
    for c in snap.consultations:
        if c.status == "completed" and not c.has_approved_summary:
            out.append(Finding(
                "CG-004", _fp("CG-004", c.id), f"Consultation summary not yet approved: {c.title}",
                "The consultation is marked completed but no professional-approved summary exists yet.",
                OPEN, [_ev("consultation", c.id, c.title, f"Held on {_d(c.scheduled_on)}")],
                ["A summary approved by the participating professionals"], [],
                {"consultation": _d(c.scheduled_on), "evaluated": as_of.isoformat()},
                "Ask the participating professionals to complete and approve the consultation summary.",
                params={"title": c.title}))
    return out


def rule_unacknowledged_handoff(snap: Snapshot, as_of: date) -> list[Finding]:
    out = []
    for h in snap.handoffs:
        if h.status == "shared" and not h.acknowledged:
            out.append(Finding(
                "CG-005", _fp("CG-005", h.id), f"Handoff to {h.to_name} not yet acknowledged",
                "A consultation summary was shared with another professional, who has not acknowledged receiving it.",
                OPEN, [_ev("handoff", h.id, f"Shared with {h.to_name}", f"Shared on {_d(h.shared_on)}")],
                ["Acknowledgment from the receiving professional"], [],
                {"shared": _d(h.shared_on), "evaluated": as_of.isoformat()},
                f"Confirm with {h.to_name} that the summary was received and reviewed.",
                params={"to": h.to_name}))
    return out


def rule_date_conflicts(snap: Snapshot, docs, as_of: date) -> list[Finding]:
    out = []
    for e in snap.events:
        for did in e.document_ids:
            d = docs.get(did)
            if not d or not d.document_date:
                continue
            if abs((d.document_date - e.occurred_on).days) > 2:
                out.append(Finding(
                    "CG-006", _fp("CG-006", e.id, d.id), f"Date mismatch: {e.title}",
                    "The journey event date and the date written in its document differ by more than two days.",
                    CLARIFY,
                    [_ev("event", e.id, e.title, f"Event date {_d(e.occurred_on)}"),
                     _ev("document", d.id, d.title, f"Document date {_d(d.document_date)}")],
                    ["Confirmation of the correct date"], [str(d.id)],
                    {"event": _d(e.occurred_on), "document": _d(d.document_date), "evaluated": as_of.isoformat()},
                    "Check which date is correct and correct the event or the document details.",
                    params={"title": e.title}))
    for d in docs.values():
        if d.document_date and d.document_date > as_of:
            out.append(Finding(
                "CG-006", _fp("CG-006-future", d.id), f"Document dated in the future: {d.title}",
                "The date detected in this document is later than today.", CLARIFY,
                [_ev("document", d.id, d.title, f"Document date {_d(d.document_date)}")],
                ["Confirmation of the correct document date"], [str(d.id)],
                {"document": _d(d.document_date), "evaluated": as_of.isoformat()},
                "Verify the document date with its source.", params={"title": d.title}))
    return out


def rule_contradictory_recommendations(snap: Snapshot, as_of: date) -> list[Finding]:
    out = []
    recs = [r for r in snap.recommendations if r.review_status != "rejected" and r.targets and r.timeframe_text]
    for i, a in enumerate(recs):
        for b in recs[i + 1:]:
            if a.kind == b.kind and a.document_id != b.document_id and set(a.targets) & set(b.targets) \
                    and a.timeframe_text.lower() != b.timeframe_text.lower():
                first, second = sorted([a, b], key=lambda r: str(r.id))
                out.append(Finding(
                    "CG-007", _fp("CG-007", first.id, second.id),
                    f"Different timeframes documented for: {', '.join(sorted(set(a.targets) & set(b.targets)))}",
                    "Two documents describe the same follow-up with different timeframes. HealthBridge does not decide which is correct.",
                    CLARIFY, [_rec_evidence(first), _rec_evidence(second)],
                    ["Clarification from the treating professional about which instruction applies"],
                    sorted({str(x.document_id) for x in (first, second) if x.document_id}),
                    {"first": _d(first.documented_at), "second": _d(second.documented_at), "evaluated": as_of.isoformat()},
                    "Ask your treating professional which of the documented timeframes applies.",
                    params={"targets": sorted(set(a.targets) & set(b.targets))}))
    return out


def rule_expected_documents(snap: Snapshot, docs, as_of: date) -> list[Finding]:
    out = []
    for e in snap.events:
        exp = EXPECTED_DOC.get(e.event_type)
        if not exp or e.occurred_on > as_of:
            continue
        cats, label = exp
        if any(docs[d].category in cats for d in e.document_ids if d in docs):
            continue
        out.append(Finding(
            "CG-008", _fp("CG-008", e.id), f"Expected {label} not received: {e.title}",
            f"This {e.event_type.replace('_', ' ')} has no linked {label} in HealthBridge. It may exist at the provider.",
            UNKNOWN, [_ev("event", e.id, e.title, f"On {_d(e.occurred_on)}")],
            [f"{'An' if label[0] in 'aeiou' else 'A'} {label} for this event"], [str(x) for x in e.document_ids],
            {"event": _d(e.occurred_on), "evaluated": as_of.isoformat()},
            f"Request the {label} from the provider and upload it.",
            params={"title": e.title, "label": label}))
    return out


def rule_information_not_shared(snap: Snapshot, docs, as_of: date, open_rec_doc_ids: set) -> list[Finding]:
    out = []
    for c in snap.consultations:
        if c.status not in ("scheduled", "in_progress"):
            continue
        key_docs = (set(c.attached_document_ids) | open_rec_doc_ids) & set(docs)
        for pid, pname in c.professionals:
            missing_docs = sorted((key_docs - set(snap.access.get(pid, set()))), key=str)
            if not missing_docs:
                continue
            out.append(Finding(
                "CG-009", _fp("CG-009", c.id, pid), f"{pname} cannot see {len(missing_docs)} relevant document(s)",
                f"For the consultation '{c.title}', these documents are in HealthBridge but have not been shared with "
                f"{pname}. They may or may not have this information from another source.",
                UNKNOWN,
                [_ev("consultation", c.id, c.title, f"Scheduled {_d(c.scheduled_on)}")]
                + [_ev("document", d, docs[d].title) for d in missing_docs],
                [f"Patient decision on sharing with {pname}"], [str(d) for d in missing_docs],
                {"consultation": _d(c.scheduled_on), "evaluated": as_of.isoformat()},
                f"Decide whether to share these documents with {pname} before the consultation (Sharing Center).",
                params={"professional": pname, "count": len(missing_docs), "title": c.title}))
    return out


def evaluate_snapshot(snap: Snapshot, as_of: date) -> list[Finding]:
    docs = {d.id: d for d in snap.documents}
    findings = rule_recommendation_completion(snap, docs, as_of)
    open_rec_doc_ids = {f_rec.document_id for f_rec in snap.recommendations
                        if f_rec.document_id and f_rec.review_status != "rejected"
                        and any(f.recommendation_id == f_rec.id and f.status in (UNKNOWN, OPEN) for f in findings)}
    findings += rule_missing_summary(snap, as_of)
    findings += rule_unacknowledged_handoff(snap, as_of)
    findings += rule_date_conflicts(snap, docs, as_of)
    findings += rule_contradictory_recommendations(snap, as_of)
    findings += rule_expected_documents(snap, docs, as_of)
    findings += rule_information_not_shared(snap, docs, as_of, open_rec_doc_ids)
    return sorted(findings, key=lambda f: (f.rule_id, f.fingerprint))


# ------------------------------------------------------------------ persistence
def build_snapshot(db, patient_id: uuid.UUID) -> Snapshot:
    from sqlalchemy import select

    from app.models import (
        Consultation, ConsultationSummary, Document, FollowUpTask, Handoff, JourneyEvent, Recommendation, User,
    )
    from app.services.extraction import find_terms

    docs_rows = list(db.execute(select(Document).where(
        Document.patient_id == patient_id, Document.deleted_at.is_(None), Document.is_latest.is_(True))).scalars())
    doc_snaps = tuple(DocSnap(d.id, d.title, d.category, d.document_date,
                              tuple(find_terms((d.title or "") + "\n" + (d.extracted_text or ""))), d.organization_id)
                      for d in docs_rows)
    titles = {d.id: d.title for d in docs_rows}
    live_doc_ids = set(titles)
    recs = tuple(RecSnap(r.id, r.kind, r.text, tuple(sorted(set((r.target or "").split(",")) - {""})),
                         r.documented_at, r.document_id, titles.get(r.document_id), r.review_status,
                         r.timeframe_text, r.passage)
                 for r in db.execute(select(Recommendation).where(Recommendation.patient_id == patient_id)).scalars()
                 if r.document_id is None or r.document_id in live_doc_ids)
    events = []
    for e in db.execute(select(JourneyEvent).where(JourneyEvent.patient_id == patient_id)).scalars():
        doc_ids = tuple(d.id for d in e.documents if d.id in live_doc_ids)
        text = " ".join([e.title, e.description or ""] + [titles[d] for d in doc_ids])
        doc_terms = set()
        for d in doc_snaps:
            if d.id in doc_ids:
                doc_terms |= set(d.terms)
        events.append(EventSnap(e.id, e.event_type, e.title, e.occurred_at.date(), e.organization_id, doc_ids,
                                e.verification_status, tuple(sorted(set(find_terms(text)) | doc_terms))))
    tasks = tuple(TaskSnap(t.id, t.recommendation_id, t.kind, t.status, t.evidence_document_id,
                           t.completed_at.date() if t.completed_at else None)
                  for t in db.execute(select(FollowUpTask).where(FollowUpTask.patient_id == patient_id)).scalars())
    consults = []
    pro_ids: set[uuid.UUID] = set()
    for c in db.execute(select(Consultation).where(Consultation.patient_id == patient_id)).scalars():
        approved = db.execute(select(ConsultationSummary.id).where(
            ConsultationSummary.consultation_id == c.id, ConsultationSummary.status == "approved")).first() is not None
        pros = tuple((p.user_id, p.user.full_name) for p in c.participants
                     if p.meeting_role == "professional" and p.invite_status != "declined")
        pro_ids |= {p[0] for p in pros}
        consults.append(ConsultSnap(c.id, c.title, c.status, c.scheduled_start.date(), approved, pros,
                                    tuple(d.id for d in c.documents)))
    handoffs = []
    for h in db.execute(select(Handoff).where(Handoff.patient_id == patient_id)).scalars():
        to = db.get(User, h.to_user_id)
        handoffs.append(HandoffSnap(h.id, h.status, h.shared_at.date() if h.shared_at else None,
                                    h.acknowledged_at is not None, to.full_name if to else "professional"))
    access: dict = {}
    if pro_ids:
        from app.authz import AccessPolicy

        for pid in pro_ids:
            pro = db.get(User, pid)
            access[pid] = AccessPolicy(db, pro).accessible_document_ids(patient_id) if pro else set()
    return Snapshot(recs, doc_snaps, tuple(events), tasks, tuple(consults), tuple(handoffs), access)


def persist_findings(db, patient_id: uuid.UUID, findings: list[Finding]) -> dict:
    """Upsert findings by fingerprint; deactivate gaps whose rule no longer triggers."""
    from sqlalchemy import select

    from app.models import CareGap, utcnow
    from app.services.notifications import notify

    now = utcnow()
    existing = {g.fingerprint: g for g in db.execute(select(CareGap).where(CareGap.patient_id == patient_id)).scalars()}
    seen = set()
    created = 0
    for f in findings:
        seen.add(f.fingerprint)
        g = existing.get(f.fingerprint)
        if g is None:
            g = CareGap(patient_id=patient_id, rule_id=f.rule_id, fingerprint=f.fingerprint, first_detected_at=now)
            db.add(g)
            created += 1
        prev_status = g.status if g.computed_status else None
        g.title, g.description, g.computed_status = f.title, f.description, f.status
        g.supporting_evidence, g.missing_evidence = f.supporting_evidence, f.missing_evidence
        g.document_ids, g.relevant_dates = f.document_ids, f.relevant_dates
        g.suggested_clarification, g.recommendation_id, g.params = f.suggested_clarification, f.recommendation_id, f.params
        g.active, g.last_evaluated_at = True, now
        # Verified evidence supersedes a human "requires clarification" flag; dismissals persist.
        if f.status == COMPLETED and g.review_status == CLARIFY:
            g.review_status = None
        if g.status in (UNKNOWN, CLARIFY) and prev_status != g.status:
            db.flush()
            notify(db, patient_id, "care_gap_clarification", f"Care continuity check: {g.title[:150]}",
                   g.suggested_clarification, f"/app/care-gaps?gap={g.id}", dedupe_key=f"gap:{g.fingerprint}:{g.status}")
    for fp, g in existing.items():
        if fp not in seen and g.active:
            g.active = False
            g.last_evaluated_at = now
    db.flush()
    return {"findings": len(findings), "new": created}


def evaluate_patient(db, patient_id: uuid.UUID, as_of: date | None = None) -> dict:
    from app.models import utcnow

    as_of = as_of or utcnow().date()
    findings = evaluate_snapshot(build_snapshot(db, patient_id), as_of)
    return persist_findings(db, patient_id, findings)


def finding_to_dict(f: Finding) -> dict:
    return {"rule_id": f.rule_id, "rule": RULES[f.rule_id], "fingerprint": f.fingerprint, "title": f.title,
            "description": f.description, "status": f.status, "supporting_evidence": f.supporting_evidence,
            "missing_evidence": f.missing_evidence, "document_ids": f.document_ids,
            "relevant_dates": f.relevant_dates, "suggested_clarification": f.suggested_clarification,
            "recommendation_id": str(f.recommendation_id) if f.recommendation_id else None, "params": f.params}

