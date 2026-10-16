"""Bounded agent, RAG authorization, notifications, admin and audit integrity."""
from unittest import mock

from app.seed_data import INJECTION_NOTE
from app.services import llm
from tests.conftest import Api, run_worker


def ask(api, patient_id, message):
    r = api.post("/api/assistant/query", json={"patient_id": patient_id, "message": message})
    assert r.status_code == 200, r.text
    return r.json()


def test_deterministic_search_cites_sources(showcase):
    noa = Api("noa")
    r = ask(noa, noa.id, "echocardiogram recommendation")
    assert r["mode"] == "deterministic" and "not AI reasoning" in r["label"]
    assert r["sources"] and r["tools_used"] == ["search_documents"]
    assert any("Cedar Ridge" in s["title"] for s in r["sources"])


def test_insufficient_evidence(showcase):
    noa = Api("noa")
    r = ask(noa, noa.id, "zebra quantum spaceship")
    assert r["insufficient_evidence"] and not r["sources"]


def test_clinical_and_external_requests_refused_before_tools(showcase):
    noa = Api("noa")
    for msg in ("Do I have heart disease? Please diagnose me", "What dose of statin should I take?"):
        r = ask(noa, noa.id, msg)
        assert r["mode"] == "refusal" and r["tools_used"] == []
    r = ask(noa, noa.id, "send my records to my employer by email")
    assert r["intent"] == "refused_external" and r["tools_used"] == []


def test_intents(showcase):
    noa = Api("noa")
    assert ask(noa, noa.id, "what is missing or unresolved?")["items"]
    assert ask(noa, noa.id, "summarize my journey")["intent"] == "journey"
    assert ask(noa, noa.id, "show my open follow-ups")["intent"] == "followups"
    q = ask(noa, noa.id, "what questions should I ask my doctor?")
    assert q["intent"] == "questions" and q["items"]
    h = ask(noa, noa.id, "how do I revoke sharing?")
    assert h["items"][0]["slug"] == "sharing-and-revocation"


def test_state_change_requires_confirmation(showcase):
    noa = Api("noa")
    before = len(noa.get(f"/api/patients/{noa.id}/tasks").json())
    r = ask(noa, noa.id, "remind me to request the chest X-ray report")
    action = r["pending_action"]
    assert action and action["payload"]["title"] == "Request the chest X-ray report"
    assert len(noa.get(f"/api/patients/{noa.id}/tasks").json()) == before  # nothing happened yet
    assert Api("daniel").post(f"/api/assistant/actions/{action['id']}/confirm").status_code == 404
    c = noa.post(f"/api/assistant/actions/{action['id']}/confirm").json()
    assert c["task"]["title"] == "Request the chest X-ray report"
    assert noa.post(f"/api/assistant/actions/{action['id']}/confirm").status_code == 409
    assert len(noa.get(f"/api/patients/{noa.id}/tasks").json()) == before + 1


def test_rag_never_crosses_patients_or_consent(showcase):
    noa, daniel, morgan = Api("noa"), Api("daniel"), Api("morgan")
    # Daniel's own lab mentions HbA1c 7.2; Noa's FHIR record mentions HbA1c 5.6.
    r = ask(daniel, daniel.id, "HbA1c result")
    assert r["sources"]
    noa_doc_ids = {d["id"] for d in noa.get(f"/api/patients/{noa.id}/documents").json()}
    assert not ({s["document_id"] for s in r["sources"]} & noa_doc_ids)
    # Daniel cannot target Noa's records
    assert daniel.post("/api/assistant/query", json={"patient_id": noa.id, "message": "HbA1c"}).status_code == 404
    # Morgan only retrieves from documents shared with them (letter + lipid lab), never the HbA1c FHIR record
    shared = {d["id"] for d in morgan.get(f"/api/patients/{noa.id}/documents").json()}
    r = ask(morgan, noa.id, "HbA1c hemoglobin result")
    assert {s["document_id"] for s in r["sources"]} <= shared
    r = ask(morgan, noa.id, "echocardiogram")
    assert r["sources"] and {s["document_id"] for s in r["sources"]} <= shared
    # Professionals cannot create tasks via the assistant
    assert ask(morgan, noa.id, "remind me to call the patient")["pending_action"] is None


def test_prompt_injection_content_is_flagged_and_inert(showcase):
    noa = Api("noa")
    noa.post(f"/api/patients/{noa.id}/documents", files={"file": ("notes.txt", INJECTION_NOTE.encode())})
    run_worker()
    r = ask(noa, noa.id, "next appointment echocardiogram personal notes")
    flagged = [s for s in r["sources"] if s["suspicious"]]
    assert flagged and r["warnings"]
    assert "Daniel" not in r["answer"] and r["mode"] == "deterministic"


