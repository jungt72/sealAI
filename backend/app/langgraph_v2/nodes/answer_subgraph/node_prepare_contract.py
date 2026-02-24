from __future__ import annotations

import hashlib
from typing import Any, Dict, List

import structlog

from app.langgraph_v2.state.sealai_state import AnswerContract, SealAIState
from app.langgraph_v2.utils.context_manager import build_final_context

logger = structlog.get_logger("langgraph_v2.answer_subgraph.prepare_contract")


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(exclude_none=True)
        if isinstance(dumped, dict):
            return dict(dumped)
    return {}


def _extract_selected_fact_ids(state: SealAIState) -> List[str]:
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
    if state.calc_results is not None:
        return _as_dict(state.calc_results)
    if isinstance(state.calculation_result, dict):
        return dict(state.calculation_result)
    return {}


def _is_smalltalk_request(state: SealAIState) -> bool:
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

    if is_smalltalk:
        resolved_parameters = {"response_style": "friendly_greeting"}
        calc_results = {"message_type": "smalltalk"}
        selected_fact_ids = ["friendly_greeting"]
        respond_with_uncertainty = False
        required_disclaimers: List[str] = []
    else:
        resolved_parameters = state.parameters.as_dict() if state.parameters else {}
        calc_results = _resolve_calc_results(state)
        selected_fact_ids = _extract_selected_fact_ids(state)

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

    flags = dict(state.flags or {})
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
