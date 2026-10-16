"""Lightweight background worker: a single polling loop, no broker.

Jobs
- documents: process pending uploads (FOR UPDATE SKIP LOCKED, so several workers are safe)
- reminders: appointment reminders, due follow-ups, expiring/expired access notices
- care_gaps: periodic re-evaluation (findings depend on the current date)
"""
import logging
import signal
import time
from datetime import timedelta

from sqlalchemy import select

from app.db import SessionLocal
from app.models import ConsentGrant, Consultation, FollowUpTask, JobRun, User, utcnow
from app.observability import configure_logging, log_event
from app.services.care_gaps import evaluate_patient
from app.services.documents import process_pending
from app.services.notifications import notify

configure_logging()
log = logging.getLogger("healthbridge.worker")
_running = True


def _stop(*_):
    global _running
    _running = False


def run_job(name: str, fn) -> None:
    with SessionLocal() as db:
        job = db.get(JobRun, name) or JobRun(job_name=name, runs=0, items_processed=0)
        job.last_started_at = utcnow()
        db.merge(job)
        db.commit()
    status, error, items = "ok", None, 0
    try:
        items = fn() or 0
    except Exception as exc:  # recorded, never crashes the loop
        status, error = "error", type(exc).__name__
        log_event(log, "job.failed", logging.ERROR, job=name, error_type=error)
    with SessionLocal() as db:
        job = db.get(JobRun, name)
        job.last_finished_at, job.last_status, job.last_error = utcnow(), status, error
        job.runs += 1
        job.items_processed += items
        db.commit()


def reminders() -> int:
    now = utcnow()
    count = 0
    with SessionLocal() as db:
        for c in db.execute(select(Consultation).where(Consultation.status == "scheduled", Consultation.reminder_sent.is_(False),
                                                       Consultation.scheduled_start <= now + timedelta(hours=24),
                                                       Consultation.scheduled_start > now)).scalars():
            for p in c.participants:
                if p.invite_status != "declined":
                    notify(db, p.user_id, "appointment_reminder", f"Upcoming consultation: {c.title}",
                           c.scheduled_start.isoformat(), f"/app/consultations/{c.id}",
                           dedupe_key=f"remind:{c.id}:{c.scheduled_start.isoformat()}")
                    count += 1
            c.reminder_sent = True
        for t in db.execute(select(FollowUpTask).where(FollowUpTask.status == "open", FollowUpTask.due_date.is_not(None))).scalars():
            lead = t.reminder_days_before if t.reminder_days_before is not None else 3
            if t.due_date - timedelta(days=lead) <= now.date():
                if notify(db, t.owner_id or t.patient_id, "followup_pending", f"Follow-up due {t.due_date.isoformat()}: {t.title[:200]}",
                          None, "/app/tasks", dedupe_key=f"due:{t.id}:{t.due_date.isoformat()}"):
                    count += 1
        for g in db.execute(select(ConsentGrant).where(ConsentGrant.revoked_at.is_(None), ConsentGrant.expiry_notified.is_(False),
                                                       ConsentGrant.expires_at <= now + timedelta(days=2))).scalars():
            grantee = db.get(User, g.grantee_id)
            expired = g.expires_at <= now
            verb = "ended" if expired else "ends soon"
            notify(db, g.patient_id, "access_expiring", f"Sharing with {grantee.full_name} {verb}",
                   g.expires_at.isoformat(), "/app/sharing", dedupe_key=f"exp:{g.id}")
            notify(db, g.grantee_id, "access_expiring", f"Your access to shared records {verb}",
                   g.expires_at.isoformat(), "/app/pro", dedupe_key=f"exp:{g.id}")
            g.expiry_notified = True
            count += 2
        db.commit()
    return count


def reevaluate_gaps() -> int:
    with SessionLocal() as db:
        ids = list(db.execute(select(User.id).where(User.role == "patient", User.is_active.is_(True))).scalars())
    for pid in ids:
        with SessionLocal() as db:
            evaluate_patient(db, pid)
            db.commit()
    return len(ids)


def main() -> None:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    from app.config import get_settings

    poll = get_settings().worker_poll_seconds
    log_event(log, "worker.started", poll_seconds=poll)
    last_reminders = last_gaps = 0.0
    while _running:
        run_job("documents", lambda: process_pending(SessionLocal))
        if time.monotonic() - last_reminders > 60:
            run_job("reminders", reminders)
            last_reminders = time.monotonic()
        if time.monotonic() - last_gaps > 900:
            run_job("care_gaps", reevaluate_gaps)
            last_gaps = time.monotonic()
        time.sleep(poll)
    log_event(log, "worker.stopped")


if __name__ == "__main__":
    main()
