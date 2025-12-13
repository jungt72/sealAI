"""Resume/await routing helpers for LangGraph v2."""

from __future__ import annotations

from typing import Dict, List

from app.langgraph_v2.state import AskMissingScope, SealAIState
from app.langgraph.io import AskMissingRequest


def resume_router_node(state: SealAIState, *_args, **_kwargs) -> Dict[str, object]:
    """
    Entry router that detects paused ask-missing runs and shortcuts to the right branch.
    """
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


__all__ = ["resume_router_node", "await_user_input_node"]
