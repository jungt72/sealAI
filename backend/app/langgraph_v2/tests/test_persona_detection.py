from app.langgraph_v2.nodes.persona_detection import detect_persona


def test_expert():
    persona, _ = detect_persona(["FKM A75, dp/dt 15 bar/s, AED erforderlich"])
    assert persona == "erfahrener"


def test_beginner():
    persona, _ = detect_persona(["was ist eine dichtung"])
    assert persona == "einsteiger"


def test_decider():
    persona, _ = detect_persona(["Anlage steht, sofort Lösung"])
    assert persona == "entscheider"


def test_unknown():
    persona, _ = detect_persona(["ok danke"])
    assert persona == "unknown"
