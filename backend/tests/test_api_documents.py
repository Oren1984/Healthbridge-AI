import json

from app.seed_data import GOLDEN_FILE, INJECTION_NOTE, make_pdf, sample_bytes
from tests.conftest import Api, run_worker


def upload(api, name, data, **form):
    return api.post(f"/api/patients/{api.id}/documents", files={"file": (name, data)}, data=form)


def test_golden_letter_ingestion(seeded):
    noa = Api("noa")
    r = upload(noa, GOLDEN_FILE, sample_bytes(GOLDEN_FILE))
    assert r.status_code == 201 and r.json()["status"] == "pending" and r.json()["encrypted"]
    doc_id = r.json()["id"]
    assert run_worker() >= 1
    d = noa.get(f"/api/documents/{doc_id}").json()
    assert d["status"] == "processed"
    assert d["organization"]["name"] == "Cedar Ridge Cardiology Clinic"
    assert d["document_date"] == "2026-07-08" and d["category"] == "consultation_note"
    assert len(d["recommendations"]) == 5
    for rec in d["recommendations"]:
        assert rec["passage"] in d["extracted_text"] and rec["review_status"] == "pending_review"
    assert d["events"] and d["events"][0]["event_type"] == "specialist_consultation"
    # journey + care gap + notification
    journey = noa.get(f"/api/patients/{noa.id}/journey?q=Cedar").json()
    assert any(doc_id in [x["id"] for x in e["documents"]] for e in journey)
    gaps = noa.get(f"/api/patients/{noa.id}/care-gaps").json()
    echo = next(g for g in gaps if "echocardiogram within 6 weeks" in g["title"].lower())
    assert echo["status"] == "unknown" and doc_id in echo["document_ids"]
    notes = noa.get("/api/notifications").json()["items"]
    assert any(n["kind"] == "document_processed" for n in notes)


def test_duplicate_detection(seeded):
    noa = Api("noa")
    data = make_pdf("Unique duplicate test document\nDate: 2026-09-09\nNothing else.")
    first = upload(noa, "dup.pdf", data)
    assert first.status_code == 201
    again = upload(noa, "dup-copy.pdf", data)
    assert again.status_code == 409 and again.json()["existing_id"] == first.json()["id"]
    run_worker()


def test_malicious_uploads_rejected_and_audited(seeded):
    noa = Api("noa")
    cases = {"evil.pdf": make_pdf("x").replace(b"<< /Type /Catalog", b"<< /OpenAction << /JS (x) >> /Type /Catalog"),
             "run.exe": b"MZ\x90", "masked.txt": b"MZ\x90\x00", "page.html": b"<html></html>"}
    for name, data in cases.items():
        r = upload(noa, name, data)
        assert r.status_code == 422, name
        assert "code" in r.json()
    log = noa.get(f"/api/patients/{noa.id}/access-log").json()
    assert sum(1 for e in log if e["action"] == "document.upload" and e["outcome"] == "denied") >= 4


def test_professional_cannot_upload_for_patient(seeded):
    noa, morgan = Api("noa"), Api("morgan")
    r = morgan.post(f"/api/patients/{noa.id}/documents", files={"file": ("x.txt", b"hello there")})
    assert r.status_code == 404


def test_download_is_attachment_and_decrypted(seeded):
    noa = Api("noa")
    docs = noa.get(f"/api/patients/{noa.id}/documents?q=Cedar").json()
    r = noa.get(f"/api/documents/{docs[0]['id']}/download")
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    assert r.headers["content-disposition"].startswith("attachment;")
    assert r.headers["content-type"] == "application/octet-stream"


def test_stored_file_is_encrypted_at_rest(seeded):
    from app.db import SessionLocal
    from app.models import Document
    from app.security.storage import get_storage

    with SessionLocal() as db:
        d = db.query(Document).filter(Document.original_filename == GOLDEN_FILE).first()
        raw = get_storage()._path(d.storage_key).read_bytes()
    assert not raw.startswith(b"%PDF") and b"echocardiogram" not in raw


