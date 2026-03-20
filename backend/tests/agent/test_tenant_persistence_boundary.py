import asyncio
import os
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

for key, value in {
    "postgres_user": "test",
    "postgres_password": "test",
    "postgres_host": "localhost",
    "postgres_port": "5432",
    "postgres_db": "test",
    "database_url": "sqlite+aiosqlite:///tmp.db",
    "POSTGRES_SYNC_URL": "sqlite:///tmp.db",
    "openai_api_key": "test",
    "qdrant_url": "http://localhost",
    "redis_url": "redis://localhost:6379/0",
    "nextauth_url": "http://localhost",
    "nextauth_secret": "secret",
    "keycloak_issuer": "http://localhost",
    "keycloak_jwks_url": "http://localhost/jwks",
    "keycloak_client_id": "client",
    "keycloak_client_secret": "secret",
    "keycloak_expected_azp": "client",
}.items():
    os.environ.setdefault(key, value)

from app.services.history.persist import (
    STRUCTURED_CASE_RECORD_TYPE,
    _build_legacy_storage_key,
    _build_structured_case_payload,
    build_structured_case_storage_key,
    delete_structured_case,
    load_structured_case,
)


def _state(tenant_id="tenant-a"):
    return {"messages": [], "sealing_state": {"cycle": {}}, "working_profile": {}, "relevant_fact_cards": [], "tenant_id": tenant_id}


def _meta(tenant_id="tenant-a", owner_id="user-1", case_id="case-1"):
    return {
        "record_type": STRUCTURED_CASE_RECORD_TYPE,
        "case_id": case_id,
        "session_id": case_id,
        "owner_id": owner_id,
        "runtime_path": "STRUCTURED_QUALIFICATION",
        "binding_level": "ORIENTATION",
        "sealing_state": {"cycle": {}},
        "case_state": None,
        "working_profile": {},
        "relevant_fact_cards": [],
        "messages": [],
        "tenant_id": tenant_id,
    }


def test_storage_key_is_tenant_scoped():
    assert build_structured_case_storage_key("tenant-a", "user-1", "case-1") == "agent_case:tenant-a:user-1:case-1"
    assert _build_legacy_storage_key("user-1", "case-1") == "agent_case:user-1:case-1"


def test_build_payload_carries_explicit_tenant_id():
    payload = _build_structured_case_payload(tenant_id="caller-tenant", owner_id="user-1", case_id="case-1", state=_state("state-tenant"), runtime_path="STRUCTURED_QUALIFICATION", binding_level="ORIENTATION")
    assert payload.tenant_id == "caller-tenant"


def test_load_structured_case_fails_closed_on_tenantless_legacy_record():
    transcript = MagicMock()
    transcript.user_id = "user-1"
    transcript.metadata_json = _meta(None)
    session = AsyncMock()
    session.get = AsyncMock(side_effect=[None, transcript])
    session_ctx = MagicMock()
    session_ctx.__aenter__ = AsyncMock(return_value=session)
    session_ctx.__aexit__ = AsyncMock(return_value=False)
    fake_db = types.SimpleNamespace(AsyncSessionLocal=lambda: session_ctx)
    fake_models = types.SimpleNamespace(ChatTranscript=type("ChatTranscript", (), {}))
    with patch.dict(sys.modules, {"app.database": fake_db, "app.models.chat_transcript": fake_models}):
        result = asyncio.run(load_structured_case(tenant_id="tenant-a", owner_id="user-1", case_id="case-1"))
    assert result is None


def test_delete_structured_case_uses_tenant_scoped_key_first():
    session = AsyncMock()
    session.get = AsyncMock(return_value=None)
    session_ctx = MagicMock()
    session_ctx.__aenter__ = AsyncMock(return_value=session)
    session_ctx.__aexit__ = AsyncMock(return_value=False)
    fake_chat_transcript = type("ChatTranscript", (), {})
    fake_db = types.SimpleNamespace(AsyncSessionLocal=lambda: session_ctx)
    fake_models = types.SimpleNamespace(ChatTranscript=fake_chat_transcript)
    with patch.dict(sys.modules, {"app.database": fake_db, "app.models.chat_transcript": fake_models}):
        asyncio.run(delete_structured_case(tenant_id="tenant-a", owner_id="user-1", case_id="case-1"))
    assert session.get.await_args_list[0].args == (fake_chat_transcript, "agent_case:tenant-a:user-1:case-1")
