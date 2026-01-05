from app.langgraph_v2.utils.jinja import render_template


def test_frontdoor_prompt_renders_goal_descriptions_and_examples() -> None:
    rendered = render_template(
        "frontdoor_discovery_prompt.jinja2",
        {"goal_descriptions": {"design_recommendation": "Empfehle Dichtungssysteme"}},
    )
    assert "Mögliche Intents" in rendered
    assert "- `design_recommendation`: Empfehle Dichtungssysteme" in rendered
    assert '"frontdoor_reply": "Deine knappe Antwort hier."' in rendered
    assert "Beispiele" in rendered


def test_frontdoor_prompt_requires_no_unfilled_placeholders() -> None:
    rendered = render_template(
        "frontdoor_discovery_prompt.jinja2",
        {"goal_descriptions": {"smalltalk": "Smalltalk-Ziel"}},
    )
    assert "{{" not in rendered
    assert "}}" not in rendered
