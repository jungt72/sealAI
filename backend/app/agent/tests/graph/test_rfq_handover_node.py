"""
Tests for graph/nodes/rfq_handover_node.py — Phase G Block 2
"""
from __future__ import annotations

import pytest

import app.agent.graph.nodes.rfq_handover_node as rfq_handover_module
from app.agent.domain.critical_review import CriticalReviewSpecialistResult
from app.agent.domain.manufacturer_rfq import ManufacturerRfqSpecialistResult
from app.agent.graph import GraphState
from app.agent.graph.nodes.rfq_handover_node import rfq_handover_node
from app.agent.state.models import AssertedClaim, AssertedState, ManufacturerRef, MatchingState
from app.agent.state.reducers import reduce_asserted_to_governance


def _claim(field: str, value, confidence: str = "confirmed") -> AssertedClaim:
    return AssertedClaim(field_name=field, asserted_value=value, confidence=confidence)


def _base_state() -> GraphState:
    asserted = AssertedState(
        assertions={
            "medium": _claim("medium", "Wasser"),
            "pressure_bar": _claim("pressure_bar", 12.0),
            "temperature_c": _claim("temperature_c", 180.0),
            "material": _claim("material", "PTFE"),
        }
    )
    governance = reduce_asserted_to_governance(asserted)
    return GraphState(
        asserted=asserted,
        governance=governance,
    )


