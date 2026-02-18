from __future__ import annotations

"""Stable LangGraph v2 contract for wiring-oriented tests."""

from typing import Iterable, Set, Tuple


MANDATORY_NODES: set[str] = {
    "policy_preflight_node",
    "resume_router_node",
    "frontdoor_discovery_node",
    "feasibility_guardrail_node",
    "supervisor_policy_node",
    "knowledge_entry_node",
    "ask_missing_node",
    "confirm_checkpoint_node",
    "policy_firewall_node",
}

MANDATORY_EDGES: set[tuple[str, str]] = {
    ("__start__", "policy_preflight_node"),
    ("policy_preflight_node", "resume_router_node"),
    ("resume_router_node", "frontdoor_discovery_node"),
    ("frontdoor_discovery_node", "feasibility_guardrail_node"),
    ("feasibility_guardrail_node", "supervisor_policy_node"),
    ("supervisor_policy_node", "knowledge_entry_node"),
    ("material_comparison_node", "supervisor_policy_node"),
    ("design_worker", "supervisor_policy_node"),
    ("calc_worker", "supervisor_policy_node"),
    ("product_explainer_node", "policy_firewall_node"),
}

# No direct bypass into supervisor from pre-gate or worker nodes.
FORBIDDEN_EDGES: set[tuple[str, str]] = {
    ("product_explainer_node", "autonomous_supervisor_node"),
    ("product_explainer_node", "supervisor_policy_node"),
}

ALLOWED_SUPERVISOR_INBOUND: set[str] = {
    "autonomous_supervisor_node",
    "calc_worker",
    "confirm_resume_node",
    "design_worker",
    "feasibility_guardrail_node",
    "material_comparison_node",
}


def edge_tuples(edges: Iterable[object]) -> Set[Tuple[str, str]]:
    return {(str(getattr(e, "source", "")), str(getattr(e, "target", ""))) for e in edges}
