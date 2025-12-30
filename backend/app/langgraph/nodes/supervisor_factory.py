from __future__ import annotations

from typing import Any, Dict

# These callables are patched in tests.
def planner_node(state: Dict[str, Any]) -> Dict[str, Any]:
    return {}


def specialist_executor(state: Dict[str, Any]) -> Dict[str, Any]:
    return {}


def challenger_feedback(state: Dict[str, Any]) -> Dict[str, Any]:
    return {}


def run_quality_review(state: Dict[str, Any]) -> Dict[str, Any]:
    return {}


def resolver(state: Dict[str, Any]) -> Dict[str, Any]:
    return {}


_SUPERVISOR_FLOW = None


def _merge_state(state: Dict[str, Any], update: Dict[str, Any]) -> Dict[str, Any]:
    if not update:
        return state
    merged = dict(state)
    for key, value in update.items():
        if key in {"slots", "routing", "meta"}:
            base = dict(merged.get(key) or {})
            base.update(value or {})
            merged[key] = base
        elif key == "messages":
            merged[key] = list(merged.get(key) or []) + list(value or [])
        else:
            merged[key] = value
    return merged


class _SupervisorGraph:
    def invoke(self, state: Dict[str, Any]) -> Dict[str, Any]:
        current = dict(state)
        current = _merge_state(current, planner_node(current))
        current = _merge_state(current, specialist_executor(current))

        review_loops = int(current.get("review_loops") or 0)
        confidence = None
        for _ in range(2):
            review = run_quality_review(current)
            current = _merge_state(current, review)
            routing = current.get("routing") or {}
            confidence = routing.get("confidence")
            if confidence is None or confidence >= 0.7:
                break
            review_loops += 1
            current["review_loops"] = review_loops
            current = _merge_state(current, challenger_feedback(current))

        if confidence is not None:
            current["confidence"] = confidence

        current = _merge_state(current, resolver(current))
        return current


def build_supervisor_subgraph() -> _SupervisorGraph:
    return _SupervisorGraph()


def build_supervisor() -> _SupervisorGraph:
    return _SupervisorGraph()


__all__ = [
    "_SUPERVISOR_FLOW",
    "planner_node",
    "specialist_executor",
    "challenger_feedback",
    "run_quality_review",
    "resolver",
    "build_supervisor_subgraph",
    "build_supervisor",
]
