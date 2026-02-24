from __future__ import annotations

"""Prepare the contract-first response payload for the answer subgraph.

This node transforms runtime state into an ``AnswerContract`` that acts as the
Evidence Authority for downstream rendering and verification. It collects:
- selected fact identifiers derived from RAG/source chunks,
- calculator outputs from deterministic computation nodes,
- resolved technical parameters and disclaimer obligations.

The resulting contract hash is persisted in state and later used by
``node_verify_claims`` for State-Race-Condition Protection.
"""

import hashlib
import re
from copy import deepcopy
from typing import Any, Dict, List

import structlog

from app.langgraph_v2.state.sealai_state import AnswerContract, SealAIState
from app.langgraph_v2.utils.context_manager import build_final_context, dedupe_retrieval_chunks

logger = structlog.get_logger("langgraph_v2.answer_subgraph.prepare_contract")
_PRESSURE_BAR_PATTERN = re.compile(
    r"(?:max(?:imaler)?\s*(?:druck|pressure)|druck\s*max|pressure\s*max)[^\d]{0,20}(\d+(?:[.,]\d+)?)\s*bar",
    re.IGNORECASE,
)


def _as_dict(value: Any) -> Dict[str, Any]:
    """Convert model-like values into plain dicts.

    Args:
        value: Arbitrary object, dict, or Pydantic model.

    Returns:
        A shallow dict copy when possible; otherwise an empty dict.
    """
    if isinstance(value, dict):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(exclude_none=True)
        if isinstance(dumped, dict):
            return dict(dumped)
    return {}


def _extract_selected_fact_ids(state: SealAIState) -> List[str]:
    """Build deterministic fact references from source and panel payloads.

    Args:
        state: Current graph state.

    Returns:
        Deduplicated ``document_id:chunk_id`` identifiers used as evidence
        references in the ``AnswerContract``.
    """
    selected: List[str] = []
    seen: set[str] = set()

    for idx, src in enumerate(list(state.sources or [])):
        src_dict = _as_dict(src)
        metadata = _as_dict(src_dict.get("metadata"))
        document_id = (
            metadata.get("document_id")
            or src_dict.get("document_id")
            or src_dict.get("source")
            or f"source_{idx}"
        )
        chunk_id = metadata.get("chunk_id") or metadata.get("id") or str(idx)
        value = f"{document_id}:{chunk_id}"
        if value in seen:
            continue
        seen.add(value)
        selected.append(value)

    panel_material = _as_dict(_as_dict(state.working_memory).get("panel_material"))
    for idx, hit in enumerate(panel_material.get("technical_docs") or []):
        if not isinstance(hit, dict):
            continue
        metadata = _as_dict(hit.get("metadata"))
        document_id = metadata.get("document_id") or hit.get("document_id") or hit.get("source") or f"doc_{idx}"
        chunk_id = metadata.get("chunk_id") or hit.get("chunk_id") or str(idx)
        value = f"{document_id}:{chunk_id}"
        if value in seen:
            continue
        seen.add(value)
        selected.append(value)

    return selected


def _resolve_calc_results(state: SealAIState) -> Dict[str, Any]:
    """Normalize calculator results from legacy and current state fields.

    Args:
        state: Current graph state.

    Returns:
        A dict with calculation outputs or an empty dict.
    """
    if state.calc_results is not None:
        return _as_dict(state.calc_results)
    if isinstance(state.calculation_result, dict):
        return dict(state.calculation_result)
    return {}


def _has_technical_parameters(state: SealAIState) -> bool:
    """Check whether user-provided technical parameters exist.

    Args:
        state: Current graph state.

    Returns:
        ``True`` when technical parameters are present, otherwise ``False``.
    """
    parameters = getattr(state, "parameters", None)
    if parameters is None:
        return False
    as_dict = getattr(parameters, "as_dict", None)
    if callable(as_dict):
        return bool(as_dict())
    if isinstance(parameters, dict):
        return bool(parameters)
    return False


def _extract_retrieval_chunks_for_authority(state: SealAIState) -> List[Dict[str, Any]]:
    chunks: List[Dict[str, Any]] = []
    panel_material = _as_dict(_as_dict(state.working_memory).get("panel_material"))
    technical_docs = panel_material.get("technical_docs")
    if isinstance(technical_docs, list):
        for item in technical_docs:
            if isinstance(item, dict):
                chunks.append(dict(item))

    retrieval_meta = _as_dict(getattr(state, "retrieval_meta", {}) or {})
    for key in ("hits", "documents", "chunks"):
        maybe_hits = retrieval_meta.get(key)
        if not isinstance(maybe_hits, list):
            continue
        for item in maybe_hits:
            if isinstance(item, dict):
                chunks.append(dict(item))

    for source in list(state.sources or []):
        src_dict = _as_dict(source)
        if not src_dict:
            continue
        chunks.append(
            {
                "text": src_dict.get("snippet") or src_dict.get("text") or "",
                "source": src_dict.get("source"),
                "metadata": _as_dict(src_dict.get("metadata")),
                "score": _as_dict(src_dict.get("metadata")).get("score"),
            }
        )
    return chunks


def _extract_authoritative_pressure_bar(state: SealAIState) -> float | None:
    ranked_chunks = dedupe_retrieval_chunks(_extract_retrieval_chunks_for_authority(state))
    for chunk in ranked_chunks:
        text = str(chunk.get("text") or "")
        match = _PRESSURE_BAR_PATTERN.search(text)
        if not match:
            continue
        raw = match.group(1).replace(",", ".")
        try:
            return float(raw)
        except ValueError:
            continue
    return None


