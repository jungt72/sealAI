"""P1-1 PR3 characterization: rwdr calc/risk detection via pack membership.

Behaviour-neutral. Freezes the current detection so the string-branch → pack
membership swap cannot change outcomes.

* `_is_rwdr_ledger_item` (calculation_projection :85) — frozen here; the rewire
  only touches the calc_id string check, so the output-key / calculator branches
  must keep their results.
* risk_readiness :437 (engineering_path == "rwdr") and :464 (the three explicit
  calc ids) are covered by the seam-helper equivalence below + the existing
  `test_pressure_truth_patch2` / `test_risk_claim_evidence_gate_patch4`.
"""
from __future__ import annotations

import pytest

from app.agent.v92.calculation_projection import _is_rwdr_ledger_item


@pytest.mark.parametrize(
    "item,expected",
    [
        ({"calculation_id": "rwdr.circumferential_speed"}, True),
        ({"calc_type": "rwdr"}, True),
        # explicit calc id: NOT matched by the id string check (no dot, != "rwdr");
        # stays False here (matched elsewhere via output keys/calculator).
        ({"calculation_id": "rwdr_pv_precheck"}, False),
        ({"calculator": "CascadingCalculationEngine"}, True),
        ({"calculator": "surface_speed_from_rpm_and_diameter"}, True),
        ({"v_surface_m_s": 1.2}, True),
        ({"pv_value_mpa_m_s": 0.5}, True),
        ({"calculation_id": "oring.groove"}, False),
        ({}, False),
    ],
)
def test_is_rwdr_ledger_item_frozen(item, expected):
    assert _is_rwdr_ledger_item(item) is expected


# Seam-helper equivalence to the legacy literals (behaviour the rewires rely on).
def test_pack_for_engineering_path_matches_legacy_literal():
    from app.domain.seal_packs import pack_for_engineering_path

    assert pack_for_engineering_path("rwdr") is not None
    assert pack_for_engineering_path("ms_pump") is None  # legacy :498 path, NOT a pack
    assert pack_for_engineering_path("") is None
    assert pack_for_engineering_path(None) is None


def test_is_pack_calculation_matches_legacy_explicit_set():
    from app.domain.seal_packs import is_pack_calculation

    for cid in ("rwdr_pv_precheck", "rwdr_dn_value", "rwdr_circumferential_speed"):
        assert is_pack_calculation(cid) is True
    assert is_pack_calculation("rwdr") is False  # not one of the explicit calc ids
    assert is_pack_calculation("oring_groove") is False


def test_pack_for_calc_id_matches_legacy_string_check():
    from app.domain.seal_packs import pack_for_calc_id

    assert pack_for_calc_id("rwdr") is not None
    assert pack_for_calc_id("rwdr.circumferential_speed") is not None
    assert pack_for_calc_id("rwdr_pv_precheck") is None  # no dot, != "rwdr"
    assert pack_for_calc_id("oring.groove") is None
