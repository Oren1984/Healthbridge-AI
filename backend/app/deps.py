"""Request dependencies: session authentication, CSRF enforcement, role checks."""
import hashlib
import hmac
from datetime import timedelta

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AuthSession, User, utcnow

SESSION_COOKIE = "hb_session"
CSRF_COOKIE = "hb_csrf"
CSRF_HEADER = "x-csrf-token"
_UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def load_session(db: Session, token: str | None) -> AuthSession | None:
    if not token or len(token) > 200:
        return None
    sess = db.get(AuthSession, hash_token(token))
    now = utcnow()
    if not sess or sess.revoked_at or sess.expires_at <= now:
        return None
    if now - sess.last_seen_at > timedelta(minutes=1):
        sess.last_seen_at = now
        db.commit()
    return sess


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    sess = load_session(db, request.cookies.get(SESSION_COOKIE))
    if not sess:
        raise HTTPException(401, "Not authenticated")
    if request.method in _UNSAFE:
        header = request.headers.get(CSRF_HEADER, "")
        if not header or not hmac.compare_digest(header, sess.csrf_token):
            raise HTTPException(403, "CSRF validation failed")
    user = db.get(User, sess.user_id)
    if not user or not user.is_active:
        raise HTTPException(401, "Not authenticated")
    request.state.user = user
    request.state.session = sess
    return user


def require_role(*roles: str):
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(403, "Not permitted for this role")
        return user

    return checker


require_patient = require_role("patient")
require_professional = require_role("professional")
require_admin = require_role("admin")
require_clinical = require_role("patient", "professional")