def _is_smalltalk_request(state: SealAIState) -> bool:
    """Infer smalltalk intent from intent-goal and frontdoor routing flags.

    Args:
        state: Current graph state.

    Returns:
        ``True`` when current request should be treated as smalltalk.
    """
    intent_goal = str(getattr(getattr(state, "intent", None), "goal", "") or "").strip().lower()
    if intent_goal == "smalltalk":
        return True

    flags = _as_dict(getattr(state, "flags", {}) or {})
    intent_category = str(flags.get("frontdoor_intent_category") or "").strip().upper()
    if intent_category == "CHIT_CHAT":
        return True

    social_opening = bool(flags.get("frontdoor_social_opening"))
    task_intents_raw = flags.get("frontdoor_task_intents") or []
    task_intents = (
        [str(intent).strip() for intent in task_intents_raw]
        if isinstance(task_intents_raw, list)
        else []
    )
    return social_opening and not any(task_intents)


def node_prepare_contract(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    """Create an ``AnswerContract`` from state for contract-first answering.

    Transformation pipeline:
    1. Build final prompt context with configurable token budget.
    2. Resolve Evidence Authority from selected fact IDs (RAG/source chunks),
       technical parameters, and deterministic calculator results.
    3. Attach required disclaimers and uncertainty behavior.
    4. Persist contract hash for later State-Race-Condition Protection.

    Smalltalk override:
    If no evidence facts and no technical parameters are available, the node
    forces ``is_smalltalk=True`` and emits a friendly greeting contract. This
    avoids cold technical fallbacks with zero factual grounding.

    Args:
        state: Current graph state.
        *_args: Unused positional arguments for LangGraph compatibility.
        **_kwargs: Unused keyword arguments for LangGraph compatibility.

    Returns:
        State patch containing contract, prompt context, metadata, and flags.
    """
    max_tokens = 3000
    user_context = _as_dict(getattr(state, "user_context", {}))
    raw_budget = user_context.get("context_max_tokens")
    try:
        if raw_budget is not None:
            max_tokens = int(raw_budget)
    except (TypeError, ValueError):
        logger.warning("prepare_contract.invalid_context_budget", raw_budget=raw_budget)

    final_context = build_final_context(state, max_tokens=max_tokens)
    is_smalltalk = _is_smalltalk_request(state)
    selected_fact_ids = _extract_selected_fact_ids(state)
    has_technical_parameters = _has_technical_parameters(state)
    # Forced smalltalk heuristic:
    # No evidence + no technical inputs means there is nothing to verify against.
    # Prefer a friendly greeting instead of a speculative technical answer.
    if not is_smalltalk and not selected_fact_ids and not has_technical_parameters:
        is_smalltalk = True
        logger.info("prepare_contract.smalltalk_forced_no_facts_no_parameters")

    if is_smalltalk:
        resolved_parameters = {"response_style": "friendly_greeting"}
        calc_results = {"message_type": "smalltalk"}
        selected_fact_ids = ["friendly_greeting"]
        respond_with_uncertainty = False
        required_disclaimers: List[str] = []
    else:
        resolved_parameters = state.parameters.as_dict() if state.parameters else {}
        if "pressure_bar" not in resolved_parameters:
            authoritative_pressure = _extract_authoritative_pressure_bar(state)
            if authoritative_pressure is not None:
                resolved_parameters["pressure_bar"] = authoritative_pressure
        calc_results = _resolve_calc_results(state)

        respond_with_uncertainty = not bool(selected_fact_ids or calc_results)
        required_disclaimers = []
        if respond_with_uncertainty:
            required_disclaimers.append("Unsicherheits-Hinweis: Antwort basiert auf begrenzter Evidenz.")
        if bool(getattr(state, "requires_human_review", False)):
            required_disclaimers.append("Human review required before final recommendation.")
        if bool((state.flags or {}).get("is_safety_critical")):
            required_disclaimers.append("Sicherheitskritischer Kontext: Ergebnis vor Umsetzung fachlich prüfen.")

    contract = AnswerContract(
        resolved_parameters=resolved_parameters,
        calc_results=calc_results,
        selected_fact_ids=selected_fact_ids,
        required_disclaimers=required_disclaimers,
        respond_with_uncertainty=respond_with_uncertainty,
    )
    contract_hash = hashlib.sha256(contract.model_dump_json().encode()).hexdigest()

    flags = deepcopy(state.flags or {})
    flags["answer_contract_hash"] = contract_hash
    flags["answer_subgraph_patch_attempts"] = 0

    final_prompt_metadata = dict(state.final_prompt_metadata or {})
    final_prompt_metadata.update(
        {
            "contract_hash": contract_hash,
            "contract_first": True,
            "context_max_tokens": max_tokens,
        }
    )

    logger.info(
        "prepare_contract.done",
        contract_hash=contract_hash,
        is_smalltalk=is_smalltalk,
        selected_fact_count=len(selected_fact_ids),
        disclaimer_count=len(required_disclaimers),
        context_len=len(final_context),
    )
    return {
        "answer_contract": contract,
        "final_prompt": final_context,
        "final_prompt_metadata": final_prompt_metadata,
        "flags": flags,
        "last_node": "node_prepare_contract",
    }


__all__ = ["node_prepare_contract"]
