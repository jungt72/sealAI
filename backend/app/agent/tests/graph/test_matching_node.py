"""
Tests for graph/nodes/matching_node.py — Phase G Block 1
"""
from __future__ import annotations

import pytest

import app.agent.graph.nodes.matching_node as matching_node_module
from app.agent.domain.governed_data import GovernedMaterialRecord
from app.agent.domain.manufacturer_rfq import ManufacturerRfqSpecialistResult
from app.agent.graph import GraphState
from app.agent.graph.nodes.matching_node import matching_node
from app.agent.state.models import AssertedClaim, AssertedState, RequirementClass
from app.agent.state.reducers import reduce_asserted_to_governance


def _claim(field: str, value, confidence: str = "confirmed") -> AssertedClaim:
    return AssertedClaim(field_name=field, asserted_value=value, confidence=confidence)


def _state(
    *,
    gov_class: str = "A",
    material: str | None = "PTFE",
    requirement_class: RequirementClass | None = RequirementClass(
        class_id="PTFE10",
        description="High-temperature steam application — PTFE sealing class",
    ),
) -> GraphState:
    assertions = {
        "medium": _claim("medium", "Dampf"),
        "pressure_bar": _claim("pressure_bar", 12.0),
        "temperature_c": _claim("temperature_c", 180.0),
        "sealing_type": _claim("sealing_type", "radial_shaft_seal"),
    }
    if material is not None:
        assertions["material"] = _claim("material", material)
    asserted = AssertedState(assertions=assertions)
    governance = reduce_asserted_to_governance(asserted)
    if gov_class != governance.gov_class:
        governance = governance.model_copy(update={"gov_class": gov_class})
    return GraphState(
        asserted=asserted,
        governance=governance.model_copy(
            update={
                "requirement_class": requirement_class,
                "rfq_admissible": (gov_class == "A"),
            }
        ),
    )


class _NonDemoProvider:
    def list_material_records(self) -> list[GovernedMaterialRecord]:
        return [
            GovernedMaterialRecord(
                record_id="registry-ptfe-g25-acme",
                material_family="PTFE",
                grade_name="G25",
                manufacturer_name="Acme",
                source_name="Governed Registry",
                source_version="v1",
                release_status="active",
                coverage_metadata={
                    "max_temp_c": 260,
                    "max_pressure_bar": 16,
                    "allowed_media": ["steam"],
                    "requirement_class_ids": ["PTFE10"],
                    "supported_seal_types": ["radial_shaft_seal"],
                    "capability_hints": ["steam_service"],
                },
                is_demo_only=False,
            ),
            GovernedMaterialRecord(
                record_id="registry-ptfe-g10-sealtech",
                material_family="PTFE",
                grade_name="G10",
                manufacturer_name="SealTech",
                source_name="Governed Registry",
                source_version="v1",
                release_status="active",
                coverage_metadata={
                    "max_temp_c": 210,
                    "max_pressure_bar": 14,
                    "allowed_media": ["steam"],
                    "requirement_class_ids": ["PTFE10"],
                    "supported_seal_types": ["radial_shaft_seal"],
                    "capability_hints": ["steam_service"],
                },
                is_demo_only=False,
            ),
        ]

    def get_material_record(self, record_id: str) -> GovernedMaterialRecord | None:
        for record in self.list_material_records():
            if record.record_id == record_id:
                return record
        return None

    def list_active_material_records(self) -> list[GovernedMaterialRecord]:
        return self.list_material_records()


