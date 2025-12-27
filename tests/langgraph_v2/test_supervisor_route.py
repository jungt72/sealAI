from app.langgraph_v2.nodes.nodes_supervisor import supervisor_route
from app.langgraph_v2.state.sealai_state import Intent, SealAIState


def _build_state(goal: str, *, ready: bool = False, go: bool = False) -> SealAIState:
    return SealAIState(
        intent=Intent(goal=goal),
        recommendation_ready=ready,
        recommendation_go=go,
    )


def test_design_recommendation_not_ready_routes_to_intermediate() -> None:
    state = _build_state("design_recommendation", ready=False, go=False)
    assert supervisor_route(state) == "intermediate"


def test_design_recommendation_ready_without_go_routes_to_confirm() -> None:
    state = _build_state("design_recommendation", ready=True, go=False)
    assert supervisor_route(state) == "confirm"


def test_design_recommendation_ready_with_go_routes_to_design_flow() -> None:
    state = _build_state("design_recommendation", ready=True, go=True)
    assert supervisor_route(state) == "design_flow"


def test_other_goals_route_to_respective_subgraphs() -> None:
    assert supervisor_route(_build_state("explanation_or_comparison")) == "comparison"
    assert supervisor_route(_build_state("troubleshooting_leakage")) == "troubleshooting"
    assert supervisor_route(_build_state("out_of_scope")) == "out_of_scope"
    assert supervisor_route(_build_state("smalltalk")) == "smalltalk"


def test_no_intent_defaults_to_smalltalk() -> None:
    state = SealAIState()
    assert supervisor_route(state) == "smalltalk"
