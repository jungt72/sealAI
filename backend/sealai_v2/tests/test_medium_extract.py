"""Unit tests for extract_medium (Modus-E Case.medium population).

Deterministic, offline, no LLM. Mirrors the material extractor's doctrine:
recognise a single canonical medium; fail CLOSED to None on nothing-found or
ambiguity (≥2 distinct media).
"""

from __future__ import annotations

from sealai_v2.core.medium_extract import extract_medium


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


def test_two_distinct_media_are_ambiguous_none():
    # Conservative fail-closed: Aceton + Mineralöl are two distinct canonicals.
    assert extract_medium("Mischung aus Mineralöl und Aceton") is None
