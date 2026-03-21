import re

from app._legacy_v2.utils.jinja import render_template


def _extract_question_bullets(text: str) -> list[str]:
    lines = text.splitlines()
    start = None
    for idx, line in enumerate(lines):
        if line.strip() == "Top-Rückfragen (priorisiert):":
            start = idx + 1
            break
    if start is None:
        return []

    bullets: list[str] = []
    for line in lines[start:]:
        stripped = line.strip()
        if not stripped:
            break
        if re.match(r"^-\s+", stripped):
            bullets.append(stripped)
            continue
        break
    return bullets


def test_discovery_template_caps_prioritized_questions_with_rationale() -> None:
    text = render_template(
        "final_answer_discovery_v2.j2",
        {
            "latest_user_text": "Bitte Dichtung empfehlen",
            "draft": "DRAFT",
            "parameters": {"medium": "Hydraulikoel"},
            "discovery_summary": None,
            "discovery_missing": [],
            "coverage_gaps": ["temperature_C", "pressure_bar", "speed_rpm", "shaft_diameter"],
            "coverage_gaps_text": "temperature_C, pressure_bar, speed_rpm, shaft_diameter",
            "coverage_score": 0.2,
        },
    )
    assert "Erste Einordnung (vorläufig):" in text
    assert "Top-Rückfragen (priorisiert):" in text

    bullets = _extract_question_bullets(text)
    assert 1 <= len(bullets) <= 5
    assert all("Warum:" in bullet for bullet in bullets)

    assert "Fragen zur Vervollständigung" not in text
    assert "Bitte fülle" not in text


def test_discovery_template_hides_questions_when_complete() -> None:
    text = render_template(
        "final_answer_discovery_v2.j2",
        {
            "latest_user_text": "Bitte Dichtung empfehlen",
            "draft": "DRAFT",
            "parameters": {
                "medium": "Hydraulikoel",
                "temperature_C": 80,
                "pressure_bar": 10,
                "speed_rpm": 1500,
                "shaft_diameter": 50,
            },
            "discovery_summary": None,
            "discovery_missing": [],
            "coverage_gaps": [],
            "coverage_gaps_text": "keine",
            "coverage_score": 1.0,
        },
    )
    assert "Erste Einordnung (vorläufig):" in text
    assert "Top-Rückfragen (priorisiert):" not in text
