"""Unit tests for the deterministic calc formulas (core/calc/formulas.py) — pure math + the
fail-closed cross-input guards the per-input validity gate cannot catch."""

from __future__ import annotations

import math

import pytest

from sealai_v2.core.calc.formulas import (
    pv_wert,
    umfangsgeschwindigkeit,
    verpressung_prozent,
)


def test_umfangsgeschwindigkeit():
    assert umfangsgeschwindigkeit(d1_mm=40.0, rpm=3000.0) == pytest.approx(
        math.pi * 0.04 * 50.0
    )


def test_pv_wert():
    assert pv_wert(p_bar=2.0, v_m_s=3.0) == 6.0


def test_verpressung_prozent_normal():
    assert verpressung_prozent(schnurstaerke_mm=5.0, nuttiefe_mm=4.0) == pytest.approx(
        20.0
    )


def test_verpressung_prozent_fails_closed_on_nonpositive_schnurstaerke():
    with pytest.raises(ValueError):
        verpressung_prozent(schnurstaerke_mm=0.0, nuttiefe_mm=1.0)


def test_verpressung_prozent_fails_closed_when_nuttiefe_exceeds_schnurstaerke():
    # nuttiefe > schnurstaerke would yield a NEGATIVE (physically impossible) Verpressung — must fail
    # closed so the evaluator emits an honest NotComputed, not a confidently-wrong negative %.
    with pytest.raises(ValueError):
        verpressung_prozent(schnurstaerke_mm=2.0, nuttiefe_mm=5.0)
