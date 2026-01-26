import pytest

@pytest.mark.anyio
async def test_hitl_wiring_present():
    from app.langgraph_v2.sealai_graph_v2 import get_sealai_graph_v2

    cg = await get_sealai_graph_v2()
    edges = list(cg.get_graph().edges)

    assert any(e.source == "__start__" and e.target == "policy_preflight_node" for e in edges)
    assert any(e.source == "policy_preflight_node" and e.target == "resume_router_node" for e in edges)
    assert any(e.source == "autonomous_supervisor_node" and e.target == "supervisor_policy_node" for e in edges)

    # confirm checkpoint exists and ends
    assert any(e.source == "supervisor_policy_node" and e.target == "confirm_checkpoint_node" for e in edges)

    # policy finalize variants are accepted and now route through challenger -> policy gate
    assert any(
        e.source == "supervisor_policy_node"
        and e.target == "challenger_feedback_node"
        and str(e.data).lower() == "finalize"
        for e in edges
    ) or any(
        e.source == "supervisor_policy_node"
        and e.target == "challenger_feedback_node"
        and str(e.data).upper() == "FINALIZE"
        for e in edges
    )
    assert any(e.source == "confirm_checkpoint_node" and e.target == "__end__" for e in edges)

    # spokes return to policy (not to supervisor)
    assert any(e.source == "design_worker" and e.target == "supervisor_policy_node" for e in edges)
    assert any(e.source == "calc_worker" and e.target == "supervisor_policy_node" for e in edges)
    assert not any(e.source == "design_worker" and e.target == "autonomous_supervisor_node" for e in edges)
    assert not any(e.source == "calc_worker" and e.target == "autonomous_supervisor_node" for e in edges)
