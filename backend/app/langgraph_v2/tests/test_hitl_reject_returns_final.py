import pytest
from langchain_core.messages import HumanMessage
from app.langgraph_v2.nodes.nodes_resume import confirm_reject_node
from app.langgraph_v2.state.sealai_state import SealAIState

@pytest.mark.anyio
async def test_hitl_reject_routes_to_final_answer():
    s = SealAIState(
        tenant_id="t",
        user_id="u",
        thread_id="thr",
        messages=[HumanMessage(content="OK")],
        awaiting_user_confirmation=True,
        confirm_decision="reject",
        pending_action="knowledge",
        next_action=None,
    )
    d = confirm_reject_node(s)

    assert d.get("awaiting_user_confirmation") is False
    assert d.get("confirm_decision") is None
    assert (d.get("confirm_status") or "") == "resolved"
    assert d.get("last_node") in ("final_answer_node", "confirm_reject_node")
