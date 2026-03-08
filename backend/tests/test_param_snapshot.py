import asyncio
import os

import pytest
from fastapi import HTTPException, Request

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

from app.api.v1.endpoints import langgraph_v2 as endpoint
from app.api.tests.helpers.langgraph_v2_test_stream_helpers import _event_stream_v2
from app.services.auth.dependencies import RequestUser


class DummyGraphSnapshot:
    checkpointer = object()

    def __init__(self, server_versions):
        self._server_versions = server_versions

    async def aget_state(self, _config):
        class Snapshot:
            def __init__(self, values):
                self.values = values

        return Snapshot(values={"parameter_versions": dict(self._server_versions)})

    def astream(self, _input, config=None, *, stream_mode=None, **_kwargs):
        async def gen():
            yield ("values", {"final_text": "ok", "phase": "final", "last_node": "final"})

        return gen()


def test_requires_param_snapshot(monkeypatch):
    monkeypatch.setattr(endpoint, "REQUIRE_PARAM_SNAPSHOT", True)
    req = endpoint.LangGraphV2Request(input="Hi", chat_id="chat-test")
    raw_request = Request({"type": "http", "headers": []})
    user = RequestUser(user_id="u1", username="u1", sub="u1", roles=[])

    with pytest.raises(HTTPException) as exc:
        asyncio.run(endpoint.langgraph_chat_v2_endpoint(req, raw_request, user))

    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "missing_param_snapshot"


def test_warns_on_stale_snapshot(monkeypatch, caplog):
    async def _dummy_graph():
        return DummyGraphSnapshot({"pressure_bar": 3})

    monkeypatch.setattr(endpoint, "get_sealai_graph_v2", _dummy_graph)
    monkeypatch.setattr(endpoint, "WARN_STALE_PARAM_SNAPSHOT", True)

    req = endpoint.LangGraphV2Request(
        input="Hi",
        chat_id="chat-test",
        client_context={
            "param_snapshot": {
                "versions": {"pressure_bar": 1},
                "updated_at": {"pressure_bar": 100},
            }
        },
    )

    async def _collect():
        async for _ in _event_stream_v2(req, user_id="user-test", request_id="req-1"):
            break

    with caplog.at_level("WARNING"):
        asyncio.run(_collect())

    assert any("stale_param_snapshot" in record.message for record in caplog.records)
