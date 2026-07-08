"""safety/risk_flags.py — deterministic risk-flag detection (Legal-by-Design Phase D, Goal 6)."""

from __future__ import annotations

from sealai_v2.core.legal_doctrine import RISK_TRIGGER_TERMS
from sealai_v2.safety.risk_flags import RISK_WARNING_TEXT, detect_risk_flags


def test_empty_text_yields_no_flags():
    assert detect_risk_flags("") == ()
    assert detect_risk_flags(None) == ()  # type: ignore[arg-type]


def test_no_trigger_term_yields_no_flags():
    assert (
        detect_risk_flags("Welches Material eignet sich für Hydrauliköl bei 80°C?")
        == ()
    )


def test_single_trigger_term_detected():
    assert detect_risk_flags("Ist FKM für ATEX-Zonen geeignet?") == ("ATEX",)


def test_multiple_trigger_terms_detected_in_list_order():
    text = "Wir brauchen eine Dichtung für Wasserstoff in einer explosionsfähigen ATEX-Umgebung."
    flags = detect_risk_flags(text)
    assert flags == ("ATEX", "Wasserstoff")  # RISK_TRIGGER_TERMS order, not text order


def test_case_insensitive_match():
    assert detect_risk_flags("atex zone 1") == ("ATEX",)


def test_word_boundary_does_not_false_positive_on_substring():
    # "CE" must not fire inside an unrelated word containing "ce"
    assert detect_risk_flags("Bezeichnung: RWDR-Standardausführung") == ()


def test_multi_word_trigger_term_matches_as_a_phrase():
    assert detect_risk_flags("This is a safety component for pressure equipment.") == (
        "Pressure Equipment",
        "Safety component",
    )


def test_every_risk_trigger_term_is_individually_detectable():
    # A guard against a term silently breaking (e.g. an unescaped regex char added later).
    for term in RISK_TRIGGER_TERMS:
        assert detect_risk_flags(f"Kontext: {term} betrifft diesen Fall.") == (term,)


def test_risk_warning_text_is_non_empty_and_mentions_no_approval():
    assert RISK_WARNING_TEXT
    assert "Freigabe" in RISK_WARNING_TEXT
    assert "keine Empfehlung" in RISK_WARNING_TEXT
