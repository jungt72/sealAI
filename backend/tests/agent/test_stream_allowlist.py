"""0A.4: SSE stream allowlist — only final_response_node tokens reach the client."""

import asyncio
import json
import pytest
from unittest.mock import patch
from langchain_core.messages import AIMessage, HumanMessage
from app.agent.api.router import (
    _VISIBLE_STREAM_NODES,
    event_generator,
    SESSION_STORE,
)
from app.agent.api.models import ChatRequest
from app.agent.cli import create_initial_state
from app.services.auth.dependencies import RequestUser


@pytest.fixture(autouse=True)
def clear_sessions():
    SESSION_STORE.clear()


@pytest.fixture()
def agent_request_user():
    return RequestUser(
        user_id="user-stream-test",
        username="tester",
        sub="user-stream-test",
        roles=[],
        scopes=[],
        tenant_id="tenant-stream-test",
    )


@pytest.fixture(autouse=True)
def fake_structured_case_store(monkeypatch):
    store = {}

    async def _fake_load(*, owner_id, case_id):
        import copy
        state = store.get((owner_id, case_id))
        return copy.deepcopy(state) if state is not None else None

    async def _fake_save(*, owner_id, case_id, state, runtime_path, binding_level):
        import copy
        store[(owner_id, case_id)] = copy.deepcopy(state)

    monkeypatch.setattr("app.agent.api.router.load_structured_case", _fake_load)
    monkeypatch.setattr("app.agent.api.router.save_structured_case", _fake_save)
    yield store


def _mock_state(messages, revision=1):
    sealing_state = create_initial_state()
    sealing_state["cycle"]["state_revision"] = revision
    sealing_state["cycle"]["analysis_cycle_id"] = f"session_test_{revision}"
    sealing_state["governance"]["release_status"] = "inadmissible"
    return {
        "messages": messages,
        "sealing_state": sealing_state,
        "working_profile": {},
        "relevant_fact_cards": [],
    }


def _make_stream_event(content, *, node=None):
    """Build an on_chat_model_stream event with optional langgraph_node metadata."""
    event = {
        "event": "on_chat_model_stream",
        "data": {"chunk": AIMessage(content=content)},
    }
    if node is not None:
        event["metadata"] = {"langgraph_node": node}
    else:
        event["metadata"] = {}
    return event


def _make_chain_end_event(state):
    return {
        "event": "on_chain_end",
        "name": "LangGraph",
        "data": {"output": state},
    }


class _MockGraph:
    def __init__(self, events):
        self._events = events

    def astream_events(self, state, version="v2"):
        return self._astream(state)

    async def _astream(self, state):
        for ev in self._events:
            yield ev


def _collect_chunks(request, user):
    chunks = []

    async def _run():
        async for chunk in event_generator(request, current_user=user):
            chunks.append(chunk)

    asyncio.run(_run())
    return chunks


def _parse_sse_data(chunks):
    """Extract parsed JSON objects from SSE data lines."""
    results = []
    for chunk in chunks:
        if chunk.startswith("data: ") and chunk.strip() != "data: [DONE]":
            raw = chunk[len("data: "):].strip()
            try:
                results.append(json.loads(raw))
            except (json.JSONDecodeError, ValueError):
                continue
    return results


# ── Test: allowlist constant ────────────────────────────────────────────

def test_visible_stream_nodes_contains_only_final_response_node():
    assert _VISIBLE_STREAM_NODES == frozenset({"final_response_node"})


# ── Test: final_response_node tokens ARE forwarded ──────────────────────

def test_final_response_node_tokens_are_forwarded(agent_request_user):
    session_id = "stream-allowlist-forward"
    final_state = _mock_state(
        [HumanMessage(content="Frage"), AIMessage(content="Antwort")],
        revision=2,
    )

    events = [
        _make_stream_event("Visible", node="final_response_node"),
        _make_stream_event(" token", node="final_response_node"),
        _make_chain_end_event(final_state),
    ]

    with patch("app.agent.api.router.get_agent_graph", return_value=_MockGraph(events)):
        chunks = _collect_chunks(
            ChatRequest(message="Frage", session_id=session_id),
            agent_request_user,
        )

    token_chunks = [c for c in chunks if '"chunk"' in c]
    assert len(token_chunks) == 2
    assert '"Visible"' in token_chunks[0]
    assert '" token"' in token_chunks[1]


# ── Test: reasoning_node tokens are SUPPRESSED ──────────────────────────

def test_reasoning_node_tokens_are_suppressed(agent_request_user):
    session_id = "stream-allowlist-suppress-reasoning"
    final_state = _mock_state(
        [HumanMessage(content="Frage"), AIMessage(content="Antwort")],
        revision=2,
    )

    events = [
        _make_stream_event("reasoning internal", node="reasoning_node"),
        _make_stream_event("Visible", node="final_response_node"),
        _make_chain_end_event(final_state),
    ]

    with patch("app.agent.api.router.get_agent_graph", return_value=_MockGraph(events)):
        chunks = _collect_chunks(
            ChatRequest(message="Frage", session_id=session_id),
            agent_request_user,
        )

    token_chunks = [c for c in chunks if '"chunk"' in c]
    assert len(token_chunks) == 1
    assert '"Visible"' in token_chunks[0]
    assert "reasoning internal" not in "".join(chunks)


