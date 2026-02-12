import json
import os

import pytest
from langgraph.checkpoint.memory import MemorySaver

from app.langgraph_v2.nodes.nodes_flows import rag_support_node
from app.langgraph_v2.nodes.nodes_supervisor import (
    ACTION_RUN_KNOWLEDGE,
    ACTION_RUN_PANEL_NORMS_RAG,
    supervisor_policy_node,
)
from app.langgraph_v2.sealai_graph_v2 import (
    build_v2_config,
    create_sealai_graph_v2,
)
from app.langgraph_v2.state import Intent, SealAIState

os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5432")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("POSTGRES_SYNC_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("QDRANT_URL", "http://localhost:6333")
os.environ.setdefault("QDRANT_COLLECTION", "test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("NEXTAUTH_URL", "http://localhost:3000")
os.environ.setdefault("NEXTAUTH_SECRET", "test")
os.environ.setdefault("KEYCLOAK_ISSUER", "http://localhost/realms/test")
os.environ.setdefault("KEYCLOAK_JWKS_URL", "http://localhost/realms/test/protocol/openid-connect/certs")
os.environ.setdefault("KEYCLOAK_CLIENT_ID", "test")
os.environ.setdefault("KEYCLOAK_CLIENT_SECRET", "test")
os.environ.setdefault("KEYCLOAK_EXPECTED_AZP", "test")

from app.api.v1.endpoints import langgraph_v2 as endpoint


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _parse_sse_frame(frame: bytes) -> tuple[str | None, dict]:
    event_name: str | None = None
    payload: dict = {}
    for raw_line in frame.decode("utf-8").splitlines():
        if raw_line.startswith("event: "):
            event_name = raw_line[len("event: ") :]
        elif raw_line.startswith("data: "):
            payload = json.loads(raw_line[len("data: ") :])
    return event_name, payload


def test_graph_routes_norms_rag_and_comparison_loop_back_to_supervisor() -> None:
    compiled = create_sealai_graph_v2(checkpointer=MemorySaver()).get_graph()

    assert any(
        edge.source == "supervisor_policy_node" and edge.target == "rag_support_node"
        for edge in compiled.edges
    )
    assert any(
        edge.source == "material_comparison_node" and edge.target == "assumption_lock_node"
        for edge in compiled.edges
    )


@pytest.mark.anyio
async def test_sources_and_rag_request_runs_rag_and_emits_retrieval_event(monkeypatch) -> None:
    class _StubTool:
        @staticmethod
        def invoke(_payload):
            return {
                "context": "Normhinweis.\nQuelle: https://example.com/norm-iso",
                "retrieval_meta": {
                    "k_requested": 3,
                    "k_returned": 1,
                    "top_scores": [0.91],
                    "tenant_id": "tenant-1",
                    "category": "norms",
                },
            }

    monkeypatch.setattr(
        "app.langgraph_v2.nodes.nodes_flows.search_knowledge_base",
        _StubTool(),
    )

    class _FakeGraph:
        checkpointer = object()

        async def astream(self, initial_state, *, config=None, stream_mode=None):
            state = (
                initial_state
                if isinstance(initial_state, SealAIState)
                else SealAIState.model_validate(initial_state)
            )
            state = state.model_copy(
                update={
                    "intent": Intent(goal="explanation_or_comparison"),
                    "needs_sources": True,
                    "phase": "supervisor",
                    "last_node": "supervisor_policy_node",
                },
                deep=True,
            )

            first_patch = supervisor_policy_node(state)
            assert first_patch.get("next_action_reason") == "rag_sources_required"
            assert (first_patch.get("pending_action") or first_patch.get("next_action")) == ACTION_RUN_PANEL_NORMS_RAG
            state = state.model_copy(update=first_patch, deep=True)
            yield ("values", state)

            state = state.model_copy(update=rag_support_node(state), deep=True)
            yield ("values", state)

            state = state.model_copy(
                update={
                    "phase": "final_answer",
                    "last_node": "final_answer_node",
                    "final_text": "Hier sind die Quellen.",
                },
                deep=True,
            )
            yield ("values", state)

    graph = _FakeGraph()
    config = build_v2_config(thread_id="chat-rag-sources", user_id="user-1", tenant_id="tenant-1")

    async def _fake_build_graph_config(**_kwargs):
        return graph, config

    monkeypatch.setattr(endpoint, "_build_graph_config", _fake_build_graph_config)

    req = endpoint.LangGraphV2Request(
        input="Bitte mit Quellen aus der Wissensdatenbank (RAG): Was gilt hier normativ?",
        chat_id="chat-rag-sources",
    )

    events: list[tuple[str, dict]] = []
    async for frame in endpoint._event_stream_v2(
        req,
        user_id="user-1",
        tenant_id="tenant-1",
        can_read_private=False,
        checkpoint_thread_id="tenant-1:user-1:chat-rag-sources",
    ):
        event_name, payload = _parse_sse_frame(frame)
        if event_name:
            events.append((event_name, payload))

    decision_events = [payload for name, payload in events if name == "decision.supervisor"]
    assert decision_events
    assert decision_events[0].get("reason") == "rag_sources_required"

    supervisor_updates = [
        payload
        for name, payload in events
        if name == "state_update" and payload.get("last_node") == "supervisor_policy_node"
    ]
    assert supervisor_updates

    last_nodes = [payload.get("last_node") for name, payload in events if name == "state_update"]
    assert "rag_support_node" in last_nodes
    assert "final_answer_node" in last_nodes
    assert last_nodes.index("rag_support_node") < last_nodes.index("final_answer_node")

    retrieval_events = [
        (i, name) for i, (name, _payload) in enumerate(events) if name in {"retrieval.results", "retrieval.skipped"}
    ]
    assert retrieval_events


@pytest.mark.anyio
async def test_material_knowledge_query_does_not_emit_checkpoint_required(monkeypatch) -> None:
    class _FakeGraph:
        checkpointer = object()

        async def astream(self, initial_state, *, config=None, stream_mode=None):
            state = (
                initial_state
                if isinstance(initial_state, SealAIState)
                else SealAIState.model_validate(initial_state)
            )
            state = state.model_copy(
                update={
                    "intent": Intent(goal="explanation_or_comparison"),
                    "requires_rag": True,
                    "needs_sources": True,
                    "phase": "supervisor",
                    "last_node": "supervisor_policy_node",
                },
                deep=True,
            )

            first_patch = supervisor_policy_node(state)
            assert first_patch.get("next_action") == ACTION_RUN_KNOWLEDGE
            assert first_patch.get("pending_action") is None
            state = state.model_copy(update=first_patch, deep=True)
            yield ("values", state)

            state = state.model_copy(
                update={
                    "phase": "final_answer",
                    "last_node": "final_answer_node",
                    "final_text": "PTFE hat typischerweise eine hohe chemische Beständigkeit.",
                },
                deep=True,
            )
            yield ("values", state)

    graph = _FakeGraph()
    config = build_v2_config(thread_id="chat-knowledge", user_id="user-1", tenant_id="tenant-1")

    async def _fake_build_graph_config(**_kwargs):
        return graph, config

    monkeypatch.setattr(endpoint, "_build_graph_config", _fake_build_graph_config)

    req = endpoint.LangGraphV2Request(
        input="Bitte gib mir Infos zu Kyrolon.",
        chat_id="chat-knowledge",
    )

    events: list[tuple[str, dict]] = []
    async for frame in endpoint._event_stream_v2(
        req,
        user_id="user-1",
        tenant_id="tenant-1",
        can_read_private=False,
        checkpoint_thread_id="tenant-1:user-1:chat-knowledge",
    ):
        event_name, payload = _parse_sse_frame(frame)
        if event_name:
            events.append((event_name, payload))

    checkpoint_events = [payload for name, payload in events if name == "checkpoint_required"]
    assert checkpoint_events == []
