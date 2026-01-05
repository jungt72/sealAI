from __future__ import annotations

from langchain_core.messages import HumanMessage

from app.langgraph import compile as graph_compile
from app.langgraph.nodes import rapport_agent
from app.langgraph.state import SealAIState


class _StubLLM:
    def invoke(self, _messages):
        class _Response:
            content = (
                "Hallo! Wie läuft es aktuell bei Ihnen? "
                "Im nächsten Schritt würde ich gern gezielte Fragen stellen."
            )

        return _Response()


def test_rapport_agent_sets_flags(monkeypatch):
    monkeypatch.setattr(rapport_agent, "_resolve_llm", lambda config: _StubLLM())
    state: SealAIState = {
        "messages": [HumanMessage(content="Hallo, wir brauchen Unterstützung.")],
        "slots": {},
        "meta": {},
    }
    update = rapport_agent.rapport_agent_node(state, config={})
    slots = update["slots"]
    assert slots["rapport_phase_done"] is True
    assert slots["rapport_summary"]
    assert update["phase"] == "rapport"


def test_route_after_intent_prefers_rapport_phase():
    state: SealAIState = {
        "slots": {},
        "intent": {
            "domain": "sealing",
            "kind": "technical_consulting",
            "task": "consulting",
            "confidence": 0.91,
        },
    }
    route = graph_compile._route_after_intent(state)
    assert route == "rapport_agent"

    state_with_rapport: SealAIState = {
        "slots": {"rapport_phase_done": True},
        "intent": {
            "domain": "sealing",
            "kind": "technical_consulting",
            "task": "consulting",
            "confidence": 0.91,
        },
    }
    route_after = graph_compile._route_after_intent(state_with_rapport)
    assert route_after == "warmup_agent"
