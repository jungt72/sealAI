"""P1-4 PR3.5 — characterization freeze for the remaining clean core seal-type
branches before routing through the pack seam:

  - checks_registry.py:293        `engineering_path != "rwdr"` guard
  - output_contract_assembly.py:752  `calc_type == "rwdr"` public-payload shape
  - calculation_projection.py:162    `calc_type != "rwdr"` ledger dedup filter

All three are 1:1 with the pack seam; the outputs must stay byte-identical —
including the `rwdr.<id>` dotted divergence, which requires the exact-match
`pack_for_calc_type` (NOT the namespace-matching `pack_for_calc_id`).
"""
from __future__ import annotations

from types import SimpleNamespace

from app.agent.domain.checks_registry import _build_rwdr_professional_check_results
from app.agent.graph.output_contract_assembly import _compute_public
from app.agent.v92.calculation_projection import calculation_ledger_derivations


class TestChecksRegistryRwdrGuardFreeze:
    _PROFILE = {"pressure_at_seal_bar": 5.0}

    def test_rwdr_path_builds_checks(self) -> None:
        assert _build_rwdr_professional_check_results(self._PROFILE, "rwdr")  # non-empty

    def test_non_rwdr_path_empty(self) -> None:
        assert _build_rwdr_professional_check_results(self._PROFILE, "static") == []
        assert _build_rwdr_professional_check_results(self._PROFILE, None) == []


class TestComputePublicRwdrShapeFreeze:
    def test_rwdr_calc_rich_shape(self) -> None:
        state = SimpleNamespace(
            compute_results=[{"calc_type": "rwdr", "status": "ok", "v_surface_m_s": 12.3}]
        )
        assert _compute_public(state) == [
            {
                "calc_type": "rwdr",
                "status": "ok",
                "v_surface_m_s": 12.3,
                "pv_value_mpa_m_s": None,
                "dn_value": None,
                "dn_warning": None,
                "pv_warning": None,
                "hrc_warning": None,
                "notes": [],
            }
        ]

    def test_non_rwdr_calc_trimmed_shape(self) -> None:
        state = SimpleNamespace(compute_results=[{"calc_type": "oring", "status": "ok"}])
        assert _compute_public(state) == [{"calc_type": "oring", "status": "ok"}]

    def test_dotted_rwdr_calc_type_is_trimmed_not_rich(self) -> None:
        # `rwdr.surface_speed` is NOT the coarse "rwdr" type → legacy `== "rwdr"`
        # is False → trimmed shape. Exact pack_for_calc_type preserves this;
        # pack_for_calc_id (namespace match) would wrongly take the rich branch.
        state = SimpleNamespace(
            compute_results=[{"calc_type": "rwdr.surface_speed", "status": "ok"}]
        )
        assert _compute_public(state) == [
            {"calc_type": "rwdr.surface_speed", "status": "ok"}
        ]


class TestLedgerDerivationDedupFreeze:
    def test_clean_rwdr_only_in_aggregate(self) -> None:
        derivations = calculation_ledger_derivations(
            [{"calc_type": "rwdr", "status": "ok", "outputs": {"v_surface_m_s": 12.3}}]
        )
        rwdr_items = [d for d in derivations if d.get("calc_type") == "rwdr"]
        assert len(rwdr_items) == 1  # only the aggregate, no standalone duplicate

    def test_non_rwdr_item_kept(self) -> None:
        derivations = calculation_ledger_derivations(
            [{"calculation_id": "oring.groove_screening", "status": "ok"}]
        )
        assert any(d.get("calc_type") == "oring.groove_screening" for d in derivations)

    def test_dotted_rwdr_calc_type_kept_standalone(self) -> None:
        # Folded into the rwdr aggregate (pack_for_calc_id namespace match) AND
        # kept standalone because the final filter is exact `!= "rwdr"`. Exact
        # pack_for_calc_type must preserve the standalone; pack_for_calc_id drops it.
        derivations = calculation_ledger_derivations(
            [{"calculation_id": "rwdr.surface_speed", "status": "ok"}]
        )
        assert any(d.get("calc_type") == "rwdr.surface_speed" for d in derivations)
