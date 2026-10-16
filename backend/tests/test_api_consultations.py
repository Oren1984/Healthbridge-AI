"""Consultations, meeting tokens, notes, multi-professional summaries, handoffs."""
from datetime import datetime, timedelta, timezone

import jwt

from app.config import get_settings
from app.seed_data import GOLDEN_FILE, sample_bytes
from tests.conftest import Api, run_worker, user_id


def _create(noa, doc_ids=(), start=None, pros=("morgan", "bennett")):
    start = start or (datetime.now(timezone.utc) + timedelta(minutes=10))
    return noa.post("/api/consultations", json={
        "title": "International cardiology second opinion", "scheduled_start": start.isoformat(),
        "duration_minutes": 45, "professional_ids": [str(user_id(p)) for p in pros], "document_ids": list(doc_ids)})


def test_scheduling_validation(seeded):
    noa = Api("noa")
    bad = noa.post("/api/consultations", json={"title": "x" * 5, "scheduled_start": "2026-11-01T10:00:00",
                                               "professional_ids": [str(user_id("morgan"))]})
    assert bad.status_code == 422  # timezone required
    unverified = _create(noa, pros=("shah",))
    assert unverified.status_code == 422
    assert Api("morgan").post("/api/consultations", json={}).status_code == 403  # patients schedule


def test_meeting_membership_does_not_grant_record_access(seeded):
    noa = Api("noa")
    letter = noa.get(f"/api/patients/{noa.id}/documents").json()[0]
    c = _create(noa, [letter["id"]]).json()
    morgan = Api("morgan")
    detail = morgan.get(f"/api/consultations/{c['id']}").json()
    assert detail["documents"][0]["accessible"] is False
    assert morgan.get(f"/api/documents/{letter['id']}").status_code == 404
    r = noa.post(f"/api/consultations/{c['id']}/share", json={"document_ids": [letter["id"]], "days": 7})
    assert r.json()["grants_created"] == 2
    assert morgan.get(f"/api/consultations/{c['id']}").json()["documents"][0]["accessible"] is True
    assert morgan.get(f"/api/documents/{letter['id']}").status_code == 200


def test_join_tokens_are_scoped_and_short_lived(seeded):
    noa = Api("noa")
    c = _create(noa).json()
    tokens = {}
    for who in ("noa", "morgan", "bennett"):
        r = Api(who).post(f"/api/consultations/{c['id']}/join")
        assert r.status_code == 200, r.text
        tokens[who] = r.json()
    s = get_settings()
    claims = jwt.decode(tokens["morgan"]["token"], s.livekit_api_secret, algorithms=["HS256"])
    assert claims["sub"] == str(user_id("morgan"))
    assert claims["video"]["room"].startswith("hb-")
    assert claims["video"]["roomJoin"] is True and not claims["video"].get("roomRecord")
    assert not claims["video"].get("roomAdmin")
    assert claims["exp"] - claims["nbf"] <= s.livekit_token_ttl_seconds
    assert len({t["room"] for t in tokens.values()}) == 1
    # outsiders
    assert Api("ronen").post(f"/api/consultations/{c['id']}/join").status_code == 404
    assert Api("daniel").post(f"/api/consultations/{c['id']}/join").status_code == 404
    assert Api("admin").post(f"/api/consultations/{c['id']}/join").status_code == 403


def test_join_window_and_cancelled(seeded):
    noa = Api("noa")
    far = _create(noa, start=datetime.now(timezone.utc) + timedelta(days=3)).json()
    assert noa.post(f"/api/consultations/{far['id']}/join").status_code == 409
    soon = _create(noa).json()
    noa.post(f"/api/consultations/{soon['id']}/cancel")
    assert Api("morgan").post(f"/api/consultations/{soon['id']}/join").status_code == 409


def test_declined_professional_loses_access(seeded):
    noa = Api("noa")
    c = _create(noa).json()
    bennett = Api("bennett")
    assert bennett.post(f"/api/consultations/{c['id']}/respond", json={"decision": "decline"}).status_code == 200
    assert bennett.get(f"/api/consultations/{c['id']}").status_code == 404
    assert bennett.post(f"/api/consultations/{c['id']}/join").status_code == 404


