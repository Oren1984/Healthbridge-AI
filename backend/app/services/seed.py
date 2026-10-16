"""Repeatable synthetic seeding.

Scenarios
- fresh:    the patient's prior history only. The golden-scenario cardiology letter is NOT yet
            uploaded, so the full flow can be demonstrated live from step 1.
- showcase: history + the cardiology letter ingested through the real pipeline, follow-up
            tracking, sharing with two international cardiologists and a consultation scheduled
            to start shortly (so the video room is open).

Usage: python -m app.services.seed [seed|reset|seed-if-empty] [fresh|showcase]
       python -m app.services.seed export-samples <dir>
"""
import hashlib
import shutil
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from sqlalchemy import select, text

from app import audit
from app.config import get_settings
from app.db import Base, SessionLocal
from app.models import (
    ConsentGrant, Consultation, ConsultationParticipant, Document, FollowUpTask, JourneyEvent, Organization,
    PatientProfile, ProfessionalProfile, Recommendation, User, utcnow,
)
from app.security.passwords import hash_password
from app.seed_data import DANIEL_LAB, GOLDEN_FILE, ORGANIZATIONS, PASSWORD, SAMPLE_FILES, USERS, sample_bytes
from app.services.care_gaps import evaluate_patient
from app.services.documents import create_document, process_document

SCENARIOS = [
    {"id": "fresh", "title": "Golden scenario — start from the beginning",
     "description": "Noa's prior history is loaded. Upload the Cedar Ridge cardiology letter yourself and walk through "
                    "extraction, care gaps, sharing, an international video consultation and an approved summary."},
    {"id": "showcase", "title": "Golden scenario — ready to consult",
     "description": "The cardiology letter is already processed, follow-ups are tracked, documents are shared with "
                    "Dr. Morgan (US) and Dr. Bennett (UK), and a consultation starts in about 30 minutes."},
]
DEMO_ACCOUNTS = [{"key": u[0], "email": u[1], "name": u[2], "role": u[3], "country": u[4], "password": PASSWORD,
                  **({"specialty": u[7]["specialty"], "verified": u[7]["verified"]} if u[3] == "professional" else {})}
                 for u in USERS]


def _at(d: str, hour: int = 9) -> datetime:
    return datetime.combine(date.fromisoformat(d), time(hour, 0), tzinfo=timezone.utc)


def _upload(db, patient: User, filename: str, orgs: dict, event: JourneyEvent | None = None) -> Document:
    _, _, org_key, category = SAMPLE_FILES[filename]
    doc = create_document(db, patient.id, patient, filename, sample_bytes(filename),
                          max_bytes=get_settings().max_upload_bytes, category=category,
                          organization_id=orgs[org_key].id if org_key else None,
                          event_id=event.id if event else None)
    db.flush()
    process_document(db, doc)
    db.flush()
    return doc


def _event(db, patient: User, etype: str, title: str, when: str, org: Organization | None, status: str,
           description: str | None = None) -> JourneyEvent:
    ev = JourneyEvent(patient_id=patient.id, event_type=etype, title=title, description=description,
                      organization_id=org.id if org else None, occurred_at=_at(when), verification_status=status,
                      provenance="manual", provenance_detail="Entered by the patient (seeded)", created_by=patient.id)
    db.add(ev)
    db.flush()
    return ev


