import pytest

@pytest.mark.anyio
async def test_no_product_explainer_loop_to_supervisor():
    from app.langgraph_v2.sealai_graph_v2 import get_sealai_graph_v2

    cg = await get_sealai_graph_v2()
    g = cg.get_graph()
    edges = list(g.edges)

    assert not any(
        e.source == "product_explainer_node" and e.target == "autonomous_supervisor_node"
        for e in edges
    ), "product_explainer_node must not loop back to autonomous_supervisor_node"

    assert any(
        e.source == "product_explainer_node" and e.target == "final_answer_node"
        for e in edges
    ), "product_explainer_node should go to final_answer_node"
