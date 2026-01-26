import pytest

@pytest.mark.anyio
async def test_graph_has_ask_user_route():
    from app.langgraph_v2.sealai_graph_v2 import get_sealai_graph_v2
    cg = await get_sealai_graph_v2()
    edges = list(cg.get_graph().edges)
    assert any(
        e.source == "supervisor_policy_node"
        and e.target == "await_user_input_node"
        and str(e.data) == "ASK_USER"
        for e in edges
    )
