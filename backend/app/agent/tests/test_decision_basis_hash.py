from __future__ import annotations

from app.agent.state.models import DerivedState, EvidenceState, GovernedSessionState, NormalizedParameter, NormalizedState
from app.agent.state.persistence import compute_decision_basis_hash


def _state() -> GovernedSessionState:
    return GovernedSessionState(
        normalized=NormalizedState.model_validate(
            {
                "parameters": {
                    "medium": NormalizedParameter(
                        field_name="medium",
                        value="Wasser",
                        confidence="confirmed",
                        source="llm",
                    ),
                },
                "parameter_status": {"medium": "observed"},
            }
        ),
        derived=DerivedState(
            pv_value=0.39,
            velocity=2.5,
            field_status={"pv_value": "derived", "velocity": "derived"},
        ),
        evidence=EvidenceState(source_versions={"doc-1": "abc123"}),
        analysis_cycle=7,
    )


def test_same_state_yields_same_hash() -> None:
    state = _state()

    first = compute_decision_basis_hash(state)
    second = compute_decision_basis_hash(state)

    assert isinstance(first, str)
    assert first
    assert first == second


def test_change_in_normalized_changes_hash() -> None:
    state = _state()
    updated = state.model_copy(
        update={
            "normalized": state.normalized.model_copy(
                update={
                    "parameters": {
                        **state.normalized.parameters,
                        "pressure_bar": NormalizedParameter(
                            field_name="pressure_bar",
                            value=6.0,
                            confidence="confirmed",
                            source="llm",
                        ),
                    }
                }
            )
        }
    )

    assert compute_decision_basis_hash(updated) != compute_decision_basis_hash(state)


def test_change_in_derived_changes_hash() -> None:
    state = _state()
    updated = state.model_copy(update={"derived": state.derived.model_copy(update={"pv_value": 0.41})})

    assert compute_decision_basis_hash(updated) != compute_decision_basis_hash(state)


def test_change_in_evidence_versions_changes_hash() -> None:
    state = _state()
    updated = state.model_copy(
        update={"evidence": state.evidence.model_copy(update={"source_versions": {"doc-1": "xyz999"}})}
    )

    assert compute_decision_basis_hash(updated) != compute_decision_basis_hash(state)


def test_irrelevant_artifacts_outside_hash_basis_do_not_change_hash() -> None:
    state = _state()
    updated = state.model_copy(
        update={
            "analysis_cycle": 99,
            "action_readiness": state.action_readiness.model_copy(update={"pdf_ready": True, "pdf_url": "https://example.invalid/demo.pdf"}),
            "conversation_messages": [],
        }
    )

    assert compute_decision_basis_hash(updated) == compute_decision_basis_hash(state)
