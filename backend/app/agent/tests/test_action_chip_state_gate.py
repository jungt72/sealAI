"""Patch 5 tests — Fast Path + Pending Slot + Action-Chip State Gate.

Covers Blueprint §7.5/§7.6 (tolerant pending-slot parse), §27.5 (no RAG / no
full graph on the fast path), §11.4/§4.5 (action-chip selection through the
State Gate with action_chip_answer provenance), and §12.6 (conflict degrades to
a field-level warning instead of blocking the whole case).
"""

from __future__ import annotations

from pathlib import Path

from app.agent.graph.action_chip_binding import (
    ACTION_CHIP_PROVENANCE,
    bind_action_chip_selection,
)
from app.agent.graph.slot_answer_binding import resolve_slot_answer_binding
from app.agent.state.models import (
    GovernedSessionState,
    ObservedExtraction,
    ObservedState,
    PendingQuestion,
)
from app.agent.state.reducers import (
    reduce_normalized_to_asserted,
    reduce_observed_to_normalized,
)


def _speed_question() -> PendingQuestion:
    return PendingQuestion(
        target_field="speed_rpm",
        expected_answer_type="rotational_speed_value",
        question_text="Welche Drehzahl liegt ungefähr an?",
        status="open",
    )


# --- Tolerant pending-slot parser (§7.5/§7.6) ------------------------------


def test_tolerant_parser_binds_jo_ca_3000_as_approximate() -> None:
    binding = resolve_slot_answer_binding(
        pending_question=_speed_question(), message="jo ca 3000", turn_index=1
    )
    assert binding is not None
    assert binding.target_field == "speed_rpm"
    assert binding.normalized_value == 3000.0
    assert binding.approximate is True


def test_clean_numeric_answer_is_unchanged_and_not_approximate() -> None:
    binding = resolve_slot_answer_binding(
        pending_question=_speed_question(), message="3000", turn_index=1
    )
    assert binding is not None
    assert binding.normalized_value == 3000.0
    assert binding.approximate is False


def test_tolerant_parser_handles_unit_and_filler() -> None:
    binding = resolve_slot_answer_binding(
        pending_question=PendingQuestion(
            target_field="temperature_c",
            expected_answer_type="temperature_value",
            status="open",
        ),
        message="so um die 90 grad",
        turn_index=1,
    )
    assert binding is not None
    assert binding.target_field == "temperature_c"
    assert binding.normalized_value == 90.0
    assert binding.approximate is True


def test_tolerant_parser_refuses_strong_new_request() -> None:
    # A new request that happens to contain a number must not bind as a slot.
    binding = resolve_slot_answer_binding(
        pending_question=_speed_question(),
        message="ich brauche 3000 Stück",
        turn_index=1,
    )
    assert binding is None


# --- Fast path mutates the field through the State Gate (§7.5) --------------


def test_pending_slot_answer_mutates_target_field_via_state_gate() -> None:
    binding = resolve_slot_answer_binding(
        pending_question=_speed_question(), message="jo ca 3000", turn_index=1
    )
    assert binding is not None
    # The binding feeds the deterministic State Gate (reducers) as user truth.
    state = bind_action_chip_selection(
        GovernedSessionState(),
        field=binding.target_field,
        value=binding.normalized_value,
        turn_index=1,
    )
    assert "speed_rpm" in state.normalized.parameters
    assert state.normalized.parameters["speed_rpm"].value == 3000.0


# --- No RAG / no full graph on the fast path (§27.5) ------------------------


def test_fast_path_modules_do_not_depend_on_rag_or_full_graph() -> None:
    import app.agent.graph.action_chip_binding as acb
    import app.agent.graph.slot_answer_binding as sab
    import app.agent.state.reducers as reducers

    source = "\n".join(
        Path(module.__file__).read_text(encoding="utf-8")
        for module in (sab, acb, reducers)
    ).lower()
    assert "services.rag" not in source
    assert "rag_orchestrator" not in source
    assert "langgraph" not in source
    assert "graph.topology" not in source


def test_fast_path_runs_without_invoking_rag(monkeypatch) -> None:
    # If any RAG retrieval were touched on the fast path, this sentinel fires.
    calls: list[str] = []
    import app.services.rag.rag_orchestrator as rag_orchestrator

    for attr in ("hybrid_retrieve", "retrieve"):
        if hasattr(rag_orchestrator, attr):
            monkeypatch.setattr(
                rag_orchestrator,
                attr,
                lambda *a, **k: calls.append("rag"),  # noqa: ARG005
                raising=False,
            )

    binding = resolve_slot_answer_binding(
        pending_question=_speed_question(), message="jo ca 3000", turn_index=1
    )
    state = bind_action_chip_selection(
        GovernedSessionState(), field="speed_rpm", value=binding.normalized_value, turn_index=1
    )
    assert state.normalized.parameters["speed_rpm"].value == 3000.0
    assert calls == []


# --- Action-chip selection through the State Gate (§11.4) -------------------


def test_action_chip_selection_mutates_field_with_provenance() -> None:
    state = bind_action_chip_selection(
        GovernedSessionState(), field="speed_rpm", value=1500, turn_index=2
    )
    param = state.normalized.parameters.get("speed_rpm")
    assert param is not None
    assert param.value == 1500
    assert param.provenance == ACTION_CHIP_PROVENANCE
    assert param.case_field is not None
    assert param.case_field.provenance == ACTION_CHIP_PROVENANCE


def test_action_chip_empty_field_is_noop() -> None:
    state = GovernedSessionState()
    assert bind_action_chip_selection(state, field="", value="x") is state


# --- State Gate degradation: conflict ≠ case blockade (§12.6) ---------------


def test_field_conflict_degrades_without_blocking_other_fields() -> None:
    observed = ObservedState(
        raw_extractions=[
            ObservedExtraction(field_name="temperature_c", raw_value=90, source="llm", turn_index=1),
            ObservedExtraction(field_name="temperature_c", raw_value=190, source="llm", turn_index=1),
            ObservedExtraction(field_name="speed_rpm", raw_value=1500, source="llm", turn_index=1),
        ]
    )
    normalized = reduce_observed_to_normalized(observed)

    # Conflict is recorded as a field-level warning, not a hard block.
    assert normalized.conflicts, "expected a conflict ref for temperature_c"
    temp_conflict = next(c for c in normalized.conflicts if c.field_name == "temperature_c")
    assert temp_conflict.severity == "warning"

    # The rest of the case stays usable: the clean field still normalizes.
    assert "speed_rpm" in normalized.parameters
    assert normalized.parameters["speed_rpm"].value == 1500

    # And it can still be asserted (case is not globally blocked).
    asserted = reduce_normalized_to_asserted(normalized)
    assert "speed_rpm" in asserted.assertions
