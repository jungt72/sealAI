import pytest
from langchain_core.messages import HumanMessage
from app.langgraph_v2.state.sealai_state import SealAIState

@pytest.mark.anyio
async def test_supervisor_routes_ptfe_question_to_knowledge():
    from app.langgraph_v2.nodes.nodes_supervisor import supervisor_policy_node, ACTION_RUN_KNOWLEDGE

    s = SealAIState(
        tenant_id="t",
        user_id="u",
        thread_id="thr",
        messages=[HumanMessage(content="Welche Einsatzgrenzen hat PTFE bezüglich Temperatur und Medienbeständigkeit?")],
    )
    patch = supervisor_policy_node(s)
    assert patch.get("next_action") == ACTION_RUN_KNOWLEDGE
