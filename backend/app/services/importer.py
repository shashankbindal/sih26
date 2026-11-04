"""CSV / XLSX case import.

Pipeline: parse file -> suggest / validate column mapping -> per row build a CaseCreate and call
`app.services.intake.create_case` (backend-workflows) inside a savepoint -> collect per-row errors
(messages never echo cell values, so no PII reaches job rows or logs) -> summary counts.

mapping orientation: {file_column: lok_sutra_field}.  The reverse orientation is accepted too.
"""

from __future__ import annotations

import csv
import importlib
import io
import logging
import re
import zipfile
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from difflib import SequenceMatcher
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models.cases import Case
from app.models.enums import Bureau, CaseCategory, CaseStatus, PendingStep, Role, SourceChannel
from app.models.system import AuditLog, ImportJob
from app.models.users import RegionalOffice, User
from app.services import clocks as clocks_svc
from app.services import passport as passport_svc

log = logging.getLogger("loksutra")
IST = ZoneInfo("Asia/Kolkata")

MAX_ROWS = 1000
MAX_BYTES = 5 * 1024 * 1024
SAMPLE_ROWS = 20

TEMPLATE_HEADERS = [
    "source_channel", "source_ref", "received_at", "institution_name", "permanent_id",
    "complainant_name", "complainant_email", "complainant_phone", "category", "subject",
    "description", "owner_bureau", "ro_code", "status", "pending_step",
]
TARGET_FIELDS = list(TEMPLATE_HEADERS)

SYNONYMS: dict[str, tuple[str, ...]] = {
    "source_channel": ("channel", "source", "mode", "received via", "complaint source", "sourcechannel"),
    "source_ref": ("ref", "reference", "reference no", "ref no", "registration no", "reg no", "diary no",
                   "ticket", "ticket id", "grievance id", "docket", "complaint id", "complaint no"),
    "received_at": ("date", "received", "received on", "date received", "complaint date", "received date",
                    "date of receipt", "filed on", "date of complaint", "timestamp"),
    "institution_name": ("institution", "college", "college name", "institute", "institution name", "inst name",
                         "institute name", "name of institution", "name of college", "against"),
    "permanent_id": ("permanent id", "aicte id", "pid", "perm id", "institution id", "aicte permanent id",
                     "approval id", "permanentid"),
    "complainant_name": ("name", "complainant", "complainant name", "applicant", "applicant name", "student name",
                         "grievant"),
    "complainant_email": ("email", "e mail", "mail", "email id", "complainant email", "emailid"),
    "complainant_phone": ("phone", "mobile", "contact", "mobile no", "phone no", "contact no", "complainant phone",
                          "telephone"),
    "category": ("type", "complaint type", "nature", "nature of complaint", "issue type", "grievance type"),
    "subject": ("title", "grievance", "subject line", "heading", "issue", "summary"),
    "description": ("details", "complaint", "text", "narrative", "grievance details", "complaint details",
                    "body", "particulars", "message"),
    "owner_bureau": ("bureau", "assigned to", "dept", "department", "marked to", "forwarded to", "desk"),
    "ro_code": ("ro", "region", "regional office", "ro code", "regional office code", "rocode"),
    "status": ("case status", "current status", "state"),
    "pending_step": ("pending", "pending step", "awaiting", "next step", "pending with"),
}


