"""
Agent Runtime — Interaction Policy Entry Point
Phase 0A.2

Re-exports the new policy types for backwards compatibility with the router.
All routing logic lives in app.agent.agent.interaction_policy.
"""
from app.agent.agent.policy import (  # noqa: F401 — public re-export
    INTERACTION_POLICY_VERSION,
    InteractionPolicyDecision,
    ResultForm,
    RoutingPath,
)
from app.agent.agent.interaction_policy import evaluate_policy  # noqa: F401


def evaluate_interaction_policy(message: str) -> InteractionPolicyDecision:
    """
    Backwards-compatible shim used by existing router imports.
    Delegates to evaluate_policy() with no current_state context.
    """
    return evaluate_policy(message)
