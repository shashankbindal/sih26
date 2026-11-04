from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models import InstitutionAlias
from app.models.enums import Bureau, CaseCategory, LinkStatus, RelationType, Role, SourceChannel
from app.services import passport
from tests.conftest import auth_headers, make_case, make_institution, make_link, make_user

NOW = datetime.now(UTC)


def _world(db):
    a = make_institution(db, "Shrinath Engineering College", name_norm="shrinath engineering college kanpur", ro_code="KNP")
    b = make_institution(db, "Narmada Polytechnic", name_norm="narmada polytechnic bhopal", ro_code="BPL", state="Madhya Pradesh")
    db.add(InstitutionAlias(institution_id=a.id, alias_raw="SEC Kanpur", alias_norm="sec kanpur", source="SEED"))
    db.commit()
    u = make_user(db, Role.RB_OFFICER, Bureau.RB)
    c1 = make_case(db, a, Bureau.PGRC, channel=SourceChannel.CSS, start_clocks=True, received_at=NOW - timedelta(days=1), source_ref="CSS-2026-88123")
    c2 = make_case(db, a, Bureau.RB, channel=SourceChannel.CPGRAMS, start_clocks=True, received_at=NOW - timedelta(days=30), category=CaseCategory.FACULTY_SHORTAGE)
    make_case(db, b, Bureau.RO, owner_ro_code="BPL", received_at=NOW - timedelta(days=3))
    make_link(db, c1, c2, RelationType.RELATED, LinkStatus.SUGGESTED)
    passport.append_entry(db, event="RECEIVED", case_id=c1.id, institution_id=a.id)
    db.commit()
    return u, a, b, c1, c2


def test_health(client, db):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["db"] == "ok" and body["version"] and body["seeded_at"] is None
    from app.models.system import PolicyConfig

    db.add(PolicyConfig(key="seeded_at", value={"at": "2026-11-01T10:00:00+00:00"}))
    db.commit()
    assert client.get("/api/v1/health").json()["seeded_at"].startswith("2026-11-01T10:00:00")


def test_openapi_available(client):
    r = client.get("/openapi.json")
    assert r.status_code == 200
    paths = r.json()["paths"]
    for p in ("/api/v1/health", "/api/v1/cases", "/api/v1/cases/{case_id}/passport/verify", "/api/v1/institutions/{institution_id}/timeline"):
        assert p in paths


def test_institution_list_filters_and_stats(client, db):
    u, a, b, *_ = _world(db)
    h = auth_headers(client, u)
    body = client.get("/api/v1/institutions", headers=h).json()
    assert body["total"] == 2
    by = {i["name"]: i for i in body["items"]}
    assert by["Shrinath Engineering College"]["open_cases"] == 2 and by["Shrinath Engineering College"]["open_alerts"] == 1
    assert client.get("/api/v1/institutions?ro_code=BPL", headers=h).json()["total"] == 1
    assert client.get("/api/v1/institutions?state=madhya pradesh", headers=h).json()["items"][0]["name"] == "Narmada Polytechnic"
    assert client.get("/api/v1/institutions?has_open_alerts=true", headers=h).json()["total"] == 1
    top = client.get("/api/v1/institutions?sort=open_cases_desc", headers=h).json()["items"][0]
    assert top["name"] == "Shrinath Engineering College"


def test_institution_fuzzy_search_alias_and_permanent_id(client, db):
    u, a, b, *_ = _world(db)
    h = auth_headers(client, u)

    def names(q):
        return [i["name"] for i in client.get("/api/v1/institutions", params={"q": q}, headers=h).json()["items"]]

    assert names("shrinath engg collage kanpur")[:1] == ["Shrinath Engineering College"]  # typo tolerant
    assert names("SEC Kanpur")[:1] == ["Shrinath Engineering College"]  # alias
    assert names(a.permanent_id) == ["Shrinath Engineering College"]
    assert names("narmada") == ["Narmada Polytechnic"]
    assert names("zzzzqqqq") == []
    hit = client.get("/api/v1/institutions", params={"q": "shrinath engineering"}, headers=h).json()["items"][0]
    assert 0 < hit["score"] <= 1


def test_institution_detail_timeline_links(client, db):
    u, a, b, c1, c2 = _world(db)
    h = auth_headers(client, u)
    d = client.get(f"/api/v1/institutions/{a.id}", headers=h).json()
    assert d["permanent_id"] == a.permanent_id and d["aliases"][0]["alias_raw"] == "SEC Kanpur"
    assert d["summary"]["open_by_bureau"] == {"PGRC": 1, "RB": 1} and d["summary"]["open_total"] == 2
    assert d["summary"]["last_action_at"] is not None
    tl = client.get(f"/api/v1/institutions/{a.id}/timeline", headers=h).json()
    assert tl["total"] == 2
    assert [i["id"] for i in tl["items"]] == [str(c1.id), str(c2.id)]  # newest first
    assert tl["items"][0]["relations"][0]["relation"] == "RELATED"
    assert tl["items"][0]["relations"][0]["other_case"]["id"] == str(c2.id)
    links = client.get(f"/api/v1/institutions/{a.id}/links", headers=h).json()
    assert len(links) == 1 and links[0]["relation"] == "RELATED" and links[0]["reasons"]
    assert client.get(f"/api/v1/institutions/{b.id}/links", headers=h).json() == []
    assert client.get("/api/v1/institutions/00000000-0000-0000-0000-000000000000", headers=h).status_code == 404


def test_search_endpoint(client, db):
    u, a, b, c1, c2 = _world(db)
    h = auth_headers(client, u)
    r = client.get("/api/v1/search", params={"q": a.permanent_id}, headers=h).json()
    assert r["institutions"][0]["permanent_id"] == a.permanent_id and r["institutions"][0]["score"] == 1.0
    r = client.get("/api/v1/search", params={"q": c1.display_id}, headers=h).json()
    assert [c["id"] for c in r["cases"]] == [str(c1.id)] and r["cases"][0]["institution_name"] == a.name
    r = client.get("/api/v1/search", params={"q": "CSS-2026-88123"}, headers=h).json()
    assert [c["id"] for c in r["cases"]] == [str(c1.id)]
    r = client.get("/api/v1/search", params={"q": "shrinath"}, headers=h).json()
    assert r["institutions"][0]["name"] == a.name
    assert client.get("/api/v1/search", params={"q": ""}, headers=h).json() == {"institutions": [], "cases": []}
    assert client.get("/api/v1/search?q=x").status_code == 401
