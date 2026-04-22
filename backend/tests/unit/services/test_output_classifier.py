from __future__ import annotations

import pytest

from app.domain.pre_gate_classification import PreGateClassification
from app.services.output_classifier import (
    OutputClassificationInput,
    OutputClassifier,
    OutputClass,
)


@pytest.fixture
def classifier() -> OutputClassifier:
    return OutputClassifier()


def _classify(
    classifier: OutputClassifier,
    **kwargs: object,
) -> OutputClass:
    return classifier.classify(OutputClassificationInput(**kwargs)).output_class


def test_output_class_values_match_authority_set() -> None:
    assert {member.value for member in OutputClass} == {
        "conversational_answer",
        "structured_clarification",
        "governed_state_update",
        "technical_preselection",
        "rca_hypothesis",
        "candidate_shortlist",
        "inquiry_ready",
    }


@pytest.mark.parametrize(
    "pre_gate",
    [
        PreGateClassification.GREETING,
        PreGateClassification.META_QUESTION,
        PreGateClassification.KNOWLEDGE_QUERY,
        PreGateClassification.BLOCKED,
    ],
)
def test_non_domain_pre_gate_outputs_conversational_answer(
    classifier: OutputClassifier,
    pre_gate: PreGateClassification,
) -> None:
    assert (
        _classify(classifier, pre_gate=pre_gate)
        is OutputClass.CONVERSATIONAL_ANSWER
    )


def test_domain_conversation_mode_outputs_conversational_answer(
    classifier: OutputClassifier,
) -> None:
    assert (
        _classify(
            classifier,
            pre_gate=PreGateClassification.DOMAIN_INQUIRY,
            gate_mode="conversation",
        )
        is OutputClass.CONVERSATIONAL_ANSWER
    )


@pytest.mark.parametrize("governance_class", [None, "C", "D", "unexpected"])
def test_missing_or_non_releasable_governance_outputs_structured_clarification(
    classifier: OutputClassifier,
    governance_class: str | None,
) -> None:
    assert (
        _classify(
            classifier,
            pre_gate=PreGateClassification.DOMAIN_INQUIRY,
            gate_mode="governed",
            governance_class=governance_class,
        )
        is OutputClass.STRUCTURED_CLARIFICATION
    )


def test_governance_b_outputs_structured_clarification_by_default(
    classifier: OutputClassifier,
) -> None:
    assert (
        _classify(
            classifier,
            pre_gate=PreGateClassification.DOMAIN_INQUIRY,
            governance_class="B",
        )
        is OutputClass.STRUCTURED_CLARIFICATION
    )


def test_governance_b_fast_confirm_outputs_governed_state_update(
    classifier: OutputClassifier,
) -> None:
    assert (
        _classify(
            classifier,
            pre_gate=PreGateClassification.DOMAIN_INQUIRY,
            governance_class="B",
            fast_confirm_applicable=True,
        )
        is OutputClass.GOVERNED_STATE_UPDATE
    )


def test_governance_a_with_preselection_blockers_stays_clarification(
    classifier: OutputClassifier,
) -> None:
    assert (
        _classify(
            classifier,
            pre_gate=PreGateClassification.DOMAIN_INQUIRY,
            governance_class="A",
            has_preselection_blockers=True,
            inquiry_ready=True,
        )
        is OutputClass.STRUCTURED_CLARIFICATION
    )


def test_inquiry_ready_has_highest_releasable_priority(
    classifier: OutputClassifier,
) -> None:
    assert (
        _classify(
            classifier,
            pre_gate=PreGateClassification.DOMAIN_INQUIRY,
            governance_class="A",
            inquiry_ready=True,
            candidate_shortlist_ready=True,
            has_compute_results=True,
        )
        is OutputClass.INQUIRY_READY
    )


def test_candidate_shortlist_precedes_technical_preselection(
    classifier: OutputClassifier,
) -> None:
    assert (
        _classify(
            classifier,
            pre_gate=PreGateClassification.DOMAIN_INQUIRY,
            governance_class="A",
            candidate_shortlist_ready=True,
            has_compute_results=True,
        )
        is OutputClass.CANDIDATE_SHORTLIST
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"has_compute_results": True},
        {"recommendation_ready": True},
    ],
)
def test_technical_preselection_when_compute_or_recommendation_ready(
    classifier: OutputClassifier,
    kwargs: dict[str, bool],
) -> None:
    assert (
        _classify(
            classifier,
            pre_gate=PreGateClassification.DOMAIN_INQUIRY,
            governance_class="A",
            **kwargs,
        )
        is OutputClass.TECHNICAL_PRESELECTION
    )


