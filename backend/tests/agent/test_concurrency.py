import asyncio
import os
import sys
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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

from app.services.history.persist import ConcurrencyConflictError, save_structured_case


def _mock_state(revision: int, parent_revision: int, cycle_id: str):
    return {
        "messages": [],
        "sealing_state": {"cycle": {"state_revision": revision, "snapshot_parent_revision": parent_revision, "analysis_cycle_id": cycle_id}},
        "working_profile": {},
        "relevant_fact_cards": [],
    }


def test_concurrency_conflict_detected():
    async def _run():
        state_a = _mock_state(6, 5, "cycle-A")
        state_b = _mock_state(6, 5, "cycle-B")
        mock_session = MagicMock()
        mock_session.get = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.add = MagicMock()
        mock_session_ctx = MagicMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_transcript = SimpleNamespace(
            user_id="user-test",
            metadata_json={"sealing_state": {"cycle": {"state_revision": 5, "snapshot_parent_revision": 4, "analysis_cycle_id": "cycle-initial"}}},
        )
        mock_session.get.side_effect = [None, mock_transcript]
        fake_db = types.SimpleNamespace(AsyncSessionLocal=lambda: mock_session_ctx)
        class FakeChatTranscript:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)

        fake_models = types.SimpleNamespace(ChatTranscript=FakeChatTranscript)
        with patch.dict(sys.modules, {"app.database": fake_db, "app.models.chat_transcript": fake_models}):
            await save_structured_case(tenant_id="tenant-test", owner_id="user-test", case_id="concurrency-test", state=state_a, runtime_path="test", binding_level="ORIENTATION")
            mock_transcript.metadata_json["sealing_state"]["cycle"]["state_revision"] = 6
            mock_transcript.metadata_json["sealing_state"]["cycle"]["analysis_cycle_id"] = "cycle-A"
            await save_structured_case(tenant_id="tenant-test", owner_id="user-test", case_id="concurrency-test", state=state_b, runtime_path="test", binding_level="ORIENTATION")

    with pytest.raises(ConcurrencyConflictError):
        asyncio.run(_run())
