from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models.enums import (
    Bureau,
    CaseCategory,
    CaseStatus,
    LinkStatus,
    PendingStep,
    RelationType,
    Role,
    SourceChannel,
)
from tests.conftest import auth_headers, make_case, make_institution, make_link, make_user

NOW = datetime.now(UTC)


def _world(db):
    knp = make_institution(db, "Shrinath Engineering College", ro_code="KNP", district="Kanpur")
    bpl = make_institution(db, "Narmada Polytechnic", ro_code="BPL", district="Bhopal", state="Madhya Pradesh")
    me = make_user(db, Role.PGRC_OFFICER, Bureau.PGRC)
    cases = {}
    cases["css_amber"] = make_case(
        db, knp, Bureau.PGRC, owner_officer=me, channel=SourceChannel.CSS,
        received_at=NOW - timedelta(hours=55), category=CaseCategory.FEE_REFUND, start_clocks=True, subject="Refund pending",
    )
    cases["cpgrams_breached"] = make_case(
        db, knp, Bureau.RB, channel=SourceChannel.CPGRAMS, received_at=NOW - timedelta(days=30),
        category=CaseCategory.FACULTY_SHORTAGE, start_clocks=True, subject="Faculty shortage complaint", source_ref="DHIGH/E/2026/0012345",
    )
    cases["refund_breached"] = make_case(
        db, knp, Bureau.PGRC, owner_officer=me, channel=SourceChannel.EMAIL, category=CaseCategory.FEE_REFUND,
        status=CaseStatus.AWAITING_ATR, pending_step=PendingStep.INSTITUTION_ATR,
        pending_since=NOW - timedelta(days=12), start_clocks=True, received_at=NOW - timedelta(days=14),
    )
    cases["ro_case"] = make_case(
        db, bpl, Bureau.RO, owner_ro_code="BPL", channel=SourceChannel.RO_REGISTER, category=CaseCategory.INFRASTRUCTURE,
        received_at=NOW - timedelta(days=5),
    )
    cases["disposed"] = make_case(
        db, bpl, Bureau.PGRC, status=CaseStatus.DISPOSED, channel=SourceChannel.EMAIL, category=CaseCategory.SCHOLARSHIP,
        received_at=NOW - timedelta(days=40),
    )
    make_link(db, cases["css_amber"], cases["refund_breached"], RelationType.DUPLICATE, LinkStatus.SUGGESTED)
    make_link(db, cases["cpgrams_breached"], cases["refund_breached"], RelationType.CONFLICTING, LinkStatus.CONFIRMED)
    return me, knp, bpl, cases


