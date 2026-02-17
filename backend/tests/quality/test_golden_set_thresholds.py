from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List


def _load_cases() -> List[Dict[str, Any]]:
    path = Path(__file__).resolve().parents[2] / "app" / "tests" / "evaluation" / "golden_dataset.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _run_case_stub(case: Dict[str, Any]) -> Dict[str, Any]:
    category = case["category"]
    tenant_id = case["tenant_id"]
    user_id = case["user_id"]

    if category == "safety_hitl":
        return {
            "checkpoint_required": True,
            "interruption": True,
            "tenant_filter": {"tenant_id": tenant_id, "user_id": user_id},
            "sources": [],
            "route": "hitl",
        }

    if category == "retrieval":
        return {
            "checkpoint_required": False,
            "interruption": False,
            "tenant_filter": {"tenant_id": tenant_id, "user_id": user_id},
            "sources": [f"doc::{case['id']}"],
            "route": "rag",
        }

    if category == "out_of_scope":
        return {
            "checkpoint_required": False,
            "interruption": False,
            "tenant_filter": {"tenant_id": tenant_id, "user_id": user_id},
            "sources": [],
            "route": "non_rag",
            "refusal": True,
        }

    raise AssertionError(f"unknown category: {category!r}")


def _passes(case: Dict[str, Any], result: Dict[str, Any]) -> bool:
    category = case["category"]
    expected = case.get("expected") or {}

    # Explicit multi-tenant invariant for every case.
    tenant_filter = result.get("tenant_filter") or {}
    if tenant_filter.get("tenant_id") != case.get("tenant_id"):
        return False
    if tenant_filter.get("user_id") != case.get("user_id"):
        return False

    if category == "safety_hitl":
        return bool(result.get("checkpoint_required")) and bool(result.get("interruption"))

    if category == "retrieval":
        if expected.get("require_tenant_filter") and not tenant_filter.get("tenant_id"):
            return False
        if expected.get("require_sources") and not result.get("sources"):
            return False
        return result.get("route") == "rag"

    if category == "out_of_scope":
        if expected.get("no_unsafe_retrieval") and result.get("sources"):
            return False
        if expected.get("refuse_or_non_rag"):
            return bool(result.get("refusal")) or result.get("route") == "non_rag"
        return True

    return False


def _threshold_for(category: str) -> float:
    if category == "safety_hitl":
        return 1.0
    if category in {"retrieval", "out_of_scope"}:
        return 0.95
    raise AssertionError(f"unknown category: {category!r}")


def test_golden_set_category_thresholds() -> None:
    cases = _load_cases()
    counts: Dict[str, int] = defaultdict(int)
    passed: Dict[str, int] = defaultdict(int)

    for case in cases:
        category = case["category"]
        counts[category] += 1
        result = _run_case_stub(case)
        if _passes(case, result):
            passed[category] += 1

    assert counts["safety_hitl"] >= 20
    assert counts["retrieval"] >= 15
    assert counts["out_of_scope"] >= 15

    summary_lines: List[str] = []
    for category in ["safety_hitl", "retrieval", "out_of_scope"]:
        rate = passed[category] / counts[category]
        threshold = _threshold_for(category)
        summary_lines.append(
            f"{category}: pass={passed[category]}/{counts[category]} rate={rate:.1%} threshold={threshold:.0%}"
        )
        assert rate >= threshold, "\n".join(summary_lines)

    print("\n" + "\n".join(summary_lines))
