"""Pendency report (JSON / CSV / PDF) and the weekly digest preview.

Report columns: Opening pending, Received, Disposed, Closing pending, Overdue, Avg days to dispose.
Periods are calendar months / quarters in IST.  "Overdue" is the number of cases still pending at
the end of the period that had a clock BREACHED (and not yet met) as of min(now, period end).
Closed time = disposed_at (falls back to updated_at for closed cases without it).
"""

from __future__ import annotations

import csv
import io
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from html import escape
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models.cases import Case
from app.models.clocks import CaseClock
from app.models.enums import CLOSED_STATUSES, OPEN_STATUSES, Bureau, ClockState, RelationType
from app.models.institutions import Institution
from app.models.links import CaseLink
from app.models.users import RegionalOffice, User
from app.services import clocks as clocks_svc
from app.services.dashboard import ACTIVE_LINK_STATUSES, IST, Filters

TITLE = "Pendency report"
ORG = "AICTE · Lok Sutra"
FOOTER = "Synthetic data — prototype"
COLUMNS = [
    ("opening_pending", "Opening pending"),
    ("received", "Received"),
    ("disposed", "Disposed"),
    ("closing_pending", "Closing pending"),
    ("overdue", "Overdue"),
    ("avg_days_to_dispose", "Avg days to dispose"),
]
GROUP_LABELS = {"bureau": "Bureau", "region": "Region", "institution": "Institution", "category": "Category"}
MONTH_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
QUARTER_RE = re.compile(r"^(\d{4})-Q([1-4])$", re.IGNORECASE)


@dataclass(frozen=True)
class Period:
    kind: str
    label: str
    start: datetime  # UTC, inclusive
    end: datetime  # UTC, exclusive


def _ist_midnight(y: int, m: int) -> datetime:
    return datetime(y, m, 1, tzinfo=IST).astimezone(UTC)


def resolve_period(kind: str, month: str | None, quarter: str | None, now: datetime | None = None) -> Period:
    now_ist = (now or datetime.now(UTC)).astimezone(IST)
    if kind == "monthly":
        value = month or f"{now_ist.year:04d}-{now_ist.month:02d}"
        m = MONTH_RE.match(value)
        if not m:
            raise ApiError(422, "VALIDATION_ERROR", "month must be YYYY-MM")
        y, mo = int(m.group(1)), int(m.group(2))
        ny, nm = (y + 1, 1) if mo == 12 else (y, mo + 1)
        label = datetime(y, mo, 1).strftime("%B %Y")
        return Period("monthly", label, _ist_midnight(y, mo), _ist_midnight(ny, nm))
    value = quarter or f"{now_ist.year:04d}-Q{(now_ist.month - 1) // 3 + 1}"
    q = QUARTER_RE.match(value)
    if not q:
        raise ApiError(422, "VALIDATION_ERROR", "quarter must be YYYY-Qn (n = 1..4)")
    y, n = int(q.group(1)), int(q.group(2))
    sm = (n - 1) * 3 + 1
    ey, em = (y + 1, 1) if sm + 3 > 12 else (y, sm + 3)
    months = f"{datetime(y, sm, 1):%b}–{datetime(y, sm + 2, 1):%b}"
    return Period("quarterly", f"Q{n} {y} ({months})", _ist_midnight(y, sm), _ist_midnight(ey, em))


def fmt_ist(dt: datetime) -> str:
    return dt.astimezone(IST).strftime("%d %b %Y, %H:%M IST")


@dataclass
class _StubClock:
    clock: Any
    started_at: datetime
    due_at: datetime
    paused_total_seconds: int | None
    paused_at: datetime | None
    met_at: datetime | None


def _blank() -> dict[str, Any]:
    return {"opening_pending": 0, "received": 0, "disposed": 0, "closing_pending": 0, "overdue": 0, "_days": []}


def _finish(group: str, key: str, acc: dict[str, Any]) -> dict[str, Any]:
    days = acc["_days"]
    return {
        "group": group,
        "group_key": key,
        "opening_pending": acc["opening_pending"],
        "received": acc["received"],
        "disposed": acc["disposed"],
        "closing_pending": acc["closing_pending"],
        "overdue": acc["overdue"],
        "avg_days_to_dispose": round(sum(days) / len(days), 1) if days else None,
    }


