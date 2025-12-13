from app.langgraph_v2.state import SealAIState, TechnicalParameters
from app.langgraph_v2.utils.confirm_checkpoint import build_confirm_checkpoint_payload


def test_build_confirm_checkpoint_payload() -> None:
    state = SealAIState(
        phase="confirm",
        last_node="confirm_recommendation_node",
        final_text="**Abnahme-Checkpoint (vorläufig)**\n- Status: GO",
        recommendation_go=True,
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
    payload = build_confirm_checkpoint_payload(state)
    assert payload["type"] == "confirm_checkpoint"
    assert payload["phase"] == "confirm"
    assert payload["recommendation_go"] is True
    assert payload["coverage_score"] == 0.9
