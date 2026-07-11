"""Deterministic-first, evidence-first, one-shot online execution policy."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from sealai_v2.pipeline.routing import RouteDecision, RouteName

POLICY_VERSION = "execution-policy.v1"


class ExecutionClass(str, Enum):
    D0 = "D0"  # exact, previously validated low-risk answer cache hit
    D1 = "D1"  # deterministic clarification/lookup/calculation response
    S0 = "S0"  # simple low-risk generation, no reasoning
    S1 = "S1"  # standard technical reasoning
    C1 = "C1"  # complex/multi-document/tool-heavy case
    C2 = "C2"  # decision-relevant high-risk or conflict case
    H1 = "H1"  # human review required; no generative recommendation


class ModelTier(str, Enum):
    NONE = "none"
    STANDARD = "standard"
    FRONTIER = "frontier"


class VerificationMode(str, Enum):
    DETERMINISTIC = "deterministic"
    CLAIM_LLM = "claim_llm"
    HUMAN = "human"


class StreamingMode(str, Enum):
    FINAL = "final"
    DRAFT = "draft"
    ATOMIC = "atomic"


@dataclass(frozen=True)
class ExecutionFeatures:
    route: RouteDecision
    risk_flags: tuple[str, ...] = ()
    authoritative_evidence_count: int = 0
    provisional_evidence_count: int = 0
    document_count: int = 0
    tool_step_count: int = 0
    case_conflict_count: int = 0
    required_missing: tuple[str, ...] = ()
    contract_status: str | None = None
    untrusted_content_count: int = 0
    has_diagnosis: bool = False
    exact_cache_hit: bool = False
    reviewed_policy_fact_count: int = 0


@dataclass(frozen=True)
class ExecutionDecision:
    execution_class: ExecutionClass
    model_tier: ModelTier
    reasoning_effort: str | None
    verification_mode: VerificationMode
    streaming_mode: StreamingMode
    needs_human_review: bool
    reason: str
    policy_version: str = POLICY_VERSION


_TECHNICAL_ROUTES = frozenset(
    {
        RouteName.ENGINEERING_CASE,
        RouteName.LEAKAGE_TROUBLESHOOTING,
        RouteName.MATERIAL_COMPARISON,
        RouteName.RFQ_MANUFACTURER_BRIEF,
        RouteName.UNSUPPORTED_OR_AMBIGUOUS,
    }
)


def decide_execution(features: ExecutionFeatures) -> ExecutionDecision:
    route = features.route.route
    technical = route in _TECHNICAL_ROUTES or features.route.forced_full_pipeline
    evidence_missing = features.authoritative_evidence_count == 0

    if features.exact_cache_hit:
        return ExecutionDecision(
            ExecutionClass.D0,
            ModelTier.NONE,
            None,
            VerificationMode.DETERMINISTIC,
            StreamingMode.ATOMIC,
            False,
            "exact_validated_cache_hit",
        )

    if features.contract_status == "NEEDS_CLARIFICATION" or (
        technical and features.required_missing
    ):
        return ExecutionDecision(
            ExecutionClass.D1,
            ModelTier.NONE,
            None,
            VerificationMode.DETERMINISTIC,
            StreamingMode.ATOMIC,
            False,
            "deterministic_contract_clarification",
        )

    unresolved = bool(features.case_conflict_count or features.required_missing)
    if technical and features.risk_flags and (unresolved or evidence_missing):
        return ExecutionDecision(
            ExecutionClass.H1,
            ModelTier.NONE,
            None,
            VerificationMode.HUMAN,
            StreamingMode.ATOMIC,
            True,
            "high_risk_with_unresolved_or_ungrounded_basis",
        )

    if technical and (
        features.risk_flags
        or features.case_conflict_count
        or features.reviewed_policy_fact_count
    ):
        return ExecutionDecision(
            ExecutionClass.C2,
            ModelTier.FRONTIER,
            "high",
            VerificationMode.DETERMINISTIC,
            StreamingMode.ATOMIC,
            True,
            "decision_relevant_risk_conflict_or_policy_fact",
        )

    # A broad knowledge answer can legitimately cite many primary sources without becoming a
    # complex reasoning case. Counting each citation URL as a "document" previously promoted a
    # well-grounded PTFE/RWDR overview to the frontier model at four sources, increasing cost while
    # adding no decision risk. Keep reviewed, self-contained knowledge on the standard renderer;
    # untrusted input still takes the complex path below.
    if (
        route
        in {
            RouteName.GENERAL_SEALING_KNOWLEDGE,
            RouteName.MATERIAL_KNOWLEDGE,
        }
        and not features.route.forced_full_pipeline
        and features.untrusted_content_count == 0
    ):
        return ExecutionDecision(
            ExecutionClass.S0,
            ModelTier.STANDARD,
            "none",
            VerificationMode.DETERMINISTIC,
            StreamingMode.DRAFT,
            False,
            "low_risk_knowledge_route",
        )

    if (
        features.document_count >= 4
        or features.tool_step_count >= 3
        or features.untrusted_content_count > 0
        or (features.has_diagnosis and features.document_count >= 2)
    ):
        return ExecutionDecision(
            ExecutionClass.C1,
            ModelTier.FRONTIER,
            "high",
            VerificationMode.DETERMINISTIC,
            StreamingMode.ATOMIC,
            False,
            "complex_context_or_tool_depth",
        )

    if route is RouteName.SMALLTALK_NAVIGATION:
        return ExecutionDecision(
            ExecutionClass.S0,
            ModelTier.STANDARD,
            "none",
            VerificationMode.DETERMINISTIC,
            StreamingMode.FINAL,
            False,
            "deterministic_smalltalk_route",
        )

    return ExecutionDecision(
        ExecutionClass.S1,
        ModelTier.STANDARD,
        "high",
        VerificationMode.CLAIM_LLM,
        StreamingMode.ATOMIC,
        False,
        "standard_technical_reasoning",
    )


def deterministic_response(
    decision: ExecutionDecision,
    *,
    missing_fields: tuple[str, ...] = (),
    conflicts: tuple[str, ...] = (),
) -> str:
    if decision.execution_class is ExecutionClass.D1:
        fields = ", ".join(missing_fields) or "entscheidungsrelevante Angaben"
        return (
            f"Für die technische Einordnung fehlen noch: {fields}. "
            "Bitte ergänze diese Angaben; vorher wäre jede fallbezogene Aussage spekulativ."
        )
    if decision.execution_class is ExecutionClass.H1:
        details = [*missing_fields, *conflicts]
        suffix = f" Offen sind: {', '.join(details)}." if details else ""
        return (
            "Dieser Fall ist sicherheits- oder zulassungsrelevant und auf der vorhandenen "
            "Datenbasis nicht belastbar automatisiert einzuordnen. Eine fachliche Prüfung durch "
            f"Hersteller oder zuständige Fachstelle ist erforderlich.{suffix}"
        )
    raise ValueError("deterministic_response is only valid for D1/H1 decisions")