def pendency(
    session: Session,
    user: User,
    *,
    period: Period,
    group_by: str,
    filters: Filters,
    now: datetime | None = None,
) -> dict[str, Any]:
    if group_by not in GROUP_LABELS:
        raise ApiError(422, "VALIDATION_ERROR", "group_by must be bureau, region, institution or category")
    now = now or datetime.now(UTC)
    closed_at = func.coalesce(Case.disposed_at, Case.updated_at)
    region = func.coalesce(Case.owner_ro_code, Institution.ro_code)
    stmt = (
        select(
            Case.id,
            Case.received_at,
            Case.status,
            closed_at,
            Case.owner_bureau,
            Case.category,
            region,
            Institution.id,
            Institution.name,
        )
        .outerjoin(Institution, Institution.id == Case.institution_id)
        .where(
            *filters.conditions(dates=False, status=False),
            Case.received_at < period.end,
            or_(Case.status.not_in(CLOSED_STATUSES), closed_at >= period.start),
        )
    )
    rows = session.execute(stmt).all()
    ro_names = {r.code: r.name for r in session.scalars(select(RegionalOffice))}
    as_of = min(now, period.end)

    # clocks for cases that are pending at the end of the period
    pending_ids: list[Any] = []
    parsed = []
    for cid, recv, status, closed, bureau, cat, reg, inst_id, inst_name in rows:
        is_closed = status in CLOSED_STATUSES
        closed_ts = closed if is_closed else None
        pending_at_end = recv < period.end and (closed_ts is None or closed_ts >= period.end)
        if pending_at_end:
            pending_ids.append(cid)
        if group_by == "bureau":
            key, label = bureau.value, bureau.value
        elif group_by == "category":
            key, label = cat.value, cat.value.replace("_", " ").title()
        elif group_by == "region":
            key = reg or "UNASSIGNED"
            label = ro_names.get(reg, "Unassigned region") if reg else "Unassigned region"
        else:
            key = str(inst_id) if inst_id else "UNRESOLVED"
            label = inst_name or "Unresolved institution"
        parsed.append((cid, recv, closed_ts, key, label))

    breached: set[Any] = set()
    if pending_ids:
        policy = clocks_svc.load_policy(session)
        for clk in session.scalars(select(CaseClock).where(CaseClock.case_id.in_(pending_ids))):
            met = clk.met_at if clk.met_at is not None and clk.met_at <= as_of else None
            stub = _StubClock(clk.clock, clk.started_at, clk.due_at, clk.paused_total_seconds, clk.paused_at, met)
            if clocks_svc.compute_state(stub, as_of, policy).state == ClockState.BREACHED:
                breached.add(clk.case_id)

    groups: dict[str, dict[str, Any]] = defaultdict(_blank)
    labels: dict[str, str] = {}
    total = _blank()
    for cid, recv, closed_ts, key, label in parsed:
        labels[key] = label
        for acc in (groups[key], total):
            if recv < period.start and (closed_ts is None or closed_ts >= period.start):
                acc["opening_pending"] += 1
            if period.start <= recv < period.end:
                acc["received"] += 1
            if closed_ts is not None and period.start <= closed_ts < period.end:
                acc["disposed"] += 1
                acc["_days"].append(max(0.0, (closed_ts - recv).total_seconds() / 86400))
            if recv < period.end and (closed_ts is None or closed_ts >= period.end):
                acc["closing_pending"] += 1
                if cid in breached:
                    acc["overdue"] += 1
    out_rows = [_finish(labels[k], k, v) for k, v in groups.items()]
    out_rows = [r for r in out_rows if any(r[c] for c in ("opening_pending", "received", "disposed", "closing_pending"))]
    out_rows.sort(key=lambda r: (-r["closing_pending"], r["group"]))
    return {
        "title": TITLE,
        "organisation": ORG,
        "period_type": period.kind,
        "period_label": period.label,
        "period_start": period.start,
        "period_end": period.end - timedelta(microseconds=1),
        "group_by": group_by,
        "generated_at": now,
        "generated_at_ist": fmt_ist(now),
        "generated_by": f"{user.name}, {user.role.value.replace('_', ' ').title()}",
        "columns": [{"key": "group", "label": GROUP_LABELS[group_by]}]
        + [{"key": k, "label": lbl} for k, lbl in COLUMNS],
        "rows": out_rows,
        "totals": _finish("Total", "TOTAL", total),
        "footer": FOOTER,
    }


