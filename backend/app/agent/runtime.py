"""
Agent Runtime — Legacy interaction-policy shim.

W3.4: interaction_policy is no longer called from production routing paths.
      This shim exists only for backward-compat with tests that still import
      INTERACTION_POLICY_VERSION or InteractionPolicyDecision from here.
      Production frontdoor routing: app.agent.runtime.gate.decide_route_async
"""
from app.agent.runtime.policy import (  # noqa: F401 — public re-export
    INTERACTION_POLICY_VERSION,
    InteractionPolicyDecision,
    legacy_policy_path_for_pre_gate,
)


def evaluate_interaction_policy(message: str) -> InteractionPolicyDecision:
    """
    Backwards-compatible shim. DEPRECATED — use app.agent.runtime.gate instead.
    Kept for test backward-compat only.
    """
    from app.agent.runtime.interaction_policy import evaluate_policy  # noqa: PLC0415

    return evaluate_policy(message)
