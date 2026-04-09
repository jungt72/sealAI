"""
Tests for runtime/session_manager.py — Phase F-A.2

Covers Umbauplan F-A.2:
  test_session_starts_conversation  → zone = "conversation"
  test_session_escalates_to_governed → zone = "governed"
  test_session_stays_governed        → subsequent messages stay governed
  test_new_session_resets            → new session_id starts conversation

All Redis calls are mocked with a simple dict-backed fake.
"""
from __future__ import annotations

import asyncio
import json
from typing import Optional
from unittest.mock import MagicMock

import pytest

from app.agent.runtime.session_manager import (
    SessionEnvelope,
    _redis_key,
    apply_gate_decision_and_persist,
    apply_gate_decision_and_persist_async,
    get_or_create_session,
    load_session,
    save_session,
)


# ---------------------------------------------------------------------------
# Fake Redis (in-memory, sync)
# ---------------------------------------------------------------------------

class FakeRedis:
    """Minimal dict-backed Redis stub (get/set with ex TTL ignored)."""

    def __init__(self):
        self._store: dict[str, str] = {}

    def set(self, key: str, value: str, ex: int | None = None) -> None:
        self._store[key] = value

    def get(self, key: str) -> str | None:
        return self._store.get(key)

    def delete(self, key: str) -> None:
        self._store.pop(key, None)

    def __contains__(self, key: str) -> bool:
        return key in self._store


class AsyncFakeRedis(FakeRedis):
    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        super().set(key, value, ex=ex)

    async def get(self, key: str) -> str | None:
        return super().get(key)


# ---------------------------------------------------------------------------
# SessionEnvelope unit tests (no Redis)
# ---------------------------------------------------------------------------

class TestSessionEnvelope:
    def _make(self, zone="conversation") -> SessionEnvelope:
        return SessionEnvelope(
            session_id="s1",
            tenant_id="t1",
            user_id="u1",
            session_zone=zone,
        )

    def test_default_zone_is_conversation(self):
        env = self._make()
        assert env.session_zone == "conversation"

    def test_escalate_sets_governed(self):
        env = self._make()
        escalated = env.escalate_to_governed(turn=3, gate_decision_reason="hard_override:numeric_unit")
        assert escalated.session_zone == "governed"
        assert escalated.entered_governed_at_turn == 3
        assert escalated.last_gate_decision == "hard_override:numeric_unit"

    def test_escalate_does_not_mutate_original(self):
        env = self._make()
        _ = env.escalate_to_governed(turn=1, gate_decision_reason="test")
        assert env.session_zone == "conversation"

    def test_escalate_on_governed_is_noop(self):
        gov = self._make("governed")
        same = gov.escalate_to_governed(turn=99, gate_decision_reason="irrelevant")
        assert same is gov  # identical object returned

    def test_with_gate_decision_preserves_zone(self):
        env = self._make()
        updated = env.with_gate_decision("llm_binary_classification")
        assert updated.session_zone == "conversation"
        assert updated.last_gate_decision == "llm_binary_classification"

    def test_envelope_is_frozen(self):
        from pydantic import ValidationError as PydanticValidationError
        env = self._make()
        with pytest.raises((TypeError, AttributeError, PydanticValidationError)):
            env.session_zone = "governed"  # type: ignore[misc]

    def test_session_id_preserved_after_escalate(self):
        env = self._make()
        escalated = env.escalate_to_governed(turn=1, gate_decision_reason="x")
        assert escalated.session_id == env.session_id
        assert escalated.tenant_id == env.tenant_id
        assert escalated.user_id == env.user_id

    def test_satisfies_has_session_zone_protocol(self):
        """SessionEnvelope works with gate.decide_route() via HasSessionZone."""
        from app.agent.runtime.gate import HasSessionZone
        env = self._make()
        assert isinstance(env, HasSessionZone)


# ---------------------------------------------------------------------------
# Redis persistence (save / load)
# ---------------------------------------------------------------------------

