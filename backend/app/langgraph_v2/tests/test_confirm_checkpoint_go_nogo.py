from app.langgraph_v2.nodes.nodes_confirm import confirm_recommendation_node
from app.langgraph_v2.state import SealAIState, TechnicalParameters


def test_confirm_checkpoint_go() -> None:
    state = SealAIState(
        coverage_score=0.9,
        coverage_gaps=[],
        parameters=TechnicalParameters(
            medium="Hydraulikoel",
            temperature_C=80,
            pressure_bar=10,
            speed_rpm=1500,
            shaft_diameter=50,
        ),
    )
    patch = confirm_recommendation_node(state)
    text = patch["final_text"]
    assert "Status: GO" in text
    assert "Checkliste" in text
    assert "Top-Rückfragen" not in text
    assert patch["recommendation_go"] is True


def test_confirm_checkpoint_no_go_with_prioritized_questions() -> None:
    state = SealAIState(
        coverage_score=0.6,
        coverage_gaps=["medium", "temperature_C"],
        parameters=TechnicalParameters(
            pressure_bar=10,
            speed_rpm=1500,
            shaft_diameter=50,
        ),
    )
    patch = confirm_recommendation_node(state)
    text = patch["final_text"]
    assert "Status: NO-GO" in text
    assert "Top-Rückfragen (priorisiert):" in text
    assert patch["recommendation_go"] is False

    questions = [line for line in text.splitlines() if line.strip().startswith("- ") and "Warum:" in line]
    assert 1 <= len(questions) <= 3
    assert all("Warum:" in q for q in questions)
