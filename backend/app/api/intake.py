"""Intake helpers: live Resolution panel (dry run), classify, paste-email parser."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.deps import DbSession, require_roles
from app.models.enums import Role
from app.models.users import User
from app.schemas.intake import (
    ClassifyRequest,
    ClassifyResult,
    ParseEmailRequest,
    ParseEmailResult,
    ResolveRequest,
    ResolveResult,
)
from app.services import intake

router = APIRouter(prefix="/intake", tags=["intake"])

INTAKE_ROLES = (
    Role.PGRC_OFFICER,
    Role.RB_OFFICER,
    Role.APPROVAL_OFFICER,
    Role.VIGILANCE_OFFICER,
    Role.RO_OFFICER,
    Role.BUREAU_HEAD,
    Role.ADMIN,
)


@router.post("/resolve", response_model=ResolveResult)
def resolve(body: ResolveRequest, db: DbSession, _user: User = Depends(require_roles(*INTAKE_ROLES))) -> ResolveResult:
    """Dry-run institution resolution + category suggestion. Nothing is stored."""
    return intake.resolve_dry_run(db, body)


@router.post("/classify", response_model=ClassifyResult)
def classify(body: ClassifyRequest, _user: User = Depends(require_roles(*INTAKE_ROLES))) -> ClassifyResult:
    return intake.classify_text(body.subject, body.description)


@router.post("/parse-email", response_model=ParseEmailResult)
def parse_email(body: ParseEmailRequest, _user: User = Depends(require_roles(*INTAKE_ROLES))) -> ParseEmailResult:
    return intake.parse_email(body.raw_text)
