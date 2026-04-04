from __future__ import annotations

import pytest

from app.agent.graph import GraphState
from app.agent.graph.nodes.norm_node import norm_node
from app.agent.state.models import (
    DispatchState,
    ManufacturerRef,
    MatchingState,
    ObservedExtraction,
    ObservedState,
    RecipientRef,
    RequirementClass,
    RfqState,
)
from app.agent.state.reducers import (
    reduce_asserted_to_governance,
    reduce_normalized_to_asserted,
    reduce_observed_to_normalized,
)


def _qualified_state() -> GraphState:
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
    return GraphState(
        session_id="phaseh-norm-node-001",
        observed=observed,
        normalized=normalized,
        asserted=asserted,
        governance=governance.model_copy(
            update={
                "validity_limits": ["Herstellervalidierung für finale Werkstofffreigabe erforderlich."],
                "open_validation_points": [],
            }
        ),
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
            qualified_material_ids=["registry-ptfe-g25-acme"],
            qualified_materials=[{"material_family": "PTFE", "grade_name": "PTFE virgin"}],
            confirmed_parameters={"medium": "Wasser"},
            dimensions={"dn_mm": 50.0},
            requirement_class=requirement_class,
        ),
        dispatch=DispatchState(
            dispatch_ready=True,
            dispatch_status="envelope_ready",
            selected_manufacturer_ref=ManufacturerRef(manufacturer_name="Acme"),
            recipient_refs=[RecipientRef(manufacturer_name="Acme", qualified_for_rfq=True)],
            requirement_class=requirement_class,
            transport_channel="internal_transport_envelope",
        ),
    )


class TestNormNode:
    @pytest.mark.asyncio
    async def test_full_qualified_case_builds_norm_object(self):
        result = await norm_node(_qualified_state())

        assert result.sealai_norm.status == "rfq_ready"
        assert result.sealai_norm.identity.norm_version == "sealai_norm_v1"
        assert result.sealai_norm.identity.requirement_class_id == "PTFE10"
        assert result.sealai_norm.identity.sealai_request_id == "sealai-phaseh-norm-node-001"
        assert result.sealai_norm.material.material_family == "PTFE"
        assert result.sealai_norm.manufacturer_validation_required is False

    @pytest.mark.asyncio
    async def test_incomplete_case_produces_valid_partial_norm(self):
        observed = ObservedState().with_extraction(
            ObservedExtraction(
                field_name="medium",
                raw_value="Wasser",
                confidence=1.0,
                turn_index=0,
            )
        )
        normalized = reduce_observed_to_normalized(observed)
        asserted = reduce_normalized_to_asserted(normalized)
        state = GraphState(
            session_id="phaseh-norm-node-002",
            observed=observed,
            normalized=normalized,
            asserted=asserted,
            governance=reduce_asserted_to_governance(asserted).model_copy(update={"gov_class": "B"}),
        )

        result = await norm_node(state)

        assert result.sealai_norm.status in {"draft", "governed"}
        assert result.sealai_norm.identity.norm_version == "sealai_norm_v1"
        assert result.sealai_norm.operating_conditions.medium == "Wasser"

    @pytest.mark.asyncio
    async def test_missing_data_does_not_crash(self):
        result = await norm_node(GraphState())

        assert result.sealai_norm.status == "pending"
        assert result.sealai_norm.identity.norm_version == "sealai_norm_v1"
        assert result.sealai_norm.geometry == {}
