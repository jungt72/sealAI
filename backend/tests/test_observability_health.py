from __future__ import annotations

import asyncio
import os
import sys
import types


for key, value in {
    "POSTGRES_USER": "sealai",
    "POSTGRES_PASSWORD": "secret",
    "POSTGRES_HOST": "localhost",
    "POSTGRES_PORT": "5432",
    "POSTGRES_DB": "sealai",
    "DATABASE_URL": "postgresql+asyncpg://sealai:secret@localhost:5432/sealai",
    "POSTGRES_SYNC_URL": "postgresql://sealai:secret@localhost:5432/sealai",
    "OPENAI_API_KEY": "test-key",
    "QDRANT_URL": "http://localhost:6333",
    "QDRANT_COLLECTION": "sealai",
    "REDIS_URL": "redis://localhost:6379/0",
    "NEXTAUTH_URL": "http://localhost:3000",
    "NEXTAUTH_SECRET": "dummy-secret",
    "KEYCLOAK_ISSUER": "http://localhost:8080/realms/test",
    "KEYCLOAK_JWKS_URL": "http://localhost:8080/realms/test/protocol/openid-connect/certs",
    "KEYCLOAK_CLIENT_ID": "sealai-backend",
    "KEYCLOAK_CLIENT_SECRET": "client-secret",
    "KEYCLOAK_EXPECTED_AZP": "sealai-frontend",
}.items():
    os.environ.setdefault(key, value)

os.environ.setdefault("postgres_user", "sealai")
os.environ.setdefault("postgres_password", "secret")
os.environ.setdefault("postgres_host", "localhost")
os.environ.setdefault("postgres_port", "5432")
os.environ.setdefault("postgres_db", "sealai")
os.environ.setdefault("database_url", "sqlite+aiosqlite:///tmp.db")
os.environ.setdefault("POSTGRES_SYNC_URL", "sqlite:///tmp.db")
os.environ.setdefault("openai_api_key", "test-key")
os.environ.setdefault("qdrant_url", "http://localhost:6333")
os.environ.setdefault("qdrant_collection", "sealai")
os.environ.setdefault("redis_url", "redis://localhost:6379/0")
os.environ.setdefault("nextauth_url", "http://localhost:3000")
os.environ.setdefault("nextauth_secret", "dummy-secret")
os.environ.setdefault("keycloak_issuer", "http://localhost:8080/realms/test")
os.environ.setdefault("keycloak_jwks_url", "http://localhost:8080/realms/test/protocol/openid-connect/certs")
os.environ.setdefault("keycloak_client_id", "sealai-backend")
os.environ.setdefault("keycloak_client_secret", "client-secret")
os.environ.setdefault("keycloak_expected_azp", "sealai-frontend")


class _MetricStub:
    def labels(self, **_: object) -> "_MetricStub":
        return self

    def set(self, *_: object, **__: object) -> None:
        return None

    def inc(self, *_: object, **__: object) -> None:
        return None

    def observe(self, *_: object, **__: object) -> None:
        return None


if "prometheus_client" not in sys.modules:
    prometheus_client = types.ModuleType("prometheus_client")
    prometheus_client.Counter = lambda *args, **kwargs: _MetricStub()
    prometheus_client.Gauge = lambda *args, **kwargs: _MetricStub()
    prometheus_client.Histogram = lambda *args, **kwargs: _MetricStub()
    sys.modules["prometheus_client"] = prometheus_client

from app.api.v1.endpoints.langgraph_health import langgraph_health
from app.observability.health import check_agent_runtime, run_all_health_checks


def _run(coro):
    return asyncio.run(coro)


def test_check_agent_runtime_validates_canonical_agent_surface():
    result = _run(check_agent_runtime())

    assert result["status"] == "healthy"
    assert result["service"] == "sealai-agent"
    assert "/health" in result["routes_checked"]
    assert "/chat" in result["routes_checked"]


def test_run_all_health_checks_reports_agent_runtime(monkeypatch):
    async def _healthy(name: str):
        return {"status": "healthy", "name": name}

    monkeypatch.setattr(
        "app.observability.health.check_redis",
        lambda: _healthy("redis"),
    )
    monkeypatch.setattr(
        "app.observability.health.check_qdrant",
        lambda: _healthy("qdrant"),
    )
    monkeypatch.setattr(
        "app.observability.health.check_agent_runtime",
        lambda: _healthy("agent_runtime"),
    )

    result = _run(run_all_health_checks())

    assert result["status"] == "healthy"
    assert "agent_runtime" in result["checks"]
    assert "graph" not in result["checks"]


def test_langgraph_health_is_compatibility_alias_of_agent_health():
    payload = _run(langgraph_health())

    assert payload["status"] == "ok"
    assert payload["service"] == "sealai-agent"
    assert payload["compatibility_alias"] is True
    assert payload["canonical_path"] == "/api/agent/health"
