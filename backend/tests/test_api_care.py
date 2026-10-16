"""Recommendations review, care gaps and follow-up task transitions (showcase scenario)."""
from tests.conftest import Api


def gaps(noa):
    return noa.get(f"/api/patients/{noa.id}/care-gaps").json()


def find(items, text):
    return next(i for i in items if text.lower() in i["title"].lower())


def test_gap_payload_is_explainable(showcase):
    noa = Api("noa")
    g = find(gaps(noa), "CBC and lipid panel")
    assert g["status"] == "unknown" and g["rule_id"] == "CG-003" and g["rule"]
    assert g["missing_evidence"] == ["Laboratory result for: cbc"]
    assert {e["type"] for e in g["supporting_evidence"]} >= {"recommendation", "document"}
    assert g["suggested_clarification"] and g["relevant_dates"]["recommendation_documented"] == "2026-05-12"
    statuses = {x["status"] for x in gaps(noa)}
    assert {"unknown", "open", "requires_clarification", "completed_verified"} <= statuses


def test_review_actions(showcase):
    noa = Api("noa")
    g = find(gaps(noa), "Chest X-ray")
    assert noa.post(f"/api/care-gaps/{g['id']}/review", json={"action": "dismiss"}).status_code == 422  # reason required
    r = noa.post(f"/api/care-gaps/{g['id']}/review", json={"action": "dismiss", "note": "Report not needed per ED physician."})
    assert r.json()["status"] == "not_applicable" and r.json()["computed_status"] == "unknown"
    noa.post(f"/api/patients/{noa.id}/care-gaps/evaluate")
    assert find(gaps(noa), "Chest X-ray")["status"] == "not_applicable"  # human decision survives re-evaluation
    assert noa.post(f"/api/care-gaps/{g['id']}/review", json={"action": "reopen"}).json()["status"] == "unknown"
    created = noa.post(f"/api/care-gaps/{g['id']}/review", json={"action": "create_clarification"}).json()
    task = created["created_task"]
    assert task["kind"] == "clarification" and task["care_gap_id"] == g["id"] and task["due_date"] is None


def test_followup_lifecycle_requires_evidence_for_verification(showcase):
    noa = Api("noa")
    tasks = noa.get(f"/api/patients/{noa.id}/tasks").json()
    echo = next(t for t in tasks if "echocardiogram within" in t["title"].lower())
    assert echo["status"] == "open" and echo["due_date"] is None  # no invented deadline
    assert find(gaps(noa), "echocardiogram within")["status"] == "open"

    r = noa.post(f"/api/tasks/{echo['id']}/complete", json={"note": "Done at Bluewave"})
    assert r.json()["status"] == "completed_reported"
    g = find(gaps(noa), "echocardiogram within")
    assert g["status"] == "unknown" and "A document confirming completion" in g["missing_evidence"][-1]

    up = noa.post(f"/api/patients/{noa.id}/documents", files={"file": ("echo-report.txt",
                  b"Bluewave Imaging Institute - Echocardiogram Report\nReport date: 2026-08-01\nNormal left ventricular function.\n")},
                  data={"category": "imaging_report"})
    from tests.conftest import run_worker

    run_worker()
    v = noa.post(f"/api/tasks/{echo['id']}/verify", json={"evidence_document_id": up.json()["id"]})
    assert v.json()["status"] == "completed_verified"
    g = find(gaps(noa), "echocardiogram within")
    assert g["status"] == "completed_verified"
    assert any(e["id"] == up.json()["id"] for e in g["supporting_evidence"])

    assert noa.post(f"/api/tasks/{echo['id']}/reopen").json()["status"] == "open"
    history = noa.get(f"/api/tasks/{echo['id']}/history").json()
    assert [h["action"] for h in history][-3:] == ["task.complete", "task.verify", "task.reopen"]


