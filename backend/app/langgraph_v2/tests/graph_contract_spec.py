from __future__ import annotations

"""Stable LangGraph v2 contract for wiring-oriented tests."""

from typing import Iterable, Set, Tuple


MANDATORY_NODES: set[str] = {
    "policy_preflight_node",
    "resume_router_node",
    "frontdoor_discovery_node",
    "failure_triage_node",
    "feasibility_guardrail_node",
    "assumption_lock_node",
    "supervisor_policy_node",
    "knowledge_entry_node",
    "ask_missing_node",
    "confirm_checkpoint_node",
    "policy_firewall_node",
}

MANDATORY_EDGES: set[tuple[str, str]] = {
    ("__start__", "policy_preflight_node"),
    ("policy_preflight_node", "resume_router_node"),
    ("failure_triage_node", "feasibility_guardrail_node"),
    ("feasibility_guardrail_node", "assumption_lock_node"),
    ("assumption_lock_node", "supervisor_policy_node"),
    ("supervisor_policy_node", "knowledge_entry_node"),
    ("material_comparison_node", "assumption_lock_node"),
    ("design_worker", "assumption_lock_node"),
    ("calc_worker", "assumption_lock_node"),
    ("product_explainer_node", "policy_firewall_node"),
}

# No direct bypass into supervisor from pre-gate or worker nodes.
FORBIDDEN_EDGES: set[tuple[str, str]] = {
    ("frontdoor_discovery_node", "supervisor_policy_node"),
    ("failure_triage_node", "supervisor_policy_node"),
    ("feasibility_guardrail_node", "supervisor_policy_node"),
    ("autonomous_supervisor_node", "supervisor_policy_node"),
    ("material_comparison_node", "supervisor_policy_node"),
    ("design_worker", "supervisor_policy_node"),
    ("calc_worker", "supervisor_policy_node"),
}

ALLOWED_SUPERVISOR_INBOUND: set[str] = {"assumption_lock_node"}


def edge_tuples(edges: Iterable[object]) -> Set[Tuple[str, str]]:
    return {(str(getattr(e, "source", "")), str(getattr(e, "target", ""))) for e in edges}

