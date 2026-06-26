"""Unit tests for extract_medium (Modus-E Case.medium population).

Deterministic, offline, no LLM. Mirrors the material extractor's doctrine:
recognise a single canonical medium; fail CLOSED to None on nothing-found or
ambiguity (≥2 distinct media).
"""

from __future__ import annotations

from sealai_v2.core.medium_extract import (
    extract_media,
    extract_medium,
    extract_medium_facts,
    medium_category,
)


def test_single_medium_recognised():
    assert extract_medium("Wir fahren das in Heißdampf, passt das?") == "Heißdampf"


def test_canonicalises_synonym_and_plural():
    assert extract_medium("greift Amine an?") == "Amin"
    assert extract_medium("beständig gegen Fette?") == "Fett"


def test_overlapping_tags_collapse_to_one_canonical():
    # "Mineralöl-Hydraulik" also contains the "Mineralöl" tag — both map to the
    # SAME canonical, so this is ONE medium, not an ambiguous pair.
    assert extract_medium("Betrieb mit Mineralöl-Hydraulik") == "Mineralöl"


def test_word_boundary_does_not_match_inside_compounds():
    # \bDampf\b must NOT fire inside "Heißdampf" -> single clean match.
    assert extract_medium("Heißdampf bei 150 °C") == "Heißdampf"


def test_unknown_medium_is_none():
    assert extract_medium("Welche Dichtung für mein Getriebe?") is None


def test_no_text_is_none():
    assert extract_medium("") is None


def test_extract_media_collects_all_distinct():
    # A real seal-check often names one medium with several tags, or genuinely two media.
    # extract_media returns the full set (the stage folds the kernel over all of them).
    assert set(extract_media("Heißdampf-Sterilisation (SIP) bei 140 C")) == {
        "Heißdampf",
        "Sterilisation",
        "SIP",
    }
    assert set(extract_media("Synthetiköl mit Ester-Additiven")) == {
        "Synthetiköl",
        "Ester",
    }


def test_extract_media_co_mentioned_disqualifier_is_kept():
    # The safety reason for collecting all: a disqualifying medium co-mentioned with a
    # compatible one must NOT be silently dropped (Aceton stays alongside Mineralöl).
    assert set(extract_media("Mischung aus Mineralöl und Aceton")) == {
        "Mineralöl",
        "Aceton",
    }


def test_extract_medium_returns_primary_or_none():
    # The single-value convenience: primary match, or None when nothing is recognised.
    assert extract_medium("nur in Heißdampf") == "Heißdampf"
    assert extract_medium("Welche Dichtung fürs Getriebe?") is None


def test_extract_medium_facts_specific_plus_category():
    # Phase-1 wiring: the stated medium becomes case-state facts the form hydrates — the specific
    # canonical under feld="medium", the coarse form category under feld="medium_kategorie".
    facts = extract_medium_facts("Welle 40mm, Medium Hydrauliköl")
    assert {f.feld: f.wert for f in facts} == {
        "medium": "Hydrauliköl",
        "medium_kategorie": "Öl",
    }
    assert all(f.provenance == "chat-inline" for f in facts)


def test_extract_medium_facts_empty_when_unrecognised():
    # Fail-closed (mirrors the extractors): nothing recognised → no facts (Phase-2 LLM covers any medium).
    assert extract_medium_facts("Hallo, wie geht es dir?") == ()


def test_medium_category_maps_oils_and_falls_back_to_sonstiges():
    assert medium_category("Mineralöl") == "Öl"
    assert medium_category("Heißdampf") == "Wasser"
    assert (
        medium_category("Schokolade") == "Sonstiges"
    )  # lossy by design; Phase-2 profiles it
