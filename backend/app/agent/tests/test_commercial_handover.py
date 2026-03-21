"""
Unit tests for Phase A6 — Commercial / Handover Layer.

Tests cover:
1. HandoverLayer TypedDict exists and is correctly typed in SealingAIState
2. is_handover_ready — True only when rfq_ready + no pending review
3. is_handover_ready — False for every other release_status
4. is_handover_ready — False when review is pending (even if rfq_ready)
5. handover_payload — contains qualified_material_ids and qualified_materials
6. handover_payload — contains confirmed_parameters from asserted layer
7. handover_payload — contains dimensions when present in asserted.machine_profile
8. handover_payload — is None when not ready
9. Leakage guard — governance internals are NOT in the payload
10. Leakage guard — review fields are NOT in the payload
11. Leakage guard — cycle/observed/normalized internals are NOT in the payload
12. final_response_node writes handover into sealing_state (integration)
"""
from __future__ import annotations

import pytest

from app.agent.agent.commercial import (
    _is_handover_ready,
    build_handover_payload,
)
from app.agent.agent.state import HandoverLayer, SealingAIState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _governance(release_status: str = "rfq_ready", rfq_admissibility: str = "ready") -> dict:
    return {
        "release_status": release_status,
        "rfq_admissibility": rfq_admissibility,
        "specificity_level": "compound_required",
        "scope_of_validity": [],
        "assumptions_active": [],
        "gate_failures": ["gate_A_failed"],          # internal — must not leak
        "unknowns_release_blocking": ["medium"],      # internal — must not leak
        "unknowns_manufacturer_validation": [],
        "conflicts": [{"type": "some_conflict"}],     # internal — must not leak
    }


def _review(required: bool = False, state: str = "none") -> dict:
    return {
        "review_required": required,
        "review_state": state,
        "review_reason": "Demo-Daten." if required else "",
        "reviewed_by": None,
        "review_decision": None,
        "review_note": None,
    }


def _selection(viable_ids: list | None = None) -> dict:
    if viable_ids is None:
        viable_ids = ["fkm::v75::freudenberg"]
    candidates = [
        {
            "candidate_id": "fkm::v75::freudenberg",
            "material_family": "FKM",
            "grade_name": "V75",
            "manufacturer_name": "Freudenberg",
            "viability_status": "viable",
            "candidate_kind": "manufacturer_grade",
            "filler_hint": None,
            "block_reason": None,
            "evidence_refs": [],
        }
    ]
    return {
        "viable_candidate_ids": viable_ids,
        "candidates": candidates,
        "blocked_candidates": [],
        "winner_candidate_id": viable_ids[0] if viable_ids else None,
        "selection_status": "viable_candidates_available",
        "release_status": "rfq_ready",
        "rfq_admissibility": "ready",
        "specificity_level": "compound_required",
        "output_blocked": False,
        "recommendation_artifact": {},
    }


def _asserted(with_dimensions: bool = False) -> dict:
    operating: dict = {
        "temperature_c": 120.0,
        "temperature_raw": "120°C",
        "pressure_bar": 50.0,
        "pressure_raw": "50 bar",
        "medium": "Hydrauliköl HLP 46",
        "dynamic_type": "rotary",
    }
    machine: dict = {}
    if with_dimensions:
        machine = {
            "shaft_diameter_mm": 80.0,
            "bore_diameter_mm": 100.0,
            # internal field that must not leak:
            "internal_notes": "do not expose",
        }
    return {
        "operating_conditions": operating,
        "machine_profile": machine,
        "medium_profile": {},
        "installation_profile": {},
        "sealing_requirement_spec": {},
    }


def _sealing_state(
    *,
    release_status: str = "rfq_ready",
    review_required: bool = False,
    review_state_str: str = "none",
    with_dimensions: bool = False,
    viable_ids: list | None = None,
) -> dict:
    return {
        "governance": _governance(release_status),
        "review": _review(review_required, review_state_str),
        "selection": _selection(viable_ids),
        "asserted": _asserted(with_dimensions),
        "observed": {"observed_inputs": [], "raw_parameters": {}},
        "normalized": {"identity_records": {}, "normalized_parameters": {}},
        "cycle": {
            "analysis_cycle_id": "cycle-001",
            "snapshot_parent_revision": 0,
            "superseded_by_cycle": None,
            "contract_obsolete": False,
            "contract_obsolete_reason": None,
            "state_revision": 1,
        },
    }


# ---------------------------------------------------------------------------
# 1. HandoverLayer structural typing
# ---------------------------------------------------------------------------

