"""Test fixtures: dedicated `loksutra_test` database, migrated via Alembic once per session,
truncated before every test. Factory functions build small fixtures (users of each role,
institutions, cases, passport chains)."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from itertools import count
from pathlib import Path

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/loksutra_test"
)
# Must be set before any app module reads settings.
os.environ["DATABASE_URL"] = TEST_DB_URL
os.environ["DEMO_MODE"] = "true"
os.environ["BCRYPT_ROUNDS"] = "4"
os.environ["JWT_SECRET"] = "test-secret-test-secret-test-secret-123"

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db import SessionLocal, get_engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    Case,
    CaseClock,
    CaseLink,
    Complainant,
    Institution,
    RegionalOffice,
    User,
)
from app.models.enums import (  # noqa: E402
    Bureau,
    CaseCategory,
    CaseStatus,
    ClockType,
    LinkStatus,
    MatchStatus,
    PendingStep,
    RelationType,
    Role,
    SourceChannel,
)
from app.services import clocks, passport  # noqa: E402
from app.services.auth import hash_password  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "Demo@2026"


@pytest.fixture(scope="session", autouse=True)
def _schema() -> Iterator[None]:
    admin = create_engine(TEST_DB_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    admin.dispose()
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(autouse=True)
def _clean(_schema: None) -> Iterator[None]:
    with get_engine().begin() as conn:
        names = conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename<>'alembic_version'")
        ).scalars()
        conn.execute(text("TRUNCATE " + ", ".join(f'"{n}"' for n in names) + " RESTART IDENTITY CASCADE"))
        conn.execute(text("ALTER SEQUENCE display_id_seq RESTART WITH 1"))
    yield


@pytest.fixture
def db() -> Iterator[Session]:
    session = SessionLocal()
    clocks.ensure_default_policy_config(session)
    session.commit()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------- factories
_seq = count(1)


def make_ro(db: Session, code: str = "KNP", name: str | None = None) -> RegionalOffice:
    ro = db.get(RegionalOffice, code)
    if ro is None:
        ro = RegionalOffice(code=code, name=name or f"{code} Regional Office", city=code, states=[])
        db.add(ro)
        db.flush()
    return ro


def make_user(
    db: Session,
    role: Role = Role.PGRC_OFFICER,
    bureau: Bureau = Bureau.PGRC,
    ro_code: str | None = None,
    email: str | None = None,
    name: str | None = None,
) -> User:
    if ro_code:
        make_ro(db, ro_code)
    n = next(_seq)
    user = User(
        email=email or f"user{n}.{role.value.lower()}@demo.loksutra.in",
        name=name or f"Test {role.value} {n}",
        designation="Section Officer",
        role=role,
        bureau=bureau,
        ro_code=ro_code,
        password_hash=hash_password(PASSWORD),
        is_active=True,
    )
    db.add(user)
    db.commit()
    return user


def make_institution(
    db: Session, name: str = "Sunrise Institute of Technology", ro_code: str = "KNP", **kw
) -> Institution:
    make_ro(db, ro_code)
    n = next(_seq)
    inst = Institution(
        permanent_id=kw.pop("permanent_id", f"1-44{n:09d}"),
        name=name,
        name_norm=kw.pop("name_norm", name.lower()),
        inst_type=kw.pop("inst_type", "Engineering"),
        district=kw.pop("district", "Kanpur"),
        state=kw.pop("state", "Uttar Pradesh"),
        pincode=kw.pop("pincode", "208001"),
        ro_code=ro_code,
        approval_status=kw.pop("approval_status", "APPROVED"),
        **kw,
    )
    db.add(inst)
    db.commit()
    return inst


def make_case(
    db: Session,
    institution: Institution | None,
    owner_bureau: Bureau = Bureau.PGRC,
    *,
    owner_officer: User | None = None,
    owner_ro_code: str | None = None,
    status: CaseStatus = CaseStatus.UNDER_PROCESS,
    channel: SourceChannel = SourceChannel.CSS,
    category: CaseCategory = CaseCategory.FEE_REFUND,
    received_at: datetime | None = None,
    subject: str = "Fee not refunded after withdrawal",
    pending_step: PendingStep = PendingStep.NONE,
    pending_since: datetime | None = None,
    source_ref: str | None = None,
    start_clocks: bool = False,
    with_passport: bool = False,
    now: datetime | None = None,
) -> Case:
    n = next(_seq)
    comp = Complainant(
        name=f"Asha Verma {n}",
        email=f"asha{n}@example.test",
        phone=f"98000{n:05d}",
        party_hash=f"hash{n}",
        party_type="STUDENT",
    )
    db.add(comp)
    db.flush()
    case = Case(
        source_channel=channel,
        source_ref=source_ref or f"REF-{n:05d}",
        received_at=received_at or datetime.now(UTC) - timedelta(days=2),
        institution_text_raw=institution.name if institution else "Unknown college",
        institution_id=institution.id if institution else None,
        institution_match_status=MatchStatus.EXACT if institution else MatchStatus.UNRESOLVED,
        complainant_id=comp.id,
        category=category,
        subject=subject,
        description=f"Detailed grievance text {n}",
        description_norm=f"detailed grievance text {n}",
        language="en",
        owner_bureau=owner_bureau,
        owner_ro_code=owner_ro_code,
        owner_officer_id=owner_officer.id if owner_officer else None,
        status=status,
        pending_step=pending_step,
        pending_since=pending_since,
    )
    db.add(case)
    db.flush()
    if start_clocks:
        clocks.start_clocks_for_case(db, case, now=now)
    if with_passport:
        passport.append_entry(
            db,
            event="RECEIVED",
            case_id=case.id,
            institution_id=case.institution_id,
            actor=owner_officer,
            payload={"channel": channel.value},
        )
    db.commit()
    return case


def make_link(
    db: Session,
    a: Case,
    b: Case,
    relation: RelationType = RelationType.RELATED,
    status: LinkStatus = LinkStatus.SUGGESTED,
    score: float = 0.71,
) -> CaseLink:
    lo, hi = sorted([a.id, b.id], key=lambda u: u.bytes)
    link = CaseLink(
        case_a_id=lo,
        case_b_id=hi,
        relation=relation,
        score=score,
        reasons=["same institution", "related subject"],
        status=status,
    )
    db.add(link)
    db.commit()
    return link


def auth_headers(client: TestClient, user: User) -> dict[str, str]:
    r = client.post("/api/v1/auth/login", json={"email": user.email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()


__all__ = [
    "ClockType",
    "CaseClock",
    "auth_headers",
    "make_case",
    "make_institution",
    "make_link",
    "make_ro",
    "make_user",
    "new_uuid",
]
