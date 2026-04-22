from __future__ import annotations

import asyncio
import json
import datetime as dt
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Dict, List, Tuple

import pytest

pytest.skip('legacy SSE contract expects pre-SSoT router private APIs; migrate to app.agent.api.streaming contract tests', allow_module_level=True)


def _parse_sse_frames(frames: List[str]) -> List[Tuple[str, Dict[str, Any]]]:
    parsed: List[Tuple[str, Dict[str, Any]]] = []
    for frame in frames:
        event = None
        data = None
        for line in frame.splitlines():
            if line.startswith("event:"):
                event = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                raw = line.split(":", 1)[1].strip()
                data = json.loads(raw)
        if event is None or data is None:
            continue
        parsed.append((event, data))
    return parsed


def _parse_agent_data_frames(frames: List[str]) -> List[Dict[str, Any]]:
    parsed: List[Dict[str, Any]] = []
    for frame in frames:
        if not frame.startswith("data: "):
            continue
        raw = frame[6:].strip()
        if raw == "[DONE]":
            parsed.append({"type": "__DONE__"})
            continue
        parsed.append(json.loads(raw))
    return parsed


def _set_minimal_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # app.core.config.Settings has many required fields; set minimal dummy values so that
    # importing API endpoints does not fail during settings initialization.
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
    monkeypatch.setenv("keycloak_jwks_url", "http://localhost:8080/realms/test/protocol/openid-connect/certs")
    monkeypatch.setenv("keycloak_client_id", "dummy")
    monkeypatch.setenv("keycloak_client_secret", "dummy")
    monkeypatch.setenv("keycloak_expected_azp", "dummy")


@dataclass
class _Snapshot:
    values: Dict[str, Any]


class _DummyGraph:
    def __init__(self, events: List[Dict[str, Any]], final_values: Dict[str, Any]):
        self._events = list(events)
        self._final_values = dict(final_values)

    async def astream_events(self, *_args: Any, **_kwargs: Any) -> AsyncGenerator[Dict[str, Any], None]:
        for item in self._events:
            await asyncio.sleep(0)
            yield item

    async def aget_state(self, *_args: Any, **_kwargs: Any) -> _Snapshot:
        return _Snapshot(values=self._final_values)


async def _collect_async(gen: AsyncGenerator[str, None]) -> List[str]:
    chunks: List[str] = []
    async for item in gen:
        chunks.append(item)
    return chunks


