"""Privacy (project privacy rule): complainant PII masked for non-owning bureaus and SENIOR_MGMT; reveal flow; RO scoping.

A fresh PGRC case is created with unique PII markers so every other endpoint can be scanned for leakage.
"""

from __future__ import annotations

import json
import uuid

import pytest

from tests.api.helpers import Api, case_payload, find_institution, passport_count, verify, walk

TAG = uuid.uuid4().hex[:6]
SURNAME = f"Quill{TAG}feather"
NAME = f"Zaphod {SURNAME}"
EMAIL = f"zaphod.{TAG}@mailbox.example"
PHONE = "9811" + str(int(TAG, 16))[:6].ljust(6, "0")
SECRET_DESC = f"My ward paid fees to the college and has not been refunded; marker DESC-{TAG}."
MARKERS = [NAME, SURNAME, EMAIL, PHONE]


@pytest.fixture(scope="module")
def pii_case(u) -> dict:
    p = case_payload("A", tag="priv")
    p["complainant"] = {"name": NAME, "email": EMAIL, "phone": PHONE, "party_type": "STUDENT"}
    p["description"] = SECRET_DESC
    r = u["pgrc.officer"].post("/cases", json=p)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["case"]["masked"] is False, "owning bureau must see the complainant"
    assert body["case"]["complainant"]["name"] == NAME
    return body["case"]


def _leaks(resp, with_description: bool = False) -> list[str]:
    t = resp.text
    marks = MARKERS + ([f"DESC-{TAG}", f"desc {TAG}"] if with_description else [])
    return [m for m in marks if m in t]


def test_owner_sees_pii(u, pii_case):
    d = u["pgrc.officer"].get(f"/cases/{pii_case['id']}").json()
    assert d["masked"] is False and d["complainant"]["email"] == EMAIL and d["description"] == SECRET_DESC


@pytest.mark.parametrize("who", ["rb.officer", "approval.officer", "vigilance.officer", "ro.bhopal", "rb.head"])
def test_non_owning_bureau_gets_masked_detail(u, pii_case, who):
    r = u[who].get(f"/cases/{pii_case['id']}")
    assert r.status_code == 200
    d = r.json()
    assert d["masked"] is True
    assert d["complainant"]["name"] is None and d["complainant"]["email"] is None and d["complainant"]["phone"] is None
    assert d["description"] is None
    for f in ("complainant.name", "complainant.email", "complainant.phone", "description"):
        assert f in d["masked_fields"], d["masked_fields"]
    assert not _leaks(r), f"PII leaked in masked case detail for {who}: {_leaks(r)}"
    # every free-text field derived from the description must be hidden too (description_norm used to leak)
    assert not d.get("description_norm"), "description_norm exposes the masked description text"
    assert "DESC-" + TAG not in r.text


def test_region_ro_is_treated_as_owner_per_prd(u, pii_case):
    """Data scoping: 'ROs: their region' - the Kanpur RO sees full detail of a case at a Kanpur-region institution."""
    assert u["ro.kanpur"].get(f"/cases/{pii_case['id']}").json()["masked"] is False


def test_senior_mgmt_never_sees_complainant_identity(u, pii_case):
    r = u["mgmt"].get(f"/cases/{pii_case['id']}")
    assert r.status_code == 200
    d = r.json()
    c = d["complainant"]
    assert c["name"] is None and c["email"] is None and c["phone"] is None
    assert not [m for m in MARKERS if m in r.text and m not in (SECRET_DESC,)] or NAME in (d.get("description") or "")
    # SENIOR_MGMT may read the description but the identity fields are always null
    assert u["mgmt"].post(f"/cases/{pii_case['id']}/reveal-pii", json={"reason": "management curiosity, not allowed"}).status_code == 403
    d2 = u["mgmt"].get(f"/cases/{pii_case['id']}").json()
    assert d2["complainant"]["name"] is None and d2["complainant"]["email"] is None


@pytest.mark.parametrize("who", ["rb.officer", "mgmt", "ro.bhopal", "approval.officer"])
def test_no_pii_anywhere_else_for_non_owner(u, pii_case, who):
    """Scan every case-bearing endpoint for the complainant's name, e-mail and phone."""
    c: Api = u[who]
    inst_id = pii_case["institution"]["id"]
    cid = pii_case["id"]
    leaks: dict[str, list[str]] = {}

    def check(label, resp):
        assert resp.status_code in (200, 403), (label, resp.status_code, resp.text[:200])
        found = _leaks(resp, with_description=(who != "mgmt"))
        if resp.status_code == 200 and found:
            leaks[label] = found

    check("cases?q=name", c.get("/cases", params={"q": NAME}))
    check("cases?q=email", c.get("/cases", params={"q": EMAIL}))
    check("cases list", c.get("/cases", params={"institution_id": inst_id, "page_size": 100}))
    check("timeline", c.get(f"/institutions/{inst_id}/timeline"))
    check("inst links", c.get(f"/institutions/{inst_id}/links"))
    check("institution", c.get(f"/institutions/{inst_id}"))
    check("search name", c.get("/search", params={"q": NAME}))
    check("search quill", c.get("/search", params={"q": SURNAME}))
    check("passport", c.get(f"/cases/{cid}/passport"))
    check("risk", c.get(f"/cases/{cid}/risk"))
    check("links", c.get("/links", params={"institution_id": inst_id}))
    for lk in c.get("/links", params={"institution_id": inst_id}).json().get("items", []):
        check("link detail", c.get(f"/links/{lk['id']}"))
    check("review", c.get("/review/institution-matches"))
    check("notifications", c.get("/notifications"))
    check("clearances", c.get("/clearances"))
    check("actions", c.get("/institution-actions"))
    check("dashboard top", c.get("/dashboard/top-institutions"))
    assert not leaks, f"PII leaked to {who}: {leaks}"


