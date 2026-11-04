"""Reports: pendency (JSON/CSV/PDF) and the weekly digest preview. Aggregates only, no PII."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Response
from fastapi.responses import HTMLResponse

from app.deps import CurrentUser, DbSession
from app.models.enums import Bureau, CaseCategory
from app.schemas.reporting import PendencyReport
from app.services import reports as svc
from app.services.dashboard import build_filters

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/pendency", response_model=PendencyReport)
def pendency(
    db: DbSession,
    user: CurrentUser,
    period: str = Query("monthly", pattern="^(monthly|quarterly)$"),
    month: str | None = Query(None, description="YYYY-MM (monthly)"),
    quarter: str | None = Query(None, description="YYYY-Qn (quarterly, calendar quarters)"),
    group_by: str = Query("bureau", pattern="^(bureau|region|institution|category)$"),
    format: str = Query("json", pattern="^(json|csv|pdf)$"),
    bureau: list[Bureau] | None = Query(None),
    ro_code: list[str] | None = Query(None),
    category: list[CaseCategory] | None = Query(None),
) -> Any:
    p = svc.resolve_period(period, month, quarter)
    f = build_filters(user, bureau=bureau, ro_code=ro_code, category=category)
    report = svc.pendency(db, user, period=p, group_by=group_by, filters=f)
    slug = (month or quarter or p.label).replace(" ", "_").replace("(", "").replace(")", "")
    slug = "".join(ch for ch in slug if ch.isalnum() or ch in "-_")
    name = f"pendency_{slug}_{group_by}"
    if format == "csv":
        return Response(
            svc.to_csv(report),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{name}.csv"'},
        )
    if format == "pdf":
        return Response(
            svc.to_pdf(report),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{name}.pdf"'},
        )
    return report


@router.get("/digest-preview", response_class=HTMLResponse)
def digest_preview(
    db: DbSession, user: CurrentUser, bureau: Bureau | None = Query(None)
) -> HTMLResponse:
    target = bureau or (user.bureau if user.bureau != Bureau.ADMIN else Bureau.PGRC)
    return HTMLResponse(svc.digest_html(db, user, target))
