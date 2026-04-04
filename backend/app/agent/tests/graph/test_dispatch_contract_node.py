from __future__ import annotations

import pytest

from app.agent.graph import GraphState
from app.agent.graph.nodes.dispatch_contract_node import dispatch_contract_node
from app.agent.state.models import (
    DispatchContractState,
    DispatchState,
    ExportProfileState,
    ManufacturerMappingState,
    RfqState,
    SealaiNormIdentity,
    SealaiNormState,
)


def _qualified_state() -> GraphState:
    return GraphState(
        sealai_norm=SealaiNormState(
            status="rfq_ready",
            identity=SealaiNormIdentity(
                sealai_request_id="sealai-phasei-contract-node-001",
                norm_version="sealai_norm_v1",
                requirement_class_id="PTFE10",
            ),
            application_summary="Wasser, 180°C, 12 bar",
        ),
        export_profile=ExportProfileState(
            status="ready",
            export_profile_version="sealai_export_profile_v1",
            sealai_request_id="sealai-phasei-contract-node-001",
            selected_manufacturer="Acme",
            recipient_refs=["Acme"],
            requirement_class_id="PTFE10",
            application_summary="Wasser, 180°C, 12 bar",
            dimensions_summary=["dn_mm=50.0"],
            material_summary="PTFE (1 qualified material candidates)",
            rfq_ready=True,
            dispatch_ready=True,
        ),
        manufacturer_mapping=ManufacturerMappingState(
            status="mapped",
            mapping_version="manufacturer_mapping_v1",
            selected_manufacturer="Acme",
            mapped_product_family="Flachdichtung",
            mapped_material_family="PTFE",
            geometry_export_hint="dn_mm=50.0",
            mapping_notes=["Mapping remains category-level only; no SKU or compound code is inferred."],
        ),
        rfq=RfqState(
            status="rfq_ready",
            rfq_ready=True,
            rfq_admissible=True,
        ),
        dispatch=DispatchState(
            dispatch_ready=True,
            dispatch_status="envelope_ready",
            transport_channel="internal_transport_envelope",
            dispatch_notes=["Internal transport envelope is ready for later sender/connector consumption."],
        ),
    ).model_copy(
        update={
            "governance": GraphState().governance.model_copy(
                update={"gov_class": "A", "rfq_admissible": True}
            )
        }
    )


class TestDispatchContractNode:
    @pytest.mark.asyncio
    async def test_qualified_case_builds_connector_ready_contract(self) -> None:
        result = await dispatch_contract_node(_qualified_state())

        contract = result.dispatch_contract
        assert isinstance(contract, DispatchContractState)
        assert contract.status == "ready"
        assert contract.contract_version == "dispatch_contract_v1"
        assert contract.sealai_request_id == "sealai-phasei-contract-node-001"
        assert contract.selected_manufacturer == "Acme"
        assert contract.recipient_refs == ["Acme"]
        assert contract.requirement_class_id == "PTFE10"
        assert contract.rfq_ready is True
        assert contract.dispatch_ready is True
        dumped = str(contract.model_dump()).lower()
        assert "transport" not in dumped
        assert "event_id" not in dumped
        assert "event_key" not in dumped
        assert "partner_id" not in dumped
        assert "manufacturer_sku" not in dumped
        assert "compound_code" not in dumped

    @pytest.mark.asyncio
    async def test_incomplete_case_returns_partial_with_unresolved_points(self) -> None:
        state = _qualified_state().model_copy(
            update={
                "dispatch": DispatchState(dispatch_ready=False, dispatch_status="not_ready"),
                "rfq": RfqState(status="not_ready", rfq_ready=False, rfq_admissible=True),
                "governance": _qualified_state().governance.model_copy(
                    update={
                        "gov_class": "B",
                        "rfq_admissible": False,
                        "open_validation_points": ["medium"],
                    }
                ),
                "export_profile": _qualified_state().export_profile.model_copy(
                    update={"dispatch_ready": False, "unresolved_points": ["medium"]}
                ),
            }
        )

        result = await dispatch_contract_node(state)

        assert result.dispatch_contract.status == "partial"
        assert "medium" in result.dispatch_contract.unresolved_points
        assert result.dispatch_contract.dispatch_ready is False

    @pytest.mark.asyncio
    async def test_missing_data_does_not_crash(self) -> None:
        result = await dispatch_contract_node(GraphState())

        assert isinstance(result.dispatch_contract, DispatchContractState)
        assert result.dispatch_contract.status == "pending"
        assert result.dispatch_contract.contract_version == "dispatch_contract_v1"