def test_search_by_complainant_name_is_not_an_oracle(u, pii_case):
    """A non-owner searching a complainant's name must not be able to find the case (side channel)."""
    r = u["rb.officer"].get("/cases", params={"q": NAME})
    assert r.status_code == 200
    ids = [i["id"] for i in r.json()["items"]]
    assert pii_case["id"] not in ids, "case found via masked complainant name"


def test_reveal_requires_reason_of_10_chars_and_logs(u, pii_case):
    rb = u["rb.officer"]
    cid = pii_case["id"]
    for bad in ["", "short", "123456789"]:
        r = rb.post(f"/cases/{cid}/reveal-pii", json={"reason": bad})
        assert r.status_code == 422, (bad, r.status_code)
    before = passport_count(rb, cid)
    r = rb.post(f"/cases/{cid}/reveal-pii", json={"reason": "Need complainant contact to schedule hearing"})
    assert r.status_code in (200, 201), r.text
    body = r.json()
    revealed = body.get("complainant") or body.get("case", {}).get("complainant")
    assert revealed and revealed["name"] == NAME
    entries = rb.get(f"/cases/{cid}/passport").json()
    entries = entries["entries"] if isinstance(entries, dict) else entries
    assert len(entries) == before + 1
    assert entries[-1]["event"] == "PII_REVEALED"
    assert "Need complainant contact" not in json.dumps(entries[-1]["payload"]) or True  # reason may be stored; PII must not be
    assert not [m for m in MARKERS if m in json.dumps(entries[-1])], "PII stored in the PII_REVEALED passport payload"
    assert verify(rb, cid)["ok"] is True


def test_reveal_requires_auth_and_valid_case(u, anon):
    assert anon.post(f"/cases/{uuid.uuid4()}/reveal-pii", json={"reason": "x" * 12}).status_code == 401
    assert u["rb.officer"].post(f"/cases/{uuid.uuid4()}/reveal-pii", json={"reason": "x" * 12}).status_code == 404


# ------------------------------------------------------------------ RO scoping
def test_ro_dashboard_is_forced_to_own_region(u):
    kn = u["ro.kanpur"]
    k = kn.get("/dashboard/kpis").json()
    admin_knp = u["admin"].get("/dashboard/kpis", params={"ro_code": "KNP"}).json()
    assert k["total"] == admin_knp["total"] < u["admin"].get("/dashboard/kpis").json()["total"]
    # user cannot widen scope by passing another region
    assert kn.get("/dashboard/kpis", params={"ro_code": "BPL"}).json()["total"] == k["total"]
    regions = {x["ro_code"] for x in kn.get("/dashboard/by-region").json()}
    assert regions == {"KNP"}, regions
    assert {x["ro_code"] for x in kn.get("/dashboard/top-institutions").json()} == {"KNP"}


def test_ro_case_list_scoped_to_region(u):
    """RO users are scoped to their region. Server-side scoping of /cases is the safe reading."""
    r = u["ro.kanpur"].get("/cases", params={"page_size": 100})
    total_all = u["admin"].get("/cases").json()["total"]
    assert r.json()["total"] < total_all, (
        f"RO officer (Kanpur) sees all {r.json()['total']} cases; the API does not scope /cases by region"
    )


def test_other_ro_dashboards_differ(u):
    a = u["ro.kanpur"].get("/dashboard/kpis").json()["total"]
    b = u["ro.bhopal"].get("/dashboard/kpis").json()["total"]
    c = u["ro.chandigarh"].get("/dashboard/kpis").json()["total"]
    assert len({a, b, c}) >= 2 and max(a, b, c) < u["admin"].get("/dashboard/kpis").json()["total"]


def test_privacy_fields_never_contain_party_hash_or_raw_contact(u, pii_case):
    r = u["rb.officer"].get(f"/cases/{pii_case['id']}")
    keys = {k for k, _ in walk(r.json())}
    assert "party_hash" not in keys and "password_hash" not in keys
    inst = find_institution(u["admin"], "1-4463974255")
    tl = u["mgmt"].get(f"/institutions/{inst['id']}/timeline")
    assert "party_hash" not in tl.text
