"""Small fixture world shared by the reporting tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models.enums import (
    Bureau,
    CaseCategory,
    CaseStatus,
    LinkStatus,
    PendingStep,
    RelationType,
    Role,
    SourceChannel,
)
from tests.conftest import make_case, make_institution, make_link, make_user

NOW = datetime.now(UTC)


def build_world(db):
    knp = make_institution(db, "Shrinath Engineering College", ro_code="KNP", district="Kanpur")
    bpl = make_institution(db, "Narmada Polytechnic", ro_code="BPL", district="Bhopal", state="Madhya Pradesh")
    admin = make_user(db, Role.ADMIN, Bureau.ADMIN)
    me = make_user(db, Role.PGRC_OFFICER, Bureau.PGRC)
    ro = make_user(db, Role.RO_OFFICER, Bureau.RO, ro_code="KNP")
    head = make_user(db, Role.BUREAU_HEAD, Bureau.PGRC)
    mgmt = make_user(db, Role.SENIOR_MGMT, Bureau.ADMIN)
    cs = {}
    cs["css_amber"] = make_case(
        db, knp, Bureau.PGRC, owner_officer=me, channel=SourceChannel.CSS,
        received_at=NOW - timedelta(hours=55), category=CaseCategory.FEE_REFUND, start_clocks=True,
    )
    cs["cpgrams_breached"] = make_case(
        db, knp, Bureau.RB, channel=SourceChannel.CPGRAMS, received_at=NOW - timedelta(days=30),
        category=CaseCategory.FACULTY_SHORTAGE, start_clocks=True, source_ref="DHIGH/E/2026/0012345",
    )
    cs["refund_breached"] = make_case(
        db, knp, Bureau.PGRC, owner_officer=me, channel=SourceChannel.EMAIL, category=CaseCategory.FEE_REFUND,
        status=CaseStatus.AWAITING_ATR, pending_step=PendingStep.INSTITUTION_ATR,
        pending_since=NOW - timedelta(days=12), start_clocks=True, received_at=NOW - timedelta(days=14),
    )
    cs["ro_case"] = make_case(
        db, bpl, Bureau.RO, owner_ro_code="BPL", channel=SourceChannel.RO_REGISTER,
        category=CaseCategory.INFRASTRUCTURE, received_at=NOW - timedelta(days=5),
        status=CaseStatus.RECEIVED,
    )
    cs["knp_ro_case"] = make_case(
        db, knp, Bureau.RO, owner_ro_code="KNP", channel=SourceChannel.RO_REGISTER,
        category=CaseCategory.SCHOLARSHIP, received_at=NOW - timedelta(days=100),
    )
    cs["disposed_recent"] = make_case(
        db, knp, Bureau.PGRC, channel=SourceChannel.CPGRAMS, category=CaseCategory.CERTIFICATE_WITHHELD,
        status=CaseStatus.DISPOSED, received_at=NOW - timedelta(days=40), start_clocks=True,
    )
    cs["disposed_recent"].disposed_at = NOW - timedelta(days=10)
    cs["old_open"] = make_case(
        db, bpl, Bureau.VIGILANCE, channel=SourceChannel.BUREAU_FILE, category=CaseCategory.RAGGING,
        received_at=NOW - timedelta(days=200), status=CaseStatus.ESCALATED,
    )
    cs["closed_no_action"] = make_case(
        db, bpl, Bureau.PGRC, category=CaseCategory.OTHER, status=CaseStatus.CLOSED_NO_ACTION,
        received_at=NOW - timedelta(days=70),
    )
    cs["closed_no_action"].disposed_at = NOW - timedelta(days=60)
    cs["transferred"] = make_case(
        db, knp, Bureau.APPROVAL, category=CaseCategory.SCRUTINY_COMMITTEE, status=CaseStatus.TRANSFERRED,
        received_at=NOW - timedelta(days=30),
    )
    db.commit()
    make_link(db, cs["css_amber"], cs["refund_breached"], RelationType.RELATED, LinkStatus.SUGGESTED)
    make_link(db, cs["css_amber"], cs["disposed_recent"], RelationType.DUPLICATE, LinkStatus.SUGGESTED)
    make_link(db, cs["knp_ro_case"], cs["transferred"], RelationType.CONFLICTING, LinkStatus.CONFIRMED)
    return {"knp": knp, "bpl": bpl, "admin": admin, "me": me, "ro": ro, "head": head, "mgmt": mgmt, "cases": cs}
