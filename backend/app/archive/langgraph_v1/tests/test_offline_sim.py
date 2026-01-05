import os

from langchain_core.messages import HumanMessage

from app.langgraph.nodes.supervisor_factory import build_supervisor
from app.langgraph.state import SealAIState


def test_offline_all_workers_reachable(monkeypatch):
    monkeypatch.setenv("LANGGRAPH_USE_FAKE_LLM", "1")
    graph = build_supervisor()

    def _handoff_trace(prompt: str) -> list[str]:
        state = SealAIState(messages=[HumanMessage(content=prompt)], slots={})
        outcome = graph.invoke(state)
        return outcome.get("slots", {}).get("handoff_history", [])

    trace_profile = _handoff_trace("Bitte Profil erstellen und anschließend validieren.")
    trace_material = _handoff_trace("Berechne Gewicht für Platte 1m x 1m x 0.01m mit Dichte 8000 kg/m³.")
    trace_validierung = _handoff_trace("Empfiehl Material")

    assert "profil" in trace_profile
    assert "material" in trace_material
    assert "validierung" in trace_validierung