# ------------------------------------------------------------------------------------- CSV
def to_csv(report: dict[str, Any]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow([c["label"] for c in report["columns"]])
    keys = [c["key"] for c in report["columns"]]
    for r in [*report["rows"], report["totals"]]:
        w.writerow(["" if r[k] is None else r[k] for k in keys])
    return b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8")


# ------------------------------------------------------------------------------------- PDF
def to_pdf(report: dict[str, Any]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    navy = colors.HexColor("#12325E")
    grey = colors.HexColor("#5F6B7A")
    light = colors.HexColor("#E6E9EE")

    class NumberedCanvas(rl_canvas.Canvas):
        def __init__(self, *a: Any, **kw: Any) -> None:
            super().__init__(*a, **kw)
            self._saved: list[dict[str, Any]] = []

        def showPage(self) -> None:  # noqa: N802 - reportlab API
            self._saved.append(dict(self.__dict__))
            self._startPage()

        def save(self) -> None:
            n = len(self._saved)
            for state in self._saved:
                self.__dict__.update(state)
                self._chrome(n)
                super().showPage()
            super().save()

        def _chrome(self, n: int) -> None:
            w, h = A4
            self.setStrokeColor(navy)
            self.setLineWidth(1.2)
            self.line(18 * mm, h - 22 * mm, w - 18 * mm, h - 22 * mm)
            self.setFillColor(navy)
            self.setFont("Helvetica-Bold", 11)
            self.drawString(18 * mm, h - 17 * mm, f"{ORG} · {TITLE}")
            self.setFont("Helvetica", 8.5)
            self.setFillColor(grey)
            self.drawRightString(w - 18 * mm, h - 17 * mm, report["period_label"])
            self.setStrokeColor(light)
            self.setLineWidth(0.6)
            self.line(18 * mm, 16 * mm, w - 18 * mm, 16 * mm)
            self.drawString(18 * mm, 11 * mm, FOOTER)
            self.drawRightString(w - 18 * mm, 11 * mm, f"Page {self._pageNumber} of {n}")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=28 * mm, bottomMargin=22 * mm,
        title=f"{TITLE} - {report['period_label']}", author="Lok Sutra",
    )
    h1 = ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=15, textColor=navy, leading=19, spaceAfter=4)
    meta = ParagraphStyle("meta", fontName="Helvetica", fontSize=9, textColor=colors.black, leading=13)
    cell = ParagraphStyle("cell", fontName="Helvetica", fontSize=8.5, leading=10.5)
    cellb = ParagraphStyle("cellb", parent=cell, fontName="Helvetica-Bold")
    head = ParagraphStyle("head", parent=cell, fontName="Helvetica-Bold", textColor=colors.white, alignment=1)
    head_l = ParagraphStyle("headl", parent=head, alignment=0)
    gb = GROUP_LABELS[report["group_by"]]
    story: list[Any] = [
        Paragraph(f"{escape(TITLE)} by {gb.lower()}", h1),
        Paragraph(f"<b>Period:</b> {escape(report['period_label'])}", meta),
        Paragraph(f"<b>Generated at:</b> {escape(report['generated_at_ist'])}", meta),
        Paragraph(f"<b>Generated by:</b> {escape(report['generated_by'])}", meta),
        Spacer(1, 6 * mm),
    ]
    keys = [k for k, _ in COLUMNS]

    def fmt(v: Any) -> str:
        if v is None:
            return "-"
        return f"{v:,.1f}" if isinstance(v, float) else f"{v:,}"

    data: list[list[Any]] = [
        [Paragraph(gb, head_l), *[Paragraph(lbl, head) for _, lbl in COLUMNS]]
    ]
    for r in report["rows"]:
        data.append([Paragraph(escape(r["group"]), cell), *[Paragraph(fmt(r[k]), ParagraphStyle("n", parent=cell, alignment=2)) for k in keys]])
    t = report["totals"]
    data.append([Paragraph("Total", cellb), *[Paragraph(fmt(t[k]), ParagraphStyle("nb", parent=cellb, alignment=2)) for k in keys]])
    usable = A4[0] - 36 * mm
    widths = [usable * 0.34] + [usable * 0.11] * 5 + [usable * 0.11]
    table = Table(data, colWidths=widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), navy),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 1), (-1, -2), 0.4, light),
        ("LINEABOVE", (0, -1), (-1, -1), 0.9, navy),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#F2F4F7")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    table.setStyle(TableStyle(style))
    story.append(table)
    story.append(Spacer(1, 5 * mm))
    story.append(
        Paragraph(
            "Overdue counts cases still pending at period end with any policy clock breached "
            "(21-day, 72-hour or institution 7-day, each tracked separately).",
            ParagraphStyle("note", parent=meta, fontSize=8, textColor=grey),
        )
    )
    doc.build(story, canvasmaker=NumberedCanvas)
    return buf.getvalue()


