from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any, Dict

import pytest
from fastapi import HTTPException
from starlette.requests import Request

sys.path.append(str(Path(__file__).resolve().parents[3]))

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
from app.services.auth.dependencies import RequestUser  # noqa: E402


class _Snapshot:
    def __init__(self, values: Dict[str, Any]):
        self.values = values


class _DummyGraph:
    def __init__(self, values: Dict[str, Any]):
        self.values = values
        self.checkpointer = object()

    async def aget_state(self, _config: Any):
        return _Snapshot(self.values)


def _request() -> Request:
    return Request({"type": "http", "headers": []})


def _user() -> RequestUser:
    return RequestUser(
        user_id="user-1",
        tenant_id="tenant-1",
        username="tester",
        sub="user-1",
        roles=[],
    )


def test_rfq_report_and_download_use_same_gate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    state = {
        "rfq_ready": True,
        "guardrail_escalation_level": "none",
        "failure_evidence_missing": False,
        "assumption_lock_hash": "abc",
        "assumption_lock_hash_confirmed": "def",
    }
    calls = {"count": 0}

    def _always_fail_gate(_values: Dict[str, Any]) -> bool:
        calls["count"] += 1
        return True

    async def _dummy_graph():
        return _DummyGraph(state)

    monkeypatch.setattr(endpoint, "get_sealai_graph_v2", _dummy_graph)
    monkeypatch.setattr(endpoint, "rfq_gate_failed", _always_fail_gate)

    with pytest.raises(HTTPException) as report_exc:
        asyncio.run(endpoint.rfq_report(_request(), chat_id="chat-1", user=_user()))
    assert report_exc.value.status_code == 409

    pdf = tmp_path / "offer.pdf"
    pdf.write_bytes(b"%PDF")
    with pytest.raises(HTTPException) as download_exc:
        asyncio.run(endpoint.rfq_download(_request(), path=str(pdf), chat_id="chat-1", user=_user()))
    assert download_exc.value.status_code == 409

    assert calls["count"] == 2
