"""#2 denylist backstop: comparative material ranking is caught, profiles are not.

Hard acceptance (output_guard replaces the WHOLE text on a hit, so a false
positive would nuke the neutral deterministic comparison):
  - POSITIVE: the incident ranking sentences are flagged as comparative_ranking.
  - NEGATIVE (decisive): no material_comparison.py profile text and no full
    deterministic _render_comparison output may match the new patterns.

The denylist is a leaky backstop only; prompt shaping (#1) and the deterministic
passthrough (#4) remain primary.
"""

from __future__ import annotations

import re

import pytest

from app.agent.runtime.output_guard import _COMPILED, check_fast_path_output
from app.services.knowledge.material_comparison import (
    _MATERIAL_PROFILES,
    build_material_comparison_answer,
    humanize_german_technical_text,
)

# The exact compiled patterns of the new category (whitebox: prove THIS category
# does not fire, isolated from any pre-existing category).
_RANKING_PATTERNS: list[re.Pattern[str]] = [
    pattern for category, pattern in _COMPILED if category == "comparative_ranking"
]


def _ranking_hits(text: str) -> list[str]:
    return [p.pattern for p in _RANKING_PATTERNS if p.search(text)]


def test_new_category_is_registered() -> None:
    assert (
        _RANKING_PATTERNS
    ), "comparative_ranking patterns must be compiled into _COMPILED"


# --- POSITIVE: the real incident sentences are caught ----------------------

INCIDENT_SENTENCES = (
    "FKM besser für dynamische Anwendungen geeignet",
    "FKM ist besser geeignet für dynamische Anwendungen",
    "PTFE für statische bevorzugt",
    "kann höhere Drücke besser handhaben",
    "EPDM ist hier die bessere Wahl",
    "FKM ist für Öl vorzuziehen",
)


@pytest.mark.parametrize("sentence", INCIDENT_SENTENCES)
def test_incident_ranking_sentences_are_flagged(sentence: str) -> None:
    safe, category = check_fast_path_output(sentence)
    assert safe is False
    assert category == "comparative_ranking"
    assert _ranking_hits(sentence)


# --- POSITIVE: the four live-documented leak classes are caught --------------
# Each form previously slipped past the denylist and is intentionally chosen so it
# is NOT already covered by a pre-existing pattern (no bare "ist geeignet", no
# "besser geeignet als"). All must now flag as comparative_ranking.

LEAK_CLASS_SENTENCES = (
    # 1. Konditional — "wäre/würde … geeignet/eignen"
    "FKM wäre für Heißwasser geeignet",
    "EPDM würde sich hier besser eignen",
    # 2. Negation-impliziert-Präferenz — "weniger geeignet" / "nicht ungeeignet"
    "NBR ist hier weniger geeignet",
    "FKM ist nicht ungeeignet für diese Anwendung",
    # 3. Superlativ — "am besten/meisten geeignet"
    "EPDM ist am besten geeignet für Heißwasser",
    # 4. statt-Präferenz — "X statt Y gewählt"
    "Ich hätte FKM statt NBR gewählt",
)


@pytest.mark.parametrize("sentence", LEAK_CLASS_SENTENCES)
def test_leak_class_sentences_are_flagged(sentence: str) -> None:
    safe, category = check_fast_path_output(sentence)
    assert safe is False
    assert category == "comparative_ranking"
    assert _ranking_hits(sentence)


# --- POSITIVE: A.3 closes the two ORIGINAL reported leak forms ---------------
# Group A.1 only covered the geeignet-family. The originally reported leaks use
# optimal/überlegen/übertrifft and still passed both layers until A.3. Predicative
# optimum/superiority on a MATERIAL subject (or application anchor), plus
# material⇄material "übertrifft". All must flag as comparative_ranking.

A3_LEAK_SENTENCES = (
    # 1+2. optimum, predicative — material subject (+ conditional "könnte … sein")
    "EPDM könnte optimal sein",
    "EPDM könnte für diese Anwendung optimal sein",
    # 3. superiority, predicative "überlegen" — material subject
    "PTFE ist NBR überlegen",
    # 4. superiority "übertrifft" — material⇄material
    "PTFE übertrifft NBR",
)


@pytest.mark.parametrize("sentence", A3_LEAK_SENTENCES)
def test_a3_original_leak_forms_are_flagged(sentence: str) -> None:
    safe, category = check_fast_path_output(sentence)
    assert safe is False
    assert category == "comparative_ranking"
    assert _ranking_hits(sentence)


# --- NEGATIVE (decisive): property comparatives & data must NOT trigger ------

