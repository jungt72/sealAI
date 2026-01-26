from __future__ import annotations

import os
import sys
import types

import pytest
from starlette.requests import Request

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

if "asyncpg" not in sys.modules:
    asyncpg_stub = types.ModuleType("asyncpg")

    async def _stub_connect(*_args, **_kwargs):
        raise RuntimeError("asyncpg stub")

    asyncpg_stub.connect = _stub_connect
    asyncpg_stub.create_pool = _stub_connect
    sys.modules["asyncpg"] = asyncpg_stub

from app.api.v1.endpoints import langgraph_v2  # noqa: E402
from app.api.v1.endpoints.langgraph_v2 import LangGraphV2Request  # noqa: E402
from app.services.auth.dependencies import RequestUser  # noqa: E402


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("roles", "expected"),
    [
        (["admin"], True),
        (["editor"], False),
        ([], False),
    ],
)
async def test_langgraph_v2_state_admin_flag_propagates(
    monkeypatch: pytest.MonkeyPatch, roles: list[str], expected: bool
) -> None:
    captured = {}

    def fake_event_stream_v2(_req, *, can_read_private: bool, **_kwargs):
        captured["can_read_private"] = can_read_private

        async def _gen():
            if False:
                yield b""

        return _gen()

    monkeypatch.setattr(langgraph_v2, "_event_stream_v2", fake_event_stream_v2)

    req = LangGraphV2Request(input="hi", chat_id="chat-1")
    raw_request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/chat/v2",
            "headers": [],
        }
    )
    user = RequestUser(
        user_id="user-1",
        tenant_id="tenant-1",
        username="user",
        sub="sub-1",
        roles=roles,
    )

    _ = await langgraph_v2.langgraph_chat_v2_endpoint(req, raw_request, user)

    assert captured.get("can_read_private") is expected