def _get(client, h, **params):
    r = client.get("/api/v1/cases", params=params, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def test_list_shape_clocks_and_alerts(client, db):
    me, _k, _b, c = _world(db)
    h = auth_headers(client, me)
    body = _get(client, h)
    assert body["total"] == 5 and body["page"] == 1 and body["page_size"] == 25
    by_id = {i["id"]: i for i in body["items"]}
    amber = by_id[str(c["css_amber"].id)]
    assert amber["clocks"][0]["clock"] == "CSS_72H" and amber["clocks"][0]["state"] == "AMBER"
    assert amber["alerts"]["clock_amber"] == 1 and amber["alerts"]["pending_links"] == 1 and amber["alerts"]["total"] == 2
    assert amber["institution"]["name"] == "Shrinath Engineering College"
    refund = by_id[str(c["refund_breached"].id)]
    assert refund["overdue"] is True and refund["alerts"]["conflicting"] == 1
    assert refund["clocks"][0]["label"].startswith("Inst. 7-day · overdue 5 days")
    disposed = by_id[str(c["disposed"].id)]
    assert disposed["alerts"]["total"] == 0 and disposed["overdue"] is False
    assert "complainant" not in amber and "description" not in amber


def test_filters(client, db):
    me, knp, _b, c = _world(db)
    h = auth_headers(client, me)

    def ids(**p):
        return {i["id"] for i in _get(client, h, **p)["items"]}

    assert ids(bureau="RB") == {str(c["cpgrams_breached"].id)}
    assert ids(bureau=["RB", "RO"]) == {str(c["cpgrams_breached"].id), str(c["ro_case"].id)}
    assert ids(status="DISPOSED") == {str(c["disposed"].id)}
    assert ids(category="INFRASTRUCTURE") == {str(c["ro_case"].id)}
    assert ids(channel="CPGRAMS") == {str(c["cpgrams_breached"].id)}
    assert ids(institution_id=str(knp.id)) == {str(c[k].id) for k in ("css_amber", "cpgrams_breached", "refund_breached")}
    assert ids(ro_code="BPL") == {str(c["ro_case"].id), str(c["disposed"].id)}
    assert ids(owner="me") == {str(c["css_amber"].id), str(c["refund_breached"].id)}
    assert ids(overdue="true") == {str(c["cpgrams_breached"].id), str(c["refund_breached"].id)}
    assert str(c["disposed"].id) in ids(overdue="false")
    assert ids(clock_state="AMBER") == {str(c["css_amber"].id)}
    assert ids(clock_state="BREACHED") == ids(overdue="true")
    assert ids(has_alert="false") == {str(c["ro_case"].id), str(c["disposed"].id)}
    assert ids(q="DHIGH/E/2026") == {str(c["cpgrams_breached"].id)}
    assert ids(q="faculty shortage") == {str(c["cpgrams_breached"].id)}
    assert ids(q="narmada") == {str(c["ro_case"].id), str(c["disposed"].id)}
    assert ids(q="LS-2026-000001") != set() and ids(q="zzzz-no-match") == set()
    frm = (NOW - timedelta(days=10)).isoformat()
    assert ids(received_from=frm) == {str(c["css_amber"].id), str(c["ro_case"].id)}
    assert ids(received_to=frm, status="DISPOSED") == {str(c["disposed"].id)}
    # combined
    assert ids(bureau="PGRC", overdue="true") == {str(c["refund_breached"].id)}


def test_pagination_and_sort(client, db):
    me, knp, _b, c = _world(db)
    h = auth_headers(client, me)
    p1 = _get(client, h, page_size=2, page=1)
    p2 = _get(client, h, page_size=2, page=2)
    p3 = _get(client, h, page_size=2, page=3)
    assert [len(p["items"]) for p in (p1, p2, p3)] == [2, 2, 1]
    assert p1["total"] == p2["total"] == p3["total"] == 5
    seen = [i["id"] for p in (p1, p2, p3) for i in p["items"]]
    assert len(set(seen)) == 5
    received = [i["received_at"] for p in (p1, p2, p3) for i in p["items"]]
    assert received == sorted(received, reverse=True)
    # due_asc: soonest unfinished clock first, no-clock cases last, still paginated
    d = _get(client, h, sort="due_asc", page_size=2)
    assert d["total"] == 5 and d["items"][0]["id"] == str(c["cpgrams_breached"].id) or d["items"][0]["id"] == str(c["refund_breached"].id)
    all_due = _get(client, h, sort="due_asc", page_size=10)["items"]
    assert all_due[-1]["clocks"] == [] or all_due[-1]["id"] in {str(c["ro_case"].id), str(c["disposed"].id)}
    assert client.get("/api/v1/cases?page_size=500", headers=h).status_code == 422
    assert client.get("/api/v1/cases?status=NOPE", headers=h).status_code == 422


def test_detail_contains_links_clocks_institution(client, db):
    me, knp, _b, c = _world(db)
    h = auth_headers(client, me)
    r = client.get(f"/api/v1/cases/{c['refund_breached'].id}", headers=h)
    assert r.status_code == 200
    d = r.json()
    assert d["institution_snapshot"]["permanent_id"] == knp.permanent_id
    assert {lk["relation"] for lk in d["links"]} == {"DUPLICATE", "CONFLICTING"}
    assert all(lk["other_case"]["id"] != d["id"] for lk in d["links"])
    assert d["clocks"][0]["rule"] == "APH 2024-27 cl. 6.45"
    assert any("7-day refund duty" in a for a in d["suggested_actions"])
    assert d["masked"] is False
    assert client.get("/api/v1/cases/00000000-0000-0000-0000-000000000000", headers=h).json()["error"]["code"] == "NOT_FOUND"
    assert client.get("/api/v1/cases/not-a-uuid", headers=h).status_code == 422
