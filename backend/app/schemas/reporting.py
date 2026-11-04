"""Response models for dashboard, reports, imports, admin and evaluation endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DeltaOut(BaseModel):
    previous: int
    change: int
    pct: float | None = None


class KpiDeltas(BaseModel):
    previous_period: dict[str, str]
    vs_prev_period: dict[str, DeltaOut]


class KpisOut(BaseModel):
    total: int
    pending: int
    under_process: int
    disposed: int
    transferred: int
    escalated: int
    overdue: int
    overdue_by_clock: dict[str, int]
    open_alerts: int
    definitions: dict[str, list[str]]
    deltas: KpiDeltas | None = None
    filters: dict[str, Any]
    as_of: str


class BureauStatusRow(BaseModel):
    model_config = ConfigDict(extra="allow")  # one integer field per case status
    bureau: str
    open: int
    total: int


class CategoryRow(BaseModel):
    category: str
    open: int
    disposed: int


class AgeingRow(BaseModel):
    bucket: str
    count: int


class TrendRow(BaseModel):
    period: str
    received: int
    disposed: int


class RegionRow(BaseModel):
    ro_code: str
    name: str
    city: str | None = None
    lat: float | None = None
    lng: float | None = None
    open: int
    overdue: int


class TopInstitutionRow(BaseModel):
    institution_id: uuid.UUID
    name: str
    permanent_id: str
    district: str | None = None
    ro_code: str | None = None
    open: int
    overdue: int
    open_alerts: int


class ClockBucket(BaseModel):
    on_track: int
    amber: int
    breached: int
    paused: int
    met: int
    total: int
    label: str
    rule: str


# ----------------------------------------------------------------------------------- reports
class ReportColumn(BaseModel):
    key: str
    label: str


class ReportRow(BaseModel):
    group: str
    group_key: str
    opening_pending: int
    received: int
    disposed: int
    closing_pending: int
    overdue: int
    avg_days_to_dispose: float | None = None


class PendencyReport(BaseModel):
    title: str
    organisation: str
    period_type: str
    period_label: str
    period_start: datetime
    period_end: datetime
    group_by: str
    generated_at: datetime
    generated_at_ist: str
    generated_by: str
    columns: list[ReportColumn]
    rows: list[ReportRow]
    totals: ReportRow
    footer: str


# ----------------------------------------------------------------------------------- imports
class ImportPreview(BaseModel):
    filename: str
    columns: list[str]
    sample_rows: list[dict[str, str]]
    total_rows: int
    suggested_mapping: dict[str, str]
    target_fields: list[str]


class ImportRowError(BaseModel):
    row: int
    message: str


class ImportJobOut(BaseModel):
    id: uuid.UUID
    filename: str
    status: str
    mapping: dict[str, str]
    total_rows: int
    imported: int
    auto_suggested: int
    needs_review: int
    unresolved: int
    links_found: int
    error_count: int
    errors: list[ImportRowError]
    created_at: datetime
    finished_at: datetime | None = None


# ------------------------------------------------------------------------------------- admin
class ConfigOut(BaseModel):
    key: str
    value: Any
    updated_at: datetime | None = None
    updated_by: uuid.UUID | None = None


class ConfigPut(BaseModel):
    value: Any


class PublicConfig(BaseModel):
    thresholds: Any
    clocks: Any
    clause_labels: Any
    amber_ratio: Any


class AdminUserOut(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    designation: str | None = None
    role: str
    bureau: str
    ro_code: str | None = None
    is_active: bool


class TamperIn(BaseModel):
    case_id: uuid.UUID


class RiskFactor(BaseModel):
    factor: str
    effect: str = Field(description="raises | lowers")


class RiskOut(BaseModel):
    case_id: uuid.UUID
    level: str
    probability: float | None = None
    factors: list[RiskFactor] = []
    note: str | None = None
    trained_on: int = 0
