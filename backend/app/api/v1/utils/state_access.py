"""Shared state-access helpers for LangGraph v2 API endpoints.

These utilities are used by both `langgraph_v2.py` and `state.py` to extract
data from the pillar-based SealAIState structure. They are kept here to avoid
duplication and to provide a single source of truth.

Scope: structural pillar access, pillar-value readers, and lightweight
state-payload builders. No LLM or graph orchestration logic.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

from app.langgraph_v2.utils.candidate_semantics import annotate_material_choice
from app.langgraph_v2.utils.rfq_admissibility import normalize_rfq_admissibility_contract


def _state_values_to_dict(values: Any) -> Dict[str, Any]:
    """Coerce any state-like value to a plain dict.

    Handles SealAIState (via model_dump), plain dicts, and anything that
    supports dict() conversion. Returns an empty dict on failure.
    """
    if values is None:
        return {}
    # Defer import to avoid circular dependencies at module load time.
    try:
        from app.langgraph_v2.state import SealAIState
        if isinstance(values, SealAIState):
            return values.model_dump(exclude_none=True)
    except Exception:
        pass
    if isinstance(values, dict):
        return dict(values)
    try:
        return dict(values)
    except Exception:
        return {}


# Alias used in state.py under the name _state_to_dict.
_state_to_dict = _state_values_to_dict


def _pillar_dict(values: Dict[str, Any], pillar: str) -> Dict[str, Any]:
    """Extract a pillar sub-dict from a state values dict.

    If the pillar value is a Pydantic model, it is serialised via model_dump.
    Returns an empty dict if the pillar is absent or not a dict.
    """
    candidate = values.get(pillar)
    if hasattr(candidate, "model_dump"):
        candidate = candidate.model_dump(exclude_none=True)
    if isinstance(candidate, dict):
        return dict(candidate)
    return {}


# ---------------------------------------------------------------------------
# Pillar-value readers — thin wrappers around _pillar_dict with legacy fallback
# ---------------------------------------------------------------------------

def _conversation_value(values: Dict[str, Any], key: str) -> Any:
    """Read from pillar 1 (`conversation`) with backward-compatible fallback."""
    pillar = _pillar_dict(values, "conversation")
    if key in pillar:
        return pillar.get(key)
    return values.get(key)


def _reasoning_value(values: Dict[str, Any], key: str) -> Any:
    """Read from pillar 3 (`reasoning`) with backward-compatible fallback."""
    pillar = _pillar_dict(values, "reasoning")
    if key in pillar:
        return pillar.get(key)
    return values.get(key)


def _system_value(values: Dict[str, Any], key: str) -> Any:
    """Read from pillar 4 (`system`) with backward-compatible fallback."""
    pillar = _pillar_dict(values, "system")
    if key in pillar:
        return pillar.get(key)
    return values.get(key)


def _working_profile_value(values: Dict[str, Any], key: str) -> Any:
    """Read from pillar 2 (`working_profile`) with backward-compatible fallback."""
    pillar = _pillar_dict(values, "working_profile")
    if key in pillar:
        return pillar.get(key)
    return values.get(key)


def _rfq_admissibility_value(values: Dict[str, Any]) -> Dict[str, Any]:
    return normalize_rfq_admissibility_contract(values)


# ---------------------------------------------------------------------------
# State payload builders — extract structured sub-payloads from state values
# ---------------------------------------------------------------------------

def _looks_like_nested_working_profile_payload(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    marker_keys = {
        "engineering_profile",
        "normalized_profile",
        "parameter_profile",
        "extracted_params",
        "live_calc_tile",
        "recommendation",
    }
    return bool(marker_keys & set(value.keys()))


def _engineering_profile_payload(values: Dict[str, Any]) -> Dict[str, Any]:
    """Return the canonical engineering profile stored inside pillar 2.

    `working_profile.engineering_profile` is the long-lived single source of
    truth for technical parameters that both the Fast Brain and the Slow Brain
    can share. The helper also tolerates older state layouts where
    `working_profile` itself was used as the engineering payload.
    """
    pillar = _pillar_dict(values, "working_profile")
    profile = pillar.get("engineering_profile")
    if hasattr(profile, "model_dump"):
        profile = profile.model_dump(exclude_none=True)
    if isinstance(profile, dict):
        return dict(profile)
    legacy = values.get("working_profile")
    if _looks_like_nested_working_profile_payload(legacy):
        return {}
    if hasattr(legacy, "model_dump"):
        legacy = legacy.model_dump(exclude_none=True)
    if isinstance(legacy, dict):
        return dict(legacy)
    return {}


def _system_model_payload(values: Dict[str, Any], key: str) -> Dict[str, Any]:
    payload = _system_value(values, key)
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(exclude_none=True)
    if isinstance(payload, dict):
        return dict(payload)
    return {}


def _candidate_semantics_payload(values: Dict[str, Any]) -> List[Dict[str, Any]]:
    system_candidate_semantics = _system_value(values, "candidate_semantics")
    if isinstance(system_candidate_semantics, list):
        return [dict(item) for item in system_candidate_semantics if isinstance(item, dict)]

    contract = _system_value(values, "answer_contract")
    if hasattr(contract, "model_dump"):
        contract = contract.model_dump(exclude_none=True)
    if isinstance(contract, dict):
        candidate_semantics = contract.get("candidate_semantics")
        if isinstance(candidate_semantics, list):
            return [dict(item) for item in candidate_semantics if isinstance(item, dict)]

    pillar = _pillar_dict(values, "working_profile")
    material_choice = pillar.get("material_choice")
    if hasattr(material_choice, "model_dump"):
        material_choice = material_choice.model_dump(exclude_none=True)
    if isinstance(material_choice, dict):
        reasoning = _pillar_dict(values, "reasoning")
        identity_map = reasoning.get("extracted_parameter_identity")
        if hasattr(identity_map, "model_dump"):
            identity_map = identity_map.model_dump(exclude_none=True)
        annotated = annotate_material_choice(material_choice, identity_map=identity_map if isinstance(identity_map, dict) else {})
        material = str(annotated.get("material") or "").strip()
        if material:
            return [
                {
                    "kind": "material",
                    "value": material,
                    "rationale": str(annotated.get("details") or ""),
                    "confidence": 0.6,
                    "specificity": str(annotated.get("specificity") or "unresolved"),
                    "source_kind": str(annotated.get("source_kind") or "unknown"),
                    "governed": bool(annotated.get("governed")),
                }
            ]
    return []


def _governance_metadata_payload(values: Dict[str, Any]) -> Dict[str, Any]:
    governance = _system_value(values, "governance_metadata")
    if hasattr(governance, "model_dump"):
        governance = governance.model_dump(exclude_none=True)
    if isinstance(governance, dict):
        return dict(governance)

    contract = _system_value(values, "answer_contract")
    if hasattr(contract, "model_dump"):
        contract = contract.model_dump(exclude_none=True)
    if isinstance(contract, dict):
        candidate = contract.get("governance_metadata")
        if isinstance(candidate, dict):
            return dict(candidate)
    return {}


# ---------------------------------------------------------------------------
# Message and Text content utilities
# ---------------------------------------------------------------------------

def _flatten_message_content(message: Any) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for chunk in content:
            if isinstance(chunk, str):
                parts.append(chunk)
            elif isinstance(chunk, dict):
                text_value = chunk.get("text") or chunk.get("content")
                nested = _flatten_message_content(text_value)
                if nested:
                    parts.append(nested)
            else:
                nested = _flatten_message_content(chunk)
                if nested:
                    parts.append(nested)
        return "".join(parts)
    if isinstance(content, dict):
        text_value = content.get("text") or content.get("content")
        return _flatten_message_content(text_value)
    if content is None:
        return ""
    if isinstance(content, (int, float)):
        return str(content)
    return ""


def _is_structured_payload_text(text: str) -> bool:
    stripped = (text or "").strip()
    if not stripped or stripped[0] not in {"{", "["}:
        return False
    try:
        parsed = json.loads(stripped)
    except Exception:
        return False
    return isinstance(parsed, (dict, list))


_LEGACY_GOVERNED_NODES = {
    "answer_subgraph_node",
    "final_answer_node",
    "response_node",
    "node_finalize",
    "node_safe_fallback",
    "smalltalk_node",
    "out_of_scope_node",
    "confirm_recommendation_node",
}


def _resolve_governed_output_text(state: Any) -> str:
    values = _state_values_to_dict(state)
    governed = _system_value(values, "governed_output_text")
    if isinstance(governed, str) and governed.strip():
        return governed.strip()

    ready = bool(_system_value(values, "governed_output_ready"))
    last_node = str(_reasoning_value(values, "last_node") or values.get("last_node") or "").strip()
    if ready or last_node in _LEGACY_GOVERNED_NODES:
        legacy = _system_value(values, "final_text")
        if not isinstance(legacy, str):
            legacy = _system_value(values, "final_answer")
        return str(legacy or "").strip()
    return ""


def _latest_ai_text(messages: Any, *, after_last_human: bool = False) -> str:
    if not isinstance(messages, list):
        return ""
    scan_from = 0
    if after_last_human:
        for idx in range(len(messages) - 1, -1, -1):
            msg = messages[idx]
            role = getattr(msg, "type", None) or getattr(msg, "role", None)
            if role is None and isinstance(msg, dict):
                role = msg.get("type") or msg.get("role")
            if role in ("human", "user"):
                scan_from = idx + 1
                break
    for msg in reversed(messages[scan_from:]):
        role = getattr(msg, "type", None) or getattr(msg, "role", None)
        if role is None and isinstance(msg, dict):
            role = msg.get("type") or msg.get("role")
        if role not in ("ai", "assistant"):
            continue
        text = _flatten_message_content(msg).strip()
        if text:
            return text
    return ""


def _extract_final_text_from_patch(data: Any) -> str:
    stack: list[Any] = [data]
    seen: set[int] = set()
    while stack:
        current = stack.pop()
        if current is None:
            continue
        marker = id(current)
        if marker in seen:
            continue
        seen.add(marker)
        # Defer import to avoid circular dependencies
        try:
            from app.langgraph_v2.state import SealAIState
            if isinstance(current, SealAIState):
                # Using a generic extract if possible, but for SealAIState we use the known pillar structure
                text = _resolve_governed_output_text(current)
                if text:
                    return text
                stack.append(current.model_dump(exclude_none=True))
                continue
        except Exception:
            pass

        if isinstance(current, dict):
            value = _system_value(current, "governed_output_text")
            if isinstance(value, str) and value.strip():
                return value.strip()
            value = _system_value(current, "final_text")
            if isinstance(value, str) and value.strip():
                return value.strip()
            value = _system_value(current, "final_answer")
            if isinstance(value, str) and value.strip():
                return value.strip()
            chunk_type = current.get("chunk_type")
            if isinstance(chunk_type, str) and chunk_type.strip().lower() == "final_answer":
                for key in ("text", "content", "message", "delta"):
                    text = _flatten_message_content(current.get(key)).strip()
                    if text:
                        return text
            for key in ("output", "state", "final_state", "values", "result", "chunk", "patch", "update", "delta", "data"):
                nested = current.get(key)
                if nested is not None:
                    stack.append(nested)
            for nested in current.values():
                if isinstance(nested, (dict, list, tuple)):
                    stack.append(nested)
                else:
                    # Check for SealAIState if it's a value
                    try:
                        from app.langgraph_v2.state import SealAIState
                        if isinstance(nested, SealAIState):
                            stack.append(nested)
                    except Exception:
                        pass
            continue
        if isinstance(current, (list, tuple)):
            stack.extend(current)
    return ""


def _resolve_final_text(state: Any) -> str:
    if state is None:
        return ""
    return _resolve_governed_output_text(state)


# ---------------------------------------------------------------------------
# State merging and Live-Calc utilities
# ---------------------------------------------------------------------------

def _is_meaningful_live_calc_tile(tile: Any) -> bool:
    if hasattr(tile, "model_dump"):
        tile = tile.model_dump(exclude_none=True)
    if not isinstance(tile, dict) or not tile:
        return False

    status = tile.get("status")
    if isinstance(status, str) and status in {"ok", "warning", "critical"}:
        return True

    numeric_keys = (
        "v_surface_m_s",
        "pv_value_mpa_m_s",
        "friction_power_watts",
        "compression_ratio_pct",
        "groove_fill_pct",
        "stretch_pct",
        "thermal_expansion_mm",
    )
    for key in numeric_keys:
        if tile.get(key) is not None:
            return True

    warning_flags = (
        "hrc_warning",
        "runout_warning",
        "pv_warning",
        "extrusion_risk",
        "requires_backup_ring",
        "shrinkage_risk",
        "dry_running_risk",
        "geometry_warning",
    )
    if any(bool(tile.get(key)) for key in warning_flags):
        return True

    parameters = tile.get("parameters")
    if isinstance(parameters, dict):
        for value in parameters.values():
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            return True

    return False


def _normalize_live_calc_tile(tile: Any) -> Dict[str, Any] | None:
    if hasattr(tile, "model_dump"):
        tile = tile.model_dump(exclude_none=True)
    if not _is_meaningful_live_calc_tile(tile):
        return None
    if not isinstance(tile, dict):
        return None
    return dict(tile)


def _inject_live_calc_tile(payload: Dict[str, Any], *, live_calc_tile: Dict[str, Any] | None) -> None:
    tile = _normalize_live_calc_tile(live_calc_tile)
    if tile is None:
        return
    data = payload.get("data")
    if not isinstance(data, dict):
        data = {}
        payload["data"] = data
    current_tile = _normalize_live_calc_tile(data.get("live_calc_tile"))
    if current_tile is None:
        data["live_calc_tile"] = dict(tile)
    payload["live_calc_tile"] = data.get("live_calc_tile")


def _merge_state_like(
    current: Any,
    update: Any,
) -> Any:
    """Deep merge two state-like objects (SealAIState or dict)."""
    def _deep_merge(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(base)
        for key, value in patch.items():
            current_value = merged.get(key)
            if isinstance(current_value, dict) and isinstance(value, dict):
                merged[key] = _deep_merge(current_value, value)
            else:
                merged[key] = value
        return merged

    update_dict = _state_values_to_dict(update)
    if not update_dict:
        return current
    if isinstance(update_dict, dict) and "parameters" in update_dict:
        raw_parameters = update_dict.pop("parameters")
        if isinstance(raw_parameters, dict):
            working_profile_patch = update_dict.get("working_profile")
            if not isinstance(working_profile_patch, dict):
                working_profile_patch = {}
            normalized_patch = working_profile_patch.get("normalized_profile")
            if not isinstance(normalized_patch, dict):
                normalized_patch = {}
            normalized_patch.update(dict(raw_parameters))
            extracted_patch = working_profile_patch.get("extracted_params")
            if not isinstance(extracted_patch, dict):
                extracted_patch = {}
            extracted_patch.update(dict(raw_parameters))
            working_profile_patch["normalized_profile"] = normalized_patch
            working_profile_patch["extracted_params"] = extracted_patch
            update_dict["working_profile"] = working_profile_patch

    base = _state_values_to_dict(current)
    merged = _deep_merge(base, update_dict)
    update_tile = _working_profile_value(update_dict, "live_calc_tile")
    if not _is_meaningful_live_calc_tile(update_tile):
        current_tile = _working_profile_value(base, "live_calc_tile")
        if _is_meaningful_live_calc_tile(current_tile):
            merged.setdefault("working_profile", {})
            if isinstance(merged["working_profile"], dict):
                merged["working_profile"]["live_calc_tile"] = current_tile
    return merged
