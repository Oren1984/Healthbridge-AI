import secrets
from datetime import timedelta
from zoneinfo import available_timezones

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.api.serializers import user_out
from app.config import get_settings
from app.db import get_db
from app.deps import SESSION_COOKIE, get_current_user, hash_token, load_session
from app.models import AuthSession, PatientProfile, User, utcnow
from app.security.passwords import hash_password, validate_password_strength, verify_password
from app.security.ratelimit import limiter

router = APIRouter(prefix="/auth", tags=["auth"])
GENERIC_LOGIN_ERROR = "Invalid email or password."
LOCK_AFTER = 5
LOCK_MINUTES = 5
_TIMEZONES = available_timezones()


EMAIL_PATTERN = r"^[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,24}$"


class LoginIn(BaseModel):
    email: str = Field(pattern=EMAIL_PATTERN, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class RegisterIn(BaseModel):
    email: str = Field(pattern=EMAIL_PATTERN, max_length=254)
    password: str = Field(min_length=1, max_length=128)
    full_name: str = Field(min_length=2, max_length=200)
    locale: str = Field(default="en", pattern="^(en|he)$")


class ProfileIn(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=200)
    locale: str | None = Field(default=None, pattern="^(en|he)$")
    timezone: str | None = Field(default=None, max_length=64)
    default_share_days: int | None = Field(default=None, ge=1, le=365)
    show_access_alerts: bool | None = None


class PasswordIn(BaseModel):
    current_password: str = Field(max_length=128)
    new_password: str = Field(max_length=128)


def _start_session(db: Session, user: User, request: Request, response: Response) -> str:
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    s = get_settings()
    db.add(AuthSession(token_hash=hash_token(token), user_id=user.id, csrf_token=csrf,
                       expires_at=utcnow() + timedelta(minutes=s.session_ttl_minutes),
                       user_agent=(request.headers.get("user-agent") or "")[:200]))
    response.set_cookie(SESSION_COOKIE, token, httponly=True, secure=s.cookie_secure, samesite="lax",
                        max_age=s.session_ttl_minutes * 60, path="/")
    return csrf


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else "unknown"
    email = body.email.lower()
    if not limiter.hit(f"login-ip:{ip}", 30, 300) or not limiter.hit(f"login-email:{email}", 10, 300):
        audit.record(db, "auth.login", outcome="denied", detail={"reason": "rate_limited"}, commit=True)
        raise HTTPException(429, "Too many attempts. Please wait a few minutes and try again.")
    user = db.execute(select(User).where(User.email == email)).scalars().first()
    now = utcnow()
    if user and user.locked_until and user.locked_until > now:
        verify_password(None, body.password)  # equalise timing
        audit.record(db, "auth.login", actor=user, outcome="denied", detail={"reason": "locked"}, commit=True)
        raise HTTPException(401, GENERIC_LOGIN_ERROR)
    if not user or not verify_password(user.password_hash, body.password) or not user.is_active:
        if user:
            user.failed_logins += 1
            if user.failed_logins >= LOCK_AFTER:
                user.locked_until = now + timedelta(minutes=LOCK_MINUTES)
                user.failed_logins = 0
        audit.record(db, "auth.login", actor=user, outcome="denied", detail={"reason": "bad_credentials"}, commit=True)
        raise HTTPException(401, GENERIC_LOGIN_ERROR)
    user.failed_logins = 0
    user.locked_until = None
    user.last_login_at = now
    csrf = _start_session(db, user, request, response)
    audit.record(db, "auth.login", actor=user)
    db.commit()
    return {"user": user_out(user), "csrf_token": csrf}


@router.post("/register", status_code=201)
def register(body: RegisterIn, request: Request, response: Response, db: Session = Depends(get_db)):
    if not get_settings().demo_mode:
        raise HTTPException(403, "Self-registration is disabled.")
    ip = request.client.host if request.client else "unknown"
    if not limiter.hit(f"register:{ip}", 5, 3600):
        raise HTTPException(429, "Too many registrations from this address.")
    if err := validate_password_strength(body.password):
        raise HTTPException(422, err)
    email = body.email.lower()
    if db.execute(select(User.id).where(User.email == email)).first():
        raise HTTPException(409, "An account with this email already exists.")
    user = User(email=email, password_hash=hash_password(body.password), full_name=body.full_name.strip(),
                role="patient", locale=body.locale, timezone="Asia/Jerusalem", country="IL")
    db.add(user)
    db.flush()
    db.add(PatientProfile(user_id=user.id))
    csrf = _start_session(db, user, request, response)
    audit.record(db, "auth.register", actor=user, resource_type="user", resource_id=user.id)
    db.commit()
    db.refresh(user)
    return {"user": user_out(user), "csrf_token": csrf}


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db),
           user: User = Depends(get_current_user)):
    sess = request.state.session
    sess.revoked_at = utcnow()
    audit.record(db, "auth.logout", actor=user)
    db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(request: Request, db: Session = Depends(get_db)):
    sess = load_session(db, request.cookies.get(SESSION_COOKIE))
    if not sess:
        raise HTTPException(401, "Not authenticated")
    user = db.get(User, sess.user_id)
    if not user or not user.is_active:
        raise HTTPException(401, "Not authenticated")
    return {"user": user_out(user), "csrf_token": sess.csrf_token}


@router.patch("/me")
def update_me(body: ProfileIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if body.timezone is not None and body.timezone not in _TIMEZONES:
        raise HTTPException(422, "Unknown timezone.")
    for field in ("full_name", "locale", "timezone"):
        val = getattr(body, field)
        if val is not None:
            setattr(user, field, val)
    if user.patient:
        if body.default_share_days is not None:
            user.patient.default_share_days = body.default_share_days
        if body.show_access_alerts is not None:
            user.patient.show_access_alerts = body.show_access_alerts
    audit.record(db, "account.update", actor=user, resource_type="user", resource_id=user.id,
                 detail={"fields": [k for k, v in body.model_dump().items() if v is not None]})
    db.commit()
    return {"user": user_out(user)}


@router.post("/change-password")
def change_password(body: PasswordIn, request: Request, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    if not limiter.hit(f"pwchange:{user.id}", 5, 900):
        raise HTTPException(429, "Too many attempts.")
    if not verify_password(user.password_hash, body.current_password):
        audit.record(db, "account.password_change", actor=user, outcome="denied", commit=True)
        raise HTTPException(400, "Current password is incorrect.")
    if err := validate_password_strength(body.new_password):
        raise HTTPException(422, err)
    user.password_hash = hash_password(body.new_password)
    # Revoke all other sessions.
    current = request.state.session.token_hash
    for s in db.execute(select(AuthSession).where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))).scalars():
        if s.token_hash != current:
            s.revoked_at = utcnow()
    audit.record(db, "account.password_change", actor=user)
    db.commit()
    return {"ok": True}