PROPERTY_COMPARATIVE_NEGATIVES = (
    # material_comparison.py:221 — property comparison "bessere X als Y"
    "bessere Wärme-, Ozon- und Alterungsbeständigkeit als NBR",
    "bessere Waerme-, Ozon- und Alterungsbestaendigkeit als NBR",
    # material_comparison.py:919 — bare "tribologisch besser:" property note
    "FFKM ist nicht automatisch tribologisch besser: Reibung, Abrieb, Wärme und "
    "dynamischer Betrieb müssen separat geprüft werden.",
    # verb forms must never match ("ver-besser-t" has no leading word boundary)
    "hoeherer ACN-Anteil verbessert meist Oel-/Kraftstofforientierung, reduziert "
    "aber Tieftemperaturflexibilitaet",
    "mehr ACN verbessert meist Öl-/Kraftstofforientierung, verschlechtert aber "
    "Tieftemperaturflexibilität.",
    "Verschleiß- und Formstabilität verbessern",
    # sts/materials.json:300 — note uses the reverse "bevorzugt für" direction
    "Sehr gute chemische Beständigkeit; FDA-konform; bevorzugt für Chemikalienhandling",
    # a user question (never guarded output anyway) must not match the patterns
    "welches ist besser für meine Anwendung?",
    # cautious LIMIT phrasing — "nicht (automatisch) geeignet" is an allowed limit,
    # not a preference; the negation leak class must never swallow it.
    "nicht automatisch geeignet für Heißwasser, Dampf, Amine",
    # property comparative "weniger robust" must not be read as "weniger geeignet"
    "mechanisch weniger robust, geringere Abrieb- und Weiterreißfestigkeit",
    # --- A.3 boundary: attributive (inflected) optimum/superiority is a PROPERTY
    #     statement, not a material selection; must never read as a ranking.
    "PTFE hat überlegene chemische Beständigkeit als NBR",
    "FKM hat optimale Temperaturbeständigkeit",
    "bietet überlegene Chemikalienbeständigkeit",
    "Die optimale Temperaturbeständigkeit liegt höher",
    # A.3 boundary: predicative optimum/superiority on a PROPERTY subject
    #     ("… von <Material> ist optimal/überlegen") — the material is a genitive
    #     modifier, not the subject, so it must NOT block.
    "Die Druckverformung von FKM ist optimal",
    "Die chemische Beständigkeit von PTFE ist der von NBR überlegen",
    # A.3 boundary: property-comparative "übertrifft" (eigenschaft-vs-eigenschaft)
    "die Wärmebeständigkeit von FKM übertrifft die von NBR",
    # A.3 boundary: hedged limit — "nicht optimal" is an allowed limitation
    "EPDM ist hier nicht optimal",
)


@pytest.mark.parametrize("text", PROPERTY_COMPARATIVE_NEGATIVES)
def test_property_comparatives_do_not_trigger_ranking(text: str) -> None:
    # The new category specifically must not fire on legitimate property text.
    assert _ranking_hits(text) == []
    _safe, category = check_fast_path_output(text)
    assert category != "comparative_ranking"


def test_no_profile_field_triggers_comparative_ranking() -> None:
    """Sweep every string field of every material profile — none may match."""

    string_fields = (
        "typical_temperature",
        "key_strengths",
        "key_limits",
        "media_orientation",
        "dynamics_orientation",
        "typical_uses",
        "critical_checks",
    )
    offenders: list[tuple[str, str, str, list[str]]] = []
    for material_id, profile in _MATERIAL_PROFILES.items():
        for field_name in string_fields:
            value = getattr(profile, field_name)
            items = (value,) if isinstance(value, str) else value
            for item in items:
                rendered = humanize_german_technical_text(item)
                hits = _ranking_hits(rendered)
                if hits:
                    offenders.append((material_id, field_name, rendered, hits))
    assert offenders == [], f"profile texts must never match: {offenders}"


@pytest.mark.parametrize(
    "pair",
    [
        ("FKM", "EPDM"),
        ("PTFE", "FKM"),
        ("HNBR", "NBR"),
        ("FFKM", "FKM"),
        ("NBR", "PTFE"),
    ],
)
def test_full_deterministic_render_never_triggers_comparative_ranking(
    pair: tuple[str, str],
) -> None:
    """Whole-text-nuke surface: the rendered comparison must never match."""

    answer = build_material_comparison_answer(f"Vergleiche {pair[0]} und {pair[1]}")
    assert answer is not None
    assert (
        _ranking_hits(answer.answer) == []
    ), f"deterministic render {pair} must not match comparative_ranking"
