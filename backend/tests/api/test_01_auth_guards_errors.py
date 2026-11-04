"""Auth, role guards on every router, and the error envelope (the API specification: {"error": {code, message, details}})."""

from __future__ import annotations

import re
import uuid

import httpx
import pytest

from tests.api.helpers import API, BASE, Api, case_payload, find_institution, timeline

PUBLIC = {("GET", "/api/v1/health"), ("POST", "/api/v1/auth/login"), ("GET", "/api/v1/auth/demo-users")}
ZERO = str(uuid.uuid4())


def _all_operations() -> list[tuple[str, str]]:
    spec = httpx.get(BASE + "/openapi.json", timeout=30).json()
    ops = []
    for path, item in spec["paths"].items():
        for method in item:
            if method.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"} and (method.upper(), path) not in PUBLIC:
                ops.append((method.upper(), path))
    return ops


def _fill(path: str) -> str:
    return re.sub(r"\{[^}]+\}", ZERO, path).removeprefix("/api/v1")


def test_login_ok_and_me(u):
    r = u["pgrc.officer"].get("/auth/me")
    assert r.status_code == 200
    me = r.json()
    assert me["email"] == "pgrc.officer@demo.loksutra.in" and me["bureau"] == "PGRC"
    assert "password" not in str(me).lower()


def test_login_bad_password_is_401_envelope():
    r = httpx.post(API + "/auth/login", json={"email": "pgrc.officer@demo.loksutra.in", "password": "nope-nope"})
    assert r.status_code == 401
    assert set(r.json()["error"]) >= {"code", "message", "details"}


def test_demo_users_listed_without_auth():
    r = httpx.get(API + "/auth/demo-users")
    assert r.status_code == 200
    users = r.json()
    users = users["items"] if isinstance(users, dict) else users
    assert len(users) >= 11
    assert all("password" not in x and "password_hash" not in x for x in users)


def test_every_protected_operation_requires_token(anon: Api):
    ops = _all_operations()
    assert len(ops) > 60
    bad = []
    for method, path in ops:
        r = anon.req(method, _fill(path), json={} if method != "GET" else None)
        if r.status_code != 401:
            bad.append((method, path, r.status_code))
    assert not bad, f"endpoints reachable without a token: {bad}"


def test_garbage_token_rejected():
    for tok in ["abc.def.ghi", "x", "Bearer"]:
        c = Api(None)
        c.c.headers["Authorization"] = f"Bearer {tok}"
        r = c.get("/cases")
        assert r.status_code == 401, (tok, r.status_code)
        assert r.json()["error"]["code"]


# ------------------------------------------------------------------ role guards
ADMIN_ONLY_GET = ["/admin/users", "/admin/demo-tools", "/admin/config/lead_bureau_rules"]
ADMIN_ONLY_POST = [("/admin/sweep", {}), ("/admin/tamper-demo", {"case_id": ZERO})]
NON_ADMIN = ["pgrc.officer", "pgrc.head", "rb.officer", "approval.officer", "vigilance.officer", "ro.kanpur", "mgmt"]


@pytest.mark.parametrize("who", NON_ADMIN)
def test_admin_endpoints_forbidden_for_non_admin(u, who):
    for path in ADMIN_ONLY_GET:
        assert u[who].get(path).status_code == 403, (who, path)
    for path, body in ADMIN_ONLY_POST:
        assert u[who].post(path, json=body).status_code == 403, (who, path)
    assert u[who].put("/admin/config/thresholds", json={"value": {}}).status_code == 403
    assert u[who].post("/admin/reset-demo").status_code == 403


def test_admin_can_read_admin_endpoints(u):
    for path in ADMIN_ONLY_GET:
        assert u["admin"].get(path).status_code == 200, path


@pytest.mark.parametrize("who", ["mgmt", "vigilance.officer", "ro.kanpur", "pgrc.officer"])
def test_pre_action_check_roles(u, who):
    """the API specification: Pre-Action Check = APPROVAL_OFFICER, RB_OFFICER, BUREAU_HEAD, ADMIN."""
    inst = find_institution(u["admin"], "1-4463974255")
    r = u[who].post(f"/institutions/{inst['id']}/pre-action-check", json={"action_type": "ISSUE_NOC"})
    assert r.status_code == 403, (who, r.status_code)


def test_senior_mgmt_cannot_create_case_or_import(u):
    r = u["mgmt"].post("/cases", json=case_payload("A", tag="mgmt"))
    assert r.status_code == 403
    assert u["mgmt"].get("/imports/template.csv").status_code == 403


