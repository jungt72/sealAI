"""
Tests for graph/nodes/dispatch_node.py — Phase G Block 3
"""
from __future__ import annotations

import pytest

import app.agent.graph.nodes.dispatch_node as dispatch_module
from app.agent.graph import GraphState
from app.agent.graph.nodes.dispatch_node import dispatch_node
from app.agent.state.models import (
    DispatchState,
    ManufacturerRef,
    RecipientRef,
    RequirementClass,
    RfqState,
)


def _rfq_ready_state() -> GraphState:
    return GraphState(
        rfq=RfqState(
            status="rfq_ready",
            rfq_ready=True,
            rfq_admissible=True,
            selected_manufacturer_ref=ManufacturerRef(
                manufacturer_name="Acme",
                candidate_ids=["registry-ptfe-g25-acme"],
            ),
            recipient_refs=[RecipientRef(manufacturer_name="Acme", qualified_for_rfq=True)],
            qualified_material_ids=["registry-ptfe-g25-acme"],
            requirement_class=RequirementClass(
                class_id="PTFE10",
                description="High-temperature PTFE class",
            ),
            rfq_send_payload={
                "object_type": "rfq_send_payload",
                "object_version": "rfq_send_payload_v1",
                "send_ready": True,
                "send_status": "send_ready",
                "blocking_reasons": [],
                "recipient_refs": [{"manufacturer_name": "Acme", "qualified_for_rfq": True}],
                "selected_manufacturer_ref": {"manufacturer_name": "Acme"},
                "requirement_class": {"requirement_class_id": "PTFE10", "description": "High-temperature PTFE class"},
                "handover_payload": {"qualified_material_ids": ["registry-ptfe-g25-acme"]},
            },
            handover_summary="Governed output is releasable and handover-ready.",
        ),
        matching={
            "manufacturer_refs": [
                {
                    "manufacturer_name": "Acme",
                    "candidate_ids": ["registry-ptfe-g25-acme"],
                    "material_families": ["PTFE"],
                    "grade_names": ["G25"],
                    "qualified_for_rfq": True,
                }
            ]
        },
    )


class TestDispatchNode:
    @pytest.mark.asyncio
    async def test_dispatch_node_consumes_rfq_send_payload_contract(self, monkeypatch: pytest.MonkeyPatch):
        captured: dict = {}

        def _capture_send_payload(send_payload):
            captured["rfq_send_payload"] = dict(send_payload or {})
            return {
                "dispatch_ready": True,
                "dispatch_status": "dispatch_ready",
                "dispatch_blockers": [],
                "recipient_refs": [{"manufacturer_name": "Acme"}],
                "selected_manufacturer_ref": {"manufacturer_name": "Acme"},
                "recipient_selection": {"selected_recipient_refs": [{"manufacturer_name": "Acme"}]},
                "requirement_class": {"requirement_class_id": "PTFE10"},
                "recommendation_identity": {"candidate_id": "registry-ptfe-g25-acme"},
                "rfq_object_basis": {"payload_present": True},
            }

        monkeypatch.setattr(dispatch_module, "project_dispatch_intent_from_rfq_send_payload", _capture_send_payload)

        result = await dispatch_node(_rfq_ready_state())

        assert captured["rfq_send_payload"]["object_type"] == "rfq_send_payload"
        assert result.dispatch.dispatch_ready is True

    @pytest.mark.asyncio
    async def test_dispatch_ready_when_prerequisites_are_met(self):
        result = await dispatch_node(_rfq_ready_state())

        assert result.dispatch.dispatch_ready is True
        assert result.dispatch.dispatch_status == "envelope_ready"
        assert result.dispatch.selected_manufacturer_ref is not None
        assert result.dispatch.transport_channel == "internal_transport_envelope"

    @pytest.mark.asyncio
    async def test_dispatch_not_ready_when_rfq_not_ready(self):
        result = await dispatch_node(GraphState())

        assert result.dispatch.dispatch_ready is False
        assert result.dispatch.dispatch_status == "not_ready"

    @pytest.mark.asyncio
    async def test_missing_recipients_do_not_crash(self):
        state = _rfq_ready_state().model_copy(
            update={
                "rfq": _rfq_ready_state().rfq.model_copy(
                    update={
                        "recipient_refs": [],
                        "rfq_send_payload": {
                            **_rfq_ready_state().rfq.rfq_send_payload,
                            "send_ready": False,
                            "send_status": "send_blocked",
                            "blocking_reasons": ["no_recipient_refs"],
                            "recipient_refs": [],
                        },
                    }
                ),
            }
        )

        result = await dispatch_node(state)

        assert result.dispatch.dispatch_ready is False
        assert result.dispatch.dispatch_status == "envelope_blocked_no_recipients"
        assert "event_id" not in str(result.dispatch.model_dump())

    @pytest.mark.asyncio
    async def test_missing_send_payload_contract_is_an_explicit_compatibility_block(self):
        state = _rfq_ready_state().model_copy(
            update={
                "rfq": _rfq_ready_state().rfq.model_copy(update={"rfq_send_payload": {}}),
            }
        )

        result = await dispatch_node(state)

        assert result.dispatch.dispatch_ready is False
        assert result.dispatch.dispatch_status == "not_ready"
        assert "bounded rfq_send_payload contract" in result.dispatch.dispatch_notes[0]
