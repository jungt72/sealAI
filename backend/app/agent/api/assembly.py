import logging
import dataclasses
from dataclasses import dataclass
from typing import Any

from app.agent.state.models import GovernedSessionState, TurnContextContract, ProposedCaseDelta
from app.agent.graph import GraphState
from app.agent.state.projections import project_for_ui
from app.agent.runtime.answer_trace import AnswerTrace, build_answer_trace, with_answer_trace
from app.agent.runtime.final_answer_layer import FinalAnswerEnvelope, apply_final_answer_layer
from app.agent.runtime.response_renderer import render_response
from app.agent.graph.output_contract_assembly import build_governed_conversation_strategy_contract
from app.agent.domain.case_delta import proposed_case_delta_from_extractions
from app.agent.runtime.turn_context import build_governed_turn_context
from app.agent.runtime.user_facing_reply import assemble_user_facing_reply
from app.agent.api.utils import _governed_structured_state
from app.agent.api.deps import _GRAPH_MODEL_ID, VISIBLE_REPLY_PROMPT_VERSION, VISIBLE_REPLY_PROMPT_HASH
from app.agent.prompts import REASONING_PROMPT_HASH, REASONING_PROMPT_VERSION
from app.agent.v92.runtime_contract import apply_v92_contracts_to_payload
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
    answer_markdown: str | None = None
    answer_markdown_source: str = "deterministic_reply"
    answer_markdown_error: str | None = None
    proposed_case_delta: ProposedCaseDelta = dataclasses.field(default_factory=ProposedCaseDelta)
    domain_context: dict[str, Any] = dataclasses.field(default_factory=dict)
    v91_field_governance_decisions: list[Any] = dataclasses.field(default_factory=list)
    v91_question_plan: Any | None = None
    v91_conversation_task: Any | None = None
    v91_dialogue_debt: Any | None = None
    v91_final_answer_context: Any | None = None

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
    answer_markdown = str(result_state.output_answer_markdown or "").strip() or None
    answer_markdown_source = str(result_state.output_answer_markdown_source or "").strip() or "deterministic_reply"
    answer_markdown_error = str(result_state.governed_answer_composer_error or "").strip() or None
    turn_index = int(getattr(result_state, "user_turn_index", 0) or result_state.analysis_cycle or 0)
    proposed_case_delta = proposed_case_delta_from_extractions(
        result_state.observed.raw_extractions,
        turn_index=turn_index,
    )

    return GovernedReplyAssemblyContext(
        response_class=response_class,
        structured_state=structured_state,
        assertions_payload=assertions_payload,
        conversation_strategy=conversation_strategy,
        turn_context=turn_context,
        run_meta={
            "version_provenance": _build_structured_version_provenance(decision=None),
            "governed_answer_composer": {
                "source": answer_markdown_source,
                "error": answer_markdown_error,
                "prompt_trace": dict(getattr(result_state, "governed_answer_prompt_trace", {}) or {}),
            },
            "v91": {
                "field_governance_decisions": [
                    decision.model_dump(mode="json")
                    for decision in result_state.v91_field_governance_decisions
                ],
                "question_plan": (
                    result_state.v91_question_plan.model_dump(mode="json")
                    if result_state.v91_question_plan is not None
                    else None
                ),
                "conversation_task": result_state.v91_conversation_task.model_dump(
                    mode="json"
                ),
                "dialogue_debt": result_state.v91_dialogue_debt.model_dump(
                    mode="json"
                ),
                "final_answer_context": (
                    result_state.v91_final_answer_context.model_dump(mode="json")
                    if result_state.v91_final_answer_context is not None
                    else None
                ),
            },
        },
        ui_payload=ui_payload,
        deterministic_reply=deterministic_reply,
        answer_markdown=answer_markdown,
        answer_markdown_source=answer_markdown_source,
        answer_markdown_error=answer_markdown_error,
        proposed_case_delta=proposed_case_delta,
        v91_field_governance_decisions=result_state.v91_field_governance_decisions,
        v91_question_plan=result_state.v91_question_plan,
        v91_conversation_task=result_state.v91_conversation_task,
        v91_dialogue_debt=result_state.v91_dialogue_debt,
        v91_final_answer_context=result_state.v91_final_answer_context,
    )

