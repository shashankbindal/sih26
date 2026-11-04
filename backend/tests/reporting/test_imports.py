from __future__ import annotations

import io
import json
from types import SimpleNamespace

from openpyxl import Workbook
from pydantic import BaseModel

from app.models.cases import Case
from app.models.complainants import Complainant
from app.models.enums import MatchStatus
from app.models.system import AuditLog, ImportJob
from app.services import importer
from tests.conftest import auth_headers, make_institution
from tests.reporting._world import build_world

API = "/api/v1"

CSV = (
    "Ref No,Date,College Name,AICTE ID,Name,Email,Mobile,Type,Title,Details,Bureau,RO\n"
    "R-1,28/10/2026,auto Shrinath college,1-4463974255,Asha Verma,asha@example.in,98100 00001,fee refund,Refund pending,Fee not refunded,PGRC,KNP\n"
    "R-2,2026-10-29 10:00,review Shri Ram college,,,,,,Hostel issue dup,Water problem,rb,\n"
    "R-3,2026-10-30,unknown place,,,,,,Faculty shortage,,RB,\n"
    "R-4,not a date,auto x,,,,,,Bad date row,,PGRC,\n"
    "R-5,2026-10-30,,,,,,,No institution,,PGRC,\n"
    "R-6,2026-10-30,auto y,,,,,,,,PGRC,\n"
    "R-7,2026-10-30,auto z,,,,,,Bad RO,,PGRC,ZZZ\n"
    ",,,,,,,,,,,\n"
)


class FakeCaseCreate(BaseModel):
    source_channel: str
    source_ref: str | None = None
    received_at: object
    institution_text_raw: str | None = None
    permanent_id_raw: str | None = None
    complainant: dict
    category: str | None = None
    subject: str
    description: str | None = None
    owner_bureau: str
    owner_ro_code: str | None = None


def _fake_create_case(session, payload, user, *, source_import_job_id=None):
    comp = Complainant(
        name=payload.complainant.get("name") or "-", email=payload.complainant.get("email"),
        phone=payload.complainant.get("phone"), party_hash=f"h{payload.source_ref}", party_type="OTHER",
    )
    session.add(comp)
    session.flush()
    text = payload.institution_text_raw or ""
    status = "AUTO_SUGGESTED" if text.startswith("auto") else "NEEDS_REVIEW" if text.startswith("review") else "UNRESOLVED"
    case = Case(
        source_channel=payload.source_channel, source_ref=payload.source_ref, received_at=payload.received_at,
        institution_text_raw=text, institution_match_status=MatchStatus(status), complainant_id=comp.id,
        category=payload.category or "OTHER", subject=payload.subject, description=payload.description,
        owner_bureau=payload.owner_bureau, owner_ro_code=payload.owner_ro_code,
    )
    session.add(case)
    session.flush()
    links = [{"link_id": "x"}] if "dup" in payload.subject else []
    return SimpleNamespace(case=SimpleNamespace(id=case.id), resolution=SimpleNamespace(status=status), links=links)


def _patch(monkeypatch):
    monkeypatch.setattr(importer, "_intake", lambda: (_fake_create_case, FakeCaseCreate))


def _upload(client, h, content: bytes, name="cases.csv", mapping=None):
    files = {"file": (name, content, "text/csv")}
    if mapping is None:
        return client.post(f"{API}/imports/preview", files=files, headers=h)
    return client.post(f"{API}/imports", files=files, data={"mapping": json.dumps(mapping)}, headers=h)


def test_template_and_preview_heuristics(db, client):
    w = build_world(db)
    h = auth_headers(client, w["me"])
    t = client.get(f"{API}/imports/template.csv", headers=h)
    assert t.status_code == 200 and t.content.decode("utf-8-sig").strip().split(",") == importer.TEMPLATE_HEADERS
    p = _upload(client, h, CSV.encode())
    assert p.status_code == 200, p.text
    body = p.json()
    assert body["total_rows"] == 7 and len(body["sample_rows"]) == 7
    m = body["suggested_mapping"]
    assert m["Ref No"] == "source_ref" and m["Date"] == "received_at" and m["College Name"] == "institution_name"
    assert m["AICTE ID"] == "permanent_id" and m["Name"] == "complainant_name" and m["Email"] == "complainant_email"
    assert m["Mobile"] == "complainant_phone" and m["Type"] == "category" and m["Title"] == "subject"
    assert m["Details"] == "description" and m["Bureau"] == "owner_bureau" and m["RO"] == "ro_code"
    mgmt = auth_headers(client, w["mgmt"])
    assert _upload(client, mgmt, CSV.encode()).status_code == 403


def test_preview_xlsx(db, client):
    w = build_world(db)
    wb = Workbook()
    ws = wb.active
    ws.append(["source_ref", "received_at", "institution_name", "subject"])
    ws.append(["X1", "2026-10-01", "Some College", "Subject here"])
    buf = io.BytesIO()
    wb.save(buf)
    r = _upload(client, auth_headers(client, w["me"]), buf.getvalue(), name="c.xlsx")
    assert r.status_code == 200 and r.json()["columns"][0] == "source_ref" and r.json()["total_rows"] == 1


