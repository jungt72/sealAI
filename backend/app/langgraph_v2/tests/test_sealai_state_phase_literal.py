from app.langgraph_v2.state import SealAIState


def test_sealai_state_accepts_supervisor_phase() -> None:
    state = SealAIState(phase="supervisor")
    assert state.phase == "supervisor"


def test_sealai_state_accepts_panel_phase() -> None:
    # "panel" is emitted by panel_* nodes in app.langgraph_v2.nodes.nodes_supervisor.
    state = SealAIState(phase="panel")
    assert state.phase == "panel"
