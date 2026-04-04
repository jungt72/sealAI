from __future__ import annotations

import pytest

from app.agent.graph import GraphState
from app.agent.graph.nodes.manufacturer_mapping_node import manufacturer_mapping_node
from app.agent.state.models import (
    ExportProfileState,
    ManufacturerMappingState,
    SealaiNormIdentity,
    SealaiNormMaterial,
    SealaiNormState,
)


def _base_state() -> GraphState:
    return GraphState(
        sealai_norm=SealaiNormState(
            status="rfq_ready",
            identity=SealaiNormIdentity(
                sealai_request_id="sealai-phaseh-map-node-001",
                norm_version="sealai_norm_v1",
                requirement_class_id="PTFE10",
                seal_family="Flachdichtung",
            ),
            material=SealaiNormMaterial(
                material_family="PTFE",
                qualified_materials=["PTFE virgin"],
            ),
        ),
        export_profile=ExportProfileState(
            status="ready",
            export_profile_version="sealai_export_profile_v1",
            sealai_request_id="sealai-phaseh-map-node-001",
            selected_manufacturer="Acme",
            recipient_refs=["Acme"],
            requirement_class_id="PTFE10",
            application_summary="Wasser, 180°C, 12 bar",
            dimensions_summary=["dn_mm=50.0"],
            material_summary="PTFE (1 qualified material candidates)",
            rfq_ready=True,
            dispatch_ready=True,
        ),
    )


class TestManufacturerMappingNode:
    @pytest.mark.asyncio
    async def test_serious_mappable_case_builds_mapping(self):
        result = await manufacturer_mapping_node(_base_state())

        assert result.manufacturer_mapping.status == "mapped"
        assert result.manufacturer_mapping.mapping_version == "manufacturer_mapping_v1"
        assert result.manufacturer_mapping.selected_manufacturer == "Acme"
        assert result.manufacturer_mapping.mapped_material_family == "PTFE"

    @pytest.mark.asyncio
    async def test_incomplete_case_returns_partial_or_not_ready(self):
        state = _base_state().model_copy(
            update={
                "sealai_norm": _base_state().sealai_norm.model_copy(
                    update={"identity": _base_state().sealai_norm.identity.model_copy(update={"seal_family": None})}
                ),
                "export_profile": _base_state().export_profile.model_copy(
                    update={"dimensions_summary": []}
                ),
            }
        )

        result = await manufacturer_mapping_node(state)

        assert result.manufacturer_mapping.status in {"partial", "not_ready"}
        assert "product_family_hint_missing" in result.manufacturer_mapping.unresolved_mapping_points

    @pytest.mark.asyncio
    async def test_missing_data_does_not_crash(self):
        result = await manufacturer_mapping_node(GraphState())

        assert isinstance(result.manufacturer_mapping, ManufacturerMappingState)
        assert result.manufacturer_mapping.status == "pending"
        assert result.manufacturer_mapping.mapping_version == "manufacturer_mapping_v1"
