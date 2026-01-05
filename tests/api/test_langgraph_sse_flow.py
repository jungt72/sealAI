from __future__ import annotations

import asyncio
import json
from typing import List, Tuple

import pytest
from langchain_core.messages import AIMessage
from starlette.requests import Request

from app.langgraph import compile as graph_compile
from app.langgraph.compile import run_langgraph_stream
from app.langgraph.nodes import context_retrieval, memory_bridge, memory_commit_node, supervisor_factory


ENDPOINT = "/api/v1/ai/langgraph/chat/stream"


def _stream_request(app, *, text: str, thread_id: str, user_id: str) -> List[Tuple[str, dict]]:
    payload = {"input": text, "chat_id": thread_id, "user_id": user_id}

    async def _invoke() -> str:
        body = json.dumps(payload).encode("utf-8")
        sent = {"done": False}

        async def receive():
            if sent["done"]:
                return {"type": "http.disconnect"}
            sent["done"] = True
            return {"type": "http.request", "body": body, "more_body": False}

        scope = {
            "type": "http",
            "method": "POST",
            "path": ENDPOINT,
            "headers": [(b"accept", b"text/event-stream")],
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("testclient", 123),
            "scheme": "http",
            "root_path": "",
            "app": app,
            "asgi": {"version": "3.0", "spec_version": "2.3"},
        }
        request = Request(scope, receive)
        response = await run_langgraph_stream(request)
        content = bytearray()
        async for chunk in response.body_iterator:
            if isinstance(chunk, str):
                chunk = chunk.encode("utf-8")
            content.extend(chunk)
        return content.decode("utf-8")

    raw = asyncio.run(_invoke())

    events: List[Tuple[str, dict]] = []
    current_event = None
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("event:"):
            current_event = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            payload = json.loads(line.split(":", 1)[1].strip())
            events.append((current_event, payload))
    return events


def _patch_memory_bridge(monkeypatch):
    async def fake_transcript(_user_id: str):
        return {"chat_id": "c-1", "summary": "Letzte Beratung zu PTFE-Hülsen.", "metadata": {}}

    async def fake_refs(_user_id: str):
        return [
            {
                "storage": "qdrant",
                "id": "ltm-1",
                "summary": "Setzt auf lange Laufzeiten.",
                "score": 0.9,
            }
        ]

    monkeypatch.setattr(memory_bridge, "_load_last_transcript", fake_transcript)
    monkeypatch.setattr(memory_bridge, "_load_ltm_refs", fake_refs)


def _patch_rag(monkeypatch):
    monkeypatch.setattr(context_retrieval, "hybrid_retrieve", lambda **_: [
        {"text": "Datenblatt zu Gleitringdichtungen", "source": "kb://doc1", "vector_score": 0.9}
    ])


def _patch_supervisor(monkeypatch, *, confidence_sequence: List[float]):
    def fake_planner(state):
        slots = dict(state.get("slots") or {})
        slots["planner_plan"] = "Plan: Spezialisten"
        return {"slots": slots}

    def fake_specialists(state):
        slots = dict(state.get("slots") or {})
        slots["specialist_summary"] = "Spezialist: Empfehlung A"
        slots["candidate_answer"] = "Spezialist: Empfehlung A"
        return {"slots": slots, "messages": [AIMessage(content="Spec", name="specialists")]}

    def fake_challenger(state):
        slots = dict(state.get("slots") or {})
        slots["challenger_feedback"] = "Challenger: Passt, keine Einwände."
        return {"slots": slots, "messages": [AIMessage(content="Challenge", name="challenger")]}

    call_counter = {"idx": 0}

    def fake_quality_review(state):
        routing = dict(state.get("routing") or {})
        routing["confidence"] = confidence_sequence[min(call_counter["idx"], len(confidence_sequence) - 1)]
        call_counter["idx"] += 1
        slots = dict(state.get("slots") or {})
        slots["checklist_result"] = {"approved": routing["confidence"] >= 0.7, "improved_answer": ""}
        return {"routing": routing, "slots": slots}

    def fake_resolver(state):
        slots = dict(state.get("slots") or {})
        slots["candidate_answer"] = slots.get("candidate_answer") or "Fallback"
        message = AIMessage(content="🧑‍⚖️ Arbiter bestätigt Empfehlung.", name="arbiter")
        return {"slots": slots, "messages": [message], "phase": "review"}

    monkeypatch.setattr(supervisor_factory, "_SUPERVISOR_FLOW", None)
    monkeypatch.setattr(supervisor_factory, "planner_node", fake_planner)
    monkeypatch.setattr(supervisor_factory, "specialist_executor", fake_specialists)
    monkeypatch.setattr(supervisor_factory, "challenger_feedback", fake_challenger)
    monkeypatch.setattr(supervisor_factory, "run_quality_review", fake_quality_review)
    monkeypatch.setattr(supervisor_factory, "resolver", fake_resolver)