def test_non_owner_bureau_cannot_write_case(u):
    inst = find_institution(u["admin"], "1-4463974255")
    rb_case = next(c for c in timeline(u["admin"], inst["id"]) if c["owner_bureau"] == "RB" and c["status"] != "DISPOSED")
    cid = rb_case["id"]
    for who in ["pgrc.officer", "approval.officer", "vigilance.officer", "pgrc.head"]:
        assert u[who].post(f"/cases/{cid}/remarks", json={"remark": "qa non-owner probe"}).status_code == 403, who
        assert u[who].post(f"/cases/{cid}/dispose", json={"remark": "qa non-owner probe"}).status_code == 403, who
        r = u[who].post(f"/cases/{cid}/transfer", json={"to_bureau": "PGRC", "remark": "qa non-owner probe"})
        assert r.status_code == 403, who
        assert u[who].patch(f"/cases/{cid}", json={"pending_action": "qa probe"}).status_code == 403, who


def test_clearance_respond_only_by_target_bureau(u):
    """A clearance addressed to VIGILANCE cannot be answered by other bureaus."""
    inst = find_institution(u["admin"], "1-4471203398")
    a = u["approval.officer"].post(f"/institutions/{inst['id']}/pre-action-check", json={"action_type": "ISSUE_NOC"}).json()
    body = {"target_bureau": "VIGILANCE", "remark": "qa guard test"}
    cl = u["approval.officer"].post(f"/institution-actions/{a['institution_action_id']}/clearances", json=body)
    assert cl.status_code == 201, cl.text
    cid = cl.json()["id"]
    for who in ["pgrc.officer", "approval.officer", "rb.officer", "ro.chandigarh", "mgmt"]:
        r = u[who].post(f"/clearances/{cid}/respond", json={"response": "CLEARED", "remarks": "should not be allowed"})
        assert r.status_code == 403, (who, r.status_code, r.text)
    ok = u["vigilance.officer"].post(f"/clearances/{cid}/respond", json={"response": "CLEARED", "remarks": "qa vigilance ok"})
    assert ok.status_code == 200, ok.text


# ------------------------------------------------------------------ error envelope
def _assert_envelope(r, status, code=None):
    assert r.status_code == status, (r.status_code, r.text[:300])
    body = r.json()
    assert set(body) == {"error"}, body
    assert set(body["error"]) >= {"code", "message", "details"}, body
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]
    if code:
        assert body["error"]["code"] == code, body


def test_envelope_401(anon):
    _assert_envelope(anon.get("/cases"), 401)


def test_envelope_403(u):
    _assert_envelope(u["pgrc.officer"].get("/admin/users"), 403, "FORBIDDEN")


def test_envelope_404(u):
    p = u["pgrc.officer"]
    _assert_envelope(p.get(f"/cases/{ZERO}"), 404, "NOT_FOUND")
    _assert_envelope(p.get(f"/institutions/{ZERO}"), 404, "NOT_FOUND")
    _assert_envelope(p.get(f"/links/{ZERO}"), 404, "NOT_FOUND")
    _assert_envelope(p.get(f"/institution-actions/{ZERO}"), 404, "NOT_FOUND")


def test_envelope_404_unknown_route(u):
    r = u["pgrc.officer"].get("/no-such-route")
    assert r.status_code == 404
    assert "error" in r.json(), r.text


def test_envelope_422_validation(u):
    p = u["pgrc.officer"]
    _assert_envelope(p.post("/cases", json={"subject": "x"}), 422, "VALIDATION_ERROR")
    _assert_envelope(p.get("/cases", params={"page": "abc"}), 422, "VALIDATION_ERROR")
    _assert_envelope(p.get("/cases/not-a-uuid"), 422, "VALIDATION_ERROR")
    _assert_envelope(p.post("/intake/classify", json={"subject": ["not", "a", "string"]}), 422)


def test_envelope_422_bad_enum_and_json(u):
    p = u["pgrc.officer"]
    bad = case_payload("A", tag="enum")
    bad["source_channel"] = "CARRIER_PIGEON"
    _assert_envelope(p.post("/cases", json=bad), 422)
    r = p.post("/cases", content=b"{not json", headers={"Content-Type": "application/json"})
    assert r.status_code == 422 and "error" in r.json()


def test_login_validation_envelope():
    r = httpx.post(API + "/auth/login", json={"email": "not-an-email"})
    assert r.status_code in (401, 422) and "error" in r.json()


def test_no_stack_trace_or_sql_in_errors(u):
    p = u["pgrc.officer"]
    assert p.get("/cases", params={"q": "'; drop table cases;--"}).status_code == 200
    assert p.get("/search", params={"q": "%' OR 1=1 --"}).status_code == 200
    for bad in [p.get(f"/cases/{ZERO}"), p.get("/cases/xyz")]:
        t = bad.text.lower()
        assert "traceback" not in t and "sqlalchemy" not in t and "psycopg" not in t
