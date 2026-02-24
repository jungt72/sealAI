from app.langgraph_v2.nodes.reducer import reducer_node
from app.langgraph_v2.state import SealAIState


def test_reducer_sets_human_review_when_safety_severity_high() -> None:
    state = SealAIState(requires_human_review=False)
    results = [
        {
            "last_node": "safety_agent",
            "safety_review": {
                "severity": 4,
                "code": "SAFETY_CRITICAL_H2_APPLICATION",
            },
        }
    ]

    patch = reducer_node(state, results=results)
    assert patch["requires_human_review"] is True


def test_reducer_does_not_set_human_review_for_low_safety_severity() -> None:
    state = SealAIState(requires_human_review=False)
    results = [
        {
            "last_node": "safety_agent",
            "safety_review": {
                "severity": 2,
                "code": "LOW_RISK",
            },
        }
    ]

    patch = reducer_node(state, results=results)
    assert patch.get("requires_human_review", False) is False
