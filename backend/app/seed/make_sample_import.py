"""Generate backend/app/seed/data/sample_import.csv (200 noisy, fully synthetic rows).

    cd backend && python -m app.seed.make_sample_import

Institution names are read from the database (so rows point at the seeded register); everything else is
drawn from the seed text banks with a fixed RNG (seed 26264), and dates are relative to the seed time
stored in policy_config.seeded_at.  Noise: abbreviations, misspellings, Hinglish/Devanagari institution
text, missing or one-digit-wrong Permanent IDs, mixed date formats, and a few garbage rows that the
importer must reject with row errors.  All names, e-mails and phone numbers are fictional.
"""

from __future__ import annotations

import csv
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.db import SessionLocal
from app.models.institutions import Institution
from app.models.system import PolicyConfig
from app.seed import textgen
from app.services.importer import TEMPLATE_HEADERS

OUT = Path(__file__).resolve().parent / "data" / "sample_import.csv"
N_ROWS = 200
RNG_SEED = 26264

BUREAU_BY_CATEGORY = {
    "FEE_REFUND": "PGRC", "CERTIFICATE_WITHHELD": "PGRC", "SCHOLARSHIP": "PGRC", "ADMISSION": "PGRC",
    "RAGGING": "PGRC", "SERVICE_MATTER": "PGRC", "FACULTY_SHORTAGE": "RB", "INFRASTRUCTURE": "RB",
    "SCRUTINY_COMMITTEE": "RB", "FAKE_APPROVAL_CLAIM": "VIGILANCE", "OTHER": "PGRC",
}
CHANNELS = ["CSS", "CSS", "CPGRAMS", "EMAIL", "RO_REGISTER", "BUREAU_FILE"]
GARBAGE_KINDS = ["no_subject", "no_institution", "bad_date", "bad_ro", "future_date", "symbols"]
UNKNOWN_INSTITUTIONS = [
    "Sunrise Public School", "XYZ Institute abroad", "Nimbus Coaching Classes", "Ministry office, Delhi",
]


def _parse_institution(inst: Institution, parts: dict[str, Any]) -> dict[str, Any]:
    """Rebuild the generator's {prefix, token, type_phrase, city, district, pincode} from a DB row."""
    name = inst.name
    city = inst.district or ""
    if "," in name:
        name, city = (x.strip() for x in name.rsplit(",", 1))
    prefix = ""
    for p in sorted(parts["prefixes"], key=len, reverse=True):
        if p and name.startswith(p + " "):
            prefix, name = p, name[len(p) + 1:]
            break
    type_phrase = ""
    for t in sorted(parts["type_phrases"], key=len, reverse=True):
        if name.endswith(t):
            type_phrase, name = t, name[: -len(t)].strip()
            break
    token = name.split()[0] if name else inst.name.split()[0]
    return {
        "prefix": prefix, "token": token, "type_phrase": type_phrase or "College of Engineering",
        "city": city or (inst.district or ""), "district": inst.district or city, "pincode": inst.pincode or "",
    }


def _fmt_date(dt: datetime, i: int) -> str:
    local = dt.astimezone(UTC)
    if i % 3 == 0:
        return local.strftime("%Y-%m-%d %H:%M")
    if i % 3 == 1:
        return local.strftime("%d/%m/%Y")
    return local.strftime("%d %b %Y")


