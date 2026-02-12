from langchain_core.messages import HumanMessage

from app.langgraph_v2.nodes.nodes_supervisor import (
    ACTION_ASK_USER,
    ACTION_REQUIRE_CONFIRM,
    ACTION_RUN_KNOWLEDGE,
    ACTION_RUN_PANEL_NORMS_RAG,
    supervisor_policy_node,
)
from app.langgraph_v2.state import Intent, QuestionItem, SealAIState
from app.langgraph_v2.state import CalcResults


def test_supervisor_routes_material_query_to_knowledge_when_high_open_questions() -> None:
    state = SealAIState(
        intent=Intent(goal="design_recommendation"),
        open_questions=[
            QuestionItem(
                id="pressure_bar",
                question="Need pressure",
                reason="Required",
                priority="high",
                status="open",
                source="missing_params",
            )
        ],
        messages=[HumanMessage(content="PTFE compatibility for oil at 80C?")],
    )

    patch = supervisor_policy_node(state)

    assert patch["next_action"] == ACTION_RUN_KNOWLEDGE
    assert patch["next_action"] != ACTION_ASK_USER


def test_confirm_checkpoint_only_for_high_design_escalation() -> None:
    state = SealAIState(
        intent=Intent(goal="design_recommendation"),
        requires_rag=True,
        flags={"risk_level": "critical"},
        calc_results=CalcResults(safety_factor=1.2),
        calc_results_ok=True,
        material_choice={"material": "FKM"},
    )

    patch = supervisor_policy_node(state)

    assert patch["next_action"] == ACTION_REQUIRE_CONFIRM
    assert patch["pending_action"] == ACTION_RUN_PANEL_NORMS_RAG
