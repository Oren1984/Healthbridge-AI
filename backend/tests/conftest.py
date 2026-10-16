"""Test fixtures. Integration tests run against a dedicated PostgreSQL+pgvector database
(`healthbridge_test`), never the development database. Data is reseeded per test module."""
import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

os.environ.setdefault("HB_ENVIRONMENT", "test")
os.environ.setdefault("HB_STORAGE_DIR", "/tmp/hb-test-docs")
os.environ["HB_AI_MODE"] = "mock"
os.environ["HB_EMBEDDING_PROVIDER"] = "hash"

DB_URL = os.environ.get("HB_DATABASE_URL", "")
assert "healthbridge_test" in DB_URL, "Refusing to run tests against a non-test database"


def _ensure_database() -> None:
    url = make_url(DB_URL)
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        if not c.execute(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": url.database}).first():
            c.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin.dispose()


_ensure_database()

from app.db import Base, engine  # noqa: E402
from app.models import User  # noqa: E402

with engine.begin() as conn:
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
Base.metadata.drop_all(engine)
Base.metadata.create_all(engine)
with engine.begin() as conn:  # /ready reads the migration version
    conn.execute(text("CREATE TABLE IF NOT EXISTS alembic_version (version_num varchar(32) PRIMARY KEY)"))
    conn.execute(text("INSERT INTO alembic_version VALUES ('test') ON CONFLICT DO NOTHING"))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.security.ratelimit import limiter  # noqa: E402
from app.seed_data import PASSWORD  # noqa: E402
from app.services.seed import reset_and_seed  # noqa: E402

EMAILS = {
    "noa": "noa@patient.healthbridge.test", "daniel": "daniel@patient.healthbridge.test",
    "ronen": "dr.ronen@pro.healthbridge.test", "haddad": "dr.haddad@pro.healthbridge.test",
    "morgan": "dr.morgan@pro.healthbridge.test", "bennett": "dr.bennett@pro.healthbridge.test",
    "shah": "dr.shah@pro.healthbridge.test", "admin": "admin@healthbridge.test",
}


@pytest.fixture(scope="module")
def seeded():
    """Fresh scenario by default; modules can parametrize via `scenario` attribute."""
    reset_and_seed("fresh")
    yield


@pytest.fixture(scope="module")
def showcase():
    reset_and_seed("showcase")
    yield


@pytest.fixture(autouse=True)
def _reset_limits():
    limiter.reset()
    yield


class Api:
    """A logged-in browser-like session (cookie + CSRF header)."""

    def __init__(self, who: str | None = None):
        self.client = TestClient(app, base_url="http://testserver")
        self.user = None
        if who:
            r = self.client.post("/api/auth/login", json={"email": EMAILS[who], "password": PASSWORD})
            assert r.status_code == 200, r.text
            self.user = r.json()["user"]
            self.client.headers["X-CSRF-Token"] = r.json()["csrf_token"]

    @property
    def id(self) -> str:
        return self.user["id"]

    def __getattr__(self, name):
        return getattr(self.client, name)


@pytest.fixture
def api():
    return Api


def user_id(email_key: str) -> uuid.UUID:
    from app.db import SessionLocal

    with SessionLocal() as db:
        return db.query(User).filter(User.email == EMAILS[email_key]).one().id


def run_worker() -> int:
    from app.db import SessionLocal
    from app.services.documents import process_pending

    return process_pending(SessionLocal, limit=20)
