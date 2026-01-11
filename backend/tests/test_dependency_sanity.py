from __future__ import annotations

import importlib
import os

from importlib import metadata


_ENV_DEFAULTS = {
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
}


def _ensure_env() -> None:
    for key, value in _ENV_DEFAULTS.items():
        os.environ.setdefault(key, value)


def _major(version: str) -> int:
    try:
        return int(version.split(".")[0])
    except Exception:
        return 0


def test_dependency_imports_and_versions() -> None:
    _ensure_env()

    import fastapi  # noqa: F401
    import starlette  # noqa: F401
    import pydantic  # noqa: F401
    import langgraph  # noqa: F401
    from langgraph.checkpoint import redis as lg_redis  # noqa: F401
    import qdrant_client  # noqa: F401
    import redis  # noqa: F401
    import redis.asyncio  # noqa: F401
    import httpx  # noqa: F401

    assert _major(pydantic.__version__) == 2
    assert _major(fastapi.__version__) >= 0
    assert _major(starlette.__version__) >= 0

    assert metadata.version("langgraph")
    assert metadata.version("langgraph-checkpoint-redis")


def test_core_modules_import() -> None:
    _ensure_env()
    importlib.import_module("app.main")
    importlib.import_module("app.api.v1.endpoints.langgraph_v2")
    importlib.import_module("app.services.rag.rag_orchestrator")
