import pytest
from langchain_core.messages import HumanMessage
from app.langgraph_v2.state.sealai_state import SealAIState

@pytest.mark.anyio
async def test_hitl_reject_routes_to_final_answer():
    from app.langgraph_v2.sealai_graph_v2 import get_sealai_graph_v2

    cg = await get_sealai_graph_v2()

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
    config = {"configurable": {"thread_id": "thr", "checkpoint_ns": "sealai:v2:test"}}

    out = await cg.ainvoke(s, config=config)
    d = out.model_dump() if hasattr(out, "model_dump") else dict(out)

    assert d.get("awaiting_user_confirmation") is False
    assert d.get("confirm_decision") is None
    assert (d.get("confirm_status") or "") == "resolved"
    assert d.get("last_node") in ("final_answer_node", "confirm_reject_node")
