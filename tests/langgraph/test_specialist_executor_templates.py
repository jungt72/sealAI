from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage

from app.langgraph.nodes import specialist_executor as specialist_module
from app.langgraph.state import SealAIState


class _FakeSpecialistGraph:
    def __init__(self, name: str, calls: list[tuple[str, dict]]) -> None:
        self._name = name
        self._calls = calls

    def invoke(self, payload):
        self._calls.append((self._name, payload))
        return {"messages": [AIMessage(content=f"{self._name} result", name=self._name)]}


def test_specialist_executor_injects_template(monkeypatch):
    calls: list[tuple[str, dict]] = []

    def fake_graph(name: str):
        return _FakeSpecialistGraph(name, calls)

    monkeypatch.setattr(specialist_module, "_specialist_graph", fake_graph)

    state: SealAIState = {
        "messages": [HumanMessage(content="Kunde sucht RWDR für 50 mm, Öl 8 bar.", id="msg-1")],
        "slots": {
            "user_query": "Welche Materialien für 50 mm RWDR?",
            "planner_mode": "expert_consulting",
            "recommended_agents": ["material"],
            "planner_plan_struct": {"ziel": "Material prüfen"},
            "planner_plan": '{"ziel": "Material prüfen"}',
            "rwd_calc_summary": "PV=1.2",
        },
        "phase": "auswahl",
        "rwd_calc_results": {"pv_value": 1.2},
        "rwd_requirements": {"machine": "Pumpe"},
    }

    result = specialist_module.specialist_executor(state)

    assert calls, "specialist graph should be invoked"
    agent_name, payload = calls[0]
    assert agent_name == "material"
    planner_messages = payload["messages"]
    base_len = len(state["messages"])
    appended = planner_messages[base_len:]
    assert appended, "template messages should be appended"
    assert any("Material-Spezialist" in getattr(msg, "content", "") for msg in appended)
    slots = result.get("slots") or {}
    assert slots.get("specialist_summary")
    assert slots.get("candidate_source") == "specialists"
