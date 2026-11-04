"""classify.py: keyword + Hinglish dictionary classifier with TF-IDF fallback."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from engine_fixtures import HERO_SUBJECT, HERO_TEXT

from app.services.classify import classify


def test_scenario_a_is_fee_refund() -> None:
    s = classify(HERO_SUBJECT, HERO_TEXT)
    assert s.category == "FEE_REFUND"
    assert s.confidence >= 0.5
    assert s.keywords


@pytest.mark.parametrize("subject,text,expected", [
    ("Faculty salary unpaid", "Teachers have not been paid salary for 4 months", "SERVICE_MATTER"),
    ("Lab", "The computer lab has only 20 working systems for 120 students", "INFRASTRUCTURE"),
    ("Scholarship", "post-matric scholarship not credited to my account", "SCHOLARSHIP"),
    ("Ragging", "seniors are ragging freshers in the hostel", "RAGGING"),
    ("Scrutiny", "scrutiny committee review of faculty norms", "SCRUTINY_COMMITTEE"),
    ("फर्जी मान्यता", "कॉलेज बिना मान्यता के एडमिशन ले रहा है", "FAKE_APPROVAL_CLAIM"),
    ("TC nahi de rahe", "college original marksheet aur certificate roke hue hai",
     "CERTIFICATE_WITHHELD"),
])
def test_other_categories(subject: str, text: str, expected: str) -> None:
    assert classify(subject, text).category == expected


def test_no_evidence_is_other_with_low_confidence() -> None:
    s = classify("hello", "xyz abc")
    assert s.category == "OTHER" and s.confidence <= 0.3


def test_accuracy_on_research_templates() -> None:
    path = (Path(__file__).resolve().parents[2] / "app" / "seed" / "data"
            / "complaint_templates.json")
    if not path.exists():
        pytest.skip("complaint_templates.json not present")
    templates = json.loads(path.read_text(encoding="utf-8"))["templates"]
    total = ok = 0
    for cat, langs in templates.items():
        if cat == "OTHER":
            continue
        for lang, items in langs.items():
            if lang == "short":
                continue
            for item in items:
                total += 1
                ok += classify("", re.sub(r"\{[a-z_]+\}", "12", item)).category == cat
    assert total >= 100
    assert ok / total >= 0.85, f"{ok}/{total}"
