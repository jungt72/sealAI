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
from typing import Any, Dict, Optional

import structlog

from app.langgraph_v2.phase import PHASE
from app.langgraph_v2.state import SealAIState, TechnicalParameters, WorkingMemory
from app.langgraph_v2.utils.messages import latest_user_text

logger = structlog.get_logger("langgraph_v2.node_router")

# ---------------------------------------------------------------------------
# Pattern sets for deterministic classification
# ---------------------------------------------------------------------------

_RFQ_PATTERNS = re.compile(
    r"\b("
    r"angebot(?:e|s)?\s+(?:einholen|anfordern|senden|erstellen)"
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
    params = state.parameters
    if params is None:
        return False
    if isinstance(params, TechnicalParameters):
        d = params.model_dump(exclude_none=True)
    elif isinstance(params, dict):
        d = {k: v for k, v in params.items() if v is not None}
    else:
        return False
    return len(d) > 0


def _has_prior_response(state: SealAIState) -> bool:
    """Check if the graph has already produced a response in this session."""
    wm = state.working_memory
    if wm is None:
        return False
    if isinstance(wm, WorkingMemory):
        return bool(wm.response_text)
    if isinstance(wm, dict):
        return bool(wm.get("response_text"))
    return False


def _is_hitl_resume(state: SealAIState) -> bool:
    """Check if user is resuming from an HITL confirmation gate."""
    return bool(
        state.awaiting_user_confirmation and state.confirm_decision
    )


# ---------------------------------------------------------------------------
# Router classification
# ---------------------------------------------------------------------------


def classify_input(state: SealAIState, user_text: str) -> str:
    """Deterministic classifier for the v4.4.0 Router Node.

    Returns one of: "rfq_trigger", "resume", "new_case", "follow_up", "clarification".
    """
    text = (user_text or "").strip()

    # 1. RFQ trigger (highest priority — explicit commercial action)
    if text and _RFQ_PATTERNS.search(text):
        return "rfq_trigger"

    # 2. HITL resume passthrough
    if _is_hitl_resume(state):
        return "resume"

    # 3. Explicit new-case request (overrides follow-up even with existing params)
    if text and _NEW_CASE_PATTERNS.search(text):
        return "new_case"

    has_params = _has_populated_parameters(state)
    has_response = _has_prior_response(state)

    # 4. Follow-up: existing parameters + parameter-change language
    if has_params and text and _PARAMETER_CHANGE_PATTERNS.search(text):
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
    user_text = latest_user_text(state.messages) or ""
    classification = classify_input(state, user_text)

    logger.info(
        "node_router_classified",
        classification=classification,
        user_text_len=len(user_text),
        has_params=_has_populated_parameters(state),
        has_response=_has_prior_response(state),
        is_hitl=_is_hitl_resume(state),
        run_id=state.run_id,
        thread_id=state.thread_id,
    )

    return {
        "router_classification": classification,
        "phase": PHASE.ROUTING,
        "last_node": "node_router",
    }


__all__ = [
    "node_router",
    "classify_input",
]
