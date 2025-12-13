import app.langgraph_v2.sealai_graph_v2  # noqa: F401

from app.langgraph_v2.nodes.nodes_supervisor import supervisor_logic_node, supervisor_route
from app.langgraph_v2.state import Intent, SealAIState, TechnicalParameters


def test_supervisor_route_design_ready_false_go_false_intermediate() -> None:
    state = SealAIState(
        intent=Intent(goal="design_recommendation"),
        recommendation_ready=False,
        recommendation_go=False,
    )
    assert supervisor_route(state) == "intermediate"


def test_supervisor_route_design_ready_true_go_false_confirm() -> None:
    state = SealAIState(
        intent=Intent(goal="design_recommendation"),
        recommendation_ready=True,
        recommendation_go=False,
    )
    assert supervisor_route(state) == "confirm"


def test_supervisor_route_design_ready_true_go_true_design_flow() -> None:
    state = SealAIState(
        intent=Intent(goal="design_recommendation"),
        recommendation_ready=True,
        recommendation_go=True,
    )
    assert supervisor_route(state) == "design_flow"


def test_supervisor_logic_node_sets_coverage_from_missing_params() -> None:
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
