from __future__ import annotations

import time
from copy import deepcopy
from typing import Any, Callable, Dict, Iterable, Tuple

from app.langgraph_v2.state.sealai_state import CalcResults, LiveCalcTile
from app.langgraph_v2.utils.rfq_admissibility import invalidate_rfq_admissibility_contract


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
            "asserted_profile_revision": next_revision,
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
            "answer_contract": None,
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

    working_profile_patch = stamped.get("working_profile")
    if isinstance(working_profile_patch, dict) and any(
        key in working_profile_patch
        for key in ("calc_results", "live_calc_tile", "calculation_result")
    ):
        working_profile_patch.setdefault("derived_from_assertion_cycle_id", cycle_id)
        working_profile_patch.setdefault("derived_from_assertion_revision", revision)
        working_profile_patch["derived_artifacts_stale"] = False
        working_profile_patch["derived_artifacts_stale_reason"] = None

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
    }
    has_system_derivation = any(key in stamped for key in ("final_text", "final_answer", "answer_contract"))
    if isinstance(system_patch, dict) and any(key in system_patch for key in system_candidate_keys):
        has_system_derivation = True
    if has_system_derivation:
        if not isinstance(system_patch, dict):
            system_patch = {}
            stamped["system"] = system_patch
        for key in ("final_text", "final_answer", "answer_contract"):
            if key in stamped and key not in system_patch:
                system_patch[key] = stamped[key]
        system_patch.setdefault("derived_from_assertion_cycle_id", cycle_id)
        system_patch.setdefault("derived_from_assertion_revision", revision)
        system_patch["derived_artifacts_stale"] = False
        system_patch["derived_artifacts_stale_reason"] = None

    reasoning_patch = stamped.get("reasoning")
    if has_system_derivation or (
        isinstance(working_profile_patch, dict)
        and any(key in working_profile_patch for key in ("calc_results", "live_calc_tile", "calculation_result"))
    ):
        if not isinstance(reasoning_patch, dict):
            reasoning_patch = {}
            stamped["reasoning"] = reasoning_patch
        reasoning_patch["derived_artifacts_stale"] = False
        reasoning_patch["derived_artifacts_stale_reason"] = None

    return stamped


__all__ = [
    "build_assertion_cycle_update",
    "get_assertion_binding",
    "stamp_patch_with_assertion_binding",
]
