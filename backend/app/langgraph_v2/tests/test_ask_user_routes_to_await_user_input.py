import pytest

@pytest.mark.anyio
async def test_graph_has_ask_user_route_to_await():
    from app.langgraph_v2.sealai_graph_v2 import get_sealai_graph_v2
    cg = await get_sealai_graph_v2()
    edges = list(cg.get_graph().edges)

    # We accept that some versions store label in e.data differently.
    assert any(
        e.source == "supervisor_policy_node"
        and e.target == "await_user_input_node"
        for e in edges
    ), "Expected an edge supervisor_policy_node -> await_user_input_node"

    assert any(
        e.source == "await_user_input_node" and e.target == "__end__"
        for e in edges
    ), "Expected await_user_input_node -> __end__"
