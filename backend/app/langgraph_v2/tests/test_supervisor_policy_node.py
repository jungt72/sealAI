import app.langgraph_v2.sealai_graph_v2  # noqa: F401

from langgraph.types import Send

from app.langgraph_v2.nodes.nodes_supervisor import (
    ACTION_FINALIZE,
    ACTION_RUN_COMPARISON,
    ACTION_RUN_TROUBLESHOOTING,
    supervisor_policy_node,
)
from app.langgraph_v2.state import Budget, CalcResults, CandidateItem, Intent, SealAIState, WorkingMemory


def test_supervisor_policy_budget_exhausted_finalizes() -> None:
    state = SealAIState(budget=Budget(remaining=0, spent=3))
    cmd = supervisor_policy_node(state)
    assert cmd.update["next_action"] == "MAP_REDUCE_PARALLEL"
    assert isinstance(cmd.goto, list)
    assert any(isinstance(item, Send) and item.node == "calculator_agent" for item in cmd.goto)


def test_supervisor_policy_missing_params_asks_user() -> None:
    state = SealAIState(missing_params=["pressure_bar"])
    cmd = supervisor_policy_node(state)
    assert cmd.update["next_action"] == "MAP_REDUCE_PARALLEL"
    assert isinstance(cmd.goto, list)
    assert any(isinstance(item, Send) and item.node == "calculator_agent" for item in cmd.goto)


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
    cmd = supervisor_policy_node(state)
    assert cmd.update["next_action"] == ACTION_FINALIZE
    assert cmd.goto == "final_answer_node"


def test_supervisor_policy_high_confidence_finalizes() -> None:
    state = SealAIState(confidence=0.85)
    cmd = supervisor_policy_node(state)
    assert cmd.update["next_action"] == "MAP_REDUCE_PARALLEL"
    assert isinstance(cmd.goto, list)
    assert any(isinstance(item, Send) and item.node == "calculator_agent" for item in cmd.goto)


def test_supervisor_policy_calc_then_material() -> None:
    state_calc = SealAIState()
    cmd_calc = supervisor_policy_node(state_calc)
    assert cmd_calc.update["next_action"] == "MAP_REDUCE_PARALLEL"
    assert isinstance(cmd_calc.goto, list)
    assert any(isinstance(item, Send) and item.node == "calculator_agent" for item in cmd_calc.goto)

    state_material = SealAIState(
        calc_results=CalcResults(safety_factor=1.4),
        calc_results_ok=True,
        material_choice={},
    )
    cmd_material = supervisor_policy_node(state_material)
    assert cmd_material.update["next_action"] == ACTION_FINALIZE
    assert cmd_material.goto == "final_answer_node"


def test_supervisor_policy_comparison_runs_comparison_first() -> None:
    state = SealAIState(
        intent=Intent(goal="explanation_or_comparison"),
        requires_rag=True,
    )
    cmd = supervisor_policy_node(state)
    assert cmd.update["next_action"] == "MAP_REDUCE_PARALLEL"
    assert isinstance(cmd.goto, list)
    assert any(isinstance(item, Send) and item.node == "material_agent" for item in cmd.goto)


def test_supervisor_policy_comparison_runs_rag_after_comparison() -> None:
    wm = WorkingMemory(comparison_notes={"comparison_text": "A vs B"})
    state = SealAIState(
        intent=Intent(goal="explanation_or_comparison"),
        requires_rag=True,
        working_memory=wm,
    )
    cmd = supervisor_policy_node(state)
    assert cmd.update["next_action"] == "MAP_REDUCE_PARALLEL"
    assert isinstance(cmd.goto, list)
    assert any(isinstance(item, Send) and item.node == "material_agent" for item in cmd.goto)


def test_supervisor_policy_comparison_finalizes_without_rag() -> None:
    wm = WorkingMemory(comparison_notes={"comparison_text": "A vs B", "rag_context": "ctx"})
    state = SealAIState(
        intent=Intent(goal="explanation_or_comparison"),
        requires_rag=False,
        working_memory=wm,
    )
    cmd = supervisor_policy_node(state)
    assert cmd.update["next_action"] == ACTION_RUN_COMPARISON
    assert cmd.goto == "material_comparison_node"


def test_supervisor_policy_troubleshooting_routes_to_wizard() -> None:
    state = SealAIState(intent=Intent(goal="troubleshooting_leakage"), requires_rag=False)
    cmd = supervisor_policy_node(state)
    assert cmd.update["next_action"] == ACTION_RUN_TROUBLESHOOTING
    assert cmd.goto == "troubleshooting_wizard_node"