def test_evidence_must_belong_to_patient(showcase):
    noa, daniel = Api("noa"), Api("daniel")
    other_doc = daniel.get(f"/api/patients/{daniel.id}/documents").json()[0]
    t = noa.post(f"/api/patients/{noa.id}/tasks", json={"title": "Bring CBC result"}).json()
    r = noa.post(f"/api/tasks/{t['id']}/complete", json={"evidence_document_id": other_doc["id"]})
    assert r.status_code == 404


def test_manual_task_due_date_and_owner_rules(showcase):
    noa = Api("noa")
    t = noa.post(f"/api/patients/{noa.id}/tasks", json={"title": "Call clinic", "due_date": "2026-11-01"}).json()
    assert t["due_date_source"] == "user_entered"
    from tests.conftest import user_id

    bad = noa.patch(f"/api/tasks/{t['id']}", json={"owner_id": str(user_id("haddad"))})  # no active grant
    assert bad.status_code == 422
    ok = noa.patch(f"/api/tasks/{t['id']}", json={"owner_id": str(user_id("morgan"))})  # has grant in showcase
    assert ok.status_code == 200
    assert noa.post(f"/api/tasks/{t['id']}/dismiss", json={"note": "no"}).status_code == 422
    assert noa.post(f"/api/tasks/{t['id']}/dismiss", json={"note": "Handled by phone"}).json()["status"] == "not_applicable"


def test_recommendation_review_and_tracking(showcase):
    noa = Api("noa")
    recs = noa.get(f"/api/patients/{noa.id}/recommendations").json()
    hmo = next(r for r in recs if r["text"].startswith("CBC and lipid"))
    c = noa.patch(f"/api/recommendations/{hmo['id']}", json={"action": "correct", "text": "CBC and lipid panel blood tests.",
                                                              "kind": "lab_test"}).json()
    assert c["review_status"] == "corrected" and c["original_text"] == "CBC and lipid panel blood tests are recommended."
    t = noa.post(f"/api/recommendations/{hmo['id']}/track")
    assert t.status_code == 201 and t.json()["recommendation_id"] == hmo["id"]
    assert noa.post(f"/api/recommendations/{hmo['id']}/track").json()["id"] == t.json()["id"]  # idempotent
    rej = next(r for r in recs if r["text"].startswith("Referral to cardiology for further"))
    assert noa.patch(f"/api/recommendations/{rej['id']}", json={"action": "reject"}).json()["review_status"] == "rejected"
    assert not [g for g in gaps(noa) if g["recommendation_id"] == rej["id"]]


def test_professional_proposal_requires_journey_access(showcase):
    noa, morgan, haddad = Api("noa"), Api("morgan"), Api("haddad")
    body = {"kind": "imaging", "text": "Cardiac MRI if echocardiogram is inconclusive"}
    assert morgan.post(f"/api/patients/{noa.id}/recommendations", json=body).status_code == 404  # documents-only grant
    assert haddad.post(f"/api/patients/{noa.id}/recommendations", json=body).status_code == 404


def test_replay_matches_persisted_and_is_side_effect_free(showcase):
    noa = Api("noa")
    before = noa.get(f"/api/patients/{noa.id}/care-gaps").json()
    replay = noa.get(f"/api/patients/{noa.id}/care-gaps/replay?as_of=2026-10-15").json()
    assert replay["findings"] and "CG-001" in replay["rules"]
    again = noa.get(f"/api/patients/{noa.id}/care-gaps/replay?as_of=2026-10-15").json()
    assert replay["findings"] == again["findings"]
    assert noa.get(f"/api/patients/{noa.id}/care-gaps").json() == before
    early = noa.get(f"/api/patients/{noa.id}/care-gaps/replay?as_of=2026-06-01").json()
    # Events after as_of are not yet expected to have documents
    assert not any(f["rule_id"] == "CG-008" and "Chest X-ray" in f["title"] for f in early["findings"])
    assert any(f["rule_id"] == "CG-008" and "Chest X-ray" in f["title"] for f in replay["findings"])
