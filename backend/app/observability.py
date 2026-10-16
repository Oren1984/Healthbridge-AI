"""Structured logging, request correlation IDs and lightweight in-process metrics."""
import contextvars
import json
import logging
import re
import sys
import threading
import time
import uuid
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

_ctx: contextvars.ContextVar[dict] = contextvars.ContextVar("request_ctx", default={})


def current_request_context() -> dict:
    return _ctx.get()


# Keys whose values are never logged; patterns redacted from free text.
_SENSITIVE_KEYS = {"password", "token", "access_token", "csrf", "cookie", "authorization", "secret",
                   "content", "text", "extracted_text", "message", "body"}
_REDACT_PATTERNS = [
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]+"), r"\1[REDACTED]"),
    (re.compile(r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+"), "[REDACTED_JWT]"),
    (re.compile(r"(?i)(hb_session=)[^;\s]+"), r"\1[REDACTED]"),
]


def redact(value):
    if isinstance(value, dict):
        return {k: ("[REDACTED]" if k.lower() in _SENSITIVE_KEYS else redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        for pat, repl in _REDACT_PATTERNS:
            value = pat.sub(repl, value)
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": redact(record.getMessage()),
        }
        ctx = _ctx.get()
        if ctx.get("request_id"):
            payload["request_id"] = ctx["request_id"]
        extra = getattr(record, "fields", None)
        if extra:
            payload.update(redact(extra))
        if record.exc_info:
            payload["exc_type"] = record.exc_info[0].__name__ if record.exc_info[0] else None
            payload["exc"] = redact(self.formatException(record.exc_info))[-2000:]
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    for noisy in ("uvicorn.access",):
        logging.getLogger(noisy).disabled = True


def log_event(logger: logging.Logger, msg: str, level: int = logging.INFO, **fields) -> None:
    logger.log(level, msg, extra={"fields": fields})


class Metrics:
    """Per-route request counts, error counts and latency (in-process, resets on restart)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.started = time.time()
        self.routes: dict[str, dict] = defaultdict(lambda: {"count": 0, "errors": 0, "total_ms": 0.0, "max_ms": 0.0})
        self.counters: dict[str, int] = defaultdict(int)

    def observe(self, route: str, status: int, ms: float) -> None:
        with self._lock:
            r = self.routes[route]
            r["count"] += 1
            r["total_ms"] += ms
            r["max_ms"] = max(r["max_ms"], ms)
            if status >= 500:
                r["errors"] += 1

    def incr(self, name: str, n: int = 1) -> None:
        with self._lock:
            self.counters[name] += n

    def snapshot(self) -> dict:
        with self._lock:
            routes = {
                k: {"count": v["count"], "errors": v["errors"], "avg_ms": round(v["total_ms"] / v["count"], 1),
                    "max_ms": round(v["max_ms"], 1)}
                for k, v in sorted(self.routes.items()) if v["count"]
            }
            return {"uptime_seconds": int(time.time() - self.started), "routes": routes,
                    "counters": dict(self.counters)}


metrics = Metrics()
_access_log = logging.getLogger("healthbridge.access")


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        incoming = request.headers.get("x-request-id", "")
        request_id = incoming if re.fullmatch(r"[A-Za-z0-9\-]{8,64}", incoming) else uuid.uuid4().hex
        ip = request.client.host if request.client else None
        token = _ctx.set({"request_id": request_id, "ip": ip})
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            ms = (time.perf_counter() - start) * 1000
            route = request.scope.get("route")
            route_path = getattr(route, "path", "unmatched")
            metrics.observe(f"{request.method} {route_path}", status, ms)
            log_event(_access_log, "request", method=request.method, route=route_path, status=status,
                      duration_ms=round(ms, 1))
            _ctx.reset(token)
