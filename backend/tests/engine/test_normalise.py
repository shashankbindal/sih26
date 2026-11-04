"""normalise.py: names, text, PII, language, extractors (the CaseLink design section 0)."""

from __future__ import annotations

import pytest

from app.services.caselink import SanscriptTransliterator
from app.services.normalise import (
    detect_language,
    extract_district,
    extract_permanent_id,
    extract_pincode,
    mask_pii,
    normalise_name,
    normalise_text,
    transliterate_word,
)


@pytest.mark.parametrize("devanagari,latin", [
    ("श्रीनाथ", "shrinath"),
    ("कानपुर", "kanpur"),
    ("लखनऊ", "lakhnau"),
    ("सरकारी", "sarkari"),
    ("जबलपुर", "jabalpur"),
    ("कृष्णा", "krishna"),
])
def test_transliteration_with_schwa_deletion(devanagari: str, latin: str) -> None:
    assert transliterate_word(devanagari) == latin
    assert SanscriptTransliterator().to_latin(devanagari) == latin


def test_hindi_city_map_beats_transliteration() -> None:
    assert normalise_name("लखनऊ").text == "lucknow"
    assert normalise_name("कानपुर").text == "kanpur"


def test_sarkari_as_institution_word_maps_to_government() -> None:
    assert normalise_name("सरकारी इंजीनियरिंग कॉलेज").text == "government engineering college"


def test_abbreviations_and_misspelling() -> None:
    nn = normalise_name("Govt Engg Collage Kanpur")
    assert nn.text == "government engineering college kanpur"
    assert nn.tokens == ("government", "engineering", "college", "kanpur")


def test_hindi_institution_name() -> None:
    nn = normalise_name("श्रीनाथ इंजीनियरिंग कॉलेज कानपुर")
    assert nn.text == "shrinath engineering college kanpur"
    assert nn.has_devanagari
    assert ("श्रीनाथ", "shrinath") in nn.translations


def test_ampersand_stop_tokens_and_key_folding() -> None:
    nn = normalise_name("Shrinath Institute of Engineering & Technology")
    assert nn.text == "shrinath institute of engineering and technology"
    assert "of" not in nn.tokens and "and" not in nn.tokens
    # sh/s folding only inside the key, never in the displayed text
    assert nn.text.startswith("shrinath")
    assert nn.key.startswith("srinath")
    assert normalise_name("Shrinath").key == normalise_name("Srinath").key


def test_name_abbreviations_stay_separate_from_text_lexicon() -> None:
    # "sr" is "shri" for institution names but "senior" in the Hinglish text map
    assert normalise_name("Sr Ram College").tokens[0] == "shri"
    assert "shri" not in normalise_text("sr faculty member").split()


def test_st_only_as_first_token() -> None:
    assert normalise_name("St Xavier Institute").tokens[0] == "saint"
    assert "saint" not in normalise_name("Ram St College").tokens


def test_zero_width_and_dotted_abbreviations() -> None:
    assert normalise_name("Shri​nath G.E.C.").text == "shrinath gec"


def test_normalise_text_hinglish_lexicon() -> None:
    out = normalise_text("Fees wapas nahi mili, certificate nahi de rahe, TC chahiye").split()
    assert "fee" in out and "refund" in out and "certificate" in out


def test_normalise_text_multiword_key_before_single() -> None:
    assert "refund" in normalise_text("paisa wapas nahi").split()


def test_normalise_text_hindi_subject() -> None:
    out = normalise_text("फीस वापस नहीं कर रहे").split()
    assert "fee" in out and "refund" in out


def test_mask_pii() -> None:
    text = ("Mail ramesh.k@example.com or call +91 98765 43210 / 9123456780. "
            "Aadhaar 2345 6789 0123. I am Ramesh Kumar. ID 1-4463974255.")
    out = mask_pii(text, known_names=["Ramesh Kumar"])
    assert "[EMAIL]" in out and out.count("[PHONE]") == 2 and "[ID]" in out and "[NAME]" in out
    assert "example.com" not in out and "98765" not in out and "Ramesh" not in out
    assert "1-4463974255" in out  # institution Permanent IDs are not personal data


def test_detect_language() -> None:
    assert detect_language("फीस वापस नहीं कर रहे") == "hi"
    assert detect_language("Maine admission withdraw kiya, fees abhi tak wapas nahi mili") == "hinglish"
    assert detect_language("The college has not refunded my fee after withdrawal") == "en"
    assert detect_language("मेरी fees वापस नहीं मिली") == "hinglish"


def test_extract_permanent_id_and_pincode() -> None:
    assert extract_permanent_id("my college id is 1-4463974255 thanks") == "1-4463974255"
    assert extract_permanent_id("id: 1 - 4463 974255") == "1-4463974255"
    assert extract_permanent_id("seven digit style 1-4463974 ok") == "1-4463974"  # 7..11 digits
    assert extract_permanent_id("phone 9876543210 only") is None
    assert extract_pincode("Kanpur 208017, refund Rs 85,000") == "208017"
    assert extract_pincode("refund of Rs 850000 pending") is None


def test_extract_district() -> None:
    districts = ["Kanpur Nagar", "Lucknow", "Dehradun"]
    assert extract_district("श्रीनाथ इंजीनियरिंग कॉलेज कानपुर", districts) == "Kanpur Nagar"
    assert extract_district("Govt college, Lucknow", districts) == "Lucknow"
    assert extract_district("college in Pune", districts) is None
