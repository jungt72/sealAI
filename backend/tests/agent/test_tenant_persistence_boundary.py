"""
A5: Direct guard-path tests for tenant-complete persistence layer.

Tests the critical trust boundary in persist.py:
- build_structured_case_storage_key is tenant-scoped
- load_structured_case fail-closed on tenant mismatch (persisted != request)
- load_structured_case accepts legacy records (persisted tenant_id is None)
- load_structured_case sets tenant_id from persisted record
- _build_structured_case_payload embeds tenant_id in payload
- delete_structured_case uses tenant-scoped key

These tests mock AsyncSessionLocal and ChatTranscript so they run offline
without a database. They exercise the guard logic directly, not through the router.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.history.persist import (
    PersistedStructuredCasePayload,
    STRUCTURED_CASE_RECORD_TYPE,
    _build_structured_case_payload,
    _build_legacy_storage_key,
    build_structured_case_storage_key,
    load_structured_case,
    delete_structured_case,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _minimal_state(tenant_id: str = "tenant-a") -> dict:
    return {
        "messages": [],
        "sealing_state": {"cycle": {}},
        "working_profile": {},
        "relevant_fact_cards": [],
        "tenant_id": tenant_id,
    }


def _persisted_payload_dict(tenant_id: str | None = "tenant-a", owner_id: str = "user-1", case_id: str = "case-1") -> dict:
    """Minimal valid persisted payload matching PersistedStructuredCasePayload."""
    return {
        "record_type": STRUCTURED_CASE_RECORD_TYPE,
        "case_id": case_id,
        "session_id": case_id,
        "owner_id": owner_id,
        "runtime_path": "STRUCTURED_QUALIFICATION",
        "binding_level": "QUALIFIED_PRESELECTION",
        "sealing_state": {"cycle": {}},
        "case_state": None,
        "working_profile": {},
        "relevant_fact_cards": [],
        "messages": [],
        "tenant_id": tenant_id,
    }


def _make_transcript_mock(metadata: dict, user_id: str = "user-1") -> MagicMock:
    t = MagicMock()
    t.metadata_json = metadata
    t.user_id = user_id
    return t


# ---------------------------------------------------------------------------
# build_structured_case_storage_key
# ---------------------------------------------------------------------------

class TestStorageKey:
    def test_key_includes_tenant_id(self):
        key = build_structured_case_storage_key("tenant-a", "user-1", "case-1")
        assert "tenant-a" in key

    def test_key_includes_owner_id(self):
        key = build_structured_case_storage_key("tenant-a", "user-1", "case-1")
        assert "user-1" in key

    def test_key_includes_case_id(self):
        key = build_structured_case_storage_key("tenant-a", "user-1", "case-1")
        assert "case-1" in key

    def test_different_tenants_produce_different_keys(self):
        key_a = build_structured_case_storage_key("tenant-a", "user-1", "case-1")
        key_b = build_structured_case_storage_key("tenant-b", "user-1", "case-1")
        assert key_a != key_b

    def test_different_owners_produce_different_keys(self):
        key_a = build_structured_case_storage_key("tenant-a", "user-1", "case-1")
        key_b = build_structured_case_storage_key("tenant-a", "user-2", "case-1")
        assert key_a != key_b

    def test_key_format(self):
        key = build_structured_case_storage_key("tenant-a", "user-1", "case-1")
        assert key == "agent_case:tenant-a:user-1:case-1"


# ---------------------------------------------------------------------------
# _build_structured_case_payload — tenant_id embedded
# ---------------------------------------------------------------------------

class TestBuildPayload:
    def test_payload_carries_tenant_id(self):
        state = _minimal_state(tenant_id="tenant-a")
        payload = _build_structured_case_payload(
            tenant_id="tenant-a",
            owner_id="user-1",
            case_id="case-1",
            state=state,
            runtime_path="STRUCTURED_QUALIFICATION",
            binding_level="QUALIFIED_PRESELECTION",
        )
        assert payload.tenant_id == "tenant-a"

    def test_payload_tenant_id_comes_from_parameter_not_state(self):
        """Caller-supplied tenant_id is authoritative, not state["tenant_id"]."""
        state = _minimal_state(tenant_id="state-tenant")
        payload = _build_structured_case_payload(
            tenant_id="caller-tenant",
            owner_id="user-1",
            case_id="case-1",
            state=state,
            runtime_path="STRUCTURED_QUALIFICATION",
            binding_level="QUALIFIED_PRESELECTION",
        )
        # The payload must use the explicit caller tenant_id.
        assert payload.tenant_id == "caller-tenant"


# ---------------------------------------------------------------------------
# load_structured_case — fail-closed tenant mismatch guard
# ---------------------------------------------------------------------------

class TestLoadStructuredCaseTenantGuard:
    def _run_load(self, transcript_mock, *, tenant_id: str, owner_id: str, case_id: str):
        """Patch AsyncSessionLocal and ChatTranscript and call load_structured_case."""
        session_mock = AsyncMock()
        session_mock.get = AsyncMock(return_value=transcript_mock)
        session_ctx = MagicMock()
        session_ctx.__aenter__ = AsyncMock(return_value=session_mock)
        session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.database.AsyncSessionLocal", return_value=session_ctx):
            return asyncio.run(
                load_structured_case(tenant_id=tenant_id, owner_id=owner_id, case_id=case_id)
            )

    def test_matching_tenant_id_returns_state(self):
        meta = _persisted_payload_dict(tenant_id="tenant-a", owner_id="user-1", case_id="case-1")
        transcript = _make_transcript_mock(meta, user_id="user-1")
        result = self._run_load(transcript, tenant_id="tenant-a", owner_id="user-1", case_id="case-1")
        assert result is not None
        assert result["tenant_id"] == "tenant-a"

    def test_mismatched_tenant_id_returns_none(self):
        """Persisted tenant-a, request from tenant-b → fail-closed → None."""
        meta = _persisted_payload_dict(tenant_id="tenant-a", owner_id="user-1", case_id="case-1")
        transcript = _make_transcript_mock(meta, user_id="user-1")
        result = self._run_load(transcript, tenant_id="tenant-b", owner_id="user-1", case_id="case-1")
        assert result is None

    def test_legacy_record_without_tenant_id_is_rejected_on_tenant_scoped_request(self):
        """Tenant-scoped runtime paths must fail closed for tenant-less legacy records."""
        meta = _persisted_payload_dict(tenant_id=None, owner_id="user-1", case_id="case-1")
        transcript = _make_transcript_mock(meta, user_id="user-1")
        session_mock = AsyncMock()
        session_mock.get = AsyncMock(side_effect=[None, transcript])
        session_ctx = MagicMock()
        session_ctx.__aenter__ = AsyncMock(return_value=session_mock)
        session_ctx.__aexit__ = AsyncMock(return_value=False)
        with patch("app.database.AsyncSessionLocal", return_value=session_ctx):
            result = asyncio.run(
                load_structured_case(tenant_id="tenant-a", owner_id="user-1", case_id="case-1")
            )
        assert result is None

    def test_legacy_record_with_matching_explicit_tenant_id_is_loadable(self):
        meta = _persisted_payload_dict(tenant_id="new-tenant", owner_id="user-1", case_id="case-1")
        transcript = _make_transcript_mock(meta, user_id="user-1")
        result = self._run_load(transcript, tenant_id="new-tenant", owner_id="user-1", case_id="case-1")
        assert result is not None
        assert result["tenant_id"] == "new-tenant"

    def test_cross_owner_access_returns_none(self):
        """user_id mismatch in transcript → None (existing guard, not A5)."""
        meta = _persisted_payload_dict(tenant_id="tenant-a", owner_id="user-1", case_id="case-1")
        transcript = _make_transcript_mock(meta, user_id="user-1")
        # Pass different owner_id in request
        result = self._run_load(transcript, tenant_id="tenant-a", owner_id="user-2", case_id="case-1")
        assert result is None

    def test_missing_transcript_returns_none(self):
        session_mock = AsyncMock()
        session_mock.get = AsyncMock(return_value=None)
        session_ctx = MagicMock()
        session_ctx.__aenter__ = AsyncMock(return_value=session_mock)
        session_ctx.__aexit__ = AsyncMock(return_value=False)
        with patch("app.database.AsyncSessionLocal", return_value=session_ctx):
            result = asyncio.run(
                load_structured_case(tenant_id="tenant-a", owner_id="user-1", case_id="case-1")
            )
        assert result is None

    def test_wrong_record_type_returns_none(self):
        meta = _persisted_payload_dict(tenant_id="tenant-a")
        meta["record_type"] = "other_record_type"
        transcript = _make_transcript_mock(meta, user_id="user-1")
        result = self._run_load(transcript, tenant_id="tenant-a", owner_id="user-1", case_id="case-1")
        assert result is None


# ---------------------------------------------------------------------------
# delete_structured_case — tenant-scoped key
# ---------------------------------------------------------------------------

class TestDeleteStructuredCase:
    def test_delete_uses_tenant_scoped_key(self):
        """Session.get is called with the tenant-scoped key first."""
        from app.models.chat_transcript import ChatTranscript

        session_mock = AsyncMock()
        session_mock.get = AsyncMock(return_value=None)
        session_ctx = MagicMock()
        session_ctx.__aenter__ = AsyncMock(return_value=session_mock)
        session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.database.AsyncSessionLocal", return_value=session_ctx):
            asyncio.run(
                delete_structured_case(tenant_id="tenant-a", owner_id="user-1", case_id="case-1")
            )

        expected_key = build_structured_case_storage_key("tenant-a", "user-1", "case-1")
        # First call must use the new tenant-scoped key.
        first_call = session_mock.get.await_args_list[0]
        assert first_call.args == (ChatTranscript, expected_key)

    def test_delete_cross_owner_is_noop(self):
        """Transcript owned by user-1 cannot be deleted by user-2."""
        transcript = _make_transcript_mock(
            _persisted_payload_dict(tenant_id="tenant-a", owner_id="user-1"),
            user_id="user-1",
        )
        session_mock = AsyncMock()
        session_mock.get = AsyncMock(return_value=transcript)
        session_mock.delete = AsyncMock()
        session_mock.commit = AsyncMock()
        session_ctx = MagicMock()
        session_ctx.__aenter__ = AsyncMock(return_value=session_mock)
        session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.database.AsyncSessionLocal", return_value=session_ctx):
            asyncio.run(
                delete_structured_case(tenant_id="tenant-a", owner_id="user-2", case_id="case-1")
            )

        # delete must NOT be called because user_id check fails
        session_mock.delete.assert_not_awaited()


# ---------------------------------------------------------------------------
# A5 Follow-up — Legacy key compatibility
# ---------------------------------------------------------------------------

class TestLegacyKeyFormat:
    def test_legacy_key_format(self):
        """Pre-A5 2-part key has the expected format."""
        key = _build_legacy_storage_key("user-1", "case-1")
        assert key == "agent_case:user-1:case-1"

    def test_new_and_legacy_keys_differ(self):
        key_new = build_structured_case_storage_key("tenant-a", "user-1", "case-1")
        key_legacy = _build_legacy_storage_key("user-1", "case-1")
        assert key_new != key_legacy


class TestLegacyKeyFallbackOnLoad:
    """load_structured_case must fall back to the old 2-part key if the new key yields nothing."""

    def _run_load(self, new_transcript, legacy_transcript, *, tenant_id: str, owner_id: str, case_id: str):
        """new_transcript → lookup for new key; legacy_transcript → lookup for legacy key."""
        session_mock = AsyncMock()
        new_key = build_structured_case_storage_key(tenant_id, owner_id, case_id)
        legacy_key = _build_legacy_storage_key(owner_id, case_id)

        async def _get(model, key, **kwargs):
            if key == new_key:
                return new_transcript
            if key == legacy_key:
                return legacy_transcript
            return None

        session_mock.get = _get
        session_ctx = MagicMock()
        session_ctx.__aenter__ = AsyncMock(return_value=session_mock)
        session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.database.AsyncSessionLocal", return_value=session_ctx):
            return asyncio.run(
                load_structured_case(tenant_id=tenant_id, owner_id=owner_id, case_id=case_id)
            )

    def test_legacy_record_with_matching_explicit_tenant_id_is_returned_when_new_key_absent(self):
        """Legacy-key fallback remains available only for records with matching tenant proof."""
        meta = _persisted_payload_dict(tenant_id="tenant-a", owner_id="user-1", case_id="case-1")
        legacy_t = _make_transcript_mock(meta, user_id="user-1")
        result = self._run_load(None, legacy_t, tenant_id="tenant-a", owner_id="user-1", case_id="case-1")
        assert result is not None
        assert result["tenant_id"] == "tenant-a"

    def test_legacy_record_without_tenant_id_is_not_returned_when_new_key_absent(self):
        """Tenant-less legacy records stay unreachable on tenant-scoped user paths."""
        meta = _persisted_payload_dict(tenant_id=None, owner_id="user-1", case_id="case-1")
        legacy_t = _make_transcript_mock(meta, user_id="user-1")
        result = self._run_load(None, legacy_t, tenant_id="tenant-a", owner_id="user-1", case_id="case-1")
        assert result is None

    def test_legacy_record_not_visible_cross_tenant(self):
        """Legacy record stored for user-1 must not be returned for user-2 (cross-owner guard)."""
        meta = _persisted_payload_dict(tenant_id=None, owner_id="user-1", case_id="case-1")
        legacy_t = _make_transcript_mock(meta, user_id="user-1")
        # Different owner_id in request → transcript.user_id check fails
        result = self._run_load(None, legacy_t, tenant_id="tenant-a", owner_id="user-2", case_id="case-1")
        assert result is None

    def test_new_key_takes_priority_over_legacy_key(self):
        """If both keys resolve, the new key is used (new_transcript beats legacy_transcript)."""
        meta_new = _persisted_payload_dict(tenant_id="tenant-a", owner_id="user-1", case_id="case-1")
        meta_legacy = _persisted_payload_dict(tenant_id=None, owner_id="user-1", case_id="case-1")
        meta_legacy["case_state"] = {"legacy": True}  # distinguishable

        new_t = _make_transcript_mock(meta_new, user_id="user-1")
        legacy_t = _make_transcript_mock(meta_legacy, user_id="user-1")
        result = self._run_load(new_t, legacy_t, tenant_id="tenant-a", owner_id="user-1", case_id="case-1")
        assert result is not None
        # payload.case_state is None for the new record (not the legacy one)
        assert result.get("case_state") is None

    def test_legacy_record_with_mismatched_tenant_id_is_rejected(self):
        """If a legacy record somehow has a mismatched tenant_id, fail-closed guard still applies."""
        meta = _persisted_payload_dict(tenant_id="other-tenant", owner_id="user-1", case_id="case-1")
        legacy_t = _make_transcript_mock(meta, user_id="user-1")
        result = self._run_load(None, legacy_t, tenant_id="tenant-a", owner_id="user-1", case_id="case-1")
        assert result is None


class TestLegacyKeyFallbackOnDelete:
    """delete_structured_case must fall back to the old 2-part key if the new key yields nothing."""

    def _run_delete(self, new_transcript, legacy_transcript, *, tenant_id, owner_id, case_id):
        new_key = build_structured_case_storage_key(tenant_id, owner_id, case_id)
        legacy_key = _build_legacy_storage_key(owner_id, case_id)

        session_mock = AsyncMock()

        async def _get(model, key, **kwargs):
            if key == new_key:
                return new_transcript
            if key == legacy_key:
                return legacy_transcript
            return None

        session_mock.get = _get
        session_mock.delete = AsyncMock()
        session_mock.commit = AsyncMock()
        session_ctx = MagicMock()
        session_ctx.__aenter__ = AsyncMock(return_value=session_mock)
        session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.database.AsyncSessionLocal", return_value=session_ctx):
            asyncio.run(
                delete_structured_case(tenant_id=tenant_id, owner_id=owner_id, case_id=case_id)
            )
        return session_mock

    def test_legacy_record_with_matching_explicit_tenant_id_is_deleted_when_new_key_absent(self):
        meta = _persisted_payload_dict(tenant_id="tenant-a", owner_id="user-1", case_id="case-1")
        legacy_t = _make_transcript_mock(meta, user_id="user-1")
        session_mock = self._run_delete(None, legacy_t, tenant_id="tenant-a", owner_id="user-1", case_id="case-1")
        session_mock.delete.assert_awaited_once_with(legacy_t)

    def test_legacy_record_without_tenant_id_is_not_deleted_when_new_key_absent(self):
        meta = _persisted_payload_dict(tenant_id=None, owner_id="user-1", case_id="case-1")
        legacy_t = _make_transcript_mock(meta, user_id="user-1")
        session_mock = self._run_delete(None, legacy_t, tenant_id="tenant-a", owner_id="user-1", case_id="case-1")
        session_mock.delete.assert_not_awaited()

    def test_delete_is_noop_when_both_keys_absent(self):
        session_mock = self._run_delete(None, None, tenant_id="tenant-a", owner_id="user-1", case_id="case-1")
        session_mock.delete.assert_not_awaited()


# ---------------------------------------------------------------------------
# A5 Follow-up — upsert_conversation passes tenant_id
# ---------------------------------------------------------------------------

class TestUpsertConversationTenantId:
    def test_upsert_conversation_accepts_tenant_id(self):
        """upsert_conversation signature accepts tenant_id without error."""
        from app.services.chat.conversations import upsert_conversation
        # Patch Redis so no real connection is made.
        with patch("app.services.chat.conversations._redis_client") as mock_redis:
            mock_r = MagicMock()
            mock_r.hgetall.return_value = {}
            mock_r.pipeline.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_r.pipeline.return_value.__exit__ = MagicMock(return_value=False)
            pipe = MagicMock()
            mock_r.pipeline.return_value = pipe
            pipe.hset = MagicMock()
            pipe.expire = MagicMock()
            pipe.zadd = MagicMock()
            pipe.execute = MagicMock()
            mock_redis.return_value = mock_r
            # Must not raise TypeError
            upsert_conversation(
                "user-1", "conv-1",
                tenant_id="tenant-a",
                first_user_message="hello",
                last_preview="hello",
            )
        # If we got here, the call succeeded
        assert True

    def test_upsert_conversation_stores_tenant_id_in_hash(self):
        """When tenant_id is provided, it is included in the hset mapping."""
        from app.services.chat.conversations import upsert_conversation

        captured_mapping: dict = {}

        with patch("app.services.chat.conversations._redis_client") as mock_redis:
            mock_r = MagicMock()
            mock_r.hgetall.return_value = {}
            pipe = MagicMock()

            def _hset(key, mapping):
                captured_mapping.update(mapping)

            pipe.hset = _hset
            pipe.expire = MagicMock()
            pipe.zadd = MagicMock()
            pipe.execute = MagicMock()
            mock_r.pipeline.return_value = pipe
            mock_r.zcard.return_value = 0
            mock_redis.return_value = mock_r

            upsert_conversation(
                "user-1", "conv-1",
                tenant_id="tenant-a",
                first_user_message="hello",
            )
        assert captured_mapping.get("tenant_id") == "tenant-a"