def seed(scenario: str = "showcase") -> dict:
    if scenario not in {"fresh", "showcase"}:
        raise ValueError("scenario must be fresh or showcase")
    with SessionLocal() as db:
        orgs = {}
        for key, name, name_he, kind, country, city in ORGANIZATIONS:
            o = Organization(name=name, name_he=name_he, kind=kind, country=country, city=city, synthetic=True)
            db.add(o)
            orgs[key] = o
        db.flush()
        pw = hash_password(PASSWORD)
        users = {}
        for key, email, name, role, country, tz, locale, extra in USERS:
            u = User(email=email, password_hash=pw, full_name=name, role=role, country=country, timezone=tz, locale=locale)
            db.add(u)
            db.flush()
            if role == "patient":
                db.add(PatientProfile(user_id=u.id, date_of_birth=date.fromisoformat(extra["dob"]),
                                      primary_organization_id=orgs[extra["org"]].id))
            elif role == "professional":
                db.add(ProfessionalProfile(user_id=u.id, specialty=extra["specialty"], organization_id=orgs[extra["org"]].id,
                                           license_number=f"SYN-{key.upper()}-{int(hashlib.sha256(email.encode()).hexdigest()[:6], 16) % 10000:04d}",
                                           verification_status="simulated_verified" if extra["verified"] else "pending",
                                           verified_at=utcnow() if extra["verified"] else None))
            users[key] = u
        db.flush()
        noa, daniel = users["noa"], users["daniel"]

        # --- Noa: prior history (manual events + documents through the real pipeline)
        _upload(db, noa, "01-tamar-family-medicine-visit.pdf", orgs)
        _upload(db, noa, "02-northstar-lipid-panel.pdf", orgs)
        er = _event(db, noa, "hospital_visit", "Emergency department visit — chest discomfort", "2026-06-02", orgs["harbor"],
                    "documented")
        _upload(db, noa, "03-harbor-crest-discharge-summary.txt", orgs, er)
        _event(db, noa, "imaging", "Chest X-ray (emergency department)", "2026-06-02", orgs["harbor"], "patient_reported",
               "Performed during the emergency visit; report not received.")
        _event(db, noa, "hmo_consultation", "Family physician follow-up", "2026-06-20", orgs["tamar"], "patient_reported",
               "Patient reports attending a follow-up visit. No visit summary in HealthBridge.")
        referral_ev = _event(db, noa, "referral", "Referral to cardiology", "2026-07-02", orgs["tamar"], "patient_reported")
        _upload(db, noa, "04-tamar-referral-letter.txt", orgs, referral_ev)
        nurse_ev = _event(db, noa, "other", "Nurse blood-pressure check", "2026-08-10", orgs["tamar"], "documented")
        _upload(db, noa, "06-tamar-nurse-note-he.txt", orgs, nurse_ev)
        _upload(db, noa, "07-northstar-hba1c.fhir.json", orgs)

        # Examples of ended permissions so the Sharing Center shows full history.
        now = utcnow()
        hmo_doc = db.execute(select(Document).where(Document.patient_id == noa.id,
                                                    Document.original_filename == "01-tamar-family-medicine-visit.pdf")).scalar_one()
        revoked = ConsentGrant(patient_id=noa.id, grantee_id=users["haddad"].id, categories=["lab_result"], include_journey=True,
                               purpose="Family physician review", starts_at=now - timedelta(days=40),
                               expires_at=now + timedelta(days=20), revoked_at=now - timedelta(days=5))
        expired = ConsentGrant(patient_id=noa.id, grantee_id=users["ronen"].id, purpose="Pre-consultation review",
                               starts_at=now - timedelta(days=100), expires_at=now - timedelta(days=86), expiry_notified=True)
        expired.documents = [hmo_doc]
        db.add_all([revoked, expired])

        # --- Daniel: separate patient for isolation
        db.flush()
        daniel_doc = create_document(db, daniel.id, daniel, "daniel-hba1c.txt", DANIEL_LAB.encode(),
                                     max_bytes=get_settings().max_upload_bytes, category="lab_result",
                                     organization_id=orgs["northstar"].id)
        db.flush()
        process_document(db, daniel_doc)

        if scenario == "showcase":
            letter = _upload(db, noa, GOLDEN_FILE, orgs)
            lab = db.execute(select(Document).where(Document.patient_id == noa.id,
                                                    Document.original_filename == "02-northstar-lipid-panel.pdf")).scalar_one()
            recs = db.execute(select(Recommendation).where(Recommendation.document_id == letter.id)).scalars().all()
            for r in recs:
                r.review_status, r.reviewed_by, r.reviewed_at = "confirmed", noa.id, now
            echo = next(r for r in recs if r.kind == "imaging" and "echocardiogram within" in r.text.lower())
            db.add(FollowUpTask(patient_id=noa.id, recommendation_id=echo.id, kind="follow_up", title=echo.text,
                                description=f"Documented timeframe: {echo.timeframe_text}", owner_id=noa.id, created_by=noa.id,
                                reminder_days_before=3))
            start = (now + timedelta(minutes=30)).replace(second=0, microsecond=0)
            c = Consultation(patient_id=noa.id, title="International cardiology second opinion",
                             purpose="Review the Cedar Ridge cardiology letter and agree next steps.",
                             scheduled_start=start, duration_minutes=45, room_name="hb-showcase-" + now.strftime("%H%M%S"),
                             created_by=noa.id)
            c.participants = [ConsultationParticipant(user_id=noa.id, meeting_role="patient", invite_status="accepted"),
                              ConsultationParticipant(user_id=users["morgan"].id, meeting_role="professional",
                                                      invite_status="accepted"),
                              ConsultationParticipant(user_id=users["bennett"].id, meeting_role="professional",
                                                      invite_status="accepted")]
            c.documents = [letter, lab]
            db.add(c)
            db.flush()
            for pro in (users["morgan"], users["bennett"]):
                g = ConsentGrant(patient_id=noa.id, grantee_id=pro.id, purpose="International cardiology second opinion",
                                 consultation_id=c.id, starts_at=now, expires_at=now + timedelta(days=14))
                g.documents = [letter, lab]
                db.add(g)
        db.flush()
        for p in (noa, daniel):
            evaluate_patient(db, p.id)
        audit.record(db, "system.seed", detail={"scenario": scenario})
        db.commit()
        counts = {"users": len(users), "organizations": len(orgs),
                  "documents": db.execute(text("SELECT count(*) FROM documents")).scalar()}
    return counts


def reset_and_seed(scenario: str) -> dict:
    with SessionLocal() as db:
        tables = ", ".join(t.name for t in reversed(Base.metadata.sorted_tables))
        db.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        db.commit()
    root = Path(get_settings().storage_dir)
    if root.exists():
        for child in root.iterdir():
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
    from app.security.ratelimit import limiter

    limiter.reset()
    return seed(scenario)


def seed_if_empty(scenario: str = "showcase") -> bool:
    with SessionLocal() as db:
        if db.execute(select(User.id).limit(1)).first():
            return False
    seed(scenario)
    return True


def export_samples(target: str) -> None:
    out = Path(target)
    out.mkdir(parents=True, exist_ok=True)
    for name in SAMPLE_FILES:
        (out / name).write_bytes(sample_bytes(name))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "seed-if-empty"
    arg = sys.argv[2] if len(sys.argv) > 2 else "showcase"
    if cmd == "seed":
        print(seed(arg))
    elif cmd == "reset":
        print(reset_and_seed(arg))
    elif cmd == "seed-if-empty":
        print("seeded" if seed_if_empty(arg) else "database already contains data; skipping seed")
    elif cmd == "export-samples":
        export_samples(arg)
    else:
        raise SystemExit(__doc__)