def test_blocking_evidence_gaps_downgrade_preselection_to_state_update(
    classifier: OutputClassifier,
) -> None:
    assert (
        _classify(
            classifier,
            pre_gate=PreGateClassification.DOMAIN_INQUIRY,
            governance_class="A",
            has_compute_results=True,
            has_blocking_evidence_gaps=True,
        )
        is OutputClass.GOVERNED_STATE_UPDATE
    )


def test_governance_a_without_result_basis_outputs_state_update(
    classifier: OutputClassifier,
) -> None:
    assert (
        _classify(
            classifier,
            pre_gate=PreGateClassification.DOMAIN_INQUIRY,
            governance_class="A",
        )
        is OutputClass.GOVERNED_STATE_UPDATE
    )


def test_rca_degrades_to_structured_clarification_in_mvp(
    classifier: OutputClassifier,
) -> None:
    result = classifier.classify(
        OutputClassificationInput(
            pre_gate=PreGateClassification.DOMAIN_INQUIRY,
            request_type="rca_failure_analysis",
            governance_class="A",
            inquiry_ready=True,
        )
    )

    assert result.output_class is OutputClass.STRUCTURED_CLARIFICATION
    assert result.reasoning == "rca_degraded_in_mvp"


def test_default_input_is_conservative_structured_clarification(
    classifier: OutputClassifier,
) -> None:
    assert classifier.classify(OutputClassificationInput()).output_class is (
        OutputClass.STRUCTURED_CLARIFICATION
    )


