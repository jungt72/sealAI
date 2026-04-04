from __future__ import annotations

import asyncio
import json
import os

import pytest

for key, value in {
    "postgres_user": "test",
    "postgres_password": "test",
    "postgres_host": "localhost",
    "postgres_port": "5432",
    "postgres_db": "testdb",
    "database_url": "postgresql+asyncpg://test:test@localhost:5432/testdb",
    "POSTGRES_SYNC_URL": "postgresql://test:test@localhost:5432/testdb",
    "openai_api_key": "sk-test",
    "qdrant_url": "http://localhost:6333",
    "qdrant_collection": "test",
    "redis_url": "redis://localhost:6379/0",
    "nextauth_url": "http://localhost:3000",
    "nextauth_secret": "test-secret",
    "keycloak_issuer": "http://localhost/realms/test",
    "keycloak_jwks_url": "http://localhost/.well-known/jwks.json",
    "keycloak_client_id": "test-client",
    "keycloak_client_secret": "test-secret",
    "keycloak_expected_azp": "test-client",
}.items():
    os.environ.setdefault(key, value)


from app.api.v1.endpoints import langgraph_v2 as endpoint
from app.services.auth.dependencies import RequestUser


def _run(coro):
    return asyncio.run(coro)


def _parse_eventsource_events(frames: list[dict]) -> dict[str, list[dict]]:
    events: dict[str, list[dict]] = {}
    for frame in frames:
        event_name = frame.get("event")
        payload = json.loads(frame.get("data") or "{}")
        events.setdefault(str(event_name), []).append(payload)
    return events


def _user() -> RequestUser:
    return RequestUser(
        user_id="user-1",
        username="tester",
        sub="user-1",
        roles=[],
        scopes=[],
        tenant_id="tenant-1",
    )


def test_compat_stream_translates_canonical_agent_frames(monkeypatch):
    captured = {}

    async def _fake_event_generator(request, *, current_user):
        captured["message"] = request.message
        captured["session_id"] = request.session_id
        captured["tenant_id"] = current_user.tenant_id
        yield 'data: {"type":"text_chunk","text":"Hallo"}\n\n'
        yield (
            'data: {"type":"state_update","reply":"Hallo","working_profile":{"medium":"water"},'
            '"case_state":{"case_meta":{"state_revision":7},'
            '"governance_state":{"release_status":"rfq_ready","rfq_admissibility":"ready","conflicts":[]},'
            '"rfq_state":{"rfq_admissibility":"ready"}}}\n\n'
        )
        yield "data: [DONE]\n\n"

    monkeypatch.setattr(
        "app.agent.api.router.event_generator",
        _fake_event_generator,
    )

    frames = _run(
        _collect_frames(
            endpoint._ssot_to_legacy_sse_stream(
                "hi",
                "case-1",
                current_user=_user(),
                request_id="req-1",
            )
        )
    )

    events = _parse_eventsource_events(frames)
    assert captured == {
        "message": "hi",
        "session_id": "case-1",
        "tenant_id": "tenant-1",
    }
    assert events["text_chunk"][0]["text"] == "Hallo"
    assert events["token"][0]["text"] == "Hallo"
    assert events["state_update"][0]["working_profile"] == {"medium": "water"}
    assert events["state_update"][0]["governance_metadata"]["release_status"] == "rfq_ready"
    assert events["state_update"][0]["governance_metadata"]["state_revision"] == 7
    assert events["done"][0]["type"] == "done"


def test_compat_stream_falls_back_to_raw_sealing_state_when_case_state_missing(monkeypatch):
    async def _fake_event_generator(request, *, current_user):
        del request, current_user
        yield (
            'data: {"type":"state_update","working_profile":{"medium":"water"},'
            '"sealing_state":{"governance":{"release_status":"approved","rfq_admissibility":"ready","conflicts":[]},'
            '"cycle":{"state_revision":9}}}\n\n'
        )
        yield "data: [DONE]\n\n"

    monkeypatch.setattr(
        "app.agent.api.router.event_generator",
        _fake_event_generator,
    )

    frames = _run(
        _collect_frames(
            endpoint._ssot_to_legacy_sse_stream(
                "hi",
                "case-legacy-fallback",
                current_user=_user(),
            )
        )
    )

    events = _parse_eventsource_events(frames)
    assert events["state_update"][0]["governance_metadata"]["release_status"] == "approved"
    assert events["state_update"][0]["governance_metadata"]["state_revision"] == 9
    assert events["state_update"][0]["governed_output_ready"] is True


def test_compat_stream_sanitizes_canonical_agent_errors(monkeypatch):
    async def _boom(_request, *, current_user):
        del current_user
        raise RuntimeError("secret runtime detail")
        yield  # pragma: no cover

    monkeypatch.setattr(
        "app.agent.api.router.event_generator",
        _boom,
    )

    frames = _run(
        _collect_frames(
            endpoint._ssot_to_legacy_sse_stream(
                "hi",
                "case-2",
                current_user=_user(),
                request_id="req-2",
            )
        )
    )

    events = _parse_eventsource_events(frames)
    assert events["error"][0]["message"] == "internal_error"
    assert events["error"][0]["request_id"] == "req-2"
    assert "secret runtime detail" not in json.dumps(events)
    assert events["done"][0]["type"] == "done"


def test_compat_chat_endpoint_is_disabled_by_default(monkeypatch):
    monkeypatch.setattr(endpoint, "ENABLE_COMPAT_CHAT", False)

    request = endpoint.LangGraphV2Request(chat_id="case-1", input="hi")
    raw_request = type("RawRequest", (), {"headers": {}})()

    with pytest.raises(endpoint.HTTPException) as exc_info:
        _run(
            endpoint.langgraph_chat_v2_endpoint(
                request,
                raw_request,
                _user(),
            )
        )

    assert exc_info.value.status_code == 410
    assert "/api/agent/chat/stream" in json.dumps(exc_info.value.detail)


async def _collect_frames(gen):
    frames = []
    async for frame in gen:
        frames.append(frame)
    return frames
