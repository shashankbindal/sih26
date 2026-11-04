"""Scripted demo scenarios A-F.

Everything here is synthetic. Institutions are fixed; case dates are relative to the seed ANCHOR.
Scenario cases are addressed by `is_seed_label.scenario_key`.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.seed.spec import CaseSpec

IST = timezone(timedelta(hours=5, minutes=30))
DATA_DIR = Path(__file__).resolve().parent / "data"

# Scenario institutions. `key` is how the rest of the seed refers to them.
SCENARIO_INSTITUTIONS: list[dict[str, Any]] = [
    {"key": "A", "prefix": "", "token": "Shrinath", "type_phrase": "Institute of Engineering & Technology",
     "district": "Kanpur Nagar", "pincode": "208017", "pid": "1-4463974255", "city_in_name": False,
     "aliases": ["SIET Kanpur", "Shrinath Engg College"]},
    {"key": "C", "prefix": "", "token": "Devbhoomi", "type_phrase": "College of Engineering",
     "district": "Dehradun", "pincode": "248001", "pid": "1-4471203398", "city_in_name": False,
     "aliases": ["Devbhoomi Engg College"]},
    {"key": "D", "prefix": "", "token": "Gyanodaya", "type_phrase": "Institute of Technology & Management",
     "district": "Bhopal", "pincode": "462003", "pid": "1-4458812074", "city_in_name": False,
     "aliases": ["GITM Bhopal"]},
    {"key": "E1", "prefix": "Shri", "token": "Ram", "type_phrase": "College of Engineering",
     "district": "Lucknow", "pincode": "226010", "pid": "1-4440019921", "city_in_name": True,
     "aliases": []},
    {"key": "E2", "prefix": "Shri", "token": "Ram", "type_phrase": "Institute of Technology",
     "district": "Lucknow", "pincode": "226021", "pid": "1-4440019987", "city_in_name": True,
     "inst_type": "Engineering", "aliases": []},
]

DEMO_INPUTS: dict[str, dict[str, Any]] = {
    "A": {
        "label": "Scenario A - Hindi CSS complaint, no Permanent ID (Shrinath)",
        "payload": {
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
            "category": None,
            "subject": "फीस वापस नहीं कर रहे",
            "description": (
                "Maine 2 Oct ko admission withdraw kiya, ₹85,000 fees abhi tak wapas nahi mili. "
                "College bolta hai 4 saal ki fees do tab certificate milega."
            ),
            "owner_bureau": "PGRC",
            "owner_ro_code": None,
        },
        "expected": [
            "Resolves to Shrinath Institute of Engineering & Technology, score >= 0.92 (AUTO_SUGGESTED)",
            "Reasons include Hindi to English transliteration and district Kanpur",
            "Category suggestion FEE_REFUND",
            "Link to PGRC-1: RELATED; link to RO-1: RELATED (coordination required)",
            "RB-1 (scrutiny on faculty norms): UNRELATED, no alert",
        ],
    },
    "E": {
        "label": "Scenario E - near-twin trap (Shri Ram, Lucknow)",
        "payload": {
            "source_channel": "CSS",
            "source_ref": "CSS-2026-88124",
            "institution_text_raw": "Shri Ram Engg College Lucknow",
            "permanent_id_raw": None,
            "complainant": {
                "name": "Demo Complainant Two",
                "email": "demo.parent@mailbox.example",
                "phone": "9000000002",
                "party_type": "PARENT",
            },
            "category": None,
            "subject": "Original certificates not returned",
            "description": (
                "The college is not returning my son's original certificates after he left the "
                "B.Tech course in the second semester."
            ),
            "owner_bureau": "PGRC",
            "owner_ro_code": None,
        },
        "expected": [
            "NEEDS_REVIEW with reason 'Two similar institutions in Lucknow'",
            "Both Shri Ram candidates shown side by side; confirming one saves an alias",
            "Same text entered again resolves EXACT via the alias",
        ],
    },
}


def write_demo_inputs(path: Path | None = None) -> Path:
    path = path or DATA_DIR / "demo_inputs.json"
    path.write_text(json.dumps(DEMO_INPUTS, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def fmt_date(dt: datetime) -> str:
    return dt.astimezone(IST).strftime("%d %b %Y")


def scenario_specs(anchor: datetime, inst: dict[str, Any]) -> list[CaseSpec]:
    """Scenario cases. `inst` maps scenario institution key -> institution dict (with `id`)."""

    def ago(days: float) -> datetime:
        return anchor - timedelta(days=days)

    a, c, d = inst["A"]["id"], inst["C"]["id"], inst["D"]["id"]
    a_name = "Shrinath Institute of Engineering & Technology"
    specs: list[CaseSpec] = []

    specs.append(CaseSpec(
        key="A-PGRC-1", bureau="PGRC", channel="CSS", category="FEE_REFUND", inst_id=a,
        received_at=ago(16), status="AWAITING_ATR", pending_step="INSTITUTION_ATR",
        pending_since=ago(11), pending_action="ATR called from institution",
        owner_email="pgrc.officer@demo.loksutra.in", fixed=True, lang="en", party_key="A-P1",
        subject="Refund of fee after admission withdrawal",
        description=("I withdrew my admission to the B.Tech programme on 28 Sep, before the classes "
                     "started. The institute has not refunded the fee of ₹72,000 so far and says "
                     "the fee is non-refundable. I have written to the accounts office three times."),
        source_ref="CSS-2026-71042", inst_text=f"{a_name}, Kanpur Nagar", pid_mode="exact",
        first_reply_hours=20, groups={"related": "R-A"}))
    specs.append(CaseSpec(
        key="A-PGRC-2", bureau="PGRC", channel="CPGRAMS", category="CERTIFICATE_WITHHELD", inst_id=a,
        received_at=ago(9), status="UNDER_PROCESS", owner_email="pgrc.officer@demo.loksutra.in",
        fixed=True, lang="en", party_key="A-P2", source_ref="DHIGH/E/2026/0034517",
        subject="Original certificates withheld by college",
        description=("The college is withholding my original Class 10 and Class 12 marksheets and is "
                     "demanding the fees for all four years before releasing them."),
        inst_text="Shrinath Engg College, Kanpur", pid_mode="missing", first_reply_hours=30,
        groups={"dup": "D-F"}))
    specs.append(CaseSpec(
        key="A-RB-1", bureau="RB", channel="BUREAU_FILE", category="SCRUTINY_COMMITTEE", inst_id=a,
        received_at=ago(25), status="UNDER_PROCESS", pending_action="Scrutiny committee review scheduled",
        owner_email="rb.officer@demo.loksutra.in", fixed=True, lang="en", party_key="A-B1",
        party_type="OTHER", source_ref="RB/F/2026/0214",
        subject="Scrutiny of faculty norms, Mechanical department",
        description=("Scrutiny committee to review compliance of the Mechanical department with the "
                     "faculty norms. The institute has submitted its deficiency reply; committee review "
                     "of the faculty cadre ratio is scheduled."),
        inst_text=a_name, pid_mode="exact", first_reply_hours=26))
    specs.append(CaseSpec(
        key="A-RO-1", bureau="RO", channel="RO_REGISTER", category="FEE_REFUND", inst_id=a,
        received_at=ago(6), status="RECEIVED", owner_email="ro.kanpur@demo.loksutra.in", ro_code="KNP",
        fixed=True, lang="en", party_key="A-R1", source_ref="ROREG/KNP/2026/0178",
        subject="Status of fee refund",
        description="Status of my fee refund please. I withdrew admission last month.",
        inst_text="Shrinath Institute of Engineering and Technology, Kanpur", pid_mode="missing",
        groups={"related": "R-A"}))
    specs.append(CaseSpec(
        key="A-HIST-1", bureau="PGRC", channel="CSS", category="RAGGING", inst_id=a,
        received_at=ago(230), status="DISPOSED", disposed_at=ago(200),
        owner_email="pgrc.officer2@demo.loksutra.in", fixed=True, lang="en", party_key="A-H1",
        first_reply_hours=14, pid_mode="exact", inst_text=a_name))
    specs.append(CaseSpec(
        key="A-HIST-2", bureau="PGRC", channel="CPGRAMS", category="SCHOLARSHIP", inst_id=a,
        received_at=ago(168), status="DISPOSED", disposed_at=ago(150),
        owner_email="pgrc.officer@demo.loksutra.in", fixed=True, lang="en", party_key="A-H2",
        pid_mode="missing"))
    specs.append(CaseSpec(
        key="A-HIST-3", bureau="RB", channel="BUREAU_FILE", category="FACULTY_SHORTAGE", inst_id=a,
        received_at=ago(140), status="DISPOSED", disposed_at=ago(100),
        owner_email="rb.officer@demo.loksutra.in", fixed=True, lang="en", party_key="A-H3",
        party_type="OTHER", pid_mode="exact"))
    ref_line = ("Please refer to my earlier grievance DHIGH/E/2026/0034517 already registered on "
                "CPGRAMS. I am sending this as a reminder by email.")
    specs.append(CaseSpec(
        key="A-EMAIL-DUP", bureau="PGRC", channel="EMAIL", category="CERTIFICATE_WITHHELD", inst_id=a,
        received_at=ago(3), status="RECEIVED", owner_email="pgrc.officer@demo.loksutra.in", fixed=True,
        lang="en", party_key="A-P2", source_ref="EML-2026-000412",
        subject="Reminder: original certificates still withheld",
        description=ref_line + " The college is still holding my original certificates.",
        inst_text="Shrinath Institute of Engineering and Technology, Kanpur", pid_mode="missing",
        groups={"dup": "D-F"}))

    show_cause_at, due_at = ago(3), anchor + timedelta(days=12)
    specs.append(CaseSpec(
        key="C-RB", bureau="RB", channel="BUREAU_FILE", category="FACULTY_SHORTAGE", inst_id=c,
        received_at=ago(20), status="UNDER_PROCESS", pending_step="SHOW_CAUSE_REPLY",
        pending_since=show_cause_at,
        pending_action=f"Show-cause notice issued {fmt_date(show_cause_at)}; reply due {fmt_date(due_at)}",
        owner_email="rb.officer@demo.loksutra.in", fixed=True, lang="en", party_key="C-B1",
        party_type="OTHER", source_ref="RB/F/2026/0231",
        subject="Faculty shortage and unpaid faculty salary, Mechanical department",
        description=("Only 4 regular faculty are available in the Mechanical department against the "
                     "approved intake of 120. Show-cause issued; the institute is asked to regularise "
                     "faculty appointments and clear the faculty salary arrears."),
        inst_text="Devbhoomi College of Engineering, Dehradun", pid_mode="exact", first_reply_hours=22,
        groups={"conflict": "C-C"}))
    hearing_at = anchor + timedelta(days=2)
    specs.append(CaseSpec(
        key="C-PGRC", bureau="PGRC", channel="CPGRAMS", category="SERVICE_MATTER", inst_id=c,
        received_at=ago(10), status="UNDER_PROCESS", pending_step="REFUND_FOLLOWUP",
        pending_since=ago(6),
        pending_action=("Negotiation with institution on faculty salary arrears; hearing scheduled "
                        f"{fmt_date(hearing_at)}"),
        owner_email="pgrc.officer@demo.loksutra.in", fixed=True, lang="en", party_key="C-P1",
        party_type="FACULTY", source_ref="DHIGH/E/2026/0035120",
        subject="Faculty salary not paid for 4 months",
        description=("Faculty salary has not been paid for 4 months in the Mechanical department. The "
                     "management says the college has no funds, but faculty appointments and admissions "
                     "continue as usual."),
        inst_text="Devbhoomi College of Engineering, Dehradun", pid_mode="missing", first_reply_hours=40,
        groups={"conflict": "C-C"}))

    specs.append(CaseSpec(
        key="D-PGRC", bureau="PGRC", channel="CSS", category="SCHOLARSHIP", inst_id=d,
        received_at=ago(12), status="UNDER_PROCESS", owner_email="pgrc.officer2@demo.loksutra.in",
        fixed=True, lang="en", party_key="D-P1", source_ref="CSS-2026-73310",
        subject="Post-matric scholarship not credited",
        description=("My post-matric scholarship for the last academic year has not been credited to my "
                     "account. The college says the verification is pending at the institute level."),
        inst_text="Gyanodaya Institute of Technology & Management, Bhopal", pid_mode="missing",
        first_reply_hours=30, groups={"negative": "N-D"}))
    specs.append(CaseSpec(
        key="D-RO", bureau="RO", channel="RO_REGISTER", category="INFRASTRUCTURE", inst_id=d,
        received_at=ago(4), status="RECEIVED", owner_email="ro.bhopal@demo.loksutra.in", ro_code="BPL",
        fixed=True, lang="en", party_key="D-R1", party_type="OTHER", source_ref="ROREG/BPL/2026/0091",
        subject="Computer lab systems not working",
        description="The computer lab has 20 working systems for 120 students.",
        inst_text="Gyanodaya Institute of Technology and Management, Bhopal", pid_mode="exact",
        groups={"negative": "N-D"}))
    return specs


def new_uuid(rng: Any) -> uuid.UUID:
    return uuid.UUID(int=rng.getrandbits(128), version=4)
