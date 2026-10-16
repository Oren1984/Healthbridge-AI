"""Retrieval evaluation on the synthetic corpus (showcase scenario).

Each labeled query names the document that should be retrieved. We report hit@1 and hit@3 for the
active embedding provider and assert a minimum quality bar, so regressions are caught.
"""
from app.db import SessionLocal
from app.models import Document, User
from app.services.rag import retrieve

LABELED = [
    ("echocardiogram within 6 weeks", "05-cedar-ridge-cardiology-letter.pdf"),
    ("second opinion international cardiology specialist", "05-cedar-ridge-cardiology-letter.pdf"),
    ("LDL cholesterol result", "02-northstar-lipid-panel.pdf"),
    ("troponin emergency department discharge", "03-harbor-crest-discharge-summary.txt"),
    ("follow-up with family physician within 1 week", "03-harbor-crest-discharge-summary.txt"),
    ("CBC blood tests recommended", "01-tamar-family-medicine-visit.pdf"),
    ("chest discomfort during brisk walking", "01-tamar-family-medicine-visit.pdf"),
    ("referral letter to cardiology service", "04-tamar-referral-letter.txt"),
    ("HbA1c laboratory result", "07-northstar-hba1c.fhir.json"),
    ("מעקב לחץ דם", "06-tamar-nurse-note-he.txt"),
]


def test_retrieval_quality(showcase):
    with SessionLocal() as db:
        noa = db.query(User).filter(User.email == "noa@patient.healthbridge.test").one()
        docs = {d.id: d.original_filename for d in db.query(Document).filter(Document.patient_id == noa.id)}
        allowed = set(docs)
        hit1 = hit3 = 0
        for query, expected in LABELED:
            got = [docs[c.document_id] for c in retrieve(db, noa.id, allowed, query, k=3)]
            hit1 += bool(got) and got[0] == expected
            hit3 += expected in got
    n = len(LABELED)
    print(f"\nRAG evaluation (n={n}): hit@1={hit1}/{n} hit@3={hit3}/{n}")
    assert hit3 / n >= 0.8 and hit1 / n >= 0.6


def test_retrieval_respects_allowed_set(showcase):
    """Even a perfect lexical match is not returned when its document is not authorized."""
    with SessionLocal() as db:
        noa = db.query(User).filter(User.email == "noa@patient.healthbridge.test").one()
        letter = db.query(Document).filter(Document.original_filename == "05-cedar-ridge-cardiology-letter.pdf").one()
        others = {d.id for d in db.query(Document).filter(Document.patient_id == noa.id, Document.id != letter.id)}
        got = retrieve(db, noa.id, others, "Transthoracic echocardiogram within 6 weeks", k=5)
        assert all(c.document_id != letter.id for c in got)
