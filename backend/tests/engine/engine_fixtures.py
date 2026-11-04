"""Synthetic fixtures mirroring the seed-data plan section 4, plus filler institutions.

Names, IDs and aliases of the scripted institutions are exactly those in the spec.  Fillers are
generated deterministically (seed 26264) from invented name parts and deliberately include
similar-sounding names ("Shreenath", "Srinath", "Shri Natha", "Sri Ram") in OTHER districts so the
matcher has something to be fooled by.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

from app.services.caselink import AliasRecord, CaseRecord, InstitutionRecord
from app.services.normalise import normalise_name, normalise_text

ANCHOR = datetime(2026, 11, 1, 9, 30, tzinfo=UTC)

SHRINATH = "inst-shrinath"
GEC_KANPUR = "inst-gec-kanpur"
SHRI_RAM_COE = "inst-shriram-coe"
SHRI_RAM_IOT = "inst-shriram-iot"
DEVBHOOMI = "inst-devbhoomi"
GYANODAYA = "inst-gyanodaya"


def _inst(iid: str, name: str, pid: str, district: str, state: str, pin: str, ro: str,
          domain: str | None = None) -> InstitutionRecord:
    return InstitutionRecord(
        id=iid, name=name, permanent_id=pid, name_norm=normalise_name(name).text,
        district=district, state=state, pincode=pin, ro_code=ro, email_domain=domain,
    )


def scripted_institutions() -> list[InstitutionRecord]:
    return [
        _inst(SHRINATH, "Shrinath Institute of Engineering & Technology", "1-4463974255",
              "Kanpur Nagar", "Uttar Pradesh", "208017", "KNP", "siet-kanpur.example.in"),
        _inst(GEC_KANPUR, "Government Engineering College, Kanpur", "1-4400100011",
              "Kanpur Nagar", "Uttar Pradesh", "208024", "KNP"),
        _inst(SHRI_RAM_COE, "Shri Ram College of Engineering, Lucknow", "1-4440019921",
              "Lucknow", "Uttar Pradesh", "226010", "KNP"),
        _inst(SHRI_RAM_IOT, "Shri Ram Institute of Technology, Lucknow", "1-4440019987",
              "Lucknow", "Uttar Pradesh", "226021", "KNP"),
        _inst(DEVBHOOMI, "Devbhoomi College of Engineering", "1-4471203398",
              "Dehradun", "Uttarakhand", "248001", "CHD"),
        _inst(GYANODAYA, "Gyanodaya Institute of Technology & Management", "1-4458812074",
              "Bhopal", "Madhya Pradesh", "462001", "BPL"),
    ]


def scripted_aliases() -> list[AliasRecord]:
    return [
        AliasRecord(SHRINATH, normalise_name("SIET Kanpur").text, "SIET Kanpur", "SEED"),
        AliasRecord(SHRINATH, normalise_name("Shrinath Engg College").text,
                    "Shrinath Engg College", "SEED"),
    ]


_LEADS = [
    "Aravali", "Bhagirath", "Chandragupt", "Dhruv", "Ekalavya", "Falguni", "Gargi", "Haldighati",
    "Ishwar", "Jhelum", "Kaveri", "Lohit", "Mandakini", "Narmada", "Odisha Central", "Panchsheel",
    "Rajarshi", "Saraswati", "Tapovan", "Udayagiri", "Vindhya", "Yamuna", "Zorawar", "Ambika",
]
_SIMILAR = [  # similar-sounding names, always placed outside Kanpur Nagar / Lucknow
    ("Shreenath Institute of Pharmacy", "Jaipur"),
    ("Srinath College of Management", "Patna"),
    ("Shri Natha Polytechnic", "Kanpur Nagar"),
    ("Sri Ram Institute of Management", "Jaipur"),
    ("Shri Krishna Institute of Technology", "Kanpur Nagar"),
    ("Government Polytechnic", "Kanpur Nagar"),
    ("Government Engineering College", "Bhopal"),
]
_TAILS = ["Vidya", "Bharti", "Mandal", "Sansthan", "Kendra", "Pratishthan", "Vihar"]
_TYPES = ["Institute of Technology", "College of Engineering", "Polytechnic",
          "Institute of Management", "College of Pharmacy", "Institute of Engineering and Technology"]
_DISTRICTS = [
    ("Jaipur", "Rajasthan", "302001"), ("Patna", "Bihar", "800001"),
    ("Nagpur", "Maharashtra", "440001"), ("Pune", "Maharashtra", "411001"),
    ("Indore", "Madhya Pradesh", "452001"), ("Varanasi", "Uttar Pradesh", "221001"),
    ("Agra", "Uttar Pradesh", "282001"), ("Meerut", "Uttar Pradesh", "250001"),
    ("Ranchi", "Jharkhand", "834001"), ("Raipur", "Chhattisgarh", "492001"),
    ("Bhopal", "Madhya Pradesh", "462003"), ("Dehradun", "Uttarakhand", "248005"),
]
_PIN = {"Kanpur Nagar": "208001", "Lucknow": "226001", "Bhopal": "462003", "Jaipur": "302001",
        "Patna": "800001"}


def filler_institutions(n: int = 40, seed: int = 26264) -> list[InstitutionRecord]:
    rng = random.Random(seed)
    out: list[InstitutionRecord] = []
    for i, (name, district) in enumerate(_SIMILAR):
        out.append(_inst(f"inst-sim-{i}", name, f"1-45{700000 + i:07d}", district,
                         "Uttar Pradesh", _PIN.get(district, "302001"), "KNP"))
    k = 0
    while len(out) < n:
        lead = rng.choice(_LEADS)
        typ = rng.choice(_TYPES)
        district, state, pin = rng.choice(_DISTRICTS)
        lead = f"{lead} {rng.choice(_TAILS)}" if rng.random() < 0.6 else lead
        name = f"{lead} {typ}"
        if any(o.name == name for o in out):
            continue
        out.append(_inst(f"inst-fill-{k}", name, f"1-46{k:07d}", district, state, pin, "KNP"))
        k += 1
    return out


def register(n_fillers: int = 40) -> tuple[list[InstitutionRecord], list[AliasRecord]]:
    return scripted_institutions() + filler_institutions(n_fillers), scripted_aliases()


# --------------------------------------------------------------------------------------
# Cases
# --------------------------------------------------------------------------------------


def days_ago(d: float) -> datetime:
    return ANCHOR - timedelta(days=d)


def case(cid: str, inst: str, bureau: str, category: str, *, received: float,
         subject: str = "", description: str = "", status: str = "UNDER_PROCESS",
         **kw) -> CaseRecord:
    return CaseRecord(
        id=cid, institution_id=inst, owner_bureau=bureau, category=category, status=status,
        received_at=days_ago(received), subject=subject, description=description,
        description_norm=normalise_text(description), display_id=kw.pop("display_id", cid), **kw,
    )


HERO_SUBJECT = "फीस वापस नहीं कर रहे"
HERO_TEXT = ("Maine 2 Oct ko admission withdraw kiya, ₹85,000 fees abhi tak wapas nahi mili. "
             "College bolta hai 4 saal ki fees do tab certificate milega.")
HERO_INSTITUTION_TEXT = "श्रीनाथ इंजीनियरिंग कॉलेज कानपुर"


def scenario_a_cases() -> dict[str, CaseRecord]:
    pgrc1 = case(
        "A-PGRC-1", SHRINATH, "PGRC", "FEE_REFUND", received=16, status="AWAITING_ATR",
        subject="Fee refund not received",
        description=("I withdrew my admission to the B.Tech programme on 14 Aug before the classes "
                     "started, but the college has not refunded the fee of Rs. 85,000 so far. "
                     "I have written to them three times and received no reply."),
        pending_step="INSTITUTION_ATR", pending_since=days_ago(11), party_hash="party-1",
        source_channel="CSS", source_refs=("CSS-2026-88123",),
    )
    pgrc2 = case(
        "A-PGRC-2", SHRINATH, "PGRC", "CERTIFICATE_WITHHELD", received=9,
        subject="Original certificates not returned",
        description=("The college is not returning my original 10th and 12th marksheets and is "
                     "demanding the fee for all four years of the programme."),
        party_hash="party-2", source_channel="CPGRAMS", source_refs=("DHIGH/E/2026/0034517",),
    )
    rb1 = case(
        "A-RB-1", SHRINATH, "RB", "SCRUTINY_COMMITTEE", received=25,
        subject="Scrutiny committee review on faculty norms",
        description=("Scrutiny committee to examine compliance with faculty norms and the "
                     "deficiency report of the institute."),
        pending_action="Scrutiny committee review scheduled", source_channel="BUREAU_FILE",
    )
    ro1 = case(
        "A-RO-1", SHRINATH, "RO", "FEE_REFUND", received=6, status="RECEIVED",
        subject="Status of fee refund", description="Status of fee refund please.",
        party_hash="party-3", source_channel="RO_REGISTER",
    )
    history = [
        case("A-H-1", SHRINATH, "RB", "RAGGING", received=200, status="DISPOSED",
             description="Seniors ragging freshers in hostel.", disposed_at=days_ago(190)),
        case("A-H-2", SHRINATH, "PGRC", "SCHOLARSHIP", received=150, status="DISPOSED",
             description="Post matric scholarship not credited.", disposed_at=days_ago(120)),
        case("A-H-3", SHRINATH, "PGRC", "ADMISSION", received=120, status="CLOSED_NO_ACTION",
             description="Admission denied despite merit list rank."),
    ]
    email_dup = case(
        "A-EMAIL-1", SHRINATH, "PGRC", "CERTIFICATE_WITHHELD", received=2, status="RECEIVED",
        subject="Reminder",
        description=("Please refer to my earlier grievance DHIGH/E/2026/0034517 already registered "
                     "on CPGRAMS. I am sending this as a reminder by email."),
        party_hash="party-2b", source_channel="EMAIL",
    )
    return {c.id: c for c in [pgrc1, pgrc2, rb1, ro1, email_dup, *history]}


def hero_new_case() -> CaseRecord:
    return case(
        "A-NEW", SHRINATH, "PGRC", "FEE_REFUND", received=0.04, status="RECEIVED",
        subject=HERO_SUBJECT, description=HERO_TEXT, party_hash="party-new", source_channel="CSS",
    )


def scenario_c_cases() -> tuple[CaseRecord, CaseRecord]:
    rb = case(
        "C-RB", DEVBHOOMI, "RB", "FACULTY_SHORTAGE", received=20,
        subject="Faculty shortage", description="Not enough faculty in the departments.",
        pending_step="SHOW_CAUSE_REPLY", pending_action="SHOW_CAUSE issued 29 Oct",
        pending_since=days_ago(3),
    )
    pgrc = case(
        "C-PGRC", DEVBHOOMI, "PGRC", "SERVICE_MATTER", received=15,
        subject="Faculty salary unpaid",
        description="Faculty salary has not been paid for four months.",
        pending_step="REFUND_FOLLOWUP", pending_action="REFUND_FOLLOWUP negotiation",
        pending_since=days_ago(8), hearing_at=ANCHOR + timedelta(days=2),
    )
    return rb, pgrc


def scenario_d_cases() -> tuple[CaseRecord, CaseRecord]:
    pgrc = case(
        "D-PGRC", GYANODAYA, "PGRC", "SCHOLARSHIP", received=12,
        subject="Scholarship not credited",
        description="My post-matric scholarship for the 2025 academic year has not been credited "
                    "to my account yet.",
    )
    ro = case(
        "D-RO", GYANODAYA, "RO", "INFRASTRUCTURE", received=4, status="RECEIVED",
        subject="Computer lab",
        description="The computer lab has only 20 working systems for 120 students.",
    )
    return pgrc, ro
