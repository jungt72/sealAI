"""Memory-integrity primitive (M6a (c)(ii)) — the deterministic numeric-trace gate.

``memory_fabrication`` is a Schranken-class hard gate: a remembered/distilled number that does not
trace to user-STATED content (e.g. 150→1500 °C) is the memory analogue of confident-false. This is
the shared unit behind the runtime distiller guard and the eval hard-gate.
"""

from __future__ import annotations

from sealai_v2.core.contracts import HARD_GATES, RememberedFact
from sealai_v2.memory.integrity import (
    memory_integrity_clean,
    numerics,
    untraceable_numeric_facts,
)


def test_memory_fabrication_is_a_hard_gate():
    assert "memory_fabrication" in HARD_GATES


def test_numerics_extracts_normalized_floats():
    assert numerics("150 °C, 3,5 bar, -40 und 80mm") == {150.0, 3.5, -40.0, 80.0}


def test_clean_when_numbers_trace_to_user_turns():
    cs = (
        RememberedFact("temperatur", "150 °C"),
        RememberedFact("medium", "Hydrauliköl"),
    )
    turns = ["FKM bei 150°C", "und Hydrauliköl dazu"]
    assert untraceable_numeric_facts(cs, turns) == ()
    assert memory_integrity_clean(cs, turns)


def test_flags_fabricated_or_distorted_number():
    cs = (RememberedFact("temperatur", "1500 °C"),)
    turns = ["FKM bei 150°C"]
    bad = untraceable_numeric_facts(cs, turns)
    assert [f.feld for f in bad] == ["temperatur"]
    assert not memory_integrity_clean(cs, turns)


def test_qualitative_facts_pass_no_numerics():
    cs = (RememberedFact("medium", "Hydrauliköl"),)
    assert untraceable_numeric_facts(cs, ["irgendwas ohne Zahl"]) == ()


def test_traces_across_the_union_of_prior_turns():
    cs = (RememberedFact("drehzahl", "3000 U/min"),)
    turns = ["Welle 80 mm", "dreht mit 3000 U/min"]
    assert untraceable_numeric_facts(cs, turns) == ()


# --- traceable-definition lock (owner guardrail): the check encodes the conservative STATED-only
# intent. "Traceable" = every numeric token of the fact appears verbatim among the user turns'
# numerics. INFERENCE (midpoint) and CONVERSION (unit change) introduce a number the user never
# stated → they must fail-to-trace and drop. Only a pure approximation that re-states an already
# stated number traces. These three cases pin that boundary for owner review (see plan §3).


def test_midpoint_inference_fails_to_trace_and_drops():
    # user stated a range "150 bis 160"; a distilled midpoint "155" is a number the user never said
    cs = (RememberedFact("temperatur", "155 °C"),)
    turns = ["läuft bei 150 bis 160 °C"]
    bad = untraceable_numeric_facts(cs, turns)
    assert [f.feld for f in bad] == ["temperatur"]  # {155} ⊄ {150, 160} → drop


def test_unit_conversion_fails_to_trace_and_drops():
    # user stated "150 °C"; a distilled Kelvin conversion "423 K" is a derived, unstated number
    cs = (RememberedFact("temperatur", "423 K"),)
    turns = ["FKM bei 150 °C"]
    bad = untraceable_numeric_facts(cs, turns)
    assert [f.feld for f in bad] == ["temperatur"]  # {423} ⊄ {150} → drop


def test_pure_approximation_traces():
    # "ca. 150" → "150" re-states the same number the user gave → traces (kept)
    cs = (RememberedFact("temperatur", "150 °C"),)
    turns = ["irgendwo um ca. 150 °C"]
    assert untraceable_numeric_facts(cs, turns) == ()  # {150} ⊆ {150} → keep