# ── Test: unknown node tokens are SUPPRESSED ────────────────────────────

def test_unknown_node_tokens_are_suppressed(agent_request_user):
    session_id = "stream-allowlist-suppress-unknown"
    final_state = _mock_state(
        [HumanMessage(content="Frage"), AIMessage(content="Antwort")],
        revision=2,
    )

    events = [
        _make_stream_event("secret stuff", node="some_other_node"),
        _make_stream_event("Visible", node="final_response_node"),
        _make_chain_end_event(final_state),
    ]

    with patch("app.agent.api.router.get_agent_graph", return_value=_MockGraph(events)):
        chunks = _collect_chunks(
            ChatRequest(message="Frage", session_id=session_id),
            agent_request_user,
        )

    token_chunks = [c for c in chunks if '"chunk"' in c]
    assert len(token_chunks) == 1
    assert "secret stuff" not in "".join(chunks)


# ── Test: missing metadata → safe suppress, no crash ────────────────────

def test_missing_metadata_suppressed_without_crash(agent_request_user):
    session_id = "stream-allowlist-no-metadata"
    final_state = _mock_state(
        [HumanMessage(content="Frage"), AIMessage(content="Antwort")],
        revision=2,
    )

    # Event with no metadata key at all
    event_no_metadata = {
        "event": "on_chat_model_stream",
        "data": {"chunk": AIMessage(content="ghost token")},
    }
    events = [
        event_no_metadata,
        _make_stream_event("also ghost", node=None),  # metadata exists but no langgraph_node value
        _make_stream_event("Visible", node="final_response_node"),
        _make_chain_end_event(final_state),
    ]

    with patch("app.agent.api.router.get_agent_graph", return_value=_MockGraph(events)):
        chunks = _collect_chunks(
            ChatRequest(message="Frage", session_id=session_id),
            agent_request_user,
        )

    token_chunks = [c for c in chunks if '"chunk"' in c]
    assert len(token_chunks) == 1
    assert "ghost token" not in "".join(chunks)
    assert "also ghost" not in "".join(chunks)
    assert "[DONE]" in "".join(chunks)


# ── Test: final payload still arrives after filtered stream ──────────────

def test_final_payload_arrives_after_filtered_stream(agent_request_user):
    session_id = "stream-allowlist-final-payload"
    # Pre-seed to get qualified path (case_state in final payload)
    SESSION_STORE[f"{agent_request_user.user_id}:{session_id}"] = {
        "sealing_state": {
            "asserted": {"medium_profile": {"name": "Wasser"}, "operating_conditions": {}},
            "governance": {"unknowns_release_blocking": []},
        },
        "messages": [],
        "working_profile": {},
        "relevant_fact_cards": [],
        "tenant_id": "tenant-stream-test",
        "owner_id": agent_request_user.user_id,
    }
    final_state = _mock_state(
        [HumanMessage(content="Empfehle Material"), AIMessage(content="Empfehlung")],
        revision=3,
    )

    events = [
        _make_stream_event("internal reasoning", node="reasoning_node"),
        _make_stream_event("Empf", node="final_response_node"),
        _make_chain_end_event(final_state),
    ]

    with patch("app.agent.api.router.get_agent_graph", return_value=_MockGraph(events)):
        chunks = _collect_chunks(
            ChatRequest(message="Empfehle Material", session_id=session_id),
            agent_request_user,
        )

    # Token chunks: only from final_response_node
    token_chunks = [c for c in chunks if '"chunk"' in c and "internal reasoning" not in c]
    assert len(token_chunks) >= 1

    # Final payload must exist (contains reply, session_id, etc.)
    parsed = _parse_sse_data(chunks)
    final_payloads = [p for p in parsed if "reply" in p and "session_id" in p]
    assert len(final_payloads) == 1
    assert final_payloads[0]["session_id"] == session_id
    assert final_payloads[0]["reply"] == "Empfehlung"

    # [DONE] sentinel
    assert "data: [DONE]\n\n" in chunks


# ── Test: fast path is unaffected ────────────────────────────────────────

def test_fast_path_unaffected_by_stream_allowlist(agent_request_user):
    """Fast path doesn't go through astream_events — should still work."""
    session_id = "stream-allowlist-fast"

    with patch("app.agent.api.router.execute_fast_knowledge") as mock_fast:
        mock_fast.return_value = type("R", (), {"reply": "Schnelle Antwort", "working_profile": {}})()
        chunks = _collect_chunks(
            ChatRequest(message="Was ist PTFE?", session_id=session_id),
            agent_request_user,
        )

    content = "".join(chunks)
    assert "Schnelle Antwort" in content
    assert "[DONE]" in content
