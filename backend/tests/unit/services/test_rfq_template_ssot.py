from pathlib import Path

from jinja2 import Environment, FileSystemLoader


TEMPLATE_DIR = Path(__file__).resolve().parents[3] / "app" / "prompts"


def _render(context: dict[str, object]) -> str:
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=False)
    return env.get_template("rfq_template.j2").render(**context)


def test_rfq_template_contains_all_v0_4_required_sections() -> None:
    text = _render(
        {
            "medium": "Salzwasser",
            "temperature_c": 80,
            "pressure_bar": 4,
            "shaft_diameter_mm": 50,
            "speed_rpm": 1500,
            "risks": ["Korrosionsrisiko pruefen"],
            "open_points": ["Salzkonzentration offen"],
            "manufacturer_questions": ["Bitte Compound-Freigabe bestaetigen"],
            "matched_partners": [],
        }
    )

    required_headings = [
        "1. KURZBESCHREIBUNG",
        "2. ANLAGE & FUNKTION",
        "3. DICHTSTELLE & BEWEGUNG",
        "4. MEDIUM & UMGEBUNG",
        "5. BETRIEBSDATEN",
        "6. GEOMETRIE & EINBAURAUM",
        "7. WERKSTOFFE & OBERFLAECHEN",
        "8. ERKANNTE RISIKEN",
        "9. BERECHNUNGEN / TECHNISCHE HINWEISE",
        "10. PLAUSIBLE TECHNISCHE RICHTUNG",
        "11. OFFENE PUNKTE / UNBESTAETIGTE ANNAHMEN",
        "12. FRAGEN AN DEN HERSTELLER",
        "13. ANFRAGEZIEL / STUECKZAHL / RUECKMELDUNG",
    ]
    for heading in required_headings:
        assert heading in text
    assert "keine finale" in text.casefold()
    assert "Herstellerpruefung" in text