def _norm_header(h: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", h.lower()).strip()


def suggest_mapping(columns: list[str]) -> dict[str, str]:
    """Header-name heuristics: exact field name, known synonym, then fuzzy match (>= 0.82)."""
    taken: set[str] = set()
    result: dict[str, str] = {}
    norm = {c: _norm_header(c) for c in columns}
    field_norm = {f: _norm_header(f) for f in TARGET_FIELDS}

    def assign(col: str, field: str) -> bool:
        if field in taken or col in result:
            return False
        taken.add(field)
        result[col] = field
        return True

    for col, n in norm.items():  # pass 1: exact field name
        for f, fn in field_norm.items():
            if n == fn and assign(col, f):
                break
    for col, n in norm.items():  # pass 2: synonyms
        if col in result:
            continue
        for f, syns in SYNONYMS.items():
            if n in syns and assign(col, f):
                break
    for col, n in norm.items():  # pass 3: fuzzy
        if col in result or not n:
            continue
        best, best_score = None, 0.0
        for f in TARGET_FIELDS:
            if f in taken:
                continue
            for cand in (field_norm[f], *SYNONYMS.get(f, ())):
                s = SequenceMatcher(None, n, cand).ratio()
                if s > best_score:
                    best, best_score = f, s
        if best and best_score >= 0.82:
            assign(col, best)
    return result


# ------------------------------------------------------------------------------------- parsing
def _decode(content: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return content.decode(enc)
        except UnicodeDecodeError:
            continue
    return content.decode("latin-1")


def _cell(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


NUL = bytes([0])


def validate_upload(filename: str, content: bytes) -> str:
    """Extension AND content sniff. Returns "csv" or "xlsx"; raises 422 UNSUPPORTED_FILE_TYPE.

    xlsx must be a zip archive with `xl/` entries; csv must be text (UTF-8, UTF-8-SIG or
    latin-1) with no NUL bytes and must not be a zip."""
    name = (filename or "").lower()
    bad = ApiError(422, "UNSUPPORTED_FILE_TYPE", "Only .csv and .xlsx files are accepted")
    if name.endswith(".xlsx"):
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                if any(n.startswith("xl/") for n in zf.namelist()):
                    return "xlsx"
        except zipfile.BadZipFile:
            pass
        raise bad
    if name.endswith(".csv"):
        if NUL in content or content[:2] == b"PK":
            raise bad
        for enc in ("utf-8-sig", "latin-1"):
            try:
                content.decode(enc)
                return "csv"
            except UnicodeDecodeError:
                continue
    raise bad


def parse_upload(filename: str, content: bytes) -> tuple[list[str], list[dict[str, str]]]:
    """Returns (columns, rows). Fully blank rows are dropped. Raises ApiError on bad/oversized files."""
    if len(content) > MAX_BYTES:
        raise ApiError(413, "IMPORT_TOO_LARGE", "File is larger than 5 MB")
    if not content.strip():
        raise ApiError(422, "EMPTY_FILE", "The file is empty")
    name = (filename or "").lower()
    kind = validate_upload(name, content)
    raw_rows: Iterable[list[str]]
    if kind == "xlsx":
        from openpyxl import load_workbook

        try:
            wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            ws = wb.worksheets[0]
            raw_rows = [[_cell(c) for c in row] for row in ws.iter_rows(values_only=True)]
        except Exception:  # noqa: BLE001 - openpyxl raises many types for corrupt files
            raise ApiError(422, "UNREADABLE_FILE", "Could not read the spreadsheet; save it as .xlsx or .csv") from None
    else:
        text = _decode(content)
        head = text.splitlines()[0] if text.splitlines() else ""
        delim = max((",", ";", "\t", "|"), key=head.count)
        raw_rows = [[c.strip() for c in row] for row in csv.reader(io.StringIO(text), delimiter=delim)]
    raw_rows = list(raw_rows)
    while raw_rows and not any(raw_rows[0]):
        raw_rows.pop(0)
    if not raw_rows:
        raise ApiError(422, "EMPTY_FILE", "The file has no header row")
    header = raw_rows[0]
    columns: list[str] = []
    for i, h in enumerate(header):
        h = h.strip() or f"column_{i + 1}"
        base, n = h, 2
        while h in columns:
            h, n = f"{base}_{n}", n + 1
        columns.append(h)
    rows: list[dict[str, str]] = []
    for r in raw_rows[1:]:
        if not any(c.strip() for c in r):
            continue
        r = (list(r) + [""] * len(columns))[: len(columns)]
        rows.append(dict(zip(columns, r, strict=True)))
        if len(rows) > MAX_ROWS:
            raise ApiError(
                413, "IMPORT_TOO_LARGE", f"Synchronous import is limited to {MAX_ROWS} rows", {"max_rows": MAX_ROWS}
            )
    return columns, rows


def template_csv() -> bytes:
    return ("﻿" + ",".join(TEMPLATE_HEADERS) + "\r\n").encode("utf-8")


def preview(filename: str, content: bytes) -> dict[str, Any]:
    columns, rows = parse_upload(filename, content)
    return {
        "filename": filename,
        "columns": columns,
        "sample_rows": rows[:SAMPLE_ROWS],
        "total_rows": len(rows),
        "suggested_mapping": suggest_mapping(columns),
        "target_fields": TARGET_FIELDS,
    }


def normalise_mapping(mapping: Any, columns: list[str]) -> dict[str, str]:
    if not isinstance(mapping, dict) or not mapping:
        raise ApiError(422, "INVALID_MAPPING", "mapping must be a JSON object {file_column: field}")
    items = {str(k): str(v) for k, v in mapping.items() if v}
    if items and all(k in TARGET_FIELDS for k in items) and not any(k in columns for k in items):
        items = {v: k for k, v in items.items()}  # reverse orientation
    for col, field in items.items():
        if col not in columns:
            raise ApiError(422, "INVALID_MAPPING", f"Column '{col[:60]}' is not in the file")
        if field not in TARGET_FIELDS:
            raise ApiError(422, "INVALID_MAPPING", f"Unknown field '{field[:60]}'", {"allowed": TARGET_FIELDS})
    fields = list(items.values())
    dupes = sorted({f for f in fields if fields.count(f) > 1})
    if dupes:
        raise ApiError(422, "INVALID_MAPPING", f"More than one column mapped to: {', '.join(dupes)}")
    missing = [f for f in ("received_at", "subject") if f not in fields]
    if "institution_name" not in fields and "permanent_id" not in fields:
        missing.append("institution_name or permanent_id")
    if missing:
        raise ApiError(422, "INVALID_MAPPING", f"Map a column to: {', '.join(missing)}", {"missing": missing})
    return items


# --------------------------------------------------------------------------------- row handling
DATE_FORMATS = (
    "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y", "%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M", "%d-%m-%Y",
    "%d.%m.%Y", "%d %b %Y", "%d %B %Y", "%d %b %Y %H:%M", "%Y/%m/%d", "%d-%b-%Y", "%d/%m/%y",
)


def parse_received_at(value: str, now: datetime) -> datetime:
    v = value.strip()
    if not v:
        raise ValueError("received_at is empty")
    dt: datetime | None = None
    try:
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        for fmt in DATE_FORMATS:
            try:
                dt = datetime.strptime(v, fmt)
                break
            except ValueError:
                continue
    if dt is None:
        raise ValueError("received_at is not a recognised date")
    dt = dt.replace(tzinfo=IST) if dt.tzinfo is None else dt
    dt = dt.astimezone(UTC)
    if dt > now + timedelta(days=1):
        raise ValueError("received_at is in the future")
    if dt.year < 2015:
        raise ValueError("received_at is implausibly old")
    return dt


def _enum(raw: str, enum: type, field: str) -> Any:
    if not raw:
        return None
    key = re.sub(r"[\s\-]+", "_", raw.strip().upper())
    try:
        return enum(key)
    except ValueError:
        raise ValueError(f"{field} is not one of the allowed values") from None


def build_row(row: dict[str, str], mapping: dict[str, str], user: User, now: datetime, ro_codes: set[str]) -> dict[str, Any]:
    """Validate one row and return {'payload': CaseCreate-shaped dict, 'status', 'pending_step'}."""
    m = {field: (row.get(col) or "").strip() for col, field in mapping.items()}
    subject = m.get("subject", "")
    description = m.get("description", "")
    if not subject and description:
        subject = description[:120]
    if len(subject) < 3:
        raise ValueError("subject is missing")
    inst_text = m.get("institution_name", "")
    perm = m.get("permanent_id", "")
    if not inst_text and not perm:
        raise ValueError("institution_name or permanent_id is required")
    if len(inst_text) > 300 or len(subject) > 400:
        raise ValueError("a text field is too long")
    received = parse_received_at(m.get("received_at", ""), now)
    channel = _enum(m.get("source_channel", ""), SourceChannel, "source_channel") or SourceChannel.CSV_IMPORT
    category = _enum(m.get("category", ""), CaseCategory, "category")
    bureau = _enum(m.get("owner_bureau", ""), Bureau, "owner_bureau")
    if bureau is None:
        bureau = user.bureau if user.bureau not in (Bureau.ADMIN,) else Bureau.PGRC
    elif bureau == Bureau.ADMIN:
        raise ValueError("owner_bureau is not one of the allowed values")
    status = _enum(m.get("status", ""), CaseStatus, "status")
    pending = _enum(m.get("pending_step", ""), PendingStep, "pending_step")
    ro = m.get("ro_code", "").upper() or None
    if ro and ro not in ro_codes:
        raise ValueError("ro_code is not a known regional office")
    email = m.get("complainant_email", "").lower() or None
    if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}", email):
        email = None
    name = m.get("complainant_name") or None
    phone = re.sub(r"[^\d+]", "", m.get("complainant_phone", "")) or None
    payload = {
        "source_channel": channel.value,
        "source_ref": m.get("source_ref") or None,
        "received_at": received,
        "institution_text_raw": inst_text or None,
        "permanent_id_raw": perm or None,
        "complainant": {
            "name": name,
            "email": email,
            "phone": phone,
            "party_type": "ANONYMOUS" if not (name or email or phone) else "OTHER",
        },
        "category": category.value if category else None,
        "subject": subject,
        "description": description or None,
        "owner_bureau": bureau.value,
        "owner_ro_code": ro,
    }
    return {"payload": payload, "status": status, "pending_step": pending}


def _intake() -> tuple[Any, Any]:
    """(create_case, CaseCreate) from backend-workflows; 501 until they exist."""
    try:
        svc = importlib.import_module("app.services.intake")
        create_case = svc.create_case
    except (ImportError, AttributeError):
        raise ApiError(501, "NOT_IMPLEMENTED", "The intake service (app.services.intake.create_case) is not available yet") from None
    for mod in ("app.schemas.intake", "app.schemas.cases", "app.schemas.case_create", "app.services.intake"):
        try:
            cls = getattr(importlib.import_module(mod), "CaseCreate", None)
        except ImportError:
            continue
        if cls is not None:
            return create_case, cls
    raise ApiError(501, "NOT_IMPLEMENTED", "The CaseCreate schema is not available yet")


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _val(x: Any) -> str:
    return str(getattr(x, "value", x))


def _apply_history(session: Session, case: Case, status: CaseStatus | None, pending: PendingStep | None, user: User, now: datetime) -> None:
    """Imported rows may carry a current status / pending step: apply it, log it, resync clocks."""
    changed: dict[str, Any] = {}
    if status is not None and status != case.status:
        changed["status"] = {"from": case.status.value, "to": status.value}
        case.status = status
        if status in (CaseStatus.DISPOSED, CaseStatus.CLOSED_NO_ACTION) and case.disposed_at is None:
            case.disposed_at = now
    if pending is not None and pending != case.pending_step:
        changed["pending_step"] = {"from": case.pending_step.value, "to": pending.value}
        case.pending_step = pending
        case.pending_since = case.pending_since or case.received_at
    if not changed:
        return
    passport_svc.append_entry(
        session,
        event="DISPOSED" if status == CaseStatus.DISPOSED else "STATUS_CHANGED",
        case_id=case.id,
        institution_id=case.institution_id,
        actor=user,
        payload={**changed, "source": "csv_import"},
    )
    session.flush()
    clocks_svc.sync_clocks_for_case(session, case, now)


def _refit(session: Session) -> None:
    """Refit the process-wide TF-IDF similarity model after an import (never fails the import)."""
    try:
        fn = importlib.import_module("app.services.caselink_runtime").refit_similarity
        fn(session)
    except (ImportError, AttributeError):
        return
    except Exception as exc:  # noqa: BLE001
        log.warning("similarity refit failed: %s", type(exc).__name__)


def run_import(session: Session, user: User, filename: str, content: bytes, mapping_in: Any) -> ImportJob:
    columns, rows = parse_upload(filename, content)
    mapping = normalise_mapping(mapping_in, columns)
    create_case, case_create_cls = _intake()
    now = datetime.now(UTC)
    ro_codes = {c for c in session.scalars(select(RegionalOffice.code))}

    job = ImportJob(
        filename=(filename or "upload")[:200], uploaded_by=user.id, mapping=mapping, total_rows=len(rows), status="RUNNING"
    )
    session.add(job)
    session.commit()  # job row exists even if the run fails part-way

    counts = {"imported": 0, "auto_suggested": 0, "needs_review": 0, "unresolved": 0, "links_found": 0}
    errors: list[dict[str, Any]] = []
    try:
        for idx, row in enumerate(rows, start=2):  # row 1 is the header
            try:
                built = build_row(row, mapping, user, now, ro_codes)
                with session.begin_nested():
                    result = create_case(session, case_create_cls(**built["payload"]), user, source_import_job_id=job.id)
                    case_obj = _get(result, "case")
                    case_id = _get(case_obj, "id")
                    if case_id is not None and (built["status"] or built["pending_step"]):
                        case = session.get(Case, case_id)
                        if case is not None:
                            _apply_history(session, case, built["status"], built["pending_step"], user, now)
            except ApiError as exc:
                errors.append({"row": idx, "message": f"{exc.message}"[:200]})
                continue
            except ValueError as exc:
                errors.append({"row": idx, "message": str(exc)[:200]})
                continue
            except Exception as exc:  # noqa: BLE001 - one bad row must not stop the file
                errors.append({"row": idx, "message": f"Row could not be saved ({type(exc).__name__})"})
                continue
            counts["imported"] += 1
            status = _val(_get(_get(result, "resolution"), "status", "UNRESOLVED"))
            if status in ("EXACT", "AUTO_SUGGESTED", "CONFIRMED"):
                counts["auto_suggested"] += 1
            elif status == "NEEDS_REVIEW":
                counts["needs_review"] += 1
            else:
                counts["unresolved"] += 1
            counts["links_found"] += len(_get(result, "links") or [])
        job.imported = counts["imported"]
        job.auto_suggested = counts["auto_suggested"]
        job.needs_review = counts["needs_review"]
        job.unresolved = counts["unresolved"]
        job.links_found = counts["links_found"]
        job.errors = errors
        job.status = "COMPLETED" if counts["imported"] or not errors else "FAILED"
        job.finished_at = datetime.now(UTC)
        session.add(
            AuditLog(
                user_id=user.id,
                method="POST",
                path="/api/v1/imports",
                entity="import_job",
                entity_id=str(job.id),
                summary=f"CSV import: {counts['imported']} of {len(rows)} rows imported, {len(errors)} errors",
            )
        )
        session.commit()
    except Exception:
        session.rollback()
        failed = session.get(ImportJob, job.id)
        if failed is not None:
            failed.status = "FAILED"
            failed.finished_at = datetime.now(UTC)
            session.commit()
        raise
    _refit(session)
    return job


def errors_csv(job: ImportJob) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(["row", "error"])
    for e in job.errors or []:
        w.writerow([e.get("row"), e.get("message")])
    return b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8")


IMPORT_ROLES = tuple(r for r in Role if r != Role.SENIOR_MGMT)
