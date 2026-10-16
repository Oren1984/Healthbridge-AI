"""Cross-patient isolation, consent enforcement, IDOR/BOLA, admin separation."""
import json
import uuid
from datetime import timedelta

from app.db import SessionLocal
from app.models import AuditEvent, ConsentGrant, utcnow
from tests.conftest import Api, user_id


def _noa_docs():
    noa = Api("noa")
    return noa, noa.get(f"/api/patients/{noa.id}/documents").json()


def test_patient_cannot_access_other_patient(seeded):
    noa, docs = _noa_docs()
    daniel = Api("daniel")
    pid = noa.id
    for path in (f"/api/patients/{pid}/documents", f"/api/patients/{pid}/journey", f"/api/patients/{pid}/care-gaps",
                 f"/api/patients/{pid}/tasks", f"/api/patients/{pid}/recommendations"):
        assert daniel.get(path).status_code == 404, path
    for d in docs:
        assert daniel.get(f"/api/documents/{d['id']}").status_code == 404
        assert daniel.get(f"/api/documents/{d['id']}/download").status_code == 404
    assert daniel.get(f"/api/patients/{pid}/access-log").status_code in (403, 404)
    assert daniel.post(f"/api/patients/{pid}/grants", json={"grantee_id": str(user_id("morgan")), "include_journey": True}).status_code in (403, 404)


def test_denials_are_audited(seeded):
    noa, docs = _noa_docs()
    Api("daniel").get(f"/api/documents/{docs[0]['id']}")
    with SessionLocal() as db:
        ev = db.query(AuditEvent).filter(AuditEvent.outcome == "denied", AuditEvent.resource_id == docs[0]["id"]).first()
        assert ev is not None and ev.action == "document.view"


def test_professional_without_grant_sees_nothing(seeded):
    noa, docs = _noa_docs()
    morgan = Api("morgan")
    assert morgan.get(f"/api/patients/{noa.id}/documents").status_code == 404
    assert morgan.get(f"/api/documents/{docs[0]['id']}").status_code == 404
    assert morgan.get("/api/shared-with-me").json() == []


def test_grant_scopes_exact_documents_and_sections(seeded):
    noa, docs = _noa_docs()
    morgan = Api("morgan")
    shared, other = docs[0], docs[1]
    r = noa.post(f"/api/patients/{noa.id}/grants", json={"grantee_id": morgan.id, "document_ids": [shared["id"]], "days": 7})
    assert r.status_code == 201
    listed = morgan.get(f"/api/patients/{noa.id}/documents").json()
    assert [d["id"] for d in listed] == [shared["id"]]
    assert morgan.get(f"/api/documents/{shared['id']}").status_code == 200
    assert morgan.get(f"/api/documents/{shared['id']}/download").status_code == 200
    assert morgan.get(f"/api/documents/{other['id']}").status_code == 404
    assert morgan.get(f"/api/documents/{other['id']}/download").status_code == 404
    # No journey / care-gap access without those flags
    assert morgan.get(f"/api/patients/{noa.id}/journey").status_code == 404
    assert morgan.get(f"/api/patients/{noa.id}/care-gaps").status_code == 404
    # Professionals cannot modify patient documents or grants
    assert morgan.patch(f"/api/documents/{shared['id']}", json={"title": "x"}).status_code == 404
    grant_id = r.json()["id"]
    assert morgan.post(f"/api/grants/{grant_id}/revoke").status_code == 403
    # Revocation takes effect immediately
    assert noa.post(f"/api/grants/{grant_id}/revoke").json()["state"] == "revoked"
    assert morgan.get(f"/api/documents/{shared['id']}").status_code == 404
    assert morgan.get(f"/api/documents/{shared['id']}/download").status_code == 404


def test_expired_grant_denies_access(seeded):
    noa, docs = _noa_docs()
    bennett = Api("bennett")
    r = noa.post(f"/api/patients/{noa.id}/grants", json={"grantee_id": bennett.id, "document_ids": [docs[0]["id"]], "days": 1})
    assert bennett.get(f"/api/documents/{docs[0]['id']}").status_code == 200
    with SessionLocal() as db:
        g = db.get(ConsentGrant, uuid.UUID(r.json()["id"]))
        g.expires_at = utcnow() - timedelta(minutes=1)
        db.commit()
    assert bennett.get(f"/api/documents/{docs[0]['id']}").status_code == 404
    states = {g["id"]: g["state"] for g in noa.get(f"/api/patients/{noa.id}/grants").json()["grants"]}
    assert states[r.json()["id"]] == "expired"


def test_category_grant_and_journey_flags(seeded):
    noa, docs = _noa_docs()
    ronen = Api("ronen")
    noa.post(f"/api/patients/{noa.id}/grants", json={"grantee_id": ronen.id, "categories": ["lab_result"],
                                                     "include_journey": True, "include_care_gaps": True, "days": 3})
    listed = ronen.get(f"/api/patients/{noa.id}/documents").json()
    assert listed and all(d["category"] == "lab_result" for d in listed)
    events = ronen.get(f"/api/patients/{noa.id}/journey").json()
    assert events
    # Event documents outside the grant are hidden but counted
    visible_ids = {d["id"] for d in listed}
    for e in events:
        assert all(d["id"] in visible_ids for d in e["documents"])
    assert any(e["hidden_documents"] > 0 for e in events)
    assert ronen.get(f"/api/patients/{noa.id}/care-gaps").status_code == 200
    # access history shows the professional's views to the patient
    log = noa.get(f"/api/patients/{noa.id}/access-log?only_others=true").json()
    assert any(e["action"] == "journey.view" and e["actor"]["full_name"] == "Dr. Yael Ronen" for e in log)


