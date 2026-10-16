"""In-app notifications. No external email/SMS delivery exists in this system."""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Notification, NotificationPreference

KINDS = ["appointment_reminder", "followup_pending", "sharing_invitation", "access_expiring",
         "consultation_update", "document_processed", "care_gap_clarification", "handoff"]


def is_enabled(db: Session, user_id: uuid.UUID, kind: str) -> bool:
    pref = db.get(NotificationPreference, (user_id, kind))
    return pref.enabled if pref else True


def notify(db: Session, user_id: uuid.UUID, kind: str, title: str, body: str | None = None,
           link: str | None = None, dedupe_key: str | None = None) -> Notification | None:
    if not is_enabled(db, user_id, kind):
        return None
    if dedupe_key and db.execute(select(Notification.id).where(
            Notification.user_id == user_id, Notification.dedupe_key == dedupe_key)).first():
        return None
    n = Notification(user_id=user_id, kind=kind, title=title[:300], body=body, link=link, dedupe_key=dedupe_key)
    db.add(n)
    db.flush()
    return n