def test_import_counts_errors_and_audit(db, client, monkeypatch):
    _patch(monkeypatch)
    w = build_world(db)
    h = auth_headers(client, w["me"])
    mapping = {
        "Ref No": "source_ref", "Date": "received_at", "College Name": "institution_name", "AICTE ID": "permanent_id",
        "Name": "complainant_name", "Email": "complainant_email", "Mobile": "complainant_phone", "Type": "category",
        "Title": "subject", "Details": "description", "Bureau": "owner_bureau", "RO": "ro_code",
    }
    before = db.query(Case).count()
    r = _upload(client, h, CSV.encode(), mapping=mapping)
    assert r.status_code == 200, r.text
    job = r.json()
    # R-1 R-2 R-3 imported; R-4 bad date, R-5 no institution, R-6 no subject, R-7 bad RO are row errors
    assert job["total_rows"] == 7 and job["imported"] == 3 and job["error_count"] == 4
    assert (job["auto_suggested"], job["needs_review"], job["unresolved"], job["links_found"]) == (1, 1, 1, 1)
    assert [e["row"] for e in job["errors"]] == [5, 6, 7, 8]
    assert "asha" not in json.dumps(job).lower() and "98100" not in json.dumps(job)
    db.expire_all()
    assert db.query(Case).count() == before + 3
    saved = db.get(ImportJob, job["id"])
    assert saved.status == "COMPLETED" and saved.imported == 3
    assert db.query(AuditLog).filter(AuditLog.entity == "import_job").count() == 1
    again = client.get(f"{API}/imports/{job['id']}", headers=h)
    assert again.status_code == 200 and again.json()["imported"] == 3
    csv_err = client.get(f"{API}/imports/{job['id']}/errors.csv", headers=h)
    assert csv_err.content.startswith(b"\xef\xbb\xbf") and b"row,error" in csv_err.content
    assert client.get(f"{API}/imports/00000000-0000-0000-0000-000000000000", headers=h).status_code == 404


def test_mapping_validation_and_limits(db, client, monkeypatch):
    _patch(monkeypatch)
    w = build_world(db)
    h = auth_headers(client, w["me"])
    r = _upload(client, h, CSV.encode(), mapping={"Title": "subject"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_MAPPING"
    r = _upload(client, h, CSV.encode(), mapping={"Nope": "subject"})
    assert r.status_code == 422
    r = _upload(client, h, CSV.encode(), mapping={"Title": "subject", "Details": "subject"})
    assert r.status_code == 422
    big = "a,b,c,d\n" + "\n".join("x,2026-10-01,y,z" for _ in range(1001))
    r = _upload(client, h, big.encode(), mapping={"a": "source_ref", "b": "received_at", "c": "institution_name", "d": "subject"})
    assert r.status_code == 413 and r.json()["error"]["code"] == "IMPORT_TOO_LARGE"
    assert client.post(f"{API}/imports", files={"file": ("a.csv", b"a,b\n1,2\n")}, data={"mapping": "{bad"}, headers=h).status_code == 422


def test_reverse_mapping_orientation_and_status_column(db, client, monkeypatch):
    _patch(monkeypatch)
    w = build_world(db)
    h = auth_headers(client, w["me"])
    csv_text = "ref,when,inst,subj,state\nQ1,2026-10-20,auto A,Hello there,UNDER_PROCESS\n"
    reverse = {"source_ref": "ref", "received_at": "when", "institution_name": "inst", "subject": "subj", "status": "state"}
    r = _upload(client, h, csv_text.encode(), mapping=reverse)
    assert r.status_code == 200 and r.json()["imported"] == 1
    db.expire_all()
    case = db.query(Case).filter(Case.source_ref == "Q1").one()
    assert case.status.value == "UNDER_PROCESS"


def test_import_end_to_end_with_real_intake_service(db, client):
    """No fakes: uses app.services.intake.create_case and the real CaseCreate schema."""
    w = build_world(db)
    make_institution(
        db, "Shrinath Institute of Engineering and Technology", ro_code="KNP", district="Kanpur Nagar",
        pincode="208017", permanent_id="1-4463974255",
    )
    h = auth_headers(client, w["me"])
    csv_text = (
        "source_channel,source_ref,received_at,institution_name,permanent_id,complainant_name,complainant_email,"
        "complainant_phone,category,subject,description,owner_bureau,ro_code,status,pending_step\n"
        "CSS,CSS-2026-99001,28/10/2026,Shrinath Institute of Engineering and Technology,1-4463974255,Meera Test,"
        "meera@mailbox.example,98100 00002,FEE_REFUND,Refund not received,Fee not refunded after withdrawal,PGRC,,"
        "AWAITING_ATR,INSTITUTION_ATR\n"
        "EMAIL,IMP-2,29/10/2026,Totally Unknown Place,,,,,,Hostel water problem,Water supply is irregular,RB,,,\n"
    )
    mapping = {c: c for c in csv_text.splitlines()[0].split(",")}
    r = _upload(client, h, csv_text.encode(), mapping=mapping)
    assert r.status_code == 200, r.text
    job = r.json()
    assert job["imported"] == 2 and job["error_count"] == 0, job
    assert job["auto_suggested"] == 1 and job["unresolved"] == 1
    db.expire_all()
    case = db.query(Case).filter(Case.source_ref == "CSS-2026-99001").one()
    assert case.status.value == "AWAITING_ATR" and case.pending_step.value == "INSTITUTION_ATR"
    assert case.institution_id is not None
