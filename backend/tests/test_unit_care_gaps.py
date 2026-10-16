"""Deterministic care-gap rules over hand-built snapshots (no database)."""
import uuid
from datetime import date

from app.services.care_gaps import (
    CLARIFY, COMPLETED, NOT_APPLICABLE, OPEN, UNKNOWN, ConsultSnap, DocSnap, EventSnap, HandoffSnap, RecSnap,
    Snapshot, TaskSnap, evaluate_snapshot,
)

AS_OF = date(2026, 10, 15)
CEDAR = uuid.uuid4()
TAMAR = uuid.uuid4()


def rec(kind, text, targets=(), when=date(2026, 7, 8), doc=None, tf=None, status="confirmed"):
    return RecSnap(uuid.uuid4(), kind, text, tuple(targets), when, doc, "Letter", status, tf, text)


def doc(category, when, terms=(), org=None):
    return DocSnap(uuid.uuid4(), f"{category} doc", category, when, tuple(terms), org)


def by_rec(findings, r):
    return next(f for f in findings if f.recommendation_id == r.id)


def test_imaging_without_report_is_unknown_not_missed():
    letter = doc("consultation_note", date(2026, 7, 8), org=CEDAR)
    r = rec("imaging", "Echocardiogram within 6 weeks", ["echocardiogram"], doc=letter.id, tf="within 6 weeks")
    f = by_rec(evaluate_snapshot(Snapshot(recommendations=(r,), documents=(letter,)), AS_OF), r)
    assert f.status == UNKNOWN and f.rule_id == "CG-001"
    assert "does not mean it was not done" in f.description
    assert f.missing_evidence and f.suggested_clarification
    assert f.relevant_dates["documented_timeframe"] == "within 6 weeks"


def test_imaging_report_after_recommendation_verifies():
    letter = doc("consultation_note", date(2026, 7, 8))
    report = doc("imaging_report", date(2026, 8, 1), ["echocardiogram"])
    r = rec("imaging", "Echocardiogram", ["echocardiogram"], doc=letter.id)
    f = by_rec(evaluate_snapshot(Snapshot(recommendations=(r,), documents=(letter, report)), AS_OF), r)
    assert f.status == COMPLETED
    assert any(e["id"] == str(report.id) for e in f.supporting_evidence)


def test_report_before_recommendation_does_not_count():
    report = doc("imaging_report", date(2026, 6, 1), ["echocardiogram"])
    r = rec("imaging", "Echocardiogram", ["echocardiogram"])
    assert by_rec(evaluate_snapshot(Snapshot(recommendations=(r,), documents=(report,)), AS_OF), r).status == UNKNOWN


def test_wrong_test_type_does_not_count():
    report = doc("imaging_report", date(2026, 8, 1), ["chest_xray"])
    r = rec("imaging", "Stress test", ["stress_test"])
    assert by_rec(evaluate_snapshot(Snapshot(recommendations=(r,), documents=(report,)), AS_OF), r).status == UNKNOWN


def test_partial_lab_results_identify_missing_test():
    lab = doc("lab_result", date(2026, 5, 19), ["lipid_panel"])
    r = rec("lab_test", "CBC and lipid panel", ["cbc", "lipid_panel"], when=date(2026, 5, 12))
    f = by_rec(evaluate_snapshot(Snapshot(recommendations=(r,), documents=(lab,)), AS_OF), r)
    assert f.status == UNKNOWN and f.rule_id == "CG-003"
    assert f.missing_evidence == ["Laboratory result for: cbc"]
    assert any(e["id"] == str(lab.id) for e in f.supporting_evidence)


def test_task_states_map_to_statuses():
    r = rec("imaging", "Echo", ["echocardiogram"])
    evidence = doc("other", date(2026, 9, 1))
    cases = [("open", None, OPEN), ("completed_reported", None, UNKNOWN), ("not_applicable", None, NOT_APPLICABLE),
             ("completed_verified", evidence.id, COMPLETED)]
    for status, ev_id, expected in cases:
        t = TaskSnap(uuid.uuid4(), r.id, "follow_up", status, ev_id, None)
        f = by_rec(evaluate_snapshot(Snapshot(recommendations=(r,), documents=(evidence,), tasks=(t,)), AS_OF), r)
        assert f.status == expected, status


def test_ai_or_manual_claim_without_evidence_never_completes():
    r = rec("imaging", "Echo", ["echocardiogram"])
    t = TaskSnap(uuid.uuid4(), r.id, "follow_up", "completed_reported", None, date(2026, 9, 1))
    f = by_rec(evaluate_snapshot(Snapshot(recommendations=(r,), tasks=(t,)), AS_OF), r)
    assert f.status == UNKNOWN
    assert any("A document confirming completion" in m for m in f.missing_evidence)


def test_rejected_recommendations_ignored_and_pending_review_flagged():
    r1 = rec("imaging", "Echo", status="rejected")
    r2 = rec("imaging", "MRI", status="pending_review")
    findings = evaluate_snapshot(Snapshot(recommendations=(r1, r2)), AS_OF)
    assert all(f.recommendation_id != r1.id for f in findings)
    assert "awaiting human review" in by_rec(findings, r2).description


def test_referral_outcome_requires_documented_matching_consultation():
    src = doc("consultation_note", date(2026, 5, 12))
    r = rec("referral", "Referral to cardiology", ["cardiology"], when=date(2026, 5, 12), doc=src.id)
    undocumented = EventSnap(uuid.uuid4(), "specialist_consultation", "Cardiology", date(2026, 6, 1), None, (), "patient_reported", ("cardiology",))
    f = by_rec(evaluate_snapshot(Snapshot(recommendations=(r,), documents=(src,), events=(undocumented,)), AS_OF), r)
    assert f.status == UNKNOWN and f.rule_id == "CG-002"
    letter = doc("consultation_note", date(2026, 7, 8), ["cardiology"])
    documented = EventSnap(uuid.uuid4(), "specialist_consultation", "Cardiology", date(2026, 7, 8), None, (letter.id,), "documented", ("cardiology",))
    f = by_rec(evaluate_snapshot(Snapshot(recommendations=(r,), documents=(src, letter), events=(documented,)), AS_OF), r)
    assert f.status == COMPLETED


