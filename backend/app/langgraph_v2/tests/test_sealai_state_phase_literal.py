from app.langgraph_v2.state import SealAIState


def test_sealai_state_accepts_supervisor_phase() -> None:
    state = SealAIState(phase="supervisor")
    assert state.phase == "supervisor"


def test_sealai_state_accepts_panel_phase() -> None:
    # "panel" is emitted by panel_* nodes in app.langgraph_v2.nodes.nodes_supervisor.
    state = SealAIState(phase="panel")
    assert state.phase == "panel"


def test_sealai_state_accepts_aggregation_phase() -> None:
    # "aggregation" is emitted by backend/app/langgraph_v2/nodes/nodes_supervisor.py (aggregator_node).
    state = SealAIState(phase="aggregation")
    assert state.phase == "aggregation"
