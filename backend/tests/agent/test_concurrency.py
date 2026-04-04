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

from app.services.history.persist import (
    ConcurrencyConflictError,
    _extract_case_meta_concurrency_token,
    _extract_persisted_concurrency_token,
    _resolve_lock_comparison_token,
    _resolve_preferred_concurrency_token,
    _extract_sealing_cycle_concurrency_token,
    _verify_concurrency_token_parity,
    save_structured_case,
)


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


def test_extract_sealing_cycle_concurrency_token_reads_current_fields_only():
    token = _extract_sealing_cycle_concurrency_token(
        {
            "sealing_state": {
                "cycle": {
                    "state_revision": 6,
                    "snapshot_parent_revision": 5,
                    "analysis_cycle_id": "cycle-A",
                    "ignored_extra": "x",
                }
            }
        }
    )

    assert token == {
        "state_revision": 6,
        "snapshot_parent_revision": 5,
        "analysis_cycle_id": "cycle-A",
    }


def test_extract_case_meta_and_persisted_concurrency_tokens_read_same_bridge_fields():
    payload = {
        "case_state": {
            "case_meta": {
                "state_revision": 6,
                "snapshot_parent_revision": 5,
                "analysis_cycle_id": "cycle-A",
                "ignored_extra": "x",
            }
        },
        "persisted_concurrency_token": {
            "state_revision": 6,
            "snapshot_parent_revision": 5,
            "analysis_cycle_id": "cycle-A",
            "ignored_extra": "x",
        },
    }

    assert _extract_case_meta_concurrency_token(payload) == {
        "state_revision": 6,
        "snapshot_parent_revision": 5,
        "analysis_cycle_id": "cycle-A",
    }
    assert _extract_persisted_concurrency_token(payload) == {
        "state_revision": 6,
        "snapshot_parent_revision": 5,
        "analysis_cycle_id": "cycle-A",
    }


def test_resolve_preferred_concurrency_token_prefers_case_meta_then_persisted_then_sealing_cycle():
    assert _resolve_preferred_concurrency_token(
        {
            "case_state": {"case_meta": {"state_revision": 7, "snapshot_parent_revision": 6, "analysis_cycle_id": "case-cycle"}},
            "persisted_concurrency_token": {"state_revision": 5, "snapshot_parent_revision": 4, "analysis_cycle_id": "persisted-cycle"},
            "sealing_state": {"cycle": {"state_revision": 3, "snapshot_parent_revision": 2, "analysis_cycle_id": "sealing-cycle"}},
        }
    ) == {
        "state_revision": 7,
        "snapshot_parent_revision": 6,
        "analysis_cycle_id": "case-cycle",
    }

    assert _resolve_preferred_concurrency_token(
        {
            "persisted_concurrency_token": {"state_revision": 5, "snapshot_parent_revision": 4, "analysis_cycle_id": "persisted-cycle"},
            "sealing_state": {"cycle": {"state_revision": 3, "snapshot_parent_revision": 2, "analysis_cycle_id": "sealing-cycle"}},
        }
    ) == {
        "state_revision": 5,
        "snapshot_parent_revision": 4,
        "analysis_cycle_id": "persisted-cycle",
    }

    assert _resolve_preferred_concurrency_token(
        {
            "sealing_state": {"cycle": {"state_revision": 3, "snapshot_parent_revision": 2, "analysis_cycle_id": "sealing-cycle"}},
        }
    ) == {
        "state_revision": 3,
        "snapshot_parent_revision": 2,
        "analysis_cycle_id": "sealing-cycle",
    }


