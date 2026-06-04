from __future__ import annotations

import pytest

from app.agent.graph import GraphState
from app.agent.graph.nodes.export_profile_node import export_profile_node
from app.agent.state.models import (
    DispatchState,
    ExportProfileState,
    ManufacturerRef,
    MatchingState,
    ObservedExtraction,
    ObservedState,
    RecipientRef,
    RequirementClass,
    RfqState,
    SealaiNormIdentity,
    SealaiNormMaterial,
    SealaiNormState,
)
from app.agent.state.reducers import (
    reduce_asserted_to_governance,
    reduce_normalized_to_asserted,
    reduce_observed_to_normalized,
)


def _base_state() -> GraphState:
    requirement_class = RequirementClass(
        class_id="PTFE10",
        description="High-temperature PTFE class",
        seal_type="Flachdichtung",
    )
    observed = ObservedState()
    for field_name, value in {
        "medium": "Wasser",
        "pressure_bar": 12.0,
        "temperature_c": 180.0,
        "material": "PTFE",
    }.items():
        observed = observed.with_extraction(
            ObservedExtraction(
                field_name=field_name,
                raw_value=value,
                confidence=1.0,
                turn_index=0,
            )
        )
    normalized = reduce_observed_to_normalized(observed)
    asserted = reduce_normalized_to_asserted(normalized)
    governance = reduce_asserted_to_governance(asserted).model_copy(
        update={"requirement_class": requirement_class}
    )
    norm = SealaiNormState(
        status="rfq_ready",
        identity=SealaiNormIdentity(
            sealai_request_id="sealai-phaseh-export-node-001",
            norm_version="sealai_norm_v1",
            requirement_class_id="PTFE10",
            seal_family="Flachdichtung",
        ),
        application_summary="Wasser, 180°C, 12 bar",
        geometry={"dn_mm": 50.0},
        material=SealaiNormMaterial(
            material_family="PTFE",
            qualified_materials=["PTFE virgin"],
        ),
    )
    return GraphState(
        observed=observed,
        normalized=normalized,
        asserted=asserted,
        governance=governance,
        sealai_norm=norm,
        matching=MatchingState(
            status="matched_primary_candidate",
            matchability_status="ready_for_matching",
            selected_manufacturer_ref=ManufacturerRef(manufacturer_name="Acme"),
            manufacturer_refs=[ManufacturerRef(manufacturer_name="Acme")],
        ),
        rfq=RfqState(
            status="rfq_ready",
            rfq_ready=True,
            rfq_admissible=True,
            selected_manufacturer_ref=ManufacturerRef(manufacturer_name="Acme"),
            recipient_refs=[RecipientRef(manufacturer_name="Acme", qualified_for_rfq=True)],
            requirement_class=requirement_class,
            notes=["Governed output is releasable and handover-ready."],
        ),
        dispatch=DispatchState(
            dispatch_ready=True,
            dispatch_status="envelope_ready",
            selected_manufacturer_ref=ManufacturerRef(manufacturer_name="Acme"),
            recipient_refs=[RecipientRef(manufacturer_name="Acme", qualified_for_rfq=True)],
            requirement_class=requirement_class,
            transport_channel="internal_transport_envelope",
            dispatch_notes=["Internal transport envelope is ready for later sender/connector consumption."],
        ),
    )


class TestExportProfileNode:
    @pytest.mark.asyncio
    async def test_full_qualified_case_builds_export_profile(self):
        result = await export_profile_node(_base_state())

        assert result.export_profile.status == "ready"
        assert result.export_profile.export_profile_version == "sealai_export_profile_v1"
        assert result.export_profile.selected_manufacturer == "Acme"
        assert result.export_profile.requirement_class_id == "PTFE10"
        assert result.export_profile.rfq_ready is True
        assert result.export_profile.dispatch_ready is True

    @pytest.mark.asyncio
    async def test_incomplete_case_builds_valid_partial_export_profile(self):
        state = _base_state().model_copy(
            update={
                "dispatch": DispatchState(dispatch_ready=False, dispatch_status="not_ready"),
                "rfq": RfqState(status="not_ready", rfq_ready=False),
            }
        )

        result = await export_profile_node(state)

        assert result.export_profile.status in {"partial", "not_ready"}
        assert result.export_profile.export_profile_version == "sealai_export_profile_v1"
        assert result.export_profile.sealai_request_id == "sealai-phaseh-export-node-001"

    @pytest.mark.asyncio
    async def test_missing_data_does_not_crash(self):
        result = await export_profile_node(GraphState())

        assert isinstance(result.export_profile, ExportProfileState)
        assert result.export_profile.status == "pending"
        assert result.export_profile.export_profile_version == "sealai_export_profile_v1"
