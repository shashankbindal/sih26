from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.deps import get_current_user, require_roles
from app.errors import ApiError, install_error_handlers
from app.models.enums import Bureau, Role
from app.services.auth import create_access_token, hash_password, verify_password
from tests.conftest import PASSWORD, auth_headers, make_user


def test_password_hash_roundtrip():
    h = hash_password(PASSWORD)
    assert h != PASSWORD and verify_password(PASSWORD, h) and not verify_password("nope", h)
    assert verify_password("x", "not-a-hash") is False


def test_login_me_and_bad_credentials(client, db):
    user = make_user(db, Role.PGRC_OFFICER, Bureau.PGRC, email="Pgrc.Officer@demo.loksutra.in")
    r = client.post("/api/v1/auth/login", json={"email": "pgrc.officer@demo.loksutra.in", "password": PASSWORD})
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer" and body["user"]["role"] == "PGRC_OFFICER"
    assert "password_hash" not in body["user"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200 and me.json()["id"] == str(user.id)

    bad = client.post("/api/v1/auth/login", json={"email": user.email, "password": "wrong"})
    assert bad.status_code == 401 and bad.json()["error"]["code"] == "INVALID_CREDENTIALS"
    unknown = client.post("/api/v1/auth/login", json={"email": "nobody@x.in", "password": "x"})
    assert unknown.status_code == 401 and unknown.json() == bad.json()


def test_me_requires_valid_token(client, db):
    assert client.get("/api/v1/auth/me").status_code == 401
    r = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer garbage"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "UNAUTHORIZED"
    user = make_user(db)
    expired = create_access_token(str(user.id), "PGRC_OFFICER", "PGRC", now=datetime.now(UTC) - timedelta(days=2))
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired}"}).status_code == 401


def test_inactive_user_rejected(client, db):
    user = make_user(db)
    h = auth_headers(client, user)
    user.is_active = False
    db.commit()
    assert client.get("/api/v1/auth/me", headers=h).status_code == 401


def test_demo_users_lists_accounts_in_demo_mode(client, db):
    make_user(db, Role.ADMIN, Bureau.ADMIN)
    r = client.get("/api/v1/auth/demo-users")
    assert r.status_code == 200 and r.json()[0].keys() >= {"email", "name", "role", "bureau"}
    assert "password_hash" not in r.text


def test_demo_users_hidden_when_not_demo(client, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "demo_mode", False)
    assert client.get("/api/v1/auth/demo-users").status_code == 404


def _mini_app() -> FastAPI:
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/admin-only")
    def admin_only(_u=Depends(require_roles(Role.ADMIN))):
        return {"ok": True}

    @app.get("/boom")
    def boom():
        raise RuntimeError("secret internal text")

    @app.get("/conflict")
    def conflict():
        raise ApiError(409, "CONFLICT", "Already decided", {"link_id": "x"})

    @app.get("/typed")
    def typed(n: int):
        return {"n": n}

    @app.get("/me")
    def me(_u=Depends(get_current_user)):
        return {}

    return app


def test_role_guard(db):
    client = TestClient(_mini_app())
    admin = make_user(db, Role.ADMIN, Bureau.ADMIN)
    officer = make_user(db, Role.PGRC_OFFICER, Bureau.PGRC)

    def tok(u):
        return {"Authorization": f"Bearer {create_access_token(str(u.id), u.role.value, u.bureau.value)}"}

    assert client.get("/admin-only", headers=tok(admin)).json() == {"ok": True}
    r = client.get("/admin-only", headers=tok(officer))
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "FORBIDDEN"
    assert r.json()["error"]["details"]["required_roles"] == ["ADMIN"]
    assert client.get("/admin-only").status_code == 401


def test_error_envelope_shapes():
    client = TestClient(_mini_app(), raise_server_exceptions=False)

    def assert_envelope(resp, status, code):
        assert resp.status_code == status
        err = resp.json()["error"]
        assert set(err) == {"code", "message", "details"}
        assert err["code"] == code and isinstance(err["message"], str) and isinstance(err["details"], dict)
        return err

    assert_envelope(client.get("/nope"), 404, "NOT_FOUND")
    assert_envelope(client.post("/conflict"), 405, "METHOD_NOT_ALLOWED")
    err = assert_envelope(client.get("/conflict"), 409, "CONFLICT")
    assert err["details"] == {"link_id": "x"}
    err = assert_envelope(client.get("/typed?n=abc"), 422, "VALIDATION_ERROR")
    assert err["details"]["errors"][0]["loc"] == ["query", "n"]
    err = assert_envelope(client.get("/boom"), 500, "INTERNAL_ERROR")
    assert "secret" not in str(err)


def test_real_app_404_and_request_id(client):
    r = client.get("/api/v1/cases/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 401
    assert r.headers["X-Request-ID"]
    r = client.get("/api/v1/health", headers={"X-Request-ID": "abc123"})
    assert r.headers["X-Request-ID"] == "abc123"
