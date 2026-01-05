import app.langgraph_v2.sealai_graph_v2  # noqa: F401

from app.langgraph_v2.sealai_graph_v2 import _render_final_prompt_messages


def test_final_system_prompt_includes_senior_policy_by_default() -> None:
    payload = {
        "template_context": {
            "goal": "smalltalk",
            "recommendation_go": False,
            "latest_user_text": "Hallo",
            "coverage_score": 0.0,
            "coverage_gaps_text": "keine",
            "draft": "DRAFT",
            "plan": {},
        },
        "messages": [],
    }
    messages = _render_final_prompt_messages(payload)
    system_text = messages[0].content
    assert "Annahmen" in system_text
    assert "Risiken" in system_text
    assert "Nächste Schritte" in system_text
    assert "Beginne NIE mit Meta-Sätzen" in system_text
    assert "freundlich" in system_text
    assert "geduldig" in system_text


def test_style_profile_can_disable_policy() -> None:
    payload = {
        "template_context": {
            "goal": "smalltalk",
            "recommendation_go": False,
            "latest_user_text": "Hallo",
            "coverage_score": 0.0,
            "coverage_gaps_text": "keine",
            "draft": "DRAFT",
            "plan": {"style_profile": "off"},
        },
        "messages": [],
    }
    messages = _render_final_prompt_messages(payload)
    system_text = messages[0].content
    assert "Denk- und Antwort-Rahmen" not in system_text