class TestHandoverLayerStructure:
    def test_handover_layer_fields(self):
        h: HandoverLayer = {
            "is_handover_ready": True,
            "target_system": "rfq_portal",
            "handover_payload": {"qualified_material_ids": ["x"]},
        }
        assert h["is_handover_ready"] is True
        assert h["target_system"] == "rfq_portal"
        assert isinstance(h["handover_payload"], dict)

    def test_handover_layer_optional_fields_can_be_none(self):
        h: HandoverLayer = {
            "is_handover_ready": False,
            "target_system": None,
            "handover_payload": None,
        }
        assert h["target_system"] is None
        assert h["handover_payload"] is None


# ---------------------------------------------------------------------------
# 2–4. _is_handover_ready
# ---------------------------------------------------------------------------

class TestIsHandoverReady:
    def test_rfq_ready_no_review_is_ready(self):
        assert _is_handover_ready(_governance("rfq_ready"), _review(False)) is True

    def test_rfq_ready_with_pending_review_is_not_ready(self):
        assert _is_handover_ready(_governance("rfq_ready"), _review(True, "pending")) is False

    @pytest.mark.parametrize("rs", [
        "inadmissible",
        "precheck_only",
        "manufacturer_validation_required",
        "not_applicable",
    ])
    def test_non_rfq_ready_statuses_are_not_ready(self, rs):
        assert _is_handover_ready(_governance(rs), _review(False)) is False

    def test_empty_governance_is_not_ready(self):
        assert _is_handover_ready({}, {}) is False

    def test_review_required_true_blocks_even_rfq_ready(self):
        gov = _governance("rfq_ready")
        rev = {"review_required": True, "review_state": "pending"}
        assert _is_handover_ready(gov, rev) is False

    def test_review_approved_does_not_block(self):
        """Once a review is resolved (review_required reset to False), handover may proceed."""
        gov = _governance("rfq_ready")
        rev = {"review_required": False, "review_state": "approved"}
        assert _is_handover_ready(gov, rev) is True


# ---------------------------------------------------------------------------
# 5–8. build_handover_payload — payload content
# ---------------------------------------------------------------------------

class TestBuildHandoverPayloadContent:
    def test_is_handover_ready_true_when_qualified(self):
        state = _sealing_state()
        result = build_handover_payload(state)
        assert result["is_handover_ready"] is True

    def test_target_system_set_when_ready(self):
        result = build_handover_payload(_sealing_state())
        assert result["target_system"] is not None

    def test_handover_payload_present_when_ready(self):
        result = build_handover_payload(_sealing_state())
        assert result["handover_payload"] is not None

    def test_qualified_material_ids_in_payload(self):
        result = build_handover_payload(_sealing_state())
        ids = result["handover_payload"]["qualified_material_ids"]
        assert "fkm::v75::freudenberg" in ids

    def test_qualified_materials_name_cards_in_payload(self):
        result = build_handover_payload(_sealing_state())
        mats = result["handover_payload"]["qualified_materials"]
        assert len(mats) > 0
        assert mats[0]["material_family"] == "FKM"
        assert mats[0]["grade_name"] == "V75"

    def test_confirmed_parameters_temperature(self):
        result = build_handover_payload(_sealing_state())
        params = result["handover_payload"]["confirmed_parameters"]
        assert params["temperature_c"] == 120.0

    def test_confirmed_parameters_pressure(self):
        result = build_handover_payload(_sealing_state())
        params = result["handover_payload"]["confirmed_parameters"]
        assert params["pressure_bar"] == 50.0

    def test_confirmed_parameters_medium(self):
        result = build_handover_payload(_sealing_state())
        params = result["handover_payload"]["confirmed_parameters"]
        assert params["medium"] == "Hydrauliköl HLP 46"

    def test_dimensions_included_when_present(self):
        result = build_handover_payload(_sealing_state(with_dimensions=True))
        dims = result["handover_payload"]["dimensions"]
        assert dims["shaft_diameter_mm"] == 80.0
        assert dims["bore_diameter_mm"] == 100.0

    def test_dimensions_absent_when_not_in_asserted(self):
        result = build_handover_payload(_sealing_state(with_dimensions=False))
        assert "dimensions" not in result["handover_payload"]

    def test_payload_is_none_when_not_ready(self):
        state = _sealing_state(release_status="inadmissible")
        result = build_handover_payload(state)
        assert result["is_handover_ready"] is False
        assert result["handover_payload"] is None
        assert result["target_system"] is None

    def test_payload_is_none_when_review_pending(self):
        state = _sealing_state(review_required=True, review_state_str="pending")
        result = build_handover_payload(state)
        assert result["is_handover_ready"] is False
        assert result["handover_payload"] is None

    def test_empty_viable_ids_produces_empty_qualified_list(self):
        state = _sealing_state(viable_ids=[])
        # Still rfq_ready → handover ready, but empty material lists
        result = build_handover_payload(state)
        if result["is_handover_ready"]:
            assert result["handover_payload"]["qualified_material_ids"] == []


