"""
Interaction Policy V1 — Data Models
Phase 0A.2

Typed enums and the InteractionPolicyDecision contract.
These are the authoritative types used by the router and persisted in case metadata.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ResultForm(str, Enum):
    """The four output forms defined in the Umbauplan (Section 2.1)."""

    DIRECT_ANSWER = "direct_answer"
    """Immediate factual help — glossary, comparisons, background knowledge."""

    GUIDED_RECOMMENDATION = "guided_recommendation"
    """Orientating guidance with visible open points and assumptions."""

    DETERMINISTIC_RESULT = "deterministic_result"
    """Calculated result from a deterministic service (e.g. RWDR speed check)."""

    QUALIFIED_CASE = "qualified_case"
    """Full technical case with governance gates and audit trail."""


class RoutingPath(str, Enum):
    """Internal execution path for the agent graph."""

    FAST_PATH = "fast"
    """Lightweight execution — no full qualification pipeline."""

    STRUCTURED_PATH = "structured"
    """Full structured pipeline with case state and persistence."""

    META_PATH = "meta"
    """Deterministic state-status response — no LLM involved."""

    BLOCKED_PATH = "blocked"
    """Request explicitly asks for content SealAI is forbidden to provide.
    Returns a deterministic safe refusal. No LLM, no pipeline."""

    GREETING_PATH = "greeting"
    """Trivial smalltalk / greeting — deterministic response, no LLM, no RAG."""


INTERACTION_POLICY_VERSION = "interaction_policy_v2"


@dataclass(frozen=True)
class InteractionPolicyDecision:
    """
    The output of evaluate_policy().

    Authoritative for routing, streaming mode, and payload contract.
    Produced entirely by deterministic Python logic — never by free LLM generation.
    """

    result_form: ResultForm
    path: RoutingPath

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