def test_agent_stream_emits_done_once_and_is_last_for_normal_run(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_minimal_settings_env(monkeypatch)
    from app.agent.api import router as endpoint
    from app.agent.api.models import ChatRequest
    from app.services.auth.dependencies import RequestUser

    class _EnumLike(str):
        @property
        def value(self) -> str:
            return str(self)

    decision = type(
        "Decision",
        (),
        {
            "path": _EnumLike("structured"),
            "result_form": _EnumLike("state_update"),
            "runtime_path": "STRUCTURED_QUALIFICATION",
            "binding_level": "ORIENTATION",
        },
    )()

    async def _fake_prepare(*_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        return {
            "messages": [],
            "sealing_state": {"cycle": {"state_revision": 1, "analysis_cycle_id": "cycle-1"}},
            "working_profile": {},
        }

    async def _fake_policy(*_args: Any, **_kwargs: Any) -> Any:
        return decision

    async def _fake_sse_gen(*_args: Any, **_kwargs: Any) -> AsyncGenerator[str, None]:
        yield 'data: {"type":"text_chunk","text":"Hallo"}\n\n'
        yield (
            'data: {"type":"state_update","reply":"Hallo","policy_path":"structured",'
            '"run_meta":{"policy_version":"interaction_policy_v1"},'
            '"response_class":"governed_state_update",'
            '"structured_state":{"case_status":"withheld_review","output_status":"withheld_review",'
            '"next_step":"human_review","primary_allowed_action":"await_review","active_blockers":["review_pending"]},'
            '"case_state":{"case_meta":{"analysis_cycle_id":"cycle-1"}},'
            '"working_profile":{"medium":"water"},"sealing_state":null}\n\n'
        )
        yield "data: [DONE]\n\n"

    monkeypatch.setattr(endpoint, "evaluate_interaction_policy_async", _fake_policy, raising=False)
    monkeypatch.setattr(endpoint, "agent_sse_generator", _fake_sse_gen)

    user = RequestUser(user_id="user-1", username="tester", sub="user-1", roles=[], scopes=[], tenant_id="tenant-1")
    frames = asyncio.run(
        _collect_async(
            endpoint.event_generator(
                ChatRequest(message="Hi", session_id="t1"),
                current_user=user,
            )
        )
    )
    events = _parse_agent_data_frames(frames)
    assert [evt["type"] for evt in events] == ["text_chunk", "state_update", "__DONE__"]


def test_agent_stream_emits_error_then_done_and_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_minimal_settings_env(monkeypatch)
    from app.agent.api import router as endpoint
    from app.agent.api.models import ChatRequest
    from app.services.auth.dependencies import RequestUser

    class _EnumLike(str):
        @property
        def value(self) -> str:
            return str(self)

    decision = type(
        "Decision",
        (),
        {
            "path": _EnumLike("structured"),
            "result_form": _EnumLike("state_update"),
            "runtime_path": "STRUCTURED_QUALIFICATION",
            "binding_level": "ORIENTATION",
        },
    )()

    async def _fake_prepare(*_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        return {
            "messages": [],
            "sealing_state": {"cycle": {"state_revision": 1, "analysis_cycle_id": "cycle-1"}},
            "working_profile": {},
        }

    async def _fake_policy(*_args: Any, **_kwargs: Any) -> Any:
        return decision

    async def _fake_sse_gen(*_args: Any, **_kwargs: Any) -> AsyncGenerator[str, None]:
        yield 'data: {"type":"error","message":"boom"}\n\n'
        yield "data: [DONE]\n\n"

    monkeypatch.setattr(endpoint, "evaluate_interaction_policy_async", _fake_policy, raising=False)
    monkeypatch.setattr(endpoint, "agent_sse_generator", _fake_sse_gen)

    user = RequestUser(user_id="user-1", username="tester", sub="user-1", roles=[], scopes=[], tenant_id="tenant-1")
    frames = asyncio.run(
        _collect_async(
            endpoint.event_generator(
                ChatRequest(message="Hi", session_id="t1"),
                current_user=user,
            )
        )
    )
    events = _parse_agent_data_frames(frames)
    assert [evt["type"] for evt in events] == ["error", "__DONE__"]


def test_agent_stream_state_update_public_minimum_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_minimal_settings_env(monkeypatch)
    from app.agent.api import router as endpoint
    from app.agent.api.models import ChatRequest
    from app.services.auth.dependencies import RequestUser

    class _EnumLike(str):
        @property
        def value(self) -> str:
            return str(self)

    decision = type(
        "Decision",
        (),
        {
            "path": _EnumLike("structured"),
            "result_form": _EnumLike("state_update"),
            "runtime_path": "STRUCTURED_QUALIFICATION",
            "binding_level": "ORIENTATION",
        },
    )()
    state = {
        "messages": [],
        "sealing_state": {"cycle": {"state_revision": 1, "analysis_cycle_id": "cycle-1"}},
        "working_profile": {},
    }

    async def _fake_sse_gen(*_args: Any, **_kwargs: Any) -> AsyncGenerator[str, None]:
        yield 'data: {"type":"text_chunk","text":"Hallo"}\n\n'
        yield (
            'data: {"type":"state_update","reply":"Hallo","policy_path":"structured",'
            '"run_meta":{"policy_version":"interaction_policy_v1"},'
            '"response_class":"governed_state_update",'
            '"structured_state":{"case_status":"withheld_review","output_status":"withheld_review",'
            '"next_step":"human_review","primary_allowed_action":"await_review","active_blockers":["review_pending"]},'
            '"case_state":{"case_meta":{"analysis_cycle_id":"cycle-1"}},'
            '"working_profile":{"medium":"water"},"sealing_state":null}\n\n'
        )
        yield "data: [DONE]\n\n"

    user = RequestUser(
        user_id="user-1",
        username="tester",
        sub="user-1",
        roles=[],
        scopes=[],
        tenant_id="tenant-1",
    )

    async def _fake_prepare(*_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        return state

    async def _fake_policy(*_args: Any, **_kwargs: Any) -> Any:
        return decision

    monkeypatch.setattr(endpoint, "evaluate_interaction_policy_async", _fake_policy, raising=False)
    monkeypatch.setattr(endpoint, "agent_sse_generator", _fake_sse_gen)

    frames = asyncio.run(
        _collect_async(
            endpoint.event_generator(
                ChatRequest(message="Bitte prüfen", session_id="case-1"),
                current_user=user,
            )
        )
    )
    parsed = _parse_agent_data_frames(frames)

    assert [item["type"] for item in parsed] == ["text_chunk", "state_update", "__DONE__"]
    assert parsed[0] == {"type": "text_chunk", "text": "Hallo"}
    state_update = parsed[1]
    assert set(state_update.keys()) == {
        "type",
        "reply",
        "policy_path",
        "run_meta",
        "response_class",
        "structured_state",
        "case_state",
        "working_profile",
        "sealing_state",
    }
    assert state_update["response_class"] == "governed_state_update"
    assert state_update["structured_state"]["primary_allowed_action"] == "await_review"
    assert state_update["run_meta"]["policy_version"] == "interaction_policy_v1"
    assert state_update["sealing_state"] is None
