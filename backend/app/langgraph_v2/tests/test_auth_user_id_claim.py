import os
from fastapi import HTTPException
import pytest

os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5432")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("POSTGRES_SYNC_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("QDRANT_URL", "http://localhost:6333")
os.environ.setdefault("QDRANT_COLLECTION", "test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("NEXTAUTH_URL", "http://localhost:3000")
os.environ.setdefault("NEXTAUTH_SECRET", "test")
os.environ.setdefault("KEYCLOAK_ISSUER", "http://localhost:8080/realms/test")
os.environ.setdefault("KEYCLOAK_JWKS_URL", "http://localhost:8080/realms/test/protocol/openid-connect/certs")
os.environ.setdefault("KEYCLOAK_CLIENT_ID", "test")
os.environ.setdefault("KEYCLOAK_CLIENT_SECRET", "test")
os.environ.setdefault("KEYCLOAK_EXPECTED_AZP", "test")

from app.services.auth import dependencies


@pytest.mark.anyio
async def test_missing_user_id_claim_returns_401(monkeypatch):
    monkeypatch.delenv("AUTH_USER_ID_CLAIM", raising=False)

    def fake_verify(_token: str) -> dict:
        return {"preferred_username": "user1"}

    monkeypatch.setattr(dependencies, "verify_access_token", fake_verify)

    try:
        await dependencies.get_current_request_user(authorization="Bearer test-token")
    except HTTPException as exc:
        assert exc.status_code == 401
        detail = exc.detail or {}
        assert detail.get("code") == "missing_user_id_claim"
        assert detail.get("claim") == "sub"
    else:
        raise AssertionError("Expected HTTPException for missing user_id claim.")


@pytest.mark.anyio
async def test_strict_tenant_rejects_sub_as_tenant(monkeypatch):
    monkeypatch.setenv("AUTH_TENANT_ID_CLAIM", "tenant_id")

    def fake_verify(_token: str) -> dict:
        return {
            "sub": "user-1",
            "tenant_id": "user-1",
            "preferred_username": "user1",
        }

    monkeypatch.setattr(dependencies, "verify_access_token", fake_verify)

    try:
        await dependencies.get_current_request_user_strict_tenant(authorization="Bearer test-token")
    except HTTPException as exc:
        assert exc.status_code == 401
        detail = exc.detail or {}
        assert detail.get("code") == "tenant_id_invalid"
    else:
        raise AssertionError("Expected HTTPException for invalid tenant claim.")
@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