def build_rows() -> list[dict[str, str]]:
    rng = random.Random(RNG_SEED)
    parts = textgen.load_json("name_parts.json")
    with SessionLocal() as s:
        insts = list(s.scalars(select(Institution).order_by(Institution.permanent_id)))
        seeded = s.get(PolicyConfig, "seeded_at")
    if not insts:
        raise SystemExit("No institutions in the database: run `python -m app.seed.generate --reset` first.")
    anchor = datetime.fromisoformat(seeded.value["at"]) if seeded and isinstance(seeded.value, dict) else datetime(2026, 11, 1, tzinfo=UTC)
    parsed = {i.id: _parse_institution(i, parts) for i in insts}
    garbage_at = dict(zip(sorted(rng.sample(range(N_ROWS), len(GARBAGE_KINDS))), GARBAGE_KINDS, strict=True))
    unknown_at = set(rng.sample([i for i in range(N_ROWS) if i not in garbage_at], len(UNKNOWN_INSTITUTIONS)))
    unknown_iter = iter(UNKNOWN_INSTITUTIONS)
    categories = list(BUREAU_BY_CATEGORY)
    rows: list[dict[str, str]] = []
    for i in range(N_ROWS):
        inst = rng.choice(insts)
        info = parsed[inst.id]
        category = rng.choice(categories)
        lang = textgen.choose_lang(rng)
        received = anchor - timedelta(days=rng.randint(1, 120), hours=rng.randint(0, 23), minutes=rng.randint(0, 59))
        slots = textgen.draw_slots(rng, category, received)
        subject = textgen.make_subject(rng, category, lang, slots)
        short = rng.random() < 0.08
        description = textgen.make_text(rng, category, lang, slots, short=short)[0]
        inst_text, _style = textgen.institution_text(info, rng)
        r = rng.random()
        pid = inst.permanent_id if r < 0.30 else textgen.corrupt_pid(rng, inst.permanent_id) if r < 0.38 else ""
        ptype = rng.choice(["STUDENT", "STUDENT", "PARENT", "FACULTY", "ANONYMOUS"]) if rng.random() > 0.1 else "ANONYMOUS"
        person = textgen.make_person(rng, ptype)
        phone = person["phone"]
        if phone and rng.random() < 0.4:
            phone = f"{phone[:5]} {phone[5:]}"
        channel = rng.choice(CHANNELS)
        ref = (
            f"DHIGH/E/2026/{rng.randint(10000, 99999):07d}" if channel == "CPGRAMS"
            else f"CSS-2026-{rng.randint(80000, 99999)}" if channel == "CSS"
            else f"IMP-{i + 1:04d}"
        )
        bureau = BUREAU_BY_CATEGORY[category]
        ro_code = ""
        if rng.random() < 0.2 and inst.ro_code:
            bureau, ro_code = "RO", inst.ro_code
        status = pending = ""
        s_roll = rng.random()
        if s_roll < 0.12:
            status = "UNDER_PROCESS"
        elif s_roll < 0.20 and category in ("FEE_REFUND", "CERTIFICATE_WITHHELD"):
            status, pending = "AWAITING_ATR", "INSTITUTION_ATR"
        elif s_roll < 0.25:
            status = "DISPOSED"
        row = {
            "source_channel": channel if rng.random() > 0.15 else "",
            "source_ref": ref,
            "received_at": _fmt_date(received, i),
            "institution_name": inst_text,
            "permanent_id": pid,
            "complainant_name": person["name"] or "",
            "complainant_email": person["email"] or "",
            "complainant_phone": phone or "",
            "category": category if rng.random() > 0.35 else "",
            "subject": subject,
            "description": description,
            "owner_bureau": bureau,
            "ro_code": ro_code,
            "status": status,
            "pending_step": pending,
        }
        if i in unknown_at:
            row["institution_name"], row["permanent_id"] = next(unknown_iter), ""
        kind = garbage_at.get(i)
        if kind == "no_subject":
            row["subject"] = row["description"] = ""
        elif kind == "no_institution":
            row["institution_name"] = row["permanent_id"] = ""
        elif kind == "bad_date":
            row["received_at"] = "yesterday evening"
        elif kind == "bad_ro":
            row["ro_code"] = "ZZ"
        elif kind == "future_date":
            row["received_at"] = (anchor + timedelta(days=90)).strftime("%d/%m/%Y")
        elif kind == "symbols":
            row = {h: "" for h in TEMPLATE_HEADERS} | {"institution_name": "#### !!!", "subject": "@@@@", "received_at": "??"}
        rows.append(row)
    return rows


def main() -> None:
    rows = build_rows()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=TEMPLATE_HEADERS)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows to {OUT}")


if __name__ == "__main__":
    main()

