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
import math
import re
from copy import deepcopy
from typing import Any, Dict, List, Set, Tuple

import structlog

from app.langgraph_v2.nodes.answer_subgraph.state import AnswerSubgraphState
from app.langgraph_v2.state.sealai_state import AnswerContract, SealAIState, WorkingMemory
from app.langgraph_v2.utils.context_manager import build_final_context, dedupe_retrieval_chunks

logger = structlog.get_logger("langgraph_v2.answer_subgraph.prepare_contract")
_PRESSURE_BAR_PATTERN = re.compile(
    r"(?:max(?:imaler)?\s*(?:druck|pressure)|druck\s*max|pressure\s*max)[^\d]{0,20}(\d+(?:[.,]\d+)?)\s*bar",
    re.IGNORECASE,
)
_TEMPERATURE_C_PATTERN = re.compile(r"([-+]?\d+(?:[.,]\d+)?)\s*°?\s*c\b", re.IGNORECASE)
_EXTREME_TEMP_LOW_C = -50.0
_EXTREME_TEMP_HIGH_C = 200.0
_EXTREME_FACTCARD_IDS: Tuple[str, str] = ("PTFE-F-008", "PTFE-F-062")
_SEAL_MATERIAL_TOKENS = frozenset(
    {
        "ptfe",
        "nbr",
        "hnbr",
        "fkm",
        "ffkm",
        "epdm",
        "vmq",
        "fvmq",
        "pu",
        "pur",
        "tpu",
        "peek",
        "elastomer",
        "elastomeric",
    }
)
_NUMBER_TOKEN_PATTERN = re.compile(r"\b\d+(?:[.,]\d+)?\b")


def _add_number_token_with_variants(token: str, output: Set[str]) -> None:
    stripped = str(token or "").strip()
    if not stripped:
        return
    output.add(stripped)

    if "." in stripped:
        output.add(stripped.replace(".", ","))
    if "," in stripped:
        output.add(stripped.replace(",", "."))

    normalized = stripped.replace(",", ".")
    try:
        numeric = float(normalized)
    except (TypeError, ValueError):
        return

    if not math.isfinite(numeric):
        return

    rounded = int(round(numeric))
    output.add(str(rounded))
    output.add(f"{rounded}.0")
    output.add(f"{rounded},0")


def _latest_user_text(state: SealAIState) -> str:
    for msg in reversed(list(state.messages or [])):
        role = getattr(msg, "type", None) or getattr(msg, "role", None)
        if role in ("human", "user"):
            return str(getattr(msg, "content", "") or "")
    return ""


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


