from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import httpx

BASE = os.environ.get("QA_API_URL", "http://127.0.0.1:8000").rstrip("/")
API = BASE + "/api/v1"
DB_URL = os.environ.get("QA_DB_URL", "postgresql://postgres:postgres@127.0.0.1:5432/loksutra")

PASSWORD = "Demo@2026"
USERS = [
    "pgrc.officer", "pgrc.head", "rb.officer", "rb.head", "approval.officer", "vigilance.officer",
    "ro.kanpur", "ro.bhopal", "ro.chandigarh", "mgmt", "admin",
]
SEED_DIR = Path(__file__).resolve().parents[2] / "app" / "seed" / "data"
DEMO_INPUTS = json.loads((SEED_DIR / "demo_inputs.json").read_text(encoding="utf-8"))


class Api:
    """Thin httpx wrapper with a bearer token and per-call latency capture."""

    def __init__(self, token: str | None, name: str = "anon") -> None:
        self.name = name
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        self.c = httpx.Client(base_url=API, headers=headers, timeout=120)
        self.last_ms = 0.0

    def req(self, method: str, path: str, **kw: Any) -> httpx.Response:
        t = time.perf_counter()
        r = self.c.request(method, path, **kw)
        self.last_ms = (time.perf_counter() - t) * 1000
        return r

    def get(self, path: str, **kw: Any) -> httpx.Response:
        return self.req("GET", path, **kw)

    def post(self, path: str, **kw: Any) -> httpx.Response:
        return self.req("POST", path, **kw)

    def patch(self, path: str, **kw: Any) -> httpx.Response:
        return self.req("PATCH", path, **kw)

    def put(self, path: str, **kw: Any) -> httpx.Response:
        return self.req("PUT", path, **kw)


def login(key: str) -> Api:
    r = httpx.post(API + "/auth/login", json={"email": f"{key}@demo.loksutra.in", "password": PASSWORD}, timeout=60)
    assert r.status_code == 200, r.text
    return Api(r.json()["access_token"], key)


def case_payload(base: str = "A", **over: Any) -> dict[str, Any]:
    p = json.loads(json.dumps(DEMO_INPUTS[base]["payload"]))
    p["source_ref"] = f"QA-{int(time.time() * 1000) % 10**9}-{over.pop('tag', '')}"
    p.update(over)
    return p


def find_institution(c: Api, permanent_id: str) -> dict[str, Any]:
    r = c.get("/institutions", params={"q": permanent_id})
    assert r.status_code == 200, r.text
    hits = [i for i in r.json()["items"] if i["permanent_id"] == permanent_id]
    assert hits, f"institution {permanent_id} not found"
    return hits[0]


def timeline(c: Api, institution_id: str) -> list[dict[str, Any]]:
    r = c.get(f"/institutions/{institution_id}/timeline")
    assert r.status_code == 200, r.text
    body = r.json()
    return body["items"] if isinstance(body, dict) else body


def passport_count(c: Api, case_id: str) -> int:
    r = c.get(f"/cases/{case_id}/passport")
    assert r.status_code == 200, r.text
    body = r.json()
    return len(body["entries"] if isinstance(body, dict) else body)


def verify(c: Api, case_id: str) -> dict[str, Any]:
    r = c.get(f"/cases/{case_id}/passport/verify")
    assert r.status_code == 200, r.text
    return r.json()


def audit_count() -> int | None:
    """audit_log row count straight from the DB (None if the DB is not reachable from the test host)."""
    try:
        import psycopg

        with psycopg.connect(DB_URL, connect_timeout=3) as conn:
            return conn.execute("select count(*) from audit_log").fetchone()[0]
    except Exception:
        return None


def walk(obj: Any):
    """Yield every (key, value) pair in a nested JSON structure."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k, v
            yield from walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk(v)
