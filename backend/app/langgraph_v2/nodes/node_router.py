"""Router node for SEALAI v4.4.0 (Sprint 3).

Classifies every user input into one of five categories before dispatching
to the correct graph entry point:

- new_case:      Fresh inquiry, no prior working profile
- follow_up:     Existing parameters, user modifies/adds values
- clarification: User asks about a previous result (direct LLM answer)
- rfq_trigger:   User requests RFQ / procurement action
- resume:        HITL confirmation pending (passthrough to resume_router)
"""

from __future__ import annotations

import re
from typing import Any, Dict

import structlog
from langchain_core.messages import AIMessage

from app.langgraph_v2.phase import PHASE
from app.langgraph_v2.state import SealAIState, WorkingMemory
from app.langgraph_v2.utils.messages import latest_user_text

logger = structlog.get_logger("langgraph_v2.node_router")

# ---------------------------------------------------------------------------
# Pattern sets for deterministic classification
# ---------------------------------------------------------------------------

_RFQ_PATTERNS = re.compile(
    r"\b("
    r"angebot(?:e|s)?\s+(?:einholen|anfordern|senden|erstellen)"
    r"|angebot\s+für\b"
    r"|angebot\s+f(?:u|ue|ü)r"
    r"|preisanfrage\b"
    r"|ich\s+brauche\s+ein\s+angebot\b"
    r"|ich\s+(?:brauche|ben[oö]tige|m[oö]chte)\s+ein\s+angebot"
    r"|preisanfrage"
    r"|preis\s+f(?:u|ue|ü)r"
    r"|quote\s+for\b"
    r"|quote\s+for"
    r"|bitte\s+um\s+ein\s+angebot\b"
    r"|bitte\s+um\s+(?:ein\s+)?angebot"
    r"|rfq\s+(?:senden|erstellen|generieren)"
    r"|anfrage\s+(?:senden|versenden)"
    r"|request\s+for\s+quotation"
    r"|send\s+rfq"
    r"|beschaffung\s+starten"
    r"|einkauf\s+starten"
    r")\b",
    re.IGNORECASE,
)

_NEW_CASE_PATTERNS = re.compile(
    r"\b("
    r"neue[rns]?\s+(?:anfrage|fall|case|projekt|auftrag)"
    r"|von\s+vorne"
    r"|neu\s+starten"
    r"|new\s+(?:case|request|inquiry)"
    r"|start\s+over"
    r")\b",
    re.IGNORECASE,
)

_CLARIFICATION_PATTERNS = re.compile(
    r"\b("
    r"warum"
    r"|wieso"
    r"|weshalb"
    r"|erkl[aä]r(?:e|st|t|en|ung)"
    r"|genauer"
    r"|detail(?:s|liert(?:er)?)"
    r"|was\s+meinst\s+du"
    r"|was\s+bedeutet"
    r"|kannst\s+du\s+(?:das\s+)?erkl[aä]ren"
    r"|why"
    r"|explain"
    r"|what\s+do\s+you\s+mean"
    r"|elaborate"
    r")\b",
    re.IGNORECASE,
)

_PARAMETER_CHANGE_PATTERNS = re.compile(
    r"\b("
    r"[aä]nder(?:e|n|ung)"
    r"|korrigier(?:e|en)"
    r"|aktualisier(?:e|en)"
    r"|update"
    r"|change"
    r"|statt(?:dessen)?"
    r"|(?:auf|zu)\s+\d+"
    r"|druck\s*[:=]?\s*\d+"
    r"|temperatur\s*[:=]?\s*\d+"
    r"|medium\s*[:=]?\s*\w+"
    r"|pressure\s*[:=]?\s*\d+"
    r"|temperature\s*[:=]?\s*\d+"
    r")\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _has_populated_parameters(state: SealAIState) -> bool:
    """Check if any technical parameter has a non-None value."""
    params = state.working_profile.engineering_profile
    if params is None:
        return False
    if hasattr(params, "as_dict"):
        d = params.as_dict()
    elif hasattr(params, "model_dump"):
        d = params.model_dump(exclude_none=True)
    elif isinstance(params, dict):
        d = {k: v for k, v in params.items() if v is not None}
    else:
        return False
    return len(d) > 0


def _has_prior_response(state: SealAIState) -> bool:
    """Check if the graph has already produced a response in this session."""
    wm = state.reasoning.working_memory
    if isinstance(wm, WorkingMemory):
        if bool(wm.response_text):
            return True
    elif isinstance(wm, dict) and bool(wm.get("response_text")):
        return True
    if bool(state.system.governed_output_text or state.system.final_text):
        return True
    for message in list(state.conversation.messages or []):
        if isinstance(message, AIMessage):
            return True
        if isinstance(message, dict):
            role = str(message.get("role") or "").strip().lower()
            if role == "assistant":
                return True
    return False


def _is_hitl_pending(state: SealAIState) -> bool:
    """Check if state indicates pending HITL/follow-up handling."""
    return bool(
        state.system.awaiting_user_confirmation
        or bool((state.system.pending_action or "").strip())
        or bool(state.reasoning.qgate_has_blockers)
    )


# ---------------------------------------------------------------------------
# Router classification
# ---------------------------------------------------------------------------


def classify_input(state: SealAIState, user_text: str) -> str:
    """Deterministic classifier for the v4.4.0 Router Node.

    Returns one of: "turn_limit_exceeded", "rfq_trigger", "resume", "new_case",
    "follow_up", "clarification".
    """
    text = (user_text or "").strip()
    block_reason = str(state.reasoning.output_blocked_reason or "").strip().lower()

    if bool(state.reasoning.output_blocked) and block_reason == "turn_limit_exceeded":
        return "turn_limit_exceeded"

    # 1. RFQ trigger (highest priority — explicit commercial action)
    if text and _RFQ_PATTERNS.search(text):
        return "rfq_trigger"

    # 2. Pending HITL/follow-up passthrough
    if _is_hitl_pending(state):
        return "resume"

    # 3. Explicit new-case request (overrides follow-up even with existing params)
    if text and _NEW_CASE_PATTERNS.search(text):
        return "new_case"

    has_params = _has_populated_parameters(state)
    has_response = _has_prior_response(state)

    # 4. Follow-up: existing parameters + parameter-change language or generic text in active session
    if has_params and text:
        if _PARAMETER_CHANGE_PATTERNS.search(text):
            return "follow_up"
        if has_response:
            # If we already have a profile and the user says SOMETHING, 
            # assume it might be a parameter update (State Continuity).
            return "follow_up"

    # 5. Clarification: prior response exists + clarification question
    if has_response and text and _CLARIFICATION_PATTERNS.search(text):
        return "clarification"

    # 6. Default: new case
    return "new_case"


# ---------------------------------------------------------------------------
# Node entry point
# ---------------------------------------------------------------------------


def node_router(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    """SEALAI v4.4.0 Router Node — classifies input and sets routing metadata."""
    user_text = latest_user_text(state.conversation.messages) or ""
    classification = classify_input(state, user_text)

    logger.info(
        "node_router_classified",
        classification=classification,
        user_text_len=len(user_text),
        has_params=_has_populated_parameters(state),
        has_response=_has_prior_response(state),
        is_hitl=_is_hitl_pending(state),
        run_id=state.system.run_id,
        thread_id=state.conversation.thread_id,
    )

    return {
        "conversation": {"router_classification": classification},
        "reasoning": {
            "phase": PHASE.ROUTING,
            "last_node": "node_router",
        },
    }


__all__ = [
    "node_router",
    "classify_input",
]
