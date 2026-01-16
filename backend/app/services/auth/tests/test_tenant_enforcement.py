
import os
import sys
from unittest import mock

# PRE-PATCH Environment to satisfy Pydantic Settings on import
os.environ.setdefault("POSTGRES_USER", "unused")
os.environ.setdefault("POSTGRES_PASSWORD", "unused")
os.environ.setdefault("POSTGRES_HOST", "unused")
os.environ.setdefault("POSTGRES_PORT", "5432")
os.environ.setdefault("POSTGRES_DB", "unused")
os.environ.setdefault("OPENAI_API_KEY", "unused")
os.environ.setdefault("QDRANT_URL", "http://unused")
os.environ.setdefault("QDRANT_COLLECTION", "unused")
os.environ.setdefault("REDIS_URL", "redis://unused")
os.environ.setdefault("KEYCLOAK_JWKS_URL", "http://unused")
os.environ.setdefault("KEYCLOAK_EXPECTED_AZP", "unused")
os.environ.setdefault("BACKEND_KEYCLOAK_ISSUER", "http://unused")
os.environ.setdefault("KEYCLOAK_CLIENT_ID", "unused")

import pytest
from fastapi import HTTPException
from app.services.auth.dependencies import RequestUser, canonical_tenant_id

@mock.patch.dict(os.environ, {}, clear=True)
def test_canonical_tenant_id_valid():
    """RequestUser has tenant_id -> return it directly (No Env check needed)."""
    user = RequestUser(
        user_id="u01",
        username="test",
        sub="u01",
        roles=[],
        tenant_id="t01"
    )
    assert canonical_tenant_id(user) == "t01"

@mock.patch.dict(os.environ, {"ALLOW_TENANT_FALLBACK": "1"}, clear=True)
def test_canonical_tenant_id_fallback_enabled():
    """RequestUser has NO tenant_id, but Fallback=1 -> return user_id."""
    user = RequestUser(
        user_id="u01",
        username="test",
        sub="u01",
        roles=[],
        tenant_id=None
    )
    assert canonical_tenant_id(user) == "u01"

@mock.patch.dict(os.environ, {"ALLOW_TENANT_FALLBACK": "0"}, clear=True)
def test_canonical_tenant_id_fallback_disabled_explicit():
    """RequestUser has NO tenant_id, Fallback=0 -> Raise 403."""
    user = RequestUser(
        user_id="u01",
        username="test",
        sub="u01",
        roles=[],
        tenant_id=None
    )
    with pytest.raises(HTTPException) as exc:
        canonical_tenant_id(user)
    assert exc.value.status_code == 403
    assert "missing_tenant" in str(exc.value.detail)

@mock.patch.dict(os.environ, {}, clear=True)
def test_canonical_tenant_id_fallback_disabled_implicit():
    """RequestUser has NO tenant_id, No Env var -> Raise 403."""
    user = RequestUser(
        user_id="u01",
        username="test",
        sub="u01",
        roles=[],
        tenant_id=None
    )
    with pytest.raises(HTTPException) as exc:
        canonical_tenant_id(user)
    assert exc.value.status_code == 403
