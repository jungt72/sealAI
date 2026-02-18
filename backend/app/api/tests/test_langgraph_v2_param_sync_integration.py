"""
Integration coverage for LangGraph v2 parameter patch -> state -> chat config.

Important:
- We must not reuse cached async clients/checkpointers across different event loops.
- Therefore:
  - set env BEFORE importing endpoint/state modules inside each test
  - clear graph caches between tests
  - run each test as async (pytest anyio) and avoid multiple asyncio.run loops
"""


from __future__ import annotations

import pytest

# AnyIO runs parametrized backends by default (asyncio+trio). Our image does not ship trio.
pytestmark = pytest.mark.anyio("asyncio")

import os
import sys
from pathlib import Path

import pytest

# Ensure backend is on path (tests run from repo root in some setups).
sys.path.append(str(Path(__file__).resolve().parents[3]))

# Minimal env defaults for settings to load (avoid import-time config failures).
os.environ.setdefault("postgres_user", "test")
os.environ.setdefault("postgres_password", "test")
os.environ.setdefault("postgres_host", "localhost")
os.environ.setdefault("postgres_port", "5432")
os.environ.setdefault("postgres_db", "testdb")
os.environ.setdefault("database_url", "postgresql+asyncpg://test:test@localhost:5432/testdb")
os.environ.setdefault("POSTGRES_SYNC_URL", "postgresql://test:test@localhost:5432/testdb")
os.environ.setdefault("openai_api_key", "sk-test")
os.environ.setdefault("qdrant_url", "http://localhost:6333")
os.environ.setdefault("qdrant_collection", "test")
os.environ.setdefault("redis_url", "redis://localhost:6379/0")
os.environ.setdefault("keycloak_jwks_url", "http://localhost/.well-known/jwks.json")
os.environ.setdefault("keycloak_expected_azp", "test-client")


def _request():
    from starlette.requests import Request

    return Request({"type": "http", "headers": []})


def _clear_langgraph_v2_caches() -> None:
    """
    Best-effort cache reset to avoid cross-event-loop reuse of async clients.

    We intentionally keep this defensive: if internal names change, this won't crash tests.
    """
    try:
        import app.langgraph_v2.sealai_graph_v2 as graphmod

        for name in (
            "_GRAPH_CACHE",
            "_GRAPH_BY_TENANT",
            "_GRAPH_SINGLETON",
            "_CACHED_GRAPH",
            "_TENANT_GRAPH_CACHE",
        ):
            obj = getattr(graphmod, name, None)
            if isinstance(obj, dict):
                obj.clear()
            elif obj is not None and hasattr(graphmod, name):
                try:
                    setattr(graphmod, name, None)
                except Exception:
                    pass
    except Exception:
        pass

    # In case the endpoint module caches anything, clear that too (best-effort).
    try:
        import app.api.v1.endpoints.langgraph_v2 as ep

        for name in (
            "_CACHED_GRAPH",
            "_GRAPH",
            "_GRAPH_CACHE",
        ):
            obj = getattr(ep, name, None)
            if isinstance(obj, dict):
                obj.clear()
            elif obj is not None and hasattr(ep, name):
                try:
                    setattr(ep, name, None)
                except Exception:
                    pass
    except Exception:
        pass


def _imports_after_env():
    """
    Import modules ONLY after env is configured in the test.
    """
    from app.api.v1.endpoints import langgraph_v2 as endpoint
    from app.api.v1.endpoints import state as state_endpoint
    from app.langgraph_v2.utils.parameter_patch import ParametersPatchRequest
    from app.langgraph_v2.utils.threading import resolve_checkpoint_thread_id
    from app.services.auth.dependencies import RequestUser

    return endpoint, state_endpoint, ParametersPatchRequest, resolve_checkpoint_thread_id, RequestUser


def _checkpoint_thread_id(resolve_checkpoint_thread_id, *, tenant_id: str, user_id: str, chat_id: str) -> str:
    # Single Source of Truth: must match production behavior (may hash chat_id to UUID5, etc.)
    return resolve_checkpoint_thread_id(tenant_id=tenant_id, user_id=user_id, chat_id=chat_id)


