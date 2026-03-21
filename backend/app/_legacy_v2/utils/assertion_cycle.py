from __future__ import annotations

import time
from copy import deepcopy
from typing import Any, Callable, Dict, Iterable, Tuple

from app._legacy_v2.state.sealai_state import CalcResults, LiveCalcTile
from app._legacy_v2.utils.rfq_admissibility import invalidate_rfq_admissibility_contract


def _as_dict(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(exclude_none=False)
        if isinstance(dumped, dict):
            return dumped
    return {}


def _pillar_get(state: Any, pillar: str, key: str, default: Any = None) -> Any:
    if isinstance(state, dict):
        pillar_value = state.get(pillar)
        if isinstance(pillar_value, dict) and key in pillar_value:
            return pillar_value.get(key)
        return state.get(key, default)
    pillar_value = getattr(state, pillar, None)
    if pillar_value is not None and hasattr(pillar_value, key):
        return getattr(pillar_value, key)
    return getattr(state, key, default)


def get_assertion_binding(state: Any) -> Tuple[int, int]:
    cycle_id = int(_pillar_get(state, "reasoning", "current_assertion_cycle_id", 0) or 0)
    revision = int(_pillar_get(state, "reasoning", "asserted_profile_revision", 0) or 0)
    return cycle_id, revision


def is_artifact_stale(state: SealAIState | Dict[str, Any]) -> bool:
    """Return True if any pillar indicates that derived artifacts are stale."""
    if isinstance(state, dict):
        wp_stale = bool(state.get("working_profile", {}).get("derived_artifacts_stale"))
        re_stale = bool(state.get("reasoning", {}).get("derived_artifacts_stale"))
        sys_stale = bool(state.get("system", {}).get("derived_artifacts_stale"))
    else:
        wp_stale = bool(getattr(state.working_profile, "derived_artifacts_stale", False))
        re_stale = bool(getattr(state.reasoning, "derived_artifacts_stale", False))
        sys_stale = bool(getattr(state.system, "derived_artifacts_stale", False))
    
    return wp_stale or re_stale or sys_stale


def build_assertion_cycle_update(
    state: Any,
    *,
    applied_fields: Iterable[str],
    now: Callable[[], float] | None = None,
) -> Dict[str, Any]:
    fields = sorted(str(field).strip() for field in applied_fields if str(field).strip())
    if not fields:
        return {}

    current_cycle_id, current_revision = get_assertion_binding(state)
    next_cycle_id = current_cycle_id + 1
    next_revision = current_revision + 1
    changed_at = float((now or time.time)())
    reason = f"assertion_revision_changed:{','.join(fields)}"

    # Soft Obsolescence: Retain the current contract but mark it as obsolete
    current_contract = _pillar_get(state, "system", "answer_contract")
    obsolete_contract = None
    if current_contract is not None:
        contract_dict = _as_dict(current_contract)
        if contract_dict:
            session_id = _pillar_get(state, "conversation", "session_id", "default")
            contract_dict["obsolete"] = True
            contract_dict["obsolete_reason"] = reason
            contract_dict["superseded_by_cycle"] = f"cycle_{session_id}_{next_cycle_id}"
            obsolete_contract = contract_dict

    return {
        "working_profile": {
            "calc_results": CalcResults().model_dump(exclude_none=False),
            "calculation_result": None,
            "live_calc_tile": LiveCalcTile().model_dump(exclude_none=False),
            "calc_results_ok": False,
            "analysis_complete": False,
            "derived_from_assertion_cycle_id": next_cycle_id,
            "derived_from_assertion_revision": next_revision,
            "derived_artifacts_stale": True,
            "derived_artifacts_stale_reason": reason,
        },
        "reasoning": {
            "current_assertion_cycle_id": next_cycle_id,
            "state_revision": next_revision,
            "asserted_profile_revision": next_revision,
            "snapshot_parent_revision": current_revision,
            "last_assertion_changed_at": changed_at,
            "derived_artifacts_stale": True,
            "derived_artifacts_stale_reason": reason,
        },
        "system": {
            "rfq_admissibility": invalidate_rfq_admissibility_contract(
                cycle_id=next_cycle_id,
                revision=next_revision,
                reason=reason,
            ),
            "sealing_requirement_spec": None,
            "rfq_draft": None,
            "rfq_confirmed": False,
            "rfq_pdf_base64": None,
            "rfq_pdf_url": None,
            "rfq_html_report": None,
            "rfq_pdf_text": None,
            "preview_text": None,
            "governed_output_text": None,
            "governed_output_status": None,
            "governed_output_ready": False,
            "governance_metadata": {},
            "final_text": None,
            "final_answer": None,
            "final_prompt": None,
            "answer_contract": obsolete_contract,
            "draft_text": None,
            "draft_base_hash": None,
            "verification_report": None,
            "verification_error": None,
            "derived_from_assertion_cycle_id": next_cycle_id,
            "derived_from_assertion_revision": next_revision,
            "derived_artifacts_stale": True,
            "derived_artifacts_stale_reason": reason,
        },
    }


def stamp_patch_with_assertion_binding(state: Any, patch: Dict[str, Any]) -> Dict[str, Any]:
    stamped = deepcopy(patch)
    cycle_id, revision = get_assertion_binding(state)
    if cycle_id <= 0 or revision <= 0:
        return stamped

    # Detect if this patch contains fresh analysis or system results
    system_patch = stamped.get("system")
    system_candidate_keys = {
        "answer_contract",
        "verification_report",
        "governed_output_text",
        "final_text",
        "final_answer",
        "draft_text",
        "draft_base_hash",
        "final_prompt",
        "sealing_requirement_spec",
        "rfq_draft",
    }
    has_system_derivation = any(key in stamped for key in ("final_text", "final_answer", "answer_contract"))
    if isinstance(system_patch, dict) and any(key in system_patch for key in system_candidate_keys):
        has_system_derivation = True

    working_profile_patch = stamped.get("working_profile")
    has_analysis_derivation = isinstance(working_profile_patch, dict) and any(
        key in working_profile_patch
        for key in ("calc_results", "live_calc_tile", "calculation_result", "material_choice", "profile_choice")
    )

    # If we have ANY fresh derivation, we clear staleness across the board
    if has_system_derivation or has_analysis_derivation:
        # Reasoning Pillar
        reasoning_patch = stamped.setdefault("reasoning", {})
        reasoning_patch["derived_artifacts_stale"] = False
        reasoning_patch["derived_artifacts_stale_reason"] = None

        # System Pillar
        if not isinstance(system_patch, dict):
            system_patch = stamped.setdefault("system", {})
        
        # Pull up top-level keys into system pillar if needed
        for key in ("final_text", "final_answer", "answer_contract"):
            if key in stamped and key not in system_patch:
                system_patch[key] = stamped[key]
        
        system_patch.setdefault("derived_from_assertion_cycle_id", cycle_id)
        system_patch.setdefault("derived_from_assertion_revision", revision)
        system_patch["derived_artifacts_stale"] = False
        system_patch["derived_artifacts_stale_reason"] = None

        # Working Profile Pillar
        if not isinstance(working_profile_patch, dict):
            working_profile_patch = stamped.setdefault("working_profile", {})
        
        working_profile_patch.setdefault("derived_from_assertion_cycle_id", cycle_id)
        working_profile_patch.setdefault("derived_from_assertion_revision", revision)
        working_profile_patch["derived_artifacts_stale"] = False
        working_profile_patch["derived_artifacts_stale_reason"] = None

    return stamped


__all__ = [
    "build_assertion_cycle_update",
    "get_assertion_binding",
    "is_artifact_stale",
    "stamp_patch_with_assertion_binding",
]
