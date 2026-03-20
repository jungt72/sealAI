from __future__ import annotations

from dataclasses import dataclass

INTERACTION_POLICY_VERSION = "interaction_policy_v1"


@dataclass(frozen=True)
class InteractionPolicyDecision:
    result_form: str
    path: str
    stream_mode: str
    interaction_class: str
    runtime_path: str
    binding_level: str
    has_case_state: bool
    coverage_status: str | None = None
    boundary_flags: tuple[str, ...] = ()
    escalation_reason: str | None = None
    required_fields: tuple[str, ...] = ()
    policy_version: str = INTERACTION_POLICY_VERSION


def evaluate_interaction_policy(message: str) -> InteractionPolicyDecision:
    lowered = message.lower()
    if "was ist" in lowered:
        return InteractionPolicyDecision(
            result_form="guided",
            path="fast",
            stream_mode="reply_only",
            interaction_class="KNOWLEDGE",
            runtime_path="FAST_KNOWLEDGE",
            binding_level="KNOWLEDGE",
            has_case_state=False,
        )
    if "berechne" in lowered:
        return InteractionPolicyDecision(
            result_form="guided",
            path="fast",
            stream_mode="reply_only",
            interaction_class="CALCULATION",
            runtime_path="FAST_CALCULATION",
            binding_level="CALCULATION",
            has_case_state=False,
        )
    return InteractionPolicyDecision(
        result_form="qualified",
        path="structured",
        stream_mode="structured_progress_stream",
        interaction_class="QUALIFICATION",
        runtime_path="STRUCTURED_QUALIFICATION",
        binding_level="ORIENTATION",
        has_case_state=True,
    )
