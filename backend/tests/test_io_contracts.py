from __future__ import annotations
from backend.app.langgraph.io.schema import (
    DiscoveryOutput, IntentClassification, HandoffSpec,
    AgentInput, AgentOutput, SynthesisOutput, SafetyVerdict,
    ParameterBag, ParamValue, Unit, Intent, Risk, ExpectedOutputSpec
)
from backend.app.langgraph.io.validation import (
    ensure_discovery, ensure_intent, ensure_handoff, ensure_agent_output, ensure_synthesis, ensure_safety
)

def test_discovery_contract():
    x = {
        "ziel": "Werkstoffauswahl",
        "zusammenfassung": "ok",
        "fehlende_parameter": ["druck"],
        "ready_to_route": False
    }
    out = ensure_discovery(x)
    assert out.schema_version.startswith("1.")

def test_intent_contract():
    x = {
        "intent": "material",
        "domäne": "material",
        "confidence": 0.8,
        "coverage": 0.72,
        "hybrid_score": 0.3,
        "risk": "low",
        "empfohlene_agenten": ["material"],
        "routing_modus": "single"
    }
    out = ensure_intent(x)
    assert out.intent == Intent.material

def test_handoff_contract():
    bag = {"items": [{"name": "temperatur", "value": 25.0, "unit": "°C", "source": "user"}]}
    x = {
        "agent": "material",
        "auftrag": "Empfehle Werkstoff",
        "eingaben": bag,
        "restriktionen": [],
        "erwartete_ausgabe": {"schema_name": "AgentOutput", "muessen_enthalten": ["empfehlung"]},
        "rag_hinweis": "auto",
        "max_tokens_hint": 400
    }
    out = ensure_handoff(x)
    assert out.agent == Intent.material
    assert out.erwartete_ausgabe.schema_name == "AgentOutput"

def test_agent_output_contract():
    x = {
        "empfehlung": "PTFE",
        "begruendung": "chemisch beständig",
        "annahmen": ["rein"],
        "unsicherheiten": [],
        "evidenz": []
    }
    out = ensure_agent_output(x)
    assert out.empfehlung == "PTFE"

def test_synthesis_contract():
    x = {
        "empfehlung": "PTFE",
        "alternativen": ["EPDM"],
        "unsicherheiten": ["Temp Fenster unklar"],
        "naechste_schritte": ["Norm prüfen"]
    }
    out = ensure_synthesis(x)
    assert out.alternativen == ["EPDM"]

def test_safety_contract():
    x = {"result": "pass"}
    out = ensure_safety(x)
    assert out.result == "pass"
