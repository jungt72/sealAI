from __future__ import annotations

import pytest

from app.langgraph.nodes.confirm_gate import ConfirmGateNode
from app.langgraph.nodes.discovery_intake import DiscoveryIntakeNode
from app.langgraph.nodes.discovery_summarize import DiscoverySummarizeNode
from app.langgraph.nodes.intent_classifier import IntentClassifierNode
from app.langgraph.nodes.router import RouterNode


@pytest.fixture()
def pipeline():
    return {
        "intake": DiscoveryIntakeNode(),
        "summarize": DiscoverySummarizeNode(),
        "gate": ConfirmGateNode(),
        "classifier": IntentClassifierNode(),
        "router": RouterNode(),
    }


def test_discovery_to_router_pipeline_with_missing_params(pipeline):
    discovery = pipeline["intake"].run({
        "ziel": "Material für 220°C",
        "missing": ["druck", "geschwindigkeit"],
        "zusammenfassung": "Hochtemperatur Dichtung",
    })
    assert discovery["schema_version"] == "1.0.0"
    assert len(discovery["fehlende_parameter"]) == 2
    assert discovery["ready_to_route"] is False

    summarized = pipeline["summarize"].run(discovery)
    gated = pipeline["gate"].run({**summarized, "force_ready": False})
    assert gated["ready_to_route"] is False

    classified = pipeline["classifier"].run(gated)
    assert classified["intent"] in {"material", "sonstiges"}

    handoff = pipeline["router"].run(
        {
            "classification": classified,
            "parameter": {
                "items": [
                    {"name": "temperatur", "value": 220, "unit": "°C", "source": "user"},
                    {"name": "druck", "value": 2.4, "unit": "bar", "source": "user"},
                ]
            },
            "auftrag": "Material prüfen",
        }
    )
    assert handoff["agent"] in {"material", "sonstiges"}
    temp = handoff["eingaben"]["items"][0]
    assert temp["unit"] == "K"
    assert pytest.approx(temp["value"], rel=1e-3) == 493.15


def test_router_sets_rag_hint_for_normen(pipeline):
    classified = {
        "schema_version": "1.0.0",
        "intent": "normen",
        "domäne": "normen",
        "confidence": 0.8,
        "coverage": 0.8,
        "hybrid_score": 0.8,
        "risk": "med",
        "empfohlene_agenten": ["normen"],
        "routing_modus": "single",
    }
    handoff = pipeline["router"].run(
        {
            "classification": classified,
            "parameter": {"items": []},
            "auftrag": "Normen prüfen",
        }
    )
    assert handoff["rag_hinweis"] == "nur_fakten"
