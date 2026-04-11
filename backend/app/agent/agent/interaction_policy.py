# Re-export shim — canonical location: app.agent.runtime.interaction_policy
# DO NOT add logic here. This file exists only for import compatibility.
from app.agent.runtime.interaction_policy import (  # noqa: F401
    evaluate_policy,
    _check_input_blocked,
    _is_greeting,
    _is_meta_query,
    _fast_path_upgrade_to_structured,
    _has_active_case,
    _missing_critical_params,
    _direct_answer,
    _deterministic_result,
    _meta_path,
    _greeting_path,
    _blocked_path,
    _call_routing_llm,
    _evaluate_deterministic_tiers,
    _resolve_llm_route,
)
