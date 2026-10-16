import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.api import admin, assistant, auth, care, consultations, documents, journey, notifications, sharing, system
from app.config import get_settings
from app.observability import RequestContextMiddleware, configure_logging, current_request_context, log_event

configure_logging()
log = logging.getLogger("healthbridge")
settings = get_settings()

app = FastAPI(title="HealthBridge AI API", version="1.0.0",
              docs_url="/api/docs" if settings.environment != "production" else None,
              openapi_url="/api/openapi.json" if settings.environment != "production" else None, redoc_url=None)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        h = response.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("Referrer-Policy", "no-referrer")
        h.setdefault("X-Frame-Options", "DENY")
        if not request.url.path.startswith("/api/docs"):
            h.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        h.setdefault("Cache-Control", "no-store")
        return response


app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                   allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
                   allow_headers=["Content-Type", "X-CSRF-Token", "X-Request-ID"])
app.add_middleware(RequestContextMiddleware)


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    # Echo field locations and messages only — never the submitted values.
    errors = [{"loc": [str(p) for p in e.get("loc", [])], "msg": e.get("msg")} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": "Validation failed", "errors": errors})


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log_event(log, "unhandled_error", logging.ERROR, path=request.url.path, error_type=type(exc).__name__)
    log.exception("unhandled exception")
    return JSONResponse(status_code=500, content={"detail": "An unexpected error occurred.",
                                                  "request_id": current_request_context().get("request_id")})


for r in (system, auth, documents, journey, care, sharing, consultations, assistant, notifications, admin):
    app.include_router(r.router, prefix="/api")
