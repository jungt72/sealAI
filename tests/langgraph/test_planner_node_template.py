from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage

from app.langgraph.nodes import planner_node as planner_module
from app.langgraph.state import SealAIState


class _FakePlannerGraph:
    def __init__(self) -> None:
        self.last_payload = None

    def invoke(self, payload):
        self.last_payload = payload
        return {
            "messages": [
                AIMessage(
                    content='{"ziel": "Test", "schritte": ["Analyse"], "empfohlene_agents": ["material"], "risiken": [], "offene_parameter": []}',
                    name="planner",
                )
            ]
        }


def test_planner_node_uses_jinja_template(monkeypatch):
    fake_graph = _FakePlannerGraph()
    monkeypatch.setattr(planner_module, "_planner_graph", lambda: fake_graph)

    state: SealAIState = {
        "messages": [HumanMessage(content="Wir brauchen eine RWDR.", id="msg-1")],
        "slots": {
            "user_query": "Welche Dichtung für 50 mm Welle?",
            "warmup": {"rapport": "freundlich"},
            "style_contract": {"no_intro": True},
        },
        "rwd_requirements": {"machine": "Pumpe"},
        "requirements_coverage": 0.2,
    }

    result = planner_module.planner_node(state)

    assert fake_graph.last_payload is not None
    planner_messages = fake_graph.last_payload["messages"]
    base_count = len(state["messages"])
    appended = planner_messages[base_count:]
    assert appended, "Planner prompt should append template messages"
    assert any("Dr. Planner" in getattr(msg, "content", "") for msg in appended)
    slots = result.get("slots") or {}
    assert slots.get("planner_plan")
    assert slots.get("recommended_agents") == ["material"]
