"""Oversight dashboard endpoints. All accept from,to,bureau[],ro_code[],category[],status[]."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from app.deps import CurrentUser, DbSession
from app.models.enums import Bureau, CaseCategory, CaseStatus
from app.schemas.reporting import (
    AgeingRow,
    BureauStatusRow,
    CategoryRow,
    ClockBucket,
    KpisOut,
    RegionRow,
    TopInstitutionRow,
    TrendRow,
)
from app.services import dashboard as svc

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def dashboard_filters(
    user: CurrentUser,
    from_: str | None = Query(None, alias="from", description="ISO datetime or date (IST)"),
    to: str | None = Query(None, description="ISO datetime or date (IST)"),
    bureau: list[Bureau] | None = Query(None),
    ro_code: list[str] | None = Query(None),
    category: list[CaseCategory] | None = Query(None),
    status: list[CaseStatus] | None = Query(None),
) -> svc.Filters:
    return svc.build_filters(
        user, start=from_, end=to, bureau=bureau, ro_code=ro_code, category=category, status=status
    )


Flt = Annotated[svc.Filters, Depends(dashboard_filters)]


@router.get("/kpis", response_model=KpisOut)
def get_kpis(db: DbSession, f: Flt) -> dict[str, Any]:
    return svc.kpis(db, f)


@router.get("/by-bureau", response_model=list[BureauStatusRow])
def get_by_bureau(db: DbSession, f: Flt) -> list[dict[str, Any]]:
    return svc.by_bureau(db, f)


@router.get("/by-category", response_model=list[CategoryRow])
def get_by_category(db: DbSession, f: Flt) -> list[dict[str, Any]]:
    return svc.by_category(db, f)


@router.get("/ageing", response_model=list[AgeingRow])
def get_ageing(db: DbSession, f: Flt) -> list[dict[str, Any]]:
    return svc.ageing(db, f)


@router.get("/trend", response_model=list[TrendRow])
def get_trend(
    db: DbSession, f: Flt, granularity: str = Query("month", pattern="^(month|week)$")
) -> list[dict[str, Any]]:
    return svc.trend(db, f, granularity)


@router.get("/by-region", response_model=list[RegionRow])
def get_by_region(db: DbSession, f: Flt) -> list[dict[str, Any]]:
    return svc.by_region(db, f)


@router.get("/top-institutions", response_model=list[TopInstitutionRow])
def get_top_institutions(db: DbSession, f: Flt, limit: int = Query(10, ge=1, le=50)) -> list[dict[str, Any]]:
    return svc.top_institutions(db, f, limit)


@router.get("/clocks", response_model=dict[str, ClockBucket])
def get_clocks(db: DbSession, f: Flt) -> dict[str, Any]:
    return svc.clocks_summary(db, f)