@pytest.mark.anyio
async def test_param_patch_state_chat_config_alignment(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("CHECKPOINTER_BACKEND", "redis")
    monkeypatch.setenv("LANGGRAPH_V2_ALLOW_MEMORY_FALLBACK", "1")

    # make sure any cached graph/checkpointer from other tests is not reused
    _clear_langgraph_v2_caches()

    endpoint, state_endpoint, ParametersPatchRequest, resolve_checkpoint_thread_id, RequestUser = _imports_after_env()

    chat_id = "chat-param-sync"
    user_id = "user-param-sync"
    tenant_id = "tenant-1"
    request = _request()
    user = RequestUser(tenant_id=tenant_id, user_id=user_id, username="tester", sub="sub-test", roles=[])

    expected_thread_key = _checkpoint_thread_id(
        resolve_checkpoint_thread_id,
        tenant_id=tenant_id,
        user_id=user.user_id,
        chat_id=chat_id,
    )

    patch_body = ParametersPatchRequest(
        chat_id=chat_id,
        parameters={"medium": "oil", "pressure_bar": 2},
    )
    await endpoint.patch_parameters(patch_body, request, user=user)

    state_response = await state_endpoint.get_state(request, thread_id=chat_id, user=user)
    assert state_response["parameters"]["medium"] == "oil"
    assert state_response["parameters"]["pressure_bar"] == 2

    # State endpoint must align to production checkpoint thread id (SoT).
    assert state_response["config"]["configurable"]["thread_id"] == expected_thread_key

    # Chat endpoint config builder must align to same checkpoint thread id (SoT).
    graph, config = await endpoint._build_graph_config(
        thread_id=chat_id,
        user_id=user.user_id,
        tenant_id=tenant_id,
    )
    assert config["configurable"]["thread_id"] == expected_thread_key

    snapshot = await graph.aget_state(config)
    state_values = state_endpoint._state_to_dict(snapshot.values)
    params = state_endpoint._serialize_parameters(state_values.get("parameters"))
    assert params["medium"] == "oil"
    assert params["pressure_bar"] == 2


@pytest.mark.anyio
async def test_param_patch_merges_existing_parameters(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("CHECKPOINTER_BACKEND", "redis")
    monkeypatch.setenv("LANGGRAPH_V2_ALLOW_MEMORY_FALLBACK", "1")

    _clear_langgraph_v2_caches()

    endpoint, state_endpoint, ParametersPatchRequest, _resolve_checkpoint_thread_id, RequestUser = _imports_after_env()

    chat_id = "chat-param-merge"
    user_id = "user-param-merge"
    tenant_id = "tenant-1"
    request = _request()
    user = RequestUser(tenant_id=tenant_id, user_id=user_id, username="tester", sub="sub-test", roles=[])

    first_patch = ParametersPatchRequest(
        chat_id=chat_id,
        parameters={"medium": "oil"},
    )
    await endpoint.patch_parameters(first_patch, request, user=user)

    second_patch = ParametersPatchRequest(
        chat_id=chat_id,
        parameters={"pressure_bar": 10},
    )
    await endpoint.patch_parameters(second_patch, request, user=user)

    state_response = await state_endpoint.get_state(request, thread_id=chat_id, user=user)
    assert state_response["parameters"]["medium"] == "oil"
    assert state_response["parameters"]["pressure_bar"] == 10


@pytest.mark.anyio
async def test_state_reads_scoped_thread(monkeypatch):
    """
    State endpoint resolves and reads tenant-scoped checkpoint thread ids.
    """
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("CHECKPOINTER_BACKEND", "redis")
    monkeypatch.setenv("LANGGRAPH_V2_ALLOW_MEMORY_FALLBACK", "1")

    _clear_langgraph_v2_caches()

    _endpoint, state_endpoint, _ParametersPatchRequest, _resolve_checkpoint_thread_id, RequestUser = _imports_after_env()

    chat_id = "chat-legacy-fallback"
    request = _request()
    tenant_id = "tenant-1"
    user = RequestUser(tenant_id=tenant_id, user_id="user-claim", username="tester", sub="legacy-sub", roles=[])

    graph, legacy_config = await state_endpoint._build_state_config_with_checkpointer(
        tenant_id=tenant_id,
        thread_id=chat_id,
        user_id=user.user_id,
        username=user.username,
    )

    await graph.aupdate_state(
        legacy_config,
        {"parameters": {"medium": "oil"}},
        as_node="supervisor_policy_node",
    )

    state_response = await state_endpoint.get_state(request, thread_id=chat_id, user=user)
    assert state_response["parameters"]["medium"] == "oil"
    # Returned config should show the tenant-scoped checkpoint key.
    expected_thread_key = _resolve_checkpoint_thread_id(
        tenant_id=tenant_id,
        user_id=user.user_id,
        chat_id=chat_id,
    )
    assert state_response["config"]["configurable"]["thread_id"] == expected_thread_key
