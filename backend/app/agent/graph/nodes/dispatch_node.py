"""
dispatch_node — Phase G Block 3

Deterministic dispatch/transport preparation for the governed path.

Responsibility:
    Build a bounded dispatch summary from the RFQ handover state without
    executing any external send/connector side effects.
"""
from __future__ import annotations

import logging

from app.agent.manufacturers.commercial import (
    build_dispatch_bridge,
    build_dispatch_dry_run,
    build_dispatch_handoff,
    build_dispatch_transport_envelope,
    build_dispatch_trigger,
)
from app.agent.domain.manufacturer_rfq import project_dispatch_intent_from_rfq_send_payload
from app.agent.graph import GraphState
from app.agent.state.models import DispatchState, ManufacturerRef, RecipientRef, RequirementClass

log = logging.getLogger(__name__)


def _recipient_refs_from_dispatch_intent(dispatch_intent: dict) -> list[RecipientRef]:
    recipients: list[RecipientRef] = []
    for ref in list(dispatch_intent.get("recipient_refs") or []):
        if not isinstance(ref, dict):
            continue
        manufacturer_name = str(ref.get("manufacturer_name") or "").strip()
        if not manufacturer_name:
            continue
        recipients.append(
            RecipientRef(
                manufacturer_name=manufacturer_name,
                candidate_ids=[str(item) for item in list(ref.get("candidate_ids") or []) if item],
                qualified_for_rfq=bool(ref.get("qualified_for_rfq", False)),
            )
        )
    return recipients


def _selected_manufacturer_ref_from_dispatch_intent(dispatch_intent: dict) -> ManufacturerRef | None:
    payload = dispatch_intent.get("selected_manufacturer_ref")
    if not isinstance(payload, dict):
        return None
    manufacturer_name = str(payload.get("manufacturer_name") or "").strip()
    if not manufacturer_name:
        return None
    return ManufacturerRef(
        manufacturer_name=manufacturer_name,
        candidate_ids=[str(item) for item in list(payload.get("candidate_ids") or []) if item],
        material_families=[str(item) for item in list(payload.get("material_families") or []) if item],
        grade_names=[str(item) for item in list(payload.get("grade_names") or []) if item],
        qualified_for_rfq=bool(payload.get("qualified_for_rfq", False)),
    )


def _requirement_class_from_dispatch_intent(dispatch_intent: dict) -> RequirementClass | None:
    payload = dispatch_intent.get("requirement_class")
    if not isinstance(payload, dict):
        return None
    class_id = str(
        payload.get("requirement_class_id")
        or payload.get("class_id")
        or ""
    ).strip()
    if not class_id:
        return None
    return RequirementClass(
        class_id=class_id,
        description=str(payload.get("description") or "").strip(),
        seal_type=str(payload.get("seal_type") or "").strip() or None,
    )


async def dispatch_node(state: GraphState) -> GraphState:
    """Build a bounded dispatch summary from the RFQ handover state."""
    if not state.rfq.rfq_ready:
        return state.model_copy(
            update={
                "dispatch": DispatchState(
                    dispatch_status="not_ready",
                    selected_manufacturer_ref=state.rfq.selected_manufacturer_ref,
                    recipient_refs=list(state.rfq.recipient_refs),
                    requirement_class=state.rfq.requirement_class,
                    transport_channel="internal_transport_envelope",
                    handover_summary=state.rfq.handover_summary,
                    dispatch_notes=["Dispatch preparation requires an RFQ-ready handover basis."],
                )
            }
        )

    dispatch_intent = project_dispatch_intent_from_rfq_send_payload(state.rfq.rfq_send_payload)
    if not isinstance(dispatch_intent, dict) or not dispatch_intent:
        return state.model_copy(
            update={
                "dispatch": DispatchState(
                    dispatch_status="not_ready",
                    selected_manufacturer_ref=state.rfq.selected_manufacturer_ref,
                    recipient_refs=list(state.rfq.recipient_refs),
                    requirement_class=state.rfq.requirement_class,
                    transport_channel="internal_transport_envelope",
                    handover_summary=state.rfq.handover_summary,
                    dispatch_notes=["Dispatch preparation requires the bounded rfq_send_payload contract."],
                )
            }
        )
    dispatch_state = {
        "case_state": {
            "dispatch_intent": dispatch_intent,
        }
    }

    trigger = build_dispatch_trigger(dispatch_state)
    dry_run = build_dispatch_dry_run({"case_state": {"dispatch_trigger": trigger}})
    bridge = build_dispatch_bridge(
        {"case_state": {"dispatch_trigger": trigger, "dispatch_dry_run": dry_run}}
    )
    handoff = build_dispatch_handoff({"case_state": {"dispatch_bridge": bridge}})
    envelope = build_dispatch_transport_envelope({"case_state": {"dispatch_handoff": handoff}})

    notes = [
        note
        for note in [
            trigger.get("trigger_reason"),
            dry_run.get("dry_run_reason"),
            bridge.get("bridge_reason"),
            handoff.get("handoff_reason"),
            envelope.get("envelope_reason"),
        ]
        if note
    ]

    log.debug(
        "[dispatch_node] dispatch_ready=%s dispatch_status=%s recipients=%d",
        envelope.get("envelope_ready"),
        envelope.get("envelope_status"),
        len(state.rfq.recipient_refs),
    )

    return state.model_copy(
        update={
            "dispatch": DispatchState(
                dispatch_ready=bool(envelope.get("envelope_ready")),
                dispatch_status=str(envelope.get("envelope_status") or "not_ready"),
                selected_manufacturer_ref=(
                    _selected_manufacturer_ref_from_dispatch_intent(dispatch_intent)
                    or state.rfq.selected_manufacturer_ref
                ),
                recipient_refs=(
                    _recipient_refs_from_dispatch_intent(dispatch_intent)
                    or list(state.rfq.recipient_refs)
                ),
                requirement_class=(
                    _requirement_class_from_dispatch_intent(dispatch_intent)
                    or state.rfq.requirement_class
                ),
                transport_channel="internal_transport_envelope",
                handover_summary=str(envelope.get("envelope_reason") or "") or state.rfq.handover_summary,
                dispatch_notes=notes,
            )
        }
    )
