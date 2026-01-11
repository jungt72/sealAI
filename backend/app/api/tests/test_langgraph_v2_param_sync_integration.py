"""
Integration coverage for LangGraph v2 parameter patch -> state -> chat config.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

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

from starlette.requests import Request  # noqa: E402

from app.api.v1.endpoints import langgraph_v2 as endpoint  # noqa: E402
from app.api.v1.endpoints import state as state_endpoint  # noqa: E402
from app.langgraph_v2.utils.parameter_patch import ParametersPatchRequest  # noqa: E402
from app.services.auth.dependencies import RequestUser  # noqa: E402


def _request() -> Request:
    return Request({"type": "http", "headers": []})


def test_param_patch_state_chat_config_alignment(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("LANGGRAPH_V2_CHECKPOINTER", "memory")

    chat_id = "chat-param-sync"
    user_id = "user-param-sync"
    request = _request()
    user = RequestUser(user_id=user_id, username="tester", sub="sub-test", roles=[])

    async def _run():
        patch_body = ParametersPatchRequest(
            chat_id=chat_id,
            parameters={"medium": "oil", "pressure_bar": 2},
        )
        await endpoint.patch_parameters(patch_body, request, user=user)

        state_response = await state_endpoint.get_state(request, thread_id=chat_id, user=user)
        assert state_response["parameters"]["medium"] == "oil"
        assert state_response["parameters"]["pressure_bar"] == 2
        assert state_response["config"]["configurable"]["thread_id"] == chat_id

        graph, config = await endpoint._build_graph_config(
            thread_id=chat_id,
            user_id=user.user_id,
            tenant_id=user.user_id,
        )
        assert config["configurable"]["thread_id"] == chat_id
        snapshot = await graph.aget_state(config)
        state_values = state_endpoint._state_to_dict(snapshot.values)
        params = state_endpoint._serialize_parameters(state_values.get("parameters"))
        assert params["medium"] == "oil"
        assert params["pressure_bar"] == 2

    asyncio.run(_run())


def test_param_patch_merges_existing_parameters(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("LANGGRAPH_V2_CHECKPOINTER", "memory")

    chat_id = "chat-param-merge"
    user_id = "user-param-merge"
    request = _request()
    user = RequestUser(user_id=user_id, username="tester", sub="sub-test", roles=[])

    async def _run():
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

    asyncio.run(_run())


def test_latest_write_patch_then_chat_wins(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("LANGGRAPH_V2_CHECKPOINTER", "memory")

    chat_id = "chat-param-latest-1"
    user_id = "user-param-latest-1"
    request = _request()
    user = RequestUser(user_id=user_id, username="tester", sub="sub-test", roles=[])

    async def _run():
        first_patch = ParametersPatchRequest(
            chat_id=chat_id,
            parameters={"pressure_bar": 5},
        )
        await endpoint.patch_parameters(first_patch, request, user=user)

        graph, config = await endpoint._build_graph_config(
            thread_id=chat_id,
            user_id=user.user_id,
            tenant_id=user.user_id,
        )
        await graph.aupdate_state(
            config,
            {"parameters": {"pressure_bar": 7}},
            as_node=endpoint.PARAMETERS_PATCH_AS_NODE,
        )

        state_response = await state_endpoint.get_state(request, thread_id=chat_id, user=user)
        assert state_response["parameters"]["pressure_bar"] == 7

    asyncio.run(_run())


def test_latest_write_chat_then_patch_wins(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("LANGGRAPH_V2_CHECKPOINTER", "memory")

    chat_id = "chat-param-latest-2"
    user_id = "user-param-latest-2"
    request = _request()
    user = RequestUser(user_id=user_id, username="tester", sub="sub-test", roles=[])

    async def _run():
        graph, config = await endpoint._build_graph_config(
            thread_id=chat_id,
            user_id=user.user_id,
            tenant_id=user.user_id,
        )
        await graph.aupdate_state(
            config,
            {"parameters": {"pressure_bar": 7}},
            as_node=endpoint.PARAMETERS_PATCH_AS_NODE,
        )

        aliased_patch = ParametersPatchRequest(
            chat_id=chat_id,
            parameters={"pressure": 5},
        )
        await endpoint.patch_parameters(aliased_patch, request, user=user)

        state_response = await state_endpoint.get_state(request, thread_id=chat_id, user=user)
        assert state_response["parameters"]["pressure_bar"] == 5

    asyncio.run(_run())


def test_pressure_alias_overwrites_existing_value(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("LANGGRAPH_V2_CHECKPOINTER", "memory")

    chat_id = "chat-param-alias-override"
    user_id = "user-param-alias-override"
    request = _request()
    user = RequestUser(user_id=user_id, username="tester", sub="sub-test", roles=[])

    async def _run():
        first_patch = ParametersPatchRequest(
            chat_id=chat_id,
            parameters={"pressure_bar": 3},
        )
        await endpoint.patch_parameters(first_patch, request, user=user)

        alias_patch = ParametersPatchRequest(
            chat_id=chat_id,
            parameters={"pressure": 6},
        )
        await endpoint.patch_parameters(alias_patch, request, user=user)

        state_response = await state_endpoint.get_state(request, thread_id=chat_id, user=user)
        assert state_response["parameters"]["pressure_bar"] == 6

    asyncio.run(_run())
def test_state_falls_back_to_legacy_thread(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("CHECKPOINTER_BACKEND", "memory")

    chat_id = "chat-legacy-fallback"
    request = _request()
    user = RequestUser(user_id="user-claim", username="tester", sub="legacy-sub", roles=[])

    async def _run():
        graph, legacy_config = await state_endpoint._build_state_config_with_checkpointer(
            thread_id=chat_id,
            user_id=user.sub,
            tenant_id=user.user_id,
            username=user.username,
        )
        await graph.aupdate_state(
            legacy_config,
            {"parameters": {"medium": "oil"}},
            as_node="supervisor_policy_node",
        )

        state_response = await state_endpoint.get_state(request, thread_id=chat_id, user=user)
        assert state_response["parameters"]["medium"] == "oil"
        assert state_response["config"]["configurable"]["thread_id"] == chat_id

    asyncio.run(_run())
