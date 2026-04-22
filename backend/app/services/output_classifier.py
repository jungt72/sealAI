from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.domain.pre_gate_classification import PreGateClassification


class OutputClass(str, Enum):
    CONVERSATIONAL_ANSWER = "conversational_answer"
    STRUCTURED_CLARIFICATION = "structured_clarification"
    GOVERNED_STATE_UPDATE = "governed_state_update"
    TECHNICAL_PRESELECTION = "technical_preselection"
    RCA_HYPOTHESIS = "rca_hypothesis"
    CANDIDATE_SHORTLIST = "candidate_shortlist"
    INQUIRY_READY = "inquiry_ready"


@dataclass(frozen=True, slots=True)
class OutputClassificationInput:
    pre_gate: PreGateClassification = PreGateClassification.DOMAIN_INQUIRY
    gate_mode: str | None = "governed"
    request_type: str | None = None
    governance_class: str | None = None
    fast_confirm_applicable: bool = False
    has_preselection_blockers: bool = False
    inquiry_ready: bool = False
    candidate_shortlist_ready: bool = False
    has_compute_results: bool = False
    recommendation_ready: bool = False
    has_blocking_evidence_gaps: bool = False


@dataclass(frozen=True, slots=True)
class OutputClassificationResult:
    output_class: OutputClass
    reasoning: str


class OutputClassifier:
    """Pure deterministic mapping from classification state to output class."""

    def classify(
        self,
        input: OutputClassificationInput,
    ) -> OutputClassificationResult:
        if input.pre_gate is not PreGateClassification.DOMAIN_INQUIRY:
            return self._result(
                OutputClass.CONVERSATIONAL_ANSWER,
                "pre_gate_non_case_interaction",
            )

        if input.request_type == "rca_failure_analysis":
            return self._result(
                OutputClass.STRUCTURED_CLARIFICATION,
                "rca_degraded_in_mvp",
            )

        gate_mode = str(input.gate_mode or "").strip().lower()
        if gate_mode == "conversation":
            return self._result(
                OutputClass.CONVERSATIONAL_ANSWER,
                "domain_inquiry_conversation_mode",
            )

        gov_class = input.governance_class
        if gov_class is None or gov_class in {"C", "D"}:
            return self._result(
                OutputClass.STRUCTURED_CLARIFICATION,
                f"governance_class_{gov_class or 'missing'}",
            )

        if gov_class == "B":
            if input.fast_confirm_applicable:
                return self._result(
                    OutputClass.GOVERNED_STATE_UPDATE,
                    "governance_b_fast_confirm",
                )
            return self._result(
                OutputClass.STRUCTURED_CLARIFICATION,
                "governance_b_blocking_unknowns",
            )

        if gov_class == "A":
            if input.has_preselection_blockers:
                return self._result(
                    OutputClass.STRUCTURED_CLARIFICATION,
                    "preselection_blockers_present",
                )
            if input.inquiry_ready:
                return self._result(OutputClass.INQUIRY_READY, "inquiry_ready")
            if input.candidate_shortlist_ready:
                return self._result(
                    OutputClass.CANDIDATE_SHORTLIST,
                    "candidate_shortlist_ready",
                )
            if input.has_compute_results or input.recommendation_ready:
                if input.has_blocking_evidence_gaps:
                    return self._result(
                        OutputClass.GOVERNED_STATE_UPDATE,
                        "blocking_evidence_gaps_downgrade",
                    )
                return self._result(
                    OutputClass.TECHNICAL_PRESELECTION,
                    "technical_preselection_ready",
                )
            return self._result(
                OutputClass.GOVERNED_STATE_UPDATE,
                "governance_a_state_update",
            )

        return self._result(
            OutputClass.STRUCTURED_CLARIFICATION,
            f"unknown_governance_class_{gov_class}",
        )

    @staticmethod
    def _result(
        output_class: OutputClass,
        reasoning: str,
    ) -> OutputClassificationResult:
        return OutputClassificationResult(
            output_class=output_class,
            reasoning=reasoning,
        )