class TestSessionPersistence:
    def test_save_and_load_roundtrip(self):
        redis = FakeRedis()
        env = SessionEnvelope(session_id="s1", tenant_id="t1", user_id="u1")
        save_session(env, redis_client=redis)
        loaded = load_session("t1", "s1", redis_client=redis)
        assert loaded is not None
        assert loaded.session_id == "s1"
        assert loaded.session_zone == "conversation"

    def test_load_missing_returns_none(self):
        redis = FakeRedis()
        result = load_session("t1", "missing", redis_client=redis)
        assert result is None

    def test_save_uses_tenant_scoped_key(self):
        redis = FakeRedis()
        env = SessionEnvelope(session_id="s1", tenant_id="t1", user_id="u1")
        save_session(env, redis_client=redis)
        expected_key = _redis_key("t1", "s1")
        assert expected_key in redis

    def test_tenant_isolation(self):
        """Sessions from different tenants do not collide."""
        redis = FakeRedis()
        env_t1 = SessionEnvelope(session_id="s1", tenant_id="t1", user_id="u1")
        env_t2 = SessionEnvelope(session_id="s1", tenant_id="t2", user_id="u2")
        env_t2_gov = env_t2.escalate_to_governed(turn=1, gate_decision_reason="x")
        save_session(env_t1, redis_client=redis)
        save_session(env_t2_gov, redis_client=redis)

        loaded_t1 = load_session("t1", "s1", redis_client=redis)
        loaded_t2 = load_session("t2", "s1", redis_client=redis)
        assert loaded_t1 is not None and loaded_t1.session_zone == "conversation"
        assert loaded_t2 is not None and loaded_t2.session_zone == "governed"

    def test_load_corrupt_data_returns_none(self):
        redis = FakeRedis()
        redis.set(_redis_key("t1", "s1"), "not-valid-json")
        result = load_session("t1", "s1", redis_client=redis)
        assert result is None

    def test_save_overwrites_previous(self):
        redis = FakeRedis()
        env = SessionEnvelope(session_id="s1", tenant_id="t1", user_id="u1")
        save_session(env, redis_client=redis)
        escalated = env.escalate_to_governed(turn=2, gate_decision_reason="test")
        save_session(escalated, redis_client=redis)
        loaded = load_session("t1", "s1", redis_client=redis)
        assert loaded is not None
        assert loaded.session_zone == "governed"


# ---------------------------------------------------------------------------
# Lifecycle: get_or_create_session
# ---------------------------------------------------------------------------

class TestGetOrCreateSession:
    def test_session_starts_conversation(self):
        """Fresh session has zone = conversation (Umbauplan F-A.2 test 1)."""
        redis = FakeRedis()
        env = get_or_create_session("t1", "s-new", "u1", redis_client=redis)
        assert env.session_zone == "conversation"

    def test_existing_session_loaded(self):
        redis = FakeRedis()
        env = SessionEnvelope(session_id="s1", tenant_id="t1", user_id="u1")
        escalated = env.escalate_to_governed(turn=1, gate_decision_reason="x")
        save_session(escalated, redis_client=redis)

        loaded = get_or_create_session("t1", "s1", "u1", redis_client=redis)
        assert loaded.session_zone == "governed"

    def test_new_session_resets_to_conversation(self):
        """New session_id always starts in conversation (Umbauplan F-A.2 test 4)."""
        redis = FakeRedis()
        # Old session was governed
        old = SessionEnvelope(session_id="s-old", tenant_id="t1", user_id="u1")
        save_session(old.escalate_to_governed(turn=1, gate_decision_reason="x"), redis_client=redis)

        # New session id → fresh envelope
        fresh = get_or_create_session("t1", "s-new", "u1", redis_client=redis)
        assert fresh.session_zone == "conversation"
        assert fresh.session_id == "s-new"

    def test_get_or_create_persists_fresh_session(self):
        redis = FakeRedis()
        get_or_create_session("t1", "s1", "u1", redis_client=redis)
        assert _redis_key("t1", "s1") in redis


# ---------------------------------------------------------------------------
# apply_gate_decision_and_persist
# ---------------------------------------------------------------------------