def _assemble_governed_stream_payload(
    *,
    context: GovernedReplyAssemblyContext,
    session_id: str = "default",
    user_message: str = "",
    state: GovernedSessionState | None = None,
    visible_reply: str | None = None,
    visible_reply_trace: AnswerTrace | None = None,
) -> dict[str, Any]:
    # V7 invariant: governed runtime has exactly one visible answer selector.
    # ``reply`` remains the deterministic backend fallback; ``answer_markdown``
    # may only come from the governed composer or that same fallback. The legacy
    # visible-reply/HCL parameters are kept for old call-site compatibility but
    # are intentionally ignored here.
    _ = (visible_reply, visible_reply_trace)
    fallback_reply = str(context.deterministic_reply or "").strip()
    visible_answer = (
        str(context.answer_markdown or "").strip()
        if context.answer_markdown_source in {"governed_composer", "composer_fallback"}
        else ""
    )
    if visible_answer:
        visible_answer = render_response(visible_answer, path="GOVERNED").text
    composer_attempted = context.answer_markdown_source in {
        "governed_composer",
        "composer_fallback",
    }
    composer_succeeded = context.answer_markdown_source == "governed_composer"
    composer_fallback_reason = (
        context.answer_markdown_error
        if context.answer_markdown_source == "composer_fallback"
        else None
    )

    public_reply = assemble_user_facing_reply(
        reply=fallback_reply,
        structured_state=context.structured_state,
        policy_path="governed",
        run_meta=context.run_meta,
        response_class=context.response_class,
        fallback_text=fallback_reply,
    )
    assembly_reply = str(public_reply.get("reply") or "").strip()
    assembly_guard_overwrote = bool(fallback_reply and assembly_reply != fallback_reply)
    if visible_answer:
        public_reply["answer_markdown"] = visible_answer
        answer_trace = build_answer_trace(
            reply_source="governed_output_contract",
            answer_markdown_source=context.answer_markdown_source,
            final_visible_source="answer_markdown",
            composer_attempted=composer_attempted,
            composer_succeeded=composer_succeeded,
            fallback_reason=composer_fallback_reason,
        )
    elif assembly_guard_overwrote:
        answer_trace = build_answer_trace(
            reply_source="api_guard",
            answer_markdown_source="deterministic_fallback",
            final_visible_source="answer_markdown",
            composer_attempted=composer_attempted,
            composer_succeeded=composer_succeeded,
            fallback_reason=composer_fallback_reason or "api_guard",
        )
    else:
        answer_trace = build_answer_trace(
            reply_source="governed_output_contract",
            answer_markdown_source=(
                "composer_fallback"
                if context.answer_markdown_source == "composer_fallback"
                else "deterministic_fallback"
            ),
            final_visible_source="answer_markdown",
            composer_attempted=composer_attempted,
            composer_succeeded=composer_succeeded,
            fallback_reason=composer_fallback_reason,
        )

    public_reply["run_meta"] = with_answer_trace(
        public_reply.get("run_meta"),
        answer_trace,
    )
    public_reply = apply_final_answer_layer(
        public_reply,
        FinalAnswerEnvelope(
            route="governed",
            answer_mode=str(context.response_class or "governed"),
            deterministic_fallback_reply=fallback_reply,
            existing_answer_markdown=public_reply.get("answer_markdown"),
            existing_answer_markdown_source=answer_trace.get("answer_markdown_source"),
            existing_reply_source=answer_trace.get("reply_source"),
            composer_tier=(
                "tier_b"
                if answer_trace.get("answer_markdown_source") == "governed_composer"
                else "tier_a"
            ),
            fallback_reason=answer_trace.get("fallback_reason"),
        ),
    )
    assistant_message = str(
        public_reply.get("answer_markdown") or public_reply.get("reply") or ""
    ).strip()

    payload = {
        "type": "state_update",
        **public_reply,
        "assistant_message": assistant_message,
        "proposed_case_delta": context.proposed_case_delta.model_dump(mode="json"),
        "assertions": context.assertions_payload,
        "conversation_strategy": context.conversation_strategy.model_dump(),
        "turn_context": context.turn_context.model_dump(),
        "v91_field_governance_decisions": [
            decision.model_dump(mode="json")
            if hasattr(decision, "model_dump")
            else decision
            for decision in context.v91_field_governance_decisions
        ],
        "v91_question_plan": (
            context.v91_question_plan.model_dump(mode="json")
            if context.v91_question_plan is not None
            else None
        ),
        "v91_conversation_task": (
            context.v91_conversation_task.model_dump(mode="json")
            if context.v91_conversation_task is not None
            else None
        ),
        "v91_dialogue_debt": (
            context.v91_dialogue_debt.model_dump(mode="json")
            if context.v91_dialogue_debt is not None
            else None
        ),
        "v91_final_answer_context": (
            context.v91_final_answer_context.model_dump(mode="json")
            if context.v91_final_answer_context is not None
            else None
        ),
        "ui": context.ui_payload,
    }
    return apply_v92_contracts_to_payload(
        payload,
        session_id=session_id,
        user_message=user_message,
        state=state,
        route_hint="governed",
        case_id=session_id,
    )
