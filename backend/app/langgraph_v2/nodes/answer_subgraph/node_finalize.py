from __future__ import annotations

"""Finalize verified answer text with last-mile numeric safety checks.

The No-New-Numbers guard compares numeric tokens from the verified draft
against the polished final candidate. If polishing introduces unseen numbers,
the node falls back to the verified draft as a final protection wall against
hallucinated quantitative claims.
"""

import re
from typing import Any, Dict, Set, Tuple

import structlog
from langchain_core.messages import AIMessage, BaseMessage

from app.langgraph_v2.state.sealai_state import SealAIState

logger = structlog.get_logger("langgraph_v2.answer_subgraph.finalize")

_NUMBER_TOKEN_PATTERN = re.compile(r"\b\d+(?:[.,]\d+)?\b")
# Citation markers like [1] or [1-3] are formatting references, not measured
# values. They are stripped before the No-New-Numbers comparison.
_BRACKET_REFERENCE_PATTERN = re.compile(r"\[\s*\d+(?:\s*[-,]\s*\d+)*\s*\]")
# Ordered-list prefixes ("1. ", "2. ") are structural text formatting and must
# not be interpreted as novel numeric claims.
_LIST_PREFIX_PATTERN = re.compile(r"(?m)^\s*\d+\.\s+")
_PTFE_FACT_ID_PATTERN = re.compile(r"^PTFE-F-\d{3}$", re.IGNORECASE)
_CORE_ALLOWED_TOKENS = frozenset({"327", "466", "19"})
_RFQ_OR_LASTENHEFT_PATTERN = re.compile(
    r"\b("
    r"rfq"
    r"|request\s+for\s+quotation"
    r"|angebot"
    r"|quote"
    r"|lastenheft"
    r"|ausschreibung"
    r")\b",
    re.IGNORECASE,
)


def _strip_formatting_numbers(text: str) -> str:
    """Remove numeric formatting tokens before semantic number checks.

    Args:
        text: Candidate output text.

    Returns:
        Text without citation/list numbering artifacts.
    """
    sanitized = _BRACKET_REFERENCE_PATTERN.sub(" ", text or "")
    sanitized = _LIST_PREFIX_PATTERN.sub("", sanitized)
    return sanitized


def _extract_number_tokens(text: str) -> Set[str]:
    """Extract numeric tokens from sanitized text.

    Args:
        text: Candidate output text.

    Returns:
        Set of numeric token strings.
    """
    return set(_NUMBER_TOKEN_PATTERN.findall(_strip_formatting_numbers(text)))


def _with_token_variants(tokens: Set[str]) -> Set[str]:
    expanded: Set[str] = set(tokens)
    for token in list(tokens):
        if "." in token:
            expanded.add(token.replace(".", ","))
            if token.endswith(".0") and token[:-2].isdigit():
                expanded.add(token[:-2])
        if "," in token:
            expanded.add(token.replace(",", "."))
            if token.endswith(",0") and token[:-2].isdigit():
                expanded.add(token[:-2])
        if token.isdigit():
            expanded.add(f"{token}.0")
            expanded.add(f"{token},0")
    return expanded


def _extract_selected_fact_ids(state: SealAIState) -> Set[str]:
    selected: Set[str] = set()

    state_selected = getattr(state, "selected_fact_ids", None)
    if isinstance(state_selected, list):
        selected.update(str(item).strip() for item in state_selected if str(item).strip())

    contract = getattr(state, "answer_contract", None)
    contract_selected = getattr(contract, "selected_fact_ids", None) if contract is not None else None
    if isinstance(contract_selected, list):
        selected.update(str(item).strip() for item in contract_selected if str(item).strip())

    return selected


