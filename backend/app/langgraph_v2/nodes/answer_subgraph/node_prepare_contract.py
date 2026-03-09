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
from app.langgraph_v2.state.governance_types import IdentityClass, SpecificityLevel
from app.langgraph_v2.state.sealai_state import (
    AnswerContract,
    CandidateItem,
    GroundedFact,
    FactVariant,
    GovernanceMetadata,
    RequirementSpec,
    SealingRequirementSpec,
    SealAIState,
    WorkingMemory,
)
from app.langgraph_v2.utils.assertion_cycle import stamp_patch_with_assertion_binding
from app.langgraph_v2.utils.candidate_semantics import (
    annotate_material_choice,
    build_candidate_clusters,
    get_specificity_rank,
)
from app.langgraph_v2.utils.context_manager import build_final_context, dedupe_retrieval_chunks
from app.langgraph_v2.utils.rfq_admissibility import normalize_rfq_admissibility_contract


def _build_requirement_spec(
    resolved_parameters: Dict[str, Any],
    governance_metadata: GovernanceMetadata,
) -> RequirementSpec:
    """Extract technical requirements into a neutral specification.

    Filters operational window parameters and captures missing critical fields
    from the current analysis stage.
    """
    technical_keys = {
        "medium",
        "pressure_bar",
        "temperature_C",
        "shaft_diameter",
        "speed_rpm",
        "shaft_runout",
        "shaft_hardness",
        "dynamic_type",
    }
    operating_conditions = {
        k: v for k, v in resolved_parameters.items() if k in technical_keys and v is not None
    }

    missing_params = resolved_parameters.get("missing_critical_parameters", [])

    return RequirementSpec(
        operating_conditions=operating_conditions,
        missing_critical_parameters=list(missing_params) if isinstance(missing_params, list) else [],
        unknowns_release_blocking=list(governance_metadata.unknowns_release_blocking),
    )


def _artifact_id(prefix: str, state: SealAIState) -> str:
    cycle_id = int(getattr(state.reasoning, "current_assertion_cycle_id", 0) or 0)
    revision = int(getattr(state.reasoning, "asserted_profile_revision", 0) or 0)
    if cycle_id <= 0 or revision <= 0:
        return ""
    return f"{prefix}-c{cycle_id}-r{revision}"


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
_NORMATIVE_REFERENCE_PATTERN = re.compile(
    r"\b(?:DIN|ISO|EN|ASTM|ASME|API)\s*[A-Z0-9./-]*\d(?:[A-Z0-9./-]*)\b",
    re.IGNORECASE,
)
_IDENTITY_GUARDED_FIELDS = {"medium", "material", "seal_material", "trade_name", "product", "product_name", "seal_family", "flange_standard"}


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
    for msg in reversed(list(state.conversation.messages or [])):
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


def _working_profile_to_dict(state: SealAIState) -> Dict[str, Any]:
    working_profile = getattr(state, "working_profile", None)
    if working_profile is None:
        return {}
    as_dict = getattr(working_profile, "as_dict", None)
    if callable(as_dict):
        dumped = as_dict()
        if isinstance(dumped, dict):
            return dict(dumped)
    engineering_profile = _working_profile_get(state, "engineering_profile")
    if engineering_profile is not None:
        as_dict = getattr(engineering_profile, "as_dict", None)
        if callable(as_dict):
            dumped = as_dict()
            if isinstance(dumped, dict):
                return dict(dumped)
        dumped = _as_dict(engineering_profile)
        if dumped:
            return dumped
    return {}


