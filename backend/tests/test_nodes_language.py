from __future__ import annotations

from app.langgraph.io.schema import Intent
from app.langgraph.io.units import normalize_bag
from app.langgraph.io.validation import ensure_discovery, ensure_handoff, ensure_intent, ensure_parameter_bag


def _to_dict(model):
    exporter = getattr(model, "model_dump", None)
    if callable(exporter):
        return exporter()
    return model.dict()


def test_discovery_to_intent_to_router_language_contract():
    discovery_raw = {
        "ziel": "Finde Material für Hochtemperatur",
        "zusammenfassung": "Nutzer sucht Hochtemperaturdichtung",
        "fehlende_parameter": [],
        "ready_to_route": True,
    }
    discovery = ensure_discovery(discovery_raw)

    intent_raw = {
        "intent": "material",
        "domäne": "material",
        "confidence": 0.85,
        "coverage": 0.75,
        "hybrid_score": 0.9,
        "risk": "low",
        "empfohlene_agenten": ["material"],
        "routing_modus": "single",
    }
    intent = ensure_intent(intent_raw)
    assert discovery.schema_version == intent.schema_version

    bag = ensure_parameter_bag({
        "items": [
            {"name": "temp_max", "value": 220.0, "unit": "°C", "source": "user"},
            {"name": "druck", "value": 3.0, "unit": "bar", "source": "user"},
        ]
    })

    handoff_raw = {
        "agent": "material",
        "auftrag": "Empfehlung erarbeiten",
        "eingaben": _to_dict(bag),
        "restriktionen": [],
        "erwartete_ausgabe": {"schema": "agent_output", "muessen_enthalten": ["empfehlung"]},
        "rag_hinweis": "auto",
        "max_tokens_hint": 300,
    }
    handoff = ensure_handoff(handoff_raw)

    canonical = normalize_bag(handoff.eingaben)
    temp = canonical.get("temp_max")
    assert temp is not None
    assert temp.unit.value == "K"
    assert handoff.agent is Intent.material
