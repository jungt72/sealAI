"""Deterministic policy checks ("policy-as-code") for ISO/DIN gating."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

from app.langgraph_v2.state import SealAIState

_POLICY_PATH = Path(__file__).resolve().parents[1] / "policy" / "iso_din_policy.json"


@lru_cache(maxsize=1)
def _load_policy() -> Dict[str, Any]:
    if not _POLICY_PATH.exists():
        return {"version": 0, "rules": []}
    with _POLICY_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _normalized_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def _text_contains_any(haystack: str, needles: List[str]) -> bool:
    hay = haystack.lower()
    return any(needle.lower() in hay for needle in needles if needle)


def _param_present(params: Dict[str, Any], key: str) -> bool:
    value = params.get(key)
    if isinstance(value, str):
        return bool(value.strip())
    return value is not None


def evaluate_policy(state: SealAIState) -> Dict[str, Any]:
    policy = _load_policy()
    rules = list(policy.get("rules") or [])

    params = state.parameters.as_dict() if state.parameters else {}
    standard_ref = params.get("standard_reference") or params.get("standard") or ""
    profile_text = (
        (state.profile_choice or {}).get("profile")
        or getattr(state.recommendation, "profile", None)
        or ""
    )
    material_text = (
        (state.material_choice or {}).get("material")
        or getattr(state.recommendation, "material", None)
        or ""
    )
    missing_context: List[str] = []
    if not material_text:
        missing_context.append("material")
    if not profile_text:
        missing_context.append("profile")

    violations: List[Dict[str, Any]] = []
    checked: List[str] = []

    for rule in rules:
        rule_id = rule.get("id") or "unnamed_rule"
        when = rule.get("when") or {}
        require = rule.get("require") or {}

        profile_keywords = when.get("profile_keywords") or []
        material_present = bool(when.get("material_present"))
        profile_present = bool(when.get("profile_present"))

        if profile_keywords and not _text_contains_any(_normalized_text(profile_text), profile_keywords):
            continue
        if material_present and not material_text:
            continue
        if profile_present and not profile_text:
            continue

        checked.append(rule_id)

        standards_any = require.get("standards_any") or []
        if standards_any and not _text_contains_any(str(standard_ref), standards_any):
            violations.append(
                {
                    "id": rule_id,
                    "reason": "missing_standard_reference",
                    "details": {"required_any": standards_any, "found": standard_ref or None},
                }
            )

        required_params = require.get("parameters") or []
        missing_params = [key for key in required_params if not _param_present(params, key)]
        if missing_params:
            violations.append(
                {
                    "id": rule_id,
                    "reason": "missing_parameters",
                    "details": {"missing": missing_params},
                }
            )

        application_fields = require.get("application_fields") or []
        if application_fields:
            has_application = False
            for key in application_fields:
                if key in {"application_category", "use_case_raw"}:
                    if getattr(state, key, None):
                        has_application = True
                        break
                elif _param_present(params, key):
                    has_application = True
                    break
            if not has_application:
                violations.append(
                    {
                        "id": rule_id,
                        "reason": "missing_application_context",
                        "details": {"fields": application_fields},
                    }
                )

    skip_due_to_missing_context = not (material_text or profile_text)
    if skip_due_to_missing_context:
        violations.append(
            {
                "id": "missing_material_or_profile",
                "reason": "missing_material_or_profile",
                "details": {"missing": missing_context or ["material", "profile"]},
            }
        )

    status = "ok" if not violations else "violations"
    if skip_due_to_missing_context:
        status = "skipped"

    return {
        "status": status,
        "policy_version": policy.get("version"),
        "checked_rules": checked,
        "violations": violations,
        "standard_reference": standard_ref or None,
    }


__all__ = ["evaluate_policy"]
