from __future__ import annotations

from app.agent.state.models import (
    ActionReadinessState,
    DecisionState,
    DerivedState,
    EvidenceState,
    GovernedSessionState,
    NormalizedState,
    ObservedState,
)


def test_all_target_six_layers_are_instantiable() -> None:
    state = GovernedSessionState()

    assert isinstance(state.observed, ObservedState)
    assert isinstance(state.normalized, NormalizedState)
    assert isinstance(state.derived, DerivedState)
    assert isinstance(state.evidence, EvidenceState)
    assert isinstance(state.decision, DecisionState)
    assert isinstance(state.action_readiness, ActionReadinessState)


def test_evidence_state_exposes_source_versions() -> None:
    evidence = EvidenceState()

    assert evidence.source_versions == {}


def test_action_readiness_generates_unique_idempotency_keys() -> None:
    first = ActionReadinessState()
    second = ActionReadinessState()

    assert isinstance(first.idempotency_key, str)
    assert first.idempotency_key
    assert isinstance(second.idempotency_key, str)
    assert second.idempotency_key
    assert first.idempotency_key != second.idempotency_key
