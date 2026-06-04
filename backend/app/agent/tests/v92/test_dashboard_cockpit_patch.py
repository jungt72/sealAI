"""Patch 4 tests — CockpitPatch projection additions on the dashboard contract.

active_question (from existing PendingQuestion), conflicts (from existing
ConflictRef), knowledge_notes, visual_candidates, sketch_candidates. Additive
projection; existing fields stay intact. Empty state → empty/None (no crash).
"""

from __future__ import annotations

from app.agent.state.models import (
    ConflictRef,
    GovernedSessionState,
    PendingQuestion,
)
from app.agent.v92.dashboard_contract import build_v92_dashboard_contract


def _build(state: GovernedSessionState | None):
    return build_v92_dashboard_contract(
        state, turn_id="t1", route="engineering_case_update", case_id="case-1"
    )


def test_empty_state_yields_empty_cockpit_patch_fields() -> None:
    contract = _build(GovernedSessionState())
    assert contract.active_question is None
    assert contract.conflicts == []
    assert contract.knowledge_notes == []
    assert contract.visual_candidates == []
    assert contract.sketch_candidates == []


def test_none_state_is_safe() -> None:
    contract = _build(None)
    assert contract.active_question is None
    assert contract.conflicts == []


def test_active_question_projected_from_pending_question() -> None:
    state = GovernedSessionState()
    state.pending_question = PendingQuestion(
        target_field="shaft_surface_condition",
        expected_answer_type="enum",
        question_text="Siehst du auf der Welle eine Rille?",
        status="open",
    )
    contract = _build(state)
    assert contract.active_question == {
        "field": "shaft_surface_condition",
        "question": "Siehst du auf der Welle eine Rille?",
        "expected_answer_type": "enum",
        "status": "open",
    }


def test_answered_pending_question_is_not_active() -> None:
    state = GovernedSessionState()
    state.pending_question = PendingQuestion(
        target_field="speed_rpm",
        expected_answer_type="number",
        question_text="Welche Drehzahl?",
        status="answered",
    )
    assert _build(state).active_question is None


def test_conflicts_projected_from_normalized_conflicts() -> None:
    state = GovernedSessionState()
    state.normalized.conflicts = [
        ConflictRef(
            field_name="temperature_operating_c",
            description="90 vs 190 °C",
            severity="warning",
        )
    ]
    contract = _build(state)
    assert contract.conflicts == [
        {
            "field_name": "temperature_operating_c",
            "description": "90 vs 190 °C",
            "severity": "warning",
        }
    ]


def test_knowledge_notes_read_tolerantly_from_context() -> None:
    state = GovernedSessionState()
    state.governed_answer_context = {
        "knowledge_notes": [{"label": "FKM prüfen", "status": "rag_supported"}]
    }
    contract = _build(state)
    assert contract.knowledge_notes == [
        {"label": "FKM prüfen", "status": "rag_supported"}
    ]


def test_existing_fields_remain_intact() -> None:
    # Sanity: the additive change does not drop pre-existing projection fields.
    contract = _build(GovernedSessionState())
    assert contract.readiness_band  # present
    assert isinstance(contract.current_facts, list)
    assert isinstance(contract.review_status, dict)
    assert contract.allowed_next_actions  # defaulted
