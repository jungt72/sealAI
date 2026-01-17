from app.langgraph_v2.nodes.response_node import response_node
from app.langgraph_v2.state import Intent, SealAIState, TechnicalParameters


def _base_state(**kwargs):
    intent = kwargs.pop("intent", Intent(goal="design_recommendation"))
    parameters = kwargs.pop("parameters", TechnicalParameters())
    return SealAIState(intent=intent, parameters=parameters, **kwargs)


def test_clarifying_questions_triggered_for_missing():
    state = _base_state()
    patch = response_node(state)
    assert "Kurzfragen:" in patch["final_text"]
    assert patch.get("clarify_round_count") == 1
    assert patch.get("clarify_missing_facts")


def test_clarifying_questions_not_when_complete():
    state = _base_state(
        parameters=TechnicalParameters(
            temperature_C=20.0,
            pressure_bar=5.0,
            speed_rpm=1200.0,
            medium="Motoröl",
            shaft_diameter=25.0,
            housing_diameter=40.0,
        )
    )
    patch = response_node(state)
    assert "Kurzfragen:" not in patch["final_text"]
    assert patch.get("clarify_round_count") is None


def test_no_questions_for_knowledge_intent():
    state = _base_state(intent=Intent(goal="design_recommendation", key="knowledge_material", knowledge_type="material"))
    patch = response_node(state)
    assert "Kurzfragen:" not in patch["final_text"]


def test_no_repeat_when_clarify_round_used():
    state = _base_state(clarify_round_count=1)
    patch = response_node(state)
    assert "Kurzfragen:" not in patch["final_text"]


def test_max_four_questions():
    state = _base_state()
    patch = response_node(state)
    lines = [line for line in patch["final_text"].splitlines() if line.startswith("- ")]
    assert len(lines) <= 4
