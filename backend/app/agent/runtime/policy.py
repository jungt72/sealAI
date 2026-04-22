"""
Interaction Policy V1 — Data Models
Phase 0A.2

Typed enums and the InteractionPolicyDecision contract.
These are the authoritative types used by the router and persisted in case metadata.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.pre_gate_classification import PreGateClassification
from app.services.output_classifier import OutputClass


INTERACTION_POLICY_VERSION = "interaction_policy_v2"


def legacy_policy_path_for_pre_gate(
    classification: PreGateClassification,
) -> str:
    """Map Sprint-2 pre-gate classification to the legacy graph edge string."""
    if classification is PreGateClassification.GREETING:
        return "greeting"
    if classification is PreGateClassification.META_QUESTION:
        return "meta"
    if classification is PreGateClassification.KNOWLEDGE_QUERY:
        return "fast"
    if classification is PreGateClassification.BLOCKED:
        return "blocked"
    return "structured"


@dataclass(frozen=True)
class InteractionPolicyDecision:
    """
    The output of evaluate_policy().

    Authoritative for routing, streaming mode, and payload contract.
    Produced entirely by deterministic Python logic — never by free LLM generation.
    """

    output_class: OutputClass
    pre_gate_classification: PreGateClassification

    # Streaming mode for the frontend
    stream_mode: str  # "reply_only" | "structured_progress_stream"

    # Kept for backwards-compatibility with router payload and persistence layer
    interaction_class: str   # e.g. "DIRECT_ANSWER", "DETERMINISTIC_RESULT", "META_STATUS", "BLOCKED"
    runtime_path: str        # e.g. "FAST_DIRECT", "STRUCTURED_QUALIFICATION"
    binding_level: str       # "KNOWLEDGE" | "ORIENTATION"
    has_case_state: bool     # whether structured case persistence is activated

    # Coverage and boundary signals (forwarded to visible narrative)
    coverage_status: str | None = None
    boundary_flags: tuple[str, ...] = field(default_factory=tuple)
    escalation_reason: str | None = None
    required_fields: tuple[str, ...] = field(default_factory=tuple)

    policy_version: str = INTERACTION_POLICY_VERSION

    @property
    def result_form(self) -> str:
        """Legacy payload alias retained during router migration."""
        return self.output_class.value

    @property
    def policy_path(self) -> str:
        """Legacy graph edge alias derived from PreGateClassification."""
        return legacy_policy_path_for_pre_gate(self.pre_gate_classification)

    @property
    def path(self) -> str:
        """Legacy attribute retained for callers not yet migrated off policy_path."""
        return self.policy_path