def test_care_gaps_redacted_for_partially_shared_professional(showcase):
    """A care-gap grant must not reveal titles, recommendation text or IDs from documents that were not shared."""
    noa, docs = _noa_docs()
    letter = next(d for d in docs if "Consultation Letter" in d["title"])
    before = noa.get(f"/api/patients/{noa.id}/care-gaps").json()
    ronen = Api("ronen")
    assert noa.post(f"/api/patients/{noa.id}/grants", json={"grantee_id": ronen.id, "document_ids": [letter["id"]],
                                                            "include_care_gaps": True, "days": 3}).status_code == 201
    visible = {d["id"] for d in ronen.get(f"/api/patients/{noa.id}/documents").json()}
    recs = noa.get(f"/api/patients/{noa.id}/recommendations").json()
    shown_texts = {r["text"] for r in recs if r["document_id"] in visible}
    hidden_texts = {r["text"] for r in recs if r["document_id"] not in visible} - shown_texts
    hidden_docs = [d for d in docs if d["id"] not in visible]
    assert hidden_texts and hidden_docs and shown_texts

    def assert_no_leak(payload, where):
        blob = json.dumps(payload, ensure_ascii=False)
        for t in hidden_texts:
            assert t not in blob, f"{where}: recommendation text leaked: {t}"
        for d in hidden_docs:
            assert d["id"] not in blob and d["title"] not in blob, f"{where}: document leaked: {d['title']}"
        assert "Dr. Oliver Bennett" not in blob and "Dr. Rachel Morgan" not in blob, f"{where}: other professional leaked"

    gaps = ronen.get(f"/api/patients/{noa.id}/care-gaps").json()
    assert_no_leak(gaps, "care-gaps list")
    assert {g["id"] for g in gaps} == {g["id"] for g in before}  # the findings themselves stay visible
    assert any(g["redacted_for_viewer"] for g in gaps)
    assert any(g["params"].get("redacted") for g in gaps if g["rule_id"] == "CG-009")
    # No journey grant: event/task evidence and event-derived titles are hidden; no handoffs or foreign consultations
    assert not [e for g in gaps for e in g["supporting_evidence"] if e["type"] in ("event", "task", "handoff", "consultation")]
    assert all(g["params"].get("redacted") for g in gaps if g["rule_id"] in ("CG-006", "CG-008"))
    # Findings sourced from the shared letter are not over-redacted
    titles = " ".join(g["title"] for g in gaps)
    assert all(t[:140] in titles for t in shown_texts if any(g["params"].get("text") == t[:200] for g in before))
    redacted = next(g for g in gaps if g["redacted_for_viewer"] and g["recommendation_id"])
    reviewed = ronen.post(f"/api/care-gaps/{redacted['id']}/review", json={"action": "clarify"})
    assert reviewed.status_code == 200
    assert_no_leak(reviewed.json(), "review response")
    # The assistant uses the same redacted view
    for message in ("What care gaps are unresolved?", "What questions should I ask my doctor?"):
        r = ronen.post("/api/assistant/query", json={"patient_id": noa.id, "message": message})
        assert r.status_code == 200
        assert_no_leak(r.json(), f"assistant: {message}")
    # The patient's own view is unchanged (apart from the review just made) and never redacted
    after = {g["id"]: g for g in noa.get(f"/api/patients/{noa.id}/care-gaps").json()}
    volatile = ("review_status", "reviewed_at", "status", "last_evaluated_at", "relevant_dates")
    for g in before:
        assert {k: v for k, v in after[g["id"]].items() if k not in volatile} == {k: v for k, v in g.items() if k not in volatile}
        assert "redacted_for_viewer" not in after[g["id"]]


def test_unverified_professional_cannot_receive_grants(seeded):
    noa = Api("noa")
    r = noa.post(f"/api/patients/{noa.id}/grants", json={"grantee_id": str(user_id("shah")), "include_journey": True})
    assert r.status_code == 422


def test_admin_has_no_clinical_access(seeded):
    noa, docs = _noa_docs()
    admin = Api("admin")
    assert admin.get(f"/api/patients/{noa.id}/documents").status_code == 403
    assert admin.get(f"/api/documents/{docs[0]['id']}").status_code == 403
    assert admin.get(f"/api/documents/{docs[0]['id']}/download").status_code == 403
    assert admin.post("/api/assistant/query", json={"patient_id": noa.id, "message": "hi"}).status_code == 403
    users = admin.get("/api/admin/users").json()
    assert users and all("extracted_text" not in str(u) for u in users)
    events = admin.get("/api/admin/security-events").json()
    assert events and all("patient_id" not in e for e in events)


def test_role_separation(seeded):
    assert Api("noa").get("/api/admin/users").status_code == 403
    assert Api("morgan").get("/api/admin/system").status_code == 403
    assert Api("noa").get("/api/shared-with-me").status_code == 403


def test_random_ids_return_404(seeded):
    noa = Api("noa")
    fake = "00000000-0000-4000-8000-000000000000"
    for path in (f"/api/documents/{fake}", f"/api/journey/{fake}", f"/api/consultations/{fake}"):
        assert noa.get(path).status_code == 404
    assert noa.get("/api/documents/not-a-uuid").status_code == 422
