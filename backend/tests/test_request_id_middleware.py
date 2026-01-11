import importlib
import os

from fastapi.testclient import TestClient


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


def test_request_id_header_is_added() -> None:
    _ensure_env()
    app_mod = importlib.import_module("app.main")
    client = TestClient(getattr(app_mod, "app"))

    res = client.get("/healthz")

    assert res.status_code == 200
    assert res.headers.get("X-Request-Id")


def test_request_id_header_is_echoed() -> None:
    _ensure_env()
    app_mod = importlib.import_module("app.main")
    client = TestClient(getattr(app_mod, "app"))

    res = client.get("/healthz", headers={"X-Request-Id": "req-123"})

    assert res.status_code == 200
    assert res.headers.get("X-Request-Id") == "req-123"