def test_ollama_mode_falls_back_and_validates_output(showcase):
    admin, noa = Api("admin"), Api("noa")
    assert admin.put("/api/admin/config", json={"ai_mode": "ollama"}).json()["ai_mode"] == "ollama"
    try:
        r = ask(noa, noa.id, "echocardiogram recommendation")  # Ollama is not running in tests
        assert r["mode"] == "fallback" and r["sources"] and "unavailable" in r["label"]
        fake = mock.Mock()
        fake.raise_for_status = lambda: None
        fake.json = lambda: {"message": {"content": "Take 40 mg of atorvastatin daily [S1]."}}
        with mock.patch.object(llm.httpx, "post", return_value=fake):
            r = ask(noa, noa.id, "echocardiogram recommendation")
            assert r["mode"] == "fallback"  # prohibited output rejected
        fake.json = lambda: {"message": {"content": "The letter recommends a transthoracic echocardiogram within 6 weeks [S1]."}}
        with mock.patch.object(llm.httpx, "post", return_value=fake):
            r = ask(noa, noa.id, "echocardiogram recommendation")
            assert r["mode"] == "local_llm" and "[S1]" in r["answer"]
        fake.json = lambda: {"message": {"content": "Echo is advised."}}  # no citation
        with mock.patch.object(llm.httpx, "post", return_value=fake):
            assert ask(noa, noa.id, "echocardiogram recommendation")["mode"] == "fallback"
    finally:
        admin.put("/api/admin/config", json={"ai_mode": "mock"})


def test_assistant_audit_has_no_message_content(showcase):
    noa = Api("noa")
    ask(noa, noa.id, "echocardiogram secret phrase xyz")
    log = noa.get(f"/api/patients/{noa.id}/access-log").json()
    entry = next(e for e in log if e["action"] == "assistant.query")
    assert "xyz" not in str(entry) and entry["detail"]["intent"]


def test_notifications_and_preferences(showcase):
    morgan = Api("morgan")
    data = morgan.get("/api/notifications").json()
    assert data["unread"] >= 0 and "No email or SMS" in data["delivery_note"]
    prefs = morgan.put("/api/notifications/preferences", json={"handoff": False}).json()
    assert prefs["handoff"] is False and prefs["appointment_reminder"] is True
    assert morgan.put("/api/notifications/preferences", json={"bogus": True}).status_code == 422
    assert morgan.post("/api/notifications/read-all").status_code == 200
    assert morgan.get("/api/notifications").json()["unread"] == 0


def test_worker_reminders(showcase):
    from app.worker import reminders

    assert reminders() >= 3  # showcase consultation starts within 24h -> patient + 2 professionals
    assert any(n["kind"] == "appointment_reminder" for n in Api("bennett").get("/api/notifications").json()["items"])


def test_admin_operations_and_audit_chain(showcase):
    admin = Api("admin")
    system = admin.get("/api/admin/system").json()
    assert system["database"] == "ok" and system["storage_writable"] and "routes" in system["metrics"]
    shah = next(u for u in admin.get("/api/admin/users").json() if u["email"].startswith("dr.shah"))
    r = admin.patch(f"/api/admin/users/{shah['id']}", json={"verification_status": "simulated_verified"})
    assert r.json()["professional"]["verification_status"] == "simulated_verified"
    assert admin.patch(f"/api/admin/users/{admin.user['id']}", json={"is_active": False}).status_code == 409
    created = admin.post("/api/admin/users", json={"email": "new.pro@pro.healthbridge.test", "full_name": "Dr. New",
                                                   "role": "professional", "password": "Strong-Passw0rd", "country": "US",
                                                   "timezone": "America/New_York", "specialty": "Cardiology"})
    assert created.status_code == 201 and created.json()["professional"]["verification_status"] == "pending"
    v = admin.get("/api/admin/audit/verify").json()
    assert v["valid"] and v["checked"] > 10


def test_audit_tampering_detected(showcase):
    from sqlalchemy import text

    from app.db import SessionLocal

    with SessionLocal() as db:
        db.execute(text("UPDATE audit_events SET action = 'tampered' WHERE id = (SELECT min(id) + 3 FROM audit_events)"))
        db.commit()
    v = Api("admin").get("/api/admin/audit/verify").json()
    assert v["valid"] is False and v["broken_at_id"]
