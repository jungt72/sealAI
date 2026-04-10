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
8. handover_payload — is None when handover is not yet admissible
9. Leakage guard — governance internals are NOT in the payload
10. Leakage guard — review fields are NOT in the payload
11. Leakage guard — cycle/observed/normalized internals are NOT in the payload
12. final_response_node writes handover into sealing_state (integration)
"""
from __future__ import annotations

import pytest

from app.agent.agent.commercial import (
    build_dispatch_bridge,
    build_dispatch_dry_run,
    build_dispatch_event,
    build_dispatch_handoff,
    build_dispatch_transport_envelope,
    build_dispatch_trigger,
    build_matching_outcome,
    _is_handover_ready,
    _project_handover_status,
    build_handover_payload,
)
from app.agent.domain.critical_review import CriticalReviewSpecialistResult
from app.agent.agent.graph import final_response_node, selection_node
from app.agent.agent.selection import _resolve_runtime_dispatch_source
from app.agent.agent.state import HandoverLayer, SealingAIState
from app.agent.case_state import build_dispatch_intent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _governance(
    release_status: str = "inquiry_ready",
    rfq_admissibility: str = "ready",
    *,
    unknowns_release_blocking: list[str] | None = None,
    conflicts: list[dict] | None = None,
) -> dict:
    return {
        "release_status": release_status,
        "rfq_admissibility": rfq_admissibility,
        "specificity_level": "compound_required",
        "scope_of_validity": [],
        "assumptions_active": [],
        "gate_failures": ["gate_A_failed"],          # internal — must not leak
        "unknowns_release_blocking": list(unknowns_release_blocking or []),      # internal — must not leak
        "unknowns_manufacturer_validation": [],
        "conflicts": list(conflicts or []),     # internal — must not leak
    }


def _review(
    required: bool = False,
    state: str = "none",
    *,
    critical_review_passed: bool = True,
    critical_review_status: str | None = None,
    blocking_findings: list[str] | None = None,
    soft_findings: list[str] | None = None,
    required_corrections: list[str] | None = None,
) -> dict:
    return {
        "review_required": required,
        "review_state": state,
        "review_reason": "Demo-Daten." if required else "",
        "reviewed_by": None,
        "review_decision": None,
        "review_note": None,
        "critical_review_status": critical_review_status or ("passed" if critical_review_passed else "failed"),
        "critical_review_passed": critical_review_passed,
        "blocking_findings": list(blocking_findings or []),
        "soft_findings": list(soft_findings or []),
        "required_corrections": list(required_corrections or []),
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
        "release_status": "inquiry_ready",
        "rfq_admissibility": "ready",
        "specificity_level": "compound_required",
        "output_blocked": False,
        "recommendation_artifact": {
            "candidate_projection": dict(candidates[0]) if candidates else {},
            "release_status": "inquiry_ready",
            "rfq_admissibility": "ready",
            "specificity_level": "compound_required",
            "output_blocked": False,
        },
        "review_escalation_projection": {
            "status": "releasable",
            "reason": "",
            "missing_items": [],
            "ambiguous_candidate_ids": [],
            "review_meaningful": True,
            "handover_possible": True,
            "human_validation_ready": True,
        },
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
    release_status: str = "inquiry_ready",
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
        assert _is_handover_ready(_governance("inquiry_ready"), _review(False)) is True

    def test_rfq_ready_with_pending_review_is_not_ready(self):
        assert _is_handover_ready(_governance("inquiry_ready"), _review(True, "pending")) is False

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
        gov = _governance("inquiry_ready")
        rev = _review(True, "pending")
        assert _is_handover_ready(gov, rev) is False

    def test_review_approved_does_not_block(self):
        """Once a review is resolved (review_required reset to False), handover may proceed."""
        gov = _governance("inquiry_ready")
        rev = _review(False, "approved")
        assert _is_handover_ready(gov, rev) is True

    def test_missing_critical_review_blocks_even_rfq_ready(self):
        gov = _governance("inquiry_ready")
        rev = {"review_required": False, "review_state": "none"}
        assert _is_handover_ready(gov, rev) is False

    def test_failed_critical_review_blocks_even_without_pending_review(self):
        gov = _governance("inquiry_ready")
        rev = _review(
            False,
            "none",
            critical_review_passed=False,
            blocking_findings=["selected_manufacturer_missing"],
            required_corrections=["Select a deterministic manufacturer candidate before RFQ handover."],
        )
        assert _is_handover_ready(gov, rev) is False


class TestProjectHandoverStatus:
    def test_reviewable_but_not_releasable(self):
        status, reason = _project_handover_status(
            _governance("inadmissible"),
            _review(False),
            {
                **_selection(),
                "review_escalation_projection": {
                    "status": "escalation_needed",
                    "reason": "Engineering escalation required.",
                    "missing_items": [],
                    "ambiguous_candidate_ids": [],
                    "review_meaningful": True,
                    "handover_possible": False,
                    "human_validation_ready": True,
                },
            },
        )
        assert status == "reviewable"
        assert "Engineering escalation" in reason

    def test_handoverable_but_not_releasable(self):
        status, _ = _project_handover_status(
            _governance("manufacturer_validation_required", "provisional"),
            _review(True, "pending"),
            {
                **_selection(),
                "review_escalation_projection": {
                    "status": "review_pending",
                    "reason": "Hersteller-Validierung erforderlich.",
                    "missing_items": [],
                    "ambiguous_candidate_ids": [],
                    "review_meaningful": True,
                    "handover_possible": True,
                    "human_validation_ready": True,
                },
            },
        )
        assert status == "handoverable"

    def test_releasable_and_handoverable(self):
        status, _ = _project_handover_status(
            _governance("inquiry_ready"),
            _review(False),
            _selection(),
        )
        assert status == "releasable"

    def test_insufficient_and_not_handoverable(self):
        status, _ = _project_handover_status(
            _governance("inadmissible"),
            _review(False),
            {
                **_selection([]),
                "review_escalation_projection": {
                    "status": "withheld_missing_core_inputs",
                    "reason": "Required core params are missing.",
                    "missing_items": ["temperature"],
                    "ambiguous_candidate_ids": [],
                    "review_meaningful": False,
                    "handover_possible": False,
                    "human_validation_ready": False,
                },
            },
        )
        assert status == "not_handoverable"


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

    def test_prefers_canonical_rfq_object_for_bounded_payload_basis(self):
        result = build_handover_payload(
            _sealing_state(),
            canonical_rfq_object={
                "qualified_material_ids": ["canonical-mat"],
                "qualified_materials": [{"manufacturer_name": "Canonical"}],
                "confirmed_parameters": {"temperature": {"value": 120.0, "unit": "C"}},
                "dimensions": {"rod_diameter_mm": 14.2},
                "target_system": "canonical_rfq_portal",
            },
            rfq_admissibility="ready",
        )
        assert result["target_system"] == "canonical_rfq_portal"
        assert result["handover_payload"]["qualified_material_ids"] == ["canonical-mat"]
        assert result["handover_payload"]["qualified_materials"] == [{"manufacturer_name": "Canonical"}]
        assert result["handover_payload"]["confirmed_parameters"] == {
            "temperature": {"value": 120.0, "unit": "C"}
        }
        assert result["handover_payload"]["dimensions"] == {"rod_diameter_mm": 14.2}
        assert result["handover_payload"]["rfq_admissibility"] == "ready"

    def test_prefers_canonical_governance_state_for_handover_shell(self):
        result = build_handover_payload(
            _sealing_state(release_status="inadmissible", review_required=True, review_state_str="pending"),
            canonical_case_state={
                "governance_state": {
                    "release_status": "inquiry_ready",
                    "review_required": False,
                    "review_state": "approved",
                    "rfq_admissibility": "ready",
                }
            },
        )
        assert result["is_handover_ready"] is True
        assert result["handover_status"] == "releasable"
        assert result["handover_reason"] == "Governed output is releasable and handover-ready."
        assert result["target_system"] == "rfq_portal"
        assert result["handover_payload"] is not None

    def test_builds_canonical_handover_object_and_preserves_raw_html_body_fallback(self):
        sealing_state = _sealing_state()
        sealing_state["handover"] = {
            "rfq_html_report": "<html>legacy</html>",
            "rfq_confirmed": False,
            "handover_completed": False,
        }
        result = build_handover_payload(
            sealing_state,
            canonical_case_state={
                "governance_state": {
                    "release_status": "inquiry_ready",
                    "review_required": False,
                    "review_state": "approved",
                    "rfq_admissibility": "ready",
                },
                "rfq_state": {
                    "rfq_confirmed": True,
                    "rfq_handover_initiated": True,
                    "rfq_html_report_present": True,
                    "rfq_object": {
                        "qualified_material_ids": ["canonical-mat"],
                        "qualified_materials": [{"manufacturer_name": "Canonical"}],
                        "confirmed_parameters": {"temperature": {"value": 120.0, "unit": "C"}},
                        "dimensions": {"rod_diameter_mm": 14.2},
                        "target_system": "canonical_rfq_portal",
                    },
                },
            },
            rfq_admissibility="ready",
        )
        assert result["is_handover_ready"] is True
        assert result["handover_status"] == "releasable"
        assert result["target_system"] == "canonical_rfq_portal"
        assert result["rfq_confirmed"] is True
        assert result["handover_completed"] is True
        assert result["rfq_html_report_present"] is True
        assert result["rfq_html_report"] == "<html>legacy</html>"
        assert result["handover_payload"]["qualified_material_ids"] == ["canonical-mat"]

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
        assert result["handover_status"] == "handoverable"

    def test_payload_is_none_when_critical_review_is_missing(self):
        state = _sealing_state()
        state["review"] = {"review_required": False, "review_state": "none"}
        result = build_handover_payload(state)
        assert result["is_handover_ready"] is False
        assert result["handover_payload"] is None
        assert result["handover_reason"] == "Critical review is mandatory before RFQ handover."

    def test_payload_is_none_when_critical_review_has_blocking_findings(self):
        state = _sealing_state()
        state["review"] = _review(
            False,
            "none",
            critical_review_passed=False,
            blocking_findings=["selected_manufacturer_missing"],
            required_corrections=["Select a deterministic manufacturer candidate before RFQ handover."],
        )
        result = build_handover_payload(state)
        assert result["is_handover_ready"] is False
        assert result["handover_payload"] is None
        assert "selected_manufacturer_missing" in result["handover_reason"]

    def test_soft_findings_do_not_block_handover_when_critical_review_passes(self):
        state = _sealing_state()
        state["review"] = _review(
            False,
            "none",
            critical_review_passed=True,
            soft_findings=["scope:Manufacturer validation remains required."],
        )
        result = build_handover_payload(state)
        assert result["is_handover_ready"] is True
        assert result["handover_payload"] is not None

    def test_handover_status_present_when_ready(self):
        result = build_handover_payload(_sealing_state())
        assert result["handover_status"] == "releasable"

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
    def test_final_response_node_uses_critical_review_specialist_anchor(self, monkeypatch):
        import asyncio
        from langchain_core.messages import HumanMessage
        import app.agent.agent.graph as graph_module
        from app.agent.tests.test_graph_routing import _make_state

        monkeypatch.setattr(
            graph_module,
            "run_critical_review_specialist",
            lambda *_: CriticalReviewSpecialistResult(
                critical_review_status="failed",
                critical_review_passed=False,
                blocking_findings=("selected_manufacturer_missing",),
                soft_findings=(),
                required_corrections=("Select a deterministic manufacturer candidate before RFQ handover.",),
            ),
        )

        sealing_state = _sealing_state(release_status="inquiry_ready")
        sealing_state["selection"] = _selection()
        sealing_state["review"] = _review(False)

        state = _make_state(
            policy_path="structured",
            result_form="direct_answer",
            messages=[HumanMessage(content="test")],
        )
        state["sealing_state"] = sealing_state  # type: ignore[index]

        result = asyncio.run(final_response_node(state))

        review = result["sealing_state"]["review"]
        handover = result["sealing_state"]["handover"]
        assert review["critical_review_passed"] is False
        assert review["blocking_findings"] == ["selected_manufacturer_missing"]
        assert handover["is_handover_ready"] is False

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
        sealing_state["governance"] = _governance("inquiry_ready")
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

        sealing_state = _sealing_state(release_status="inquiry_ready")
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
        case_state = result["case_state"]
        assert case_state["rfq_state"]["handover_ready"] is True
        assert case_state["rfq_state"]["handover_status"] == handover["handover_status"]
        assert case_state["matching_state"]["matching_outcome"] is not None
        assert isinstance(case_state["recipient_selection"]["selection_status"], str)
        assert (
            case_state["rfq_state"]["rfq_dispatch"]["recipient_basis_summary"]["handover_ready"]
            is True
        )

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

    def test_final_response_node_preserves_and_mirrors_bounded_rfq_lifecycle_flags(self):
        import asyncio
        from langchain_core.messages import HumanMessage
        from app.agent.agent.graph import final_response_node
        from app.agent.tests.test_graph_routing import _make_state

        sealing_state = _sealing_state(release_status="inquiry_ready")
        sealing_state["selection"] = _selection()
        sealing_state["review"] = _review(False)

        state = _make_state(
            policy_path="structured",
            result_form="direct_answer",
            messages=[HumanMessage(content="test")],
        )
        state["sealing_state"] = sealing_state  # type: ignore[index]
        state["case_state"] = {
            "rfq_state": {
                "rfq_confirmed": True,
                "rfq_handover_initiated": True,
                "rfq_html_report_present": True,
            }
        }

        result = asyncio.run(final_response_node(state))

        rfq_state = result["case_state"]["rfq_state"]
        handover = result["sealing_state"]["handover"]
        assert rfq_state["rfq_admissibility"] == "ready"
        assert rfq_state["status"] == "ready"
        assert rfq_state["handover_ready"] is True
        assert rfq_state["handover_status"] == handover["handover_status"]
        assert rfq_state["rfq_confirmed"] is True
        assert rfq_state["rfq_handover_initiated"] is True
        assert rfq_state["rfq_html_report_present"] is True
        assert handover["rfq_confirmed"] is True
        assert handover["handover_completed"] is True
        assert handover["rfq_html_report_present"] is True

    def test_final_response_node_prefers_canonical_rfq_object_basis_for_handover_payload(self):
        import asyncio
        from langchain_core.messages import HumanMessage
        from app.agent.agent.graph import final_response_node
        from app.agent.tests.test_graph_routing import _make_state

        sealing_state = _sealing_state(release_status="inquiry_ready")
        sealing_state["selection"] = _selection()
        sealing_state["review"] = _review(False)

        state = _make_state(
            policy_path="structured",
            result_form="direct_answer",
            messages=[HumanMessage(content="test")],
        )
        state["sealing_state"] = sealing_state  # type: ignore[index]
        state["case_state"] = {
            "rfq_state": {
                "rfq_admissibility": "ready",
                "rfq_object": {
                    "object_type": "rfq_payload_basis",
                    "object_version": "rfq_payload_basis_v1",
                    "qualified_material_ids": ["canonical-mat"],
                    "qualified_materials": [
                        {
                            "candidate_id": "canonical-mat",
                            "material_family": "PTFE",
                            "grade_name": "G25",
                            "manufacturer_name": "Canonical Materials",
                        }
                    ],
                    "confirmed_parameters": {
                        "temperature": {"value": 120.0, "unit": "C"},
                        "pressure": {"value": 8.0, "unit": "bar"},
                    },
                    "dimensions": {"rod_diameter_mm": 14.2},
                    "target_system": "canonical_rfq_portal",
                },
            }
        }

        result = asyncio.run(final_response_node(state))

        rfq_object = result["case_state"]["rfq_state"]["rfq_object"]
        handover = result["sealing_state"]["handover"]
        handover_payload = handover["handover_payload"]

        assert rfq_object["qualified_material_ids"] == ["canonical-mat"]
        assert rfq_object["qualified_materials"][0]["manufacturer_name"] == "Canonical Materials"
        assert rfq_object["confirmed_parameters"] == {
            "temperature": {"value": 120.0, "unit": "C"},
            "pressure": {"value": 8.0, "unit": "bar"},
        }
        assert rfq_object["dimensions"] == {"rod_diameter_mm": 14.2}
        assert rfq_object["target_system"] == "canonical_rfq_portal"

        assert handover["target_system"] == "canonical_rfq_portal"
        assert handover_payload["qualified_material_ids"] == ["canonical-mat"]
        assert handover_payload["qualified_materials"][0]["manufacturer_name"] == "Canonical Materials"
        assert handover_payload["confirmed_parameters"] == {
            "temperature": {"value": 120.0, "unit": "C"},
            "pressure": {"value": 8.0, "unit": "bar"},
        }
        assert handover_payload["dimensions"] == {"rod_diameter_mm": 14.2}
        assert handover_payload["rfq_admissibility"] == "ready"

    def test_build_matching_outcome_prefers_canonical_winner_candidate(self):
        outcome = build_matching_outcome(
            {
                "case_state": {
                    "matching_state": {
                        "matchable": True,
                        "matchability_status": "ready_for_matching",
                        "winner_candidate_id": "fkm::v75::freudenberg",
                        "match_candidates": [
                            {
                                "candidate_id": "fkm::v75::freudenberg",
                                "candidate_kind": "manufacturer_grade",
                                "material_family": "FKM",
                                "grade_name": "V75",
                                "manufacturer_name": "Freudenberg",
                                "viability_status": "viable",
                            }
                        ],
                        "requirement_class_hint": "compound::fkm::v75::freudenberg",
                    },
                    "manufacturer_state": {
                        "manufacturer_refs": [
                            {
                                "manufacturer_name": "Freudenberg",
                                "candidate_ids": ["fkm::v75::freudenberg"],
                            }
                        ]
                    },
                    "result_contract": {
                        "recommendation_identity": {
                            "candidate_id": "fkm::v75::freudenberg",
                            "manufacturer_name": "Freudenberg",
                        }
                    },
                },
                "sealing_state": {"selection": _selection()},
            }
        )

        assert outcome["status"] == "matched_primary_candidate"
        assert outcome["primary_match_candidate"]["candidate_id"] == "fkm::v75::freudenberg"
        assert outcome["selected_manufacturer_ref"]["manufacturer_name"] == "Freudenberg"

    def test_build_matching_outcome_prefers_canonical_requirement_class_and_recipient_selection(self):
        outcome = build_matching_outcome(
            {
                "case_state": {
                    "matching_state": {
                        "matchable": True,
                        "matchability_status": "ready_for_matching",
                        "winner_candidate_id": "fkm::v75::freudenberg",
                        "match_candidates": [
                            {
                                "candidate_id": "fkm::v75::freudenberg",
                                "candidate_kind": "manufacturer_grade",
                                "material_family": "FKM",
                                "grade_name": "V75",
                                "manufacturer_name": "Freudenberg",
                                "viability_status": "viable",
                            }
                        ],
                        "requirement_class_hint": "legacy::wrong",
                    },
                    "recipient_selection": {
                        "selected_recipient_refs": [],
                        "candidate_recipient_refs": [
                            {
                                "manufacturer_name": "Freudenberg",
                                "candidate_ids": ["fkm::v75::freudenberg"],
                                "material_families": ["FKM"],
                                "grade_names": ["V75"],
                                "candidate_kinds": ["manufacturer_grade"],
                                "capability_hints": ["manufacturer_grade_candidate"],
                                "source_refs": ["recommendation_identity", "match_candidate"],
                                "qualified_for_rfq": False,
                            }
                        ],
                    },
                    "manufacturer_state": {
                        "manufacturer_refs": [
                            {
                                "manufacturer_name": "OtherCorp",
                                "candidate_ids": ["other::candidate"],
                            }
                        ],
                        "manufacturer_capabilities": [
                            {
                                "object_type": "manufacturer_capability",
                                "object_version": "manufacturer_capability_v1",
                                "manufacturer_name": "Freudenberg",
                                "capability_sources": ["match_candidate"],
                                "capability_hints": ["manufacturer_grade_candidate"],
                                "material_families": ["FKM"],
                                "grade_names": ["V75"],
                                "candidate_kinds": ["manufacturer_grade"],
                                "candidate_ids": ["fkm::v75::freudenberg"],
                                "requirement_class_ids": ["compound::fkm::v75::freudenberg"],
                                "rfq_qualified": False,
                            }
                        ],
                    },
                    "result_contract": {
                        "recommendation_identity": {
                            "candidate_id": "fkm::v75::freudenberg",
                            "manufacturer_name": "Freudenberg",
                        },
                        "requirement_class": {
                            "object_type": "requirement_class",
                            "object_version": "requirement_class_v1",
                            "requirement_class_id": "compound::fkm::v75::freudenberg",
                        },
                        "requirement_class_hint": "legacy::wrong",
                    },
                },
                "sealing_state": {"selection": _selection()},
            }
        )

        assert outcome["status"] == "matched_primary_candidate"
        assert outcome["requirement_class"]["requirement_class_id"] == "compound::fkm::v75::freudenberg"
        assert outcome["requirement_class_hint"] == "compound::fkm::v75::freudenberg"
        assert outcome["selected_manufacturer_ref"]["manufacturer_name"] == "Freudenberg"

    def test_build_matching_outcome_prefers_existing_canonical_matching_outcome_core_slice(self):
        outcome = build_matching_outcome(
            {
                "case_state": {
                    "matching_state": {
                        "matchable": True,
                        "matchability_status": "ready_for_matching",
                        "winner_candidate_id": "fkm::v75::freudenberg",
                        "match_candidates": [
                            {
                                "candidate_id": "fkm::v75::freudenberg",
                                "candidate_kind": "manufacturer_grade",
                                "material_family": "FKM",
                                "grade_name": "V75",
                                "manufacturer_name": "Freudenberg",
                                "viability_status": "viable",
                            }
                        ],
                        "matching_outcome": {
                            "status": "blocked_review_required",
                            "reason": "Canonical review block.",
                            "matchability_status": "ready_for_matching",
                            "primary_match_candidate": {
                                "candidate_id": "canonical::candidate",
                                "manufacturer_name": "Canonical",
                            },
                            "selected_manufacturer_ref": {
                                "manufacturer_name": "Canonical",
                                "candidate_ids": ["canonical::candidate"],
                            },
                        },
                    },
                    "manufacturer_state": {
                        "manufacturer_refs": [
                            {
                                "manufacturer_name": "Freudenberg",
                                "candidate_ids": ["fkm::v75::freudenberg"],
                            }
                        ]
                    },
                    "result_contract": {
                        "recommendation_identity": {
                            "candidate_id": "fkm::v75::freudenberg",
                            "manufacturer_name": "Freudenberg",
                        }
                    },
                },
                "sealing_state": {"selection": _selection()},
            }
        )

        assert outcome["status"] == "blocked_review_required"
        assert outcome["reason"] == "Canonical review block."
        assert outcome["primary_match_candidate"]["candidate_id"] == "canonical::candidate"
        assert outcome["selected_manufacturer_ref"]["manufacturer_name"] == "Canonical"

    def test_build_matching_outcome_preserves_legacy_fallback_when_canonical_objects_absent(self):
        outcome = build_matching_outcome(
            {
                "case_state": {
                    "matching_state": {
                        "matchable": True,
                        "matchability_status": "ready_for_matching",
                        "winner_candidate_id": "fkm::v75::freudenberg",
                        "match_candidates": [
                            {
                                "candidate_id": "fkm::v75::freudenberg",
                                "candidate_kind": "manufacturer_grade",
                                "material_family": "FKM",
                                "grade_name": "V75",
                                "manufacturer_name": "Freudenberg",
                                "viability_status": "viable",
                            }
                        ],
                        "requirement_class_hint": "compound::fkm::v75::freudenberg",
                    },
                    "manufacturer_state": {
                        "manufacturer_refs": [
                            {
                                "manufacturer_name": "Freudenberg",
                                "candidate_ids": ["fkm::v75::freudenberg"],
                            }
                        ]
                    },
                    "result_contract": {
                        "recommendation_identity": {
                            "candidate_id": "fkm::v75::freudenberg",
                            "manufacturer_name": "Freudenberg",
                        }
                    },
                },
                "sealing_state": {"selection": _selection()},
            }
        )

        assert outcome["requirement_class"] is None
        assert outcome["requirement_class_hint"] == "compound::fkm::v75::freudenberg"
        assert outcome["selected_manufacturer_ref"]["manufacturer_name"] == "Freudenberg"

    def test_final_response_node_writes_matching_outcome(self):
        import asyncio
        from langchain_core.messages import HumanMessage
        from app.agent.agent.graph import final_response_node
        from app.agent.tests.test_graph_routing import _make_state

        sealing_state = _sealing_state(release_status="inquiry_ready")
        sealing_state["selection"] = _selection()
        sealing_state["review"] = _review(False)

        state = _make_state(
            policy_path="structured",
            result_form="direct_answer",
            messages=[HumanMessage(content="test")],
        )
        state["sealing_state"] = sealing_state  # type: ignore[index]
        state["case_state"] = {
            "matching_state": {
                "matchable": True,
                "matchability_status": "ready_for_matching",
                "winner_candidate_id": "fkm::v75::freudenberg",
                "match_candidates": [
                    {
                        "candidate_id": "fkm::v75::freudenberg",
                        "candidate_kind": "manufacturer_grade",
                        "material_family": "FKM",
                        "grade_name": "V75",
                        "manufacturer_name": "Freudenberg",
                        "viability_status": "viable",
                    }
                ],
                "requirement_class_hint": "compound::fkm::v75::freudenberg",
            },
            "manufacturer_state": {
                "manufacturer_refs": [
                    {
                        "manufacturer_name": "Freudenberg",
                        "candidate_ids": ["fkm::v75::freudenberg"],
                    }
                ]
            },
            "result_contract": {
                "recommendation_identity": {
                    "candidate_id": "fkm::v75::freudenberg",
                    "manufacturer_name": "Freudenberg",
                }
            },
        }  # type: ignore[index]

        result = asyncio.run(final_response_node(state))
        matching_outcome = result["sealing_state"]["matching_outcome"]
        assert matching_outcome["status"] == "matched_primary_candidate"
        assert matching_outcome["primary_match_candidate"]["candidate_id"] == "fkm::v75::freudenberg"

    def test_final_response_node_uses_bounded_manufacturer_rfq_matching_anchor(self, monkeypatch):
        import asyncio
        from langchain_core.messages import HumanMessage
        import app.agent.agent.graph as graph_module
        from app.agent.tests.test_graph_routing import _make_state

        monkeypatch.setattr(
            graph_module,
            "build_manufacturer_match_result_from_runtime_state",
            lambda *_: {
                "status": "matched_primary_candidate",
                "reason": "Bounded specialist runtime adapter.",
                "matchability_status": "ready_for_matching",
                "primary_match_candidate": {"candidate_id": "bounded::candidate"},
                "selected_manufacturer_ref": {"manufacturer_name": "BoundedCo"},
            },
        )

        sealing_state = _sealing_state(release_status="inquiry_ready")
        sealing_state["selection"] = _selection()
        sealing_state["review"] = _review(False)

        state = _make_state(
            policy_path="structured",
            result_form="direct_answer",
            messages=[HumanMessage(content="test")],
        )
        state["sealing_state"] = sealing_state  # type: ignore[index]

        result = asyncio.run(final_response_node(state))

        assert result["sealing_state"]["matching_outcome"]["selected_manufacturer_ref"]["manufacturer_name"] == "BoundedCo"

    def test_selection_node_supplies_case_state_with_matching_outcome_before_reply(self):
        from app.agent.tests.test_graph_routing import _make_state
        import asyncio
        from langchain_core.messages import HumanMessage

        sealing_state = _sealing_state(release_status="inquiry_ready")
        sealing_state["selection"] = _selection()
        sealing_state["review"] = _review(False)

        state = _make_state(
            policy_path="structured",
            result_form="direct_answer",
            messages=[HumanMessage(content="test")],
        )
        state["sealing_state"] = sealing_state  # type: ignore[index]
        state["case_state"] = {
            "case_meta": {
                "binding_level": "ORIENTATION",
                "runtime_path": "STRUCTURED_QUALIFICATION",
            },
            "recipient_selection": {"selected_partner_id": "Freudenberg"},
        }

        result = selection_node(state)

        assert "case_state" in result
        case_state = result["case_state"]
        assert case_state["matching_state"]["matching_outcome"] is not None
        assert case_state["rfq_state"]["rfq_dispatch"]["dispatch_status"] in {
            "not_ready_dispatch_blocked",
            "dispatch_ready",
            "not_ready_no_recipients",
        }
        assert isinstance(case_state["recipient_selection"]["selection_status"], str)
        assert case_state["recipient_selection"]["selected_partner_id"] == "Freudenberg"
        assert result["sealing_state"]["selection"]["selected_partner_id"] == "Freudenberg"
        dispatch_intent = case_state["dispatch_intent"]
        canonical_dispatch = case_state["rfq_state"]["rfq_dispatch"]
        assert dispatch_intent["dispatch_status"] == canonical_dispatch["dispatch_status"]
        assert dispatch_intent["dispatch_ready"] == canonical_dispatch["dispatch_ready"]
        assert dispatch_intent["recipient_refs"] == canonical_dispatch["recipient_refs"]
        assert dispatch_intent["source"] == "canonical_rfq_dispatch"
        dispatch_trigger = case_state["dispatch_trigger"]
        assert dispatch_trigger["trigger_status"] in {
            "trigger_ready",
            "trigger_blocked_dispatch_not_ready",
            "trigger_blocked_no_recipients",
        }
        assert dispatch_trigger["recipient_refs"] == dispatch_intent["recipient_refs"]
        assert dispatch_trigger["source"] == "dispatch_intent"
        dispatch_dry_run = case_state["dispatch_dry_run"]
        assert dispatch_dry_run["dry_run_status"] in {
            "dry_run_ready",
            "dry_run_blocked",
            "dry_run_blocked_no_recipients",
        }
        assert dispatch_dry_run["recipient_refs"] == dispatch_trigger["recipient_refs"]
        assert dispatch_dry_run["trigger_source"] == dispatch_trigger["source"]
        assert dispatch_dry_run["source"] == "dispatch_trigger"
        dispatch_event = case_state["dispatch_event"]
        assert dispatch_event["event_status"] in {
            "event_dispatch_would_run",
            "event_dispatch_blocked",
            "event_dispatch_no_recipients",
            "event_dispatch_missing_basis",
        }
        assert dispatch_event["recipient_refs"] == dispatch_trigger["recipient_refs"]
        assert dispatch_event["trigger_source"] == dispatch_trigger["source"]
        assert dispatch_event["dry_run_status"] == dispatch_dry_run["dry_run_status"]
        assert dispatch_event["source"] == "dispatch_trigger"

    def test_selection_node_uses_bounded_manufacturer_rfq_matching_anchor(self, monkeypatch):
        import app.agent.agent.graph as graph_module
        from app.agent.tests.test_graph_routing import _make_state
        from langchain_core.messages import HumanMessage

        monkeypatch.setattr(
            graph_module,
            "build_manufacturer_match_result_from_runtime_state",
            lambda *_: {
                "status": "matched_primary_candidate",
                "reason": "Bounded specialist runtime adapter.",
                "matchability_status": "ready_for_matching",
                "selected_manufacturer_ref": {"manufacturer_name": "BoundedCo"},
            },
        )

        sealing_state = _sealing_state(release_status="inquiry_ready")
        sealing_state["selection"] = _selection()
        sealing_state["review"] = _review(False)

        state = _make_state(
            policy_path="structured",
            result_form="direct_answer",
            messages=[HumanMessage(content="test")],
        )
        state["sealing_state"] = sealing_state  # type: ignore[index]

        result = selection_node(state)

        assert result["sealing_state"]["matching_outcome"]["selected_manufacturer_ref"]["manufacturer_name"] == "BoundedCo"

    def test_final_response_node_prefers_same_turn_canonical_case_state_for_reply(self):
        import asyncio
        from unittest.mock import patch
        from langchain_core.messages import HumanMessage
        from app.agent.agent.graph import final_response_node
        from app.agent.tests.test_graph_routing import _make_state

        sealing_state = _sealing_state(release_status="inquiry_ready")
        sealing_state["selection"] = {
            **_selection(),
            "release_status": "manufacturer_validation_required",
            "rfq_admissibility": "provisional",
            "specificity_level": "family_only",
        }
        sealing_state["review"] = _review(False)

        state = _make_state(
            policy_path="structured",
            result_form="direct_answer",
            messages=[HumanMessage(content="test")],
        )
        state["sealing_state"] = sealing_state  # type: ignore[index]

        seen: dict = {}

        def _fake_build_final_reply(selection_state_arg, **kwargs):
            seen["selection_state"] = selection_state_arg
            seen["case_state"] = kwargs.get("case_state")
            return "canonical-case-state-reply"

        with patch("app.agent.agent.graph.build_final_reply", side_effect=_fake_build_final_reply):
            result = asyncio.run(final_response_node(state))

        assert result["messages"][0].content == "canonical-case-state-reply"
        assert seen["selection_state"]["release_status"] == "manufacturer_validation_required"
        assert seen["case_state"]["rfq_state"]["rfq_dispatch"]["dispatch_ready"] is True
        assert seen["case_state"]["recipient_selection"]["selection_status"] == "selected_recipient"
        assert result["case_state"]["rfq_state"]["rfq_dispatch"]["dispatch_ready"] is True
        assert result["case_state"]["recipient_selection"]["selection_status"] == "selected_recipient"


def test_dispatch_source_prefers_dispatch_intent_where_present():
    canonical_case_state = {
        "dispatch_intent": {"dispatch_ready": False, "dispatch_status": "blocked"},
        "rfq_state": {"rfq_dispatch": {"dispatch_ready": True, "dispatch_status": "dispatch_ready"}},
    }
    source = _resolve_runtime_dispatch_source(canonical_case_state)
    assert source["dispatch_status"] == "blocked"
    assert source["dispatch_ready"] is False


def test_dispatch_source_falls_back_to_rfq_dispatch_when_intent_missing():
    canonical_case_state = {
        "rfq_state": {"rfq_dispatch": {"dispatch_ready": True, "dispatch_status": "dispatch_ready"}},
    }
    source = _resolve_runtime_dispatch_source(canonical_case_state)
    assert source["dispatch_status"] == "dispatch_ready"
    assert source["dispatch_ready"] is True


@pytest.mark.parametrize(
    "state_input,expected_status,expected_allowed,expected_source",
    [
        (
            {
                "case_state": {
                    "dispatch_intent": {
                        "dispatch_ready": True,
                        "dispatch_status": "dispatch_ready",
                        "recipient_refs": [{"manufacturer_name": "Acme"}],
                    }
                }
            },
            "trigger_ready",
            True,
            "dispatch_intent",
        ),
        (
            {
                "case_state": {
                    "dispatch_intent": {
                        "dispatch_ready": False,
                        "dispatch_status": "not_ready_no_recipients",
                        "dispatch_blockers": ["no_recipient_refs"],
                        "recipient_refs": [],
                    }
                }
            },
            "trigger_blocked_no_recipients",
            False,
            "dispatch_intent",
        ),
        (
            {
                "case_state": {
                    "rfq_state": {
                        "rfq_dispatch": {
                            "dispatch_ready": False,
                            "dispatch_status": "not_ready_dispatch_blocked",
                            "dispatch_blockers": ["review_required"],
                            "recipient_refs": [{"manufacturer_name": "Acme"}],
                        }
                    }
                }
            },
            "trigger_blocked_dispatch_not_ready",
            False,
            "canonical_rfq_dispatch_fallback",
        ),
    ],
)
def test_build_dispatch_trigger_prefers_intent_and_falls_back_truthfully(
    state_input,
    expected_status,
    expected_allowed,
    expected_source,
):
    trigger = build_dispatch_trigger(state_input)

    assert trigger["trigger_status"] == expected_status
    assert trigger["trigger_allowed"] is expected_allowed
    assert trigger["source"] == expected_source


@pytest.mark.parametrize(
    "state_input,expected_status,expected_ready,expected_dispatch",
    [
        (
            {
                "case_state": {
                    "dispatch_trigger": {
                        "trigger_allowed": True,
                        "trigger_status": "trigger_ready",
                        "recipient_refs": [{"manufacturer_name": "Acme"}],
                        "source": "dispatch_intent",
                    }
                }
            },
            "dry_run_ready",
            True,
            True,
        ),
        (
            {
                "case_state": {
                    "dispatch_trigger": {
                        "trigger_allowed": False,
                        "trigger_status": "trigger_blocked_no_recipients",
                        "trigger_blockers": ["no_recipient_refs"],
                        "recipient_refs": [],
                        "source": "dispatch_intent",
                    }
                }
            },
            "dry_run_blocked_no_recipients",
            False,
            False,
        ),
        (
            {
                "case_state": {
                    "dispatch_trigger": {
                        "trigger_allowed": False,
                        "trigger_status": "trigger_blocked_dispatch_not_ready",
                        "trigger_blockers": ["review_required"],
                        "recipient_refs": [{"manufacturer_name": "Acme"}],
                        "source": "canonical_rfq_dispatch_fallback",
                    }
                }
            },
            "dry_run_blocked",
            False,
            False,
        ),
    ],
)
def test_build_dispatch_dry_run_reflects_trigger_truthfully(
    state_input,
    expected_status,
    expected_ready,
    expected_dispatch,
):
    dry_run = build_dispatch_dry_run(state_input)

    assert dry_run["dry_run_status"] == expected_status
    assert dry_run["dry_run_ready"] is expected_ready
    assert dry_run["would_dispatch"] is expected_dispatch
    assert dry_run["source"] == "dispatch_trigger"


@pytest.mark.parametrize(
    "state_input,expected_status,expected_kind,expected_dispatch",
    [
        (
            {
                "case_state": {
                    "dispatch_trigger": {
                        "trigger_allowed": True,
                        "trigger_status": "trigger_ready",
                        "recipient_refs": [{"manufacturer_name": "Acme"}],
                        "source": "dispatch_intent",
                    },
                    "dispatch_dry_run": {"dry_run_status": "dry_run_ready"},
                }
            },
            "event_dispatch_would_run",
            "dispatch_would_run",
            True,
        ),
        (
            {
                "case_state": {
                    "dispatch_trigger": {
                        "trigger_allowed": False,
                        "trigger_status": "trigger_blocked_no_recipients",
                        "trigger_blockers": ["no_recipient_refs"],
                        "recipient_refs": [],
                        "source": "dispatch_intent",
                    },
                    "dispatch_dry_run": {"dry_run_status": "dry_run_blocked_no_recipients"},
                }
            },
            "event_dispatch_no_recipients",
            "dispatch_no_recipients",
            False,
        ),
        (
            {
                "case_state": {
                    "dispatch_trigger": {
                        "trigger_allowed": False,
                        "trigger_status": "trigger_blocked_missing_dispatch_basis",
                        "trigger_blockers": ["missing_dispatch_basis"],
                        "recipient_refs": [],
                        "source": "missing_dispatch_basis",
                    },
                    "dispatch_dry_run": {"dry_run_status": "dry_run_blocked_missing_dispatch_basis"},
                }
            },
            "event_dispatch_missing_basis",
            "dispatch_missing_basis",
            False,
        ),
    ],
)
def test_build_dispatch_event_reflects_trigger_truthfully(
    state_input,
    expected_status,
    expected_kind,
    expected_dispatch,
):
    event = build_dispatch_event(state_input)

    assert event["event_status"] == expected_status
    assert event["event_kind"] == expected_kind
    assert event["would_dispatch"] is expected_dispatch
    assert event["source"] == "dispatch_trigger"
    assert event["event_id"] == f"dispatch_event::{event['event_key']}"
    assert event["event_identity"]["event_status"] == expected_status


def test_build_dispatch_event_identity_is_deterministic_for_same_runtime_state():
    state_input = {
        "case_state": {
            "case_meta": {
                "session_id": "case-1",
                "analysis_cycle_id": "cycle-1",
                "state_revision": 7,
            },
            "dispatch_trigger": {
                "trigger_allowed": True,
                "trigger_status": "trigger_ready",
                "recipient_refs": [{"manufacturer_name": "Acme", "candidate_ids": ["ptfe::g25::acme"]}],
                "selected_manufacturer_ref": {"manufacturer_name": "Acme", "candidate_ids": ["ptfe::g25::acme"]},
                "requirement_class": {"requirement_class_id": "compound::ptfe::g25::acme"},
                "recommendation_identity": {"candidate_id": "ptfe::g25::acme"},
                "source": "dispatch_intent",
            },
            "dispatch_dry_run": {"dry_run_status": "dry_run_ready"},
        }
    }

    first_event = build_dispatch_event(state_input)
    second_event = build_dispatch_event(state_input)

    assert first_event["event_key"] == second_event["event_key"]
    assert first_event["event_id"] == second_event["event_id"]
    assert first_event["event_identity"] == second_event["event_identity"]


def test_build_dispatch_event_identity_changes_when_material_dispatch_state_changes():
    base_state = {
        "case_state": {
            "case_meta": {
                "session_id": "case-1",
                "analysis_cycle_id": "cycle-1",
                "state_revision": 7,
            },
            "dispatch_trigger": {
                "trigger_allowed": True,
                "trigger_status": "trigger_ready",
                "recipient_refs": [{"manufacturer_name": "Acme", "candidate_ids": ["ptfe::g25::acme"]}],
                "selected_manufacturer_ref": {"manufacturer_name": "Acme", "candidate_ids": ["ptfe::g25::acme"]},
                "requirement_class": {"requirement_class_id": "compound::ptfe::g25::acme"},
                "recommendation_identity": {"candidate_id": "ptfe::g25::acme"},
                "source": "dispatch_intent",
            },
            "dispatch_dry_run": {"dry_run_status": "dry_run_ready"},
        }
    }
    changed_state = {
        "case_state": {
            "case_meta": {
                "session_id": "case-1",
                "analysis_cycle_id": "cycle-1",
                "state_revision": 8,
            },
            "dispatch_trigger": {
                "trigger_allowed": False,
                "trigger_status": "trigger_blocked_no_recipients",
                "trigger_blockers": ["no_recipient_refs"],
                "recipient_refs": [],
                "selected_manufacturer_ref": None,
                "requirement_class": {"requirement_class_id": "compound::ptfe::g25::acme"},
                "recommendation_identity": {"candidate_id": "ptfe::g25::acme"},
                "source": "dispatch_intent",
            },
            "dispatch_dry_run": {"dry_run_status": "dry_run_blocked_no_recipients"},
        }
    }

    base_event = build_dispatch_event(base_state)
    changed_event = build_dispatch_event(changed_state)

    assert base_event["event_key"] != changed_event["event_key"]
    assert base_event["event_id"] != changed_event["event_id"]
    assert base_event["event_identity"] != changed_event["event_identity"]


@pytest.mark.parametrize(
    "state_input,expected_status,expected_ready",
    [
        (
            {
                "case_state": {
                    "dispatch_event": {
                        "event_id": "dispatch_event::abc",
                        "event_key": "abc",
                        "event_status": "event_dispatch_would_run",
                        "event_blockers": [],
                        "would_dispatch": True,
                        "recipient_refs": [{"manufacturer_name": "Acme"}],
                        "requirement_class": {"requirement_class_id": "compound::ptfe::g25::acme"},
                        "recommendation_identity": {"candidate_id": "ptfe::g25::acme"},
                        "event_identity": {"trigger_status": "trigger_ready"},
                        "dry_run_status": "dry_run_ready",
                    }
                }
            },
            "bridge_ready",
            True,
        ),
        (
            {
                "case_state": {
                    "dispatch_event": {
                        "event_id": "dispatch_event::def",
                        "event_key": "def",
                        "event_status": "event_dispatch_no_recipients",
                        "event_blockers": ["no_recipient_refs"],
                        "would_dispatch": False,
                        "recipient_refs": [],
                        "event_identity": {"trigger_status": "trigger_blocked_no_recipients"},
                        "dry_run_status": "dry_run_blocked_no_recipients",
                    }
                }
            },
            "bridge_blocked_no_recipients",
            False,
        ),
        (
            {
                "case_state": {
                    "dispatch_event": {
                        "event_id": "dispatch_event::ghi",
                        "event_key": "ghi",
                        "event_status": "event_dispatch_missing_basis",
                        "event_blockers": ["missing_dispatch_basis"],
                        "would_dispatch": False,
                        "recipient_refs": [],
                        "event_identity": {"trigger_status": "trigger_blocked_missing_dispatch_basis"},
                        "dry_run_status": "dry_run_blocked_missing_dispatch_basis",
                    }
                }
            },
            "bridge_blocked_missing_basis",
            False,
        ),
    ],
)
def test_build_dispatch_bridge_reflects_event_truthfully(
    state_input,
    expected_status,
    expected_ready,
):
    bridge = build_dispatch_bridge(state_input)

    assert bridge["bridge_status"] == expected_status
    assert bridge["bridge_ready"] is expected_ready
    assert bridge["source"] == "dispatch_event"
    assert bridge["event_id"] == state_input["case_state"]["dispatch_event"]["event_id"]
    assert bridge["event_key"] == state_input["case_state"]["dispatch_event"]["event_key"]


@pytest.mark.parametrize(
    "state_input,expected_status,expected_ready",
    [
        (
            {
                "case_state": {
                    "dispatch_bridge": {
                        "bridge_ready": True,
                        "bridge_status": "bridge_ready",
                        "bridge_blockers": [],
                        "event_id": "dispatch_event::abc",
                        "event_key": "abc",
                        "recipient_refs": [{"manufacturer_name": "Acme"}],
                        "requirement_class": {"requirement_class_id": "compound::ptfe::g25::acme"},
                        "recommendation_identity": {"candidate_id": "ptfe::g25::acme"},
                    }
                }
            },
            "handoff_ready",
            True,
        ),
        (
            {
                "case_state": {
                    "dispatch_bridge": {
                        "bridge_ready": False,
                        "bridge_status": "bridge_blocked_no_recipients",
                        "bridge_blockers": ["no_recipient_refs"],
                        "event_id": "dispatch_event::def",
                        "event_key": "def",
                        "recipient_refs": [],
                    }
                }
            },
            "handoff_blocked_no_recipients",
            False,
        ),
        (
            {
                "case_state": {
                    "dispatch_bridge": {
                        "bridge_ready": False,
                        "bridge_status": "bridge_blocked_missing_basis",
                        "bridge_blockers": ["missing_dispatch_basis"],
                        "event_id": "dispatch_event::ghi",
                        "event_key": "ghi",
                        "recipient_refs": [],
                    }
                }
            },
            "handoff_blocked_missing_basis",
            False,
        ),
    ],
)
def test_build_dispatch_handoff_reflects_bridge_truthfully(
    state_input,
    expected_status,
    expected_ready,
):
    handoff = build_dispatch_handoff(state_input)

    assert handoff["handoff_status"] == expected_status
    assert handoff["handoff_ready"] is expected_ready
    assert handoff["source"] == "dispatch_bridge"
    assert handoff["event_id"] == state_input["case_state"]["dispatch_bridge"]["event_id"]
    assert handoff["event_key"] == state_input["case_state"]["dispatch_bridge"]["event_key"]


@pytest.mark.parametrize(
    "state_input,expected_status,expected_ready",
    [
        (
            {
                "case_state": {
                    "dispatch_handoff": {
                        "handoff_ready": True,
                        "handoff_status": "handoff_ready",
                        "handoff_blockers": [],
                        "event_id": "dispatch_event::abc",
                        "event_key": "abc",
                        "recipient_refs": [{"manufacturer_name": "Acme"}],
                        "requirement_class": {"requirement_class_id": "compound::ptfe::g25::acme"},
                        "recommendation_identity": {"candidate_id": "ptfe::g25::acme"},
                    }
                }
            },
            "envelope_ready",
            True,
        ),
        (
            {
                "case_state": {
                    "dispatch_handoff": {
                        "handoff_ready": False,
                        "handoff_status": "handoff_blocked_no_recipients",
                        "handoff_blockers": ["no_recipient_refs"],
                        "event_id": "dispatch_event::def",
                        "event_key": "def",
                        "recipient_refs": [],
                    }
                }
            },
            "envelope_blocked_no_recipients",
            False,
        ),
        (
            {
                "case_state": {
                    "dispatch_handoff": {
                        "handoff_ready": False,
                        "handoff_status": "handoff_blocked_missing_basis",
                        "handoff_blockers": ["missing_dispatch_basis"],
                        "event_id": "dispatch_event::ghi",
                        "event_key": "ghi",
                        "recipient_refs": [],
                    }
                }
            },
            "envelope_blocked_missing_basis",
            False,
        ),
    ],
)
def test_build_dispatch_transport_envelope_reflects_handoff_truthfully(
    state_input,
    expected_status,
    expected_ready,
):
    envelope = build_dispatch_transport_envelope(state_input)

    assert envelope["envelope_status"] == expected_status
    assert envelope["envelope_ready"] is expected_ready
    assert envelope["source"] == "dispatch_handoff"
    assert envelope["event_id"] == state_input["case_state"]["dispatch_handoff"]["event_id"]
    assert envelope["event_key"] == state_input["case_state"]["dispatch_handoff"]["event_key"]


@pytest.mark.parametrize(
    "dispatch_status,recipient_refs,expected_ready,blockers",
    [
        ("dispatch_ready", [{"manufacturer_name": "Acme", "candidate_ids": ["candidate-1"]}], True, []),
        ("not_ready_dispatch_blocked", [{"manufacturer_name": "Acme", "candidate_ids": ["candidate-1"]}], False, ["review_required"]),
        ("not_ready_no_recipients", [], False, ["no_recipient_refs"]),
    ],
)
def test_build_dispatch_intent_reflects_status_from_canonical_rfq_dispatch(dispatch_status, recipient_refs, expected_ready, blockers):
    candidate_ref = recipient_refs[0] if recipient_refs else None
    rfq_dispatch = {
        "dispatch_ready": expected_ready,
        "dispatch_status": dispatch_status,
        "dispatch_blockers": blockers,
        "recipient_refs": [dict(candidate_ref)] if candidate_ref else [],
        "selected_manufacturer_ref": dict(candidate_ref) if candidate_ref else None,
        "recipient_selection": {"selection_status": "selected_recipient" if recipient_refs else "no_recipient_candidates"},
        "requirement_class": {"requirement_class_id": "rc::test"},
        "recommendation_identity": {"candidate_id": "candidate-1"},
        "rfq_object_basis": {
            "object_type": "rfq_object",
            "object_version": "rfq_object_v1",
            "payload_present": True,
            "qualified_material_ids": ["mat-1"],
        },
    }

    intent = build_dispatch_intent(rfq_dispatch)

    assert intent["dispatch_status"] == dispatch_status
    assert intent["dispatch_ready"] == expected_ready
    assert intent["dispatch_blockers"] == blockers
    assert intent["recipient_refs"] == rfq_dispatch["recipient_refs"]
    assert intent["selected_manufacturer_ref"] == (dict(candidate_ref) if candidate_ref else None)
    assert intent["recipient_selection"]["selection_status"] == rfq_dispatch["recipient_selection"]["selection_status"]
    assert intent["source"] == "canonical_rfq_dispatch"


def test_final_response_node_backfills_dispatch_trigger_when_selection_node_not_run():
    import asyncio
    from langchain_core.messages import HumanMessage
    from app.agent.agent.graph import final_response_node
    from app.agent.tests.test_graph_routing import _make_state

    sealing_state = _sealing_state(release_status="inquiry_ready")
    sealing_state["selection"] = _selection()
    sealing_state["review"] = _review(False)

    state = _make_state(
        policy_path="structured",
        result_form="direct_answer",
        messages=[HumanMessage(content="test")],
    )
    state["sealing_state"] = sealing_state  # type: ignore[index]
    state["case_state"] = {
        "rfq_state": {
            "rfq_admissibility": "ready",
            "rfq_dispatch": {
                "dispatch_ready": True,
                "dispatch_status": "dispatch_ready",
                "dispatch_blockers": [],
                "recipient_refs": [{"manufacturer_name": "Acme", "candidate_ids": ["ptfe::g25::acme"]}],
                "selected_manufacturer_ref": {"manufacturer_name": "Acme", "candidate_ids": ["ptfe::g25::acme"]},
                "requirement_class": {"requirement_class_id": "compound::ptfe::g25::acme"},
                "recommendation_identity": {"candidate_id": "ptfe::g25::acme"},
            },
        }
    }  # type: ignore[index]

    result = asyncio.run(final_response_node(state))

    assert result["sealing_state"]["dispatch_trigger"]["trigger_status"] == "trigger_ready"
    assert result["sealing_state"]["dispatch_intent"]["source"] == "canonical_rfq_dispatch"
    assert result["sealing_state"]["dispatch_trigger"]["source"] == "dispatch_intent"
    assert result["case_state"]["dispatch_trigger"]["trigger_allowed"] is True
    assert result["sealing_state"]["dispatch_dry_run"]["dry_run_status"] == "dry_run_ready"
    assert result["sealing_state"]["dispatch_dry_run"]["would_dispatch"] is True
    assert result["case_state"]["dispatch_dry_run"]["trigger_source"] == "dispatch_intent"
    assert result["sealing_state"]["dispatch_event"]["event_status"] == "event_dispatch_would_run"
    assert result["sealing_state"]["dispatch_event"]["would_dispatch"] is True
    assert result["case_state"]["dispatch_event"]["trigger_source"] == "dispatch_intent"
    assert result["case_state"]["dispatch_event"]["event_id"].startswith("dispatch_event::")
    assert result["sealing_state"]["dispatch_bridge"]["bridge_status"] == "bridge_ready"
    assert result["sealing_state"]["dispatch_bridge"]["event_id"] == result["sealing_state"]["dispatch_event"]["event_id"]
    assert result["case_state"]["dispatch_bridge"]["source"] == "dispatch_event"
    assert result["sealing_state"]["dispatch_handoff"]["handoff_status"] == "handoff_ready"
    assert result["sealing_state"]["dispatch_handoff"]["event_id"] == result["sealing_state"]["dispatch_bridge"]["event_id"]
    assert result["case_state"]["dispatch_handoff"]["source"] == "dispatch_bridge"
    assert result["sealing_state"]["dispatch_transport_envelope"]["envelope_status"] == "envelope_ready"
    assert result["sealing_state"]["dispatch_transport_envelope"]["event_id"] == result["sealing_state"]["dispatch_handoff"]["event_id"]
    assert result["case_state"]["dispatch_transport_envelope"]["source"] == "dispatch_handoff"


def test_final_response_node_realigns_existing_dispatch_surface_from_sealing_state():
    import asyncio
    from langchain_core.messages import HumanMessage
    from app.agent.agent.graph import final_response_node
    from app.agent.tests.test_graph_routing import _make_state

    sealing_state = _sealing_state(release_status="inquiry_ready")
    sealing_state["selection"] = _selection()
    sealing_state["review"] = _review(False)
    sealing_state["dispatch_intent"] = {
        "dispatch_ready": True,
        "dispatch_status": "dispatch_ready",
        "recipient_refs": [{"manufacturer_name": "Acme", "candidate_ids": ["ptfe::g25::acme"]}],
        "dispatch_blockers": [],
        "source": "canonical_rfq_dispatch",
    }
    sealing_state["dispatch_trigger"] = {
        "trigger_status": "trigger_ready",
        "trigger_allowed": True,
        "recipient_refs": [{"manufacturer_name": "Acme", "candidate_ids": ["ptfe::g25::acme"]}],
        "source": "dispatch_intent",
    }
    sealing_state["dispatch_dry_run"] = {
        "dry_run_status": "dry_run_ready",
        "would_dispatch": True,
        "recipient_refs": [{"manufacturer_name": "Acme", "candidate_ids": ["ptfe::g25::acme"]}],
        "trigger_source": "dispatch_intent",
        "source": "dispatch_trigger",
    }
    sealing_state["dispatch_event"] = {
        "event_status": "event_dispatch_would_run",
        "would_dispatch": True,
        "recipient_refs": [{"manufacturer_name": "Acme", "candidate_ids": ["ptfe::g25::acme"]}],
        "trigger_source": "dispatch_intent",
        "dry_run_status": "dry_run_ready",
        "event_id": "dispatch_event::abc",
        "event_key": "abc",
        "source": "dispatch_trigger",
    }
    sealing_state["dispatch_bridge"] = {
        "bridge_status": "bridge_ready",
        "event_id": "dispatch_event::abc",
        "event_key": "abc",
        "dry_run_status": "dry_run_ready",
        "recipient_refs": [{"manufacturer_name": "Acme", "candidate_ids": ["ptfe::g25::acme"]}],
        "source": "dispatch_event",
    }
    sealing_state["dispatch_handoff"] = {
        "handoff_status": "handoff_ready",
        "event_id": "dispatch_event::abc",
        "event_key": "abc",
        "bridge_status": "bridge_ready",
        "recipient_refs": [{"manufacturer_name": "Acme", "candidate_ids": ["ptfe::g25::acme"]}],
        "source": "dispatch_bridge",
    }
    sealing_state["dispatch_transport_envelope"] = {
        "envelope_status": "envelope_ready",
        "event_id": "dispatch_event::abc",
        "event_key": "abc",
        "handoff_status": "handoff_ready",
        "recipient_refs": [{"manufacturer_name": "Acme", "candidate_ids": ["ptfe::g25::acme"]}],
        "source": "dispatch_handoff",
    }

    state = _make_state(
        policy_path="structured",
        result_form="direct_answer",
        messages=[HumanMessage(content="test")],
    )
    state["sealing_state"] = sealing_state  # type: ignore[index]
    state["case_state"] = {  # type: ignore[index]
        "rfq_state": {"rfq_admissibility": "ready"},
        "dispatch_intent": {
            "dispatch_status": "blocked",
            "dispatch_ready": False,
            "recipient_refs": [{"manufacturer_name": "Canonical", "candidate_ids": ["canonical::candidate"]}],
            "requirement_class": {"requirement_class_id": "canonical::rc"},
            "recommendation_identity": {"candidate_id": "canonical::candidate"},
            "selected_manufacturer_ref": {"manufacturer_name": "Canonical", "candidate_ids": ["canonical::candidate"]},
        },
        "dispatch_trigger": {
            "trigger_status": "trigger_blocked_dispatch_not_ready",
            "trigger_allowed": False,
            "recipient_refs": [{"manufacturer_name": "Canonical", "candidate_ids": ["canonical::candidate"]}],
            "requirement_class": {"requirement_class_id": "canonical::rc"},
            "recommendation_identity": {"candidate_id": "canonical::candidate"},
        },
        "dispatch_dry_run": {
            "dry_run_status": "dry_run_blocked",
            "would_dispatch": False,
            "recipient_refs": [{"manufacturer_name": "Canonical", "candidate_ids": ["canonical::candidate"]}],
            "requirement_class": {"requirement_class_id": "canonical::rc"},
            "recommendation_identity": {"candidate_id": "canonical::candidate"},
        },
        "dispatch_event": {
            "event_status": "event_dispatch_missing_basis",
            "would_dispatch": False,
            "recipient_refs": [{"manufacturer_name": "Canonical", "candidate_ids": ["canonical::candidate"]}],
            "requirement_class": {"requirement_class_id": "canonical::rc"},
            "recommendation_identity": {"candidate_id": "canonical::candidate"},
        },
        "dispatch_bridge": {
            "bridge_status": "bridge_blocked_missing_basis",
            "recipient_refs": [{"manufacturer_name": "Canonical", "candidate_ids": ["canonical::candidate"]}],
            "bridge_payload_summary": {"recipient_count": 1, "requirement_class_id": "canonical::rc", "candidate_id": "canonical::candidate"},
        },
        "dispatch_handoff": {
            "handoff_status": "handoff_blocked_missing_basis",
            "recipient_refs": [{"manufacturer_name": "Canonical", "candidate_ids": ["canonical::candidate"]}],
            "payload_summary": {"recipient_count": 1, "requirement_class_id": "canonical::rc", "candidate_id": "canonical::candidate", "manufacturer_names": ["Canonical"]},
        },
        "dispatch_transport_envelope": {
            "envelope_status": "envelope_blocked_missing_basis",
            "recipient_refs": [{"manufacturer_name": "Canonical", "candidate_ids": ["canonical::candidate"]}],
            "payload_summary": {"recipient_count": 1, "manufacturer_names": ["Canonical"], "requirement_class_id": "canonical::rc", "candidate_id": "canonical::candidate"},
        },
    }

    result = asyncio.run(final_response_node(state))

    assert result["case_state"]["dispatch_intent"]["dispatch_status"] == "blocked"
    assert result["case_state"]["dispatch_intent"]["dispatch_ready"] is False
    assert result["sealing_state"]["dispatch_intent"]["dispatch_status"] == "blocked"
    assert result["sealing_state"]["dispatch_intent"]["dispatch_ready"] is False
    assert result["case_state"]["dispatch_intent"]["recipient_refs"] == [{"manufacturer_name": "Canonical", "candidate_ids": ["canonical::candidate"]}]
    assert result["case_state"]["dispatch_intent"]["requirement_class"]["requirement_class_id"] == "canonical::rc"
    assert result["sealing_state"]["dispatch_intent"]["recipient_refs"] == [{"manufacturer_name": "Canonical", "candidate_ids": ["canonical::candidate"]}]
    assert result["sealing_state"]["dispatch_intent"]["recommendation_identity"]["candidate_id"] == "canonical::candidate"

    assert result["case_state"]["dispatch_trigger"]["trigger_status"] == "trigger_blocked_dispatch_not_ready"
    assert result["case_state"]["dispatch_trigger"]["trigger_allowed"] is False
    assert result["sealing_state"]["dispatch_trigger"]["trigger_status"] == "trigger_blocked_dispatch_not_ready"
    assert result["sealing_state"]["dispatch_trigger"]["trigger_allowed"] is False
    assert result["sealing_state"]["dispatch_trigger"]["recipient_refs"] == [{"manufacturer_name": "Canonical", "candidate_ids": ["canonical::candidate"]}]

    assert result["case_state"]["dispatch_dry_run"]["dry_run_status"] == "dry_run_blocked"
    assert result["case_state"]["dispatch_dry_run"]["would_dispatch"] is False
    assert result["sealing_state"]["dispatch_dry_run"]["dry_run_status"] == "dry_run_blocked"
    assert result["sealing_state"]["dispatch_dry_run"]["would_dispatch"] is False
    assert result["sealing_state"]["dispatch_dry_run"]["recipient_refs"] == [{"manufacturer_name": "Canonical", "candidate_ids": ["canonical::candidate"]}]

    assert result["case_state"]["dispatch_event"]["event_status"] == "event_dispatch_missing_basis"
    assert result["case_state"]["dispatch_event"]["would_dispatch"] is False
    assert result["sealing_state"]["dispatch_event"]["event_status"] == "event_dispatch_missing_basis"
    assert result["sealing_state"]["dispatch_event"]["would_dispatch"] is False
    assert result["sealing_state"]["dispatch_event"]["recipient_refs"] == [{"manufacturer_name": "Canonical", "candidate_ids": ["canonical::candidate"]}]
    assert result["sealing_state"]["dispatch_event"]["event_id"] != "dispatch_event::abc"
    assert result["sealing_state"]["dispatch_event"]["event_key"] != "abc"
    assert result["case_state"]["dispatch_event"]["event_id"] == result["sealing_state"]["dispatch_event"]["event_id"]
    assert result["case_state"]["dispatch_event"]["event_key"] == result["sealing_state"]["dispatch_event"]["event_key"]

    assert result["case_state"]["dispatch_bridge"]["bridge_status"] == "bridge_blocked_missing_basis"
    assert result["sealing_state"]["dispatch_bridge"]["bridge_status"] == "bridge_blocked_missing_basis"
    assert result["sealing_state"]["dispatch_bridge"]["recipient_refs"] == [{"manufacturer_name": "Canonical", "candidate_ids": ["canonical::candidate"]}]
    assert result["sealing_state"]["dispatch_bridge"]["bridge_payload_summary"]["candidate_id"] == "canonical::candidate"
    assert result["sealing_state"]["dispatch_bridge"]["event_id"] == result["sealing_state"]["dispatch_event"]["event_id"]
    assert result["sealing_state"]["dispatch_bridge"]["event_key"] == result["sealing_state"]["dispatch_event"]["event_key"]

    assert result["case_state"]["dispatch_handoff"]["handoff_status"] == "handoff_blocked_missing_basis"
    assert result["sealing_state"]["dispatch_handoff"]["handoff_status"] == "handoff_blocked_missing_basis"
    assert result["sealing_state"]["dispatch_handoff"]["recipient_refs"] == [{"manufacturer_name": "Canonical", "candidate_ids": ["canonical::candidate"]}]
    assert result["sealing_state"]["dispatch_handoff"]["payload_summary"]["manufacturer_names"] == ["Canonical"]
    assert result["sealing_state"]["dispatch_handoff"]["event_id"] == result["sealing_state"]["dispatch_event"]["event_id"]
    assert result["sealing_state"]["dispatch_handoff"]["event_key"] == result["sealing_state"]["dispatch_event"]["event_key"]

    assert result["case_state"]["dispatch_transport_envelope"]["envelope_status"] == "envelope_blocked_missing_basis"
    assert result["sealing_state"]["dispatch_transport_envelope"]["envelope_status"] == "envelope_blocked_missing_basis"
    assert result["sealing_state"]["dispatch_transport_envelope"]["recipient_refs"] == [{"manufacturer_name": "Canonical", "candidate_ids": ["canonical::candidate"]}]
    assert result["sealing_state"]["dispatch_transport_envelope"]["payload_summary"]["candidate_id"] == "canonical::candidate"
    assert result["sealing_state"]["dispatch_transport_envelope"]["event_id"] == result["sealing_state"]["dispatch_event"]["event_id"]
    assert result["sealing_state"]["dispatch_transport_envelope"]["event_key"] == result["sealing_state"]["dispatch_event"]["event_key"]