def test_technical_flow_with_memory_commit(app, monkeypatch):
    _patch_memory_bridge(monkeypatch)
    _patch_rag(monkeypatch)
    _patch_supervisor(monkeypatch, confidence_sequence=[0.5, 0.92])

    store_calls = []

    async def fake_store(user_id: str, key: str, value: str) -> int:
        store_calls.append((user_id, key, value))
        return 100

    monkeypatch.setattr(memory_commit_node, "_store_ltm_entry", fake_store)
    monkeypatch.setattr(memory_commit_node.memory_core, "commit_summary", lambda *args, **kwargs: None)

    class TechnicalGraph:
        async def astream_events(self, state, config, version="v1"):
            yield {"event": "messages", "data": [{"content": "Rapport: Schön, dass Sie da sind."}]}
            yield {"event": "messages", "data": [{"content": "Langzeit-Kontext: Letzte Beratung zu PTFE."}]}
            yield {"event": "messages", "data": [{"content": "🧑‍⚖️ Arbiter bestätigt Empfehlung."}]}
            fake_state = {
                "meta": {"user_id": config["configurable"]["user_id"], "thread_id": config["configurable"]["thread_id"]},
                "rapport_summary": "Rapport ok",
                "discovery_summary": "Bedarfsanalyse abgeschlossen",
                "slots": {"candidate_answer": "Empfehlung X", "final_answer": "Empfehlung X"},
            }
            await memory_commit_node.memory_commit_node(fake_state)
            yield {"event": "on_graph_end", "data": {"state": fake_state}}

    monkeypatch.setattr(graph_compile, "ensure_main_graph", lambda: TechnicalGraph())

    events = _stream_request(app, text="Ich brauche Hilfe bei einer Gleitringdichtung für eine Chemiepumpe.", thread_id="thread-123", user_id="user-123")

    tokens = " ".join(payload.get("text") or payload.get("token", "") for event, payload in events if event in {"message", "token"})

    assert "Empfehlung X" in tokens
    assert store_calls, "Memory Commit wurde nicht ausgelöst"
    assert "Rapport ok" in store_calls[0][2]
    assert "Bedarfsanalyse" in store_calls[0][2]
    assert any(event == "done" for event, _ in events)


def test_smalltalk_flow_without_heavy_backend(app, monkeypatch):
    _patch_rag(monkeypatch)
    called_bridge = {"count": 0}

    async def guard_memory_bridge(state, *, config=None):
        called_bridge["count"] += 1
        return {}

    monkeypatch.setattr(memory_bridge, "memory_bridge_node", guard_memory_bridge)
    monkeypatch.setattr(graph_compile, "memory_bridge_node", guard_memory_bridge)

    class SmalltalkGraph:
        async def astream_events(self, state, config, version="v1"):
            yield {"event": "messages", "data": [{"content": "Hallo! Schön, dich zu hören."}]}
            yield {"event": "on_graph_end", "data": {"state": {"slots": {"final_answer": "Smalltalk-Reply"}}}}

    monkeypatch.setattr(graph_compile, "ensure_main_graph", lambda: SmalltalkGraph())

    events = _stream_request(app, text="Hi, wie geht es dir heute?", thread_id="thread-smalltalk", user_id="user-xyz")

    tokens = " ".join(payload.get("text") or payload.get("token", "") for event, payload in events if event in {"message", "token"})
    assert called_bridge["count"] == 0, "Memory Bridge sollte bei Smalltalk nicht laufen"
    assert "🧑‍⚖️" not in tokens
    assert any(event == "done" for event, _ in events)
