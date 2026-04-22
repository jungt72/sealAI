# Re-export shim — canonical location: app.agent.runtime.policy
# DO NOT add logic here. This file exists only for import compatibility.
from app.agent.runtime.policy import (  # noqa: F401
    INTERACTION_POLICY_VERSION,
    InteractionPolicyDecision,
    legacy_policy_path_for_pre_gate,
)