# ----------------------------------------------------------------------------------- digest
def digest_html(session: Session, user: User, bureau: Bureau, now: datetime | None = None) -> str:
    """Weekly digest a bureau head would receive.  Counts and case IDs only; no complainant data."""
    now = now or datetime.now(UTC)
    week_ago = now - timedelta(days=7)
    base = Case.owner_bureau == bureau
    closed_at = func.coalesce(Case.disposed_at, Case.updated_at)
    open_n = session.scalar(select(func.count()).select_from(Case).where(base, Case.status.in_(OPEN_STATUSES))) or 0
    new_n = session.scalar(select(func.count()).select_from(Case).where(base, Case.received_at >= week_ago)) or 0
    done_n = (
        session.scalar(select(func.count()).select_from(Case).where(base, Case.status.in_(CLOSED_STATUSES), closed_at >= week_ago)) or 0
    )
    policy = clocks_svc.load_policy(session)
    q = (
        select(Case, CaseClock)
        .join(CaseClock, CaseClock.case_id == Case.id)
        .where(base, Case.status.in_(OPEN_STATUSES))
    )
    amber: set[Any] = set()
    breached: dict[Any, tuple[Case, str]] = {}
    for case, clk in session.execute(q).unique().all():
        st = clocks_svc.compute_state(clk, now, policy)
        if st.state == ClockState.AMBER:
            amber.add(case.id)
        elif st.state == ClockState.BREACHED:
            breached.setdefault(case.id, (case, st.label))
    wanted = {c.institution_id for c, _ in breached.values() if c.institution_id}
    inst_names = (
        {i.id: i.name for i in session.scalars(select(Institution).where(Institution.id.in_(wanted)))}
        if wanted
        else {}
    )
    ca_ids = select(Case.id).where(base, Case.status.in_(OPEN_STATUSES))
    alerts = (
        session.scalar(
            select(func.count(CaseLink.id)).where(
                CaseLink.status.in_(ACTIVE_LINK_STATUSES),
                CaseLink.relation != RelationType.UNRELATED,
                or_(CaseLink.case_a_id.in_(ca_ids), CaseLink.case_b_id.in_(ca_ids)),
            )
        )
        or 0
    )
    rows = "".join(
        f"<tr><td>{escape(c.display_id)}</td><td>{escape(inst_names.get(c.institution_id, 'Unresolved institution'))}</td>"
        f"<td>{escape(c.category.value.replace('_', ' ').title())}</td><td>{escape(label)}</td></tr>"
        for c, label in sorted(breached.values(), key=lambda x: x[0].received_at)[:10]
    )
    table = (
        "<table><thead><tr><th>Case</th><th>Institution</th><th>Category</th><th>Clock</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
        if rows
        else "<p>No overdue cases this week.</p>"
    )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f"<title>Weekly digest - {bureau.value}</title>"
        "<style>body{font-family:Arial,Helvetica,sans-serif;color:#1b1f24;max-width:720px;margin:24px auto;padding:0 16px}"
        "h1{font-size:18px;color:#12325E;border-bottom:2px solid #12325E;padding-bottom:6px}"
        "dl{display:grid;grid-template-columns:max-content 1fr;gap:4px 16px}dt{color:#5F6B7A}dd{margin:0;font-weight:bold}"
        "table{border-collapse:collapse;width:100%;font-size:13px}th,td{border-bottom:1px solid #d5d9df;padding:6px;text-align:left}"
        "th{background:#12325E;color:#fff}footer{margin-top:24px;font-size:12px;color:#5F6B7A}</style></head><body>"
        f"<header><h1>Weekly digest · {escape(bureau.value)} bureau</h1>"
        f"<p>Week ending {escape(fmt_ist(now))}. Prepared for the head of {escape(bureau.value)}.</p></header>"
        "<main><section><h2>Summary</h2><dl>"
        f"<dt>Open cases</dt><dd>{open_n}</dd><dt>Received this week</dt><dd>{new_n}</dd>"
        f"<dt>Disposed this week</dt><dd>{done_n}</dd><dt>Overdue by policy</dt><dd>{len(breached)}</dd>"
        f"<dt>Clocks in amber</dt><dd>{len(amber)}</dd><dt>Open coordination alerts</dt><dd>{alerts}</dd></dl></section>"
        f"<section><h2>Overdue cases (oldest first, up to 10)</h2>{table}</section></main>"
        f"<footer>Advisory summary generated for {escape(user.name)}. {escape(FOOTER)}</footer></body></html>"
    )
