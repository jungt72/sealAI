from app.langgraph.prompts.prompt_loader import load_jinja_chat_prompt, render_prompt
from app.langgraph.nodes.quality_review import _style_hints


def _flatten_message_text(messages):
    return "\n".join(
        str(getattr(message, "content", "")) for message in messages if getattr(message, "content", "")
    )

def _assert_no_placeholders(text: str):
    assert "{{" not in text
    assert "{%" not in text


def test_challenger_prompt_includes_user_and_summary():
    prompt = load_jinja_chat_prompt("challenger_feedback.de.j2")
    messages = prompt.format_messages(
        user_query="Welche PTFE-Dichtung brauche ich?",
        specialist_summary="Die Experten empfehlen ein PTFE-Labyrinth.",
    )
    text = _flatten_message_text(messages)
    assert "Welche PTFE-Dichtung brauche ich?" in text
    assert "PTFE-Labyrinth" in text


def test_quality_gate_prompt_renders_style_hints():
    prompt = load_jinja_chat_prompt("quality_gate.de.j2")
    hints = ["Keine Einleitung erlauben.", "Antwort muss exakt ein Satz sein."]
    messages = prompt.format_messages(
        user_query="Gib mir die finale Antwort.",
        candidate_answer="Hier ist eine mögliche Lösung.",
        style_hints=hints,
    )
    text = _flatten_message_text(messages)
    for hint in hints:
        assert hint in text


def test_style_hints_builder_maps_contract_flags():
    slots = {
        "style_contract": {
            "no_intro": True,
            "no_outro": True,
            "single_sentence": True,
            "numbers_with_commas": True,
            "literal_numbers_start": 1,
            "literal_numbers_end": 3,
            "enforce_plain_answer": True,
            "additional_notes": "Nur technische Angaben.",
        }
    }
    hints = _style_hints(slots)
    assert "Keine Einleitung erlauben." in hints
    assert "Kein Nachsatz oder Fazit." in hints
    assert "Antwort muss exakt ein Satz sein." in hints
    assert "Zahlenfolge mit Kommas trennen." in hints
    assert "Zahlenbereich 1–3 vollständig abbilden." in hints
    assert "Keine Erklärungen oder Meta-Kommentare." in hints
    assert "Nur technische Angaben." in hints


def test_resolver_template_lists_required_params():
    text = render_prompt(
        "resolver.de.j2",
        required_params=["Param A", "Param B"],
        hints=["Zusatzhinweis"],
    )
    _assert_no_placeholders(text)
    assert "Param A" in text
    assert "Zusatzhinweis" in text


def test_confirm_gate_template_handles_missing_and_summary():
    missing_text = render_prompt(
        "confirm_gate.de.j2",
        mode="missing",
        missing_parameters=["Medium", "Temperatur"],
        has_more_missing=False,
    )
    _assert_no_placeholders(missing_text)
    assert "Medium" in missing_text
    summary_text = render_prompt(
        "confirm_gate.de.j2",
        mode="confirm",
        summary="Maschine XYZ, Medium Wasser",
        missing_parameters=[],
        has_more_missing=False,
    )
    _assert_no_placeholders(summary_text)
    assert "Maschine XYZ" in summary_text


def test_rwd_confirm_template_mentions_missing_fields():
    text = render_prompt(
        "rwd_confirm_missing.de.j2",
        missing_fields=["Drehzahl", "Temperatur"],
        has_more=True,
    )
    _assert_no_placeholders(text)
    assert "Drehzahl" in text
    assert "..." in text


def test_rwd_calculation_missing_template_lists_fields():
    text = render_prompt(
        "rwd_calculation_missing.de.j2",
        missing_fields=["shaft_diameter & speed_rpm"],
    )
    _assert_no_placeholders(text)
    assert "shaft_diameter" in text


def test_specialist_and_exit_templates_are_static():
    specialist = render_prompt("specialist_blocked.de.j2")
    fallback = render_prompt("exit_fallback.de.j2")
    _assert_no_placeholders(specialist)
    _assert_no_placeholders(fallback)
    assert "Bedarfsanalyse" in specialist
    assert "Medium/Anwendung" in fallback


def test_intent_projector_prompt_includes_smalltalk_and_technical_examples():
    text = render_prompt(
        "intent_projector.de.j2",
        user_query="hi",
        messages_window="",
        slots={},
    )
    _assert_no_placeholders(text)
    assert '"kind": "greeting"' in text
    assert '"kind": "technical_consulting"' in text
