import pytest

from app.langgraph_v2.nodes.nodes_supervisor import ACTION_REQUIRE_CONFIRM
from app.langgraph_v2.tests.graph_contract_spec import MANDATORY_EDGES, edge_tuples


@pytest.mark.anyio
async def test_hitl_wiring_present():
    from app.langgraph_v2.sealai_graph_v2 import get_sealai_graph_v2

    cg = await get_sealai_graph_v2()
    raw_edges = list(cg.get_graph().edges)
    edges = edge_tuples(raw_edges)

    assert ("__start__", "policy_preflight_node") in edges
    assert ("policy_preflight_node", "resume_router_node") in edges
    assert ("assumption_lock_node", "supervisor_policy_node") in edges
    assert ("design_worker", "assumption_lock_node") in edges
    assert ("calc_worker", "assumption_lock_node") in edges
    assert MANDATORY_EDGES.issuperset(
        {
            ("__start__", "policy_preflight_node"),
            ("policy_preflight_node", "resume_router_node"),
            ("assumption_lock_node", "supervisor_policy_node"),
            ("design_worker", "assumption_lock_node"),
            ("calc_worker", "assumption_lock_node"),
        }
    )

    # confirm checkpoint exists and ends
    assert ("supervisor_policy_node", "confirm_checkpoint_node") in edges
    assert any(
        e.source == "supervisor_policy_node"
        and e.target == "confirm_checkpoint_node"
        and str(e.data) == ACTION_REQUIRE_CONFIRM
        for e in raw_edges
    )

    # policy finalize variants are accepted and now route through challenger -> policy gate
    assert any(
        e.source == "supervisor_policy_node"
        and e.target == "challenger_feedback_node"
        and str(e.data).lower() == "finalize"
        for e in raw_edges
    ) or any(
        e.source == "supervisor_policy_node"
        and e.target == "challenger_feedback_node"
        and str(e.data).upper() == "FINALIZE"
        for e in raw_edges
    )
    assert ("confirm_checkpoint_node", "__end__") in edges

    # spokes return via assumption lock before policy
    assert not (("design_worker", "autonomous_supervisor_node") in edges)
    assert not (("calc_worker", "autonomous_supervisor_node") in edges)
