"""
Agent Runtime — Legacy interaction-policy shim.

Residual compat only. The productive frontdoor routing authority lives in
app.agent.runtime.gate and the agent API router dispatch.
"""
from app.agent.agent.policy import (  # noqa: F401 — public re-export
    INTERACTION_POLICY_VERSION,
    InteractionPolicyDecision,
    ResultForm,
    RoutingPath,
)
def evaluate_interaction_policy(message: str) -> InteractionPolicyDecision:
    """
    Backwards-compatible shim for residual callers.
    Delegates lazily so importing this module does not keep the legacy policy
    on the productive router import path.
    """
    from app.agent.agent.interaction_policy import evaluate_policy  # noqa: PLC0415

    return evaluate_policy(message)
