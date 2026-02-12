from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any, Dict

import pytest
from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import FileResponse

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


def test_rfq_export_blocked_when_not_ready(monkeypatch, tmp_path: Path) -> None:
    dummy = DummyGraph(
        {
            "rfq_ready": False,
            "guardrail_escalation_level": "none",
            "failure_evidence_missing": False,
            "assumption_lock_hash": "abc",
            "assumption_lock_hash_confirmed": "abc",
        }
    )

    async def _dummy_graph():
        return dummy

    monkeypatch.setattr(endpoint, "get_sealai_graph_v2", _dummy_graph)

    pdf = tmp_path / "offer.pdf"
    pdf.write_bytes(b"%PDF")
    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(endpoint.rfq_download(_request(), path=str(pdf), chat_id="chat-1", user=_user()))
    assert excinfo.value.status_code == 409
    assert excinfo.value.detail["code"] == "rfq_not_ready"


def test_rfq_export_blocked_when_hash_mismatch(monkeypatch, tmp_path: Path) -> None:
    dummy = DummyGraph(
        {
            "rfq_ready": True,
            "guardrail_escalation_level": "none",
            "failure_evidence_missing": False,
            "assumption_lock_hash": "abc",
            "assumption_lock_hash_confirmed": "def",
        }
    )

    async def _dummy_graph():
        return dummy

    monkeypatch.setattr(endpoint, "get_sealai_graph_v2", _dummy_graph)

    pdf = tmp_path / "offer.pdf"
    pdf.write_bytes(b"%PDF")
    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(endpoint.rfq_download(_request(), path=str(pdf), chat_id="chat-1", user=_user()))
    assert excinfo.value.status_code == 409
    assert excinfo.value.detail["code"] == "rfq_not_ready"


def test_rfq_export_allowed_when_ready_and_hash_confirmed(monkeypatch, tmp_path: Path) -> None:
    dummy = DummyGraph(
        {
            "rfq_ready": True,
            "guardrail_escalation_level": "none",
            "failure_evidence_missing": False,
            "assumption_lock_hash": "abc",
            "assumption_lock_hash_confirmed": "abc",
        }
    )

    async def _dummy_graph():
        return dummy

    monkeypatch.setattr(endpoint, "get_sealai_graph_v2", _dummy_graph)

    pdf = tmp_path / "offer.pdf"
    pdf.write_bytes(b"%PDF")
    response = asyncio.run(endpoint.rfq_download(_request(), path=str(pdf), chat_id="chat-1", user=_user()))
    assert isinstance(response, FileResponse)

    expected_checkpoint_id = resolve_checkpoint_thread_id(
        tenant_id="tenant-1",
        user_id="user-1",
        chat_id="chat-1",
    )
    assert isinstance(dummy.last_config, dict)
    assert dummy.last_config is not None
    assert dummy.last_config.get("configurable", {}).get("thread_id") == expected_checkpoint_id