def _extract_validated_factcard_number_tokens(selected_fact_ids: Set[str]) -> Set[str]:
    fact_ids = sorted(
        fact_id
        for fact_id in selected_fact_ids
        if _PTFE_FACT_ID_PATTERN.match(fact_id or "")
    )
    if not fact_ids:
        return set()

    try:
        from app.services.knowledge.factcard_store import FactCardStore
    except Exception as exc:
        logger.warning("finalize.factcard_store_unavailable", error=str(exc))
        return set()

    store = FactCardStore.get_instance()
    tokens: Set[str] = set()
    for fact_id in fact_ids:
        card = store.get_by_id(fact_id)
        if not isinstance(card, dict):
            continue
        for field in ("value", "conditions", "units", "property"):
            tokens.update(_extract_number_tokens(str(card.get(field) or "")))
        properties = card.get("properties")
        if isinstance(properties, dict):
            for value in properties.values():
                tokens.update(_extract_number_tokens(str(value or "")))

    return _with_token_variants(tokens)


def _collect_number_tokens(value: Any, output: Set[str]) -> None:
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        output.add(str(value))
        return
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return
        output.update(_NUMBER_TOKEN_PATTERN.findall(text))
        return
    if isinstance(value, dict):
        for nested in value.values():
            _collect_number_tokens(nested, output)
        return
    if isinstance(value, (list, tuple, set)):
        for nested in value:
            _collect_number_tokens(nested, output)
        return
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(exclude_none=True)
        if isinstance(dumped, dict):
            _collect_number_tokens(dumped, output)


def _extract_allowed_state_parameter_tokens(state: SealAIState) -> Set[str]:
    tokens: Set[str] = set()
    flags = getattr(state, "flags", {}) or {}
    from_prepare_contract = flags.get("answer_subgraph_allowed_number_tokens")
    if isinstance(from_prepare_contract, list):
        for token in from_prepare_contract:
            if token is None:
                continue
            stripped = str(token).strip()
            if stripped:
                tokens.add(stripped)

    _collect_number_tokens(getattr(state, "extracted_params", None), tokens)
    _collect_number_tokens(getattr(state, "parameters", None), tokens)
    _collect_number_tokens(getattr(state, "working_profile", None), tokens)
    _collect_number_tokens(getattr(state, "live_calc_tile", None), tokens)
    _collect_number_tokens(getattr(state, "calculation_result", None), tokens)
    _collect_number_tokens(getattr(state, "calc_results", None), tokens)
    contract = getattr(state, "answer_contract", None)
    if contract is not None:
        _collect_number_tokens(getattr(contract, "resolved_parameters", None), tokens)
        _collect_number_tokens(getattr(contract, "calc_results", None), tokens)
    return _with_token_variants(tokens)


def _latest_user_text(state: SealAIState) -> str:
    for msg in reversed(list(state.messages or [])):
        role = getattr(msg, "type", None) or getattr(msg, "role", None)
        if role in ("human", "user"):
            return str(getattr(msg, "content", "") or "")
    return ""


def _normalize_intents(raw: Any) -> Set[str]:
    if isinstance(raw, list):
        return {str(item).strip().lower() for item in raw if str(item).strip()}
    return set()


def _should_bypass_no_new_numbers_guard(state: SealAIState) -> Tuple[bool, str]:
    flags = getattr(state, "flags", {}) or {}
    if bool(flags.get("number_verification_skip_active")):
        return True, "number_verification_skip_active"

    intent_category = str(
        getattr(state, "intent_category", None)
        or flags.get("frontdoor_intent_category")
        or ""
    ).strip().upper()
    if intent_category == "MATERIAL_RESEARCH":
        return True, "material_research / explanation"

    if intent_category == "COMMERCIAL":
        return True, "intent_category=COMMERCIAL"

    intent = getattr(state, "intent", None)
    intent_goal = str(getattr(intent, "goal", "") or "").strip().lower()
    if intent_goal == "explanation_or_comparison":
        return True, "material_research / explanation"

    task_intents = _normalize_intents(getattr(state, "task_intents", None))
    task_intents.update(_normalize_intents(flags.get("frontdoor_task_intents")))
    if {"commercial", "rfq"} & task_intents:
        return True, "task_intents contains commercial/rfq"

    router_classification = str(getattr(state, "router_classification", "") or "").strip().lower()
    if router_classification == "rfq_trigger":
        return True, "router_classification=rfq_trigger"

    working_profile = getattr(state, "working_profile", None)
    goal = None
    if working_profile is not None:
        goal = getattr(working_profile, "goal", None)
        if goal is None and isinstance(working_profile, dict):
            goal = working_profile.get("goal")
    goal_text = str(goal or "").strip().lower()
    if goal_text == "explanation_or_comparison":
        return True, "material_research / explanation"
    if goal_text in {"commercial", "rfq", "lastenheft"}:
        return True, f"working_profile.goal={goal_text}"

    if _RFQ_OR_LASTENHEFT_PATTERN.search(_latest_user_text(state)):
        return True, "latest_user_text matched rfq/lastenheft pattern"

    return False, ""


