"""Plain-English reason strings for stage A (institution) and stage B (relationship).

Every string is meant to be read by an officer, so no jargon (no "log-odds", no "TF-IDF").
Spec: the CaseLink design A5 and B4.
"""

from __future__ import annotations

from datetime import datetime

# --------------------------------------------------------------------------------------
# Stage A
# --------------------------------------------------------------------------------------

MAX_REASONS = 5


def pick_reasons(scored: list[tuple[float, str]], limit: int = MAX_REASONS) -> list[str]:
    """Strongest first, de-duplicated, at most ``limit``."""
    seen: set[str] = set()
    out: list[str] = []
    for _, text in sorted(scored, key=lambda t: -t[0]):
        if text not in seen:
            seen.add(text)
            out.append(text)
    return out[:limit]


def permanent_id_found(pid: str, in_text: bool) -> str:
    return f"Permanent ID {pid} found in complaint" if in_text else f"Permanent ID {pid} matches"


def permanent_id_name_differs() -> str:
    return "Permanent ID matches but name differs — check for typo in ID"


def permanent_id_not_found(pid: str, near: str | None) -> str:
    if near:
        return (
            f"Permanent ID {pid} is not in the register but differs by one digit from {near} "
            "— check for typo in ID"
        )
    return f"Permanent ID {pid} is not in the register — check for typo in ID"


def known_alias(confirmed_by: str | None, confirmed_at: datetime | None) -> str:
    who = f" by {confirmed_by}" if confirmed_by else ""
    when = f" on {confirmed_at.strftime('%d %b %Y')}" if confirmed_at else ""
    return f"Known alias confirmed earlier{who}{when}"


def transliteration(devanagari: str, latin: str) -> str:
    return f"Name matches after Hindi→English transliteration ({devanagari} → {latin})"


def name_similarity(score: float, query_name: str, candidate_name: str) -> str:
    return f"Name similarity {score:.2f} ('{query_name}' vs '{candidate_name}')"


def same_district(district: str) -> str:
    return f"Same district: {district}"


def different_district(query_district: str, candidate_district: str) -> str:
    return f"Different district ({query_district} vs {candidate_district})"


def same_pincode(pincode: str) -> str:
    return f"Same pincode: {pincode}"


def different_pincode(query_pin: str, candidate_pin: str) -> str:
    return f"Different pincode ({query_pin} vs {candidate_pin})"


def same_email_domain(domain: str) -> str:
    return f"Complainant email domain matches the institution ({domain})"


def distinctive_word(token: str) -> str:
    return f"Distinctive word '{token}' appears in both"


def weak_name() -> str:
    return "Name is only loosely similar"


def two_similar(district: str | None) -> str:
    return f"Two similar institutions in {district}" if district else "Two similar institutions"


# --------------------------------------------------------------------------------------
# Stage B
# --------------------------------------------------------------------------------------

_CATEGORY_WORDS = {
    "FEE_REFUND": "fee refund",
    "CERTIFICATE_WITHHELD": "withheld certificates",
    "FACULTY_SHORTAGE": "faculty shortage",
    "INFRASTRUCTURE": "infrastructure",
    "RAGGING": "ragging",
    "FAKE_APPROVAL_CLAIM": "fake approval claims",
    "SCHOLARSHIP": "scholarship",
    "ADMISSION": "admission",
    "SERVICE_MATTER": "staff service matters",
    "SCRUTINY_COMMITTEE": "scrutiny committee",
    "OTHER": "other matters",
}


def category_word(category: str) -> str:
    return _CATEGORY_WORDS.get(category, category.replace("_", " ").lower())


def same_institution(permanent_id: str | None) -> str:
    return f"Same institution (Permanent ID {permanent_id})" if permanent_id else "Same institution"


def same_category(category: str) -> str:
    return f"Both about {category_word(category)}"

def related_category(cat_a: str, cat_b: str) -> str:
    return f"Related subjects ({category_word(cat_a)} and {category_word(cat_b)})"


def text_similarity(value: float) -> str:
    return f"Text similarity {value:.2f}"


def days_apart(days: int) -> str:
    return "Received on the same day" if days == 0 else f"Received {days} days apart"


def same_complainant() -> str:
    return "Same complainant (contact details match — identity hidden)"


def ref_mentioned(ref: str, channel: str | None) -> str:
    where = {"EMAIL": "email", "CPGRAMS": "CPGRAMS case", "CSS": "CSS case"}.get(channel or "", "text")
    return f"CPGRAMS ref {ref} mentioned in {where}"


def ref_shared(ref: str) -> str:
    return f"Both cases carry source reference {ref}"


def different_bureaus(bureau_a: str, bureau_b: str) -> str:
    return f"Different bureaus: {bureau_a} and {bureau_b}"


def action_conflict(reason: str) -> str:
    return reason
