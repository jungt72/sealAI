"""Unit-binding fix — Part 1: synonym normalization + fail-closed clarify classification.

The synonym table recognizes provably-equivalent unit spellings (so a correct typo-free value always
binds); a mapped feld that still does not bind emits a structured ``BindClarification`` WITHOUT ever
auto-binding. Critically, the one-click recovery NEVER silently re-scales a known unit ("50 cm" must
not become 50 mm). All deterministic — no network."""

from __future__ import annotations

import pytest

from sealai_v2.core.calc.binding import bind_params
from sealai_v2.core.contracts import RememberedFact


def fact(feld: str, wert: str, provenance: str = "distilled-from-conversation") -> RememberedFact:
    return RememberedFact(feld=feld, wert=wert, provenance=provenance)


def _clar(res, feld: str):
    return next(c for c in res.clarifications if c.feld == feld)


# --- recognized synonyms bind (incl. the owner-approved additions) ------------------------


@pytest.mark.parametrize(
    "wert", ["5000 U/min", "5000 u/min", "5000 1/min", "5000 min⁻¹", "5000 min^-1", "5000 rpm", "5000 UpM", "5000 Upm"]
)
def test_rpm_synonyms_bind(wert: str):
    res = bind_params((fact("drehzahl", wert),))
    assert res.params == {"rpm": 5000.0}
    assert res.clarifications == ()  # bound → no clarification


@pytest.mark.parametrize("wert", ["50 mm", "50 millimeter", "50 Millimeter", "50mm"])
def test_mm_synonyms_bind(wert: str):
    res = bind_params((fact("wellendurchmesser", wert),))
    assert res.params == {"d1_mm": 50.0}


def test_spacing_and_case_normalize_into_bind():
    # whitespace + case variants normalize to an accepted token
    assert bind_params((fact("drehzahl", "4000  U / MIN"),)).params == {"rpm": 4000.0}


# --- unit_unrecognized: garbage/typo → one-click suggest (the reported live case) ----------


def test_typo_unit_is_unrecognized_one_click_not_bound():
    res = bind_params((fact("drehzahl", "5000 u/mon"),))
    assert "rpm" not in res.params  # fail-closed — NOT guessed
    c = _clar(res, "drehzahl")
    assert c.reason == "unit_unrecognized"
    assert c.raw_value == "5000" and c.raw_unit == "u/mon"
    assert c.suggested_unit == "U/min" and c.one_click is True
    assert res.notes  # visible drop note
    # the suggested unit round-trips: confirming "5000 U/min" through the binder actually binds
    assert bind_params((fact("drehzahl", f"{c.raw_value} {c.suggested_unit}"),)).params == {"rpm": 5000.0}


# --- unit_missing: pure number → one-click suggest (safe append) ---------------------------


@pytest.mark.parametrize(
    "feld,wert,inp,unit", [("drehzahl", "5000", "rpm", "U/min"), ("wellendurchmesser", "50", "d1_mm", "mm")]
)
def test_missing_unit_is_one_click(feld, wert, inp, unit):
    res = bind_params((fact(feld, wert),))
    assert inp not in res.params
    c = _clar(res, feld)
    assert c.reason == "unit_missing" and c.raw_value == wert and c.raw_unit == ""
    assert c.suggested_unit == unit and c.one_click is True


def test_thousands_dot_without_unit_is_unit_missing_not_silently_4000():
    res = bind_params((fact("drehzahl", "4.000"),))
    assert "rpm" not in res.params  # owner decision: thousands-dot binds ONLY with a unit
    assert _clar(res, "drehzahl").reason == "unit_missing"


# --- unit_known_other: NEVER one-click (the no-silent-rescale guarantee) -------------------


def test_cm_is_known_other_not_silently_50mm():
    res = bind_params((fact("wellendurchmesser", "50 cm"),))
    assert res.params == {}  # MUST NOT bind 50 mm — a 10× silent error is forbidden
    c = _clar(res, "wellendurchmesser")
    assert c.reason == "unit_known_other"
    assert c.known_dimension == "length" and c.raw_unit == "cm"
    assert c.one_click is False  # no one-click append
    assert "cm" in res.notes[0] and "mm" in res.notes[0]  # honest "give it in mm" message


def test_angular_unit_is_known_other_dimension_mismatch():
    res = bind_params((fact("wellendurchmesser", "50 grad"),))
    assert res.params == {}
    c = _clar(res, "wellendurchmesser")
    assert c.reason == "unit_known_other" and c.known_dimension == "angle" and c.one_click is False


@pytest.mark.parametrize("unit,dim", [("cm", "length"), ("dm", "length"), ("m", "length"), ("zoll", "length"), ("inch", "length"), ("hz", "frequency"), ("deg", "angle"), ("°", "angle")])
def test_known_units_registry_never_one_click(unit, dim):
    # for any param: a real-but-unaccepted unit is known_other and never one-click (no scale guess)
    res = bind_params((fact("drehzahl", f"5000 {unit}"),))
    assert "rpm" not in res.params
    c = _clar(res, "drehzahl")
    assert c.reason == "unit_known_other" and c.known_dimension == dim and c.one_click is False


# --- no_value: no number → re-enter guidance, no one-click --------------------------------


@pytest.mark.parametrize("wert", ["groß", "schnell, ca. 4000 U/min und mehr", ""])
def test_no_number_is_no_value(wert: str):
    res = bind_params((fact("wellendurchmesser", wert),))
    assert res.params == {}
    c = _clar(res, "wellendurchmesser")
    assert c.reason == "no_value" and c.one_click is False


# --- the clarify path is for MAPPED felder only (unmapped stay silent) ---------------------


def test_unmapped_felder_emit_no_clarification():
    res = bind_params((fact("medium", "Salzwasser"), fact("temperatur", "80 °C")))
    assert res.params == {} and res.notes == () and res.clarifications == ()


def test_bound_value_emits_no_clarification():
    res = bind_params((fact("wellendurchmesser", "50 mm"), fact("drehzahl", "5000 U/min")))
    assert res.params == {"d1_mm": 50.0, "rpm": 5000.0} and res.clarifications == ()