def node_finalize(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    """Produce the user-visible final answer for the subgraph.

    Steps:
    1. Select polished final candidate (or fallback to draft).
    2. Apply No-New-Numbers guard against verified draft tokens.
    3. Persist ``final_text`` / ``final_answer`` and append AI message.

    Args:
        state: Current graph state.
        *_args: Unused positional arguments for LangGraph compatibility.
        **_kwargs: Unused keyword arguments for LangGraph compatibility.

    Returns:
        State patch containing final answer payload and optional error marker.
    """
    verified_draft = str(state.draft_text or "").strip()
    # Use `final_text` from the current subgraph run as the polished candidate;
    # fall back to the verified draft when no polished text is present.
    candidate_final = str(state.final_text or "").strip() or verified_draft

    bypass_number_guard, bypass_reason = _should_bypass_no_new_numbers_guard(state)
    selected_fact_ids: Set[str] = set()
    validated_fact_tokens: Set[str] = set()
    allowed_state_tokens: Set[str] = set()
    validated_tokens: Set[str] = set()
    blocked_tokens: list[str] = []
    new_tokens: list[str] = []

    if bypass_number_guard:
        blocked = False
        final_text = candidate_final
        logger.info("finalize.no_new_numbers_guard_bypassed", reason=bypass_reason)
    else:
        verified_tokens = _extract_number_tokens(verified_draft)
        candidate_tokens = _extract_number_tokens(candidate_final)
        new_tokens = sorted(candidate_tokens - verified_tokens)
        selected_fact_ids = _extract_selected_fact_ids(state)
        validated_fact_tokens = _extract_validated_factcard_number_tokens(selected_fact_ids)
        allowed_state_tokens = _extract_allowed_state_parameter_tokens(state)
        validated_tokens = _with_token_variants(set(_CORE_ALLOWED_TOKENS)) | validated_fact_tokens | allowed_state_tokens
        blocked_tokens = sorted(token for token in new_tokens if token not in validated_tokens)
        blocked = bool(blocked_tokens)
        final_text = verified_draft if blocked else candidate_final
    if not final_text:
        final_text = verified_draft or "Unable to safely finalize response; please provide additional context."

    messages: list[BaseMessage] = list(state.messages or [])
    messages.append(AIMessage(content=final_text))

    if blocked:
        logger.warning(
            "finalize.no_new_numbers_guard_blocked",
            new_number_tokens=blocked_tokens,
            selected_fact_ids=sorted(selected_fact_ids),
            validated_fact_tokens=sorted(validated_fact_tokens),
            allowed_state_tokens=sorted(allowed_state_tokens),
        )
    else:
        logger.info(
            "finalize.completed",
            final_length=len(final_text),
            allowed_new_tokens=[token for token in new_tokens if token in validated_tokens],
            selected_fact_ids=sorted(selected_fact_ids),
        )

    patch: Dict[str, Any] = {
        "messages": messages,
        "final_text": final_text,
        "final_answer": final_text,
        "phase": state.phase or "final",
        "last_node": "node_finalize",
    }
    if blocked:
        patch["error"] = "No-New-Numbers guard blocked unvalidated numbers; returning verified draft."
    return patch


__all__ = ["node_finalize"]
