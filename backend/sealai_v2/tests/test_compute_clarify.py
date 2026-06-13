"""Unit-binding fix — Part 2 (backend): the /compute read surface carries structured clarifications.

Goes through the REAL recompute path (recompute_derived → compute_response) with the real cascade
engine; no network. Proves a unit-issue surfaces as a structured clarification on /compute (the
panel's confirm source) WITHOUT binding a value."""

from __future__ import annotations

from sealai_v2.api.serializers import compute_response
from sealai_v2.core.calc.derived import recompute_derived
from sealai_v2.core.calc.evaluator import CascadeCalcEngine
from sealai_v2.core.contracts import RememberedFact


def fact(feld: str, wert: str) -> RememberedFact:
    return RememberedFact(feld=feld, wert=wert, provenance="distilled-from-conversation")


def test_compute_surfaces_unrecognized_unit_as_one_click_clarification():
    comp = recompute_derived(
        (fact("wellendurchmesser", "40 mm"), fact("drehzahl", "5000 u/mon")), CascadeCalcEngine()
    )
    # v is NOT computed (rpm unbound — fail-closed), and the unit issue is a structured clarification
    assert not any(d.name == "v_m_s" for d in comp.derived)
    drehzahl = next(c for c in comp.clarifications if c.feld == "drehzahl")
    assert drehzahl.reason == "unit_unrecognized" and drehzahl.one_click is True
    assert drehzahl.suggested_unit == "U/min"

    payload = compute_response(comp)
    c = next(c for c in payload["clarifications"] if c["feld"] == "drehzahl")
    assert c["reason"] == "unit_unrecognized" and c["one_click"] is True
    assert c["raw_value"] == "5000" and c["suggested_unit"] == "U/min"


def test_compute_surfaces_known_other_unit_without_one_click():
    comp = recompute_derived((fact("wellendurchmesser", "50 cm"),), CascadeCalcEngine())
    c = next(c for c in compute_response(comp)["clarifications"] if c["feld"] == "wellendurchmesser")
    assert c["reason"] == "unit_known_other" and c["one_click"] is False
    assert c["known_dimension"] == "length" and c["expected_dimension"] == "length"


def test_compute_clean_inputs_emit_no_clarifications():
    comp = recompute_derived(
        (fact("wellendurchmesser", "40 mm"), fact("drehzahl", "8000 U/min")), CascadeCalcEngine()
    )
    payload = compute_response(comp)
    assert payload["clarifications"] == []
    assert any(d["name"] == "v_m_s" for d in payload["computed"])  # the kern computed v