def test_verify_concurrency_token_parity_warns_but_does_not_switch_authority(caplog: pytest.LogCaptureFixture):
    caplog.set_level("WARNING")

    preferred = _verify_concurrency_token_parity(
        {
            "case_state": {"case_meta": {"state_revision": 7, "snapshot_parent_revision": 6, "analysis_cycle_id": "case-cycle"}},
            "sealing_state": {"cycle": {"state_revision": 3, "snapshot_parent_revision": 2, "analysis_cycle_id": "sealing-cycle"}},
        },
        source_label="test-source",
    )

    assert preferred == {
        "state_revision": 7,
        "snapshot_parent_revision": 6,
        "analysis_cycle_id": "case-cycle",
    }
    assert "Concurrency token parity mismatch for test-source" in caplog.text


def test_resolve_lock_comparison_token_prefers_complete_bridge_token_and_falls_back_when_incomplete(
    caplog: pytest.LogCaptureFixture,
):
    caplog.set_level("WARNING")

    assert _resolve_lock_comparison_token(
        {
            "case_state": {"case_meta": {"state_revision": 7, "snapshot_parent_revision": 6, "analysis_cycle_id": "case-cycle"}},
            "sealing_state": {"cycle": {"state_revision": 3, "snapshot_parent_revision": 2, "analysis_cycle_id": "sealing-cycle"}},
        },
        source_label="preferred-complete",
    ) == {
        "state_revision": 7,
        "snapshot_parent_revision": 6,
        "analysis_cycle_id": "case-cycle",
    }

    assert _resolve_lock_comparison_token(
        {
            "case_state": {"case_meta": {"state_revision": 7, "analysis_cycle_id": "case-cycle"}},
            "sealing_state": {"cycle": {"state_revision": 3, "snapshot_parent_revision": 2, "analysis_cycle_id": "sealing-cycle"}},
        },
        source_label="preferred-incomplete",
    ) == {
        "state_revision": 3,
        "snapshot_parent_revision": 2,
        "analysis_cycle_id": "sealing-cycle",
    }


def test_concurrency_comparison_prefers_bridge_token_over_stale_raw_cycle():
    async def _run():
        state_a = _mock_state(6, 5, "cycle-A")
        state_b = _mock_state(6, 5, "cycle-B")
        state_b["case_state"] = {
            "case_meta": {
                "state_revision": 6,
                "snapshot_parent_revision": 5,
                "analysis_cycle_id": "cycle-B",
            }
        }
        mock_session = MagicMock()
        mock_session.get = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.add = MagicMock()
        mock_session_ctx = MagicMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_transcript = SimpleNamespace(
            user_id="user-test",
            metadata_json={
                "sealing_state": {"cycle": {"state_revision": 5, "snapshot_parent_revision": 4, "analysis_cycle_id": "cycle-initial"}},
                "case_state": {"case_meta": {"state_revision": 5, "snapshot_parent_revision": 4, "analysis_cycle_id": "cycle-A"}},
                "persisted_concurrency_token": {"state_revision": 5, "snapshot_parent_revision": 4, "analysis_cycle_id": "cycle-A"},
            },
        )
        mock_session.get.side_effect = [None, mock_transcript]
        fake_db = types.SimpleNamespace(AsyncSessionLocal=lambda: mock_session_ctx)

        class FakeChatTranscript:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)

        fake_models = types.SimpleNamespace(ChatTranscript=FakeChatTranscript)
        with patch.dict(sys.modules, {"app.database": fake_db, "app.models.chat_transcript": fake_models}):
            await save_structured_case(
                tenant_id="tenant-test",
                owner_id="user-test",
                case_id="concurrency-test",
                state=state_a,
                runtime_path="test",
                binding_level="ORIENTATION",
            )
            mock_transcript.metadata_json["sealing_state"]["cycle"]["state_revision"] = 6
            mock_transcript.metadata_json["sealing_state"]["cycle"]["analysis_cycle_id"] = "stale-cycle"
            await save_structured_case(
                tenant_id="tenant-test",
                owner_id="user-test",
                case_id="concurrency-test",
                state=state_b,
                runtime_path="test",
                binding_level="ORIENTATION",
            )

    asyncio.run(_run())
