"""V1.8 §5.4 No-Go completeness: affirmative suitability/"bedenkenlos" release
wording is detected, while refusals are not (P1-G)."""

from __future__ import annotations

import pytest

from app.agent.templates.no_go_guard import detect_no_go_phrases


@pytest.mark.parametrize(
    "text",
    [
        "Den FKM-Ring können Sie bedenkenlos einsetzen.",
        "Sie können bedenkenlos verbauen, das hält.",
        "Können Sie das bedenkenlos montieren.",
    ],
)
def test_detects_affirmative_bedenkenlos_release(text: str) -> None:
    assert detect_no_go_phrases(text, include_final_release=True) != []


@pytest.mark.parametrize(
    "text",
    [
        # Interrogative/refusal — "können" follows "bedenkenlos", so no match.
        "Ob Sie das bedenkenlos einsetzen können, kann ich nicht beurteilen.",
        "Das kann ich nicht bedenkenlos freigeben — bitte Hersteller fragen.",
        "Laut Datenblatt liegt die Temperaturgrenze bei 150 °C.",
    ],
)
def test_ignores_refusal_and_neutral_wording(text: str) -> None:
    assert detect_no_go_phrases(text, include_final_release=True) == []
