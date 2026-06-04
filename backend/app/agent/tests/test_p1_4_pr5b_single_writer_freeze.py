"""P1-4 PR5b — characterization freeze for the S3 governed-layer content-syncs
before they are routed through reducer helpers (single-writer invariant).

Three deterministic model_copy sites produce governed-layer instances outside
the reducer chain:
  - api/utils.py::_sync_governed_state_from_review_outcome  (governance)
  - graph/output_contract_assembly.py  (decision.blocking_reasons)
  - state/persistence.py::_with_decision_basis_hash         (decision.decision_basis_hash)

This freeze locks the observable behaviour of the two that have no other direct
coverage, so routing them through reducers stays byte-identical. (The output
contract downgrade is covered by test_output_contract_node.py.)
"""
from __future__ import annotations

from app.agent.api.utils import _sync_governed_state_from_review_outcome
from app.agent.state.models import (
    DerivedState,
    EvidenceState,
    GovernedSessionState,
    NormalizedParameter,
    NormalizedState,
)
from app.agent.state.persistence import (
    _with_decision_basis_hash,
    compute_decision_basis_hash,
)


def _hashable_state() -> GovernedSessionState:
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


def test_with_decision_basis_hash_sets_hash_only() -> None:
    state = _hashable_state()
    expected_hash = compute_decision_basis_hash(state)

    result = _with_decision_basis_hash(state)

    assert result.decision.decision_basis_hash == expected_hash
    # Nothing else on the decision layer changes.
    assert result.decision.model_copy(
        update={"decision_basis_hash": None}
    ) == state.decision.model_copy(update={"decision_basis_hash": None})


def test_sync_governed_state_review_outcome_admissible() -> None:
    result = _sync_governed_state_from_review_outcome(
        GovernedSessionState(),
        case_state={"governance_state": {"rfq_admissibility": "ready"}, "rfq_state": {}},
        sealing_state={},
    )
    assert result.governance.rfq_admissible is True


def test_sync_governed_state_review_outcome_inadmissible() -> None:
    result = _sync_governed_state_from_review_outcome(
        GovernedSessionState(),
        case_state={
            "governance_state": {"rfq_admissibility": "inadmissible"},
            "rfq_state": {},
        },
        sealing_state={},
    )
    assert result.governance.rfq_admissible is False
