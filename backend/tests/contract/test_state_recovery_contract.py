from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph


def _set_minimal_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # Keep consistent with other contract tests: avoid settings init failures.
    monkeypatch.setenv("postgres_user", "test")
    monkeypatch.setenv("postgres_password", "test")
    monkeypatch.setenv("postgres_host", "localhost")
    monkeypatch.setenv("postgres_port", "5432")
    monkeypatch.setenv("postgres_db", "test")
    monkeypatch.setenv("database_url", "postgresql+psycopg://test:test@localhost:5432/test")
    monkeypatch.setenv("POSTGRES_SYNC_URL", "postgresql://test:test@localhost:5432/test")

    monkeypatch.setenv("openai_api_key", "dummy")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")

    monkeypatch.setenv("qdrant_url", "http://localhost:6333")
    monkeypatch.setenv("qdrant_collection", "test")

    monkeypatch.setenv("redis_url", "redis://localhost:6379/0")

    monkeypatch.setenv("nextauth_url", "http://localhost:3000")
    monkeypatch.setenv("nextauth_secret", "dummy")

    monkeypatch.setenv("keycloak_issuer", "http://localhost:8080/realms/test")
    monkeypatch.setenv(
        "keycloak_jwks_url",
        "http://localhost:8080/realms/test/protocol/openid-connect/certs",
    )
    monkeypatch.setenv("keycloak_client_id", "dummy")
    monkeypatch.setenv("keycloak_client_secret", "dummy")
    monkeypatch.setenv("keycloak_expected_azp", "dummy")


def _build_minimal_state_graph():
    from app.langgraph_v2.state import SealAIState

    def _noop_node(_state: SealAIState):
        return {"last_node": "noop_node"}

    builder = StateGraph(SealAIState)
    builder.add_node("noop_node", _noop_node)
    builder.add_edge(START, "noop_node")
    builder.add_edge("noop_node", END)
    return builder


def test_state_recovery_persists_messages_across_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_minimal_settings_env(monkeypatch)
    from app.langgraph_v2.sealai_graph_v2 import build_v2_config

    graph = _build_minimal_state_graph().compile(checkpointer=InMemorySaver())

    config1 = build_v2_config(thread_id="t1", user_id="u1", tenant_id="tenant-1")
    assert config1.get("configurable", {}).get("thread_id") == "u1|t1"
    graph.invoke({"messages": [HumanMessage(content="Hi 1")]}, config1)
    snap1 = graph.get_state(config1)
    assert len(snap1.values.get("messages") or []) == 1

    config2 = build_v2_config(thread_id="t1", user_id="u1", tenant_id="tenant-1")
    graph.invoke({"messages": [HumanMessage(content="Hi 2")]}, config2)
    snap2 = graph.get_state(config2)
    assert len(snap2.values.get("messages") or []) == 2


def test_state_isolation_across_users_with_same_thread_id(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_minimal_settings_env(monkeypatch)
    from app.langgraph_v2.sealai_graph_v2 import build_v2_config

    graph = _build_minimal_state_graph().compile(checkpointer=InMemorySaver())

    config_user_a = build_v2_config(thread_id="same-thread", user_id="user-a", tenant_id="tenant-1")
    graph.invoke({"messages": [HumanMessage(content="A1")]}, config_user_a)

    config_user_b = build_v2_config(thread_id="same-thread", user_id="user-b", tenant_id="tenant-1")
    snap_b_before = graph.get_state(config_user_b)
    assert (
        len(snap_b_before.values.get("messages") or []) == 0
    ), "user-b must not see user-a messages for colliding thread_id"

    graph.invoke({"messages": [HumanMessage(content="B1")]}, config_user_b)
    snap_a = graph.get_state(config_user_a)
    snap_b = graph.get_state(config_user_b)
    assert [m.content for m in snap_a.values.get("messages") or []] == ["A1"]
    assert [m.content for m in snap_b.values.get("messages") or []] == ["B1"]
