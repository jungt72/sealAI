import pytest

from app.langgraph_v2.nodes.nodes_supervisor import (
    ACTION_RUN_KNOWLEDGE,
    ACTION_RUN_PANEL_NORMS_RAG,
    ACTION_RUN_TROUBLESHOOTING,
    ACTION_RUN_PANEL_CALC,
    ACTION_RUN_PANEL_MATERIAL,
    supervisor_policy_node,
)
from app.langgraph_v2.state import CalcResults, Intent, SealAIState, WorkingMemory


@pytest.mark.parametrize(
    "state, expected_action",
    [
        (
            SealAIState(
                intent=Intent(goal="design_recommendation", key="knowledge_material", knowledge_type="material"),
                calc_results=CalcResults(safety_factor=1.2),
                calc_results_ok=True,
                material_choice={"material": "FKM"},
            ),
            ACTION_RUN_KNOWLEDGE,
        ),
        (
            SealAIState(
                intent=Intent(goal="design_recommendation", key="knowledge_material", knowledge_type="material"),
                calc_results=None,
                calc_results_ok=False,
            ),
            ACTION_RUN_PANEL_CALC,
        ),
        (
            SealAIState(
                intent=Intent(goal="design_recommendation", key="knowledge_material", knowledge_type="material"),
                calc_results=CalcResults(safety_factor=1.2),
                calc_results_ok=True,
                material_choice={},
            ),
            ACTION_RUN_PANEL_MATERIAL,
        ),
        (
            SealAIState(
                intent=Intent(goal="design_recommendation", key="knowledge_lifetime", knowledge_type="lifetime"),
                calc_results=CalcResults(safety_factor=1.2),
                calc_results_ok=True,
                material_choice={"material": "FKM"},
            ),
            ACTION_RUN_KNOWLEDGE,
        ),
        (
            SealAIState(
                intent=Intent(goal="design_recommendation", key="knowledge_norms", knowledge_type="norms"),
                calc_results=CalcResults(safety_factor=1.2),
                calc_results_ok=True,
                material_choice={"material": "FKM"},
                confirmed_actions=["RUN_PANEL_NORMS_RAG"],
            ),
            ACTION_RUN_PANEL_NORMS_RAG,
        ),
        (
            SealAIState(requires_rag=True, confirmed_actions=["RUN_PANEL_NORMS_RAG"]),
            ACTION_RUN_PANEL_NORMS_RAG,
        ),
        (
            SealAIState(needs_sources=True, confirmed_actions=["RUN_PANEL_NORMS_RAG"]),
            ACTION_RUN_PANEL_NORMS_RAG,
        ),
        (
            SealAIState(
                intent=Intent(goal="design_recommendation", key="knowledge_material", knowledge_type="material"),
                requires_rag=True,
                calc_results=CalcResults(safety_factor=1.2),
                calc_results_ok=True,
                material_choice={"material": "FKM"},
            ),
            ACTION_RUN_KNOWLEDGE,
        ),
        (
            SealAIState(intent=Intent(goal="troubleshooting_leakage")),
            ACTION_RUN_TROUBLESHOOTING,
        ),
        (
            SealAIState(intent=Intent(goal="design_recommendation")),
            ACTION_RUN_PANEL_CALC,
        ),
        (
            SealAIState(
                intent=Intent(goal="explanation_or_comparison"),
                requires_rag=True,
                working_memory=WorkingMemory(comparison_notes={"comparison_text": "A vs B"}),
                confirmed_actions=["RUN_PANEL_NORMS_RAG"],
            ),
            ACTION_RUN_PANEL_NORMS_RAG,
        ),
    ],
)
def test_supervisor_routing_matrix(state, expected_action):
    patch = supervisor_policy_node(state)
    assert patch["next_action"] == expected_action
