import app.langgraph_v2.sealai_graph_v2  # noqa: F401

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

from app.langgraph_v2.nodes.nodes_supervisor import supervisor_logic_node
from app.langgraph_v2.sealai_graph_v2 import _merge_deterministic_router, _reducer_router, create_sealai_graph_v2
from app.langgraph_v2.nodes.route_after_frontdoor import route_after_frontdoor_node
from app.langgraph_v2.state import Intent, SealAIState, TechnicalParameters


def test_graph_entry_routes_to_kb_lookup_or_smalltalk() -> None:
    """Frontdoor should route through dedicated route_after_frontdoor node."""
    builder = create_sealai_graph_v2(checkpointer=MemorySaver(), store=InMemoryStore(), return_builder=True)
    
    # In V8, frontdoor_discovery_node uses a direct edge to route_after_frontdoor
    entry_targets = {target for source, target in builder.edges if source == "frontdoor_discovery_node"}
    assert "route_after_frontdoor" in entry_targets

    route_targets = {target for source, target in builder.edges if source == "frontdoor_parallel_fanout_node"}
    assert "node_factcard_lookup_parallel" in route_targets
    assert "node_compound_filter_parallel" in route_targets

    # supervisor_policy_node is reached via node_merge_deterministic
    mapping = {}
    for source, branches in builder.branches.items():
        if source == "node_merge_deterministic":
            for branch in branches.values():
                mapping.update(branch.ends)
    assert mapping["supervisor"] == "supervisor_policy_node"


def test_graph_parallel_worker_edges_route_to_reducer() -> None:
    builder = create_sealai_graph_v2(checkpointer=MemorySaver(), store=InMemoryStore(), return_builder=True)
    node_ids = set(builder.nodes.keys())
    assert "calculator_agent" in node_ids
    assert "pricing_agent" in node_ids
    assert "safety_agent" in node_ids
    assert "human_review_node" in node_ids
    assert "troubleshooting_wizard_node" in node_ids


def test_graph_rfq_trigger_routes_via_validator_before_procurement() -> None:
    builder = create_sealai_graph_v2(checkpointer=MemorySaver(), store=InMemoryStore(), return_builder=True)
    assert "rfq_validator_node" in builder.nodes

    # Check conditional edges from rfq_validator_node
    mapping = {}
    for source, branches in builder.branches.items():
        if source == "rfq_validator_node":
            for branch in branches.values():
                mapping.update(branch.ends)
    
    assert mapping["ready"] == "node_p5_procurement"


def test_graph_reducer_routes_to_hitl_or_final() -> None:
    assert _reducer_router(SealAIState(requires_human_review=True)) == "human_review"
    assert _reducer_router(SealAIState(requires_human_review=False)) == "standard"
    assert _reducer_router(
        SealAIState(requires_human_review=False, intent=Intent(goal="explanation_or_comparison"))
    ) == "conversational_rag"


def test_route_after_frontdoor_prioritizes_task_intents_over_social_opening() -> None:
    state = SealAIState(
        intent=Intent(goal="design_recommendation"),
        flags={
            "frontdoor_bypass_supervisor": True,
            "frontdoor_social_opening": True,
            "frontdoor_task_intents": ["engineering_calculation"],
        }
    )
    assert route_after_frontdoor_node(state).goto == "node_p1_context"


def test_route_after_frontdoor_routes_social_opening_without_task_intents_to_smalltalk() -> None:
    state = SealAIState(
        intent=Intent(goal="smalltalk"),
        flags={
            "frontdoor_social_opening": True,
            "frontdoor_task_intents": [],
            "frontdoor_bypass_supervisor": False,
        }
    )
    assert route_after_frontdoor_node(state).goto == "smalltalk_node"


def test_route_after_frontdoor_routes_comparison_goal_to_supervisor() -> None:
    state = SealAIState(
        intent=Intent(goal="explanation_or_comparison"),
        flags={
            "frontdoor_intent_category": "GENERAL_KNOWLEDGE",
            "frontdoor_social_opening": False,
            "frontdoor_task_intents": ["general_knowledge"],
        }
    )
    assert route_after_frontdoor_node(state).goto == "supervisor_policy_node"