def test_metadata_correction_and_versioning(seeded):
    noa = Api("noa")
    r = upload(noa, "v1.txt", b"Clinic visit summary\nDate: 2026-09-01\nPlease schedule a follow-up visit in 2 weeks.\n")
    doc_id = r.json()["id"]
    run_worker()
    patched = noa.patch(f"/api/documents/{doc_id}", json={"title": "Corrected title", "document_date": "2026-09-02"})
    assert patched.json()["title"] == "Corrected title" and patched.json()["document_date"] == "2026-09-02"
    v2 = noa.post(f"/api/documents/{doc_id}/versions", files={"file": ("v2.txt", b"Clinic visit summary v2\nDate: 2026-09-02\n")})
    assert v2.status_code == 201 and v2.json()["version"] == 2
    run_worker()
    detail = noa.get(f"/api/documents/{v2.json()['id']}").json()
    assert [v["version"] for v in detail["versions"]] == [1, 2]
    latest_ids = [d["id"] for d in noa.get(f"/api/patients/{noa.id}/documents").json()]
    assert v2.json()["id"] in latest_ids and doc_id not in latest_ids
    assert noa.post(f"/api/documents/{doc_id}/versions", files={"file": ("v3.txt", b"other")}).status_code == 409


def test_fhir_upload_and_unsupported_reporting(seeded):
    noa = Api("noa")
    bundle = {"resourceType": "Bundle", "type": "collection", "entry": [
        {"resource": {"resourceType": "Observation", "id": "o1", "status": "final", "code": {"text": "TSH"},
                      "effectiveDateTime": "2026-09-05", "valueQuantity": {"value": 2.1, "unit": "mIU/L"}, "note": [{"text": "x"}]}},
        {"resource": {"resourceType": "AllergyIntolerance", "id": "a1"}}]}
    r = upload(noa, "tsh.json", json.dumps(bundle).encode())
    assert r.status_code == 201
    run_worker()
    d = noa.get(f"/api/documents/{r.json()['id']}").json()
    assert d["category"] == "fhir_record" and d["status"] == "processed"
    assert any("AllergyIntolerance" in s for s in d["import_report"]["skipped"])
    assert any("note" in s for s in d["import_report"]["ignored_fields"])
    export = noa.get(f"/api/patients/{noa.id}/fhir/export")
    assert export.status_code == 200 and export.json()["resourceType"] == "Bundle"
    types = {e["resource"]["resourceType"] for e in export.json()["entry"]}
    assert {"Patient", "Encounter", "DocumentReference", "ServiceRequest"} <= types


def test_scanned_like_pdf_needs_review(seeded):
    noa = Api("noa")
    r = upload(noa, "scan.pdf", make_pdf(" "))
    run_worker()
    d = noa.get(f"/api/documents/{r.json()['id']}").json()
    assert d["status"] == "needs_review" and "OCR" in d["status_detail"]


def test_delete_document_removes_access_and_index(seeded):
    noa = Api("noa")
    r = upload(noa, "todelete.txt", INJECTION_NOTE.encode())
    run_worker()
    doc_id = r.json()["id"]
    assert noa.delete(f"/api/documents/{doc_id}").status_code == 200
    assert noa.get(f"/api/documents/{doc_id}").status_code == 404
    from app.db import SessionLocal
    from app.models import DocumentChunk

    with SessionLocal() as db:
        assert db.query(DocumentChunk).filter(DocumentChunk.document_id == doc_id).count() == 0


def test_search_documents_by_content(seeded):
    noa = Api("noa")
    hits = noa.get(f"/api/patients/{noa.id}/documents?q=echocardiogram").json()
    assert any("Cedar" in d["title"] for d in hits)
    assert noa.get(f"/api/patients/{noa.id}/documents?q=%25").status_code == 200  # wildcard is escaped