def _normalize_material_token(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    return re.sub(r"[^a-z0-9]+", "", text)


def _looks_like_seal_material(value: Any) -> bool:
    token = _normalize_material_token(value)
    if not token:
        return False
    return token in _SEAL_MATERIAL_TOKENS


def _extract_selected_seal_material(state: SealAIState, resolved: Dict[str, Any]) -> str | None:
    for value in (
        resolved.get("seal_material"),
        resolved.get("selected_seal_material"),
        (state.material_choice or {}).get("material"),
    ):
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


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


def _collect_number_tokens(value: Any, output: Set[str]) -> None:
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        _add_number_token_with_variants(str(value), output)
        return
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return
        for token in _NUMBER_TOKEN_PATTERN.findall(text):
            _add_number_token_with_variants(token, output)
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


def _extract_allowed_number_tokens_from_state(state: SealAIState, resolved_parameters: Dict[str, Any]) -> List[str]:
    tokens: Set[str] = set()
    _collect_number_tokens(getattr(state, "extracted_params", None), tokens)
    _collect_number_tokens(getattr(state, "parameters", None), tokens)
    _collect_number_tokens(getattr(state, "working_profile", None), tokens)
    _collect_number_tokens(getattr(state, "live_calc_tile", None), tokens)
    _collect_number_tokens(getattr(state, "calculation_result", None), tokens)
    _collect_number_tokens(getattr(state, "calc_results", None), tokens)
    _collect_number_tokens(resolved_parameters, tokens)
    return sorted(tokens)


def _extract_temperature_candidates_c(state: SealAIState) -> List[float]:
    values: List[float] = []
    params = getattr(state, "parameters", None)
    if params is not None:
        for field in (
            "temperature_C",
            "temperature_min",
            "temperature_max",
            "T_medium_min",
            "T_medium_max",
            "T_ambient_min",
            "T_ambient_max",
        ):
            raw = getattr(params, field, None)
            if raw is None:
                continue
            try:
                values.append(float(raw))
            except (TypeError, ValueError):
                continue

    user_text = _latest_user_text(state)
    for match in _TEMPERATURE_C_PATTERN.finditer(user_text):
        raw = match.group(1).replace(",", ".")
        try:
            values.append(float(raw))
        except ValueError:
            continue
    return values


def _is_extreme_temperature_query(state: SealAIState) -> bool:
    for temp_c in _extract_temperature_candidates_c(state):
        if temp_c < _EXTREME_TEMP_LOW_C or temp_c > _EXTREME_TEMP_HIGH_C:
            return True
    return False


def _hit_matches_factcard(hit: Dict[str, Any], factcard_id: str) -> bool:
    needle = factcard_id.strip().lower()
    if not needle:
        return False

    metadata = _as_dict(hit.get("metadata"))
    haystacks = (
        str(hit.get("document_id") or ""),
        str(hit.get("source") or ""),
        str(hit.get("snippet") or hit.get("text") or ""),
        str(metadata.get("id") or ""),
        str(metadata.get("document_id") or ""),
        str(metadata.get("doc_id") or ""),
        str(metadata.get("factcard_id") or ""),
    )
    return any(needle in item.lower() for item in haystacks if item)


def _normalize_factcard_hit(hit: Dict[str, Any], factcard_id: str) -> Dict[str, Any]:
    metadata = _as_dict(hit.get("metadata"))
    metadata.setdefault("id", factcard_id)
    metadata.setdefault("factcard_id", factcard_id)
    metadata.setdefault("document_id", hit.get("document_id") or factcard_id)
    metadata.setdefault("chunk_id", hit.get("chunk_id") or factcard_id)

    text = str(hit.get("text") or hit.get("snippet") or "").strip()
    return {
        "text": text,
        "snippet": str(hit.get("snippet") or text),
        "source": hit.get("source") or factcard_id,
        "document_id": hit.get("document_id") or factcard_id,
        "chunk_id": hit.get("chunk_id") or factcard_id,
        "score": hit.get("score"),
        "metadata": metadata,
    }


def _dedupe_technical_docs(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    deduped: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for idx, chunk in enumerate(chunks):
        if not isinstance(chunk, dict):
            continue
        metadata = _as_dict(chunk.get("metadata"))
        document_id = (
            metadata.get("document_id")
            or chunk.get("document_id")
            or chunk.get("source")
            or f"doc_{idx}"
        )
        chunk_id = metadata.get("chunk_id") or chunk.get("chunk_id") or str(idx)
        key = f"{document_id}:{chunk_id}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(chunk)
    return deduped


def _fetch_extreme_temperature_factcards(state: SealAIState) -> List[Dict[str, Any]]:
    if not _is_extreme_temperature_query(state):
        return []

    try:
        from app.mcp.knowledge_tool import search_technical_docs
    except Exception as exc:
        logger.warning("prepare_contract.factcard_search_import_failed", error=str(exc))
        return []

    forced_hits: List[Dict[str, Any]] = []
    tenant_scope = getattr(state, "tenant_id", None) or getattr(state, "user_id", None)

    for factcard_id in _EXTREME_FACTCARD_IDS:
        query = f"FactCard {factcard_id} PTFE"
        if factcard_id == "PTFE-F-008":
            query = f"{query} cryogenic -200C"
        elif factcard_id == "PTFE-F-062":
            query = f"{query} spring energization preload"

        matched: List[Dict[str, Any]] = []
        filters_to_try = (
            {"id": factcard_id, "doc_type": "ptfe_factcard"},
            None,
        )
        for metadata_filters in filters_to_try:
            try:
                payload = search_technical_docs(
                    query=query,
                    tenant_id=tenant_scope,
                    k=6,
                    metadata_filters=metadata_filters,
                )
            except Exception as exc:
                logger.warning(
                    "prepare_contract.factcard_search_failed",
                    factcard_id=factcard_id,
                    error=str(exc),
                )
                continue

            hits = list(payload.get("hits") or [])
            matched = [hit for hit in hits if isinstance(hit, dict) and _hit_matches_factcard(hit, factcard_id)]
            if matched:
                break

        if not matched:
            logger.warning("prepare_contract.factcard_missing_for_extreme_temp", factcard_id=factcard_id)
            continue
        forced_hits.append(_normalize_factcard_hit(matched[0], factcard_id))

    if forced_hits:
        logger.info(
            "prepare_contract.factcard_augmented_for_extreme_temp",
            factcard_ids=[hit.get("metadata", {}).get("id") for hit in forced_hits],
        )
    return forced_hits


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
    if parameters is not None:
        as_dict = getattr(parameters, "as_dict", None)
        if callable(as_dict) and bool(as_dict()):
            return True
        if isinstance(parameters, dict) and bool(parameters):
            return True
    extracted = getattr(state, "extracted_params", None)
    if isinstance(extracted, dict) and bool(extracted):
        return True
    working_profile = getattr(state, "working_profile", None)
    if working_profile is not None:
        profile_dump = _as_dict(working_profile)
        if bool(profile_dump):
            return True
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


def _is_gate_triggered(state: SealAIState, gate_id: str) -> bool:
    kb_result = _as_dict(getattr(state, "kb_factcard_result", {}) or {})
    triggered = kb_result.get("triggered_pattern_gates")
    if not isinstance(triggered, list):
        return False
    needle = str(gate_id or "").strip().upper()
    for item in triggered:
        if not isinstance(item, dict):
            continue
        value = str(item.get("gate_id") or "").strip().upper()
        if value == needle:
            return True
    return False


def _extract_runout_hardness_missing_flags(state: SealAIState) -> tuple[bool, bool]:
    params = getattr(state, "parameters", None)
    runout_value = None
    hardness_value = None
    if params is not None:
        runout_value = (
            getattr(params, "shaft_runout", None)
            or getattr(params, "runout", None)
            or getattr(params, "dynamic_runout", None)
        )
        hardness_value = getattr(params, "shaft_hardness", None) or getattr(params, "hardness", None)
    extracted = getattr(state, "extracted_params", None)
    if isinstance(extracted, dict):
        if runout_value is None:
            runout_value = extracted.get("runout_mm") or extracted.get("runout") or extracted.get("shaft_runout")
        if hardness_value is None:
            hardness_value = extracted.get("hrc_value") or extracted.get("hrc") or extracted.get("shaft_hardness")
    missing_runout = runout_value is None or str(runout_value).strip() == ""
    missing_hardness = hardness_value is None or str(hardness_value).strip() == ""
    return missing_runout, missing_hardness


def _build_resolved_parameters(state: SealAIState) -> Dict[str, Any]:
    resolved: Dict[str, Any] = state.parameters.as_dict() if state.parameters else {}

    extracted = state.extracted_params or {}
    if isinstance(extracted, dict):
        for key, value in extracted.items():
            if value is None:
                continue
            resolved.setdefault(key, value)

    # Alias-map extraction keys into fields used by final templates.
    if resolved.get("speed_rpm") is None:
        rpm = resolved.get("rpm")
        if rpm is not None:
            resolved["speed_rpm"] = rpm

    if resolved.get("shaft_diameter") is None:
        shaft_d = resolved.get("shaft_d1_mm") or resolved.get("shaft_d1") or resolved.get("d1")
        if shaft_d is not None:
            resolved["shaft_diameter"] = shaft_d

    if resolved.get("pressure_bar") is None:
        pressure_bar = resolved.get("pressure_max_bar") or resolved.get("p_max")
        if pressure_bar is not None:
            resolved["pressure_bar"] = pressure_bar

    if resolved.get("temperature_C") is None:
        temperature_c = resolved.get("temperature_max_c") or resolved.get("temp_max") or resolved.get("temperature_max")
        if temperature_c is not None:
            resolved["temperature_C"] = temperature_c

    # Persist chosen seal compound independently from shaft/counterface material.
    seal_material = _extract_selected_seal_material(state, resolved)
    if seal_material:
        resolved["seal_material"] = seal_material

    # Guardrail: never keep seal compounds in the shaft/counterface `material` field.
    material_value = resolved.get("material")
    if _looks_like_seal_material(material_value):
        material_text = str(material_value or "").strip()
        if material_text:
            resolved.setdefault("seal_material", material_text)
        resolved.pop("material", None)

    return resolved


def node_prepare_contract(state: AnswerSubgraphState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
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

    augmented_wm = None
    context_state = state
    forced_factcards = _fetch_extreme_temperature_factcards(state)
    if forced_factcards:
        wm_dict = _as_dict(getattr(state, "working_memory", None))
        panel_material = _as_dict(wm_dict.get("panel_material"))
        technical_docs = list(panel_material.get("technical_docs") or [])
        technical_docs.extend(forced_factcards)
        panel_material["technical_docs"] = _dedupe_technical_docs(technical_docs)
        wm_dict["panel_material"] = panel_material
        augmented_wm = WorkingMemory.model_validate(wm_dict)
        context_state = state.model_copy(update={"working_memory": augmented_wm})

    final_context = build_final_context(context_state, max_tokens=max_tokens)
    is_smalltalk = _is_smalltalk_request(state)
    selected_fact_ids = _extract_selected_fact_ids(context_state)
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
        resolved_parameters = _build_resolved_parameters(state)
        if "pressure_bar" not in resolved_parameters:
            authoritative_pressure = _extract_authoritative_pressure_bar(context_state)
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
        if _is_gate_triggered(state, "PTFE-G-011"):
            missing_runout, missing_hardness = _extract_runout_hardness_missing_flags(state)
            missing_critical_parameters: List[str] = []
            if missing_runout:
                missing_critical_parameters.append("Wellenschlag")
            if missing_hardness:
                missing_critical_parameters.append("Wellenhärte")
            if missing_critical_parameters:
                resolved_parameters["missing_critical_parameters"] = missing_critical_parameters
                required_disclaimers.append(
                    "Missing Critical Parameters: Wellenschlag und Wellenhärte müssen vor PTFE-Freigabe bestätigt werden."
                )

    contract = AnswerContract(
        resolved_parameters=resolved_parameters,
        calc_results=calc_results,
        selected_fact_ids=selected_fact_ids,
        required_disclaimers=required_disclaimers,
        respond_with_uncertainty=respond_with_uncertainty,
    )
    contract_hash = hashlib.sha256(contract.model_dump_json().encode()).hexdigest()

    flags = deepcopy(state.flags or {})
    flags["answer_subgraph_allowed_number_tokens"] = _extract_allowed_number_tokens_from_state(
        state,
        resolved_parameters,
    )
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
    patch = {
        "answer_contract": contract,
        "final_prompt": final_context,
        "final_prompt_metadata": final_prompt_metadata,
        "flags": flags,
        "last_node": "node_prepare_contract",
    }
    if augmented_wm is not None:
        patch["working_memory"] = augmented_wm
    return patch


__all__ = ["node_prepare_contract"]
