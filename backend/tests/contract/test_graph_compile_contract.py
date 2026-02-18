import os


def test_langgraph_v2_graph_compiles_and_registers_expected_nodes() -> None:
    os.environ.setdefault("OPENAI_API_KEY", "dummy")
    os.environ.setdefault("CHECKPOINTER_BACKEND", "memory")

    from langgraph.checkpoint.memory import MemorySaver

    from app.langgraph_v2.sealai_graph_v2 import create_sealai_graph_v2

    graph = create_sealai_graph_v2(MemorySaver(), require_async=False)
    assert graph is not None

    runnable_graph = graph.get_graph()
    node_names = set(runnable_graph.nodes)

    expected_nodes = {
        "__start__",
        "frontdoor_discovery_node",
        "supervisor_policy_node",
        "discovery_intake_node",
        "discovery_summarize_node",
        "calc_worker",
        "design_worker",
        "profile_agent_node",
        "validation_agent_node",
        "product_explainer_node",
        "material_comparison_node",
        "rag_support_node",
        "confirm_checkpoint_node",
        "resume_router_node",
        "final_answer_node",
        "__end__",
    }

    missing = expected_nodes - node_names
    assert not missing, f"Graph is missing expected nodes: {sorted(missing)}"