def _working_profile_get(state: SealAIState, field: str, default: Any = None) -> Any:
    working_profile = getattr(state, "working_profile", None)
    if working_profile is None:
        return default
    if isinstance(working_profile, dict):
        return working_profile.get(field, default)
    return getattr(working_profile, field, default)


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
    material_choice = _working_profile_get(state, "material_choice", {}) or {}
    for value in (
        resolved.get("seal_material"),
        resolved.get("selected_seal_material"),
        material_choice.get("material") if isinstance(material_choice, dict) else None,
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

    for idx, src in enumerate(list(state.system.sources or [])):
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

    reasoning = _as_dict(getattr(state, "reasoning", None))
    panel_material = _as_dict(_as_dict(reasoning.get("working_memory")).get("panel_material"))
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
    _collect_number_tokens(_working_profile_get(state, "extracted_params"), tokens)
    _collect_number_tokens(_working_profile_get(state, "engineering_profile"), tokens)
    _collect_number_tokens(_working_profile_get(state, "engineering_profile"), tokens)
    _collect_number_tokens(_working_profile_get(state, "live_calc_tile"), tokens)
    _collect_number_tokens(_working_profile_get(state, "calculation_result"), tokens)
    _collect_number_tokens(_working_profile_get(state, "calc_results"), tokens)
    _collect_number_tokens(resolved_parameters, tokens)
    return sorted(tokens)


def _extract_temperature_candidates_c(state: SealAIState) -> List[float]:
    values: List[float] = []
    params = _working_profile_get(state, "engineering_profile")
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
            raw = params.get(field) if isinstance(params, dict) else getattr(params, field, None)
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
    tenant_scope = getattr(state.system, "tenant_id", None) or getattr(state.conversation, "user_id", None)

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
    calc_results = _working_profile_get(state, "calc_results")
    if calc_results is not None:
        return _as_dict(calc_results)
    calculation_result = _working_profile_get(state, "calculation_result")
    if isinstance(calculation_result, dict):
        return dict(calculation_result)
    return {}


def _has_technical_parameters(state: SealAIState) -> bool:
    """Check whether user-provided technical parameters exist.

    Args:
        state: Current graph state.

    Returns:
        ``True`` when technical parameters are present, otherwise ``False``.
    """
    parameters = _working_profile_get(state, "engineering_profile")
    if parameters is not None:
        as_dict = getattr(parameters, "as_dict", None)
        if callable(as_dict) and bool(as_dict()):
            return True
        if isinstance(parameters, dict) and bool(parameters):
            return True
    extracted = _working_profile_get(state, "extracted_params")
    if isinstance(extracted, dict) and bool(extracted):
        return True
    working_profile = _working_profile_get(state, "engineering_profile")
    if working_profile is not None:
        as_dict = getattr(working_profile, "as_dict", None)
        if callable(as_dict):
            return bool(as_dict())
        if isinstance(working_profile, dict) and bool(working_profile):
            return True
        profile_dump = _as_dict(working_profile)
        if bool(profile_dump):
            return True
    return False


def _extract_retrieval_chunks_for_authority(state: SealAIState) -> List[Dict[str, Any]]:
    chunks: List[Dict[str, Any]] = []
    reasoning = _as_dict(getattr(state, "reasoning", None))
    panel_material = _as_dict(_as_dict(reasoning.get("working_memory")).get("panel_material"))
    technical_docs = panel_material.get("technical_docs")
    if isinstance(technical_docs, list):
        for item in technical_docs:
            if isinstance(item, dict):
                chunks.append(dict(item))

    retrieval_meta = _as_dict(getattr(state.reasoning, "retrieval_meta", {}) or {})
    for key in ("hits", "documents", "chunks"):
        maybe_hits = retrieval_meta.get(key)
        if not isinstance(maybe_hits, list):
            continue
        for item in maybe_hits:
            if isinstance(item, dict):
                chunks.append(dict(item))

    for source in list(state.system.sources or []):
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
    intent_goal = str(getattr(getattr(state.conversation, "intent", None), "goal", "") or "").strip().lower()
    if intent_goal == "smalltalk":
        return True

    flags = _as_dict(getattr(state.reasoning, "flags", {}) or {})
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
    kb_result = _as_dict(getattr(state.reasoning, "kb_factcard_result", {}) or {})
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
    params = _working_profile_get(state, "engineering_profile")
    runout_value = None
    hardness_value = None
    if params is not None:
        if isinstance(params, dict):
            runout_value = params.get("shaft_runout") or params.get("runout") or params.get("dynamic_runout")
            hardness_value = params.get("shaft_hardness") or params.get("hardness")
        else:
            runout_value = (
                getattr(params, "shaft_runout", None)
                or getattr(params, "runout", None)
                or getattr(params, "dynamic_runout", None)
            )
            hardness_value = getattr(params, "shaft_hardness", None) or getattr(params, "hardness", None)
    extracted = _working_profile_get(state, "extracted_params")
    if isinstance(extracted, dict):
        if runout_value is None:
            runout_value = extracted.get("runout_mm") or extracted.get("runout") or extracted.get("shaft_runout")
        if hardness_value is None:
            hardness_value = extracted.get("hrc_value") or extracted.get("hrc") or extracted.get("shaft_hardness")
    missing_runout = runout_value is None or str(runout_value).strip() == ""
    missing_hardness = hardness_value is None or str(hardness_value).strip() == ""
    return missing_runout, missing_hardness


from app.langgraph_v2.state.governance_types import IdentityClass


def _filter_identity_guarded_extracted_params(state: SealAIState, extracted: Dict[str, Any]) -> Dict[str, Any]:
    identity_map = _as_dict(getattr(state.reasoning, "extracted_parameter_identity", {}) or {})
    filtered: Dict[str, Any] = {}
    for key, value in dict(extracted or {}).items():
        if key not in _IDENTITY_GUARDED_FIELDS:
            filtered[key] = value
            continue
        meta = _as_dict(identity_map.get(key) or {})
        identity_class = str(meta.get("identity_class") or "identity_unresolved")
        if IdentityClass.normalize(identity_class) == IdentityClass.CONFIRMED:
            filtered[key] = value
    return filtered


def _build_resolved_parameters(state: SealAIState) -> Dict[str, Any]:
    resolved: Dict[str, Any] = _working_profile_to_dict(state)

    # Identity gate: strip identity-guarded fields from engineering_profile
    # that have a non-confirmed identity classification.  This prevents
    # family_only / probable / unresolved values from being treated as
    # asserted facts in the contract.
    identity_map = _as_dict(getattr(state.reasoning, "extracted_parameter_identity", {}) or {})
    for key in list(resolved.keys()):
        if key not in _IDENTITY_GUARDED_FIELDS:
            continue
        meta = _as_dict(identity_map.get(key) or {})
        identity_class = str(meta.get("identity_class") or "")
        if identity_class and IdentityClass.normalize(identity_class) != IdentityClass.CONFIRMED:
            resolved.pop(key, None)

    extracted = _working_profile_get(state, "extracted_params", {}) or {}
    if isinstance(extracted, dict):
        filtered_extracted = _filter_identity_guarded_extracted_params(state, extracted)
        for key, value in filtered_extracted.items():
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


def _excluded_by_upstream_gate(state: SealAIState, material: str) -> str | None:
    """Derive gate-exclusion reason from upstream deterministic guard results already in State.

    Reads ``reasoning.flags.combinatorial_chemistry_blocker_rule_ids`` — no new lookup.
    Coverage: the 4 BLOCKER rules of combinatorial_chemistry_guard (FKM+amine,
    NBR+aromatics, FKM+AED, pressure+extrusion-gap). Rating-C cases beyond those
    rules are intentionally NOT checked here; they are handled by node_verify_claims.

    Material matching: CHEM_ rule IDs embed the material name (e.g. CHEM_FKM_AMINE_BLOCKER).
    MECH_ rule IDs are geometry constraints that exclude all materials equally.
    """
    flags = _as_dict(getattr(state.reasoning, "flags", {}) or {})
    if not flags.get("combinatorial_chemistry_has_blocker"):
        return None
    blocker_rule_ids: list = list(flags.get("combinatorial_chemistry_blocker_rule_ids") or [])
    if not blocker_rule_ids:
        return None
    material_upper = str(material or "").upper()
    for rule_id in blocker_rule_ids:
        rule_str = str(rule_id or "").upper()
        if rule_str.startswith("MECH_"):
            # Geometry/mechanical blockers apply regardless of material
            return f"gate:{rule_id}"
        if rule_str.startswith("CHEM_") and material_upper in rule_str:
            return f"gate:{rule_id}"
    return None


def _extract_grounded_facts_for_material(state: SealAIState, material: str) -> List[GroundedFact]:
    """Extract technical facts for a specific material from authoritative retrieval chunks.

    Patch C1a/C2:
    - Deduplication of identical values.
    - Divergence detection for different values of the same fact.
    - Source ranking based on retrieval score.
    - Strict material reference matching.
    """
    chunks = dedupe_retrieval_chunks(_extract_retrieval_chunks_for_authority(state))
    material_clean = _normalize_material_token(material)
    if not material_clean:
        return []

    # Intermediate storage: (name, unit) -> List[GroundedFact]
    grouped_raw: Dict[Tuple[str, Optional[str]], List[GroundedFact]] = {}

    for chunk in chunks:
        metadata = _as_dict(chunk.get("metadata"))
        score = float(chunk.get("retrieval_score") or 0.0)
        chunk_material = _normalize_material_token(
            metadata.get("material_code") or metadata.get("entity") or ""
        )
        
        is_material_match = (
            material_clean in chunk_material 
            or material_clean in _normalize_material_token(chunk.get("text"))
        )
        if not is_material_match:
            continue

        extracted_in_chunk: List[GroundedFact] = []

        # Rule 1: Temp Range
        temp_range = metadata.get("temp_range")
        if isinstance(temp_range, dict):
            min_c, max_c = temp_range.get("min_c"), temp_range.get("max_c")
            if min_c is not None and max_c is not None:
                extracted_in_chunk.append(GroundedFact(
                    name="Temperature Range", value=f"{min_c} to {max_c}", unit="°C",
                    source=str(metadata.get("document_id") or chunk.get("source") or "unknown"),
                    source_rank=score, grounding_basis="metadata",
                ))

        # Rule 2: Shore Hardness
        shore = metadata.get("shore_hardness")
        if shore:
            extracted_in_chunk.append(GroundedFact(
                name="Shore Hardness", value=str(shore), unit="A",
                source=str(metadata.get("document_id") or chunk.get("source") or "unknown"),
                source_rank=score, grounding_basis="metadata",
            ))

        for fact in extracted_in_chunk:
            key = (fact.name, fact.unit)
            if key not in grouped_raw:
                grouped_raw[key] = []
            grouped_raw[key].append(fact)

    final_facts: List[GroundedFact] = []

    for key, raw_list in grouped_raw.items():
        if not raw_list:
            continue
        # Sort by rank descending
        sorted_raw = sorted(raw_list, key=lambda x: x.source_rank, reverse=True)
        
        primary = sorted_raw[0]
        variants: List[FactVariant] = []
        seen_values = {primary.value}

        for other in sorted_raw[1:]:
            if other.value not in seen_values:
                variants.append(FactVariant(
                    value=other.value,
                    source=other.source,
                    source_rank=other.source_rank,
                ))
                seen_values.add(other.value)
        
        if variants:
            primary.is_divergent = True
            primary.variants = variants
        
        final_facts.append(primary)

    return sorted(final_facts, key=lambda x: x.source_rank, reverse=True)


def _build_candidate_semantics(state: SealAIState) -> List[Dict[str, Any]]:
    semantics: List[Dict[str, Any]] = []
    identity_map = _as_dict(getattr(state.reasoning, "extracted_parameter_identity", {}) or {})

    material_choice = _working_profile_get(state, "material_choice", {}) or {}
    if isinstance(material_choice, dict):
        annotated_material_choice = annotate_material_choice(material_choice, identity_map=identity_map)
        material = str(annotated_material_choice.get("material") or "").strip()
        if material:
            # Patch C1: Extract grounded facts from RAG
            grounded_facts = _extract_grounded_facts_for_material(state, material)
            
            semantics.append(
                CandidateItem(
                    kind="material",
                    value=material,
                    rationale=str(annotated_material_choice.get("details") or ""),
                    confidence=0.6,
                    specificity=str(annotated_material_choice.get("specificity") or SpecificityLevel.FAMILY_ONLY.value),
                    source_kind=str(annotated_material_choice.get("source_kind") or "unknown"),
                    governed=bool(annotated_material_choice.get("governed")),
                    excluded_by_gate=_excluded_by_upstream_gate(state, material),
                    grounded_facts=grounded_facts,
                ).model_dump(exclude_none=False)
            )

    return semantics


def _extract_normative_references(
    state: SealAIState,
    *,
    selected_fact_ids: List[str],
) -> List[str]:
    selected = {str(item).strip() for item in selected_fact_ids if str(item).strip()}
    references: List[str] = []
    for chunk in _extract_retrieval_chunks_for_authority(state):
        chunk_dict = _as_dict(chunk)
        metadata = _as_dict(chunk_dict.get("metadata"))
        document_id = str(metadata.get("document_id") or chunk_dict.get("document_id") or "").strip()
        chunk_id = str(metadata.get("chunk_id") or chunk_dict.get("chunk_id") or "").strip()
        compound_id = f"{document_id}:{chunk_id}" if document_id and chunk_id else ""
        if selected and compound_id and compound_id not in selected:
            continue
        text_candidates = (
            document_id,
            str(chunk_dict.get("source") or "").strip(),
            str(chunk_dict.get("text") or chunk_dict.get("snippet") or "").strip(),
        )
        for text in text_candidates:
            if not text:
                continue
            for match in _NORMATIVE_REFERENCE_PATTERN.findall(text):
                reference = " ".join(str(match).strip().split())
                if reference:
                    references.append(reference.upper())
    return list(dict.fromkeys(references))


def _build_material_family_candidates(candidate_clusters: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    for cluster_name in ("plausibly_viable", "viable_only_with_manufacturer_validation"):
        for item in list(candidate_clusters.get(cluster_name) or []):
            candidate = _as_dict(item)
            if str(candidate.get("kind") or "").strip() != "material":
                continue
            specificity = str(candidate.get("specificity") or "").strip()
            value = str(candidate.get("value") or "").strip()
            if not value or specificity not in {
                SpecificityLevel.FAMILY_ONLY.value,
                SpecificityLevel.PRODUCT_FAMILY_REQUIRED.value,
                SpecificityLevel.SUBFAMILY.value,
            }:
                continue
            candidates.append(
                {
                    "material_family": value,
                    "specificity": specificity,
                    "source_kind": str(candidate.get("source_kind") or "").strip(),
                    "governed": bool(candidate.get("governed")),
                }
            )
    deduped: List[Dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in candidates:
        key = (str(item.get("material_family") or ""), str(item.get("specificity") or ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _build_open_points_visible(
    requirement_spec: RequirementSpec,
    governance_metadata: GovernanceMetadata,
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for value in list(requirement_spec.missing_critical_parameters or []):
        text = str(value).strip()
        if text:
            items.append({"kind": "missing_critical_parameter", "value": text, "source": "requirement_spec"})
    for value in list(requirement_spec.unknowns_release_blocking or []):
        text = str(value).strip()
        if text:
            items.append({"kind": "release_blocker", "value": text, "source": "governance_metadata"})
    for value in list(governance_metadata.unknowns_manufacturer_validation or []):
        text = str(value).strip()
        if text:
            items.append({"kind": "manufacturer_validation", "value": text, "source": "governance_metadata"})
    deduped: List[Dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        key = (str(item.get("kind") or ""), str(item.get("value") or ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _build_sealing_requirement_spec(
    state: SealAIState,
    *,
    requirement_spec: RequirementSpec,
    governance_metadata: GovernanceMetadata,
    candidate_clusters: Dict[str, List[Dict[str, Any]]],
    selected_fact_ids: List[str],
) -> SealingRequirementSpec:
    operating_envelope = dict(requirement_spec.operating_conditions or {})
    dimensional_requirements = {
        key: value
        for key, value in operating_envelope.items()
        if key in {"shaft_diameter"}
    }
    construction_requirements = {
        key: value
        for key, value in operating_envelope.items()
        if key in {"dynamic_type", "shaft_runout", "shaft_hardness"}
    }
    
    # Blueprint v1.2: material_specificity_required reflects what is needed for this contract.
    # We derive the best AVAILABLE specificity from all candidates to see what we CAN offer.
    best_available_spec = SpecificityLevel.FAMILY_ONLY.value
    all_candidates = []
    for cluster in candidate_clusters.values():
        all_candidates.extend(cluster)
    
    for item in all_candidates:
        spec_val = str(_as_dict(item).get("specificity") or "")
        if get_specificity_rank(spec_val) > get_specificity_rank(best_available_spec):
            best_available_spec = spec_val

    # For SealingRequirementSpec, we report the best available level to maintain 
    # compatibility with existing verification logic that expects this field 
    # to reflect the output quality.
    required_spec = best_available_spec

    return SealingRequirementSpec(
        spec_id=_artifact_id("srs", state),
        operating_envelope=operating_envelope,
        dimensional_requirements=dimensional_requirements,
        normative_references=_extract_normative_references(state, selected_fact_ids=selected_fact_ids),
        material_family_candidates=_build_material_family_candidates(candidate_clusters),
        material_specificity_required=required_spec,
        construction_requirements=construction_requirements,
        manufacturer_validation_scope=list(governance_metadata.unknowns_manufacturer_validation),
        assumption_boundaries=list(governance_metadata.assumptions_active),
        invalid_if=list(requirement_spec.exclusion_criteria),
        open_points_visible=_build_open_points_visible(requirement_spec, governance_metadata),
        operating_conditions=operating_envelope,
        missing_critical_parameters=list(requirement_spec.missing_critical_parameters),
        exclusion_criteria=list(requirement_spec.exclusion_criteria),
        unknowns_release_blocking=list(requirement_spec.unknowns_release_blocking),
    )


def _build_governance_metadata(
    state: SealAIState,
    *,
    candidate_semantics: List[Dict[str, Any]],
    required_disclaimers: List[str],
    respond_with_uncertainty: bool,
    selected_fact_ids: List[str],
    calc_results: Dict[str, Any],
    resolved_parameters: Dict[str, Any],
) -> GovernanceMetadata:
    scope_of_validity: List[str] = []
    assumptions_active: List[str] = []
    unknowns_release_blocking: List[str] = []
    unknowns_manufacturer_validation: List[str] = []
    gate_failures: List[str] = []
    governance_notes: List[str] = []

    if selected_fact_ids or calc_results or resolved_parameters:
        scope_of_validity.append("Gilt nur fuer den aktuellen Assertion-Stand sowie die in diesem Lauf gebundenen Parameter, Berechnungen und Evidenzen.")
    if calc_results:
        scope_of_validity.append("Deterministische Berechnungsergebnisse gelten nur fuer den aktuell erfassten Betriebspunkt.")
    if any(str(item.get("specificity") or "") != SpecificityLevel.COMPOUND_REQUIRED.value for item in candidate_semantics):
        scope_of_validity.append("Kandidaten mit Specificity unter compound_required sind keine compoundscharfe Freigabe.")

    if respond_with_uncertainty:
        assumptions_active.append("Antwort basiert auf begrenzter Evidenz- oder Berechnungsabdeckung.")
    if bool((state.reasoning.flags or {}).get("rag_low_quality_results")):
        assumptions_active.append("Retrieval-Qualitaet fuer Material-/Dokumentkontext war niedrig.")
    
    # Missing parameters from reasoning (e.g. from discovery or qgate)
    missing_params = [str(item).strip() for item in list(state.reasoning.missing_params or []) if str(item).strip()]
    if missing_params:
        assumptions_active.append(f"Offene Parameterluecken: {', '.join(missing_params)}.")
        # Blueprint v1.2: treat missing params as release-blocking unknowns
        unknowns_release_blocking.extend(missing_params)

    missing_critical = resolved_parameters.get("missing_critical_parameters")
    if isinstance(missing_critical, list):
        unknowns_release_blocking.extend(str(item).strip() for item in missing_critical if str(item).strip())

    qgate_result = _as_dict(getattr(state.reasoning, "qgate_result", {}) or {})
    for check in list(qgate_result.get("checks") or []):
        check_dict = _as_dict(check)
        if not check_dict or check_dict.get("passed") is True:
            continue
        severity = str(check_dict.get("severity") or "").upper()
        message = str(check_dict.get("message") or check_dict.get("name") or check_dict.get("check_id") or "").strip()
        if not message:
            continue
        gate_failures.append(f"{severity}: {message}")
        if severity == "CRITICAL":
            unknowns_release_blocking.append(message)

    for candidate in candidate_semantics:
        specificity = str(candidate.get("specificity") or "").strip()
        value = str(candidate.get("value") or "").strip()
        if specificity and specificity != SpecificityLevel.COMPOUND_REQUIRED.value:
            label = value or "Kandidat"
            unknowns_manufacturer_validation.append(
                f"{label} erfordert Hersteller-/Compound-Validierung (specificity: {specificity})."
            )

    if bool(getattr(state.system, "requires_human_review", False)):
        governance_notes.append("Human review required before external release.")
    governance_notes.extend(str(item).strip() for item in required_disclaimers if str(item).strip())

    return GovernanceMetadata(
        scope_of_validity=list(dict.fromkeys(scope_of_validity)),
        assumptions_active=list(dict.fromkeys(assumptions_active)),
        unknowns_release_blocking=list(dict.fromkeys(unknowns_release_blocking)),
        unknowns_manufacturer_validation=list(dict.fromkeys(unknowns_manufacturer_validation)),
        gate_failures=list(dict.fromkeys(gate_failures)),
        governance_notes=list(dict.fromkeys(governance_notes)),
    )


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
    user_context = _as_dict(getattr(state.conversation, "user_context", {}))
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
        wm_dict = _as_dict(getattr(state.reasoning, "working_memory", None))
        panel_material = _as_dict(wm_dict.get("panel_material"))
        technical_docs = list(panel_material.get("technical_docs") or [])
        technical_docs.extend(forced_factcards)
        panel_material["technical_docs"] = _dedupe_technical_docs(technical_docs)
        wm_dict["panel_material"] = panel_material
        augmented_wm = WorkingMemory.model_validate(wm_dict)
        context_state = state.model_copy(update={
                                                    "reasoning": {
                                                        "working_memory": augmented_wm,
                                                    },
                                                })

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
        if bool(getattr(state.system, "requires_human_review", False)):
            required_disclaimers.append("Human review required before final recommendation.")
        if bool((state.reasoning.flags or {}).get("is_safety_critical")):
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

    candidate_semantics = _build_candidate_semantics(state)
    # Blueprint v1.2: Default required specificity for AnswerContract is compound_required.
    # This can be made dynamic in Patch 2C if we support purely family-level recommendations.
    required_spec = SpecificityLevel.COMPOUND_REQUIRED.value
    candidate_clusters = build_candidate_clusters(candidate_semantics, required_specificity=required_spec)
    governance_metadata = _build_governance_metadata(
        state,
        candidate_semantics=candidate_semantics,
        required_disclaimers=required_disclaimers,
        respond_with_uncertainty=respond_with_uncertainty,
        selected_fact_ids=selected_fact_ids,
        calc_results=calc_results,
        resolved_parameters=resolved_parameters,
    )

    requirement_spec = _build_requirement_spec(resolved_parameters, governance_metadata)
    sealing_requirement_spec = _build_sealing_requirement_spec(
        state,
        requirement_spec=requirement_spec,
        governance_metadata=governance_metadata,
        candidate_clusters=candidate_clusters,
        selected_fact_ids=selected_fact_ids,
    )

    # Blueprint v1.2: Ensure rfq_admissibility is normalized and tied to this contract.
    # Pass cycle context explicitly to ensure binding.
    cycle_id = int(getattr(state.reasoning, "current_assertion_cycle_id", 0) or 0)
    revision = int(getattr(state.reasoning, "asserted_profile_revision", 0) or 0)

    state_dump = state.model_dump(exclude_none=False)
    admissibility_dict = normalize_rfq_admissibility_contract(state_dump)
    
    # Ensure cycle/revision are set in the admissibility contract
    admissibility_dict["derived_from_assertion_cycle_id"] = cycle_id if cycle_id > 0 else None
    admissibility_dict["derived_from_assertion_revision"] = revision if revision > 0 else None

    # Override/re-check blockers from current contract's governance metadata
    all_blockers = list(dict.fromkeys(
        admissibility_dict.get("blockers", []) + governance_metadata.unknowns_release_blocking
    ))
    if all_blockers:
        admissibility_dict["status"] = "inadmissible"
        admissibility_dict["release_status"] = "inadmissible"
        admissibility_dict["blockers"] = all_blockers
        admissibility_dict["governed_ready"] = False

    from app.langgraph_v2.state.sealai_state import RFQAdmissibilityContract
    rfq_admissibility = RFQAdmissibilityContract.model_validate(admissibility_dict)

    contract = AnswerContract(
        contract_id=_artifact_id("contract", state),
        snapshot_parent_revision=revision,
        release_status=rfq_admissibility.release_status,
        rfq_admissibility=rfq_admissibility,
        resolved_parameters=resolved_parameters,
        requirement_spec=requirement_spec,
        calc_results=calc_results,
        selected_fact_ids=selected_fact_ids,
        candidate_semantics=candidate_semantics,
        candidate_clusters=candidate_clusters,
        governance_metadata=governance_metadata,
        required_disclaimers=required_disclaimers,
        respond_with_uncertainty=respond_with_uncertainty,
        claims=list(state.reasoning.claims or []),
    )
    contract_hash = hashlib.sha256(contract.model_dump_json().encode()).hexdigest()

    flags = deepcopy(state.reasoning.flags or {})
    flags["answer_subgraph_allowed_number_tokens"] = _extract_allowed_number_tokens_from_state(
        state,
        resolved_parameters,
    )
    flags["answer_contract_hash"] = contract_hash
    flags["answer_subgraph_patch_attempts"] = 0

    final_prompt_metadata = dict(state.system.final_prompt_metadata or {})
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
        "system": {
            "answer_contract": contract,
            "final_prompt": final_context,
            "final_prompt_metadata": final_prompt_metadata,
            "sealing_requirement_spec": sealing_requirement_spec,
        },
        "reasoning": {
            "flags": flags,
            "last_node": "node_prepare_contract",
            "working_memory": {
                "material_requirements": requirement_spec,
            },
        },
    }
    if augmented_wm is not None:
        # Merge augmented working memory if it was built (e.g. during material panel enrichment)
        patch["reasoning"]["working_memory"].update(augmented_wm.model_dump(exclude_none=True))
    return stamp_patch_with_assertion_binding(state, patch)


__all__ = ["node_prepare_contract"]