# ---------------------------------------------------------------------------
# 9–11. Leakage guards
# ---------------------------------------------------------------------------

class TestLeakageGuards:
    def setup_method(self):
        self.result = build_handover_payload(_sealing_state())
        self.payload = self.result["handover_payload"]

    def test_gate_failures_not_in_payload(self):
        assert "gate_failures" not in self.payload

    def test_unknowns_release_blocking_not_in_payload(self):
        assert "unknowns_release_blocking" not in self.payload

    def test_conflicts_not_in_payload(self):
        assert "conflicts" not in self.payload

    def test_review_fields_not_in_payload(self):
        assert "review_required" not in self.payload
        assert "review_state" not in self.payload
        assert "review_reason" not in self.payload
        assert "reviewed_by" not in self.payload

    def test_cycle_internals_not_in_payload(self):
        assert "analysis_cycle_id" not in self.payload
        assert "state_revision" not in self.payload
        assert "cycle" not in self.payload

    def test_observed_raw_not_in_payload(self):
        assert "observed_inputs" not in self.payload
        assert "raw_parameters" not in self.payload

    def test_normalized_internals_not_in_payload(self):
        assert "identity_records" not in self.payload
        assert "normalized_parameters" not in self.payload

    def test_machine_internal_notes_not_in_payload(self):
        result = build_handover_payload(_sealing_state(with_dimensions=True))
        payload = result["handover_payload"]
        dims = payload.get("dimensions", {})
        assert "internal_notes" not in dims

    def test_demo_data_flag_not_in_payload(self):
        assert "demo_data_in_scope" not in self.payload
        assert "is_demo_only" not in self.payload

    def test_selection_status_not_in_payload(self):
        """Internal selection routing fields must not leak into the handover."""
        assert "selection_status" not in self.payload
        assert "output_blocked" not in self.payload
        assert "blocked_candidates" not in self.payload


# ---------------------------------------------------------------------------
# 12. Integration: final_response_node writes handover into sealing_state
# ---------------------------------------------------------------------------

class TestFinalResponseNodeHandoverIntegration:
    def test_final_response_node_writes_handover(self):
        """final_response_node must write sealing_state['handover'] at graph end."""
        import asyncio
        from langchain_core.messages import HumanMessage
        from app.agent.agent.graph import final_response_node
        from app.agent.tests.test_graph_routing import _make_state

        # Build a minimal state with rfq_ready governance
        sealing_state = _sealing_state()
        # Inject selection so final_response_node has something to work with
        sealing_state["selection"] = _selection()
        sealing_state["governance"] = _governance("rfq_ready")
        sealing_state["review"] = _review(False)

        state = _make_state(
            policy_path="structured",
            result_form="direct_answer",
            messages=[HumanMessage(content="test")],
        )
        state["sealing_state"] = sealing_state  # type: ignore[index]

        result = asyncio.run(final_response_node(state))

        new_sealing = result["sealing_state"]
        assert "handover" in new_sealing
        handover = new_sealing["handover"]
        assert "is_handover_ready" in handover

    def test_final_response_node_handover_ready_when_rfq_ready(self):
        import asyncio
        from langchain_core.messages import HumanMessage
        from app.agent.agent.graph import final_response_node
        from app.agent.tests.test_graph_routing import _make_state

        sealing_state = _sealing_state(release_status="rfq_ready")
        sealing_state["selection"] = _selection()
        sealing_state["review"] = _review(False)

        state = _make_state(
            policy_path="structured",
            result_form="direct_answer",
            messages=[HumanMessage(content="test")],
        )
        state["sealing_state"] = sealing_state  # type: ignore[index]

        result = asyncio.run(final_response_node(state))
        handover = result["sealing_state"]["handover"]
        assert handover["is_handover_ready"] is True

    def test_final_response_node_handover_not_ready_when_inadmissible(self):
        import asyncio
        from langchain_core.messages import HumanMessage
        from app.agent.agent.graph import final_response_node
        from app.agent.tests.test_graph_routing import _make_state

        sealing_state = _sealing_state(release_status="inadmissible")
        sealing_state["selection"] = _selection()
        sealing_state["review"] = _review(False)

        state = _make_state(
            policy_path="structured",
            result_form="direct_answer",
            messages=[HumanMessage(content="test")],
        )
        state["sealing_state"] = sealing_state  # type: ignore[index]

        result = asyncio.run(final_response_node(state))
        handover = result["sealing_state"]["handover"]
        assert handover["is_handover_ready"] is False
        assert handover["handover_payload"] is None
