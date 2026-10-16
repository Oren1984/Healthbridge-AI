from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.security.storage import get_storage

router = APIRouter(tags=["system"])

DISCLAIMER = ("HealthBridge AI is a synthetic-data research and engineering demonstration. It is not a clinically "
              "validated medical product and must not be used for real patient care.")


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/ready")
def ready(db: Session = Depends(get_db)):
    checks = {}
    try:
        db.execute(text("SELECT 1"))
        rev = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
        checks["database"] = "ok"
        checks["migration"] = rev
    except Exception:
        checks["database"] = "unavailable"
    checks["storage"] = "ok" if get_storage().writable() else "not_writable"
    ok = checks["database"] == "ok" and checks["storage"] == "ok"
    return JSONResponse(status_code=200 if ok else 503, content={"ready": ok, "checks": checks})


@router.get("/meta")
def meta(db: Session = Depends(get_db)):
    from app.services.llm import get_ai_mode

    s = get_settings()
    return {"name": "HealthBridge AI", "version": "1.0.0", "demo_mode": s.demo_mode, "ai_mode": get_ai_mode(db),
            "livekit_url": s.livekit_public_url, "disclaimer": DISCLAIMER, "recording": "disabled",
            "max_upload_mb": s.max_upload_bytes // (1024 * 1024)}


@router.get("/demo/scenarios")
def scenarios():
    if not get_settings().demo_mode:
        raise HTTPException(404, "Not found")
    from app.services.seed import DEMO_ACCOUNTS, SCENARIOS

    return {"scenarios": SCENARIOS, "accounts": DEMO_ACCOUNTS,
            "note": "All accounts and records are synthetic. Passwords are published only in demo mode."}
