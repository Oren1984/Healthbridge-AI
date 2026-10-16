import asyncio
import uuid
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.api.serializers import notification_out
from app.config import get_settings
from app.db import SessionLocal, get_db
from app.deps import SESSION_COOKIE, get_current_user, load_session
from app.models import Notification, NotificationPreference, User, utcnow
from app.services.notifications import KINDS

router = APIRouter(tags=["notifications"])


@router.get("/notifications")
def list_notifications(unread_only: bool = False, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    stmt = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    items = db.execute(stmt.order_by(Notification.created_at.desc()).limit(100)).scalars().all()
    unread = db.execute(select(func.count()).select_from(Notification).where(
        Notification.user_id == user.id, Notification.read_at.is_(None))).scalar()
    return {"items": [notification_out(n) for n in items], "unread": unread,
            "delivery_note": "Notifications are delivered in-app only. No email or SMS is sent."}


@router.post("/notifications/{nid}/read")
def mark_read(nid: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    n = db.get(Notification, nid)
    if not n or n.user_id != user.id:
        raise HTTPException(404, "Not found")
    n.read_at = n.read_at or utcnow()
    db.commit()
    return notification_out(n)


@router.post("/notifications/read-all")
def mark_all_read(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    db.execute(update(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None))
               .values(read_at=utcnow()))
    db.commit()
    return {"ok": True}


@router.get("/notifications/preferences")
def get_prefs(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    prefs = {p.kind: p.enabled for p in db.execute(select(NotificationPreference).where(
        NotificationPreference.user_id == user.id)).scalars()}
    return {k: prefs.get(k, True) for k in KINDS}


@router.put("/notifications/preferences")
def put_prefs(body: dict[str, bool], db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    for kind, enabled in body.items():
        if kind not in KINDS:
            raise HTTPException(422, f"Unknown notification kind: {kind}")
        pref = db.get(NotificationPreference, (user.id, kind))
        if pref:
            pref.enabled = enabled
        else:
            db.add(NotificationPreference(user_id=user.id, kind=kind, enabled=enabled))
    db.commit()
    return get_prefs(db, user)


def _origin_allowed(ws: WebSocket) -> bool:
    origin = ws.headers.get("origin")
    if not origin:
        return False
    host = ws.headers.get("host", "")
    allowed = {o.rstrip("/") for o in get_settings().cors_origins}
    return urlparse(origin).netloc == host or origin.rstrip("/") in allowed


@router.websocket("/ws")
async def notifications_ws(ws: WebSocket):
    """Pushes unread-count changes. Authenticated by session cookie; cross-origin connections refused."""
    if not _origin_allowed(ws):
        await ws.close(code=4403)
        return
    with SessionLocal() as db:
        sess = load_session(db, ws.cookies.get(SESSION_COOKIE))
        user_id = sess.user_id if sess else None
    if not user_id:
        await ws.close(code=4401)
        return
    await ws.accept()
    last = None
    try:
        while True:
            with SessionLocal() as db:
                if not load_session(db, ws.cookies.get(SESSION_COOKIE)):
                    await ws.close(code=4401)
                    return
                unread = db.execute(select(func.count()).select_from(Notification).where(
                    Notification.user_id == user_id, Notification.read_at.is_(None))).scalar()
                newest = db.execute(select(Notification).where(Notification.user_id == user_id)
                                    .order_by(Notification.created_at.desc()).limit(1)).scalars().first()
            state = (unread, newest.id if newest else None)
            if state != last:
                await ws.send_json({"type": "notifications", "unread": unread,
                                    "latest": notification_out(newest) if newest else None})
                last = state
            await asyncio.sleep(4)
    except (WebSocketDisconnect, RuntimeError):
        return
