"""Phase 2a — pressure unpark: druck → p_bar binds (bar-EXACT), every other pressure unit clarifies.

The owner-gated extension of the declared binding table (build-spec §4: extending it is an owner
decision). `druck` now feeds the PV kern via `p_bar`, but ONLY when the value is in bar — the
fail-closed, never-silently-rescale guarantee extends to pressure: mbar / kPa / MPa / Pa / psi are
real pressure units of a DIFFERENT scale, so they classify `unit_known_other` (clarify, NO one-click
append — appending "bar" to "500 mbar" or "0.5 MPa" would be a silent ×1000 / ×10 wrong-bind).
Deterministic; no network.
"""

from __future__ import annotations

import pytest

from sealai_v2.core.calc.binding import bind_params
from sealai_v2.core.contracts import RememberedFact


def fact(
    feld: str, wert: str, provenance: str = "distilled-from-conversation"
) -> RememberedFact:
    return RememberedFact(feld=feld, wert=wert, provenance=provenance)


def _clar(res, feld: str):
    return next(c for c in res.clarifications if c.feld == feld)


# --- bar binds (the unpark) ----------------------------------------------------------------


def test_druck_binds_p_bar_in_bar():
    res = bind_params((fact("druck", "5 bar"),))
    assert res.params == {"p_bar": 5.0}
    assert res.clarifications == ()  # bound → no clarification
    assert "druck" in res.origins["p_bar"] and "5 bar" in res.origins["p_bar"]


def test_druck_german_decimal_binds():
    assert bind_params((fact("druck", "2,5 bar"),)).params == {"p_bar": 2.5}


def test_druck_user_form_provenance_binds():
    res = bind_params((fact("druck", "5 bar", provenance="user-form"),))
    assert res.params == {"p_bar": 5.0}
    assert "Formular" in res.origins["p_bar"] or "user-form" in res.origins["p_bar"]


# --- the scale-guard: real pressure units of a different scale NEVER rescale to bar ----------


@pytest.mark.parametrize("wert", ["500 mbar", "10 psi", "0.5 MPa", "0,5 MPa", "100 kPa", "50 Pa"])
def test_other_pressure_units_are_known_other_never_one_click(wert: str):
    res = bind_params((fact("druck", wert),))
    assert "p_bar" not in res.params  # MUST NOT bind — appending/scaling "bar" is forbidden
    c = _clar(res, "druck")
    assert c.reason == "unit_known_other"
    assert c.known_dimension == "pressure" and c.expected_dimension == "pressure"
    assert c.one_click is False  # NO one-click → no silent rescale to bar
    assert res.notes  # the drop is visible, never silent


def test_druck_unitless_is_unit_missing_one_click_safe():
    # a pure number gets the canonical bar appended (no scale error) — same policy as mm/rpm.
    res = bind_params((fact("druck", "5"),))
    assert "p_bar" not in res.params
    c = _clar(res, "druck")
    assert c.reason == "unit_missing" and c.suggested_unit == "bar" and c.one_click is True
    # the suggestion round-trips: "5 bar" actually binds
    assert bind_params((fact("druck", f"{c.raw_value} {c.suggested_unit}"),)).params == {"p_bar": 5.0}


def test_druck_length_unit_is_dimension_mismatch():
    # a length unit on the pressure field → wrong KIND of quantity (not just a scale slip).
    c = _clar(bind_params((fact("druck", "5 cm"),)), "druck")
    assert c.reason == "unit_known_other"
    assert c.known_dimension == "length" and c.expected_dimension == "pressure"
    assert c.one_click is False