def test_summary_requires_every_professional_and_links_journey(seeded):
    """API-level golden scenario: letter -> sharing -> consultation -> approved summary -> evidence-based status."""
    noa, morgan, bennett = Api("noa"), Api("morgan"), Api("bennett")
    up = noa.post(f"/api/patients/{noa.id}/documents", files={"file": (GOLDEN_FILE, sample_bytes(GOLDEN_FILE))})
    run_worker()
    letter = noa.get(f"/api/documents/{up.json()['id']}").json()
    gaps = noa.get(f"/api/patients/{noa.id}/care-gaps").json()
    assert next(g for g in gaps if "second opinion" in g["title"].lower())["status"] == "unknown"
    c = _create(noa, [letter["id"]]).json()
    noa.post(f"/api/consultations/{c['id']}/share", json={"document_ids": [letter["id"]], "days": 7})
    assert noa.post(f"/api/consultations/{c['id']}/notes", json={"content": "patient note"}).status_code == 403
    morgan.post(f"/api/consultations/{c['id']}/notes", json={"content": "Agree echocardiogram is the next step."})
    bennett.post(f"/api/consultations/{c['id']}/notes", json={"content": "Stress test after echo if echo is normal."})
    body = {"discussion": "Reviewed the referral letter and symptoms together.", "observation": "Echo first.",
            "proposed_followups": [{"title": "Share echocardiogram report with consultation team"}],
            "referenced_document_ids": [letter["id"]]}
    assert morgan.post(f"/api/consultations/{c['id']}/summaries", json=body).status_code == 409  # not completed yet
    assert morgan.post(f"/api/consultations/{c['id']}/complete").json()["status"] == "completed"

    draft = morgan.post(f"/api/consultations/{c['id']}/summaries/draft").json()
    assert draft["ai_generated_draft"] and "Agree echocardiogram" in draft["discussion"]
    unauthorized_ref = {**body, "referenced_document_ids": [d["id"] for d in noa.get(f"/api/patients/{noa.id}/documents").json()]}
    assert morgan.post(f"/api/consultations/{c['id']}/summaries", json=unauthorized_ref).status_code == 422

    s1 = morgan.post(f"/api/consultations/{c['id']}/summaries", json=body).json()
    assert s1["status"] == "pending_approval" and len(s1["awaiting_approval_from"]) == 2
    s2 = bennett.post(f"/api/summaries/{s1['id']}/observations", json={"text": "Consider stress test afterwards."}).json()
    assert s2["version"] == 2 and {o["author_name"] for o in s2["observations"]} == {"Dr. Rachel Morgan", "Dr. Oliver Bennett"}
    assert morgan.post(f"/api/summaries/{s1['id']}/approve", json={}).status_code == 409  # superseded

    a1 = morgan.post(f"/api/summaries/{s2['id']}/approve", json={"comment": "OK"}).json()
    assert a1["status"] == "pending_approval"  # consensus is never assumed
    assert a1["awaiting_approval_from"] == [str(user_id("bennett"))]
    assert noa.post(f"/api/summaries/{s2['id']}/approve", json={}).status_code == 403
    a2 = bennett.post(f"/api/summaries/{s2['id']}/approve", json={}).json()
    assert a2["status"] == "approved" and a2["document_id"]

    journey = noa.get(f"/api/patients/{noa.id}/journey?type=international_consultation").json()
    ev = next(e for e in journey if e["consultation_id"] == c["id"])
    assert ev["verification_status"] == "professional_confirmed" and ev["documents"][0]["id"] == a2["document_id"]
    gaps = noa.get(f"/api/patients/{noa.id}/care-gaps").json()
    assert any(g["recommendation_id"] for g in gaps if "Share echocardiogram report" in g["title"])
    second = next(g for g in gaps if "second opinion" in g["title"].lower())
    assert second["status"] == "completed_verified"
    assert noa.post(f"/api/summaries/{s2['id']}/acknowledge").json()["patient_acknowledged_at"]
    # Participants can read the approved summary document even without a separate grant
    assert bennett.get(f"/api/documents/{a2['document_id']}").status_code == 200
    assert Api("ronen").get(f"/api/documents/{a2['document_id']}").status_code == 404

    # Handoff proposed by a professional is inert until the patient approves
    h = morgan.post(f"/api/summaries/{s2['id']}/handoffs", json={"to_user_id": str(user_id("ronen")), "note": "FYI"}).json()
    assert h["status"] == "pending_patient_approval"
    ronen = Api("ronen")
    assert ronen.get(f"/api/documents/{a2['document_id']}").status_code == 404
    assert noa.post(f"/api/handoffs/{h['id']}/decide", json={"decision": "approve", "days": 10}).json()["status"] == "shared"
    assert ronen.get(f"/api/documents/{a2['document_id']}").status_code == 200
    assert any(g["rule_id"] == "CG-005" for g in noa.get(f"/api/patients/{noa.id}/care-gaps").json())
    assert ronen.post(f"/api/handoffs/{h['id']}/acknowledge").json()["acknowledged_at"]
    assert not any(g["rule_id"] == "CG-005" for g in noa.get(f"/api/patients/{noa.id}/care-gaps").json())


def test_completed_consultation_without_summary_creates_gap(seeded):
    noa = Api("noa")
    c = _create(noa).json()
    Api("morgan").post(f"/api/consultations/{c['id']}/complete")
    gaps = noa.get(f"/api/patients/{noa.id}/care-gaps").json()
    assert any(g["rule_id"] == "CG-004" and g["status"] == "open" for g in gaps)


def test_presence_diagnostics_recorded(seeded):
    noa = Api("noa")
    c = _create(noa).json()
    assert noa.post(f"/api/consultations/{c['id']}/presence", json={"event": "joined"}).status_code == 200
    assert noa.post(f"/api/consultations/{c['id']}/presence", json={"event": "hacked"}).status_code == 422
    parts = noa.get(f"/api/consultations/{c['id']}").json()["participants"]
    assert next(p for p in parts if p["meeting_role"] == "patient")["joined_at"]
