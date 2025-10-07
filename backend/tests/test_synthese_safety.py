from __future__ import annotations

from app.langgraph.nodes.safety_gate import SafetyGateNode
from app.langgraph.nodes.synthese import SyntheseNode


def test_synthese_prioritises_norm_conflicts():
    node = SyntheseNode()
    result = node.run(
        {
            "agent_outputs": [
                {
                    "empfehlung": "Setze Material X ein",
                    "begruendung": "Temperaturbereich ausreichend",
                    "unsicherheiten": [
                        "Norm ISO 1234 nicht bestätigt",
                        "Kosten höher als Budget",
                    ],
                },
                {
                    "empfehlung": "Alternative Material Y",
                    "unsicherheiten": ["Grenzwert Geschwindigkeit unklar"],
                },
            ]
        }
    )
    assert result["empfehlung"].startswith("Setze Material")
    assert result["alternativen"] == ["Alternative Material Y"]
    assert result["unsicherheiten"][0].startswith("Norm")
    assert result["naechste_schritte"][0] == "Normenlage prüfen"


def test_safety_blocks_when_risk_high_and_no_evidence():
    node = SafetyGateNode()
    verdict = node.run(
        {
            "risk": "high",
            "classification": {"empfohlene_agenten": ["material"]},
            "agent_outputs": [
                {
                    "empfehlung": "Material X",
                    "begruendung": "",
                    "unsicherheiten": ["Erhöhte Temperatur"],
                }
            ],
        }
    )
    assert verdict["result"] == "block_with_reason"
    assert isinstance(verdict["reason"], str)
    assert "evidenz" in verdict["reason"].lower()


def test_safety_passes_when_normen_has_evidence():
    node = SafetyGateNode()
    verdict = node.run(
        {
            "risk": "med",
            "classification": {"empfohlene_agenten": ["normen"]},
            "agent_outputs": [
                {
                    "empfehlung": "Normkonforme Lösung",
                    "begruendung": "",
                    "unsicherheiten": [],
                    "evidenz": [{"kind": "internal", "ref": "report-1"}],
                }
            ],
        }
    )
    assert verdict["result"] == "pass"
