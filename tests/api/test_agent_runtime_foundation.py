from __future__ import annotations

import json

import anyio
from langchain_core.messages import AIMessage

from app.agent.api.models import ChatRequest
from app.agent.api.router import chat_endpoint, event_generator
from app.agent.runtime import route_interaction


def _parse_sse_payloads(response_text: str) -> list[dict]:
    payloads: list[dict] = []
    for raw_line in response_text.splitlines():
        if not raw_line.startswith("data: "):
            continue
        data = raw_line[6:]
        if data == "[DONE]":
            continue
        payloads.append(json.loads(data))
    return payloads


def test_route_interaction_classifies_expected_paths():
    calc = route_interaction("Berechne für 50 mm und 1500 rpm die Umfangsgeschwindigkeit.")
    assert calc.runtime_path == "FAST_CALCULATION"
    assert calc.interaction_class == "CALCULATION"

    knowledge = route_interaction("Was ist PTFE?")
    assert knowledge.runtime_path == "FAST_KNOWLEDGE"
    assert knowledge.binding_level == "KNOWLEDGE"

    fallback = route_interaction("Ich brauche Unterstützung für meinen Fall.")
    assert fallback.runtime_path == "FALLBACK_SAFE_STRUCTURED"

    qualification = route_interaction("Bitte empfehle ein geeignetes Material für diese Dichtung.")
    assert qualification.runtime_path == "STRUCTURED_QUALIFICATION"


def test_fast_calculation_path_bypasses_graph(monkeypatch, agent_request_user):
    from app.agent.api import router as router_mod

    router_mod.SESSION_STORE.clear()

    async def _fail_execute_agent(_state):
        raise AssertionError("graph must not run for fast calculation")

    monkeypatch.setattr(router_mod, "execute_agent", _fail_execute_agent)
    async def _call():
        return await chat_endpoint(
            ChatRequest(
                message=(
                    "Berechne bei 50 mm, 1500 rpm und 10 bar "
                    "die Umfangsgeschwindigkeit und den PV-Wert."
                ),
                session_id="calc-1",
            ),
            current_user=agent_request_user,
        )

    response = anyio.run(_call)

    payload = response.model_dump()
    assert payload["runtime_path"] == "FAST_CALCULATION"
    assert payload["interaction_class"] == "CALCULATION"
    assert payload["binding_level"] == "CALCULATION"
    assert payload["has_case_state"] is False
    assert payload["qualified_action_gate"] is None
    assert payload["rfq_ready"] is False
    assert payload["case_state"] is None
    assert "sealing_state" not in payload
    assert payload["working_profile"]["calc_results"]["v_surface_m_s"] is not None


def test_fast_knowledge_path_bypasses_graph(monkeypatch, agent_request_user):
    from app.agent.api import router as router_mod
    from app.agent import runtime as runtime_mod

    router_mod.SESSION_STORE.clear()

    async def _fail_execute_agent(_state):
        raise AssertionError("graph must not run for fast knowledge")

    class _Card:
        topic = "PTFE"
        content = "PTFE ist ein fluorierter Hochleistungskunststoff mit guter chemischer Beständigkeit."

    async def _fake_retrieve(*_args, **_kwargs):
        return [_Card()]

    monkeypatch.setattr(router_mod, "execute_agent", _fail_execute_agent)
    monkeypatch.setattr(runtime_mod, "retrieve_rag_context", _fake_retrieve)
    async def _call():
        return await chat_endpoint(
            ChatRequest(
                message="Was ist PTFE?",
                session_id="knowledge-1",
            ),
            current_user=agent_request_user,
        )

    response = anyio.run(_call)

    payload = response.model_dump()
    assert payload["runtime_path"] == "FAST_KNOWLEDGE"
    assert payload["interaction_class"] == "KNOWLEDGE"
    assert payload["binding_level"] == "KNOWLEDGE"
    assert payload["has_case_state"] is False
    assert payload["qualified_action_gate"] is None
    assert payload["rfq_ready"] is False
    assert payload["case_state"] is None
    assert "PTFE" in payload["reply"]


def test_structured_request_still_invokes_graph(monkeypatch, agent_request_user):
    from app.agent.api import router as router_mod

    router_mod.SESSION_STORE.clear()
    called = {"value": False}

    async def _fake_execute_agent(state):
        called["value"] = True
        state["messages"].append(AIMessage(content="Structured reply"))
        return state

    monkeypatch.setattr(router_mod, "execute_agent", _fake_execute_agent)
    async def _call():
        return await chat_endpoint(
            ChatRequest(
                message="Bitte empfehle ein geeignetes Material für diese Dichtung bei 10 bar.",
                session_id="structured-1",
            ),
            current_user=agent_request_user,
        )

    response = anyio.run(_call)

    payload = response.model_dump()
    assert called["value"] is True
    assert payload["runtime_path"] == "STRUCTURED_QUALIFICATION"
    assert payload["interaction_class"] == "QUALIFICATION"
    assert payload["binding_level"] == "QUALIFIED_PRESELECTION"
    assert payload["has_case_state"] is True
    assert payload["case_id"] == "structured-1"
    assert payload["qualified_action_gate"]["allowed"] is False
    assert payload["rfq_ready"] is False


def test_stream_shell_contains_runtime_metadata(monkeypatch, agent_request_user):
    from app.agent.api import router as router_mod

    router_mod.SESSION_STORE.clear()

    async def _fail_execute_agent(_state):
        raise AssertionError("graph must not run for fast calculation stream")

    monkeypatch.setattr(router_mod, "execute_agent", _fail_execute_agent)
    async def _collect_chunks():
        chunks = []
        async for chunk in event_generator(
            ChatRequest(
                message="Berechne bei 40 mm und 1000 rpm die Umfangsgeschwindigkeit.",
                session_id="stream-1",
            ),
            current_user=agent_request_user,
        ):
            chunks.append(chunk)
        return chunks

    chunks = anyio.run(_collect_chunks)

    payloads = _parse_sse_payloads("".join(chunks))
    final_payload = payloads[-1]
    assert final_payload["runtime_path"] == "FAST_CALCULATION"
    assert final_payload["interaction_class"] == "CALCULATION"
    assert final_payload["binding_level"] == "CALCULATION"
    assert final_payload["has_case_state"] is False
    assert final_payload["qualified_action_gate"] is None
    assert final_payload["rfq_ready"] is False
    assert "case_state" not in final_payload
