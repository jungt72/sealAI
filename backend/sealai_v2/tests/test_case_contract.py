"""G1 (V2.1 Inc 1) — the typed ``Case`` contract + its byte-identical prompt projection.

Owner decision (2): ``Case`` → a byte-identical ``list[dict]{feld,wert}`` projection for the prompt;
Jinja unchanged. This test pins that bridge: ``Case.to_prompt_context()`` reproduces EXACTLY the
prior ``[{"feld": f.feld, "wert": f.wert} for f in case_state]`` projection (the old ``pipeline.py``
line), so L1/L3 see a byte-identical ``case_context`` and the eval is unperturbed. RED before the
``Case`` type exists.
"""

from __future__ import annotations

from sealai_v2.core.contracts import Case, RememberedFact


def _prior_projection(case_state):
    """The exact projection pipeline.py built before G1 — the byte-identity reference."""
    return [{"feld": f.feld, "wert": f.wert} for f in case_state]


def test_to_prompt_context_is_byte_identical_to_prior_projection():
    facts = (
        RememberedFact(feld="medium", wert="Mineralöl"),
        RememberedFact(feld="temperatur", wert="100 °C"),
        RememberedFact(feld="anwendung", wert="RWDR Getriebe"),
    )
    case = Case.from_case_state(facts)
    assert case.to_prompt_context() == _prior_projection(facts)


def test_empty_case_state_projects_empty_list():
    assert Case.from_case_state(()).to_prompt_context() == []


def test_projection_preserves_order_and_only_feld_wert():
    facts = (
        RememberedFact(feld="b", wert="2", as_of_turn=3),
        RememberedFact(feld="a", wert="1", as_of_turn=1),
    )
    out = Case.from_case_state(facts).to_prompt_context()
    # order preserved, and ONLY feld/wert surface (provenance/as_of_turn never reach the prompt)
    assert out == [{"feld": "b", "wert": "2"}, {"feld": "a", "wert": "1"}]


def test_typed_slots_are_scaffold_none_at_inc1():
    # The §5.1 typed slots exist but stay unpopulated in Inc 1 (archetype lands in G4; the rest via
    # the decode/describe adapters later) — so they cannot perturb the byte-identical projection.
    case = Case.from_case_state((RememberedFact(feld="medium", wert="Wasser"),))
    assert case.archetype is None
    assert case.conditions is None
    assert case.medium is None
    assert case.geometry is None
    assert case.seal_spec is None