class TestRfqHandoverNode:
    @pytest.mark.asyncio
    async def test_rfq_ready_when_prerequisites_are_met(self):
        state = _base_state().model_copy(
            update={
                "matching": MatchingState(
                    status="matched_primary_candidate",
                    matchability_status="ready_for_matching",
                    selected_manufacturer_ref=ManufacturerRef(
                        manufacturer_name="Acme",
                        candidate_ids=["registry-ptfe-g25-acme"],
                        material_families=["PTFE"],
                        grade_names=["G25"],
                        qualified_for_rfq=True,
                    ),
                    manufacturer_refs=[
                        ManufacturerRef(
                            manufacturer_name="Acme",
                            candidate_ids=["registry-ptfe-g25-acme"],
                            material_families=["PTFE"],
                            grade_names=["G25"],
                            qualified_for_rfq=True,
                        )
                    ],
                )
            }
        )

        result = await rfq_handover_node(state)

        assert result.rfq.rfq_ready is True
        assert result.rfq.status == "rfq_ready"
        assert result.rfq.rfq_object["object_type"] == "rfq_payload_basis"
        assert result.rfq.selected_manufacturer_ref is not None
        assert result.rfq.selected_manufacturer_ref.manufacturer_name == "Acme"
        assert result.rfq.qualified_material_ids == ["registry-ptfe-g25-acme"]
        assert result.rfq.confirmed_parameters["medium"] == "Wasser"
        assert result.rfq.requirement_class is not None
        assert result.rfq.critical_review_passed is True

    @pytest.mark.asyncio
    async def test_not_ready_when_matching_is_missing(self):
        result = await rfq_handover_node(_base_state())

        assert result.rfq.rfq_ready is False
        assert result.rfq.status == "not_ready"
        assert result.rfq.selected_manufacturer_ref is None

    @pytest.mark.asyncio
    async def test_missing_prerequisites_do_not_crash(self):
        result = await rfq_handover_node(GraphState())

        assert result.rfq.rfq_ready is False
        assert result.rfq.status == "needs_clarification"
        assert result.rfq.qualified_material_ids == []

    @pytest.mark.asyncio
    async def test_critical_review_failure_blocks_rfq_handover(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(
            rfq_handover_module,
            "run_critical_review_specialist",
            lambda *_: CriticalReviewSpecialistResult(
                critical_review_status="failed",
                critical_review_passed=False,
                blocking_findings=("selected_manufacturer_missing",),
                soft_findings=(),
                required_corrections=("Select a deterministic manufacturer candidate before RFQ handover.",),
            ),
        )
        result = await rfq_handover_node(
            _base_state().model_copy(
                update={
                    "matching": MatchingState(
                        status="matched_primary_candidate",
                        matchability_status="ready_for_matching",
                        selected_manufacturer_ref=ManufacturerRef(
                            manufacturer_name="Acme",
                            candidate_ids=["registry-ptfe-g25-acme"],
                        ),
                        manufacturer_refs=[
                            ManufacturerRef(
                                manufacturer_name="Acme",
                                candidate_ids=["registry-ptfe-g25-acme"],
                                qualified_for_rfq=True,
                            )
                        ],
                    )
                }
            )
        )

        assert result.rfq.rfq_ready is False
        assert result.rfq.status == "blocked_critical_review"
        assert result.rfq.critical_review_passed is False
        assert result.rfq.blocking_findings == ["selected_manufacturer_missing"]

    @pytest.mark.asyncio
    async def test_soft_findings_do_not_block_when_critical_review_passes(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(
            rfq_handover_module,
            "run_critical_review_specialist",
            lambda *_: CriticalReviewSpecialistResult(
                critical_review_status="passed",
                critical_review_passed=True,
                blocking_findings=(),
                soft_findings=("scope:Manufacturer validation remains required.",),
                required_corrections=(),
            ),
        )
        result = await rfq_handover_node(
            _base_state().model_copy(
                update={
                    "matching": MatchingState(
                        status="matched_primary_candidate",
                        matchability_status="ready_for_matching",
                        selected_manufacturer_ref=ManufacturerRef(
                            manufacturer_name="Acme",
                            candidate_ids=["registry-ptfe-g25-acme"],
                            qualified_for_rfq=True,
                        ),
                        manufacturer_refs=[
                            ManufacturerRef(
                                manufacturer_name="Acme",
                                candidate_ids=["registry-ptfe-g25-acme"],
                                qualified_for_rfq=True,
                            )
                        ],
                    )
                }
            )
        )

        assert result.rfq.rfq_ready is True
        assert result.rfq.critical_review_passed is True
        assert result.rfq.soft_findings == ["scope:Manufacturer validation remains required."]

    @pytest.mark.asyncio
    async def test_rfq_handover_node_uses_manufacturer_rfq_specialist_anchor(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(
            rfq_handover_module,
            "run_critical_review_specialist",
            lambda *_: CriticalReviewSpecialistResult(
                critical_review_status="passed",
                critical_review_passed=True,
                blocking_findings=(),
                soft_findings=(),
                required_corrections=(),
            ),
        )
        monkeypatch.setattr(
            rfq_handover_module,
            "run_manufacturer_rfq_specialist",
            lambda *_: ManufacturerRfqSpecialistResult(
                manufacturer_match_result=None,
                rfq_basis={
                    "rfq_object": {
                        "object_type": "rfq_payload_basis",
                        "object_version": "rfq_payload_basis_v1",
                        "qualified_material_ids": ["patched::candidate"],
                        "qualified_materials": [{"candidate_id": "patched::candidate", "manufacturer_name": "Acme"}],
                        "confirmed_parameters": {"medium": "PatchedMedium"},
                        "dimensions": {"shaft_diameter_mm": 33.0},
                        "target_system": "rfq_portal",
                    },
                    "handover_payload": {
                        "qualified_material_ids": ["patched::candidate"],
                        "qualified_materials": [{"candidate_id": "patched::candidate", "manufacturer_name": "Acme"}],
                        "confirmed_parameters": {"medium": "PatchedMedium"},
                        "dimensions": {"shaft_diameter_mm": 33.0},
                        "rfq_admissibility": "ready",
                    },
                    "target_system": "rfq_portal",
                },
                rfq_send_payload={
                    "object_type": "rfq_send_payload",
                    "send_ready": True,
                },
            ),
        )

        result = await rfq_handover_node(
            _base_state().model_copy(
                update={
                    "matching": MatchingState(
                        status="matched_primary_candidate",
                        matchability_status="ready_for_matching",
                        selected_manufacturer_ref=ManufacturerRef(
                            manufacturer_name="Acme",
                            candidate_ids=["registry-ptfe-g25-acme"],
                            qualified_for_rfq=True,
                        ),
                        manufacturer_refs=[
                            ManufacturerRef(
                                manufacturer_name="Acme",
                                candidate_ids=["registry-ptfe-g25-acme"],
                                qualified_for_rfq=True,
                            )
                        ],
                    )
                }
            )
        )

        assert result.rfq.rfq_ready is True
        assert result.rfq.qualified_material_ids == ["patched::candidate"]
        assert result.rfq.confirmed_parameters == {"medium": "PatchedMedium"}
        assert result.rfq.dimensions == {"shaft_diameter_mm": 33.0}
        assert result.rfq.rfq_send_payload["object_type"] == "rfq_send_payload"
        assert result.rfq.rfq_send_payload["send_ready"] is True
