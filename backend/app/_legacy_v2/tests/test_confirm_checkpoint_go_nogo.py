from app._legacy_v2.nodes.nodes_confirm import confirm_recommendation_node
from app._legacy_v2.state import SealAIState


def test_confirm_checkpoint_go() -> None:
    state = SealAIState(
        coverage_score=0.9,
        coverage_gaps=[],
        working_profile={
            "engineering_profile": {
                "medium": "Hydraulikoel",
                "temperature_C": 80,
                "pressure_bar": 10,
                "speed_rpm": 1500,
                "shaft_diameter": 50,
            }
        },
    )
    patch = confirm_recommendation_node(state)
    text = patch["system"]["final_text"]
    assert "Status: GO" in text
    assert "Checkliste" in text
    assert "Top-Rückfragen" not in text
    assert patch["reasoning"]["recommendation_go"] is True


def test_confirm_checkpoint_no_go_with_prioritized_questions() -> None:
    state = SealAIState(
        coverage_score=0.6,
        coverage_gaps=["medium", "temperature_C"],
        working_profile={
            "engineering_profile": {
                "pressure_bar": 10,
                "speed_rpm": 1500,
                "shaft_diameter": 50,
            }
        },
    )
    patch = confirm_recommendation_node(state)
    text = patch["system"]["final_text"]
    assert "Status: NO-GO" in text
    assert "Top-Rückfragen (priorisiert):" in text
    assert patch["reasoning"]["recommendation_go"] is False

    questions = [line for line in text.splitlines() if line.strip().startswith("- ") and "Warum:" in line]
    assert 1 <= len(questions) <= 3
    assert all("Warum:" in q for q in questions)