def test_route_after_frontdoor_routes_troubleshooting_to_wizard() -> None:
    state = SealAIState(
        intent=Intent(goal="troubleshooting_leakage"),
        flags={
            "frontdoor_intent_category": "ENGINEERING_CALCULATION",
            "frontdoor_social_opening": False,
            "frontdoor_task_intents": ["troubleshooting_leakage"],
        },
    )
    assert route_after_frontdoor_node(state).goto == "troubleshooting_wizard_node"


def test_route_after_frontdoor_prioritizes_resume_session_over_commercial_fast_path() -> None:
    state = SealAIState(
        intent=Intent(goal="design_recommendation"),
        router_classification="resume",
        awaiting_user_confirmation=True,
        flags={
            "frontdoor_intent_category": "COMMERCIAL",
            "frontdoor_task_intents": ["commercial"],
            "needs_pricing": True,
        },
        messages=[HumanMessage(content="Wie sind eure Preise fuer 100 Stueck?")],
    )
    assert route_after_frontdoor_node(state).goto == "node_p1_context"


def test_route_after_frontdoor_keeps_commercial_fast_path_for_non_resume_sessions() -> None:
    state = SealAIState(
        intent=Intent(goal="design_recommendation"),
        flags={
            "frontdoor_intent_category": "COMMERCIAL",
            "frontdoor_task_intents": ["commercial"],
            "needs_pricing": True,
        },
    )
    assert route_after_frontdoor_node(state).goto == "frontdoor_parallel_fanout_node"


def test_route_after_frontdoor_routes_extreme_temp_suitability_to_kb_fast_path() -> None:
    state = SealAIState(
        intent=Intent(goal="design_recommendation"),
        flags={
            "frontdoor_intent_category": "ENGINEERING_CALCULATION",
            "frontdoor_social_opening": False,
            "frontdoor_task_intents": ["engineering_calculation"],
        },
        messages=[HumanMessage(content="Ist PTFE bei -200°C noch einsetzbar?")],
    )
    assert route_after_frontdoor_node(state).goto == "frontdoor_parallel_fanout_node"


def test_graph_troubleshooting_wizard_completion_routes_to_conversational_rag() -> None:
    builder = create_sealai_graph_v2(checkpointer=MemorySaver(), store=InMemoryStore(), return_builder=True)
    
    mapping = {}
    for source, branches in builder.branches.items():
        if source == "troubleshooting_wizard_node":
            for branch in branches.values():
                mapping.update(branch.ends)
                
    assert mapping["complete"] == "conversational_rag_node"
    assert "final_answer_node" not in mapping.values()


def test_supervisor_policy_node_sets_coverage_from_missing_params() -> None:
    params = TechnicalParameters(
        medium="Hydraulikoel",
        pressure_bar=10,
        temperature_C=80,
        shaft_diameter=50,
        # speed_rpm missing -> 4/5 coverage == 0.8 => ready True
    )
    state = SealAIState(
        intent=Intent(goal="design_recommendation"),
        parameters=params,
    )
    patch = supervisor_logic_node(state)
    assert patch["missing_params"] == ["speed_rpm"]
    assert patch["coverage_gaps"] == ["speed_rpm"]
    assert patch["coverage_score"] == 0.8
    assert patch["recommendation_ready"] is True


def test_merge_deterministic_router_forces_supervisor_for_rfq_requests() -> None:
    state = SealAIState(
        kb_factcard_result={"deterministic": True},
        messages=[HumanMessage(content="Bitte RFQ/Lastenheft erstellen.")],
    )
    assert _merge_deterministic_router(state) == "supervisor"


def test_merge_deterministic_router_keeps_deterministic_for_non_rfq_requests() -> None:
    state = SealAIState(
        kb_factcard_result={"deterministic": True},
        messages=[HumanMessage(content="Wie hoch ist die Temperaturgrenze von PTFE?")],
    )
    assert _merge_deterministic_router(state) == "deterministic"