class TestMatchingNode:
    @pytest.mark.asyncio
    async def test_matching_node_uses_manufacturer_rfq_specialist_anchor(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(
            matching_node_module,
            "get_default_domain_data_provider",
            lambda: _NonDemoProvider(),
        )
        monkeypatch.setattr(
            matching_node_module,
            "run_manufacturer_rfq_specialist",
            lambda *_: ManufacturerRfqSpecialistResult(
                manufacturer_match_result={
                    "status": "matched_primary_candidate",
                    "reason": "Specialist-selected canonical candidate.",
                    "matchability_status": "ready_for_matching",
                    "selected_manufacturer_ref": {
                        "manufacturer_name": "PatchedCo",
                        "candidate_ids": ["patched::candidate"],
                    },
                },
                rfq_basis=None,
                rfq_send_payload=None,
            ),
        )

        result = await matching_node(_state())

        assert result.matching.status == "matched_primary_candidate"
        assert result.matching.shortlist_ready is True
        assert result.matching.selected_manufacturer_ref is not None
        assert result.matching.selected_manufacturer_ref.manufacturer_name == "PatchedCo"
        assert any("Specialist-selected canonical candidate." in note for note in result.matching.matching_notes)

    @pytest.mark.asyncio
    async def test_matchable_case_selects_manufacturer(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(
            matching_node_module,
            "get_default_domain_data_provider",
            lambda: _NonDemoProvider(),
        )
        result = await matching_node(_state())

        assert result.matching.matchability_status == "ready_for_matching"
        assert result.matching.status == "matched_primary_candidate"
        assert result.matching.shortlist_ready is True
        assert result.matching.release_blockers == []
        assert result.matching.selected_manufacturer_ref is not None
        assert result.matching.selected_manufacturer_ref.manufacturer_name == "Acme"
        assert any("capability score 100" in note for note in result.matching.matching_notes)

    @pytest.mark.asyncio
    async def test_requirement_class_can_supply_matching_basis_without_material(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(
            matching_node_module,
            "get_default_domain_data_provider",
            lambda: _NonDemoProvider(),
        )
        result = await matching_node(_state(material=None))

        assert result.matching.matchability_status == "ready_for_matching"
        assert result.matching.status == "matched_primary_candidate"
        assert result.matching.selected_manufacturer_ref is not None
        assert result.matching.selected_manufacturer_ref.manufacturer_name == "Acme"

    @pytest.mark.asyncio
    async def test_demo_catalog_candidate_is_not_released_as_shortlist(self):
        result = await matching_node(_state())

        assert result.matching.matchability_status == "not_released"
        assert result.matching.status == "candidate_not_released"
        assert result.matching.shortlist_ready is False
        assert result.matching.selected_manufacturer_ref is None
        assert "demo_matching_catalog" in result.matching.release_blockers
        assert result.matching.manufacturer_refs

    @pytest.mark.asyncio
    async def test_material_family_without_requirement_class_is_not_enough_for_matching(self):
        result = await matching_node(_state(requirement_class=None))

        assert result.matching.matchability_status == "insufficient_matching_basis"
        assert result.matching.status == "not_ready"
        assert result.matching.selected_manufacturer_ref is None
        assert any("requirement class" in note.lower() for note in result.matching.matching_notes)

    @pytest.mark.asyncio
    async def test_non_matchable_material_returns_negative_status_without_crash(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(
            matching_node_module,
            "get_default_domain_data_provider",
            lambda: _NonDemoProvider(),
        )
        result = await matching_node(_state(material="NBR"))

        assert result.matching.matchability_status == "ready_for_matching"
        assert result.matching.status == "blocked_no_match_candidates"
        assert result.matching.selected_manufacturer_ref is None
        assert result.matching.manufacturer_refs == []
        assert any("Rejected" in note for note in result.matching.matching_notes)

    @pytest.mark.asyncio
    async def test_best_fit_wins_over_weaker_candidate_by_score(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(
            matching_node_module,
            "get_default_domain_data_provider",
            lambda: _NonDemoProvider(),
        )
        result = await matching_node(_state())

        assert [ref.manufacturer_name for ref in result.matching.manufacturer_refs] == ["Acme", "SealTech"]
        assert any("Selected registry-ptfe-g25-acme" in note for note in result.matching.matching_notes)
