"""Cascade evaluator — OWNER-CONFIRMED expected values (the calc correctness gate, HUMAN-FINAL),
plus fail-closed, DAG cascade/depth, validity, conditions, and the qualitative swelling cross-layer."""

from __future__ import annotations

from sealai_v2.core.calc.evaluator import CascadeCalcEngine
from sealai_v2.core.contracts import GroundingFact


def _e() -> CascadeCalcEngine:
    return CascadeCalcEngine()


def _by_id(result):
    return {c.calc_id: c for c in result.computed}


def test_umfangsgeschwindigkeit_owner_expected_12_6():
    # OWNER-CONFIRMED: d = 80 mm, n = 3000 1/min → v = π·0,08·50 ≈ 12,6 m/s (eval CALC-01)
    r = _e().evaluate(params={"d1_mm": 80, "rpm": 3000, "seal_type": "rwdr"})
    cv = _by_id(r)
    assert "umfangsgeschwindigkeit" in cv
    assert abs(cv["umfangsgeschwindigkeit"].value - 12.566) < 0.01
    assert cv["umfangsgeschwindigkeit"].unit == "m/s"
    assert cv["umfangsgeschwindigkeit"].stage == 1
    assert cv["umfangsgeschwindigkeit"].estimate is False
    assert any(
        "grenzwertige Auslegung" in warning
        for warning in cv["umfangsgeschwindigkeit"].warnings
    )


def test_fail_closed_missing_input_is_never_a_number():
    r = _e().evaluate(params={"rpm": 3000, "seal_type": "rwdr"})  # no d1_mm
    nc = {n.calc_id: n.reason for n in r.not_computed}
    assert "Eingaben fehlen" in nc["umfangsgeschwindigkeit"]
    assert not any(c.calc_id == "umfangsgeschwindigkeit" for c in r.computed)


def test_fail_closed_outside_validity():
    r = _e().evaluate(params={"d1_mm": 80, "rpm": 999999, "seal_type": "rwdr"})
    nc = {n.calc_id: n.reason for n in r.not_computed}
    assert "außerhalb Gültigkeit" in nc["umfangsgeschwindigkeit"]
    assert not any(c.calc_id == "umfangsgeschwindigkeit" for c in r.computed)


def test_cascade_pv_from_computed_v_is_depth2_estimate():
    # PV = p · v; v is itself computed → PV is stage-2 / depth-2 → estimate-with-assumptions
    r = _e().evaluate(
        params={"d1_mm": 80, "rpm": 3000, "p_bar": 5, "seal_type": "rwdr"}
    )
    cv = _by_id(r)
    assert "pv_wert" in cv
    assert abs(cv["pv_wert"].value - (5 * 12.566)) < 0.05
    assert cv["pv_wert"].stage == 2
    assert cv["pv_wert"].derivation_depth == 2
    assert cv["pv_wert"].estimate is True


def test_verpressung_owner_expected_and_out_of_band_warning():
    r = _e().evaluate(
        params={"schnurstaerke_mm": 3.0, "nuttiefe_mm": 2.4, "seal_type": "o-ring"}
    )
    cv = _by_id(r)
    assert (
        abs(cv["verpressung_prozent"].value - 20.0) < 0.01
    )  # (3−2.4)/3·100, in 15–25 band
    assert not cv["verpressung_prozent"].warnings
    r2 = _e().evaluate(
        params={"schnurstaerke_mm": 3.0, "nuttiefe_mm": 1.5, "seal_type": "o-ring"}
    )  # 50 % → out of the 15–25 band
    cv2 = _by_id(r2)
    assert any("typischen Bereichs" in w for w in cv2["verpressung_prozent"].warnings)


def test_swelling_fachkarte_warns_and_notes():
    gf = (
        GroundingFact(
            text="EPDM ist unpolar und quillt stark in Mineralöl.",
            quelle="FK",
            card_id="FK-EPDM-MINERALOEL",
        ),
    )
    r = _e().evaluate(
        params={"schnurstaerke_mm": 3.0, "nuttiefe_mm": 2.4, "seal_type": "o-ring"},
        grounding_facts=gf,
    )
    cv = _by_id(r)
    assert any("Quellung" in w for w in cv["verpressung_prozent"].warnings)
    assert any("Quellung" in n for n in r.notes)


def test_condition_not_applicable():
    # verpressung requires seal_type=o-ring; an rwdr case → not applicable, not a number
    r = _e().evaluate(
        params={"schnurstaerke_mm": 3.0, "nuttiefe_mm": 2.4, "seal_type": "rwdr"}
    )
    nc = {n.calc_id: n.reason for n in r.not_computed}
    assert "nicht anwendbar" in nc["verpressung_prozent"]
