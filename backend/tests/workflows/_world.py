"""Fixtures modelled on the seed-data plan scenarios A-F (synthetic)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.models import Case, CaseSourceRef, Complainant, Institution, InstitutionAlias
from app.models.enums import (
    Bureau,
    CaseCategory,
    CaseStatus,
    MatchStatus,
    PendingStep,
    Role,
    SourceChannel,
)
from app.services import clocks, passport
from app.services.normalise import mask_pii, normalise_name, normalise_text
from tests.conftest import make_institution, make_ro, make_user

NOW = datetime.now(UTC)

DEMO_A = {
    "source_channel": "CSS",
    "source_ref": "CSS-2026-88123",
    "institution_text_raw": "श्रीनाथ इंजीनियरिंग कॉलेज कानपुर",
    "permanent_id_raw": None,
    "complainant": {
        "name": "Demo Complainant",
        "email": "demo.student@mailbox.example",
        "phone": "9000000001",
        "party_type": "STUDENT",
    },
    "subject": "फीस वापस नहीं कर रहे",
    "description": (
        "Maine 2 Oct ko admission withdraw kiya, ₹85,000 fees abhi tak wapas nahi mili. "
        "College bolta hai 4 saal ki fees do tab certificate milega."
    ),
    "owner_bureau": "PGRC",
}


@dataclass
class World:
    users: dict[str, Any] = field(default_factory=dict)
    inst: dict[str, Institution] = field(default_factory=dict)
    cases: dict[str, Case] = field(default_factory=dict)


def add_case(
    db: Session,
    inst: Institution | None,
    bureau: Bureau,
    officer,
    *,
    category: CaseCategory,
    subject: str,
    description: str,
    channel: SourceChannel = SourceChannel.CSS,
    status: CaseStatus = CaseStatus.UNDER_PROCESS,
    received_days_ago: float = 5,
    pending_step: PendingStep = PendingStep.NONE,
    pending_since_days_ago: float | None = None,
    pending_action: str | None = None,
    source_ref: str | None = None,
    ro_code: str | None = None,
    party_hash: str | None = None,
    inst_text: str | None = None,
) -> Case:
    comp = Complainant(
        name="Existing Person", email="x@mailbox.example", phone="9111111111", party_hash=party_hash,
        party_type="STUDENT",
    )
    db.add(comp)
    db.flush()
    received = NOW - timedelta(days=received_days_ago)
    case = Case(
        source_channel=channel,
        source_ref=source_ref,
        received_at=received,
        institution_text_raw=inst_text or (inst.name if inst else None),
        institution_id=inst.id if inst else None,
        institution_match_status=MatchStatus.EXACT if inst else MatchStatus.UNRESOLVED,
        institution_match_score=1.0 if inst else None,
        complainant_id=comp.id,
        category=category,
        subject=subject,
        description=description,
        description_norm=normalise_text(mask_pii(description)),
        language="en",
        owner_bureau=bureau,
        owner_ro_code=ro_code,
        owner_officer_id=officer.id if officer else None,
        status=status,
        pending_step=pending_step,
        pending_since=NOW - timedelta(days=pending_since_days_ago) if pending_since_days_ago is not None else None,
        pending_action=pending_action,
    )
    db.add(case)
    db.flush()
    if source_ref:
        db.add(CaseSourceRef(channel=channel, ref=source_ref, case_id=case.id))
    clocks.start_clocks_for_case(db, case, now=NOW)
    passport.append_entry(
        db, event="RECEIVED", case_id=case.id, institution_id=case.institution_id, actor=officer,
        payload={"channel": channel.value}, created_at=received,
    )
    db.flush()
    return case


def add_alias(db: Session, inst: Institution, raw: str) -> None:
    db.add(InstitutionAlias(institution_id=inst.id, alias_raw=raw, alias_norm=normalise_name(raw).text, source="SEED"))
    db.flush()


def users(db: Session) -> dict[str, Any]:
    return {
        "pgrc": make_user(db, Role.PGRC_OFFICER, Bureau.PGRC, name="Ritu Sharma"),
        "pgrc2": make_user(db, Role.PGRC_OFFICER, Bureau.PGRC, name="Neha Gupta"),
        "pgrc_head": make_user(db, Role.BUREAU_HEAD, Bureau.PGRC, name="Anil Verma"),
        "rb": make_user(db, Role.RB_OFFICER, Bureau.RB, name="Karthik Iyer"),
        "rb_head": make_user(db, Role.BUREAU_HEAD, Bureau.RB, name="Meenakshi Rao"),
        "approval": make_user(db, Role.APPROVAL_OFFICER, Bureau.APPROVAL, name="Sandeep Kulkarni"),
        "vig": make_user(db, Role.VIGILANCE_OFFICER, Bureau.VIGILANCE, name="Farhan Qureshi"),
        "ro_knp": make_user(db, Role.RO_OFFICER, Bureau.RO, ro_code="KNP", name="Pooja Mishra"),
        "ro_bpl": make_user(db, Role.RO_OFFICER, Bureau.RO, ro_code="BPL", name="Vivek Chouhan"),
        "mgmt": make_user(db, Role.SENIOR_MGMT, Bureau.ADMIN, name="Member Secretary Office"),
        "admin": make_user(db, Role.ADMIN, Bureau.ADMIN, name="System Admin"),
    }


def build_world(db: Session) -> World:
    """Scenario A institution and its open cases (PGRC-1, PGRC-2, RB-1, RO-1) plus filler institutions."""
    w = World()
    w.users = users(db)
    u = w.users
    make_ro(db, "KNP")
    make_ro(db, "BPL")
    make_ro(db, "CHD")
    shri = make_institution(
        db, "Shrinath Institute of Engineering & Technology", ro_code="KNP", permanent_id="1-4463974255",
        district="Kanpur Nagar", state="Uttar Pradesh", pincode="208017", name_norm="shrinath institute of engineering and technology",
    )
    add_alias(db, shri, "SIET Kanpur")
    add_alias(db, shri, "Shrinath Engg College")
    w.inst["A"] = shri
    for name, district, pid, pin in (
        ("Government Engineering College Kanpur", "Kanpur Nagar", "1-4400000011", "208002"),
        ("Narmada Polytechnic", "Bhopal", "1-4400000012", "462001"),
        ("Vidyadeep College of Pharmacy", "Lucknow", "1-4400000013", "226001"),
        ("Sarvodaya Institute of Management Studies", "Dehradun", "1-4400000014", "248001"),
    ):
        make_institution(db, name, ro_code="KNP", district=district, permanent_id=pid, pincode=pin,
                         name_norm=normalise_name(name).text)

    c = w.cases
    c["PGRC-1"] = add_case(
        db, shri, Bureau.PGRC, u["pgrc2"], category=CaseCategory.FEE_REFUND, channel=SourceChannel.CSS,
        subject="Fee not refunded after withdrawal",
        description="Maine admission cancel kiya tha lekin college 85000 fees wapas nahi kar raha. 3 baar mail kiya, koi reply nahi.",
        status=CaseStatus.AWAITING_ATR, received_days_ago=16, pending_step=PendingStep.INSTITUTION_ATR,
        pending_since_days_ago=11, party_hash="other-party-1",
    )
    c["PGRC-2"] = add_case(
        db, shri, Bureau.PGRC, u["pgrc2"], category=CaseCategory.CERTIFICATE_WITHHELD, channel=SourceChannel.CPGRAMS,
        subject="Original certificates withheld",
        description="College is not returning my original 10th and 12th marksheet and certificates and demands four years fees.",
        received_days_ago=9, source_ref="DHIGH/E/2026/0034517", party_hash="parent-party-2",
    )
    c["RB-1"] = add_case(
        db, shri, Bureau.RB, u["rb"], category=CaseCategory.SCRUTINY_COMMITTEE, channel=SourceChannel.BUREAU_FILE,
        subject="Scrutiny committee review on faculty norms",
        description="Scrutiny committee to review the faculty norms: only 4 regular faculty against the approved intake of 120.",
        received_days_ago=25, pending_action="Scrutiny committee review scheduled",
    )
    c["RO-1"] = add_case(
        db, shri, Bureau.RO, u["ro_knp"], category=CaseCategory.FEE_REFUND, channel=SourceChannel.RO_REGISTER,
        subject="Status of fee refund", description="Please tell the status of my fee refund from the college.",
        status=CaseStatus.RECEIVED, received_days_ago=6, ro_code="KNP",
    )
    db.commit()
    return w
