"""Admin and demo tools. ADMIN-only, except read access to non-sensitive policy config
(thresholds, clocks, clause_labels, amber_ratio), which any authenticated user may read."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select

from app.config import get_settings
from app.deps import CurrentUser, DbSession, require_roles
from app.errors import ApiError
from app.models.cases import Case
from app.models.enums import Role
from app.models.institutions import Institution
from app.models.users import User
from app.schemas.reporting import AdminUserOut, ConfigOut, ConfigPut, PublicConfig, TamperIn
from app.services import admin_config, admin_tools
from app.services import evaluation as evaluation_svc

AdminUser = Annotated[User, Depends(require_roles(Role.ADMIN))]

router = APIRouter(prefix="/admin", tags=["admin"])
config_router = APIRouter(prefix="/config", tags=["config"])


@config_router.get("/public", response_model=PublicConfig)
def public_config(db: DbSession, _user: CurrentUser) -> dict[str, Any]:
    """Read-only policy values the UI needs (score meter, clock pills). No PII."""
    return admin_config.public_config(db)


@router.get("/config/{key}", response_model=ConfigOut)
def get_config(key: str, db: DbSession, user: CurrentUser) -> ConfigOut:
    if key not in admin_config.PUBLIC_KEYS and user.role != Role.ADMIN:
        if key not in admin_config.ALL_KEYS:
            raise ApiError(404, "NOT_FOUND", f"Unknown config key '{key}'")
        raise ApiError(
            403,
            "FORBIDDEN",
            "Your role is not permitted to perform this action",
            {"required_roles": [Role.ADMIN.value]},
        )
    value, updated_at, updated_by = admin_config.get_config(db, key)
    db.commit()  # defaults may have been inserted
    return ConfigOut(key=key, value=value, updated_at=updated_at, updated_by=updated_by)


@router.put("/config/{key}", response_model=ConfigOut)
def put_config(key: str, body: ConfigPut, request: Request, db: DbSession, admin: AdminUser) -> ConfigOut:
    value, row = admin_config.put_config(db, admin, key, body.value, path=request.url.path)
    db.commit()
    if key == "thresholds":
        evaluation_svc.clear_cache()
    return ConfigOut(key=key, value=value, updated_at=row.updated_at, updated_by=row.updated_by)


@router.post("/sweep")
def sweep(db: DbSession, admin: AdminUser) -> dict[str, Any]:
    result = admin_tools.run_sweep(db, admin)
    db.commit()
    return result


@router.post("/reset-demo")
def reset_demo(db: DbSession, admin: AdminUser) -> dict[str, Any]:
    admin_tools.require_demo_mode()
    db.close()  # release our connection/locks before the seeder truncates tables
    return admin_tools.reset_demo(admin)


@router.post("/tamper-demo")
def tamper_demo(body: TamperIn, db: DbSession, admin: AdminUser) -> dict[str, Any]:
    result = admin_tools.tamper_demo(db, admin, body.case_id)
    db.commit()
    return result


@router.get("/users", response_model=list[AdminUserOut])
def users(db: DbSession, _admin: AdminUser) -> list[AdminUserOut]:
    rows = db.scalars(select(User).order_by(User.role, User.name)).all()
    return [
        AdminUserOut(
            id=u.id,
            email=str(u.email),
            name=u.name,
            designation=u.designation,
            role=u.role.value,
            bureau=u.bureau.value,
            ro_code=u.ro_code,
            is_active=u.is_active,
        )
        for u in rows
    ]


@router.get("/demo-tools")
def demo_tools(db: DbSession, _admin: AdminUser) -> dict[str, Any]:
    from app.scheduler import scheduler_status

    settings = get_settings()
    return {
        "demo_mode": settings.demo_mode,
        "seeded_at": admin_tools.seeded_at(db),
        "counts": {
            "institutions": db.scalar(select(func.count()).select_from(Institution)) or 0,
            "cases": db.scalar(select(func.count()).select_from(Case)) or 0,
            "users": db.scalar(select(func.count()).select_from(User)) or 0,
        },
        "scheduler": scheduler_status(),
    }