class TestApplyGateDecisionAndPersist:
    def _conv_env(self, session_id="s1") -> SessionEnvelope:
        return SessionEnvelope(session_id=session_id, tenant_id="t1", user_id="u1")

    def test_session_escalates_to_governed(self):
        """Gate says GOVERNED → zone becomes governed (Umbauplan F-A.2 test 2)."""
        redis = FakeRedis()
        env = self._conv_env()
        updated = apply_gate_decision_and_persist(
            env,
            gate_route="GOVERNED",
            gate_reason="hard_override:numeric_unit",
            turn=1,
            redis_client=redis,
        )
        assert updated.session_zone == "governed"
        assert updated.entered_governed_at_turn == 1

    def test_session_stays_governed_on_subsequent_calls(self):
        """Governed session stays governed regardless of new gate decision (Umbauplan F-A.2 test 3)."""
        redis = FakeRedis()
        env = self._conv_env()

        # First request escalates
        gov = apply_gate_decision_and_persist(
            env,
            gate_route="GOVERNED",
            gate_reason="hard_override:numeric_unit",
            turn=1,
            redis_client=redis,
        )
        assert gov.session_zone == "governed"

        # Second request — gate might say a light mode but session stays governed
        still_gov = apply_gate_decision_and_persist(
            gov,
            gate_route="CONVERSATION",
            gate_reason="deterministic_instant:greeting_or_smalltalk",
            turn=2,
            redis_client=redis,
        )
        assert still_gov.session_zone == "governed"

    def test_conversation_gate_does_not_escalate(self):
        redis = FakeRedis()
        env = self._conv_env()
        updated = apply_gate_decision_and_persist(
            env,
            gate_route="CONVERSATION",
            gate_reason="deterministic_instant:greeting_or_smalltalk",
            turn=1,
            redis_client=redis,
        )
        assert updated.session_zone == "conversation"

    def test_gate_reason_recorded(self):
        redis = FakeRedis()
        env = self._conv_env()
        updated = apply_gate_decision_and_persist(
            env,
            gate_route="CONVERSATION",
            gate_reason="deterministic_instant:greeting_or_smalltalk",
            turn=1,
            redis_client=redis,
        )
        assert updated.last_gate_decision == "deterministic_instant:greeting_or_smalltalk"

    def test_updated_envelope_persisted(self):
        redis = FakeRedis()
        env = self._conv_env()
        apply_gate_decision_and_persist(
            env,
            gate_route="GOVERNED",
            gate_reason="x",
            turn=1,
            redis_client=redis,
        )
        loaded = load_session("t1", "s1", redis_client=redis)
        assert loaded is not None
        assert loaded.session_zone == "governed"

    def test_governed_session_escalate_is_noop(self):
        redis = FakeRedis()
        gov = SessionEnvelope(
            session_id="s1", tenant_id="t1", user_id="u1", session_zone="governed"
        )
        # Calling again with GOVERNED on already-governed session
        result = apply_gate_decision_and_persist(
            gov,
            gate_route="GOVERNED",
            gate_reason="sticky_governed_session",
            turn=5,
            redis_client=redis,
        )
        assert result.session_zone == "governed"
        # entered_governed_at_turn should NOT be updated (was not set in original)
        assert result.entered_governed_at_turn is None

    # ── Fix 1: audit log preservation ─────────────────────────────────────

    def test_escalation_reason_preserved_in_governed_session(self):
        """Original escalation reason must NOT be overwritten by sticky_governed_session."""
        redis = FakeRedis()
        env = self._conv_env()

        # Escalate with a meaningful origin reason
        gov = apply_gate_decision_and_persist(
            env,
            gate_route="GOVERNED",
            gate_reason="hard_override:numeric_unit",
            turn=1,
            redis_client=redis,
        )
        assert gov.last_gate_decision == "hard_override:numeric_unit"

        # Subsequent call with sticky reason must NOT overwrite origin
        after_sticky = apply_gate_decision_and_persist(
            gov,
            gate_route="GOVERNED",
            gate_reason="sticky_governed_session",
            turn=2,
            redis_client=redis,
        )
        assert after_sticky.last_gate_decision == "hard_override:numeric_unit"

    def test_conversation_override_in_governed_session_preserves_reason(self):
        """Light-mode gate in governed session must not overwrite escalation reason."""
        redis = FakeRedis()
        gov = SessionEnvelope(
            session_id="s1", tenant_id="t1", user_id="u1",
            session_zone="governed",
            last_gate_decision="hard_override:numeric_unit",
        )
        result = apply_gate_decision_and_persist(
            gov,
            gate_route="CONVERSATION",
            gate_reason="governed_instant_override",
            turn=3,
            redis_client=redis,
        )
        assert result.session_zone == "governed"
        assert result.last_gate_decision == "hard_override:numeric_unit"

    # ── Fix 2: turn tracking ──────────────────────────────────────────────

    def test_turn_count_increments_on_each_call(self):
        """turn_count must increment on every apply_gate_decision_and_persist call."""
        redis = FakeRedis()
        env = self._conv_env()
        assert env.turn_count == 0

        e1 = apply_gate_decision_and_persist(
            env, gate_route="CONVERSATION", gate_reason="deterministic_instant:greeting_or_smalltalk",
            turn=1, redis_client=redis,
        )
        assert e1.turn_count == 1

        e2 = apply_gate_decision_and_persist(
            e1, gate_route="CONVERSATION", gate_reason="deterministic_instant:greeting_or_smalltalk",
            turn=2, redis_client=redis,
        )
        assert e2.turn_count == 2

    def test_entered_governed_at_turn_uses_internal_counter(self):
        """entered_governed_at_turn must reflect the internal turn_count, not the caller's turn."""
        redis = FakeRedis()
        # Pre-warm: 2 conversation turns first
        env = self._conv_env()
        e1 = apply_gate_decision_and_persist(
            env, gate_route="CONVERSATION", gate_reason="deterministic_instant:greeting_or_smalltalk",
            turn=0, redis_client=redis,
        )
        e2 = apply_gate_decision_and_persist(
            e1, gate_route="CONVERSATION", gate_reason="deterministic_instant:greeting_or_smalltalk",
            turn=0, redis_client=redis,
        )
        assert e2.turn_count == 2

        # Now escalate — entered_governed_at_turn must be 3 (internal), not 0 (caller)
        gov = apply_gate_decision_and_persist(
            e2, gate_route="GOVERNED", gate_reason="hard_override:numeric_unit",
            turn=0, redis_client=redis,
        )
        assert gov.entered_governed_at_turn == 3
        assert gov.turn_count == 3

    def test_turn_count_increments_for_governed_session(self):
        """turn_count must also increment for governed sessions on each call."""
        redis = FakeRedis()
        gov = SessionEnvelope(
            session_id="s1", tenant_id="t1", user_id="u1",
            session_zone="governed", turn_count=5,
        )
        result = apply_gate_decision_and_persist(
            gov, gate_route="GOVERNED", gate_reason="sticky_governed_session",
            turn=0, redis_client=redis,
        )
        assert result.turn_count == 6


