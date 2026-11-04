"""Re-verification of fixes D1, D2, D3, D6 (black-box)."""

from __future__ import annotations

import io
import json
import uuid
import zipfile

import pytest

from tests.api.helpers import case_payload, find_institution, timeline

TAG = uuid.uuid4().hex[:6]


@pytest.fixture(scope="module")
def pii_case(u):
    p = case_payload("A", tag="reverify")
    p["complainant"] = {"name": f"Rev{TAG} Person", "email": f"rev{TAG}@mailbox.example", "phone": "9822200033", "party_type": "STUDENT"}
    p["description"] = f"My ward paid fees to the college and has not been refunded; marker REV-{TAG}."
    r = u["pgrc.officer"].post("/cases", json=p)
    assert r.status_code == 201, r.text
    return r.json()


# ------------------------------------------------------------------ D1
@pytest.mark.parametrize("who", ["rb.officer", "approval.officer", "vigilance.officer", "ro.bhopal", "rb.head"])
def test_D1_masked_description_and_norm_are_null_on_case_and_link(u, pii_case, who):
    c = u[who]
    cid = pii_case["case"]["id"]
    d = c.get(f"/cases/{cid}").json()
    assert d["description"] is None
    assert d.get("description_norm") in (None, "")
    assert f"REV-{TAG}" not in json.dumps(d) and f"rev {TAG}".lower() not in json.dumps(d).lower().replace("-", " ")
    assert pii_case["links"], "scenario A payload must yield links"
    for lk in pii_case["links"]:
        r = c.get(f"/links/{lk['link_id']}")
        assert r.status_code == 200
        txt = r.text.lower().replace("-", " ")
        assert f"rev {TAG}" not in txt, f"{who}: marker present in /links/{{id}}"
        body = r.json()
        for side in ("case_a", "case_b"):
            side_case = body.get(side) or {}
            if side_case.get("id") == cid:  # other side may be RB-owned (legitimately visible to RB)
                assert side_case.get("description") in (None, "")
                assert not side_case.get("description_norm")


def test_D1_owner_still_sees_description(u, pii_case):
    d = u["pgrc.officer"].get(f"/cases/{pii_case['case']['id']}").json()
    assert d["description"] and f"REV-{TAG}" in d["description"]


# ------------------------------------------------------------------ D2
def test_D2_ro_default_is_region_only_and_scope_all_widens(u):
    ro, ad = u["ro.kanpur"], u["admin"]
    total_all = ad.get("/cases", params={"page_size": 1}).json()["total"]
    r = ro.get("/cases", params={"page_size": 100}).json()
    assert 0 < r["total"] < total_all
    for i in r["items"]:
        assert "KNP" in ((i["institution"] or {}).get("ro_code"), i["owner_ro_code"]), i["display_id"]
    wide = ro.get("/cases", params={"scope": "all", "page_size": 1}).json()["total"]
    assert wide == total_all
    # an explicit foreign region filter does not silently widen the default scope
    other = ro.get("/cases", params={"ro_code": "BPL", "page_size": 1}).json()["total"]
    assert other <= r["total"]


def test_D2_masked_detail_outside_region_and_institution_360_cross_region(u):
    gyan = find_institution(u["admin"], "1-4458812074")  # BPL
    tl = timeline(u["ro.kanpur"], gyan["id"])
    assert tl, "Institution 360 timeline must stay cross-region"
    cid = next(c["id"] for c in tl if c["owner_bureau"] == "PGRC")
    d = u["ro.kanpur"].get(f"/cases/{cid}")
    assert d.status_code == 200
    body = d.json()
    assert body["masked"] is True
    assert body["complainant"]["name"] is None and body["description"] is None and not body.get("description_norm")
    assert u["ro.kanpur"].get(f"/institutions/{gyan['id']}/links").status_code == 200


def test_D2_other_roles_unaffected_by_scope(u):
    total_all = u["admin"].get("/cases", params={"page_size": 1}).json()["total"]
    for who in ("pgrc.officer", "rb.officer", "mgmt"):
        assert u[who].get("/cases", params={"page_size": 1}).json()["total"] == total_all


# ------------------------------------------------------------------ D3
def test_D3_seeded_links_carry_next_action_and_lead(u):
    ad = u["admin"]
    inst = find_institution(ad, "1-4471203398")
    conf = [lk for lk in ad.get(f"/institutions/{inst['id']}/links").json() if lk["relation"] == "CONFLICTING"][0]
    d = ad.get(f"/links/{conf['id']}").json()
    assert "hold" in d["suggested_next_action"].lower() and "letters" in d["suggested_next_action"].lower()
    assert d["lead_bureau"] == "RB"
    assert (d["thread"] or {}).get("shared_next_action")
    bad = []
    for lk in ad.get("/links", params={"page_size": 100}).json()["items"]:
        x = ad.get(f"/links/{lk['id']}").json()
        if not x["suggested_next_action"] or not x["lead_bureau"]:
            bad.append(lk["id"])
    assert not bad, f"links without next action/lead bureau: {len(bad)}"


# ------------------------------------------------------------------ D6
def _xlsx_like() -> bytes:
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("not_xl/foo.txt", "x")
    return b.getvalue()


@pytest.mark.parametrize("name,content,ctype", [
    ("evil.exe", b"MZ\x90\x00\x03\x00\x00\x00", "application/octet-stream"),
    ("renamed.csv", b"MZ\x90\x00\x03\x00\x00\x00\x00\x00\xff\xfe", "text/csv"),
    ("renamed.xlsx", b"MZ\x90\x00\x03\x00\x00\x00", "application/octet-stream"),
    ("fake.xlsx", _xlsx_like(), "application/octet-stream"),
    ("notes.txt", b"a,b\n1,2\n", "text/plain"),
])
def test_D6_non_csv_xlsx_rejected_with_422(u, name, content, ctype):
    pg = u["pgrc.officer"]
    r = pg.post("/imports/preview", files={"file": (name, content, ctype)})
    assert r.status_code == 422, (name, r.status_code, r.text[:200])
    assert r.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"
    r2 = pg.post("/imports", files={"file": (name, content, ctype)}, data={"mapping": "{}"})
    assert r2.status_code == 422, (name, r2.status_code)


def test_D6_real_csv_still_accepted(u):
    r = u["pgrc.officer"].post("/imports/preview", files={"file": ("ok.csv", b"subject,institution_name\nx,y\n", "text/csv")})
    assert r.status_code == 200, r.text
