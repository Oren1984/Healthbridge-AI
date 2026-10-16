from app.seed_data import PASSWORD
from tests.conftest import EMAILS, Api


def test_health_and_ready(seeded):
    c = Api()
    assert c.get("/api/health").json() == {"status": "ok"}
    r = c.get("/api/ready")
    assert r.status_code == 200 and r.json()["checks"]["database"] == "ok"
    assert r.headers["x-request-id"]
    assert r.headers["x-content-type-options"] == "nosniff"


def test_login_success_sets_httponly_cookie(seeded):
    c = Api()
    r = c.post("/api/auth/login", json={"email": EMAILS["noa"], "password": PASSWORD})
    assert r.status_code == 200
    cookie = r.headers["set-cookie"]
    assert "hb_session=" in cookie and "HttpOnly" in cookie and "SameSite=lax" in cookie
    assert "password_hash" not in r.text
    assert r.json()["user"]["role"] == "patient"


def test_login_errors_are_generic(seeded):
    c = Api()
    unknown = c.post("/api/auth/login", json={"email": "nobody@x.test", "password": "whatever"})
    wrong = c.post("/api/auth/login", json={"email": EMAILS["noa"], "password": "wrong-password"})
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["detail"] == wrong.json()["detail"] == "Invalid email or password."


def test_account_lockout_after_repeated_failures(seeded):
    c = Api()
    for _ in range(5):
        c.post("/api/auth/login", json={"email": EMAILS["daniel"], "password": "wrong-password"})
    r = c.post("/api/auth/login", json={"email": EMAILS["daniel"], "password": PASSWORD})
    assert r.status_code == 401  # locked even with the right password
    from app.db import SessionLocal
    from app.models import User

    with SessionLocal() as db:  # unlock for other tests
        u = db.query(User).filter(User.email == EMAILS["daniel"]).one()
        u.locked_until = None
        db.commit()


def test_rate_limit_on_login(seeded):
    c = Api()
    codes = [c.post("/api/auth/login", json={"email": "spray@x.test", "password": "x"}).status_code for _ in range(12)]
    assert 429 in codes


def test_csrf_required_for_state_changes(seeded):
    a = Api("noa")
    token = a.client.headers.pop("X-CSRF-Token")
    r = a.patch("/api/auth/me", json={"locale": "he"})
    assert r.status_code == 403 and "CSRF" in r.json()["detail"]
    r = a.patch("/api/auth/me", json={"locale": "he"}, headers={"X-CSRF-Token": "forged"})
    assert r.status_code == 403
    r = a.patch("/api/auth/me", json={"locale": "he"}, headers={"X-CSRF-Token": token})
    assert r.status_code == 200 and r.json()["user"]["locale"] == "he"
    a.patch("/api/auth/me", json={"locale": "en"}, headers={"X-CSRF-Token": token})


def test_unauthenticated_requests_rejected(seeded):
    c = Api()
    for path in ("/api/auth/me", "/api/consultations", "/api/notifications", "/api/admin/users"):
        assert c.get(path).status_code == 401


def test_logout_invalidates_session(seeded):
    a = Api("noa")
    assert a.post("/api/auth/logout").status_code == 200
    assert a.get("/api/auth/me").status_code == 401


def test_validation_errors_do_not_echo_input(seeded):
    a = Api("noa")
    r = a.patch("/api/auth/me", json={"timezone": "Not/A_Zone<script>"})
    assert r.status_code == 422 and "<script>" not in r.text


def test_register_and_password_policy(seeded):
    c = Api()
    weak = c.post("/api/auth/register", json={"email": "new@patient.healthbridge.test", "password": "weak", "full_name": "New"})
    assert weak.status_code == 422
    ok = c.post("/api/auth/register", json={"email": "new@patient.healthbridge.test", "password": "Strong-Passw0rd",
                                            "full_name": "New Patient"})
    assert ok.status_code == 201 and ok.json()["user"]["role"] == "patient"
    dup = Api().post("/api/auth/register", json={"email": "new@patient.healthbridge.test", "password": "Strong-Passw0rd",
                                                 "full_name": "Again"})
    assert dup.status_code == 409


def test_change_password_revokes_other_sessions(seeded):
    a, b = Api("haddad"), Api("haddad")
    r = a.post("/api/auth/change-password", json={"current_password": PASSWORD, "new_password": "Another-Passw0rd"})
    assert r.status_code == 200
    assert b.get("/api/auth/me").status_code == 401 and a.get("/api/auth/me").status_code == 200
    a.post("/api/auth/change-password", json={"current_password": "Another-Passw0rd", "new_password": PASSWORD})