@pytest.mark.parametrize(
    ("name", "kwargs", "expected", "reasoning"),
    [
        (
            "greeting_ignores_governance_signals",
            {
                "pre_gate": PreGateClassification.GREETING,
                "governance_class": "A",
                "inquiry_ready": True,
            },
            OutputClass.CONVERSATIONAL_ANSWER,
            "pre_gate_non_case_interaction",
        ),
        (
            "meta_ignores_shortlist_signal",
            {
                "pre_gate": PreGateClassification.META_QUESTION,
                "candidate_shortlist_ready": True,
            },
            OutputClass.CONVERSATIONAL_ANSWER,
            "pre_gate_non_case_interaction",
        ),
        (
            "knowledge_ignores_compute_signal",
            {
                "pre_gate": PreGateClassification.KNOWLEDGE_QUERY,
                "has_compute_results": True,
            },
            OutputClass.CONVERSATIONAL_ANSWER,
            "pre_gate_non_case_interaction",
        ),
        (
            "blocked_ignores_inquiry_signal",
            {
                "pre_gate": PreGateClassification.BLOCKED,
                "inquiry_ready": True,
            },
            OutputClass.CONVERSATIONAL_ANSWER,
            "pre_gate_non_case_interaction",
        ),
        (
            "domain_uppercase_conversation",
            {
                "pre_gate": PreGateClassification.DOMAIN_INQUIRY,
                "gate_mode": "CONVERSATION",
                "governance_class": "A",
            },
            OutputClass.CONVERSATIONAL_ANSWER,
            "domain_inquiry_conversation_mode",
        ),
        (
            "domain_conversation_spaces",
            {
                "pre_gate": PreGateClassification.DOMAIN_INQUIRY,
                "gate_mode": " conversation ",
                "inquiry_ready": True,
            },
            OutputClass.CONVERSATIONAL_ANSWER,
            "domain_inquiry_conversation_mode",
        ),
        (
            "none_gate_mode_defaults_governed_missing_class",
            {
                "pre_gate": PreGateClassification.DOMAIN_INQUIRY,
                "gate_mode": None,
            },
            OutputClass.STRUCTURED_CLARIFICATION,
            "governance_class_missing",
        ),
        (
            "exploration_missing_class_clarifies",
            {
                "pre_gate": PreGateClassification.DOMAIN_INQUIRY,
                "gate_mode": "exploration",
            },
            OutputClass.STRUCTURED_CLARIFICATION,
            "governance_class_missing",
        ),
        (
            "governed_class_c_blocks_inquiry",
            {
                "pre_gate": PreGateClassification.DOMAIN_INQUIRY,
                "governance_class": "C",
                "inquiry_ready": True,
            },
            OutputClass.STRUCTURED_CLARIFICATION,
            "governance_class_C",
        ),
        (
            "governed_class_d_blocks_shortlist",
            {
                "pre_gate": PreGateClassification.DOMAIN_INQUIRY,
                "governance_class": "D",
                "candidate_shortlist_ready": True,
            },
            OutputClass.STRUCTURED_CLARIFICATION,
            "governance_class_D",
        ),
        (
            "unknown_governance_class_is_conservative",
            {
                "pre_gate": PreGateClassification.DOMAIN_INQUIRY,
                "governance_class": "Z",
                "has_compute_results": True,
            },
            OutputClass.STRUCTURED_CLARIFICATION,
            "unknown_governance_class_Z",
        ),
        (
            "governance_b_with_inquiry_ready_still_clarifies",
            {
                "pre_gate": PreGateClassification.DOMAIN_INQUIRY,
                "governance_class": "B",
                "inquiry_ready": True,
            },
            OutputClass.STRUCTURED_CLARIFICATION,
            "governance_b_blocking_unknowns",
        ),
        (
            "governance_b_fast_confirm_beats_compute",
            {
                "pre_gate": PreGateClassification.DOMAIN_INQUIRY,
                "governance_class": "B",
                "fast_confirm_applicable": True,
                "has_compute_results": True,
            },
            OutputClass.GOVERNED_STATE_UPDATE,
            "governance_b_fast_confirm",
        ),
        (
            "governance_a_blockers_beat_inquiry",
            {
                "pre_gate": PreGateClassification.DOMAIN_INQUIRY,
                "governance_class": "A",
                "has_preselection_blockers": True,
                "inquiry_ready": True,
            },
            OutputClass.STRUCTURED_CLARIFICATION,
            "preselection_blockers_present",
        ),
        (
            "governance_a_blockers_beat_shortlist",
            {
                "pre_gate": PreGateClassification.DOMAIN_INQUIRY,
                "governance_class": "A",
                "has_preselection_blockers": True,
                "candidate_shortlist_ready": True,
            },
            OutputClass.STRUCTURED_CLARIFICATION,
            "preselection_blockers_present",
        ),
        (
            "governance_a_blockers_beat_preselection",
            {
                "pre_gate": PreGateClassification.DOMAIN_INQUIRY,
                "governance_class": "A",
                "has_preselection_blockers": True,
                "has_compute_results": True,
            },
            OutputClass.STRUCTURED_CLARIFICATION,
            "preselection_blockers_present",
        ),
        (
            "inquiry_ready_beats_shortlist",
            {
                "pre_gate": PreGateClassification.DOMAIN_INQUIRY,
                "governance_class": "A",
                "inquiry_ready": True,
                "candidate_shortlist_ready": True,
            },
            OutputClass.INQUIRY_READY,
            "inquiry_ready",
        ),
        (
            "inquiry_ready_beats_evidence_gap",
            {
                "pre_gate": PreGateClassification.DOMAIN_INQUIRY,
                "governance_class": "A",
                "inquiry_ready": True,
                "has_compute_results": True,
                "has_blocking_evidence_gaps": True,
            },
            OutputClass.INQUIRY_READY,
            "inquiry_ready",
        ),
        (
            "shortlist_beats_compute",
            {
                "pre_gate": PreGateClassification.DOMAIN_INQUIRY,
                "governance_class": "A",
                "candidate_shortlist_ready": True,
                "has_compute_results": True,
            },
            OutputClass.CANDIDATE_SHORTLIST,
            "candidate_shortlist_ready",
        ),
        (
            "shortlist_beats_recommendation_ready",
            {
                "pre_gate": PreGateClassification.DOMAIN_INQUIRY,
                "governance_class": "A",
                "candidate_shortlist_ready": True,
                "recommendation_ready": True,
            },
            OutputClass.CANDIDATE_SHORTLIST,
            "candidate_shortlist_ready",
        ),
        (
            "compute_with_clean_evidence_preselects",
            {
                "pre_gate": PreGateClassification.DOMAIN_INQUIRY,
                "governance_class": "A",
                "has_compute_results": True,
            },
            OutputClass.TECHNICAL_PRESELECTION,
            "technical_preselection_ready",
        ),
        (
            "recommendation_ready_preselects_without_compute",
            {
                "pre_gate": PreGateClassification.DOMAIN_INQUIRY,
                "governance_class": "A",
                "recommendation_ready": True,
            },
            OutputClass.TECHNICAL_PRESELECTION,
            "technical_preselection_ready",
        ),
        (
            "compute_evidence_gap_downgrades",
            {
                "pre_gate": PreGateClassification.DOMAIN_INQUIRY,
                "governance_class": "A",
                "has_compute_results": True,
                "has_blocking_evidence_gaps": True,
            },
            OutputClass.GOVERNED_STATE_UPDATE,
            "blocking_evidence_gaps_downgrade",
        ),
        (
            "recommendation_evidence_gap_downgrades",
            {
                "pre_gate": PreGateClassification.DOMAIN_INQUIRY,
                "governance_class": "A",
                "recommendation_ready": True,
                "has_blocking_evidence_gaps": True,
            },
            OutputClass.GOVERNED_STATE_UPDATE,
            "blocking_evidence_gaps_downgrade",
        ),
        (
            "governance_a_no_release_basis_updates_state",
            {
                "pre_gate": PreGateClassification.DOMAIN_INQUIRY,
                "governance_class": "A",
            },
            OutputClass.GOVERNED_STATE_UPDATE,
            "governance_a_state_update",
        ),
        (
            "rca_beats_inquiry_ready",
            {
                "pre_gate": PreGateClassification.DOMAIN_INQUIRY,
                "request_type": "rca_failure_analysis",
                "governance_class": "A",
                "inquiry_ready": True,
            },
            OutputClass.STRUCTURED_CLARIFICATION,
            "rca_degraded_in_mvp",
        ),
        (
            "rca_beats_shortlist",
            {
                "pre_gate": PreGateClassification.DOMAIN_INQUIRY,
                "request_type": "rca_failure_analysis",
                "governance_class": "A",
                "candidate_shortlist_ready": True,
            },
            OutputClass.STRUCTURED_CLARIFICATION,
            "rca_degraded_in_mvp",
        ),
        (
            "rca_beats_preselection",
            {
                "pre_gate": PreGateClassification.DOMAIN_INQUIRY,
                "request_type": "rca_failure_analysis",
                "governance_class": "A",
                "has_compute_results": True,
            },
            OutputClass.STRUCTURED_CLARIFICATION,
            "rca_degraded_in_mvp",
        ),
        (
            "rca_in_conversation_still_degrades",
            {
                "pre_gate": PreGateClassification.DOMAIN_INQUIRY,
                "gate_mode": "conversation",
                "request_type": "rca_failure_analysis",
            },
            OutputClass.STRUCTURED_CLARIFICATION,
            "rca_degraded_in_mvp",
        ),
        (
            "non_rca_request_type_does_not_change_a_state",
            {
                "pre_gate": PreGateClassification.DOMAIN_INQUIRY,
                "request_type": "new_design",
                "governance_class": "A",
            },
            OutputClass.GOVERNED_STATE_UPDATE,
            "governance_a_state_update",
        ),
        (
            "non_rca_request_type_keeps_preselection",
            {
                "pre_gate": PreGateClassification.DOMAIN_INQUIRY,
                "request_type": "validation_check",
                "governance_class": "A",
                "has_compute_results": True,
            },
            OutputClass.TECHNICAL_PRESELECTION,
            "technical_preselection_ready",
        ),
        (
            "fast_confirm_flag_ignored_for_a_without_basis",
            {
                "pre_gate": PreGateClassification.DOMAIN_INQUIRY,
                "governance_class": "A",
                "fast_confirm_applicable": True,
            },
            OutputClass.GOVERNED_STATE_UPDATE,
            "governance_a_state_update",
        ),
        (
            "evidence_gap_without_result_basis_still_state_update",
            {
                "pre_gate": PreGateClassification.DOMAIN_INQUIRY,
                "governance_class": "A",
                "has_blocking_evidence_gaps": True,
            },
            OutputClass.GOVERNED_STATE_UPDATE,
            "governance_a_state_update",
        ),
        (
            "empty_gate_mode_is_governed_semantics",
            {
                "pre_gate": PreGateClassification.DOMAIN_INQUIRY,
                "gate_mode": "",
                "governance_class": "A",
                "has_compute_results": True,
            },
            OutputClass.TECHNICAL_PRESELECTION,
            "technical_preselection_ready",
        ),
        (
            "unknown_gate_mode_is_governed_semantics",
            {
                "pre_gate": PreGateClassification.DOMAIN_INQUIRY,
                "gate_mode": "unexpected",
                "governance_class": "A",
                "candidate_shortlist_ready": True,
            },
            OutputClass.CANDIDATE_SHORTLIST,
            "candidate_shortlist_ready",
        ),
        (
            "lowercase_governance_class_is_not_promoted",
            {
                "pre_gate": PreGateClassification.DOMAIN_INQUIRY,
                "governance_class": "a",
                "inquiry_ready": True,
            },
            OutputClass.STRUCTURED_CLARIFICATION,
            "unknown_governance_class_a",
        ),
    ],
)
def test_output_classifier_matrix_cases(
    classifier: OutputClassifier,
    name: str,
    kwargs: dict[str, object],
    expected: OutputClass,
    reasoning: str,
) -> None:
    result = classifier.classify(OutputClassificationInput(**kwargs))

    assert result.output_class is expected, name
    assert result.reasoning == reasoning


def test_no_deprecated_resultform_values_are_output_classes() -> None:
    deprecated = {
        "direct_answer",
        "guided_recommendation",
        "deterministic_result",
        "qualified_case",
    }

    assert not deprecated & {member.value for member in OutputClass}
