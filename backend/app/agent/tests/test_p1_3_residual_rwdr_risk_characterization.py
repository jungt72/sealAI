"""P1-3: freeze the three residual rwdr risk branches before refactor.

Behaviour-neutral — these snapshots must stay GREEN before AND after.

* :527 runout_risk   — clean `engineering_path == "rwdr"` → pack refactor
* :555 surface_risk  — clean `engineering_path == "rwdr"` → pack refactor
* :499 speed_pv_risk — heterogeneous {rwdr, ms_pump, unclear_rotary}; stays a
  documented CORE check (owner decision). The neutrality guard below pins that
  ms_pump / unclear_rotary keep emitting it.
"""
from __future__ import annotations

from app.agent.domain.risk_readiness import evaluate_risks


def _risk(results, name):
    return next((r for r in results if r.risk_name == name), None)


# --- :527 runout_risk (rwdr only) ------------------------------------------- #
def test_runout_risk_rwdr_above_threshold():
    r = _risk(evaluate_risks({"runout_mm": 0.3}, engineering_path="rwdr"), "runout_risk")
    assert r is not None and r.score == 3


def test_runout_risk_rwdr_below_threshold():
    r = _risk(evaluate_risks({"runout_mm": 0.1}, engineering_path="rwdr"), "runout_risk")
    assert r is not None and r.score == 0


def test_runout_risk_absent_for_non_rwdr():
    assert _risk(evaluate_risks({"runout_mm": 0.3}, engineering_path="o_ring"), "runout_risk") is None
    assert _risk(evaluate_risks({"runout_mm": 0.3}, engineering_path="ms_pump"), "runout_risk") is None


# --- :555 surface_risk (rwdr only) ------------------------------------------ #
def test_surface_risk_rwdr_when_missing():
    r = _risk(evaluate_risks({}, engineering_path="rwdr"), "surface_risk")
    assert r is not None and r.score == 9


def test_surface_risk_absent_for_non_rwdr():
    assert _risk(evaluate_risks({}, engineering_path="o_ring"), "surface_risk") is None


# --- :499 speed_pv_risk (heterogeneous core check — stays as-is) ------------- #
def test_speed_pv_risk_fires_for_all_three_paths():
    for path in ("rwdr", "ms_pump", "unclear_rotary"):
        r = _risk(evaluate_risks({}, engineering_path=path), "speed_pv_risk")
        assert r is not None and r.score == 9, f"speed_pv_risk missing for {path}"


def test_speed_pv_risk_absent_for_unrelated_path():
    assert _risk(evaluate_risks({}, engineering_path="o_ring"), "speed_pv_risk") is None
