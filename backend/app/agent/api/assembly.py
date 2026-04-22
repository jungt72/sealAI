import logging
import dataclasses
from dataclasses import dataclass
from typing import Any, Optional, Dict, List

from app.agent.state.models import GovernedSessionState, TurnContextContract
from app.agent.graph import GraphState
from app.agent.state.projections import project_for_ui
from app.agent.runtime.response_renderer import render_response
from app.agent.graph.output_contract_assembly import build_governed_conversation_strategy_contract
from app.agent.runtime.turn_context import build_governed_turn_context
from app.agent.runtime.user_facing_reply import assemble_user_facing_reply
from app.agent.api.utils import _governed_structured_state
from app.agent.api.deps import _GRAPH_MODEL_ID, VISIBLE_REPLY_PROMPT_VERSION, VISIBLE_REPLY_PROMPT_HASH
from app.agent.prompts import REASONING_PROMPT_HASH, REASONING_PROMPT_VERSION
from app.agent.state.case_state import (
    PROJECTION_VERSION,
    CASE_STATE_BUILDER_VERSION,
    DETERMINISTIC_SERVICE_VERSION,
    DETERMINISTIC_DATA_VERSION,
)

_log = logging.getLogger(__name__)

@dataclass(frozen=True)
class GovernedReplyAssemblyContext:
    response_class: str
    structured_state: dict[str, Any] | None
    assertions_payload: dict[str, Any]
    conversation_strategy: Any
    turn_context: TurnContextContract
    run_meta: dict[str, Any]
    ui_payload: dict[str, Any]
    deterministic_reply: str
    domain_context: dict[str, Any] = dataclasses.field(default_factory=dict)

def _build_structured_version_provenance(*, decision: Any, rwdr_config_version: str | None = None) -> dict[str, Any]:
    vp = {
        "model_id": _GRAPH_MODEL_ID,
        "model_version": _GRAPH_MODEL_ID,
        "prompt_version": REASONING_PROMPT_VERSION,
        "prompt_hash": REASONING_PROMPT_HASH,
        "visible_reply_prompt_version": VISIBLE_REPLY_PROMPT_VERSION,
        "visible_reply_prompt_hash": VISIBLE_REPLY_PROMPT_HASH,
        "policy_version": getattr(decision, "policy_version", "interaction_policy_v1"),
        "projection_version": PROJECTION_VERSION,
        "case_state_builder_version": CASE_STATE_BUILDER_VERSION,
        "service_version": DETERMINISTIC_SERVICE_VERSION,
        "data_version": DETERMINISTIC_DATA_VERSION,
    }
    if rwdr_config_version is not None:
        vp["rwdr_config_version"] = rwdr_config_version
    return vp

def _build_fast_path_version_provenance(*, decision: Any) -> dict[str, Any]:
    return {
        "model_id": None,
        "model_version": None,
        "policy_version": getattr(decision, "policy_version", "interaction_policy_v1"),
        "projection_version": PROJECTION_VERSION,
        "case_state_builder_version": CASE_STATE_BUILDER_VERSION,
        "service_version": DETERMINISTIC_SERVICE_VERSION,
        "data_version": DETERMINISTIC_DATA_VERSION,
    }

def _build_governed_reply_context(
    *,
    result_state: GraphState,
    persisted_state: GovernedSessionState,
) -> GovernedReplyAssemblyContext:
    def _sanitize_public_notes(notes: list[Any]) -> list[str]:
        blocked_fragments = (
            "transport", "bridge", "handoff", "dry-run", "internal trigger",
            "sender/connector", "connector consumption", "envelope",
        )
        public_notes: list[str] = []
        for note in notes:
            text = str(note or "").strip()
            if not text or any(f in text.lower() for f in blocked_fragments):
                continue
            if text not in public_notes:
                public_notes.append(text)
        return public_notes

    def _strip_forbidden_keys(value: Any) -> Any:
        forbidden_keys = {
            "event_id", "event_key", "analysis_cycle_id", "partner_id",
            "transport_channel", "manufacturer_sku", "compound_code",
        }
        if isinstance(value, dict):
            return {k: _strip_forbidden_keys(v) for k, v in value.items() if k not in forbidden_keys}
        if isinstance(value, list):
            return [_strip_forbidden_keys(v) for v in value]
        return value

    ui_payload = project_for_ui(result_state).model_dump()
    if "inquiry" not in ui_payload and isinstance(ui_payload.get("rfq"), dict):
        ui_payload["inquiry"] = dict(ui_payload["rfq"])
    for tile_name, note_field in (
        ("rfq", "notes"), ("inquiry", "notes"),
        ("export_profile", "notes"), ("dispatch_contract", "handover_notes"),
    ):
        tile = ui_payload.get(tile_name)
        if isinstance(tile, dict) and isinstance(tile.get(note_field), list):
            tile[note_field] = _sanitize_public_notes(tile[note_field])
    ui_payload = _strip_forbidden_keys(ui_payload)

    response_class = str(result_state.output_response_class or "structured_clarification")
    conversation_strategy = build_governed_conversation_strategy_contract(result_state, response_class)
    turn_context = build_governed_turn_context(
        state=result_state,
        strategy=conversation_strategy,
        response_class=response_class,
    )
    assertions_payload: dict[str, Any] = {}
    for k, e in (result_state.asserted.assertions or {}).items():
        if e.asserted_value is not None:
            assertions_payload[k] = {"value": str(e.asserted_value), "confidence": e.confidence}

    structured_state = _governed_structured_state(persisted_state, response_class)
    deterministic_reply = str(result_state.output_reply or "").strip()

    return GovernedReplyAssemblyContext(
        response_class=response_class,
        structured_state=structured_state,
        assertions_payload=assertions_payload,
        conversation_strategy=conversation_strategy,
        turn_context=turn_context,
        run_meta={"version_provenance": _build_structured_version_provenance(decision=None)},
        ui_payload=ui_payload,
        deterministic_reply=deterministic_reply,
    )

def _assemble_governed_stream_payload(
    *,
    context: GovernedReplyAssemblyContext,
    visible_reply: str | None = None,
) -> dict[str, Any]:
    fallback_reply = str(context.deterministic_reply or "").strip()
    final_reply = str(visible_reply or "").strip() or fallback_reply
    
    public_reply = assemble_user_facing_reply(
        reply=final_reply,
        structured_state=context.structured_state,
        policy_path="governed",
        run_meta=context.run_meta,
        response_class=context.response_class,
        fallback_text=fallback_reply,
    )

    return {
        "type": "state_update",
        **public_reply,
        "assertions": context.assertions_payload,
        "conversation_strategy": context.conversation_strategy.model_dump(),
        "turn_context": context.turn_context.model_dump(),
        "ui": context.ui_payload,
    }
