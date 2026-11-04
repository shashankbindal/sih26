"""D2 (RO region scoping), D6 (upload validation), D8 (access-log redaction)."""

from __future__ import annotations

import io
import logging
import zipfile
from datetime import UTC, datetime, timedelta

import pytest

from app.main import RedactQueryFilter, install_access_log_redaction, redact_query
from app.models.enums import Bureau, Role
from app.services import importer
from tests.conftest import auth_headers, make_case, make_institution, make_user

NOW = datetime.now(UTC)


def _ro_world(db):
    knp = make_institution(db, "Kanpur Institute", ro_code="KNP")
    bpl = make_institution(db, "Bhopal Institute", ro_code="BPL", state="Madhya Pradesh")
    ro = make_user(db, Role.RO_OFFICER, Bureau.RO, ro_code="KNP")
    pgrc = make_user(db, Role.PGRC_OFFICER, Bureau.PGRC)
    c = {
        "knp_pgrc": make_case(db, knp, Bureau.PGRC, received_at=NOW - timedelta(days=1)),
        "knp_ro": make_case(db, knp, Bureau.RO, owner_ro_code="KNP", received_at=NOW - timedelta(days=2)),
        "bpl_pgrc": make_case(db, bpl, Bureau.PGRC, received_at=NOW - timedelta(days=3)),
        "bpl_ro": make_case(db, bpl, Bureau.RO, owner_ro_code="BPL", received_at=NOW - timedelta(days=4)),
        "bpl_rb": make_case(db, bpl, Bureau.RB, received_at=NOW - timedelta(days=5)),
    }
    return knp, bpl, ro, pgrc, c


def _ids(client, h, **params):
    r = client.get("/api/v1/cases", params=params, headers=h)
    assert r.status_code == 200, r.text
    return {i["id"] for i in r.json()["items"]}, r.json()["total"]


def test_ro_list_defaults_to_own_region(client, db):
    _k, _b, ro, pgrc, c = _ro_world(db)
    h = auth_headers(client, ro)
    own = {str(c["knp_pgrc"].id), str(c["knp_ro"].id)}
    assert _ids(client, h) == (own, 2)
    # asking for another region without scope=all does not widen the list
    assert _ids(client, h, ro_code="BPL")[0] == own
    all_ids, total = _ids(client, h, scope="all")
    assert total == 5 and all_ids == {str(x.id) for x in c.values()}
    assert _ids(client, h, scope="all", ro_code="BPL")[0] == {str(c["bpl_pgrc"].id), str(c["bpl_ro"].id), str(c["bpl_rb"].id)}
    # other roles unaffected, and scope is validated
    assert _ids(client, auth_headers(client, pgrc))[1] == 5
    assert client.get("/api/v1/cases?scope=none", headers=h).status_code == 422


def test_ro_privacy_on_detail(client, db):
    _k, _b, ro, _p, c = _ro_world(db)
    h = auth_headers(client, ro)

    def detail(key):
        return client.get(f"/api/v1/cases/{c[key].id}", headers=h).json()

    for key in ("bpl_pgrc", "bpl_ro", "bpl_rb"):  # other region and other bureaus: existence visible, PII/description masked
        d = detail(key)
        assert d["masked"] is True
        assert d["complainant"]["name"] is None and d["complainant"]["email"] is None and d["complainant"]["phone"] is None
        assert d["description"] is None and "description" in d["masked_fields"]
        assert d["display_id"] and d["subject"] and d["institution"]["name"] and d["owner_bureau"]
    for key in ("knp_pgrc", "knp_ro"):  # own region (even PGRC-owned): full detail
        d = detail(key)
        assert d["masked"] is False and d["complainant"]["name"] and d["description"]


def test_institution_timeline_and_links_stay_cross_region(client, db):
    _k, bpl, ro, _p, c = _ro_world(db)
    h = auth_headers(client, ro)
    tl = client.get(f"/api/v1/institutions/{bpl.id}/timeline", headers=h)
    assert tl.status_code == 200 and tl.json()["total"] == 3
    assert "complainant" not in tl.text and "description" not in tl.json()["items"][0]
    assert client.get(f"/api/v1/institutions/{bpl.id}/links", headers=h).status_code == 200