class TestApplyGateDecisionAndPersistAsync:
    def _conv_env(self, session_id="s1") -> SessionEnvelope:
        return SessionEnvelope(session_id=session_id, tenant_id="t1", user_id="u1")

    def test_async_session_escalates_to_governed(self):
        redis = AsyncFakeRedis()
        env = self._conv_env()
        updated = asyncio.run(
            apply_gate_decision_and_persist_async(
                env,
                gate_route="GOVERNED",
                gate_reason="hard_override:numeric_unit",
                turn=1,
                redis_client=redis,
            )
        )
        assert updated.session_zone == "governed"

    def test_async_conversation_gate_preserves_zone(self):
        redis = AsyncFakeRedis()
        env = self._conv_env()
        updated = asyncio.run(
            apply_gate_decision_and_persist_async(
                env,
                gate_route="CONVERSATION",
                gate_reason="deterministic_instant:greeting_or_smalltalk",
                turn=1,
                redis_client=redis,
            )
        )
        assert updated.session_zone == "conversation"


# ---------------------------------------------------------------------------
# Integration: gate + session_manager
# ---------------------------------------------------------------------------

class TestGateSessionIntegration:
    """End-to-end: gate decision → session zone update."""

    def test_technical_message_escalates_session(self):
        from unittest.mock import patch
        from app.agent.runtime.gate import decide_route, LLMGateResult

        redis = FakeRedis()
        env = get_or_create_session("t1", "s1", "u1", redis_client=redis)
        assert env.session_zone == "conversation"

        # Gate decides GOVERNED (hard override — LLM not called)
        decision = decide_route("PTFE-Dichtung für 180°C Dampf", env)
        assert decision.route == "GOVERNED"

        # Apply decision to session
        updated = apply_gate_decision_and_persist(
            env,
            gate_route=decision.route,
            gate_reason=decision.reason,
            turn=1,
            redis_client=redis,
        )
        assert updated.session_zone == "governed"

    def test_trivial_message_keeps_conversation_zone(self):
        from unittest.mock import patch
        from app.agent.runtime.gate import decide_route, LLMGateResult

        redis = FakeRedis()
        env = get_or_create_session("t1", "s1", "u1", redis_client=redis)

        llm_result = LLMGateResult(routing="CONVERSATION", confidence=0.92)
        with patch("app.agent.runtime.gate._call_gate_llm", return_value=llm_result):
            decision = decide_route("Was ist ein O-Ring?", env)
        assert decision.route == "CONVERSATION"

        updated = apply_gate_decision_and_persist(
            env,
            gate_route=decision.route,
            gate_reason=decision.reason,
            turn=1,
            redis_client=redis,
        )
        assert updated.session_zone == "conversation"
