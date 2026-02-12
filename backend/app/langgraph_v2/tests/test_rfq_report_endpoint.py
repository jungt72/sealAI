from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

import pytest
from fastapi import HTTPException
from starlette.requests import Request

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

from app.api.v1.endpoints import rfq as endpoint  # noqa: E402
from app.langgraph_v2.utils.threading import resolve_checkpoint_thread_id  # noqa: E402
from app.services.auth.dependencies import RequestUser  # noqa: E402


def _request() -> Request:
    return Request({"type": "http", "headers": []})


class _Snapshot:
    def __init__(self, values: Dict[str, Any]):
        self.values = values


class DummyGraph:
    def __init__(self, values: Dict[str, Any]):
        self.values = values
        self.checkpointer = object()
        self.last_config: Dict[str, Any] | None = None

    async def aget_state(self, config: Any):
        self.last_config = dict(config or {})
        return _Snapshot(self.values)


def _user() -> RequestUser:
    return RequestUser(
        user_id="user-1",
        tenant_id="tenant-1",
        username="tester",
        sub="user-1",
        roles=[],
    )


def _ready_state() -> Dict[str, Any]:
    return {
        "rfq_ready": True,
        "guardrail_escalation_level": "none",
        "failure_evidence_missing": False,
        "assumption_lock_hash": "abc",
        "assumption_lock_hash_confirmed": "abc",
        "guardrail_coverage": {"pv_limit": {"status": "confirmed"}},
        "guardrail_rag_coverage": {},
        "risk_heatmap": {"pv_limit": "high"},
        "assumption_list": [{"id": "1", "text": "A", "impact": "high", "source": "inferred", "requires_confirmation": True}],
        "pending_assumptions": [],
        "assumptions_confirmed": True,
        "parameters": {"pressure_bar": 5.0, "speed_rpm": 1000.0, "shaft_diameter": 40.0},
        "recommendation": {"summary": "ready", "risk_hints": []},
    }


def test_rfq_report_endpoint_blocked_when_not_ready(monkeypatch) -> None:
    dummy = DummyGraph({**_ready_state(), "rfq_ready": False})

    async def _dummy_graph():
        return dummy

    monkeypatch.setattr(endpoint, "get_sealai_graph_v2", _dummy_graph)

    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(endpoint.rfq_report(_request(), chat_id="chat-1", user=_user()))
    assert excinfo.value.status_code == 409
    assert excinfo.value.detail["code"] == "rfq_not_ready"


def test_rfq_report_endpoint_blocked_when_hash_mismatch(monkeypatch) -> None:
    dummy = DummyGraph({**_ready_state(), "assumption_lock_hash_confirmed": "def"})

    async def _dummy_graph():
        return dummy

    monkeypatch.setattr(endpoint, "get_sealai_graph_v2", _dummy_graph)

    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(endpoint.rfq_report(_request(), chat_id="chat-1", user=_user()))
    assert excinfo.value.status_code == 409
    assert excinfo.value.detail["code"] == "rfq_not_ready"


def test_rfq_report_endpoint_blocked_when_escalated(monkeypatch) -> None:
    dummy = DummyGraph({**_ready_state(), "guardrail_escalation_level": "human_required"})

    async def _dummy_graph():
        return dummy

    monkeypatch.setattr(endpoint, "get_sealai_graph_v2", _dummy_graph)

    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(endpoint.rfq_report(_request(), chat_id="chat-1", user=_user()))
    assert excinfo.value.status_code == 409
    assert excinfo.value.detail["code"] == "rfq_not_ready"


def test_rfq_report_endpoint_returns_report_and_uses_checkpoint_scope(monkeypatch) -> None:
    dummy = DummyGraph(_ready_state())

    async def _dummy_graph():
        return dummy

    monkeypatch.setattr(endpoint, "get_sealai_graph_v2", _dummy_graph)

    response = asyncio.run(endpoint.rfq_report(_request(), chat_id="chat-1", user=_user()))
    payload = json.loads(response.body.decode("utf-8"))
    assert payload["meta"]["rfq_ready"] is True
    assert payload["meta"]["chat_id"] == "chat-1"
    assert payload["risk"]["guardrail_escalation_level"] == "none"

    expected_checkpoint_id = resolve_checkpoint_thread_id(
        tenant_id="tenant-1",
        user_id="user-1",
        chat_id="chat-1",
    )
    assert dummy.last_config is not None
    assert dummy.last_config.get("configurable", {}).get("thread_id") == expected_checkpoint_id
