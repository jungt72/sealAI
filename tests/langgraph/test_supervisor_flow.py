from __future__ import annotations

import copy

from langchain_core.messages import AIMessage

from app.langgraph.nodes import supervisor_factory
from app.langgraph.state import SealAIState


def _patch_supervisor_dependencies(monkeypatch, *, confidence_sequence):
    def fake_planner(state):
        slots = copy.deepcopy(state.get("slots") or {})
        slots["planner_plan"] = "plan::ok"
        return {"slots": slots}

    def fake_specialists(state):
        slots = copy.deepcopy(state.get("slots") or {})
        slots["specialist_summary"] = "Spezialist: Basisempfehlung"
        slots["candidate_answer"] = "Spezialist: Basisempfehlung"
        return {"slots": slots, "messages": [AIMessage(content="spec", name="specialists")]}

    def fake_challenger(state):
        loops = int(state.get("review_loops") or 0)
        slots = copy.deepcopy(state.get("slots") or {})
        if loops == 0:
            slots["challenger_feedback"] = "Challenger: Bitte Parameter prüfen."
            slots["candidate_answer"] = "Challenger: Bitte Parameter prüfen."
        else:
            slots["challenger_feedback"] = "OK – keine weiteren Einwände."
        return {"slots": slots, "messages": [AIMessage(content="challenge", name="challenger")]}

    review_calls = {"count": 0}

    def fake_quality_review(state):
        routing = dict(state.get("routing") or {})
        routing["confidence"] = confidence_sequence[min(review_calls["count"], len(confidence_sequence) - 1)]
        review_calls["count"] += 1
        slots = copy.deepcopy(state.get("slots") or {})
        slots["checklist_result"] = {"approved": routing["confidence"] >= 0.7, "improved_answer": ""}
        return {"routing": routing, "slots": slots}

    def fake_resolver(state):
        slots = copy.deepcopy(state.get("slots") or {})
        slots["candidate_answer"] = slots.get("candidate_answer") or "Fallback"
        message = AIMessage(content="Arbiter-OK", name="arbiter")
        return {"slots": slots, "messages": [message], "phase": "review"}

    monkeypatch.setattr(supervisor_factory, "_SUPERVISOR_FLOW", None)
    monkeypatch.setattr(supervisor_factory, "planner_node", fake_planner)
    monkeypatch.setattr(supervisor_factory, "specialist_executor", fake_specialists)
    monkeypatch.setattr(supervisor_factory, "challenger_feedback", fake_challenger)
    monkeypatch.setattr(supervisor_factory, "run_quality_review", fake_quality_review)
    monkeypatch.setattr(supervisor_factory, "resolver", fake_resolver)


def test_supervisor_flow_triggers_review_loop(monkeypatch):
    _patch_supervisor_dependencies(monkeypatch, confidence_sequence=[0.4, 0.85])
    graph = supervisor_factory.build_supervisor_subgraph()
    state: SealAIState = {
        "messages": [],
        "slots": {"user_query": "Wir brauchen Hilfe"},
        "routing": {},
        "review_loops": 0,
    }

    result = graph.invoke(state)

    assert result.get("review_loops") == 1
    assert any(getattr(msg, "content", "").startswith("Arbiter") or getattr(msg, "content", "") == "Arbiter-OK" for msg in result.get("messages", []))


def test_supervisor_flow_high_confidence_direct(monkeypatch):
    _patch_supervisor_dependencies(monkeypatch, confidence_sequence=[0.9])
    graph = supervisor_factory.build_supervisor_subgraph()
    state: SealAIState = {
        "messages": [],
        "slots": {"user_query": "Direkte Frage"},
        "routing": {},
        "review_loops": 0,
    }

    result = graph.invoke(state)

    assert result.get("review_loops") == 0
    assert result.get("confidence") >= 0.8
