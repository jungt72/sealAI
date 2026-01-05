"""Resume/await routing helpers for LangGraph v2."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List

from langchain_core.messages import HumanMessage

from app.langgraph_v2.state import AskMissingScope, SealAIState, TechnicalParameters, WorkingMemory
from app.langgraph.io import AskMissingRequest
from app.langgraph_v2.utils.parameter_patch import apply_parameter_patch_with_provenance


def resume_router_node(state: SealAIState, *_args, **_kwargs) -> Dict[str, object]:
    """
    Entry router that detects paused ask-missing runs and shortcuts to the right branch.
    """
    if state.awaiting_user_confirmation and state.confirm_decision:
        return {
            "phase": "confirm",
            "last_node": "resume_router_node",
        }
    awaiting = bool(state.awaiting_user_input)
    scope: AskMissingScope | None = state.ask_missing_scope
    if scope is None and awaiting:
        # Heuristic fallback: if we have missing technical params, treat as technical ask.
        scope = "technical" if (state.missing_params or state.ask_missing_request) else "discovery"

    # Ensure ask-missing consistency: if awaiting but no request, synthesize one.
    ask_missing_request = state.ask_missing_request
    missing: List[str] = list(state.missing_params or [])
    if awaiting and ask_missing_request is None:
        question = (
            "Bitte ergänze noch die fehlenden Angaben: "
            f"{', '.join(missing) if missing else 'Bitte liefere die fehlenden technischen Parameter.'}"
        )
        ask_missing_request = AskMissingRequest(
            missing_fields=missing,
            question=question,
        )

    phase = state.phase or ("preflight_parameters" if scope == "technical" else "entry")

    return {
        "phase": phase,
        "ask_missing_scope": scope,
        "ask_missing_request": ask_missing_request,
        "last_node": "resume_router_node",
    }


def await_user_input_node(state: SealAIState, *_args, **_kwargs) -> Dict[str, object]:
    """
    Terminal placeholder for ask-missing pauses. Keeps the state stable for the checkpointer.
    """
    phase = state.phase or ("preflight_parameters" if state.ask_missing_scope == "technical" else "entry")
    return {
        "phase": phase,
        "awaiting_user_input": True,
        "last_node": "await_user_input_node",
    }


def confirm_resume_node(state: SealAIState, *_args, **_kwargs) -> Dict[str, object]:
    """
    Apply HITL decisions and resume with the pending action.
    """
    decision = (state.confirm_decision or "").strip().lower()
    pending_action = state.pending_action or "FINALIZE"
    resolved_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    updates: Dict[str, object] = {
        "awaiting_user_confirmation": False,
        "confirm_decision": None,
        "confirm_edits": {},
        "confirm_checkpoint": {},
        "confirm_checkpoint_id": None,
        "confirm_status": "resolved",
        "confirm_resolved_at": resolved_at,
        "pending_action": None,
        "confirmed_actions": [*(state.confirmed_actions or []), pending_action],
        "last_node": "confirm_resume_node",
    }

    if decision == "edit":
        edits = state.confirm_edits or {}
        parameters_patch = edits.get("parameters") or {}
        instructions = edits.get("instructions")
        merged_params, merged_provenance = apply_parameter_patch_with_provenance(
            state.parameters.as_dict() if state.parameters else {},
            parameters_patch,
            state.parameter_provenance,
            source="user",
        )
        updates["parameters"] = TechnicalParameters.model_validate(merged_params)
        updates["parameter_provenance"] = merged_provenance
        if isinstance(instructions, str) and instructions.strip():
            messages = list(state.messages or [])
            messages.append(HumanMessage(content=instructions.strip()))
            updates["messages"] = messages

    updates["next_action"] = pending_action
    return updates


def confirm_reject_node(state: SealAIState, *_args, **_kwargs) -> Dict[str, object]:
    """
    Safe response when a HITL checkpoint is rejected.
    """
    wm = state.working_memory or WorkingMemory()
    response_text = (
        "Abgebrochen. Ich habe die Aktion nicht ausgeführt. "
        "Wenn du fortfahren möchtest, gib bitte eine neue Freigabe oder aktualisiere die Parameter."
    )
    wm = wm.model_copy(update={"response_text": response_text, "response_kind": "confirm_reject"})
    return {
        "working_memory": wm,
        "final_text": response_text,
        "phase": state.phase or "confirm",
        "awaiting_user_confirmation": False,
        "confirm_decision": None,
        "confirm_edits": {},
        "confirm_checkpoint": {},
        "confirm_checkpoint_id": None,
        "confirm_status": "resolved",
        "confirm_resolved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "pending_action": None,
        "last_node": "confirm_reject_node",
    }


__all__ = [
    "resume_router_node",
    "await_user_input_node",
    "confirm_resume_node",
    "confirm_reject_node",
]