def test_gp_follow_up_matches_hmo_visit_only():
    src = doc("discharge_summary", date(2026, 6, 3))
    r = rec("follow_up_visit", "Follow-up with your family physician within 1 week", when=date(2026, 6, 3), doc=src.id)
    hosp = EventSnap(uuid.uuid4(), "specialist_consultation", "Other", date(2026, 6, 10), None, (uuid.uuid4(),), "documented", ())
    assert by_rec(evaluate_snapshot(Snapshot(recommendations=(r,), documents=(src,), events=(hosp,)), AS_OF), r).status == UNKNOWN
    gp_doc = doc("consultation_note", date(2026, 6, 9))
    gp = EventSnap(uuid.uuid4(), "hmo_consultation", "GP", date(2026, 6, 9), TAMAR, (gp_doc.id,), "documented", ())
    assert by_rec(evaluate_snapshot(Snapshot(recommendations=(r,), documents=(src, gp_doc), events=(gp,)), AS_OF), r).status == COMPLETED


def test_contradictory_timeframes_require_clarification():
    a = rec("lab_test", "Repeat lipid panel in 6 months", ["lipid_panel"], doc=uuid.uuid4(), tf="in 6 months")
    b = rec("lab_test", "Repeat lipid panel in 3 months", ["lipid_panel"], doc=uuid.uuid4(), tf="in 3 months")
    same = rec("lab_test", "Repeat lipid panel in 3 months", ["lipid_panel"], doc=uuid.uuid4(), tf="In 3 months")
    findings = [f for f in evaluate_snapshot(Snapshot(recommendations=(a, b, same)), AS_OF) if f.rule_id == "CG-007"]
    assert len(findings) == 2 and all(f.status == CLARIFY for f in findings)  # a-b and a-same; b-same agree


def test_date_conflict_and_future_document():
    d = doc("referral", date(2026, 6, 25))
    future = doc("lab_result", date(2027, 1, 1))
    ev = EventSnap(uuid.uuid4(), "referral", "Referral", date(2026, 7, 2), None, (d.id,), "patient_reported", ())
    findings = [f for f in evaluate_snapshot(Snapshot(documents=(d, future), events=(ev,)), AS_OF) if f.rule_id == "CG-006"]
    assert len(findings) == 2 and all(f.status == CLARIFY for f in findings)


def test_expected_document_missing():
    xray = EventSnap(uuid.uuid4(), "imaging", "Chest X-ray", date(2026, 6, 2), None, (), "patient_reported", ())
    future = EventSnap(uuid.uuid4(), "imaging", "Planned", date(2026, 12, 1), None, (), "patient_reported", ())
    findings = [f for f in evaluate_snapshot(Snapshot(events=(xray, future)), AS_OF) if f.rule_id == "CG-008"]
    assert len(findings) == 1 and findings[0].status == UNKNOWN


def test_consultation_summary_handoff_and_sharing_rules():
    pro = uuid.uuid4()
    letter = doc("consultation_note", date(2026, 7, 8))
    r = rec("imaging", "Echo", ["echocardiogram"], doc=letter.id)
    done = ConsultSnap(uuid.uuid4(), "Done", "completed", date(2026, 10, 1), False, ((pro, "Dr. X"),), ())
    upcoming = ConsultSnap(uuid.uuid4(), "Upcoming", "scheduled", date(2026, 10, 20), False, ((pro, "Dr. X"),), ())
    h = HandoffSnap(uuid.uuid4(), "shared", date(2026, 10, 2), False, "Dr. Y")
    snap = Snapshot(recommendations=(r,), documents=(letter,), consultations=(done, upcoming), handoffs=(h,), access={pro: set()})
    rules = {f.rule_id: f for f in evaluate_snapshot(snap, AS_OF)}
    assert rules["CG-004"].status == OPEN
    assert rules["CG-005"].status == OPEN
    assert rules["CG-009"].status == UNKNOWN and rules["CG-009"].document_ids == [str(letter.id)]
    shared = Snapshot(recommendations=(r,), documents=(letter,), consultations=(upcoming,), access={pro: {letter.id}})
    assert not [f for f in evaluate_snapshot(shared, AS_OF) if f.rule_id == "CG-009"]


def test_replay_is_deterministic():
    letter = doc("consultation_note", date(2026, 7, 8))
    snap = Snapshot(recommendations=(rec("imaging", "Echo", ["echocardiogram"], doc=letter.id),), documents=(letter,))
    a = [(f.fingerprint, f.status, f.title) for f in evaluate_snapshot(snap, AS_OF)]
    b = [(f.fingerprint, f.status, f.title) for f in evaluate_snapshot(snap, AS_OF)]
    assert a == b


def test_suggestions_are_administrative_never_clinical():
    letter = doc("consultation_note", date(2026, 7, 8))
    r = rec("imaging", "Echocardiogram within 6 weeks", ["echocardiogram"], doc=letter.id)
    for f in evaluate_snapshot(Snapshot(recommendations=(r,), documents=(letter,)), AS_OF):
        text = (f.suggested_clarification or "").lower() + f.description.lower()
        for word in ("urgent", "diagnos", "prescri", "dose", "immediately"):
            assert word not in text
