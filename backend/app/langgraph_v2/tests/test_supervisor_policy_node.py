import app.langgraph_v2.sealai_graph_v2  # noqa: F401

from app.langgraph_v2.nodes.nodes_supervisor import (
    ACTION_ASK_USER,
    ACTION_FINALIZE,
    ACTION_RUN_COMPARISON,
    ACTION_RUN_PANEL_CALC,
    ACTION_RUN_PANEL_MATERIAL,
    ACTION_RUN_PANEL_NORMS_RAG,
    supervisor_policy_node,
)
from app.langgraph_v2.state import Budget, CalcResults, CandidateItem, Intent, SealAIState, WorkingMemory


def test_supervisor_policy_budget_exhausted_finalizes() -> None:
    state = SealAIState(budget=Budget(remaining=0, spent=3))
    patch = supervisor_policy_node(state)
    assert patch["next_action"] == ACTION_FINALIZE


def test_supervisor_policy_missing_params_asks_user() -> None:
    state = SealAIState(missing_params=["pressure_bar"])
    patch = supervisor_policy_node(state)
    assert patch["next_action"] == ACTION_ASK_USER


def test_supervisor_policy_contradictions_run_norms_panel() -> None:
    candidates = [
        CandidateItem(kind="material", value="NBR", confidence=0.7),
        CandidateItem(kind="material", value="FKM", confidence=0.65),
    ]
    state = SealAIState(
        candidates=candidates,
        material_choice={"material": "NBR"},
        calc_results=CalcResults(safety_factor=1.5),
        calc_results_ok=True,
        confidence=0.3,
    )
    patch = supervisor_policy_node(state)
    assert patch["next_action"] == ACTION_RUN_PANEL_NORMS_RAG


def test_supervisor_policy_high_confidence_finalizes() -> None:
    state = SealAIState(confidence=0.85)
    patch = supervisor_policy_node(state)
    assert patch["next_action"] == ACTION_FINALIZE


def test_supervisor_policy_calc_then_material() -> None:
    state_calc = SealAIState()
    patch_calc = supervisor_policy_node(state_calc)
    assert patch_calc["next_action"] == ACTION_RUN_PANEL_CALC

    state_material = SealAIState(
        calc_results=CalcResults(safety_factor=1.4),
        calc_results_ok=True,
        material_choice={},
    )
    patch_material = supervisor_policy_node(state_material)
    assert patch_material["next_action"] == ACTION_RUN_PANEL_MATERIAL


def test_supervisor_policy_comparison_runs_comparison_first() -> None:
    state = SealAIState(
        intent=Intent(goal="explanation_or_comparison"),
        requires_rag=True,
    )
    patch = supervisor_policy_node(state)
    assert patch["next_action"] == ACTION_RUN_COMPARISON


def test_supervisor_policy_comparison_runs_rag_after_comparison() -> None:
    wm = WorkingMemory(comparison_notes={"comparison_text": "A vs B"})
    state = SealAIState(
        intent=Intent(goal="explanation_or_comparison"),
        requires_rag=True,
        working_memory=wm,
    )
    patch = supervisor_policy_node(state)
    assert patch["next_action"] == ACTION_RUN_PANEL_NORMS_RAG


def test_supervisor_policy_comparison_finalizes_without_rag() -> None:
    wm = WorkingMemory(comparison_notes={"comparison_text": "A vs B", "rag_context": "ctx"})
    state = SealAIState(
        intent=Intent(goal="explanation_or_comparison"),
        requires_rag=False,
        working_memory=wm,
    )
    patch = supervisor_policy_node(state)
    assert patch["next_action"] == ACTION_FINALIZE