# ------------------------------------------------------------------------------------ D6
def _xlsx_bytes() -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    wb.active.append(["subject", "source_ref"])
    wb.active.append(["Refund", "R-1"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("evil.exe", b"MZ\x90\x00\x03\x00\x00\x00"),
        ("evil.csv", b"MZ\x90\x00\x03\x00\x00\x00,a\n1,2\n"),  # binary renamed .csv (NUL bytes)
        ("data.txt", b"a,b\n1,2\n"),
        ("noext", b"a,b\n1,2\n"),
        ("fake.xlsx", b"a,b\n1,2\n"),  # not a zip
        ("zip.xlsx", _zip_noxl := b"PK\x03\x04"),  # truncated zip
        ("zipped.csv", b"PK\x03\x04rest"),
        ("macro.xlsm", b"PK\x03\x04"),
    ],
)
def test_preview_rejects_bad_uploads(client, db, name, content):
    h = auth_headers(client, make_user(db, Role.PGRC_OFFICER, Bureau.PGRC))
    r = client.post("/api/v1/imports/preview", files={"file": (name, content)}, headers=h)
    assert r.status_code == 422, (name, r.text)
    err = r.json()["error"]
    assert err["code"] in {"UNSUPPORTED_FILE_TYPE", "EMPTY_FILE"} and set(err) == {"code", "message", "details"}


def test_zip_without_xl_entries_rejected(client, db):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("readme.txt", "hello")
    h = auth_headers(client, make_user(db, Role.PGRC_OFFICER, Bureau.PGRC))
    r = client.post("/api/v1/imports/preview", files={"file": ("x.xlsx", buf.getvalue())}, headers=h)
    assert r.status_code == 422 and r.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"


def test_preview_accepts_valid_csv_and_xlsx(client, db):
    h = auth_headers(client, make_user(db, Role.PGRC_OFFICER, Bureau.PGRC))
    r = client.post("/api/v1/imports/preview", files={"file": ("a.csv", b"subject,ref\nFee,1\n")}, headers=h)
    assert r.status_code == 200 and r.json()["columns"] == ["subject", "ref"]
    utf8 = "subject,name\nफ,x\n".encode()
    assert client.post("/api/v1/imports/preview", files={"file": ("u.csv", utf8)}, headers=h).status_code == 200
    assert client.post("/api/v1/imports/preview", files={"file": ("l.csv", "subject,name\ncaf\xe9,x\n".encode("latin-1"))}, headers=h).status_code == 200
    r = client.post("/api/v1/imports/preview", files={"file": ("a.xlsx", _xlsx_bytes())}, headers=h)
    assert r.status_code == 200 and r.json()["columns"] == ["subject", "source_ref"]


def test_validate_upload_unit():
    assert importer.validate_upload("A.CSV", b"a,b\n") == "csv"
    assert importer.validate_upload("a.xlsx", _xlsx_bytes()) == "xlsx"


# ------------------------------------------------------------------------------------ D8
def test_redact_query_function():
    assert redact_query("/api/v1/search?q=Asha+Verma%40example.test") == "/api/v1/search?[redacted]"
    assert redact_query("/api/v1/cases?q=x&status=DISPOSED") == "/api/v1/cases?[redacted]"
    assert redact_query("/api/v1/health") == "/api/v1/health"


def test_uvicorn_access_record_is_redacted():
    rec = logging.LogRecord(
        "uvicorn.access", logging.INFO, __file__, 1,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:5555", "GET", "/api/v1/search?q=asha.verma@example.test", "1.1", 200), None,
    )
    assert RedactQueryFilter().filter(rec) is True
    out = rec.getMessage()
    assert "q=" not in out and "asha" not in out and "/api/v1/search?[redacted]" in out
    assert "200" in out


def test_filter_installed_on_access_logger_and_idempotent(caplog):
    install_access_log_redaction()
    install_access_log_redaction()
    access = logging.getLogger("uvicorn.access")
    assert sum(isinstance(f, RedactQueryFilter) for f in access.filters) == 1
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    access.addHandler(handler)
    access.setLevel(logging.INFO)
    try:
        access.info('%s - "%s %s HTTP/%s" %d', "1.2.3.4:1", "GET", "/api/v1/cases?q=Asha+Verma", "1.1", 200)
    finally:
        access.removeHandler(handler)
    assert "Asha" not in stream.getvalue() and "?[redacted]" in stream.getvalue()
